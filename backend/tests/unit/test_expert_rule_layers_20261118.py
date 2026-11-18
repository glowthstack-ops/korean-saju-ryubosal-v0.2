"""2026-11-18 데굴님 제공 규칙 3종 — 투자 매수 시점 참고·궁합 오행 관계·계절 길흉 구간.

서술 전용 층이다(사건 점수·후보 불변). 궁합 오행 관계만 궁합 엔진의 본 신호(보완/마찰 카운트)에
들어간다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines import period_v2_config
from saju_engines.compatibility_engine import _element_affinity_signals
from saju_engines.season_fortune import (
    SEASON_FORTUNE_HEADER,
    SEASON_FORTUNE_MAX_MONTHS,
    SEASON_FORTUNE_MAX_YEARS,
    birth_season,
    chuseok,
    month_grade,
    season_fortune_lines,
    season_grade,
)
from saju_engines.wealth_lecture import (
    INVEST_MONTH_ADVICE_HEADER,
    investment_month_advice_lines,
)
from saju_shared_types.compatibility import CompatDirection, CompatSignalKind
from saju_shared_types.enums import Stem


# ── 계절 길흉 구간 ───────────────────────────────────────────────────────────
def test_birth_season_and_chuseok_dates() -> None:
    assert [birth_season(b) for b in ("寅", "午", "戌", "亥", "丑")] == [
        "봄", "여름", "가을", "겨울", "겨울",
    ]
    assert birth_season("") is None
    assert chuseok(2025) == date(2025, 10, 6)
    assert chuseok(2026) == date(2026, 9, 25)
    assert chuseok(2027) == date(2027, 9, 15)


def test_season_grades_follow_the_given_table() -> None:
    for born in ("봄", "가을", "겨울"):
        assert [season_grade(born, s) for s in ("봄", "여름", "가을", "겨울")] == [1, 2, None, -1]
    assert [season_grade("여름", s) for s in ("봄", "여름", "가을", "겨울")] == [1, -1, 1, 1]


def test_month_grade_splits_autumn_at_chuseok_and_marks_birth_month() -> None:
    # 겨울생(亥월): 추석(2026-09-25)이 든 酉월만 갈리고, 태어난 달은 특히 나쁨.
    assert month_grade("亥", "2026-03") == (1, None, None)
    assert month_grade("亥", "2026-06") == (2, None, None)
    assert month_grade("亥", "2026-08") == (1, None, None)
    assert month_grade("亥", "2026-09") == (1, -1, date(2026, 9, 25))
    assert month_grade("亥", "2026-10") == (-1, None, None)
    assert month_grade("亥", "2026-11") == (-2, None, None)
    assert month_grade("亥", "2026-12") == (-1, None, None)
    assert month_grade("亥", "2027-01") == (-1, None, None)
    # 2025년 추석(10-06)은 酉월 끝자락 — 戌월(10월 라벨)은 추석 뒤.
    assert month_grade("亥", "2025-09") == (1, -1, date(2025, 10, 6))
    assert month_grade("亥", "2025-10") == (-1, None, None)
    # 여름생(午월): 가을은 갈리지 않고, 여름은 나쁨·태어난 달은 특히 나쁨.
    assert month_grade("午", "2026-09") == (1, None, None)
    assert month_grade("午", "2026-05") == (-1, None, None)
    assert month_grade("午", "2026-06") == (-2, None, None)
    assert month_grade("午", "2026-12") == (1, None, None)
    # 반례: 봄생·가을생은 태어난 달에 따로 감점이 없다.
    assert month_grade("卯", "2026-03") == (1, None, None)
    assert month_grade("酉", "2026-09") == (1, -1, date(2026, 9, 25))


def test_season_fortune_lines_shape_and_caps() -> None:
    lines = season_fortune_lines("亥", [2026], [("2026-09", "丁酉"), ("2026-11", "己亥")])
    assert lines[0].startswith(SEASON_FORTUNE_HEADER) and "겨울생(亥월)" in lines[0]
    assert "여름(5~7월) 많이 좋은 구간" in lines[1]
    assert "추석(9월 25일) 전까지 좋은 구간, 추석 뒤부터 나쁜 구간" in lines[1]
    assert "亥월(11월 절기월)은 특히 나쁜 구간" in lines[1]
    assert lines[2] == (
        "계절 구간 2026-09(丁酉월): 추석(9월 25일) 전까지 좋은 구간, 추석 뒤부터 나쁜 구간"
    )
    assert lines[3] == "계절 구간 2026-11(己亥월): 특히 나쁜 구간"
    # 줄 머리가 달 라벨로 시작하지 않는다(창 블록의 요약 표 행과 섞이지 않게).
    assert not any(ln[:4].isdigit() for ln in lines)
    assert "엔진 판정이 본론" in lines[-1]
    # 여름생 해 줄에는 추석 갈림이 없다.
    summer = season_fortune_lines("午", [2026])
    assert "추석" not in summer[1] and "여름(5~7월) 나쁜 구간" in summer[1]
    # 반례: 월지 미상·상한 초과·낼 것 없음 → 빈 목록(추측하지 않는다).
    assert season_fortune_lines(None, [2026]) == []
    assert season_fortune_lines("亥", []) == []
    too_many_years = list(range(2026, 2027 + SEASON_FORTUNE_MAX_YEARS))
    assert season_fortune_lines("亥", too_many_years) == []
    too_many_months = [(f"2026-{m:02d}", "甲子") for m in range(2, 3 + SEASON_FORTUNE_MAX_MONTHS)]
    assert season_fortune_lines("亥", [], too_many_months) == []
    # 연 단위 라벨이 달 목록에 섞여 와도 달 줄로 만들지 않는다.
    assert season_fortune_lines("亥", [], [("2026", "丙午")]) == []


# ── 투자 매수 시점 참고 ─────────────────────────────────────────────────────
def test_investment_advice_lists_only_gui_and_jia_months() -> None:
    lines = investment_month_advice_lines([
        ("2026-04", "壬辰"), ("2026-05", "癸巳"), ("2026-06", "甲午"), ("2026-07", "乙未"),
        ("2026-05", "癸巳"), ("2026", "丙午"),
    ])
    assert len(lines) == 1 and lines[0].startswith(INVEST_MONTH_ADVICE_HEADER)
    assert "2026-05(癸巳월), 2026-06(甲午월)이다" in lines[0]
    assert "2026-04" not in lines[0] and "2026-07" not in lines[0]
    # 하드 가드(절대원칙 8)를 지우지 않는다.
    assert "확정하지" in lines[0] and "종목" in lines[0] and "큰 금액" in lines[0]
    # 반례: 해당 달이 없거나 연 단위뿐이면 줄이 없다 — 지지가 甲·癸와 무관해도 천간만 본다.
    assert investment_month_advice_lines([("2026-04", "壬辰"), ("2026", "甲辰")]) == []
    assert investment_month_advice_lines([]) == []


# ── 궁합 오행 관계 ──────────────────────────────────────────────────────────
def _affinity(a: str, b: str):
    return _element_affinity_signals(Stem(a), Stem(b), self_label="본인", partner_label="상대")


def test_element_affinity_good_and_drain_from_each_side() -> None:
    # 甲(木) → 丙(火): 내가 생해 주는 오행 — 본인에게 상대가 함께하면 좋은 사람.
    (sig,) = _affinity("甲", "丙")
    assert sig.kind is CompatSignalKind.ELEMENT_AFFINITY_GOOD
    assert sig.direction is CompatDirection.HARMONY and not sig.auxiliary
    assert "본인에게 상대은(는) 함께하면 좋은 사람" in sig.detail
    # 정·편을 가르지 않는다 — 甲에게 丁(상관)도 같은 신호.
    assert _affinity("甲", "丁")[0].kind is CompatSignalKind.ELEMENT_AFFINITY_GOOD
    # 甲(木) ↔ 庚(金): 상대가 나를 극함 — 본인에게 상대가 운이 깎일 수 있는 사람.
    (sig,) = _affinity("甲", "庚")
    assert sig.kind is CompatSignalKind.ELEMENT_AFFINITY_DRAIN
    assert sig.direction is CompatDirection.FRICTION
    assert "본인에게 상대은(는) 함께할 때 운이 깎일 수 있는 사람" in sig.detail
    assert "끊으라는 뜻이 아니라" in sig.detail
    assert _affinity("甲", "辛")[0].kind is CompatSignalKind.ELEMENT_AFFINITY_DRAIN
    # 상대 시점도 본다 — 丙에게 甲은 인성이라 본인 쪽 신호는 없고, 甲 쪽 신호만 선다.
    (sig,) = _affinity("丙", "甲")
    assert "상대에게 본인은(는) 함께하면 좋은 사람" in sig.detail
    # 반례: 같은 오행·내가 극하는 쪽(재성)만으로는 신호가 없다(상대 시점에서 극을 받는 쪽만 선다).
    assert _affinity("甲", "乙") == []
    (sig,) = _affinity("甲", "戊")
    assert sig.kind is CompatSignalKind.ELEMENT_AFFINITY_DRAIN
    assert "상대에게 본인은(는) 함께할 때 운이 깎일 수 있는 사람" in sig.detail


def test_layer_flags_default_on() -> None:
    assert period_v2_config.INVEST_MONTH_ADVICE_ENABLED is True
    assert period_v2_config.COMPAT_ELEMENT_AFFINITY_ENABLED is True
    assert period_v2_config.SEASON_FORTUNE_LINE_ENABLED is True


def test_compat_affinity_respects_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import date as _date

    from saju_api.services.manse_service import calculate
    from saju_engines.compatibility_engine import analyze_compatibility
    from saju_shared_types.birth_input import BirthInput
    from saju_shared_types.llm_input import UsefulGods

    def chart(d: _date):
        return calculate(BirthInput(
            birth_date=d, birth_time="10:00", birth_place_name="서울", gender="male",
        ))

    a, b = chart(_date(1990, 5, 5)), chart(_date(1991, 8, 17))
    kinds = {CompatSignalKind.ELEMENT_AFFINITY_GOOD, CompatSignalKind.ELEMENT_AFFINITY_DRAIN}
    expected = _element_affinity_signals(
        Stem(a.pillars.day.stem), Stem(b.pillars.day.stem), self_label="A", partner_label="B",
    )
    on = analyze_compatibility(a, b, UsefulGods(), UsefulGods(), self_label="A", partner_label="B")
    assert on is not None
    assert [s.detail for s in on.signals if s.kind in kinds] == [s.detail for s in expected]
    monkeypatch.setattr(period_v2_config, "COMPAT_ELEMENT_AFFINITY_ENABLED", False)
    off = analyze_compatibility(a, b, UsefulGods(), UsefulGods(), self_label="A", partner_label="B")
    assert off is not None and not [s for s in off.signals if s.kind in kinds]


def test_ten_god_direction_follows_element_rule_without_double_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-11-18 데굴님 "새 규칙대로 가자" — 식상 전체 보완·관성 전체 마찰, 같은 관계는 한 번만."""
    from datetime import date as _date

    from saju_api.services.manse_service import calculate
    from saju_engines.compatibility_engine import _TEN_GOD_DIRECTION, analyze_compatibility
    from saju_shared_types.birth_input import BirthInput
    from saju_shared_types.constants import ten_god
    from saju_shared_types.llm_input import UsefulGods

    assert _TEN_GOD_DIRECTION["식신"] is CompatDirection.HARMONY
    assert _TEN_GOD_DIRECTION["상관"] is CompatDirection.HARMONY
    assert _TEN_GOD_DIRECTION["정관"] is CompatDirection.FRICTION
    assert _TEN_GOD_DIRECTION["편관"] is CompatDirection.FRICTION
    # 반례: 규칙이 말하지 않는 십성은 그대로다.
    assert _TEN_GOD_DIRECTION["정재"] is CompatDirection.HARMONY
    assert _TEN_GOD_DIRECTION["겁재"] is CompatDirection.FRICTION
    assert _TEN_GOD_DIRECTION["편인"] is CompatDirection.NEUTRAL

    def chart(d: _date):
        return calculate(BirthInput(
            birth_date=d, birth_time="10:00", birth_place_name="서울", gender="male",
        ))

    base = chart(_date(1990, 5, 5))
    me = Stem(base.pillars.day.stem)
    # 상대 일간이 본인의 식상 또는 관성인 날짜를 찾아 쌍을 만든다(엔진 계산값으로).
    partner = None
    for offset in range(1, 40):
        cand = chart(_date(1991, 8, offset) if offset <= 31 else _date(1991, 9, offset - 31))
        name = ten_god(me, Stem(cand.pillars.day.stem)).value
        if name in ("상관", "정관"):
            partner = cand
            break
    assert partner is not None
    tg_kinds = {CompatSignalKind.TEN_GOD_TO_PARTNER}
    aff_kinds = {CompatSignalKind.ELEMENT_AFFINITY_GOOD, CompatSignalKind.ELEMENT_AFFINITY_DRAIN}
    on = analyze_compatibility(base, partner, UsefulGods(), UsefulGods())
    assert on is not None
    # 켜져 있으면 방향은 오행 관계 신호 하나가 싣고, 십성 신호는 사실만(중립).
    assert [s.direction for s in on.signals if s.kind in tg_kinds] == [CompatDirection.NEUTRAL]
    expect = CompatDirection.HARMONY if name == "상관" else CompatDirection.FRICTION
    mine = [s for s in on.signals if s.kind in aff_kinds and s.detail.startswith("본인 일간")]
    theirs = [s for s in on.signals if s.kind in aff_kinds and s.detail.startswith("상대 일간")]
    assert [s.direction for s in (mine if name == "상관" else theirs)] == [expect]
    # 끄면 십성 신호가 새 방향표를 그대로 싣는다(오행 관계 신호는 없다).
    monkeypatch.setattr(period_v2_config, "COMPAT_ELEMENT_AFFINITY_ENABLED", False)
    off = analyze_compatibility(base, partner, UsefulGods(), UsefulGods())
    assert off is not None
    assert [s.direction for s in off.signals if s.kind in tg_kinds] == [expect]
    assert not [s for s in off.signals if s.kind in aff_kinds]
    assert on.harmony_count - on.friction_count == off.harmony_count - off.friction_count


def test_entry_season_tenure_line_only_for_extreme_grades() -> None:
    """2026-11-18 데굴님 "입사 자체가 길흉은 아니고 … 해당 회사에 재직할 수 있는 기간"."""
    from saju_engines.season_fortune import (
        ENTRY_SEASON_TENURE_HEADER,
        ENTRY_SEASON_TENURE_MAX_MONTHS,
        entry_season_tenure_line,
    )

    # 겨울생(亥월): 태어난 달 = 오래 다니지 못할 수도, 여름 = 오래 다니게 될 수도.
    line = entry_season_tenure_line("亥", ["2026-11", "2027-06", "2027-03", "2027"])
    assert line is not None and line.startswith(ENTRY_SEASON_TENURE_HEADER)
    assert "2026-11(절기월)은 이 명식이 태어난 달과 같은 亥월" in line
    assert "오래 다니지 못할 수도 있다" in line
    assert "2027-06(절기월)은 계절로 보면 많이 좋은 구간" in line
    assert "오래 다니게 될 수도 있다" in line
    assert "2027-03" not in line  # 좋은 구간(가운데 등급)은 싣지 않는다
    assert "성사되는지와는 별개" in line and "숫자로 말하거나 확정하지" in line
    # 반례: 가운데 등급뿐(봄·겨울의 다른 달)·추석으로 갈리는 달·연 단위 라벨 → 줄이 없다.
    assert entry_season_tenure_line("亥", ["2027-03", "2026-12", "2026-09", "2026"]) is None
    assert entry_season_tenure_line("亥", []) is None
    assert entry_season_tenure_line(None, ["2026-11"]) is None
    # 여름생은 많이 좋은 구간이 없다 — 태어난 달만 선다. 봄생은 태어난 달 감점이 없다.
    summer = entry_season_tenure_line("午", ["2026-06", "2026-05", "2026-12"])
    assert summer is not None and "2026-06" in summer and "오래 다니게 될" not in summer
    spring = entry_season_tenure_line("卯", ["2026-03", "2026-06"])
    assert spring is not None and "오래 다니지 못할" not in spring and "2026-06" in spring
    # 상한: 한쪽에 달이 많아도 앞에서부터 상한까지만.
    many = entry_season_tenure_line("亥", [f"{y}-11" for y in range(2026, 2032)])
    assert many is not None
    assert sum(f"{y}-11" in many for y in range(2026, 2032)) == ENTRY_SEASON_TENURE_MAX_MONTHS

