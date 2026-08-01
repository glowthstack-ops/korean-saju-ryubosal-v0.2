"""운 관계 shadow 플래그 (P1-b2, 2026-08-01).

P1-a·P1-b1 은 순수 함수만 추가해 플래그가 필요 없었다. P1-b2 에서 **생산 호출부가 처음
생기므로** 여기서 플래그를 도입한다. 함수가 존재하는 시점이 아니라 생산 경로가 호출하는
시점에 추가한다.

두 플래그의 관계:

    graph  만 ON  → 그래프까지만 만든다
    state  만 ON  → 그래프도 만든다(상태 조립의 재료라 없으면 못 만든다)
    둘 다 ON      → 그래프를 **한 번만** 만든다

`os.environ` 을 직접 읽는 곳은 이 모듈뿐이다. 서비스는 해석된 값을 읽는다.
"""

from __future__ import annotations

import os as _os

_GRAPH_ENV = "SAJU_LUCK_RELATION_GRAPH_SHADOW_ENABLED"
_STATE_ENV = "SAJU_LUCK_RELATION_STATE_SHADOW_ENABLED"


def _env_flag(name: str, default: bool) -> bool:
    """boolean env override — 정확히 "true"/"1"·"false"/"0" 만 인정(그 외=기본값).

    오타·오염으로 켜지는 경로를 두지 않는다(fail-closed). 코드 기본값이 False 라 env 없이는
    아무것도 켜지지 않는다.
    """
    raw = (_os.environ.get(name) or "").strip().lower()
    if raw in ("true", "1"):
        return True
    if raw in ("false", "0"):
        return False
    return default


#: 관계 의존 그래프(P1-a) shadow.
LUCK_RELATION_GRAPH_SHADOW_ENABLED: bool = _env_flag(_GRAPH_ENV, False)

#: 상태 원장 체인(P1-b2) shadow. ON 이면 그래프도 만든다.
LUCK_RELATION_STATE_SHADOW_ENABLED: bool = _env_flag(_STATE_ENV, False)


def should_build_relation_graph() -> bool:
    """그래프를 만들어야 하는가. 상태 플래그가 켜져 있으면 그래프 플래그와 무관하게 만든다."""
    return LUCK_RELATION_GRAPH_SHADOW_ENABLED or LUCK_RELATION_STATE_SHADOW_ENABLED


def should_build_relation_state_chain() -> bool:
    """상태 체인을 조립해야 하는가."""
    return LUCK_RELATION_STATE_SHADOW_ENABLED
