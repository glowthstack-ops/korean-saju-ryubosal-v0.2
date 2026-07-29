"""OA-10a — 날짜별 계약 해소(contract resolver).

`legacy-v0` adapter 안에 날짜 분기를 넣지 않는다. "그 날짜에 무엇이 살아 있었는가"는
여기서 해소하고, adapter 는 해소된 계약을 받아 **분기 없이** 동작한다.

    target_date → 당시 dict/content/rebalance 계약 해소 → legacy-v0 adapter 적용

가장 중요한 규칙: **없던 날짜를 지어내지 않는다.** 일운 서비스는 2026-07-23 에
시작했다. 그 이전 날짜에는 재현할 라이브 계약 자체가 없으므로, 현재 코드에 버전
문자열만 붙여 실행하면 그것은 재현이 아니라 **날조**다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from saju_engines.daily_fortune_snapshot import load_snapshot
from saju_engines.daily_ilju_fortune import (
    EVENT_SELECTION_COMPAT_SALT,
    SELECTOR_VERSION,
)
from saju_shared_types.daily_fortune import (
    ENGINE_VERSION,
    NARRATIVE_ROTATION_VERSION,
    PROMPT_VERSION,
    active_dict_version,
)

#: 일운 서비스 최초 게시일. 이 날 이전에는 보드가 존재하지 않았다.
#: (`git log --diff-filter=A` — 엔진·서비스·API·프론트 전부 2026-07-23 도입)
DAILY_FORTUNE_SERVICE_START = date(2026, 7, 23)

#: 날짜 경계로 사전 버전을 고르는 장치가 도입된 날. 이전 날짜는 사전 버전을
#: **날짜로 특정할 수 없다** — 그때는 버전을 올리며 제자리에서 교체했다.
DICT_DATE_BOUNDARY_SINCE = date(2026, 7, 30)

#: 정확한 재현이 가능한 최초 날짜. 서비스 시작일과 스냅샷 보유 여부를 함께 본다.
REPLAYABLE_FROM = DAILY_FORTUNE_SERVICE_START


class ContractResolutionError(RuntimeError):
    """그 날짜의 계약을 정확히 해소할 수 없다 — 근사하지 않고 실패한다."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


#: 서비스가 존재하지 않던 날짜.
SERVICE_NOT_YET_LIVE = "SERVICE_NOT_YET_LIVE"
#: 그 날짜의 사전 스냅샷이 없다.
DICT_SNAPSHOT_MISSING = "DICT_SNAPSHOT_MISSING"
#: 날짜로 사전 버전을 특정할 수 없는 구간(경계 장치 도입 이전).
DICT_VERSION_NOT_DATE_ADDRESSABLE = "DICT_VERSION_NOT_DATE_ADDRESSABLE"


@dataclass(frozen=True)
class DayContracts:
    """그 날짜에 실제로 적용된 계약 묶음."""

    fortune_date: date
    active_dict_version: str
    content_version: str
    event_selection_contract: str
    board_rebalance_version: str
    #: 정확 재현 가능 여부. False 면 `PARTIAL` 이며 C10 history 로 쓸 수 없다.
    exactly_replayable: bool
    #: 재현이 불가능한 이유(가능하면 빈 문자열).
    resolution_note: str = ""


def replay_blocker(target_date: date) -> str:
    """그 날짜를 정확히 재현할 수 없는 이유. 가능하면 빈 문자열.

    Args:
        target_date: 대상 날짜.

    Returns:
        차단 코드 또는 "".
    """
    if target_date < DAILY_FORTUNE_SERVICE_START:
        return SERVICE_NOT_YET_LIVE
    if target_date < DICT_DATE_BOUNDARY_SINCE:
        # 경계 장치 이전에는 사전을 제자리에서 교체했다. `active_dict_version()` 은
        # 이 구간 전체에 `PREVIOUS_DICT_VERSION` 을 돌려주지만, 그것이 그 날 실제로
        # 살아 있던 버전이라는 보장이 없다.
        return DICT_VERSION_NOT_DATE_ADDRESSABLE
    if load_snapshot(active_dict_version(target_date)) is None:
        return DICT_SNAPSHOT_MISSING
    return ""


def resolve_day_contracts(target_date: date, *, strict: bool = True) -> DayContracts:
    """그 날짜의 계약을 해소한다.

    Args:
        target_date: 대상 날짜.
        strict: True 면 정확 재현이 불가능할 때 예외를 던진다(기본). False 면
            `exactly_replayable=False` 로 표시해 돌려준다 — 감사·진단용이며
            **C10 history 로 쓸 수 없다**.

    Returns:
        해소된 계약.

    Raises:
        ContractResolutionError: `strict` 이고 정확 재현이 불가능할 때.
    """
    blocker = replay_blocker(target_date)
    if blocker and strict:
        raise ContractResolutionError(
            blocker,
            f"{target_date.isoformat()} 의 라이브 계약을 정확히 해소할 수 없다. "
            "현재 코드로 근사해 재현본이라고 부르지 않는다.",
        )
    dict_version = active_dict_version(target_date)
    return DayContracts(
        fortune_date=target_date,
        active_dict_version=dict_version,
        content_version=(
            f"{ENGINE_VERSION}|{dict_version}|{PROMPT_VERSION}"
            f"|{NARRATIVE_ROTATION_VERSION}"
        ),
        event_selection_contract=EVENT_SELECTION_COMPAT_SALT,
        board_rebalance_version=SELECTOR_VERSION,
        exactly_replayable=not blocker,
        resolution_note=blocker,
    )


def earliest_exact_replay_date() -> date:
    """정확 재현이 가능한 최초 날짜 — 백필·전환 계획의 하한."""
    return max(REPLAYABLE_FROM, DICT_DATE_BOUNDARY_SINCE)
