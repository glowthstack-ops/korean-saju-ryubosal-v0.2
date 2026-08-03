"""용신 결정 margin 분포 감사 — MC-A (CAL-ROLE-MARGIN-CENSUS, 2026-08-03).

**측정만 한다.** production resolver 를 그대로 쓰고 점수·선택·출력을 바꾸지 않는다.
runner-up 강제 재생은 MC-B 이며 여기서는 하지 않는다.

`ROLE_CLOSE_MARGIN_V1 = 0.02` 는 지금 근거 없이 서 있는 상수다. 실제 분포를 보기 전에
계약을 설계하면 임계값이 가설을 굳힌다. 그래서 인접 구간을 함께 재고, **정확한 동점과
반올림 동점을 분리**한다.

    raw    useful 테이블의 반올림 전 값(float). Decimal 로 보존한다.
    표시    ElementCandidate.score = round(raw, 4)

    raw margin 0        정확한 동점
    raw margin > 0 인데 표시 점수가 같음   반올림 동점

임계값을 나중에 0.015·0.03 으로 바꿔도 원자료를 다시 돌리지 않도록 raw 를 남긴다.

사용법:
    python scripts/audits/measure_role_margin_census.py --out var/audit/role_margin_census
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
for _path in (_BACKEND / "apps/api", _BACKEND / "packages"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from saju_manse_analysis.yongsin import candidates as cand_mod  # noqa: E402
from saju_manse_analysis.yongsin.role_realization import (  # noqa: E402
    resolve_realized_roles,
)

from saju_api.services import manse_service  # noqa: E402
from saju_api.services.manse_service import calculate  # noqa: E402
from saju_shared_types.birth_input import BirthInput  # noqa: E402

#: 기존 감사와 **같은 모집단**을 쓴다(measure_luck_element_operability_shadow).
#: 무작위 생성은 넣지 않는다 — 코호트가 달라지면 이전 측정과 비교할 수 없다.
FIXTURE_BIRTHS: tuple[tuple[int, int, int, str], ...] = (
    (1980, 11, 22, "09:08"), (1980, 11, 22, "09:40"), (1985, 3, 5, "12:00"),
    (1985, 3, 15, "14:30"), (1985, 4, 18, "16:00"), (1985, 5, 5, "14:00"),
    (1987, 8, 5, "21:00"), (1988, 3, 5, "10:30"), (1990, 3, 3, "10:00"),
    (1990, 3, 15, "10:00"), (1990, 5, 5, "13:30"), (1990, 5, 15, "09:30"),
    (1992, 7, 20, "14:00"),
)
GENDERS: tuple[str, ...] = ("male", "female")

#: 용신 판정은 원국만 쓴다 — 기준일을 바꿔도 결과가 같음을 확인하고 하나로 고정했다.
#: 여러 기준일을 곱하면 같은 행이 3번 들어가 분포가 왜곡된다.
REFERENCE_DATE = date(2026, 7, 27)

#: 인접 구간까지 함께 본다. 0.02 만 잘라 세면 그 값이 변곡점인지 알 수 없다.
BUCKET_EDGES: tuple[tuple[str, Decimal | None], ...] = (
    ("=0", Decimal("0")),
    ("(0, 0.005]", Decimal("0.005")),
    ("(0.005, 0.01]", Decimal("0.01")),
    ("(0.01, 0.02]", Decimal("0.02")),
    ("(0.02, 0.03]", Decimal("0.03")),
    ("(0.03, 0.05]", Decimal("0.05")),
    ("(0.05, 0.10]", Decimal("0.10")),
    ("> 0.10", None),
)

THRESHOLDS: tuple[Decimal, ...] = (
    Decimal("0.01"), Decimal("0.02"), Decimal("0.03"), Decimal("0.05"),
)


def _birth(y: int, m: int, d: int, hhmm: str, gender: str) -> BirthInput:
    return BirthInput(
        birth_date=date(y, m, d), birth_time=hhmm, birth_place_name="서울",
        gender=gender, reference_date=REFERENCE_DATE,
    )


def _capture(birth: BirthInput) -> tuple[Any, dict[str, Any]]:
    """production 을 돌리고 실현 경계 입력을 포획한다. 선택 결과는 건드리지 않는다."""
    captured: dict[str, Any] = {}

    def _spy(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return resolve_realized_roles(**kwargs)

    original = cand_mod.resolve_realized_roles
    cand_mod.resolve_realized_roles = _spy
    try:
        manse_service._cache.clear()
        analysis = calculate(birth).yongsin_analysis
        manse_service._cache.clear()
    finally:
        cand_mod.resolve_realized_roles = original
    return analysis, captured


def _bucket(margin: Decimal) -> str:
    for label, edge in BUCKET_EDGES:
        if edge is None:
            return label
        if label == "=0":
            if margin == 0:
                return label
            continue
        if margin <= edge:
            return label
    return BUCKET_EDGES[-1][0]


def _row(birth: BirthInput, gender: str) -> dict[str, Any]:
    """명식 1건의 margin 관측. 강제 재생 없이 production 산출만 읽는다."""
    analysis, captured = _capture(birth)
    candidates = list(analysis.useful_candidates)
    raw_scores = captured["useful_scores"]

    top1 = candidates[0] if candidates else None
    top2 = candidates[1] if len(candidates) > 1 else None
    row: dict[str, Any] = {
        "birth": birth.birth_date.isoformat(),
        "birth_time": str(birth.birth_time),
        "gender": gender,
        "candidate_count": len(candidates),
        "yongsin": analysis.final.get("yongsin"),
        "selected_model": analysis.final.get("selected_model"),
        "status": analysis.status,
    }
    if top1 is None or top2 is None:
        row["margin_available"] = False
        return row

    raw1 = Decimal(repr(raw_scores[top1.element][0]))
    raw2 = Decimal(repr(raw_scores[top2.element][0]))
    shown1, shown2 = Decimal(repr(top1.score)), Decimal(repr(top2.score))
    raw_margin = raw1 - raw2

    # primary 쪽 실현 사실은 production 산출이라 재생이 필요 없다. runner-up 은 MC-B.
    realization = resolve_realized_roles(**captured).result
    row.update({
        "margin_available": True,
        "top1_element": top1.element, "top2_element": top2.element,
        "top1_model": top1.model, "top2_model": top2.model,
        "top1_role": top1.reason, "top2_role": top2.reason,
        "top1_raw": str(raw1), "top2_raw": str(raw2),
        "top1_shown": str(shown1), "top2_shown": str(shown2),
        "raw_margin": str(raw_margin),
        "shown_margin": str(shown1 - shown2),
        "exact_tie": raw_margin == 0,
        "display_tie": raw_margin != 0 and shown1 == shown2,
        "same_element": top1.element == top2.element,
        "same_model": top1.model == top2.model,
        "bucket": _bucket(raw_margin),
        "primary_origin": realization.realization_origin.value,
        "primary_model_complete": realization.model_complete,
        "primary_model_map_promoted": realization.model_map_promoted,
        "primary_special_role_kind": realization.special_role_kind,
        "primary_reason_codes": list(realization.reason_codes),
    })
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for y, m, d, hhmm in FIXTURE_BIRTHS:
        for gender in GENDERS:
            rows.append(_row(_birth(y, m, d, hhmm, gender), gender))

    measured = [r for r in rows if r.get("margin_available")]

    # 성별이 원국 용신 판정을 바꾸지 않으면 남녀 두 행은 **같은 표본 하나**다.
    # 그대로 세면 N 이 두 배로 부풀어 임계값 판단이 왜곡된다(2026-08-03 실측: 13/13 동일).
    decision_of = lambda r: (  # noqa: E731
        r["raw_margin"], r["yongsin"], r["selected_model"], r["primary_origin"])
    by_chart: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in measured:
        by_chart.setdefault((row["birth"], row["birth_time"]), []).append(row)
    gender_invariant = sum(
        1 for pair in by_chart.values()
        if len({decision_of(r) for r in pair}) == 1
    )
    independent = [pair[0] for pair in by_chart.values()]

    buckets: Counter[str] = Counter(r["bucket"] for r in independent)
    summary: dict[str, Any] = {
        "verdict": "MARGIN_DISTRIBUTION_MEASURED",
        "population_rows": len(rows),
        "charts": len(by_chart),
        "gender_invariant_charts": gender_invariant,
        "independent_samples": len(independent),
        "measured_rows": len(measured),
        "unavailable_rows": len(rows) - len(measured),
        "candidate_count_distribution": dict(
            Counter(r["candidate_count"] for r in rows)),
        "buckets": {label: buckets.get(label, 0) for label, _ in BUCKET_EDGES},
        "exact_ties": sum(1 for r in independent if r["exact_tie"]),
        "display_ties": sum(1 for r in independent if r["display_tie"]),
        "same_element_pairs": sum(1 for r in independent if r["same_element"]),
        "same_model_pairs": sum(1 for r in independent if r["same_model"]),
        "at_or_below": {
            str(t): sum(1 for r in independent if Decimal(r["raw_margin"]) <= t)
            for t in THRESHOLDS
        },
        "sorted_margins": sorted(
            (str(r["raw_margin"]) for r in independent), key=lambda s: Decimal(s)),
        "primary_origin_distribution": dict(
            Counter(r["primary_origin"] for r in independent)),
        "top2_model_distribution": dict(Counter(r["top2_model"] for r in independent)),
    }

    (args.out / "rows.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8")
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
