"""구조 패턴 F6(2026-09-17 용어 감사) — 신규 63종·별칭 14건 감지·표기 검증.

설계: doc/v2_2/STRUCTURE_TERMS_AUDIT_2026-09-17.md §2,
      doc/v2_2/docs/13_STRUCTURE_PATTERNS.md §10 F6.
회귀 픽스처 5차트(tests/fixtures/structure_patterns_cases.jsonl)에서 실제로 성립하는
항목으로 감지 조건을 고정하고, 별칭은 llm_line 병기 규칙을 검증한다(inert — 점수 불변).
"""

from __future__ import annotations

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.dictionaries import _lint_structure_patterns
from saju_engines.structure_patterns import detect_structure_patterns, load_structure_patterns
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.structure_patterns import DetectedPattern

_F6_IDS = {
    "HWATO_SEONGJA", "TOGEUM_YUKSU", "GEUMBAEK_SUCHEONG", "SUMOK_CHEONGHWA",
    "GEUMMOK_DONGRYANG", "MOKTO_SOTONG", "TOSU_JISO", "HWAGEUM_JUIN",
    "MOKDA_HWASIK", "HWADA_TOCHO", "GEUMDA_SUTAK", "MOKDA_SUCHUK", "HWADA_MOKBUN",
    "TODA_HWAHOE", "GEUMDA_TOBYEON", "SUDA_GEUMCHIM", "MOKGYEON_GEUMGYEOL",
    "TOJUNG_MOKJEOL", "SUDA_TORYU", "HWAYEOM_SUYEOL", "GEUMDA_HWASIK",
    "HANMOK_HYANGYANG", "GEUMHAN_SURAENG", "HWAYEOM_TOJO", "CHEONHAN_JIDONG",
    "DEUNGRA_GYEGAP", "BYEOKGAP_INJEONG", "JEONGHWA_YEONGEUM", "BYEONGHWA_TALGWANG",
    "GAPMOK_SOTO", "MUTO_JESU", "SUTANG_GIHO", "HWACHI_SEUNGRYONG",
    "JAEGWANIN_SANGSAENG", "SIKSANG_SEOLSU", "GWANSAL_JEGEOP", "JAEJA_YAKSAL",
    "JAEJE_HYOIN", "INDA_YONGJAE", "GEOSAL_YUGWAN", "GEOGWAN_YUSAL",
    "SINSAL_YANGJEONG", "JAEDA_SAENGSAL", "INWANG_SINWANG", "SINWANG_MUUI",
    "SALJUNG_JEGYEONG", "GISIK_CHWIIN", "SEOLGI_TAEGWA", "GISIN_HAPGEO",
    "TAMHAP_MANGGEUK", "JAPGI_INSU_GYEOK", "HWATO_GYEOK", "HWAGEUM_GYEOK",
    "HWASU_GYEOK", "HWAMOK_GYEOK", "HWAHWA_GYEOK", "ILROK_GWISI", "SISANG_PYEONJAE",
    "CHEONWON_ILGI", "SEONGJUNG_YUPAE", "PAEJUNG_YUSEONG", "YONGSIN_YURYEOK",
    "YONGSIN_MURYEOK",
}


def _chart(date: str, time: str, place: str = "서울", gender: str = "male"):
    return calculate(BirthInput(
        birth_date=date, birth_time=time, birth_place_name=place, gender=gender,
    ))


def _ids(result) -> set[str]:
    return {d.pattern_id for d in detect_structure_patterns(result)}


# ── 사전 ────────────────────────────────────────────────────────────────

def test_f6_ids_all_registered() -> None:
    dic = load_structure_patterns()
    ids = {p.pattern_id for p in dic.patterns}
    assert len(_F6_IDS) == 63
    assert _F6_IDS <= ids


def test_aliases_registered_and_lint_clean() -> None:
    dic = load_structure_patterns()
    by = {p.pattern_id: p for p in dic.patterns}
    assert "효신탈식(梟神奪食)" in by["PYEONIN_DOSIK"].aliases
    assert "비겁쟁재(比劫爭財)" in by["GUNGEOP_JAENGJAE"].aliases
    assert "양인가살(羊刃駕殺)" in by["YANGIN_HAPSAL"].aliases
    assert sum(1 for p in dic.patterns if p.aliases) == 19, "기존 13 + 신규 6"
    assert _lint_structure_patterns(dic) == []


def test_llm_line_appends_aliases_only_when_present() -> None:
    base = dict(pattern_id="X", name_ko="x", strength=0.5, polarity_mode="context_only",
                llm_tag="태그")
    assert DetectedPattern(**base).llm_line == "태그"
    assert DetectedPattern(**base, aliases=["a", "b"]).llm_line == "태그 [별칭: a·b]"


# ── 감지(회귀 픽스처 차트 기반 결정적 사례) ─────────────────────────────

@pytest.fixture(scope="module")
def chart_1980_01_20():
    return _chart("1980-01-20", "10:00")


def test_saljung_jegyeong_and_paejung_yuseong(chart_1980_01_20) -> None:
    """壬 극신약 · 관살 4 · 제화 1 → 살중제경. 격국 등급 failure_with_rescue → 패중유성."""
    ids = _ids(chart_1980_01_20)
    ev = chart_1980_01_20.geokguk.evaluation
    assert ev is not None and ev.success_failure_grade == "failure_with_rescue"
    assert {"SALJUNG_JEGYEONG", "PAEJUNG_YUSEONG"} <= ids
    assert "SEONGJUNG_YUPAE" not in ids, "성중유패와 패중유성은 상호 배타"


def test_japgi_insu_geok_month_storage(chart_1980_01_20) -> None:
    """월지 丑(사고) 지장간 인성 → 잡기인수격(미투간 강도 0.4)."""
    det = {d.pattern_id: d for d in detect_structure_patterns(chart_1980_01_20)}
    assert chart_1980_01_20.pillars.month.branch in {"辰", "戌", "丑", "未"}
    assert det["JAPGI_INSU_GYEOK"].strength == 0.4


def test_harmony_requires_non_weak_day_master(chart_1980_01_20) -> None:
    """壬 극신약 + 木 존재 — 약한 일간의 生은 설기이므로 수목청화 불성립."""
    assert chart_1980_01_20.force_analysis.strength.band == "극신약"
    assert "SUMOK_CHEONGHWA" not in _ids(chart_1980_01_20)


def test_jeonghwa_yeongeum_without_byeokgap() -> None:
    """庚丁己戊: 丁·庚 천간 → 정화련금, 甲 부재 → 벽갑인정 아님. 己 신약 → 토금육수 아님."""
    r = _chart("1980-11-22", "09:08")
    ids = _ids(r)
    assert "JEONGHWA_YEONGEUM" in ids
    assert "BYEOKGAP_INJEONG" not in ids
    assert "TOGEUM_YUKSU" not in ids


def test_sinwang_muui_strong_without_outlet() -> None:
    """甲 신강 · 식상+재성+관살 통로 15% 이하 → 신왕무의."""
    r = _chart("1975-07-07", "22:00", place="부산")
    assert r.force_analysis.strength.band in {"신강", "태신강", "극신강"}
    assert "SINWANG_MUUI" in _ids(r)


def test_gisik_chwiin_uses_selected_model() -> None:
    """식신 존재 + 용신 선택 모델이 인성 계열 → 기식취인(점수·모델 불변, 라벨만)."""
    r = _chart("1990-03-15", "14:30")
    assert r.yongsin_analysis.final.get("selected_model") == "resource_as_yongsin"
    assert "GISIK_CHWIIN" in _ids(r)


def test_f6_patterns_are_inert(chart_1980_01_20) -> None:
    for d in detect_structure_patterns(chart_1980_01_20):
        if d.pattern_id in _F6_IDS:
            assert d.favorability is None
            assert 0.0 < d.strength <= 0.6
