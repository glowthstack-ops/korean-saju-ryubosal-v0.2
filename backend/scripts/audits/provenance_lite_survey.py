"""P2-PROV-3-lite — A(strict selected-base)의 안정성과 P2 실제 영향 범위를 검증한다.

설계: `doc/v2_2/REVIEW_CONTRIBUTION_PROVENANCE.md` §13~15

차트 수만 늘려 `day MINOR 11%`가 유지되는지만 보면 부족하다. P2는 도메인별 사건
후보를 게이트하므로 도메인·긍부정 분해를 최소 집계로라도 남긴다.

측정:
    1. 레벨별       year / month / day
    2. 도메인별     EVENT_DOMAIN 기준 MINOR 분포
    3. 긍부정별     minor-only 긍정 후보 / 부정 후보
    4. 배경 보정    대운 우호·불리별 UPPER_BACKGROUND_ADJUSTED 분포

⚠ 모든 표본은 **동일한 full-pipeline 경로**(`EventEngineV2.score`)로만 산출한다.
스택을 밖에서 재구성한 §13의 값(전체 3.6%)과 섞지 않는다 — 세운 표본이 달라
비교가 성립하지 않는다. 비교 기준은 레벨별 수치다.

실행:
    python3 scripts/audits/provenance_lite_survey.py
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(_BACKEND / "packages" / "shared_types"),
    str(_BACKEND / "packages" / "saju_engines"),
    str(_BACKEND / "apps" / "api"),
]

from saju_api.services.manse_service import calculate  # noqa: E402
from saju_engines import EventEngineV2  # noqa: E402
from saju_engines.contribution_provenance import ProvenanceRecorder  # noqa: E402
from saju_engines.layer_evidence_scope import classify_layer_evidence_scope  # noqa: E402
from saju_shared_types.birth_input import BirthInput  # noqa: E402
from saju_shared_types.event_taxonomy_v2 import EVENT_DOMAIN  # noqa: E402
from saju_shared_types.ganji_calendar import GanjiLevel  # noqa: E402

_REF = date(2026, 6, 11)

#: 12명식 — 계절·성별·시각·시주미상을 분산한다. 대운 우호/불리는 사후에 관측값으로
#: 확인한다(사전에 강제할 수 없어 표본을 넓혀 양쪽이 모두 나오게 한다).
_CHARTS: list[tuple[str, BirthInput]] = [
    ("01 1980-11-22 남 겨울", dict(birth_date=date(1980, 11, 22), birth_time="09:08", gender="male")),
    ("02 1992-03-05 여 봄", dict(birth_date=date(1992, 3, 5), birth_time="14:20", gender="female")),
    ("03 2001-08-17 남 여름", dict(birth_date=date(2001, 8, 17), birth_time="23:10", gender="male")),
    ("04 1975-05-30 여 여름", dict(birth_date=date(1975, 5, 30), birth_time="06:45", gender="female")),
    ("05 1988-09-12 남 가을", dict(birth_date=date(1988, 9, 12), birth_time="18:30", gender="male")),
    ("06 1996-01-24 여 겨울", dict(birth_date=date(1996, 1, 24), birth_time="03:15", gender="female")),
    ("07 1983-07-08 남 여름", dict(birth_date=date(1983, 7, 8), birth_time="11:50", gender="male")),
    ("08 1970-10-03 여 가을", dict(birth_date=date(1970, 10, 3), birth_time="20:05", gender="female")),
    ("09 2005-04-19 남 봄", dict(birth_date=date(2005, 4, 19), birth_time="15:40", gender="male")),
    ("10 1965-12-27 여 겨울", dict(birth_date=date(1965, 12, 27), birth_time="08:25", gender="female")),
    # 시주 미상 2건 — 시지 신호가 빠질 때 분포가 흔들리는지 본다.
    ("11 1979-06-14 남 시미상", dict(birth_date=date(1979, 6, 14), birth_time_unknown=True, gender="male")),
    ("12 1999-02-08 여 시미상", dict(birth_date=date(1999, 2, 8), birth_time_unknown=True, gender="female")),
]


def _birth(over: dict) -> BirthInput:
    base = dict(
        calendar_type="solar", birth_place_name="서울", reference_date=_REF,
    )
    base.update(over)
    return BirthInput(**base)


def _level_of(label: str) -> str:
    return "year" if len(label) == 4 else ("month" if len(label) == 7 else "day")


def survey(name: str, birth: BirthInput) -> dict[str, Counter]:
    """한 차트를 엔진 전 구간으로 돌려 레벨·도메인·극성·배경 보정을 집계한다."""
    chart = calculate(birth)
    eng = EventEngineV2(_BACKEND / "dictionaries")
    rec = ProvenanceRecorder()
    cands = eng.score(
        chart,
        levels={GanjiLevel.YEAR, GanjiLevel.MONTH, GanjiLevel.DAY},
        provenance_recorder=rec,
    )
    # 후보 극성 조회용 — (period, event_key) → favorability.
    fav_of = {(c.period, str(c.event_key)): c.favorability for c in cands}

    lv = Counter()
    dom = Counter()
    pol = Counter()
    minor_keys: set[tuple[str, str]] = set()
    unknown = 0
    no_base = 0
    total = 0

    for label, period in rec.periods().items():
        level = _level_of(label)
        for event_key, status in period.selection_status.items():
            total += 1
            if status.value == "NO_SELECTED_BASE":
                no_base += 1
            sel = period.selected.get(event_key)
            layers = sel.source_layers if sel is not None else ()
            verdict = classify_layer_evidence_scope(layers).value
            lv[f"{level}:{verdict}"] += 1
            if verdict == "UNKNOWN":
                unknown += 1
            if verdict != "MINOR_ONLY":
                continue
            minor_keys.add((label, event_key))
            domain = str(EVENT_DOMAIN.get(event_key, "?"))
            dom[domain] += 1
            if level == "day":
                dom[f"{domain}@day"] += 1
            fav = fav_of.get((label, event_key), 0.0)
            pol["positive" if fav > 0.2 else ("negative" if fav < -0.2 else "neutral")] += 1

    # 배경 보정 — 대운 역할은 favorability_effect로 역산한다.
    # (길 사건 상승 = IMPROVES = 용·희 / 그 외 = WORSENS = 기·구)
    bg = Counter()
    seen: set[tuple[str, str]] = set()
    for label, period in rec.periods().items():
        for m in period.modifiers:
            key = (label, m.event_key)
            if key in seen:
                continue
            seen.add(key)
            scope = "minor" if key in minor_keys else "upper"
            bg[f"{scope}:adjusted"] += 1
            bg[f"{scope}:fav:{m.favorability_effect.value}"] += 1
            bg[f"{scope}:align:{m.candidate_alignment.value}"] += 1
    bg["minor_total"] = len(minor_keys)
    bg["candidate_total"] = total

    return {"level": lv, "domain": dom, "polarity": pol, "background": bg,
            "meta": Counter({"total": total, "unknown": unknown, "no_base": no_base,
                             "minor": len(minor_keys)})}


def main() -> None:
    """12명식 집계와 종료 조건 검사 결과를 출력한다."""
    tot = {k: Counter() for k in ("level", "domain", "polarity", "background", "meta")}
    print(f"{'차트':<24} {'후보':>6} {'MINOR':>6} {'day MINOR%':>11}")
    print("-" * 52)
    day_ratios: list[float] = []
    for name, over in _CHARTS:
        r = survey(name, _birth(over))
        for k in tot:
            tot[k] += r[k]
        dmin = r["level"]["day:MINOR_ONLY"]
        dtot = dmin + r["level"]["day:UPPER_SUPPORTED"] + r["level"]["day:UNKNOWN"]
        ratio = dmin / dtot if dtot else 0.0
        day_ratios.append(ratio)
        print(f"{name:<24} {r['meta']['total']:>6} {r['meta']['minor']:>6} {ratio:>10.1%}")

    print("-" * 52)
    m = tot["meta"]
    print(f"{'합계':<24} {m['total']:>6} {m['minor']:>6}")
    print(f"\nUNKNOWN={m['unknown']}  NO_SELECTED_BASE={m['no_base']}")
    if day_ratios:
        print(f"day MINOR 비율 범위: {min(day_ratios):.1%} ~ {max(day_ratios):.1%}"
              f" (평균 {sum(day_ratios) / len(day_ratios):.1%})")

    print("\n[레벨별]")
    for k in sorted(tot["level"]):
        print(f"  {k:<28} {tot['level'][k]:>6}")
    print("\n[도메인별 MINOR]")
    for k in sorted(tot["domain"], key=lambda x: -tot["domain"][x]):
        print(f"  {k:<28} {tot['domain'][k]:>6}")
    print("\n[MINOR 후보 극성]")
    for k in sorted(tot["polarity"]):
        print(f"  {k:<28} {tot['polarity'][k]:>6}")
    print("\n[대운 배경 보정]")
    for k in sorted(tot["background"]):
        print(f"  {k:<28} {tot['background'][k]:>6}")

    # 종료 조건 — 데이터 안정성.
    lvl_sum = sum(v for k, v in tot["level"].items())
    assert lvl_sum == m["total"], (lvl_sum, m["total"])
    print(f"\n불변식 upper+minor+unknown == unique candidates: {lvl_sum} == {m['total']} ✓")


if __name__ == "__main__":
    main()
