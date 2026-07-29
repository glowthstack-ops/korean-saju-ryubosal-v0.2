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

from saju_shared_types.daily_fortune import DailyFortuneBoard

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
#: snapshot 이 없거나 손상됐다 — legacy 로 조용히 대체하지 않는다.
BETA_POOL_UNAVAILABLE = "BETA_POOL_UNAVAILABLE"
BETA_POOL_FINGERPRINT_MISMATCH = "BETA_POOL_FINGERPRINT_MISMATCH"
#: 렌더 결과가 snapshot 선택과 다르다.
BETA_POOL_SELECTION_DRIFT = "BETA_POOL_SELECTION_DRIFT"

#: 렌더링 계약 — 문장까지 동결한다. 선택만 고정해서는 테스터가 보는 것이 안 고정된다.
RENDERER_CONTRACT_VERSION = "daily-beta-render.c10.v1"


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


# ── 렌더링 — snapshot 이 선택의 SSOT 다 ───────────────────────────────────


def validate_pool(
    pool_version: str, compiled_dir: Path = _COMPILED
) -> dict[tuple[str, str], dict[str, Any]]:
    """서버 시작 시 1회 전수 검증. 하나라도 실패하면 활성화하지 않는다.

    Returns:
        (date, ilju) → 선택 인덱스.

    Raises:
        BetaPoolError: 구조·계약·불변식 위반.
    """
    from saju_engines.daily_ilju_fortune import load_daily_dicts_for

    try:
        pool = load_pool(pool_version, compiled_dir)
    except BetaPoolError:
        raise
    except Exception as exc:                       # noqa: BLE001 — 손상 파일
        raise BetaPoolError(BETA_POOL_UNAVAILABLE, str(exc)) from exc

    days = pool.get("days") or []
    if len(days) != pool.get("public_days"):
        raise BetaPoolError(
            BETA_POOL_UNAVAILABLE, f"날짜 {len(days)} != {pool.get('public_days')}"
        )
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for day in days:
        cards = day.get("cards") or []
        if len(cards) != 60:
            raise BetaPoolError(
                BETA_POOL_UNAVAILABLE, f"{day['fortune_date']}: 카드 {len(cards)} != 60"
            )
        catalog = load_daily_dicts_for(
            date.fromisoformat(day["fortune_date"])
        ).catalog["events"]
        for c in cards:
            key = (day["fortune_date"], c["ilju"])
            if key in index:
                raise BetaPoolError(BETA_POOL_UNAVAILABLE, f"중복 {key}")
            slots = {
                c["display_good_representative"], c["support_event"], c["caution_event"]
            }
            if len(slots) != 3:
                raise BetaPoolError(BETA_POOL_UNAVAILABLE, f"{key}: 슬롯 중복")
            for event_key in (*slots, c["raw_good_winner"]):
                if event_key not in catalog:
                    raise BetaPoolError(
                        BETA_POOL_UNAVAILABLE, f"{key}: 미지의 사건 {event_key}"
                    )
            if c["final_headline"] not in slots:
                raise BetaPoolError(
                    BETA_POOL_SELECTION_DRIFT, f"{key}: 헤드라인이 표시 사건 밖"
                )
            if not 0 <= c["display_displacement_loss"] <= 7:
                raise BetaPoolError(BETA_POOL_UNAVAILABLE, f"{key}: 손실 예산 초과")
            if c["raw_good_winner"] == c["display_good_representative"] and (
                c["display_displacement_loss"] != 0
            ):
                raise BetaPoolError(BETA_POOL_UNAVAILABLE, f"{key}: 손실 불일치")
            index[key] = c
        if day.get("domain_cap_hard_violation"):
            raise BetaPoolError(
                BETA_POOL_UNAVAILABLE, f"{day['fortune_date']}: 설명되지 않은 domain 초과"
            )
    if len(index) != pool["public_days"] * 60:
        raise BetaPoolError(BETA_POOL_UNAVAILABLE, f"카드 총계 {len(index)}")
    return index


def render_board(
    pool_version: str,
    target_date: date,
    *,
    now: datetime | None = None,
    allow_future: bool = False,
    compiled_dir: Path = _COMPILED,
) -> DailyFortuneBoard:
    """snapshot 의 선택을 그대로 써서 문장만 렌더링한다.

    선택을 다시 하지 않는다 — `compute_board(selection_override=...)` 가
    `_select_slots`·`_headline_candidates`·`_rebalance_headlines` 를 건너뛴다.

    Raises:
        BetaPoolError: 날짜 게이트·구조 위반. **legacy 로 조용히 내려가지 않는다.**
    """
    from saju_engines.daily_ilju_fortune import (
        build_day_context,
        compute_board,
        load_daily_dicts_for,
    )

    day = load_day(
        pool_version, target_date, now=now, allow_future=allow_future,
        compiled_dir=compiled_dir,
    )
    override = {
        c["ilju"]: {
            "good": c["display_good_representative"],
            "support": c["support_event"],
            "caution": c["caution_event"],
            "final_headline": c["final_headline"],
            "band": c["band"],
        }
        for c in day.cards
    }
    board = compute_board(
        build_day_context(target_date), load_daily_dicts_for(target_date),
        selection_override=override,
    )
    # 렌더 결과가 snapshot 선택과 어긋나면 차단한다(조용한 드리프트 금지).
    for f in board.fortunes:
        want = override[f.ilju]
        got = [e.event_key for e in f.events]
        if got != [want["good"], want["caution"], want["support"]]:
            raise BetaPoolError(
                BETA_POOL_SELECTION_DRIFT, f"{target_date} {f.ilju}: 슬롯 불일치 {got}"
            )
        if str(f.headline_event_key) != want["final_headline"]:
            raise BetaPoolError(
                BETA_POOL_SELECTION_DRIFT,
                f"{target_date} {f.ilju}: 헤드라인 {f.headline_event_key}",
            )
    return board


def render_result_fingerprint(board: DailyFortuneBoard) -> str:
    """사용자 가시 결과의 지문 — 같은 카드를 다시 열면 문장까지 같아야 한다."""
    import hashlib

    h = hashlib.sha256()
    for f in board.fortunes:
        h.update(f"{f.ilju}|{f.headline}|{f.lucky_place.name}|{f.love_line or ''}"
                 f"|{f.lotto_phrase or ''}".encode())
        for e in f.events:
            h.update(f"|{e.slot}:{e.event_key}:{e.probability}:{e.phrase}".encode())
        h.update(b"\x1e")
    return h.hexdigest()
