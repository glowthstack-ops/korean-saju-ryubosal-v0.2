"""P2-1A 민감도 harness — secondary_factor × activation band (RELATIONSHIP_VECTOR_CALIBRATION).

**감사 전용·읽기 전용.** production 경로 delta 0(합성기에 실험 profile 명시 주입 —
전역 monkeypatch 없음). 두 효과를 **분리**해 측정한다(리뷰 §1):

- Raw synthesis 축(secondary_factor 5종, band 고정 B0): activation **raw value** 민감도
  — same-root/cross-root increment·root 구별력·raw ordering inversion.
- Band projection 축(band 4종, secondary_factor 고정 SF30): 동일 raw를 **어떻게 분류**
  하는지 — band 분포·transition·collapse·near-threshold·root=N strong rate.

세 데이터 분모(불변식 fixture / 합성 lattice / 331 harness)는 **합치지 않는다**(§3).
baseline = P2A_SF30_B0가 production BASELINE과 byte-identical(§14)이 최우선 게이트.
자동 최적 profile 선정 없음(§12) — P2-1B/C 범위 축소용 관찰 자료.

산출: P2_1A_SENSITIVITY_REPORT.md + p2_1a_invariant_results.json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from saju_engines.relationship_effect_vector import (
    RELATIONSHIP_CALIBRATION_VERSION,
    RelationshipVectorCalibration,
    synthesize_relationship_effect_vector,
)
from saju_engines.spouse_palace_activation import (
    SpousePalaceHit,
    build_spouse_palace_vector,
)
from saju_shared_types.event_engine import Pillar4, RelationKind
from saju_shared_types.relationship_effect import AxisStatus

_DICTS = Path(__file__).resolve().parents[3] / "dictionaries"
OUT_MD = Path(__file__).resolve().parent / "P2_1A_SENSITIVITY_REPORT.md"
OUT_JSON = Path(__file__).resolve().parent / "p2_1a_invariant_results.json"

EXPERIMENT_SPEC_VERSION = "p2.1a.v1"
_PERIOD = "2027"

# secondary_factor 축(band 고정 B0) · band 축(SF 고정 0.30).
_SF = [("SF00", 0.0), ("SF15", 0.15), ("SF30", 0.3), ("SF45", 0.45), ("SF60", 0.6)]
_BANDS = [
    ("B0", {"weak": 6.0, "moderate": 12.0, "strong": 20.0}),
    ("B1", {"weak": 6.0, "moderate": 15.0, "strong": 24.0}),
    ("B2", {"weak": 8.0, "moderate": 16.0, "strong": 26.0}),
    ("B3", {"weak": 10.0, "moderate": 18.0, "strong": 28.0}),
]
_BASELINE_SF = 0.3
_NEAR_THRESHOLD_EPS = 0.5   # metric version에 고정(§8)

# 운 글자 pool(서로 다른 root = 서로 다른 지지 글자).
_GLYPHS = ["未", "戌", "申", "午", "卯", "子"]


def _hit(kind: RelationKind, glyph: str, natal: str = "丑") -> SpousePalaceHit:
    return SpousePalaceHit(
        kind=kind, palace=Pillar4.DAY, layer="sewoon", position="branch",
        transit_component="branch", transit_participant=glyph,
        natal_participant=natal)


def _evidences(hits: list[SpousePalaceHit]):
    return build_spouse_palace_vector(hits, _DICTS, period_key=_PERIOD).evidences


@dataclass
class LatticeCase:
    case_id: str
    partition: str            # lattice | fixture
    structure: str            # single | same_root_pair | cross_root_pair | root_n
    expected_roots: int
    hits: list[SpousePalaceHit]
    # paired 비교용(같은 kind pair의 same/cross 대응) — increment 계산.
    pair_key: str | None = None
    pair_role: str | None = None   # single_a | single_b | same | cross


_KINDS = [RelationKind.HAP, RelationKind.CHUNG, RelationKind.HYEONG,
          RelationKind.PA, RelationKind.HAE]
# 같은 root 2-kind pair(의미 있는 조합) — same/cross 대응 생성.
_PAIRS = [
    (RelationKind.CHUNG, RelationKind.HYEONG),
    (RelationKind.CHUNG, RelationKind.PA),
    (RelationKind.CHUNG, RelationKind.HAE),
    (RelationKind.HYEONG, RelationKind.PA),
    (RelationKind.HAP, RelationKind.CHUNG),
    (RelationKind.HAP, RelationKind.HYEONG),
]


def build_lattice() -> list[LatticeCase]:
    cases: list[LatticeCase] = []
    # 단일 kind(§9).
    for k in _KINDS:
        cases.append(LatticeCase(
            case_id=f"single_{k.value}", partition="lattice", structure="single",
            expected_roots=1, hits=[_hit(k, _GLYPHS[0])]))
    # same-root / cross-root paired(§4·§9).
    for a, b in _PAIRS:
        pk = f"{a.value}+{b.value}"
        cases.append(LatticeCase(
            case_id=f"single_{pk}_a", partition="lattice", structure="single",
            expected_roots=1, hits=[_hit(a, _GLYPHS[0])],
            pair_key=pk, pair_role="single_a"))
        cases.append(LatticeCase(
            case_id=f"single_{pk}_b", partition="lattice", structure="single",
            expected_roots=1, hits=[_hit(b, _GLYPHS[0], natal="辰")],
            pair_key=pk, pair_role="single_b"))
        # same root: 같은 운 글자(未)가 두 kind 유발.
        cases.append(LatticeCase(
            case_id=f"same_{pk}", partition="lattice", structure="same_root_pair",
            expected_roots=1,
            hits=[_hit(a, _GLYPHS[0], natal="丑"), _hit(b, _GLYPHS[0], natal="辰")],
            pair_key=pk, pair_role="same"))
        # cross root: 서로 다른 운 글자.
        cases.append(LatticeCase(
            case_id=f"cross_{pk}", partition="lattice", structure="cross_root_pair",
            expected_roots=2,
            hits=[_hit(a, _GLYPHS[0], natal="丑"), _hit(b, _GLYPHS[1], natal="辰")],
            pair_key=pk, pair_role="cross"))
    # root 수 증가(1~4, 대표 kind=CHUNG, 서로 다른 글자).
    for n in (1, 2, 3, 4):
        cases.append(LatticeCase(
            case_id=f"root_{n}", partition="lattice", structure="root_n",
            expected_roots=n,
            hits=[_hit(RelationKind.CHUNG, _GLYPHS[i], natal="丑") for i in range(n)]))
    return cases


def _cal(sf: float, band: dict[str, float]) -> RelationshipVectorCalibration:
    return RelationshipVectorCalibration.shared(
        profile_id=f"P2A_sf{sf}_b{band['strong']}",
        secondary_factor=sf, activation_band=band)


def _act(case: LatticeCase, sf: float, band: dict[str, float]):
    return synthesize_relationship_effect_vector(
        _evidences(case.hits), calibration=_cal(sf, band)).axes


# ── Raw synthesis 축 (secondary_factor sweep, band 고정 B0) ───────────────────
def raw_sweep(cases: list[LatticeCase]) -> dict:
    b0 = dict(_BANDS[0][1])
    # case별 SF별 activation raw.
    raw: dict[str, dict[str, float | None]] = {}
    for c in cases:
        raw[c.case_id] = {}
        for sf_id, sf in _SF:
            ax = _act(c, sf, b0)
            raw[c.case_id][sf_id] = (
                ax.activation.value if ax.activation.status is AxisStatus.EVALUATED
                else None)
    # same/cross increment(§4) — pair_key별.
    pairs: dict[str, dict[str, str]] = {}
    for c in cases:
        if c.pair_key and c.pair_role:
            pairs.setdefault(c.pair_key, {})[c.pair_role] = c.case_id
    increments: list[dict] = []
    for pk, roles in sorted(pairs.items()):
        if not {"single_a", "single_b", "same", "cross"} <= roles.keys():
            continue
        row: dict = {"pair": pk}
        for sf_id, _ in _SF:
            va = raw[roles["single_a"]][sf_id] or 0.0
            vb = raw[roles["single_b"]][sf_id] or 0.0
            vsame = raw[roles["same"]][sf_id] or 0.0
            vcross = raw[roles["cross"]][sf_id] or 0.0
            vprim = max(va, vb)
            same_inc = vsame - vprim
            cross_inc = vcross - vprim
            margin = cross_inc - same_inc
            row[sf_id] = {
                "same_inc": round(same_inc, 3),
                "cross_inc": round(cross_inc, 3),
                "margin": round(margin, 3),
                # 정규화 지표(§2) — 절대 margin은 kind 강도에 좌우되므로 비율 병기.
                "retention": round(margin / cross_inc, 3) if cross_inc else None,
                "same_cross_ratio": (
                    round(same_inc / cross_inc, 3) if cross_inc else None),
            }
        increments.append(row)
    # raw pairwise ordering inversion vs baseline SF30(§6).
    baseline = {cid: v["SF30"] for cid, v in raw.items()}
    ordered_cases = [c.case_id for c in cases]
    inversions: dict[str, int] = {}
    for sf_id, _ in _SF:
        inv = 0
        for i in range(len(ordered_cases)):
            for j in range(i + 1, len(ordered_cases)):
                bi, bj = baseline[ordered_cases[i]], baseline[ordered_cases[j]]
                si = raw[ordered_cases[i]][sf_id]
                sj = raw[ordered_cases[j]][sf_id]
                if bi is None or bj is None or si is None or sj is None:
                    continue
                if (bi - bj) * (si - sj) < 0:   # 순서 뒤집힘
                    inv += 1
        inversions[sf_id] = inv
    return {"raw_by_case": raw, "increments": increments,
            "raw_pairwise_inversion": inversions}


def axis_sf_impact(cases: list[LatticeCase]) -> dict:
    """구조별 SF 영향 축 관측(§4) — SF00↔SF60에서 축 value가 **어느 사례에서든**
    바뀌면 '있음'(구조 내 OR — 대표 1건이 아니라 구조 전체 기준)."""
    b0 = dict(_BANDS[0][1])
    out: dict[str, dict[str, bool]] = {}
    for c in cases:
        lo = synthesize_relationship_effect_vector(
            _evidences(c.hits), calibration=_cal(0.0, b0))
        hi = synthesize_relationship_effect_vector(
            _evidences(c.hits), calibration=_cal(0.6, b0))
        sup_lo = round(sum(r.stability_support for r in lo.root_contributions), 3)
        sup_hi = round(sum(r.stability_support for r in hi.root_contributions), 3)
        cur = out.setdefault(c.structure, {
            "activation": False, "stability_support": False,
            "stability_net": False, "separation": False})
        cur["activation"] |= lo.axes.activation.value != hi.axes.activation.value
        cur["stability_support"] |= sup_lo != sup_hi
        cur["stability_net"] |= lo.axes.stability.value != hi.axes.stability.value
        cur["separation"] |= (lo.axes.separation_pressure.value
                              != hi.axes.separation_pressure.value)
    return out


# ── Band projection 축 (band sweep, SF 고정 baseline) ─────────────────────────
def band_sweep(cases: list[LatticeCase]) -> dict:
    # 동일 raw(SF30)에 B0~B3 적용 → band 분류.
    band_of: dict[str, dict[str, str | None]] = {}
    for c in cases:
        band_of[c.case_id] = {}
        for b_id, band in _BANDS:
            ax = _act(c, _BASELINE_SF, band)
            band_of[c.case_id][b_id] = (
                ax.activation.band if ax.activation.status is AxisStatus.EVALUATED
                else None)
    # band 분포(profile별).
    dist: dict[str, dict[str, int]] = {}
    for b_id, _ in _BANDS:
        d: dict[str, int] = {}
        for c in cases:
            bb = band_of[c.case_id][b_id]
            if bb is not None:
                d[bb] = d.get(bb, 0) + 1
        dist[b_id] = d
    # B0 대비 transition(§6) — 보수화 방향만 허용(strong→moderate 등).
    _rank = {"strong": 3, "moderate": 2, "weak": 1, "low": 0}
    transitions: dict[str, dict[str, int]] = {}
    reverse_violations = 0
    for b_id, _ in _BANDS:
        if b_id == "B0":
            continue
        tm: dict[str, int] = {}
        for c in cases:
            f, t = band_of[c.case_id]["B0"], band_of[c.case_id][b_id]
            if f is None or t is None:
                continue
            if f != t:
                tm[f"{f}->{t}"] = tm.get(f"{f}->{t}", 0) + 1
                if _rank[t] > _rank[f]:      # 역방향(보수화 위반)
                    reverse_violations += 1
        transitions[b_id] = tm
    # near-threshold(§8) — baseline SF30·B0 raw 기준.
    b0 = dict(_BANDS[0][1])
    near: dict[str, int] = {"weak": 0, "moderate": 0, "strong": 0}
    for c in cases:
        ax = _act(c, _BASELINE_SF, b0)
        if ax.activation.status is not AxisStatus.EVALUATED or ax.activation.value is None:
            continue
        v = ax.activation.value
        for name, thr in b0.items():
            if abs(v - thr) <= _NEAR_THRESHOLD_EPS:
                near[name] += 1
    # root=N strong rate(§5) — 분모 = root=N & activation EVALUATED. SF·B별.
    strong_rate: dict[str, dict[str, dict]] = {}
    for sf_id, sf in _SF:
        strong_rate[sf_id] = {}
        for b_id, band in _BANDS:
            by_root: dict[int, list[int]] = {}
            for c in cases:
                ax = _act(c, sf, band)
                if ax.activation.status is not AxisStatus.EVALUATED:
                    continue
                lst = by_root.setdefault(c.expected_roots, [])
                lst.append(1 if ax.activation.band == "strong" else 0)
            strong_rate[sf_id][b_id] = {
                f"root_{r}": {"n": len(v), "strong": sum(v),
                              "rate": round(sum(v) / len(v), 3) if v else None}
                for r, v in sorted(by_root.items())}
    # band collapse(§3·§4) — 한 band에 몰리는 비율(최대 band share / 전체).
    collapse: dict[str, float] = {}
    for b_id, _ in _BANDS:
        d = dist[b_id]
        total = sum(d.values())
        collapse[b_id] = round(max(d.values()) / total, 3) if total else 0.0
    return {"band_of_case": band_of, "band_distribution": dist,
            "band_transitions_vs_b0": transitions,
            "band_reverse_violations": reverse_violations,
            "near_threshold_b0": near, "strong_rate_grid": strong_rate,
            "band_collapse": collapse}


# ── 불변식 게이트 (§10·§11·§14) ──────────────────────────────────────────────
def invariant_checks(cases: list[LatticeCase]) -> dict:
    results: dict = {"violations": []}

    def viol(msg: str) -> None:
        results["violations"].append(msg)

    # (§14) baseline P2A_SF30_B0 == production BASELINE(byte-identical).
    for c in cases:
        ev = _evidences(c.hits)
        base = synthesize_relationship_effect_vector(ev)  # production BASELINE
        p2a = synthesize_relationship_effect_vector(
            ev, calibration=_cal(0.3, dict(_BANDS[0][1])))
        if base.model_dump() != p2a.model_dump():
            viol(f"baseline_identity:{c.case_id}")

    # (§10 정정) secondary_factor는 **공유 same-root 복합 계수**다(spec §3
    # affected_axes=[activation,stability,separation] — 코드 _primary_plus_secondary가
    # 세 축에 동일 적용). 리뷰 §10의 'activation 전용' 가정은 이 코드베이스와 다르다.
    # 따라서 올바른 불변식: ①single-kind 사례는 SF 전 불변(복합 대상 없음) ②status·
    # evidence/root count·stability_support(순수 sum, SF 무관)는 전 사례 SF 불변.
    b0 = dict(_BANDS[0][1])
    for c in cases:
        ref_full = synthesize_relationship_effect_vector(
            _evidences(c.hits), calibration=_cal(0.3, b0))
        ref_ax = ref_full.axes
        ref_support = round(
            sum(rc.stability_support for rc in ref_full.root_contributions), 3)
        for sf_id, sf in _SF:
            full = synthesize_relationship_effect_vector(
                _evidences(c.hits), calibration=_cal(sf, b0))
            ax = full.axes
            # ① single-kind → SF 전 축 불변(복합 없음).
            if c.structure == "single" and ax.model_dump() != ref_ax.model_dump():
                viol(f"sf_changed_single_kind:{c.case_id}:{sf_id}")
            # ② 전 사례: status·count·stability_support는 SF 무관.
            if ax.activation.status is not ref_ax.activation.status:
                viol(f"sf_changed_activation_status:{c.case_id}:{sf_id}")
            if full.evidence_count != ref_full.evidence_count:
                viol(f"sf_changed_evidence_count:{c.case_id}:{sf_id}")
            if full.independent_root_trigger_count != ref_full.independent_root_trigger_count:
                viol(f"sf_changed_root_count:{c.case_id}:{sf_id}")
            support = round(
                sum(rc.stability_support for rc in full.root_contributions), 3)
            if support != ref_support:
                viol(f"sf_changed_stability_support:{c.case_id}:{sf_id}")

    # (§11) band profile은 activation band만 — raw value/root/stability/sep 불변.
    for c in cases:
        full = synthesize_relationship_effect_vector(
            _evidences(c.hits), calibration=_cal(0.3, b0))
        ref_v = full.axes.activation.value
        ref_roots = full.independent_root_trigger_count
        ref_ec = full.evidence_count
        for b_id, band in _BANDS:
            r = synthesize_relationship_effect_vector(
                _evidences(c.hits), calibration=_cal(0.3, band))
            if r.axes.activation.value != ref_v:
                viol(f"band_changed_raw:{c.case_id}:{b_id}")
            if r.independent_root_trigger_count != ref_roots:
                viol(f"band_changed_roots:{c.case_id}:{b_id}")
            if r.evidence_count != ref_ec:
                viol(f"band_changed_evidence:{c.case_id}:{b_id}")
            if r.axes.stability.model_dump() != full.axes.stability.model_dump():
                viol(f"band_changed_stability:{c.case_id}:{b_id}")

    # (§9) expected_roots 검증(lattice 구성 정확성).
    for c in cases:
        r = synthesize_relationship_effect_vector(_evidences(c.hits))
        if r.independent_root_trigger_count != c.expected_roots:
            viol(f"root_count_mismatch:{c.case_id}:"
                 f"{r.independent_root_trigger_count}!={c.expected_roots}")

    results["passed"] = not results["violations"]
    return results


def _fmt_increments(increments: list[dict]) -> list[str]:
    lines = ["| pair | SF | same_inc | cross_inc | margin | retention | same/cross |",
             "|---|---|--:|--:|--:|--:|--:|"]
    for row in increments:
        for sf_id, _ in _SF:
            d = row[sf_id]
            lines.append(
                f"| {row['pair']} | {sf_id} | {d['same_inc']} | {d['cross_inc']} "
                f"| {d['margin']} | {d['retention']} | {d['same_cross_ratio']} |")
    return lines


def run(out_md: Path = OUT_MD, out_json: Path = OUT_JSON) -> dict:
    cases = build_lattice()
    raw = raw_sweep(cases)
    band = band_sweep(cases)
    axis_impact = axis_sf_impact(cases)
    inv = invariant_checks(cases)

    md = ["# P2-1A 민감도 harness — secondary_factor × activation band", "",
          f"spec {EXPERIMENT_SPEC_VERSION} · baseline calibration "
          f"{RELATIONSHIP_CALIBRATION_VERSION} · lattice {len(cases)} case. "
          "**감사 전용·읽기 전용·production delta 0.** 두 효과 분리(raw synthesis / "
          "band projection). 자동 최적 profile 선정 없음(§12).", "",
          "## 0. 불변식 게이트", "",
          f"- baseline P2A_SF30_B0 == production BASELINE: "
          f"{'OK' if inv['passed'] or not any(v.startswith('baseline') for v in inv['violations']) else 'FAIL'}",
          f"- band 보수화 역방향 위반: {band['band_reverse_violations']}",
          f"- 전체 위반: **{len(inv['violations'])}** "
          f"({'PASS' if inv['passed'] else 'FAIL — ' + ', '.join(inv['violations'][:8])})",
          "",
          "## 1. Raw synthesis 축 (secondary_factor sweep · band 고정 B0)", "",
          "### 축별 SF 영향(§4 — 구조별 SF00↔SF60 value 변화)", "",
          "| 구조 | activation | stability_support | stability_net | separation |",
          "|---|---|---|---|---|"]
    for struct in ("single", "same_root_pair", "cross_root_pair", "root_n"):
        if struct in axis_impact:
            a = axis_impact[struct]
            md.append(
                f"| {struct} | {'있음' if a['activation'] else '없음'} "
                f"| {'있음' if a['stability_support'] else '없음'} "
                f"| {'있음' if a['stability_net'] else '없음'} "
                f"| {'있음' if a['separation'] else '없음'} |")
    md += ["", "> single-kind는 전 축 SF 불변(복합 없음). same-root는 activation·"
           "stability_net·separation 변동(stability_support는 순수 sum이라 불변). "
           "cross-root는 서로 다른 root라 SF 미적용.", "",
           "### same-root / cross-root increment(§4·§2 정규화 병기)", "",
           "> same_inc = V_same − max(V_a,V_b) · cross_inc = V_cross − max(V_a,V_b) · "
           "margin = cross−same · retention = margin/cross_inc · "
           "same/cross = same_inc/cross_inc. 기대: same_inc≥0 · cross_inc≥same_inc "
           "(SF00에서 same_inc=0). retention↓ = root 구별력 침식.", ""]
    md += _fmt_increments(raw["increments"])
    md += ["", "### raw pairwise ordering inversion vs SF30(§6)", "",
           "> band threshold는 raw ordering을 바꾸지 못한다 — 이 값은 순수 raw 효과.", "",
           "| SF | raw_inversion |", "|---|--:|"]
    for sf_id, _ in _SF:
        md.append(f"| {sf_id} | {raw['raw_pairwise_inversion'][sf_id]} |")

    md += ["", "## 2. Band projection 축 (band sweep · SF 고정 0.30)", "",
           "### band 분포 + collapse(§3·§4 — collapse = 최대 band 점유율)", "",
           "| profile | 분포 | collapse |", "|---|---|--:|"]
    for b_id, _ in _BANDS:
        md.append(f"| {b_id} | {json.dumps(band['band_distribution'][b_id], ensure_ascii=False)} "
                  f"| {band['band_collapse'][b_id]} |")
    md += ["", "### B0 대비 band transition(§6 — 보수화 방향만 허용)", "",
           "| profile | transition | (역방향 위반은 §0 게이트) |", "|---|---|---|"]
    for b_id, _ in _BANDS:
        if b_id == "B0":
            continue
        md.append(f"| {b_id} | {json.dumps(band['band_transitions_vs_b0'][b_id], ensure_ascii=False)} | |")
    md += ["", "### near-threshold(§8 · |v−thr|≤0.5 · SF30/B0)", "",
           f"weak {band['near_threshold_b0']['weak']} · "
           f"moderate {band['near_threshold_b0']['moderate']} · "
           f"strong {band['near_threshold_b0']['strong']}", "",
           "### root=N strong rate(§5 · 분모=root=N & EVALUATED · SF30 발췌)", "",
           "| band | root별 rate |", "|---|---|"]
    for b_id, _ in _BANDS:
        md.append(f"| {b_id} | {json.dumps(band['strong_rate_grid']['SF30'][b_id], ensure_ascii=False)} |")

    md += ["", "## 3. 핵심 발견 — secondary_factor는 공유 계수", "",
           "> **리뷰 §10의 'activation 전용' 가정과 코드가 다르다.** secondary_factor는 "
           "`_primary_plus_secondary`로 **activation·stability_pressure·separation 세 축의 "
           "same-root 복합에 동일 적용**된다(spec §3 affected_axes에 이미 명시). 따라서 "
           "P2-1A raw sweep은 activation뿐 아니라 same-root 사례의 stability(net)·separation "
           "value도 함께 움직인다. stability_support(순수 sum)·status·root/evidence count는 "
           "SF 불변임을 게이트로 확인했다.", "",
           "> **함의(P2-1C 전달)**: secondary_factor를 축별로 분리할지(activation vs "
           "stability/separation 별도 계수) 여부는 P2 캘리브레이션 결정 사항이다. 현 단계는 "
           "공유 계수 사실을 확정·관측만 한다(수정 없음).", "",
           "## 4. 관찰 분류(§12 — 최적 profile 선정 아님)", "",
           "- 이 결과는 P2-1B(쟁합)·P2-1C(kind/stability/separation OAT) 실험 범위를 "
           "좁히는 자료다. baseline 대비 raw·band 민감도가 큰 SF·profile을 표시하되 "
           "운영 채택 후보로 선정하지 않는다.",
           "- 분모 분리(§3): 본 표는 **lattice** 전용. 331 harness·불변식 fixture와 "
           "합산 금지.", ""]

    payload = {
        "experiment_spec_version": EXPERIMENT_SPEC_VERSION,
        "baseline_calibration_version": RELATIONSHIP_CALIBRATION_VERSION,
        "lattice_case_count": len(cases),
        "invariants": inv,
        "raw_pairwise_inversion": raw["raw_pairwise_inversion"],
        "band_distribution": band["band_distribution"],
        "band_reverse_violations": band["band_reverse_violations"],
        "near_threshold_b0": band["near_threshold_b0"],
    }
    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"cases": len(cases), "violations": len(inv["violations"]),
            "invariants_passed": inv["passed"]}


def main() -> int:
    r = run()
    print(f"P2-1A: {r['cases']} cases · violations {r['violations']} · "
          f"invariants {'PASS' if r['invariants_passed'] else 'FAIL'}")
    return 0 if r["invariants_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
