"""saju_engines Phase 0 — ManseChart 어댑터 + GanjiCalendarEntry 생성기 검증.

T0.3: 어댑터가 만세력 엔진 결과(`ManseV2Result`)를 정규화 `ManseChart`로 1:1 투영하는지
(원국 간지/일간/공망/대운/성별 매핑) 스냅샷성 검증.
T0.4: 운 문자열 관계(`relations_to_chart`/`gongmang_activation`)가 구조화 `RelationHit`로
변환되고, 충/육합/삼합기여/천간합/공망의 원국 자리·국 구성·완성 오행이 보강되는지 검증.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import adapt_manse_chart, calendar_entries_from_result, relation_hits
from saju_engines.ganji_calendar import to_calendar_entry
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.ganji_calendar import GanjiLevel, RelationType
from saju_shared_types.manse_result import ManseV2Result

_BASE = dict(
    calendar_type="solar",
    birth_date=date(1980, 11, 22),
    birth_time="09:08",
    birth_place_name="서울",
    gender="male",
)


def _result(reference_date: str | None = "2026-06-11") -> ManseV2Result:
    """기준일을 가진 표준 테스트 차트(대운·세운·월운·일운 포함)."""
    return calculate(BirthInput(reference_date=reference_date, **_BASE))


# ── T0.3 어댑터 ────────────────────────────────────────────────────


def test_adapter_projects_chart_identity() -> None:
    """어댑터가 원국 간지·일간·공망·차트ID를 그대로 투영한다."""
    result = _result()
    chart = adapt_manse_chart(result)
    assert result.pillars is not None
    p = result.pillars
    assert chart.chart_id == result.chart_id
    assert chart.day_master == p.day_master
    assert chart.chart.year.stem == p.year.stem
    assert chart.chart.year.branch == p.year.branch
    assert (chart.chart.day.stem, chart.chart.day.branch) == (p.day.stem, p.day.branch)
    assert chart.void_branches == list(p.gongmang_branches)
    # 쌍둥이 미구현 → 고정값.
    assert chart.chart_variant == "original" and chart.twin_shift == 0


def test_adapter_maps_gender_and_daewoon() -> None:
    """성별은 M/F/U로 정규화하고, 대운표 길이·간지를 보존한다."""
    result = _result()
    chart = adapt_manse_chart(result)
    assert chart.birth_info.gender == "M"
    assert result.luck_cycles is not None
    assert len(chart.daewoon_list) == len(result.luck_cycles.daewoon_table)
    first_engine = result.luck_cycles.daewoon_table[0]
    first_adapted = chart.daewoon_list[0]
    assert first_adapted.ganji == first_engine.ganji
    assert first_adapted.start_age == first_engine.start_age


def test_adapter_hour_unknown_yields_none() -> None:
    """시주 미상이면 chart.hour=None, time_unknown 플래그가 선다."""
    result = calculate(
        BirthInput(
            calendar_type="solar", birth_date=date(1980, 11, 22),
            birth_time=None, birth_time_unknown=True,
            birth_place_name="서울", gender="female", reference_date=date(2026, 6, 11),
        )
    )
    chart = adapt_manse_chart(result)
    assert chart.chart.hour is None
    assert chart.birth_info.birth_time_unknown is True
    assert chart.birth_info.gender == "F"


def test_adapter_requires_pillars() -> None:
    """원국이 없는 결과는 어댑터가 거부한다."""
    broken = _result().model_copy(update={"pillars": None})
    with pytest.raises(ValueError, match="pillars"):
        adapt_manse_chart(broken)


# ── T0.4 간지달력 생성기 ────────────────────────────────────────────


def test_calendar_entries_cover_present_levels() -> None:
    """기준일이 있으면 대운/세운/월운/일운 엔트리가 모두 생성된다."""
    result = _result()
    entries = calendar_entries_from_result(result)
    levels = {e.level for e in entries}
    assert {GanjiLevel.DAEWOON, GanjiLevel.YEAR, GanjiLevel.MONTH, GanjiLevel.DAY} <= levels
    # ganji는 stem+branch 결합.
    for e in entries:
        assert e.ganji == f"{e.stem}{e.branch}"


def test_calendar_entries_level_filter() -> None:
    """levels 인자로 특정 계층만 추릴 수 있다."""
    result = _result()
    only_daewoon = calendar_entries_from_result(result, levels={GanjiLevel.DAEWOON})
    assert only_daewoon and all(e.level is GanjiLevel.DAEWOON for e in only_daewoon)


def test_relation_hit_branch_clash_resolves_natal_position(make_pillars) -> None:
    """충 문자열이 원국 자리(해당 지지를 가진 기둥)로 구조화된다.

    원국 일지 子 + 운 지지 午 → 子午충. natal_refs는 day 자리를 가리킨다.
    """
    pillars = make_pillars(
        (Stem.GAP, Branch.SIN), (Stem.BYEONG, Branch.JA),
        (Stem.MU, Branch.JA), (Stem.GAP, Branch.IN), Stem.MU,
    )
    hits = relation_hits(
        GanjiLevel.YEAR, str(Stem.GYEONG), str(Branch.O),
        relations_to_chart=[f"충:{Branch.O}-{Branch.JA}"],
        gongmang_activation=[],
        pillars=pillars,
    )
    assert len(hits) == 1
    hit = hits[0]
    assert hit.type is RelationType.BRANCH_CLASH
    assert hit.luck_ref.side == "luck" and hit.luck_ref.branch == str(Branch.O)
    positions = {r.position for r in hit.natal_refs}
    assert "day" in positions and "month" in positions  # 子가 일지·월지 둘 다


def test_relation_hit_three_harmony_contrib_backfills_members(make_pillars) -> None:
    """삼합기여 문자열이 완성 오행 + 국 구성 원국 지지로 보강된다.

    원국 子·辰 + 운 申 → 申子辰 水국 기여. element=水, natal_refs는 子·辰 자리.
    """
    pillars = make_pillars(
        (Stem.GAP, Branch.JA), (Stem.BYEONG, Branch.JIN),
        (Stem.MU, Branch.O), (Stem.GAP, Branch.IN), Stem.MU,
    )
    hits = relation_hits(
        GanjiLevel.YEAR, str(Stem.GYEONG), str(Branch.SIN),
        relations_to_chart=["삼합기여:水"],
        gongmang_activation=[],
        pillars=pillars,
    )
    contrib = [h for h in hits if h.type is RelationType.THREE_HARMONY_CONTRIB]
    assert len(contrib) == 1
    natal_branches = {r.branch for r in contrib[0].natal_refs}
    assert contrib[0].element == "水"
    assert {str(Branch.JA), str(Branch.JIN)} <= natal_branches


def test_relation_hit_stem_combination_uses_natal_stems(make_pillars) -> None:
    """천간합 문자열은 원국 천간 자리로 해소된다."""
    pillars = make_pillars(
        (Stem.GI, Branch.SA), (Stem.BYEONG, Branch.JA),
        (Stem.MU, Branch.O), (Stem.GAP, Branch.IN), Stem.MU,
    )
    hits = relation_hits(
        GanjiLevel.YEAR, str(Stem.GAP), str(Branch.JA),
        relations_to_chart=[f"천간합:{Stem.GAP}-{Stem.GI}"],
        gongmang_activation=[],
        pillars=pillars,
    )
    assert len(hits) == 1
    hit = hits[0]
    assert hit.type is RelationType.STEM_COMBINATION
    assert {r.position for r in hit.natal_refs} == {"year"}
    assert all(r.stem == str(Stem.GI) for r in hit.natal_refs)


def test_relation_hit_gongmang_fill(make_pillars) -> None:
    """공망전실 문자열이 void_fill로 구조화된다."""
    pillars = make_pillars(
        (Stem.GAP, Branch.SIN), (Stem.BYEONG, Branch.JIN),
        (Stem.MU, Branch.O), (Stem.GAP, Branch.IN), Stem.MU,
    )
    void_branch = pillars.gongmang_branches[0]
    hits = relation_hits(
        GanjiLevel.YEAR, str(Stem.GYEONG), void_branch,
        relations_to_chart=[],
        gongmang_activation=[f"공망전실:{void_branch}"],
        pillars=pillars,
    )
    assert len(hits) == 1 and hits[0].type is RelationType.VOID_FILL


def test_unknown_relation_prefix_skipped(make_pillars) -> None:
    """인식 불가한(미래 추가) 접두사는 조용히 건너뛴다."""
    pillars = make_pillars(
        (Stem.GAP, Branch.SIN), (Stem.BYEONG, Branch.JIN),
        (Stem.MU, Branch.O), (Stem.GAP, Branch.IN), Stem.MU,
    )
    entry = to_calendar_entry(
        GanjiLevel.YEAR, "2026", str(Stem.GYEONG), str(Branch.O),
        relations_to_chart=["미래관계:午-子"], gongmang_activation=[], pillars=pillars,
    )
    assert entry.relations_with_chart == []
