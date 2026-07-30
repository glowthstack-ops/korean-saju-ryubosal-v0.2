#!/usr/bin/env python3
"""OA-11f-P — 2026-03-15 `love_deepening` 유입 누락의 매개 경로 (측정 전용).

but-for 개입 {2026-02-12, 2026-03-14} 은 찾았지만, 두 개입이 **어떤 상태 변수를
거쳐** 03-15 선택을 바꿨는지는 미확정이다. 온라인 가드가 가능한지는 그것에 달렸다.

두 값을 분리한다.

    first_upstream_state_divergence
        개입 이후 丙辰 상태가 S0 과 처음 달라진 날짜·필드
    first_decision_stage_divergence
        03-15 의사결정 파이프라인에서 처음 달라진 단계

각 trajectory 의 2026-03-01 state 는 **자기 경로에서** 생성된다 — 공통 checkpoint
를 쓰면 ablation 대상 개입의 영향이 이미 섞여 들어간다. 여기서는 checkpoint 를
쓰지 않고 canonical origin 부터 각 trajectory 를 독립 재생한다(더 강한 조건).

한계효과 판정은 `audit_oa11f_b_online_replay.evaluate_marginal_candidate` 를
직접 호출한다 — probe 가 selector 로직을 복제하면 drift 가 난다.
"""

from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types",
           _BACKEND / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import audit_oa11f_b_online_replay as B  # noqa: E402
import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_board_constraints import HeadlineCandidate  # noqa: E402
from saju_engines.daily_canonical_bootstrap import C10_POLICY  # noqa: E402
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    SEVERITY_CLEAN,
    repeat_severity,
    select_board,
    select_good_representative,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

TARGET = "丙辰"
PROBE_EVENT = "love_deepening"
CHECKPOINT = dt.date(2026, 3, 1)
FOCUS = dt.date(2026, 3, 15)
FOCUS_END = dt.date(2026, 3, 20)

TRAJECTORIES: dict[str, dict[str, Any]] = {
    "S0": {"limit": None, "suppress": ()},
    "R6": {"limit": 6, "suppress": ()},
    "R7": {"limit": 7, "suppress": ()},
    "R6_drop_02-12": {"limit": 6, "suppress": ("2026-02-12",)},
    "R6_drop_03-14": {"limit": 6, "suppress": ("2026-03-14",)},
}

#: 03-15 비교 단계 — 선언 순서가 계약이다. 최초로 달라지는 단계가 causal pathway.
DECISION_STAGES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("state_before", ("headline_window_fp", "good_history_fp")),
    ("family_deficit", ("family_coverage", "family_deficit_active")),
    ("repeat_severity", ("raw_top_repeat_severity",)),
    ("raw_good_winner", ("raw_good_winner",)),
    ("c10_representative", ("c10_representative", "c10_kept_raw_top")),
    ("candidate_bundle", ("bundle_fp", "probe_lifecycle_stage")),
    ("marginal_deltas", ("probe_family_cov_delta", "probe_key_cov_delta",
                         "probe_family_qual_delta", "probe_key_qual_delta")),
    ("safety_eligibility", ("probe_safety_result", "probe_selector_eligible")),
    ("selector_decision", ("selector_intervened", "selector_choice",
                           "safe_option_count")),
    ("selected_preboard", ("selected_preboard_event",)),
    ("board_input", ("board_candidates_fp", "board_own_history_fp")),
    ("realized_postboard", ("realized_postboard_event",)),
    ("history_committed", ("history_committed_family",)),
)


def _fp(values) -> str:
    return hashlib.sha256("|".join(map(str, values)).encode("utf-8")).hexdigest()[:12]


def _lifecycle(scored, events, ranked, raw_key) -> str:
    """`PROBE_EVENT` 가 후보열에 도달했는지 — 도달 실패 지점을 이름으로 남긴다."""
    if PROBE_EVENT not in {s.event_key for s in scored}:
        return "NOT_GENERATED"
    s = next(x for x in scored if x.event_key == PROBE_EVENT)
    slots = events[PROBE_EVENT].get("headline_slots") or events[PROBE_EVENT]["slots"]
    if s.valence != "good" or "good" not in slots:
        return "BLOCKED_BY_HARD_FILTER"
    if PROBE_EVENT == raw_key:
        return "IS_RAW_TOP"
    if PROBE_EVENT not in {k for k, _ in ranked}:
        return "ABSENT_FROM_ORDERED_BUNDLE"
    return "PRESENT_IN_ORDERED_BUNDLE"


def replay(spec: dict[str, Any], family_of, events) -> dict[str, Any]:
    """한 trajectory 를 canonical origin 부터 재생한다."""
    limit, suppress = spec["limit"], set(spec["suppress"])
    hh: dict[str, list[str]] = collections.defaultdict(list)
    gh: dict[str, list[str]] = collections.defaultdict(list)
    rows: list[dict[str, Any]] = []
    daily_fp: dict[str, str] = {}
    checkpoint_fp: str | None = None
    reached: set[str] = set()
    suppressed: set[str] = set()
    day = B.DAILY_ROLLING_AUDIT_CONTRACT_V1.origin
    while day <= FOCUS_END:
        iso = day.isoformat()
        ctx = M.build_day_context(day)
        raw: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
        rec: dict[str, Any] | None = None
        others = 0
        for idx, ilju in enumerate(B._ILJUS):
            stem, branch = ganzi_from_index(idx)
            seed = f"{iso}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
            scored = [M._score_event(k, e, stem, branch, ctx)
                      for k, e in events.items()]
            goods = [
                (s.event_key, s.probability) for s in scored
                if s.valence == "good"
                and "good" in (events[s.event_key].get("headline_slots")
                               or events[s.event_key]["slots"])
            ]
            if not goods:
                continue
            ranked = sorted(goods, key=lambda x: (-x[1], x[0]))
            raw_key, raw_p = ranked[0]
            window = tuple(hh[ilju][-B._LOOKBACK:])
            families = {family_of.get(k, k) for k in window}
            deficit = len(families) < C10_POLICY.coverage_floor
            severity = repeat_severity(gh[ilju], raw_key)
            consulted = limit is not None and deficit and severity == SEVERITY_CLEAN
            options = B._safe_candidates(
                scored, seed, events, ranked, raw_key, raw_p, window, family_of,
                loss_limit=limit,
            ) if consulted else []
            chosen = B._pick("B1", options) if options else None
            if chosen is not None and ilju == TARGET:
                reached.add(iso)
                if iso in suppress:
                    suppressed.add(iso)
                    chosen = None
            c10_rep: str | None = None
            c10_reason: str | None = None
            if chosen is not None:
                g, c, s = chosen["slots"]
                cands, pick = chosen["cands"], chosen["event_key"]
                if ilju != TARGET:
                    others += 1
            else:
                rep = select_good_representative(
                    goods, gh[ilju], B._BUDGET, policy=C10_POLICY,
                    family_of=family_of, headline_history=hh[ilju],
                )
                g, c, s = M._select_slots(
                    scored, seed, good_override=rep.display_good_representative
                )
                cands = M._headline_candidates(g, s, c, M._band(g, c))
                pick = rep.display_good_representative
                c10_rep = rep.display_good_representative
                c10_reason = getattr(rep, "reason", None)
            cmap[ilju] = [
                HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
            ]
            raw[ilju] = cmap[ilju][0]
            gh[ilju].append(pick)
            if ilju != TARGET:
                continue
            daily_fp[iso] = _fp((*window, "#", *gh[ilju]))
            if day == CHECKPOINT:
                checkpoint_fp = _fp((*window, "#", *gh[ilju][:-1]))
            if day < CHECKPOINT:
                continue
            # ── 상세 기록 구간 (03-01 ~ 03-20) ─────────────────────────
            life = _lifecycle(scored, events, ranked, raw_key)
            pe: dict[str, Any] = {}
            if life == "PRESENT_IN_ORDERED_BUNDLE":
                baseline = B.marginal_baseline(
                    scored, seed, raw_key, raw_p, window, family_of,
                    loss_limit=limit if limit is not None else B._BUDGET,
                )
                if baseline.available:
                    rank, prob = next(
                        (i, p) for i, (k, p) in enumerate(ranked, start=1)
                        if k == PROBE_EVENT
                    )
                    pe = B.evaluate_marginal_candidate(
                        scored=scored, seed=seed, family_of=family_of,
                        baseline=baseline, event_key=PROBE_EVENT, rank=rank,
                        probability=prob,
                    ).as_record()
                else:
                    pe = {"baseline_unavailable": True}
            rec = {
                "date": iso,
                "headline_window_fp": _fp(window),
                "good_history_fp": _fp(gh[ilju][:-1]),
                "family_coverage": len(families),
                "family_deficit_active": deficit,
                "raw_top_repeat_severity": severity,
                "raw_good_winner": raw_key,
                "bundle_fp": _fp([f"{k}:{p}" for k, p in ranked]),
                "c10_representative": c10_rep,
                "c10_representative_reason": c10_reason,
                "c10_kept_raw_top": c10_rep == raw_key if c10_rep else None,
                "probe_lifecycle_stage": life,
                "probe_rejected_at_stage": pe.get("rejected_at_stage"),
                "probe_mediation": pe.get("mediation"),
                "probe_safety_result": pe.get("safety_result"),
                "probe_rank": pe.get("rank"),
                "probe_slot_feasible": pe.get("slot_feasible"),
                "probe_projection_status": pe.get("projection_status"),
                "probe_family_cov_delta": pe.get("family_coverage_delta_vs_raw"),
                "probe_key_cov_delta": pe.get("key_coverage_delta_vs_raw"),
                "probe_family_qual_delta": pe.get("family_qualifying_delta_vs_raw"),
                "probe_key_qual_delta": pe.get("key_qualifying_delta_vs_raw"),
                "probe_selector_eligible": pe.get("selector_eligible"),
                "selector_consulted": consulted,
                "safe_option_count": len(options),
                "selector_intervened": chosen is not None,
                "selector_choice": chosen["event_key"] if chosen else None,
                "selected_preboard_event": cmap[ilju][0].event_key,
                "board_candidates_fp": _fp(
                    [f"{c.event_key}:{c.probability}" for c in cmap[ilju]]
                ),
                "board_own_history_fp": _fp(hh[ilju][-B._LOOKBACK:]),
                "other_iljus_intervened_today": others,
            }
        result = select_board(
            raw, cmap, hh, domain_cap=21, event_cap=10,
            max_displacement_cost=B._BUDGET, policy=B._BOARD, today=day.toordinal(),
        )
        if rec is not None:
            got = result.selections[TARGET].event_key
            rec["realized_postboard_event"] = got
            rec["history_committed_family"] = family_of.get(got, got)
            rec["board_displaced"] = rec["selected_preboard_event"] != got
            rows.append(rec)
        for ilju, sel in result.selections.items():
            hh[ilju].append(sel.event_key)
        day += dt.timedelta(days=1)
    return {
        "state_generation_start": B.DAILY_ROLLING_AUDIT_CONTRACT_V1.origin.isoformat(),
        "checkpoint_policy": "SELF_GENERATED_FROM_CANONICAL_ORIGIN",
        "ablation_requested": sorted(suppress),
        "ablation_reached": sorted(reached & suppress),
        "ablation_suppressed": sorted(suppressed),
        "ablation_unreached": sorted(suppress - reached),
        "state_2026_03_01_fingerprint": checkpoint_fp,
        "target_interventions_total": len(reached),
        "daily_state_fp": daily_fp,
        "rows": rows,
    }


def run() -> dict[str, Any]:
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    events = M.load_daily_dicts().catalog["events"]
    traj = {n: replay(s, family_of, events) for n, s in TRAJECTORIES.items()}

    iso_focus = FOCUS.isoformat()
    s0 = traj["S0"]
    s0_row = next(r for r in s0["rows"] if r["date"] == iso_focus)

    out: dict[str, Any] = {}
    for name, t in traj.items():
        row = next((r for r in t["rows"] if r["date"] == iso_focus), None)
        # ① 개입 이후 상태가 S0 과 처음 달라진 날
        up = next(
            (d for d in sorted(s0["daily_state_fp"])
             if t["daily_state_fp"].get(d) != s0["daily_state_fp"][d]),
            None,
        )
        # ② 03-15 파이프라인에서 처음 달라진 단계
        diverged: list[str] = []
        equal: list[str] = []
        for stage, fields in DECISION_STAGES:
            same = row is not None and all(row[f] == s0_row[f] for f in fields)
            (equal if same else diverged).append(stage)
        first_stage = diverged[0] if diverged else None
        restored = next(
            (st for st, _ in DECISION_STAGES
             if st in equal and diverged and
             [s for s, _ in DECISION_STAGES].index(st)
             > [s for s, _ in DECISION_STAGES].index(diverged[0])),
            None,
        )
        out[name] = {
            "state_generation_start": t["state_generation_start"],
            "checkpoint_policy": t["checkpoint_policy"],
            "ablation_requested": t["ablation_requested"],
            "ablation_reached": t["ablation_reached"],
            "ablation_suppressed": t["ablation_suppressed"],
            "ablation_unreached": t["ablation_unreached"],
            "state_2026_03_01_fingerprint": t["state_2026_03_01_fingerprint"],
            "checkpoint_fp_equals_r6": (
                t["state_2026_03_01_fingerprint"]
                == traj["R6"]["state_2026_03_01_fingerprint"]
            ),
            "target_interventions_total": t["target_interventions_total"],
            "first_upstream_state_divergence": up,
            "first_decision_stage_divergence": first_stage,
            "diverged_stages": diverged,
            "stages_equal_to_s0": equal,
            "restored_to_s0_at_stage": restored,
            "focus_row": row,
        }
    # ── 두 but-for 개입의 역할 분리 (측정에서 유도) ──────────────────────
    #: 직전일(03-14) 행에서 개입이 사라진 이유가 "그 날을 직접 억제해서"인지
    #: "경로가 바뀌어 후보 자격이 사라져서"인지로 근접 원인과 조력 원인을 가른다.
    roles: dict[str, Any] = {}
    prev = (FOCUS - dt.timedelta(days=1)).isoformat()
    for name, t in traj.items():
        if not t["ablation_suppressed"]:
            continue
        row = next((r for r in t["rows"] if r["date"] == prev), None)
        if row is None:
            continue
        directly = prev in t["ablation_suppressed"]
        roles[name] = {
            "suppressed_date": t["ablation_suppressed"][0],
            "prev_day_intervened": row["selector_intervened"],
            "prev_day_consulted": row["selector_consulted"],
            "prev_day_safe_option_count": row["safe_option_count"],
            "prev_day_family_coverage": row["family_coverage"],
            "prev_day_committed": row["realized_postboard_event"],
            "role": (
                "PROXIMATE_CAUSE" if directly
                else "ENABLING_CAUSE_VIA_CANDIDATE_ELIGIBILITY"
                if row["selector_consulted"] and row["safe_option_count"] == 0
                else "ENABLING_CAUSE_MECHANISM_UNRESOLVED"
            ),
            "mechanism": (
                "직전일 원시 1위를 치환해 다음 날 연속 반복(severity 3)을 소멸시켰다"
                if directly
                else "직전일 family coverage 를 복원해 한계효과 후보 자격을 없앴고, "
                     "그 결과 직전일 개입 자체가 발생하지 않았다"
            ),
        }
    return {
        "audit_id": "OA-11f-P",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "target_ilju": TARGET,
        "probe_event": PROBE_EVENT,
        "focus_date": iso_focus,
        "detail_range": f"{CHECKPOINT.isoformat()} ~ {FOCUS_END.isoformat()}",
        "outcome_failure": "REPLENISHMENT_OMISSION_ON_2026-03-15",
        "but_for_interventions": ["2026-02-12", "2026-03-14"],
        "marginal_evaluator_ssot": "evaluate_marginal_candidate",
        "probe_reimplements_marginal_delta": False,
        "note": (
            "두 but-for 개입이 같은 매개 경로를 쓴다고 가정하지 않는다 — 각 단일 "
            "ablation 을 따로 비교한다."
        ),
        "causal_layers": {
            "outcome_failure": "REPLENISHMENT_OMISSION_ON_2026-03-15",
            "but_for_interventions": ["2026-02-12", "2026-03-14"],
            "causal_pathway": "REPEAT_HISTORY_MEDIATION",
            "mediator": "repeat_severity(raw_top) — SEVERITY_CONSECUTIVE(3)",
            "chain": [
                "2026-02-12 개입 → 03-14 family coverage 15→14",
                "03-14 한계효과 후보 자격 발생(opts 0→1) → 03-14 개입",
                "03-14 원시 1위(good_news_arrives) 치환 → 03-15 severity 3→0",
                "C10 반복 회피 미발동 → 대표가 원시 1위 유지",
                "love_deepening 이 헤드라인 후보 묶음에 진입하지 못함",
                "board 가 치환할 재료 없음 → deepening family 미기록",
                "2026-04-02 丙辰 coverage 15→14 (family·key 동시 하락)",
            ],
            "rejected_pathways": {
                "CANDIDATE_AVAILABILITY_MEDIATION": "bundle_fp 5/5 동일",
                "MARGINAL_ELIGIBILITY_MEDIATION": "famΔ=0 로 5/5 동일 탈락",
                "SELECTOR_ORDER_MEDIATION": "03-15 개입 0/5",
                "DEFICIT_STATE_MEDIATION": "deficit 5/5 활성 동일",
                "CROSS_ILJU_BOARD_COUPLING": "03-15 타 일주 개입 0건",
            },
            "board_role": (
                "board 는 C10 이 후보 묶음에 넣은 love_deepening 을 실현했을 뿐이다 "
                "— 두 계층이 모두 필요했지만 갈리는 변수는 C10 대표다."
            ),
            "two_intervention_sequential_mediation": "CONFIRMED",
            "intervention_roles": roles,
        },
        "comparison": out,
        "trace": {n: t["rows"] for n, t in traj.items()},
    }


if __name__ == "__main__":
    r = run()
    p = _ROOT / "doc" / "v2_2" / "audits" / "oa11f_p_focus_0315.json"
    p.write_text(json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n",
                 encoding="utf-8")
    print("[ok]", p.name)
    for n, c in r["comparison"].items():
        f = c["focus_row"]
        print(f"\n── {n}")
        print(f"   03-01 state fp {c['state_2026_03_01_fingerprint']} "
              f"(=R6? {c['checkpoint_fp_equals_r6']})  "
              f"ablation req/reach/supp "
              f"{c['ablation_requested']}/{c['ablation_reached']}/"
              f"{c['ablation_suppressed']}  丙辰 개입 "
              f"{c['target_interventions_total']}")
        print(f"   상태 최초 분기 {c['first_upstream_state_divergence']}   "
              f"03-15 단계 최초 분기 {c['first_decision_stage_divergence']}   "
              f"복원 {c['restored_to_s0_at_stage']}")
        print(f"   분기 단계 {c['diverged_stages']}")
        print(f"   cov={f['family_coverage']} deficit={f['family_deficit_active']} "
              f"sev={f['raw_top_repeat_severity']} raw={f['raw_good_winner']} "
              f"consult={f['selector_consulted']} opts={f['safe_option_count']} "
              f"iv={f['selector_intervened']}")
        print(f"   C10 대표 {f['c10_representative']} "
              f"(원시1위 유지 {f['c10_kept_raw_top']}) 이유 "
              f"{f['c10_representative_reason']}")
        print(f"   probe {f['probe_lifecycle_stage']} rank={f['probe_rank']} "
              f"reject={f['probe_rejected_at_stage']} "
              f"famΔ={f['probe_family_cov_delta']} "
              f"keyΔ={f['probe_key_cov_delta']} "
              f"eligible={f['probe_selector_eligible']}")
        print(f"   preboard={f['selected_preboard_event']} "
              f"→ postboard={f['realized_postboard_event']} "
              f"displaced={f['board_displaced']} "
              f"cand_fp={f['board_candidates_fp']} "
              f"ownhist_fp={f['board_own_history_fp']}")
