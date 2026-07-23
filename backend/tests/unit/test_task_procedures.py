"""현실 과업 절차 레이어 회귀 (2026-07-22 승인 — 능력 탐문 라우트 + 절차 지식팩).

배경: '너 집 계약이 어떤 방식과 절차로 진행되는지 알고 있어?'가 일진 풀이로 응답되던
과잉 라우팅(테스터 신고). CAPABILITY_PROBE/PROCEDURE_QUERY는 명식·이벤트·LLM 미호출
즉답(policy — 질문권 미차감), MIXED_TASK 점검에는 L1/L2 절차 지식을 가산 주입한다.
L3(최신 규정·법률)는 자체 단정 금지 — expert_note 고지로 분리.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.task_procedures import (
    TASK_PACKS,
    build_capability_answer,
    detect_task_pack,
    procedure_reference_block,
)

_T = date(2026, 7, 22)


# ── 라우팅 판정 ────────────────────────────────────────────────

@pytest.mark.parametrize(
    "q",
    [
        "너 집 계약이 어떤 방식과 절차로 진행되는지 알고 있어?",
        "집 계약 순서가 어떻게 돼?",
        "이것도 상담 가능해?",
        "궁합도 볼 줄 알아?",
    ],
)
def test_probe_and_procedure_routed(q: str) -> None:
    assert build_capability_answer(q) is not None


@pytest.mark.parametrize(
    "q",
    [
        "9월에 계약해도 괜찮아?",   # 길흉 질문 — 분석 경로
        "언제 이사 갈지 알아?",     # 시기 질문 — 분석 경로
        "올해 이직운 어때?",
        "8월 대출 진행 시 주의할 점 알려줘",  # 과업 점검 — 분석 경로
    ],
)
def test_fortune_questions_not_routed(q: str) -> None:
    assert build_capability_answer(q) is None


def test_probe_answer_shows_scope_and_limits() -> None:
    ans = build_capability_answer("너 집 계약이 어떤 방식과 절차로 진행되는지 알고 있어?")
    assert ans is not None
    assert "자금계획" in ans and "잔금" in ans      # L1 단계 노출
    assert "확인이 필요" in ans                      # L3 한계 고지
    assert "시기·주의점" in ans                      # 상담 전환 유도


# ── 지식팩 ─────────────────────────────────────────────────────

def test_detect_pack_by_trigger_words() -> None:
    def _key(q: str) -> str:
        pack = detect_task_pack(q)
        assert pack is not None, q
        return pack.key

    assert _key("8월 대출과 인테리어 점검") == "housing"
    assert _key("입영 추첨이 걱정돼") == "selection"
    assert _key("면접이 다음 주야") == "employment"
    assert detect_task_pack("오늘 점심 뭐 먹지") is None


def test_procedure_block_has_l1_l2_and_l3_boundary() -> None:
    block = procedure_reference_block(TASK_PACKS["housing"])
    assert "[과업 절차 참고" in block and "운 신호가 아니라" in block
    assert "대출 승인이 나야 잔금" in block            # L1 의존관계
    assert "되돌리기 어려운 시점" in block              # L2
    assert "단정 금지" in block                        # L3 경계


# ── 서비스 경유 — policy 즉답(엔진·LLM 미호출) ────────────────

def test_capability_probe_returns_policy_route() -> None:
    from saju_api.services import chat_service
    from saju_shared_types.birth_input import BirthInput

    me = BirthInput(
        calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울", gender="male",
    )
    res = chat_service.chat(
        me, "너 집 계약이 어떤 방식과 절차로 진행되는지 알고 있어?", _T, True,
    )
    assert res.status == "policy"           # LLM·이벤트 미호출 즉답(질문권 미차감 라우트)
    assert res.answer and "자금계획" in res.answer
    assert res.prompt_preview is None       # dry_run 본문 없음 = 분석 파이프라인 미진입
