"""MT1 — 일간 干合 배우자성 '관계 의식(awareness)' Seed Producer (v2.2, 2026-06-30).

기존 후보를 증폭하는 modifier가 아니라, 엔진에 없던 **awareness 후보를 '생성'**하는 규칙이다
(MARRIAGE_TIMING_ENHANCEMENT §6, 사용자 확정 — 생성형/Seed Producer로 분리해 marriage_flow_modifier
의 '증폭만' 원칙을 깨지 않는다). 운 천간이 원국 일간과 干合(본신지합)하고 그 천간 십성이
배우자성(partner_star)일 때, "마음·생각이 동하는" 단계를 표현한다.

**생성 범위 하드 제한**: `new_relationship` + marriage_stage `awareness`까지만. relationship/action/
commitment/formalization/marriage/family_expansion 후보는 절대 생성하지 않는다('마음이 동한다'이지
'좋은 인연/결혼'이 아니다). commitment/formalization marker를 대체하지 않는다.

**합거·쟁합·기신은 미발동이 아니라 불안정(awareness) 분기** — awareness seed는 생성하되 risk_flag를
달고 승급을 막는다. gender 미상은 차단하지 않고 양 기준(재성·관살)을 모두 검사하되 점수·confidence를
낮춘다(절대원칙 11). 점수·플래그는 단일 영상 가설의 **잠정값**(reviewed:false) — 캘리브레이션 전
미보장.
"""

from __future__ import annotations

from saju_manse_analysis.relations.hap_modes import resolve_stem_hap

from saju_shared_types.constants import STEM_ELEMENT, ten_god
from saju_shared_types.enums import Stem
from saju_shared_types.event_engine import (
    ConfidenceLevel,
    EventCandidateV2,
    EventKeyV2,
    PolarityRole,
)
from saju_shared_types.luck import LuckPillar
from saju_shared_types.manse_result import ManseV2Result

# 성별별 배우자성 십성(partner_star) — 여=관살, 남=재성. resolve_partner_star(marriage_timing)와
# 동일 의미를 운(運) 십성 한글 라벨 집합으로 직접 표현한다(엔진 group 어휘 'authority'와 무관).
_PARTNER_STARS: dict[str, frozenset[str]] = {
    "female": frozenset({"정관", "편관"}),
    "male": frozenset({"정재", "편재"}),
}
# 정형 배우자성(正) — 알려진 성별에서 +confirmed 가산 대상(정관/정재). 편관/편재는 base.
_CANONICAL_PARTNER_STAR: dict[str, str] = {"female": "정관", "male": "정재"}
_UNKNOWN_PARTNER_STARS = _PARTNER_STARS["female"] | _PARTNER_STARS["male"]

_BASE_SCORE = 30                 # 干合 + partner_star (영상 0.30 → 정수 스케일)
_PARTNER_CONFIRMED_BONUS = 10    # 성별 확정 + partner_star (상한 0.40)
_HWA_FAVORABLE_BONUS = 5         # 합화 화신이 용·희신 (상한 0.45)
_AWARENESS_CAP = 60              # awareness 단계 cap (§5)
_UNKNOWN_GENDER_CAP = 35         # gender 미상 — 양 기준 검사 시 점수 제한
_FAVORABLE_ROLES = frozenset({"용신", "희신"})
_ADVERSE_ROLES = frozenset({"기신", "구신"})


def produce_mt1_awareness_seeds(
    target: LuckPillar,
    result: ManseV2Result,
    fav_map: dict[str, str],
    gender: str,
    period: str,
) -> list[EventCandidateV2]:
    """MT1 — 운 천간이 일간과 干合 + 배우자성이면 new_relationship awareness seed를 생성한다.

    Args:
        target: 그 시점 운 기둥(세운·월운 등) — 운 천간이 일간 干合 대상인지 본다.
        result: 만세 결과(pillars 필수).
        fav_map: 오행 → 용기신 역할('용신'/'희신'/'기신'/'구신'/'한신').
        gender: 'female'/'male'/그 외(미상). 미상은 양 기준 검사 + 점수·confidence 하향.
        period: 운 기간 라벨('2026'/'2026-06' 등) — 후보 period로 그대로 쓴다.

    Returns:
        awareness seed 후보 목록(0 또는 1건). 干合 부재·비배우자성·pillars 부재 시 빈 목록.
    """
    if result.pillars is None or result.pillars.day is None or not target.stem:
        return []
    day_master = Stem(result.pillars.day.stem)
    luck_stem = Stem(target.stem)

    # 일간 본신지합(干合) — 운 천간이 일간과 결합(combine_self) + 운 관여 + 차단 아님.
    try:
        resolutions = resolve_stem_hap(result.pillars, fav_map, luck_stems=[target.stem])
    except (ValueError, KeyError):
        return []
    combined = any(
        r.hap_mode == "combine_self"
        and r.luck_origin
        and not r.blocked
        and "day" in r.positions
        for r in resolutions
    )
    if not combined:
        return []

    # 운 천간의 일간 기준 십성이 배우자성인가(성별 인지).
    luck_tg = str(ten_god(day_master, luck_stem))
    known = gender in ("female", "male")
    allowed = _PARTNER_STARS[gender] if known else _UNKNOWN_PARTNER_STARS
    if luck_tg not in allowed:
        return []

    reasons = ["MT1_DAY_STEM_HAP_PARTNER", "MT1_STAGE_AWARENESS"]
    score = _BASE_SCORE

    if known:
        reasons.append("MT1_PARTNER_STAR_CONFIRMED")
        score += _PARTNER_CONFIRMED_BONUS
        confidence = ConfidenceLevel.WEAK_EVENT_CANDIDATE
        if luck_tg == _CANONICAL_PARTNER_STAR[gender]:
            reasons.append("MT1_PARTNER_STAR_PROPER")  # 정관/정재 — 안정성 평가 보조(점수 동일)
    else:
        reasons.append("UNKNOWN_GENDER_DUAL_RULE")
        confidence = ConfidenceLevel.THEME_ONLY

    # 합화 화신이 용·희신이면 소폭 가산(긍정적 관심) — 단 합거·쟁합·기신 분기와 양립 가능.
    for r in resolutions:
        if (
            r.hap_mode == "combine_self"
            and r.transform_tier == "confirmed"
            and r.transform_element
            and fav_map.get(r.transform_element) in _FAVORABLE_ROLES
        ):
            reasons.append("MT1_HWA_FAVORABLE_BONUS")
            score += _HWA_FAVORABLE_BONUS
            break

    # 불안정 분기(미발동 아님): 기신/구신 — 마음은 동하나 안정성 낮음(risk_flag).
    luck_el = str(STEM_ELEMENT[luck_stem])
    if fav_map.get(luck_el) in _ADVERSE_ROLES:
        reasons.append("MT1_GISIN_RISK")
    # 쟁합·투합 proxy: 같은 운 천간 글자가 원국(일주 제외)에 있어 일간을 두고 다툼.
    p = result.pillars
    natal_stems = [
        pil.stem for pil in (p.year, p.month, p.hour) if pil is not None
    ]
    if target.stem in natal_stems:
        reasons.append("MT1_COMPETITION_RISK")

    cap = _UNKNOWN_GENDER_CAP if not known else _AWARENESS_CAP
    score = max(0, min(score, cap))

    return [
        EventCandidateV2(
            event_key=EventKeyV2.NEW_RELATIONSHIP,
            period=period,
            score=score,
            confidence_level=confidence,
            polarity_role=PolarityRole.NEUTRAL,
            reason_codes=reasons,
            contributions={"mt1_awareness": float(score)},
        )
    ]
