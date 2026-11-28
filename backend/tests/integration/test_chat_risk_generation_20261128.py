"""채팅 생성 단계 단일 진입점 + 위험 흐름 1회 실행(2026-11-28 데굴님 지적·승인).

배경: 라우터는 모든 채팅을 `chat(dry_run=True)` 로 준비한 뒤 따로 생성한다. 위험 INJECTED
실호출이 준비 단계 안에 있어 (1) 구조화 호출 결과가 매번 버려지고 같은 입력으로 한 번 더
호출됐고 (2) 그 호출은 사용량 기록·thinking 설정·소진 신호 처리에서 빠져 있었으며 (3) 감사된
답은 운영에서 한 번도 전달되지 않았다.

성공 조건: 준비 단계 호출 0회 · 생성 단계에서 위험 흐름 1회(감사된 답 전달, 일반 생성 미호출) ·
후처리 전체가 최종 감사 앞(renderer)에서 실행 · 공급자 장애·소진·중단이면 위험 요소 없는 본문의
일반 경로 · 구조화 호출 1건마다 사용량 적재 + 메인 프로필 생성 옵션(thinkingConfig) 전달.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest

from saju_api.services import chat_service, gemini_token_adapter, llm_client
from saju_api.services import risk_exposure_bootstrap as reb
from saju_api.services.token_counter_registry import ProviderRequest
from saju_engines.risk_exposure import (
    RISK_EXPOSURE_SUPPRESSED_GUARD,
    RISK_SAFE_FALLBACK_TEMPLATE,
)
from saju_shared_types.birth_input import BirthInput

_TODAY = date(2026, 6, 11)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date="2026-06-11",
)
_QUESTION = "올해 하반기 전체 운세 알려줘"
_BASELINE = "기준 본문"
_INJECTED = "기준 본문\n[위험 블록 대역]"


@pytest.fixture(scope="module")
def base_ctx() -> chat_service.ChatPostprocessContext:
    """실제 준비 단계(dry_run — LLM 미호출)가 만든 후처리 맥락."""
    res = chat_service.chat(_BIRTH, _QUESTION, _TODAY, dry_run=True)
    assert res.status == "dry_run" and res.postprocess is not None
    return res.postprocess


def _ctx_with_plan(
    base: chat_service.ChatPostprocessContext, followups: list | None = None,
) -> chat_service.ChatPostprocessContext:
    plan = chat_service.RiskGenerationPlan(
        baseline_prompt=_BASELINE, injected_prompt=_INJECTED, system="시스템",
        observability={"disposition": "INJECTED"}, payload={"llmRiskEpisodes": [{"k": "v"}]},
        call_type="chat_single", request_context_id="t1:3", followups=followups or [],
    )
    return base.model_copy(update={"prompt_text": _INJECTED, "risk_plan": plan})


class _Harness:
    """위험 흐름·일반 생성·후처리를 기록용 대역으로 바꾼다."""

    def __init__(self, monkeypatch, flow_result: dict | Exception, ready: bool = True) -> None:
        self.flow_calls: list[dict] = []
        self.plain_calls: list[dict] = []
        self.finalized: list[tuple[str, str]] = []
        self._flow_result = flow_result

        def fake_flow(**kwargs: Any) -> dict:
            self.flow_calls.append(kwargs)
            if isinstance(self._flow_result, Exception):
                raise self._flow_result
            out = dict(self._flow_result)
            if out.get("final_text") == "<render>":
                out["final_text"] = kwargs["renderer"]("초안 ~~지움~~")
            return out

        def fake_plain(prompt: str, **kwargs: Any) -> str:
            self.plain_calls.append({"prompt": prompt, **kwargs})
            return "일반 답"

        def fake_finalize(answer: str, ctx: Any, thread_id: str | None = None) -> str:
            self.finalized.append((answer, ctx.prompt_text if ctx is not None else ""))
            return f"[후처리]{answer}"

        monkeypatch.setattr(reb, "run_exposed_reading", fake_flow)
        monkeypatch.setattr(chat_service.llm_client, "generate_reading", fake_plain)
        monkeypatch.setattr(chat_service, "finalize_answer_full", fake_finalize)
        monkeypatch.setattr(chat_service.llm_client, "direct_primary_call_ready", lambda: ready)


def _generate(ctx: chat_service.ChatPostprocessContext) -> tuple[str, str | None]:
    return chat_service.generate_chat_answer(
        _INJECTED, call_type="chat_single", system="시스템", postprocess=ctx,
        owner_id="owner-1", thread_id="t1",
    )


# ── 생성 단계: 위험 흐름 1회 ─────────────────────────────────────────


def test_risk_turn_runs_flow_once_and_skips_plain_call(monkeypatch, base_ctx) -> None:
    """위험 블록이 실린 턴 — 위험 흐름 1회, 일반 생성 0회, 감사된 답이 그대로 전달된다."""
    h = _Harness(monkeypatch, {"outcome": "DELIVER_GENERATED", "final_text": "<render>",
                               "attempts": [{"kind": "INITIAL"}], "provider_reports": 1})
    answer, outcome = _generate(_ctx_with_plan(base_ctx))
    assert outcome == "DELIVER_GENERATED"
    assert len(h.flow_calls) == 1 and h.plain_calls == []
    call = h.flow_calls[0]
    assert call["injected_prompt"] == _INJECTED and call["baseline_prompt"] == _BASELINE
    # 사용량 적재에 필요한 맥락이 흐름까지 간다.
    assert (call["owner_id"], call["ref_id"], call["surface"]) == ("owner-1", "t1", "chat")
    # renderer = 출력 정리 → 후처리 전체. 커리어 재생성이 위험 블록 본문을 쓰지 않게 원문을 넘긴다.
    assert answer == "[후처리]초안"  # 취소선은 출력 정리가 지운다
    assert h.finalized == [("초안", _BASELINE)]


def test_non_risk_turn_uses_plain_generation(monkeypatch, base_ctx) -> None:
    """반례 — 위험 계획이 없으면 일반 생성 1회 + 후처리, 위험 흐름은 돌지 않는다."""
    h = _Harness(monkeypatch, {"outcome": "DELIVER_GENERATED", "final_text": "x"})
    answer, outcome = chat_service.generate_chat_answer(
        "일반 본문", call_type="chat_single", system=None, postprocess=base_ctx,
        owner_id=None, thread_id=None,
    )
    assert (answer, outcome) == ("[후처리]일반 답", None)
    assert h.flow_calls == [] and h.plain_calls[0]["prompt"] == "일반 본문"


def test_safe_template_is_not_postprocessed(monkeypatch, base_ctx) -> None:
    """고정 안전 문구에는 명식 후처리(단식 문단 삽입 등)를 붙이지 않는다."""
    h = _Harness(monkeypatch, {"outcome": "DELIVER_GENERATED", "final_text": "x"})
    _generate(_ctx_with_plan(base_ctx))
    render = h.flow_calls[0]["renderer"]
    assert render(RISK_SAFE_FALLBACK_TEMPLATE) == RISK_SAFE_FALLBACK_TEMPLATE
    assert h.finalized == []


def test_safe_fallback_from_audit_is_delivered(monkeypatch, base_ctx) -> None:
    """감사 실패로 끝난 안전 문구는 그대로 전달한다(일반 경로로 다시 부르지 않는다)."""
    h = _Harness(monkeypatch, {
        "outcome": "DELIVER_SAFE_FALLBACK", "final_text": RISK_SAFE_FALLBACK_TEMPLATE,
        "attempts": [{"kind": "INITIAL", "audit_issues": ["PROHIBITED_CLAIM:rg1"]},
                     {"kind": "REVISION_1", "audit_issues": ["PROHIBITED_CLAIM:rg1"]}],
    })
    answer, outcome = _generate(_ctx_with_plan(base_ctx))
    assert (answer, outcome) == (RISK_SAFE_FALLBACK_TEMPLATE, "DELIVER_SAFE_FALLBACK")
    assert h.plain_calls == []


@pytest.mark.parametrize("flow_result", [
    # provider 장애로 안전 문구만 남음 → 폴백 공급자가 있는 일반 경로
    {"outcome": "DELIVER_SAFE_FALLBACK", "final_text": RISK_SAFE_FALLBACK_TEMPLATE,
     "attempts": [{"kind": "INITIAL", "audit_issues": ["PROVIDER_CALL_FAILED"]},
                  {"kind": "REGENERATE_WITHOUT_RISK", "audit_issues": ["PROVIDER_CALL_FAILED"]}]},
    # 흐름 인프라 장애
    RuntimeError("manifest 불가"),
])
def test_provider_or_infra_failure_falls_back_without_risk(
    monkeypatch, base_ctx, flow_result,
) -> None:
    """공급자·인프라 장애면 위험 요소가 없는 본문 + 억제 가드로 일반 생성한다."""
    h = _Harness(monkeypatch, flow_result)
    answer, outcome = _generate(_ctx_with_plan(base_ctx))
    assert (answer, outcome) == ("[후처리]일반 답", None)
    assert len(h.plain_calls) == 1
    sent = h.plain_calls[0]["prompt"]
    assert sent == _BASELINE + "\n" + RISK_EXPOSURE_SUPPRESSED_GUARD
    assert "[위험 블록 대역]" not in sent  # 위험 요소는 감사 없이 나가지 않는다
    assert h.finalized[-1] == ("일반 답", sent)  # 후처리 맥락의 본문도 같은 것으로 바뀐다


def test_primary_unavailable_skips_flow(monkeypatch, base_ctx) -> None:
    """중단·메인 공급자 쿨다운이면 위험 흐름을 돌리지 않고 일반 경로(폴백·중단 처리)로 간다."""
    h = _Harness(monkeypatch, {"outcome": "DELIVER_GENERATED", "final_text": "x"}, ready=False)
    answer, outcome = _generate(_ctx_with_plan(base_ctx))
    assert h.flow_calls == [] and outcome is None
    assert h.plain_calls[0]["prompt"].endswith(RISK_EXPOSURE_SUPPRESSED_GUARD)


def test_block_outcome_raises(monkeypatch, base_ctx) -> None:
    """BLOCK 은 전달 금지 — 호출처가 일반 실패 문구로 마감하도록 예외로 올린다."""
    h = _Harness(monkeypatch, {"outcome": "BLOCK", "final_text": "", "attempts": []})
    with pytest.raises(chat_service.RiskAnswerBlocked):
        _generate(_ctx_with_plan(base_ctx))
    assert h.plain_calls == []


def test_input_budget_checked_before_flow(monkeypatch, base_ctx) -> None:
    """주입 본문이 입력 한도를 넘으면 흐름 전에 막힌다(일반 경로의 호출 직전 검사와 같은 기준)."""
    from saju_engines.llm_guard import TokenBudgetExceeded

    h = _Harness(monkeypatch, {"outcome": "DELIVER_GENERATED", "final_text": "x"})

    def _over(prompt: str, system: str | None, call_type: str) -> None:
        raise TokenBudgetExceeded("초과")

    monkeypatch.setattr(chat_service.llm_client, "check_input_budget", _over)
    with pytest.raises(TokenBudgetExceeded):
        _generate(_ctx_with_plan(base_ctx))
    assert h.flow_calls == [] and h.plain_calls == []


# ── 후속 질문 참조 등록 ───────────────────────────────────────────────


def test_followups_only_for_delivered_generated(base_ctx) -> None:
    """위험 episode 참조는 감사 통과 답이 전달된 턴에만 등록한다(안전 문구·일반 경로는 미등록)."""
    from saju_api.routers.chat import _risk_followups_for
    from saju_shared_types.conversation import ResultSummaryRef

    ref = ResultSummaryRef(kind="risk_episode", label="k|finance|2026", detail="d")
    ctx = _ctx_with_plan(base_ctx, followups=[ref])
    assert _risk_followups_for(ctx, "DELIVER_GENERATED") == [ref]
    assert _risk_followups_for(ctx, "DELIVER_SAFE_FALLBACK") is None
    assert _risk_followups_for(ctx, None) is None
    assert _risk_followups_for(base_ctx, "DELIVER_GENERATED") is None  # 계획 없음


def test_risk_followups_from_payload() -> None:
    """노출 수준 none·키 없는 기록은 빼고 최대 3건."""
    recs = [
        {"diagnostics": {"episodeKey": f"k{i}", "startPeriod": "2026-12"},
         "domains": ["finance"], "presentationLevel": "watch"}
        for i in range(4)
    ]
    recs.insert(0, {"diagnostics": {"episodeKey": "hidden"}, "presentationLevel": "none"})
    recs.insert(0, {"diagnostics": {}, "presentationLevel": "watch"})
    out = chat_service._risk_followups({"presentationRecords": recs})
    assert [r.label for r in out] == ["k0|finance|2026", "k1|finance|2026", "k2|finance|2026"]


# ── 구조화 호출: 사용량·생성 옵션·소진 처리 ──────────────────────────


def _run_exposed(monkeypatch, *, ready: bool = True, fail: Exception | None = None) -> dict:
    """run_exposed_reading 을 상태기 대역(초안 1회 호출)으로 돌려 `_llm_call` 배선만 본다."""
    from saju_api.services import risk_exposure_service as svc
    from saju_api.services import risk_llm_pipeline as pipe
    from saju_api.services import risk_validation_lease as lease
    from saju_api.services import token_counter_registry as reg
    from saju_engines import risk_exposure as rexp

    seen: dict[str, Any] = {"structured": [], "usage": [], "noted": []}

    def fake_structured(request: ProviderRequest, model_id: str, **kwargs: Any) -> dict:
        seen["structured"].append({"model": model_id, **kwargs})
        if fail is not None:
            raise fail
        return {"text": '{"main_answer": "답", "risk_guidance": []}', "prompt_tokens": 27000,
                "cached_tokens": 100, "output_tokens": 700, "thoughts_tokens": 50,
                "model_version": "m1", "finish_reason": "STOP"}

    def fake_state_machine(**kwargs: Any) -> dict:
        try:
            out = kwargs["llm_call"](kwargs["initial_request"])
        except Exception as exc:  # noqa: BLE001 — 상태기처럼 attempt 실패로 접는다
            return {"outcome": "DELIVER_SAFE_FALLBACK", "final_text": "",
                    "attempts": [{"kind": "INITIAL", "audit_issues": ["PROVIDER_CALL_FAILED"],
                                  "error": type(exc).__name__}]}
        return {"outcome": "DELIVER_GENERATED", "final_text": out["answer"], "attempts": []}

    monkeypatch.setattr(svc, "_load_manifest_snapshot",
                        lambda: {"validated_token_counters": []})
    monkeypatch.setattr(reg, "resolve_expose_counter", lambda *a, **k: None)
    monkeypatch.setattr(lease, "load_valid_lease", lambda *a, **k: None)
    monkeypatch.setattr(reb, "exposure_runtime_inputs", lambda call_type: {
        "context_limit": 100_000, "response_reserve": 2_000,
        "reviewed_shape_digests": frozenset()})
    monkeypatch.setattr(rexp, "build_guidance_reference_context", lambda *a, **k: object())
    monkeypatch.setattr(pipe, "build_risk_execution_context", lambda *a, **k: object())
    monkeypatch.setattr(pipe, "run_injected_risk_flow", fake_state_machine)
    monkeypatch.setattr(gemini_token_adapter, "generate_structured", fake_structured)
    monkeypatch.setattr(llm_client, "reading_model", lambda: "m1")
    monkeypatch.setattr(llm_client, "direct_primary_call_ready", lambda: ready)
    monkeypatch.setattr(llm_client, "primary_generation_extras",
                        lambda: {"thinkingConfig": {"thinkingLevel": "LOW"}})
    monkeypatch.setattr(llm_client, "record_direct_primary_call",
                        lambda **k: seen["usage"].append(k))
    monkeypatch.setattr(llm_client, "note_direct_primary_error",
                        lambda exc, **k: seen["noted"].append(k) or True)
    seen["result"] = reb.run_exposed_reading(
        baseline_prompt=_BASELINE, injected_prompt=_INJECTED, system="시스템",
        observability={"risk_output_schemas": {"gemini_transport": {"type": "OBJECT"}}},
        payload={"llmRiskEpisodes": []}, call_type="chat_single",
        request_context_id="t1:3", renderer=lambda s: s,
        owner_id="owner-1", ref_id="t1", surface="chat",
    )
    return seen


def test_structured_call_records_usage_and_sends_thinking_config(monkeypatch) -> None:
    """구조화 호출 1건 = 사용량 1건(일반 생성과 같은 칸) + 메인 프로필 생성 옵션 전달."""
    seen = _run_exposed(monkeypatch)
    assert seen["result"]["outcome"] == "DELIVER_GENERATED"
    assert seen["structured"][0]["generation_extras"] == {
        "thinkingConfig": {"thinkingLevel": "LOW"}}
    assert seen["usage"] == [{
        "call_type": "chat_single", "input_tokens": 27000, "output_tokens": 700,
        "cached_tokens": 100, "owner_id": "owner-1", "surface": "chat", "ref_id": "t1",
        "product_code": "CHAT",
    }]
    assert seen["result"]["thoughts_tokens"] == 50


def test_structured_call_not_sent_when_primary_unavailable(monkeypatch) -> None:
    """중단·쿨다운이면 실패할 호출을 네트워크에 내지 않는다(사용량도 없음)."""
    seen = _run_exposed(monkeypatch, ready=False)
    assert seen["structured"] == [] and seen["usage"] == []
    assert seen["result"]["outcome"] == "DELIVER_SAFE_FALLBACK"


def test_structured_http_error_is_classified_for_quota(monkeypatch) -> None:
    """HTTP 오류는 소진 분류로 넘긴다 — 실패한 호출은 사용량에 적재하지 않는다."""
    err = httpx.HTTPStatusError(
        "429", request=httpx.Request("POST", "http://x"),
        response=httpx.Response(429, json={"error": {"message": "daily quota"}}),
    )
    seen = _run_exposed(monkeypatch, fail=err)
    assert len(seen["noted"]) == 1 and seen["usage"] == []
    assert seen["noted"][0] == {"surface": "chat", "owner_id": "owner-1", "ref_id": "t1"}


def test_generate_structured_keeps_counted_body_and_adds_output_options(monkeypatch) -> None:
    """생성 옵션은 maxOutputTokens 와 같은 자리(출력 쪽)에만 실린다 — 계수 대상 본문은 그대로."""
    sent: dict[str, Any] = {}

    class _Res:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"candidates": [{"content": {"parts": [{"text": "{}"}]},
                                    "finishReason": "STOP"}],
                    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 2,
                                      "thoughtsTokenCount": 7},
                    "modelVersion": "m1"}

    def fake_post(url: str, **kwargs: Any) -> _Res:
        sent.update(kwargs["json"])
        return _Res()

    monkeypatch.setattr(gemini_token_adapter.httpx, "post", fake_post)
    monkeypatch.setattr(gemini_token_adapter, "_api_key", lambda: "k")
    request = ProviderRequest(
        system_messages=("시스템",), user_messages=("본문",),
        output_schema='{"type": "OBJECT"}')
    counted = gemini_token_adapter.build_gemini_request_body(request)
    out = gemini_token_adapter.generate_structured(
        request, "m1", max_output_tokens=512,
        generation_extras={"thinkingConfig": {"thinkingLevel": "LOW"}})
    assert sent["contents"] == counted["contents"]
    assert sent["systemInstruction"] == counted["systemInstruction"]
    cfg = sent["generationConfig"]
    assert cfg["thinkingConfig"] == {"thinkingLevel": "LOW"} and cfg["maxOutputTokens"] == 512
    assert cfg["responseSchema"] == counted["generationConfig"]["responseSchema"]
    assert out["thoughts_tokens"] == 7 and out["output_tokens"] == 2
    # 반례 — 옵션을 주지 않으면 종전 본문과 같다(maxOutputTokens 만 추가).
    sent.clear()
    gemini_token_adapter.generate_structured(request, "m1", max_output_tokens=512)
    assert set(sent["generationConfig"]) == {
        "responseMimeType", "responseSchema", "maxOutputTokens"}


# ── llm_client 직접 호출 보조 ─────────────────────────────────────────


def _cfg() -> dict:
    return {"primary": {"provider": "gemini", "model": "m1", "api_key_env": "X",
                        "generation_extras": {"thinkingConfig": {"thinkingLevel": "LOW"}}},
            "fallback": {"provider": "openai", "model": "f1", "api_key_env": "Y"},
            "options": {"provider_cooldown_seconds": 900}}


def test_record_direct_primary_call_emits_usage(monkeypatch) -> None:
    """직접 호출도 일반 생성과 같은 필드로 사용량 sink 에 간다."""
    rows: list[dict] = []
    monkeypatch.setattr(llm_client, "load_config", lambda force=False: _cfg())
    monkeypatch.setattr(llm_client, "_usage_sink", lambda **k: rows.append(k))
    llm_client.record_direct_primary_call(
        call_type="chat_single", input_tokens=27000, output_tokens=700, cached_tokens=100,
        owner_id="o", surface="chat", ref_id="t1")
    assert rows == [{
        "surface": "chat", "model": "m1", "provider": "gemini", "is_fallback": False,
        "input_tokens": 27000, "output_tokens": 700, "cached_tokens": 100,
        "owner_id": "o", "product_code": "CHAT", "call_type": "chat_single", "ref_id": "t1",
    }]
    assert llm_client.primary_generation_extras() == {
        "thinkingConfig": {"thinkingLevel": "LOW"}}


@pytest.mark.parametrize(("status", "body", "expected"), [
    (429, {"error": {"message": "x", "details": [{"quotaId": "RequestsPerDayPerProject"}]}}, True),
    (429, {"error": {"message": "x", "details": [{"quotaId": "RequestsPerMinute"}]}}, False),
    (503, {"error": {"message": "overloaded"}}, False),
])
def test_note_direct_primary_error_marks_only_explicit_quota(
    monkeypatch, status: int, body: dict, expected: bool,
) -> None:
    """명시 소진 신호만 공급자 쿨다운으로 기록한다 — 분당 한도·5xx 는 일시 오류."""
    marked: list[tuple] = []
    monkeypatch.setattr(llm_client, "load_config", lambda force=False: _cfg())
    monkeypatch.setattr(llm_client._svc, "mark_provider_exhausted",
                        lambda *a, **k: marked.append((a, k)) or True)
    monkeypatch.setattr(llm_client, "_emit_error", lambda *a, **k: None)
    err = httpx.HTTPStatusError(
        str(status), request=httpx.Request("POST", "http://x"),
        response=httpx.Response(status, json=body))
    assert llm_client.note_direct_primary_error(
        err, surface="chat", owner_id="o", ref_id="t1") is expected
    assert bool(marked) is expected
    if expected:
        assert marked[0][0][:2] == ("gemini", "m1")
        assert marked[0][1] == {"kind": "quota", "cooldown_seconds": 900.0}


@pytest.mark.parametrize(("suspended", "blocked", "key", "expected"), [
    (False, False, "k", True),
    (True, False, "k", False),
    (False, True, "k", False),
    (False, False, None, False),
])
def test_direct_primary_call_ready(
    monkeypatch, suspended: bool, blocked: bool, key: str | None, expected: bool,
) -> None:
    """키 있음·중단 아님·메인 공급자 쿨다운 아님일 때만 직접 호출한다."""

    class _State:
        is_suspended = suspended

        def provider_blocked(self, provider: str) -> bool:
            return blocked and provider == "gemini"

    monkeypatch.setattr(llm_client, "load_config", lambda force=False: _cfg())
    monkeypatch.setattr(llm_client, "_api_key", lambda profile: key)
    monkeypatch.setattr(llm_client._svc, "current", lambda force=False: _State())
    assert llm_client.direct_primary_call_ready() is expected


# ── 리포트 위험 섹션: 같은 구조화 호출을 쓴다 ─────────────────────────


def _report_section(monkeypatch, flow_result: dict, ready: bool = True) -> tuple[Any, list[dict]]:
    """리포트 위험 섹션을 INJECTED 로 고정하고 위험 흐름을 기록용 대역으로 바꿔 실행한다."""
    from types import SimpleNamespace

    from saju_api.services import report_service
    from saju_api.services import risk_exposure_service as svc

    calls: list[dict] = []

    def fake_flow(**kwargs: Any) -> dict:
        calls.append(kwargs)
        return flow_result

    monkeypatch.setattr(svc, "exposure_mode_active", lambda: True)
    monkeypatch.setattr(reb, "build_risk_payload", lambda *a, **k: {
        "presentationRecords": [{"presentationLevel": "watch", "domains": ["finance"],
                                 "diagnostics": {"episodeKey": "k1"}}],
        "llmRiskEpisodes": [{"k": "v"}]})
    monkeypatch.setattr(report_service, "resolve_risk_owner", lambda *a, **k: "C-06")
    monkeypatch.setattr(reb, "exposure_runtime_inputs", lambda call_type: {
        "counter": lambda t: 1, "counter_model_id": "m1", "resolved_model_id": "m1",
        "context_limit": 100_000, "response_reserve": 2_000})
    monkeypatch.setattr(
        svc, "apply_risk_exposure",
        lambda prompt, system, **k: (prompt + "\n[위험 블록 대역]", system,
                                     {"disposition": "INJECTED"}))
    monkeypatch.setattr(reb, "run_exposed_reading", fake_flow)
    monkeypatch.setattr(llm_client, "direct_primary_call_ready", lambda: ready)
    data = SimpleNamespace(allowed_years={2026}, risk_shadow=[], risk_exposed_keys=set())
    out = report_service._try_risk_exposed_section(
        data,  # type: ignore[arg-type]
        SimpleNamespace(product_code="RPT_FOCUS"),  # type: ignore[arg-type]
        "섹션 본문", "시스템", "report_focus_section", "subj-1",
        section_id="C-06", available_section_ids=frozenset({"C-06"}), owner_id="owner-1",
    )
    return out, calls


def test_report_risk_section_passes_usage_context(monkeypatch) -> None:
    """리포트 위험 섹션의 구조화 호출도 리포트 칸(surface·상품:섹션)으로 사용량이 남는다."""
    (text, prompt), calls = _report_section(monkeypatch, {
        "outcome": "DELIVER_GENERATED", "final_text": "감사 통과 섹션",
        "attempts": [{"kind": "INITIAL"}], "provider_reports": 1})
    assert text == "감사 통과 섹션" and "[위험 블록 대역]" in prompt
    assert len(calls) == 1
    call = calls[0]
    assert (call["owner_id"], call["ref_id"], call["surface"], call["product_code"]) == (
        "owner-1", "subj-1", "report", "RPT_FOCUS:C-06")


def test_report_risk_section_provider_failure_uses_plain_path(monkeypatch) -> None:
    """provider 장애로 안전 문구만 남으면 그 문구를 섹션 본문으로 싣지 않고 기존 생성으로 넘긴다."""
    (text, prompt), calls = _report_section(monkeypatch, {
        "outcome": "DELIVER_SAFE_FALLBACK", "final_text": RISK_SAFE_FALLBACK_TEMPLATE,
        "attempts": [{"kind": "INITIAL", "audit_issues": ["PROVIDER_CALL_FAILED"]}]})
    assert text is None and len(calls) == 1
    assert "[위험 블록 대역]" not in prompt  # 위험 요소 없는 본문


def test_report_risk_section_audit_fallback_is_kept(monkeypatch) -> None:
    """반례 — 감사 실패로 끝난 안전 문구는 종전대로 섹션 본문이 된다."""
    (text, _prompt), _calls = _report_section(monkeypatch, {
        "outcome": "DELIVER_SAFE_FALLBACK", "final_text": RISK_SAFE_FALLBACK_TEMPLATE,
        "attempts": [{"kind": "INITIAL", "audit_issues": ["PROHIBITED_CLAIM:rg1"]}]})
    assert text == RISK_SAFE_FALLBACK_TEMPLATE


def test_report_risk_section_skips_flow_when_primary_unavailable(monkeypatch) -> None:
    """중단·메인 공급자 쿨다운이면 구조화 호출을 내지 않고 기존 생성 경로로 간다."""
    (text, prompt), calls = _report_section(
        monkeypatch, {"outcome": "DELIVER_GENERATED", "final_text": "x"}, ready=False)
    assert text is None and calls == []
    assert "[위험 블록 대역]" not in prompt


# ── 라우터 백그라운드 생성 ───────────────────────────────────────────


class _History:
    """`complete_turn` 만 기록하는 대역."""

    def __init__(self) -> None:
        self.done: list[tuple[int, str, str]] = []

    def complete_turn(self, message_id: int, text: str, status: str = "done",
                      meta: dict | None = None) -> None:
        self.done.append((message_id, text, status))


def test_background_answer_uses_single_entry_and_registers_followups(
    monkeypatch, base_ctx,
) -> None:
    """백그라운드 생성 — 단일 진입점 1회 호출, 감사 통과 답이면 위험 episode 참조를 등록한다."""
    from saju_api.routers import chat as chat_router
    from saju_shared_types.conversation import ResultSummaryRef

    ref = ResultSummaryRef(kind="risk_episode", label="k|finance|2026", detail="d")
    ctx = _ctx_with_plan(base_ctx, followups=[ref])
    gen_calls: list[dict] = []
    offers: list[dict] = []

    def fake_generate(prompt: str, **kwargs: Any) -> tuple[str, str | None]:
        gen_calls.append({"prompt": prompt, **kwargs})
        return "감사 통과 답", "DELIVER_GENERATED"

    monkeypatch.setattr(chat_router.chat_service, "generate_chat_answer", fake_generate)
    monkeypatch.setattr(chat_router.chat_service, "update_thread_offer",
                        lambda thread_id, answer, **k: offers.append({"answer": answer, **k}))
    history = _History()
    chat_router._run_chat_answer(
        history, 7, "owner-1", "t1", _INJECTED, "chat_single", "시스템", ctx)  # type: ignore[arg-type]
    assert len(gen_calls) == 1 and gen_calls[0]["postprocess"] is ctx
    assert history.done == [(7, "감사 통과 답", "done")]
    assert offers[0]["system_results"] == [ref]


def test_background_blocked_answer_ends_with_generic_error(monkeypatch, base_ctx) -> None:
    """BLOCK 이면 내부 상태를 설명하지 않는 일반 실패 문구로 마감한다(위험 본문 미전달)."""
    from saju_api.routers import chat as chat_router

    def blocked(prompt: str, **kwargs: Any) -> tuple[str, str | None]:
        raise chat_service.RiskAnswerBlocked("BLOCK")

    monkeypatch.setattr(chat_router.chat_service, "generate_chat_answer", blocked)
    monkeypatch.setattr(chat_router.chat_service, "update_thread_offer", lambda *a, **k: None)
    history = _History()
    chat_router._run_chat_answer(
        history, 8, "owner-1", "t1", _INJECTED, "chat_single", "시스템",  # type: ignore[arg-type]
        _ctx_with_plan(base_ctx))
    generic = "답변 생성 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요."
    assert history.done == [(8, generic, "error")]
