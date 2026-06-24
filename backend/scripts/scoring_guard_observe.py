#!/usr/bin/env python3
"""Scoring 1c-α career 운영 관찰 — rank guard 태그 작동 양상 수집(기능 변경 없음).

career 경로에서 guard 가 붙는 후보 샘플·reason 분포·caution_note append 자연성·과발동/미발동을 본다.
실제 .score·순위·reduce 불변. 산출 console only. 규격: §14-9

사용: python scripts/scoring_guard_observe.py [--samples 20]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import saju_manse_analysis.yongsin.operational_role_config as cfg

from saju_engines.context_reducer import _daewoon_lookup, _to_llm_candidate
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.event_scoring import favorability_map
from saju_engines.scoring_operational import (
    guard_caution_phrase,
    operational_rank_guards,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel

_BACKEND = Path(__file__).resolve().parents[1]
_CHARTS = _BACKEND / "data" / "shadow_charts" / "charts.jsonl"
_DICTS = _BACKEND / "dictionaries"


def _calc(birth: BirthInput):
    from saju_api.services.manse_service import calculate
    return calculate(birth)


def main() -> None:
    ap = argparse.ArgumentParser(description="1c-α career guard 관찰")
    ap.add_argument("--samples", type=int, default=20)
    args = ap.parse_args()

    # career + 1c-α on(관찰용 — 실제 .score/순위 불변).
    cfg.SCORING_OPERATIONAL_APPLY_ENABLED = True
    cfg.SCORING_OPERATIONAL_APPLY_MODE = {"rank_guard": True, "near_tie_demotion": False}
    cfg.SCORING_OPERATIONAL_COMPONENTS = {
        "conditional_byeong_downgrade": True, "low_operability_yongsin": True}
    eng = EventEngineV2(_DICTS)
    charts = [json.loads(line) for line in _CHARTS.read_text(encoding="utf-8").splitlines()
              if line.strip()]

    samples: list[tuple] = []
    reason_ct: Counter = Counter()
    with_existing = 0           # 기존 caution_note 가 있던 후보 수(append 자연성)
    total_guards = 0
    per_chart_guard: list[tuple[str, int, int]] = []   # (chart, guards, selected)
    fear_words = ("흉", "나쁨", "불행", "위험")          # 과장 단어 미사용 확인

    for c in charts:
        r = _calc(BirthInput(**c["input"]))
        if r.luck_cycles is None:
            continue
        dw = eng.score_legacy(r, levels={GanjiLevel.DAEWOON, GanjiLevel.YEAR})
        gbp = {f"{d.approx_start_date.year}~{d.approx_end_date.year}": d.ganji
               for d in r.luck_cycles.daewoon_table}
        for p in r.luck_cycles.yearly_luck:
            gbp[p.label] = p.ganji
        guards = operational_rank_guards(r, dw, gbp, domain="career")
        total_guards += len(guards)
        per_chart_guard.append((c["chart_id"], len(guards), len(dw)))
        dwy = _daewoon_lookup(r)
        dm = r.pillars.day_master if r.pillars else ""
        fav = favorability_map(r)
        for idx, reason_key in guards:
            reason_ct[reason_key] += 1
            cand = dw[idx]
            natural = _to_llm_candidate(cand, gbp, dwy, dm, fav, r).caution_note
            if natural:
                with_existing += 1
            phrase = guard_caution_phrase(reason_key, natural)  # compact/full 반영
            appended = f"{natural} {phrase}".strip() if natural else phrase
            samples.append((c["chart_id"], cand.period, str(cand.event_key),
                            natural, phrase, appended))

    print("=" * 76)
    print(f"1c-α career guard 관찰 — 차트 {len(charts)} · 총 guard {total_guards} "
          f"(실제 .score·순위·reduce 불변)")
    print("=" * 76)
    print(f"1. reason 분포: {dict(reason_ct)}")
    print(f"2. 기존 caution_note 존재(append 대상): {with_existing}/{len(samples)}")
    fear = [s for s in samples if any(w in s[4] for w in fear_words)]
    print(f"3. guard 문구에 과장 단어(흉/나쁨/위험) 사용: {len(fear)} (0이어야 정상)")
    chart_over = [(cid, g) for cid, g, _ in per_chart_guard if g > 3]
    print(f"4. 차트당 guard >3(과발동): {len(chart_over)} (0이어야 정상)")
    zero = sum(1 for _c, g, _ in per_chart_guard if g == 0)
    print(f"5. guard 0 차트(미발동): {zero}/{len(per_chart_guard)}")
    print(f"6. caution_note append 샘플 (상위 {args.samples}):")
    for cid, per, ek, nat, _ph, app in samples[:args.samples]:
        tag = "+append" if nat else "신규"
        print(f"   [{cid[:18]:<18}] {per:<10} {ek:<20} ({tag})")
        if nat:
            print(f"        기존: {nat[:60]}")
        print(f"        최종: {app[:90]}")
    print("=" * 76)


if __name__ == "__main__":
    main()
