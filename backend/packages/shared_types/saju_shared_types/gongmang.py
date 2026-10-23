"""공망 체계 타입 — 2축 상태(VOID_STATE × ACTIVATION)·강도(자왕)·확장 공망 사실 (2026-10-23).

doc/v2_2/GONGMANG_HAP_SEMANTICS.md §2·§3·§7 의 구조를 pydantic 으로 고정한다. 전부 **서술 전용**
이다 — 점수·게이트·선별에 쓰지 않는다(절대 원칙 10: 길흉 가중 규칙은 미도입, 사실·등급만 전달).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

VoidState = Literal["FULL_VOID", "PARTIAL_VOID", "RELEASED"]
Activation = Literal["DORMANT", "CONTACTED", "ACTIVATED"]
StimulusKind = Literal[
    "fill", "clash", "punishment", "six_combine", "trine", "half_trine", "directional",
    "hidden_combine",
]
Intensity = Literal["강", "중", "약"]

VOID_STATE_KO: dict[str, str] = {
    "FULL_VOID": "완전공망", "PARTIAL_VOID": "부분해공", "RELEASED": "해공",
}
ACTIVATION_KO: dict[str, str] = {"DORMANT": "잠복", "CONTACTED": "접촉", "ACTIVATED": "활성"}
STIMULUS_KO: dict[str, str] = {
    "fill": "전실(같은 글자)", "clash": "충", "punishment": "형", "six_combine": "육합",
    "trine": "삼합국", "half_trine": "반합", "directional": "방합", "hidden_combine": "암합",
}


class GongmangStimulus(BaseModel):
    """운 지지가 원국 공망 자리 글자에 가한 자극 1건."""

    kind: StimulusKind
    luck_branch: str
    natal_branch: str
    natal_position: str  # year/month/hour
    strength: float = Field(ge=0.0, le=1.0)  # 해공 강도 등급(SSOT §3) — 점수 아님
    partner_void: bool = False  # 합 상대(운 글자)까지 공망 글자 — 해공력 감산
    note: str = ""


class GongmangSlotState(BaseModel):
    """원국 공망 자리 1개의 상태 — 특정 운 기둥 기준."""

    natal_branch: str
    position: str
    position_ko: str
    ten_god: str  # 본기 십성
    intensity: Intensity  # 자왕(세력) 등급 — 통설·가설
    intensity_basis: str
    void_state: VoidState
    activation: Activation
    stimuli: list[GongmangStimulus] = Field(default_factory=list)


class GongmangTransitState(BaseModel):
    """운 기둥 1개에 대한 공망 상태 묶음."""

    luck_label: str
    luck_ganji: str
    slots: list[GongmangSlotState] = Field(default_factory=list)
    # 공망 글자가 원국에 없는데 운에서 오는 경우(빈 자리 채움·전실). 대운은 비운다(대운 공망 무시).
    fill_absent: list[str] = Field(default_factory=list)


class ExtendedGongmang(BaseModel):
    """확장 공망 사실(산출만 — 해석 규칙 미도입, 2026-10-23 데굴님 승인 범위)."""

    xun_head: str  # 일주가 속한 旬 — '甲子旬' (동순 비교용 사실)
    # 사대공망 결 납음 오행 — 甲子·甲午旬 水 / 甲寅·甲申旬 金 / 甲辰·甲戌旬 None
    sadae_missing_element: str | None = None
    sadae_hits: list[str] = Field(default_factory=list)  # 결 오행 납음을 가진 다른 기둥(연/월/시)
    jeollo: bool = False  # 절로공망 — 시간이 壬·癸
    hohwan: list[str] = Field(default_factory=list)  # 호환공망 — '연↔일' / '일↔시'
    facts_ko: list[str] = Field(default_factory=list)  # 프롬프트·화면용 사실 문장
