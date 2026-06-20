"""결혼·이혼 결정 디렉티브 게이트 — 운 저점 보류(E2)·이혼 사유 severity(T1).

궁합 자료: 운 저점엔 큰 결정 보류(조급함이 신호), 이혼 사유는 외도·폭력(회복 난) vs 성격·건강
(극복 가능)으로 결을 나눈다. 디렉티브는 결정 어미/이혼 키워드가 있을 때만 주입한다.
"""

from __future__ import annotations

from datetime import date

from saju_api.services.chat_service import _is_big_decision, _is_divorce_question
from saju_engines.query_parser import parse_message


def _intent(q: str):
    return parse_message(q, date(2026, 6, 20)).intents[0]


def test_big_decision_detected() -> None:
    for q in ("지금 결혼해도 될까?", "이혼하는 게 좋을까요?", "재혼해야 할까"):
        assert _is_big_decision(_intent(q), q), q


def test_big_decision_not_for_plain_relationship_question() -> None:
    # 결정 어미 없는 일반 관계 질문은 보류 디렉티브 대상이 아니다.
    q = "올해 연애운 어때?"
    assert not _is_big_decision(_intent(q), q)


def test_divorce_question_detected() -> None:
    assert _is_divorce_question("이혼 고민 중이에요")
    assert _is_divorce_question("별거 중인데 어떨까요")
    assert not _is_divorce_question("결혼운 좋아질까")
