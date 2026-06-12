"""Conversation Layer 엔진 (v2.2 Phase 4 T4.2~T4.4, docs/03 A0~A3 + docs/08 F).

턴 처리 순서(절대 원칙 7 — 대상 우선 확정):
  1. Subject Resolution(A0): 별칭/관계어/인라인/누적 참조/정정 발화 해소
  2. Question Linking(A3): 룰 우선 — 참조어 → follow-up, 단답+1슬롯 → 슬롯 상속
  3. Query Parser 호출(+상속 슬롯 병합) → 상태/엔티티 갱신
  4. 반복 감지(F7): 동일 질문 2회 이상 → 다른 각도 제시 신호

애매한 연속성의 LLM 분류기(T4.3 5순위)는 운영 연동 시 llm_client 경유로 추가한다 —
본 엔진은 룰 경로의 결정론을 보장한다.
"""

from __future__ import annotations

import re
from datetime import date

from saju_shared_types.conversation import (
    ConversationState,
    EntityType,
    LinkKind,
    LinkResult,
    ResultSummaryRef,
    SubjectResolution,
    TrackedEntity,
)
from saju_shared_types.intent import (
    Domain,
    ParsedMessage,
    QueryType,
    SubjectKind,
    SubjectMode,
    SubjectRef,
)

from .query_parser import _detect_domains, _parse_inline_births, parse_message

# 대상 정정(A10) — subject 교체 + 동일 intent 재실행.
_CORRECTION_RE = re.compile(r"헷갈려|헷갈렸|잘못\s*봤|다시\s*체크|아니\s.*사주")
# 본인 복귀(A8).
_SELF_RETURN_RE = re.compile(r"본인\s*사주로|내\s*사주로\s*봐")
# 생시 미상(A13).
_TIME_UNKNOWN_RE = re.compile(r"태어난\s*시간[은는]?\s*몰라|시간\s*모름")
# 누적 참조(F4) — "앞서 물어본 2명까지 포함".
_CUMULATIVE_RE = re.compile(r"앞서\s*물어본\s*(\d+)\s*명|이전에\s*물어본")
# 조건 추가(F3) / 세분화(F8).
_CONSTRAINT_RE = re.compile(r"간다면|한다면|이라면|쪽으로")
_DRILL_RE = re.compile(r"세부적으로|구체적으로|시기별로|자세히")


class ConversationEngine:
    """스레드 1개의 턴 처리기 — 상태는 호출 측이 보존/주입(저장소 분리)."""

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        """aliases: 별칭('1호'/'신랑') → companion_id 매핑(E14 — 학습분 포함)."""
        self._aliases = dict(aliases or {})

    # ── 공개 API ─────────────────────────────────────────────────

    def process_turn(
        self,
        state: ConversationState,
        text: str,
        today: date,
        birth_year: int | None = None,
    ) -> tuple[ParsedMessage, ConversationState, SubjectResolution, LinkResult]:
        """한 턴을 처리해 (파싱 결과, 갱신 상태, 대상 해소, 연속성)을 반환한다."""
        resolution = self.resolve_subjects(state, text)
        link = self.link_question(state, text)

        prev = state.last_intent if link.is_follow_up else None
        parsed = parse_message(text, today, prev_intent=prev, birth_year=birth_year)

        # 슬롯 상속 보강: 파서가 직접 상속 못 한 경우(참조어형) 도메인/대상 병합.
        for intent in parsed.intents:
            if link.is_follow_up and intent.domain is Domain.GENERAL and link.inherited_domain:
                intent.domain = link.inherited_domain
            if resolution.subjects:
                intent.subjects = resolution.subjects
                intent.subject_mode = resolution.subject_mode
            if resolution.correction:
                intent.query_type = QueryType.FEEDBACK_CORRECTION

        new_state = self._advance_state(state, text, parsed, resolution)
        return parsed, new_state, resolution, link

    # ── T4.4 Subject Resolution (A0) ─────────────────────────────

    def resolve_subjects(self, state: ConversationState, text: str) -> SubjectResolution:
        """대상 확정 — intent보다 먼저. 모호하면 추측하지 않고 unresolved로 표시."""
        correction = bool(_CORRECTION_RE.search(text))
        time_unknown = bool(_TIME_UNKNOWN_RE.search(text))

        subjects: list[SubjectRef] = []
        unresolved: list[str] = []

        # A8 — 본인 복귀.
        if _SELF_RETURN_RE.search(text):
            return SubjectResolution(
                subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
                subject_mode=SubjectMode.SINGLE,
                correction=correction,
            )

        # A9 — 별칭/번호: 매핑 테이블 조회(없으면 확인 질문 대상).
        for m in re.finditer(r"(\d+\s*호|신랑|아가)", text):
            alias = m.group(1).replace(" ", "")
            companion_id = self._aliases.get(alias)
            if companion_id:
                subjects.append(SubjectRef(
                    kind=SubjectKind.COMPANION, label=alias, companion_id=companion_id,
                ))
            else:
                unresolved.append(alias)

        # A6/A7 — 인라인 생년월일 → 임시 인물(Entity Tracking 등록은 상태 갱신에서).
        inline = _parse_inline_births(text)
        subjects += inline

        # F4 — 누적 참조: 이전 턴의 임시 인물을 집합으로 재호출.
        cumulative = _CUMULATIVE_RE.search(text)
        if cumulative:
            wanted = int(cumulative.group(1)) if cumulative.group(1) else None
            past_temps = [
                e for e in state.entities
                if e.type is EntityType.PERSON and e.attributes.get("kind") == "inline_temp"
            ]
            recall = past_temps[-wanted:] if wanted else past_temps
            for e in recall:
                subjects.append(SubjectRef(
                    kind=SubjectKind.INLINE_TEMP, label=e.label, entity_id=e.id,
                ))

        if not subjects and not unresolved:
            # 직전 턴 subject 상속, 그것도 없으면 self (A0 4순위).
            inherited = state.active_subjects or [
                SubjectRef(kind=SubjectKind.SELF, label="본인")
            ]
            subjects = list(inherited)

        mode = self._subject_mode(text, subjects, state)
        return SubjectResolution(
            subjects=subjects,
            subject_mode=mode,
            unresolved=unresolved,
            correction=correction,
            time_unknown=time_unknown,
        )

    @staticmethod
    def _subject_mode(
        text: str, subjects: list[SubjectRef], state: ConversationState
    ) -> SubjectMode:
        if re.search(r"나를\s*제외", text):
            return SubjectMode.COMPARE_EXCLUDE_SELF
        if re.search(r"누구야|순위|합이\s*좋은", text) and len(subjects) >= 2:
            return SubjectMode.RANKING
        if re.search(r"궁합|나랑\s*맞", text):
            return SubjectMode.PAIRWISE
        if re.search(r"둘\s*다|모두|종합해서", text) and len(subjects) >= 2:
            return SubjectMode.GROUP_AGGREGATE
        return state.last_intent.subject_mode if (
            state.last_intent and len(subjects) == len(state.last_intent.subjects)
            and subjects == state.last_intent.subjects
        ) else SubjectMode.SINGLE

    # ── T4.3 Question Linking (A3 — 룰 우선) ─────────────────────

    def link_question(self, state: ConversationState, text: str) -> LinkResult:
        """연속성 판별 — 룰 1~4순위(5순위 LLM 분류기는 운영 연동 시)."""
        if state.last_intent is None:
            return LinkResult(is_follow_up=False, link_kind=LinkKind.NEW)
        parent_id = state.last_intent.intent_id

        # 1순위 — 명시적 참조어/판정 인용 → follow-up 확정.
        if re.search(r"그\s*사람|그때|그\s*시기|이번\s*운|라고\s*했잖|그럼\s", text):
            kind = (
                LinkKind.CHALLENGE if re.search(r"했잖|아니야", text)
                else LinkKind.DOMAIN_SHIFT if _detect_domains(text)
                else LinkKind.TIME_SHIFT
            )
            return self._follow(parent_id, kind, state)

        # 2순위 — 단답(10자 이하) + 슬롯 1개만 → 교체상속(B2/B3).
        compact = text.replace(" ", "")
        if len(compact) <= 10:
            if re.search(
                r"\d{1,2}월|오늘|내일|모레|글피|올해|내년|이번\s*주"
                r"|[년연월주일]\s*단위",  # '년단위였어' — 직전 질문의 기간 단위 정정(2026-06-12)
                text,
            ):
                return self._follow(parent_id, LinkKind.TIME_SHIFT, state)
            if _detect_domains(text):
                return self._follow(parent_id, LinkKind.DOMAIN_SHIFT, state)
            if re.search(r"남편|아내|엄마|아빠|아들|딸|\d+호", text):
                return self._follow(parent_id, LinkKind.SUBJECT_SHIFT, state)

        # 3순위 — 조건 누적(F3) / 세분화(F8).
        if _CONSTRAINT_RE.search(text) and not _detect_domains(text):
            return self._follow(parent_id, LinkKind.CONSTRAINT_ADD, state)
        if _DRILL_RE.search(text) and len(compact) <= 20:
            return self._follow(parent_id, LinkKind.DRILL_DOWN, state)

        # 정정/이의(B9·A10) — challenge.
        if _CORRECTION_RE.search(text):
            return self._follow(parent_id, LinkKind.CHALLENGE, state)

        # 4순위 — 새로운 도메인+완결 질문 → 새 스레드 문맥.
        return LinkResult(is_follow_up=False, link_kind=LinkKind.NEW)

    @staticmethod
    def _follow(parent_id: str, kind: LinkKind, state: ConversationState) -> LinkResult:
        assert state.last_intent is not None
        return LinkResult(
            is_follow_up=True,
            parent_intent_id=parent_id,
            link_kind=kind,
            inherited_domain=state.last_intent.domain,
            inherited_subjects=state.last_intent.subjects,
        )

    # ── T4.2 Entity Tracking + 상태 전이 ─────────────────────────

    def _advance_state(
        self,
        state: ConversationState,
        text: str,
        parsed: ParsedMessage,
        resolution: SubjectResolution,
    ) -> ConversationState:
        """턴 종료 상태 — 엔티티 등록·반복 감지·활성 문맥 갱신."""
        turn = state.turn_no + 1
        intent = parsed.intents[0]
        entities = list(state.entities)

        # 인라인 임시 인물(A6/A7)은 반드시 Entity Tracking 등록 — 누적 참조(F4) 대비.
        known = {e.id for e in entities}
        for s in resolution.subjects:
            if s.kind is SubjectKind.INLINE_TEMP and s.inline_birth is not None:
                eid = s.entity_id or f"temp_{s.inline_birth.date.replace('-', '')}" + (
                    f"_{s.inline_birth.gender or 'u'}".lower()
                )
                if eid not in known:
                    entities.append(TrackedEntity(
                        id=eid, type=EntityType.PERSON, label=s.label,
                        source_turn=turn, source_role="user",
                        attributes={"kind": "inline_temp",
                                    "birth": s.inline_birth.model_dump()},
                    ))
                    known.add(eid)
        # 외부 일정 앵커(C11).
        if intent.time_range is not None:
            for a in intent.time_range.anchor_dates:
                eid = f"anchor_{a.date}"
                if eid not in known:
                    entities.append(TrackedEntity(
                        id=eid, type=EntityType.ANCHOR_DATE, label=a.label,
                        source_turn=turn, source_role="user",
                        attributes={"date": a.date},
                    ))
                    known.add(eid)

        # F7 — 동일 질문 반복 감지(정규화 비교).
        norm = re.sub(r"[\s?.!~ㅋㅎ]", "", text)
        repeat = state.repeat_count + 1 if norm == state.last_question_norm else 0

        return state.model_copy(update={
            "turn_no": turn,
            "active_subjects": resolution.subjects,
            "active_topic": intent.domain,
            "active_time_scope": (
                intent.time_range.start if intent.time_range else state.active_time_scope
            ),
            "active_event": intent.event_key or state.active_event,
            "last_intent": intent,
            "repeat_count": repeat,
            "last_question_norm": norm,
            "entities": entities,
        })

    # ── T4.5 claim 엔티티(시스템 답변 발) ─────────────────────────

    @staticmethod
    def register_system_results(
        state: ConversationState, summaries: list[ResultSummaryRef]
    ) -> ConversationState:
        """시스템 답변의 명리 판정/이벤트를 엔티티로 등록 — 수 턴 뒤 이의 재검산 대비."""
        entities = list(state.entities)
        known = {e.id for e in entities}
        for idx, s in enumerate(summaries):
            eid = f"claim_t{state.turn_no}_{idx}" if s.kind == "claim" else (
                f"{s.kind}_t{state.turn_no}_{idx}"
            )
            if eid in known:
                continue
            entities.append(TrackedEntity(
                id=eid,
                type=EntityType.CLAIM if s.kind == "claim" else EntityType.EVENT,
                label=s.label,
                source_turn=state.turn_no,
                source_role="assistant",
                attributes={"detail": s.detail},
            ))
        return state.model_copy(update={
            "entities": entities, "last_results": summaries,
        })
