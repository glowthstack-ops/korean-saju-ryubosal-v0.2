"""운 층 구조의 '빠진 다리' 게이트 · 진합화 · 다리별 근거 글자 (2026-11-21 데굴님 실답).

실답: 己 일간 명식(庚申 丁亥 己亥 己巳)에서 관성(木) 글자가 하나도 없는 달(丙申·庚子·辛丑월 — 인성·
식상·재성 운)에 '재관인상생 신규 성립'이 떴다. 관성 세력은 대운 壬과 월간 丁의 합화(木)뿐이었고,
그 달 글자는 이미 있는 다리만 보탰다 — 풀이가 식상 글자를 관성처럼 읽게 되는 구조다.

고친 것: ①원국에 빠진 다리는 글자(또는 인정되는 化)로 채워져야 운에서 선다 ②천간 합화는 진합화
(운+원국 · 化 오행 득령 · 방해 세력 없음)만 구조 기여로 인정 ③신규 성립 줄에 다리별 근거 글자.
"""

from __future__ import annotations

import datetime as dt

import pytest

from saju_api.services.manse_service import _calculate, pattern_timeline
from saju_engines import pattern_transit as pt
from saju_engines.relation_semantics import collect_luck_relation_semantics
from saju_engines.structure_patterns import _hidden_only_leg_notes, detect_structure_patterns
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.enums import Element
from saju_shared_types.relation_semantics import TransformationState

# 데굴님 명식(庚申 丁亥 己亥 己巳, 己 일간) — 재성 水·관성 木·인성 火·식상 金.
_DEGOOL = BirthInput(
    birth_date=dt.date(1980, 11, 22), birth_time=dt.time(9, 40), birth_place_name="서울 구로구",
    gender="male", latitude=37.4944, longitude=126.8563, timezone="Asia/Seoul",
    reference_date=dt.date(2026, 11, 21),
)
# 壬子 辛亥 庚午 丁丑(庚 일간) — 대운 丙이 월간 辛과 합화 水(亥월 득령, 극하는 土가 드러나지 않음).
_TRUE_HWA = BirthInput(
    birth_date=dt.date(1972, 12, 5), birth_time=dt.time(3, 30), birth_place_name="서울 구로구",
    gender="female", latitude=37.4944, longitude=126.8563, timezone="Asia/Seoul",
    reference_date=dt.date(2026, 11, 21),
)
_DW = pt.LuckGlyph("daewoon", "壬", "辰")
_YR = pt.LuckGlyph("year", "丙", "午")


@pytest.fixture(scope="module")
def degool():
    return _calculate(_DEGOOL)


def _states(result, stack) -> dict[str, object]:
    natal = detect_structure_patterns(result)
    return {s.pattern_id: s for s in pt.evaluate_pattern_states(result, natal, stack)}


def _stem_sem(result, stack):
    sems = collect_luck_relation_semantics(
        result, [g.stem for g in stack], [g.branch for g in stack]
    )
    return next(
        s for s in sems
        if s.kind == "stem_combination"
        and s.transformation_state is TransformationState.TRANSFORMED
    )


# ── 실답 재현 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("stem", "branch"),
    [("丙", "申"), ("庚", "子"), ("辛", "丑")],  # 2026-08 · 2026-12 · 2027-01 — 관성 글자 없는 달
)
def test_no_new_jaegwanin_in_months_without_an_officer_glyph(degool, stem, branch) -> None:
    states = _states(degool, [_DW, _YR, pt.LuckGlyph("month", stem, branch)])
    assert "JAEGWANIN_SANGSAENG" not in states


def test_month_that_brings_the_officer_glyph_still_establishes_it(degool) -> None:
    """반례 — 辛卯월은 卯(편관)가 빠진 다리를 직접 채운다."""
    st = _states(degool, [_DW, _YR, pt.LuckGlyph("month", "辛", "卯")])["JAEGWANIN_SANGSAENG"]
    assert st.status_vs_parent == "new" and st.operating
    assert any(n.startswith("관성 ") and "卯(월운)" in n for n in st.leg_notes)
    assert any(n.startswith("재성 ") and "(원국)" in n for n in st.leg_notes)
    assert not any("글자 없음" in n for n in st.leg_notes)


def test_timeline_marks_only_the_month_with_the_glyph() -> None:
    row = next(
        r for r in pattern_timeline(_DEGOOL, 2026).rows
        if r.pattern_id == "JAEGWANIN_SANGSAENG"
    )
    assert row.summary == "원국 미성립 → 3월 신규 성립"
    cell = next(c for c in row.months if c is not None and c.status == "new")
    assert "관성 卯(월운)" in cell.legs


def test_window_lines_and_change_lines_carry_leg_glyphs(degool) -> None:
    lines = pt.window_structure_lines([pattern_timeline(_DEGOOL, 2026)], ["2026-03", "2026-12"])
    march = next(ln for ln in lines if ln.startswith("월운 2026-03"))
    december = next(ln for ln in lines if ln.startswith("월운 2026-12"))
    assert "재관인상생 신규 성립(재성 " in march and "관성 卯(월운)" in march
    assert "재관인상생" not in december
    natal = detect_structure_patterns(degool)
    states = pt.evaluate_pattern_states(
        degool, natal, [_DW, _YR, pt.LuckGlyph("month", "辛", "卯")]
    )
    changed = pt.pattern_change_lines(states, "month", max_count=10)
    assert any("재관인상생" in ln and "(근거 글자: " in ln for ln in changed)


# ── 진합화 판정 ───────────────────────────────────────────────────────────────


def test_obstructed_stem_transform_is_not_a_true_transform(degool) -> None:
    """丁壬 化木 — 木을 극하는 庚이 연간에 드러나 申에 통근하고 丁 바로 옆에 있다."""
    sem = _stem_sem(degool, [_DW])
    assert sem.transform_element == "木"
    assert pt._hwa_obstructed(Element.WOOD, "month", "壬", degool, [_DW])
    assert not pt._true_stem_transform(sem, degool, [_DW])
    s = pt.compute_adjusted_strength(degool, [_DW])
    # 세력에는 그대로 반영되지만(化 세력의 그룹 편입은 불변) 구조 기여로는 세지 않는다.
    assert s.transformed_groups.get("officer", 0.0) > 0
    assert "officer" not in s.hwa_labels and s.luck_supply[0][1] == frozenset()


def test_unobstructed_stem_transform_counts_as_supply() -> None:
    """반례 — 丙辛 化水: 亥월 득령, 水를 극하는 土가 천간에 없고 월지 충도 없다."""
    result = _calculate(_TRUE_HWA)
    stack = [pt.LuckGlyph("daewoon", "丙", "午")]
    sem = _stem_sem(result, stack)
    assert sem.transform_element == "水" and pt._true_stem_transform(sem, result, stack)
    s = pt.compute_adjusted_strength(result, stack)
    grp = next(g for g, el in s.element_of_group.items() if el == "水")
    assert s.hwa_labels[grp] == ["丙辛合 化水"]
    assert grp in s.luck_supply[0][1]


def test_month_branch_clash_obstructs_the_same_transform() -> None:
    """같은 합화도 운 지지가 월지(亥)를 충하면(巳) 화신이 안착하지 못한다(조건 ③-3)."""
    result = _calculate(_TRUE_HWA)
    stack = [pt.LuckGlyph("daewoon", "丙", "巳")]
    assert pt._hwa_obstructed(Element.WATER, "month", "丙", result, stack)


def test_luck_only_stem_pair_is_never_a_true_transform(degool) -> None:
    """운 글자끼리의 합화(세운 丙 + 월운 辛)는 원국 글자가 변한 것이 아니다."""
    stack = [_DW, _YR, pt.LuckGlyph("month", "辛", "丑")]
    sems = collect_luck_relation_semantics(
        degool, [g.stem for g in stack], [g.branch for g in stack]
    )
    pair = next(
        s for s in sems
        if s.kind == "stem_combination" and all(o.position == "luck" for o in s.occurrences)
    )
    assert pair.transformation_state is TransformationState.TRANSFORMED
    assert not pt._true_stem_transform(pair, degool, stack)


# ── 다리 게이트 단위 ─────────────────────────────────────────────────────────


def test_legs_grounded_needs_a_glyph_or_true_transform_for_the_missing_leg(degool) -> None:
    s0 = pt.compute_adjusted_strength(degool, [])
    assert s0.group(["정관", "편관"]) < 10.0  # 원국에 빠진 다리 = 관성
    without = pt.compute_adjusted_strength(degool, [_DW, _YR, pt.LuckGlyph("month", "庚", "子")])
    with_glyph = pt.compute_adjusted_strength(
        degool, [_DW, _YR, pt.LuckGlyph("month", "辛", "卯")]
    )
    assert not pt._legs_grounded("JAEGWANIN_SANGSAENG", s0, without)
    assert pt._legs_grounded("JAEGWANIN_SANGSAENG", s0, with_glyph)
    # 억부·수화 유형은 글자 조건이 아니다(게이트 미적용)
    assert pt._legs_grounded("JAEDA_SINYAK", s0, without)


def test_natal_structure_notes_hidden_only_legs() -> None:
    note = _hidden_only_leg_notes("JAE_SAENGGWAN", frozenset({"정재", "편인", "상관"}))
    assert note == ["정관은(는) 지장간에만 있음(천간·지지 본기에 드러난 글자 없음)"]
    assert _hidden_only_leg_notes("JAE_SAENGGWAN", frozenset({"정재", "정관"})) == []
    assert _hidden_only_leg_notes("JAEDA_SINYAK", frozenset()) == []  # 조건 미정의 유형
    assert _hidden_only_leg_notes("JAE_SAENGGWAN", None) == []  # 원국 없음
