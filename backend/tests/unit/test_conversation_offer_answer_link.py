"""되물음 답변·서비스 설명 발화의 스레드 연결 회귀 (2026-07-22 실로그).

버그 체인: ① '사이드프로젝트'의 '사이'가 관계 도메인으로 오검출돼 스레드 도메인이
연애로 오염 → too_broad 제안이 '연애운'으로 빠짐. ② 후속 발화 '사주 풀이를 해주는
웹 서비스인데…'(자기 서비스 설명)가 _READING_REQUEST_RE('사주 풀')에 걸려 새 풀이
요청으로 오인 → 토픽 연속이 차단돼 NEW → too_broad 단절. ③ 직전 답변이 되물음
('…궁금해요')으로 끝나도 12자 초과 서술형 답변을 받을 링킹 규칙이 없었음.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.conversation import _READING_REQUEST_RE, ConversationEngine
from saju_engines.query_parser import _detect_domains
from saju_shared_types.conversation import ConversationState
from saju_shared_types.intent import Domain

_T = date(2026, 7, 22)
_Q1 = (
    "지금 개인적으로 개발중인 사이드프로젝트로는 사업이 가능할까? "
    "아니면 부업수준에서 정리해야할까?"
)
_Q2 = "사주 풀이를 해주는 웹 서비스인데, 이미 개발은 끝났어."


# ── ① '사이' 경계 가드 ─────────────────────────────────────────

def test_side_project_not_relationship() -> None:
    # '사이드프로젝트'의 '사이'가 관계 도메인으로 오검출되지 않는다.
    doms = _detect_domains(_Q1)
    assert Domain.RELATIONSHIP not in doms
    assert doms[0] is Domain.CAREER  # '사업' → 직업 도메인이 primary


@pytest.mark.parametrize(
    "text", ["사이트 만들었어", "옷 사이즈가 애매해", "사이클 타러 갈까", "사이버 보안 일이야"]
)
def test_sai_loanwords_not_relationship(text: str) -> None:
    assert Domain.RELATIONSHIP not in _detect_domains(text)


@pytest.mark.parametrize(
    "text",
    [
        "그 사람과 나는 어떤 사이일까?",
        "우리 사이 괜찮을까",
        "동료랑 사이가 좋아질까?",
        "엄마랑 사이는 어때",
        "둘이 사이좋게 지낼 수 있을까",
    ],
)
def test_sai_relation_word_still_detected(text: str) -> None:
    # 2026-07-01 '관계/사이' 추가 계기 케이스 보존 — 진짜 관계어 '사이'는 계속 감지된다.
    assert Domain.RELATIONSHIP in _detect_domains(text)


# ── ② 새 풀이 요청 정규식 — 요청형만 ──────────────────────────

@pytest.mark.parametrize(
    "text",
    [
        "사주 봐줘",
        "사주풀이 해줘",
        "사주 풀이 부탁해요",
        "사주 풀어줘",
        "내 사주를 풀어 봐",
    ],
)
def test_reading_request_forms_match(text: str) -> None:
    assert _READING_REQUEST_RE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "사주 풀이를 해주는 웹 서비스인데, 이미 개발은 끝났어.",
        "사주 풀이 서비스를 만들고 있어",
    ],
)
def test_reading_description_not_request(text: str) -> None:
    # 자기 서비스 '설명'은 새 풀이 요청이 아니다(관형형 '해주는'·명사구).
    assert not _READING_REQUEST_RE.search(text)


# ── ③ 스레드 연결 — 실로그 시나리오 재현 ──────────────────────

def test_service_description_links_to_prior_thread() -> None:
    # 사업/부업 질문 뒤 서비스 설명 답변이 NEW로 끊기지 않고 직전 스레드를 잇는다.
    eng = ConversationEngine()
    st = ConversationState(thread_id="t")
    _, st, _, _ = eng.process_turn(st, _Q1, _T, birth_year=1980)
    assert st.last_intent is not None and st.last_intent.domain is Domain.CAREER
    _, st, _, link = eng.process_turn(st, _Q2, _T, birth_year=1980)
    assert link.is_follow_up
    assert link.inherited_domain is Domain.CAREER


def test_offer_answer_links_without_length_cap() -> None:
    # 직전 답변이 되물음(offer)으로 끝났으면 12자 초과 서술형 답변도 후속으로 잇는다.
    eng = ConversationEngine()
    st = ConversationState(thread_id="t")
    _, st, _, _ = eng.process_turn(st, _Q1, _T, birth_year=1980)
    st.last_offer = "지금 구상 중인 것이 제품형인지 서비스형인지 궁금해요."
    link = eng.link_question(st, "구독 결제를 붙인 B2C 형태로 생각하고 있고 지인 반응은 좋았어")
    assert link.is_follow_up


def test_offer_answer_new_domain_still_switches() -> None:
    # offer가 있어도 새 도메인을 들고 온 완결 질문은 offer-answer로 흡수하지 않는다
    # (명시 새 도메인 최우선 — NEW로 떨어져 새 스레드 문맥을 연다).
    eng = ConversationEngine()
    st = ConversationState(thread_id="t")
    _, st, _, _ = eng.process_turn(st, _Q1, _T, birth_year=1980)
    st.last_offer = "지금 구상 중인 것이 제품형인지 서비스형인지 궁금해요."
    q = "요즘 몸이 계속 나빠지는데 건강 문제부터 봐야 할 것 같아"
    assert Domain.HEALTH in _detect_domains(q)
    link = eng.link_question(st, q)
    assert not link.is_follow_up
