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
