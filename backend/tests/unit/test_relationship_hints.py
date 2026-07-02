"""관계유형 추론 + 관점 힌트(P3a).

질문 키워드 > companion relation_to_user > intent/domain > unknown 순으로 관계유형을
추론하고, 관계유형별 관점 힌트를 제공한다. 점수·우열·승패는 만들지 않는다(관점 제어 전용).
"""

from __future__ import annotations

import pytest

from saju_engines.relationship_hints import (
    COMPETITION_SAFETY_GUARDS,
    PERSPECTIVE_HINTS,
    RELATION_TYPES,
    SAFETY_GUARDS,
    infer_relation_type,
    is_competition,
    perspective_hints_for,
)


@pytest.mark.parametrize(
    ("question", "relation_to_user", "domains", "expected_type", "expected_basis"),
    [
        ("와이프랑 궁합 봐줘", "spouse", None, "spouse", "explicit_keyword"),
        ("지민이랑 연애 궁합 봐줘", None, None, "romance", "explicit_keyword"),
        ("엄마랑 관계가 왜 힘들까?", "mother", None, "parent_child", "explicit_keyword"),
        ("이 사람이랑 동업해도 될까?", None, None, "business_partner", "explicit_keyword"),
        ("직장 동료랑 잘 맞을까?", None, None, "coworker", "explicit_keyword"),
        ("친구랑 궁합 봐줘", None, None, "friend", "explicit_keyword"),
        # 키워드 없음 + 등록 관계로 결정.
        ("이 분이랑 봐줘", "mother", None, "parent_child", "relation_to_user"),
        # 키워드/관계 없음 + 관계 도메인 → romance(약한 추론).
        ("이 사람이랑 봐줘", None, ["relationship"], "romance", "intent_domain"),
        # 단서 전무 → unknown.
        ("이 사람이랑 봐줘", None, [], "unknown", "unknown"),
    ],
)
def test_infer_relation_type(
    question: str, relation_to_user: str | None, domains: list[str] | None,
    expected_type: str, expected_basis: str,
) -> None:
    rtype, basis = infer_relation_type(question, relation_to_user, domains)
    assert rtype == expected_type
    assert basis == expected_basis


def test_question_keyword_overrides_registered_relation() -> None:
    """질문 키워드가 등록 관계보다 우선 — friend로 등록됐어도 '동업'이면 business_partner."""
    rtype, basis = infer_relation_type("동업하면 어때?", "friend", None)
    assert rtype == "business_partner"
    assert basis == "explicit_keyword"


def test_perspective_hints_defined_for_all_types() -> None:
    """모든 관계유형에 관점 힌트가 정의돼 있고, 미정의는 unknown 힌트로 폴백."""
    for rt in RELATION_TYPES:
        assert PERSPECTIVE_HINTS.get(rt)
    assert perspective_hints_for("nonexistent") == PERSPECTIVE_HINTS["unknown"]


def test_safety_guards_present() -> None:
    """안전 가드(우열·승패 단정 금지)가 비어 있지 않다 — competition 미구현이어도 유지."""
    assert SAFETY_GUARDS
    assert any("우열" in g or "승패" in g for g in SAFETY_GUARDS)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("누가 합격 가능성이 더 있어?", True),
        ("둘 중 누가 이길까?", True),
        ("누가 더 잘돼?", True),
        ("우승은 누구?", True),
        ("당선될 사람은?", True),
        ("엄마랑 아빠 잘 맞아?", False),  # 관계 비교(경쟁 아님)
        ("지민이랑 궁합 봐줘", False),
        ("내 올해 운 봐줘", False),
    ],
)
def test_is_competition(question: str, expected: bool) -> None:
    assert is_competition(question) is expected


def test_competition_guards_forbid_verdicts() -> None:
    """경쟁 가드는 승패·당락 확정·확률·순위 산출 금지를 명시한다(절대원칙 8)."""
    joined = " ".join(COMPETITION_SAFETY_GUARDS)
    assert "확정하지" in joined
    assert "승률" in joined or "확률" in joined
    assert "순위" in joined


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("누가 제일 잘돼?", True),
        ("셋 중 누가 가장 나아?", True),
        ("지민 민수 영희 비교해줘", True),
        ("순위 매겨줘", True),
        ("내 올해 운 봐줘", False),
        ("지민이랑 궁합", False),
    ],
)
def test_is_ranking_query(question: str, expected: bool) -> None:
    from saju_engines.relationship_hints import is_ranking_query
    assert is_ranking_query(question) is expected


def test_ranking_guards_forbid_rank_and_scores() -> None:
    """다자 가드는 절대 순위·점수·확률·승률 산출 금지를 명시한다."""
    from saju_engines.relationship_hints import RANKING_SAFETY_GUARDS
    joined = " ".join(RANKING_SAFETY_GUARDS)
    assert "순위" in joined and "1등" in joined
    assert "점수" in joined and ("확률" in joined or "승률" in joined)
