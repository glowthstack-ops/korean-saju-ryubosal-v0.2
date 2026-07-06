"""상담 사례 파생 서술 디렉티브 채팅 트리거 검증 (P0 — 사례 §5).

성향 반박(_is_trait_mismatch)·규범 당위(_is_normative_question) 감지는 인용+부정,
강한 당위 표지 기반 — 일반 질문 오탐을 함께 고정한다(과잉 트리거 방지).
"""

from __future__ import annotations

from saju_api.services.chat_service import (
    _is_normative_question,
    _is_trait_mismatch,
)


def test_trait_mismatch_detects_quote_plus_negation() -> None:
    """'풀이 인용 + 실제 부정' 조합만 성향 반박으로 잡는다."""
    assert _is_trait_mismatch("말이 매력적인 팔자라는데 실제로는 면접에서 말을 잘 못해요")
    assert _is_trait_mismatch("리포트에 외로움을 잘 탄다는데 저는 혼자 있어도 아무렇지 않은데요")
    # 인용만 있고 부정이 없으면 미트리거.
    assert not _is_trait_mismatch("제 사주에는 재물복이 있다는데 맞나요")
    # 부정만 있고 인용이 없으면 미트리거(일반 고민 상담).
    assert not _is_trait_mismatch("요즘 일이 잘 안 맞는 것 같아요")


def test_normative_question_detects_strong_obligation_only() -> None:
    """'꼭 해야 하나' 류 강한 당위만 잡고 일반 의사결정 질문은 놓아둔다."""
    assert _is_normative_question("결혼 꼭 해야 하나요?")
    assert _is_normative_question("다들 하니까 저도 집을 사야 할까요")
    # 일반 의사결정/시기 질문은 미트리거(결론 선제시 디렉티브가 담당).
    assert not _is_normative_question("이직해야 하나 고민이에요")
    assert not _is_normative_question("올해 결혼운이 어때요")
