"""위험 엔진 shadow 후보 밀도 리포트 (R0.5 — RISK_ENGINE.md §감수 절차 5, 2차 개정).

점수(R1) 없이 사전 과발동을 잡기 위한 계측. 후보를 단계별로 분리해 측정한다:

- observed  = 룰 하나 이상 매칭(INSUFFICIENT 포함 전체)
- eligible  = 증거 계약 충족(ELIGIBLE/MITIGATED/BLOCKED)
- active    = blocker·특이도 억제 통과(is_active)
- exposable = claimCeiling·등급 통과(R3 배선 후 — 현재 미산출)

밀도 목표(기준: raw가 아니라 active/unique family):
  active incident/period ≤ 1.5 · active family/period ≤ 3 · 단일 원인 활성 family ≤ 2(예외 3)
  incident 항목 발동률 >40% = 0건 · vulnerability/pressure >40% = 수동 검토 대상

기준 차트 1건은 진단용, 임계값 확정은 코퍼스(신강·신약·오행 과다 등 10차트)로 본다 —
평균만이 아니라 p50/p90/최댓값·kind별·차트별 상시 발동 항목을 본다.

실행: python scripts/risk_shadow_density.py [--levels year,month] [--baseline-only]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND / "apps" / "api"))

from saju_api.services.manse_service import calculate  # noqa: E402
from saju_engines import EventEngineV2  # noqa: E402
from saju_engines.risk_engine import cause_atoms  # noqa: E402
from saju_shared_types.birth_input import BirthInput  # noqa: E402
from saju_shared_types.ganji_calendar import GanjiLevel  # noqa: E402
from saju_shared_types.risk_engine import (  # noqa: E402
    EligibilityStatus,
    EvidenceRole,
    ExposureStatus,
    RiskDomain,
    RiskKind,
    is_active,
    is_exposable,
)

_DICTS = _BACKEND / "dictionaries"
_LEVELS = {"daewoon": GanjiLevel.DAEWOON, "year": GanjiLevel.YEAR,
           "month": GanjiLevel.MONTH, "day": GanjiLevel.DAY}
_REF = date(2026, 6, 11)

# 코퍼스 — 기준 차트 + 구조가 다른 합성 명식(신강·신약/오행 편중/관계 다·소 등을 넓게
# 커버하려는 생년 분산 샘플). 임계값 확정용이 아니라 분포 관찰용(R0.5).
# 출생지는 시드 지역(서울/부산)만 사용 — location_db seed 제약(구조 분포에는 무영향).
_CORPUS: list[tuple[str, BirthInput]] = [
    ("기준 1980 남", BirthInput(calendar_type="solar", birth_date=date(1980, 11, 22),
                              birth_time="09:08", birth_place_name="서울", gender="male",
                              reference_date=_REF)),
    ("1955 여", BirthInput(calendar_type="solar", birth_date=date(1955, 3, 5),
                           birth_time="04:30", birth_place_name="부산", gender="female",
                           reference_date=_REF)),
    ("1963 남", BirthInput(calendar_type="solar", birth_date=date(1963, 8, 17),
                           birth_time="22:10", birth_place_name="서울", gender="male",
                           reference_date=_REF)),
    ("1972 여", BirthInput(calendar_type="solar", birth_date=date(1972, 1, 29),
                           birth_time="13:40", birth_place_name="부산", gender="female",
                           reference_date=_REF)),
    ("1985 여", BirthInput(calendar_type="solar", birth_date=date(1985, 6, 10),
                           birth_time="07:15", birth_place_name="서울", gender="female",
                           reference_date=_REF)),
    ("1990 남", BirthInput(calendar_type="solar", birth_date=date(1990, 12, 3),
                           birth_time="18:55", birth_place_name="부산", gender="male",
                           reference_date=_REF)),
    ("1995 여", BirthInput(calendar_type="solar", birth_date=date(1995, 4, 21),
                           birth_time="11:05", birth_place_name="서울", gender="female",
                           reference_date=_REF)),
    ("1998 남", BirthInput(calendar_type="solar", birth_date=date(1998, 9, 9),
                           birth_time="02:20", birth_place_name="부산", gender="male",
                           reference_date=_REF)),
    ("2001 여", BirthInput(calendar_type="solar", birth_date=date(2001, 7, 7),
                           birth_time="16:45", birth_place_name="서울", gender="female",
                           reference_date=_REF)),
    ("2004 남", BirthInput(calendar_type="solar", birth_date=date(2004, 2, 14),
                           birth_time="09:50", birth_place_name="부산", gender="male",
                           reference_date=_REF)),
]


def _pct(n: float, d: float) -> str:
    return f"{(100.0 * n / d):.1f}%" if d else "n/a"


def _percentile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, round(q * (len(s) - 1))))
    return float(s[idx])


def _chart_stats(engine: EventEngineV2, birth: BirthInput, levels: set[GanjiLevel]) -> dict:
    """차트 1건의 단계별 밀도 통계."""
    chart = calculate(birth)
    lc = chart.luck_cycles
    assert lc is not None
    total = 0
    if GanjiLevel.DAEWOON in levels:
        total += len(lc.daewoon_table)
    if GanjiLevel.YEAR in levels:
        total += len(lc.yearly_luck)
    if GanjiLevel.MONTH in levels:
        total += len(lc.monthly_luck)
    if GanjiLevel.DAY in levels:
        total += len(lc.daily_luck)
    engine.score(chart, levels=levels)
    cands = engine.risk_shadow
    eligible = [
        c for c in cands
        if c.eligibility_status is not EligibilityStatus.INSUFFICIENT_EVIDENCE
    ]
    active = [c for c in cands if is_active(c)]
    # 노출 단계 분리(감수 6차) — structural active를 노출 요구별로 나눈다:
    # exposure-required-unknown 후보는 R1에서 등급 상한·차단 대상이므로 일반 incident
    # 밀도와 합산하면 과발동 판단이 왜곡된다(structural vs exposure-qualified 병기).
    exp_unknown = [
        c for c in active
        if c.exposure_requirement in ("required_for_exposure", "confirmed_required")
    ]
    exp_qualified = [c for c in active if c not in exp_unknown]
    active_per_period: dict[str, int] = Counter(c.period_key for c in active)
    fam_per_period: dict[str, set[str]] = defaultdict(set)
    cause_fanout: dict[tuple[str, str], set[str]] = defaultdict(set)
    for c in active:
        fam_per_period[c.period_key].add(c.risk_family or c.risk_id)
        for e in c.evidence:
            if e.role is EvidenceRole.TRIGGER:
                for atom in cause_atoms(e.source):
                    if not atom.startswith("polarity:"):  # 극성은 원인이 아니라 방향
                        cause_fanout[(c.period_key, atom)].add(
                            c.risk_family or c.risk_id,
                        )
    fire_periods: dict[str, set[str]] = defaultdict(set)
    domain_family_periods: Counter = Counter()
    seen_dfp: set[tuple[str, str, str]] = set()
    for c in active:
        fire_periods[c.risk_id].add(c.period_key)
        key = (c.period_key, c.domain.value, c.risk_family or c.risk_id)
        if key not in seen_dfp:
            seen_dfp.add(key)
            domain_family_periods[c.domain.value] += 1
    # REL 차수 지표(감수 16차) — '같은 관계 작용 하나가 여러 위험 이름으로 복제'를
    # 직접 측정: REL 활성 family/기간 + REL 단일 원인 확산(목표: 같은 원인 활성 REL
    # family ≤1, 독립 발현 시 예외 2) + 흡수 역할 분포(대표 수렴이 실제 일어나는가).
    # 관계 컨텍스트 부재 가정(전 REL UNKNOWN) — partner DENIED 오발동=0은 단위
    # fixture(test_risk_rel_c5)가 고정한다.
    def _domain_metrics(domain: RiskDomain) -> dict:
        dom_active = [c for c in active if c.domain is domain]
        fam_pp: dict[str, set[str]] = defaultdict(set)
        fanout: dict[tuple[str, str], set[str]] = defaultdict(set)
        for c in dom_active:
            fam_pp[c.period_key].add(c.risk_family or c.risk_id)
            for e in c.evidence:
                if e.role is EvidenceRole.TRIGGER:
                    for atom in cause_atoms(e.source):
                        if not atom.startswith("polarity:"):
                            fanout[(c.period_key, atom)].add(
                                c.risk_family or c.risk_id)
        return {
            "family_per_period": [len(v) for v in fam_pp.values()] or [0],
            "max_cause_fanout": max((len(v) for v in fanout.values()), default=0),
            "absorbed_roles": dict(Counter(
                c.absorbed_role for c in cands
                if c.domain is domain and c.absorbed_role
            )),
        }

    rel_metrics = _domain_metrics(RiskDomain.RELATIONSHIP)
    mov_metrics = _domain_metrics(RiskDomain.RELOCATION)
    hlt_metrics = _domain_metrics(RiskDomain.HEALTH_SAFETY)
    leg_metrics = _domain_metrics(RiskDomain.CONTRACT_LEGAL)
    # 노출 후보 밀도(감수 18차 — family 목표 계층화): 구조 진단(structural)과 별도로
    # context-exposable(현 컨텍스트에서 노출 가능 판정) family/기간을 병기한다 —
    # R2 최종 선별(≤3)의 입력 규모. 전 컨텍스트 UNKNOWN 가정이므로 하한 추정치.
    exposable_fam_pp: dict[str, set[str]] = defaultdict(set)
    for c in active:
        if is_exposable(c):
            exposable_fam_pp[c.period_key].add(c.risk_family or c.risk_id)
    # 전체 family 최대 기간의 구성(도메인·family) — max가 부당 중복인지 정당 병존인지
    # 감수가 판단할 재료.
    fam_max_period = max(fam_per_period, key=lambda k: len(fam_per_period[k]),
                         default=None)
    fam_max_composition = sorted(
        {f"{c.domain.value}:{c.risk_family or c.risk_id}"
         for c in active if c.period_key == fam_max_period}
    ) if fam_max_period else []
    # 최장 연속 발동(월운 기준) — 평균이 낮아도 특정 위험이 계속 켜져 있으면 범용 룰 신호.
    month_labels = sorted(p.label for p in lc.monthly_luck)
    longest_streak: dict[str, int] = {}
    for rid, ps in fire_periods.items():
        streak = best = 0
        for m in month_labels:
            streak = streak + 1 if m in ps else 0
            best = max(best, streak)
        longest_streak[rid] = best
    return {
        "n_months": len(month_labels),
        "longest_streak": longest_streak,
        "domain_family_periods": dict(domain_family_periods),
        "total": total,
        "observed": len(cands),
        "eligible": len(eligible),
        "active": len(active),
        "suppressed": sum(1 for c in cands if c.suppressed_by_specificity),
        # vulnerability 추적(감수 22차) — 단독 노출 없음 원칙의 실측: 활성/흡수/잔존.
        # incident·warning 승격 기여는 R1 미구현(원칙상 0 — R1 배선 시 지표 추가).
        "vuln_active": sum(
            1 for c in active if c.kind is RiskKind.VULNERABILITY),
        "vuln_absorbed": sum(
            1 for c in cands
            if c.kind is RiskKind.VULNERABILITY and c.suppressed_by_specificity),
        "blocked": sum(
            1 for c in cands if c.eligibility_status is EligibilityStatus.BLOCKED
        ),
        "active_incident": sum(
            1 for c in active if c.kind is RiskKind.INCIDENT_RISK
        ),
        "exposure_required_unknown": len(exp_unknown),
        "exposure_qualified_incident": sum(
            1 for c in exp_qualified if c.kind is RiskKind.INCIDENT_RISK
        ),
        "active_kind": Counter(c.kind.value for c in active),
        "active_counts": [active_per_period.get(p, 0) for p in
                          {c.period_key for c in cands} | set(active_per_period)] or [0],
        "family_per_period": [len(v) for v in fam_per_period.values()] or [0],
        "max_cause_fanout": max((len(v) for v in cause_fanout.values()), default=0),
        "rel_family_per_period": rel_metrics["family_per_period"],
        "rel_max_cause_fanout": rel_metrics["max_cause_fanout"],
        "rel_absorbed_roles": rel_metrics["absorbed_roles"],
        "mov_family_per_period": mov_metrics["family_per_period"],
        "mov_max_cause_fanout": mov_metrics["max_cause_fanout"],
        "mov_absorbed_roles": mov_metrics["absorbed_roles"],
        "hlt_family_per_period": hlt_metrics["family_per_period"],
        "hlt_max_cause_fanout": hlt_metrics["max_cause_fanout"],
        "hlt_absorbed_roles": hlt_metrics["absorbed_roles"],
        "leg_family_per_period": leg_metrics["family_per_period"],
        "leg_max_cause_fanout": leg_metrics["max_cause_fanout"],
        "leg_absorbed_roles": leg_metrics["absorbed_roles"],
        "exposable_family_per_period": [
            len(v) for v in exposable_fam_pp.values()] or [0],
        "fam_max_period_composition": fam_max_composition,
        "fire_rates": {rid: len(ps) / total for rid, ps in fire_periods.items() if total},
        "periods_with_active": len(active_per_period),
    }


_MOV_SCENARIOS: list[tuple[str, list]] = []


def _build_mov_scenarios() -> list[tuple[str, list]]:
    """MOV confirmed 컨텍스트 시나리오 4종(감수 19차 조건 7) — 지연 구성."""
    from saju_engines.risk_engine import MobilityContext
    return [
        ("계획 없음(전 UNKNOWN)", []),
        ("이사 진행 중", [MobilityContext(
            target_type="residential_move", stage="contracted",
            exposure_status=ExposureStatus.CONFIRMED, episode_id="move_plan_1")]),
        ("통근 의존", [MobilityContext(
            target_type="commute_change", stage="moving",
            exposure_status=ExposureStatus.CONFIRMED, commute_dependency=True,
            episode_id="commute_route_1")]),
        ("정착+수리 책임", [MobilityContext(
            target_type="residential_move", stage="settled",
            exposure_status=ExposureStatus.CONFIRMED, repair_responsibility=True,
            episode_id="home_1")]),
    ]


def _mov_scenario_report(levels: set[GanjiLevel], corpus) -> None:
    """시나리오별 MOV 밀도 — 하드 비노출로 낮아진 수치와 실제 노출 밀도를 분리 실측."""
    print("\n# MOV confirmed 시나리오 밀도(감수 19차 조건 7)")
    for name, ctxs in _build_mov_scenarios():
        engine = EventEngineV2(_DICTS, risk_mode="shadow")
        engine.set_risk_shadow_contexts(mobility_contexts=ctxs)
        mov_active = mov_exposable = mov_blocked = periods = 0
        expo_fam_pp: dict[str, set[str]] = defaultdict(set)
        fanout: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        kind_cnt: Counter = Counter()
        for cname, birth in corpus:
            chart = calculate(birth)
            engine.score(chart, levels=levels)
            lc = chart.luck_cycles
            assert lc is not None
            periods += len(lc.yearly_luck) + len(lc.monthly_luck)
            for c in engine.risk_shadow:
                if c.domain is not RiskDomain.RELOCATION:
                    continue
                if c.eligibility_status is EligibilityStatus.BLOCKED:
                    mov_blocked += 1
                if not is_active(c):
                    continue
                mov_active += 1
                kind_cnt[c.kind.value] += 1
                if is_exposable(c):
                    mov_exposable += 1
                    expo_fam_pp[f"{cname}|{c.period_key}"].add(
                        c.risk_family or c.risk_id)
                for e in c.evidence:
                    if e.role is EvidenceRole.TRIGGER:
                        for atom in cause_atoms(e.source):
                            if not atom.startswith("polarity:"):
                                fanout[(cname, c.period_key, atom)].add(
                                    c.risk_family or c.risk_id)
        expo_fams = [len(v) for v in expo_fam_pp.values()] or [0]
        print(f"\n## {name}")
        print(f"  MOV 활성 {mov_active} · 노출 가능 {mov_exposable} · 차단 {mov_blocked} "
              f"· kind {dict(kind_cnt)}")
        # 비율 지표(감수 20차) — 구조 후보 대비 노출·차단·UNKNOWN 보존 비율.
        if mov_active:
            print(f"  비율: exposable/active {_pct(mov_exposable, mov_active)} · "
                  f"blocked/active {_pct(mov_blocked, mov_active)} · "
                  f"UNKNOWN 보존/active "
                  f"{_pct(mov_active - mov_exposable, mov_active)}")
        print(f"  노출 가능 family/기간: p50 {_percentile(expo_fams, 0.5):.0f} · "
              f"p90 {_percentile(expo_fams, 0.9):.0f} · max {max(expo_fams)} · "
              f"노출 기간 수 {len(expo_fam_pp)}/{periods}")
        print(f"  단일 원인 MOV family 확산 max: "
              f"{max((len(v) for v in fanout.values()), default=0)}")


def _build_hlt_scenarios() -> list[tuple[str, list]]:
    """HLT confirmed 컨텍스트 시나리오 5종(감수 21차 §16) — 지연 구성."""
    from saju_engines.risk_engine import HealthContext
    return [
        ("all_unknown", []),
        ("건강 질문만(상태 미확인)", [HealthContext(is_question_target=True)]),
        ("기존 질환 확인", [HealthContext(
            context_type="existing_condition", condition_status="managed",
            exposure_status=ExposureStatus.CONFIRMED, episode_id="health_1")]),
        ("치료·회복 중", [HealthContext(
            context_type="treatment_process", treatment_status="ongoing",
            exposure_status=ExposureStatus.CONFIRMED, episode_id="treatment_1")]),
        ("고강도 신체 업무", [HealthContext(
            context_type="physical_workload", physical_demand="high",
            exposure_status=ExposureStatus.CONFIRMED, episode_id="workload_1")]),
    ]


def _hlt_scenario_report(levels: set[GanjiLevel], corpus) -> None:
    """시나리오별 HLT 밀도 — 오노출률(미확인 특정 노출)은 엔진 게이트로 0이어야 한다."""
    print("\n# HLT confirmed 시나리오 밀도(감수 21차)")
    specific_reqs = ("required_for_exposure", "confirmed_required")
    for name, ctxs in _build_hlt_scenarios():
        engine = EventEngineV2(_DICTS, risk_mode="shadow")
        engine.set_risk_shadow_contexts(health_contexts=ctxs)
        active = exposable = blocked = 0
        mis_specific = 0  # 미확인 상태에서 노출된 특정 항목(=오노출, 0 목표)
        expo_fam_pp: dict[str, set[str]] = defaultdict(set)
        kind_cnt: Counter = Counter()
        for cname, birth in corpus:
            chart = calculate(birth)
            engine.score(chart, levels=levels)
            for c in engine.risk_shadow:
                if c.domain is not RiskDomain.HEALTH_SAFETY:
                    continue
                if c.eligibility_status is EligibilityStatus.BLOCKED:
                    blocked += 1
                if not is_active(c):
                    continue
                active += 1
                kind_cnt[c.kind.value] += 1
                # vulnerability는 단독 노출 없음 원칙(R1/R2) — 노출 지표에서 제외.
                if c.kind is not RiskKind.VULNERABILITY and is_exposable(c):
                    exposable += 1
                    expo_fam_pp[f"{cname}|{c.period_key}"].add(
                        c.risk_family or c.risk_id)
                    if (c.exposure_requirement in specific_reqs
                            and c.exposure_status is not ExposureStatus.CONFIRMED):
                        mis_specific += 1
        expo_fams = [len(v) for v in expo_fam_pp.values()] or [0]
        print(f"\n## {name}")
        print(f"  HLT 활성 {active} · 노출 가능 {exposable} · 차단 {blocked} · "
              f"kind {dict(kind_cnt)}")
        if active:
            print(f"  비율: exposable/active {_pct(exposable, active)} · "
                  f"UNKNOWN 보존 {_pct(active - exposable, active)}")
        print(f"  특정 항목 미확인 오노출: {mis_specific}건 (목표 0)")
        print(f"  노출 가능 family/기간: p50 {_percentile(expo_fams, 0.5):.0f} · "
              f"p90 {_percentile(expo_fams, 0.9):.0f} · max {max(expo_fams)}")


def _build_leg_scenarios() -> list[tuple[str, list]]:
    """LEG confirmed 절차 시나리오 4종(감수 23차 커밋 조건 3) — 지연 구성."""
    from saju_engines.risk_engine import LegalProcessContext
    return [
        ("all_unknown", []),
        ("active_contract", [LegalProcessContext(
            target_type="contract", stage="active_contract",
            exposure_status=ExposureStatus.CONFIRMED,
            process_episode_id="contract_1")]),
        ("official_administrative_process", [LegalProcessContext(
            target_type="administrative_application", stage="review",
            exposure_status=ExposureStatus.CONFIRMED,
            process_episode_id="permit_1")]),
        ("active_dispute_or_litigation", [LegalProcessContext(
            target_type="litigation", stage="litigation_active",
            exposure_status=ExposureStatus.CONFIRMED, existing_dispute=True,
            existing_litigation=True, process_episode_id="dispute_1")]),
    ]


def _leg_scenario_report(levels: set[GanjiLevel], corpus) -> None:
    """시나리오별 LEG 밀도 + RCW 역할 보장 실측(감수 23차 커밋 조건 3·4).

    보고 축(데굴님 요구): observed RCW / context-matched RCW / 대표 아래 흡수 RCW /
    독립 잔존 RCW / family 집계 기여 / 사용자 노출 수. 지표 명칭 분리(감수 24차 —
    '대표 흡수'의 두 의미 구분): rcw_became_representative(RCW가 다른 후보를 흡수한
    대표가 된 수 — 반드시 0) vs rcw_absorbed_as_background(RCW가 구체 대표 아래
    background로 흡수된 수 — 같은 episode에 구체 후보가 있으면 정상 발생). 목표:
    rcw_became_representative=0 · rcw_standalone_exposable=0 · 독립 family 기여=0.
    """
    print("\n# LEG confirmed 절차 시나리오 밀도(감수 23차 커밋 조건)")
    rcw_id = "LEG_REVIEW_CAPACITY_WEAK"
    specific_reqs = ("required_for_exposure", "confirmed_required")
    for name, ctxs in _build_leg_scenarios():
        engine = EventEngineV2(_DICTS, risk_mode="shadow")
        engine.set_risk_shadow_contexts(legal_contexts=ctxs)
        active = exposable = blocked = 0
        mis_specific = 0  # 미확인 절차에서 노출된 특정 항목(=오노출, 0 목표)
        rcw_observed = rcw_matched = rcw_absorbed_as_background = 0
        rcw_standalone = rcw_standalone_exposable = 0
        rcw_became_representative = rcw_family_contrib = 0
        expo_fam_pp: dict[str, set[str]] = defaultdict(set)
        kind_cnt: Counter = Counter()
        for cname, birth in corpus:
            chart = calculate(birth)
            engine.score(chart, levels=levels)
            for c in engine.risk_shadow:
                if c.domain is not RiskDomain.CONTRACT_LEGAL:
                    continue
                if c.suppressed_by_specificity == rcw_id:
                    rcw_became_representative += 1  # RCW가 흡수 대표(반드시 0)
                if c.risk_id == rcw_id:
                    rcw_observed += 1
                    if c.legal_alignment == "matched":
                        rcw_matched += 1
                    if c.suppressed_by_specificity:
                        rcw_absorbed_as_background += 1  # 정상 발생 가능
                    elif is_active(c):
                        rcw_standalone += 1
                    if is_exposable(c):
                        rcw_standalone_exposable += 1
                if c.eligibility_status is EligibilityStatus.BLOCKED:
                    blocked += 1
                if not is_active(c):
                    continue
                active += 1
                kind_cnt[c.kind.value] += 1
                # 노출 지표·family 기여는 is_exposable 기준 — vulnerability는 단독
                # 노출 없음 원칙이 kind 차단으로 내장돼 자동 제외된다.
                if is_exposable(c):
                    exposable += 1
                    expo_fam_pp[f"{cname}|{c.period_key}"].add(
                        c.risk_family or c.risk_id)
                    if c.risk_id == rcw_id:
                        rcw_family_contrib += 1
                    if (c.exposure_requirement in specific_reqs
                            and c.exposure_status is not ExposureStatus.CONFIRMED):
                        mis_specific += 1
        expo_fams = [len(v) for v in expo_fam_pp.values()] or [0]
        print(f"\n## {name}")
        print(f"  LEG 활성 {active} · 노출 가능 {exposable} · 차단 {blocked} · "
              f"kind {dict(kind_cnt)}")
        if active:
            print(f"  비율: exposable/active {_pct(exposable, active)} · "
                  f"UNKNOWN 보존 {_pct(active - exposable, active)}")
        print(f"  특정 항목 미확인 오노출: {mis_specific}건 (목표 0)")
        print(f"  노출 가능 family/기간: p50 {_percentile(expo_fams, 0.5):.0f} · "
              f"p90 {_percentile(expo_fams, 0.9):.0f} · max {max(expo_fams)}")
        print(f"  RCW(latent vulnerability): observed {rcw_observed} · "
              f"context-matched {rcw_matched} · "
              f"rcw_absorbed_as_background {rcw_absorbed_as_background}(정상 발생 가능)"
              f" · 독립 잔존(구조) {rcw_standalone}")
        print(f"  RCW 역할 보장(목표 전부 0): rcw_standalone_exposable "
              f"{rcw_standalone_exposable} · 독립 family 기여 {rcw_family_contrib} · "
              f"rcw_became_representative {rcw_became_representative}")


def _build_exposure_profiles() -> list[tuple[str, dict]]:
    """3프로필 노출 단계 묶음(감수 24차 — R1 진입 게이트 baseline).

    A all_unknown: 전 컨텍스트 미확인 — projected 하한(required_for_warning advisory만).
    B typical_confirmed: 현실적 단일 사용자 — 파트너 확인+일반 건강 질문(상태 미확인)+
      진행 중 계약 1건. 이사·소송·치료·대인 금전거래 없음. 직업 역할(전역 노출 축)은
      R5 프로필 배선 전이라 UNKNOWN 유지 — career 구체 항목은 하한으로 측정된다.
    C high_exposure: 서로 다른 익명 episode 복수 병존(채용 결과 대기+이사 계약+진행
      계약+파트너+치료 중) — R2 risk budget 상한 측정. boolean 무차별 true 금지
      (인위적 후보 폭발이 아니라 현실 상한을 잰다).
    D multi_selection(감수 25차 — SEL-e 회귀): 서로 다른 target type 병존 + 동일
      target type 복수 episode 병존을 동시에 검증 — 채용(결과 대기)+시험 2건
      (assessment/결과 대기)+추첨(draw). C의 의미는 바꾸지 않는다(역사 비교 유지).
    """
    from saju_engines.risk_engine import (
        HealthContext,
        LegalProcessContext,
        MobilityContext,
        RelationshipContext,
        SelectionContext,
    )
    typical = dict(
        relationship_contexts=[RelationshipContext(
            target_role="current_partner", target_id="partner_1",
            exposure_status=ExposureStatus.CONFIRMED)],
        health_contexts=[HealthContext(is_question_target=True)],
        legal_contexts=[LegalProcessContext(
            target_type="contract", stage="active_contract",
            exposure_status=ExposureStatus.CONFIRMED,
            process_episode_id="contract_1")],
    )
    high = dict(
        selection_context=SelectionContext(
            target_type="employment_hiring", stage="result_wait"),
        relationship_contexts=[RelationshipContext(
            target_role="current_partner", target_id="partner_1",
            exposure_status=ExposureStatus.CONFIRMED)],
        mobility_contexts=[MobilityContext(
            target_type="residential_move", stage="contracted",
            exposure_status=ExposureStatus.CONFIRMED,
            episode_id="housing_move_1")],
        health_contexts=[HealthContext(
            context_type="treatment_process", treatment_status="ongoing",
            exposure_status=ExposureStatus.CONFIRMED, episode_id="treatment_1")],
        legal_contexts=[LegalProcessContext(
            target_type="contract", stage="active_contract",
            exposure_status=ExposureStatus.CONFIRMED,
            process_episode_id="active_contract_1")],
    )
    multi_selection = dict(
        selection_contexts=[
            SelectionContext(
                target_type="employment_hiring", stage="result_wait",
                exposure_status=ExposureStatus.CONFIRMED,
                episode_id="employment_hiring_1"),
            SelectionContext(
                target_type="examination", stage="assessment",
                exposure_status=ExposureStatus.CONFIRMED,
                episode_id="examination_1"),
            SelectionContext(
                target_type="examination", stage="result_wait",
                exposure_status=ExposureStatus.CONFIRMED,
                episode_id="examination_2"),
            SelectionContext(
                mode="lottery_draw", target_type="lottery_allocation",
                stage="draw", exposure_status=ExposureStatus.CONFIRMED,
                episode_id="lottery_draw_1"),
        ],
    )
    return [("A_all_unknown", {}), ("B_typical_confirmed", typical),
            ("C_high_exposure", high), ("D_multi_selection", multi_selection)]


def collect_profile_metrics(levels: set[GanjiLevel], corpus) -> dict[str, dict]:
    """3프로필 지표 수집(감수 24차) — 리포트·JSON baseline의 단일 계산 원천.

    반환은 전부 JSON 직렬화 가능·결정적(코퍼스·컨텍스트 고정, 키 정렬)이다.
    blocked 분해(데굴님 §3): 도메인·risk_id·차단 사유별 분해 — 소유권 mismatch의
    과도한 전역 차단을 발견하는 재료.
    """
    out: dict[str, dict] = {}
    for name, ctxs in _build_exposure_profiles():
        engine = EventEngineV2(_DICTS, risk_mode="shadow")
        engine.set_risk_shadow_contexts(**ctxs)
        periods = 0
        active: list = []
        blocked = mismatched = 0
        blocked_by_domain: Counter = Counter()
        blocked_by_risk: Counter = Counter()
        blocked_by_reason: Counter = Counter()
        # blocked 집계 3층(감수 25차 정의 확정 — 데굴님 §4):
        # unique(후보 identity 중복 제거) / unique candidate×reason pair(후보+사유
        # 코드 중복 제거 — 조합표와 같은 모집단은 selection 축 pair) / raw rule hit
        # (동일 사유의 복수 기록 포함). 한 후보가 selection 축 사유와 증거 미충족
        # 사유(evidence_groups_unmet 등)를 동시에 가질 수 있어 전체 pair는 축 pair를
        # 초과한다 — 축 조합표와 비교할 값은 selection_axis_reason_pairs다.
        blocked_reason_pairs = 0  # 후보×사유 중복 제거(전 사유)
        blocked_raw_rule_hits = 0  # 중복 포함 원시 기록 수
        blocked_axis_pairs = 0  # selection 축 2종만의 후보×사유 pair
        blocked_axis_combo: Counter = Counter()
        active_by_risk: Counter = Counter()
        expo_fam_pp: dict[str, set[str]] = defaultdict(set)
        fam_pp: dict[str, set[str]] = defaultdict(set)
        fanout: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        atom_domains: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        episode_counts: Counter = Counter()
        dom_fam: Counter = Counter()
        seen_dfp: set = set()
        kind_cnt: Counter = Counter()
        exposable_n = 0
        for cname, birth in corpus:
            chart = calculate(birth)
            engine.score(chart, levels=levels)
            lc = chart.luck_cycles
            assert lc is not None
            periods += len(lc.yearly_luck) + len(lc.monthly_luck)
            for c in engine.risk_shadow:
                if c.eligibility_status is EligibilityStatus.BLOCKED:
                    blocked += 1
                    blocked_by_domain[c.domain.value] += 1
                    blocked_by_risk[c.risk_id] += 1
                    blocked_raw_rule_hits += len(c.suppression_reasons)
                    unique_reasons = set(c.suppression_reasons)
                    blocked_reason_pairs += len(unique_reasons)
                    for r in sorted(unique_reasons):
                        blocked_by_reason[r] += 1
                    if any(r.endswith("_mismatch") for r in unique_reasons):
                        mismatched += 1
                    has_target = "selection_target_type_mismatch" in unique_reasons
                    has_stage = "selection_stage_mismatch" in unique_reasons
                    blocked_axis_pairs += int(has_target) + int(has_stage)
                    if has_target and has_stage:
                        blocked_axis_combo["target_type_and_stage"] += 1
                    elif has_target:
                        blocked_axis_combo["target_type_only"] += 1
                    elif has_stage:
                        blocked_axis_combo["stage_only"] += 1
                if not is_active(c):
                    continue
                active.append(c)
                kind_cnt[c.kind.value] += 1
                active_by_risk[c.risk_id] += 1
                pkey = f"{cname}|{c.period_key}"
                fam = c.risk_family or c.risk_id
                fam_pp[pkey].add(fam)
                key = (cname, c.period_key, c.domain.value, fam)
                if key not in seen_dfp:
                    seen_dfp.add(key)
                    dom_fam[c.domain.value] += 1
                for axis in ("legal_episode_id", "mobility_episode_id",
                             "health_episode_id", "relationship_target_id",
                             "selection_episode_id"):
                    ep = getattr(c, axis)
                    if ep is not None:
                        episode_counts[f"{axis.rsplit('_', 1)[0]}:{ep}"] += 1
                if is_exposable(c):
                    exposable_n += 1
                    expo_fam_pp[pkey].add(fam)
                for e in c.evidence:
                    if e.role is EvidenceRole.TRIGGER:
                        for atom in cause_atoms(e.source):
                            if not atom.startswith("polarity:"):
                                fanout[(cname, c.period_key, atom)].add(fam)
                                atom_domains[(cname, c.period_key, atom)].add(
                                    c.domain.value)
        fams = [len(v) for v in fam_pp.values()] or [0]
        expo_fams = [len(v) for v in expo_fam_pp.values()] or [0]
        # 집계 불변식(감수 25차 — baseline 기록 전 기계 검증): 축 조합 분해 합 =
        # 축 사유를 가진 unique 후보 수 ≤ 전체 unique, only+only+2×both = 축 pair.
        combo_total = sum(blocked_axis_combo.values())
        assert combo_total <= blocked, (name, combo_total, blocked)
        assert (blocked_axis_combo.get("target_type_only", 0)
                + blocked_axis_combo.get("stage_only", 0)
                + 2 * blocked_axis_combo.get("target_type_and_stage", 0)
                ) == blocked_axis_pairs, name
        out[name] = {
            "periods": periods,
            "active_total": len(active),
            "exposable_total": exposable_n,
            "active_per_period": round(len(active) / max(1, periods), 4),
            "exposable_per_period": round(exposable_n / max(1, periods), 4),
            "kind": dict(sorted(kind_cnt.items())),
            "family_per_period": {
                "p50": _percentile(fams, 0.5), "p90": _percentile(fams, 0.9),
                "max": max(fams)},
            "exposable_family_per_period": {
                "p50": _percentile(expo_fams, 0.5),
                "p90": _percentile(expo_fams, 0.9), "max": max(expo_fams)},
            "max_cause_fanout": max((len(v) for v in fanout.values()), default=0),
            "cross_domain_shared_causes": sum(
                1 for doms in atom_domains.values() if len(doms) >= 2),
            "unknown_retained": len(active) - exposable_n,
            "blocked_unique_candidates": blocked,
            "blocked_unique_candidate_reason_pairs": blocked_reason_pairs,
            "blocked_raw_rule_hits": blocked_raw_rule_hits,
            "blocked_selection_axis_reason_pairs": blocked_axis_pairs,
            "blocked_mismatched": mismatched,
            "blocked_selection_axis_combo": dict(sorted(blocked_axis_combo.items())),
            "blocked_by_domain": dict(sorted(blocked_by_domain.items())),
            "blocked_by_risk_id": dict(sorted(blocked_by_risk.items())),
            "blocked_by_reason": dict(sorted(blocked_by_reason.items())),
            "active_by_risk_id": dict(sorted(active_by_risk.items())),
            "episode_active_counts": dict(sorted(episode_counts.items())),
            "domain_family_contribution": dict(sorted(dom_fam.items())),
        }
    return out


def _profile_scenario_report(levels: set[GanjiLevel], corpus) -> None:
    """3프로필 밀도 baseline(감수 24차 필수 지표) — TYP-0 전후 불변 비교의 기준.

    출력은 결정적이다(코퍼스·컨텍스트 고정, 정렬 출력) — 저장본과의 diff가 회귀 신호.
    기계 판독 baseline은 scripts/risk_profile_baseline.py --write/--check가 담당.
    """
    print("# 위험 3프로필 노출 단계 baseline(감수 24차 — R1 진입 게이트)")
    print(f"코퍼스 {len(corpus)}차트 · 층위 year+month · env 사전 기준 manifest 참조")
    for name, m in collect_profile_metrics(levels, corpus).items():
        print(f"\n## {name}")
        print(f"  기간 {m['periods']} · 활성/기간 {m['active_per_period']:.2f} · "
              f"context-exposable/기간 {m['exposable_per_period']:.2f}")
        print(f"  kind(활성): {m['kind']}")
        print(f"  활성 family/기간: p50 {m['family_per_period']['p50']:.0f} · "
              f"p90 {m['family_per_period']['p90']:.0f} · "
              f"max {m['family_per_period']['max']}")
        print(f"  노출 가능 family/기간: "
              f"p50 {m['exposable_family_per_period']['p50']:.0f} · "
              f"p90 {m['exposable_family_per_period']['p90']:.0f} · "
              f"max {m['exposable_family_per_period']['max']}")
        print(f"  단일 원인 family 확산 max: {m['max_cause_fanout']}")
        print(f"  교차 도메인 공유 원인(기간·원인 기준): "
              f"{m['cross_domain_shared_causes']}")
        print(f"  UNKNOWN 보존(활성·비노출): {m['unknown_retained']} · "
              f"blocked_unique_candidates {m['blocked_unique_candidates']}"
              f"(축 MISMATCHED {m['blocked_mismatched']})")
        print(f"  blocked 3층: unique {m['blocked_unique_candidates']} · "
              f"candidate×reason pairs {m['blocked_unique_candidate_reason_pairs']}"
              f"(target·stage 축만 {m['blocked_selection_axis_reason_pairs']} — "
              f"mode 사유는 분해표 밖·사유 목록에 표시) · "
              f"raw rule hits {m['blocked_raw_rule_hits']}")
        print("  blocked 축 조합(selection): " + (", ".join(
            f"{k}={v}" for k, v in m["blocked_selection_axis_combo"].items())
            or "없음"))
        print("  blocked 분해 — 도메인: " + (", ".join(
            f"{k}={v}" for k, v in m["blocked_by_domain"].items()) or "없음"))
        print("  blocked 분해 — 사유: " + (", ".join(
            f"{k}={v}" for k, v in m["blocked_by_reason"].items()) or "없음"))
        print("  episode별 활성 후보: " + (", ".join(
            f"{k}={v}" for k, v in m["episode_active_counts"].items()) or "없음"))
        print("  도메인 기여도(unique 기간·family): " + ", ".join(
            f"{d} {n}" for d, n in sorted(
                m["domain_family_contribution"].items(), key=lambda kv: -kv[1])))


def main() -> None:
    """코퍼스 단계별 밀도를 계산해 stdout으로 리포트한다."""
    parser = argparse.ArgumentParser(description="위험 shadow 후보 밀도 리포트(단계별)")
    parser.add_argument("--levels", default="year,month")
    parser.add_argument("--baseline-only", action="store_true",
                        help="기준 차트 1건만 실행(빠른 진단)")
    parser.add_argument("--mov-scenarios", action="store_true",
                        help="MOV confirmed 컨텍스트 시나리오 4종 밀도(감수 19차)")
    parser.add_argument("--hlt-scenarios", action="store_true",
                        help="HLT confirmed 컨텍스트 시나리오 5종 밀도(감수 21차)")
    parser.add_argument("--leg-scenarios", action="store_true",
                        help="LEG confirmed 절차 시나리오 4종 밀도(감수 23차 커밋 조건)")
    parser.add_argument("--profile-scenarios", action="store_true",
                        help="3프로필 노출 단계 baseline(감수 24차 — R1 진입 게이트)")
    args = parser.parse_args()
    levels = {_LEVELS[x.strip()] for x in args.levels.split(",") if x.strip()}
    corpus = _CORPUS[:1] if args.baseline_only else _CORPUS
    if args.mov_scenarios:
        _mov_scenario_report(levels, corpus)
        return
    if args.hlt_scenarios:
        _hlt_scenario_report(levels, corpus)
        return
    if args.leg_scenarios:
        _leg_scenario_report(levels, corpus)
        return
    if args.profile_scenarios:
        _profile_scenario_report(levels, corpus)
        return

    engine = EventEngineV2(_DICTS, risk_mode="shadow")
    all_stats: list[tuple[str, dict]] = []
    for name, birth in corpus:
        try:
            all_stats.append((name, _chart_stats(engine, birth, levels)))
        except Exception as exc:  # noqa: BLE001 -- 코퍼스 개별 실패는 건너뛰고 보고
            print(f"[skip] {name}: {exc}")

    print(f"# 위험 shadow 밀도 리포트(단계별) — 차트 {len(all_stats)}개, 층위={args.levels}")
    print(f"{'차트':<12} {'기간':>4} {'obs':>5} {'elig':>5} {'act':>5} {'흡수':>4} "
          f"{'차단':>4} {'act.inc':>7} {'act/기간':>8} {'fam/기간 p90':>12} {'원인확산max':>10}")
    agg_fire: dict[str, list[float]] = defaultdict(list)
    for name, s in all_stats:
        act_per = s["active"] / s["total"] if s["total"] else 0
        fam_p90 = _percentile(s["family_per_period"], 0.9)
        print(f"{name:<12} {s['total']:>4} {s['observed']:>5} {s['eligible']:>5} "
              f"{s['active']:>5} {s['suppressed']:>4} {s['blocked']:>4} "
              f"{s['active_incident']:>7} {act_per:>8.2f} {fam_p90:>12.1f} "
              f"{s['max_cause_fanout']:>10}")
        for rid, rate in s["fire_rates"].items():
            agg_fire[rid].append(rate)

    totals = [s for _, s in all_stats]
    n_periods = sum(s["total"] for s in totals)
    n_active = sum(s["active"] for s in totals)
    n_inc = sum(s["active_incident"] for s in totals)
    kind_sum: Counter = Counter()
    for s in totals:
        kind_sum.update(s["active_kind"])
    n_exp_unknown = sum(s.get("exposure_required_unknown", 0) for s in totals)
    n_exp_inc = sum(s.get("exposure_qualified_incident", 0) for s in totals)
    print("\n## 코퍼스 종합")
    print(f"활성/기간 평균: {n_active / max(1, n_periods):.2f} "
          f"(structural incident/기간: {n_inc / max(1, n_periods):.2f} · "
          f"exposure-qualified incident/기간: {n_exp_inc / max(1, n_periods):.2f} — "
          f"목표 ≤1.5는 exposure-qualified 기준 병기)")
    print(f"노출 확인 필요(UNKNOWN) 활성 후보: {n_exp_unknown} — R1 등급 상한·차단 대상"
          f"(일반 밀도와 분리, 룰 약화 판단에 합산 금지)")
    print("exposure_assumption: 전 후보 UNKNOWN 가정(프로필 미적용) · "
          "required_for_exposure/confirmed_required=분리 · "
          "not_required/required_for_warning=qualified 포함")
    print(f"활성 kind 분포: {dict(kind_sum)}")
    n_vuln_active = sum(s.get("vuln_active", 0) for s in totals)
    n_vuln_absorbed = sum(s.get("vuln_absorbed", 0) for s in totals)
    print(f"vulnerability 추적(단독 노출 없음 원칙): 활성/기간 "
          f"{n_vuln_active / max(1, n_periods):.2f} · 대표 흡수 {n_vuln_absorbed} · "
          f"독립 잔존 {n_vuln_active} · incident/warning 승격 기여 0(R1 미구현 — "
          f"원칙상 0 유지)")
    fam_all = [x for s in totals for x in s["family_per_period"]]
    print(f"활성 family/기간: p50 {_percentile(fam_all, 0.5):.0f} · "
          f"p90 {_percentile(fam_all, 0.9):.0f} · max {max(fam_all, default=0)} (목표 ≤3)")
    dom_fam: Counter = Counter()
    for s in totals:
        dom_fam.update(s.get("domain_family_periods", {}))
    total_fam_periods = sum(dom_fam.values()) or 1
    print("family 밀도 도메인 기여도(기준: suppression 후 활성 unique (기간,도메인,family) 합"
          " — exposure 미확인 후보 포함): " + ", ".join(
        f"{d} {n}({100*n//total_fam_periods}%)" for d, n in dom_fam.most_common()))
    print("밀도 목표(감수 14차 분리): 구조 품질=structural incident 별도 추적(현재 상단) · "
          "사용자 노출 밀도=exposure-qualified incident ≤1.5")
    fanout_max = max((s["max_cause_fanout"] for s in totals), default=0)
    print(f"단일 원인 활성 family 확산 max: {fanout_max} (목표 ≤2, 예외 3)")

    for label, prefix, note in (
        ("REL 차수 지표(감수 16차)", "rel", "목표 ≤1 · 독립 발현 형태 예외 2"),
        ("MOV 차수 지표(감수 18차)", "mov", "목표 ≤1 · 독립 발현 형태 예외 2"),
        ("HLT 차수 지표(감수 21차)", "hlt", "목표 ≤1 · 독립 발현 형태 예외 2"),
        ("LEG 재검토 지표(감수 23차)", "leg", "목표 ≤1 · 독립 발현 형태 예외 2"),
    ):
        fam_all_d = [x for s in totals for x in s.get(f"{prefix}_family_per_period", [])]
        fanout_d = max((s.get(f"{prefix}_max_cause_fanout", 0) for s in totals), default=0)
        roles_d: Counter = Counter()
        for s in totals:
            roles_d.update(s.get(f"{prefix}_absorbed_roles", {}))
        print(f"\n## {label} — 컨텍스트 부재=전 항목 UNKNOWN 가정")
        print(f"활성 family/기간(해당 도메인 활성 기간 기준): p50 "
              f"{_percentile(fam_all_d, 0.5):.0f} · p90 {_percentile(fam_all_d, 0.9):.0f} "
              f"· max {max(fam_all_d, default=0)}")
        print(f"단일 원인 활성 family 확산 max: {fanout_d} ({note})")
        print(f"흡수 역할 분포(대표 수렴 실측): {dict(roles_d) or '없음'}")
    # family 목표 계층화(감수 18차 승인): 구조 진단(structural p90=중복·fanout 감시) /
    # context-exposable p90 ≤4~5 권장 / R2 최종 선별 ≤3 — raw 구조를 3으로 자르지 않는다.
    expo_fam_all = [x for s in totals for x in s.get("exposable_family_per_period", [])]
    print("\n## 노출 후보 밀도(계층화 목표 — 구조 진단/context-exposable ≤4~5/R2 선별 ≤3)")
    print(f"context-exposable family/기간: p50 {_percentile(expo_fam_all, 0.5):.0f} · "
          f"p90 {_percentile(expo_fam_all, 0.9):.0f} · max {max(expo_fam_all, default=0)} "
          f"(전 컨텍스트 UNKNOWN 가정 — 하한 추정)")
    worst = max(all_stats, key=lambda kv: max(kv[1]["family_per_period"], default=0),
                default=None)
    if worst:
        print(f"전체 family max 기간 구성({worst[0]}): "
              + ", ".join(worst[1].get("fam_max_period_composition", [])))

    # 발동률 분모 정의: 해당 위험이 1회 이상 활성인 '적용 차트'만 집계에 포함된다
    # (agg_fire에 없는 차트는 미적용). 코퍼스 평균은 적용 차트 평균이다.
    print("\n## 항목별 평균 발동률 top10 (활성 기준 · 분모=적용 차트 수)")
    warn: list[str] = []
    max_streaks: dict[str, int] = defaultdict(int)
    for _, s in all_stats:
        for rid, st in s.get("longest_streak", {}).items():
            max_streaks[rid] = max(max_streaks[rid], st)
    n_months = max((s.get("n_months", 0) for s in totals), default=0)
    for rid, rates in sorted(agg_fire.items(), key=lambda x: -sum(x[1]) / len(x[1]))[:10]:
        avg = sum(rates) / len(rates)
        n_high = sum(1 for r in rates if r > 0.4)
        streak = max_streaks.get(rid, 0)
        print(f"  - {rid}: 적용차트 평균 {_pct(avg, 1.0)} · >40% 차트 {n_high}/적용 "
              f"{len(rates)}/전체 {len(all_stats)} · 최장 연속(월) {streak}/{n_months}")
        if avg > 0.4:
            warn.append(f"{rid} 적용차트 평균 발동률 {_pct(avg, 1.0)} (>40%)")
        if n_months and streak / n_months > 0.5:
            warn.append(f"{rid} 최장 연속 발동 {streak}/{n_months}개월 (>50% — 범용 룰 의심)")
    if fanout_max > 3:
        warn.append(f"단일 원인 확산 {fanout_max} family (>3)")
    for prefix, name in (("rel", "REL"), ("mov", "MOV"), ("hlt", "HLT"),
                         ("leg", "LEG")):
        fo = max((s.get(f"{prefix}_max_cause_fanout", 0) for s in totals), default=0)
        if fo > 2:
            warn.append(f"{name} 단일 원인 확산 {fo} family (>2 — 복제 의심)")
    if n_periods and n_inc / n_periods > 1.5:
        warn.append("active incident/기간 > 1.5")
    print("\n경고 신호:" if warn else "\n경고 신호: 없음(목표 범위)")
    for w in warn:
        print(f"  ⚠ {w}")


if __name__ == "__main__":
    main()
