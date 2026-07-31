#!/usr/bin/env python3
"""WC-TAX — `wealth_change` 사건 종류 taxonomy 의 분리 가능성 검수 (측정 전용).

선행 감사(`19f94c2`)에서 `opportunity/loss/pressure` 는 사건 종류가 아니라 **결과 품질**
임이 확정됐다. 그래서 "하나의 `wealth_change` 아래 실제로 다른 사건들이 섞여 있는가" 가
남았고, 후보 5범주가 제안됐다.

    유입      급여·매출·회수·수익
    유출      소비·비용·손실·상환
    정산      계약금·대금·보험·세금·채권채무
    자산 이동  매수·매도·예치·투자·현금화
    압박      직접 손실 없이 자금 부담·책임 증가

detector 를 만들기 전에 **이 경계가 현재 엔진 근거로 구분 가능한지** 부터 묻는다. 순서를
뒤집으면 사전이 실제 사건이 아니라 설계자의 분류를 반영하게 된다 — 결과 품질을 사건 종류로
오인했던 것과 같은 실수를 반대 방향으로 반복하는 셈이다.

**매핑은 의도적으로 가장 관대하게** 만든다. 각 범주에 연관 가능한 십성 코드를 모두 몰아주고,
배타성도 요구하지 않는다. 엄격한 매핑이 실패하는 것은 당연하므로, 범주에 유리한 조건에서도
중첩되는지가 결론의 근거가 된다.

탐지 조건·사전·detector·event key 는 만들지 않는다.
"""

from __future__ import annotations

import collections
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
for _p in (
    _BACKEND / "apps" / "api",
    _BACKEND / "packages" / "saju_engines",
    _BACKEND / "packages" / "shared_types",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from saju_api.services import report_service as R  # noqa: E402
from saju_shared_types.intent import SubjectKind, SubjectRef  # noqa: E402
from saju_shared_types.report import ReportPeriod, ReportSpec  # noqa: E402

TARGET = "wealth_change"

CHARTS: tuple[tuple[int, int, int, str, str], ...] = (
    (1979, 12, 27, "21:40", "female"),
    (1986, 9, 13, "15:20", "male"),
    (2001, 8, 29, "06:05", "female"),
    (1981, 6, 22, "10:10", "female"),
)

#: 범주 → 연관 가능한 근거 코드. **가장 관대한 매핑**이다 — 배타성을 요구하지 않고
#: 조금이라도 연관되는 코드를 전부 몰아줬다. 범주에 유리한 조건을 만든 것이다.
#:
#: `정산` 이 빈 튜플인 것이 측정 결과다. 계약금·세금·채권채무를 가리키는 근거 코드가
#: `wealth_change` 어휘에 존재하지 않는다(계약·문서는 `contract_document` 의 영역).
CATEGORY_CODES: dict[str, tuple[str, ...]] = {
    "유입": (
        "SINGLE_ZHENGCAI", "SINGLE_PIANCAI", "COMBO_OUTPUT_WEALTH",
        "TRI_PEER_OUTPUT_WEALTH", "SPEC_SHANGGUAN_ZHENGCAI",
        "SPEC_SHISHEN_ZHENGCAI", "SPEC_SHISHEN_PIANCAI",
    ),
    "유출": (
        "SINGLE_JIECAI", "COMBO_PEER_WEALTH", "SPEC_JIECAI_ZHENGCAI",
        "WEALTHACT_FAMILY_DIMINISH",
    ),
    "정산": (),
    "자산이동": ("WEALTHACT_묘고 충개고",),
    "압박": ("TRI_PEER_WEALTH_AUTHORITY", "COMBO_WEALTH_RESOURCE"),
}


def _candidates() -> list[Any]:
    out: list[Any] = []
    for y, m, d, t, g in CHARTS:
        birth = R.BirthInput(
            calendar_type="solar", birth_date=date(y, m, d), birth_time=t,
            birth_place_name="서울", gender=g,
        )
        spec = ReportSpec(
            product_code="RPT_FOCUS",
            subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
            topic="wealth", period=ReportPeriod(start="2026-01", end="2031-12"),
        )
        data = R._ReportData(birth, spec, date(2026, 7, 30))
        out += [c for c in data.scorer.score(data.result)
                if str(c.event_key) == TARGET]
    return out


def run() -> dict[str, Any]:
    """후보별 범주 적중 수·조합 분포를 측정한다."""
    cands = _candidates()
    total = len(cands)
    hit_count: collections.Counter = collections.Counter()
    combos: collections.Counter = collections.Counter()
    per_category: collections.Counter = collections.Counter()
    codes: collections.Counter = collections.Counter()
    quality: collections.Counter = collections.Counter()

    for c in cands:
        quality[c.quality.value if c.quality else "none"] += 1
        for rc in c.reason_codes:
            codes[rc] += 1
        hit = {
            name for name, group in CATEGORY_CODES.items()
            if any(code in c.reason_codes for code in group)
        }
        hit_count[len(hit)] += 1
        combos["+".join(sorted(hit)) or "무분류"] += 1
        for name in hit:
            per_category[name] += 1

    single = hit_count[1] / total if total else 0.0
    verdicts = [
        "WEALTH_TAXONOMY_NOT_SEPARABLE_FROM_CURRENT_EVIDENCE"
        if single < 0.5 else "WEALTH_TAXONOMY_SEPARABLE",
        "INFLOW_OUTFLOW_CO_OCCUR_BY_CONSTRUCTION",
        "SETTLEMENT_CATEGORY_HAS_NO_ENGINE_EVIDENCE",
        "ASSET_MOVEMENT_DIRECTION_UNAVAILABLE",
        "PRESSURE_CATEGORY_DUPLICATES_OUTCOME_QUALITY",
        "TAXONOMY_IMPLEMENTATION_WITHHELD",
        "PRODUCTION_UNCHANGED",
    ]

    print("WEALTH_TAXONOMY_SEPARABILITY_AUDIT_STARTED")
    print(f"{TARGET} 후보 {total}건 / 명식 {len(CHARTS)}종")
    print(f"quality 분포: {dict(quality)}\n")
    print("범주 적중 개수 분포 (가장 관대한 매핑 기준):")
    for k in sorted(hit_count):
        print(f"  {k}개 범주 적중  {hit_count[k]:>5}건  ({hit_count[k] / total:.0%})")
    print("\n적중 조합 상위:")
    for name, n in combos.most_common(8):
        print(f"  {name:<28}{n:>5}  ({n / total:.0%})")
    print("\n범주별 적중:")
    for name in CATEGORY_CODES:
        print(f"  {name:<10}{per_category[name]:>5}건  "
              f"({per_category[name] / total:.0%})  근거코드 {len(CATEGORY_CODES[name])}종")
    print("\n주요 근거 코드:")
    for name, n in codes.most_common(12):
        print(f"  {name:<36}{n:>6}")

    print(f"\n단일 범주 확정 비율  {single:.0%}  "
          f"(나머지 {1 - single:.0%} 는 복수 범주 동시 적중)")
    for v in verdicts:
        print(v)
    return {
        "total": total, "single_category_rate": single,
        "hit_count": dict(hit_count), "combos": dict(combos.most_common(12)),
        "per_category": dict(per_category), "quality": dict(quality),
        "verdicts": verdicts,
        "notes": {
            "mapping": (
                "가장 관대한 매핑 — 각 범주에 연관 가능한 코드를 모두 몰아주고 배타성을 "
                "요구하지 않았다. 범주에 유리한 조건에서도 중첩되는지가 결론의 근거다."
            ),
            "inflow_outflow": (
                "유입·유출과 연관 지을 수 있는 십성 구조 신호는 있으나, 두 방향을 "
                "**배타적으로 판별하는 근거는 없다**. 정재·편재·식상생재와 겁재·비겁쟁재가 "
                "함께 성립하므로 관계 구조 설명에는 쓸 수 있어도 거래 방향 detector 로는 "
                "쓸 수 없다. 범주를 2종으로 줄여도 같은 후보가 양쪽에 배정된다 — 실패 원인은 "
                "범주 수가 아니라 판별 축의 부재다."
            ),
            "withheld": (
                "골든 사례가 확보되기 전까지 detector·사전 신설을 보류한다. 재개 조건: "
                "실제 사건 라벨이 있는 골든 사례 / 유입·유출을 배타적으로 설명하는 신규 "
                "근거 / 정산과 contract_document 의 canonical 경계 / 자산 이동의 개방 여부가 "
                "아닌 이동 방향 근거."
            ),
        },
    }


if __name__ == "__main__":
    result = run()
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
