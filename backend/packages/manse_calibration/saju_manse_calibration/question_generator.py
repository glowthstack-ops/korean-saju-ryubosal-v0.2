"""검증 질문 5종 생성.

유형: ① 용신 후보 긍정 ② 기신 후보 부정 ③ 경쟁 모델 비교 ④ 사건 도메인 ⑤ 년월 상세.
같은 연도를 중복 질문하지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable

from saju_shared_types.calibration import (
    DOMAIN_LABELS,
    MILITARY_DOMAIN,
    CalibrationEventItem,
    CalibrationQuestion,
    CalibrationQuestionSet,
)
from saju_shared_types.yongsin import AggregatedYongsinResult

EventProvider = Callable[[int], list[CalibrationEventItem]]


def _options(gender: str | None) -> list[str]:
    """영향 영역(범주). 남성은 군 입대/제대 칩을 추가 노출."""
    opts = list(DOMAIN_LABELS.values())
    if gender == "male":
        opts.append(MILITARY_DOMAIN)
    return [*opts, "특별한 일 없음", "기억나지 않음"]


def _anchor(period: dict) -> str:
    """그 해를 간지(세운)·나이로 못박는다(모호한 '전후' 대신 특정 세운 1년을 명시)."""
    ganji = period.get("ganji")
    inner = [str(v) for v in (f"{ganji}세운" if ganji else None, _age_label(period)) if v]
    return f"{period['year']}년" + (f"({'·'.join(inner)})" if inner else "")


def _age_label(period: dict) -> str | None:
    age = period.get("age")
    return f"만 {age}세" if age is not None else None


def _dynamics_hint(period: dict) -> str:
    """세운 지지의 공망·충을 회상 단서로 — 공망=지연·실속, 충=변화·사건."""
    if period.get("has_clash"):
        return " (이 해는 이동·변화·갈등 같은 사건이 두드러졌을 수 있어요)"
    if period.get("is_void"):
        return " (이 해는 기회는 있었어도 결과가 지연·무산되기 쉬웠어요)"
    return ""


def _domains_ko(domains: list[str]) -> str:
    """대표 영역(intent) 라벨을 한글로 — 질문에 '어떤 영역을 보는지' 제시(항목 11)."""
    labels = [DOMAIN_LABELS.get(d, d) for d in domains]
    return "·".join(labels)


def _targets(period: dict) -> tuple[list[str], dict[str, str]]:
    exp = {m: e for m, e in period["expected_by_model"].items() if e != "neutral"}
    return list(exp), exp


def _make(qid: str, qtype: str, period: dict, text: str, domains: list[str],
          options: list[str], period_type: str = "year",
          month: int | None = None) -> CalibrationQuestion:
    targets, exp = _targets(period)
    return CalibrationQuestion(
        id=qid,
        question_type=qtype,
        period_type=period_type,
        year=period["year"],
        month=month,
        period_label=f"{period['year']}년" + (f" {month}월" if month else ""),
        period_range=period.get("range_label", ""),
        target_models=targets,
        expected_effect_by_model=exp,
        ask_domains=domains,
        question_text=text,
        options=options,
    )


def _make_event(qid: str, period: dict, intro: str,
                events: list[CalibrationEventItem]) -> CalibrationQuestion:
    """이벤트형 질문 — 그 해의 검출 이벤트를 나열하고 이벤트별 긍/부정을 받는다."""
    targets, exp = _targets(period)
    return CalibrationQuestion(
        id=qid,
        question_type="event_list",
        period_type="year",
        year=period["year"],
        period_label=f"{period['year']}년",
        period_range=period.get("range_label", ""),
        target_models=targets,
        expected_effect_by_model=exp,
        ask_domains=sorted({e.category for e in events}),
        question_text=intro,
        events=events,
    )


def generate_questions(
    periods: list[dict],
    yongsin: AggregatedYongsinResult,
    gender: str | None = None,
    event_provider: EventProvider | None = None,
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

    def events_for(period: dict) -> list[CalibrationEventItem]:
        return event_provider(period["year"]) if event_provider else []

    questions: list[CalibrationQuestion] = []
    opts = _options(gender)

    # 질문 = 대표 영역(intent) 제시 + 긍정/부정 흐름 택일(항목 11, 2026-06-12 사용자 확정).
    # 흐름은 overall_rating(very_positive~very_negative)으로 받아 score_feedback이
    # 모델 예측(positive/negative)과 대조한다 — 사용자가 중요시하는 영역 기준으로 답하게.
    # 이벤트형 우선 — 그 해의 검출 이벤트를 나열하고 이벤트별 긍/부정을 받는다(사용자 확정).
    # 이벤트가 없으면(검출 0건) 기존 텍스트형 질문으로 폴백한다.
    def add(qid: str, qtype: str, period: dict | None, text: str, domains: list[str]) -> None:
        if period is None:
            return
        events = events_for(period)
        if events:
            questions.append(_make_event(
                qid, period,
                f"{_anchor(period)} 무렵 아래 일들이 있었다면, 각각 본인에게 어떤 영향이었는지"
                f" 골라 주세요.{_dynamics_hint(period)}",
                events,
            ))
        else:
            questions.append(_make(qid, qtype, period, text, domains, opts))

    d1 = ["career", "study", "relationship"]
    p1 = pick(lambda p: "positive" in p["expected_by_model"].values())
    add("q1", "useful", p1,
        f"{_anchor(p1)}는 좋은 기운이 들어올 것으로 본 해예요. 그 무렵 "
        f"{_domains_ko(d1)} 중 본인이 가장 중요하게 여긴 영역의 흐름은 순조로웠나요, "
        f"힘들었나요?{_dynamics_hint(p1)}" if p1 else "", d1)

    d2 = ["money", "family_health", "legal_public"]
    p2 = pick(lambda p: "negative" in p["expected_by_model"].values())
    add("q2", "unfavorable", p2,
        f"{_anchor(p2)}는 다소 까다로운 기운이 예상된 해예요. 그 무렵 "
        f"{_domains_ko(d2)} 면에서 어려움이 있었나요, 오히려 순조로웠나요?"
        f"{_dynamics_hint(p2)}" if p2 else "", d2)

    d3 = ["career", "money", "relationship", "family_health"]
    p3 = pick(lambda p: p["disagree"])
    add("q3", "contrast", p3,
        f"{_anchor(p3)}는 해석이 갈리는 해예요. {_domains_ko(d3)} 중 가장 마음 쓰인 "
        f"영역에서 그해 흐름이 긍정적이었나요, 부정적이었나요?{_dynamics_hint(p3)}"
        if p3 else "", d3)

    p4 = pick(lambda _p: True)
    add("q4", "event_domain", p4,
        f"{_anchor(p4)} 무렵, 가장 크게 변한 영역은 어디였나요?" if p4 else "",
        list(DOMAIN_LABELS))

    p5 = pick(lambda _p: True)
    add("q5", "period_detail", p5,
        f"{_anchor(p5)} 중 특히 변화가 컸던 시기가 있었나요?" if p5 else "",
        ["career", "relationship", "relocation"])

    return CalibrationQuestionSet(
        status="required",
        questions=questions,
        candidate_periods=[
            {"year": p["year"], "age": p["age"], "ganji": p["ganji"], "score": p["score"]}
            for p in periods[:8]
        ],
        note="과거 사건 피드백으로 용신 후보를 검증합니다(기억나지 않음은 점수 제외).",
    )
