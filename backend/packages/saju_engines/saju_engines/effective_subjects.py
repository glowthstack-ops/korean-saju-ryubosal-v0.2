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
from saju_shared_types.intent import SubjectKind, SubjectRef

from .companion_alias import AliasEntry

_INJECTION_REASON = "P1 shadow only; P2 will enable subject_blocks"


@dataclass(frozen=True)
class AttachedCompanion:
    """FE 칩으로 첨부된 동반자(텍스트 지칭과 별개 경로). 등록/즉석 공용."""

    subject_id: str
    label: str
    relation_to_user: str | None = None


def _read_mode(self_present: bool, companion_count: int) -> CompanionReadMode:
    """대상 구성(본인 포함 여부 · 동반자 수)에서 공동 풀이 모드를 결정한다."""
    if companion_count == 0:
        return "self_only"
    if self_present and companion_count == 1:
        return "pairwise"
    if not self_present and companion_count == 1:
        return "companion_only"
    if not self_present and companion_count >= 2:
        return "compare_exclude_self"
    if self_present and companion_count >= 2:
        return "multi_with_self"
    return "unknown"


def build_effective_subjects(
    subjects: list[SubjectRef],
    base_subject_id: str | None,
    base_label: str = "본인",
    attached: list[AttachedCompanion] | None = None,
    companion_meta: dict[str, AliasEntry] | None = None,
) -> tuple[list[EffectiveSubject], CompanionReadMode, SubjectInjectionPolicy]:
    """해소된 대상 + 첨부 동반자 → (effective_subjects, mode, injection). 중복은 subject_id로 제거.

    Args:
        subjects: intent.subjects(P0 해소 결과 — self/companion/inline_temp).
        base_subject_id: 대화 기준(본인) 사주 id. self 대상의 subject_id로 쓴다.
        base_label: 본인 표시명.
        attached: FE 칩으로 첨부된 동반자(텍스트에 없어도 병합).
        companion_meta: subject_id → AliasEntry(관계·매칭 별칭 보강, 있으면).

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

    self_present = any(e.role == "self" for e in eff)
    companions = [e for e in eff if e.role != "self"]
    mode = _read_mode(self_present, len(companions))

    primary = self_id if self_present else (companions[0].subject_id if companions else None)
    targets = (
        [e.subject_id for e in companions] if mode == "compare_exclude_self"
        else [e.subject_id for e in eff]
    )
    injection = SubjectInjectionPolicy(
        mode=mode,
        primary_subject_id=primary,
        target_subject_ids=targets,
        companion_subject_ids=[e.subject_id for e in companions],
        requires_companion_chart=len(companions) >= 1,
        requires_relationship_context=mode in (
            "pairwise", "compare_exclude_self", "multi_with_self",
        ),
        execution_enabled=False,  # P1 shadow — P2에서 True 전환
        reason=_INJECTION_REASON,
    )
    return eff, mode, injection
