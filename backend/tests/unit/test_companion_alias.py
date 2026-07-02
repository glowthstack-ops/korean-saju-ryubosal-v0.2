"""동반자 별칭 해소(P0) — 등록 레지스트리 기반 대상 지칭 → subject_id.

docs/03 A0/A9. 별명·관계어·별칭을 등록 동반자로 안정 해소하고, 복수 후보/미등록은
임의 추정 없이 확인 질문(unresolved)으로 넘기는지 검증한다(사용자 수용 기준 8종).
"""

from __future__ import annotations

from saju_engines.companion_alias import AliasEntry, build_companion_alias_index
from saju_engines.conversation import ConversationEngine
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.conversation import ConversationState
from saju_shared_types.intent import SubjectKind, SubjectMode
from saju_shared_types.subject import SubjectRecord


def _rec(
    sid: str, label: str, rel: str | None = None,
    aliases: list[str] | None = None, kind: str = "companion",
) -> SubjectRecord:
    return SubjectRecord(
        subject_id=sid, owner_id="u1", kind=kind, label=label,
        aliases=aliases or [], relation_to_user=rel,
        birth=BirthInput(birth_date="1990-01-01", birth_place_name="서울"),
    )


def _resolve(records: list[SubjectRecord], text: str, base: str = "self1"):
    idx = build_companion_alias_index(records, base_subject_id=base)
    eng = ConversationEngine(alias_index=idx)
    return eng.resolve_subjects(ConversationState(thread_id="t"), text)


_SELF = _rec("self1", "나", kind="self")


def test_label_reference_resolves() -> None:
    """별명 직접 지칭 → 해당 companion 해소."""
    res = _resolve([_SELF, _rec("c1", "지민", rel="spouse")], "지민이랑 봐줘")
    assert [(s.kind, s.companion_id) for s in res.subjects] == [
        (SubjectKind.COMPANION, "c1")
    ]
    assert not res.unresolved


def test_relation_synonym_resolves_and_pairwise() -> None:
    """관계어 동의어('와이프')→배우자 해소 + '궁합'이면 pairwise 모드."""
    res = _resolve([_SELF, _rec("c1", "지민", rel="spouse")], "우리 와이프랑 궁합 봐줘")
    assert res.subjects[0].companion_id == "c1"
    assert res.subject_mode is SubjectMode.PAIRWISE


def test_relation_word_only_resolves() -> None:
    """관계어 단독('엄마 사주만') → 해당 companion 해소."""
    res = _resolve([_SELF, _rec("c2", "김여사", rel="mother")], "엄마 사주만 봐줘")
    assert res.subjects[0].companion_id == "c2"


def test_ambiguous_relation_not_auto_resolved() -> None:
    """같은 관계어에 복수 등록(아들 2명) → 자동 해소 금지, 확인 대상."""
    res = _resolve(
        [_SELF, _rec("c3", "큰아이", rel="son"), _rec("c4", "작은아이", rel="son")],
        "아들 사주 봐줘",
    )
    assert not res.subjects
    assert "아들" in res.unresolved


def test_unregistered_relation_asks_clarification() -> None:
    """미등록 관계어('와이프' 배우자 미등록) → 임의 추정 금지, 확인 질문."""
    res = _resolve([_SELF, _rec("c2", "김여사", rel="mother")], "와이프랑 봐줘")
    assert not res.subjects
    assert "와이프" in res.unresolved


def test_self_only_unchanged() -> None:
    """본인 단독 질문은 기존대로 self, 확인 대상 없음."""
    res = _resolve([_SELF, _rec("c1", "지민", rel="spouse")], "내 올해 운 봐줘")
    assert res.subjects[0].kind is SubjectKind.SELF
    assert not res.unresolved


def test_subject_particle_not_false_positive() -> None:
    """일반 주격('엄마가 보라고')은 대상 지칭이 아니므로 확인 대상 아님(오탐 방지)."""
    res = _resolve([_SELF], "엄마가 보라고 해서 내 취업운 봐줘")
    assert res.subjects[0].kind is SubjectKind.SELF
    assert not res.unresolved


def test_owner_isolation_no_other_companions() -> None:
    """등록 동반자가 없으면(다른 owner 미포함) 별명이 있어도 self — 인덱스 비어 있음."""
    res = _resolve([_SELF], "지민이랑 봐줘")
    assert res.subjects[0].kind is SubjectKind.SELF


def test_index_excludes_self_and_short_alias() -> None:
    """인덱스는 self/base 제외 + 1글자 별칭(과매칭 위험) 제외."""
    idx = build_companion_alias_index(
        [_SELF, _rec("c1", "수", rel="son"), _rec("c2", "지민", rel="spouse")],
        base_subject_id="self1",
    )
    assert "나" not in idx  # self label 제외
    assert "수" not in idx  # 1글자 라벨 제외
    assert "지민" in idx and idx["지민"][0].subject_id == "c2"


def test_legacy_aliases_still_supported() -> None:
    """레거시 aliases=dict(별칭→id) 계약 유지(E14 학습분·기존 테스트 호환)."""
    eng = ConversationEngine(aliases={"1호": "c-son"})
    res = eng.resolve_subjects(ConversationState(thread_id="t"), "1호 사주 봐줘")
    assert res.subjects[0].companion_id == "c-son"


def test_alias_entry_metadata_preserved() -> None:
    """alias index는 subject_id뿐 아니라 label·relation·source 메타를 보존(모호성 설명용)."""
    idx = build_companion_alias_index(
        [_SELF, _rec("c1", "지민", rel="spouse")], base_subject_id="self1"
    )
    entry = idx["와이프"][0]
    assert isinstance(entry, AliasEntry)
    assert entry.subject_id == "c1"
    assert entry.label == "지민"
    assert entry.relation_to_user == "spouse"
    assert entry.source == "relation_synonym"
