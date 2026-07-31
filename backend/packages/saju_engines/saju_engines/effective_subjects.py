"""대상 조합 계산 (동반자 공동 풀이 P1 — 계산/실행 분리).

P0가 해소한 대상(intent.subjects)과 FE 칩으로 첨부된 동반자(partner)를 병합해
effective_subjects를 만들고, 조합으로부터 CompanionReadMode와 SubjectInjectionPolicy를
자동 산출한다(사용자 지정 없음). P1은 계산·노출만 — 실행 전환(per_subject·subject_blocks)은
P2에서 execution_enabled를 켜며 수행한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from saju_shared_types.execution_plan import (
    CompanionReadMode,
    EffectiveSubject,
    SubjectInjectionPolicy,
)
from saju_shared_types.intent import SubjectKind, SubjectMode, SubjectRef

from .companion_alias import AliasEntry
from .query_parser import INTERPERSONAL_RELATIONS

_INJECTION_REASON = "P1 shadow only; P2 will enable subject_blocks"


@dataclass(frozen=True)
class AttachedCompanion:
    """FE 칩으로 첨부된 동반자(텍스트 지칭과 별개 경로). 등록/즉석 공용."""

    subject_id: str
    label: str
    relation_to_user: str | None = None


def _read_mode(self_present: bool, companion_count: int) -> CompanionReadMode:
    """공동 풀이 모드 결정 — 대상 구성(본인 포함 여부·동반자 수)으로 판정한다.

    PAIRWISE 암묵 self(궁합)는 build_effective_subjects의 self-삽입에서 이미 처리되므로, 여기서는
    구성만 본다. 본인 미포함: 1명=companion_only, 2명=compare_exclude_self, 3명 이상=ranking.
    본인 포함: 1명=pairwise, 2명 이상=multi_with_self(P3c-2 범위 밖).
    """
    if companion_count == 0:
        return "self_only"
    if self_present:
        return "pairwise" if companion_count == 1 else "multi_with_self"
    if companion_count == 1:
        return "companion_only"
    if companion_count == 2:
        return "compare_exclude_self"
    return "ranking"  # 동반자 3명 이상(본인 미포함) — 다자 비교


def build_effective_subjects(
    subjects: list[SubjectRef],
    subject_mode: SubjectMode,
    base_subject_id: str | None,
    base_label: str = "본인",
    attached: list[AttachedCompanion] | None = None,
    companion_meta: dict[str, AliasEntry] | None = None,
    self_implied: bool = False,
) -> tuple[list[EffectiveSubject], CompanionReadMode, SubjectInjectionPolicy]:
    """해소된 대상 + 첨부 동반자 → (effective_subjects, mode, injection). 중복은 subject_id로 제거.

    Args:
        subjects: intent.subjects(P0 해소 결과 — self/companion/inline_temp).
        subject_mode: intent.subject_mode(기존 실행 enum) — 모드 판정의 우선 신호.
        base_subject_id: 대화 기준(본인) 사주 id. self 대상의 subject_id로 쓴다.
        base_label: 본인 표시명.
        attached: FE 칩으로 첨부된 동반자(텍스트에 없어도 병합).
        companion_meta: subject_id → AliasEntry(관계·매칭 별칭 보강, 있으면).
        self_implied: 발화의 상호 술어로 본인이 암묵 포함되는가(query_parser.
            implies_self_counterpart). 칩으로만 첨부돼 발화에 상대 언급이 없으면
            _subject_mode가 동반자를 0명으로 보아 PAIRWISE로 올리지 못한다 — 그 경우를
            여기서 받는다.

    Returns:
        (effective_subjects, companion_read_mode, subject_injection). injection.execution_enabled은
        항상 False(P1 shadow) — 실행 전환은 P2가 켠다.
    """
    meta = companion_meta or {}
    eff: list[EffectiveSubject] = []
    seen: set[str] = set()

    def _add(es: EffectiveSubject) -> None:
        if es.subject_id in seen:
            return
        seen.add(es.subject_id)
        eff.append(es)

    self_id = base_subject_id or "self"
    for s in subjects:
        if s.kind is SubjectKind.SELF:
            _add(EffectiveSubject(
                subject_id=self_id, role="self", label=base_label or s.label, source="base",
            ))
        elif s.kind is SubjectKind.COMPANION and s.companion_id:
            m = meta.get(s.companion_id)
            _add(EffectiveSubject(
                subject_id=s.companion_id, role="companion", label=s.label,
                relation_to_user=m.relation_to_user if m else None,
                matched_alias=(s.label if m and m.source != "label" else None),
                source="text_alias",
            ))
        elif s.kind is SubjectKind.INLINE_TEMP:
            _add(EffectiveSubject(
                subject_id=s.entity_id or f"inline:{s.label}", role="inline_temp",
                label=s.label, source="text_inline",
            ))

    for a in attached or []:
        _add(EffectiveSubject(
            subject_id=a.subject_id, role="companion", label=a.label,
            relation_to_user=a.relation_to_user, source="chip",
        ))

    companions = [e for e in eff if e.role != "self"]
    self_present = any(e.role == "self" for e in eff)
    # 관계 유형이 대인 관계(연인·배우자 등)면 그 관계 자체가 '본인과의' 관계다 — 발화에
    # 상호 술어가 없어도 본인을 함께 봐야 한다. 칩으로만 첨부돼 텍스트에 언급이 없는 경우
    # (_subject_mode는 발화만 본다)를 여기서 받는다. 직장 관계는 제외 — 상대 단독 질문일
    # 수 있어 self를 끌어오면 대상이 뒤바뀐다.
    _relational = (
        len(companions) == 1
        and companions[0].relation_to_user in INTERPERSONAL_RELATIONS
    )
    # PAIRWISE + 동반자 1명은 본인↔동반자 — self를 암묵 포함(궁합). 2명 이상은 동반자끼리라 제외.
    if (
        (subject_mode is SubjectMode.PAIRWISE or _relational or self_implied)
        and not self_present and len(companions) == 1
    ):
        eff.insert(0, EffectiveSubject(
            subject_id=self_id, role="self", label=base_label or "본인", source="base",
        ))
        self_present = True
    mode = _read_mode(self_present, len(companions))

    primary = self_id if self_present else (companions[0].subject_id if companions else None)
    targets = (
        [e.subject_id for e in companions] if mode in ("compare_exclude_self", "ranking")
        else [e.subject_id for e in eff]
    )
    injection = SubjectInjectionPolicy(
        mode=mode,
        primary_subject_id=primary,
        target_subject_ids=targets,
        companion_subject_ids=[e.subject_id for e in companions],
        requires_companion_chart=len(companions) >= 1,
        requires_relationship_context=mode in (
            "pairwise", "compare_exclude_self", "ranking", "multi_with_self",
        ),
        execution_enabled=False,  # P1 shadow — P2에서 True 전환
        reason=_INJECTION_REASON,
    )
    return eff, mode, injection
