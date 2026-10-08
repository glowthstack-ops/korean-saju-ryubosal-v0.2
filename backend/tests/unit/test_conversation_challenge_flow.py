"""추천 → 조건 → 모순 지적 다중 턴 회귀(2026-10-01, 실로그 web-mup4m82l 커튼 색).

네 가지 시나리오(데굴님 승인 설계):
  ① 같은 정보로 번복(실로그) — 4턴 이의가 CHALLENGE/Q12 로 잡히고, 프롬프트에 [이전 발언 원문]
     (T2 추천·T3 대체됨 양쪽)·[정정 답 계약]·배제 조건·[오행 보완 색](희신 金 포함)이 실리며, 되물음
     답(offer-answer) 지시는 붙지 않는다.
  ② 새 조건으로 정당 변경 — 원장은 이전 건을 삭제하지 않고 superseded 이력으로 남긴다.
  ③ 사용자 오기억 — 원장에 없는 발언은 매치가 비어 '그 말씀은 드리지 않았다' 경로로 간다.
  ④ 철회된 추천 재등장 — 배제 조건 재제시를 shadow 감사가 잡는다(test_commitment_audit).
3턴 "녹색을 추가해도 돼?"는 NEW 가 아니라 선택지 확인 후속(CONSTRAINT_ADD)으로 이어진다.
"""

from __future__ import annotations

from datetime import date, time

import pytest

from saju_api.services import chat_service
from saju_engines.assistant_commitments import extract_commitments, merge_commitments
from saju_engines.conversation import ConversationEngine
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.conversation import ConversationState, LinkKind
from saju_shared_types.intent import QueryType

_T = date(2026, 10, 1)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date=date(2015, 3, 1), birth_time=time(3, 34),
    birth_place_name="서울 도봉구", gender="male", latitude=37.6691, longitude=127.0324,
    timezone="Asia/Seoul",
)
_Q = [
    "이 사주의 학업운을 향상시킬 수 있는 색깔은 뭐야?",
    "커텐으로 할건데 붉은색은 좀 그래. 다른색을 추천해줘.",
    "지금 인성과다라서 공부할때 잡생각이 많은데 녹색을 추가해도 돼?",
    "니가 연두색이나 초록색계열 커튼을 추천해줬잖아",
]
# 실답 요지(원장 추출 대상 문장만).
_A = [
    "아들님, 학업운을 북돋아 줄 색깔은 용신인 불의 기운을 상징하는 붉은색 계열이에요. "
    "책상 위에 붉은색 필기구나 메모지를 두어 시선이 닿게 하는 것만으로도 집중력을 모으는 데 큰 "
    "도움이 돼요. "
    "올해 안에 꼭 마무리하고 싶은 공부 목표가 하나 있나요?",
    "붉은색이 부담스럽다면 같은 화 오행에 속하면서도 조금 더 부드러운 분홍색이나 보라색, 혹은 화를 "
    "생해주는 "
    "목 기운의 연두색이나 초록색 계열을 선택해 보세요. "
    "그 목표를 위해 12월에 어떤 서류나 자격을 먼저 준비해두면 좋을까요?",
    "아들님, 사주에 목 기운이 이미 두터운 상태에서 녹색을 더하는 것은 오히려 생각의 짐을 무겁게 할 "
    "수 있어요. "
    "지금 준비하고 있는 공부 중에서 가장 먼저 눈에 보이는 결과로 나타내고 싶은 목표는 무엇인가요?",
]


class _MemStore:
    """DB 없는 스레드 저장소 — chat() 의 migrate/load/save 계약만 만족한다."""

    def __init__(self) -> None:
        self._s: dict[str, ConversationState] = {}

    def migrate(self) -> None:
        return None

    def load(self, thread_id: str) -> ConversationState | None:
        return self._s.get(thread_id)

    def save(self, state: ConversationState, owner_id: str = "default") -> None:
        self._s[state.thread_id] = state


def _engine_trace() -> list[tuple[LinkKind, QueryType, ConversationState]]:
    eng = ConversationEngine()
    st = ConversationState(thread_id="t")
    out: list[tuple[LinkKind, QueryType, ConversationState]] = []
    for i, q in enumerate(_Q):
        parsed, st, _, link = eng.process_turn(st, q, _T, birth_year=2015)
        out.append((link.link_kind, parsed.intents[0].query_type, st))
        if i < len(_A):
            st.assistant_commitments = merge_commitments(
                st.assistant_commitments, extract_commitments(_A[i], st.turn_no, "education")
            )
    return out


def test_challenge_turn_links_as_challenge_and_routes_q12() -> None:
    trace = _engine_trace()
    kind4, qtype4, st4 = trace[3]
    assert kind4 is LinkKind.CHALLENGE
    assert qtype4 is QueryType.FEEDBACK_CORRECTION
    keys = {f.key for f in st4.user_facts}
    assert {"excluded_option", "user_claim"} <= keys  # 붉은색 배제 + '인성과다' 사용자 해석 저장


def test_option_check_turn_is_followup_not_new() -> None:
    kind3, _, _ = _engine_trace()[2]
    assert kind3 is LinkKind.CONSTRAINT_ADD  # '녹색을 추가해도 돼?' — 앞서 추천한 선택지 확인


def test_ledger_keeps_reversal_history() -> None:
    _, _, st4 = _engine_trace()[3]
    green = [c for c in st4.assistant_commitments if "연두색" in c.quote]
    assert green and green[0].status == "superseded" and green[0].superseded_by_turn == 3


def _chat_turns() -> list[str]:
    store = _MemStore()
    tid = "challenge-flow"
    prompts: list[str] = []
    prior: str | None = None
    for i, q in enumerate(_Q):
        res = chat_service.chat(
            _BIRTH, q, _T, dry_run=True, thread_id=tid, store=store, subject_label="아들",
            prior_answer=prior,
        )
        assert res.status == "dry_run", res.answer
        prompts.append(res.prompt_preview or "")
        if i < len(_A):
            chat_service.update_thread_offer(tid, _A[i], store)  # 비동기 경로 계약과 동일
            prior = _A[i]
    return prompts


def test_chat_prompt_composition_across_turns() -> None:
    p1, p2, p3, p4 = _chat_turns()
    # T1: 색 질문 → 오행 보완 색 표(희신 金 포함), 라우팅은 분석 흐름 유지.
    assert "[오행 보완 색" in p1 and "희신 金" in p1
    # T2: 요청형 후속은 되물음의 '답'이 아니다 + 배제 조건이 사용자 정보 블록에 실린다.
    assert "이번 발화는 그 질문에 대한 답" not in p2
    assert "(배제 조건)" in p2 and "붉은색은 좀 그래" in p2
    # T3: 선택지 확인 — 이전 추천 원문 + 사용자 해석 라벨 + 지목 색 역할.
    assert "[이전 발언 원문" in p3 and "연두색이나 초록색" in p3
    assert "(사용자 명리 해석)" in p3
    assert "지목한 색 '녹색' = 木(기신)" in p3
    # T4: 이의 — 정정 답 계약 + 번복 양쪽 원문 + offer 답 지시 없음.
    assert "[정정 답 계약" in p4
    assert "T2 추천·T3에서 반대 발언으로 대체됨" in p4 and "T3 비권장·유효" in p4
    assert "이번 발화는 그 질문에 대한 답" not in p4
    assert "[오행 보완 색" in p4 and "지목한 색 '연두색' = 木(기신)" in p4


def test_user_misremembers_yields_no_prior_statements() -> None:
    from saju_engines.assistant_commitments import match_commitments

    _, _, st4 = _engine_trace()[3]
    assert match_commitments(st4.assistant_commitments, "니가 노란색 커튼을 추천했잖아") == []


# ── 재물 동의어(2026-10-01 실로그: '내 10월 금전 운세는 어때?' → general 월 총운) ──────────

@pytest.mark.parametrize(
    "q",
    ["내 10월 금전 운세는 어때?", "10월 금전운 어때?", "올해 재정 상태는?", "내년 자금 흐름 어때?"],
)
def test_money_synonyms_route_to_wealth_domain(q: str) -> None:
    from saju_engines.query_parser import parse_message
    from saju_shared_types.intent import Domain

    i = parse_message(q, _T).intents[0]
    assert i.domain is Domain.WEALTH
    assert i.query_type is not QueryType.FORTUNE_OVERVIEW
