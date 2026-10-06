"""이동 시기 shadow — 계절 묶임·삼합 왕지 트리거 감지 (관측 전용, 2026-10-06 데굴님 승인).

SSOT: doc/v2_2/MOVEMENT_TIMING_SHADOW.md

영상 규칙("같은 계절 글자가 모이면 그 계절에 묶이고, 묶인 생지를 끌어당기는 것은 삼합의
왕지다")을 **별도 가설**로 명세해 감지·로그만 한다. 3층 분리(marriage_marker_shadow 와 동일):
  - Detection(이 모듈): 묶임 등급·근거·보조 플래그, 왕지/고지 도래 기간을 계산한다.
  - Interpretation: 없음 — "떠나고 싶어도 못 떠난다" 류 문장은 만들지 않는다.
  - Exposure: 사용자 서술·LLM 입력·사건 점수에 연결하지 않는다(승격은 shadow 지표 검토 후
    별도 승인).

플래그는 해석이 아니라 관측값이다. 특히 `natal_royal_present`(대응 왕지 원국 보유)는 영상 §5의
'자의적 이동 성향' 근거 후보일 뿐이며 성향 서술로 쓰지 않는다(검토 의견 §5 보류).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel, Field

from saju_shared_types.constants import THREE_HARMONY
from saju_shared_types.enums import Branch
from saju_shared_types.pillars import FourPillarsResult

#: 계절 → 방합 세 글자(생지·왕지·고지 순은 아님 — 계절 순).
SEASONS: dict[str, tuple[Branch, Branch, Branch]] = {
    "봄": (Branch.IN, Branch.MYO, Branch.JIN),
    "여름": (Branch.SA, Branch.O, Branch.MI),
    "가을": (Branch.SIN, Branch.YU, Branch.SUL),
    "겨울": (Branch.HAE, Branch.JA, Branch.CHUK),
}
#: 계절의 앵커(생지) — 영상 "인 중심·사 중심·신 중심·해 중심".
SEASON_ANCHOR: dict[str, Branch] = {
    "봄": Branch.IN, "여름": Branch.SA, "가을": Branch.SIN, "겨울": Branch.HAE,
}
_STORAGE = {Branch.JIN, Branch.SUL, Branch.CHUK, Branch.MI}
#: 생지 충 짝(寅↔申·巳↔亥) — 앵커가 원국 내 충을 받는지 관측용.
_ANCHOR_CLASH: dict[Branch, Branch] = {
    Branch.IN: Branch.SIN, Branch.SIN: Branch.IN, Branch.SA: Branch.HAE, Branch.HAE: Branch.SA,
}
#: 월운 라벨 길이(YYYY-MM).
_MONTH_LABEL_LEN = 7
_RELOCATION_KEYS = ("relocation",)
_CAREER_KEYS = ("career_change",)
_SAMHAP_PREFIXES = ("삼합완성", "반합성립", "삼합기여")


def _trine_roles(anchor: Branch) -> tuple[Branch, Branch]:
    """앵커(생지)가 속한 삼합국의 (왕지, 고지) — THREE_HARMONY(멤버·오행·왕지) 단일 소스."""
    for members, _element, royal in THREE_HARMONY:
        if anchor in members:
            storage = next(b for b in members if b in _STORAGE)
            return royal, storage
    raise ValueError(f"삼합국을 찾을 수 없는 생지: {anchor}")


class SeasonBound(BaseModel):
    """계절 묶임 판정(관측값). tier='none' 이면 season·anchor 는 None."""

    season: str | None = None
    anchor: str | None = None
    tier: str = "none"  # none | moderate | strong
    evidence: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    royal_branch: str | None = None  # 앵커를 끌어당기는 삼합 왕지(트리거 후보)
    storage_branch: str | None = None  # 같은 삼합의 고지(트리거 아님 — 영상 §3)


class PeriodRef(BaseModel):
    """운 기간 1개의 최소 참조 — ManseV2Result.luck_cycles 에서 뽑는다(재계산 없음)."""

    level: str  # daewoon | year | month
    label: str  # 'DW:壬辰' | '2026' | '2026-06'
    branch: str
    relations: list[str] = Field(default_factory=list)  # LuckPillar.relations_to_chart


class RoyalTrigger(BaseModel):
    """왕지(또는 고지) 도래 기간 관측 1건."""

    period: str
    level: str
    branch: str
    kind: str  # royal(트리거 후보) | storage(명시적 비트리거)
    overlaps_samhap: bool = False  # 이미 삼합·반합 hit 이 있는 기간(중복 가산 차단 근거)
    has_relocation_candidate: bool = False
    has_career_candidate: bool = False

    def compact(self) -> str:
        """로그용 축약 — 'month:2026-06:午:royal:samhap=0:reloc=1:career=0'."""
        return (
            f"{self.level}:{self.period}:{self.branch}:{self.kind}:"
            f"samhap={int(self.overlaps_samhap)}:reloc={int(self.has_relocation_candidate)}:"
            f"career={int(self.has_career_candidate)}"
        )


class MovementTimingShadow(BaseModel):
    """shadow 결과 — 로그 전용(사용자 출력·LLM 입력·점수 연결 금지)."""

    season_bound: SeasonBound
    royal_triggers: list[RoyalTrigger] = Field(default_factory=list)
    unevaluated: list[str] = Field(default_factory=list)


def _natal_branches(pillars: FourPillarsResult) -> list[Branch]:
    out = [Branch(pillars.year.branch), Branch(pillars.month.branch), Branch(pillars.day.branch)]
    if pillars.hour is not None:
        out.append(Branch(pillars.hour.branch))
    return out


def _evaluate_season(
    season: str, natal: Sequence[Branch], month_branch: Branch,
) -> tuple[str, list[str]]:
    """한 계절의 묶임 등급·근거. 앵커(생지)가 없으면 ('none', [])."""
    members = SEASONS[season]
    anchor = SEASON_ANCHOR[season]
    counts = Counter(b for b in natal if b in members)
    if counts[anchor] == 0:
        return "none", []
    evidence: list[str] = []
    distinct = set(counts)
    if len(distinct) == 3:
        evidence.append("directional_full")
    if counts[anchor] >= 2:
        evidence.append("repeat_birth_branch")
    if sum(counts.values()) >= 3:
        evidence.append("season_dominance")
    if "directional_full" not in evidence and len(distinct) >= 2 and month_branch in members:
        evidence.append("directional_partial_with_month")
    if "directional_full" in evidence or "season_dominance" in evidence:
        return "strong", evidence
    if evidence:
        return "moderate", evidence
    return "none", []


_TIER_RANK = {"none": 0, "moderate": 1, "strong": 2}


def detect_season_bound(pillars: FourPillarsResult) -> SeasonBound:
    """원국 4지지(시지 없으면 3)로 계절 묶임을 판정한다.

    여러 계절이 동시에 조건을 만족하면 등급이 높은 쪽, 같으면 월지가 속한 계절, 그래도 같으면
    글자 수가 많은 계절을 고른다. 보조 플래그는 어느 경우에도 해석하지 않고 기록만 한다.
    """
    natal = _natal_branches(pillars)
    month_branch = Branch(pillars.month.branch)
    best: tuple[int, int, int, str, list[str]] | None = None
    for season in SEASONS:
        tier, evidence = _evaluate_season(season, natal, month_branch)
        if tier == "none":
            continue
        members = SEASONS[season]
        key = (
            _TIER_RANK[tier], int(month_branch in members),
            sum(1 for b in natal if b in members),
        )
        if best is None or key > best[:3]:
            best = (*key, season, evidence)
    flags: list[str] = []
    if month_branch in _STORAGE:
        flags.append("month_is_storage")  # 영상 §4 — 辰戌丑未월은 월지 하나로 설명 보류
    if best is None:
        return SeasonBound(flags=flags)
    _r, _m, _n, season, evidence = best
    anchor = SEASON_ANCHOR[season]
    royal, storage = _trine_roles(anchor)
    if month_branch in SEASONS[season]:
        flags.append("month_in_season")
    if _ANCHOR_CLASH[anchor] in natal:
        flags.append("anchor_clashed")
    if royal in natal:
        flags.append("natal_royal_present")  # 관측값 — 성향 서술 금지(검토 의견 §5)
    tier = "strong" if _r == 2 else "moderate"
    return SeasonBound(
        season=season, anchor=anchor.value, tier=tier, evidence=evidence, flags=flags,
        royal_branch=royal.value, storage_branch=storage.value,
    )


def _candidate_periods(candidates: Iterable[Any], keys: tuple[str, ...]) -> set[str]:
    out: set[str] = set()
    for c in candidates:
        key = str(getattr(c, "event_key", ""))
        if any(key == k or key.endswith(f".{k}") for k in keys):
            period = str(getattr(c, "period", "") or "")
            if period:
                out.add(period)
    return out


def _has_candidate(period: str, level: str, periods: set[str]) -> bool:
    """그 기간에 후보가 있는가 — 연 트리거는 그 해의 월 후보도, 월 트리거는 그 해 후보도 인정."""
    if level == "daewoon":
        return False
    if period in periods:
        return True
    if level == "year":
        return any(p.startswith(f"{period}-") for p in periods)
    return period[:4] in periods


def detect_royal_triggers(
    bound: SeasonBound, periods: Sequence[PeriodRef], candidates: Iterable[Any],
) -> list[RoyalTrigger]:
    """묶인 계절의 왕지·고지가 도래하는 기간을 기록한다(묶임이 없으면 빈 리스트)."""
    if bound.tier == "none" or bound.royal_branch is None:
        return []
    cands = list(candidates)
    reloc = _candidate_periods(cands, _RELOCATION_KEYS)
    career = _candidate_periods(cands, _CAREER_KEYS)
    out: list[RoyalTrigger] = []
    for ref in periods:
        if ref.branch == bound.royal_branch:
            kind = "royal"
        elif ref.branch == bound.storage_branch:
            kind = "storage"
        else:
            continue
        out.append(RoyalTrigger(
            period=ref.label, level=ref.level, branch=ref.branch, kind=kind,
            overlaps_samhap=any(r.startswith(_SAMHAP_PREFIXES) for r in ref.relations),
            has_relocation_candidate=_has_candidate(ref.label, ref.level, reloc),
            has_career_candidate=_has_candidate(ref.label, ref.level, career),
        ))
    return out


def periods_from_result(result: Any) -> list[PeriodRef]:
    """ManseV2Result.luck_cycles 의 대운·세운·월운을 PeriodRef 로 뽑는다(없으면 빈 리스트)."""
    cycles = getattr(result, "luck_cycles", None)
    if cycles is None:
        return []
    out: list[PeriodRef] = []
    for dw in getattr(cycles, "daewoon_table", []) or []:
        out.append(PeriodRef(
            level="daewoon", label=f"DW:{dw.ganji}", branch=str(dw.branch),
            relations=list(dw.relations_to_chart or []),
        ))
    for lp in getattr(cycles, "yearly_luck", []) or []:
        out.append(PeriodRef(level="year", label=str(lp.label), branch=str(lp.branch),
                             relations=list(lp.relations_to_chart or [])))
    for lp in getattr(cycles, "monthly_luck", []) or []:
        if len(str(lp.label)) == _MONTH_LABEL_LEN:
            out.append(PeriodRef(level="month", label=str(lp.label), branch=str(lp.branch),
                                 relations=list(lp.relations_to_chart or [])))
    return out


def detect_movement_timing_shadow(result: Any, candidates: Iterable[Any]) -> MovementTimingShadow:
    """계절 묶임 + 왕지 트리거 shadow — 결과는 로그 전용."""
    pillars = getattr(result, "pillars", None)
    if pillars is None:
        return MovementTimingShadow(season_bound=SeasonBound(), unevaluated=["pillars 없음"])
    bound = detect_season_bound(pillars)
    periods = periods_from_result(result)
    unevaluated: list[str] = []
    if not any(p.level == "month" for p in periods):
        unevaluated.append("월운 미포함 — 연·대운 트리거만 관측")
    unevaluated.append("대운 트리거는 후보 결합 미평가(기간 라벨이 연·월과 다름)")
    return MovementTimingShadow(
        season_bound=bound,
        royal_triggers=detect_royal_triggers(bound, periods, candidates),
        unevaluated=unevaluated,
    )
