"""이직 유입 경로 어휘 회귀 — 2026-07-30 실사용 미탐지.

    '어제 들어온 헤드헌터 제안은 받는게 맞을까?'
    → domain general · time None → rewriter.assess = too_broad
    → '질문 범위가 넓어요. 이렇게 좁혀볼까요? — 향후 3개월 전체 흐름 / …'

`이직` 이라는 낱말의 유무가 갈랐다. 같은 질문에서 '헤드헌터'를 '이직'으로만 바꾸면
career 로 정상 라우팅됐다. 어휘 누락이 곧 안내 문구 오출력으로 이어지므로, 파서
단계와 판정 단계를 **둘 다** 고정한다.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from saju_engines.query_parser import parse_message  # noqa: E402
from saju_engines.rewriter import assess  # noqa: E402
from saju_shared_types.intent import Domain  # noqa: E402

_TODAY = dt.date(2026, 7, 30)

#: 실사용에서 미탐지로 확인된 문장 + 같은 누락으로 묶여 있던 것들.
INFLOW_QUESTIONS = [
    "어제 들어온 헤드헌터 제안은 받는게 맞을까?",
    "헤드헌터 제안 받는게 맞을까?",
    "헤드헌팅 연락이 왔는데 어떨까?",
    "스카우트 제안 받아도 될까?",
    "전직하는게 나을까?",
    "경력직 지원 해볼까?",
    "이력서 넣어볼까?",
    "면접 잘 볼 수 있을까?",
    "연봉 협상 잘 될까?",
    "커리어 전환 시기 언제가 좋아?",
]


@pytest.mark.parametrize("question", INFLOW_QUESTIONS)
def test_career_inflow_questions_route_to_career_domain(question: str) -> None:
    """유입 경로 질문이 general 로 남으면 안 된다."""
    parsed = parse_message(question, _TODAY)
    assert parsed.intents, f"의도 파싱 실패: {question}"
    assert parsed.intents[0].domain is Domain.CAREER


@pytest.mark.parametrize("question", INFLOW_QUESTIONS)
def test_career_inflow_questions_are_not_too_broad(question: str) -> None:
    """도메인이 잡히면 범위 좁힘 안내가 아니라 기본 기간 적용으로 가야 한다."""
    parsed = parse_message(question, _TODAY)
    result = assess(parsed.intents[0], question)
    assert result.status != "too_broad"
    assert not result.rewrite_suggestions


def test_the_reported_regression_no_longer_shows_the_narrowing_prompt() -> None:
    """보고된 문장 그대로 — 하드코딩 제안 3종이 다시 나오지 않는지 고정한다."""
    question = "어제 들어온 헤드헌터 제안은 받는게 맞을까?"
    parsed = parse_message(question, _TODAY)
    result = assess(parsed.intents[0], question)
    labels = [s.label for s in result.rewrite_suggestions]
    assert "향후 3개월 전체 흐름" not in labels
    assert "올해 직업운" not in labels
    assert "향후 6개월 연애운" not in labels


def test_headhunter_and_job_change_wording_agree() -> None:
    """'헤드헌터 제안'과 '이직 제안'이 같은 도메인으로 가야 한다 — 낱말 차이로
    갈리던 것이 이 결함의 본질이었다."""
    a = parse_message("어제 들어온 헤드헌터 제안은 받는게 맞을까?", _TODAY)
    b = parse_message("어제 들어온 이직 제안은 받는게 맞을까?", _TODAY)
    assert a.intents[0].domain is b.intents[0].domain is Domain.CAREER


@pytest.mark.parametrize(
    "question",
    [
        "오퍼 받았는데 수락해도 될까?",   # 부동산·투자 맥락과 모호 — 넣지 않았다
        "부서 이동 어때?",                # '이동'이 이사 어휘와 겹칠 수 있어 별건
        "팀 옮기는게 좋을까?",
    ],
)
def test_deliberately_excluded_wording_stays_out_of_scope(question: str) -> None:
    """의도적으로 제외한 어휘 — 조용히 들어오면 이 테스트가 알려준다.

    실패하면 어휘가 추가된 것이므로, 모호성 검토를 거쳤는지 확인해야 한다.
    """
    parsed = parse_message(question, _TODAY)
    assert parsed.intents[0].domain is not Domain.CAREER
