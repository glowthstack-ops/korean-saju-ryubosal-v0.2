"""복수 명시 일자·짧은 일 범위 질문의 chat 배선 — 2026-10-02 실답 회귀 고정(데굴님 승인).

사고: 로또 택일 답 뒤 "10월 7일과 9일은 어때?" → 10-07 하나로만 파싱·주입되어 LLM 이 7일만 풀고
"9일 세부 정보는 제공되지 않았다"로 넘겼다. 고정 대상: ① 두 날이 모두 날짜별 블록에 실린다
② 둘째 날도 관계·슬롯까지 같은 깊이(extra_period_fortunes) ③ 복수 날짜 지시문 ④ 관계 감사는
날짜별 의미의 합집합이되 판정이 갈리는 라벨은 제외(10-09 는 절기월 戊戌로 바뀌어 丁壬合 판정이 다름)
⑤ 단일 날짜·주간 경로는 기존 그대로.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services import chat_service
from saju_api.services.chat_service import (
    _explicit_dates,
    _multi_day_focus_dates,
    _period_fortune_type,
    _tr_day_targets,
    _union_relation_semantics,
)
from saju_engines.conversation import _retro_anchor_bare_date
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import Granularity, IntentJson, QueryType, TimeRange

_BIRTH = BirthInput(
    birth_date=date(1980, 11, 22), birth_time="09:40:00", birth_place_name="서울 구로구",
    latitude=37.4944, longitude=126.8563, timezone="Asia/Seoul", gender="male",
)
_T = date(2026, 10, 2)


def _prep(q: str) -> chat_service.ChatResponse:
    res = chat_service.chat(_BIRTH, q, _T, dry_run=True)
    assert res.status == "dry_run"
    return res


@pytest.fixture(scope="module")
def two_days() -> chat_service.ChatResponse:
    return _prep("10월 7일과 9일은 어때?")


# ── 순수 함수 ────────────────────────────────────────────────────────────────
def test_explicit_dates_inherits_month_for_bare_continuation() -> None:
    assert _explicit_dates("10월 7일과 9일은 어때?", 2026) == [date(2026, 10, 7), date(2026, 10, 9)]
    assert _explicit_dates("10월 7일, 9일, 11일", 2026) == [
        date(2026, 10, 7), date(2026, 10, 9), date(2026, 10, 11),
    ]
    # 기간·빈도 꼬리는 날짜가 아니다 / 월이 붙은 다음 날짜는 자체 매치로 처리(중복 없음).
    assert _explicit_dates("10월 7일과 3일 동안", 2026) == [date(2026, 10, 7)]
    assert _explicit_dates("8월 31일과 9월 30일", 2026) == [date(2026, 8, 31), date(2026, 9, 30)]


def _tr(start: str, end: str | None = None, dates: list[str] | None = None, **kw) -> TimeRange:
    return TimeRange(
        type="absolute", granularity=kw.pop("granularity", Granularity.DAY),
        start=start, end=end if end is not None else start, dates=dates or [], **kw,
    )


def test_tr_day_targets_prefers_dates_then_short_range_then_single() -> None:
    assert _tr_day_targets(_tr("2026-10-07", "2026-10-09", ["2026-10-07", "2026-10-09"])) == [
        date(2026, 10, 7), date(2026, 10, 9),
    ]
    assert _tr_day_targets(_tr("2026-10-07", "2026-10-09")) == [
        date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9),
    ]
    assert _tr_day_targets(_tr("2026-10-05", "2026-10-11")) == []  # 주간 — 일별 흐름 블록 담당
    assert _tr_day_targets(_tr("2026-10-07")) == [date(2026, 10, 7)]
    assert _tr_day_targets(_tr("2026-10", granularity=Granularity.MONTH)) is None
    assert _tr_day_targets(_tr("2026-10-02", None, end_offset_days=184)) is None  # offset 창


def test_multi_day_focus_gate() -> None:
    def _intent(tr: TimeRange) -> IntentJson:
        return IntentJson(intent_id="t", query_type=QueryType.FORTUNE_OVERVIEW, time_range=tr)

    listed = _tr("2026-10-07", "2026-10-09", ["2026-10-07", "2026-10-09"])
    assert _multi_day_focus_dates(_intent(listed)) == [date(2026, 10, 7), date(2026, 10, 9)]
    assert len(_multi_day_focus_dates(_intent(_tr("2026-10-07", "2026-10-09")))) == 3
    assert _multi_day_focus_dates(_intent(_tr("2026-10-07"))) == []  # 단일 → 특정일 지시문 몫
    assert _multi_day_focus_dates(_intent(_tr("2026-10-05", "2026-10-11"))) == []  # 주간 제외


def test_period_fortune_type_accepts_dates_but_not_ranges() -> None:
    def _intent(tr: TimeRange) -> IntentJson:
        return IntentJson(intent_id="t", query_type=QueryType.FORTUNE_OVERVIEW, time_range=tr)

    listed = _tr("2026-10-07", "2026-10-09", ["2026-10-07", "2026-10-09"])
    assert _period_fortune_type(_intent(listed), "어때") == "daily"
    assert _period_fortune_type(_intent(_tr("2026-10-07", "2026-10-09")), "어때") is None
    assert _period_fortune_type(_intent(_tr("2026-10-07")), "어때") == "daily"


def test_retro_anchor_shifts_dates_too() -> None:
    tr = _tr("2027-06-17", "2027-06-19", ["2027-06-17", "2027-06-19"])
    back = _retro_anchor_bare_date(tr, date(2026, 9, 6))
    assert back is not None
    assert (back.start, back.end) == ("2026-06-17", "2026-06-19")
    assert back.dates == ["2026-06-17", "2026-06-19"]


# ── dry-run 배선 ─────────────────────────────────────────────────────────────
def test_two_days_both_grounded_with_full_blocks(two_days: chat_service.ChatResponse) -> None:
    p = two_days.prompt_preview or ""
    payload = two_days.postprocess.payload
    assert payload.period_fortune is not None
    assert payload.period_fortune.period_label.startswith("2026-10-07")
    assert [x.period_label[:10] for x in payload.extra_period_fortunes] == ["2026-10-09"]
    assert "[해당 일 운세 — 2026-10-07" in p and "[해당 일 운세 — 2026-10-09" in p
    assert "[해당 날짜들(2026-10-07·2026-10-09) 일운" in p
    assert "2026-10-08" not in p.split("[해당 날짜들")[1].split("]")[1][:200]  # 사이 날 미노출
    assert "2026-10-07:" in p and "2026-10-09:" in p  # [질문한 날짜의 일운] 두 날 모두
    assert "[중요·복수 날짜 질문" in p and "5일 뒤" in p and "7일 뒤" in p
    assert "[중요·특정일 질문" not in p


def test_three_day_range_lists_each_day_with_multi_directive() -> None:
    res = _prep("10월 7일부터 9일까지는 어때?")
    p = res.prompt_preview or ""
    assert "[해당 기간(2026-10-07~2026-10-09) 일별 흐름" in p
    assert all(f"- 2026-10-0{d}(" in p for d in (7, 8, 9))
    assert "[중요·복수 날짜 질문" in p and "6일 뒤" in p
    assert res.postprocess.payload.extra_period_fortunes == []


def test_single_day_path_keeps_single_directive() -> None:
    res = _prep("10월 7일은 어때?")
    p = res.prompt_preview or ""
    assert "[중요·특정일 질문" in p and "[중요·복수 날짜 질문" not in p
    assert res.postprocess.payload.extra_period_fortunes == []
    assert "[해당 일 운세 — 2026-10-09" not in p


def test_relation_audit_union_covers_second_day_and_drops_conflicts(monkeypatch) -> None:
    """관계 감사 합집합 — 둘째 날에만 있는 관계는 잡히고, 날짜별 판정이 갈리는 라벨은 제외된다.

    관계 의미는 플래그(RELATION_SEMANTIC_PATCH/PERIOD_HIERARCHY)가 꺼진 pytest 기준선에서는
    payload 에 실리지 않으므로, 엔진 판정(resolve_*_hap)에서 직접 파생해 날짜별 PeriodFortune 을
    조립한다.
    """
    from saju_api.services.manse_service import calculate
    from saju_engines import period_v2_config
    from saju_engines.relation_semantics import collect_luck_relation_semantics
    from saju_shared_types.llm_input import PeriodFortune

    monkeypatch.setattr(period_v2_config, "RELATION_SEMANTIC_PATCH_ENABLED", True)
    chart = calculate(_BIRTH.model_copy(update={"reference_date": date(2026, 10, 7)}))
    # 10-07: 대운 壬辰 · 세운 丙午 · 월운 丁酉 · 일진 甲寅
    # 10-09: 절기월 戊戌(寒露 10-08) · 일진 丙辰.
    sem1 = collect_luck_relation_semantics(
        chart, ["甲", "壬", "丙", "丁"], ["寅", "辰", "午", "酉"]
    )
    sem2 = collect_luck_relation_semantics(
        chart, ["丙", "壬", "丙", "戊"], ["辰", "辰", "午", "戌"]
    )

    def _pf(label: str, ganji: str, sems) -> PeriodFortune:
        return PeriodFortune(
            fortune_type="daily", period_label=label, ganji=ganji, pillar_line="-",
            relation_semantics=sems,
        )

    first = _pf("2026-10-07 (수)", "甲寅", sem1)
    extras = [_pf("2026-10-09 (금)", "丙辰", sem2)]
    only_second = {s.relation_label for s in sem2} - {s.relation_label for s in sem1}
    assert only_second  # 10-09 에만 있는 관계(午戌반합·申戌방합 등)
    union = _union_relation_semantics(first, extras, "t")
    labels = {s.relation_label for s in union}
    assert only_second <= labels
    # 丁壬合 — 7일(월운 丁酉가 원국 丁과 壬을 쟁합→합반·합거)과 9일(월운 戊戌→木 합화)의
    # 판정이 갈린다.
    first_tj = next(s for s in sem1 if s.relation_label == "丁壬合")
    second_tj = next(s for s in sem2 if s.relation_label == "丁壬合")
    assert first_tj.transformation_state is not second_tj.transformation_state
    assert "丁壬合" not in labels
    # 9일 기준으로 맞는 문장이 7일 판정으로 위반 처리되면 안 된다(첫 값 유지 방식의 오탐 차단).
    text = "9일에는 丁壬合이 木으로 합화합니다."
    assert chat_service._audit_relation_answer(text, first, "t", extras) == text
    # 둘째 날에만 있는 관계의 진짜 역전은 합집합으로만 잡힌다.
    label = sorted(only_second)[0]
    bad = f"{label}으로 서로 묶여 작용이 둔해집니다."
    assert chat_service._audit_relation_answer(bad, first, "t", None) == bad  # 첫 날만으론 미검출
    assert chat_service._audit_relation_answer(bad, first, "t", extras) != bad  # 합집합이면 교정
