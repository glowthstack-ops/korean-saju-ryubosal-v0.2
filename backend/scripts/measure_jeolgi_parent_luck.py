"""관할 상위 운 절기 기준(`JEOLGI_PARENT_MONTH_ENABLED`·`JEOLGI_PARENT_YEAR_ENABLED`) 영향 측정.

배경(2026-11-11): 사건 엔진 스택이 월·일 라벨의 양력 연·월로 관할 세운·월운을 골랐다. 세운은 입춘에,
월운은 절(節)에 바뀌므로 ① 丑월(라벨 'YYYY-01')에 다음 해 세운 ② 양력 1월 1일~입춘 전 날에 다음 해
세운 ③ 절입 전 초순 날에 다음 절기월의 월운이 붙고 ④ 기준 연도 12달 밖 절기월의 날에는 월운 층이
없었다. ①②는 YEAR 갈래, ③④는 MONTH 갈래다. 이 스크립트는 두 플래그를 껐다 켜며 영향 범위와
실사례 지표를 낸다. 엔진·사전·DB 는 읽기 전용.

측정:
① 달력 범위 — 한 해 365일 가운데 관할 세운·월운이 달라지는 날 수(명식 무관).
② 모의 명식 — 丑월 한 달의 사건 후보(종류·점수)가 얼마나 달라지는가, 경계 구간 날의 후보가 얼마나
   달라지는가.
③ 실사례 — 확정 입사 달에 대한 진입 표지(trigger95 = 현행 기준 등)의 허용 창 포함률(입사 달·전월·
   전전월, 우연 포함률 대비)과 입사 달 정밀도. 丑월 라벨만 바뀌므로 차이는 작다.

사용법:
    python scripts/measure_jeolgi_parent_luck.py [--md 경로] [--json 경로] [--charts 60]
DSN 은 SAJU_V2_DATABASE_URL(루트 .env 자동 로드). 출력에 이름·회사명은 찍지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, time, timedelta
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND / "apps" / "api"))
sys.path.insert(0, str(_BACKEND / "scripts"))

from saju_manse_analysis.luck.luck_calendar import (  # noqa: E402
    luck_month_label,
    sewoon_year_of,
)

from measure_entry_slot_modes import _label_year, load_hires, predicted_done  # noqa: E402
from measure_exam_outcome_patterns import _load_env, coverage  # noqa: E402
from saju_api.services.manse_service import calculate, daily_luck_window  # noqa: E402
from saju_engines import period_v2_config  # noqa: E402
from saju_engines.event_engine_v2 import EventEngineV2  # noqa: E402
from saju_engines.subject_store import SubjectStore  # noqa: E402
from saju_manse_core.calendar.solar_terms import get_table  # noqa: E402
from saju_shared_types.birth_input import BirthInput  # noqa: E402
from saju_shared_types.ganji_calendar import GanjiLevel  # noqa: E402

ENTRY_ROWS: tuple[str, ...] = ("trigger95", "trigger90", "trigger85", "top3")
TOLERANCES: tuple[int, ...] = (0, 1, 2)


#: 상태 이름 → (MONTH 갈래, YEAR 갈래).
STATES: dict[str, tuple[bool, bool]] = {
    "off": (False, False), "month": (True, False), "year": (False, True), "both": (True, True),
}


def _set_flag(state: str) -> None:
    """플래그를 실행 중에 바꾼다 — 모든 소비자가 호출 시점에 모듈 속성을 읽는다."""
    month, year = STATES[state]
    period_v2_config.JEOLGI_PARENT_MONTH_ENABLED = month
    period_v2_config.JEOLGI_PARENT_YEAR_ENABLED = year


def calendar_extent(year: int) -> dict[str, int]:
    """한 해 가운데 관할 세운·월운이 양력 기준과 달라지는 날 수(Asia/Seoul)."""
    table = get_table()
    d = date(year, 1, 1)
    days = sewoon_diff = wolwoon_diff = 0
    while d.year == year:
        ml = luck_month_label(d, table)
        days += 1
        sewoon_diff += sewoon_year_of(ml) != d.year
        wolwoon_diff += ml != f"{d.year}-{d.month:02d}"
        d += timedelta(days=1)
    return {"days": days, "sewoon_changed": sewoon_diff, "wolwoon_changed": wolwoon_diff}


def _sample_births(n: int) -> list[BirthInput]:
    """결정론적 모의 명식 — 1965~2004년, 달·날·시·성별을 고르게 돈다."""
    out: list[BirthInput] = []
    for i in range(n):
        out.append(BirthInput(
            calendar_type="solar",
            birth_date=date(1965 + (i * 7) % 40, 1 + (i * 5) % 12, 1 + (i * 11) % 28),
            birth_time=time((i * 5) % 24, 30),
            birth_place_name="서울",
            gender="male" if i % 2 == 0 else "female",
        ))
    return out


def _by_period(cands: list[Any]) -> dict[str, dict[str, int]]:
    """기간 → {사건 키: 최고 점수}."""
    out: dict[str, dict[str, int]] = defaultdict(dict)
    for c in cands:
        k = str(c.event_key)
        out[str(c.period)][k] = max(out[str(c.period)].get(k, 0), int(c.score))
    return out


def _diff(off: dict[str, int], on: dict[str, int]) -> dict[str, Any]:
    """한 기간의 OFF/ON 후보 비교 — 사건 집합·1위·최대 점수 차."""
    keys = set(off) | set(on)
    top_off = max(off.items(), key=lambda kv: (kv[1], kv[0]))[0] if off else None
    top_on = max(on.items(), key=lambda kv: (kv[1], kv[0]))[0] if on else None
    return {
        "changed": off != on,
        "set_changed": set(off) != set(on),
        "top_changed": top_off != top_on,
        "max_delta": max((abs(off.get(k, 0) - on.get(k, 0)) for k in keys), default=0),
    }


def _summarize(diffs: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(diffs)
    if not n:
        return {"n": 0}
    deltas = sorted(d["max_delta"] for d in diffs)
    return {
        "n": n,
        "changed": sum(d["changed"] for d in diffs),
        "set_changed": sum(d["set_changed"] for d in diffs),
        "top_changed": sum(d["top_changed"] for d in diffs),
        "max_delta_median": deltas[n // 2],
        "max_delta_p90": deltas[min(n - 1, int(n * 0.9))],
        "max_delta_max": deltas[-1],
    }


def synthetic(engine: EventEngineV2, births: list[BirthInput], ref_year: int) -> dict[str, Any]:
    """모의 명식 — 丑월 한 달과 경계 구간 날의 후보 변화."""
    month_diffs: list[dict[str, Any]] = []
    other_month_changed = 0
    month_flag_changed = 0  # MONTH 갈래만 켰을 때 월 단위 후보가 달라진 달(0 이어야 한다)
    day_diffs: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    # 경계 구간: 연초~입춘 전(세운·월운), 한여름 절입 전 초순(월운만), 절입 뒤 대조 구간(불변 기대).
    spans = {
        "1/1~2/3 (세운·월운)": (date(ref_year, 1, 1), date(ref_year, 2, 3)),
        "7/1~7/6 (월운)": (date(ref_year, 7, 1), date(ref_year, 7, 6)),
        "7/8~7/20 (대조)": (date(ref_year, 7, 8), date(ref_year, 7, 20)),
    }
    for b in births:
        chart = calculate(b.model_copy(update={"reference_date": date(ref_year, 7, 1)}))
        lc = chart.luck_cycles
        if lc is None:
            continue
        jan_label = f"{ref_year + 1}-01"
        res: dict[str, dict[str, dict[str, int]]] = {}
        for state in ("off", "month", "year"):
            _set_flag(state)
            res[state] = _by_period(engine.score(chart, levels={GanjiLevel.MONTH}))
        month_diffs.append(_diff(res["off"].get(jan_label, {}), res["year"].get(jan_label, {})))
        other_month_changed += sum(
            res["off"].get(p.label, {}) != res["year"].get(p.label, {})
            for p in lc.monthly_luck if p.label != jan_label
        )
        month_flag_changed += sum(
            res["off"].get(p.label, {}) != res["month"].get(p.label, {}) for p in lc.monthly_luck
        )
        for name, (start, end) in spans.items():
            window = daily_luck_window(chart, start, end)
            day_chart = chart.model_copy(
                update={"luck_cycles": lc.model_copy(update={"daily_luck": window})}
            )
            dres: dict[str, dict[str, dict[str, int]]] = {}
            for state in STATES:
                _set_flag(state)
                dres[state] = _by_period(engine.score(day_chart, levels={GanjiLevel.DAY}))
            for p in window:
                for state in ("month", "year", "both"):
                    day_diffs[(name, state)].append(
                        _diff(dres["off"].get(p.label, {}), dres[state].get(p.label, {}))
                    )
    _set_flag("off")
    return {
        "charts": len(month_diffs),
        "jan_month": _summarize(month_diffs),
        "other_months_changed": other_month_changed,
        "month_flag_changed_months": month_flag_changed,
        "days": {f"{name} · {state}": _summarize(v) for (name, state), v in day_diffs.items()},
    }


def real_cases(engine: EventEngineV2, dsn: str) -> dict[str, Any]:
    """실사례 — 확정 입사 달에 대한 진입 표지의 포함률·정밀도(OFF/ON)."""
    subjects = load_hires(dsn)
    store = SubjectStore()
    out: dict[str, Any] = {"subjects": len(subjects)}
    for on in (False, True):
        _set_flag("year" if on else "off")
        flagged: dict[str, set[tuple[str, str]]] = {v: set() for v in ENTRY_ROWS}
        universe: set[tuple[str, str]] = set()
        hires: set[tuple[str, str]] = set()
        for sh in subjects:
            rec = store.get(sh.subject_id)
            if rec is None or not sh.periods:
                continue
            hires |= {(sh.subject_id, p) for p in sh.periods}
            years = [_label_year(p) for p in sh.periods]
            for y in range(min(years) - 1, max(years) + 1):
                chart = calculate(rec.birth.model_copy(update={"reference_date": date(y, 7, 1)}))
                cands = engine.score(chart, levels={GanjiLevel.MONTH})
                lc = chart.luck_cycles
                labels = {p.label for p in lc.monthly_luck} if lc else set()
                if y >= min(years):
                    universe |= {(sh.subject_id, lb) for lb in labels}
                for v in ENTRY_ROWS:
                    flagged[v] |= {(sh.subject_id, p) for p in predicted_done(cands, v) & labels}
        rows: dict[str, Any] = {}
        for v in ENTRY_ROWS:
            pos_u = flagged[v] & universe
            rows[v] = {
                "flagged": len(pos_u),
                "precision": round(len(pos_u & hires) / len(pos_u), 3) if pos_u else 0.0,
                "coverage": {t: coverage(flagged[v], hires, universe, t) for t in TOLERANCES},
                "jan_flagged": len({k for k in pos_u if k[1].endswith("-01")}),
            }
        out["on" if on else "off"] = {
            "months": len(universe), "hires": len(hires),
            "jan_hires": sorted(p for _, p in hires if p.endswith("-01")),
            "rows": rows,
        }
    _set_flag("off")
    return out


def render_md(result: dict[str, Any]) -> str:
    """측정 결과 표(마크다운)."""
    lines = ["## ① 달력 범위(명식 무관)", ""]
    for y, e in result["extent"].items():
        lines.append(
            f"- {y}년 {e['days']}일 가운데 관할 세운이 달라지는 날 {e['sewoon_changed']}일, "
            f"관할 월운이 달라지는 날 {e['wolwoon_changed']}일"
        )
    s = result["synthetic"]
    jm = s["jan_month"]
    lines += [
        "",
        f"## ② 모의 명식 {s['charts']}건",
        "",
        f"- 丑월 한 달(YEAR 갈래): 후보가 달라진 명식 {jm['changed']}/{jm['n']}, 사건 종류 집합이 "
        f"달라진 명식 "
        f"{jm['set_changed']}, 1위 사건이 달라진 명식 {jm['top_changed']}, 최대 점수 차 "
        f"중앙값 {jm['max_delta_median']}·90% {jm['max_delta_p90']}·최대 {jm['max_delta_max']}",
        f"- 丑월 밖 11달에서 달라진 달 수: {s['other_months_changed']}(0 이어야 한다)",
        f"- MONTH 갈래만 켰을 때 월 단위에서 달라진 달 수: {s['month_flag_changed_months']}"
        "(0 이어야 한다 — 일 단위 전용)",
        "",
        "| 구간 · 켠 갈래 | 대상 날 | 후보가 달라진 날 | 사건 종류 달라진 날 | 1위 달라진 날 "
        "| 최대 점수 차(중앙·90%·최대) |",
        "|---|---|---|---|---|---|",
    ]
    for name, d in s["days"].items():
        if not d.get("n"):
            continue
        lines.append(
            f"| {name} | {d['n']} | {d['changed']} | {d['set_changed']} | {d['top_changed']} "
            f"| {d['max_delta_median']}·{d['max_delta_p90']}·{d['max_delta_max']} |"
        )
    r = result["real"]
    lines += [
        "",
        f"## ③ 실사례 — 대상 {r['subjects']}명·{r['off']['months']}달·입사 {r['off']['hires']}건 "
        f"(丑월 입사 {r['off']['jan_hires']})",
        "",
        "칸 = 포함 건수/입사 건수 (우연 포함률)",
        "",
        "| 표지 | YEAR 갈래 | 표지 달 | 입사 달 정밀도 | 입사 달만 | 전월까지 | 전전월까지 "
        "| 丑월 표지 달 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for v in ENTRY_ROWS:
        for state in ("off", "on"):
            row = r[state]["rows"][v]
            cells = " | ".join(
                f"{row['coverage'][t]['hits']}/{row['coverage'][t]['n']} "
                f"(우연 {row['coverage'][t]['base']:.0%})"
                for t in TOLERANCES
            )
            lines.append(
                f"| {v} | {state.upper()} | {row['flagged']} | {row['precision']:.1%} | {cells} "
                f"| {row['jan_flagged']} |"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--md", type=Path, default=None)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--charts", type=int, default=60, help="모의 명식 수")
    ap.add_argument("--ref-year", type=int, default=2026, help="모의 명식 기준 연도")
    args = ap.parse_args(argv)
    _load_env()
    dsn = os.environ.get("SAJU_V2_DATABASE_URL")
    if not dsn:
        print("SAJU_V2_DATABASE_URL 이 없다", file=sys.stderr)
        return 2
    engine = EventEngineV2(_BACKEND / "dictionaries")
    result = {
        "extent": {str(y): calendar_extent(y) for y in (2026, 2027)},
        "synthetic": synthetic(engine, _sample_births(args.charts), args.ref_year),
        "real": real_cases(engine, dsn),
    }
    md = render_md(result)
    print(md)
    if args.md:
        args.md.write_text(md + "\n", encoding="utf-8")
    if args.json:
        args.json.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
