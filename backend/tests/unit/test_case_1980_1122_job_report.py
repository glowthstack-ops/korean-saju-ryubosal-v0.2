"""외부 상담 사례 회귀 — 1980-11-22 09:40 서울 남성 (직업 리포트 케이스).

실제 상담 리포트(메타인지보고서)와 우리 엔진의 명식·판정 정합성을 고정한다
(doc/v2_2/cases/1980_1122_job_report_case.md). 金/木 역할은 상담사 해석과 갈리는
감수 보류 항목이라 **테스트 실패 기준으로 단언하지 않고** review_flags 등록만
검증한다(2026-07-03 데굴님 확정).
"""

from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput

_FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "fixtures" / "cases" / "1980_1122_job_report_case.json"
)


def _load_fixture() -> dict:
    """사례 fixture JSON을 로드한다."""
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _calculate_case(fixture: dict):
    """fixture 입력으로 만세력 엔진을 실행한다(진태양시 보정 기본 적용)."""
    inp = fixture["input"]
    birth = BirthInput(
        calendar_type=inp["calendar_type"],
        birth_date=date.fromisoformat(inp["birth_date"]),
        birth_time=time.fromisoformat(inp["birth_time"]),
        birth_place_name=inp["birth_place_name"],
        gender=inp["gender"],
        reference_date=date(2026, 7, 3),
    )
    return calculate(birth)


def test_pillars_match_consultant_report() -> None:
    """사주 네 기둥이 상담 리포트(庚申 丁亥 己亥 己巳)와 일치한다."""
    fixture = _load_fixture()
    result = _calculate_case(fixture)
    assert result.pillars is not None
    for pos, expected in fixture["expected"]["pillars"].items():
        pillar = getattr(result.pillars, pos)
        assert pillar.stem + pillar.branch == expected, f"{pos}주 불일치"


def test_hour_pillar_stable_under_true_solar_time() -> None:
    """진태양시 보정(09:40→09:21)에도 시주가 己巳로 유지된다(경계 회귀 가드)."""
    fixture = _load_fixture()
    result = _calculate_case(fixture)
    tc = result.time_correction
    assert tc is not None
    assert tc.standard_time_hour_pillar == "己巳"
    assert tc.true_solar_time_hour_pillar == "己巳"
    assert tc.hour_pillar_changed_by_true_solar_time is (
        not fixture["expected"]["hour_pillar_stable_under_true_solar_time"]
    )


def test_strength_and_geokguk_match() -> None:
    """신강약(신약)·격국(정재격, 반성반패)이 상담 판정 방향과 일치한다."""
    fixture = _load_fixture()
    result = _calculate_case(fixture)
    assert result.force_analysis is not None
    band = result.force_analysis.strength.band
    assert band == fixture["expected"]["strength_band"]
    assert result.geokguk is not None
    geok = fixture["expected"]["geokguk"]
    assert result.geokguk.main_structure == geok["main_structure"]
    assert (
        result.geokguk.evaluation.success_failure_label
        == geok["success_failure_label"]
    )


def test_canonical_roles_match_reviewed_subset() -> None:
    """용신 土·희신 火·구신 水가 상담사 GOOD(화·토)/BAD(수)와 일치한다.

    金(한신 vs BAD)·木(기신 vs 혼재)은 감수 보류 — expected에 없어야 하며
    review_flags에 expert_review_required로 등록돼 있어야 한다.
    """
    fixture = _load_fixture()
    result = _calculate_case(fixture)
    assert result.yongsin_analysis is not None
    roles = result.yongsin_analysis.canonical_roles
    for role, element in fixture["expected"]["canonical_roles"].items():
        assert roles.get(role) == element, f"{role} 불일치"
    # 감수 보류 축은 단언 대상에서 빠져 있어야 한다(단일 사례로 role 고정 금지).
    assert "gisin" not in fixture["expected"]["canonical_roles"]
    assert "hansin" not in fixture["expected"]["canonical_roles"]


def test_review_flags_registered_for_metal_and_wood() -> None:
    """金/木 역할 차이가 expert_review_required로 fixture에 등록돼 있다."""
    fixture = _load_fixture()
    flags = {f["id"]: f for f in fixture["review_flags"]}
    assert flags["metal_role_mismatch"]["status"] == "expert_review_required"
    assert flags["wood_role_ambiguity"]["status"] == "expert_review_required"


def test_natal_sinsal_includes_hyeonchim() -> None:
    """원국 신살에 현침이 포함된다(활동 키워드 사전 star 매칭의 전제)."""
    fixture = _load_fixture()
    result = _calculate_case(fixture)
    assert result.traditional_extras is not None
    summary = result.traditional_extras.sinsal.summary.model_dump()
    all_names = {name for names in summary.values() for name in names}
    for name in fixture["expected"]["natal_sinsal_includes"]:
        assert name in all_names, f"신살 {name} 미검출"
