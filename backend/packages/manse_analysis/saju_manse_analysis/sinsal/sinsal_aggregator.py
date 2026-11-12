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
from saju_shared_types.twelve_sinsal import (
    TWELVE_SINSAL_ORDER,
    TWELVE_SINSAL_POSITIONAL,
    branch_of_sinsal,
    relative_twelve_sinsal,
    self_sinsal_bases,
    trine_group_label,
)

from . import sinsal_catalog as cat

_Detection = tuple[str, str, str, str]  # (name, category, position, basis)


def _positions(pillars: FourPillarsResult) -> list[tuple[str, Pillar]]:
    items = [("year", pillars.year), ("month", pillars.month), ("day", pillars.day)]
    if pillars.hour is not None:
        items.append(("hour", pillars.hour))
    return items


def _yangnam_eumnyeo(year_stem: Stem, gender: str | None) -> bool | None:
    """陽男陰女 여부 — 양간년 남성·음간년 여성이면 True, 陰男陽女면 False, 성별 미상이면 None."""
    if gender not in ("male", "female"):
        return None
    return (year_stem in cat.YANG_STEMS) == (gender == "male")


def _detect(pillars: FourPillarsResult, gender: str | None = None) -> list[_Detection]:
    """원국 신살 감지.

    Args:
        pillars: 원국 사주.
        gender: 'male'/'female'/그 외(미상). 원진(元辰)·구교살의 陽男陰女 구분에만 쓴다.
    """
    out: list[_Detection] = []
    positions = _positions(pillars)
    day_stem = Stem(pillars.day.stem)
    year_branch = Branch(pillars.year.branch)
    day_branch = Branch(pillars.day.branch)

    # 역마·도화·화개 — 값 3종 분리(2026-10-06 데굴님 승인): ①글자 보유=표지(이동지·사정지·사고지)
    # ②성립=삼합국 기준 상대 12신살(역마살·년살→'도화'·화개살). 기준 자리는 역마·화개가 일지
    # (SELF_SINSAL_BASE_SLOTS — 2026-11-12 부터 연지 제외), 도화만 연지·일지(DOHWA_BASE_SLOTS)
    # ③활성화=구조 패턴·기회 엔진(여기선 안 봄). 자리별 9종은 `_positional_twelve_sinsal` 이 낸다.
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
        ("홍염", [cat.HONGYEOM[day_stem], *cat.HONGYEOM_EXTRA.get(day_stem, [])]),
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

    # 괴강 / 백호 — 일주 기준(2026-11-12 데굴님 결정). 일주가 그 간지일 때만 성립하고, 그 전제에서
    # 다른 기둥의 해당 간지도 함께 인정한다. 일주가 아니면 연·월·시에 있어도 판정하지 않는다
    # (삼명통회 "此格有四日", 나무위키·위키백과 — 종전에는 모든 기둥에 독립으로 판정했다).
    for name, gz_table, label in (
        ("괴강", cat.GOEGANG, "괴강"), ("백호", cat.BAEKHO, "백호대살"),
    ):
        if (day_stem, day_branch) not in gz_table:
            continue
        for pos, p in positions:
            if (Stem(p.stem), Branch(p.branch)) in gz_table:
                basis = f"{p.stem}{p.branch} {label}" + ("" if pos == "day" else "(일주 성립 전제)")
                out.append((name, "health_risk", pos, basis))

    # 천사(天赦) — 월지 계절별 일주(2026-10-15 추가, evidence 전용). 일주 한 자리에만 성립.
    cheonsa = cat.CHEONSA.get(month_branch)
    if cheonsa is not None and (day_stem, day_branch) == cheonsa:
        out.append(("천사", "noble_stars", "day",
                    f"월지 {month_branch} 계절 기준 일주 {pillars.day.ganji} 천사"))

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

    # 격각살: 일지 +2 지지가 시지일 때(2026-11-12 교정 — 통설 원칙은 일지→시지. 종전에는 연·월
    # 지지에도 같은 무게로 판정했다).
    gyeokgak = cat.branch_at(BRANCH_INDEX[day_branch] + 2)
    for pos, p in positions:
        if pos == "hour" and Branch(p.branch) == gyeokgak:
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

    # ── 2026-09-18 추가 7종(통설표) — 보조 상징. 원진(元辰)·구교는 陽男陰女 구분에 성별을 쓴다.
    year_stem = Stem(pillars.year.stem)
    yangnam_eumnyeo = _yangnam_eumnyeo(year_stem, gender)
    if day_gz in cat.EUMYANG_CHACHAK:
        day_txt = f"{day_gz[0]}{day_gz[1]}"
        out.append(("음양차착", "relationship_social", "day", f"{day_txt} 음양차착(일주)"))
    if day_gz in cat.GORAN:
        out.append(("고란살", "isolation_conflict", "day", f"{day_gz[0]}{day_gz[1]} 고란(일주)"))
    # 탕화: 일지 丑·寅·午 + 월지·시지에 동반 글자(2026-11-12 — 일지 단독 판정에서 좁힘).
    companions = cat.TANGHWA_COMPANIONS.get(day_branch, frozenset())
    tanghwa_with = [
        p.branch for pos, p in positions
        if pos in cat.TANGHWA_COMPANION_POSITIONS and Branch(p.branch) in companions
    ]
    if tanghwa_with:
        out.append((
            "탕화살", "health_risk", "day",
            f"일지 {day_branch} + 동반 글자 {'·'.join(dict.fromkeys(tanghwa_with))} 탕화(상징)",
        ))
    yb = BRANCH_INDEX[year_branch]
    year_targets: list[tuple[str, Branch, str]] = [
        ("상문", cat.branch_at(yb + cat.SANGMUN_OFFSET), "연지 앞 두 자리"),
        ("조객", cat.branch_at(yb + cat.JOGAEK_OFFSET), "연지 뒤 두 자리"),
    ]
    # 구교: 두 자리(±3) 모두 구교살. 勾/絞 표기는 陽男陰女(勾=+3)·陰男陽女(勾=−3),
    # 성별 미상이면 생략.
    fwd, back = cat.GUGYO_OFFSETS_YANG
    if yangnam_eumnyeo is None:
        gugyo_labels = ((fwd, "앞 세 자리(연지 기준)"), (back, "뒤 세 자리(연지 기준)"))
    elif yangnam_eumnyeo:
        gugyo_labels = ((fwd, "勾(연지 기준)"), (back, "絞(연지 기준)"))
    else:
        gugyo_labels = ((fwd, "絞(연지 기준)"), (back, "勾(연지 기준)"))
    for off, label_txt in gugyo_labels:
        year_targets.append(("구교살", cat.branch_at(yb + off), label_txt))
    # 원진(元辰): 陽男陰女=충 다음 자리(+7), 陰男陽女=충 앞 자리(+5). 성별 미상이면 판정하지 않는다
    # (2026-11-12 교정 — 종전에는 연간 음양만 써서 여성 명식이 반대로 나왔다).
    if yangnam_eumnyeo is not None:
        yuan_off = (
            cat.WONJIN_YUAN_OFFSET_YANGNAM_EUMNYEO if yangnam_eumnyeo
            else cat.WONJIN_YUAN_OFFSET_EUMNAM_YANGNYEO
        )
        kind = "陽男陰女" if yangnam_eumnyeo else "陰男陽女"
        year_targets.append(("원진(元辰)", cat.branch_at(yb + yuan_off), f"연지 기준 元辰({kind})"))
    for name, tgt, basis_txt in year_targets:
        meta = cat.CATALOG_META[name]
        for pos, p in positions:
            if pos != "year" and Branch(p.branch) == tgt:
                basis = f"년지 {year_branch} 기준 {p.branch} — {basis_txt}"
                out.append((name, meta["category"], pos, basis))
    # 협록(夾祿): 일간 정록(L)을 이웃한 두 지지가 L-1·L+1로 끼고(夾), 정록 글자 자체는 원국에
    # 없을 때 성립(2026-11-12 교정 — 전실(塡實) 금지·인접 조건 추가. 종전에는 두 글자 보유만 봤다).
    rok = cat.CHEONROK[day_stem]
    prev_b = cat.branch_at(BRANCH_INDEX[rok] - 1)
    next_b = cat.branch_at(BRANCH_INDEX[rok] + 1)
    if rok not in chart_branches:
        hyeop_pos: list[str] = []
        for (pa, a), (pb, b) in zip(positions, positions[1:], strict=False):
            if {Branch(a.branch), Branch(b.branch)} == {prev_b, next_b}:
                hyeop_pos.extend(x for x in (pa, pb) if x not in hyeop_pos)
        out.extend(
            ("협록", "wealth_status", pos, f"정록 {rok} 협({prev_b}{next_b})") for pos in hyeop_pos
        )
    out.extend(_added_20261112(pillars, positions))
    out.extend(_positional_twelve_sinsal(positions, year_branch, day_branch))
    return out


def _added_20261112(
    pillars: FourPillarsResult, positions: list[tuple[str, Pillar]],
) -> list[_Detection]:
    """2026-11-12 추가 12종(출처 간 표가 일치한 것만).

    급각살·효신살·유하살·십악대패·절로공망·천덕합·월덕합·월공귀인·육수·진신·홍란·천희.
    """
    out: list[_Detection] = []
    day_stem = Stem(pillars.day.stem)
    day_branch = Branch(pillars.day.branch)
    month_branch = Branch(pillars.month.branch)
    year_branch = Branch(pillars.year.branch)
    day_gz = (day_stem, day_branch)

    def meta_cat(name: str) -> str:
        return str(cat.CATALOG_META[name]["category"])

    # 월지 기준 — 급각살(일지·시지만), 천덕합·월덕합·월공귀인(천간 또는 지지).
    geupgak = cat.GEUPGAK[month_branch]
    for pos, p in positions:
        if pos in ("day", "hour") and Branch(p.branch) in geupgak:
            out.append(("급각살", meta_cat("급각살"), pos, f"월지 {month_branch} 기준 {p.branch}"))
    cdh = cat.CHEONDEOK_HAP[month_branch]
    for name, target in (
        ("천덕합", cdh), ("월덕합", cat.WOLDEOK_HAP[month_branch]),
        ("월공귀인", cat.WOLGONG[month_branch]),
    ):
        for pos, p in positions:
            if isinstance(target, Stem) and Stem(p.stem) == target:
                out.append((name, meta_cat(name), pos, f"월지 {month_branch} 기준 천간 {target}"))
            elif isinstance(target, Branch) and Branch(p.branch) == target:
                out.append((name, meta_cat(name), pos, f"월지 {month_branch} 기준 지지 {target}"))
    # 일간 기준 — 유하살(모든 지지), 절로공망(시지만).
    for pos, p in positions:
        if Branch(p.branch) == cat.YUHA[day_stem]:
            out.append(("유하살", meta_cat("유하살"), pos, f"일간 {day_stem} 기준 {p.branch}"))
        if pos == "hour" and Branch(p.branch) in cat.JEOLLO_GONGMANG[day_stem]:
            out.append((
                "절로공망", meta_cat("절로공망"), pos, f"일간 {day_stem} 기준 시지 {p.branch}",
            ))
    # 일주 자체.
    day_txt = f"{pillars.day.stem}{pillars.day.branch}"
    for name, table in (
        ("효신살", cat.HYOSIN), ("십악대패", cat.SIBAK_DAEPAE),
        ("육수", cat.YUKSU), ("진신", cat.JINSIN),
    ):
        if day_gz in table:
            out.append((name, meta_cat(name), "day", f"{day_txt} {name}(일주)"))
    # 연지 기준 — 홍란·천희(연주 자신 제외).
    hongran = cat.hongran_branch(year_branch)
    cheonhui = cat.branch_at(BRANCH_INDEX[hongran] + cat.CHEONHUI_FROM_HONGRAN_OFFSET)
    for name, target in (("홍란", hongran), ("천희", cheonhui)):
        for pos, p in positions:
            if pos != "year" and Branch(p.branch) == target:
                out.append((name, meta_cat(name), pos, f"년지 {year_branch} 기준 {p.branch}"))
    return out


def _positional_twelve_sinsal(
    positions: list[tuple[str, Pillar]], year_branch: Branch, day_branch: Branch,
) -> list[_Detection]:
    """자리별 12신살 9종 — 기준 자리(일지, SELF_SINSAL_BASE_SLOTS)의 삼합국 기준.

    겁살·재살·천살·지살·월살·망신살·장성살·반안살·육해살.

    2026-11-12 복원(데굴님 승인). 역마살·도화(년살)·화개살은 `_relative_trine_sinsal` 이 같은 표로
    이미 내므로 여기서는 나머지 9종만 낸다. 같은 자리에 두 기준이 같은 이름이면 1건으로 병기한다.
    """
    by_key: dict[tuple[str, str], list[str]] = {}
    for _slot, label, base in self_sinsal_bases(year_branch, day_branch):
        for pos, p in positions:
            name = relative_twelve_sinsal(base, Branch(p.branch))
            if name in TWELVE_SINSAL_POSITIONAL:
                by_key.setdefault((pos, name), []).append(
                    f"{label} {base.value} 기준 {name}({trine_group_label(base)}국)"
                )
    order = {n: i for i, n in enumerate(TWELVE_SINSAL_ORDER)}
    pos_order = {pos: i for i, (pos, _p) in enumerate(positions)}
    return [
        (name, "twelve_sinsal", pos, " · ".join(dict.fromkeys(txt)))
        for (pos, name), txt in sorted(
            by_key.items(), key=lambda kv: (pos_order[kv[0][0]], order[kv[0][1]]),
        )
    ]


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
    """기준 자리 삼합국의 상대 역마·도화(년살)·화개.

    역마·화개는 일지 기준(SELF_SINSAL_BASE_SLOTS), 도화만 연지·일지 기준(DOHWA_BASE_SLOTS —
    2026-11-13 데굴님 결정). 두 기준이 같은 자리에 겹치면 1건으로 병기한다.

    글자살(寅申巳亥·子午卯酉·辰戌丑未 보유)로 판정하지 않는다 — structure_patterns.json
    `yeokma_rule`(2026-07-23 데굴님 정정)과 같은 원칙을 세 신살 모두에 적용한다(2026-10-06 통일).
    """
    out: list[_Detection] = []
    for display, sinsal in _RELATIVE_TRINE_SINSAL:
        by_pos: dict[str, list[str]] = {}
        for _slot, label, base in self_sinsal_bases(year_branch, day_branch, sinsal):
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


#: 상문·조객을 판정하는 운 레벨 — 통설은 세운·월운(대운·일운에는 붙이지 않는다).
_MOURNING_PERIOD_TYPES: frozenset[str] = frozenset({"year", "month"})


def sinsal_for_luck(
    pillars: FourPillarsResult, stem: Stem, branch: Branch, period_type: str | None = None,
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
        period_type: 운 레벨('year'=세운·'month'=월운·'day'=일운, 대운은 None). 상문·조객처럼
            세운·월운에서만 보는 신살의 적용 범위를 가른다.

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
    # 운 지지가 상대 12신살 자리일 때 — 역마·화개는 일지 기준, 도화(년살)는 연지·일지 기준.
    for display, sinsal in _RELATIVE_TRINE_SINSAL:
        if any(
            branch == branch_of_sinsal(base, sinsal)
            for _slot, _label, base in self_sinsal_bases(year_branch, day_branch, sinsal)
        ):
            add(display)

    # 일간 기준 지지 타깃.
    stem_branch_targets: list[tuple[str, list[Branch]]] = [
        ("천을귀인", cat.CHEONEUL.get(day_stem, [])),
        ("태극귀인", cat.TAEGEUK.get(day_stem, [])),
        ("문창귀인", [cat.MUNCHANG[day_stem]]),
        ("학당귀인", [JANGSAENG_BRANCH[day_stem]]),
        ("홍염", [cat.HONGYEOM[day_stem], *cat.HONGYEOM_EXTRA.get(day_stem, [])]),
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

    # 괴강 / 백호 — 운 간지가 해당 간지이고 **원국 일주도 해당 간지일 때만**(2026-11-12 데굴님
    # 결정: 일주 기준, 운에서 들어와 일주 기준으로 겹치는 경우 포함). 일주가 아니면 운에서 와도
    # 판정하지 않는다.
    gz = (stem, branch)
    day_gz = (day_stem, day_branch)
    if gz in cat.GOEGANG and day_gz in cat.GOEGANG:
        add("괴강")
    if gz in cat.BAEKHO and day_gz in cat.BAEKHO:
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
    # 정록 글자가 원국에 이미 있으면(塡實) 성립하지 않는다(2026-11-12 교정).
    rok = cat.CHEONROK[day_stem]
    prev_b = cat.branch_at(BRANCH_INDEX[rok] - 1)
    next_b = cat.branch_at(BRANCH_INDEX[rok] + 1)
    if rok not in natal_branches:
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

    # ── 2026-11-12 추가 ── 기존 이름 뒤에 붙여 같은 극성 안에서 뒤 순서가 되게 한다.
    # 월지 기준 덕합·월공(운 천간 또는 지지), 일간 기준 유하살, 연지 기준 홍란·천희.
    for nm, target in (
        ("천덕합", cat.CHEONDEOK_HAP[month_branch]), ("월덕합", cat.WOLDEOK_HAP[month_branch]),
        ("월공귀인", cat.WOLGONG[month_branch]),
    ):
        if (isinstance(target, Stem) and stem == target) or (
            isinstance(target, Branch) and branch == target
        ):
            add(nm)
    if branch == cat.YUHA[day_stem]:
        add("유하살")
    hongran = cat.hongran_branch(year_branch)
    if branch == hongran:
        add("홍란")
    if branch == cat.branch_at(BRANCH_INDEX[hongran] + cat.CHEONHUI_FROM_HONGRAN_OFFSET):
        add("천희")
    # 상문·조객 — 생년지 기준 앞·뒤 두 자리의 세운·월운(통설은 유년 신살).
    if period_type in _MOURNING_PERIOD_TYPES:
        yb = BRANCH_INDEX[year_branch]
        if branch == cat.branch_at(yb + cat.SANGMUN_OFFSET):
            add("상문")
        if branch == cat.branch_at(yb + cat.JOGAEK_OFFSET):
            add("조객")
    # 자리별 12신살 9종 — 일지 삼합국 기준(역마·도화·화개는 위에서 이미 판정).
    for _slot, _label, base in self_sinsal_bases(year_branch, day_branch):
        nm = relative_twelve_sinsal(base, branch)
        if nm in TWELVE_SINSAL_POSITIONAL:
            add(nm)

    items = [
        LuckSinsal(
            name=nm,
            polarity=cat.CATALOG_META.get(nm, {}).get("polarity", "neutral"),
            hidden=nm in cat.HIDDEN_NAMES,
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
    pillars: FourPillarsResult, structure: StructureAnalysis, gender: str | None = None,
) -> SinsalAnalysis:
    """원국 신살 집계.

    Args:
        pillars: 원국 사주.
        structure: 구조 분석(충·형·해 겹침 강도 판정용).
        gender: 'male'/'female'/그 외(미상) — 원진(元辰)의 陽男陰女 구분. 미상이면 元辰 미판정.
    """
    detections = _detect(pillars, gender)
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
            hidden=name in cat.HIDDEN_NAMES,
        ))

    # by_pillar/by_category 는 이름 목록(중복 제거, 순서 유지). 상세는 full_list 참조.
    # 숨김 항목(HIDDEN_NAMES)은 full_list 에만 남기고(hidden=True, 엔진 전용) 이름 목록·요약에서는
    # 뺀다 — 이 목록들이 화면 외 노출 경로(LLM 궁성 뷰·신살 발췌)의 입력이다.
    visible = [i for i in full if not i.hidden]
    by_pillar: dict[str, list[str]] = {"year": [], "month": [], "day": [], "hour": []}
    by_category: dict[str, list[str]] = {c: [] for c in cat.ALL_CATEGORIES}
    for item in visible:
        if item.name not in by_pillar.setdefault(item.position, []):
            by_pillar[item.position].append(item.name)
        if item.name not in by_category.setdefault(item.category, []):
            by_category[item.category].append(item.name)

    summary = SinsalSummary(
        repeated=sorted({
            n for n, c in name_counts.items() if c > 1 and n not in cat.HIDDEN_NAMES
        }),
        # 자리별 12신살 9종은 모든 자리에 하나씩 붙는 일반 표지라 '주요' 요약에서 뺀다.
        major_positive=sorted({
            i.name for i in visible
            if cat.CATALOG_META.get(i.name, {}).get("polarity") == "positive"
            and i.name not in TWELVE_SINSAL_POSITIONAL
        }),
        major_caution=sorted({
            i.name for i in visible
            if cat.CATALOG_META.get(i.name, {}).get("polarity") == "caution"
            and i.name not in TWELVE_SINSAL_POSITIONAL
        }),
        palace_sensitive=sorted({i.name for i in visible if i.position in ("day", "month")}),
        structure_overlapped=sorted({i.name for i in visible if i.activated_by_relations}),
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
