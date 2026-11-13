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

2026-11-13 데굴님 검수("재생관과 재생살이 관과는 무관한 대운에 의해 모두 성립")로 더한 규칙
(근거: 《子平真詮》 論財·論偏官·論行運成格變格, 《淵海子平》 論偏官 —
doc/v2_2/PATTERN_TRANSIT_STATES.md §6):
- **재생관·재생살은 함께 서지 않는다.** 정관·편관이 둘 다 10%+ 이면 강한 쪽 이름 하나만 성립하고
  `mixed_officer`(관살혼잡) 표지를 단다("財旺生官者…不混七煞").
- **제살태과가 서면 식신제살·상관제살·관살유제는 서지 않는다**(같은 제어를 '적절'과 '과다'로
  동시에 부르지 않는다).
- **관살유제의 制는 식상이다.** 인성은 化(살인상생·살중용인이 담당)라 유제의 근거가 아니다
  ("煞用食制者，上也" / "不若轉而就印"). 식상이 관살의 절반 미만이면 살중제경, 2배 이상이면
  제살태과 쪽이므로 그 사이만 유제다. 인성이 식상을 압도하면(인극식) 제어 불성.
- **化 세력은 그룹 세력에만 있다.** `groups` 는 化神 세력을 포함하지만 `ten_gods` 는 실제 글자의
  십성만 담는다 — 정·편이 지정된 다리(정관·편관·식신·상관·편인·겁재)는 글자 세력만 본다.
- 운에서의 '신규 성립'은 운 글자가 다리를 직접 공급하거나 차단자를 덜어낼 때만(`contribution_spec`).

2026-11-13 (2) 데굴님 검수("식상생재는 일간의 힘이 필요 … 내 경우에는 신약 사주") — SSOT §7:
- **일간이 힘을 쓰는 구조**(`DM_SPENDING_IDS`: 생재 3종·재생관·식신제살·상관제살·관살유제·
  살중용식)는 원국이 신약·태신약(`FRAIL_BANDS`)이면 구조(局)는 있어도 감당이 부족하다 —
  성립은 두되 표지 `weak_dm` 을 항상 단다
  ("食神生財之局，因身輕身重而不同…身輕則喜幫身", "煞重身輕，用食則身不能當").
  운에서의 신규 성립 금지·일간 쪽 글자 손실 불인정·幫身 운 표지는 운 판정 모듈이 맡는다.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field

from saju_manse_analysis.distribution.ten_god_distribution import GROUPS as _TG_GROUPS

from saju_shared_types.manse_result import ManseV2Result

MIN_PRESENCE = 10.0
MIN_CONTROLLED = 20.0
JESAL_TAEGWA_RATIO = 2.0
JAEDA_RESOURCE_RATIO = 3.0
WEAK_KILLING = 5.0  # '존재하되 약한' 칠살 하한(제살태과·재자약살) — 기존 운 판정 값
#: 제어가 가벼운(制輕) 경계 — 식상·제화가 관살의 절반 미만(살중제경의 기존 비율). 관살유제 하한.
LIGHT_CONTROL_RATIO = 0.5
#: 일간이 주체로 힘을 쓰는 구조(설기·재관 감당·제살). 재생살은 신약에서 재가 살을 생해 일간을 치는
#: 구조라 신약이 본래 자리이고, 재관인상생은 인성이 일간을 생하며 끝나는 순환이라 넣지 않는다.
DM_SPENDING_IDS: frozenset[str] = frozenset({
    "SIKSIN_SAENGJAE", "SANGGWAN_SAENGJAE", "SIKSANG_SAENGJAE", "JAE_SAENGGWAN",
    "SIKSIN_JESAL", "SANGGWAN_JESAL", "GWANSAL_YUJE", "SALJUNG_YONGSIK",
})
#: 일간이 약해 감당이 부족하다고 보는 원국 밴드(중화신약은 받침이 있는 쪽으로 본다).
FRAIL_BANDS: frozenset[str] = frozenset({"태신약", "신약"})
#: 일간 쪽 그룹(비겁·인성) — 신약 원국에서는 덜어져도 '길이 열린' 것이 아니다.
SELF_SIDE_GROUPS: frozenset[str] = frozenset({"peer", "resource"})
#: 원국 감지 줄 끝에 붙는 신약형 근거 문구(화면·LLM 공용, `DetectedPattern.basis_note`).
WEAK_DM_BASIS_NOTE = "신약형 — 일간이 약해 감당이 부족(비겁·인성 운에서 쓸 힘이 생김)"


#: 같은 작용을 두 이름으로 부르지 않는다(2026-11-13 3차, SSOT §8) — 왼쪽 구조는 오른쪽 구조가 서면
#: 띄우지 않는다. 원국 감지와 운 판정이 함께 쓴다.
#: - 군겁쟁재·비겁탈재 → 득비이재: 재다신약 원국의 비겁은 재를 나눠 감당하는 받침이다.
#: - 재생살 → 재자약살: 신강에 약한 살을 재가 기르는 것은 재자약살이라 부른다.
#: - 재극인·탐재괴인 → 인다용재: 인성 과다 원국에서 재가 인을 제하는 것은 병이 아니라 약이다.
YIELDS_TO: dict[str, frozenset[str]] = {
    "GUNGEOP_JAENGJAE": frozenset({"DEUKBI_IJAE"}),
    "BIGEOP_TALJAE": frozenset({"DEUKBI_IJAE"}),
    "JAE_SAENGSAL": frozenset({"JAEJA_YAKSAL"}),
    "JAE_GEUGIN": frozenset({"INDA_YONGJAE"}),
    "TAMJAE_GOEIN": frozenset({"INDA_YONGJAE"}),
}
#: 신왕(身旺) 전제 구조 — 신약·태신약 원국에서는 운에서 새로 서지 않는다. 군겁쟁재·비겁탈재는 신왕한
#: 일간의 비겁이 재를 다투는 구조이고, 관살제겁은 그 쟁재를 관살로 다스리는 약이다.
STRONG_PREMISE_IDS: frozenset[str] = frozenset({
    "GUNGEOP_JAENGJAE", "BIGEOP_TALJAE", "GWANSAL_JEGEOP",
})


def dm_cannot_carry(pid: str, band: str) -> bool:
    """일간이 힘을 쓰는 구조인데 원국이 신약·태신약인가(감당 부족)."""
    return pid in DM_SPENDING_IDS and band in FRAIL_BANDS


#: 수화기제·미제(원국 감지와 운 판정 공용 — 원국 감지기의 기존 값). 결핍 임계는 오행 분포의
#: `deficient_elements`(9% 미만)와 같다.
SUHWA_MIN = 15.0
SUHWA_GAP_BALANCED = 15.0
SUHWA_GAP_BROKEN = 30.0
SUHWA_DEFICIENT = 9.0
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


def full_group_of(tgs: Sequence[str]) -> str | None:
    """십성 목록이 한 그룹의 구성원 전부면 그 그룹 키, 아니면 None(정·편 지정 다리)."""
    if not tgs:
        return None
    grp = GROUP_OF.get(tgs[0])
    if grp is None:
        return None
    return grp if set(tgs) == set(_TG_GROUPS[grp]) else None


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
        """십성 목록 세력 합(%).

        목록이 한 그룹 전체(예: 정재·편재)면 그룹 세력(`groups`, 化神 세력 포함)을, 정·편이 지정된
        목록이면 실제 글자의 십성 세력만 더한다 — 化 세력으로 없는 정관·편관을 만들지 않는다.
        """
        grp = full_group_of(tgs)
        if grp is not None and grp in self.groups:
            return float(self.groups[grp])
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


def evaluate_t1(pid: str, inp: ConditionInput, *, exclusive: bool = True) -> ConditionResult:
    """생극 경로(A→B) 성립: 양단 10%+ ∧ 비손상 ∧ A의 극제자 ≤ A ∧ 패턴별 추가 게이트.

    Args:
        exclusive: 재생관·재생살 상호 배타 적용 여부. False 는 '재→정관 다리 자체가 서는가'만
            묻는 호출(재관인상생 연쇄 판정)용이다.
    """
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
    if exclusive and pid in _OFFICER_PATH_RIVAL:
        # 재생관·재생살 배타(2026-11-13): 정관·편관이 함께 있으면(둘 다 10%+) 강한 쪽 이름만 선다.
        # 같으면 재생살 — 칠살이 섞이면 재생관(財旺生官)의 전제 "不混七煞"이 깨진다.
        jeong, pyeon = inp.group(["정관"]), inp.group(["편관"])
        if jeong >= MIN_PRESENCE and pyeon >= MIN_PRESENCE:
            dominant = "JAE_SAENGGWAN" if jeong > pyeon else "JAE_SAENGSAL"
            if pid != dominant:
                ok = False
                ev.append(f"정관 {jeong:.0f}%·편관 {pyeon:.0f}% 병존 — 강한 쪽만 성립")
            elif ok:
                flags.append("mixed_officer")
    if inp.band in WEAK_BANDS and a_grp in ("output", "wealth") and output + wealth >= 50.0:
        flags.append("burden")
    return ConditionResult(ok, a + b, ev, flags)


#: 재→관 경로의 맞수(정관 다리·편관 다리) — 둘이 함께 서지 않는다.
_OFFICER_PATH_RIVAL: frozenset[str] = frozenset({"JAE_SAENGGWAN", "JAE_SAENGSAL"})


def jesal_taegwa_ok(inp: ConditionInput) -> bool:
    """제살태과 핵심 조건 — 편관 5%+ ∧ 식상 10%+ ∧ 식상 ≥ 2×편관(편관은 실제 글자 세력)."""
    killing, output = inp.group(["편관"]), inp.g("output")
    return (
        killing >= WEAK_KILLING
        and output >= MIN_PRESENCE
        and output >= JESAL_TAEGWA_RATIO * killing
    )


def evaluate_suhwa(su: float, hwa: float, deficient: Collection[str]) -> tuple[bool, bool]:
    """수화기제·수화미제 성립(원국 감지와 운 판정 공용, 2026-11-13).

    Args:
        su: 水 세력(%). hwa: 火 세력(%).
        deficient: 결핍으로 본 오행(한자) 모음.

    Returns:
        (기제, 미제). 기제 = 둘 다 15%+ ∧ 둘 다 결핍 아님 ∧ 차 15 이내.
        미제 = 기제가 아니면서 한쪽 결핍 또는 차 30 이상. 한쪽이 아예 없으면 둘 다 False.
    """
    if su <= 0 or hwa <= 0:
        return False, False
    healthy = "水" not in deficient and "火" not in deficient
    gap = abs(su - hwa)
    gije = su >= SUHWA_MIN and hwa >= SUHWA_MIN and healthy and gap <= SUHWA_GAP_BALANCED
    mije = (not gije) and (not healthy or gap >= SUHWA_GAP_BROKEN)
    return gije, mije


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
        taegwa = jesal_taegwa_ok(inp)  # 제어가 과하면 제살태과 쪽 — 같이 세우지 않는다(2026-11-13)
        ok = (
            killing >= MIN_PRESENCE
            and food >= MIN_PRESENCE
            and "output" not in inp.damaged_groups
            and "officer" not in inp.damaged_groups
            and not obstructed
            and not taegwa
        )
        flags: list[str] = []
        if resource < MIN_PRESENCE:
            flags.append("no_yin")  # 無印(문자 그대로의 인성 부재) — 표지
        if wealth >= MIN_PRESENCE and wealth >= food:
            flags.append("wealth_feeds_killing")  # 재생살 부작용
        ev = [
            f"{food_tgs[0]} {food:.0f}% → 편관 {killing:.0f}%",
            f"인성 {resource:.0f}%{'(인극식 방해)' if obstructed else ''}·{_subtype(inp.band)}"
            + ("·제살 과다(제살태과 쪽)" if taegwa else ""),
        ]
        return ConditionResult(ok, food + killing, ev, flags)
    if pid == "JESAL_TAEGWA":
        killing = inp.group(["편관"])
        ok = jesal_taegwa_ok(inp)
        flags = []
        if _dm_lacks_support(inp):
            flags.append("dm_lacks_support")  # 일주 의지처 없음 — 독립 보조 판정
        if resource >= output / 2:
            flags.append("yin_restrains_output")  # 인성이 식상을 제어 → 구응(완화 조정)
        ev = [f"식상 {output:.0f}% ≥ 2×편관 {killing:.0f}%", _subtype(inp.band)]
        return ConditionResult(ok, output - killing, ev, flags)
    if pid == "GWANSAL_YUJE":
        # 관살유제(2026-11-13 재정의): 制 = 식상("有制伏則為偏官", "煞用食制者，上也"). 인성은 化 라
        # 유제의 근거가 아니다. 식상이 관살의 절반 미만이면 制輕(살중제경), 2배 이상이면 과다 —
        # 그 사이만 유제. 인성이 식상을 압도하면 제어 불성("印能去食護煞"), 제살태과와는 배타.
        obstructed = resource >= output
        ok = (
            officer >= MIN_CONTROLLED
            and output >= MIN_PRESENCE
            and inp.rooted("output")
            and officer * LIGHT_CONTROL_RATIO <= output < JESAL_TAEGWA_RATIO * officer
            and not obstructed
            and "output" not in inp.damaged_groups
            and "officer" not in inp.damaged_groups
            and not jesal_taegwa_ok(inp)
        )
        flags = []
        if wealth >= MIN_PRESENCE and wealth >= output:
            flags.append("wealth_feeds_killing")  # "財能轉食生煞"
        return ConditionResult(
            ok,
            officer + output,
            [
                f"관살 {officer:.0f}% ← 식상 {output:.0f}%"
                f"({'유근' if inp.rooted('output') else '무근'})",
                f"인성 {resource:.0f}%{'(인극식 방해)' if obstructed else ''}",
            ],
            flags,
        )
    if pid == "GWANSAL_MUJE":
        ok = officer >= MIN_CONTROLLED and output < MIN_PRESENCE and resource < MIN_PRESENCE
        return ConditionResult(
            ok, officer, [f"관살 {officer:.0f}%·식상 {output:.0f}%·인성 {resource:.0f}%"], []
        )
    if pid == "SALJUNG_JEGYEONG":
        ctl = output + resource
        return ConditionResult(
            officer >= MIN_CONTROLLED and 0 < ctl < officer * LIGHT_CONTROL_RATIO,
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


def evaluate_condition(
    pid: str, inp: ConditionInput, *, exclusive: bool = True
) -> ConditionResult | None:
    """패턴 성립 조건 평가(원국·운 공용). 범위 밖 패턴은 None.

    Args:
        exclusive: 재생관·재생살 상호 배타 적용 여부(`evaluate_t1` 참조).
    """
    res: ConditionResult | None = None
    if pid in T1_PATHS:
        res = evaluate_t1(pid, inp, exclusive=exclusive)
    elif pid in T2_CONTROLS or pid in T2_SPECIAL:
        res = evaluate_t2(pid, inp)
    if res is not None and dm_cannot_carry(pid, inp.band):
        # 신약형 표지는 상시 — 식상+재 50% 조건부 `burden` 과 겹치면 이쪽 하나만 둔다.
        res.flags = [f for f in res.flags if f != "burden"] + ["weak_dm"]
    return res


@dataclass(frozen=True)
class ContributionSpec:
    """운에서 '신규 성립'을 인정하는 직접 기여 조건(2026-11-13).

    근거: 《子平真詮》 論行運成格變格 "本命用神，成而未全，從而就之" — 운의 成格은 운 글자가 빠진
    부분을 직접 채울 때다. 論支中喜忌逢運透清 — 지장간은 투출될 때 쓰인다(운 지지는 본기만 공급).

    Attributes:
        legs: 다리별 십성 목록. 운 천간 또는 운 지지 본기의 십성이 이 중 하나에 들면 공급.
            그룹 전체 다리는 확정 化·局의 그룹 세력으로도 공급된다(정·편 지정 다리는 글자만).
        blockers: 차단자 그룹. 운 글자가 원국의 이 그룹 글자를 합·충·化로 덜어내면 기여.
        veto: 운이 이 십성을 공급하면 신규 성립이 아니다(구조가 풀리는 방향).
    """

    legs: tuple[tuple[str, ...], ...]
    blockers: frozenset[str] = frozenset()
    veto: frozenset[str] = frozenset()


#: T1 추가 게이트 → 그 게이트가 견주는 차단자 그룹.
_GATE_BLOCKERS: dict[str | None, frozenset[str]] = {
    "peer<=wealth": frozenset({"peer"}),
    "output<=officer": frozenset({"output"}),
    "wealth<resource": frozenset({"wealth"}),
    "wealth<resource*3": frozenset({"wealth"}),
    "resource>=10&output<=officer": frozenset({"output"}),
    "wealth>=resource&officer<10": frozenset({"officer"}),
}
#: 기본 차단 조건(A의 극제자 ≤ A)을 쓰지 않는 게이트 — 차단자 없음.
_GATES_WITHOUT_BASE_BLOCKER: frozenset[str] = frozenset(
    {"rescue_flag", "rescue_wealth_flag", "weak_killing_strong_dm"}
)


def contribution_spec(pid: str) -> ContributionSpec | None:
    """패턴의 직접 기여 조건. 범위 밖(조건 미정의) 패턴은 None."""
    if pid in T1_PATHS:
        a_tgs, b_tgs, gate = T1_PATHS[pid]
        legs: tuple[tuple[str, ...], ...] = (tuple(a_tgs), tuple(b_tgs))
        if pid == "JAEGWANIN_SANGSAENG":
            legs = (tuple(_WEALTH), tuple(_OFFICER), tuple(_RESOURCE))
        blockers: frozenset[str] = _GATE_BLOCKERS.get(gate, frozenset())
        if gate not in _GATES_WITHOUT_BASE_BLOCKER:
            blockers = blockers | {CONTROLLER_OF[GROUP_OF[a_tgs[0]]]}
        return ContributionSpec(legs, blockers)
    if pid in ("SIKSIN_JESAL", "SANGGWAN_JESAL"):
        food = "식신" if pid == "SIKSIN_JESAL" else "상관"
        return ContributionSpec((("편관",), (food,)), frozenset({"resource"}))
    if pid == "JESAL_TAEGWA":
        # 편관을 보태는 운은 제살태과가 풀리는 방향("運行財印，亦能發福")이라 신규 성립이 아니다.
        return ContributionSpec((tuple(_OUTPUT),), veto=frozenset({"편관"}))
    if pid == "GWANSAL_YUJE":
        return ContributionSpec((tuple(_OFFICER), tuple(_OUTPUT)), frozenset({"resource"}))
    if pid in ("GWANSAL_MUJE", "SALJUNG_JEGYEONG"):
        return ContributionSpec((tuple(_OFFICER),), frozenset({"output", "resource"}))
    if pid in ("SANGGWAN_PAEIN", "SANGGWAN_YONGIN"):
        return ContributionSpec((("상관",), tuple(_RESOURCE)), frozenset({"wealth"}))
    if pid in T2_CONTROLS:
        controlled, controller = T2_CONTROLS[pid]
        return ContributionSpec(
            (tuple(controlled), tuple(controller)),
            frozenset({CONTROLLER_OF[GROUP_OF[controller[0]]]}),
        )
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
