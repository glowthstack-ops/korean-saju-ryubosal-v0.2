"""Scoring Phase 1a — operational adjusted score(감점 계열·산출만).

operational shadow 를 **감점 2 component(A 조건부 희신/병 downgrade·B 낮은 operability 용신운)**
로만 반영한 adjusted score 를 **sidecar(candidate index 기반 list)** 로 산출한다. **actual score
아님·랭킹 미사용·LLM 미투입(1a).** `.score`/`final`/`favorability_map`/`canonical_roles`/`groups`/
신강약/polarity 불변. Option A 제외.

`apply_operational_scoring` 은 순수 함수 — **component flag·계수만** 참조(마스터 flag 미참조).
마스터 게이트는 `operational_scoring_sidecar`(호출부 wrapper)가 담당. 규격: §14
"""

from __future__ import annotations

import math

import saju_manse_analysis.yongsin.operational_role_config as _cfg
from saju_manse_analysis.yongsin.operational_role_config import (
    SHADOW_PERIOD_ELEMENT_WEIGHT,
    SHADOW_ROLE_WEIGHT,
)

from saju_shared_types.constants import BRANCH_ELEMENT, STEM_ELEMENT
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.events import EventCandidate
from saju_shared_types.manse_result import ManseV2Result

from .event_scoring import favorability_map


def apply_operational_scoring(
    result: ManseV2Result,
    candidates: list[EventCandidate],
    ganji_by_period: dict[str, str],
    *,
    components: dict[str, bool] | None = None,
    coef_override: dict[str, float] | None = None,
) -> list[dict]:
    """후보별 operational adjusted score sidecar(index 기반 list — period/event_key 충돌 무관).

    각 항목: candidate_index·period·event_key·legacy_score·operational_adjusted_score·
    operational_score_delta(≤0)·penalties(양수). ganji 없으면 missing_ganji=True·감점 0(임의 계산
    금지). component flag off → 해당 penalty 0. 둘 다 off → adjusted=legacy·delta=0.

    components/coef_override 미지정 → config 사용. 지정 시 **인자 주입만**(config 불변 — 1b 실험·
    low_op 시뮬용).
    """
    ya = result.yongsin_analysis
    if ya is None:
        return []
    legacy_role = favorability_map(result)
    legacy_weight = {el: SHADOW_ROLE_WEIGHT.get(role, 0.0)
                     for el, role in legacy_role.items()}
    op_role = {er.element: er for er in ya.operational_roles}
    yongsin_el = ya.final.get("yongsin")
    yongsin_er = op_role.get(yongsin_el) if yongsin_el else None
    yongsin_op = yongsin_er.operability if yongsin_er else None

    comp = components if components is not None else _cfg.SCORING_OPERATIONAL_COMPONENTS
    coef = {**_cfg.SCORING_OPERATIONAL_COEF, **(coef_override or {})}  # 주입만·config 불변
    ws, wb = SHADOW_PERIOD_ELEMENT_WEIGHT["stem"], SHADOW_PERIOD_ELEMENT_WEIGHT["branch"]

    out: list[dict] = []
    for i, c in enumerate(candidates):
        legacy = int(c.score)
        ganji = ganji_by_period.get(c.period, "")
        base = {"candidate_index": i, "period": c.period,
                "event_key": str(getattr(c, "event_key", "")), "legacy_score": legacy}
        if len(ganji) < 2:  # 임의 계산 금지 — skip 의미로 명시.
            out.append({**base, "operational_adjusted_score": legacy,
                        "operational_score_delta": 0, "penalties": {},
                        "missing_ganji": True})
            continue
        # 운 간지 표면 오행 가중(#9b 동일: 천간 0.5·지지 0.5).
        elw: dict[str, float] = {}
        elw[str(STEM_ELEMENT[Stem(ganji[0])])] = (
            elw.get(str(STEM_ELEMENT[Stem(ganji[0])]), 0.0) + ws)
        elw[str(BRANCH_ELEMENT[Branch(ganji[1])])] = (
            elw.get(str(BRANCH_ELEMENT[Branch(ganji[1])]), 0.0) + wb)

        penalties: dict[str, float] = {}
        # A: 조건부 희신/병 downgrade — legacy_fav>0 일 때만.
        if comp.get("conditional_byeong_downgrade"):
            wa = sum(w for el, w in elw.items()
                     if (er := op_role.get(el)) is not None
                     and er.operational_role == "조건부 희신/병"
                     and legacy_weight.get(el, 0.0) > 0)
            if wa:
                penalties["conditional_byeong_downgrade"] = round(
                    coef["byeong_max_penalty"] * wa, 2)
        # B: 낮은 operability 용신운 — 용신 오행에만.
        if (comp.get("low_operability_yongsin") and yongsin_el in elw
                and yongsin_op is not None and yongsin_op < coef["op_threshold"]):
            pb = coef["low_op_max_penalty"] * elw[yongsin_el] * (1 - yongsin_op)
            if pb:
                penalties["low_operability_yongsin"] = round(pb, 2)

        total = sum(penalties.values())
        floor = math.ceil(legacy * coef["adjusted_floor_ratio"])
        adjusted = max(floor, min(legacy, round(legacy - total)))  # 감점만·바닥 보장
        out.append({**base, "operational_adjusted_score": adjusted,
                    "operational_score_delta": adjusted - legacy,  # ≤ 0
                    "penalties": penalties})
    return out


def operational_scoring_sidecar(
    result: ManseV2Result,
    candidates: list[EventCandidate],
    ganji_by_period: dict[str, str],
) -> list[dict] | None:
    """마스터 게이트 wrapper — SCORING_OPERATIONAL_SHADOW_ENABLED off면 None(미산출).

    1a 에서는 하네스/디버그/테스트만 호출(서비스 응답·LLM·reduce_candidates 미투입).
    """
    if not _cfg.SCORING_OPERATIONAL_SHADOW_ENABLED:
        return None
    return apply_operational_scoring(result, candidates, ganji_by_period)


def _level_ranks(items: list[dict]) -> tuple[dict[int, int], dict[int, int]]:
    """level 풀 1개의 (legacy_rank, adjusted_rank) id 맵.

    legacy_rank = 입력 순서(score_legacy 반환 순서·재계산 금지).
    adjusted_rank = operational_adjusted_score 내림차순 stable 재정렬(동점=legacy order 유지).
    """
    legacy_rank = {id(s): i + 1 for i, s in enumerate(items)}
    adj_order = sorted(items, key=lambda s: -s["operational_adjusted_score"])  # stable
    adj_rank = {id(s): i + 1 for i, s in enumerate(adj_order)}
    return legacy_rank, adj_rank


def adjusted_rank_experiment(
    result: ManseV2Result,
    candidates: list[EventCandidate],
    ganji_by_period: dict[str, str],
    period_level: dict[str, str],
    *,
    components: dict[str, bool],
    coef_override: dict[str, float] | None = None,
    topn: int = 10,
) -> list[dict]:
    """adjusted rank 실험(1b) — legacy=입력 순서, adjusted=adjusted_score 재정렬. 랭킹 미교체·관찰.

    missing ganji 후보도 제거하지 않고 adjusted=legacy 로 풀에 유지(후보 수 보존). level(year/
    daewoon) 내부 rank 가 WARN 기준, global 은 참고용. 같은 후보군·legacy order 로 A/B 비교.
    op_rank_delta_level = score 베이스라인 대비 순수 operational penalty 효과(confound 제거).
    """
    side = apply_operational_scoring(result, candidates, ganji_by_period,
                                     components=components, coef_override=coef_override)
    if not side:
        return []
    # 전역(참고용) 순위 — 입력 순서 = legacy, adjusted 재정렬.
    g_legacy, g_adj = _level_ranks(side)
    # level 분리.
    by_level: dict[str, list[dict]] = {}
    for s in side:
        by_level.setdefault(period_level.get(s["period"], ""), []).append(s)

    rows: list[dict] = []
    for lv, items in by_level.items():
        legacy_rank, adj_rank = _level_ranks(items)
        adj_order = sorted(items, key=lambda s: -s["operational_adjusted_score"])
        # score 베이스라인 — penalty 0(legacy_score) 정렬. adjusted 와 같은 score 축이라
        # **순수 operational penalty 효과만** 격리(입력순서=lei_rank_key 와의 차이 confound 제거).
        sb_order = sorted(items, key=lambda s: -s["legacy_score"])
        sb_rank = {id(s): i + 1 for i, s in enumerate(sb_order)}
        topn_legacy = {id(s) for s in items[:topn]}
        topn_adj = {id(s) for s in adj_order[:topn]}
        topn_sb = {id(s) for s in sb_order[:topn]}
        for s in items:
            lr, ar, sr = legacy_rank[id(s)], adj_rank[id(s)], sb_rank[id(s)]
            rows.append({
                "candidate_index": s["candidate_index"], "period": s["period"],
                "event_key": s["event_key"], "level": lv,
                "legacy_score": s["legacy_score"],
                "operational_adjusted_score": s["operational_adjusted_score"],
                "legacy_rank_level": lr, "adjusted_rank_level": ar,
                "score_baseline_rank_level": sr,
                "rank_delta_level": ar - lr,          # vs 엔진 입력순서(참고·confound 포함)
                "op_rank_delta_level": ar - sr,       # ★ 순수 operational penalty 효과(튜닝 기준)
                "pool": len(items),
                "left_topn": id(s) in topn_legacy and id(s) not in topn_adj,
                # ★ operational 효과 기준 top-N 이탈(score 베이스라인 대비).
                "op_left_topn": id(s) in topn_sb and id(s) not in topn_adj,
                # 전역은 참고용(WARN 미사용).
                "legacy_rank_global": g_legacy[id(s)],
                "adjusted_rank_global": g_adj[id(s)],
                "missing_ganji": bool(s.get("missing_ganji")),
            })
    return rows


def rank_experiment_sidecar(
    result: ManseV2Result,
    candidates: list[EventCandidate],
    ganji_by_period: dict[str, str],
    period_level: dict[str, str],
    *,
    components: dict[str, bool] | None = None,
    coef_override: dict[str, float] | None = None,
    topn: int | None = None,
) -> list[dict] | None:
    """sub-flag 게이트 wrapper — SCORING_OPERATIONAL_RANK_EXPERIMENT_ENABLED off면 None.

    1b 에서는 하네스/리포트/테스트만 호출(서비스·reduce_candidates·LLM 미투입).
    """
    if not _cfg.SCORING_OPERATIONAL_RANK_EXPERIMENT_ENABLED:
        return None
    comp = components if components is not None else _cfg.SCORING_OPERATIONAL_COMPONENTS
    n = topn if topn is not None else _cfg.SCORING_OPERATIONAL_RANK_TOPN
    return adjusted_rank_experiment(result, candidates, ganji_by_period, period_level,
                                    components=comp, coef_override=coef_override, topn=n)


def operational_rank_guards(
    result: ManseV2Result,
    selected: list[EventCandidate],
    ganji_by_period: dict[str, str],
    *,
    domain: str | None,
) -> list[tuple[int, str]]:
    """rank guard 태그(1c-α) — reduce 후 selected 후보에 (index, reason_key). **순위·score 불변.**

    게이트 전부 만족 시에만 산출: APPLY_ENABLED ∧ rank_guard ∧ domain∈APPLY_INTENTS ∧ component≥1.
    operational_score_delta ≤ −penalty_threshold 후보만, delta 큰 순 max_guards 개. reason_key 는
    우세 penalty(conditional_byeong_downgrade·low_operability_yongsin). 실제 문구는 guard_caution_
    phrase 가 기존 caution 중복 여부로 full/compact 결정. missing ganji 미부착(임의 계산 금지).
    index 는 selected 내부 index — caution_note 와 1:1.
    """
    if not (_cfg.SCORING_OPERATIONAL_APPLY_ENABLED
            and _cfg.SCORING_OPERATIONAL_APPLY_MODE.get("rank_guard")):
        return []
    # domain 정규화(5b-2b 와 동일 표현 key) — Domain.EDUCATION.value="education"→"study_document"
    # 등 enum value/string 일관 매칭. general/미상→None→미적용.
    from .shadow_scoring import domain_to_expression_key
    key = domain_to_expression_key(domain)
    if key is None or key not in _cfg.SCORING_OPERATIONAL_APPLY_INTENTS:
        return []
    if not any(_cfg.SCORING_OPERATIONAL_COMPONENTS.values()):  # 1a component 전부 off → 무태그
        return []
    coef = _cfg.SCORING_OPERATIONAL_APPLY_COEF
    threshold = coef["penalty_threshold"]
    side = apply_operational_scoring(result, selected, ganji_by_period)
    cand: list[tuple[int, int, str]] = []
    for s in side:
        if s.get("missing_ganji") or s["operational_score_delta"] > -threshold:
            continue
        pens = s["penalties"]
        if not pens:
            continue
        key = max(pens, key=lambda k: pens[k])  # 우세 penalty → reason_key
        if key in _cfg.SCORING_OPERATIONAL_GUARD_PHRASE:
            cand.append((s["candidate_index"], -s["operational_score_delta"], key))
    cand.sort(key=lambda x: -x[1])  # 감점 큰 순
    return [(idx, reason_key) for idx, _d, reason_key in cand[:coef["max_guards"]]]


def guard_caution_phrase(reason_key: str, existing_caution: str) -> str:
    """rank guard 문구 — 기존 caution 에 과대긍정 차단 마커가 있으면 compact(지시문 중복 제거),
    없으면 full. 기존 caution 텍스트는 재작성하지 않는다(중복 지시문만 억제). spec §14-9.
    """
    has_marker = bool(existing_caution) and any(
        m in existing_caution for m in _cfg.SCORING_OPERATIONAL_REDUNDANCY_MARKERS)
    table = (_cfg.SCORING_OPERATIONAL_GUARD_PHRASE_COMPACT if has_marker
             else _cfg.SCORING_OPERATIONAL_GUARD_PHRASE)
    return table[reason_key]
