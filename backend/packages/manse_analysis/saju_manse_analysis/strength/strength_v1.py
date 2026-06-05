"""신강·신약 v1.3 — 8성분 합산 + 가종격 판별 (day_strength_v1.json 이식).

월령·통근·투간·천간십성·지장간십성·합국·충·조후를 합산해 score(-100~+100대)를 내고
7밴드(극신강/신강/중화신강/중화/중화신약/신약/극신약)로 분류한다. 구조(합/충) 탐지는
v2 constants 테이블을 재사용하고, 계수만 v1 마스터에서 가져온다.
"""

from __future__ import annotations

from saju_shared_types.constants import (
    BRANCH_CLASHES,
    CONTROLS,
    DIRECTIONAL_COMBINATIONS,
    GENERATES,
    SEASON_ELEMENT_BY_MONTH,
    SIX_COMBINATIONS,
    STEM_COMBINATIONS,
    STEM_ELEMENT,
    THREE_HARMONY,
    hidden_stems_for,
    main_hidden_stem,
)
from saju_shared_types.enums import Branch, Element, Stem
from saju_shared_types.pillars import FourPillarsResult

_POS_KO = {"year": "년", "month": "월", "day": "일", "hour": "시"}
_STAGE_KO = {"main": "정기", "middle": "중기", "residual": "여기"}

# ── v1 계수 마스터 (day_strength_v1.json) ──────────────────────────────────
_THRESHOLDS = [
    (90, 9999, "극신강"), (50, 89, "신강"), (20, 49, "중화신강"),
    (-19, 19, "중화"), (-49, -20, "중화신약"), (-79, -50, "신약"),
    (-9999, -80, "극신약"),
]
_BOUNDARIES = [90, 50, 20, -19, -49, -79]

_REL_MONTH = {"비겁": 40, "인성": 30, "식상": -15, "재성": -20, "관성": -30}
_BRANCH_STRENGTH = {
    Branch.IN: 1.0, Branch.MYO: 1.2, Branch.JIN: 0.8, Branch.SA: 1.0,
    Branch.O: 1.2, Branch.MI: 0.8, Branch.SIN: 1.0, Branch.YU: 1.2,
    Branch.SUL: 0.8, Branch.HAE: 1.0, Branch.JA: 1.2, Branch.CHUK: 0.8,
}
_ROOT = {
    "month": {"main": 27, "middle": 16, "residual": 9},
    "day": {"main": 22, "middle": 13, "residual": 7},
    "hour": {"main": 13, "middle": 8, "residual": 4},
    "year": {"main": 13, "middle": 8, "residual": 4},
}
_TEN_GOD = {"비겁": 9, "인성": 7, "식상": -9, "재성": -11, "관성": -13}
_STEM_POS_W = {"month": 1.2, "hour": 1.0, "year": 0.8}  # 일간 제외
_BRANCH_POS_W = {"month": 1.5, "day": 1.3, "hour": 1.0, "year": 0.8}
_STAGE_W = {"main": 1.0, "middle": 0.6, "residual": 0.35}
_REVEALED = {
    "month": {"main": 12, "middle": 8, "residual": 5},
    "day": {"main": 8, "middle": 5, "residual": 3},
    "hour": {"main": 5, "middle": 3, "residual": 2},
    "year": {"main": 5, "middle": 3, "residual": 2},
}
_COMBO_K = {"samhap_full": 1.4, "samhap_half": 1.2, "banghap_full": 1.5,
            "banghap_half": 1.15, "yukhap": 1.1}
_COMBO_REL = {"비겁": 15, "인성": 12, "식상": -8, "재성": -10, "관성": -12}
_STEMHAP_REL = {"비겁": 5, "인성": 4, "식상": -3, "재성": -4, "관성": -5}


def _grp(day_el: Element, t_el: Element) -> str:
    if day_el == t_el:
        return "비겁"
    if GENERATES[t_el] == day_el:
        return "인성"
    if GENERATES[day_el] == t_el:
        return "식상"
    if CONTROLS[day_el] == t_el:
        return "재성"
    if CONTROLS[t_el] == day_el:
        return "관성"
    return ""


def _positions(pillars: FourPillarsResult):
    for pos in ("year", "month", "day", "hour"):
        p = getattr(pillars, pos)
        if p is not None:
            yield pos, p


def _month_command(pillars, day_el):
    br = Branch(pillars.month.branch)
    br_el = SEASON_ELEMENT_BY_MONTH[br]
    rel = _grp(day_el, br_el)
    if not rel:
        return 0.0, ["월령 관계 미상 → 0"]
    s = _REL_MONTH[rel] * _BRANCH_STRENGTH[br]
    return s, [f"월령 {br}({br_el}) {rel} {_REL_MONTH[rel]:+d}×{_BRANCH_STRENGTH[br]} = {s:+.1f}"]


def _root(pillars, day_el):
    total = 0.0
    lines: list[str] = []
    for pos, p in _positions(pillars):
        for stem, kind, _w in hidden_stems_for(Branch(p.branch)):
            if STEM_ELEMENT[stem] == day_el:
                s = _ROOT[pos][kind.value]
                total += s
                lines.append(f"{_POS_KO[pos]}지{p.branch} {stem} 통근+{s}")
    return total, lines or ["통근 없음"]


def _revealed(pillars, day_stem, day_el):
    chart_stems = {p.stem for _pos, p in _positions(pillars)}
    total = 0.0
    lines: list[str] = []
    for pos, p in _positions(pillars):
        for stem, kind, _w in hidden_stems_for(Branch(p.branch)):
            if str(stem) not in chart_stems:
                continue
            rel = _grp(day_el, STEM_ELEMENT[stem])
            sign = 1 if rel in ("비겁", "인성") else -1 if rel in ("식상", "재성", "관성") else 0
            base = _REVEALED[pos][kind.value]
            total += base * sign
            lines.append(f"{_POS_KO[pos]}지{p.branch} {stem}({rel}) 투간{base}×{sign:+d}")
    return total, lines or ["투간 없음"]


def _stem_ten_god(pillars, day_el):
    total = 0.0
    lines: list[str] = []
    for pos in ("year", "month", "hour"):
        p = getattr(pillars, pos)
        if p is None:
            continue
        rel = _grp(day_el, STEM_ELEMENT[Stem(p.stem)])
        if not rel:
            continue
        s = _TEN_GOD[rel] * _STEM_POS_W[pos]
        total += s
        lines.append(f"{_POS_KO[pos]}간{p.stem}({rel}) {s:+.1f}")
    return total, lines or ["천간 십성 없음"]


def _hidden_ten_god(pillars, day_el):
    total = 0.0
    for pos, p in _positions(pillars):
        for stem, kind, _w in hidden_stems_for(Branch(p.branch)):
            rel = _grp(day_el, STEM_ELEMENT[stem])
            if not rel:
                continue
            s = _TEN_GOD[rel] * _BRANCH_POS_W[pos] * _STAGE_W[kind.value]
            total += s
    return total, [f"지장간 십성 합 {total:+.2f}"]


def _combination(pillars, day_el):
    branches = {Branch(p.branch) for _pos, p in _positions(pillars)}
    stems = {Stem(p.stem) for _pos, p in _positions(pillars)}
    by_elem: dict[Element, float] = {}

    def track(el: Element, k: float) -> None:
        if el not in by_elem or k > by_elem[el]:
            by_elem[el] = k

    for members, el, royal in THREE_HARMONY:
        if members <= branches:
            track(el, _COMBO_K["samhap_full"])
        elif royal in branches and len(members & branches) >= 2:
            track(el, _COMBO_K["samhap_half"])
    for members, el in DIRECTIONAL_COMBINATIONS:
        if members <= branches:
            track(el, _COMBO_K["banghap_full"])
        elif len(members & branches) == 2:
            track(el, _COMBO_K["banghap_half"])
    for pair, el in SIX_COMBINATIONS.items():
        if pair <= branches:
            track(el, _COMBO_K["yukhap"])

    total = 0.0
    lines: list[str] = []
    for el, k in by_elem.items():
        rel = _grp(day_el, el)
        s = _COMBO_REL.get(rel, 0) * k
        total += s
        lines.append(f"합국→{el}({rel}) {_COMBO_REL.get(rel, 0):+d}×{k} = {s:+.1f}")
    for pair, el in STEM_COMBINATIONS.items():
        if pair <= stems:
            rel = _grp(day_el, el)
            total += _STEMHAP_REL.get(rel, 0)
            lines.append(f"천간합→화기 {el}({rel}) {_STEMHAP_REL.get(rel, 0):+d}")
    return total, lines or ["합 없음"]


def _clash(pillars, day_el):
    items = [(pos, Branch(p.branch)) for pos, p in _positions(pillars)]
    total = 0.0
    lines: list[str] = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (pa, ba), (pb, bb) = items[i], items[j]
            if frozenset({ba, bb}) not in BRANCH_CLASHES:
                continue
            a_root = STEM_ELEMENT[main_hidden_stem(ba)] == day_el
            b_root = STEM_ELEMENT[main_hidden_stem(bb)] == day_el
            if (pa == "month" and a_root) or (pb == "month" and b_root):
                total -= 10
                lines.append(f"월지 통근 충 {ba}↔{bb} -10")
            elif a_root or b_root:
                total -= 8
                lines.append(f"통근 지지 충 {ba}↔{bb} -8")
            else:
                for br in (ba, bb):
                    if _grp(day_el, STEM_ELEMENT[main_hidden_stem(br)]) == "관성":
                        total += 5
                        lines.append(f"관성 {br} 충으로 약화 +5")
                        break
    return total, lines or ["충 없음"]


def _climate(pillars, day_el):
    mb = Branch(pillars.month.branch)
    branches = [Branch(p.branch) for _pos, p in _positions(pillars)]
    total = 0.0
    lines: list[str] = []
    if mb == Branch.JA and day_el == Element.FIRE:
        total -= 10
        lines.append("겨울 왕수절(子)+화 일간 -10")
    elif mb == Branch.JA and day_el == Element.WOOD:
        total -= 5
        lines.append("겨울 왕수절(子)+목 일간 -5")
    elif mb == Branch.O and day_el == Element.METAL:
        total -= 10
        lines.append("여름 왕화절(午)+금 일간 -10")
    elif mb == Branch.O and day_el == Element.WATER:
        total -= 8
        lines.append("여름 왕화절(午)+수 일간 -8")
    fire = sum(1 for b in branches if b in (Branch.SA, Branch.O, Branch.MI))
    dry_earth = sum(1 for b in branches if b in (Branch.SUL, Branch.MI))
    water = sum(1 for b in branches if b in (Branch.HAE, Branch.JA, Branch.CHUK))
    if fire >= 2 and dry_earth >= 1:
        total -= 8
        lines.append("화염건조 구조 -8")
    if water >= 3:
        total -= 8
        lines.append("한습 구조 -8")
    return total, lines or ["조후 보정 없음"]


def _jong_signal(pillars, day_stem: Stem, day_el: Element, root_total: float) -> dict:
    grp: dict[str, float] = {"비겁": 0.0, "인성": 0.0, "식상": 0.0, "재성": 0.0, "관성": 0.0}
    for pos in ("year", "month", "hour"):
        p = getattr(pillars, pos)
        if p is None:
            continue
        rel = _grp(day_el, STEM_ELEMENT[Stem(p.stem)])
        if rel:
            grp[rel] += 1.0
    for _pos, p in _positions(pillars):
        for stem, kind, _w in hidden_stems_for(Branch(p.branch)):
            rel = _grp(day_el, STEM_ELEMENT[stem])
            if rel:
                grp[rel] += _STAGE_W[kind.value]
    total = sum(grp.values()) or 1.0
    ilgan = (grp["비겁"] + grp["인성"]) / total
    external = (grp["식상"] + grp["재성"] + grp["관성"]) / total
    active = ilgan <= 0.40 and external >= 0.60 and root_total <= 15.0
    return {
        "active": active,
        "ilgan_group_ratio": round(ilgan, 3),
        "external_ratio": round(external, 3),
        "evidence": (
            f"일간그룹 {ilgan*100:.0f}% / 외부 {external*100:.0f}% / 통근 {root_total:+.1f}"
        ),
    }


def _label(score: float) -> str:
    for lo, hi, lab in _THRESHOLDS:
        if lo <= score <= hi:
            return lab
    return "중화"


def compute_v1(pillars: FourPillarsResult) -> dict:
    """8성분 합산 → score/label + 가종격 분기."""
    day_stem = Stem(pillars.day.stem)
    day_el = STEM_ELEMENT[day_stem]
    raw: list[tuple[str, float, list[str]]] = [
        ("month_command_score", *_month_command(pillars, day_el)),
        ("root_score", *_root(pillars, day_el)),
        ("revealed_stem_score", *_revealed(pillars, day_stem, day_el)),
        ("stem_ten_god_score", *_stem_ten_god(pillars, day_el)),
        ("hidden_stem_ten_god_score", *_hidden_ten_god(pillars, day_el)),
        ("combination_adjustment", *_combination(pillars, day_el)),
        ("clash_adjustment", *_clash(pillars, day_el)),
        ("climate_adjustment", *_climate(pillars, day_el)),
    ]
    components: dict[str, float] = {}
    traces: dict[str, list[str]] = {}
    total = 0.0
    root_total = 0.0
    for name, s, tr in raw:
        s = round(s, 2)
        components[name] = s
        traces[name] = tr
        total += s
        if name == "root_score":
            root_total = s
    total = round(total, 1)
    base = _label(round(total))
    jong = _jong_signal(pillars, day_stem, day_el, root_total)
    label = "중화" if jong["active"] else base
    return {
        "score": total, "label": label, "label_base": base,
        "components": components, "traces": traces,
        "root_total": root_total, "jong": jong,
    }


def is_borderline_v1(score: float) -> bool:
    return any(abs(score - b) <= 3 for b in _BOUNDARIES)
