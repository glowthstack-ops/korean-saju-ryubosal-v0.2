"""택일 내부 enum 한글화 — LLM에 'recommended'·'wealth' 같은 내부값이 노출되던 결함 차단.

실로그: '택일 결과도 recommended이고', '재물'인데 'wealth 신호 기반'으로 답변에 영문 enum 누출.
직렬화 단계에서 한글 라벨로만 내보낸다(2026-07-01 데굴님 지적).
"""

from __future__ import annotations

from saju_engines.context_reducer import recommendation_ko
from saju_engines.date_selection import _DOMAIN_KO


def test_recommendation_labels_ko() -> None:
    assert recommendation_ko("recommended") == "추천"
    assert recommendation_ko("acceptable") == "무난"
    assert recommendation_ko("avoid") == "회피"
    # 미지값은 그대로(방어) — 단, 알려진 3등급은 모두 한글이어야 한다.
    assert recommendation_ko("unknown") == "unknown"
    for eng in ("recommended", "acceptable", "avoid"):
        assert recommendation_ko(eng).isascii() is False  # 한글로 치환됨


def test_domain_reason_ko() -> None:
    assert _DOMAIN_KO["wealth"] == "재물"
    assert _DOMAIN_KO["relocation"] == "이사"
    # 모든 매핑값이 한글(영문 enum 잔존 금지).
    for ko in _DOMAIN_KO.values():
        assert ko.isascii() is False
