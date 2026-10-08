#!/usr/bin/env python3
"""사례집 재생 결과(var/casebook_replay/subjects.jsonl) ↔ 문서 제공 이력 자동 대조 리포트.

지표
  A. 쌍 비교 순위: 같은 사례 안에서 결과 극성이 다른 명식 쌍에 대해 엔진 생애 지수가 같은 순서인가
  B. 시점 사건 극성: 제공된 연도/나이/대운의 세운·대운 luck_score 부호가 결과 극성과 같은가
     (C6-A 2026-10-08 데굴님 승인: 단일 연도(year/years/age)와 다년 구간(daewoon/age~age_max/
      ~age_max)을 분리해 센다. 다년 구간의 세운 평균은 60갑자 순환으로 0에 수렴해 부호를 지우므로
      세운 극성 지표는 단일 연도만, 다년 구간은 대운 극성 + 세운 부호 연도 비율(≥0.6)로 본다.
      합산 B/B'는 비교용으로 유지)
  C. 시점 도메인 히트: 그 시점 상위 이벤트/위험에 결과 도메인이 나타나는가(개인 기준선 대비)
  D. 구조 판정표: 신강약·격국·용희기구한 — 문서 해설과 사람이 대조

출력: var/casebook_replay/report.md, var/casebook_replay/metrics.json
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
_CASES = _BACKEND / "tests" / "fixtures" / "comparison_casebook" / "cases.jsonl"
_DIR = _BACKEND.parent / "var" / "casebook_replay"

DOMAIN_EVENTS: dict[str, set[str]] = {
    "wealth": {"wealth_change", "windfall", "business_start", "business_expansion"},
    "career": {"career_change", "job_gain", "promotion", "business_start", "public_exposure"},
    "education": {"education_admission", "education_completion"},
    "marriage": {"marriage_signal", "relationship_change", "new_relationship"},
    "relationship": {"relationship_change", "new_relationship"},
    "family": {"childbirth", "relationship_change"},
    "health": {"health_attention"},
    "death": {"health_attention"},
    "accident": {"health_attention"},
    "legal": {"legal_conflict"},
    "relocation": {"relocation"},
    "misc": set(),
}
DOMAIN_RISK_PREFIX: dict[str, tuple[str, ...]] = {
    "wealth": ("FIN_",), "career": ("CAR_",), "health": ("HLT_",), "death": ("HLT_",),
    "accident": ("HLT_",), "legal": ("LEG_",), "marriage": ("REL_",), "relationship": ("REL_",),
    "family": ("REL_",), "relocation": ("MOV_",), "education": ("SEL_",), "misc": (),
}

_STRUCT_HEADER = ("| 키 | 성별 | 명식 | 날짜(변형) | 신강약 | 격국 | 용/희/기/구/한 "
                  "| 대운방향·시작 | 생애지수 |")
_OUTCOME_HEADER = ("| 키 | 제공 이력 | 극성 | 시점 | 세운평균 | 대운 | 도메인 이벤트 히트 "
                   "| 위험밀도(기준) | 그 해 상위 이벤트 |")


def _row(cells: list[Any]) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _sep(n: int) -> str:
    return "|" + "---|" * n


def _load(subjects: Path | None = None) -> tuple[list[dict], dict[tuple[str, str], dict]]:
    case_lines = _CASES.read_text(encoding="utf-8").splitlines()
    cases = [json.loads(ln) for ln in case_lines if ln.strip()]
    subs: dict[tuple[str, str], dict] = {}
    for ln in (subjects or _DIR / "subjects.jsonl").read_text(encoding="utf-8").splitlines():
        if ln.strip():
            r = json.loads(ln)
            subs[(r["case_id"], r["key"])] = r
    return cases, subs


def _sign(x: float, eps: float = 0.05) -> str:
    return "+" if x > eps else "-" if x < -eps else "0"


def lifetime_index(sub: dict) -> float | None:
    """생애 지수 = 대운 1~6(약 10~70세) luck_score 평균 + 세운 양성 비율 보정."""
    dw = sub.get("daewoon") or []
    if not dw:
        return None
    core = [d["luck_score"] for d in dw[1:7]] or [d["luck_score"] for d in dw]
    sw = (sub.get("lifetime") or {}).get("sewoon") or {}
    pos = [v["score"] for v in sw.values()]
    pos_ratio = (sum(1 for s in pos if s > 0.05) / len(pos)) if pos else 0.5
    return round(statistics.mean(core) + (pos_ratio - 0.5), 3)


def _age_year(sub: dict, age: int) -> int:
    return int(sub["date_used"][:4]) + age - 1


def _span_kind(when: dict) -> str:
    """시점 종류 — 'single'(year/years/age 단독) 또는 'multi'(대운·연령 구간). C6-A."""
    if "year" in when or "years" in when:
        return "single"
    if "age" in when and "age_max" not in when:
        return "single"
    return "multi"


def _years_for_when(sub: dict, when: dict) -> tuple[list[int], str]:
    """제공 시점 → 엔진 연도 목록, 기준 설명."""
    if "year" in when:
        return [int(when["year"])], f"year={when['year']}"
    if "years" in when:
        return [int(y) for y in when["years"]], f"years={when['years']}"
    if "age" in when and "age_max" in when:
        lo, hi = _age_year(sub, when["age"]), _age_year(sub, when["age_max"])
        return list(range(lo, hi + 1)), f"age {when['age']}~{when['age_max']}"
    if "age" in when:
        return [_age_year(sub, when["age"])], f"age={when['age']}"
    if "daewoon" in when:
        g = str(when["daewoon"]).split("/")[0]
        for d in sub.get("daewoon") or []:
            if d["ganji"] == g:
                y0 = int(d["start"][:4])
                return list(range(y0, y0 + 10)), f"daewoon={g}({d['start_age']}세~)"
        return [], f"daewoon={g} 미발견"
    if "age_max" in when:
        lo = int(sub["date_used"][:4])
        return list(range(lo, _age_year(sub, when["age_max"]) + 1)), f"~age {when['age_max']}"
    return [], "?"


def _domain_hits(sub: dict, years: list[int], domain: str) -> dict[str, Any]:
    lt = sub.get("lifetime") or {}
    top = lt.get("top_by_year") or {}
    risks = lt.get("risks") or {}
    sew = lt.get("sewoon") or {}
    evs = DOMAIN_EVENTS.get(domain, set())
    pref = DOMAIN_RISK_PREFIX.get(domain, ())

    # C5-3(2026-10-07): HLT_* 는 incident_risk 가 없고 pressure 뿐이라, 건강 계열 도메인은
    # pressure 를 포함한 전체 수를 개인 기준선과 비교한다(지표 전용, 노출 로직 무관).
    health_like = domain in ("health", "death", "accident")

    def _inc(y: str) -> int:
        """개인 기준선용: 해당 연도 도메인 위험 수(건강 계열은 전체 kind, 그 외 incident_risk)."""
        return sum(
            1 for r in risks.get(y, [])
            if r.startswith(pref) and (health_like or "incident_risk" in r)
        )

    base = [_inc(y) for y in sew] or [0]
    base_mean = statistics.mean(base)
    hit_years: list[int] = []
    scores: list[float] = []
    fav: list[float] = []
    inc: list[int] = []
    ctx_scores: list[float] = []
    for y in years:
        ys = str(y)
        matched = [e for e in top.get(ys, []) if e["ev"] in evs]
        if matched:
            hit_years.append(y)
            fav.extend(e["fav"] for e in matched)
        if ys in sew:
            scores.append(sew[ys]["score"])
            if sew[ys].get("ctx") is not None:
                ctx_scores.append(sew[ys]["ctx"])
        inc.append(_inc(ys))
    top_events = {
        str(y): [f"{e['ev']}({e['score']},{e['fav']:+.1f})" for e in top.get(str(y), [])[:3]]
        for y in years[:3]
    }
    return {
        "years": years,
        "sewoon_scores": scores,
        "sewoon_mean": round(statistics.mean(scores), 2) if scores else None,
        # C6 B/C 실험값(재생이 플래그 ON 으로 돌았을 때만 채워짐).
        "ctx_scores": ctx_scores,
        "ctx_mean": round(statistics.mean(ctx_scores), 2) if ctx_scores else None,
        "event_hit_years": hit_years,
        "event_fav_mean": round(statistics.mean(fav), 2) if fav else None,
        "risk_inc_mean": round(statistics.mean(inc), 2) if inc else None,
        "risk_inc_base": round(base_mean, 2),
        "top_events": top_events,
    }


def _structure_rows(
    c: dict, subs: dict, metrics: dict,
) -> tuple[list[str], dict[str, float | None]]:
    rows = [_STRUCT_HEADER, _sep(9)]
    lfi: dict[str, float | None] = {}
    for s in c["subjects"]:
        sub = subs.get((c["case_id"], s["key"]))
        pil = " ".join(s["pillars"])
        if not sub or sub.get("structure") is None:
            rows.append(_row([s["key"], s["gender"], pil, "오류", "", "", "", "", ""]))
            continue
        if not sub["pillars_match"]:
            metrics["pillars_mismatch"].append(f"{c['case_id']}/{s['key']}")
        if sub.get("error"):
            metrics["structure_only"].append(f"{c['case_id']}/{s['key']}")
        st, ro = sub["structure"], sub["roles"]
        fin = ro.get("final") or {}
        role_keys = ("yongsin", "heesin", "gisin", "gusin", "hansin")
        roles = "/".join(str(fin.get(k, "-")) for k in role_keys)
        idx = lifetime_index(sub)
        lfi[s["key"]] = idx
        dstr = f"{sub.get('date_used') or '-'}({sub.get('variant') or '-'})"
        dwd = (f"{sub.get('luck_direction', '-')}·{sub.get('luck_start_age', '-')}세"
               if sub.get("daewoon") else "-")
        rows.append(_row([
            s["key"], s["gender"], pil, dstr,
            f"{st['strength_band']}({st['strength_score']})",
            f"{st['geokguk']}·{st['geokguk_level']}", roles, dwd,
            idx if idx is not None else "-",
        ]))
    return rows, lfi


def _c6_track(
    metrics: dict, span: str, c: dict, s: dict, o: dict, label: str,
    before_ok: bool, after_ok: bool, before: Any, after: Any, dw_mean: float | None,
) -> None:
    """C6 B/C 개선·악화 사례 추적(세운 원본 판정 → 맥락 점수 판정)."""
    if before_ok == after_ok:
        return
    key = "improved" if after_ok else "regressed"
    metrics["c6_context"][span][key].append({
        "case": c["case_id"], "key": s["key"], "text": o["text"], "pol": o["polarity"],
        "when": label, "before": before, "after": after, "daewoon_mean": dw_mean,
    })


def _c6_year_stats(subs: dict, metrics: dict) -> None:
    """C6 B/C 전 연도 통계 — 세운 독립 변화가 대운에 묻히는 비율·대운 지배율(원본 대비)."""
    n = buried = dom_before = dom_after = 0
    for sub in subs.values():
        for row in ((sub.get("lifetime") or {}).get("sewoon") or {}).values():
            if row.get("ctx") is None or row.get("dw") is None:
                continue
            n += 1
            s_sign, c_sign, d_sign = _sign(row["score"]), _sign(row["ctx"]), _sign(row["dw"])
            buried += int(s_sign != "0" and c_sign != s_sign)
            dom_before += int(s_sign == d_sign)
            dom_after += int(c_sign == d_sign)
    if n:
        metrics["c6_context"]["years"] = {
            "n": n, "buried_share": round(buried / n, 3),
            "daewoon_dominance_before": round(dom_before / n, 3),
            "daewoon_dominance_after": round(dom_after / n, 3),
        }


def _outcome_rows(c: dict, subs: dict, metrics: dict) -> list[str]:
    rows = [_OUTCOME_HEADER, _sep(9)]
    for s in c["subjects"]:
        sub = subs.get((c["case_id"], s["key"]))
        for o in s["outcomes"]:
            when = o.get("when")
            pol = o["polarity"]
            if not when or not sub or not sub.get("daewoon"):
                rows.append(_row([s["key"], o["text"], pol, "-", "", "", "", "", ""]))
                continue
            years, label = _years_for_when(sub, when)
            if not years:
                rows.append(_row([s["key"], o["text"], pol, label, "", "", "", "", ""]))
                continue
            h = _domain_hits(sub, years, o["domain"])
            dw_scores = [
                d["luck_score"] for d in sub["daewoon"]
                if any(int(d["start"][:4]) <= y < int(d["start"][:4]) + 10 for y in years)
            ]
            dw_mean = round(statistics.mean(dw_scores), 2) if dw_scores else None
            span = _span_kind(when)
            sew_scores = h["sewoon_scores"]
            sign_ratio = (
                round(sum(1 for v in sew_scores if _sign(v) == pol) / len(sew_scores), 2)
                if sew_scores else None
            )
            if pol in "+-":
                metrics["timed_total"] += 1
                sew_ok = h["sewoon_mean"] is not None and _sign(h["sewoon_mean"]) == pol
                dw_ok = dw_mean is not None and _sign(dw_mean) == pol
                if sew_ok:
                    metrics["timed_sewoon_agree"] += 1
                if dw_ok:
                    metrics["timed_daewoon_agree"] += 1
                # C6-A: 단일 연도/다년 구간 분리 집계.
                ctx_scores = h["ctx_scores"]
                ctx_ok = h["ctx_mean"] is not None and _sign(h["ctx_mean"]) == pol
                ctx_ratio = (
                    round(sum(1 for v in ctx_scores if _sign(v) == pol) / len(ctx_scores), 2)
                    if ctx_scores else None
                )
                if span == "single":
                    metrics["timed_single_total"] += 1
                    metrics["timed_single_sewoon_agree"] += int(sew_ok)
                    metrics["timed_single_daewoon_agree"] += int(dw_ok)
                    if ctx_scores:
                        metrics["timed_single_ctx_agree"] += int(ctx_ok)
                        _c6_track(metrics, "single", c, s, o, label, sew_ok, ctx_ok,
                                  h["sewoon_mean"], h["ctx_mean"], dw_mean)
                else:
                    metrics["timed_multi_total"] += 1
                    metrics["timed_multi_daewoon_agree"] += int(dw_ok)
                    ratio_ok = sign_ratio is not None and sign_ratio >= 0.6
                    metrics["timed_multi_sewoon_ratio_agree"] += int(ratio_ok)
                    if ctx_scores:
                        ctx_ratio_ok = ctx_ratio is not None and ctx_ratio >= 0.6
                        metrics["timed_multi_ctx_ratio_agree"] += int(ctx_ratio_ok)
                        _c6_track(metrics, "multi", c, s, o, label, ratio_ok, ctx_ratio_ok,
                                  sign_ratio, ctx_ratio, dw_mean)
                if h["event_hit_years"]:
                    metrics["timed_event_hit"] += 1
                risk_up = (h["risk_inc_mean"] is not None
                           and h["risk_inc_mean"] > h["risk_inc_base"])
                if risk_up:
                    metrics["timed_risk_above_base"] += 1
                metrics["timed_detail"].append({
                    "case": c["case_id"], "key": s["key"], "domain": o["domain"], "pol": pol,
                    "when": label, "span": span, "sewoon_mean": h["sewoon_mean"],
                    "sewoon_sign_ratio": sign_ratio, "daewoon_mean": dw_mean,
                    "event_hit": bool(h["event_hit_years"]), "event_fav": h["event_fav_mean"],
                    "risk_inc": h["risk_inc_mean"], "risk_base": h["risk_inc_base"],
                })
            ev_hit = (f"{len(h['event_hit_years'])}/{len(years)}년 fav={h['event_fav_mean']}"
                      if h["event_hit_years"] else "없음")
            tops = "; ".join(f"{y}:{','.join(v)}" for y, v in h["top_events"].items())
            rows.append(_row([
                s["key"], o["text"], pol, label, h["sewoon_mean"], dw_mean, ev_hit,
                f"{h['risk_inc_mean']}({h['risk_inc_base']})", tops,
            ]))
    return rows


def _pair_rows(c: dict, lfi: dict[str, float | None], metrics: dict) -> list[str]:
    pol_sum: dict[str, int] = {}
    for s in c["subjects"]:
        untimed = [o for o in s["outcomes"] if o["polarity"] in "+-"]
        pol_sum[s["key"]] = sum(1 if o["polarity"] == "+" else -1 for o in untimed)
    keys = [s["key"] for s in c["subjects"]]
    lines: list[str] = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            if pol_sum.get(a) == pol_sum.get(b) or lfi.get(a) is None or lfi.get(b) is None:
                continue
            better = a if pol_sum[a] > pol_sum[b] else b
            worse = b if better == a else a
            lb, lw = lfi[better], lfi[worse]
            assert lb is not None and lw is not None
            agree = lb > lw
            metrics["pair_total"] += 1
            metrics["pair_agree"] += int(agree)
            metrics["pair_detail"].append({
                "case": c["case_id"], "better": better, "worse": worse,
                "lfi_better": lb, "lfi_worse": lw, "agree": agree,
            })
            verdict = "일치" if agree else "**불일치**"
            lines.append(f"- 쌍 {better}(우) vs {worse}(열): 생애지수 {lb} vs {lw} → {verdict}")
    return lines


def _case_section(c: dict, subs: dict, metrics: dict) -> str:
    sec = [f"## {c['case_id']} — {c['topic']}", ""]
    if c.get("claims"):
        sec.append("문서 해설: " + " / ".join(c["claims"]))
        sec.append("")
    rows, lfi = _structure_rows(c, subs, metrics)
    sec.extend(rows)
    sec.append("")
    for s in c["subjects"]:
        sub = subs.get((c["case_id"], s["key"]))
        if sub and sub.get("daewoon"):
            dws = " ".join(f"{d['ganji']}{d['start_age']}{_sign(d['luck_score'])}"
                           for d in sub["daewoon"])
            sec.append(f"- {s['key']} 대운: {dws}")
    sec.append("")
    sec.extend(_outcome_rows(c, subs, metrics))
    pair_lines = _pair_rows(c, lfi, metrics)
    if pair_lines:
        sec.append("")
        sec.extend(pair_lines)
    sec.append("")
    return "\n".join(sec)


def _summary(metrics: dict, n_subs: int) -> list[str]:
    pt, pa = metrics["pair_total"], metrics["pair_agree"]
    tt = metrics["timed_total"]
    md = ["## 요약 지표", ""]
    md.append(
        f"- 명식 재현: {n_subs}명식 중 불일치 {len(metrics['pillars_mismatch'])}건, "
        f"구조 전용(날짜 복원 불가) {len(metrics['structure_only'])}건 {metrics['structure_only']}"
    )
    md.append(f"- A. 쌍 비교 순위 일치: {pa}/{pt} = {pa / pt * 100:.1f}%"
              if pt else "- A. 쌍 비교 없음")
    if tt:
        for label, key in (("B. 시점 사건 세운 극성 일치(합산·비교용)", "timed_sewoon_agree"),
                           ("B'. 시점 사건 대운 극성 일치(합산·비교용)", "timed_daewoon_agree"),
                           ("C. 시점 도메인 이벤트 히트(상위4)", "timed_event_hit"),
                           ("C'. 시점 도메인 위험밀도 > 개인 기준선", "timed_risk_above_base")):
            md.append(f"- {label}: {metrics[key]}/{tt} = {metrics[key] / tt * 100:.1f}%")
        st, mt = metrics["timed_single_total"], metrics["timed_multi_total"]
        if st:
            for label, key in (("B1. 단일 연도 세운 극성 일치", "timed_single_sewoon_agree"),
                               ("B1'. 단일 연도 대운 극성 일치", "timed_single_daewoon_agree")):
                md.append(f"- {label}: {metrics[key]}/{st} = {metrics[key] / st * 100:.1f}%")
        if mt:
            for label, key in (("B2. 다년 구간 대운 극성 일치", "timed_multi_daewoon_agree"),
                               ("B2'. 다년 구간 세운 부호 연도 비율≥0.6",
                                "timed_multi_sewoon_ratio_agree")):
                md.append(f"- {label}: {metrics[key]}/{mt} = {metrics[key] / mt * 100:.1f}%")
        c6 = metrics["c6_context"]
        if c6.get("years"):
            y = c6["years"]
            md.append("")
            md.append(f"### C6 B/C 실험(daewoon_context_score, mode={c6.get('mode')})")
            md.append(f"- B1c. 단일 연도 맥락 점수 극성 일치: "
                      f"{metrics['timed_single_ctx_agree']}/{st}"
                      f" (세운 원본 {metrics['timed_single_sewoon_agree']}/{st})")
            md.append(f"- B2c. 다년 구간 맥락 부호 연도 비율≥0.6: "
                      f"{metrics['timed_multi_ctx_ratio_agree']}/{mt}"
                      f" (세운 원본 {metrics['timed_multi_sewoon_ratio_agree']}/{mt})")
            md.append(f"- 전 연도 {y['n']}건: 세운 부호가 맥락에서 뒤집힌 비율(묻힘) "
                      f"{y['buried_share']:.1%}, 대운 부호 일치율 원본 "
                      f"{y['daewoon_dominance_before']:.1%} → 맥락 "
                      f"{y['daewoon_dominance_after']:.1%}")
            for span in ("single", "multi"):
                for key, word in (("improved", "개선"), ("regressed", "악화")):
                    items = c6[span][key]
                    md.append(f"- {span} {word} {len(items)}건: " + ", ".join(
                        f"{i['case']}/{i['key']} {i['text']}"
                        f"({i['pol']}, {i['before']}→{i['after']})"
                        for i in items) if items else f"- {span} {word} 0건")
    bydom: dict[str, Counter] = defaultdict(Counter)
    for r in metrics["timed_detail"]:
        d = bydom[r["domain"]]
        d["n"] += 1
        d["sewoon"] += int(r["sewoon_mean"] is not None and _sign(r["sewoon_mean"]) == r["pol"])
        d["daewoon"] += int(r["daewoon_mean"] is not None and _sign(r["daewoon_mean"]) == r["pol"])
        d["event"] += int(r["event_hit"])
        d["risk"] += int(r["risk_inc"] is not None and r["risk_inc"] > r["risk_base"])
    md.append("")
    md.append("| 도메인 | n | 세운극성 | 대운극성 | 이벤트히트 | 위험>기준 |")
    md.append(_sep(6))
    for dom, d in sorted(bydom.items()):
        md.append(_row([dom, d["n"], d["sewoon"], d["daewoon"], d["event"], d["risk"]]))
    md.append("")
    bad = [f"{p['case']}({p['better']}>{p['worse']}: {p['lfi_better']} vs {p['lfi_worse']})"
           for p in metrics["pair_detail"] if not p["agree"]]
    md.append("불일치 쌍: " + ", ".join(bad))
    md.append("")
    return md


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--subjects", default="",
                    help="재생 결과 파일(기본 var/casebook_replay/subjects.jsonl)")
    ap.add_argument("--tag", default="",
                    help="출력 접미사 — report_{tag}.md / metrics_{tag}.json")
    args = ap.parse_args()
    cases, subs = _load(Path(args.subjects) if args.subjects else None)
    metrics: dict[str, Any] = {
        "pair_total": 0, "pair_agree": 0, "pair_detail": [],
        "timed_total": 0, "timed_sewoon_agree": 0, "timed_daewoon_agree": 0,
        "timed_event_hit": 0, "timed_risk_above_base": 0, "timed_detail": [],
        "timed_single_total": 0, "timed_single_sewoon_agree": 0, "timed_single_daewoon_agree": 0,
        "timed_multi_total": 0, "timed_multi_daewoon_agree": 0,
        "timed_multi_sewoon_ratio_agree": 0,
        # C6 B/C 실험(재생이 플래그 ON 일 때만 의미).
        "timed_single_ctx_agree": 0, "timed_multi_ctx_ratio_agree": 0,
        "c6_context": {"mode": None, "years": None,
                       "single": {"improved": [], "regressed": []},
                       "multi": {"improved": [], "regressed": []}},
        "structure_only": [], "pillars_mismatch": [],
    }
    sections = [_case_section(c, subs, metrics) for c in cases]
    _c6_year_stats(subs, metrics)
    metrics["c6_context"]["mode"] = next(
        (r.get("sewoon_context_mode") for r in subs.values() if r.get("sewoon_context_mode")),
        None,
    )
    md: list[str] = [
        "# 사례집 전수 재생 대조 리포트 (자동 생성)", "",
        "생성: scripts/casebook_report.py · 원천: tests/fixtures/comparison_casebook/cases.jsonl "
        "· 엔진 결과: var/casebook_replay/subjects.jsonl", "",
    ]
    md.extend(_summary(metrics, len(subs)))
    md.extend(sections)
    suffix = f"_{args.tag}" if args.tag else ""
    (_DIR / f"report{suffix}.md").write_text("\n".join(md), encoding="utf-8")
    (_DIR / f"metrics{suffix}.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(md[:20]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
