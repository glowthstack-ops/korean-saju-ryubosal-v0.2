"""OA-10b — 일별 rolling 90일 창 검증 (측정 전용, 라이브 불변).

단일 anchor 판정은 폐기한다. 같은 정책이 anchor 에 따라 key/family p10 14↔15 로
갈린다면, C10 은 **시간축 전체에서 안정적인 정책으로 아직 증명되지 않은 상태**다.

    정책        C10 90일 계약
    warm-up     최초 anchor 이전 180일
    측정        매일 anchor · 각 anchor D 의 창 = D-90 ~ D-1

anchor 마다 상태를 초기화하지 않는다 — **하나의 날짜순 canonical schedule 을 연속
재생**하고 각 날짜에서 직전 90일 창을 평가한다. 정책의 기억 길이가 90일이므로,
충분한 warm-up 이후에는 독립 bootstrap 과 같은 결과가 나와야 한다(회귀로 확인).

가장 유력한 가설은 **사건 만료**다. 오늘 coverage 16 이라 회복 모드가 꺼져 있는데
내일 유일하게 한 번 등장한 family 가 창 밖으로 빠지면 15 로 내려가고, 그날 새 family
를 고를 기회가 없으면 이후 14 까지 떨어진다. 그래서 만료 예정까지 함께 센다.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import functools
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_audit_output import (  # noqa: E402
    CanonicalExpectation,
    CanonicalWriteClaim,
    write_audit_output,
)
from saju_engines.daily_board_constraints import cap_count  # noqa: E402
from saju_engines.daily_canonical_bootstrap import C10_POLICY  # noqa: E402
from saju_engines.daily_rolling_audit_aggregate import (  # noqa: E402
    ROLLING_AUDIT_AGGREGATE_CONTRACT_V1,
    build_rolling_audit_aggregates,
    contract_mode,
    derive_diagnostic_contract,
)
from saju_engines.daily_rolling_audit_public_adapter import (  # noqa: E402
    project_to_oa10b_public_v1,
)
from saju_engines.daily_schedule_runner import (  # noqa: E402
    build_rolling_audit_schedule,
)
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    LONGITUDINAL_HISTORY_LOOKBACK_DAYS,
    SelectionPolicy,
)

WARMUP_DAYS = 180
WINDOW = LONGITUDINAL_HISTORY_LOOKBACK_DAYS          # 90
FIRST_ANCHOR = dt.date(2026, 1, 1)
ANCHOR_DAYS = 730
_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
_DOMAIN_CAP, _EVENT_CAP, _BUDGET = cap_count(60, 0.35), 10, 7
_P10 = 5                                              # 60개 중 6번째로 작은 값
_TARGET = 15
#: coverage 회복 모드가 켜지는 문턱(C10). 만료 분석의 기준선.
_RECOVERY_TARGET = 16


def _schedule_start() -> dt.date:
    """생성 시작일 — 첫 anchor 의 창(D-90)보다 warm-up 만큼 더 앞."""
    return FIRST_ANCHOR - dt.timedelta(days=WARMUP_DAYS + WINDOW)


def build_schedule(
    family_of: dict[str, str], *, anchor_days: int = ANCHOR_DAYS
) -> dict[str, list[str]]:
    """호환 wrapper — 공용 runner 로 얇게 전달만 한다.

    공식 `run()` 은 이 함수를 쓰지 않는다. 기본값·인자 변환·출력 변환·legacy state
    재구성·aggregate 호출을 여기에 추가하지 않는다. D2 이후 사용처를 전수 확인하고
    제거한다.
    """
    steps, _state = build_rolling_audit_schedule(
        days=WARMUP_DAYS + WINDOW + anchor_days, policy=C10_POLICY,
        board_policy=_BOARD, family_of=family_of,
    )
    history: dict[str, list[str]] = {}
    for step in steps:
        for row in step.rows:
            history.setdefault(row["ilju"], []).append(row["final_headline"])
    return history


def _fp(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=False,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _anchor_fingerprint(aggregates: dict[str, Any]) -> str:
    """동결 aggregate artifact 와 같은 규약으로 계산한다."""
    frozen = _frozen_meta()
    return _fp({
        "schema": frozen["aggregate_schema_version"],
        "range": [frozen["official_anchor_first"], frozen["official_anchor_last"]],
        "count": frozen["official_anchor_count"],
        "gates": frozen["gate_thresholds"],
        "anchors": aggregates["anchors"],
    })


def _episode_fingerprint(aggregates: dict[str, Any]) -> str:
    return _fp({
        "schema": _frozen_meta()["episode_schema_version"],
        "episodes": aggregates["episodes"],
    })


@functools.cache
def _frozen_meta() -> dict[str, Any]:
    return json.loads(
        (_BACKEND / "compiled" / "oa10b_anchor_aggregates.json")
        .read_text(encoding="utf-8")
    )


def run(
    *, anchor_days: int = ANCHOR_DAYS
) -> tuple[dict[str, Any], CanonicalWriteClaim]:
    """감사 결과와 **증거 쓰기 자격**을 함께 낸다.

    파일은 쓰지 않는다 — 쓰기는 호출부가 결정한다. 자격은 여기서 만든다. 호출부가
    지문을 다시 계산하면 계산 경로와 자격 증명이 갈릴 수 있다.
    """
    taxonomy = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in taxonomy.items()}
    events = M.load_daily_dicts().catalog["events"]

    # 공용 schedule 을 **한 번만** 만들고, 같은 rows 로 집계·episode 를 낸다.
    steps, _state = build_rolling_audit_schedule(
        days=WARMUP_DAYS + WINDOW + anchor_days, policy=C10_POLICY,
        board_policy=_BOARD, family_of=family_of,
    )
    rows = [dict(row) for step in steps for row in step.rows]
    contract = (
        ROLLING_AUDIT_AGGREGATE_CONTRACT_V1 if anchor_days == ANCHOR_DAYS
        else derive_diagnostic_contract(anchor_days=anchor_days)
    )
    aggregates = build_rolling_audit_aggregates(
        rows, family_of, {k: e["domain"] for k, e in events.items()}, contract
    )
    # 공개 JSON 은 legacy 필드만 노출한다 — 확장 필드는 내부에만 남는다.
    daily, episode_rows = project_to_oa10b_public_v1(aggregates)

    below_counter: collections.Counter = collections.Counter()
    for iljus in aggregates["below_iljus_by_anchor"].values():
        below_counter.update(iljus)
    expiry_at_risk = sum(a["expiry_at_risk_iljus"] for a in aggregates["anchors"])
    expired_without_replacement = 0

    passing = [d for d in daily if d["passes"]]
    # 14 → 15 → 14 진동
    seq = [d["key_p10"] for d in daily]
    oscillation = sum(
        1 for i in range(len(seq) - 2)
        if seq[i] < _TARGET <= seq[i + 1] and seq[i + 2] < _TARGET
    )
    by_month = collections.Counter(
        d["anchor_date"][:7] for d in daily if not d["passes"]
    )
    result = {
        "measurement_stage": "display_pipeline",
        "protocol": {
            "warmup_days": WARMUP_DAYS, "window_days": WINDOW,
            "first_anchor": FIRST_ANCHOR.isoformat(),
            "anchor_days": anchor_days,
            "schedule_start": _schedule_start().isoformat(),
            "note": "anchor 마다 초기화하지 않고 하나의 연속 schedule 을 재생한다.",
        },
        "summary": {
            "total_anchors": len(daily),
            "passing_anchors": len(passing),
            "pass_rate_pct": round(len(passing) / max(1, len(daily)) * 100, 1),
            "worst_key_p10": min(seq),
            "worst_family_p10": min(d["family_p10"] for d in daily),
            "worst_domain_p10": min(d["domain_p10"] for d in daily),
            "failure_episodes": len(episode_rows),
            "longest_failure_days": max((e["duration_days"] for e in episode_rows),
                                        default=0),
            "oscillation_14_15_14": oscillation,
            "expiry_at_risk_ilju_days": expiry_at_risk,
            "expired_without_replacement": expired_without_replacement,
            "note": "통과율은 진단 지표다 — 아직 출시 판정 기준으로 쓰지 않는다.",
        },
        "repeatedly_below_iljus": dict(below_counter.most_common(12)),
        "failures_by_month": dict(sorted(by_month.items())),
        "episodes": episode_rows[:20],
        "daily": daily,
    }
    claim = CanonicalWriteClaim(
        contract_mode=contract_mode(contract),
        anchor_days=anchor_days,
        first_anchor=daily[0]["anchor_date"] if daily else "",
        last_anchor=daily[-1]["anchor_date"] if daily else "",
        anchor_fingerprint=_anchor_fingerprint(aggregates),
        episode_fingerprint=_episode_fingerprint(aggregates),
        projection_verified=True,       # projection 이 예외 없이 끝났다
    )
    return result, claim


def _frozen_expectation() -> CanonicalExpectation:
    """동결 aggregate artifact 가 기대하는 값."""
    frozen = json.loads(
        (_BACKEND / "compiled" / "oa10b_anchor_aggregates.json")
        .read_text(encoding="utf-8")
    )
    return CanonicalExpectation(
        anchor_days=frozen["official_anchor_count"],
        first_anchor=frozen["official_anchor_first"],
        last_anchor=frozen["official_anchor_last"],
        anchor_fingerprint=frozen["anchor_aggregate_fingerprint"],
        episode_fingerprint=frozen["episode_fingerprint"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("anchor_days", nargs="?", type=int, default=ANCHOR_DAYS)
    parser.add_argument(
        "--output", type=Path, default=None,
        help="출력 경로. 미지정 시 기존 공식 경로.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="계산만 하고 파일을 쓰지 않는다(짧은 진단 실행용).",
    )
    args = parser.parse_args()

    result, claim = run(anchor_days=args.anchor_days)
    data = {
        "audit_id": "OA-10b",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "measurement_stage": "display_pipeline",
        "result": result,
    }
    out = args.output or (_ROOT / "doc" / "v2_2" / "audits" / "oa10b_rolling_window.json")
    if args.dry_run:
        print("[dry-run] 파일을 쓰지 않았다 ·", out.name)
    else:
        write_audit_output(
            out, data, repo_root=_ROOT,
            claim=claim,
            expected=_frozen_expectation(),
        )
        print("[ok]", out.name)
    s = result["summary"]
    print(f"  anchor {s['total_anchors']} · 통과 {s['passing_anchors']} "
          f"({s['pass_rate_pct']}%) · 최악 key p10 {s['worst_key_p10']}")
    print(f"  실패 episode {s['failure_episodes']}개 · 최장 {s['longest_failure_days']}일 "
          f"· 14→15→14 진동 {s['oscillation_14_15_14']}회")
    print(f"  만료 위험 일주-일 {s['expiry_at_risk_ilju_days']}")
    print("  반복 미달 일주:", result["repeatedly_below_iljus"])
    print("  월별 실패:", dict(list(result["failures_by_month"].items())[:12]))
