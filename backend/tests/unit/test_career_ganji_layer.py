"""간지론 번역층 — 직업 유형 축·궁위 우선·관성 위치·업종·사업 시기 (2026-10-16 데굴님 승인) 회귀.

외부 강의 「제2강 사주상담(직업선택)」(간지론 기반)을 `career_fields.json` 의 선택 절 7종으로
번역했다. 서술 전용(점수·판정 불변)이며 렌더는 '[간지론 관점]' 머리말 + "간지론에서는 ~로 본다"
어투를 강제한다.
픽스처는 2026-10-16 탐색(기준일 2026-10-16 대운 포함).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.career_field import (
    _palace_ten_gods,
    build_career_field_facts,
    load_career_fields,
    render_career_field_lines,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.career_fields import CareerFieldDict

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_TODAY = date(2026, 10, 16)


def _birth(d: str, t: str = "10:00:00", g: str = "male") -> BirthInput:
    return BirthInput(
        birth_date=date.fromisoformat(d), birth_time=t, birth_place_name="서울", gender=g,
    )


_WORKPLACE_ROOTED = _birth("1976-01-05")            # 직장형 · 관성 천간 통근 · 관인 인접
_WORKPLACE_BRANCH = _birth("1976-01-19")            # 직장형 · 관성 지지만
_MIXED = _birth("1976-03-22")                       # 혼합형
_BUSINESS_RES_DW = _birth("1976-01-26")             # 상업형 · 현재 대운 인성이 식상을 누름
_BUSINESS_CASE = _birth("1980-11-22", "09:40:00")   # 상업형(데굴님 명식) · 월지 亥 충 간섭


def _facts(birth: BirthInput, today: date | None = _TODAY):
    return build_career_field_facts(calculate(birth), today=today)


# ── 사전 ────────────────────────────────────────────────────────────────────


def test_dictionary_has_ganji_school_sections():
    d = load_career_fields(_DICTS)
    assert d.ganji_school is not None and d.ganji_school.label == "간지론"
    assert d.ganji_school.narration == "간지론에서는"
    assert d.orientation is not None
    assert set(d.orientation.labels) == {"workplace", "business", "mixed"}
    assert d.orientation.workplace_groups == ["authority", "resource"]
    assert d.orientation.business_groups == ["output", "wealth"]
    assert d.orientation.weights["month_branch"] > d.orientation.weights["month_stem"] > (
        d.orientation.weights["year_stem"]
    )
    assert d.palace_priority is not None and d.palace_priority.order[0] == "월지"
    assert d.officer_position is not None and {
        "stem_rooted", "stem_unrooted", "branch_only", "jeonggwan", "pyeongwan",
        "resource_adjacent", "resource_absent", "daewoon_resource", "authority_many",
    } <= set(d.officer_position.items)
    assert d.business_types is not None and {
        "식신_천간", "식신_지지", "상관", "정재", "편재", "정인", "편인", "겁재_양인",
    } == set(d.business_types.items)
    assert d.business_rules is not None and len(d.business_rules.items) == 8
    assert d.business_timing is not None and d.workplace_notes is not None


def test_dictionary_excludes_policy_words():
    """노출 어휘 정책 — 유흥주점·사채·전당포·기획부동산은 싣지 않는다(지역 단정 어휘도)."""
    d = load_career_fields(_DICTS)
    assert d.business_types is not None and d.business_rules is not None
    assert d.officer_position is not None and d.orientation is not None
    exposed = [
        *(t for it in d.business_types.items.values() for t in it.types),
        *(it.meaning for it in d.business_types.items.values()),
        *(r.text for r in d.business_rules.items),
        *d.officer_position.items.values(),
        *d.orientation.readings.values(),
    ]
    for bad in ("유흥주점", "사채", "전당포", "기획부동산", "서울", "지방공무원"):
        assert not any(bad in x for x in exposed), bad


def test_optional_sections_absent_keeps_layer_off():
    d = load_career_fields(_DICTS)
    raw = d.model_dump(by_alias=True)
    for key in ("ganji_school", "orientation", "palace_priority", "officer_position",
                "workplace_notes", "business_types", "business_rules", "business_timing"):
        raw.pop(key, None)
    slim = CareerFieldDict.model_validate(raw)
    assert slim.ganji_school is None and slim.orientation is None


# ── 직업 유형 축 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("birth", "key", "label"),
    [
        (_WORKPLACE_ROOTED, "workplace", "직장형"),
        (_WORKPLACE_BRANCH, "workplace", "직장형"),
        (_MIXED, "mixed", "혼합형"),
        (_BUSINESS_RES_DW, "business", "상업형"),
        (_BUSINESS_CASE, "business", "상업형"),
    ],
)
def test_orientation_label(birth, key, label):
    o = _facts(birth).orientation
    assert o is not None and o.key == key and o.label == label
    assert o.basis and o.reading
    if key == "workplace":
        assert o.workplace_axis - o.business_axis >= 1.5
    elif key == "business":
        assert o.business_axis - o.workplace_axis >= 1.5
    else:
        assert abs(o.workplace_axis - o.business_axis) < 1.5


def test_orientation_month_branch_weighs_most_and_clash_penalises():
    """데굴님 명식: 월지 정재(+2)·월지 亥 충 간섭(−1)이 근거에 적힌다."""
    o = _facts(_BUSINESS_CASE).orientation
    assert o is not None
    assert any(b.startswith("월지 정재(식·재 +2") for b in o.basis)
    assert any("월지 亥 충 간섭" in b for b in o.basis)


def test_orientation_daewoon_axis_needs_today():
    with_today = _facts(_BUSINESS_CASE).orientation
    without = _facts(_BUSINESS_CASE, today=None).orientation
    assert with_today is not None and "대운" in with_today.daewoon_axis
    assert without is not None and without.daewoon_axis == ""
    assert with_today.key == without.key  # 대운은 축 판정을 바꾸지 않는다(설명만)


# ── 궁위·관성 위치 ──────────────────────────────────────────────────────────


def test_palace_ten_gods_excludes_day_master_slot():
    pal = _palace_ten_gods(calculate(_BUSINESS_CASE))
    assert "일간" not in pal and pal["월지"] == "정재" and pal["일지"] == "정재"


def test_palace_lines_follow_priority_and_timing():
    f = _facts(_WORKPLACE_ROOTED)
    assert f.palace_lines and f.palace_lines[0].startswith("궁위 우선(월지→월간→년주→일지): 월지 ")
    assert any(line.startswith("사용 시기(근묘화실): 관·인 자리") for line in f.palace_lines)


def test_officer_lines_rooted_stem_and_adjacent_resource():
    ol = " ".join(_facts(_WORKPLACE_ROOTED).officer_lines)
    assert "투출하고 지지에 뿌리" in ol and "관인상생" in ol
    assert "지지에만 있고" not in ol


def test_officer_lines_branch_only():
    ol = " ".join(_facts(_WORKPLACE_BRANCH).officer_lines)
    assert "지지에만 있고" in ol and "투출" not in ol


def test_officer_lines_absent_without_authority():
    """관성이 없는 명식은 관성 위치 줄이 비어 있다(1978-09-02 丁: 관성 0)."""
    f = _facts(_birth("1978-09-02"))
    assert f.officer_lines == []


# ── 업종·사업 시기(상업형·혼합형 전용) ────────────────────────────────────────


def test_business_lines_only_for_non_workplace():
    assert _facts(_WORKPLACE_ROOTED).business_lines == []
    assert _facts(_WORKPLACE_ROOTED).timing_lines == []
    f = _facts(_BUSINESS_CASE)
    assert f.business_lines and f.timing_lines
    assert sum(1 for x in f.business_lines if x.startswith("업종 결")) <= 3  # 토큰 상한
    assert any("재성 오행 水" in x for x in f.business_lines)  # 己 일간 재성=水
    # 식상·재성 인접(월지 정재·년간 상관)
    assert any("곁에 붙어 있다" in x for x in f.business_lines)


def test_business_timing_resource_daewoon_controls_output():
    tl = " ".join(_facts(_BUSINESS_RES_DW).timing_lines)
    assert "누르는 시기" in tl and "대운은 큰 환경" in tl


def test_business_timing_supportive_daewoon():
    tl = " ".join(_facts(_BUSINESS_CASE).timing_lines)
    assert "사업 환경이 열리는" in tl


def test_jeonggwan_rule_requires_jeonggwan_present():
    """1979-02-25 癸(편관만, 관성 28%): '정관이 강한데 재성 간섭' 규칙이 붙지 않는다."""
    bl = " ".join(_facts(_birth("1979-02-25")).business_lines)
    assert "정관이 강한데" not in bl


# ── 렌더 ────────────────────────────────────────────────────────────────────


def test_render_block_header_and_narration():
    lines = render_career_field_lines(_facts(_BUSINESS_CASE))
    head = [x for x in lines if x.startswith("[간지론 관점")]
    assert len(head) == 1 and "간지론에서는 …로 본다" in head[0] and "단정 금지" in head[0]
    axis = [x for x in lines if x.startswith("- 직업 유형 축: 상업형")]
    assert len(axis) == 1 and "간지론에서는" in axis[0]
    assert any(x.startswith("- 사업 시기:") for x in lines)
    # 기존 블록(두드러진 십성·배합)은 그대로 뒤따른다.
    assert any(x.startswith("- 두드러진 십성") for x in lines)


def test_render_workplace_has_no_business_section():
    lines = render_career_field_lines(_facts(_WORKPLACE_ROOTED))
    assert any(x.startswith("- 관성 위치(직장 축)") for x in lines)
    assert not any(x.startswith("- 업종") or x.startswith("- 사업 시기") for x in lines)


def test_directives_mention_ganji_school():
    import saju_api.services.chat_service as cs
    import saju_api.services.report_service as rs

    assert "간지론에서는 …로 본다" in cs._CAREER_FIELD_DIRECTIVE
    assert "간지론에서는 …로 본다" in rs._CAREER_FIELD_REPORT_DIRECTIVE
    assert "합산·상쇄" in cs._CAREER_FIELD_DIRECTIVE
    assert "합산·상쇄" in rs._CAREER_FIELD_REPORT_DIRECTIVE
