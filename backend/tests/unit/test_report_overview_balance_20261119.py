"""한해 리포트 직업 쏠림·채팅과의 내용 차이 교정(2026-11-19 데굴님 "전반적으로 검토할 필요").

실답(2027년 한해풀이): '한눈에·큰 흐름·운과 신호·행동 가이드'가 전부 취업 이야기였고, 관계 섹션은
채팅과 달리 '새로운 인연' 쪽으로 쓰였다. 원인은 리포트 후보 순위가 (현실 적합 > 과거 유사 > 점수)
라서, 원장에 입사 이력이 많은 명식은 취업의 과거 유사도(반복 가산)가 모든 달에서 가장 높았던 것.

- 순위: 종류가 다른 사건은 점수로 겨루고 과거 유사도는 동점 가름에만 쓴다(리포트 한정).
- 개관 섹션: 시점 대표와 영역이 다른 사건을 품질 게이트 안에서 같은 줄 형식으로 싣는다.
- 부수 사건 줄·토픽 요약 줄: 사건 키(영문) 대신 한글 사건명, 언급 생략 구간은 제외.
- 토픽 요약(M07): 직업 상태에 따른 사건 종류 전환을 같은 전환표로.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import pytest

from saju_api.services import report_service as R
from saju_engines.addendum_gate_modifier import (
    AddendumGateModifier,
    GateContext,
    profile_career_key_map,
)
from saju_engines.context_reducer import (
    OVERVIEW_COVERAGE_MIN_SCORE,
    OVERVIEW_RELATIVE_WINDOW,
    SCORE_FLOOR,
)
from saju_engines.report_event_input import candidate_brief
from saju_engines.report_plan import build_section_plans
from saju_engines.topic_builder import _lead_event_keys
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import EventKeyV2
from saju_shared_types.events import Confidence, EventCandidate, EventPolarity, EventType
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec


def _cand(period: str, event_key: str, score: int, personal_match: float = 0.0) -> EventCandidate:
    """실제 후보 DTO — 순위 키와 표기 헬퍼가 읽는 필드를 모두 갖춘다."""
    return EventCandidate(
        event_key=EventKeyV2(event_key), event_type=EventType.PROGRESS,
        period=period, score=score, confidence=Confidence.MEDIUM,
        polarity=EventPolarity.POSITIVE, personal_match=personal_match,
    )


# ── ① 순위 — 과거 유사도가 점수를 뒤집지 않는다 ─────────────────────────────


def test_rank_key_orders_different_events_by_score_first() -> None:
    """실측 재현 — 취업(점수 62·유사도 88)이 재물 변화(점수 100·유사도 18)를 이기지 않는다."""
    job = _cand("2027-12", "job_gain", 62, personal_match=88.2)
    wealth = _cand("2027-12", "wealth_change", 100, personal_match=18.3)
    # 프로필 상태로 눌린 사건(점수 6) — 종전에는 유사도 70 으로 2~3위였다.
    suppressed = _cand("2027-12", "career_change", 6, personal_match=70.0)
    ranked = sorted([job, suppressed, wealth], key=R._CANDIDATE_RANK_KEY)
    assert [str(c.event_key) for c in ranked] == ["wealth_change", "job_gain", "career_change"]


def test_rank_key_uses_personal_match_only_to_break_score_ties() -> None:
    """반례 — 점수가 같으면 과거 유사도가 가른다(같은 사건의 달 사이 순서 유지)."""
    feb = _cand("2027-02", "job_gain", 100, personal_match=103.9)
    may = _cand("2027-05", "job_gain", 100, personal_match=115.8)
    assert sorted([feb, may], key=R._CANDIDATE_RANK_KEY)[0] is may
    # 현실 적합은 여전히 최상위 축이다.
    fit = _cand("2027-03", "relocation", 50)
    fit = fit.model_copy(update={"life_fit": 0.9})
    assert sorted([may, fit], key=R._CANDIDATE_RANK_KEY)[0] is fit


def test_period_representatives_are_not_monopolized_by_a_repeated_event() -> None:
    """원장 이력이 많은 사건이 모든 시점의 대표가 되지 않는다."""
    pool = [
        _cand("2027-02", "job_gain", 100, 103.9), _cand("2027-02", "wealth_change", 98, 10.0),
        _cand("2027-08", "job_gain", 84, 114.5), _cand("2027-08", "wealth_change", 94, 15.0),
        _cand("2027-12", "job_gain", 62, 88.2), _cand("2027-12", "wealth_change", 100, 18.3),
    ]
    reps, _groups = R._period_representatives(
        sorted(pool, key=R._CANDIDATE_RANK_KEY), 8, R._CANDIDATE_RANK_KEY)
    by_period = {c.period: str(c.event_key) for c in reps}
    assert by_period == {
        "2027-02": "job_gain", "2027-08": "wealth_change", "2027-12": "wealth_change",
    }


# ── ② 개관 섹션 — 다른 영역 사건(품질 게이트) ──────────────────────────────


def test_domain_companions_pick_best_of_other_domains_within_gates() -> None:
    """영역이 다른 사건을 영역별 최고 1건씩, 상한까지."""
    rep = _cand("2027-02", "job_gain", 100)
    members = [
        rep,
        _cand("2027-02", "contract_document", 100),     # 대표와 같은 영역(직업) — 제외
        _cand("2027-02", "relationship_change", 99),
        _cand("2027-02", "marriage_signal", 96),         # 관계 영역 2번째 — 제외
        _cand("2027-02", "wealth_change", 98),
        _cand("2027-02", "education_admission", 80),     # 상한(2) 밖
    ]
    out = R._domain_companions([rep], {"2027-02": members})
    assert [str(c.event_key) for c in out["2027-02"]] == ["relationship_change", "wealth_change"]


def test_domain_companions_do_not_promote_weak_signals() -> None:
    """반례 — 게이트 밖 신호는 균형을 위해 끌어올리지 않는다(없으면 대표만)."""
    rep = _cand("2027-05", "job_gain", 100)
    below_abs = _cand("2027-05", "wealth_change", OVERVIEW_COVERAGE_MIN_SCORE - 1)
    below_rel = _cand("2027-05", "relationship_change", 100 - OVERVIEW_RELATIVE_WINDOW - 1)
    assert R._domain_companions([rep], {"2027-05": [rep, below_abs, below_rel]}) == {}
    # 경계 — 상대 창 끝점은 통과한다.
    edge = _cand("2027-05", "relationship_change", 100 - OVERVIEW_RELATIVE_WINDOW)
    out = R._domain_companions([rep], {"2027-05": [rep, edge]})
    assert out["2027-05"] == [edge]


# ── ③ 부수 사건 줄 — 한글 사건명·언급 생략 구간·중복 ────────────────────────


def test_co_signal_lines_use_korean_names_and_skip_weak_or_shown() -> None:
    """사건 키(영문) 대신 한글 사건명 + 강도 + 방향 · 약한 신호·이미 실린 사건은 제외."""
    data = R._ReportData.__new__(R._ReportData)   # 엔진 실행 없이 렌더링만 시험
    rep = _cand("2027-02", "job_gain", 100)
    wealth = _cand("2027-02", "wealth_change", 98)
    contract = _cand("2027-02", "contract_document", 95)
    weak = _cand("2027-02", "career_change", SCORE_FLOOR - 1)   # 프로필 상태로 눌린 사건
    data.period_groups = {"2027-02": [rep, wealth, contract, weak]}
    data._domain_period_groups = {}
    assert data._co_signal_lines([rep]) == [
        f"2027-02: {candidate_brief(wealth)}, {candidate_brief(contract)}"
    ]
    # 이미 후보 줄로 실린 사건(개관 섹션의 다른 영역 사건)은 다시 싣지 않는다.
    assert data._co_signal_lines([rep], shown=[wealth]) == [
        f"2027-02: {candidate_brief(contract)}"
    ]
    brief = candidate_brief(wealth)
    assert "신호 강도 98" in brief and "wealth_change" not in brief


# ── ④ 토픽 요약 줄 — 한글 사건명 + 직업 상태 전환 ───────────────────────────


@dataclass
class _Sig:
    event_key: str | None
    weight: float


def test_lead_event_keys_are_korean_and_follow_occupation_state() -> None:
    """구직 중이면 '이직' 신호를 '취업'으로 읽는다 — 전환 뒤 같은 사건은 한 번만."""
    sigs = [_Sig("career_change", 0.5), _Sig("job_gain", 0.4), _Sig("contract_document", 0.3)]
    plain = _lead_event_keys(sigs, "직업")
    assert "career_change" not in plain and "_" not in plain
    assert plain.count(", ") == 2            # 세 사건 그대로
    mapped = _lead_event_keys(sigs, "직업", key_map=profile_career_key_map("unemployed"))
    assert mapped.count(", ") == 1           # 이직→취업 전환으로 한 사건이 됐다
    assert mapped.split(", ")[0] == _lead_event_keys([_Sig("job_gain", 1.0)], "직업")
    # 반례 — 상태를 모르면 전환하지 않는다(규칙 11: 프로필은 선택).
    assert profile_career_key_map(None) == {}
    assert _lead_event_keys(sigs, "직업", key_map=profile_career_key_map(None)) == plain


@pytest.mark.parametrize("status", ["unemployed", "employee", "public_official", "student", None])
def test_profile_career_key_map_matches_gate_rules(status: str | None) -> None:
    """전환표가 게이트(`_apply_profile_rules`)의 직업 분기와 같은 결과를 낸다(이동운 미동반)."""
    ctx = GateContext(occupation_status=status)
    expected: dict[str, str] = {}
    for ek in (EventKeyV2.JOB_GAIN, EventKeyV2.CAREER_CHANGE, EventKeyV2.PROMOTION):
        new_key, _reasons = AddendumGateModifier._apply_profile_rules(ek, 80, ek, [], ctx, False)
        if new_key is not ek:
            expected[str(ek)] = str(new_key)
    assert profile_career_key_map(status) == expected


# ── ⑤ 통합 — 한해 리포트 개관 섹션이 여러 영역을 싣는다 ─────────────────────

_TODAY = date(2026, 11, 19)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1992-03-14", birth_time="15:20",
    birth_place_name="서울", gender="female", reference_date=_TODAY.isoformat(),
)
_RAW_KEY_RE = re.compile(r"\b[a-z]+_[a-z_]+\b")


def _year_prompts() -> dict[str, str]:
    spec = ReportSpec(
        product_code="RPT_YEAR",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="회원")],
        period=ReportPeriod(start="2027-01", end="2027-12"),
    )
    data = R._ReportData(_BIRTH, spec, _TODAY)
    plans = R._expand_report_plans(build_section_plans(spec), data)
    return {p.section_id: R.build_section_context(p, spec, data).body_prompt for p in plans}


def _block(prompt: str, head: str) -> list[str]:
    """머리 줄이 `head` 로 시작하는 블록의 본문 줄(다음 빈 줄 전까지)."""
    lines = prompt.split("\n")
    for i, ln in enumerate(lines):
        if ln.startswith(head):
            body: list[str] = []
            for nxt in lines[i + 1:]:
                if not nxt.strip():
                    break
                body.append(nxt)
            return body
    return []


def test_year_overview_sections_carry_multiple_domains_in_korean() -> None:
    """'한눈에' 섹션의 후보 줄이 한 영역에 몰리지 않고, 부수·토픽 줄에 영문 키가 없다."""
    prompts = _year_prompts()
    events = [ln for ln in _block(prompts["Y-01"], "[이벤트 후보 — ") if ln.startswith("  - ")]
    # 한 시점에 영역이 다른 사건이 함께 실린다 — 시점 머리 줄 수보다 사건 줄이 많다.
    heads = [ln for ln in _block(prompts["Y-01"], "[이벤트 후보 — ") if ln.startswith("[2")]
    assert len(events) > len(heads)
    co = _block(prompts["Y-01"], "[같은 시점의 함께 나타나는 신호")
    assert co and not any(_RAW_KEY_RE.search(ln) for ln in co)
    topic = _block(prompts["Y-05-H1"], "[M07·career 토픽 신호")
    summaries = [ln for ln in topic if ln.startswith("- ")]
    assert summaries and not any(_RAW_KEY_RE.search(ln) for ln in summaries)
