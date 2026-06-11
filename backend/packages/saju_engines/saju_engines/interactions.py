"""상호작용 탐지기 (v2.2 Phase 2.5 T2.5.1·T2.5.2, docs/09 2장 — 전체 규격).

탐지 대상 소스 = { 원국(4주), 대운, 세운, 월운, 일운 }. 모든 소스의 글자를 풀(pool)로
모아 docs/09 2장 목록 **전부**를 검사한다: 천간합5/천간충4 · 육합6 · 삼합4(반합+왕지
플래그) · 방합4(반합) · 충6 · 형(삼형2+부분형, 상형 子卯, 자형 辰午酉亥) · 파6 · 해6 ·
원진6 · 암합(기본 비활성 — relations.json enabled 플래그로만 활성화).

레벨 조합 P01~P11은 호출 측(LuckComposite 계산기)이 풀 구성과 소스 필터로 결정한다.
다자(삼합/방합/삼형)는 **소스 혼합 성립을 허용**하고 참여 소스를 기록한다(누락 금지).

관계의 참여 글자·기본 가중치는 relations.json(사전)을 단일 소스로 사용한다 — Phase 1
테스트가 사전과 만세력 엔진 상수의 일치를 고정하므로 엔진과 모순되지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

from saju_shared_types.constants import THREE_HARMONY
from saju_shared_types.precompute import (
    InteractionHit,
    InteractionKind,
    InteractionParticipant,
    InteractionSource,
)

from .dictionaries import RelationItem, RelationsFile

# relations.json type → InteractionHit.kind (docs/09 3장 12종).
_TYPE_TO_KIND: dict[str, InteractionKind] = {
    "stem_combination": InteractionKind.STEM_COMBINE,
    "stem_clash": InteractionKind.STEM_CLASH,
    "six_combination": InteractionKind.BRANCH_SIX_COMBINE,
    "three_harmony": InteractionKind.BRANCH_THREE_COMBINE,
    "directional": InteractionKind.BRANCH_DIRECTIONAL,
    "branch_clash": InteractionKind.BRANCH_CLASH,
    "punishment_triple": InteractionKind.BRANCH_PUNISH,
    "punishment_mutual": InteractionKind.BRANCH_PUNISH,
    "self_punishment": InteractionKind.SELF_PUNISH,
    "branch_break": InteractionKind.BRANCH_BREAK,
    "harm": InteractionKind.BRANCH_HARM,
    "wonjin": InteractionKind.WONJIN,
}

# 삼합 왕지(子午卯酉) — 반합의 왕지 포함 플래그용 (엔진 상수 THREE_HARMONY의 royal).
_ROYAL_BY_GROUP: dict[frozenset[str], str] = {
    frozenset(str(m) for m in members): str(royal)
    for members, _el, royal in THREE_HARMONY
}


class PoolEntry:
    """탐지 풀의 한 자리 — 소스(원국 자리/운 레벨)와 그 간지."""

    def __init__(self, source: InteractionSource, stem: str | None, branch: str | None):
        """stem/branch는 한자 1글자(없으면 None — 시주 미상 등)."""
        self.source = source
        self.stem = stem
        self.branch = branch


class InteractionDetector:
    """relations.json 기반 전수 상호작용 탐지기 (결정론)."""

    def __init__(self, relations_path: Path) -> None:
        """사전을 로드해 쌍/3자 관계 인덱스를 만든다. enabled=false 항목은 제외."""
        parsed = RelationsFile.model_validate(
            json.loads(relations_path.read_text(encoding="utf-8"))
        )
        self._pairs: dict[tuple[str, frozenset[str]], RelationItem] = {}
        self._triples: list[RelationItem] = []
        self._selfs: dict[str, RelationItem] = {}
        for item in parsed.items:
            if not item.enabled:
                continue  # 암합 등 — 기본 비활성, 사전 플래그로만 활성화
            if item.type in ("three_harmony", "directional", "punishment_triple"):
                self._triples.append(item)
            elif item.type == "self_punishment":
                self._selfs[item.participants[0]] = item
            elif item.participants:
                self._pairs[(item.type, frozenset(item.participants))] = item

    # ── 공개 API ─────────────────────────────────────────────────

    def detect(self, pool: list[PoolEntry]) -> list[InteractionHit]:
        """풀 전체에서 2장 목록의 상호작용을 모두 탐지한다.

        Args:
            pool: 소스별 간지 자리 목록(원국 4주 + 평가 중인 운 레벨들).

        Returns:
            탐지된 InteractionHit 목록(쌍 → 다자 → 자형 순).
        """
        return [
            *self._detect_pairs(pool),
            *self._detect_triples(pool),
            *self._detect_self_punishment(pool),
        ]

    # ── 쌍 관계 (천간합/충 · 육합 · 충 · 상형 · 파 · 해 · 원진) ──

    def _detect_pairs(self, pool: list[PoolEntry]) -> list[InteractionHit]:
        hits: list[InteractionHit] = []
        for i, a in enumerate(pool):
            for b in pool[i + 1:]:
                hits.extend(self._pair_hits(a, b, stems=True))
                hits.extend(self._pair_hits(a, b, stems=False))
        return hits

    def _pair_hits(self, a: PoolEntry, b: PoolEntry, *, stems: bool) -> list[InteractionHit]:
        ca = a.stem if stems else a.branch
        cb = b.stem if stems else b.branch
        if ca is None or cb is None or ca == cb:
            return []
        out: list[InteractionHit] = []
        for (_typ, members), item in self._pairs.items():
            if members != frozenset({ca, cb}):
                continue
            if stems != (item.type in ("stem_combination", "stem_clash")):
                continue
            out.append(InteractionHit(
                relation_id=item.id,
                kind=_TYPE_TO_KIND[item.type],
                participants=[
                    InteractionParticipant(source=a.source, ganji=ca),
                    InteractionParticipant(source=b.source, ganji=cb),
                ],
                mode_candidates=item.possible_modes,
                base_weight=item.base_score,
            ))
        return out

    # ── 다자 관계 (삼합 · 방합 · 삼형 — 소스 혼합 허용 + 반합/부분형) ──

    def _detect_triples(self, pool: list[PoolEntry]) -> list[InteractionHit]:
        hits: list[InteractionHit] = []
        for item in self._triples:
            members = set(item.participants)
            present: dict[str, list[InteractionSource]] = {
                ch: [e.source for e in pool if e.branch == ch] for ch in members
            }
            found = [ch for ch in item.participants if present[ch]]
            if len(found) < 2:
                continue
            participants = [
                InteractionParticipant(source=src, ganji=ch)
                for ch in found
                for src in present[ch]
            ]
            partial = len(found) < len(members)
            royal: bool | None = None
            if item.type == "three_harmony" and partial:
                royal_char = _ROYAL_BY_GROUP.get(frozenset(members))
                royal = royal_char in found if royal_char else None
            hits.append(InteractionHit(
                relation_id=item.id,
                kind=_TYPE_TO_KIND[item.type],
                participants=participants,
                partial=partial,
                royal_included=royal,
                mode_candidates=item.possible_modes,
                base_weight=item.base_score,
            ))
        return hits

    # ── 자형 (같은 글자 2자리 이상) ──

    def _detect_self_punishment(self, pool: list[PoolEntry]) -> list[InteractionHit]:
        hits: list[InteractionHit] = []
        for ch, item in self._selfs.items():
            spots = [e for e in pool if e.branch == ch]
            if len(spots) < 2:
                continue
            hits.append(InteractionHit(
                relation_id=item.id,
                kind=InteractionKind.SELF_PUNISH,
                participants=[
                    InteractionParticipant(source=e.source, ganji=ch) for e in spots
                ],
                mode_candidates=item.possible_modes,
                base_weight=item.base_score,
            ))
        return hits


# ── 구조 플래그 (docs/09 2-3) ────────────────────────────────────


def structure_flags(
    luck_stem: str,
    luck_branch: str,
    natal_pillars: list[tuple[str, str]],
    void_branches: list[str],
    stem_clash_pairs: set[frozenset[str]],
    branch_clash_pairs: set[frozenset[str]],
    six_combine_pairs: set[frozenset[str]],
) -> list[str]:
    """운 간지 1개의 구조 플래그: 공망활성(전실/충발/합해소) · 복음 · 반음.

    병존·간여지동은 원국 내부 구조라 natal 레코드에서 별도 산출한다.
    신살 활성은 만세력 엔진 산출(luck_sinsal)을 그대로 사용한다(재정의 금지).
    """
    flags: list[str] = []
    for vb in void_branches:
        if luck_branch == vb:
            flags.append(f"공망전실:{vb}")
        elif frozenset({luck_branch, vb}) in branch_clash_pairs:
            flags.append(f"공망발동(충):{luck_branch}-{vb}")
        elif frozenset({luck_branch, vb}) in six_combine_pairs:
            flags.append(f"공망해소(합):{luck_branch}-{vb}")
    for stem, branch in natal_pillars:
        if luck_stem == stem and luck_branch == branch:
            flags.append(f"복음:{stem}{branch}")
        elif (
            frozenset({luck_stem, stem}) in stem_clash_pairs
            and frozenset({luck_branch, branch}) in branch_clash_pairs
        ):
            flags.append(f"반음:{stem}{branch}")
    return flags


def natal_structure_flags(natal_pillars: list[tuple[str, str]]) -> list[str]:
    """원국 내부 구조 플래그: 병존(인접 동일 간지) · 간여지동은 신살/구조분석 결과 활용.

    병존은 인접(년-월/월-일/일-시) 기둥의 간지가 동일할 때 성립으로 본다.
    """
    flags: list[str] = []
    for (s1, b1), (s2, b2) in zip(natal_pillars, natal_pillars[1:], strict=False):
        if s1 == s2 and b1 == b2:
            flags.append(f"병존:{s1}{b1}")
    return flags


def clash_pair_sets(relations_path: Path) -> tuple[
    set[frozenset[str]], set[frozenset[str]], set[frozenset[str]]
]:
    """structure_flags용 (천간충, 지지충, 육합) 글자쌍 집합을 사전에서 구성한다."""
    parsed = RelationsFile.model_validate(
        json.loads(relations_path.read_text(encoding="utf-8"))
    )
    stem_clash: set[frozenset[str]] = set()
    branch_clash: set[frozenset[str]] = set()
    six: set[frozenset[str]] = set()
    for item in parsed.items:
        pair = frozenset(item.participants)
        if item.type == "stem_clash":
            stem_clash.add(pair)
        elif item.type == "branch_clash":
            branch_clash.add(pair)
        elif item.type == "six_combination":
            six.add(pair)
    return stem_clash, branch_clash, six


def natal_pool(pillars_pairs: list[tuple[InteractionSource, str, str]]) -> list[PoolEntry]:
    """(source, stem, branch) 튜플 목록 → PoolEntry 목록 헬퍼."""
    return [PoolEntry(src, stem, branch) for src, stem, branch in pillars_pairs]
