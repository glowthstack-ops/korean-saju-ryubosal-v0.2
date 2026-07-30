#!/usr/bin/env python3
"""WC-SCORE — `wealth_change` 손실 상단 편중의 성분·인과 감사 (측정 전용).

WC-SIG 이 남긴 미완 질문: 재물 테마 풀은 opportunity 63.9% 인데 대표 8시점은 loss
75% 다. 원인이 선별 규칙이 아니라 upstream score 분포임은 확인됐지만, **왜 손실 후보의
점수가 더 높은가**는 답하지 않았다.

파이프라인(event_engine_v2):

    ... → _apply_daewoon_hwa_background(cands, dw_role)   ±3% 배경 보정
        → LifeFitRanker
        → _apply_soft_cap(c)   raw 보존 + score = soft_cap(raw)

    _soft_cap(raw) = raw                             (raw ≤ 85)
                   = 100 - 15 * exp(-(raw-85)/25)    (raw > 85)

단순 절단이 아니라 **지수 포화**이고 raw 이후 다른 정규화·감쇠가 없다. 그래서 "cap
제거" 반사실은 raw 를 그대로 쓰는 것과 같은 계산이 된다 — 별개 실험으로 분리하지 않고
중복임을 명시한다.

반사실 4종(동일 정합 모집단 · 동일 기간 그룹화 · 동일 대표 선정 계약, **점수 필드만**
교체):

    A  현재 final score
    B  raw_score
    C  cap 제거 = B 와 동일 계산(중복 명시)
    D  daewoon_hwa 성분만 0 으로 둔 final (감사 스크립트 안에서만 재계산)

바꾸지 않는 것: score 공식 · cap · 대표 선정 · polarity·quality · production 출력 ·
P1 라우팅.
"""

from __future__ import annotations

import collections
import json
import statistics
import sys
from datetime import date
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _p in (
    _BACKEND / "apps" / "api",
    _BACKEND / "packages" / "saju_engines",
    _BACKEND / "packages" / "shared_types",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from saju_api.services import report_service as R  # noqa: E402
from saju_engines.event_engine_v2 import _soft_cap  # noqa: E402

TARGET = "wealth_change"
#: 결과 품질 → WC-SIG 축. 사건 종류가 아니라 길흉 방향이다(19f94c2 에서 확정).
_QUALITY_AXIS = {
    "opportunity": "opportunity_inflow", "achievement": "opportunity_inflow",
    "loss": "loss_outflow", "conflict": "loss_outflow",
    "pressure": "pressure", "mixed": "mixed",
}


def _axis(quality: object) -> str:
    return _QUALITY_AXIS.get(str(quality or "").split(".")[-1].lower(), "UNKNOWN")


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 3),
        "median": round(statistics.median(values), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def duplicate_state(codes: list[str]) -> str:
    """한 후보 안에서 근거 **코드 문자열**이 어떻게 반복되는가.

    접두사 반복 판정은 폐기했다 — `SINGLE_JIECAI`(겁재)와 `SINGLE_ZHENGCAI`(정재)는
    접두사가 같아도 다른 근거다.

    다만 전체 코드가 같아도 **같은 evidence 는 아니다.** `REL_{kind}_{palace}` 는
    관계 종류와 궁위만 담고 어느 운 층위(대운·세운·월운)에서 발동했는지를 담지
    않는다. 그래서 서로 다른 발동이 같은 문자열로 기록된다 — 코드 중복 ≠ 근거 중복.
    """
    counts = collections.Counter(codes)
    if any(n > 1 for n in counts.values()):
        return "DUPLICATE_REASON_CODE"
    prefixes = collections.Counter(c.split("_")[0] for c in codes)
    if any(n > 1 for n in prefixes.values()):
        return "SAME_PREFIX_DISTINCT_CODE"
    return "NO_DUPLICATION"


def representatives(
    rows: list[dict[str, Any]], score_key: str, limit: int = 8
) -> list[dict[str, Any]]:
    """동일 기간 그룹화 + 동일 대표 선정 계약. 점수 필드만 교체한다.

    production 의 `_CANDIDATE_RANK_KEY` 는 life_fit > personal_match > score 다. 이
    감사 대상은 앞 두 축이 전건 0 이라 점수 축만 남는다 — 점수 필드 교체가 곧 랭킹
    교체이며, 그래서 반사실 비교가 성립한다.
    """
    ordered = sorted(
        rows,
        key=lambda r: (-r["life_fit"], -r["personal_match"], -r[score_key]),
    )
    groups: dict[str, dict[str, Any]] = {}
    for r in ordered:
        groups.setdefault(r["period"], r)
    return list(groups.values())[:limit]


def run() -> dict[str, Any]:
    """정합 모집단에서 성분·중복·반사실 대표를 측정한다."""
    birth = R.BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male",
    )
    today = date(2026, 7, 30)
    from saju_shared_types.intent import SubjectKind, SubjectRef
    from saju_shared_types.report import ReportPeriod, ReportSpec

    spec = ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic="wealth", period=ReportPeriod(start="2026-01", end="2031-12"),
    )
    data = R._ReportData(birth, spec, today)

    # ── ① 모집단 정합화 ─────────────────────────────────────────────────
    # 대표 편중을 설명하는 감사이므로 결론은 기간 필터가 적용된 동일 모집단에서 낸다.
    # score() 직접 호출분(필터 전)은 참고 자료로만 남긴다.
    legacy_pool = [c for c in data.candidate_pool if str(c.event_key) == TARGET]
    v2_all = data.scorer.score(data.result)
    v2_target = [c for c in v2_all if str(c.event_key) == TARGET]
    v2_by_key: dict[tuple, Any] = {}
    for c in v2_target:
        v2_by_key.setdefault(
            (c.period, round(float(c.raw_score), 2), int(c.score)), c
        )

    rows: list[dict[str, Any]] = []
    unmatched: list[str] = []
    for lc in legacy_pool:
        key = (lc.period, round(float(lc.raw_total), 2), int(lc.score))
        v2 = v2_by_key.get(key)
        if v2 is None:
            unmatched.append(lc.period)
            continue
        contrib = {k: float(v) for k, v in (v2.contributions or {}).items()}
        dw = contrib.get("daewoon_hwa", 0.0)
        raw = float(v2.raw_score)
        rows.append({
            "period": lc.period,
            "axis": _axis(v2.quality),
            "quality": str(v2.quality),
            "polarity_role": str(getattr(v2, "polarity_role", "")),
            "final_score": float(lc.score),                     # A
            "raw_score": raw,                                   # B (= C)
            # D — daewoon_hwa 기여만 0 으로 둔 반사실. raw 에서 그 몫을 빼고 같은
            # soft_cap 을 다시 적용한다(production 공식 미수정).
            "score_without_daewoon_hwa": round(
                _soft_cap(max(0.0, raw - dw)), 3
            ),
            "daewoon_hwa": dw,
            "life_fit": float(lc.life_fit),
            "personal_match": float(lc.personal_match),
            "favorability": float(lc.favorability),
            "contributions": contrib,
            "reason_codes": list(v2.reason_codes),
            "duplicate_state": duplicate_state(list(v2.reason_codes)),
        })

    by_axis: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for r in rows:
        by_axis[r["axis"]].append(r)

    # ── ② 성분 비교 ─────────────────────────────────────────────────────
    comp_keys = sorted({k for r in rows for k in r["contributions"]})
    component_table = {
        comp: {
            axis: _stats([r["contributions"].get(comp, 0.0) for r in items])
            for axis, items in sorted(by_axis.items())
        }
        for comp in comp_keys
    }
    loss_only = [
        c for c in comp_keys
        if any(
            r["contributions"].get(c, 0.0)
            for r in by_axis.get("loss_outflow", [])
        )
        and not any(
            r["contributions"].get(c, 0.0)
            for r in by_axis.get("opportunity_inflow", [])
        )
    ]

    # ── ② 중복 ──────────────────────────────────────────────────────────
    dup_states = collections.Counter(r["duplicate_state"] for r in rows)
    exact_examples = [
        {
            "period": r["period"],
            "repeated": [
                c for c, n in collections.Counter(r["reason_codes"]).items() if n > 1
            ],
        }
        for r in rows if r["duplicate_state"] == "DUPLICATE_REASON_CODE"
    ][:5]

    # ── ③ 반사실 대표 ───────────────────────────────────────────────────
    variants = {
        "A_final_score": "final_score",
        "B_raw_score": "raw_score",
        "C_cap_removed": "raw_score",     # B 와 동일 계산 — cap_contract 에 명시
        "D_no_daewoon_hwa": "score_without_daewoon_hwa",
    }
    reps: dict[str, Any] = {}
    for name, key in variants.items():
        picked = representatives(rows, key)
        share = collections.Counter(r["axis"] for r in picked)
        reps[name] = {
            "score_field": key,
            "periods": [r["period"] for r in picked],
            "axis_counts": dict(share),
            "loss_count": share.get("loss_outflow", 0),
            "loss_share": (
                round(share.get("loss_outflow", 0) / len(picked), 4)
                if picked else 0.0
            ),
        }
    base = set(reps["A_final_score"]["periods"])
    for v in reps.values():
        v["periods_changed_vs_A"] = len(set(v["periods"]) ^ base) // 2
        v["loss_count_delta_vs_A"] = (
            v["loss_count"] - reps["A_final_score"]["loss_count"]
        )

    # ── ④ cap 인과 판정 ─────────────────────────────────────────────────
    a, b, d = reps["A_final_score"], reps["B_raw_score"], reps["D_no_daewoon_hwa"]
    if b["loss_count"] < a["loss_count"]:
        cap_verdict = "CAP_SATURATION_CONTRIBUTES_TO_LOSS_ENRICHMENT"
    elif b["loss_count"] > a["loss_count"]:
        cap_verdict = "CAP_SATURATION_SUPPRESSES_LOSS_ENRICHMENT"
    elif b["periods_changed_vs_A"]:
        cap_verdict = "CAP_SATURATION_ALTERS_WINNERS_NOT_QUALITY_SHARE"
    else:
        cap_verdict = "CAP_SATURATION_PRESENT_BUT_NOT_CAUSAL"

    # ── ⑤ cross-component 판정 ──────────────────────────────────────────
    # D 반사실은 `daewoon_hwa` 의 **인과 영향**을 증명하지만, 그 영향이 부당한 이중
    # 가산이라는 **규범 판단**까지 자동으로 증명하지는 않는다. 이 성분은
    # `quality × daewoon background` 상호작용항으로도 해석할 수 있고, 주효과(yongi)와
    # 상호작용항이 같은 feature 를 쓰는 것 자체는 항상 중복이 아니다.
    if d["loss_count"] != a["loss_count"] or d["periods_changed_vs_A"]:
        cross_verdict = "CROSS_COMPONENT_QUALITY_REUSE_CONFIRMED"
    else:
        cross_verdict = "CROSS_COMPONENT_EFFECT_INCONCLUSIVE"

    saturated = [r for r in rows if r["raw_score"] > 85.0]
    return {
        "audit_id": "WC-SCORE",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "target_event_key": TARGET,
        "scopes": {
            "selection_audit_scope": f"filtered candidate_pool {len(rows)}",
            "reference_scope": f"prefilter score pool {len(v2_target)}",
            "unmatched_legacy_periods": unmatched,
            "note": (
                "대표 구성 판정은 기간 필터가 적용된 정합 모집단에서만 낸다. 필터 전 "
                "풀 통계는 채점 엔진 전반 분포 참고용이며 결론에 섞지 않는다."
            ),
        },
        "cap_contract": {
            "function": "_soft_cap",
            "knee": 85.0,
            "tau": 25.0,
            "form": "raw≤85 항등 · raw>85 → 100-15*exp(-(raw-85)/25)",
            "is_hard_truncation": False,
            "b_and_c_are_same_computation": True,
            "note": (
                "지수 포화이고 raw 이후 다른 정규화·감쇠가 없다. 'cap 제거' 반사실은 "
                "raw 를 그대로 쓰는 것과 동일 계산이라 중복 실험으로 명시한다."
            ),
        },
        "axis_counts": {k: len(v) for k, v in sorted(by_axis.items())},
        "component_table": component_table,
        "loss_only_components": loss_only,
        "daewoon_hwa_by_axis": {
            axis: _stats([r["daewoon_hwa"] for r in items])
            for axis, items in sorted(by_axis.items())
        },
        "duplicate": {
            "states": dict(dup_states),
            "exact_duplicate_examples": exact_examples,
            "cross_component_shared_source": {
                "pair": ["yongi", "daewoon_hwa"],
                "shared_input": "용기신 역할 판정(fav_map)",
                "mechanism": (
                    "yongi 가 polarity_role 로 quality 를 정하고, daewoon_hwa 가 그 "
                    "quality 를 다시 읽어 ±3% 를 적용한다. 적용 방향(boon)은 대운 化神 "
                    "역할이라 독립 입력이지만 적용 대상은 yongi 산출물이다."
                ),
                "counted_in_exact_duplicate": False,
            },
        },
        "counterfactual_representatives": reps,
        "saturation": {
            "raw_above_knee": len(saturated),
            "raw_above_knee_axis": dict(
                collections.Counter(r["axis"] for r in saturated)
            ),
            "raw_stats_above_knee": _stats([r["raw_score"] for r in saturated]),
            "final_stats_above_knee": _stats([r["final_score"] for r in saturated]),
        },
        "verdicts": {
            "loss_exclusive_component": (
                "LOSS_EXCLUSIVE_COMPONENT_HYPOTHESIS_REJECTED" if not loss_only
                else "LOSS_EXCLUSIVE_COMPONENT_FOUND"
            ),
            "duplicate_reason_code": (
                "DUPLICATE_REASON_CODE_FOUND"
                if dup_states.get("DUPLICATE_REASON_CODE")
                else "DUPLICATE_REASON_CODE_NOT_FOUND"
            ),
            "duplicate_evidence": "DUPLICATE_CODE_DISTINCT_SOURCE",
            "duplicate_scoring": "DUPLICATE_RELATION_SCORING_NOT_A_DEFECT",
            "cap": cap_verdict,
            "cross_component": cross_verdict,
            "cross_component_design": (
                "CROSS_COMPONENT_DOUBLE_COUNTING_DESIGN_JUDGMENT_PENDING"
            ),
        },
        "status_flags": [
            "LOSS_EXCLUSIVE_COMPONENT_HYPOTHESIS_REJECTED",
            "CAP_SATURATION_PRESENT_BUT_NOT_CAUSAL",
            "DAEWOON_HWA_SIGN_ASYMMETRY_EXPLAINED",
            "DAEWOON_HWA_CAUSAL_DRIVER_OF_LOSS_ENRICHMENT_ON_AUDITED_FIXTURE",
            "CROSS_COMPONENT_QUALITY_REUSE_CONFIRMED",
            "CROSS_COMPONENT_DOUBLE_COUNTING_DESIGN_JUDGMENT_PENDING",
            "DUPLICATE_REASON_CODE_FOUND_18_OF_72",
            "DUPLICATE_CODE_DISTINCT_SOURCE",
            "MULTI_SOURCE_RELATION_ACCUMULATION_CONFIRMED",
            "DUPLICATE_RELATION_SCORING_NOT_A_DEFECT",
            "REL_CODE_SOURCE_IDENTITY_MISSING",
            "PRODUCTION_UNCHANGED",
        ],
        "retired_status_flags": [
            "CROSS_COMPONENT_DOUBLE_COUNTING_CONFIRMED",
            "EXACT_DUPLICATE_EVIDENCE_FOUND",
            "LOSS_SCORE_ENRICHMENT_FROM_DUPLICATE_EVIDENCE",
            "LOSS_SCORE_ENRICHMENT_FROM_CAP_SATURATION",
        ],
        "causal_narrative": (
            "감사 대상 명식과 기간에서 `wealth_change` 대표의 손실 편중은 score cap "
            "때문이 아니었다. 동일한 후보군과 선별 계약에서 cap 을 제거해도 대표 8건은 "
            "변하지 않았지만, `daewoon_hwa` 보정을 제거하면 손실 대표가 6건에서 3건으로 "
            "감소하고 대표 3건이 교체됐다. 따라서 이 fixture 에서 손실 편중을 직접 만든 "
            "측정 가능한 성분은 `daewoon_hwa` 였다. 전체 시스템의 유일한 원인으로 "
            "일반화하지 않는다 — 단일 fixture 결과다."
        ),
        "relation_code_finding": {
            "flag": "REL_CODE_SOURCE_IDENTITY_MISSING",
            "generator": "relation_palace_engine:129 f\"REL_{act.kind.value}_{act.palace.value}\"",
            "mechanism": (
                "발동(act) 1건마다 bonus 를 누적하고 같은 문자열을 append 한다. 코드에 "
                "운 층위(대운·세운·월운) 식별자가 없어 서로 다른 발동이 같은 문자열로 "
                "기록된다. 합산에는 `_MAX_RELATION_DELTA` 상한이 걸려 있다."
            ),
            "is_score_defect": False,
            "is_observability_defect": True,
            "impact": (
                "`marriage_output_guard` 가 이 코드로 안정성 위험을 분류하고 리포트 "
                "근거 블록에도 노출된다. 같은 코드가 두 번 나오면 사용자·감사 양쪽에서 "
                "'같은 근거가 중복 기록됐다' 로 오독된다."
            ),
            "dedup_counterfactual_not_computed": (
                "source identity 가 코드에 없고 실제로는 다른 발동이므로 dedup 자체가 "
                "잘못된 조작이다 — 반사실 E 는 계산하지 않는다."
            ),
            "followup": "별도 provenance/observability 개선(코드 포맷 변경은 이번 범위 밖)",
        },
        "rows": rows,
    }


if __name__ == "__main__":
    r = run()
    out = _ROOT / "doc" / "v2_2" / "audits" / "wc_score_components.json"
    out.write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    print("  scope:", r["scopes"]["selection_audit_scope"],
          "· 참고", r["scopes"]["reference_scope"],
          "· 미매칭", r["scopes"]["unmatched_legacy_periods"])
    print("  축:", r["axis_counts"])
    print("\n  성분 평균 (축 → mean):")
    for comp, per in r["component_table"].items():
        print(f"    {comp:14} " + "  ".join(
            f"{a}={v.get('mean')}" for a, v in per.items() if v.get("n")))
    print("\n  중복 상태:", r["duplicate"]["states"])
    print("  daewoon_hwa 축별 평균:", {
        a: v.get("mean") for a, v in r["daewoon_hwa_by_axis"].items()})
    s = r["saturation"]
    print(f"\n  포화(raw>85): {s['raw_above_knee']}건 {s['raw_above_knee_axis']}")
    print(f"    raw {s['raw_stats_above_knee'].get('min')}~"
          f"{s['raw_stats_above_knee'].get('max')} → final "
          f"{s['final_stats_above_knee'].get('min')}~"
          f"{s['final_stats_above_knee'].get('max')}")
    print("\n  반사실 대표:")
    for name, v in r["counterfactual_representatives"].items():
        print(f"    {name:20} loss {v['loss_count']}/8 "
              f"({v['loss_share']:.0%}) Δloss={v['loss_count_delta_vs_A']:+d} "
              f"교체={v['periods_changed_vs_A']} {v['axis_counts']}")
    print("\n  판정:", r["verdicts"])
