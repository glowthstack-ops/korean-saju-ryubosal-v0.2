"""P1 계층형 grounding 불변식 — 2026-07-27 일운 회귀 고정.

배경: 기존 grounding은 일진과 원국의 1:1 관계만 렌더해, 상위 운이 만드는 결합
(巳午未 방합 火 · 寅午 반합 火)과 층간 충(丙壬충)을 통째로 누락했다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.luck_hierarchy import build_luck_hierarchy
from saju_engines.relation_semantics import collect_luck_relation_semantics
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.luck_hierarchy import (
    ParticipantLayer,
    SemanticResolutionStatus,
    normalize_participant_layer,
)
from saju_shared_types.precompute import CompositeLevel

_BIRTH = BirthInput(
    birth_date=date(1980, 11, 22), birth_time="09:40:00",
    birth_place_name="서울", gender="male", reference_date=date(2026, 7, 27),
)
_STACK = {"month": "2026-07", "year": "2026"}


@pytest.fixture(scope="module")
def hierarchy():
    """2026-07-27 일운의 계층형 grounding."""
    from saju_api.services.chat_service import _DICTS
    from saju_api.services.manse_service import calculate, luck_days
    from saju_engines.precompute import CompositeBuilder

    chart = calculate(_BIRTH)
    chart.luck_cycles.daily_luck = luck_days(_BIRTH, 2026, 7)
    comps = CompositeBuilder(_DICTS).build(
        chart, "chat", "1.0.0", "2026-07-27T00:00:00+00:00",
        levels={CompositeLevel.DAY, CompositeLevel.MONTH,
                CompositeLevel.YEAR, CompositeLevel.NATAL},
    )
    sems = collect_luck_relation_semantics(
        chart, ["壬", "丙", "乙", "壬"], ["辰", "午", "未", "寅"]
    )
    return build_luck_hierarchy(comps, "day", "2026-07-27", sems, stack_keys=_STACK), sems


def _ids(h):
    return [i.interaction_id for i in h.interactions]


def test_upper_layer_combination_is_present(hierarchy):
    """일진이 참여하지 않는 상위 결합도 포함된다 — 이번 사고의 직접 원인."""
    h, _ = hierarchy
    assert "rel_巳午未方合" in _ids(h)  # 원국 시지 巳 + 세운 午 + 월운 未 (월운 composite)
    assert "rel_寅午戌三合" in _ids(h)  # 일진 寅 + 세운 午 (반합)
    assert "rel_丙壬沖" in _ids(h)  # 층간 충


def test_cross_layer_flag(hierarchy):
    """운 층위가 둘 이상 참여한 관계는 층간으로 표시된다."""
    h, _ = hierarchy
    banghap = next(i for i in h.interactions if i.interaction_id == "rel_巳午未方合")
    assert banghap.crosses_luck_layers
    layers = {p.layer for p in banghap.participants}
    assert ParticipantLayer.ANNUAL in layers and ParticipantLayer.MONTHLY in layers
    assert ParticipantLayer.NATAL_HOUR in layers  # 원국 시지 巳


def test_meaning_is_copied_from_p0_not_recomputed(hierarchy):
    """P1은 의미를 재계산하지 않는다 — P0 값과 완전히 같아야 한다."""
    h, sems = hierarchy
    by_label = {s.relation_label: s for s in sems}
    for inter in h.interactions:
        if not inter.relation_label:
            continue
        sem = by_label[inter.relation_label]
        assert inter.canonical_claim == sem.canonical_claim
        assert inter.formation_state is sem.formation_state
        assert inter.transformation_state is sem.transformation_state
        assert inter.binding_state is sem.binding_state
        assert inter.result_element == sem.transform_element
        assert [e.model_dump() for e in inter.effects] == [
            e.model_dump() for e in sem.effects
        ]


def test_scope_is_limited_to_requested_stack(hierarchy):
    """운 participant는 요청 스택 층위에만 속한다(인접 연도 유입 0건)."""
    h, _ = hierarchy
    allowed = {
        ParticipantLayer.DAEWOON, ParticipantLayer.ANNUAL,
        ParticipantLayer.MONTHLY, ParticipantLayer.DAILY,
    }
    for inter in h.interactions:
        for p in inter.participants:
            assert p.layer.is_natal or p.layer in allowed


def test_natal_occurrences_are_distinct(hierarchy):
    """월지 亥와 일지 亥는 별도 발생으로 보존된다."""
    h, _ = hierarchy
    hae = [i for i in h.interactions if i.interaction_id == "rel_寅亥合"]
    layers = {p.layer for i in hae for p in i.participants if p.char == "亥"}
    assert {ParticipantLayer.NATAL_MONTH, ParticipantLayer.NATAL_DAY} <= layers


def test_cluster_references_ids_only_and_preserves_originals(hierarchy):
    """클러스터는 표현 뷰다 — ID만 참조하고 원본 관계를 지우지 않는다."""
    h, _ = hierarchy
    fire = next(c for c in h.clusters if c.result_element == "火")
    assert fire.primary_interaction_id == "rel_巳午未方合"  # 완성 방합이 대표
    assert "rel_寅午戌三合" in fire.supporting_interaction_ids  # 반합은 보조
    for mid in fire.member_ids:
        assert h.by_id(mid) is not None  # 원본 보존
    assert h.interaction_summary.total_interactions == len(h.interactions)


def test_cluster_does_not_mix_result_elements(hierarchy):
    """결과 오행이 다르면 참여가 겹쳐도 같은 클러스터에 넣지 않는다."""
    h, _ = hierarchy
    for c in h.clusters:
        for mid in c.member_ids:
            assert h.by_id(mid).result_element == c.result_element


def test_binding_relations_are_not_clustered_as_strengthening(hierarchy):
    """묶임(합거) 관계는 강화 클러스터에 들어가지 않는다.

    午未合은 火가 결과 오행이지만 엔진 판정은 합반·합거(丁·己 이로운 작용 묶임)다.
    결과 오행만 같다고 火 강화 클러스터에 넣으면 의미가 뒤집힌다.
    """
    h, _ = hierarchy
    fire = next(c for c in h.clusters if c.result_element == "火")
    assert "rel_午未合" not in fire.member_ids


def test_engine_conflict_is_preserved_but_excluded(hierarchy):
    """탐지기는 성립, 의미 판정기는 미성립인 관계는 보존하되 사용하지 않는다.

    亥未는 InteractionDetector가 rel_卯未亥三合으로 감지하지만 resolve_branch_hap은
    '반합은 왕지 포함만'이라 미성립으로 본다. 의미 미상으로 흘려보내면 LLM이 자체
    지식으로 '亥未는 木 반합'이라 채운다.
    """
    h, _ = hierarchy
    conflict = next(i for i in h.interactions if i.interaction_id == "rel_卯未亥三合")
    assert conflict.semantic_resolution_status is SemanticResolutionStatus.ENGINE_CONFLICT
    assert conflict.formation_confirmed is False  # 성립 자체가 미확정
    assert conflict.narrative_eligible is False
    assert conflict.cluster_eligible is False
    assert conflict.score_eligible is False
    assert conflict.canonical_claim == ""
    assert conflict.exclusion_reason  # 감사·telemetry용 사유 보존


def test_clash_is_narratable_but_not_scored(hierarchy):
    """충·형·해는 성립 확정이라 서술은 되지만 길흉 부호는 이번 릴리즈에서 미판정."""
    h, _ = hierarchy
    clash = next(i for i in h.interactions if i.interaction_id == "rel_丙壬沖")
    assert clash.semantic_resolution_status is SemanticResolutionStatus.STRUCTURAL_ONLY
    assert clash.formation_confirmed is True  # 엔진 불일치와 다르다
    assert clash.narrative_eligible is True  # 층간 긴장은 서술한다
    assert clash.score_eligible is False
    assert clash.cluster_eligible is False


def test_engine_conflict_never_enters_clusters(hierarchy):
    """엔진 불일치 관계는 어떤 클러스터에도 들어가지 않는다."""
    h, _ = hierarchy
    conflicted = {
        i.interaction_id for i in h.interactions
        if i.semantic_resolution_status is SemanticResolutionStatus.ENGINE_CONFLICT
    }
    for c in h.clusters:
        assert not conflicted & set(c.member_ids)


def test_same_label_different_occurrence_is_not_deduped(hierarchy):
    """라벨이 같아도 참여 발생이 다르면 별개 관계로 남는다."""
    h, _ = hierarchy
    hae = [i for i in h.interactions if i.interaction_id == "rel_寅亥合"]
    assert len(hae) == 2  # 원국 월지 亥 / 일지 亥
    assert hae[0].occurrence_ids != hae[1].occurrence_ids


def test_unknown_source_is_fail_closed():
    """알 수 없는 source는 임의 층위로 바꾸지 않는다."""
    assert normalize_participant_layer("year") is ParticipantLayer.ANNUAL
    assert normalize_participant_layer("luck") is None
    assert normalize_participant_layer("") is None


def test_cluster_id_is_stable_across_input_order(hierarchy):
    """같은 입력이면 클러스터 정의 ID가 동일하다(날짜 미포함)."""
    h, _ = hierarchy
    fire = next(c for c in h.clusters if c.result_element == "火")
    assert "2026" not in fire.cluster_definition_id
    assert fire.cluster_definition_id.startswith("火:")


def test_flag_off_keeps_legacy_relation_lines(monkeypatch):
    """플래그 OFF면 기존 형충회합 렌더가 그대로다(출력 불변)."""
    from saju_api.services.chat_service import _build_period_fortune
    from saju_engines import period_v2_config
    from saju_shared_types.intent import (
        Domain,
        Granularity,
        IntentJson,
        QueryType,
        TimeRange,
    )

    monkeypatch.setattr(period_v2_config, "PERIOD_HIERARCHY_ENABLED", False)
    intent = IntentJson(
        intent_id="i1", query_type=QueryType.FORTUNE_OVERVIEW, domain=Domain.GENERAL,
        time_range=TimeRange(type="absolute", granularity=Granularity.DAY,
                             start="2026-07-27", end="2026-07-27"),
    )
    pf = _build_period_fortune(_BIRTH, intent, date(2026, 7, 27), "daily")
    assert pf.relation_lines  # 기존 경로 유지
    assert pf.hierarchy_lines == []
    assert pf.luck_hierarchy is None


def test_flag_on_replaces_relation_lines_without_duplication(monkeypatch):
    """플래그 ON이면 관계는 계층형 하나만 — 기존 형충회합과 동시 노출 금지."""
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
    intent = IntentJson(
        intent_id="i1", query_type=QueryType.FORTUNE_OVERVIEW, domain=Domain.GENERAL,
        time_range=TimeRange(type="absolute", granularity=Granularity.DAY,
                             start="2026-07-27", end="2026-07-27"),
    )
    pf = _build_period_fortune(_BIRTH, intent, date(2026, 7, 27), "daily")
    assert pf.hierarchy_lines
    assert pf.relation_lines == []  # 중복 삽입 없음
    assert pf.luck_hierarchy is not None  # 감사 SSOT 보존

    body = "\n".join(pf.hierarchy_lines)
    # 사고에서 누락됐던 상위 지원과 완화 신호가 본문에 남는다.
    assert "巳午未방합" in body
    assert "寅午반합" in body
    assert "寅亥合" in body and "완화" in body
    assert "丙壬沖" in body  # 층간 마찰
    # 엔진 불일치 관계는 본문·부록 어디에도 없다.
    assert "卯未亥" not in body
    assert "卯未亥" not in "\n".join(pf.hierarchy_appendix)
    # 같은 발생이 본문에 두 번 나오지 않는다.
    supports = [ln for ln in pf.hierarchy_lines if ln.startswith("지원: ")]
    assert len(supports) == len({ln for ln in supports})


def test_render_axis_respects_favorability_not_just_effect(hierarchy):
    """축 분류는 구조적 효과가 아니라 길흉 방향까지 본다.

    기신 오행 강화를 '지원'으로, 이로운 글자가 묶이는 손실을 '완화'로 부르면
    사용자 의미에서 정반대가 된다(2026-07-27 렌더 결함).
    """
    from saju_engines.luck_hierarchy_render import _axis

    h, _ = hierarchy
    axis = {i.interaction_id: _axis(i) for i in h.interactions
            if i.can_render_narrative()}
    assert axis["rel_巳午未方合"] == "favorable_activation"  # 火 = 희신
    assert axis["rel_寅卯辰方合"] == "adverse_activation"  # 木 = 기신 강화
    assert axis["rel_寅亥合"] == "mitigation"  # 壬·甲 흉 제거
    assert axis["rel_午未合"] == "loss"  # 丁 희신·己 용신이 묶임
    assert axis["rel_丁壬合"] == "mixed_binding"  # 쟁합 — 壬 boon + 丁 harm
    assert axis["rel_丙壬沖"] == "structural_tension"


def test_render_does_not_merge_different_axes(hierarchy):
    """서로 다른 축의 관계는 한 문장에 결합되지 않는다."""
    from saju_engines.luck_hierarchy_render import AXIS_LABEL, render_hierarchy_narrative

    h, _ = hierarchy
    lines = render_hierarchy_narrative(h)
    mitigation = [ln for ln in lines if ln.startswith(AXIS_LABEL["mitigation"])]
    assert mitigation
    for ln in mitigation:
        assert "丁壬合" not in ln  # 혼재 관계가 완화 문장에 섞이지 않는다


def test_partial_formation_label_keeps_partial_marker(hierarchy):
    """축약 라벨이 성립 수준을 왜곡하지 않는다(부분 방합을 완성처럼 쓰지 않음)."""
    from saju_engines.luck_hierarchy_render import _name

    h, _ = hierarchy
    banghap = next(i for i in h.interactions if i.interaction_id == "rel_寅卯辰方合")
    assert "부분" in _name(banghap)


def test_render_axis_and_score_polarity_share_one_classifier(hierarchy):
    """P1 렌더 축과 P3 점수 부호가 같은 분류기에서 나온다(drift 차단).

    분류기를 둘로 만들면 화면 설명과 점수가 다른 규칙으로 갈라진다.
    """
    from saju_engines.luck_hierarchy_render import _axis
    from saju_engines.signal_polarity import classify_relation_polarity
    from saju_shared_types.relation_semantics import PolarityState

    h, _ = hierarchy
    expected = {
        PolarityState.POSITIVE: {"favorable_activation", "mitigation"},
        PolarityState.NEGATIVE: {"adverse_activation", "loss"},
        PolarityState.MIXED: {"mixed_binding"},
        PolarityState.NEUTRAL: {"neutral_activation"},
        PolarityState.UNRESOLVED: {"structural_tension", "neutral_activation"},
    }
    for inter in h.interactions:
        if not inter.can_render_narrative():
            continue
        decision = classify_relation_polarity(inter)
        assert _axis(inter) in expected[decision.polarity_state]


def test_mixed_relation_is_not_forced_into_a_sign(hierarchy):
    """혼재 관계에 단일 부호를 강제하지 않는다 — signed score 미반영."""
    from saju_engines.signal_polarity import (
        ScoreExclusionReason,
        classify_relation_polarity,
    )
    from saju_shared_types.relation_semantics import PolarityState

    h, _ = hierarchy
    jung_im = next(i for i in h.interactions if i.interaction_id == "rel_丁壬合")
    decision = classify_relation_polarity(jung_im)  # 쟁합 — 壬 boon + 丁 harm
    assert decision.polarity_state is PolarityState.MIXED
    assert decision.score_polarity == 0
    assert decision.score_eligible is False
    assert decision.exclusion_reason is ScoreExclusionReason.MIXED_UNALLOCATED
    assert decision.exclusion_reason.is_coverage_failure is False


def test_structural_and_conflict_are_not_scored(hierarchy):
    """충·형·해와 엔진 불일치는 점수에 반영되지 않는다."""
    from saju_engines.signal_polarity import classify_relation_polarity

    h, _ = hierarchy
    from saju_engines.signal_polarity import ScoreExclusionReason

    expected = {
        # 충 — 성립 확정, 길흉 규칙만 미정. 서술과 변동성에는 남는다.
        "rel_丙壬沖": (ScoreExclusionReason.STRUCTURAL_ONLY, True, "structural_tension"),
        # 엔진 불일치 — 성립 자체가 미확정. 변동성도 반영 금지.
        "rel_卯未亥三合": (ScoreExclusionReason.ENGINE_CONFLICT, False, None),
    }
    for rid, (reason, volatility, axis) in expected.items():
        inter = next(i for i in h.interactions if i.interaction_id == rid)
        decision = classify_relation_polarity(inter)
        assert decision.score_eligible is False
        assert decision.score_polarity == 0
        assert decision.exclusion_reason is reason
        assert decision.volatility_eligible is volatility
        # 정상 제외는 coverage 실패가 아니다.
        assert decision.exclusion_reason.is_coverage_failure is False
        if axis:
            assert decision.narrative_axis == axis


def test_favorable_and_adverse_activation_get_signs(hierarchy):
    """결과 오행의 역할이 부호를 정한다(운주 라벨 상속 아님)."""
    from saju_engines.signal_polarity import classify_relation_polarity

    h, _ = hierarchy
    fire = next(i for i in h.interactions if i.interaction_id == "rel_巳午未方合")
    wood = next(i for i in h.interactions if i.interaction_id == "rel_寅卯辰方合")
    assert classify_relation_polarity(fire).score_polarity == 1  # 火 = 희신
    assert classify_relation_polarity(wood).score_polarity == -1  # 木 = 기신
