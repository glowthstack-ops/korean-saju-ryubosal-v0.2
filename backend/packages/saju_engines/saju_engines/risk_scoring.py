"""위험 점수 R1-a — 순수 점수 인프라 (doc/v2_2/RISK_ENGINE.md §5, 감수 26차 착수).

R0.5 원자 후보의 6축 `RiskScoreComponents`를 산출한다. **shadow 전용 인프라 차수**:
랭킹·사용자 노출·등급(risk_level) 산출을 하지 않으며, 다음이 1급 불변식이다
(데굴님 R1 착수 조건 — fixture 강제):

- **적격성 결과 불변**: eligibility_status·BLOCKED·INSUFFICIENT·suppression 대표·
  context-exposable 판정을 점수가 바꾸지 않는다(점수는 R0.5 판정을 뒤집지 않는다).
- **raw cause 1회 계산**: cause-level occurrence 기여는 (period, cause_atom)당 한 번
  계산되어 여러 후보가 참조한다 — 포트폴리오·episode 합산은 후보 합이 아니라
  `cause_occurrence_table`을 원천으로 써야 중복 가산이 없다.
- **cause identity 계약(감수 26차 확정)**: 관계 원자는 매처가 사실 기반으로 만든
  완전한 canonical 서명이다 — `relation:<종류>:<궁위>:<자리>[:<글자>][:<십성>]`에
  **target_object_signature가 내장**되어, 같은 관계 종류라도 대상이 다르면 서로
  다른 원자(원인 2), 같은 대상의 다른 관계도 다른 원자(원인 2), 같은 대상·같은
  관계의 다층 반복은 같은 원자(원인 1 — layer는 서명 밖, 수렴 진단만)다. 같은
  사실을 재표현한 복수 룰은 매처가 같은 source 서명을 만들므로 root-fact 기준
  dedup이 자동 성립한다(fixture 고정).
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
    is_exposable,
)

from .risk_engine import cause_atoms

# 점수 의미 버전 — 축 정의·가중·매핑이 바뀌면 올린다(엔진 env 버전과 독립).
RISK_SCORING_VERSION = "risk-score-r1.2.2-shadow"

# exposure 축 = **rankable 가중**(감수 26차 확정 — 정책별 분리, 전 항목 공통값
# 금지): 노출 게이트(is_exposable)를 통과하지 못한 후보는 0 — DENIED(명시 부정)·
# NOT_APPLICABLE·confirmed_required+UNKNOWN·CONTEXT_CONFLICT·vulnerability(단독
# 노출 없음) 전부 ranking 대상 아님(구조 진단은 structural_priority가 exposure
# 없이 별도 제공 — DENIED의 counterfactual 진단도 그쪽). 통과 후보만:
# CONFIRMED=1.0, UNKNOWN(required_for_warning 등 조건부 허용 항목)=0.55(잠정 —
# 사실 중간값이 아니라 랭킹 정책 가중, §5-1 상한 warning 별도 강제).
_EXPOSURE_CONFIRMED, _EXPOSURE_UNKNOWN_RANKABLE = 1.0, 0.55
# persistence 정규화(감수 26차 확정 — 단순 반복 횟수 아님): 같은 계열(risk_id+
# episode 서명)의 **최장 연속 구간(longest contiguous run)** n → (n-1)/SPAN,
# cap 1.0. 간헐 반복(1·6·11월)은 연속 3개월과 다르다. 월운 라벨이 있으면 월
# 연속만 계산하고 그 달들을 포함하는 연운 라벨은 별도 기간이 아니라 layer
# convergence로 본다(기간 중복 계산 금지). 신호 강도 재합산 금지. total/gap-
# adjusted 비교 지표는 R1-b 측정에서 병행 출력(잠정 기본=contiguous run).
_PERSISTENCE_SPAN = 5
# compound(감수 26→32차): 독립 exposable 효과(role 상이·resolved)만. 증분은
# 감수 32차에서 **0.25 기각** — 0.10을 보수적 shadow 잠정값으로 두고 taxonomy·
# ByContext 정리 후 재측정으로 확정한다(민감도 표 병행 출력). role 1건당, cap 1.0.
_COMPOUND_PER_LINK = 0.10
# 대운 교운기 modifier(감수 36차 — R1-T): 교운기는 새 원인·노출·persistence가
# 아니라 이미 성립한 사건 구조의 **시점 활성도 modifier**다. 커널은 이벤트 엔진의
# daewoon_transition_weight를 단일 SSOT로 공유(복제 금지 — exp(-(d/365)^1.0)
# 라플라스형, MIN 0.05 게이트 동일). 적용: timed_base = base × (1 + weight ×
# 민감도 계수 × MAX_BONUS). base=0·비노출·BLOCKED는 교운기로 부활 불가(곱 구조).
# 계수·MAX_BONUS=0.20 **확정**(감수 39차 — R2-b episode 기준 0.20/0.30 판정
# 동일 → "같은 episode 결과면 더 작은 modifier" 원칙, 0.30은 비교 기록만).
# 교운일 최대 보정: high +20% · medium +12% · low +5% · none 0%.
# cause table 진입 금지 — 교운 원자는 존재하지 않는다(fail-closed namespace).
_TRANSITION_SENSITIVITY_COEF = {"none": 0.0, "low": 0.25, "medium": 0.6,
                                "high": 1.0}
_TRANSITION_MAX_BONUS = 0.20
# protection 하드 상한(감수 33차): 보호는 위험을 크게 완화할 수 있지만, 구조와
# 현실 노출을 통과한 후보의 존재 자체를 삭제할 수 없다 — protection=1.0으로
# rankable이 0이 되는 경로 차단(positive base + 최대 보호 → rankable > 0 fixture).
_PROTECTION_CAP = 0.70
# confidence 휴리스틱(잠정): 기본 + 독립 원인 추가분 + 다층 수렴 관측.
_CONF_BASE, _CONF_PER_EXTRA_CAUSE, _CONF_LAYER = 0.4, 0.2, 0.2


# ── occurrence 의미 registry(감수 28차 — R1-c0) ────────────────────
# canonical identity(원자를 고유 식별)와 **occurrence 적격성**(발생 원인으로 점수에
# 들어가도 되는가)은 다른 문제다. 시점 상태·비공망·운성 같은 보조 조건까지 원인으로
# 계산하면 점수는 결정적이어도 의미적으로 잘못된다(데굴님 확정):
#   relation:*  → CAUSE(target 내장 canonical — 사건 구조의 원인)
#   ten_god:*   → CAUSE(운 유입 사실 — 같은 십성의 layer·source 반복은 같은
#                 semantic cause 1개, supporting layer/convergence로만 누적)
#   void        → CONDITIONAL_CAUSE(일반 공망 상태 단독=원인 아님 — 같은 source에
#                 CAUSE 원자가 동반된 감수 룰에서만 그 원인의 조건으로 작동.
#                 독립 cause row·독립 원인 수 증가 금지)
#   no_void     → GATE_OR_PROTECTION(비공망 상태 — 원인 아님, 기여 0)
#   stage:*     → ACTIVATION_OR_CONFIDENCE(12운성 시점 상태 — 작동 조건·강도
#                 보조. occurrence source row 생성 금지, confidence 보조는 예약)
#   polarity:*  → AMPLIFIER(방향 신호 — 진입 금지)
# 미상 namespace는 조용한 과소/과대 dedup을 막기 위해 거부(fail-closed).
_SEM_CAUSE = "cause"
_SEM_CONDITIONAL = "conditional_cause"
_SEM_GATE = "gate_or_protection"
_SEM_ACTIVATION = "activation_or_confidence"
_SEM_AMPLIFIER = "amplifier"
# cause 정규화 의미 버전 — registry 분류가 바뀌면 올린다(감수 hash 재료).
CAUSE_SEMANTICS_VERSION = "cause-semantics-v3"


def atom_semantics(atom: str) -> str:
    """원자 → occurrence 의미 분류(미상 namespace는 ValueError — fail-closed)."""
    if atom.startswith("relation:") or atom.startswith("ten_god:"):
        return _SEM_CAUSE
    if atom == "void":
        return _SEM_CONDITIONAL
    if atom == "no_void":
        return _SEM_GATE
    if atom.startswith("stage:"):
        return _SEM_ACTIVATION
    if atom.startswith("polarity:"):
        return _SEM_AMPLIFIER
    raise ValueError(
        f"canonical cause 계약 위반 — 미상 namespace 원자: {atom!r} "
        f"(occurrence 의미 registry 등재·감수 후 사용)"
    )


def normalized_effect_role(c: RiskCandidate) -> str:
    """후보의 현실 효과 role — **사전 SSOT**(normalizedEffectRole, 감수 31차).

    compound '서로 다른 현실 효과' 판정·교차 도메인 dedup의 어휘. scoring 코드
    registry는 사전 필드로 이관·삭제됨(사전 lint가 감수 승격 항목의 role 존재·
    enum·kind 혼동 금지를 강제, 값 변경=shadow_scoring scope 자동 강등). 미등재
    (합성 후보 등)는 risk_family fallback — 독립 효과 주장에 쓰이지 않도록
    fail-closed(episode 미해결 제외)와 병행된다.
    """
    return c.normalized_effect_role or c.risk_family or c.risk_id


def _cause_atoms_of_source(source: str) -> frozenset[str]:
    """source의 occurrence 적격(CAUSE) 원자만 — 보조 조건은 원인이 아니다."""
    return frozenset(
        a for a in cause_atoms(source) if atom_semantics(a) == _SEM_CAUSE
    )


def _trigger_cause_strengths(c: RiskCandidate) -> dict[str, float]:
    """TRIGGER 근거를 원인 사실(source) 단위로 축약 — evidence 1회 반영 불변식.

    같은 source(원인 사실)를 잡은 복수 룰은 최강 strength 1건으로만 반영한다.
    AMPLIFIER(극성 포함)·MITIGATOR·BLOCKER 역할은 occurrence 재료가 아니다.
    """
    out: dict[str, float] = {}
    for e in c.evidence:
        if e.role is not EvidenceRole.TRIGGER:
            continue
        if not _cause_atoms_of_source(e.source):
            # CAUSE 원자가 없는 source(순수 공망·비공망·운성 상태) — 발생
            # 원인이 아니다(semantic registry, 감수 28차). 독립 원인 수·
            # occurrence에 진입 금지(작동 조건·확신 보조는 별도 축 예약).
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
                # 전 원자 namespace 검증(미상=raise) 후 CAUSE 의미만 row 생성 —
                # void/no_void/stage/polarity는 원인 표가 아니라 보조 축 소관.
                if atom_semantics(atom) != _SEM_CAUSE:
                    continue
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
    return round(min(_PROTECTION_CAP, 1.0 - acc), 6)


def _candidate_atoms(c: RiskCandidate) -> frozenset[str]:
    """후보의 occurrence 적격(CAUSE) 원인 원자 — compound 연결·lineage 재료."""
    return frozenset(a for a in c.trigger_cause_atoms
                     if atom_semantics(a) == _SEM_CAUSE)


def score_shadow(
    candidates: list[RiskCandidate],
    base_impact: Mapping[str, float],
    transition_weights: Mapping[str, float] | None = None,
) -> list[RiskCandidate]:
    """R0.5 후보 목록에 6축 점수·confidence를 채운 사본을 반환한다(순수 함수).

    score_components·confidence 외 어떤 필드도 변경하지 않는다(불변식 fixture가
    byte 비교로 강제). 입력 순서 보존·결정적.

    Args:
        candidates: R0.5 원자 후보(상태·억제 판정 완료본).
        base_impact: risk_id → 사전 baseImpact prior(0~1). 미등재는 0.0(관측 전용).
        transition_weights: period_key → 교운기 커널 가중(이벤트 엔진
            daewoon_transition_weight 산출값 — SSOT). None/미등재=보정 없음
            (기존 결과 byte 불변). MIN 0.05 미만 값은 무시.

    Returns:
        점수 채운 후보 사본 목록(원본 불변).
    """
    # persistence 재료(감수 29차 — **개별 cause lineage**): 원인 하나가 유지되는
    # 한 보조 원인의 추가·제거({A}→{A,B}→{A})로 지속성이 끊기지 않는다 — lineage
    # 키 = (risk_id, 연결 episode 서명, canonical cause_atom 1개). 후보 persistence
    # = 자신을 지지한 원인 lineage 중 최장 연속 run. native gate(감수 27차 —
    # 직렬화 구분)는 유지: 월 기간은 월운/일운 발동, 연 기간은 세운 발동만 지속.
    # 전체 원인 묶음 연속(trigger_bundle_contiguous_runs)·효과 연속(effect_
    # contiguous_runs)은 진단 전용 — 점수 키로 쓰지 않는다.
    cause_period_sets: dict[tuple, set[str]] = {}
    for c in candidates:
        if not _has_period_native_trigger(c):
            continue
        for atom in _candidate_atoms(c):
            cause_period_sets.setdefault(
                (c.risk_id, _episode_signature(c), atom), set(),
            ).add(c.period_key)
    rankable_links = compound_family_links(candidates, exposable_only=True)

    out: list[RiskCandidate] = []
    for idx, c in enumerate(candidates):
        occ, n_causes, layer_conv = _occurrence(c)
        # compound(감수 26차) = rankable 연결 — 원인을 공유하는 다른 primary
        # effect family의 독립 exposable 후보만(같은 family=alias·파생, 비노출·
        # 흡수=복합 위험 아님). exposure 무관 구조 연결은 compound_family_links(
        # exposable_only=False)가 별도 진단으로 제공(structural_priority는 이
        # 축을 아예 제외 — exposability가 구조 진단에 새는 것 차단, 감수 27차).
        linked_families = rankable_links[idx]
        run = max((
            _longest_contiguous_run(cause_period_sets.get(
                (c.risk_id, _episode_signature(c), atom), set()))
            for atom in _candidate_atoms(c)), default=0)
        components = RiskScoreComponents(
            occurrence=occ,
            impact=min(1.0, max(0.0, base_impact.get(c.risk_id, 0.0))),
            exposure=_exposure_weight(c),
            persistence=min(1.0, max(0.0, (run - 1) / _PERSISTENCE_SPAN)),
            compound=min(1.0, _COMPOUND_PER_LINK * len(linked_families)),
            protection=_protection(c),
        )
        t_weight = (transition_weights or {}).get(c.period_key, 0.0)
        if t_weight < 0.05:  # 이벤트 엔진 MIN_WEIGHT와 동일 게이트
            t_weight = 0.0
        transition_bonus = round(
            t_weight
            * _TRANSITION_SENSITIVITY_COEF.get(c.transition_sensitivity, 0.0)
            * _TRANSITION_MAX_BONUS, 6)
        confidence = min(1.0, (
            _CONF_BASE
            + _CONF_PER_EXTRA_CAUSE * max(0, n_causes - 1)
            + (_CONF_LAYER if layer_conv else 0.0)
        )) if n_causes else 0.0
        out.append(c.model_copy(update={
            "score_components": components,
            "confidence": round(confidence, 6),
            "transition_bonus": transition_bonus,
        }))
    return out


def compound_family_links(
    candidates: list[RiskCandidate],
    *,
    exposable_only: bool,
) -> list[set[str]]:
    """후보별 compound 연결 family 집합(입력 순서 정렬 반환).

    연결 = 같은 기간 + 원인 원자 공유 + **다른 primary effect family** + 미흡수.
    exposable_only=True(=rankable compound — components.compound 재료)는 여기에
    is_exposable 통과를 추가로 요구한다. False(=structural compound — 구조 연결
    진단·R1-b 측정 전용)는 exposure 무관: 같은 구조에서 노출 상태만 바뀌어도
    구조 연결 수는 변하지 않는다(감수 27차 — exposability의 구조 진단 누수 차단).
    """
    links_by_period: dict[str, list[tuple]] = {}
    for c in candidates:
        links_by_period.setdefault(c.period_key, []).append((
            c.risk_id, normalized_effect_role(c), _candidate_atoms(c),
            bool(_episode_signature(c)),  # effect identity RESOLVED 여부
            c.suppressed_by_specificity is None
            # rankable 연결의 노출 판정은 _exposure_weight와 동일 기준(DENIED/
            # NOT_APPLICABLE 상태 방어 포함) — 축 간 기준 불일치 방지.
            and (not exposable_only or _exposure_weight(c) > 0.0),
        ))
    out: list[set[str]] = []
    for c in candidates:
        my_atoms = _candidate_atoms(c)
        my_role = normalized_effect_role(c)
        my_resolved = bool(_episode_signature(c))
        out.append({
            role for rid, role, atoms, resolved, independent in (
                links_by_period.get(c.period_key, []))
            if independent and rid != c.risk_id and (atoms & my_atoms)
            # compound = **서로 다른 normalized effect role**의 개수(감수 29차):
            # 같은 role은 family·도메인·episode 수와 무관하게 같은 현실 효과의
            # 복제/반복 폭이다(폭은 R2 breadth 소관 — compound 아님).
            and role != my_role
            # effect identity 미해결(episode-free)은 독립 효과를 증명할 수 없다
            # — fail-closed: compound 제외(진단은 compound_unresolved_counts).
            and resolved and my_resolved
        })
    return out


def compound_unresolved_counts(candidates: list[RiskCandidate]) -> list[int]:
    """effect identity 미해결로 compound에서 제외된 원인 공유 연결 수(진단).

    episode-free 후보끼리(또는 한쪽이 episode-free) 원인·role 상이 조건은 맞지만
    독립 효과를 증명할 수 없어 0 처리된 연결 — R1-c1 unresolved_effect_identity
    지표 재료(사전 role 편입·episode 공급 확충의 우선순위 판단).
    """
    rows = [(c.risk_id, normalized_effect_role(c), _candidate_atoms(c),
             bool(_episode_signature(c)), c.period_key) for c in candidates]
    out: list[int] = []
    for rid, role, atoms, resolved, period in rows:
        out.append(sum(
            1 for orid, orole, oatoms, oresolved, operiod in rows
            if operiod == period and orid != rid and (oatoms & atoms)
            and orole != role and not (resolved and oresolved)
        ))
    return out


def _layer_tokens(layer: str) -> set[str]:
    """근거 layer 표기('daewoon+sewoon', 'sewoon&period' 등) → 토큰 집합."""
    return {tok for part in layer.split("&") for tok in part.split("+")}


def _has_period_native_trigger(c: RiskCandidate) -> bool:
    """기간 granularity에 맞는 native 발동 trigger가 있는가(직렬화 구분).

    월 기간('YYYY-MM')=월운/일운 발동, 연 기간('YYYY')=세운 발동. 그 외 라벨
    (대운 등)은 보수적으로 native 취급. 상위 layer 원인만으로 구성된 하위 기간
    후보는 같은 사실의 직렬화 — persistence 지속 근거가 아니다.
    """
    if _month_index(c.period_key) is not None:
        native = {"wolwoon", "ilwoon"}
    elif len(c.period_key) == 4 and c.period_key.isdigit():
        native = {"sewoon"}
    else:
        return True
    return any(
        e.role is EvidenceRole.TRIGGER and (_layer_tokens(e.layer) & native)
        for e in c.evidence
    )


def _exposure_weight(c: RiskCandidate) -> float:
    """exposure 축 = rankable 가중(감수 26차) — 게이트 미통과는 0.

    is_exposable이 정책을 이미 통합한다: DENIED/NOT_APPLICABLE(BLOCKED),
    confirmed_required+UNKNOWN, unknownExposable=false, CONTEXT_CONFLICT,
    vulnerability(단독 노출 없음), 축 미확인 구체 항목 — 전부 0. 통과 후보만
    CONFIRMED=1.0 / UNKNOWN(조건부 허용 항목)=0.55. DENIED의 구조 진단은
    structural_priority(exposure 제외)가 담당한다.
    """
    # DENIED/NOT_APPLICABLE는 엔진에서 BLOCKED로 이어지지만(hard blocker),
    # 점수층은 입력 상태를 신뢰하지 않고 자체 방어한다(0 — counterfactual 진단은
    # structural_priority 소관).
    if c.exposure_status in (ExposureStatus.DENIED, ExposureStatus.NOT_APPLICABLE):
        return 0.0
    if not is_exposable(c):
        return 0.0
    if c.exposure_status is ExposureStatus.CONFIRMED:
        return _EXPOSURE_CONFIRMED
    return _EXPOSURE_UNKNOWN_RANKABLE


def _month_index(label: str) -> int | None:
    """'YYYY-MM' → 절대 월 인덱스(연속 판정용). 그 외 형식은 None."""
    if len(label) == 7 and label[4] == "-":
        return int(label[:4]) * 12 + int(label[5:7]) - 1
    return None


def _longest_contiguous_run(periods: set[str]) -> int:
    """같은 계열의 최장 연속 구간(감수 26차 — 간헐 반복≠연속 압박).

    월운 라벨('YYYY-MM')이 있으면 월 연속만 계산한다 — 그 달들을 포함하는 연운
    라벨('YYYY')은 별도 기간이 아니라 layer convergence(기간 중복 계산 금지).
    월운이 없으면 연 단위 연속으로 계산한다.
    """
    months = sorted(m for m in (_month_index(x) for x in periods) if m is not None)
    if months:
        seq = months
    else:
        seq = sorted(int(x) for x in periods if len(x) == 4 and x.isdigit())
        if not seq:
            return max(1, len(periods))  # 미상 형식 — 보수적으로 반복 없음 취급
    best = cur = 1
    for prev, nxt in zip(seq, seq[1:], strict=False):
        cur = cur + 1 if nxt == prev + 1 else 1
        best = max(best, cur)
    return best


def _episode_signature(c: RiskCandidate) -> frozenset[tuple[str, str]]:
    """후보가 실제로 연결된 (축, episode) 서명 — 항목이 게이트하지 않는 축은
    None이라 자동 제외된다(무관 episode가 lineage·효과 식별에 못 들어감)."""
    return frozenset(
        (axis, ep) for axis, ep in (
            ("selection", c.selection_episode_id),
            ("mobility", c.mobility_episode_id),
            ("health", c.health_episode_id),
            ("legal", c.legal_episode_id),
            ("relationship", c.relationship_target_id),
        ) if ep is not None
    )


def trigger_bundle_contiguous_runs(
    candidates: list[RiskCandidate],
) -> dict[tuple, int]:
    """복수 원인 **묶음**의 연속성 진단(감수 29차) — 점수 키로 쓰지 않는다.

    키 = (risk_id, 연결 episode 서명, CAUSE 원자 전체 집합). 두 원인의 동시
    존재를 요구하는 항목의 조합 지속 관찰 전용 — 후보 persistence는 개별 cause
    lineage 기준이다({A}→{A,B}→{A}: A run 3·bundle run 1).
    """
    period_sets: dict[tuple, set[str]] = {}
    for c in candidates:
        if _has_period_native_trigger(c):
            period_sets.setdefault(
                (c.risk_id, _episode_signature(c), _candidate_atoms(c)), set(),
            ).add(c.period_key)
    return {k: _longest_contiguous_run(v) for k, v in sorted(
        period_sets.items(), key=lambda kv: repr(kv[0]))}


def effect_contiguous_runs(candidates: list[RiskCandidate]) -> dict[tuple, int]:
    """effect 연속성 진단 — (risk_id, episode 서명)별 최장 연속 구간.

    원인이 교체되어도 이어지는 노출 연속(1월 충→2월 형→3월 유입)을 별도로
    관찰한다. **persistence component에는 쓰지 않는다**(점수는 cause lineage
    기준) — R2 episode 병합·서술 재료.
    """
    period_sets: dict[tuple, set[str]] = {}
    for c in candidates:
        if _has_period_native_trigger(c):
            period_sets.setdefault(
                (c.risk_id, _episode_signature(c)), set()).add(c.period_key)
    return {k: _longest_contiguous_run(v) for k, v in sorted(
        period_sets.items(), key=lambda kv: repr(kv[0]))}


def risk_priority(
    components: RiskScoreComponents,
    *,
    transition_bonus: float = 0.0,
) -> tuple[float, float]:
    """(raw, capped) rankable 우선도 — total은 여기서 마지막 한 번만 계산한다.

    감수 32차 공식 개정 — **지속성·복합성·보호는 기본 위험의 modifier**이지
    독립 점수원이 아니다(additive에서 persistence가 기본 구조항의 3배로 상위를
    주도하던 문제 교정):

        structural_base = occurrence × impact
        raw = exposure × structural_base × (1 + persistence + compound)
              × (1 − protection)

    성질: ①비노출(exposure 0)은 지속·복합으로 부활 불가 ②occurrence가 약하면
    persistence만으로 상위 진입 불가(기여 상한 = base×1) ③UNKNOWN 가중이 전
    양의 항에 일관 적용 ④protection은 비례 완화 — 절대 감점이 다수 후보를
    음수로 만들던 문제(context-exposable 65% 음수) 해소, raw ≥ 0.
    capped = [0,1] clamp(포화 진단은 raw). 후보 저장 금지 — 등급·선별은 R2.
    """
    base = components.occurrence * components.impact
    timed_base = base * (1.0 + transition_bonus)  # 교운기 시점 modifier(감수 36차)
    raw = (
        components.exposure * timed_base
        * (1.0 + components.persistence + components.compound)
        * (1.0 - components.protection)
    )
    return round(raw, 6), min(1.0, max(0.0, round(raw, 6)))


def structural_priority(
    components: RiskScoreComponents,
    *,
    transition_bonus: float = 0.0,
) -> float:
    """exposure 제외 구조 진단 우선도 — DENIED·미확인 후보의 counterfactual 진단.

    rankable(risk_priority)과 달리 노출 게이트와 무관하게 구조 신호의 세기만
    본다(사용자 노출·선별에 쓰지 않는다 — R4 오경고 분석·감수 재료).

    **compound 축 제외(감수 27차)**: components.compound는 rankable 연결(is_
    exposable 내장)이라 노출 상태에 따라 변한다 — 구조 진단에 포함하면 CONFIRMED
    ↔DENIED 전환만으로 structural 값이 바뀌는 누수가 생긴다. 구조 연결 진단은
    compound_family_links(exposable_only=False)를 별도로 쓴다.
    """
    base = components.occurrence * components.impact * (1.0 + transition_bonus)
    return round(
        base * (1.0 + components.persistence) * (1.0 - components.protection),
        6,
    )


def context_axes(c: RiskCandidate) -> dict[str, list[str]]:
    """후보가 실제로 요구하는 context 축의 상태 분해(감수 29차 — R1-c1 리포트).

    required = 항목이 게이트하는 축(alignment 비기본·episode·stage 메타 존재).
    confirmed/unknown/conflicted로 분해 — context confidence의 근거를 축 단위로
    보여준다(요구하지 않는 축은 평가하지 않는다).
    """
    axes = {
        "selection": (c.selection_alignment, c.selection_episode_id,
                      bool(c.selection_stages)),
        "mobility": (c.mobility_alignment, c.mobility_episode_id,
                     bool(c.mobility_stages)),
        "health": (c.health_alignment, c.health_episode_id, False),
        "legal": (c.legal_alignment, c.legal_episode_id, bool(c.legal_stages)),
        "relationship": (c.relationship_alignment, c.relationship_target_id,
                         c.relationship_role is not None),
    }
    out: dict[str, list[str]] = {
        "required": [], "confirmed": [], "unknown": [], "conflicted": []}
    for name, (alignment, episode, gated_meta) in sorted(axes.items()):
        required = alignment != "matched" or episode is not None or gated_meta
        if not required:
            continue
        out["required"].append(name)
        if name == "selection" and c.selection_context_conflict:
            out["conflicted"].append(name)
        elif alignment == "matched" and (
            c.exposure_status is ExposureStatus.CONFIRMED or episode is not None
        ):
            out["confirmed"].append(name)
        else:
            out["unknown"].append(name)
    return out


def context_confidence(c: RiskCandidate) -> float:
    """context confidence(잠정) — **후보가 요구하는 축만** 평가한 현실 정보의
    완전성·충돌 여부(감수 29차).

    structural confidence(candidate.confidence — provenance 구체성·독립 근거·
    layer corroboration)와 분리된 축이다: context가 CONFIRMED라고 structural
    confidence가 오르지 않고, context가 UNKNOWN이라고 occurrence가 내려가지
    않는다(불변식 fixture). 후보에 저장하지 않는 진단 함수 — R2/R3 표현 재료.
    점수(rankable/structural priority)에 포함하지 않는다.
    """
    if c.selection_context_conflict:
        return 0.0
    if c.exposure_status in (ExposureStatus.DENIED, ExposureStatus.NOT_APPLICABLE):
        return 0.0  # 적용 부정 — 완전성 축 아님
    axes = context_axes(c)
    if not axes["required"]:  # 축 요구 없음 — 전역 노출 상태만
        return 1.0 if c.exposure_status is ExposureStatus.CONFIRMED else 0.5
    if axes["conflicted"]:
        return 0.0
    resolved = len(axes["confirmed"])
    return round(0.5 + 0.5 * (resolved / len(axes["required"])), 6) if (
        c.exposure_status is ExposureStatus.CONFIRMED or resolved
    ) else 0.5


def scoring_config_hash() -> str:
    """점수 설정 해시 — shadow_scoring 감수 무효화 가드 재료(감수 28차).

    공식·가중·cap·매핑이 하나라도 바뀌면 값이 바뀐다 — reviewHashes에 포함된
    감수는 자동 강등 대상이 된다(RISK_SCORING_VERSION 문자열만으로는 부족).
    """
    import hashlib
    import json as _json
    config = {
        "formula": "exposure * (occurrence*impact) * (1+persistence+compound)"
                   " * (1-protection) — modifier 구조(감수 32차)",
        "structural_formula": "(occurrence*impact) * (1+persistence)"
                              " * (1-protection) — compound·exposure 제외",
        "exposure_weights": {
            "confirmed": _EXPOSURE_CONFIRMED,
            "unknown_rankable": _EXPOSURE_UNKNOWN_RANKABLE,
            "denied": 0.0, "not_applicable": 0.0, "context_conflict": 0.0,
            "gate": "is_exposable",
        },
        "persistence": {"basis": "per_cause_lineage_longest_contiguous_run"
                                 " (개별 원인 — 보조 원인 증감에 불연속 금지)",
                        "native_gate": True, "span": _PERSISTENCE_SPAN},
        "compound": {"basis": "distinct_normalized_effect_roles",
                     "identity_resolution": "episode 서명 필수 —"
                                            " unresolved=제외(fail-closed)",
                     "per_link": _COMPOUND_PER_LINK, "cap": 1.0,
                     "status": "잠정 0.10 — 0.25 기각(감수 32차),"
                               " taxonomy 정리 후 재측정 확정"},
        "occurrence": {"combine": "1-prod(1-s)", "per_source_dedup": "max"},
        "protection_cap": _PROTECTION_CAP,
        "transition": "shadow_temporal scope 분리(감수 37차) —"
                      " transition_policy_hash 참조",
        "confidence": {"base": _CONF_BASE, "per_extra_cause": _CONF_PER_EXTRA_CAUSE,
                       "layer": _CONF_LAYER,
                       "context_confidence": "separate_diagnostic"},
        "component_caps": "각 축 [0,1] + capped total clamp",
    }
    return hashlib.sha256(
        _json.dumps(config, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


def transition_policy_hash() -> str:
    """교운기 temporal 정책 해시(감수 37차 — shadow_temporal scope 재료).

    계수·MAX_BONUS·커널 참조·기간→대표일 규칙·공식이 하나라도 바뀌면 변경 —
    shadow_temporal 감수 자동 강등 재료(스탬프·manifest 병기).
    """
    import hashlib
    import json as _json
    policy = {
        "kernel_ssot": "saju_engines.event_scoring.daewoon_transition_weight"
                       " (exp(-(d/365)^1.0) 라플라스형 kernel)",
        "min_weight_gate": 0.05,
        "period_reference": "호출부가 기간 대표일→커널값을 이벤트 엔진과 동일"
                            " 규칙으로 산출해 transition_weights로 공급"
                            "(월=이벤트 엔진 기준일 규칙 공유)",
        "apply": "timed_base = base × (1 + weight×coef×MAX_BONUS)",
        "sensitivity_coef": _TRANSITION_SENSITIVITY_COEF,
        "max_bonus": _TRANSITION_MAX_BONUS,
        "invariants": "적격성·원인 수·cause table·persistence·episode identity"
                      " 불개입, base=0·비노출 부활 불가, vulnerability=none",
    }
    return hashlib.sha256(
        _json.dumps(policy, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


def cause_semantics_hash() -> str:
    """cause 의미 registry 해시 — 분류·정규화 변경 시 감수 자동 강등 재료."""
    import hashlib
    import json as _json
    semantics = {
        "version": CAUSE_SEMANTICS_VERSION,
        "registry": {
            "relation:*": _SEM_CAUSE, "ten_god:*": _SEM_CAUSE,
            "void": _SEM_CONDITIONAL, "no_void": _SEM_GATE,
            "stage:*": _SEM_ACTIVATION, "polarity:*": _SEM_AMPLIFIER,
            "unknown": "reject",
        },
        "cause_eligibility": "CAUSE 원자 동반 source만 occurrence 재료",
        "lineage": "risk_id + 연결 episode 서명 + 개별 canonical cause_atom",
        "effect_roles_ssot": "dictionary field normalizedEffectRole"
                             " (hash schema v9 — shadow_scoring scope 본문)",
        "void_target_contract": "현재 매처의 void는 시점 전역 상태(궁위 무관) — "
                                "targeted void 원자는 미정의(미상 namespace로 "
                                "fail-closed 거부, 도입 시 target 일치 검증 필수)",
    }
    return hashlib.sha256(
        _json.dumps(semantics, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


__all__ = [
    "CAUSE_SEMANTICS_VERSION",
    "RISK_SCORING_VERSION",
    "atom_semantics",
    "cause_occurrence_table",
    "cause_semantics_hash",
    "compound_family_links",
    "compound_unresolved_counts",
    "context_axes",
    "context_confidence",
    "effect_contiguous_runs",
    "normalized_effect_role",
    "risk_priority",
    "score_shadow",
    "scoring_config_hash",
    "structural_priority",
    "transition_policy_hash",
    "trigger_bundle_contiguous_runs",
]
