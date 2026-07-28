"""OA-7b — 일운 헤드라인 기준선 감사(측정 전용, 제품 로직 변경 없음).

OA-8a 파일럿 대상을 고르기 위한 근거를 만든다. 네 가지만 낸다:

    A. support 6종의 원시 순위 분포 — 신호 부재 / 저점수 / 동일 도메인에 밀림 구분
    B. 도메인 전환별 교체 손실 — 특정 방향만 손실이 크면 점수 구조 문제
    C. 하루 보드의 event_key 최대 점유 — domain cap 통과 후 사건 단위 재독점 확인
    D. 헤드라인 Pareto — 상위 5·8·10 누적 점유

사용법:
    python scripts/audit_daily_headline_baseline.py [시작일 YYYY-MM-DD] [일수]
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import saju_engines.daily_ilju_fortune as M

#: OA-6a에서 헤드라인 자격을 연 사건.
OPENED = (
    "rest_recharge", "tidy_luck", "walk_refresh",
    "small_find", "focus_flow", "family_talk",
)


def _scored_ranks(ctx, dicts) -> dict[str, dict[str, int]]:
    """일주별 `event_key → 전체 점수 순위(1-based)`.

    헤드라인 후보(2개)가 아니라 **사건 49종 전체** 안에서의 순위다. 이 값이 있어야
    "후보에 못 든 것"과 "점수가 낮은 것"을 가를 수 있다.
    """
    from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

    out: dict[str, dict[str, int]] = {}
    for idx in range(60):
        stem, branch = ganzi_from_index(idx)
        scored = [
            M._score_event(key, ev, stem, branch, ctx)
            for key, ev in dicts.catalog["events"].items()
        ]
        ordered = sorted(scored, key=lambda s: (-s.probability, s.event_key))
        out[f"{stem.value}{branch.value}"] = {
            s.event_key: i + 1 for i, s in enumerate(ordered)
        }
    return out


def run(start: dt.date, days: int) -> dict[str, Any]:
    """감사 지표를 산출한다(순수 — 파일을 쓰지 않는다)."""
    dicts = M.load_daily_dicts()
    rank_buckets: dict[str, collections.Counter] = {
        k: collections.Counter() for k in OPENED
    }
    final_headline = collections.Counter()
    transitions: dict[str, list[int]] = collections.defaultdict(list)
    per_day_max: list[dict[str, Any]] = []
    total_cards = 0

    for i in range(days):
        d = start + dt.timedelta(days=i)
        ctx = M.build_day_context(d)
        board = M.compute_board(ctx, dicts)
        ranks = _scored_ranks(ctx, dicts)

        raw_counter = collections.Counter(a.raw_event_key for a in board._headline_audit)
        fin_counter = collections.Counter(
            a.selected_event_key for a in board._headline_audit
        )
        raw_top = raw_counter.most_common(1)[0]
        fin_top = fin_counter.most_common(1)[0]
        per_day_max.append({
            "date": d.isoformat(),
            "raw_top_event": raw_top[0], "raw_top_share": round(raw_top[1] / 60 * 100, 1),
            "final_top_event": fin_top[0],
            "final_top_share": round(fin_top[1] / 60 * 100, 1),
            "top_changed": raw_top[0] != fin_top[0],
        })

        for a in board._headline_audit:
            total_cards += 1
            final_headline[a.selected_event_key] += 1
            if a.selection_reason == "board_domain_cap":
                transitions[f"{a.raw_domain} → {a.selected_domain}"].append(
                    a.displacement_cost
                )
            for key in OPENED:
                r = ranks[a.ilju].get(key)
                if r is None:
                    continue
                bucket = str(r) if r <= 3 else "4+"
                rank_buckets[key][bucket] += 1

    ordered = final_headline.most_common()
    cum = []
    run_sum = 0
    for _key, n in ordered:
        run_sum += n
        cum.append(run_sum / total_cards * 100)
    events = dicts.catalog["events"]
    return {
        "window": {"start": start.isoformat(), "days": days, "cards": total_cards},
        "A_opened_rank_distribution": {
            k: {
                "rank1": rank_buckets[k]["1"], "rank2": rank_buckets[k]["2"],
                "rank3": rank_buckets[k]["3"], "rank4plus": rank_buckets[k]["4+"],
                "final_headline": final_headline.get(k, 0),
            }
            for k in OPENED
        },
        "B_domain_transition_cost": {
            name: {
                "count": len(costs),
                "mean": round(sum(costs) / len(costs), 2),
                "max": max(costs),
                "p90": sorted(costs)[max(0, int(len(costs) * 0.9) - 1)],
            }
            for name, costs in sorted(transitions.items())
        },
        "C_daily_max_event_share": per_day_max,
        "D_headline_pareto": {
            "top5_cum_pct": round(cum[4], 1) if len(cum) > 4 else None,
            "top8_cum_pct": round(cum[7], 1) if len(cum) > 7 else None,
            "top10_cum_pct": round(cum[9], 1) if len(cum) > 9 else None,
            "events": [
                {
                    "event_key": k, "count": n,
                    "share_pct": round(n / total_cards * 100, 1),
                    "domain": events[k]["domain"], "valence": events[k]["valence"],
                }
                for k, n in ordered
            ],
        },
    }


def _head_commit() -> str:
    """기준선을 만든 커밋 — 결과를 코드 상태에 묶는다."""
    import subprocess

    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:  # noqa: BLE001 - git 없는 환경에서도 감사는 돌아야 한다
        return "unknown"


def main(argv: list[str]) -> int:
    start = dt.date.fromisoformat(argv[1]) if len(argv) > 1 else dt.date(2026, 7, 1)
    days = int(argv[2]) if len(argv) > 2 else 30
    from saju_engines.daily_fortune_snapshot import SOURCES, source_digest
    from saju_shared_types.daily_fortune import DICT_VERSION

    backend = Path(__file__).resolve().parent.parent
    dicts_dir = backend / "dictionaries" / "daily_fortune"
    metrics = run(start, days)
    report = {
        "audit_id": "OA-7b",
        "generated_from_commit": _head_commit(),
        "dict_version": DICT_VERSION,
        "selector_version": M.SELECTOR_VERSION,
        "date_range": {
            "from": start.isoformat(),
            "to": (start + dt.timedelta(days=days - 1)).isoformat(),
        },
        "cards": metrics["window"]["cards"],
        "generation_command": (
            f"python scripts/audit_daily_headline_baseline.py {start.isoformat()} {days}"
        ),
        # 사전이 바뀌면 기준선도 다시 만들어야 한다는 신호.
        "source_digest": {
            name: source_digest(dicts_dir / name) for name, _key in SOURCES
        },
        "metrics": metrics,
    }
    out = backend.parent / "doc" / "v2_2" / "audits" / "oa7b_headline_baseline.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[ok] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
