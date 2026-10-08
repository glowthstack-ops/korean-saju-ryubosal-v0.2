"""LLM 비용 소진 일시 중단 — 분류·전이·단락·재개 (2026-10-06, doc/v2_2/LLM_SERVICE_SUSPENSION.md).

상태 저장소는 메모리 백엔드로 격리한다(DB 없이 결정적). 공급자 호출부는 `_PROVIDERS`
항목을 바꿔 모의한다(conftest 의 실호출 차단 경계와 같은 자리).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from saju_api.services import llm_client, llm_resume_service, llm_service_state


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch):
    """설정 캐시 초기화 + 테스트 키 + 메모리 상태 백엔드 + 재시도 대기 생략."""
    llm_client.load_config(force=True)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    llm_service_state.use_memory_backend()
    monkeypatch.setattr(llm_client.time, "sleep", lambda _s: None)
    yield
    llm_service_state.use_memory_backend()


def _quota(provider: str, model: str = "m") -> llm_client.ProviderQuotaExhausted:
    return llm_client.ProviderQuotaExhausted(provider, model, "insufficient_quota")


def _wire(monkeypatch: pytest.MonkeyPatch, gemini, openai) -> list[str]:
    calls: list[str] = []

    def g(profile, system, prompt, max_tokens, timeout):
        calls.append("gemini")
        return gemini()

    def o(profile, system, prompt, max_tokens, timeout):
        calls.append("openai")
        return openai()

    monkeypatch.setitem(llm_client._PROVIDERS, "gemini", g)
    monkeypatch.setitem(llm_client._PROVIDERS, "openai", o)
    return calls


def _ok(text: str):
    return lambda: (text, 100, 50, 0)


def _probe(role: str, provider: str, ok: bool, kind: str | None = None, detail: str = "") -> dict:
    return {"role": role, "provider": provider, "model": provider[0], "ok": ok,
            "kind": kind, "detail": detail}


def _raise(exc: Exception):
    def _f():
        raise exc
    return _f


# ── 분류기 ─────────────────────────────────────────────────────────


def _resp(status: int, body: Any) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("POST", "https://x.test/"))


def test_classify_openai_insufficient_quota_is_quota() -> None:
    body = {"error": {"type": "insufficient_quota", "code": "insufficient_quota",
                      "message": "You exceeded your current quota"}}
    assert llm_client.classify_provider_error("openai", 429, body) == "quota"
    assert llm_client.classify_provider_error("openai", 402, {}) == "quota"


def test_classify_openai_rate_limit_is_transient() -> None:
    body = {"error": {"type": "rate_limit_exceeded", "code": "rate_limit_exceeded"}}
    assert llm_client.classify_provider_error("openai", 429, body) == "transient"
    assert llm_client.classify_provider_error("openai", 500, {}) == "transient"


def test_classify_gemini_daily_quota_is_quota_but_per_minute_is_transient() -> None:
    daily = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                       "message": "You exceeded your current quota",
                       "details": [{
                           "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                           "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel"}],
                       }]}}
    minute = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                        "message": "You exceeded your current quota",
                        "details": [{"violations": [
                            {"quotaId": "GenerateRequestsPerMinutePerProjectPerModel"},
                        ]}]}}
    generic = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                         "message": "You exceeded your current quota"}}
    assert llm_client.classify_provider_error("gemini", 429, daily) == "quota"
    assert llm_client.classify_provider_error("gemini", 429, minute) == "transient"
    # 범용 문구만 있는 429 는 분당 한도일 수 있어 하드 중단 신호로 쓰지 않는다.
    assert llm_client.classify_provider_error("gemini", 429, generic) == "transient"
    billing = {"error": {"code": 403, "status": "PERMISSION_DENIED",
                         "message": "Billing account disabled"}}
    assert llm_client.classify_provider_error("gemini", 403, billing) == "quota"


def test_raise_for_provider_maps_quota_and_keeps_http_error() -> None:
    profile = {"model": "gpt-x"}
    with pytest.raises(llm_client.ProviderQuotaExhausted) as ei:
        llm_client._raise_for_provider(
            "openai", profile,
            _resp(429, {"error": {"type": "insufficient_quota", "message": "no credit"}}),
        )
    assert ei.value.provider == "openai" and ei.value.model == "gpt-x"
    assert "no credit" in ei.value.detail
    with pytest.raises(httpx.HTTPStatusError):
        llm_client._raise_for_provider(
            "openai", profile, _resp(503, {"error": {"message": "busy"}}),
        )
    llm_client._raise_for_provider("openai", profile, _resp(200, {}))  # 정상은 통과


# ── 전이 규칙 ───────────────────────────────────────────────────────


def test_primary_quota_falls_back_and_skips_primary_on_next_call(monkeypatch) -> None:
    """메인만 소진 → 폴백으로 응답 + 메인은 쿨다운(다음 호출에서 호출하지 않음). 서비스는 active."""
    calls = _wire(monkeypatch, _raise(_quota("gemini")), _ok("폴백 본문"))
    assert llm_client.generate_reading("질문", product_code="T1") == "폴백 본문"
    assert calls == ["gemini", "openai"]
    state = llm_service_state.current(force=True)
    assert not state.is_suspended and state.provider_blocked("gemini")
    assert not state.provider_blocked("openai")

    calls.clear()
    assert llm_client.generate_reading("질문2", product_code="T1") == "폴백 본문"
    assert calls == ["openai"]  # 메인은 쿨다운 동안 실패 호출을 반복하지 않는다


def test_transient_primary_error_does_not_mark_provider(monkeypatch) -> None:
    """일시 오류(네트워크·5xx)는 종전 그대로 — 쿨다운 기록 없음, 상태 변화 없음."""
    _wire(monkeypatch, _raise(httpx.ConnectError("down")), _ok("폴백"))
    assert llm_client.generate_reading("q", product_code="T2") == "폴백"
    state = llm_service_state.current(force=True)
    assert not state.providers and not state.is_suspended


def test_both_quota_suspends_service_and_short_circuits(monkeypatch) -> None:
    """메인·폴백 모두 소진 → suspended 전이 + 이후 호출은 공급자에 닿지 않는다."""
    calls = _wire(monkeypatch, _raise(_quota("gemini")), _raise(_quota("openai")))
    with pytest.raises(llm_client.LLMServiceSuspended):
        llm_client.generate_reading("q", product_code="T3")
    assert calls == ["gemini", "openai"]
    state = llm_service_state.current(force=True)
    assert state.is_suspended and state.reason == "quota_exhausted"
    assert state.snapshot()["state"] == "suspended"  # 공개 스냅샷(health)

    calls.clear()
    with pytest.raises(llm_client.LLMServiceSuspended):
        llm_client.generate_reading("q2", product_code="T3")
    assert calls == []  # 단락 — 네트워크 0건
    assert llm_client.is_suspended() is True


def test_suspend_is_recorded_once_in_error_sink(monkeypatch) -> None:
    """중단 전이는 system_errors 에 1건(고정 메시지 → fingerprint 안정) — 재전이 시도는 무기록."""
    seen: list[dict[str, Any]] = []
    llm_client.set_error_sink(lambda exc, **f: seen.append(f))
    try:
        _wire(monkeypatch, _raise(_quota("gemini")), _raise(_quota("openai")))
        with pytest.raises(llm_client.LLMServiceSuspended):
            llm_client.generate_reading("q", product_code="T4")
        kinds = [f["kind"] for f in seen]
        assert kinds.count(llm_service_state.SUSPENDED_ERROR_KIND) == 1
        assert kinds.count(llm_service_state.PROVIDER_EXHAUSTED_KIND) == 2  # 공급자별 warning
        susp = next(f for f in seen if f["kind"] == llm_service_state.SUSPENDED_ERROR_KIND)
        assert susp["message"] == llm_service_state.SUSPENDED_ERROR_MESSAGE
        assert llm_service_state.suspend() is False  # 이미 중단 — 재전이 없음
    finally:
        llm_client.set_error_sink(None)


def test_primary_only_key_quota_suspends(monkeypatch) -> None:
    """폴백 키가 없고 메인이 소진이면 '키 있는 공급자 전부 소진' → 중단."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _wire(monkeypatch, _raise(_quota("gemini")), _ok("x"))
    with pytest.raises(llm_client.LLMServiceSuspended):
        llm_client.generate_reading("q", product_code="T5")
    assert llm_service_state.current(force=True).is_suspended


# ── 재개 ──────────────────────────────────────────────────────────


def _suspend_now(monkeypatch) -> None:
    _wire(monkeypatch, _raise(_quota("gemini")), _raise(_quota("openai")))
    with pytest.raises(llm_client.LLMServiceSuspended):
        llm_client.generate_reading("q", product_code="S")
    assert llm_service_state.current(force=True).is_suspended


def test_resume_rejected_when_no_probe_passes(monkeypatch) -> None:
    _suspend_now(monkeypatch)
    monkeypatch.setattr(llm_client, "probe_all", lambda: [
        _probe("primary", "gemini", False, "quota", "d"),
        _probe("fallback", "openai", False, "quota", "d"),
    ])
    with pytest.raises(llm_resume_service.ResumeRejected) as ei:
        llm_resume_service.probe_and_resume("admin", None, None)
    assert len(ei.value.payload["probes"]) == 2
    state = llm_service_state.current(force=True)
    assert state.is_suspended and state.last_probe is not None  # 상태 유지, 프로브는 기록


def test_resume_with_all_probes_ok_clears_state_and_serves_again(monkeypatch) -> None:
    _suspend_now(monkeypatch)
    monkeypatch.setattr(llm_client, "probe_all", lambda: [
        _probe("primary", "gemini", True),
        _probe("fallback", "openai", True),
    ])
    out = llm_resume_service.probe_and_resume("admin", None, None)
    assert out["resumed"] is True and out["was_suspended"] is True and out["still_blocked"] == []
    state = llm_service_state.current(force=True)
    assert not state.is_suspended and state.resumed_by == "admin" and not state.providers

    calls = _wire(monkeypatch, _ok("메인 복구"), _ok("폴백"))
    assert llm_client.generate_reading("q", product_code="R") == "메인 복구"
    assert calls == ["gemini"]


def test_resume_partial_keeps_failed_provider_in_cooldown(monkeypatch) -> None:
    """일부만 통과 → 재개하되 소진 공급자는 쿨다운(호출 안 함)."""
    _suspend_now(monkeypatch)
    monkeypatch.setattr(llm_client, "probe_all", lambda: [
        _probe("primary", "gemini", False, "quota", "still"),
        _probe("fallback", "openai", True),
    ])
    out = llm_resume_service.probe_and_resume("admin", None, None)
    assert out["resumed"] is True and out["still_blocked"] == ["gemini"]
    calls = _wire(monkeypatch, _ok("메인"), _ok("폴백만"))
    assert llm_client.generate_reading("q", product_code="R2") == "폴백만"
    assert calls == ["openai"]


def test_resume_when_active_is_noop() -> None:
    out_probe = [_probe("primary", "gemini", True)]
    mp = pytest.MonkeyPatch()
    mp.setattr(llm_client, "probe_all", lambda: out_probe)
    try:
        out = llm_resume_service.probe_and_resume("admin", None, None)
    finally:
        mp.undo()
    assert out["resumed"] is False and out["was_suspended"] is False
    assert out["requeued_reports"] == 0 and out["daily_polish_scheduled"] is False


def test_manual_suspend_blocks_calls(monkeypatch) -> None:
    calls = _wire(monkeypatch, _ok("x"), _ok("y"))
    out = llm_resume_service.manual_suspend("admin", "manual")
    assert out["suspended"] is True and out["state"]["reason"] == "manual"
    with pytest.raises(llm_client.LLMServiceSuspended):
        llm_client.generate_reading("q", product_code="M")
    assert calls == []
