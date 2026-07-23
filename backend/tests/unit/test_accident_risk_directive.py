"""사고수(事故數) 풀이 — 사고·안전 질문 감지와 디렉티브 정책(2026-07-23).

데굴님 제공 강의 자료 증류: 이동(역마 충형)·문서(인성 충극)·통제력(관성 손상·태왕
고집)·외부 유입(대비 전용) 4축 + 발생 단정·초자연 원인 서술 금지. '사고'는 매수
연결형('집을 사고 싶어')·'사고방식' 동형어가 많아 경계 정규식으로만 인정한다.
"""

from __future__ import annotations

from saju_api.services.chat_service import (
    _ACCIDENT_RISK_DIRECTIVE,
    _is_accident_risk_question,
)


def test_accident_questions_detected() -> None:
    for q in (
        "앞으로 10년간 내게 사고 위험은 없을까?",
        "교통사고 조심해야 할 시기가 있을까",
        "올해 사고수 있어?",
        "사고 안 나겠지?",
        "크게 다칠 일은 없을까",
        "횡액이 있는지 봐줘",
        "낙상 위험이 걱정돼",
    ):
        assert _is_accident_risk_question(q), q


def test_purchase_and_homonyms_not_detected() -> None:
    for q in (
        "내년에 집을 사고 싶어",
        "주식을 사고 팔고 하는 게 맞을까",
        "내 사고방식은 어떤 편이야?",
        "사고력이 좋은 사주야?",
        "복권을 사고 나서 어떻게 해야 해",
    ):
        assert not _is_accident_risk_question(q), q


def test_directive_policy_content() -> None:
    """디렉티브에 4축과 금지 프레임이 모두 들어 있는지 — 정책 회귀 가드."""
    d = _ACCIDENT_RISK_DIRECTIVE
    assert "이동·교통" in d and "문서·계약" in d and "통제력" in d and "외부 유입" in d
    assert "단정 금지" in d
    assert "귀신" in d and "금지" in d  # 초자연 원인 서술 금지
    assert "주의가 필요한 시기" in d
