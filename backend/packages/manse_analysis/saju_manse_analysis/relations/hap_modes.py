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

# 실험 플래그(2026-10-25 데굴님 "실험 우선") — casebook_replay `--hap-experiment` 로 켜서 85사례
# 적중·방향 오탐을 비교한 뒤에만 기본값을 바꾼다(점수 규칙은 적중률로 ON/OFF).
#   trine_third_clash: 삼합·반합 化 등급에 '제3 글자가 구성 지지를 충'을 방해로 반영(육합 P0-5 와
#     통일). 측정(2026-10-25): pair 33/68·적중 23/44·오탐 8 불변·행 차이 0 → 육합과의 일관성을
#     위해 **기본 ON**.
#   stem_tougan: 천간합 化 확정에 化神 오행의 천간 투출(합 당사자 외)을 요구(투간 조건). 측정 지표
#     불변이나 통설 합의가 약한 추가 조건이라 **기본 OFF** 유지(근거 사례 축적 후 재검토).
HAP_EXPERIMENTS: dict[str, bool] = {"trine_third_clash": True, "stem_tougan": False}

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
    contested_stem: str | None = None  # 쟁합 대상 글자(제3자가 함께 합하려는 쪽)
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


def _contend_dissolved(
    pos_target: str, pos_third: str, target: Stem, third: Stem,
    natal: list[tuple[str, Stem]],
) -> bool:
    """제3 천간의 쟁합 가세가 무효인가 — 격위(비인접)이거나 그 쌍이 간격극으로 차단될 때.

    SPEC §B: "둘 중 하나가 隔位면 쟁투 소멸". 운(luck) 천간은 자리가 없어 소멸 판정을 하지
    않는다(항상 쟁합 가세로 본다 — 종전 동작 유지). **일간이 끼면 소멸하지 않는다** — 일간은
    명식의 주체라 자리와 무관하게 자기 합(본신지합) 상대를 두고 다투는 당사자다(85사례 재생
    2026-10-25: 일간 丙↔연간 辛 격위를 소멸로 보자 丙 세운마다 丙辛合 水(구신) 化 확정이 되어
    CASE-028 방향 오탐 +1 → 일간 예외로 복원).
    """
    if pos_target not in _ORDER or pos_third not in _ORDER:
        return False
    if "day" in (pos_target, pos_third):
        return False
    if abs(_ORDER.index(pos_target) - _ORDER.index(pos_third)) >= 2:
        return True
    return _intervening_control(pos_target, pos_third, target, third, natal)


def _root_count(stem: Stem, pillars: FourPillarsResult) -> int:
    """천간 자기 오행의 지장간 뿌리 개수(본기·중기·여기 불문) — 합거 대상 노트용 비교값."""
    el = STEM_ELEMENT[stem].value
    pillar_list = [pillars.year, pillars.month, pillars.day]
    if pillars.hour is not None:
        pillar_list.append(pillars.hour)
    return sum(1 for p in pillar_list for hs in p.hidden_stems if hs.element == el)


def _weaker_rooted(sa: Stem, sb: Stem, pillars: FourPillarsResult) -> Stem | None:
    """두 천간 중 뿌리가 더 약한 쪽(동률이면 None) — 서술 참고값."""
    ra, rb = _root_count(sa, pillars), _root_count(sb, pillars)
    if ra == rb:
        return None
    return sa if ra < rb else sb


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
        # 2026-10-25(데굴님 승인, SPEC §B "둘 중 하나가 隔位면 쟁투 소멸"): 제3 천간 k 가 다투는
        # 상대와 격위(비인접)이거나 k 쌍 자체가 간격극으로 차단되면 쟁합으로 치지 않는다 —
        # 멀리서 끼어들 수 없는 글자까지 쟁합으로 잡아 등급을 떨어뜨리던 과탐지 교정.
        contested: Stem | None = None
        for k, (pk, sk) in enumerate(all_pos):
            if k in (i, j):
                continue
            for cand, pc in ((sa, pa), (sb, pb)):
                if frozenset({cand, sk}) not in STEM_COMBINATIONS:
                    continue
                if _contend_dissolved(pc, pk, cand, sk, natal):
                    continue
                contested = cand
                break
            if contested is not None:
                break
        contend = contested is not None
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
        # 2026-10-25(데굴님 승인): 격위(비인접)는 化 확정을 막는다 — 통설(천간합은 인접 성립,
        # 사이 글자가 끼면 불성립 또는 약화)·SPEC §B 표와 달리 종전에는 strength 만 깎고 등급은
        # 그대로 두어 年干↔時干 합도 confirmed 가 나왔다. 불성립까지는 학파가 갈려 '약화'로 둔다.
        disturbed = blocked or contend or weakened
        if HAP_EXPERIMENTS["stem_tougan"] and not _transform_stem_exposed(target, (i, j), all_pos):
            disturbed = True  # 化神 투간 없음 — 확정 불가(실험)
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
            else:
                # 2026-10-25(데굴님 승인, 서술 전용): 원국 합반에서 '밀리기 쉬운 쪽' 노트 —
                # 통설(無根 천간이 합거 쪽, 뿌리 약한 쪽이 묶임). direction·affected·점수는 불변.
                weak = _weaker_rooted(sa, sb, pillars)
                if weak is not None:
                    notes.append(
                        f"묶이기 쉬운 쪽(통설·참고): {weak.value} — 뿌리가 약한 글자가 합에 "
                        "끌려가기 쉽다(판정 아님)"
                    )

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
            contested_stem=contested.value if contested is not None else None,
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

    kind: str                      # 'six' | 'three_harmony' | 'half' | 'gonghap' | 'directional'
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


def _third_clash_on(members: list[Branch], all_branches: list[Branch]) -> list[str]:
    """구성 지지를 제3 글자가 충하는 관계 목록('충:寅申') — 삼합·반합 실험(trine_third_clash)."""
    out: list[str] = []
    mem = set(members)
    for m in mem:
        for other in all_branches:
            if other in mem:
                continue
            if frozenset({m, other}) in BRANCH_CLASHES:
                out.append(f"충:{m.value}{other.value}")
    return list(dict.fromkeys(out))


def _transform_stem_exposed(
    target, pair_idx: tuple[int, int], all_pos: list[tuple[str, Stem]],
) -> bool:
    """化神 오행이 합 당사자 외의 천간(원국·운)에 투출했는가 — stem_tougan 실험 조건."""
    return any(
        STEM_ELEMENT[s] == target
        for k, (_pos, s) in enumerate(all_pos) if k not in pair_idx
    )


def _six_disturbing(a: Branch, b: Branch, all_branches: list[Branch]) -> list[str]:
    """육합 두 글자의 化 등급을 실제로 방해하는 관계만.

    ① 제3 글자(원국·운 스택)가 구성원을 충 — '합에 참여한 지지가 충을 받는가'(합·충 경쟁,
       寅亥合 + 申 → 寅申충). ② 완전 삼형(寅巳申 세 글자 동석). 자체 파·해·두 글자 부분형은
       제외(보조 신호). 2026-10-25 데굴님 승인(외부 기준 §5 단계 4·5·6).
    """
    out: list[str] = []
    pair = frozenset({a, b})
    for member in (a, b):
        for other in all_branches:
            if other in pair:
                continue
            if frozenset({member, other}) in BRANCH_CLASHES:
                out.append(f"충:{member.value}{other.value}")
    for trip in PUNISHMENT_TRIPLES:
        if pair <= trip and all(m in all_branches for m in trip):
            out.append("형:" + "".join(m.value for m in trip))
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
        # 2026-10-25(데굴님 승인·외부 기준 「寅亥합·巳申합에서 형·파 중첩」): 두 글자 **자체의**
        # 파(寅亥파·巳申파)는 합을 막는 근거가 약해(삼명통회 파살 4쌍·명리약언 파 배제) 등급에서
        # 뺀다(co_relations 에는 보조 신호로 남긴다). 巳申의 형은 두 글자만으로는 '부분형 후보'라
        # 등급을 막지 않고, 寅까지 동석해 寅巳申 완전형이 될 때만 방해로 본다. 충은 그대로 방해.
        # 종전에는 자체 파·형이 disturbed 라 寅亥·巳申 육합이 영구히 확정 불가였다(결함).
        disturbing = _six_disturbing(ba, bb, [b for _, b in all_pos])
        notes: list[str] = []
        if co and not disturbing:
            notes.append("자체 파·부분형은 보조 신호 — 합 성립을 막지 않음(중복 감점 금지)")
        if any(c.startswith("형:") and len(c) >= 5 for c in disturbing):
            notes.append("寅巳申 완전형 동석 — 형이 합의 안정성을 흔듦(합·형 경쟁)")
        if any(c.startswith("충:") for c in disturbing):
            notes.append("구성 지지가 충을 받음 — 합·충 경쟁(합이 충을 무조건 해소하지 않음)")
        tier, strength = _branch_tier(
            target.value, month_branch, disturbed=bool(disturbing), partial=False)
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
            affected=affected, strength=round(strength, 4), notes=notes,
        ))

    # ── 삼합 / 반합 ─────────────────────────────────────────────
    for members, element, royal in THREE_HARMONY:
        present = [(pos, b) for pos, b in all_pos if b in members]
        kinds = {b for _, b in present}
        if len(kinds) < 2:
            continue
        full = len(kinds) == 3
        co = _co_relations([b for _, b in present])
        if HAP_EXPERIMENTS["trine_third_clash"]:
            co = co + _third_clash_on(
                [b for _, b in present], [b for _, b in all_pos],
            )
        if not full and royal not in kinds:
            # 공합(拱合·가합) — 왕지 없는 생지+고지 2자(申辰·寅戌·巳丑·亥未). 반합이 아니라
            # 그 오행에 '부분 가세(미약)'하는 별도 종류로 기록한다(2026-10-25 데굴님 승인 —
            # 종전엔 여기서 버려져 탐지기와 엔진 불일치(ENGINE_CONFLICT) 격리 상태였다).
            # 化 등급 없음(none)·strength 0.3·점수 반영 없음. 완전한 삼합처럼 계산 금지.
            out.append(BranchHapResolution(
                kind="gonghap",
                members=tuple(dict.fromkeys(b.value for _, b in present)),
                positions=tuple(pos for pos, _ in present),
                transform_element=element.value, role=_role(element.value),
                transform_tier="none", hap_mode="partial",
                luck_origin=any(pos == "luck" for pos, _ in present),
                co_relations=co, royal_included=False, strength=0.3,
                notes=["공합(가합) — 왕지 없음, 합으로 미인정 학파 다수 · 부분 가세(미약)"],
            ))
            continue
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


# ── 화기격(化氣格) 성립 판정 — 정본(2026-10-08 데굴님 결정) ──────────────────────────────
# 판정원은 이 모듈의 천간합 3단계(resolve_stem_hap)다. structure_analysis.TransformationCheck(가중
# 점수)는 일간 무관·지지 충 blocker 를 섞어 사례집 재생에서 ① confirmed 9건 중 1건만 잡고 쟁합
# 사례(獨相作合 위반)를 confirmed 로 잡아 정본으로 쓰지 않는다(HWAGI_REEVALUATION_REVIEW §7).
# 성립 조건(滴天髓 從化論－真): ① 일간 천간합 confirmed(化神 월령 왕·상 ∧ 통근 ∧ 쟁합·간격극 없음)
# ② 원국 합(운 제외) ③ 합 상대가 월간·시간(연간 제외) ④ 투간 인·겁·관 不遇(합 상대 제외) ⑤ 일간 무근
# → 진화(眞化). ①②는 충족하나 ③④⑤ 중 하나라도 어긋나면 가화(假化) 후보(격국 치환·용신 단독 없음).
_HWAGI_BLOCK_TG = frozenset({"비견", "겁재", "정인", "편인", "정관", "편관"})
_HWAGI_NAME = {"木": "화목격", "火": "화화격", "土": "화토격", "金": "화금격", "水": "화수격"}


@dataclass
class HwagiCheck:
    """일간 화기격 판정 1건(원국 전용)."""

    kind: str                        # 'real'(진화) | 'pseudo'(가화)
    target_element: str              # 化神 오행(한자)
    name: str                        # 화토격 등
    pair: tuple[str, str]
    partner_pos: str                 # month/hour(진화 조건) 또는 year
    dm_rooted: bool
    month_or_hour: bool
    blocking_stems: list[str]        # 투간 인·겁·관(합 상대 제외) — "己(편인)" 형식
    reasons: list[str] = field(default_factory=list)


def detect_hwagi(pillars: FourPillarsResult) -> HwagiCheck | None:
    """일간 본신지합의 화기격 성립 판정(정본). 없으면 None, 있으면 진화/가화.

    chart_transform(일간 참여·confirmed·化神 통근)인 원국 합 중 첫 건만 본다(獨相作合 — 두 건이면
    쟁합이라 confirmed 가 될 수 없다).
    """
    day_master = Stem(pillars.day_master)
    stems_by_pos = {
        pos: Stem(getattr(pillars, pos).stem)
        for pos in ("year", "month", "day", "hour") if getattr(pillars, pos) is not None
    }
    for r in resolve_stem_hap(pillars, {}):
        if r.luck_origin or not r.chart_transform or not r.transform_element:
            continue
        if "day" not in r.positions:
            continue
        partner_pos = r.positions[1] if r.positions[0] == "day" else r.positions[0]
        dm_rooted = _rooted(STEM_ELEMENT[day_master].value, pillars)
        month_or_hour = partner_pos in ("month", "hour")
        blocking = [
            f"{st}({ten_god(day_master, st)})"
            for pos, st in stems_by_pos.items()
            if pos not in ("day", partner_pos) and str(ten_god(day_master, st)) in _HWAGI_BLOCK_TG
        ]
        reasons = [f"일간 {day_master.value}+{''.join(r.pair).replace(day_master.value, '')} 합 "
                   f"confirmed → 化神 {r.transform_element}(월령·통근·쟁합 없음)"]
        kind = "real"
        if dm_rooted:
            kind = "pseudo"
            reasons.append("일간 유근 — 가화(假化)")
        if not month_or_hour:
            kind = "pseudo"
            reasons.append(f"합 상대가 {partner_pos}(연간) — 월·시 합이 아니라 가화")
        if blocking:
            kind = "pseudo"
            reasons.append("투간 인·겁·관 " + "·".join(blocking) + " — 不遇 조건 위반, 가화")
        if kind == "real":
            reasons.append("일간 무근·월/시 합·투간 인겁관 없음 — 진화(眞化)")
        return HwagiCheck(
            kind=kind, target_element=r.transform_element,
            name=_HWAGI_NAME.get(r.transform_element, "화기격"), pair=r.pair,
            partner_pos=partner_pos, dm_rooted=dm_rooted, month_or_hour=month_or_hour,
            blocking_stems=blocking, reasons=reasons,
        )
    return None
