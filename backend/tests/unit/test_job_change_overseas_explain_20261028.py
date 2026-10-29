"""2026-10-28 실답 교정 묶음 회귀.

이직 완료 사실·되물음 답·사실 단언형 이의·'몇 년도' 5년 창·설명 요청·해외 근무 층.

실로그 두 스레드(web-mvrpyw6m·web-mvrq8ocg):
  ① "이직을 했는데 업무의 양이 많아" — 되물음 답인데 '이직'이 새 사건(career_change)으로 잡혀
     2027년 이직 창 서술로 흘렀다.
  ② "주재원을 나가고 싶은데 해외에서 일한 운이 몇년도에 있어?" — 해외 근무 어휘가 없어 12개월 career
     총운 + 국내 이직 서술.
  ③ "아니 난 이직을 했다니까!" — 이의로 안 잡혀 또 이직 전망.
  ④ 인용문 + "위의 내용 쉽게 설명해줘" — 방위 설명 뒤 2028~2031 연운·삼재 서술.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import pytest

import saju_api.services.chat_service as cs
from saju_engines.challenge_detect import is_challenge
from saju_engines.conversation import ConversationEngine
from saju_engines.horizon import horizon_directive, resolve_horizon
from saju_engines.job_change_report import (
    asks_new_job_change,
    is_job_change_report,
    job_change_report_clauses,
    strip_job_change_report,
)
from saju_engines.overseas_work import (
    detect_overseas_work,
    is_travel_only,
    overseas_year_signals,
    render_overseas_block,
)
from saju_engines.query_parser import detect_explain_request, explain_target, parse_message
from saju_engines.user_facts import extract_user_facts, user_facts_block
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.conversation import ConversationState, LinkKind
from saju_shared_types.events import EventKey
from saju_shared_types.intent import Domain, Granularity, QueryType

_T = date(2026, 10, 28)
_Q_OVERSEAS = "내가 주재원을 나가고 싶은데 해외에서 일한 운이 몇년도에 있어?"
_Q_WORKLOAD = "요즘 내가 일이 너무 많아 힘든데 언제쯤 안정 될까?"
_B = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:40", birth_place_name="서울",
    gender="male", reference_date="2026-10-28",
)


class _MemStore:
    """DB 없는 스레드 저장소 대역 — chat() 이 쓰는 load/save/migrate/owner_of 만."""

    def __init__(self) -> None:
        self.d: dict[str, ConversationState] = {}

    def migrate(self) -> None:
        return None

    def load(self, tid: str) -> ConversationState | None:
        return self.d.get(tid)

    def save(self, st: ConversationState, owner_id: str = "default") -> None:
        self.d[st.thread_id] = st.model_copy(deep=True)

    def owner_of(self, tid: str) -> str | None:
        return None


# ── ① 완료형 이직 보고 ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text, clause, residual",
    [
        ("이직을 했는데 업무의 양이 많아", "이직을 했는데", "업무의 양이 많아"),
        ("아니 난 이직을 했다니까!", "아니 난 이직을 했다니까", "!"),
        ("회사 옮겼는데 적응이 힘들어", "회사 옮겼는데", "적응이 힘들어"),
        ("새 직장에 들어갔는데 상사가 힘들어", "새 직장에 들어갔는데", "상사가 힘들어"),
        ("작년에 이직했는데 언제쯤 안정될까", "작년에 이직했는데", "언제쯤 안정될까"),
        ("이직을 해서 환경이 바뀌었어", "이직을 해서", "환경이 바뀌었어"),
    ],
)
def test_job_change_report_clause_and_residual(text: str, clause: str, residual: str) -> None:
    assert job_change_report_clauses(text) == [clause]
    assert strip_job_change_report(text).strip() == residual


@pytest.mark.parametrize(
    "text",
    [
        "이직하면 어떨까",  # 가정형
        "이직했으면 좋겠어",  # 소원형
        "이직 안 했어",  # 부정형
        "남편이 이직을 했는데 괜찮을까",  # 제3자
        "올해 이직운 어때?",  # 완료형 없음
        "이직 언제 할 수 있을까",
        "오늘 해고통보를 받았어",  # 직장 이탈 계열은 별도 모듈
    ],
)
def test_job_change_report_rejects_non_reports(text: str) -> None:
    assert not is_job_change_report(text)
    assert strip_job_change_report(text) == text


def test_asks_new_job_change_marks_forward_ask() -> None:
    assert asks_new_job_change("이직을 했는데 또 이직할까?")
    assert asks_new_job_change("다시 이직할 시기는?")
    assert not asks_new_job_change("이직을 했는데 업무의 양이 많아")


def test_parser_strips_report_before_event_detection() -> None:
    it = parse_message("이직을 했는데 업무의 양이 많아 ", _T).intents[0]
    assert it.job_changed_reported is True
    assert it.event_key is None  # 보고 절의 '이직'은 앞으로의 사건이 아니다
    assert it.domain is Domain.CAREER  # 잔여 '업무'
    it2 = parse_message("이직을 했는데 또 이직할까?", _T).intents[0]
    assert it2.event_key is EventKey.CAREER_CHANGE  # 새 이직을 물으면 전망이 맞다


def test_user_facts_job_changed_slot_and_note() -> None:
    facts = extract_user_facts("이직을 했는데 업무의 양이 많아", turn=2)
    assert [f.key for f in facts] == ["job_changed"]
    block = user_facts_block(facts) or ""
    assert "이직 완료(사용자 진술)" in block and "이직은 이미 일어났다" in block
    assert not [f for f in extract_user_facts("남편이 이직을 했는데", 1) if f.key == "job_changed"]
    assert not [f for f in extract_user_facts("이직하면 어떨까", 1) if f.key == "job_changed"]


# ── ① 되물음 답 → 직전 시점 탐색 승계 ─────────────────────────────────────


def test_offer_answer_with_report_clause_links_and_inherits_timing_search() -> None:
    eng = ConversationEngine()
    st = ConversationState(thread_id="t")
    p, st, _, _ = eng.process_turn(st, _Q_WORKLOAD, _T)
    assert p.intents[0].query_type is QueryType.TIMING_SEARCH
    st.last_offer = (
        "업무의 양 때문인지 관계 스트레스 때문인지, 어느 쪽을 더 우선적으로 해결하고 싶으신가요?"
    )
    p, st, _, link = eng.process_turn(st, "이직을 했는데 업무의 양이 많아 ", _T)
    assert link.is_follow_up and link.link_kind is LinkKind.DRILL_DOWN
    it = p.intents[0]
    assert it.query_type is QueryType.TIMING_SEARCH and it.domain is Domain.CAREER
    assert it.event_key is None
    assert it.time_range is not None and it.time_range.type == "open_when"
    assert [f.key for f in st.user_facts] == ["job_changed"]


def test_offer_answer_without_report_still_blocks_new_domain() -> None:
    # 보고 절이 없는 되물음 답에 새 도메인 어휘가 있으면 기존대로 새 질문(과승계 차단 유지).
    eng = ConversationEngine()
    st = ConversationState(thread_id="t")
    _, st, _, _ = eng.process_turn(st, _Q_WORKLOAD, _T)
    st.last_offer = "어느 쪽을 더 우선적으로 해결하고 싶으신가요?"
    link = eng.link_question(st, "요즘 연애가 잘 안 풀리는데 어떻게 해야 할까")
    assert link.link_kind is LinkKind.NEW


# ── ③ 사실 단언형 이의 ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "아니 난 이직을 했다니까!", "아니요 이미 결혼했다니까요", "벌써 이사 갔거든",
        "아니 나 이직했잖아",
    ],
)
def test_asserted_fact_rebuttal_is_challenge(text: str) -> None:
    assert is_challenge(text)


@pytest.mark.parametrize(
    "text",
    [
        "아니 이직했어", "내가 아까 말한 아들 사주로", "3년 전에 이사했잖아",
        "이직을 했는데 업무가 많아",
    ],
)
def test_plain_statements_are_not_challenge(text: str) -> None:
    assert not is_challenge(text)


def test_challenge_turn_after_job_change_forecast() -> None:
    eng = ConversationEngine()
    st = ConversationState(thread_id="t")
    _, st, _, _ = eng.process_turn(st, _Q_OVERSEAS, _T)
    st.last_offer = "2027년 4월을 목표로 준비해 보는 건 어떠세요?"
    p, st, _, link = eng.process_turn(st, "아니 난 이직을 했다니까!", _T)
    assert link.link_kind is LinkKind.CHALLENGE
    assert p.intents[0].query_type is QueryType.FEEDBACK_CORRECTION
    assert p.intents[0].job_changed_reported is True
    assert [f.key for f in st.user_facts] == ["job_changed"]


# ── ⑤ '몇 년도' 5년 창 + 이후 기간 지정 ──────────────────────────────────


def test_year_when_parses_as_year_open_when_timing_search() -> None:
    it = parse_message("결혼은 몇 년도에 하게 될까", _T).intents[0]
    assert it.query_type is QueryType.TIMING_SEARCH
    assert it.time_range is not None and it.time_range.type == "open_when"
    assert it.time_range.granularity is Granularity.YEAR
    # '몇 년 걸릴까'는 기간이지 연도 탐색이 아니다
    assert parse_message("몇 년 걸릴까?", _T).intents[0].query_type is not QueryType.TIMING_SEARCH


def test_year_when_horizon_is_five_years_without_entry_window() -> None:
    q = _Q_OVERSEAS
    it = parse_message(q, _T).intents[0]
    h = resolve_horizon(q, it)
    assert h is not None and h.kind == "year_when"
    assert (h.years_span, h.months_detail, h.entry_window) == (5, 0, False)
    d = horizon_directive(h)
    assert "향후 5년을 기준으로 보면" in d and "연도 범위를 지정해 달라" in d
    assert "[진입 시기 두 칸]" not in d


def test_year_after_phrase_is_absolute_five_year_window() -> None:
    it = parse_message("2032년 이후는?", _T).intents[0]
    assert it.time_range is not None
    tr = it.time_range
    assert (tr.type, tr.start, tr.end) == ("absolute", "2032", "2036")
    assert it.time_range.granularity is Granularity.YEAR


@pytest.mark.parametrize(
    "text, start, end",
    [
        ("2032년부터 2036년까지는?", "2032", "2036"),
        ("2032~2036년은 어때?", "2032", "2036"),
        ("2032년 이후는?", "2032", "2036"),
        ("그 이후 5년은?", "2031", "2035"),  # 직전 창(올해부터 5년=2026~2030) 다음 해부터
        ("그럼 그 다음은?", "2031", "2035"),
    ],
)
def test_specified_period_after_year_when_becomes_window(text: str, start: str, end: str) -> None:
    eng = ConversationEngine()
    st = ConversationState(thread_id="t")
    _, st, _, _ = eng.process_turn(st, _Q_OVERSEAS, _T)
    st.last_offer = "그 이후 기간이 궁금하면 연도 범위를 지정해 주세요."
    p, _, _, link = eng.process_turn(st, text, _T)
    assert link.link_kind is LinkKind.TIME_SHIFT
    it = p.intents[0]
    assert it.query_type is QueryType.TIMING_SEARCH and it.domain is Domain.CAREER
    assert it.overseas_work == "assignment"  # 주제(해외 근무)도 같이 이어진다
    assert it.time_range is not None and (it.time_range.start, it.time_range.end) == (start, end)


# ── ④ 설명 요청 ────────────────────────────────────────────────────────────

_QUOTE = "해외 업무나 이동을 준비하신다면 서쪽인 申(신) 방위나 酉(유) 방위를 활용해 보세요."
_EXPLAIN = _QUOTE + "  \n위의 내용 쉽게 설명해줘 "


def test_explain_request_detection_and_target() -> None:
    assert detect_explain_request(_EXPLAIN)
    assert explain_target(_EXPLAIN) == _QUOTE
    assert not detect_explain_request("쉽게 설명해줘")  # 참조·인용 없음
    assert not detect_explain_request("이사 언제 가면 좋을지 자세히 알려줘")


def test_explain_request_parses_as_dialogue_act_without_time_or_event() -> None:
    pm = parse_message(_EXPLAIN, _T)
    assert len(pm.intents) == 1  # 인용 문장이 별도 질문 조각으로 쪼개지지 않는다
    it = pm.intents[0]
    assert it.dialogue_act == "explain_request" and it.explain_target == _QUOTE
    assert it.time_range is None and it.event_key is None and not it.event_keys
    # 용어 교육은 기존 규칙이 먼저
    term = parse_message("용신이 무슨 뜻이야", _T).intents[0]
    assert term.query_type is QueryType.TERMINOLOGY_EDUCATION


def test_explain_request_links_drill_down_and_does_not_inherit_timing() -> None:
    eng = ConversationEngine()
    st = ConversationState(thread_id="t")
    _, st, _, _ = eng.process_turn(st, _Q_OVERSEAS, _T)
    st.last_offer = "지금 해외 진출을 고민하게 된 계기가 무엇인가요?"
    p, _, _, link = eng.process_turn(st, _EXPLAIN, _T)
    assert link.link_kind is LinkKind.DRILL_DOWN
    it = p.intents[0]
    assert it.dialogue_act == "explain_request"
    assert it.time_range is None and it.event_key is None
    assert it.query_type is not QueryType.TIMING_SEARCH


# ── ⑥ 해외 근무 층 ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text, kind",
    [
        (_Q_OVERSEAS, "assignment"),
        ("해외 발령 날 수 있을까", "assignment"),
        ("해외 파견 나갈 수 있을까", "dispatch"),
        ("해외 취업은 언제쯤 될까", "local_hire"),
        ("이민 가면 어떨까", "emigration"),
        ("해외에서 일할 운이 있어?", "unspecified"),
        ("해외 여행 언제 가면 좋아?", None),
    ],
)
def test_detect_overseas_work_kind(text: str, kind: str | None) -> None:
    assert detect_overseas_work(text) == kind


def test_travel_only_is_not_overseas_work() -> None:
    assert is_travel_only("해외 여행 언제 가면 좋아?")
    assert not is_travel_only("해외 근무 여행도 자주 가는 일인데 언제쯤")


def test_parser_anchors_overseas_on_relocation_with_job_companions() -> None:
    it = parse_message(_Q_OVERSEAS, _T).intents[0]
    assert it.overseas_work == "assignment"
    assert it.domain is Domain.CAREER and it.event_key is EventKey.RELOCATION
    assert EventKey.PROMOTION in it.event_keys and EventKey.CAREER_CHANGE in it.event_keys
    it2 = parse_message("해외 취업은 언제쯤 될까", _T).intents[0]
    assert it2.event_key is EventKey.RELOCATION and it2.event_keys[0] is EventKey.JOB_GAIN
    it3 = parse_message("이민 가면 어떨까", _T).intents[0]
    assert it3.domain is Domain.RELOCATION and it3.overseas_work == "emigration"


@dataclass
class _C:
    event_key: EventKey
    period: str
    score: int


@dataclass
class _P:
    label: str
    ganji: str
    stem_ten_god: str
    branch_ten_god: str
    yongsin_alignment: str


def test_overseas_year_signals_tiers_and_hints() -> None:
    cands = [
        _C(EventKey.RELOCATION, "2027-03", 64), _C(EventKey.CONTRACT_DOCUMENT, "2027", 87),
        _C(EventKey.CAREER_CHANGE, "2028", 84),  # 이동 없음 → 직업 신호만
        _C(EventKey.RELOCATION, "2029", 45), _C(EventKey.PROMOTION, "2029-05", 50),  # 둘 다 40 이상
        _C(EventKey.RELOCATION, "2030", 70),  # 직업 없음 → 이동 신호만
    ]
    pillars = [
        _P("2027", "丁未", "정인", "겁재", "용신운"), _P("2028", "戊申", "비견", "식신", "용신운"),
        _P("2029", "己酉", "정관", "편재", "혼합"), _P("2030", "庚戌", "상관", "편인", "기신운"),
        _P("2031", "辛亥", "정재", "정관", "평운"),
    ]
    years = ["2027", "2028", "2029", "2030", "2031"]
    sig = overseas_year_signals(cands, pillars, years, "assignment")
    tiers = {s.year: s.tier for s in sig}
    assert tiers == {
        "2027": "strong", "2028": "job_only", "2029": "moderate", "2030": "move_only",
        "2031": "none",
    }
    assert sig[0].job_key is EventKey.CONTRACT_DOCUMENT and "인성 주도" in sig[0].hint
    assert "관성 주도" in sig[2].hint
    block = render_overseas_block(sig, "assignment")
    assert block[0].startswith("[해외 근무 신호") and "주재원·해외 발령" in block[0]
    assert "2027년 丁未 — 이동 64 · 직업 87(계약·문서) → 직장·거주 환경 동시 변화 가능성 — 강" in (
        block[1]
    )
    assert "직업 신호만" in block[2] and "이동 신호만" in block[4]
    assert "뚜렷한 신호 없음" in block[5]


# ── 채팅 dry-run — 프롬프트 계약 ───────────────────────────────────────────


def _dry(store: _MemStore, tid: str, q: str, offer: str | None = None) -> str:
    if offer is not None:
        st = store.load(tid)
        assert st is not None
        st.last_offer = offer
        store.save(st)
    r = cs.chat(_B, q, _T, dry_run=True, thread_id=tid, store=store, owner_id="t")
    assert r.status == "dry_run", r.answer
    return r.prompt_preview or ""


def _candidate_section(prompt: str) -> str:
    i = prompt.find("[이벤트 후보")
    j = prompt.find("\n[", i + 1)
    return prompt[i:j] if i >= 0 else ""


def _entry_candidate_lines(prompt: str) -> list[str]:
    """후보 줄('<사건> @ <기간>') 중 이직·입사 사건만 — 해석 본문의 어휘는 세지 않는다."""
    return re.findall(r"^(?:이직·직업 변화|취업[^@\n]*) @ [^\n]*", _candidate_section(prompt), re.M)


def test_chat_job_changed_drops_entry_candidates_and_pins_directive() -> None:
    store = _MemStore()
    _dry(store, "a", _Q_WORKLOAD)
    p = _dry(
        store, "a", "이직을 했는데 업무의 양이 많아 ",
        offer="어느 쪽을 더 우선적으로 해결하고 싶으신가요?",
    )
    assert "[이직 완료 — 사용자가 이미 이직했다고 알렸다]" in p
    assert "이직 완료(사용자 진술)" in p
    assert not _entry_candidate_lines(p)  # 이직·입사 후보 줄이 없다(해석 본문의 어휘는 무관)
    assert "[진입 시기 두 칸]" not in p


def test_chat_asserted_rebuttal_gets_challenge_contract_and_fact() -> None:
    store = _MemStore()
    _dry(store, "b", _Q_OVERSEAS)
    p = _dry(
        store, "b", "아니 난 이직을 했다니까!",
        offer="2027년 4월을 목표로 준비해 보는 건 어떠세요?",
    )
    assert "[정정 답 계약" in p and "[이직 완료 — 사용자가 이미 이직했다고 알렸다]" in p
    assert not _entry_candidate_lines(p)


def test_chat_year_when_overseas_prompt_has_signal_table_and_five_year_horizon() -> None:
    store = _MemStore()
    p = _dry(store, "c", _Q_OVERSEAS)
    assert "[답변 지평] 이 질문의 답변 지평은 '향후 5년(연 단위)'이다" in p
    assert "[진입 시기 두 칸]" not in p
    assert "[해외 근무 신호 — 이동 신호 × 직업 신호 동시 활성화" in p
    assert "[해외 근무 해석 규칙]" in p
    for y in ("2026년", "2027년", "2028년", "2029년", "2030년"):
        assert f"- {y}" in p
    p2 = _dry(
        store, "c", "2032년부터 2036년까지는?",
        offer="그 이후 기간이 궁금하면 연도 범위를 지정해 주세요.",
    )
    assert "[해외 근무 신호" in p2 and "- 2034년" in p2 and "- 2036년" in p2


def test_chat_explain_request_prompt_has_no_candidates_or_monthly_table() -> None:
    store = _MemStore()
    _dry(store, "d", _Q_OVERSEAS)
    p = _dry(store, "d", _EXPLAIN, offer="지금 해외 진출을 고민하게 된 계기가 무엇인가요?")
    assert "[설명 요청 — 사용자가 앞선 답의 한 부분" in p and f"[인용] {_QUOTE}" in p
    assert "[월별 요약" not in p and "[연도별 흐름" not in p
    assert "후보 없음" in _candidate_section(p) and " @ " not in _candidate_section(p)
    assert "[답변 지평]" not in p and "[해외 근무 신호" not in p
