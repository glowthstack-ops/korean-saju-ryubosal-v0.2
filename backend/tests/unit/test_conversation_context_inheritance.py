"""멀티턴 맥락 패키지 상속 회귀 테스트 (v1, 2026-07-01).

SSOT: doc/v2_2/MULTITURN_CONTEXT_INHERITANCE.md. 실로그 결함(1턴 '난 언제쯤 돈이 생길까?' →
2턴 '2026년'이 재물 스레드를 잃고 일반 총운으로 흐름)의 회귀 고정. bare 절대시점 후속 인식(P0),
'연도+새 도메인' 오상속 수정(P0b), offer-slot 링킹·월별 승격(P1)을 검증한다.
"""

from __future__ import annotations

from datetime import date

from saju_engines.conversation import ConversationEngine
from saju_shared_types.conversation import ConversationState
from saju_shared_types.intent import (
    Domain,
    Granularity,
    IntentJson,
    QueryType,
    TimeRange,
)

_TODAY = date(2026, 7, 1)


def _state(
    domain: Domain,
    qtype: QueryType,
    *,
    granularity: Granularity = Granularity.YEAR,
    start: str = "2026",
    offer: str = "",
) -> ConversationState:
    last = IntentJson(
        intent_id="t1", query_type=qtype, domain=domain,
        time_range=TimeRange(type="absolute", granularity=granularity, start=start),
    )
    return ConversationState(
        thread_id="x", turn_no=1, active_topic=domain, last_intent=last, last_offer=offer,
    )


def _run(state: ConversationState, text: str) -> IntentJson:
    parsed, _ns, _res, _link = ConversationEngine().process_turn(state, text, _TODAY)
    return parsed.intents[0]


# ── 1. 재물 타이밍 → "2026년": 재물 도메인·연도 상속 ──
def test_bare_year_inherits_wealth() -> None:
    it = _run(_state(Domain.WEALTH, QueryType.TIMING_SEARCH), "2026년")
    assert it.domain is Domain.WEALTH
    assert it.query_type is QueryType.TIMING_SEARCH  # 총운으로 리셋되지 않음
    assert it.time_range is not None and it.time_range.start.startswith("2026")


# ── 1b. offer가 '월별 흐름'이면 granularity 월로 승격 ──
def test_bare_year_with_monthly_offer_promotes_to_month() -> None:
    it = _run(
        _state(Domain.WEALTH, QueryType.TIMING_SEARCH, offer="어느 해의 월별 흐름을 볼까요?"),
        "2026년",
    )
    assert it.domain is Domain.WEALTH
    assert it.time_range is not None and it.time_range.granularity is Granularity.MONTH


# ── 2. "2026년 총운": 상속 금지(새 총운 스레드) ──
def test_year_plus_overview_does_not_inherit() -> None:
    it = _run(_state(Domain.WEALTH, QueryType.TIMING_SEARCH), "2026년 총운")
    assert it.domain is Domain.GENERAL
    assert it.query_type is QueryType.FORTUNE_OVERVIEW


# ── 3. "2026년 연애운": 새 도메인이 이김(재물 오상속 금지) ──
def test_year_plus_new_domain_switches() -> None:
    it = _run(_state(Domain.WEALTH, QueryType.TIMING_SEARCH), "2026년 연애운")
    assert it.domain is Domain.RELATIONSHIP
    assert it.time_range is not None and it.time_range.start.startswith("2026")


# ── 4. "내년": 상대 절대시점도 재물 상속 ──
def test_relative_year_inherits_wealth() -> None:
    it = _run(_state(Domain.WEALTH, QueryType.TIMING_SEARCH), "내년")
    assert it.domain is Domain.WEALTH


# ── 5. 재물 월별 스레드 → "5월": 재물 상속 + 월 단위 ──
def test_bare_month_inherits_wealth_month() -> None:
    it = _run(
        _state(Domain.WEALTH, QueryType.DOMAIN_ANALYSIS,
               granularity=Granularity.MONTH, start="2026-05"),
        "5월",
    )
    assert it.domain is Domain.WEALTH
    assert it.time_range is not None and it.time_range.granularity is Granularity.MONTH


# ── 6. 이사운 스레드 → "2026년": 이사 도메인 상속 ──
def test_bare_year_inherits_relocation() -> None:
    it = _run(_state(Domain.RELOCATION, QueryType.DOMAIN_ANALYSIS), "2026년")
    assert it.domain is Domain.RELOCATION


# ── 7. offer 없음 + "2026년": 활성 스레드가 강하면(도메인 확정) 그 스레드 상속 ──
def test_bare_year_without_offer_follows_active_thread() -> None:
    it = _run(_state(Domain.WEALTH, QueryType.TIMING_SEARCH, offer=""), "2026년")
    assert it.domain is Domain.WEALTH  # 스레드 강함 → 상속
    # 활성 스레드가 general(약함)이면 상속해도 general 유지(무해).
    it_g = _run(_state(Domain.GENERAL, QueryType.FORTUNE_OVERVIEW, offer=""), "2026년")
    assert it_g.domain is Domain.GENERAL


# ── 8. 일반 운세 요청은 직전 특정 주제를 승계하지 않는다(과승계 차단, 2026-07-01) ──
def test_general_fortune_resets_prior_topic() -> None:
    # 이사(relocation) 스레드 뒤 '내일 운세를 알려줘' → 일반 운세로 리셋(이사 승계 금지).
    reloc = _state(Domain.RELOCATION, QueryType.DOMAIN_ANALYSIS, start="2026-07-04")
    it = _run(reloc, "내일 운세를 알려줘")
    assert it.domain is Domain.GENERAL and it.event_key is None
    assert it.query_type is QueryType.FORTUNE_OVERVIEW
    # '운세 알려줘'(시점 없음)도 리셋.
    assert _run(reloc, "운세 알려줘").domain is Domain.GENERAL
    # 단, 도메인이 명시되면(내일 재물운) 그 도메인은 유지(무조건 리셋 아님).
    assert _run(reloc, "내일 재물운").domain is Domain.WEALTH


# ── 9. '관계/사이' 질문은 직전 이사 스레드를 승계하지 않고 관계 도메인으로 전환 ──
def test_relationship_question_switches_from_relocation() -> None:
    reloc = _state(Domain.RELOCATION, QueryType.DOMAIN_ANALYSIS, start="2026-07-04")
    assert _run(reloc, "ㄱㄱ과 나는 어떤 관계일까?").domain is Domain.RELATIONSHIP
    assert _run(reloc, "우리 사이는 어때?").domain is Domain.RELATIONSHIP
