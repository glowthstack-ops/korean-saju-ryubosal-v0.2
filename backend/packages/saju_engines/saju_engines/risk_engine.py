"""위험 탐지 엔진 R0 — 원시 신호 → 원자 위험 후보 생성 (doc/v2_2/RISK_ENGINE.md).

기회 파이프라인(EventEngineV2 6계층)과 독립이다. 입력은 **reducer·모디파이어 이전의 원시
신호 스냅샷(RawPeriodFacts)** — 감점·quality flip·floor·Top-N을 거친 최종 후보를 소비하면
위험 근거가 이미 손실되므로 금지한다(2026-07-15 데굴님 승인 조건 1).

R0 책임 범위: 사전 룰 매칭 → 근거(provenance) 수집 → minimum_evidence 게이트 → 원자
RiskCandidate 생성까지. 점수(6축)·기간 병합(RiskEpisode)·risk_level·사용자 노출은 하지
않는다(R1/R2/R3). 결과는 shadow 사이드채널 전용 — LLM 입력에 주입하지 않는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from saju_shared_types.event_engine import (
    TEN_GOD_GROUP,
    LuckLayer,
    Pillar4,
    PolarityRole,
    RelationKind,
    TenGod,
    TwelveStage,
)
from saju_shared_types.risk_engine import (
    EligibilityStatus,
    EvidenceRole,
    ExposureStatus,
    RiskCandidate,
    RiskDomain,
    RiskEvidence,
    RiskKind,
    dedupe_evidence,
    independent_source_count,
    is_exposable,
)

from .dictionaries import RiskItem, RiskMappingFile, RiskRuleSpec

# 극성 사실은 특정 운 층위가 아니라 시점(기간) 전체의 판정이다 — 근거 layer 표기용.
_PERIOD_LAYER = "period"
# kind → 기본 특이도(사전 specificityRank 미지정 시): 구체 대상 사건은 사전에서 3 명시.
_KIND_SPECIFICITY = {"incident_risk": 2, "vulnerability": 1, "pressure": 0}


def _specificity_rank(item: RiskItem) -> int:
    """항목 특이도 — 명시값 우선, 없으면 kind에서 유도한다."""
    if item.specificity_rank is not None:
        return item.specificity_rank
    return _KIND_SPECIFICITY.get(item.kind, 0)


# 현실 대상 수렴 도메인(감수 16→18차) — 흡수 범위가 family가 아니라 '같은 현실 대상'
# (관계=같은 상대, 이동=같은 이동 episode)인 도메인. cross-family 흡수는 relation 원자
# 공유 + absorbedRoleHint 명시 항목만.
_CONVERGENCE_DOMAINS = frozenset({
    RiskDomain.RELATIONSHIP, RiskDomain.RELOCATION, RiskDomain.HEALTH_SAFETY,
    RiskDomain.CONTRACT_LEGAL,
})

_SHAPE_GROUPS = frozenset({"event_shape", "targeted_event_shape", "structural_weakness"})
_ACTIVATION_GROUPS = frozenset({"activation", "target_activation"})


def _evidence_god_groups(e: RiskEvidence) -> set[str]:
    """근거 원자에서 십성군 토큰 추출 — 유입 십성(ten_god:)과 피자극 십성(관계 원자
    말미 gods)을 모두 군으로 환원한다(대상 연결 판정용)."""
    groups: set[str] = set()
    for atom in cause_atoms(e.source):
        if atom.startswith("ten_god:"):
            names = atom.split(":", 1)[1].split("+")
        elif atom.startswith("relation:"):
            names = atom.split(":")[-1].split("+")  # 서명 말미 = 피자극 십성(없으면 잡음)
        else:
            continue
        for n in names:
            try:
                groups.add(TEN_GOD_GROUP[TenGod(n)].value)
            except (KeyError, ValueError):
                continue
    return groups


def _relation_atoms(e: RiskEvidence) -> frozenset[str]:
    """근거의 관계 원자(정규화된 대상 객체 서명 포함)만 추출."""
    return frozenset(a for a in cause_atoms(e.source) if a.startswith("relation:"))


def _target_object_signatures(e: RiskEvidence) -> frozenset[str]:
    """관계 원자에서 **관계 종류를 제외한** 대상 객체 서명(궁위:자리[:글자][:십성])만
    추출 — 형과 해가 같은 대상을 쳐도 같은 객체로 판정한다(감수 14차: 대상 동일성은
    관계 종류가 아니라 target_object_signature 기준)."""
    return frozenset(
        a.split(":", 2)[2] for a in _relation_atoms(e) if a.count(":") >= 2
    )


def _targets_linked(triggers: list[RiskEvidence]) -> bool:
    """shape 계열과 활성 계열 trigger의 대상 연결 판정(감수 11차·12차 강화).

    연결 우선순위: ①동일 원인 원자(같은 사실) ②십성군 대상 겹침 — 단, **양쪽 모두
    구체적 대상 객체(관계 원자)를 갖고 있는데 서로 다르면 십성군 일치가 이를 구제하지
    못한다**(같은 관성군이어도 사회궁 피격과 일지 피격은 별개 대상). 십성군 fallback은
    한쪽에 상위 대상 정보가 없을 때만 제한적으로 허용된다. link_type 기록(연결 강도별
    occurrence 신뢰도)은 R1 백로그.
    """
    shapes = [e for e in triggers if e.source_group in _SHAPE_GROUPS]
    acts = [e for e in triggers if e.source_group in _ACTIVATION_GROUPS]
    if not shapes or not acts:
        return True  # 두 계열이 모두 있을 때만 연결을 요구한다(targeted 단독 경로 등).
    for s in shapes:
        s_atoms = cause_atoms(s.source)
        s_rel, s_groups = _relation_atoms(s), _evidence_god_groups(s)
        for a in acts:
            if s_atoms & cause_atoms(a.source):
                return True  # ① 동일 원인 사실.
            a_rel = _relation_atoms(a)
            if s_rel and a_rel and not (
                _target_object_signatures(s) & _target_object_signatures(a)
            ):
                continue  # 양쪽 대상 객체가 명시적으로 다름 — fallback 구제 금지.
            if s_groups & _evidence_god_groups(a):
                return True  # ② 십성군 fallback(상위 대상 정보 부재 시에만 도달).
    return False


def cause_atoms(source: str) -> frozenset[str]:
    """원인 서명 → 원자 사실 집합. 복합 조건 룰(충&극성 등)의 서명을 원자로 분해해
    '같은 충'을 공유하는지 판정한다(서명 문자열 전체 비교는 부가 조건이 붙으면 어긋남)."""
    return frozenset(source.split("&"))


def _apply_specificity_suppression(cands: list[RiskCandidate]) -> list[RiskCandidate]:
    """특이도 우선 억제 — 동일 기간·동일 risk_family에서 원인을 공유하면 가장 구체적인
    후보를 대표로 남기고 하위 일반 후보를 흡수한다(2026-07-15 감수).

    조건(전부 충족 시 억제): 같은 period_key, 같은 risk_family(둘 다 non-null), trigger
    원인 원자(cause atom) 교집합 존재, 더 높은 specificity_rank의 활성 후보 존재.
    흡수된 후보는 삭제하지 않고 suppressed_by_specificity/primary_risk_id를 남긴다 —
    대표 후보의 부가 설명(보조 발현·배경 취약성)으로 쓴다. relatedDomains 복제 금지의
    코드 표현: 교차 도메인이라도 family가 같으면 대표 1건으로 수렴한다.

    relationship 도메인(감수 16차)은 흡수 범위가 family가 아니라 '같은 상대'다: 같은
    상대·같은 원인에서 나온 감정 충돌·오해·신뢰 저하·거리감이 family가 달라도 대표
    1건+보조 역할로 수렴한다. 다른 target_id(배우자 vs 친구) 또는 다른 확인 역할은
    별개 그룹 — 서로 억제하지 않는다(같은 십성군이라도 상대가 다르면 병존).
    """
    candidates_ok = [
        c for c in cands
        if c.eligibility_status in (EligibilityStatus.ELIGIBLE, EligibilityStatus.MITIGATED)
        and c.risk_family is not None
    ]
    by_key: dict[tuple[str, str], list[RiskCandidate]] = {}
    for c in candidates_ok:
        if c.domain in _CONVERGENCE_DOMAINS:
            # 도메인 전체가 한 흡수 범위 — 상대 호환성(target_id·역할 상이 시 흡수
            # 금지)은 그룹 내부에서 검사한다: 상대 미상(None) 일반 후보가 매칭된
            # 대표(배우자 재조정 등)에 흡수되는 주 경로를 보존하기 위함이다.
            # 이동 게이트 후보(감수 22차): 같은 차량·이동 episode의 MOV 사건과 HLT
            # 안전 주의는 교차 도메인이라도 한 수렴 범위다(MOV primary — HLT는
            # hint로 impact_amplifier 수렴, 독립 원인이면 relation 원자 불공유로 병존).
            scope = ("mobility" if c.mobility_gated
                     and c.domain in (RiskDomain.RELOCATION, RiskDomain.HEALTH_SAFETY)
                     else c.domain.value)
            key = (c.period_key, "\x00convergence:" + scope)
        else:
            key = (c.period_key, "\x00family:" + (c.risk_family or ""))
        by_key.setdefault(key, []).append(c)

    def _atoms(c: RiskCandidate) -> set[str]:
        return {
            atom
            for e in c.evidence if e.role is EvidenceRole.TRIGGER
            for atom in cause_atoms(e.source)
        }

    def _exposure_ok(c: RiskCandidate) -> bool:
        """노출 적격성 — 컨텍스트 노출 게이트(is_exposable) 전체 기준(감수 22차 일반화).

        C2 불변식의 확장: 어떤 이유로든(노출 미확인·축 미확인·unknownExposable=false)
        사용자에게 노출될 수 없는 후보는, 노출 가능한 더 일반적인 후보를 흡수할 수
        없다(신체 부담 미확인 후보가 일반 피로 advisory를 지우는 역전 방지). 이 시점
        후보는 전부 활성(eligible·미흡수)이라 is_exposable을 그대로 쓸 수 있다.
        """
        return is_exposable(c)

    suppression: dict[int, tuple[str, str]] = {}  # id(candidate) → (대표 risk_id, 흡수 역할)
    for group in by_key.values():
        if len(group) < 2:
            continue
        # 대표 우선순위(감수 9차 → 17차 결정화): 구조적 적격성(이미 필터) → 노출
        # 적격성 → 구체 상대(target_id) → 역할 특정 → 특이도 → canonical risk_id
        # 타이브레이크. 사전 항목 순서·iteration 순서에 무관한 결정적 비교자다(같은
        # 입력은 저작 순서를 바꿔도 같은 대표를 선택 — 결정성 fixture 고정).
        # 불변식: 더 구체적이지만 더 엄격한 exposure를 요구하는 후보는, 그 exposure가
        # 충족되지 않은 상태에서 더 일반적이고 노출 가능한 후보를 흡수할 수 없다
        # (소송 확대가 노출 미확인 상태로 일반 분쟁 경고를 지우는 역전 방지).
        # 감수 16차 일반화 — 그룹 최상위 1건만이 아니라 선호 순서대로 '원인을 공유하는
        # 첫 적격 대표'를 찾는다(관계 도메인처럼 한 그룹에 서로 다른 상대의 대표가
        # 공존할 때 최상위와 원인이 무관하면 차선 대표가 흡수). 이미 흡수된 후보는
        # 대표가 될 수 없다(대표 체인 금지 — primary_risk_id는 항상 활성 대표:
        # A├─B supporting └─C trajectory, B→C 체인 없음).
        ordered = sorted(group, key=lambda c: (
            not _exposure_ok(c),
            c.relationship_target_id is None,
            c.relationship_role is None,
            -c.specificity_rank,
            c.risk_id,
        ))
        for c in ordered:
            for primary in ordered:
                if primary is c or id(primary) in suppression:
                    continue
                # vulnerability 대표 금지(감수 23차 커밋 조건 — RCW 역할 보장 일반화):
                # 취약성은 어떤 후보도 흡수할 수 없다 — 단독 노출 없음(is_exposable)에
                # 더해 대표 역할 자체를 차단한다(배경 근거·심각도 상향 재료 전용).
                # 노출 적격성 가드(_exposure_ok)와 독립인 이유: 양쪽 모두 비노출인
                # 조합(취약성 vs 미확인 압박)에서도 취약성이 대표가 되면 안 된다.
                if primary.kind is RiskKind.VULNERABILITY:
                    continue
                if c.specificity_rank >= primary.specificity_rank:
                    continue  # 동률은 억제하지 않는다(서로 다른 구체 사건 병존 허용).
                if not _exposure_ok(primary) and _exposure_ok(c):
                    continue  # 노출 부적격 대표는 노출 가능 후보를 흡수 불가.
                # stage-aware(감수 14차) — 양쪽 stage 메타가 명시적으로 다르면(교집합
                # 없음) 상호 배타 단계 후보라 같은 family여도 흡수하지 않는다.
                if (
                    primary.selection_stages and c.selection_stages
                    and not (set(primary.selection_stages) & set(c.selection_stages))
                ):
                    continue
                # 상대 상이(감수 16차) — 확인된 target_id 또는 역할이 서로 다르면 다른
                # 상대의 위험이다(배우자 재조정이 친구 금전·가족 부담을 흡수 금지 —
                # 같은 십성군이라도 병존). 미확인(None)은 같은 상대일 수 있어 통과.
                if (
                    c.relationship_target_id and primary.relationship_target_id
                    and c.relationship_target_id != primary.relationship_target_id
                ):
                    continue
                if (
                    c.relationship_role and primary.relationship_role
                    and c.relationship_role != primary.relationship_role
                ):
                    continue
                shared = _atoms(c) & _atoms(primary)
                if not shared:
                    continue
                # 이동 stage 호환(감수 19차) — 계약 전 단계와 정착 후 단계처럼 명시
                # stage 집합이 상호 배타면 같은 원인·family여도 흡수하지 않는다
                # (계약 차질 vs 통근·정착 부담 — 계약이 무산되면 후자는 발생하지 않을
                # 수 있는 별개 국면). selection stage-aware와 동일 규칙.
                if (
                    primary.mobility_stages and c.mobility_stages
                    and not (set(primary.mobility_stages) & set(c.mobility_stages))
                ):
                    continue
                # 이동 episode 상이(감수 19차) — 확인된 episode_id가 서로 다르면 다른
                # 이동 계획의 위험이다(새 집 계약 vs 임시 숙소 — 병존).
                if (
                    c.mobility_episode_id and primary.mobility_episode_id
                    and c.mobility_episode_id != primary.mobility_episode_id
                ):
                    continue
                # 건강 episode 상이(감수 21차) — 기존 불편 관리 vs 치료 회복 vs 교대
                # 근무 부담은 서로 다른 현실 맥락이다(병존).
                if (
                    c.health_episode_id and primary.health_episode_id
                    and c.health_episode_id != primary.health_episode_id
                ):
                    continue
                # 법적 process episode·stage(감수 23차) — 다른 절차는 병존, 명시
                # stage 상호 배타(초안 작성 vs 소송 진행)는 수렴 금지.
                if (
                    c.legal_episode_id and primary.legal_episode_id
                    and c.legal_episode_id != primary.legal_episode_id
                ):
                    continue
                # 선발 episode 상이(감수 25차 — SEL-e): 서로 다른 선발 건은 같은
                # 원인을 공유해도 자동 흡수하지 않는다(취업 결과 대기 vs 자격시험 —
                # 각자 자기 episode의 후보 보존, R1 shared cause 1회 계산은
                # trigger_cause_atoms 연결이 담당).
                if (
                    c.selection_episode_id and primary.selection_episode_id
                    and c.selection_episode_id != primary.selection_episode_id
                ):
                    continue
                if (
                    primary.legal_stages and c.legal_stages
                    and not (set(primary.legal_stages) & set(c.legal_stages))
                ):
                    continue
                if c.domain in _CONVERGENCE_DOMAINS:
                    # 같은 현실 대상 판정(감수 17→23차 일반화) — 확인된 동일성(같은
                    # 상대 target_id / 같은 이동·건강·법적 process episode)이 없으면
                    # **관계 사실(relation 원자 — 대상 객체 서명 내장)** 공유가 필수다.
                    # 십성 유입 원자만 공유한 두 후보는 서로 다른 현실 대상일 수 있다
                    # (부모 부담 vs 형제 오해). 같은 episode가 확인되면 검토 취약처럼
                    # relation 원자가 없는 구조 신호도 그 절차의 배경으로 수렴한다.
                    same_real_target = any(
                        getattr(c, f) is not None and getattr(c, f) == getattr(primary, f)
                        for f in ("relationship_target_id", "mobility_episode_id",
                                  "health_episode_id", "legal_episode_id")
                    )
                    if not same_real_target and not any(
                        a.startswith("relation:") for a in shared
                    ):
                        continue
                    # 명시적 수렴 관계(감수 17차) — cross-family 흡수는 사전이
                    # absorbedRoleHint로 수렴을 허용한 항목만(감정 충돌·소통·신뢰·
                    # 거리감). FAMILY_BURDEN·PEER_FINANCIAL처럼 별개 현실 문제인
                    # 항목은 같은 상대·같은 원인이어도 자동 흡수 금지.
                    if (
                        c.risk_family != primary.risk_family
                        and c.absorbed_role_hint is None
                    ):
                        continue
                suppression[id(c)] = (primary.risk_id, _absorbed_role(c, primary))
                break
    if not suppression:
        return cands
    return [
        c.model_copy(update={
            "suppressed_by_specificity": suppression[id(c)][0],
            "primary_risk_id": suppression[id(c)][0],
            "absorbed_role": suppression[id(c)][1],
        }) if id(c) in suppression else c
        for c in cands
    ]


def _absorbed_role(absorbed: RiskCandidate, primary: RiskCandidate) -> str:
    """흡수 후보의 역할 — 삭제가 아니라 역할 전환(2026-07-15 감수 3차).

    R1에서 대표 후보의 impact(압박=예상 영향)·exposure(취약성=피해 확대 요인) 계산과
    보조 서술에 쓴다. vulnerability는 사건 후보보다 일반적이어도 버리지 않는다.
    사전 absorbedRoleHint(감수 16차)가 있으면 kind 기본값 대신 그 역할을 쓴다
    (감정 충돌=supporting_manifestation, 거리감=possible_trajectory 등).
    """
    if absorbed.absorbed_role_hint is not None:
        return absorbed.absorbed_role_hint
    if absorbed.kind is RiskKind.VULNERABILITY:
        return "background_vulnerability"
    if absorbed.kind is RiskKind.PRESSURE:
        return "impact_amplifier"
    if absorbed.domain is not primary.domain:
        return "secondary_domain_effect"
    return "supporting_manifestation"


@dataclass(frozen=True)
class SelectionContext:
    """현실 선발 컨텍스트 1건(감수 14차 → 25차 SEL-e 확장) — mode/stage/대상 유형.

    None = UNKNOWN(정보 부족 — 구조 보존, 특정 표현 금지). 값이 있는데 항목의 허용
    목록 밖이면 MISMATCHED(임의 fallback 금지). mode와 stage는 상호 자동 추론 금지:
    stage=draw여도 mode를 lottery로 가정하지 않는다. target_type은 CAR·SEL 소유권
    (채용=CAR primary) — context_target_signature의 선발·직업 도메인 구현체.

    SEL-e(감수 25차): 복수 선발 episode 지원 — 취업 지원 결과 대기와 별도 자격시험·
    추첨 지원이 동시에 실재할 수 있다. episode_id는 target_type과 별개의 명시 키다
    (같은 유형의 선발 2건 병존 — examination_1/examination_2). is_question_target
    기본 True인 이유: 선발 컨텍스트의 기존 공급원은 질문 파싱(질문 대상)뿐이라
    단수 시절 의미(축 밖 질문 대상 = BLOCKED)를 보존한다 — 프로필·등록 유래의
    '존재 정보' 컨텍스트는 False를 명시한다.
    """

    mode: str | None = None  # competitive_assessment/lottery_draw/... (None=UNKNOWN)
    stage: str | None = None  # application_document/.../waitlist (None=UNKNOWN)
    target_type: str | None = None  # employment_hiring/examination/... (None=UNKNOWN)
    # 익명 선발 episode 키(감수 25차) — 후보 identity·소유권·수렴 경계의 핵심.
    episode_id: str | None = None
    # 이 선발 건에 대한 현실 노출 확인 수준 — UNKNOWN(기본)이면 전역 노출 인자 사용
    # (단수 시절 호출 하위 호환: 전역 exposure_status가 선발 노출을 대신 표현했다).
    exposure_status: ExposureStatus = ExposureStatus.UNKNOWN
    is_question_target: bool = True


def _axis_alignment(ctx_value: str | None, allowed: list[str]) -> str:
    """한 축의 3상태 판정 — 항목이 축을 제한하지 않으면 항상 matched."""
    if not allowed:
        return "matched"
    if ctx_value is None:
        return "unknown"
    return "matched" if ctx_value in allowed else "mismatched"


_SELECTION_AXES = ("mode", "stage", "target_type")


def _item_selection_gated(item: RiskItem) -> bool:
    """선발 축이 있는 항목인가 — episode별 해석 대상."""
    return bool(
        item.applicable_selection_modes or item.applicable_selection_stages
        or item.applicable_target_types
    )


def _resolve_selection_all(
    item: RiskItem,
    contexts: list[SelectionContext],
) -> list[tuple[str, str | None, ExposureStatus | None, bool, list[str]]]:
    """선발 축 episode별 해석(감수 25차 — SEL-e) → (alignment, episode_id,
    유효 노출(None=전역 사용), context_conflict, mismатch 축 목록).

    이동·건강·법률과 동일 원리 + 선발 고유 규칙 둘:

    - **결정적 병합·보완**: 같은 episode의 중복 컨텍스트는 입력 순서와 무관하게
      병합한다 — 축별로 명시 값이 하나뿐이면 그 값으로 보완(stage만 아는 입력 +
      mode를 아는 입력 = 둘 다 반영), 서로 다른 명시 값이 충돌하면 임의 우선순위
      없이 CONTEXT_CONFLICT(구조 보존·비노출·위생 로그).
    - **episode ≠ target_type**: 같은 유형의 선발 2건(examination_1/2)이 병존할
      수 있다 — episode 합치기는 명시 episode_id로만 한다(유형 기반 병합 금지).

    질문 대상(is_question_target) 컨텍스트가 명시적으로 축 밖이면 그 항목은
    mismatched(BLOCKED — 단수 시절 의미 보존)지만, **다른 episode가 호환되면
    그 episode 해석이 우선한다**(mismatch의 episode 간 전파 금지).
    """
    if not _item_selection_gated(item):
        return [("matched", None, None, False, [])]
    groups: dict[str | None, list[SelectionContext]] = {}
    for ctx in contexts:
        groups.setdefault(ctx.episode_id, []).append(ctx)
    out: list[tuple[str, str | None, ExposureStatus | None, bool, list[str]]] = []
    mismatch_axes: list[str] = []  # 질문 대상 컨텍스트의 명시 불일치 축(전 episode)
    for ep in sorted(groups, key=lambda e: (e is None, e or "")):
        group = groups[ep]
        # 축별 결정적 병합 — 명시 값 집합이 2개 이상이면 충돌.
        merged: dict[str, str | None] = {}
        conflict = False
        for axis in _SELECTION_AXES:
            values = {v for v in (getattr(c, axis) for c in group) if v is not None}
            if len(values) > 1:
                conflict = True
                merged[axis] = None
            else:
                merged[axis] = next(iter(values), None)
        exposure = max(
            (c.exposure_status for c in group),
            key=lambda e: _EXPOSURE_PREFERENCE[e],
        )
        question = any(c.is_question_target for c in group)
        if conflict:
            # 양립 불가 상태 — 구조 후보 보존, 노출은 is_exposable이 차단.
            out.append(("unknown", ep, ExposureStatus.UNKNOWN, True, []))
            continue
        axes = {
            "mode": _axis_alignment(merged["mode"], item.applicable_selection_modes),
            "stage": _axis_alignment(
                merged["stage"], item.applicable_selection_stages),
            "target_type": _axis_alignment(
                merged["target_type"], item.applicable_target_types),
        }
        if any(a == "mismatched" for a in axes.values()):
            if question:
                mismatch_axes.extend(
                    name for name, a in axes.items() if a == "mismatched")
            continue  # 이 episode는 이 항목의 대상이 아님 — 다른 episode 병존.
        alignment = ("unknown" if any(a == "unknown" for a in axes.values())
                     else "matched")
        eff = exposure if exposure is not ExposureStatus.UNKNOWN else None
        out.append((alignment, ep, eff, False, []))
    if out:
        return out
    if mismatch_axes:
        return [("mismatched", None, None, False,
                 sorted(dict.fromkeys(mismatch_axes)))]
    return [("unknown", None, None, False, [])]


@dataclass(frozen=True)
class RelationshipContext:
    """현실 관계 컨텍스트 1건(감수 16차 — REL 차수) — 프로필·동반자 등록·질문에서 확인된
    관계다. 관계 위험은 십성·궁위만으로 현실의 상대를 만들어내지 않는다: 배우자궁 충은
    관계 영역의 구조적 활성일 뿐, "배우자가 있다/갈등한다"는 이 컨텍스트가 공급한다.

    공급원: ①2단계 프로필(결혼·가족 — 항상 선택, 부재≠DENIED) ②동반자 등록·관계힌트
    (테마사주·AI채팅의 궁합/함께보기 — 등록된 동반자는 role·target_id가 확인된 관계)
    ③질문 명시("남자친구랑…"). target_id는 실명이 아니라 동일 기간 서로 다른 상대를
    구분하는 익명 대상 서명(동반자 프로필 키 등) — 배우자 감정 충돌과 친구 금전 문제가
    서로 억제되지 않게 한다.

    is_question_target: 이 관계가 질문의 직접 대상(궁합·함께보기·비교 질문)인지 —
    True인 컨텍스트의 역할이 항목 허용 밖이면 MISMATCHED(BLOCKED, fallback 금지).
    False 컨텍스트는 존재 정보일 뿐이라 불일치해도 UNKNOWN(다른 상대가 있을 수 있음).
    """

    target_role: str | None = None  # _RISK_RELATIONSHIP_ROLES 값(None=역할 미확인)
    target_id: str | None = None  # 익명 대상 서명 — 같은 상대 억제·동반자 후보 선별
    exposure_status: ExposureStatus = ExposureStatus.UNKNOWN  # 이 관계에 대한 노출
    financial_tie: bool | None = None  # 금전 거래·공동 비용·대여·보증·정산(None=미확인)
    shared_responsibility: bool | None = None  # 돌봄·재정·주거·의사결정 책임(None=미확인)
    relationship_status: str | None = None  # 교제·별거 등 상태 — R1 소비 예약
    current_contact_state: str | None = None  # 교류 상태 — R1 소비 예약
    is_question_target: bool = False


# 유효 노출 선호 순서 — 같은 항목에 매칭된 관계가 여럿이면 가장 유리한(가장 확인된)
# 상대 기준으로 후보를 만든다(둘 다 위험하면 R2 Episode가 상대별로 분리).
_EXPOSURE_PREFERENCE = {
    ExposureStatus.CONFIRMED: 3, ExposureStatus.UNKNOWN: 2,
    ExposureStatus.DENIED: 1, ExposureStatus.NOT_APPLICABLE: 0,
}


def _effective_ctx_exposure(
    item: RiskItem, ctx: RelationshipContext,
) -> ExposureStatus:
    """한 관계 컨텍스트의 유효 노출 — 실질 조건(금전 관계·공동 책임)을 반영한다.

    조건 요구 항목에서 컨텍스트 값이 False면 그 관계에 대해 DENIED(명시적 부재),
    None(미확인)이면 CONFIRMED여도 UNKNOWN으로 강등한다 — 겁재·재성만으로 "친구에게
    돈을 빌려줬다"를 추론하지 않는다(감수 16차 불변식).
    """
    policy = item.exposure_policy
    eff = ctx.exposure_status
    if policy is None:
        return eff
    for required, value in (
        (policy.requires_financial_tie, ctx.financial_tie),
        (policy.requires_shared_responsibility, ctx.shared_responsibility),
    ):
        if not required:
            continue
        if value is False:
            return ExposureStatus.DENIED
        if value is None and eff is ExposureStatus.CONFIRMED:
            eff = ExposureStatus.UNKNOWN
    return eff


@dataclass(frozen=True)
class MobilityContext:
    """현실 이동·주거 컨텍스트(감수 18차 — MOV 차수) — 프로필·질문에서 확인된 계획·상황.

    운 신호만으로 이사 계획·계약·차량·통근의 존재를 만들지 않는다: 일지 충은 이동
    영역의 구조적 활성일 뿐, "이사를 준비 중이다/차가 있다"는 이 컨텍스트가 공급한다.
    preference(desired/neutral/undesired, None=미확인)는 **적격성 미사용 — R3 표현
    전용**이다: '원치 않는 이동' 표현은 undesired 확인 시에만 허용(신호만으로 비자발
    판단 금지). assignment_authority는 R1 예약(CAR 소유권 보조).
    """

    target_type: str | None = None  # _RISK_MOBILITY_TARGET_TYPES 값(None=UNKNOWN)
    stage: str | None = None  # _RISK_MOBILITY_STAGES 값(None=UNKNOWN)
    preference: str | None = None  # desired/neutral/undesired — R3 표현 전용
    housing_tenure: str | None = None  # owner/renter/... — R1 예약
    exposure_status: ExposureStatus = ExposureStatus.UNKNOWN  # 이동 계획·상황 확인 수준
    # 익명 이동 계획 키(감수 19차) — 같은 시기의 서로 다른 계획(현 집 계약 종료 vs
    # 새 집 계약 vs 임시 숙소 vs 통근 조정)을 구분한다. 실명 주소 저장 금지.
    episode_id: str | None = None
    # 질문 직접 대상 여부(감수 19차) — True인 컨텍스트의 축이 항목 허용 밖이면
    # MISMATCHED(발령 질문에서 주거 이동 항목 차단). False 컨텍스트는 존재 정보일 뿐
    # (차량 등록만 있는 사용자의 이사 여부는 UNKNOWN — 다른 계획이 있을 수 있음).
    is_question_target: bool = False
    active_contract: bool | None = None  # stage 축이 대체 — R1 예약
    repair_responsibility: bool | None = None  # 수리 책임(하자 비용 위험 조건)
    commute_dependency: bool | None = None  # 통근 의존(통근 부담 조건)
    vehicle_exposure: bool | None = None  # 차량 노출(차량·운송 사건 조건)
    assignment_authority: bool | None = None  # 발령 권한 조직 소속 — R1 예약


def _effective_mobility_exposure(
    item: RiskItem, ctx: MobilityContext | None,
) -> ExposureStatus:
    """이동 컨텍스트의 유효 노출 — 실질 조건(수리 책임·통근 의존·차량)을 반영한다.

    관계 조건과 동일 규칙: 조건 요구 항목에서 값 False→DENIED(명시적 부재), None
    (미확인)→CONFIRMED여도 UNKNOWN 강등(존재 추론 금지). 컨텍스트 부재=UNKNOWN.
    """
    if ctx is None:
        return ExposureStatus.UNKNOWN
    policy = item.exposure_policy
    eff = ctx.exposure_status
    if policy is None:
        return eff
    for required, value in (
        (policy.requires_repair_responsibility, ctx.repair_responsibility),
        (policy.requires_commute_dependency, ctx.commute_dependency),
        (policy.requires_vehicle_exposure, ctx.vehicle_exposure),
    ):
        if not required:
            continue
        if value is False:
            return ExposureStatus.DENIED
        if value is None and eff is ExposureStatus.CONFIRMED:
            eff = ExposureStatus.UNKNOWN
    return eff


def _item_mobility_gated(item: RiskItem) -> bool:
    """이동 축·실질 조건이 있는 항목인가 — 유효 노출을 MobilityContext에서 유도."""
    if item.applicable_mobility_target_types or item.applicable_mobility_stages:
        return True
    policy = item.exposure_policy
    return policy is not None and (
        policy.requires_repair_responsibility
        or policy.requires_commute_dependency
        or policy.requires_vehicle_exposure
    )


def _resolve_mobility_all(
    item: RiskItem,
    contexts: list[MobilityContext] | None,
) -> list[tuple[str, str | None, ExposureStatus | None]]:
    """이동 축 3상태 + episode·유효 노출 유도 — **episode별** 해석 목록을 반환한다.

    미적용 항목(이동 축·조건 없음)은 [(matched, None, None — 전역 노출 사용)]. 적용
    항목: ①축이 호환(mismatch 없는)되는 컨텍스트를 episode_id별로 묶어 각각 해석
    (감수 20차 조건 4 — 같은 risk_id라도 서로 다른 이동 계획이면 후보를 분리 보존:
    CONFIRMED episode와 UNKNOWN episode가 섞이거나 exposure가 잘못 승계되는 것 차단.
    같은 episode의 중복 컨텍스트는 입력 순서 무관 결정적 병합) ②호환 컨텍스트가 없고
    질문 직접 대상 컨텍스트가 명시적으로 축 밖이면 [(mismatched — BLOCKED)] ③그 외
    [(unknown — 구조 보존)]. 컨텍스트 부재는 계획 부재(DENIED)가 아니다. 발령(CAR)
    질문이라도 별도 residential_move·commute_change 컨텍스트가 확인되면 해당 항목은
    matched로 병존한다(감수 19차 조건 6).
    """
    if not _item_mobility_gated(item):
        return [("matched", None, None)]
    ctxs = contexts or []
    groups: dict[str | None, list[tuple[bool, ExposureStatus, MobilityContext]]] = {}
    mismatch_question = False
    for ctx in ctxs:
        t = _axis_alignment(ctx.target_type, item.applicable_mobility_target_types)
        s = _axis_alignment(ctx.stage, item.applicable_mobility_stages)
        if t == "mismatched" or s == "mismatched":
            if ctx.is_question_target:
                mismatch_question = True
            continue
        fully = t == "matched" and s == "matched"
        groups.setdefault(ctx.episode_id, []).append(
            (fully, _effective_mobility_exposure(item, ctx), ctx))
    if not groups:
        if mismatch_question:
            return [("mismatched", None, ExposureStatus.UNKNOWN)]
        return [("unknown", None, ExposureStatus.UNKNOWN)]
    out: list[tuple[str, str | None, ExposureStatus | None]] = []
    for ep in sorted(groups, key=lambda e: (e is None, e or "")):
        # 같은 episode 중복 컨텍스트 — 결정적 병합(완전 매칭 > 노출 선호 > 축 값).
        fully, eff, _ctx = sorted(
            groups[ep],
            key=lambda t3: (not t3[0], -_EXPOSURE_PREFERENCE[t3[1]],
                            t3[2].target_type or "", t3[2].stage or ""),
        )[0]
        out.append((("matched" if fully else "unknown"), ep, eff))
    return out


@dataclass(frozen=True)
class HealthContext:
    """현실 건강 컨텍스트 1건(감수 21차 — HLT 차수) — 질병명·진단·부위 저장 금지.

    익명 상태값만 갖는다: 기존 질환·치료·회복·신체 부담의 실재가 확인된 경우에만
    해당 맥락 위험을 설명한다(건강 질문이라는 사실은 어느 것도 자동 확인하지 않음).
    episode_id: 같은 시기 서로 다른 건강 맥락(기존 불편 관리 vs 최근 치료 회복 vs
    교대 근무 부담)을 구분하는 익명 키 — episode별 후보 분리·수렴 경계.
    """

    context_type: str | None = None  # _RISK_HEALTH_CONTEXT_TYPES 값(None=UNKNOWN)
    condition_status: str | None = None  # none/managed/currently_uncomfortable/recently_worsened
    treatment_status: str | None = None  # none/monitoring/ongoing/recent_procedure
    recovery_status: str | None = None  # none/in_progress/recently_completed
    # none/low/moderate/high(확인 취급)·shift_or_irregular(근무 리듬 — 확인 아님)
    physical_demand: str | None = None
    schedule_load: str | None = None  # regular/shift/irregular — R3 배선 예약(리듬 부담 축)
    exposure_status: ExposureStatus = ExposureStatus.UNKNOWN
    episode_id: str | None = None
    is_question_target: bool = False


def _effective_health_exposure(item: RiskItem, ctx: HealthContext) -> ExposureStatus:
    """건강 컨텍스트의 유효 노출 — 실질 조건 4종을 반영한다.

    상태 'none'(명시 부재)→DENIED, None(미확인)→CONFIRMED여도 UNKNOWN 강등.
    physical_demand는 none·low→DENIED(직업 존재만으로 신체 부하 추론 금지).
    """
    policy = item.exposure_policy
    eff = ctx.exposure_status
    if policy is None:
        return eff
    # (요구 여부, 컨텍스트 값, 명시 부재=DENIED 집합, 확인 취급 집합) — 확인 집합
    # 밖의 값(monitoring=관찰 중, shift_or_irregular=리듬 패턴)은 확인이 아니라
    # 미확인(UNKNOWN 강등)이다: 관찰 중을 치료 중으로, 교대 근무를 신체 강도로
    # 단정하지 않는다(감수 22차).
    checks: list[tuple[bool, str | None, frozenset[str], frozenset[str]]] = [
        (policy.requires_existing_condition, ctx.condition_status,
         frozenset({"none"}),
         frozenset({"managed", "currently_uncomfortable", "recently_worsened"})),
        (policy.requires_treatment_process, ctx.treatment_status,
         frozenset({"none"}), frozenset({"ongoing", "recent_procedure"})),
        (policy.requires_recovery_process, ctx.recovery_status,
         frozenset({"none"}), frozenset({"in_progress", "recently_completed"})),
        (policy.requires_physical_demand, ctx.physical_demand,
         frozenset({"none", "low"}), frozenset({"moderate", "high"})),
    ]
    for required, value, denied_values, confirmed_values in checks:
        if not required:
            continue
        if value in denied_values:
            return ExposureStatus.DENIED
        if value not in confirmed_values and eff is ExposureStatus.CONFIRMED:
            eff = ExposureStatus.UNKNOWN
    return eff


def _item_health_gated(item: RiskItem) -> bool:
    """건강 축·실질 조건이 있는 항목인가 — 유효 노출을 HealthContext에서 유도."""
    if item.applicable_health_context_types:
        return True
    policy = item.exposure_policy
    return policy is not None and (
        policy.requires_existing_condition or policy.requires_treatment_process
        or policy.requires_recovery_process or policy.requires_physical_demand
    )


def _resolve_health_all(
    item: RiskItem,
    contexts: list[HealthContext] | None,
) -> list[tuple[str, str | None, ExposureStatus | None]]:
    """건강 축 3상태 + episode·유효 노출 유도 — episode별 해석 목록(이동과 동일 원리).

    미적용 항목은 [(matched, None, None)]. 적용 항목: 호환 컨텍스트를 episode별로
    해석(중복=결정적 병합), 질문 직접 대상이 명시적으로 축 밖이면 mismatched, 그 외
    unknown. 컨텍스트 부재는 질환·치료 부재(DENIED)가 아니다.
    """
    if not _item_health_gated(item):
        return [("matched", None, None)]
    ctxs = contexts or []
    groups: dict[str | None, list[tuple[bool, ExposureStatus, HealthContext]]] = {}
    mismatch_question = False
    for ctx in ctxs:
        t = _axis_alignment(ctx.context_type, item.applicable_health_context_types)
        if t == "mismatched":
            if ctx.is_question_target:
                mismatch_question = True
            continue
        groups.setdefault(ctx.episode_id, []).append(
            (t == "matched", _effective_health_exposure(item, ctx), ctx))
    if not groups:
        if mismatch_question:
            return [("mismatched", None, ExposureStatus.UNKNOWN)]
        return [("unknown", None, ExposureStatus.UNKNOWN)]
    out: list[tuple[str, str | None, ExposureStatus | None]] = []
    for ep in sorted(groups, key=lambda e: (e is None, e or "")):
        fully, eff, _ctx = sorted(
            groups[ep],
            key=lambda t3: (not t3[0], -_EXPOSURE_PREFERENCE[t3[1]],
                            t3[2].context_type or ""),
        )[0]
        out.append((("matched" if fully else "unknown"), ep, eff))
    return out


@dataclass(frozen=True)
class LegalProcessContext:
    """현실 법적 절차 컨텍스트 1건(감수 23차 — LEG 재검토) — 진행 중인 계약·행정·
    분쟁·소송 process를 표현한다. Selection 어휘와 별개(공통 판정기만 공유).

    process_episode_id: 같은 시기 서로 다른 절차(전세 계약 vs 사업 인허가 vs 진행
    분쟁)를 구분하는 익명 키 — episode별 후보 분리·수렴 경계.
    """

    target_type: str | None = None  # _RISK_LEGAL_TARGET_TYPES 값(None=UNKNOWN)
    stage: str | None = None  # _RISK_LEGAL_STAGES 값(None=UNKNOWN)
    exposure_status: ExposureStatus = ExposureStatus.UNKNOWN  # 절차 진행 확인 수준
    existing_dispute: bool | None = None  # 진행 중 분쟁 존재(None=미확인)
    existing_litigation: bool | None = None  # 진행 중 소송·공식 절차(None=미확인)
    document_responsibility: bool | None = None  # R1 예약
    response_obligation: bool | None = None  # R1 예약
    process_episode_id: str | None = None
    is_question_target: bool = False


def _effective_legal_exposure(
    item: RiskItem, ctx: LegalProcessContext,
) -> ExposureStatus:
    """법적 절차 컨텍스트의 유효 노출 — 기존 분쟁/소송 조건 반영(존재 추론 금지)."""
    policy = item.exposure_policy
    eff = ctx.exposure_status
    if policy is None:
        return eff
    for required, value in (
        (policy.requires_existing_dispute, ctx.existing_dispute),
        (policy.requires_existing_litigation, ctx.existing_litigation),
    ):
        if not required:
            continue
        if value is False:
            return ExposureStatus.DENIED
        if value is None and eff is ExposureStatus.CONFIRMED:
            eff = ExposureStatus.UNKNOWN
    return eff


def _item_legal_gated(item: RiskItem) -> bool:
    """법적 절차 축·조건이 있는 항목인가."""
    if item.applicable_legal_target_types or item.applicable_legal_stages:
        return True
    policy = item.exposure_policy
    return policy is not None and (
        policy.requires_existing_dispute or policy.requires_existing_litigation
    )


def _resolve_legal_all(
    item: RiskItem,
    contexts: list[LegalProcessContext] | None,
) -> list[tuple[str, str | None, ExposureStatus | None]]:
    """법적 절차 축 3상태 + episode·유효 노출 — episode별 해석(이동·건강과 동일 원리).

    closed stage(감수 23차 커밋 조건 — 데굴님 권장 10): 종결된 절차 컨텍스트는 항목이
    stage 목록에 'closed'를 명시(opt-in)하지 않는 한 어떤 LEG 항목과도 매칭되지
    않는다 — stage 축을 제한하지 않는 항목(빈 목록=무관)도 예외가 아니다. 종결 계약이
    신규 문서·행정·분쟁 후보를 만들거나 흡수하는 경로 차단(사후 정산·청구는 별도
    episode·별도 stage 컨텍스트로 병존).
    """
    if not _item_legal_gated(item):
        return [("matched", None, None)]
    ctxs = contexts or []
    groups: dict[str | None, list[tuple[bool, ExposureStatus, LegalProcessContext]]] = {}
    mismatch_question = False
    for ctx in ctxs:
        t = _axis_alignment(ctx.target_type, item.applicable_legal_target_types)
        s = _axis_alignment(ctx.stage, item.applicable_legal_stages)
        if ctx.stage == "closed" and "closed" not in item.applicable_legal_stages:
            s = "mismatched"  # closed는 명시 opt-in — 무관(빈 목록) 항목도 비매칭.
        if t == "mismatched" or s == "mismatched":
            if ctx.is_question_target:
                mismatch_question = True
            continue
        groups.setdefault(ctx.process_episode_id, []).append(
            (t == "matched" and s == "matched",
             _effective_legal_exposure(item, ctx), ctx))
    if not groups:
        if mismatch_question:
            return [("mismatched", None, ExposureStatus.UNKNOWN)]
        return [("unknown", None, ExposureStatus.UNKNOWN)]
    out: list[tuple[str, str | None, ExposureStatus | None]] = []
    for ep in sorted(groups, key=lambda e: (e is None, e or "")):
        fully, eff, _ctx = sorted(
            groups[ep],
            key=lambda t3: (not t3[0], -_EXPOSURE_PREFERENCE[t3[1]],
                            t3[2].target_type or "", t3[2].stage or ""),
        )[0]
        out.append((("matched" if fully else "unknown"), ep, eff))
    return out


def _resolve_relationship(
    item: RiskItem,
    contexts: list[RelationshipContext] | None,
    default_exposure: ExposureStatus,
) -> tuple[str, str | None, str | None, ExposureStatus]:
    """관계 축 3상태 + 유효 노출 유도 → (alignment, role, target_id, exposure).

    관계 역할·실질 조건이 없는 항목은 관계 축과 무관하다(matched, 전역 노출 사용).
    역할 지정 항목: ①허용 역할의 컨텍스트가 있으면 matched — 가장 확인된 상대 기준
    ②없고, 질문 직접 대상(is_question_target)의 확인된 역할이 허용 밖이면 mismatched
    (BLOCKED) ③그 외는 unknown — 유효 노출 UNKNOWN(구조 보존, 조건부 표현 가부는
    exposurePolicy 소관). 컨텍스트 부재는 관계 부재(DENIED)가 아니다.
    """
    policy = item.exposure_policy
    needs_context = bool(item.applicable_relationship_roles) or (
        policy is not None
        and (policy.requires_financial_tie or policy.requires_shared_responsibility)
    )
    if not needs_context:
        return "matched", None, None, default_exposure
    allowed = item.applicable_relationship_roles
    ctxs = contexts or []
    matching = [
        c for c in ctxs
        if c.target_role is not None and (not allowed or c.target_role in allowed)
    ]
    if not matching:
        if any(
            c.is_question_target and c.target_role is not None
            and allowed and c.target_role not in allowed
            for c in ctxs
        ):
            return "mismatched", None, None, ExposureStatus.UNKNOWN
        return "unknown", None, None, ExposureStatus.UNKNOWN
    scored = [(_effective_ctx_exposure(item, c), c) for c in matching]
    eff, best = max(scored, key=lambda pair: _EXPOSURE_PREFERENCE[pair[0]])
    return "matched", best.target_role, best.target_id, eff


@dataclass(frozen=True)
class RelationFact:
    """시점의 관계 발동 원시 사실 1건(합충형파해·복음, 자극 궁성·피자극 십성 포함).

    target_ten_god: 원국 피자극 글자의 십성 — 충·형·공망은 존재만으로 위험 도메인을 못
    정하므로(재성 충 ≠ 배우자궁 충 ≠ 사회궁 충) '무엇을 쳤는가'를 근거에 보존한다
    (2026-07-15 감수 — R0 근거 정확도 문제). 일간 등 십성 미정의는 None.
    """

    kind: RelationKind
    palace: Pillar4
    position: str = "branch"  # 'stem' | 'branch' (피자극 자리 slot)
    target_ten_god: TenGod | None = None  # 피자극 글자(궁성의 천간/지지 본기) 십성
    target_letter: str | None = None  # 피자극 글자 자체(한자 천간/지지) — 정밀 매칭용


@dataclass(frozen=True)
class RawPeriodFacts:
    """한 시점의 원시 신호 스냅샷 — 위험 엔진 전용 입력 (Raw Signal Ledger 단위).

    EventEngineV2._score_target이 모디파이어 적용 **이전** 재료(신호·관계 적중·시점 극성·
    운성·공망)에서 그대로 구성한다. 긍정 후보가 하나도 없어도 위험 근거는 남는다.
    """

    period_key: str  # '2026' / '2026-09' 등 운 기간 라벨
    layer: LuckLayer  # 채점 대상 층위(세운/월운/일운/대운)
    ten_god_layers: dict[TenGod, frozenset[LuckLayer]]  # 유입 십성 → 관측 층위들
    relations: tuple[RelationFact, ...]  # 관계 발동 사실(공망류 제외)
    void_active: bool  # 공망 활성(충발·해공 포함 상태 아님 — 활성 여부만)
    polarity_role: PolarityRole  # 시점 유입 글자의 용기신 극성(化/制 반영)
    twelve_stage: TwelveStage | None  # 대상 기둥 지지 12운성


_ROLE_SECTIONS: tuple[tuple[EvidenceRole, str], ...] = (
    (EvidenceRole.TRIGGER, "trigger_rules"),
    (EvidenceRole.AMPLIFIER, "amplifier_rules"),
    (EvidenceRole.MITIGATOR, "mitigator_rules"),
    (EvidenceRole.BLOCKER, "blocker_rules"),
)


@dataclass(frozen=True)
class _Match:
    """룰 매칭 결과 — 원인 사실 서명과 부가 정보."""

    source: str  # 원인 사실 서명(독립 출처·중복 방지 키)
    layer: str  # 근거 층위 표기
    palace: str | None  # 자극 궁성(관계 조건일 때)


class RiskEngine:
    """risks/ 사전을 로드해 원시 신호 스냅샷에서 원자 위험 후보를 생성한다."""

    def __init__(self, dictionaries_dir: Path) -> None:
        """risks/<domain>.json 전체를 로드한다.

        Args:
            dictionaries_dir: 사전 원본 루트(backend/dictionaries).

        Raises:
            FileNotFoundError: risks/ 디렉토리가 없을 때(호출부가 graceful 처리).
        """
        risks_dir = dictionaries_dir / "risks"
        if not risks_dir.is_dir():
            raise FileNotFoundError(f"위험 사전 디렉토리 없음: {risks_dir}")
        self._items: list[RiskItem] = []
        for path in sorted(risks_dir.glob("*.json")):
            file = RiskMappingFile.model_validate(
                json.loads(path.read_text(encoding="utf-8"))
            )
            self._items.extend(file.items)

    # ── 공개 API ─────────────────────────────────────────────────

    def generate(
        self,
        facts: RawPeriodFacts,
        exposure_status: ExposureStatus = ExposureStatus.UNKNOWN,
        selection_context: SelectionContext | None = None,
        selection_contexts: list[SelectionContext] | None = None,
        relationship_contexts: list[RelationshipContext] | None = None,
        mobility_contexts: list[MobilityContext] | None = None,
        health_contexts: list[HealthContext] | None = None,
        legal_contexts: list[LegalProcessContext] | None = None,
    ) -> list[RiskCandidate]:
        """한 시점의 원시 신호에서 원자 위험 후보를 생성한다.

        단계(2026-07-15 감수 2차):
        1) 룰 매칭·근거 수집(중복 제거). trigger가 하나도 없으면 관측 자체가 없음(미생성).
        2) 증거 계약 — 개수(trigger_count·독립 원인 수) + 그룹(evidenceContract anyOf
           또는 requiredGroups). 미충족이면 삭제하지 않고 INSUFFICIENT_EVIDENCE로 보존
           (observed 통계와 활성 집계 분리).
        3) 차단 — blocker 근거(대상 부재 등 동시 존재 가능한 차단 조건) 또는 사용자
           노출 DENIED/NOT_APPLICABLE(hard blocker)이면 BLOCKED.
        4) 완화 — mitigator 동반이면 MITIGATED(후보 유지, 강도 하향은 R1). 아니면 ELIGIBLE.
        5) 특이도 억제 — 동일 기간·동일 risk_family·원인 공유 시 가장 구체적인 후보를
           대표로 남기고 하위 일반 후보는 suppressed_by_specificity로 흡수(활성 제외).

        Args:
            facts: 원시 신호 스냅샷.
            exposure_status: 사용자 노출 상태 — R0 기본 UNKNOWN(프로필 배선은 R1/R5).
                미입력을 숫자 중간값으로 대체하지 않는다. 관계 역할이 지정된 항목은
                이 전역값 대신 relationship_contexts에서 유효 노출을 유도한다.
            selection_context: 현실 선발 컨텍스트 1건(감수 14차 — 단수 하위 호환:
                selection_contexts=[ctx]와 결과 동일, 내부에서 목록으로 정규화).
            selection_contexts: 확인된 선발 건 목록(감수 25차 — SEL-e): 같은 시기
                복수 선발 episode(채용+자격시험+추첨, 같은 유형 2건 포함)를
                episode_id로 구분해 병존시킨다. 미제공은 선발 정보 부재(UNKNOWN).
            relationship_contexts: 확인된 현실 관계 목록(감수 16차) — 미제공(None/[])은
                관계 정보 부재(UNKNOWN)이지 관계 부재(DENIED)가 아니다.
            mobility_contexts: 확인된 이동·주거 컨텍스트 목록(감수 18·19차 — 같은
                시기 복수 계획 지원, episode_id로 구분). 미제공은 계획 정보 부재
                (UNKNOWN)이지 계획 부재(DENIED)가 아니다.
            health_contexts: 확인된 건강 컨텍스트 목록(감수 21차 — 익명 상태값·
                episode_id). 미제공은 질환·치료 부재(DENIED)가 아니다.
            legal_contexts: 확인된 법적 절차 컨텍스트 목록(감수 23차 — process
                episode). 미제공은 절차 부재(DENIED)가 아니다.

        Returns:
            생성된 원자 RiskCandidate 목록(관측 후보 포함 — 활성 판정은 is_active).
        """
        out: list[RiskCandidate] = []
        for item in self._items:
            evidences: list[RiskEvidence] = []
            for role, section in _ROLE_SECTIONS:
                rules: list[RiskRuleSpec] = getattr(item, section)
                for rule in rules:
                    m = self._match(rule, facts)
                    if m is None:
                        continue
                    evidences.append(RiskEvidence(
                        evidence_id=f"{facts.period_key}|{m.source}",
                        code=rule.id,
                        period_key=facts.period_key,
                        layer=m.layer,
                        source=m.source,
                        strength=rule.strength,
                        role=role,
                        source_group=rule.group,
                        target_domain=RiskDomain(item.domain),
                        target_palace=m.palace,
                    ))
            evidences = dedupe_evidence(evidences)
            triggers = [e for e in evidences if e.role is EvidenceRole.TRIGGER]
            if not triggers:
                continue  # 관측 없음 — 후보 자체를 만들지 않는다.
            # RelationshipContext(감수 16차) — 관계 역할 지정 항목의 유효 노출은 전역
            # 파라미터가 아니라 매칭된 현실 관계에서 유도한다(존재 추론 금지).
            rel_alignment, rel_role, rel_target_id, rel_exposure = (
                _resolve_relationship(item, relationship_contexts, exposure_status)
            )
            # SelectionContext(감수 14차 → 25차 SEL-e) — episode별 해석 목록:
            # MISMATCHED는 명시적 부적용(BLOCKED — 단, 호환 episode가 있으면 그
            # episode가 우선·mismatch 전파 금지). UNKNOWN은 구조 보존. 단수
            # selection_context는 목록으로 정규화(두 입력 형태 결과 동일).
            sel_ctxs = list(selection_contexts or [])
            if selection_context is not None:
                sel_ctxs.append(selection_context)
            # MobilityContext(감수 18~20차) — episode별 해석 목록: 같은 risk_id라도
            # 서로 다른 이동 계획이면 후보를 분리 보존한다(각 후보의 exposure·stage·
            # episode 독립 — identity는 risk_id+period+episode).
            # 컨텍스트 해석 곱(감수 21차) — 항목은 실제로 한 컨텍스트 축만 게이트
            # 한다(미적용 축은 (matched, None, None) 단일 해석이라 곱이 1이 된다).
            combos = [
                (s, m, h, lg)
                for s in _resolve_selection_all(item, sel_ctxs)
                for m in _resolve_mobility_all(item, mobility_contexts)
                for h in _resolve_health_all(item, health_contexts)
                for lg in _resolve_legal_all(item, legal_contexts)
            ]
            for (
                alignment, sel_episode_id, sel_exposure, sel_conflict,
                sel_mismatch_axes,
            ), (mob_alignment, mob_episode_id, mob_exposure), (
                hlt_alignment, hlt_episode_id, hlt_exposure,
            ), (leg_alignment, leg_episode_id, leg_exposure) in combos:
                # 유효 노출 우선순위: 법적 절차 > 건강 > 이동 > 선발 > 관계 > 전역.
                effective_exposure = rel_exposure
                if sel_exposure is not None:
                    effective_exposure = sel_exposure
                if mob_exposure is not None:
                    effective_exposure = mob_exposure
                if hlt_exposure is not None:
                    effective_exposure = hlt_exposure
                if leg_exposure is not None:
                    effective_exposure = leg_exposure
                status, reasons = self._evaluate(
                    item, evidences, triggers, effective_exposure,
                )
                if alignment == "mismatched":
                    status = EligibilityStatus.BLOCKED
                    reasons = list(reasons) + [
                        f"selection_{name}_mismatch" for name in sel_mismatch_axes
                    ]
                if sel_conflict:
                    # 데이터 위생 로그 — 구조 보존, 노출은 is_exposable이 차단.
                    reasons = list(reasons) + ["selection_context_conflict"]
                # 이동 축 MISMATCHED(감수 18·19차) — 질문 직접 대상의 계획이 항목 축
                # 밖(발령 질문에서 주거 이동 항목 등). fallback 없이 차단. UNKNOWN의
                # 노출 차등은 is_exposable이 exposure_requirement로 판정.
                if mob_alignment == "mismatched":
                    status = EligibilityStatus.BLOCKED
                    reasons = list(reasons) + ["mobility_target_mismatch"]
                # 건강 축 MISMATCHED(감수 21차) — 질문 직접 대상 맥락이 항목 축 밖.
                if hlt_alignment == "mismatched":
                    status = EligibilityStatus.BLOCKED
                    reasons = list(reasons) + ["health_context_mismatch"]
                # 법적 절차 축 MISMATCHED(감수 23차).
                if leg_alignment == "mismatched":
                    status = EligibilityStatus.BLOCKED
                    reasons = list(reasons) + ["legal_process_mismatch"]
                # 관계 축 MISMATCHED — 질문 직접 대상의 역할이 항목 허용 밖(궁합
                # 대상이 사업 파트너인데 배우자 전용 항목 등). fallback 없이 차단.
                if rel_alignment == "mismatched":
                    status = EligibilityStatus.BLOCKED
                    reasons = list(reasons) + ["relationship_role_mismatch"]
                out.append(RiskCandidate(
                    risk_id=item.risk_id,
                    domain=RiskDomain(item.domain),
                    kind=RiskKind(item.kind),
                    risk_family=item.risk_family,
                    period_key=facts.period_key,
                    manifestation_ids=[m.id for m in item.manifestations],
                    evidence=evidences,
                    score_components=None,  # R1에서 산출
                    exposure_status=effective_exposure,
                    exposure_requirement=(
                        item.exposure_policy.requirement
                        if item.exposure_policy is not None else "not_required"
                    ),
                    confidence=0.0,  # R1에서 산출
                    eligibility_status=status,
                    suppression_reasons=reasons,
                    specificity_rank=_specificity_rank(item),
                    selection_alignment=alignment,
                    selection_episode_id=sel_episode_id,
                    selection_context_conflict=sel_conflict,
                    mobility_alignment=mob_alignment,
                    mobility_episode_id=mob_episode_id,
                    mobility_stages=list(item.applicable_mobility_stages),
                    mobility_gated=_item_mobility_gated(item),
                    health_alignment=hlt_alignment,
                    health_episode_id=hlt_episode_id,
                    legal_alignment=leg_alignment,
                    legal_episode_id=leg_episode_id,
                    legal_stages=list(item.applicable_legal_stages),
                    relationship_alignment=rel_alignment,
                    relationship_role=rel_role,
                    relationship_target_id=rel_target_id,
                    selection_stages=list(item.applicable_selection_stages),
                    # UNKNOWN 노출 차등(감수 17차) — 역할 특정 관계 항목은 관계가 확인
                    # 되거나 질문 대상일 때(alignment=matched)만 조건부 노출 가능. 총운·
                    # 재물운처럼 관계가 질문 대상이 아닌 컨텍스트에서 partner·peer 후보가
                    # 상시 조건부 경고로 반복 노출되는 것을 기계적으로 차단한다.
                    exposable_when_unknown=(
                        (item.exposure_policy.unknown_exposable
                         if item.exposure_policy is not None else True)
                        and (rel_alignment == "matched"
                             or not item.applicable_relationship_roles)
                    ),
                    absorbed_role_hint=item.absorbed_role_hint,
                    # 교차 도메인 연결 키(감수 17차) — 같은 원인의 FIN·REL 병존 후보를
                    # R1(중복 1회 점수)·R2(episode 병합·대표 1개)가 연결하는 재료.
                    trigger_cause_atoms=sorted(
                        {a for e in triggers for a in cause_atoms(e.source)}
                    ),
                ))
        return _apply_specificity_suppression(out)

    @staticmethod
    def _evaluate(
        item: RiskItem,
        evidences: list[RiskEvidence],
        triggers: list[RiskEvidence],
        exposure_status: ExposureStatus,
    ) -> tuple[EligibilityStatus, list[str]]:
        """증거 계약·차단·완화를 평가해 (적격 상태, 사유 목록)을 반환한다."""
        contract = item.evidence_contract
        min_causes = (
            contract.min_independent_causes if contract is not None
            else item.minimum_evidence.independent_source_count
        )
        trigger_groups = {e.source_group for e in triggers}
        if contract is not None:
            groups_ok = any(
                set(clause.all_of_groups) <= trigger_groups
                for clause in contract.any_of
            )
        else:
            groups_ok = all(
                g in trigger_groups for g in item.minimum_evidence.required_groups
            )
        insufficient: list[str] = []
        if len(triggers) < item.minimum_evidence.trigger_count:
            insufficient.append("trigger_count_unmet")
        if independent_source_count(evidences) < min_causes:
            insufficient.append("independent_causes_unmet")
        if not groups_ok:
            insufficient.append("evidence_groups_unmet")
        if (
            contract is not None and contract.requires_linked_targets and groups_ok
            and not _targets_linked(triggers)
        ):
            insufficient.append("targets_unlinked")
        if insufficient:
            return EligibilityStatus.INSUFFICIENT_EVIDENCE, insufficient
        # hard blocker — 대상·노출 부재는 위험 신호와 동시에 존재할 수 있는 차단 조건.
        blockers = [e.code for e in evidences if e.role is EvidenceRole.BLOCKER]
        if exposure_status is ExposureStatus.DENIED:
            blockers.append("exposure_denied")
        if exposure_status is ExposureStatus.NOT_APPLICABLE:
            blockers.append("exposure_not_applicable")
        if blockers:
            return EligibilityStatus.BLOCKED, blockers
        # 원인별 완화(2026-07-15 감수 3차) — 용희신이 강하다는 극성 사실 '단독'으로는
        # 상태를 완화하지 않는다(전역 완화 금지). 극성 단독 mitigator는 근거로만 보존하고,
        # 실질 조건(관계 완화·통관 십성 등 — 원인·대상 제어를 표현)이 동반된 mitigator만
        # MITIGATED로 전환한다. 투간·통근 작동성(operability) 연동은 R1에서 확장한다.
        substantive_mitigation = any(
            e.role is EvidenceRole.MITIGATOR
            and any(not atom.startswith("polarity:") for atom in cause_atoms(e.source))
            for e in evidences
        )
        if substantive_mitigation:
            return EligibilityStatus.MITIGATED, []
        return EligibilityStatus.ELIGIBLE, []

    # ── 룰 매칭 ───────────────────────────────────────────────────

    def _match(self, rule: RiskRuleSpec, facts: RawPeriodFacts) -> _Match | None:
        """룰 조건(전부 AND)을 원시 사실과 대조한다. 통과 시 원인 사실 서명을 만든다.

        source(서명)는 매칭 **룰**이 아니라 바탕 **사실**을 표현한다 — 서로 다른 룰이 같은
        사실을 잡으면 서명이 같아 evidence_id 중복 제거·독립 출처 1개 계산이 성립한다.
        """
        parts: list[str] = []
        layers: list[str] = []
        palace: str | None = None

        if rule.ten_god is not None:
            god = TenGod(rule.ten_god)
            god_layers = facts.ten_god_layers.get(god)
            if not god_layers:
                return None
            parts.append(f"ten_god:{god.value}")
            layers.append("+".join(sorted(la.value for la in god_layers)))

        if rule.ten_god_group is not None:
            matched = sorted(
                g.value for g in facts.ten_god_layers
                if TEN_GOD_GROUP[g].value == rule.ten_god_group
            )
            if not matched:
                return None
            parts.append("ten_god:" + "+".join(matched))
            group_layers = {
                la.value
                for g in facts.ten_god_layers
                if TEN_GOD_GROUP[g].value == rule.ten_god_group
                for la in facts.ten_god_layers[g]
            }
            layers.append("+".join(sorted(group_layers)))

        if rule.relation is not None:
            kind = RelationKind(rule.relation)
            hits = [
                r for r in facts.relations
                if r.kind is kind and (
                    rule.relation_palace is None
                    or r.palace.value == rule.relation_palace
                )
            ]
            # 대상 조건 — '무엇을 충·형했는가'(피자극 십성). 충·형은 존재만으로 도메인을
            # 못 정하므로 대상 필터가 있으면 피자극 십성/십성군이 일치하는 발동만 남긴다.
            if rule.relation_target_ten_god is not None:
                want = TenGod(rule.relation_target_ten_god)
                hits = [r for r in hits if r.target_ten_god is want]
            if rule.relation_target_ten_god_group is not None:
                hits = [
                    r for r in hits
                    if r.target_ten_god is not None
                    and TEN_GOD_GROUP[r.target_ten_god].value == (
                        rule.relation_target_ten_god_group
                    )
                ]
            if rule.relation_target_letter is not None:
                hits = [r for r in hits if r.target_letter == rule.relation_target_letter]
            if not hits:
                return None
            # 정규화된 대상 서명(감수 9차) — 독립 대상 판정을 '다른 글자'가 아니라
            # 궁위+자리+글자+십성의 대상 객체 서명으로 한다. 같은 충을 잡은 일반 룰과
            # 대상 룰은 같은 hits를 집계하므로 서명이 같다(같은 원인 = 같은 서명).
            palaces = sorted({r.palace.value for r in hits})
            positions = sorted({r.position for r in hits})
            letters = sorted({r.target_letter for r in hits if r.target_letter})
            gods = sorted({
                r.target_ten_god.value for r in hits if r.target_ten_god is not None
            })
            sig_parts = [f"relation:{kind.value}", "+".join(palaces), "+".join(positions)]
            if letters:
                sig_parts.append("+".join(letters))
            if gods:
                sig_parts.append("+".join(gods))
            parts.append(":".join(sig_parts))
            layers.append(facts.layer.value)
            palace = palaces[0] if len(palaces) == 1 else None

        if rule.polarity_role_in is not None:
            if facts.polarity_role.value not in rule.polarity_role_in:
                return None
            parts.append(f"polarity:{facts.polarity_role.value}")
            layers.append(_PERIOD_LAYER)

        if rule.void_active is not None:
            if facts.void_active != rule.void_active:
                return None
            parts.append("void" if rule.void_active else "no_void")
            layers.append(_PERIOD_LAYER)

        if rule.twelve_stage_in is not None:
            if facts.twelve_stage is None:
                return None
            if facts.twelve_stage.value not in rule.twelve_stage_in:
                return None
            parts.append(f"stage:{facts.twelve_stage.value}")
            layers.append(facts.layer.value)

        if not parts:  # 무조건 룰은 스키마에서 거부되지만 방어적으로 차단.
            return None
        return _Match(
            source="&".join(parts),
            layer="&".join(dict.fromkeys(layers)),
            palace=palace,
        )


def build_raw_period_facts(
    *,
    period_key: str,
    layer: LuckLayer,
    ten_god_layers: dict[TenGod, set[LuckLayer]],
    relations: list[RelationFact],
    void_active: bool,
    polarity_role: PolarityRole,
    twelve_stage: TwelveStage | None,
) -> RawPeriodFacts:
    """원시 사실 재료 → RawPeriodFacts 스냅샷(불변화)."""
    return RawPeriodFacts(
        period_key=period_key,
        layer=layer,
        ten_god_layers={g: frozenset(ls) for g, ls in ten_god_layers.items()},
        relations=tuple(relations),
        void_active=void_active,
        polarity_role=polarity_role,
        twelve_stage=twelve_stage,
    )


__all__ = [
    "RawPeriodFacts",
    "RelationFact",
    "RiskEngine",
    "SelectionContext",
    "build_raw_period_facts",
    "cause_atoms",
]
