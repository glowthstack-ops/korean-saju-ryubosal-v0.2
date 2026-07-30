"""관계 벡터 shadow chat 배선 — P1-6 §12 (RELATIONSHIP_EVENT_SYSTEM 부록 D).

엔진이 채점 중 수집한 **불변 projection**(탐지 재호출 0)을 어댑터(배우자궁·MT2)와
합성기에 걸어 기간 단위 Draft를 만들고, reducer 이후 legacy audit를 상세분에만
결합한다. 실행 계약(2026-07-24 승인):

Top-N 이전 Draft 생성 → 전체 aggregate 즉시 누적 → 상세 cap개만 보존 →
production reducer 실행 → 상세 Draft에만 audit/rank 결합 → Envelope finalize →
allowlist batch 1회 emit → sidecar 폐기.

원칙:
- **탐지 재호출·결과 변형 금지** — 입력은 RelationshipShadowProjection(primitive
  snapshot)뿐이고, natal 단위 분석(MT2 원국·구조 패턴)은 순수 함수 1회 호출이다.
- **join은 서명 기반 1건만**(§3 CandidateAuditIdentity) — event_key 단독 매칭
  금지: (subject, period, event_key, event_type) HMAC 서명이 같은 후보 1건만
  결합하고, 복수 매치는 JOIN_AMBIGUOUS로 fail-closed(추정 결합 없음).
- **pre_reduce_rank = production comparator 순위** — 별도 재정렬 없이 reducer에
  실제 입력된 목록의 순서(1-based)를 그대로 읽는다.
- 실패 격리: 기간 실패는 PeriodFailureReason 카운트, 요청 실패는 호출측
  try/except — 어느 쪽도 본 응답을 막지 않는다.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from saju_engines.event_engine_v2 import RelationshipShadowProjection
from saju_engines.marriage_emergence_modifier import analyze_marriage_emergence_natal
from saju_engines.partner_star_emergence import build_partner_star_emergence_evidence
from saju_engines.relationship_effect_vector import (
    RelationshipEffectVectorResult,
    synthesize_relationship_effect_vector,
)
from saju_engines.relationship_structure_modifiers import (
    build_relationship_structure_modifiers,
)
from saju_engines.spouse_palace_activation import (
    SpousePalaceHit,
    build_spouse_palace_vector,
)
from saju_engines.structure_patterns import detect_structure_patterns
from saju_shared_types.event_engine import Pillar4, RelationKind
from saju_shared_types.events import EventCandidate
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.relationship_effect import AxisStatus

from .relationship_vector_telemetry import (
    AuditProjectionStatus,
    BoundedDraftAccumulator,
    LegacyCandidateAudit,
    PeriodFailureReason,
    RelationshipEffectShadowDraft,
    RelationshipEffectShadowEnvelope,
    candidate_join_signature,
    finalize_shadow_envelope,
    vector_observation_id,
    vector_run_id,
)

logger = logging.getLogger(__name__)

# 감사 대상 관계 이벤트 키(P0-A 실측 3종) — M01/M02 canonical과 정합.
REL_AUDIT_EVENT_KEYS = ("marriage_signal", "new_relationship", "relationship_change")

# Pillar4.value → ManseV2Result.pillars 속성명(원국 참여자 글자 조회).
_PALACE_ATTR = {
    "year_pillar": "year", "month_pillar": "month",
    "day_pillar": "day", "hour_pillar": "hour",
}


@dataclass
class SidecarBuildResult:
    """Draft 생성 단계 산출 — bounded 누적기 + 기간 실패 카운트 + 계측."""

    accumulator: BoundedDraftAccumulator
    period_failure_counts: dict[str, int] = field(default_factory=dict)
    build_latency_ms: float = 0.0


def _natal_participant(result: ManseV2Result, palace: str, position: str) -> str:
    """활성이 자극한 원국 글자(한자) — pillars에서 결정적 조회(실패 시 빈 값)."""
    attr = _PALACE_ATTR.get(palace)
    pillars = result.pillars
    if attr is None or pillars is None:
        return ""
    pil = getattr(pillars, attr, None)
    if pil is None:
        return ""
    return str(pil.stem if position == "stem" else pil.branch)


def build_relationship_effect_accumulator(
    projections: tuple[RelationshipShadowProjection, ...],
    result: ManseV2Result,
    *,
    dictionaries_dir: Path,
    thread_scope: str,
    turn: int,
    subject_scope: str,
    input_signature: str,
) -> SidecarBuildResult:
    """projection → 어댑터·합성기 → Draft 생성 + aggregate 즉시 누적(Top-N 이전).

    Args:
        projections: 엔진 take_relationship_shadow() 산출(불변 snapshot).
        result: 채점에 쓰인 만세 결과 — natal 단위 순수 분석(MT2 원국·구조 패턴·
            참여자 글자 조회)에만 읽는다(변형 금지).
        dictionaries_dir: 어댑터 사전 루트(엔진과 동일 경로).
        thread_scope/turn/subject_scope/input_signature: observation identity 재료
            (§5 — HMAC digest에만 소비, 원문 미노출).

    Returns:
        bounded 누적기(aggregate 반영 완료·상세 후보만 보존) + 실패 카운트.
    """
    t0 = time.perf_counter()
    acc = BoundedDraftAccumulator()
    failures: dict[str, int] = {}

    def _fail(reason: PeriodFailureReason) -> None:
        failures[reason.value] = failures.get(reason.value, 0) + 1

    # natal 단위 순수 분석 1회 — 실패 시 전 기간 ADAPTER_FAILURE(부분 결손 은폐 금지).
    try:
        natal_mt2 = analyze_marriage_emergence_natal(result)
        # 구조 패턴은 natal 정적 — live 경로(context_reducer)와 동일한 순수 감지기를
        # 재호출한다(결정적·읽기 전용). 관계 소관 6종만 modifier로 변환된다.
        static_modifiers = build_relationship_structure_modifiers(
            detect_structure_patterns(result, dictionaries_dir=dictionaries_dir))
    except Exception:  # noqa: BLE001 — sidecar 실패는 본 응답 비차단(계측만)
        logger.exception("relationship_vector_sidecar natal 분석 실패")
        for _ in projections:
            _fail(PeriodFailureReason.ADAPTER_FAILURE)
        return SidecarBuildResult(
            accumulator=acc, period_failure_counts=failures,
            build_latency_ms=(time.perf_counter() - t0) * 1000.0)

    for proj in projections:
        try:
            vec = synthesize_period_vector(
                proj, result, natal_mt2, static_modifiers,
                dictionaries_dir=dictionaries_dir)
        except _AdapterError:
            _fail(PeriodFailureReason.ADAPTER_FAILURE)
            continue
        except _SynthesisError:
            _fail(PeriodFailureReason.SYNTHESIS_FAILURE)
            continue
        period_identity = f"{proj.layer}:{proj.label}"
        obs = vector_observation_id(
            thread_scope=thread_scope, turn=turn, subject_scope=subject_scope,
            period_identity=period_identity, input_signature=input_signature)
        acc.add(RelationshipEffectShadowDraft(
            observation_id=obs, vector_run_id=vector_run_id(obs),
            period_identity=period_identity, subject_scope=subject_scope,
            vector=vec))
    return SidecarBuildResult(
        accumulator=acc, period_failure_counts=failures,
        build_latency_ms=(time.perf_counter() - t0) * 1000.0)


class _AdapterError(Exception):
    """어댑터 단계(배우자궁·MT2) 실패 — 기간 격리용 내부 신호."""


class _SynthesisError(Exception):
    """합성기 단계 실패 — 기간 격리용 내부 신호."""


def synthesize_period_vector(
    proj: RelationshipShadowProjection,
    result: ManseV2Result,
    natal_mt2,  # MarriageEmergenceNatal
    static_modifiers: list,
    *,
    dictionaries_dir: Path,
    calibration=None,  # RelationshipVectorCalibration | None
    kind_bonus_scale: dict[str, float] | None = None,
) -> RelationshipEffectVectorResult:
    """한 기간 projection → 7축 벡터(어댑터·합성기, 순수). 실패는 단계별 예외.

    production 누적기와 deterministic 감사 harness가 공유하는 SSOT — 같은 벡터가
    두 경로에서 동일하게 나오도록 per-period 합성 로직을 한 곳에 둔다.
    """
    try:
        hits = [SpousePalaceHit(
            kind=RelationKind(a.kind), palace=Pillar4(a.palace),
            layer=a.layer, position=a.position,
            hap_subtype=a.hap_subtype, element=a.element,
            transit_component=a.position,
            # 운 글자 확보 — EXACT signal trigger(root 1개 판정 기준, P1-5 §1).
            transit_participant=(
                proj.luck_branch if a.position == "branch" else proj.luck_stem),
            natal_participant=_natal_participant(result, a.palace, a.position),
        ) for a in proj.activations]
        spa = build_spouse_palace_vector(
            hits, dictionaries_dir, period_key=proj.label)
        evidences = list(spa.evidences)
        blockers: list = []
        mt2 = build_partner_star_emergence_evidence(
            natal_mt2, proj.luck_stem, layer=proj.layer, period_key=proj.label,
            spouse_palace_clashed=proj.spouse_palace_clashed)
        evidences += mt2.evidences
        blockers += mt2.blocker_evidences
        # P2-1C-2/P2-1D 감사 hook — kind_base_bonus(S1) OAT: 대상 kind evidence의
        # base_relation_strength를 스케일(production은 None → 무변경).
        if kind_bonus_scale:
            evidences = [
                e.model_copy(update={
                    "base_relation_strength": round(
                        e.base_relation_strength * kind_bonus_scale[e.relation_kind], 6)})
                if e.relation_kind in kind_bonus_scale else e
                for e in evidences]
    except Exception as exc:  # noqa: BLE001 — 기간 격리(§2)
        raise _AdapterError from exc
    try:
        return synthesize_relationship_effect_vector(
            evidences, blockers=blockers, modifiers=static_modifiers,
            superseded_map=spa.superseded_map, calibration=calibration)
    except Exception as exc:  # noqa: BLE001
        raise _SynthesisError from exc


# ── beta 노출 신호(슬라이스 1 — 테스터용) ────────────────────────────────────
@dataclass(frozen=True)
class RelationshipBetaSignal:
    """한 기간의 관계 벡터 3축 요약(beta 노출 전용) — 평가된 3축만.

    activation/stability/separation만 노출한다. 미평가 4축(exposure·realization·
    experience·formalization)은 절대 포함하지 않는다(P3 증거 계약 전 — 성사/공식화
    판정 금지). band·부호 라벨만(원시 계수·간지 미노출).
    """

    layer: str
    label: str                          # '2027' / '2027-04'
    activation_band: str | None         # strong | moderate | weak | low
    stability_sign: str | None          # favorable | neutral | adverse
    separation_band: str | None         # strong | moderate | weak | low (미평가 None)


def _label_in_window(label: str, window: tuple[str, str] | None) -> bool:
    if window is None:
        return True
    start, end = window
    y = label[:4]
    return start[:4] <= y <= end[:4]


def build_relationship_beta_signals(
    projections: tuple[RelationshipShadowProjection, ...],
    result: ManseV2Result,
    *,
    dictionaries_dir: Path,
    window: tuple[str, str] | None = None,
    cap: int = 6,
) -> list[RelationshipBetaSignal]:
    """질문 창 기간의 관계 벡터 3축 요약(beta 노출). 실패는 빈 목록(비차단).

    production 경로는 이 함수를 RELATIONSHIP_BETA_EXPOSE 플래그가 켜질 때만 호출한다.
    벡터는 BASELINE 캘리브레이션(사람 감수 전 잠정값)으로 합성한다.
    """
    try:
        natal_mt2 = analyze_marriage_emergence_natal(result)
        static_modifiers = build_relationship_structure_modifiers(
            detect_structure_patterns(result, dictionaries_dir=dictionaries_dir))
    except Exception:  # noqa: BLE001 — beta 노출 실패는 본 응답 비차단
        logger.exception("relationship beta natal 분석 실패")
        return []
    out: list[RelationshipBetaSignal] = []
    for proj in projections:
        if not _label_in_window(proj.label, window):
            continue
        try:
            vec = synthesize_period_vector(
                proj, result, natal_mt2, static_modifiers,
                dictionaries_dir=dictionaries_dir)
        except Exception:  # noqa: BLE001 — 기간 실패 스킵
            continue
        act = vec.axes.activation
        if act.status is not AxisStatus.EVALUATED:
            continue  # 활성 미평가 기간은 노출 안 함(근거 없음≠약함)
        stab = vec.axes.stability
        sep = vec.axes.separation_pressure
        stab_sign = None
        if stab.status is AxisStatus.EVALUATED and stab.value is not None:
            stab_sign = ("favorable" if stab.value > 0
                         else "adverse" if stab.value < 0 else "neutral")
        out.append(RelationshipBetaSignal(
            layer=proj.layer, label=proj.label, activation_band=act.band,
            stability_sign=stab_sign,
            separation_band=(sep.band if sep.status is AxisStatus.EVALUATED
                             else None)))
    # 기간 라벨 정렬 후 중복 라벨 제거(같은 라벨 복수 층 방지) + cap.
    out.sort(key=lambda s: s.label)
    seen: set[str] = set()
    deduped: list[RelationshipBetaSignal] = []
    for s in out:
        if s.label in seen:
            continue
        seen.add(s.label)
        deduped.append(s)
    return deduped[:cap]


def _draft_period(draft: RelationshipEffectShadowDraft) -> str:
    """period_identity('sewoon:2027') → 후보 period 라벨('2027')."""
    return draft.period_identity.split(":", 1)[1]


class PeriodKeyedCandidate(Protocol):
    """rank 조회에 필요한 최소 계약 — `period` 와 `event_key` 뿐.

    `final_candidates` 는 실제로 이 두 필드만 읽는다(§7 읽기 전용). 그런데 호출부는
    reducer 이후 LLM payload(`LlmEventCandidate`)를 넘기고 여기 서명은 채점 DTO
    (`EventCandidate`)를 요구해 경계가 어긋나 있었다. 두 타입은 책임이 다르므로
    union 이나 `cast()` 로 봉합하지 않고, 이 함수가 실제로 요구하는 구조만 선언한다.

    읽기 전용 property 로 두어 공변이다 — `event_key` 가 StrEnum 이든 문자열이든
    `str` 계약을 만족한다(가변 속성으로 두면 불변성 때문에 둘 다 거부된다).
    """

    @property
    def period(self) -> str: ...

    @property
    def event_key(self) -> str: ...


def finalize_relationship_envelopes(
    detailed_drafts: list[RelationshipEffectShadowDraft],
    *,
    subject_scope: str,
    all_scored: list[EventCandidate],
    pre_reduce_candidates: list[EventCandidate],
    final_candidates: Sequence[PeriodKeyedCandidate],
) -> list[RelationshipEffectShadowEnvelope]:
    """reducer **이후** 상세 draft에만 legacy audit/rank를 결합해 finalize(§2·§3).

    Args:
        detailed_drafts: bounded 누적기의 상세 후보(HMAC 정렬 상위 cap).
        subject_scope: draft와 동일한 스코프 — join 서명 재료.
        all_scored: 채점 전체 목록(production comparator 정렬) — audit 값의 원천.
        pre_reduce_candidates: reducer에 실제 입력된 목록 — pre_reduce_rank는
            이 목록의 순서(1-based)다(별도 재정렬 금지). 창 필터로 빠진 기간의
            후보는 None(존재하지만 reduce 미입장).
        final_candidates: reducer 이후 Top-N(LLM payload와 동일) —
            selected_in_top_n/final_rank의 원천. **읽기 전용**(§7).
    """

    def _sig(period: str, cand: EventCandidate) -> str:
        return candidate_join_signature(
            subject_scope=subject_scope, period=period,
            event_key=str(cand.event_key), event_type=str(cand.event_type.value))

    envelopes: list[RelationshipEffectShadowEnvelope] = []
    for draft in detailed_drafts:
        period = _draft_period(draft)
        try:
            audits: list[LegacyCandidateAudit] = []
            ambiguous = False
            join_not_found = False
            joined_keys: set[str] = set()
            base = [c for c in all_scored
                    if c.period == period and str(c.event_key) in REL_AUDIT_EVENT_KEYS]
            # 서명 기반 1건 join(§3) — 같은 서명 복수 매치는 결합하지 않는다.
            by_sig: dict[str, list[EventCandidate]] = {}
            for c in base:
                by_sig.setdefault(_sig(period, c), []).append(c)
            for matches in by_sig.values():
                if len(matches) > 1:
                    ambiguous = True
                    continue
                c = matches[0]
                key = str(c.event_key)
                joined_keys.add(key)
                pre_rank = next(
                    (i + 1 for i, x in enumerate(pre_reduce_candidates)
                     if x.period == period and str(x.event_key) == key), None)
                final_rank = next(
                    (i + 1 for i, x in enumerate(final_candidates)
                     if x.period == period and str(x.event_key) == key), None)
                audits.append(LegacyCandidateAudit(
                    event_key=key, candidate_present=True,
                    pre_reduce_rank=pre_rank,
                    selected_in_top_n=final_rank is not None,
                    final_rank=final_rank,
                    score=float(c.score), raw_score=float(c.raw_total),
                    confidence=str(c.confidence.value),
                    # legacy DTO는 contributions를 보존하지 않는다 — 추정 금지(None).
                    relation_delta=None, relation_capped=None,
                ))
            # 최종 목록에만 있고 base 서명과 결합되지 않은 REL 후보 → identity 불일치.
            for x in final_candidates:
                if (x.period == period and str(x.event_key) in REL_AUDIT_EVENT_KEYS
                        and str(x.event_key) not in joined_keys):
                    join_not_found = True
            if ambiguous:
                status = AuditProjectionStatus.JOIN_AMBIGUOUS
            elif join_not_found:
                status = AuditProjectionStatus.JOIN_NOT_FOUND
            elif audits:
                status = AuditProjectionStatus.SUCCESS
            else:
                status = AuditProjectionStatus.NO_CANDIDATE
        except Exception:  # noqa: BLE001 — audit 실패는 벡터 실패가 아니다(§2)
            status = AuditProjectionStatus.PROJECTION_FAILURE
            audits = []
        envelopes.append(finalize_shadow_envelope(
            draft, audit_status=status, audits=tuple(audits)))
    return envelopes
