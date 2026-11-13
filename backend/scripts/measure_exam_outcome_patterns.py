"""시험·합격 결과 보정(exam_outcome_patterns) 성립 범위의 실사례 측정 — 판정 변경 전 대조.

배경(2026-11-11 외부 '합격운' 글 대조): 현행 `ExamOutcomeModifier` 는 대운·세운·월운 **어느 층에
있든** 십성 두 개가 있으면 패턴 성립으로 친다(스택 전체 집합 매칭). 그래서 ① 정관+편인 쌍이
사전에 없고 ② 세운의 상관과 월운의 정관이 '상관견관'으로 잡혀, 같은 달에 甲 일간은 +0.45·乙 일간은
−0.50 처럼 부호가 갈린다. 이 스크립트는 성립 범위를 바꾼 변형들을 **실제 입사·합격 기록**에 대조해
수치만 낸다. 엔진·사전·DB 는 바꾸지 않는다(읽기 전용).

변형:
- current        : 현행(스택 전체 집합 매칭, 현행 사전)
- +jg_py         : 현행 + 정관·편인 합격 쌍(가정값 +0.20)
- target         : 쌍의 십성 가운데 하나 이상이 **채점 대상 기둥**(월 단위=월운, 연 단위=세운)에
                   있을 때만
- target+jg_py   : target + 정관·편인 쌍
- pillar+jg_py   : 쌍의 두 십성이 채점 대상 기둥 **한 기둥 안**에 함께 있을 때만(글의 규칙)
                   + 정관·편인 쌍
- group_pillar   : (참고) 채점 대상 기둥의 천간·지지 본기가 관성군+인성군 — 정편 구분 없는
                   글의 원 규칙

표지: 변형별 보정 합(상한 적용)이 양수면 '합격 기류', 음수면 '불합격 위험'.

측정 중심(데굴님 2026-11-11): **예측 안에 실제가 얼마나 들어오는가(포함률)**. 합격 발표 → 처우
결정 → 입사 사이에 간격이 있으므로 입사 달·전월·전전월 가운데 한 달이라도 표지가 붙으면
포함으로 센다.
표지가 많이 붙는 변형일수록 우연히도 포함되므로, 같은 창을 **모든 달**에 적용한 우연 포함률과
그 대비 배수·이항 꼬리 확률(우연만으로 이만큼 이상 포함될 확률)을 함께 낸다. 참고 행으로 엔진의
진입 시기 표지(`measure_entry_slot_modes.predicted_done` 의 trigger95 = 현행 '성사 달' 기준, 그리고
trigger90/85/70·top3)도 같은 방식으로 잰다.

모집단:
① 월 단위 — 확정 입사(`job_gain`·confirmed·'YYYY-MM')가 있는 대상의 첫 입사 해~마지막 입사 해
   모든 달.
   입사 달(0)·한 달 전(−1)·두 달 전(−2)·그 석 달 창(0~−2)에 표지가 붙었는가. 통지가 입사보다
   한두 달 앞선다는 이력 관찰(EMPLOYMENT_HISTORY_CALIBRATION.md) 때문에 창을 함께 낸다.
② 연 단위 — 원장 `job_gain`·`education_admission` 의 confirmed / not_happened 를 대상-사건-연도로
   묶어(같은 해의 행 중복 제거) 표지 × 결과 2×2.
③ 사례집 — 시점이 있는 시험 합격 결과(연 단위).

사용법:
    python scripts/measure_exam_outcome_patterns.py [--md 경로] [--json 경로] [--no-engine-check]
DSN 은 SAJU_V2_DATABASE_URL(루트 .env 자동 로드). 출력에 이름·회사명은 찍지 않는다.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND / "apps" / "api"))
sys.path.insert(0, str(_BACKEND / "scripts"))

from measure_entry_slot_modes import predicted_done  # noqa: E402
from saju_api.services.manse_service import calculate  # noqa: E402
from saju_engines.event_engine_v2 import EventEngineV2, _StackIndex  # noqa: E402
from saju_engines.hidden_latent_activation import sewoon_year_of  # noqa: E402
from saju_engines.subject_store import SubjectStore  # noqa: E402
from saju_engines.ten_god_brancher import TEN_GOD_KO_TO_KEY  # noqa: E402
from saju_shared_types.event_engine import LuckLayer, TenGod  # noqa: E402
from saju_shared_types.ganji_calendar import GanjiLevel  # noqa: E402
from saju_shared_types.manse_result import ManseV2Result  # noqa: E402

_ENV_PATHS = [_BACKEND.parent / ".env", _BACKEND / ".env"]
_DICT = _BACKEND / "dictionaries" / "event_engine" / "exam_outcome_patterns.json"
_CASES = _BACKEND / "tests" / "fixtures" / "comparison_casebook" / "cases.jsonl"
VARIANTS: tuple[str, ...] = (
    "current", "+jg_py", "target", "target+jg_py", "pillar+jg_py", "group_pillar",
)
#: 정관·편인 합격 쌍의 가정 보정값 — 살인상생(+0.25)과 편관·편인(+0.15) 사이.
JG_PY_DELTA = 0.2
_OFFICER = frozenset({TenGod("ZHENGGUAN"), TenGod("QISHA")})
_RESOURCE = frozenset({TenGod("ZHENGYIN"), TenGod("PIANYIN")})


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


@dataclass(frozen=True)
class Rule:
    """패턴 1건 — 십성 쌍과 보정값."""

    id: str
    gods: frozenset[TenGod]
    delta: float


def load_rules() -> tuple[list[Rule], float]:
    """현행 사전의 합·불 패턴과 누적 상한."""
    data = json.loads(_DICT.read_text(encoding="utf-8"))
    rules = [
        Rule(p["id"], frozenset(TenGod(g) for g in p["ten_gods"]), float(p["fav_delta"]))
        for p in (*data["pass_patterns"], *data["fail_patterns"])
    ]
    return rules, abs(float(data["fav_adj_cap"]))


_JG_PY_RULE = Rule(
    "EXAM_PASS_관인상생_정관편인", frozenset({TenGod("ZHENGGUAN"), TenGod("PIANYIN")}), JG_PY_DELTA,
)


def layer_gods(stack: list[tuple[LuckLayer, Any]]) -> dict[LuckLayer, frozenset[TenGod]]:
    """스택의 층별 십성 집합(천간·지지 본기) — 엔진의 신호 수집과 같은 재료."""
    out: dict[LuckLayer, frozenset[TenGod]] = {}
    for layer, pillar in stack:
        gods = {
            g for g in (
                TEN_GOD_KO_TO_KEY.get(pillar.stem_ten_god),
                TEN_GOD_KO_TO_KEY.get(pillar.branch_ten_god),
            ) if g is not None
        }
        out[layer] = frozenset(gods)
    return out


def variant_delta(
    variant: str, by_layer: dict[LuckLayer, frozenset[TenGod]], target: LuckLayer,
    rules: list[Rule], cap: float,
) -> tuple[float, list[str]]:
    """변형별 보정 합(상한 적용)과 성립 패턴 id."""
    present = frozenset().union(*by_layer.values()) if by_layer else frozenset()
    tgt = by_layer.get(target, frozenset())
    if variant == "group_pillar":
        hit = bool(tgt & _OFFICER) and bool(tgt & _RESOURCE)
        return (JG_PY_DELTA if hit else 0.0), (["GROUP_관인_한기둥"] if hit else [])
    pool = [*rules, _JG_PY_RULE] if variant.endswith("jg_py") else rules
    hits: list[Rule] = []
    for r in pool:
        if variant.startswith("pillar"):
            ok = r.gods <= tgt
        elif variant.startswith("target"):
            ok = r.gods <= present and bool(r.gods & tgt)
        else:
            ok = r.gods <= present
        if ok:
            hits.append(r)
    total = sum(r.delta for r in hits)
    return max(-cap, min(cap, total)), [r.id for r in hits]


def _shift(label: str, k: int) -> str:
    """'YYYY-MM' 라벨을 k달 옮긴다."""
    idx = int(label[:4]) * 12 + int(label[5:7]) - 1 + k
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def _label_year(period: str) -> int:
    """절기월 라벨이 들어 있는 만세력 기준 연도(1월 라벨은 전년 목록)."""
    y, m = int(period[:4]), int(period[5:7])
    return y - 1 if m == 1 else y


@dataclass
class MonthAcc:
    """월 단위 변형 1개의 누적 — 표지 달은 모집단 앞 한 해(허용 창 계산용)까지 담는다."""

    pos: set[tuple[str, str]] = field(default_factory=set)
    neg: set[tuple[str, str]] = field(default_factory=set)


#: 엔진 진입 시기 표지 참고 행 — `measure_entry_slot_modes` 의 변형 이름(trigger95 = 현행 기준).
ENTRY_ROWS: tuple[str, ...] = ("trigger95", "trigger90", "trigger85", "trigger70", "top3")
#: 허용 창 — 입사 달만 / 전월까지 / 전전월까지.
TOLERANCES: tuple[int, ...] = (0, 1, 2)


def _binom_tail(k: int, n: int, p: float) -> float:
    """이항 꼬리 확률 P(X ≥ k | n, p) — 우연만으로 k건 이상 포함될 확률."""
    if n == 0 or p <= 0.0:
        return 1.0 if k == 0 else 0.0
    if p >= 1.0:
        return 1.0
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


def coverage(
    flagged: set[tuple[str, str]], targets: set[tuple[str, str]],
    universe: set[tuple[str, str]], tolerance: int,
) -> dict[str, Any]:
    """허용 창 포함률 — 대상 달·그 앞 tolerance 달 가운데 한 달이라도 표지가 있는 비율.

    Args:
        flagged: 표지가 붙은 (대상, 달) 집합(모집단 앞 달 포함).
        targets: 실제 사건 (대상, 달).
        universe: 우연 포함률을 재는 모든 (대상, 달).
        tolerance: 앞으로 허용하는 달 수(0 = 그 달만).
    """
    def covered(key: tuple[str, str]) -> bool:
        return any((key[0], _shift(key[1], -k)) in flagged for k in range(tolerance + 1))

    hit = sum(covered(t) for t in targets)
    base = sum(covered(u) for u in universe) / len(universe) if universe else 0.0
    rate = hit / len(targets) if targets else 0.0
    return {
        "hits": hit, "n": len(targets), "rate": round(rate, 3), "base": round(base, 3),
        "lift": round(rate / base, 2) if base else None,
        "p_tail": round(_binom_tail(hit, len(targets), base), 3),
    }


def measure_months(
    dsn: str, rules: list[Rule], cap: float, engine: EventEngineV2 | None,
) -> dict[str, Any]:
    """모집단 ① — 입사 달·앞선 달에 표지가 붙었는가(변형별)."""
    import psycopg

    sql = (
        "SELECT subject_id, period FROM subject_life_events "
        "WHERE event_key='job_gain' AND outcome='confirmed' AND length(period)=7 "
        "ORDER BY subject_id, period"
    )
    hires: dict[str, list[str]] = defaultdict(list)
    with psycopg.connect(dsn) as conn:
        for sid, period in conn.execute(sql).fetchall():
            if period not in hires[sid]:
                hires[sid].append(period)
    store = SubjectStore()
    acc = {v: MonthAcc() for v in VARIANTS}
    score_acc = {name: MonthAcc() for name in ENTRY_ROWS}
    universe: set[tuple[str, str]] = set()
    seen: set[tuple[str, str]] = set()
    hire_keys: set[tuple[str, str]] = set()
    mismatches: list[str] = []
    checked = 0
    for sid, periods in hires.items():
        rec = store.get(sid)
        if rec is None:
            continue
        hire_keys |= {(sid, p) for p in periods}
        label_years = [_label_year(p) for p in periods]
        # 첫 입사 해의 앞 한 해도 표지만 계산한다 — 연초 입사의 전월·전전월 창이 잘리지 않게.
        years = range(min(label_years) - 1, max(label_years) + 1)
        for y in years:
            in_universe = y >= min(label_years)
            chart = calculate(rec.birth.model_copy(update={"reference_date": date(y, 7, 1)}))
            lc = chart.luck_cycles
            if lc is None:
                continue
            idx = _StackIndex(chart)
            engine_codes: dict[str, set[str]] = defaultdict(set)
            entry_done: dict[str, set[str]] = {}
            if engine is not None:
                cands = engine.score(chart, levels={GanjiLevel.MONTH})
                for c in cands:
                    if str(c.event_key) == "job_gain":
                        engine_codes[str(c.period)] |= {
                            r for r in c.reason_codes if r.startswith("EXAM_")
                        }
                entry_done = {name: predicted_done(cands, name) for name in ENTRY_ROWS}
            for p in lc.monthly_luck:
                key = (sid, p.label)
                if key in seen:
                    continue
                seen.add(key)
                if in_universe:
                    universe.add(key)
                for name, done in entry_done.items():
                    if p.label in done:
                        score_acc[name].pos.add(key)
                by_layer = layer_gods(idx.stack_for(GanjiLevel.MONTH, p.label, p))
                for v in VARIANTS:
                    delta, ids = variant_delta(v, by_layer, LuckLayer.WOLWOON, rules, cap)
                    if delta > 0:
                        acc[v].pos.add(key)
                    elif delta < 0:
                        acc[v].neg.add(key)
                    # 재구현 검증 — 엔진이 job_gain 후보를 낸 달의 EXAM_ 사유와 현행 변형이 같은가.
                    if (
                        v == "current" and engine is not None and in_universe
                        and p.label in engine_codes
                    ):
                        checked += 1
                        expected = (
                            {i for i in ids if i.startswith("EXAM_PASS")} if delta > 0 else set()
                        )
                        if expected != engine_codes[p.label]:
                            mismatches.append(f"{sid[:6]} {p.label}")
    windows: dict[str, set[tuple[str, str]]] = {
        "입사 달": hire_keys,
        "한 달 전": {(s, _shift(p, -1)) for s, p in hire_keys},
        "두 달 전": {(s, _shift(p, -2)) for s, p in hire_keys},
    }
    windows["석 달 창(0~-2)"] = set().union(*windows.values())
    for name in list(windows):
        windows[name] &= universe
    n = len(universe)
    out: dict[str, Any] = {
        "subjects": len(hires), "months": n, "hires": len(hire_keys),
        "per_subject": sorted((len(v) for v in hires.values()), reverse=True),
        "engine_check": {"checked": checked, "mismatch": mismatches[:10]},
        "variants": {},
    }
    for v in VARIANTS:
        a = acc[v]
        pos_u, neg_u = a.pos & universe, a.neg & universe
        row: dict[str, Any] = {
            "pos_months": len(pos_u), "neg_months": len(neg_u),
            "pos_rate": round(len(pos_u) / n, 3) if n else 0.0,
            "neg_rate": round(len(neg_u) / n, 3) if n else 0.0,
        }
        for name, keys in windows.items():
            base = len(keys) / n if n else 0.0
            hit = len(pos_u & keys)
            prec = hit / len(pos_u) if pos_u else 0.0
            row[name] = {
                "n": len(keys), "pos_hits": hit,
                "pos_share": round(hit / len(keys), 3) if keys else 0.0,
                "precision": round(prec, 3),
                "lift": round(prec / base, 2) if base and pos_u else None,
                "neg_hits": len(neg_u & keys),
                "neg_share": round(len(neg_u & keys) / len(keys), 3) if keys else 0.0,
            }
        out["variants"][v] = row
    # 허용 창 포함률(측정 중심) — 합격 기류 표지·불합격 위험 표지·엔진 사건 점수 참고 행.
    cov: dict[str, Any] = {}
    for v in VARIANTS:
        cov[v] = {
            "pos": {t: coverage(acc[v].pos, hire_keys, universe, t) for t in TOLERANCES},
            "neg": {t: coverage(acc[v].neg, hire_keys, universe, t) for t in TOLERANCES},
        }
    if engine is not None:
        for name in ENTRY_ROWS:
            cov[f"진입 표지 {name}"] = {
                "pos": {
                    t: coverage(score_acc[name].pos, hire_keys, universe, t) for t in TOLERANCES
                },
            }
    out["coverage"] = cov
    return out


def measure_years(dsn: str, rules: list[Rule], cap: float) -> dict[str, Any]:
    """모집단 ② — 원장 연 단위 2×2(대상-사건-연도 중복 제거)."""
    import psycopg

    sql = (
        "SELECT subject_id, event_key, period, outcome FROM subject_life_events "
        "WHERE event_key IN ('job_gain','education_admission') "
        "AND outcome IN ('confirmed','not_happened') ORDER BY subject_id, period"
    )
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(sql).fetchall()
    cells: dict[tuple[str, str, int], bool] = {}
    for sid, ek, period, outcome in rows:
        year = sewoon_year_of(str(period))
        if year is None:
            continue
        key = (sid, str(ek), year)
        cells[key] = cells.get(key, False) or outcome == "confirmed"
    store = SubjectStore()
    charts: dict[tuple[str, int], ManseV2Result | None] = {}
    table = {v: {"confirmed": [0, 0, 0], "not_happened": [0, 0, 0]} for v in VARIANTS}
    used = 0
    subjects: set[str] = set()
    for (sid, _ek, year), confirmed in cells.items():
        if (sid, year) not in charts:
            rec = store.get(sid)
            charts[(sid, year)] = (
                calculate(rec.birth.model_copy(update={"reference_date": date(year, 7, 1)}))
                if rec is not None else None
            )
        chart = charts[(sid, year)]
        if chart is None or chart.luck_cycles is None:
            continue
        idx = _StackIndex(chart)
        pillar = idx.sewoon_by_year.get(year)
        if pillar is None:
            continue
        by_layer = layer_gods(idx.stack_for(GanjiLevel.YEAR, str(year), pillar))
        used += 1
        subjects.add(sid)
        for v in VARIANTS:
            delta, _ = variant_delta(v, by_layer, LuckLayer.SEWOON, rules, cap)
            cell = table[v]["confirmed" if confirmed else "not_happened"]
            cell[0] += 1
            cell[1] += delta > 0
            cell[2] += delta < 0
    return {"cells": used, "subjects": len(subjects), "table": table}


def measure_casebook(rules: list[Rule], cap: float) -> list[dict[str, Any]]:
    """모집단 ③ — 사례집의 시점 있는 시험 합격 결과(연 단위)."""
    from casebook_replay import _calc_matching

    out: list[dict[str, Any]] = []
    for line in _CASES.read_text(encoding="utf-8").splitlines():
        case = json.loads(line)
        for s in case["subjects"]:
            for o in s["outcomes"]:
                year = (o.get("when") or {}).get("year")
                if o["domain"] != "education" or not year or not s.get("date"):
                    continue
                found = _calc_matching(s["date"], s["time"], s["gender"], s["pillars"])
                if found is None or found[0].luck_cycles is None:
                    continue
                idx = _StackIndex(found[0])
                pillar = idx.sewoon_by_year.get(int(year))
                if pillar is None:
                    continue
                by_layer = layer_gods(idx.stack_for(GanjiLevel.YEAR, str(year), pillar))
                out.append({
                    "case": case["case_id"], "key": s["key"], "year": year, "text": o["text"],
                    "polarity": o["polarity"],
                    "deltas": {
                        v: variant_delta(v, by_layer, LuckLayer.SEWOON, rules, cap)[0]
                        for v in VARIANTS
                    },
                })
    return out


def render_md(result: dict[str, Any]) -> str:
    """측정 결과 표(마크다운)."""
    m = result["months"]
    lines = [
        f"## ① 월 단위 — 대상 {m['subjects']}명·{m['months']}달·입사 {m['hires']}건 "
        f"(대상별 입사 수 {m['per_subject']})",
        f"재구현 검증: 엔진 job_gain 후보 {m['engine_check']['checked']}달 대조, "
        f"불일치 {len(m['engine_check']['mismatch'])}건",
        "",
        "| 변형 | 합격 기류 달(비율) | 불합격 위험 달(비율) | 입사 달 +/− | 한 달 전 +/− "
        "| 두 달 전 +/− "
        "| 석 달 창 + 정밀도(배수) |",
        "|---|---|---|---|---|---|---|",
    ]
    for v in VARIANTS:
        r = m["variants"][v]

        def cell(name: str, r: dict[str, Any] = r) -> str:
            c = r[name]
            return f"{c['pos_hits']}/{c['n']} · {c['neg_hits']}/{c['n']}"

        w = r["석 달 창(0~-2)"]
        lift = f"×{w['lift']}" if w["lift"] is not None else "-"
        lines.append(
            f"| {v} | {r['pos_months']} ({r['pos_rate']:.0%}) "
            f"| {r['neg_months']} ({r['neg_rate']:.0%}) "
            f"| {cell('입사 달')} | {cell('한 달 전')} | {cell('두 달 전')} "
            f"| {w['pos_hits']}/{r['pos_months']} = {w['precision']:.1%} ({lift}) |"
        )
    lines += [
        "",
        "### ①-b 허용 창 포함률 — 실제 입사가 예측 안에 들어온 비율(우연 포함률 대비)",
        "",
        "칸 = 포함 건수/입사 건수 = 포함률 (우연 포함률, 배수, 우연만으로 이 이상일 확률)",
        "",
        "| 표지 | 입사 달만 | 전월까지 | 전전월까지 |",
        "|---|---|---|---|",
    ]

    def cov_cell(c: dict[str, Any]) -> str:
        lift = f"×{c['lift']}" if c["lift"] is not None else "-"
        return (
            f"{c['hits']}/{c['n']} = {c['rate']:.0%} "
            f"(우연 {c['base']:.0%}, {lift}, p={c['p_tail']})"
        )

    for name, sides in m["coverage"].items():
        for side, label in (("pos", "합격 기류"), ("neg", "불합격 위험")):
            if side not in sides:
                continue
            tag = name if name.startswith("진입 표지") else f"{name} · {label}"
            cells = " | ".join(cov_cell(sides[side][t]) for t in TOLERANCES)
            lines.append(f"| {tag} | {cells} |")
    y = result["years"]
    lines += [
        "",
        f"## ② 연 단위 — 대상-사건-연도 {y['cells']}칸·대상 {y['subjects']}명",
        "",
        "| 변형 | confirmed: 표본 / 합격 기류 / 불합격 위험 "
        "| not_happened: 표본 / 합격 기류 / 불합격 위험 |",
        "|---|---|---|",
    ]
    for v in VARIANTS:
        c, nh = y["table"][v]["confirmed"], y["table"][v]["not_happened"]
        lines.append(f"| {v} | {c[0]} / {c[1]} / {c[2]} | {nh[0]} / {nh[1]} / {nh[2]} |")
    lines += ["", "## ③ 사례집 시점 있는 시험 결과", ""]
    for row in result["casebook"]:
        deltas = " · ".join(f"{k} {d:+.2f}" for k, d in row["deltas"].items())
        lines.append(f"- {row['case']} {row['key']} {row['year']} {row['text']}: {deltas}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--md", type=Path, default=None)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--no-engine-check", action="store_true", help="엔진 재생 검증 생략(빠름)")
    args = ap.parse_args(argv)
    _load_env()
    dsn = os.environ.get("SAJU_V2_DATABASE_URL")
    if not dsn:
        print("SAJU_V2_DATABASE_URL 이 없다", file=sys.stderr)
        return 2
    rules, cap = load_rules()
    engine = None if args.no_engine_check else EventEngineV2(_BACKEND / "dictionaries")
    result = {
        "months": measure_months(dsn, rules, cap, engine),
        "years": measure_years(dsn, rules, cap),
        "casebook": measure_casebook(rules, cap),
    }
    md = render_md(result)
    print(md)
    if args.md:
        args.md.write_text(md + "\n", encoding="utf-8")
    if args.json:
        args.json.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
