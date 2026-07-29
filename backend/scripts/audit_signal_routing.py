"""OA-9a — 신호→사건 라우팅 감사 (측정 전용, 라이브 불변).

OA-7c-S3 가 남긴 질문: 왜 편재 affinity 를 17% 내려도 money 독점이 거의 안 움직이고,
비워진 자리를 같은 도메인의 `overspend_caution` 이 채우는가.

가설: **한 명리 신호가 같은 도메인의 여러 사건에 복제되어 여러 장의 후보표를 만든다.**
이 스크립트는 그 구조를 세 층으로 나눠 센다.

    A 정적 fan-out    사전만 보고 — 한 신호가 몇 장의 후보를 만드는가
    B 런타임 전환     그 후보표가 실제 상위권으로 전환되는가
    C 극성 게이트     같은 신호가 양극(혜택·경고) 사건을 동시에 올리는가

감사 지표(새 점수 공식이 아니다 — 구조 비교용):

    effective_ticket_count(signal, domain)
        해당 신호에서 양의 기여를 받고 **헤드라인 자격이 있는** 사건 수
    activation_mass(signal, domain)
        각 사건의 양의 affinity × expr_confidence 합
"""

from __future__ import annotations

import collections
import copy
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

import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402
from saju_shared_types.constants import ten_god  # noqa: E402
from saju_shared_types.enums import Branch, Stem  # noqa: E402

START, DAYS = dt.date(2026, 7, 1), 90

#: 불리 관계 — 과다·충돌 조건. 극성 게이트 판정의 기준선이다.
_ADVERSE_RELATIONS = ("clash", "punishment", "break", "harm")
#: 극성 게이트를 집중 추적할 사건(사용자 지정 + 편재를 받는 나머지 money 사건).
_POLARITY_TARGET = "overspend_caution"


def _tg_name(a: Stem, b: Stem) -> str:
    return "비견" if a == b else ten_god(a, b).value


def _headline_slots(event: dict[str, Any]) -> list[str]:
    return list(event.get("headline_slots") or event["slots"])


# ── A. 정적 fan-out ────────────────────────────────────────────────────────


def static_fanout(events: dict[str, dict]) -> dict[str, Any]:
    """사전만 보고 산출하는 신호별 후보 생성 구조.

    Args:
        events: 사건 카탈로그(`catalog["events"]`).

    Returns:
        십성별 요약 + (십성 × 도메인) 매트릭스.
    """
    all_tg = sorted({tg for e in events.values() for tg in (e.get("ten_god_affinity") or {})})
    matrix: dict[str, dict[str, Any]] = {}
    summary: dict[str, Any] = {}

    for tg in all_tg:
        by_domain: dict[str, dict[str, Any]] = {}
        for key, e in sorted(events.items()):
            aff = (e.get("ten_god_affinity") or {}).get(tg, 0.0)
            if aff <= 0:
                continue
            d = by_domain.setdefault(
                e["domain"],
                {"fanout": 0, "effective_ticket_count": 0, "activation_mass": 0.0,
                 "affinity_sum": 0.0, "affinity_max": 0.0,
                 "good_active": 0, "caution_active": 0, "events": []},
            )
            d["fanout"] += 1
            d["affinity_sum"] += aff
            d["affinity_max"] = max(d["affinity_max"], aff)
            d["activation_mass"] += aff * float(e["expr_confidence"])
            if "good" in _headline_slots(e):
                d["effective_ticket_count"] += 1
            if e["valence"] == "caution":
                d["caution_active"] += 1
            else:
                d["good_active"] += 1
            d["events"].append(f"{key}({aff})")

        for d in by_domain.values():
            d["affinity_sum"] = round(d["affinity_sum"], 3)
            d["activation_mass"] = round(d["activation_mass"], 3)

        matrix[tg] = dict(sorted(by_domain.items(), key=lambda x: -x[1]["activation_mass"]))
        summary[tg] = {
            "fanout": sum(d["fanout"] for d in by_domain.values()),
            "effective_ticket_count": sum(
                d["effective_ticket_count"] for d in by_domain.values()),
            "activation_mass": round(
                sum(d["activation_mass"] for d in by_domain.values()), 3),
            "affinity_max": max((d["affinity_max"] for d in by_domain.values()), default=0.0),
            "domains": len(by_domain),
            "good_active": sum(d["good_active"] for d in by_domain.values()),
            "caution_active": sum(d["caution_active"] for d in by_domain.values()),
            # 같은 신호가 양극 사건을 동시에 올리는가 — 극성 게이트 부재 지표
            "bipolar_domains": sorted(
                dm for dm, d in by_domain.items()
                if d["good_active"] and d["caution_active"]
            ),
            "top_domain": max(
                by_domain.items(), key=lambda x: x[1]["activation_mass"])[0]
            if by_domain else None,
            "top_domain_mass_share_pct": round(
                max(d["activation_mass"] for d in by_domain.values())
                / sum(d["activation_mass"] for d in by_domain.values()) * 100, 1)
            if by_domain else 0.0,
        }

    return {
        "by_ten_god": dict(sorted(summary.items(), key=lambda x: -x[1]["activation_mass"])),
        "matrix": matrix,
    }


# ── C. 극성 게이트 변형 사전 ───────────────────────────────────────────────


def _without_ten_god(event: dict[str, Any], tg: str) -> dict[str, Any]:
    """특정 십성 기여만 제거한 사건 사본(반사실용)."""
    e = copy.deepcopy(event)
    e["ten_god_affinity"].pop(tg, None)
    return e


def _without_adverse_relations(event: dict[str, Any]) -> dict[str, Any]:
    """불리 관계(충·형·파·해) 기여만 제거한 사건 사본(반사실용)."""
    e = copy.deepcopy(event)
    for k in _ADVERSE_RELATIONS:
        e["relation_affinity"].pop(k, None)
    return e


def run() -> dict[str, Any]:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    money_keys = sorted(k for k, e in events.items() if e["domain"] == "money")

    target = events[_POLARITY_TARGET]
    variants = {
        "Z0_baseline": target,
        "Z1_no_pyeonjae": _without_ten_god(target, "편재"),
        "Z2_no_adverse_relation": _without_adverse_relations(target),
    }

    # ── 런타임 집계 ──
    cards_by_tg = collections.Counter()
    top3_by_tg: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    top1_by_tg: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    # 도메인 단위: 한 신호 조건에서 상위 3위 안에 든 사건의 도메인 분포
    top3_domain_by_tg: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter)

    # money 사건별 조건부 지표
    money_prob: dict[str, dict[str, list[int]]] = {
        k: collections.defaultdict(list) for k in money_keys
    }
    money_top3: dict[str, collections.Counter] = {
        k: collections.Counter() for k in money_keys
    }

    # 극성 게이트 반사실
    var_prob: dict[str, list[int]] = {v: [] for v in variants}
    var_top3: collections.Counter = collections.Counter()
    var_caution_win: collections.Counter = collections.Counter()
    #: 실제 카드에 표시된 주의 사건(슬롯 선발 결과) — 원시 1위와 반드시 구분한다.
    var_displayed: collections.Counter = collections.Counter()
    # 편재만 있고 불리 신호가 전혀 없는 카드에서의 거동
    pure_pyeonjae_cards = 0
    pure_pyeonjae_top3 = 0
    pure_pyeonjae_caution_win = 0
    pure_pyeonjae_displayed = 0
    pure_displayed_caution: collections.Counter = collections.Counter()
    pure_pyeonjae_prob: list[int] = []
    #: 같은 코호트에서 편재 기여만 뺐을 때 — 100% 승리가 '불리 게이트 사건이 함께
    #: 억제된 탓'인지 '편재 단독 부양' 탓인지 가르는 유일한 대조군이다.
    pure_z1_caution_win = 0
    pure_z1_prob: list[int] = []
    pure_z1_replacement = collections.Counter()
    #: 상위 3칸을 한 도메인이 몇 칸 차지하는가(신호별 복제 강도)
    top3_money_slots_by_tg: dict[str, list[int]] = collections.defaultdict(list)

    for i in range(DAYS):
        ctx = M.build_day_context(START + dt.timedelta(days=i))
        day_stem = Stem(ctx.day_stem)
        day_branch = Branch(ctx.day_branch)
        month_branch = Branch(ctx.month_branch)
        year_branch = Branch(ctx.year_branch)

        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            tg = _tg_name(stem, day_stem)
            cards_by_tg[tg] += 1

            scored = {k: M._score_event(k, e, stem, branch, ctx) for k, e in events.items()}
            order = sorted(scored.values(), key=lambda s: -s.probability)
            for r, s in enumerate(order[:3], 1):
                top3_by_tg[tg][s.event_key] += 1
                top3_domain_by_tg[tg][s.domain] += 1
                if r == 1:
                    top1_by_tg[tg][s.event_key] += 1

            top3_keys = {s.event_key for s in order[:3]}
            for k in money_keys:
                money_prob[k][tg].append(scored[k].probability)
                if k in top3_keys:
                    money_top3[k][tg] += 1

            # ── 극성 게이트 ──
            rel = M._branch_relations(day_branch, branch, (month_branch, year_branch))
            adverse = any(rel.get(r, 0.0) for r in _ADVERSE_RELATIONS)
            cautions = [s for s in order if s.valence == "caution"]
            #: **원시 주의 1위** — 점수만으로 매긴 순위다. 실제 카드에 표시되는 주의
            #: 사건과 다르다: `_select_slots` 는 주의를 가급적 good 과 **다른 도메인**
            #: 에서 뽑기 때문에, good 이 money 인 카드에서는 money 주의가 밀려난다.
            #: 두 값을 함께 내야 "점수 구조의 문제"와 "노출의 문제"가 섞이지 않는다.
            caution_rank1 = cautions[0].event_key if cautions else None
            seed = (f"{ctx.the_date.isoformat()}|{stem.value}{branch.value}"
                    f"|{M.EVENT_SELECTION_COMPAT_SALT}")  # 라이브와 동일 seed
            displayed_caution = M._select_slots(list(scored.values()), seed)[1].event_key

            for name, ev in variants.items():
                p = M._score_event(_POLARITY_TARGET, ev, stem, branch, ctx).probability
                var_prob[name].append(p)
            if _POLARITY_TARGET in top3_keys:
                var_top3["Z0_baseline"] += 1
            if caution_rank1 == _POLARITY_TARGET:
                var_caution_win["Z0_baseline"] += 1
            if displayed_caution == _POLARITY_TARGET:
                var_displayed["Z0_baseline"] += 1

            # 변형 사전으로 재정렬해 실제 순위 변화를 본다
            for name in ("Z1_no_pyeonjae", "Z2_no_adverse_relation"):
                alt = dict(scored)
                alt[_POLARITY_TARGET] = M._score_event(
                    _POLARITY_TARGET, variants[name], stem, branch, ctx)
                alt_order = sorted(alt.values(), key=lambda s: -s.probability)
                if _POLARITY_TARGET in {s.event_key for s in alt_order[:3]}:
                    var_top3[name] += 1
                alt_cautions = [s for s in alt_order if s.valence == "caution"]
                if alt_cautions and alt_cautions[0].event_key == _POLARITY_TARGET:
                    var_caution_win[name] += 1

            top3_money_slots_by_tg[tg].append(
                sum(1 for s in order[:3] if s.domain == "money"))

            if tg == "편재" and not adverse:
                pure_pyeonjae_cards += 1
                pure_pyeonjae_prob.append(scored[_POLARITY_TARGET].probability)
                if _POLARITY_TARGET in top3_keys:
                    pure_pyeonjae_top3 += 1
                if caution_rank1 == _POLARITY_TARGET:
                    pure_pyeonjae_caution_win += 1
                if displayed_caution == _POLARITY_TARGET:
                    pure_pyeonjae_displayed += 1
                pure_displayed_caution[displayed_caution] += 1
                z1 = M._score_event(
                    _POLARITY_TARGET, variants["Z1_no_pyeonjae"], stem, branch, ctx)
                pure_z1_prob.append(z1.probability)
                z1_cautions = sorted(
                    [s for s in scored.values() if s.valence == "caution"
                     and s.event_key != _POLARITY_TARGET] + [z1],
                    key=lambda s: -s.probability,
                )
                if z1_cautions[0].event_key == _POLARITY_TARGET:
                    pure_z1_caution_win += 1
                else:
                    pure_z1_replacement[z1_cautions[0].event_key] += 1

    cards = DAYS * 60

    runtime = {}
    for tg, n in cards_by_tg.most_common():
        t3, t1 = top3_by_tg[tg], top1_by_tg[tg]
        runtime[tg] = {
            "cards": n,
            "distinct_top3_events": len(t3),
            "distinct_top1_events": len(t1),
            "top3_domains": dict(top3_domain_by_tg[tg].most_common()),
            "top3_domain_share_pct": round(
                max(top3_domain_by_tg[tg].values()) / (n * 3) * 100, 1) if n else 0.0,
            "top1_events": dict(t1.most_common(5)),
        }

    money_detail = {}
    for k in money_keys:
        e = events[k]
        by_tg = {
            tg: {
                "mean_probability": round(statistics.mean(ps), 1),
                "top3_pct": round(money_top3[k][tg] / len(ps) * 100, 1),
            }
            for tg, ps in sorted(money_prob[k].items())
            if len(ps) >= 60
        }
        money_detail[k] = {
            "valence": e["valence"],
            "slots": e["slots"],
            "headline_slots": _headline_slots(e),
            "synonym_group": e.get("synonym_group"),
            "base_weight": e["base_weight"],
            "expr_confidence": e["expr_confidence"],
            "pyeonjae_affinity": (e.get("ten_god_affinity") or {}).get("편재", 0.0),
            "adverse_relation_affinity": {
                r: e["relation_affinity"].get(r, 0.0) for r in _ADVERSE_RELATIONS
            },
            "top3_pct_overall": round(sum(money_top3[k].values()) / cards * 100, 1),
            "by_ten_god": by_tg,
        }

    polarity = {
        "target": _POLARITY_TARGET,
        "question": "편재라는 이유만으로 상승하는가, 별도 과다·충돌 조건이 필요한가",
        "variants": {
            name: {
                "mean_probability": round(statistics.mean(ps), 2),
                "top3_cards": var_top3[name],
                "top3_pct": round(var_top3[name] / cards * 100, 1),
                "raw_caution_rank1_cards": var_caution_win[name],
                "raw_caution_rank1_pct": round(var_caution_win[name] / cards * 100, 1),
                "displayed_caution_cards": var_displayed[name] or None,
            }
            for name, ps in var_prob.items()
        },
        "pure_pyeonjae_no_adverse": {
            "cards": pure_pyeonjae_cards,
            "mean_probability": round(statistics.mean(pure_pyeonjae_prob), 1)
            if pure_pyeonjae_prob else None,
            "top3_cards": pure_pyeonjae_top3,
            "top3_pct": round(pure_pyeonjae_top3 / pure_pyeonjae_cards * 100, 1)
            if pure_pyeonjae_cards else 0.0,
            "raw_caution_rank1_cards": pure_pyeonjae_caution_win,
            "raw_caution_rank1_pct": round(
                pure_pyeonjae_caution_win / pure_pyeonjae_cards * 100, 1)
            if pure_pyeonjae_cards else 0.0,
            "displayed_caution_cards": pure_pyeonjae_displayed,
            "displayed_caution_winners": dict(pure_displayed_caution.most_common(6)),
            "note": "일지 기준 불리 관계(충·형·파·해)가 없는 편재 카드. **원시 주의 1위**와 "
                    "**실제 표시된 주의**는 다르다 — 슬롯 선발이 주의를 good 과 다른 "
                    "도메인에서 뽑으므로, good 이 money 인 카드에서는 money 주의가 표시되지 "
                    "않는다. 점수 구조의 문제(원시 1위)와 노출의 문제(표시)를 섞지 말 것. "
                    "또한 이 코호트는 '불리 근거가 전혀 없는' 집합이 아니다 — 비겁이나 "
                    "월지·연지발 충형은 여기서 걸러지지 않는다(OA-9c 에서 392/421 이 "
                    "독립 근거 보유로 확인됐다).",
        },
        "pure_cohort_without_pyeonjae": {
            "cards": pure_pyeonjae_cards,
            "mean_probability": round(statistics.mean(pure_z1_prob), 1)
            if pure_z1_prob else None,
            "raw_caution_rank1_cards": pure_z1_caution_win,
            "raw_caution_rank1_pct": round(
                pure_z1_caution_win / pure_pyeonjae_cards * 100, 1)
            if pure_pyeonjae_cards else 0.0,
            "replaced_by": dict(pure_z1_replacement.most_common(5)),
            "note": "같은 코호트에서 편재 기여만 제거한 대조군. 승률이 크게 떨어지면 "
                    "100% 승리는 '다른 주의 사건이 함께 억제된 탓'이 아니라 편재 단독 부양이다.",
        },
    }

    money_slot_share = {
        tg: {
            "mean_money_slots_in_top3": round(statistics.mean(v), 2),
            "cards_with_all_three_money_pct": round(
                sum(1 for n in v if n == 3) / len(v) * 100, 1),
        }
        for tg, v in sorted(
            top3_money_slots_by_tg.items(),
            key=lambda x: -statistics.mean(x[1]),
        )
    }

    return {
        "cards": cards,
        "A_static_fanout": static_fanout(events),
        "B_runtime_conversion": runtime,
        "C_money_events": money_detail,
        "C_polarity_gate": polarity,
        "C_money_slot_occupancy": money_slot_share,
    }


#: 측정값에서 곧바로 읽히는 판정(수치는 result 에 그대로 있다 — 여기서 재계산하지 않는다).
_VERDICT = {
    "fanout_confirmed": True,
    "fanout_evidence": (
        "편재 카드의 상위 3칸 중 평균 2.13칸이 money 이고 25.6% 는 3칸 전부 money 다. "
        "편재 조건에서 money_small_gain 93.9% · money_good_deal 69.3% · "
        "overspend_caution 48.0% 가 동시에 Top-3 에 든다 — 같은 신호가 세 장의 표를 만든다."
    ),
    "collapse_evidence": (
        "편재 조건에서 1위를 차지한 사건은 540카드 통틀어 2종뿐이다"
        "(money_small_gain 447 · overspend_caution 93). 정인 15종 · 식신 17종과 대비된다."
    ),
    "polarity_gate_missing": True,
    "polarity_evidence": (
        "일지 불리 관계(충·형·파·해)가 없는 편재 카드 421건에서 overspend_caution 이 "
        "**원시 주의 1위**를 100% 차지한다. 같은 코호트에서 편재 기여만 제거하면 5.0% 로 "
        "떨어지고 평균 확률도 65.1 → 41.7 로 내려간다 — 다른 주의 사건이 함께 억제된 탓이 "
        "아니라 편재 단독 부양이다. 전체 기준으로도 편재 제거(34.8→16.8%)가 불리 관계 "
        "제거(34.8→25.0%)보다 원시 주의 1위율을 더 크게 낮춘다."
    ),
    "polarity_scope_correction": (
        "원시 1위 != 사용자에게 표시된 주의다. 슬롯 선발이 주의를 good 과 다른 도메인에서 "
        "뽑으므로, good 이 money 인 카드에서는 money 주의가 밀려난다. 실측: 421건에서 "
        "**표시된 overspend_caution 은 0건**이고 자리는 guarantee_stamp_caution 등이 "
        "가져갔다. 이 코호트도 '불리 근거가 전혀 없는' 집합이 아니다 — 비겁·월지·연지발 "
        "충형은 걸러지지 않으며 OA-9c 에서 392/421 이 독립 근거 보유로 확인됐다. "
        "따라서 이 절의 수치는 **점수 구조의 결손**을 증명하되 노출 규모를 뜻하지 않는다."
    ),
    "polarity_conclusion": (
        "편재의 '활성'과 편재의 '과잉·손실 발현'이 사전 스키마에서 구분되지 않는다. "
        "affinity 수치 조정이 아니라 발현 조건 분기가 필요하다."
    ),
    "headline_ticket_starvation": (
        "move 도메인은 전 십성을 통틀어 effective_ticket_count 가 0 이다 — 어떤 신호로도 "
        "good 헤드라인 후보가 되지 못한다. document 3 · health 4 로 뒤를 잇는다. "
        "S3b 의 move Top1 0.0% 는 affinity 가 낮아서가 아니라 표가 없어서다."
    ),
    "mass_is_not_the_whole_story": (
        "social 은 activation_mass 9.04 · ticket 16 으로 money(9.11 · 8)와 질량이 거의 같지만 "
        "Top1 은 낮다. 차이는 질량이 아니라 단일 최댓값(편재 0.9)과 한 도메인 집중도"
        "(편재 money 45.6% · 정재 money 46.9%)에서 온다."
    ),
    "live_behavior_changed": False,
}

if __name__ == "__main__":
    data = {
        "audit_id": "OA-9a",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "days": DAYS,
        "verdict": _VERDICT,
        "result": run(),
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa9a_signal_routing_90d.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
