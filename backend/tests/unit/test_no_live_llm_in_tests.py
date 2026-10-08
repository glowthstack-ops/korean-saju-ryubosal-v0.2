"""테스트 프로세스의 과금·운영오염 차단 회귀 (2026-08-03).

관측된 사고다. `test_daily_fortune_api` 가 공개 라우터를 부르면서 `llm_client` 를
스텁하지 않았고, 공개 라우터에는 날짜 파라미터가 없어 **오늘의 진짜 보드**가
생성됐다. 보드는 InMemory 캐시라 언제나 RAW → 교정 예약 → 저장소 루트 `.env` 의
키로 `is_available()` 이 True → 데몬 스레드에서 실제 Gemini 호출.

    콘솔 24건 / 일   ←  의도한 2건 (서버 기동 보충 + 23:50 선생성)
    llm_usage 1건    ←  테스트 프로세스에는 사용량 sink 가 없어 기록조차 안 남았다

같은 스레드가 `write_threads_export` 까지 불러 운영 파일을 덮었다. 여기서는 그
두 경로가 다시 열리지 않는지만 고정한다 — 호출 횟수를 세지 않고 **경로가 닫혀
있는지**를 본다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from saju_api.deps import get_daily_fortune_cache_or_beta
from saju_api.main import app
from saju_api.services import (
    daily_fortune_export,
    daily_fortune_polish,
    daily_fortune_service,
    llm_client,
)
from saju_engines.daily_fortune_cache import InMemoryDailyFortuneCache
from saju_shared_types.daily_fortune import content_version_for

_REPO_EXPORT = daily_fortune_export._REPO_ROOT / "오늘의운세.txt"

#: conftest 는 pytest 가 최상위 `conftest` 로 로드한다. `tests.conftest` 로 다시
#: import 하면 **같은 이름의 다른 클래스**가 생겨 isinstance 가 어긋난다. 그래서
#: 클래스 객체가 아니라 이름으로 확인한다.
_BLOCK_EXC_NAME = "LiveLLMCallBlocked"


@pytest.fixture()
def client():
    cache = InMemoryDailyFortuneCache()
    app.dependency_overrides[get_daily_fortune_cache_or_beta] = lambda: cache
    try:
        yield TestClient(app), cache
    finally:
        app.dependency_overrides.pop(get_daily_fortune_cache_or_beta, None)


# ── 공급자 호출부 차단 ───────────────────────────────────────────────────


def test_provider_call_is_blocked_at_the_single_funnel() -> None:
    """`_call_profile` 이 gemini·openai 양쪽의 유일한 통로다."""
    with pytest.raises(RuntimeError) as exc:
        llm_client._call_profile(
            {"provider": "gemini", "model": "x"}, "sys", "prompt", 100, 1.0
        )
    assert type(exc.value).__name__ == _BLOCK_EXC_NAME


def test_generate_reading_never_returns_text() -> None:
    """공개 진입점이 본문을 만들어내지 못한다.

    사유는 실행 순서에 따라 '차단' 일 수도 '키 없음' 일 수도 있다 — 여기서 사유를
    단정하지 않는다. 차단 자체는 위 두 회귀가 환경과 무관하게 고정한다.
    """
    with pytest.raises(RuntimeError):
        llm_client.generate_reading("본문", call_type="chat_single")


def test_availability_is_not_faked() -> None:
    """네트워크만 끊고 키 존재 판정은 사실대로 둔다 — 가용성 테스트가 거짓을 보면 안 된다."""
    assert isinstance(llm_client.is_available(), bool)


# ── 일운 경로 end-to-end ─────────────────────────────────────────────────


def test_every_provider_entry_is_blocked() -> None:
    """공급자 표의 **모든** 항목이 차단 함수다 — 새 공급자가 추가돼도 이 회귀가 잡는다."""
    assert llm_client._PROVIDERS
    for provider, call in llm_client._PROVIDERS.items():
        assert call.__name__ == "_blocked_provider_call", provider


def test_daily_polish_path_cannot_produce_polished_text(client) -> None:
    """교정 경로 전체가 실패로 끝난다 — 스레드가 아니라 동기 호출로 확인한다.

    **실패 사유 문자열로 단정하지 않는다.** 앞선 테스트가 키 환경변수를 지우면 차단에
    닿기 전에 '키 없음' 으로 끝나 사유가 달라진다(전체 스위트에서 실측). 차단 자체는
    `test_every_provider_entry_is_blocked` 가 환경과 무관하게 고정하고, 여기서는
    **교정된 문장이 나오지 않는다**는 결과만 본다.
    """
    _, cache = client
    today = daily_fortune_service.kst_today()
    board = daily_fortune_polish.get_board(cache, today)
    assert board.polish_status == "RAW"

    audit = daily_fortune_polish.polish_board(cache, today)
    assert audit is not None
    assert audit["accepted"] == 0

    after = cache.load_board(today, content_version_for(today))  # 날짜별 계약(전역 상수 아님)
    assert after is not None
    assert after.polish_status == "FAILED"
    assert all(not f.polished for f in after.fortunes)


def test_router_still_schedules_polish_for_a_raw_board(client, monkeypatch) -> None:
    """백그라운드 예약을 세션 전체에서 껐으므로 **배선 자체는 여기서 고정**한다."""
    scheduled: list[str] = []
    monkeypatch.setattr(
        daily_fortune_polish, "maybe_schedule_polish",
        lambda cache, d: scheduled.append(d.isoformat()) or True,
    )
    http, _ = client
    assert http.get("/api/v2/daily-fortune/today").status_code == 200
    assert scheduled == [daily_fortune_service.kst_today().isoformat()]


def test_today_route_does_not_touch_the_repo_export_file(client) -> None:
    """라우터 호출이 운영 `오늘의운세.txt` 를 건드리지 않는다."""
    before = _REPO_EXPORT.stat().st_mtime_ns if _REPO_EXPORT.exists() else None
    http, _ = client
    assert http.get("/api/v2/daily-fortune/today").status_code == 200
    after = _REPO_EXPORT.stat().st_mtime_ns if _REPO_EXPORT.exists() else None
    assert after == before


# ── export 경로 격리 ─────────────────────────────────────────────────────


def test_threads_export_path_is_isolated_from_the_repo_file() -> None:
    assert daily_fortune_export.THREADS_EXPORT_PATH != _REPO_EXPORT


def test_default_export_path_is_resolved_at_call_time(tmp_path) -> None:
    """시그니처 기본값이 아니라 호출 시점의 상수를 읽는다 — 격리가 성립하는 근거다."""
    cache = InMemoryDailyFortuneCache()
    today = daily_fortune_service.kst_today()
    board = daily_fortune_polish.get_board(cache, today)

    target = tmp_path / "격리.txt"
    monkey = pytest.MonkeyPatch()
    monkey.setattr(daily_fortune_export, "THREADS_EXPORT_PATH", target)
    try:
        assert (
            daily_fortune_export.write_threads_export(board, publish_date=today) is True
        )
    finally:
        monkey.undo()
    assert target.exists()
