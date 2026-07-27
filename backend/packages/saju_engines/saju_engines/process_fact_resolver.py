"""진행 사실 원천 통합 (P2-PROC-3) — 커리어 어댑터 + 3원천 병합.

설계: `doc/v2_2/REVIEW_ACTIVE_PROCESS_CONTRACT.md` · `REVIEW_PROCESS_FACT_PATTERNS.md`

세 원천을 하나의 `ProcessFact` 목록으로 정규화한다.

    1. 현재 발화 명시 사실   (rules-first 추출기)
    2. 원장 명시 사실         (동일 추출기를 원장 인용문에 적용)
    3. 커리어 hard-fact Episode (구조화된 객체 변환 — 정규식 불필요)

커리어는 텍스트 추출이 아니라 **이미 구조화된 객체의 변환**이라 여기 둔다. 다만
엔진 점수 경로가 커리어 모듈에 결합되면 안 되므로(`test_career_shadow_drift`),
이 모듈은 커리어 타입을 import하지 않고 **트랙·단계 문자열 값**만 받는다.
`FACT_STAGE_MAPPING` 조회와 `OBSERVABLE_HARD_FACT` 필터는 호출자(chat_service ·
report_service — 이미 inbound allowlist)가 한다.

이 단계는 아직 EventScope를 바꾸지 않는다 — 사건 family 호환 판정은 P2-2b다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from saju_shared_types.process_fact import (
    TERMINAL_STAGES,
    CareerProcessSnapshot,
    EvidenceOrigin,
    ProcessFact,
    ProcessFamily,
    ProcessStage,
    ProcessStatus,
    SubjectResolution,
    SupersessionResult,
    supersede,
    usable_active_facts,
)

from .process_fact_extractor import extract_process_facts

#: 커리어 트랙 값 → process family. 새 추상화를 만들지 않고 기존 3트랙에 정렬한다.
#: ⚠ enum이 아니라 **문자열 값**으로 받는다 — 엔진 점수 경로가 커리어 모듈에 결합되면
#: 안 된다는 드리프트 가드(`test_career_shadow_drift`)를 지키기 위해서다. 호출자
#: (chat_service·report_service — 이미 allowlist)가 enum→값 변환을 한다.
_TRACK_TO_FAMILY: dict[str, ProcessFamily] = {
    "opportunity": ProcessFamily.CAREER_OPPORTUNITY,
    "exit": ProcessFamily.CAREER_EXIT,
    "entry": ProcessFamily.CAREER_ENTRY,
}

#: 커리어 단계 값 → 공통 단계. 매핑에 없는 단계는 변환하지 않는다(추측 금지).
_STAGE_MAP: dict[str, ProcessStage] = {
    "contact": ProcessStage.APPLIED,
    "application": ProcessStage.APPLIED,
    "screening": ProcessStage.IN_REVIEW,
    "interview": ProcessStage.INTERVIEWING,
    "offer_received": ProcessStage.RESULT_PENDING,
    "offer_review": ProcessStage.NEGOTIATING,
    "negotiating": ProcessStage.NEGOTIATING,
    "agreement": ProcessStage.APPROVED,
    "notice_planned": ProcessStage.IN_PROGRESS,
    "notice_given": ProcessStage.NOTICE_GIVEN,
    "counteroffer": ProcessStage.NEGOTIATING,
    "handover": ProcessStage.IN_PROGRESS,
    "exited": ProcessStage.COMPLETED,
    "start_date_pending": ProcessStage.RESULT_PENDING,
    "start_date_fixed": ProcessStage.SCHEDULED,
    "contract_approved": ProcessStage.APPROVED,
    "joined": ProcessStage.ONBOARDING,
    "probation": ProcessStage.IN_PROGRESS,
    "stabilized": ProcessStage.COMPLETED,
}


def adapt_career_fact(
    track: str,
    stage_value: str,
    *,
    episode_id: str | None,
    subject_id: str | None,
    fact_type: str = "",
    original_text: str = "",
    entry_scope: str | None = None,
    source_turn: int | None = None,
) -> ProcessFact | None:
    """커리어 (트랙, 단계)를 공통 `ProcessFact`로 변환한다.

    호출자가 `FACT_STAGE_MAPPING`으로 사실 유형 → (트랙, 단계)를 먼저 풀고,
    `OBSERVABLE_HARD_FACT` 여부도 먼저 걸러야 한다 — 이 함수는 등급을 판정하지 않는다.

    Args:
        track: 커리어 트랙 값(`opportunity` / `exit` / `entry`).
        stage_value: 트랙별 단계 값(`interview` · `notice_given` 등).
        episode_id: 인스턴스 키. 없으면 terminal이 아무것도 닫지 못한다
            (커리어는 `INSTANCE_REQUIRED`).
        subject_id: 사실의 주체. None이면 `SubjectResolution.UNKNOWN`으로 남긴다.
        fact_type: 추적용 사실 유형 값(선택).
        original_text: 원문 보존.
        entry_scope: 외부 이직/내부 승진 구분(`EntryScope` 값).
        source_turn: 발화 턴.

    Returns:
        매핑 가능한 경우 `ProcessFact`, 아니면 None(추측해서 만들지 않는다).
    """
    family = _TRACK_TO_FAMILY.get(track)
    stage = _STAGE_MAP.get(stage_value)
    if family is None or stage is None:
        return None
    terminal = stage is ProcessStage.COMPLETED
    return ProcessFact(
        fact_id=f"career:{fact_type or stage_value}:{episode_id or '-'}",
        subject_id=subject_id,
        subject_resolution=(
            SubjectResolution.RESOLVED if subject_id else SubjectResolution.UNKNOWN
        ),
        process_family=family,
        stage=stage,
        status=ProcessStatus.TERMINAL if terminal else ProcessStatus.ACTIVE,
        entry_scope=entry_scope,
        process_instance_key=episode_id,
        evidence_origin=EvidenceOrigin.CAREER_HARD_FACT_EPISODE,
        original_text=original_text,
        rule_id=f"CAREER_ADAPT_{fact_type or stage_value}",
        source_turn=source_turn,
    )


def adapt_career_snapshot(snapshot: CareerProcessSnapshot) -> ProcessFact | None:
    """중립 스냅샷 → 공통 `ProcessFact`. **P2-2c 기본 경로다.**

    `adapt_career_fact`(문자열 입력)는 내부 호환 레이어로 남기고, 서비스 경계는 이
    함수를 쓴다 — 임의 문자열이 흩어지지 않게 한다.

    Args:
        snapshot: 커리어를 볼 수 있는 호출자가 만든 중립 스냅샷.

    Returns:
        `observable_hard_fact`가 아니면 None — 주관적 인상·상대 추측은 변환하지 않는다.
    """
    if not snapshot.observable_hard_fact:
        return None
    terminal = snapshot.stage in TERMINAL_STAGES
    return ProcessFact(
        fact_id=f"career:{snapshot.episode_id}:{snapshot.stage.value}",
        subject_id=snapshot.subject_id,
        subject_resolution=(
            SubjectResolution.RESOLVED if snapshot.subject_id
            else SubjectResolution.UNKNOWN
        ),
        process_family=snapshot.process_family,
        stage=snapshot.stage,
        status=ProcessStatus.TERMINAL if terminal else ProcessStatus.ACTIVE,
        entry_scope=snapshot.entry_scope.value if snapshot.entry_scope else None,
        process_instance_key=snapshot.episode_id,
        evidence_origin=EvidenceOrigin.CAREER_HARD_FACT_EPISODE,
        original_text=snapshot.original_text,
        rule_id="CAREER_SNAPSHOT",
        source_turn=snapshot.source_turn,
        source_order=snapshot.source_order,
        current=snapshot.current,
    )


@dataclass
class ResolvedProcessFacts:
    """통합 결과 — 살아남은 사실과 왜 닫혔는지."""

    facts: list[ProcessFact] = field(default_factory=list)
    closed: list[tuple[ProcessFact, SupersessionResult]] = field(default_factory=list)

    def usable_for(self, subject_id: str | None) -> list[ProcessFact]:
        """그 주체의 예외 근거로 쓸 수 있는 사실만."""
        return usable_active_facts(self.facts, subject_id=subject_id)


def resolve_process_facts(
    *,
    current_turn_text: str = "",
    ledger_quotes: list[str] | None = None,
    career_facts: list[ProcessFact] | None = None,
    subject_id: str | None = "self",
    turn: int | None = None,
) -> ResolvedProcessFacts:
    """세 원천을 병합하고 정책에 맞게 terminal supersession을 적용한다.

    우선순위는 현재 발화 > 원장 > Episode다(`supersede`가 출처 순위로 처리).
    다만 **다른 인스턴스·다른 주체·다른 entry_scope는 서로를 닫지 않는다.**

    Args:
        current_turn_text: 이번 턴 사용자 발화.
        ledger_quotes: 원장에 보존된 사용자 인용문.
        career_facts: `adapt_career_fact`로 이미 변환된 커리어 사실.
        subject_id: 화자 본인의 subject id.
        turn: 현재 턴 번호. 원장 사실은 이보다 앞선 턴으로 둔다.

    Returns:
        살아남은 사실과 종료 내역.
    """
    facts: list[ProcessFact] = []
    for e in extract_process_facts(
        current_turn_text, turn=turn, subject_id=subject_id
    ):
        if e.normalized_fact is not None:
            facts.append(e.normalized_fact)
    prior_turn = (turn - 1) if turn else None
    for quote in ledger_quotes or []:
        for e in extract_process_facts(
            quote, turn=prior_turn, subject_id=subject_id
        ):
            if e.normalized_fact is None:
                continue
            facts.append(e.normalized_fact.model_copy(update={
                "evidence_origin": EvidenceOrigin.LEDGER_EXPLICIT,
                "source_ledger_key": "user_facts",
            }))
    facts.extend(career_facts or [])
    survivors, closed = supersede(facts)
    return ResolvedProcessFacts(facts=survivors, closed=closed)
