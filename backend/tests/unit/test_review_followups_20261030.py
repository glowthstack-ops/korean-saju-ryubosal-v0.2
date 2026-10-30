"""2026-10-29 작업 점검(2026-10-30) 보강 권고 회귀 고정.

- 편인 도식 문구는 간지 단위 블록(직장 운 결·재물 운 결)에서 블록당 1회만.
- 사건 키 career_leave 가 도메인 필터·플래너 graph scope·사전 목록에 등재.
- '지금/다음 대운' 질문은 대운표로 창을 확정(다음 대운이 현재 대운 창으로 답해지던 결함).
- 단위가 붙은 범위 물결표(`2026년~2027년`)도 엔 대시로, 세운 환경 블록 머리줄의 자리표시 `~` 제거.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from saju_api.services import chat_service
from saju_api.services.manse_service import calculate
from saju_engines import yearly_environment
from saju_engines.chart_interpretation import (
    career_exit_lecture_block,
    dosik_texts,
    luck_has_pianyin,
)
from saju_engines.context_reducer import _DOMAIN_EVENT_KEYS
from saju_engines.planner import _DOMAIN_GRAPH_SCOPE
from saju_engines.prompt_notation import normalize_range_tilde
from saju_engines.wealth_lecture import wealth_period_block
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import EventKeyV2
from saju_shared_types.intent import Domain

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_TODAY = date(2026, 10, 30)


def _chart(d: str, t: str = "10:00:00", g: str = "male"):
    return calculate(BirthInput(
        birth_date=date.fromisoformat(d), birth_time=t, birth_place_name="서울", gender=g,
    ))


# ── 편인 도식 1회 ───────────────────────────────────────────────────────────

_PIANYIN_PERIODS = [("2028", "戊辰"), ("2032", "戊子"), ("2026-02", "戊寅")]


def test_dosik_text_once_per_career_block() -> None:
    chart = _chart("1971-10-12")  # 원국 식신 1개 → pianyin_dosik_single
    dm = chart.pillars.day_master
    assert all(luck_has_pianyin(dm, g) for _, g in _PIANYIN_PERIODS)
    dosik = dosik_texts(chart)
    assert len(dosik) == 1
    block = career_exit_lecture_block(chart, _PIANYIN_PERIODS)
    joined = "\n".join(block)
    assert joined.count(dosik[0]) == 1
    assert joined.count("편인 운 공통") == 1
    assert sum(1 for line in block if line.startswith("- 20")) == 3  # 간지별 줄은 유지


def test_dosik_text_once_per_wealth_block() -> None:
    chart = _chart("1971-10-12")
    dosik = dosik_texts(chart)
    block = wealth_period_block(chart, [(p, g, None) for p, g in _PIANYIN_PERIODS])
    assert "\n".join(block).count(dosik[0]) == 1


def test_no_pianyin_no_common_line() -> None:
    chart = _chart("1971-10-12")
    block = career_exit_lecture_block(chart, [("2026-05", "癸巳")])
    assert all("편인 운 공통" not in line for line in block)


# ── career_leave 레지스트리 ─────────────────────────────────────────────────


def test_career_leave_registered_in_domain_filters() -> None:
    assert "career_leave" in _DOMAIN_EVENT_KEYS["career"]
    assert EventKeyV2.CAREER_LEAVE in _DOMAIN_GRAPH_SCOPE[Domain.CAREER]
    assert EventKeyV2.CAREER_LEAVE in _DOMAIN_GRAPH_SCOPE[Domain.HEALTH]


def test_career_leave_registered_in_dictionaries() -> None:
    dur = json.loads(
        (_DICTS / "event_engine" / "conflict_resolver_duration.json").read_text("utf-8")
    )
    types = dur["event_duration_classifier"]["event_duration_types"]
    assert "career_leave" in types["progressive"]["events"]
    add = json.loads(
        (_DICTS / "event_engine" / "transit_ten_god_branching_addendum.json").read_text("utf-8")
    )
    assert "career_leave" in add["volition_rules"]["self_initiated"]["events"]
    assert "career_leave" in add["volition_rules"]["externally_forced"]["events"]
    assert "career_leave" in add["duration_latency_rules"]["delayed_or_blocked"]["events"]
    rules = add["event_disambiguation_rules"]
    assert any(r["id"] == "CAREER_LEAVE_VS_CAREER_CHANGE" for r in rules)
    proc = json.loads((_DICTS / "event_process_types.json").read_text("utf-8"))
    by_id = {it["id"]: it for it in proc["items"]}
    assert "career_leave" in by_id["separation"]["match"]["event_keys"]
    assert "career_leave" in by_id["relief"]["match"]["event_keys"]


# ── 대운 단위 창 ────────────────────────────────────────────────────────────

_B = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date="2026-10-30",
)


def _prompt(q: str) -> str:
    res = chat_service.chat(_B, q, _TODAY, dry_run=True)
    assert res.status == "dry_run", res.answer
    assert res.prompt_preview
    return res.prompt_preview


def test_current_daewoon_question_uses_current_daewoon_window() -> None:
    p = _prompt("지금 대운은 어때요?")
    assert "질문의 시점 표현은 현재 대운 壬辰(2025–2035, 45–54세) 구간으로 해석되었다" in p
    assert "시점이 명시되지 않았다" not in p
    assert "[응답 형식 — 대운 단위] 이 질문은 현재 대운 壬辰(2025–2035, 45–54세) 하나를 묻는다" in p
    assert "대상 구간은 2026–2035년" in p
    assert "시점이 막연하다" not in p


def test_next_daewoon_question_uses_next_daewoon_window() -> None:
    p = _prompt("다음 대운은 어때요?")
    assert "다음 대운 癸巳(2035–2045, 55–64세)" in p
    assert "대상 구간은 2035–2045년" in p
    assert "[대운 배경 — 11년 흐름]" in p
    assert "시점이 막연하다" not in p


def test_vague_future_without_daewoon_word_unchanged() -> None:
    p = _prompt("앞으로 결혼운은 어떨까요?")
    assert "[응답 형식 — 대운 단위]" not in p


# ── 물결표 ─────────────────────────────────────────────────────────────────


def test_unit_suffixed_ranges_normalized() -> None:
    assert normalize_range_tilde("2026년~2027년") == "2026년–2027년"
    assert normalize_range_tilde("10월 ~ 12월") == "10월 – 12월"
    assert normalize_range_tilde("3개월~6개월") == "3개월–6개월"
    assert normalize_range_tilde("30%~40%") == "30%–40%"
    kept = "사용자: 그럼~ 이직은 언제쯤~?"
    assert normalize_range_tilde(kept) == kept


def test_yearly_environment_header_has_no_placeholder_tilde() -> None:
    src = Path(yearly_environment.__file__).read_text("utf-8")
    assert "~'로 쓸 것" not in src and "…'로 쓸 것" in src
