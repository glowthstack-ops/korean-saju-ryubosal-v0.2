"""건강 채널 단일 원천(C5-1, 2026-10-07 데굴님 승인) — 건강 창 점수 → health_attention 후보.

사례집 분석(doc/v2_2/HEALTH_CHANNEL_C5.md): 이벤트 엔진의 health.json 7규칙은 12연도 중 8건에서
후보조차 내지 못했고, 기존 `health_risk_windows`(취약 구조 운 재자극)는 7건 ≥30 을 맞혔다. 그래서
health_attention 후보는 창 점수에서 파생하고, 기존 규칙 후보는 같은 기간에서 **치환**한다
(중복 가산 금지). 연(YYYY)·월(YYYY-MM) 모두 다룬다(월 단위는 데굴님 지시로 같은 날 추가).

- 새 명리 규칙 없음: 점수는 `health_vulnerability` 의 기존 가중(천극지충 25, 손상 장기 재공격 24 …).
- 후보 생성 임계는 창 ≥30. 표시 점수는 창 30→45, 100→95 로 선형 사상.
- 월 후보는 그 달 창 ≥30 이고 (그 해 세운 창이 본인 p85 이상이거나 월 창 ≥60)일 때만 —
  과다 경고 억제.
- 사망·질병 어휘를 만들지 않는다. 비밀 코드(C5-4)는 `health_vulnerability.severe_event_code` 가
  따로 다루며 reason_codes 에 `HEALTH_CODE:F-n` 으로만 실린다(의미 미포함).
"""

from __future__ import annotations

from saju_shared_types.event_engine import (
    ConfidenceLevel,
    EventCandidateV2,
    EventKeyV2,
    EventQuality,
    PolarityRole,
)
from saju_shared_types.health_vulnerability import HealthRiskWindow
from saju_shared_types.manse_result import ManseV2Result

from .event_scoring import favorability_map
from .health_vulnerability import (
    analyze_health_vulnerability,
    health_percentile_thresholds,
    health_window_scores,
    health_window_scores_monthly,
    lifetime_health_scores,
    severe_event_code,
)

HEALTH_CANDIDATE_MIN_WINDOW = 30
MONTH_STANDALONE_MIN_WINDOW = 60
_CONF_BY_LEVEL = {
    "적극 관리·검진 권장": ConfidenceLevel.STRONG_EVENT_CANDIDATE,
    "정기 검진 권장": ConfidenceLevel.EVENT_CANDIDATE,
    "생활 관리 권장": ConfidenceLevel.WEAK_EVENT_CANDIDATE,
}


def _display_score(window_score: int) -> int:
    """창 30→45, 100→95 선형 사상(다른 도메인 후보와 같은 표시 스케일)."""
    return int(round(45 + (window_score - 30) * (50 / 70)))


def _candidate(
    w: HealthRiskWindow, thresholds: dict[str, int], extra: list[str],
) -> EventCandidateV2:
    reasons = [f"HEALTH_WINDOW:{r}" for r in w.reasons] + extra
    code = severe_event_code(w, thresholds)
    if code:
        reasons.append(f"HEALTH_CODE:{code}")
    return EventCandidateV2(
        event_key=EventKeyV2.HEALTH_ATTENTION,
        period=w.period,
        score=_display_score(w.score),
        confidence_level=_CONF_BY_LEVEL.get(w.level, ConfidenceLevel.WEAK_EVENT_CANDIDATE),
        quality=EventQuality.PRESSURE,
        polarity_role=PolarityRole.NEUTRAL,
        reason_codes=reasons,
        contributions={"health_window": float(w.score)},
        activation=float(_display_score(w.score)),
        favorability=-0.5,
    )


def inject_health_window_candidates(
    result: ManseV2Result,
    candidates: list[EventCandidateV2],
) -> list[EventCandidateV2]:
    """연·월 health_attention 후보를 창 점수에서 파생해 기존 것을 치환한다.

    결과에 있는 세운(yearly_luck)·월운(monthly_luck) 기간만 다룬다. 창 점수가 없는 기간의 기존
    health_attention 후보는 제거한다(규칙 후보가 변별력 없이 양성 fav 로 뜨던 결함 차단).
    """
    lc = result.luck_cycles
    if lc is None or result.pillars is None:
        return candidates
    sewoon = [sw for sw in lc.yearly_luck if str(getattr(sw, "label", "")).isdigit()]
    months = [mp for mp in lc.monthly_luck if len(str(getattr(mp, "label", ""))) == 7]
    if not sewoon and not months:
        return candidates
    profile = analyze_health_vulnerability(result, favorability_map(result))
    yearly = health_window_scores(result, profile, sewoon) if sewoon else {}
    thresholds = health_percentile_thresholds(lifetime_health_scores(result, profile))
    p85 = thresholds.get("p85", 0)
    year_scope = {int(sw.label) for sw in sewoon}
    month_scope = {str(mp.label) for mp in months}
    kept = [
        c for c in candidates
        if not (
            c.event_key == EventKeyV2.HEALTH_ATTENTION
            and ((c.period.isdigit() and int(c.period) in year_scope) or c.period in month_scope)
        )
    ]
    for y in sorted(year_scope):
        w = yearly.get(y)
        if w is None or w.score < HEALTH_CANDIDATE_MIN_WINDOW:
            continue
        kept.append(_candidate(w, thresholds, []))
    if months:
        # 월 배경용 세운 창: 결과 yearly_luck 에 없는 해는 생애 창에서 보충.
        need_years = {int(lbl[:4]) for lbl in month_scope} - set(yearly)
        if need_years:
            life = lifetime_health_scores(result, profile)
            yearly = {**{y: life[y] for y in need_years if y in life}, **yearly}
        monthly = health_window_scores_monthly(result, profile, months, yearly)
        for label in sorted(month_scope):
            w = monthly.get(label)
            if w is None or w.score < HEALTH_CANDIDATE_MIN_WINDOW:
                continue
            yw = yearly.get(int(label[:4]))
            year_flagged = yw is not None and p85 > 0 and yw.score >= p85
            if not (year_flagged or w.score >= MONTH_STANDALONE_MIN_WINDOW):
                continue
            kept.append(_candidate(w, thresholds, ["HEALTH_WINDOW:월 단위"]))
    return kept
