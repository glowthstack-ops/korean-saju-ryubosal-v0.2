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
