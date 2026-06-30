"""신살 보정 LLM payload 배선 검증 (SINSAL_MODIFIER_SPEC Phase A-1).

build_llm_input 경유로 ① 후보에 pruned 신살 태그 부착 ② 점수·랭킹·favorability 불변
③ 숫자 weight 미노출 ④ 토큰 한도 통과 를 검증한다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import EventEngineV2, GraphIndex, load_event_graph
from saju_engines import context_reducer as cr
from saju_engines import sinsal_modifier_config as cfg
from saju_engines.context_reducer import build_llm_input, serialize_llm_input, serialize_with_guard
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventKey
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.intent import Domain, IntentJson, QueryType, TimeScope

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"


@pytest.fixture(scope="module")
def chart():
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))


@pytest.fixture(scope="module")
def scorer() -> EventEngineV2:
    return EventEngineV2(_DICTS)


@pytest.fixture(scope="module")
def candidates(chart, scorer):
    return scorer.score_legacy(chart, levels={GanjiLevel.YEAR})


@pytest.fixture(scope="module")
def bundles():
    graph = load_event_graph(_BACKEND / "compiled" / "event_graph_v1.1.0.json")
    return GraphIndex(graph).retrieve([EventKey.CAREER_CHANGE, EventKey.CONTRACT_DOCUMENT])


def _intent(**over) -> IntentJson:
    base = dict(
        intent_id="i1", query_type=QueryType.DOMAIN_ANALYSIS,
        domain=Domain.CAREER, time_scope=TimeScope.MID_TERM,
        event_key=EventKey.CAREER_CHANGE,
    )
    base.update(over)
    return IntentJson(**base)


def test_candidates_carry_pruned_modifiers(chart, candidates, bundles, scorer) -> None:
    payload = build_llm_input("올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer,
                              today=date(2026, 6, 11))
    assert payload.event_candidates
    # 후보당 신살 태그는 최대 3개(pruning 가드).
    for c in payload.event_candidates:
        assert len(c.sinsal_modifiers) <= cfg.SINSAL_PAYLOAD_MAX_PER_EVENT
        # 후보당 domain_match=False 최대 1, 년주 background 최대 1.
        assert sum(1 for m in c.sinsal_modifiers if not m.domain_match) <= 1
    # career 질문 → 적어도 한 후보엔 신살 태그가 붙는다(1980 차트는 월주 신살 보유).
    assert any(c.sinsal_modifiers for c in payload.event_candidates)


def test_modifiers_are_additive_scores_unchanged(
    chart, candidates, bundles, scorer, monkeypatch,
) -> None:
    """신살 태그 유무와 무관하게 score·polarity·favorability·랭킹 불변(순수 enrichment)."""
    base = build_llm_input("올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer,
                           today=date(2026, 6, 11))
    base_core = [
        (c.event_key, c.period, c.score, c.polarity, c.favorability_ko, c.direction)
        for c in base.event_candidates
    ]
    # 신살 태그를 강제로 비활성화한 payload 와 핵심 필드가 완전히 동일해야 한다.
    monkeypatch.setattr(cr, "select_llm_sinsal_modifiers", lambda mods, **kw: [])
    empty = build_llm_input("올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer,
                            today=date(2026, 6, 11))
    empty_core = [
        (c.event_key, c.period, c.score, c.polarity, c.favorability_ko, c.direction)
        for c in empty.event_candidates
    ]
    assert base_core == empty_core  # 점수·랭킹·길흉 불변
    assert all(not c.sinsal_modifiers for c in empty.event_candidates)


def test_no_numeric_weight_exposed(chart, candidates, bundles, scorer) -> None:
    payload = build_llm_input("올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer,
                              today=date(2026, 6, 11))
    for c in payload.event_candidates:
        for m in c.sinsal_modifiers:
            dumped = m.model_dump()
            assert "internal_weight" not in dumped
            assert "internal_factors" not in dumped
    # 직렬화 본문의 '신살 보조' 줄에 숫자(점수·계수)가 노출되지 않는다.
    text = serialize_llm_input(payload)
    for line in text.splitlines():
        if "신살 보조" in line:
            assert not any(ch.isdigit() for ch in line)


def test_serialized_prompt_within_guard_with_modifiers(chart, candidates, bundles, scorer) -> None:
    payload = build_llm_input("올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer,
                              today=date(2026, 6, 11))
    text, _tokens = serialize_with_guard(payload, "chat_single")  # 한도 초과 시 예외
    assert "신살 보조" in text  # 태그가 본문에 직렬화됨


# ── Phase B-2 챗 + 트림 우선순위(Tier0 신살 먼저 제거) ──

def test_chat_candidates_carry_channel_note(chart, candidates, bundles, scorer) -> None:
    payload = build_llm_input("올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer,
                              today=date(2026, 6, 11))
    text = serialize_llm_input(payload)
    # 도메인 질문이면 채널 색채 노트가 본문에 직렬화될 수 있다(재활성 기간이 있을 때).
    assert any(c.sinsal_channel_note for c in payload.event_candidates) or "시기색채" not in text


def test_drop_sinsal_aux_noop_without_sinsal(chart, candidates, bundles, scorer) -> None:
    from saju_engines.context_reducer import _drop_sinsal_aux
    payload = build_llm_input("올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer,
                              today=date(2026, 6, 11))
    stripped = _drop_sinsal_aux(payload)
    again = _drop_sinsal_aux(stripped)
    assert again is stripped  # 신살 없는 payload는 동일 객체(복사 회피)
    for c in stripped.event_candidates:
        assert not c.sinsal_modifiers and not c.sinsal_channel_note


def test_trim_drops_sinsal_before_excerpts(chart, candidates, bundles, scorer) -> None:
    """토큰 초과 시 신살 보조가 먼저 빠지고 고정 prefix(해석 발췌)는 보존된다(Tier0)."""
    from saju_engines.context_reducer import _drop_sinsal_aux
    from saju_engines.llm_guard import estimate_tokens
    payload = build_llm_input("올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer,
                              today=date(2026, 6, 11))
    if not any(c.sinsal_modifiers or c.sinsal_channel_note for c in payload.event_candidates):
        return  # 신살이 없으면 트림 우선순위 무관(스킵)
    n_tok = estimate_tokens(serialize_llm_input(_drop_sinsal_aux(payload)))
    reserve = 20000 - n_tok - 5  # full 초과·no_sinsal 통과 유도
    text, _ = serialize_with_guard(payload, "chat_single", reserve_tokens=reserve)
    assert "신살 보조" not in text and "시기색채" not in text  # 신살 먼저 제거
    assert ("보조 — 단독 판정" in text) or ("명식 해석" in text)  # excerpt(prefix) 보존
