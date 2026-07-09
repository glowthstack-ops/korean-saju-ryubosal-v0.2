"""이사 목적지 명시 질문 → 지역오행·방위 중심 응답 라우팅 (실로그 회귀).

버그: '이사할집은 서울 중구야'처럼 특정 목적지를 대고 적합성을 물어도 10년 연 단위 타임라인
지시(year digest)가 답을 채워 지역오행·방위 의도가 묻힘. 목적지 명시 시 타임라인 강제를 끄고
목적지 중심 지시로 대체해야 한다.
"""

from __future__ import annotations

from datetime import date

from saju_api.services import chat_service
from saju_shared_types.birth_input import BirthInput

_TODAY = date(2026, 6, 25)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="07:30",
    birth_place_name="서울", gender="male", reference_date="2026-06-25",
)

_YEAR_DIGEST_MARK = "올해부터 약 10년의 흐름을"
_DEST_MARK = "이사 목적지 질문"


def _prompt(q: str) -> str:
    res = chat_service.chat(_BIRTH, q, _TODAY, dry_run=True)
    return res.prompt_preview or ""


def test_destination_question_centers_on_region_and_direction() -> None:
    t = _prompt("현재는 고양시 일산동구에 있는데 이사할집은 서울 중구야.")
    # 목적지 중심 지시 ON, 10년 타임라인 강제 지시 OFF.
    assert _DEST_MARK in t
    assert _YEAR_DIGEST_MARK not in t
    # 지역오행·방위 적합 블록이 프롬프트에 실린다.
    assert "지역 오행 적합" in t and "이동 방위 적합" in t


def test_vague_relocation_without_destination_keeps_timeline() -> None:
    # 목적지 미명시 막연 이사 질문 — 지평 정책(2026-07-09)에 따라 분야 기본 6개월 월 단위
    # 타임라인로 답한다(과거 10년 digest → 축소). 목적지 지시는 여전히 미적용.
    t = _prompt("앞으로 이사운 어때?")
    assert _YEAR_DIGEST_MARK not in t
    assert "[답변 지평]" in t and "향후 6개월" in t
    assert "[월별 요약" in t  # 월 단위 타임라인은 유지
    assert _DEST_MARK not in t


def test_non_relocation_question_unaffected() -> None:
    t = _prompt("앞으로 재물운 흐름 어때?")
    assert _DEST_MARK not in t  # 이사 목적지 지시 미적용


def _has_timeline(t: str) -> bool:
    return ("[연도별 흐름" in t) or ("[월별 요약" in t)


def test_decided_move_suppresses_timeline_blocks() -> None:
    # 목적지 결정 + 시점 미질문 → '언제 옮기나' 타임라인 데이터 블록을 만들지 않는다.
    t = _prompt("현재는 고양시 일산동구에 있는데 이사할집은 서울 중구야.")
    assert not _has_timeline(t)
    # 평가 핵심 블록은 유지.
    assert "지역 오행 적합" in t and "이동 방위 적합" in t and "이사 이유" in t


def test_relocation_timing_question_keeps_timeline() -> None:
    # 시점을 명시적으로 물으면(언제) 타임라인 유지.
    assert _has_timeline(_prompt("서울 중구로 언제 이사하면 좋아?"))


def test_vague_relocation_without_destination_keeps_timeline_block() -> None:
    assert _has_timeline(_prompt("앞으로 이사운 어때?"))
