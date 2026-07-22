"""사용자 제공 사실 원장 P0 회귀 (2026-07-22 — 대화 연속성 사실 상속).

2026-07-22 테스터 스레드에서 사용자가 밝힌 사실("이미 계약 끝냈고"·"잔금만 남음"·
"손없는 날")이 매 턴 증발해 모순 서술·되묻기가 반복되던 결함의 구조적 해법. 쓰기
정책 불변식: user_explicit만 저장(엔진·LLM 산출물 금지), 상속은 슬롯 단위.
"""

from __future__ import annotations

from datetime import date

from saju_engines.conversation import ConversationEngine
from saju_engines.user_facts import (
    extract_user_facts,
    merge_user_facts,
    user_facts_block,
)
from saju_shared_types.conversation import ConversationState, UserFact

_T = date(2026, 7, 22)


# ── 추출 (실로그 문장) ─────────────────────────────────────────

def test_extract_from_tester_utterances() -> None:
    t1 = extract_user_facts(
        "이동에 적합한 일이 아니라도 그날 이사를 가게 됐는데 뭐 어쩔 수 없어. "
        "그나마 그날이 손없는 날이래.",
        turn=5,
    )
    keys = {f.key for f in t1}
    assert "unchangeable" in keys and "folk_condition" in keys

    t2 = extract_user_facts(
        "아니 ㅠㅠ 9월 30일날 딱 이사를 간다니까??? 이미 계약도 끝냈고 인테리어와 이사, "
        "잔금만 남았는데 그때까지 주의할 점을 얘기해달라고..",
        turn=8,
    )
    keys2 = {f.key for f in t2}
    assert "completed" in keys2 and "remaining" in keys2
    completed = next(f for f in t2 if f.key == "completed")
    assert "계약" in completed.quote  # 원문 인용 보존


def test_extract_fixed_schedule() -> None:
    facts = extract_user_facts("9월 30일에 이사가 예정되어있어. 주의사항 알려줘", turn=1)
    assert any(f.key == "fixed_schedule" for f in facts)


def test_no_facts_from_plain_question() -> None:
    assert extract_user_facts("올해 이직운 어때?", turn=1) == []


# ── 병합·정정·만료 ─────────────────────────────────────────────

def _state(facts: list[UserFact]) -> ConversationState:
    return ConversationState(thread_id="t", user_facts=facts)


def test_singleton_supersede_keeps_history() -> None:
    old = UserFact(key="fixed_schedule", quote="9월 30일에 이사가 예정되어있어", source_turn=1)
    new = UserFact(key="fixed_schedule", quote="10월 2일로 이사가 확정됐어", source_turn=3)
    merged = merge_user_facts(_state([old]), [new], topic_reset=False)
    assert len([f for f in merged if f.key == "fixed_schedule"]) == 1
    kept = next(f for f in merged if f.key == "fixed_schedule")
    assert kept.quote.startswith("10월 2일") and kept.superseded_quote is not None


def test_duplicate_accumulating_fact_deduped() -> None:
    f = UserFact(key="completed", quote="이미 계약도 끝냈고", source_turn=2)
    merged = merge_user_facts(_state([f]), [f.model_copy()], topic_reset=False)
    assert len(merged) == 1


def test_topic_reset_expires_topic_scope() -> None:
    topic = UserFact(key="remaining", quote="잔금만 남았는데", source_turn=2)
    global_ = UserFact(key="completed", quote="이미 결혼했고", scope="global", source_turn=1)
    merged = merge_user_facts(_state([topic, global_]), [], topic_reset=True)
    assert [f.key for f in merged] == ["completed"]


# ── 블록 렌더 ──────────────────────────────────────────────────

def test_block_renders_quotes_and_correction() -> None:
    facts = [
        UserFact(key="completed", quote="이미 계약도 끝냈고", source_turn=2),
        UserFact(
            key="fixed_schedule", quote="10월 2일로 확정됐어",
            superseded_quote="9월 30일 예정", source_turn=3,
        ),
    ]
    block = user_facts_block(facts)
    assert block is not None and "[사용자 제공 정보" in block
    assert "이미 계약도 끝냈고" in block
    assert "정정됨" in block and "9월 30일 예정" in block
    assert user_facts_block([]) is None


# ── 대화 계층 통합 — 턴 경유 축적 ─────────────────────────────

def test_facts_accumulate_across_turns() -> None:
    eng = ConversationEngine()
    st = ConversationState(thread_id="t")
    _, st, _, _ = eng.process_turn(
        st, "9월 30일에 이사가 예정되어있어. 주의사항 알려줘", _T, birth_year=1985
    )
    assert any(f.key == "fixed_schedule" for f in st.user_facts)
    _, st, _, _ = eng.process_turn(
        st, "이미 계약도 끝냈고 잔금만 남았는데 뭘 조심해야 해?", _T, birth_year=1985
    )
    keys = {f.key for f in st.user_facts}
    assert {"fixed_schedule", "completed", "remaining"} <= keys  # 이전 턴 사실 유지


# ── 커버리지 확대(2026-07-22 테스터 실문장 — 원장 빈 채 유지되던 결함) ──

def test_extract_decision_and_plan_statements() -> None:
    f1 = extract_user_facts(
        "나는 9월 30일에 이사가 결정되었어. 8~9월 동안 은행 대출과 인테리어를 진행해야되는데", 1
    )
    k1 = {f.key for f in f1}
    assert "fixed_schedule" in k1 and "planned_task" in k1

    f2 = extract_user_facts("계약서는 이미 다 썼고 그 날은 짐만 옮기는 날이야.", 2)
    k2 = {f.key for f in f2}
    assert "completed" in k2 and "day_plan" in k2

    f3 = extract_user_facts(
        "8월에는 은행 대출을 신청하고 인테리어 업체 선정이 마무리 될거야. 공사는 9월에 진행해.", 3
    )
    assert sum(1 for f in f3 if f.key == "planned_task") == 2  # 8월 신청·9월 공사 각각

    f4 = extract_user_facts("주택을 사기 위한 대출이겠지 ㅜㅜ", 4)
    assert any(f.key == "stated_purpose" for f in f4)


def test_fixed_schedule_clause_not_duplicated_as_plan() -> None:
    # 같은 절이 확정 일정과 계획 진술 둘 다에 걸리면 구체적인 쪽(fixed)만 남는다.
    facts = extract_user_facts("9월 30일에 이사가 결정되었어", 1)
    keys = [f.key for f in facts]
    assert keys.count("fixed_schedule") == 1 and "planned_task" not in keys
