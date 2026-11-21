"""올해 흐름 × 이번 달 연결 문장 검증 (docs/17 §34, dict.v1.22, 2026-11-18).

데굴님 "대운·세운·월운은 떼서 생각해서는 안 돼 — 역할별 영향" → "오늘의 운세쪽의 세운, 월운에도
적용". 이번 달 흐름 공통 줄에서, 세운 겹침이 없는 달에는 올해(세운 천간 십성군)가 깔아 둔 흐름
위에서 이번 달(월운 천간 십성군)이 하는 일을 한 문장으로 잇는다. 사전 커버리지·텍스트 정책·발화
조건·버전 경계·과거 계약 불변·판정 불변을 지킨다.
"""

from __future__ import annotations

import datetime as dt
import re

from saju_api.services import daily_fortune_polish as polish
from saju_engines import daily_ilju_fortune as M
from saju_engines import daily_month_layer as L
from saju_engines.daily_fortune_v2 import compute_board_v2
from saju_shared_types.daily_fortune import (
    DICT_VERSION,
    DICT_VERSION_BEFORE_YEAR_LINK,
    YEAR_LINK_EFFECTIVE_FROM,
    DailyFortuneBoard,
    active_dict_version,
)
from saju_shared_types.enums import Stem

_FROM = YEAR_LINK_EFFECTIVE_FROM  # 2026-11-19 — 丙午년 己亥월
_BEFORE = _FROM - dt.timedelta(days=1)
_GROUPS = ("비겁", "식상", "재성", "관성", "인성")
_HANJA = re.compile(r"[一-鿿]")
_DIGITS = re.compile(r"[0-9]")


def _layers(d: dt.date) -> tuple[dict, dict]:
    t = M.load_daily_dicts_for(d).templates
    return t["month_layer"], t["simple_layer"]


def _board(d: dt.date) -> DailyFortuneBoard:
    return compute_board_v2(M.build_day_context(d), M.load_daily_dicts_for(d))


def test_version_boundary() -> None:
    assert DICT_VERSION == "dict.v1.24"  # 11/23 부터(§37) — 이 파일은 v1.22 계약(11/19)
    assert DICT_VERSION_BEFORE_YEAR_LINK == "dict.v1.21"
    assert active_dict_version(_FROM) == "dict.v1.22"
    assert active_dict_version(_BEFORE) == "dict.v1.21"


def test_link_table_covers_all_ordered_pairs() -> None:
    link = _layers(_FROM)[0]["year_link"]
    expected = {f"{y}>{m}" for y in _GROUPS for m in _GROUPS if y != m}
    assert set(link) == expected  # 20쌍 — 같은 군은 기존 '세운 겹침' 문장이 맡는다
    assert len(set(link.values())) == 20  # 쌍마다 다른 문장


def test_link_text_policy() -> None:
    for key, sentence in _layers(_FROM)[0]["year_link"].items():
        assert not any(word in sentence for word in polish._FORBIDDEN), (key, sentence)
        assert not _HANJA.search(sentence) and not _DIGITS.search(sentence), (key, sentence)
        assert sentence.endswith("요.") and sentence.count(".") == 1, (key, sentence)  # 한 문장
        assert "올해" in sentence and "이번 달" in sentence, (key, sentence)  # 두 층을 함께 말한다


def test_previous_snapshot_has_no_link_table() -> None:
    assert "year_link" not in _layers(_BEFORE)[0]


def test_link_fires_only_without_overlap() -> None:
    layer, simple = _layers(_FROM)
    ctx = M.build_day_context(_FROM)  # 세운 丙午, 월운 己亥
    links = set(layer["year_link"].values())
    # 己 일간: 올해 丙=인성, 이번 달 己=비겁·亥=재성 → 겹침 없음 → 연결 문장(인성>비겁).
    gi = L._stem_common_line(Stem("己"), ctx, layer, simple)
    assert layer["year_link"]["인성>비겁"] in gi and layer["year_overlap"] not in gi
    # 甲 일간: 올해 丙=식상, 이번 달 己=재성·亥=인성 → 연결 문장(식상>재성).
    gap = L._stem_common_line(Stem("甲"), ctx, layer, simple)
    assert layer["year_link"]["식상>재성"] in gap
    # 겹치는 달(월운 지지 午 = 세운 천간 丙 과 같은 군)에는 기존 겹침 문장만 — 연결 문장 없음.
    june = L._stem_common_line(Stem("甲"), M.build_day_context(dt.date(2027, 6, 20)), layer, simple)
    year_group_same = layer["year_overlap"] in june
    assert year_group_same == (not any(s in june for s in links))
    # 열 일간 모두 겹침·연결 중 정확히 하나만 나온다.
    for stem in "甲乙丙丁戊己庚辛壬癸":
        line = L._stem_common_line(Stem(stem), ctx, layer, simple)
        assert (layer["year_overlap"] in line) + sum(s in line for s in links) == 1, stem


def test_board_from_boundary_carries_link_and_before_does_not() -> None:
    new, old = _board(_FROM), _board(_BEFORE)
    links = set(_layers(_FROM)[0]["year_link"].values())
    assert new.content_version.split("|")[1] == "dict.v1.22"
    assert old.content_version.split("|")[1] == "dict.v1.21"
    assert new.month_flow is not None and old.month_flow is not None
    assert all(
        sum(s in f.common for s in links) + (_layers(_FROM)[0]["year_overlap"] in f.common) == 1
        for f in new.month_flow
    )
    assert not any(s in f.common for f in old.month_flow for s in links)
    # 다음 달 미리보기도 같은 공통 줄 규칙을 탄다(있을 때만).
    for f in new.month_flow:
        if f.next_preview:
            assert sum(s in f.next_preview for s in links) <= 1


def test_link_does_not_change_judgment() -> None:
    """문체 전용 — 사건·확률·등수는 v1.21 사전으로 만든 보드와 같다."""
    ctx = M.build_day_context(_FROM)
    new = compute_board_v2(ctx, M.load_daily_dicts_for(_FROM))
    old = compute_board_v2(ctx, M.load_daily_dicts_for(_BEFORE))
    assert new.top5 == old.top5
    for a, b in zip(new.fortunes, old.fortunes, strict=True):
        assert a.headline_event_key == b.headline_event_key
        assert a.events == b.events
        assert a.lucky_place == b.lucky_place
        assert a.lotto_phrase == b.lotto_phrase
        assert a.advice == b.advice
