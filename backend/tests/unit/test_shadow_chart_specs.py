"""Shadow 차트 spec/predicate 무결성 — 탐색 도구 사양 검증(운영 미연결).

24개 구조 사양의 구성 규칙(critical⊆required·best_match 한정·hap_confirmed 불변)과 predicate 가
표준 operational 차트에서 정상 평가되는지 고정. 규격: YONGSIN_OPERATIONAL_ROLE_SPEC §13-5
"""

from __future__ import annotations

from saju_api.services.manse_service import calculate
from saju_engines import shadow_chart_predicates as P
from saju_engines.shadow_chart_specs import SPECS
from saju_shared_types.birth_input import BirthInput

_STD = BirthInput(calendar_type="solar", birth_date="1977-12-16", birth_time="05:30",
                  birth_place_name="Seoul", gender="male")


def test_spec_count_and_ids_unique() -> None:
    assert len(SPECS) == 24
    ids = [s.chart_id for s in SPECS]
    assert len(set(ids)) == 24


def test_spec_structure_rules() -> None:
    for s in SPECS:
        assert s.required, f"{s.chart_id} required 비어있음"
        # critical 은 required 의 부분집합(이름 기준).
        req_names = {p.name for p in s.required}
        assert {p.name for p in s.critical} <= req_names, f"{s.chart_id} critical⊄required"
        # critical 은 best_match_allowed spec 에만 의미.
        if s.critical:
            assert s.best_match_allowed, f"{s.chart_id} critical 있으나 best_match 불허"


def test_hap_confirmed_is_note_only_invariant() -> None:
    spec = next(s for s in SPECS if s.chart_id == "hap_confirmed_01")
    # role 전환·세력 재산정 기대 없음 — invariant(additive 2계층 공존)만.
    assert spec.invariants and any("additive" in p.name for p in spec.invariants)
    assert spec.expected_shadow is None  # 변화 오행 fav 이동 기대 금지


def test_yongsin_bound_and_hap_bind_separated() -> None:
    yb = next(s for s in SPECS if s.chart_id == "yongsin_bound_01")
    hb = next(s for s in SPECS if s.chart_id == "hap_bind_01")
    assert any("yongsin_bound" in p.name for p in yb.required)   # operability factor
    assert any("합반bind" in p.name for p in hb.required)         # 일반 합 맥락
    assert not any("yongsin_bound" in p.name for p in hb.required)


def test_special_pattern_type_predicate() -> None:
    # 2차 확장에서 확보한 jonggyeok/jeonwang birth — special_pattern.type 검증(regression).
    import json
    from pathlib import Path
    charts_path = (Path(__file__).resolve().parents[2]
                   / "data" / "shadow_charts" / "charts.jsonl")
    by_id = {json.loads(line)["chart_id"]: json.loads(line)
             for line in charts_path.read_text(encoding="utf-8").splitlines() if line.strip()}
    jg = calculate(BirthInput(**by_id["jonggyeok_01"]["input"]))
    jw = calculate(BirthInput(**by_id["jeonwang_01"]["input"]))
    assert P.special_pattern_type("follow").fn(jg)     # 종격
    assert P.special_pattern_type("dominant").fn(jw)   # 전왕/일행득기
    # 표준 차트(정격)는 둘 다 아님.
    r = calculate(_STD)
    assert not P.special_pattern_type("follow").fn(r)
    assert not P.special_pattern_type("dominant").fn(r)


def test_predicates_evaluate_on_standard_chart() -> None:
    r = calculate(_STD)
    # 표준 차트가 만족해야 하는 대표 predicate(엔진 산출 바인딩 정상 동작 확인).
    assert P.has_operational_role("조건부 한신/병").fn(r)  # 희신 과다 교정 후 라벨
    assert P.has_operational_role("조후보조신").fn(r)
    assert P.has_operational_role("조건부 제살보조").fn(r)
    assert P.yongsin_factor("no_transmit").fn(r)
    assert P.element_pct_ge("水", 40).fn(r)
    assert P.dominant_group("officer").fn(r)
    # 미성립 predicate 는 False.
    assert not P.yongsin_factor("yongsin_void").fn(r)
    assert not P.geokguk_special(["종"]).fn(r)
