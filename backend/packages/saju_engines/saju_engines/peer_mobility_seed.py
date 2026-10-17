"""비겁 용신 × 비겁 운 유입 → 직장·역할 이동(career_change) 시드 (2026-10-14 데굴님 확정 규칙).

실사례: 1980-11-22 09:40 서울 남(용신 土=비겁)의 2026-10 戊戌월 — 천간·지지 모두 겁재(운 간여지동)에
권고사직. 기존 브랜처는 겁재 단독을 재물 분탈·분쟁·무리한 독립으로만 가지를 쳐 career_change 후보가
없었고, 그 달을 "강한 용신운 · 재물 변화 우세"로 읽었다.

규칙(사전 `event_engine/transit_ten_god_branching.json` → `peer_yongsin_mobility_rules`):
  - 비겁(비견·겁재)이 용신인 명식에 채점 대상 층(세운·월운)으로 비겁이 들어오면 career_change 후보를
    만든다. 이동은 자의(독립·이직)·타의(권고사직·배치 전환) 양방이라 polarity 는 조건부다.
  - 간여지동(천간·지지 같은 십성)은 그 기운이 **강하게** 들어온 경우 — 기준점이 가장 높다.
  - 약하게(한쪽으로만) 들어와도 관성과의 충 등 다른 작용으로 풀이가 바뀔 수 있으므로 후보는 항상
    만들고 유입 강도만 나눈다. 길흉·충합·궁성·12운성 보정은 뒤 6계층이 그대로 적용된다
    (브랜처 직후 합류 — MT1 awareness seed 와 같은 자리).
규칙 기반이며 LLM 판정을 쓰지 않는다(절대원칙 1). 점수 상수는 사전에서 읽는다(하드코딩 금지).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from saju_shared_types.constants import STEM_ELEMENT
from saju_shared_types.enums import Stem
from saju_shared_types.event_engine import (
    TEN_GOD_GROUP,
    ConfidenceLevel,
    EventCandidateV2,
    EventKeyV2,
    LuckLayer,
    PolarityRole,
    TenGodGroup,
)
from saju_shared_types.manse_result import ManseV2Result

from .ten_god_brancher import TransitSignal

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
_INFLOW_ORDER = ("same_god", "same_group", "stem_only", "branch_only")


@dataclass(frozen=True)
class PeerMobilityRule:
    """사전 `peer_yongsin_mobility_rules` 1건."""

    rule_id: str
    incoming_groups: frozenset[str]
    favorability_any: frozenset[str]
    layers: frozenset[LuckLayer]
    event: EventKeyV2
    base_by_inflow: dict[str, int]
    inflow_reason_codes: dict[str, str]
    event_candidate_threshold: int
    theme_only_threshold: int


YONGSIN_SECTION = "peer_yongsin_mobility_rules"
GISIN_SECTION = "peer_gisin_mobility_rules"  # 기신 대칭 시드(2026-10-15 데굴님 확정)


@lru_cache(maxsize=8)
def load_peer_mobility_rule(
    dictionaries_dir: Path = _DICTS_DEFAULT, section: str = YONGSIN_SECTION,
) -> PeerMobilityRule | None:
    """브랜처 사전에서 규칙 절(용신 `peer_yongsin_mobility_rules` / 기신
    `peer_gisin_mobility_rules`)을 읽는다(절이 없으면 None — 시드 비활성)."""
    path = dictionaries_dir / "event_engine" / "transit_ten_god_branching.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get(section)
    if not raw:
        return None
    thresholds = data.get("activation_thresholds", {})
    return PeerMobilityRule(
        rule_id=str(raw["id"]),
        incoming_groups=frozenset(raw.get("incoming_groups", ["peer"])),
        favorability_any=frozenset(raw.get("favorability_any", ["용신"])),
        layers=frozenset(LuckLayer(x) for x in raw.get("layers", ["sewoon", "wolwoon"])),
        event=EventKeyV2(raw.get("event", "career_change")),
        base_by_inflow={k: int(v) for k, v in raw["base_by_inflow"].items()},
        inflow_reason_codes=dict(raw.get("inflow_reason_codes", {})),
        event_candidate_threshold=int(thresholds.get("event_candidate", 55)),
        theme_only_threshold=int(thresholds.get("theme_only", 35)),
    )


def classify_inflow(signals: list[TransitSignal]) -> str | None:
    """채점 대상 층의 비겁 신호 → 유입 강도.

    'same_god' > 'same_group' > 'stem_only' > 'branch_only' 순으로 강하다.
    """
    if not signals:
        return None
    if any(s.same_god for s in signals):
        return "same_god"
    if any(s.same_group for s in signals):
        return "same_group"
    if any(s.source == "stem" for s in signals):
        return "stem_only"
    return "branch_only"


def produce_peer_mobility_seeds(
    signals: list[TransitSignal],
    target_layer: LuckLayer,
    result: ManseV2Result,
    fav_map: dict[str, str],
    period: str,
    rule: PeerMobilityRule | None,
) -> list[EventCandidateV2]:
    """비겁 용신(또는 기신 — 대칭 규칙) 명식의 비겁 유입 → career_change 시드(0 또는 1건).

    Args:
        signals: 거버닝 스택에서 수집한 운 십성 신호 전체(층위 포함).
        target_layer: 이번 채점 대상 층(세운·월운·일운…) — 규칙의 layers 에 들어야 한다.
        result: 만세 결과(일간으로 비겁 오행을 정한다).
        fav_map: 오행 → 용기신 역할.
        period: 시점 라벨.
        rule: 사전 규칙(None 이면 빈 목록).
    """
    if rule is None or target_layer not in rule.layers or result.pillars is None:
        return []
    peer_el = str(STEM_ELEMENT[Stem(result.pillars.day.stem)])
    if fav_map.get(peer_el) not in rule.favorability_any:
        return []
    peer_signals = [
        s for s in signals
        if s.layer is target_layer
        and TEN_GOD_GROUP.get(s.ten_god, None) is not None
        and TEN_GOD_GROUP[s.ten_god].value in rule.incoming_groups
    ]
    inflow = classify_inflow(peer_signals)
    if inflow is None:
        return []
    score = rule.base_by_inflow.get(inflow, 0)
    if score <= 0:
        return []
    if score >= rule.event_candidate_threshold:
        confidence = ConfidenceLevel.EVENT_CANDIDATE
    elif score >= rule.theme_only_threshold + 10:
        confidence = ConfidenceLevel.WEAK_EVENT_CANDIDATE
    else:
        confidence = ConfidenceLevel.THEME_ONLY
    reasons = [rule.rule_id]
    code = rule.inflow_reason_codes.get(inflow)
    if code:
        reasons.append(code)
    # 상위 층(대운·세운)에도 비겁이 들어와 있으면 근거 층에 함께 적는다 — 운 위계(상위가 형성,
    # 하위가 사건화)상 상위 뿌리가 있는 월운 유입은 '월운 단독 체감'이 아니다(2026-10 실사례:
    # 대운 壬辰의 辰 겁재). source_layers 는 브랜처 관례대로 평가 스택 구성 전체다(상위 지지
    # 판정에 쓰지 않는다).
    upper_peer_layers = sorted(
        {
            s.layer for s in signals
            if s.layer is not target_layer
            and TEN_GOD_GROUP.get(s.ten_god, None) is not None
            and TEN_GOD_GROUP[s.ten_god].value in rule.incoming_groups
        },
        key=lambda x: list(LuckLayer).index(x),
    )
    for layer in upper_peer_layers:
        reasons.append(f"PEER_UPPER_SUPPORT_{layer.value}")
    stack_layers = sorted({s.layer for s in signals}, key=lambda x: list(LuckLayer).index(x))
    # 극성 자리표시 — 뒤 계층 `_period_role` 이 시점 유입 오행의 용기신 역할로 덮어쓴다. 기신
    # 대칭 시드는 GI 로 두어 덮어쓰기 전 단계(테스트·감사)에서도 방향이 읽히게 한다.
    seed_role = PolarityRole.GI if "기신" in rule.favorability_any else PolarityRole.YONG
    return [EventCandidateV2(
        event_key=rule.event,
        period=period,
        score=score,
        confidence_level=confidence,
        polarity_role=seed_role,
        source_layers=stack_layers or [target_layer],
        candidate_source_layers=[
            layer.value for layer in (*upper_peer_layers, target_layer)
        ],
        source_ten_gods=sorted({s.ten_god for s in peer_signals}, key=str),
        reason_codes=reasons,
        # 단독 시드는 이 점수가 곧 base다 — 기여 로그 불변식(기여 합 ≈ raw_score, 'base' 존재) 유지.
        contributions={"base": float(score)},
    )]


def merge_peer_mobility_seeds(
    cands: list[EventCandidateV2], seeds: list[EventCandidateV2]
) -> list[EventCandidateV2]:
    """같은 시점에 브랜처가 이미 같은 사건 후보를 냈으면 점수는 최댓값·근거는 합집합으로 합친다."""
    if not seeds:
        return cands
    out = list(cands)
    for seed in seeds:
        existing = next((c for c in out if c.event_key is seed.event_key), None)
        if existing is None:
            out.append(seed)
            continue
        # 병합 기여는 실제 증분만 기록한다(기여 합 ≈ raw_score 불변식 — test_score_saturation).
        delta = max(0, seed.score - existing.score)
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
        existing.contributions["peer_mobility_seed"] = float(delta)
    return out


__all__ = [
    "GISIN_SECTION", "PeerMobilityRule", "TenGodGroup", "YONGSIN_SECTION", "classify_inflow",
    "load_peer_mobility_rule", "merge_peer_mobility_seeds", "produce_peer_mobility_seeds",
]
