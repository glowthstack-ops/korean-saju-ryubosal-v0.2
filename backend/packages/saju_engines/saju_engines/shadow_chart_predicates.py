"""Shadow 차트 탐색 predicate primitives — 엔진 산출(calculate 결과)로 구조를 검증한다.

손으로 "이 생일이 관살태왕"이라 단정하지 않고, 각 predicate 가 ManseV2Result 를 받아 목표 구조의
성립 여부를 bool 로 판정한다. find_shadow_charts.py 가 합성 birth 후보를 이 predicate 로 검증해
**FOUND/BEST_MATCH 인 BirthInput 만** charts.jsonl 에 채택한다(검증 도구·운영 미연결).

규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §13-5
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import NamedTuple

from saju_manse_analysis.yongsin.operational_role_config import SHADOW_ROLE_WEIGHT

from saju_shared_types.manse_result import ManseV2Result

from .event_scoring import favorability_map
from .shadow_scoring import operational_shadow_weights


class Pred(NamedTuple):
    """이름표 달린 predicate — coverage_report 의 satisfied/missing 표기용."""

    name: str
    fn: Callable[[ManseV2Result], bool]


# 천간합 파트너(쟁합 탐지용).
_STEM_HAP = {"甲": "己", "己": "甲", "乙": "庚", "庚": "乙", "丙": "辛",
             "辛": "丙", "丁": "壬", "壬": "丁", "戊": "癸", "癸": "戊"}


def _ya(r: ManseV2Result):
    return r.yongsin_analysis


def yongsin_element(r: ManseV2Result) -> str | None:
    ya = _ya(r)
    return ya.final.get("yongsin") if ya and ya.final else None


def yongsin_role(r: ManseV2Result):
    """용신 오행의 operational ElementRole(operability·factors 보유)."""
    yel = yongsin_element(r)
    ya = _ya(r)
    if not ya or yel is None:
        return None
    for er in ya.operational_roles:
        if er.element == yel:
            return er
    return None


def _dominant_group(r: ManseV2Result) -> str | None:
    g = r.force_analysis.ten_gods.groups if r.force_analysis else {}
    return max(g, key=lambda k: g[k]) if g else None


# ── primitive factory ──────────────────────────────────────────────
def strength_in(bands: list[str]) -> Pred:
    bs = set(bands)
    return Pred(f"strength∈{'/'.join(bands)}",
               lambda r: r.force_analysis is not None
               and r.force_analysis.strength.band in bs)


def element_pct_ge(el: str, x: float) -> Pred:
    return Pred(f"{el}≥{x}%",
               lambda r: r.force_analysis is not None
               and r.force_analysis.five_elements.effective_percent.get(el, 0.0) >= x)


def excessive(el: str) -> Pred:
    return Pred(f"{el}과다",
               lambda r: r.force_analysis is not None
               and el in r.force_analysis.five_elements.excessive_elements)


def dominant_group(group: str) -> Pred:
    return Pred(f"최다십성={group}", lambda r: _dominant_group(r) == group)


def month_branch_in(branches: list[str]) -> Pred:
    bs = set(branches)
    return Pred(f"월지∈{'/'.join(branches)}",
               lambda r: r.pillars is not None and r.pillars.month.branch in bs)


def has_operational_role(label: str) -> Pred:
    return Pred(f"작동역할:{label}",
               lambda r: bool(_ya(r))
               and any(er.operational_role == label for er in _ya(r).operational_roles))


def yongsin_factor(f: str) -> Pred:
    def fn(r: ManseV2Result) -> bool:
        yr = yongsin_role(r)
        return yr is not None and f in yr.operability_factors
    return Pred(f"용신factor:{f}", fn)


def yongsin_operability_below(x: float) -> Pred:
    def fn(r: ManseV2Result) -> bool:
        yr = yongsin_role(r)
        return yr is not None and yr.operability is not None and yr.operability < x
    return Pred(f"용신operability<{x}", fn)


def confirmed_transform() -> Pred:
    return Pred("합화confirmed",
               lambda r: r.structure_analysis is not None
               and any(t.confirmed for t in r.structure_analysis.transformed_candidates))


def bind_transform() -> Pred:
    """합이불화(bind) — 합은 있으나(exists) 化 미성립(not confirmed/possible)."""
    def fn(r: ManseV2Result) -> bool:
        if not r.structure_analysis:
            return False
        return any(getattr(t, "exists", False) and not t.confirmed
                   and not getattr(t, "possible", False)
                   for t in r.structure_analysis.transformed_candidates)
    return Pred("합반bind", fn)


def contend_transform() -> Pred:
    """쟁합 — 동일 천간 2개가 같은 합 파트너를 다툼."""
    def fn(r: ManseV2Result) -> bool:
        p = r.pillars
        if p is None:
            return False
        stems = [pp.stem for pp in (p.year, p.month, p.day, p.hour) if pp is not None]
        for s, cnt in Counter(stems).items():
            if cnt >= 2 and _STEM_HAP.get(s) in stems:
                return True
        return False
    return Pred("쟁합contend", fn)


def away_transform() -> Pred:
    """합거(away) 근사 — 化 미성립 합이 기신/구신 오행을 묶음(제거 유익)."""
    def fn(r: ManseV2Result) -> bool:
        ya = _ya(r)
        if not ya or not r.structure_analysis:
            return False
        harmful = {ya.final.get("gisin"), ya.final.get("gusin")}
        return any(getattr(t, "exists", False) and not t.confirmed
                   and getattr(t, "target_element", None) in harmful
                   for t in r.structure_analysis.transformed_candidates)
    return Pred("합거away", fn)


def geokguk_special(keywords: list[str]) -> Pred:
    """main_structure(정격 명칭) 키워드 매칭 — 양인/건록 등 일반 격국용."""
    def fn(r: ManseV2Result) -> bool:
        g = r.geokguk
        if not g:
            return False
        sp = g.special_pattern
        name = sp.get("name", "") if isinstance(sp, dict) else ""
        text = f"{name}{g.main_structure or ''}"
        return any(k in text for k in keywords)
    return Pred(f"격국∋{'/'.join(keywords)}", fn)


def special_pattern_type(t: str) -> Pred:
    """geokguk.special_pattern.type — 'dominant'(전왕/일행득기) / 'follow'(종격)."""
    def fn(r: ManseV2Result) -> bool:
        g = r.geokguk
        sp = g.special_pattern if g else None
        return isinstance(sp, dict) and sp.get("type") == t
    return Pred(f"특수격type={t}", fn)


def hap_note_enriched() -> Pred:
    """일반 합 맥락 — operational_role note/positive/negative 에 합 맥락 enrich."""
    def fn(r: ManseV2Result) -> bool:
        ya = _ya(r)
        if not ya:
            return False
        for er in ya.operational_roles:
            blob = (er.note or "") + " ".join(er.positive_when) + " ".join(er.negative_when)
            if "합" in blob:
                return True
        return False
    return Pred("합맥락enrich", fn)


# ── expected_shadow (사후 검증·선택 게이트 아님) ──────────────────────
def _shadow_below_legacy(r: ManseV2Result, el: str | None) -> bool:
    ya = _ya(r)
    if not ya or el is None:
        return False
    sw = operational_shadow_weights(ya).get(el)
    lr = favorability_map(r).get(el)
    lw = SHADOW_ROLE_WEIGHT.get(lr, 0.0) if lr else 0.0
    return sw is not None and sw < lw


def expect_yongsin_shadow_down() -> Pred:
    return Pred("용신 shadow 하향", lambda r: _shadow_below_legacy(r, yongsin_element(r)))


def expect_role_shadow_down(label: str) -> Pred:
    """해당 operational_role 라벨을 가진 오행의 shadow 가 legacy 대비 하향인지."""
    def fn(r: ManseV2Result) -> bool:
        ya = _ya(r)
        if not ya:
            return False
        el = next((er.element for er in ya.operational_roles
                   if er.operational_role == label), None)
        return _shadow_below_legacy(r, el)
    return Pred(f"{label} shadow 하향", fn)


def invariant_additive() -> Pred:
    """2계층 공존 — canonical/operational/final 모두 존재(operational 이 무엇도 덮지 않음)."""
    def fn(r: ManseV2Result) -> bool:
        ya = _ya(r)
        return bool(ya and ya.canonical_roles and ya.operational_roles and ya.final)
    return Pred("additive(2계층 공존)", fn)
