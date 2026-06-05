"""피드백 점수화 및 calibrated/probable/uncertain 판정."""

from __future__ import annotations

from saju_shared_types.calibration import (
    FEEDBACK_SCALE,
    MAJOR_EVENTS,
    CalibrationQuestion,
    CalibrationResult,
    FeedbackAnswer,
)
from saju_shared_types.yongsin import AggregatedYongsinResult, YongsinCandidateModel


def score_feedback(expected: str, user_score: int | None) -> float:
    """예측 vs 사용자 응답 매칭 점수(명세 §15.7). unknown(None)은 0."""
    if user_score is None:
        return 0.0
    if expected == "positive":
        return float(user_score)
    if expected == "negative":
        return float(-user_score)
    if expected == "mixed":
        return 0.5 * abs(user_score)
    if expected == "volatile":
        return 0.3 * abs(user_score)
    return 0.0


def _model_by_type(yongsin: AggregatedYongsinResult) -> dict[str, YongsinCandidateModel]:
    return {m.model_type: m for m in yongsin.candidate_models}


def score_calibration(
    questions: list[CalibrationQuestion],
    answers: list[FeedbackAnswer],
    yongsin: AggregatedYongsinResult,
) -> CalibrationResult:
    models = _model_by_type(yongsin)
    answers_by_id = {a.question_id: a for a in answers}

    scores: dict[str, float] = {mt: 0.0 for mt in models}
    hits: dict[str, int] = {mt: 0 for mt in models}
    totals: dict[str, int] = {mt: 0 for mt in models}

    for q in questions:
        ans = answers_by_id.get(q.id)
        if ans is None:
            continue
        user_score = FEEDBACK_SCALE.get(ans.overall_rating)
        if user_score is None:  # 기억나지 않음 → 점수 제외
            continue
        weight = 1.5 if (set(ans.selected_events) & MAJOR_EVENTS) else 1.0
        for model_type, expected in q.expected_effect_by_model.items():
            if model_type not in scores:
                continue
            delta = score_feedback(expected, user_score) * weight
            scores[model_type] += delta
            totals[model_type] += 1
            if delta > 0:
                hits[model_type] += 1

    if not models or all(t == 0 for t in totals.values()):
        return CalibrationResult(
            status="uncertain",
            explanation=["유효한 피드백이 부족합니다(기억나지 않음 제외)."],
            model_scores={k: round(v, 4) for k, v in scores.items()},
        )

    ranked = sorted(scores, key=lambda m: scores[m], reverse=True)
    best = ranked[0]
    best_score = scores[best]
    second_score = scores[ranked[1]] if len(ranked) > 1 else 0.0
    evidence_count = totals[best]
    match_rate = round(hits[best] / totals[best], 4) if totals[best] else 0.0
    gap = (best_score - second_score) / (abs(best_score) + 1e-6)

    if evidence_count >= 4 and match_rate >= 0.75 and gap >= 0.15:
        status = "calibrated"
    elif evidence_count >= 3 and match_rate >= 0.60:
        status = "probable"
    else:
        status = "uncertain"

    m = models[best]
    return CalibrationResult(
        status=status,
        final_yongsin=m.yongsin if status != "uncertain" else None,
        final_heesin=m.heesin if status != "uncertain" else None,
        final_gisin=m.gisin if status != "uncertain" else None,
        final_gusin=m.gusin if status != "uncertain" else None,
        confidence=round(min(match_rate, 0.95), 4),
        evidence_count=evidence_count,
        match_rate=match_rate,
        model_scores={k: round(v, 4) for k, v in scores.items()},
        selected_model=best,
        explanation=[
            f"최적 모델={best}({m.label}), match_rate={match_rate}, evidence={evidence_count}",
            f"판정={status} (gap={round(gap, 3)})",
        ],
    )
