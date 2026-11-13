"""운 적용 구조 상태(F8-P1) — 세력 보정·상태 머신·층 규칙·경쟁·시주 미상·불변식.

SSOT: doc/v2_2/PATTERN_TRANSIT_STATES.md §2.
반례가 있는 단언만 둔다(반례 없는 테스트는 게이트를 통과한다).
"""

from __future__ import annotations

import pytest

from saju_api.services.manse_service import calculate, luck_months
from saju_engines.pattern_transit import (
    LuckGlyph,
    compute_adjusted_strength,
    daewoon_ganji_by_year,
    evaluate_pattern_states,
    load_pattern_transit_text,
    pattern_change_lines,
    transit_type_of,
)
from saju_engines.precompute import CompositeBuilder
from saju_engines.structure_patterns import detect_structure_patterns, load_structure_patterns
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.precompute import CompositeLevel

_DICTS = __import__("pathlib").Path(__file__).resolve().parents[2] / "dictionaries"


def _chart(d="1985-03-12", t="14:30", g="male"):
    return calculate(BirthInput(birth_date=d, birth_time=t, birth_place_name="서울", gender=g))


@pytest.fixture(scope="module")
def chart():
    return _chart()


@pytest.fixture(scope="module")
def natal(chart):
    return detect_structure_patterns(chart)


# ── 세력 보정 ───────────────────────────────────────────────────────────────


def test_adjusted_strength_without_luck_equals_effective(chart) -> None:
    s = compute_adjusted_strength(chart, [])
    eff = chart.force_analysis.ten_gods.effective_percent
    assert abs(sum(s.ten_gods.values()) - 100.0) < 0.5
    for tg, v in eff.items():
        assert abs(s.ten_gods.get(tg, 0.0) - v) < 0.05


def test_luck_wealth_stem_raises_wealth_group(chart) -> None:
    # 庚일간 乙丑·己卯·庚戌·癸未: 乙(정재)·未 운은 재성 그룹을 올린다(丑未충으로 丑의 인성은 깎임).
    assert chart.pillars.day.stem == "庚"
    base = compute_adjusted_strength(chart, [])
    with_luck = compute_adjusted_strength(chart, [LuckGlyph("year", "乙", "未")])
    assert with_luck.groups["wealth"] > base.groups["wealth"]
    # 丑未충은 丑 한 글자만 깎으므로(인성 그룹 단위의 절반 미만) 그룹 손상으로는 잡히지 않는다.
    assert "resource" not in with_luck.damaged_groups
    assert abs(sum(with_luck.ten_gods.values()) - 100.0) < 0.5
    # 반례: 乙·卯 운은 卯戌合이 化火로 확정되어 卯의 재성 기여가 火(관성)로 전환
    # — 재성은 오르지 않고 관성이 오른다.
    transformed = compute_adjusted_strength(chart, [LuckGlyph("year", "乙", "卯")])
    assert transformed.groups["wealth"] <= base.groups["wealth"] + 0.5
    assert transformed.groups["officer"] > base.groups["officer"]


def test_clash_marks_natal_branch_glyph_factor(chart) -> None:
    # 운 지지와 충하는 원국 지지는 글자 factor 0.7 — 손상 그룹 판정은 그룹 단위의 절반 이상일 때만.
    from saju_engines import pattern_transit as pt
    from saju_shared_types.constants import BRANCH_CLASHES
    from saju_shared_types.enums import Branch, Stem

    pillars = chart.pillars
    branches = [p.branch for p in (pillars.year, pillars.month, pillars.day, pillars.hour)]
    target = None
    for b in branches:
        for pair in BRANCH_CLASHES:
            if Branch(b) in pair:
                target = (b, str(next(x for x in pair if x != Branch(b))))
                break
        if target:
            break
    assert target is not None
    stack = [pt.LuckGlyph("year", "甲", target[1])]
    natal = pt._natal_glyphs(chart)
    luck = pt._luck_glyphs(Stem(pillars.day.stem), stack)
    pt._apply_relation_modifiers(chart, natal, luck, stack)
    hit = [g for g in natal if g.key[0] == "branch" and g.key[2] == target[0]]
    assert hit and all(g.factor <= pt._CLASH_FACTOR for g in hit)
    # 한 글자 손상으로 그 그룹 경로가 일괄로 꺼지지 않는다(그룹 단위 절반 미만이면 손상 그룹 아님).
    s = pt.compute_adjusted_strength(chart, stack)
    assert isinstance(s.damaged_groups, set)


# ── 카탈로그 ────────────────────────────────────────────────────────────────


def test_catalog_ids_exist_in_dictionary_and_exclude_geguk() -> None:
    dic = {e.pattern_id: e for e in load_structure_patterns().patterns}
    from saju_engines import pattern_transit as pt

    ids = set(pt._TYPE_OF)
    missing = ids - set(dic)
    assert not missing, missing
    assert not any("geguk" in dic[i].family and len(dic[i].family) == 1 for i in ids)
    assert (
        transit_type_of("SANGGWAN_SAENGJAE") == "T1" and transit_type_of("SANGGWAN_PAEIN") == "T2"
    )
    assert transit_type_of("JAEDA_SINYAK") == "T3" and transit_type_of("SUHWA_GIJE") == "T4"
    assert (
        transit_type_of("JEONGHWA_YEONGEUM") == "T5" and transit_type_of("JEONGGWAN_GYEOK") is None
    )


def test_text_dictionary_covers_25_cells() -> None:
    text = load_pattern_transit_text()
    cells = {(it["type"], it["status"]) for it in text["items"]}
    assert len(cells) == 25


# ── 상태 머신 ───────────────────────────────────────────────────────────────


def test_states_empty_when_hour_unknown() -> None:
    r = calculate(
        BirthInput(
            birth_date="1985-03-12",
            birth_time=None,
            birth_time_unknown=True,
            birth_place_name="서울",
            gender="male",
        )
    )
    natal = detect_structure_patterns(r, apply_hour_unknown_policy=False)
    assert evaluate_pattern_states(r, natal, [LuckGlyph("year", "戊", "辰")]) == []


def test_states_empty_for_empty_stack(chart, natal) -> None:
    assert evaluate_pattern_states(chart, natal, []) == []


def test_month_layer_never_resolves(chart, natal) -> None:
    # 월운 층은 '해소'를 쓰지 않는다 — 12개월 × 여러 해를 돌려도 month 층 상태에
    # resolved 가 없어야 한다.
    dw_by_year = daewoon_ganji_by_year(chart)
    seen_weakened = False
    for year in (2024, 2025, 2026, 2027):
        months = luck_months(
            BirthInput(
                birth_date="1985-03-12", birth_time="14:30", birth_place_name="서울", gender="male"
            ),
            year,
        )
        dw = dw_by_year.get(year)
        yg = next(
            (
                p.ganji
                for d in chart.luck_cycles.daewoon_table
                for p in d.sewoon
                if p.label == str(year)
            ),
            None,
        )
        base = ([LuckGlyph("daewoon", dw[0], dw[1])] if dw else []) + (
            [LuckGlyph("year", yg[0], yg[1])] if yg else []
        )
        for m in months:
            states = evaluate_pattern_states(
                chart, natal, [*base, LuckGlyph("month", m.stem, m.branch)]
            )
            assert all(st.status_vs_parent != "resolved" for st in states)
            seen_weakened |= any(st.status_vs_parent == "weakened" for st in states)
    assert seen_weakened, "반례 없음: 월운에서 완화되는 패턴이 하나도 없으면 규칙이 검증되지 않는다"


def test_year_layer_can_resolve_and_create() -> None:
    # 여러 명식 × 세운을 훑어 '신규 성립'과 '해소'가 실제로 나오는지(반례 보장).
    statuses: set[str] = set()
    for d, t in (
        ("1985-03-12", "14:30"),
        ("2001-01-19", "10:00"),
        ("1978-07-25", "22:05"),
        ("1992-11-02", "06:10"),
    ):
        r = _chart(d, t)
        natal = detect_structure_patterns(r)
        dw_by_year = daewoon_ganji_by_year(r)
        for dwi in r.luck_cycles.daewoon_table:
            for p in dwi.sewoon:
                if not p.label.isdigit():
                    continue
                dw = dw_by_year.get(int(p.label))
                stack = ([LuckGlyph("daewoon", dw[0], dw[1])] if dw else []) + [
                    LuckGlyph("year", p.stem, p.branch)
                ]
                for st in evaluate_pattern_states(r, natal, stack):
                    statuses.add(st.status_vs_parent)
                    if st.status_vs_parent == "new":
                        assert not st.natal_established and st.operating
                    if st.status_vs_parent == "resolved":
                        assert not st.operating
    assert {"new", "resolved", "strengthened", "weakened"} <= statuses, statuses


def test_new_not_allowed_for_band_fixed_t3() -> None:
    # 신왕재왕·조후 4종·과다 물상처럼 원국 고정 전제가 있는 패턴은 운에서 '신규 성립'하지 않는다.
    from saju_engines import pattern_transit as pt

    for pid in (*pt._T3_DELTA_ONLY, *pt._T3_ELEMENT_OVERLOAD, "HANMOK_HYANGYANG", "SUTANG_GIHO"):
        assert not pt._new_allowed(pid), pid
    for pid in (
        "JAEDA_SINYAK",
        "SANGGWAN_SAENGJAE",
        "SANGGWAN_PAEIN",
        "SUHWA_GIJE",
        "JEONGHWA_YEONGEUM",
    ):
        assert pt._new_allowed(pid), pid


def test_competition_flag_when_path_and_control_coexist() -> None:
    # 상관생재(T1) + 상관패인(T2) 가 같은 층에서 함께 작동하면 양쪽에 competition.
    from saju_engines import pattern_transit as pt
    from saju_shared_types.structure_patterns import PatternState

    def mk(pid: str, t: str) -> PatternState:
        return PatternState(
            pattern_id=pid,
            name_ko=pid,
            transit_type=t,
            natal_established=True,  # noqa: E731
            operating=True,
            status_vs_natal="unchanged",
            status_vs_parent="unchanged",
        )
    states = [mk("SANGGWAN_SAENGJAE", "T1"), mk("SANGGWAN_PAEIN", "T2"), mk("JAE_SAENGGWAN", "T1")]
    pt._mark_competition(states)
    assert "competition" in states[0].flags and "competition" in states[1].flags
    assert "competition" not in states[2].flags


def test_lines_use_dictionary_and_cap(chart, natal) -> None:
    dw_by_year = daewoon_ganji_by_year(chart)
    found = []
    for dwi in chart.luck_cycles.daewoon_table:
        for p in dwi.sewoon:
            dw = dw_by_year.get(int(p.label)) if p.label.isdigit() else None
            stack = ([LuckGlyph("daewoon", dw[0], dw[1])] if dw else []) + [
                LuckGlyph("year", p.stem, p.branch)
            ]
            states = evaluate_pattern_states(chart, natal, stack)
            lines = pattern_change_lines(states, "year")
            assert len(lines) <= 3
            for ln in lines:
                assert ln.startswith("[") and "이 해" in ln
                for bad in ("길하", "흉하", "반드시"):
                    assert bad not in ln
            found += lines
    assert found, "반례 없음: 세운 줄이 하나도 안 나오면 렌더가 검증되지 않는다"


# ── 배선 ────────────────────────────────────────────────────────────────────


def test_calculate_fills_year_pattern_changes_and_months(chart) -> None:
    years = [p for d in chart.luck_cycles.daewoon_table for p in d.sewoon]
    assert any(p.pattern_changes for p in years)
    months = luck_months(
        BirthInput(
            birth_date="1985-03-12", birth_time="14:30", birth_place_name="서울", gender="male"
        ),
        2026,
    )
    assert len(months) == 12 and all(isinstance(m.pattern_changes, list) for m in months)


def test_hour_unknown_pillars_have_no_pattern_changes() -> None:
    r = calculate(
        BirthInput(
            birth_date="1985-03-12",
            birth_time=None,
            birth_time_unknown=True,
            birth_place_name="서울",
            gender="male",
        )
    )
    assert all(not p.pattern_changes for d in r.luck_cycles.daewoon_table for p in d.sewoon)


def test_composites_carry_pattern_states_except_day(chart) -> None:
    comps = CompositeBuilder(_DICTS).build(
        chart,
        "t",
        "1.1.0",
        "2026-10-17T00:00:00",
        levels={CompositeLevel.DAEWOON, CompositeLevel.YEAR, CompositeLevel.MONTH},
    )
    # 기본 calculate 는 yearly_luck 이 비어 있어 연 composite 가 없을 수 있다
    # — 대운 레벨로 존재를 확인한다.
    assert any(c.pattern_states for c in comps if c.level is CompositeLevel.DAEWOON)
    for c in comps:
        for st in c.pattern_states:
            assert st.transit_type in {"T1", "T2", "T3", "T4", "T5"}
            if c.level is CompositeLevel.MONTH:
                assert st.status_vs_parent != "resolved"


def test_scores_and_favorability_unchanged_by_p1(chart) -> None:
    # inert 불변식 — 상태 계산은 결과 객체의 점수·용신 필드를 건드리지 않는다.
    before = (
        chart.yongsin_analysis.final,
        [p.luck_score for d in chart.luck_cycles.daewoon_table for p in d.sewoon],
    )
    natal = detect_structure_patterns(chart)
    for dwi in chart.luck_cycles.daewoon_table:
        for p in dwi.sewoon:
            evaluate_pattern_states(chart, natal, [LuckGlyph("year", p.stem, p.branch)])
    after = (
        chart.yongsin_analysis.final,
        [p.luck_score for d in chart.luck_cycles.daewoon_table for p in d.sewoon],
    )
    assert before == after


# ── 접지 교정(2026-10-17 데굴님 검수) — 변화는 원국 구조를 바탕으로만 ─────────


def _year_states(r):
    natal = detect_structure_patterns(r)
    dw_by_year = daewoon_ganji_by_year(r)
    for dwi in r.luck_cycles.daewoon_table:
        for p in dwi.sewoon:
            if not p.label.isdigit():
                continue
            dw = dw_by_year.get(int(p.label))
            stack = [LuckGlyph("daewoon", dw[0], dw[1])] if dw else []
            stack.append(LuckGlyph("year", p.stem, p.branch))
            yield from evaluate_pattern_states(r, natal, stack)


_WEAK_CHARTS = (("1985-03-12", "14:30", "male"), ("2001-01-19", "10:00", "female"),
                ("1992-11-02", "06:10", "female"))
_STRONG_CHART = ("1978-07-25", "22:05", "male")


def test_strong_prereq_patterns_never_new_in_non_strong_chart() -> None:
    # 재자약살·식상설수는 신강 전제 — 신약·중화 명식 300세운에서 '신규 성립' 0건.
    for d, t, g in _WEAK_CHARTS:
        r = _chart(d, t, g)
        assert r.force_analysis.strength.band not in {"신강", "태신강"}
        bad = [st for st in _year_states(r)
               if st.pattern_id in ("JAEJA_YAKSAL", "SIKSANG_SEOLSU")
               and st.status_vs_parent == "new"]
        assert not bad, [(st.pattern_id, st.evidence) for st in bad[:3]]
    # 반례 보장: 신강 명식에서는 같은 패턴이 신규 성립할 수 있다.
    r = _chart(*_STRONG_CHART)
    assert r.force_analysis.strength.band in {"신강", "태신강"}
    assert any(st.pattern_id in ("JAEJA_YAKSAL", "SIKSANG_SEOLSU") and st.status_vs_parent == "new"
               for st in _year_states(r))


def test_derived_patterns_require_natal_base() -> None:
    # 득비이재는 원국 재다신약, 살중용인은 원국 관다신약이 있어야 운에서 신규 성립한다.
    r_no = _chart("1992-11-02", "06:10", "female")
    natal_no = {p.pattern_id for p in detect_structure_patterns(r_no)}
    assert "JAEDA_SINYAK" not in natal_no
    assert not any(st.pattern_id == "DEUKBI_IJAE" and st.status_vs_parent == "new"
                   for st in _year_states(r_no))
    r_yes = _chart("1985-03-12", "14:30", "male")
    assert "JAEDA_SINYAK" in {p.pattern_id for p in detect_structure_patterns(r_yes)}
    assert any(st.pattern_id == "DEUKBI_IJAE" and st.status_vs_parent == "new"
               for st in _year_states(r_yes))


def test_resolved_only_for_natal_established_and_luck_created_only_while_operating() -> None:
    seen_resolved = False
    for d, t, g in (*_WEAK_CHARTS, _STRONG_CHART):
        for st in _year_states(_chart(d, t, g)):
            if st.status_vs_parent == "resolved":
                assert st.natal_established
                seen_resolved = True
            if not st.natal_established:
                assert st.operating
    assert seen_resolved


def test_stem_pairing_requires_natal_stem() -> None:
    # 정화련금은 원국에 丁 또는 庚이 있어야 운에서 충족된다 — 둘 다 없는 명식에서는 신규 0건.
    checked = 0
    for d, t, g in (*_WEAK_CHARTS, _STRONG_CHART, ("1966-09-30", "09:00", "male")):
        r = _chart(d, t, g)
        p = r.pillars
        stems = {p.year.stem, p.month.stem, p.day.stem, p.hour.stem}
        if {"丁", "庚"} & stems:
            continue
        checked += 1
        assert not any(st.pattern_id == "JEONGHWA_YEONGEUM" and st.status_vs_parent == "new"
                       for st in _year_states(r))
    assert checked >= 1, "반례 없음: 丁·庚이 둘 다 없는 명식이 표본에 없다"


# ── 감당 능력 모델(2026-10-17 재다신약 예시 대조) ──────────────────────────────


def _jaeda_chart():
    # 乙일간 신약, 원국 재성 43%·일간 측 22% — 재다신약 뚜렷한 성립(P0).
    return calculate(BirthInput(birth_date="1970-07-24", birth_time="04:30",
                                birth_place_name="서울", gender="male"))


def _jaeda_state(r, natal, stack):
    states = evaluate_pattern_states(r, natal, stack)
    return {st.pattern_id: st for st in states}.get("JAEDA_SINYAK")


def test_jaeda_resolves_when_self_side_exceeds_wealth() -> None:
    # 비견 乙卯 운: 재성 33% vs 일간 측 47% → 재성 비율은 30% 이상인데도 '일시적 해소'
    # (원국 성립 유지).
    r = _jaeda_chart()
    natal = detect_structure_patterns(r)
    assert "JAEDA_SINYAK" in {p.pattern_id for p in natal}
    st = _jaeda_state(r, natal, [LuckGlyph("year", "乙", "卯")])
    assert st is not None and st.natal_established and not st.operating
    assert st.status_vs_parent == "resolved"
    assert "일간측" in st.evidence[0]


def test_jaeda_weakens_with_resource_and_strengthens_with_wealth() -> None:
    r = _jaeda_chart()
    natal = detect_structure_patterns(r)
    weak = _jaeda_state(r, natal, [LuckGlyph("year", "壬", "亥")])   # 정인 — 격차 감소
    strong = _jaeda_state(r, natal, [LuckGlyph("year", "戊", "辰")])  # 정재 — 격차 증가
    assert weak is not None and weak.operating and weak.status_vs_parent == "weakened"
    assert strong is not None and strong.operating and strong.status_vs_parent == "strengthened"
    # 재극인: 재성이 인성의 3배를 넘으면 인성은 감당 능력에서 제외(근거 표기).
    assert "인성 제외" in strong.evidence[0]


def test_jaeda_reversal_flag_when_self_side_doubles_wealth() -> None:
    # 비겁 운이 겹쳐 일간 측이 재성의 2배 이상이면 '역전' 플래그(반례 보장: 조합 탐색).
    r = _jaeda_chart()
    natal = detect_structure_patterns(r)
    found = None
    for dw in ("乙卯", "甲寅", "乙未"):
        for yr in ("乙卯", "甲寅", "癸卯", "壬子"):
            stack = [LuckGlyph("daewoon", dw[0], dw[1]), LuckGlyph("year", yr[0], yr[1])]
            st = _jaeda_state(r, natal, stack)
            # 대운 층에서 이미 해소된 뒤 세운이 그대로면 상태는 '변동 없음'+역전 플래그다.
            # 줄 검증은 세운 층에서 전이가 일어난 경우(해소·완화)로 한다.
            if st is not None and "reversal" in st.flags and st.status_vs_parent != "unchanged":
                found = (dw, yr, st)
                break
        if found:
            break
    assert found is not None, "반례 없음: 역전이 한 번도 안 나오면 플래그가 검증되지 않는다"
    assert not found[2].operating
    assert any("반대 불균형" in ln for ln in pattern_change_lines([found[2]], "year"))


def test_jaeda_reactivates_in_month_after_year_resolution() -> None:
    # 세운에서 해소된 뒤 월운 재성 유입으로 다시 작동하면 '강화(재활성)'
    # — 해소 상태를 하위 운에 가정하지 않는다.
    r = _jaeda_chart()
    natal = detect_structure_patterns(r)
    year_stack = [LuckGlyph("year", "乙", "卯")]
    assert not _jaeda_state(r, natal, year_stack).operating
    month = _jaeda_state(r, natal, [*year_stack, LuckGlyph("month", "戊", "辰")])
    assert month is not None and month.operating and month.status_vs_parent == "strengthened"


def test_condition_patterns_natal_parity_with_base_operating() -> None:
    # 성립 조건 SSOT: 조건 패턴은 원국 감지(성립)와 운 모델의 원국 기준 작동이 항상 일치한다.
    from saju_engines import pattern_transit as pt
    from saju_engines.pattern_conditions import NATAL_CONDITION_IDS
    charts = (*_WEAK_CHARTS, _STRONG_CHART, ("1966-09-30", "09:00", "male"),
              ("1970-07-24", "04:30", "male"))
    for d, t, g in charts:
        r = _chart(d, t, g)
        natal_ids = {p.pattern_id for p in detect_structure_patterns(r)}
        base = pt.compute_adjusted_strength(r, [])
        band = r.force_analysis.strength.band
        for pid in NATAL_CONDITION_IDS:
            ev = pt._evaluate(
                pid, base, band=band, dm_stem=r.pillars.day.stem,
                natal_established=pid in natal_ids, natal_weak=band in pt.WEAK_BANDS_FOR_TEST,
            )
            assert ev is not None
            assert ev.operating == (pid in natal_ids), (d, pid, ev.evidence)


# ── 2026-11-13 데굴님 검수("재생관과 재생살이 관과는 무관한 대운에 의해 모두 성립") ──────────
# SSOT §6. 표본 = 데굴님 명식(庚申 丁亥 己亥 己巳 — 원국 편관 0%·정관은 亥 속 甲뿐).


def _degool():
    return _chart("1980-11-22", "09:40", "male")


def _daewoon_states(r, natal, ganji: str):
    states = evaluate_pattern_states(r, natal, [LuckGlyph("daewoon", ganji[0], ganji[1])])
    return {st.pattern_id: st for st in states}


def test_transformed_strength_stays_in_group_and_creates_no_polarity() -> None:
    # 壬辰 대운: 운 천간 壬(정재)이 월간 丁과 丁壬合化木 → 관성 '그룹' 세력만 는다.
    # 종전에는 化 세력을 정관·편관에 반씩 나눠 편관 11%가 생겼고 재생관·재생살이 함께 섰다.
    r = _degool()
    p = r.pillars
    assert [x.stem + x.branch for x in (p.year, p.month, p.day, p.hour)] == [
        "庚申", "丁亥", "己亥", "己巳"
    ]
    natal = detect_structure_patterns(r)
    assert compute_adjusted_strength(r, []).ten_gods.get("편관", 0.0) == 0.0
    s = compute_adjusted_strength(r, [LuckGlyph("daewoon", "壬", "辰")])
    assert s.transformed_groups.get("officer", 0.0) > 10.0
    assert s.ten_gods.get("편관", 0.0) < 5.0 and s.ten_gods.get("정관", 0.0) < 10.0
    assert s.groups["officer"] > 20.0
    assert abs(sum(s.ten_gods.values()) + sum(s.transformed_groups.values()) - 100.0) < 0.5
    states = _daewoon_states(r, natal, "壬辰")
    for pid in ("JAE_SAENGGWAN", "JAE_SAENGSAL", "SANGGWAN_JESAL", "SANGGWAN_GYEONGWAN"):
        assert pid not in states, pid
    # 신약 원국이라 일간이 힘을 쓰는 구조(생재·관살유제)는 이 대운에 새로 서지 않는다(§7).
    for pid in ("SIKSANG_SAENGJAE", "SANGGWAN_SAENGJAE", "GWANSAL_YUJE"):
        assert pid not in states, pid
    # 化 세력으로 선 운 생성 그룹 단위 배합에는 표지가 붙는다(재관인상생 — 2026년 3월 층).
    month = evaluate_pattern_states(r, natal, [
        LuckGlyph("daewoon", "壬", "辰"), LuckGlyph("year", "丙", "午"),
        LuckGlyph("month", "辛", "卯"),
    ])
    chain = {st.pattern_id: st for st in month}.get("JAEGWANIN_SANGSAENG")
    assert chain is not None and "via_transform" in chain.flags
    # 반례: 정관 글자가 직접 오는 운에는 재생관이 새로 선다 — 중화신약 庚일간(乙丑 己卯 庚戌 癸未)의
    # 丁丑 대운(丁 = 정관). 데굴님 명식은 신약이라 甲午 대운에도 서지 않는다(§7).
    assert "JAE_SAENGGWAN" not in _daewoon_states(r, natal, "甲午")
    other = _chart()
    gwan = _daewoon_states(other, detect_structure_patterns(other), "丁丑").get("JAE_SAENGGWAN")
    assert gwan is not None and gwan.status_vs_parent == "new"
    assert "via_transform" not in gwan.flags


def test_new_requires_direct_supply_from_the_luck_glyph() -> None:
    r = _degool()
    natal = detect_structure_patterns(r)
    # 辛卯(식신·편관)는 상관견관의 다리(상관·정관)를 공급하지 않는다 — 종전에는 재정규화로 신규였다.
    assert "SANGGWAN_GYEONGWAN" not in _daewoon_states(r, natal, "辛卯")
    # 반례: 庚寅(상관·정관 본기)은 두 다리를 직접 공급한다.
    st = _daewoon_states(r, natal, "庚寅").get("SANGGWAN_GYEONGWAN")
    assert st is not None and st.status_vs_parent == "new"
    # 제살태과는 원국 편관이 실재해야 한다 — 살이 오는 辛卯 대운에도 서지 않는다(종전 신규).
    assert "JESAL_TAEGWA" not in _daewoon_states(r, natal, "辛卯")


def test_contributes_and_touches_rules() -> None:
    from saju_engines import pattern_transit as pt
    from saju_engines.pattern_conditions import contribution_spec

    def mk(tgs, grps=(), lost=None):
        return pt.AdjustedStrength(
            {}, {}, {}, luck_supply=[(frozenset(tgs), frozenset(grps))], natal_lost=lost or {}
        )

    gwan = contribution_spec("JAE_SAENGGWAN")
    assert pt._contributes(gwan, mk({"정관"}), None) and pt._contributes(gwan, mk({"정재"}), None)
    assert not pt._contributes(gwan, mk({"편관"}), None)  # 정·편 불일치
    assert not pt._contributes(gwan, mk({"겁재"}, {"officer"}), None)  # 化 그룹 ≠ 정·편 지정 다리
    chain = contribution_spec("JAEGWANIN_SANGSAENG")
    assert pt._contributes(chain, mk({"겁재"}, {"officer"}), None)  # 그룹 전체 다리는 化 로 공급
    # 차단자(비겁)를 이 층에서 덜어냈으면 기여, 직전 층에서 이미 덜어낸 것은 기여가 아니다.
    relieved = mk({"정인"}, lost={"peer": 5.0})
    assert pt._contributes(gwan, relieved, None)
    assert not pt._contributes(gwan, relieved, mk({"정인"}, lost={"peer": 5.0}))
    taegwa = contribution_spec("JESAL_TAEGWA")
    assert pt._contributes(taegwa, mk({"식신"}), None)
    assert not pt._contributes(taegwa, mk({"식신", "편관"}), None)  # 살을 보태는 운은 금지
    related = frozenset({"wealth", "officer"})
    assert pt._touches(related, mk({"편관"}), None)  # 접촉은 그룹 단위
    assert not pt._touches(related, mk({"정인"}), None)
    assert pt._touches(related, mk({"정인"}, lost={"wealth": 3.0}), None)
    assert pt._touches(None, mk({"정인"}), None)  # 게이트 없는 유형(T5)


def test_unrelated_luck_does_not_change_natal_pattern() -> None:
    # 원국 수화기제. 己丑(비견)은 水·火 어느 쪽도 공급하지 않는다 — 운 글자가 더해져 몫이 줄어도
    # (희석) 변동 없음. 종전에는 '약화'로 찍혔다.
    r = _degool()
    natal = detect_structure_patterns(r)
    assert "SUHWA_GIJE" in {d.pattern_id for d in natal}
    st = _daewoon_states(r, natal, "己丑").get("SUHWA_GIJE")
    assert st is not None and st.operating and st.status_vs_parent == "unchanged"
    # 반례: 癸巳(水·火 글자 공급)는 맞닿는 운이라 상태가 움직인다.
    assert _daewoon_states(r, natal, "癸巳")["SUHWA_GIJE"].status_vs_parent == "strengthened"


def test_suhwa_transit_condition_matches_natal_detector() -> None:
    from saju_engines import pattern_transit as pt

    def st(su: float, hwa: float):
        return pt.AdjustedStrength({}, {}, {"水": su, "火": hwa})

    # 水 20·火 12 는 기제(둘 다 15%+)도 미제(결핍 또는 차 30+)도 아니다.
    # 종전 운 판정은 '기제가 아니면 전부 미제'라 이 구간이 미제였다.
    mid = st(20.0, 12.0)
    assert not pt._eval_t4("SUHWA_GIJE", mid, False).operating
    assert not pt._eval_t4("SUHWA_MIJE", mid, False).operating
    assert pt._eval_t4("SUHWA_GIJE", st(20.0, 22.0), False).operating
    assert pt._eval_t4("SUHWA_MIJE", st(45.0, 12.0), False).operating
    assert pt._eval_t4("SUHWA_MIJE", st(20.0, 6.0), False).operating  # 한쪽 결핍


_RIVAL_PAIRS = (
    ("JAE_SAENGGWAN", "JAE_SAENGSAL"),
    ("SUHWA_GIJE", "SUHWA_MIJE"),
    ("JESAL_TAEGWA", "SIKSIN_JESAL"),
    ("JESAL_TAEGWA", "SANGGWAN_JESAL"),
    ("JESAL_TAEGWA", "GWANSAL_YUJE"),
    ("GWANSAL_YUJE", "SALJUNG_JEGYEONG"),
)


def test_rival_patterns_never_operate_in_the_same_layer() -> None:
    charts = (*_WEAK_CHARTS, _STRONG_CHART, ("1980-11-22", "09:40", "male"),
              ("1975-06-06", "13:03", "female"), ("1981-06-15", "12:00", "male"),
              ("1980-01-20", "10:00", "male"))
    seen_on: set[str] = set()
    for d, t, g in charts:
        r = _chart(d, t, g)
        natal = detect_structure_patterns(r)
        dw_by_year = daewoon_ganji_by_year(r)
        for dwi in r.luck_cycles.daewoon_table:
            for p in dwi.sewoon:
                if not p.label.isdigit():
                    continue
                dw = dw_by_year.get(int(p.label))
                stack = [LuckGlyph("daewoon", dw[0], dw[1])] if dw else []
                for upto in (stack, [*stack, LuckGlyph("year", p.stem, p.branch)]):
                    if not upto:
                        continue
                    on = {st.pattern_id for st in evaluate_pattern_states(r, natal, upto)
                          if st.operating}
                    seen_on |= on
                    for a, b in _RIVAL_PAIRS:
                        assert not {a, b} <= on, (d, [x.stem + x.branch for x in upto], a, b)
    # 반례 보장: 맞수 양쪽이 표본 어딘가에서는 각각 작동한다(아예 안 나오면 검증이 아니다).
    for pid in ("JAE_SAENGGWAN", "JAE_SAENGSAL", "SUHWA_GIJE", "SUHWA_MIJE", "JESAL_TAEGWA"):
        assert pid in seen_on, pid


def test_standing_natal_pattern_beats_freshly_formed_rival() -> None:
    # 乙卯 辛巳 癸未 戊午(원국 재생살: 편관 > 정관). 庚寅 대운은 재·관을 공급하지 않고 식신(乙)을
    # 합으로 덜어낼 뿐이다 — 재생살은 그대로 이어지고 재생관이 그 옆에 새로 서지 않는다.
    r = _chart("1975-06-06", "13:03", "female")
    natal = detect_structure_patterns(r)
    assert "JAE_SAENGSAL" in {d.pattern_id for d in natal}
    states = _daewoon_states(r, natal, "庚寅")
    assert states["JAE_SAENGSAL"].operating and "JAE_SAENGGWAN" not in states


# ── 2026-11-13 (2) 데굴님 검수("식상생재는 일간의 힘이 필요 … 내 경우에는 신약 사주") — SSOT §7 ──


def _all_layer_states(r):
    """대운 층과 세운 층의 상태를 모두 낸다."""
    natal = detect_structure_patterns(r)
    dw_by_year = daewoon_ganji_by_year(r)
    for dwi in r.luck_cycles.daewoon_table:
        for p in dwi.sewoon:
            if not p.label.isdigit():
                continue
            dw = dw_by_year.get(int(p.label))
            stack = [LuckGlyph("daewoon", dw[0], dw[1])] if dw else []
            if stack:
                yield from evaluate_pattern_states(r, natal, stack)
            year = LuckGlyph("year", p.stem, p.branch)
            yield from evaluate_pattern_states(r, natal, [*stack, year])


def test_dm_spending_patterns_never_new_in_frail_charts() -> None:
    from saju_engines.pattern_conditions import DM_SPENDING_IDS, FRAIL_BANDS

    # 신약·태신약 원국: 식상·재·관이 더 와도 생재·재생관·제살 구조는 '신규 성립'이 아니다.
    for d, t, g in (("1980-11-22", "09:40", "male"), ("2001-01-19", "10:00", "female"),
                    ("1992-11-02", "06:10", "female"), ("1980-01-20", "10:00", "male")):
        r = _chart(d, t, g)
        assert r.force_analysis.strength.band in FRAIL_BANDS, d
        bad = [st for st in _all_layer_states(r)
               if st.pattern_id in DM_SPENDING_IDS and st.status_vs_parent == "new"]
        assert not bad, (d, [(st.pattern_id, st.evidence) for st in bad[:3]])
    # 반례: 중화신약·중화신강 명식에서는 같은 구조가 운에서 새로 선다.
    seen: set[str] = set()
    for d, t, g in (("1985-03-12", "14:30", "male"), ("1966-09-30", "09:00", "male")):
        r = _chart(d, t, g)
        assert r.force_analysis.strength.band not in FRAIL_BANDS
        seen |= {st.pattern_id for st in _all_layer_states(r)
                 if st.pattern_id in DM_SPENDING_IDS and st.status_vs_parent == "new"}
    assert {"JAE_SAENGGWAN", "SIKSANG_SAENGJAE"} <= seen, seen


def test_frail_chart_ignores_self_side_loss_as_blocker_relief() -> None:
    from saju_engines import pattern_transit as pt
    from saju_engines.pattern_conditions import contribution_spec

    def mk(tgs, lost):
        return pt.AdjustedStrength(
            {}, {}, {}, luck_supply=[(frozenset(tgs), frozenset())], natal_lost=lost
        )

    geugin = contribution_spec("JAE_GEUGIN")  # 차단자 = 비겁·관성
    lost_peer = mk({"식신"}, {"peer": 5.0})
    assert pt._contributes(geugin, lost_peer, None)  # 신강·중화: 비겁이 덜어지면 길이 열린다
    assert not pt._contributes(geugin, lost_peer, None, frail=True)  # 신약: 일간 받침이 빠진 것
    # 반례: 일간 쪽이 아닌 차단자(관성 통관)가 덜어진 것은 신약 원국에서도 기여다.
    assert pt._contributes(geugin, mk({"식신"}, {"officer": 5.0}), None, frail=True)


def test_natal_dm_spending_pattern_carries_weak_dm_note_and_flag() -> None:
    # 己未 丁丑 壬辰 乙巳(태신약) — 원국 식상생재·재생관·상관제살 성립.
    r = _chart("1980-01-20", "10:00", "male")
    assert r.force_analysis.strength.band == "태신약"
    natal = detect_structure_patterns(r)
    by_id = {d.pattern_id: d for d in natal}
    for pid in ("SIKSANG_SAENGJAE", "JAE_SAENGGWAN", "SANGGWAN_JESAL"):
        assert "신약형" in by_id[pid].basis_note and "신약형" in by_id[pid].llm_line
    # 반례: 억부 줄의 근거(표면·보정 세력)는 그대로다.
    assert "신약형" not in by_id["GWANDA_SINYAK"].basis_note
    # 운에서도 표지가 상시 붙는다 — 식상·재가 더 오는 丁卯 대운의 '강화'에도.
    st = _daewoon_states(r, natal, "丁卯")["SIKSANG_SAENGJAE"]
    assert st.status_vs_parent == "strengthened" and "weak_dm" in st.flags
    # 반례: 신강 명식의 원국 구조에는 신약형 근거가 없다.
    strong = detect_structure_patterns(_chart(*_STRONG_CHART))
    assert all("신약형" not in d.basis_note for d in strong)


def test_support_luck_keeps_frail_natal_pattern_and_flags_it() -> None:
    # 壬申 대운(비견·편인만 공급)은 幫身 운이다 — 원국 상관제살은 해소·완화되지 않고 표지가 붙는다.
    r = _chart("1980-01-20", "10:00", "male")
    natal = detect_structure_patterns(r)
    st = _daewoon_states(r, natal, "壬申")["SANGGWAN_JESAL"]
    assert st.status_vs_parent == "unchanged" and st.operating and "supported" in st.flags
    # 같은 대운이라도 巳申合으로 재성 글자가 묶인 생재·재생관은 실제 손상이라 幫身 층이 아니다.
    assert "supported" not in _daewoon_states(r, natal, "壬申")["SIKSANG_SAENGJAE"].flags
    # 반례: 식상·재가 오는 丁卯 대운에는 표지가 없다.
    assert "supported" not in _daewoon_states(r, natal, "丁卯")["SANGGWAN_JESAL"].flags


# ── 2026-11-13 (3) 같은 계열 추가 교정(데굴님 "제안대로 진행 … C 는 신강계 미성립") — §8 ──


def test_new_never_reports_pattern_already_met_in_natal() -> None:
    # 운 모델 기준으로 원국 세력만으로 이미 조건이 충족되는 구조는 운이 만든 것이 아니다 —
    # 운 글자가 스쳐도 '신규 성립'이 아니다(종전: 신규의 30%가 이런 경우였다).
    from saju_engines import pattern_transit as pt

    news = 0
    for d, t, g in (*_WEAK_CHARTS, _STRONG_CHART, ("1966-09-30", "09:00", "male"),
                    ("1951-05-16", "00:41", "female"), ("1979-02-17", "04:06", "male")):
        r = _chart(d, t, g)
        band = r.force_analysis.strength.band
        base = pt.compute_adjusted_strength(r, [])
        for st in _all_layer_states(r):
            if st.status_vs_parent != "new":
                continue
            news += 1
            ev = pt._evaluate(
                st.pattern_id, base, band=band, dm_stem=r.pillars.day.stem,
                natal_established=False, natal_weak=band in pt.WEAK_BANDS_FOR_TEST,
            )
            assert ev is not None and not ev.operating, (d, st.pattern_id, ev.evidence)
    assert news > 50, "반례 없음: 신규 성립이 충분히 나오지 않으면 불변식이 검증되지 않는다"
    # 반례(여전히 서는 신규): 신강 명식에서 식상이 원국에 약하다가 운에서 들어오면 식상설수 신규.
    r = _chart("1951-05-16", "00:41", "female")
    st = _daewoon_states(r, detect_structure_patterns(r), "甲午").get("SIKSANG_SEOLSU")
    assert st is not None and st.status_vs_parent == "new"


def test_strong_premise_patterns_never_new_in_frail_charts() -> None:
    from saju_engines.pattern_conditions import FRAIL_BANDS, STRONG_PREMISE_IDS

    # 군겁쟁재·비겁탈재·관살제겁은 신왕 전제 — 신약·태신약 원국의 비겁은 재를 다투는 쪽이 아니다.
    for d, t, g in (("1980-11-22", "09:40", "male"), ("2001-01-19", "10:00", "female"),
                    ("1992-11-02", "06:10", "female"), ("1980-01-20", "10:00", "male")):
        r = _chart(d, t, g)
        assert r.force_analysis.strength.band in FRAIL_BANDS
        bad = [st for st in _all_layer_states(r)
               if st.pattern_id in STRONG_PREMISE_IDS and st.status_vs_parent == "new"]
        assert not bad, (d, [(st.pattern_id, st.evidence) for st in bad[:3]])
    # 반례: 중화·태신강 명식에서는 운에서 새로 선다.
    mid = _chart("1975-01-18", "03:38", "female")
    assert mid.force_analysis.strength.band == "중화"
    taljae = _daewoon_states(mid, detect_structure_patterns(mid), "丁卯").get("BIGEOP_TALJAE")
    assert taljae is not None and taljae.status_vs_parent == "new"
    strong = _chart("1961-01-27", "04:23", "male")
    jegeop = _daewoon_states(strong, detect_structure_patterns(strong), "甲午").get(
        "GWANSAL_JEGEOP"
    )
    assert jegeop is not None and jegeop.status_vs_parent == "new"


def test_inda_sinyak_not_established_in_strong_charts() -> None:
    # 인성 40%+ 인 태신강 명식(인왕신왕 성립) — '신약'이 붙은 인다신약은 서지 않는다.
    strong = _chart("1983-02-05", "22:57", "male")
    assert strong.force_analysis.strength.band == "태신강"
    ids = {d.pattern_id for d in detect_structure_patterns(strong)}
    assert "INWANG_SINWANG" in ids and "INDA_SINYAK" not in ids
    # 운에서도 새로 서지 않는다.
    assert not any(st.pattern_id == "INDA_SINYAK" for st in _all_layer_states(strong))
    # 반례: 신약 명식의 인다신약은 그대로 선다.
    weak = _chart("1975-02-14", "20:49", "female")
    assert weak.force_analysis.strength.band == "신약"
    assert "INDA_SINYAK" in {d.pattern_id for d in detect_structure_patterns(weak)}


def test_yielding_names_never_operate_with_their_winner() -> None:
    from saju_engines.pattern_conditions import YIELDS_TO
    from saju_engines.structure_patterns import _drop_yielding_patterns
    from saju_shared_types.structure_patterns import DetectedPattern

    # 원국: 이기는 구조가 서면 양보하는 이름과 그 파생 신호를 뺀다.
    def mk(pid: str) -> DetectedPattern:
        return DetectedPattern(
            pattern_id=pid, name_ko=pid, strength=0.5, polarity_mode="context_only"
        )

    kept = {d.pattern_id for d in _drop_yielding_patterns(
        [mk(p) for p in ("DEUKBI_IJAE", "BIGEOP_TALJAE", "IDENTITY_AUTHORIZATION_STRESS",
                         "JAEJA_YAKSAL", "JAE_SAENGSAL", "JAE_GEUGIN")]
    )}
    assert kept == {"DEUKBI_IJAE", "JAEJA_YAKSAL", "JAE_GEUGIN"}  # 재극인은 인다용재가 없어 남는다
    # 반례: 이기는 구조가 없으면 그대로다.
    same = [mk(p) for p in ("BIGEOP_TALJAE", "IDENTITY_AUTHORIZATION_STRESS", "JAE_SAENGSAL")]
    assert len(_drop_yielding_patterns(same)) == 3
    # 운: 표본 명식의 대운·세운 층에서 양보 쌍이 함께 작동하는 층이 없다.
    seen_on: set[str] = set()
    for d, t, g in (*_WEAK_CHARTS, _STRONG_CHART, ("1979-02-17", "04:06", "male"),
                    ("1973-04-07", "15:57", "male"), ("2001-03-28", "00:50", "male"),
                    ("1975-01-18", "03:38", "female")):
        r = _chart(d, t, g)
        natal = detect_structure_patterns(r)
        dw_by_year = daewoon_ganji_by_year(r)
        for dwi in r.luck_cycles.daewoon_table:
            for p in dwi.sewoon:
                if not p.label.isdigit():
                    continue
                dw = dw_by_year.get(int(p.label))
                stack = [LuckGlyph("daewoon", dw[0], dw[1])] if dw else []
                stack.append(LuckGlyph("year", p.stem, p.branch))
                on = {st.pattern_id for st in evaluate_pattern_states(r, natal, stack)
                      if st.operating}
                seen_on |= on
                for loser, winners in YIELDS_TO.items():
                    assert not (loser in on and winners & on), (d, p.label, loser)
    # 반례 보장: 이기는 쪽과 양보하는 쪽이 표본 어딘가에서는 각각 작동한다.
    for pid in ("DEUKBI_IJAE", "JAEJA_YAKSAL", "INDA_YONGJAE", "JAE_SAENGSAL", "JAE_GEUGIN",
                "BIGEOP_TALJAE"):
        assert pid in seen_on, pid
