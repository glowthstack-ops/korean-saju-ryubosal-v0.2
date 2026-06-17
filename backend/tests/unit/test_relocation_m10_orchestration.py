"""M10 그룹 리졸버 오케스트레이션 — 채팅(다인 택일) + 리포트(방위·월별 흐름) 연결.

본인+첨부 상대 2인 이사 택일은 M10 그룹 집계(함께 무난한 날)로, 이사 테마 리포트는
방위 적합(RL-04)·월별 이동운 흐름(RL-06)을 surface한다. 점수는 코드가 계산(절대원칙 1).
"""

from __future__ import annotations

from datetime import date

from saju_api.services import chat_service
from saju_api.services.report_service import plan_report
from saju_engines.query_parser import parse_message
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportSpec

_SELF = BirthInput(
    calendar_type="solar", birth_date=date(1990, 3, 15), birth_time="10:00",
    birth_place_name="서울", gender="male",
)
_PARTNER = BirthInput(
    calendar_type="solar", birth_date=date(1992, 7, 20), birth_time="14:00",
    birth_place_name="서울", gender="female",
)


# ── 채팅: 다인 그룹 택일 ──────────────────────────────────────────


def test_relocation_intent_gate() -> None:
    """이사 도메인/이벤트 질문만 그룹 M10으로 분기한다."""
    reloc = parse_message(
        "배우자랑 같이 이사 좋은 날", date(2026, 6, 11), birth_year=1990).intents[0]
    other = parse_message(
        "올해 재물운 좋은 날", date(2026, 6, 11), birth_year=1990).intents[0]
    assert chat_service._is_relocation_intent(reloc) is True
    assert chat_service._is_relocation_intent(other) is False


def test_group_block_aggregates_two_subjects() -> None:
    """본인+상대 이사 택일 → 그룹 집계 블록(랭킹·방위·그룹 라벨)."""
    intent = parse_message(
        "배우자랑 같이 이사 좋은 날 언제야?", date(2026, 6, 11), birth_year=1990
    ).intents[0]
    block = chat_service._relocation_group_block(
        _SELF, _PARTNER, intent, date(2026, 6, 11), "본인", "배우자",
    )
    assert block is not None
    assert "그룹" in block.purpose_ko and "본인" in block.purpose_ko
    assert block.rows  # 함께 무난한 이사일 랭킹
    assert all(0 <= r.score <= 100 for r in block.rows)
    assert block.directions  # 방위 적합 동반


def test_group_block_falls_back_when_not_relocation() -> None:
    """이사가 아닌 질문은 그룹 경로를 타지 않는다(게이트)."""
    intent = parse_message("재물운 좋은 날", date(2026, 6, 11), birth_year=1990).intents[0]
    assert chat_service._is_relocation_intent(intent) is False


# ── 리포트: 방위·월별 흐름 surface ───────────────────────────────


def _reloc_spec() -> ReportSpec:
    return ReportSpec(
        product_code="RPT_FOCUS", topic="relocation",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period={"start": "2026", "end": "2031"},
    )


def test_report_surfaces_direction_and_flow() -> None:
    """이사 테마 리포트 RL-04(방위)·RL-06(월별 이동운 흐름)에 M10 결과가 실린다."""
    secs = {s.section_id: s for s in plan_report(_SELF, _reloc_spec(), date(2026, 6, 11))}
    assert "방위 적합" in secs["RL-04"].body_prompt
    assert "월별 이동운 흐름" in secs["RL-06"].body_prompt
    assert "유리한 방위" in secs["RL-04"].body_prompt
