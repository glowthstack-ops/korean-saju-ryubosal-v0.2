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
ApproxBand = Literal["새벽", "아침", "낮", "저녁", "밤"]

#: 대략 시간대 → 시진(12지지) 후보. KST 생활 시간대 기준(2026-10-06 데굴님 승인 범위):
#: 새벽 03~07(寅卯) / 아침 07~11(辰巳) / 낮 11~15(午未) / 저녁 15~19(申酉) / 밤 19~03(戌亥子丑).
APPROX_BAND_BRANCHES: dict[str, tuple[str, ...]] = {
    "새벽": ("寅", "卯"),
    "아침": ("辰", "巳"),
    "낮": ("午", "未"),
    "저녁": ("申", "酉"),
    "밤": ("戌", "亥", "子", "丑"),
}
HOUR_BRANCHES: tuple[str, ...] = (
    "子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥",
)
#: 시진 → 대표 시각 범위(표시용).
HOUR_BRANCH_RANGE: dict[str, str] = {
    "子": "23~01시", "丑": "01~03시", "寅": "03~05시", "卯": "05~07시", "辰": "07~09시",
    "巳": "09~11시", "午": "11~13시", "未": "13~15시", "申": "15~17시", "酉": "17~19시",
    "戌": "19~21시", "亥": "21~23시",
}


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


class PillarVariant(BaseModel):
    """출생시각에 따라 연·월·일주가 달라지는 경우(입춘·절입·일 경계)의 명식 변형 1개."""

    year_ganji: str
    month_ganji: str
    day_ganji: str
    hour_branches: list[str] = Field(default_factory=list)  # 이 변형이 되는 시진들
    is_base: bool = False  # 정오 기준(현재 표시 중) 명식인가


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
    #: 후보 집합의 근거: 'all12' | 'band:아침' | 'hint:子'(성향 추정 — 확정 아님)
    basis: str = "all12"
    approx_band: str | None = None
    hint_branch: str | None = None
    #: 연·월·일주 변형(경계 당일). 1개면 명식 자체는 확정, 2개 이상이면 분기.
    pillar_variants: list[PillarVariant] = Field(default_factory=list)
    strength_band: ConsensusItem
    geokguk: ConsensusItem
    useful_gods: ConsensusItem
    #: 확정에서 제외할 항목 키(상이 항목): 'strength_band' | 'geokguk' | 'useful_gods' |
    #: 'year_pillar' | 'month_branch' | 'day_master'(경계 당일 — 명식 자체가 갈림)
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
