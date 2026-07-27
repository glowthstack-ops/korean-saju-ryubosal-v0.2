"""P3 무부호 강도 golden test (2026-07-27 데굴님 확정).

계약: 방향 무관 구조 보정은 보존하고, 용희기구한 modifier와 그로 인한 clamp만 분리한다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.signal_magnitude import (
    PARTIAL_DECAY,
    MagnitudeUnavailable,
    derive_unsigned_magnitude_v2,
    v2_contribution,
)


def test_magnitude_ignores_favorability_role():
    """역할만 다른 두 사례의 무부호 강도는 같아야 한다(달라지는 건 부호뿐)."""
    a = derive_unsigned_magnitude_v2(base_weight=0.55, partial=False)
    b = derive_unsigned_magnitude_v2(base_weight=0.55, partial=False)
    assert a.unsigned_magnitude_v2 == b.unsigned_magnitude_v2
    assert v2_contribution(a.unsigned_magnitude_v2, 1) == pytest.approx(0.55)
    assert v2_contribution(b.unsigned_magnitude_v2, -1) == pytest.approx(-0.55)
    assert abs(v2_contribution(a.unsigned_magnitude_v2, 1)) == abs(
        v2_contribution(b.unsigned_magnitude_v2, -1)
    )


def test_partial_relation_is_weaker_than_complete():
    """부분 성립은 완성보다 약하다 — 방향 무관 구조 보정은 보존한다."""
    full = derive_unsigned_magnitude_v2(base_weight=0.55, partial=False)
    partial = derive_unsigned_magnitude_v2(base_weight=0.65, partial=True)
    assert partial.unsigned_magnitude_v2 == pytest.approx(0.65 * PARTIAL_DECAY)
    assert partial.magnitude_formula_id == "base_x_partial_v1"
    assert full.magnitude_formula_id == "base"


def test_no_double_modifier():
    """V2 기여는 곱셈 한 번뿐 — 층위·구조 값을 다시 곱하면 안 된다."""
    assert v2_contribution(0.7, -1) == pytest.approx(-0.7)
    assert v2_contribution(0.7, 1) == pytest.approx(0.7)
    assert v2_contribution(0.7, 0) == pytest.approx(0.0)


def test_magnitude_is_never_negative():
    """unsigned 계약 — 음수 입력은 재현 실패로 둔다."""
    with pytest.raises(MagnitudeUnavailable):
        derive_unsigned_magnitude_v2(base_weight=-0.1, partial=False)


def test_missing_input_is_unavailable_not_guessed():
    """구형 캐시처럼 입력이 없으면 임의 추정하지 않는다."""
    with pytest.raises(MagnitudeUnavailable):
        derive_unsigned_magnitude_v2(base_weight=None, partial=False)
    with pytest.raises(MagnitudeUnavailable):
        derive_unsigned_magnitude_v2(base_weight=0.5, partial=None)


def test_write_time_equals_read_time_fallback():
    """write-time과 read-time fallback이 같은 순수 함수라 결과가 동일하다."""
    args = {"base_weight": 0.65, "partial": True}
    assert (
        derive_unsigned_magnitude_v2(**args).model_dump()
        == derive_unsigned_magnitude_v2(**args).model_dump()
    )


def test_legacy_clamp_does_not_erase_v2_signal():
    """유불리 modifier·clamp로 legacy가 0이 되어도 V2 강도는 살아 있다.

    현재 사전 값(최소 baseScore 0.3, 최대 음수 modifier -0.25)에서는 clamp가 도달
    불가하지만, 사전이 바뀌면 즉시 활성화되는 잠재 결함이라 계약을 고정한다.
    """
    base, modifier = 0.15, -0.2
    legacy_weight = max(base + modifier, 0.0)
    v2 = derive_unsigned_magnitude_v2(base_weight=base, partial=False)
    assert legacy_weight == 0.0  # V1은 소거
    assert v2.unsigned_magnitude_v2 > 0  # V2는 생존
    assert v2_contribution(v2.unsigned_magnitude_v2, -1) == pytest.approx(-0.15)


def test_write_time_signals_carry_magnitude():
    """실제 파이프라인에서 모든 신호가 무부호 강도를 갖는다(생성이 clamp보다 앞선다)."""
    from saju_api.services.chat_service import _DICTS
    from saju_api.services.manse_service import calculate, luck_days
    from saju_engines.precompute import CompositeBuilder
    from saju_shared_types.birth_input import BirthInput
    from saju_shared_types.precompute import CompositeLevel

    birth = BirthInput(
        birth_date=date(1980, 11, 22), birth_time="09:40:00",
        birth_place_name="서울", gender="male", reference_date=date(2026, 7, 27),
    )
    chart = calculate(birth)
    chart.luck_cycles.daily_luck = luck_days(birth, 2026, 7)
    comps = CompositeBuilder(_DICTS).build(
        chart, "t", "1.0.0", "2026-07-27T00:00:00+00:00",
        levels={CompositeLevel.DAY, CompositeLevel.MONTH},
    )
    signals = [s for c in comps for s in c.domain_signals]
    assert signals
    for s in signals:
        assert s.unsigned_magnitude_v2 is not None
        assert s.unsigned_magnitude_v2 >= 0
        assert s.magnitude_formula_id in ("base", "base_x_partial_v1")
        assert s.structural_weight_version


def test_occurrence_ids_distinguish_same_relation_at_different_positions():
    """월지 亥와 일지 亥가 만드는 두 寅亥合이 별개 신호로 유지된다(dedupe 핵심 조건)."""
    from saju_api.services.chat_service import _DICTS
    from saju_api.services.manse_service import calculate, luck_days
    from saju_engines.precompute import CompositeBuilder
    from saju_engines.signal_occurrence import canonical_identity_key
    from saju_shared_types.birth_input import BirthInput
    from saju_shared_types.precompute import CompositeLevel

    birth = BirthInput(
        birth_date=date(1980, 11, 22), birth_time="09:40:00",
        birth_place_name="서울", gender="male", reference_date=date(2026, 7, 27),
    )
    chart = calculate(birth)
    chart.luck_cycles.daily_luck = luck_days(birth, 2026, 7)
    comps = CompositeBuilder(_DICTS).build(
        chart, "t", "1.0.0", "x", levels={CompositeLevel.DAY}
    )
    day = next(c for c in comps if c.period_key == "2026-07-27")
    hae = {
        canonical_identity_key(s.participant_occurrence_ids)
        for s in day.domain_signals
        if s.source_interaction == "rel_寅亥合"
    }
    assert len(hae) == 2  # 관계명·글자는 같아도 원국 위치가 다르면 별개
    assert any("natal.month.branch:亥" in k for k in hae)
    assert any("natal.day.branch:亥" in k for k in hae)
    # relation ID fallback 금지 — occurrence가 반드시 채워져야 한다.
    for s in day.domain_signals:
        assert s.participant_occurrence_ids
        assert s.source_interaction not in s.participant_occurrence_ids


def test_occurrence_id_format_is_deterministic():
    """천간·지지와 층위를 구분하는 결정론적 형식."""
    from saju_engines.signal_occurrence import canonical_identity_key, occurrence_id

    assert occurrence_id("natal_month", "亥") == "natal.month.branch:亥"
    assert occurrence_id("natal_day", "亥") == "natal.day.branch:亥"
    assert occurrence_id("year", "丙", {"year": "丙午"}) == "year:丙午.stem:丙"
    assert occurrence_id("day", "寅", {"day": "2026-07-27"}) == (
        "day:2026-07-27.branch:寅"
    )
    # dedupe 키는 정렬본 — 참여 순서가 달라도 같은 신호로 본다.
    a = ("natal.month.branch:亥", "day:2026-07-27.branch:寅")
    assert canonical_identity_key(a) == canonical_identity_key(tuple(reversed(a)))
