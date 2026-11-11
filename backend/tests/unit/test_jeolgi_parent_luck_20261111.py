"""관할 상위 운 절기 기준 플래그 (2026-11-11) — 기본 OFF 불변 + 두 갈래 ON 동작.

세운은 입춘에, 월운은 절(節)에 바뀐다. 종전에는 월·일 라벨의 양력 연·월로 관할 운을 골랐다.
- YEAR 갈래(`JEOLGI_PARENT_YEAR_ENABLED`): 丑월('YYYY-01')과 입춘 전 날의 관할 세운 = 전년
- MONTH 갈래(`JEOLGI_PARENT_MONTH_ENABLED`): 일운의 관할 월운 = 절기월(없으면 만들어 채운다)

측정은 `scripts/measure_jeolgi_parent_luck.py`. 실사례에서 YEAR 갈래는 丑월 입사 2건의 표지를
잃어 보류했고 두 플래그 모두 기본 OFF 다 — 이 파일은 OFF 가 종전 그대로임과 ON 의 뜻을 고정한다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from saju_manse_analysis.luck.luck_calendar import sewoon_year_of

from saju_api.services.manse_service import calculate, daily_luck_window
from saju_engines import period_v2_config
from saju_engines.clash_relief import _with_year_pillars
from saju_engines.date_selection import _parent_keys
from saju_engines.event_engine_v2 import EventEngineV2, _StackIndex
from saju_engines.health_vulnerability import governing_sewoon_year
from saju_engines.hidden_latent_activation import sewoon_year_of as reexported_sewoon_year_of
from saju_engines.precompute import CompositeBuilder
from saju_engines.repetition_structure import _upper_layers
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import LuckLayer
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.precompute import CompositeLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_BIRTH = BirthInput(
    calendar_type="solar", birth_date=date(1990, 5, 5), birth_time="12:00",
    birth_place_name="서울", gender="male",
)


def _chart(ref: date) -> ManseV2Result:
    return calculate(_BIRTH.model_copy(update={"reference_date": ref}))


def _flags(monkeypatch: pytest.MonkeyPatch, *, month: bool = False, year: bool = False) -> None:
    monkeypatch.setattr(period_v2_config, "JEOLGI_PARENT_MONTH_ENABLED", month)
    monkeypatch.setattr(period_v2_config, "JEOLGI_PARENT_YEAR_ENABLED", year)


def _month_stack(chart: ManseV2Result, label: str) -> dict[LuckLayer, str]:
    assert chart.luck_cycles is not None
    pillar = next(p for p in chart.luck_cycles.monthly_luck if p.label == label)
    stack = _StackIndex(chart).stack_for(GanjiLevel.MONTH, label, pillar)
    return {layer: p.ganji for layer, p in stack}


def _day_stack(chart: ManseV2Result, day: date) -> dict[LuckLayer, str]:
    pillar = daily_luck_window(chart, day, day)[0]
    stack = _StackIndex(chart).stack_for(GanjiLevel.DAY, day.isoformat(), pillar)
    return {layer: p.ganji for layer, p in stack}


def test_flags_default_off_and_reported() -> None:
    versions = period_v2_config.active_versions()
    assert versions["jeolgi_parent_month_enabled"] is False
    assert versions["jeolgi_parent_year_enabled"] is False


def test_sewoon_year_of_single_definition() -> None:
    assert reexported_sewoon_year_of is sewoon_year_of
    assert sewoon_year_of("2027-01") == 2026  # 丑월은 전년 세운
    assert sewoon_year_of("2027-02") == 2027
    assert sewoon_year_of("2026-12") == 2026
    assert sewoon_year_of("2027") == 2027
    assert sewoon_year_of("") is None


# ── YEAR 갈래 ─────────────────────────────────────────────────────────────────


def test_month_stack_sewoon_for_chuk_month(monkeypatch: pytest.MonkeyPatch) -> None:
    """2027-01 辛丑월 — OFF 는 종전대로 丁未(다음 해), YEAR ON 은 관할 세운 丙午."""
    chart = _chart(date(2026, 7, 1))
    _flags(monkeypatch)
    assert _month_stack(chart, "2027-01")[LuckLayer.SEWOON] == "丁未"
    _flags(monkeypatch, year=True)
    on = _month_stack(chart, "2027-01")
    assert on[LuckLayer.SEWOON] == "丙午" and on[LuckLayer.WOLWOON] == "辛丑"
    # 丑월 밖의 달은 그대로다.
    assert _month_stack(chart, "2026-12")[LuckLayer.SEWOON] == "丙午"
    assert _month_stack(chart, "2026-02")[LuckLayer.SEWOON] == "丙午"


def test_month_flag_alone_does_not_touch_month_level(monkeypatch: pytest.MonkeyPatch) -> None:
    chart = _chart(date(2026, 7, 1))
    _flags(monkeypatch, month=True)
    assert _month_stack(chart, "2027-01")[LuckLayer.SEWOON] == "丁未"


def test_day_stack_sewoon_before_ipchun(monkeypatch: pytest.MonkeyPatch) -> None:
    """2027년 입춘(2/4) 전 날은 丙午년 소속 — YEAR ON 에서만 전년 세운."""
    chart = _chart(date(2027, 1, 20))
    _flags(monkeypatch)
    assert _day_stack(chart, date(2027, 1, 20))[LuckLayer.SEWOON] == "丁未"
    _flags(monkeypatch, year=True)
    assert _day_stack(chart, date(2027, 1, 20))[LuckLayer.SEWOON] == "丙午"
    assert _day_stack(chart, date(2027, 2, 3))[LuckLayer.SEWOON] == "丙午"
    assert _day_stack(chart, date(2027, 2, 5))[LuckLayer.SEWOON] == "丁未"


def test_year_level_scores_unchanged_and_only_chuk_month_moves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """YEAR ON 은 연 단위 후보와 丑월 밖 열한 달의 후보를 건드리지 않는다."""
    chart = _chart(date(2026, 7, 1))
    engine = EventEngineV2(_DICTS)

    def snapshot() -> dict[str, list[tuple[str, int]]]:
        out: dict[str, list[tuple[str, int]]] = {}
        for c in engine.score(chart, levels={GanjiLevel.YEAR, GanjiLevel.MONTH}):
            out.setdefault(str(c.period), []).append((str(c.event_key), int(c.score)))
        return {k: sorted(v) for k, v in out.items()}

    _flags(monkeypatch)
    off = snapshot()
    _flags(monkeypatch, year=True)
    on = snapshot()
    changed = {k for k in set(off) | set(on) if off.get(k) != on.get(k)}
    assert changed <= {"2027-01"}


# ── MONTH 갈래 ────────────────────────────────────────────────────────────────


def test_day_stack_wolwoon_before_jeol(monkeypatch: pytest.MonkeyPatch) -> None:
    """소서(7/7) 전 7/3 은 절기상 甲午월 — OFF 는 종전대로 乙未, MONTH ON 은 甲午."""
    chart = _chart(date(2026, 7, 1))
    _flags(monkeypatch)
    assert _day_stack(chart, date(2026, 7, 3))[LuckLayer.WOLWOON] == "乙未"
    _flags(monkeypatch, month=True)
    assert _day_stack(chart, date(2026, 7, 3))[LuckLayer.WOLWOON] == "甲午"
    assert _day_stack(chart, date(2026, 7, 8))[LuckLayer.WOLWOON] == "乙未"  # 절입 뒤는 그대로


def test_day_stack_fills_month_outside_reference_year(monkeypatch: pytest.MonkeyPatch) -> None:
    """기준 연도 12달(2026-02~2027-01) 밖인 2026-01 丑월 — OFF 는 월운 층 없음, ON 은 채운다."""
    chart = _chart(date(2026, 1, 20))
    _flags(monkeypatch)
    assert LuckLayer.WOLWOON not in _day_stack(chart, date(2026, 1, 20))
    _flags(monkeypatch, month=True)
    on = _day_stack(chart, date(2026, 1, 20))
    assert on[LuckLayer.WOLWOON] == "己丑"  # 乙巳년 丑월
    assert on[LuckLayer.SEWOON] == "丙午"  # 세운은 YEAR 갈래가 꺼져 있어 종전(양력 연도)


# ── 같은 계열 소비자 ──────────────────────────────────────────────────────────


def test_precompute_parent_year_for_chuk_month(monkeypatch: pytest.MonkeyPatch) -> None:
    chart = _chart(date(2026, 7, 1))

    def parent_year() -> str | None:
        comps = CompositeBuilder(_DICTS).build(
            chart, "t", "1.0.0", "2026-07-01T00:00:00+00:00",
            levels={CompositeLevel.MONTH, CompositeLevel.YEAR},
        )
        comp = next(
            c for c in comps if c.level is CompositeLevel.MONTH and c.period_key == "2027-01"
        )
        return comp.parent_context.year

    _flags(monkeypatch)
    assert parent_year() == "丁未"
    _flags(monkeypatch, year=True)
    assert parent_year() == "丙午"


def test_health_background_year(monkeypatch: pytest.MonkeyPatch) -> None:
    _flags(monkeypatch)
    assert governing_sewoon_year("2027-01") == 2027
    _flags(monkeypatch, year=True)
    assert governing_sewoon_year("2027-01") == 2026
    assert governing_sewoon_year("2027-03") == 2027


def test_repetition_upper_layer_year(monkeypatch: pytest.MonkeyPatch) -> None:
    chart = _chart(date(2026, 7, 1))

    def year_layer() -> str:
        layers = _upper_layers(chart, "month", "2027-01")
        return next(s + b for name, s, b in layers if name == "year")

    _flags(monkeypatch)
    assert year_layer() == "丁未"
    _flags(monkeypatch, year=True)
    assert year_layer() == "丙午"


def test_clash_relief_year_pillar_for_chuk_month(monkeypatch: pytest.MonkeyPatch) -> None:
    periods = [("2027-01", "辛丑"), ("2027-03", "癸卯")]
    _flags(monkeypatch)
    assert [p for p, _ in _with_year_pillars(periods)] == ["2027", "2027-01", "2027-03"]
    _flags(monkeypatch, year=True)
    assert _with_year_pillars(periods) == [
        ("2026", "丙午"), ("2027-01", "辛丑"), ("2027", "丁未"), ("2027-03", "癸卯"),
    ]


def test_date_selection_parent_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    _flags(monkeypatch)
    assert _parent_keys("2026-07-03") == ("2026", "2026-07")
    assert _parent_keys("2027-01-03") == ("2027", "2027-01")
    _flags(monkeypatch, month=True)
    assert _parent_keys("2026-07-03") == ("2026", "2026-06")  # 소서 전 — 午월
    assert _parent_keys("2027-01-03") == ("2027", "2026-12")  # 소한(1/5) 전 — 子월, 연은 종전
    _flags(monkeypatch, year=True)
    assert _parent_keys("2027-01-20") == ("2026", "2027-01")  # 입춘 전 — 전년 세운, 월은 종전
    _flags(monkeypatch, month=True, year=True)
    assert _parent_keys("2027-01-03") == ("2026", "2026-12")
    assert _parent_keys("2027-02-05") == ("2027", "2027-02")
