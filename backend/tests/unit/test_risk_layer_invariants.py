"""P1-a 위험 엔진 층위 감사 — 일운 단독 승격이 구조적으로 불가능함을 고정한다.

배경: 총운 슬롯은 단순 가중합이라 층위 캡을 별도로 넣어야 했지만(P0·P0.5b), 위험
엔진은 이미 곱셈 구조와 occurrence dedup으로 같은 문제를 막고 있다. 새 캡을 추가하는
대신 그 불변식이 실제로 성립하는지 회귀로 못박는다(2026-07-27 데굴님 확정 — 감사만).

    structural_base = occurrence × impact
    raw = exposure × structural_base × (1 + persistence + compound)
"""

from __future__ import annotations

import pytest

from saju_engines.risk_scoring import risk_priority
from saju_shared_types.risk_engine import RiskScoreComponents


def _c(**kw) -> RiskScoreComponents:
    base = {"occurrence": 0.8, "impact": 0.8, "exposure": 1.0,
            "persistence": 0.0, "compound": 0.0, "protection": 0.0}
    base.update(kw)
    return RiskScoreComponents(**base)


def test_zero_occurrence_cannot_produce_risk():
    """독립 원인이 없으면(occurrence=0) 어떤 지속·복합도 위험을 만들 수 없다.

    vulnerability만 있고 occurrence가 서지 않는 경우가 여기 해당한다 —
    '원국 취약성'은 단독 승격 근거가 아니다.
    """
    raw, capped = risk_priority(_c(occurrence=0.0, persistence=1.0, compound=1.0))
    assert raw == 0.0
    assert capped == 0.0


def test_zero_exposure_cannot_be_revived():
    """비노출은 지속·복합으로 부활하지 못한다."""
    raw, _ = risk_priority(_c(exposure=0.0, persistence=1.0, compound=1.0))
    assert raw == 0.0


def test_persistence_alone_is_bounded_by_base():
    """occurrence가 약하면 persistence만으로 상위에 진입하지 못한다.

    기여 상한은 base×1이므로, 약한 원인에 지속·복합을 최대로 줘도 강한 원인의
    기본값을 넘지 못한다(층위 반복이 원인 수를 늘리지 못하게 하는 구조).
    """
    weak_max, _ = risk_priority(
        _c(occurrence=0.2, impact=0.5, persistence=1.0, compound=1.0)
    )
    strong_plain, _ = risk_priority(_c(occurrence=0.8, impact=0.8))
    assert weak_max < strong_plain


def test_layer_repetition_must_not_inflate_occurrence():
    """같은 관계의 층위 반복은 원인 1개다 — occurrence 재합산이 없어야 한다.

    persistence(반복성)는 별도 축이며 occurrence를 대신하지 않는다. 이 테스트는
    '일운에서 같은 관계가 또 보였다'가 occurrence를 올리는 경로가 없음을 고정한다.
    """
    single, _ = risk_priority(_c(occurrence=0.5, persistence=0.0))
    repeated, _ = risk_priority(_c(occurrence=0.5, persistence=0.6))
    # 반복은 강도를 올릴 뿐, 원인 항(base)은 동일하다.
    assert repeated > single
    assert repeated == pytest.approx(single * 1.6, rel=1e-6)


def test_capped_never_exceeds_one():
    """capped는 [0,1] — 포화가 등급 폭주로 이어지지 않는다."""
    _, capped = risk_priority(
        _c(occurrence=1.0, impact=1.0, exposure=1.0, persistence=1.0, compound=1.0)
    )
    assert capped == 1.0
