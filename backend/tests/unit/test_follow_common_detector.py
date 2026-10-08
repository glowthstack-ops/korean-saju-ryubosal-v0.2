"""종격 공통 판정기(strength.follow_check.detect_follow) — 격국·용신 통합 기준 (2026-10-08).

기준(엔진 채택 규칙): 점수≤34 ∧ 비겁 뿌리<8(인성 뿌리 제외, 투간 비겁은 무근이면 허부) ∧ 압도
세력 ≥0.40·인성<0.12 → 진종 / ≥0.33·인성<0.28 → 가종. 격국 override 는 진종만, 명칭은 세력 기준.
"""

from __future__ import annotations

from saju_manse_analysis.strength.follow_check import PEER_ROOT_MAX, detect_follow

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput


def _calc(d: str, t: str, g: str = "male"):
    return calculate(BirthInput(calendar_type="solar", birth_date=d, birth_time=t,
                                birth_place_name="서울", gender=g))


def test_real_follow_confirms_on_both_sides() -> None:
    """shadow jonggyeok_01(己丑 丙子 丙申 戊子): 진종 → 격국 override(종살격) + 용신 종격."""
    r = _calc("1961-01-03", "00:30")
    fc = detect_follow(r.force_analysis)
    assert fc is not None and fc.kind == "real" and fc.name == "종살격"
    g = r.geokguk
    assert g.special_pattern["type"] == "follow" and g.special_pattern["override"]
    assert g.main_structure == "종살격"
    assert r.yongsin_analysis.final["selected_model"] == "follow_structure"
    assert g.follow_consistency and g.follow_consistency["status"] == "consistent"


def test_rooted_peer_blocks_follow_even_if_weak() -> None:
    """066/L(丙申 戊戌 甲戌 辛未, 점수 18.6): 未 중 乙 비겁 뿌리 9.2 → 종격 아님.

    전문가 해설 "신약 甲, 재성 강, 인비 필요"와 같은 방향.
    """
    r = _calc("1956-11-03", "14:30")
    assert r.force_analysis.strength.components["peer_root_score"] >= PEER_ROOT_MAX
    assert detect_follow(r.force_analysis) is None
    assert r.geokguk.special_pattern is None
    assert r.yongsin_analysis.final["selected_model"] != "follow_structure"


def test_resource_support_makes_pseudo_follow() -> None:
    """063/L(癸巳 戊午 甲午 壬申): 비겁 무근이나 인성 0.23 의지처 → 가종.

    격국은 신호만(override 없음, 상관격 유지), 용신은 억부 1차 + 종격 보조 병기.
    """
    r = _calc("1953-06-12", "16:00", "female")
    fc = detect_follow(r.force_analysis)
    assert fc is not None and fc.kind == "pseudo" and fc.name == "종아격"
    g = r.geokguk
    assert g.special_pattern["type"] == "follow" and g.special_pattern["override"] is False
    assert g.main_structure == "상관격"
    ya = r.yongsin_analysis
    assert ya.final["selected_model"] != "follow_structure"
    assert any(m.model_type == "follow_structure" and "가종" in m.label
               for m in ya.candidate_models)


def test_no_follow_above_score_threshold() -> None:
    """기준 사주 1980-11-22(점수>34) → 전제 탈락, 판정 None."""
    r = _calc("1980-11-22", "09:40")
    assert r.force_analysis.strength.score > 34
    assert detect_follow(r.force_analysis) is None


def test_clarity_level_matches_common_follow_result() -> None:
    """격국 명확도는 공통 판정과 표현이 일치한다: 진종=confirmed, 가종=uncertain, 비종=일반 라벨."""
    real = _calc("1961-01-03", "00:30")            # shadow jonggyeok_01 — 진종
    pseudo = _calc("1953-06-12", "16:00", "female")  # 063/L — 가종
    none = _calc("1956-11-03", "14:30")             # 066/L — 비겁 뿌리 有, 비종
    assert real.geokguk.evaluation.clarity_level == "special_pattern_confirmed"
    assert pseudo.geokguk.evaluation.clarity_level == "special_pattern_uncertain"
    assert none.geokguk.evaluation.clarity_level not in (
        "special_pattern_confirmed", "special_pattern_uncertain",
    )
    assert "종격" in real.geokguk.evaluation.clarity_policy
    assert "양쪽" in pseudo.geokguk.evaluation.clarity_policy
    # 표시와 가중 분리: 진종은 옛 종격 의심 가중(0.25×1.30=0.325), 가종은 정격 평가 가중 그대로
    # (라벨 변경으로 자동 상승하지 않음).
    assert real.geokguk.evaluation.final_weight == 0.325
    assert pseudo.geokguk.evaluation.final_weight < 0.325
