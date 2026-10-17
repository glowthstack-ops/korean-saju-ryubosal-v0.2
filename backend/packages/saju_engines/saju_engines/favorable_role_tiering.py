"""용신 배율 품질군 차등 + 십성별 유익형 후보 (2026-10-15 데굴님 승인).

배경: `YongiQualityEngine`은 같은 극성(용신·희신·강한 용신)의 **모든** 후보에 배율을 곱했다. 그래서
상관 용신에 상관 운이 오면 충돌·이탈(career_change 41)이, 편관 용신이면 압박, 편인 용신이면 보류가
용신이라는 이유로 더 강해지고, 발표·취업·입학 같은 유익형 후보는 뒤에 남았다(2026-10-15 검수).

규칙(사전 `event_engine/transit_ten_god_branching.json` → `favorable_role_tiering`):
  - 용신 역할일 때 **유입 십성별 유익형 사건 목록**에 든 후보에만 모드별 배율(a=1.10 / b=1.20)을
    곱하고, 그 외(불리·혼합형) 후보는 1.00이다. 기존 `polarity_rules` 배율은 이 모드에서 쓰지 않는다
    (한 곳에서만 곱한다 — 중복 곱 금지). 기신 쪽(quality_flip)은 손대지 않는다.
  - 기존 단일 운 규칙에 없는 유익형(편관→promotion, 편인→creative_output)은 `extra_base_events`로
    모드가 켜졌을 때만 브랜처 기본 후보에 더한다(OFF면 기존 결과 불변).
  - 용신이라는 이유만으로 취업·승진·입학을 자동 우선하지 않는다 — 기본점과 관계 근거가 그대로라
    유익형이 흉형 기본점(41)을 넘지 못하면 뒤에 남는 것이 맞다.
값은 명리의 확정 수치가 아니라 초기 설계값이며 85사례 재생(off/a/b)으로 비교해 정한다. 플래그
`SAJU_YONG_TIERED_MULTIPLIER_MODE`(off 기본). 규칙 기반이며 LLM 판정을 쓰지 않는다(절대원칙 1).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from saju_shared_types.event_engine import EventKeyV2, PolarityRole, TenGod

TIER_MODES: tuple[str, ...] = ("off", "a", "b")


@dataclass(frozen=True)
class ExtraBaseEvent:
    """모드가 켜졌을 때만 브랜처 단일 운 규칙에 더하는 유익형 기본 후보 1건."""

    incoming: TenGod
    event: EventKeyV2
    score: int
    reason: str


@dataclass(frozen=True)
class FavorableTieringRule:
    """사전 `favorable_role_tiering` 1건."""

    rule_id: str
    roles: frozenset[PolarityRole]
    modes: dict[str, float]
    favorable: dict[TenGod, frozenset[EventKeyV2]]
    extra_base_events: tuple[ExtraBaseEvent, ...]
    reason_prefix: str
    #: 근거 코드로 유익형을 인정하는 접두사(2026-10-15 데굴님 확정 — 비겁 용신 이동 시드: 이동 뒤
    #: 흐름이 좋은 쪽이라 유익형. 사건 키(career_change)로는 흉형과 구분이 안 돼 근거로 본다).
    favorable_reason_prefixes: tuple[str, ...] = ()

    def is_favorable(
        self,
        source_ten_gods: Iterable[TenGod],
        event_key: EventKeyV2,
        reason_codes: Iterable[str] = (),
    ) -> bool:
        """유입 십성 중 하나라도 이 사건을 유익형으로 두거나, 유익형 근거 코드가 있으면 유익형."""
        if any(event_key in self.favorable.get(g, frozenset()) for g in source_ten_gods):
            return True
        return any(
            r.startswith(self.favorable_reason_prefixes) for r in reason_codes
        ) if self.favorable_reason_prefixes else False

    def multiplier(self, mode: str) -> float:
        """모드별 유익형 배율(모드가 사전에 없으면 1.0 — 안전 기본)."""
        return float(self.modes.get(mode, 1.0))


@lru_cache(maxsize=4)
def load_favorable_tiering(dictionaries_dir: Path) -> FavorableTieringRule | None:
    """사전 절 `favorable_role_tiering`을 읽는다(없으면 None — 기존 동작)."""
    path = dictionaries_dir / "event_engine" / "transit_ten_god_branching.json"
    raw = json.loads(path.read_text(encoding="utf-8")).get("favorable_role_tiering")
    if not raw:
        return None
    return FavorableTieringRule(
        rule_id=str(raw.get("id", "YONG_TIERED_MULTIPLIER")),
        roles=frozenset(PolarityRole(r) for r in raw.get("roles", ["YONG", "HEE", "YONG_STRONG"])),
        modes={str(k): float(v) for k, v in raw.get("modes", {}).items()},
        favorable={
            TenGod(g): frozenset(EventKeyV2(e) for e in events)
            for g, events in raw.get("favorable_events_by_ten_god", {}).items()
        },
        extra_base_events=tuple(
            ExtraBaseEvent(
                incoming=TenGod(e["incoming"]),
                event=EventKeyV2(e["event"]),
                score=int(e["score"]),
                reason=str(e.get("reason", "")),
            )
            for e in raw.get("extra_base_events", [])
        ),
        reason_prefix=str(raw.get("reason_prefix", "YONG_TIER")),
        favorable_reason_prefixes=tuple(str(x) for x in raw.get("favorable_reason_prefixes", [])),
    )
