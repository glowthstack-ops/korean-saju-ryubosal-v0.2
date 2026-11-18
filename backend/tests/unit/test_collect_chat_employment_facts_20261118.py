"""채팅 입력 입퇴사 사실 수집기 — 절 판별·때 표현 해석 검증 (2026-11-18).

본인의 완료형 보고만 사실로 본다(가정·계획·부정·제3자 제외 — 사용자가 말한 사실만). 때 표현은
메시지 작성일 기준으로 옮기고, 미래 표현은 버린다. DB 는 건드리지 않는 순수 함수만 검증한다.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import collect_chat_employment_facts as C  # noqa: E402

_SAID = date(2026, 11, 18)


def test_only_own_completed_reports_are_facts() -> None:
    assert C.classify_clause("오늘 해고통보를 받았어") == ("exit", "involuntary")
    report_then_question = "나 해고당했는데 이제 다시 취직할 수 있을까"
    assert C.classify_clause(report_then_question) == ("exit", "involuntary")
    assert C.classify_clause("지난달에 퇴사했어") == ("exit", None)
    assert C.classify_clause("작년 3월에 입사했어") == ("entry", None)
    assert C.classify_clause("이직을 했는데 업무의 양이 많아") == ("move", None)
    assert C.classify_clause("카페에서 일한 지 3-4개월 정도 됐어") == ("entry", None)
    # 반례: 가정·걱정·계획·부정·제3자·질문은 사실이 아니다.
    for clause in (
        "해고 당할까 걱정돼", "해고당했으면 어땠을까", "퇴사할까 고민 중이야", "그냥 퇴사 하고싶어",
        "아직 이직 안 했어", "남편이 권고사직 당했어", "친구가 지난달 퇴사했어",
        "이직운이 언제 좋아", "내년에 이직하려고 해",
    ):
        assert C.classify_clause(clause) is None, clause


def test_stated_dates_resolve_against_the_message_date() -> None:
    r = C.resolve_stated_date
    assert r("2019년 3월 4일에 입사했어", _SAID) == C.ResolvedDate("2019-03-04", "day")
    assert r("2019년 3월에 입사했어", _SAID) == C.ResolvedDate("2019-03", "month")
    assert r("21년 11월에 퇴사했어", _SAID) == C.ResolvedDate("2021-11", "month")
    assert r("작년 3월에 입사했어", _SAID) == C.ResolvedDate("2025-03", "month")
    assert r("재작년에 퇴사했어", _SAID) == C.ResolvedDate("2024", "year")
    assert r("지난달에 퇴사했어", _SAID) == C.ResolvedDate("2026-10", "month")
    assert r("3년 전에 입사했어", _SAID) == C.ResolvedDate("2023", "year")
    assert r("두 달은 아니고 2개월 전에 그만뒀어", _SAID) == C.ResolvedDate("2026-09", "month")
    assert r("어제 퇴사했어", _SAID) == C.ResolvedDate("2026-11-17", "day")
    assert r("일한 지 3-4개월 정도 됐어", _SAID) == C.ResolvedDate("2026-08", "month")
    assert r("입사한 지 2년 됐어", _SAID) == C.ResolvedDate("2024", "year")
    # 연도 없는 달은 작성일 이전의 가장 가까운 그 달.
    assert r("9월에 퇴사했어", _SAID) == C.ResolvedDate("2026-09", "month")
    assert r("12월에 입사했어", _SAID) == C.ResolvedDate("2025-12", "month")
    # 1월 작성 — 지난달은 전년 12월.
    assert r("지난달에 퇴사했어", date(2026, 1, 10)) == C.ResolvedDate("2025-12", "month")
    # 반례: 때 표현 없음·미래·없는 날짜.
    assert r("이직을 했는데 일이 많아", _SAID) is None
    assert r("2027년 3월에 입사했어", _SAID) is None
    assert r("2025년 13월에 입사했어", _SAID) is None


def test_extract_splits_clauses_and_caps_quote() -> None:
    text = "작년 3월에 입사했어. 이번 달에 권고사직 통보를 받았어, 다시 취직할 수 있을까?"
    facts = C.extract_facts(text, _SAID)
    assert [(k, reason, d.text if d else None) for k, reason, d, _ in facts] == [
        ("entry", None, "2025-03"), ("exit", "involuntary", "2026-11"),
    ]
    long = "오늘 해고통보를 받았어" + "가" * 200
    assert all(len(q) <= 80 for *_, q in C.extract_facts(long, _SAID))
    assert C.extract_facts("이직운이 궁금해", _SAID) == []


# ── 원장 적재(2026-11-18 데굴님 "원장에 적재만 하고 채팅에서의 추가 액션은 없이 가자") ──────────
def _fact(mid: int, **kw) -> C.ChatEmploymentFact:
    base = dict(
        subject_id="s-self", owner_key="k", subject_label="본인", kind="entry", exit_reason=None,
        date="2026-03", precision="month", luck_month_label="2026-03", quote="…",
        message_id=mid, said_on="2026-06-15",
    )
    base.update(kw)
    return C.ChatEmploymentFact(**base)


def _subject(sid: str, kind: str, label: str):
    from saju_shared_types.birth_input import BirthInput
    from saju_shared_types.subject import SubjectRecord

    birth = BirthInput(
        birth_date=date(1990, 5, 5), birth_time="10:00", birth_place_name="서울", gender="male",
    )
    return SubjectRecord(subject_id=sid, owner_id="o1", kind=kind, label=label, birth=birth)


def test_load_plan_keeps_only_dated_own_chart_facts_without_canonical_overlap() -> None:
    from types import SimpleNamespace

    from saju_shared_types.life_event import LifeEventSource

    subjects = [_subject("s-self", "self", "지민"), _subject("s-comp", "companion", "남편")]
    canonical = [SimpleNamespace(
        source=LifeEventSource.EMPLOYMENT_HISTORY, event_key="resignation", period="2026-10",
    )]
    facts = [
        _fact(1),                                                    # 적재
        _fact(2, date=None, precision=None, luck_month_label=None),  # 때 없음
        _fact(3, date="2025", precision="year", luck_month_label=None),  # 연 단위
        _fact(4, subject_id="s-comp"),                               # 동반자 명식 스레드
        _fact(5, subject_id=None, subject_label="본인"),             # 명식 연결 없음
        _fact(6, subject_id=None, subject_label="지민", kind="move"),  # 이름이 같아도 미확정
        _fact(7, kind="exit", date="2026-10-13", precision="day", luck_month_label="2026-10"),
        _fact(8, subject_id="s-other"),                              # 그 계정 명식이 아님
    ]
    owners = {f.message_id: "o1" for f in facts}
    planned, skipped = C.plan_load(facts, owners, lambda _o: subjects, lambda _r: canonical)
    assert [(f.message_id, rec.subject_id) for f, rec in planned] == [(1, "s-self")]
    assert skipped == {
        C.SKIP_NO_DATE: 2, C.SKIP_NOT_SELF: 1, C.SKIP_NO_SUBJECT: 3, C.SKIP_CANONICAL: 1,
    }
    # 반례: 계정을 모르는 메시지는 대상을 확정하지 않는다.
    planned, skipped = C.plan_load([_fact(1)], {}, lambda _o: subjects, lambda _r: [])
    assert planned == [] and skipped == {C.SKIP_NO_SUBJECT: 1}


def test_subject_is_identified_by_bound_chart_not_by_label() -> None:
    """2026-11-18 데굴님 "동명인 경우도 많을 수 있으니 기본적으로는 사주 자체로 구분"."""
    only = [_subject("a", "self", "지민")]
    # 명식 연결이 없으면 이름이 같고 그 계정에 본인 명식이 하나뿐이어도 정하지 않는다.
    assert C.resolve_fact_subject(_fact(1, subject_id=None, subject_label="지민"), only) is None
    assert C.resolve_fact_subject(_fact(1, subject_id=None, subject_label="본인"), only) is None
    assert C.resolve_fact_subject(_fact(1, subject_id=None, subject_label=None), only) is None
    # 반례: 묶인 명식이 있으면 별명이 달라도·동명이 있어도 그 명식이다.
    twins = [_subject("a", "self", "지민"), _subject("b", "companion", "지민")]
    got = C.resolve_fact_subject(_fact(1, subject_id="b", subject_label="본인"), twins)
    assert got is not None and got.subject_id == "b"


def test_unbound_threads_are_grouped_by_thread_not_by_label() -> None:
    """명식 연결 없는 스레드의 묶음 단위는 스레드 — 같은 별명이라고 한 사람으로 세지 않는다."""
    a = _fact(1, subject_id=None, subject_label="본인", thread_key="t1")
    b = _fact(2, subject_id=None, subject_label="본인", thread_key="t2")
    c = _fact(3, subject_id="s-self", subject_label="본인", thread_key="t3")
    d = _fact(4, subject_id="s-self", subject_label="다른 별명", thread_key="t4")
    assert C.summarize([a, b, c, d]).startswith("사실 4건 · 대상 3명(subject_id 묶인 대상 1명)")


def test_chat_statement_row_is_idempotent_and_carries_no_text() -> None:
    from saju_engines.employment_history import chat_statement_row
    from saju_shared_types.life_event import SCORING_EXCLUDED_SOURCES, LifeEventSource

    sig = ("庚午", "辛巳", "甲子", "己巳", "male")
    kw = dict(subject_id="s1", owner_id="o1", pillars_sig=sig, message_id=42)
    row = chat_statement_row(
        kind="exit", stated_date="2026-10-13", precision="day", exit_reason="involuntary", **kw,
    )
    assert row is not None
    assert (row.event_key, row.period) == ("resignation", "2026-10")
    assert row.source is LifeEventSource.CHAT_STATEMENT
    assert str(row.source) in SCORING_EXCLUDED_SOURCES  # 점수·코호트에 쓰지 않는 소스
    assert row.attrs.source_ref == "chat_message:42" and row.attrs.label is None
    assert row.attrs.exit_reason == "involuntary" and row.attrs.event_date == date(2026, 10, 13)
    again = chat_statement_row(
        kind="exit", stated_date="2026-10-13", precision="day", exit_reason="involuntary", **kw,
    )
    assert again is not None and again.event_row_id == row.event_row_id  # 재실행 멱등
    move = chat_statement_row(
        kind="move", stated_date="2026-03", precision="month", exit_reason=None, **kw,
    )
    assert move is not None and move.event_key == "career_change"
    assert move.attrs.event_date is None and move.attrs.date_precision == "month"
    # 반례: 연 단위·모르는 종류는 행을 만들지 않는다(절기월 추측 금지).
    assert chat_statement_row(
        kind="entry", stated_date="2025", precision="year", exit_reason=None, **kw,
    ) is None
    assert chat_statement_row(
        kind="tenure", stated_date="2026-03", precision="month", exit_reason=None, **kw,
    ) is None
