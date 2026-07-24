"""P2-3 블라인드 감수 표본 생성 (RELATIONSHIP_P2_3_REVIEW_TEMPLATE).

24~30건(disagreement 15 + control 12)을 실제 profile 값으로 채운 **블라인드 감수지**를
만든다. profile 실명·baseline·legacy 비노출, 사례별 profile 표시 순서 결정적 무작위화,
answer key 분리. 감사 전용·읽기 전용·production delta 0.

산출(감수자 제공): p2_3_blind_review_sheet.csv
산출(숨김): p2_3_profile_key.csv · p2_3_case_manifest.json · p2_3_selection_report.md
review_case_id = HMAC(fixture+period) — 실 subject/period 미노출(§2).
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import importlib.util
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_P2_1D = _HERE.parent / "relationship_p2_1d" / "shortlist_harness.py"
_KEY = b"p2-3-blind-review.v1"

# 감수자 제공.
OUT_SHEET = _HERE / "p2_3_blind_review_sheet.csv"
# 숨김(answer key·manifest·선정 보고).
OUT_KEY = _HERE / "p2_3_profile_key.csv"
OUT_MANIFEST = _HERE / "p2_3_case_manifest.json"
OUT_SELECT = _HERE / "p2_3_selection_report.md"

_N_DISAGREEMENT = 15
_N_CONTROL = 12
_N_HIDDEN_REPEAT = 2


def _load_p2_1d():
    spec = importlib.util.spec_from_file_location("_p2_1d_gen", _P2_1D)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _digest(*parts: str) -> str:
    msg = "\x1f".join(parts).encode()
    return hmac.new(_KEY, msg, hashlib.sha256).hexdigest()


def _case_id(fixture: str, layer: str, label: str) -> str:
    return _digest("case", fixture, layer, label)[:12]


def _kinds_and_structure(pi, roots: int) -> tuple[str, str]:
    kinds = sorted({a.kind for a in pi.proj.activations})
    kind_combo = "+".join(kinds) if kinds else "none"
    if not kinds:
        structure = "no_relation"
    elif len(pi.proj.activations) <= 1:
        structure = "single"
    elif roots == 1:
        structure = "same_root_compound"
    else:
        structure = "multi_root"
    return kind_combo, structure


def collect(h) -> tuple[list[str], list[dict]]:
    profiles = h.build_profiles()
    pis = h.build_period_inputs()
    names = list(profiles)
    rows: list[dict] = []
    for pi in pis:
        vals: dict[str, dict] = {}
        roots = None
        for name in names:
            try:
                v = h._synth(pi, profiles[name])
            except Exception:  # noqa: BLE001
                vals = {}
                break
            roots = v.independent_root_trigger_count
            ax = v.axes
            vals[name] = {
                "act_band": ax.activation.band if ax.activation.status.value
                == "evaluated" else None,
                "act_raw": ax.activation.value,
                "stab_net": ax.stability.value,
                "stab_sign": (None if ax.stability.value is None
                              else "pos" if ax.stability.value > 0
                              else "neg" if ax.stability.value < 0 else "zero"),
                "sep_band": ax.separation_pressure.band
                if ax.separation_pressure.status.value == "evaluated" else None,
                "sep_raw": ax.separation_pressure.value,
            }
        if not vals or roots is None:
            continue
        kind_combo, structure = _kinds_and_structure(pi, roots)
        rows.append({
            "case_id": _case_id(pi.fixture, pi.layer, pi.label),
            "roots": roots, "kind_combo": kind_combo, "structure": structure,
            "has_modifier": bool(pi.static_modifiers),
            "vals": vals,
        })
    return names, rows


def _disagreement_reasons(row: dict, names: list[str]) -> list[str]:
    v = row["vals"]
    reasons = []
    if len({v[n]["act_band"] for n in names}) > 1:
        reasons.append("act_band")
    if len({v[n]["stab_sign"] for n in names}) > 1:
        reasons.append("stab_sign")
    if len({v[n]["sep_band"] for n in names}) > 1:
        reasons.append("sep_band")
    if v["D0_baseline"]["act_band"] != v["D1_C1_act_conservative"]["act_band"]:
        reasons.append("C0!=C1")
    if (v["D1_C1_act_conservative"]["act_band"]
            != v["D3_CHUNG_bonus_conservative"]["act_band"]):
        reasons.append("D1!=D3")
    return reasons


def select(rows: list[dict], names: list[str]) -> tuple[list[dict], list[dict]]:
    disagree = [r for r in rows if _disagreement_reasons(r, names)]
    control_pool = [r for r in rows if not _disagreement_reasons(r, names)]
    # disagreement: reason 다양성 우선(정렬 후 상위 N — case_id 결정적).
    for r in disagree:
        r["_reasons"] = _disagreement_reasons(r, names)
    disagree.sort(key=lambda r: (-len(r["_reasons"]), r["case_id"]))
    picked_dis = disagree[:_N_DISAGREEMENT]
    # control: 구조 균형(structure별 라운드로빈).
    by_struct: dict[str, list] = {}
    for r in sorted(control_pool, key=lambda r: r["case_id"]):
        by_struct.setdefault(r["structure"], []).append(r)
    picked_ctrl: list[dict] = []
    order = sorted(by_struct)
    i = 0
    while len(picked_ctrl) < _N_CONTROL and any(by_struct.values()):
        s = order[i % len(order)]
        if by_struct[s]:
            picked_ctrl.append(by_struct[s].pop(0))
        i += 1
        if i > 1000:
            break
    return picked_dis, picked_ctrl


def _blind_map(names: list[str]) -> dict[str, str]:
    """profile 실명 → 중립 라벨(A~G) 결정적 매핑(digest 정렬)."""
    ordered = sorted(names, key=lambda n: _digest("blindmap", n))
    labels = [chr(ord("A") + i) for i in range(len(ordered))]
    return dict(zip(ordered, labels, strict=True))


def _case_profile_order(case_id: str, names: list[str]) -> list[str]:
    """사례별 profile 표시 순서 결정적 무작위화(HMAC ordering)."""
    return sorted(names, key=lambda n: _digest("order", case_id, n))


def generate() -> dict:
    h = _load_p2_1d()
    names, rows = collect(h)
    picked_dis, picked_ctrl = select(rows, names)
    blind = _blind_map(names)

    # 숨은 반복(§7) — disagreement 앞 2건을 다른 case_id·다른 순서로 복제.
    repeats = []
    for r in picked_dis[:_N_HIDDEN_REPEAT]:
        rep = dict(r)
        rep["case_id"] = _digest("repeat", r["case_id"])[:12]
        rep["_is_repeat_of"] = r["case_id"]
        repeats.append(rep)

    all_cases = ([("disagreement", r) for r in picked_dis]
                 + [("control", r) for r in picked_ctrl]
                 + [("hidden_repeat", r) for r in repeats])
    # 감수지 행 순서도 case_id 기반 결정적 셔플(군 라벨 비노출).
    all_cases = sorted(all_cases, key=lambda x: _digest("row", x[1]["case_id"]))

    # 감수지(블라인드) — profile 실명·군·baseline·legacy 비노출.
    sheet_rows = []
    for _group, r in all_cases:
        order = _case_profile_order(r["case_id"], names)
        for slot, real in enumerate(order, 1):
            v = r["vals"][real]
            sheet_rows.append({
                "review_case_id": r["case_id"],
                "root_count": r["roots"],
                "kind_combo": r["kind_combo"],
                "structure": r["structure"],
                "has_modifier": r["has_modifier"],
                "profile_label": blind[real],  # 사례 내 표시(순서는 slot)
                "display_slot": slot,
                "activation_band": v["act_band"] or "insufficient",
                "activation_raw": v["act_raw"],
                "stability_net": v["stab_net"],
                "stability_sign": v["stab_sign"] or "insufficient",
                "separation_band": v["sep_band"] or "insufficient",
                "separation_raw": v["sep_raw"],
                # 감수 응답란(빈칸).
                "activation_judgment": "",
                "stability_judgment": "",
                "separation_judgment": "",
                "no_meaningful_difference": "",
                "basis_tag": "",
            })
    with OUT_SHEET.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sheet_rows[0].keys()))
        w.writeheader()
        w.writerows(sheet_rows)

    # profile key(숨김).
    from saju_engines.relationship_effect_vector import (
        RELATIONSHIP_CALIBRATION_VERSION,
    )
    with OUT_KEY.open("w", encoding="utf-8", newline="") as f:
        kw = csv.writer(f)
        kw.writerow(["blind_label", "actual_profile_id", "factor_structure",
                     "same_root_factors", "kind_bonus_scale", "calibration_version"])
        profiles = h.build_profiles()
        for name in names:
            spec = profiles[name]
            kw.writerow([
                blind[name], name, spec.calibration.factor_structure.value,
                json.dumps(spec.calibration.same_root_factors.model_dump()),
                json.dumps(spec.kind_bonus_scale), RELATIONSHIP_CALIBRATION_VERSION])

    # case manifest(숨김) — 군·reason·repeat 매핑.
    manifest = {
        "experiment_spec_version": "p2.3.v1",
        "calibration_version": RELATIONSHIP_CALIBRATION_VERSION,
        "counts": {"disagreement": len(picked_dis), "control": len(picked_ctrl),
                   "hidden_repeat": len(repeats),
                   "unique_review_cases": len(picked_dis) + len(picked_ctrl)},
        "cases": [
            {"case_id": r["case_id"], "group": g, "structure": r["structure"],
             "kind_combo": r["kind_combo"], "roots": r["roots"],
             "reasons": r.get("_reasons", []),
             "repeat_of": r.get("_is_repeat_of")}
            for g, r in all_cases],
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    # selection report(숨김).
    from collections import Counter
    struct_dist = Counter(r["structure"] for _g, r in all_cases)
    reason_dist = Counter(x for r in picked_dis for x in r["_reasons"])
    sel = ["# P2-3 표본 선정 보고(숨김 — 감수자 비제공)", "",
           f"unique 감수 사례 {len(picked_dis) + len(picked_ctrl)}건"
           f"(disagreement {len(picked_dis)} + control {len(picked_ctrl)}) "
           f"+ hidden repeat {len(repeats)} = 감수지 {len(all_cases)} 사례. "
           f"131 unique period 기준 dedupe(case_id=HMAC).", "",
           "## 구조 분포", ""]
    for s, c in struct_dist.most_common():
        sel.append(f"- {s}: {c}")
    sel += ["", "## disagreement reason 분포", ""]
    for s, c in reason_dist.most_common():
        sel.append(f"- {s}: {c}")
    sel += ["", "## 게이트", "",
            f"- disagreement {len(picked_dis)}/{_N_DISAGREEMENT}·control "
            f"{len(picked_ctrl)}/{_N_CONTROL}",
            f"- D1!=D3 포함: {reason_dist.get('D1!=D3', 0)}건",
            "- profile 실명·baseline·legacy·군 라벨 감수지 비노출",
            "- profile 표시 순서 사례별 결정적 무작위화(HMAC)", ""]
    OUT_SELECT.write_text("\n".join(sel) + "\n", encoding="utf-8")

    return {"unique_cases": len(picked_dis) + len(picked_ctrl),
            "disagreement": len(picked_dis), "control": len(picked_ctrl),
            "repeats": len(repeats), "sheet_rows": len(sheet_rows),
            "d1_ne_d3": reason_dist.get("D1!=D3", 0)}


def main() -> int:
    r = generate()
    print(f"P2-3: unique {r['unique_cases']}(dis {r['disagreement']}·ctrl "
          f"{r['control']})·repeat {r['repeats']}·sheet {r['sheet_rows']} rows·"
          f"D1!=D3 {r['d1_ne_d3']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
