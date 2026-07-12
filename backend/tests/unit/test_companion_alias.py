"""동반자 별칭 해소(P0) — 등록 레지스트리 기반 대상 지칭 → subject_id.

docs/03 A0/A9. 별명·관계어·별칭을 등록 동반자로 안정 해소하고, 복수 후보/미등록은
임의 추정 없이 확인 질문(unresolved)으로 넘기는지 검증한다(사용자 수용 기준 8종).
"""

from __future__ import annotations

from saju_engines.companion_alias import (
    AliasEntry,
    build_companion_alias_index,
    merge_attached_partner,
)
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


def test_attached_partner_resolves_without_registry() -> None:
    """FE 칩 첨부(inline)만 있고 서버 등록이 없어도 첨부 라벨 지칭이 해소된다.

    실사용 결함(2026-07-12): 게스트가 '남편' 첨부 후 '남편 사주로 …' 질문 시
    need_subject 확인 질문이 무한 반복되던 문제의 회귀 방지.
    """
    idx = merge_attached_partner({}, {"mode": "inline", "label": "남편"})
    res = ConversationEngine(alias_index=idx).resolve_subjects(
        ConversationState(thread_id="t"), "아니 남편 사주로 대출 시 어떤 흐름일지 봐달라고."
    )
    assert [(s.kind, s.companion_id) for s in res.subjects] == [
        (SubjectKind.COMPANION, "inline:partner")
    ]
    assert not res.unresolved


def test_attached_partner_overrides_same_label_registration() -> None:
    """동일 라벨 등록 대상이 있어도 첨부(명시 선택)가 우선 — ambiguous 확인 질문 금지."""
    base = build_companion_alias_index(
        [_SELF, _rec("c9", "남편", rel="husband")], base_subject_id="self1"
    )
    idx = merge_attached_partner(base, {"mode": "inline", "label": "남편"})
    res = ConversationEngine(alias_index=idx).resolve_subjects(
        ConversationState(thread_id="t"), "남편 올해 재물운 봐줘"
    )
    assert res.subjects[0].companion_id == "inline:partner"
    assert not res.unresolved


def test_attached_partner_registered_mode_uses_subject_id() -> None:
    """등록 첨부(registered)는 그 subject_id로 해소 — birth 맵 조회와 정합."""
    idx = merge_attached_partner(
        {}, {"mode": "registered", "subjectId": "c1", "label": "지민"}
    )
    res = ConversationEngine(alias_index=idx).resolve_subjects(
        ConversationState(thread_id="t"), "지민 사주 봐줘"
    )
    assert res.subjects[0].companion_id == "c1"


def test_merge_attached_partner_noop_cases() -> None:
    """첨부 없음·1글자 라벨은 원본 인덱스 그대로(과매칭 방지 기준 동일)."""
    base = {"남편": [AliasEntry("c1", "남편", None, "label")]}
    assert merge_attached_partner(base, None) is base
    assert merge_attached_partner(base, {"mode": "inline", "label": "김"}) is base


def test_possessive_context_mention_not_a_subject() -> None:
    """소유격 문맥 언급("아들의 교육을 위해")은 대상 지칭 아님 — 확인 질문 금지.

    실사용 결함(2026-07-12): 이사 질문 속 "이사는 아들의 교육을 위해 가는거야"가
    need_subject 확인 질문을 무한 유발.
    """
    res = _resolve(
        [_SELF], "뭐라는거야 9월 30일에 이사간다니까. 이사는 아들의 교육을 위해 가는거야"
    )
    assert not res.unresolved
    assert not any(s.kind is SubjectKind.COMPANION for s in res.subjects)


def test_possessive_reading_noun_still_triggers() -> None:
    """소유격이라도 풀이성 명사가 이어지면("아들의 취업운") 대상 지칭 유지."""
    res = _resolve([_SELF], "아들의 취업운 봐줘")
    assert res.unresolved == ["아들"]  # 미등록 → 확인 질문(기존 동작 보존)
    res2 = _resolve([_SELF, _rec("c1", "첫째", rel="son")], "아들의 사주 봐줘")
    assert res2.subjects and res2.subjects[0].companion_id == "c1"


def test_excluded_mention_not_unresolved() -> None:
    """명시적 제외("아들사주는 빼고 봐줘"·"안봐도 된다니까")는 확인 질문 대상 아님."""
    for q in ("아들사주는 빼고 봐줘", "아들사주는 안봐도 된다니까", "아들 사주는 보지 마"):
        res = _resolve([_SELF], q)
        assert not res.unresolved, q
        assert not any(s.kind is SubjectKind.COMPANION for s in res.subjects), q


def test_excluded_mention_skips_registered_companion() -> None:
    """등록 동반자도 제외 표현이면 동반자로 해소하지 않는다("아들 빼고" ≠ 아들 풀이)."""
    res = _resolve([_SELF, _rec("c1", "첫째", rel="son")], "아들 사주는 빼고 내 재물운 봐줘")
    assert not any(s.companion_id == "c1" for s in res.subjects)
    assert not res.unresolved


def test_exclusion_is_per_token() -> None:
    """제외는 토큰 단위 — "아들 사주는 빼고 남편이랑 봐줘"는 남편만 해소."""
    res = _resolve(
        [_SELF, _rec("c1", "첫째", rel="son"), _rec("c2", "남편님", rel="husband")],
        "아들 사주는 빼고 남편이랑 봐줘",
    )
    ids = {s.companion_id for s in res.subjects}
    assert ids == {"c2"} and not res.unresolved


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
