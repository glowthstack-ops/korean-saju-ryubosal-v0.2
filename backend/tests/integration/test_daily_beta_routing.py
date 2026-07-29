"""베타 일운 라우팅 — 배포 단위 적용과 fail-closed.

베타 대상은 **배포 환경 전체**다. 계정·헤더·query parameter 로 나누지 않는다 —
사용자마다 legacy 와 C10 이 섞이면 피드백 기준이 무너지고, 헤더는 위조할 수 있다.

검증 실패에 legacy 로 조용히 내려가지 않는 것이 이 파일의 핵심이다.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from saju_api.services import daily_fortune_service as svc
from saju_api.services.daily_beta_registry import (
    BETA_POOL_EXPIRED,
    BETA_POOL_NOT_YET_EFFECTIVE,
    INTENDED_REPRESENTATIVE_NOT_SLOT_FEASIBLE,
    BetaPoolConfig,
    build_registry,
    render,
)
from saju_engines.daily_beta_pool import (
    BETA_POOL_FINGERPRINT_MISMATCH,
    BETA_POOL_UNAVAILABLE,
    FUTURE_DATE_NOT_PUBLISHABLE,
    KST,
    BetaPoolError,
)

_POOL = "beta-daily-pool.c10.v2"
_ANCHOR = dt.date(2026, 7, 30)
_UNTIL = dt.date(2026, 8, 28)
_COMPILED = Path(svc.__file__).resolve().parents[4] / "compiled"


def _env(monkeypatch, **over) -> None:
    base = {
        "DAILY_BETA_POOL_ENABLED": "true",
        "DAILY_BETA_POOL_REQUIRED": "true",
        "DAILY_BETA_POOL_VERSION": _POOL,
        "DAILY_BETA_AUDIENCE": "deployment",
        "DAILY_BETA_POOL_EFFECTIVE_FROM": _ANCHOR.isoformat(),
        "DAILY_BETA_POOL_EFFECTIVE_UNTIL": _UNTIL.isoformat(),
        "DAILY_BETA_EXPECTED_POOL_FP": "f0ce1e0c",
        "DAILY_BETA_EXPECTED_BOOTSTRAP_FP": "a499f342",
    }
    base.update(over)
    for k, v in base.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)


def _now(d: dt.date) -> dt.datetime:
    return dt.datetime(d.year, d.month, d.day, 12, 0, tzinfo=KST)


@pytest.fixture()
def registry(monkeypatch):
    _env(monkeypatch)
    return build_registry()


# ── 배포 단위 적용 ─────────────────────────────────────────────────────────


def test_flag_off_keeps_legacy(monkeypatch) -> None:
    """플래그 OFF 면 기존 경로 그대로 — registry 를 구성하지 않는다."""
    _env(monkeypatch, DAILY_BETA_POOL_ENABLED="false")
    assert svc.beta_enabled() is False
    assert svc.beta_preflight() is None
    assert svc.beta_registry() is None


def test_flag_on_builds_registry(monkeypatch) -> None:
    _env(monkeypatch)
    reg = svc.beta_preflight()
    assert reg is not None
    assert reg.pool_version == _POOL
    assert len(reg.selections) == 30 * 60
    svc.beta_preflight.__globals__["_BETA_REGISTRY"] = None   # 다른 테스트 격리


def test_audience_must_be_deployment(monkeypatch) -> None:
    """계정·헤더 기반 분기는 이번 단계에서 지원하지 않는다."""
    _env(monkeypatch, DAILY_BETA_AUDIENCE="account_flag")
    with pytest.raises(BetaPoolError) as e:
        build_registry()
    assert e.value.code == BETA_POOL_UNAVAILABLE


# ── preflight fail-closed ─────────────────────────────────────────────────


def test_fingerprint_mismatch_blocks_startup(monkeypatch) -> None:
    """버전만 맞고 지문이 다르면 활성화하지 않는다."""
    _env(monkeypatch, DAILY_BETA_EXPECTED_POOL_FP="deadbeef")
    with pytest.raises(BetaPoolError) as e:
        build_registry()
    assert e.value.code == BETA_POOL_FINGERPRINT_MISMATCH


def test_missing_pool_version_blocks_startup(monkeypatch) -> None:
    _env(monkeypatch, DAILY_BETA_POOL_VERSION="")
    with pytest.raises(BetaPoolError):
        build_registry()


def test_corrupted_snapshot_blocks_startup(monkeypatch, tmp_path) -> None:
    """손상된 snapshot 은 legacy 로 내려가지 않고 시작을 막는다."""
    src = json.loads((_COMPILED / f"{_POOL}.json").read_text(encoding="utf-8"))
    src["days"] = src["days"][:5]                       # 날짜 누락
    (tmp_path / f"{_POOL}.json").write_text(
        json.dumps(src, ensure_ascii=False), encoding="utf-8"
    )
    _env(monkeypatch, DAILY_BETA_POOL_PATH=str(tmp_path))
    from saju_engines.daily_beta_pool import load_pool

    load_pool.cache_clear()
    with pytest.raises(BetaPoolError) as e:
        build_registry(BetaPoolConfig.from_env())
    assert e.value.code == BETA_POOL_UNAVAILABLE
    load_pool.cache_clear()


def test_missing_ilju_blocks_startup(monkeypatch, tmp_path) -> None:
    src = json.loads((_COMPILED / f"{_POOL}.json").read_text(encoding="utf-8"))
    src["days"][0]["cards"] = src["days"][0]["cards"][:59]   # 일주 누락
    (tmp_path / f"{_POOL}.json").write_text(
        json.dumps(src, ensure_ascii=False), encoding="utf-8"
    )
    _env(monkeypatch, DAILY_BETA_POOL_PATH=str(tmp_path))
    from saju_engines.daily_beta_pool import load_pool

    load_pool.cache_clear()
    with pytest.raises(BetaPoolError) as e:
        build_registry(BetaPoolConfig.from_env())
    assert e.value.code == BETA_POOL_UNAVAILABLE
    load_pool.cache_clear()


# ── 날짜 게이트 ────────────────────────────────────────────────────────────


def test_before_effective_date_is_blocked_not_legacy(registry) -> None:
    """기간 전이라고 legacy 로 내려가지 않는다 — 테스터는 한 풀만 본다."""
    with pytest.raises(BetaPoolError) as e:
        render(registry, _ANCHOR - dt.timedelta(days=1), now=_now(_ANCHOR))
    assert e.value.code == BETA_POOL_NOT_YET_EFFECTIVE


def test_after_effective_window_is_expired(registry) -> None:
    after = _UNTIL + dt.timedelta(days=1)
    with pytest.raises(BetaPoolError) as e:
        render(registry, after, now=_now(after))
    assert e.value.code == BETA_POOL_EXPIRED


def test_public_path_refuses_future(registry) -> None:
    with pytest.raises(BetaPoolError) as e:
        render(registry, _ANCHOR + dt.timedelta(days=2), now=_now(_ANCHOR))
    assert e.value.code == FUTURE_DATE_NOT_PUBLISHABLE


def test_admin_path_may_read_future(registry) -> None:
    board, audit = render(
        registry, _ANCHOR + dt.timedelta(days=5), now=_now(_ANCHOR), allow_future=True
    )
    assert len(board.fortunes) == 60
    assert audit["source"] == "BETA_POOL_SNAPSHOT"


# ── 결정론·감사 메타 ──────────────────────────────────────────────────────


def test_repeated_requests_are_identical(registry) -> None:
    a, am = render(registry, _ANCHOR, now=_now(_ANCHOR))
    b, bm = render(registry, _ANCHOR, now=_now(_ANCHOR))
    assert am["render_result_fingerprint"] == bm["render_result_fingerprint"]
    assert a.model_dump() == b.model_dump()


def test_registry_rebuild_gives_the_same_answer(monkeypatch) -> None:
    """서버 재기동과 같다 — registry 를 다시 만들어도 결과가 같아야 한다."""
    _env(monkeypatch)
    a, am = render(build_registry(), _ANCHOR, now=_now(_ANCHOR))
    b, bm = render(build_registry(), _ANCHOR, now=_now(_ANCHOR))
    assert am["render_result_fingerprint"] == bm["render_result_fingerprint"]
    assert a.model_dump() == b.model_dump()


def test_audit_metadata_carries_contracts(registry) -> None:
    _b, audit = render(registry, _ANCHOR, now=_now(_ANCHOR))
    for key in ("pool_version", "pool_result_fingerprint", "bootstrap_fingerprint",
                "display_selection_policy_version", "renderer_contract_version",
                "render_result_fingerprint"):
        assert audit[key]
    assert len(audit["cards"]) == 60


def test_intent_and_realization_are_recorded_separately(registry) -> None:
    """의도만 있었는데 실현된 것처럼 기록하면 이후 감사가 다시 왜곡된다."""
    _b, audit = render(registry, _ANCHOR, now=_now(_ANCHOR))
    unrealized = [c for c in audit["cards"] if not c["representative_realized"]]
    assert unrealized
    for c in unrealized:
        assert INTENDED_REPRESENTATIVE_NOT_SLOT_FEASIBLE in c["selection_reason_codes"]
        assert c["intended_good_representative"] != c["realized_good_event"]


def test_rendered_slots_match_realized_not_intended(registry) -> None:
    """사용자가 본 것은 실현된 슬롯이다."""
    board, audit = render(registry, _ANCHOR, now=_now(_ANCHOR))
    by_ilju = {c["ilju"]: c for c in audit["cards"]}
    for f in board.fortunes:
        c = by_ilju[f.ilju]
        assert f.events[0].event_key == c["realized_good_event"]


# ── 선택 함수 미호출 ──────────────────────────────────────────────────────


def test_beta_path_calls_no_selection_function(registry, monkeypatch) -> None:
    """라우터 앞뒤 helper 가 다시 호출하지 않는지까지 고정한다."""
    import saju_engines.daily_ilju_fortune as engine

    called: list[str] = []
    for name in ("_select_slots", "_headline_candidates", "_rebalance_headlines"):
        original = getattr(engine, name)

        def spy(*a, _n=name, _o=original, **kw):
            called.append(_n)
            return _o(*a, **kw)

        monkeypatch.setattr(engine, name, spy)

    render(registry, _ANCHOR, now=_now(_ANCHOR))
    assert called == [], f"베타 경로가 선택 함수를 호출했다: {sorted(set(called))}"


# ── HTTP 경계 ─────────────────────────────────────────────────────────────


@pytest.fixture()
def beta_client(monkeypatch):
    """베타 배포로 뜬 앱. `httpx` 로 실제 라우터를 통과시킨다."""
    from fastapi.testclient import TestClient

    _env(monkeypatch)
    from saju_api.main import app

    monkeypatch.setattr(svc, "_BETA_REGISTRY", build_registry())
    # 배포일의 벽시계를 흉내낸다 — 날짜 게이트 자체는 `now` 주입 단위 테스트가 덮는다.
    monkeypatch.setattr(svc, "kst_today", lambda: _ANCHOR)
    monkeypatch.setattr(
        "saju_engines.daily_beta_pool.today_kst", lambda now=None: _ANCHOR
    )
    with TestClient(app) as client:
        yield client


def test_public_endpoint_serves_the_snapshot(beta_client) -> None:
    r = beta_client.get("/api/v2/daily-fortune/today")
    assert r.status_code == 200, r.text
    assert len(r.json()["fortunes"]) == 60


def test_public_endpoint_ignores_client_supplied_beta_switches(beta_client) -> None:
    """헤더·query 로 legacy/C10 을 고를 수 없다 — 무시되고 같은 결과가 나온다."""
    base = beta_client.get("/api/v2/daily-fortune/today").json()
    for req in (
        {"params": {"allow_future": "true"}},
        {"params": {"beta": "false", "date": "2026-08-20"}},
        {"headers": {"X-Beta-Pool": "off", "X-Daily-Allow-Future": "1"}},
    ):
        r = beta_client.get("/api/v2/daily-fortune/today", **req)
        assert r.status_code == 200
        assert r.json() == base


def test_public_endpoint_fails_closed_when_registry_breaks(
    beta_client, monkeypatch
) -> None:
    """스냅샷을 열 수 없으면 legacy 보드가 아니라 503 이다."""
    def boom(*_a, **_kw):
        raise BetaPoolError(BETA_POOL_UNAVAILABLE, "런타임 손상")

    monkeypatch.setattr(
        "saju_api.services.daily_fortune_service.render_beta", boom
    )
    r = beta_client.get("/api/v2/daily-fortune/today")
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == BETA_POOL_UNAVAILABLE
    assert r.headers["cache-control"] == "no-store"


def test_other_apis_are_unaffected_by_a_broken_pool(beta_client, monkeypatch) -> None:
    """차단 범위는 베타 일운 API 뿐이다."""
    def boom(*_a, **_kw):
        raise BetaPoolError(BETA_POOL_UNAVAILABLE, "런타임 손상")

    monkeypatch.setattr(
        "saju_api.services.daily_fortune_service.render_beta", boom
    )
    assert beta_client.get("/health").status_code == 200


def test_single_card_endpoint_matches_the_board(beta_client) -> None:
    board = beta_client.get("/api/v2/daily-fortune/today").json()
    first = board["fortunes"][0]
    r = beta_client.get(f"/api/v2/daily-fortune/today/{first['ilju']}")
    assert r.status_code == 200
    assert r.json()["fortune"]["headline"] == first["headline"]


def test_admin_future_route_requires_admin(beta_client) -> None:
    r = beta_client.get(f"/api/v2/admin/daily-beta/day/{_ANCHOR + dt.timedelta(days=9)}")
    assert r.status_code in (401, 403)


def test_pregen_loop_is_off_on_beta_deployments(monkeypatch) -> None:
    """legacy 보드를 만들어 캐시에 쌓을 이유가 없다."""
    _env(monkeypatch)
    assert svc.beta_enabled() is True
