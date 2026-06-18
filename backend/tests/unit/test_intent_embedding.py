"""Intent 임베딩 보조 분류기 — graceful 비활성 + rules-first 폴백 보강 검증.

모델(compiled/intent_onnx)·런타임 의존성([intent])이 없는 fresh clone/CI에서는 분류기가
비활성이므로 보강 테스트는 skip한다(graceful 자체는 항상 검증). 절대원칙 11 — 부재가 차단 금지.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_engines.intent_embedding import (
    IntentEmbeddingClassifier,
    get_intent_classifier,
)
from saju_engines.query_parser import parse_message
from saju_shared_types.intent import Domain

_CLF = get_intent_classifier()
_needs_model = pytest.mark.skipif(
    not _CLF.available(), reason="intent ONNX 모델/의존성 부재 — 분류기 비활성(graceful)"
)


def test_graceful_when_model_absent() -> None:
    """모델 경로가 없으면 예외 없이 비활성(서버 정상 기동 보장)."""
    clf = IntentEmbeddingClassifier(model_dir=Path("/nonexistent/intent_onnx"))
    assert clf.available() is False
    assert clf.classify("이사 언제 갈까") is None


@_needs_model
def test_rescues_general_domain_queries() -> None:
    """규칙이 general로만 잡는 표현을 임베딩이 구체 domain으로 보강한다(rules-first 폴백)."""
    from saju_api.services.chat_service import _augment_domain_by_similarity

    cases = {
        "주머니 사정 나아질까?": Domain.WEALTH,
        "혼삿길이 언제 열릴까": Domain.RELATIONSHIP,
        "보금자리 옮기는 거 어떨까?": Domain.RELOCATION,
    }
    for q, expected in cases.items():
        base = parse_message(q, date(2026, 6, 18)).intents[0]
        assert base.domain is Domain.GENERAL, f"전제: 규칙이 general이어야 — {q}"
        aug = _augment_domain_by_similarity(base, q)
        assert aug.domain is expected, q


@_needs_model
def test_does_not_override_confident_rule_domain() -> None:
    """규칙이 이미 도메인을 확신하면(general 아님) 임베딩이 덮어쓰지 않는다(rules-first)."""
    from saju_api.services.chat_service import _augment_domain_by_similarity

    base = parse_message("이직 언제쯤 할까?", date(2026, 6, 18)).intents[0]
    assert base.domain is Domain.CAREER
    aug = _augment_domain_by_similarity(base, "이직 언제쯤 할까?")
    assert aug.domain is Domain.CAREER  # 변경 없음


@_needs_model
def test_abstains_on_vague_chitchat() -> None:
    """모호·잡담은 게이트(저신뢰)가 abstain — general 유지(오라우팅 금지)."""
    from saju_api.services.chat_service import _augment_domain_by_similarity

    base = parse_message("오늘 기분이 좋아", date(2026, 6, 18)).intents[0]
    aug = _augment_domain_by_similarity(base, "오늘 기분이 좋아")
    assert aug.domain is Domain.GENERAL
