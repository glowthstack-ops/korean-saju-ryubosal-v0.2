"""작동 역할 LLM 노출 (Phase 5a) — compact summary adapter + 직렬화 + mapper guard.

원국 기준 요약을 chart_interpretation ⑤ 블록에 additive surface. 점수·이벤트·final 불변(scoring-0).
조건부 희신/병은 OPERATIONAL_ROLE_CLASS mapper=conditional(문자열 substring 파싱 금지).
규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §10
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import cast

from saju_manse_analysis import analyze_chart
from saju_manse_analysis.yongsin.operational_role_config import OPERATIONAL_ROLE_CLASS

from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import (
    _MAX_WARNINGS,
    _WARNINGS_CHAR_BUDGET,
    build_yongsin_operational_summary,
)
from saju_engines.context_reducer import serialize_chart_prefix
from saju_engines.event_scoring import favorability_map
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.llm_input import (
    BirthChartSummary,
    ChartInterpretation,
    UsefulGods,
)
from saju_shared_types.manse_result import ManseV2Result

# 표준사례 丁巳/壬子/丁未/癸卯 = 1977-12-16 05:30 서울(진태양시 경유 동일 명식).
_STD_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1977-12-16", birth_time="05:30",
    birth_place_name="서울", gender="male", reference_date="2026-06-11",
)


def _std_summary(make_pillars):
    ya = analyze_chart(make_pillars(
        (Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG,
    )).yongsin
    return build_yongsin_operational_summary(SimpleNamespace(yongsin_analysis=ya))


def test_summary_fields(make_pillars) -> None:
    s = _std_summary(make_pillars)
    assert s is not None
    assert s.primary_yongsin == "木"
    assert s.operability == 0.595 and s.operability_level == "낮음"
    assert s.operability_factors == ["no_transmit", "gyeokgak_zimao"]  # 내부 stable key
    assert s.operability_factors_ko == ["투간無", "子卯 격각"]  # 프리픽스용 한국어 압축
    assert s.main_support == ["火: 조후보조신"]
    assert any("水: 조건부 한신/병" in c for c in s.conditional)
    assert any("土: 조건부 제살보조" in c for c in s.conditional)


def test_mapper_guard_conditional_not_favorable(make_pillars) -> None:
    # 조건부 희신/병은 '희신' 문자열을 포함하지만 mapper 기준 conditional(≠favorable).
    assert OPERATIONAL_ROLE_CLASS["조건부 희신/병"] == "conditional"
    assert OPERATIONAL_ROLE_CLASS["희신"] == "favorable"
    s = _std_summary(make_pillars)
    # 水는 conditional 목록에만 — 단순 희신(favorable)으로 새지 않는다.
    assert any(c.startswith("水") for c in s.conditional)


def test_fallback_none(make_pillars) -> None:
    none_chart = cast("ManseV2Result", SimpleNamespace(yongsin_analysis=None))
    assert build_yongsin_operational_summary(none_chart) is None
    empty = cast("ManseV2Result", SimpleNamespace(
        yongsin_analysis=SimpleNamespace(operational_roles=[])))
    assert build_yongsin_operational_summary(empty) is None


def test_warnings_priority_and_budget(make_pillars) -> None:
    s = _std_summary(make_pillars)
    assert len(s.warnings) <= _MAX_WARNINGS
    assert sum(len(w) for w in s.warnings) <= _WARNINGS_CHAR_BUDGET
    # 우선순위 1번(조건부 병 경고 — 희신/한신 강등형 공통)이 맨 앞.
    assert "자동 길신 처리 금지" in s.warnings[0]


def test_serialize_block_and_token_budget(make_pillars) -> None:
    s = _std_summary(make_pillars)
    summary = BirthChartSummary(
        day_master="丁", pillars={"year": "丁巳", "month": "壬子", "day": "丁未", "hour": "癸卯"},
        useful_gods=UsefulGods(
            yongsin=["木"], heesin=["火"], gisin=["金"], gusin=["土"], hansin=["水"]),
        strength="신약",
    )
    base = serialize_chart_prefix(summary, ChartInterpretation())
    withop = serialize_chart_prefix(summary, ChartInterpretation(yongsin_operational_summary=s))
    text = "\n".join(withop)
    assert "[작동 역할" in text
    assert "水: 조건부 한신/병" in text and "火: 조후보조신" in text
    assert "작동성 낮음 0.595" in text
    # 프리픽스엔 한국어 압축 표현만, 내부 key(no_transmit 등)는 노출 안 됨.
    assert "투간無" in text and "子卯 격각" in text
    assert "no_transmit" not in text and "gyeokgak_zimao" not in text
    # token proxy: 추가 char 합리적 상한 이내(≈115 token).
    assert len("\n".join(withop)) - len("\n".join(base)) <= 230
    # None 이어도 깨지지 않음.
    assert serialize_chart_prefix(summary, None)


def test_end_to_end_prompt_and_invariance() -> None:
    import saju_api.services.chat_service as chat_service

    result = calculate(_STD_BIRTH)
    # 불변: final/canonical/favorability 그대로(operational 은 additive·미소비).
    fav = favorability_map(result)
    assert fav.get("水") == "한신" and fav.get("火") == "희신"  # 희신 과다 교정 반영(final=모델맵)
    # 프롬프트에 작동 역할 블록 + 지침 노출.
    res = chat_service.chat(_STD_BIRTH, "내 사주 성향 알려줘", date(2026, 6, 11), dry_run=True)
    pv = res.prompt_preview or ""
    assert "[작동 역할" in pv
    assert "조건부 한신/병" in pv and "조후보조신" in pv
    assert "작동성(operability)이 낮으면" in pv  # _OPERATIONAL_INSTRUCTION 지침
