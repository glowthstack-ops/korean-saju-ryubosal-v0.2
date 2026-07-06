"""즉석 상대(InlineBirth) 출생지 처리 — 좌표 전달·시드 미등록 지명 폴백 (2026-07-03 수정).

버그: 즉석입력 출생지가 자유 텍스트로만 전송되고 백엔드 지명 시드는 4개(서울/부산/도쿄/
뉴욕)뿐이라, 그 외 지명은 resolve ValueError로 풀이가 죽었다. 수정: FE 피커가 좌표·tz를
함께 보내면 그대로 전달(request-source resolve), 좌표 없는 미등록 지명은 서울 폴백.
"""

from __future__ import annotations

import pytest

from saju_api.location import resolve
from saju_api.services.partner_resolve import inline_to_birth
from saju_shared_types.intent import InlineBirth


def test_coords_passed_through_for_picker_selection() -> None:
    """지역 피커 선택(좌표·tz 동반) — 시드에 없는 지명도 그대로 정확 계산된다."""
    birth = inline_to_birth(InlineBirth(
        date="1990-05-05", time="10:00", gender="F",
        birthplace="성남시 분당구", latitude=37.3825, longitude=127.1188,
        timezone="Asia/Seoul",
    ))
    assert birth.birth_place_name == "성남시 분당구"
    assert birth.latitude == 37.3825 and birth.longitude == 127.1188
    assert birth.timezone == "Asia/Seoul"
    # 좌표 동반이면 resolve가 request 소스로 통과(시드 무관).
    loc = resolve(birth.birth_place_name, birth.latitude, birth.longitude, birth.timezone)
    assert loc.source == "request"


def test_unseeded_free_text_falls_back_to_seoul() -> None:
    """좌표 없는 시드 미등록 지명(구 클라이언트·자유 입력) — 죽지 않고 서울 폴백."""
    birth = inline_to_birth(InlineBirth(date="1990-05-05", birthplace="분당"))
    assert birth.birth_place_name == "서울"
    assert birth.latitude is None and birth.timezone is None


def test_seeded_name_without_coords_kept() -> None:
    """시드 등록 지명(부산)은 좌표 없이도 이름 유지 — 기존 동작 보존."""
    birth = inline_to_birth(InlineBirth(date="1990-05-05", birthplace="부산"))
    assert birth.birth_place_name == "부산"


def test_no_birthplace_defaults_to_seoul() -> None:
    """출생지 미입력 — 기존 서울 폴백 유지(시주 제외 모드도 유지)."""
    birth = inline_to_birth(InlineBirth(date="1990-05-05"))
    assert birth.birth_place_name == "서울"
    assert birth.birth_time_unknown is True


def test_partial_coords_treated_as_no_coords() -> None:
    """좌표가 불완전(tz 누락 등)하면 좌표 미전달로 취급 — 미등록 지명이면 폴백."""
    birth = inline_to_birth(InlineBirth(
        date="1990-05-05", birthplace="분당", latitude=37.38, longitude=None,
    ))
    assert birth.birth_place_name == "서울"
    assert birth.latitude is None


def test_unseeded_name_without_fallback_would_raise() -> None:
    """전제 확인 — 폴백이 없으면 미등록 지명은 resolve가 실제로 실패한다(버그 재현)."""
    with pytest.raises(ValueError):
        resolve("분당", None, None, None)
