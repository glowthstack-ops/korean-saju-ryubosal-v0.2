"""'그래 봐줘' 수락 시 직전 답변의 LLM 제안을 이어 답하도록 주입 (실로그 후속 개선).

버그: LLM이 답변 끝에 제시한 즉석 제안('제안받는 vs 내가 움직이는')이 상태에 없어, 수락
('그래 봐줘')해도 일반 흐름으로 끊김. 직전 답변에서 제안을 추출해 '그걸 이어 답하라' 지시 주입.
"""

from __future__ import annotations

from datetime import date

from saju_api.services import chat_service
from saju_api.services.chat_service import _extract_offer
from saju_shared_types.birth_input import BirthInput

_T = date(2026, 6, 25)
_B = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="07:30",
    birth_place_name="서울", gender="male", reference_date="2026-06-25",
)
_PRIOR = (
    "데굴님, 흐름이 좋네요. 핵심은 올해가 전환의 바닥을 깔아 주는 해라는 점이에요. "
    "원하시면 제가 '제안이 들어오는 쪽'과 '내가 먼저 움직이는 쪽' 중 어느 흐름이 "
    "더 강한지도 이어서 봐드릴게요."
)
_MARK = "이어보기 — 다른 표기보다"


def _prompt(q: str, prior: str | None) -> str:
    return chat_service.chat(_B, q, _T, dry_run=True, prior_answer=prior).prompt_preview or ""


def test_extract_offer_picks_proposal_tail() -> None:
    offer = _extract_offer(_PRIOR)
    assert "제안이 들어오는 쪽" in offer and "봐드릴게요" in offer


def test_extract_offer_empty_without_markers() -> None:
    assert _extract_offer("흐름이 좋네요. 잘 지내세요.") == ""
    assert _extract_offer("") == ""


def test_affirm_continue_injects_prior_offer() -> None:
    t = _prompt("그래 봐줘", _PRIOR)
    assert _MARK in t  # 이어보기 지시문
    assert "제안이 들어오는 쪽" in t  # 직전 제안 텍스트가 그대로 실린다


def test_non_affirmation_does_not_inject() -> None:
    # 수락이 아닌 새 질문엔 직전 제안을 주입하지 않는다.
    assert _MARK not in _prompt("올해 재물운 어때?", _PRIOR)


def test_no_prior_or_no_offer_does_not_inject() -> None:
    assert _MARK not in _prompt("그래 봐줘", None)
    assert _MARK not in _prompt("그래 봐줘", "흐름이 좋네요. 잘 지내세요.")
