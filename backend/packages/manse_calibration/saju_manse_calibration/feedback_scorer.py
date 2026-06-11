"""피드백 점수화 및 calibrated/probable/uncertain 판정."""

from __future__ import annotations

from saju_shared_types.calibration import (
    FEEDBACK_SCALE,
    MAJOR_DOMAINS,
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
        weight = 1.5 if (set(ans.selected_events) & MAJOR_DOMAINS) else 1.0
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

    # 모델 신뢰도(prior)로 가중 — confidence 0.4인 보조 모델이 질문 구성만으로
    # 1등이 되지 않도록 한다.
    weighted = {mt: scores[mt] * models[mt].confidence for mt in models}

    # 최종 용신 확정은 primary 모델을 기준으로 한다. 단, 용신 산출 단계에서 이미
    # final.selected_model로 채택된 보조 모델(조후/통관)은 검증 대상에 포함한다.
    selected_final_model = yongsin.final.get("selected_model")
    primary = [
        mt for mt in models
        if not models[mt].is_auxiliary or mt == selected_final_model
    ]
    explanation: list[str] = []

    if not primary:
        return CalibrationResult(
            status="uncertain",
            evidence_count=0,
            model_scores={k: round(v, 4) for k, v in scores.items()},
            explanation=["primary 모델 부재(보조 모델만 존재) → 단독 확정 불가."],
        )

    ranked = sorted(primary, key=lambda m: weighted[m], reverse=True)
    best = ranked[0]
    best_w = weighted[best]
    second_w = weighted[ranked[1]] if len(ranked) > 1 else 0.0
    evidence_count = totals[best]
    match_rate = round(hits[best] / totals[best], 4) if totals[best] else 0.0
    gap = (best_w - second_w) / (abs(best_w) + 1e-6)

    if best_w <= 0:
        status = "uncertain"
        explanation.append("긍정 근거가 부족합니다(primary 모델 점수 비양수).")
    elif evidence_count >= 4 and match_rate >= 0.75 and gap >= 0.15:
        status = "calibrated"
    elif evidence_count >= 3 and match_rate >= 0.60:
        status = "probable"
    else:
        status = "uncertain"

    m = models[best]

    # 보조 모델 corroboration: 보조가 best여도 단독 확정 금지. 동일 용신을 지지하면
    # 보조 근거로만 반영, 다른 용신을 지지하면 단독 확정 불가를 명시.
    aux = [mt for mt in models if models[mt].is_auxiliary and scores[mt] > 0]
    aux_top = max(aux, key=lambda mt: weighted[mt], default=None)
    confidence = match_rate
    if aux_top is not None:
        if models[aux_top].yongsin == m.yongsin:
            confidence = min(confidence + 0.05, 0.95)
            explanation.append(f"보조 모델({aux_top})이 동일 용신 지지 → 보조 근거 반영.")
        elif weighted.get(aux_top, 0) > best_w:
            explanation.append(
                f"보조 모델({aux_top}) 우세하나 최종 선택 모델이 아니므로 단독 확정 불가 → "
                f"primary({best}) 기준 채택."
            )

    explanation.insert(0, f"최적 primary 모델={best}({m.label}), match_rate={match_rate}, "
                          f"evidence={evidence_count}, 판정={status}(gap={round(gap, 3)})")

    return CalibrationResult(
        status=status,
        final_yongsin=m.yongsin if status != "uncertain" else None,
        final_heesin=m.heesin if status != "uncertain" else None,
        final_gisin=m.gisin if status != "uncertain" else None,
        final_gusin=m.gusin if status != "uncertain" else None,
        confidence=round(min(confidence, 0.95), 4),
        evidence_count=evidence_count,
        match_rate=match_rate,
        model_scores={k: round(v, 4) for k, v in scores.items()},
        weighted_model_scores={k: round(v, 4) for k, v in weighted.items()},
        selected_model=best,
        explanation=explanation,
    )
