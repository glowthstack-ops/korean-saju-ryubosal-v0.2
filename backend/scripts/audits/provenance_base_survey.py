"""P2-PROV-1 감사 — selected base만으로 후보 provenance가 충분한지 실측한다.

설계: `doc/v2_2/REVIEW_CONTRIBUTION_PROVENANCE.md` §10 종료 판정 A~D

이 스크립트는 **판정하지 않는다.** 종료 판정에 필요한 분포만 낸다.

    A  selected base만으로 충분        → strict generator 정의로 감수 진행
    B  modifier 없이는 상위 근거 누락  → 동일 formula·aligned modifier 검토
    C  modifier가 거의 모두 UPPER화    → modifier는 confidence/quality 근거로만
    D  occurrence 복원 불가            → P2 보류, brancher 데이터 모델 재설계

엔진 계산에는 개입하지 않는다 — 스택을 밖에서 재구성해 브랜처만 recorder와 함께
다시 돌린다(기존 감사 스크립트와 같은 방식).

실행:
    python3 scripts/audits/provenance_base_survey.py
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
from saju_engines.contribution_provenance import (  # noqa: E402
    ProvenanceRecorder,
)
from saju_engines.event_engine_v2 import _StackIndex  # noqa: E402
from saju_engines.layer_evidence_scope import classify_layer_evidence_scope  # noqa: E402
from saju_shared_types.birth_input import BirthInput  # noqa: E402
from saju_shared_types.ganji_calendar import GanjiLevel  # noqa: E402

#: 감사 대상 차트 — 이번 사이클의 기준 사례.
_CHARTS: list[tuple[str, BirthInput]] = [
    ("A 1980-11-22 남", BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11))),
    ("B 1992-03-05 여", BirthInput(
        calendar_type="solar", birth_date=date(1992, 3, 5), birth_time="14:20",
        birth_place_name="부산", gender="female", reference_date=date(2026, 6, 11))),
    ("C 2001-08-17 남", BirthInput(
        calendar_type="solar", birth_date=date(2001, 8, 17), birth_time="23:10",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11))),
]


def _periods(chart, idx: _StackIndex) -> list[tuple[GanjiLevel, str, object]]:
    """세운·월운·일운 시점 목록.

    일운을 반드시 포함한다 — P2의 주 관심사(날짜 선택·일반 길일)가 일운 레벨이라
    빼면 MINOR_ONLY가 과소 집계된다.
    """
    out: list[tuple[GanjiLevel, str, object]] = []
    for year, pillar in sorted(idx.sewoon_by_year.items()):
        out.append((GanjiLevel.YEAR, str(year), pillar))
    for ym, pillar in sorted(idx.wolwoon_by_ym.items()):
        out.append((GanjiLevel.MONTH, ym, pillar))
    for pillar in chart.luck_cycles.daily_luck or []:
        out.append((GanjiLevel.DAY, pillar.label, pillar))
    return out


def survey_chart(name: str, birth: BirthInput) -> dict[str, Counter]:
    """한 차트의 selected base 층위 분포를 낸다."""
    chart = calculate(birth)
    eng = EventEngineV2(_BACKEND / "dictionaries")
    idx = _StackIndex(chart)
    rec = ProvenanceRecorder()

    for level, label, target in _periods(chart, idx):
        stack = idx.stack_for(level, label, target)
        if not stack:
            continue
        target_layer = {
            GanjiLevel.YEAR: "sewoon", GanjiLevel.MONTH: "wolwoon",
            GanjiLevel.DAY: "ilwoon",
        }[level]
        signals = [
            s
            for layer, pillar in stack
            for s in eng._brancher.collect_from_pillar(
                pillar, layer, is_target=str(layer) == target_layer
            )
        ]
        if signals:
            eng._brancher.branch(signals, label, provenance_recorder=rec)

    level_of = {label: level for level, label, _ in _periods(chart, idx)}
    scope = Counter()
    status = Counter()
    by_level: Counter = Counter()
    for label, period in rec.periods().items():
        lv = str(level_of.get(label, "?"))
        for event_key, st in period.selection_status.items():
            status[st.value] += 1
            sel = period.selected.get(event_key)
            layers = sel.source_layers if sel is not None else ()
            verdict = classify_layer_evidence_scope(layers).value
            scope[verdict] += 1
            by_level[f"{lv}:{verdict}"] += 1
    return {"scope": scope, "status": status, "by_level": by_level,
            "counts": Counter(rec.counts())}


def main() -> None:
    """차트별 분포와 불변식 검사 결과를 출력한다."""
    total_scope: Counter = Counter()
    total_counts: Counter = Counter()
    total_by_level: Counter = Counter()
    print(f"{'차트':<18} {'후보':>6} {'근거':>7} {'승자':>6} "
          f"{'UPPER':>7} {'MINOR':>7} {'UNKNOWN':>8}")
    print("-" * 66)
    for name, birth in _CHARTS:
        r = survey_chart(name, birth)
        s, c = r["scope"], r["counts"]
        total_scope += s
        total_counts += c
        total_by_level.update(r["by_level"])
        print(f"{name:<18} {c['unique_candidate_count']:>6} "
              f"{c['evaluated_evidence_count']:>7} {c['selected_base_evidence_count']:>6} "
              f"{s['UPPER_SUPPORTED']:>7} {s['MINOR_ONLY']:>7} {s['UNKNOWN']:>8}")
        # 불변식 — 세 분류의 합은 후보 수와 같아야 한다.
        assert sum(s.values()) == c["unique_candidate_count"], (name, s, c)
        assert c["selected_base_evidence_count"] <= c["unique_candidate_count"], name

    print("-" * 66)
    n = total_counts["unique_candidate_count"]
    print(f"{'합계':<18} {n:>6} {total_counts['evaluated_evidence_count']:>7} "
          f"{total_counts['selected_base_evidence_count']:>6} "
          f"{total_scope['UPPER_SUPPORTED']:>7} {total_scope['MINOR_ONLY']:>7} "
          f"{total_scope['UNKNOWN']:>8}")
    if n:
        minor = total_scope["MINOR_ONLY"]
        print(f"\nMINOR_ONLY 비율 (strict_generator 기준): {minor}/{n} = {minor / n:.1%}")
        print(f"NO_SELECTED_BASE: {total_counts.get('NO_SELECTED_BASE', 0)}")
        print("\n레벨별 분해")
        for key in sorted(total_by_level):
            print(f"  {key:<28} {total_by_level[key]:>6}")


if __name__ == "__main__":
    main()
