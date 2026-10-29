"""연애운 시기 규칙 — 외부 강의 4편 대조(2026-10-25 데굴님 승인).

SSOT: doc/v2_2/EXTERNAL_TEXT_GAP_LOVE_TIMING.md

점수 규칙은 전부 **실험 플래그**(`LOVE_EXPERIMENTS`, 기본 OFF)이며 85사례 재생 적중률로 ON/OFF 를
정한다(데굴님 원칙: 점수 규칙은 적중률). 성별 기준 배우자성(여=관성·남=재성)은 기존 정책을 따른다.

  female_qisha_partner   : 여성 세운·월운 편관 → 새 인연 28·관계 변동 24 시드(남 편재 30 과 대칭).
                            원국 관살 ≥3 또는 관살혼잡이면 relationship_change 에 QISHA_PRESSURE
                            태그(갈등·선택 폭 — 이별 단정 금지, RES §1·§4 정책).
  hap_overload_damping   : 원국 합(천간합·육합·왕지 반합·완성) ≥3 이면 일지 HAP 궁위 가산 ×0.7.
  partner_element_daewoon: 배우자성 미투출(약) + 대운 천간/지지 오행 = 배우자성 오행
                            → marriage_signal +6.
  new_relationship_palace: new_relationship 을 일지 HAP·복음 likely_events 에 편입
                            (궁위 가산 사각 해소).
  separation_*           : 남녀 이별운 강의(2026-10-29) — love_separation 모듈 참조.
"""

from __future__ import annotations

import os
from collections.abc import Collection

from saju_shared_types.constants import CONTROLS, STEM_ELEMENT
from saju_shared_types.enums import Element, Stem, TenGod
from saju_shared_types.event_engine import (
    ConfidenceLevel,
    EventCandidateV2,
    EventKeyV2,
    LuckLayer,
    PolarityRole,
)
from saju_shared_types.event_engine import TenGod as TenGodCode
from saju_shared_types.luck import LuckPillar
from saju_shared_types.manse_result import ManseV2Result

from .love_separation import SEPARATION_KEYS

LOVE_EXPERIMENT_KEYS: tuple[str, ...] = (
    "new_relationship_palace",
    "female_qisha_partner",
    "hap_overload_damping",
    "partner_element_daewoon",
    # 이별운 강의 번역층(2026-10-29, saju_engines.love_separation) — 규칙 4종 + 지지 가중 변형.
    *SEPARATION_KEYS,
)
_ENV = "SAJU_LOVE_EXPERIMENTS"  # 쉼표 구분 이름 목록 — 운영 기본은 비움(전부 OFF)

#: 여성 편관 운 시드 점수 — 남성 편재 단일 운(new_relationship 30)과 대칭(데굴님 "권유대로").
FEMALE_QISHA_NEW_RELATIONSHIP = 28
FEMALE_QISHA_RELATIONSHIP_CHANGE = 24
#: 원국 합 과다 감쇠 — 합 관계 수 임계와 배율.
HAP_OVERLOAD_THRESHOLD = 3
HAP_OVERLOAD_MULT = 0.7
#: 배우자성 오행 대운 배경 가산.
PARTNER_ELEMENT_DAEWOON_BONUS = 6


def resolve_love_experiments(names: Collection[str] | None = None) -> dict[str, bool]:
    """실험 플래그 dict — 인자가 None 이면 환경변수 `SAJU_LOVE_EXPERIMENTS`(쉼표)에서 읽는다."""
    if names is None:
        raw = os.environ.get(_ENV, "")
        names = [x.strip() for x in raw.split(",") if x.strip()]
    unknown = sorted(set(names) - set(LOVE_EXPERIMENT_KEYS))
    if unknown:
        raise ValueError(f"알 수 없는 연애운 실험 플래그: {unknown}")
    return {k: (k in names) for k in LOVE_EXPERIMENT_KEYS}


def partner_star_element(result: ManseV2Result, gender: str) -> Element | None:
    """배우자성 오행 — 여=관성(일간을 극하는 오행), 남=재성(일간이 극하는 오행).

    성별 미상은 None.
    """
    if result.pillars is None or gender not in ("male", "female"):
        return None
    dm_el = STEM_ELEMENT[Stem(result.pillars.day_master)]
    if gender == "male":
        return CONTROLS[dm_el]
    return next(el for el, target in CONTROLS.items() if target == dm_el)


def _natal_officer_count(result: ManseV2Result) -> int:
    """원국 관살(정관·편관) 가시 개수 — 천간 십성 + 지지 본기 십성."""
    p = result.pillars
    if p is None:
        return 0
    n = 0
    for pillar in (p.year, p.month, p.day, p.hour):
        if pillar is None:
            continue
        for god in (pillar.stem_ten_god, pillar.branch_main_ten_god):
            if god in ("정관", "편관"):
                n += 1
    return n


def _has_gwansal_honjap(result: ManseV2Result) -> bool:
    """관살혼잡(정관·편관 동시 가시)."""
    p = result.pillars
    if p is None:
        return False
    gods = {
        g for pillar in (p.year, p.month, p.day, p.hour) if pillar is not None
        for g in (pillar.stem_ten_god, pillar.branch_main_ten_god)
    }
    return "정관" in gods and "편관" in gods


def produce_female_qisha_seeds(
    signals: list,
    target_layer: LuckLayer,
    result: ManseV2Result,
    gender: str,
    period: str,
) -> list[EventCandidateV2]:
    """여성 명식의 세운·월운 편관 유입 → 새 인연·관계 변동 시드(P1-1, 실험).

    강의(운세고): 여성 사주에 편관 운이 강하게 들면 남자와 엮이는 확률이 높다. 원국에 관살이 이미
    많거나 혼잡이면 갈등·이성 이슈도 함께 — 우리는 이별 단정 대신 `QISHA_PRESSURE` 태그로 둔다.
    남성은 편재 단일 운이 이미 new_relationship 30 을 내므로 대칭 보정(28·24)이다.
    """
    if gender != "female" or result.pillars is None:
        return []
    if target_layer not in (LuckLayer.SEWOON, LuckLayer.WOLWOON):
        return []
    hits = [s for s in signals if s.layer is target_layer and s.ten_god is TenGod.PYEONGWAN]
    if not hits:
        return []
    strong = any(getattr(s, "strength", 0.0) >= 1.0 for s in hits)  # 천간 유입 또는 동계열 집중
    reasons = ["LOVE_QISHA_FEMALE_PARTNER"]
    if strong:
        reasons.append("LOVE_QISHA_STRONG_INFLOW")
    pressure = _natal_officer_count(result) >= 3 or _has_gwansal_honjap(result)
    out: list[EventCandidateV2] = []
    for event, score in (
        (EventKeyV2.NEW_RELATIONSHIP, FEMALE_QISHA_NEW_RELATIONSHIP),
        (EventKeyV2.RELATIONSHIP_CHANGE, FEMALE_QISHA_RELATIONSHIP_CHANGE),
    ):
        codes = list(reasons)
        if pressure and event is EventKeyV2.RELATIONSHIP_CHANGE:
            codes.append("LOVE_QISHA_PRESSURE")
        out.append(EventCandidateV2(
            event_key=event,
            period=period,
            score=score,
            confidence_level=ConfidenceLevel.WEAK_EVENT_CANDIDATE,
            polarity_role=PolarityRole.NEUTRAL,
            source_layers=[target_layer],
            candidate_source_layers=[target_layer.value],
            source_ten_gods=[TenGodCode.QISHA],
            reason_codes=codes,
            contributions={"base": float(score)},
        ))
    return out


def natal_hap_count(result: ManseV2Result) -> int:
    """원국 합 관계 수 — 천간합(차단 제외)·육합·왕지 반합·삼합/방합 완성(공합 제외)."""
    from saju_manse_analysis.relations.hap_modes import resolve_branch_hap, resolve_stem_hap

    if result.pillars is None:
        return 0
    n = sum(1 for r in resolve_stem_hap(result.pillars, {}) if not r.blocked)
    for r in resolve_branch_hap(result.pillars, {}):
        if r.kind in ("six", "half", "three_harmony") or (
            r.kind == "directional" and r.hap_mode == "strengthen"
        ):
            n += 1
    return n


def hap_overload_damping(result: ManseV2Result) -> float:
    """원국 합이 임계 이상이면 일지 HAP 가산 배율(강의: 합이 너무 많으면 급상승과 거리)."""
    return HAP_OVERLOAD_MULT if natal_hap_count(result) >= HAP_OVERLOAD_THRESHOLD else 1.0


def apply_partner_element_daewoon(
    cands: list[EventCandidateV2],
    stack: list[tuple[LuckLayer, LuckPillar]],
    result: ManseV2Result,
    gender: str,
) -> list[EventCandidateV2]:
    """배우자성 미투출(약) + 대운 오행이 배우자성 오행이면 marriage_signal 배경 가산(P1-3).

    강의(결혼운): 배우자성 오행이 약한 명식은 그 오행이 대운에서 강해지는 시기가 결혼 시기.
    """
    from .marriage_resource import analyze_marriage_resource

    el = partner_star_element(result, gender)
    if el is None or result.force_analysis is None:
        return cands
    try:
        mr = analyze_marriage_resource(result)
    except (AssertionError, ValueError):
        return cands
    if not mr.spouse_star_absent:
        return cands
    daewoon = next((p for layer, p in stack if layer is LuckLayer.DAEWOON), None)
    if daewoon is None or len(daewoon.ganji) < 2:
        return cands
    from saju_shared_types.constants import BRANCH_ELEMENT
    from saju_shared_types.enums import Branch

    hit = (
        STEM_ELEMENT[Stem(daewoon.ganji[0])] == el
        or BRANCH_ELEMENT[Branch(daewoon.ganji[1])] == el
    )
    if not hit:
        return cands
    code = f"LOVE_PARTNER_ELEMENT_DAEWOON_{daewoon.ganji}"
    out: list[EventCandidateV2] = []
    for c in cands:
        if c.event_key is not EventKeyV2.MARRIAGE_SIGNAL or code in c.reason_codes:
            out.append(c)
            continue
        out.append(c.model_copy(update={  # provenance-audit: not-risk (EventCandidateV2)
            "score": c.score + PARTNER_ELEMENT_DAEWOON_BONUS,
            "reason_codes": [*c.reason_codes, code],
            "contributions": {
                **c.contributions, "partner_element_daewoon": float(PARTNER_ELEMENT_DAEWOON_BONUS),
            },
        }))
    return out


__all__ = [
    "FEMALE_QISHA_NEW_RELATIONSHIP",
    "FEMALE_QISHA_RELATIONSHIP_CHANGE",
    "HAP_OVERLOAD_MULT",
    "HAP_OVERLOAD_THRESHOLD",
    "LOVE_EXPERIMENT_KEYS",
    "PARTNER_ELEMENT_DAEWOON_BONUS",
    "apply_partner_element_daewoon",
    "hap_overload_damping",
    "natal_hap_count",
    "partner_star_element",
    "produce_female_qisha_seeds",
    "resolve_love_experiments",
]
