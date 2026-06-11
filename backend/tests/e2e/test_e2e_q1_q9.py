"""Phase 8 T8.1 — 질문→답변 전체 파이프라인 E2E (Q1~Q9 각 5개, docs/08 실측 어구).

LLM 미호출(dry-run) 기준: 분류가 맞고, 분석 라우트는 4요소 LLM 입력이 한도 내로
직렬화되며, 판정/정책 라우트는 해당 status로 즉시 응답함을 검증한다.
절대 점수는 고정하지 않는다(가중치 튜닝 내성 — docs/07 리스크 1).
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services import chat_service
from saju_shared_types.birth_input import BirthInput

_TODAY = date(2026, 6, 11)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date="2026-06-11",
)

# Q1~Q9 × 5 — (질문, 기대 query_type). 어구는 docs/08 실측 패턴 변형.
_CASES: list[tuple[str, str, str]] = [
    # Q1 fortune_overview — 종합운(시점 있음 → 분석, 무시점 → too_broad 허용).
    ("올해 운세 어때?", "fortune_overview", "any"),
    ("이번 달 운세 봐줘", "fortune_overview", "any"),
    ("내일 운세는?", "fortune_overview", "any"),
    ("내년 전체 운 흐름이 궁금해", "fortune_overview", "any"),
    ("이번 주 운세 알려줘", "fortune_overview", "any"),
    # Q2 domain_analysis — 분야 분석.
    ("올해 이직운 어때?", "domain_analysis", "analytical"),
    ("올해 재물운 좀 봐줘", "domain_analysis", "analytical"),
    ("내년 연애운은 어때?", "domain_analysis", "analytical"),
    ("올해 사업운이 궁금해", "domain_analysis", "analytical"),
    ("올해 건강운 어때?", "domain_analysis", "analytical"),
    # Q3 timing_search — 시점 탐색.
    ("언제 이직하는 게 좋을까?", "timing_search", "analytical"),
    ("결혼은 언제쯤 가능할까?", "timing_search", "analytical"),
    ("언제 이사가면 좋아?", "timing_search", "analytical"),
    ("연애는 언제 시작될까?", "timing_search", "analytical"),
    ("사업은 언제 시작하면 좋을까?", "timing_search", "analytical"),
    # Q4 date_recommendation — 날짜 추천(택일).
    ("7월에 이사하기 좋은 날짜 알려줘", "date_recommendation", "any"),
    ("다음 달 계약하기 좋은 날 골라줘", "date_recommendation", "any"),
    ("8월 중 개업 날짜 추천해줘", "date_recommendation", "any"),
    ("이번 달 손없는 날 알려줘", "date_recommendation", "any"),
    ("결혼식 날짜 좋은 날 추천해줘", "date_recommendation", "any"),
    # Q5 event_explanation — 사건/시기 설명.
    ("작년에 왜 그렇게 힘들었을까?", "event_explanation", "any"),
    ("2024년에 무슨 일이 있었는지 봐줘", "event_explanation", "any"),
    ("재작년 퇴사한 게 운 때문이야?", "event_explanation", "any"),
    ("작년에 헤어진 이유가 사주에 있어?", "event_explanation", "any"),
    ("올해 초에 사고난 거 운이랑 관련 있어?", "event_explanation", "any"),
    # Q6 comparison — 비교(궁합/경쟁/순위).
    ("1997.04.08 여자랑 나랑 궁합 봐줘", "comparison", "any"),
    ("남편이랑 나랑 궁합 어때?", "comparison", "any"),
    ("1998.07.23 여자, 1997.10.16 여자 중 나랑 합이 좋은 사람은?", "comparison", "any"),
    ("아들이랑 딸 중에 누가 올해 운이 더 좋아?", "comparison", "any"),
    ("동업자랑 나랑 잘 맞아?", "comparison", "any"),
    # Q7 decision_support — 선택 지원.
    ("이직할까 말까 고민이야", "decision_support", "analytical"),
    ("지금 집을 팔까 말까?", "decision_support", "any"),
    ("대학원 갈까 취업할까?", "decision_support", "any"),
    ("이 사람이랑 계속 만날까 말까?", "decision_support", "any"),
    ("사업을 접을까 말까 고민중이야", "decision_support", "any"),
    # Q8 chart_analysis — 명식 분석.
    ("내 사주에 뭐가 강해?", "chart_analysis", "any"),
    ("내 용신이 뭐야?", "chart_analysis", "any"),
    ("내 사주 격국 알려줘", "chart_analysis", "any"),
    ("나 신강이야 신약이야?", "chart_analysis", "any"),
    ("내 사주에 도화살 있어?", "chart_analysis", "any"),
    # Q9 relationship_analysis — 관계 분석(특정 인물).
    ("남편은 어떤 사람이야?", "relationship_analysis", "any"),
    ("우리 아들 성격은 어때?", "relationship_analysis", "any"),
    ("엄마랑 나는 왜 자꾸 부딪힐까?", "relationship_analysis", "any"),
    ("상사랑 관계가 힘든데 사주로 보면 어때?", "relationship_analysis", "any"),
    ("딸이랑 나랑 잘 지내려면 어떻게 해야 해?", "relationship_analysis", "any"),
]

_OK_STATUSES = {"dry_run", "too_broad", "need_subject", "policy"}


@pytest.mark.parametrize(
    "question,expected_type,route", _CASES,
    ids=[f"{t}-{i % 5 + 1}" for i, (_, t, _r) in enumerate(_CASES)],
)
def test_full_pipeline(question: str, expected_type: str, route: str) -> None:
    """질문 1건 → 파서→플래너→(엔진)→축소→직렬화 전체 경로가 안전하게 완주한다."""
    res = chat_service.chat(_BIRTH, question, _TODAY, dry_run=True)

    # 어떤 질문도 예외 없이 정의된 status로 응답.
    assert res.status in _OK_STATUSES, f"{question} → {res.status}"

    # 분류 확인 — 첫 intent 기준.
    assert res.intents, question
    assert res.intents[0].query_type.value == expected_type, (
        f"{question}: {res.intents[0].query_type} ≠ {expected_type}"
    )

    # 분석 라우트는 4요소 입력 + 토큰 한도(docs/09 8장) 검증.
    if route == "analytical":
        assert res.status == "dry_run", f"{question} → {res.status}: {res.answer}"
    if res.status == "dry_run":
        assert res.prompt_preview is not None
        for section in ("[원국]", "[이벤트 후보", "[지시]"):
            assert section in res.prompt_preview, f"{question}: {section} 누락"
        assert res.input_tokens is not None and res.input_tokens <= 8_000


def test_all_nine_types_covered() -> None:
    """Q1~Q9 각 5개 — 누락 없는 커버리지(규격 준수 자체 검증)."""
    types = [t for _q, t, _r in _CASES]
    assert len(_CASES) == 45
    for expected in (
        "fortune_overview", "domain_analysis", "timing_search", "date_recommendation",
        "event_explanation", "comparison", "decision_support", "chart_analysis",
        "relationship_analysis",
    ):
        assert types.count(expected) == 5
