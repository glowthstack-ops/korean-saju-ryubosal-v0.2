"""범용 추첨·선발·배치(selection_allocation) 이벤트 코어 schemas (2026-07-14 데굴님 설계).

군입대·청약·학교 배정 등 "기회→지원→자격→선발→배치→수락·실행→적응" 흐름을 갖는
사건의 공용 구조. 핵심 원칙:

- **당첨운 단일 사건 금지**: 선발(selection)과 희망 조건 배치(preference_match)는
  서로 다른 사건이다 — 단계별 점수를 분리 산출한다.
- **외부 무작위성 캡**: 추첨 비중이 높을수록 confidence 상한과 점수 상한을 낮추고
  당첨·탈락 단정을 금지한다(response_policy). 객관 확률과 사주 해석은 섞지 않는다.
- **결과는 이진값이 아니라 상태 머신**: 대기·추가 선발·차선 배정·취소를 표현한다.
- 검증(실사례 캘리브레이션) 전까지 shadow/설명 보조 전용 — 사건 점수·판정 불변.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

SELECTION_EVENT_FAMILY = "selection_allocation"


class SelectionStage(StrEnum):
    """선발·배치 사건의 단계 (설계 §1)."""

    OPPORTUNITY_OPEN = "opportunity_open"  # 지원·신청 기회가 열림
    APPLICATION = "application"  # 실제 지원·신청
    ELIGIBILITY = "eligibility"  # 자격·서류·조건 심사 통과
    SELECTION = "selection"  # 추첨·선발에서 선택됨
    ALLOCATION = "allocation"  # 자리·지역·일정·기관 배정
    PREFERENCE_MATCH = "preference_match"  # 배정 결과가 희망 조건과 일치
    ACCEPTANCE = "acceptance"  # 결과 수락·등록·계약
    EXECUTION = "execution"  # 실제 입주·입영·입학·참여 시작
    ADAPTATION = "adaptation"  # 배치 환경 적응·만족


class SelectionMode(StrEnum):
    """선발 방식 (설계 §3) — 방식에 따라 사주 신호 활용도·신뢰 상한이 다르다."""

    LOTTERY = "lottery"  # 순수 무작위 추첨
    WEIGHTED_LOTTERY = "weighted_lottery"  # 가중치 추첨
    SCORE_RANKED = "score_ranked"  # 점수·순위 기반
    HYBRID = "hybrid"  # 자격·점수 + 추첨 혼합
    FIRST_COME = "first_come"  # 선착순
    QUEUE = "queue"  # 대기 순번
    ADMINISTRATIVE = "administrative"  # 기관 판단·행정 배정


class AllocationMode(StrEnum):
    """배치 방식 (설계 §3)."""

    RANDOM = "random"
    PREFERENCE_ORDERED = "preference_ordered"
    SCORE_BASED = "score_based"
    CAPACITY_BASED = "capacity_based"
    LOCATION_BASED = "location_based"
    QUALIFICATION_BASED = "qualification_based"
    ADMINISTRATIVE = "administrative"
    HYBRID = "hybrid"


class SelectionState(StrEnum):
    """결과 상태 머신 (설계 §4) — 이진 당첨값 금지."""

    NOT_OPEN = "not_open"
    NOT_APPLIED = "not_applied"
    APPLICATION_PENDING = "application_pending"
    INELIGIBLE = "ineligible"
    ELIGIBLE = "eligible"
    NOT_SELECTED = "not_selected"
    WAITLISTED = "waitlisted"
    SELECTED = "selected"
    SELECTED_UNALLOCATED = "selected_unallocated"
    ALLOCATED_NONPREFERRED = "allocated_nonpreferred"
    ALLOCATED_PREFERRED = "allocated_preferred"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    EXECUTED = "executed"
    ADAPTED_POSITIVE = "adapted_positive"
    ADAPTED_MIXED = "adapted_mixed"
    ADAPTED_NEGATIVE = "adapted_negative"


# 허용 전이 — "대기→추가 선발", "선발→자격 재검토 취소" 같은 현실 서사를 구조로 지원.
SELECTION_STATE_TRANSITIONS: dict[SelectionState, tuple[SelectionState, ...]] = {
    SelectionState.NOT_OPEN: (SelectionState.NOT_APPLIED,),
    SelectionState.NOT_APPLIED: (
        SelectionState.APPLICATION_PENDING, SelectionState.NOT_OPEN,
    ),
    SelectionState.APPLICATION_PENDING: (
        SelectionState.ELIGIBLE, SelectionState.INELIGIBLE, SelectionState.CANCELLED,
    ),
    SelectionState.INELIGIBLE: (SelectionState.NOT_APPLIED,),  # 보완 후 재지원
    SelectionState.ELIGIBLE: (
        SelectionState.SELECTED, SelectionState.NOT_SELECTED,
        SelectionState.WAITLISTED, SelectionState.CANCELLED,
    ),
    SelectionState.NOT_SELECTED: (
        SelectionState.WAITLISTED, SelectionState.NOT_APPLIED,  # 재지원 회차
    ),
    SelectionState.WAITLISTED: (
        SelectionState.SELECTED, SelectionState.NOT_SELECTED, SelectionState.CANCELLED,
    ),
    SelectionState.SELECTED: (
        SelectionState.SELECTED_UNALLOCATED, SelectionState.ALLOCATED_PREFERRED,
        SelectionState.ALLOCATED_NONPREFERRED, SelectionState.CANCELLED,  # 자격 재검토 취소
    ),
    SelectionState.SELECTED_UNALLOCATED: (
        SelectionState.ALLOCATED_PREFERRED, SelectionState.ALLOCATED_NONPREFERRED,
        SelectionState.CANCELLED,
    ),
    SelectionState.ALLOCATED_PREFERRED: (
        SelectionState.ACCEPTED, SelectionState.DECLINED,
    ),
    SelectionState.ALLOCATED_NONPREFERRED: (
        SelectionState.ACCEPTED, SelectionState.DECLINED,
    ),
    SelectionState.ACCEPTED: (SelectionState.EXECUTED, SelectionState.CANCELLED),
    SelectionState.DECLINED: (SelectionState.NOT_APPLIED,),  # 다음 회차
    SelectionState.CANCELLED: (SelectionState.NOT_APPLIED,),
    SelectionState.EXECUTED: (
        SelectionState.ADAPTED_POSITIVE, SelectionState.ADAPTED_MIXED,
        SelectionState.ADAPTED_NEGATIVE,
    ),
    SelectionState.ADAPTED_POSITIVE: (),
    SelectionState.ADAPTED_MIXED: (),
    SelectionState.ADAPTED_NEGATIVE: (),
}


def can_transition(src: SelectionState, dst: SelectionState) -> bool:
    """상태 머신 전이 허용 여부."""
    return dst in SELECTION_STATE_TRANSITIONS.get(src, ())


class FunctionSignal(StrEnum):
    """도메인 중립 기능 신호 (설계 §6) — 십성 의미를 코어에 고정하지 않는 추상층."""

    INSTITUTION = "institution_signal"  # 기관·조직·공식 절차 (관성)
    QUALIFICATION = "qualification_signal"  # 자격·서류·승인 (인성)
    APPLICATION = "application_signal"  # 지원·표현·시험·제출 (식상)
    COMPETITION = "competition_signal"  # 경쟁자·정원·순번 (비겁)
    BENEFIT = "benefit_signal"  # 획득 자원·혜택 (재성)
    MATCHING = "matching_signal"  # 희망 조건과의 일치 (재성·조건 효용)
    TRANSITION = "transition_signal"  # 이동·입주·입영·입학 (충·운 유입)
    STABILITY = "stability_signal"  # 배치 후 유지·적응 (마찰 부재·인성)


class PreferenceCondition(BaseModel):
    """희망 조건 1건 (설계 §10 preferences) — 지망 순위 모델."""

    rank: int = Field(ge=1)
    condition: str
    importance: str = "medium"  # 'high' | 'medium' | 'low'


class SelectionMechanism(BaseModel):
    """선발·배치 방식 (설계 §3·§10 mechanism)."""

    selection_mode: SelectionMode = SelectionMode.LOTTERY
    allocation_mode: AllocationMode = AllocationMode.RANDOM
    waitlist_enabled: bool = True
    multi_stage: bool = True


class ExternalUncertainty(BaseModel):
    """외부 무작위성 (설계 §8) — 클수록 표현·점수를 제한한다."""

    level: str = "high"  # 'high' | 'medium' | 'low'
    reason: str = ""


class ResponsePolicy(BaseModel):
    """답변 표현 정책 (설계 §8·§10) — 엔진이 산출하고 LLM 지시문이 강제한다."""

    binary_outcome_prediction: bool = False  # 당첨·탈락 단정 금지(항상 False 권장)
    confidence_cap: str = "low"  # 'low' | 'medium' | 'high'
    relative_timing_comparison: bool = True  # 상대적 유리 시기 비교는 허용
    allow_waitlist_scenario: bool = True  # 대기·추가 선발 서사 허용


class StageScores(BaseModel):
    """단계별 성립도 점수(0~100, 설계 §5) — 단일 '당첨운' 점수 금지."""

    opportunity: int = Field(ge=0, le=100, default=0)
    application: int = Field(ge=0, le=100, default=0)
    eligibility: int = Field(ge=0, le=100, default=0)
    selection_support: int = Field(ge=0, le=100, default=0)
    allocation: int = Field(ge=0, le=100, default=0)
    preference_match: int = Field(ge=0, le=100, default=0)
    execution: int = Field(ge=0, le=100, default=0)
    adaptation: int = Field(ge=0, le=100, default=0)


class SelectionSignalEvidence(BaseModel):
    """기능 신호 1건의 강도·근거 — LLM 서술 재료(판정 재료 아님)."""

    signal: FunctionSignal
    strength: float = Field(ge=0.0, le=1.0)
    basis: str = ""  # '관성 작동(운 유입)·희신' 등 근거 요약


class TimingWindow(BaseModel):
    """상대적으로 유리한 시기 창 1건 (설계 §8 relative_timing_comparison 허용 범위).

    결과 보장이 아니라 초점 단계의 기능 신호가 운에서 유입되는 달의 상대 비교다.
    사전계산(T0~T2) 정식 통합 전의 경량 시기 축 — 월운 간지의 십성군 유입 기반.
    """

    label: str  # 'YYYY-MM'
    boost: float  # 단계 가중 기준 유입 강도(상대값)
    reason: str = ""  # '관성·인성 유입' 등


class ObjectiveOdds(BaseModel):
    """객관적 기초 확률 (설계 §8) — 사주 해석과 절대 혼합 금지(분리 표기 전용).

    사용자 발화("경쟁률 5대 1", "1000명 중 200명")나 외부 데이터에서 온 실제
    경쟁률. 엔진 점수와 섞어 가짜 확률을 만들지 않고 별도 표기한다.
    """

    applicants: int | None = None
    seats: int | None = None
    base_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    source: str = "user"  # 'user' | 'external'


class ModeGuard(BaseModel):
    """선발 방식별 무작위성 가드 (설계 §4·§8) — 사전 외부화 대상."""

    uncertainty: str  # 'high' | 'medium' | 'low'
    confidence_cap: str  # 'low' | 'medium' | 'high'
    selection_cap: int = Field(ge=0, le=100)
    allocation_cap: int = Field(ge=0, le=100)
    preference_cap: int = Field(ge=0, le=100)


class SelectionWeightsConfig(BaseModel):
    """선발·배치 엔진 가중 설정 (사전 외부화 — 원칙 5 validate→compile→배포).

    코드 기본값과 동일 구조의 JSON(`dictionaries/selection_allocation_weights.json`)을
    검증·컴파일해 로드한다. 골든 사례 캘리브레이션(잔여 ①)의 조정 지점이 이 파일이다.
    """

    version: str = "0.1.0"
    reviewed: bool = False
    base_strengths: dict[str, float] = Field(
        default_factory=lambda: {"active": 0.65, "present": 0.40, "absent": 0.20}
    )
    role_adjust: dict[str, float] = Field(
        default_factory=lambda: {
            "yongsin": 0.15, "heesin": 0.10, "gisin": -0.15, "gusin": -0.10,
        }
    )
    state_adjust: dict[str, float] = Field(
        default_factory=lambda: {
            "inflow": 0.10, "deficient": -0.15,
            "excess_nonpeer": -0.05, "excess_peer": 0.10,
        }
    )
    transition: dict[str, float] = Field(
        default_factory=lambda: {"base": 0.30, "clash": 0.25, "inflow": 0.15}
    )
    stability: dict[str, float] = Field(
        default_factory=lambda: {
            "base": 0.65, "friction_step": 0.10, "qualification_coupling": 0.30,
        }
    )
    competition_inversion: dict[str, float] = Field(
        default_factory=lambda: {"default": 0.70, "peer_favorable": 0.40}
    )
    # 단계 → (기능 신호 → 가중). 각 단계 가중 합=1.0(빌드 검증).
    stage_weights: dict[str, dict[str, float]] = Field(default_factory=dict)
    merit_selection_weights: dict[str, float] = Field(default_factory=dict)
    mode_guards: dict[str, ModeGuard] = Field(default_factory=dict)


class SelectionAllocationReading(BaseModel):
    """선발·배치 사건 풀이 1건 (설계 §10) — shadow/설명 보조 출력."""

    event_family: str = SELECTION_EVENT_FAMILY
    domain: str = "generic"  # 도메인 어댑터 키(military_service/housing_subscription/…)
    focus_stage: SelectionStage = SelectionStage.SELECTION
    mechanism: SelectionMechanism = Field(default_factory=SelectionMechanism)
    preferences: list[PreferenceCondition] = Field(default_factory=list)
    stage_scores: StageScores = Field(default_factory=StageScores)
    signals: list[SelectionSignalEvidence] = Field(default_factory=list)
    external_uncertainty: ExternalUncertainty = Field(default_factory=ExternalUncertainty)
    response_policy: ResponsePolicy = Field(default_factory=ResponsePolicy)
    # 객관 경쟁률(사용자 제공·외부 데이터) — 사주 해석과 분리 표기 전용(혼합 금지).
    objective_odds: ObjectiveOdds | None = None


class SelectionDomainAdapter(BaseModel):
    """도메인 어댑터 — 기능 신호를 현실 언어로 바꾸고 기본 방식을 제공한다(설계 §6)."""

    key: str
    label_ko: str
    default_mechanism: SelectionMechanism
    signal_labels: dict[str, str] = Field(default_factory=dict)  # FunctionSignal → 현실 언어
    stage_labels: dict[str, str] = Field(default_factory=dict)  # SelectionStage → 현실 언어


# 도메인 어댑터 레지스트리 (설계 '권장 구현 방향') — 군입대가 첫 적용 사례.
SELECTION_DOMAIN_ADAPTERS: dict[str, SelectionDomainAdapter] = {
    "military_service": SelectionDomainAdapter(
        key="military_service", label_ko="군입대·모집병",
        default_mechanism=SelectionMechanism(
            selection_mode=SelectionMode.WEIGHTED_LOTTERY,
            allocation_mode=AllocationMode.PREFERENCE_ORDERED,
        ),
        signal_labels={
            "institution_signal": "병무·군 조직·공식 절차",
            "qualification_signal": "신체검사·자격·서류",
            "application_signal": "모집 지원·특기 제출·면접",
            "competition_signal": "동일 회차 지원자·정원 경쟁",
            "benefit_signal": "복무 조건·특기·처우",
            "matching_signal": "희망 입영월·특기·지역 일치",
            "transition_signal": "실제 입영·생활권 전환",
            "stability_signal": "복무 적응·환경 안정",
        },
        stage_labels={
            "selection": "추첨·선발", "allocation": "부대·특기·일정 배정",
            "execution": "실제 입영", "adaptation": "복무 적응",
        },
    ),
    "housing_subscription": SelectionDomainAdapter(
        key="housing_subscription", label_ko="청약·공공주택",
        default_mechanism=SelectionMechanism(
            selection_mode=SelectionMode.LOTTERY,
            allocation_mode=AllocationMode.RANDOM,
        ),
        signal_labels={
            "institution_signal": "시행사·공공기관·청약 제도",
            "qualification_signal": "청약 가점·소득·무주택 요건",
            "application_signal": "청약 신청·서류 제출",
            "competition_signal": "경쟁률·대기 순번",
            "benefit_signal": "주거·자산 혜택",
            "matching_signal": "희망 단지·동·호수·입주 시기 일치",
            "transition_signal": "계약·입주·이사",
            "stability_signal": "거주 만족·정착",
        },
        stage_labels={
            "selection": "청약 당첨", "allocation": "동·호수·입주 시기 배정",
            "execution": "계약·실제 입주", "adaptation": "거주 만족",
        },
    ),
    "school_assignment": SelectionDomainAdapter(
        key="school_assignment", label_ko="학교·교육기관 배정",
        default_mechanism=SelectionMechanism(
            selection_mode=SelectionMode.HYBRID,
            allocation_mode=AllocationMode.LOCATION_BASED,
        ),
        signal_labels={
            "institution_signal": "학교·교육기관·배정 제도",
            "qualification_signal": "성적·서류·지원 자격",
            "application_signal": "지원서·시험·면접",
            "competition_signal": "지원 경쟁·정원",
            "benefit_signal": "교육 기회·프로그램 혜택",
            "matching_signal": "1지망·희망 학교 일치",
            "transition_signal": "등록·입학·통학 환경 변화",
            "stability_signal": "학교 적응",
        },
        stage_labels={
            "selection": "선발·추첨 배정", "allocation": "학교·반·캠퍼스 배정",
            "execution": "등록·입학", "adaptation": "학교 적응",
        },
    ),
    "dormitory_assignment": SelectionDomainAdapter(
        key="dormitory_assignment", label_ko="기숙사 배정",
        default_mechanism=SelectionMechanism(
            selection_mode=SelectionMode.HYBRID,
            allocation_mode=AllocationMode.CAPACITY_BASED,
        ),
    ),
    "public_program": SelectionDomainAdapter(
        key="public_program", label_ko="공공 프로그램·지원사업",
        default_mechanism=SelectionMechanism(
            selection_mode=SelectionMode.HYBRID,
            allocation_mode=AllocationMode.ADMINISTRATIVE,
        ),
    ),
    "workplace_assignment": SelectionDomainAdapter(
        key="workplace_assignment", label_ko="근무지·부서 배치",
        default_mechanism=SelectionMechanism(
            selection_mode=SelectionMode.ADMINISTRATIVE,
            allocation_mode=AllocationMode.ADMINISTRATIVE,
        ),
    ),
    "event_ticketing": SelectionDomainAdapter(
        key="event_ticketing", label_ko="행사·좌석 추첨",
        default_mechanism=SelectionMechanism(
            selection_mode=SelectionMode.LOTTERY,
            allocation_mode=AllocationMode.RANDOM,
            multi_stage=False,  # 당첨 후 별도 배치 과정이 없으면 selection에서 종료
        ),
    ),
    "generic": SelectionDomainAdapter(
        key="generic", label_ko="추첨·선발·배치",
        default_mechanism=SelectionMechanism(),
    ),
}
