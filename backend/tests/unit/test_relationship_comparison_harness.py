"""P1-7b 결정적 비교 harness 스모크 — 파이프라인 유지 + 읽기 전용 불변식.

harness(fixture 채점→projection→벡터→legacy delta→분류)가 계속 돌아가고, 감사가
score/rank/candidate를 변형하지 않음을 확인한다. 상세 분류 정확성은 P1-7a 단위
테스트가 담당(여기선 실 데이터 파이프라인 무결성만).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from saju_api.services.relationship_legacy_comparison import (
    LegacyVectorComparisonClass,
    LegacyVectorComparisonRecord,
)


def _load_harness():
    path = (Path(__file__).resolve().parents[1].parent / "scripts" / "audits"
            / "relationship_p1_7" / "comparison_harness.py")
    spec = importlib.util.spec_from_file_location("_cmp_harness", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_harness_produces_valid_records():
    """전 fixture에서 유효 record 생성 — 클래스는 전부 고정 enum."""
    h = _load_harness()
    records, strata = h.build_records()
    assert len(records) > 50
    assert len(records) == len(strata)
    for r in records:
        assert isinstance(r, LegacyVectorComparisonRecord)
        assert isinstance(r.comparison_class, LegacyVectorComparisonClass)
    # 관찰 지도의 핵심 class가 실제로 관측되는지(감사 신호 존재).
    classes = {r.comparison_class for r in records}
    assert LegacyVectorComparisonClass.LEGACY_CAP_SATURATED in classes
    assert LegacyVectorComparisonClass.LEGACY_EVENT_KEY_BLIND_SPOT in classes


def test_harness_is_read_only_on_scoring():
    """비교 감사 전후 legacy 채점 결과가 byte-identical(delta 0)."""
    from datetime import date

    from saju_engines.event_engine_v2 import EventEngineV2
    from saju_engines.marriage_timing_profile import marriage_engine_flags
    from saju_shared_types.birth_input import BirthInput
    from saju_shared_types.ganji_calendar import GanjiLevel

    h = _load_harness()
    birth = BirthInput(
        calendar_type="solar", birth_date=date(1985, 3, 15), birth_time="14:30",
        birth_place_name="서울", gender="female")
    from saju_api.services.manse_service import calculate
    chart = calculate(birth.model_copy(update={"reference_date": date(2026, 7, 24)}))
    eng = EventEngineV2(h._DICTS, **marriage_engine_flags())
    before = eng.score(chart, levels={GanjiLevel.YEAR, GanjiLevel.MONTH})
    # 감사 실행(harness 전체) 후 재채점.
    h.build_records()
    after = eng.score(chart, levels={GanjiLevel.YEAR, GanjiLevel.MONTH})
    assert [c.model_dump() for c in before] == [c.model_dump() for c in after]


def test_harness_writes_report(tmp_path):
    """report 생성 — 파일 산출·record 수 반환(파이프라인 end-to-end)."""
    h = _load_harness()
    out = tmp_path / "REPORT.md"
    n = h.main(out)
    assert n > 50
    text = out.read_text(encoding="utf-8")
    assert "비교 class 분포" in text
    assert "§4 필수 매트릭스" in text
    assert "stratification" in text
