"""신살 감지 + 집계 (주별/카테고리별/요약/강도).

전체 표시하되 use_for_yongsin_decision=False. 강도는 명세 §4 factor로 산출.
"""

from __future__ import annotations

from saju_shared_types.constants import BRANCH_INDEX, JANGSAENG_BRANCH
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.pillars import FourPillarsResult, Pillar
from saju_shared_types.sinsal import SinsalAnalysis, SinsalItem, SinsalSummary
from saju_shared_types.structure import StructureAnalysis

from . import sinsal_catalog as cat

_Detection = tuple[str, str, str, str]  # (name, category, position, basis)


def _positions(pillars: FourPillarsResult) -> list[tuple[str, Pillar]]:
    items = [("year", pillars.year), ("month", pillars.month), ("day", pillars.day)]
    if pillars.hour is not None:
        items.append(("hour", pillars.hour))
    return items


def _twelve_sinsal(ref: Branch, target: Branch) -> str:
    saengji = cat.TRINE_SAENGJI[ref]
    start = (BRANCH_INDEX[saengji] - 3) % 12
    off = (BRANCH_INDEX[target] - start) % 12
    return cat.TWELVE_SINSAL_ORDER[off]


def _detect(pillars: FourPillarsResult) -> list[_Detection]:
    out: list[_Detection] = []
    positions = _positions(pillars)
    day_stem = Stem(pillars.day.stem)
    year_branch = Branch(pillars.year.branch)

    # 12신살 (년지 기준) — 모든 주 지지에 1개씩.
    for pos, p in positions:
        name = _twelve_sinsal(year_branch, Branch(p.branch))
        out.append((name, "twelve_sinsal", pos, f"년지 {year_branch} 기준 {p.branch}=>{name}"))

    # 일간 기준 지지 타깃 신살.
    stem_branch_targets: list[tuple[str, list[Branch]]] = [
        ("천을귀인", cat.CHEONEUL.get(day_stem, [])),
        ("태극귀인", cat.TAEGEUK.get(day_stem, [])),
        ("문창귀인", [cat.MUNCHANG[day_stem]]),
        ("학당귀인", [JANGSAENG_BRANCH[day_stem]]),
        ("홍염", [cat.HONGYEOM[day_stem]]),
        ("금여", [cat.GEUMYEO[day_stem]]),
        ("암록", [cat.AMROK[day_stem]]),
    ]
    if day_stem in cat.YANGIN:
        stem_branch_targets.append(("양인", [cat.YANGIN[day_stem]]))
    for name, targets in stem_branch_targets:
        meta = cat.CATALOG_META[name]
        for pos, p in positions:
            if Branch(p.branch) in targets:
                out.append((name, meta["category"], pos, f"일간 {day_stem} 기준 {p.branch}"))

    # 월덕귀인(월지→천간) / 천덕귀인(월지→천간 or 지지)
    month_branch = Branch(pillars.month.branch)
    wd = cat.WOLDEOK.get(month_branch)
    for pos, p in positions:
        if wd is not None and Stem(p.stem) == wd:
            out.append(("월덕귀인", "noble_stars", pos, f"월지 {month_branch} 기준 천간 {wd}"))
    cd = cat.CHEONDEOK.get(month_branch)
    for pos, p in positions:
        if isinstance(cd, Stem) and Stem(p.stem) == cd:
            out.append(("천덕귀인", "noble_stars", pos, f"월지 {month_branch} 기준 천간 {cd}"))
        elif isinstance(cd, Branch) and Branch(p.branch) == cd:
            out.append(("천덕귀인", "noble_stars", pos, f"월지 {month_branch} 기준 지지 {cd}"))

    # 괴강 / 백호 (주 간지)
    for pos, p in positions:
        gz = (Stem(p.stem), Branch(p.branch))
        if gz in cat.GOEGANG:
            out.append(("괴강", "health_risk", pos, f"{p.stem}{p.branch} 괴강"))
        if gz in cat.BAEKHO:
            out.append(("백호", "health_risk", pos, f"{p.stem}{p.branch} 백호대살"))

    # 현침 (글자)
    for pos, p in positions:
        if Stem(p.stem) in cat.HYEONCHIM_STEMS or Branch(p.branch) in cat.HYEONCHIM_BRANCHES:
            out.append(("현침", "health_risk", pos, f"{p.stem}{p.branch} 현침 글자"))

    # 공망 (일주 旬 기준 공망 지지가 다른 주에 있을 때)
    void = set(pillars.gongmang_branches)
    for pos, p in positions:
        if pos != "day" and p.branch in void:
            out.append(("공망", "miscellaneous", pos, f"일주 기준 공망 {p.branch}"))

    # 귀문관살 / 원진 (두 지지 쌍)
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            pa, a = positions[i]
            pb, b = positions[j]
            pair = frozenset({Branch(a.branch), Branch(b.branch)})
            label = f"{a.branch}-{b.branch}"
            if len(pair) == 2 and pair in cat.GWIMUN:
                for pos in (pa, pb):
                    out.append(("귀문관살", "isolation_conflict", pos, f"{label} 귀문"))
            if len(pair) == 2 and pair in cat.WONJIN:
                for pos in (pa, pb):
                    out.append(("원진", "isolation_conflict", pos, f"{label} 원진"))
    return out


def _intensity(name: str, position: str, repeated: bool, void: bool, overlaps: bool) -> str:
    score = 0.3
    if repeated:
        score += 0.20
    if position in ("month", "day"):
        score += 0.15
    if position == "day":
        score += 0.12
    if overlaps:
        score += 0.12
    if void:
        score -= 0.05
    if score >= 0.75:
        return "very_high"
    if score >= 0.6:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def analyze_sinsal(
    pillars: FourPillarsResult, structure: StructureAnalysis
) -> SinsalAnalysis:
    detections = _detect(pillars)
    name_counts: dict[str, int] = {}
    for name, _c, _p, _b in detections:
        name_counts[name] = name_counts.get(name, 0) + 1

    pillar_map = {pos: p for pos, p in _positions(pillars)}
    void = set(pillars.gongmang_branches)

    full: list[SinsalItem] = []
    for name, category, position, basis in detections:
        p = pillar_map[position]
        meta = cat.CATALOG_META.get(name, {"polarity": "neutral", "tags": []})
        overlaps_rel = [
            f"{i.relation_type}:{'-'.join(i.members)}"
            for i in structure.interactions
            if position in i.positions
            and i.relation_type in ("clash", "punishment", "self_punishment", "harm")
        ]
        is_void = p.branch in void
        repeated = name_counts[name] > 1
        intensity = _intensity(name, position, repeated, is_void, bool(overlaps_rel))
        polarity = meta["polarity"]
        full.append(SinsalItem(
            name=name, category=category, position=position, basis=basis,
            palace=p.palace,
            ten_god_context=p.branch_main_ten_god,
            element_context=p.branch_element,
            intensity=intensity,
            repeated=repeated,
            activated_by_relations=overlaps_rel,
            interpretation_tags=list(meta.get("tags", [])),
            caution_tags=["주의"] if polarity == "caution" else [],
            use_for_yongsin_decision=False,
        ))

    # by_pillar/by_category 는 이름 목록(중복 제거, 순서 유지). 상세는 full_list 참조.
    by_pillar: dict[str, list[str]] = {"year": [], "month": [], "day": [], "hour": []}
    by_category: dict[str, list[str]] = {c: [] for c in cat.ALL_CATEGORIES}
    for item in full:
        if item.name not in by_pillar.setdefault(item.position, []):
            by_pillar[item.position].append(item.name)
        if item.name not in by_category.setdefault(item.category, []):
            by_category[item.category].append(item.name)

    summary = SinsalSummary(
        repeated=sorted({n for n, c in name_counts.items() if c > 1}),
        major_positive=sorted({
            i.name for i in full
            if cat.CATALOG_META.get(i.name, {}).get("polarity") == "positive"
        }),
        major_caution=sorted({
            i.name for i in full
            if cat.CATALOG_META.get(i.name, {}).get("polarity") == "caution"
        }),
        palace_sensitive=sorted({i.name for i in full if i.position in ("day", "month")}),
        structure_overlapped=sorted({i.name for i in full if i.activated_by_relations}),
    )

    warnings: list[str] = []
    if pillars.hour is None:
        warnings.append("hour_unknown: 시주 신살을 계산할 수 없습니다.")

    return SinsalAnalysis(
        summary=summary,
        by_pillar=by_pillar,
        by_category={k: v for k, v in by_category.items() if v},
        full_list=full,
        hour_unknown=pillars.hour is None,
        warnings=warnings,
    )
