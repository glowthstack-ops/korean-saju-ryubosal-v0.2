"""이사 이동 방위(8방위) + 용신 방위 길흉 — region_direction 엔진 검증.

지역오행(터전)과 별개 축: 목적지가 용신이어도 이동 '방향'은 기신일 수 있다(실로그 고양→서울중구).
"""

from __future__ import annotations

import json
from pathlib import Path

from saju_engines.region_direction import RegionDirection

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_FAV_YONGSIN_TO = {"土": "용신", "火": "희신", "木": "기신", "水": "구신", "金": "한신"}


def _rd() -> RegionDirection:
    return RegionDirection(_DICTS)


def test_coords_resolves_exact_and_token() -> None:
    rd = _rd()
    assert rd.coords("서울 중구") is not None  # 완전일치
    assert rd.coords("고양시 일산동구") == rd.coords("경기도 고양시")  # 세부 동구→시 흡수
    assert rd.coords("없는동네 가나구") is None  # 미등재 → None(graceful)


def test_move_direction_geography() -> None:
    rd = _rd()
    assert rd.move_direction("고양시 일산동구", "서울 중구") == "남동"  # 일산은 서울 중구의 북서
    assert rd.move_direction("서울 강남구", "경기도 고양시") == "북서"
    assert rd.move_direction("서울 중구", "부산") == "남동"
    assert rd.move_direction("부산", "서울 중구") == "북서"


def test_move_direction_missing_region_is_none() -> None:
    rd = _rd()
    assert rd.move_direction("화성외계도시", "서울 중구") is None


def test_cardinal_direction_single_element() -> None:
    rd = _rd()
    # 용신 土·희신 火·기신 木 사주: 사정은 단일 오행.
    assert rd.direction_fit("남", _FAV_YONGSIN_TO)[1] == "매우 유리"  # 火 희신(+1.2)
    assert rd.direction_fit("동", _FAV_YONGSIN_TO)[1] == "주의"  # 木 기신(-2.0)
    assert rd.direction_fit("북", _FAV_YONGSIN_TO)[1] == "다소 주의"  # 水 구신(-1.2)


def test_southeast_is_mixed_wood_fire() -> None:
    """남동 = 木·火 혼합 전환 방위(데굴님 확정) — 한쪽 기신이어도 다른쪽 길신이면 완화."""
    rd = _rd()
    el, label, reason = rd.direction_fit("남동", _FAV_YONGSIN_TO)
    assert "木" in el and "火" in el and "土" in el  # 혼합 표기
    # 木(기신,-2)·火(희신,+1.2)·土(용신,+2) → 0.45*-2+0.45*1.2+0.10*2 = -0.16 → 중립.
    assert label == "중립"
    assert "섞" in reason or "혼합" in reason or "함께" in reason


def test_intercardinal_blend_weights_sum_to_one() -> None:
    from saju_engines.region_direction import _DIRECTION_ELEMENTS
    for direction, weights in _DIRECTION_ELEMENTS.items():
        assert abs(sum(weights.values()) - 1.0) < 1e-9, direction
        if direction in ("동", "남", "서", "북"):
            assert len(weights) == 1  # 사정=단일
        else:
            assert len(weights) == 3 and "土" in weights  # 간방=혼합+土 전환


def test_coords_keys_align_with_region_elements() -> None:
    """region_coords 키는 region_elements 키 형식과 정합('{시도} {시군구}' 또는 시도 폴백)."""
    coords = json.loads((_DICTS / "region_coords.json").read_text("utf-8"))["items"]
    elem = json.loads((_DICTS / "region_elements.json").read_text("utf-8"))["items"]
    elem_keys = {it["region"] for it in elem}
    elem_sido = {it["sido"] for it in elem}
    for it in coords:
        r = it["region"]
        # 시군구 키이면 region_elements에 존재, 아니면 시도 폴백 키여야 한다.
        assert r in elem_keys or r in elem_sido, f"정합 안 됨: {r}"
        assert -90 <= it["lat"] <= 90 and 120 <= it["lon"] <= 132  # 한반도 범위
