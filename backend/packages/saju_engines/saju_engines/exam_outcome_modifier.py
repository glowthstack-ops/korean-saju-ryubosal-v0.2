"""ExamOutcomeModifier (Phase 6b) — 시험·합격·취업의 결과 길흉을 십성 구조로 보정한다.

career_mobility 자료 9-3·9-4의 합격/불합격 십성 패턴(관인상생·상관견관·비겁쟁재·도식 등)을
favorability 채널(contributions['fav_adj'])에만 가감한다. 사건 종류·표시 점수(activation)는
바꾸지 않는다 — "합격 신호가 떠도 결과는 별개"(자료 0·16장, 절대원칙 3·4). 그 시점 운 십성
(transit present_gods)에 패턴의 십성 쌍이 모두 있으면 적용하며, 누적 보정은 fav_adj_cap으로 제한.

favorability 최종값은 통합 엔진의 _apply_soft_cap이 극성 기준값 + fav_adj로 확정한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from saju_shared_types.event_engine import (
    EventCandidateV2,
    EventKeyV2,
    TenGod,
)


class _Pattern(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    ten_gods: list[TenGod]
    fav_delta: float


class _ExamOutcomeFile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    target_events: list[EventKeyV2]
    fav_adj_cap: float = 0.5
    pass_patterns: list[_Pattern] = []
    fail_patterns: list[_Pattern] = []


@dataclass
class _Rule:
    """패턴 1건 — 십성 집합(부분집합 매칭)과 favorability 가감."""

    id: str
    gods: frozenset[TenGod]
    fav_delta: float


class ExamOutcomeModifier:
    """시험·합격 결과 길흉(favorability)을 십성 구조 패턴으로 보정한다."""

    def __init__(self, dictionaries_dir: Path) -> None:
        """event_engine/exam_outcome_patterns.json을 로드해 룰을 인덱싱한다."""
        path = dictionaries_dir / "event_engine" / "exam_outcome_patterns.json"
        data = _ExamOutcomeFile.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
        self._targets: set[EventKeyV2] = set(data.target_events)
        self._cap: float = abs(data.fav_adj_cap)
        self._rules: list[_Rule] = [
            _Rule(p.id, frozenset(p.ten_gods), p.fav_delta)
            for p in (*data.pass_patterns, *data.fail_patterns)
        ]

    def apply(
        self, candidates: list[EventCandidateV2], present_gods: set[TenGod]
    ) -> list[EventCandidateV2]:
        """대상 이벤트(시험·합격·취업) 후보에 합·불 패턴의 favorability 보정을 누적한다."""
        out: list[EventCandidateV2] = []
        for c in candidates:
            if c.event_key not in self._targets:
                out.append(c)
                continue
            delta = 0.0
            reasons = [*c.reason_codes]
            for rule in self._rules:
                if rule.gods <= present_gods:
                    delta += rule.fav_delta
                    reasons.append(rule.id)
            if delta == 0.0:
                out.append(c)
                continue
            # 누적 보정을 cap으로 제한(폭주 방지). 기존 fav_adj가 있으면 합산.
            prev = c.contributions.get("fav_adj", 0.0)
            fav_adj = max(-self._cap, min(self._cap, prev + delta))
            out.append(c.model_copy(update={
                "reason_codes": reasons,
                "contributions": {**c.contributions, "fav_adj": fav_adj},
            }))
        return out
