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
RISK_SCORING_VERSION = "risk-score-r1.0.3-shadow"

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
# compound(감수 26차 확정 — risk_id 개수 기준 금지): 같은 기간·원인 공유 연결 중
# **독립 exposable 효과군**만 — 다른 risk_family(같은 family=동일 효과 계열의
# alias·파생) + is_exposable + 미흡수(supporting 아님). 같은 원인의 문서 부담·
# 검토 취약·행정 supporting 파생은 복합 위험이 아니다. family 1건당 가중, cap 1.0.
_COMPOUND_PER_LINK = 0.25
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
CAUSE_SEMANTICS_VERSION = "cause-semantics-v2"


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
    return round(1.0 - acc, 6)


def _candidate_atoms(c: RiskCandidate) -> frozenset[str]:
    """후보의 occurrence 적격(CAUSE) 원인 원자 — compound 연결·lineage 재료."""
    return frozenset(a for a in c.trigger_cause_atoms
                     if atom_semantics(a) == _SEM_CAUSE)


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
    # persistence 재료(감수 27차 — 직렬화 구분): 같은 계열(lineage — risk_id+
    # 전 축 episode 서명)에서 **period-native trigger**가 있는 기간만 센다.
    # 상위 layer(세운) 원인이 12개 월 후보에 단순 복제된 직렬화는 같은 사실의
    # 반복 출력이라 persistence를 자동 최대화하면 안 된다 — 월 기간은 월운/일운
    # 발동, 연 기간은 세운 발동이 실제로 있는 경우만 지속으로 인정.
    native_period_sets: dict[tuple[str | None, ...], set[str]] = {}
    for c in candidates:
        if _has_period_native_trigger(c):
            native_period_sets.setdefault(_series_key(c), set()).add(c.period_key)
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
        run = _longest_contiguous_run(
            native_period_sets.get(_series_key(c), set()))
        components = RiskScoreComponents(
            occurrence=occ,
            impact=min(1.0, max(0.0, base_impact.get(c.risk_id, 0.0))),
            exposure=_exposure_weight(c),
            persistence=min(1.0, max(0.0, (run - 1) / _PERSISTENCE_SPAN)),
            compound=min(1.0, _COMPOUND_PER_LINK * len(linked_families)),
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
            c.risk_id, c.risk_family, _candidate_atoms(c),
            _effect_identity(c),
            c.suppressed_by_specificity is None
            # rankable 연결의 노출 판정은 _exposure_weight와 동일 기준(DENIED/
            # NOT_APPLICABLE 상태 방어 포함) — 축 간 기준 불일치 방지.
            and (not exposable_only or _exposure_weight(c) > 0.0),
        ))
    out: list[set[str]] = []
    for c in candidates:
        my_atoms = _candidate_atoms(c)
        my_effect = _effect_identity(c)
        out.append({
            fam for rid, fam, atoms, effect, independent in (
                links_by_period.get(c.period_key, []))
            if independent and rid != c.risk_id and fam is not None
            and fam != c.risk_family and (atoms & my_atoms)
            # 교차 도메인 normalized effect identity(감수 28차): family가 달라도
            # 같은 현실 효과의 복제(같은 episode·같은 효과 성격)는 영향 확장이
            # 아니다 — compound 제외. episode-free 쌍의 동일 효과 통합은 사전
            # riskFamily(교차 도메인 통합 키) 저작이 담당(감수 질문로 기록).
            and effect != my_effect
        })
    return out


def _effect_identity(c: RiskCandidate) -> tuple:
    """normalized effect identity(잠정) — (kind, 연결 episode 서명).

    같은 episode에 걸린 같은 성격(kind)의 후보는 family·도메인이 달라도 같은
    현실 효과의 복제로 본다(계약 일정 차질의 MOV·LEG·FIN 병렬 표현). episode
    정보가 없는 후보는 이 proxy로 동일성을 주장할 수 없으므로 후보별 고유
    identity를 부여해 제외 규칙이 발동하지 않는다 — episode-free 쌍의 동일 효과
    통합은 riskFamily(교차 도메인 통합 키) 저작+R2 대표 선택 소관(효과 role
    어휘 정식화는 R1-c 감수 질문).
    """
    sig = _episode_signature(c)
    if not sig:
        return (c.kind.value, None, c.risk_id)  # 고유 — 동일성 주장 불가
    return (c.kind.value, sig)


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


def _series_key(c: RiskCandidate) -> tuple:
    """persistence **cause lineage** 키(감수 28차) — risk_id + 연결 episode 서명 +
    CAUSE 원인 원자 집합.

    같은 risk_id·episode라도 매달 원인이 바뀌면(충→형→십성 유입) 같은 지속 위험이
    아니다 — cause lineage가 끊겨 run이 분리된다. 원인이 달라도 이어지는 효과
    연속성(effect run)은 점수가 아니라 진단(effect_contiguous_runs — R2 episode
    분석 재료)으로만 남긴다.
    """
    return (c.risk_id, _episode_signature(c), _candidate_atoms(c))


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


def structural_priority(components: RiskScoreComponents) -> float:
    """exposure 제외 구조 진단 우선도 — DENIED·미확인 후보의 counterfactual 진단.

    rankable(risk_priority)과 달리 노출 게이트와 무관하게 구조 신호의 세기만
    본다(사용자 노출·선별에 쓰지 않는다 — R4 오경고 분석·감수 재료).

    **compound 축 제외(감수 27차)**: components.compound는 rankable 연결(is_
    exposable 내장)이라 노출 상태에 따라 변한다 — 구조 진단에 포함하면 CONFIRMED
    ↔DENIED 전환만으로 structural 값이 바뀌는 누수가 생긴다. 구조 연결 진단은
    compound_family_links(exposable_only=False)를 별도로 쓴다.
    """
    return round(
        components.occurrence * components.impact
        + components.persistence - components.protection,
        6,
    )


def context_confidence(c: RiskCandidate) -> float:
    """context confidence(잠정) — 현실 exposure 정보의 완전성·충돌 여부.

    structural confidence(candidate.confidence — provenance 구체성·독립 근거·
    layer corroboration)와 분리된 축이다: context가 CONFIRMED라고 structural
    confidence가 오르지 않고, context가 UNKNOWN이라고 occurrence가 내려가지
    않는다(불변식 fixture). 후보에 저장하지 않는 진단 함수 — R2/R3 표현 재료.
    """
    if c.selection_context_conflict:
        return 0.0
    if c.exposure_status is ExposureStatus.CONFIRMED:
        return 1.0
    if c.exposure_status is ExposureStatus.UNKNOWN:
        return 0.5
    return 0.0  # DENIED/NOT_APPLICABLE — 적용 부정(완전성 아님)


def scoring_config_hash() -> str:
    """점수 설정 해시 — shadow_scoring 감수 무효화 가드 재료(감수 28차).

    공식·가중·cap·매핑이 하나라도 바뀌면 값이 바뀐다 — reviewHashes에 포함된
    감수는 자동 강등 대상이 된다(RISK_SCORING_VERSION 문자열만으로는 부족).
    """
    import hashlib
    import json as _json
    config = {
        "formula": "occurrence*impact*exposure + persistence + compound"
                   " - protection",
        "structural_formula": "occurrence*impact + persistence - protection"
                              " (compound 제외)",
        "exposure_weights": {
            "confirmed": _EXPOSURE_CONFIRMED,
            "unknown_rankable": _EXPOSURE_UNKNOWN_RANKABLE,
            "denied": 0.0, "not_applicable": 0.0, "context_conflict": 0.0,
            "gate": "is_exposable",
        },
        "persistence": {"basis": "cause_lineage_longest_contiguous_run",
                        "native_gate": True, "span": _PERSISTENCE_SPAN},
        "compound": {"basis": "independent_exposable_effect_family",
                     "effect_identity": "kind+episode_signature",
                     "per_link": _COMPOUND_PER_LINK, "cap": 1.0},
        "occurrence": {"combine": "1-prod(1-s)", "per_source_dedup": "max"},
        "confidence": {"base": _CONF_BASE, "per_extra_cause": _CONF_PER_EXTRA_CAUSE,
                       "layer": _CONF_LAYER,
                       "context_confidence": "separate_diagnostic"},
        "component_caps": "각 축 [0,1] + capped total clamp",
    }
    return hashlib.sha256(
        _json.dumps(config, sort_keys=True, ensure_ascii=False).encode()
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
        "lineage": "risk_id + 연결 episode 서명 + CAUSE 원자 집합",
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
    "context_confidence",
    "effect_contiguous_runs",
    "risk_priority",
    "score_shadow",
    "scoring_config_hash",
    "structural_priority",
]
