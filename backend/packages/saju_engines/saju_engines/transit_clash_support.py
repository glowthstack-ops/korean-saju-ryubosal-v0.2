"""운↔운 충 → 이동형 후보 보조 가산 (2026-10-15 데굴님 승인, 선택 항목).

배경: 대운 壬辰 ↔ 월운 戊戌의 辰戌충처럼 **운끼리의 충**은 사전계산 상호작용(층간 충)·재물 충개고·
합화 상태 수집기에서 계산되지만, 사건 점수의 관계 보정(`RelationPalaceEngine`)은 운↔원국 궁위 충만
다뤄 직장·소속 변화 후보에는 변화 근거로 닿지 않았다(2026-10-15 검수). 외부 검토 기준: 운↔운 충은
기본적으로 **변화의 보조 근거**다 — 그 충만으로 '무엇이 변하는가'를 특정하지 않고, 이동형 후보의
강도·구체성만 보강한다.

규칙(사전 `event_engine/transit_ten_god_branching.json` → `transit_clash_mobility_support`):
  - 거버닝 스택(대운·세운·월운·일운)의 서로 다른 층 사이 지지 충을 모은다.
  - 대상 사건(career_change·relocation) 후보에 사전 상수 bonus 를 **한 후보에 한 번만** 더한다 —
    같은 충을 같은 사건 안에서 여러 이름으로 반복 가산하지 않는다. 쌍 전부를 reason 1건에 적는다.
  - 비겁 이동 시드·기준점은 건드리지 않는다. 플래그 `SAJU_TRANSIT_CLASH_SUPPORT_ENABLED`(기본 OFF).
규칙 기반이며 LLM 판정을 쓰지 않는다(절대원칙 1). 점수 상수는 사전에서 읽는다(하드코딩 금지).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from saju_shared_types.constants import BRANCH_CLASHES
from saju_shared_types.enums import Branch
from saju_shared_types.event_engine import EventCandidateV2, EventKeyV2, LuckLayer
from saju_shared_types.luck import LuckPillar


@dataclass(frozen=True)
class TransitClashRule:
    """사전 `transit_clash_mobility_support` 1건."""

    rule_id: str
    events: frozenset[EventKeyV2]
    bonus: int
    reason_prefix: str


@dataclass(frozen=True)
class TransitClash:
    """서로 다른 운 층 사이의 지지 충 1건."""

    layer_a: LuckLayer
    branch_a: str
    layer_b: LuckLayer
    branch_b: str

    def code(self) -> str:
        return f"{self.layer_a.value}{self.branch_a}-{self.layer_b.value}{self.branch_b}"


@lru_cache(maxsize=4)
def load_transit_clash_rule(dictionaries_dir: Path) -> TransitClashRule | None:
    """사전 절 `transit_clash_mobility_support`를 읽는다(없으면 None — 기존 동작)."""
    path = dictionaries_dir / "event_engine" / "transit_ten_god_branching.json"
    raw = json.loads(path.read_text(encoding="utf-8")).get("transit_clash_mobility_support")
    if not raw:
        return None
    return TransitClashRule(
        rule_id=str(raw.get("id", "TRANSIT_CLASH_MOBILITY_SUPPORT")),
        events=frozenset(EventKeyV2(e) for e in raw.get("events", [])),
        bonus=int(raw.get("bonus", 0)),
        reason_prefix=str(raw.get("reason_prefix", "TRANSIT_CLASH")),
    )


def transit_clashes(stack: Sequence[tuple[LuckLayer, LuckPillar]]) -> list[TransitClash]:
    """거버닝 스택에서 서로 다른 층 사이의 지지 충을 (층 순서대로) 모은다."""
    out: list[TransitClash] = []
    for i, (la, pa) in enumerate(stack):
        for lb, pb in stack[i + 1:]:
            if la is lb or not pa.branch or not pb.branch:
                continue
            try:
                pair = frozenset({Branch(pa.branch), Branch(pb.branch)})
            except ValueError:
                continue
            if pair in BRANCH_CLASHES:
                out.append(TransitClash(la, pa.branch, lb, pb.branch))
    return out


def apply_transit_clash_support(
    candidates: list[EventCandidateV2],
    clashes: Sequence[TransitClash],
    rule: TransitClashRule,
) -> list[EventCandidateV2]:
    """이동형 후보에 운↔운 충 보조 가산을 한 번만 더한다(충 없음·대상 아님이면 불변)."""
    if not clashes or rule.bonus <= 0:
        return candidates
    code = rule.reason_prefix + "_" + "+".join(c.code() for c in clashes)
    out: list[EventCandidateV2] = []
    for c in candidates:
        if c.event_key not in rule.events or any(
            r.startswith(rule.reason_prefix) for r in c.reason_codes
        ):
            out.append(c)
            continue
        out.append(c.model_copy(update={
            "score": c.score + rule.bonus,
            "reason_codes": [*c.reason_codes, code],
            "contributions": {**c.contributions, "transit_clash": float(rule.bonus)},
        }))
    return out
