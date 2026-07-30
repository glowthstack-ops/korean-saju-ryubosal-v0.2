#!/usr/bin/env python3
"""OA-11f-B — 안전 후보 풀의 **온라인** 도달성 (측정 전용, 정책 미채택).

OA-11f-A 는 행 단위 한계효과만 봤다. 문턱 이득 후보가 anchor 마다 10~18건이고
필요한 순증가가 1·1·3·1 이지만, 그것만으로 닫힌다고 말할 수 없다 — 앞선 선택이
이후 후보의 delta 를 바꾸고 eviction·board 가 상쇄한다(S1 에서 실현 34건이 순증가
0 이 된 것과 같은 구조).

이 감사는 새 정책 개발이 아니라, candidate/slot 계약을 확장하기 전에 필요한
**마지막 반증 단계**다.

    S0  기존 C10 (대조군 — selector 를 끄면 C10 과 같아야 한다)
    B1  threshold-first  online
    B2  coverage-first   online
    B3  optimistic safe local bound (production 후보 아님)

`SAFETY_BLOCKED` 후보는 어떤 모드에서도 쓰지 않는다 — 안전 가드를 완화했을 때의
가능성을 보는 감사가 아니다.
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types",
           _BACKEND / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_board_constraints import HeadlineCandidate  # noqa: E402
from saju_engines.daily_canonical_bootstrap import C10_POLICY  # noqa: E402
from saju_engines.daily_rolling_audit_aggregate import (  # noqa: E402
    build_rolling_audit_aggregates,
    derive_diagnostic_contract,
)
from saju_engines.daily_schedule_runner import (  # noqa: E402
    DAILY_BOARD_CONTRACT_V1,
    DAILY_HISTORY_CONTRACT_V1,
    DAILY_ROLLING_AUDIT_CONTRACT_V1,
    CardCandidateBundle,
    ProjectionStatus,
    derive_top1_family_projection,
)
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    SEVERITY_CLEAN,
    SelectionPolicy,
    repeat_severity,
    select_board,
    select_good_representative,
    strength_band,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
_ILJUS = [
    f"{ganzi_from_index(i)[0].value}{ganzi_from_index(i)[1].value}" for i in range(60)
]
ANCHORS = ("2026-04-02", "2027-03-03", "2027-06-01", "2027-08-05", "2027-10-09")
_LAST = dt.date(2027, 10, 9)
_LOOKBACK = DAILY_HISTORY_CONTRACT_V1.lookback_days
#: 전역 안전 예산 — 강한 사건 구제·위험 차단용 상한이다. 바꾸지 않는다.
_BUDGET = DAILY_BOARD_CONTRACT_V1.displacement_loss_budget
#: 이 diversity 보조 정책의 **실효** 상한. 보조 정책이 전역 예산을 전부 쓰게 두지
#: 않는다(R7 측정에서 개입의 17.9%가 7p 를 소진했다). 집계 상한은 온라인 선택
#: 시점에 적용할 수 없으므로 각 행에서 판정 가능한 로컬 계약으로 둔다.
_DIVERSITY_LOSS_LIMIT = 6
_QUALIFY = 15
MODES = ("S0", "B1", "B2", "B3")
SELECTOR_ID = "FIRST_SAFE_POSITIVE_MARGINAL_CANDIDATE_R6"


def _next_counts(window: tuple[str, ...], addition: str, family_of) -> tuple[int, int]:
    merged = (*window, addition)
    if len(merged) > _LOOKBACK:
        merged = merged[-_LOOKBACK:]
    return len(set(merged)), len({family_of.get(k, k) for k in merged})


#: 후보가 탈락한 단계. 선언 순서 = 실제 평가 순서이며, `None` 이면 selector 자격
#: 획득이다. 진단(probe)과 selector 가 같은 라벨을 읽어야 하므로 여기서만 정의한다.
MARGINAL_STAGES = (
    "SAFETY", "SLOT_FEASIBILITY", "PROJECTION", "FAMILY_MARGINAL", "KEY_MARGINAL",
)
#: `rejected_at_stage` → causal pathway 상위 라벨.
STAGE_TO_MEDIATION = {
    "SAFETY": "SAFETY_MEDIATION",
    "SLOT_FEASIBILITY": "SLOT_FEASIBILITY_MEDIATION",
    "PROJECTION": "PROJECTION_MEDIATION",
    "FAMILY_MARGINAL": "FAMILY_MARGINAL_MEDIATION",
    "KEY_MARGINAL": "KEY_MARGINAL_MEDIATION",
}


@dataclass(frozen=True)
class MarginalBaseline:
    """행 단위 기준선 — 원시 1위를 commit 했을 때의 다음 창(같은 D-90 eviction)."""

    available: bool
    base_key_coverage: int | None
    base_family_coverage: int | None
    raw_top_band: int | None
    raw_probability: int | None
    loss_limit: int
    #: 기준선과 후보가 **같은 D-90 창**을 쓰도록 창을 결과에 결박한다.
    window: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarginalCandidateEvaluation:
    """후보 1건의 한계효과 평가 결과 — selector 와 probe 의 **공용 SSOT**.

    두 호출자가 이 immutable 결과만 읽는다. 평가 로직을 복제하면 drift 가 나므로
    (실제로 focus probe 초안에서 발생했다) 계산은 여기 한 곳에만 둔다.
    """

    event_key: str
    rank: int
    probability: int
    loss: int
    safety_result: str
    slot_feasible: bool | None
    projection_status: str | None
    projected_family: str | None
    preboard_event_key: str | None
    family_coverage_delta_vs_raw: int | None
    key_coverage_delta_vs_raw: int | None
    family_qualifying_delta_vs_raw: int | None
    key_qualifying_delta_vs_raw: int | None
    selector_eligible: bool
    rejected_at_stage: str | None
    slots: Any = None
    cands: Any = None

    @property
    def mediation(self) -> str | None:
        """탈락 단계의 causal pathway 라벨(자격 획득 시 `None`)."""
        return STAGE_TO_MEDIATION.get(self.rejected_at_stage or "")

    def as_record(self) -> dict[str, Any]:
        """artifact 직렬화용 — 비직렬화 slot/candidate 객체는 제외한다."""
        return {
            k: v for k, v in self.__dict__.items() if k not in ("slots", "cands")
        } | {"mediation": self.mediation}


def marginal_baseline(
    scored, seed, raw_key, raw_p, window, family_of, loss_limit: int | None = None,
) -> MarginalBaseline:
    """원시 1위 기준선을 계산한다. 원시 1위 카드가 없으면 `available=False`."""
    limit = _DIVERSITY_LOSS_LIMIT if loss_limit is None else loss_limit
    rg, rc, rs = M._select_slots(scored, seed, good_override=raw_key)
    if rg.event_key != raw_key:
        return MarginalBaseline(False, None, None, None, None, limit, tuple(window))
    rcands = M._headline_candidates(rg, rs, rc, M._band(rg, rc))
    base_key, base_fam = _next_counts(window, rcands[0].event_key, family_of)
    return MarginalBaseline(
        True, base_key, base_fam, strength_band(raw_p), raw_p, limit, tuple(window)
    )


def evaluate_marginal_candidate(
    *, scored, seed, family_of, baseline: MarginalBaseline,
    event_key: str, rank: int, probability: int,
) -> MarginalCandidateEvaluation:
    """후보 1건을 실제 평가 순서대로 판정하고, **최초 실패 단계**를 기록한다.

    단계 순서는 라이브 계약 그대로다 — safety 가 slot 구성보다 앞이므로 안전 차단
    후보에 대해서는 `_select_slots` 를 호출하지 않는다(호출 수도 계약의 일부).
    """
    loss = (baseline.raw_probability or 0) - probability
    band = strength_band(probability)
    top_band = baseline.raw_top_band or 0
    safety = (
        "LOSS_OVER_LIMIT" if loss > baseline.loss_limit
        else "S5_PROTECTION" if top_band == 4 and band < top_band
        else "TWO_BAND_DROP" if top_band - band >= 2
        else "PASS"
    )
    def _out(
        *, stage: str | None, slot_feasible: bool | None = None,
        projection_status: str | None = None, projected_family: str | None = None,
        preboard_event_key: str | None = None, fam_cov: int | None = None,
        key_cov: int | None = None, fam_qual: int | None = None,
        key_qual: int | None = None, eligible: bool = False,
        slots: Any = None, cands: Any = None,
    ) -> MarginalCandidateEvaluation:
        return MarginalCandidateEvaluation(
            event_key=event_key, rank=rank, probability=probability, loss=loss,
            safety_result=safety, slot_feasible=slot_feasible,
            projection_status=projection_status, projected_family=projected_family,
            preboard_event_key=preboard_event_key,
            family_coverage_delta_vs_raw=fam_cov,
            key_coverage_delta_vs_raw=key_cov,
            family_qualifying_delta_vs_raw=fam_qual,
            key_qualifying_delta_vs_raw=key_qual,
            selector_eligible=eligible, rejected_at_stage=stage,
            slots=slots, cands=cands,
        )

    if safety != "PASS":
        return _out(stage="SAFETY")
    g, c, s = M._select_slots(scored, seed, good_override=event_key)
    if g.event_key != event_key:
        return _out(stage="SLOT_FEASIBILITY", slot_feasible=False)
    cands = M._headline_candidates(g, s, c, M._band(g, c))
    projection = derive_top1_family_projection(
        raw_top_event_key=event_key,
        card_candidates=CardCandidateBundle(
            good_event_key=g.event_key, slots=(g, c, s),
            headline_candidates=tuple(cands),
        ),
        family_of=family_of,
    )
    status, family = projection.status.value, projection.family
    preboard = cands[0].event_key
    if projection.status is not ProjectionStatus.PROJECTED:
        return _out(
            stage="PROJECTION", slot_feasible=True, projection_status=status,
            projected_family=family, preboard_event_key=preboard,
        )
    base_fam = baseline.base_family_coverage or 0
    base_key = baseline.base_key_coverage or 0
    cand_key, cand_fam = _next_counts(baseline.window, preboard, family_of)
    fam_cov, key_cov = cand_fam - base_fam, cand_key - base_key
    fam_qual = int(cand_fam >= _QUALIFY) - int(base_fam >= _QUALIFY)
    key_qual = int(cand_key >= _QUALIFY) - int(base_key >= _QUALIFY)
    stage = (
        "FAMILY_MARGINAL" if fam_cov <= 0
        else "KEY_MARGINAL" if key_cov < 0 or key_qual < 0
        else None
    )
    return _out(
        stage=stage, slot_feasible=True, projection_status=status,
        projected_family=family, preboard_event_key=preboard, fam_cov=fam_cov,
        key_cov=key_cov, fam_qual=fam_qual, key_qual=key_qual,
        eligible=stage is None, slots=(g, c, s), cands=cands,
    )


def _safe_candidates(
    scored, seed, events, ranked, raw_key, raw_p, window, family_of,
    loss_limit: int | None = None,
) -> list[dict[str, Any]]:
    """기존 후보열 중 안전 가드를 모두 통과한 후보의 한계효과.

    `loss_limit` 은 이 diversity 보조 정책의 실효 상한이다(R6=6, R7=7). 전역 안전
    예산 `_BUDGET` 을 바꾸는 것이 아니다 — 포렌식에서 두 변형을 나란히 재생하기
    위해 인자로 받는다.

    판정은 `evaluate_marginal_candidate` 에 위임한다 — probe 와 같은 SSOT.
    """
    evals = evaluate_candidate_bundle(
        scored=scored, seed=seed, ranked=ranked, raw_key=raw_key, raw_p=raw_p,
        window=window, family_of=family_of, loss_limit=loss_limit,
    )
    return [
        {
            "rank": e.rank, "event_key": e.event_key, "slots": e.slots,
            "cands": e.cands, "fam_qual": e.family_qualifying_delta_vs_raw,
            "fam_cov": e.family_coverage_delta_vs_raw,
            "key_qual": e.key_qualifying_delta_vs_raw,
            "key_cov": e.key_coverage_delta_vs_raw, "loss": e.loss,
            "preboard_family": e.projected_family,
        }
        for e in evals if e.selector_eligible
    ]


def evaluate_candidate_bundle(
    *, scored, seed, ranked, raw_key, raw_p, window, family_of,
    loss_limit: int | None = None,
) -> list[MarginalCandidateEvaluation]:
    """정렬된 후보열 전체를 SSOT 평가자로 판정한다(원시 1위는 제외)."""
    baseline = marginal_baseline(
        scored, seed, raw_key, raw_p, window, family_of, loss_limit=loss_limit
    )
    if not baseline.available:
        return []
    return [
        evaluate_marginal_candidate(
            scored=scored, seed=seed, family_of=family_of, baseline=baseline,
            event_key=key, rank=rank, probability=prob,
        )
        for rank, (key, prob) in enumerate(ranked, start=1)
        if key != raw_key
    ]


def _pick(mode: str, options: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not options:
        return None
    if mode == "B1":            # 즉시 문턱 우선
        return min(options, key=lambda o: (
            -o["fam_qual"], -o["fam_cov"], -o["key_qual"], -o["key_cov"],
            o["rank"], o["event_key"],
        ))
    if mode == "B2":            # coverage 우선(13→14 도 포함)
        return min(options, key=lambda o: (
            -o["fam_cov"], -o["fam_qual"], -o["key_qual"], -o["key_cov"],
            o["rank"], o["event_key"],
        ))
    # B3 — 감사 목적함수를 가장 크게. production 후보가 아니며 lookahead 도
    # 쓰지 않으므로 참 상한이 아니라 **로컬** 낙관 경계다.
    return min(options, key=lambda o: (
        -(o["fam_qual"] * 10 + o["fam_cov"]), -o["key_qual"], -o["key_cov"],
        o["loss"], o["rank"], o["event_key"],
    ))


def replay(mode: str, family_of, events) -> dict[str, Any]:
    """canonical 연속 재생 — anchor 별 독립 실행이 아니다."""
    headline_history: dict[str, list[str]] = collections.defaultdict(list)
    good_history: dict[str, list[str]] = collections.defaultdict(list)
    stats: collections.Counter = collections.Counter()
    rows_out: list[dict[str, Any]] = []
    day = DAILY_ROLLING_AUDIT_CONTRACT_V1.origin
    while day <= _LAST:
        ctx = M.build_day_context(day)
        raw_sel: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
        pending: dict[str, dict[str, Any]] = {}
        intended: dict[str, str] = {}
        for idx, ilju in enumerate(_ILJUS):
            stem, branch = ganzi_from_index(idx)
            seed = f"{day.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
            scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
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
            window = tuple(headline_history[ilju][-_LOOKBACK:])
            families = {family_of.get(k, k) for k in window}
            deficit = (
                C10_POLICY.coverage_floor is not None
                and len(families) < C10_POLICY.coverage_floor
            )
            clean = repeat_severity(good_history[ilju], raw_key) == SEVERITY_CLEAN
            chosen = None
            if mode != "S0" and deficit and clean:
                options = _safe_candidates(
                    scored, seed, events, ranked, raw_key, raw_p, window, family_of
                )
                stats["rows_with_options"] += bool(options)
                chosen = _pick(mode, options)
            if chosen is not None:
                stats["selected"] += 1
                stats["immediate_threshold_gain"] += chosen["fam_qual"] > 0
                stats["coverage_only_gain"] += chosen["fam_qual"] == 0
                g, c, s = chosen["slots"]
                cands = chosen["cands"]
                intended[ilju] = chosen["event_key"]
                pending[ilju] = {
                    "expected_family": chosen["preboard_family"],
                    "fam_qual": chosen["fam_qual"],
                }
            else:
                rep = select_good_representative(
                    goods, good_history[ilju], _BUDGET, policy=C10_POLICY,
                    family_of=family_of, headline_history=headline_history[ilju],
                )
                g, c, s = M._select_slots(
                    scored, seed, good_override=rep.display_good_representative
                )
                cands = M._headline_candidates(g, s, c, M._band(g, c))
                intended[ilju] = rep.display_good_representative
            cmap[ilju] = [
                HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
            ]
            raw_sel[ilju] = cmap[ilju][0]
            good_history[ilju].append(intended[ilju])
            rows_out.append({
                "fortune_date": day.isoformat(), "ilju": ilju,
                "final_headline": None,
            })
        result = select_board(
            raw_sel, cmap, headline_history,
            domain_cap=DAILY_BOARD_CONTRACT_V1.domain_cap_count,
            event_cap=DAILY_BOARD_CONTRACT_V1.event_cap_count,
            max_displacement_cost=_BUDGET, policy=_BOARD, today=day.toordinal(),
        )
        base = len(rows_out) - len(raw_sel)
        for offset, ilju in enumerate(i for i in _ILJUS if i in raw_sel):
            sel = result.selections[ilju]
            rows_out[base + offset]["final_headline"] = sel.event_key
            fam = family_of.get(sel.event_key, sel.event_key)
            if ilju in pending:
                if fam != pending[ilju]["expected_family"]:
                    stats["board_erased_gain"] += 1
                elif pending[ilju]["fam_qual"] > 0:
                    stats["threshold_gain_survived_board"] += 1
            headline_history[ilju].append(sel.event_key)
        day += dt.timedelta(days=1)
    return {"rows": rows_out, "stats": dict(stats)}


def run() -> dict[str, Any]:
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    events = M.load_daily_dicts().catalog["events"]
    domain_of = {k: e["domain"] for k, e in events.items()}
    contract = derive_diagnostic_contract(
        anchor_days=(_LAST - dt.date(2026, 1, 1)).days + 1
    )

    out: dict[str, Any] = {}
    for mode in MODES:
        res = replay(mode, family_of, events)
        agg = build_rolling_audit_aggregates(
            res["rows"], family_of, domain_of, contract
        )
        by = {a["anchor_date"]: a for a in agg["anchors"]}
        fam_q = agg["family_qualifying_count_by_anchor"]
        out[mode] = {
            "stats": res["stats"],
            "anchors": {
                iso: {
                    "family_p10": by[iso]["family_p10"],
                    "family_qualifying": fam_q[iso],
                    "key_p10": by[iso]["key_p10"],
                    "key_below_15": by[iso]["count_below_15"],
                    "domain_p10": by[iso]["domain_p10"],
                }
                for iso in ANCHORS
            },
        }
    s0 = out["S0"]["anchors"]
    verdict = {}
    for mode in ("B1", "B2", "B3"):
        a = out[mode]["anchors"]
        verdict[mode] = {
            "family_gate_all": all(
                a[i]["family_p10"] >= 15 and a[i]["family_qualifying"] >= 55
                for i in ANCHORS
            ),
            "no_regression": all(
                a[i]["family_qualifying"] >= s0[i]["family_qualifying"]
                and a[i]["key_p10"] >= s0[i]["key_p10"]
                and a[i]["key_below_15"] <= s0[i]["key_below_15"]
                for i in ANCHORS
            ),
        }
    return {
        "audit_id": "OA-11f-B",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "selector_id": SELECTOR_ID,
        "loss_contract": {
            "global_loss_budget": _BUDGET,
            "marginal_diversity_loss_limit": _DIVERSITY_LOSS_LIMIT,
            "single_change_from_r7": "loss <= 7 → loss <= 6 (그 외 전부 동일)",
        },
        "note": (
            "SAFETY_BLOCKED 후보는 어떤 모드에서도 쓰지 않는다. B3 는 lookahead 를 "
            "쓰지 않으므로 참 상한이 아니라 로컬 낙관 경계다."
        ),
        "modes": out,
        "verdict": verdict,
    }


if __name__ == "__main__":
    r = run()
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11f_b_online_replay_r6.json"
    out.write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    for mode in MODES:
        m = r["modes"][mode]
        print(f"  {mode}  {m['stats']}")
        for iso, a in m["anchors"].items():
            print(f"      {iso} family {a['family_p10']}/{a['family_qualifying']} "
                  f"key {a['key_p10']}/{a['key_below_15']}")
    print("  판정:", r["verdict"])
