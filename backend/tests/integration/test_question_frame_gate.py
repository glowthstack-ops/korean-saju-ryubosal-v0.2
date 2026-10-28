"""질문 이해 층 게이트 — 룰 Q1/GENERAL 폴백 턴의 색·방향·음식·장소 보정 회귀(dry_run, 2026-10-28).

소형 모델 호출은 monkeypatch(네트워크 없음). 실측 결함군: '커텐 색 추천해줘'·'침대헤드방향은?'·
'보금자리 옮기는 거 어떨까?'가 전부 Q1 폴백 → too_broad 바운스였다.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from saju_api.services import chat_service, llm_client, question_frame_service
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import Domain, QueryType  # noqa: F401 — Domain 은 보정 검사용

_TODAY = date(2026, 10, 28)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date=_TODAY.isoformat(),
)


def _frame(item: str, ask: str = "recommendation", shape: str = "short_pick") -> str:
    return (
        f'{{"ask_kind":"{ask}","lifestyle_item":"{item}","answer_shape":"{shape}",'
        '"brevity":"short","topic_object":"t"}'
    )


@pytest.fixture
def gate_on(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setenv(question_frame_service.GATE_FLAG, "1")
    monkeypatch.setenv(question_frame_service.ENV_FLAG, "0")
    monkeypatch.setattr(question_frame_service, "_record", lambda shadow: None)
    box: dict[str, Any] = {"reply": _frame("none"), "calls": 0}

    def fake_call(role: str, system: str, prompt: str, **kw: Any) -> tuple[str, int, int]:
        box["calls"] += 1
        return box["reply"], 600, 30

    monkeypatch.setattr(llm_client, "call_role_raw", fake_call)
    return box


def test_color_fallback_is_routed_to_color_remedy(gate_on: dict[str, Any]) -> None:
    gate_on["reply"] = _frame("color")
    res = chat_service.chat(_BIRTH, "커텐 색 추천해줘", _TODAY, dry_run=True)
    assert res.status == "dry_run", res.answer  # 이전: too_broad 바운스
    assert res.prompt_preview is not None
    assert "[오행 보완 색 — 용희기구한 기준" in res.prompt_preview
    assert gate_on["calls"] == 1


def test_direction_fallback_is_routed_to_direction_remedy(gate_on: dict[str, Any]) -> None:
    gate_on["reply"] = _frame("direction", ask="judgment")
    res = chat_service.chat(_BIRTH, "침대헤드방향은?", _TODAY, dry_run=True)
    assert res.status == "dry_run", res.answer
    assert res.prompt_preview is not None
    assert "[오행 보완 방향" in res.prompt_preview or "방위" in res.prompt_preview


def test_place_fallback_is_routed_to_relocation(gate_on: dict[str, Any]) -> None:
    gate_on["reply"] = _frame("place", shape="analysis")
    res = chat_service.chat(_BIRTH, "보금자리 옮기는 거 어떨까?", _TODAY, dry_run=True)
    assert res.status == "dry_run", res.answer
    # 응답의 intents 는 파서 원본이라 보정은 프롬프트·판정으로 확인한다 — 거주 분야 기본 기간 +
    # 이사 해석 재료(이사 이유·집 성격, 지역 오행 추천)가 실린다.
    assert res.assessment is not None and res.assessment.status == "apply_default_period"
    assert res.prompt_preview is not None
    assert "[이사 이유·집 성격" in res.prompt_preview or "[지역 오행 추천" in res.prompt_preview


def test_gate_never_overrides_rule_confirmed_turn(gate_on: dict[str, Any]) -> None:
    gate_on["reply"] = _frame("color")
    res = chat_service.chat(_BIRTH, "올해 재물운 어때?", _TODAY, dry_run=True)
    assert res.status == "dry_run"
    assert res.intents[0].query_type is QueryType.DOMAIN_ANALYSIS
    assert res.intents[0].domain is Domain.WEALTH and res.intents[0].color_question is False
    assert gate_on["calls"] == 0  # 폴백 턴이 아니면 동기 호출 자체를 하지 않는다


def test_unsupported_item_leaves_fallback_untouched(gate_on: dict[str, Any]) -> None:
    gate_on["reply"] = _frame("clothing")  # 엔진 층 없음 — 보정 대상 아님(검색 보충 후 추가)
    res = chat_service.chat(_BIRTH, "오늘 옷 뭐 입을까", _TODAY, dry_run=True)
    assert res.intents[0].query_type is QueryType.FORTUNE_OVERVIEW
    assert res.intents[0].color_question is False and res.intents[0].food_question is False


def test_gate_off_keeps_shadow_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(question_frame_service.GATE_FLAG, "0")
    monkeypatch.setenv(question_frame_service.ENV_FLAG, "0")
    called: list[str] = []
    monkeypatch.setattr(
        llm_client, "call_role_raw", lambda *a, **k: called.append("x") or (_frame("color"), 1, 1),
    )
    res = chat_service.chat(_BIRTH, "커텐 색 추천해줘", _TODAY, dry_run=True)
    assert res.status == "too_broad" and called == []


# ── A안(2026-10-28 "권장대로"): clothing=색 층, activity/grooming=답 형태 지시만 ───────────


def test_clothing_fallback_uses_color_layer(gate_on: dict[str, Any]) -> None:
    gate_on["reply"] = _frame("clothing")
    res = chat_service.chat(_BIRTH, "오늘 옷 뭐 입을까", _TODAY, dry_run=True)
    assert res.status == "dry_run", res.answer
    assert res.prompt_preview is not None
    assert "[오행 보완 색 — 용희기구한 기준" in res.prompt_preview  # 옷=색(소재 사전 없음)


def test_activity_with_day_gets_judgment_directive_not_overview(gate_on: dict[str, Any]) -> None:
    gate_on["reply"] = (
        '{"ask_kind":"judgment","lifestyle_item":"activity","answer_shape":"short_pick",'
        '"brevity":"short","topic_object":"오늘 운동"}'
    )
    res = chat_service.chat(_BIRTH, "오늘 운동해도 돼?", _TODAY, dry_run=True)
    assert res.status == "dry_run", res.answer
    p = res.prompt_preview or ""
    assert "[행동 가부 질문 — 말미 고정] 이 턴은 '오늘 운동'을(를)" in p
    assert "[질문한 날짜의 일운 — 엔진 확정 사실] 2026-10-28" in p
    for banned in (
        "[이벤트 후보 — ", "[원국 횡재 그릇", "[연애 유형 — ", "질문 기간 내 해당 도메인 후보 없음",
    ):
        assert banned not in p, banned


def test_activity_without_time_still_asks_to_narrow(gate_on: dict[str, Any]) -> None:
    gate_on["reply"] = (
        '{"ask_kind":"judgment","lifestyle_item":"activity","answer_shape":"short_pick",'
        '"brevity":"short","topic_object":"운동 지속"}'
    )
    res = chat_service.chat(_BIRTH, "운동 계속 해도 돼?", _TODAY, dry_run=True)
    assert res.status == "too_broad"  # 시점 없음 — 데굴님 결정: 지금처럼 되묻기


def test_grooming_with_day_is_activity_judgment(gate_on: dict[str, Any]) -> None:
    gate_on["reply"] = (
        '{"ask_kind":"judgment","lifestyle_item":"grooming","answer_shape":"short_pick",'
        '"brevity":"short","topic_object":"오늘 머리 자르기"}'
    )
    res = chat_service.chat(_BIRTH, "오늘 머리 자를까", _TODAY, dry_run=True)
    assert res.status == "dry_run", res.answer
    p = res.prompt_preview or ""
    assert "[행동 가부 질문 — 말미 고정] 이 턴은 '오늘 머리 자르기'을(를)" in p
