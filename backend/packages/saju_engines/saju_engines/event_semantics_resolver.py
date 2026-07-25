"""이벤트 의미 3분리 공통 resolver — CAREER_TRANSITION_SYSTEM §11-4·§11-5.

reader마다 fallback을 각자 구현하면 drift가 생기므로(question_generator는 event_key
기준, feedback_scorer는 legacy category 기준) **각 reader는 자체 매핑표를 만들지 않고
이 resolver만 소비한다.**

해소 우선순위(§11-4):
1. canonical `event_key` 매핑이 의미 SSOT
2. 신규 필드가 있으면 canonical과 **일치 검증**(`EXPLICIT_VALIDATED`)
3. `event_key`가 없을 때만 legacy category 보조
4. **legacy category만으로 `transition_family`를 확정하지 않는다**
5. 모호하면 `LEGACY_AMBIGUOUS`로 **fail-closed**

**P0-B 범위**: 순수 함수이며 기존 소비처를 전환하지 않는다. 기존 `EVENT_CATEGORY`·
`CATEGORY_TO_CALIB_DOMAIN`·직렬화는 그대로 두고(D12·INV-20), 이 결과는 shadow 계측만
소비한다.
"""

from __future__ import annotations

from saju_shared_types.event_engine import EventKeyV2
from saju_shared_types.event_semantics import (
    CANONICAL_EVENT_SEMANTICS,
    LEGACY_KEY_NORMALIZATION,
    SEMANTICS_CONTRACT_VERSION,
    CalibrationCapKey,
    CanonicalEventSemantics,
    ResolutionSource,
    ResolvedEventSemantics,
    TransitionFamily,
)
from saju_shared_types.event_taxonomy_v2 import EVENT_DOMAIN


def _fail_closed(source: ResolutionSource) -> ResolvedEventSemantics:
    """의미 필드를 전부 None으로 둔 fail-closed 결과 — 부분 fallback을 막는다."""
    return ResolvedEventSemantics(
        event_domain=None,
        transition_family=None,
        calibration_domain=None,
        calibration_cap_key=None,
        resolution_source=source,
        contract_version=SEMANTICS_CONTRACT_VERSION,
    )


def _canonical_semantics(event_key: EventKeyV2) -> CanonicalEventSemantics:
    """canonical 의미 조회.

    §11-5가 규정한 4키 밖의 canonical 키는 `event_domain`(기존 EVENT_DOMAIN)만 해소하고
    형제 가족·캘리브레이션 의미는 **본 Phase 범위 밖(None)** 으로 둔다 — 억지로 career
    의미를 채우지 않는다.
    """
    known = CANONICAL_EVENT_SEMANTICS.get(event_key)
    if known is not None:
        return known
    return CanonicalEventSemantics(event_domain=EVENT_DOMAIN[event_key])


def _normalize_event_key(event_key: EventKeyV2 | str | None) -> EventKeyV2 | None:
    """legacy 문자열을 canonical key로 정규화한다(`resignation` → `career_change`).

    canonical `EventKeyV2`에 없는 legacy 문자열(예: `travel`)은 None을 돌려주고 legacy
    보조 경로로 넘긴다 — legacy `move`라는 이유로 형제 가족에 넣지 않기 위함.
    """
    if event_key is None:
        return None
    if isinstance(event_key, EventKeyV2):
        return event_key
    normalized = LEGACY_KEY_NORMALIZATION.get(event_key)
    if normalized is not None:
        return normalized
    try:
        return EventKeyV2(event_key)
    except ValueError:
        return None


def resolve_event_semantics(
    event_key: EventKeyV2 | str | None = None,
    *,
    explicit_event_domain: str | None = None,
    explicit_transition_family: TransitionFamily | str | None = None,
    explicit_calibration_domain: str | None = None,
    legacy_category: str | None = None,
) -> ResolvedEventSemantics:
    """이벤트 의미를 해소한다 — 3분리 필드의 단일 소유자.

    Args:
        event_key: canonical `EventKeyV2` 또는 legacy 문자열(정규화 대상).
        explicit_event_domain: 전달본에 실려 온 `event_domain`(검증 대상, 권위 아님).
        explicit_transition_family: 전달본 `transition_family`(검증 대상).
        explicit_calibration_domain: 전달본 `calibration_domain`(검증 대상).
        legacy_category: legacy `EVENT_CATEGORY` 값. **event_key가 없을 때만 보조로
            쓰이며, 이 값만으로 `transition_family`를 확정하지 않는다.**

    Returns:
        해소 결과. `LEGACY_AMBIGUOUS`·`INVALID_MISMATCH`면 의미 필드가 전부 None이고
        `is_consumable`이 False다.

    Note:
        `calibration_cap_key`는 호출자가 입력하는 권위 필드가 아니라 canonical
        event_key에서 **파생**된다(D21). 인자로 받지 않는다.
    """
    canonical_key = _normalize_event_key(event_key)

    # ③ event_key가 없을 때만 legacy 보조 — ④ legacy 단독으로 family 확정 금지.
    if canonical_key is None:
        if legacy_category is None:
            return _fail_closed(ResolutionSource.LEGACY_AMBIGUOUS)
        # legacy category는 여러 canonical 키가 공유한다(예: legacy move = 4멤버).
        # 어느 키인지 특정할 수 없으므로 fail-closed 한다.
        return _fail_closed(ResolutionSource.LEGACY_AMBIGUOUS)

    canonical = _canonical_semantics(canonical_key)

    # ② 전달본이 있으면 canonical과 일치 검증 — 충돌하면 그대로 신뢰하지 않는다.
    explicit_family = (
        TransitionFamily(explicit_transition_family)
        if isinstance(explicit_transition_family, str)
        else explicit_transition_family
    )
    provided = (
        explicit_event_domain is not None
        or explicit_family is not None
        or explicit_calibration_domain is not None
    )
    if provided:
        mismatched = (
            (explicit_event_domain is not None and explicit_event_domain != canonical.event_domain)
            or (explicit_family is not None and explicit_family != canonical.transition_family)
            or (
                explicit_calibration_domain is not None
                and explicit_calibration_domain != canonical.calibration_domain
            )
        )
        if mismatched:
            return _fail_closed(ResolutionSource.INVALID_MISMATCH)
        source = ResolutionSource.EXPLICIT_VALIDATED
    else:
        source = ResolutionSource.CANONICAL

    return ResolvedEventSemantics(
        event_domain=canonical.event_domain,
        transition_family=canonical.transition_family,
        calibration_domain=canonical.calibration_domain,
        calibration_cap_key=canonical.calibration_cap_key,
        resolution_source=source,
        contract_version=SEMANTICS_CONTRACT_VERSION,
    )


def is_semantics_stale(contract_version: str) -> bool:
    """저장·캐시된 해소 결과가 현재 계약과 다른지 — 다르면 재해소 대상이다(§13-1)."""
    return contract_version != SEMANTICS_CONTRACT_VERSION


__all__ = [
    "CalibrationCapKey",
    "ResolutionSource",
    "ResolvedEventSemantics",
    "TransitionFamily",
    "is_semantics_stale",
    "resolve_event_semantics",
]
