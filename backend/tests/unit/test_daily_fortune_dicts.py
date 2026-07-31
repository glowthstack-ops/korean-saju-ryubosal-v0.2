"""일주별 오늘의 운세 — 사전(JSON) 3종 스키마·콘텐츠 규칙 검증.

docs/17_DAILY_ILJU_FORTUNE.md 규격: 사건 카탈로그 28종(good 12/caution 10/support 6),
조합형 템플릿 최소 수량(fragment 3·action 3·result 2), 명리 용어·금지 표현 부재.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries" / "daily_fortune"

_DOMAINS = {"money", "love", "work", "social", "news", "document", "move", "health", "leisure"}
_RELATION_KEYS = {
    "six_combination", "half_harmony", "three_harmony_complete",
    "clash", "punishment", "break", "harm",
}
_TEN_GODS = {"비견", "겁재", "식신", "상관", "편재", "정재", "편관", "정관", "편인", "정인"}
_ELEMENTS = {"木", "火", "土", "金", "水"}

# 사용자 노출 문장에 나타나면 안 되는 명리 용어 (PRD §3 — 계산 근거 비노출).
# "합"/"파" 단독, "일지"("~일지도"), "일간"(일간 재방문)은 일반어와 겹쳐 제외하고
# 술어형 전문 용어만 차단한다.
_FORBIDDEN_TERMS = [
    "비견", "겁재", "식신", "상관", "편재", "정재", "편관", "정관", "편인", "정인",
    "지장간", "세운", "월운", "대운", "용신", "기신",
    "삼합", "육합", "반합", "형살", "원진", "명리", "오행", "십성", "간지",
]
# 로또 문구 금지 표현 (PRD §12): 당첨 단정·금액·연속 권유.
_LOTTO_FORBIDDEN = ["당첨", "무조건", "반드시", "확실", "매일", "원씩", "만원", "대출", "빚"]


def _load(name: str) -> dict[str, Any]:
    return json.loads((_DICTS / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def catalog() -> dict[str, Any]:
    return _load("daily_event_catalog.json")


@pytest.fixture(scope="module")
def templates() -> dict[str, Any]:
    return _load("daily_phrase_templates.json")


@pytest.fixture(scope="module")
def places() -> dict[str, Any]:
    return _load("daily_lucky_places.json")


def test_catalog_counts_and_schema(catalog: dict[str, Any]) -> None:
    events = catalog["events"]
    assert len(events) == 49  # 일일 연애운 확장(love 사건 +4: good 2·caution 2)
    by_valence = {"good": 0, "caution": 0}
    support_only = 0
    for key, ev in events.items():
        assert ev["domain"] in _DOMAINS, key
        assert ev["valence"] in ("good", "caution"), key
        assert set(ev["slots"]) <= {"good", "caution", "support"}, key
        assert 0 < ev["base_weight"] <= 1.0, key
        assert 0 < ev["expr_confidence"] <= 1.0, key
        assert set(ev["ten_god_affinity"]) <= _TEN_GODS, key
        assert set(ev["relation_affinity"]) <= _RELATION_KEYS, key
        assert set(ev["element_affinity"]) <= _ELEMENTS, key
        for table in ("ten_god_affinity", "relation_affinity", "element_affinity"):
            for v in ev[table].values():
                assert -1.0 <= v <= 1.0, f"{key}.{table}"
        by_valence[ev["valence"]] += 1
        if ev["slots"] == ["support"]:
            support_only += 1
    # good 12 + support 전용 6(모두 valence=good) = 18 → +love good 2 = 20,
    # caution 27 → +love caution 2 = 29(일일 연애운 확장).
    assert by_valence["caution"] == 29
    assert by_valence["good"] == 20
    assert support_only == 6


def test_caution_slots_are_caution_only(catalog: dict[str, Any]) -> None:
    for key, ev in catalog["events"].items():
        if ev["valence"] == "caution":
            assert ev["slots"] == ["caution"], key
        else:
            assert "caution" not in ev["slots"], key


def test_templates_cover_catalog_with_min_variants(
    catalog: dict[str, Any], templates: dict[str, Any]
) -> None:
    ev_templates = templates["events"]
    assert set(ev_templates) == set(catalog["events"]), "카탈로그와 템플릿 키 불일치"
    for key, tpl in ev_templates.items():
        assert len(tpl["fragments"]) >= 3, key
        assert len(tpl["actions"]) >= 3, key
        assert len(tpl["results"]) >= 2, key


def test_generic_fallbacks_exist(templates: dict[str, Any]) -> None:
    for slot in ("good", "caution", "support"):
        g = templates["generic"][slot]
        assert len(g["fragments"]) >= 3 and len(g["actions"]) >= 3 and len(g["results"]) >= 2


def test_place_phrases_have_placeholder(templates: dict[str, Any]) -> None:
    assert len(templates["place_phrases"]) >= 2
    for p in templates["place_phrases"]:
        assert "{place}" in p


def _all_user_facing_texts(catalog: dict[str, Any], templates: dict[str, Any]) -> list[str]:
    texts: list[str] = [ev["label"] for ev in catalog["events"].values()]
    for tpl in templates["events"].values():
        texts += tpl["fragments"] + tpl["actions"] + tpl["results"]
    for g in templates["generic"].values():
        texts += g["fragments"] + g["actions"] + g["results"]
    texts += templates["place_phrases"] + templates["lotto_phrases"]
    return texts


def test_no_forbidden_myeongri_terms(
    catalog: dict[str, Any], templates: dict[str, Any]
) -> None:
    for text in _all_user_facing_texts(catalog, templates):
        for term in _FORBIDDEN_TERMS:
            assert term not in text, f"명리 용어 노출: {term!r} in {text!r}"


def test_no_hanja_in_user_texts(catalog: dict[str, Any], templates: dict[str, Any]) -> None:
    hanja = re.compile(r"[一-鿿]")
    for text in _all_user_facing_texts(catalog, templates):
        assert not hanja.search(text), f"한자 노출: {text!r}"


def test_lotto_phrases_policy(templates: dict[str, Any]) -> None:
    phrases = templates["lotto_phrases"]
    assert len(phrases) >= 3
    for p in phrases:
        for bad in _LOTTO_FORBIDDEN:
            assert bad not in p, f"로또 금지 표현: {bad!r} in {p!r}"


def test_synonym_groups_consistent(catalog: dict[str, Any]) -> None:
    groups: dict[str, list[str]] = {}
    for key, ev in catalog["events"].items():
        g = ev.get("synonym_group")
        if g:
            groups.setdefault(g, []).append(key)
    for g, members in groups.items():
        assert len(members) >= 2, f"동의어 그룹 {g}는 2개 이상이어야 함"


def test_places_schema(places: dict[str, Any]) -> None:
    entries = places["places"]
    assert len(entries) == 40
    for key, pl in entries.items():
        assert pl["element"] in _ELEMENTS, key
        assert pl["name"], key
        assert set(pl["domains"]) <= _DOMAINS, key
    # 오행별 8개씩 고르게
    by_el: dict[str, int] = {}
    for pl in entries.values():
        by_el[pl["element"]] = by_el.get(pl["element"], 0) + 1
    assert all(v == 8 for v in by_el.values()), by_el


# ── 스레드 업로드용 export(2026-07-23) — 최상단 날짜·고정 파일명·원자 교체 ──

def test_threads_export_writes_date_header(tmp_path) -> None:
    from datetime import date as _date

    from saju_api.services.daily_fortune_export import (
        render_threads_text,
        write_threads_export,
    )
    from saju_api.services.daily_fortune_service import _generate

    board = _generate(_date(2026, 7, 23))
    text = render_threads_text(board)
    first = text.splitlines()[0]
    assert "2026-07-23" in first and "오늘의 운세" in first  # 대상 날짜 최상단
    assert text.count("일주") >= 60
    out = tmp_path / "오늘의운세.txt"
    # export 는 **오늘 보드일 때만** 쓴다(2026-08-01 사고 — 미래 보드가 파일을 덮었다).
    # 이 테스트의 관심사는 렌더 내용이므로 고정 날짜를 기준일로 함께 주입한다.
    assert write_threads_export(board, out, today=_date(2026, 7, 23)) is True
    assert out.read_text(encoding="utf-8").startswith("[오늘의 운세 — 2026-07-23")
