"""용신 검증(calibration) 루프.

흐름: 후보별 검증 기간 추출 → 질문 5종 생성 → 피드백 점수화 → calibrated/probable/uncertain.
"""

from __future__ import annotations

from collections.abc import Callable

from saju_shared_types.calibration import (
    CalibrationEventItem,
    CalibrationQuestionSet,
    DeficiencyPairCandidate,
    TraitProbeCandidate,
)
from saju_shared_types.pillars import FourPillarsResult
from saju_shared_types.yongsin import AggregatedYongsinResult

from .feedback_scorer import score_calibration, score_feedback
from .period_selector import select_validation_periods, transition_weight
from .question_generator import generate_questions
from .trait_tagging import classify_trait_denial_kind

__all__ = [
    "generate_calibration",
    "select_validation_periods",
    "transition_weight",
    "generate_questions",
    "score_calibration",
    "score_feedback",
    "classify_trait_denial_kind",
]


def generate_calibration(
    yongsin: AggregatedYongsinResult,
    birth_year: int,
    reference_year: int,
    pillars: FourPillarsResult | None = None,
    gender: str | None = None,
    event_provider: Callable[[int], list[CalibrationEventItem]] | None = None,
    transition_years: list[int] | None = None,
    trait_candidates: list[TraitProbeCandidate] | None = None,
    pair_candidates: list[DeficiencyPairCandidate] | None = None,
    daewoon_element_years: dict[str, set[int]] | None = None,
) -> CalibrationQuestionSet:
    """검증 기간 선택 + 질문 생성을 한 번에 수행.

    event_provider 주입 시 연도별 이벤트형 질문(이벤트 나열 + 모델별 기대 극성)을 생성한다
    (saju_engines 의존을 calibration 패키지 밖으로 격리 — manse_service가 클로저로 공급).

    CAL-P0: transition_years(대운 교체 연도)는 교운기 전후 해를 질문 후보 상위로 올리고
    (ranking 전용), trait_candidates는 성향 동의/반박 수집 질문(채점 비반영)을 만든다.
    CAL-P1-b: pair_candidates(정적 결핍 vs 운 작동 이원 질문 축)와
    daewoon_element_years(오행별 대운 활성 연도 — B 앵커 boost용)를 주입한다.
    전부 manse_service가 엔진 확정값에서 결정론적으로 만들어 공급한다.
    """
    periods = select_validation_periods(
        yongsin, birth_year, reference_year, pillars,
        transition_years=transition_years,
    )
    return generate_questions(
        periods, yongsin, gender, event_provider,
        trait_candidates=trait_candidates,
        pair_candidates=pair_candidates,
        daewoon_element_years=daewoon_element_years,
    )
