"""역할별 사건 전환 시드 — 사흉신 용신 운·사길신 기신 운 (2026-10-16 데굴님 확정 6규칙).

배경: 사건 **종류**는 십성 단일 운 규칙(`single_transit_rules`)이 정하고 용·기신은 배율·품질만
바꾼다(2026-06-16 분리 원칙). 그래서 상관·편관·편인이 **용신**인 명식에 그 십성 운이 들어와도
흉성 기본 가지(충돌·이탈 / 압박 / 보류)에 용신 배율만 붙어 "용신이라 더 강한 흉사"가 되고,
정관·정인·식신이 **기신**인 명식에 그 운이 들어와도 길성 기본 가지(취업 / 문서 / 성과)에 압박
품질만 붙어 사건 종류가 현실과 어긋난다.

방식(데굴님 승인 — 비겁 이동 시드와 같은 패턴):
  - 브랜처의 기본 가지는 바꾸지 않는다(브랜처는 오행 favorability 를 모르는 채 유지).
  - 브랜처 직후 합류 자리에서 역할별 사건 후보를 시드로 더해 **순위로** 전환한다. 뒤 6계층
    보정(길흉·충합·궁위·12운성·대운 교체)은 그대로 적용된다.
  - 유입 강도 4단계(간여지동 > 같은 군 > 천간만 > 지지만)·기준점은 비겁 시드와 같은 값이고
    둘째 사건은 `secondary_ratio` 를 곱한다.
  - 규칙·사건·점수는 전부 사전 `event_engine/transit_ten_god_branching.json` →
    `role_event_seed_rules` 에서 읽는다(하드코딩 금지). 규칙별 `enabled` 로 개별 측정이 가능하다.
점수 규칙이므로 운영 ON/OFF 는 85사례 재생 적중률·실사례로 정한다(플래그
`SAJU_ROLE_EVENT_SEED_ENABLED`, 기본 OFF). 규칙 기반이며 LLM 판정을 쓰지 않는다(절대원칙 1).
"""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from saju_shared_types.constants import STEM_ELEMENT, group_elements
from saju_shared_types.enums import Stem
from saju_shared_types.event_engine import (
    TEN_GOD_GROUP,
    ConfidenceLevel,
    EventCandidateV2,
    EventKeyV2,
    LuckLayer,
    PolarityRole,
    TenGod,
    TenGodGroup,
)
from saju_shared_types.manse_result import ManseV2Result

from .peer_mobility_seed import classify_inflow
from .ten_god_brancher import TransitSignal

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
SECTION = "role_event_seed_rules"
# 십성군(TenGodGroup) → `group_elements` 키. authority 만 이름이 다르다.
_GROUP_TO_ELEMENT_KEY: dict[TenGodGroup, str] = {
    TenGodGroup.PEER: "peer",
    TenGodGroup.OUTPUT: "output",
    TenGodGroup.WEALTH: "wealth",
    TenGodGroup.AUTHORITY: "officer",
    TenGodGroup.RESOURCE: "resource",
}


@dataclass(frozen=True)
class RoleEventRule:
    """`role_event_seed_rules.rules[]` 1건 — 유입 십성 × 역할 → 사건 후보."""

    rule_id: str
    incoming: TenGod
    favorability_any: frozenset[str]
    events: tuple[EventKeyV2, ...]
    enabled: bool


@dataclass(frozen=True)
class RoleEventSeedConfig:
    """`role_event_seed_rules` 절 전체(공통 기준점 + 규칙 목록)."""

    layers: frozenset[LuckLayer]
    base_by_inflow: dict[str, int]
    secondary_ratio: float
    inflow_reason_codes: dict[str, str]
    upper_support_prefix: str
    rules: tuple[RoleEventRule, ...]
    event_candidate_threshold: int
    theme_only_threshold: int


@lru_cache(maxsize=8)
def load_role_event_seed_config(
    dictionaries_dir: Path = _DICTS_DEFAULT,
) -> RoleEventSeedConfig | None:
    """브랜처 사전의 `role_event_seed_rules` 절을 읽는다(절이 없으면 None — 시드 비활성)."""
    path = dictionaries_dir / "event_engine" / "transit_ten_god_branching.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get(SECTION)
    if not raw:
        return None
    thresholds = data.get("activation_thresholds", {})
    rules = tuple(
        RoleEventRule(
            rule_id=str(r["id"]),
            incoming=TenGod(r["incoming"]),
            favorability_any=frozenset(r.get("favorability_any", ["용신"])),
            events=tuple(EventKeyV2(e) for e in r["events"]),
            enabled=bool(r.get("enabled", True)),
        )
        for r in raw.get("rules", [])
    )
    return RoleEventSeedConfig(
        layers=frozenset(LuckLayer(x) for x in raw.get("layers", ["sewoon", "wolwoon"])),
        base_by_inflow={k: int(v) for k, v in raw["base_by_inflow"].items()},
        secondary_ratio=float(raw.get("secondary_ratio", 0.85)),
        inflow_reason_codes=dict(raw.get("inflow_reason_codes", {})),
        upper_support_prefix=str(raw.get("upper_support_prefix", "ROLE_UPPER_SUPPORT_")),
        rules=rules,
        event_candidate_threshold=int(thresholds.get("event_candidate", 55)),
        theme_only_threshold=int(thresholds.get("theme_only", 35)),
    )


def incoming_element(day_master: Stem, incoming: TenGod) -> str:
    """유입 십성의 오행(한자) — 일간 기준 십성군 → 오행."""
    group = TEN_GOD_GROUP[incoming]
    return str(group_elements(STEM_ELEMENT[day_master])[_GROUP_TO_ELEMENT_KEY[group]])


def _confidence(score: int, cfg: RoleEventSeedConfig) -> ConfidenceLevel:
    if score >= cfg.event_candidate_threshold:
        return ConfidenceLevel.EVENT_CANDIDATE
    if score >= cfg.theme_only_threshold + 10:
        return ConfidenceLevel.WEAK_EVENT_CANDIDATE
    return ConfidenceLevel.THEME_ONLY


def produce_role_event_seeds(
    signals: list[TransitSignal],
    target_layer: LuckLayer,
    result: ManseV2Result,
    fav_map: dict[str, str],
    period: str,
    cfg: RoleEventSeedConfig | None,
    rule_ids: Collection[str] | None = None,
) -> list[EventCandidateV2]:
    """역할별 사건 전환 시드 — 규칙마다 0 또는 사건 수만큼의 후보.

    Args:
        signals: 거버닝 스택에서 수집한 운 십성 신호 전체(층위 포함).
        target_layer: 이번 채점 대상 층 — 절의 layers 에 들어야 한다.
        result: 만세 결과(일간으로 유입 십성의 오행을 정한다).
        fav_map: 오행(한자) → 용기신 역할.
        period: 시점 라벨.
        cfg: 사전 절(None 이면 빈 목록).
        rule_ids: 측정용 — 지정하면 그 규칙 id 만 적용(None=사전 enabled 전부).
    """
    if cfg is None or target_layer not in cfg.layers or result.pillars is None:
        return []
    dm = Stem(result.pillars.day.stem)
    out: list[EventCandidateV2] = []
    stack_layers = sorted({s.layer for s in signals}, key=lambda x: list(LuckLayer).index(x))
    for rule in cfg.rules:
        if rule_ids is not None:
            if rule.rule_id not in rule_ids:
                continue
        elif not rule.enabled:
            continue
        if fav_map.get(incoming_element(dm, rule.incoming)) not in rule.favorability_any:
            continue
        target_signals = [
            s for s in signals if s.layer is target_layer and s.ten_god is rule.incoming
        ]
        inflow = classify_inflow(target_signals)
        if inflow is None:
            continue
        base = cfg.base_by_inflow.get(inflow, 0)
        if base <= 0:
            continue
        reasons = [rule.rule_id]
        code = cfg.inflow_reason_codes.get(inflow)
        if code:
            reasons.append(code)
        # 상위 층(대운·세운)에도 같은 십성이 있으면 근거 층에 적는다(비겁 시드와 같은 운 위계
        # 관례 — 상위 뿌리가 있는 월운 유입은 '월운 단독 체감'이 아니다).
        upper_layers = sorted(
            {
                s.layer for s in signals
                if s.layer is not target_layer and s.ten_god is rule.incoming
            },
            key=lambda x: list(LuckLayer).index(x),
        )
        for layer in upper_layers:
            reasons.append(f"{cfg.upper_support_prefix}{layer.value}")
        # 극성 자리표시 — 뒤 계층 `_period_role` 이 시점 유입 오행의 역할로 덮어쓴다.
        seed_role = PolarityRole.GI if "기신" in rule.favorability_any else PolarityRole.YONG
        for idx, event in enumerate(rule.events):
            score = base if idx == 0 else int(round(base * cfg.secondary_ratio))
            if score <= 0:
                continue
            out.append(EventCandidateV2(
                event_key=event,
                period=period,
                score=score,
                confidence_level=_confidence(score, cfg),
                polarity_role=seed_role,
                source_layers=stack_layers or [target_layer],
                candidate_source_layers=[
                    layer.value for layer in (*upper_layers, target_layer)
                ],
                source_ten_gods=[rule.incoming],
                reason_codes=list(reasons),
                # 단독 시드는 이 점수가 곧 base — 기여 합 ≈ raw_score 불변식 유지.
                contributions={"base": float(score)},
            ))
    return out


def merge_role_event_seeds(
    cands: list[EventCandidateV2], seeds: list[EventCandidateV2]
) -> list[EventCandidateV2]:
    """브랜처(또는 앞선 시드)가 이미 같은 사건을 냈으면 점수 최댓값·근거 합집합.

    비겁 시드 병합(`merge_peer_mobility_seeds`)과 같은 규칙이되 기여 키는 `role_event_seed` 로
    따로 남긴다 — 같은 후보에 비겁 시드 기여가 이미 있어도 덮어쓰지 않는다.
    """
    if not seeds:
        return cands
    out = list(cands)
    for seed in seeds:
        existing = next((c for c in out if c.event_key is seed.event_key), None)
        if existing is None:
            out.append(seed)
            continue
        delta = max(0, seed.score - existing.score)  # 기여 합 ≈ raw_score 불변식
        existing.score += delta
        if delta > 0 and existing.confidence_level is ConfidenceLevel.THEME_ONLY:
            existing.confidence_level = seed.confidence_level
        for code in seed.reason_codes:
            if code not in existing.reason_codes:
                existing.reason_codes.append(code)
        for tg in seed.source_ten_gods:
            if tg not in existing.source_ten_gods:
                existing.source_ten_gods.append(tg)
        for layer in seed.candidate_source_layers:
            if layer not in existing.candidate_source_layers:
                existing.candidate_source_layers.append(layer)
        existing.contributions["role_event_seed"] = (
            existing.contributions.get("role_event_seed", 0.0) + float(delta)
        )
    return out


__all__ = [
    "SECTION", "RoleEventRule", "RoleEventSeedConfig", "incoming_element",
    "load_role_event_seed_config", "merge_role_event_seeds", "produce_role_event_seeds",
]
