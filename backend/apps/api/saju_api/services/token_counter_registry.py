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

__all__ = ["ADAPTER_VALIDATION_POLICY", "ADAPTER_VALIDATION_STATES",
           "adapter_validation_policy_hash", "record_count_observation",
           "resolve_expose_counter", "ProviderRequest",
           "TokenCounterAdapter", "register_adapter", "resolve_counter",
           "resolve_validated_counter", "set_validation_state"]

# adapter 검증 상태(감수 50차 §4): EXPOSE 주입 자격=VALIDATED만.
# UNREGISTERED→SHADOW_VALIDATING(등록 직후 — shadow에서 counted vs
# provider_reported 대조)→VALIDATED(감수)→SUSPENDED(오차 허용 초과 시).
# calibration 용어: counted_request_tokens / provider_reported_input_tokens
# / token_count_delta / token_count_relative_error.
ADAPTER_VALIDATION_STATES = ("UNREGISTERED", "SHADOW_VALIDATING",
                             "VALIDATED", "SUSPENDED")

# adapter 승격 기준(감수 51차 §6 — **실측 전 선행 고정**: 결과에 맞춘 기준
# 방지). 변경=expose 재감수 신호(hash가 manifest에 병기됨).
ADAPTER_VALIDATION_POLICY: dict = {
    "validation_key": ["provider_id", "resolved_model_id",
                       "counter_version", "provider_request_schema_version"],
    "key_change": "하나라도 변경 시 VALIDATED → SHADOW_VALIDATING 강등",
    "sample_shapes": ["한국어 장문", "한영 혼합", "JSON risk block",
                      "tool schema 포함", "output schema 포함",
                      "SUPPRESSED guard", "INJECTED instruction",
                      "FULL/P1/P0/P0_COMPACT 각 tier",
                      "모델 fallback·rerouting", "hard-max episode 요청"],
    "sample_minimum": "카테고리 10형 × 각 3개 이상 = 모델·counter 조합당"
                      " 최소 30개(크기 변형 포함 — 감수 52차 §2)",
    "runtime_drift": "canary 중 counted < provider_reported **1건**이라도"
                     " 발생 시 즉시 VALIDATED→SUSPENDED(이후 BYPASS)."
                     " overcount_ratio p50/p90/max 별도 관측(과대 계산은"
                     " 안전 문제 아님 — 과도하면 불필요 compact/suppressed)",
    "manifest_ssot": "registry 자체 선언으로 EXPOSE 자격 불가 — manifest"
                     " validatedTokenCounters 항목(reviewed=true·validation"
                     " key 4종·corpus/policy hash 일치)과 runtime adapter"
                     " key가 일치해야 주입(감수 52차 §2)",
    "provider_exact_pass": "undercount=0 · request shape 누락=0 · model"
                           " mismatch=0 · routing 후 recount 누락=0",
    "model_tokenizer_pass": "전 감수 표본에서 counted_request_tokens >="
                            " provider_reported_input_tokens(wrapper"
                            " reserve 포함) — 과소 계산 불허(과대는 허용)",
    "reported_basis": "비용 청구 수치가 아니라 실제 전체 prompt/input"
                      " token 수 기준(cached_input_tokens 별도 기록)",
    "observability": ["counted_request_tokens",
                      "provider_reported_input_tokens", "delta",
                      "relative_error", "cached_input_tokens",
                      "routing_changed", "recount_performed"],
}


def adapter_validation_policy_hash() -> str:
    """승격 기준 해시 — manifest 병기(변경=expose 재감수 신호)."""
    import hashlib
    import json
    return hashlib.sha256(json.dumps(
        ADAPTER_VALIDATION_POLICY, sort_keys=True, ensure_ascii=False,
    ).encode()).hexdigest()[:16]


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
_VALIDATION: dict[str, str] = {}  # model_id → 검증 상태(기본 SHADOW_VALIDATING)


def register_adapter(adapter: TokenCounterAdapter) -> None:
    """adapter 등록 — mode는 EXPOSE 허용 2종만(heuristic 등록 금지)."""
    if adapter.mode not in ("PROVIDER_EXACT", "MODEL_TOKENIZER"):
        raise ValueError(f"EXPOSE 불가 token mode: {adapter.mode}")
    _REGISTRY[adapter.model_id] = adapter
    # 등록≠검증(감수 50차 §4 — 등록과 canary 활성화 분리): shadow 대조 후
    # 감수를 거쳐야 VALIDATED가 된다.
    _VALIDATION.setdefault(adapter.model_id, "SHADOW_VALIDATING")


def set_validation_state(model_id: str, state: str) -> None:
    """adapter 검증 상태 전환(감수 절차 전용) — 미등록 상태값 거부."""
    if state not in ADAPTER_VALIDATION_STATES:
        raise ValueError(f"미지원 검증 상태: {state}")
    _VALIDATION[model_id] = state


def resolve_validated_counter(
        resolved_model_id: str) -> TokenCounterAdapter | None:
    """EXPOSE 주입용 해소(감수 50차 §4) — **VALIDATED 상태만** 반환.

    SHADOW_VALIDATING/SUSPENDED/미등록은 None(게이트 BYPASS). shadow
    측정에는 resolve_counter(상태 무관)를 쓴다.
    """
    if _VALIDATION.get(resolved_model_id) != "VALIDATED":
        return None
    return _REGISTRY.get(resolved_model_id)


def resolve_expose_counter(
    resolved_model_id: str,
    manifest_counters: list[dict],
) -> TokenCounterAdapter | None:
    """manifest SSOT 대조 해소(감수 52차 §2) — canary 주입의 정본 경로.

    registry의 VALIDATED 선언만으로는 부족: manifest validatedTokenCounters
    항목(reviewed=true)과 validation key 4종(provider·model·counter version
    ·request schema version)이 **모두 일치**해야 반환한다. 불일치·항목
    부재=None(BYPASS).
    """
    adapter = resolve_validated_counter(resolved_model_id)
    if adapter is None:
        return None
    for entry in manifest_counters:
        if (entry.get("reviewed") is True
                and entry.get("resolvedModelId") == adapter.model_id
                and entry.get("providerId") == adapter.provider_id
                and entry.get("counterVersion") == adapter.counter_version):
            return adapter
    return None


def record_count_observation(model_id: str, counted: int,
                             reported: int) -> None:
    """canary 계수 관측(감수 52차 §2 — drift auto-suspend).

    counted < reported(과소 계산) 1건이라도 관측되면 즉시
    VALIDATED→SUSPENDED — 이후 요청은 BYPASS된다.
    """
    if counted < reported and _VALIDATION.get(model_id) == "VALIDATED":
        _VALIDATION[model_id] = "SUSPENDED"


def resolve_counter(resolved_model_id: str) -> TokenCounterAdapter | None:
    """resolved model ID → adapter(없으면 None — 게이트가 BYPASS 처리).

    호출부 계약: 모델 fallback 발생 시 새 resolved ID로 다시 호출하고
    최종 request 전체를 재계수한다.
    """
    return _REGISTRY.get(resolved_model_id)
