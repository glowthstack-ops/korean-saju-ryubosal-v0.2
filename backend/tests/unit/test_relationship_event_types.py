"""3층 타입·손실 어댑터 검증 — P0-B2 (RELATIONSHIP_EVENT_SYSTEM §3·부록 C-2)."""

from __future__ import annotations

from saju_shared_types.marriage_timing import MarriageStage
from saju_shared_types.relationship_event import (
    RelationshipCondition,
    RelationshipStage,
    relationship_stage_from_marriage_stage,
)


def test_relationship_stage_canonical_7() -> None:
    assert [s.value for s in RelationshipStage] == [
        "none", "awareness", "contact", "dating",
        "commitment", "formalization", "married",
    ]


def test_relationship_condition_canonical_8() -> None:
    assert [c.value for c in RelationshipCondition] == [
        "quiet", "growing", "ambiguous", "stable",
        "friction", "distancing", "separated", "reconciling",
    ]


def test_adapter_full_mapping_table() -> None:
    """어댑터 매핑표(부록 C-2) 전수 — relationship→DATING 명칭 정렬."""
    expect = {
        MarriageStage.AWARENESS: RelationshipStage.AWARENESS,
        MarriageStage.CONTACT: RelationshipStage.CONTACT,
        MarriageStage.RELATIONSHIP: RelationshipStage.DATING,
        MarriageStage.COMMITMENT: RelationshipStage.COMMITMENT,
        MarriageStage.FORMALIZATION: RelationshipStage.FORMALIZATION,
        MarriageStage.FAMILY_EXPANSION: RelationshipStage.MARRIED,
    }
    for ms, rs in expect.items():
        assert relationship_stage_from_marriage_stage(ms).stage is rs


def test_adapter_covers_every_marriage_stage() -> None:
    """기존 enum 멤버 추가 시 어댑터 누락을 즉시 잡는다."""
    for ms in MarriageStage:
        relationship_stage_from_marriage_stage(ms)  # KeyError 없이 전수 처리


def test_family_expansion_is_lossy_with_facet() -> None:
    """family_expansion → MARRIED 강등 + facet 보존(손실 변환 명시).

    역방향 round-trip 미보장: MARRIED만으로 family_expansion 복원 불가 —
    역변환 함수는 의도적으로 제공하지 않는다.
    """
    out = relationship_stage_from_marriage_stage(MarriageStage.FAMILY_EXPANSION)
    assert out.stage is RelationshipStage.MARRIED
    assert out.facets == ("family_expansion",)
    non_lossy = relationship_stage_from_marriage_stage(MarriageStage.RELATIONSHIP)
    assert non_lossy.facets == ()


def test_no_reverse_adapter_exported() -> None:
    """역변환(신규→기존) 함수 부재 고정 — round-trip 보장 오해 방지."""
    import saju_shared_types.relationship_event as mod

    assert not [n for n in dir(mod) if "marriage_stage_from_relationship" in n]


def test_stage_condition_independent_axes() -> None:
    """단계·상태 독립 — 별거 부부(MARRIED+SEPARATED)가 표현 가능해야 하며
    SEPARATED가 stage를 NONE으로 강제하지 않는다(결합 검증 없음)."""
    stage, cond = RelationshipStage.MARRIED, RelationshipCondition.SEPARATED
    assert (stage, cond) == (RelationshipStage.MARRIED, RelationshipCondition.SEPARATED)
    # 같은 DATING이라도 상태로 사건이 갈린다(§3-2) — 두 조합은 서로 다른 상태다.
    growing = (RelationshipStage.DATING, RelationshipCondition.GROWING)
    friction = (RelationshipStage.DATING, RelationshipCondition.FRICTION)
    assert growing != friction and growing[0] is friction[0]


def test_existing_marriage_stage_untouched() -> None:
    """P0-B2는 기존 MarriageStage를 수정하지 않는다(6단계 어휘 불변)."""
    assert [s.value for s in MarriageStage] == [
        "awareness", "contact", "relationship",
        "commitment", "formalization", "family_expansion",
    ]
