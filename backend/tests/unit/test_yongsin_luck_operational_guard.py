"""운세 해석 operational guard (Phase 5b-1) — 운 입자 오행에 원국 작동 역할 주석.

운 입자가 원국에서 조건부 희신/병·조후보조신·조건부 제살보조면 LLM 이 단순 희신/기신운으로
단정하지 않도록 guard. **explanation only** — favorability/event score/랭킹/final 불변.
규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §10
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from saju_manse_analysis import analyze_chart

from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import (
    build_luck_grounding,
    incoming_ten_god_note,
    natal_operational_role_map,
)
from saju_engines.event_scoring import favorability_map
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.enums import Branch, Stem

_STD_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1977-12-16", birth_time="05:30",
    birth_place_name="서울", gender="male", reference_date="2026-06-11",
)
# 희신 과다 교정(2026-07-12) 후 final: 희신=火·한신=水 — fav 미러도 동일하게 갱신.
_FAV = {"水": "한신", "火": "희신", "木": "용신", "金": "기신", "土": "구신"}


def _std_opmap(make_pillars) -> dict[str, str]:
    ya = analyze_chart(make_pillars(
        (Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG,
    )).yongsin
    return natal_operational_role_map(SimpleNamespace(yongsin_analysis=ya))


def test_natal_operational_role_map(make_pillars) -> None:
    m = _std_opmap(make_pillars)
    assert m["水"] == "조건부 한신/병" and m["火"] == "조후보조신"
    assert m["土"] == "조건부 제살보조" and m["木"] == "용신"
    # fallback: operational_roles 없으면 빈 dict.
    assert natal_operational_role_map(SimpleNamespace(yongsin_analysis=None)) == {}


def test_water_luck_conditional_guard(make_pillars) -> None:
    note = incoming_ten_god_note("丁", "壬子", _FAV, _std_opmap(make_pillars))
    assert note.count("원국 작동: 조건부 한신/병") == 2          # 천간·지지 인라인 태그
    assert "길운 판정 금지" in note
    assert note.count("※ 운 水:") == 1                          # 오행별 suffix 1회(dedupe)


def test_none_map_keeps_legacy_behavior(make_pillars) -> None:
    legacy = incoming_ten_god_note("丁", "壬子", _FAV, None)
    assert "원국 작동" not in legacy and "※" not in legacy
    assert "(水 한신)" in legacy  # 기존 canonical 태그 그대로


def test_johu_support_luck_positive_guard(make_pillars) -> None:
    note = incoming_ten_god_note("丁", "丙午", _FAV, _std_opmap(make_pillars))
    assert "원국 작동: 조후보조신" in note
    assert "기후·균형 보조로 작동" in note      # 긍정 보조 문맥(≠조건부 병 문구)
    assert "길운 판정 금지" not in note


def test_build_luck_grounding_surfaces_guard() -> None:
    result = calculate(_STD_BIRTH)
    luck = SimpleNamespace(
        ganji="壬子", twelve_unseong="", relations_to_chart=[], yongsin_alignment="",
    )
    g = build_luck_grounding(result, luck)
    assert "원국 작동: 조건부 한신/병" in g["pillar_line"]


def test_explanation_only_invariance() -> None:
    # favorability_map(=final canonical) 불변 — operational guard 는 설명 태그일 뿐.
    fav = favorability_map(calculate(_STD_BIRTH))
    assert fav.get("水") == "한신" and fav.get("火") == "희신"  # 희신 과다 교정 반영


def test_period_prompt_has_luck_directive() -> None:
    import saju_api.services.chat_service as chat_service

    res = chat_service.chat(_STD_BIRTH, "올해 운 어때?", date(2026, 6, 11), dry_run=True)
    pv = res.prompt_preview or ""
    assert "운에서 들어오는 오행" in pv  # _OPERATIONAL_INSTRUCTION 운 입자 지침
