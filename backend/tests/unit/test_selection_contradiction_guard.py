"""선별 결과의 상충·클론 감사 상설화 (2026-09-10, daily 감사 기법 이식 — 권장 순서 4).

daily 에서는 동의어 그룹으로 '같은 현상의 반대 결과' 동시 노출을 막았다. 리포트·채팅에는
그런 장치가 없었고, 클러스터 축(사건×방향×지배 신호)은 반대 방향을 의도적으로 분리한다
(2026-07-14 감수 확정 — 다른 시기의 반대 흐름은 정보다). 그래서 여기서 막는 상충은
**같은 시기·같은 도메인·반대 방향** 쌍으로 한정한다. 40명식 shadow 실측(2026-09-10)에서
0건이었고, 이 테스트가 그 상태를 고정한다. 클론(같은 시기·다른 사건·신호 벡터 cos≥0.85)은
실측 채팅 총운 2.05쌍/명식·리포트 표 9.03쌍/명식 — 캡 도입은 별도 승인(선별 변경).
"""

from __future__ import annotations

import itertools
import math
from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import EventEngineV2
from saju_engines.context_reducer import (
    EVENT_DOMAIN,
    _overview_direction,
    reduce_overview_candidates,
)
from saju_engines.report_event_input import select_table_candidates
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventCandidate
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
# 결정론 소형 코퍼스(shadow 40명식 중 앞 8) — 전체 스위트 시간 보호.
_CORPUS = [
    (
        f"{1955 + (i * 7) % 50}-{1 + (i * 5) % 12:02d}-{1 + (i * 11) % 28:02d}",
        f"{(i * 3) % 24:02d}:{(i * 17) % 60:02d}",
        "male" if i % 2 else "female",
    )
    for i in range(8)
]


def _domain(c: EventCandidate) -> str:
    return EVENT_DOMAIN.get(c.event_key, "general")


def _signal_vec(c: EventCandidate) -> dict[str, float]:
    return {s.name: s.weight for s in c.signals}


def _cos(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def contradiction_pairs(sel: list[EventCandidate]) -> list[tuple[str, str, str]]:
    """같은 시기·같은 도메인·반대 방향으로 함께 선별된 쌍."""
    out = []
    for a, b in itertools.combinations(sel, 2):
        if a.period != b.period or _domain(a) != _domain(b):
            continue
        if {_overview_direction(a), _overview_direction(b)} == {"pos", "neg"}:
            out.append((a.period, str(a.event_key), str(b.event_key)))
    return out


def clone_pairs(sel: list[EventCandidate], threshold: float = 0.85) -> int:
    """같은 시기·다른 사건인데 신호 벡터가 거의 같은 쌍의 수(감사 지표 — 판정 아님)."""
    return sum(
        1 for a, b in itertools.combinations(sel, 2)
        if a.period == b.period and a.event_key != b.event_key
        and _cos(_signal_vec(a), _signal_vec(b)) >= threshold
    )


@pytest.fixture(scope="module")
def selections() -> list[tuple[str, list[EventCandidate], list[EventCandidate]]]:
    scorer = EventEngineV2(_DICTS)
    out = []
    for bd, bt, g in _CORPUS:
        chart = calculate(BirthInput(
            calendar_type="solar", birth_date=bd, birth_time=bt, birth_place_name="서울",
            gender=g, reference_date=date(2026, 6, 11),
        ))
        cands = scorer.score_legacy(chart, levels={GanjiLevel.YEAR, GanjiLevel.MONTH})
        pool = [c for c in cands if str(c.period).startswith("2026")]
        overview = reduce_overview_candidates(pool, "2026-01", "2026-12")[0]
        table = select_table_candidates(pool)
        out.append((bd, overview, table))
    return out


def test_no_same_period_opposite_direction_pairs_in_chat_overview(selections) -> None:
    for bd, overview, _table in selections:
        assert not contradiction_pairs(overview), (bd, contradiction_pairs(overview))


def test_no_same_period_opposite_direction_pairs_in_report_table(selections) -> None:
    for bd, _overview, table in selections:
        assert not contradiction_pairs(table), (bd, contradiction_pairs(table))


def test_clone_audit_metric_is_reported_not_enforced(selections) -> None:
    """클론 쌍 수는 감사 지표다 — 상한을 강제하지 않고 '측정 가능'만 고정(캡은 별도 승인)."""
    for _bd, overview, table in selections:
        assert clone_pairs(overview) >= 0 and clone_pairs(table) >= 0
        assert len(overview) <= 5 and len(table) <= 12
