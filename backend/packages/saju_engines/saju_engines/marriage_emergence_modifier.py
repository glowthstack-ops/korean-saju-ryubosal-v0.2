"""MT2 — 일지 투출 글자 운 회귀 '배우자궁 발동' 증폭 (전용 modifier, v2.2 2026-06-30).

일지(배우자궁) 지장간 중 원국 천간으로 투출(透出)한 글자가 운 천간으로 **회귀**할 때, 배우자궁이
다시 발동한다는 영상 자료(MARRIAGE_TIMING_ENHANCEMENT §7)를 모델링한다. 복음(BOKEUM)과 같은 '원국
글자의 운 회귀' 개념이지만, same_stem/same_ten_god/same_element 3종 강도 차등·partner_star
게이트·spouse_palace_clashed 분기가 relation_palace의 flat bonus 구조와 안 맞아 **전용 modifier**로
처리한다(사용자 확정 — RelationKind.EMERGENCE_RETURN 미도입).

**증폭형(생성 금지)**: 기존 new_relationship/marriage_signal/relationship_change 후보에만 근거·
delta를 얹는다. 후보를 새로 만들지 않으므로 '단독 발동 금지'가 자동 충족된다. 배수는 후보 점수
전체에 곱하지 않고 **절대 delta 상한**으로 환산한다(과증폭 방지). same_element는 배경 근거(최소
delta). 배우자성 회귀만 강하게, 비배우자성·일간 투출(자기 의식)은 약하게. 회귀 글자가 일지 충에
관여하면 긍정 증폭하지 않고 stability 하향 태그만 남긴다. 가중은 잠정값(reviewed:false) — 미보장.
"""

from __future__ import annotations

from dataclasses import dataclass

from saju_shared_types.constants import STEM_ELEMENT, ten_god
from saju_shared_types.enums import Stem
from saju_shared_types.event_engine import EventCandidateV2, EventKeyV2
from saju_shared_types.manse_result import ManseV2Result

# 성별별 배우자성 십성(partner_star) — 여=관살·남=재성. marriage_timing.resolve_partner_star와 동의.
_PARTNER_STARS: dict[str, frozenset[str]] = {
    "female": frozenset({"정관", "편관"}),
    "male": frozenset({"정재", "편재"}),
}
_TARGET_KEYS = (
    EventKeyV2.NEW_RELATIONSHIP,
    EventKeyV2.MARRIAGE_SIGNAL,
    EventKeyV2.RELATIONSHIP_CHANGE,
)
# 절대 delta 상한(정수 점수) — (is_partner_star, 회귀유형). same_stem×1.0/same_element×0.40의
# 내부 strength를 과증폭 없는 상한으로 환산. same_element는 음양 짝(같은 오행·십성군) 회귀로 배경.
# NOTE: 일간 기준 천간↔십성은 1:1(전단사)이라 '글자 다름+십성 동일'(same_ten_god) 티어는 실현
# 불가능하다(같은 십성 ⟺ 같은 글자). 따라서 의미 있는 티어는 same_stem / same_element 둘뿐이다.
_DELTA: dict[tuple[bool, str], int] = {
    (True, "same_stem"): 10, (True, "same_element"): 4,
    (False, "same_stem"): 5, (False, "same_element"): 1,
}
_TIER_RANK = {"same_stem": 2, "same_element": 1}


@dataclass(frozen=True)
class EmergedStem:
    """일지 지장간 중 원국 천간으로 투출한 글자 1건(정적·비단정)."""

    stem: str
    element: str
    ten_god: str
    source_pillars: tuple[str, ...]   # 투출이 드러난 천간 자리(year/month/day/hour)
    is_day_master_exposure: bool      # 일간 자기 투출(자기 의식 발동 — partner_star 아님, weak)
    is_partner_star: bool


@dataclass(frozen=True)
class MarriageEmergenceNatal:
    """원국 일지 투출 글자 집합(운 미반영, 성별 인지)."""

    day_master: str
    emerged: tuple[EmergedStem, ...]
    gender: str


def analyze_marriage_emergence_natal(result: ManseV2Result) -> MarriageEmergenceNatal:
    """일지 지장간 ∩ 원국 천간4(글자 일치)로 투출 글자를 판정한다(정적·비단정).

    Args:
        result: 만세 결과(pillars.day 필요).

    Returns:
        MarriageEmergenceNatal — 일간·투출 글자 목록·성별. pillars 부재 시 빈 목록.
    """
    if result.pillars is None or result.pillars.day is None:
        return MarriageEmergenceNatal(day_master="", emerged=(), gender="unknown")
    p = result.pillars
    day = p.day
    dm = day.stem
    gender = str(result.input_summary.get("gender", "unknown"))
    partner = _PARTNER_STARS.get(gender, frozenset())

    stem_positions: dict[str, list[str]] = {}
    for pos, pil in (("year", p.year), ("month", p.month), ("day", p.day), ("hour", p.hour)):
        if pil is not None:
            stem_positions.setdefault(pil.stem, []).append(pos)

    emerged: list[EmergedStem] = []
    seen: set[str] = set()
    for h in day.hidden_stems:
        char = h.stem
        if char in seen or char not in stem_positions:
            continue  # 투출 안 됨(원국 천간에 안 드러남)
        seen.add(char)
        is_dm = char == dm
        tg = str(ten_god(Stem(dm), Stem(char)))
        emerged.append(EmergedStem(
            stem=char,
            element=h.element,
            ten_god=tg,
            source_pillars=tuple(stem_positions[char]),
            is_day_master_exposure=is_dm,
            is_partner_star=(not is_dm) and tg in partner,
        ))
    return MarriageEmergenceNatal(day_master=dm, emerged=tuple(emerged), gender=gender)


def _classify_return(
    natal: MarriageEmergenceNatal, luck_stem: str
) -> tuple[EmergedStem, str] | None:
    """운 천간이 투출 글자로 회귀한 가장 강한 1건 (emerged, tier)을 고른다.

    tier: same_stem(글자 동일) > same_element(같은 오행·음양 짝, 글자 다름). partner_star 회귀를
    우선하고, 동급이면 tier 강도로 고른다. 회귀 없으면 None. (천간↔십성 1:1이라 '십성만 동일'
    티어는 존재하지 않는다 — 같은 십성 ⟺ 같은 글자.)
    """
    if not luck_stem or not natal.day_master:
        return None
    luck_el = str(STEM_ELEMENT[Stem(luck_stem)])
    best: tuple[tuple[int, int], EmergedStem, str] | None = None
    for e in natal.emerged:
        if luck_stem == e.stem:
            tier = "same_stem"
        elif luck_el == e.element:
            tier = "same_element"
        else:
            continue
        prio = (1 if e.is_partner_star else 0, _TIER_RANK[tier])
        if best is None or prio > best[0]:
            best = (prio, e, tier)
    return (best[1], best[2]) if best is not None else None


class MarriageEmergenceModifier:
    """일지 투출 글자 운 회귀 → 기존 관계 후보 증폭(생성 금지·증폭만)."""

    @staticmethod
    def apply(
        cands: list[EventCandidateV2],
        natal: MarriageEmergenceNatal,
        luck_stem: str,
        spouse_palace_clashed: bool,
    ) -> list[EventCandidateV2]:
        """회귀 1건을 판정해 관계 후보에 절대 delta·근거를 얹는다(타 도메인·미회귀 시 무영향).

        Args:
            cands: 시점 후보(증폭 대상은 new_relationship/marriage_signal/relationship_change).
            natal: 원국 투출 글자(analyze_marriage_emergence_natal).
            luck_stem: 그 시점 운 천간(회귀 판정 대상).
            spouse_palace_clashed: 그 시점 일지(배우자궁) 충 활성 여부 — 긍정 증폭 차단·분기.

        Returns:
            증폭/태그가 반영된 후보 목록.
        """
        hit = _classify_return(natal, luck_stem)
        if hit is None:
            return cands
        emerged, tier = hit
        delta = _DELTA[(emerged.is_partner_star, tier)]
        out: list[EventCandidateV2] = []
        for c in cands:
            if c.event_key not in _TARGET_KEYS:
                out.append(c)
                continue
            reasons = [*c.reason_codes, f"MT2_EMERGENCE_{tier.upper()}"]
            if emerged.is_day_master_exposure:
                reasons.append("MT2_DAY_MASTER_EXPOSURE")  # 자기 의식 발동(weak·action 금지)
            applied = delta
            if spouse_palace_clashed:
                # 배우자궁이 움직인 '근거'는 남기되 결혼 성사로 긍정 증폭하지 않는다.
                reasons.extend(["MT2_EMERGENCE_CLASHED", "SPOUSE_PALACE_CLASHED"])
                applied = 0
            if applied <= 0:
                out.append(c.model_copy(update={"reason_codes": reasons}))
                continue
            new_score = max(0, c.score + applied)
            out.append(c.model_copy(update={
                "score": new_score,
                "reason_codes": reasons,
                "contributions": {**c.contributions, "marriage_emergence": float(applied)},
            }))
        return out
