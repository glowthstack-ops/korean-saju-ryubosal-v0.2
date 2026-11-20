"""진입 시기 두 칸 엔진 배정(2026-10-24 실답 web-mvm8zqyr — '내년 4월 취업?' → '최대한 빨리 언제?').

결함 체인: ①같은 사건 키(job_gain)의 후보가 '취업 성사 가능성'(기회·유입)과 '구직·채용 국면'
(압박·부담)으로 갈리는데 두 칸 지시가 "후보 달을 성사 달로"라고만 해 '최대한 빨리' 질문에서 가장
이른 국면 달(2027-02)이 성사 달로 올라감 ②성사 방향 후보 2027-04가 2턴 답에서 통째로 빠짐 ③1턴
답이 두 칸 표지를 안 써 승계 슬롯이 비고, 승계 지시가 명시 시점 후속에만 붙어 '언제' 열린 후속엔
비켜 감.

§4-7(같은 날 저녁): 두 모드(direction/trigger)를 두고 정밀도 측정으로 trigger·95점을 기본으로 정했다
(`scripts/measure_entry_slot_modes.py`). direction 모드 규칙은 비교·회귀용으로 보존한다.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from saju_api.services import chat_service
from saju_api.services.chat_service import (
    _decision_periods,
    _entry_slot_block,
    _prior_entry_slots_directive,
    _record_entry_slots,
)
from saju_engines import counseling_arbiter as ca
from saju_engines.answer_label_audit import audit_entry_candidate_coverage, month_mentioned
from saju_engines.context_reducer import ASKED_EVENT_STRONG_MIN, asked_event_score_in_period
from saju_engines.entry_slots import (
    COND_ADVERSE,
    COND_SMOOTH,
    DEFAULT_ENTRY_SLOT_MODE,
    ENTRY_DONE_MIN_SCORE,
    ENTRY_LIKELY_MIN_SCORE,
    ENTRY_POSSIBLE_MIN_SCORE,
    ENTRY_SLOT_HEADER,
    NO_ABSENCE_CLAUSE,
    NOTE_DELAY,
    assign_entry_slots,
    condition_grade,
    entry_slot_directive,
    is_earliest_question,
    resolve_mode,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.conversation import ConversationState
from saju_shared_types.intent import (
    Domain,
    EventKey,
    IntentJson,
    QueryType,
    TimeRange,
)
from saju_shared_types.llm_input import LlmEventCandidate

_TODAY = date(2026, 10, 24)


def _intent(start: str | None, event: EventKey | None = EventKey.JOB_GAIN) -> IntentJson:
    tr = None
    if start is not None:
        tr = TimeRange(type="absolute", start=start, end=start, granularity="month")
    return IntentJson(
        intent_id="i", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.CAREER,
        event_key=event, time_range=tr,
    )


def _cand(
    period: str, score: int, quality: str, *, ganji: str = "", review: bool = False,
    direction: str = "", event: EventKey = EventKey.JOB_GAIN,
) -> LlmEventCandidate:
    return LlmEventCandidate(
        event_key=event, period=period, ganji=ganji, daewoon_context="壬辰", score=score,
        confidence="medium", polarity="positive", quality=quality, review_month=review,
        direction=direction,
    )


# 실답 2턴 Top-5 구성(오전 라벨 기준) — 가장 이른 후보가 국면(pressure), 성사 방향(opportunity)은
# 뒤.
_LIVE_TOP5 = [
    _cand("2027-02", 90, "pressure", ganji="壬寅"),
    _cand("2027-05", 88, "opportunity", ganji="乙巳"),
    _cand("2027-03", 86, "pressure", ganji="癸卯"),
    _cand("2027-04", 87, "opportunity", ganji="甲辰"),
    _cand("2026-12", 60, "pressure", ganji="庚子"),
]
# trigger 모드 반례 — 가장 이른 성사 가능 달은 조건 불리(2027-02), 순조한 성사 달은 뒤(2027-04).
_TRIGGER_SET = [
    _cand("2027-02", 96, "pressure", ganji="壬寅"),
    _cand("2027-05", 95, "opportunity", ganji="乙巳", direction="기회·유입 · 지연"),
    _cand("2027-03", 86, "pressure", ganji="癸卯"),
    _cand("2027-04", 97, "opportunity", ganji="甲辰"),
    _cand("2026-12", 60, "pressure", ganji="庚子"),
    _cand("2026-11", 51, "opportunity", ganji="己亥"),  # 55 미만 — 어느 칸에도 없음
]


def test_default_mode_and_threshold_are_measured_values() -> None:
    assert DEFAULT_ENTRY_SLOT_MODE == "trigger" and ENTRY_DONE_MIN_SCORE == 95
    assert resolve_mode(None) in ("trigger", "direction")
    assert resolve_mode("direction") == "direction" and resolve_mode("nonsense") == "trigger"


# ── A. direction 모드(비교·회귀용) ──────────────────────────────────────────────


def test_direction_mode_splits_by_result_direction() -> None:
    a = assign_entry_slots(_LIVE_TOP5, mode="direction")
    assert a is not None and a.mode == "direction"
    assert a.done_periods == ["2027-04", "2027-05"]
    assert a.move_periods == ["2026-12", "2027-02", "2027-03"]
    assert a.to_state_slots() == {"done": "2027-04", "move": "2027-03"}
    cands = [
        _cand("2027-01", 80, "opportunity", direction="기회·유입 · 지연"),
        _cand("2027-02", 80, "opportunity", review=True),
        _cand("2027-03", 80, "loss"),
        _cand("2027-04", 80, "achievement"),
    ]
    b = assign_entry_slots(cands, mode="direction")
    assert b is not None and b.done_periods == ["2027-04"]
    d = entry_slot_directive(a, event_ko="취업·합격", earliest_asked=True)
    assert "성사 달 후보(결과 방향 긍정): 2027-04·2027-05" in d
    assert "국면 달을 성사 달로 세우지 말 것" in d and "가장 이른 2027-04로 두고" in d


def test_direction_mode_without_done_names_months_without_absence() -> None:
    """2026-11-20: 성사 방향 후보가 없어도 '없다'고 선언시키지 않는다 — 있는 달을 이름 들어 말한다.

    direction 모드(비교·회귀용)의 무성사 갈래.
    """
    a = assign_entry_slots(
        [_cand("2027-02", 90, "pressure"), _cand("2027-03", 86, "pressure")], mode="direction",
    )
    assert a is not None
    d = entry_slot_directive(a, event_ko="취업·합격", earliest_asked=True)
    assert "움직임이 보이는 달을 찾아보니" in d and "2027-02·2027-03" in d
    assert "입사·계약이 맺어지는 달로 세우지는 말 것" in d and NO_ABSENCE_CLAUSE in d
    assert "성사 달 후보 없음" not in d and "성사 달 후보가 없고" not in d


# ── B. trigger 모드(기본) — 점수 하한 + 조건 등급 ───────────────────────────────


def test_trigger_mode_splits_by_score_and_grades_conditions() -> None:
    a = assign_entry_slots(_TRIGGER_SET, mode="trigger", done_min=95)
    assert a is not None and a.mode == "trigger" and a.done_min == 95
    assert a.done_periods == ["2027-02", "2027-04", "2027-05"]
    assert a.move_periods == ["2026-12", "2027-03"]  # 51점(2026-11)은 어느 칸에도 없다
    assert a.conditions["2027-02"] == COND_ADVERSE
    assert a.conditions["2027-04"] == COND_SMOOTH
    assert a.conditions["2027-05"] == f"{COND_SMOOTH} · {NOTE_DELAY}"  # 지연은 제외가 아니라 주석
    assert a.earliest_done == "2027-02" and a.earliest_smooth == "2027-04"
    assert a.to_state_slots() == {"done": "2027-02", "move": "2026-12"}


def test_trigger_mode_threshold_and_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    # 오전 라벨 세트(최고 90점)는 95 하한에서 성사 가능 달이 없고 전부 움직이는 달이다.
    a = assign_entry_slots(_LIVE_TOP5, mode="trigger")
    assert a is not None and a.done_periods == []
    assert a.move_periods == ["2026-12", "2027-02", "2027-03", "2027-04", "2027-05"]
    monkeypatch.setenv("SAJU_ENTRY_DONE_MIN_SCORE", "85")
    b = assign_entry_slots(_LIVE_TOP5, mode="trigger")
    assert b is not None and b.done_periods == ["2027-02", "2027-03", "2027-04", "2027-05"]
    monkeypatch.setenv("SAJU_ENTRY_SLOT_MODE", "direction")
    assert resolve_mode() == "direction"


def test_condition_grade_translates_direction_not_outcome() -> None:
    assert condition_grade(_cand("2027-02", 96, "pressure")) == COND_ADVERSE
    assert condition_grade(_cand("2027-02", 96, "loss")) == COND_ADVERSE
    assert condition_grade(_cand("2027-02", 96, "mixed")).startswith("완화")
    assert condition_grade(_cand("2027-02", 96, "opportunity", review=True)) == (
        f"{COND_SMOOTH} · 검토월(계약 유지력 낮음)"
    )


def test_trigger_directive_names_earliest_and_smooth_months() -> None:
    a = assign_entry_slots(_TRIGGER_SET, mode="trigger", done_min=95)
    assert a is not None
    d = entry_slot_directive(
        a, event_ko="취업·합격", earliest_asked=True,
        ganji_by_period={"2027-02": "壬寅", "2027-04": "甲辰"},
    )
    assert d.startswith(ENTRY_SLOT_HEADER)
    # 2026-11-20: 틀 = 유력한 달(93점 이상 전부, 시점순 · 조건 등급 병기 · 최고점 표시).
    assert "유력한 달('취업·합격' 사건 신호가 매우 강한 달" in d
    assert (
        "2027-02(壬寅 · 조건 불리(처우·강도 주의))·"
        "2027-04(甲辰 · 순조 · 신호 가장 강함)·2027-05(순조 · " in d
    )
    # 86~92점은 약하지만 가능성 있는 달(조건 등급 없음), 86 미만은 '흐름이 보이는 달'로만.
    assert "약하지만 가능성 있는 달(신호는 있으나 유력한 달보다 약함): 2027-03." in d
    assert "그 밖에 흐름이 보이는 달(탐색·준비 단계): 2026-12." in d
    assert set(a.conditions) == {"2027-02", "2027-04", "2027-05"}
    # 95점 이상(성사 가능 달)은 유력한 달 가운데 결정 행동이 붙는 달로 병기한다.
    assert "유력한 달 가운데 2027-02(壬寅)·2027-04(甲辰)·2027-05은(는) 신호가 가장 강한 구간" in d
    assert "가장 이른 유력한 달은 2027-02(壬寅)(조건 불리" in d
    assert "조건까지 순조한 가장 이른 달은 2027-04(甲辰)" in d
    assert "국면으로 격하하지 말 것" in d and "각각 한 번씩 달 이름을 들어" in d
    assert "유력한 달을 찾아보니" in d and NO_ABSENCE_CLAUSE in d
    d2 = entry_slot_directive(a, event_ko="취업·합격")
    assert "가장 이른 유력한 달" not in d2


def test_trigger_directive_without_done_names_likely_months() -> None:
    """95점 이상이 없어도 93점 이상은 전부 '유력한 달' — 부재 선언을 시키지 않는다(2026-11-20).

    데굴님: "성사가 확정되는 달은 보이지 않지만 … 은 앞으로 네게 그런 기회는 없어 라고 말하는 것과
    같아. 유력한 달을 찾아보니, 같은 식으로 정리해주는게 맞을 것 같아."
    """
    cands = [
        _cand("2027-02", 94, "pressure"), _cand("2027-05", 93, "opportunity"),
        _cand("2027-03", 92, "pressure"), _cand("2027-04", 90, "opportunity"),
        _cand("2026-12", 60, "pressure"),
    ]
    a = assign_entry_slots(cands, mode="trigger", done_min=95)
    assert a is not None and a.done_periods == []
    assert a.likely_periods == ["2027-02", "2027-05"] and a.strongest_likely == "2027-02"
    assert a.possible_periods == ["2027-03", "2027-04"]
    d = entry_slot_directive(a, event_ko="취업·합격", earliest_asked=True)
    assert "유력한 달('취업·합격' 사건 신호가 매우 강한 달" in d
    assert "2027-02(조건 불리(처우·강도 주의) · 신호 가장 강함)·2027-05(순조)" in d
    assert "약하지만 가능성 있는 달(신호는 있으나 유력한 달보다 약함): 2027-03·2027-04." in d
    assert "그 밖에 흐름이 보이는 달(탐색·준비 단계): 2026-12." in d
    assert "유력한 달을 찾아보니" in d and NO_ABSENCE_CLAUSE in d
    assert "제안·접수·면접과 조건 확인이 본격적으로 오가는 달" in d
    assert "가장 이른 유력한 달은 2027-02" in d and "조건까지 순조한 가장 이른 달은 2027-05" in d
    # 종전 문구가 남아 있으면 안 된다.
    for old in ("성사 가능 달 없음", "사건 신호가 성사 기준에 못 미친다", "없다'고 먼저 말"):
        assert old not in d
    # 결정 행동 병기는 95점 이상 달이 있을 때만.
    assert "입사·계약까지 닿을 수 있는 달" not in d
    # 승계 저장: 성사 가능 달이 없으면 유력한 달 가운데 신호가 가장 강한 달.
    assert a.to_state_slots() == {"done": "2027-02", "move": "2026-12"}


def test_trigger_tiers_follow_score_boundaries() -> None:
    """점수 경계 — 유력한 달 = 93점 이상 전부 / 약하지만 가능성 있는 달 = 86~92 / 55~85 = 흐름만.

    경계값은 데굴님 확정(2026-11-20 "93/86으로 가자" — 처음 지정한 85/70 은 실이력에서 한 해 평균
    8.6달이 유력한 달이 됐다).
    """
    assert (ENTRY_LIKELY_MIN_SCORE, ENTRY_POSSIBLE_MIN_SCORE) == (93, 86)
    cands = [
        _cand("2027-01", 93, "opportunity"),   # 경계 — 유력
        _cand("2027-02", 92, "opportunity"),   # 경계 바로 아래 — 가능성
        _cand("2027-03", 86, "pressure"),      # 경계 — 가능성
        _cand("2027-04", 85, "opportunity"),   # 경계 바로 아래 — 흐름만
        _cand("2027-05", 55, "opportunity"),   # 흐름 하한
        _cand("2027-06", 54, "opportunity"),   # 어느 칸에도 없음
        _cand("2027-07", 99, "opportunity"),   # 성사 가능 달 — 유력한 달에 포함
        _cand("2027", 99, "opportunity"),      # 연 단위 — 월 배정 대상 아님
    ]
    a = assign_entry_slots(cands, mode="trigger", done_min=95)
    assert a is not None
    assert a.likely_periods == ["2027-01", "2027-07"] and a.done_periods == ["2027-07"]
    assert a.possible_periods == ["2027-02", "2027-03"]
    assert a.move_periods == ["2027-01", "2027-02", "2027-03", "2027-04", "2027-05"]
    assert a.scores["2027-06"] == 54 and "2027" not in a.scores
    # 조건 등급은 유력한 달에만 붙는다.
    assert set(a.conditions) == {"2027-01", "2027-07"}
    d = entry_slot_directive(a, event_ko="취업·합격")
    assert "2027-01(순조)·2027-07(순조 · 신호 가장 강함)" in d
    assert "약하지만 가능성 있는 달(신호는 있으나 유력한 달보다 약함): 2027-02·2027-03." in d
    assert "그 밖에 흐름이 보이는 달(탐색·준비 단계): 2027-04·2027-05." in d
    assert "2027-06" not in d
    # 같은 달에 후보가 둘이면 높은 점수로 칸을 정한다.
    b = assign_entry_slots(
        [_cand("2027-03", 88, "pressure"),
         _cand("2027-03", 94, "opportunity", event=EventKey.CAREER_CHANGE)],
        mode="trigger", done_min=95,
    )
    assert b is not None and b.likely_periods == ["2027-03"] and b.possible_periods == []
    assert b.conditions["2027-03"].startswith(COND_SMOOTH)   # 88점 pressure 는 등급에 참여하지 않음


def test_trigger_directive_possible_only_and_faint_only() -> None:
    """유력한 달이 없을 때도 '없다'가 아니라 있는 달을 강도대로 — 유력한 달로 올리지도 않는다."""
    # 실답 2턴 Top-5(오전 라벨 기준 점수 90·88·86·87·60)는 93 미만이라 전부 '가능성 있는 달'이다.
    poss = assign_entry_slots(_LIVE_TOP5, mode="trigger", done_min=95)
    assert poss is not None and poss.likely_periods == [] and poss.strongest_likely is None
    assert poss.possible_periods == ["2027-02", "2027-03", "2027-04", "2027-05"]
    d = entry_slot_directive(poss, event_ko="취업·합격", earliest_asked=True)
    head = ENTRY_SLOT_HEADER + " 약하지만 가능성 있는 달('취업·합격' 신호가 있는 달): "
    assert d.startswith(head)
    assert "2027-02·2027-03·2027-04·2027-05." in d and "가능성 있는 달을 찾아보니" in d
    assert "그 밖에 흐름이 보이는 달(탐색·준비 단계): 2026-12." in d
    assert "'가장 유력한 달·유력한 달'이라고 부르지는 말 것" in d and NO_ABSENCE_CLAUSE in d
    assert "유력한 달(" not in d and "가장 이른 유력한 달" not in d
    # 반례: 입력 줄에 '기준에 못 미친다'가 금지 예시 밖에서 쓰이면 답으로 샌다.
    assert "못 미치는" not in d and d.count("못 미친다") == 1   # 금지 문장 안의 한 번뿐
    assert poss.to_state_slots() == {}          # 유력한 달이 없으면 승계할 달도 없다

    faint = assign_entry_slots(
        [_cand("2026-12", 85, "pressure"), _cand("2027-01", 55, "opportunity")],
        mode="trigger", done_min=95,
    )
    assert faint is not None and faint.likely_periods == [] and faint.possible_periods == []
    d2 = entry_slot_directive(faint, event_ko="취업·합격")
    assert d2.startswith(ENTRY_SLOT_HEADER + " 흐름이 보이는 달(")
    assert "2026-12·2027-01." in d2 and "흐름이 보이는 달을 찾아보니" in d2
    assert "'유력한 달'이라고 부르지는 말 것" in d2 and NO_ABSENCE_CLAUSE in d2
    # 85점 달은 후보 줄 강도가 '신호가 매우 강합니다'다 — 지시문이 '약하게'라고 깎지 않는다.
    assert "약하게" not in d2
    # 55점 미만뿐이면 배정 자체가 없다(약한 후보 예외 지시문 소관).
    assert assign_entry_slots([_cand("2026-12", 54, "pressure")], mode="trigger") is None


def test_non_entry_or_year_candidates_give_none() -> None:
    assert assign_entry_slots([_cand("2027", 99, "opportunity")]) is None
    assert assign_entry_slots(
        [_cand("2027-04", 99, "opportunity", event=EventKey.RELOCATION)]
    ) is None
    assert assign_entry_slots([]) is None
    assert assign_entry_slots([_cand("2027-04", 40, "opportunity")], mode="trigger") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("최대한 빠르게 취업하려면 언제 가능할가", True),
        ("가장 빠른 취업 시기는?", True),
        ("돈이 없어서 빨리 취업해야해", True),
        ("언제 취업할 수 있을까", False),
        ("", False),
    ],
)
def test_is_earliest_question(text: str, expected: bool) -> None:
    assert is_earliest_question(text) is expected


def test_entry_slot_block_uses_candidate_ganji_and_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SAJU_ENTRY_SLOT_MODE", raising=False)
    monkeypatch.delenv("SAJU_ENTRY_DONE_MIN_SCORE", raising=False)
    d, slots = _entry_slot_block(
        _TRIGGER_SET, _intent(None), "최대한 빠르게 취업하려면 언제 가능할가",
    )
    assert d is not None and "2027-02(壬寅 · 조건 불리" in d
    assert "순조한 가장 이른 달은 2027-04(甲辰)" in d
    assert slots == {"done": "2027-02", "move": "2026-12"}
    assert _entry_slot_block(
        [_cand("2027", 90, "opportunity")], _intent(None), "언제",
    ) == (None, {})


# ── C. 승계 — 엔진 배정 우선 저장 + '언제' 열린 후속 주입 ──────────────────────


def test_record_entry_slots_prefers_engine_done_and_answer_move() -> None:
    st = ConversationState(thread_id="t", turn_no=1, last_intent=_intent("2027-04"))
    _record_entry_slots(
        st, "2027년 4월은 성사 가능성이 높습니다.", _TODAY, "t", engine_slots={"done": "2027-04"},
    )
    assert st.entry_slots == {
        "done": "2027-04", "event_key": "job_gain", "turn_no": 1, "source": "engine",
    }
    st2 = ConversationState(thread_id="t2", turn_no=2, last_intent=_intent(None))
    _record_entry_slots(
        st2, "성사 달 2027년 2월·움직이는 달 2026년 12월입니다.", _TODAY, "t2",
        engine_slots={"done": "2027-04", "move": "2027-03"},
    )
    assert st2.entry_slots["done"] == "2027-04" and st2.entry_slots["move"] == "2026-12"
    assert st2.entry_slots["source"] == "engine"
    st3 = ConversationState(thread_id="t3", turn_no=1, last_intent=_intent(None))
    _record_entry_slots(st3, "취업 흐름은 완만합니다.", _TODAY, "t3", engine_slots={})
    assert st3.entry_slots == {}


def test_prior_slots_directive_for_open_when_followup() -> None:
    st = ConversationState(
        thread_id="t", turn_no=2,
        entry_slots={"done": "2027-04", "event_key": "job_gain", "turn_no": 1, "source": "engine"},
    )
    open_when = IntentJson(
        intent_id="i", query_type=QueryType.TIMING_SEARCH, domain=Domain.CAREER,
        event_key=EventKey.JOB_GAIN, time_range=None,
    )
    d = _prior_entry_slots_directive(st, open_when, "2026-10", is_followup=False)
    assert d is not None
    assert "유력한 달 2027년 4월" in d and "'언제' 질문" in d and "뒤집지 말 것" in d
    d2 = _prior_entry_slots_directive(st, _intent("2027-02"), "2026-10", is_followup=False)
    assert d2 is not None and "2027년 2월" in d2 and "'언제' 질문" not in d2
    assert _prior_entry_slots_directive(
        st, _intent(None, event=EventKey.RELOCATION), "2026-10", is_followup=True,
    ) is None
    year_only = IntentJson(
        intent_id="i", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.CAREER,
        event_key=EventKey.JOB_GAIN,
        time_range=TimeRange(type="absolute", start="2027", end="2027", granularity="year"),
    )
    assert _prior_entry_slots_directive(st, year_only, "2026-10", is_followup=True) is None
    assert _prior_entry_slots_directive(st, open_when, "2027-05", is_followup=True) is None


# ── D. 감사·권유 처리 ─────────────────────────────────────────────────────────────


def test_entry_candidate_coverage_audit() -> None:
    answer = (
        "가장 빠르게 취업의 결실을 맺을 수 있는 시기는 2027년 2월이며 … 2027년 5월 乙巳월에도 "
        "강한 신호가 있습니다. 12월은 준비 달입니다."
    )
    assert audit_entry_candidate_coverage(answer, ["2027-04", "2027-05"]) == ["2027-04"]
    assert month_mentioned("12월은 준비 달입니다.", "2027-02") is False
    assert month_mentioned("4월에 결과를 매듭짓는", "2027-04") is True
    assert audit_entry_candidate_coverage("", ["2027-04"]) == ["2027-04"]


def test_asked_event_score_in_period() -> None:
    assert asked_event_score_in_period(_LIVE_TOP5, "2027-04", EventKey.JOB_GAIN) == 87
    assert asked_event_score_in_period(_LIVE_TOP5, "2027-04", "job_gain") == 87
    assert asked_event_score_in_period(_LIVE_TOP5, "2027-01", EventKey.JOB_GAIN) is None
    assert asked_event_score_in_period(_LIVE_TOP5, "2027-04", EventKey.RELOCATION) is None
    assert asked_event_score_in_period(_LIVE_TOP5, "2027-04", None) is None
    assert ASKED_EVENT_STRONG_MIN == 70


def test_counseling_block_review_periods_line() -> None:
    sem = ca.CounselingSemantics(
        event_key="job_gain", event_ko="취업·합격", period="2027-02",
        activation_band="high", outcome_outlook="adverse",
        summary_stance="PROCEED_WITH_CONDITIONS",
    )
    both = "\n".join(ca.counseling_block_lines(
        sem, allowed_periods=("2027-05", "2027-04"), review_periods=("2027-02", "2027-03"),
    ))
    assert "결정 행동(수락·계약·실행) 허용 시기: 2027-05, 2027-04" in both
    assert "준비·검토 시기(결정 권고 금지): 2027-02, 2027-03" in both
    assert "사건 신호가 있는 달" in both and "국면·압박 후보 달" not in both
    # 2026-11-20: '성사 기준 미달' 문구가 답으로 새지 않게 줄 자체에서 뺐다.
    assert "성사 기준에 못 미치는 달" not in both
    assert "'기준에 못 미친다'는 말은 답에 쓰지 말 것" in both
    assert both.index("허용 시기") < both.index("준비·검토 시기") < both.index("[상담 서술 계약]")
    only_review = "\n".join(ca.counseling_block_lines(sem, review_periods=("2027-02",)))
    assert "결정 행동(수락·계약·실행) 권고는 이 창의 어느 달에도 붙이지 말 것" in only_review
    assert "'성사되는 달이 없다·기회가 없다'는 뜻으로 답에 옮기지 말 것" in only_review
    assert "허용 시기: 없음" not in only_review and "성사 기준에 못 미쳐" not in only_review
    assert "준비·검토 시기(결정 권고 금지): 2027-02" in only_review
    plain = "\n".join(ca.counseling_block_lines(sem))
    assert "허용 시기" not in plain and "준비·검토 시기" not in plain


# ── E. 실답 명식 회귀(dry-run, 기본 모드 trigger·95) ──────────────────────────────

_FIXTURE = Path(__file__).parent / "fixtures" / "entry_slots_birth_19801122.json"


@pytest.mark.skipif(not _FIXTURE.exists(), reason="실답 명식 픽스처 없음")
def test_live_case_prompts_under_default_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SAJU_ENTRY_SLOT_MODE", raising=False)
    monkeypatch.delenv("SAJU_ENTRY_DONE_MIN_SCORE", raising=False)
    birth = BirthInput.model_validate(json.loads(_FIXTURE.read_text(encoding="utf-8")))
    r1 = chat_service.chat(birth, "다른 사주에서는 내년 4월에 취업할 수 있을거래. ", _TODAY, True)
    pp1 = r1.prompt_preview or ""
    assert r1.postprocess is not None
    # 1턴(2027-04 한 달 창): 90점 — 86~92 구간이라 '약하지만 가능성 있는 달'이다
    # (2026-11-20: 종전에는 '성사 가능 달 없음 + 움직이는 달 2027-04'로 나갔다).
    assert "약하지만 가능성 있는 달('취업·합격' 신호가 있는 달): 2027-04(甲辰)." in pp1
    assert "가능성 있는 달을 찾아보니" in pp1
    assert "성사 가능 달 없음" not in pp1 and "움직이는 달 후보: 2027-04" not in pp1
    assert r1.postprocess.entry_slots_engine == {}
    # 권유 처리 A: 질문 사건이 그 달의 강한 후보면 '동반 신호로만' 격하 대신 함께 서술.
    # 최상위 사건명은 점수 규칙에 따라 바뀐다(2026-11-07 결혼 실험 ON 뒤 이 달은 '결혼 신호') —
    # 검증 대상은 '질문 사건을 동반 신호로 격하하지 않고 함께 서술'하는 처리다.
    assert re.search(r"최상위 신호는 '[^']+'이고 질문하신 '취업·합격'도 강한 후보", pp1)
    assert "질문하신 '취업·합격'은(는) 동반 신호로만 서술할 것" not in pp1
    # direction 모드로 같은 후보를 나누면 2027-04 가 성사 방향 후보 — 두 모드의 차이가 바로 이 달.
    d1 = assign_entry_slots(list(r1.postprocess.payload.event_candidates), mode="direction")
    assert d1 is not None and d1.done_periods == ["2027-04"]

    r2 = chat_service.chat(birth, "최대한 빠르게 취업하려면 언제 가능할가", _TODAY, True)
    pp2 = r2.prompt_preview or ""
    assert r2.postprocess is not None
    assert "유력한 달('취업·합격' 사건 신호가 매우 강한 달" in pp2
    # 2026-10-25 연애운 대조 P0-1(삼합완성·반합성립 변환 복구)을 전 궁위에 열면 2027-03 癸卯가
    # 亥卯 반합(월지·일지 亥) 월·일주 HAP 가산으로 job_gain 92→96 이 되어 성사 가능 달에 편입되고
    # 실이력 trigger95 정밀도가 6.4%→5.6% 로 내려갔다(`var/entry_slot_modes_20261025_love.md`).
    # 2차 조정(`hap_grade_scope`: half·full 은 일지 × 관계 사건만)으로 직업 사건은 종전과 같다.
    # 점수 98·93 = 유력한 달, 92·90 = 약하지만 가능성 있는 달, 56 = 그 밖에 흐름이 보이는 달.
    assert (
        "2027-02(壬寅 · 조건 불리(처우·강도 주의) · 신호 가장 강함)·2027-05(乙巳 · 순조)" in pp2
    )
    assert (
        "약하지만 가능성 있는 달(신호는 있으나 유력한 달보다 약함): "
        "2027-03(癸卯)·2027-04(甲辰)." in pp2
    )
    assert "그 밖에 흐름이 보이는 달(탐색·준비 단계): 2026-12(庚子)." in pp2
    assert "조건까지 순조한 가장 이른 달은 2027-05(乙巳)" in pp2
    assert "유력한 달 가운데 2027-02(壬寅)은(는) 신호가 가장 강한 구간" in pp2
    assert "가장 이른 유력한 달은 2027-02(壬寅)(조건 불리" in pp2
    # 배정 입력 = 질문 창 전체의 진입 월 후보(상위 5개 밖의 달도 담긴다).
    _window = {c.period for c in r2.postprocess.payload.entry_window_candidates}
    assert {c.period for c in r2.postprocess.payload.event_candidates} <= _window
    assert {"2026-11", "2027-06"} <= _window
    assert r2.postprocess.entry_slots_engine == {"done": "2027-02", "move": "2026-12"}
    # 권유 처리 B: 결정 행동 허용 시기는 성사 가능 달만, 나머지 월 후보는 준비·검토 시기.
    allowed, review = _decision_periods(r2.postprocess.payload)
    assert allowed == ("2027-02",)
    assert set(review) == {"2027-05", "2027-03", "2027-04", "2026-12"}
    if ca.COUNSELING_SEMANTICS_ENABLED:
        assert "결정 행동(수락·계약·실행) 허용 시기: 2027-02" in pp2
        assert "준비·검토 시기(결정 권고 금지): 2027-05, 2027-03, 2027-04, 2026-12" in pp2
    d2 = assign_entry_slots(list(r2.postprocess.payload.event_candidates), mode="direction")
    assert d2 is not None and d2.done_periods == ["2027-04", "2027-05"]


def test_slot_assignment_reads_whole_window_not_top_n(monkeypatch: pytest.MonkeyPatch) -> None:
    """실답 web-mwobgi4o(2026-11-20): 98점 달이 상위 5개 선별에서 빠져 '성사 가능 달 없음'이 나갔다.

    배정·결정 행동 허용 시기는 `entry_window_candidates`(창 전체)를 본다 — 실린 후보에서 유력한 달을
    지워도 결과가 같아야 한다. 창 전체 목록이 비어 있을 때만 실린 후보로 돌아간다.
    """
    from saju_api.services.chat_service import _entry_slot_candidates

    monkeypatch.delenv("SAJU_ENTRY_SLOT_MODE", raising=False)
    monkeypatch.delenv("SAJU_ENTRY_DONE_MIN_SCORE", raising=False)
    birth = BirthInput.model_validate(json.loads(_FIXTURE.read_text(encoding="utf-8")))
    r = chat_service.chat(birth, "최대한 빠르게 취업하려면 언제 가능할가", _TODAY, True)
    assert r.postprocess is not None
    payload = r.postprocess.payload
    trimmed = payload.model_copy(update={
        "event_candidates": [c for c in payload.event_candidates if c.period == "2026-12"],
    })
    assert [c.period for c in trimmed.event_candidates] == ["2026-12"]
    a = assign_entry_slots(_entry_slot_candidates(trimmed))
    assert a is not None and a.done_periods == ["2027-02"]
    assert a.likely_periods == ["2027-02", "2027-05"]
    assert a.possible_periods == ["2027-03", "2027-04"]
    # 종전 방식(실린 후보만)이면 유력한 달이 사라진다 — 이 차이가 결함이었다.
    old = assign_entry_slots(list(trimmed.event_candidates))
    assert old is not None and old.likely_periods == [] and old.done_periods == []
    # 결정 행동 허용 시기도 창 전체 기준: 실린 2026-12 는 검토 시기, 허용 달은 실린 후보 안에서만.
    assert _decision_periods(trimmed) == ((), ("2026-12",))
    # 창 전체 목록이 없으면(진입 사건 질문이 아닌 payload) 실린 후보로 돌아간다.
    empty = payload.model_copy(update={"entry_window_candidates": []})
    assert [c.period for c in _entry_slot_candidates(empty)] == [
        c.period for c in payload.event_candidates
    ]
