"""검증 질문 5종 생성.

유형: ① 용신 후보 긍정 ② 기신 후보 부정 ③ 경쟁 모델 비교 ④ 사건 도메인 ⑤ 년월 상세.
같은 연도를 중복 질문하지 않는다.
"""

from __future__ import annotations

from saju_shared_types.calibration import (
    EVENT_DOMAINS,
    CalibrationQuestion,
    CalibrationQuestionSet,
)
from saju_shared_types.yongsin import AggregatedYongsinResult

_OPTIONS = [
    *[opt for opts in EVENT_DOMAINS.values() for opt in opts],
    "특별한 일 없음",
    "기억나지 않음",
]


def _targets(period: dict) -> tuple[list[str], dict[str, str]]:
    exp = {m: e for m, e in period["expected_by_model"].items() if e != "neutral"}
    return list(exp), exp


def _make(qid: str, qtype: str, period: dict, text: str, domains: list[str],
          period_type: str = "year", month: int | None = None) -> CalibrationQuestion:
    targets, exp = _targets(period)
    return CalibrationQuestion(
        id=qid,
        question_type=qtype,
        period_type=period_type,
        year=period["year"],
        month=month,
        period_label=f"{period['year']}년" + (f" {month}월" if month else ""),
        target_models=targets,
        expected_effect_by_model=exp,
        ask_domains=domains,
        question_text=text,
        options=_OPTIONS,
    )


def generate_questions(
    periods: list[dict], yongsin: AggregatedYongsinResult
) -> CalibrationQuestionSet:
    if not periods or not yongsin.candidate_models:
        return CalibrationQuestionSet(
            status="not_available",
            note="검증 기간 또는 후보 모델이 부족합니다(생년/기준일 확인).",
        )

    used_years: set[int] = set()

    def pick(predicate) -> dict | None:
        for p in periods:
            if p["year"] not in used_years and predicate(p):
                used_years.add(p["year"])
                return p
        return None

    questions: list[CalibrationQuestion] = []

    p1 = pick(lambda p: "positive" in p["expected_by_model"].values())
    if p1:
        questions.append(_make(
            "q1", "useful", p1,
            f"{p1['year']}년 전후에는 취업·자격증·진로·인연 면에서 일이 풀리는 느낌이 강했나요?",
            ["career", "study", "relationship"],
        ))

    p2 = pick(lambda p: "negative" in p["expected_by_model"].values())
    if p2:
        questions.append(_make(
            "q2", "unfavorable", p2,
            f"{p2['year']}년 전후에는 압박·손실·갈등·건강 문제로 막히는 느낌이 강했나요?",
            ["money", "family_health", "legal_public"],
        ))

    p3 = pick(lambda p: p["disagree"])
    if p3:
        questions.append(_make(
            "q3", "contrast", p3,
            f"{p3['year']}년은 전반적으로 좋았나요, 힘들었나요? (모델 간 예측이 갈리는 해)",
            ["career", "money", "relationship", "family_health"],
        ))

    p4 = pick(lambda _p: True)
    if p4:
        questions.append(_make(
            "q4", "event_domain", p4,
            f"{p4['year']}년 전후 가장 크게 변한 영역을 골라주세요.",
            list(EVENT_DOMAINS),
        ))

    p5 = pick(lambda _p: True)
    if p5:
        questions.append(_make(
            "q5", "period_detail", p5,
            f"{p5['year']}년 중 특히 변화가 컸던 시기(상·하반기/월)가 있었나요?",
            ["career", "relationship", "relocation"],
            period_type="year_month",
        ))

    return CalibrationQuestionSet(
        status="required",
        questions=questions,
        candidate_periods=[
            {"year": p["year"], "age": p["age"], "ganji": p["ganji"], "score": p["score"]}
            for p in periods[:8]
        ],
        note="과거 사건 피드백으로 용신 후보를 검증합니다(기억나지 않음은 점수 제외).",
    )
