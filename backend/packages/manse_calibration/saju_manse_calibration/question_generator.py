"""검증 질문 생성.

기본 5종: ① 용신 후보 긍정 ② 기신 후보 부정 ③ 경쟁 모델 비교 ④ 사건 도메인 ⑤ 년월 상세.
같은 연도를 중복 질문하지 않는다.

CAL-P0(상담 사례 파생, doc/v2_2/cases/1980_1122_job_report_case.md) 추가 2종:
- transition_probe: 교운기(대운 교체) 전후 실제 변화 회상 — 질문 ranking에만 관여, 채점 비반영.
- trait_probe: 성향 해석 동의/반박 수집 — review 축적 전용, 용신·점수 채점 절대 비반영.
"""

from __future__ import annotations

from collections.abc import Callable

from saju_shared_types.calibration import (
    CATEGORY_TO_CALIB_DOMAIN,
    DOMAIN_LABELS,
    MILITARY_DOMAIN,
    TRAIT_PROBE_OPTIONS,
    TRANSIT_PROBE_OPTIONS,
    CalibrationEventItem,
    CalibrationQuestion,
    CalibrationQuestionSet,
    DeficiencyPairCandidate,
    DomainExpectation,
    TraitProbeCandidate,
)
from saju_shared_types.yongsin import AggregatedYongsinResult

EventProvider = Callable[[int], list[CalibrationEventItem]]

# 모델 기대극성 문자열 → 극성 수치(도메인 집계용). mixed/neutral은 0(mixed는 변동성으로 별도).
_EXPECTED_POLARITY_NUM: dict[str, float] = {"positive": 1.0, "negative": -1.0}


def build_domain_expectations(
    events: list[CalibrationEventItem],
) -> dict[str, dict[str, DomainExpectation]]:
    """이벤트들의 expected_by_model을 4도메인으로 집계(docs/14 P1 결정③).

    도메인 기대극성 = 그 도메인 이벤트들의 모델별 기대극성 평균(동일 category는 family cap으로
    1회만 반영). 후보 부족(비중립 0건) 도메인은 no_signal(neutral과 구분, 채점 제외).
    """
    model_types: set[str] = set()
    for e in events:
        model_types.update(e.expected_by_model.keys())
    out: dict[str, dict[str, DomainExpectation]] = {}
    for mt in model_types:
        acc: dict[str, dict] = {}
        for e in events:
            domain = CATEGORY_TO_CALIB_DOMAIN.get(e.category)
            exp = e.expected_by_model.get(mt)
            if domain is None or exp is None:
                continue
            a = acc.setdefault(domain, {"pol": [], "vol": 0, "nonneutral": 0, "cats": set()})
            if e.category in a["cats"]:  # family cap — 동일 계열 중복 과대반영 방지
                continue
            a["cats"].add(e.category)
            if exp in _EXPECTED_POLARITY_NUM:
                a["pol"].append(_EXPECTED_POLARITY_NUM[exp])
                a["nonneutral"] += 1
            elif exp == "mixed":
                a["vol"] += 1
                a["nonneutral"] += 1
        dom_out: dict[str, DomainExpectation] = {}
        for domain, a in acc.items():
            if a["nonneutral"] == 0:
                dom_out[domain] = DomainExpectation(status="no_signal")
                continue
            mean_pol = round(sum(a["pol"]) / len(a["pol"]), 3) if a["pol"] else 0.0
            cats = max(1, len(a["cats"]))
            dom_out[domain] = DomainExpectation(
                expected_polarity=mean_pol,
                expected_volatility=round(a["vol"] / cats, 3),
                signal_strength=round(min(1.0, a["nonneutral"] / 2), 3),
                status="scored",
            )
        out[mt] = dom_out
    return out


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
        domain_expectations=build_domain_expectations(events),
    )


# 교운기 체감 회상 단서(대운 교체기 신호와 동일 관점 — saju_engines 의존 없이 질문 문구로만
# 중복 유지. 원본: structural_context.DAEWOON_TRANSITION_SIGNALS_DIRECTIVE). 비단정 회상형.
_TRANSITION_RECALL_HINT = (
    " 큰 사건이 없었더라도 주변 사람이 바뀌거나, 오래된 관계·하던 일을 정리하거나, "
    "거주지·생활 리듬이 달라지거나, 이유 없이 싱숭생숭하며 새 방향을 찾는 느낌이 "
    "있었는지도 함께 봐주세요."
)


def _make_transition_probe(period: dict, qid: str = "q_transition") -> CalibrationQuestion:
    """교운기 변화 회상 질문(CAL-P0-a) — 채점 비반영(target/expected 공란), ranking 전용.

    교운기 신호를 사건 단정으로 표현하지 않는다(회상형 문구 고정 — CAL-P0 금지 조항).
    """
    return CalibrationQuestion(
        id=qid,
        question_type="transition_probe",
        period_type="year",
        year=period["year"],
        period_label=f"{period['year']}년",
        period_range=period.get("range_label", ""),
        question_text=(
            f"{_anchor(period)} 무렵은 10년 대운이 바뀌는 교운기 전후예요. 그 시기에 "
            "직장·소속, 거주지, 주변 사람, 생활 리듬이 바뀌는 흐름이 있었나요?"
            f"{_TRANSITION_RECALL_HINT} 변화가 있었다면 어떤 영역이었는지 골라 주세요."
        ),
        ask_domains=list(DOMAIN_LABELS),
        options=[*DOMAIN_LABELS.values(), "특별한 일 없음", "기억나지 않음"],
    )


def _make_trait_probe(
    candidate: TraitProbeCandidate, anchor_year: int, qid: str = "q_trait",
) -> CalibrationQuestion:
    """성향 동의/반박 수집 질문(CAL-P0-b) — 채점 절대 비반영, review 축적 전용.

    후보(target·engine_basis·문구)는 manse_service의 결정론 predicate가 만든다(원칙 1).
    year는 시간 앵커가 아니라 스키마 필수 필드 충족용(period_type='trait'로 구분).
    """
    return CalibrationQuestion(
        id=qid,
        question_type="trait_probe",
        period_type="trait",
        year=anchor_year,
        period_label="",
        question_text=candidate.question_text,
        options=list(TRAIT_PROBE_OPTIONS),
        trait_target=candidate.target,
        engine_basis=list(candidate.engine_basis),
    )


# CAL-P1-b — B 앵커 랭킹 가중(§1-B 확정 공식). ranking 전용 — 엔진 판정 불변.
_PAIR_AXIS_STRENGTH_W = 1.0  # 천간/지지 각 활성당
_PAIR_DAEWOON_BOOST = 1.0  # 대운 target axis 중첩
_PAIR_RECALL_BONUS = 0.5  # 깨끗한 해(공망·충 없음)
_PAIR_TRANSITION_SAME_PENALTY = 3.0  # q_transition 앵커와 동일 해
_PAIR_TRANSITION_NEAR_PENALTY = 1.0  # q_transition ±1년
_PAIR_BASE_DUP_PENALTY = 1.5  # 기본 q1~q5에서 이미 쓰인 해
# 교운 중첩 예외 안내(§1-B — 유일 후보라 회피 못한 경우에도 단정 금지).
_PAIR_TRANSITION_OVERLAP_NOTE = (
    " 그 시기는 대운 전환감도 함께 있었을 수 있어요 — 그중에서도 이 질문은 위 압박·"
    "변화가 실제로 강해졌는지를 확인합니다."
)


def _select_pair_anchor(
    periods: list[dict],
    axis_element: str,
    base_years: set[int],
    transition_year: int | None,
    daewoon_years: set[int],
) -> dict | None:
    """B 앵커 해 선정(§1-B 확정 랭킹) — 세운 활성 해 기본 + boost/penalty.

    B_anchor_score = 세운 축 강도(천간·지지 활성당 +1) + 대운 중첩 boost + 회상 품질
    보너스 − 교운 동일/인접 penalty − 기본 질문 중복 penalty. 후보가 전혀 없으면 None
    (쌍 전체 미생성 — A 단독 금지). penalty로 자연 회피하되 유일 후보면 그대로 쓴다.
    """
    best: dict | None = None
    best_key: tuple[float, int] | None = None
    for p in periods:
        strength = (p.get("stem_element") == axis_element) + (
            p.get("branch_element") == axis_element
        )
        if strength == 0:
            continue  # 세운에서 target axis가 활성인 해만 후보(§1-B 규칙 1)
        score = strength * _PAIR_AXIS_STRENGTH_W
        if p["year"] in daewoon_years:
            score += _PAIR_DAEWOON_BOOST
        if p.get("clean"):
            score += _PAIR_RECALL_BONUS
        if transition_year is not None:
            if p["year"] == transition_year:
                score -= _PAIR_TRANSITION_SAME_PENALTY
            elif abs(p["year"] - transition_year) == 1:
                score -= _PAIR_TRANSITION_NEAR_PENALTY
        if p["year"] in base_years:
            score -= _PAIR_BASE_DUP_PENALTY
        key = (score, p["year"])  # 동점이면 최근 해(기억 선명)
        if best_key is None or key > best_key:
            best, best_key = p, key
    return best


def _make_pair_questions(
    cand: DeficiencyPairCandidate,
    anchor: dict,
    static_anchor_year: int,
    transition_year: int | None,
    id_suffix: str = "",
) -> list[CalibrationQuestion]:
    """A(정적 결핍)+B(운 작동) 질문 쌍 생성 — pair_id 공유, 채점 비반영(§5).

    B가 교운 앵커와 동일/±1년이면 교운 중첩 안내를 덧붙인다(§1-B 예외 문구 — 단정 금지).
    """
    pair_id = f"pair_{cand.axis_id}_{anchor['year']}"
    static_q = CalibrationQuestion(
        id=f"q_pair_static{id_suffix}",
        question_type="static_deficiency_probe",
        period_type="trait",
        year=static_anchor_year,
        period_label="",
        question_text=cand.static_question_text,
        options=list(TRAIT_PROBE_OPTIONS),
        engine_basis=list(cand.engine_basis),
        pair_id=pair_id,
        axis_type=cand.axis_type,
        axis_id=cand.axis_id,
        axis_element=cand.axis_element,
    )
    transit_text = f"{_anchor(anchor)}에는 {cand.transit_question_text}"
    if transition_year is not None and abs(anchor["year"] - transition_year) <= 1:
        transit_text += _PAIR_TRANSITION_OVERLAP_NOTE
    transit_q = CalibrationQuestion(
        id=f"q_pair_transit{id_suffix}",
        question_type="transit_activation_probe",
        period_type="year",
        year=anchor["year"],
        period_label=f"{anchor['year']}년",
        period_range=anchor.get("range_label", ""),
        question_text=transit_text,
        options=list(TRANSIT_PROBE_OPTIONS),
        engine_basis=list(cand.engine_basis),
        pair_id=pair_id,
        axis_type=cand.axis_type,
        axis_id=cand.axis_id,
        axis_element=cand.axis_element,
    )
    return [static_q, transit_q]


def generate_questions(
    periods: list[dict],
    yongsin: AggregatedYongsinResult,
    gender: str | None = None,
    event_provider: EventProvider | None = None,
    trait_candidates: list[TraitProbeCandidate] | None = None,
    pair_candidates: list[DeficiencyPairCandidate] | None = None,
    daewoon_element_years: dict[str, set[int]] | None = None,
    max_transition_probes: int = 1,
    max_trait_probes: int = 1,
    max_pair_probes: int = 1,
    max_extra_probes: int = 3,
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

    # ── CAL-P0/P1 probe 조립 — 생성 순서: 기본 q1~q5 → transition → pair → trait
    # fallback → cap → 표시 재배치(P1-b 확정). 기본 질문은 위에서 이미 생성돼 보호됨
    # (probe가 기본 질문의 유일 후보 해를 선점해 굶기지 않는다 — QA-P0 불변식).
    base_questions = list(questions)
    base_years = {q.year for q in base_questions}

    # ① transition_probe(교운기 변화 회상) — 남은 연도에서, cap max_transition_probes.
    transition_pool = sorted(
        (p for p in periods if p.get("transition_weight", 0.0) > 0.0),
        key=lambda p: (p["transition_weight"], p["score"], p["year"]),
        reverse=True,
    )
    transition_qs: list[CalibrationQuestion] = []
    for p in transition_pool:
        if len(transition_qs) >= max(0, max_transition_probes):
            break
        if p["year"] in used_years:
            continue
        used_years.add(p["year"])
        qid = "q_transition" if not transition_qs else f"q_transition{len(transition_qs) + 1}"
        transition_qs.append(_make_transition_probe(p, qid))
    transition_year = transition_qs[0].year if transition_qs else None

    # ② P1 static/transit pair — 후보 우선순위 순으로 B 앵커가 잡히는 첫 축 1쌍.
    # B 앵커 없으면 그 축은 건너뛴다(A 단독 생성 금지 — 쌍 전체 미생성).
    pair_qs: list[CalibrationQuestion] = []
    pair_suppress: set[str] = set()
    for cand in (pair_candidates or []):
        if len(pair_qs) >= 2 * max(0, max_pair_probes):
            break
        anchor = _select_pair_anchor(
            periods, cand.axis_element, base_years, transition_year,
            (daewoon_element_years or {}).get(cand.axis_element, set()),
        )
        if anchor is None:
            continue
        suffix = "" if not pair_qs else str(len(pair_qs) // 2 + 1)
        pair_qs.extend(_make_pair_questions(
            cand, anchor, periods[0]["year"], transition_year, id_suffix=suffix,
        ))
        pair_suppress |= set(cand.suppress_axis_keys)

    # ③ trait_probe fallback — pair가 생성된 axis는 suppress(§1-C 확정).
    trait_qs: list[CalibrationQuestion] = []
    for tcand in (trait_candidates or []):
        if len(trait_qs) >= max(0, max_trait_probes):
            break
        if tcand.axis_key is not None and tcand.axis_key in pair_suppress:
            continue
        qid = "q_trait" if not trait_qs else f"q_trait{len(trait_qs) + 1}"
        trait_qs.append(_make_trait_probe(tcand, periods[0]["year"], qid))

    # ④ cap 적용 — 추가 문항 총합 ≤ max_extra_probes, 우선순위 transition > pair > trait
    # (초과 시 pair 우선, trait drop — §1-C 확정). pair는 2문항 통째로만 들어간다.
    budget = max(0, max_extra_probes)
    transition_qs = transition_qs[:budget]
    budget -= len(transition_qs)
    if len(pair_qs) > budget:
        pair_qs, pair_suppress = [], set()
    budget -= len(pair_qs)
    trait_qs = trait_qs[:budget]

    # ⑤ 표시 재배치 — transition → A(static) → B(transit) → q1~q5 → trait fallback.
    questions = [*transition_qs, *pair_qs, *base_questions, *trait_qs]

    return CalibrationQuestionSet(
        status="required",
        questions=questions,
        candidate_periods=[
            {"year": p["year"], "age": p["age"], "ganji": p["ganji"], "score": p["score"]}
            for p in periods[:8]
        ],
        note="과거 사건 피드백으로 용신 후보를 검증합니다(기억나지 않음은 점수 제외).",
    )
