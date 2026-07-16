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
    # canary(감수 44차 — R4): allowlist 계정·감수 질문 유형·critical 강제
    # 하향·tokenizer 지원 모델·충분한 headroom에만 주입하는 제한 노출 단계.
    EXPOSE_CANARY = "expose_canary"
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
    # 매칭된 선발 건의 익명 episode 키(감수 25차 — SEL-e): 같은 시기 서로 다른
    # 선발(취업 지원 vs 자격시험 vs 추첨 — 같은 유형 2건 포함)을 구분한다. 후보
    # identity(risk_id+period+episode+target)·episode별 소유권·수렴 경계에 쓴다.
    selection_episode_id: str | None = None
    # 같은 selection episode의 컨텍스트 명시적 충돌(감수 25차) — 임의 우선순위로
    # 병합하지 않고 구조 보존+비노출(is_exposable 차단)+데이터 위생 로그로 남긴다.
    selection_context_conflict: bool = False
    # MobilityContext 3상태(감수 18·19차 — MOV 차수) — matched/unknown/mismatched.
    # mismatched=BLOCKED. unknown 노출 차등(감수 19차): 구체 항목(required_for_
    # exposure/confirmed_required — 계약·수리·통근·차량)은 하드 비노출, 일반 이동
    # 압박(required_for_warning)은 조건부 경로 유지(예상 못한 이동 압박 경고 목적).
    mobility_alignment: str = "matched"
    # 매칭된 이동 계획의 익명 episode 키(감수 19차) — 같은 시기 복수 계획(새 집 계약
    # vs 임시 숙소 vs 통근 조정) 구분·같은 episode 기준 수렴·교차 도메인 연결에 쓴다.
    mobility_episode_id: str | None = None
    # HealthContext 3상태(감수 21차 — HLT 차수) — 이동 축과 동일 정책: mismatched=
    # BLOCKED, unknown은 구체 항목(required_for_exposure/confirmed_required) 하드
    # 비노출·일반 컨디션(required_for_warning) 조건부. 건강 질문이 질환·치료 존재를
    # 자동 확인하지 않는다.
    health_alignment: str = "matched"
    # 매칭된 건강 맥락의 익명 episode 키(감수 21차) — 기존 불편 관리 vs 치료 회복 vs
    # 신체 부담 분리·같은 episode 기준 수렴. 질병명·부위 저장 금지.
    health_episode_id: str | None = None
    # LegalProcessContext 3상태(감수 23차) — 이동·건강 축과 동일 정책(mismatched=
    # BLOCKED, unknown은 구체 항목 하드 비노출·일반 압박 조건부).
    legal_alignment: str = "matched"
    # 매칭된 법적 절차의 익명 process episode 키(감수 23차) — 전세 계약 vs 인허가 vs
    # 진행 분쟁 분리·같은 episode 기준 수렴.
    legal_episode_id: str | None = None
    # 항목의 법적 단계 메타(applicableLegalStages 복사) — stage 호환 억제용.
    legal_stages: list[str] = Field(default_factory=list)
    # 항목의 이동 단계 메타(사전 applicableMobilityStages 복사) — stage 호환 억제용
    # (계약 전 vs 정착 후 상호 배타 단계는 같은 원인이어도 수렴 금지).
    mobility_stages: list[str] = Field(default_factory=list)
    # 이동 게이트 항목 여부(감수 22차) — 같은 차량·이동 episode의 MOV 사건과 HLT
    # 안전 주의를 한 수렴 범위로 묶는 마커(교차 도메인 수렴 그룹 라우팅).
    mobility_gated: bool = False
    # RelationshipContext 3상태(감수 16차 — REL 차수) — matched/unknown/mismatched.
    # mismatched(질문 직접 대상의 역할이 항목 허용 밖 — 궁합·함께보기 등)는 BLOCKED.
    # unknown은 selection과 달리 hard 비노출이 아니다: 유효 노출이 UNKNOWN으로 유도되어
    # exposurePolicy(unknownExposable·claimCeilingWhenUnknown)가 조건부 표현("현재
    # 관계가 있다면") 가부를 정한다 — 관계 존재를 단정하는 표현은 어느 경우에도 금지.
    relationship_alignment: str = "matched"
    # 매칭된 현실 관계(감수 16차): role=관계 역할(spouse/friend_peer 등), target_id=
    # 익명 대상 서명(동반자 프로필 키 등) — 동일 기간 서로 다른 상대 구분, '같은 상대'
    # 기준 억제, 궁합·함께보기에서 해당 동반자 관련 REL 후보 선별에 쓴다(실명 저장 금지).
    relationship_role: str | None = None
    relationship_target_id: str | None = None
    # 항목의 stage 메타(사전 applicableSelectionStages 복사) — stage-aware suppression용.
    selection_stages: list[str] = Field(default_factory=list)
    # UNKNOWN 노출 가부(사전 exposurePolicy.unknownExposable) — is_exposable이 소비.
    exposable_when_unknown: bool = True
    # 흡수 후보의 역할(2026-07-15 감수 3차) — 흡수는 삭제가 아니라 역할 전환이다.
    # R1에서 대표 후보의 impact/exposure 계산·보조 서술에 쓴다:
    # supporting_manifestation(같은 도메인 하위 사건) / impact_amplifier(압박 — 예상 영향)
    # / background_vulnerability(취약성 — 피해 확대 요인) / secondary_domain_effect(교차
    # 도메인 파생) / possible_trajectory(대표 위험 진행 시의 궤적 — 감수 16차, 거리감 등
    # 독립 발현이 아니라 전개 방향 서술 전용).
    absorbed_role: str | None = None
    # 사전 normalizedEffectRole 복사(감수 31차 — SSOT): compound '서로 다른 현실
    # 효과' 판정·교차 도메인 dedup 재료. 값 변경은 shadow_scoring scope만 강등.
    normalized_effect_role: str | None = None
    # 교차 도메인 현실 건 alias(감수 35차 — R2): 같은 주택 계약을 MOV·LEG·FIN
    # 컨텍스트가 공유할 때의 명시 연결값. 축별 local episode_id는 축 namespace로
    # 구분되며(문자열 우연 일치 병합 금지), 교차 축 병합은 이 alias가 있을 때만.
    # 매칭된 축 컨텍스트들의 reality id가 상충하면 None(fail-closed)이다.
    reality_episode_id: str | None = None
    # 현실 건 유형(감수 37차) — 같은 alias라도 type 비호환이면 CONFLICT(오부여
    # alias가 전혀 다른 현실 건을 합치는 것을 데이터 모델에서 감지).
    reality_episode_type: str | None = None
    # reality alias 상충(감수 36차) — 매칭 축 컨텍스트들의 alias가 서로 다름.
    # 병합 금지(fallback 재진입도 금지)·데이터 위생 로그 대상.
    reality_conflict: bool = False
    # 사전 transitionSensitivity 복사(감수 36차 — R1-T): 교운기 modifier 계수
    # 선택 재료(none/low/medium/high — vulnerability는 none 강제).
    transition_sensitivity: str = "none"
    # primary ownership 축(감수 39차 — R2-c 사전 계약 사본): 대표 정렬의
    # ownership rank는 이 축의 **명시 local episode 매칭**으로만 성립한다 —
    # reality alias(특히 partial)는 episode 연결 근거일 뿐 ownership 증거가
    # 아니다. "none"=축 미적용(역할·구조 기반 항목).
    primary_ownership_axis: str = "none"
    # 교운기 시점 보정(감수 36차) — score_shadow가 채우는 파생값(0=보정 없음).
    # 적격성·원인·persistence·episode identity에 일절 관여하지 않는다.
    transition_bonus: float = 0.0
    # 사전 absorbedRoleHint 복사(감수 16차) — 흡수 시 kind 기본값 대신 쓸 역할.
    # 관계 도메인 cross-family 흡수 허용 마커를 겸한다(감수 17차 — 미지정 항목은
    # 같은 상대·같은 원인이어도 family 밖 대표에 자동 흡수되지 않는다).
    absorbed_role_hint: str | None = None
    # trigger 원인 원자(정렬·중복 제거) — 교차 도메인 연결 키(감수 17차): 같은 원인의
    # FIN·REL 병존 후보를 R1(independent cause·occurrence 1회 계산)·R2(episode 병합
    # 시 대표 1개 선택)가 연결하는 재료. cause_signature/episode key의 원천.
    trigger_cause_atoms: list[str] = Field(default_factory=list)


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
    """**context-level exposure eligibility** — 최종 사용자 노출 승인이 아니다(감수 15차).

    판정 계층: is_active(구조적 활성) → is_exposable(본 함수 — 컨텍스트·mode·stage·
    노출 상위 게이트) → is_score_qualified(R1 점수·등급·confidence·protection) →
    is_selection_qualified(R2 병합·risk budget) → is_finally_exposable(R3 표현 감수).
    본 함수가 True여도 뒤 계층을 통과해야 사용자에게 노출된다.

    R3 노출 정책(claimCeiling·등급·질문 컨텍스트)의 상위 게이트다: 구조적 활성이면서
    ①selection 정렬이 unknown/mismatched가 아니고 ②UNKNOWN 비노출 항목
    (unknownExposable=false, 예: 대기명단)은 노출 CONFIRMED여야 한다. R3는 이 함수가
    True인 후보만 표현 정책 대상으로 삼는다 — "대기명단일 수 있다면" 류 우회 금지.

    관계 축(감수 16차)은 별도 분기가 없다: mismatched는 생성 시 BLOCKED(is_active에서
    탈락), unknown은 유효 노출 UNKNOWN으로 유도되어 위 ②(unknownExposable)가 그대로
    지배한다 — 관계 항목의 조건부 표현 가부는 사전 exposurePolicy가 정한다.
    """
    if not is_active(candidate):
        return False
    # vulnerability 단독 노출 없음 원칙(§2)의 명문화(감수 23차) — 취약성은 사용자
    # 경고로 단독 노출되지 않는다(incident 생성·심각도 상향의 중간 신호·배경 근거
    # 전용). 대표 흡수 적격성(_exposure_ok)도 이 판정을 소비하므로, 노출 부적격
    # 대표가 취약성을 background로 흡수하는 경로는 역전 방지에 걸리지 않는다.
    if candidate.kind is RiskKind.VULNERABILITY:
        return False
    if candidate.selection_alignment != "matched":
        return False
    # 같은 selection episode의 명시적 충돌 컨텍스트(감수 25차 — SEL-e): 임의
    # 우선순위 병합 금지 — 구조 후보는 보존하되 사용자 노출은 차단한다.
    if candidate.selection_context_conflict:
        return False
    if candidate.mobility_alignment == "mismatched":
        return False
    if candidate.mobility_alignment == "unknown" and candidate.exposure_requirement in (
        "required_for_exposure", "confirmed_required",
    ):
        # 이동 축 미확인(감수 19차 차등): 구체 항목(계약·수리·통근·차량)은 계획 확인
        # 없이 비노출. required_for_warning 일반 이동 압박은 unknownExposable 경로로
        # 조건부 서술 가능("거주·이동 조건을 조정할 변수가 생길 수 있음" 수준 — R3).
        return False
    if candidate.legal_alignment == "mismatched":
        return False
    if candidate.legal_alignment == "unknown" and candidate.exposure_requirement in (
        "required_for_exposure", "confirmed_required",
    ):
        # 법적 절차 축 미확인(감수 23차 — 이동·건강과 동일 차등): 절차 특정 항목은
        # 진행 확인 없이 비노출.
        return False
    if candidate.health_alignment == "mismatched":
        return False
    if candidate.health_alignment == "unknown" and candidate.exposure_requirement in (
        "required_for_exposure", "confirmed_required",
    ):
        # 건강 축 미확인(감수 21차 — 이동과 동일 차등): 기존 질환·치료·신체 부담 특정
        # 항목은 확인 없이 비노출("질환이 있다면" 우회 금지는 unknownExposable=false가
        # 추가 차단). 일반 컨디션 pressure(required_for_warning)는 조건부 경로 유지.
        return False
    if not candidate.exposable_when_unknown and (
        candidate.exposure_status is not ExposureStatus.CONFIRMED
    ):
        return False
    # confirmed_required(감수 22차 명시화) — 노출 CONFIRMED 없이는 사건 적용 불가
    # 항목은 unknownExposable과 무관하게 컨텍스트 게이트에서 비노출이다(소송 확대·
    # 대인 금전 등 — '~일 수 있다면' 우회 금지). 대표 흡수 적격성(_exposure_ok)도
    # 이 판정을 그대로 소비한다.
    if candidate.exposure_requirement == "confirmed_required" and (
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
    """회복 창 — 위험·압박 이후 정상화 전망(별도 산출, R2). 현재 위험 점수·순위에서
    빼지 않는다(감수 34차 — 점수 불변 fixture). 단정 표현 금지: '반드시 해결'·
    '완전 소멸'·'회복 운이라 현재 위험 낮음' 불가."""

    earliest_relief_window: str  # 부담이 처음 덜릴 수 있는 기간 라벨
    stable_recovery_window: str | None = None  # 안정 회복 전망 기간(보수적)
    recovery_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    recovery_reasons: list[str] = Field(default_factory=list)  # lineage 종료 등
    note_ko: str | None = None  # 회복 근거 요약(기신 약화·보호 오행 유입 등)


class RiskEpisode(BaseModel):
    """병합된 위험 episode — R2 산출물(감수 34차 — R0 자리표시 키 폐기).

    **identity 3분리**: reality episode(명시 context episode_id+대상 서명+stage·
    기간 호환)가 병합 키다 — cause(canonical atom·lineage)와 effect(normalized
    EffectRole)는 별도 축. **risk_id·domain은 키가 아니라 구성원 속성**: 주택
    계약 episode 하나에 MOV·LEG·FIN 후보가 함께 묶인다. cause 교집합은 연결
    근거일 뿐(다른 episode+같은 cause=병합 금지·portfolio 1회 계산).

    대표 선택 후에도 supporting·background·trajectory 구성원을 삭제하지 않는다 —
    역할 보존, 사용자 출력만 대표 중심 압축(R3).
    """

    # reality episode identity — 명시 (축, episode_id) 서명. fallback 병합
    # episode는 결정적 합성 키("fallback:<대상·원인 서명 해시>").
    episode_key: str
    target_signature: list[str] = Field(default_factory=list)  # 대상 객체 서명들
    start_period: str
    end_period: str
    stages: list[str] = Field(default_factory=list)  # 관측 stage 메타(호환 기록)
    member_candidate_ids: list[str] = Field(default_factory=list)
    representative_candidate_id: str | None = None  # 자격 미달이면 None(비노출)
    supporting_candidate_ids: list[str] = Field(default_factory=list)
    background_vulnerability_ids: list[str] = Field(default_factory=list)
    canonical_cause_ids: list[str] = Field(default_factory=list)  # cause 축(별도)
    effect_roles: list[str] = Field(default_factory=list)  # effect 축(별도)
    domains: list[RiskDomain] = Field(default_factory=list)  # 구성원 속성
    exposure_status: ExposureStatus = ExposureStatus.UNKNOWN  # 대표 기준
    # reality alias identity 상태(감수 38차 preflight): resolved=구성원 전원
    # type 보유·호환 / partial=alias 동일이나 type 일부·전부 미기재(병합은
    # 유지하되 완전한 identity로 취급 금지 — confidence 차등) / conflict.
    # 비reality episode(explicit·fallback)는 None.
    reality_identity_status: str | None = None
    structural_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    context_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_level: RiskLevel | None = None  # 등급 — confidence와 독립 축(R3 상한 소비)
    protective_factors: list[ProtectiveFactor] = Field(default_factory=list)
    recovery_window: RecoveryWindow | None = None  # 현재 점수와 완전 독립


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
