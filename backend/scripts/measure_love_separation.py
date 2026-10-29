"""이별운 강의 시드(연애 실험 키 separation_*)의 생애 사건 원장 적중 측정 (2026-10-29).

데굴님 결정 ①(2026-10-29): 겁재 유입의 천간/지지 가중은 "연애운이니 케이스를 기준으로 판단"한다 —
기본(천간 우위)과 `separation_peer_branch_weight`(지지 우위)를 같은 셸에서 나란히 낸다.

정의(이직 측정과 같은 틀 — `measure_career_exit_seed.py`): **엔진이 관계 변동 후보
(relationship_change)라고 한 해·달 가운데 실제 관계 변동이 있던 비율(정밀도)**. 연 단위는
confirmed=양성·not_happened=음성, 월 단위는 confirmed 월 라벨의 절기년 12달. 판정은 하지 않는다 —
수치만 내고 ON/OFF 는 데굴님이 정한다. 85사례 재생 비교는 `casebook_replay --love-experiment`
로 따로 낸다.

사용법:
    python scripts/measure_love_separation.py [--subject <id> ...] [--json 경로] [--md 경로]
DSN 은 SAJU_V2_DATABASE_URL(루트 .env 자동 로드). DB 에 쓰지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import psycopg

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND / "apps" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from measure_career_exit_seed import (  # noqa: E402
    _VARIANTS,
    Metrics,
    SubjectExits,
    _load_env,
    _predicted,
)
from saju_api.services.manse_service import calculate  # noqa: E402
from saju_engines.event_engine_v2 import EventEngineV2  # noqa: E402
from saju_engines.love_separation import (  # noqa: E402
    SEP_OFFICER_OUTPUT,
    SEP_PALACE_JIECAI,
    SEP_PEER_BRANCH_WEIGHT,
    SEP_RESOURCE_INFLOW,
    SEP_ZHENGCAI_PEER,
)
from saju_engines.subject_store import SubjectStore  # noqa: E402
from saju_shared_types.ganji_calendar import GanjiLevel  # noqa: E402

_DICTS = _BACKEND / "dictionaries"
_EVENT = "relationship_change"
_RULES = (SEP_OFFICER_OUTPUT, SEP_PALACE_JIECAI, SEP_RESOURCE_INFLOW, SEP_ZHENGCAI_PEER)
#: 모드 → 켤 실험 키. 'all' 은 네 규칙 + 천간 우위, 'all+branch' 는 지지 우위 변형.
MODES: dict[str, tuple[str, ...]] = {
    "off": (),
    "all": _RULES,
    "all+branch": (*_RULES, SEP_PEER_BRANCH_WEIGHT),
    **{f"only:{k}": (k,) for k in _RULES},
    f"only:{SEP_ZHENGCAI_PEER}+branch": (SEP_ZHENGCAI_PEER, SEP_PEER_BRANCH_WEIGHT),
    f"only:{SEP_PALACE_JIECAI}+branch": (SEP_PALACE_JIECAI, SEP_PEER_BRANCH_WEIGHT),
}


def load_relationship(dsn: str, only: Iterable[str] | None = None) -> list[SubjectExits]:
    """relationship_change 행을 대상별 연/월로 모은다(confirmed 가 not_happened 보다 우선)."""
    sql = (
        "SELECT subject_id, period, outcome FROM subject_life_events "
        "WHERE event_key = %s AND outcome IN ('confirmed','not_happened') "
        "ORDER BY subject_id, period"
    )
    by: dict[str, SubjectExits] = {}
    with psycopg.connect(dsn) as conn:
        for sid, period, outcome in conn.execute(sql, (_EVENT,)).fetchall():
            if only and sid not in set(only):
                continue
            e = by.setdefault(sid, SubjectExits(sid))
            year = int(str(period)[:4])
            if outcome == "confirmed" or year not in e.years:
                e.years[year] = outcome
            if outcome == "confirmed" and len(str(period)) == 7:
                e.months.add(str(period))
    return list(by.values())


def measure(subjects: list[SubjectExits]) -> dict[tuple[str, str], Metrics]:
    """(모드, 변형)별 연·월 정밀도 합산 — relationship_change 기준."""
    engines = {
        m: EventEngineV2(_DICTS, risk_mode="shadow", love_experiments=list(keys))
        for m, keys in MODES.items()
    }
    acc = {(m, v): Metrics(m, v) for m in MODES for v in _VARIANTS}
    store = SubjectStore()
    for sx in subjects:
        record = store.get(sx.subject_id)
        if record is None or not sx.years:
            continue
        month_years = {int(p[:4]) - (1 if p[5:7] == "01" else 0) for p in sx.months}
        for y in sorted(set(sx.years) | month_years):
            chart = calculate(record.birth.model_copy(update={"reference_date": date(y, 7, 1)}))
            lc = chart.luck_cycles
            labels = {p.label for p in lc.monthly_luck} if lc else set()
            actual = sx.months & labels
            for m, eng in engines.items():
                best: dict[str, int] = {}
                for c in eng.score(chart, levels={GanjiLevel.MONTH}):
                    if str(c.event_key) == _EVENT and str(c.period) in labels:
                        best[str(c.period)] = max(best.get(str(c.period), 0), int(c.score))
                for v in _VARIANTS:
                    met = acc[(m, v)]
                    predicted = _predicted(best, v)
                    if y in sx.years and not v.startswith("top"):
                        met.years += 1
                        pos = sx.years[y] == "confirmed"
                        met.positive_years += int(pos)
                        met.predicted_years += int(bool(predicted))
                        met.hit_years += int(bool(predicted) and pos)
                    if actual:
                        met.months += len(labels)
                        met.actual_months += len(actual)
                        met.predicted_months += len(predicted)
                        met.hit_months += len(predicted & actual)
    return acc


def render_md(metrics: dict[tuple[str, str], Metrics], n_subjects: int) -> str:
    lines = [
        "# 이별운 강의 시드 적중 측정 (relationship_change — 문턱·상위 k달 변형)",
        "",
        f"대상 {n_subjects}명. 연: confirmed=양성·not_happened=음성. "
        "월: confirmed 월 라벨의 절기년 12달.",
        "",
        "| 모드 | 변형 | 연 n/양성 | 연 예측/적중 | 연 정밀도 | 연 lift | 월 n/실제 | 월 예측/적중 "
        "| 월 정밀도 | 월 lift |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for m in metrics.values():
        d = m.as_dict()
        y, mo = d["year"], d["month"]
        lines.append(
            f"| {m.mode} | {m.variant} | {y['n']}/{y['positive']} | {y['predicted']}/{y['hits']} "
            f"| {y['precision']:.3f} | {y['lift']:.2f} | {mo['n']}/{mo['actual']} "
            f"| {mo['predicted']}/{mo['hits']} | {mo['precision']:.3f} | {mo['lift']:.2f} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--subject", action="append", default=[])
    var_dir = _BACKEND.parent / "var"
    ap.add_argument("--json", default=str(var_dir / "measure_love_separation.json"))
    ap.add_argument("--md", default=str(var_dir / "measure_love_separation.md"))
    args = ap.parse_args(argv)
    _load_env()
    dsn = os.environ.get("SAJU_V2_DATABASE_URL")
    if not dsn:
        print("SAJU_V2_DATABASE_URL 미설정", file=sys.stderr)
        return 2
    subjects = load_relationship(dsn, args.subject or None)
    metrics = measure(subjects)
    out = {
        "subjects": len(subjects), "variants": list(_VARIANTS),
        "modes": [m.as_dict() for m in metrics.values()],
    }
    Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md = render_md(metrics, len(subjects))
    Path(args.md).write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
