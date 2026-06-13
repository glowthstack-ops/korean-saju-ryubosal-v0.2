"""점수 100 포화 진단 (reviewed:false 가중 감수용).

EventEngineV2의 6계층을 한 시점에 대해 단계별로 재생(brancher→12운성→층위·흐름→게이트→
관계·궁성→용신)하면서 이벤트별 점수 변화를 계측한다. 어느 단계·어느 사전 가중이 점수를
100으로 밀어 올리는지(포화)와 클램프 전 raw 초과 폭을 사례로 보여준다.

사용: python scripts/diagnose_score_saturation.py [YYYY ...]   (기본 2024 2025 2026)
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines import event_engine_v2 as E
from saju_engines.addendum_gate_modifier import GateContext
from saju_engines.event_engine_v2 import (
    _LEVEL_TO_LAYER,
    EventEngineV2,
    _activations,
    _period_role,
    _rank_context,
    _StackIndex,
    _stage_of,
)
from saju_engines.event_scoring import favorability_map
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel

_BACKEND = Path(__file__).resolve().parents[1]
_DICTS = _BACKEND / "dictionaries"
_STAGES = ["base", "+12운성", "+층위흐름", "+게이트", "+관계궁성", "+용신", "랭커"]


def _snap(cands) -> dict[str, int]:
    return {str(c.event_key): c.score for c in cands}


def diagnose_period(eng: EventEngineV2, result, idx: _StackIndex, fav_map, label: str):
    """한 세운(YYYY)을 단계별로 계측해 행 단위로 반환한다."""
    target = idx.sewoon_by_year.get(int(label))
    if target is None:
        return None, None
    level = GanjiLevel.YEAR
    stack = idx.stack_for(level, label, target)
    signals = [s for layer, p in stack for s in eng._brancher.collect_from_pillar(p, layer)]

    snaps: list[dict[str, int]] = []
    cands = eng._brancher.branch(signals, label)
    snaps.append(_snap(cands))  # base
    stage_by_layer = {layer: st for layer, p in stack if (st := _stage_of(p)) is not None}
    cands = eng._stage.apply(cands, stage_by_layer)
    snaps.append(_snap(cands))  # +12운성
    cands = eng._flow.apply(cands, signals)
    snaps.append(_snap(cands))  # +층위흐름
    raw = {str(c.event_key): c.raw_score for c in cands}
    present = {s.ten_god for s in signals}
    layers = {layer for layer, _ in stack}
    hits = eng._relation_hits(result, level, target)
    void = any(h.type in E._VOID_TYPES for h in hits)
    cands = eng._gate.apply(cands, GateContext(
        present_gods=present, layers=layers, void_active=void,
    ))
    snaps.append(_snap(cands))  # +게이트
    acts = _activations(hits, _LEVEL_TO_LAYER[level])
    cands = eng._relpalace.apply(cands, acts)
    snaps.append(_snap(cands))  # +관계궁성
    role = _period_role(target, fav_map)
    if role.name != "NEUTRAL":
        cands = [c.model_copy(update={"polarity_role": role}) for c in cands]
        cands = eng._yongi.apply(cands)
    snaps.append(_snap(cands))  # +용신
    cands = eng._ranker.rank(cands, _rank_context(acts, present, cands, None, None))
    snaps.append(_snap(cands))  # 랭커
    final_conf = {str(c.event_key): c.confidence_level.value for c in cands}

    keys = sorted({k for s in snaps for k in s}, key=lambda k: -snaps[-1].get(k, 0))
    rows = []
    for k in keys:
        row = {"event": k, "stages": [s.get(k) for s in snaps],
               "raw": round(raw.get(k, 0.0), 1), "conf": final_conf.get(k, "-")}
        rows.append(row)
    meta = {
        "ganji": target.ganji,
        "role": role.name,
        "n": len(keys),
        "saturated": sum(1 for k in keys if snaps[-1].get(k) == 100),
        "raw_max": max((raw.values()), default=0.0),
    }
    return rows, meta


def main(argv: list[str]) -> int:
    years = [y for y in argv[1:] if y.isdigit()] or ["2024", "2025", "2026"]
    chart = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))
    eng = EventEngineV2(_DICTS)
    idx = _StackIndex(chart)
    fav_map = favorability_map(chart)
    # 거버닝 스택이 결합하는 십성 신호 점검도 출력.
    print(f"# 점수 포화 진단 — 1980-11-22 차트 (용기신 map: {fav_map})\n")
    for label in years:
        rows, meta = diagnose_period(eng, chart, idx, fav_map, label)
        if rows is None:
            print(f"## {label}: 세운 없음\n")
            continue
        print(
            f"## {label} 세운 {meta['ganji']} (운 오행 역할={meta['role']}) — "
            f"후보 {meta['n']}개, score=100 포화 {meta['saturated']}개, "
            f"raw 최대 {meta['raw_max']:.1f}"
        )
        ev = "event"
        hdr = f"{ev:22}" + "".join(f"{s:>9}" for s in _STAGES) + f"{'raw':>8}  conf"
        print(hdr)
        print("-" * len(hdr))
        for r in rows[:12]:
            cells = "".join(f"{(v if v is not None else '·'):>9}" for v in r["stages"])
            print(f"{r['event']:22}{cells}{r['raw']:>8}  {r['conf']}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
