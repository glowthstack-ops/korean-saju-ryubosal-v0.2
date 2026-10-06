"""출생시간 미상(시주 없음) 분석 스키마 (2026-10-06, 데굴님 승인 — doc/v2_2/HOUR_UNKNOWN_POLICY.md).

원칙: **미상은 없음이 아니고, 불완전 정보는 확정이 아니다.** 시주가 없으면 3기둥 결과를 그대로
확정값으로 쓰지 않고, 가능한 12시진을 모두 계산해 판단이 유지되는지(일치) 갈리는지(상이)를
항목별로 기록한다. 상이 항목(특히 용희신)은 풀이에 적극 활용하지 않는다.

docs/11 의 상태 구분과 대응: 확정 / 부분 확인 / 후보별 일치·상이 / 산출 불가 / 범위 표시.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ConsensusStatus = Literal["agree", "differ"]


class HourCandidate(BaseModel):
    """12시진 후보 1개의 핵심 판정값 — 대표 시각(짝수 정시)으로 계산한 결과."""

    hour_branch: str  # 子~亥
    ganji: str  # 후보 시주 간지(예: 甲子)
    strength_band: str = ""
    geokguk: str = ""
    useful_gods: str = ""  # '용土·희火·기木' 형태(비교 키)
    yongsin: str = ""
    year_ganji: str = ""  # 연·월·일주가 후보에 따라 바뀌는지(절입·일 경계) 확인용
    month_ganji: str = ""
    day_ganji: str = ""
    daewoon_start_exact: float | None = None


class ConsensusItem(BaseModel):
    """항목 1개의 후보 비교 결과."""

    status: ConsensusStatus
    base: str = ""  # 3기둥(시주 제외) 계산값 — 참고용이지 확정값이 아니다
    values: list[str] = Field(default_factory=list)  # 후보에서 나온 서로 다른 값(출현 순)

    @property
    def agree(self) -> bool:
        return self.status == "agree"


class HourUnknownAnalysis(BaseModel):
    """시간 미상 분석 — ManseV2Result.hour_unknown (시간이 있으면 None)."""

    candidates: list[HourCandidate] = Field(default_factory=list)
    strength_band: ConsensusItem
    geokguk: ConsensusItem
    useful_gods: ConsensusItem
    #: 확정에서 제외할 항목 키(상이 항목): 'strength_band' | 'geokguk' | 'useful_gods'
    unconfirmed: list[str] = Field(default_factory=list)
    #: 대운수(기운 나이) 후보 범위 — 정오 단일값 대신 표시용.
    daewoon_start_range: tuple[float, float] | None = None
    #: 연·월·일주가 후보 시각에 따라 달라지는 경우(입춘·절입·일 경계) 경고.
    boundary_warnings: list[str] = Field(default_factory=list)
    #: 사용자·LLM 공용 1회 고지 문구(엔진 생성, 즉석 작문 금지).
    notice: str = ""

    def is_unconfirmed(self, key: str) -> bool:
        """해당 항목이 후보에 따라 갈려 확정 제외인가."""
        return key in self.unconfirmed
