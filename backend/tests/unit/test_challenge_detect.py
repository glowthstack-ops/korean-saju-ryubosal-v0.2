"""이의(challenge) 발화 감지 — 파서 Q12·대화 링크 공용 규칙 회귀(2026-10-01).

실로그 web-mup4m82l: "니가 연두색이나 초록색계열 커튼을 추천해줬잖아"가 리터럴 `했잖아`에 걸리지
않아 되물음 답(offer-slot)으로 링크된 결함. 2인칭+인용 표지 / 시점 참조+발화 동사로 일반화하고,
사용자 자신의 발화·사실("내가 아까 말한", "3년 전에 이사했잖아")은 제외한다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.challenge_detect import is_challenge
from saju_engines.query_parser import parse_message
from saju_shared_types.intent import QueryType


@pytest.mark.parametrize(
    "text",
    [
        "니가 연두색이나 초록색계열 커튼을 추천해줬잖아",
        "네가 9월이 좋다고 했잖아",
        "너 그랬잖아",
        "아까는 북쪽이 좋다고 말했잖아",
        "앞서 초록을 추천했는데 왜 달라?",
        "방금 알려준 거랑 다른데",
        "아들은 편인격 아니야?",
        "아닌데 11월인데 틀렸어",
        "5월에는 계약하지 말라던데 맞아?",
        "내 배우자운이 인목이라고 했잖아?",
        "너 내 사주랑 아들사주를 헷갈려서 내 사주로 풀이했는데 다시 체크해봐",
    ],
)
def test_challenge_detected(text: str) -> None:
    assert is_challenge(text)


@pytest.mark.parametrize(
    "text",
    [
        "3년 전에 이사했잖아",  # 사용자 자신의 과거 사실
        "내가 작년에 이직했잖아",
        "내가 아까 말한 아들 사주로 봐줘",  # 1인칭 발화 참조
        "전에 다니던 회사로 돌아갈까?",
        "처음에 뭘 준비해야 해?",
        "커텐으로 할건데 붉은색은 좀 그래. 다른색을 추천해줘.",
        "지금 인성과다라서 공부할때 잡생각이 많은데 녹색을 추가해도 돼?",
        "그래 봐줘",
        "2027년 결혼운 어때?",
    ],
)
def test_not_challenge(text: str) -> None:
    assert not is_challenge(text)


def test_parser_routes_generalized_challenge_to_q12() -> None:
    """'추천해줬잖아'(리터럴 `했잖아` 아님)도 Q12 FEEDBACK_CORRECTION 으로 잡힌다."""
    parsed = parse_message("니가 연두색이나 초록색계열 커튼을 추천해줬잖아", date(2026, 10, 1))
    assert parsed.intents[0].query_type is QueryType.FEEDBACK_CORRECTION
