"""피드백 점수화 (Phase 4 구현 예정).

예측(expected) vs 사용자 응답(user_score, -2..+2, 기억없음=None) 매칭 점수.
명세 §15.7의 score_feedback 규칙을 Phase 4에서 구현한다.
"""

from __future__ import annotations


def score_feedback(expected: str, user_score: int | None) -> float:
    raise NotImplementedError("calibration feedback scoring — Phase 4")
