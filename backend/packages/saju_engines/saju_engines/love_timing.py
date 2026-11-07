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
    # 결혼운 강의 7편(2026-11-07, EXTERNAL_TEXT_GAP_MARRIAGE_TIMING_LECTURES §3 P1) — 데굴님
    # "ON으로 시작": 기본 ON, 끄려면 `SAJU_LOVE_EXPERIMENTS_OFF` 에 이름을 적는다.
    "partner_star_hap_confluence",
    "female_officer_resource",
    "male_peer_breaks_wealth",
    "month_clash_partner_tag",
)
#: 기본 ON 실험(2026-11-07) — 측정 전이라도 노출해야 실답 감수가 된다(데굴님 원칙).
LOVE_DEFAULT_ON: frozenset[str] = frozenset({
    "partner_star_hap_confluence",
    "female_officer_resource",
    "male_peer_breaks_wealth",
    "month_clash_partner_tag",
})
_ENV = "SAJU_LOVE_EXPERIMENTS"  # 쉼표 구분 이름 목록 — 운영 기본은 비움(전부 OFF)
_ENV_OFF = "SAJU_LOVE_EXPERIMENTS_OFF"  # 기본 ON 실험을 끄는 이름 목록(쉼표)
#: 배우자성 운 × 배우자궁 합 동반(P1-1) — 결혼 신호 배율.
PARTNER_HAP_CONFLUENCE_MULT = 1.15
#: 여성 관인상생(P1-2) — 관성 있고 인성 없는 명식의 인성 운 시드.
FEMALE_OFFICER_RESOURCE_MARRIAGE = 26
FEMALE_OFFICER_RESOURCE_NEW_RELATIONSHIP = 22
#: 남성 비겁 운(P1-3) — 재성 있는 명식의 세운·월운 비겁 → 관계 변동 시드.
MALE_PEER_BREAKS_WEALTH_SCORE = 24

#: 여성 편관 운 시드 점수 — 남성 편재 단일 운(new_relationship 30)과 대칭(데굴님 "권유대로").
FEMALE_QISHA_NEW_RELATIONSHIP = 28
FEMALE_QISHA_RELATIONSHIP_CHANGE = 24
#: 원국 합 과다 감쇠 — 합 관계 수 임계와 배율.
HAP_OVERLOAD_THRESHOLD = 3
HAP_OVERLOAD_MULT = 0.7
#: 배우자성 오행 대운 배경 가산.
PARTNER_ELEMENT_DAEWOON_BONUS = 6


def resolve_love_experiments(
    names: Collection[str] | None = None, *, off: Collection[str] | None = None,
) -> dict[str, bool]:
    """실험 플래그 dict — 인자가 None 이면 환경변수 `SAJU_LOVE_EXPERIMENTS`(쉼표)에서 읽는다.

    기본 ON 실험(`LOVE_DEFAULT_ON`)은 `off`(또는 `SAJU_LOVE_EXPERIMENTS_OFF`)에 적힌 것만 꺼진다.
    """
    if names is None:
        raw = os.environ.get(_ENV, "")
        names = [x.strip() for x in raw.split(",") if x.strip()]
    if off is None:
        raw_off = os.environ.get(_ENV_OFF, "")
        off = [x.strip() for x in raw_off.split(",") if x.strip()]
    unknown = sorted((set(names) | set(off)) - set(LOVE_EXPERIMENT_KEYS))
    if unknown:
        raise ValueError(f"알 수 없는 연애운 실험 플래그: {unknown}")
    on = set(names) | (LOVE_DEFAULT_ON - set(off))
    return {k: (k in on) for k in LOVE_EXPERIMENT_KEYS}


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


# ── 결혼운 강의 7편(2026-11-07) P1 실험 4종 ──────────────────────────────────
_WEALTH_TOKENS = ("ZHENGCAI", "PIANCAI", "WEALTH")
_OFFICER_TOKENS = ("ZHENGGUAN", "QISHA", "AUTHORITY")
_RESOURCE_GODS = (TenGod.JEONGIN, TenGod.PYEONIN)
_PEER_GODS = (TenGod.BIGYEON, TenGod.GEOMJAE)


def _has_partner_star_code(codes: str, gender: str) -> bool:
    """후보 근거코드에 성별 기준 배우자성 운(남=재성·여=관성) 구동 코드가 있는지."""
    tokens = _WEALTH_TOKENS if gender == "male" else _OFFICER_TOKENS if gender == "female" else ()
    return any(t in codes for t in tokens)


def apply_partner_star_hap_confluence(
    cands: list[EventCandidateV2], gender: str,
) -> list[EventCandidateV2]:
    """배우자성 운 + 배우자궁(일지) 합이 같은 기간에 겹치면 결혼 신호 ×1.15(P1-1).

    강의(2011 논문·임상): 재성(남)/관성(여) 운이 **원국과 합**할 때 결혼이 많다. 천간합은 이미
    `SAME_GOD_HAP_*` +2 로 잡히지만 일지 합과의 동반은 가산만 되고 합류 가중이 없었다.
    """
    if gender not in ("male", "female"):
        return cands
    out: list[EventCandidateV2] = []
    for c in cands:
        codes = " ".join(c.reason_codes)
        if (
            c.event_key is not EventKeyV2.MARRIAGE_SIGNAL
            or "LOVE_PARTNER_HAP_CONFLUENCE" in codes
            or "REL_HAP_day_pillar" not in codes
            or not _has_partner_star_code(codes, gender)
        ):
            out.append(c)
            continue
        new_score = min(100, round(c.score * PARTNER_HAP_CONFLUENCE_MULT))
        out.append(c.model_copy(update={  # provenance-audit: not-risk (EventCandidateV2)
            "score": new_score,
            "reason_codes": [*c.reason_codes, "LOVE_PARTNER_HAP_CONFLUENCE"],
            "contributions": {
                **c.contributions, "partner_hap_confluence": float(new_score - c.score),
            },
        }))
    return out


def _visible_gods(result: ManseV2Result) -> set[str]:
    """원국 가시 십성(천간 + 지지 본기)."""
    p = result.pillars
    if p is None:
        return set()
    return {
        g for pillar in (p.year, p.month, p.day, p.hour) if pillar is not None
        for g in (pillar.stem_ten_god, pillar.branch_main_ten_god) if g
    }


def produce_female_officer_resource_seeds(
    signals: list,
    target_layer: LuckLayer,
    result: ManseV2Result,
    gender: str,
    period: str,
) -> list[EventCandidateV2]:
    """여성 관인상생(P1-2): 원국에 관성은 있고 인성이 없을 때 인성 운(대운·세운) → 결혼·새 인연
    시드.

    강의(임상): 관(남자)이 인성을 타고 들어온다 — '사랑받는' 결. 인성이 이미 많으면 관설이라 제외.
    """
    if gender != "female" or result.pillars is None:
        return []
    if target_layer not in (LuckLayer.DAEWOON, LuckLayer.SEWOON):
        return []
    gods = _visible_gods(result)
    if not gods & {"정관", "편관"} or gods & {"정인", "편인"}:
        return []
    hits = [s for s in signals if s.layer is target_layer and s.ten_god in _RESOURCE_GODS]
    if not hits:
        return []
    out: list[EventCandidateV2] = []
    for event, score in (
        (EventKeyV2.MARRIAGE_SIGNAL, FEMALE_OFFICER_RESOURCE_MARRIAGE),
        (EventKeyV2.NEW_RELATIONSHIP, FEMALE_OFFICER_RESOURCE_NEW_RELATIONSHIP),
    ):
        out.append(EventCandidateV2(
            event_key=event,
            period=period,
            score=score,
            confidence_level=ConfidenceLevel.WEAK_EVENT_CANDIDATE,
            polarity_role=PolarityRole.NEUTRAL,
            source_layers=[target_layer],
            candidate_source_layers=[target_layer.value],
            source_ten_gods=[TenGodCode.ZHENGYIN],
            reason_codes=["LOVE_FEMALE_OFFICER_RESOURCE"],
            contributions={"base": float(score)},
        ))
    return out


def produce_male_peer_breaks_wealth_seeds(
    signals: list,
    target_layer: LuckLayer,
    result: ManseV2Result,
    gender: str,
    period: str,
) -> list[EventCandidateV2]:
    """남성 비겁 운(P1-3): 원국에 재성이 있을 때 세운·월운 비겁 → 관계 변동 시드(결렬 단정 아님).

    강의(강의체·효도명리 통설): 남자는 비겁 운(겁재)에 재성=배우자가 흔들려 하려던 결혼도 깨질 수
    있다. 군겁쟁재 구조와 같은 원리 — 시드는 '관계 조율이 흔들리기 쉬운 때'로만 쓴다.
    """
    if gender != "male" or result.pillars is None:
        return []
    if target_layer not in (LuckLayer.SEWOON, LuckLayer.WOLWOON):
        return []
    if not _visible_gods(result) & {"정재", "편재"}:
        return []
    hits = [s for s in signals if s.layer is target_layer and s.ten_god in _PEER_GODS]
    if not hits:
        return []
    codes = ["LOVE_MALE_PEER_BREAKS_WEALTH"]
    if any(s.ten_god is TenGod.GEOMJAE for s in hits):
        codes.append("LOVE_PEER_JIECAI")
    return [EventCandidateV2(
        event_key=EventKeyV2.RELATIONSHIP_CHANGE,
        period=period,
        score=MALE_PEER_BREAKS_WEALTH_SCORE,
        confidence_level=ConfidenceLevel.WEAK_EVENT_CANDIDATE,
        polarity_role=PolarityRole.NEUTRAL,
        source_layers=[target_layer],
        candidate_source_layers=[target_layer.value],
        source_ten_gods=[TenGodCode.JIECAI],
        reason_codes=codes,
        contributions={"base": float(MALE_PEER_BREAKS_WEALTH_SCORE)},
    )]


def apply_month_clash_partner_tag(
    cands: list[EventCandidateV2], gender: str,
) -> list[EventCandidateV2]:
    """월지 충 + 배우자성 운 동반 → 결혼·새 인연 후보에 '환경 급변 동반' 태그(P1-4, 점수 0).

    강의(강의체·Q&A): 월지(직장·환경)가 충하는 해에 직장을 그만두며 갑작스럽게 결혼하기도 한다.
    점수는 바꾸지 않고 서술 재료로만 남긴다.
    """
    if gender not in ("male", "female"):
        return cands
    out: list[EventCandidateV2] = []
    for c in cands:
        codes = " ".join(c.reason_codes)
        if (
            c.event_key not in (EventKeyV2.MARRIAGE_SIGNAL, EventKeyV2.NEW_RELATIONSHIP)
            or "LOVE_MONTH_CLASH_ENV_SHIFT" in codes
            or "REL_CHUNG_month_pillar" not in codes
            or not _has_partner_star_code(codes, gender)
        ):
            out.append(c)
            continue
        out.append(c.model_copy(update={  # provenance-audit: not-risk (EventCandidateV2)
            "reason_codes": [*c.reason_codes, "LOVE_MONTH_CLASH_ENV_SHIFT"],
        }))
    return out


__all__ = [
    "FEMALE_OFFICER_RESOURCE_MARRIAGE",
    "FEMALE_OFFICER_RESOURCE_NEW_RELATIONSHIP",
    "LOVE_DEFAULT_ON",
    "MALE_PEER_BREAKS_WEALTH_SCORE",
    "PARTNER_HAP_CONFLUENCE_MULT",
    "apply_month_clash_partner_tag",
    "apply_partner_star_hap_confluence",
    "produce_female_officer_resource_seeds",
    "produce_male_peer_breaks_wealth_seeds",
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
