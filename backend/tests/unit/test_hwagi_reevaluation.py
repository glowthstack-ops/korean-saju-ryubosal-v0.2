"""化氣格 성립 시 격국·용신 재평가 (2026-10-08 데굴님 결정 — HWAGI_REEVALUATION_REVIEW §7).

정본 = hap_modes.detect_hwagi(일간 천간합 3단계 + 滴天髓 진화 조건: 월·시 합·투간 인겁관 不遇·
일간 무근). 진화(眞化) → 격국 special_pattern(type=transform, 화X격) 주격 치환 + 용신 化神 모델
(special 축 단독).
가화(假化) → 격국 치환 없음(경고만) + 용신 보조 모델 병기(final 불변). 신강약 일간 치환은 없음.
"""

from __future__ import annotations

import json
from pathlib import Path

from saju_manse_analysis.relations.hap_modes import detect_hwagi

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput

_GOLDEN = Path(__file__).resolve().parents[2] / "data" / "test_fixtures" / "manse" / "golden"


def _birth(d: str, t: str, g: str = "male") -> BirthInput:
    return BirthInput(calendar_type="solar", birth_date=d, birth_time=t,
                      birth_place_name="서울", gender=g)


def test_real_transform_reevaluates_geokguk_and_yongsin() -> None:
    """사례집 066/R(丙申 戊戌 甲戌 己巳): 甲己合土 진화 → 화토격 치환, 용신 土(化神)·희 火·기 木."""
    r = calculate(_birth("1956-11-03", "10:30"))
    p = r.pillars
    ganji = [p.year.ganji, p.month.ganji, p.day.ganji, p.hour.ganji]
    assert ganji == ["丙申", "戊戌", "甲戌", "己巳"]
    hw = detect_hwagi(p)
    assert hw is not None and hw.kind == "real" and hw.target_element == "土"
    assert hw.month_or_hour and not hw.dm_rooted and hw.blocking_stems == []
    g = r.geokguk
    assert g.special_pattern and g.special_pattern["type"] == "transform"
    assert g.special_pattern["override"] is True and g.main_structure == "화토격"
    assert g.formation_level == "특수격"
    assert g.follow_consistency and g.follow_consistency["status"] == "superseded_by_transform"
    fin = r.yongsin_analysis.final
    assert fin["selected_model"] == "transformation_structure"
    assert (fin["yongsin"], fin["heesin"], fin["gisin"]) == ("土", "火", "木")
    # 신강약은 일간 甲 기준 그대로(일간 치환 없음).
    assert r.force_analysis.strength.band in ("태신약", "신약")


def test_pseudo_transform_keeps_geokguk_and_final() -> None:
    """사례집 080/L(己亥 丙子 辛巳 癸巳): 丙辛合水 confirmed 이나 일간 유근·편인 투간 → 가화.

    격국 식신격 유지·special_pattern 없음·경고만, 용신 final 은 억부 결과 그대로(보조 모델만 병기).
    """
    r = calculate(_birth("1959-12-25", "10:30"))
    hw = detect_hwagi(r.pillars)
    assert hw is not None and hw.kind == "pseudo" and hw.dm_rooted
    assert any("편인" in b for b in hw.blocking_stems)
    g = r.geokguk
    assert g.main_structure == "식신격" and g.special_pattern is None
    assert any("가화" in w for w in g.warnings)
    ya = r.yongsin_analysis
    assert ya.final["selected_model"] != "transformation_structure"
    aux = [m for m in ya.candidate_models if m.model_type == "transformation_structure"]
    assert len(aux) == 1 and aux[0].is_auxiliary and aux[0].yongsin == "水"
    assert any("가화" in w for w in ya.warnings)


def test_no_transform_when_tier_not_confirmed() -> None:
    """골든 uk_london(庚午 壬午 丁卯 乙巳): 丁壬合木이 午월 休 → conditional → 화기격 아님."""
    fx = json.loads((_GOLDEN / "uk_london_bst.json").read_text("utf-8"))
    r = calculate(BirthInput(**fx["input"]))
    assert detect_hwagi(r.pillars) is None
    assert r.geokguk.main_structure == fx["expected"]["geokguk_main_structure"]
    assert not any(m.model_type == "transformation_structure"
                   for m in r.yongsin_analysis.candidate_models)


def test_transform_precedes_follow_in_special_signal() -> None:
    """066/R 은 종재격 override 조건도 충족하지만 우선순위(화기격→전왕→종격)로 화토격이 주격."""
    r = calculate(_birth("1956-11-03", "10:30"))
    sp = r.geokguk.special_pattern
    assert sp["type"] == "transform" and sp["name"] == "화토격"
    assert sp.get("jeonggyeok")  # 정격은 병기
