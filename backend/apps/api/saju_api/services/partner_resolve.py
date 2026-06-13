"""상대(궁합) 대상 해석 공용 유틸 — 리포트·채팅 공유.

즉석 입력(InlineBirth)을 BirthInput으로 변환한다. 등록 동반자(companion_id)는 호출 측이
SubjectStore로 조회한다(소유자 검증 포함). 시각 미입력 시 시주 제외 모드.
"""

from __future__ import annotations

from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import InlineBirth

_GENDER_MAP = {"M": "male", "F": "female", "male": "male", "female": "female"}


def inline_to_birth(ib: InlineBirth) -> BirthInput:
    """미등록 즉석 상대(InlineBirth) → 만세 계산용 BirthInput.

    출생지 미입력 시 '서울'로 폴백(경도 보정 기준점 필요 — 정확도 한계는 1회 분석 수용).
    """
    cal = ib.calendar_type if ib.calendar_type in ("solar", "lunar") else "solar"
    return BirthInput.model_validate({
        "calendar_type": cal,
        "birth_date": ib.date,
        "birth_time": ib.time,
        "birth_time_unknown": ib.time is None,
        "birth_place_name": ib.birthplace or "서울",
        "gender": _GENDER_MAP.get(ib.gender or "", "unknown"),
    })
