"""D1 — OA-10b 가 공용 builder 를 거치는지, 공개 계약이 그대로인지.

계산 경로와 저장 경로의 분리가 다시 흐려지지 않도록 두 층으로 나눠 센다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import audit_rolling_window as OA  # noqa: E402
from saju_engines.daily_rolling_audit_public_adapter import (  # noqa: E402
    OA10B_PUBLIC_DAILY_FIELDS_V1,
    OA10B_PUBLIC_EPISODE_FIELDS_V1,
    OA10BPublicProjectionError,
    project_to_oa10b_public_v1,
)

_ANCHORS = 3          # 회귀용 짧은 구간


@pytest.fixture()
def counters(monkeypatch) -> dict[str, int]:
    """공식 경로가 어느 구현을 몇 번 부르는지 센다."""
    import legacy_oa10b_runner as LEGACY

    seen = dict.fromkeys(
        ("legacy", "wrapper", "schedule", "aggregate", "projection", "writer"), 0
    )

    def spy_on(module, name, key):
        original = getattr(module, name)

        def spy(*a, **kw):
            seen[key] += 1
            return original(*a, **kw)

        monkeypatch.setattr(module, name, spy)

    spy_on(LEGACY, "build_schedule_observed", "legacy")
    spy_on(OA, "build_schedule", "wrapper")
    spy_on(OA, "build_rolling_audit_schedule", "schedule")
    spy_on(OA, "build_rolling_audit_aggregates", "aggregate")
    spy_on(OA, "project_to_oa10b_public_v1", "projection")
    spy_on(OA, "write_audit_output", "writer")
    return seen


def test_run_uses_shared_builders_and_writes_nothing(counters) -> None:
    """`run()` 은 계산만 한다 — 저장은 호출부 몫이다."""
    OA.run(anchor_days=_ANCHORS)
    assert counters == {
        "legacy": 0, "wrapper": 0,
        "schedule": 1, "aggregate": 1, "projection": 1,
        "writer": 0,
    }


def test_run_does_not_touch_the_filesystem(counters, tmp_path) -> None:
    result, _claim = OA.run(anchor_days=_ANCHORS)
    assert result["summary"]["total_anchors"] == _ANCHORS
    assert counters["writer"] == 0
    assert list(tmp_path.iterdir()) == []


# ── 공개 계약 ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def public() -> tuple[list[dict], list[dict]]:
    result, _claim = OA.run(anchor_days=_ANCHORS)
    return result["daily"], result["episodes"]


def test_daily_keys_and_order_are_frozen(public) -> None:
    daily, _episodes = public
    for row in daily:
        assert tuple(row) == OA10B_PUBLIC_DAILY_FIELDS_V1


def test_episode_keys_and_order_are_frozen(public) -> None:
    _daily, episodes = public
    for row in episodes:
        assert tuple(row) == OA10B_PUBLIC_EPISODE_FIELDS_V1


def test_internal_expansion_fields_are_not_exposed(public) -> None:
    """확장 필드는 지문 대상이라 내부에 남지만 공개되지 않는다."""
    daily, episodes = public
    for hidden in ("key_min", "family_min", "domain_min", "qualifying_ilju_count"):
        assert all(hidden not in row for row in daily)
    for hidden in ("episode_id", "minimum_key_p10_dates", "worst_count_below_15"):
        assert all(hidden not in row for row in episodes)


def test_internal_builder_still_carries_the_expansion_fields() -> None:
    """공개에서 감춘다고 내부에서 없애면 지문이 깨진다."""
    import saju_engines.daily_ilju_fortune as M
    from saju_engines.daily_rolling_audit_aggregate import (
        build_rolling_audit_aggregates,
        derive_diagnostic_contract,
    )
    from saju_engines.daily_schedule_runner import build_rolling_audit_schedule

    tax = json.loads(
        (Path(__file__).resolve().parents[2] / "dictionaries" / "daily_fortune"
         / "daily_event_taxonomy.json").read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    steps, _s = build_rolling_audit_schedule(
        days=OA.WARMUP_DAYS + OA.WINDOW + 1, policy=OA.C10_POLICY,
        board_policy=OA._BOARD, family_of=family_of,
    )
    rows = [dict(r) for st in steps for r in st.rows]
    events = M.load_daily_dicts().catalog["events"]
    agg = build_rolling_audit_aggregates(
        rows, family_of, {k: e["domain"] for k, e in events.items()},
        derive_diagnostic_contract(anchor_days=1),
    )
    for field in ("key_min", "family_min", "domain_min", "qualifying_ilju_count"):
        assert field in agg["anchors"][0]


def test_projection_fails_closed_on_missing_fields() -> None:
    """shared builder 가 필드를 없애면 공개 출력이 조용히 축소되면 안 된다."""
    with pytest.raises(OA10BPublicProjectionError):
        project_to_oa10b_public_v1(
            {"anchors": [{"anchor_date": "2026-01-01"}], "episodes": []}
        )
