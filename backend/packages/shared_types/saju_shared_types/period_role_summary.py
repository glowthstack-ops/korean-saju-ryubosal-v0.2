"""연·월·일 역할 요약과 슬롯 상태 (P2 — 2026-07-27 데굴님 확정).

배경: 일진 하나만 보고 "오늘은 기신운"이라고 총평하면, 그 하루를 감싸는 세운·월운의
방향이 사라진다. 이 모듈은 **요청 대상 층위(target)와 그 위의 배경(background)을 나눠**
각각의 상태를 보존한다.

고정 규칙(데굴님 확정):
  - 4:6 가중은 기존 stem/branch 점수가 아니라 **역할 방향값(+1/0/-1)** 에만 적용한다.
    기존 점수에는 위치·역할 보정이 이미 섞여 있어 다시 곱하면 지지가 이중 반영된다.
  - 천간과 지지의 방향이 다르면 net 부호와 무관하게 항상 MIXED다.
  - `sort_net`은 표시 정렬·진단·V1/V2 비교 전용이다. 상태·요약·점수 결정에 쓰지 않는다.
  - 역할 미상(UNKNOWN)을 閑(NEUTRAL)으로 축약하지 않는다 — 데이터 누락을 명리적
    중립으로 잘못 해석하게 된다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .luck_hierarchy import ParticipantLayer

#: 역할 → 방향값. 4:6 가중은 **이 값에만** 적용한다.
ROLE_DIRECTION: dict[str, int] = {
    "용신": 1, "희신": 1,
    "한신": 0,
    "기신": -1, "구신": -1,
}


class PillarState(StrEnum):
    """운주 1개의 방향 상태."""

    FAVORABLE = "FAVORABLE"
    ADVERSE = "ADVERSE"
    NEUTRAL = "NEUTRAL"
    MIXED = "MIXED"  # 천간·지지 방향이 반대 — net 부호로 덮지 않는다
    UNKNOWN = "UNKNOWN"  # 역할 미상(데이터 누락) — 중립이 아니다


class BackgroundState(StrEnum):
    """대상 기간 위쪽 층위들이 만드는 배경 방향."""

    SUPPORT = "SUPPORT"
    PRESSURE = "PRESSURE"
    MIXED = "MIXED"
    NEUTRAL = "NEUTRAL"
    NONE = "NONE"  # 상위 층위 없음
    UNKNOWN = "UNKNOWN"  # 판단 불가


class HierarchySummary(StrEnum):
    """배경 × 대상의 종합 유형. background/target 상태에서 **파생되는 표시값**이다."""

    CONSISTENT_SUPPORT = "CONSISTENT_SUPPORT"
    CONSISTENT_PRESSURE = "CONSISTENT_PRESSURE"
    BACKGROUND_SUPPORT_TARGET_FRICTION = "BACKGROUND_SUPPORT_TARGET_FRICTION"
    BACKGROUND_PRESSURE_TARGET_RELIEF = "BACKGROUND_PRESSURE_TARGET_RELIEF"
    MIXED_ACROSS_LAYERS = "MIXED_ACROSS_LAYERS"
    NO_CLEAR_DIRECTION = "NO_CLEAR_DIRECTION"


class PillarRoleState(BaseModel):
    """층위 1개의 역할 상태."""

    layer: ParticipantLayer
    ganji: str
    stem_role: str = ""  # 용신/희신/기신/구신/한신 (미상이면 빈 문자열)
    branch_role: str = ""
    stem_state: PillarState = PillarState.UNKNOWN
    branch_state: PillarState = PillarState.UNKNOWN
    state: PillarState = PillarState.UNKNOWN
    #: 표시 정렬·진단 전용. 상태·요약·점수 결정에 쓰지 말 것.
    sort_net: float = 0.0
    #: 천간·지지 역할이 모두 확인됐는가. False면 종합 판단에서 제외한다.
    direction_available: bool = False


class PeriodRoleSummary(BaseModel):
    """이번 요청의 연·월·일 역할 요약 SSOT.

    background_state와 target_state를 각각 보존한다 — 요약 enum 하나로 뭉치면
    '배경은 중립인데 대상만 우호' 같은 조합이 표현되지 않는다.
    """

    requested_level: str  # 'day' | 'month' | 'year'
    target_layer: ParticipantLayer | None = None
    target: PillarRoleState | None = None
    background: list[PillarRoleState] = Field(default_factory=list)
    background_state: BackgroundState = BackgroundState.NONE
    target_state: PillarState = PillarState.UNKNOWN
    hierarchy_summary: HierarchySummary = HierarchySummary.NO_CLEAR_DIRECTION


# ── 슬롯 상태 ────────────────────────────────────────────────────────────────


class SlotStatusSource(StrEnum):
    """슬롯 상태를 계산한 원재료의 출처.

    LEGACY_V1은 운주 단일 라벨에서 부호를 상속받은 오염된 값이라, 형식이 새로워도
    판정 근거가 틀렸다. 사용자 서술에는 POLARITY_V2만 쓴다(데굴님 확정).
    """

    LEGACY_V1 = "LEGACY_V1"
    POLARITY_V2 = "POLARITY_V2"


class SlotStatus(StrEnum):
    """슬롯의 **의미 상태**. 화면 clamp 여부와는 별개 축이다."""

    NO_SIGNAL = "NO_SIGNAL"
    FAVORABLE_DOMINANT = "FAVORABLE_DOMINANT"
    ADVERSE_DOMINANT = "ADVERSE_DOMINANT"
    MIXED_BALANCED = "MIXED_BALANCED"
    VOLATILITY_ONLY = "VOLATILITY_ONLY"
    NEUTRAL = "NEUTRAL"
    #: 양방향 효과는 있으나 크기를 배분하지 못한 상태(丁壬 쟁합 등). 신호가 없는 것도
    #: 아니고 양쪽이 같다는 근거도 없으므로 NO_SIGNAL·MIXED_BALANCED 어느 쪽도 아니다.
    DIRECTION_UNRESOLVED = "DIRECTION_UNRESOLVED"


class SlotStatusResult(BaseModel):
    """슬롯 상태 판정 결과 — 의미 상태와 화면 표시를 분리해 보존한다."""

    status: SlotStatus
    source: SlotStatusSource
    positive_total: float = 0.0
    negative_total: float = 0.0
    net_raw: float = 0.0
    signed_signal_count: int = 0
    neutral_signal_count: int = 0
    volatility_signal_count: int = 0
    volatility_total: float = 0.0
    #: 방향은 있으나 크기 배분 근거가 없어 signed score에서 보류한 신호 수.
    mixed_unallocated_signal_count: int = 0
    display_score: int = 0
    display_clamped: bool = False

    @property
    def narrative_eligible(self) -> bool:
        """사용자 서술에 쓸 수 있는가 — V2 부호로 계산됐을 때만."""
        return self.source is SlotStatusSource.POLARITY_V2

    @property
    def has_opposing_signals(self) -> bool:
        """반대 방향 신호가 함께 있는가.

        상태 라벨만 전달하면 ADVERSE_DOMINANT를 '나쁜 신호만 있다'로 서술한다.
        우세와 독점은 다르므로 이 값을 함께 넘겨 '전적으로 불리하다'를 막는다
        (2026-07-27 데굴님 지적 — MIXED_BALANCED뿐 아니라 우세 상태에도 필요).
        """
        return self.positive_total > 0 and self.negative_total > 0

    @property
    def has_unallocated_opposing_signals(self) -> bool:
        """수치로 배분하지 못한 혼재 관계가 함께 있는가.

        '확인 가능한 신호에서는 부담이 우세하지만, 방향을 수치로 배분하지 않은 혼재
        관계도 함께 있다'는 서술을 가능하게 한다.
        """
        return self.mixed_unallocated_signal_count > 0
