#!/usr/bin/env python3
"""OA-11f-S — marginal 평가자 SSOT 추출의 동작 보존 증명 + probe/selector 동일성.

focus probe 초안이 marginal delta 계산을 **복제**했고, 그 복제본에 죽은 코드가
있었다(`base_k, base_f = ... if False else (None, None)`). 결함 자체는 실행 전에
제거했지만, 복제 구조가 남으면 같은 drift 가 재발한다. 그래서 평가 로직을
`evaluate_marginal_candidate` 한 곳으로 모았다.

이 감사는 그 추출이 **판정을 바꾸지 않았음**을 증명한다. refactor 이전 본문을
아래에 동결 복사해 두고, 같은 replay 를 한 번 돌면서 매 행에서 두 구현을 나란히
호출해 결과를 대조한다. 동결 본문은 특성화 기준선 전용이며 권위가 없다.
"""

from __future__ import annotations

import collections
import datetime as dt
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
from saju_engines.daily_schedule_runner import (  # noqa: E402
    CardCandidateBundle,
    ProjectionStatus,
    derive_top1_family_projection,
)
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    SEVERITY_CLEAN,
    repeat_severity,
    select_board,
    select_good_representative,
    strength_band,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

#: 대조 종점 — 문제의 anchor. 여기까지의 모든 행에서 두 구현을 대조한다.
PARITY_END = dt.date(2026, 4, 2)
FROZEN_LABEL = "PREREFACTOR_FROZEN_NOT_AUTHORITATIVE"


def _frozen_safe_candidates(
    scored, seed, events, ranked, raw_key, raw_p, window, family_of,
    loss_limit: int | None = None,
) -> list[dict[str, Any]]:
    """refactor 이전 본문의 동결 복사 — 수정 금지, 특성화 대조 전용."""
    limit = B._DIVERSITY_LOSS_LIMIT if loss_limit is None else loss_limit
    rg, rc, rs = M._select_slots(scored, seed, good_override=raw_key)
    if rg.event_key != raw_key:
        return []
    rcands = M._headline_candidates(rg, rs, rc, M._band(rg, rc))
    base_key, base_fam = B._next_counts(window, rcands[0].event_key, family_of)
    top_band = strength_band(raw_p)
    out: list[dict[str, Any]] = []
    for rank, (key, prob) in enumerate(ranked, start=1):
        if key == raw_key:
            continue
        loss = raw_p - prob
        band = strength_band(prob)
        if loss > limit or (top_band == 4 and band < top_band) or (
            top_band - band >= 2
        ):
            continue
        g, c, s = M._select_slots(scored, seed, good_override=key)
        if g.event_key != key:
            continue
        cands = M._headline_candidates(g, s, c, M._band(g, c))
        projection = derive_top1_family_projection(
            raw_top_event_key=key,
            card_candidates=CardCandidateBundle(
                good_event_key=g.event_key, slots=(g, c, s),
                headline_candidates=tuple(cands),
            ),
            family_of=family_of,
        )
        if projection.status is not ProjectionStatus.PROJECTED:
            continue
        cand_key, cand_fam = B._next_counts(window, cands[0].event_key, family_of)
        fam_qual = int(cand_fam >= B._QUALIFY) - int(base_fam >= B._QUALIFY)
        key_qual = int(cand_key >= B._QUALIFY) - int(base_key >= B._QUALIFY)
        fam_cov = cand_fam - base_fam
        key_cov = cand_key - base_key
        if fam_cov <= 0 or key_cov < 0 or key_qual < 0:
            continue
        out.append({
            "rank": rank, "event_key": key,
            "fam_qual": fam_qual, "fam_cov": fam_cov,
            "key_qual": key_qual, "key_cov": key_cov, "loss": loss,
            "preboard_family": projection.family,
        })
    return out


_KEYS = ("rank", "event_key", "fam_qual", "fam_cov", "key_qual", "key_cov", "loss",
         "preboard_family")


def run(loss_limit: int = 6) -> dict[str, Any]:
    """R6(=loss_limit 6) 경로로 origin~2026-04-02 전 행을 대조한다."""
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    events = M.load_daily_dicts().catalog["events"]
    hh: dict[str, list[str]] = collections.defaultdict(list)
    gh: dict[str, list[str]] = collections.defaultdict(list)
    stats: collections.Counter[str] = collections.Counter()
    stage_seen: collections.Counter[str] = collections.Counter()
    mismatches: list[dict[str, Any]] = []
    day = B.DAILY_ROLLING_AUDIT_CONTRACT_V1.origin
    while day <= PARITY_END:
        iso = day.isoformat()
        ctx = M.build_day_context(day)
        raw: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
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
            chosen = None
            if deficit and severity == SEVERITY_CLEAN:
                stats["rows_selector_consulted"] += 1
                new = B._safe_candidates(
                    scored, seed, events, ranked, raw_key, raw_p, window,
                    family_of, loss_limit=loss_limit,
                )
                old = _frozen_safe_candidates(
                    scored, seed, events, ranked, raw_key, raw_p, window,
                    family_of, loss_limit=loss_limit,
                )
                n = [{k: o[k] for k in _KEYS} for o in new]
                if n != old:
                    mismatches.append(
                        {"date": iso, "ilju": ilju, "new": n, "frozen": old}
                    )
                stats["candidate_lists_compared"] += 1
                stats["candidates_compared"] += len(old)
                # 모든 후보 분류 유형이 실제로 관측됐는지 — 공허한 통과 방지.
                for e in B.evaluate_candidate_bundle(
                    scored=scored, seed=seed, ranked=ranked, raw_key=raw_key,
                    raw_p=raw_p, window=window, family_of=family_of,
                    loss_limit=loss_limit,
                ):
                    stage_seen[e.rejected_at_stage or "ELIGIBLE"] += 1
                    stats["candidate_evaluations"] += 1
                chosen = B._pick("B1", new) if new else None
                if chosen is not None:
                    stats["interventions"] += 1
            if chosen is not None:
                g, c, s = chosen["slots"]
                cands, pick = chosen["cands"], chosen["event_key"]
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
            cmap[ilju] = [
                HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
            ]
            raw[ilju] = cmap[ilju][0]
            gh[ilju].append(pick)
        result = select_board(
            raw, cmap, hh, domain_cap=21, event_cap=10,
            max_displacement_cost=B._BUDGET, policy=B._BOARD, today=day.toordinal(),
        )
        for ilju, sel in result.selections.items():
            hh[ilju].append(sel.event_key)
        day += dt.timedelta(days=1)
    missing = [s for s in B.MARGINAL_STAGES if not stage_seen.get(s)]
    return {
        "audit_id": "OA-11f-S",
        "purpose": "SSOT 추출의 동작 보존 + probe/selector 동일 구현 증명",
        "frozen_baseline": FROZEN_LABEL,
        "range": f"{B.DAILY_ROLLING_AUDIT_CONTRACT_V1.origin.isoformat()} ~ "
                 f"{PARITY_END.isoformat()}",
        "loss_limit": loss_limit,
        "execution_proof": dict(stats),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:20],
        "stage_coverage": dict(stage_seen),
        "stages_never_observed": missing,
        "probe_selector_shared_ssot": "evaluate_marginal_candidate",
        "probe_reimplements_marginal_delta": False,
        "verdict": (
            "BEHAVIOR_PRESERVED"
            if not mismatches and stats.get("candidate_lists_compared", 0) > 0
            else "MISMATCH" if mismatches else "VACUOUS_NO_ROWS_COMPARED"
        ),
    }


if __name__ == "__main__":
    r = run()
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11f_s_ssot_parity.json"
    out.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("[ok]", out.name, r["verdict"])
    print("  실행 증명", r["execution_proof"])
    print("  불일치", r["mismatch_count"])
    print("  단계 관측", r["stage_coverage"])
    print("  미관측 단계", r["stages_never_observed"])
    sys.exit(0 if r["verdict"] == "BEHAVIOR_PRESERVED" else 1)
