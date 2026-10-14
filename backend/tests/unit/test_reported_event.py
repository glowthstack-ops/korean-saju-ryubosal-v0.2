"""사건 보고형 질문·직장 이탈 계열 — 2026-10-13 실로그 회귀 고정(데굴님 지시).

실로그: "오늘 해고통보를 받았어. 앞으로 어떻게 하면 좋을까"가 '오늘 하루 총운'으로 분류돼
"오늘은 업무적인 면에서 유리한 신호가 우세"로 시작했고, '오늘'을 빼면 too_broad 로 반려됐다.
해고·퇴사 통보·권고사직은 한 계열(직장을 떠나게 된 사건)이다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.horizon import resolve_horizon
from saju_engines.job_separation import is_job_separation
from saju_engines.query_parser import detect_reported_event, parse_message
from saju_engines.user_facts import extract_user_facts, user_facts_block
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventKey
from saju_shared_types.intent import Domain, QueryType

_TODAY = date(2026, 10, 13)
_BIRTH = BirthInput(
    birth_date=date(1980, 11, 22), birth_time="09:40:00", birth_place_name="서울",
    gender="male",
)


@pytest.mark.parametrize(
    "text",
    [
        "오늘 해고통보를 받았어. 앞으로 어떻게 하면 좋을까",
        "해고통보를 받았어. 앞으로 어떻게 하면 좋을까",
        "오늘 퇴사 통보를 받았어. 앞으로 어떻게 하면 좋을까",
        "회사에서 오늘 권고사직 당했어 앞으로 어떻게 해야 할까",
        "어제 회사에서 잘렸어. 이제 뭘 해야 할까",
    ],
)
def test_job_separation_family_routes_to_career_forward(text):
    """세 표현(해고·퇴사 통보·권고사직)과 동형 표현이 같은 계열로 — 직업·이직/직업 변화·앞으로."""
    intent = parse_message(text, _TODAY).intents[0]
    assert intent.domain is Domain.CAREER
    assert intent.event_key is EventKey.CAREER_CHANGE
    assert intent.time_range is None  # 보고 날짜는 대상 기간이 아니다
    assert intent.dialogue_act == "reported_event"


@pytest.mark.parametrize(
    ("text", "start", "act"),
    [
        ("오늘 운세 알려줘", "2026-10-13", None),            # 당일 운세는 그대로
        ("오늘 면접 봤는데 붙을까?", "2026-10-13", None),     # 결과 질문 — 대응 질문 아님
        ("이직할까?", None, None),
    ],
)
def test_non_report_questions_unchanged(text, start, act):
    intent = parse_message(text, _TODAY).intents[0]
    assert (intent.time_range.start if intent.time_range else None) == start
    assert intent.dialogue_act == act


def test_reported_event_is_general_beyond_career():
    """사건 보고형 규칙은 직업 외 사건에도 같다('오늘 헤어졌어. 앞으로 어떻게…')."""
    intent = parse_message("오늘 헤어졌어. 앞으로 어떻게 하면 좋을까", _TODAY).intents[0]
    assert intent.dialogue_act == "reported_event" and intent.time_range is None
    assert intent.domain is Domain.RELATIONSHIP


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("머리 잘렸어", False), ("퇴사할까", False), ("이직할까", False),
        ("회사에서 잘렸어", True), ("구조조정 대상이래", True), ("희망퇴직 신청했어", True),
    ],
)
def test_job_separation_vocabulary(text, expected):
    assert is_job_separation(text) is expected


def test_detect_reported_event_requires_forward_ask():
    assert detect_reported_event("오늘 해고통보를 받았어") is False  # 대응 질문 없음
    assert detect_reported_event("오늘 해고통보를 받았어. 앞으로 어떻게 하면 좋을까") is True


def test_horizon_is_structural_for_job_separation():
    """직장 이탈 계열은 퇴사와 같은 구조 결정형 지평(원국+대운+5년+당장 3개월)."""
    q = "해고통보를 받았어. 앞으로 어떻게 하면 좋을까"
    policy = resolve_horizon(q, parse_message(q, _TODAY).intents[0])
    assert policy is not None and policy.kind == "structural"


def test_user_fact_slot_records_job_separation():
    facts = extract_user_facts("오늘 해고통보를 받았어. 앞으로 어떻게 하면 좋을까", turn=1)
    sep = [f for f in facts if f.key == "job_separation"]
    assert sep and "해고통보" in sep[0].quote
    block = user_facts_block(facts) or ""
    assert "직장 이탈(사용자 진술)" in block and "재직 중이라는 전제로 답하지 말 것" in block


def test_chat_prompt_uses_reported_event_contract():
    """dry-run 프롬프트 — 특정일·총운 지시 없이 사건 보고형 지시·구조 결정형 지평.

    과거형 어미가 있어도 회고 모드로 뒤집지 않는다.
    """
    from saju_api.services import chat_service

    resp = chat_service.chat(
        _BIRTH, "오늘 해고통보를 받았어. 앞으로 어떻게 하면 좋을까", _TODAY, True,
    )
    assert resp.status == "dry_run"
    p = resp.prompt_preview or ""
    assert "[사건 보고형 — 사용자가 이미 겪은 일을 알리고 앞으로를 묻는다]" in p
    assert "특정일 질문" not in p
    assert "[해당 일 운세" not in p
    assert "회고 모드" not in p
    assert "원국 적합성 + 현재 대운 + 향후 5년" in p
    q = resp.intents[0]
    assert q.query_type is not QueryType.FORTUNE_OVERVIEW and q.domain is Domain.CAREER


# ── 2026-10-14 검수 반례 — 어제 테스트가 설계 경로만 고정해 놓친 것들 ──────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "해고 당할까? 앞으로 어떻게 해야 하지",              # 미발생 걱정
        "구조조정 소문이 돌아. 앞으로 어떻게 하면 좋을까",     # 소문
        "해고 안 당하려면 어떻게 해야 할까",                  # 예방 질문
        "남편이 오늘 해고됐어. 앞으로 어떻게 하면 좋을까",    # 제3자
        "직원을 해고하려는데 앞으로 어떻게 하면 좋을까",       # 고용주
    ],
)
def test_job_separation_fact_requires_own_completed_report(text):
    """가정·제3자·고용주 발화는 본인 실직 사실로 기록하지 않는다(절대원칙 7)."""
    assert [f for f in extract_user_facts(text, turn=1) if f.key == "job_separation"] == []


def test_reported_event_keeps_explicit_forward_time():
    """보고 문장의 '오늘'만 빼고, 질문이 명시한 앞으로의 시점(11월·내년 상반기)은 남긴다."""
    it = parse_message(
        "오늘 해고통보 받았어. 11월에 어떻게 하면 좋을까", _TODAY, current_month_label="2026-10",
    ).intents[0]
    assert it.dialogue_act == "reported_event"
    assert it.time_range is not None and (it.time_range.start, it.time_range.end) == (
        "2026-11", "2026-11",
    )
    it2 = parse_message(
        "어제 회사에서 잘렸어. 내년 상반기에 어떻게 하면 좋을까", _TODAY,
        current_month_label="2026-10",
    ).intents[0]
    assert it2.dialogue_act == "reported_event"
    assert it2.time_range is not None and it2.time_range.start == "2027-01"


def test_reported_event_leaves_other_question_piece_alone():
    """보고 문장이 없는 다른 질문 조각('12월 이사운')은 시점·행위를 그대로 둔다."""
    pm = parse_message(
        "오늘 해고통보 받았어. 앞으로 어떻게 하면 좋을까? 그리고 12월 이사운은 어때?", _TODAY,
        current_month_label="2026-10",
    )
    first, second = pm.intents
    assert first.dialogue_act == "reported_event" and first.time_range is None
    assert second.dialogue_act is None and second.domain is Domain.RELOCATION
    assert second.time_range is not None and second.time_range.start == "2026-12"


@pytest.mark.parametrize(
    "text",
    [
        "오늘 면접 잘 됐으면 좋겠는데 앞으로 어떻게 해야 할까",   # 소원형
        "오늘 운세 어떻게 되었어? 앞으로 어떻게 해야할까",       # 결과 질문
    ],
)
def test_wish_and_outcome_questions_are_not_reports(text):
    assert detect_reported_event(text) is False


def test_horizon_not_structural_for_unrealized_worry():
    """사건이 일어나지 않은 걱정 질문은 5년 구조 결정형 지평을 받지 않는다."""
    q = "해고 당할까? 앞으로 어떻게 해야 하지"
    policy = resolve_horizon(q, parse_message(q, _TODAY).intents[0])
    assert policy is None or policy.kind != "structural"


def test_reported_turn_does_not_inherit_previous_window():
    """멀티턴: 직전 과거 창(9월 회고)을 보고형 턴이 이어받아 회고 모드로 뒤집히지 않는다."""
    from saju_engines.conversation import ConversationEngine
    from saju_shared_types.conversation import ConversationState
    from saju_shared_types.intent import Granularity, IntentJson, TimeRange

    last = IntentJson(
        intent_id="t1", query_type=QueryType.EVENT_EXPLANATION, domain=Domain.CAREER,
        time_range=TimeRange(
            type="absolute", granularity=Granularity.MONTH, start="2026-09", end="2026-09",
        ),
    )
    state = ConversationState(
        thread_id="x", turn_no=1, active_topic=Domain.CAREER, last_intent=last,
    )
    parsed, _s, _r, _l = ConversationEngine().process_turn(
        state, "오늘 해고통보 받았어. 앞으로 어떻게 하면 좋을까", _TODAY,
    )
    it = parsed.intents[0]
    assert it.dialogue_act == "reported_event" and it.time_range is None


def test_job_separation_tail_only_for_job_reports():
    """'재직 전제 금지' 꼬리는 직장 이탈 보고에만 — 승진 보고에는 붙지 않는다."""
    from saju_api.services import chat_service

    tail = "재직 중이라는 전제로 쓰지 말 것"
    for q, expected in [
        ("오늘 승진했어! 앞으로 어떻게 하면 좋을까", False),
        ("오늘 해고통보를 받았어. 앞으로 어떻게 하면 좋을까", True),
    ]:
        resp = chat_service.chat(_BIRTH, q, _TODAY, True)
        p = resp.prompt_preview or ""
        assert "[사건 보고형 — 사용자가 이미 겪은 일을 알리고 앞으로를 묻는다]" in p
        assert (tail in p) is expected, q


def test_kin_subject_in_report_follows_companion_registration():
    """'남편이 오늘 해고됐어' — 남편이 등록 동반자면 그 명식, 미등록이면 기존 정책대로 본인 명식.

    확인 질문을 추가하지 않는다(2026-10-14 데굴님: 뎁스 증가 대신 동반자 등록 여부로 동작).
    """
    from saju_engines.conversation import ConversationEngine
    from saju_shared_types.conversation import ConversationState
    from saju_shared_types.intent import SubjectKind

    q = "남편이 오늘 해고됐어. 앞으로 어떻게 하면 좋을까"
    _p, _s, res, _l = ConversationEngine(aliases={"남편": "c-husband"}).process_turn(
        ConversationState(thread_id="x", turn_no=0), q, _TODAY,
    )
    assert [(s.kind, s.companion_id) for s in res.subjects] == [
        (SubjectKind.COMPANION, "c-husband")
    ]
    _p, _s, res2, _l = ConversationEngine().process_turn(
        ConversationState(thread_id="y", turn_no=0), q, _TODAY,
    )
    assert [s.kind for s in res2.subjects] == [SubjectKind.SELF] and res2.unresolved == []
