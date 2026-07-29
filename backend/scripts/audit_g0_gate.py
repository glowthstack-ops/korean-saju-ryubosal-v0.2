"""OA-9c — G0 불리 발현 게이트 shadow 감사 (측정 전용, 라이브 불변).

두 money caution 사건(`overspend_caution`·`lend_money_caution`)을 **동시에** 게이트한
보드를 만들어 기준 보드와 비교한다. 하나만 막으면 같은 편재 근거를 쓰는 다른 사건으로
승자가 옮겨가 효과를 잘못 재게 된다(OA-9a 실측: 223건 이전).

측정 축
    A 의미론적 정확성   게이트가 계약대로 작동하는가
    B 421장 재검증      OA-9a 코호트에서 무엇이 달라졌는가
    C 보존율            정상적인 경고까지 지우지는 않는가
    D 전체 구조         독점이 다른 사건으로 옮겨가지 않는가
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import statistics
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import saju_engines.daily_g0_shadow as G  # noqa: E402
import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402
from saju_shared_types.constants import ten_god  # noqa: E402
from saju_shared_types.enums import Branch, Stem  # noqa: E402

START, DAYS = dt.date(2026, 7, 1), 90
_TARGETS = G.g0_target_keys()


def _tg_name(a: Stem, b: Stem) -> str:
    return "비견" if a == b else ten_god(a, b).value


def _board_pass(scored_by_ilju: dict[str, list], day: dt.date) -> dict[str, Any]:
    """라이브 2패스(슬롯 선발 → 보드 캡)를 그대로 재현한다."""
    slot_rows, candidates, order = {}, {}, []
    for ilju, scored in scored_by_ilju.items():
        seed = f"{day.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
        good, caution, support = M._select_slots(scored, seed)
        band = M._band(good, caution)
        slot_rows[ilju] = (good, caution, support, band)
        candidates[ilju] = M._headline_candidates(good, support, caution, band)
        order.append(ilju)
    headline_pick, _reasons, _unresolved = M._rebalance_headlines(
        candidates, order, M._DOMAIN_HEADLINE_CAP
    )
    return {"slots": slot_rows, "headline": headline_pick}


def run() -> dict[str, Any]:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]

    # ── A 의미론적 정확성 ──
    violation_no_provenance = 0
    violation_cause_overlap = 0
    violation_cross_domain = 0
    selected_without_provenance = 0
    ungated_selection_without_adverse = 0

    # ── B 421장 코호트(OA-9a 정의: 일진 천간 편재 + 일지 불리 관계 없음) ──
    cohort_cards = 0
    cohort_raw_caution = collections.Counter()
    cohort_new_caution = collections.Counter()
    cohort_eligibility = collections.Counter()
    cohort_raw_prob_match = 0

    # ── C 보존율 ──
    with_adverse_cards = collections.Counter()   # 대상 사건별: 독립 근거가 있던 카드 수
    kept_caution = collections.Counter()          # 그중 caution 슬롯을 유지한 수
    raw_top3 = collections.Counter()
    eff_top3 = collections.Counter()
    raw_headline = collections.Counter()
    eff_headline = collections.Counter()
    gate_code_hist = collections.Counter()
    blocked_cards = collections.Counter()

    # ── D 전체 구조 ──
    base_caution_domain = collections.Counter()
    gate_caution_domain = collections.Counter()
    base_caution_event = collections.Counter()
    gate_caution_event = collections.Counter()
    base_headline_event = collections.Counter()
    gate_headline_event = collections.Counter()
    base_headline_domain = collections.Counter()
    gate_headline_domain = collections.Counter()
    replacement = collections.Counter()           # 막힌 자리를 누가 이어받았나
    replacement_money = collections.Counter()      # 그중 money 도메인
    replacement_wealth_lifted = collections.Counter()  # 그중 재성 양수를 받는 caution
    pyeonjae_all_money_top3_base = 0
    pyeonjae_all_money_top3_gate = 0
    pyeonjae_cards = 0
    no_eligible_caution = 0
    support_fallback = 0
    base_hist: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    gate_hist: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)

    taxonomy = G.load_taxonomy()["events"]
    wealth_lifted_cautions = {
        k for k, t in taxonomy.items() if t["g0_candidate"]
    }

    for i in range(DAYS):
        day = START + dt.timedelta(days=i)
        ctx = M.build_day_context(day)
        day_stem = Stem(ctx.day_stem)
        day_branch = Branch(ctx.day_branch)
        month_branch = Branch(ctx.month_branch)
        year_branch = Branch(ctx.year_branch)

        base_scored: dict[str, list] = {}
        gate_scored: dict[str, list] = {}
        per_card: dict[str, dict] = {}

        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            scored, survivors, decisions = G.evaluate_card(events, stem, branch, ctx)
            base_scored[ilju] = list(scored.values())
            gate_scored[ilju] = survivors

            provenance = G.money_adverse_evidence(stem, branch, ctx)
            per_card[ilju] = {
                "stem": stem, "branch": branch, "decisions": decisions,
                "provenance": provenance,
                "tg": _tg_name(stem, day_stem),
                "adverse_rel": any(
                    M._branch_relations(
                        day_branch, branch, (month_branch, year_branch)
                    ).get(k, 0.0) for k in G.ADVERSE_RELATIONS
                ),
            }

            # A — 근거 계약 검증
            for ev in provenance:
                if ev.domain_relevance != "money":
                    violation_cross_domain += 1
                if ev.cause_group not in (G.WEALTH_CONTENTION, G.WEALTH_BRANCH_CONFLICT):
                    violation_cause_overlap += 1
            for key, d in decisions.items():
                gate_code_hist[d.gate_codes[0] if d.gate_codes else "ELIGIBLE"] += 1
                if not d.caution_slot_eligible:
                    blocked_cards[key] += 1
                if d.caution_slot_eligible and d.subject_activated and not provenance:
                    violation_no_provenance += 1

            order = sorted(scored.values(), key=lambda s: -s.probability)
            top3 = {s.event_key for s in order[:3]}
            for key in _TARGETS:
                if key in top3:
                    raw_top3[key] += 1

        base = _board_pass(base_scored, day)
        gate = _board_pass(gate_scored, day)

        for ilju, card in per_card.items():
            b_good, b_caution, b_support, _bb = base["slots"][ilju]
            g_good, g_caution, g_support, _gb = gate["slots"][ilju]
            b_head = base["headline"][ilju]
            g_head = gate["headline"][ilju]
            decisions = card["decisions"]
            provenance = card["provenance"]

            base_caution_domain[b_caution.domain] += 1
            gate_caution_domain[g_caution.domain] += 1
            base_caution_event[b_caution.event_key] += 1
            gate_caution_event[g_caution.event_key] += 1
            base_headline_event[b_head.event_key] += 1
            gate_headline_event[g_head.event_key] += 1
            base_headline_domain[b_head.domain] += 1
            gate_headline_domain[g_head.domain] += 1
            base_hist[ilju][b_head.event_key] += 1
            gate_hist[ilju][g_head.event_key] += 1

            for key in _TARGETS:
                if b_caution.event_key == key:
                    if not provenance:
                        ungated_selection_without_adverse += 1
                if g_caution.event_key == key:
                    eff_top3[key] += 1
                    if not provenance:
                        selected_without_provenance += 1
                if g_head.event_key == key:
                    eff_headline[key] += 1
                if b_head.event_key == key:
                    raw_headline[key] += 1

            # C 보존율 — 독립 근거가 있던 카드에서 유지되는가
            for key, d in decisions.items():
                if d.subject_activated and provenance:
                    with_adverse_cards[key] += 1
                    if g_caution.event_key == key:
                        kept_caution[key] += 1

            # 대체 추적 — 막혔고 실제로 기준 보드에서 그 사건이 주의 슬롯이었던 경우
            blocked_now = {k for k, d in decisions.items() if not d.caution_slot_eligible}
            if b_caution.event_key in blocked_now and g_caution.event_key != b_caution.event_key:
                replacement[g_caution.event_key] += 1
                if g_caution.domain == "money":
                    replacement_money[g_caution.event_key] += 1
                if g_caution.event_key in wealth_lifted_cautions:
                    replacement_wealth_lifted[g_caution.event_key] += 1
            if not any(s.valence == "caution" for s in gate_scored[ilju]):
                no_eligible_caution += 1
            if g_caution.valence != "caution":
                support_fallback += 1

            # B 421장 코호트
            if card["tg"] == "편재" and not card["adverse_rel"]:
                cohort_cards += 1
                cohort_raw_caution[b_caution.event_key] += 1
                cohort_new_caution[g_caution.event_key] += 1
                for key, d in decisions.items():
                    cohort_eligibility[
                        f"{key}:{'eligible' if d.caution_slot_eligible else 'blocked'}"
                    ] += 1
                    if d.raw_probability == M._score_event(
                        key, events[key], card["stem"], card["branch"], ctx
                    ).probability:
                        cohort_raw_prob_match += 1

            # D 편재 카드에서 상위 3칸 전부 money 인 비율
            if card["tg"] == "편재":
                pyeonjae_cards += 1
                b_order = sorted(base_scored[ilju], key=lambda s: -s.probability)[:3]
                g_order = sorted(gate_scored[ilju], key=lambda s: -s.probability)[:3]
                if all(s.domain == "money" for s in b_order):
                    pyeonjae_all_money_top3_base += 1
                if all(s.domain == "money" for s in g_order):
                    pyeonjae_all_money_top3_gate += 1

    cards = DAYS * 60

    def _p90_max(hist: dict[str, collections.Counter]) -> dict[str, float]:
        tops = [c.most_common(1)[0][1] for c in hist.values()]
        tops.sort()
        return {
            "p90_pct": round(tops[int(len(tops) * 0.9) - 1] / DAYS * 100, 1),
            "max_pct": round(max(tops) / DAYS * 100, 1),
            "mean_pct": round(statistics.mean(tops) / DAYS * 100, 1),
        }

    return {
        "cards": cards,
        "contract_version": G.G0_CONTRACT_VERSION,
        "gated_events": list(_TARGETS),
        "A_semantic_accuracy": {
            "selected_without_adverse_provenance": selected_without_provenance,
            "eligible_without_provenance": violation_no_provenance,
            "cause_group_outside_contract": violation_cause_overlap,
            "cross_domain_evidence": violation_cross_domain,
            "baseline_selections_without_adverse": ungated_selection_without_adverse,
            "note": "앞의 네 값은 모두 0 이어야 한다. 마지막 값은 게이트 이전 기준선 —"
                    " 독립 근거 없이 노출되던 카드 수이며 이번 슬라이스가 없애려는 대상이다.",
        },
        "B_cohort_no_adverse_relation": {
            "cards": cohort_cards,
            "raw_probability_preserved": cohort_raw_prob_match == cohort_cards * len(_TARGETS),
            "eligibility": dict(sorted(cohort_eligibility.items())),
            "baseline_caution_winners": dict(cohort_raw_caution.most_common(8)),
            "gated_caution_winners": dict(cohort_new_caution.most_common(8)),
        },
        "C_preservation": {
            key: {
                "cards_with_independent_adverse": with_adverse_cards[key],
                "kept_in_caution_slot": kept_caution[key],
                "blocked_cards": blocked_cards[key],
                "raw_top3": raw_top3[key],
                "effective_caution_slot": eff_top3[key],
                "raw_headline": raw_headline[key],
                "effective_headline": eff_headline[key],
            }
            for key in _TARGETS
        },
        "C_gate_codes": dict(gate_code_hist.most_common()),
        "D_structure": {
            "caution_domain_base": dict(base_caution_domain.most_common()),
            "caution_domain_gated": dict(gate_caution_domain.most_common()),
            "caution_event_base": dict(base_caution_event.most_common(8)),
            "caution_event_gated": dict(gate_caution_event.most_common(8)),
            "distinct_caution_events_base": len(base_caution_event),
            "distinct_caution_events_gated": len(gate_caution_event),
            "headline_domain_base": dict(base_headline_domain.most_common()),
            "headline_domain_gated": dict(gate_headline_domain.most_common()),
            "distinct_headline_events_base": len(base_headline_event),
            "distinct_headline_events_gated": len(gate_headline_event),
            "pyeonjae_cards": pyeonjae_cards,
            "pyeonjae_all_money_top3_base_pct": round(
                pyeonjae_all_money_top3_base / max(1, pyeonjae_cards) * 100, 1),
            "pyeonjae_all_money_top3_gated_pct": round(
                pyeonjae_all_money_top3_gate / max(1, pyeonjae_cards) * 100, 1),
            "no_eligible_caution_cards": no_eligible_caution,
            "support_fallback_cards": support_fallback,
            "longitudinal_headline_base": _p90_max(base_hist),
            "longitudinal_headline_gated": _p90_max(gate_hist),
        },
        "E_displacement": {
            "replacements": dict(replacement.most_common(10)),
            "money_domain_replacements": dict(replacement_money.most_common(10)),
            "wealth_lifted_replacements": dict(replacement_wealth_lifted.most_common(10)),
            "note": "wealth_lifted_replacements 는 재성 양수를 받는 caution(= 구조상 G0"
                    " 대상)이 자리를 이어받은 수다. 여기 document 3종이 크게 나오면"
                    " deferred 범위가 효과를 흡수하고 있다는 뜻이다.",
        },
    }


if __name__ == "__main__":
    data = {
        "audit_id": "OA-9c",
        "policy_status": "shadow_only",
        "live_behavior_changed": False,
        "days": DAYS,
        "result": run(),
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa9c_g0_gate_90d.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
