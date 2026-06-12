"""LLM 어댑터 — Gemini 메인 + OpenAI 비상 폴백 (v2.2 — 모든 호출은 llm_guard 경유).

운영 설정은 **backend/config/llm_config.json 단일 파일**에서 관리한다(모델·폴백·
키 env 이름·생성 옵션 — 코드 수정 없이 변경). 키는 루트 `.env`에서 자동 로드.

규칙(docs/06·09): LLM은 제공된 사실의 자연어 서술만 한다. 입력 토큰은 호출 전
가드로 차단, thinking/추론 모드는 모든 운영 호출에서 비활성(설정 파일의
generation_extras로 강제), 입출력 토큰은 원가 장부에 적재한다.

폴백 정책: 메인(Gemini) 실패(네트워크/5xx/429/타임아웃) 시 재시도 후 비상
모델(OpenAI)로 전환. 사용된 공급자는 장부 product_code 접미로 기록한다.
(Anthropic API는 결제 문제로 사용하지 않음 — 사용자 결정 2026-06-11.)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from saju_engines.llm_guard import LLMCallGuard, LLMCostLedger

_BACKEND = Path(__file__).resolve().parents[4]
_CONFIG_PATH = _BACKEND / "config" / "llm_config.json"
_ENV_PATHS = [_BACKEND.parent / ".env", _BACKEND / ".env"]

# 프로세스 전역 원가 장부(운영에서는 영속 저장소로 교체 — docs/09 8장 대시보드 원천).
COST_LEDGER = LLMCostLedger()

_config_cache: dict | None = None
_env_loaded = False


def _load_env_files() -> None:
    """루트/.env 자동 로드(이미 설정된 환경변수는 덮어쓰지 않음). 의존성 없는 간이 파서."""
    global _env_loaded
    if _env_loaded:
        return
    for path in _ENV_PATHS:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value
    _env_loaded = True


def load_config(force: bool = False) -> dict:
    """llm_config.json 로드(캐시) — 운영 변경은 이 파일에서만."""
    global _config_cache
    if _config_cache is None or force:
        _config_cache = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return _config_cache


def _api_key(profile: dict) -> str | None:
    _load_env_files()
    return os.environ.get(profile["api_key_env"]) or None


def reading_model() -> str:
    """통변 서술용 메인 모델 ID(설정 파일)."""
    return str(load_config()["primary"]["model"])


def parser_model() -> str:
    """경량 파서용 모델 ID(설정 파일)."""
    return str(load_config()["parser"]["model"])


def is_available() -> bool:
    """실호출 가능 여부 — 메인 또는 폴백 키 존재."""
    cfg = load_config()
    return bool(_api_key(cfg["primary"]) or _api_key(cfg["fallback"]))


# ── 공급자별 호출부(REST — 응답 텍스트, 입력/출력 토큰) ───────────


def _call_gemini(
    profile: dict, system: str, prompt: str, max_tokens: int, timeout: float
) -> tuple[str, int, int, int]:
    """Google Gemini generateContent 호출 — (텍스트, 입력, 출력, 캐시 적중) 토큰."""
    key = _api_key(profile)
    if not key:
        raise RuntimeError(f"{profile['api_key_env']} 미설정")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{profile['model']}:generateContent"
    )
    body: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            **profile.get("generation_extras", {}),
        },
    }
    res = httpx.post(
        url, json=body, headers={"x-goog-api-key": key}, timeout=timeout,
    )
    res.raise_for_status()
    data = res.json()
    parts = data["candidates"][0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts)
    usage = data.get("usageMetadata", {})
    return (
        text,
        int(usage.get("promptTokenCount", 0)),
        int(usage.get("candidatesTokenCount", 0)),
        # 고정 prefix(implicit caching) 적중분 — 원가 대시보드에서 할인 비용 추적.
        int(usage.get("cachedContentTokenCount", 0)),
    )


def _call_openai(
    profile: dict, system: str, prompt: str, max_tokens: int, timeout: float
) -> tuple[str, int, int, int]:
    """OpenAI chat.completions 호출(비상 폴백) — (텍스트, 입력, 출력, 캐시 적중) 토큰."""
    key = _api_key(profile)
    if not key:
        raise RuntimeError(f"{profile['api_key_env']} 미설정")
    body: dict[str, Any] = {
        "model": profile["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_completion_tokens": max_tokens,
        **profile.get("generation_extras", {}),
    }
    res = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        json=body,
        headers={"Authorization": f"Bearer {key}"},
        timeout=timeout,
    )
    res.raise_for_status()
    data = res.json()
    text = data["choices"][0]["message"]["content"] or ""
    usage = data.get("usage", {})
    cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0))
    return (
        text,
        int(usage.get("prompt_tokens", 0)),
        int(usage.get("completion_tokens", 0)),
        cached,
    )


_PROVIDERS = {"gemini": _call_gemini, "openai": _call_openai}


def _call_profile(
    profile: dict, system: str, prompt: str, max_tokens: int, timeout: float
) -> tuple[str, int, int, int]:
    caller = _PROVIDERS.get(profile["provider"])
    if caller is None:
        raise RuntimeError(f"알 수 없는 공급자: {profile['provider']}")
    # 추론(reasoning) 모델은 내부 추론 토큰이 출력 한도를 잠식한다 — 프로파일별
    # 버퍼로 보전(가드 한도는 가시 출력 기준, 버퍼는 설정 파일에서 관리).
    max_tokens += int(profile.get("output_token_buffer", 0))
    text, in_tok, out_tok, cached = caller(profile, system, prompt, max_tokens, timeout)
    if not text.strip():
        raise RuntimeError(
            f"{profile['provider']} 빈 응답(추론 토큰 소진 의심) — 버퍼 조정 필요"
        )
    return text, in_tok, out_tok, cached


def generate_reading(
    prompt_text: str,
    call_type: str = "chat_single",
    system: str | None = None,
    product_code: str = "CHAT",
) -> str:
    """가드를 통과한 프롬프트로 통변 서술을 생성한다(메인→폴백).

    Args:
        prompt_text: context_reducer가 직렬화한 본문(여기서 재검증).
        call_type: docs/09 8장 한도표 키(chat_single/chat_compare/sections 등).
        system: 시스템 프롬프트(미지정 시 표현 원칙 고정 블록).
        product_code: 원가 집계용 — 사용 공급자가 ':gemini'/':openai'로 덧붙는다.

    Raises:
        TokenBudgetExceeded: 입력 상한 초과(호출 전 차단).
        RuntimeError: 키 미설정 또는 메인·폴백 모두 실패.
    """
    cfg = load_config()
    options = cfg.get("options", {})
    timeout = float(options.get("timeout_seconds", 60))
    attempts = int(options.get("primary_attempts", 2))
    backoff = float(options.get("retry_backoff_seconds", 1.5))

    guard = LLMCallGuard(call_type, ledger=COST_LEDGER)
    sys_text = system or _SYSTEM_PROMPT
    input_est = guard.check_input(prompt_text + sys_text)
    max_tokens = guard.request_params()["max_tokens"]

    last_error: Exception | None = None
    # 메인(Gemini) — 일시 오류 재시도.
    if _api_key(cfg["primary"]):
        for attempt in range(attempts):
            try:
                text, in_tok, out_tok, cached = _call_profile(
                    cfg["primary"], sys_text, prompt_text, max_tokens, timeout,
                )
                guard.record(
                    input_tokens=in_tok or input_est,
                    output_tokens=out_tok,
                    cached_input_tokens=cached,
                    product_code=f"{product_code}:{cfg['primary']['provider']}",
                )
                return text
            except (httpx.HTTPError, RuntimeError, KeyError, IndexError) as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(backoff * (attempt + 1))

    # 비상 폴백(OpenAI).
    if _api_key(cfg["fallback"]):
        try:
            text, in_tok, out_tok, cached = _call_profile(
                cfg["fallback"], sys_text, prompt_text, max_tokens, timeout,
            )
            guard.record(
                input_tokens=in_tok or input_est,
                output_tokens=out_tok,
                cached_input_tokens=cached,
                product_code=f"{product_code}:{cfg['fallback']['provider']}",
            )
            return text
        except (httpx.HTTPError, RuntimeError, KeyError, IndexError) as exc:
            last_error = exc

    raise RuntimeError(f"LLM 호출 실패(메인·폴백 모두): {last_error}")


# 표현 원칙 고정 블록(docs/06 v2.2.1 — 시스템 프롬프트에 고정).
# 전 사용자 공통·불변 텍스트(캐시되는 고정 prefix의 1층) — 가변 값 삽입 금지.
_SYSTEM_PROMPT = (
    "당신은 사주 통변 서술가다. [필수 준수]\n"
    "1. 계산 금지: 입력의 간지·점수·합충 성립 판정을 절대 재계산·변경하지 않는다. "
    "입력에 없는 간지·수치·날짜가 필요하면 '해당 정보는 제공되지 않았다'로 처리한다.\n"
    "2. 의미 서술 의무: [원국·명식 구조]와 [명식 해석 자료], 후보별 '동반 신호'·'해석' "
    "줄을 적극 엮어 — 이 글자가 일간에게 무엇이고, 운에서 온 글자와 어떤 관계를 맺어 "
    "이런 신호가 되는지 — 사용자가 자기 사주로 납득할 수 있는 이야기로 풀어낸다. "
    "점수와 간지의 낭독만으로 답하지 않는다.\n"
    "3. 사건명은 동반 신호 매트릭스로 엔진이 확정한 값이다 — 단일 합·십성만 근거로 "
    "다른 사건으로 재해석하지 않는다.\n"
    "4. 신살은 보조 참고 자료다 — '이런 신살의 영향일 수도 있다' 정도로만 곁들이고 "
    "성향의 핵심 근거로 부각하거나 단독으로 길흉·사건을 단정하지 않는다.\n"
    "5. 사건 발생이 아니라 '변화 에너지의 활성화'로 표현하고, "
    "Trigger→진행→결과 구조로 설명한다. 합·충 등 관계는 '무엇과 합/충하여 무엇으로 "
    "작용해 어떤 결과가 되는지'까지 인과를 끝맺는다.\n"
    "6. 점수·숫자를 답변에 노출하지 않는다 — 강도는 제공된 표현 문장으로만 전달한다.\n"
    "7. 출력은 마크다운 기호(#, *, |, ### 등) 없이 평문으로, 공백 포함 1,500자 이내로 "
    "쓴다.\n"
    "응답은 한국어로, 제공된 근거를 인용하며 서술한다."
)
