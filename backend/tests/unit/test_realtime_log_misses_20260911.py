"""실로그 미인식 사례 회귀(2026-09-11 전수 점검 — 추천 순서 1·2·4).

DB 738쌍 재판정에서 현재 코드로도 바운스되던 사례 중 이번에 처리한 것:
  1. 시험일 질문의 동반자 바운스 — 본문 날짜가 즉석 출생일로 잡혀 본인이 빠짐
  2. 업무 변화 질문의 정서 지지 오분류 — '힘들어질까'가 감정 어휘에 삼켜짐
  4. 지원 경로 질문 — '원서·추천·제안'에 career 어휘 없음
"""
from __future__ import annotations

from datetime import date

import pytest

import saju_api.services.chat_service as cs
from saju_engines.query_parser import parse_message
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import Domain, QueryType, SubjectKind

_TODAY = date(2026, 8, 21)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date="2026-08-21",
)


# ── 1. 본문 날짜 ≠ 즉석 출생일 ────────────────────────────────────────────

@pytest.mark.parametrize("q", [
    "2026년 8월 25일에 시험이 있어\n공부는 많이 못했는데 그날의 운세가 어떨지 알려줘",
    "2006년 8월 25일에 시험이 있습니다\n공부는 많이 못했는데 그날의 운세는 어떨까요?",  # 일정 표현
    "2026년 9월 30일에 이사가 예정되어 있어 주의할 점은?",
    "2027년 3월 2일 면접인데 그날 어때",  # 미래 날짜
])
def test_schedule_or_future_date_is_not_inline_birth(q: str) -> None:
    intent = parse_message(q, _TODAY).intents[0]
    kinds = [s.kind for s in intent.subjects]
    assert kinds == [SubjectKind.SELF], kinds
    assert intent.time_range is not None  # 날짜는 시점으로는 살아 있다


@pytest.mark.parametrize("q", [
    "91년 10월 31일 오후 3시 부천에서 태어난 사람이랑 궁합 봐줘",
    "1972년 11월 7일생이 남편일 경우와 1980년 10월 8일생이 남편일 경우 둘 중 누가 더 잘 맞아?",
    "1998.07.23 여자랑 궁합 어때",
])
def test_genuine_inline_births_still_parsed(q: str) -> None:
    intent = parse_message(q, _TODAY).intents[0]
    assert any(s.kind is SubjectKind.INLINE_TEMP for s in intent.subjects)


def test_exam_day_question_is_not_bounced_as_need_subject() -> None:
    """실로그 #1753 — 동반자 언급이 없는데 '비교할 대상' 바운스가 났다."""
    res = cs.chat(
        _BIRTH, "2026년 8월 25일에 시험이 있어\n공부는 많이 못했는데 그날의 운세가 어떨지 알려줘",
        _TODAY, dry_run=True, owner_id="t",
    )
    assert res.status == "dry_run", res.answer
    assert res.intents[0].domain is Domain.EDUCATION


# ── 2·4. 업무 변화 질문은 career 분석 경로 ───────────────────────────────

def test_work_change_question_is_career_not_emotional() -> None:
    q = "아 내 위의 리더가 다른팀으로가는데 그럼 나의업무 방향은 더 힘들어질까? 10월부터"
    intent = parse_message(q, _TODAY).intents[0]
    assert intent.query_type is not QueryType.EMOTIONAL_SUPPORT
    assert intent.domain is Domain.CAREER
    res = cs.chat(_BIRTH, q, _TODAY, dry_run=True, owner_id="t")
    assert res.status == "dry_run", res.answer


def test_application_channel_question_is_career() -> None:
    """실로그 #455 — 자발 지원 vs 추천·제안 경로 질문."""
    q = "내가 원서를 내야해 아님 추천이나 제안을 받게될까"
    intent = parse_message(q, _TODAY).intents[0]
    assert intent.domain is Domain.CAREER
    res = cs.chat(_BIRTH, q, _TODAY, dry_run=True, owner_id="t")
    assert res.status == "dry_run", res.answer


# ═══ 2차(추천 순서 5·6·7·8, 2026-09-11 데굴님 승인) ═══════════════════════════

from saju_engines.companion_alias import AliasEntry  # noqa: E402
from saju_engines.conversation_store import ConversationStore  # noqa: E402

_CHILD = BirthInput(
    calendar_type="solar", birth_date="2015-05-05", birth_time="10:00",
    birth_place_name="서울", gender="female", reference_date="2026-08-21",
)


def _thread_chat(q: str, alias_index: dict, births: dict, tid: str) -> cs.ChatResponse:
    store = ConversationStore()
    try:
        return cs.chat(
            _BIRTH, q, _TODAY, dry_run=True, store=store, thread_id=tid, owner_id="t",
            companion_alias_index=alias_index, companion_births=births,
        )
    finally:
        store.delete(tid)


# ── 5. 구 단위·생활권 지역 추천 ─────────────────────────────────────────────

@pytest.mark.parametrize("q,scope", [
    ("창원에서는 어느 구가 가장 좋아?", "창원"),
    ("내 동반자와 같이 살기에 창원에서는 어느 구가 적합할까?", "창원"),
    ("응 봐줘 수지안에서 어떤 생활권이 맞을지", "수지"),
])
def test_subunit_region_question_is_relocation_with_scope(q: str, scope: str) -> None:
    intent = parse_message(q, _TODAY).intents[0]
    assert intent.domain is Domain.RELOCATION
    assert intent.constraints.target_region == scope


def test_residence_fit_question_has_target_region() -> None:
    """실로그 #1013 — '용인 수지에 사는게 잘 맞을까'가 관계 도메인으로 새던 오라우팅."""
    intent = parse_message("나는 용인 수지에 사는게 잘 맞을까?", _TODAY).intents[0]
    assert intent.domain is Domain.RELOCATION
    assert intent.constraints.target_region == "용인 수지"


def test_subunit_scope_yields_candidates_inside_scope() -> None:
    """창원 하위 구·동 후보가 추천 블록에 실린다(전국 폴백 아님). 엔진 미빌드면 스킵."""
    if cs._get_region_orchestrator() is None:
        pytest.skip("지역 추천 엔진 미빌드")
    res = cs.chat(_BIRTH, "창원에서는 어느 구가 가장 좋아?", _TODAY, dry_run=True, owner_id="t")
    assert res.status == "dry_run", res.answer
    text = res.prompt_preview or ""
    i = text.find("[지역 오행 추천(참고)")
    assert i >= 0
    assert "창원시" in text[i:i + 600]
    # 수지구처럼 시군구로 해소되는 범위도 하위 단위 요구면 그 안의 동 후보를 추천한다.
    res2 = cs.chat(_BIRTH, "수지안에서 어떤 생활권이 맞을지", _TODAY, dry_run=True, owner_id="t")
    t2 = res2.prompt_preview or ""
    j = t2.find("[지역 오행 추천(참고)")
    assert j >= 0 and "수지구" in t2[j:j + 600]


# ── 6. 육친 운 — 등록 동반자 우선, 없으면 본인 명식 육친 축 ───────────────────

@pytest.mark.parametrize("q,axis", [
    ("내 부모님 운은 어때?", "parent"),
    ("자녀운 어때?", "child"),
    ("아들 운은 어때", "child"),
    ("자식복이 있을까", "child"),
])
def test_kin_axis_question_is_self_chart_analysis(q: str, axis: str) -> None:
    from saju_engines.query_parser import detect_kin_axis

    assert detect_kin_axis(q) == axis
    intent = parse_message(q, _TODAY).intents[0]
    assert intent.query_type is QueryType.CHART_ANALYSIS
    assert intent.domain is Domain.RELATIONSHIP
    assert [s.kind for s in intent.subjects] == [SubjectKind.SELF]


@pytest.mark.parametrize("q", ["자녀랑 나는 어때?", "엄마 운전 조심해야 해?"])
def test_non_axis_kin_mentions_are_untouched(q: str) -> None:
    from saju_engines.query_parser import detect_kin_axis

    assert detect_kin_axis(q) is None


def test_kin_axis_unregistered_uses_self_module_in_thread() -> None:
    res = _thread_chat("내 부모님 운은 어때?", {}, {}, "t-kin-self")
    assert res.status == "dry_run", res.answer
    assert [s.kind for s in res.intents[0].subjects] == [SubjectKind.SELF]
    assert "부모·윗사람" in (res.prompt_preview or "")


def test_kin_axis_registered_child_reads_that_companion() -> None:
    """데굴님 지시 — 등록 동반자의 관계·표시 이름이 맞으면 그 대상 기준(육친 축 모듈 아님)."""
    idx = {
        "자녀": [AliasEntry("c1", "민지호", "child", "relation_synonym")],
        "민지호": [AliasEntry("c1", "민지호", "child", "label")],
    }
    res = _thread_chat("자녀운 어때?", idx, {"c1": _CHILD}, "t-kin-reg")
    assert res.status == "dry_run", res.answer
    subj = res.intents[0].subjects
    assert any(s.kind is SubjectKind.COMPANION and s.companion_id == "c1" for s in subj)
    assert "자녀·표현" not in (res.prompt_preview or "")


def test_kin_reference_without_axis_still_asks_which_one() -> None:
    res = _thread_chat("자녀랑 나는 어때?", {}, {}, "t-kin-ask")
    assert res.status == "need_subject"


# ── 7. 구매·지출 결정 ─────────────────────────────────────────────────────

@pytest.mark.parametrize("q", [
    "차를 바꾸려고 하는데 과연 좋은 선택일까?",
    "현금자산이 있는데 그걸로 중고차를 구매할까 하는데. 좋은 선택일까?",
])
def test_purchase_decision_is_wealth(q: str) -> None:
    intent = parse_message(q, _TODAY).intents[0]
    assert intent.domain is Domain.WEALTH
    res = cs.chat(_BIRTH, q, _TODAY, dry_run=True, owner_id="t")
    assert res.status == "dry_run", res.answer


# ── 8. 본문 괄호 출생정보 → 즉석 대상 ────────────────────────────────────────

def test_parenthetical_birth_attaches_to_token() -> None:
    q = "나는 지금 결혼한 신랑(1975.04.04 시간모름)고 사주가 궁금하다"
    intent = parse_message(q, _TODAY).intents[0]
    assert len(intent.subjects) == 1
    s = intent.subjects[0]
    assert s.kind is SubjectKind.INLINE_TEMP and s.label == "신랑"
    assert s.inline_birth is not None and s.inline_birth.date == "1975-04-04"
    assert s.inline_birth.time is None


def test_inline_subject_birth_is_computed_with_note() -> None:
    """실로그 #2003 — 즉석 대상 출생정보가 need_subject로 끝나지 않고 계산·안내된다."""
    q = "나는 지금 결혼한 신랑(1975.04.04 시간모름)고 사주가 궁금하다"
    res = cs.chat(_BIRTH, q, _TODAY, dry_run=True, owner_id="t")
    assert res.status == "dry_run", res.answer
    assert "[즉석 대상 안내] 신랑" in (res.prompt_preview or "")
    res2 = cs.chat(
        _BIRTH, "동생(1998.07.23 여자)이랑 궁합 봐줘", _TODAY, dry_run=True, owner_id="t",
    )
    assert res2.status == "dry_run", res2.answer
    t2 = res2.prompt_preview or ""
    assert "[즉석 대상 안내] 동생" in t2 and "동생(" in t2  # 궁합 경로에도 대상 명식·안내


def test_parenthetical_birth_prefers_registered_companion_in_thread() -> None:
    idx = {"신랑": [AliasEntry("h1", "신랑", "husband", "label")]}
    res = _thread_chat(
        "신랑(1975.04.04 시간모름) 사주가 궁금하다", idx, {"h1": _CHILD}, "t-paren-reg",
    )
    assert res.status == "dry_run", res.answer
    subj = res.intents[0].subjects
    assert [s.kind for s in subj] == [SubjectKind.COMPANION] and subj[0].companion_id == "h1"
