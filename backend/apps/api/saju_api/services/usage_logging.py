"""LLM 사용량 영속 로깅 배선 (운영 콘솔 Phase A).

llm_client의 usage sink에 연결돼, 호출 1건마다 관리자 등록 단가로 비용을 계산해 llm_usage에
적재한다. 단가는 호출마다 DB를 읽지 않도록 짧게 캐시한다. DSN 미설정 시 setup이 no-op이라
DB 없이도(테스트 등) 안전하다.
"""

from __future__ import annotations

import time

from saju_engines.usage_store import PricingStore, UsageStore, compute_cost_usd

from . import llm_client

_PRICE_TTL = 60.0  # 단가 캐시 수명(초)
_pricing: PricingStore | None = None
_usage: UsageStore | None = None
_price_cache: dict[str, tuple[float, float, float]] = {}
_price_cache_at = 0.0


def _price_for(model: str) -> tuple[float, float, float]:
    """모델 단가(input, output, cached) — TTL 캐시."""
    global _price_cache, _price_cache_at
    now = time.time()
    if now - _price_cache_at > _PRICE_TTL:
        _price_cache = {}
        _price_cache_at = now
    if model not in _price_cache and _pricing is not None:
        _price_cache[model] = _pricing.price_for(model)
    return _price_cache.get(model, (0.0, 0.0, 0.0))


def _sink(
    *, surface: str, model: str, provider: str, is_fallback: bool,
    input_tokens: int, output_tokens: int, cached_tokens: int,
    owner_id: str | None = None, product_code: str | None = None,
    call_type: str | None = None, ref_id: str | None = None,
) -> None:
    """호출 1건 → 비용 계산 후 llm_usage 적재(best-effort; llm_client가 예외를 삼킨다)."""
    if _usage is None:
        return
    in_p, out_p, cached_p = _price_for(model)
    cost = compute_cost_usd(
        input_tokens, output_tokens, cached_tokens, in_p, out_p, cached_p,
    )
    _usage.record(
        surface=surface, model=model, provider=provider, is_fallback=is_fallback,
        input_tokens=input_tokens, output_tokens=output_tokens, cached_tokens=cached_tokens,
        cost_usd=cost, owner_id=owner_id, product_code=product_code,
        call_type=call_type, ref_id=ref_id,
    )


def setup() -> bool:
    """admin 테이블 마이그레이션·단가 seed 후 sink를 주입한다. DSN 없으면 no-op(False)."""
    global _pricing, _usage
    try:
        _pricing = PricingStore()
        _usage = UsageStore()
    except ValueError:
        return False  # DSN 미설정 — 로깅 비활성(앱은 정상 기동)
    _usage.migrate()  # 009: llm_usage·model_pricing·admin_settings·is_admin (멱등)
    _pricing.seed_defaults()
    llm_client.set_usage_sink(_sink)
    return True
