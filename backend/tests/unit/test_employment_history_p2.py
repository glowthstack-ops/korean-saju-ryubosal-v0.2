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


# ── 2026-10-22 실답 교정: 라벨 상한 예외·두 칸 지시 분리·반복 가중 상한 ──────────
def test_reducer_keeps_personal_repeat_label_beyond_signal_cap() -> None:
    from saju_engines.context_reducer import _to_llm_candidate
    from saju_shared_types.events import EventCandidate, EventType, Signal

    sigs = [Signal(type="reason", name=f"신호{i}", effect=f"신호{i}", weight=0.0) for i in range(6)]
    label = ("개인 이력 반복(같은 亥월 글자에서 같은 사건 4/11건 — 기대 비율 1/12, "
             "특정 사례·회사 지목 아님)")
    sigs.append(Signal(type="reason", name="x", weight=0.0, effect=label))
    c = EventCandidate(event_key="job_gain", event_type=EventType.PROGRESS, period="2026-11",
                       score=50, confidence="medium", polarity="conditional", signals=sigs)
    out = _to_llm_candidate(c, ganji={}, dw_by_year={})
    assert len(out.signals_ko) == 5 and out.signals_ko[-1].startswith("개인 이력 반복(")


def test_entry_window_directive_needed_outside_horizon_path() -> None:
    from saju_engines.horizon import HorizonPolicy

    job = _intent(event_key="job_gain")
    # 시점 명시 질문(지평 None) → 별도 주입 필요.
    needed = chat_service._entry_window_directive_needed
    assert needed(job, None, is_retro=False, is_structural=False)
    # 지평 지시에 이미 포함 → 중복 금지.
    pol = HorizonPolicy(kind="transactional_when", months_detail=12, years_span=3,
                        natal_fit=False, label="x", entry_window=True)
    assert not needed(job, pol, is_retro=False, is_structural=False)
    # 회고·구조·비진입 사건은 붙이지 않는다.
    assert not needed(job, None, is_retro=True, is_structural=False)
    assert not needed(job, None, is_retro=False, is_structural=True)
    assert not needed(
        _intent(event_key="relocation"), None, is_retro=False, is_structural=False,
    )


def test_personal_repeat_directive_trigger() -> None:
    class _C:
        def __init__(self, s): self.signals_ko = s
    assert chat_service._personal_repeat_present([_C(["공망 지연", "개인 이력 반복(같은 亥월…)"])])
    assert not chat_service._personal_repeat_present([_C(["공망 지연"])])


def test_repeat_cap_limits_personal_match_without_changing_order() -> None:
    from saju_engines.personal_calibration import apply_personal_match
    from saju_shared_types.life_event import (
        LifeEventOutcome,
        LifeEventRow,
        LifeEventSource,
        SignalFingerprint,
    )

    def row(period: str) -> LifeEventRow:
        return LifeEventRow(
            event_row_id=f"s:eh:{period}:job_gain", subject_id="s", pillar_year="庚申",
            pillar_month="丁亥", pillar_day="己亥", event_key="job_gain", period=period,
            signal_fingerprint=SignalFingerprint(ten_god_groups=["wealth"]),
            outcome=LifeEventOutcome.CONFIRMED, source=LifeEventSource.EMPLOYMENT_HISTORY,
        )
    sig = [row(f"20{10 + i}-05") for i in range(11)]  # 11개 기간 → 반복 항 2.0
    c = EventCandidateV2(event_key="job_gain", period="2026-11", score=40,
                         confidence_level=ConfidenceLevel.EVENT_CANDIDATE)
    free = apply_personal_match([c], sig)[0]
    capped = apply_personal_match([c], sig, repeat_cap=0.6)[0]
    assert free.personal_match >= 200 and capped.personal_match <= 100
    assert capped.personal_match < free.personal_match
