"""용신 검증(calibration) 루프 — 골격 패키지.

명세(`saju_v2_yongsin_calibration_loop_spec.md`)의 흐름:
    후보별 검증 기간 추출 → 질문 5종 생성 → 피드백 점수화 → calibrated/probable/uncertain.

실제 구현은 Phase 4. 현재는 인덱스/greenfield 구조에 맞춘 import 가능한 skeleton으로,
각 단계 함수는 `NotImplementedError`를 던진다(스키마·로직은 후속 PR에서 채운다).
"""

from __future__ import annotations

from .feedback_scorer import score_feedback
from .period_selector import select_validation_periods
from .question_generator import generate_questions

__all__ = [
    "select_validation_periods",
    "generate_questions",
    "score_feedback",
]

STATUS = "skeleton"  # Phase 4에서 구현 예정
