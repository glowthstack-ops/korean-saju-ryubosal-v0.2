"""모델별 favorability 오버라이드 검증 (용신 검증 질문 개선 — Step 1).

favorability_map_from_model이 후보 모델의 용희기구한을 올바른 라벨로 매핑하고,
EventScorer.score(fav_override=...)가 차트 기본값 대신 주입 매핑을 사용해 모델별로 다른
이벤트 극성을 산출할 수 있는지 확인한다(LLM·DB 불필요).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.event_scoring import (
    favorability_map,
    favorability_map_from_model,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.yongsin import YongsinCandidateModel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _result():
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 13),
    ))


def test_favorability_map_from_model_labels() -> None:
    m = YongsinCandidateModel(
        model_type="test", label="테스트",
        yongsin="水", heesin="金", gisin="土", gusin="火", hansin="木", confidence=1.0,
    )
    fav = favorability_map_from_model(m)
    assert fav == {"水": "용신", "金": "희신", "土": "기신", "火": "구신", "木": "한신"}


def test_partial_model_skips_empty_roles() -> None:
    m = YongsinCandidateModel(model_type="t", label="t", yongsin="水", gisin="火", confidence=1.0)
    fav = favorability_map_from_model(m)
    assert fav == {"水": "용신", "火": "기신"}
    assert "金" not in fav


def test_override_changes_polarity_distribution() -> None:
    result = _result()
    scorer = EventEngineV2(_DICTS)
    base = scorer.score_legacy(result, levels={GanjiLevel.YEAR})

    # 차트 용신과 정반대 역할을 준 모델로 재계산하면 극성 분포가 달라져야 한다.
    chart_fav = favorability_map(result)
    # 용신↔기신을 뒤집은 인위적 모델.
    swapped = {role: el for el, role in chart_fav.items()}
    inverted = YongsinCandidateModel(
        model_type="inverted", label="역전",
        yongsin=swapped.get("기신"), heesin=swapped.get("구신"),
        gisin=swapped.get("용신"), gusin=swapped.get("희신"),
        hansin=swapped.get("한신"), confidence=1.0,
    )
    override = favorability_map_from_model(inverted)
    inv = scorer.score_legacy(result, levels={GanjiLevel.YEAR}, fav_override=override)

    # 같은 연도·이벤트가 두 실행 모두 나오되, 극성이 적어도 한 건 이상 달라야 한다(변별력).
    base_pol = {(c.period, str(c.event_key)): str(c.polarity) for c in base}
    inv_pol = {(c.period, str(c.event_key)): str(c.polarity) for c in inv}
    common = set(base_pol) & set(inv_pol)
    assert common, "공통 (연도,이벤트)가 있어야 비교 가능"
    assert any(base_pol[k] != inv_pol[k] for k in common), "모델별 극성이 달라야 변별 가능"
