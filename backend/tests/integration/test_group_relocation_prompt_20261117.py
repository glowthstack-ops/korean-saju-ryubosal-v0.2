"""다인 이사 택일 프롬프트 배선(2026-11-17) — 구성원별 줄·말미 지시 분기(LLM 미호출 dry-run).

표의 규칙은 `tests/unit/test_group_relocation_members_20261117.py` 가 고정한다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services import chat_service
from saju_shared_types.birth_input import BirthInput

_TODAY = date(2026, 6, 11)
_SELF = BirthInput(
    calendar_type="solar", birth_date=date(1990, 3, 15), birth_time="10:00",
    birth_place_name="서울", gender="male", reference_date=_TODAY,
)
_PARTNER = BirthInput(
    calendar_type="solar", birth_date=date(1992, 7, 20), birth_time="14:00",
    birth_place_name="서울", gender="female",
)


@pytest.fixture(scope="module")
def group():
    """첨부 상대와 함께 묻는 이사 택일 dry-run 응답."""
    return chat_service.chat(
        _SELF, "배우자랑 같이 이사 좋은 날 언제야?", _TODAY, dry_run=True,
        partner_birth=_PARTNER, partner_label="배우자",
    )


def test_member_lines_rendered_without_row_grade(group) -> None:
    block = group.postprocess.payload.date_selection
    text = group.prompt_preview or ""
    # 첫 구성원은 기준 대상(라벨 미지정 시 기본 호칭), 둘째가 첨부 상대다.
    assert block is not None and len(block.group_members) == 2
    assert block.group_members[1] == "배우자"
    assert f"[택일 결과 — 이사(구성원별: {'·'.join(block.group_members)})" in text
    row = block.rows[0]
    head = next(ln for ln in text.splitlines() if ln.startswith(f"{row.date}({row.weekday})"))
    # 날짜 줄에는 등급 괄호가 없다 — 등급은 구성원 줄에만 붙는다.
    assert "[추천]" not in head and "[무난]" not in head and "[회피]" not in head
    for label in block.group_members:
        assert any(ln.startswith(f"  · {label} [") for ln in text.splitlines())
    assert "방위(구성원 공통): " in text
    assert "(None)" not in text


def test_group_tail_instruction_replaces_single_pick(group) -> None:
    text = group.prompt_preview or ""
    assert "이 표는 구성원별 풀이다" in text
    assert "1–3개 날짜를 명확히 추천할 것" not in text
    assert "[택일 표 인용 규칙]" in text


def test_single_subject_relocation_unchanged() -> None:
    """동반자가 없으면 종전 단일 택일 표(행 등급) 그대로다."""
    res = chat_service.chat(_SELF, "이사 좋은 날 언제야?", _TODAY, dry_run=True)
    block = res.postprocess.payload.date_selection
    assert block is not None and not block.group_members
    assert all(not r.members for r in block.rows)
    assert "이 표는 구성원별 풀이다" not in (res.prompt_preview or "")
