"""신살 감지 + 집계 (주별/카테고리별/요약/강도).

전체 표시하되 use_for_yongsin_decision=False. 강도는 명세 §4 factor로 산출.
"""

from __future__ import annotations

from saju_shared_types.constants import BRANCH_INDEX, JANGSAENG_BRANCH
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.pillars import FourPillarsResult, Pillar
from saju_shared_types.sinsal import (
    LuckSinsal,
    SinsalAnalysis,
    SinsalItem,
    SinsalSummary,
)
from saju_shared_types.structure import StructureAnalysis
from saju_shared_types.twelve_sinsal import branch_of_sinsal, trine_group_label

from . import sinsal_catalog as cat

_Detection = tuple[str, str, str, str]  # (name, category, position, basis)


def _positions(pillars: FourPillarsResult) -> list[tuple[str, Pillar]]:
    items = [("year", pillars.year), ("month", pillars.month), ("day", pillars.day)]
    if pillars.hour is not None:
        items.append(("hour", pillars.hour))
    return items


def _detect(pillars: FourPillarsResult) -> list[_Detection]:
    out: list[_Detection] = []
    positions = _positions(pillars)
    day_stem = Stem(pillars.day.stem)
    year_branch = Branch(pillars.year.branch)
    day_branch = Branch(pillars.day.branch)

    # 역마·도화·화개 — 값 3종 분리(2026-10-06 데굴님 승인): ①글자 보유=표지(이동지·사정지·사고지)
    # ②성립=연지·일지 삼합국 기준 상대 12신살(역마살·년살→'도화'·화개살) ③활성화=구조 패턴·기회
    # 엔진(여기선 안 봄). 위치별 12신살 전체는 펼치지 않는다.
    for pos, p in positions:
        for marker, group, what in _BRANCH_MARKERS:
            if Branch(p.branch) in group:
                out.append((marker, cat.CATALOG_META[marker]["category"], pos,
                            f"{p.branch} {what}(글자) — 보유 표지, 성립과 별개"))
    out.extend(_relative_trine_sinsal(positions, year_branch, day_branch))

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

    # 추가 신살 (표준 명리표) ---------------------------------------------------
    # 일간 → 지지 단일 타깃 (천록/천주/관귀학관/문곡/낙정관/비인).
    extra_stem: list[tuple[str, Branch | None]] = [
        ("천록귀인", cat.CHEONROK.get(day_stem)),
        ("천주귀인", cat.CHEONJU.get(day_stem)),
        ("관귀학관", cat.GWANGWI.get(day_stem)),
        ("문곡귀인", cat.MUNGOK.get(day_stem)),
        ("낙정관살", cat.NAKJEONG.get(day_stem)),
        ("비인살", cat.BIIN.get(day_stem)),
    ]
    for name, tgt in extra_stem:
        if tgt is None:
            continue
        meta = cat.CATALOG_META[name]
        for pos, p in positions:
            if Branch(p.branch) == tgt:
                out.append((name, meta["category"], pos, f"일간 {day_stem} 기준 {p.branch}"))

    # 월지 기준 (천의성=월지 직전, 단교관살).
    month_targets: list[tuple[str, Branch]] = [
        ("천의성", cat.branch_at(BRANCH_INDEX[month_branch] - 1)),
        ("단교관살", cat.DANGYO[month_branch]),
    ]
    for name, tgt in month_targets:
        meta = cat.CATALOG_META[name]
        for pos, p in positions:
            if Branch(p.branch) == tgt:
                out.append((name, meta["category"], pos, f"월지 {month_branch} 기준 {p.branch}"))

    # 년지 기준 (고신/과숙).
    for name, table in [("고신살", cat.GOSHIN), ("과숙살", cat.GWASUK)]:
        tgt = table[year_branch]
        meta = cat.CATALOG_META[name]
        for pos, p in positions:
            if Branch(p.branch) == tgt:
                out.append((name, meta["category"], pos, f"년지 {year_branch} 기준 {p.branch}"))

    # 격각살: 일지 +2 지지(자기 자리 제외).
    gyeokgak = cat.branch_at(BRANCH_INDEX[day_branch] + 2)
    for pos, p in positions:
        if pos != "day" and Branch(p.branch) == gyeokgak:
            out.append(("격각살", "isolation_conflict", pos, f"일지 {day_branch} 격각 {p.branch}"))

    # 일덕 / 일귀 (일주 간지 자체).
    day_gz = (day_stem, day_branch)
    if day_gz in cat.ILDEOK:
        out.append(("일덕", "noble_stars", "day", f"{pillars.day.stem}{pillars.day.branch} 일덕"))
    if day_gz in cat.ILGWI:
        out.append(("일귀", "noble_stars", "day", f"{pillars.day.stem}{pillars.day.branch} 일귀"))

    # 천문성: 戌·亥 글자(지지 기준, 위치 무관).
    for pos, p in positions:
        if Branch(p.branch) in cat.CHEONMUN_BRANCHES:
            out.append(("천문성", "spiritual_intuition", pos, f"{p.branch} 천문(글자)"))

    # 천라지망: 戌亥(천라)·辰巳(지망)가 모두 명식에 있을 때.
    chart_branches = {Branch(p.branch) for _pos, p in positions}
    for pair_b, kind in [(cat.CHEONRA, "천라(戌亥)"), (cat.JIMANG, "지망(辰巳)")]:
        if set(pair_b) <= chart_branches:
            for pos, p in positions:
                if Branch(p.branch) in pair_b:
                    out.append(("천라지망", "isolation_conflict", pos, kind))

    # ── 2026-09-18 추가 7종(통설표) — 보조 상징. 성별 부재라 연간 음양으로 陽/陰年을 대신한다.
    year_stem = Stem(pillars.year.stem)
    yang_year = year_stem in cat.YANG_STEMS
    if day_gz in cat.EUMYANG_CHACHAK:
        day_txt = f"{day_gz[0]}{day_gz[1]}"
        out.append(("음양차착", "relationship_social", "day", f"{day_txt} 음양차착(일주)"))
    if day_gz in cat.GORAN:
        out.append(("고란살", "isolation_conflict", "day", f"{day_gz[0]}{day_gz[1]} 고란(일주)"))
    if day_branch in cat.TANGHWA_DAY_BRANCHES:
        out.append(("탕화살", "health_risk", "day", f"일지 {day_branch} 탕화(상징)"))
    yb = BRANCH_INDEX[year_branch]
    year_targets: list[tuple[str, Branch, str]] = [
        ("상문", cat.branch_at(yb + cat.SANGMUN_OFFSET), "연지 앞 두 자리"),
        ("조객", cat.branch_at(yb + cat.JOGAEK_OFFSET), "연지 뒤 두 자리"),
    ]
    gu, gyo = cat.GUGYO_OFFSETS_YANG if yang_year else tuple(-o for o in cat.GUGYO_OFFSETS_YANG)
    year_targets.append(("구교살", cat.branch_at(yb + gu), "勾(연지 기준)"))
    year_targets.append(("구교살", cat.branch_at(yb + gyo), "絞(연지 기준)"))
    yuan_off = cat.WONJIN_YUAN_OFFSET_YANG if yang_year else cat.WONJIN_YUAN_OFFSET_YIN
    year_targets.append(("원진(元辰)", cat.branch_at(yb + yuan_off), "연지 기준 元辰(연간 음양)"))
    for name, tgt, basis_txt in year_targets:
        meta = cat.CATALOG_META[name]
        for pos, p in positions:
            if pos != "year" and Branch(p.branch) == tgt:
                basis = f"년지 {year_branch} 기준 {p.branch} — {basis_txt}"
                out.append((name, meta["category"], pos, basis))
    # 협록(夾祿): 일간 정록(L)을 두 지지가 L-1·L+1로 끼면(夾) 성립.
    rok = cat.CHEONROK[day_stem]
    prev_b = cat.branch_at(BRANCH_INDEX[rok] - 1)
    next_b = cat.branch_at(BRANCH_INDEX[rok] + 1)
    if prev_b in chart_branches and next_b in chart_branches:
        for pos, p in positions:
            if Branch(p.branch) in (prev_b, next_b):
                out.append(("협록", "wealth_status", pos, f"정록 {rok} 협({prev_b}{next_b})"))
    return out


#: (표시명, 12신살명) — 집계기 표시명은 기존 소비처(사전·FE) 호환을 위해 유지한다.
_RELATIVE_TRINE_SINSAL: tuple[tuple[str, str], ...] = (
    ("역마살", "역마살"), ("도화", "년살"), ("화개살", "화개살"),
)
#: (표지명, 글자군, 설명) — 보유 표지.
_BRANCH_MARKERS: tuple[tuple[str, frozenset[Branch], str], ...] = (
    ("이동지", cat.SASAENG, "사생지"),
    ("사정지", cat.SAJEONG, "왕지"),
    ("사고지", cat.SAGO, "고지"),
)


def _relative_trine_sinsal(
    positions: list[tuple[str, Pillar]], year_branch: Branch, day_branch: Branch,
) -> list[_Detection]:
    """연지·일지 삼합국 기준 상대 역마·도화(년살)·화개 — 같은 자리에 두 기준이 겹치면 1건으로 병기.

    글자살(寅申巳亥·子午卯酉·辰戌丑未 보유)로 판정하지 않는다 — structure_patterns.json
    `yeokma_rule`(2026-07-23 데굴님 정정)과 같은 원칙을 세 신살 모두에 적용한다(2026-10-06 통일).
    """
    bases = (("연지", year_branch), ("일지", day_branch))
    out: list[_Detection] = []
    for display, sinsal in _RELATIVE_TRINE_SINSAL:
        by_pos: dict[str, list[str]] = {}
        for label, base in bases:
            target = branch_of_sinsal(base, sinsal)
            for pos, p in positions:
                if Branch(p.branch) == target:
                    by_pos.setdefault(pos, []).append(
                        f"{label} {base.value} 기준 {display}({trine_group_label(base)}국)"
                    )
        meta = cat.CATALOG_META[display]
        out.extend(
            (display, meta["category"], pos, " · ".join(dict.fromkeys(txt)))
            for pos, txt in by_pos.items()
        )
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


# 표시 정렬 우선순위: 길신 → 신살 → 흉성.
_POLARITY_ORDER = {"positive": 0, "neutral": 1, "caution": 2}


def sinsal_for_luck(
    pillars: FourPillarsResult, stem: Stem, branch: Branch
) -> list[LuckSinsal]:
    """운(대운/세운/월운/일운) 간지가 불러오는 신살/길신/흉성을 산출.

    운의 간지를 새로운 자리(位)로 보고 원국 기준점(일간·월지·년지·일지)과 운 간지 자체에
    대조한다. 단일 간지에 적용 가능한 신살과, 운이 원국 구조 신살(천라지망·협록)을
    완성하는 경우를 포함한다.

    복음(伏吟): 운의 간지가 원국 특정 주와 완전히 같으면 표시한다. 일주복음은 가장
    민감하므로 기존 호환 이름 "복음"을 유지하고 목록 맨 앞에 둔다.

    Args:
        pillars: 원국 사주(기준점 제공).
        stem: 운의 천간.
        branch: 운의 지지.

    Returns:
        복음(해당 시)→길신→신살→흉성 순으로 정렬된 LuckSinsal 목록(중복 제거).
    """
    day_stem = Stem(pillars.day.stem)
    month_branch = Branch(pillars.month.branch)
    year_branch = Branch(pillars.year.branch)
    day_branch = Branch(pillars.day.branch)
    natal_branches = {Branch(p.branch) for _pos, p in _positions(pillars)}

    names: list[str] = []

    def add(name: str) -> None:
        if name not in names:
            names.append(name)

    # 글자 보유 표지(이동지·사정지·사고지) — 성립과 별개.
    for marker, group, _what in _BRANCH_MARKERS:
        if branch in group:
            add(marker)
    # 역마·도화(년살)·화개 성립 — 연지·일지 삼합국 기준 상대 12신살(운 지지가 그 자리일 때).
    for display, sinsal in _RELATIVE_TRINE_SINSAL:
        if any(branch == branch_of_sinsal(base, sinsal) for base in (year_branch, day_branch)):
            add(display)

    # 일간 기준 지지 타깃.
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
    for nm, targets in stem_branch_targets:
        if branch in targets:
            add(nm)

    # 추가 일간 기준 단일 타깃(천록/천주/관귀학관/문곡/낙정관/비인).
    extra_stem: list[tuple[str, Branch | None]] = [
        ("천록귀인", cat.CHEONROK.get(day_stem)),
        ("천주귀인", cat.CHEONJU.get(day_stem)),
        ("관귀학관", cat.GWANGWI.get(day_stem)),
        ("문곡귀인", cat.MUNGOK.get(day_stem)),
        ("낙정관살", cat.NAKJEONG.get(day_stem)),
        ("비인살", cat.BIIN.get(day_stem)),
    ]
    for nm, tgt in extra_stem:
        if tgt is not None and branch == tgt:
            add(nm)

    # 월덕(월지→천간) / 천덕(월지→천간 or 지지).
    wd = cat.WOLDEOK.get(month_branch)
    if wd is not None and stem == wd:
        add("월덕귀인")
    cd = cat.CHEONDEOK.get(month_branch)
    if isinstance(cd, Stem) and stem == cd:
        add("천덕귀인")
    elif isinstance(cd, Branch) and branch == cd:
        add("천덕귀인")

    # 월지 기준(천의성=월지 직전, 단교관살).
    if branch == cat.branch_at(BRANCH_INDEX[month_branch] - 1):
        add("천의성")
    if branch == cat.DANGYO[month_branch]:
        add("단교관살")

    # 년지 기준(고신/과숙).
    if branch == cat.GOSHIN[year_branch]:
        add("고신살")
    if branch == cat.GWASUK[year_branch]:
        add("과숙살")

    # 일지 기준 격각살(일지 +2 지지).
    if branch == cat.branch_at(BRANCH_INDEX[day_branch] + 2):
        add("격각살")

    # 괴강 / 백호 (운 간지 자체).
    gz = (stem, branch)
    if gz in cat.GOEGANG:
        add("괴강")
    if gz in cat.BAEKHO:
        add("백호")

    # 현침(운 글자).
    if stem in cat.HYEONCHIM_STEMS or branch in cat.HYEONCHIM_BRANCHES:
        add("현침")

    # 천문성(운 지지 戌·亥).
    if branch in cat.CHEONMUN_BRANCHES:
        add("천문성")

    # 귀문관살 / 원진 (운 지지 ↔ 원국 지지 쌍).
    for nb in natal_branches:
        pair = frozenset({branch, nb})
        if len(pair) == 2 and pair in cat.GWIMUN:
            add("귀문관살")
        if len(pair) == 2 and pair in cat.WONJIN:
            add("원진")

    # 협록(夾祿): 일간 정록(L)의 양 협지(L-1·L+1) 중 운이 한쪽, 원국이 다른 한쪽이면 완성.
    rok = cat.CHEONROK[day_stem]
    prev_b = cat.branch_at(BRANCH_INDEX[rok] - 1)
    next_b = cat.branch_at(BRANCH_INDEX[rok] + 1)
    if branch == prev_b and next_b in natal_branches:
        add("협록")
    elif branch == next_b and prev_b in natal_branches:
        add("협록")

    # 천라지망: 천라(戌亥)·지망(辰巳) 짝 중 운이 한쪽, 원국이 나머지 한쪽이면 완성.
    for pair_b in (cat.CHEONRA, cat.JIMANG):
        if branch in pair_b:
            other = pair_b[0] if branch == pair_b[1] else pair_b[1]
            if other in natal_branches:
                add("천라지망")

    items = [
        LuckSinsal(
            name=nm,
            polarity=cat.CATALOG_META.get(nm, {}).get("polarity", "neutral"),
        )
        for nm in names
    ]
    items.sort(key=lambda s: _POLARITY_ORDER.get(s.polarity, 1))

    # 복음: 운 간지 == 원국 주 간지. 일주복음은 기존 호환을 위해 이름 "복음" 유지.
    labels = {"year": "연주", "month": "월주", "day": "일주", "hour": "시주"}
    matches: list[LuckSinsal] = []
    for pos, p in _positions(pillars):
        if stem == Stem(p.stem) and branch == Branch(p.branch):
            name = "복음" if pos == "day" else f"복음({labels[pos]})"
            matches.append(LuckSinsal(name=name, polarity="caution"))
    if matches:
        items = matches + [i for i in items if not i.name.startswith("복음")]
    return items


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
        warnings.append("시간 미상: 시주 신살을 계산할 수 없습니다.")

    day_stem = Stem(pillars.day.stem)
    return SinsalAnalysis(
        summary=summary,
        by_pillar=by_pillar,
        by_category={k: v for k, v in by_category.items() if v},
        full_list=full,
        cheoneul_targets=[str(b) for b in cat.CHEONEUL.get(day_stem, [])],
        hour_unknown=pillars.hour is None,
        warnings=warnings,
    )
