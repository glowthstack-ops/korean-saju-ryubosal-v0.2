"""부동산 매도 질문 라우팅 + 개방형 '언제' 거래형 지평 (2026-10-14 데굴님 승인) 회귀 고정.

실로그: "부동산은 언제쯤 팔릴까"가 사건 없음·general·open_when 으로 10년 digest(2026~2035)에 빠져
2031·2034년을 유력 시기로 답했다. 후보 앵커(계약·문서)가 없어 LLM이 문서 서술을 창작했다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.horizon import resolve_horizon
from saju_engines.query_parser import is_real_estate_sale, parse_message
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventKey
from saju_shared_types.intent import Domain, QueryType

_TODAY = date(2026, 10, 14)
_BIRTH = BirthInput(
    birth_date=date(1980, 11, 22), birth_time="09:40:00", birth_place_name="서울", gender="male",
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("부동산은 언제쯤 팔릴까", True), ("집은 언제 팔릴까", True), ("아파트 매도 시기", True),
        ("땅을 처분하려는데", True), ("상가 매매 언제 하면 좋을까", True),
        ("집안 분위기가 어때", False), ("집중이 잘 될까", False), ("부동산 투자 어때", False),
        ("이사 언제 갈까", False),
    ],
)
def test_real_estate_sale_vocabulary(text, expected):
    assert is_real_estate_sale(text) is expected


def test_sale_question_routes_to_wealth_contract_document():
    it = parse_message("부동산은 언제쯤 팔릴까", _TODAY, current_month_label="2026-10").intents[0]
    assert it.domain is Domain.WEALTH and it.event_key is EventKey.CONTRACT_DOCUMENT
    assert it.event_keys == [EventKey.WEALTH_CHANGE]
    assert it.query_type is QueryType.TIMING_SEARCH
    assert it.time_range is not None and it.time_range.type == "open_when"
    policy = resolve_horizon("부동산은 언제쯤 팔릴까", it)
    assert policy is not None and policy.kind == "transactional_when"


def test_twelve_month_sale_question_keeps_window_and_gets_event():
    it = parse_message(
        "12개월안에 부동산이 팔릴일은 없을까", _TODAY, current_month_label="2026-10",
    ).intents[0]
    assert it.domain is Domain.WEALTH and it.event_key is EventKey.CONTRACT_DOCUMENT
    assert it.time_range is not None and it.time_range.end_offset_days == 360


def test_dry_run_prompt_uses_three_year_horizon_not_ten_year_digest():
    from saju_api.services import chat_service

    resp = chat_service.chat(_BIRTH, "부동산은 언제쯤 팔릴까", _TODAY, True)
    assert resp.status == "dry_run"
    p = resp.prompt_preview or ""
    assert "[답변 지평] 이 질문의 답변 지평은 '앞 12개월 월 단위 + 이후 2년 연 단위(총 3년)'" in p
    assert "[응답 형식] 이 질문은 시점이 막연하다" not in p
    assert "2026~2035 10년" not in p
    assert "[운 흐름 요약 — 앞 12개월은 월 단위, 이후 3개년은" in p
    assert "계약·문서 @" in p  # 사건 후보 앵커


# ── 매수·점포 양도(2026-10-15 데굴님 승인) — 매도만 고쳐 같은 증상이 남아 있던 반례 ──────────

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("아파트는 언제쯤 살 수 있을까", True), ("집을 언제 사면 좋을까", True),
        ("집을 언제 사는게 좋을지", True), ("집 사고 싶은데 언제가 좋을까", True),
        ("내 집 마련은 언제쯤", True), ("아파트 매수 시기", True), ("땅을 구입하려는데", True),
        # 거주 '살다'·동형어는 매수가 아니다.
        ("집에서 살 수 있을까", False), ("이 집 살게 될까", False), ("집은 살만할까", False),
        ("집이 살기 좋을까", False), ("집안 분위기가 어때", False), ("이사 언제 갈까", False),
    ],
)
def test_real_estate_purchase_vocabulary(text, expected):
    from saju_engines.query_parser import is_real_estate_purchase

    assert is_real_estate_purchase(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("가게는 언제 넘기는 게 좋을까", True), ("점포 정리 시기", True), ("집에 가게 될까", False)],
)
def test_shop_transfer_counts_as_sale(text, expected):
    assert is_real_estate_sale(text) is expected


@pytest.mark.parametrize("text", ["아파트는 언제쯤 살 수 있을까", "가게는 언제 넘기는 게 좋을까"])
def test_purchase_and_transfer_route_like_sale(text):
    it = parse_message(text, _TODAY, current_month_label="2026-10").intents[0]
    assert it.domain is Domain.WEALTH and it.event_key is EventKey.CONTRACT_DOCUMENT
    assert it.event_keys == [EventKey.WEALTH_CHANGE]
    assert it.time_range is not None and it.time_range.type == "open_when"
    policy = resolve_horizon(text, it)
    assert policy is not None and policy.kind == "transactional_when"
