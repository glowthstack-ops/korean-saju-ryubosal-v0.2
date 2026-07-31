#!/usr/bin/env python3
"""AMHAP-SAT — 암합 탐지 포화의 원인 감사 (측정 전용, production 불변).

선행 감사(`audit_amhap_channel_coverage.py`)에서 탐지가 82/82 기간·평균 4.4건으로
변별력이 없었다. 이번에 가릴 것:

    실제로 대부분 기간에 암합이 성립하는 구조
    vs
    탐지 조건이 넓어 거의 모든 기간을 양성 처리하는 구조

`detect_luck_amhap` 은 기간당 최대 48쌍을 검사한다.

    명암합      운 천간 1 × 원국 지장간 3 × 4궁          = 12쌍
    지장간암합  운 지지 지장간 3 × 원국 지장간 3 × 4궁   = 36쌍

천간합은 10간 중 **5쌍**뿐이라 임의 쌍의 성립 확률이 약 11%다. 48 × 11% ≈ 5건 —
탐지량이 명식의 특성인지 검사 쌍 수의 산술적 귀결인지가 질문이다.

포화 원인을 둘로 분해한다.

    COMBINATORIAL_SATURATION      지장간 전조합 수가 많아 양성이 발생
    PAIR_RECURRENCE_SATURATION    소수 천간합 조합이 대부분 기간에 반복

두 가설은 관측이 정반대다. 반복이면 top-N 조합 점유율이 높고 동일 조합이 연속으로
이어진다. 조합 폭발이면 고유 조합이 많고 매 기간 다른 쌍이 잡힌다.

**월운 12기간만 보면 표본이 얇아** 운 간지 60갑자를 전수 대입한다. 실제 달력이 주는
기간 집합과 무관하게 "어떤 운이 와도 잡히는가" 를 직접 묻는 방식이다.

이번 감사는 원인 측정까지만 한다. 탐지 조건·궁위 가중치·채팅 cap·리포트 배선·후보/
점수/그래프 배선은 바꾸지 않는다. 축소안(직접성·본기성·궁위성)은 다음 설계 사이클에서
독립 shadow 로 비교한다.
"""

from __future__ import annotations

import collections
import hashlib
import json
import statistics
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

from saju_api.services import manse_service as M  # noqa: E402
from saju_api.services import report_service as R  # noqa: E402
from saju_engines.amhap_luck import detect_luck_amhap  # noqa: E402
from saju_shared_types.constants import (  # noqa: E402
    STEM_COMBINATIONS,
    hidden_stems_for,
)
from saju_shared_types.enums import Branch  # noqa: E402

#: 층화 표본 8명식(144명식 스캔에서 선별) — 지장간 수 10~12로 분포시키고, 선행 감사
#: fixture 와 대운 감사 fixture 4종을 포함해 이전 측정과 이어 읽을 수 있게 했다.
CHARTS: tuple[tuple[str, int, int, int, str, str], ...] = (
    ("기존 포화 fixture", 1979, 12, 27, "21:40", "female"),
    ("보강 대운 fixture", 1986, 9, 13, "15:20", "male"),
    ("합화 불성립 fixture", 2001, 8, 29, "06:05", "female"),
    ("혼재 fixture", 1981, 6, 22, "10:10", "female"),
    ("지장간 10", 1972, 3, 9, "04:30", "male"),
    ("지장간 12", 1990, 8, 8, "10:10", "male"),
    ("지장간 12(b)", 1975, 2, 3, "14:20", "male"),
    ("지장간 11", 1994, 12, 1, "03:15", "female"),
)

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
#: 60갑자 — 실제 달력이 주는 기간과 무관하게 가능한 운 간지 전체.
SEXAGENARY: tuple[tuple[str, str], ...] = tuple(
    (STEMS[i % 10], BRANCHES[i % 12]) for i in range(60)
)


def _chart(y: int, m: int, d: int, t: str, g: str) -> Any:
    return M.calculate(R.BirthInput(
        calendar_type="solar", birth_date=date(y, m, d), birth_time=t,
        birth_place_name="서울", gender=g, reference_date=date(2026, 7, 30),
    ))


def _hidden_count(pillars: Any) -> int:
    """원국 4지지의 지장간 총수 — 조합 폭발 가설의 설명 변수."""
    total = 0
    for name in ("year", "month", "day", "hour"):
        pillar = getattr(pillars, name)
        if pillar is None:
            continue
        try:
            total += len(hidden_stems_for(Branch(pillar.branch)))
        except ValueError:
            continue
    return total


def audit_chart(label: str, y: int, m: int, d: int, t: str, g: str) -> dict[str, Any]:
    """한 명식에 60갑자를 전수 대입해 탐지 분포를 측정한다."""
    pillars = _chart(y, m, d, t, g).pillars
    counts: list[int] = []
    pairs: collections.Counter = collections.Counter()
    kinds: collections.Counter = collections.Counter()
    palaces: collections.Counter = collections.Counter()
    gods: collections.Counter = collections.Counter()
    signatures: list[str] = []
    for stem, branch in SEXAGENARY:
        hits = detect_luck_amhap(stem, branch, pillars)
        counts.append(len(hits))
        for h in hits:
            pairs[(h.kind, h.luck_char, h.natal_hidden)] += 1
            kinds[h.kind] += 1
            palaces[h.palace] += 1
            gods[h.ten_god] += 1
        signatures.append(",".join(sorted(f"{h.luck_char}{h.natal_hidden}" for h in hits)))

    # 동일 조합 연속 반복 길이 — PAIR_RECURRENCE 가설의 직접 지표.
    run = best = 1
    for i in range(1, len(signatures)):
        if signatures[i] and signatures[i] == signatures[i - 1]:
            run += 1
            best = max(best, run)
        else:
            run = 1

    total = sum(pairs.values())
    top3 = sum(v for _k, v in pairs.most_common(3))
    return {
        "label": label,
        "birth": f"{y}-{m:02}-{d:02} {t} {g[0]}",
        "hidden_stems": _hidden_count(pillars),
        "ganzhi_tested": len(SEXAGENARY),
        "detected_ganzhi": sum(1 for c in counts if c),
        "zero_ganzhi": sum(1 for c in counts if c == 0),
        "detection_rate": sum(1 for c in counts if c) / len(counts),
        "mean": round(statistics.mean(counts), 2),
        "median": statistics.median(counts),
        "max": max(counts),
        "myeong": kinds["myeong"],
        "jijang": kinds["jijang"],
        "unique_pairs": len(pairs),
        "top3_share": round(top3 / total, 3) if total else 0.0,
        "max_consecutive_run": best,
        "palaces": dict(palaces),
        "top_ten_gods": dict(gods.most_common(3)),
        "total_hits": total,
    }


def run() -> dict[str, Any]:
    """8명식 × 60갑자 전수 측정 + 원인 분해."""
    rows = [audit_chart(*c) for c in CHARTS]
    rates = [r["detection_rate"] for r in rows]
    hidden = [r["hidden_stems"] for r in rows]
    means = [r["mean"] for r in rows]
    myeong = sum(r["myeong"] for r in rows)
    jijang = sum(r["jijang"] for r in rows)
    top3 = statistics.mean(r["top3_share"] for r in rows)
    runs = max(r["max_consecutive_run"] for r in rows)
    corr = statistics.correlation(hidden, means) if len(set(hidden)) > 1 else None

    # 원인 분해 — 두 가설은 관측이 정반대라 한쪽만 성립한다.
    recurrence = top3 >= 0.5 or runs >= 3
    verdicts = [
        "AMHAP_SATURATION_GENERALIZED_ON_AUDITED_SAMPLE"
        if min(rates) >= 0.9 else "AMHAP_SATURATION_FIXTURE_SPECIFIC",
        "PAIR_RECURRENCE_SATURATION_CONFIRMED" if recurrence
        else "PAIR_RECURRENCE_SATURATION_REJECTED",
        "AMHAP_SATURATION_DRIVEN_BY_HIDDEN_STEM_COMBINATORICS"
        if not recurrence and (corr is None or corr > 0.5) else
        "AMHAP_SATURATION_CAUSE_INCONCLUSIVE",
        "AMHAP_DISCRIMINATIVE_VALUE_NOT_CONFIRMED"
        if min(rates) >= 0.9 else "AMHAP_DISCRIMINATIVE_VALUE_CONFIRMED",
        "PRODUCTION_UNCHANGED",
    ]

    print("AMHAP_SATURATION_AUDIT_STARTED")
    print(f"명식 {len(CHARTS)} × 60갑자 전수 = {len(CHARTS) * 60} 조합\n")
    print(f"{'명식':<22}{'지장간':>6}{'탐지율':>8}{'0건':>5}{'평균':>7}"
          f"{'최대':>5}{'고유쌍':>7}{'top3':>7}{'연속':>5}{'명암':>6}{'지장':>6}")
    for r in rows:
        print(f"{r['label']:<22}{r['hidden_stems']:>6}{r['detection_rate']:>8.0%}"
              f"{r['zero_ganzhi']:>5}{r['mean']:>7.1f}{r['max']:>5}"
              f"{r['unique_pairs']:>7}{r['top3_share']:>7.0%}"
              f"{r['max_consecutive_run']:>5}{r['myeong']:>6}{r['jijang']:>6}")

    print(f"\n탐지율        min {min(rates):.0%}  max {max(rates):.0%}  "
          f"평균 {statistics.mean(rates):.0%}")
    print(f"지장간 수 ↔ 기간당 평균 탐지  상관 {corr:+.2f}" if corr is not None else "")
    print(f"명암합:지장간암합  {myeong}:{jijang}  "
          f"(검사 쌍 12:36 = 1:3)")
    print(f"top3 조합 점유율 평균  {top3:.0%}   동일 조합 최대 연속  {runs}")
    print(f"천간합 쌍 수 {len(STEM_COMBINATIONS)} / 10간 — 임의 쌍 성립 확률 약 11%")

    out = {
        "charts": rows,
        "summary": {
            "detection_rate_min": min(rates), "detection_rate_max": max(rates),
            "detection_rate_mean": statistics.mean(rates),
            "hidden_stem_correlation": corr,
            "myeong_total": myeong, "jijang_total": jijang,
            "top3_share_mean": top3, "max_consecutive_run": runs,
            "stem_combination_pairs": len(STEM_COMBINATIONS),
        },
        "verdicts": verdicts,
        "not_changed": [
            "탐지 조건", "궁위 가중치", "채팅 cap 2", "리포트 배선",
            "후보·점수·그래프 배선",
        ],
        "scope_limit": (
            "60갑자는 전수지만 명식은 8종이다. 모든 명식에 대한 수학적 증명이 아니라 "
            "층화 표본에서의 일반화다."
        ),
    }
    # 재현 지문 — 설계 변경 전후를 같은 모집단으로 재측정할 때 기준선이 된다.
    body = json.dumps(out["charts"], ensure_ascii=False, sort_keys=True)
    out["fingerprint"] = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    print(f"\n재현 지문  {out['fingerprint']}")
    for v in verdicts:
        print(v)
    return out


if __name__ == "__main__":
    result = run()
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
