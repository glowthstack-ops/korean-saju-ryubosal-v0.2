"""진행 사실 원천 통합 (P2-PROC-3) — 커리어 어댑터 + 3원천 병합.

설계: `doc/v2_2/REVIEW_ACTIVE_PROCESS_CONTRACT.md`

아직 EventScope를 바꾸지 않는다. 병합·우선순위·supersession 범위만 고정한다.
"""

from __future__ import annotations

from saju_engines.process_fact_resolver import adapt_career_fact, resolve_process_facts
from saju_shared_types.process_fact import (
    EvidenceOrigin,
    ProcessFamily,
    ProcessStage,
    ProcessStatus,
    SupersessionResult,
)

#: 커리어 (트랙, 단계) 값 — 이 리포의 CareerFactType/FACT_STAGE_MAPPING이 내는 값이다.
#: 테스트도 enum을 import하지 않는다(드리프트 가드와 같은 방향).
_INTERVIEW = ("opportunity", "interview")
_OFFER_ACCEPTED = ("opportunity", "agreement")
_APPLIED = ("opportunity", "application")
_NOTICE_GIVEN = ("exit", "notice_given")
_EXIT_COMPLETED = ("exit", "exited")
_JOINED = ("entry", "joined")


def _career(pair, episode_id="ep-A", subject_id="self", **over):
    track, stage_value = pair
    return adapt_career_fact(
        track, stage_value, episode_id=episode_id, subject_id=subject_id, **over
    )


# ── 커리어 어댑터 ────────────────────────────────────────────────


def test_career_fact_maps_to_track_family_and_stage() -> None:
    """기존 3트랙에 정렬한다 — 새 추상화를 만들지 않는다."""
    f = _career(_INTERVIEW)
    assert f is not None
    assert f.process_family is ProcessFamily.CAREER_OPPORTUNITY
    assert f.stage is ProcessStage.INTERVIEWING
    assert f.evidence_origin is EvidenceOrigin.CAREER_HARD_FACT_EPISODE
    assert f.is_usable_exception()


def test_exit_completed_is_terminal() -> None:
    """퇴사 완료는 종료 상태다."""
    f = _career(_EXIT_COMPLETED)
    assert f is not None
    assert f.process_family is ProcessFamily.CAREER_EXIT
    assert f.status is ProcessStatus.TERMINAL
    assert not f.is_usable_exception()


def test_entry_scope_is_preserved() -> None:
    """외부 이직과 내부 승진을 가르는 축을 잃지 않는다."""
    ext = _career(_JOINED, entry_scope="external_employer")
    internal = _career(_JOINED, entry_scope="internal_role")
    assert ext is not None and internal is not None
    assert ext.entry_scope != internal.entry_scope


def test_episode_id_becomes_instance_key() -> None:
    """episode_id가 supersession 범위를 정한다."""
    f = _career(_APPLIED, episode_id="ep-42")
    assert f is not None and f.process_instance_key == "ep-42"


def test_missing_subject_fails_closed() -> None:
    """주체가 없으면 본인으로 추정하지 않는다."""
    f = _career(_INTERVIEW, subject_id=None)
    assert f is not None and not f.is_usable_exception()


# ── 3원천 병합 ───────────────────────────────────────────────────


def test_current_turn_terminal_beats_ledger_active() -> None:
    """원장의 '이사 결정'보다 이번 턴의 '이사 취소'가 이긴다."""
    r = resolve_process_facts(
        current_turn_text="이번 이사는 취소했어.",
        ledger_quotes=["9월 30일에 이사가 결정되었어."],
        turn=3,
    )
    assert r.closed and r.closed[0][1] is (
        SupersessionResult.SUPERSEDED_SINGLE_ACTIVE_FAMILY
    )
    assert r.usable_for("self") == []


def test_ledger_active_survives_without_terminal() -> None:
    """종료 사실이 없으면 원장 사실은 살아남는다."""
    r = resolve_process_facts(
        ledger_quotes=["9월 30일에 이사가 결정되었어."], turn=3
    )
    usable = r.usable_for("self")
    assert len(usable) == 1
    assert usable[0].evidence_origin is EvidenceOrigin.LEDGER_EXPLICIT


def test_opportunity_completed_and_entry_active_coexist() -> None:
    """F9 — 한 문장의 terminal과 active가 서로 다른 family면 둘 다 유지된다.

    "11월에 합격해서 12월부터 다니는 중인데" — 채용 과정은 끝났고 입사는 진행 중이다.
    """
    r = resolve_process_facts(
        career_facts=[
            _career(_OFFER_ACCEPTED, episode_id="ep-A"),
            _career(_JOINED, episode_id="ep-A"),
        ],
    )
    families = {f.process_family for f in r.facts}
    assert families == {ProcessFamily.CAREER_OPPORTUNITY, ProcessFamily.CAREER_ENTRY}
    assert r.closed == []


def test_rejected_instance_does_not_close_other_instance() -> None:
    """A회사 결과가 B회사 결과 대기를 닫지 않는다."""
    a_reject = _career(_EXIT_COMPLETED, episode_id="ep-A")
    b_active = _career(_NOTICE_GIVEN, episode_id="ep-B")
    r = resolve_process_facts(career_facts=[a_reject, b_active])

    assert b_active in r.facts
    assert r.closed == []


def test_partner_fact_does_not_close_own_process() -> None:
    """동반자 사실이 본인 진행을 닫지 않는다."""
    mine = _career(_NOTICE_GIVEN, episode_id="ep-A")
    partner_exit = _career(
        _EXIT_COMPLETED, episode_id="ep-A", subject_id="partner-1"
    )
    r = resolve_process_facts(career_facts=[mine, partner_exit])

    assert mine in r.facts
    assert r.closed == []


def test_unsupported_domain_yields_nothing() -> None:
    """대출·연애·선발은 추출기가 없어 사실이 만들어지지 않는다."""
    r = resolve_process_facts(
        current_turn_text="대출 심사 중이고 소개팅 날짜도 잡혔어.", turn=1
    )
    assert r.facts == []
    assert r.usable_for("self") == []


def test_later_clause_active_survives_earlier_terminal() -> None:
    """같은 턴에서 앞 절의 종료가 뒤 절의 새 진행을 지우지 않는다.

    "이사를 마쳤어. 그런데 다른 집으로 다시 이사가 결정됐어" — 앞의 완료는 지난 건이고
    뒤의 결정은 새 건이다. 턴 우선순위만 보면 새 사실이 사라진다.
    """
    r = resolve_process_facts(
        current_turn_text="이사를 마쳤어. 그런데 다른 집으로 다시 이사가 결정됐어.",
        turn=2,
    )
    stages = {f.stage for f in r.facts}
    assert ProcessStage.IN_PROGRESS in stages, "뒤 절의 새 진행이 살아 있어야 한다"
    assert r.usable_for("self"), "예외 근거로도 쓸 수 있어야 한다"


# ── 요청 스코프 컨텍스트 (P2-3a) ─────────────────────────────────


def test_request_context_is_built_once_and_shared() -> None:
    """세 원천을 한 번에 읽어 불변 컨텍스트로 만든다."""
    from saju_engines.process_fact_resolver import build_request_process_context
    from saju_shared_types.process_fact import (
        CareerEntryScope,
        CareerProcessSnapshot,
    )
    from saju_shared_types.process_fact import (
        ProcessFamily as PF,
    )
    from saju_shared_types.process_fact import (
        ProcessStage as PS,
    )

    ctx = build_request_process_context(
        subject_id="self",
        current_turn_text="9월 30일에 이사가 결정되었어.",
        career_snapshots=[
            CareerProcessSnapshot(
                episode_id="ep-A", subject_id="self",
                process_family=PF.CAREER_OPPORTUNITY, stage=PS.INTERVIEWING,
                entry_scope=CareerEntryScope.EXTERNAL_EMPLOYER,
            )
        ],
        turn=2,
    )
    families = {f.process_family for f in ctx.usable()}
    assert families == {ProcessFamily.MOVE_PROCESS, ProcessFamily.CAREER_OPPORTUNITY}
    assert not ctx.source_unavailable


def test_request_context_marks_source_unavailable() -> None:
    """저장소 장애는 '사실 없음'이 아니다 — 컨텍스트가 구분해 전달한다."""
    from saju_engines.process_fact_resolver import build_request_process_context

    ctx = build_request_process_context(
        subject_id="self", career_source_unavailable=True
    )
    assert ctx.source_unavailable
    assert ctx.usable() == []


def test_snapshot_without_hard_fact_is_not_converted() -> None:
    """주관적 인상은 스냅샷이어도 변환하지 않는다."""
    from saju_engines.process_fact_resolver import build_request_process_context
    from saju_shared_types.process_fact import (
        CareerProcessSnapshot,
    )
    from saju_shared_types.process_fact import (
        ProcessFamily as PF,
    )
    from saju_shared_types.process_fact import (
        ProcessStage as PS,
    )

    ctx = build_request_process_context(
        subject_id="self",
        career_snapshots=[
            CareerProcessSnapshot(
                episode_id="ep-A", subject_id="self",
                process_family=PF.CAREER_OPPORTUNITY, stage=PS.INTERVIEWING,
                observable_hard_fact=False,
            )
        ],
    )
    assert ctx.usable() == []
