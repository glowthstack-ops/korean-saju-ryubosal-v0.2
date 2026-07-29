"""장기 rolling 감사 집계 — 현재 OA-10b 의미를 복제하는 **버전 계약**.

일반적인 "coverage aggregate" 가 아니다. 지금 OA-10b 가 실제로 계산하는 것을 그대로
옮긴 것이고, 이름과 축이 어긋난 부분까지 포함한다.

    · 통과 판정은 key AND family 결합 게이트다. domain 은 게이트가 아니다.
    · `bottom_6_iljus` 는 family 가 아니라 **key** coverage 15 미만이다.
    · episode 최저값과 영향 일주도 **key** 축이다.
    · `episode_id` 의 `family-coverage` 접두사는 legacy 포맷 상수일 뿐이며,
      코드가 이 문자열을 보고 의미를 추론해서는 안 된다.

의미를 개선하려면 이 계약을 고치지 말고 **새 버전**을 만든다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any

DAILY_ROLLING_AUDIT_AGGREGATE_CONTRACT_VERSION = "daily-rolling-audit-aggregate.v1"

#: legacy 포맷 상수. 의미를 담지 않는다.
EPISODE_ID_PREFIX = "family-coverage"

#: p10 은 라이브러리 percentile 이 아니라 **고정 index** 다. 60개를 오름차순으로
#: 정렬해 6번째(index 5)를 집는다 — interpolation 방식이 바뀌어도 움직이지 않는다.
P10_SAMPLE_SIZE = 60
P10_INDEX = 5


class RollingAuditInputError(ValueError):
    """집계 전에 입력을 막는다 — 부분 결과를 돌려주지 않는다."""


@dataclass(frozen=True)
class RollingAuditAggregateContract:
    """무엇을 어떤 축으로 집계하는지 명시한다."""

    version: str = DAILY_ROLLING_AUDIT_AGGREGATE_CONTRACT_VERSION
    board_size: int = P10_SAMPLE_SIZE
    pass_axes: str = "KEY_AND_FAMILY"
    pass_threshold: int = 15
    domain_gate_applied: bool = False
    p10_index: int = P10_INDEX
    recovery_target: int = 16
    expiry_horizon_days: int = 7
    window_days: int = 90
    warmup_days: int = 180
    first_anchor: date = date(2026, 1, 1)
    anchor_days: int = 730
    bottom_ilju_axis: str = "KEY"
    bottom_ilju_threshold: int = 15
    bottom_ilju_limit: int = 6
    bottom_ilju_order: str = "LEGACY_SORTED_ORDER"
    episode_trigger: str = "COMBINED_KEY_AND_FAMILY_GATE_FAILURE"
    episode_minimum_axis: str = "KEY"
    episode_affected_axis: str = "KEY"
    episode_affected_order: str = "SORTED_UNIQUE"
    episode_id_prefix: str = EPISODE_ID_PREFIX
    episode_id_prefix_semantics: str = "LEGACY_LABEL_NOT_AUTHORITATIVE"


ROLLING_AUDIT_AGGREGATE_CONTRACT_V1 = RollingAuditAggregateContract()

#: 공식 v1 계약으로 낸 결과인지, 짧은 진단 실행인지 구분한다. canonical 결과만
#: 동결 증거 경로에 쓸 수 있다.
CONTRACT_MODE_CANONICAL = "CANONICAL"
CONTRACT_MODE_DIAGNOSTIC = "NONCANONICAL_DIAGNOSTIC"


def contract_mode(contract: RollingAuditAggregateContract) -> str:
    """이 계약이 공식 v1 인가."""
    return (
        CONTRACT_MODE_CANONICAL
        if contract == ROLLING_AUDIT_AGGREGATE_CONTRACT_V1
        else CONTRACT_MODE_DIAGNOSTIC
    )


def derive_diagnostic_contract(
    *,
    base: RollingAuditAggregateContract = ROLLING_AUDIT_AGGREGATE_CONTRACT_V1,
    anchor_days: int,
) -> RollingAuditAggregateContract:
    """짧은 진단 실행용 계약 — **anchor 일수만** 바꾼다.

    호출부가 `replace()` 를 무제한으로 쓰면 cap 이나 의미 축까지 조용히 달라질 수
    있다. 여기서 바꿀 수 있는 것을 하나로 묶는다.

    Args:
        base: 기준 계약.
        anchor_days: 진단 실행의 anchor 수.

    Returns:
        anchor 수만 다른 계약. 결과는 canonical 이 아니다.

    Raises:
        ValueError: anchor 수가 1 미만일 때.
    """
    if anchor_days < 1:
        raise ValueError(f"anchor_days 는 1 이상이어야 한다: {anchor_days}")
    return replace(base, anchor_days=anchor_days)


def validate_rows(
    rows: Sequence[Mapping[str, Any]], contract: RollingAuditAggregateContract
) -> list[str]:
    """fail-closed 입력 검증 — 누락 일주를 분모에서 조용히 빼지 않는다.

    Args:
        rows: 날짜·일주 순서의 행.
        contract: 집계 계약.

    Returns:
        공식 60갑자 순서의 일주 목록(첫 날짜 등장 순서).

    Raises:
        RollingAuditInputError: 중복·누락·정렬 위반·구간 부족.
    """
    size = contract.board_size
    if not rows:
        raise RollingAuditInputError("행이 비어 있다")
    if len(rows) % size:
        raise RollingAuditInputError(f"행 수가 {size} 의 배수가 아니다: {len(rows)}")

    seen: set[tuple[str, str]] = set()
    by_date: dict[str, list[str]] = {}
    order: list[str] = []
    for row in rows:
        key = (row["fortune_date"], row["ilju"])
        if key in seen:
            raise RollingAuditInputError(f"날짜x일주 중복: {key}")
        seen.add(key)
        by_date.setdefault(row["fortune_date"], []).append(row["ilju"])
        if row["ilju"] not in order:
            order.append(row["ilju"])

    if len(order) != size:
        raise RollingAuditInputError(f"고유 일주 {len(order)} != {size}")
    expected = set(order)
    for day, iljus in by_date.items():
        if len(iljus) != size:
            raise RollingAuditInputError(f"{day}: 행 {len(iljus)} != {size}")
        if set(iljus) != expected:
            missing = sorted(expected - set(iljus))
            raise RollingAuditInputError(f"{day}: 일주 누락 {missing}")

    days = list(by_date)
    # 엄밀히는 "strictly increasing and consecutive" 다. 중복은 위에서 이미 막았고,
    # 간격은 반드시 1일이어야 한다.
    if days != sorted(days):
        raise RollingAuditInputError("날짜가 순증가하지 않는다")
    for a, b in zip(days[:-1], days[1:], strict=True):
        if date.fromisoformat(b) - date.fromisoformat(a) != timedelta(days=1):
            raise RollingAuditInputError(f"날짜 연속성 단절: {a} → {b}")

    need = contract.warmup_days + contract.window_days + contract.anchor_days
    if len(days) != need:
        raise RollingAuditInputError(f"생성일 {len(days)} != {need}")
    first_anchor_index = contract.warmup_days + contract.window_days
    if date.fromisoformat(days[first_anchor_index]) != contract.first_anchor:
        raise RollingAuditInputError(
            f"첫 공식 anchor 가 {days[first_anchor_index]} — "
            f"{contract.first_anchor} 여야 한다"
        )
    # 마지막 날짜가 논리적으로 따라오더라도 감사 가능성을 위해 직접 검사한다.
    expected_last = contract.first_anchor + timedelta(days=contract.anchor_days - 1)
    if date.fromisoformat(days[-1]) != expected_last:
        raise RollingAuditInputError(
            f"마지막 날짜가 {days[-1]} — {expected_last} 여야 한다"
        )
    return order


def _p10(values: list[int], contract: RollingAuditAggregateContract) -> int:
    """오름차순 정렬 후 고정 index 를 그대로 집는다.

    라이브러리 percentile 을 쓰지 않는다 — interpolation 방식이 바뀌면 결과가
    움직인다. 60개 중 6번째로 작은 값(index 5)이라는 정의 자체를 코드로 둔다.
    """
    if len(values) != contract.board_size:
        raise RollingAuditInputError(
            f"p10 입력이 {len(values)} 개 — {contract.board_size} 여야 한다"
        )
    return sorted(values)[contract.p10_index]


def build_rolling_audit_aggregates(
    rows: Sequence[Mapping[str, Any]],
    family_of: Mapping[str, str],
    domain_of: Mapping[str, str],
    contract: RollingAuditAggregateContract = ROLLING_AUDIT_AGGREGATE_CONTRACT_V1,
) -> dict[str, Any]:
    """730 anchor 집계와 실패 episode.

    Args:
        rows: 날짜·일주 순서의 행(`fortune_date` · `ilju` · `final_headline`).
        family_of: event_key → semantic family.
        domain_of: event_key → domain.
        contract: 집계 계약.

    Returns:
        `anchors` · `episodes` · `transitions` · `summary`.
    """
    order = validate_rows(rows, contract)
    size = contract.board_size
    series: dict[str, list[str]] = {ilju: [] for ilju in order}
    for row in rows:
        series[row["ilju"]].append(row["final_headline"])

    target = contract.pass_threshold
    horizon = contract.expiry_horizon_days
    anchors: list[dict[str, Any]] = []
    # 잘리지 않은 below 목록. `anchors` **바깥**에 둔다 — anchor 지문은 anchors
    # payload 만 덮으므로, 진단용 필드를 안에 넣으면 지문이 움직인다.
    below_by_anchor: dict[str, list[str]] = {}
    #: family 축 진단. legacy 의 `below`·`qualifying_ilju_count` 는 둘 다 **key**
    #: 축이라 family 축 판정에 쓸 수 없다. 같은 family coverage 벡터에서 한 번에
    #: 파생하고, 순서는 공식 60갑자 board 순서를 유지한다.
    family_below_by_anchor: dict[str, list[str]] = {}

    for step in range(contract.anchor_days):
        lo = contract.warmup_days + step
        hi = lo + contract.window_days
        anchor = contract.first_anchor + timedelta(days=step)
        keys: list[int] = []
        fams: list[int] = []
        doms: list[int] = []
        below: list[str] = []
        family_below: list[str] = []
        at_risk = 0
        for ilju in order:
            window = series[ilju][lo:hi]
            distinct = set(window)
            key_cov = len(distinct)
            fam_cov = len({family_of.get(e, e) for e in distinct})
            keys.append(key_cov)
            fams.append(fam_cov)
            doms.append(len({domain_of[e] for e in distinct}))
            if key_cov < contract.bottom_ilju_threshold:
                below.append(ilju)
            if fam_cov < contract.pass_threshold:
                family_below.append(ilju)
            # 창 안에서 각 family 를 마지막으로 본 위치(0 = 가장 오래된 날).
            last_seen: dict[str, int] = {}
            for offset, event in enumerate(window):
                last_seen[family_of.get(event, event)] = offset
            projected = sum(1 for pos in last_seen.values() if pos >= horizon)
            if fam_cov >= contract.recovery_target and projected < target:
                at_risk += 1

        key_p10 = _p10(keys, contract)
        family_p10 = _p10(fams, contract)
        domain_p10 = _p10(doms, contract)
        anchors.append({
            "anchor_date": anchor.isoformat(),
            "key_p10": key_p10,
            "family_p10": family_p10,
            "domain_p10": domain_p10,
            "count_below_15": len(below),
            "count_equal_14": len([v for v in keys if v == 14]),
            "bottom_6_iljus": sorted(below)[:contract.bottom_ilju_limit],
            "expiry_at_risk_iljus": at_risk,
            # domain 은 게이트에 들어가지 않는다.
            "passes": key_p10 >= target and family_p10 >= target,
            "key_min": min(keys),
            "family_min": min(fams),
            "domain_min": min(doms),
            "qualifying_ilju_count": len([v for v in keys if v >= target]),
        })
        below_by_anchor[anchor.isoformat()] = list(below)
        family_below_by_anchor[anchor.isoformat()] = list(family_below)

    return {
        "contract_version": contract.version,
        "anchors": anchors,
        "episodes": build_failure_episodes(anchors, contract),
        "transitions": {
            axis: transition_dates(anchors, f"{axis}_p10", contract)
            for axis in ("key", "family")
        },
        "summary": {
            "anchors": len(anchors),
            "passing": len([a for a in anchors if a["passes"]]),
            "episodes": len(build_failure_episodes(anchors, contract)),
            "anchors_in_2025": len(
                [a for a in anchors if a["anchor_date"][:4] == "2025"]
            ),
            "duplicate_anchors": (
                len(anchors) - len({a["anchor_date"] for a in anchors})
            ),
        },
        "board_size": size,
        # family 축 진단 — 지문 대상이 아니다. 정책이 읽어서는 안 된다(정책은 각
        # 일주의 과거 이력만 보고, 이 값은 사후 평가용이다).
        "family_below_iljus_by_anchor": family_below_by_anchor,
        "family_qualifying_count_by_anchor": {
            iso: contract.board_size - len(iljus)
            for iso, iljus in family_below_by_anchor.items()
        },
        # NON_FINGERPRINTED_CALLER_DIAGNOSTIC — 새 canonical 결과 축이 아니다.
        # 키는 공식 anchor 날짜 730개, 값은 bottom_6 절단 **이전**의 전체 목록이며
        # 순서는 legacy below 누적 순서 그대로다. 호출부가
        # `repeatedly_below_iljus` 를 만들 때만 쓴다.
        "below_iljus_by_anchor": below_by_anchor,
    }


def build_failure_episodes(
    anchors: Sequence[Mapping[str, Any]],
    contract: RollingAuditAggregateContract = ROLLING_AUDIT_AGGREGATE_CONTRACT_V1,
) -> list[dict[str, Any]]:
    """연속 실패 구간. 기간은 양 끝 날짜를 **포함**한다."""
    episodes: list[dict[str, Any]] = []
    run: list[Mapping[str, Any]] = []

    def flush() -> None:
        if not run:
            return
        start, end = run[0]["anchor_date"], run[-1]["anchor_date"]
        worst = min(a["key_p10"] for a in run)      # 최저값 축은 KEY 다
        episodes.append({
            "episode_id": f"{contract.episode_id_prefix}:{start}:{end}",
            "episode_start": start,
            "episode_end": end,
            "duration_days": (
                date.fromisoformat(end) - date.fromisoformat(start)
            ).days + 1,
            "minimum_key_p10": worst,
            "minimum_key_p10_dates": [
                a["anchor_date"] for a in run if a["key_p10"] == worst
            ],
            "worst_count_below_15": max(a["count_below_15"] for a in run),
            "affected_iljus": sorted(
                {i for a in run for i in a["bottom_6_iljus"]}
            ),
        })
        run.clear()

    for anchor in anchors:
        if anchor["passes"]:
            flush()
        else:
            run.append(anchor)
    flush()
    return episodes


def transition_dates(
    anchors: Sequence[Mapping[str, Any]],
    axis: str,
    contract: RollingAuditAggregateContract = ROLLING_AUDIT_AGGREGATE_CONTRACT_V1,
) -> dict[str, list[str]]:
    """`D-1 → D` 전환 날짜. 첫 anchor 는 이전 값이 없어 제외한다."""
    target = contract.pass_threshold
    to_15: list[str] = []
    to_14: list[str] = []
    for index in range(1, len(anchors)):
        prev, cur = anchors[index - 1][axis], anchors[index][axis]
        if prev < target <= cur:
            to_15.append(anchors[index]["anchor_date"])
        elif cur < target <= prev:
            to_14.append(anchors[index]["anchor_date"])
    return {"to_15_dates": to_15, "to_14_dates": to_14}
