#!/usr/bin/env python3
"""WC-SIG — `wealth_change` 근거 축 감사 (측정 전용, production 무변경).

**결론(2026-07-30 코드 계보 추적으로 확정): opportunity/loss/pressure 는 사건 종류가
아니라 결과 품질(길흉 방향)이다.** 초기 두 차례 측정은 이 축을 `semantic` 으로 잘못
명명했다. 계보는 다음이다.

    polarity_role(용신·희신·기신·한신)
      → YongiQualityEngine.apply()
          HAN_GOOD → OPPORTUNITY · HAN_BAD → PRESSURE
          GI/GI_STRONG → _gi_quality(event_key)   LOSS/CONFLICT/PRESSURE
          용신·희신     → _yong_quality(event_key) ACHIEVEMENT/OPPORTUNITY
      → quality
      → _QUALITY_TO_POLARITY  (polarity 는 quality **파생**)
      → materialization 방향 문자열(기회·유입/손실·지출/압박·부담, 1:1)

`_gi_quality`·`_yong_quality` 는 `event_key` 만 보고 품질을 정한다 — 같은
`wealth_change` 에 대해 용기신 역할이 길이면 opportunity, 흉이면 loss/pressure 다.
사건의 **종류**를 가른 것이 아니라 같은 사건의 **유불리**를 가른 것이다. 그래서
quality × materialization 일치 72/72 는 독립 근거 합치가 아니라 한 값의 두 번 표기다.

`EventQuality` 스키마 docstring 도 같은 말을 한다 — "사건 '방향'(길흉) 품질 …
방향 전용이다".

배경: 재물 테마의 대표 시점 8개가 모두 `wealth_change` 였다. umbrella 키가 도메인을
덮고 있다는 것까지는 확정됐지만, **그 안의 근거가 여러 의미로 분화되는지는 미확정**
이다. 확정 없이 키를 쪼개면 없는 구분을 만들어 낸다.

원래 물음("유형 A: 키만 같고 의미가 다름 / 유형 B: 근거도 같음")에 대한 답은
**B 에 가까운 semantic 비분화 상태**다. activation 과 provenance 는 후보마다 다르지만
그 차이가 수입·지출·정산·자산이동 같은 사건 종류를 만들지는 않는다.

    event_key        = wealth_change
    outcome_quality  = opportunity / loss / pressure
    activation       = active / delayed / conflicted / mixed / ...
    semantic_subtype = 없음 (엔진에 존재하지 않는다)

사건 종류로 나누려면 taxonomy·detector 신설이 필요하다 — `display_subtype` 추가로
해결할 문제가 아니다. 이번 작업에서 하지 않는 것: subtype 신설, 점수 변경,
대표 교체, taxonomy 분할.

군집화는 결정적 필드 정규화로만 한다 — LLM·임베딩을 쓰지 않는다. 기간과 점수는
signature 에서 **제외**하고 별도 속성으로 둔다(같은 구조가 여러 시기에 반복되는지를
보기 위해서다).
"""

from __future__ import annotations

import collections
import json
import sys
from dataclasses import dataclass
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
from saju_shared_types.events import EventCandidate  # noqa: E402
from saju_shared_types.intent import SubjectKind, SubjectRef  # noqa: E402
from saju_shared_types.report import ReportPeriod, ReportSpec  # noqa: E402

TARGET_EVENT_KEY = "wealth_change"
UNKNOWN = "UNKNOWN"

# ── 3축 분리 (2026-07-30 데굴님 확정) ────────────────────────────────────
#
# 1차 시도는 근거 **어휘 매칭**으로 의미를 붙였고 그래서 `financial_volatility` 25건
# 같은 라벨이 나왔다. 그것은 재물 사건의 종류가 아니라 합충형파에 따른 **작동 방식**
# 이었다. 어휘 매칭을 폐기하고 구조화 필드에서 도출한다.
#
#   outcome_quality_axis    무슨 재물 변화인가   ← quality + materialization 방향
#   activation_axis  어떻게 활성되는가    ← timing + 공망·관계발동·혼합·역행
#   context_locus    어디서 드러나는가    ← 궁위 라벨(의미 결정에 쓰지 않는다)
#
# provenance(detector·stack·source layer·evidence path)는 군집 키에서 **제외**한다.
# 1차 측정에서 exact signature 72/72 가 유일했던 것은 의미 차이가 아니라 provenance
# 조합 차이였다(detector 7종이 72건 전부 동일). 과세분 확인됨.

QUALITY_OPPORTUNITY = "opportunity_inflow"
QUALITY_LOSS = "loss_outflow"
QUALITY_PRESSURE = "pressure"

#: materialization 문자열의 방향 표현 → 의미 축. 궁위·단계는 여기서 읽지 않는다.
#:
#: 방향은 **3종**이며 `quality` 3값과 1:1 대응한다. 초기 매핑에 `압박·부담` 이 빠져
#: 있어 그 4건이 방향 결측으로 관측됐다(2026-07-30 수동 검토에서 발견). 실제 데이터
#: 결측이 아니라 감사 매핑 누락이었다 — 미등록 표현은 계속 UNKNOWN 으로 fail-closed
#: 하되, 알려진 표현을 빠뜨리면 없는 결측을 만들어 낸다.
_DIRECTION_TO_QUALITY = {
    "기회·유입": QUALITY_OPPORTUNITY,
    "손실·지출": QUALITY_LOSS,
    "압박·부담": QUALITY_PRESSURE,
}
#: quality → 의미 축.
_QUALITY_FIELD_TO_AXIS = {
    "opportunity": QUALITY_OPPORTUNITY,
    "loss": QUALITY_LOSS,
    "pressure": QUALITY_PRESSURE,
}
#: 작동 방식 표지 — reason 신호 이름에서만 읽는다.
_ACTIVATION_MARKERS = {
    "공망 지연": "delayed",
    "관계 발동": "conflicted",
    "혼합 신호": "mixed",
    "역행 흐름": "reversed",
}
#: 궁위 라벨 → 발현 맥락. 의미 축과 섞지 않는다.
_LOCUS_TOKENS = {"배우자": "spouse_palace", "거처": "residence_context"}


@dataclass(frozen=True)
class OutcomeQualityReading:
    """3축 판독 — 출처까지 남겨 어느 필드가 판정을 만들었는지 추적한다."""

    outcome_quality_axis: str
    activation_axis: tuple[str, ...]
    context_loci: tuple[str, ...]
    process_stages: tuple[str, ...]
    outcome_quality_sources: tuple[str, ...]
    context_sources: tuple[str, ...]
    outcome_quality_conflict: bool
    quality_missing: bool
    direction_missing: bool

    def outcome_quality_key(self) -> tuple:
        """의미 군집 키 — provenance·궁위 제외."""
        return (self.outcome_quality_axis,)

    def cross_key(self) -> tuple:
        """outcome_quality × activation 교차 키."""
        return (self.outcome_quality_axis, self.activation_axis)


def _materialization_parts(cand: EventCandidate) -> list[list[str]]:
    """materialization 신호를 ' · ' 로 분해한다.

    방향 표현('기회·유입')은 내부에 공백 없는 '·' 를 쓰므로 구분자와 충돌하지 않는다.
    """
    out: list[list[str]] = []
    for sig in cand.signals:
        if sig.type != "materialization":
            continue
        out.append([p.strip() for p in sig.effect.split(" · ") if p.strip()])
    return out


def read_axes(cand: EventCandidate) -> OutcomeQualityReading:
    """구조화 필드에서 3축을 도출한다. 불일치·결측은 UNKNOWN 으로 남긴다."""
    q_axis = _QUALITY_FIELD_TO_AXIS.get((cand.quality or "").strip())
    directions: set[str] = set()
    loci: set[str] = set()
    stages: set[str] = set()
    for parts in _materialization_parts(cand):
        for part in parts:
            # 방향 판정이 **먼저**다 — 뒤로 밀면 방향 표현이 process 단계로 흘러간다.
            if part in _DIRECTION_TO_QUALITY:
                directions.add(_DIRECTION_TO_QUALITY[part])
            elif any(tok in part for tok in _LOCUS_TOKENS):
                # 궁위 라벨 — 의미 결정에 쓰지 않고 맥락으로만 보존한다.
                for tok, name in _LOCUS_TOKENS.items():
                    if tok in part:
                        loci.add(name)
            elif "사건 후보" in part:
                continue                      # 강/약 강도 표기 — 의미 축 아님
            else:
                stages.add(part)              # process 단계
    d_axis = next(iter(directions)) if len(directions) == 1 else None
    # 교차 확인 — 두 출처가 어긋나면 UNKNOWN(억지로 합치지 않는다).
    sources: list[str] = []
    if q_axis is not None:
        sources.append("quality")
    if d_axis is not None:
        sources.append("materialization_direction")
    if q_axis is not None and d_axis is not None:
        axis = q_axis if q_axis == d_axis else UNKNOWN
    elif q_axis is not None:
        axis = q_axis
    elif d_axis is not None:
        axis = d_axis
    else:
        axis = UNKNOWN
    conflict = q_axis is not None and d_axis is not None and q_axis != d_axis

    markers = {"active": (cand.timing or "").strip() == "active"}
    names = {s.name for s in cand.signals}
    act: set[str] = {"active"} if markers["active"] else set()
    if (cand.timing or "").strip() == "delay":
        act.add("delayed")
    for name, label in _ACTIVATION_MARKERS.items():
        if name in names:
            act.add(label)
    return OutcomeQualityReading(
        outcome_quality_axis=axis,
        activation_axis=tuple(sorted(act)) or (UNKNOWN,),
        context_loci=tuple(sorted(loci)) or (UNKNOWN,),
        process_stages=tuple(sorted(stages)),
        outcome_quality_sources=tuple(sources) or (UNKNOWN,),
        context_sources=("materialization_palace_label",) if loci else (),
        outcome_quality_conflict=conflict,
        quality_missing=q_axis is None,
        direction_missing=d_axis is None,
    )


def run() -> dict[str, Any]:
    """`wealth_change` 전건을 3축으로 재집계한다(provenance 군집 키 제외)."""
    birth = R.BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male",
    )
    today = date(2026, 7, 30)
    spec = ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic="wealth", period=ReportPeriod(start="2026-01", end="2031-12"),
    )
    data = R._ReportData(birth, spec, today)
    pool = [c for c in data.candidate_pool if str(c.event_key) == TARGET_EVENT_KEY]
    bundle = data.evidence_bundle
    view = (bundle.view("wealth_change") if bundle is not None else None)
    rep_periods = [g.period for g in view.groups] if view is not None else []

    rows: list[dict[str, Any]] = []
    axis_counts = collections.Counter()
    act = collections.Counter()
    cross = collections.Counter()
    locus = collections.Counter()
    pol_by_axis: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    conflicts = 0
    q_missing = 0
    d_missing = 0
    for rank, c in enumerate(pool, start=1):
        r = read_axes(c)
        axis_counts[r.outcome_quality_axis] += 1
        act["+".join(r.activation_axis)] += 1
        cross[(r.outcome_quality_axis, "+".join(r.activation_axis))] += 1
        locus[(r.outcome_quality_axis, "+".join(r.context_loci))] += 1
        pol_by_axis[r.outcome_quality_axis][str(c.polarity)] += 1
        conflicts += r.outcome_quality_conflict
        q_missing += r.quality_missing
        d_missing += r.direction_missing
        rows.append({
            "rank": rank, "period": c.period, "score": c.score,
            "raw_total": c.raw_total, "life_fit": c.life_fit,
            "personal_match": c.personal_match, "favorability": c.favorability,
            "reason_signals": sorted({
                s.name for s in c.signals if s.type == "reason"
            }),
            "polarity": str(c.polarity), "quality": c.quality, "timing": c.timing,
            "outcome_quality_axis": r.outcome_quality_axis,
            "activation_axis": list(r.activation_axis),
            "context_loci": list(r.context_loci),
            "process_stages": list(r.process_stages),
            "outcome_quality_sources": list(r.outcome_quality_sources),
            "context_sources": list(r.context_sources),
            "outcome_quality_conflict": r.outcome_quality_conflict,
            "is_representative_period": c.period in rep_periods,
        })

    total = len(rows)
    reps = [r for r in rows if r["is_representative_period"]]
    # ── 궁위 변별력 ─────────────────────────────────────────────────────
    # 전건 동일하면 후보별 사건 맥락이 아니라 명식 일지에 기계적으로 붙는 정적
    # 위치 라벨이다. 이번 감사에서는 semantic·activation 입력과 변별 정보에서
    # 제외하고 원시 데이터만 보존한다.
    locus_sets = {tuple(r["context_loci"]) for r in rows}
    context_discriminative = len(locus_sets) > 1

    # ── 수동 검토 표본 ──────────────────────────────────────────────────
    # 전수 검토는 불필요하다. 군집 대표 · pressure 전건 · 대표 시점 · 경계 사례만.
    picked: dict[int, dict[str, Any]] = {}

    def _pick(row: dict[str, Any], reason: str) -> None:
        slot = picked.setdefault(row["rank"], dict(row) | {"review_reasons": []})
        if reason not in slot["review_reasons"]:
            slot["review_reasons"].append(reason)

    by_axis: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for r in rows:
        by_axis[r["outcome_quality_axis"]].append(r)
    for axis in ("opportunity_inflow", "loss_outflow"):
        for r in by_axis.get(axis, [])[:2]:
            _pick(r, f"{axis}_cluster_representative")
    for r in by_axis.get("pressure", []):
        _pick(r, "pressure_all_cases")            # 4건 전부 — 독립성 확인
    for r in reps:
        _pick(r, "display_representative_period")
    # 같은 semantic · 다른 activation 경계 사례 2쌍.
    for axis in ("loss_outflow", "opportunity_inflow"):
        seen_act: set[str] = set()
        for r in by_axis.get(axis, []):
            act_label = "+".join(r["activation_axis"])   # Counter `act` 를 가리지 않게
            if act_label in seen_act:
                continue
            seen_act.add(act_label)
            if len(seen_act) <= 2:
                _pick(r, f"{axis}_activation_boundary")
    # 방향 근거가 약한 사례(materialization 방향 결측) 최대 2건.
    weak = [r for r in rows if "materialization_direction" not in r["outcome_quality_sources"]]
    for r in weak[:2]:
        _pick(r, "weak_direction_evidence")
    rep_axis = collections.Counter(r["outcome_quality_axis"] for r in reps)
    rep_act = collections.Counter("+".join(r["activation_axis"]) for r in reps)
    unknown_sem = axis_counts.get(UNKNOWN, 0)
    named = {k: n for k, n in axis_counts.items() if k != UNKNOWN}
    # 확정 기준(데굴님 6조건 중 자동 판정 가능한 것): 비-UNKNOWN 군집 ≥2,
    # 주요 군집 각 ≥5건, 대표 시점이 ≥2 군집에 분포, 의미 UNKNOWN 과반 미만.
    checks = {
        "at_least_two_named_axisantic_clusters": len(named) >= 2,
        "major_clusters_have_five_or_more": (
            sum(1 for n in named.values() if n >= 5) >= 2
        ),
        "representatives_span_two_or_more": len(
            {k for k in rep_axis if k != UNKNOWN}
        ) >= 2,
        "semantic_unknown_below_half": (
            unknown_sem / total < 0.5 if total else False
        ),
    }
    # 자동 조건은 "축이 여러 값으로 갈리는가" 만 본다 — 그것이 **사건 의미** 분화인지는
    # 코드 계보가 답했고, 답은 아니다. 그래서 판정은 축 갈림과 무관하게 기각이다.
    verdict = "TYPE_A_REJECTED_OUTCOME_QUALITY_AXIS"
    return {
        "audit_id": "WC-SIG-2",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "target_event_key": TARGET_EVENT_KEY,
        "supersedes": "WC-SIG (어휘 매칭 기반 — 폐기)",
        "note": (
            "3축 분리: semantic(quality+materialization 방향) / activation(timing+"
            "공망·관계발동·혼합·역행) / context_locus(궁위 — 의미 결정에 쓰지 않음). "
            "provenance(detector·stack·source layer·evidence path)는 군집 키에서 "
            "제외했다. 궁위는 bridge evidence 없이 배우자 재정·부동산·이사로 확장하지 "
            "않는다(context_only)."
        ),
        "total_candidates": total,
        "outcome_quality_distribution": dict(axis_counts),
        "activation_distribution": dict(act),
        "outcome_quality_x_activation": {f"{k[0]} × {k[1]}": n for k, n in cross.most_common()},
        "outcome_quality_x_context_locus": {
            f"{k[0]} × {k[1]}": n for k, n in locus.most_common()
        },
        "polarity_by_outcome_quality": {k: dict(v) for k, v in pol_by_axis.items()},
        "outcome_quality_conflict_count": conflicts,
        "quality_missing_count": q_missing,
        "materialization_direction_missing_count": d_missing,
        "outcome_quality_unknown_count": unknown_sem,
        "outcome_quality_unknown_share": round(unknown_sem / total, 4) if total else 0.0,
        "representative_periods": rep_periods,
        "representative_outcome_quality_distribution": dict(rep_axis),
        "representative_activation_distribution": dict(rep_act),
        "representative_table": [
            {
                "period": r["period"], "outcome_quality": r["outcome_quality_axis"],
                "activation": "+".join(r["activation_axis"]),
                "context": "+".join(r["context_loci"]),
            }
            for r in sorted(reps, key=lambda x: x["period"])
        ],
        # 궁위는 후보 간 값이 갈리지만(45/72 라벨 有) **의미를 구분하지 않는다** —
        # opportunity·loss 양쪽에 유무가 모두 분산돼 있다. 전건 동일이 아니며,
        # 두 번째 값은 다른 궁위가 아니라 라벨 결측이다.
        "context_label_coverage": (
            f"{sum(1 for r in rows if r['context_loci'] != [UNKNOWN])}/{total}"
        ),
        "context_locus_semantically_non_discriminative": True,
        "context_label_present_in_representatives": sum(
            1 for r in reps if r["context_loci"] != [UNKNOWN]
        ),
        # 손실 편중 원인 분리용 measurement — 점수·선별은 바꾸지 않는다.
        "rank_enrichment_probe": {
            "pool_share": {
                k: round(n / total, 4) for k, n in axis_counts.items()
            } if total else {},
            "representative_share": {
                k: round(n / len(reps), 4) for k, n in rep_axis.items()
            } if reps else {},
            "score_histogram_by_axisantic": {
                axis: dict(
                    collections.Counter(r["score"] for r in by_axis.get(axis, []))
                )
                for axis in axis_counts
            },
            "score_mean_by_axisantic": {
                axis: round(
                    sum(r["score"] for r in by_axis.get(axis, []))
                    / max(1, len(by_axis.get(axis, []))), 3
                )
                for axis in axis_counts
            },
            "top_score_composition": dict(collections.Counter(
                r["outcome_quality_axis"] for r in rows
                if r["score"] == max((x["score"] for x in rows), default=0)
            )),
            "life_fit_all_zero": all(r["life_fit"] == 0.0 for r in rows),
            "personal_match_all_zero": all(
                r["personal_match"] == 0.0 for r in rows
            ),
            "tie_break_note": (
                "life_fit·personal_match 가 전건 0 이면 _CANDIDATE_RANK_KEY 의 1·2축이 "
                "무력하고 score 만으로 정렬된다. score 가 포화(98~99)면 동점 구간의 "
                "순서는 풀 입력 순서가 결정한다 — 랭킹 규칙이 손실을 우대한다는 인과는 "
                "이 관측만으로 확정되지 않는다."
            ),
        },
        "context_locus_discriminative": context_discriminative,
        "context_locus_note": (
            "전건 동일 — 명식 일지에 기계적으로 붙는 정적 위치 라벨로 보인다. "
            "semantic·activation 입력과 후보 변별에서 제외했다. bridge evidence 없이 "
            "배우자 재정·부동산·이사 사건으로 확장하지 않는다(static_natal_palace)."
        ) if not context_discriminative else "후보별로 다름 — 맥락 축으로 유효",
        "context_source": (
            "static_natal_palace" if not context_discriminative else "per_candidate"
        ),
        "cluster_tiers": {
            "major": {k: n for k, n in axis_counts.items() if k != UNKNOWN and n >= 5},
            "minor": {k: n for k, n in axis_counts.items() if k != UNKNOWN and n < 5},
            "note": (
                "주요 군집은 production subtype 후보 판단용 임계(5건 이상)다. 세 번째"
                " 이후 군집까지 모두 5건 이상이어야 하는 것은 아니다. minor 군집은 "
                "umbrella wealth_change 에 유지하고 승격을 보류한다."
            ),
        },
        # 대표 선정이 손실·주의 사건을 더 올리는지 — taxonomy 문제와 구분하기 위한
        # 관측값이다. 점수·선별을 바꾸지 않는다.
        "representative_ranking_table": [
            {
                "period": r["period"], "outcome_quality": r["outcome_quality_axis"],
                "activation": "+".join(r["activation_axis"]),
                "polarity": r["polarity"], "score": r["score"],
                "life_fit": r["life_fit"], "personal_match": r["personal_match"],
                "favorability": r["favorability"], "rank": r["rank"],
            }
            for r in sorted(reps, key=lambda x: x["period"])
        ],
        "manual_review_sample": [
            picked[k] for k in sorted(picked)
        ],
        "manual_review_sample_size": len(picked),
        "status_flags": [
            "TYPE_A_REJECTED",
            "OUTCOME_QUALITY_AXIS_CONFIRMED",
            "SEMANTIC_SUBTYPE_UNAVAILABLE",
            "ACTIVATION_AXIS_CONFIRMED",
            "WEALTH_CHANGE_TAXONOMY_GAP_CONFIRMED",
            "OVERSEGMENTATION_RESOLVED",
            "PRESSURE_DIRECTION_CONFIRMED",
            "CONTEXT_LOCUS_NON_DISCRIMINATIVE",
            "LOSS_OUTFLOW_RANK_ENRICHMENT_OBSERVED",
            "PRODUCTION_UNCHANGED",
        ],
        "retired_status_flags": [
            "PRESSURE_MINOR_CLUSTER_DIRECTION_MISSING",
            "TYPE_A_CANDIDATE_AUTOCHECKS_PASS",
            "PRESSURE_INDEPENDENT_SEMANTIC_CANDIDATE",
            "CONTEXT_LOCUS_SEMANTICALLY_NON_DISCRIMINATIVE",
            "MANUAL_REVIEW_PENDING",
        ],
        "semantic_subtype": "UNAVAILABLE",
        "semantic_subtype_note": (
            "엔진에 재물 사건 **종류** 분류가 없다. opportunity/loss/pressure 는 "
            "용기신 역할에서 나온 길흉 방향이며, 수입·지출·정산·자산이동 구분은 "
            "taxonomy·detector 신설 없이 만들 수 없다."
        ),
        "quality_derivation_lineage": {
            "origin": "polarity_role (용신·희신·기신·한신)",
            "assigns_quality": "yongi_quality_engine.YongiQualityEngine.apply",
            "quality_inputs": ["polarity_role", "event_key"],
            "gi_quality_fn": "_gi_quality(event_key) → LOSS/CONFLICT/PRESSURE",
            "yong_quality_fn": "_yong_quality(event_key) → ACHIEVEMENT/OPPORTUNITY",
            "polarity_derived_from_quality": (
                "event_engine_v2._QUALITY_TO_POLARITY"
            ),
            "materialization_direction_is_quality_string": True,
            "independent_semantic_evidence_in_quality_inputs": False,
            "schema_docstring": (
                "EventQuality — \"사건 '방향'(길흉) 품질 … 방향 전용이다\""
            ),
        },
        "manual_review_terminated": (
            "TYPE_A 의미 군집 검증 목적은 종료했다 — 코드 계보가 세 값이 결과 품질임을 "
            "결정적으로 보여줬다. 표본 13건은 향후 outcome-quality 표현 감수에 재사용할 "
            "수 있으나 이번 판정의 필수 단계가 아니다."
        ),
        "outcome_quality_source_agreement": {
            "quality_x_direction_agree": total - conflicts - q_missing - d_missing,
            "direction_missing": d_missing,
            "direction_conflict": conflicts,
            "quality_missing": q_missing,
        },
        "autochecks": checks,
        "verdict": verdict,
        "manual_review_status": "TERMINATED_NOT_REQUIRED",
        "rows": rows,
    }


if __name__ == "__main__":
    r = run()
    out = _ROOT / "doc" / "v2_2" / "audits" / "wc_sig2_wealth_change_axes.json"
    out.write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name, "→", r["verdict"])
    print(f"  후보 {r['total_candidates']}건")
    print("  outcome_quality:", r["outcome_quality_distribution"])
    print("  activation:", r["activation_distribution"])
    print(f"  의미 UNKNOWN {r['outcome_quality_unknown_count']}건 "
          f"({r['outcome_quality_unknown_share']:.1%}) · 불일치 "
          f"{r['outcome_quality_conflict_count']} · quality 결측 "
          f"{r['quality_missing_count']} · 방향 결측 "
          f"{r['materialization_direction_missing_count']}")
    print("  semantic × activation:")
    for k, n in list(r["outcome_quality_x_activation"].items())[:10]:
        print(f"    {n:4}  {k}")
    print("  polarity by outcome_quality:", r["polarity_by_outcome_quality"])
    print("  대표 8시점:")
    for t in r["representative_table"]:
        print(f"    {t['period']}  {t['semantic']:20} {t['activation']:24} "
              f"{t['context']}")
    print("  자동 확인:", r["autochecks"])
    print(f"  궁위 변별력: {r['context_locus_discriminative']} "
          f"({r['context_source']})")
    print("  군집 계층:", {k: v for k, v in r["cluster_tiers"].items() if k != "note"})
    print(f"  수동 검토 표본 {r['manual_review_sample_size']}건")
    print("  대표 8시점 rank 구성:")
    for t in r["representative_ranking_table"]:
        print(f"    {t['period']}  {t['semantic']:19} pol={t['polarity']:18} "
              f"score={t['score']:3} life_fit={t['life_fit']:.2f} "
              f"fav={t['favorability']:.2f} rank={t['rank']}")
