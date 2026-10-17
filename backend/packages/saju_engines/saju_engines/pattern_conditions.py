"""구조 배합 성립 조건 SSOT — 원국 감지와 운 적용 판정이 **같은 함수**를 쓴다.

(2026-10-17 데굴님 검수)

배경: 생극·제어 계열 11종의 원국 감지가 십성 공존만으로 성립했고(`_PRESENCE_RULES`), 운 판정 모델은
다른 조건을 써서 "원국 성립인데 운 모델로는 원국부터 미작동"이 생겼다. 고전 전제(살왕·인극식 방해·
재불괴인·식상상관 등)를 패턴당 한 벌로 여기 두고 양쪽이 호출한다.

원칙:
- 임계는 기존 값만 쓴다: 존재 10%, 피제어 20%, 제살 과다 2배, 재극인 3배(용신 모듈), 신약·신강 밴드.
- 신강약은 성립 게이트가 아니라 **유형**(subtype)으로 남긴다. 예외는 고전이 명시한 것만
  (상관패인=身稍弱, 재자약살·식상설수=신강).
- 제살태과의 '일주 의지처 없음'은 필수 조건이 아니라 **독립 보조 판정**(`dm_lacks_support`:
  일간 오행 무근 ∧ 비겁·인성 유효 지원 없음). 신강약은 subtype.
- 식신제살의 無印: 인성이 식신을 압도하면(인성 ≥ 식신) 제살 경로 손상으로 보아 미작동. 인성 부재
  (10% 미만)는 `no_yin` 표지로만 둔다. 재성이 살을 생하면 `wealth_feeds_killing` 표지.
- 결과는 길흉이 아니다(성립≠길흉).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from saju_manse_analysis.distribution.ten_god_distribution import GROUPS as _TG_GROUPS

from saju_shared_types.manse_result import ManseV2Result

MIN_PRESENCE = 10.0
MIN_CONTROLLED = 20.0
JESAL_TAEGWA_RATIO = 2.0
JAEDA_RESOURCE_RATIO = 3.0
WEAK_KILLING = 5.0  # '존재하되 약한' 칠살 하한(제살태과·재자약살) — 기존 운 판정 값
WEAK_BANDS = frozenset({"태신약", "신약", "중화신약"})
STRONG_BANDS = frozenset({"신강", "태신강"})

GROUP_OF: dict[str, str] = {tg: g for g, members in _TG_GROUPS.items() for tg in members}
CONTROLLER_OF: dict[str, str] = {
    "wealth": "peer",
    "resource": "wealth",
    "output": "resource",
    "officer": "output",
    "peer": "officer",
}
_PEER = list(_TG_GROUPS["peer"])
_RESOURCE = list(_TG_GROUPS["resource"])
_OUTPUT = list(_TG_GROUPS["output"])
_WEALTH = list(_TG_GROUPS["wealth"])
_OFFICER = list(_TG_GROUPS["officer"])


@dataclass
class ConditionInput:
    """조건 평가 입력 — 원국(effective_percent)·운 적용 세력 어느 쪽이든 같은 형태."""

    groups: dict[str, float]
    ten_gods: dict[str, float]
    band: str  # 원국 신강약 밴드(운 적용에서도 원국 값 고정)
    element_of_group: dict[str, str] = field(default_factory=dict)
    damaged_groups: set[str] = field(default_factory=set)
    rooted_elements: set[str] = field(default_factory=set)

    def group(self, tgs: Sequence[str]) -> float:
        """십성 목록 세력 합(%)."""
        return float(sum(self.ten_gods.get(t, 0.0) for t in tgs))

    def g(self, grp: str) -> float:
        """그룹 세력(%)."""
        return float(self.groups.get(grp, 0.0))

    def rooted(self, grp: str) -> bool:
        """그룹 오행이 지지 지장간에 통근하는가(유근)."""
        return self.element_of_group.get(grp, "") in self.rooted_elements


@dataclass
class ConditionResult:
    """성립 판정 — ok(작동)·metric(강화/완화 비교 지표)·근거·표지. 길흉 아님."""

    ok: bool
    metric: float
    evidence: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


#: T1 생극 경로: pid → (A, B, 추가 게이트 키)
T1_PATHS: dict[str, tuple[list[str], list[str], str | None]] = {
    "SIKSIN_SAENGJAE": (["식신"], _WEALTH, "peer<=wealth"),
    "SANGGWAN_SAENGJAE": (["상관"], _WEALTH, "peer<=wealth"),
    "SIKSANG_SAENGJAE": (_OUTPUT, _WEALTH, "peer<=wealth"),
    "JAE_SAENGGWAN": (_WEALTH, ["정관"], "output<=officer"),
    "JAE_SAENGSAL": (_WEALTH, ["편관"], None),
    "JAEJA_YAKSAL": (_WEALTH, ["편관"], "weak_killing_strong_dm"),
    "GWAN_IN_SANGSAENG": (["정관"], _RESOURCE, "wealth<resource"),
    "SAL_IN_SANGSAENG": (["편관"], _RESOURCE, "wealth<resource*3"),
    "JAEGWANIN_SANGSAENG": (_WEALTH, _OFFICER, "resource>=10&output<=officer"),
    "SIKSANG_SEOLSU": (_PEER, _OUTPUT, "strong_dm"),
    "JAE_GEUGIN": (_WEALTH, _RESOURCE, "wealth>=resource&officer<10"),
    "SANGGWAN_GYEONGWAN": (["상관"], ["정관"], "rescue_flag"),
    "PYEONIN_DOSIK": (["편인"], ["식신"], "rescue_wealth_flag"),
    "TAMJAE_GOEIN": (_WEALTH, _RESOURCE, "wealth>=resource"),
}
#: T2 제어·배합(일반형): pid → (피제어, 제어)
T2_CONTROLS: dict[str, tuple[list[str], list[str]]] = {
    "SANGGWAN_PAEIN": (["상관"], _RESOURCE),
    "SANGGWAN_YONGIN": (["상관"], _RESOURCE),
    "SIKSIN_JESAL": (["편관"], ["식신"]),
    "SANGGWAN_JESAL": (["편관"], ["상관"]),
    "GWANSAL_YUJE": (_OFFICER, _OUTPUT),
    # 살중(殺重)은 관살 전체의 압력이다 — 원국 어댑터(관다신약=관살 2+)와 같은 기준.
    "SALJUNG_YONGIN": (_OFFICER, _RESOURCE),
    "SALJUNG_YONGSIK": (_OFFICER, ["식신"]),
    "YANGIN_HAPSAL": (["겁재"], ["편관"]),
    "JAEJE_HYOIN": (["편인"], _WEALTH),
    "GWANSAL_JEGEOP": (_PEER, _OFFICER),
    "DEUKBI_IJAE": (_WEALTH, _PEER),
    "INDA_YONGJAE": (_RESOURCE, _WEALTH),
}
T2_SPECIAL: tuple[str, ...] = ("SALJUNG_JEGYEONG", "JESAL_TAEGWA", "GWANSAL_MUJE")
CONDITION_IDS: frozenset[str] = frozenset({*T1_PATHS, *T2_CONTROLS, *T2_SPECIAL})

#: 원국 감지에서 공존 규칙(_PRESENCE_RULES) 대신 이 조건으로 성립을 판정하는 패턴.
NATAL_CONDITION_IDS: tuple[str, ...] = (
    "SIKSIN_SAENGJAE",
    "SANGGWAN_SAENGJAE",
    "SIKSANG_SAENGJAE",
    "JAE_SAENGGWAN",
    "GWAN_IN_SANGSAENG",
    "SAL_IN_SANGSAENG",
    "JAE_SAENGSAL",
    "SIKSIN_JESAL",
    "SANGGWAN_JESAL",
    "SANGGWAN_PAEIN",
    "JESAL_TAEGWA",
)


def _subtype(band: str) -> str:
    return "신강형" if band in STRONG_BANDS else ("신약형" if band in WEAK_BANDS else "중화형")


def _dm_lacks_support(inp: ConditionInput) -> bool:
    """일주 의지처 없음(독립 보조 판정) — 일간 오행 무근 ∧ 비겁·인성 유효 지원 없음."""
    return (
        not inp.rooted("peer") and inp.g("peer") < MIN_PRESENCE and inp.g("resource") < MIN_PRESENCE
    )


def evaluate_t1(pid: str, inp: ConditionInput) -> ConditionResult:
    """생극 경로(A→B) 성립: 양단 10%+ ∧ 비손상 ∧ A의 극제자 ≤ A ∧ 패턴별 추가 게이트."""
    a_tgs, b_tgs, gate = T1_PATHS[pid]
    a, b = inp.group(a_tgs), inp.group(b_tgs)
    a_grp, b_grp = GROUP_OF[a_tgs[0]], GROUP_OF[b_tgs[0]]
    blocker_grp = CONTROLLER_OF[a_grp]
    blocker = inp.g(blocker_grp)
    ok = (
        a >= MIN_PRESENCE
        and b >= MIN_PRESENCE
        and a_grp not in inp.damaged_groups
        and b_grp not in inp.damaged_groups
        and blocker <= a
    )
    flags: list[str] = []
    ev = [
        f"{'·'.join(a_tgs)} {a:.0f}% → {'·'.join(b_tgs)} {b:.0f}%",
        f"차단 {blocker_grp} {blocker:.0f}%",
    ]
    wealth, resource, officer, output, peer = (
        inp.g(k) for k in ("wealth", "resource", "officer", "output", "peer")
    )
    if gate == "peer<=wealth":
        ok = ok and peer <= wealth
        ev.append(f"비겁 {peer:.0f}% ≤ 재 {wealth:.0f}%")
    elif gate == "output<=officer":
        ok = ok and output <= officer
        ev.append(f"식상 {output:.0f}% ≤ 관 {officer:.0f}%")
    elif gate == "wealth<resource":
        ok = ok and wealth < resource
        ev.append(f"재 {wealth:.0f}% < 인 {resource:.0f}%(재불괴인)")
    elif gate == "wealth<resource*3":
        ok = ok and wealth < resource * JAEDA_RESOURCE_RATIO
        ev.append(f"재 {wealth:.0f}% < 인×3(재불괴인)")
    elif gate == "resource>=10&output<=officer":
        ok = ok and resource >= MIN_PRESENCE and output <= officer
        ev.append(f"인 {resource:.0f}%·식상 {output:.0f}% ≤ 관 {officer:.0f}%")
    elif gate == "strong_dm":
        ok = ok and inp.band in STRONG_BANDS
        ev.append(f"{inp.band}")
    elif gate == "weak_killing_strong_dm":
        ok = (
            wealth >= MIN_PRESENCE
            and WEAK_KILLING <= inp.group(["편관"]) < MIN_CONTROLLED
            and inp.band in STRONG_BANDS
            and a_grp not in inp.damaged_groups
        )
        ev = [f"재 {wealth:.0f}%·편관 {inp.group(['편관']):.0f}%(약)·{inp.band}"]
    elif gate == "wealth>=resource&officer<10":
        ok = ok and wealth >= resource and officer < MIN_PRESENCE
        ev.append(f"재 {wealth:.0f}% ≥ 인 {resource:.0f}%·관 {officer:.0f}%(통관 없음)")
    elif gate == "wealth>=resource":
        ok = ok and wealth >= resource
    elif gate == "rescue_flag":
        ok = (
            a >= MIN_PRESENCE
            and b >= MIN_PRESENCE
            and a_grp not in inp.damaged_groups
            and b_grp not in inp.damaged_groups
        )
        if resource >= MIN_PRESENCE or wealth >= MIN_PRESENCE:
            flags.append("rescued")  # 인성 패인·재성 통관이 있으면 상관견관이 완화된다(게이트 아님)
    elif gate == "rescue_wealth_flag":
        ok = (
            a >= MIN_PRESENCE
            and b >= MIN_PRESENCE
            and a_grp not in inp.damaged_groups
            and b_grp not in inp.damaged_groups
        )
        if wealth >= MIN_PRESENCE:
            flags.append("rescued")  # 재성이 편인을 제하면 도식이 완화된다
    if inp.band in WEAK_BANDS and a_grp in ("output", "wealth") and output + wealth >= 50.0:
        flags.append("burden")
    return ConditionResult(ok, a + b, ev, flags)


def evaluate_t2(pid: str, inp: ConditionInput) -> ConditionResult:
    """제어·배합 성립.

    패턴별 고전 전제 반영(식신제살 인극식 방해·상관패인 재불괴인·제살태과 과다).
    """
    officer, output, resource, wealth, peer = (
        inp.g(k) for k in ("officer", "output", "resource", "wealth", "peer")
    )
    if pid in ("SIKSIN_JESAL", "SANGGWAN_JESAL"):
        food_tgs = ["식신"] if pid == "SIKSIN_JESAL" else ["상관"]
        food, killing = inp.group(food_tgs), inp.group(["편관"])
        obstructed = resource >= food  # 인성이 식신을 압도 → 제살 경로 손상(無印의 실질 판정)
        ok = (
            killing >= MIN_PRESENCE
            and food >= MIN_PRESENCE
            and "output" not in inp.damaged_groups
            and "officer" not in inp.damaged_groups
            and not obstructed
        )
        flags: list[str] = []
        if resource < MIN_PRESENCE:
            flags.append("no_yin")  # 無印(문자 그대로의 인성 부재) — 표지
        if wealth >= MIN_PRESENCE and wealth >= food:
            flags.append("wealth_feeds_killing")  # 재생살 부작용
        if ok and food >= JESAL_TAEGWA_RATIO * killing:
            flags.append("excessive")  # 제살 과다 — 제살태과와 겹침
        ev = [
            f"{food_tgs[0]} {food:.0f}% → 편관 {killing:.0f}%",
            f"인성 {resource:.0f}%{'(인극식 방해)' if obstructed else ''}·{_subtype(inp.band)}",
        ]
        return ConditionResult(ok, food + killing, ev, flags)
    if pid == "JESAL_TAEGWA":
        killing = inp.group(["편관"])
        ok = (
            killing >= WEAK_KILLING
            and output >= MIN_PRESENCE
            and output >= JESAL_TAEGWA_RATIO * killing
        )
        flags = []
        if _dm_lacks_support(inp):
            flags.append("dm_lacks_support")  # 일주 의지처 없음 — 독립 보조 판정
        if resource >= output / 2:
            flags.append("yin_restrains_output")  # 인성이 식상을 제어 → 구응(완화 조정)
        ev = [f"식상 {output:.0f}% ≥ 2×편관 {killing:.0f}%", _subtype(inp.band)]
        return ConditionResult(ok, output - killing, ev, flags)
    if pid == "GWANSAL_YUJE":
        ok = (
            officer >= MIN_CONTROLLED
            and (output >= MIN_PRESENCE or resource >= MIN_PRESENCE)
            and output < JESAL_TAEGWA_RATIO * officer
        )
        return ConditionResult(
            ok,
            officer + max(output, resource),
            [f"관살 {officer:.0f}%·식상 {output:.0f}%·인성 {resource:.0f}%"],
            [],
        )
    if pid == "GWANSAL_MUJE":
        ok = officer >= MIN_CONTROLLED and output < MIN_PRESENCE and resource < MIN_PRESENCE
        return ConditionResult(
            ok, officer, [f"관살 {officer:.0f}%·식상 {output:.0f}%·인성 {resource:.0f}%"], []
        )
    if pid == "SALJUNG_JEGYEONG":
        ctl = output + resource
        return ConditionResult(
            officer >= MIN_CONTROLLED and 0 < ctl < officer / 2,
            officer - ctl,
            [f"관살 {officer:.0f}%·제화 {ctl:.0f}%"],
            [],
        )
    if pid in ("SANGGWAN_PAEIN", "SANGGWAN_YONGIN"):
        sg = inp.group(["상관"])
        ok = (
            sg >= MIN_CONTROLLED
            and resource >= MIN_PRESENCE
            and inp.rooted("resource")
            and wealth < resource
            and inp.band in WEAK_BANDS
            and "resource" not in inp.damaged_groups
        )
        flags = ["over_control"] if ok and resource >= 2 * sg else []
        ev = [
            f"상관 {sg:.0f}% ← 인성 {resource:.0f}%"
            f"({'유근' if inp.rooted('resource') else '무근'})",
            f"재 {wealth:.0f}% < 인(재불괴인)·{inp.band}",
        ]
        return ConditionResult(ok, sg + resource, ev, flags)
    controlled_tgs, controller_tgs = T2_CONTROLS[pid]
    controlled, controller = inp.group(controlled_tgs), inp.group(controller_tgs)
    ctl_grp = GROUP_OF[controller_tgs[0]]
    counter_grp = CONTROLLER_OF[ctl_grp]
    counter = inp.g(counter_grp)
    rooted = inp.rooted(ctl_grp)
    ok = (
        controlled >= MIN_CONTROLLED
        and controller >= MIN_PRESENCE
        and rooted
        and counter < controller
        and ctl_grp not in inp.damaged_groups
    )
    flags = ["over_control"] if ok and controller >= 2 * controlled else []
    ev = [
        f"{'·'.join(controlled_tgs)} {controlled:.0f}% ← "
        f"{'·'.join(controller_tgs)} {controller:.0f}%({'유근' if rooted else '무근'})",
        f"역제 {counter_grp} {counter:.0f}%",
    ]
    return ConditionResult(ok, controlled + controller, ev, flags)


def evaluate_condition(pid: str, inp: ConditionInput) -> ConditionResult | None:
    """패턴 성립 조건 평가(원국·운 공용). 범위 밖 패턴은 None."""
    if pid in T1_PATHS:
        return evaluate_t1(pid, inp)
    if pid in T2_CONTROLS or pid in T2_SPECIAL:
        return evaluate_t2(pid, inp)
    return None


def natal_condition_input(result: ManseV2Result) -> ConditionInput | None:
    """원국용 입력.

    `effective_percent`(지장간·월령·투간·공망 반영) + 통근 오행 + 원국 밴드. 손상 없음.
    """
    from saju_shared_types.constants import STEM_ELEMENT, group_elements, hidden_stems_for
    from saju_shared_types.enums import Branch, Stem

    pillars, force = result.pillars, result.force_analysis
    if pillars is None or force is None:
        return None
    ten_gods = {tg: float(v) for tg, v in (force.ten_gods.effective_percent or {}).items()}
    groups = {g: float(sum(ten_gods.get(t, 0.0) for t in m)) for g, m in _TG_GROUPS.items()}
    ge = group_elements(STEM_ELEMENT[Stem(pillars.day.stem)])
    element_of_group = {g: str(e) for g, e in ge.items()}
    rooted: set[str] = set()
    for pos in ("year", "month", "day", "hour"):
        p = getattr(pillars, pos)
        if p is not None:
            rooted |= {str(STEM_ELEMENT[hs]) for hs, _k, _w in hidden_stems_for(Branch(p.branch))}
    return ConditionInput(
        groups=groups,
        ten_gods=ten_gods,
        band=force.strength.band,
        element_of_group=element_of_group,
        rooted_elements=rooted,
    )
