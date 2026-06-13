"""EventRanker (Phase 6) — 증거 등급으로 confidence_level을 산출하고 충돌을 해결한다.

evidence_grading.json(증거 7종 × 5등급 + no_event_suppression)으로 사건화 강도(level_1 theme_only ~
level_5 high_probability)를 매기고, conflict_resolver_duration.json(priority_rules)로 같은 신호가
여러 이벤트로 튈 때 대표 이벤트를 정한다. 점수·confidence_level만 조정하고 타입은 만들지 않는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from saju_shared_types.event_engine import (
    ConfidenceLevel,
    EventCandidateV2,
    LuckLayer,
    PolarityRole,
)

# 증거 등급 confidence_level 문자열 → enum.
_CL: dict[str, ConfidenceLevel] = {c.value: c for c in ConfidenceLevel}
_CL_ORDER = [
    ConfidenceLevel.THEME_ONLY,
    ConfidenceLevel.WEAK_EVENT_CANDIDATE,
    ConfidenceLevel.EVENT_CANDIDATE,
    ConfidenceLevel.STRONG_EVENT_CANDIDATE,
    ConfidenceLevel.HIGH_PROBABILITY_EVENT,
]


@dataclass
class RankContext:
    """충돌 해결용 컨텍스트 플래그(통합 계층이 채움 — 비면 충돌 규칙 미적용)."""

    flags: set[str] = field(default_factory=set)
    close_score_threshold: int = 6  # 근접 점수 묶음 판정 폭


class EventRanker:
    """증거 등급·억제·충돌 해결로 최종 랭킹과 confidence_level을 확정한다."""

    def __init__(self, dictionaries_dir: Path) -> None:
        base = dictionaries_dir / "event_engine"
        grading = json.loads((base / "evidence_grading.json").read_text(encoding="utf-8"))
        # 등급 정의를 (confidence_level, 필요 신호 집합) 목록으로, 강→약 순으로 정렬.
        self._levels: list[tuple[ConfidenceLevel, frozenset[str]]] = []
        for v in grading["levels"].values():
            cl = _CL[v["confidence_level"]]
            self._levels.append((cl, frozenset(v["required"])))
        self._levels.sort(key=lambda t: _CL_ORDER.index(t[0]), reverse=True)
        conflict = json.loads(
            (base / "conflict_resolver_duration.json").read_text(encoding="utf-8")
        )
        self._priority: list[dict] = conflict["event_conflict_resolver"]["priority_rules"]

    def rank(
        self, candidates: list[EventCandidateV2], ctx: RankContext | None = None
    ) -> list[EventCandidateV2]:
        """충돌 해결 → 증거 등급 → 억제 순으로 적용하고 점수 내림차순으로 반환한다."""
        ctx = ctx or RankContext()
        work = self._resolve_conflicts(candidates, ctx)
        scored = [self._grade(c) for c in work]
        # 3개 이상 근접 점수로 분산되면 대표 확정하지 않고 묶음 플래그.
        scored = self._mark_diffuse(scored, ctx.close_score_threshold)
        return sorted(scored, key=lambda x: -x.score)

    # ── 충돌 해결 ────────────────────────────────────────────
    def _resolve_conflicts(
        self, candidates: list[EventCandidateV2], ctx: RankContext
    ) -> list[EventCandidateV2]:
        by_key = {str(c.event_key): c for c in candidates}
        boost: dict[str, int] = {}
        reason_add: dict[str, str] = {}
        for rule in self._priority:
            if not set(rule["if"]) <= ctx.flags:
                continue
            prefer = rule["prefer"]
            if prefer not in by_key:
                continue
            boost[prefer] = boost.get(prefer, 0) + 6
            reason_add[prefer] = f"CONFLICT_prefer_{prefer}"
            for over in rule["over"]:
                if over in by_key:
                    boost[over] = boost.get(over, 0) - 10
                    reason_add[over] = f"CONFLICT_over_{prefer}"
        if not boost:
            return list(candidates)
        out: list[EventCandidateV2] = []
        for c in candidates:
            k = str(c.event_key)
            if k not in boost:
                out.append(c)
                continue
            reasons = [*c.reason_codes, reason_add[k]]
            out.append(c.model_copy(update={
                "score": max(0, min(100, c.score + boost[k])),
                "reason_codes": reasons,
            }))
        return out

    # ── 증거 등급 + 억제 ─────────────────────────────────────
    def _grade(self, c: EventCandidateV2) -> EventCandidateV2:
        present = self._signals(c)
        level = ConfidenceLevel.THEME_ONLY
        for cl, required in self._levels:
            if required <= present:
                level = cl
                break
        reasons = [*c.reason_codes]
        score = c.score
        # no_event_suppression: 월/일운 신호만 있고 대운·세운 흐름 없음 → 일시 체감으로 강등.
        lset = set(c.source_layers)
        only_minor = lset and lset <= {LuckLayer.WOLWOON, LuckLayer.ILWOON}
        if only_minor and level not in (ConfidenceLevel.THEME_ONLY,):
            idx = max(0, _CL_ORDER.index(level) - 1)
            level = _CL_ORDER[idx]
            score = max(0, score - 6)
            reasons.append("SUPPRESS_minor_layer_only")
        return c.model_copy(update={
            "confidence_level": level,
            "score": score,
            "reason_codes": reasons,
        })

    @staticmethod
    def _signals(c: EventCandidateV2) -> frozenset[str]:
        """후보에 채워진 필드·근거코드로 증거 신호 7종의 존재 여부를 도출한다."""
        s = {"ten_god_signal"}  # 브랜처에서 나온 후보는 항상 십성 신호 보유.
        if c.twelve_stage is not None:
            s.add("life_stage_signal")
        if any(r.startswith("REL_") for r in c.reason_codes):
            s.add("relation_signal")
        if c.palace is not None:
            s.add("palace_signal")
        if len(set(c.source_layers)) >= 2:
            s.add("layer_signal")
        if c.polarity_role is not PolarityRole.NEUTRAL:
            s.add("yonggi_signal")
        if any(r.startswith("PROFILE_") for r in c.reason_codes):
            s.add("profile_signal")
        return frozenset(s)

    @staticmethod
    def _mark_diffuse(
        cands: list[EventCandidateV2], threshold: int
    ) -> list[EventCandidateV2]:
        """상위 3개 이상이 근접 점수면 대표 확정 보류 플래그를 단다."""
        if len(cands) < 3:
            return cands
        top = max(c.score for c in cands)
        close = [c for c in cands if top - c.score <= threshold]
        if len(close) < 3:
            return cands
        ids = {id(c) for c in close}
        return [
            c.model_copy(update={"reason_codes": [*c.reason_codes, "DIFFUSE_group"]})
            if id(c) in ids else c
            for c in cands
        ]
