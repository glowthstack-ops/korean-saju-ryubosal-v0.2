"""Shared test fixtures.

운영 자원 격리가 이 파일의 첫 번째 책임이다. DB(`_isolate_test_db`)와 같은 층에
**LLM 실호출**과 **스레드 export 파일**을 둔다 — 둘 다 테스트가 실제로 오염시킨
전적이 있다(2026-08-03).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import psycopg
import pytest

from saju_manse_core.pillars.four_pillars import build_pillar
from saju_manse_core.pillars.gongmang import gongmang_branches
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.pillars import FourPillarsResult

PillarSpec = tuple[Stem, Branch]

_MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


class LiveLLMCallBlocked(RuntimeError):
    """테스트 프로세스에서 LLM 공급자 실호출을 차단했다."""


ProviderCall = Callable[[dict, str, str, int, float], tuple[str, int, int, int]]

#: 차단 전의 진짜 공급자 호출부. `live_llm` 마커가 붙은 테스트만 이걸 되돌린다.
_REAL_PROVIDERS: dict[str, ProviderCall] = {}


def _blocked_provider_call(
    profile: dict, system: str, prompt: str, max_tokens: int, timeout: float,
) -> tuple[str, int, int, int]:
    """네트워크 대신 즉시 실패한다. 응답을 흉내 내지 않는다."""
    raise LiveLLMCallBlocked(
        f"테스트에서 LLM 실호출 차단 — provider={profile.get('provider')} "
        f"model={profile.get('model')} prompt_chars={len(prompt)}"
    )


@pytest.fixture(scope="session", autouse=True)
def _block_live_llm() -> Iterator[None]:
    """`_PROVIDERS` 항목 = 실제 네트워크 경계를 세션 내내 막는다.

    **경계 선택**이 핵심이다. 한 단계 위(`_call_profile`)를 막으면 공급자 스텁을
    `_PROVIDERS` 에 넣어 폴백을 검증하는 기존 테스트가 자기 스텁에 닿지 못한다.
    항목 단위로 막으면 그 테스트의 `setitem` 이 차단을 덮고, 끝나면 차단으로
    되돌아온다.

    **세션 스코프인 이유**도 핵심이다. 일운 교정은 데몬 스레드로 나가므로 함수
    스코프로 막으면 teardown 뒤 깨어난 스레드가 진짜 호출을 낸다.

    `is_available()` 은 건드리지 않는다 — 키 존재 여부는 사실대로 두고 네트워크만
    끊는다. 그래야 가용성 판정 자체를 검증하는 테스트가 거짓을 보지 않는다.
    """
    from saju_api.services import llm_client

    _REAL_PROVIDERS.update(llm_client._PROVIDERS)
    mp = pytest.MonkeyPatch()
    for provider in llm_client._PROVIDERS:
        mp.setitem(llm_client._PROVIDERS, provider, _blocked_provider_call)
    try:
        yield
    finally:
        mp.undo()


@pytest.fixture(autouse=True)
def _allow_live_llm_when_marked(request: pytest.FixtureRequest) -> Iterator[None]:
    """`@pytest.mark.live_llm` 이 붙은 테스트에서만 차단을 푼다(현재 사용처 없음)."""
    if request.node.get_closest_marker("live_llm") is None or not _REAL_PROVIDERS:
        yield
        return
    from saju_api.services import llm_client

    mp = pytest.MonkeyPatch()
    for provider, call in _REAL_PROVIDERS.items():
        mp.setitem(llm_client._PROVIDERS, provider, call)
    try:
        yield
    finally:
        mp.undo()


@pytest.fixture(scope="session", autouse=True)
def _no_background_polish_threads() -> Iterator[None]:
    """lazy 경로의 백그라운드 교정 예약을 끈다.

    라우터가 데몬 스레드를 띄우면 응답 뒤에도 캐시 보드가 비동기로 바뀐다. 실제로
    `test_today_endpoint_and_headers` 의 ETag 재검증은 **실호출이 느려서** 통과하고
    있었다 — 교정이 빨라지면 두 번째 요청의 ETag 가 달라져 깨진다. 예약 배선 자체는
    `test_no_live_llm_in_tests` 가 따로 고정한다.
    """
    from saju_api.services import daily_fortune_polish

    mp = pytest.MonkeyPatch()
    mp.setattr(daily_fortune_polish, "maybe_schedule_polish", lambda *a, **k: False)
    try:
        yield
    finally:
        mp.undo()


@pytest.fixture(scope="session", autouse=True)
def _isolate_threads_export(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    """`오늘의운세.txt` 를 임시 경로로 돌린다.

    공개 라우터에는 날짜 파라미터가 없어 테스트도 **오늘의 진짜 보드**를 만든다.
    그래서 export 의 '게시 기준일 보드일 때만 쓴다' 가드가 통과해 버리고, 운영 파일이
    테스트 산출물로 덮인다(2026-08-03 실측: 교정 PARTIAL 파일이 FAILED 로 교체됨).

    21시 이후 실행에서는 기준일이 익일이라 가드가 막아 주지만, 그 우연에 기대지 않는다
    — 경로 격리가 시각과 무관하게 성립해야 한다.
    """
    from saju_api.services import daily_fortune_export

    mp = pytest.MonkeyPatch()
    mp.setattr(
        daily_fortune_export, "THREADS_EXPORT_PATH",
        tmp_path_factory.mktemp("threads_export") / "오늘의운세.txt",
    )
    try:
        yield
    finally:
        mp.undo()


@pytest.fixture(autouse=True)
def _isolate_risk_state(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """위험 어댑터 suspension·lease 상태를 테스트마다 임시 경로로 돌린다.

    이 경로들은 **운영 상태**다(tombstone ledger는 append-only이고
    `_is_globally_suspended` 가 읽는다). 격리하지 않은 테스트가 실제
    `backend/var/risk_state/` 에 기록해 온 사실이 확인됐다(2026-08-04:
    `conc-a`/`conc-b` 18행 누적). 기능 장애는 없었지만 실제 suspension
    사고를 분석할 때 테스트 기록과 운영 기록을 갈라내야 하는 비용이
    생기고, 실행마다 파일이 달라져 재현성이 깨진다.

    개별 테스트가 자기 fixture 로 다시 monkeypatch 하는 것은 그대로
    동작한다(나중 patch 가 이긴다). 여기서는 **명시적으로 주입하지 않은
    테스트가 운영 경로를 쓰는 일이 없도록** 기본값을 임시 경로로 돌린다.
    """
    try:
        from saju_api.services import risk_validation_lease as lease_mod
        from saju_api.services import token_counter_registry as reg
    except ImportError:  # saju_api 미가용 환경(순수 엔진 테스트) — 무해
        yield
        return

    root = tmp_path_factory.mktemp("risk_state")
    mp = pytest.MonkeyPatch()
    mp.setattr(reg, "_SUSPENSION_FILE", root / "adapter_suspensions.json")
    mp.setattr(reg, "_SUSPENSION_LOCK_FILE", root / "adapter_suspensions.lock")
    mp.setattr(reg, "_SUSPENSION_LEDGER", root / "adapter_suspensions_ledger.jsonl")
    mp.setattr(reg, "_EXPOSURE_DISABLED_MARKER", root / "exposure_disabled.marker")
    mp.setattr(lease_mod, "_STATE_DIR", root)
    try:
        yield
    finally:
        mp.undo()


def _test_dsn(base: str) -> str:
    """운영 DSN의 DB명 뒤에 _test를 붙인 테스트 DSN(쿼리 파라미터 보존)."""
    head, _, tail = base.rpartition("/")
    db = tail.split("?", 1)[0]
    if db.endswith("_test"):
        return base
    suffix = tail[len(db):]
    return f"{head}/{db}_test{suffix}"


@pytest.fixture(scope="session", autouse=True)
def _isolate_test_db() -> Iterator[None]:
    """통합 테스트가 운영 DB를 오염시키지 않도록 전용 테스트 DB로 격리한다.

    SAJU_V2_DATABASE_URL이 있으면 같은 서버의 '<db>_test'로 전환하고(없으면 생성),
    전 마이그레이션을 적용한다. 세션 종료 시 원래 DSN으로 복원. DSN 미설정(DB 없는 단위
    테스트 환경)이면 그대로 둔다.
    """
    base = os.environ.get("SAJU_V2_DATABASE_URL")
    if not base:
        yield
        return
    test = _test_dsn(base)
    name = test.rsplit("/", 1)[-1].split("?", 1)[0]
    admin = base.rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(admin, autocommit=True) as c:
        if not c.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
            c.execute(f'CREATE DATABASE "{name}"')
    with psycopg.connect(test) as c:
        for sql in sorted(_MIGRATIONS.glob("*.sql")):
            c.execute(sql.read_text(encoding="utf-8"))
    os.environ["SAJU_V2_DATABASE_URL"] = test
    try:
        yield
    finally:
        os.environ["SAJU_V2_DATABASE_URL"] = base


@pytest.fixture
def make_pillars() -> Callable[..., FourPillarsResult]:
    """Factory: build a FourPillarsResult from (stem, branch) specs + day master."""

    def _make(
        year: PillarSpec,
        month: PillarSpec,
        day: PillarSpec,
        hour: PillarSpec,
        dm: Stem,
    ) -> FourPillarsResult:
        glist = gongmang_branches(dm, day[1])
        g = set(glist)
        return FourPillarsResult(
            year=build_pillar(dm, year[0], year[1], "year", g),
            month=build_pillar(dm, month[0], month[1], "month", g),
            day=build_pillar(dm, day[0], day[1], "day", g),
            hour=build_pillar(dm, hour[0], hour[1], "hour", g),
            day_master=str(dm),
            gongmang_branches=[str(b) for b in glist],
        )

    return _make
