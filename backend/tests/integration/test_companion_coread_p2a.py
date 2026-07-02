"""동반자 공동 풀이 P2a(pairwise) — 대상별 명식 subject_blocks 가산 주입.

본인 base 파이프라인은 유지한 채 동반자 ChartAnalysis를 [함께 보기] 블록으로 더한다.
per_subject/chat_compare 실행 분기는 불변(chat_single 유지), 궁합 오버레이는 보조 유지,
동반자 birth가 없으면 본인 명식으로 대체하지 않고 블록을 생략한다.
"""

from __future__ import annotations

from datetime import date

from saju_api.services import chat_service
from saju_shared_types.birth_input import BirthInput

_TODAY = date(2026, 7, 2)
_SELF = BirthInput(
    birth_date="1980-11-22", birth_time="09:40", birth_place_name="서울", gender="male",
)
_COMP = BirthInput(
    birth_date="1985-03-15", birth_time="14:00", birth_place_name="서울", gender="female",
)


def _dry(question: str, **kw) -> chat_service.ChatResponse:
    return chat_service.chat(
        _SELF, question, today=_TODAY, dry_run=True, subject_label="데굴", **kw,
    )


def test_self_only_no_subject_blocks() -> None:
    """동반자 없음 → [함께 보기] 미주입, 기존 chat_single 경로 불변."""
    r = _dry("내 올해 운 봐줘")
    assert "함께 보기" not in (r.prompt_preview or "")
    assert r.call_type == "chat_single"


def test_pairwise_injects_companion_chart() -> None:
    """칩 partner pairwise → 동반자 명식 블록 + 관계맥락 주입. 궁합 오버레이 보조 유지."""
    r = _dry(
        "지민이랑 궁합 어때?",
        partner_birth=_COMP, partner_label="지민",
        partner_ref={"mode": "registered", "subjectId": "c1", "label": "지민"},
        companion_births={"c1": _COMP},
    )
    txt = r.prompt_preview or ""
    assert "함께 보기 — 대상별 명식" in txt
    assert "지민" in txt
    # 동반자 명식 구조(일간·용신)가 실제로 실린다 — 본인 것으로 대체되지 않음.
    assert "일간 癸" in txt  # 지민(1985-03-15) 일간
    assert "[궁합 분석" in txt  # 기존 오버레이 보조 유지


def test_pairwise_does_not_flip_per_subject() -> None:
    """P2a 불변식 — pairwise여도 call_type은 chat_single(per_subject 미전환)."""
    r = _dry(
        "지민이랑 궁합",
        partner_birth=_COMP, partner_label="지민",
        partner_ref={"mode": "registered", "subjectId": "c1", "label": "지민"},
        companion_births={"c1": _COMP},
    )
    assert r.call_type == "chat_single"


def test_relationship_perspective_injected() -> None:
    """P3a — '연애 궁합'이면 relation_type=romance + 관점 힌트 + 안전 가드가 입력에 실린다."""
    r = _dry(
        "지민이랑 연애 궁합 어때?",
        partner_birth=_COMP, partner_label="지민",
        partner_ref={"mode": "registered", "subjectId": "c1", "label": "지민"},
        companion_births={"c1": _COMP},
    )
    txt = r.prompt_preview or ""
    assert "함께 보기 — 관계 관점" in txt
    assert "romance" in txt
    assert "연애 지속성" in txt  # romance 관점 힌트
    assert "우열·승패로 단정하지 말 것" in txt  # 안전 가드


def test_missing_companion_birth_no_self_fallback() -> None:
    """동반자 birth 없음 → 블록 생략(본인 명식으로 대체 금지), 크래시 없음."""
    r = _dry(
        "지민이랑 궁합",
        partner_ref={"mode": "registered", "subjectId": "c1", "label": "지민"},
        companion_births={},
    )
    assert "함께 보기" not in (r.prompt_preview or "")
    assert r.status == "dry_run"
