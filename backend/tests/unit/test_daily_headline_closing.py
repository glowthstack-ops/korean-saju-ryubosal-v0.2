"""docs/17 §23-7 — 12운성 끝 문장 폐지 회귀 (2026-11-01 데굴님 승인).

"나누면 일 처리가 훨씬 빨라져요. 동료와 역할을 분담해서 같이 움직여 보세요. 작게 시작한
생각이 크게 자랍니다."처럼 사건을 보지 않는 문장이 카드 끝에 붙던 결함을 막는다. 끝 문장을
없애도 판정은 그대로여야 하고, 과거 계약은 재생이 바뀌면 안 되며, LLM 교정이 마무리 문장을
되살려서도 안 된다.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import pytest

from saju_api.services import daily_fortune_polish as polish
from saju_engines import daily_ilju_fortune as M
from saju_engines.daily_fortune_v2 import compute_board_v2, load_catalog_v2
from saju_shared_types.daily_fortune import (
    DICT_VERSION_BEFORE_HEADLINE_CLOSING_REMOVAL,
    DICT_VERSION_BEFORE_WORDING_REVISION,
    HEADLINE_CLOSING_REMOVAL_EFFECTIVE_FROM,
    DailyFortuneBoard,
    active_dict_version,
)

_LAST_OLD = HEADLINE_CLOSING_REMOVAL_EFFECTIVE_FROM - dt.timedelta(days=1)
_FIRST_NEW = HEADLINE_CLOSING_REMOVAL_EFFECTIVE_FROM
_ENDS = re.compile(r"[.!?♥~]$")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?♥~])\s+")


def _board(d: dt.date, dicts: M.DailyFortuneDicts | None = None) -> DailyFortuneBoard:
    return compute_board_v2(M.build_day_context(d), dicts or M.load_daily_dicts_for(d))


def _old_stage_sentences() -> set[str]:
    """폐지 전 계약의 공용·연애 12운성 결과 문장 전체."""
    old = M.load_daily_dicts_for(_LAST_OLD).templates
    out: set[str] = set()
    for pools in (*old["stage_results"].values(), *old["stage_results_by_stage"].values()):
        for sents in pools.values():
            out.update(sents)
    return out


def _templates_with_sentence_lists(tpl: dict) -> list[dict]:
    fams = list((tpl.get("families") or {}).values())
    return [tpl, *fams, *(f["romantic"] for f in fams if f.get("romantic"))]


@pytest.fixture(scope="module")
def board_new() -> DailyFortuneBoard:
    return _board(_FIRST_NEW)


def test_boundary_keeps_old_board_on_old_contract() -> None:
    assert active_dict_version(_LAST_OLD) == DICT_VERSION_BEFORE_HEADLINE_CLOSING_REMOVAL
    assert active_dict_version(_FIRST_NEW) == DICT_VERSION_BEFORE_WORDING_REVISION
    old = _board(_LAST_OLD)
    assert sum(len(_SENTENCE_BREAK.split(f.headline)) == 3 for f in old.fortunes) > 50


def test_current_dictionary_has_no_stage_closing_pools() -> None:
    """풀 자체를 제거한다 — 경로를 되살려도 붙일 문장이 없어야 한다."""
    tpl = M.load_daily_dicts_for(_FIRST_NEW).templates
    assert tpl["headline_closing"] == "none"
    assert "stage_results" not in tpl and "stage_results_by_stage" not in tpl
    assert not any("stage_result_exclude" in ev for ev in tpl["events"].values())


def test_every_fragment_and_action_ends_with_punctuation() -> None:
    """마침표가 없으면 두 문장이 한 문장으로 붙는다 — 2문장 카드에서는 바로 드러난다."""
    events = M.load_daily_dicts_for(_FIRST_NEW).templates["events"]
    for key, ev in events.items():
        for tpl in _templates_with_sentence_lists(ev):
            for sent in (*tpl["fragments"], *tpl["actions"]):
                assert _ENDS.search(sent), (key, sent)


@pytest.mark.parametrize("offset", [0, 1, 2, 3, 4, 5, 6])
def test_cards_never_carry_a_closing_sentence(offset: int) -> None:
    d = _FIRST_NEW + dt.timedelta(days=offset)
    board = _board(d)
    stage = _old_stage_sentences()
    events = M.load_daily_dicts_for(d).templates["events"]
    shown = [(f.headline_event_key, f.headline) for f in board.fortunes]
    shown += [(None, f.love_line) for f in board.fortunes if f.love_line]
    for key, text in shown:
        assert text is not None
        assert not any(text.endswith(s) for s in stage), text
        # 사건 풀의 결과 문장도 붙지 않는다(중복 회피 사다리 salt≥3 포함).
        if key is not None:
            results = {r for t in _templates_with_sentence_lists(events[key]) for r in t["results"]}
            assert not any(text.endswith(r) for r in results), text


def test_board_stays_unique_with_two_sentences(board_new) -> None:
    headlines = [f.headline for f in board_new.fortunes]
    assert len(set(headlines)) == 60
    groups: dict[str, set[str]] = {}
    for f in board_new.fortunes:
        groups.setdefault(f.ilju[0], set()).add(f.headline)
    assert all(len(v) == 6 for v in groups.values())


def test_removal_changes_text_only_not_judgement(board_new) -> None:
    """같은 날짜를 폐지 전 사전으로 렌더해도 사건·확률·Top5·로또·장소는 같다."""
    before = _board(_FIRST_NEW, M.load_daily_dicts_for(_LAST_OLD))
    assert before.top5 == board_new.top5
    for a, b in zip(before.fortunes, board_new.fortunes, strict=True):
        assert a.ilju == b.ilju and a.headline_event_key == b.headline_event_key
        assert [e.model_dump() for e in a.events] == [e.model_dump() for e in b.events]
        assert a.lucky_place.model_dump() == b.lucky_place.model_dump()
        assert a.lotto_phrase == b.lotto_phrase
        assert (a.love_line is None) == (b.love_line is None)


def _polish_line(board: DailyFortuneBoard, suffix: str) -> str:
    return "\n".join(
        json.dumps(
            {
                "ilju": f.ilju,
                "headline": f"{f.headline} {suffix}" if i == 0 else f.headline,
                "place_phrase": f.lucky_place.phrase,
                "lotto": f.lotto_phrase,
            },
            ensure_ascii=False,
        )
        for i, f in enumerate(board.fortunes)
    )


def test_polish_cannot_add_closing_sentence_on_new_contract(board_new) -> None:
    """모델이 지어 붙인 마무리 문장은 폐기되고 원문 2문장이 남는다."""
    target = board_new.fortunes[0]
    updated, audit = polish.validate_and_apply(
        board_new, _polish_line(board_new, "작게 시작한 생각이 크게 자랍니다.")
    )
    assert audit["reject_reasons"][target.ilju] == "too_many_sentences"
    assert updated.fortunes[0].headline == target.headline
    assert audit["accepted"] == 59


def test_polish_keeps_old_limit_on_old_contract() -> None:
    """폐지 전 보드는 종전 상한(3문장) — 재교정 거동이 바뀌지 않는다."""
    old = _board(_LAST_OLD)
    assert polish._max_sentences(old, "가요. 와요.") == 3
    assert polish._max_sentences(old, "가. 나. 다. 라.") == 4


def test_catalog_events_all_have_templates() -> None:
    """풀 제거가 사건 템플릿을 건드리지 않았는지 — 전 사건 십성 행동 풀 유지."""
    events = M.load_daily_dicts_for(_FIRST_NEW).templates["events"]
    for key in load_catalog_v2().events:
        assert events[key].get("sipseong_actions"), key
