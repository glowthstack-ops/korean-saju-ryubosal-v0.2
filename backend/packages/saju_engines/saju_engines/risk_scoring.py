"""위험 점수 R1-a — 순수 점수 인프라 (doc/v2_2/RISK_ENGINE.md §5, 감수 26차 착수).

R0.5 원자 후보의 6축 `RiskScoreComponents`를 산출한다. **shadow 전용 인프라 차수**:
랭킹·사용자 노출·등급(risk_level) 산출을 하지 않으며, 다음이 1급 불변식이다
(데굴님 R1 착수 조건 — fixture 강제):

- **적격성 결과 불변**: eligibility_status·BLOCKED·INSUFFICIENT·suppression 대표·
  context-exposable 판정을 점수가 바꾸지 않는다(점수는 R0.5 판정을 뒤집지 않는다).
- **raw cause 1회 계산**: cause-level occurrence 기여는 (period, cause_atom)당 한 번
  계산되어 여러 후보가 참조한다 — 포트폴리오·episode 합산은 후보 합이 아니라
  `cause_occurrence_table`을 원천으로 써야 중복 가산이 없다.
- **서로 다른 관계 = 독립 원인**(같은 대상의 충+형=2), **같은 관계의 layer 반복 =
  원인 1 + layer_convergence 별도 진단**(occurrence 재합산 금지).
- **컨텍스트는 증거가 아님**: episode 존재·is_question_target·exposure CONFIRMED·
  stage 일치·selection_context_conflict는 occurrence에 일절 기여하지 않는다
  (exposure는 별도 축으로만).
- **기여 0 역할**: possible_trajectory·vulnerability·absorbed 후보·polarity
  amplifier(GI/GI_STRONG)·context conflict는 occurrence·독립 원인 수를 올리지
  않는다(TRIGGER 역할 근거만 occurrence 재료).
- **protection ≠ recovery**: protection 축은 현재 완충(실질 조건 동반 mitigator)만
  반영 — 미래 회복은 R2 recovery_window 소관(현재 점수 차감 금지).
- **포화 금지**: 6축 원값 보존 + 축별 cap + total은 마지막 한 번만
  (`risk_priority()` — raw와 capped를 함께 반환, 후보에 저장하지 않는다).

버전: 후보 생성·적격성·suppression 의미는 불변이므로 review environment는
r0.5.12 유지 — 점수 의미는 `RISK_SCORING_VERSION`이 별도로 추적하고, 감수 scope도
기존 shadow_structure를 해제하지 않고 shadow_scoring을 **추가**한다(R1-c).

가중치·매핑 상수는 전부 shadow 진단용 잠정값(감수 표본 대상 — R1-b/c에서 실측 후
데굴님 확정). exposure 상태 가중은 미입력을 사실 중간값으로 대체하는 것이 아니라
투명한 랭킹 정책 가중이다(UNKNOWN의 등급 상한 warning은 §5-1이 별도 강제).
"""

from __future__ import annotations

from collections.abc import Mapping

from saju_shared_types.risk_engine import (
    EvidenceRole,
    ExposureStatus,
    RiskCandidate,
    RiskScoreComponents,
)

from .risk_engine import cause_atoms

# 점수 의미 버전 — 축 정의·가중·매핑이 바뀌면 올린다(엔진 env 버전과 독립).
RISK_SCORING_VERSION = "risk-score-r1.0.0-shadow"

# exposure 상태 → 축 가중(잠정 — 감수 질문): CONFIRMED만 만점, DENIED는 하향
# (삭제 아님 — '현재 노출 없음' 보호), NOT_APPLICABLE은 스킵(0). UNKNOWN은
# 중간 사실이 아니라 '확인 전 랭킹 정책 가중'이며 §5-1 상한(warning)이 별도 적용.
_EXPOSURE_WEIGHT: dict[ExposureStatus, float] = {
    ExposureStatus.CONFIRMED: 1.0,
    ExposureStatus.UNKNOWN: 0.55,
    ExposureStatus.DENIED: 0.15,
    ExposureStatus.NOT_APPLICABLE: 0.0,
}
# persistence 정규화: 반복 기간 n → (n-1)/_PERSISTENCE_SPAN, cap 1.0 (반복 횟수만
# 반영 — 같은 신호 강도의 재합산 금지).
_PERSISTENCE_SPAN = 5
# compound: 같은 기간에 원인 원자를 공유하는 **별도의 다른 risk_id** 연결 1건당
# 가중(연쇄=복합 시나리오 재료), cap 1.0.
_COMPOUND_PER_LINK = 0.25
# confidence 휴리스틱(잠정): 기본 + 독립 원인 추가분 + 다층 수렴 관측.
_CONF_BASE, _CONF_PER_EXTRA_CAUSE, _CONF_LAYER = 0.4, 0.2, 0.2


def _trigger_cause_strengths(c: RiskCandidate) -> dict[str, float]:
    """TRIGGER 근거를 원인 사실(source) 단위로 축약 — evidence 1회 반영 불변식.

    같은 source(원인 사실)를 잡은 복수 룰은 최강 strength 1건으로만 반영한다.
    AMPLIFIER(극성 포함)·MITIGATOR·BLOCKER 역할은 occurrence 재료가 아니다.
    """
    out: dict[str, float] = {}
    for e in c.evidence:
        if e.role is not EvidenceRole.TRIGGER:
            continue
        out[e.source] = max(out.get(e.source, 0.0), e.strength)
    return out


def cause_occurrence_table(
    candidates: list[RiskCandidate],
) -> dict[tuple[str, str], float]:
    """(period_key, cause_atom) → 원인 단위 occurrence 기여(한 번만 계산).

    교차 도메인·교차 episode에서 같은 원인을 공유하는 후보들이 이 표의 같은 값을
    참조한다 — 포트폴리오 합산의 중복 가산 방지 원천(감수 17차 1회 계산 불변식).
    값은 그 원인을 잡은 전 후보 TRIGGER 근거의 최강 strength(결정적).
    """
    table: dict[tuple[str, str], float] = {}
    for c in candidates:
        for source, strength in _trigger_cause_strengths(c).items():
            for atom in cause_atoms(source):
                if atom.startswith("polarity:"):
                    continue  # 극성은 원인이 아니라 방향 — 기여 0 역할.
                key = (c.period_key, atom)
                table[key] = max(table.get(key, 0.0), strength)
    return table


def _occurrence(c: RiskCandidate) -> tuple[float, int, bool]:
    """후보 occurrence(0~1)·독립 원인 수·layer convergence 관측 여부.

    독립 원인 = source(원인 사실 서명) 단위 — 같은 대상의 충+형은 서명이 달라
    2개, 같은 관계의 다층 반복은 서명이 같아 1개(layer 문자열의 '+'로 수렴 관측만
    별도 보고). 결합은 포화형 1-Π(1-s): 원인이 늘수록 증가하되 100% 포화 금지.
    """
    strengths = _trigger_cause_strengths(c)
    if not strengths:
        return 0.0, 0, False
    acc = 1.0
    for s in strengths.values():
        acc *= 1.0 - min(1.0, max(0.0, s))
    layer_conv = any(
        "+" in e.layer for e in c.evidence if e.role is EvidenceRole.TRIGGER
    )
    return round(1.0 - acc, 6), len(strengths), layer_conv


def _protection(c: RiskCandidate) -> float:
    """현재 완충(0~1) — 실질 조건 동반 mitigator만(극성 단독 전역 완화 금지).

    미래 회복(recovery)은 여기 반영 금지 — R2 recovery_window 소관.
    """
    acc = 1.0
    seen: set[str] = set()
    for e in c.evidence:
        if e.role is not EvidenceRole.MITIGATOR or e.source in seen:
            continue
        if all(atom.startswith("polarity:") for atom in cause_atoms(e.source)):
            continue
        seen.add(e.source)
        acc *= 1.0 - min(1.0, max(0.0, e.strength))
    return round(1.0 - acc, 6)


def _candidate_atoms(c: RiskCandidate) -> frozenset[str]:
    return frozenset(a for a in c.trigger_cause_atoms
                     if not a.startswith("polarity:"))


def score_shadow(
    candidates: list[RiskCandidate],
    base_impact: Mapping[str, float],
) -> list[RiskCandidate]:
    """R0.5 후보 목록에 6축 점수·confidence를 채운 사본을 반환한다(순수 함수).

    score_components·confidence 외 어떤 필드도 변경하지 않는다(불변식 fixture가
    byte 비교로 강제). 입력 순서 보존·결정적.

    Args:
        candidates: R0.5 원자 후보(상태·억제 판정 완료본).
        base_impact: risk_id → 사전 baseImpact prior(0~1). 미등재는 0.0(관측 전용).

    Returns:
        점수 채운 후보 사본 목록(원본 불변).
    """
    # persistence 재료 — 같은 (risk_id + 전 축 episode 서명)의 반복 기간 수.
    period_sets: dict[tuple[str | None, ...], set[str]] = {}
    for c in candidates:
        period_sets.setdefault(_series_key(c), set()).add(c.period_key)
    # compound 재료 — 같은 기간·원인 원자를 공유하는 다른 risk_id 연결 수.
    atoms_by_period: dict[str, list[tuple[str, frozenset[str]]]] = {}
    for c in candidates:
        atoms_by_period.setdefault(c.period_key, []).append(
            (c.risk_id, _candidate_atoms(c)))

    out: list[RiskCandidate] = []
    for c in candidates:
        occ, n_causes, layer_conv = _occurrence(c)
        my_atoms = _candidate_atoms(c)
        linked_ids = {
            rid for rid, atoms in atoms_by_period.get(c.period_key, [])
            if rid != c.risk_id and (atoms & my_atoms)
        }
        n_periods = len(period_sets[_series_key(c)])
        components = RiskScoreComponents(
            occurrence=occ,
            impact=min(1.0, max(0.0, base_impact.get(c.risk_id, 0.0))),
            exposure=_EXPOSURE_WEIGHT[c.exposure_status],
            persistence=min(1.0, (n_periods - 1) / _PERSISTENCE_SPAN),
            compound=min(1.0, _COMPOUND_PER_LINK * len(linked_ids)),
            protection=_protection(c),
        )
        confidence = min(1.0, (
            _CONF_BASE
            + _CONF_PER_EXTRA_CAUSE * max(0, n_causes - 1)
            + (_CONF_LAYER if layer_conv else 0.0)
        )) if n_causes else 0.0
        out.append(c.model_copy(update={
            "score_components": components,
            "confidence": round(confidence, 6),
        }))
    return out


def _series_key(c: RiskCandidate) -> tuple[str | None, ...]:
    """persistence 반복 계열 키 — risk_id + 전 축 현실 대상 서명(episode 경계 유지)."""
    return (
        c.risk_id, c.selection_episode_id, c.mobility_episode_id,
        c.health_episode_id, c.legal_episode_id, c.relationship_target_id,
    )


def risk_priority(components: RiskScoreComponents) -> tuple[float, float]:
    """§5 공식의 (raw, capped) 우선도 — total은 여기서 마지막 한 번만 계산한다.

    raw = occurrence×impact×exposure + persistence + compound − protection.
    capped = raw를 [0, 1]로 clamp(포화 진단은 raw로, 소비는 capped로).
    후보에 저장하지 않는다 — 등급·선별은 R2 소관.
    """
    raw = (
        components.occurrence * components.impact * components.exposure
        + components.persistence + components.compound - components.protection
    )
    return round(raw, 6), min(1.0, max(0.0, round(raw, 6)))


__all__ = [
    "RISK_SCORING_VERSION",
    "cause_occurrence_table",
    "risk_priority",
    "score_shadow",
]
