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


# ═══ 3차(남은 항목 전부, 2026-09-11 데굴님 승인) ═══════════════════════════════

from saju_engines.llm_guard import TokenBudgetExceeded  # noqa: E402
from saju_engines.query_parser import mask_inline_birth_spans, parse_pillar_claim  # noqa: E402

_LOVER = BirthInput(
    calendar_type="solar", birth_date="1985-03-03", birth_time="10:00",
    birth_place_name="서울", gender="male", reference_date="2026-08-21",
)


def _thread_seq(turns: list[str], alias_index: dict, births: dict, tid: str) -> list:
    store = ConversationStore()
    out = []
    prior = None
    try:
        for q in turns:
            out.append(cs.chat(
                _BIRTH, q, _TODAY, dry_run=True, store=store, thread_id=tid, owner_id="t",
                companion_alias_index=alias_index, companion_births=births, prior_answer=prior,
            ))
            prior = "(직전 답변 요지)"
    finally:
        store.delete(tid)
    return out


# ── 9. 숫자·영문 별칭 ─────────────────────────────────────────────────────

@pytest.mark.parametrize("q,token", [
    ("남자1과 잘될 수 있을까?", "남자1"),
    ("jw의 사주가 궁금합니다.", "jw"),
])
def test_generic_alias_unregistered_asks_which_one(q: str, token: str) -> None:
    res = _thread_seq([q], {}, {}, f"t-alias-{token}")[0]
    assert res.status == "need_subject"
    assert token in (res.answer or "")


def test_generic_alias_registered_resolves() -> None:
    idx = {"남자1": [AliasEntry("m1", "남자1", "lover", "label")]}
    res = _thread_seq(["남자1과 잘될 수 있을까?"], idx, {"m1": _LOVER}, "t-alias-reg")[0]
    assert res.status == "dry_run", res.answer
    assert any(s.companion_id == "m1" for s in res.intents[0].subjects)


# ── 10. 'N일내' 단기 창 ──────────────────────────────────────────────────────

def test_three_days_window_without_spacing() -> None:
    intent = parse_message("3일내 나에게 일어질 이슈에 대해서 알랴줘", _TODAY).intents[0]
    assert intent.time_range is not None
    assert intent.time_range.start == "2026-08-21" and intent.time_range.end == "2026-08-24"


# ── 11. 명식 정정 발화 — 결정론 답변 ─────────────────────────────────────────

def test_pillar_claim_parsing() -> None:
    assert parse_pillar_claim("시주가 경인인데?") == ("hour", "경인")
    assert parse_pillar_claim("월주는 정해 아니야?") == ("month", "정해")
    assert parse_pillar_claim("시주가 가나인데?") is None  # 60갑자 아님
    assert parse_pillar_claim("이번 주 운세 어때") is None
    qt = parse_message("시주가 경인인데?", _TODAY).intents[0].query_type
    assert qt is QueryType.FEEDBACK_CORRECTION


def test_pillar_claim_answer_is_deterministic_from_engine() -> None:
    res = cs.chat(_BIRTH, "시주가 경인인데?", _TODAY, dry_run=True, owner_id="t")
    assert res.status == "policy"
    ans = res.answer or ""
    assert "엔진 계산으로는 시주가 戊辰(무진)" in ans and "'경인'과는 다릅니다" in ans
    assert "진태양시 보정" in ans and "입력을 한 번 확인" in ans
    res2 = cs.chat(_BIRTH, "일주가 기해인데?", _TODAY, dry_run=True, owner_id="t")
    assert res2.status == "policy" and "일주가 己亥(기해)입니다" in (res2.answer or "")


# ── 12. 주말부부 합가 ─────────────────────────────────────────────────────────

def test_weekend_couple_reunion_is_relocation() -> None:
    q = ("지금 창원시 마산합포구에 살고 있고 동반자는 거창에서 일하고 있어. 주말부부 중이야. "
         "이제 주말 부부를 그만하고 싶은데 그런 운이 있어?")
    intent = parse_message(q, _TODAY).intents[0]
    assert intent.domain is Domain.RELOCATION
    res = cs.chat(_BIRTH, q, _TODAY, dry_run=True, owner_id="t")
    assert res.status == "dry_run", res.answer


# ── 13. 동반자 제외 지시(기존 규칙 회귀 고정) ────────────────────────────────

def test_exclusion_instruction_keeps_self_even_when_registered() -> None:
    idx = {"아들": [AliasEntry("s1", "아들", "son", "relation_synonym")]}
    r1, r2 = _thread_seq(
        ["9월 30일에 이사가 예정인데 비용 지출이 걱정이야", "아들사주는 빼고 봐줘"],
        idx, {"s1": _CHILD}, "t-exclude",
    )
    assert r2.status == "dry_run", r2.answer
    assert [s.kind for s in r2.intents[0].subjects] == [SubjectKind.SELF]


# ── 14. 이전 답 반박 — 스레드 맥락이면 재검토 경로 ────────────────────────────

def test_challenge_with_thread_context_rechecks_instead_of_canned() -> None:
    r1, r2 = _thread_seq(
        ["2026년 연애운 어때?", "그럼 기간상 26년에 어디선가 만나야 하는거아니야?"],
        {}, {}, "t-recheck",
    )
    assert r2.status == "dry_run", r2.answer
    assert "재검토" in (r2.prompt_preview or "")


def test_challenge_without_context_uses_updated_canned_text() -> None:
    res = cs.chat(
        _BIRTH, "그럼 기간상 26년에 어디선가 만나야 하는거아니야?", _TODAY,
        dry_run=True, owner_id="t",
    )
    assert res.status == "policy"
    ans = res.answer or ""
    assert "준비 중" not in ans and "이전 풀이 맥락을 찾지 못했어요" in ans


# ── 15. 진술형 후속(기존 offer-answer 규칙 회귀 고정) ─────────────────────────

@pytest.mark.parametrize("first,statement", [
    (
        "이사 비용이 걱정인데 8월에 지출 흐름 어때?",
        "중도금이지. 가급적 조금만 보내는걸로 하고 싶어서.",
    ),
    ("이직 준비 중인데 10월 흐름 어때?", "없어.. 서류나 포트폴리오 ㅠㅠ"),
])
def test_statement_followup_continues_thread(first: str, statement: str) -> None:
    r1, r2 = _thread_seq([first, statement], {}, {}, f"t-stmt-{abs(hash(first)) % 1000}")
    assert r2.status == "dry_run", r2.answer
    assert r2.intents[0].domain is r1.intents[0].domain


# ── 16. 토큰 상한 초과 — 오류가 아니라 범위 좁히기 안내 ─────────────────────────

def test_token_budget_exceeded_at_call_returns_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a, **_k):
        raise TokenBudgetExceeded("chat_single: 입력 99999tok > 상한 22000tok")

    monkeypatch.setattr(cs.llm_client, "generate_reading", _boom)
    res = cs.chat(_BIRTH, "올해 직업운 어때?", _TODAY, dry_run=False, owner_id="t")
    assert res.status == "too_broad"
    assert res.answer == cs.TOKEN_BUDGET_ANSWER


def test_router_background_maps_token_budget_to_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    from saju_api.routers import chat as chat_router

    class _Hist:
        calls: list = []

        def complete_turn(self, message_id, answer, status="done", meta=None):
            self.calls.append((message_id, answer, status, meta))

    def _boom(*_a, **_k):
        raise TokenBudgetExceeded("chat_single: 입력 99999tok > 상한 22000tok")

    monkeypatch.setattr(cs.llm_client, "generate_reading", _boom)
    monkeypatch.setattr(cs, "update_thread_offer", lambda *_a, **_k: None)
    hist = _Hist()
    chat_router._run_chat_answer(hist, 1, "o", "th", "prompt", "chat_single", None)  # type: ignore[arg-type]
    assert hist.calls and hist.calls[0][1] == cs.TOKEN_BUDGET_ANSWER and hist.calls[0][2] == "done"


# ── 17. 본인 + 후보 2명 비교(multi_with_self) ─────────────────────────────────

_TWO_CANDIDATES = (
    "1972년 11월 7일생이 남편일 경우와 1980년 10월 8일생이 남편일 경우\n"
    "둘 중 내 사주와 더 잘 맞는 사람이 누구야?"
)


def test_self_plus_two_candidates_parsed_with_self() -> None:
    intent = parse_message(_TWO_CANDIDATES, _TODAY).intents[0]
    kinds = [s.kind for s in intent.subjects]
    assert kinds == [SubjectKind.SELF, SubjectKind.INLINE_TEMP, SubjectKind.INLINE_TEMP]
    assert intent.time_range is None  # 출생일이 시점으로 새지 않는다


def test_inline_birth_spans_are_masked_for_time_parsing() -> None:
    masked = mask_inline_birth_spans(_TWO_CANDIDATES, _TODAY)
    assert "11월 7일" not in masked and "10월 8일" not in masked
    # 사건 날짜는 남긴다.
    assert "8월 25일" in mask_inline_birth_spans("2026년 8월 25일에 시험이 있어", _TODAY)


def test_self_plus_two_candidates_runs_multi_with_self() -> None:
    res = cs.chat(_BIRTH, _TWO_CANDIDATES, _TODAY, dry_run=True, owner_id="t")
    assert res.status == "dry_run", res.answer
    text = res.prompt_preview or ""
    assert "[본인 기준 후보 비교 지침]" in text
    assert "1972-11-07" in text and "1980-10-08" in text
    assert "순위·점수·확률·승률 단정을 하지 말 것" in text
