"""택일(Date Selection) schemas (v2.2 Phase 7, docs/02 E10).

택일 = 날짜 후보 **랭킹** 문제 — 상위 흐름(대운/세운)이 허용하는 기간 안에서 실행일을
최적화한다. "좋은 날"이 아니라 **가능한 날 중 가장 좋은 날**(Reality Constraint).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .events import EventKey


class DateScores(BaseModel):
    """5단계 부분점수 + 최종 (docs/02 E10 DateCandidate.scores)."""

    macro_flow: int = Field(ge=0, le=100)
    month_fit: int = Field(ge=0, le=100)
    day_execution: int = Field(ge=0, le=100)
    calendar_rule: int = Field(ge=0, le=100)
    reality_fit: int = Field(ge=0, le=100)
    final: int = Field(ge=0, le=100)


class HourFit(BaseModel):
    """시진(時辰) 적합도 1칸 (T7.7 — docs/08 C17 '로또 사러 가기 좋은 시간대')."""

    branch: str  # 子~亥
    time_range: str  # '23:00~01:00'
    fit: float = Field(ge=0.0, le=1.0)
    note: str = ""


class DateCandidate(BaseModel):
    """택일 후보 1건 (docs/02 E10)."""

    date: str
    purpose: EventKey
    ganji: str = ""
    scores: DateScores
    risk_score: int = Field(ge=0, le=100, default=0)
    reasons: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    recommendation: str = "acceptable"  # recommended | acceptable | avoid
    is_holiday: bool = False
    is_weekend: bool = False
    son_eomneun_nal: bool = False
    hour_fits: list[HourFit] = Field(default_factory=list)  # 시진 요청 시에만


class DateSelectionResult(BaseModel):
    """택일 결과 — 랭킹 + 회피일."""

    purpose: EventKey
    candidates: list[DateCandidate] = Field(default_factory=list)
    avoid_dates: list[dict] = Field(default_factory=list)  # {'date','reason'}
    cautions: list[str] = Field(default_factory=list)  # 목적 공통 경고(변동성 등)
