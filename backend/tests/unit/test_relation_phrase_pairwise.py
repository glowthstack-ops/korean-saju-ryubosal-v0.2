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
        "어머니와 나의 관계는?",       # 2차 실로그 — '나의'도 1인칭
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


# ── 비연애 관계 프레임 ────────────────────────────────────────────────────────────
# 2026-10-14 데굴님 지적: 등록 어머니와의 관계 질문이 '연애와 결혼의 흐름'으로 답했다.


class _FakeStore:
    def __init__(self) -> None:
        self.saved: dict[str, ConversationState] = {}

    def migrate(self) -> None:
        return None

    def load(self, thread_id: str) -> ConversationState | None:
        return self.saved.get(thread_id)

    def save(self, state: ConversationState, owner_id: str = "default") -> None:
        self.saved[state.thread_id] = state


def _prompt(
    text: str, records=None, companion_id: str = "mom", label: str = "박여사",
) -> tuple[str, str]:
    from saju_api.services import chat_service

    recs = records or _RECORDS
    index = build_companion_alias_index(recs, base_subject_id="me")
    comp = next(r for r in recs if r.subject_id == companion_id)
    ref = {"mode": "registered", "label": label, "subjectId": companion_id}
    resp = chat_service.chat(
        _ME, text, _TODAY, True, thread_id="t-frame", store=_FakeStore(),
        partner_birth=comp.birth, partner_label=label, partner_ref=ref, subject_label="데굴",
        owner_id="o", subject_id="me", companion_alias_index=index,
        companion_births={companion_id: comp.birth},
    )
    return resp.prompt_preview or "", resp.intents[0].subject_mode.value


_FRAME = "[관계 유형 — 부모·자식: 본인과 박여사]"


@pytest.mark.parametrize(
    "text",
    [
        "어머니와의 관계는 어때?", "어머니와 나의 관계는?", "박여사와의 관계는?",
        "박여사랑 궁합 어때?",
    ],
)
def test_parent_child_frame_replaces_romance_blocks(text: str) -> None:
    """등록 관계가 어머니면 호칭('박여사')으로 물어도 부모·자식 프레임 — 연애·결혼 블록은 빠진다."""
    p, mode = _prompt(text)
    assert mode == "pairwise"
    assert "[궁합 분석" in p and _FRAME in p
    assert "[배우자성" not in p and "[인연·만남 시기" not in p and "결혼 답변 출력 가드" not in p
    assert "선별: 결혼 신호" not in p and "박여사님" not in p


def test_companion_health_question_has_no_relation_frame() -> None:
    """관계 맥락이 아닌 상대 단독 질문(건강운)엔 프레임을 붙이지 않는다."""
    p, mode = _prompt("어머니 건강운 어때?")
    assert mode == "single" and _FRAME not in p


def test_romantic_companion_keeps_romance_blocks() -> None:
    """등록 관계가 연인이면 기존 연애·결혼 블록이 그대로 — 프레임 지시 없음."""
    lover = SubjectRecord(
        subject_id="gf", owner_id="o", kind="companion", label="지은", relation_to_user="lover",
        birth=BirthInput(
            birth_date=date(1990, 3, 3), birth_time="07:30:00", birth_place_name="서울",
            gender="female",
        ),
    )
    p, mode = _prompt(
        "지은이랑 관계 어때?", records=[_RECORDS[0], lover], companion_id="gf", label="지은",
    )
    assert mode == "pairwise"
    # pairwise 는 구조 블록을 생략하므로 연애 프레임은 인연 시기 지시·결혼 출력 가드로 확인한다.
    assert "[관계 유형 — " not in p
    assert "[인연·만남 시기" in p and "결혼 답변 출력 가드" in p
