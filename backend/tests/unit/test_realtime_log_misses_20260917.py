"""실로그 미인식 사례(2026-09-17) — '로또 좋은 달' → '9월 소식은 추석 전/후?' 2턴 대화 결함 회귀.

관측된 결함(데굴님 제공 대화):
1. 추석이 시점으로 파싱되지 않아 일 단위 데이터 없이 월운으로 얼버무리고 질문을 회피.
2. 후속 턴 '제안·소식'이 사건 없는 시점 보완으로 잡혀 직전 사건(횡재)을 승계 → 주제 이탈.
3. 단일 달(9월) 질문인데 월별 요약·유력 달 종합이 12개월로 확장돼 12월 손실 서술이 섞임.
4. 월별 요약 행에 십성이 없어 LLM이 丁(己일간 편인)을 '정인'으로 계산(절대원칙 1).
5. 직전 답변 말미의 되물음을 다음 턴에서 '말씀하신 ~'으로 사용자에게 귀속.
"""

from __future__ import annotations

from datetime import date

import saju_api.services.chat_service as cs
from saju_engines.conversation_store import ConversationStore
from saju_engines.query_parser import parse_message
from saju_engines.time_parser import holiday_anchor, parse_time_with_constraints
from saju_manse_core.calendar.lunar_solar_converter import lunar_to_solar
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import EventKey

_TODAY = date(2026, 9, 17)
_BIRTH = BirthInput(
    birth_date="1980-11-22", birth_time="09:40", birth_place_name="서울", gender="male",
)
_Q1 = "올해 남은 달중 로또사기 좋은 달은 언제야?"
_Q2 = "9월의 예상치 못한 제안이나 소식은 추석전에 들어올까 아니면 추석후에 들어올까"


# ── 1. 명절 앵커 ────────────────────────────────────────────────────────────

def test_chuseok_anchor_attached_to_month_range() -> None:
    tr, _scope, _items = parse_time_with_constraints(_Q2, _TODAY)
    assert tr is not None and tr.start == "2026-09" and tr.end == "2026-09"
    assert [a.label for a in tr.anchor_dates] == ["추석"]
    assert tr.anchor_dates[0].date == lunar_to_solar(date(2026, 8, 15), False).isoformat()
    assert tr.anchor_dates[0].date == "2026-09-25"


def test_holiday_alone_becomes_single_month_with_anchor() -> None:
    tr, _scope, _items = parse_time_with_constraints("추석 때 운세 어때?", _TODAY)
    assert tr is not None and tr.start == tr.end == "2026-09"
    assert tr.anchor_dates and tr.anchor_dates[0].label == "추석"


def test_holiday_rolls_to_next_year_when_far_past() -> None:
    a = holiday_anchor("설날 연휴에 여행 가도 될까", date(2026, 11, 20))
    assert a is not None and a.label == "설날"
    assert a.date == lunar_to_solar(date(2027, 1, 1), False).isoformat()


def test_seol_prefix_words_not_mistaken_for_holiday() -> None:
    assert holiday_anchor("설명 좀 해줘. 설득이 필요해", _TODAY) is None


# ── 2. 제안·소식 → 계약·문서 사건(직전 사건 미승계) ───────────────────────

def test_offer_parses_as_contract_document_event() -> None:
    intent = parse_message(_Q2, _TODAY).intents[0]
    assert intent.event_key is EventKey.CONTRACT_DOCUMENT


def test_followup_does_not_inherit_windfall() -> None:
    store = ConversationStore()  # DSN은 스위트 환경(.env)에서 — 기존 실로그 테스트와 동일
    tid = "t-20260917"
    try:
        first = cs.chat(
            _BIRTH, _Q1, _TODAY, dry_run=True, store=store, thread_id=tid, owner_id="t",
        )
        assert first.intents and first.intents[0].event_key is EventKey.WINDFALL
        second = cs.chat(
            _BIRTH, _Q2, _TODAY, dry_run=True, store=store, thread_id=tid, owner_id="t",
        )
    finally:
        store.delete(tid)
    it = second.intents[0]
    assert it.event_key is EventKey.CONTRACT_DOCUMENT, "직전 횡재 사건을 승계하면 안 된다"
    assert it.time_range is not None and it.time_range.start == "2026-09"
    body = second.prompt_preview or ""
    # 3. 단일 달 창 — 월별 요약이 12개월로 늘지 않는다.
    assert "[월별 요약 — 2026-09~2026-09 1개월" in body
    assert "[월별 요약 — 2026-01~2026-12" not in body
    # 1. 앵커 전후 일운 창이 엔진 사실로 들어간다.
    assert "[앵커 전후 일운 — 엔진 확정 사실] 앵커: 추석 2026-09-25." in body
    assert "09-25(추석)" in body
    assert "앵커 전(" in body and "앵커 후(" in body
    # 5. 귀속 규칙(스레드 공통).
    assert "[귀속 규칙 — 스레드 공통]" in body
    # 횡재 디렉티브는 붙지 않는다.
    assert "[생활형 횡재" not in body


# ── 4. 월별 요약 행 십성 병기 ──────────────────────────────────────────────

def test_monthly_overview_row_carries_ten_gods() -> None:
    res = cs.chat(_BIRTH, _Q1, _TODAY, dry_run=True, owner_id="t")
    body = res.prompt_preview or ""
    # 己 일간에게 丁=편인·酉(辛)=식신 — 엔진 표기가 행에 그대로 실린다.
    assert "2026-09 丁酉" in body
    assert "[丁火 편인·희신 / 酉金 식신·한신]" in body
    assert "십성은 이 표기를 그대로 쓰고 직접 계산하지 말 것" in body
    assert "'9월(丁酉월)'처럼 부르고" in body


# ── 6. '내 사주에서 주의해야 할 점' — 명식 범위 주의점(2턴 대화 3번째 질문) ────────

_Q3 = "그럼 내 사주에서 주의해야할 점은 뭐야?"


def test_chart_caution_routes_to_chart_analysis() -> None:
    from saju_shared_types.intent import Domain, QueryType

    it = parse_message(_Q3, _TODAY).intents[0]
    assert it.query_type is QueryType.CHART_ANALYSIS and it.chart_caution
    assert it.domain is Domain.GENERAL and it.time_range is None
    # 분야가 붙은 개운 질문은 기존 경로(REMEDY+분야 기본 기간) 유지.
    it2 = parse_message("내 사주에서 재물 관련해 주의해야 할 점은?", _TODAY).intents[0]
    assert it2.query_type is QueryType.REMEDY and not it2.chart_caution


def test_chart_caution_standalone_not_too_broad() -> None:
    res = cs.chat(_BIRTH, _Q3, _TODAY, dry_run=True, owner_id="t")
    assert res.status == "dry_run", "단독 질문이 too_broad 안내로 빠지면 안 된다"
    body = res.prompt_preview or ""
    assert "[명식 주의점 — 원국 범위]" in body and "[극복 아니라 관리]" in body
    assert "[월별 요약 —" not in body and "[이벤트 후보 —" not in body  # 헤더형(지시문 인용 제외)


def test_chart_caution_in_thread_ignores_inherited_month_and_anchor() -> None:
    from saju_shared_types.intent import Domain

    store = ConversationStore()
    tid = "t-20260917-caution"
    try:
        cs.chat(_BIRTH, _Q1, _TODAY, dry_run=True, store=store, thread_id=tid, owner_id="t")
        cs.chat(_BIRTH, _Q2, _TODAY, dry_run=True, store=store, thread_id=tid, owner_id="t")
        third = cs.chat(_BIRTH, _Q3, _TODAY, dry_run=True, store=store, thread_id=tid, owner_id="t")
    finally:
        store.delete(tid)
    it = third.intents[0]
    assert it.chart_caution and it.time_range is None, "직전 9월 시점을 승계하면 안 된다"
    assert it.domain is Domain.GENERAL and it.event_key is None
    body = third.prompt_preview or ""
    assert "[명식 주의점 — 원국 범위]" in body
    assert "질문 기간: 2026-09" not in body
    assert "[앵커 전후 일운" not in body, "추석 앵커가 다음 턴까지 따라오면 안 된다"
    assert "[월별 요약 —" not in body
