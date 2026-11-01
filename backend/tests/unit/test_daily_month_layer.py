"""docs/17 §24 — 이번 달 흐름·조언 층·사건 전용 제안 회귀 (2026-11-01 데굴님 승인).

오늘 카드와 영역을 나눈 이번 달 흐름, 카드 안의 조언 줄, 앞뒤가 맞는 오늘의 제안을 지킨다.
새 층은 문체 전용이라 판정을 바꾸면 안 되고, 과거 계약과 스레드 파일에 새면 안 된다.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import json
import re

import pytest

from saju_api.services import daily_fortune_polish as polish
from saju_api.services.daily_fortune_export import render_threads_text
from saju_engines import daily_ilju_fortune as M
from saju_engines import daily_month_layer as L
from saju_engines.daily_fortune_v2 import compute_board_v2
from saju_shared_types.daily_fortune import (
    HEADLINE_CLOSING_REMOVAL_EFFECTIVE_FROM,
    WORDING_REVISION_EFFECTIVE_FROM,
    DailyFortuneBoard,
)
from saju_shared_types.enums import Branch, Stem

_FIRST = WORDING_REVISION_EFFECTIVE_FROM
_LAST_V116 = _FIRST - dt.timedelta(days=1)
_GIHAE = dt.date(2026, 11, 8)  # 일진 丙戌, 월운 간지 己亥


def _board(d: dt.date, dicts: M.DailyFortuneDicts | None = None) -> DailyFortuneBoard:
    return compute_board_v2(M.build_day_context(d), dicts or M.load_daily_dicts_for(d))


def _layer() -> dict:
    return M.load_daily_dicts_for(_FIRST).templates["month_layer"]


def _without_new_keys() -> M.DailyFortuneDicts:
    """새 사전 키를 뺀 같은 사전 — 판정 불변 비교용."""
    dicts = M.load_daily_dicts_for(_FIRST)
    tpl = copy.deepcopy(dicts.templates)
    tpl.pop("month_layer")
    tpl.pop("headline_action_pool")
    for event in tpl["events"].values():
        event.pop("action_exclude", None)
    return dataclasses.replace(dicts, templates=tpl)


@pytest.fixture(scope="module")
def board() -> DailyFortuneBoard:
    return _board(_GIHAE)


def _sentences(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    items = value.values() if isinstance(value, dict) else value
    return [s for item in items for s in _sentences(item)]  # type: ignore[attr-defined]


def test_layer_coverage() -> None:
    layer = _layer()
    groups = ["비겁", "식상", "재성", "관성", "인성"]
    pairs = {f"{a}+{b}" for a in groups for b in groups}
    assert set(layer["month_tone"]) == pairs == set(layer["day_scene"])
    assert all(len(v) == L._VARIANTS for v in layer["day_scene"].values())
    assert len(layer["month_action"]) == 10
    assert set(layer["next_month"]) == set(layer["next_year"]) == set(groups)
    assert len(layer["season_band"]) == 12
    assert len(layer["ilju_stage"]) == 12
    for key in ("stem_hap", "own_pillar", "flow_relief", "flow_defer"):
        assert len(layer[key]) == L._VARIANTS


def test_layer_sentences_pass_text_policy() -> None:
    sentences = _sentences(_layer())
    assert len(sentences) == len(set(sentences))
    for sentence in sentences:
        assert sentence.endswith((".", "!", "?")), sentence
        assert not re.search(r"[一-鿿]", sentence), sentence
        assert not any(word in sentence for word in polish._FORBIDDEN), sentence


def test_decision_unchanged_by_new_layer(board: DailyFortuneBoard) -> None:
    plain = _board(_GIHAE, _without_new_keys())
    assert board.top5 == plain.top5
    for new, old in zip(board.fortunes, plain.fortunes, strict=True):
        assert new.headline_event_key == old.headline_event_key
        assert new.events == old.events
        assert new.lucky_place == old.lucky_place
        assert new.lotto_phrase == old.lotto_phrase
        assert (new.love_line is None) == (old.love_line is None)


def test_past_contract_has_no_new_fields() -> None:
    past = _board(HEADLINE_CLOSING_REMOVAL_EFFECTIVE_FROM - dt.timedelta(days=1))
    assert past.month_flow is None and past.season_band is None
    assert all(f.advice is None for f in past.fortunes)


def test_board_carries_layer(board: DailyFortuneBoard) -> None:
    assert board.month_flow is not None and len(board.month_flow) == 10
    assert all(f.advice for f in board.fortunes)


def test_threads_export_excludes_layer(board: DailyFortuneBoard) -> None:
    """SNS 파일에는 오늘 내용만 — 이번 달 흐름과 조언을 싣지 않는다(데굴님 지시)."""
    text = render_threads_text(board)
    assert board.month_flow is not None
    assert all(flow.common not in text for flow in board.month_flow)
    assert all(f.advice not in text for f in board.fortunes)


def test_headline_uses_event_pool_and_respects_exclusions() -> None:
    tpl = M.load_daily_dicts_for(_FIRST).templates
    for offset in range(14):
        for fortune in _board(_FIRST + dt.timedelta(days=offset)).fortunes:
            event = tpl["events"][fortune.headline_event_key]
            if event.get("families"):
                continue  # 서사 family 는 자기 문장 쌍을 쓴다
            sipseong = {s for pool in event["sipseong_actions"].values() for s in pool}
            for fragment, banned in (event.get("action_exclude") or {}).items():
                if fortune.headline.startswith(fragment):
                    assert not any(fortune.headline.endswith(a) for a in banned)
            if not any(fortune.headline.endswith(a) for a in event["actions"]):
                # 사건 풀에 없으면 중복 회피로 합류한 그 사건의 십성 풀뿐이다
                assert any(fortune.headline.endswith(a) for a in sipseong), fortune.headline


def test_exclusions_reference_real_sentences() -> None:
    tpl = M.load_daily_dicts_for(_FIRST).templates
    for key, event in tpl["events"].items():
        for fragment, banned in (event.get("action_exclude") or {}).items():
            assert fragment in event["fragments"], key
            assert set(banned) <= set(event["actions"]), key
            assert set(event["actions"]) - set(banned), key  # 전부 빼면 안 된다


def test_board_headlines_stay_unique() -> None:
    for offset in range(14):
        fortunes = _board(_FIRST + dt.timedelta(days=offset)).fortunes
        assert len({f.headline for f in fortunes}) == 60


def test_every_ilju_has_a_note_and_stem_tab_is_all_distinct() -> None:
    """일주별 흐름이 빈 일주가 없어야 한다(데굴님 지적) — 12개월 전부."""
    layer = _layer()
    for month in range(12):
        d = dt.date(2026 + (10 + month) // 12, (10 + month) % 12 + 1, 20)
        flows = L.month_flow(M.build_day_context(d), layer)
        assert len(flows) == 10
        for flow in flows:
            assert len(flow.ilju_notes) == 6
            assert len({n.note for n in flow.ilju_notes}) == 6


def test_relation_sentence_follows_stage_sentence() -> None:
    layer = _layer()
    ctx = M.build_day_context(_GIHAE)  # 월운 간지 己亥, 내년 세운 지지 未
    note = L._ilju_note
    assert note(Branch("巳"), ctx, layer).endswith(layer["ilju_note"]["month_chung"])
    assert note(Branch("寅"), ctx, layer).endswith(layer["ilju_note"]["month_yukhap"])
    assert note(Branch("卯"), ctx, layer).endswith(layer["ilju_note"]["month_samhap"])
    assert note(Branch("丑"), ctx, layer).endswith(layer["ilju_note"]["year_chung"])
    assert note(Branch("午"), ctx, layer).endswith(layer["ilju_note"]["year_yukhap"])
    # 일지 子 는 亥·未 어느 쪽과도 충·합이 없어 12운성 문장만 남는다
    assert note(Branch("子"), ctx, layer) in layer["ilju_stage"].values()
    spring = M.build_day_context(dt.date(2027, 3, 20))  # 연말 구간 아님
    year_notes = [v for k, v in layer["ilju_note"].items() if k.startswith("year_")]
    assert not any(y in note(b, spring, layer) for b in Branch for y in year_notes)


def test_v116_board_keeps_relation_only_notes() -> None:
    """11/2 보드는 이미 export 됐다 — 재생성돼도 그날 계약의 문장이어야 한다."""
    assert M.load_daily_dicts_for(_LAST_V116).templates["version"] == "dict.v1.16"
    board = _board(_LAST_V116)
    assert board.month_flow is not None
    assert all(len(flow.ilju_notes) < 6 for flow in board.month_flow)


def test_next_year_lines_stay_anchored_to_this_month() -> None:
    """이번 달 패널인데 내년 얘기로만 끝나면 안 된다(데굴님 지적)."""
    assert all("이번 달" in s for s in _layer()["next_year"].values())


def test_common_line_joins_next_month_or_year_end() -> None:
    layer = _layer()
    winter = L._stem_common_line(Stem("壬"), M.build_day_context(_GIHAE), layer)
    assert layer["next_year"]["재성"] in winter  # 내년 丁 = 壬 의 재성
    assert not any(s in winter for s in layer["next_month"].values())
    spring = L._stem_common_line(Stem("壬"), M.build_day_context(dt.date(2027, 3, 20)), layer)
    assert any(s in spring for s in layer["next_month"].values())
    assert not any(s in spring for s in layer["next_year"].values())


def test_year_overlap_fires_only_on_matching_group() -> None:
    layer = _layer()
    november = M.build_day_context(dt.date(2026, 11, 20))
    june = M.build_day_context(dt.date(2026, 6, 20))  # 월운 지지 午 = 세운 천간 丙 과 같은 火
    assert layer["year_overlap"] not in L._stem_common_line(Stem("甲"), november, layer)
    assert layer["year_overlap"] in L._stem_common_line(Stem("甲"), june, layer)


def test_season_band_only_on_jeol_days() -> None:
    layer = _layer()
    assert "입동" in (L.season_band(M.build_day_context(dt.date(2026, 11, 7)), layer) or "")
    assert L.season_band(M.build_day_context(dt.date(2026, 11, 22)), layer) is None  # 소설
    assert L.season_band(M.build_day_context(_GIHAE), layer) is None


def test_advice_priority_and_flow() -> None:
    layer = _layer()
    ctx = M.build_day_context(_GIHAE)  # 일진 丙戌
    def line(stem: str, branch: str, y: str | None, b: str, t: str | None) -> str:
        return L.day_advice(Stem(stem), Branch(branch), ctx, layer, y, b, t)

    assert line("丙", "戌", None, "s5", None) in layer["own_pillar"]
    assert line("辛", "亥", None, "s5", None) in layer["stem_hap"]  # 丙辛합
    relief = line("甲", "子", "s1", "s5", "s5")
    assert any(relief.endswith(s) for s in layer["flow_relief"])
    defer = line("甲", "子", "s5", "s1", "s4")
    assert any(defer.endswith(s) for s in layer["flow_defer"])
    plain = line("甲", "子", "s5", "s5", "s1")
    assert not any(plain.endswith(s) for s in layer["flow_relief"] + layer["flow_defer"])


def test_same_stem_tab_is_not_one_repeated_line() -> None:
    fortunes = _board(_GIHAE + dt.timedelta(days=1)).fortunes
    by_stem: dict[str, set[str]] = {}
    for fortune in fortunes:
        by_stem.setdefault(fortune.day_stem_ko, set()).add(fortune.advice or "")
    assert min(len(v) for v in by_stem.values()) >= 3


def test_polish_keeps_layer_fields(board: DailyFortuneBoard) -> None:
    response = "\n".join(
        json.dumps({
            "ilju": f.ilju, "headline": f.headline,
            "place_phrase": f.lucky_place.phrase, "lotto": f.lotto_phrase,
        }, ensure_ascii=False)
        for f in board.fortunes
    )
    updated, _audit = polish.validate_and_apply(board, response)
    assert updated.month_flow == board.month_flow
    assert [f.advice for f in updated.fortunes] == [f.advice for f in board.fortunes]
    assert "advice" not in polish.build_polish_payload(board)
