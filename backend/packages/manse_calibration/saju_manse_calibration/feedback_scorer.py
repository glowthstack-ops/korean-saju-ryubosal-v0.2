"""피드백 점수화 및 calibrated/probable/uncertain 판정."""

from __future__ import annotations

from saju_shared_types.calibration import (
    MAJOR_CATEGORIES,
    MAJOR_DOMAINS,
    NO_SIGNAL_RATINGS,
    TRAIT_RESPONSES,
    TRAIT_TARGET_KO,
    TRANSIT_ACTIVATION_RESPONSES,
    CalibrationQuestion,
    CalibrationResult,
    DeficiencyPairFeedback,
    FeedbackAnswer,
    PairExpressionHint,
    TraitProbeFeedback,
    experience_polarity,
    experience_volatility,
)
from saju_shared_types.yongsin import AggregatedYongsinResult, YongsinCandidateModel

from .trait_tagging import classify_trait_denial_kind

# 채점 축 가중(docs/14 P1): 영역 극성 = 주축(이벤트 1건보다 크게), 변동성 = 보조.
_DOMAIN_POLARITY_W = 3.0
_DOMAIN_VOLATILITY_W = 1.0


def _score_domains(
    q: CalibrationQuestion,
    ans: FeedbackAnswer,
    scores: dict[str, float],
    hits: dict[str, int],
    totals: dict[str, int],
) -> None:
    """영역별 극성(주축) + 변동성을 모델 도메인 기대와 대조해 누적한다(no_signal 제외)."""
    for model_type, dom_exp in q.domain_expectations.items():
        if model_type not in scores:
            continue
        for domain, exp in dom_exp.items():
            if exp.status != "scored":
                continue  # no_signal — 모델이 그 영역 판단 근거 없음(neutral과 구분)
            rating = ans.domain_ratings.get(domain)
            if rating is None:
                continue
            # CAL-QA(docs/14 §8) — 무신호 응답(no_domain_activity 등)은 극성·변동성
            # 모두 채점 제외(delta 0·분모 제외). unknown 계열과 저장 값만 다르다.
            if rating in NO_SIGNAL_RATINGS:
                continue
            upol = experience_polarity(rating)
            ep = exp.expected_polarity
            if upol is not None and ep is not None:
                sign = 1.0 if ep > 0 else -1.0 if ep < 0 else 0.0
                delta = sign * upol * exp.signal_strength * _DOMAIN_POLARITY_W
                scores[model_type] += delta
                # 일치율 분모에는 '극성 신호가 있는' 대조만 센다. 사용자가 보통/반반(upol 0)이거나
                # 모델이 그 영역에 중립(ep 0)이면 방향 일치를 논할 수 없어 unknown처럼 제외한다.
                # (delta 0이라 scores에는 영향 없음 — evidence/match_rate만 왜곡되던 것을 바로잡음.)
                if upol != 0 and ep != 0:
                    totals[model_type] += 1
                    if delta > 0:
                        hits[model_type] += 1
            ev_vol = exp.expected_volatility
            if ev_vol is not None:
                uvol = experience_volatility(rating)
                if uvol > 0 or ev_vol > 0:
                    vmatch = 1.0 - abs(uvol - ev_vol)  # 0..1(근접도)
                    bonus = (vmatch - 0.5) * 2 * exp.signal_strength * _DOMAIN_VOLATILITY_W
                    scores[model_type] += bonus


def score_feedback(expected: str, user_score: float | None) -> float:
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


# CAL-P0/P1 — 채점에서 제외하는 probe 유형. transition_probe는 ranking 전용,
# trait_probe·P1 pair는 축적 전용이며 전부 용신·기신 role, event score, favorability,
# model_scores, selected_model에 절대 반영하지 않는다(CAL-P1 §5 불변식).
_PROBE_TYPES = frozenset({
    "transition_probe", "trait_probe",
    "static_deficiency_probe", "transit_activation_probe",
})


def _collect_trait_feedback(
    questions: list[CalibrationQuestion],
    answers_by_id: dict[str, FeedbackAnswer],
) -> tuple[list[TraitProbeFeedback], list[str]]:
    """trait_probe 응답을 축적 레코드 + LLM 표현 조정 힌트로 변환한다(채점 미개입).

    반박(denied)·부분 동의(mixed)는 '엔진 오류'가 아니라 발현 조건·전달 형태의 재해석
    재료다 — 힌트는 단정 회피·표현 조정만 지시하고 판정 변경을 금지한다(CAL-P0).
    미응답/알 수 없는 값은 unclear로 처리한다.
    """
    feedback: list[TraitProbeFeedback] = []
    hints: list[str] = []
    for q in questions:
        if q.question_type != "trait_probe":
            continue
        ans = answers_by_id.get(q.id)
        if ans is None:
            continue
        resp = (
            ans.trait_response
            if ans.trait_response in TRAIT_RESPONSES
            else "unclear"
        )
        target = q.trait_target or ""
        feedback.append(TraitProbeFeedback(
            question_id=q.id,
            target=target,
            engine_basis=list(q.engine_basis),
            user_feedback=resp,
            user_statement=ans.trait_statement,
            # CAL-P1 §4 — 반박 결 룰 태깅(채점 비반영, 빈 진술 None).
            denial_kind=classify_trait_denial_kind(ans.trait_statement),
        ))
        if resp in ("denied", "mixed"):
            target_ko = TRAIT_TARGET_KO.get(target, target)
            basis = ", ".join(q.engine_basis) or "명식 신호"
            stated = f" 본인 진술: '{ans.trait_statement}'." if ans.trait_statement else ""
            hints.append(
                f"[성향 표현 조정 — {target_ko}] 이 해석({basis} 기반)에 본인 반박이 "
                f"있었다.{stated} 해당 성향을 단정 서술하지 말고, 재능·기질이 없다는 뜻이 "
                "아니라 발현 조건(환경·시기·전달 형태)에 따라 다르게 드러날 수 있다는 "
                "방향으로 표현을 조정할 것. 용신·점수 등 엔진 판정은 변경하지 않는다."
            )
    return feedback, hints


def _collect_pair_feedback(
    questions: list[CalibrationQuestion],
    answers_by_id: dict[str, FeedbackAnswer],
) -> list[DeficiencyPairFeedback]:
    """P1 pair(A/B) 응답을 축적 레코드로 변환한다 — 채점 미개입(CAL-P1-b §7 저장).

    pair_id로 A(static)·B(transit)를 묶고, 응답이 하나도 없는 쌍은 기록하지 않는다.
    해석 매트릭스 기반 LLM 힌트 생성은 P1-c 스코프 — 여기서는 왕복·축적까지만.
    """
    by_pair: dict[str, dict[str, CalibrationQuestion]] = {}
    for q in questions:
        if q.pair_id is None:
            continue
        if q.question_type == "static_deficiency_probe":
            by_pair.setdefault(q.pair_id, {})["static"] = q
        elif q.question_type == "transit_activation_probe":
            by_pair.setdefault(q.pair_id, {})["transit"] = q
    out: list[DeficiencyPairFeedback] = []
    for pair_id, qs in by_pair.items():
        static_q, transit_q = qs.get("static"), qs.get("transit")
        static_ans = answers_by_id.get(static_q.id) if static_q else None
        transit_ans = answers_by_id.get(transit_q.id) if transit_q else None
        # P1-c 확정 — 전용 필드 static_response 우선, trait_response 폴백(P1-b 하위호환).
        raw_static = (
            (static_ans.static_response or static_ans.trait_response)
            if static_ans
            else None
        )
        static_resp = (
            raw_static
            if raw_static in TRAIT_RESPONSES
            else ("unclear" if raw_static else None)
        )
        transit_resp = (
            transit_ans.transit_response
            if transit_ans
            and transit_ans.transit_response in TRANSIT_ACTIVATION_RESPONSES
            else ("unknown" if transit_ans and transit_ans.transit_response else None)
        )
        if static_resp is None and transit_resp is None:
            continue  # 미응답 쌍 — 빈 레코드 축적 방지
        anchor_q = transit_q or static_q
        assert anchor_q is not None
        out.append(DeficiencyPairFeedback(
            pair_id=pair_id,
            axis_type=anchor_q.axis_type or "",
            axis_id=anchor_q.axis_id or "",
            axis_element=anchor_q.axis_element,
            engine_basis=list(anchor_q.engine_basis),
            static_response=static_resp,
            static_statement=static_ans.trait_statement if static_ans else None,
            static_denial_kind=classify_trait_denial_kind(
                static_ans.trait_statement if static_ans else None
            ),
            transit_year=transit_q.year if transit_q else None,
            transit_response=transit_resp,
            transit_statement=(
                transit_ans.transit_statement if transit_ans else None
            ),
        ))
    return out


# ── A×B 응답 매트릭스 → LLM 표현 힌트(P1-c §6-2) — 판정 변경이 아니라 서술 조정. ──
# 공통 불변 조항: 어떤 조합도 용신·점수 등 엔진 판정을 바꾸지 않으며 처방식 표현을 금지.
_PAIR_HINT_INVARIANT = (
    " 이 힌트는 표현 조정 전용이다 — 용신·희신·기신 역할과 점수 등 엔진 판정은 변경하지 "
    "말고, '부족하니 반드시 보완해야 한다' 식의 처방도 금지."
)
_PAIR_HINT_MATRIX: dict[tuple[str, str], tuple[str, str]] = {
    ("agreed", "strong"): (
        "dual_static_deficiency_and_transit_pressure",
        "이 축은 '없어서 허전하고, 들어오면 부담스럽게 작동하는' 양면성이 있다 — 모순으로 "
        "쓰지 말고, 평소의 결핍 보완 욕구와 운 시기의 작동 압박을 분리해 설명할 것.",
    ),
    ("agreed", "partial"): (
        "conditional_manifestation",
        "평소 결핍 체감은 있으나 운 작동은 일부 상황에서만 확인됐다 — 이 축을 단정적으로 "
        "좋다/나쁘다 하지 말고 조건부로 설명할 것.",
    ),
    ("agreed", "none"): (
        "felt_lack_without_activation",
        "정적 결핍 체감은 있으나 해당 운에서 사건 작동은 약했다 — 이 축을 사건 예측 근거로 "
        "강하게 쓰지 말고 생활감·욕구·보완감 중심으로만 설명할 것.",
    ),
    ("denied", "strong"): (
        "external_period_pressure",
        "평소 결핍 체감은 낮지만 운에서는 실제 사건·압박으로 작동했다 — 성향 설명은 줄이고 "
        "특정 시기의 외부 조건·환경 변화 중심으로 설명할 것.",
    ),
    ("denied", "none"): (
        "deemphasize_axis",
        "정적 체감도 낮고 운 작동도 낮다 — 이 축은 사용자에게 크게 체감되지 않을 수 있으니 "
        "본문 비중을 낮추고 단정 서술을 피할 것('원국상 부족하니 반드시 문제' 금지).",
    ),
}
_PAIR_HINT_HEDGE = (
    "hedge_uncertain",
    "사용자 체감 확인이 부족하다 — 기존 엔진 해석은 유지하되 이 축은 확정적으로 말하지 "
    "말고 가능성·조건부 표현을 쓸 것.",
)
_PAIR_HINT_CONDITIONAL = (
    "conditional_manifestation",
    "부분 체감 또는 일부 작동이다 — '항상 그렇다'가 아니라 상황·환경·시기·관계 조건에 "
    "따라 달라진다고 설명할 것.",
)


def _pair_expression_hint(fb: DeficiencyPairFeedback) -> PairExpressionHint:
    """pair 응답 조합을 서술 조정 힌트로 번역한다(P1-c 매트릭스 — 판정 비개입).

    매핑 우선순위: 확정 5조합 → 어느 한쪽 유보(unclear/unknown/미응답) → 그 외
    mixed/partial 계열은 조건부 발현. instruction에는 불변 조항을 항상 덧붙인다.
    """
    key = (fb.static_response or "", fb.transit_response or "")
    if key in _PAIR_HINT_MATRIX:
        mode, text = _PAIR_HINT_MATRIX[key]
    elif (
        fb.static_response in (None, "unclear")
        or fb.transit_response in (None, "unknown")
    ):
        mode, text = _PAIR_HINT_HEDGE
    else:
        mode, text = _PAIR_HINT_CONDITIONAL
    return PairExpressionHint(
        axis_type=fb.axis_type,
        axis_id=fb.axis_id,
        element=fb.axis_element,
        basis_label="·".join(fb.engine_basis),
        static_response=fb.static_response,
        transit_response=fb.transit_response,
        transit_year=fb.transit_year,
        narrative_mode=mode,
        instruction=text + _PAIR_HINT_INVARIANT,
    )


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

    def accrue(model_type: str, expected: str, user_score: float, weight: float) -> None:
        if model_type not in scores:
            return
        delta = score_feedback(expected, user_score) * weight
        scores[model_type] += delta
        # 방향성 없는 응답(보통/반반 → user_score 0)은 일치율 분모에서 제외(unknown과 동일 취급).
        # '신호 없음'을 '반대'로 세어 match_rate가 부당하게 낮아지던 문제를 바로잡는다.
        if user_score != 0:
            totals[model_type] += 1
            if delta > 0:
                hits[model_type] += 1

    # CAL-P0/P1 — probe 응답은 채점과 완전 분리해 축적만(용신 override 발생 금지).
    trait_feedback, trait_hints = _collect_trait_feedback(questions, answers_by_id)
    pair_feedback = _collect_pair_feedback(questions, answers_by_id)
    pair_hints = [_pair_expression_hint(fb) for fb in pair_feedback]

    for q in questions:
        if q.question_type in _PROBE_TYPES:
            continue  # probe 유형은 채점 루프에서 명시 제외(CAL-P0 불변식)
        ans = answers_by_id.get(q.id)
        if ans is None:
            continue
        # ── 영역별 극성(주축) + 변동성 — docs/14 P1. domain_ratings가 있을 때만 가법 추가한다.
        # no_signal 도메인은 채점 제외(neutral과 구분). 발생 여부는 여기서 채점하지 않는다(결정②).
        if ans.domain_ratings and q.domain_expectations:
            _score_domains(q, ans, scores, hits, totals)
        # CAL-QA(docs/14 §8) — 무신호 이벤트 응답(not_occurred + 레거시 na→무신호 매핑)은
        # 값이 0점인 것으로 부족하고 **브랜치 선택에서도 제외**해야 한다. 안 그러면
        # '그런 일 없었다'만 고른 응답이 이벤트 브랜치를 열어 연도 전체 평점 폴백을
        # 건너뛰게 만들어, 아무것도 안 고른 경우와 점수가 달라진다(간접 개입 = 불변식 위반).
        scoreable_event_ratings = {
            k: v for k, v in ans.event_ratings.items()
            if v not in NO_SIGNAL_RATINGS and v != "na"
        }
        if q.events and scoreable_event_ratings:
            # 이벤트형 — 이벤트별 경험(그래이드) × 강도를 모델별 기대 극성과 대조(보조).
            for ev in q.events:
                user_score = experience_polarity(scoreable_event_ratings.get(ev.event_key))
                if user_score is None:  # na/모름 → 제외
                    continue
                weight = 1.5 if ev.category in MAJOR_CATEGORIES else 1.0
                intensity = ans.event_intensity.get(ev.event_key)
                if intensity:  # 1~3 강도 — 미세 가중(없으면 1.0로 불변)
                    weight *= 1.0 + 0.1 * (max(1, min(3, intensity)) - 1)
                for model_type, expected in ev.expected_by_model.items():
                    accrue(model_type, expected, user_score, weight)
            continue
        # 레거시 — 연도 전체 평점(비이벤트형 질문 호환). 7상태(mixed 포함) 극성으로 채점.
        user_score = experience_polarity(ans.overall_rating)
        if user_score is None:  # 기억나지 않음 → 점수 제외
            continue
        weight = 1.5 if (set(ans.selected_events) & MAJOR_DOMAINS) else 1.0
        for model_type, expected in q.expected_effect_by_model.items():
            accrue(model_type, expected, user_score, weight)

    if not models or all(t == 0 for t in totals.values()):
        return CalibrationResult(
            status="uncertain",
            explanation=["유효한 피드백이 부족합니다(기억나지 않음 제외)."],
            model_scores={k: round(v, 4) for k, v in scores.items()},
            trait_probe_feedback=trait_feedback,
            trait_llm_hints=trait_hints,
            deficiency_pair_feedback=pair_feedback,
            pair_expression_hints=pair_hints,
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
            trait_probe_feedback=trait_feedback,
            trait_llm_hints=trait_hints,
            deficiency_pair_feedback=pair_feedback,
            pair_expression_hints=pair_hints,
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
        trait_probe_feedback=trait_feedback,
        trait_llm_hints=trait_hints,
        deficiency_pair_feedback=pair_feedback,
            pair_expression_hints=pair_hints,
    )
