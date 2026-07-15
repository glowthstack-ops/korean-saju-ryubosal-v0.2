"""위험 탐지 엔진(Risk Engine) 타입 — R0 (doc/v2_2/RISK_ENGINE.md).

기회 후보(EventCandidateV2)와 독립된 위험 후보 계층. 핵심 계약:

- 위험 엔진의 입력은 **reducer·모디파이어 이전의 원시 신호**다(감점·floor·Top-N을 거친
  최종 후보를 소비하면 위험 근거가 이미 손실됨).
- `RiskCandidate`(원자, 단일 period_key)와 `RiskEpisode`(R2 기간 병합 결과)는 별도 타입 —
  원자 후보 생성과 기간 병합의 책임을 섞지 않는다.
- 근거는 문자열 코드가 아니라 구조화 provenance(`RiskEvidence`)로 남기며, `evidence_id`로
  동일 원인의 중복 반영을 차단한다(동일 원인 파생 신호는 독립 출처 1개로 계산).
- protection(현재 완충 — 점수 차감 대상)과 recovery(사후 회복 — 별도 창 산출, 현재 위험
  점수에서 빼지 않음)는 분리한다.
- `risk_level`(얼마나 주의할 문제인가)과 `confidence`(근거가 얼마나 충분한가)는 독립 축.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class RiskEngineMode(StrEnum):
    """위험 엔진 게이트 3단계.

    OFF: 계산하지 않음 — 기존 출력 byte-identical.
    SHADOW: 계산하되 사용자 답변·리포트·LLM 입력·토큰에 일절 주입하지 않음(구조화 로그 전용).
    EXPOSE: 선별·임계값을 통과한 위험만 사용자 노출(R3 이후, 세분 게이트 별도).
    """

    OFF = "off"
    SHADOW = "shadow"
    EXPOSE = "expose"


class RiskDomain(StrEnum):
    """위험 도메인 7종 (RISK_ENGINE.md §3)."""

    FINANCE = "finance"
    CAREER = "career"
    CONTRACT_LEGAL = "contract_legal"
    HEALTH_SAFETY = "health_safety"
    RELATIONSHIP = "relationship"
    RELOCATION = "relocation"
    SELECTION = "selection"


class RiskKind(StrEnum):
    """위험 종류 3분류 — 시기적 압박 ≠ 취약성 ≠ 사건 위험 (RISK_ENGINE.md §2).

    PRESSURE: 특정 사건을 특정하지 않는 전반적 부담·소모(피로·긴장·비용 증가).
    VULNERABILITY: 특정 영역의 보호력이 약해진 상태(검토력·완충력 저하) — 사용자에게 별도
        사건처럼 노출하지 않고, incident_risk 생성·심각도 상향의 중간 신호로 쓴다.
    INCIDENT_RISK: 구체적 사건 가능성이 형성된 상태(계약 취소·지급 지연·배치 불이익 등).
    """

    PRESSURE = "pressure"
    VULNERABILITY = "vulnerability"
    INCIDENT_RISK = "incident_risk"


class EvidenceRole(StrEnum):
    """근거 역할 — 모든 불리 신호를 단일 감점으로 합치지 않기 위한 4분류."""

    TRIGGER = "trigger"  # 위험 발생 근거
    AMPLIFIER = "amplifier"  # 위험 강도 증가
    MITIGATOR = "mitigator"  # 보호·완화(현재 완충 — protection 축)
    BLOCKER = "blocker"  # 해당 위험의 발현 제한


class ExposureStatus(StrEnum):
    """사용자 현실 노출 상태 — 미입력을 중간값 숫자로 대체하지 않는다(RISK_ENGINE.md §7).

    UNKNOWN이면 위험을 삭제하지 않되 risk_level 상한을 warning으로 제한하고 조건부
    표현("현재 해당 활동을 하고 있다면")으로 서술한다. CRITICAL은 CONFIRMED에서만 허용.
    """

    CONFIRMED = "confirmed"
    DENIED = "denied"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class RiskLevel(StrEnum):
    """노출 밴드 — 사용자 노출 방식이 다른 4등급. CRITICAL은 다중 조건 동시 충족 시만.

    사용자 노출 문구에서 내부 명칭(critical)을 그대로 쓰지 않고 "강한 주의가 필요한 시기"
    수준으로 변환한다(건강·법률·재정 영역 특히).
    """

    ADVISORY = "advisory"  # 약한 부담·초기 신호 — 참고
    WATCH = "watch"  # 주의 가능성 — 체크 사항 제공
    WARNING = "warning"  # 여러 신호 중첩 — 주요 위험으로 노출
    CRITICAL = "critical"  # 고영향·노출 확인·근접 시점 — 최상단 경고


class EligibilityStatus(StrEnum):
    """후보 적격 상태 — blocker/mitigator를 근거로만 남기지 않고 상태로 분리한다
    (RISK_ENGINE.md §불변식, 2026-07-15 감수 2차 개정).

    'matched'는 룰 평가 결과일 뿐 후보 적격 상태가 아니다 — 룰 일부가 매칭됐지만 증거
    계약을 못 채운 후보는 INSUFFICIENT_EVIDENCE로 남겨 밀도 통계(observed)와 활성
    집계를 분리한다.

    불변식: blocker는 후보 기록을 삭제하지 않지만 활성 위험 집계(R2 슬롯·R4 오경고
    분모)에서는 제외한다. mitigator는 후보를 유지하고 강도만 낮춘다(R1).
    recovery는 현재 후보의 적격성·점수를 낮추지 않는다.
    """

    INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # 일부 룰 매칭·증거 계약 미충족
    ELIGIBLE = "eligible"  # 활성 — 증거 계약 충족, 차단·완화 없음
    MITIGATED = "mitigated"  # 활성 — 보호 신호 동반(강도 하향은 R1)
    BLOCKED = "blocked"  # 비활성 — 노출 부재·대상 부재 등 발현 차단(기록 보존)


class RiskEvidence(BaseModel):
    """위험 근거 1건 — 구조화 provenance.

    evidence_id는 매칭 룰이 아니라 **바탕 원인 사실**의 식별자(period|source)다. 서로 다른
    룰이 같은 원인 사실을 잡으면 evidence_id가 같아 중복 반영이 차단된다(독립 출처 판정도
    source 기준). code는 매칭된 사전 룰 id(추적용)로 별도 보존한다.
    """

    evidence_id: str  # 원인 사실 식별자 — "{period_key}|{source}" (중복 반영 방지 키)
    code: str  # 매칭된 사전 룰 id (추적용 — 독립 출처 판정에 쓰지 않는다)
    period_key: str  # '2026' / '2026-09' 등 운 기간 라벨
    layer: str  # 신호 층위(daewoon/sewoon/wolwoon/ilwoon, 복합이면 '+' 연결, 시점 극성='period')
    source: str  # 원인 사실 서명 — 예: 'relation:CHUNG:branch:day_pillar', 'polarity:GI_STRONG'
    strength: float = Field(ge=0.0, le=1.0)  # 사전 룰의 기여 강도(0~1 정규화)
    role: EvidenceRole
    # 신호 역할 그룹(사전 룰의 group) — event_shape(사건 형태)/target_activation(대상 활성)/
    # activation(발동)/generic. minimum_evidence.required_groups 판정에 쓴다(§신호 역할 매트릭스).
    source_group: str | None = None
    target_domain: RiskDomain | None = None
    target_palace: str | None = None  # 자극 궁성(year/month/day/hour_pillar)


class RiskScoreComponents(BaseModel):
    """위험 점수 6축 — R1에서 산출(전 축 0~1 정규화). R0에서는 채우지 않는다(None).

    불변식(RISK_ENGINE.md §5): 한 evidence_id는 occurrence 직접 점수에 한 번만 반영,
    persistence는 기간 반복 횟수만, compound는 별도의 다른 risk_id 연결이 있을 때만.
    recovery(사후 회복)는 여기서 빼지 않는다 — protection(현재 완충)만 차감 축이다.
    """

    occurrence: float = Field(ge=0.0, le=1.0)  # 운 신호로부터의 발생 가능성
    impact: float = Field(ge=0.0, le=1.0)  # 사전의 사건별 기본 피해 prior
    exposure: float = Field(ge=0.0, le=1.0)  # 사용자 현실 노출(ExposureStatus 기반)
    persistence: float = Field(ge=0.0, le=1.0)  # 기간 반복성
    compound: float = Field(ge=0.0, le=1.0)  # 다른 위험으로의 확산 가능성
    protection: float = Field(ge=0.0, le=1.0)  # 현재 완충력(mitigator 근거)


class RiskCandidate(BaseModel):
    """원자 위험 후보 — 단일 기간(period_key) 1건. 기간 병합 결과는 RiskEpisode(별도 타입).

    R0에서는 생성·근거 수집까지만 하고 점수(score_components)·등급·확신도는 채우지 않는다.
    """

    risk_id: str  # 위험 사전 키 — 예: 'FIN_CASHFLOW_PRESSURE' (EventKeyV2와 별도 네임스페이스)
    domain: RiskDomain
    kind: RiskKind
    risk_family: str | None = None  # 교차 도메인 중복 통합 키(특이도 억제·R2 병합)
    period_key: str  # 원자 후보는 단일 기간 라벨만 갖는다(start/peak/end는 Episode 소관)
    manifestation_ids: list[str] = Field(default_factory=list)  # 가능한 발현 형태 id
    evidence: list[RiskEvidence] = Field(default_factory=list)  # 구조화 근거(전 역할)
    score_components: RiskScoreComponents | None = None  # R1에서 산출 — R0는 None
    exposure_status: ExposureStatus = ExposureStatus.UNKNOWN
    # 항목의 노출 요구 수준(사전 exposurePolicy.requirement) — 밀도 단계 분리·R1 소비:
    # not_required / required_for_warning / required_for_exposure / confirmed_required.
    exposure_requirement: str = "not_required"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)  # 근거 충분도 — R1 산출(R0=0.0)
    # 적격 상태 — blocked·insufficient 후보는 기록을 보존하되 활성 집계에서 제외한다.
    eligibility_status: EligibilityStatus = EligibilityStatus.ELIGIBLE
    suppression_reasons: list[str] = Field(default_factory=list)  # 차단·미충족 사유
    # 특이도 우선 억제(2026-07-15 감수) — 동일 원인·동일 family·동일 기간에서 더 구체적
    # 위험이 있으면 하위 일반 후보를 대표 후보에 흡수한다(별도 활성 후보 아님).
    specificity_rank: int = 0  # 구체 대상 사건 3 > 도메인 일반 2 > 취약성 1 > 압박 0
    primary_risk_id: str | None = None  # 흡수된 경우 대표 위험의 risk_id
    suppressed_by_specificity: str | None = None  # 억제 사유(대표 risk_id — 활성 집계 제외)
    # SelectionContext 3상태(감수 14차) — matched/unknown/mismatched. mismatched는
    # BLOCKED로 이어지며, unknown은 구조 보존 + mode·stage 특정 표현 금지.
    selection_alignment: str = "matched"
    # 항목의 stage 메타(사전 applicableSelectionStages 복사) — stage-aware suppression용.
    selection_stages: list[str] = Field(default_factory=list)
    # UNKNOWN 노출 가부(사전 exposurePolicy.unknownExposable) — is_exposable이 소비.
    exposable_when_unknown: bool = True
    # 흡수 후보의 역할(2026-07-15 감수 3차) — 흡수는 삭제가 아니라 역할 전환이다.
    # R1에서 대표 후보의 impact/exposure 계산·보조 서술에 쓴다:
    # supporting_manifestation(같은 도메인 하위 사건) / impact_amplifier(압박 — 예상 영향)
    # / background_vulnerability(취약성 — 피해 확대 요인) / secondary_domain_effect(교차
    # 도메인 파생).
    absorbed_role: str | None = None


def is_active(candidate: RiskCandidate) -> bool:
    """**구조적 활성** 판정 — 사용자 노출 가능 여부가 아니다(2026-07-15 감수 3차 확정).

    True의 의미: "구조적으로 성립한 shadow 후보"까지다 — 증거 계약 충족(ELIGIBLE/
    MITIGATED) + 비차단 + 특이도 미흡수. 점수·등급·노출 기준 통과를 뜻하지 않는다.
    R1 이후 is_score_qualified(점수 통과), R3 이후 is_exposable(claimCeiling·등급·노출
    정책 통과)이 별도 판정으로 추가된다. R2 슬롯·R4 오경고 분모·밀도 active 지표는
    이 구조적 활성을 기준으로 하되, 사용자 노출은 반드시 exposable 판정을 거친다.
    """
    return (
        candidate.eligibility_status
        in (EligibilityStatus.ELIGIBLE, EligibilityStatus.MITIGATED)
        and candidate.suppressed_by_specificity is None
    )


def is_exposable(candidate: RiskCandidate) -> bool:
    """사용자 노출 가부의 구조적 근사(감수 14차 — R3 전 기계 강제).

    R3 노출 정책(claimCeiling·등급·질문 컨텍스트)의 상위 게이트다: 구조적 활성이면서
    ①selection 정렬이 unknown/mismatched가 아니고 ②UNKNOWN 비노출 항목
    (unknownExposable=false, 예: 대기명단)은 노출 CONFIRMED여야 한다. R3는 이 함수가
    True인 후보만 표현 정책 대상으로 삼는다 — "대기명단일 수 있다면" 류 우회 금지.
    """
    if not is_active(candidate):
        return False
    if candidate.selection_alignment != "matched":
        return False
    if not candidate.exposable_when_unknown and (
        candidate.exposure_status is not ExposureStatus.CONFIRMED
    ):
        return False
    return True


class ProtectiveFactor(BaseModel):
    """보호 요인(현재 완충) — 위험을 삭제하지 않고 "보호 요인이 있어 피해 확대 가능성이
    낮다"로 서술하기 위한 구조. mitigator 근거에서 파생된다(R1)."""

    code: str
    description_ko: str
    strength: float = Field(ge=0.0, le=1.0)


class RecoveryWindow(BaseModel):
    """회복 창 — 위험·압박 이후 정상화 흐름(별도 산출, R2). 현재 위험 점수에서 빼지 않는다."""

    start_period: str  # 회복 신호가 들어오는 기간 라벨
    note_ko: str | None = None  # 회복 근거 요약(기신 약화·보호 오행 유입 등)


class RiskEpisode(BaseModel):
    """병합된 위험 구간 — R2 산출물(R0에서는 타입만 고정, 생성하지 않는다).

    병합 키는 risk_id 단독이 아니라 (risk_id, cause_signature, domain, exposure_target)다 —
    같은 risk_id라도 원인 구조가 크게 바뀌면 별도 episode로 분리한다.
    """

    risk_id: str
    domain: RiskDomain
    kind: RiskKind
    cause_signature: str  # 지배 원인 서명 — 병합 키 구성 요소
    start_period: str
    peak_period: str  # 단순 최고 점수가 아니라 confidence 동반 고려(R2)
    end_period: str
    candidates: list[RiskCandidate] = Field(default_factory=list)
    risk_level: RiskLevel | None = None  # 등급(주의 필요도) — confidence와 독립 축
    protective_factors: list[ProtectiveFactor] = Field(default_factory=list)
    recovery_window: RecoveryWindow | None = None


def independent_source_count(evidences: list[RiskEvidence]) -> int:
    """TRIGGER 근거의 독립 출처 수 — source(원인 사실 서명) 기준 중복 제거.

    동일 원인에서 파생된 신호(같은 충의 감점·태그 등)는 source가 같아 1개로 계산된다.
    minimum_evidence.independent_source_count 판정에 쓴다.
    """
    return len({e.source for e in evidences if e.role is EvidenceRole.TRIGGER})


def dedupe_evidence(evidences: list[RiskEvidence]) -> list[RiskEvidence]:
    """(evidence_id, role, source_group) 단위 중복 제거.

    같은 원인 사실이 같은 역할·그룹으로 두 번 반영되는 것을 차단한다(먼저 온 것 유지,
    입력 순서 보존). source_group을 키에 포함하는 이유: 같은 사실을 event_shape 룰과
    targeted_event_shape 룰이 동시에 잡을 수 있고, 그룹 사실은 증거 계약 판정에
    필요하다 — 독립 원인 수 부풀림은 source 기준 계산(independent_source_count)이
    별도로 막는다."""
    seen: set[tuple[str, EvidenceRole, str | None]] = set()
    out: list[RiskEvidence] = []
    for e in evidences:
        key = (e.evidence_id, e.role, e.source_group)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out
