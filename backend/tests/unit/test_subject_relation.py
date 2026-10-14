"""명식별 '나와의 관계'(relation_to_user) — 키 검증·kind 파생·본인 유일성 (2026-10-14 데굴님 승인).

배경: 등록 위저드가 모든 사주를 kind=self 로 저장해 채팅 동반자 모달에 전부 '본인'이 붙었고,
관계어 지칭("남편이…")의 등록 동반자 해소도 relation_to_user 가 비어 작동하지 않았다.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from saju_api.routers.subjects import SubjectUpsert, demote_other_selves
from saju_engines.companion_alias import RELATION_SYNONYMS, build_companion_alias_index
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.subject import (
    RELATION_TO_USER_KEYS,
    RELATION_TO_USER_KO,
    SubjectRecord,
    kind_for_relation,
)

_BIRTH = BirthInput(birth_date=date(1980, 11, 22), birth_time="09:40:00", birth_place_name="서울")


def _rec(sid: str, relation: str | None, kind: str = "self") -> SubjectRecord:
    return SubjectRecord(
        subject_id=sid, owner_id="o", kind=kind, label=sid, relation_to_user=relation, birth=_BIRTH,
    )


def test_relation_keys_have_labels_and_alias_synonyms():
    assert len(RELATION_TO_USER_KEYS) == 17
    assert set(RELATION_TO_USER_KO) == set(RELATION_TO_USER_KEYS)
    # 본인·연인·상사·기타를 뺀 관계 키는 별칭 동의어표에 있어 관계어 지칭이 해소된다.
    for key in RELATION_TO_USER_KEYS:
        if key not in ("self", "lover", "boss", "other"):
            assert key in RELATION_SYNONYMS, key


@pytest.mark.parametrize(
    ("relation", "fallback", "kind"),
    [("self", "companion", "self"), ("husband", "self", "companion"), (None, "self", "self"),
     (None, "companion", "companion")],
)
def test_kind_for_relation(relation, fallback, kind):
    assert kind_for_relation(relation, fallback) == kind


def test_upsert_rejects_unknown_relation_and_derives_kind():
    with pytest.raises(ValidationError):
        SubjectUpsert(label="x", birth=_BIRTH, relation_to_user="남편")
    body = SubjectUpsert(label="x", birth=_BIRTH, kind="self", relation_to_user="husband")
    assert body.effective_kind == "companion"
    body2 = SubjectUpsert(label="x", birth=_BIRTH, kind="companion", relation_to_user="self")
    assert body2.effective_kind == "self"
    legacy = SubjectUpsert(label="x", birth=_BIRTH, kind="self", relation_to_user="")
    assert legacy.relation_to_user is None and legacy.effective_kind == "self"


def test_demote_other_explicit_selves_only():
    """명시 본인은 1명 — 다른 명시 본인만 강등, 관계 미설정 레거시(kind=self)는 그대로."""
    records = [
        _rec("a", "self"), _rec("b", "self"), _rec("legacy", None, "self"),
        _rec("h", "husband", "companion"),
    ]
    demoted = demote_other_selves(records, keep_subject_id="b")
    assert [d.subject_id for d in demoted] == ["a"]
    assert demoted[0].relation_to_user is None and demoted[0].kind == "companion"
    assert demote_other_selves(records, keep_subject_id="a") and all(
        d.subject_id == "b" for d in demote_other_selves(records, keep_subject_id="a")
    )


def test_relation_key_resolves_kin_mention_in_alias_index():
    """관계 키를 저장하면 '남편' 지칭이 그 동반자로 해소된다(동의어표 키 일치)."""
    me = _rec("me", "self")
    husband = _rec("h", "husband", "companion")
    index = build_companion_alias_index([me, husband], base_subject_id="me")
    assert {e.subject_id for e in index["남편"]} == {"h"}
    assert "me" not in {e.subject_id for es in index.values() for e in es}
