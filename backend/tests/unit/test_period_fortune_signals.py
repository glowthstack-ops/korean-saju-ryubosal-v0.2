"""월·연 총운 입력의 사건 신호 보강(2026-10-16 데굴님 승인) 회귀.

실사례: 데굴님 명식(1980-11-22 09:40 서울 남) 2026-10 권고사직 — "이번달 운세는 어때?" 입력에
사건 후보가 비어('후보 없음') 이동 후보(비겁 용신 시드)와 [이동 주체 미상] 지시문이 빠졌고,
'일·직업 100점' + '강한 용신운' 만 남아 LLM 이 '직장 유리·주도권'으로 읽었다.
고정: ①월·연 총운에 해당 기간 주요 후보 Top-3 ②슬롯 '주 신호' + 활성 강도 고지 ③비겁 이동 시드 ×
이후 흐름 조건부 문구(용신이라는 이유만으로 '나쁘지 않다' 금지 — 데굴님 정정) ④일 총운은 불변.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import saju_api.services.chat_service as cs
from saju_engines.conversation_store import ConversationStore
from saju_engines.dictionaries import MobilityFlowTextFile, _lint_mobility_flow_text
from saju_engines.period_fortune_signals import (
    PERIOD_FORTUNE_TOP_N,
    annotate_slots,
    assess_following_flow,
    load_mobility_flow,
    mobility_flow_lines,
    select_period_candidates,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventCandidate, EventPolarity
from saju_shared_types.llm_input import PeriodFortune, PeriodFortuneSlot
from saju_shared_types.luck import LuckPillar

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_TODAY = date(2026, 10, 16)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:40", birth_place_name="서울",
    gender="male", reference_date="2026-10-16",
)


def _dry(question: str) -> str:
    r = cs.chat(_BIRTH, question, _TODAY, dry_run=True, store=ConversationStore(), owner_id="t")
    assert r.status == "dry_run", r.answer
    return r.prompt_preview or ""


# ── 라이브 경로(dry-run) ────────────────────────────────────────────────────


def test_month_overview_prompt_carries_mobility_candidate_and_directive():
    text = _dry("이번달 운세는 어때?")
    assert "질문 기간 내 해당 도메인 후보 없음" not in text
    assert "이직·직업 변화 @ 2026-10" in text
    assert "[이동 주체 미상]" in text
    assert "주 신호: 이직·직업 변화" in text and "이동·주체 미상" in text
    assert "슬롯 점수는 그 분야 활성 강도이지 길흉·유불리가 아니다" in text
    # 비겁 용신 시드 + 이후 흐름 긍정 → '나쁘지 않게' 는 두 조건이 함께 있을 때만.
    assert "이동 흐름(비겁 용신 시드 × 이후 흐름 긍정" in text
    assert "근거(이후 운의 용기신 역할): 2026-11" in text
    assert "'이동 뒤 흐름'은" in text  # 월간 지시문 보강


def test_month_overview_candidate_count_is_capped():
    text = _dry("이번달 운세는 어때?")
    n = sum(1 for ln in text.splitlines() if ln.startswith("후보 ") and " @ 2026-10" in ln)
    assert 1 <= n <= PERIOD_FORTUNE_TOP_N


def test_daily_overview_unchanged_without_life_event_candidates():
    text = _dry("오늘 운세 알려줘")
    assert "[해당 일 운세" in text or "[해당 일" in text
    assert "주 신호:" not in text and "이동 흐름(" not in text


def test_yearly_overview_carries_candidates_and_flow_basis_years():
    text = _dry("2027년 운세는 어때?")
    assert "[해당 연 총운" in text
    assert "후보 1/" in text
    if "이동 흐름(" in text:
        assert "근거(이후 운의 용기신 역할): 2028" in text


# ── 단위 ────────────────────────────────────────────────────────────────────


def _cand(key: str, period: str, score: int, polarity=EventPolarity.POSITIVE, evidence=()):
    return EventCandidate(
        event_key=key, event_type="progress", period=period, score=score, confidence="medium",
        polarity=polarity, evidence_path=list(evidence),
    )


def test_select_period_candidates_filters_by_label_and_caps():
    pool = [
        _cand("wealth_change", "2026-10", 94), _cand("career_change", "2026-10", 79),
        _cand("contract_document", "2026-10", 70), _cand("relocation", "2026-10", 60),
        _cand("job_gain", "2026-11", 99), _cand("marriage_signal", "2026", 90),
    ]
    sel = select_period_candidates(pool, "monthly", "2026-10")
    assert [str(c.event_key) for c in sel] == [
        "wealth_change", "career_change", "contract_document",
    ]
    assert [str(c.event_key) for c in select_period_candidates(pool, "yearly", "2026")] == [
        "marriage_signal"
    ]
    assert select_period_candidates(pool, "daily", "2026-10-16") == []


def _pf() -> PeriodFortune:
    return PeriodFortune(
        fortune_type="monthly", period_label="2026-10", ganji="戊戌", pillar_line="x",
        slots=[
            PeriodFortuneSlot(name="일·직업", score=100, summary="점수 100"),
            PeriodFortuneSlot(name="재물", score=50, summary="점수 50"),
            PeriodFortuneSlot(name="건강", score=51, summary="점수 51"),
        ],
    )


def test_annotate_slots_attaches_main_signals_by_domain():
    pf = _pf()
    annotate_slots(pf, [
        _cand("wealth_change", "2026-10", 94),
        _cand("career_change", "2026-10", 79, EventPolarity.CONDITIONAL, ["PEER_YONGSIN_MOBILITY"]),
    ])
    by = {s.name: s.summary for s in pf.slots}
    assert by["일·직업"].endswith("주 신호: 이직·직업 변화(조건부·이동·주체 미상)")
    assert by["재물"].endswith("주 신호: 재물 변화(기회 쪽)")
    assert by["건강"] == "점수 51"
    assert pf.slot_note.startswith("(슬롯 점수는")


def test_annotate_slots_noop_without_candidates():
    pf = _pf()
    annotate_slots(pf, [])
    assert pf.slot_note == "" and pf.slots[0].summary == "점수 100"


def _pillar(label: str, ganji: str) -> LuckPillar:
    return LuckPillar(
        label=label, period_type="month" if len(label) == 7 else "year", ganji=ganji,
        stem=ganji[0], branch=ganji[1], stem_ten_god="x", branch_ten_god="y",
    )


_FAV_EARTH_YONG = {"土": "용신", "火": "희신", "金": "한신", "水": "구신", "木": "기신"}


def test_following_flow_verdicts():
    cfg = load_mobility_flow(_DICTS)
    good = [_pillar("2026-11", "戊戌"), _pillar("2026-12", "丙午")]   # 土·土·火·火 → 긍정
    bad = [_pillar("2026-11", "甲寅"), _pillar("2026-12", "壬子")]    # 木·木·水·水 → 부정
    mixed = [_pillar("2026-11", "甲戌"), _pillar("2026-12", "庚申")]  # 木·土·金·金 → 엇갈림
    assert assess_following_flow(good, _FAV_EARTH_YONG, cfg)[0] == "positive"
    assert assess_following_flow(bad, _FAV_EARTH_YONG, cfg)[0] == "negative"
    assert assess_following_flow(mixed, _FAV_EARTH_YONG, cfg)[0] == "mixed"
    assert assess_following_flow([], _FAV_EARTH_YONG, cfg) == ("mixed", "")
    assert assess_following_flow(good, {}, cfg) == ("mixed", "")


@pytest.mark.parametrize(
    ("seed", "pillars", "needle", "forbidden"),
    [
        ("PEER_YONGSIN_MOBILITY", [_pillar("2026-11", "戊戌")], "나쁘지 않게 흐를 수 있다",
         "시간이 걸릴"),
        ("PEER_YONGSIN_MOBILITY", [_pillar("2026-11", "甲寅")], "시간이 걸릴 수 있다", "나쁘지 않"),
        ("PEER_YONGSIN_MOBILITY", [_pillar("2026-11", "甲戌")], "엇갈려", "나쁘지 않"),
        ("PEER_GISIN_MOBILITY", [_pillar("2026-11", "戊戌")], "오히려 맞을 수 있다", "나쁘지 않"),
        ("PEER_GISIN_MOBILITY", [_pillar("2026-11", "甲寅")], "바로 안정되기 어려울", "나쁘지 않"),
    ],
)
def test_mobility_flow_text_depends_on_role_and_following_flow(seed, pillars, needle, forbidden):
    cands = [_cand("career_change", "2026-10", 75, EventPolarity.CONDITIONAL, [seed])]
    lines = mobility_flow_lines(cands, pillars, _FAV_EARTH_YONG, load_mobility_flow(_DICTS))
    assert lines and needle in lines[0] and forbidden not in lines[0]
    assert "주체 미상" in lines[0]


def test_mobility_flow_silent_without_peer_seed():
    cands = [_cand("career_change", "2026-10", 75), _cand("wealth_change", "2026-10", 90)]
    assert mobility_flow_lines(cands, [_pillar("2026-11", "戊戌")], _FAV_EARTH_YONG) == []


def test_mobility_flow_dictionary_valid_and_linted():
    data = json.loads((_DICTS / "interpretations" / "mobility_flow_text.json").read_text("utf-8"))
    parsed = MobilityFlowTextFile.model_validate(data)
    assert _lint_mobility_flow_text(parsed) == []
    assert sum(1 for it in parsed.items if "나쁘지 않" in it.text) == 1


def test_peer_mobility_texts_no_longer_assert_post_move_quality_unconditionally():
    data = json.loads(
        (_DICTS / "interpretations" / "transit_peer_mobility_text.json").read_text("utf-8")
    )
    by = {it["id"]: it["text"] for it in data["items"]}
    assert "나쁘지 않게" not in by["peer_yongsin_mobility"]
    assert "이후 운의 흐름이 정한다" in by["peer_yongsin_mobility"]
    assert "이후 운의 흐름이 정한다" in by["peer_gisin_mobility"]
