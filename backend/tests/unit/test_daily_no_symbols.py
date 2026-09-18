"""오늘의 운세 풀이 이모지·특수기호 금지 (2026-09-10 데굴님 지시, docs/17 §6).

세 지점(사전 원본 / LLM 교정 출력 / 서비스 응답·export)에서 같은 정책이 걸리는지 고정한다.
엔진 렌더·캐시는 바이트 불변이어야 하므로 정리는 복사본에서만 일어난다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from saju_api.services import daily_fortune_polish as polish
from saju_api.services import daily_fortune_service as svc
from saju_api.services.daily_fortune_export import render_threads_text
from saju_engines.daily_fortune_cache import InMemoryDailyFortuneCache
from saju_engines.daily_ilju_fortune import build_day_context, compute_board, load_daily_dicts_for
from saju_engines.daily_text_policy import has_symbols, sanitize_board, strip_symbols
from saju_shared_types.daily_fortune import CATALOG_EXPANSION_EFFECTIVE_FROM

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries" / "daily_fortune"
_D = CATALOG_EXPANSION_EFFECTIVE_FROM


def test_strip_symbols_rules() -> None:
    assert strip_symbols("잘 풀려요♪") == "잘 풀려요."
    assert strip_symbols("이어질지도♥") == "이어질지도."
    assert strip_symbols("이미 마침표.♪") == "이미 마침표."
    assert strip_symbols("기분 좋은 날! ♪ 산책") == "기분 좋은 날! 산책"
    assert strip_symbols("★행운★ 하루 → 좋아요 ✨") == "행운. 하루 좋아요"
    assert strip_symbols("🍀 오늘도 가볍게") == "오늘도 가볍게"
    plain = "가운뎃점·물결~ 느낌표! 물음표? 그대로."
    assert strip_symbols(plain) is plain  # 기호 없으면 바이트 불변(같은 객체)
    assert not has_symbols(plain) and has_symbols("♪")


def _walk(x, out: list[str]) -> None:
    if isinstance(x, dict):
        for v in x.values():
            _walk(v, out)
    elif isinstance(x, list):
        for v in x:
            _walk(v, out)
    elif isinstance(x, str):
        out.append(x)


@pytest.mark.parametrize("name", ["daily_phrase_templates.json", "daily_lucky_places.json"])
def test_dictionary_texts_have_no_symbols(name: str) -> None:
    texts: list[str] = []
    _walk(json.loads((_DICTS / name).read_text("utf-8")), texts)
    bad = [t for t in texts if has_symbols(t)]
    assert not bad, bad[:5]


@pytest.fixture(scope="module")
def board():
    return compute_board(build_day_context(_D), load_daily_dicts_for(_D))


def test_engine_board_has_no_symbols_and_sanitize_is_identity(board) -> None:
    for f in board.fortunes:
        for text in (f.headline, f.love_line or "", f.lotto_phrase or "", f.lucky_place.phrase):
            assert not has_symbols(text), text
    assert sanitize_board(board) is board  # 기호 없으면 원본 그대로


def test_get_board_sanitizes_cached_legacy_board(board, monkeypatch) -> None:
    """과거 계약 보드(♪ 포함)가 캐시에 있어도 응답은 정리된 복사본, 캐시는 불변."""
    monkeypatch.setattr(svc, "beta_registry", lambda: None)
    dirty = board.model_copy(deep=True)
    dirty.fortunes[0].headline = dirty.fortunes[0].headline + "♪"
    dirty.fortunes[1].lucky_place.phrase = "★" + dirty.fortunes[1].lucky_place.phrase
    cache = InMemoryDailyFortuneCache()
    version = svc._active_content_version(_D)
    cache.save_board(_D, version, dirty, 3600)
    served = svc.get_board(cache, _D)
    assert not has_symbols(served.fortunes[0].headline)
    assert not has_symbols(served.fortunes[1].lucky_place.phrase)
    assert served.fortunes[0].headline.endswith(".")
    cached = cache.load_board(_D, version)
    assert cached is not None and cached.fortunes[0].headline.endswith("♪")  # 캐시 불변
    # 스레드 export — 섹션 헤더 이모지(레이아웃)는 범위 밖, 풀이 문장의 기호만 걷힌다.
    text = render_threads_text(sanitize_board(dirty))
    assert "♪" not in text and "★" not in text


def test_polish_output_symbols_are_stripped_not_rejected(board) -> None:
    f = board.fortunes[0]
    line = json.dumps({
        "ilju": f.ilju, "headline": f.headline + "♪", "place_phrase": f.lucky_place.phrase + " ✨",
        "lotto": f.lotto_phrase,
    }, ensure_ascii=False)
    updated, audit = polish.validate_and_apply(board, line)
    assert f.ilju not in audit["reject_reasons"], audit["reject_reasons"]
    got = next(x for x in updated.fortunes if x.ilju == f.ilju)
    assert not has_symbols(got.headline) and not has_symbols(got.lucky_place.phrase)
    assert got.polished


def test_polish_prompt_forbids_symbols() -> None:
    assert "이모지" in polish._SYSTEM and "장식 기호" in polish._SYSTEM
