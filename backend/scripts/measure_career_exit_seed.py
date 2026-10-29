"""외부 강의 번역 시드(상관견관·겁재 역할 무관·편인 휴직)의 생애 사건 원장 적중 측정 (2026-10-29).

적중률의 정의(데굴님 2026-10-24 기준을 이직·퇴사에 적용): **엔진이 '이직·퇴사 후보(career_change
≥ event_candidate 문턱)'라고 한 해(또는 달) 가운데 실제 이직·퇴사가 있던 비율(정밀도)**. 재현율과
기저율 대비 배수(lift)는 참고로 함께 낸다. 판정은 하지 않는다 — 수치만 내고 규칙별 ON/OFF 는
데굴님이 정한다(점수 규칙은 실사례 적중률로 켜고 끈다, 2026-10-15).

모집단(연 단위): `subject_life_events` 의 career_change(confirmed / not_happened)·resignation
(원장 전용, confirmed) 행이 있는 모든 대상-연도. not_happened 연도가 음성 표본이다.
모집단(월 단위): 월 라벨('YYYY-MM')이 있는 confirmed 행 — 그 절기년 12달 가운데 표지가 붙은 달과
실제 달을 비교한다(기저율 = 실제 달 / 12).

모드: off(기준선) / on(절 전체) / on:<규칙 id>(그 규칙만). career_leave(휴직)는 원장에 행이 없어
적중률을 재지 못한다 — 발생 건수만 shadow 관측으로 적는다.

사용법:
    python scripts/measure_career_exit_seed.py [--subject <id> ...] [--json 경로] [--md 경로]
DSN 은 SAJU_V2_DATABASE_URL(루트 .env 자동 로드). DB 에 쓰지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import psycopg

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND / "apps" / "api"))

from saju_api.services.manse_service import calculate  # noqa: E402
from saju_engines.career_exit_seed import load_career_exit_config  # noqa: E402
from saju_engines.event_engine_v2 import EventEngineV2  # noqa: E402
from saju_engines.subject_store import SubjectStore  # noqa: E402
from saju_shared_types.ganji_calendar import GanjiLevel  # noqa: E402

_DICTS = _BACKEND / "dictionaries"
_ENV_PATHS = [_BACKEND.parent / ".env", _BACKEND / ".env"]
_EXIT_KEYS = ("career_change", "resignation")
#: 변형 — 문턱(t55=event_candidate 문턱·t70·t85·t95)과 절기년 12달 안의 상대 순위(top1·top3).
#: t55 는 거의 모든 달이 후보라 포화한다(2026-10-29 1차: 276달 중 265달) — 변별은 t85↑·top-k.
_VARIANTS = ("t55", "t70", "t85", "t95", "top1", "top3")


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
class SubjectExits:
    """대상 1명의 이직·퇴사 원장 — 연도별 결과(confirmed/not_happened)와 월 라벨."""

    subject_id: str
    years: dict[int, str] = field(default_factory=dict)  # 연도 → 'confirmed'|'not_happened'
    months: set[str] = field(default_factory=set)  # 'YYYY-MM' confirmed


def load_exits(dsn: str, only: Iterable[str] | None = None) -> list[SubjectExits]:
    """career_change·resignation 행을 대상별 연/월로 모은다(confirmed 가 not_happened 보다 우선)."""
    sql = (
        "SELECT subject_id, period, outcome FROM subject_life_events "
        "WHERE event_key = ANY(%s) AND outcome IN ('confirmed','not_happened') "
        "ORDER BY subject_id, period"
    )
    by: dict[str, SubjectExits] = {}
    with psycopg.connect(dsn) as conn:
        for sid, period, outcome in conn.execute(sql, (list(_EXIT_KEYS),)).fetchall():
            if only and sid not in set(only):
                continue
            e = by.setdefault(sid, SubjectExits(sid))
            year = int(str(period)[:4])
            if outcome == "confirmed" or year not in e.years:
                e.years[year] = outcome
            if outcome == "confirmed" and len(str(period)) == 7:
                e.months.add(str(period))
    return list(by.values())


@dataclass
class Metrics:
    """모드 1개의 연·월 정밀도."""

    mode: str
    variant: str = "t55"
    years: int = 0
    positive_years: int = 0
    predicted_years: int = 0
    hit_years: int = 0
    months: int = 0
    actual_months: int = 0
    predicted_months: int = 0
    hit_months: int = 0
    leave_candidates: int = 0  # career_leave 후보 수(shadow 관측 — 적중 정의 없음)

    def _ratio(self, a: int, b: int) -> float:
        return a / b if b else 0.0

    def as_dict(self) -> dict:
        yp = self._ratio(self.hit_years, self.predicted_years)
        yb = self._ratio(self.positive_years, self.years)
        mp = self._ratio(self.hit_months, self.predicted_months)
        mb = self._ratio(self.actual_months, self.months)
        return {
            "mode": self.mode,
            "variant": self.variant,
            "year": {
                "n": self.years, "positive": self.positive_years,
                "predicted": self.predicted_years, "hits": self.hit_years,
                "precision": round(yp, 4),
                "recall": round(self._ratio(self.hit_years, self.positive_years), 4),
                "base_rate": round(yb, 4), "lift": round(yp / yb, 3) if yb else 0.0,
            },
            "month": {
                "n": self.months, "actual": self.actual_months,
                "predicted": self.predicted_months, "hits": self.hit_months,
                "precision": round(mp, 4),
                "recall": round(self._ratio(self.hit_months, self.actual_months), 4),
                "base_rate": round(mb, 4), "lift": round(mp / mb, 3) if mb else 0.0,
            },
            "career_leave_candidates": self.leave_candidates,
        }


def _engine(mode: str) -> EventEngineV2:
    if mode == "off":
        return EventEngineV2(_DICTS, risk_mode="shadow")
    rule_ids = None if mode == "on" else [mode.split(":", 1)[1]]
    return EventEngineV2(
        _DICTS, risk_mode="shadow", enable_career_exit_seed=True, career_exit_rule_ids=rule_ids,
    )


def _predicted(best: dict[str, int], variant: str) -> set[str]:
    """변형별 '이직·퇴사 후보' 달 집합."""
    if variant.startswith("top"):
        k = int(variant[3])
        ranked = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
        return {p for p, _ in ranked}
    th = int(variant[1:])
    return {p for p, s in best.items() if s >= th}


def measure(modes: list[str], subjects: list[SubjectExits]) -> dict[tuple[str, str], Metrics]:
    """(모드, 변형)별 연·월 정밀도 합산."""
    acc = {(m, v): Metrics(m, v) for m in modes for v in _VARIANTS}
    engines = {m: _engine(m) for m in modes}
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
            for m, eng in engines.items():
                cands = eng.score(chart, levels={GanjiLevel.MONTH})
                best: dict[str, int] = {}
                leave = 0
                for c in cands:
                    key = str(c.event_key)
                    if key == "career_change" and str(c.period) in labels:
                        best[str(c.period)] = max(best.get(str(c.period), 0), int(c.score))
                    elif key == "career_leave":
                        leave += 1
                actual = sx.months & labels
                for v in _VARIANTS:
                    met = acc[(m, v)]
                    met.leave_candidates += leave
                    predicted_months = _predicted(best, v)
                    if y in sx.years and not v.startswith("top"):
                        # 연 단위는 문턱 변형만 — 상대 순위는 해마다 항상 k달이 뽑혀 의미가 없다.
                        met.years += 1
                        pos = sx.years[y] == "confirmed"
                        met.positive_years += int(pos)
                        pred = bool(predicted_months)
                        met.predicted_years += int(pred)
                        met.hit_years += int(pred and pos)
                    if actual:
                        met.months += len(labels)
                        met.actual_months += len(actual)
                        met.predicted_months += len(predicted_months)
                        met.hit_months += len(predicted_months & actual)
    return acc


def render_md(metrics: dict[tuple[str, str], Metrics], n_subjects: int) -> str:
    lines = [
        "# 강의 번역 시드 적중 측정 (career_change — 문턱·상위 k달 변형)",
        "",
        f"대상 {n_subjects}명. 연 단위: confirmed=양성·not_happened=음성. "
        "월 단위: confirmed 월 라벨의 절기년 12달.",
        "",
        "| 모드 | 변형 | 연 n/양성 | 연 예측/적중 | 연 정밀도 | 연 재현율 | 연 lift "
        "| 월 n/실제 | 월 예측/적중 | 월 정밀도 | 월 재현율 | 월 lift | career_leave 후보 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for m in metrics.values():
        d = m.as_dict()
        y, mo = d["year"], d["month"]
        lines.append(
            f"| {m.mode} | {m.variant} | {y['n']}/{y['positive']} | {y['predicted']}/{y['hits']} | "
            f"{y['precision']:.3f} | {y['recall']:.3f} | {y['lift']:.2f} | "
            f"{mo['n']}/{mo['actual']} | {mo['predicted']}/{mo['hits']} | "
            f"{mo['precision']:.3f} | {mo['recall']:.3f} | {mo['lift']:.2f} | "
            f"{d['career_leave_candidates']} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--subject", action="append", default=[])
    var_dir = _BACKEND.parent / "var"
    ap.add_argument("--json", default=str(var_dir / "measure_career_exit_seed.json"))
    ap.add_argument("--md", default=str(var_dir / "measure_career_exit_seed.md"))
    args = ap.parse_args(argv)
    _load_env()
    dsn = os.environ.get("SAJU_V2_DATABASE_URL")
    if not dsn:
        print("SAJU_V2_DATABASE_URL 미설정", file=sys.stderr)
        return 2
    cfg = load_career_exit_config(_DICTS)
    if cfg is None:
        print("career_exit_lecture_rules 절 없음", file=sys.stderr)
        return 2
    modes = ["off", "on", *(f"on:{r.rule_id}" for r in cfg.rules)]
    subjects = load_exits(dsn, args.subject or None)
    metrics = measure(modes, subjects)
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
