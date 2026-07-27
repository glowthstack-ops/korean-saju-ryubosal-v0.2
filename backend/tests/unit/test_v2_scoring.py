"""P3-b dual-run 계약 (2026-07-27 데굴님 확정).

완료 기준: V2는 V1과 같은 raw DomainSignal을 읽되 원본을 변경하지 않고, occurrence와
effect까지 같은 실제 중복만 복사 뷰에서 제거한다. 실패 시 사용자 요청을 실패시키지
않고 V1 점수로만 복귀한다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.v2_scoring import (
    V2ActivationStatus,
    V2ScoringError,
    build_v2_scoring,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.precompute import CompositeLevel

_BIRTH = BirthInput(
    birth_date=date(1980, 11, 22), birth_time="09:40:00",
    birth_place_name="서울", gender="male", reference_date=date(2026, 7, 27),
)
_SCOPE = ("2026-07-27", "2026-07", "2026")


@pytest.fixture(scope="module")
def fixture():
    """기준 명식의 composite·hierarchy·범위 목록."""
    from saju_api.services.chat_service import _DICTS
    from saju_api.services.manse_service import calculate, luck_days
    from saju_engines.luck_hierarchy import build_luck_hierarchy
    from saju_engines.precompute import CompositeBuilder
    from saju_engines.relation_semantics import collect_luck_relation_semantics

    chart = calculate(_BIRTH)
    chart.luck_cycles.daily_luck = luck_days(_BIRTH, 2026, 7)
    comps = CompositeBuilder(_DICTS).build(
        chart, "t", "1.0.0", "x",
        levels={CompositeLevel.DAY, CompositeLevel.MONTH, CompositeLevel.YEAR},
    )
    sems = collect_luck_relation_semantics(
        chart, ["壬", "丙", "乙", "壬"], ["辰", "午", "未", "寅"]
    )
    hier = build_luck_hierarchy(
        comps, "day", "2026-07-27", sems,
        stack_keys={"month": "2026-07", "year": "2026"},
    )
    scope = [c for c in comps if c.period_key in _SCOPE]
    return comps, hier, scope


def test_v1_raw_signals_are_not_mutated(fixture):
    """V2 계산 전후로 원본 신호 수·순서·legacy weight가 모두 동일하다."""
    _, hier, scope = fixture
    before = [
        [(s.source_interaction, s.weight, s.domain) for s in c.domain_signals]
        for c in scope
    ]
    build_v2_scoring(scope, hier, enabled=True)
    after = [
        [(s.source_interaction, s.weight, s.domain) for s in c.domain_signals]
        for c in scope
    ]
    assert before == after


def test_disabled_flag_yields_disabled_status(fixture):
    """플래그 OFF면 계산하지 않고 DISABLED."""
    _, hier, scope = fixture
    result = build_v2_scoring(scope, hier, enabled=False)
    assert result.activation_status is V2ActivationStatus.DISABLED
    assert result.narrative_eligible is False
    assert result.totals == {}


def test_active_run_restores_zeroed_slots(fixture):
    """V1에서 0점이던 일·관계 슬롯이 V2에서 방향을 갖는다(이번 수정의 핵심)."""
    _, hier, scope = fixture
    result = build_v2_scoring(scope, hier, enabled=True)
    assert result.activation_status is V2ActivationStatus.ACTIVE
    assert result.narrative_eligible is True
    for category in ("work", "relationship"):
        totals = result.totals[category]
        assert totals.positive_total > 0  # 未土·火 지원이 살아난다
        assert result.slot_status[category].status.value != "NO_SIGNAL"


def test_policy_exclusions_keep_coverage_complete(fixture):
    """충·엔진충돌·혼재가 있어도 coverage는 complete다."""
    _, hier, scope = fixture
    cov = build_v2_scoring(scope, hier, enabled=True).coverage
    assert cov.structural_only_count > 0
    assert cov.engine_conflict_count > 0  # 亥未
    assert cov.mixed_unallocated_count > 0  # 丁壬 쟁합
    assert cov.unavailable_signal_count == 0
    assert cov.complete is True


def test_duplicate_removal_keeps_distinct_occurrences(fixture):
    """실제 중복만 제거하고 서로 다른 발생은 유지한다."""
    _, hier, scope = fixture
    result = build_v2_scoring(scope, hier, enabled=True)
    assert result.duplicate_removed_count > 0  # 여러 composite 경로의 실제 중복
    assert result.deduplicated_signal_count < result.raw_signal_count
    # 월지 亥/일지 亥의 寅亥合은 별개 신호이므로 둘 다 남아야 한다.
    hae = {
        tuple(sorted(s.participant_occurrence_ids or ()))
        for c in scope for s in c.domain_signals
        if s.source_interaction == "rel_寅亥合"
    }
    assert len(hae) == 2


def test_missing_magnitude_raises_v2_error(fixture):
    """무부호 강도가 없으면 V2 전용 예외 — 호출부가 V1으로 폴백한다."""
    _, hier, scope = fixture
    broken = [c.model_copy(deep=True) for c in scope]
    for comp in broken:
        for signal in comp.domain_signals:
            signal.unsigned_magnitude_v2 = None
    with pytest.raises(V2ScoringError):
        build_v2_scoring(broken, hier, enabled=True)


def test_totals_keep_magnitudes_non_negative(fixture):
    """positive/negative는 둘 다 0 이상 크기로 누적한다(음수를 더하지 않는다)."""
    _, hier, scope = fixture
    result = build_v2_scoring(scope, hier, enabled=True)
    for totals in result.totals.values():
        assert totals.positive_total >= 0
        assert totals.negative_total >= 0
    assert not result.invariant_failure_codes


def test_wired_scope_includes_target_period(monkeypatch):
    """V2 범위에 대상 기간이 포함된다 — 빠지면 일진 신호가 통째로 누락된다."""
    from saju_api.services.chat_service import _build_period_fortune
    from saju_engines import period_v2_config
    from saju_shared_types.intent import (
        Domain,
        Granularity,
        IntentJson,
        QueryType,
        TimeRange,
    )

    for flag in (
        "RELATION_SEMANTIC_PATCH_ENABLED", "PERIOD_HIERARCHY_ENABLED",
        "PILLAR_POLARITY_V2_ENABLED",
    ):
        monkeypatch.setattr(period_v2_config, flag, True)
    intent = IntentJson(
        intent_id="i1", query_type=QueryType.FORTUNE_OVERVIEW, domain=Domain.GENERAL,
        time_range=TimeRange(type="absolute", granularity=Granularity.DAY,
                             start="2026-07-27", end="2026-07-27"),
    )
    pf = _build_period_fortune(_BIRTH, intent, date(2026, 7, 27), "daily")
    body = "\n".join(pf.hierarchy_lines)
    assert "[분야별 상태" in body
    # 5개 카테고리가 모두 나온다(일진 신호가 빠지면 일부가 사라진다).
    for label in ("의사결정", "건강", "재물", "관계·연애", "일·직업"):
        assert label in body
    # 사용자 문구 후보와 서술 정책이 **분리된 섹션**으로 나간다(에코 방지).
    assert "[서술 정책" in body
    assert "문구 후보:" in body
    # 변동성만 있는 슬롯을 '신호 없음'으로 서술하지 못하게 막는다(정책 섹션).
    assert "'관련 신호가 없다'로 서술 금지" in body
    # 우세와 독점을 구분하는 단서가 함께 나간다.
    assert "전적으로 불리·유리'로 단정 금지" in body
    # 정책 문장은 지시 영역에만 있고 문구 후보 줄에는 섞이지 않는다.
    hint_lines = [ln for ln in pf.hierarchy_lines if "문구 후보:" in ln]
    assert hint_lines
    assert all("금지" not in ln for ln in hint_lines)


def test_v2_lines_absent_when_polarity_flag_off(monkeypatch):
    """polarity V2가 꺼져 있으면 slot_status가 사용자 입력에 나가지 않는다."""
    from saju_api.services.chat_service import _build_period_fortune
    from saju_engines import period_v2_config
    from saju_shared_types.intent import (
        Domain,
        Granularity,
        IntentJson,
        QueryType,
        TimeRange,
    )

    monkeypatch.setattr(period_v2_config, "RELATION_SEMANTIC_PATCH_ENABLED", True)
    monkeypatch.setattr(period_v2_config, "PERIOD_HIERARCHY_ENABLED", True)
    monkeypatch.setattr(period_v2_config, "PILLAR_POLARITY_V2_ENABLED", False)
    intent = IntentJson(
        intent_id="i1", query_type=QueryType.FORTUNE_OVERVIEW, domain=Domain.GENERAL,
        time_range=TimeRange(type="absolute", granularity=Granularity.DAY,
                             start="2026-07-27", end="2026-07-27"),
    )
    pf = _build_period_fortune(_BIRTH, intent, date(2026, 7, 27), "daily")
    body = "\n".join(pf.hierarchy_lines)
    assert "[분야별 상태" not in body  # hierarchy 설명은 유지, 점수만 미노출
    assert "[상위 운 결합" in body


def test_upper_support_uses_same_category_contribution(fixture):
    """상위 지지는 최종 라벨이 아니라 같은 카테고리의 실제 긍정 기여로 판정한다."""
    _, hier, scope = fixture
    result = build_v2_scoring(scope, hier, enabled=True)
    for category, totals in result.totals.items():
        support = totals.upper_positive_support
        expected = any(
            totals.positive_by_level.get(lv, 0.0) > 0 for lv in ("daewoon", "year")
        )
        assert support is expected
        # 다른 카테고리의 상위 지지를 빌려오지 않는다.
        assert result.slot_status[category].upper_positive_support is support


def test_reference_case_keeps_favorable_because_annual_supports(fixture):
    """2026-07-27은 세운 丙午의 긍정 기여가 있어 캡이 걸리지 않는다."""
    _, hier, scope = fixture
    result = build_v2_scoring(scope, hier, enabled=True)
    work = result.slot_status["work"]
    assert work.upper_positive_support is True
    assert work.guard_codes == []
    assert work.status.value == "FAVORABLE_DOMINANT"


def test_negative_by_level_mirrors_positive(fixture):
    """부정 기여도 층위별로 분해해 shadow 판정 근거를 남긴다."""
    _, hier, scope = fixture
    result = build_v2_scoring(scope, hier, enabled=True)
    for category, totals in result.totals.items():
        expected = any(
            totals.negative_by_level.get(lv, 0.0) > 0 for lv in ("daewoon", "year")
        )
        assert totals.upper_negative_support is expected
        assert result.slot_status[category].upper_negative_support is expected
        # 층위 합은 총합과 일치해야 한다(누락 없음).
        assert sum(totals.negative_by_level.values()) == pytest.approx(
            totals.negative_total, abs=1e-6
        )
        assert sum(totals.positive_by_level.values()) == pytest.approx(
            totals.positive_total, abs=1e-6
        )
