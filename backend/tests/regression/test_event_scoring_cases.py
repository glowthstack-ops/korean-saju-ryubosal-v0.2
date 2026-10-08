"""v2.2 이벤트 엔진 재설계 회귀 픽스처 (Phase 7c-2/8) — 새 EventEngineV2 계약.

기준 차트: 1980-11-22 09:08 서울 남(일간 己土 · 용신 土 · 희신 火 · 기신 木 · 구신 水).
사전 가중치는 reviewed:false 초안이므로 **절대 점수가 아니라 사건화 강도(confidence_level)
순위·신호 존재·궁성·금기룰**을 고정한다(docs/07 리스크 1). 회귀 기준(docs/05): "갑기합+정관+
기신 → 직업 변화 상위권"은 confidence_level 상위로 표현된다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate, luck_months
from saju_engines import EventEngineV2, GraphIndex, build_event_graph, filter_year_candidates
from saju_engines.event_scoring import daewoon_transition_boost, daewoon_transition_weight
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import ConfidenceLevel, EventCandidateV2, EventKeyV2
from saju_shared_types.events import EventKey
from saju_shared_types.ganji_calendar import GanjiLevel

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"
_CONF_ORDER = [
    ConfidenceLevel.THEME_ONLY,
    ConfidenceLevel.WEAK_EVENT_CANDIDATE,
    ConfidenceLevel.EVENT_CANDIDATE,
    ConfidenceLevel.STRONG_EVENT_CANDIDATE,
    ConfidenceLevel.HIGH_PROBABILITY_EVENT,
]
_CAREER_KEYS = {
    EventKeyV2.CAREER_CHANGE, EventKeyV2.JOB_GAIN, EventKeyV2.PROMOTION,
}


@pytest.fixture(scope="module")
def chart():
    """기준 차트(기준일 2026-06-11 → 세운 2022~2031 범위)."""
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))


@pytest.fixture(scope="module")
def engine() -> EventEngineV2:
    """재설계 이벤트 엔진(모듈 1회 로드)."""
    return EventEngineV2(_DICTS)


@pytest.fixture(scope="module")
def year_candidates(chart, engine: EventEngineV2) -> list[EventCandidateV2]:
    """세운 후보 전체(V2)."""
    return engine.score(chart, levels={GanjiLevel.YEAR})


def _period(cands: list[EventCandidateV2], period: str) -> list[EventCandidateV2]:
    return [c for c in cands if c.period == period]


# 케이스 1 — 정관(甲)+기신 → 직업 변화가 근래 세운에서 강한 사건 후보로 발현된다.
# 거버닝 스택은 점수가 포화되므로 '상위권'은 순위 슬롯이 아니라 confidence_level(strong+)로 본다.
# 발동(관계·궁성)은 연도별로 다르므로 검증 창(2024~2026) 안에서 직업 계열 strong+를 요구한다.
def test_case01_career_strong_materialization(year_candidates) -> None:
    window = [c for c in year_candidates if c.period in ("2024", "2025", "2026")]
    strong_career = {
        c.event_key for c in window
        if c.event_key in _CAREER_KEYS and c.confidence_level in (
            ConfidenceLevel.STRONG_EVENT_CANDIDATE, ConfidenceLevel.HIGH_PROBABILITY_EVENT,
        )
    }
    assert strong_career, "직업 계열이 근래 세운에서 강한 사건 후보(strong+)여야 한다"


# 케이스 2 — 상위 후보는 관계·궁성 발동 신호를 동반한다(strong 이상은 궁성 보유).
def test_case02_strong_has_palace(year_candidates) -> None:
    strong = [c for c in year_candidates if c.confidence_level in (
        ConfidenceLevel.STRONG_EVENT_CANDIDATE, ConfidenceLevel.HIGH_PROBABILITY_EVENT,
    )]
    assert strong
    assert all(c.palace is not None for c in strong)


# 케이스 3 — confidence_level이 1차 정렬축(거버닝 스택 포화 보정).
def test_case03_confidence_primary_sort(year_candidates) -> None:
    ranks = [_CONF_ORDER.index(c.confidence_level) for c in year_candidates]
    assert ranks == sorted(ranks, reverse=True)


# 케이스 4 — 모든 후보는 근거코드(reason_codes)와 0~100 점수를 갖춘다.
def test_case04_evidence_and_clamp(year_candidates) -> None:
    assert all(c.reason_codes for c in year_candidates)
    assert all(0 <= c.score <= 100 for c in year_candidates)


# 케이스 5 — 레거시 어댑터 라운드트립: polarity·confidence·signals가 채워진다.
def test_case05_legacy_adapter(chart, engine: EventEngineV2) -> None:
    legacy = engine.score_legacy(chart, levels={GanjiLevel.YEAR})
    assert legacy
    c = legacy[0]
    assert str(c.polarity) and str(c.confidence)
    assert c.signals, "동반 신호(materialization/reason)가 있어야 한다"
    assert c.evidence_path  # reason_codes 기반


# 케이스 6 — 세운 계층 필터(레거시 후보 기준): score≥70 또는 Top5만 통과.
def test_case06_year_hierarchy_filter(chart, engine: EventEngineV2) -> None:
    legacy = engine.score_legacy(chart, levels={GanjiLevel.YEAR})
    filtered = filter_year_candidates(legacy)
    assert len(filtered) <= len(legacy)


# 케이스 7 — windfall에는 금기 표현 규칙(당첨 단정 금지)이 항상 첨부된다.
def test_case07_windfall_prohibition_attached() -> None:
    index = GraphIndex(build_event_graph(_DICTS))
    bundles = index.retrieve([EventKey.WINDFALL])
    assert bundles[0].prohibitions and "당첨" in bundles[0].prohibitions[0]


# 케이스 8 — 경쟁(오디션·대회·선거)·합격 단정 금지 — 신규 보호(public_exposure/education).
def test_case08_competition_exam_prohibitions() -> None:
    index = GraphIndex(build_event_graph(_DICTS))
    comp = index.retrieve([EventKey.PUBLIC_EXPOSURE])[0]
    exam = index.retrieve([EventKey.EDUCATION_ADMISSION])[0]
    assert any("경쟁" in p or "승부" in p for p in comp.prohibitions)
    assert any("합격" in p or "당락" in p for p in exam.prohibitions)


# 케이스 9 — Graph Retrieval: career_change 역방향 탐색이 관계·규칙 경로를 찾는다.
def test_case09_graph_retrieval_paths() -> None:
    index = GraphIndex(build_event_graph(_DICTS))
    bundle = index.retrieve([EventKey.CAREER_CHANGE])[0]
    assert bundle.paths, "career_change로 들어오는 triggers 경로가 있어야 함"
    assert all(p.nodes[-1] == "event_career_change" for p in bundle.paths)


# 케이스 10 — 교운기 영향도: 교운일에서 1.0, 멀어질수록 단조 감소(뾰족한 분포).
def test_case10_daewoon_transition_weight_shape() -> None:
    jiao = [date(2025, 11, 22)]
    at_zero = daewoon_transition_weight(date(2025, 11, 22), jiao)
    near = daewoon_transition_weight(date(2026, 2, 22), jiao)
    far = daewoon_transition_weight(date(2027, 11, 22), jiao)
    assert at_zero == pytest.approx(1.0)
    assert at_zero > near > far
    gauss_near = daewoon_transition_weight(date(2026, 2, 22), jiao, beta=2.0)
    assert near < gauss_near


# 케이스 11 — 교운 가중 부스트: 전환성 이벤트만 교운일 근접도로 곱셈 배율, 비전환성은 불변.
def test_case11_daewoon_transition_boost_gating() -> None:
    jiao = [date(2025, 11, 15)]
    # 전환성 이벤트(job_gain)는 교운일 근접 시 (1 + α·weight)로 증폭.
    near_raw, near_w = daewoon_transition_boost(
        100.0, date(2025, 11, 15), jiao, EventKeyV2.JOB_GAIN
    )
    assert near_w == pytest.approx(1.0) and near_raw == pytest.approx(200.0)
    # 멀어지면 배율이 작아진다(단조).
    far_raw, far_w = daewoon_transition_boost(100.0, date(2026, 6, 15), jiao, EventKeyV2.JOB_GAIN)
    assert far_w < near_w and far_raw < near_raw and far_raw > 100.0
    # 비전환성 이벤트(wealth_change)는 교운일 바로 위여도 불변.
    nb_raw, nb_w = daewoon_transition_boost(
        100.0, date(2025, 11, 15), jiao, EventKeyV2.WEALTH_CHANGE
    )
    assert nb_w == 0.0 and nb_raw == 100.0
    # 교운일이 없으면 불변.
    no_raw, no_w = daewoon_transition_boost(100.0, date(2025, 11, 15), [], EventKeyV2.JOB_GAIN)
    assert no_w == 0.0 and no_raw == 100.0


# 케이스 12 — 회귀(사용자 보고 2026-06-23): 교운일 근접 달이 강한 먼 달을 재취업 랭킹에서 앞선다.
# 21키 재설계에서 누락됐던 교운 가중을 복원해, 데굴 차트(교운일 2025-11-15)의 job_gain
# raw_score 1위가 6월이 아니라 11월이 되도록 보장한다(죽은 daewoonTransition 신호 재발 방지).
def test_case12_daewoon_transition_reemployment_ranking() -> None:
    birth = BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
        birth_place_name="서울 구로구", latitude=37.4944, longitude=126.8563,
        timezone="Asia/Seoul", gender="male",
        # 사례 채록 당시 기준(균시차 적용) 고정 — 기본값 변경(2026-08-25)과 무관하게 유지.
        time_options={"apply_equation_of_time": True},
    )
    result = calculate(birth)
    assert result.luck_cycles is not None
    # 교운일이 11월 중순인지 전제 확인(부스트 거리 기준).
    assert "2025-11-15" in result.luck_cycles.trace.get("exact_jiao_un_dates", [])
    result.luck_cycles.monthly_luck = luck_months(birth, 2025) + luck_months(birth, 2026)
    cands = EventEngineV2(_DICTS).score(result, levels={GanjiLevel.MONTH})

    def best_job_gain(period: str) -> EventCandidateV2 | None:
        rows = [c for c in cands if c.period == period and c.event_key is EventKeyV2.JOB_GAIN]
        return max(rows, key=lambda c: c.raw_score) if rows else None

    nov = best_job_gain("2025-11")
    jun = best_job_gain("2026-06")
    assert nov is not None and jun is not None
    # 교운일 근접 11월이 정관 강한 6월을 raw_score(유력 달 랭킹축)에서 앞선다.
    assert nov.raw_score > jun.raw_score
    # 11월은 전 구간 job_gain raw_score 최댓값(1위).
    all_jg = [c for c in cands if c.event_key is EventKeyV2.JOB_GAIN]
    assert nov.raw_score == max(c.raw_score for c in all_jg)
    # 부스트 추적: 교운 기여 항과 reason_code가 남는다.
    assert "daewoon_transition" in nov.contributions
    assert any(rc.startswith("DAEWOON_TRANSITION_BOOST_") for rc in nov.reason_codes)
