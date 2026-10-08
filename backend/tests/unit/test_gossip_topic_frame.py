"""구설 소재·당사자 프레임 가드 (2026-08-11).

관측된 미스: **"지금은 가족적인 문제로 인해 구설이 심해. 가라앉을까?"** — 사용자는
[가족 문제 = 구설의 소재(원인)] / [구설 = 외부에서 도는 말]이라고 밝혔는데, 답변이
원인에 등장한 '가족'을 갈등의 상대방으로 재해석했다("가족 간의 오해나 구설",
"가족 내에서", 마무리 질문의 "가족의 요구 사항" — 말한 적 없는 사실의 전제).

라우팅은 정상이었다(구설 → social_conflict → career 승격 → 기본 기간). 결함은 LLM
해석 단계 — 인과 구조 보존을 강제하는 디렉티브 부재였다. 원인 표지(로 인해/때문에/
탓에)로 구설류 어휘와 연결된 질문이면 소재≠당사자 디렉티브를 주입한다(서술 전용,
점수·판정 불변). 문장 경계를 넘는 인과 서술은 P0 미지원.
"""

from __future__ import annotations

import pytest

from saju_api.services.chat_service import (
    _GOSSIP_TOPIC_FRAME_DIRECTIVE,
    _gossip_cause_clause,
)

# ── 감지: 원인 절 추출 ──────────────────────────────────────────────────────


def test_observed_case_extracts_family_cause() -> None:
    """관측된 원 사례 — 원인 절에 '가족적인 문제'가 담긴다."""
    cause = _gossip_cause_clause("지금은 가족적인 문제로 인해 구설이 심해. 가라앉을까?")
    assert cause is not None and "가족적인 문제" in cause


@pytest.mark.parametrize(("question", "expected_in_cause"), [
    ("집안일 때문에 논란이 커졌어. 어떻게 될까?", "집안일"),
    ("과거 행동 탓에 뒷말이 도는 것 같아. 언제 잠잠해질까?", "과거 행동"),
    ("구설이 심한데 가족 문제 때문이야. 가라앉을까?", "가족 문제"),  # 역방향 어순
])
def test_cause_marker_variants(question: str, expected_in_cause: str) -> None:
    cause = _gossip_cause_clause(question)
    assert cause is not None and expected_in_cause in cause


@pytest.mark.parametrize("question", [
    "올해 구설수가 있을까?",                      # 원인 표지 없음 — 무원인 구설 질문
    "가족 문제로 인해 고민이 많아. 어떻게 될까?",  # 구설류 어휘 없음
    "구설이 심해. 가족 문제가 원인이야.",          # 문장 경계 초과 — P0 미지원(문서화된 한계)
    "이사 때문에 고민이야",                        # 원인 표지만 있고 구설 없음
])
def test_non_trigger_questions(question: str) -> None:
    assert _gossip_cause_clause(question) is None


def test_directive_quotes_cause() -> None:
    """디렉티브에 추출된 원인 절이 그대로 인용된다."""
    cause = _gossip_cause_clause("지금은 가족적인 문제로 인해 구설이 심해. 가라앉을까?")
    assert cause is not None
    text = _GOSSIP_TOPIC_FRAME_DIRECTIVE.format(cause=cause)
    assert cause in text
    assert "소재" in text and "갈등의 상대방" in text
