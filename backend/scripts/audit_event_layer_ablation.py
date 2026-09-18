"""이벤트 채점 층별 ablation 감사 (EVENT_SCORING_3LAYER_PROPOSAL §3 — 상설, 2026-09-10 승인 P0).

현행 6계층 가산 채점(`EventEngineV2.score`)의 contributions 로 raw 를 재구성해, 층 하나를
0 으로 두면 (a) 기간별 top 사건 (b) 연간 raw Top-5 집합이 얼마나 바뀌는지와, 12운성 보정값의
상한(±cap) 포화율을 산출한다. 감사는 판정하지 않는다 — 판정은 사람이 한다(회귀는 "측정 가능"만
고정). daily §22-7 재측정 방식의 이식.

사용법:
    python scripts/audit_event_layer_ablation.py [N_CHARTS] [YEAR]
기본: 40명식(결정론 합성 코퍼스) × 2026년(연운+월운).
"""

from __future__ import annotations

import collections
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines import EventEngineV2
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import EventCandidateV2
from saju_shared_types.ganji_calendar import GanjiLevel

_BACKEND = Path(__file__).resolve().parent.parent
_DICTS = _BACKEND / "dictionaries"
#: contributions 중 곱셈 인수(가산 항이 아님) — raw 재구성에서 제외.
NON_ADDITIVE = frozenset({"src_strength"})
#: ablation 대상 층(가산 항).
LAYERS: tuple[str, ...] = (
    "base", "stage", "stage_combo", "flow", "relation", "yongi", "gate", "daewoon_hwa",
    "daewoon_transition", "rank",
)
#: 12운성 보정 상한(twelve_stage_modifier._STAGE_DELTA_CAP 과 동일 — 포화율 산출용).
STAGE_DELTA_CAP = 18.0


def synthetic_corpus(n: int) -> list[tuple[str, str, str]]:
    """결정론 합성 명식 코퍼스 (생년월일, 시각, 성별) — 실사용자 데이터 미사용."""
    return [
        (
            f"{1955 + (i * 7) % 50}-{1 + (i * 5) % 12:02d}-{1 + (i * 11) % 28:02d}",
            f"{(i * 3) % 24:02d}:{(i * 17) % 60:02d}",
            "male" if i % 2 else "female",
        )
        for i in range(n)
    ]


def raw_score(c: EventCandidateV2, without: str | None = None) -> float:
    """contributions 로 재구성한 raw(가산 항 합) — `without` 층은 0 으로 둔다."""
    return sum(
        v for k, v in c.contributions.items() if k not in NON_ADDITIVE and k != without
    )


@dataclass
class AblationReport:
    """감사 산출물 — 전부 비율(0..1) 또는 건수."""

    charts: int = 0
    candidates: int = 0
    periods: int = 0
    share: dict[str, float] = field(default_factory=dict)  # 층별 |기여| 평균 비율
    period_top_changed: dict[str, float] = field(default_factory=dict)  # 층 제거 시
    year_top5_changed: dict[str, float] = field(default_factory=dict)
    stage_cap_share: float = 0.0  # stage 기여가 +cap 인 후보 비율
    stage_mean_by_stage: dict[str, float] = field(default_factory=dict)


def run_ablation(
    n_charts: int = 40, year: int = 2026, dictionaries_dir: Path = _DICTS
) -> AblationReport:
    """코퍼스 전체를 채점해 ablation 표를 만든다(순수 계산 — 출력 없음)."""
    scorer = EventEngineV2(dictionaries_dir)
    rep = AblationReport()
    share_acc: dict[str, float] = collections.defaultdict(float)
    top_changed: collections.Counter[str] = collections.Counter()
    top5_changed: collections.Counter[str] = collections.Counter()
    stage_vals: dict[str, list[float]] = collections.defaultdict(list)
    at_cap = 0
    prefix = f"{year}-"
    for bd, bt, g in synthetic_corpus(n_charts):
        chart = calculate(BirthInput(
            calendar_type="solar", birth_date=bd, birth_time=bt, birth_place_name="서울",
            gender=g, reference_date=date(year, 6, 11),
        ))
        cands = [
            c for c in scorer.score(chart, levels={GanjiLevel.YEAR, GanjiLevel.MONTH})
            if str(c.period).startswith(prefix)
        ]
        rep.charts += 1
        by_period: dict[str, list[EventCandidateV2]] = collections.defaultdict(list)
        for c in cands:
            rep.candidates += 1
            by_period[str(c.period)].append(c)
            total = sum(abs(v) for k, v in c.contributions.items() if k not in NON_ADDITIVE)
            for k, v in c.contributions.items():
                if k not in NON_ADDITIVE and total:
                    share_acc[k] += abs(v) / total
            sv = float(c.contributions.get("stage", 0.0))
            stage_vals[str(c.twelve_stage)].append(sv)
            if sv >= STAGE_DELTA_CAP:
                at_cap += 1
        rep.periods += len(by_period)
        base_top5 = {
            f"{c.event_key}|{c.period}"
            for c in sorted(cands, key=raw_score, reverse=True)[:5]
        }
        for layer in LAYERS:
            for cs in by_period.values():
                a = max(cs, key=raw_score).event_key
                b = max(cs, key=lambda c: raw_score(c, layer)).event_key
                if a != b:
                    top_changed[layer] += 1
            alt = {
                f"{c.event_key}|{c.period}"
                for c in sorted(cands, key=lambda c: raw_score(c, layer), reverse=True)[:5]
            }
            if alt != base_top5:
                top5_changed[layer] += 1
    if rep.candidates:
        rep.share = {k: v / rep.candidates for k, v in share_acc.items()}
        rep.stage_cap_share = at_cap / rep.candidates
    if rep.periods:
        rep.period_top_changed = {k: top_changed[k] / rep.periods for k in LAYERS}
    if rep.charts:
        rep.year_top5_changed = {k: top5_changed[k] / rep.charts for k in LAYERS}
    rep.stage_mean_by_stage = {
        st: sum(vs) / len(vs) for st, vs in stage_vals.items() if vs
    }
    return rep


def main(argv: list[str]) -> int:
    """표를 출력한다. 항상 0(감사는 판정하지 않는다)."""
    n = int(argv[1]) if len(argv) > 1 else 40
    year = int(argv[2]) if len(argv) > 2 else 2026
    rep = run_ablation(n, year)
    print(f"charts {rep.charts} | candidates {rep.candidates} | periods {rep.periods}")
    print("층별 |기여| 평균 비율:")
    for k, v in sorted(rep.share.items(), key=lambda kv: -kv[1]):
        print(f"  {k:20s} {v:6.1%}")
    print("층 제거 시 변경률 (기간별 top 사건 / 연간 raw Top-5 집합):")
    for layer in LAYERS:
        print(
            f"  {layer:20s} {rep.period_top_changed.get(layer, 0.0):6.1%} / "
            f"{rep.year_top5_changed.get(layer, 0.0):6.1%}"
        )
    print(f"12운성 보정 +{STAGE_DELTA_CAP:.0f} 포화율: {rep.stage_cap_share:.1%}")
    for st, m in sorted(rep.stage_mean_by_stage.items(), key=lambda kv: -kv[1]):
        print(f"  {st:10s} mean {m:6.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
