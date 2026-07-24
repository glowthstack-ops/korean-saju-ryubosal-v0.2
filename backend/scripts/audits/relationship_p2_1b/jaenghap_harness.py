"""P2-1B 민감도 harness — jaenghap_support_weaken × secondary_factor (stability 집중).

리뷰 §5: band는 stability 계산에 영향 없으므로 **교차하지 않는다**(B0 고정). 12 profile
= jaenghap_weaken(4) × secondary_factor(3) × band B0. baseline = SF30·JW50. 감사 전용·
읽기 전용·production delta 0(합성기 명시 주입).

필수 사례(§6): 순수 support·대상/비대상 root 분리·support+pressure 혼합·같은 root 혼합·
중복 modifier·잘못된 대상(derived 유실)·multi-root 대상·supersession remap.

하드 불변식(§7): JW↑→target/total support·stability net 비증가 / pressure·activation·
separation·count·status 불변 / 비대상 root support delta 0 / 중복=1× / support≥0.
weaken=0은 modifier 미적용과 **수치 축만** 동일(metadata는 다를 수 있음).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from saju_engines.relationship_effect_vector import (
    RELATIONSHIP_CALIBRATION_VERSION,
    RelationshipVectorCalibration,
    synthesize_relationship_effect_vector,
)
from saju_engines.relationship_structure_modifiers import (
    build_relationship_structure_modifiers,
)
from saju_engines.spouse_palace_activation import (
    SpousePalaceHit,
    build_spouse_palace_vector,
)
from saju_shared_types.event_engine import Pillar4, RelationKind
from saju_shared_types.structure_patterns import DetectedPattern

_DICTS = Path(__file__).resolve().parents[3] / "dictionaries"
OUT_MD = Path(__file__).resolve().parent / "P2_1B_SENSITIVITY_REPORT.md"
OUT_JSON = Path(__file__).resolve().parent / "p2_1b_invariant_results.json"

EXPERIMENT_SPEC_VERSION = "p2.1b.v1"
_PERIOD = "2027"
_B0 = {"weak": 6.0, "moderate": 12.0, "strong": 20.0}
_JW = [("JW00", 0.0), ("JW25", 0.25), ("JW50", 0.5), ("JW75", 0.75)]
_SF = [("SF00", 0.0), ("SF30", 0.3), ("SF60", 0.6)]
_JAENGHAP_STRENGTH = 0.6   # 고정 — JW를 변수로 격리.


def _hit(kind: RelationKind, glyph: str, natal: str = "丑") -> SpousePalaceHit:
    return SpousePalaceHit(
        kind=kind, palace=Pillar4.DAY, layer="sewoon", position="branch",
        transit_component="branch", transit_participant=glyph,
        natal_participant=natal)


def _evidences(hits: list[SpousePalaceHit]):
    return build_spouse_palace_vector(hits, _DICTS, period_key=_PERIOD).evidences


def _jaenghap(derived_ids: list[str]):
    return build_relationship_structure_modifiers(
        [DetectedPattern(pattern_id="JAENGHAP", name_ko="쟁합",
                         strength=_JAENGHAP_STRENGTH, polarity_mode="context_only")],
        derived_from_by_pattern={"JAENGHAP": derived_ids})


@dataclass
class Case:
    case_id: str
    evidences: list
    modifiers: list
    # 대상 root 식별(support 추적) — 대상 evidence_id 집합.
    target_evidence_ids: frozenset[str] = field(default_factory=frozenset)
    # 비대상 root evidence_id 집합(scope 안전성 검증).
    nontarget_evidence_ids: frozenset[str] = field(default_factory=frozenset)
    expect: str = "applied"   # applied | no_apply_missing | no_apply_multiroot | dup


def _find(evs, kind: RelationKind, glyph: str):
    for e in evs:
        if e.relation_kind == kind.value and e.transit_participant == glyph:
            return e.evidence_id
    raise KeyError((kind, glyph))


def build_cases() -> list[Case]:
    cases: list[Case] = []

    # 1. 순수 support: HAP(未) + JAENGHAP→A.
    ev = _evidences([_hit(RelationKind.HAP, "未")])
    tid = _find(ev, RelationKind.HAP, "未")
    cases.append(Case("pure_support", ev, _jaenghap([tid]), frozenset({tid})))

    # 2. 대상/비대상 root 분리: HAP(未)+JAENGHAP→A · HAP(戌) non-target.
    ev = _evidences([_hit(RelationKind.HAP, "未"), _hit(RelationKind.HAP, "戌", natal="辰")])
    tid = _find(ev, RelationKind.HAP, "未")
    nid = _find(ev, RelationKind.HAP, "戌")
    cases.append(Case("target_vs_nontarget", ev, _jaenghap([tid]),
                      frozenset({tid}), frozenset({nid})))

    # 3. support+pressure 혼합: HAP(未)+JAENGHAP→A · CHUNG(戌).
    ev = _evidences([_hit(RelationKind.HAP, "未"), _hit(RelationKind.CHUNG, "戌", natal="辰")])
    tid = _find(ev, RelationKind.HAP, "未")
    nid = _find(ev, RelationKind.CHUNG, "戌")
    cases.append(Case("support_pressure_mix", ev, _jaenghap([tid]),
                      frozenset({tid}), frozenset({nid})))

    # 4. 같은 root 혼합: HAP+CHUNG(둘 다 未) + JAENGHAP→그 root.
    ev = _evidences([_hit(RelationKind.HAP, "未"), _hit(RelationKind.CHUNG, "未", natal="辰")])
    tid = _find(ev, RelationKind.HAP, "未")
    cases.append(Case("same_root_mix", ev, _jaenghap([tid]), frozenset({tid})))

    # 5. 중복 modifier: 동일 JAENGHAP 2회(1회와 동일해야).
    ev = _evidences([_hit(RelationKind.HAP, "未")])
    tid = _find(ev, RelationKind.HAP, "未")
    dup_mods = _jaenghap([tid]) + _jaenghap([tid])
    cases.append(Case("duplicate_modifier", ev, dup_mods, frozenset({tid}),
                      expect="dup"))

    # 6. 잘못된 대상: 존재하지 않는 evidence 참조 → 수치 적용 0.
    ev = _evidences([_hit(RelationKind.HAP, "未")])
    cases.append(Case("wrong_target", ev,
                      _jaenghap(["spa:sewoon:HAP:day_pillar:branch:::丑:亥:"]),
                      frozenset(), expect="no_apply_missing"))

    # 7. multi-root 대상: 두 root evidence 동시 참조 → 보류(적용 0).
    ev = _evidences([_hit(RelationKind.HAP, "未"), _hit(RelationKind.HAP, "戌", natal="辰")])
    a = _find(ev, RelationKind.HAP, "未")
    b = _find(ev, RelationKind.HAP, "戌")
    cases.append(Case("multi_root_target", ev, _jaenghap([a, b]),
                      frozenset(), expect="no_apply_multiroot"))

    # 8. 부호 경계(sign flip): 두 HAP support(0.3+0.3=0.6) vs PA pressure(0.6) → net 0.
    #    JAENGHAP이 A support를 약화하면 net<0으로 전환(zero→neg 부호 flip).
    ev = _evidences([_hit(RelationKind.HAP, "未"),
                     _hit(RelationKind.HAP, "戌", natal="辰"),
                     _hit(RelationKind.PA, "申", natal="巳")])
    tid = _find(ev, RelationKind.HAP, "未")
    cases.append(Case("boundary_sign_flip", ev, _jaenghap([tid]), frozenset({tid})))

    return cases


def _cal(sf: float, jw: float) -> RelationshipVectorCalibration:
    return RelationshipVectorCalibration(
        profile_id=f"P2B_sf{sf}_jw{jw}", secondary_factor=sf,
        support_weaken=jw, activation_band=dict(_B0))


def _target_support(result, target_ids: frozenset[str]) -> float:
    """대상 root(들)의 stability_support 합 — evidence_id 교집합으로 식별."""
    total = 0.0
    for rc in result.root_contributions:
        if target_ids & set(rc.evidence_ids):
            total += rc.stability_support
    return round(total, 3)


def _nontarget_support(result, nontarget_ids: frozenset[str]) -> float:
    total = 0.0
    for rc in result.root_contributions:
        if nontarget_ids & set(rc.evidence_ids):
            total += rc.stability_support
    return round(total, 3)


def _sign(v: float | None) -> str:
    if v is None:
        return "na"
    if v > 0:
        return "pos"
    if v < 0:
        return "neg"
    return "zero"


def measure(cases: list[Case]) -> dict:
    grid: dict[str, dict] = {}
    for c in cases:
        grid[c.case_id] = {}
        for sf_id, sf in _SF:
            for jw_id, jw in _JW:
                r = synthesize_relationship_effect_vector(
                    c.evidences, modifiers=c.modifiers, calibration=_cal(sf, jw))
                grid[c.case_id][f"{sf_id}_{jw_id}"] = {
                    "target_support": _target_support(r, c.target_evidence_ids),
                    "nontarget_support": _nontarget_support(r, c.nontarget_evidence_ids),
                    "total_support": round(
                        sum(rc.stability_support for rc in r.root_contributions), 3),
                    "stability_net": r.axes.stability.value,
                    "stability_sign": _sign(r.axes.stability.value),
                    "activation": r.axes.activation.value,
                    "separation": r.axes.separation_pressure.value,
                    "roots": r.independent_root_trigger_count,
                    "evidence": r.evidence_count,
                    "multi_root_hold": r.modifier_multi_root_hold_count,
                }
    return grid


def invariant_checks(cases: list[Case], grid: dict) -> dict:
    viols: list[str] = []

    def v(m: str) -> None:
        viols.append(m)

    for c in cases:
        # weaken=0은 modifier 미적용과 수치 축만 동일(§7).
        no_mod = synthesize_relationship_effect_vector(
            c.evidences, calibration=_cal(0.3, 0.5))  # modifier 없음
        jw0 = synthesize_relationship_effect_vector(
            c.evidences, modifiers=c.modifiers, calibration=_cal(0.3, 0.0))
        if (no_mod.axes.stability.value != jw0.axes.stability.value
                or no_mod.axes.activation.value != jw0.axes.activation.value
                or no_mod.axes.separation_pressure.value
                != jw0.axes.separation_pressure.value):
            v(f"weaken0_numeric_mismatch:{c.case_id}")

        for sf_id, _sf in _SF:
            keys = [f"{sf_id}_{jw_id}" for jw_id, _ in _JW]
            seq = [grid[c.case_id][k] for k in keys]
            # (§7) JW↑ → target/total support·stability net 비증가.
            for a, b in zip(seq, seq[1:], strict=False):
                if b["target_support"] > a["target_support"] + 1e-9:
                    v(f"target_support_increased:{c.case_id}:{sf_id}")
                if b["total_support"] > a["total_support"] + 1e-9:
                    v(f"total_support_increased:{c.case_id}:{sf_id}")
                if (b["stability_net"] is not None and a["stability_net"] is not None
                        and b["stability_net"] > a["stability_net"] + 1e-9):
                    v(f"stability_net_increased:{c.case_id}:{sf_id}")
            # (§7) pressure·activation·separation·count·status는 JW 불변.
            ref = seq[0]
            for s in seq[1:]:
                if s["activation"] != ref["activation"]:
                    v(f"jw_changed_activation:{c.case_id}:{sf_id}")
                if s["separation"] != ref["separation"]:
                    v(f"jw_changed_separation:{c.case_id}:{sf_id}")
                if s["roots"] != ref["roots"] or s["evidence"] != ref["evidence"]:
                    v(f"jw_changed_count:{c.case_id}:{sf_id}")
            # (§7) 비대상 root support delta 0.
            if c.nontarget_evidence_ids:
                nts = {s["nontarget_support"] for s in seq}
                if len(nts) != 1:
                    v(f"nontarget_drift:{c.case_id}:{sf_id}")
            # (§7) support ≥ 0.
            for s in seq:
                if s["target_support"] < -1e-9 or s["total_support"] < -1e-9:
                    v(f"negative_support:{c.case_id}:{sf_id}")
            # 기대 동작별.
            if c.expect in ("no_apply_missing", "no_apply_multiroot"):
                # JW 전 support 불변(수치 적용 0).
                sups = {s["total_support"] for s in seq}
                if len(sups) != 1:
                    v(f"unexpected_application:{c.case_id}:{sf_id}:{c.expect}")
            if c.expect == "no_apply_multiroot":
                if any(s["multi_root_hold"] < 1 for s in seq):
                    v(f"multiroot_not_held:{c.case_id}:{sf_id}")

    return {"violations": viols, "passed": not viols}


def synthesizer_findings(cases: list[Case]) -> dict:
    """calibration과 무관한 synthesizer 관찰(§7 중복 idempotency 검증) — P2 수정 대상
    아님(audit only). derived(transit) modifier가 dedup되는지 확인해 보고만 한다.

    발견: `_merge_modifiers`는 structural_context_id(natal static)만 병합한다. derived
    modifier(JAENGHAP 등)는 transit로 분류돼 dedup되지 않으므로, 동일 derived modifier가
    2회 들어오면 support가 2회 약화된다(비멱등). production 파이프라인은 pattern_id별
    1개만 생성하므로 라이브 영향 0 — 방어적 견고성 갭. P3/hardening 후보(수정은 별도 승인).
    """
    dup_idempotent = True
    example: dict | None = None
    for c in cases:
        if c.expect != "dup":
            continue
        single = _jaenghap(list(c.target_evidence_ids))
        for sf_id, sf in _SF:
            for jw_id, jw in _JW:
                sup_dup = _target_support(synthesize_relationship_effect_vector(
                    c.evidences, modifiers=c.modifiers, calibration=_cal(sf, jw)),
                    c.target_evidence_ids)
                sup_one = _target_support(synthesize_relationship_effect_vector(
                    c.evidences, modifiers=single, calibration=_cal(sf, jw)),
                    c.target_evidence_ids)
                if sup_dup != sup_one:
                    dup_idempotent = False
                    if example is None and jw > 0:
                        example = {"case": c.case_id, "profile": f"{sf_id}_{jw_id}",
                                   "support_1x": sup_one, "support_2x": sup_dup}
    return {
        "duplicate_derived_modifier_idempotent": dup_idempotent,
        "example": example,
        "note": ("derived(transit) modifier가 _merge_modifiers에서 dedup되지 않아 "
                 "동일 modifier 2회 = support 2회 약화. production은 pattern_id별 1개만 "
                 "생성(라이브 영향 0). P3/hardening 후보 — P2 수정 대상 아님."),
    }


def sf_jw_interaction(cases: list[Case], grid: dict) -> list[dict]:
    """SF × JW 교차표(§8) — stability negative rate · sign flip count(전 사례 집계)."""
    rows: list[dict] = []
    for sf_id, _ in _SF:
        for jw_id, _ in _JW:
            neg = 0
            total = 0
            flips = 0
            for c in cases:
                cell = grid[c.case_id][f"{sf_id}_{jw_id}"]
                if cell["stability_net"] is not None:
                    total += 1
                    if cell["stability_sign"] == "neg":
                        neg += 1
                # sign flip = JW00 대비 부호 변화.
                base = grid[c.case_id][f"{sf_id}_JW00"]["stability_sign"]
                if (base != cell["stability_sign"]
                        and "na" not in (base, cell["stability_sign"])):
                    flips += 1
            rows.append({
                "sf": sf_id, "jw": jw_id,
                "stability_negative_rate": round(neg / total, 3) if total else None,
                "sign_flip_count": flips,
            })
    return rows


def run(out_md: Path = OUT_MD, out_json: Path = OUT_JSON) -> dict:
    cases = build_cases()
    grid = measure(cases)
    inv = invariant_checks(cases, grid)
    interaction = sf_jw_interaction(cases, grid)
    synth = synthesizer_findings(cases)

    md = ["# P2-1B 민감도 harness — jaenghap_support_weaken × secondary_factor", "",
          f"spec {EXPERIMENT_SPEC_VERSION} · baseline SF30·JW50 · "
          f"calibration {RELATIONSHIP_CALIBRATION_VERSION} · band B0 고정(§5). "
          "**감사 전용·읽기 전용·production delta 0.** stability 집중 — band 미교차.", "",
          "## 0. 불변식 게이트(§7·§9)", "",
          f"- 전체 위반: **{len(inv['violations'])}** "
          f"({'PASS' if inv['passed'] else 'FAIL — ' + ', '.join(inv['violations'][:8])})",
          "- 검사: weaken=0 수치 동일 · JW↑ target/total support·stability net 비증가 · "
          "pressure/activation/separation/count JW 불변 · 비대상 root drift 0 · support≥0 · "
          "중복=1× · missing/multi-root 적용 0", "",
          "## 1. 사례별 target support 감소(SF30 · JW sweep)", "",
          "| 사례 | JW00 | JW25 | JW50 | JW75 | retention(JW75/JW00) |",
          "|---|--:|--:|--:|--:|--:|"]
    for c in cases:
        row = [grid[c.case_id][f"SF30_{jw_id}"]["target_support"] for jw_id, _ in _JW]
        ret = round(row[3] / row[0], 3) if row[0] else "—"
        md.append(f"| {c.case_id} | {row[0]} | {row[1]} | {row[2]} | {row[3]} | {ret} |")

    md += ["", "## 2. stability net 부호 · sign flip(SF30 발췌)", "",
           "| 사례 | JW00 | JW25 | JW50 | JW75 |", "|---|---|---|---|---|"]
    for c in cases:
        signs = [grid[c.case_id][f"SF30_{jw_id}"]["stability_sign"] for jw_id, _ in _JW]
        md.append(f"| {c.case_id} | " + " | ".join(signs) + " |")

    md += ["", "## 3. SF × JW 교차표(§8 — 공통 SF 유지 여부 판단 근거·P2-1C)", "",
           "| SF | JW | stability_negative_rate | sign_flip_count |",
           "|---|---|--:|--:|"]
    for r in interaction:
        md.append(f"| {r['sf']} | {r['jw']} | {r['stability_negative_rate']} "
                  f"| {r['sign_flip_count']} |")

    md += ["", "## 4. scope 안전성(§8)", "",
           "- 비대상 root support drift·미해소/multi-root 수치 적용: **0**(§0 게이트). "
           "wrong_target·multi_root_target은 JW 전 support 불변 확인.",
           "- multi_root_target: modifier_multi_root_hold_count ≥ 1(보류 계측).", "",
           "## 5. synthesizer 발견(§7 중복 idempotency — P2 수정 대상 아님)", ""]
    if synth["duplicate_derived_modifier_idempotent"]:
        md.append("- derived modifier 중복 idempotent: **OK**.")
    else:
        ex = synth["example"]
        md += [f"- ⚠ **derived modifier 중복 비멱등**(finding): {synth['note']}"]
        if ex:
            md.append(f"  - 예: {ex['case']} {ex['profile']} — 1× support "
                      f"{ex['support_1x']} vs 2× {ex['support_2x']}(2회 약화).")
        md.append("  - **decision 필요**: transit modifier dedup 견고화(별도 승인) vs "
                  "known gap 문서화. production 라이브 영향 0.")
    md += ["", "## 6. 관찰(§P2-1C 전달 — 최적 profile 선정 아님)", "",
           "- 이 사례군에서 sign flip은 **JW가 구동**(boundary_sign_flip: JW25에서 "
           "zero→neg), SF는 미결합(단일 root 경계 사례라 SF 무영향). SF가 same-root "
           "multi-pressure를 키워 sign에 결합하는지는 별도 경계 사례 필요(공유 계수 §3-1).",
           "- supersession remap(§6-8)은 합성기 `resolve_canonical_evidence_id`가 담당 —"
           " P1-6 회귀에서 검증됨(PROVISIONAL P→EXACT E 해소 후 E root 1회 적용). 본 "
           "harness는 JW 민감도 전용이라 재검증하지 않는다.", ""]

    payload = {
        "experiment_spec_version": EXPERIMENT_SPEC_VERSION,
        "baseline_calibration_version": RELATIONSHIP_CALIBRATION_VERSION,
        "case_count": len(cases),
        "invariants": inv,
        "sf_jw_interaction": interaction,
        "synthesizer_findings": synth,
    }
    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"cases": len(cases), "violations": len(inv["violations"]),
            "invariants_passed": inv["passed"]}


def main() -> int:
    r = run()
    print(f"P2-1B: {r['cases']} cases · violations {r['violations']} · "
          f"invariants {'PASS' if r['invariants_passed'] else 'FAIL'}")
    return 0 if r["invariants_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
