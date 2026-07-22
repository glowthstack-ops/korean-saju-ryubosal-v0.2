"""부부 공동 질문 본인 배제 회귀 — '우리가' 포함·괄호 주석 강등·kind='self' 동반자 인정.

2026-07-22 실로그 2건: '… 우리가 주의할 점은? 은행 대출(남편)…' / '… 은행 대출(남편) -
인테리어 등이 남아있는데 주의사항이…'(+남편 칩)가 본인 배제된 companion_only로 빠져
'비교할 대상의 출생 정보를 확인할 수 없어요' 거부. 원인 3중: ①'우리가'가 본인 신호로
인식 안 됨 ②괄호 주석 '(남편)'이 대상 지정으로 채택됨 ③사주목록이 전부 kind='self'로
등록되는데 별칭 인덱스·birth 맵이 kind!='self'만 동반자로 인정(등록 동반자 기능 사장).
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.companion_alias import (
    build_companion_alias_index,
    merge_attached_partner,
)
from saju_engines.conversation import ConversationEngine
from saju_engines.effective_subjects import AttachedCompanion, build_effective_subjects
from saju_engines.query_parser import INCLUSIVE_WE_RE, _detect_subjects
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.conversation import ConversationState
from saju_shared_types.intent import SubjectKind
from saju_shared_types.subject import SubjectRecord

_T = date(2026, 7, 22)
_Q = (
    "9월 30일에 이사가 예정되어 있는데 이 과정에서 우리가 주의할 점은 뭘까? "
    "은행 대출(남편) - 인테리어 - 가전구입이 남아있어."
)


def _thread_subjects(q: str):
    idx = merge_attached_partner(
        {}, {"mode": "registered", "label": "남편", "subjectId": "comp-1"}
    )
    eng = ConversationEngine(alias_index=idx)
    parsed, _, _, _ = eng.process_turn(
        ConversationState(thread_id="t"), q, _T, birth_year=1985
    )
    i = parsed.intents[0]
    _, mode, _ = build_effective_subjects(
        i.subjects, i.subject_mode, base_subject_id="self-1", base_label="나",
        attached=[AttachedCompanion(subject_id="comp-1", label="남편")],
    )
    return i.subjects, mode


def test_inclusive_we_adds_self_to_couple_question() -> None:
    # 실로그 1 — '(남편)'은 주석으로 강등, 본인+칩 동반자 pairwise 판정(companion_only 금지).
    subjects, read_mode = _thread_subjects(_Q)
    assert any(s.kind is SubjectKind.SELF for s in subjects)
    assert read_mode == "pairwise"


def test_paren_annotation_couple_question_stays_pairwise() -> None:
    # 실로그 2(재발 문구 — '우리가' 없음): 괄호 주석만으로 남편 단독 대상이 되지 않는다.
    q = (
        "9월 30일에 이사가 예정되어있어. 지금 은행 대출(남편) - 인테리어 등이 "
        "남아있는데 주의사항이 뭐가 있을까"
    )
    subjects, read_mode = _thread_subjects(q)
    assert any(s.kind is SubjectKind.SELF for s in subjects)
    assert all(s.kind is not SubjectKind.COMPANION for s in subjects)  # 텍스트 대상 미채택
    assert read_mode == "pairwise"  # 동반자는 칩 첨부로만 합류


def test_possessive_uri_stays_companion_only() -> None:
    # '우리 남편 사주 봐줘'는 소유격 — 본인 미삽입, 남편 단독 유지.
    subjects, read_mode = _thread_subjects("우리 남편 사주 봐줘")
    assert all(s.kind is not SubjectKind.SELF for s in subjects)
    assert read_mode == "companion_only"


@pytest.mark.parametrize(
    "text",
    [
        "우리가 주의할 점은 뭘까",
        "우리는 언제 이사하면 좋아",
        "우리 둘 궁합 어때",
        "우리 부부 올해 어때",
        "남편이랑 우리한테 좋은 날 알려줘",
        "저희가 조심할 게 있을까요",
    ],
)
def test_inclusive_we_positive(text: str) -> None:
    assert INCLUSIVE_WE_RE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "우리 남편 사주 봐줘",
        "우리 엄마 건강운 어때",
        "우리 집 이사 언제가 좋아",
        "우리가게 언제 열면 좋을까",
    ],
)
def test_inclusive_we_negative(text: str) -> None:
    assert not INCLUSIVE_WE_RE.search(text)


def test_parser_paren_annotation_not_subject() -> None:
    # '(남편)' 괄호 주석은 대상 지정이 아니다 — 파서도 본인 기본으로 남는다.
    subjects, _ = _detect_subjects(_Q)
    assert all(s.kind is not SubjectKind.COMPANION for s in subjects)
    assert any(s.kind is SubjectKind.SELF for s in subjects)


def test_parser_relation_word_comma_boundary() -> None:
    # 괄호 밖 관계어는 쉼표·문말 경계로도 검출된다(경계 보정 유지).
    subjects, _ = _detect_subjects("남편, 요즘 사업 흐름이 어떤지 궁금해")
    assert any(s.kind is SubjectKind.COMPANION for s in subjects)


def test_parser_relation_compound_still_excluded() -> None:
    # '남편감'(합성어)은 관계어 지칭이 아니다 — 기존 동작 보존.
    subjects, _ = _detect_subjects("어떤 남편감을 만나게 될까?")
    assert all(s.kind is not SubjectKind.COMPANION for s in subjects)


# ── kind='self' 등록 사주의 동반자 인정(2026-07-22 실측 결함) ──


def _record(sid: str, label: str) -> SubjectRecord:
    return SubjectRecord(
        subject_id=sid, owner_id="o1", kind="self", label=label,
        birth=BirthInput(
            calendar_type="solar", birth_date="1979-03-05",
            birth_time="04:30", birth_place_name="서울", gender="male",
        ),
    )


def test_alias_index_includes_all_self_records() -> None:
    # 사주목록 전원이 kind='self'여도 기준 사주 제외 전부가 별칭 인덱스에 오른다.
    records = [_record("base-1", "나님"), _record("husb-1", "남편"), _record("son-1", "아들")]
    idx = build_companion_alias_index(records, base_subject_id="base-1")
    assert "남편" in idx and idx["남편"][0].subject_id == "husb-1"
    assert "아들" in idx and idx["아들"][0].subject_id == "son-1"
    assert all(e.subject_id != "base-1" for es in idx.values() for e in es)  # 기준 제외


def test_registered_husband_reading_resolves() -> None:
    # '남편 사주 봐줘'(괄호 아님) — kind='self' 등록 남편이 정상 해소돼 companion_only.
    records = [_record("base-1", "나님"), _record("husb-1", "남편")]
    idx = build_companion_alias_index(records, base_subject_id="base-1")
    eng = ConversationEngine(alias_index=idx)
    parsed, _, res, _ = eng.process_turn(
        ConversationState(thread_id="t"), "남편 사주 봐줘", _T, birth_year=1985
    )
    i = parsed.intents[0]
    assert not res.unresolved
    assert [s.companion_id for s in i.subjects if s.kind is SubjectKind.COMPANION] == ["husb-1"]
