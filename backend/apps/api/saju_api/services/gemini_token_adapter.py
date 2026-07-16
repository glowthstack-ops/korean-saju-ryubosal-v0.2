"""Gemini countTokens 기반 실물 token counter adapter(감수 56차 §9).

mode=PROVIDER_EXACT: provider 자신의 countTokens API가 **최종 provider
request 전체**(systemInstruction·contents·generationConfig·tools·
responseSchema)를 계수한다 — 사전 탐침에서 countTokens.totalTokens ==
generateContent.usageMetadata.promptTokenCount 정확 일치 확인
(responseSchema 포함 케이스 포함).

계약:
- 등록은 import 부수효과가 아니라 **명시 호출**(register_gemini_shadow_
  adapter) — registry 기본 비어 있음 계약 유지.
- 등록 직후 상태는 SHADOW_VALIDATING 고정 — 30표본 통과만으로 runtime
  객체가 자동 VALIDATED가 되지 않는다(validation artifact 생성 → manifest
  감수(reviewed entry) → 배포 이후에만 VALIDATED 자격, 감수 56차 §9).
- validation_corpus_hash는 shadow 검증 harness(scripts/
  risk_adapter_shadow_validation.py)가 산출한 corpus canonical hash를
  주입한다 — corpus 재감수=새 validation identity.
- 계수는 네트워크 호출(무료 countTokens endpoint)이다: shadow 검증·canary
  대조 전용이며, 대량 경로에 넣기 전 지연·실패율을 별도 감수한다. 호출
  실패는 예외로 전파한다(추정값 대체 금지 — 게이트가 TOKENIZER_UNAVAILABLE
  로 BYPASS 처리).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from .token_counter_registry import (
    ProviderRequest,
    TokenCounterAdapter,
    register_adapter,
)

__all__ = ["GEMINI_COUNTER_VERSION", "GeminiTokenCounterAdapter",
           "build_gemini_request_body", "build_gemini_adapter",
           "register_gemini_shadow_adapter"]

# counter 구현 버전 — 매핑(build_gemini_request_body)·endpoint 의미가
# 바뀌면 반드시 올린다(validation identity 구성 요소 → 재감수).
GEMINI_COUNTER_VERSION = "countTokens-v1beta-r1"
_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _api_key() -> str:
    """GEMINI_API_KEY 해소(.env 자동 로드 재사용) — 부재 시 예외."""
    from .llm_client import _load_env_files
    _load_env_files()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY 미설정 — adapter 계수 불가")
    return key


def build_gemini_request_body(request: ProviderRequest) -> dict[str, Any]:
    """ProviderRequest → Gemini generateContentRequest 본문(계수 SSOT).

    countTokens와 generateContent가 **동일한 이 본문**을 사용해야 계수
    대상=실제 전송 요청 계약이 성립한다. output_schema/tool_schema/
    generation_config는 JSON 문자열로 받아 그대로 반영한다(누락=과소
    계산 위험이므로 파싱 실패는 예외 전파).
    """
    body: dict[str, Any] = {}
    if request.system_messages:
        body["systemInstruction"] = {
            "parts": [{"text": m} for m in request.system_messages]}
    body["contents"] = [{"role": "user", "parts": [{"text": m}]}
                        for m in request.user_messages] or [
        {"role": "user", "parts": [{"text": ""}]}]
    generation_config: dict[str, Any] = {}
    if request.generation_config:
        generation_config.update(json.loads(request.generation_config))
    if request.output_schema:
        generation_config["responseMimeType"] = "application/json"
        generation_config["responseSchema"] = json.loads(
            request.output_schema)
    if generation_config:
        body["generationConfig"] = generation_config
    if request.tool_schema:
        body["tools"] = json.loads(request.tool_schema)
    return body


@dataclass(frozen=True)
class GeminiTokenCounterAdapter(TokenCounterAdapter):
    """Gemini countTokens 정밀 계수 어댑터 — count_request가 정본."""

    timeout_seconds: float = 30.0

    def count_request(self, request: ProviderRequest) -> int:
        """provider request 전체를 countTokens endpoint로 정밀 계수."""
        body = build_gemini_request_body(request)
        res = httpx.post(
            f"{_API_BASE}/{self.model_id}:countTokens",
            json={"generateContentRequest": {
                "model": f"models/{self.model_id}", **body}},
            headers={"x-goog-api-key": _api_key()},
            timeout=self.timeout_seconds)
        res.raise_for_status()
        return int(res.json()["totalTokens"])


def build_gemini_adapter(model_id: str,
                         validation_corpus_hash: str = "",
                         ) -> GeminiTokenCounterAdapter:
    """실물 Gemini adapter 생성(미등록) — corpus hash는 harness 산출값."""
    def _count_text(text: str) -> int:
        adapter = build_gemini_adapter(model_id, validation_corpus_hash)
        return adapter.count_request(
            ProviderRequest(user_messages=(text,)))

    return GeminiTokenCounterAdapter(
        model_id=model_id,
        mode="PROVIDER_EXACT",
        counter=_count_text,
        provider_id="gemini",
        counter_version=GEMINI_COUNTER_VERSION,
        request_schema_version="1",
        validation_corpus_hash=validation_corpus_hash)


def register_gemini_shadow_adapter(
        model_id: str, validation_corpus_hash: str = "",
) -> GeminiTokenCounterAdapter:
    """shadow 검증용 명시 등록 — 등록 직후 SHADOW_VALIDATING(승격 없음)."""
    adapter = build_gemini_adapter(model_id, validation_corpus_hash)
    register_adapter(adapter)
    return adapter
