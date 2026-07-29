"""OA-7c-S3 — money_small_gain 의 전체 1위를 십성 조건별로 분해(측정 전용).

닫아야 할 질문: 전체 1위 1,388회가 **특정 십성 조건에 몰리는가(T1)**, 아니면
조건과 무관하게 base·confidence 구조가 높은가(T2).

    FULL             현재 점수
    NO_TEN_GOD       money 의 ten_god 기여만 제거
    BASE_NORMALIZED  비교 사건과 base·confidence 를 맞춤
"""

from __future__ import annotations

import collections
import copy
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_relation_shadow import _finalize, _signals  # noqa: E402
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402
from saju_shared_types.constants import ten_god  # noqa: E402
from saju_shared_types.enums import Stem  # noqa: E402

START, DAYS = dt.date(2026, 7, 1), 90
TARGET = "money_small_gain"
PEERS = ("money_good_deal", "praise_recognition", "meet_helper",
         "document_progress", "teamwork_flow")


def _tg_name(ilju_stem: Stem, day_stem: Stem) -> str:
    if ilju_stem == day_stem:
        return "비견"
    return ten_god(ilju_stem, day_stem).value


def run() -> dict:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    tgt = events[TARGET]
    # 비교군 평균 base/conf 로 정규화한 반사실 사전
    peer_base = statistics.mean(events[k]["base_weight"] for k in PEERS)
    peer_conf = statistics.mean(events[k]["expr_confidence"] for k in PEERS)
    norm = {**copy.deepcopy(tgt), "base_weight": peer_base, "expr_confidence": peer_conf}
    no_tg = {**copy.deepcopy(tgt), "ten_god_affinity": {}}

    by_tg: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    probs: dict[str, list[int]] = collections.defaultdict(list)
    gaps: dict[str, list[int]] = collections.defaultdict(list)

    for i in range(DAYS):
        d = START + dt.timedelta(days=i)
        ctx = M.build_day_context(d)
        day_stem = Stem(ctx.day_stem)
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            tg = _tg_name(stem, day_stem)
            scored = {k: M._score_event(k, e, stem, branch, ctx) for k, e in events.items()}
            order = sorted(scored.values(), key=lambda s: -s.probability)
            rank = {s.event_key: r for r, s in enumerate(order, 1)}
            p = scored[TARGET].probability
            c = by_tg[tg]
            c["cards"] += 1
            probs[tg].append(p)
            c["rank1"] += rank[TARGET] == 1
            c["top3"] += rank[TARGET] <= 3
            if rank[TARGET] == 1 and len(order) > 1:
                gaps[tg].append(p - order[1].probability)
            # 반사실 — money 만 바꾸고 나머지는 그대로 두고 순위를 다시 계산
            for label, ev in (("no_ten_god", no_tg), ("base_normalized", norm)):
                alt = _finalize(ev, _signals(ev, stem, branch, ctx), TARGET).probability
                higher = sum(1 for s in order if s.event_key != TARGET and s.probability > alt)
                if higher == 0:
                    c[f"{label}_rank1"] += 1
    out = {}
    for tg, c in sorted(by_tg.items(), key=lambda x: -x[1]["rank1"]):
        n = c["cards"]
        g = gaps.get(tg) or [0]
        out[tg] = {
            "cards": n,
            "mean_probability": round(statistics.mean(probs[tg]), 1),
            "rank1": c["rank1"], "rank1_pct": round(c["rank1"] / n * 100, 1),
            "top3_pct": round(c["top3"] / n * 100, 1),
            "mean_gap_when_rank1": round(statistics.mean(g), 2),
            "p90_gap_when_rank1": sorted(g)[max(0, int(len(g) * 0.9) - 1)],
            "no_ten_god_rank1": c["no_ten_god_rank1"],
            "no_ten_god_rank1_pct": round(c["no_ten_god_rank1"] / n * 100, 1),
            "base_normalized_rank1": c["base_normalized_rank1"],
            "base_normalized_rank1_pct": round(c["base_normalized_rank1"] / n * 100, 1),
            "ten_god_affinity": tgt["ten_god_affinity"].get(tg, 0.0),
        }
    return {
        "target": TARGET,
        "target_base_weight": tgt["base_weight"],
        "target_expr_confidence": tgt["expr_confidence"],
        "peer_mean_base_weight": round(peer_base, 3),
        "peer_mean_expr_confidence": round(peer_conf, 3),
        "by_ten_god": out,
    }


if __name__ == "__main__":
    data = {"audit_id": "OA-7c-S3", "policy_status": "measurement_only",
            "live_behavior_changed": False, "days": DAYS, "result": run()}
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa7c_money_ten_god_90d.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data["result"], ensure_ascii=False, indent=1))
