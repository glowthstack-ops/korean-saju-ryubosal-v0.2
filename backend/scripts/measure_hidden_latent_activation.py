#!/usr/bin/env python3
"""지장간 잠복 십성 발현(투출·자극)의 실사례 적중 측정 (2026-11-10).

데굴님 "지금 진행할 수 있는 항목 아닌가". 질문: 잠복 십성이 운에서 드러나는 해(투출·자극)에 그
십성 영역의 사건이 **실제로 더 자주** 일어났는가.
점수 규칙을 만들기 전에 신호 자체의 변별력을 본다 — 판정은 하지 않고 수치만 낸다(점수 규칙은
실사례 적중률로 켜고 끈다, 2026-10-15). 엔진·사전·DB 를 바꾸지 않는다.

모집단 ① 원장(`subject_life_events`): confirmed / not_happened 행 전부. 행의 사건 키 → 도메인
(`EVENT_DOMAIN`) → 그 도메인의 십성군(`hidden_latent_activation.domain_groups`) 가운데 **그 대상의
원국에서 잠복인 군**이 있을 때만 표본이 된다. 적중률 = 표지가 켜진 행 중 confirmed 비율,
기저율 = 표본 전체의 confirmed 비율, lift = 적중률 / 기저율.

모집단 ② 사례집(`comparison_casebook`, 85사례 180명식): 시점이 있는 결과(when)의 연도와 그 명식의
나머지 연도(10~70세)를 비교한다. 사건 연도의 표지 비율 vs 같은 명식의 다른 연도 표지 비율.

표지(운 기둥 하나 기준): 세운 투출 / 세운 자극 / 세운 뚜렷(둘 다) / 대운 투출 / 대운 자극 /
월운 투출(원장 월 라벨 행만).

사용법:
    python scripts/measure_hidden_latent_activation.py [--json 경로] [--md 경로] [--no-ledger]
DSN 은 SAJU_V2_DATABASE_URL(루트 .env 자동 로드). DB 에 쓰지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND / "apps" / "api"))
sys.path.insert(0, str(_BACKEND / "scripts"))

from saju_api.services.manse_service import calculate  # noqa: E402
from saju_engines.hidden_latent_activation import (  # noqa: E402
    HiddenLatent,
    LuckUnit,
    domain_groups,
    judge,
    natal_hidden_latents,
    sewoon_year_of,
)
from saju_engines.simple_reading import month_ganji_of_year  # noqa: E402
from saju_manse_core.calendar.sexagenary_cycle import year_ganzi  # noqa: E402
from saju_shared_types.event_taxonomy_v2 import EVENT_DOMAIN  # noqa: E402
from saju_shared_types.manse_result import ManseV2Result  # noqa: E402

_ENV_PATHS = [_BACKEND.parent / ".env", _BACKEND / ".env"]
_CASES = _BACKEND / "tests" / "fixtures" / "comparison_casebook" / "cases.jsonl"
_REPLAY = _BACKEND.parent / "var" / "casebook_replay" / "subjects.jsonl"
#: 표지 이름(출력 순서).
FLAGS: tuple[str, ...] = (
    "세운 투출", "세운 자극", "세운 뚜렷", "대운 투출", "대운 자극", "투출(대운·세운)", "월운 투출",
)
#: 원장에 있지만 `EVENT_DOMAIN` 에 없는 키의 도메인(원장 전용 키).
_EXTRA_DOMAIN: dict[str, str] = {"resignation": "career"}
#: 사례집 결과 도메인 → 질문 도메인(십성군 표의 키). 그 밖(health·death·legal …)은 대상 아님.
_CASEBOOK_DOMAIN: dict[str, str] = {
    "career": "career", "wealth": "wealth", "education": "education", "marriage": "relationship",
}


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


def _daewoon_unit(result: ManseV2Result, year: int) -> LuckUnit | None:
    """그 해 7/1 을 덮는 대운 기둥."""
    lc = result.luck_cycles
    if lc is None:
        return None
    d = date(year, 7, 1)
    for dw in lc.daewoon_table:
        if dw.approx_start_date <= d <= dw.approx_end_date:
            return LuckUnit("daewoon", f"{dw.approx_start_date.year}~", dw.ganji)
    return None


def _month_unit(label: str) -> LuckUnit | None:
    """'YYYY-MM' 절기월 라벨 → 월운 기둥(월건법 달력 계산)."""
    year = sewoon_year_of(label)
    if year is None or len(label) != 7:
        return None
    y_stem, _ = year_ganzi(year)
    for stem, branch, month_no in month_ganji_of_year(y_stem):
        if month_no == int(label[5:7]):
            return LuckUnit("wolwoon", label, f"{stem.value}{branch.value}")
    return None


def year_flags(
    result: ManseV2Result, latents: list[HiddenLatent], year: int, month_label: str | None = None,
) -> dict[str, bool]:
    """잠복 글자 목록(같은 영역) × 그 해 운 기둥 → 표지별 성립 여부(한 글자라도 성립하면 참)."""
    y_stem, y_branch = year_ganzi(year)
    sew = LuckUnit("sewoon", str(year), f"{y_stem.value}{y_branch.value}")
    dae = _daewoon_unit(result, year)
    mon = _month_unit(month_label) if month_label else None
    out = dict.fromkeys(FLAGS, False)
    for lt in latents:
        s = judge(lt, sew)
        if s is not None:
            out["세운 투출"] |= s.emerge
            out["세운 자극"] |= s.stir is not None
            out["세운 뚜렷"] |= s.grade == "clear"
        d = judge(lt, dae) if dae is not None else None
        if d is not None:
            out["대운 투출"] |= d.emerge
            out["대운 자극"] |= d.stir is not None
        m = judge(lt, mon) if mon is not None else None
        if m is not None:
            out["월운 투출"] |= m.emerge
    out["투출(대운·세운)"] = out["세운 투출"] or out["대운 투출"]
    return out


def _relevant_latents(result: ManseV2Result, domain: str, primary_only: bool) -> list[HiddenLatent]:
    groups = domain_groups(result, domain)
    if not groups:
        return []
    wanted = groups[:1] if primary_only else groups
    return [lt for lt in natal_hidden_latents(result) if lt.group in wanted]


# ── ① 원장 ────────────────────────────────────────────────────────────────────


def measure_ledger(dsn: str, primary_only: bool) -> dict[str, Any]:
    """원장 행 단위 2×2 — 표지 × (confirmed / not_happened)."""
    import psycopg

    from saju_engines.subject_store import SubjectStore

    sql = (
        "SELECT subject_id, event_key, period, outcome FROM subject_life_events "
        "WHERE outcome IN ('confirmed','not_happened') ORDER BY subject_id, period"
    )
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(sql).fetchall()
    store = SubjectStore()
    domain_of = {**{str(k.value): v for k, v in EVENT_DOMAIN.items()}, **_EXTRA_DOMAIN}
    charts: dict[str, ManseV2Result | None] = {}
    n = pos = 0
    flagged: dict[str, int] = defaultdict(int)
    hit: dict[str, int] = defaultdict(int)
    month_n = month_pos = 0
    subjects: set[str] = set()
    by_domain: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # 도메인 → [표본, confirmed]
    detail: list[dict[str, Any]] = []
    # 대상-도메인-연도 단위(한 해에 사건 키가 여럿이면 행 단위는 같은 해를 여러 번 센다) —
    # 값 = [그 해 confirmed 가 하나라도 있는가, 표지별 성립].
    sy: dict[tuple[str, str, int], list[Any]] = {}
    for sid, event_key, period, outcome in rows:
        domain = domain_of.get(str(event_key))
        if domain is None:
            continue
        if sid not in charts:
            rec = store.get(sid)
            charts[sid] = calculate(rec.birth) if rec is not None else None
        chart = charts[sid]
        if chart is None:
            continue
        latents = _relevant_latents(chart, str(domain), primary_only)
        year = sewoon_year_of(str(period))
        if not latents or year is None:
            continue
        month_label = str(period) if len(str(period)) == 7 else None
        flags = year_flags(chart, latents, year, month_label)
        confirmed = outcome == "confirmed"
        n += 1
        pos += confirmed
        subjects.add(sid)
        by_domain[str(domain)][0] += 1
        by_domain[str(domain)][1] += confirmed
        cell = sy.setdefault((sid, str(domain), year), [False, flags])
        cell[0] = cell[0] or confirmed
        if month_label:
            month_n += 1
            month_pos += confirmed
        for f in FLAGS:
            if f == "월운 투출" and not month_label:
                continue
            if flags[f]:
                flagged[f] += 1
                hit[f] += confirmed
        if confirmed:
            detail.append({
                "subject": sid[:8], "event": str(event_key), "period": str(period),
                "latent": "·".join(f"{lt.stem}({lt.ten_god})" for lt in latents),
                "flags": [f for f in FLAGS if flags[f]],
            })
    out_flags = {}
    for f in FLAGS:
        base_n, base_pos = (month_n, month_pos) if f == "월운 투출" else (n, pos)
        base = base_pos / base_n if base_n else 0.0
        prec = hit[f] / flagged[f] if flagged[f] else 0.0
        out_flags[f] = {
            "flagged": flagged[f], "hits": hit[f], "precision": round(prec, 3),
            "base_rate": round(base, 3),
            "lift": round(prec / base, 2) if base and flagged[f] else None,
            "recall": round(hit[f] / base_pos, 3) if base_pos else 0.0,
        }
    sy_n, sy_pos = len(sy), sum(1 for v in sy.values() if v[0])
    sy_base = sy_pos / sy_n if sy_n else 0.0
    sy_flags = {}
    for f in FLAGS[:-1]:
        on = [(k, v) for k, v in sy.items() if v[1][f]]
        hits = sum(1 for _, v in on if v[0])
        prec = hits / len(on) if on else 0.0
        sy_flags[f] = {
            "flagged": len(on), "hits": hits, "precision": round(prec, 3),
            "base_rate": round(sy_base, 3),
            "lift": round(prec / sy_base, 2) if sy_base and on else None,
            "subjects": len({k[0] for k, _ in on}),
            "years": sorted(f"{k[0][:6]}:{k[2]}{'+' if v[0] else '-'}" for k, v in on),
        }
    return {
        "rows": n, "confirmed": pos, "subjects": len(subjects),
        "by_domain": {k: {"rows": v[0], "confirmed": v[1]} for k, v in sorted(by_domain.items())},
        "flags": out_flags, "confirmed_detail": detail,
        "subject_years": {"n": sy_n, "positive": sy_pos, "flags": sy_flags},
    }


# ── ② 사례집 ──────────────────────────────────────────────────────────────────


def measure_casebook(primary_only: bool) -> dict[str, Any]:
    """시점 있는 결과의 연도 vs 같은 명식의 나머지 연도(10~70세) 표지 비율."""
    from casebook_replay import _calc_matching  # scripts/ 형제 모듈
    from casebook_report import _years_for_when

    cases = [json.loads(ln) for ln in _CASES.read_text("utf-8").splitlines() if ln.strip()]
    subs: dict[tuple[str, str], dict] = {}
    for ln in _REPLAY.read_text("utf-8").splitlines():
        if ln.strip():
            r = json.loads(ln)
            subs[(r["case_id"], r["key"])] = r
    ev_years = 0
    base_years = 0
    ev_hit: dict[str, int] = defaultdict(int)
    base_hit: dict[str, int] = defaultdict(int)
    detail: list[dict[str, Any]] = []
    used_subjects: set[tuple[str, str]] = set()
    timed_total = 0
    for c in cases:
        for s in c["subjects"]:
            sub = subs.get((c["case_id"], s["key"]))
            timed = [o for o in s.get("outcomes") or [] if o.get("when")]
            timed_total += len(timed)
            if not timed or sub is None or not sub.get("date_used") or not sub.get("time_used"):
                continue
            found = _calc_matching(sub["date_used"], sub["time_used"], s["gender"], s["pillars"])
            if found is None:
                continue
            chart = found[0]
            birth_year = int(sub["date_used"][:4])
            life = list(range(birth_year + 9, birth_year + 70))  # 10~70세
            for o in timed:
                domain = _CASEBOOK_DOMAIN.get(o["domain"])
                if domain is None:
                    continue
                latents = _relevant_latents(chart, domain, primary_only)
                years, basis = _years_for_when(sub, o["when"])
                years = [y for y in years if y in life]
                if not latents or not years:
                    continue
                used_subjects.add((c["case_id"], s["key"]))
                ev = set(years)
                row_flags: dict[str, int] = defaultdict(int)
                for y in life:
                    fl = year_flags(chart, latents, y)
                    for f in FLAGS[:-1]:
                        if y in ev:
                            ev_hit[f] += fl[f]
                            row_flags[f] += fl[f]
                        else:
                            base_hit[f] += fl[f]
                ev_years += len(ev)
                base_years += len(life) - len(ev)
                detail.append({
                    "case": c["case_id"], "key": s["key"], "domain": o["domain"],
                    "polarity": o["polarity"], "when": basis, "years": len(ev),
                    "latent": "·".join(f"{lt.stem}({lt.ten_god})" for lt in latents),
                    "flag_years": {f: n for f, n in row_flags.items() if n},
                    "text": o["text"][:40],
                })
    flags = {}
    for f in FLAGS[:-1]:
        er = ev_hit[f] / ev_years if ev_years else 0.0
        br = base_hit[f] / base_years if base_years else 0.0
        flags[f] = {
            "event_years_flagged": ev_hit[f], "event_rate": round(er, 3),
            "other_years_flagged": base_hit[f], "other_rate": round(br, 3),
            "ratio": round(er / br, 2) if br else None,
        }
    return {
        "timed_outcomes_total": timed_total, "outcomes_used": len(detail),
        "subjects_used": len(used_subjects), "event_years": ev_years, "other_years": base_years,
        "flags": flags, "detail": detail,
    }


def render_md(res: dict[str, Any]) -> str:
    """사람이 읽는 요약."""
    lines = ["# 지장간 잠복 십성 발현 — 실사례 적중 측정", ""]
    for scope in ("primary", "all"):
        r = res[scope]
        scope_ko = "도메인 대표 십성군만" if scope == "primary" else "도메인 십성군 전부"
        lines += [f"## 범위: {scope_ko}", ""]
        led = r.get("ledger")
        if led:
            lines += [
                f"### ① 원장 — 표본 {led['rows']}행(confirmed {led['confirmed']}), 대상 "
                f"{led['subjects']}명, 도메인 {json.dumps(led['by_domain'], ensure_ascii=False)}",
                "", "| 표지 | 켜진 행 | 그중 confirmed | 적중률 | 기저율 | lift | 재현율 |",
                "|---|---|---|---|---|---|---|",
            ]
            for f, v in led["flags"].items():
                lines.append(
                    f"| {f} | {v['flagged']} | {v['hits']} | {v['precision']} | {v['base_rate']} | "
                    f"{v['lift']} | {v['recall']} |"
                )
            sy = led["subject_years"]
            lines += [
                "",
                f"대상-도메인-연도 단위(한 해 = 1표본): {sy['n']}해 중 사건 있던 해 "
                f"{sy['positive']}",
                "", "| 표지 | 켜진 해 | 그중 사건 해 | 적중률 | 기저율 | lift | 대상 수 |",
                "|---|---|---|---|---|---|---|",
            ]
            for f, v in sy["flags"].items():
                lines.append(
                    f"| {f} | {v['flagged']} | {v['hits']} | {v['precision']} | {v['base_rate']} | "
                    f"{v['lift']} | {v['subjects']} |"
                )
            lines.append("")
        cb = r["casebook"]
        lines += [
            f"### ② 사례집 — 시점 결과 {cb['timed_outcomes_total']}건 중 표본 "
            f"{cb['outcomes_used']}건({cb['subjects_used']}명식), "
            f"사건 연도 {cb['event_years']}년 / 나머지 {cb['other_years']}년",
            "",
            "| 표지 | 사건 연도 중 | 비율 | 나머지 연도 중 | 비율 | 배수 |",
            "|---|---|---|---|---|---|",
        ]
        for f, v in cb["flags"].items():
            lines.append(
                f"| {f} | {v['event_years_flagged']} | {v['event_rate']} | "
                f"{v['other_years_flagged']} | {v['other_rate']} | {v['ratio']} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--md", default="")
    ap.add_argument("--no-ledger", action="store_true", help="원장(DB) 측정을 건너뛴다")
    args = ap.parse_args()
    _load_env()
    dsn = os.environ.get("SAJU_V2_DATABASE_URL", "")
    res: dict[str, Any] = {}
    for scope, primary in (("primary", True), ("all", False)):
        res[scope] = {"casebook": measure_casebook(primary)}
        if dsn and not args.no_ledger:
            res[scope]["ledger"] = measure_ledger(dsn, primary)
    md = render_md(res)
    if args.json:
        Path(args.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.md:
        Path(args.md).write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
