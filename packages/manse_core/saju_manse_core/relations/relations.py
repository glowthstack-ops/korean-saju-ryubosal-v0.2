"""Detect 합충형파해·병존·간여지동 from the four pillars (pure pair detection).

This module only finds relations; semantic enrichment (palaces, severity, 합화
판정, stability, structure_modifier) lives in manse_analysis.structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from saju_shared_types.constants import (
    BRANCH_BREAKS,
    BRANCH_CLASHES,
    BRANCH_ELEMENT,
    BRANCH_HARMS,
    DIRECTIONAL_COMBINATIONS,
    PUNISHMENT_MUTUAL,
    PUNISHMENT_TRIPLES,
    SELF_PUNISHMENT,
    SIX_COMBINATIONS,
    STEM_COMBINATIONS,
    STEM_ELEMENT,
    THREE_HARMONY,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.pillars import FourPillarsResult

_ADJACENT = [("year", "month"), ("month", "day"), ("day", "hour")]


@dataclass
class Relation:
    rel_type: str
    scope: str  # stem | branch | pillar
    positions: list[str]
    members: list[str]
    transform_element: str | None = None
    notes: list[str] = field(default_factory=list)


def _branch_positions(pillars: FourPillarsResult) -> list[tuple[str, Branch]]:
    items = [("year", pillars.year), ("month", pillars.month), ("day", pillars.day)]
    if pillars.hour is not None:
        items.append(("hour", pillars.hour))
    return [(pos, Branch(p.branch)) for pos, p in items]


def _stem_positions(pillars: FourPillarsResult) -> list[tuple[str, Stem]]:
    items = [("year", pillars.year), ("month", pillars.month), ("day", pillars.day)]
    if pillars.hour is not None:
        items.append(("hour", pillars.hour))
    return [(pos, Stem(p.stem)) for pos, p in items]


def detect(pillars: FourPillarsResult) -> list[Relation]:
    rels: list[Relation] = []
    stems = _stem_positions(pillars)
    branches = _branch_positions(pillars)

    # 천간합
    for (pa, sa), (pb, sb) in combinations(stems, 2):
        target = STEM_COMBINATIONS.get(frozenset({sa, sb}))
        if target is not None and sa != sb:
            rels.append(
                Relation("stem_combination", "stem", [pa, pb], [str(sa), str(sb)], str(target))
            )

    present = {b for _, b in branches}

    # 삼합 / 반합
    for members, element, royal in THREE_HARMONY:
        have = members & present
        if members <= present:
            combo_pos = [p for p, b in branches if b in members]
            rels.append(
                Relation(
                    "three_harmony", "branch", combo_pos,
                    [str(b) for b in members], str(element),
                )
            )
        elif royal in present and len(have) == 2:
            combo_pos = [p for p, b in branches if b in have]
            rels.append(
                Relation(
                    "half_harmony", "branch", combo_pos,
                    [str(b) for b in have], str(element),
                )
            )

    # 방합
    for members, element in DIRECTIONAL_COMBINATIONS:
        if members <= present:
            combo_pos = [p for p, b in branches if b in members]
            rels.append(
                Relation(
                    "directional", "branch", combo_pos,
                    [str(b) for b in members], str(element),
                )
            )

    # 지지 페어 관계: 육합 / 충 / 파 / 해 / 상형
    for (pa, ba), (pb, bb) in combinations(branches, 2):
        key = frozenset({ba, bb})
        if ba == bb:
            continue
        if key in SIX_COMBINATIONS:
            rels.append(
                Relation("six_combination", "branch", [pa, pb], [str(ba), str(bb)],
                         str(SIX_COMBINATIONS[key]))
            )
        if key in BRANCH_CLASHES:
            rels.append(Relation("clash", "branch", [pa, pb], [str(ba), str(bb)]))
        if key in BRANCH_BREAKS:
            rels.append(Relation("break", "branch", [pa, pb], [str(ba), str(bb)]))
        if key in BRANCH_HARMS:
            rels.append(Relation("harm", "branch", [pa, pb], [str(ba), str(bb)]))
        if key in PUNISHMENT_MUTUAL:
            rels.append(Relation("punishment", "branch", [pa, pb], [str(ba), str(bb)],
                                 notes=["무례지형"]))

    # 삼형 (삼합처럼 셋 중 둘 이상이면 형 성립)
    for triple in PUNISHMENT_TRIPLES:
        members_present = [(p, b) for p, b in branches if b in triple]
        if len({b for _, b in members_present}) >= 2:
            rels.append(
                Relation(
                    "punishment", "branch", [p for p, _ in members_present],
                    [str(b) for _, b in members_present], notes=["삼형"],
                )
            )

    # 자형 (같은 지지 2개 이상이며 자형 지지)
    for b in SELF_PUNISHMENT:
        sp_positions = [p for p, bb in branches if bb == b]
        if len(sp_positions) >= 2:
            rels.append(
                Relation("self_punishment", "branch", sp_positions, [str(b)] * len(sp_positions))
            )

    # 병존 (인접 동일 천간/지지)
    bp = {p: b for p, b in branches}
    sp = {p: s for p, s in stems}
    for a, c in _ADJACENT:
        if a in sp and c in sp and sp[a] == sp[c]:
            rels.append(Relation("stem_duplication", "stem", [a, c], [str(sp[a])] * 2))
        if a in bp and c in bp and bp[a] == bp[c]:
            rels.append(Relation("branch_duplication", "branch", [a, c], [str(bp[a])] * 2))

    # 간여지동 (주 내 천간·지지 오행 동일)
    for pos, stem in stems:
        branch = bp.get(pos)
        if branch is not None and STEM_ELEMENT[stem] == BRANCH_ELEMENT[branch]:
            rels.append(
                Relation("gan_yeo_ji_dong", "pillar", [pos], [str(stem), str(branch)])
            )

    return rels
