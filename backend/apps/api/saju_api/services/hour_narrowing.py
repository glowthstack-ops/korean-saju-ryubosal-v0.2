"""시주 후보 좁히기 — 대략 시간대 + 성향 문항 (2026-10-06, doc/v2_2/HOUR_UNKNOWN_POLICY.md §8).

출생시간을 모르는 사용자가 ①대략 시간대(새벽·아침·낮·저녁·밤)로 후보 시진을 2~4개로 줄이고
②각 후보 시주가 뜻하는 성향 문장(시주 천간 십성·시지 본기 십성·12운성 — 사전 `ten_gods_text` ·
`twelve_stages_text` 의 natal 문구)에 "나와 맞다"를 고르면, 일치 수로 후보를 순위화한다.

결과는 **추정**이다. `hour_branch_hint` 로 저장되어도 시간 미상 모드는 유지되고(hour=None),
LLM 입력에는 '성향 추정 시진 — 확정 아님'으로 표기된다. 문장은 사전 문구를 그대로 쓰며 즉석 작문하지
않는다(절대원칙 12 와 같은 취지 — 엔진이 만든 문장만 노출).
"""

from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from saju_shared_types.birth_input import BirthInput
from saju_shared_types.hour_unknown import HOUR_BRANCH_RANGE

from . import manse_service

_DICTS = Path(__file__).resolve().parents[4] / "dictionaries"
_PALACE_NOTE = (
    "시주는 자녀·말년·결과의 자리로 보는 통설이 있어, 이 자리의 십성이 후반 인생의 결을 뜻한다고 "
    "읽는다."
)


def _load(name: str) -> dict:
    return json.loads((_DICTS / "interpretations" / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _texts() -> tuple[dict[str, str], dict[str, str]]:
    """십성명 → natal 문구, 12운성명 → natal 문구(사전 원문 그대로)."""
    tg = {str(i["tenGod"]): str(i["natal"]) for i in _load("ten_gods_text.json")["items"]}
    st = {str(i["stage"]): str(i["natal"]) for i in _load("twelve_stages_text.json")["items"]}
    return tg, st


class TraitStatement(BaseModel):
    """후보 시주에서 파생된 성향 문장 1개(사전 문구, 즉석 작문 아님)."""

    id: str  # '{시진}:{source}' — 예 '午:stem'
    source: str  # stem(시간 십성) | branch(시지 본기 십성) | stage(12운성)
    label: str  # '시간 정관' 등
    text: str


class HourTraitCandidate(BaseModel):
    """후보 시진 1개와 성향 문장."""

    hour_branch: str
    ganji: str
    time_range: str
    stem_ten_god: str
    branch_ten_god: str
    twelve_stage: str
    statements: list[TraitStatement] = Field(default_factory=list)


class HourTraitsResponse(BaseModel):
    """POST /manse/hour-traits 응답."""

    basis: str  # 'all12' | 'band:아침'
    candidates: list[HourTraitCandidate]
    note: str = _PALACE_NOTE


class HourNarrowRequest(BaseModel):
    """POST /manse/hour-narrow 요청 — 사용자가 '맞다'고 고른 문장 id 목록."""

    birth: BirthInput
    picked: list[str] = Field(default_factory=list, max_length=60)


class HourRank(BaseModel):
    hour_branch: str
    ganji: str
    time_range: str
    matched: int
    total: int
    share: float  # matched/total(0~1)


class HourNarrowResponse(BaseModel):
    """순위 + 추천 추정 시진(단독 1위이고 2개 이상 일치할 때만)."""

    ranking: list[HourRank]
    recommended: str | None = None
    confidence: str  # 'none' | 'low' | 'medium'
    note: str


def trait_candidates(birth: BirthInput) -> HourTraitsResponse:
    """후보 시진별 성향 문장 — 시간이 있으면 빈 목록(좁힐 것이 없다)."""
    if birth.birth_time is not None and not birth.birth_time_unknown:
        return HourTraitsResponse(basis="known", candidates=[])
    # 추정값이 있어도 시간대 전체를 다시 보여 준다(재선택 가능).
    base = birth.model_copy(update={"hour_branch_hint": None})
    branches, basis = manse_service.candidate_hour_branches(base)
    tg_text, st_text = _texts()
    out: list[HourTraitCandidate] = []
    for hb in branches:
        r = manse_service.calculate(manse_service.candidate_birth(base, hb))
        if r.pillars is None or r.pillars.hour is None:
            continue
        hp = r.pillars.hour
        statements: list[TraitStatement] = []
        for source, label, name, table in (
            ("stem", f"시간 {hp.stem_ten_god}", hp.stem_ten_god, tg_text),
            ("branch", f"시지 {hp.branch_main_ten_god}", hp.branch_main_ten_god, tg_text),
            ("stage", f"시주 운성 {hp.twelve_unseong}", hp.twelve_unseong, st_text),
        ):
            text = table.get(name)
            if text:
                statements.append(
                    TraitStatement(id=f"{hb}:{source}", source=source, label=label, text=text),
                )
        out.append(HourTraitCandidate(
            hour_branch=hb, ganji=hp.ganji, time_range=HOUR_BRANCH_RANGE[hb],
            stem_ten_god=hp.stem_ten_god, branch_ten_god=hp.branch_main_ten_god,
            twelve_stage=hp.twelve_unseong, statements=statements,
        ))
    return HourTraitsResponse(basis=basis, candidates=out)


def narrow(req: HourNarrowRequest) -> HourNarrowResponse:
    """고른 문장 수로 후보를 순위화한다. 같은 문구를 여러 후보가 공유하면 모두 가산한다."""
    traits = trait_candidates(req.birth)
    picked = set(req.picked)
    # 같은 문장(text)이 여러 후보에 있으면 한 후보에서 고른 선택이 동일 문장 후보 전부에 적용되도록
    # text 기준으로 본다.
    picked_texts = {
        st.text for c in traits.candidates for st in c.statements if st.id in picked
    }
    matched: Counter[str] = Counter()
    totals: dict[str, int] = {}
    for c in traits.candidates:
        totals[c.hour_branch] = len(c.statements)
        matched[c.hour_branch] = sum(1 for st in c.statements if st.text in picked_texts)
    ranking = sorted(
        (
            HourRank(
                hour_branch=c.hour_branch, ganji=c.ganji, time_range=c.time_range,
                matched=matched[c.hour_branch], total=totals[c.hour_branch],
                share=(round(matched[c.hour_branch] / totals[c.hour_branch], 3)
                       if totals[c.hour_branch] else 0.0),
            )
            for c in traits.candidates
        ),
        key=lambda r: (-r.matched, -r.share, r.hour_branch),
    )
    recommended: str | None = None
    confidence = "none"
    if len(ranking) >= 1 and ranking[0].matched >= 2:
        second = ranking[1].matched if len(ranking) > 1 else 0
        if ranking[0].matched > second:
            recommended = ranking[0].hour_branch
            confidence = "medium" if ranking[0].matched - second >= 2 else "low"
    note = (
        "성향 문항으로 좁힌 결과는 추정이며 확정이 아니다. 추정 시진을 적용해도 시간 미상 모드는 "
        "유지되고 풀이에는 '성향 추정 시진' 으로만 표기된다. 출생 기록으로 시간을 확인하면 추정을 "
        "대체할 것."
    )
    return HourNarrowResponse(
        ranking=ranking, recommended=recommended, confidence=confidence, note=note,
    )
