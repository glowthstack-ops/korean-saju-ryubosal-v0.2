"""용신 기준 사주 6건 — 엄격 회귀(2026-10-07 데굴님 지시).

데굴님이 확정한 용희기신 정확도 확인용 테스트 사주 목록이다. 진태양시 적용·균시차 미적용
(엔진 기본값)이며 출생지는 프론트 `locations-kr.ts`의 시군구 좌표를 그대로 쓴다.
용신·희신·한신은 **문자 그대로 일치**해야 한다. 바뀌면 그 변경은 데굴님 승인 사항이다
(CLAUDE.md 절대원칙 6, CASEBOOK_CALIBRATION_PLAN §4).
"""

from __future__ import annotations

import pytest

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput

#: (생년월일, 시각, 성별, 출생지, 위도, 경도, 용신, 희신, 기신, 구신, 한신)
#: 용·희·한은 데굴님 목록, 기·구는 2026-10-07 C3 시점 엔진값을 데굴님 승인으로 고정
#: (5역할 전부 엄격).
REFERENCE_CHARTS: list[
    tuple[str, str, str, str, float | None, float | None, str, str, str, str, str]
] = [
    ("1980-11-22", "09:40", "male", "서울", None, None, "土", "火", "木", "水", "金"),
    ("1985-10-29", "22:20", "female", "서울", None, None, "火", "木", "土", "金", "水"),
    ("1985-04-18", "16:00", "male", "경남 사천시", 35.0497, 128.0377, "火", "木", "土", "金", "水"),
    ("2016-03-10", "16:00", "female", "경북 안동시", 36.5802, 128.78, "金", "土", "火", "木", "水"),
    ("2018-01-09", "12:50", "female", "경남 창원시 성산구", 35.1962, 128.6721,
     "火", "木", "土", "金", "水"),
    ("2015-03-01", "03:24", "male", "서울", None, None, "火", "金", "木", "土", "水"),
]


@pytest.mark.parametrize(
    "birth_date, birth_time, gender, place, lat, lon, yongsin, heesin, gisin, gusin, hansin",
    REFERENCE_CHARTS,
    ids=[f"{c[0]}_{c[3]}" for c in REFERENCE_CHARTS],
)
def test_reference_chart_roles(
    birth_date: str, birth_time: str, gender: str, place: str,
    lat: float | None, lon: float | None,
    yongsin: str, heesin: str, gisin: str, gusin: str, hansin: str,
) -> None:
    """기준 사주의 용·희·기·구·한신 5역할이 확정값과 문자 그대로 일치한다."""
    extra = (
        {"latitude": lat, "longitude": lon, "timezone": "Asia/Seoul"}
        if lat is not None and lon is not None else {}
    )
    result = calculate(BirthInput(
        calendar_type="solar", birth_date=birth_date, birth_time=birth_time,
        birth_place_name=place, gender=gender, **extra,
    ))
    final = result.yongsin_analysis.final
    got = tuple(final.get(k) for k in ("yongsin", "heesin", "gisin", "gusin", "hansin"))
    expected = (yongsin, heesin, gisin, gusin, hansin)
    assert got == expected, (
        f"{birth_date} {birth_time} {place}: 기대 용/희/기/구/한={'/'.join(expected)}, "
        f"엔진={'/'.join(str(g) for g in got)} (model={final.get('selected_model')})"
    )
