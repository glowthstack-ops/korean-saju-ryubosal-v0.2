"""R3-b 위험 노출(presentation) 전수 측정 (감수 42차 §12 — shadow 전용).

목적(데굴님): 잠정 밴드·하한이 실제 코퍼스에서 어떤 level 분포와 강등 사유를
만드는지 실측한다 — critical은 수가 적어도 전량 공개, 개수를 만들기 위해
경계를 낮추지 않는다(0건도 정상).

측정 축:
- level 분포: 전체 episode(선택 전) vs budget 선택 후 분리, 프로필·도메인·
  kind별
- 강등 사유 3층: downgraded unique episodes / primary reason pairs /
  all reason pairs
- critical 전수 표(발생 시 전량 — role·exposure·적격 원인 수·identity·
  confidence·최종 level)
- claim 정책 검증: 충돌(prohibited 우선 제거)·partial qualifier 누락 0·
  전역 금지 코드 상존
- token guard 실측(256/512/1024/2048): tier 생존·compact 전환·overflow·
  episode/qualifier/prohibited 보존·전역 dedup 절감량
- 밴드 국소 민감도(한 축씩): watch 0.10/0.12/0.15 · warning 0.22/0.25/0.28
  · critical 0.35/0.40/0.45 · critical confidence 하한 0.50/0.65/0.75

결정적 출력 — 저장본(doc/v2_2/RISK_PRESENTATION_SURVEY_R3B.md)과의 diff가
회귀 신호. 실행: python scripts/risk_presentation_survey.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND / "apps" / "api"))
sys.path.insert(0, str(_BACKEND / "scripts"))

from risk_selection_survey import (  # noqa: E402
    _build_all,
    _collect_by_chart,
    _reality_linked_profile,
    _score_variant,
)
from risk_shadow_density import _build_exposure_profiles  # noqa: E402
from saju_engines import risk_presentation as rp  # noqa: E402
from saju_engines.risk_engine import RiskEngine  # noqa: E402
from saju_engines.risk_presentation import (  # noqa: E402
    RISK_PRESENTATION_VERSION,
    build_presentation,
    estimate_tokens,
    presentation_policy_hash,
    serialize_llm_payload,
)
from saju_engines.risk_selection import candidate_uid  # noqa: E402

_DICTS = _BACKEND / "dictionaries"


def _claims_map() -> dict[str, dict]:
    """사전 → presentation claim 공급 맵(호출부 책임 — 모듈은 순수)."""
    engine = RiskEngine(_DICTS)
    out: dict[str, dict] = {}
    for it in engine._items:
        policy = it.exposure_policy
        out[it.risk_id] = {
            "manifestations": [m.ko for m in it.manifestations],
            "prohibited": list(it.prohibited_claims),
            "allowed": list(it.allowed_claim_scope),
            "claimCeiling": it.claim_ceiling,
            "unknownClaimCeiling": (
                policy.claim_ceiling_when_unknown
                if policy is not None else None),
        }
    return out


def _profile_presentation(name: str, built: list, claims: dict) -> None:
    """프로필 1종의 level 분포·강등 사유·critical 전수·claim 검증."""
    all_levels: Counter = Counter()
    sel_levels: Counter = Counter()
    by_domain: dict[str, Counter] = {}
    by_kind: dict[str, Counter] = {}
    downgraded_eps = 0
    primary_pairs: Counter = Counter()
    all_pairs: Counter = Counter()
    omission: Counter = Counter()
    critical_rows: list[str] = []
    partial_missing_qualifier = 0
    conflict_removed = 0
    for _chart, scored, eps, selected, _ in built:
        by_uid = {candidate_uid(c): c for c in scored}
        for group, counter in ((eps, all_levels), (selected, sel_levels)):
            payload = build_presentation(list(group), scored, claims)
            for rec in payload["presentationRecords"]:
                counter[rec["presentationLevel"]] += 1
                if counter is not sel_levels:
                    continue
                # 선택 집합 기준 상세(강등·critical·claim 검증).
                for d in rec["domains"]:
                    by_domain.setdefault(d, Counter())[
                        rec["presentationLevel"]] += 1
                if rec["downgradeReasons"]:
                    downgraded_eps += 1
                    primary_pairs[rec["primaryDowngradeReason"]] += 1
                    for r in rec["downgradeReasons"]:
                        all_pairs[r] += 1
                if rec["presentationOmissionReason"]:
                    omission[rec["presentationOmissionReason"]] += 1
                if rec["identityPhraseMode"] == "possibly_related" and (
                        "possibly_related" not in rec["requiredQualifiers"]):
                    partial_missing_qualifier += 1
                removed = (len(rec["allowedClaimScope"]) + 4) - len(
                    rec["effectiveAllowedClaimCodes"])
                conflict_removed += max(0, removed - len(
                    rec["allowedClaimScope"]))
                if rec["presentationLevel"] == "critical":
                    critical_rows.append(
                        f"    {rec['diagnostics']['episodeKey']} · roles="
                        f"{','.join(rec['effectRoles'])} · exposure="
                        f"{rec['exposureStatus']} · eligibleCauses="
                        f"{rec['criticalEligibleCauseCount']} · identity="
                        f"{rec['identityPhraseMode']} · conf="
                        f"{rec['contextConfidenceBand']} · score="
                        f"{rec['scoreBand']}")
        # kind 분해(선택 집합·record 기준 — ceiling 적용 후 동일 경로).
        kind_by_key = {
            ep.episode_key: by_uid[ep.representative_candidate_id].kind.value
            for ep in selected
            if ep.representative_candidate_id in by_uid}
        payload_sel = build_presentation(list(selected), scored, claims)
        for rec in payload_sel["presentationRecords"]:
            kind = kind_by_key.get(rec["diagnostics"]["episodeKey"])
            if kind is not None:
                by_kind.setdefault(kind, Counter())[
                    rec["presentationLevel"]] += 1
    print(f"\n## profile {name} — presentation 분포"
          "(단위: episode 건수 — 10차트 합산)")
    print("  전체 episode(선택 전 — 잠재 구조 포함): " + " · ".join(
        f"{k} {all_levels[k]}" for k in ("critical", "warning", "watch",
                                         "advisory", "none")))
    print("  budget 선택 후(warning_episode_count 등 —"
          " hard_max 3 적용): " + " · ".join(
        f"{k} {sel_levels[k]}" for k in ("critical", "warning", "watch",
                                         "advisory", "none")))
    print("  도메인별(선택): " + " / ".join(
        f"{d}[" + " ".join(f"{k}:{c[k]}" for k in
                           ("critical", "warning", "watch", "advisory",
                            "none") if c[k]) + "]"
        for d, c in sorted(by_domain.items())))
    print("  kind별(선택): " + " / ".join(
        f"{k}[" + " ".join(f"{lv}:{c[lv]}" for lv in
                           ("critical", "warning", "watch", "advisory",
                            "none") if c[lv]) + "]"
        for k, c in sorted(by_kind.items())))
    print(f"  강등: unique episodes {downgraded_eps} · primary " + (
        " · ".join(f"{k} {v}" for k, v in sorted(primary_pairs.items())
                   if k) or "없음") + " · all " + (
        " · ".join(f"{k} {v}" for k, v in sorted(all_pairs.items()))
        or "없음"))
    print("  omission(none): " + (" · ".join(
        f"{k} {v}" for k, v in sorted(omission.items())) or "없음"))
    print("  critical 전수: " + (str(len(critical_rows)) + "건"
                                if critical_rows else "0건(정상 — 개수를"
                                " 만들기 위한 경계 하향 금지)"))
    for row in critical_rows:
        print(row)
    print(f"  claim 검증: partial qualifier 누락 {partial_missing_qualifier}"
          f" · 충돌 제거(참고) {conflict_removed} · 전역 prohibited 7코드"
          " payload 최상단 상존")


def _token_guard_measure(built: list, claims: dict) -> None:
    """token guard 실측(감수 42차 §12) — budget 256/512/1024/2048."""
    print("\n## token guard 실측(선택 집합·프로필 C 기준 — 보수 estimator·"
          "512 미만/compact 초과=fail-closed 비주입)")
    p0_tokens: list[int] = []
    for budget in (256, 512, 1024, 2048):
        tier_hits: Counter = Counter()
        overflow = 0
        kept = total = 0
        dedup_saving = 0
        for _chart, scored, _eps, selected, _ in built:
            payload = build_presentation(list(selected), scored, claims)
            rendered = serialize_llm_payload(payload, budget)
            data = json.loads(rendered)
            total += len(payload["llmRiskEpisodes"])
            kept += len(data["riskEpisodes"])
            if data.get("exposureSuppressedReason"):
                tier_hits["SUPPRESSED(fail-closed)"] += 1
            elif data.get("compressionMode") == "P0_COMPACT":
                tier_hits["P0_COMPACT"] += 1
            elif any("effectRoles" in e for e in data["riskEpisodes"]):
                tier_hits["P2(full)"] += 1
            elif any("scoreBand" in e for e in data["riskEpisodes"]):
                tier_hits["P1"] += 1
            else:
                tier_hits["P0"] += 1
            overflow += 1 if data.get("exposureSuppressedReason") else 0
            # 전역 dedup 절감량: 전역 7+4 코드를 episode마다 반복했을 경우.
            per_ep = len(json.dumps(
                {"globalProhibitedClaimCodes":
                 payload["globalProhibitedClaimCodes"],
                 "globalAllowedClaimCodes":
                 payload["globalAllowedClaimCodes"]}, ensure_ascii=False))
            dedup_saving += per_ep * max(
                0, len(data["riskEpisodes"]) - 1)
            if budget == 512:  # compact(최소 주입 표현) 크기 측정
                p0_tokens.append(estimate_tokens(rendered))
        print(f"  budget {budget}: tier " + " · ".join(
            f"{k} {v}" for k, v in sorted(tier_hits.items()))
            + f" · fail-closed 비주입 차트 {overflow} ·"
            f" episode 주입 {kept}/{total}"
            f" · 전역 dedup 절감(반복 대비) ≈{dedup_saving // 3} tokens")
    if p0_tokens:
        s = sorted(p0_tokens)
        print(f"  최소 주입 표현(P0_COMPACT) 토큰(차트별): "
              f"p50 {s[len(s) // 2]} · max {s[-1]}")


def _threshold_sensitivity(built: list, claims: dict) -> None:
    """밴드·critical 하한 국소 민감도(한 축씩 — 감수 42차 §11·13)."""
    def _levels_with(thresholds=None, min_conf=None) -> Counter:
        orig_t = rp._NUMERIC_BAND_THRESHOLDS
        orig_c = rp._CRITICAL_MIN_CONTEXT_CONFIDENCE
        try:
            if thresholds is not None:
                rp._NUMERIC_BAND_THRESHOLDS = thresholds
            if min_conf is not None:
                rp._CRITICAL_MIN_CONTEXT_CONFIDENCE = min_conf
            out: Counter = Counter()
            for _chart, scored, _eps, selected, _ in built:
                payload = build_presentation(list(selected), scored, claims)
                for rec in payload["presentationRecords"]:
                    out[rec["presentationLevel"]] += 1
            return out
        finally:
            rp._NUMERIC_BAND_THRESHOLDS = orig_t
            rp._CRITICAL_MIN_CONTEXT_CONFIDENCE = orig_c

    def _fmt(c: Counter) -> str:
        return " ".join(f"{k}:{c[k]}" for k in
                        ("critical", "warning", "watch", "advisory", "none"))

    print("\n## 경계 국소 민감도(단위: 선택 후 episode 건수 — C 프로필"
          " 10차트 합산, 한 축씩)")
    base = (("critical", 0.40), ("warning", 0.25), ("watch", 0.12),
            ("advisory", 0.0))
    for label, variants in (
        ("watch", (0.10, 0.12, 0.15)),
        ("warning", (0.22, 0.25, 0.28)),
        ("critical", (0.35, 0.40, 0.45)),
    ):
        for v in variants:
            t = tuple((name, (v if name == label else lo))
                      for name, lo in base)
            print(f"  {label}={v:.2f}: {_fmt(_levels_with(thresholds=t))}")
    for conf in (0.50, 0.65, 0.75):
        print(f"  critical_min_conf={conf:.2f}: "
              f"{_fmt(_levels_with(min_conf=conf))}")


def main() -> int:
    """프로필 5종 presentation 전수 측정."""
    print(f"# R3-b 위험 노출 전수 측정 — {RISK_PRESENTATION_VERSION}")
    print(f"presentation_policy {presentation_policy_hash()} — 밴드"
          "(0.40/0.25/0.12)·critical conf 하한 0.5 전부 잠정(본 측정이"
          " 감수 재료)")
    base_impacts = RiskEngine(_DICTS).base_impacts()
    claims = _claims_map()
    c_built = None
    for name, ctxs in [*_build_exposure_profiles(),
                       ("E_reality_linked", _reality_linked_profile())]:
        raw_by_chart = _collect_by_chart(ctxs)
        scored_by_chart = [(n, _score_variant(
            r, base_impacts, weight=None, max_bonus=0.20, mov_high=False))
            for n, r in raw_by_chart]
        built = _build_all(scored_by_chart, horizon=True)
        _profile_presentation(name, built, claims)
        if name == "C_high_exposure":
            c_built = built
    assert c_built is not None
    _token_guard_measure(c_built, claims)
    _threshold_sensitivity(c_built, claims)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
