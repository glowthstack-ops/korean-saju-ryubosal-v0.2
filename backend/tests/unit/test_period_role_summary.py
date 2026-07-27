"""P2 연·월·일 역할 요약 + 슬롯 상태 불변식 (2026-07-27 데굴님 확정).

핵심: 일진 하나로 총평하지 않도록 background/target 상태를 각각 보존하고,
천간·지지 방향이 다르면 net 부호와 무관하게 MIXED를 유지한다.
"""

from __future__ import annotations

import pytest

from saju_engines.period_role_summary import (
    build_period_role_summary,
    build_pillar_role_state,
    derive_slot_status,
)
from saju_shared_types.luck_hierarchy import (
    LuckHierarchy,
    ParticipantLayer,
    PillarSummary,
)
from saju_shared_types.period_role_summary import (
    BackgroundState,
    HierarchySummary,
    PillarState,
    SlotStatus,
    SlotStatusSource,
)

# 1980-11-22 09:40 서울 남 (己土 신약) 기준 — 用土 喜火 忌木 仇水 閑金.
_FAV = {"土": "용신", "火": "희신", "木": "기신", "水": "구신", "金": "한신"}


def _hierarchy(level: str, layers: list[tuple[ParticipantLayer, str]]) -> LuckHierarchy:
    return LuckHierarchy(
        requested_period="x", requested_level=level,
        active_layers=[
            PillarSummary(layer=lay, ganji=g, stem=g[0], branch=g[1])
            for lay, g in layers
        ],
    )


@pytest.mark.parametrize(
    ("ganji", "expected", "net"),
    [
        ("乙未", PillarState.MIXED, 0.20),  # 乙 기신 / 未 용신 — net 양수여도 MIXED
        ("丙午", PillarState.FAVORABLE, 1.00),  # 丙 희신 / 午 희신
        ("壬寅", PillarState.ADVERSE, -1.00),  # 壬 구신 / 寅 기신
    ],
)
def test_pillar_state_uses_direction_not_legacy_score(ganji, expected, net):
    """4:6은 역할 방향값(+1/0/-1)에만 적용한다(기존 stem/branch 점수 재사용 금지)."""
    row = build_pillar_role_state(ParticipantLayer.ANNUAL, ganji, _FAV)
    assert row.state is expected
    assert row.sort_net == pytest.approx(net)


def test_mixed_is_never_overridden_by_sort_net():
    """sort_net이 양수여도 방향이 반대면 MIXED로 남는다."""
    row = build_pillar_role_state(ParticipantLayer.MONTHLY, "乙未", _FAV)
    assert row.sort_net > 0
    assert row.state is PillarState.MIXED


def test_unknown_role_is_not_neutral():
    """역할 미상을 閑(중립)으로 축약하지 않는다 — 데이터 누락과 중립은 다르다."""
    row = build_pillar_role_state(ParticipantLayer.DAILY, "壬寅", {})
    assert row.state is PillarState.UNKNOWN
    assert row.direction_available is False


def test_target_is_decided_by_requested_level_not_last_layer():
    """일진 데이터가 있어도 월운 질문의 target은 월운이다."""
    h = _hierarchy("month", [
        (ParticipantLayer.DAEWOON, "壬辰"),
        (ParticipantLayer.ANNUAL, "丙午"),
        (ParticipantLayer.MONTHLY, "乙未"),
        (ParticipantLayer.DAILY, "壬寅"),
    ])
    summary = build_period_role_summary(h, _FAV)
    assert summary.target_layer is ParticipantLayer.MONTHLY
    assert summary.target.ganji == "乙未"
    # 배경은 상위 층위만 — 하위인 일진은 배경이 아니다.
    assert [r.layer for r in summary.background] == [
        ParticipantLayer.DAEWOON, ParticipantLayer.ANNUAL,
    ]


def test_year_question_target_is_annual():
    """연운 질문에 월운·일진 데이터가 있어도 target은 세운이다."""
    h = _hierarchy("year", [
        (ParticipantLayer.DAEWOON, "壬辰"),
        (ParticipantLayer.ANNUAL, "丙午"),
        (ParticipantLayer.MONTHLY, "乙未"),
    ])
    summary = build_period_role_summary(h, _FAV)
    assert summary.target_layer is ParticipantLayer.ANNUAL
    assert [r.layer for r in summary.background] == [ParticipantLayer.DAEWOON]


def test_daily_background_includes_daewoon():
    """일운 질문의 배경에는 대운·세운·월운이 모두 들어간다."""
    h = _hierarchy("day", [
        (ParticipantLayer.DAEWOON, "壬辰"),
        (ParticipantLayer.ANNUAL, "丙午"),
        (ParticipantLayer.MONTHLY, "乙未"),
        (ParticipantLayer.DAILY, "壬寅"),
    ])
    summary = build_period_role_summary(h, _FAV)
    assert summary.target_state is PillarState.ADVERSE  # 壬寅
    assert {r.layer for r in summary.background} == {
        ParticipantLayer.DAEWOON, ParticipantLayer.ANNUAL, ParticipantLayer.MONTHLY,
    }
    # 대운 壬辰(구신/용신)=MIXED, 월운 乙未=MIXED → 배경은 MIXED
    assert summary.background_state is BackgroundState.MIXED
    assert summary.hierarchy_summary is HierarchySummary.MIXED_ACROSS_LAYERS


def test_neutral_does_not_cancel_direction():
    """중립은 방향 증거를 상쇄하지 않는다(NEUTRAL + FAVORABLE = SUPPORT)."""
    h = _hierarchy("day", [
        (ParticipantLayer.DAEWOON, "庚申"),  # 金 한신 — NEUTRAL
        (ParticipantLayer.ANNUAL, "丙午"),  # FAVORABLE
        (ParticipantLayer.MONTHLY, "丁巳"),  # 火 희신 — FAVORABLE
        (ParticipantLayer.DAILY, "壬寅"),  # ADVERSE
    ])
    summary = build_period_role_summary(h, _FAV)
    assert summary.background_state is BackgroundState.SUPPORT
    assert summary.hierarchy_summary is (
        HierarchySummary.BACKGROUND_SUPPORT_TARGET_FRICTION
    )


def test_summary_mapping_table():
    """배경 × 대상 매핑이 규격대로다."""
    cases = [
        ("戊戌", "己丑", HierarchySummary.CONSISTENT_SUPPORT),  # SUPPORT + FAVORABLE
        ("戊戌", "壬寅", HierarchySummary.BACKGROUND_SUPPORT_TARGET_FRICTION),
        ("壬子", "己丑", HierarchySummary.BACKGROUND_PRESSURE_TARGET_RELIEF),
        ("壬子", "壬寅", HierarchySummary.CONSISTENT_PRESSURE),  # PRESSURE + ADVERSE
        ("庚申", "壬寅", HierarchySummary.NO_CLEAR_DIRECTION),  # NEUTRAL 배경
    ]
    for bg, tg, expected in cases:
        h = _hierarchy("year", [
            (ParticipantLayer.DAEWOON, bg), (ParticipantLayer.ANNUAL, tg),
        ])
        assert build_period_role_summary(h, _FAV).hierarchy_summary is expected


def test_no_background_is_no_clear_direction():
    """상위 층위가 없으면 종합 유형을 단정하지 않는다."""
    h = _hierarchy("year", [(ParticipantLayer.ANNUAL, "丙午")])
    summary = build_period_role_summary(h, _FAV)
    assert summary.background_state is BackgroundState.NONE
    assert summary.hierarchy_summary is HierarchySummary.NO_CLEAR_DIRECTION


# ── slot_status ─────────────────────────────────────────────────────────────


def test_volatility_only_is_not_no_signal():
    """충·형·해만 있는 슬롯을 '신호 없음'으로 부르지 않는다."""
    r = derive_slot_status(
        positive_total=0.0, negative_total=0.0, neutral_signal_count=0,
        volatility_signal_count=3, volatility_total=1.6,
        source=SlotStatusSource.POLARITY_V2,
    )
    assert r.status is SlotStatus.VOLATILITY_ONLY
    assert r.display_clamped is False


def test_adverse_dominant_separates_meaning_from_clamp():
    """의미 상태와 화면 clamp는 별개 축이다."""
    r = derive_slot_status(
        positive_total=26.0, negative_total=31.0, neutral_signal_count=0,
        volatility_signal_count=0, signed_signal_count=7, display_score=0,
        source=SlotStatusSource.POLARITY_V2,
    )
    assert r.status is SlotStatus.ADVERSE_DOMINANT
    assert r.display_clamped is True
    assert r.net_raw == pytest.approx(-5.0)


def test_no_signal_only_when_nothing_at_all():
    """신호가 하나도 없을 때만 NO_SIGNAL."""
    r = derive_slot_status(
        positive_total=0.0, negative_total=0.0, neutral_signal_count=0,
        volatility_signal_count=0, source=SlotStatusSource.POLARITY_V2,
    )
    assert r.status is SlotStatus.NO_SIGNAL


def test_mixed_balanced_uses_epsilon_not_threshold():
    """MIXED_BALANCED는 체감 임계값이 아니라 부동소수점 오차 수준만 본다."""
    assert derive_slot_status(
        positive_total=10.0, negative_total=10.0, neutral_signal_count=0,
        volatility_signal_count=0, source=SlotStatusSource.POLARITY_V2,
    ).status is SlotStatus.MIXED_BALANCED
    # 1.0 차이는 균형이 아니라 우세다(임의 임계값 도입 금지).
    assert derive_slot_status(
        positive_total=11.0, negative_total=10.0, neutral_signal_count=0,
        volatility_signal_count=0, source=SlotStatusSource.POLARITY_V2,
    ).status is SlotStatus.FAVORABLE_DOMINANT


def test_legacy_v1_is_not_narrative_eligible():
    """V1 부호로 계산한 상태는 사용자 서술에 쓰지 않는다."""
    legacy = derive_slot_status(
        positive_total=5.0, negative_total=1.0, neutral_signal_count=0,
        volatility_signal_count=0, source=SlotStatusSource.LEGACY_V1,
    )
    assert legacy.status is SlotStatus.FAVORABLE_DOMINANT
    assert legacy.narrative_eligible is False
    v2 = derive_slot_status(
        positive_total=5.0, negative_total=1.0, neutral_signal_count=0,
        volatility_signal_count=0, source=SlotStatusSource.POLARITY_V2,
    )
    assert v2.narrative_eligible is True


def test_has_opposing_signals_is_preserved_for_dominant_states():
    """우세와 독점은 다르다 — 상태 라벨만 주면 '전적으로 불리'로 서술된다."""
    dominant = derive_slot_status(
        positive_total=26.0, negative_total=31.0, neutral_signal_count=0,
        volatility_signal_count=0, source=SlotStatusSource.POLARITY_V2,
    )
    assert dominant.status is SlotStatus.ADVERSE_DOMINANT
    assert dominant.has_opposing_signals is True

    exclusive = derive_slot_status(
        positive_total=0.0, negative_total=31.0, neutral_signal_count=0,
        volatility_signal_count=0, source=SlotStatusSource.POLARITY_V2,
    )
    assert exclusive.status is SlotStatus.ADVERSE_DOMINANT
    assert exclusive.has_opposing_signals is False


def test_render_keeps_both_sides_of_mixed_layer(monkeypatch):
    """MIXED 층위의 천간·지지 근거가 렌더에 남는다(이번 사건의 핵심 교정)."""
    from datetime import date

    from saju_api.services.chat_service import _build_period_fortune
    from saju_engines import period_v2_config
    from saju_shared_types.birth_input import BirthInput
    from saju_shared_types.intent import (
        Domain,
        Granularity,
        IntentJson,
        QueryType,
        TimeRange,
    )

    monkeypatch.setattr(period_v2_config, "RELATION_SEMANTIC_PATCH_ENABLED", True)
    monkeypatch.setattr(period_v2_config, "PERIOD_HIERARCHY_ENABLED", True)
    birth = BirthInput(
        birth_date=date(1980, 11, 22), birth_time="09:40:00",
        birth_place_name="서울", gender="male",
    )
    intent = IntentJson(
        intent_id="i1", query_type=QueryType.FORTUNE_OVERVIEW, domain=Domain.GENERAL,
        time_range=TimeRange(type="absolute", granularity=Granularity.DAY,
                             start="2026-07-27", end="2026-07-27"),
    )
    pf = _build_period_fortune(birth, intent, date(2026, 7, 27), "daily")
    body = "\n".join(pf.hierarchy_lines)
    # 월운 乙未 — 천간은 기신, 지지는 용신. 한쪽으로 축약되면 안 된다.
    assert "乙(기신" in body and "未(용신" in body
    assert "혼합" in body
    # 배경과 대상이 분리돼 있고, 분류 코드만 단독으로 쓰이지 않는다.
    assert "배경 종합" in body and "당일 상태" in body
    assert "층별 근거를 함께 쓸 것" in body


def test_mixed_unallocated_is_not_no_signal():
    """혼재 관계만 있는 슬롯은 '신호 없음'도 '균형'도 아니다."""
    r = derive_slot_status(
        positive_total=0.0, negative_total=0.0, neutral_signal_count=0,
        volatility_signal_count=0, mixed_unallocated_signal_count=1,
        source=SlotStatusSource.POLARITY_V2,
    )
    assert r.status is SlotStatus.DIRECTION_UNRESOLVED
    assert r.has_unallocated_opposing_signals is True


def test_unallocated_flag_survives_alongside_signed_signals():
    """signed 신호와 함께 있으면 우세는 totals로 정하되 보류 사실을 남긴다."""
    r = derive_slot_status(
        positive_total=26.0, negative_total=31.0, neutral_signal_count=0,
        volatility_signal_count=0, mixed_unallocated_signal_count=2,
        source=SlotStatusSource.POLARITY_V2,
    )
    assert r.status is SlotStatus.ADVERSE_DOMINANT
    assert r.has_opposing_signals is True
    assert r.has_unallocated_opposing_signals is True


def test_cap_blocks_favorable_without_upper_support():
    """대운·세운 긍정 기여가 없으면 월·일운만으로 '유리 우세'에 들어갈 수 없다."""
    r = derive_slot_status(
        positive_total=90.0, negative_total=0.0, neutral_signal_count=0,
        volatility_signal_count=0, upper_positive_support=False,
        source=SlotStatusSource.POLARITY_V2,
    )
    assert r.raw_status is SlotStatus.FAVORABLE_DOMINANT  # 원판정 보존
    assert r.status is SlotStatus.LOCAL_FAVORABLE_ONLY  # 등급 자체를 막는다
    assert "CAP_minor_without_upper_support" in r.guard_codes
    # MIXED_BALANCED로 강등하지 않는다 — 양쪽 크기가 같다는 별개 주장이 된다.
    assert r.status is not SlotStatus.MIXED_BALANCED


def test_cap_not_applied_when_upper_support_exists():
    """상위 지지가 있으면 캡을 적용하지 않는다(2026-07-27 사례)."""
    r = derive_slot_status(
        positive_total=90.0, negative_total=0.0, neutral_signal_count=0,
        volatility_signal_count=0, upper_positive_support=True,
        source=SlotStatusSource.POLARITY_V2,
    )
    assert r.status is SlotStatus.FAVORABLE_DOMINANT
    assert r.guard_codes == []


def test_cap_is_one_directional_only():
    """이번 단계에서는 부정 방향 대칭 캡을 적용하지 않는다."""
    r = derive_slot_status(
        positive_total=0.0, negative_total=90.0, neutral_signal_count=0,
        volatility_signal_count=0, upper_positive_support=False,
        source=SlotStatusSource.POLARITY_V2,
    )
    assert r.status is SlotStatus.ADVERSE_DOMINANT  # 변경 없음
    assert r.guard_codes == []


def test_cap_does_not_touch_already_lower_grades():
    """이미 유리 우세가 아니면 점수·상태를 바꾸지 않는다."""
    for pos, neg, expected in (
        (10.0, 20.0, SlotStatus.ADVERSE_DOMINANT),
        (10.0, 10.0, SlotStatus.MIXED_BALANCED),
    ):
        r = derive_slot_status(
            positive_total=pos, negative_total=neg, neutral_signal_count=0,
            volatility_signal_count=0, upper_positive_support=False,
            source=SlotStatusSource.POLARITY_V2,
        )
        assert r.status is expected
        assert r.guard_codes == []
