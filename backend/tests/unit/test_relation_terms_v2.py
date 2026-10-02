"""관계 용어 층위 정리 v2(2026-09-18 데굴님 승인, 전문가 참고 기준) — 서술·표기 전용 회귀.

플래그 SAJU_RELATION_TERMS_V2_ENABLED(기본 OFF)로 4단 서술·쟁합 십성 라벨·합처봉충·세운병림
표지가 켜진다. OFF면 기존 문자열 그대로. 점수·판정은 어느 쪽도 바뀌지 않는다.
희용신 손상(harm)은 HAP_MITIGATION 플래그(판정 층)에 속하며 여기서는 판정기만 검증한다.
"""

from __future__ import annotations

from datetime import date

import pytest
from saju_manse_analysis.relations.hap_mitigation import resolve_hap_mitigation

from saju_api.services.manse_service import calculate
from saju_engines import context_reducer as cr
from saju_engines import hap_lines, period_v2_config
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.llm_input import SelectedYear
from saju_shared_types.structure_patterns import DetectedPattern

_FAV = {"土": "용신", "火": "희신", "木": "기신", "水": "구신", "金": "한신"}


@pytest.fixture(scope="module")
def chart():
    """데굴 차트(庚申 丁亥 己亥 己巳 · 공망 辰巳)."""
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
        birth_place_name="서울 구로구", latitude=37.4944, longitude=126.8563,
        timezone="Asia/Seoul", gender="male", reference_date=date(2026, 9, 18),
    ))


def _pattern(**over) -> DetectedPattern:
    base = dict(
        pattern_id="SANGGWAN_GYEONGWAN", name_ko="상관견관", family=["conflict"], strength=0.7,
        scope="natal", polarity_mode="depends_on_yonggi_and_control",
        domain_hints=["career_change", "legal_conflict"],
        evidence=["상관 존재", "정관 존재", "상관→정관 극 접촉(천간/지지)"],
        llm_tag="상관견관: 표현·반항·비판(상관)이 규칙·조직·직책(정관)과 충돌하는 구조",
    )
    base.update(over)
    return DetectedPattern(**base)


def test_four_stage_line_orders_action_area_mode_conditions() -> None:
    """작용→영역·후보→양상→성립 조건 순서, 이름 접두 제거, 별칭 병기."""
    line = cr._pattern_four_stage_line(_pattern(aliases=["상관극관(傷官剋官)"]))
    assert line.startswith("상관견관: [작용] 표현·반항·비판(상관)이")
    i_act, i_area = line.index("[작용]"), line.index("[영역·후보]")
    i_mode, i_cond = line.index("[양상]"), line.index("[성립 조건]")
    assert i_act < i_area < i_mode < i_cond
    assert "이직·직업 변화" in line and "법적 갈등" in line  # domain_hints → 한글 사건명
    assert "용기신·제어 여부에 따라 유불리가 갈림" in line
    assert "상관 존재 · 정관 존재 · 상관→정관 극 접촉" in line
    assert line.endswith("[별칭: 상관극관(傷官剋官)]")
    # 사전 필드가 비어도 깨지지 않는다.
    bare = cr._pattern_four_stage_line(
        _pattern(domain_hints=[], evidence=[], polarity_mode="context_only")
    )
    assert "명시 영역 없음" in bare and "사전 성립 조건 없음" in bare
    assert "맥락 표지 — 길흉을 정하지 않음" in bare


def test_pattern_block_switches_on_flag(monkeypatch) -> None:
    """OFF: 기존 태그 한 줄. ON: 4단 서술 헤더 + 줄."""
    p = _pattern()
    monkeypatch.setattr(period_v2_config, "RELATION_TERMS_V2_ENABLED", False)
    off: list[str] = []
    cr._append_structure_patterns(off, [p])
    assert off[-1] == p.llm_line and "[구조 패턴 — 의미 설명 태그" in off[1]
    monkeypatch.setattr(period_v2_config, "RELATION_TERMS_V2_ENABLED", True)
    on: list[str] = []
    cr._append_structure_patterns(on, [p])
    assert "작용→영향 영역→가능한 양상→성립 조건 순으로 읽을 것" in on[1]
    assert on[-1].startswith("상관견관: [작용]")


def test_sewoon_line_marks_byeongrim_only_when_same_ganji(monkeypatch) -> None:
    """세운병림 표지는 ON + 대운·세운 간지 동일일 때만. 흉 아님 문구 동반."""
    same = SelectedYear(year=2072, ganji="壬辰", daewoon="壬辰", reason_selected="테스트")
    diff = SelectedYear(year=2027, ganji="丁未", daewoon="壬辰", reason_selected="테스트")
    monkeypatch.setattr(period_v2_config, "RELATION_TERMS_V2_ENABLED", True)
    assert "세운병림(대운과 같은 간지" in cr._sewoon_line(same)
    assert "그 자체는 흉이 아님" in cr._sewoon_line(same)
    assert "세운병림" not in cr._sewoon_line(diff)
    monkeypatch.setattr(period_v2_config, "RELATION_TERMS_V2_ENABLED", False)
    assert cr._sewoon_line(same) == "세운 2072 壬辰 (대운 壬辰 내) — 선별: 테스트"


def test_contend_label_names_ten_god_group(chart, monkeypatch) -> None:
    """운 乙 둘이 원국 庚을 두고 다투면 '식상 쟁합 — 상관 庚'. OFF면 '쟁합·투합'만."""
    monkeypatch.setattr(period_v2_config, "RELATION_TERMS_V2_ENABLED", True)
    on = hap_lines.luck_hap_mode_lines(chart, luck_stems=["乙", "乙"])
    assert any("쟁합·투합(식상 쟁합 — 상관 庚)" in ln for ln in on), on
    monkeypatch.setattr(period_v2_config, "RELATION_TERMS_V2_ENABLED", False)
    off = hap_lines.luck_hap_mode_lines(chart, luck_stems=["乙", "乙"])
    assert any(ln.endswith("쟁합·투합") or "· 쟁합·투합" in ln for ln in off), off
    assert not any("식상 쟁합" in ln for ln in off)


def test_hapcheo_bongchung_marks_natal_clash_on_combined_member(chart, monkeypatch) -> None:
    """2027-02 운 寅: 寅亥合의 亥를 원국 巳가, 寅을 원국 申이 충 → 합처봉충 표기(ON만)."""
    monkeypatch.setattr(period_v2_config, "RELATION_TERMS_V2_ENABLED", True)
    on = [ln for ln in hap_lines.luck_hap_mode_lines(chart, luck_branches=["寅"]) if "亥寅合" in ln]
    assert on and "합처봉충(" in on[0] and "巳충亥" in on[0] and "申충寅" in on[0]
    monkeypatch.setattr(period_v2_config, "RELATION_TERMS_V2_ENABLED", False)
    off_all = hap_lines.luck_hap_mode_lines(chart, luck_branches=["寅"])
    off = [ln for ln in off_all if "亥寅合" in ln]
    assert off and "합처봉충" not in off[0]


def test_harm_detected_only_for_bound_useful_god_outside_void(chart) -> None:
    """희용신 손상: 묶인 원국 글자가 용·희신이고 공망지가 아닐 때만(데굴 실제 역할은 해당 없음)."""
    # 실제 역할(亥=구신): 寅亥合은 완화이지 손상이 아니다.
    real = resolve_hap_mitigation(chart.pillars, _FAV, luck_stem="壬", luck_branch="寅")
    assert real.branch_mitigated and not real.branch_harmed
    # 가정 역할(水=용신): 같은 합이 원국 용신 亥를 묶는 손상으로 판정된다.
    pretend = {"土": "기신", "火": "기신", "木": "한신", "水": "용신", "金": "희신"}
    harmed = resolve_hap_mitigation(chart.pillars, pretend, luck_stem="壬", luck_branch="寅")
    assert harmed.branch_harmed and not harmed.branch_mitigated
    assert any("길신 손상" in n for n in harmed.notes)
    # 巳申合: 巳가 공망지라 合則不能空이 우선 — 희신 巳가 묶여도 손상으로 보지 않는다.
    void_case = resolve_hap_mitigation(chart.pillars, _FAV, luck_stem="戊", luck_branch="申")
    assert not void_case.branch_harmed
