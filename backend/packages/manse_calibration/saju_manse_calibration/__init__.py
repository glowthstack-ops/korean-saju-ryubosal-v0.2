"""용신 검증(calibration) 루프.

흐름: 후보별 검증 기간 추출 → 질문 5종 생성 → 피드백 점수화 → calibrated/probable/uncertain.
"""

from __future__ import annotations

from saju_shared_types.calibration import CalibrationQuestionSet
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
) -> CalibrationQuestionSet:
    """검증 기간 선택 + 질문 5종 생성을 한 번에 수행."""
    periods = select_validation_periods(yongsin, birth_year, reference_year)
    return generate_questions(periods, yongsin)
