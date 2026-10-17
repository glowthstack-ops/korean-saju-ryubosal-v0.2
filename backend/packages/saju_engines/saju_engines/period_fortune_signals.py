"""기간 총운(월·연) 입력의 사건 신호 보강 — 주요 후보 Top-N·슬롯 주 신호·이동 뒤 흐름.

2026-10-16 데굴님 승인.

배경(실사례 2026-10, 권고사직): 월·연 총운 경로는 2026-06-12 결정으로 사건 후보를 비우고 생활
슬롯 점수만 실었다. 그 결과 '일·직업 100점'이 사건 종류·방향 없이 "강한 용신운"과 붙어 LLM이
'직장 유리·주도권'으로 읽었고, 엔진이 만든 이동 후보(비겁 용신 시드)는 전달되지 않았다.

이 모듈은 세 가지를 **서술 전용**으로 더한다(점수·순위 불변).
  1. 해당 기간 주요 사건 후보 Top-N(기본 3) 선별 — 후보 블록 형식 그대로(강도 표현·활성화 창·
     주체 미상), 단정 차단은 지시문이 유지한다.
  2. 슬롯 줄에 '주 신호'(사건 종류 한글 라벨 + 방향) 부착 — 슬롯 점수는 활성 강도이지 길흉이 아니다.
  3. 비겁 이동 시드가 있는 기간의 '이동 뒤 흐름' 조건부 문구 — 데굴님 정정(2026-10-16): 이동 뒤
     기반이 좋은가는 비겁이 용신이라는 이유만으로 정해지지 않고 **이후 운의 흐름**(긍정/부정/
     엇갈림)으로 정한다. 시드 역할 × 이후 흐름 6칸 사전(`mobility_flow_text.json`)에서 고르기만
     한다.
규칙 기반이며 LLM 판정을 쓰지 않는다(절대원칙 1).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from saju_shared_types.constants import BRANCH_ELEMENT, STEM_ELEMENT
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.event_taxonomy_v2 import EVENT_DOMAIN, EVENT_KO
from saju_shared_types.events import EventCandidate, EventPolarity
from saju_shared_types.llm_input import PeriodFortune
from saju_shared_types.luck import LuckPillar

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
PERIOD_FORTUNE_TOP_N = 3  # 데굴님 승인(2026-10-16) — 월·연 총운 주요 후보 수
_MOBILITY_KEYS = {"career_change"}
_PEER_SEED_ROLE = {"PEER_YONGSIN_MOBILITY": "용신", "PEER_GISIN_MOBILITY": "기신"}
_POLARITY_KO = {
    EventPolarity.POSITIVE: "기회 쪽",
    EventPolarity.NEGATIVE_OR_FORCED: "압박·강제 쪽",
    EventPolarity.CONDITIONAL: "조건부",
    EventPolarity.NEUTRAL: "중립",
}
# 슬롯 이름 → 사건 도메인(event_taxonomy_v2.EVENT_DOMAIN). 월·연 슬롯 명칭 모두 수용.
_SLOT_DOMAINS: dict[str, frozenset[str]] = {
    "일·직업": frozenset({"career", "education"}),
    "직업": frozenset({"career", "education"}),
    "재물": frozenset({"wealth"}),
    "관계·연애": frozenset({"relationship"}),
    "관계": frozenset({"relationship"}),
    "건강": frozenset({"health"}),
}
_EVENT_DOMAIN_STR: dict[str, str] = {str(k): v for k, v in EVENT_DOMAIN.items()}
_EVENT_KO_STR: dict[str, str] = {str(k): v for k, v in EVENT_KO.items()}
SLOT_NOTE = (
    "(슬롯 점수는 그 분야 활성 강도이지 길흉·유불리가 아니다 — 방향은 '주 신호'의 사건 종류·"
    "방향과 [이벤트 후보]·[이동 흐름] 줄로 판단할 것)"
)


@dataclass(frozen=True)
class MobilityFlowItem:
    role: str
    verdict: str
    text: str


@dataclass(frozen=True)
class MobilityFlowConfig:
    role_weights: dict[str, float]
    positive: float
    negative: float
    monthly_months: int
    monthly_years: int
    yearly_years: int
    verdict_ko: dict[str, str]
    items: dict[tuple[str, str], MobilityFlowItem]


@lru_cache(maxsize=4)
def load_mobility_flow(dictionaries_dir: Path = _DICTS_DEFAULT) -> MobilityFlowConfig:
    """`interpretations/mobility_flow_text.json` 로드(캐시)."""
    raw = json.loads(
        (dictionaries_dir / "interpretations" / "mobility_flow_text.json").read_text("utf-8")
    )
    th = raw.get("thresholds", {})
    hz = raw.get("horizon", {})
    items = {
        (it["role"], it["verdict"]): MobilityFlowItem(it["role"], it["verdict"], it["text"])
        for it in raw["items"]
    }
    return MobilityFlowConfig(
        role_weights={k: float(v) for k, v in raw["role_weights"].items()},
        positive=float(th.get("positive", 0.25)),
        negative=float(th.get("negative", -0.25)),
        monthly_months=int(hz.get("monthly_months", 3)),
        monthly_years=int(hz.get("monthly_years", 1)),
        yearly_years=int(hz.get("yearly_years", 2)),
        verdict_ko=dict(raw.get("verdict_ko", {})),
        items=items,
    )


def select_period_candidates(
    all_scored: Iterable[EventCandidate], fortune_type: str, start_label: str,
    top_n: int = PERIOD_FORTUNE_TOP_N,
) -> list[EventCandidate]:
    """해당 기간(월: 'YYYY-MM' / 연: 'YYYY')의 후보를 점수순 Top-N 으로.

    일 총운은 비운다(하루 운세는 인생 사건을 싣지 않는다 — 2026-06-12 결정 유지).
    """
    if fortune_type == "monthly":
        key = start_label[:7]
        pool = [c for c in all_scored if c.period == key]
    elif fortune_type == "yearly":
        key = start_label[:4]
        pool = [c for c in all_scored if c.period == key]
    else:
        return []
    pool.sort(key=lambda c: (-c.score, str(c.event_key)))
    return pool[:top_n]


def _seed_role(c: EventCandidate) -> str:
    for code in c.evidence_path:
        for prefix, role in _PEER_SEED_ROLE.items():
            if str(code).startswith(prefix):
                return role
    return ""


def _signal_label(c: EventCandidate) -> str:
    key = str(c.event_key)
    label = _EVENT_KO_STR.get(key, key)
    tags = [_POLARITY_KO.get(c.polarity, str(c.polarity))]
    if key in _MOBILITY_KEYS:
        tags.append("이동·주체 미상")
    return f"{label}({'·'.join(tags)})"


def annotate_slots(pf: PeriodFortune, candidates: Sequence[EventCandidate]) -> None:
    """슬롯 요약에 '주 신호' 를 붙인다(제자리 수정). 후보가 없으면 아무것도 하지 않는다."""
    if not candidates:
        return
    for slot in pf.slots:
        domains = _SLOT_DOMAINS.get(slot.name)
        if not domains:
            continue
        hits = [c for c in candidates if _EVENT_DOMAIN_STR.get(str(c.event_key)) in domains]
        if hits:
            slot.summary = (
                f"{slot.summary} — 주 신호: " + ", ".join(_signal_label(c) for c in hits[:2])
            )
    pf.slot_note = SLOT_NOTE


def _role_of_pillar(p: LuckPillar, fav_map: dict[str, str]) -> tuple[str, str]:
    try:
        s_el = str(STEM_ELEMENT[Stem(p.stem)])
        b_el = str(BRANCH_ELEMENT[Branch(p.branch)])
    except ValueError:
        return ("", "")
    return (fav_map.get(s_el, "한신"), fav_map.get(b_el, "한신"))


def assess_following_flow(
    following: Sequence[LuckPillar], fav_map: dict[str, str], cfg: MobilityFlowConfig,
) -> tuple[str, str]:
    """이후 운의 흐름 판정 → (verdict, 근거 문자열). 운 기둥이 없거나 역할이 비면 ('mixed', '')."""
    if not following or not fav_map:
        return ("mixed", "")
    vals: list[float] = []
    parts: list[str] = []
    for p in following:
        s_role, b_role = _role_of_pillar(p, fav_map)
        if not s_role and not b_role:
            continue
        vals.append(cfg.role_weights.get(s_role, 0.0))
        vals.append(cfg.role_weights.get(b_role, 0.0))
        parts.append(f"{p.label} {p.ganji}({p.stem_ten_god}·{s_role}/{p.branch_ten_god}·{b_role})")
    if not vals:
        return ("mixed", "")
    mean = sum(vals) / len(vals)
    if mean >= cfg.positive:
        verdict = "positive"
    elif mean <= cfg.negative:
        verdict = "negative"
    else:
        verdict = "mixed"
    return (verdict, " · ".join(parts))


def mobility_flow_lines(
    candidates: Sequence[EventCandidate], following: Sequence[LuckPillar],
    fav_map: dict[str, str], cfg: MobilityFlowConfig | None = None,
) -> list[str]:
    """비겁 이동 시드가 있는 기간의 [이동 흐름] 줄(0 또는 1~2줄). 시드가 없으면 빈 목록."""
    role = next((r for r in (_seed_role(c) for c in candidates) if r), "")
    if not role:
        return []
    cfg = cfg or load_mobility_flow()
    verdict, basis = assess_following_flow(following, fav_map, cfg)
    item = cfg.items.get((role, verdict))
    if item is None:
        return []
    verdict_ko = cfg.verdict_ko.get(verdict, verdict)
    lines = [f"이동 흐름(비겁 {role} 시드 × 이후 흐름 {verdict_ko}): {item.text}"]
    if basis:
        lines.append(f"  근거(이후 운의 용기신 역할): {basis}")
    return lines


def annotate_period_fortune(
    pf: PeriodFortune, candidates: Sequence[EventCandidate], following: Sequence[LuckPillar],
    fav_map: dict[str, str], dictionaries_dir: Path = _DICTS_DEFAULT,
) -> None:
    """슬롯 주 신호 + 이동 흐름 줄을 PeriodFortune 에 채운다(제자리 수정, 점수 불변)."""
    annotate_slots(pf, candidates)
    pf.mobility_flow_lines = mobility_flow_lines(
        candidates, following, fav_map, load_mobility_flow(dictionaries_dir)
    )


__all__ = [
    "PERIOD_FORTUNE_TOP_N", "SLOT_NOTE", "MobilityFlowConfig", "annotate_period_fortune",
    "annotate_slots", "assess_following_flow", "load_mobility_flow", "mobility_flow_lines",
    "select_period_candidates",
]
