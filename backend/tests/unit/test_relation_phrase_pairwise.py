"""등록 동반자 + 'X와의 관계·사이' 문형 → pairwise (2026-10-14 실로그 회귀).

실로그(데굴 스레드, 어머니=박여사 등록·첨부): "어머니와의 관계는 어때?" · "나와 어머니와의 관계를
풀어줘"가 어머니 단독 풀이(companion_only)로 나가 답이 "박여사님…"으로 시작하고 어머니의 월주
모친궁을 서술했다.
'궁합'·'나랑'이 있을 때만 pairwise 였고, '와의 관계'·'나와'·'나 사이'는 1인칭 표지로 보지 않았다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.companion_alias import build_companion_alias_index
from saju_engines.conversation import ConversationEngine
from saju_engines.effective_subjects import build_effective_subjects
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.conversation import ConversationState
from saju_shared_types.intent import SubjectKind, SubjectMode
from saju_shared_types.subject import SubjectRecord

_TODAY = date(2026, 10, 14)
_ME = BirthInput(
    birth_date=date(1980, 11, 22), birth_time="09:40:00", birth_place_name="서울", gender="male",
)
_MOM = BirthInput(
    birth_date=date(1955, 9, 5), birth_time="09:30:00", birth_place_name="서울", gender="female",
)
_RECORDS = [
    SubjectRecord(
        subject_id="me", owner_id="o", kind="self", label="데굴", relation_to_user="self",
        birth=_ME,
    ),
    SubjectRecord(
        subject_id="mom", owner_id="o", kind="companion", label="박여사",
        relation_to_user="mother", birth=_MOM,
    ),
]
_INDEX = build_companion_alias_index(_RECORDS, base_subject_id="me")


def _resolve(text: str):
    engine = ConversationEngine(alias_index=_INDEX)
    _parsed, _state, res, _link = engine.process_turn(
        ConversationState(thread_id="t", turn_no=0), text, _TODAY,
    )
    return res


@pytest.mark.parametrize(
    "text",
    [
        "어머니와의 관계는 어때?",
        "나와 어머니와의 관계를 풀어줘",
        "박여사와의 관계는?",
        "엄마랑 나 사이 어떻게 지내면 좋아?",
        "어머니랑 궁합 어때?",      # 기존 동작 유지
        "저와 어머니 관계가 궁금해요",
    ],
)
def test_relation_phrase_with_registered_companion_is_pairwise(text: str) -> None:
    res = _resolve(text)
    assert [(s.kind, s.companion_id) for s in res.subjects] == [(SubjectKind.COMPANION, "mom")]
    assert res.subject_mode is SubjectMode.PAIRWISE
    eff, mode, _inj = build_effective_subjects(
        res.subjects, res.subject_mode, base_subject_id="me", base_label="데굴",
    )
    assert mode == "pairwise" and [e.role for e in eff] == ["self", "companion"]


@pytest.mark.parametrize(
    "text",
    [
        "어머니 건강운 어때?",     # 상대 단독 — 그대로 companion_only
        "어머니 사주 좀 봐줘",
        "어머니 대인관계 어때?",   # 조사 없는 '대인관계'는 상대의 대인관계
        "어머니 사이드잡 괜찮을까",  # '사이드' 오매칭 금지
    ],
)
def test_solo_companion_question_stays_single(text: str) -> None:
    res = _resolve(text)
    assert [s.companion_id for s in res.subjects] == ["mom"]
    assert res.subject_mode is SubjectMode.SINGLE
    _eff, mode, _inj = build_effective_subjects(
        res.subjects, res.subject_mode, base_subject_id="me", base_label="데굴",
    )
    assert mode == "companion_only"


def test_self_only_question_unaffected() -> None:
    res = _resolve("내 재물운 어때?")
    assert [s.kind for s in res.subjects] == [SubjectKind.SELF]
    assert res.subject_mode is SubjectMode.SINGLE
