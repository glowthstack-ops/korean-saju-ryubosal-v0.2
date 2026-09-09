"""docs/17 §23 — 표현 결(tone) 층 회귀 (2026-09-10 사용자 승인).

결 층은 **문체 전용**이다: 행동 문장은 오늘 천간의 십성군, 결과 문장은 오늘 천간이
일지에서 갖는 12운성 채널이 고른다. 사건 선발·점수는 건드리지 않고, 결 풀이 없는
사전(과거 계약 스냅샷)에서는 이전 조합과 바이트 단위로 같아야 한다.
"""

from __future__ import annotations

import datetime as dt

import pytest

from saju_engines import daily_ilju_fortune as M
from saju_engines.daily_fortune_v2 import compute_board_v2, load_catalog_v2
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index
from saju_shared_types.daily_fortune import (
    CATALOG_EXPANSION_EFFECTIVE_FROM,
    DayGanjiContext,
)
from saju_shared_types.enums import Branch, Stem

GROUPS = ("비겁", "식상", "재성", "관성", "인성")
CHANNELS = (
    "renewal", "activity_up", "overdrive", "stamina_down", "pace_down", "disengage",
    "closure",
)


@pytest.fixture(scope="module")
def dicts() -> M.DailyFortuneDicts:
    return M.load_daily_dicts()


def _ctx(day_stem: str, day_branch: str) -> DayGanjiContext:
    return DayGanjiContext(
        the_date=dt.date(2026, 9, 12), day_stem=day_stem, day_branch=day_branch,
        month_stem="丁", month_branch="酉", year_stem="丙", year_branch="午",
    )


# ── 1. 사전 커버리지 ──────────────────────────────────────────────────────────


def test_tone_pools_cover_every_v2_event(dicts) -> None:
    """64종 × 5군 ≥2문장, 7채널 × good/caution ≥3문장."""
    events = dicts.templates["events"]
    for key in load_catalog_v2().events:
        tone = events[key].get("tone_actions")
        assert tone and tuple(tone) == GROUPS, key
        for group, sents in tone.items():
            assert len(sents) >= 2, (key, group)
            assert all(s.strip() for s in sents), (key, group)
    stage = dicts.templates["stage_results"]
    assert tuple(stage) == CHANNELS
    for channel, pools in stage.items():
        for kind in ("good", "caution"):
            assert len(pools[kind]) >= 3, (channel, kind)


# ── 2. day_tone 정의·결정론 ──────────────────────────────────────────────────


def test_day_tone_matches_definition() -> None:
    """십성군 = 오늘 천간 → 일간 십성의 군, 채널 = 오늘 천간이 일지에서 갖는 12운성."""
    # 甲 일간에 己 천간 = 정재 → 재성군. 己 는 丑 에서 묘(墓) → closure.
    t = M.day_tone(Stem("甲"), Branch("丑"), _ctx("己", "丑"))
    assert t == M.DayTone(sipseong_group="재성", stage_channel="closure")
    # 같은 천간(甲→甲)은 비견 → 비겁군. 甲 은 寅 에서 건록 → activity_up.
    t = M.day_tone(Stem("甲"), Branch("寅"), _ctx("甲", "子"))
    assert t == M.DayTone(sipseong_group="비겁", stage_channel="activity_up")
    # 甲 은 卯 에서 제왕 → overdrive(과속), 申 에서 절 → disengage.
    assert M.day_tone(Stem("庚"), Branch("卯"), _ctx("甲", "子")).stage_channel == "overdrive"
    assert M.day_tone(Stem("庚"), Branch("申"), _ctx("甲", "子")).stage_channel == "disengage"


def test_day_tone_is_deterministic_and_covers_all_channels() -> None:
    seen: set[str] = set()
    ctx = _ctx("甲", "子")
    for idx in range(60):
        stem, branch = ganzi_from_index(idx)
        a, b = M.day_tone(stem, branch, ctx), M.day_tone(stem, branch, ctx)
        assert a == b
        assert a.sipseong_group in GROUPS and a.stage_channel in CHANNELS
        seen.add(a.stage_channel)
    assert seen == set(CHANNELS)


def test_same_stem_group_shares_sipseong_but_not_stage() -> None:
    """같은 일간 6일주는 십성군이 같고(구조), 12운성 채널은 갈린다(결 층의 존재 이유)."""
    ctx = _ctx("己", "丑")
    tones = [M.day_tone(Stem("甲"), Branch(b), ctx) for b in ("子", "寅", "辰", "午", "申", "戌")]
    assert len({t.sipseong_group for t in tones}) == 1
    assert len({t.stage_channel for t in tones}) >= 3


# ── 3. 렌더 규칙 ─────────────────────────────────────────────────────────────


def test_headline_is_byte_identical_without_tone_pools(dicts) -> None:
    """결 키가 없는 사전(과거 계약)에서는 tone 인자가 있어도 이전 조합 그대로다."""
    old = M.load_daily_dicts_for(CATALOG_EXPANSION_EFFECTIVE_FROM - dt.timedelta(days=1))
    assert "stage_results" not in old.templates
    tone = M.DayTone("재성", "closure")
    for band in ("s5", "s3", "s1"):
        for salt in (0, 3, 6):
            a = M._headline(old, "money_good_deal", band, "2026-09-11|甲子|x", salt)
            b = M._headline(
                old, "money_good_deal", band, "2026-09-11|甲子|x", salt, tone=tone
            )
            assert a == b


def test_headline_uses_tone_pools_when_active(dicts) -> None:
    """행동은 십성군 풀에서, 결과는 채널 풀에서 나오고 결과 문장은 항상 붙는다."""
    tpl = dicts.templates["events"]["money_good_deal"]
    for group in GROUPS:
        for channel in CHANNELS:
            tone = M.DayTone(group, channel)
            for band in ("s5", "s3", "s2"):
                text = M._headline(dicts, "money_good_deal", band, "seed|甲子", 0, tone=tone)
                parts = text.split(" ")
                # 행동 문장은 해당 십성군 풀의 것이어야 한다.
                assert any(a in text for a in tpl["tone_actions"][group]), (group, text)
                # 결과 문장은 해당 채널 good 풀의 것이어야 한다(s2 밴드에도 붙는다).
                pool = dicts.templates["stage_results"][channel]["good"]
                assert any(r in text for r in pool), (channel, text)
                assert len(parts) >= 3


def test_caution_headline_uses_caution_stage_pool(dicts) -> None:
    tone = M.DayTone("식상", "overdrive")
    text = M._headline(dicts, "argument_caution", "s1", "seed|乙丑", 0, tone=tone)
    pool = dicts.templates["stage_results"]["overdrive"]["caution"]
    assert any(r in text for r in pool), text


def test_different_sipseong_groups_give_different_actions(dicts) -> None:
    """같은 사건·같은 seed 라도 십성군이 다르면 행동 문장이 달라진다."""
    texts = {
        g: M._headline(dicts, "work_smooth", "s4", "seed|丙寅", 0, tone=M.DayTone(g, "renewal"))
        for g in GROUPS
    }
    actions = {t.split(" ")[1:3] and t for t in texts.values()}
    assert len(actions) == len(GROUPS), texts


# ── 4. 보드 수준 — 판정 불변 + 그룹 내 차별화 ────────────────────────────────


@pytest.fixture(scope="module")
def board_after():
    d = CATALOG_EXPANSION_EFFECTIVE_FROM
    return d, compute_board_v2(M.build_day_context(d), M.load_daily_dicts_for(d))


def test_tone_layer_does_not_change_selection(board_after) -> None:
    """결 층은 문체 전용 — 결 풀을 제거한 사전으로 만든 보드와 사건·확률이 같다."""
    d, board = board_after
    dicts = M.load_daily_dicts_for(d)
    stripped_templates = {
        k: v for k, v in dicts.templates.items() if k not in ("stage_results", "tone_layer")
    }
    stripped_templates["events"] = {
        key: {kk: vv for kk, vv in tpl.items() if kk != "tone_actions"}
        for key, tpl in dicts.templates["events"].items()
    }
    plain = compute_board_v2(
        M.build_day_context(d),
        M.DailyFortuneDicts(
            catalog=dicts.catalog, templates=stripped_templates, places=dicts.places
        ),
    )
    for a, b in zip(board.fortunes, plain.fortunes, strict=True):
        assert a.headline_event_key == b.headline_event_key
        assert [(e.event_key, e.probability) for e in a.events] == [
            (e.event_key, e.probability) for e in b.events
        ]
        assert a.lucky_place == b.lucky_place and a.lotto_phrase == b.lotto_phrase
    assert board.top5 == plain.top5


def test_shared_headline_event_in_stem_group_gets_distinct_results(board_after) -> None:
    """같은 일간 그룹에서 같은 헤드라인 사건을 받은 일주들은 채널이 다르면 결과 문장이 다르다."""
    d, board = board_after
    ctx = M.build_day_context(d)
    stage = M.load_daily_dicts_for(d).templates["stage_results"]
    checked = 0
    by_group: dict[tuple[str, str], list] = {}
    for f in board.fortunes:
        by_group.setdefault((f.ilju[0], f.headline_event_key), []).append(f)
    for (_stem, _key), rows in by_group.items():
        if len(rows) < 2:
            continue
        results_by_channel: dict[str, set[str]] = {}
        for f in rows:
            tone = M.day_tone(Stem(f.ilju[0]), Branch(f.ilju[1]), ctx)
            kind = "caution" if _band_of(f) == "s1" else "good"
            hit = [r for r in stage[tone.stage_channel][kind] if r in f.headline]
            assert hit, (f.ilju, f.headline)
            results_by_channel.setdefault(tone.stage_channel, set()).add(hit[0])
        if len(results_by_channel) >= 2:
            pools = list(results_by_channel.values())
            assert pools[0].isdisjoint(pools[1])
            checked += 1
    assert checked >= 1


def _band_of(fortune) -> str:
    """헤드라인이 caution 사건이면 s1(주의 우세) — 그 외는 good 밴드로 취급."""
    valence = load_catalog_v2().events[fortune.headline_event_key].valence
    return "s1" if valence == "caution" else "s4"


def test_headlines_have_three_sentences_when_tone_active(board_after) -> None:
    _d, board = board_after
    for f in board.fortunes:
        # 결 층 활성: fragment + action + result 3부. 각 부는 공백으로 이어 붙인다.
        assert len(f.headline) <= 120, f.ilju
        assert f.headline.count(" ") >= 2
