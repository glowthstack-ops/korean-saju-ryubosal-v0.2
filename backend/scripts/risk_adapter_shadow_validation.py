"""실물 token adapter shadow 계수 검증 harness(감수 56차 §9 + 62차 확대).

validation identity별 13형×3=39표본으로 counted_request_tokens(adapter
countTokens — **generateContent와 동일한 전체 request body**)와
provider_reported_total_input_tokens(generateContent usageMetadata.
promptTokenCount — cached+non-cached 전체, 청구 할인 전)를 전수 대조한다.
합격 기준(ADAPTER_VALIDATION_POLICY 선행 고정): undercount=0(shape별
검증 프레이밍 오버헤드 귀속 후) · request shape 누락=0 · model mismatch=0
· rerouting 후 recount 누락=0 · S13 cache-hit 3표본 적중.

2026-08-04 개정(B1 — 데굴님 확정):
- **S13 캐시 적중은 전체 합격의 하드 조건이 아니다.** Gemini 암묵 캐시는
  best-effort이며 동일 코드 3회 실행에서 1회만 적중했다(계수 정확도는
  3회 모두 undercount 0). 미적중=`cacheValidationStatus=NOT_OBSERVED` →
  `cache_path_validated=false`로 등록(런타임에서 cached_input>0이 나오면
  응답 폐기). 적중했는데 계수가 어긋난 경우에만 FAILED=불합격.
- **validationCorpusHash는 요청 본문 파생 항목에서만 산출**한다
  (identityCorpus). 실행 관측값을 identity에 넣으면 코드가 그대로여도
  매 실행 identity가 달라져 주간 재검증이 manifest 재감수를 유발했다.
- 외부 호출 전 운영 HMAC 키를 검증한다(dev 기본키면 즉시 종료).

감수 62차 추가:
- S13 cache-hit replay: 대형 공통 prefix(≥8,192tok) 워밍업 후 동일 body
  재호출 — cached_input>0 상태에서 promptTokenCount 일관성 검증
  (2026-08-04 B1로 불합격 조건에서 제외).
- shape별 validated_framing_overhead: 동일 shape 표본 간 고정 음수
  delta만 오버헤드로 귀속(가변이면 불합격). 범용 tolerance 금지.
- 응답 최상위 modelVersion 수집(표본 간 일치 필수) → **validation
  lease**(var/risk_state, HMAC 서명, 7일) 기록. artifact는 불변 정적
  identity만 보관.

**승격 없음**: 본 스크립트는 SHADOW_VALIDATING 상태로 계측·artifact 생성·
manifest 감수 후보 출력까지만 한다 — VALIDATED 전환은 manifest 감수
(reviewed entry) + 유효 lease 이후 startup 파생으로만.

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
    RiskPromptBlock,
    wrap_risk_block,
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
# identity corpus에 참여하는 표본 필드 — 전부 요청 본문에서 파생된다.
# 실행 시점 관측값(counted/reported_total_input/cached_input/passed 등)은
# 여기 넣지 않는다(2026-08-04 승인 조건 ⑦).
_IDENTITY_SAMPLE_FIELDS = ("sample_id", "category", "tier",
                           "resolved_model_id", "attempt_kind",
                           "request_digest", "request_shape_digest")

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
        # attempt shape 라벨(감수 60차 §5): S11/S12는 재작성·재생성
        # attempt 구조, 나머지는 INITIAL 계열 구조로 대조된다.
        attempt_kind = {"S11_revision_attempt": "REVISION_1",
                        "S12_regenerate_attempt":
                            "REGENERATE_WITHOUT_RISK"}.get(cat, "INITIAL")
        samples.append({
            "sample_id": f"{cat}-{idx}", "category": cat, "tier": tier,
            "request": request, "resolved_model_id": resolved or model_id,
            "attempt_kind": attempt_kind, "reroute": reroute})

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
    # 실서비스 INITIAL과 동일 구조: instruction+**wrapped block**(BEGIN/
    # END marker)+**transport output schema**(P1 교정 — 실요청과 동일한
    # message 구조가 corpus에 있어야 shape 대조가 성립).
    def _wrapped(serialized: str) -> str:
        return wrap_risk_block(RiskPromptBlock(
            serialized_text=serialized,
            content_hash=hashlib.sha256(
                serialized.encode()).hexdigest()[:16],
            compression_mode="FULL",
            exact_token_count=max(1, len(serialized) // 4)))

    for idx, block in (("a", full_1), ("b", full_8), ("c", full_1)):
        add("S07_injected_instruction", idx,
            req(_KO + "\n" + RISK_EXPOSURE_INSTRUCTION_BLOCK
                + "\n" + _wrapped(block), schema=out_schema))
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
                + "\n" + _wrapped(block), schema=out_schema))
    # S10: oversized stress payload(8/12/16 episodes) — R2 hard max가
    # 아니라 tokenizer 압박용 synthetic 과대 요청(감수 57차 §6 명칭 정정).
    for idx, n in (("a", 8), ("b", 12), ("c", 16)):
        big = serialize_llm_payload(_payload(n), 100_000)
        add("S10_oversized_stress", idx,
            req(_KO + "\n" + RISK_EXPOSURE_INSTRUCTION_BLOCK + "\n"
                + _wrapped(big), schema=out_schema))
    # S11: REVISION_1 attempt(감수 60차 §5) — 원 요청(instruction+block)
    # +위반 요약+원 초안이 추가된 실제 재작성 message 구조.
    from saju_api.services.risk_llm_pipeline import (
        build_regenerate_request,
        build_revision_request,
    )
    for idx, draft_scale in (("a", 1), ("b", 3), ("c", 8)):
        base_req = req(_KO + "\n" + RISK_EXPOSURE_INSTRUCTION_BLOCK
                       + "\n" + _wrapped(full_1), schema=out_schema)
        revision = build_revision_request(
            base_req,
            draft="관련 조건을 점검해 두면 좋은 시기입니다. " * draft_scale,
            violation_codes=["prohibited_phrase"],
            missing_required_refs=["rg1"],
            required_qualifier_kinds=["uncertainty"],
            allowed_levels=["warning"])
        add("S11_revision_attempt", idx, revision)
    # S12: REGENERATE_WITHOUT_RISK attempt(감수 60차 §5) — baseline+
    # suppressed guard의 실제 재생성 message 구조.
    for idx, scale in (("a", 1), ("b", 4), ("c", 12)):
        add("S12_regenerate_attempt", idx,
            build_regenerate_request(req(_KO * scale)))
    # S13: cache-hit replay(감수 62차) — 실서비스 INITIAL_INJECTED 구조의
    # 대형 공통 prefix(≥8,192tok) 표본. 워밍업(최초 호출)은 main()이
    # 수행하고, 재호출에서 cached_input>0 상태의 promptTokenCount
    # 일관성을 검증한다. 표본 간 prefix는 동일(적중 극대화), 접미만 상이.
    cache_prefix = _KO * 175  # 한글 ≈1자/token — 정책 하한(8,192tok) 상회 보장
    for idx in ("a", "b", "c"):
        add("S13_cache_hit_replay", idx,
            req(cache_prefix + "\n" + RISK_EXPOSURE_INSTRUCTION_BLOCK
                + "\n" + _wrapped(full_1)
                + f"\n[cache-replay-{idx}]", schema=out_schema))
    # 부록: 모델 fallback·rerouting 재계수 검증(39표본 외 — 감수 57차 §2).
    supplementary: list[dict] = []
    for idx, scale in (("a", 1), ("b", 4), ("c", 12)):
        supplementary.append({
            "sample_id": f"R01_rerouting-{idx}",
            "category": "R01_rerouting", "tier": "FULL",
            "request": req(_KO * scale + _MIX),
            "resolved_model_id": reroute_model,
            "attempt_kind": "INITIAL", "reroute": True})
    return samples, supplementary


def _provider_reported(model_id: str, body: dict,
                       api_key: str) -> tuple[int, int, str]:
    """generateContent 1토큰 호출 — (전체 input 토큰, cached 토큰,
    응답 최상위 modelVersion).

    promptTokenCount는 캐시 할인 전 **전체 실제 input** 기준(감수 56차
    §9 — cached_input은 별도 관측하되 under-count 비교에서 빼지 않는다).
    modelVersion은 usageMetadata가 아니라 응답 최상위 필드(감수 62차).
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
    data = res.json()
    usage = data.get("usageMetadata", {})
    return (int(usage.get("promptTokenCount", 0)),
            int(usage.get("cachedContentTokenCount", 0)),
            str(data.get("modelVersion", "")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gemini-3-flash-preview")
    parser.add_argument("--reroute-model", default="gemini-2.5-flash")
    parser.add_argument("--out-dir", default=str(
        Path(__file__).resolve().parents[1] / "compiled"
        / "risk_adapter_validation"))
    # 결정성 반복 검증(manifest 재감수 전 조건 ⑥)에서는 운영 lease를
    # 건드리지 않는다 — artifact는 --out-dir로, lease는 이 플래그로 격리.
    parser.add_argument("--no-lease", action="store_true",
                        help="합격해도 운영 lease를 기록하지 않는다"
                             "(결정성 반복 검증용)")
    args = parser.parse_args()

    # 외부 호출 **전** HMAC 키 검증(2026-08-04 승인 조건 ②): dev 기본키로
    # 서명한 lease는 서버가 서명 불일치로 거부한다. 실제로 .env만 로드한
    # 채 39표본을 돌려 통과시켰으나 lease를 쓸 수 없었던 사고가 있었다
    # (2026-08-04). 판정 기준은 런타임과 동일 SSOT를 쓴다.
    from saju_api.services.risk_exposure_service import _audit_hmac_key_valid
    if not _audit_hmac_key_valid():
        print("[중단] RISK_AUDIT_HMAC_KEY_B64 미설정/비정상 — dev 기본키로"
              " 서명한 lease는 서버가 거부한다(외부 호출 전 종료).\n"
              "       ./scripts/revalidate_risk_lease.sh 로 실행할 것"
              "(.env + .env.risk 를 서버와 동일하게 로드한다).",
              file=sys.stderr)
        return 2

    from saju_api.services.gemini_token_adapter import _api_key
    api_key = _api_key()
    adapter = build_gemini_adapter(args.model)
    reroute_adapter = build_gemini_adapter(args.reroute_model)
    native, supplementary = _build_corpus(args.model, args.reroute_model)
    assert len(native) == 39, len(native)  # 13형×3(감수 62차 S13 추가)
    assert all(not s["reroute"] for s in native)  # native=전부 primary

    import time as _time

    records: list[dict] = []
    supp_records: list[dict] = []
    recount_performed = 0
    model_versions: set[str] = set()
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
        warmup_reported = None
        if sample["category"] == "S13_cache_hit_replay":
            # S13(감수 62차): 최초(non-cache) 호출 보존 후 동일 body
            # 재호출 — cached_input>0 적중까지 재시도 5회(미적중=불합격).
            warmup_reported, _wc, wmv = _provider_reported(
                resolved, body, api_key)
            if wmv:
                model_versions.add(wmv)
            reported, cached, mv = 0, 0, ""
            for _retry in range(5):
                _time.sleep(2.0)
                reported, cached, mv = _provider_reported(
                    resolved, body, api_key)
                if cached > 0:
                    break
        else:
            reported, cached, mv = _provider_reported(
                resolved, body, api_key)
        if mv and not sample["reroute"]:
            model_versions.add(mv)
        digest = hashlib.sha256(json.dumps(
            body, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()[:16]
        from saju_api.services.risk_llm_pipeline import (
            request_shape_digest,
        )
        shape_digest = request_shape_digest(
            sample["attempt_kind"], request, "1")
        record = {
            "sample_id": sample["sample_id"],
            "category": sample["category"],
            "tier": sample["tier"],
            "resolved_model_id": resolved,
            "attempt_kind": sample["attempt_kind"],
            "request_digest": digest,
            "request_shape_digest": shape_digest,
            "counted": counted,
            "reported_total_input": reported,
            "cached_input": cached,
            "routing_changed": sample["reroute"],
            "recount_performed": sample["reroute"],
            "passed": counted >= reported,
        }
        if warmup_reported is not None:
            record["warmup_reported_total_input"] = warmup_reported
            # B1(2026-08-04 데굴님 확정): 캐시 적중은 provider best-effort
            # 이므로 계수기 전체 합격의 하드 조건에서 분리한다 — 미적중은
            # 불합격이 아니라 NOT_OBSERVED(캐시 capability 미검증).
            # 적중했는데 계수가 어긋난 경우에만 FAILED로 불합격.
            record["cache_hit_achieved"] = cached > 0
        (supp_records if sample["reroute"] else records).append(record)
        print(f"  {sample['sample_id']:26s} counted={counted:6d}"
              f" reported={reported:6d} delta={counted - reported:+3d}"
              f" cached={cached} mv={mv or '-'}")

    records.sort(key=lambda r: r["sample_id"])  # 실행 순서 배제(canonical)
    supp_records.sort(key=lambda r: r["sample_id"])

    # shape별 프레이밍 오버헤드 귀속(감수 62차 framing_overhead_policy):
    # 동일 shape 표본의 음수 delta(reported-counted)가 **단일 고정값**일
    # 때만 validated_framing_overhead로 인정. 가변이면 불합격.
    overhead_by_shape: dict[str, int] = {}
    overhead_consistent = True
    for shape_d in {r["request_shape_digest"] for r in records}:
        group = [r for r in records
                 if r["request_shape_digest"] == shape_d]
        deficits = sorted({r["reported_total_input"] - r["counted"]
                           for r in group
                           if r["counted"] < r["reported_total_input"]})
        if not deficits:
            overhead_by_shape[shape_d] = 0
        elif len(deficits) == 1:
            overhead_by_shape[shape_d] = int(deficits[0])
        else:
            overhead_consistent = False  # 가변 음수 delta — 고정 아님
            overhead_by_shape[shape_d] = int(max(deficits))
    for r in records:
        oh = overhead_by_shape.get(r["request_shape_digest"], 0)
        r["validated_framing_overhead"] = oh
        # 합격 = 계수 계약(undercount 없음)만. 캐시 적중 여부는 별도 축
        # (cacheValidationStatus)으로 뺀다 — B1.
        r["passed"] = bool(r["counted"] + oh >= r["reported_total_input"])

    # 캐시 capability 검증(계수기 검증과 독립):
    #   VALIDATED    3표본 전부 적중 + 적중 표본의 계수 계약 충족
    #   NOT_OBSERVED 적중이 한 건도 관측되지 않음(= 미검증, 불합격 아님)
    #   FAILED       적중했는데 계수가 어긋남(= 실제 결함)
    s13_records = [r for r in records
                   if r["category"] == "S13_cache_hit_replay"]
    cache_observed = [r for r in s13_records if r.get("cache_hit_achieved")]
    if not cache_observed:
        cache_validation_status = "NOT_OBSERVED"
    elif not all(r["passed"] for r in cache_observed):
        cache_validation_status = "FAILED"
    elif len(cache_observed) == len(s13_records):
        cache_validation_status = "VALIDATED"
    else:
        cache_validation_status = "NOT_OBSERVED"  # 부분 적중=미검증
    identity_wo_corpus = {
        "providerId": "gemini", "resolvedModelId": args.model,
        "counterVersion": GEMINI_COUNTER_VERSION,
        "providerRequestSchemaVersion": "1", "countMode": "PROVIDER_EXACT",
        "validationPolicyHash": adapter_validation_policy_hash(),
    }

    def _digest(obj: object) -> str:
        return hashlib.sha256(json.dumps(
            obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    # 3층 hash 분리(감수 58차 §2): validation identity는 **해당 모델의
    # qualifying corpus(native 30)에만** 결속 — fallback 부록이 바뀌어도
    # primary identity가 변하지 않는다.
    native_corpus = {"identity": identity_wo_corpus, "samples": records}
    # identity corpus(2026-08-04 데굴님 승인 조건 ⑦): **요청 본문에서
    # 파생되는 항목만** identity에 참여한다. 실행 시점 관측값(counted·
    # reported·cached_input 등)을 넣으면 코드가 그대로여도 매 실행 identity
    # 가 달라져 "주간 재검증=lease만 갱신"이 성립하지 않는다(실측 확인:
    # 동일 코드 3회 실행에서 cached_input만 달라져 corpus hash 3종 발생).
    # 관측값은 artifact의 nativeValidationCorpus에 전량 보존된다.
    identity_corpus = {
        "identity": identity_wo_corpus,
        "samples": [{k: r[k] for k in _IDENTITY_SAMPLE_FIELDS}
                    for r in records],
    }
    corpus_hash = _digest(identity_corpus)  # validationCorpusHash(정본)
    corpus_hash_short = corpus_hash[:16]
    supplementary_evidence = {"samples": supp_records}
    supplementary_hash = _digest(supplementary_evidence)

    all_records = [*records, *supp_records]
    # undercount는 shape별 검증 오버헤드 귀속 **후** 기준(감수 62차) —
    # rerouting 부록은 오버헤드 미적용(별도 identity 대상).
    deltas = []
    for r in all_records:
        oh = (overhead_by_shape.get(r["request_shape_digest"], 0)
              if not r["routing_changed"] else 0)
        deltas.append(r["counted"] + oh - r["reported_total_input"])
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

    def _shape_name(r: dict) -> str:
        """digest에 사람이 읽을 수 있는 안정적 shape 이름 결속(감수 61차
        §5) — hash만 저장하면 어떤 구조가 빠졌는지 검토 불가."""
        if r["attempt_kind"] == "REVISION_1":
            return "REVISION_1_INJECTED"
        if r["attempt_kind"] == "REGENERATE_WITHOUT_RISK":
            return "REGENERATE_WITHOUT_RISK"
        cat = r["category"]
        if cat in ("S07_injected_instruction", "S09_runtime_hard_max",
                   "S10_oversized_stress"):
            return "INITIAL_INJECTED"
        if cat == "S06_suppressed_guard":
            return "SUPPRESSED"
        if cat == "S04_tool_schema":
            return "BYPASS_TOOL_SCHEMA"
        if cat == "S05_output_schema":
            return "BYPASS_OUTPUT_SCHEMA"
        return "BYPASS_PLAIN"

    shape_names: dict[str, str] = {}
    for r in records:
        shape_names.setdefault(r["request_shape_digest"], _shape_name(r))
    # validated_shapes(감수 62차 P0⑦): 단일 artifact 안에 shape별 검증
    # 항목 — runtime required shape ⊆ 이 집합이어야 해당 call_type 주입.
    reviewed_shapes: list[dict] = []
    for d in sorted(shape_names):
        group = [r for r in records if r["request_shape_digest"] == d]
        reviewed_shapes.append({
            "name": shape_names[d], "digest": d,
            "validated_framing_overhead": overhead_by_shape.get(d, 0),
            "non_cache_samples": sum(1 for r in group
                                     if r["cached_input"] == 0),
            "cache_hit_samples": sum(1 for r in group
                                     if r["cached_input"] > 0),
        })
    required_shape_set_hash = _digest(sorted(shape_names))
    # transport 변환 규칙 digest(감수 58차 §5): schema version을 올리지
    # 않은 채 transport shape가 바뀌는 실수를 탐지하는 대조값.
    canonical_schema = build_risk_output_schema(
        _payload(1)["llmRiskEpisodes"], hard_max=3)
    canonical_schema_hash = _digest(canonical_schema)
    transport_schema_hash = _digest(
        build_gemini_transport_schema(canonical_schema))
    report = {
        "identity": {**identity_wo_corpus,
                     "validationCorpusHash": corpus_hash,
                     "validationCorpusHashShort": corpus_hash_short},
        "supplementaryReroutingHash": supplementary_hash,
        "canonicalOutputSchemaHash": canonical_schema_hash,
        "geminiTransportSchemaHash": transport_schema_hash,
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
        "reviewed_request_shapes": {str(s["name"]): str(s["digest"])[:16]
                                    for s in reviewed_shapes},
        # 감수 62차 확대 필드 — 정적 identity(artifact)·검증 요약.
        "staticIdentity": {
            "configured_model": args.model,
            "api_endpoint": _API_BASE,
            "api_version": "v1beta",
            "sdk_version": f"httpx-{httpx.__version__}",
            "serializer_version": "1",
            "adapter_policy_hash": adapter_validation_policy_hash(),
            "required_shape_set_hash": required_shape_set_hash,
        },
        "framingOverheadConsistent": overhead_consistent,
        # 캐시 경로 검증 결과(B1) — adapter 등록 시 cache_path_validated로
        # 그대로 전달된다. VALIDATED가 아니면 false로 등록되고, 런타임에서
        # cached_input>0이 관측되면 응답을 폐기한다(CACHE_PATH_UNVALIDATED).
        "cacheValidationStatus": cache_validation_status,
        "cacheSamplesValidated": cache_validation_status == "VALIDATED",
        "cacheHitSamplesObserved": len(cache_observed),
        "modelVersionsObserved": sorted(model_versions),
        "modelVersionConsistent": len(model_versions) == 1,
        # 전체 합격 = 계수기 검증만(B1). 캐시는 FAILED(적중했는데 계수
        # 불일치)일 때만 불합격 사유가 되고, NOT_OBSERVED는 합격을 막지
        # 않는다 — 미검증 상태로 등록될 뿐이다.
        "pass": (len(records) == 39 and undercount == 0
                 and overhead_consistent
                 and recount_performed == 3
                 and len(model_versions) == 1
                 and cache_validation_status != "FAILED"
                 and all(r["passed"] for r in all_records)),
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / f"{args.model}__{corpus_hash_short}.json"
    artifact_body = {
        # native corpus(실행 관측값 전량 보존 — 증거)와 rerouting 부록·
        # 메타데이터를 분리 보관(감수 58차 §2).
        "nativeValidationCorpus": native_corpus,
        # identityCorpus = validationCorpusHash의 유일한 입력(요청 본문
        # 파생 항목만). runtime의 _artifact_corpus_ok가 이 필드를 재해시해
        # 대조한다(필드 부재=구 schema로 간주하고 native 재해시로 폴백).
        "identityCorpus": identity_corpus,
        "validationCorpusHash": corpus_hash,
        "validationCorpusHashShort": corpus_hash_short,
        "supplementaryReroutingEvidence": supplementary_evidence,
        "supplementaryReroutingHash": supplementary_hash,
        # 실제 attempt shape 대조 집합(감수 60차 §5 — native 표본의
        # 구조적 digest만): preflight의 REQUEST_SHAPE_NOT_REVIEWED 기준.
        "reviewedRequestShapeDigests": reviewed_shapes,
        "report": report,
        "volatile": {"generated_at": datetime.now(UTC).isoformat(),
                     "script": "risk_adapter_shadow_validation.py"},
    }
    artifact_body["validationArtifactHash"] = _digest(
        {k: v for k, v in artifact_body.items() if k != "volatile"})
    artifact_path.write_text(json.dumps(
        artifact_body, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8")

    manifest_candidate = {**identity_wo_corpus,
                          "validationCorpusHash": corpus_hash,
                          "reviewed": False}
    # validation lease 기록(감수 62차 P1 — artifact/운영 lease 분리):
    # 합격 시에만. 실제 reported modelVersion·만료(7일)를 lease에 담고
    # artifact는 불변으로 유지한다(주간 재검증=lease만 갱신).
    if report["pass"] and args.no_lease:
        print("\nvalidation lease: 기록 생략(--no-lease) — 운영 lease 무변경")
    elif report["pass"]:
        from saju_api.services.risk_validation_lease import write_lease
        from saju_api.services.token_counter_registry import (
            adapter_identity_hash,
        )
        final_adapter = build_gemini_adapter(
            args.model, corpus_hash,
            cache_path_validated=bool(report["cacheSamplesValidated"]),
            framing_overhead_by_shape=tuple(
                (str(s["digest"]), int(str(s["validated_framing_overhead"])))
                for s in reviewed_shapes))
        lease_file = write_lease(
            model_id=args.model,
            identity_hash=adapter_identity_hash(final_adapter),
            reported_model_version=next(iter(model_versions)),
            samples_summary={
                "native_samples": len(records),
                "undercount": undercount,
                # 실제 적중 표본 수(구 구현은 S13 표본 수 3을 그대로 세어
                # 미적중에도 3이 기록됐다 — B1에서 교정).
                "cache_hit_samples": len(cache_observed),
                "cache_validation_status": cache_validation_status,
            })
        print(f"\nvalidation lease: {lease_file}")
    print(f"\n캐시 경로 검증: {cache_validation_status}"
          f" (적중 {len(cache_observed)}/{len(s13_records)})"
          f" → cache_path_validated="
          f"{str(report['cacheSamplesValidated']).lower()}")
    print("\n== §11 보고 ==")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"\nartifact: {artifact_path}")
    print("manifest validatedTokenCounters 감수 후보(reviewed=false):")
    print(json.dumps(manifest_candidate, ensure_ascii=False, indent=1))
    print("\n상태: SHADOW_VALIDATING 유지 — VALIDATED 전환은 manifest 감수"
          " + 유효 lease 후 startup 파생으로만(감수 56차 §9 + 62차).")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
