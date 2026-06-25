"""'그래 봐줘' 류 동의+이어보기 후속 → 직전 의도 승계 (실로그 회귀).

버그: 직전 '이직 언제?'(career/timing_search) 뒤 '그래 봐줘'가 새 풀이 요청(general/
fortune_overview)으로 끊겨 일반 10년 인생 흐름으로 빠짐. 동의+이어보기는 직전 의도를 잇는다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.conversation import ConversationEngine
from saju_shared_types.conversation import ConversationState
from saju_shared_types.intent import Domain, QueryType

_T = date(2026, 6, 25)
_Q1 = "이직... 진짜 하고 싶어. 정말 언제쯤 할 수 있을까? 빠른시일내에 누가 제안해왔으면 좋겠어"


def _turn2(q2: str):
    eng = ConversationEngine()
    st = ConversationState(thread_id="t")
    _, st, _, _ = eng.process_turn(st, _Q1, _T, birth_year=1980)
    parsed, st, _, link = eng.process_turn(st, q2, _T, birth_year=1980)
    return parsed.intents[0], link


@pytest.mark.parametrize(
    "q2", ["그래 봐줘", "응 보여줘", "좋아 계속", "그래", "그래줘", "ㅇㅇ 봐줘"]
)
def test_affirm_continue_inherits_prior_intent(q2: str) -> None:
    i2, link = _turn2(q2)
    assert link.is_follow_up
    assert i2.domain is Domain.CAREER  # 일반(general)으로 리셋되지 않음
    assert i2.query_type is QueryType.TIMING_SEARCH  # '이직 언제'를 이어감
    assert "career_change" in str(i2.event_key).lower()


def test_new_domain_followup_switches_domain() -> None:
    # 새 도메인을 들고 온 후속은 그 도메인으로 전환(이직에 고정되지 않음).
    i2, link = _turn2("연애운 봐줘")
    assert link.is_follow_up and i2.domain is Domain.RELATIONSHIP


def test_fresh_reading_request_stays_new() -> None:
    # '총운/사주 봐줘'류 새 풀이 요청은 NEW(직전 의도 미승계).
    i2, link = _turn2("총운 봐줘")
    assert not link.is_follow_up
    assert i2.query_type is QueryType.FORTUNE_OVERVIEW
