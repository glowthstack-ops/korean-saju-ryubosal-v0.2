"""원국×운 상관견관·겁재 역할 무관 이동·편인 휴직 시드 — 외부 강의 번역층(2026-10-29).

배경: 외부 강의 「직장을 그만두거나 이직해야 할 때」(대조 문서 doc/v2_2/
EXTERNAL_TEXT_GAP_CAREER_EXIT_LECTURE.md)의 세 축을 브랜처와 대조한 결과,
① 원국 천간 정관 × 운 상관(환경형)·② 원국 천간 상관 × 운 정관(자기형)은 브랜처가
**운 신호만** 조합해 원국 글자가 참여하지 않았고(정관격일 때 運破格 감점만),
⑤ 겁재 운 이동 시드는 비겁이 용신·기신일 때만 있어 희신·한신·구신 명식은 후보 0건이었으며,
④ 편인 운의 휴직(복귀 전제의 긴 휴가 — 완전 이탈 아님)은 사건 키가 없었다(`career_leave` 신설).

방식(비겁 시드·역할 시드와 같은 패턴):
  - 브랜처 기본 가지는 바꾸지 않고 브랜처 직후 합류 자리(역할 시드 다음)에서 시드를 더해 **순위로**
    전환한다. 뒤 6계층 보정(길흉·충합·궁위·12운성·대운 교체)은 그대로 적용된다.
  - 원국 쪽 글자는 **천간만**(연·월·시 — 일간 제외, 2026-10-29 데굴님 결정). 구응(정인)은 원국
    천간·지지 본기에서 찾아 `resource_rescue_ratio` 를 곱한다(제거 아님 — 참고 지나갈 수 있음).
  - 유입 강도 4단계(간여지동 > 같은 군 > 천간만 > 지지만)·기준점은 규칙별 `base_by_inflow`.
  - 원인 축(환경/자기)은 점수에 관여하지 않고 reason_code 로만 실린다(서술층이 문구를 고른다).
  - 규칙·사건·점수는 전부 사전 `event_engine/transit_ten_god_branching.json` →
    `career_exit_lecture_rules` 에서 읽는다(하드코딩 금지). 규칙별 `enabled`·`rule_ids` 로 개별
    측정.

점수 규칙이므로 운영 ON/OFF 는 85사례 재생·생애 사건 원장 적중률로 정한다(플래그
`SAJU_CAREER_EXIT_SEED_ENABLED`, 기본 OFF). 규칙 기반이며 LLM 판정을 쓰지 않는다(절대원칙 1).
"""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from saju_shared_types.enums import Stem
from saju_shared_types.event_engine import (
    ConfidenceLevel,
    EventCandidateV2,
    EventKeyV2,
    LuckLayer,
    PolarityRole,
    TenGod,
)
from saju_shared_types.manse_result import ManseV2Result

from .peer_mobility_seed import classify_inflow
from .role_event_seed import incoming_element
from .ten_god_brancher import TEN_GOD_KO_TO_KEY, TransitSignal

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
SECTION = "career_exit_lecture_rules"
#: 원국 천간 자리 — 일간(day)은 십성이 없으므로 제외된다.
_NATAL_STEM_POSITIONS: tuple[str, ...] = ("year", "month", "hour")


@dataclass(frozen=True)
class CareerExitRule:
    """`career_exit_lecture_rules.rules[]` 1건."""

    rule_id: str
    enabled: bool
    incoming: TenGod
    event: EventKeyV2
    natal_stem: TenGod | None  # 원국 천간(연·월·시)에 있어야 하는 십성(None=조건 없음)
    favorability_any: frozenset[str]  # 유입 십성 오행의 역할 조건(비어 있으면 역할 무관)
    rescue_by: frozenset[TenGod]  # 원국(천간·지지 본기)에 있으면 감쇠하는 구응 십성
    cause: str | None  # environment / self — reason_code 전용
    base_by_inflow: dict[str, int]
    seed_role: PolarityRole


@dataclass(frozen=True)
class CareerExitConfig:
    """사전 절 전체."""

    section_id: str
    layers: frozenset[LuckLayer]
    resource_rescue_ratio: float
    inflow_reason_codes: dict[str, str]
    upper_support_prefix: str
    rescue_reason_prefix: str
    cause_reason_codes: dict[str, str]
    event_candidate_threshold: int
    theme_only_threshold: int
    rules: tuple[CareerExitRule, ...]


@lru_cache(maxsize=8)
def load_career_exit_config(dictionaries_dir: Path = _DICTS_DEFAULT) -> CareerExitConfig | None:
    """브랜처 사전에서 `career_exit_lecture_rules` 절을 읽는다(절이 없으면 None — 시드 비활성)."""
    path = dictionaries_dir / "event_engine" / "transit_ten_god_branching.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get(SECTION)
    if not raw:
        return None
    thresholds = data.get("activation_thresholds", {})
    default_base = {k: int(v) for k, v in raw["base_by_inflow"].items()}
    rules: list[CareerExitRule] = []
    for r in raw.get("rules", []):
        fav = r.get("favorability_any") or []
        rules.append(CareerExitRule(
            rule_id=str(r["id"]),
            enabled=bool(r.get("enabled", True)),
            incoming=TenGod(r["incoming"]),
            event=EventKeyV2(r["event"]),
            natal_stem=TenGod(r["natal_stem"]) if r.get("natal_stem") else None,
            favorability_any=frozenset(fav),
            rescue_by=frozenset(TenGod(x) for x in r.get("rescue_by", [])),
            cause=r.get("cause"),
            base_by_inflow={
                k: int(v) for k, v in (r.get("base_by_inflow") or default_base).items()
            },
            seed_role=PolarityRole.GI if r.get("seed_role", "gi") == "gi" else PolarityRole.YONG,
        ))
    return CareerExitConfig(
        section_id=str(raw["id"]),
        layers=frozenset(LuckLayer(x) for x in raw.get("layers", ["sewoon", "wolwoon"])),
        resource_rescue_ratio=float(raw.get("resource_rescue_ratio", 0.8)),
        inflow_reason_codes=dict(raw.get("inflow_reason_codes", {})),
        upper_support_prefix=str(raw.get("upper_support_prefix", "CXL_UPPER_SUPPORT_")),
        rescue_reason_prefix=str(raw.get("rescue_reason_prefix", "CXL_RESCUE_")),
        cause_reason_codes=dict(raw.get("cause_reason_codes", {})),
        event_candidate_threshold=int(thresholds.get("event_candidate", 55)),
        theme_only_threshold=int(thresholds.get("theme_only", 35)),
        rules=tuple(rules),
    )


def natal_stem_ten_gods(result: ManseV2Result) -> set[TenGod]:
    """원국 천간(연·월·시) 십성 집합 — 일간은 제외된다."""
    p = result.pillars
    if p is None:
        return set()
    out: set[TenGod] = set()
    for pos in _NATAL_STEM_POSITIONS:
        pil = getattr(p, pos, None)
        key = TEN_GOD_KO_TO_KEY.get(getattr(pil, "stem_ten_god", "") or "") if pil else None
        if key is not None:
            out.add(key)
    return out


def natal_all_ten_gods(result: ManseV2Result) -> set[TenGod]:
    """원국 천간(연·월·시) + 지지 본기(연·월·일·시) 십성 집합 — 구응(정인) 탐색용."""
    p = result.pillars
    if p is None:
        return set()
    out = natal_stem_ten_gods(result)
    for pos in ("year", "month", "day", "hour"):
        pil = getattr(p, pos, None)
        key = TEN_GOD_KO_TO_KEY.get(getattr(pil, "branch_main_ten_god", "") or "") if pil else None
        if key is not None:
            out.add(key)
    return out


def _confidence(score: int, cfg: CareerExitConfig) -> ConfidenceLevel:
    if score >= cfg.event_candidate_threshold:
        return ConfidenceLevel.EVENT_CANDIDATE
    if score >= cfg.theme_only_threshold + 10:
        return ConfidenceLevel.WEAK_EVENT_CANDIDATE
    return ConfidenceLevel.THEME_ONLY


def produce_career_exit_seeds(
    signals: list[TransitSignal],
    target_layer: LuckLayer,
    result: ManseV2Result,
    fav_map: dict[str, str],
    period: str,
    cfg: CareerExitConfig | None,
    rule_ids: Collection[str] | None = None,
) -> list[EventCandidateV2]:
    """강의 번역 시드 — 규칙마다 0 또는 1건.

    Args:
        signals: 거버닝 스택에서 수집한 운 십성 신호 전체(층위 포함).
        target_layer: 이번 채점 대상 층 — 절의 layers 에 들어야 한다.
        result: 만세 결과(원국 천간 십성·일간).
        fav_map: 오행(한자) → 용기신 역할.
        period: 시점 라벨.
        cfg: 사전 절(None 이면 빈 목록).
        rule_ids: 측정용 — 지정하면 그 규칙 id 만 적용(None=사전 enabled 전부).
    """
    if cfg is None or target_layer not in cfg.layers or result.pillars is None:
        return []
    dm = Stem(result.pillars.day.stem)
    stems = natal_stem_ten_gods(result)
    natal_all = natal_all_ten_gods(result)
    stack_layers = sorted({s.layer for s in signals}, key=lambda x: list(LuckLayer).index(x))
    out: list[EventCandidateV2] = []
    for rule in cfg.rules:
        if rule_ids is not None:
            if rule.rule_id not in rule_ids:
                continue
        elif not rule.enabled:
            continue
        if rule.natal_stem is not None and rule.natal_stem not in stems:
            continue
        if rule.favorability_any:
            if fav_map.get(incoming_element(dm, rule.incoming)) not in rule.favorability_any:
                continue
        target_signals = [
            s for s in signals if s.layer is target_layer and s.ten_god is rule.incoming
        ]
        inflow = classify_inflow(target_signals)
        if inflow is None:
            continue
        score = rule.base_by_inflow.get(inflow, 0)
        if score <= 0:
            continue
        reasons = [rule.rule_id]
        code = cfg.inflow_reason_codes.get(inflow)
        if code:
            reasons.append(code)
        if rule.cause:
            cause_code = cfg.cause_reason_codes.get(rule.cause)
            if cause_code:
                reasons.append(cause_code)
        rescued = sorted(str(g) for g in (rule.rescue_by & natal_all))
        if rescued:
            # 구응(정인 등) — 상관 작용을 달래 참고 지나갈 수 있다(강의 ③). 제거가 아니라 감쇠.
            score = int(round(score * cfg.resource_rescue_ratio))
            reasons.extend(f"{cfg.rescue_reason_prefix}{g}" for g in rescued)
        if score <= 0:
            continue
        upper_layers = sorted(
            {
                s.layer for s in signals
                if s.layer is not target_layer and s.ten_god is rule.incoming
            },
            key=lambda x: list(LuckLayer).index(x),
        )
        reasons.extend(f"{cfg.upper_support_prefix}{layer.value}" for layer in upper_layers)
        out.append(EventCandidateV2(
            event_key=rule.event,
            period=period,
            score=score,
            confidence_level=_confidence(score, cfg),
            polarity_role=rule.seed_role,  # 자리표시 — 뒤 계층 `_period_role` 이 덮어쓴다.
            source_layers=stack_layers or [target_layer],
            candidate_source_layers=[layer.value for layer in (*upper_layers, target_layer)],
            source_ten_gods=[rule.incoming],
            reason_codes=reasons,
            # 단독 시드는 이 점수가 곧 base — 기여 합 ≈ raw_score 불변식 유지.
            contributions={"base": float(score)},
        ))
    return out
