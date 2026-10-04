"""주 틀(일~토) 회귀 — 로또 판매 회차·요일 범위·주 틀 정정 후속·용어/병기 후처리.

실로그(2026-10-04 일요일):
  ① '다음주중 로또사기 좋은 날' → 월~일(10/5~10/11)로 잡혀 다른 회차인 10/11(일)을 추천.
  ② '한주를 일요일부터 토요일까지로 잡고 확인해줘' → '일요일' 한 단어만 집혀 오늘 하루로 축소.
  ③ '다음주' 질문에 '이번 주'로 답함. ④ '乙卯(乙卯(을묘))' 중첩 병기. ⑤ 식신+정재를 '상관생재'.
로또는 일요일~토요일 저녁 판매분을 토요일 저녁에 추첨한다 — 주 = 판매 회차(데굴님 확정).
"""

from __future__ import annotations

from datetime import date

from saju_api.services.chat_service import (
    _normalize_ganji_gloss,
    _week_frame_notes,
    finalize_answer_text,
)
from saju_api.services.llm_client import _sanitize_output
from saju_engines.conversation import ConversationEngine
from saju_engines.output_wealth_term import fix_wealth_generation_term
from saju_engines.time_parser import WEEK_FRAME_SUN_SAT, parse_time
from saju_shared_types.conversation import ConversationState
from saju_shared_types.events import EventKey
from saju_shared_types.intent import Granularity, QueryType, TimeRange

_SUN = date(2026, 10, 4)  # 일요일
_WED = date(2026, 10, 7)  # 수요일
_SAT = date(2026, 10, 10)  # 토요일


def _span(text: str, today: date) -> tuple[str | None, str | None, str | None]:
    tr, _ = parse_time(text, today)
    assert tr is not None
    return tr.start, tr.end, tr.week_frame


def _turns(today: date, *texts: str) -> list:
    eng = ConversationEngine()
    state = ConversationState(thread_id="t")
    out = []
    for text in texts:
        parsed, state, _, link = eng.process_turn(state, text, today)
        out.append((parsed.intents[0], link))
    return out


# ── 로또 주 = 판매 회차(일~토) ───────────────────────────────────


def test_lotto_this_week_is_sunday_to_saturday() -> None:
    want = ("2026-10-04", "2026-10-10", WEEK_FRAME_SUN_SAT)
    for today in (_SUN, _WED, _SAT):
        assert _span("이번주 로또 사기 좋은 날", today) == want


def test_lotto_next_week_on_sunday_is_next_round() -> None:
    """일요일의 '다음주'는 오늘 시작한 회차가 아니라 다음 회차다(일요일 시작 확정)."""
    assert _span("다음주중 로또사기 좋은 날을 알려줘", _SUN) == (
        "2026-10-11", "2026-10-17", WEEK_FRAME_SUN_SAT,
    )


def test_non_lotto_week_stays_monday_to_sunday() -> None:
    assert _span("다음주중 이사하기 좋은 날을 알려줘", _SUN) == ("2026-10-05", "2026-10-11", None)
    assert _span("이번주 이사 좋은 날", _WED) == ("2026-10-05", "2026-10-11", None)
    # 연금복권은 추첨 요일이 달라 대상이 아니다.
    assert _span("이번주 연금복권 사기 좋은 날", _WED) == ("2026-10-05", "2026-10-11", None)


def test_week_label_recorded() -> None:
    tr, _ = parse_time("다음주 로또 좋은 날", _WED)
    assert tr is not None and tr.week_label == "다음 주"
    tr, _ = parse_time("이번 주 운세", _WED)
    assert tr is not None and tr.week_label == "이번 주"


def test_lotto_weekday_in_sunday_frame() -> None:
    # 일~토 틀의 '다음주 토요일'은 다음 회차 추첨일.
    assert _span("로또 다음주 토요일 어때", _SUN)[:2] == ("2026-10-17", "2026-10-17")
    # '이번주 일요일'이 지났으면 다가오는 일요일(구어 관행 유지).
    assert _span("로또 이번주 일요일 어때", _WED)[:2] == ("2026-10-11", "2026-10-11")


# ── 요일 범위(C3.4) ──────────────────────────────────────────────


def test_weekday_range_full_week_is_frame_not_single_day() -> None:
    assert _span("한주를 일요일부터 토요일까지로 잡고 확인해줘", _SUN) == (
        "2026-10-04", "2026-10-10", WEEK_FRAME_SUN_SAT,
    )
    assert _span("일요일부터 토요일까지로 봐줘", _WED) == (
        "2026-10-04", "2026-10-10", WEEK_FRAME_SUN_SAT,
    )
    assert _span("월요일부터 일요일까지 운세", _WED) == ("2026-10-05", "2026-10-11", None)


def test_weekday_range_partial() -> None:
    assert _span("월요일부터 수요일까지 운세", _WED)[:2] == ("2026-10-05", "2026-10-07")
    # 이미 끝난 구간이면 다음 주로.
    assert _span("월요일~화요일 운세", _WED)[:2] == ("2026-10-12", "2026-10-13")
    assert _span("다음주 목요일부터 토요일까지", _WED)[:2] == ("2026-10-15", "2026-10-17")


def test_single_weekday_unchanged() -> None:
    assert _span("다음주 금요일 운세", _WED)[:2] == ("2026-10-16", "2026-10-16")
    assert _span("일요일 운세", _SUN)[:2] == ("2026-10-04", "2026-10-04")


# ── 주 틀 정정 후속 ──────────────────────────────────────────────


def test_week_frame_correction_keeps_topic_and_week() -> None:
    """실로그 재현 — 로또 택일 뒤 주 정의 정정이 오늘 하루 운세로 떨어지지 않는다."""
    (first, _), (second, link) = _turns(
        _SUN, "다음주중 로또사기 좋은 날을 알려줘", "한주를 일요일부터 토요일까지로 잡고 확인해줘",
    )
    assert link.is_follow_up
    assert second.query_type is QueryType.DATE_RECOMMENDATION
    assert second.event_key is EventKey.WINDFALL
    assert second.time_range is not None and first.time_range is not None
    assert (second.time_range.start, second.time_range.end) == ("2026-10-11", "2026-10-17")
    assert second.time_range.week_frame == WEEK_FRAME_SUN_SAT
    assert second.time_range.week_label == "다음 주"


def test_week_frame_correction_reframes_prev_monday_week() -> None:
    """월~일로 잡혔던 직전 창(이사 '다음주')을 일~토로 다시 잡는다 — 호칭 기준 재계산."""
    (_, _), (second, link) = _turns(_WED, "다음주 이사 좋은 날", "일요일부터 토요일까지로 봐줘")
    assert link.is_follow_up
    assert second.event_key is EventKey.RELOCATION
    assert second.time_range is not None
    assert (second.time_range.start, second.time_range.end) == ("2026-10-11", "2026-10-17")


def test_followup_next_week_inherits_sunday_frame() -> None:
    (_, _), (second, link) = _turns(_SUN, "이번주 로또사기 좋은 날을 알려줘", "다음 주는?")
    assert link.is_follow_up
    assert second.event_key is EventKey.WINDFALL
    assert second.time_range is not None
    assert (second.time_range.start, second.time_range.end) == ("2026-10-11", "2026-10-17")
    assert second.time_range.week_frame == WEEK_FRAME_SUN_SAT


# ── 택일 블록 기간 기준 안내 ─────────────────────────────────────


def _week_tr(start: str, end: str, frame: str | None, label: str | None) -> TimeRange:
    return TimeRange(
        type="relative", granularity=Granularity.DAY, start=start, end=end,
        week_frame=frame, week_label=label,
    )


def test_frame_notes_lotto_round_and_label() -> None:
    notes = _week_frame_notes(
        _week_tr("2026-10-11", "2026-10-17", WEEK_FRAME_SUN_SAT, "다음 주"),
        EventKey.WINDFALL, _SUN,
    )
    joined = "\n".join(notes)
    assert "'다음 주'" in joined
    assert "2026-10-11(일) ~ 2026-10-17(토)" in joined
    assert "한 회차" in joined and "판매 마감 전" in joined
    assert "20시" not in joined  # 마감 시각은 명시하지 않는다(문구만 — 데굴님 확정)


def test_frame_notes_non_lotto_has_no_round_note() -> None:
    notes = _week_frame_notes(
        _week_tr("2026-10-05", "2026-10-11", None, "다음 주"), EventKey.RELOCATION, _SUN,
    )
    assert len(notes) == 1 and "회차" not in notes[0]
    assert _week_frame_notes(None, EventKey.WINDFALL, _SUN) == []
    assert _week_frame_notes(
        TimeRange(type="absolute", granularity=Granularity.MONTH, start="2026-10", end="2026-10"),
        EventKey.WINDFALL, _SUN,
    ) == []


# ── 후처리: 중첩 병기·생재 용어 ──────────────────────────────────


def test_same_hanja_nested_gloss_collapsed() -> None:
    assert _normalize_ganji_gloss("乙卯(乙卯(을묘))일 역시") == "乙卯(을묘)일 역시"
    assert _sanitize_output("목요일 乙卯(乙卯)일 역시") == "목요일 乙卯(을묘)일 역시"


def test_wealth_generation_term_fixed_by_paragraph_ten_god() -> None:
    src = "己(기)토에게 辛(신)금 식신과 亥(해)수 정재가 찾아와 상관생재의 흐름을 만드니 좋습니다."
    fixed, changes = fix_wealth_generation_term(src)
    assert "식신생재의 흐름" in fixed and "상관생재" not in fixed
    assert changes == [("상관생재", "식신생재")]
    assert "식신생재" in finalize_answer_text(src)


def test_wealth_generation_term_left_alone_without_basis() -> None:
    both = "식신과 상관이 함께 들어와 상관생재로 이어집니다."
    assert fix_wealth_generation_term(both) == (both, [])
    none = "이 시기는 상관생재의 흐름입니다."
    assert fix_wealth_generation_term(none) == (none, [])
    ok = "庚(경)금 상관이 재성을 생하는 상관생재 구조입니다."
    assert fix_wealth_generation_term(ok) == (ok, [])
    # 문단이 다르면 서로 영향을 주지 않는다.
    two = "식신이 들어옵니다.\n\n상관이 재성을 생하는 상관생재입니다."
    assert fix_wealth_generation_term(two) == (two, [])
    rev = "壬(임)수 상관이 재성을 만나 식신생재가 됩니다."
    assert fix_wealth_generation_term(rev)[0] == "壬(임)수 상관이 재성을 만나 상관생재가 됩니다."


# ── 2차 점검(2026-10-04) — 틀 누출·후속 승계·다다음주·지난 요일·주말·회차 지시문 ──


def test_sunday_frame_does_not_leak_to_new_topic() -> None:
    """로또 뒤 이사 질문의 '다음주'는 월~일이다 — 일~토 틀은 로또 주제에 딸린 것."""
    (_, _), (second, _) = _turns(
        _SUN, "이번주 로또 좋은 날", "그럼 이사는 다음주 언제가 좋아?",
    )
    assert second.event_key is EventKey.RELOCATION
    assert second.time_range is not None
    assert (second.time_range.start, second.time_range.end) == ("2026-10-05", "2026-10-11")
    assert second.time_range.week_frame is None


def test_reframe_back_to_monday_keeps_remaining_days() -> None:
    """일요일에 '이번 주'를 월~일로 되돌려도 이미 지난 주가 아니라 남은 날이 있는 주를 잡는다."""
    (_, _), (second, _) = _turns(_SUN, "이번주 로또 좋은 날", "월요일부터 일요일까지로 봐줘")
    assert second.time_range is not None
    assert (second.time_range.start, second.time_range.end) == ("2026-10-05", "2026-10-11")
    assert second.time_range.week_label is None


def test_best_pick_followup_without_reference_word() -> None:
    (first, _), (second, link) = _turns(_SUN, "이번주 로또 좋은 날", "가장 좋은 날은 언제야?")
    assert link.is_follow_up
    assert second.query_type is QueryType.DATE_RECOMMENDATION
    assert second.event_key is EventKey.WINDFALL
    assert second.time_range == first.time_range


def test_bare_weekday_and_month_followups_keep_topic() -> None:
    (_, _), (second, link) = _turns(_SUN, "이번주 로또 좋은 날", "토요일은 어때?")
    assert link.is_follow_up and second.event_key is EventKey.WINDFALL
    assert second.time_range is not None and second.time_range.start == "2026-10-10"
    (_, _), (third, link3) = _turns(_SUN, "이번주 로또 좋은 날", "이번달은?")
    assert link3.is_follow_up and third.event_key is EventKey.WINDFALL
    assert third.time_range is not None and third.time_range.start == "2026-10"


def test_abbreviated_weekday_range() -> None:
    (_, _), (second, link) = _turns(_SUN, "이번주 로또 좋은 날", "일~토로 다시 봐줘")
    assert link.is_follow_up and second.event_key is EventKey.WINDFALL
    assert second.time_range is not None
    assert (second.time_range.start, second.time_range.end) == ("2026-10-04", "2026-10-10")
    assert _span("월~금 운세", _WED)[:2] == ("2026-10-05", "2026-10-09")
    # 월(달) 범위·날짜 뒤 요일은 요일 범위가 아니다.
    assert _span("3월~5월 재물운", _WED)[:2] == ("2026-03", "2026-05")


def test_week_after_next() -> None:
    tr, _ = parse_time("다다음주 로또 좋은 날", _SUN)
    assert tr is not None
    assert (tr.start, tr.end, tr.week_label) == ("2026-10-18", "2026-10-24", "다다음 주")
    assert _span("다다음주 운세", _WED)[:2] == ("2026-10-19", "2026-10-25")
    assert _span("다다음주 금요일 운세", _WED)[:2] == ("2026-10-23", "2026-10-23")


def test_past_weekday() -> None:
    assert _span("지난 일요일은 어땠어?", _WED)[:2] == ("2026-10-04", "2026-10-04")
    assert _span("저번 수요일 운세", _WED)[:2] == ("2026-09-30", "2026-09-30")  # 오늘과 같은 요일
    assert _span("지난주 금요일 운세", _WED)[:2] == ("2026-10-02", "2026-10-02")


def test_weekend_is_saturday_and_sunday() -> None:
    assert _span("이번 주말 운세", _WED) == ("2026-10-10", "2026-10-11", None)
    assert _span("이번주 주말 운세", _WED) == ("2026-10-10", "2026-10-11", None)
    assert _span("다음 주말 이사 좋은 날", _WED) == ("2026-10-17", "2026-10-18", None)
    assert _span("이번 주말 로또 사기 좋은 날", _WED) == ("2026-10-10", "2026-10-11", None)
    # 주 지정어 없는 '주말만'은 시점이 아니라 현실 제약이다.
    assert parse_time("주말만 돼", _WED)[0] is None


def test_lotto_round_directive() -> None:
    from saju_api.services.chat_service import _lotto_round_directive

    (intent, _), = _turns(_SAT, "로또 내일 사도 돼?")
    text = _lotto_round_directive(intent, "로또 내일 사도 돼?", _SAT, None)
    assert text is not None
    assert "2026-10-04(일) ~ 2026-10-10(토)" in text
    assert "2026-10-11(일)부터는 다음 회차" in text
    assert "판매 마감 전" in text
    # 로또가 아니면 없음.
    (other, _), = _turns(_SAT, "이번주 연금복권 운 어때?")
    assert _lotto_round_directive(other, "이번주 연금복권 운 어때?", _SAT, None) is None
