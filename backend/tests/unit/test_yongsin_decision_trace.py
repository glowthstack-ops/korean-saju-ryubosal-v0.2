"""용신 선정 근거 추적·희신 기능·축 충돌·부작용 주석 회귀(2026-10-01, 데굴님 승인 D·C·B·A1).

불변 원칙: 이 계층은 설명 전용이다 — final·canonical_roles·useful/unfavorable·operability 는 플래그
OFF(기본)에서 한 글자도 바뀌지 않는다(719명식 스냅샷 비교로 확인, WORKLOG 2026-10-01). 여기서는
감수 골든 3건의 추적 내용과 B 플래그(조후 강등 severe 게이트)의 ON/OFF 차이를 고정한다.
"""

from __future__ import annotations

from datetime import date

import pytest
from saju_manse_analysis import analyze_chart
from saju_manse_analysis.yongsin import candidates as cand
from saju_manse_analysis.yongsin.operational_role_config import (
    CLIMATE_DEMOTE_REQUIRE_SEVERE,
    COLLATERAL_SCORE_ENABLED,
    DOMINANT_REQUIRE_NO_CONTROLLER,
    HEESIN_FUNCTION_KO,
    MODEL_HEESIN_FUNCTION,
)

from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import build_yongsin_operational_summary
from saju_engines.context_reducer import _append_operational_summary
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.enums import Branch, Stem

_G1965 = (
    (Stem.EUL, Branch.SA), (Stem.SIN, Branch.SA), (Stem.GI, Branch.SA), (Stem.GYEONG, Branch.O),
    Stem.GI,
)
_G1959 = (
    (Stem.GI, Branch.HAE), (Stem.EUL, Branch.HAE), (Stem.SIN, Branch.CHUK), (Stem.GAP, Branch.O),
    Stem.SIN,
)
_G1953 = (
    (Stem.IM, Branch.JIN), (Stem.GYE, Branch.CHUK), (Stem.BYEONG, Branch.IN), (Stem.GAP, Branch.O),
    Stem.BYEONG,
)


def test_flags_default_off() -> None:
    """판정 변경 가능 플래그는 기본 OFF — 전환은 그리드 비교 보고 후 데굴님 확정."""
    assert CLIMATE_DEMOTE_REQUIRE_SEVERE is False
    assert DOMINANT_REQUIRE_NO_CONTROLLER is False
    assert COLLATERAL_SCORE_ENABLED is False


def test_heesin_function_vocabulary_closed() -> None:
    """모델 유형 표의 값은 전부 어휘 사전에 있어야 한다(미등록 key 노출 방지)."""
    assert set(MODEL_HEESIN_FUNCTION.values()) <= set(HEESIN_FUNCTION_KO)


def test_1965_trace_problem_and_rejected(make_pillars) -> None:
    y = analyze_chart(make_pillars(*_G1965)).yongsin
    t = y.decision_trace
    assert t is not None
    assert "극신강" in t.problem and "인성 과다(火)" in t.problem and "극열" in t.problem
    assert t.chosen_path.startswith("조후 보조형")
    assert t.heesin_function == "generate_yongsin"
    rejected = {(r["element"], r["reason"].split("(")[0]) for r in t.rejected}
    assert ("木", "경쟁 후보") in rejected and ("火", "climate_demote") in rejected
    assert y.final["heesin"] not in {r["element"] for r in t.rejected}  # 채택 희신은 기각이 아니다
    # 설명 전용 — 감수 골든 판정 불변.
    assert y.final["yongsin"] == "水" and y.final["heesin"] == "金"


def test_1953_bridge_heesin_function_and_collateral(make_pillars) -> None:
    y = analyze_chart(make_pillars(*_G1953)).yongsin
    t = y.decision_trace
    assert t is not None and t.heesin_function == "bridge_support"
    # 희신 火가 용신 金을 극한다 — 참고 글의 '희신이 더 큰 불균형을 만들 수 있다' 경고를 주석으로.
    assert any("火(희신)" in c and "金(용신)을 극함" in c for c in t.collateral)
    fire = next(r for r in y.operational_roles if r.element == "火")
    assert fire.note and "부작용" in fire.note
    assert t.axis_conflict is not None and t.axis_conflict["eokbu"] == "土"


def test_1959_axis_conflict_reported_without_changing_final(make_pillars) -> None:
    y = analyze_chart(make_pillars(*_G1959)).yongsin
    t = y.decision_trace
    assert t is not None and t.axis_conflict == {
        "eokbu": "金", "johu": "水", "resolution": "억부 우선", "significant": True,
    }
    assert any(w.startswith("억부·조후 축 충돌") for w in y.warnings)
    assert y.final["selected_model"] != "johu"


def test_models_carry_heesin_function(make_pillars) -> None:
    for spec in (_G1965, _G1959, _G1953):
        y = analyze_chart(make_pillars(*spec)).yongsin
        for m in y.candidate_models:
            if m.heesin:
                assert m.heesin_function in HEESIN_FUNCTION_KO, (m.model_type, m.label)


def test_climate_demote_gate_flag_keeps_candidate_when_not_severe(
    make_pillars, monkeypatch,
) -> None:
    """B 플래그: 1959(한·비severe)는 ON 이면 水가 강등되지 않는다. 1965(극열·severe)는 ON/OFF
    동일."""
    off = analyze_chart(make_pillars(*_G1959)).yongsin
    assert any(r["reason"] == "climate_demote" for r in off.decision_trace.rejected)
    monkeypatch.setattr(cand, "CLIMATE_DEMOTE_REQUIRE_SEVERE", True)
    on = analyze_chart(make_pillars(*_G1959)).yongsin
    assert not any(r["reason"] == "climate_demote" for r in on.decision_trace.rejected)
    on1965 = analyze_chart(make_pillars(*_G1965)).yongsin
    assert any(r["reason"] == "climate_demote" for r in on1965.decision_trace.rejected)
    assert on1965.final["yongsin"] == "水"


@pytest.mark.parametrize(
    "birth",
    [BirthInput(
        birth_date=date(1977, 12, 16), birth_time="05:30", birth_place_name="Seoul", gender="male",
    )],
)
def test_operational_summary_and_prefix_carry_trace(birth: BirthInput) -> None:
    result = calculate(birth)
    s = build_yongsin_operational_summary(result)
    assert s is not None and s.decision_problem and s.decision_path
    assert s.heesin_element and any(
        v.startswith(s.heesin_function_ko or "§") for v in HEESIN_FUNCTION_KO.values()
    )
    lines: list[str] = []
    _append_operational_summary(lines, s)
    text = "\n".join(lines)
    assert "희신 " in text and "판정 경로: [" in text


# ── 판정 변경 플래그 ON 의 대표 사례(그리드 diff 에서 선별, 2026-10-01) — OFF 가 기본이며 전환
# 미승인 ──

_GRID_1951_03 = BirthInput(
    birth_date=date(1951, 3, 15), birth_time="12:00", birth_place_name="서울", gender="male",
)
_GRID_1967_07 = BirthInput(
    birth_date=date(1967, 7, 15), birth_time="12:00", birth_place_name="서울", gender="male",
)


def test_pseudo_dominant_flag_competes_with_eokbu(monkeypatch) -> None:
    """E: 辛卯 辛卯 甲寅 庚午 — 木 압도이나 金 관살 투간 잔존 → ON 이면 가전왕으로 억부(관성 제겁)와
    경쟁."""
    from saju_manse_analysis import analyze_chart as _ac

    off = _ac(calculate(_GRID_1951_03).pillars).yongsin
    assert off.final["selected_model"] == "dominant_one_element"
    assert str(off.special_case_checks["dominant_one_element"].detail).startswith("pseudo:")
    monkeypatch.setattr(cand, "DOMINANT_REQUIRE_NO_CONTROLLER", True)
    on = _ac(calculate(_GRID_1951_03).pillars).yongsin
    assert on.final["selected_model"] != "dominant_one_element"
    assert any(m.label.startswith("가전왕") for m in on.candidate_models)
    assert any(w.startswith("가전왕") for w in on.warnings)
    assert "가전왕" in on.decision_trace.problem


def test_collateral_penalty_flag_changes_only_scores_when_on(monkeypatch) -> None:
    """A2: 丁未 丁未 庚辰 壬午 — OFF 는 財損印(木), ON 은 feeds_excess 계수로 치료 경로 모델이
    앞선다."""
    from saju_manse_analysis import analyze_chart as _ac

    off = _ac(calculate(_GRID_1967_07).pillars).yongsin
    assert off.final["selected_model"] == "wealth_breaks_resource"
    monkeypatch.setattr(cand, "COLLATERAL_SCORE_ENABLED", True)
    on = _ac(calculate(_GRID_1967_07).pillars).yongsin
    assert on.final["selected_model"].startswith("food_rescue")


# ── 偏印倒食 문헌 완비맵(식신격 한정, SPEC §14-3) ─────────────────────────────────────────

def test_siksin_pattern_pyeonin_dosik_uses_literature_map_in_neutral_band() -> None:
    """2015-03-01(식신격)을 중화신강으로 가정하면 용=金(財) 희=土(食傷) 기=木(印) 구=水(官殺)
    한=火(比劫)."""
    from saju_manse_analysis.structure.geokguk import detect_geokguk
    from saju_manse_analysis.yongsin import build_yongsin

    from saju_shared_types.enums import Stem as _Stem

    r = calculate(BirthInput(
        birth_date=date(2015, 3, 1), birth_time="03:34", birth_place_name="서울 도봉구",
        gender="male",
        latitude=37.6691, longitude=127.0324, timezone="Asia/Seoul",
    ))
    force = r.force_analysis
    st = force.strength.model_copy(update={"band": "중화신강", "score": 55.5, "borderline": False})
    f2 = force.model_copy(update={"strength": st})
    p = r.pillars
    gk = detect_geokguk(p, _Stem(p.day.stem), r.structure_analysis, p.gongmang_branches, f2)
    assert gk.main_structure == "식신격"
    y = build_yongsin(p, f2, r.structure_analysis, gk)
    f = y.final
    assert f["selected_model"] == "disease_remedy:pyeonin_dosik"
    roles = (f["yongsin"], f["heesin"], f["gisin"], f["gusin"], f["hansin"])
    assert roles == ("金", "土", "木", "水", "火")
    # 실제 밴드(태신강)는 2026-07-13 감수 판정 火/金 그대로.
    assert r.yongsin_analysis.final["yongsin"] == "火"
    assert r.yongsin_analysis.final["heesin"] == "金"
