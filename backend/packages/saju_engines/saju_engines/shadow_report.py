"""Shadow Validation Harness 리포트 빌더 — 순수 함수(검증 도구, 운영 미연결).

#9a/#9b shadow 결과를 골든 차트 × 대표 기간에 일괄 산출해 legacy 대비 리포트한다.
**score/rank/favorability/final/polarity 불변** — 본 모듈은 산출물(리포트)만 만들고 어떤
운영 경로도 바꾸지 않는다. CLI(scripts/shadow_validation_harness.py)가 이 함수를 호출한다.

규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §10·§13
"""

from __future__ import annotations

import math

from saju_manse_analysis.yongsin.operational_role_config import (
    OPERABILITY_FACTOR_SHORT,
    SHADOW_WARN_RANK_DELTA_ABS,
    SHADOW_WARN_RANK_DELTA_RATIO,
    SHADOW_WARN_SCORE_DELTA,
)

from saju_shared_types.events import EventCandidate
from saju_shared_types.manse_result import ManseV2Result

from .event_scoring import favorability_map
from .shadow_scoring import candidate_shadow_diff, luck_expression_clamp, shadow_rank_diff

# 리포트 컬럼(고정 순서) — CSV 헤더·JSON 키 공통. BirthInput 원본 PII 미포함(chart_id만).
# rank 는 전역(_global)·레벨별(_level) 모두 노출. WARN 은 _level 기준(YEAR/DAEWOON 혼합 착시 제거).
REPORT_COLUMNS: tuple[str, ...] = (
    "chart_id", "level", "period", "ganji", "event_key",
    "legacy_score", "shadow_observation_score", "score_delta",
    "legacy_fav", "shadow_fav", "fav_delta",
    "legacy_rank_global", "shadow_rank_global", "rank_delta_global",
    "legacy_rank_level", "shadow_rank_level", "rank_delta_level",
    "level_pool_size", "rank_delta_pct", "rank_warn_threshold",
    "expression_class", "reason", "operational_roles", "operability_factors", "warns",
)


def _operational_summary(result: ManseV2Result) -> tuple[str, str]:
    """operational_roles 요약 + 용신 operability factor 요약(둘 다 표시용 문자열)."""
    ya = result.yongsin_analysis
    if ya is None:
        return "", ""
    roles = ",".join(f"{er.element}:{er.operational_role}" for er in ya.operational_roles)
    factors = ""
    for er in ya.operational_roles:
        if er.operability is not None:  # 용신 element
            ko = ",".join(
                OPERABILITY_FACTOR_SHORT.get(f, f) for f in er.operability_factors
            ) or "-"
            factors = f"{er.element} op={er.operability} [{ko}]"
            break
    return roles, factors


def build_shadow_report(
    result: ManseV2Result,
    candidates: list[EventCandidate],
    ganji_by_period: dict[str, str],
    *,
    chart_id: str,
    period_level: dict[str, str],
) -> tuple[list[dict], dict]:
    """단일 차트의 shadow 리포트 행 + 차트 단위 요약을 만든다(순수·미소비).

    candidate.period 와 ganji_by_period 키는 exact match 여야 한다. 매칭 간지가 없는 후보는
    skip + missing_ganji WARN 으로 집계한다(전부 skip 이면 errors 에 기록).

    Args:
        result: 만세 결과(yongsin_analysis.operational_roles 필요).
        candidates: legacy 후보(EventEngineV2.score_legacy 결과). .score 불변.
        ganji_by_period: period(label) → 운 간지("壬子"). exact match.
        chart_id: 익명 식별자(원본 BirthInput 미노출).
        period_level: period(label) → "year"/"daewoon" 등 레벨.

    Returns:
        (rows, summary). rows = REPORT_COLUMNS 키 dict 목록. summary = guard/skip 집계.
    """
    diffs = candidate_shadow_diff(result, candidates, ganji_by_period)
    # shadow_rank_diff 는 diffs 와 동일 순서로 후보별 행을 반환 — period 키로 묶으면 동일 기간의
    # 복수 후보가 충돌하므로 index 로 정렬한다(후보별 rank 보존). level 전달 → 전역+레벨별 순위.
    rank_rows = shadow_rank_diff(diffs, level_by_period=period_level)
    op_roles, op_factors = _operational_summary(result)
    # 레벨별 풀 크기(후보 수) — rank WARN 임계 상대화 기준.
    level_pool: dict[str, int] = {}
    for d in diffs:
        lvl = period_level.get(d["period"], "")
        level_pool[lvl] = level_pool.get(lvl, 0) + 1

    rows: list[dict] = []
    warn_counts: dict[str, int] = {"score_delta": 0, "rank_delta": 0}
    for i, d in enumerate(diffs):
        period = d["period"]
        ganji = ganji_by_period.get(period, "")
        clamp = luck_expression_clamp(result, ganji) if len(ganji) >= 2 else None
        rank = rank_rows[i]
        # rank WARN 은 레벨별(_level)·풀 크기 상대화 — 큰 풀의 잔흔을 WARN 에서 제외.
        pool = level_pool.get(period_level.get(period, ""), 0)
        threshold = max(SHADOW_WARN_RANK_DELTA_ABS,
                        math.ceil(pool * SHADOW_WARN_RANK_DELTA_RATIO))
        rdl = rank.get("rank_delta_level", 0)
        rank_delta_pct = round(abs(rdl) / pool, 4) if pool else 0.0
        warns: list[str] = []
        if abs(d["score_delta"]) >= SHADOW_WARN_SCORE_DELTA:
            warns.append("score_delta")
            warn_counts["score_delta"] += 1
        if abs(rdl) >= threshold:
            warns.append("rank_delta")
            warn_counts["rank_delta"] += 1
        rows.append({
            "chart_id": chart_id,
            "level": period_level.get(period, ""),
            "period": period,
            "ganji": ganji,
            "event_key": d["event_key"],
            "legacy_score": d["legacy_score"],
            "shadow_observation_score": d["shadow_observation_score"],
            "score_delta": d["score_delta"],
            "legacy_fav": d["legacy_fav"],
            "shadow_fav": d["shadow_fav"],
            "fav_delta": d["fav_delta"],
            "legacy_rank_global": rank.get("legacy_rank_global"),
            "shadow_rank_global": rank.get("shadow_rank_global"),
            "rank_delta_global": rank.get("rank_delta_global"),
            "legacy_rank_level": rank.get("legacy_rank_level"),
            "shadow_rank_level": rank.get("shadow_rank_level"),
            "rank_delta_level": rank.get("rank_delta_level"),
            "level_pool_size": pool,
            "rank_delta_pct": rank_delta_pct,
            "rank_warn_threshold": threshold,
            "expression_class": clamp["expression_class"] if clamp else "",
            "reason": "; ".join(d["reason"]),
            "operational_roles": op_roles,
            "operability_factors": op_factors,
            "warns": ",".join(warns),
        })

    # missing ganji: 후보는 있으나 매칭 간지 없는 건수(candidate_shadow_diff 가 내부 skip).
    missing = [c.period for c in candidates if c.period not in ganji_by_period
               or len(ganji_by_period.get(c.period, "")) < 2]
    summary = {
        "chart_id": chart_id,
        "candidates": len(candidates),
        "rows": len(rows),
        "missing_ganji": len(missing),
        "warn_score_delta": warn_counts["score_delta"],
        "warn_rank_delta": warn_counts["rank_delta"],
        "errors": (["all_candidates_skipped"]
                   if candidates and not rows else []),
    }
    return rows, summary


def invariance_snapshot(result: ManseV2Result, candidates: list[EventCandidate]) -> dict:
    """불변 검증용 스냅샷(Guard #6) — favorability_map + 후보 score/polarity/final.

    harness 실행 전후로 이 스냅샷이 동일해야 한다(shadow 산출이 운영값을 건드리지 않음).
    """
    ya = result.yongsin_analysis
    return {
        "favorability": dict(favorability_map(result)),
        "final": dict(ya.final) if ya is not None else {},
        "scores": [(c.period, c.event_key, c.score) for c in candidates],
        "polarity": [(c.period, c.event_key, str(c.polarity)) for c in candidates],
    }
