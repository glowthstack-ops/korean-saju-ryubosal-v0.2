"""OA-9c G0 — 불리 발현 자격 게이트 (shadow 전용, 라이브 불변).

OA-9a 실측: 불리 관계(충·형·파·해)가 **하나도 없는** 편재 카드 421건에서
`overspend_caution` 이 주의 슬롯을 100% 차지했다. 같은 코호트에서 편재 기여만
제거하면 5.0% 로 무너지므로, 이는 편재 단독 부양이다. 즉 사전 스키마가

    편재가 활성됨 → 재물이 오늘의 소재다          (성립)
    편재가 활성됨 → 과소비·손실 위험이 높다        (성립하지 않는다)

두 연결을 구분하지 못한다.

G0 계약 — 주의 사건은 **두 종류의 증거를 모두** 요구한다:

    money_subject_activation              재물·거래·자원이 오늘의 소재다
    AND
    independent money-relevant adverse    그것이 과잉·손실·충돌로 발현할 별도 근거
    manifestation

여기서 재성(편재·정재)은 앞의 절반만 충족한다. **같은 재성 근거가 뒤의 절반까지
충족해서는 안 된다** — 이것이 G0 의 핵심 불변식이다.

점수와 affinity 는 건드리지 않는다. `raw_probability`·`raw_rank` 는 그대로 보존하고
**표시·선택 자격만** fail-closed 로 분리한다(감사 가능성 유지).

주의 슬롯은 사용자 카드에 문장으로 노출되므로, 헤드라인만 막는 것으로는 의미론적
오류가 남는다. 따라서 `caution_slot_eligible` 부터 막는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from saju_engines.daily_ilju_fortune import (
    _DICTS_DEFAULT,
    _branch_relations,
    _score_event,
    _ScoredEvent,
)
from saju_shared_types.constants import hidden_stems_for, ten_god
from saju_shared_types.daily_fortune import DayGanjiContext
from saju_shared_types.enums import Branch, HiddenStemType, Stem

#: 게이트 계약 버전 — shadow 산출물에 찍어 비교 대상을 특정한다.
G0_CONTRACT_VERSION = "g0.v1-money-slice"

#: 재물 주제를 활성화하는 십성. **주제 활성 전용** — 불리 발현 근거로 쓸 수 없다.
WEALTH_TEN_GODS = ("편재", "정재")
#: 재성을 극하는 십성(비겁) — 분탈·경쟁·통제 저하. 재성과 독립된 원인군이다.
CONTENTION_TEN_GODS = ("비견", "겁재")
#: 불리 관계 — 구조적 마찰.
ADVERSE_RELATIONS = ("clash", "punishment", "break", "harm")

# ── 게이트 코드 ────────────────────────────────────────────────────────────

#: 주제는 활성이나 독립된 불리 발현 근거가 없다 — 자격 박탈.
ADVERSE_MANIFESTATION_NOT_ESTABLISHED = "ADVERSE_MANIFESTATION_NOT_ESTABLISHED"
#: 게이트를 통과한 주의 사건이 하나도 없다.
NO_ELIGIBLE_CAUTION_EVENT = "NO_ELIGIBLE_CAUTION_EVENT"
#: 주의를 억지로 만들지 않고 보조 표현으로 전환했다.
CAUTION_FALLBACK_TO_SUPPORT = "CAUTION_FALLBACK_TO_SUPPORT"
#: 주제 자체가 활성이 아니다 — G0 판정 대상이 아니다(자격 유지).
SUBJECT_NOT_ACTIVATED = "SUBJECT_NOT_ACTIVATED"

# ── 원인군 ────────────────────────────────────────────────────────────────

#: 비겁이 재성을 극한다 — 분탈·경쟁·씀씀이 통제 저하.
WEALTH_CONTENTION = "WEALTH_CONTENTION"
#: 재성을 품은 지지가 충·형·파·해를 받는다 — 재물 자리의 손상.
WEALTH_BRANCH_CONFLICT = "WEALTH_BRANCH_CONFLICT"


@dataclass(frozen=True)
class AdverseEvidence:
    """불리 발현 근거 1건의 출처(provenance).

    감사에서 "무엇이 이 경고를 열었는가"를 사람이 되짚을 수 있어야 하므로, 값 하나가
    아니라 출처를 통째로 남긴다.
    """

    cause_group: str        # WEALTH_CONTENTION | WEALTH_BRANCH_CONFLICT
    evidence_id: str        # 카드 안에서 유일한 안정 식별자
    evidence_role: str      # 항상 "independent_adverse_manifestation"
    domain_relevance: str   # 항상 "money" — 다른 도메인 불리 신호는 여기 오지 않는다
    source_relation: str    # 관계 종류(clash 등). 십성 근거면 ""
    source_pattern: str     # 사람이 읽는 명리 표현
    strength: float


@dataclass(frozen=True)
class G0Decision:
    """사건 1개의 G0 판정 — raw 결과와 자격을 분리해 보존한다."""

    event_key: str
    raw_probability: int
    raw_rank: int
    subject_activated: bool
    caution_slot_eligible: bool
    headline_eligible: bool
    gate_codes: tuple[str, ...]
    adverse_evidence_provenance: tuple[AdverseEvidence, ...]


# ── 분류(taxonomy) 로드 ───────────────────────────────────────────────────


@lru_cache(maxsize=1)
def load_taxonomy(dictionaries_dir: Path = _DICTS_DEFAULT) -> dict[str, Any]:
    """OA-9b 분류 sidecar. 런타임 스냅샷과 분리돼 있어 엔진은 읽지 않는다."""
    path = dictionaries_dir / "daily_event_taxonomy.json"
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def g0_target_keys(dictionaries_dir: Path = _DICTS_DEFAULT) -> tuple[str, ...]:
    """이번 슬라이스에서 게이트할 사건 — 승인된 rollout 범위만.

    "구조상 G0 대상인가"(`g0_candidate`)와 "이번 실험에 포함됐는가"
    (`g0_rollout_scope`)를 섞지 않는다. document 3종은 `deferred_document` 로
    남아 있어 여기 오지 않는다.
    """
    events = load_taxonomy(dictionaries_dir)["events"]
    return tuple(sorted(
        k for k, t in events.items() if t.get("g0_rollout_scope") == "money_slice"
    ))


# ── 주제 활성 ─────────────────────────────────────────────────────────────


def _stem_ten_god(day_master: Stem, target: Stem) -> str:
    return "비견" if day_master == target else ten_god(day_master, target).value


def _chart_stems(ilju_stem: Stem, ctx: DayGanjiContext) -> tuple[tuple[str, Stem], ...]:
    """자리 이름과 천간 — 근거 식별자에 자리를 남기기 위해 함께 든다."""
    return (
        ("day_stem", Stem(ctx.day_stem)),
        ("month_stem", Stem(ctx.month_stem)),
        ("year_stem", Stem(ctx.year_stem)),
    )


def _chart_branches(ilju_branch: Branch, ctx: DayGanjiContext) -> tuple[tuple[str, Branch], ...]:
    return (
        ("ilju_branch", ilju_branch),
        ("day_branch", Branch(ctx.day_branch)),
        ("month_branch", Branch(ctx.month_branch)),
        ("year_branch", Branch(ctx.year_branch)),
    )


def wealth_subject_activated(ilju_stem: Stem, ilju_branch: Branch, ctx: DayGanjiContext) -> bool:
    """재물·거래·자원이 오늘의 소재인가 — 재성의 **존재** 여부.

    사건의 affinity 값이 아니라 명식·운의 십성 구성으로 판정한다. 그래야 이 판정이
    사건 사전을 고쳐도 흔들리지 않는다.

    Args:
        ilju_stem: 일주 천간(일간).
        ilju_branch: 일주 지지.
        ctx: 그 날의 일진·월운·세운 간지.

    Returns:
        재성이 천간에 투출했거나 지지 본기·중기에 있으면 True.
    """
    for _pos, stem in _chart_stems(ilju_stem, ctx):
        if _stem_ten_god(ilju_stem, stem) in WEALTH_TEN_GODS:
            return True
    for _pos, branch in _chart_branches(ilju_branch, ctx):
        for stem, kind, _w in hidden_stems_for(branch):
            if kind is HiddenStemType.RESIDUAL:
                continue  # 여기(잔기)만으로는 주제 활성으로 보지 않는다
            if _stem_ten_god(ilju_stem, stem) in WEALTH_TEN_GODS:
                return True
    return False


def _branch_holds_wealth(ilju_stem: Stem, branch: Branch) -> bool:
    return any(
        kind is not HiddenStemType.RESIDUAL
        and _stem_ten_god(ilju_stem, stem) in WEALTH_TEN_GODS
        for stem, kind, _w in hidden_stems_for(branch)
    )


# ── 독립 불리 근거 ─────────────────────────────────────────────────────────


def money_adverse_evidence(
    ilju_stem: Stem, ilju_branch: Branch, ctx: DayGanjiContext
) -> tuple[AdverseEvidence, ...]:
    """재물 영역의 **독립** 불리 발현 근거 — 없으면 빈 튜플.

    두 원인군만 인정한다. 둘 다 재성 affinity 와 무관한 값에서 나온다:

    WEALTH_CONTENTION       비겁이 재성을 극한다(분탈·경쟁·통제 저하).
                            십성 관계로만 판정하므로 사건의 재성 계수와 독립이다.
    WEALTH_BRANCH_CONFLICT  재성을 품은 지지가 충·형·파·해를 받는다.
                            강도는 전적으로 관계에서 나오고, 재성은 **어느 지지가
                            재물 자리인지 지목**하는 데만 쓰인다.

    다음은 근거로 인정하지 않는다 — 재성 자체, 재성 계수를 다시 포장한 값,
    우호 신호의 부재, 다른 도메인의 불리 신호, 무신호.

    Args:
        ilju_stem: 일주 천간(일간).
        ilju_branch: 일주 지지.
        ctx: 그 날의 일진·월운·세운 간지.

    Returns:
        근거 목록(원인군·근거 id 순 정렬). 같은 원인군이 여러 자리에서 나오면 모두 남긴다.
    """
    found: list[AdverseEvidence] = []

    # ① 비겁 — 재성을 극하는 독립 원인군
    for pos, stem in _chart_stems(ilju_stem, ctx):
        tg = _stem_ten_god(ilju_stem, stem)
        if tg in CONTENTION_TEN_GODS:
            found.append(AdverseEvidence(
                cause_group=WEALTH_CONTENTION,
                evidence_id=f"{pos}:{tg}",
                evidence_role="independent_adverse_manifestation",
                domain_relevance="money",
                source_relation="",
                source_pattern=f"{tg} 투출 — 재성 분탈",
                strength=1.0,
            ))
    for pos, branch in _chart_branches(ilju_branch, ctx):
        for stem, kind, weight in hidden_stems_for(branch):
            if kind is HiddenStemType.RESIDUAL:
                continue
            tg = _stem_ten_god(ilju_stem, stem)
            if tg in CONTENTION_TEN_GODS:
                found.append(AdverseEvidence(
                    cause_group=WEALTH_CONTENTION,
                    evidence_id=f"{pos}:장간:{tg}",
                    evidence_role="independent_adverse_manifestation",
                    domain_relevance="money",
                    source_relation="",
                    source_pattern=f"{tg} 지장간({kind.value}) — 재성 분탈",
                    strength=round(weight, 2),
                ))

    # ② 재성 지지의 충·형·파·해 — 강도는 관계에서만 나온다
    day_branch = Branch(ctx.day_branch)
    month_branch = Branch(ctx.month_branch)
    year_branch = Branch(ctx.year_branch)
    for pos, transit in (
        ("day_branch", day_branch),
        ("month_branch", month_branch),
        ("year_branch", year_branch),
    ):
        helpers = tuple(
            b for b in (day_branch, month_branch, year_branch) if b is not transit
        )
        hits = _branch_relations(transit, ilju_branch, helpers)
        # `relation` 은 관계 종류(충·형·파·해) 문자열이다. 위 장간 루프의 `kind`
        # (HiddenStemType)와 의미가 달라 같은 이름을 쓰면 타입 계약이 어긋난다.
        for relation in ADVERSE_RELATIONS:
            strength = hits.get(relation, 0.0)
            if strength <= 0:
                continue
            # 충돌하는 두 자리 중 하나가 재물 자리여야 재물 관련성이 성립한다.
            wealth_side = [
                name for name, b in (("ilju_branch", ilju_branch), (pos, transit))
                if _branch_holds_wealth(ilju_stem, b)
            ]
            if not wealth_side:
                continue
            found.append(AdverseEvidence(
                cause_group=WEALTH_BRANCH_CONFLICT,
                evidence_id=f"{pos}:{relation}:{'+'.join(wealth_side)}",
                evidence_role="independent_adverse_manifestation",
                domain_relevance="money",
                source_relation=relation,
                source_pattern=f"재성 지지 {relation} — 재물 자리 손상",
                strength=round(strength, 2),
            ))

    return tuple(sorted(found, key=lambda e: (e.cause_group, e.evidence_id)))


# ── 판정 ──────────────────────────────────────────────────────────────────


def gate_decision(
    scored: _ScoredEvent, raw_rank: int, ilju_stem: Stem, ilju_branch: Branch,
    ctx: DayGanjiContext,
) -> G0Decision:
    """사건 1개의 자격 판정 — 점수는 그대로 두고 자격만 정한다.

    Args:
        scored: raw 점수 산출 결과(불변).
        raw_rank: 게이트 이전 전체 순위(1-base).
        ilju_stem: 일주 천간.
        ilju_branch: 일주 지지.
        ctx: 그 날의 간지 맥락.

    Returns:
        자격·게이트 코드·근거 출처.
    """
    subject = wealth_subject_activated(ilju_stem, ilju_branch, ctx)
    provenance = money_adverse_evidence(ilju_stem, ilju_branch, ctx)

    if not subject:
        # 주제조차 활성이 아니면 이 사건은 애초에 상위권에 오지 않는다.
        # G0 는 "재성이 열어 준 경고"만 막는다 — 판정 대상 밖은 건드리지 않는다.
        return G0Decision(
            event_key=scored.event_key, raw_probability=scored.probability,
            raw_rank=raw_rank, subject_activated=False,
            caution_slot_eligible=True, headline_eligible=True,
            gate_codes=(SUBJECT_NOT_ACTIVATED,), adverse_evidence_provenance=(),
        )

    if not provenance:
        return G0Decision(
            event_key=scored.event_key, raw_probability=scored.probability,
            raw_rank=raw_rank, subject_activated=True,
            caution_slot_eligible=False, headline_eligible=False,
            gate_codes=(ADVERSE_MANIFESTATION_NOT_ESTABLISHED,),
            adverse_evidence_provenance=(),
        )

    return G0Decision(
        event_key=scored.event_key, raw_probability=scored.probability,
        raw_rank=raw_rank, subject_activated=True,
        caution_slot_eligible=True, headline_eligible=True,
        gate_codes=(), adverse_evidence_provenance=provenance,
    )


def evaluate_card(
    events: dict[str, dict], ilju_stem: Stem, ilju_branch: Branch, ctx: DayGanjiContext,
    dictionaries_dir: Path = _DICTS_DEFAULT,
) -> tuple[dict[str, _ScoredEvent], list[_ScoredEvent], dict[str, G0Decision]]:
    """카드 1장의 raw 점수와 G0 판정을 함께 산출한다.

    Args:
        events: 사건 카탈로그.
        ilju_stem: 일주 천간.
        ilju_branch: 일주 지지.
        ctx: 그 날의 간지 맥락.
        dictionaries_dir: 분류 sidecar 위치.

    Returns:
        (사건별 raw 점수, 자격 없는 사건을 제외한 후보 목록, 대상 사건별 판정)

        두 번째 값을 `_select_slots` 에 그대로 넘기면 슬롯 선발이 게이트를 반영한다.
        제외 대상은 전부 `slots == ["caution"]` 이라 good·support 슬롯에는 영향이 없다
        (회귀 `test_gate_touches_only_caution_slot` 이 이를 강제한다).
    """
    scored = {k: _score_event(k, e, ilju_stem, ilju_branch, ctx) for k, e in events.items()}
    order = sorted(scored.values(), key=lambda s: -s.probability)
    rank_of = {s.event_key: i for i, s in enumerate(order, 1)}

    decisions = {
        key: gate_decision(scored[key], rank_of[key], ilju_stem, ilju_branch, ctx)
        for key in g0_target_keys(dictionaries_dir)
        if key in scored
    }
    blocked = {k for k, d in decisions.items() if not d.caution_slot_eligible}
    survivors = [s for s in scored.values() if s.event_key not in blocked]
    return scored, survivors, decisions
