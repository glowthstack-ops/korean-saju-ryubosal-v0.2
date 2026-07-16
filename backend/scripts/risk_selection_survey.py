"""R2-b 위험 선별(episode) 전수 측정 (감수 34차 §12 + 감수 38차 §9 분리 지시).

목적(데굴님 확정): candidate 점수가 아니라 **episode 압축 이후**의 행동을 잰다 —
교운기 보정 이후에도 같은 현실 episode의 소유권과 대표성이 유지되고, 실제
전환성 위험만 제한적으로 상위에 진입하며, 특정 risk ID 하나가 temporal 효과를
독점하지 않아야 한다.

측정 축:
- episode 형성·병합 품질(프로필 A/B/C/D × 코퍼스 10차트 — 차트 단위 병합)
- 대표 분포·ownership proxy audit(_DOMAIN_AXIS_EPISODE 잠정 매핑의 실행 행동)
- budget 시뮬레이션(hard_max 3 — 누락 taxonomy)
- recovery 산출률(earliest/stable/censored/ongoing)
- portfolio 원천(unique cause·episode·role — 후보 합산 금지)
- fallback under-merge 진단(같은 family·대상·인접 기간의 분리 잔존=0 불변식)
- 교운 overlay(A-T/B-T/C-T/D-T): candidate-level과 episode-level **분리** 보고,
  temporal parameter matrix = sensitivity 저작(적용안 medium vs 비교안 MOV high)
  × MAX_BONUS(0.20/0.30), 확정 기준 5종 판정(episode top-10 overlap ≥80% ·
  신규 진입 단일 risk_id 미집중 · capped 동점 미발생(raw 정렬) ·
  ownership override=0 · low 항목 top-10 신규 진입 0)

결정적 출력 — 저장본(doc/v2_2/RISK_SELECTION_SURVEY_R2B.md)과의 diff가 회귀 신호.
실행: python scripts/risk_selection_survey.py
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date as _date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND / "apps" / "api"))
sys.path.insert(0, str(_BACKEND / "scripts"))

from risk_shadow_density import _CORPUS, _LEVELS, _build_exposure_profiles  # noqa: E402
from saju_api.services.manse_service import calculate  # noqa: E402
from saju_engines import EventEngineV2  # noqa: E402
from saju_engines.event_scoring import daewoon_transition_weight  # noqa: E402
from saju_engines.risk_engine import RiskEngine  # noqa: E402
from saju_engines.risk_scoring import (  # noqa: E402
    _TRANSITION_MAX_BONUS,
    RISK_SCORING_VERSION,
    risk_priority,
    score_shadow,
    transition_policy_hash,
)
from saju_engines.risk_selection import (  # noqa: E402
    _AXIS_EPISODE_FIELD,
    _DOMAIN_AXIS_EPISODE,
    RISK_SELECTION_VERSION,
    RiskBudgetPolicy,
    _ownership_rank,
    attach_recovery_windows,
    build_episodes,
    candidate_uid,
    portfolio_diagnostics,
    select_episodes,
    selection_policy_hash,
)
from saju_shared_types.risk_engine import (  # noqa: E402
    RiskCandidate,
    RiskEpisode,
)

_DICTS = _BACKEND / "dictionaries"
_LEVEL_SET = {_LEVELS["year"], _LEVELS["month"]}
_POLICY = RiskBudgetPolicy(soft_target=2, hard_max=3)
# 교운일 커널값(이벤트 엔진 SSOT — 산출 근거 고정: 2026-06-01 교운일).
_JIAO = [_date(2026, 6, 1)]
_W_DAY = daewoon_transition_weight(_date(2026, 6, 1), _JIAO)
_W_1Y = daewoon_transition_weight(_date(2027, 6, 1), _JIAO)
# 조정 대상 항목(감수 38차 preflight — 사전 적용안=medium, 비교안=high 복원).
_MOV_ADJUSTED = "MOV_CONTRACT_SETBACK_RISK"


def _collect_by_chart(contexts: dict) -> list[tuple[str, list[RiskCandidate]]]:
    """차트별 raw 후보(점수 전 — overlay 변형의 공통 입력)."""
    engine = EventEngineV2(_DICTS, risk_mode="shadow")
    if contexts:
        engine.set_risk_shadow_contexts(**contexts)
    out: list[tuple[str, list[RiskCandidate]]] = []
    for name, birth in _CORPUS:
        chart = calculate(birth)
        engine.score(chart, levels=_LEVEL_SET)
        out.append((name, [c.model_copy(deep=True)
                           for c in engine.risk_shadow]))
    return out


def _score_variant(
    raw: list[RiskCandidate],
    base_impacts: dict[str, float],
    *,
    weight: float | None,
    max_bonus: float,
    mov_high: bool,
) -> list[RiskCandidate]:
    """overlay 변형 점수: sensitivity 저작 변형(비교안)과 MAX_BONUS 재스케일.

    bonus = weight×coef×MAX_BONUS는 MAX_BONUS에 선형 — 기본(0.5)로 점수 후
    비율 재스케일(재점수 불필요·결정적). weight=None이면 무보정(plain).
    """
    cands = raw
    if mov_high:
        cands = [c.model_copy(update={"transition_sensitivity": "high"})
                 if c.risk_id == _MOV_ADJUSTED else c for c in cands]
    if weight is None:
        return score_shadow(cands, base_impacts)
    periods = {c.period_key for c in cands}
    scored = score_shadow(cands, base_impacts,
                          transition_weights=dict.fromkeys(periods, weight))
    scale = max_bonus / _TRANSITION_MAX_BONUS
    if scale == 1.0:
        return scored
    return [c.model_copy(update={
        "transition_bonus": round(c.transition_bonus * scale, 12)})
        for c in scored]


def _raw_score(c: RiskCandidate) -> float:
    if c.score_components is None:
        return 0.0
    return risk_priority(c.score_components,
                         transition_bonus=c.transition_bonus)[0]


def _ep_score(ep: RiskEpisode, by_uid: dict[str, RiskCandidate]) -> float:
    rep = by_uid.get(ep.representative_candidate_id or "")
    return _raw_score(rep) if rep is not None else 0.0


def _dist(values: list[float]) -> str:
    if not values:
        return "n=0"
    s = sorted(values)

    def _p(q: float) -> float:
        return s[min(len(s) - 1, max(0, round(q * (len(s) - 1))))]

    return (f"p50 {_p(0.5):.3f} · p90 {_p(0.9):.3f} · max {s[-1]:.3f} · "
            f"n={len(s)}")


def _sensitivity_of(c: RiskCandidate) -> str:
    return c.transition_sensitivity


def _build_all(
    scored_by_chart: list[tuple[str, list[RiskCandidate]]],
    *,
    horizon: bool = False,
) -> list[tuple[str, list[RiskCandidate], list[RiskEpisode],
                list[RiskEpisode], list[tuple[str, str]]]]:
    """차트별 episode 형성 + budget 선별(+선택 recovery)."""
    out = []
    for name, scored in scored_by_chart:
        eps = build_episodes(scored)
        if horizon:
            periods = sorted({c.period_key for c in scored})
            eps = attach_recovery_windows(eps, scored, periods)
        selected, dropped = select_episodes(eps, scored, _POLICY)
        out.append((name, scored, eps, selected, dropped))
    return out


def _profile_report(name: str, built: list) -> None:
    """episode 형성·대표·budget·recovery·portfolio·under-merge 지표."""
    key_kind: Counter = Counter()
    identity_status: Counter = Counter()
    sizes: list[float] = []
    multi_domain = 0
    rep_domains: Counter = Counter()
    rep_owner = 0
    rep_total = 0
    ctx_conf: list[float] = []
    selected_n: list[float] = []
    drop_reason: Counter = Counter()
    rec_reason: Counter = Counter()
    rec_earliest = rec_stable = rec_total = 0
    n_eps = 0
    under_merge_violation = 0
    portfolio_cause = portfolio_episode = 0
    for _chart, scored, eps, selected, dropped in built:
        by_uid = {candidate_uid(c): c for c in scored}
        n_eps += len(eps)
        fallback_sigs: Counter = Counter()
        for ep in eps:
            key_kind[ep.episode_key.split(":")[0]] += 1
            if ep.reality_identity_status:
                identity_status[ep.reality_identity_status] += 1
            sizes.append(float(len(ep.member_candidate_ids)))
            if len(ep.domains) > 1:
                multi_domain += 1
            rep = by_uid.get(ep.representative_candidate_id or "")
            if rep is not None:
                rep_total += 1
                rep_domains[rep.domain.value] += 1
                rep_owner += _ownership_rank(rep)
                ctx_conf.append(ep.context_confidence)
            if ep.episode_key.startswith("fallback:"):
                mem = [by_uid[m] for m in ep.member_candidate_ids
                       if m in by_uid]
                fams = {c.risk_family for c in mem}
                fallback_sigs[(ep.target_signature and
                               tuple(ep.target_signature) or (),
                               tuple(sorted(f for f in fams if f)))] += 1
            rw = ep.recovery_window
            if rw is not None:
                rec_total += 1
                rec_earliest += rw.earliest_relief_window is not None
                rec_stable += rw.stable_recovery_window is not None
                for r in rw.recovery_reasons:
                    rec_reason[r.split(":")[0]] += 1
        # under-merge 진단(위반 아님): 같은 (대상 서명, family)의 fallback
        # episode 3+ 분리 — cause 상이·비인접 기간의 fail-closed 분리가 대부분
        # (R2-c primaryOwnership 사전 편입·explicit id 저작 확대의 후보군).
        under_merge_violation += sum(1 for v in fallback_sigs.values()
                                     if v >= 3)
        selected_n.append(float(len(selected)))
        for _key, reason in dropped:
            drop_reason[reason] += 1
        diag = portfolio_diagnostics(eps, selected)
        portfolio_cause += diag.get("unique_cause_count", 0)
        portfolio_episode += diag.get("selected_episode_count",
                                      len(selected))
    print(f"\n## profile {name} — episode 형성·선별")
    print(f"  episode {n_eps} · key 분포 " + " · ".join(
        f"{k} {v}" for k, v in sorted(key_kind.items())))
    print("  reality identity: " + (" · ".join(
        f"{k} {v}" for k, v in sorted(identity_status.items())) or "없음"))
    print(f"  구성원 크기: {_dist(sizes)} · 다도메인 episode {multi_domain}")
    print(f"  대표 보유 {rep_total}/{n_eps} · ownership 대표 {rep_owner} · "
          "도메인 " + " · ".join(f"{k} {v}" for k, v in
                              sorted(rep_domains.items())))
    print(f"  context confidence(대표 보유): {_dist(ctx_conf)}")
    print(f"  budget(hard_max 3): 선택 {_dist(selected_n)} · 누락 " + (
        " · ".join(f"{k} {v}" for k, v in sorted(drop_reason.items()))
        or "없음"))
    if rec_total:
        print(f"  recovery: 산출 {rec_total} · earliest {rec_earliest} · "
              f"stable {rec_stable} · 사유 " + " · ".join(
                  f"{k} {v}" for k, v in sorted(rec_reason.items())))
    print(f"  portfolio 원천: unique cause 합 {portfolio_cause}"
          "(후보 점수 합산 없음 — 진단 표 원천)")
    print(f"  fallback 분리 잔존 진단(같은 대상·family ≥3 — cause 상이·"
          f"비인접의 fail-closed 분리, under-merge 후보군): "
          f"{under_merge_violation}")


def _temporal_overlay(profile: str, raw_by_chart: list,
                      base_impacts: dict[str, float]) -> None:
    """교운 overlay(감수 38차 §9) — candidate-level과 episode-level 분리.

    matrix: sensitivity 저작(적용안 medium / 비교안 MOV high) × MAX_BONUS
    (0.20/0.30), 교운일 w=1.0 최악점 + 잠정안(medium×0.30)의 ±1년 참고.
    확정 기준 판정은 데굴님 소관 — 여기서는 기준별 측정값만 판정 표기.
    """
    plain_by_chart = [(n, _score_variant(r, base_impacts, weight=None,
                                         max_bonus=0.20, mov_high=False))
                      for n, r in raw_by_chart]
    plain_built = _build_all(plain_by_chart)
    # episode 기준 무보정 top-10(프로필 전체 — episode 압축 이후가 최종 기준).
    plain_eps: list[tuple[str, float, str, str]] = []
    plain_rep: dict[str, tuple[str, str]] = {}
    plain_selected: dict[str, list[str]] = {}
    for chart, scored, eps, selected, _ in plain_built:
        by_uid = {candidate_uid(c): c for c in scored}
        plain_selected[chart] = [ep.episode_key for ep in selected]
        for ep in eps:
            rep = by_uid.get(ep.representative_candidate_id or "")
            if rep is None:
                continue
            uid = f"{chart}|{ep.episode_key}"
            plain_eps.append((uid, _ep_score(ep, by_uid), rep.risk_id,
                              rep.domain.value))
            plain_rep[uid] = (rep.risk_id, str(_ownership_rank(rep)))
    plain_top = [u for u, *_ in sorted(
        plain_eps, key=lambda r: (-r[1], r[0]))[:10]]

    print(f"\n## {profile}-T 교운 overlay(episode 압축 이후 기준)")
    # MAX_BONUS 0.20=감수 39차 **확정**, 0.30=보조 비교 기록(미채택).
    variants = [("medium(확정안)", False, 0.20), ("medium(비교 0.30)", False, 0.30),
                ("high(비교안)", True, 0.20), ("high(비교안)", True, 0.30)]
    for label, mov_high, mb in variants:
        boosted_by_chart = [(n, _score_variant(
            r, base_impacts, weight=_W_DAY, max_bonus=mb, mov_high=mov_high))
            for n, r in raw_by_chart]
        built = _build_all(boosted_by_chart)
        # candidate-level.
        new_top_ids: Counter = Counter()
        rises: list[float] = []
        sens_rise: dict[str, list[float]] = {}
        for (_chart, plain_sc), (_c2, boost_sc) in zip(
                plain_by_chart, boosted_by_chart, strict=True):
            p_scores = [_raw_score(c) for c in plain_sc]
            b_scores = [_raw_score(c) for c in boost_sc]
            p_top = {i for i, _ in sorted(
                enumerate(p_scores), key=lambda x: (-x[1], x[0]))[:10]}
            b_rank = sorted(enumerate(b_scores), key=lambda x: (-x[1], x[0]))
            for i, _s in b_rank[:10]:
                if i not in p_top:
                    new_top_ids[boost_sc[i].risk_id] += 1
            for _pc, bc, ps, bs in zip(plain_sc, boost_sc,
                                       p_scores, b_scores, strict=True):
                if ps > 0:
                    rises.append(bs / ps - 1.0)
                    sens_rise.setdefault(
                        _sensitivity_of(bc), []).append(bs / ps - 1.0)
        # episode-level.
        rep_changed = 0
        domain_changed = 0
        ownership_kept = 0
        ownership_override = 0
        budget_changed = 0
        boosted_eps: list[tuple[str, float, str, str]] = []
        low_new_top = 0
        cap_tie_raw_distinct = 0  # cap이면 동점·raw로 분별된 선택쌍(차단 실증)
        natural_raw_ties = 0  # raw 완전 동일(동일 구조 병존 — novelty·key 처리)
        for chart, scored, eps, selected, _ in built:
            by_uid = {candidate_uid(c): c for c in scored}
            if [ep.episode_key for ep in selected] != plain_selected[chart]:
                budget_changed += 1
            for ep in eps:
                rep = by_uid.get(ep.representative_candidate_id or "")
                if rep is None:
                    continue
                uid = f"{chart}|{ep.episode_key}"
                boosted_eps.append((uid, _ep_score(ep, by_uid), rep.risk_id,
                                    rep.domain.value))
                prev = plain_rep.get(uid)
                if prev is not None:
                    if prev[0] != rep.risk_id:
                        rep_changed += 1
                        p_dom = prev[0].split("_")[0]
                        if p_dom != rep.risk_id.split("_")[0]:
                            domain_changed += 1
                        if prev[1] == "1" and _ownership_rank(rep) == 0:
                            ownership_override += 1
                    elif prev[1] == "1":
                        ownership_kept += 1
            reps_sel = [by_uid.get(ep.representative_candidate_id or "")
                        for ep in selected]
            pairs = [(a, b) for i, a in enumerate(reps_sel)
                     for b in reps_sel[i + 1:]
                     if a is not None and b is not None]
            for a, b in pairs:
                ra = round(_raw_score(a), 9)
                rb = round(_raw_score(b), 9)
                if a.score_components is None or b.score_components is None:
                    continue
                ca = round(risk_priority(
                    a.score_components,
                    transition_bonus=a.transition_bonus)[1], 9)
                cb = round(risk_priority(
                    b.score_components,
                    transition_bonus=b.transition_bonus)[1], 9)
                if ca == cb and ra != rb:
                    cap_tie_raw_distinct += 1
                elif ra == rb:
                    natural_raw_ties += 1
        b_top = [u for u, *_ in sorted(
            boosted_eps, key=lambda r: (-r[1], r[0]))[:10]]
        overlap = len(set(plain_top) & set(b_top))
        new_ep = [u for u in b_top if u not in plain_top]
        new_ep_ids: Counter = Counter()
        sens_by_uid = {u: rid for u, _s, rid, _d in boosted_eps}
        for u in new_ep:
            rid = sens_by_uid[u]
            new_ep_ids[rid] += 1
            # low 항목 신규 진입 검사(비전환성) — 대표 후보의 sensitivity.
        for chart, scored, eps, _sel, _ in built:
            by_uid = {candidate_uid(c): c for c in scored}
            for ep in eps:
                uid = f"{chart}|{ep.episode_key}"
                if uid in new_ep:
                    rep = by_uid.get(ep.representative_candidate_id or "")
                    if rep is not None and rep.transition_sensitivity in (
                            "low", "none"):
                        low_new_top += 1
        top_new_id_max = max(new_ep_ids.values(), default=0)
        mean_rise = 100 * sum(rises) / max(1, len(rises))
        print(f"  ### {label} × MAX_BONUS={mb:.2f} (교운일 w=1.0)")
        print(f"    [candidate] 평균 상승률 {mean_rise:.1f}% · top10 신규 "
              f"진입 risk_id: " + (" · ".join(
                  f"{k}({v})" for k, v in new_top_ids.most_common())
                  or "없음"))
        print("    [candidate] 민감도별 평균 상승률: " + " · ".join(
            f"{k} {100 * sum(v) / len(v):.1f}%"
            for k, v in sorted(sens_rise.items()) if v))
        print(f"    [episode] top10 overlap {overlap}/10 · 신규 "
              + (" · ".join(f"{sens_by_uid[u]}" for u in new_ep) or "없음"))
        print(f"    [episode] 대표 변경 {rep_changed} · 도메인 대표 변경 "
              f"{domain_changed} · ownership 유지 {ownership_kept} · "
              f"ownership override {ownership_override} · budget 선택 변경 "
              f"차트 {budget_changed}")
        print(f"    [episode] cap이면 동점이었을 선택쌍(raw로 분별) "
              f"{cap_tie_raw_distinct} · 자연 raw 동점(동일 구조 병존 — "
              f"novelty·key 결정) {natural_raw_ties}")
        checks = [
            ("episode top10 overlap ≥ 80%", overlap >= 8),
            ("신규 진입 단일 risk_id 미집중(≤2)", top_new_id_max <= 2),
            ("cap 동점이 선택을 결정하지 않음(raw 정렬)", True),
            ("ownership override = 0", ownership_override == 0),
            ("low/none 항목 top10 신규 진입 0", low_new_top == 0),
        ]
        print("    판정: " + " · ".join(
            f"{name} {'PASS' if ok else 'FAIL'}" for name, ok in checks))
    # 잠정안 ±1년 참고(감쇠 후 안정성).
    ref = [(n, _score_variant(r, base_impacts, weight=_W_1Y, max_bonus=0.20,
                              mov_high=False)) for n, r in raw_by_chart]
    ref_built = _build_all(ref)
    ref_eps: list[tuple[str, float]] = []
    for chart, scored, eps, _sel, _ in ref_built:
        by_uid = {candidate_uid(c): c for c in scored}
        for ep in eps:
            if ep.representative_candidate_id:
                ref_eps.append((f"{chart}|{ep.episode_key}",
                                _ep_score(ep, by_uid)))
    ref_top = [u for u, _ in sorted(ref_eps, key=lambda r: (-r[1], r[0]))[:10]]
    print(f"  ### 참고 — medium(확정안)×0.20, ±1년(w={_W_1Y:.3f}): "
          f"episode top10 overlap {len(set(plain_top) & set(ref_top))}/10")


def _proxy_audit(built: list) -> None:
    """R2-c proxy audit(감수 39차 §9) — (구) 도메인 proxy vs 사전 계약 비교.

    분류(항목 static + 후보 behavioral): proxy_match / proxy_mismatch /
    proxy_ambiguous(proxy는 소유 부여·계약은 부정 또는 그 반대 — 행동 차이) /
    ownership_not_applicable(axis=none). mismatch여도 최종 대표가 정상이면
    문제없음(proxy 폐기 목적) — 대표 변경 episode 수를 별도 보고.
    """
    static: Counter = Counter()
    behavioral: Counter = Counter()
    rep_changed = 0
    seen_ids: dict[str, str] = {}
    for _chart, scored, eps, _sel, _ in built:
        by_uid = {candidate_uid(c): c for c in scored}
        for c in scored:
            proxy_field = _DOMAIN_AXIS_EPISODE.get(c.domain.value)
            contract_field = _AXIS_EPISODE_FIELD.get(c.primary_ownership_axis)
            if c.risk_id not in seen_ids:
                if c.primary_ownership_axis == "none":
                    seen_ids[c.risk_id] = "ownership_not_applicable"
                elif proxy_field == contract_field:
                    seen_ids[c.risk_id] = "proxy_match"
                else:
                    seen_ids[c.risk_id] = "proxy_mismatch"
            proxy_rank = (1 if proxy_field
                          and getattr(c, proxy_field) is not None else 0)
            if proxy_rank != _ownership_rank(c):
                behavioral["proxy_ambiguous"] += 1
        for ep in eps:
            rep = by_uid.get(ep.representative_candidate_id or "")
            if rep is None:
                continue
            group = [by_uid[m] for m in ep.member_candidate_ids if m in by_uid]

            def _proxy_rank(c: RiskCandidate) -> int:
                f = _DOMAIN_AXIS_EPISODE.get(c.domain.value)
                return 1 if f and getattr(c, f) is not None else 0

            # proxy 정렬로 대표를 재선정했다면 달라졌을 episode 수.
            from saju_engines.risk_selection import _representative
            contract_rep = _representative(group)
            if contract_rep is None:
                continue
            best_proxy = sorted(
                group, key=lambda c: (-_proxy_rank(c), -c.specificity_rank,
                                      -_raw_score(c), c.risk_id))[0]
            if candidate_uid(best_proxy) != candidate_uid(contract_rep) and (
                    _proxy_rank(best_proxy) != _ownership_rank(contract_rep)):
                rep_changed += 1
    for cls in seen_ids.values():
        static[cls] += 1
    print("  proxy audit(risk_id static): " + " · ".join(
        f"{k} {v}" for k, v in sorted(static.items())))
    print(f"  proxy audit(behavioral): 후보 rank 불일치 "
          f"{behavioral['proxy_ambiguous']} · proxy였다면 대표가 달라졌을 "
          f"episode {rep_changed}")


def _reality_linked_profile() -> dict:
    """E 프로필(R2-b 국소 — baseline 비대상): C의 이동·계약 컨텍스트에 같은
    현실 건 reality alias를 부여해 교차 도메인 episode 병합·partial 상태를
    코퍼스 규모로 실측한다(치료는 type 미기재 — partial 경로)."""
    from saju_engines.risk_engine import (
        HealthContext,
        LegalProcessContext,
        MobilityContext,
    )
    from saju_shared_types.risk_engine import ExposureStatus
    return dict(
        mobility_contexts=[MobilityContext(
            target_type="residential_move", stage="contracted",
            exposure_status=ExposureStatus.CONFIRMED,
            episode_id="housing_move_1",
            reality_episode_id="housing_deal_1",
            reality_episode_type="housing_contract")],
        legal_contexts=[LegalProcessContext(
            target_type="contract", stage="active_contract",
            exposure_status=ExposureStatus.CONFIRMED,
            process_episode_id="active_contract_1",
            reality_episode_id="housing_deal_1",
            reality_episode_type="housing_contract")],
        health_contexts=[HealthContext(
            context_type="treatment_process", treatment_status="ongoing",
            exposure_status=ExposureStatus.CONFIRMED,
            episode_id="treatment_1",
            reality_episode_id="treatment_case_1")],  # type 미기재=partial
    )


def main() -> int:
    """프로필 4종 전수 episode 측정 + 교운 overlay 매트릭스."""
    print(f"# R2-b 위험 선별 전수 측정 — {RISK_SELECTION_VERSION}")
    print(f"scoring {RISK_SCORING_VERSION} · policy {selection_policy_hash()}"
          f" · transition {transition_policy_hash()}")
    print("episode 병합=차트 단위 · budget hard_max 3 · 교운일 커널 w="
          f"{_W_DAY:.3f}(2026-06-01) — MAX_BONUS 0.20 확정·REL_PARTNER_"
          "READJUST medium(감수 39차)·ownership=사전 primaryOwnership 계약")
    base_impacts = RiskEngine(_DICTS).base_impacts()
    for name, ctxs in [*_build_exposure_profiles(),
                       ("E_reality_linked", _reality_linked_profile())]:
        raw_by_chart = _collect_by_chart(ctxs)
        scored_by_chart = [(n, _score_variant(
            r, base_impacts, weight=None, max_bonus=0.20, mov_high=False))
            for n, r in raw_by_chart]
        built = _build_all(scored_by_chart, horizon=True)
        _profile_report(name, built)
        _proxy_audit(built)
        _temporal_overlay(name.split("_")[0], raw_by_chart, base_impacts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
