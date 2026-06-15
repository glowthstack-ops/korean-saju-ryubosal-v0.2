"""Shared test fixtures."""

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
