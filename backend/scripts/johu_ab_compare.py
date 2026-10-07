#!/usr/bin/env python3
"""C2 조후 후보 생성부 교체 — 전/후(A/B) 비교표 (JOHU_NEED_DICTIONARY_C2 §5 재현성 검증).

모집단: 사례집 180명식(var/casebook_replay/subjects.jsonl) + shadow 33 + 용신 기준 6.
비교축: 조후 후보 오행·신뢰도, 최종 용희기구한, 선택 모델, 감점/강등 기록, 같은 오행이 조후·억부 두
모델에서 모두 용신 후보로 나온 경우(중복 근거 — 점수는 _put 최대값이라 가산은 아니지만 기록).

사용: python scripts/johu_ab_compare.py [--out var/casebook_replay/johu_ab.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND / "apps" / "api"))

import saju_manse_analysis.yongsin.candidates as cand  # noqa: E402
from saju_manse_analysis import analyze_chart  # noqa: E402

from saju_shared_types.birth_input import BirthInput, TimeCalculationOptions  # noqa: E402

_LEGACY = {"JOHU_CLIMATE_ROLE_ONLY": False, "CLIMATE_PENALTY_MODE": "legacy_month_demote"}
_NEW = {"JOHU_CLIMATE_ROLE_ONLY": True, "CLIMATE_PENALTY_MODE": "month_axis_graded"}
_VAR = {
    "default": {}, "no_dst": {"apply_daylight_saving": False},
    "no_dst_no_lon": {"apply_daylight_saving": False, "apply_longitude_correction": False},
    "no_tst": {"apply_true_solar_time": False},
}
_G = {"M": "male", "F": "female", "U": "male"}


def _population() -> list[tuple[str, BirthInput]]:
    pop: list[tuple[str, BirthInput]] = []
    subj = _BACKEND.parent / "var" / "casebook_replay" / "subjects.jsonl"
    if subj.exists():
        for ln in subj.read_text("utf-8").splitlines():
            r = json.loads(ln)
            if not r.get("date_used"):
                continue
            v = (r.get("variant") or "default").split("+")[0].split("-")[0]
            pop.append((f"{r['case_id']}/{r['key']}", BirthInput(
                calendar_type="solar", birth_date=r["date_used"], birth_time=r["time_used"],
                birth_place_name="서울", gender=_G[r["gender"]],
                time_options=TimeCalculationOptions(**_VAR.get(v, {})),
            )))
    shadow = _BACKEND / "data" / "shadow_charts" / "charts.jsonl"
    if shadow.exists():
        for ln in shadow.read_text("utf-8").splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            b = r.get("birth") or r.get("input") or r
            try:
                sid = r.get('id') or r.get('chart_id') or len(pop)
                pop.append((f"shadow:{sid}", BirthInput(**b)))
            except Exception:  # noqa: BLE001
                continue
    sys.path.insert(0, str(_BACKEND / "tests" / "regression"))
    try:
        from test_yongsin_reference_charts import REFERENCE_CHARTS
        for d, t, g, place, lat, lon, *_ in REFERENCE_CHARTS:
            extra = {"latitude": lat, "longitude": lon, "timezone": "Asia/Seoul"} if lat else {}
            pop.append((f"ref:{d}", BirthInput(
                calendar_type="solar", birth_date=d, birth_time=t, birth_place_name=place,
                gender=g, **extra)))
    except Exception:  # noqa: BLE001
        pass
    return pop


def _snapshot(birth: BirthInput, flags: dict) -> dict:
    from saju_api.services.manse_service import calculate
    for k, v in flags.items():
        setattr(cand, k, v)
    r = calculate(birth)
    y = analyze_chart(r.pillars).yongsin
    f = y.final or {}
    johu = next((m for m in y.candidate_models if m.model_type == "johu"), None)
    eokbu_els = {m.yongsin for m in y.candidate_models
                 if cand._axis_of(m.model_type) == "eokbu" and m.yongsin}
    rejected = [(x["element"], str(x["reason"]).split("(")[0])
                for x in (y.decision_trace.rejected if y.decision_trace else [])
                if "climate" in str(x["reason"])]
    return {
        "pillars": " ".join(
            p.ganji for p in (r.pillars.year, r.pillars.month, r.pillars.day, r.pillars.hour) if p
        ),
        "johu": (johu.yongsin, johu.confidence) if johu else None,
        "roles": "/".join(str(f.get(k)) for k in ("yongsin", "heesin", "gisin", "gusin", "hansin")),
        "model": f.get("selected_model"),
        "climate_rej": rejected,
        "dup": bool(johu and johu.yongsin in eokbu_els),
        "warn": [w for w in y.warnings if w.startswith("조후 교정 필요")],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    default_out = _BACKEND.parent / "var" / "casebook_replay" / "johu_ab.md"
    ap.add_argument("--out", default=str(default_out))
    args = ap.parse_args()
    pop = _population()
    rows: list[str] = []
    stats = {"n": 0, "johu_changed": 0, "roles_changed": 0, "model_changed": 0,
             "yongsin_changed": 0, "dup_before": 0, "dup_after": 0, "no_cand_warn": 0}
    for name, birth in pop:
        try:
            a = _snapshot(birth, _LEGACY)
            b = _snapshot(birth, _NEW)
        except Exception as exc:  # noqa: BLE001
            rows.append(f"| {name} | 오류 {exc} | | | | | |")
            continue
        stats["n"] += 1
        jc = a["johu"] != b["johu"]
        rc = a["roles"] != b["roles"]
        mc = a["model"] != b["model"]
        yc = a["roles"].split("/")[0] != b["roles"].split("/")[0]
        stats["johu_changed"] += jc
        stats["roles_changed"] += rc
        stats["model_changed"] += mc
        stats["yongsin_changed"] += yc
        stats["dup_before"] += a["dup"]
        stats["dup_after"] += b["dup"]
        stats["no_cand_warn"] += bool(b["warn"])
        if jc or rc or mc:
            rows.append(
                f"| {name} | {b['pillars']} | {a['johu']} → {b['johu']} "
                f"| {a['roles']} → {b['roles']} "
                f"| {a['model']} → {b['model']} | {a['climate_rej']} → {b['climate_rej']} "
                f"| {'경고' if b['warn'] else ''} |"
            )
    for k, v in _NEW.items():
        setattr(cand, k, v)
    md = ["# C2 조후 후보 생성부 교체 — 전/후 비교", "",
          f"모집단 {stats['n']}명식 · 조후 후보 변경 {stats['johu_changed']} · 최종 역할표 변경 "
          f"{stats['roles_changed']} · 용신 변경 {stats['yongsin_changed']} · 선택 모델 변경 "
          f"{stats['model_changed']} · 조후·억부 동일 오행 후보(전/후) "
          f"{stats['dup_before']}/{stats['dup_after']} · "
          f"조후 후보 없음 경고 {stats['no_cand_warn']}", "",
          "| 명식 | 사주 | 조후 후보(오행,신뢰도) 전→후 | 용/희/기/구/한 전→후 | 선택 모델 전→후 "
          "| 조후 감점/강등 전→후 | 후보없음 |", "|---|---|---|---|---|---|---|", *rows]
    Path(args.out).write_text("\n".join(md), "utf-8")
    print("\n".join(md[:3]))
    print(f"변경 행 {len(rows)} → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
