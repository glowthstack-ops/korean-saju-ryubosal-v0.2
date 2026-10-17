"""운 적용 구조 상태(F8-P1, 2026-10-17 데굴님 승인) — 원국 구조 배합이 운에서 어떻게 변하는가.

SSOT: `doc/v2_2/PATTERN_TRANSIT_STATES.md` §2. 외부 검토 글 2편(재다신약 운 변화·4조합 운 변화)을
계산 가능한 규칙으로 번역한 층이다.

원칙(불변):
- **성립 ≠ 길흉.** 상태(신규 성립·강화·완화·해소)는 구조 작동의 변화일 뿐 유불리가 아니다.
  `favorability` 를 만들지 않고 점수·용신·신강약에 관여하지 않는다(inert).
- **구조 성립과 현재 작동을 분리한다.** `natal_established` 는 원국 감지(P0 포함)로 고정하고,
  `operating` 은 운 스택(원국+대운 → +세운 → +월운)을 누적 적용한 세력으로 층마다 판정한다.
- **월운 층은 '해소'를 쓰지 않는다**(최대 '완화' = 일시 차단). 해소는 대운·세운 층에서만.
- **변화는 원국 구조를 바탕으로만 진행한다**(2026-10-17 데굴님 검수). 신규 성립은 패턴별
  **원국 전제**(`_natal_prereq`: 신강·격국·과다·파격 파생 전제, 또는 두 다리 중 하나의 원국
  존재)를 통과한 패턴만, 해소는 원국 성립 패턴만. 운만으로 생겼던 상태의 소멸은 줄을 내지 않는다.
- **시주 미상은 계산하지 않는다**(HOUR_UNKNOWN_POLICY §8). 일운은 범위 밖.
- 운 적용 세력은 신강약 재판정이 아니다. 원국 `effective_percent`(지장간·월령·투간·공망 반영)를
  기준으로 운 글자를 **표시 분포와 같은 자리 가중치의 평균**(천간 10·지지 17.5 단위, 원국 합 100)
  으로 더하고, 합반(×0.5)·합거(제거)·합화(化 오행 전환)·충(원국 지지 ×0.7)을 반영해 재정규화한다.
  운 기둥 1개의 단위 무게는 층(대운·세운·월운)에 관계없이 같다 — 층 차이는 '누적 범위'로만 드러난다.
- 임계는 전부 기존 값 재사용: 억부 6종은 P0(`_p0_effective_ok`), T1/T2 10%·20%, 세력 변화 ±5%p,
  T4 균형 구간 8~40%·비율 0.5~2.0, T5 金 15%·水<火. 문구는 사전(`pattern_transit_text.json`) 치환만.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from saju_manse_analysis._chart import DIST_BRANCH_WEIGHT, DIST_STEM_WEIGHT
from saju_manse_analysis.distribution.ten_god_distribution import GROUPS as _TG_GROUPS

from saju_shared_types.constants import (
    BRANCH_CLASHES,
    STEM_ELEMENT,
    group_elements,
    hidden_stems_for,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.relation_semantics import BindingState, TransformationState
from saju_shared_types.structure_patterns import (
    DetectedPattern,
    PatternState,
    PatternTimeline,
    PatternTimelineCell,
    PatternTimelineRow,
    PatternTransitStatus,
    PatternTransitType,
)

from .pattern_conditions import (
    T1_PATHS,
    T2_CONTROLS,
    ConditionInput,
    evaluate_condition,
)
from .relation_semantics import collect_luck_relation_semantics
from .structure_patterns import (
    _P0_MAIN_GROUP,
    _STRONG_BANDS,
    _p0_effective_ok,
    load_structure_patterns,
)

#: 층 이름(스택 순서). 일운은 범위 밖(T2 플래그만 — SSOT §0).
LAYERS: tuple[str, ...] = ("daewoon", "year", "month")
WEAK_BANDS_FOR_TEST = frozenset({"신약", "태신약", "중화신약"})

# ── 임계(전부 기존 값 재사용) ───────────────────────────────────────────────
_MIN_PRESENCE = 10.0  # T1 경로 양단 최소 세력(%) — 구조 패턴 사전 '존재' 임계와 동일
_MIN_CONTROLLED = 20.0  # T2 피제어자 최소 세력(%)
_DELTA = 5.0  # 강화·완화 판정 세력 변화(%p)
_BALANCE_LO, _BALANCE_HI = 8.0, 40.0  # T4 균형 구간(%)
_BALANCE_RATIO = 2.0  # T4 비율 상한(하한 = 1/2)
_BALANCE_BROKEN = 3.0  # T4 중단 비율
_T5_STRENGTH = 15.0  # T5 제련 대상 오행 최소 세력(%)
#: 재다신약 감당 능력에서 인성을 제외하는 재극인 비율 — 용신 모듈 `_jaeda_sinyak`(재 > 인×3) 재사용.
_JAEDA_RESOURCE_RATIO = 3.0
#: 감당 능력 모델을 쓰는 억부 패턴(압력 그룹 > 일간 측 유효 세력일 때만 '작동'). 인다신약·군겁쟁재·
#: 비겁탈재는 '과다 자체'가 구조라 비율 규칙(P0) 그대로.
_T3_CAPACITY: dict[str, str] = {
    "JAEDA_SINYAK": "wealth", "GWANDA_SINYAK": "officer", "SEOLGI_TAEGWA": "output",
}
_LUCK_STEM_UNITS = sum(DIST_STEM_WEIGHT.values()) / len(DIST_STEM_WEIGHT)  # 10
_LUCK_BRANCH_UNITS = sum(DIST_BRANCH_WEIGHT.values()) / len(DIST_BRANCH_WEIGHT)  # 17.5
_BOUND_FACTOR = 0.5
_CLASH_FACTOR = 0.7

#: 십성 그룹을 극하는 그룹(비겁剋재·재剋인·인剋식상·식상剋관·관剋비겁).
_CONTROLLER_OF: dict[str, str] = {
    "wealth": "peer",
    "resource": "wealth",
    "output": "resource",
    "officer": "output",
    "peer": "officer",
}
_GROUP_OF: dict[str, str] = {tg: g for g, members in _TG_GROUPS.items() for tg in members}
_PEER = list(_TG_GROUPS["peer"])
_RESOURCE = list(_TG_GROUPS["resource"])
_OUTPUT = list(_TG_GROUPS["output"])
_WEALTH = list(_TG_GROUPS["wealth"])
_OFFICER = list(_TG_GROUPS["officer"])

# ── 패턴 카탈로그(판정 유형별 역할) — 사전 family 와 1:1 ─────────────────────
#: T1 생극 경로·T2 제어 배합의 역할 표는 성립 조건 SSOT(pattern_conditions)에서 가져온다.
_T1_PATHS: dict[str, tuple[list[str], list[str], str | None]] = {
    pid: (a, b, None) for pid, (a, b, _gate) in T1_PATHS.items()
}
_T2_CONTROLS: dict[str, tuple[list[str], list[str]]] = dict(T2_CONTROLS)
#: T3 억부 6종(P0 임계 재사용, 신규 성립 허용 — 밴드 조건은 `_p0_effective_ok` 안에 있다).
_T3_P0: tuple[str, ...] = (
    "JAEDA_SINYAK",
    "GWANDA_SINYAK",
    "INDA_SINYAK",
    "SEOLGI_TAEGWA",
    "GUNGEOP_JAENGJAE",
    "BIGEOP_TALJAE",
)
#: T3 변화 전용(원국 성립 고정, 강화·완화만): pid → 압력 지표 계산 키.
#: 'group:<g>' = 그룹 세력, 'element:<E>' = 오행 세력, 'neg_group_sum' = 식재관 합의 음수,
#: 'neg_abs_officer_peer' = 관·비겁 차의 음수.
_T3_DELTA_ONLY: dict[str, str] = {
    "JAEDA_SAENGSAL": "group:wealth",
    "GWANSAL_HONJAP": "group:officer",
    "SINWANG_JAEWANG": "group:wealth",
    "SINWANG_JAEYAK": "group:wealth",
    "INWANG_SINWANG": "group:resource",
    "SINWANG_MUUI": "neg_group_sum",
    "SINSAL_YANGJEONG": "neg_abs_officer_peer",
}
#: 오행 과다 물상 20종: pid → 강한 오행(변화 전용 지표 = 그 오행 세력).
_T3_ELEMENT_OVERLOAD: dict[str, str] = {
    "TODA_GEUMMAE": "土",
    "SUDA_MOKBU": "水",
    "MOKDA_TOBUNG": "木",
    "HWADA_GEUMSAK": "火",
    "GEUMDA_MOKJEOL": "金",
    "TODA_SUTAK": "土",
    "SUDA_HWAMYEOL": "水",
    "MOKDA_HWASIK": "木",
    "HWADA_TOCHO": "火",
    "GEUMDA_SUTAK": "金",
    "MOKDA_SUCHUK": "木",
    "HWADA_MOKBUN": "火",
    "TODA_HWAHOE": "土",
    "GEUMDA_TOBYEON": "金",
    "SUDA_GEUMCHIM": "水",
    "MOKGYEON_GEUMGYEOL": "木",
    "TOJUNG_MOKJEOL": "土",
    "SUDA_TORYU": "水",
    "HWAYEOM_SUYEOL": "火",
    "GEUMDA_HWASIK": "金",
}
#: T4 오행 균형·조후: pid → 모드.
#: 'balance'(水火 균형) / 'imbalance' / ('need', 오행) / ('lack', 오행).
_T4_RULES: dict[str, tuple[str, str]] = {
    "SUHWA_GIJE": ("balance", "水火"),
    "SUHWA_MIJE": ("imbalance", "水火"),
    "HANMOK_HYANGYANG": ("need", "火"),
    "GEUMHAN_SURAENG": ("lack", "火"),
    "HWAYEOM_TOJO": ("lack", "水"),
    "CHEONHAN_JIDONG": ("lack", "火"),
}
#: T4 중 운에서 신규 성립을 허용하는 것(계절 조건이 원국 고정인 조후 4종은 제외).
_T4_NEW_ALLOWED = frozenset({"SUHWA_GIJE", "SUHWA_MIJE"})
#: T5 천간 배합: pid → 조건 평가 함수 키(아래 `_t5_conditions`).
_T5_IDS: tuple[str, ...] = (
    "JEONGHWA_YEONGEUM",
    "BYEOKGAP_INJEONG",
    "DEUNGRA_GYEGAP",
    "BYEONGHWA_TALGWANG",
    "GAPMOK_SOTO",
    "MUTO_JESU",
    "SUTANG_GIHO",
    "HWACHI_SEUNGRYONG",
)
#: T5 중 '과다' 전제(원국 excessive 고정)라 변화 전용으로 보는 것.
_T5_DELTA_ONLY: dict[str, str] = {"SUTANG_GIHO": "水", "HWACHI_SEUNGRYONG": "火"}

_TYPE_OF: dict[str, PatternTransitType] = {}
for _pid in _T1_PATHS:
    _TYPE_OF[_pid] = "T1"
for _pid in _T2_CONTROLS:
    _TYPE_OF[_pid] = "T2"
for _pid in ("SALJUNG_JEGYEONG", "JESAL_TAEGWA", "GWANSAL_MUJE"):
    _TYPE_OF[_pid] = "T2"
for _pid in (*_T3_P0, *_T3_DELTA_ONLY, *_T3_ELEMENT_OVERLOAD):
    _TYPE_OF[_pid] = "T3"
for _pid in _T4_RULES:
    _TYPE_OF[_pid] = "T4"
for _pid in _T5_IDS:
    _TYPE_OF[_pid] = "T5"

#: 표시용 상태 우선순위(신규 > 해소 > 강화 > 완화 > 변동 없음).
_STATUS_RANK: dict[str, int] = {
    "new": 0,
    "resolved": 1,
    "strengthened": 2,
    "weakened": 3,
    "unchanged": 4,
}


def transit_type_of(pattern_id: str) -> PatternTransitType | None:
    """패턴 ID 의 판정 유형(T1~T5). 범위 밖(격국·합충·내부 신호 등)이면 None."""
    return _TYPE_OF.get(pattern_id)


# ── 운 적용 세력 ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LuckGlyph:
    """운 스택의 글자 1개."""

    layer: str
    stem: str
    branch: str


@dataclass
class AdjustedStrength:
    """운 적용 세력 — 원국 `effective_percent` 기준, 합 100 으로 재정규화."""

    ten_gods: dict[str, float]
    groups: dict[str, float]
    elements: dict[str, float]
    damaged_groups: set[str] = field(default_factory=set)
    rooted_elements: set[str] = field(default_factory=set)
    stems: set[str] = field(default_factory=set)  # 원국 천간(일간 포함) + 운 천간
    branches: set[str] = field(default_factory=set)  # 원국 지지 + 운 지지
    element_of_group: dict[str, str] = field(default_factory=dict)  # 그룹 → 오행(한자)

    def group(self, tgs: Sequence[str]) -> float:
        """십성 목록의 세력 합(%)."""
        return float(sum(self.ten_gods.get(t, 0.0) for t in tgs))

    def group_element(self, grp: str) -> str:
        """그룹의 오행(한자)."""
        return self.element_of_group.get(grp, "")


@dataclass
class _Glyph:
    key: tuple[str, str, str]  # (kind, position, char)
    contrib: dict[str, float]  # 십성 → 단위
    main_tgs: set[str]  # 손상 판정에 쓰는 주 십성(천간/본기)
    factor: float = 1.0
    transform_to: str | None = None  # 化 오행(한자)


def _natal_glyphs(result: ManseV2Result) -> list[_Glyph]:
    pillars = result.pillars
    assert pillars is not None
    dm = Stem(pillars.day.stem)
    out: list[_Glyph] = []
    for pos in ("year", "month", "hour"):
        p = getattr(pillars, pos)
        if p is None:
            continue
        tg = str(ten_god(dm, Stem(p.stem)))
        out.append(_Glyph(("stem", pos, p.stem), {tg: float(DIST_STEM_WEIGHT[pos])}, {tg}))
    for pos in ("year", "month", "day", "hour"):
        p = getattr(pillars, pos)
        if p is None:
            continue
        contrib: dict[str, float] = {}
        main: set[str] = set()
        for hs, kind, budget in hidden_stems_for(Branch(p.branch)):
            tg = str(ten_god(dm, hs))
            contrib[tg] = contrib.get(tg, 0.0) + DIST_BRANCH_WEIGHT[pos] * budget
            if kind.value == "main":
                main.add(tg)
        out.append(_Glyph(("branch", pos, p.branch), contrib, main))
    return out


def _luck_glyphs(dm: Stem, stack: Sequence[LuckGlyph]) -> list[_Glyph]:
    out: list[_Glyph] = []
    for g in stack:
        tg = str(ten_god(dm, Stem(g.stem)))
        out.append(_Glyph(("stem", "luck", g.stem), {tg: _LUCK_STEM_UNITS}, {tg}))
        contrib: dict[str, float] = {}
        main: set[str] = set()
        for hs, kind, budget in hidden_stems_for(Branch(g.branch)):
            t = str(ten_god(dm, hs))
            contrib[t] = contrib.get(t, 0.0) + _LUCK_BRANCH_UNITS * budget
            if kind.value == "main":
                main.add(t)
        out.append(_Glyph(("branch", "luck", g.branch), contrib, main))
    return out


def _apply_relation_modifiers(
    result: ManseV2Result,
    natal: list[_Glyph],
    luck: list[_Glyph],
    stack: Sequence[LuckGlyph],
) -> None:
    """합반·합거·합화·충을 글자 factor/transform 으로 옮긴다.

    기존 운 합 의미화 결과를 읽기만 한다(재판정 없음).
    """
    if not stack:
        return
    sems = collect_luck_relation_semantics(
        result,
        luck_stems=[g.stem for g in stack],
        luck_branches=[g.branch for g in stack],
    )
    by_key: dict[tuple[str, str, str], list[_Glyph]] = {}
    for g in (*natal, *luck):
        by_key.setdefault(g.key, []).append(g)
    for sem in sems:
        kind = "stem" if sem.kind == "stem_combination" else "branch"
        for occ in sem.occurrences:
            for g in by_key.get((kind, occ.position, occ.char), []):
                if sem.binding_state == BindingState.BOUND:
                    g.factor = min(g.factor, _BOUND_FACTOR)
                elif sem.binding_state == BindingState.REMOVED and occ.position != "luck":
                    g.factor = 0.0  # 합거 — 운이 원국 글자를 끌어가 작용 제거
                if (
                    sem.transformation_state == TransformationState.TRANSFORMED
                    and sem.transform_element
                ):
                    g.transform_to = sem.transform_element
    luck_branches = {Branch(g.branch) for g in stack}
    for g in natal:
        if g.key[0] != "branch":
            continue
        b = Branch(g.key[2])
        if any(frozenset({b, lb}) in BRANCH_CLASHES for lb in luck_branches):
            g.factor = min(g.factor, _CLASH_FACTOR)


def compute_adjusted_strength(
    result: ManseV2Result,
    stack: Sequence[LuckGlyph],
) -> AdjustedStrength:
    """원국 effective_percent 에 운 스택을 더하고 합·충 보정 후 재정규화한 세력.

    Args:
        result: 만세 결과(pillars·force_analysis 필수, 시주 있음).
        stack: 운 글자(대운→세운→월운 순 누적). 비어 있으면 원국 세력 그대로.

    Returns:
        십성·그룹·오행 세력(%)과 손상 그룹·통근 오행·출현 천간/지지.
    """
    pillars = result.pillars
    force = result.force_analysis
    assert pillars is not None and force is not None
    dm = Stem(pillars.day.stem)
    base = {tg: float(v) for tg, v in (force.ten_gods.effective_percent or {}).items()}
    natal = _natal_glyphs(result)
    luck = _luck_glyphs(dm, stack)
    _apply_relation_modifiers(result, natal, luck, stack)

    ge = group_elements(STEM_ELEMENT[dm])
    el_of_group = {g: str(e) for g, e in ge.items()}
    group_of_el = {v: k for k, v in el_of_group.items()}
    tg_units: dict[str, float] = {}
    for g in natal:
        for tg, u in g.contrib.items():
            tg_units[tg] = tg_units.get(tg, 0.0) + u
    adj = dict(base)
    # 손상 집계는 그룹 단위다: 손상된 글자의 단위가 그 그룹 원국 단위의 절반 이상일 때만
    # '손상 그룹'.
    # 충 하나가 글자 하나를 깎았다고 그 그룹의 모든 경로를 끄면 과잉이다(2026-10-17 실측: 丑未충 →
    # 재성 경로 6종 일괄 해소). 글자 단위 감산 자체는 세력에 이미 반영된다.
    group_units: dict[str, float] = {}
    damaged_units: dict[str, float] = {}
    for g in natal:
        for t in g.main_tgs:
            grp = _GROUP_OF.get(t)
            if grp is not None:
                group_units[grp] = group_units.get(grp, 0.0) + sum(g.contrib.values())
    damaged: set[str] = set()

    def _add_transformed(amount: float, element: str) -> None:
        grp = group_of_el.get(element)
        if grp is None or amount <= 0:
            return
        for tg in _TG_GROUPS[grp]:
            adj[tg] = adj.get(tg, 0.0) + amount / 2.0  # 正/偏 균등(근사)

    for g in natal:
        if g.factor >= 1.0 and g.transform_to is None:
            continue
        for tg, u in g.contrib.items():
            share = u / tg_units[tg] if tg_units.get(tg) else 0.0
            amount = base.get(tg, 0.0) * share
            if g.transform_to is not None:
                adj[tg] = adj.get(tg, 0.0) - amount
                _add_transformed(amount * g.factor, g.transform_to)
            else:
                adj[tg] = adj.get(tg, 0.0) - amount * (1.0 - g.factor)
        # 손상 = 묶임·제거·충, 또는 다른 그룹 오행으로의 合化. 자기 그룹과 같은 오행으로 化하는 것
        # (예: 庚일간 亥卯未 木局 → 재성 그대로)은 강화이지 손상이 아니다.
        for t in g.main_tgs:
            grp = _GROUP_OF.get(t)
            if grp is None:
                continue
            same_el = g.transform_to is not None and group_of_el.get(g.transform_to) == grp
            if g.transform_to is not None and not same_el:
                lost = sum(g.contrib.values())
            elif g.factor < 1.0:
                lost = sum(g.contrib.values()) * (1.0 - g.factor)
            else:
                continue
            damaged_units[grp] = damaged_units.get(grp, 0.0) + lost
    for grp, total_u in group_units.items():
        if total_u > 0 and damaged_units.get(grp, 0.0) >= 0.5 * total_u:
            damaged.add(grp)
    for g in luck:
        for tg, u in g.contrib.items():
            if g.transform_to is not None:
                _add_transformed(u * g.factor, g.transform_to)
            else:
                adj[tg] = adj.get(tg, 0.0) + u * g.factor
    total = sum(max(v, 0.0) for v in adj.values()) or 1.0
    ten_gods = {tg: round(max(v, 0.0) / total * 100.0, 3) for tg, v in adj.items()}
    groups = {grp: round(sum(ten_gods.get(t, 0.0) for t in m), 3) for grp, m in _TG_GROUPS.items()}
    elements = {el_of_group[grp]: v for grp, v in groups.items()}

    rooted: set[str] = set()
    branches: set[str] = set()
    for pos in ("year", "month", "day", "hour"):
        p = getattr(pillars, pos)
        if p is not None:
            branches.add(p.branch)
    branches |= {g.branch for g in stack}
    for b in branches:
        rooted |= {str(STEM_ELEMENT[hs]) for hs, _k, _w in hidden_stems_for(Branch(b))}
    stems = {pillars.day.stem}
    for pos in ("year", "month", "hour"):
        p = getattr(pillars, pos)
        if p is not None:
            stems.add(p.stem)
    stems |= {g.stem for g in stack}
    return AdjustedStrength(
        ten_gods, groups, elements, damaged, rooted, stems, branches, el_of_group
    )


# ── 유형별 작동 판정 ────────────────────────────────────────────────────────


@dataclass
class _Eval:
    operating: bool
    metric: float
    evidence: list[str]
    flags: list[str]


def _cond_input(s: AdjustedStrength, band: str) -> ConditionInput:
    """운 적용 세력 → 성립 조건 입력(원국 밴드 고정)."""
    return ConditionInput(
        groups=s.groups, ten_gods=s.ten_gods, band=band,
        element_of_group=s.element_of_group, damaged_groups=s.damaged_groups,
        rooted_elements=s.rooted_elements,
    )


def _eval_t1(pid: str, s: AdjustedStrength, band: str) -> _Eval:
    """T1 생극 경로 — 성립 조건 SSOT 위임(원국 감지와 같은 함수)."""
    r = evaluate_condition(pid, _cond_input(s, band))
    assert r is not None
    return _Eval(r.ok, r.metric, list(r.evidence), list(r.flags))


def _eval_t2(pid: str, s: AdjustedStrength, band: str) -> _Eval:
    """T2 제어·배합 — 성립 조건 SSOT 위임."""
    r = evaluate_condition(pid, _cond_input(s, band))
    assert r is not None
    return _Eval(r.ok, r.metric, list(r.evidence), list(r.flags))


def _group_element_rooted(s: AdjustedStrength, grp: str) -> bool:
    """그룹 오행이 원국·운 지지 지장간에 통근(유근)하는가."""
    return s.group_element(grp) in s.rooted_elements


def _eval_t3(pid: str, s: AdjustedStrength, band: str, natal_established: bool) -> _Eval:
    if pid in _T3_CAPACITY:
        # 감당 능력 모델(2026-10-17): 재성 개수가 그대로여도 일간 측이 충분히 강해지면
        # '일시적 해소'.
        # 작동 = 기존 비율 임계(P0, 원국 밴드) ∧ 압력 > 일간 측 유효 세력(비겁+인성). 재다신약은
        # 재 > 인×3 이면 인성이 재에 깨져(재극인) 감당에 못 쓴다 — 용신 모듈 규칙 재사용.
        main = _T3_CAPACITY[pid]
        pressure = s.groups[main]
        peer, resource = s.groups["peer"], s.groups["resource"]
        resource_broken = pid == "JAEDA_SINYAK" and pressure > resource * _JAEDA_RESOURCE_RATIO
        capacity = peer + (0.0 if resource_broken else resource)
        ok = _p0_effective_ok(pid, s.groups, band) and pressure > capacity
        flags: list[str] = []
        if natal_established and not ok and capacity >= pressure * _BALANCE_RATIO:
            flags.append("reversal")  # 역전 — 해소를 넘어 일간 쪽이 과해짐(반대 불균형 가능)
        ev = [
            f"{main} {pressure:.0f}%·일간측 {capacity:.0f}%"
            + ("(인성 제외·재극인)" if resource_broken else "") + f"·{band}"
        ]
        return _Eval(ok, pressure - capacity, ev, flags)
    if pid in _T3_P0:
        ok = _p0_effective_ok(pid, s.groups, band)
        main = {"INDA_SINYAK": "resource", "GUNGEOP_JAENGJAE": "peer", "BIGEOP_TALJAE": "peer"}[pid]
        self_side = s.groups["peer"] + s.groups["resource"]
        ev = [f"{main} {s.groups[main]:.0f}%·일간측 {self_side:.0f}%·{band}"]
        return _Eval(ok, s.groups[main], ev, [])
    if pid in _T3_ELEMENT_OVERLOAD:
        el = _T3_ELEMENT_OVERLOAD[pid]
        return _Eval(
            natal_established, s.elements.get(el, 0.0), [f"{el} {s.elements.get(el, 0.0):.0f}%"], []
        )
    key = _T3_DELTA_ONLY[pid]
    if key.startswith("group:"):
        g = key.split(":", 1)[1]
        return _Eval(natal_established, s.groups[g], [f"{g} {s.groups[g]:.0f}%"], [])
    if key == "neg_group_sum":
        v = s.groups["output"] + s.groups["wealth"] + s.groups["officer"]
        return _Eval(natal_established, 100.0 - v, [f"식재관 {v:.0f}%"], [])
    v = abs(s.groups["officer"] - s.groups["peer"])
    return _Eval(
        natal_established,
        100.0 - v,
        [f"관 {s.groups['officer']:.0f}%·비겁 {s.groups['peer']:.0f}%"],
        [],
    )


def _eval_t4(pid: str, s: AdjustedStrength, natal_established: bool) -> _Eval:
    mode, arg = _T4_RULES[pid]
    if mode in ("balance", "imbalance"):
        su, hwa = s.elements.get("水", 0.0), s.elements.get("火", 0.0)
        in_band = _BALANCE_LO <= su <= _BALANCE_HI and _BALANCE_LO <= hwa <= _BALANCE_HI
        ratio = (su / hwa) if hwa > 0 else math.inf
        balanced = in_band and (1 / _BALANCE_RATIO) <= ratio <= _BALANCE_RATIO
        broken = ratio > _BALANCE_BROKEN or ratio < 1 / _BALANCE_BROKEN
        damaged = bool({"水", "火"} & _damaged_elements(s))
        off = abs(math.log(ratio, _BALANCE_RATIO)) if 0 < ratio < math.inf else 2.0
        metric = 1.0 - min(off, 2.0) / 2.0
        ev = [f"水 {su:.0f}%·火 {hwa:.0f}%"]
        if mode == "balance":
            return _Eval(
                balanced and not damaged,
                metric * 100.0,
                ev,
                ["broken"] if (broken or damaged) else [],
            )
        return _Eval((not balanced) and su + hwa > 0, (1.0 - metric) * 100.0, ev, [])
    el = arg
    v = s.elements.get(el, 0.0)
    if mode == "need":
        return _Eval(natal_established and v >= _BALANCE_LO, v, [f"{el} {v:.0f}%"], [])
    return _Eval(natal_established and v < _BALANCE_LO, _BALANCE_LO - v, [f"{el} {v:.0f}%"], [])


def _damaged_elements(s: AdjustedStrength) -> set[str]:
    return {s.group_element(g) for g in s.damaged_groups}


def _eval_t5(pid: str, s: AdjustedStrength, dm_stem: str, natal_established: bool) -> _Eval:
    e = s.elements
    stems = s.stems
    conds: list[tuple[str, bool]]
    if pid == "JEONGHWA_YEONGEUM":
        conds = [
            ("丁·庚 동시", {"丁", "庚"} <= stems),
            (f"金 {e.get('金', 0):.0f}%≥15", e.get("金", 0) >= _T5_STRENGTH),
            ("丁 유근 또는 甲", "火" in s.rooted_elements or "甲" in stems),
            ("水<火", e.get("水", 0) < e.get("火", 0)),
        ]
    elif pid == "BYEOKGAP_INJEONG":
        conds = [
            ("丁·甲·庚 동시", {"丁", "甲", "庚"} <= stems),
            ("水<火", e.get("水", 0) < e.get("火", 0)),
        ]
    elif pid == "DEUNGRA_GYEGAP":
        conds = [
            ("乙일간·甲", dm_stem == "乙" and "甲" in stems),
            ("金<木", e.get("金", 0) < e.get("木", 0)),
        ]
    elif pid == "BYEONGHWA_TALGWANG":
        conds = [
            ("丁일간·丙", dm_stem == "丁" and "丙" in stems),
            (f"火 {e.get('火', 0):.0f}%≥15", e.get("火", 0) >= _T5_STRENGTH),
        ]
    elif pid == "GAPMOK_SOTO":
        conds = [
            ("甲", "甲" in stems),
            (f"土 {e.get('土', 0):.0f}%≥15", e.get("土", 0) >= _T5_STRENGTH),
            ("金<木", e.get("金", 0) < e.get("木", 0)),
        ]
    elif pid == "MUTO_JESU":
        conds = [
            ("戊", "戊" in stems),
            (f"水 {e.get('水', 0):.0f}%≥15", e.get("水", 0) >= _T5_STRENGTH),
            ("木<土", e.get("木", 0) < e.get("土", 0)),
        ]
    else:  # 과다 전제(원국 고정) — 변화 전용
        el = _T5_DELTA_ONLY[pid]
        return _Eval(natal_established, e.get(el, 0.0), [f"{el} {e.get(el, 0.0):.0f}%"], [])
    ok = all(c for _, c in conds)
    metric = 100.0 * sum(1 for _, c in conds if c) / len(conds)
    ev = [("✓ " if c else "✗ ") + name for name, c in conds]
    return _Eval(ok, metric, ev, [])


def _evaluate(
    pid: str,
    s: AdjustedStrength,
    *,
    band: str,
    dm_stem: str,
    natal_established: bool,
    natal_weak: bool,
) -> _Eval | None:
    t = _TYPE_OF.get(pid)
    if t == "T1":
        return _eval_t1(pid, s, band)
    if t == "T2":
        return _eval_t2(pid, s, band)
    if t == "T3":
        return _eval_t3(pid, s, band, natal_established)
    if t == "T4":
        return _eval_t4(pid, s, natal_established)
    if t == "T5":
        return _eval_t5(pid, s, dm_stem, natal_established)
    return None


def _natal_prereq(
    pid: str, s0: AdjustedStrength, *, natal_ids: set[str], band: str, dm_stem: str,
    geok_main: str, excessive: set[str],
) -> bool:
    """운에서 '신규 성립'을 허용하는 **원국 전제**.

    원국 감지기의 성립 조건에서 그대로 가져온 고정값이다.

    원국 전제가 없으면 운 글자끼리 다리를 만들어도 성립으로 보지 않는다(변화는 원국 구조 바탕).
    - 생극 경로: 두 다리 중 하나가 원국에 10%+ 존재(운은 나머지 한쪽만 보충).
    - 신강 전제(재자약살·식상설수), 과다 전제(탐재괴인), 파생 전제(득비이재=재다신약,
      살중용인/용식=관다신약, 인다용재=인다신약, 관살제겁=쟁재, 재제효인=편인도식,
      양인합살=양인격)는 원국 성립 여부로.
    - 억부 6종: 주 그룹 원국 10%+(밴드 조건은 `_p0_effective_ok` 안의 원국 밴드).
    - 수화기제/미제: 원국에 水·火 둘 다 존재. 천간 배합: 필요 천간 중 하나 이상 원국 출현.
    """
    g, e, stems = s0.groups, s0.elements, s0.stems
    strong = band in _STRONG_BANDS

    def has(grp: str) -> bool:
        return g.get(grp, 0.0) >= _MIN_PRESENCE

    if pid in _T1_PATHS:
        a_tgs, b_tgs, _extra = _T1_PATHS[pid]
        if pid == "JAEJA_YAKSAL":
            return strong and has("wealth")
        if pid == "SIKSANG_SEOLSU":
            return strong
        if pid == "TAMJAE_GOEIN":
            return s0.group_element("wealth") in excessive and has("resource")
        if pid == "JAEGWANIN_SANGSAENG":
            return sum(1 for x in ("wealth", "officer", "resource") if has(x)) >= 2
        return s0.group(a_tgs) >= _MIN_PRESENCE or s0.group(b_tgs) >= _MIN_PRESENCE
    if pid in ("SANGGWAN_PAEIN", "SANGGWAN_YONGIN"):
        return s0.group(["상관"]) >= _MIN_PRESENCE
    if pid in ("SALJUNG_YONGIN", "SALJUNG_YONGSIK"):
        return "GWANDA_SINYAK" in natal_ids
    if pid == "DEUKBI_IJAE":
        return "JAEDA_SINYAK" in natal_ids
    if pid == "INDA_YONGJAE":
        return "INDA_SINYAK" in natal_ids
    if pid == "GWANSAL_JEGEOP":
        return bool({"GUNGEOP_JAENGJAE", "BIGEOP_TALJAE"} & natal_ids)
    if pid == "JAEJE_HYOIN":
        return "PYEONIN_DOSIK" in natal_ids
    if pid == "YANGIN_HAPSAL":
        return geok_main == "양인격" or "YANGIN_HAPSAL" in natal_ids
    if pid in ("SALJUNG_JEGYEONG", "GWANSAL_MUJE"):
        return g.get("officer", 0.0) >= _MIN_CONTROLLED
    if pid == "JESAL_TAEGWA":
        return g.get("officer", 0.0) >= 5.0 and has("output")
    if pid in _T2_CONTROLS:
        controlled, controller = _T2_CONTROLS[pid]
        return s0.group(controlled) >= _MIN_PRESENCE or s0.group(controller) >= _MIN_PRESENCE
    if pid in _T3_P0:
        return has(_P0_MAIN_GROUP[pid])
    if pid in _T4_NEW_ALLOWED:
        return e.get("水", 0.0) > 0 and e.get("火", 0.0) > 0
    if pid == "JEONGHWA_YEONGEUM":
        return bool({"丁", "庚"} & stems)
    if pid == "BYEOKGAP_INJEONG":
        return len({"丁", "甲", "庚"} & stems) >= 2
    if pid == "DEUNGRA_GYEGAP":
        return dm_stem == "乙"
    if pid == "BYEONGHWA_TALGWANG":
        return dm_stem == "丁"
    if pid == "GAPMOK_SOTO":
        return "甲" in stems or e.get("土", 0.0) >= _T5_STRENGTH
    if pid == "MUTO_JESU":
        return "戊" in stems or e.get("水", 0.0) >= _T5_STRENGTH
    return False


def _new_allowed(pid: str) -> bool:
    t = _TYPE_OF.get(pid)
    if t in ("T1", "T2"):
        return True
    if t == "T3":
        return pid in _T3_P0
    if t == "T4":
        return pid in _T4_NEW_ALLOWED
    return pid not in _T5_DELTA_ONLY


def _status(
    prev_on: bool,
    now_on: bool,
    prev_metric: float,
    now_metric: float,
    *,
    layer: str,
    new_allowed: bool,
    natal_on: bool = False,
) -> PatternTransitStatus:
    """상태 전이.

    원국 성립 패턴이 상위 층에서 꺼졌다가 다시 켜지면 '신규'가 아니라 '강화'(재작동)다.
    """
    if not prev_on and now_on:
        if natal_on:
            return "strengthened"
        return "new" if new_allowed else "unchanged"
    if prev_on and not now_on:
        if not natal_on:
            return "unchanged"  # 운만으로 생겼던 상태의 소멸은 '해소'가 아니다(원국 바탕 아님)
        return "weakened" if layer == "month" else "resolved"  # 월운 층은 해소 금지(일시 차단)
    if prev_on and now_on:
        if now_metric - prev_metric >= _DELTA:
            return "strengthened"
        if prev_metric - now_metric >= _DELTA:
            return "weakened"
    return "unchanged"


# ── 공개 API ────────────────────────────────────────────────────────────────


def evaluate_pattern_states(
    result: ManseV2Result,
    natal_patterns: Sequence[DetectedPattern],
    stack: Sequence[LuckGlyph],
) -> list[PatternState]:
    """운 스택의 **마지막 층**에 대한 패턴 상태 목록.

    Args:
        result: 만세 결과(시주 미상이면 빈 목록 — 정책).
        natal_patterns: 원국 감지(P0 포함) 전체. 성립 고정(`natal_established`).
        stack: 대운→세운→월운 순 누적 운 글자. 빈 스택은 허용하지 않는다(원국 자체는 상태가 아님).

    Returns:
        `natal_established` 이거나 이 층·상위 층에서 작동한 패턴만.
        강도순(신규 > 해소 > 강화 > 완화).
    """
    pillars = result.pillars
    force = result.force_analysis
    if not stack or pillars is None or pillars.hour is None or force is None:
        return []
    band = force.strength.band
    dm_stem = pillars.day.stem
    natal_weak = band in {"신약", "태신약", "중화신약"}
    natal_ids = {d.pattern_id: d for d in natal_patterns}
    s_natal = compute_adjusted_strength(result, [])
    geok_main = (result.geokguk.main_structure if result.geokguk is not None else None) or ""
    excessive = set(force.five_elements.excessive_elements or [])
    # 신규 성립 후보 = 원국 전제를 통과한 패턴. 원국 성립 패턴은 항상 후보(강화·완화·해소 판정).
    candidates = [
        pid for pid in _TYPE_OF
        if pid in natal_ids or (
            _new_allowed(pid) and _natal_prereq(
                pid, s_natal, natal_ids=set(natal_ids), band=band, dm_stem=dm_stem,
                geok_main=geok_main, excessive=excessive,
            )
        )
    ]
    layers = [compute_adjusted_strength(result, stack[: i + 1]) for i in range(len(stack))]
    layer_name = stack[-1].layer

    def _eval_all(s: AdjustedStrength) -> dict[str, _Eval]:
        out: dict[str, _Eval] = {}
        for pid in candidates:
            ev = _evaluate(
                pid,
                s,
                band=band,
                dm_stem=dm_stem,
                natal_established=pid in natal_ids,
                natal_weak=natal_weak,
            )
            if ev is not None:
                out[pid] = ev
        return out

    base_eval = _eval_all(s_natal)
    layer_evals = [_eval_all(s) for s in layers]
    now = layer_evals[-1]
    parent = layer_evals[-2] if len(layer_evals) >= 2 else base_eval

    states: list[PatternState] = []
    for pid, ev in now.items():
        natal_on = pid in natal_ids  # 원국 성립은 감지기 결과로 고정(P0 포함)
        prev_on = parent[pid].operating if pid in parent else natal_on
        if pid in parent and parent is base_eval:
            prev_on = natal_on  # 대운 층의 부모 = 원국 성립 여부
        # 운만으로 생긴 패턴은 지금 작동 중일 때만 상태를 낸다(꺼진 뒤 '해소'·'완화'를 쓰지 않는다).
        if not natal_on and not ev.operating:
            continue
        base_metric = base_eval[pid].metric if pid in base_eval else 0.0
        parent_metric = parent[pid].metric if pid in parent else base_metric
        # 원국 감지기는 성립으로 보지만 운 모델의 작동 조건이 원국에서부터 미충족인 패턴
        # (예: 관인상생인데 원국 식상 > 관)은 '해소'를 낼 수 없다 — 성립을 고정으로 두고
        # 세력 변화(강화·완화)만 본다.
        base_on = base_eval[pid].operating if pid in base_eval else natal_on
        now_on, prev_for_status = ev.operating, prev_on
        if natal_on and not base_on:
            now_on, prev_for_status = True, True
        st_parent = _status(
            prev_for_status,
            now_on,
            parent_metric,
            ev.metric,
            layer=layer_name,
            new_allowed=_new_allowed(pid),
            natal_on=natal_on,
        )
        st_natal = _status(
            natal_on,
            now_on,
            base_metric,
            ev.metric,
            layer=layer_name,
            new_allowed=_new_allowed(pid),
            natal_on=natal_on,
        )
        if st_parent == "unchanged" and st_natal == "unchanged" and not ev.operating:
            continue
        sources = (
            [g.layer for g in stack]
            if (ev.operating and not natal_on)
            else ([layer_name] if st_parent != "unchanged" else [])
        )
        states.append(
            PatternState(
                pattern_id=pid,
                name_ko=natal_ids[pid].name_ko if pid in natal_ids else _name_ko(pid),
                transit_type=_TYPE_OF[pid],
                natal_established=natal_on,
                operating=ev.operating,
                status_vs_natal=st_natal,
                status_vs_parent=st_parent,
                strength_natal=round(natal_ids[pid].strength, 3) if pid in natal_ids else 0.0,
                strength_operating=round(min(max(ev.metric / 60.0, 0.0), 1.0), 3),
                activation_sources=sources,
                evidence=ev.evidence,
                flags=list(ev.flags),
            )
        )
    _mark_competition(states)
    states.sort(
        key=lambda x: (_STATUS_RANK[x.status_vs_parent], -x.strength_operating, x.pattern_id)
    )
    return states


def _name_ko(pid: str) -> str:
    """사전 한글명(운에서 신규 성립한 패턴은 원국 감지 객체가 없어 사전에서 읽는다)."""
    for e in load_structure_patterns().patterns:
        if e.pattern_id == pid:
            return e.name_ko
    return pid


def _mark_competition(states: list[PatternState]) -> None:
    """T1 경로와 그 A 를 누르는 T2 배합이 함께 작동하면 양쪽에 competition(경쟁) 플래그."""
    on = {st.pattern_id: st for st in states if st.operating}
    for pid, st in on.items():
        if pid not in _T1_PATHS:
            continue
        a_grp = _GROUP_OF[_T1_PATHS[pid][0][0]]
        for pid2, st2 in on.items():
            if pid2 not in _T2_CONTROLS:
                continue
            controlled, controller = _T2_CONTROLS[pid2]
            if (
                _GROUP_OF[controlled[0]] == a_grp
                and _GROUP_OF[controller[0]] == _CONTROLLER_OF[a_grp]
            ):
                for x in (st, st2):
                    if "competition" not in x.flags:
                        x.flags.append("competition")


# ── 문구(사전 치환) ────────────────────────────────────────────────────────

_TEXT_PATH = (
    Path(__file__).resolve().parents[3]
    / "dictionaries"
    / "interpretations"
    / "pattern_transit_text.json"
)


@lru_cache(maxsize=2)
def load_pattern_transit_text(path: Path = _TEXT_PATH) -> dict:
    """`interpretations/pattern_transit_text.json` 로드(캐시).

    스키마·린트는 dictionaries.py 가 담당한다.
    """
    return json.loads(path.read_text("utf-8"))


def status_label_ko(transit_type: str, status: str) -> str:
    """유형별 상태 어휘(신규 성립/활성/충족 …) — 사전 label."""
    for it in load_pattern_transit_text()["items"]:
        if it["type"] == transit_type and it["status"] == status:
            return str(it["label"])
    return status


def pattern_change_lines(
    states: Sequence[PatternState],
    layer: str,
    *,
    max_count: int = 3,
    include_unchanged: bool = False,
) -> list[str]:
    """화면·LLM 공용 '구조 변화' 줄(최대 N, 상태 우선순위·강도순). 즉석 작문 없음 — 사전 문구 치환.

    Args:
        states: `evaluate_pattern_states` 결과.
        layer: 'daewoon' | 'year' | 'month' — 문구의 {layer} 치환.
        max_count: 줄 수 상한(채팅·리포트 3, 화면 3).
        include_unchanged: 변동 없음도 포함할지(기본 제외).
    """
    text = load_pattern_transit_text()
    layer_ko = text["layer_ko"].get(layer, layer)
    by_cell = {(it["type"], it["status"]): it for it in text["items"]}
    out: list[str] = []
    used_flags: set[str] = set()  # 같은 기간 안에서 플래그 문구는 한 번만(줄마다 반복 금지)
    for st in states:
        if st.status_vs_parent == "unchanged" and not include_unchanged:
            continue
        cell = by_cell.get((st.transit_type, st.status_vs_parent))
        if cell is None:
            continue
        line = f"[{cell['label']}] " + str(cell["text"]).format(name=st.name_ko, layer=layer_ko)
        flags = [text["flag_text"][f] for f in st.flags
                 if f in text["flag_text"] and f not in used_flags]
        used_flags |= set(st.flags)
        if flags:
            line += " — " + " · ".join(flags)
        out.append(line)
        if len(out) >= max_count:
            break
    return out


def daewoon_ganji_by_year(result: ManseV2Result) -> dict[int, str]:
    """연도 → 그 해가 속한 대운 간지(근사 교운일, 시작 포함·끝 제외 — 사전계산 빌더와 같은 규칙)."""
    out: dict[int, str] = {}
    lc = result.luck_cycles
    if lc is None:
        return out
    for d in lc.daewoon_table:
        for y in range(d.approx_start_date.year, d.approx_end_date.year):
            out.setdefault(y, d.ganji)
    return out


# ── 종합 타임라인(원국 → 대운 → 세운 → 월) ───────────────────────────────────

_MONTH_SYMBOL_ORDER: dict[str, int] = {"new": 0, "resolved": 1, "strengthened": 2, "weakened": 3}


def _cell(st: PatternState) -> PatternTimelineCell:
    return PatternTimelineCell(
        status=st.status_vs_parent, operating=st.operating,
        label=status_label_ko(st.transit_type, st.status_vs_parent),
    )


def build_pattern_timeline(
    result: ManseV2Result,
    natal_patterns: Sequence[DetectedPattern],
    *,
    year: int,
    daewoon_ganji: str | None,
    year_ganji: str | None,
    months: Sequence[tuple[str, str, str]],
) -> PatternTimeline:
    """선택 연도의 구조 배합 흐름 — 대운 층·세운 층·월운 12층 상태를 패턴별 한 줄로 종합한다.

    각 층의 상태는 **직전 층 대비**(`status_vs_parent`)다. 대운에서 선 구조가 세운에서 꺼지고
    월운에서 다시 켜지는 흐름을 한 줄에서 읽게 한다(2026-10-17 데굴님 제안). 시주 미상이면
    `hour_unknown=True`·빈 행(정책). 점수·길흉 무관.

    Args:
        months: (label 'YYYY-MM', stem, branch) 12개(절기월 순).
    """
    tl = PatternTimeline(
        year=year, daewoon_ganji=daewoon_ganji, year_ganji=year_ganji,
        month_labels=[m[0] for m in months], month_ganji=[m[1] + m[2] for m in months],
    )
    if result.pillars is None or result.pillars.hour is None:
        tl.hour_unknown = True
        tl.note = "시주 미상 — 세력 기반 구조 상태는 산출하지 않는다(후보 시진에 따라 달라짐)."
        return tl
    base: list[LuckGlyph] = []
    dw_states: list[PatternState] = []
    if daewoon_ganji:
        base.append(LuckGlyph("daewoon", daewoon_ganji[0], daewoon_ganji[1]))
        dw_states = evaluate_pattern_states(result, natal_patterns, base)
    yr_states: list[PatternState] = []
    if year_ganji:
        base.append(LuckGlyph("year", year_ganji[0], year_ganji[1]))
        yr_states = evaluate_pattern_states(result, natal_patterns, base)
    month_states: list[list[PatternState]] = [
        evaluate_pattern_states(result, natal_patterns, [*base, LuckGlyph("month", st, br)])
        for _label, st, br in months
    ]
    by_dw = {x.pattern_id: x for x in dw_states}
    by_yr = {x.pattern_id: x for x in yr_states}
    by_mo = [{x.pattern_id: x for x in ms} for ms in month_states]
    natal_ids = {d.pattern_id: d for d in natal_patterns}
    ids: list[str] = []
    for src in (by_dw, by_yr, *by_mo):
        for pid in src:
            if pid not in ids:
                ids.append(pid)
    # 원국 성립 패턴(판정 유형 범위 안)은 변동이 없어도 행을 만든다(원국 기록 유지).
    for pid in natal_ids:
        if pid in _TYPE_OF and pid not in ids:
            ids.append(pid)
    dic = {e.pattern_id: e for e in load_structure_patterns().patterns}
    rows: list[PatternTimelineRow] = []
    for pid in ids:
        ttype = _TYPE_OF.get(pid)
        if ttype is None:
            continue
        dcell = _cell(by_dw[pid]) if pid in by_dw else None
        ycell = _cell(by_yr[pid]) if pid in by_yr else None
        mcells = [(_cell(bm[pid]) if pid in bm else None) for bm in by_mo]
        flags: list[str] = []
        for st in (by_dw.get(pid), by_yr.get(pid), *(bm.get(pid) for bm in by_mo)):
            if st is not None:
                for f in st.flags:
                    if f not in flags:
                        flags.append(f)
        natal_on = pid in natal_ids
        # 요약: 원국 → 대운 → 세운 → 월(상태별 묶음). 변동 없음은 생략, 전부 없으면 '변동 없음'.
        parts = ["원국 성립" if natal_on else "원국 미성립"]
        if dcell is not None and dcell.status != "unchanged":
            parts.append(f"대운 {dcell.label}")
        if ycell is not None and ycell.status != "unchanged":
            parts.append(f"세운 {ycell.label}")
        # 월 번호는 순번이 아니라 절기월 라벨(YYYY-MM)에서 읽는다 — 월운 목록은 입춘월(2월)부터
        # 시작하므로 순번+1 로 세면 한 달씩 밀린다(2026-10-17 데굴님 지적).
        grouped: dict[str, list[int]] = {}
        for i, c in enumerate(mcells):
            if c is not None and c.status != "unchanged":
                label = months[i][0]
                month_no = int(label[5:7]) if len(label) >= 7 and label[5:7].isdigit() else i + 1
                grouped.setdefault(c.label, []).append(month_no)
        for label, idxs in grouped.items():
            parts.append("·".join(f"{i}" for i in idxs) + f"월 {label}")
        summary = " → ".join(parts) if len(parts) > 1 else parts[0] + " · 이 해 변동 없음"
        entry = dic.get(pid)
        rows.append(PatternTimelineRow(
            pattern_id=pid,
            name_ko=natal_ids[pid].name_ko if natal_on else (entry.name_ko if entry else pid),
            name_hanja=entry.name_hanja if entry else "",
            transit_type=ttype, natal_established=natal_on,
            daewoon=dcell, year=ycell, months=mcells, flags=flags, summary=summary,
        ))
    # 정렬: 원국 성립 먼저, 그다음 변동이 큰 순(신규·해소 > 강화·완화), 이름순.
    def _rank(r: PatternTimelineRow) -> tuple:
        cells = [c for c in (r.daewoon, r.year, *r.months) if c is not None]
        best = min((_MONTH_SYMBOL_ORDER.get(c.status, 9) for c in cells), default=9)
        return (0 if r.natal_established else 1, best, r.name_ko)
    rows.sort(key=_rank)
    tl.rows = rows
    tl.note = (
        "각 칸은 직전 층 대비 상태(대운=원국 대비, 세운=대운 대비, 월=세운 대비). "
        "구조 작동의 변화이지 길흉이 아니다."
    )
    return tl
