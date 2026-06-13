"""용신 검증(calibration) 루프.

흐름: 후보별 검증 기간 추출 → 질문 5종 생성 → 피드백 점수화 → calibrated/probable/uncertain.
"""

from __future__ import annotations

from collections.abc import Callable

from saju_shared_types.calibration import CalibrationEventItem, CalibrationQuestionSet
from saju_shared_types.pillars import FourPillarsResult
from saju_shared_types.yongsin import AggregatedYongsinResult

from .feedback_scorer import score_calibration, score_feedback
from .period_selector import select_validation_periods
from .question_generator import generate_questions

__all__ = [
    "generate_calibration",
    "select_validation_periods",
    "generate_questions",
    "score_calibration",
    "score_feedback",
]


def generate_calibration(
    yongsin: AggregatedYongsinResult,
    birth_year: int,
    reference_year: int,
    pillars: FourPillarsResult | None = None,
    gender: str | None = None,
    event_provider: Callable[[int], list[CalibrationEventItem]] | None = None,
) -> CalibrationQuestionSet:
    """검증 기간 선택 + 질문 생성을 한 번에 수행.

    event_provider 주입 시 연도별 이벤트형 질문(이벤트 나열 + 모델별 기대 극성)을 생성한다
    (saju_engines 의존을 calibration 패키지 밖으로 격리 — manse_service가 클로저로 공급).
    """
    periods = select_validation_periods(yongsin, birth_year, reference_year, pillars)
    return generate_questions(periods, yongsin, gender, event_provider)
