"""진입 시기 두 칸 배정 모드의 정밀도 측정 — EMPLOYMENT_HISTORY_CALIBRATION.md §4-7.

적중률의 정의(데굴님 2026-10-24): **엔진이 '성사 가능'이라고 한 달 가운데 실제 입사가 있던 달의
비율(정밀도)**. 재현율(실제 입사 달 가운데 표지가 붙은 비율)과 기저율 대비 배수(lift)는 참고로 함께
낸다. 판정은 하지 않는다 — 수치만 내고 모드·임계값은 데굴님이 정한다.

모집단: 확정 입사(`job_gain`·confirmed·월 라벨) 행이 있는 모든 대상. 대상마다 첫 입사 절기년부터
마지막 입사 절기년까지의 **모든 달**(입사 없는 해 포함)을 모집단으로 삼아, 모드별로 '성사 가능'
표지가 붙은 달 집합과 실제 입사 달 집합을 비교한다. 입사 달 라벨은 원장의 `period`(절기월).

변형:
- direction            : 결과 방향 긍정·지연 아님·검토월 아님(2026-10-24 오전 1차 규칙)
- trigger70/85/90/95     : 사건 신호 점수 하한 이상(방향 무관)
- trigger70+pos / trigger85+pos: 점수 하한 + 결과 방향 긍정(지연 포함)
- top1/top2/top3          : 그 절기년 12달 안에서 job_gain 점수 상위 k달(상대 순위)
- top3&85                 : 상위 3달 가운데 85점 이상

사용법:
    python scripts/measure_entry_slot_modes.py [--subject <id> ...] [--md 경로] [--json 경로]
DSN 은 SAJU_V2_DATABASE_URL(루트 .env 자동 로드). 출력에 회사명은 찍지 않는다(달·수치만).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import psycopg

from saju_api.services.manse_service import calculate
from saju_engines.entry_slots import assign_entry_slots, is_positive_candidate
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.subject_store import SubjectStore
from saju_shared_types.ganji_calendar import GanjiLevel

_BACKEND = Path(__file__).resolve().parent.parent
_ENV_PATHS = [_BACKEND.parent / ".env", _BACKEND / ".env"]
_VARIANTS = (
    "direction", "trigger70", "trigger85", "trigger90", "trigger95",
    "trigger70+pos", "trigger85+pos", "top1", "top2", "top3", "top3&85",
)


def _load_env() -> None:
    """루트 .env → 환경 변수(이미 설정된 키는 유지)."""
    for path in _ENV_PATHS:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


@dataclass
class SubjectHires:
    """대상 1명의 확정 입사 월 라벨."""

    subject_id: str
    owner_id: str
    periods: list[str]


def load_hires(dsn: str, only: Iterable[str] | None = None) -> list[SubjectHires]:
    """확정 입사(job_gain·confirmed·'YYYY-MM') 행을 대상별로 모은다."""
    sql = (
        "SELECT subject_id, owner_id, period FROM subject_life_events "
        "WHERE event_key='job_gain' AND outcome='confirmed' AND length(period)=7 "
        "ORDER BY subject_id, period"
    )
    by_subject: dict[str, SubjectHires] = {}
    with psycopg.connect(dsn) as conn:
        for sid, owner, period in conn.execute(sql).fetchall():
            if only and sid not in set(only):
                continue
            entry = by_subject.setdefault(sid, SubjectHires(sid, owner, []))
            if period not in entry.periods:
                entry.periods.append(period)
    return list(by_subject.values())


def _label_year(period: str) -> int:
    """절기월 라벨이 들어 있는 만세력 기준 연도(1월 라벨은 전년 목록)."""
    y, m = int(period[:4]), int(period[5:7])
    return y - 1 if m == 1 else y


def _job_best_by_period(cands: list) -> dict[str, int]:
    """달별 job_gain 최고 점수."""
    best: dict[str, int] = {}
    for c in cands:
        if str(c.event_key) == "job_gain" and len(str(c.period)) == 7:
            best[str(c.period)] = max(best.get(str(c.period), 0), int(c.score))
    return best


def predicted_done(cands: list, variant: str) -> set[str]:
    """변형별 '성사 가능' 달 집합."""
    if variant == "direction":
        a = assign_entry_slots(cands, mode="direction")
        return set(a.done_periods) if a else set()
    if variant.startswith("top"):
        k = int(variant[3])
        best = _job_best_by_period(cands)
        ranked = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
        if variant.endswith("&85"):
            ranked = [kv for kv in ranked if kv[1] >= 85]
        return {p for p, _ in ranked}
    th = int(variant[7:9])
    a = assign_entry_slots(cands, mode="trigger", done_min=th)
    done = set(a.done_periods) if a else set()
    if variant.endswith("+pos"):
        pos = {
            str(c.period) for c in cands
            if str(c.event_key) == "job_gain" and len(str(c.period)) == 7
            and is_positive_candidate(c)
        }
        done &= pos
    return done


@dataclass
class VariantMetrics:
    """변형 1개의 정밀도·재현율."""

    variant: str
    months: int
    hires: int
    predicted: int
    hits: int

    @property
    def precision(self) -> float:
        return self.hits / self.predicted if self.predicted else 0.0

    @property
    def recall(self) -> float:
        return self.hits / self.hires if self.hires else 0.0

    @property
    def base_rate(self) -> float:
        return self.hires / self.months if self.months else 0.0

    @property
    def lift(self) -> float:
        return self.precision / self.base_rate if self.base_rate else 0.0


def measure(engine: EventEngineV2, subjects: list[SubjectHires]) -> dict[str, VariantMetrics]:
    """전체 대상 합산 정밀도·재현율(변형별)."""
    acc = {v: VariantMetrics(v, 0, 0, 0, 0) for v in _VARIANTS}
    store = SubjectStore()
    for sh in subjects:
        record = store.get(sh.subject_id)
        if record is None or not sh.periods:
            continue
        first = min(_label_year(p) for p in sh.periods)
        last = max(_label_year(p) for p in sh.periods)
        years = range(first, last + 1)
        actual = set(sh.periods)
        for y in years:
            chart = calculate(record.birth.model_copy(update={"reference_date": date(y, 7, 1)}))
            cands = engine.score(chart, levels={GanjiLevel.MONTH})
            lc = chart.luck_cycles
            month_labels = {p.label for p in lc.monthly_luck} if lc else set()
            for v in _VARIANTS:
                done = predicted_done(cands, v) & month_labels
                m = acc[v]
                m.months += len(month_labels)
                m.hires += len(actual & month_labels)
                m.predicted += len(done)
                m.hits += len(done & actual)
    return acc


def render_md(metrics: dict[str, VariantMetrics], n_subjects: int) -> str:
    """정밀도 표(마크다운)."""
    any_m = next(iter(metrics.values()))
    lines = [
        f"두 칸 배정 모드 정밀도 — 대상 {n_subjects}명, 모집단 {any_m.months}달, "
        f"실제 입사 {any_m.hires}건, 기저율 {any_m.base_rate:.1%}",
        "",
        "| 변형 | 성사 가능 표지 달 | 그중 실제 입사 | 정밀도 | 재현율 | 기저율 대비 |",
        "|---|---|---|---|---|---|",
    ]
    for v in _VARIANTS:
        m = metrics[v]
        lines.append(
            f"| {v} | {m.predicted} | {m.hits} | {m.precision:.1%} | {m.recall:.1%} "
            f"| ×{m.lift:.2f} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", action="append", default=None)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--md", type=Path, default=None)
    args = ap.parse_args(argv)
    _load_env()
    dsn = os.environ.get("SAJU_V2_DATABASE_URL")
    if not dsn:
        print("SAJU_V2_DATABASE_URL 미설정", file=sys.stderr)
        return 2
    subjects = load_hires(dsn, args.subject)
    engine = EventEngineV2(_BACKEND / "dictionaries")
    metrics = measure(engine, subjects)
    md = render_md(metrics, len(subjects))
    print(md)
    if args.json:
        args.json.write_text(json.dumps(
            {v: {**asdict(m), "precision": m.precision, "recall": m.recall, "lift": m.lift}
             for v, m in metrics.items()}, ensure_ascii=False, indent=2,
        ), encoding="utf-8")
    if args.md:
        args.md.write_text(md + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
