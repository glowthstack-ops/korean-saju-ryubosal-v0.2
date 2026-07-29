"""`beta-daily-pool.*` 조회 — 선생성 snapshot 을 **날짜별로만** 연다.

선생성과 미래 노출은 다른 문제다. snapshot 은 공개 기간 전체를 담지만, 조회는 KST
오늘까지로 막는다. 관리자·감사 경로만 `allow_future=True` 로 넘길 수 있다.

원장·CAS 없이도 동작한다 — 불변 snapshot 이므로 서버를 재기동해도, 캐시가 비어도
같은 파일을 읽으면 같은 결과가 나온다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

_COMPILED = Path(__file__).resolve().parents[3] / "compiled"

#: 한국 표준시. 보드 경계는 KST 자정이다.
KST = timezone(timedelta(hours=9))


class BetaPoolError(RuntimeError):
    """풀 조회 실패 — 코드로 구분한다."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


POOL_NOT_FOUND = "POOL_NOT_FOUND"
DATE_BEFORE_POOL = "DATE_BEFORE_POOL"
DATE_AFTER_POOL = "DATE_AFTER_POOL"
#: 아직 오지 않은 날짜 — 선생성돼 있어도 열지 않는다.
FUTURE_DATE_NOT_PUBLISHABLE = "FUTURE_DATE_NOT_PUBLISHABLE"


@dataclass(frozen=True)
class BetaPoolDay:
    """공개 가능한 하루치 선택 결과."""

    pool_version: str
    fortune_date: date
    active_dict_version: str
    content_version: str
    display_selection_policy_version: str
    pool_result_fingerprint: str
    cards: list[dict[str, Any]]


@lru_cache(maxsize=4)
def load_pool(pool_version: str, compiled_dir: Path = _COMPILED) -> dict[str, Any]:
    """snapshot 원본. 없으면 `POOL_NOT_FOUND`."""
    path = compiled_dir / f"{pool_version}.json"
    if not path.exists():
        raise BetaPoolError(POOL_NOT_FOUND, str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def today_kst(now: datetime | None = None) -> date:
    """KST 기준 오늘. 테스트가 시각을 주입할 수 있게 인자로 받는다."""
    return (now or datetime.now(KST)).astimezone(KST).date()


def load_day(
    pool_version: str,
    target_date: date,
    *,
    now: datetime | None = None,
    allow_future: bool = False,
    compiled_dir: Path = _COMPILED,
) -> BetaPoolDay:
    """그 날짜의 보드를 연다.

    Args:
        pool_version: 풀 버전(`beta-daily-pool.c10.v1`).
        target_date: 조회할 날짜.
        now: 현재 시각(미주입 시 실제 시각). KST 로 환산해 오늘을 정한다.
        allow_future: 관리자·감사 전용. 일반 경로에서는 절대 True 로 넘기지 않는다.
        compiled_dir: snapshot 위치.

    Returns:
        하루치 선택 결과.

    Raises:
        BetaPoolError: 풀이 없거나, 기간 밖이거나, 아직 오지 않은 날짜일 때.
    """
    pool = load_pool(pool_version, compiled_dir)
    start = date.fromisoformat(pool["public_start"])
    end = date.fromisoformat(pool["public_end"])
    if target_date < start:
        raise BetaPoolError(DATE_BEFORE_POOL, f"{target_date} < {start}")
    if target_date > end:
        raise BetaPoolError(DATE_AFTER_POOL, f"{target_date} > {end}")
    if not allow_future and target_date > today_kst(now):
        # 선생성돼 있어도 열지 않는다 — 선생성과 미래 노출은 다른 문제다.
        raise BetaPoolError(
            FUTURE_DATE_NOT_PUBLISHABLE,
            f"{target_date} 는 KST 오늘({today_kst(now)}) 이후다",
        )
    for day in pool["days"]:
        if day["fortune_date"] == target_date.isoformat():
            return BetaPoolDay(
                pool_version=pool["pool_version"],
                fortune_date=target_date,
                active_dict_version=day["active_dict_version"],
                content_version=day["content_version"],
                display_selection_policy_version=pool[
                    "display_selection_policy_version"
                ],
                pool_result_fingerprint=pool["pool_result_fingerprint"],
                cards=day["cards"],
            )
    raise BetaPoolError(DATE_AFTER_POOL, f"{target_date} 가 snapshot 에 없다")


def pool_metadata(pool_version: str, compiled_dir: Path = _COMPILED) -> dict[str, Any]:
    """계약·지문만 — 카드는 담지 않는다(감사·표시용)."""
    pool = load_pool(pool_version, compiled_dir)
    return {k: v for k, v in pool.items() if k != "days"}
