"""후보별 검증 연도/년월 추출 (Phase 4 구현 예정)."""

from __future__ import annotations

from typing import Any


def select_validation_periods(yongsin_analysis: Any, luck_cycles: Any) -> list[dict]:
    """용신/기신 후보가 강해지는 시기·경쟁 모델이 갈리는 시기를 추출한다.

    Phase 4에서 대운/세운(`luck_cycles`)과 후보 모델을 받아 검증 기간을 산출한다.
    """
    raise NotImplementedError("calibration period selection — Phase 4")
