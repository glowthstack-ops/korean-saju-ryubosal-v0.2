"""Life Event Inference 타입 — 개인 현실 사건 시그니처 + 현실 신호 캘리브레이션 질문.

doc/v2_2/LIFE_EVENT_INFERENCE.md. 사용자 확인 사건(원자 행)과 코호트 지문, 그리고 주요 ~10개
연도의 연도별 발생 이벤트 선택 질문을 정의한다. 본 단계는 **수집만** 하며 랭킹에 반영하지 않는다.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from .calibration import ExperienceRating


class LifeEventOutcome(StrEnum):
    """사건 확정 상태 (미래 사건 루프 포함)."""

    CONFIRMED = "confirmed"            # 실제 일어남
    NOT_HAPPENED = "not_happened"      # 안 일어남(해당없음 — failed_prediction 소스)
    PLANNED = "planned"                # 예정(2026.08 이사 예정 등)
    PENDING = "pending"                # 미래 사건, 결과 대기
    REALITY_FIT_ONLY = "reality_fit_only"  # 방향만 맞음(결과 미확인 — 채팅 즉시 피드백)


class LifeEventSource(StrEnum):
    """수집 채널 (소스별 신뢰 가중 차등)."""

    REALITY_SIGNAL_CALIBRATION = "reality_signal_calibration"  # 온보딩 — 가장 깨끗
    CHAT_CORRECTION = "chat_correction"                        # 채팅 맞음/틀림 정정
    CHAT_RATING = "chat_rating"                                # 채팅 평가(👍/👎)
    DELAYED_OUTCOME = "delayed_outcome"                        # 시점 경과 결과 — 최상


class SignalFingerprint(BaseModel):
    """사건을 만든 신호 지문 — 코호트·개인 매칭의 비교 단위."""

    ten_god_groups: list[str] = Field(default_factory=list)  # peer/output/wealth/authority/resource
    palace: str | None = None        # year_pillar/month_pillar/day_pillar/hour_pillar
    relation: str | None = None      # HAP/CHUNG/HYEONG/PA/HAE
    twelve_stage: str | None = None  # JANGSAENG ... YANG


class LifeEventRow(BaseModel):
    """subject_life_events 한 행(원자 행 — 읽을 때 granularity별 집계)."""

    event_row_id: str
    subject_id: str
    owner_id: str = "default"
    # 코호트 지문(보정 후 4기둥 간지 + 성별)
    pillar_year: str
    pillar_month: str
    pillar_day: str          # 일주 = coarse 코호트 키
    pillar_hour: str | None = None
    gender: str | None = None
    # 사건
    event_key: str
    period: str              # '2025' / '2025-08'
    signal_fingerprint: SignalFingerprint = Field(default_factory=SignalFingerprint)
    outcome: LifeEventOutcome
    source: LifeEventSource
    weight: float = 1.0


# ── 현실 신호 캘리브레이션 질문 (주요 ~10개 연도 · 연도별 이벤트 선택) ──


class RealityCalibrationEvent(BaseModel):
    """질문에 노출되는 그 해 후보 이벤트 1건(사용자 선택 대상)."""

    event_key: str
    label: str               # 한글 라벨(내부 키 노출 금지)
    fingerprint: SignalFingerprint = Field(default_factory=SignalFingerprint)


class RealityCalibrationYear(BaseModel):
    """주요 연도 1개 + 그 해 선택 가능한 이벤트 목록(+해당없음은 UI 고정)."""

    year: int
    ganji: str               # 그 해 세운 간지
    salience: float          # 연도 선정 점수(높을수록 신호 강함)
    daewoon_transition: bool = False  # 대운 교운 인접 연도
    events: list[RealityCalibrationEvent] = Field(default_factory=list)


class OccurredEvent(BaseModel):
    """실제 일어난 사건 1건 + 선택적 발생 월/경험(기억나는 경우만).

    발생(occurred)은 이벤트 엔진/personal_match 학습용, 경험(experience)은 용신 후보 검증용으로
    분리한다(docs/14 결정②). experience/intensity는 선택 — 없으면 발생만 반영.
    """

    event_key: str
    month: int | None = None  # 1~12. 없으면 연도 지문으로 폴백(미입력 무해 — 규칙11)
    experience: ExperienceRating | None = None  # 그 일이 어땠나(좋음/힘듦/반반) — 선택
    intensity: int | None = None  # 1~3 강도 — 선택


class PeriodNuance(BaseModel):
    """층위(대운/세운/월운) 뉘앙스 — 보류(docs/14 §5). 스키마만, 강한 신호 해에만 후속 노출."""

    has_peak_period: bool = False
    peak_granularity: Literal["half", "season", "month"] | None = None
    peak_value: str | None = None
    peak_experience: ExperienceRating | None = None


class RealityCalibrationYearAnswer(BaseModel):
    """한 연도에 대한 사용자 선택. 발생·경험·영역을 분리해 받는다(docs/14)."""

    year: int
    occurred: list[OccurredEvent] = Field(default_factory=list)  # 실제 일어난 사건(+선택 월·경험)
    none_of_them: bool = False  # 해당 없음(그 해 후보 전부 not_happened)
    overall_rating: ExperienceRating = "unknown"  # 그 해 전체 체감(7상태, 약보조)
    domain_ratings: dict[str, str] = Field(default_factory=dict)  # 영역별 체감(ExperienceRating)
    period_nuance: PeriodNuance | None = None  # 보류(비활성)


class RealityCalibrationQuestionSet(BaseModel):
    """현실 신호 캘리브레이션 질문 세트 — 주요 ~10개 연도."""

    subject_id: str | None = None
    years: list[RealityCalibrationYear] = Field(default_factory=list)
    note: str = (
        "각 연도에 실제로 있었던 일을 모두 선택하세요. 없었으면 '해당 없음'을 선택하면 됩니다. "
        "선택은 풀이 정확도를 높이는 데만 쓰이며 언제든 비워둘 수 있습니다."
    )
    # 이전 제출 답변(수정 모드 프리필) — 없으면 빈 목록(신규 입력). subject_signature로 복원.
    prior: list[RealityCalibrationYearAnswer] = Field(default_factory=list)


class RealityCalibrationSubmission(BaseModel):
    """현실 신호 캘리브레이션 제출 — 연도별 선택."""

    subject_id: str
    owner_id: str = "default"
    answers: list[RealityCalibrationYearAnswer] = Field(default_factory=list)
