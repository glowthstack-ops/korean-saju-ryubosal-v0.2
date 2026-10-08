"""C6 B/C — 세운 daewoon_context_score 실험 필드 (2026-10-08 데굴님 승인, 플래그 기본 OFF).

계약: ① 플래그 OFF 면 필드는 None 이고 기존 출력은 byte 불변 ② ON 이어도 luck_score·라벨은 불변이며
별도 필드만 채워진다 ③ blend/gate 식 ④ 첫 대운 전 연도(기준 창)는 None.
"""

from __future__ import annotations

import pytest
from saju_manse_analysis.luck import luck_cycles as lc

from saju_api.services.manse_service import _calculate
from saju_shared_types.birth_input import BirthInput


def _birth(d: str = "1985-10-29") -> BirthInput:
    return BirthInput(calendar_type="solar", birth_date=d, birth_time="22:20",
                      birth_place_name="서울", gender="female", reference_date="2026-10-08")


def _fresh(birth: BirthInput):
    """캐시(manse_service._cache)를 우회해 플래그 변경이 반영된 결과를 받는다."""
    return _calculate(birth)


def test_flag_off_field_is_none() -> None:
    assert lc.SEWOON_DAEWOON_CONTEXT_ENABLED is False  # 기본 OFF
    r = _fresh(_birth())
    assert all(sp.daewoon_context_score is None
               for dw in r.luck_cycles.daewoon_table for sp in dw.sewoon)
    assert all(sp.daewoon_context_score is None for sp in r.luck_cycles.yearly_luck)


def test_blend_fills_separate_field_only(monkeypatch: pytest.MonkeyPatch) -> None:
    off = _fresh(_birth())
    monkeypatch.setattr(lc, "SEWOON_DAEWOON_CONTEXT_ENABLED", True)
    monkeypatch.setattr(lc, "SEWOON_DAEWOON_CONTEXT_MODE", "blend")
    monkeypatch.setattr(lc, "SEWOON_DAEWOON_CONTEXT_W", 0.5)
    on = _fresh(_birth())
    for dw_off, dw_on in zip(off.luck_cycles.daewoon_table, on.luck_cycles.daewoon_table,
                             strict=True):
        assert dw_off.luck_score == dw_on.luck_score
        for a, b in zip(dw_off.sewoon, dw_on.sewoon, strict=True):
            assert (a.luck_score, a.luck_label_code, a.yongsin_alignment) == (
                b.luck_score, b.luck_label_code, b.yongsin_alignment)
            assert b.daewoon_context_score == round(0.5 * a.luck_score + 0.5 * dw_on.luck_score, 4)
    # 기준 창(올해±5)도 소속 대운으로 채워진다.
    dw_by_year = lc.daewoon_score_by_year(on.luck_cycles.daewoon_table)
    for sp in on.luck_cycles.yearly_luck:
        d = dw_by_year.get(int(sp.label))
        assert sp.daewoon_context_score == (
            None if d is None else round(0.5 * sp.luck_score + 0.5 * d, 4))


def test_pre_daewoon_years_are_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """첫 대운 시작 전 유년의 기준 창 세운은 소속 대운이 없어 None."""
    monkeypatch.setattr(lc, "SEWOON_DAEWOON_CONTEXT_ENABLED", True)
    birth = BirthInput(calendar_type="solar", birth_date="2024-03-10", birth_time="10:00",
                       birth_place_name="서울", gender="male", reference_date="2026-10-08")
    r = _fresh(birth)
    first = r.luck_cycles.daewoon_table[0].approx_start_date.year
    pre = [sp for sp in r.luck_cycles.yearly_luck if int(sp.label) < first]
    assert pre and all(sp.daewoon_context_score is None for sp in pre)


def test_gate_mode_formula(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lc, "SEWOON_DAEWOON_CONTEXT_MODE", "gate")
    assert lc.daewoon_context_score(0.8, 0.1) == 0.8          # |대운| < 0.3 → 세운 그대로
    assert lc.daewoon_context_score(0.8, -0.5) == round(0.3 * 0.8 + 0.7 * -0.5, 4)
    monkeypatch.setattr(lc, "SEWOON_DAEWOON_CONTEXT_MODE", "blend")
    monkeypatch.setattr(lc, "SEWOON_DAEWOON_CONTEXT_W", 0.7)
    assert lc.daewoon_context_score(1.0, -1.0) == round(0.7 - 0.3, 4)


def test_yearly_range_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """온디맨드 범위 조회는 daewoon_table 을 넘길 때만 채우고, 기존 호출(생략)은 None 유지."""
    monkeypatch.setattr(lc, "SEWOON_DAEWOON_CONTEXT_ENABLED", True)
    r = _fresh(_birth())
    from saju_shared_types.enums import Stem
    ya = r.yongsin_analysis
    useful = {str(ya.final.get("yongsin")), str(ya.final.get("heesin"))}
    unfav = {str(ya.final.get("gisin")), str(ya.final.get("gusin"))}
    plain = lc.yearly_luck_for_range(r.pillars, Stem(r.pillars.day.stem), useful, unfav, [2030])
    ctx = lc.yearly_luck_for_range(r.pillars, Stem(r.pillars.day.stem), useful, unfav, [2030],
                                   daewoon_table=r.luck_cycles.daewoon_table)
    assert plain[0].daewoon_context_score is None
    assert ctx[0].daewoon_context_score is not None
    assert plain[0].luck_score == ctx[0].luck_score
