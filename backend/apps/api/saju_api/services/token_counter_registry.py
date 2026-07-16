"""모델 tokenizer adapter registry (감수 48차 §10-③ — EXPOSE 필수 조건).

계약: configured model alias → 실제 resolved provider model → matching
counter. **등록 여부만 검사하지 않는다** — counter는 provider에 실제 전달되는
전체 요청(system·user·context·risk instruction/guard·block·schema)을
계수해야 하며, 모델 fallback/라우팅 변경 시 새 resolved model로 counter를
재해소하고 전체 request를 재계수해야 한다(이전 모델 count 재사용 금지).

기본 registry는 **비어 있다** — adapter 미등록 모델은 EXPOSE에서
TOKENIZER_UNAVAILABLE(BYPASS)로 처리된다(heuristic 대체 금지). 실물
adapter(Gemini token-count API·GPT 계열 tokenizer)는 canary 개시 차수에서
감수와 함께 등록한다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

__all__ = ["ProviderRequest", "TokenCounterAdapter", "register_adapter",
           "resolve_counter"]


@dataclass(frozen=True)
class ProviderRequest:
    """provider에 실제 전송되는 요청 전체(감수 49차 §4 — 계수 대상 SSOT).

    문자열 하나가 아니라 요청 전체를 계수한다: 모든 message(system/user)·
    risk instruction 또는 suppressed guard·risk block·output/tool schema·
    provider wrapper·모델 특수 토큰(어댑터 구현이 반영).
    """

    system_messages: tuple[str, ...] = field(default_factory=tuple)
    user_messages: tuple[str, ...] = field(default_factory=tuple)
    output_schema: str | None = None
    tool_schema: str | None = None
    generation_config: str | None = None


@dataclass(frozen=True)
class TokenCounterAdapter:
    """모델별 token counter — model_id는 alias 해소 후의 resolved ID.

    count_request가 정본(요청 전체 계수 — 감수 49차 §4). counter(문자열
    단건)는 block 단위 예비 계수 용도로만 유지한다.
    """

    model_id: str
    mode: str  # PROVIDER_EXACT | MODEL_TOKENIZER
    counter: Callable[[str], int]
    provider_id: str = ""
    counter_version: str = ""

    def count_request(self, request: ProviderRequest) -> int:
        """provider request 전체 계수 — 기본 구현은 전 구성요소 합산 +
        wrapper 여유(어댑터가 provider 정밀 계수로 재정의 가능)."""
        parts = [*request.system_messages, *request.user_messages]
        for extra in (request.output_schema, request.tool_schema,
                      request.generation_config):
            if extra:
                parts.append(extra)
        return sum(self.counter(p) for p in parts) + 4 * len(parts)


_REGISTRY: dict[str, TokenCounterAdapter] = {}


def register_adapter(adapter: TokenCounterAdapter) -> None:
    """adapter 등록 — mode는 EXPOSE 허용 2종만(heuristic 등록 금지)."""
    if adapter.mode not in ("PROVIDER_EXACT", "MODEL_TOKENIZER"):
        raise ValueError(f"EXPOSE 불가 token mode: {adapter.mode}")
    _REGISTRY[adapter.model_id] = adapter


def resolve_counter(resolved_model_id: str) -> TokenCounterAdapter | None:
    """resolved model ID → adapter(없으면 None — 게이트가 BYPASS 처리).

    호출부 계약: 모델 fallback 발생 시 새 resolved ID로 다시 호출하고
    최종 request 전체를 재계수한다.
    """
    return _REGISTRY.get(resolved_model_id)
