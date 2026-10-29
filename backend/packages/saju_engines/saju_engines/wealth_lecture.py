"""재물 강의 3편 번역층 — 재물 그릇 4분류·식상/재성 보완·그릇×유입 만족도·재성×겁재 제안 경계.

대조 문서: doc/v2_2/EXTERNAL_TEXT_GAP_WEALTH_VESSEL.md (2026-10-29 데굴님 결정 — "권유대로").

- 재물 그릇 4분류(원국 분류 해설 — 판정 아님): 신강약(엔진 밴드, `wealth_capacity._is_strong`)
  × 재성 튼튼(재성 세력 강 = 비중 22%+ 또는 3자리+ — 결혼 자원 블록과 같은 기준 — 그리고 식상
  10%+). 신왕재왕=그릇 큼, 신약재약=그릇 작음, 나머지=보통.
- 식상·재성 보완(운 간지별): 원국 식상만(식상 10%+·재성 10% 미만) + 운 재성 → 밖에서 벌어올 환경,
  원국 재성만 + 운 식상 → 묻힌 재물을 캐내 쓰는 시기. 둘 다 없는 원국은 인성·관성 경로 해설.
- 그릇 × 시기 재물 유입(운 간지별): 그 기간 재물 후보(재물 변화·횡재) 최고점 ≥70 = 유입 많음,
  <55 = 유입 적음(사건 후보 문턱 55·'가능성 높음' 문턱 70 재사용).
- 재성 × 겁재 제안 경계(운 간지별): 원국 재성 + 운 겁재, 또는 원국 겁재 + 운 재성. 원국 관성이
  있으면 완화 문구, 신약이면 '도움이 지분 요구로' 문구 — 재물 질문에서 한 번만(원칙 8).

문구는 사전 `interpretations/wealth_lecture_text.json` 에서 고르기만 한다. 점수·판정 불변(서술층).
점수층(원국 한쪽 + 운 한쪽 식상생재 발동)은 `wealth_capacity.detect_wealth_activations` 의
`natal_complement` 인자로 따로 둔다(플래그 OFF — 측정 후).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from saju_shared_types.constants import main_hidden_stem, ten_god
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.manse_result import ManseV2Result

from .marriage_resource import analyze_marriage_resource
from .wealth_capacity import _is_strong

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"

#: 존재 임계(%) — 구조 패턴 '존재' 임계(pattern_transit._MIN_PRESENCE)와 같다.
PRESENCE_PCT = 10.0
#: 시기 재물 유입 문턱 — 사건 후보(55)·'가능성 높음'(70) 표현 문턱 재사용.
INFLOW_HIGH = 70
INFLOW_LOW = 55
_WEALTH = ("정재", "편재")
_OUTPUT = ("식신", "상관")


@dataclass(frozen=True)
class WealthVessel:
    """원국 재물 그릇 판정 재료(엔진 산출값만)."""

    strong: bool
    wealth_firm: bool
    output_pct: float
    wealth_pct: float
    officer_pct: float
    natal_jiecai: bool

    @property
    def quadrant(self) -> str:
        """신왕재왕 / 신왕재약 / 신약재왕 / 신약재약."""
        return ("신왕" if self.strong else "신약") + ("재왕" if self.wealth_firm else "재약")

    @property
    def size(self) -> str:
        """그릇 크기 — 'big'(신왕재왕) / 'small'(신약재약) / 'mid'."""
        return {"신왕재왕": "big", "신약재약": "small"}.get(self.quadrant, "mid")


def wealth_vessel(result: ManseV2Result) -> WealthVessel | None:
    """원국 재물 그릇 재료 — 기둥·세력 분석이 없으면 None."""
    p = result.pillars
    fa = result.force_analysis
    if p is None or fa is None:
        return None
    groups = fa.ten_gods.groups
    output_pct = float(groups.get("output", 0.0))
    wealth_strong = analyze_marriage_resource(result).wealth_strong
    gods = [
        tg for pil in (p.year, p.month, p.day, p.hour) if pil is not None
        for tg in ((pil.stem_ten_god if pil is not p.day else ""), pil.branch_main_ten_god)
    ]
    return WealthVessel(
        strong=_is_strong(fa.strength.band, bool(fa.strength.strong_chart_gate.get("passed"))),
        wealth_firm=wealth_strong and output_pct >= PRESENCE_PCT,
        output_pct=output_pct,
        wealth_pct=float(groups.get("wealth", 0.0)),
        officer_pct=float(groups.get("officer", 0.0)),
        natal_jiecai="겁재" in gods,
    )


@lru_cache(maxsize=4)
def _texts(dictionaries_dir: Path = _DICTS_DEFAULT) -> dict[str, str]:
    path = dictionaries_dir / "interpretations" / "wealth_lecture_text.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {it["id"]: it["text"] for it in data["items"]}


_QUADRANT_ID = {
    "신왕재왕": "vessel_strong_firm", "신왕재약": "vessel_strong_weak",
    "신약재왕": "vessel_weak_firm", "신약재약": "vessel_weak_weak",
}


def wealth_vessel_lines(result: ManseV2Result) -> list[str]:
    """원국 분류 해설 줄 — 재물 그릇 4분류 + (식상·재성 모두 없을 때) 인성·관성 경로 + 관점."""
    v = wealth_vessel(result)
    if v is None:
        return []
    t = _texts()
    lines = [
        f"재물 그릇 분류(원국 해설 — 판정 아님): {v.quadrant} — {t[_QUADRANT_ID[v.quadrant]]}",
    ]
    output_on = v.output_pct >= PRESENCE_PCT
    wealth_on = v.wealth_pct >= PRESENCE_PCT
    if not output_on and not wealth_on:
        groups = result.force_analysis.ten_gods.groups if result.force_analysis else {}
        resource = float(groups.get("resource", 0.0)) >= PRESENCE_PCT
        officer = v.officer_pct >= PRESENCE_PCT
        if resource and officer:
            lines.append("식상·재성이 약한 원국: " + t["no_output_wealth_resource_officer"])
        elif resource:
            lines.append("식상·재성이 약한 원국: " + t["no_output_wealth_resource"])
    elif wealth_on and not output_on:  # 식상생재 강의(2026-10-29) — 재성만
        lines.append("재성만 있는 원국: " + t["natal_wealth_only"])
    elif output_on and not wealth_on:  # 식상만
        lines.append("식상만 있는 원국: " + t["natal_output_only"])
    if not output_on:
        lines.append(t["bond_support"])
    lines += output_blocked_lines(result)
    lines.append(t["perspective"])
    return lines


#: 식상이 능력을 펴기 어려운 원국 구조(식상생재 강의 — 일간 허약·관살·인성·재성 과다) — 구조 패턴
#: 사전 id. 성립 판정은 `detect_structure_patterns` 그대로(재판정 없음).
OUTPUT_BLOCKING_PATTERNS: tuple[str, ...] = (
    "SEOLGI_TAEGWA", "GWANDA_SINYAK", "INDA_SINYAK", "PYEONIN_DOSIK", "JAEDA_SINYAK",
)


def output_blocked_lines(result: ManseV2Result) -> list[str]:
    """원국 식상(10%+)이 있고 식상을 막는 구조 패턴이 원국에서 성립하면 1줄(없으면 빈 목록)."""
    v = wealth_vessel(result)
    if v is None or v.output_pct < PRESENCE_PCT:
        return []
    from .structure_patterns import detect_structure_patterns

    hits = [
        p.name_ko for p in detect_structure_patterns(result)
        if p.pattern_id in OUTPUT_BLOCKING_PATTERNS
    ]
    if not hits:
        return []
    return [f"식상 발휘 제약({'·'.join(hits)}): " + _texts()["output_blocked"]]


def _luck_gods(dm: Stem, ganji: str) -> tuple[str, str] | None:
    try:
        return (
            str(ten_god(dm, Stem(ganji[0]))),
            str(ten_god(dm, Stem(main_hidden_stem(Branch(ganji[1])).value))),
        )
    except (ValueError, IndexError):
        return None


def wealth_period_texts(result: ManseV2Result, ganji: str, wealth_score: int | None) -> list[str]:
    """운 간지 1개(그 기간 재물 후보 최고점 포함)에 붙는 문구 — 조건 성립분만."""
    v = wealth_vessel(result)
    p = result.pillars
    if v is None or p is None or len(ganji) < 2:
        return []
    gods = _luck_gods(Stem(p.day_master), ganji)
    if gods is None:
        return []
    t = _texts()
    out: list[str] = []
    luck_wealth = any(g in _WEALTH for g in gods)
    luck_output = any(g in _OUTPUT for g in gods)
    if v.output_pct >= PRESENCE_PCT and v.wealth_pct < PRESENCE_PCT and luck_wealth:
        out.append(t["complement_output_natal"])
    if v.wealth_pct >= PRESENCE_PCT and v.output_pct < PRESENCE_PCT and luck_output:
        out.append(t["complement_wealth_natal"])
    if wealth_score is not None:
        inflow = (
            "high" if wealth_score >= INFLOW_HIGH else "low" if wealth_score < INFLOW_LOW else ""
        )
        cell = f"satisfaction_{v.size}_{inflow}" if inflow and v.size != "mid" else ""
        if cell in t:
            out.append(t[cell])
    if "편인" in gods:
        # 편인 도식(2026-10-29 강의) — 원국 식신 기준 문구(경제 활동 제약·큰 결정 조언·몰입 상담).
        from .chart_interpretation import dosik_texts

        out.extend(dosik_texts(result))
    peer_wealth = (v.wealth_pct >= PRESENCE_PCT and "겁재" in gods) or (
        v.natal_jiecai and luck_wealth
    )
    if peer_wealth:
        key = (
            "peer_wealth_caution_officer" if v.officer_pct >= PRESENCE_PCT
            else "peer_wealth_caution_weak" if not v.strong
            else "peer_wealth_caution"
        )
        out.append(t[key])
    return out


def wealth_period_block(
    result: ManseV2Result, periods: list[tuple[str, str, int | None]],
) -> list[str]:
    """재물 질문용 블록 — 후보 기간 운 간지마다 문구를 간지당 1회(없으면 빈 목록).

    Args:
        result: 본인 명식.
        periods: (기간 라벨, 운 간지, 그 기간 재물 후보 최고점 또는 None).
    """
    seen: set[str] = set()
    lines: list[str] = []
    for period, ganji, score in periods:
        if not ganji or ganji in seen:
            continue
        seen.add(ganji)
        texts = wealth_period_texts(result, ganji, score)
        if texts:
            lines.append(f"- {period} {ganji}: " + " ".join(texts))
    if not lines:
        return []
    return [
        "[재물 운 결 — 재물 강의 번역층(원국 그릇 × 운 글자)] 그릇은 조건일 뿐 실제 재물은 운과 "
        "노력에 따라 달라진다. 재물 사건은 가능성형으로 쓰고 수익·당첨 확정은 금지, 주의 문장은 "
        "답 전체에서 한 번만.",
        *lines,
    ]


def daewoon_readiness_lines(result: ManseV2Result, start_year: int, end_year: int) -> list[str]:
    """[start_year, end_year] 와 겹치는 재성 대운마다 '받을 준비' 1줄(2026-10-29 대운 강의).

    재성 대운(천간 또는 지지 본기 십성이 정재·편재)에 원국 식상(10%+)이 있으면 '받을 준비가 된
    대운', 없으면 '방법을 만들어야 내 것이 되는 대운'. 강의 예시 범위(재성×식상)만 — 다른 십성으로
    넓히지 않는다(데굴님 결정). 해당 대운이 없으면 빈 목록.
    """
    v = wealth_vessel(result)
    lc = result.luck_cycles
    if v is None or lc is None or not lc.daewoon_table:
        return []
    t = _texts()
    ready = v.output_pct >= PRESENCE_PCT
    lines: list[str] = []
    for dw in lc.daewoon_table:
        s = dw.approx_start_date.year if dw.approx_start_date else None
        e = dw.approx_end_date.year if dw.approx_end_date else None
        if s is None or (e or 9999) < start_year or s > end_year:
            continue
        if dw.stem_ten_god not in _WEALTH and dw.branch_ten_god not in _WEALTH:
            continue
        key = "daewoon_wealth_ready" if ready else "daewoon_wealth_no_spoon"
        lines.append(f"- 대운 {dw.ganji}({s}–{e}, {dw.start_age}세–): {t[key]}")
    if not lines:
        return []
    return ["[대운 받을 준비 — 재성 대운 × 원국 식상(대운 강의, 서술 전용)]", *lines]

