"""점수 포화 제어(2차 1단계) — 단계 클램프 제거 + 누적 raw 보존 + 최종 soft_cap + 기여 로그.

매달·여러 사건이 100에 붙어 변별이 사라지던 문제를, raw를 끝까지 누적하고 최종에만 soft_cap을
걸어 완화한다. 순위는 보존(soft_cap은 단조 증가). 단계별 기여(contributions)는 2차 계열 인지
감쇠 전환을 위한 계측이다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines.event_engine_v2 import EventEngineV2, _soft_cap
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def test_soft_cap_curve() -> None:
    """knee(85) 이하 항등, 이상은 100에 완만히 접근(거의 정확히 100 안 됨)."""
    assert _soft_cap(50) == 50
    assert _soft_cap(85) == 85
    assert _soft_cap(100) < 93 and _soft_cap(100) > 90  # ≈91.8
    assert _soft_cap(120) < 97 and _soft_cap(120) > 95  # ≈96.3
    assert _soft_cap(150) < 100  # 점근만, 정확히 100 아님
    # 단조 증가(순위 보존).
    assert _soft_cap(90) < _soft_cap(100) < _soft_cap(120) < _soft_cap(150)


def test_pipeline_desaturates_and_logs_contributions() -> None:
    """누적이 큰 달도 display는 100 미만으로 분산되고, raw_score·기여 로그가 남는다."""
    b = BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
        birth_place_name="서울 구로구", latitude=37.495, longitude=126.858,
        timezone="Asia/Seoul", gender="male", reference_date=date(2026, 6, 16),
    )
    cands = EventEngineV2(_DICTS).score(calculate(b), levels={GanjiLevel.MONTH})
    assert cands
    # 어떤 후보도 정확히 100으로 포화하지 않는다(soft_cap 점근).
    assert all(c.score < 100 for c in cands)
    # 누적이 큰 후보는 raw_score가 표시 점수보다 크다(클램프 전 raw 보존).
    saturated = [c for c in cands if c.raw_score > 100]
    assert saturated, "이 차트엔 raw>100 누적 후보가 있어야(포화 케이스)"
    for c in saturated:
        assert c.score < c.raw_score  # 압축됨
        # 단계별 기여 로그 — 최소 base는 있어야(2차 계열 감쇠 계측).
        assert "base" in c.contributions
        # 기여 합(±)이 raw_score에 근접(누적이 기여로 설명됨).
        assert abs(sum(c.contributions.values()) - c.raw_score) < 1.5
