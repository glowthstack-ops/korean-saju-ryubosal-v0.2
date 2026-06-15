"""천간합(天干合) 작용 모드 판정 — Phase 1 (HAP_INTERACTION_SPEC B·C·D 구현).

manse_core relations는 합 '성립'과 化神 후보(transform_element)만 기록한다(수정 금지). 이 어댑터는
그 위에 **작용 모드**(합화/합반/합거/쟁투)와 **化 3단계 등급**, **용기신 길흉**을 얹는 순수 함수다.

판정 흐름(스펙 §B·C·D):
  1. 성립 후보(천간합 5종) 탐지 → 2. B 게이트(간격극=차단 / 隔位=약화 / 쟁투) →
  3. C-1 化 3단계(化神 월령 season_state + 통근 + 방해) →
  4. 모드 분기(化 confirmed→합화 / 일간 자합→본신지합 / 그 외→합반+합거 효과) →
  5. 용기신 길흉(기·구신 묶임=boon, 용·희신 묶임=harm).

정책(스펙 §0, 2026-06-15 사용자 확정): 化 3단계 확률화, 일간 자합은 합거·기반으로 치지 않음,
다수설 우선. 정량 가중치는 보수 기본값(# CALIBRATE) — 전문가 감수·캘리브레이션 대상.

배선(점수·그래프·LLM)은 Phase 2. 본 모듈은 판정 결과(StemHapResolution)만 산출한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from saju_shared_types.constants import (
    BRANCH_BREAKS,
    BRANCH_CLASHES,
    BRANCH_HARMS,
    CONTROLS,
    DIRECTIONAL_COMBINATIONS,
    PUNISHMENT_MUTUAL,
    PUNISHMENT_TRIPLES,
    SIX_COMBINATIONS,
    STEM_COMBINATIONS,
    STEM_ELEMENT,
    THREE_HARMONY,
    main_hidden_stem,
    season_state,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.pillars import FourPillarsResult

# 원국 자리 순서(인접 판정용). 운(運) 천간은 위치 무관이라 별도.
_ORDER = ("year", "month", "day", "hour")
# 묶임이 길(boon)/흉(harm)으로 작용하는 용기신 역할.
_HARM_WHEN_BOUND = {"용신", "희신"}
_BOON_WHEN_BOUND = {"기신", "구신"}

# CALIBRATE: 정량 가중치 보수 기본값(스펙 §0·G — 전문가 감수·캘리브레이션 전 잠정).
HAP_WEIGHTS: dict[str, float] = {
    "bind_penalty": 0.5,     # 합반 시 묶인 글자의 기여 감산 비율
    "remove_penalty": 1.0,   # 합거 시 해당 십성 제거 정도(1.0=완전 제거)
    "geokwi_strength": 0.3,  # 隔位(비인접) 합 약화 후 잔존 비율(子平真詮 '2~3할')
    "contend_strength": 0.5, # 쟁합·투합 시 합력 약화 비율
}


@dataclass
class AffectedGod:
    """합에 묶인 천간 1개와 그 길흉(일간 기준)."""

    stem: str       # 천간(한자)
    ten_god: str    # 일간 기준 십성
    element: str    # 오행(한자)
    role: str       # 용신/희신/기신/구신/한신 또는 '' (favorability 미상)
    effect: str     # 'boon' | 'harm' | 'neutral' — 묶임/제거의 길흉


@dataclass
class StemHapResolution:
    """천간합 1건의 작용 모드 판정 결과."""

    pair: tuple[str, str]            # 합한 두 천간(한자)
    positions: tuple[str, str]       # 자리(year/month/day/hour/luck)
    transform_element: str | None    # 化神 오행(한자)
    transform_tier: str              # 'confirmed' | 'conditional' | 'none'
    hap_mode: str                    # 'transform'|'bind'|'combine_self'|'blocked'
    direction: str | None = None     # 'away'(합거) | 'toward'(합래) | None
    luck_origin: bool = False        # 운(運) 천간이 관여한 합인가
    blocked: bool = False            # B 차단(실질 미작용)
    block_reason: str | None = None  # '간격극' | None
    weakened: bool = False           # 隔位(비인접) 약화
    contend: bool = False            # 쟁합·투합
    chart_transform: bool = False    # 일간 화기격(化氣格) 후보 — 일간이 化神으로 化
    strength: float = 1.0            # 합력(약화 반영, 0~1) — CALIBRATE
    affected: list[AffectedGod] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _natal_stems(pillars: FourPillarsResult) -> list[tuple[str, Stem]]:
    """원국 천간을 (자리, Stem)로. 시주 없으면 3주."""
    items = [("year", pillars.year), ("month", pillars.month), ("day", pillars.day)]
    if pillars.hour is not None:
        items.append(("hour", pillars.hour))
    return [(pos, Stem(p.stem)) for pos, p in items]


def _rooted(element_hanja: str, pillars: FourPillarsResult) -> bool:
    """化神 오행이 어느 지지의 지장간에 통근(뿌리)하는가."""
    pillar_list = [pillars.year, pillars.month, pillars.day]
    if pillars.hour is not None:
        pillar_list.append(pillars.hour)
    return any(
        hs.element == element_hanja
        for p in pillar_list
        for hs in p.hidden_stems
    )


def _intervening_control(
    pos_a: str, pos_b: str, sa: Stem, sb: Stem, natal: list[tuple[str, Stem]]
) -> bool:
    """두 자리 사이에 합 글자를 극(剋)하는 천간이 끼었는가(간격극 → 합 차단)."""
    if pos_a not in _ORDER or pos_b not in _ORDER:
        return False
    ia, ib = _ORDER.index(pos_a), _ORDER.index(pos_b)
    lo, hi = sorted((ia, ib))
    if hi - lo < 2:  # 인접 — 사이 자리 없음
        return False
    targets = {STEM_ELEMENT[sa], STEM_ELEMENT[sb]}
    for pos, stem in natal:
        if pos in _ORDER and lo < _ORDER.index(pos) < hi:
            if CONTROLS[STEM_ELEMENT[stem]] in targets:  # 사이 글자가 합 글자를 극
                return True
    return False


def _affected(stem: Stem, day_master: Stem, favorability: dict[str, str],
              effect: str | None = None) -> AffectedGod:
    """묶인 천간 1개 → 십성·오행·역할·길흉."""
    element = STEM_ELEMENT[stem].value
    role = favorability.get(element, "")
    if effect is None:
        if role in _BOON_WHEN_BOUND:
            effect = "boon"   # 기·구신 묶임 = 흉 제거(길)
        elif role in _HARM_WHEN_BOUND:
            effect = "harm"   # 용·희신 묶임 = 길 상실(흉)
        else:
            effect = "neutral"
    return AffectedGod(
        stem=stem.value, ten_god=str(ten_god(day_master, stem)),
        element=element, role=role, effect=effect,
    )


def resolve_stem_hap(
    pillars: FourPillarsResult,
    favorability: dict[str, str],
    *,
    luck_stems: list[str] | None = None,
    weights: dict[str, float] | None = None,
) -> list[StemHapResolution]:
    """천간합의 작용 모드를 판정한다(원국 + 선택적 운 천간).

    Args:
        pillars: 원국 4주.
        favorability: 오행(한자)→용기신 역할(`favorability_map` 산출).
        luck_stems: 운(대운·세운·월운) 천간 한자 목록(있으면 원국과의 합도 판정).
        weights: 정량 가중치 override(미지정 시 보수 기본값 `HAP_WEIGHTS`).

    Returns:
        StemHapResolution 목록(합 1건당 1개).
    """
    w = weights or HAP_WEIGHTS
    day_master = Stem(pillars.day_master)
    month_branch = Branch(pillars.month.branch)
    natal = _natal_stems(pillars)
    luck = [("luck", Stem(s)) for s in (luck_stems or [])]
    all_pos = natal + luck

    out: list[StemHapResolution] = []
    for (i, (pa, sa)), (j, (pb, sb)) in combinations(enumerate(all_pos), 2):
        if sa == sb:
            continue
        target = STEM_COMBINATIONS.get(frozenset({sa, sb}))
        if target is None:
            continue

        luck_origin = "luck" in (pa, pb)
        both_natal = not luck_origin
        notes: list[str] = []

        # ── B 게이트 ──────────────────────────────────────────────
        blocked = both_natal and _intervening_control(pa, pb, sa, sb, natal)
        block_reason = "간격극" if blocked else None
        weakened = (
            both_natal and not blocked
            and pa in _ORDER and pb in _ORDER
            and abs(_ORDER.index(pa) - _ORDER.index(pb)) >= 2
        )
        # 쟁합·투합: 이 쌍(i,j) 밖의 제3 천간이 sa·sb 중 하나와 또 합하는가(위치 기준).
        contend = any(
            k not in (i, j) and (
                frozenset({sa, sk}) in STEM_COMBINATIONS
                or frozenset({sb, sk}) in STEM_COMBINATIONS
            )
            for k, (_, sk) in enumerate(all_pos)
        )
        strength = 1.0
        if weakened:
            strength *= w["geokwi_strength"]
            notes.append("隔位(비인접) — 합력 약화(2~3할)")
        if contend:
            strength *= w["contend_strength"]
            notes.append("쟁합·투합 — 정(情)이 전일하지 못함")

        # ── C-1 化 3단계 ─────────────────────────────────────────
        season = season_state(target, month_branch)  # wang/xiang/xiu/qiu/si
        rooted = _rooted(target.value, pillars)
        disturbed = blocked or contend
        if season in ("wang", "xiang") and rooted and not disturbed:
            tier = "confirmed"
        elif season in ("qiu", "si") or blocked:
            tier = "none"
        else:
            tier = "conditional"

        # ── 모드 분기(§C) ───────────────────────────────────────
        # 본신지합은 '일주(日) 자리' 천간일 때만 — 같은 글자라도 다른 자리(비견 등)는 합거/합반.
        involves_dm = "day" in (pa, pb)
        direction: str | None = None
        chart_transform = False
        affected: list[AffectedGod] = []

        if blocked:
            hap_mode = "blocked"
            tier = "none"
            notes.append("간격극 — 합 불성립(사이 글자가 극)")
        elif involves_dm:
            # 일간 본신지합 — 합거·기반 아님(정책). 일간 아닌 쪽이 십성.
            hap_mode = "combine_self"
            other = sb if pa == "day" else sa
            affected = [_affected(other, day_master, favorability, effect="neutral")]
            notes.append("일간 본신지합 — 합거·기반 아님(십성 그대로 사용)")
            if tier == "confirmed":
                # 化氣格 후보: 化神 통근 + 일간 무근이면 진화(眞化), 일간 유근이면 가화(假化).
                dm_rooted = _rooted(STEM_ELEMENT[day_master].value, pillars)
                chart_transform = _rooted(target.value, pillars)
                if chart_transform:
                    notes.append(
                        f"化氣格 후보 — 일간 {day_master.value}이 化神 {target.value}으로 化"
                        + ("(가화: 일간 유근)" if dm_rooted else "(진화: 일간 무근)")
                    )
        elif tier == "confirmed":
            hap_mode = "transform"
            role = favorability.get(target.value, "역할 미상")
            notes.append(f"합화 {target.value}({role}) — 化神 오행으로 작용")
            affected = [
                _affected(sa, day_master, favorability, effect="neutral"),
                _affected(sb, day_master, favorability, effect="neutral"),
            ]
        else:
            # 성립하나 化 실패 → 합반(묶임) + 각 글자 합거 효과.
            hap_mode = "bind"
            affected = [
                _affected(sa, day_master, favorability),
                _affected(sb, day_master, favorability),
            ]
            if luck_origin:
                # 운 글자가 원국 글자를 합거(보냄) + 운 글자의 십성을 합래(데려옴).
                direction = "away"
                notes.append("운(運) 합 — 원국 글자 합거 / 운 글자 합래")

        out.append(StemHapResolution(
            pair=(sa.value, sb.value),
            positions=(pa, pb),
            transform_element=target.value,
            transform_tier=tier,
            hap_mode=hap_mode,
            direction=direction,
            luck_origin=luck_origin,
            blocked=blocked,
            block_reason=block_reason,
            weakened=weakened,
            contend=contend,
            chart_transform=chart_transform,
            strength=round(strength, 4),
            affected=affected,
            notes=notes,
        ))
    return out


# ─── 지지합(六合·三合·方合) Phase 3 ──────────────────────────────


@dataclass
class BranchHapResolution:
    """지지합 1건의 작용 모드 판정 결과(육합/삼합/방합/반합)."""

    kind: str                      # 'six' | 'three_harmony' | 'half' | 'directional'
    members: tuple[str, ...]       # 지지(한자)
    positions: tuple[str, ...]     # 자리(year/month/day/hour/luck)
    transform_element: str | None  # 化神/局 오행(한자)
    role: str                      # 化神/局 favorability 역할
    transform_tier: str            # 'confirmed' | 'conditional' | 'none'
    hap_mode: str                  # 'transform'|'bind'|'strengthen'|'partial'
    luck_origin: bool = False
    direction: str | None = None   # 'away'(합거) | None — 운이 원국 지지를 합거
    co_relations: list[str] = field(default_factory=list)  # 동시 충/형/파/해
    royal_included: bool = False   # 삼합 반합 왕지(子午卯酉) 포함
    # 육합 합반/합거로 묶인 지지의 정기(正氣) 십성 길흉(지장간 본기 기준).
    affected: list[AffectedGod] = field(default_factory=list)
    strength: float = 1.0          # 합력(0~1) — CALIBRATE
    notes: list[str] = field(default_factory=list)


def _co_relations(members: list[Branch]) -> list[str]:
    """결합 지지들 사이에 동시 성립하는 충/형/파/해(HAP_INTERACTION_SPEC §D-2)."""
    uniq = list(dict.fromkeys(members))
    out: list[str] = []
    for a, b in combinations(uniq, 2):
        pair = frozenset({a, b})
        if pair in BRANCH_CLASHES:
            out.append(f"충:{a.value}{b.value}")
        if pair in BRANCH_BREAKS:
            out.append(f"파:{a.value}{b.value}")
        if pair in BRANCH_HARMS:
            out.append(f"해:{a.value}{b.value}")
        if pair in PUNISHMENT_MUTUAL:
            out.append(f"형:{a.value}{b.value}")
    for trip in PUNISHMENT_TRIPLES:  # 삼형 부분 성립(2자 이상 동석)
        present = [m for m in uniq if m in trip]
        if len(present) >= 2:
            out.append("형:" + "".join(m.value for m in present))
    return list(dict.fromkeys(out))


def _branch_tier(target_element_value: str, month_branch: Branch,
                 *, disturbed: bool, partial: bool) -> tuple[str, float]:
    """化神/局 오행의 월령·방해·완전성으로 化 등급과 합력 산정(지지합은 보수적)."""
    from saju_shared_types.enums import Element
    season = season_state(Element(target_element_value), month_branch)
    if season in ("wang", "xiang") and not disturbed and not partial:
        return "confirmed", 1.0
    if season in ("qiu", "si") or disturbed:
        return "none", 0.4 if partial else 0.6
    return "conditional", 0.6 if partial else 0.8


def resolve_branch_hap(
    pillars: FourPillarsResult,
    favorability: dict[str, str],
    *,
    luck_branches: list[str] | None = None,
) -> list[BranchHapResolution]:
    """지지합(육합/삼합/방합/반합)의 작용 모드를 판정한다(원국 + 선택적 운 지지).

    육합: 化神 월령으로 합화/합반(지지는 보수적 — 묶임 경향). 삼합/방합: 완전 局(3자) vs
    반합(2자·왕지). 결합 지지 사이의 동시 충/형/파/해를 co_relations로 표기(§D-2).
    """
    if pillars.month is None:
        return []
    day_master = Stem(pillars.day_master)
    month_branch = Branch(pillars.month.branch)
    natal = [(pos, Branch(getattr(pillars, pos).branch))
             for pos in _ORDER if getattr(pillars, pos, None) is not None]
    luck = [("luck", Branch(b)) for b in (luck_branches or [])]
    all_pos = natal + luck

    out: list[BranchHapResolution] = []

    def _role(el: str) -> str:
        return favorability.get(el, "역할 미상")

    # ── 육합 ────────────────────────────────────────────────────
    for (pa, ba), (pb, bb) in combinations(all_pos, 2):
        if ba == bb:
            continue
        target = SIX_COMBINATIONS.get(frozenset({ba, bb}))
        if target is None:
            continue
        co = _co_relations([ba, bb])
        tier, strength = _branch_tier(
            target.value, month_branch, disturbed=bool(co), partial=False)
        luck_origin = "luck" in (pa, pb)
        affected: list[AffectedGod] = []
        direction: str | None = None
        if tier != "confirmed":  # 합반/합거 — 묶인 지지 정기 십성 길흉
            affected = [
                _affected(main_hidden_stem(ba), day_master, favorability),
                _affected(main_hidden_stem(bb), day_master, favorability),
            ]
            if luck_origin:
                direction = "away"  # 운 지지가 원국 지지를 합거(묶음)
        out.append(BranchHapResolution(
            kind="six", members=(ba.value, bb.value), positions=(pa, pb),
            transform_element=target.value, role=_role(target.value),
            transform_tier=tier,
            hap_mode="transform" if tier == "confirmed" else "bind",
            luck_origin=luck_origin, direction=direction, co_relations=co,
            affected=affected, strength=round(strength, 4),
        ))

    # ── 삼합 / 반합 ─────────────────────────────────────────────
    for members, element, royal in THREE_HARMONY:
        present = [(pos, b) for pos, b in all_pos if b in members]
        kinds = {b for _, b in present}
        if len(kinds) < 2:
            continue
        full = len(kinds) == 3
        if not full and royal not in kinds:
            continue  # 반합은 왕지 포함만(다수설)
        co = _co_relations([b for _, b in present])
        tier, strength = _branch_tier(
            element.value, month_branch, disturbed=bool(co), partial=not full)
        out.append(BranchHapResolution(
            kind="three_harmony" if full else "half",
            members=tuple(dict.fromkeys(b.value for _, b in present)),
            positions=tuple(pos for pos, _ in present),
            transform_element=element.value, role=_role(element.value),
            transform_tier=tier,
            hap_mode="transform" if full else "partial",
            luck_origin=any(pos == "luck" for pos, _ in present),
            co_relations=co, royal_included=royal in kinds,
            strength=round(strength if full else strength * 0.7, 4),
        ))

    # ── 방합 ────────────────────────────────────────────────────
    for members, element in DIRECTIONAL_COMBINATIONS:
        present = [(pos, b) for pos, b in all_pos if b in members]
        kinds = {b for _, b in present}
        if len(kinds) < 2:
            continue
        full = len(kinds) == 3
        co = _co_relations([b for _, b in present])
        out.append(BranchHapResolution(
            kind="directional",
            members=tuple(dict.fromkeys(b.value for _, b in present)),
            positions=tuple(pos for pos, _ in present),
            transform_element=element.value, role=_role(element.value),
            transform_tier="confirmed" if full else "conditional",
            hap_mode="strengthen" if full else "partial",
            luck_origin=any(pos == "luck" for pos, _ in present),
            co_relations=co,
            strength=round(1.0 if full else 0.6, 4),
            notes=["방합 — 기존 오행 강화(변화 아님)"],
        ))
    return out
