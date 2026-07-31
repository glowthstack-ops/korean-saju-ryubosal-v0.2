"""궁합 질문에서 본인이 누락되던 결함 회귀 (2026-07-31 실로그 '나 × 전남친').

`"헤어진 전남친과 다시 만날 수 있을까?"` 가 상대 단독 풀이로 나갔다. 경로는 이렇다.

    _subject_mode      명시적 1인칭(나/내가)이 없어 SINGLE
    build_effective..  self 암묵 삽입이 PAIRWISE 에서만 동작 → companion_only
    chat_service       companion_only → partner_birth=None → 궁합 오버레이 OFF

한국어는 1인칭 주어를 자주 생략하고, **재회·연락 같은 술어는 행위자가 둘**이라 '나와'가
자명하다. 명시적 '나' 를 요구하는 게이트가 이 부류를 통째로 놓쳤다.

경계가 이 회귀의 핵심이다. `'전남친 요즘 어때?'` 처럼 정말로 상대만 묻는 질문까지 끌어오면
반대 방향 오류가 난다 — 그쪽은 술어가 상호적이지 않다. 그래서 양성과 **음성을 함께** 고정한다.
"""

from __future__ import annotations

import pytest
from saju_engines.effective_subjects import (
    AttachedCompanion,
    build_effective_subjects,
)
from saju_engines.query_parser import (
    INTERPERSONAL_RELATIONS,
    implies_self_counterpart,
)
from saju_shared_types.intent import SubjectMode

# ── 상호 술어 ────────────────────────────────────────────────────────────

RECIPROCAL = [
    "헤어진 전남친과 다시 만날 수 있을까?",
    "전남친한테 연락 올까?",
    "우리 다시 잘될까?",
    "재회 가능성 있어?",
    "그 사람이랑 화해할 수 있을까",
    "다시 사귈 수 있을까",
    "헤어졌는데 어떻게 해야 해?",
    "이 사람이랑 결혼할 수 있을까",
    "우리 관계 계속 이어질까",
    "그 사람 돌아올까?",
]

#: 상대 **단독** 질문. 여기까지 본인을 끌어오면 대상이 뒤바뀐다.
SOLO = [
    "엄마 사주만 봐줘",
    "전남친 요즘 어때?",
    "남편 올해 재물운 어때",
    "동생 취업운 봐줘",
    "상사 성격이 어떤 사람이야",
    "아빠 건강운 알려줘",
    "친구 올해 어때?",
]


@pytest.mark.parametrize("text", RECIPROCAL)
def test_reciprocal_predicate_implies_self(text: str) -> None:
    """행위자가 둘인 술어는 1인칭 생략을 허용한다."""
    assert implies_self_counterpart(text)


@pytest.mark.parametrize("text", SOLO)
def test_solo_question_does_not_imply_self(text: str) -> None:
    """상대 단독 질문에 본인을 끌어오면 안 된다 — 이쪽이 과검출 경계다."""
    assert not implies_self_counterpart(text)


# ── 관계 유형 단독 근거 ──────────────────────────────────────────────────


@pytest.mark.parametrize("relation", sorted(INTERPERSONAL_RELATIONS))
def test_interpersonal_relation_implies_self_without_predicate(relation: str) -> None:
    """연인·배우자 등은 관계 자체가 '본인과의' 관계다 — 술어가 없어도 함께 본다."""
    assert implies_self_counterpart("요즘 어때?", relation)


@pytest.mark.parametrize("relation", ["coworker", "boss", "subordinate", "friend"])
def test_workplace_relation_alone_does_not_imply_self(relation: str) -> None:
    """'상사 사주 좀 봐줘'는 상대 단독일 수 있다 — 관계만으로 본인을 끌어오지 않는다."""
    assert not implies_self_counterpart("요즘 어때?", relation)


# ── 대상 모드 ────────────────────────────────────────────────────────────


def _mode(
    *, relation: str | None = None, self_implied: bool = False,
    subject_mode: SubjectMode = SubjectMode.SINGLE,
) -> str:
    """칩으로 상대 1명만 첨부된 상태의 모드."""
    _eff, mode, _inj = build_effective_subjects(
        [], subject_mode, base_subject_id="me",
        attached=[AttachedCompanion(
            subject_id="inline:partner", label="상대", relation_to_user=relation,
        )],
        self_implied=self_implied,
    )
    return mode


def test_chip_only_reciprocal_question_becomes_pairwise() -> None:
    """칩만 첨부되고 발화에 상대 언급이 없어도 상호 술어면 본인을 포함한다.

    이 경로가 없으면 `_subject_mode` 가 동반자를 0명으로 보아 PAIRWISE 로 올리지 못한다.
    """
    assert _mode(self_implied=True) == "pairwise"


def test_chip_with_interpersonal_relation_becomes_pairwise() -> None:
    """관계만으로도 성립한다 — 즉석 상대에 '연인'을 고르면 궁합으로 본다."""
    assert _mode(relation="romance") == "pairwise"
    assert _mode(relation="spouse") == "pairwise"


def test_workplace_relation_stays_companion_only() -> None:
    """직장 관계는 단독 질문일 수 있어 기존 동작을 유지한다."""
    assert _mode(relation="boss") == "companion_only"


def test_no_signal_stays_companion_only() -> None:
    """신호가 없으면 기존 동작 그대로 — 이 회귀가 기본 동작을 바꾸지 않는다."""
    assert _mode() == "companion_only"


def test_explicit_pairwise_still_works() -> None:
    """기존 PAIRWISE 경로는 그대로다."""
    assert _mode(subject_mode=SubjectMode.PAIRWISE) == "pairwise"


def test_two_companions_never_get_implicit_self() -> None:
    """동반자 2명은 동반자끼리 비교다 — 상호 술어가 있어도 본인을 끼워 넣지 않는다."""
    _eff, mode, _inj = build_effective_subjects(
        [], SubjectMode.SINGLE, base_subject_id="me",
        attached=[
            AttachedCompanion(subject_id="a", label="A", relation_to_user="romance"),
            AttachedCompanion(subject_id="b", label="B", relation_to_user="romance"),
        ],
        self_implied=True,
    )
    assert mode == "compare_exclude_self"


def test_pairwise_injection_requires_relationship_context() -> None:
    """궁합으로 올라가면 관계 컨텍스트가 요구된다 — 오버레이가 켜지는 근거."""
    _eff, mode, inj = build_effective_subjects(
        [], SubjectMode.SINGLE, base_subject_id="me",
        attached=[AttachedCompanion(subject_id="inline:partner", label="전남친")],
        self_implied=True,
    )
    assert mode == "pairwise"
    assert inj.requires_relationship_context
    assert inj.primary_subject_id == "me"  # 본인이 서술 기준 — 상대가 아니다
