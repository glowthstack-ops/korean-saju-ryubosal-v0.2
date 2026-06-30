"""미래지향 open_when '언제 들어올까' 시점 클램프 (2026-06-30 수정).

open_when을 일괄 과거 회고로 보던 결함으로, '이직 제안 언제 들어올까?'가 과거 10년 창으로
앵커링돼 이미 지난 달(2~4월)이 메인 답변에 오르던 시점 오류를 차단. _FUTURE_WHEN_RE가
미래지향 '언제 ~ㄹ까'를 잡아 과거 회고에서 제외한다.
"""

from __future__ import annotations

from saju_api.services.chat_service import _FUTURE_WHEN_RE


def test_future_when_phrases_match() -> None:
    for q in (
        "이직 제안은 언제쯤 들어올까?",
        "연애 언제 시작될까?",
        "승진 언제 될까요?",
        "앞으로 기회가 올까?",
        "새 인연 언제 만날까?",
        "계약이 언제 풀릴까?",
    ):
        assert _FUTURE_WHEN_RE.search(q), q


def test_past_recall_phrases_do_not_match() -> None:
    for q in (
        "오래 쉬었던 기간 언제였을까?",
        "작년에 무슨 일 있었어?",
        "그때 언제였지?",
        "예전에 어땠어?",
        "년단위였어",
        "언제 그만뒀을까?",
    ):
        assert not _FUTURE_WHEN_RE.search(q), q
