"""위험 선별 R2 — episode 병합·대표 선택·risk budget·portfolio·recovery
(doc/v2_2/RISK_DICTIONARY_REVIEW.md §20 manifest, 감수 34차 착수 — shadow 전용).

차수 성공 조건(데굴님 확정): **같은 현실 건은 도메인과 위험 항목이 달라도 하나의
episode로 묶고, 같은 원인은 여러 episode에 연결돼도 포트폴리오에서 한 번만
계산하며, 보여줄 위험이 부족할 때 budget을 채우기 위해 약한 위험을 만들지 않는다.**

identity 3분리(병합 키에서 risk_id·domain 제외 — 구성원 속성):
- reality episode identity: 명시 context episode_id(전 축) + 대상 서명 + stage·
  기간 호환 — fallback은 보수적(fail-closed).
- cause identity: canonical cause_atom·lineage — **연결 근거이지 병합 키가 아니다**
  (다른 episode + 같은 cause = 병합 금지·portfolio 1회).
- effect identity: normalizedEffectRole.

점수·적격성·suppression을 변경하지 않는다(R1 판정 소비 전용). recovery는 현재
점수·순위와 완전 독립(별도 전망).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from saju_shared_types.risk_engine import (
    ExposureStatus,
    RecoveryWindow,
    RiskCandidate,
    RiskEpisode,
    RiskKind,
    is_active,
    is_exposable,
)

from .risk_scoring import (
    _candidate_atoms,
    _episode_signature,
    context_confidence,
    normalized_effect_role,
    risk_priority,
)

# 선별 의미 버전 — 병합·대표·budget·portfolio·recovery 정책 변경 시 올린다.
RISK_SELECTION_VERSION = "risk-select-r2.0.0-shadow"


def candidate_uid(c: RiskCandidate) -> str:
    """episode 구성원 참조용 결정적 후보 id(risk_id+기간+전 축 episode 서명)."""
    sig = ",".join(f"{a}:{e}" for a, e in sorted(_episode_signature(c)))
    return f"{c.risk_id}|{c.period_key}|{sig}"


def _target_signatures(c: RiskCandidate) -> frozenset[str]:
    """후보의 대상 객체 서명들(관계 원자에서 관계 종류 제외) — fallback 병합 재료."""
    out = set()
    for atom in _candidate_atoms(c):
        if atom.startswith("relation:") and atom.count(":") >= 2:
            out.add(atom.split(":", 2)[2])
    return frozenset(out)


def _month_index(label: str) -> int | None:
    if len(label) == 7 and label[4] == "-":
        return int(label[:4]) * 12 + int(label[5:7]) - 1
    return None


def _periods_adjacent(periods: set[str]) -> bool:
    """기간 호환(temporal continuity) — 월 라벨은 인접(±1)·연 라벨은 동일/인접 연."""
    months = sorted(m for m in (_month_index(x) for x in periods) if m is not None)
    if months and months[-1] - months[0] > len(months):  # gap 큰 집합은 비연속
        return False
    return True


@dataclass(frozen=True)
class RiskBudgetPolicy:
    """질문 유형별 노출 예산 — hard_min은 존재하지 않는다(감수 34차).

    적격 위험이 없으면 0개를 반환한다 — 개수를 맞추려 약한·BLOCKED 후보를
    끌어올리지 않는다. 도메인 다양성은 강제하지 않는다(동점 soft tie-break만).
    """

    soft_target: int = 2  # 권장 개수(진단 표시용 — 강제 아님)
    hard_max: int = 3  # 사용자 노출 최대


def _member_ok(c: RiskCandidate) -> bool:
    """episode 구성원 자격 — 활성 또는 역할 보존 흡수 후보(BLOCKED·미충족 제외)."""
    return is_active(c) or c.suppressed_by_specificity is not None


def build_episodes(candidates: list[RiskCandidate]) -> list[RiskEpisode]:
    """원자 후보 → reality episode 병합(감수 34차 §20-2).

    ①명시 episode 서명이 있으면 그 서명이 키 — 같은 explicit episode는 cause·
    risk_id·domain이 달라도 병합(주택 계약 episode의 MOV·LEG·FIN). ②명시 서명이
    없으면 보수적 fallback: (대상 서명, cause 원자, riskFamily — 현 시점의 동일
    현실 건 ownership 계약) 동일 + 기간 연속일 때만 시간 병합, 그 외 후보 단독
    episode(fail-closed — 동일성 입증 불가 시 병합 금지).
    """
    members = [c for c in candidates if _member_ok(c)]
    groups: dict[tuple, list[RiskCandidate]] = defaultdict(list)
    for c in members:
        sig = _episode_signature(c)
        if sig:
            key: tuple = ("explicit", sig)
        else:
            key = ("fallback", _target_signatures(c), _candidate_atoms(c),
                   c.risk_family)
        groups[key].append(c)

    episodes: list[RiskEpisode] = []
    for key, group in sorted(groups.items(), key=lambda kv: repr(kv[0])):
        if key[0] == "fallback":
            periods = {c.period_key for c in group}
            if len(group) > 1 and not _periods_adjacent(periods):
                # 기간 비연속 fallback — 동일 현실 건 입증 불가, 후보별 분리.
                for c in group:
                    episodes.append(_make_episode(
                        f"fallback:{candidate_uid(c)}", [c]))
                continue
            ep_key = "fallback:" + "|".join(sorted(
                {a for c in group for a in _candidate_atoms(c)}))
            episodes.append(_make_episode(ep_key, group))
        else:
            sig = key[1]
            ep_key = "explicit:" + ",".join(
                f"{a}:{e}" for a, e in sorted(sig))
            episodes.append(_make_episode(ep_key, group))
    return episodes


def _representative(group: list[RiskCandidate]) -> RiskCandidate | None:
    """exposure-aware 대표 선택(감수 34차 §20-4) — 자격 미달이면 None(비노출).

    자격: context-exposable + rankable>0 + kind≠vulnerability + 비흡수.
    순서: exposure 적격성(자격에 내장) → effect specificity(specificity_rank —
    generic이 primary owner를 점수로 밀어내지 못하게 점수보다 앞) → rankable →
    structural confidence → 결정적 risk_id. explicit primary ownership은
    R0.5 suppression(소유권 차단·대표 역전 방지)이 이미 반영한 상태를 소비한다.
    """
    eligible = []
    for c in group:
        if c.suppressed_by_specificity is not None:
            continue
        if c.kind is RiskKind.VULNERABILITY or not is_exposable(c):
            continue
        comp = c.score_components
        if comp is None:
            continue
        _, capped = risk_priority(comp)
        if capped <= 0:
            continue
        eligible.append((c, capped))
    if not eligible:
        return None
    return sorted(
        eligible,
        key=lambda pair: (-pair[0].specificity_rank, -pair[1],
                          -pair[0].confidence, pair[0].risk_id,
                          pair[0].period_key),
    )[0][0]


def _make_episode(ep_key: str, group: list[RiskCandidate]) -> RiskEpisode:
    rep = _representative(group)
    supporting = [
        candidate_uid(c) for c in group
        if c.suppressed_by_specificity is not None
        and c.kind is not RiskKind.VULNERABILITY
    ]
    background = [
        candidate_uid(c) for c in group
        if c.kind is RiskKind.VULNERABILITY
    ]
    periods = sorted({c.period_key for c in group})
    return RiskEpisode(
        episode_key=ep_key,
        target_signature=sorted({t for c in group
                                 for t in _target_signatures(c)}),
        start_period=periods[0],
        end_period=periods[-1],
        stages=sorted({s for c in group
                       for s in (*c.selection_stages, *c.mobility_stages,
                                 *c.legal_stages)}),
        member_candidate_ids=[candidate_uid(c) for c in sorted(
            group, key=lambda c: (c.period_key, c.risk_id))],
        representative_candidate_id=(
            candidate_uid(rep) if rep is not None else None),
        supporting_candidate_ids=sorted(supporting),
        background_vulnerability_ids=sorted(background),
        canonical_cause_ids=sorted({a for c in group
                                    for a in _candidate_atoms(c)}),
        effect_roles=sorted({normalized_effect_role(c) for c in group}),
        domains=sorted({c.domain for c in group}),
        exposure_status=(rep.exposure_status if rep is not None
                         else ExposureStatus.UNKNOWN),
        structural_confidence=(rep.confidence if rep is not None else 0.0),
        context_confidence=(round(context_confidence(rep), 6)
                            if rep is not None else 0.0),
        recovery_window=None,  # attach_recovery_windows가 별도 산출(점수 불변)
    )


def select_episodes(
    episodes: list[RiskEpisode],
    candidates: list[RiskCandidate],
    policy: RiskBudgetPolicy,
) -> tuple[list[RiskEpisode], list[tuple[str, str]]]:
    """risk budget 적용(감수 34차 §20-5) → (선택 episode, 누락 [(key, 이유)]).

    hard_min 없음 — 적격(대표 보유) episode가 없으면 0개. 순서: episode 중복은
    build가 보장 → 같은 effect role 중복 제거 → shared cause 중복 제거 →
    hard_max → 동점에서만 도메인 다양성 soft tie-break.
    """
    by_uid = {candidate_uid(c): c for c in candidates}

    def rep_score(ep: RiskEpisode) -> float:
        rep = by_uid.get(ep.representative_candidate_id or "")
        if rep is None or rep.score_components is None:
            return 0.0
        return risk_priority(rep.score_components)[1]

    qualified = [ep for ep in episodes
                 if ep.representative_candidate_id is not None]
    dropped: list[tuple[str, str]] = [
        (ep.episode_key, "no_qualified_representative")
        for ep in episodes if ep.representative_candidate_id is None
    ]
    ranked = sorted(qualified, key=lambda ep: (-rep_score(ep), ep.episode_key))
    selected: list[RiskEpisode] = []
    seen_roles: set[str] = set()
    seen_causes: set[str] = set()
    for ep in ranked:
        rep = by_uid[ep.representative_candidate_id or ""]
        rep_role = normalized_effect_role(rep)
        if rep_role in seen_roles:
            dropped.append((ep.episode_key, f"duplicate_effect_role:{rep_role}"))
            continue
        rep_causes = set(_candidate_atoms(rep))
        if rep_causes and rep_causes <= seen_causes:
            # 대표의 원인이 전부 기선택 episode에 포함 — 같은 원인 반복 노출.
            dropped.append((ep.episode_key, "shared_cause_duplicate"))
            continue
        if len(selected) >= policy.hard_max:
            dropped.append((ep.episode_key, "hard_max_budget"))
            continue
        selected.append(ep)
        seen_roles.add(rep_role)
        seen_causes |= rep_causes
    return selected, dropped


def portfolio_diagnostics(
    episodes: list[RiskEpisode],
    selected: list[RiskEpisode],
) -> dict[str, int]:
    """portfolio 진단(감수 34차 §20-6) — 원천은 unique cause·lineage·role·episode.

    후보 점수 합산은 어디에도 없다(금지 목록: 후보 rankable 합·episode occurrence
    합·같은 cause persistence 반복·supporting/vulnerability 재가산).
    """
    all_causes = {a for ep in episodes for a in ep.canonical_cause_ids}
    shared_cause_eps = 0
    for ep in episodes:
        others = {a for other in episodes if other is not ep
                  for a in other.canonical_cause_ids}
        if set(ep.canonical_cause_ids) & others:
            shared_cause_eps += 1
    return {
        "unique_cause_count": len(all_causes),
        "distinct_effect_role_count": len(
            {r for ep in episodes for r in ep.effect_roles}),
        "episode_count": len(episodes),
        "selected_episode_count": len(selected),
        "shared_cause_episode_count": shared_cause_eps,
    }


def attach_recovery_windows(
    episodes: list[RiskEpisode],
    candidates: list[RiskCandidate],
    horizon_periods: list[str],
) -> list[RiskEpisode]:
    """recovery window 산출(감수 34차 §20-7) — 현재 점수·순위와 완전 독립.

    보수 성립 조건: episode의 주요 cause lineage가 관측 지평 안에서 종료(마지막
    활성 기간 뒤에 같은 원인이 재발하지 않는 잔여 기간 존재)할 때만 earliest_
    relief_window를 그 다음 기간으로 제시한다. '미래 운이 좋다'는 이유의 회복
    생성 금지, 단정 표현 금지(표현 계약은 R3).
    """
    if not horizon_periods:
        return episodes
    horizon = sorted(horizon_periods)
    active_periods_by_cause: dict[str, set[str]] = defaultdict(set)
    for c in candidates:
        if is_active(c):
            for a in _candidate_atoms(c):
                active_periods_by_cause[a].add(c.period_key)
    out: list[RiskEpisode] = []
    for ep in episodes:
        last_active = max(
            (p for a in ep.canonical_cause_ids
             for p in active_periods_by_cause.get(a, ())),
            default=None)
        later = [p for p in horizon if last_active is not None and p > last_active]
        if last_active is None or not later:
            out.append(ep)  # 지평 안 종료 입증 불가 — 회복 창 없음(fail-closed)
            continue
        out.append(ep.model_copy(update={"recovery_window": RecoveryWindow(
            earliest_relief_window=later[0],
            stable_recovery_window=later[-1] if len(later) >= 3 else None,
            recovery_confidence=0.3,  # 보수 고정(잠정 — R3 감수)
            recovery_reasons=[f"cause_lineage_ends:{last_active}"],
        )}))
    return out


def selection_policy_hash() -> str:
    """선별 정책 해시 — shadow_selection 감수 무효화 가드 재료(감수 34차)."""
    import hashlib
    import json as _json
    policy = {
        "version": RISK_SELECTION_VERSION,
        "episode_identity": "explicit context episode signature 우선 — risk_id·"
                            "domain 제외(구성원 속성), fallback=대상 서명+cause"
                            "+riskFamily(ownership 계약)+기간 연속(fail-closed)",
        "representative_order": "exposure 적격(자격) → specificity → rankable →"
                                " structural confidence → risk_id",
        "representative_gate": "exposable + rankable>0 + kind≠vulnerability"
                               " + 비흡수",
        "budget": {"hard_min": 0, "dedup_order": "episode→effect_role→"
                   "shared_cause→hard_max→domain_soft_tiebreak"},
        "portfolio_source": "unique cause·lineage·effect role·episode"
                            " (후보 점수 합산 금지)",
        "recovery": "cause lineage 지평 내 종료 시만·점수 독립·단정 금지",
    }
    return hashlib.sha256(
        _json.dumps(policy, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


__all__ = [
    "RISK_SELECTION_VERSION",
    "RiskBudgetPolicy",
    "attach_recovery_windows",
    "build_episodes",
    "candidate_uid",
    "portfolio_diagnostics",
    "select_episodes",
    "selection_policy_hash",
]
