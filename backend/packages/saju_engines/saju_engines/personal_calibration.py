"""personal_calibration — 개인 과거 사건 시그니처로 후보를 보정한다(LIFE_EVENT_INFERENCE.md §4).

같은 신호 지문의 과거 확정 사건과 유사하면 personal_match↑(past_event_match), 반복 확정 테마는
가중(repeated_life_theme), 과거에 '안 일어남'으로 확인된 유형은 감점(failed_prediction_penalty),
반복 확정/예정인데 후보에 없는 사건은 시드(missing-event seed — 예: relocation 누락 보완).
본 계층은 개인(subject 본인) 시그니처만 다룬다. 코호트는 활성 게이트 통과 후 별도(§4.4).
"""

from __future__ import annotations

from saju_shared_types.event_engine import (
    TEN_GOD_GROUP,
    ConfidenceLevel,
    EventCandidateV2,
    EventKeyV2,
    Pillar4,
    TwelveStage,
)
from saju_shared_types.life_event import LifeEventOutcome, LifeEventRow, SignalFingerprint

_OCCURRED = {LifeEventOutcome.CONFIRMED, LifeEventOutcome.PLANNED}


def candidate_fingerprint(c: EventCandidateV2) -> SignalFingerprint:
    """후보의 신호 지문(십성그룹·궁성·관계·12운성) — 개인·코호트 매칭 단위."""
    groups = sorted({TEN_GOD_GROUP[g].value for g in c.source_ten_gods if g in TEN_GOD_GROUP})
    relation: str | None = None
    for code in c.reason_codes:
        if code.startswith("REL_"):
            parts = code.split("_")
            if len(parts) >= 2:
                relation = parts[1]
                break
    return SignalFingerprint(
        ten_god_groups=groups,
        palace=c.palace.value if c.palace else None,
        relation=relation,
        twelve_stage=c.twelve_stage.value if c.twelve_stage else None,
    )


def fingerprint_similarity(a: SignalFingerprint, b: SignalFingerprint) -> float:
    """두 신호 지문의 유사도 0~1 (십성그룹 Jaccard 0.4 + 궁성·관계·12운성 일치)."""
    sa, sb = set(a.ten_god_groups), set(b.ten_god_groups)
    jac = len(sa & sb) / len(sa | sb) if (sa or sb) else 0.0
    palace = 1.0 if a.palace and a.palace == b.palace else 0.0
    relation = 1.0 if a.relation and a.relation == b.relation else 0.0
    stage = 1.0 if a.twelve_stage and a.twelve_stage == b.twelve_stage else 0.0
    return 0.4 * jac + 0.3 * palace + 0.2 * relation + 0.1 * stage


# 개인 시그니처가 점수에 주는 최대 가감(상한) — 기저 명리 계산을 뒤집지 않는 보정폭.
_PERSONAL_SCORE_CAP = 8
# 확신도 티어 순서(강한 매칭/불일치 시 ±1티어만 이동).
_CONF_ORDER = [
    ConfidenceLevel.THEME_ONLY,
    ConfidenceLevel.WEAK_EVENT_CANDIDATE,
    ConfidenceLevel.EVENT_CANDIDATE,
    ConfidenceLevel.STRONG_EVENT_CANDIDATE,
    ConfidenceLevel.HIGH_PROBABILITY_EVENT,
]


def _shift_confidence(level: ConfidenceLevel, steps: int) -> ConfidenceLevel:
    """확신도 티어를 steps(±)만큼 이동(범위 클램프)."""
    i = _CONF_ORDER.index(level)
    return _CONF_ORDER[max(0, min(len(_CONF_ORDER) - 1, i + steps))]


def apply_personal_match(
    candidates: list[EventCandidateV2], signature: list[LifeEventRow]
) -> list[EventCandidateV2]:
    """후보별 personal_match를 개인 시그니처로 산출하고, 그 강도를 점수·확신도에 상한 내 반영한다.

    현실 신호 캘리브레이션(사용자 확인 과거 사건)이 정렬만 바꾸지 않고 **계산(점수·확신도)** 을
    보정해 풀이 정확도를 높인다(사용자 확정 2026-07-02, 풀이 프롬프트 낭독이 아님). 점수 보정폭은
    ±``_PERSONAL_SCORE_CAP``(기저 명리 계산을 뒤집지 않음), 확신도는 강한 매칭/불일치 시 ±1티어만
    이동한다. 사건 타입·정렬축(lei_rank_key)은 불변.
    """
    if not signature:
        return candidates
    occurred: dict[str, list[LifeEventRow]] = {}
    failed: dict[str, list[LifeEventRow]] = {}
    for r in signature:
        (occurred if r.outcome in _OCCURRED else failed).setdefault(r.event_key, []).append(r)
    out: list[EventCandidateV2] = []
    for c in candidates:
        ek = str(c.event_key)
        cfp = candidate_fingerprint(c)
        oc = occurred.get(ek, [])
        fl = failed.get(ek, []) if failed.get(ek) is not None else []
        match = max((fingerprint_similarity(cfp, r.signal_fingerprint) for r in oc), default=0.0)
        repeat = 0.2 * max(0, len({r.period for r in oc}) - 1)  # 반복 확정 테마 가중
        fail = max(
            (fingerprint_similarity(cfp, r.signal_fingerprint) for r in fl), default=0.0
        ) * 0.5
        pm = round((match + repeat - fail) * 100, 1)
        if pm == 0.0:
            out.append(c)
            continue
        # 점수 보정(상한 클램프) + 강한 매칭·불일치 시 확신도 ±1티어.
        boost = round(max(-100.0, min(100.0, pm)) / 100 * _PERSONAL_SCORE_CAP)
        new_score = max(0, min(100, c.score + boost))
        conf = c.confidence_level
        if pm >= 50:
            conf = _shift_confidence(conf, 1)
        elif pm <= -50:
            conf = _shift_confidence(conf, -1)
        reasons = [*c.reason_codes, "PERSONAL_MATCH" if pm > 0 else "PERSONAL_FAIL"]
        out.append(c.model_copy(update={
            "personal_match": pm, "reason_codes": reasons,
            "score": new_score, "confidence_level": conf,
        }))
    return out


def seed_missing_events(
    candidates: list[EventCandidateV2], signature: list[LifeEventRow], periods: list[str]
) -> list[EventCandidateV2]:
    """반복 확정/예정 테마인데 후보에 없는 사건을 시드한다(사주 신호 약해도 현실·과거가 렌하면).

    예: relocation이 2025·2026 확정/예정인데 그 시점 후보에 없으면 relocation을 personal_match와
    함께 후보로 추가한다(점수=0, 강도는 personal_match·life_fit가 부여).
    """
    occurred: dict[str, list[LifeEventRow]] = {}
    for r in signature:
        if r.outcome in _OCCURRED:
            occurred.setdefault(r.event_key, []).append(r)
    # 반복(연도 2개+) 또는 예정(planned)인 테마만 시드 대상.
    themes = {
        ek: rows for ek, rows in occurred.items()
        if len({r.period for r in rows}) >= 2
        or any(r.outcome is LifeEventOutcome.PLANNED for r in rows)
    }
    if not themes:
        return candidates
    present = {(str(c.event_key), c.period) for c in candidates}
    seeds: list[EventCandidateV2] = []
    for period in periods:
        for ek, rows in themes.items():
            if (ek, period) in present:
                continue
            rep = rows[0]
            repeats = max(0, len({r.period for r in rows}) - 1)
            seeds.append(EventCandidateV2(
                event_key=EventKeyV2(ek),
                period=period,
                score=0,  # 사주 잠재 없음 — 강도는 personal_match/life_fit
                confidence_level=ConfidenceLevel.EVENT_CANDIDATE,
                palace=_pillar(rep.signal_fingerprint.palace),
                twelve_stage=_stage(rep.signal_fingerprint.twelve_stage),
                reason_codes=["PERSONAL_SEED"],
                personal_match=round((0.6 + 0.2 * repeats) * 100, 1),
            ))
    return [*candidates, *seeds]


def _pillar(v: str | None) -> Pillar4 | None:
    try:
        return Pillar4(v) if v else None
    except ValueError:
        return None


def _stage(v: str | None) -> TwelveStage | None:
    try:
        return TwelveStage(v) if v else None
    except ValueError:
        return None
