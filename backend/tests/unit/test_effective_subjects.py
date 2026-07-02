"""대상 조합 계산(P1 — 계산/실행 분리).

P0가 해소한 대상 + FE 칩 동반자를 병합해 effective_subjects/mode/injection을 산출하되,
실행(per_subject)은 바꾸지 않는 shadow 단계임을 검증한다. injection.execution_enabled은
항상 False여야 하고, planner.per_subject는 이 계산에 영향받지 않아야 한다(기존 스냅샷 불변).
"""

from __future__ import annotations

from saju_engines.companion_alias import AliasEntry
from saju_engines.effective_subjects import AttachedCompanion, build_effective_subjects
from saju_engines.planner import build_execution_plan
from saju_shared_types.intent import (
    IntentJson,
    QueryType,
    SubjectKind,
    SubjectMode,
    SubjectRef,
)


def _self() -> SubjectRef:
    return SubjectRef(kind=SubjectKind.SELF, label="본인")


def _comp(cid: str, label: str) -> SubjectRef:
    return SubjectRef(kind=SubjectKind.COMPANION, label=label, companion_id=cid)


def test_self_only() -> None:
    """동반자 없음 → self_only, 동반자 명식 불요."""
    eff, mode, inj = build_effective_subjects([_self()], SubjectMode.SINGLE, base_subject_id="s1")
    assert mode == "self_only"
    assert [e.role for e in eff] == ["self"]
    assert inj.requires_companion_chart is False
    assert inj.execution_enabled is False


def test_pairwise_self_plus_one() -> None:
    """본인 + 동반자 1명 → pairwise, 관계 맥락 필요, 실행 미전환."""
    eff, mode, inj = build_effective_subjects(
        [_self(), _comp("c1", "지민")], SubjectMode.SINGLE, base_subject_id="s1",
        companion_meta={"c1": AliasEntry("c1", "지민", "spouse", "relation_synonym")},
    )
    assert mode == "pairwise"
    assert inj.primary_subject_id == "s1"
    assert inj.companion_subject_ids == ["c1"]
    assert inj.requires_companion_chart is True
    assert inj.requires_relationship_context is True
    assert inj.execution_enabled is False
    comp = next(e for e in eff if e.role == "companion")
    assert comp.relation_to_user == "spouse"


def test_companion_only() -> None:
    """동반자 1명만(본인 없음) → companion_only, primary=그 동반자."""
    eff, mode, inj = build_effective_subjects(
        [_comp("c2", "김여사")], SubjectMode.SINGLE, base_subject_id="s1",
    )
    assert mode == "companion_only"
    assert inj.primary_subject_id == "c2"
    assert [e.role for e in eff] == ["companion"]


def test_compare_exclude_self() -> None:
    """동반자 2명(본인 없음) → compare_exclude_self, target에 self 미포함."""
    _eff, mode, inj = build_effective_subjects(
        [_comp("c1", "형"), _comp("c2", "동생")], SubjectMode.SINGLE, base_subject_id="s1",
    )
    assert mode == "compare_exclude_self"
    assert set(inj.target_subject_ids) == {"c1", "c2"}
    assert "s1" not in inj.target_subject_ids


def test_multi_with_self() -> None:
    """본인 + 동반자 2명 → multi_with_self."""
    _eff, mode, _inj = build_effective_subjects(
        [_self(), _comp("c1", "형"), _comp("c2", "동생")], SubjectMode.SINGLE, base_subject_id="s1",
    )
    assert mode == "multi_with_self"


def test_chip_partner_merged_without_text() -> None:
    """텍스트에 동반자 없어도 FE 칩 partner가 병합돼 pairwise."""
    eff, mode, inj = build_effective_subjects(
        [_self()], SubjectMode.SINGLE, base_subject_id="s1",
        attached=[AttachedCompanion(subject_id="c9", label="상대", relation_to_user="spouse")],
    )
    assert mode == "pairwise"
    assert "c9" in inj.companion_subject_ids
    assert next(e for e in eff if e.role == "companion").source == "chip"


def test_dedup_text_and_chip_same_subject() -> None:
    """같은 동반자를 텍스트+칩으로 모두 지칭해도 중복 제거(1명)."""
    eff, mode, _inj = build_effective_subjects(
        [_self(), _comp("c1", "지민")], SubjectMode.SINGLE, base_subject_id="s1",
        attached=[AttachedCompanion(subject_id="c1", label="지민")],
    )
    assert mode == "pairwise"
    assert [e.subject_id for e in eff] == ["s1", "c1"]


def test_pairwise_mode_implies_self_even_if_not_listed() -> None:
    """'궁합'(PAIRWISE)은 self를 subjects에 안 넣어도 pairwise로 판정하고 self를 삽입한다.

    resolve_subjects가 '엄마랑 궁합'을 subjects=[동반자]+mode=PAIRWISE로 주는 케이스 —
    구성만 보면 companion_only로 오판해 base가 동반자로 잘못 교체되던 결함 방지.
    """
    eff, mode, inj = build_effective_subjects(
        [_comp("c1", "엄마")], SubjectMode.PAIRWISE, base_subject_id="s1",
    )
    assert mode == "pairwise"
    assert any(e.role == "self" for e in eff)
    assert inj.primary_subject_id == "s1"


def test_pairwise_enum_with_two_companions_is_compare_not_pairwise() -> None:
    """PAIRWISE(궁합)라도 동반자 2명·본인 미포함이면 pairwise가 아니라 compare_exclude_self.

    '엄마랑 아빠 궁합'이 self를 잘못 삽입해 pairwise로 오판하던 결함 방지(P3b 전제).
    """
    eff, mode, inj = build_effective_subjects(
        [_comp("c1", "엄마"), _comp("c2", "아빠")], SubjectMode.PAIRWISE, base_subject_id="s1",
    )
    assert mode == "compare_exclude_self"
    assert not any(e.role == "self" for e in eff)
    assert set(inj.companion_subject_ids) == {"c1", "c2"}


def test_injection_never_enabled_in_p1() -> None:
    """P1 불변식 — 어떤 조합에서도 execution_enabled=False(실행 전환은 P2)."""
    for subs in (
        [_self()],
        [_self(), _comp("c1", "지민")],
        [_comp("c2", "엄마")],
        [_comp("c1", "형"), _comp("c2", "동생")],
    ):
        _e, _m, inj = build_effective_subjects(subs, SubjectMode.SINGLE, base_subject_id="s1")
        assert inj.execution_enabled is False


def test_planner_per_subject_unaffected() -> None:
    """계산/실행 분리 — effective_subjects 계산은 planner.per_subject 산출을 바꾸지 않는다.

    per_subject는 기존대로 intent.subject_mode/len(subjects)에서만 결정된다.
    """
    single = IntentJson(intent_id="i1", query_type=QueryType.DOMAIN_ANALYSIS)
    assert build_execution_plan(single).per_subject is False

    multi = IntentJson(
        intent_id="i2", query_type=QueryType.COMPARISON,
        subject_mode=SubjectMode.PAIRWISE,
        subjects=[_self(), _comp("c1", "지민")],
    )
    assert build_execution_plan(multi).per_subject is True
