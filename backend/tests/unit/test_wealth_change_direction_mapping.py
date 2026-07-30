"""`wealth_change` 결과 품질 방향 매핑 회귀 (2026-07-30).

축 이름은 `outcome_quality` 다 — opportunity/loss/pressure 는 사건 종류가 아니라
용기신 역할에서 나온 길흉 방향이다(코드 계보로 확정). 초기 측정이 이를 `semantic` 으로
잘못 명명했고, 그 명칭이 남으면 사건 subtype 근거로 오용될 수 있다.

초기 감사 매핑에 `압박·부담` 이 빠져 있어 그 4건이 **방향 결측**으로 관측됐다. 실제
데이터 결측이 아니라 감사 매핑 누락이었고, 그 상태로 판정하면 pressure 를 "upstream
잔여 범주"로 잘못 결론낼 수 있었다.

방향은 3종이며 `quality` 3값과 1:1 대응한다. 미등록 표현은 계속 UNKNOWN 으로
fail-closed 하되, **알려진 표현을 빠뜨리면 없는 결측을 만들어 낸다.**
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
for _p in (
    _BACKEND / "scripts",
    _BACKEND / "apps" / "api",
    _BACKEND / "packages" / "saju_engines",
    _BACKEND / "packages" / "shared_types",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import audit_wealth_change_signature as A  # noqa: E402
from saju_shared_types.event_engine import EventKeyV2  # noqa: E402
from saju_shared_types.events import (  # noqa: E402
    Confidence,
    EventCandidate,
    EventPolarity,
    EventType,
    Signal,
)


def _cand(quality: str, effect: str, timing: str = "active") -> EventCandidate:
    return EventCandidate(
        event_key=EventKeyV2.WEALTH_CHANGE, event_type=EventType.PROGRESS,
        period="2027-02", score=90, confidence=Confidence.MEDIUM,
        polarity=EventPolarity.POSITIVE, quality=quality, timing=timing,
        signals=[Signal(type="materialization", name="materialization",
                        effect=effect, weight=1.0)],
    )


@pytest.mark.parametrize(
    ("quality", "direction", "expected"),
    [
        ("opportunity", "기회·유입", A.QUALITY_OPPORTUNITY),
        ("loss", "손실·지출", A.QUALITY_LOSS),
        ("pressure", "압박·부담", A.QUALITY_PRESSURE),
    ],
)
def test_three_directions_map_and_agree_with_quality(
    quality: str, direction: str, expected: str
) -> None:
    """세 방향 모두 인식되고 quality 와 일치해야 한다.

    일치 자체는 독립 근거의 합치가 아니다 — materialization 방향은 quality 를 문자열로
    옮긴 것이라 1:1 이다. 여기서 고정하는 것은 **매핑 누락이 없다**는 것뿐이다.
    """
    r = A.read_axes(_cand(quality, f"강한 사건 후보 · {direction} · new_start"))
    assert r.outcome_quality_axis == expected
    assert set(r.outcome_quality_sources) == {"quality", "materialization_direction"}
    assert not r.direction_missing
    assert not r.outcome_quality_conflict


def test_pressure_direction_is_not_swallowed_as_a_process_stage() -> None:
    """방향 판정이 뒤로 밀리면 방향 표현이 단계로 흘러간다 — 실제 발생한 결함."""
    r = A.read_axes(
        _cand("pressure", "강한 사건 후보 · 압박·부담 · exposure_volatility")
    )
    assert "압박·부담" not in r.process_stages
    assert r.process_stages == ("exposure_volatility",)


def test_unregistered_direction_stays_unknown() -> None:
    """미등록 표현은 임의 편입하지 않는다(fail-closed)."""
    r = A.read_axes(_cand("", "강한 사건 후보 · 새로운·표현 · new_start"))
    assert r.outcome_quality_axis == A.UNKNOWN
    assert r.direction_missing and r.quality_missing


def test_conflicting_sources_yield_unknown_not_a_merge() -> None:
    """quality 와 방향이 어긋나면 억지로 합치지 않는다."""
    r = A.read_axes(_cand("opportunity", "강한 사건 후보 · 손실·지출 · new_start"))
    assert r.outcome_quality_axis == A.UNKNOWN
    assert r.outcome_quality_conflict


def test_palace_label_is_context_not_semantic_or_stage() -> None:
    """궁위는 의미·단계 어느 쪽에도 들어가지 않는다."""
    r = A.read_axes(
        _cand("loss", "강한 사건 후보 · 손실·지출 · 일주(배우자·거처) · formalization")
    )
    assert r.outcome_quality_axis == A.QUALITY_LOSS
    assert set(r.context_loci) == {"spouse_palace", "residence_context"}
    assert r.process_stages == ("formalization",)
    assert r.context_sources == ("materialization_palace_label",)
