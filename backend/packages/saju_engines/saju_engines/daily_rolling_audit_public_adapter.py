"""OA-10b 공개 JSON 호환 어댑터 — **필드 선택·배치 전용**.

두 계약을 분리한다.

    shared aggregate payload   내부 계산·감사 SSOT. 확장 필드 포함.
                               anchor/episode fingerprint 대상.
    OA-10b public JSON         기존 외부 계약. legacy 필드만 노출.

이 모듈은 계산기가 아니다. p10 재계산·pass 재판정·bottom 재선별·episode 재분할·
repeatedly_below 재해석을 하지 않는다 — 이미 나온 결과에서 공개 계약 필드만 골라
기존 키 순서로 배치한다.

확장 필드를 기존 파일에 그대로 추가하지 않는다. 필드를 무시하지 않는 소비자가
깨질 수 있어서다. 확장이 실제로 필요해지면 별도 버전(`oa10b-public.v2` 또는
`rolling-audit-internal.v1`)으로 낸다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

#: 출력에 넣지 않는다 — 기존 JSON 에 버전 필드가 없었다.
OA10B_PUBLIC_SCHEMA_VERSION = "oa10b-public.v1"

OA10B_PUBLIC_DAILY_FIELDS_V1 = (
    "anchor_date",
    "key_p10",
    "family_p10",
    "domain_p10",
    "count_below_15",
    "count_equal_14",
    "bottom_6_iljus",
    "expiry_at_risk_iljus",
    "passes",
)

OA10B_PUBLIC_EPISODE_FIELDS_V1 = (
    "episode_start",
    "episode_end",
    "duration_days",
    "minimum_key_p10",
    "affected_iljus",
)


class OA10BPublicProjectionError(RuntimeError):
    """공개 계약 필드가 사라졌다 — 조용히 축소된 출력을 내지 않는다."""


def _project(
    row: Mapping[str, Any], fields: Sequence[str], kind: str
) -> dict[str, Any]:
    missing = [f for f in fields if f not in row]
    if missing:
        raise OA10BPublicProjectionError(
            f"{kind} 공개 필드 누락: {missing} — shared builder 가 필드를 없앴다면 "
            f"공개 계약을 먼저 검토해야 한다"
        )
    return {f: row[f] for f in fields}


def project_daily_v1(
    anchors: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """anchor 행을 공개 계약 필드로 투영한다(확장 필드는 노출하지 않는다)."""
    return [_project(a, OA10B_PUBLIC_DAILY_FIELDS_V1, "daily") for a in anchors]


def project_episodes_v1(
    episodes: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """episode 를 공개 계약 필드로 투영한다."""
    return [
        _project(e, OA10B_PUBLIC_EPISODE_FIELDS_V1, "episode") for e in episodes
    ]


def project_to_oa10b_public_v1(
    aggregates: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`(daily, episodes)` 공개 표현.

    Args:
        aggregates: `build_rolling_audit_aggregates()` 결과.

    Returns:
        공개 계약 필드만 담은 daily·episode 목록.

    Raises:
        OA10BPublicProjectionError: 공개 필드가 없을 때.
    """
    return (
        project_daily_v1(aggregates["anchors"]),
        project_episodes_v1(aggregates["episodes"]),
    )
