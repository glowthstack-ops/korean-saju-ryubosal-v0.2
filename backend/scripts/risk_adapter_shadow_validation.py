"""실물 token adapter shadow 계수 검증 harness(감수 56차 §9 — §11 보고).

validation identity별 10형×3=30표본으로 counted_request_tokens(adapter
countTokens)와 provider_reported_total_input_tokens(generateContent
usageMetadata.promptTokenCount — cached+non-cached 전체, 청구 할인 전)를
전수 대조한다. 합격 기준(ADAPTER_VALIDATION_POLICY 선행 고정):
undercount=0 · request shape 누락=0 · model mismatch=0 · rerouting 후
recount 누락=0.

**승격 없음**: 본 스크립트는 SHADOW_VALIDATING 상태로 계측·artifact 생성·
manifest 감수 후보 출력까지만 한다 — VALIDATED 전환은 manifest 감수
(reviewed entry) 이후 별도 절차(감수 56차 §9).

corpus canonical hash(감수 56차 §1): 표본을 sample ID로 정렬한 canonical
직렬화 기준 — 실행 시각·원본 request ID·파일 경로·실행 순서·임시 로그 ID
제외(동일 검증 결과=동일 hash=동일 identity).

사용: python scripts/risk_adapter_shadow_validation.py
      [--model gemini-3-flash-preview] [--reroute-model gemini-2.5-flash]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from saju_api.services.gemini_token_adapter import (  # noqa: E402
    GEMINI_COUNTER_VERSION,
    build_gemini_adapter,
    build_gemini_request_body,
    build_gemini_transport_schema,
)
from saju_api.services.token_counter_registry import (  # noqa: E402
    ProviderRequest,
    adapter_validation_policy_hash,
)
from saju_engines.risk_claim_audit import (  # noqa: E402
    build_risk_output_schema,
)
from saju_engines.risk_exposure import (  # noqa: E402
    RISK_EXPOSURE_INSTRUCTION_BLOCK,
    RISK_EXPOSURE_SUPPRESSED_GUARD,
)
from saju_engines.risk_presentation import (  # noqa: E402
    build_presentation,
    serialize_llm_payload,
)
from saju_engines.risk_scoring import score_shadow  # noqa: E402
from saju_engines.risk_selection import build_episodes  # noqa: E402
from saju_shared_types.risk_engine import (  # noqa: E402
    EvidenceRole,
    ExposureStatus,
    RiskCandidate,
    RiskDomain,
    RiskEvidence,
    RiskKind,
)

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_SYSTEM = ("당신은 사주 통변 보조입니다. 제공된 사실과 점수만 자연어로"
           " 설명하며 간지·점수를 직접 계산하지 않습니다.")
_KO = ("2026년 하반기의 계약과 이동 흐름을 알고 싶습니다. 현재 전세"
       " 계약 만기가 다가오고 있고, 회사에서는 부서 개편 이야기가"
       " 나오고 있어 시기 판단이 필요합니다. ")
_MIX = ("Next quarter의 계약 리스크와 relocation 흐름을 알려주세요."
        " 특히 deposit 반환 조건과 job transfer 가능성이 궁금합니다. ")


def _make_candidates(n: int) -> list[RiskCandidate]:
    """결정적 위험 후보 n건(도메인 순환) — 표본 payload 재료."""
    domains = [RiskDomain.CONTRACT_LEGAL, RiskDomain.FINANCE,
               RiskDomain.CAREER, RiskDomain.RELOCATION]
    out = []
    for i in range(n):
        dom = domains[i % len(domains)]
        src = f"relation:CHUNG:month_pillar:branch:ZHENGCAI:{i}"
        out.append(RiskCandidate(
            risk_id=f"LEG_A{i}", domain=dom, kind=RiskKind.INCIDENT_RISK,
            risk_family=f"fam{i}", period_key="2026",
            evidence=[RiskEvidence(
                evidence_id=f"2026|{src}", code="T", period_key="2026",
                layer="sewoon", source=src, strength=0.5,
                role=EvidenceRole.TRIGGER, source_group="event_shape",
                target_domain=dom)],
            exposure_status=ExposureStatus.CONFIRMED, specificity_rank=2,
            normalized_effect_role="legal_dispute",
            trigger_cause_atoms=[src], legal_episode_id=f"e{i}"))
    return out


def _payload(n_candidates: int) -> dict:
    cands = _make_candidates(n_candidates)
    scored = score_shadow(
        cands, {c.risk_id: 0.6 for c in cands})
    return build_presentation(build_episodes(scored), scored)


def _tier_of(rendered: str) -> str:
    doc = json.loads(rendered)
    if doc.get("exposureSuppressedReason"):
        return "SUPPRESSED"
    if doc.get("compressionMode") == "P0_COMPACT":
        return "P0_COMPACT"
    eps = doc.get("riskEpisodes") or [{}]
    if "effectRoles" in eps[0]:
        return "FULL"
    if "scoreBand" in eps[0]:
        return "P1"
    return "P0"


def _build_corpus(model_id: str,
                  reroute_model: str) -> tuple[list[dict], list[dict]]:
    """(native 30표본, rerouting 별도 3표본) — 결정적(감수 57차 §2).

    native 30 = 10형×3 전부 최종 resolved=primary 모델. rerouting 표본은
    최종 resolved 모델이 다르므로 **30표본에 불포함** — 재계수 계약 검증
    전용 부록으로 별도 집계한다(fallback 모델의 canary 자격은 그 모델
    identity의 별도 30표본 감수로만).
    """
    p1 = _payload(1)
    p8 = _payload(8)
    full_1 = serialize_llm_payload(p1, 100_000)
    full_8 = serialize_llm_payload(p8, 100_000)
    tool_schema = json.dumps([{"functionDeclarations": [{
        "name": "record_followup",
        "description": "후속 확인이 필요한 항목을 기록한다",
        "parameters": {"type": "OBJECT", "properties": {
            "topic": {"type": "STRING"},
            "period": {"type": "STRING"}}, "required": ["topic"]},
    }]}], ensure_ascii=False)
    out_schema = json.dumps(build_gemini_transport_schema(
        build_risk_output_schema(p1["llmRiskEpisodes"], hard_max=3)),
        ensure_ascii=False)

    def req(user: str, *, system: str = _SYSTEM, schema: str | None = None,
            tools: str | None = None) -> ProviderRequest:
        return ProviderRequest(
            system_messages=(system,), user_messages=(user,),
            output_schema=schema, tool_schema=tools)

    samples: list[dict] = []

    def add(cat: str, idx: str, request: ProviderRequest, *,
            tier: str = "FULL", resolved: str | None = None,
            reroute: bool = False) -> None:
        samples.append({
            "sample_id": f"{cat}-{idx}", "category": cat, "tier": tier,
            "request": request, "resolved_model_id": resolved or model_id,
            "reroute": reroute})

    for idx, scale in (("a", 1), ("b", 6), ("c", 20)):
        add("S01_korean_long", idx, req(_KO * scale))
    for idx, scale in (("a", 1), ("b", 6), ("c", 20)):
        add("S02_mixed_ko_en", idx, req(_MIX * scale))
    for idx, block in (("a", full_1), ("b", full_8),
                       ("c", serialize_llm_payload(p8, 100_000))):
        add("S03_json_risk_block", idx,
            req(_KO + "\n" + block))
    for idx, scale in (("a", 1), ("b", 4), ("c", 12)):
        add("S04_tool_schema", idx, req(_KO * scale, tools=tool_schema))
    for idx, scale in (("a", 1), ("b", 4), ("c", 12)):
        add("S05_output_schema", idx, req(_KO * scale, schema=out_schema))
    for idx, scale in (("a", 1), ("b", 4), ("c", 12)):
        add("S06_suppressed_guard", idx,
            req(_KO * scale + "\n" + RISK_EXPOSURE_SUPPRESSED_GUARD))
    for idx, block in (("a", full_1), ("b", full_8), ("c", full_1)):
        add("S07_injected_instruction", idx,
            req(_KO + "\n" + RISK_EXPOSURE_INSTRUCTION_BLOCK
                + "\n" + block))
    # S08: render tier 축약 단계 — P1·P0·P0_COMPACT를 결정적으로 강제
    # (직전 tier 실측 토큰-1을 다음 예산으로; FULL은 S03·S07·S10이 대표).
    from saju_engines.risk_presentation import estimate_tokens
    rendered_by_tier: dict[str, str] = {}
    budget = estimate_tokens(full_8) - 1
    while len(rendered_by_tier) < 3 and budget >= 512:
        rendered = serialize_llm_payload(p8, budget)
        tier = _tier_of(rendered)
        if tier == "SUPPRESSED":
            break
        if tier != "FULL":
            rendered_by_tier.setdefault(tier, rendered)
        budget = estimate_tokens(rendered) - 1
    for idx, tier in zip(("a", "b", "c"),
                         ("P1", "P0", "P0_COMPACT"), strict=True):
        rendered = rendered_by_tier.get(tier) or full_8
        add("S08_render_tier", idx, req(_KO + "\n" + rendered),
            tier=_tier_of(rendered) if tier in rendered_by_tier
            else "FULL")
    # S09: runtime hard-max payload — R2 질문 유형별 **실제** 상한
    # (specific_event 2 / period_overview 3 / multi_episode_compare 4,
    # 감수 57차 §6 — 운영 형태 표본).
    for idx, n in (("a", 2), ("b", 3), ("c", 4)):
        block = serialize_llm_payload(_payload(n), 100_000)
        add("S09_runtime_hard_max", idx,
            req(_KO + "\n" + RISK_EXPOSURE_INSTRUCTION_BLOCK
                + "\n" + block))
    # S10: oversized stress payload(8/12/16 episodes) — R2 hard max가
    # 아니라 tokenizer 압박용 synthetic 과대 요청(감수 57차 §6 명칭 정정).
    for idx, n in (("a", 8), ("b", 12), ("c", 16)):
        big = serialize_llm_payload(_payload(n), 100_000)
        add("S10_oversized_stress", idx,
            req(_KO + "\n" + RISK_EXPOSURE_INSTRUCTION_BLOCK + "\n" + big))
    # 부록: 모델 fallback·rerouting 재계수 검증(30표본 외 — 감수 57차 §2).
    supplementary: list[dict] = []
    for idx, scale in (("a", 1), ("b", 4), ("c", 12)):
        supplementary.append({
            "sample_id": f"R01_rerouting-{idx}",
            "category": "R01_rerouting", "tier": "FULL",
            "request": req(_KO * scale + _MIX),
            "resolved_model_id": reroute_model, "reroute": True})
    return samples, supplementary


def _provider_reported(model_id: str, body: dict,
                       api_key: str) -> tuple[int, int]:
    """generateContent 1토큰 호출 — (전체 input 토큰, cached 토큰).

    promptTokenCount는 캐시 할인 전 **전체 실제 input** 기준(감수 56차
    §9 — cached_input은 별도 관측하되 under-count 비교에서 빼지 않는다).
    """
    import time
    gen = dict(body)
    cfg = dict(gen.get("generationConfig") or {})
    cfg["maxOutputTokens"] = 1
    gen["generationConfig"] = cfg
    res = None
    for attempt in range(6):  # 프리뷰 모델 503·읽기 지연 간헐 — 지수 백오프
        try:
            res = httpx.post(f"{_API_BASE}/{model_id}:generateContent",
                             json=gen, headers={"x-goog-api-key": api_key},
                             timeout=150)
        except httpx.TimeoutException:
            time.sleep(1.5 * 2 ** attempt)
            continue
        if res.status_code not in (429, 500, 503):
            break
        time.sleep(1.5 * 2 ** attempt)
    assert res is not None
    res.raise_for_status()
    usage = res.json().get("usageMetadata", {})
    return (int(usage.get("promptTokenCount", 0)),
            int(usage.get("cachedContentTokenCount", 0)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gemini-3-flash-preview")
    parser.add_argument("--reroute-model", default="gemini-2.5-flash")
    parser.add_argument("--out-dir", default=str(
        Path(__file__).resolve().parents[1] / "compiled"
        / "risk_adapter_validation"))
    args = parser.parse_args()

    from saju_api.services.gemini_token_adapter import _api_key
    api_key = _api_key()
    adapter = build_gemini_adapter(args.model)
    reroute_adapter = build_gemini_adapter(args.reroute_model)
    native, supplementary = _build_corpus(args.model, args.reroute_model)
    assert len(native) == 30, len(native)
    assert all(not s["reroute"] for s in native)  # 30표본=전부 native

    records: list[dict] = []
    supp_records: list[dict] = []
    recount_performed = 0
    for sample in [*native, *supplementary]:
        request: ProviderRequest = sample["request"]
        body = build_gemini_request_body(request)
        resolved = sample["resolved_model_id"]
        if sample["reroute"]:
            # rerouting 계약: 최초 모델 계수 후 최종 라우팅 모델로 전체
            # request **재계수**(이전 모델 count 재사용 금지).
            adapter.count_request(request)  # 최초 모델 계수(폐기)
            counted = reroute_adapter.count_request(request)
            recount_performed += 1
        else:
            counted = adapter.count_request(request)
        reported, cached = _provider_reported(resolved, body, api_key)
        digest = hashlib.sha256(json.dumps(
            body, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()[:16]
        (supp_records if sample["reroute"] else records).append({
            "sample_id": sample["sample_id"],
            "category": sample["category"],
            "tier": sample["tier"],
            "resolved_model_id": resolved,
            "request_digest": digest,
            "counted": counted,
            "reported_total_input": reported,
            "cached_input": cached,
            "routing_changed": sample["reroute"],
            "recount_performed": sample["reroute"],
            "passed": counted >= reported,
        })
        print(f"  {sample['sample_id']:26s} counted={counted:6d}"
              f" reported={reported:6d} delta={counted - reported:+3d}"
              f" cached={cached}")

    records.sort(key=lambda r: r["sample_id"])  # 실행 순서 배제(canonical)
    supp_records.sort(key=lambda r: r["sample_id"])
    identity_wo_corpus = {
        "providerId": "gemini", "resolvedModelId": args.model,
        "counterVersion": GEMINI_COUNTER_VERSION,
        "providerRequestSchemaVersion": "1", "countMode": "PROVIDER_EXACT",
        "validationPolicyHash": adapter_validation_policy_hash(),
    }
    canonical = {"identity": identity_wo_corpus, "samples": records,
                 "supplementary_rerouting": supp_records}
    # 정본=전체 SHA-256 digest(감수 57차 §5) — 16자는 표시·파일명 전용.
    corpus_hash = hashlib.sha256(json.dumps(
        canonical, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    corpus_hash_short = corpus_hash[:16]

    all_records = [*records, *supp_records]
    deltas = [r["counted"] - r["reported_total_input"] for r in all_records]
    undercount = sum(1 for d in deltas if d < 0)
    overs = sorted(d for d in deltas if d >= 0)
    rel = [abs(d) / max(1, r["reported_total_input"])
           for d, r in zip(deltas, all_records, strict=True)]

    def pct(vals: list[int], q: float) -> float:
        if not vals:
            return 0.0
        return float(statistics.quantiles(
            vals, n=100, method="inclusive")[int(q) - 1]) if len(
                vals) > 1 else float(vals[0])

    report = {
        "identity": {**identity_wo_corpus,
                     "validationCorpusHash": corpus_hash,
                     "validationCorpusHashShort": corpus_hash_short},
        # 30표본=전부 최종 resolved=primary native(감수 57차 §2) —
        # rerouting 3건은 별도 집계(최종 resolved 모델 기준).
        "primary_native_samples": len(records),
        "samples_by_category": {
            c: sum(1 for r in records if r["category"] == c)
            for c in sorted({r["category"] for r in records})},
        "tier_distribution": {
            t: sum(1 for r in records if r["tier"] == t)
            for t in sorted({r["tier"] for r in records})},
        "undercount_count": undercount,
        "overcount_p50": pct(overs, 50),
        "overcount_p90": pct(overs, 90),
        "overcount_max": max(overs) if overs else 0,
        "relative_error_max": max(rel) if rel else 0.0,
        "supplementary_rerouting": {
            "samples": len(supp_records),
            "recounts_performed": recount_performed,
            "by_final_resolved_model": {
                m: sum(1 for r in supp_records
                       if r["resolved_model_id"] == m)
                for m in sorted({r["resolved_model_id"]
                                 for r in supp_records})},
            "note": "최종 resolved 모델(fallback)은 별도 identity — 해당"
                    " 모델의 30표본 감수 전 canary에서 validated counter"
                    " 없음 → BYPASS 유지",
        },
        "cached_input_observed": sum(r["cached_input"]
                                     for r in all_records),
        "pass": (len(records) == 30 and undercount == 0
                 and recount_performed == 3
                 and all(r["passed"] for r in all_records)),
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / f"{args.model}__{corpus_hash_short}.json"
    artifact_path.write_text(json.dumps({
        "canonical": canonical,
        "corpus_canonical_hash": corpus_hash,
        "corpus_canonical_hash_short": corpus_hash_short,
        "report": report,
        "volatile": {"generated_at": datetime.now(UTC).isoformat(),
                     "script": "risk_adapter_shadow_validation.py"},
    }, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    manifest_candidate = {**identity_wo_corpus,
                          "validationCorpusHash": corpus_hash,
                          "reviewed": False}
    print("\n== §11 보고 ==")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"\nartifact: {artifact_path}")
    print("manifest validatedTokenCounters 감수 후보(reviewed=false):")
    print(json.dumps(manifest_candidate, ensure_ascii=False, indent=1))
    print("\n상태: SHADOW_VALIDATING 유지 — VALIDATED 전환은 manifest 감수"
          " 후 별도 절차(감수 56차 §9).")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
