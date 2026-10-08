#!/usr/bin/env python3
"""사주 비교 사례집(Vol.1~2, 85사례 180명식) 엔진 전수 재생 — 비교 기준선 생성.

입력: tests/fixtures/comparison_casebook/cases.jsonl (문서 큐레이션)
출력: var/casebook_replay/subjects.jsonl (명식별 엔진 결과 요약)
      var/casebook_replay/report.md (사례별 비교표 — 사람이 읽는 리포트)

원칙: 엔진 결과를 그대로 기록한다(보정·재해석 금지). 문서의 제공 이력은 ground truth가
아니라 어긋남 감지용이다(doc/v2_2/LIFE_EVENT_CASES.md). LLM 호출 없음.

사용:
    python scripts/casebook_replay.py                 # 전수
    python scripts/casebook_replay.py --only CASE-010 # 특정 사례
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND / "apps" / "api"))

from saju_manse_analysis.force_analysis import analyze_chart  # noqa: E402
from saju_manse_analysis.relations import hap_modes as _hm  # noqa: E402

from saju_engines.event_engine_v2 import EventEngineV2  # noqa: E402

# 화기격 기록(H0, 2026-10-08 데굴님 지시) — 두 판정원 결과와 고전 조건 충족 여부를 산출물에
# 남긴다(판정·점수 불변).
from saju_engines.event_scoring import favorability_map  # noqa: E402
from saju_engines.lifetime_scan import lifetime_pillars, merge_yearly_luck  # noqa: E402
from saju_manse_core.calendar.sexagenary_cycle import (  # noqa: E402
    day_ganzi,
    ganzi_index,
    year_ganzi,
)
from saju_manse_core.pillars.four_pillars import build_pillar  # noqa: E402
from saju_manse_core.pillars.gongmang import gongmang_branches  # noqa: E402
from saju_shared_types.birth_input import BirthInput, TimeCalculationOptions  # noqa: E402
from saju_shared_types.constants import STEM_ELEMENT, season_state, ten_god  # noqa: E402
from saju_shared_types.enums import (  # noqa: E402
    Branch,
    Element,  # noqa: E402
    Stem,
)
from saju_shared_types.ganji_calendar import GanjiLevel  # noqa: E402
from saju_shared_types.pillars import FourPillarsResult  # noqa: E402

_HWA_BLOCK_TG = {"비견", "겁재", "정인", "편인", "정관", "편관"}  # 滴天髓 "不遇 印·劫·官"


def _hwa_record(r) -> dict[str, Any]:
    """일간 천간합의 화기격 판정 기록 — ① hap_modes 3단계 ② TransformationCheck ③ 고전 조건.

    고전(滴天髓 從化論－真): 합 상대가 월·시간(연간 제외) · 獨相作合(쟁합 없음) · 투간 인·겁·관
    不遇 · 化神 월령 통함 · 化神 통근 · 일간 무근(진화)/유근(가화). 엔진 판정은 바꾸지 않고
    기록만 한다.
    """
    p = r.pillars
    dm = Stem(p.day_master)
    try:
        fav = favorability_map(r)
    except Exception:  # noqa: BLE001
        fav = {}
    out: list[dict[str, Any]] = []
    try:
        res = _hm.resolve_stem_hap(p, fav)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "haps": []}
    tc_by_pair: dict[frozenset, Any] = {}
    sa = r.structure_analysis
    for t in (getattr(sa, "transformed_candidates", None) or []):
        if len(t.members) == 2 and all(len(m) == 1 for m in t.members):
            tc_by_pair[frozenset(t.members)] = t
    stems_by_pos = {pos: Stem(getattr(p, pos).stem) for pos in ("year", "month", "day", "hour")
                    if getattr(p, pos) is not None}
    for x in res:
        if "day" not in x.positions or x.luck_origin:
            continue
        partner_pos = x.positions[1] if x.positions[0] == "day" else x.positions[0]
        target_el = Element(x.transform_element) if x.transform_element else None
        others = [st for pos, st in stems_by_pos.items() if pos not in ("day", partner_pos)]
        blocking = [f"{st}({ten_god(dm, st)})" for st in others
                    if str(ten_god(dm, st)) in _HWA_BLOCK_TG]
        tc = tc_by_pair.get(frozenset(x.pair))
        out.append({
            "pair": "".join(x.pair), "partner_pos": partner_pos,
            "transform_element": x.transform_element,
            "tier": x.transform_tier, "mode": x.hap_mode, "chart_transform": x.chart_transform,
            "contend": x.contend, "blocked": x.blocked, "block_reason": x.block_reason,
            "weakened": x.weakened,
            "dm_rooted": _hm._rooted(STEM_ELEMENT[dm].value, p),
            "target_rooted": (_hm._rooted(target_el.value, p) if target_el else None),
            "target_season": (season_state(target_el, Branch(p.month.branch))
                              if target_el else None),
            "classic_month_or_hour": partner_pos in ("month", "hour"),
            "classic_no_resource_peer_officer": not blocking,
            "classic_blocking_stems": blocking,
            "tc_confirmed": (t.confirmed if (t := tc) is not None else None),
            "tc_possible": (tc.possible if tc is not None else None),
            "tc_confidence": (tc.confidence if tc is not None else None),
            "tc_blockers": (list(tc.blockers) if tc is not None else None),
            "notes": [n for n in x.notes if "化" in n or "진화" in n or "가화" in n],
        })
    return {"haps": out}

_CASES = _BACKEND / "tests" / "fixtures" / "comparison_casebook" / "cases.jsonl"
_OUT_DIR = _BACKEND.parent / "var" / "casebook_replay"
_DICTS = _BACKEND / "dictionaries"

# 화면 프로그램과 같은 대표 시각(시진 중앙, 子시는 00:00 朝子)
_BRANCH_HOUR = {"子": "00:00", "丑": "02:00", "寅": "04:00", "卯": "06:00", "辰": "08:00",
                "巳": "10:00", "午": "12:00", "未": "14:00", "申": "16:00", "酉": "18:00",
                "戌": "20:00", "亥": "22:00"}
_GENDER = {"M": "male", "F": "female", "U": "male"}


# 시간 보정 변형 — 화면 프로그램(-30분 고정)과 엔진(표준시 변천·서머타임 반영)의 차이를
# 흡수해 문서 명식을 재현한다. 문서 명식이 비교 기준이므로 날짜가 아니라 명식에 맞춘다.
_VARIANTS: list[tuple[str, dict[str, Any]]] = [
    ("default", {}),
    ("no_dst", {"apply_daylight_saving": False}),
    ("no_dst_no_lon", {"apply_daylight_saving": False, "apply_longitude_correction": False}),
    ("no_tst", {"apply_true_solar_time": False}),
]


def _birth(d: str, t: str, gender: str, variant: dict[str, Any] | None = None) -> BirthInput:
    kw: dict[str, Any] = {}
    if variant:
        kw["time_options"] = TimeCalculationOptions(**variant)
    return BirthInput(calendar_type="solar", birth_date=d, birth_time=t,
                      birth_place_name="서울", gender=_GENDER[gender], **kw)


def _shift(t: str, hours: int) -> tuple[str, int]:
    """시각을 시간 단위로 이동. (새 시각, 날짜 이동일수)"""
    h, m = map(int, t.split(":"))
    h += hours
    dd = 0
    while h < 0:
        h += 24
        dd -= 1
    while h >= 24:
        h -= 24
        dd += 1
    return f"{h:02d}:{m:02d}", dd


def _calc_matching(d: str, t: str, gender: str, pillars: list[str]):
    """문서 명식을 재현하는 (결과, 변형명, 날짜, 시각)을 찾는다. 실패 시 default 결과."""
    first = None
    for name, var in _VARIANTS:
        for hshift in (0, -1, 1, -2, 2):
            t2, dd = _shift(t, hshift)
            d2 = (date.fromisoformat(d) + timedelta(days=dd)).isoformat()
            try:
                r = _calc(_birth(d2, t2, gender, var))
            except Exception:  # noqa: BLE001
                continue
            if first is None:
                first = (r, name, d2, t2)
            if _ganji4(r) == pillars:
                tag = name if hshift == 0 else f"{name}{hshift:+d}h"
                return r, tag, d2, t2
    return first


def _calc(birth: BirthInput):
    from saju_api.services.manse_service import calculate
    return calculate(birth)


def _ganji4(r) -> list[str]:
    p = r.pillars
    return [p.year.ganji, p.month.ganji, p.day.ganji, p.hour.ganji if p.hour else "--"]


def find_dates(pillars: list[str], lo: int = 1900, hi: int = 2060, gender: str = "M",
               max_hits: int = 3) -> list[tuple[str, str]]:
    """간지 4주 → (양력일, 시각) 후보. 년간지 60년 주기 × 일간지 60일 주기 × 시진 대표시각.

    월주는 calculate 로 절기 검증한다(둔월법 포함). 후보는 오래된 연도부터.
    """
    ys, yb = Stem(pillars[0][0]), Branch(pillars[0][1])
    ds, db = Stem(pillars[2][0]), Branch(pillars[2][1])
    day_idx = ganzi_index(ds, db)
    hour_t = _BRANCH_HOUR[pillars[3][1]]
    hits: list[tuple[str, str]] = []
    for year in range(lo, hi + 1):
        if year_ganzi(year) != (ys, yb):
            continue
        # 입춘 전 1월·2월초는 전년 간지 — 전년 12월~익년 2월까지 넓게 훑는다
        start = date(year, 1, 1)
        end = date(year + 1, 2, 15)
        d = start
        # 첫 일치일로 점프
        while (ganzi_index(*day_ganzi(d)) != day_idx):
            d += timedelta(days=1)
        while d <= end:
            try:
                r = _calc(_birth(d.isoformat(), hour_t, gender))
                if _ganji4(r) == pillars:
                    hits.append((d.isoformat(), hour_t))
                    if len(hits) >= max_hits:
                        return hits
            except Exception:  # noqa: BLE001
                pass
            d += timedelta(days=60)
    return hits


class _PillarsOnly:
    """날짜 복원 불가 명식의 구조 전용 결과(대운·세운 없음)."""

    def __init__(self, pillars: list[str]):
        dm = Stem(pillars[2][0])
        specs = [(Stem(g[0]), Branch(g[1])) for g in pillars]
        glist = gongmang_branches(dm, specs[2][1])
        g = set(glist)
        self.pillars = FourPillarsResult(
            year=build_pillar(dm, *specs[0], "year", g),
            month=build_pillar(dm, *specs[1], "month", g),
            day=build_pillar(dm, *specs[2], "day", g),
            hour=build_pillar(dm, *specs[3], "hour", g),
            day_master=str(dm), gongmang_branches=[str(b) for b in glist])
        a = analyze_chart(self.pillars)
        self.force_analysis = a.force
        self.structure_analysis = a.structure
        self.geokguk = a.geokguk
        self.yongsin_analysis = a.yongsin
        self.traditional_extras = a.traditional


def _roles(r) -> dict[str, Any]:
    y = r.yongsin_analysis
    out: dict[str, Any] = {"final": {}, "operational": []}
    if y is None:
        return out
    out["final"] = {k: v for k, v in (y.final or {}).items() if isinstance(v, str)}
    out["status"] = getattr(y, "status", None)
    for er in getattr(y, "operational_roles", []) or []:
        out["operational"].append(
            f"{er.element}:{er.canonical_role}->{er.operational_role}")
    return out


def _daewoon(r) -> list[dict[str, Any]]:
    rows = []
    for dw in r.luck_cycles.daewoon_table:
        rows.append({"idx": dw.index, "start_age": dw.start_age, "ganji": dw.ganji,
                     "start": dw.approx_start_date.isoformat(),
                     "stem_tg": dw.stem_ten_god, "branch_tg": dw.branch_ten_god,
                     "unseong": dw.twelve_unseong, "relation": dw.yongsin_relation,
                     "luck_score": round(dw.luck_score, 2), "label": dw.luck_label_code,
                     "rels": dw.relations_to_chart[:6]})
    return rows


def _structure(r) -> dict[str, Any]:
    fa = r.force_analysis
    st = fa.strength if fa else None
    gk = r.geokguk
    sinsal = []
    te = r.traditional_extras
    if te and te.sinsal:
        sinsal = sorted({f"{s.name}@{s.position}" for s in te.sinsal.full_list})
    inter = []
    sa = r.structure_analysis
    if sa:
        for it in sa.interactions:
            mem = "".join(getattr(it, "members", []) or [])
            inter.append(f"{it.relation_type}:{mem}")
    tg = {}
    if fa and fa.ten_gods:
        try:
            tg = {k: round(float(v), 2) for k, v in dict(fa.ten_gods).items()
                  if isinstance(v, (int, float))}
        except Exception:  # noqa: BLE001
            tg = {}
    return {
        "strength_band": getattr(st, "band", None),
        "strength_score": round(float(getattr(st, "score", 0.0) or 0.0), 2),
        "borderline": getattr(st, "borderline", None),
        "geokguk": getattr(gk, "main_structure", None) if gk else None,
        "geokguk_level": getattr(gk, "formation_level", None) if gk else None,
        "special_pattern": getattr(gk, "special_pattern", None) if gk else None,
        "follow_consistency": getattr(gk, "follow_consistency", None) if gk else None,
        "hwa": _hwa_record(r),
        "five_elements": (dict(fa.five_elements) if fa and fa.five_elements else {}),
        "ten_gods": tg,
        "interactions": inter,
        "sinsal": sinsal,
        "gongmang": list(r.pillars.gongmang_branches or []),
        "warnings": list(r.pillars.warnings or [])[:5],
    }


def _v(x: Any) -> str:
    """Enum이면 .value, 아니면 str — 직렬화용."""
    return str(x.value) if hasattr(x, "value") else str(x)


def _lifetime_events(r, birth_year: int, engine: EventEngineV2) -> dict[str, Any]:
    lo, hi = birth_year, birth_year + 100
    dw, missing = lifetime_pillars(r, lo, hi)
    lt = merge_yearly_luck(r, list(dw))
    cands = engine.score(lt, levels={GanjiLevel.YEAR})
    by_year: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in cands:
        by_year[c.period].append({
            "ev": _v(c.event_key),
            "score": c.score,
            "fav": round(c.favorability, 2),
            "act": round(c.activation, 2),
            "conf": _v(c.confidence_level),
            "q": _v(c.quality),
            "timing": _v(c.timing),
        })
    top: dict[str, list[dict[str, Any]]] = {}
    for yr, lst in by_year.items():
        lst.sort(key=lambda x: (-x["score"], x["ev"]))
        top[yr] = lst[:4]
    risks: dict[str, list[str]] = defaultdict(list)
    try:
        for rc in engine.take_risk_shadow():
            risks[str(rc.period_key)].append(f"{rc.risk_id}({_v(rc.kind)})")
    except Exception:  # noqa: BLE001
        pass
    # 세운 극성(용신/기신 라벨·점수)
    sewoon: dict[str, dict[str, Any]] = {}
    for dwi in lt.luck_cycles.daewoon_table:
        for sp in dwi.sewoon:
            sewoon[sp.label] = {"ganji": sp.ganji, "align": sp.yongsin_alignment,
                                "score": round(sp.luck_score, 2), "code": sp.luck_label_code,
                                "rels": sp.relations_to_chart[:4],
                                # C6 B/C: 소속 대운 점수·맥락 점수(플래그 OFF 면 None).
                                "dw": round(dwi.luck_score, 2),
                                "ctx": (round(sp.daewoon_context_score, 2)
                                        if sp.daewoon_context_score is not None else None)}
    return {"missing_years": missing, "top_by_year": top, "risks": dict(risks), "sewoon": sewoon}


def replay_subject(case: dict, subj: dict, engine: EventEngineV2) -> dict[str, Any]:
    out: dict[str, Any] = {"case_id": case["case_id"], "key": subj["key"],
                           "gender": subj["gender"], "pillars_doc": subj["pillars"],
                           "date_kind": subj["date_kind"], "date_used": None, "time_used": None,
                           "pillars_engine": None, "pillars_match": None, "error": None}
    d, t = subj.get("date"), subj.get("time")
    tried: list[tuple[str, str]] = []
    if d:
        tried.append((d, t))
    else:
        tried = find_dates(subj["pillars"], gender=subj["gender"])
        out["date_candidates"] = tried
        pref = subj.get("prefer_year")
        if pref and tried:
            tried.sort(key=lambda x: abs(int(x[0][:4]) - int(pref)))
    if not tried:
        # 1900~2060 범위에 해당 명식이 없다(문서 명식 자체가 역법상 불성립이거나 범위 밖).
        # 구조 분석만 수행하고 대운·생애 스캔은 비운다.
        out["error"] = "no date candidate found (structure-only)"
        try:
            po = _PillarsOnly(subj["pillars"])
        except Exception as exc:  # noqa: BLE001
            out["error"] = f"structure-only failed: {exc}"
            return out
        out["pillars_engine"] = _ganji4(po)
        out["pillars_match"] = out["pillars_engine"] == subj["pillars"]
        out["structure"] = _structure(po)
        out["roles"] = _roles(po)
        return out
    d, t = tried[0]
    found = _calc_matching(d, t, subj["gender"], subj["pillars"])
    if found is None:
        out["error"] = "calculate failed"
        return out
    r, variant, d, t = found
    out["date_used"], out["time_used"], out["variant"] = d, t, variant
    out["pillars_engine"] = _ganji4(r)
    out["pillars_match"] = out["pillars_engine"] == subj["pillars"]
    out["structure"] = _structure(r)
    out["roles"] = _roles(r)
    # C4 결정 ④: 원국 품질 shadow 지표(사용자 비노출·평가 전용) 기록.
    try:
        from saju_engines.chart_quality_shadow import chart_quality_shadow
        out["quality_shadow"] = chart_quality_shadow(r).as_dict()
    except Exception as exc:  # noqa: BLE001
        out["quality_shadow"] = {"error": str(exc)}
    out["luck_direction"] = r.luck_cycles.direction
    # C6 B/C: 이 재생이 어떤 맥락 모드로 돌았는지(플래그 OFF 면 None).
    from saju_manse_analysis.luck import luck_cycles as _lc
    out["sewoon_context_mode"] = (
        _lc.SEWOON_DAEWOON_CONTEXT_MODE if _lc.SEWOON_DAEWOON_CONTEXT_ENABLED else None
    )
    out["luck_start_age"] = r.luck_cycles.start_age
    out["daewoon"] = _daewoon(r)
    out["lifetime"] = _lifetime_events(r, int(d[:4]), engine)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--no-events", action="store_true")
    ap.add_argument("--out-name", default="",
                    help="subjects 출력 파일명(기본 subjects.jsonl; C6 실험 등 별도 보존용)")
    args = ap.parse_args()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = _CASES.read_text(encoding="utf-8").splitlines()
    cases = [json.loads(line) for line in lines if line.strip()]
    if args.only:
        cases = [c for c in cases if c["case_id"] in set(args.only)]
    engine = EventEngineV2(_DICTS, risk_mode="shadow")
    rows = []
    # --only 실행은 전수 결과를 덮어쓰지 않도록 별도 파일에 쓴다.
    out_name = args.out_name or ("subjects_only.jsonl" if args.only else "subjects.jsonl")
    with (_OUT_DIR / out_name).open("w", encoding="utf-8") as f:
        for c in cases:
            for s in c["subjects"]:
                row = replay_subject(c, s, engine)
                rows.append(row)
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                print(
                    f"{row['case_id']}/{row['key']} {row['pillars_doc']} -> "
                    f"{row['pillars_engine']} match={row['pillars_match']} "
                    f"date={row['date_used']} err={row['error']}",
                    flush=True,
                )
    print(f"done {len(rows)} subjects → {_OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
