"""v2.2 Phase 2 회귀 픽스처 (T2.5) — Event Graph + Scoring 핵심 케이스 10종.

기준 차트: 1980-11-22 09:08 서울 남(일간 己土 · 용신 土 · 희신 火 · 기신 木 · 구신 水).
사전 가중치는 reviewed:false 초안이므로 **절대 점수가 아니라 상대 순위·신호 존재·
극성**을 고정한다(docs/07 리스크 1: 순위 중심). 가중치 검수/조정 시에도 이 계약은
유지되어야 한다(docs/05 회귀 기준: "갑기합+정관+기신 → 원치 않는 이동/직업변화 상위권").
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import EventScorer, GraphIndex, build_event_graph, filter_year_candidates
from saju_engines.event_scoring import daewoon_transition_weight
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventCandidate, EventKey
from saju_shared_types.ganji_calendar import GanjiLevel

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"


@pytest.fixture(scope="module")
def chart():
    """기준 차트(기준일 2026-06-11 → 세운 2022~2031 범위)."""
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))


@pytest.fixture(scope="module")
def scorer() -> EventScorer:
    """사전 기반 스코어러(모듈 1회 로드)."""
    return EventScorer(_DICTS)


@pytest.fixture(scope="module")
def year_candidates(chart, scorer: EventScorer) -> list[EventCandidate]:
    """세운 후보 전체(2022~2031)."""
    return scorer.score(chart, levels={GanjiLevel.YEAR})


def _period(cands: list[EventCandidate], period: str) -> list[EventCandidate]:
    """기간 라벨로 후보를 추린다(점수 내림차순 유지)."""
    return [c for c in cands if c.period == period]


# 케이스 1 — 갑기합+정관+기신 → career_change 상위권 (docs/05 회귀 기준).
def test_case01_gabgihap_jeonggwan_gisin_career_top(year_candidates) -> None:
    y2024 = _period(year_candidates, "2024")  # 甲辰 — 운 甲 + 원국 己(일간)
    top3 = {c.event_key for c in y2024[:3]}
    assert EventKey.CAREER_CHANGE in top3


# 케이스 2 — 같은 신호 매핑이 강제성(negative_or_forced) 신호를 포함한다.
def test_case02_gisin_rule_signal_forced(year_candidates) -> None:
    y2024 = _period(year_candidates, "2024")
    career = next(c for c in y2024 if c.event_key is EventKey.CAREER_CHANGE)
    # 정관합+기신 매핑(rule_career_00)이 신호로 잡혀야 한다.
    assert any(s.name == "rule_career_00" for s in career.signals)


# 케이스 3 — 갑기합 → contract 후보 동반 (docs/05 예시 eventCandidates).
def test_case03_gabgihap_contract_candidate(year_candidates) -> None:
    y2024 = _period(year_candidates, "2024")
    assert any(c.event_key is EventKey.CONTRACT for c in y2024)


# 케이스 4 — 역마+巳亥충 → relocation·travel 후보 (2025 乙巳).
def test_case04_yeokma_clash_relocation(year_candidates) -> None:
    y2025 = _period(year_candidates, "2025")
    keys = {c.event_key for c in y2025}
    assert EventKey.RELOCATION in keys and EventKey.TRAVEL in keys
    relocation = next(c for c in y2025 if c.event_key is EventKey.RELOCATION)
    assert any("충" in s.name or s.type == "rule_match" for s in relocation.signals)


# 케이스 5 — evidence path는 운→간지→관계/규칙→이벤트 노드를 갖춘다.
def test_case05_evidence_path_structure(year_candidates, scorer: EventScorer) -> None:
    y2024 = _period(year_candidates, "2024")
    career = next(c for c in y2024 if c.event_key is EventKey.CAREER_CHANGE)
    assert career.evidence_path[0].startswith("year_2024_")
    assert career.evidence_path[-1] == "event_career_change"
    readable = scorer.readable_path(career)
    assert "세운" in readable[0] and readable[-1] == "이직·직업 변화"


# 케이스 6 — 점수는 0~100으로 클램프된다(다신호 합산 포함).
def test_case06_score_clamped(year_candidates) -> None:
    assert all(0 <= c.score <= 100 for c in year_candidates)


# 케이스 7 — 세운 계층 필터: score≥70 또는 Top5만 통과.
def test_case07_year_hierarchy_filter(year_candidates) -> None:
    filtered = filter_year_candidates(year_candidates)
    top5_scores = sorted((c.score for c in year_candidates), reverse=True)[:5]
    floor = min(top5_scores) if top5_scores else 0
    assert all(c.score >= 70 or c.score >= floor for c in filtered)
    assert len(filtered) <= len(year_candidates)


# 케이스 8 — windfall에는 금기 표현 규칙이 항상 첨부된다 (Graph Retrieval).
def test_case08_windfall_prohibition_attached() -> None:
    graph = build_event_graph(_DICTS)
    index = GraphIndex(graph)
    bundles = index.retrieve([EventKey.WINDFALL])
    assert bundles[0].prohibitions and "당첨" in bundles[0].prohibitions[0]


# 케이스 9 — Graph Retrieval: career_change 역방향 탐색이 관계·규칙 경로를 찾는다.
def test_case09_graph_retrieval_paths() -> None:
    graph = build_event_graph(_DICTS)
    index = GraphIndex(graph)
    bundle = index.retrieve([EventKey.CAREER_CHANGE])[0]
    assert bundle.paths, "career_change로 들어오는 triggers 경로가 있어야 함"
    flat = {n for p in bundle.paths for n in p.nodes}
    assert any(n.startswith("rel_") or n.startswith("rule_") for n in flat)
    assert all(p.nodes[-1] == "event_career_change" for p in bundle.paths)


# 케이스 10 — 교운기 영향도: 교운일에서 1.0, 멀어질수록 단조 감소(뾰족한 분포).
def test_case10_daewoon_transition_weight_shape() -> None:
    jiao = [date(2025, 11, 22)]
    at_zero = daewoon_transition_weight(date(2025, 11, 22), jiao)
    near = daewoon_transition_weight(date(2026, 2, 22), jiao)  # ~3개월
    far = daewoon_transition_weight(date(2027, 11, 22), jiao)  # 2년
    assert at_zero == pytest.approx(1.0)
    assert at_zero > near > far
    # 첨도↑(라플라스형): 3개월 시점 가중이 표준정규(beta=2)보다 낮아야 한다(뾰족한 중심).
    gauss_near = daewoon_transition_weight(date(2026, 2, 22), jiao, beta=2.0)
    assert near < gauss_near


# 보강 — 교운기 신호가 스코어링에 실제 반영되는지(2025-11-22 교운: 2025·2026 세운).
def test_case10b_daewoon_transition_signal_applied(chart, scorer: EventScorer) -> None:
    cands = scorer.score(chart, levels={GanjiLevel.YEAR})
    near_jiao = [c for c in cands if c.period in ("2025", "2026")]
    rule_signals = [
        s for c in near_jiao for s in c.signals
        if s.type == "rule_match" and "교체" in s.effect
    ]
    assert rule_signals, "교운 인접 세운에 대운 교체 신호가 잡혀야 함"
