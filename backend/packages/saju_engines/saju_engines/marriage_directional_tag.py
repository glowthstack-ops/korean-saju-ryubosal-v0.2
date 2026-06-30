"""MT3 — 방합(方合) 배우자궁 게이트 '얇은 태깅' 레이어 (v2.2, 2026-06-30).

방합(DIRECTIONAL_CONTRIB)은 이미 `_REL_KIND`에서 HAP으로 매핑돼 relation_palace가 일지(DAY)궁
활성으로 관계 후보를 보강한다. 따라서 **MT3는 점수를 다시 더하지 않고**(과증폭·포화 방지), "방합이
배우자궁(일지)을 물었다"는 의미와 partnerElement·충형파해 분기를 **reason_code 태그로만** 남긴다
(A안, 사용자 확정 2026-06-30). full/partial(반합) 구분은 hit가 노출하지 않아 2차로 보류한다.

spousePalace=true의 정의: **일지 글자가 방합 구성에 참여**(방합 hit의 natal_refs에 day 포함). 이는
relation_palace의 DAY궁 활성과 동치다. partnerElement는 방합 결과 오행이 배우자성(여=관살·남=재성)
오행과 일치하는지의 **별개 조건**이다. MT3는 단독으로 commitment/formalization 승급을 만들지 않는다
(태깅만이라 자동 충족). 전부 reviewed:false — feature flag OFF면 완전 비활성.
"""

from __future__ import annotations

from saju_shared_types.constants import STEM_ELEMENT
from saju_shared_types.enums import Stem
from saju_shared_types.event_engine import EventCandidateV2, EventKeyV2
from saju_shared_types.ganji_calendar import RelationHit, RelationType
from saju_shared_types.manse_result import ManseV2Result

_TARGET_KEYS = (
    EventKeyV2.NEW_RELATIONSHIP,
    EventKeyV2.MARRIAGE_SIGNAL,
    EventKeyV2.RELATIONSHIP_CHANGE,
)
# 오행 상극(한자) — 재성=일간이 극하는 오행 / 관살=일간을 극하는 오행.
_CONTROLS: dict[str, str] = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
# 일지 관여 충형파해 → stability 분기 태그(점수 감점 아님).
_RISK_TAG: dict[RelationType, str] = {
    RelationType.BRANCH_CLASH: "MT3_DIRECTIONAL_CLASHED",
    RelationType.BRANCH_BREAK: "MT3_DIRECTIONAL_BREAK",
    RelationType.HARM: "MT3_DIRECTIONAL_HARM",
    RelationType.PUNISHMENT_TRIPLE: "MT3_DIRECTIONAL_PUNISHMENT",
    RelationType.PUNISHMENT_MUTUAL: "MT3_DIRECTIONAL_PUNISHMENT",
    RelationType.SELF_PUNISHMENT: "MT3_DIRECTIONAL_PUNISHMENT",
}


def _partner_elements(day_el: str, gender: str) -> set[str]:
    """배우자성 오행 — 여=관살(일간을 극) / 남=재성(일간이 극) / 미상=양쪽."""
    wealth = _CONTROLS.get(day_el, "")
    officer = next((e for e, v in _CONTROLS.items() if v == day_el), "")
    if gender == "female":
        return {officer} - {""}
    if gender == "male":
        return {wealth} - {""}
    return {wealth, officer} - {""}


def _involves_day(hit: RelationHit) -> bool:
    """관계 hit가 원국 일지(배우자궁)를 포함하는지."""
    return any(r.position == "day" for r in hit.natal_refs)


def apply_mt3_directional_tags(
    cands: list[EventCandidateV2],
    hits: list[RelationHit],
    result: ManseV2Result,
    gender: str,
) -> list[EventCandidateV2]:
    """방합이 일지를 물면 관계 후보에 MT3 태그를 부여한다(점수 무변경·증폭 아님).

    Args:
        cands: 시점 후보.
        hits: 시점 관계 적중(합충형파해·공망).
        result: 만세 결과(일간 오행 — partnerElement 판정).
        gender: 성별(female/male/그 외) — 배우자성 오행 방향.

    Returns:
        spousePalace 방합이 있으면 관계 후보에 태그를 단 목록, 없으면 원본 그대로.
    """
    if result.pillars is None or result.pillars.day is None:
        return cands
    dir_day = [
        h for h in hits
        if h.type is RelationType.DIRECTIONAL_CONTRIB and _involves_day(h)
    ]
    if not dir_day:
        return cands  # 방합이 일지 미포함 → MT3 미발동

    tags = ["MT3_DIRECTIONAL_DAY_BRANCH"]
    day_el = str(STEM_ELEMENT[Stem(result.pillars.day.stem)])
    partner_els = _partner_elements(day_el, gender)
    if any(h.element in partner_els for h in dir_day if h.element):
        tags.append("MT3_DIRECTIONAL_PARTNER_ELEMENT")
    # 일지 관여 충형파해 → stability 분기 태그(중복 제거, 안정 순서 유지).
    for h in hits:
        tag = _RISK_TAG.get(h.type)
        if tag is not None and _involves_day(h) and tag not in tags:
            tags.append(tag)

    out: list[EventCandidateV2] = []
    for c in cands:
        if c.event_key in _TARGET_KEYS:
            out.append(c.model_copy(update={"reason_codes": [*c.reason_codes, *tags]}))
        else:
            out.append(c)
    return out
