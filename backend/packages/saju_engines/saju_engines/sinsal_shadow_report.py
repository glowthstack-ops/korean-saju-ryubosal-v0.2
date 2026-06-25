"""신살 numeric shadow 리포트 빌더 — 순수 함수(검증 도구, 운영 미연결).

Phase B-1: 신살 numeric sidecar(`sinsal_numeric_scoring`)를 골든 차트 × 대표 기간에 일괄 산출해
legacy 대비 관측 리포트한다. **score/polarity 불변** — 산출물(리포트)만 만든다. 용신 operational
`shadow_report.py`와 분리(독립). 규격: SINSAL_MODIFIER_SPEC §10-1.
"""

from __future__ import annotations

from saju_shared_types.events import EventCandidate
from saju_shared_types.manse_result import ManseV2Result

from . import sinsal_modifier_config as cfg
from .sinsal_numeric_scoring import apply_sinsal_channel_shadow

# CSV 헤더·JSON 키 공통(고정 순서). BirthInput 원본 PII 미포함(chart_id만).
# occurrence_score_delta 는 항상 0(발생 가능성 불변) — 컬럼으로 명시해 검증 가시화.
SINSAL_REPORT_COLUMNS: tuple[str, ...] = (
    "chart_id", "level", "period", "ganji", "event_key", "legacy_score",
    "occurrence_score_delta", "favorability_delta", "risk_delta", "mitigation_delta",
    "texture_tags", "contributions", "warns",
)


def build_sinsal_shadow_report(
    result: ManseV2Result,
    candidates: list[EventCandidate],
    ganji_by_period: dict[str, str],
    *,
    chart_id: str,
    period_level: dict[str, str],
    domain: str = "general",
) -> tuple[list[dict], dict]:
    """단일 차트의 신살 numeric shadow 리포트 행 + 요약(순수·미소비).

    Args:
        result: 만세 결과(traditional_extras.sinsal 필요).
        candidates: legacy 후보(EventEngineV2.score_legacy 결과). .score 불변.
        ganji_by_period: period(label) → 운 간지. exact match.
        chart_id: 익명 식별자.
        period_level: period → "year"/"daewoon".
        domain: 위치/intent 가중에 쓰는 질문 도메인.

    Returns:
        (rows, summary). rows = SINSAL_REPORT_COLUMNS 키 dict 목록.
    """
    sidecar = apply_sinsal_channel_shadow(
        result, candidates, ganji_by_period, domain=domain,
    )
    rows: list[dict] = []
    warn_count = 0
    for r in sidecar:
        period = r["period"]
        warns: list[str] = []
        magnitude = max(abs(r["favorability_delta"]), r["risk_delta"], r["mitigation_delta"])
        if magnitude >= cfg.SINSAL_CHANNEL_WARN:
            warns.append("channel")
            warn_count += 1
        rows.append({
            "chart_id": chart_id,
            "level": period_level.get(period, ""),
            "period": period,
            "ganji": ganji_by_period.get(period, ""),
            "event_key": r["event_key"],
            "legacy_score": r["legacy_score"],
            "occurrence_score_delta": r["occurrence_score_delta"],
            "favorability_delta": r["favorability_delta"],
            "risk_delta": r["risk_delta"],
            "mitigation_delta": r["mitigation_delta"],
            "texture_tags": ",".join(r.get("texture_tags", [])),
            "contributions": "; ".join(
                f"{k}={v}" for k, v in r.get("contributions", {}).items()
            ),
            "warns": ",".join(warns),
        })
    missing = sum(1 for r in sidecar if r.get("missing_ganji"))
    summary = {
        "chart_id": chart_id,
        "domain": domain,
        "candidates": len(candidates),
        "rows": len(rows),
        "missing_ganji": missing,
        "warn_channel": warn_count,
        "errors": ["all_candidates_skipped"] if candidates and not rows else [],
    }
    return rows, summary
