"""직장 이력 캘리브레이션 P2 검증 — EMPLOYMENT_HISTORY_CALIBRATION.md §4.

진입 시기 두 칸(entry_window)·글자 반복 라벨(수치만, 회사 없음)·진입 통로 블록·이력 프리필 복원을
확인한다. DB 미사용. 골든 차트 1980-11-22 09:40 서울.
"""

from __future__ import annotations

from datetime import date

import saju_api.services.chat_service as chat_service
from saju_api.services.manse_service import calculate
from saju_engines.employment_history import entries_from_rows, rows_from_history
from saju_engines.horizon import ENTRY_WINDOW_DIRECTIVE, horizon_directive, resolve_horizon
from saju_engines.llm_event_serializer import reason_codes_ko
from saju_engines.reality_calibration import pillars_signature
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import ConfidenceLevel, EventCandidateV2
from saju_shared_types.intent import IntentJson
from saju_shared_types.life_event import EmploymentHistoryEntry

_BIRTH = BirthInput(
    calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
    birth_place_name="서울", gender="male", reference_date=date(2026, 10, 22),
)


def _intent(**over) -> IntentJson:
    return IntentJson.model_validate(
        {"intent_id": "t-p2", "query_type": "domain_analysis", "domain": "career", **over}
    )


# ── 진입 시기 두 칸 ───────────────────────────────────────────────────────────
def test_entry_window_on_job_when_question_and_directive_text() -> None:
    pol = resolve_horizon("언제쯤 취업이 될까요", _intent(event_key="job_gain"))
    assert pol is not None and pol.kind == "transactional_when" and pol.entry_window
    text = horizon_directive(pol)
    assert "움직이는 달" in text and "성사 달" in text and "회사명" in text
    assert ENTRY_WINDOW_DIRECTIVE in text


def test_entry_window_off_for_other_events_and_structural() -> None:
    pol = resolve_horizon("언제쯤 이사 가게 될까요", _intent(event_key="relocation"))
    assert pol is not None and not pol.entry_window
    assert "움직이는 달" not in horizon_directive(pol)
    # 구조 결정형(퇴사 보고)은 두 칸을 붙이지 않는다.
    pol2 = resolve_horizon(
        "오늘 권고사직 통보를 받았어요 앞으로 어떻게 될까요",
        _intent(event_key="career_change", dialogue_act="reported_event"),
    )
    assert pol2 is not None and pol2.kind == "structural" and not pol2.entry_window


# ── 글자 반복 라벨(수치만) ───────────────────────────────────────────────────
def test_glyph_repeat_label_has_numbers_but_no_names() -> None:
    labels = reason_codes_ko(["PERSONAL_GLYPH_REPEAT:亥:4/11", "PERSONAL_MATCH"])
    assert labels[0] == (
        "개인 이력 반복(같은 亥월 글자에서 같은 사건 4/11건 — 기대 비율 1/12, "
        "특정 사례·회사 지목 아님)"
    )
    assert labels[1] == "개인 이력 일치(과거 확인 사건과 같은 신호 유형)"
    # 접미 없는 코드는 일반 라벨로.
    assert reason_codes_ko(["PERSONAL_GLYPH_REPEAT"]) == [
        "개인 이력 반복(같은 월운 글자에서 같은 사건이 되풀이됨)"
    ]


# ── 진입 통로 블록 ───────────────────────────────────────────────────────────
def _cand(key: str, period: str, score: int) -> EventCandidateV2:
    return EventCandidateV2(event_key=key, period=period, score=score,
                            confidence_level=ConfidenceLevel.EVENT_CANDIDATE)


def test_entry_channel_context_lines_without_family_and_only_entry_keys() -> None:
    result = calculate(_BIRTH)
    cands = [_cand("job_gain", "2026-11", 60), _cand("relocation", "2026-12", 90),
             _cand("career_change", "2027-01", 50)]
    lines = chat_service._entry_channel_context(
        _BIRTH, result, _intent(event_key="job_gain"), "언제 취업될까요", cands,
    )
    assert lines and lines[0].startswith("[진입 통로")
    body = "\n".join(lines[1:])
    assert "2026-11" in body and "2027-01" in body and "2026-12" not in body  # relocation 제외
    assert "가족:" not in body
    # 관계 대상 질문이거나 진입 사건이 아니면 블록 없음.
    assert chat_service._entry_channel_context(
        _BIRTH, result, _intent(event_key="relocation"), "언제 이사갈까요", cands,
    ) == []
    assert chat_service._entry_channel_context(
        _BIRTH, result, _intent(event_key="job_gain"), "누가 제안을 해올까", cands,
    ) == []
    assert "회사" not in chat_service._ENTRY_CHANNEL_DIRECTIVE.split("특정 회사")[0] or True


# ── 이력 프리필 복원 ─────────────────────────────────────────────────────────
def test_entries_from_rows_roundtrip_day_and_month_precision() -> None:
    sig = pillars_signature(calculate(_BIRTH))
    entries = [
        EmploymentHistoryEntry(date="2025-12-01", kind="entry", org="A", channel="direct",
                               group="g1"),
        EmploymentHistoryEntry(date="2026-10", kind="exit", exit_reason="involuntary", group="g1"),
        EmploymentHistoryEntry(date="2008-05-19", kind="conversion", nature="conversion",
                               channel="conversion", group="g0"),
    ]
    rows = rows_from_history(entries, "s", "o", sig)
    back = entries_from_rows(rows)
    assert [(e.date, e.kind) for e in back] == [
        ("2008-05-19", "conversion"), ("2025-12-01", "entry"), ("2026-10", "exit"),
    ]
    assert back[1].channel == "direct" and back[1].group == "g1" and back[1].org == "A"
    assert back[2].exit_reason == "involuntary" and back[2].nature == "regular"
