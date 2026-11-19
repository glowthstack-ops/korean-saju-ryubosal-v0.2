"""횡재 택일 프롬프트 배선(2026-11-16) — 등급 기준 줄·상세 사유·회피일·지시 분기·일별 흐름 줄.

엔진 규칙은 `tests/unit/test_windfall_date_grade_20261116.py` 가 고정한다. 여기서는 그 값이
대화 프롬프트까지 그대로 실리는지만 본다(LLM 미호출 dry-run).
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services import chat_service
from saju_shared_types.birth_input import BirthInput

_TODAY = date(2026, 11, 16)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date=_TODAY,
)


@pytest.fixture(scope="module")
def lotto():
    """'이번주 로또 사기 좋은 날' dry-run 응답."""
    return chat_service.chat(_BIRTH, "이번주중 로또사기 좋은 날을 알려줘", _TODAY, dry_run=True)


def test_table_rows_carry_engine_reasons(lotto) -> None:
    block = lotto.postprocess.payload.date_selection
    assert block is not None and block.rows
    for row in block.rows:
        assert row.stem_ten_god and row.branch_ten_god and row.stem_role
        assert row.notes[0].startswith(f"천간 {row.ganji[0]} {row.stem_ten_god}({row.stem_role})")
        assert any(n.startswith("재물 신호 ") for n in row.notes)
        assert any(n.startswith("걸리는 관계") for n in row.notes)
        assert not any("신호 기반" in n for n in row.notes)
        # [추천]은 유리 방향 신호가 적힌 날에만 붙는다.
        if row.recommendation == "recommended":
            assert any(n.startswith("재물 신호 있음(유리 방향") for n in row.notes)
            assert row.stem_role not in ("기신", "구신")


def test_grade_notes_and_instruction_branch(lotto) -> None:
    block = lotto.postprocess.payload.date_selection
    text = lotto.prompt_preview or ""
    assert block.grade_notes and "등급 기준: [추천]은 그날 재물 신호가 유리 방향으로" in text
    assert "[택일 표 인용 규칙]" in text
    has_rec = any(r.recommendation == "recommended" for r in block.rows)
    assert block.has_recommended is has_rec
    if has_rec:
        assert "1–3개 날짜를 명확히 추천할 것" in text
    else:
        assert "이 표에는 [추천] 등급 날이 없다" in text
        assert "1–3개 날짜를 명확히 추천할 것" not in text
        assert "이 기간에는 [추천] 등급 날이 없다" in text


def test_risk_avoid_days_are_listed_not_dropped(lotto) -> None:
    """위험도 회피 등급 날은 표에서 빠지되 회피일 줄에 사유와 함께 남는다(종전에는 사라졌다)."""
    block = lotto.postprocess.payload.date_selection
    row_dates = {r.date for r in block.rows}
    avoid_dates = {str(a["date"]) for a in block.avoid}
    assert not (row_dates & avoid_dates)
    # 이번 회차의 남은 날(11/16~11/21)은 표 행이든 회피일이든 한 곳에는 실린다.
    remaining = {f"2026-11-{d:02d}" for d in range(16, 22)}
    assert remaining <= (row_dates | avoid_dates)
    for a in block.avoid:
        assert "걸리는 관계(충·형·원진)" in str(a["reason"])
        assert f"회피일 {a['date']} — " in (lotto.prompt_preview or "")


def test_daily_flow_lines_label_stem_and_branch(lotto) -> None:
    text = lotto.prompt_preview or ""
    flow = text.split("일별 흐름")[1].split("\n\n")[0]
    day_lines = [ln for ln in flow.splitlines() if ln.startswith("- 2026-11-")]
    assert len(day_lines) == 7
    for ln in day_lines:
        assert " · 천간 " in ln and " · 지지 " in ln and "십성 " not in ln
    assert "읽는 법: 괄호의 길흉은 그날 천간 기준이다" in flow


def test_relocation_table_uses_stem_only_grade_note() -> None:
    """이사 택일은 십성 적합표가 그날 근거라 신호를 요구하지 않는다 — 기신·구신 천간 차단 문장만
    싣고, [추천] 행의 천간은 기신·구신이 아니다."""
    res = chat_service.chat(
        _BIRTH, "다음 달 이사하기 좋은 날짜 알려줘", date(2026, 6, 11), dry_run=True,
    )
    block = res.postprocess.payload.date_selection
    text = res.prompt_preview or ""
    assert block is not None and len(block.grade_notes) >= 1
    assert "등급 기준: [추천]은 일진 천간이 기신·구신이 아니고" in text
    assert "신호가 유리 방향으로 있고" not in text
    assert "[택일 표 인용 규칙]" in text
    assert block.has_recommended is any(r.recommendation == "recommended" for r in block.rows)
    for row in block.rows:
        assert row.notes[0].startswith(f"천간 {row.ganji[0]} {row.stem_ten_god}({row.stem_role})")
        if row.recommendation == "recommended":
            assert row.stem_role not in ("기신", "구신")
    assert not any("횡재 관점" in n for row in block.rows for n in row.notes)
