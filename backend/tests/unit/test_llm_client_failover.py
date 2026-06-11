"""LLM 어댑터 검증 — 단일 설정 파일·메인(Gemini)→폴백(OpenAI)·가드 경유."""

from __future__ import annotations

import httpx
import pytest

from saju_api.services import llm_client


@pytest.fixture(autouse=True)
def _fresh_config(monkeypatch: pytest.MonkeyPatch):
    """설정 캐시 초기화 + 테스트용 키 주입."""
    llm_client.load_config(force=True)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    yield


def test_config_single_file_drives_models() -> None:
    """모델·폴백·키 env가 llm_config.json 한 파일에서 결정된다."""
    cfg = llm_client.load_config()
    assert cfg["primary"]["provider"] == "gemini"
    assert cfg["primary"]["model"] == "gemini-3-flash-preview"
    assert cfg["fallback"]["provider"] == "openai"
    assert cfg["fallback"]["model"] == "gpt-5-mini"
    assert llm_client.reading_model() == "gemini-3-flash-preview"
    assert llm_client.is_available() is True


def test_primary_success_records_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """메인 성공 → 폴백 미호출 + 장부에 ':gemini' 기록."""
    calls: list[str] = []

    def fake_gemini(profile, system, prompt, max_tokens, timeout):
        calls.append("gemini")
        return "통변 본문(모의)", 500, 300

    def fake_openai(profile, system, prompt, max_tokens, timeout):
        calls.append("openai")
        return "폴백 본문", 1, 1

    monkeypatch.setitem(llm_client._PROVIDERS, "gemini", fake_gemini)
    monkeypatch.setitem(llm_client._PROVIDERS, "openai", fake_openai)

    text = llm_client.generate_reading("질문 본문", product_code="TEST")
    assert text == "통변 본문(모의)" and calls == ["gemini"]
    assert any(
        e.product_code == "TEST:gemini" for e in llm_client.COST_LEDGER.entries
    )


def test_failover_to_openai_on_primary_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """메인 연속 실패(재시도 포함) → 비상 폴백으로 응답 + ':openai' 기록."""
    calls: list[str] = []

    def broken_gemini(profile, system, prompt, max_tokens, timeout):
        calls.append("gemini")
        raise httpx.ConnectError("simulated outage")

    def fake_openai(profile, system, prompt, max_tokens, timeout):
        calls.append("openai")
        return "비상 폴백 본문", 400, 200

    monkeypatch.setitem(llm_client._PROVIDERS, "gemini", broken_gemini)
    monkeypatch.setitem(llm_client._PROVIDERS, "openai", fake_openai)
    monkeypatch.setattr(llm_client.time, "sleep", lambda _s: None)  # 재시도 대기 생략

    text = llm_client.generate_reading("질문 본문", product_code="TEST2")
    assert text == "비상 폴백 본문"
    assert calls == ["gemini", "gemini", "openai"]  # primary_attempts=2 후 폴백
    assert any(
        e.product_code == "TEST2:openai" for e in llm_client.COST_LEDGER.entries
    )


def test_both_fail_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(profile, system, prompt, max_tokens, timeout):
        raise httpx.ConnectError("down")

    monkeypatch.setitem(llm_client._PROVIDERS, "gemini", broken)
    monkeypatch.setitem(llm_client._PROVIDERS, "openai", broken)
    monkeypatch.setattr(llm_client.time, "sleep", lambda _s: None)
    with pytest.raises(RuntimeError, match="메인·폴백 모두"):
        llm_client.generate_reading("질문 본문")


def test_guard_blocks_oversize_before_any_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """입력 한도 초과는 어떤 공급자도 호출하기 전에 차단(절대 원칙 9)."""
    from saju_engines.llm_guard import TokenBudgetExceeded

    def must_not_call(profile, system, prompt, max_tokens, timeout):
        raise AssertionError("호출되면 안 됨")

    monkeypatch.setitem(llm_client._PROVIDERS, "gemini", must_not_call)
    monkeypatch.setitem(llm_client._PROVIDERS, "openai", must_not_call)
    with pytest.raises(TokenBudgetExceeded):
        llm_client.generate_reading("가" * 40_000)
