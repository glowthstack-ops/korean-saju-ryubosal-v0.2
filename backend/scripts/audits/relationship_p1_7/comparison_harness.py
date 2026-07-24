"""P1-7b 결정적 비교 harness — 벡터 ↔ legacy 관찰 지도 (RELATIONSHIP_EVENT_SYSTEM 부록 D).

**감사 전용·읽기 전용**: score/rank/candidate/payload를 건드리지 않는다. exact 벡터와
legacy 후보를 전부 확보해 기간·family·축 단위로 분류하고 매트릭스(§4)를 만든다.
production telemetry로는 원인을 재구성할 수 없으므로(원문 미보존), 이상 bucket은 이
결정적 fixture 경로에서 상세 분석한다(§9 이중 경로 중 deterministic 쪽).

산출: REPORT.md — findings만(수정 없음, §10·§11f). LLM·리포트·가드 미노출.

stratification(§8): 성별 × 일간 음양 × 후보 family × 층위 × root × kind × MT2 발화 ×
cap × 후보 유무. MT1·MT2 성별/일간 비대칭이 비교 결과에 섞이지 않게 분리 집계한다.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_api.services.relationship_legacy_comparison import (
    REL_COMPARISON_FAMILIES,
    FamilyLegacyObservation,
    LegacyVectorComparisonRecord,
    PeriodComparisonInput,
    classify_period,
)
from saju_api.services.relationship_vector_sidecar import synthesize_period_vector
from saju_api.services.relationship_vector_telemetry import (
    AuditProjectionStatus,
    classify_kind_combo,
)
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.marriage_emergence_modifier import analyze_marriage_emergence_natal
from saju_engines.marriage_timing_profile import marriage_engine_flags
from saju_engines.relationship_structure_modifiers import (
    build_relationship_structure_modifiers,
)
from saju_engines.structure_patterns import detect_structure_patterns
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[3] / "dictionaries"
OUT = Path(__file__).resolve().parent / "REPORT.md"
_CAP = 22.0
_YANG_STEMS = frozenset("甲丙戊庚壬")

# stratification fixture(성별·일간 음양 다양성) — 결정적 감사 표본(§8).
_FIXTURES = [
    ("F1", BirthInput(calendar_type="solar", birth_date=date(1985, 3, 15),
                      birth_time="14:30", birth_place_name="서울", gender="female")),
    ("M1", BirthInput(calendar_type="solar", birth_date=date(1988, 6, 20),
                      birth_time="09:00", birth_place_name="서울", gender="male")),
    ("F2", BirthInput(calendar_type="solar", birth_date=date(1992, 11, 5),
                      birth_time="22:00", birth_place_name="부산", gender="female")),
    ("M2", BirthInput(calendar_type="solar", birth_date=date(1979, 2, 14),
                      birth_time="06:00", birth_place_name="서울", gender="male")),
    # 성별↔음양 공선성 해소(§8) — 음일간 남성 · 양일간 여성.
    ("M3y", BirthInput(calendar_type="solar", birth_date=date(1990, 1, 10),
                       birth_time="10:00", birth_place_name="서울", gender="male")),
    ("F3y", BirthInput(calendar_type="solar", birth_date=date(1993, 12, 1),
                       birth_time="10:00", birth_place_name="서울", gender="female")),
]
_TODAY = date(2026, 7, 24)


class _LegacyDelta:
    """legacy relation precap 재현(cap 이전) — case22 방식(RelationPalaceEngine 산식)."""

    def __init__(self) -> None:
        from saju_engines.relation_palace_engine import RelationPalaceEngine
        rp = RelationPalaceEngine(_DICTS)
        self.palace = rp._palace
        self.rel_bonus = rp._rel_bonus
        self.layer_w = rp._layer_w
        self.palace_mult = rp._palace_mult
        self.rel_palace_events: dict[tuple[str, str], set[str]] = {}
        for r in rp._rel_to_palace:
            self.rel_palace_events.setdefault(
                (r["relation"], r["target_palace"]), set()).update(r["likely_events"])

    def precap(self, activations, family: str) -> float:
        """한 family의 relation precap(cap·MT4 제외) — 활성 primitive에서 계산."""
        total = 0.0
        for a in activations:
            pinfo = self.palace[a.palace]
            in_domain = family in pinfo["event_domains"]
            likely = family in self.rel_palace_events.get((a.kind, a.palace), set())
            if not (in_domain or likely):
                continue
            b = self.rel_bonus[a.kind] * float(pinfo["activation_weight"])
            b *= self.layer_w.get(f"{a.layer}_to_natal", 1.0)
            b *= self.palace_mult[a.palace][a.position]
            if likely:
                b *= 1.2
            total += b
        return total


def _family_observations(
    activations, present_families: set[str], ld: _LegacyDelta,
) -> list[FamilyLegacyObservation]:
    out: list[FamilyLegacyObservation] = []
    for fam in REL_COMPARISON_FAMILIES:
        precap = ld.precap(activations, fam)
        out.append(FamilyLegacyObservation(
            event_family=fam,
            candidate_present=fam in present_families,
            relation_delta=min(precap, _CAP),
            relation_precap=round(precap, 3),
            relation_capped=precap > _CAP,
        ))
    return out


def _collect(ld: _LegacyDelta) -> tuple[list, list[dict]]:
    """전 fixture 비교 record + strata 메타 수집."""
    records: list[LegacyVectorComparisonRecord] = []
    strata: list[dict] = []
    for tag, birth in _FIXTURES:
        chart = calculate(birth.model_copy(update={"reference_date": _TODAY}))
        assert chart.pillars is not None and chart.pillars.day is not None
        day_stem = chart.pillars.day.stem
        yinyang = "yang" if day_stem in _YANG_STEMS else "yin"
        eng = EventEngineV2(_DICTS, **marriage_engine_flags())
        scored = eng.score(chart, levels={GanjiLevel.YEAR, GanjiLevel.MONTH})
        projections = eng.take_relationship_shadow()
        # period 라벨 → 그 기간 존재하는 REL family 집합.
        present_by_period: dict[str, set[str]] = {}
        for c in scored:
            if str(c.event_key) in REL_COMPARISON_FAMILIES:
                present_by_period.setdefault(c.period, set()).add(str(c.event_key))
        natal_mt2 = analyze_marriage_emergence_natal(chart)
        static_mods = build_relationship_structure_modifiers(
            detect_structure_patterns(chart, dictionaries_dir=_DICTS))
        for proj in projections:
            try:
                vec = synthesize_period_vector(
                    proj, chart, natal_mt2, static_mods, dictionaries_dir=_DICTS)
            except Exception:  # noqa: BLE001 — 기간 실패는 감사에서 스킵(집계 제외)
                continue
            fams = _family_observations(
                proj.activations, present_by_period.get(proj.label, set()), ld)
            audit = (AuditProjectionStatus.SUCCESS
                     if any(f.candidate_present for f in fams)
                     else AuditProjectionStatus.NO_CANDIDATE)
            recs = classify_period(PeriodComparisonInput(
                vector=vec, period_layer=proj.layer, subject_scope="self",
                vector_run_id=f"{tag}:{proj.layer}:{proj.label}", audit_status=audit,
                families=fams))
            for r in recs:
                records.append(r)
                strata.append({
                    "fixture": tag, "gender": birth.gender, "day_yinyang": yinyang,
                    "layer": proj.layer,
                    "mt2_fire": bool(natal_mt2.emerged) and any(
                        e.stem == proj.luck_stem for e in natal_mt2.emerged),
                    "kind_combo": classify_kind_combo(vec).value,
                })
    return records, strata


def _matrix_root_cap(records) -> dict:
    """A. root 수 × legacy cap(§4-A)."""
    m: dict[str, dict[str, int]] = {}
    for r in records:
        row = m.setdefault(r.root_count_bucket, {"cap": 0, "no_cap": 0, "cap_unknown": 0})
        if r.legacy_capped is True:
            row["cap"] += 1
        elif r.legacy_capped is False:
            row["no_cap"] += 1
        else:
            row["cap_unknown"] += 1
    return m


def _matrix_kind_family(records) -> dict:
    """B. KindCombo × 후보 family — 후보 생성률(§4-B)."""
    m: dict[str, dict[str, int]] = {}
    for r in records:
        if r.legacy_event_family is None:
            continue
        row = m.setdefault(r.kind_combo.value, {f: 0 for f in REL_COMPARISON_FAMILIES})
        if r.legacy_candidate_present:
            row[r.legacy_event_family] += 1
    return m


def _matrix_axis_direction(records) -> dict:
    """C. 벡터 축(stability 부호) × legacy delta 방향(§4-C)."""
    m: dict[str, Counter] = {}
    for r in records:
        key = f"stab={r.stability_bucket or 'na'}/sep={r.separation_status.value}"
        c = m.setdefault(key, Counter())
        c[r.legacy_relation_delta_bucket or "delta_na"] += 1
    return {k: dict(v) for k, v in m.items()}


def _md_table(title: str, matrix: dict, cols: list[str]) -> list[str]:
    lines = [f"### {title}", "", "| row | " + " | ".join(cols) + " |",
             "|---|" + "|".join("---" for _ in cols) + "|"]
    for row_key in sorted(matrix):
        row = matrix[row_key]
        cells = [str(row.get(c, 0)) for c in cols]
        lines.append(f"| {row_key} | " + " | ".join(cells) + " |")
    return [*lines, ""]


def build_records() -> tuple[list[LegacyVectorComparisonRecord], list[dict]]:
    """전 fixture 비교 record + strata(테스트·재사용 진입점)."""
    return _collect(_LegacyDelta())


def main(out_path: Path = OUT) -> int:
    records, strata = build_records()
    n = len(records)
    cls_dist = Counter(r.comparison_class.value for r in records)
    absent_sub = Counter(
        r.candidate_absent_subclass.value for r in records
        if r.candidate_absent_subclass is not None)
    # 중첩 독립 finding 카운터(§2·§3) — 합계 ≠ record 수(현상 중첩 보존).
    finding_dist: Counter = Counter()
    for r in records:
        finding_dist.update(f.value for f in r.findings)
    # stratification 교차(성별·일간 음양별 class 분포).
    by_gender: dict[str, Counter] = {}
    by_yinyang: dict[str, Counter] = {}
    for r, s in zip(records, strata, strict=True):
        by_gender.setdefault(s["gender"], Counter())[r.comparison_class.value] += 1
        by_yinyang.setdefault(s["day_yinyang"], Counter())[r.comparison_class.value] += 1

    md = ["# P1-7b 결정적 비교 harness — 관찰 지도 (2026-07-24)", "",
          f"fixture {len(_FIXTURES)}종(성별·일간 음양 stratified) · 비교 record {n}건. "
          "**감사 전용 — 수정 없음.** legacy relation delta와 P1 activation은 동일 척도가 "
          "아니다(유무·방향·cap·root·kind 우선, delta는 bucket 보조).", "",
          "## 비교 class 분포", "",
          "| class | count |", "|---|--:|"]
    for k, v in cls_dist.most_common():
        md.append(f"| {k} | {v} |")
    md += ["", "### 후보 부재 세분(§7 — 오류 아님, P3 검토 신호)", "",
           "| subclass(대표값) | count |", "|---|--:|"]
    for k, v in absent_sub.most_common():
        md.append(f"| {k} | {v} |")

    md += ["", "### 중첩 독립 finding(§2·§3 — 합계≠record 수, 복합 현상 보존)", "",
           "> primary_class 하나가 가리는 현상을 독립 카운터로 집계한다. "
           "strong+multi-root 부재처럼 한 record가 복수 finding을 동시에 갖는다.", "",
           "| finding | count |", "|---|--:|"]
    for k, v in finding_dist.most_common():
        md.append(f"| {k} | {v} |")

    md += ["", "## §4 필수 매트릭스", ""]
    md += _md_table("A. Root 수 × legacy cap", _matrix_root_cap(records),
                    ["cap", "no_cap", "cap_unknown"])
    md += _md_table("B. KindCombo × 후보 family(후보 존재 수)",
                    _matrix_kind_family(records), list(REL_COMPARISON_FAMILIES))
    md += ["### C. 벡터 stability/separation × legacy delta 방향", ""]
    axis_dir = _matrix_axis_direction(records)
    md += ["| 벡터 축 | legacy delta 분포 |", "|---|---|"]
    for k in sorted(axis_dir):
        md.append(f"| {k} | {json.dumps(axis_dir[k], ensure_ascii=False)} |")

    # 성별↔일간 음양 공선성 점검(§8·§9 — 이상 시 fixture 추가 신호).
    gy_pairs = {(s["gender"], s["day_yinyang"]) for s in strata}
    collinear = len({g for g, _ in gy_pairs}) == len({y for _, y in gy_pairs}) and all(
        len({y for g2, y in gy_pairs if g2 == g}) == 1 for g, _ in gy_pairs)

    md += ["", "## stratification(§8)", ""]
    if collinear:
        md += ["> ⚠ 본 fixture 집합에서 성별과 일간 음양이 공선(collinear)이라 아래 두 표가 "
               "동일하다. 성별·음양을 분리하려면 음일간 남성·양일간 여성 명식을 추가해야 "
               "한다(§9 — 이상 bucket 발견 시 결정적 fixture 추가).", ""]
    md += ["### 성별 × class", "",
           "| gender | class 분포 |", "|---|---|"]
    for g in sorted(by_gender):
        md.append(f"| {g} | {json.dumps(dict(by_gender[g]), ensure_ascii=False)} |")
    md += ["", "### 일간 음양 × class", "", "| 음양 | class 분포 |", "|---|---|"]
    for y in sorted(by_yinyang):
        md.append(f"| {y} | {json.dumps(dict(by_yinyang[y]), ensure_ascii=False)} |")

    md += ["", "## findings(관찰만 — 수정은 P2/P3 별도 승인)", "",
           "명칭은 결론을 선점하지 않게 중립 서술한다(§5). 아래는 결정적 재현 관찰이며 "
           "production 빈도는 P1-7d coarse aggregate가 별도 분모로 확인한다(fixture는 "
           "확률 표본 아님 — §11).", "",
           f"- **event family 신호 소비 비대칭**(coverage gap) "
           f"{cls_dist.get('legacy_event_key_blind_spot', 0)}건 — 동일 기간·구조에서 일부 "
           "family만 relation 신호를 소비. 의도된 사건별 계약인지 구현 사각지대인지는 P3 판단.",
           f"- **legacy cap 포화** {cls_dist.get('legacy_cap_saturated', 0)}건 — cap 22는 "
           "복수 root의 복합성뿐 아니라 단일 root 안의 강한 relation kind·원시 강도도 동일 "
           "+22로 압축한다(root=1 cap 포화가 이를 입증 — 매트릭스 A).",
           f"- **벡터 존재·후보 미생성** {cls_dist.get('legacy_candidate_absent', 0)}건 — "
           "legacy ten-god branching gate/신호 소비 공백/P1 activation 범위가 사건 후보보다 "
           "넓음 중 하나일 수 있음. P3 증거 계약·후보 승격 검토(원인은 미확정).",
           f"- **방향 의미 혼합**(review-required) "
           f"{cls_dist.get('review_required_direction_mismatch', 0)}건 — legacy 단일 스칼라에 "
           "관계 활성과 유지 품질이 함께 압축된 현상. 오류 확정 아님 — P1 formalization "
           "미평가라 leakage 판단은 P3 이후.",
           f"- **P1 축 근거 부족** {cls_dist.get('vector_insufficient', 0)}건 — legacy 후보 "
           "있으나 P1 해당 축 미평가(정상 보류 — 0으로 비교하지 않음).",
           ""]
    out_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"written: {out_path} ({n} records)")
    print("class dist:", dict(cls_dist))
    return n


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
