"""직장 이력 leave-one-out 적중 측정 — EMPLOYMENT_HISTORY_CALIBRATION.md §3-3.

원장의 `employment_history` 입사(job_gain) 행 가운데 취업 통계 성격(정규·파견)만 골라, 한 건을 빼고
나머지로 개인 시그니처를 만든 뒤 그 절기년 12개월 후보를 LifeFitRanker 로 정렬해 실제 입사월이
job_gain 후보 Top-3 안에 드는 비율을 센다. 세 모드를 같은 절차로 비교한다.
- engine: 개인 시그니처 없음(엔진만)
- base:   시그니처 + 글자 가중 0(현재 운영값 — 근거 코드만)
- glyph:  시그니처 + 사전 glyph_weight(플래그 ON 상태와 동일)
- glyph_cap: glyph + 반복 가중 상한(--repeat-cap, 기본 0.6) — personal_match 포화 완화 후보
판정은 하지 않는다 — 수치만 내고 ON/OFF 는 데굴님이 정한다(점수 규칙은 실사례 적중률로
ON/OFF). 우연 기준선 = 3/12 = 25%.

사용법:
    python scripts/measure_employment_history_loo.py --subject <subject_id> \\
        [--json 경로] [--md 경로]
DSN 은 SAJU_V2_DATABASE_URL(루트 .env 자동 로드). 출력에 회사명(label)이 사용자 제공 그대로 찍힌다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines.employment_history import EMPLOYMENT_STAT_NATURES, reference_date_for_label
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.glyph_context import GlyphContext
from saju_engines.life_event_store import LifeEventStore
from saju_engines.life_fit_ranker import LifeFitRanker
from saju_engines.personal_calibration import _GLYPH_CFG
from saju_engines.subject_store import SubjectStore
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.life_event import LifeEventOutcome, LifeEventRow, LifeEventSource

_BACKEND = Path(__file__).resolve().parent.parent
_ENV_PATHS = [_BACKEND.parent / ".env", _BACKEND / ".env"]
_TOP_N = 3
_MODES = ("engine", "base", "glyph", "glyph_cap")


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
class HeldOut:
    """한 건을 뺀 측정 결과."""

    period: str
    label: str
    rank: dict[str, int | None]   # 모드별 실제 월의 순위(1부터, 없으면 None)
    top3: dict[str, list[str]]    # 모드별 Top-3 기간


def _rank_of(ranked: list, period: str) -> tuple[int | None, list[str]]:
    jobs = [c for c in ranked if str(c.event_key) == "job_gain"]
    periods = [c.period for c in jobs]
    rank = periods.index(period) + 1 if period in periods else None
    return rank, periods[:_TOP_N]


def measure(
    birth, signature: list[LifeEventRow], engine: EventEngineV2, repeat_cap: float = 0.6,
) -> list[HeldOut]:
    """정규·파견 입사 행 leave-one-out — 모드별 순위·Top-3."""
    entries = [
        r for r in signature
        if r.event_key == "job_gain" and r.source is LifeEventSource.EMPLOYMENT_HISTORY
        and r.outcome is LifeEventOutcome.CONFIRMED
        and r.attrs.nature in EMPLOYMENT_STAT_NATURES and len(r.period) >= 7
    ]
    out: list[HeldOut] = []
    glyph_w = float(_GLYPH_CFG["glyph_weight"])
    for held in entries:
        rest = [r for r in signature if r.event_row_id != held.event_row_id]
        chart = calculate(birth.model_copy(
            update={"reference_date": reference_date_for_label(held.period)},
        ))
        cands = engine.score(chart, levels={GanjiLevel.MONTH})
        ctx = GlyphContext.from_result(chart)
        ranks: dict[str, int | None] = {}
        tops: dict[str, list[str]] = {}
        for mode in _MODES:
            if mode == "engine":
                ranked = LifeFitRanker().rank(cands)
            else:
                ranked = LifeFitRanker().rank(
                    cands, signature=rest, glyph_context=ctx,
                    glyph_weight=0.0 if mode == "base" else glyph_w,
                    repeat_cap=repeat_cap if mode == "glyph_cap" else None,
                )
            ranks[mode], tops[mode] = _rank_of(ranked, held.period)
        out.append(HeldOut(
            period=held.period, label=held.attrs.label or "", rank=ranks, top3=tops,
        ))
    return out


@dataclass
class FalsePositiveYear:
    """사건이 없던 해(캘리브레이션 not_happened) — 모드별 job_gain 이 월 Top-1 인 달 수."""

    year: int
    top1_months: dict[str, int]


def measure_false_positive(
    birth, signature: list[LifeEventRow], engine: EventEngineV2, repeat_cap: float = 0.6,
) -> list[FalsePositiveYear]:
    """not_happened(job_gain, 연 단위) 해의 12개월에서 job_gain 이 그 달 Top-1 후보인 달 수.

    무상한 반복 가중이 '사건 없는 달'에도 job_gain 을 1위로 올리는 편향(오탐)을 잰다. 시그니처는
    운영과 같은 전체(그 해 not_happened 행 포함 — 운영도 그 행을 보므로).
    """
    years = sorted({
        int(r.period) for r in signature
        if r.event_key == "job_gain" and r.outcome is LifeEventOutcome.NOT_HAPPENED
        and len(r.period) == 4
    })
    glyph_w = float(_GLYPH_CFG["glyph_weight"])
    out: list[FalsePositiveYear] = []
    for y in years:
        chart = calculate(birth.model_copy(update={"reference_date": date(y, 7, 1)}))
        cands = engine.score(chart, levels={GanjiLevel.MONTH})
        ctx = GlyphContext.from_result(chart)
        counts: dict[str, int] = {}
        for mode in _MODES:
            if mode == "engine":
                ranked = LifeFitRanker().rank(cands)
            else:
                ranked = LifeFitRanker().rank(
                    cands, signature=signature, glyph_context=ctx,
                    glyph_weight=0.0 if mode == "base" else glyph_w,
                    repeat_cap=repeat_cap if mode == "glyph_cap" else None,
                )
            top_by_period: dict[str, str] = {}
            for c in ranked:
                top_by_period.setdefault(c.period, str(c.event_key))
            counts[mode] = sum(1 for k in top_by_period.values() if k == "job_gain")
        out.append(FalsePositiveYear(year=y, top1_months=counts))
    return out


def render_fp_md(rows: list[FalsePositiveYear]) -> str:
    """오탐 표 — 모드별 (job_gain Top-1 달 수 / 12×해 수)."""
    if not rows:
        return "오탐 측정: not_happened(job_gain) 연도 없음."
    total = 12 * len(rows)
    lines = [f"오탐(사건 없던 해 {len(rows)}년 × 12달 = {total}달 중 job_gain Top-1 달 수)",
             "| 모드 | Top-1 달 수 | 비율 |", "|---|---|---|"]
    for mode in _MODES:
        n = sum(r.top1_months[mode] for r in rows)
        lines.append(f"| {mode} | {n} | {round(n / total, 3)} |")
    lines.append("")
    lines.append("| 해 | " + " | ".join(_MODES) + " |")
    lines.append("|---|" + "---|" * len(_MODES))
    for r in rows:
        lines.append(f"| {r.year} | " + " | ".join(str(r.top1_months[m]) for m in _MODES) + " |")
    return "\n".join(lines)


def summarize(rows: list[HeldOut]) -> dict[str, dict[str, float | int]]:
    """모드별 Top-3 적중 수·비율·평균 순위."""
    summary: dict[str, dict[str, float | int]] = {}
    n = len(rows)
    for mode in _MODES:
        ranked = [rk for r in rows if (rk := r.rank[mode]) is not None]
        hits = sum(1 for rk in ranked if rk <= _TOP_N)
        summary[mode] = {
            "n": n, "top3_hits": hits, "top3_rate": round(hits / n, 3) if n else 0.0,
            "mean_rank": round(sum(ranked) / len(ranked), 2) if ranked else 0.0,
            "unranked": n - len(ranked),
        }
    return summary


def render_md(rows: list[HeldOut], summary: dict[str, dict[str, float | int]]) -> str:
    """사람이 읽는 표."""
    lines = [
        "| 모드 | n | Top-3 적중 | 비율 | 평균 순위 | 후보 없음 |", "|---|---|---|---|---|---|",
    ]
    for mode, s in summary.items():
        lines.append(f"| {mode} | {s['n']} | {s['top3_hits']} | {s['top3_rate']} | "
                     f"{s['mean_rank']} | {s['unranked']} |")
    lines += [
        "", "| 입사월 | 회사 | engine | base | glyph | glyph_cap | glyph_cap Top-3 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r.period} | {r.label} | {r.rank['engine']} | {r.rank['base']} | "
                     f"{r.rank['glyph']} | {r.rank['glyph_cap']} | "
                     f"{', '.join(r.top3['glyph_cap'])} |")
    lines.append("")
    lines.append("우연 기준선 Top-3 = 25%. 판정은 데굴님(점수 규칙은 실사례 적중률로 ON/OFF).")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--md", type=Path, default=None)
    ap.add_argument("--repeat-cap", type=float, default=0.6)
    args = ap.parse_args(argv)
    _load_env()
    record = SubjectStore().get(args.subject)
    if record is None:
        print(f"대상 없음: {args.subject}", file=sys.stderr)
        return 2
    signature = LifeEventStore().subject_signature(record.owner_id, args.subject)
    engine = EventEngineV2(_BACKEND / "dictionaries")
    rows = measure(record.birth, signature, engine, repeat_cap=args.repeat_cap)
    summary = summarize(rows)
    fp_rows = measure_false_positive(record.birth, signature, engine, repeat_cap=args.repeat_cap)
    md = render_md(rows, summary) + "\n\n" + render_fp_md(fp_rows)
    print(md)
    if args.json:
        args.json.write_text(json.dumps(
            {"summary": summary, "rows": [asdict(r) for r in rows],
             "false_positive": [asdict(r) for r in fp_rows]}, ensure_ascii=False, indent=2,
        ), encoding="utf-8")
    if args.md:
        args.md.write_text(md + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
