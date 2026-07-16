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
from dataclasses import dataclass

__all__ = ["TokenCounterAdapter", "register_adapter", "resolve_counter"]


@dataclass(frozen=True)
class TokenCounterAdapter:
    """모델별 token counter — model_id는 alias 해소 후의 resolved ID."""

    model_id: str
    mode: str  # PROVIDER_EXACT | MODEL_TOKENIZER
    counter: Callable[[str], int]


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
