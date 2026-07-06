"""상대(궁합) 대상 해석 공용 유틸 — 리포트·채팅 공유.

즉석 입력(InlineBirth)을 BirthInput으로 변환한다. 등록 동반자(companion_id)는 호출 측이
SubjectStore로 조회한다(소유자 검증 포함). 시각 미입력 시 시주 제외 모드.
"""

from __future__ import annotations

from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import InlineBirth

from ..location import resolve as _resolve_location

_GENDER_MAP = {"M": "male", "F": "female", "male": "male", "female": "female"}


def inline_to_birth(ib: InlineBirth) -> BirthInput:
    """미등록 즉석 상대(InlineBirth) → 만세 계산용 BirthInput.

    출생지 미입력 시 '서울'로 폴백(경도 보정 기준점 필요 — 정확도 한계는 1회 분석 수용).
    좌표·timezone이 오면 그대로 전달한다(FE 지역 피커 — 백엔드 지명 시드와 무관하게
    정확 보정). 좌표 없이 시드 미등록 자유 지명이 오면(구 클라이언트·채팅 자유 입력)
    계산이 ValueError로 죽지 않게 '서울'로 폴백한다(2026-07-03 즉석입력 지역 미동작 수정).
    """
    cal = ib.calendar_type if ib.calendar_type in ("solar", "lunar") else "solar"
    place = ib.birthplace or "서울"
    has_coords = (
        ib.latitude is not None and ib.longitude is not None and bool(ib.timezone)
    )
    if not has_coords and ib.birthplace:
        try:
            _resolve_location(place, None, None, None)
        except ValueError:
            place = "서울"  # 시드 미등록 지명 — 미입력과 동일 폴백(풀이 중단 방지)
    return BirthInput.model_validate({
        "calendar_type": cal,
        "birth_date": ib.date,
        "birth_time": ib.time,
        "birth_time_unknown": ib.time is None,
        "birth_place_name": place,
        "latitude": ib.latitude if has_coords else None,
        "longitude": ib.longitude if has_coords else None,
        "timezone": ib.timezone if has_coords else None,
        "gender": _GENDER_MAP.get(ib.gender or "", "unknown"),
    })
