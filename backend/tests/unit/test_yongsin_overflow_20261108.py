"""용신 태과(간여지동) 규칙(2026-11-08 데굴님 실측).

같은 용신 오행이 천간·지지에 몰린 운은 '강한 용신운'이 아니다. 모드 off/damp/flip 은 환경변수
`SAJU_YONGSIN_OVERFLOW_MODE`(점수 규칙 → 85사례 적중률로 결정: damp 세운 일치 −1 악화, flip 5지표 +1
개선·악화 없음 → 기본 flip). 여기서는 모듈 상수를 monkeypatch 해 세 모드의 산술과 라벨·십성군 얼굴,
군 필터, 기신 간여지동 불변, coarse 호환을 고정한다.
"""

from __future__ import annotations

import datetime as dt

import pytest
from saju_manse_analysis.luck import luck_cycles as LC

from saju_api.services.manse_service import _calculate  # 캐시 우회(모드별 재계산)
from saju_shared_types.birth_input import BirthInput

# 데굴님 명식(庚申 丁亥 己亥 己巳, 己 일간 신약, 용신 土·희신 火)
# — 2026 丙午(火火)·己丑 대운(土土)이 간여지동 용신.
_BIRTH = BirthInput(
    birth_date=dt.date(1980, 11, 22), birth_time=dt.time(9, 40), birth_place_name="서울 구로구",
    gender="male", latitude=37.4944, longitude=126.8563, timezone="Asia/Seoul",
)


def _calc():
    return _calculate(_BIRTH.model_copy(update={"reference_date": dt.date(2026, 11, 8)}))


def _year(result, label: str):
    return next(p for p in result.luck_cycles.yearly_luck if p.label == label)


def test_off_keeps_pure_yongsin_label(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(LC, "YONGSIN_OVERFLOW_MODE", "off")
    r = _calc()
    y = _year(r, "2026")
    assert y.luck_label == "강한 용신운" and y.luck_score == pytest.approx(1.0, abs=0.01)
    assert r.luck_cycles.daewoon_table[1].luck_label == "강한 용신운"


@pytest.mark.parametrize(
    ("mode", "expect_year", "expect_dw"),
    [("damp", 0.25, 0.61 * 0.25), ("flip", -0.3, -0.3)],
)
def test_overflow_modes_relabel_same_element_yongsin(
    monkeypatch: pytest.MonkeyPatch, mode: str, expect_year: float, expect_dw: float
) -> None:
    monkeypatch.setattr(LC, "YONGSIN_OVERFLOW_MODE", mode)
    r = _calc()
    y = _year(r, "2026")
    # 2026 丙午 = 己 일간에게 火 = 인성 간여지동 → 인다(게으름·멈춤) 얼굴,
    # 己丑 대운 = 비겁 → 군겁쟁재.
    assert y.luck_label == "용신 태과(간여지동·인성)"
    assert y.luck_label_code == "yongsin_overflow_luck"
    assert "인다" in y.luck_summary
    assert y.luck_score == pytest.approx(expect_year, abs=0.02)
    assert y.yongsin_alignment == "혼합"  # coarse 호환 — '용신운'으로 세지 않는다
    dw = r.luck_cycles.daewoon_table[1]
    assert dw.ganji == "己丑" and dw.luck_label == "용신 태과(간여지동·비겁)"
    assert "군겁쟁재" in dw.luck_summary
    assert dw.luck_score == pytest.approx(expect_dw, abs=0.02)
    # 간여지동이 아닌 용신운(2027 丁未: 火·土 다른 오행)과 혼합운(2025 乙巳)은 그대로.
    assert _year(r, "2027").luck_label == "강한 용신운"
    assert _year(r, "2025").luck_label.startswith("천간 기신·지지 용신")
    # 기신 간여지동은 손대지 않는다(태과는 용·희신에만) — 2016 丙申? 아니라 木木 해를 찾는다.
    gisin_same = [
        p for p in r.luck_cycles.yearly_luck
        if p.luck_label == "강한 기신운" and p.ganji in ("甲寅", "乙卯", "壬子", "癸亥")
    ]
    assert all(p.luck_score < 0 for p in gisin_same)


def test_group_filter_limits_rule_to_listed_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    """GROUPS='비겁' 이면 인성 간여지동(2026 丙午)은 종전 '강한 용신운' 그대로."""
    monkeypatch.setattr(LC, "YONGSIN_OVERFLOW_MODE", "damp")
    monkeypatch.setattr(LC, "YONGSIN_OVERFLOW_GROUPS", frozenset({"비겁"}))
    r = _calc()
    assert _year(r, "2026").luck_label == "강한 용신운"
    assert r.luck_cycles.daewoon_table[1].luck_label == "용신 태과(간여지동·비겁)"


def test_default_mode_is_flip() -> None:
    """기본값은 측정 결과(flip)·전 군 적용 — env 미설정 시."""
    assert LC.YONGSIN_OVERFLOW_MODE == "flip" and "all" in LC.YONGSIN_OVERFLOW_GROUPS
