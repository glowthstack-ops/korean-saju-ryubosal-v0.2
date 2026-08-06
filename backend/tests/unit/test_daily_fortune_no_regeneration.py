"""이미 만든 보드를 다시 만들지 않는다 — 재생성 금지 불변식 (2026-08-06).

llm_usage 실측이 근거다. `daily_fortune_polish` 25회 중 10회(40%, $0.18)가 **이미
만들어 둔 날짜를 다시 만든 것**이었고, KST 로 보면 매일 06시 전후 기동 흔적으로
남아 있었다(07-24·07-25·07-27·07-28·07-30·08-04·08-05).

원인은 판정 로직이 아니라 **판정 근거의 수명**이었다. 멱등은 캐시 하나에 걸려 있는데
Redis 에 볼륨이 없어 컨테이너 recreate 마다 기록이 사라졌다. 그래서 고친 것이 둘이다.

    docker-compose.yml   redis 명명 볼륨 — "이미 만들었다"는 기록이 재기동을 넘긴다
    main.py              기동 보충 대상을 게시 기준일 **하나**로 축소

여기서는 코드 쪽 불변식만 고정한다(볼륨은 인프라라 단위 테스트 범위 밖이다).

원칙 1(개발 테스트에서 LLM 미사용)에 따라 실호출은 하지 않는다. 공급자는 conftest 가
세션 내내 막고 있고, 이 파일은 그 위층(`generate_reading`)을 세는 스텁으로 갈음한다
— **호출 횟수**가 곧 검증 대상이라 응답 내용은 필요 없다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from saju_api.services import daily_fortune_polish
from saju_api.services.daily_fortune_export import (
    THREADS_PUBLISH_HOUR,
    threads_publish_date,
)
from saju_engines.daily_fortune_cache import InMemoryDailyFortuneCache
from saju_shared_types.daily_fortune import CONTENT_VERSION

_KST = ZoneInfo("Asia/Seoul")

#: 엔진이 결정론이므로 어떤 날짜든 결과가 고정된다 — 오늘에 의존하지 않는다.
_TARGET = date(2026, 8, 7)


class _CountingLLM:
    """`generate_reading` 대역 — 호출 횟수만 센다. 응답은 전량 거부돼도 무방하다.

    빈 문자열을 돌려주면 `validate_and_apply` 가 한 줄도 채택하지 못해 보드는
    FAILED 가 된다. 그 상태에서도 **재호출이 없어야** 한다는 것이 이 파일의 요지 중
    하나라, 일부러 성공 응답을 흉내 내지 않는다.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, payload: str, **kwargs: object) -> str:
        self.calls.append(str(kwargs.get("ref_id")))
        return ""


@pytest.fixture()
def llm(monkeypatch: pytest.MonkeyPatch) -> _CountingLLM:
    """LLM 을 세는 스텁으로 갈음하고 가용 판정은 True 로 고정한다.

    `is_available()` 을 고정하는 이유는, 키 유무에 따라 테스트가 조용히 통과해
    (호출이 애초에 일어나지 않아) 회귀를 놓치는 것을 막기 위해서다.
    """
    counter = _CountingLLM()
    monkeypatch.setattr(daily_fortune_polish.llm_client, "generate_reading", counter)
    monkeypatch.setattr(daily_fortune_polish.llm_client, "is_available", lambda: True)
    # 프로세스 전역 1회 예약 기록 — 테스트 간 누수를 막는다.
    monkeypatch.setattr(daily_fortune_polish, "_attempted", set())
    return counter


# ── 재생성 금지 ─────────────────────────────────────────────────────────


def test_second_preparation_of_the_same_date_calls_no_llm(
    llm: _CountingLLM,
) -> None:
    """같은 날짜를 두 번 준비해도 LLM 은 한 번만 불린다 — 이 파일의 본론."""
    cache = InMemoryDailyFortuneCache()

    daily_fortune_polish.generate_and_polish(cache, _TARGET)
    assert llm.calls == [_TARGET.isoformat()]

    daily_fortune_polish.generate_and_polish(cache, _TARGET)
    assert llm.calls == [_TARGET.isoformat()], "이미 만든 날짜를 다시 교정했다"


def test_a_failed_board_is_not_retried_automatically(llm: _CountingLLM) -> None:
    """교정이 실패한 보드도 자동 재호출 대상이 아니다(운영자 수동 경로 전용).

    스텁이 빈 응답을 주므로 첫 호출 뒤 보드는 FAILED 다. RAW 가 아니게 되었으므로
    이후 준비는 LLM 에 닿지 않아야 한다 — 실패를 매 기동마다 재시도하면 그것이 곧
    무한 낭비다.
    """
    cache = InMemoryDailyFortuneCache()
    daily_fortune_polish.generate_and_polish(cache, _TARGET)

    board = cache.load_board(_TARGET, CONTENT_VERSION)
    assert board is not None and board.polish_status == "FAILED"

    daily_fortune_polish.generate_and_polish(cache, _TARGET)
    assert len(llm.calls) == 1


def test_a_lost_cache_is_the_only_thing_that_reopens_the_call(
    llm: _CountingLLM,
) -> None:
    """캐시를 잃으면 다시 부른다 — 그래서 캐시 수명이 곧 절약의 상한이다.

    이 동작 자체는 옳다(기록이 없으면 정말 없는 것이다). 고정해 두는 이유는 절약이
    코드가 아니라 **Redis 볼륨**에 달려 있음을 회귀로 못박기 위해서다.
    """
    cache = InMemoryDailyFortuneCache()
    daily_fortune_polish.generate_and_polish(cache, _TARGET)

    daily_fortune_polish.generate_and_polish(InMemoryDailyFortuneCache(), _TARGET)
    assert len(llm.calls) == 2


# ── 기동 보충 대상 ───────────────────────────────────────────────────────


@pytest.mark.parametrize("hour", [0, 6, 12, 20, 21, 23])
def test_startup_has_exactly_one_target(hour: int) -> None:
    """어느 시각에 기동하든 보충 대상은 게시 기준일 하나뿐이다.

    기동 보충이 오늘과 익일을 둘 다 부르던 때에는 21시 이후 재기동이 교정을 최대
    2회 냈다. 그중 오늘 몫은 이미 전날 21시에 만들어 내보낸 것의 재생성이었다.
    """
    now = datetime(2026, 8, 6, hour, 30, tzinfo=_KST)
    publish = threads_publish_date(now)

    expected = now.date() + timedelta(days=1 if hour >= THREADS_PUBLISH_HOUR else 0)
    assert publish == expected


def test_after_the_publish_hour_today_is_not_a_target() -> None:
    """21시 이후 기동에서 오늘 보드는 보충 대상이 아니다 — 남은 수명이 3시간 미만이고,
    교정본은 이미 전날 스레드로 나갔다."""
    now = datetime(2026, 8, 6, 21, 30, tzinfo=_KST)
    assert threads_publish_date(now) != now.date()


# ── 엔진 결정론(원칙 1: 판단 근거는 엔진 출력) ────────────────────────────


def test_engine_output_is_deterministic_so_regeneration_buys_nothing() -> None:
    """같은 날짜를 다시 생성해도 엔진 원문은 한 글자도 다르지 않다.

    재생성이 무가치하다는 근거를 LLM 없이 엔진 출력만으로 고정한다. 달라지는 것은
    교정문뿐이고, 그건 매번 새 비용이면서 사용자에게는 같은 하루다.
    """
    from saju_api.services.daily_fortune_service import _generate

    assert _generate(_TARGET).model_dump_json() == _generate(_TARGET).model_dump_json()
