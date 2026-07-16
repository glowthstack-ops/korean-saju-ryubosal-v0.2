"""배우자궁(일지) 성향 보조 발췌 — spouse_palace_tendency 사전·배선 검증.

4인자(子亥巳午)+계절(봄여름/가을겨울) 레이어, 마킹(성향 묘사 보조 전용), 단정 표현 부재,
12지지 전수 커버, chat 프롬프트 [명식 해석 자료] 블록 유입. 점수·판정 미개입(순수 텍스트).
출처: 상담가 강의 경험칙(reviewed:false) — 2026-07-07 데굴님 승인(1·2번 항목만, 명의 규칙 제외).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from saju_api.services import chat_service
from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import (
    _spouse_palace_excerpts,
    build_chart_interpretation,
)
from saju_shared_types.birth_input import BirthInput

_DICT = (Path(__file__).resolve().parents[2] / "dictionaries" / "interpretations"
         / "spouse_palace_tendency.json")
_DATA = json.loads(_DICT.read_text(encoding="utf-8"))
_BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
_MARKER = "성향 묘사에만 보조 인용"


# ── 사전 규격: reviewed:false·4인자 4개·계절 12지 전수 분할 ──
def test_dictionary_shape() -> None:
    assert _DATA["reviewed"] is False  # 감수 전 초안 강제
    assert sorted(_DATA["four_factor"]["branches"]) == sorted(["子", "亥", "巳", "午"])
    season_union = [b for s in _DATA["season"] for b in s["branches"]]
    assert sorted(season_union) == sorted(_BRANCHES)  # 중복 없이 12지 전수


# ── 단정 표현 금지(절대 원칙 3) — 경향 톤만 ──
def test_no_assertive_wording() -> None:
    texts = [_DATA["four_factor"]["text"]] + [s["text"] for s in _DATA["season"]]
    for t in texts:
        assert not any(w in t for w in ("반드시", "무조건", "확실", "100%", "된다."))
        assert "경험칙" in t  # 출처 성격 명시


# ── 4인자 지지 → 4인자+계절 2건, 그 외 → 계절 1건 ──
def test_four_factor_branch_two_excerpts() -> None:
    for b, season_label in (("子", "가을·겨울"), ("亥", "가을·겨울"),
                            ("巳", "봄·여름"), ("午", "봄·여름")):
        ex = _spouse_palace_excerpts(b)
        assert [e.kind for e in ex] == ["spouse_palace_tendency"] * 2
        assert "4인자" in ex[0].key and season_label in ex[1].key


def test_non_four_factor_branch_one_excerpt() -> None:
    for b in ("寅", "卯", "辰", "未"):
        ex = _spouse_palace_excerpts(b)
        assert len(ex) == 1 and "봄·여름" in ex[0].key
    for b in ("申", "酉", "戌", "丑"):
        ex = _spouse_palace_excerpts(b)
        assert len(ex) == 1 and "가을·겨울" in ex[0].key


# ── 모든 발췌에 보조 인용 마킹 부착 ──
def test_marker_attached_all() -> None:
    for b in _BRANCHES:
        assert all(_MARKER in e.text for e in _spouse_palace_excerpts(b))


# ── 통합: 명식 해석에 항상 ≥1건(계절 레이어는 12지 전수) + 일지 소속 일치 ──
def test_build_chart_interpretation_contains_excerpt() -> None:
    result = calculate(BirthInput(
        calendar_type="solar", birth_date="1977-12-16", birth_time="05:30",
        birth_place_name="Seoul", gender="male"))
    assert result.pillars is not None
    ci = build_chart_interpretation(result)
    assert ci is not None
    spouse = [e for e in ci.excerpts if e.kind == "spouse_palace_tendency"]
    assert spouse  # 계절 레이어가 모든 일지를 커버 — 항상 존재
    day_branch = result.pillars.day.branch
    expected = 2 if day_branch in _DATA["four_factor"]["branches"] else 1
    assert len(spouse) == expected


# ── chat 프롬프트 [명식 해석 자료] 블록 유입(성향 묘사 보조 자료로 노출) ──
def test_chat_prompt_exposure() -> None:
    birth = BirthInput(
        calendar_type="solar", birth_date="1977-12-16", birth_time="05:30",
        birth_place_name="Seoul", gender="male", reference_date="2026-06-11")
    preview = chat_service.chat(birth, "저는 어떤 사람인가요?", date(2026, 6, 11),
                                dry_run=True).prompt_preview or ""
    assert "배우자궁" in preview and _MARKER in preview
