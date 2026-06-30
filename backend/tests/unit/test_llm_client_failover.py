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
    # 구체 모델명은 운영 결정으로 바뀐다(예: 2026-06-12 프리뷰 503 장애 → 2.5-flash
    # 전환) — 테스트는 '단일 파일이 모델을 결정'하는 계약만 고정한다.
    assert cfg["primary"]["model"].startswith("gemini-")
    assert cfg["fallback"]["provider"] == "openai"
    assert cfg["fallback"]["model"] == "gpt-5.4-mini"
    assert llm_client.reading_model() == cfg["primary"]["model"]
    assert llm_client.is_available() is True


def test_primary_success_records_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """메인 성공 → 폴백 미호출 + 장부에 ':gemini' 기록."""
    calls: list[str] = []

    def fake_gemini(profile, system, prompt, max_tokens, timeout):
        calls.append("gemini")
        return "통변 본문(모의)", 500, 300, 120  # 마지막 = 캐시 적중 토큰(v2.2.1)

    def fake_openai(profile, system, prompt, max_tokens, timeout):
        calls.append("openai")
        return "폴백 본문", 1, 1, 0

    monkeypatch.setitem(llm_client._PROVIDERS, "gemini", fake_gemini)
    monkeypatch.setitem(llm_client._PROVIDERS, "openai", fake_openai)

    text = llm_client.generate_reading("질문 본문", product_code="TEST")
    assert text == "통변 본문(모의)" and calls == ["gemini"]
    entry = next(
        e for e in llm_client.COST_LEDGER.entries if e.product_code == "TEST:gemini"
    )
    # 캐시 적중 토큰 별도 집계(v2.2.1 — 고정 prefix 실비용 추적).
    assert entry.cached_input_tokens == 120


def test_failover_to_openai_on_primary_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """메인 연속 실패(재시도 포함) → 비상 폴백으로 응답 + ':openai' 기록."""
    calls: list[str] = []

    def broken_gemini(profile, system, prompt, max_tokens, timeout):
        calls.append("gemini")
        raise httpx.ConnectError("simulated outage")

    def fake_openai(profile, system, prompt, max_tokens, timeout):
        calls.append("openai")
        return "비상 폴백 본문", 400, 200, 0

    monkeypatch.setitem(llm_client._PROVIDERS, "gemini", broken_gemini)
    monkeypatch.setitem(llm_client._PROVIDERS, "openai", fake_openai)
    monkeypatch.setattr(llm_client.time, "sleep", lambda _s: None)  # 재시도 대기 생략

    text = llm_client.generate_reading("질문 본문", product_code="TEST2")
    assert text == "비상 폴백 본문"
    # primary_attempts 회 메인 시도 후 폴백 — 재시도 횟수는 운영 설정값(llm_config.json)에서 온다.
    attempts = int(llm_client.load_config()["options"]["primary_attempts"])
    assert calls == ["gemini"] * attempts + ["openai"]
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


def test_sanitize_removes_strikethrough_keeps_ranges() -> None:
    """취소선(~~…~~) 구간은 통째로 제거하되, 범위 표기의 단일 물결표(1~2)는 보존한다."""
    s = llm_client._sanitize_output
    # 자기수정 자취 제거 + 이중 공백 정돈.
    assert s("올해는 ~~이직~~ 이사 에너지가 강해요.") == "올해는 이사 에너지가 강해요."
    # 구두점 앞 공백 제거.
    assert s("변화가 ~~큽니다~~ 옵니다 ~~.~~") == "변화가 옵니다"
    # 단일 물결표(범위)는 그대로.
    assert s("앞으로 1~2개월 내 변동이 있어요.") == "앞으로 1~2개월 내 변동이 있어요."
    # 취소선 없으면 원문 그대로(동일 객체 반환 경로).
    assert s("평범한 문장입니다.") == "평범한 문장입니다."


def test_sanitize_normalizes_mixed_ganji() -> None:
    """간지 한자/한글 혼용·부분 음역을 '한자(한글)' 병기로 통일한다(2026-06-18 결함)."""
    s = llm_client._sanitize_output
    # 혼용(한글천간+한자지지) → 병기.
    assert "丁卯(정묘)일" in s("6월 22일 정卯일이 좋아요")
    assert "辛未(신미)일" in s("신未일과") and "乙丑(을축)일" in s("을丑일이")
    # 순수 한자 + 표식 → 병기.
    assert s("올해 丙午년은") == "올해 丙午(병오)년은"
    # 이미 병기된 간지는 중복 변환하지 않는다.
    assert s("丁卯(정묘)일") == "丁卯(정묘)일"
    # 간지 표식 없는 일반어(기사=글)는 건드리지 않는다(오탐 방지).
    assert s("그는 기사를 읽었다") == "그는 기사를 읽었다"


def test_sanitize_collapses_duplicate_gloss() -> None:
    """병기 중복 정리(2026-06-27) — 중첩 '한글(한자(한글))'과 자기중복 'X(X)' 제거."""
    s = llm_client._sanitize_output
    # 중첩: LLM '기해(己亥)' → _normalize_ganji가 이중 병기 → 표준형 '己亥(기해)'로 접는다.
    assert s("일주 기해(己亥)는") == "일주 己亥(기해)는"
    assert "丁亥(정해)" in s("월주 정해(丁亥)와") and "(丁亥(" not in s("월주 정해(丁亥)와")
    # 한글·한자가 어긋나게 쓰인 중첩도 한자 기준으로 일관 정리('임인'은 버리고 한자 신뢰).
    assert s("임인(壬辰) 대운") == "壬辰(임진) 대운"
    # 자기중복: 십성·신살까지 과잉 병기한 '정재(정재)' 류는 괄호 군더더기만 제거.
    assert s("지지 정재(정재)의 성분") == "지지 정재의 성분"
    assert s("상관(상관)과 천을귀인(천을귀인)") == "상관과 천을귀인"
    # 정상 병기·서로 다른 병기는 보존('해수(亥水)'는 지지+오행, 중복 아님).
    assert s("해수(亥水)는 정재") == "해수(亥水)는 정재"
    assert s("이미 표준형 己亥(기해)는") == "이미 표준형 己亥(기해)는"


def test_primary_output_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    """generate_reading 반환값에서 취소선이 제거된다(채팅·리포트 공통 경로)."""
    def fake_gemini(profile, system, prompt, max_tokens, timeout):
        return "결론은 ~~이직~~ 이사예요.", 100, 50, 0

    monkeypatch.setitem(llm_client._PROVIDERS, "gemini", fake_gemini)
    text = llm_client.generate_reading("질문 본문", product_code="TEST_SAN")
    assert "~~" not in text and text == "결론은 이사예요."


def test_guard_blocks_oversize_before_any_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """입력 한도 초과는 어떤 공급자도 호출하기 전에 차단(절대 원칙 9)."""
    from saju_engines.llm_guard import TokenBudgetExceeded

    def must_not_call(profile, system, prompt, max_tokens, timeout):
        raise AssertionError("호출되면 안 됨")

    monkeypatch.setitem(llm_client._PROVIDERS, "gemini", must_not_call)
    monkeypatch.setitem(llm_client._PROVIDERS, "openai", must_not_call)
    with pytest.raises(TokenBudgetExceeded):
        llm_client.generate_reading("가" * 40_000)
