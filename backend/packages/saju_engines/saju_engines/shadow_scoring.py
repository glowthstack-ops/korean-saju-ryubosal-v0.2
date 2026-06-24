"""operational 기반 shadow scoring (#9a) — 계산·검증 전용, **실제 scoring 미소비**.

legacy(canonical/final) 점수는 그대로 두고, operational 역할 + 용신 operability 를 반영한 shadow
가중을 병행 산출해 diff 를 본다. AggregatedYongsinResult 에 저장하지 않고 on-demand 함수로만 제공.
favorability_map / event score / 운세 랭킹 / final 은 전부 불변이다.

규칙(데굴님 승인):
- SHADOW_ROLE_WEIGHT exact label lookup 만(substring 금지). 미등록 label 은 fail-fast(KeyError).
- '조건부 희신/병' = 0.0(mixed — positive 처리 금지). '조후보조신' < 주용신/희신.
- operability 는 **용신 element 가중에만** 곱연산(비용신 미적용).
규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §10
"""

from __future__ import annotations

from saju_manse_analysis.yongsin.operational_role_config import (
    DOMAIN_EXPRESSION_PHRASE,
    EXPRESSION_BAND,
    EXPRESSION_GUIDANCE,
    EXPRESSION_OPERABILITY_THRESHOLD,
    SHADOW_PERIOD_ELEMENT_WEIGHT,
    SHADOW_ROLE_WEIGHT,
    SHADOW_SCORE_SPAN,
)

from saju_shared_types.constants import BRANCH_ELEMENT, STEM_ELEMENT
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.events import EventCandidate
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.yongsin import AggregatedYongsinResult

from .event_scoring import favorability_map


def operational_shadow_weights(ya: AggregatedYongsinResult) -> dict[str, float]:
    """operational_roles → {오행: shadow 가중}. 용신 element 는 × operability(작동성 반영).

    exact label lookup(미등록 label 은 KeyError — fail-fast). operability 가 None 이 아닌 element
    (=용신)만 가중에 operability 를 곱한다.
    """
    out: dict[str, float] = {}
    for er in ya.operational_roles:
        weight = SHADOW_ROLE_WEIGHT[er.operational_role]  # exact·fail-fast
        if er.operability is not None:
            weight = round(weight * er.operability, 4)
        out[er.element] = weight
    return out


def shadow_vs_legacy_diff(result: ManseV2Result) -> dict[str, dict]:
    """오행별 legacy(canonical) vs shadow(operational) 가중 비교(미소비·검증용).

    각 오행: legacy_role/legacy_weight(canonical) · operational_role/shadow_weight · delta.
    legacy_weight 도 동일 SHADOW_ROLE_WEIGHT 스케일로 산출해 같은 축에서 차이를 본다.
    """
    ya = result.yongsin_analysis
    if ya is None:
        return {}
    legacy_role = favorability_map(result)  # {오행: 역할(한글)} — final/canonical
    shadow = operational_shadow_weights(ya)
    out: dict[str, dict] = {}
    for er in ya.operational_roles:
        el = er.element
        lr = legacy_role.get(el)
        legacy_weight = SHADOW_ROLE_WEIGHT[lr] if lr else 0.0
        out[el] = {
            "legacy_role": lr,
            "legacy_weight": legacy_weight,
            "operational_role": er.operational_role,
            "shadow_weight": shadow[el],
            "delta": round(shadow[el] - legacy_weight, 4),
        }
    return out


def _period_element_fav(
    ganji: str,
    legacy_w: dict[str, float],
    shadow_w: dict[str, float],
) -> tuple[float, float]:
    """운 간지(천간·지지 표면 오행) → (legacy_fav, shadow_fav) 가중 평균. 지장간 미포함."""
    ws, wb = SHADOW_PERIOD_ELEMENT_WEIGHT["stem"], SHADOW_PERIOD_ELEMENT_WEIGHT["branch"]
    stem_el = str(STEM_ELEMENT[Stem(ganji[0])])
    branch_el = str(BRANCH_ELEMENT[Branch(ganji[1])])
    legacy = ws * legacy_w.get(stem_el, 0.0) + wb * legacy_w.get(branch_el, 0.0)
    shadow = ws * shadow_w.get(stem_el, 0.0) + wb * shadow_w.get(branch_el, 0.0)
    return legacy, shadow


def candidate_shadow_diff(
    result: ManseV2Result,
    candidates: list[EventCandidate],
    ganji_by_period: dict[str, str],
) -> list[dict]:
    """후보별 operational 유불리 관찰(#9b) — **미소비**. legacy score/랭킹/favorability 불변.

    candidate.score(발생 가능성)는 그대로, 운 간지 오행의 legacy vs shadow 유불리 차(fav_delta) +
    관찰용 결합값(shadow_observation_score = score + fav_delta×SPAN, 0~100 클램프)을 산출.
    shadow_observation_score 는 **실제 발생 가능성 score 가 아니라 유불리 관찰값**이다. reason ≤3.
    """
    ya = result.yongsin_analysis
    if ya is None:
        return []
    legacy_role = favorability_map(result)  # {오행: 역할(한글)}
    legacy_w = {el: SHADOW_ROLE_WEIGHT[role] for el, role in legacy_role.items()}
    shadow_w = operational_shadow_weights(ya)
    op_role = {er.element: er.operational_role for er in ya.operational_roles}
    out: list[dict] = []
    for c in candidates:
        ganji = ganji_by_period.get(c.period, "")
        if len(ganji) < 2:
            continue
        legacy_fav, shadow_fav = _period_element_fav(ganji, legacy_w, shadow_w)
        fav_delta = round(shadow_fav - legacy_fav, 4)
        obs = max(0, min(100, round(c.score + fav_delta * SHADOW_SCORE_SPAN)))
        # reason: 운 오행 중 유불리 가중이 바뀐 것(라벨 변경 또는 용신 operability) — 변화 큰 순 ≤3.
        els = {str(STEM_ELEMENT[Stem(ganji[0])]), str(BRANCH_ELEMENT[Branch(ganji[1])])}
        changed: list[tuple[float, str]] = []
        for el in els:
            diff = abs(shadow_w.get(el, 0.0) - legacy_w.get(el, 0.0))
            if diff < 1e-9:
                continue
            lr, orr = legacy_role.get(el, "?"), op_role.get(el, "?")
            if lr != orr:
                changed.append((diff, f"{el}: {lr} → {orr}"))
            else:  # 라벨 동일·가중 변화 = 용신 operability 반영
                changed.append((diff, f"{el}: {orr}이나 작동성 {shadow_w.get(el, 0.0)}"))
        reason = [txt for _d, txt in sorted(changed, key=lambda x: -x[0])[:3]]
        out.append({
            "period": c.period,
            "event_key": str(getattr(c, "event_key", "")),
            "legacy_score": c.score,
            "legacy_fav": round(legacy_fav, 4),
            "shadow_fav": round(shadow_fav, 4),
            "fav_delta": fav_delta,
            "shadow_observation_score": obs,  # ★ 관찰용 — 실제 score 아님
            "score_delta": obs - c.score,
            "reason": reason,
        })
    return out


def _rank_maps(items: list[dict]) -> tuple[dict[int, int], dict[int, int]]:
    """주어진 후보군의 legacy/shadow 순위 맵(id→순위). 동일 풀 안에서만 비교."""
    legacy_order = sorted(items, key=lambda d: -d["legacy_score"])
    shadow_order = sorted(items, key=lambda d: -d["shadow_observation_score"])
    return ({id(d): i + 1 for i, d in enumerate(legacy_order)},
            {id(d): i + 1 for i, d in enumerate(shadow_order)})


def shadow_rank_diff(
    diffs: list[dict], level_by_period: dict[str, str] | None = None
) -> list[dict]:
    """legacy vs shadow_observation 가상 순위 비교(#9b) — 관찰만. 실제 정렬·랭킹 불변.

    level_by_period 미지정: 전역 풀 순위(기존 키 legacy_rank/shadow_rank/rank_delta/rank_changed).
    지정 시: 전역(_global) + 레벨별(_level) 순위를 모두 산출한다. 대운/세운을 같은 풀에서 섞으면
    대운 1개의 shadow shift 가 세운 순위를 크게 밀어내므로(착시), 레벨별 순위로 진짜 영향을 본다.
    하위호환: legacy_rank/shadow_rank/rank_delta 는 전역(global) alias 로 유지한다.
    """
    g_legacy, g_shadow = _rank_maps(diffs)
    level_legacy: dict[int, int] = {}
    level_shadow: dict[int, int] = {}
    if level_by_period is not None:
        groups: dict[str, list[dict]] = {}
        for d in diffs:
            groups.setdefault(level_by_period.get(d["period"], ""), []).append(d)
        for items in groups.values():
            ll, ls = _rank_maps(items)
            level_legacy.update(ll)
            level_shadow.update(ls)

    out: list[dict] = []
    for d in diffs:
        lr, sr = g_legacy[id(d)], g_shadow[id(d)]
        row = {
            "period": d["period"],
            "legacy_rank": lr,            # 전역 alias(하위호환)
            "shadow_rank": sr,
            "rank_delta": sr - lr,
            "rank_changed": sr != lr,
        }
        if level_by_period is not None:
            llr, lsr = level_legacy[id(d)], level_shadow[id(d)]
            row.update({
                "legacy_rank_global": lr,
                "shadow_rank_global": sr,
                "rank_delta_global": sr - lr,
                "legacy_rank_level": llr,
                "shadow_rank_level": lsr,
                "rank_delta_level": lsr - llr,
                "rank_changed_level": lsr != llr,
            })
        out.append(row)
    return out


# 표현 등급 보수 병합 우선순위(Phase 5b-2a) — 가장 보수적(주의)일수록 앞. 천간·지지 오행이
# 다를 때 element 별 등급을 만든 뒤 가장 보수적인 것으로 병합(과한 길흉 단정 방지).
_EXPRESSION_PRIORITY = [
    "주의/흉", "조건부·유보+주의", "조건부·유보", "주의",
    "주의 속 일부 완화", "보조 긍정", "길", "중립",
]


def _element_expression_class(legacy_w: float, shadow_w: float) -> str:
    """오행 1개의 표현 등급 — legacy 밴드(±EXPRESSION_BAND) × shadow 가중. 점수 아님."""
    if legacy_w > EXPRESSION_BAND:  # legacy positive
        if shadow_w >= EXPRESSION_BAND:
            return "길"
        if shadow_w >= -0.05:
            return "조건부·유보"   # ★ 조건부 희신/병 등 — 단순 길운 승격 금지
        return "조건부·유보+주의"
    if legacy_w < -EXPRESSION_BAND:  # legacy negative
        return "주의 속 일부 완화" if shadow_w > 0.05 else "주의/흉"
    # legacy neutral
    if shadow_w > 0.05:
        return "보조 긍정"
    if shadow_w < -0.05:
        return "주의"
    return "중립"


def _merge_expression(classes: list[str]) -> str:
    """천간·지지 등급을 가장 보수적인 것으로 병합."""
    return min(classes, key=lambda c: _EXPRESSION_PRIORITY.index(c))


def luck_expression_clamp(result: ManseV2Result, ganji: str) -> dict | None:
    """운 간지 길흉 '표현 제한'(Phase 5b-2a) — **점수·랭킹 불변·문장 강도만 clamp**.

    천간·지지 오행별 표현 등급(legacy 밴드 × shadow 가중)을 만든 뒤 보수적으로 병합한다.
    운 오행이 용신이고 operability < 임계면 '용신운이나 작동성 낮아 강한 길운 단정 금지' 부기.
    조건부 희신/병은 어떤 경우에도 '길'로 승격되지 않는다(_element_expression_class).
    """
    ya = result.yongsin_analysis
    if ya is None or len(ganji) < 2:
        return None
    legacy_role = favorability_map(result)
    legacy_w = {el: SHADOW_ROLE_WEIGHT[r] for el, r in legacy_role.items()}
    shadow_w = operational_shadow_weights(ya)
    op_role = {er.element: er.operational_role for er in ya.operational_roles}
    op_value = {er.element: er.operability for er in ya.operational_roles}
    stem_el = str(STEM_ELEMENT[Stem(ganji[0])])
    branch_el = str(BRANCH_ELEMENT[Branch(ganji[1])])
    classes = [
        _element_expression_class(legacy_w.get(el, 0.0), shadow_w.get(el, 0.0))
        for el in (stem_el, branch_el)
    ]
    merged = _merge_expression(classes)
    low_op: float | None = None
    for el in (stem_el, branch_el):
        op = op_value.get(el)
        if op_role.get(el) == "용신" and op is not None and op < EXPRESSION_OPERABILITY_THRESHOLD:
            low_op = op
    return {
        "expression_class": merged,
        "guidance": EXPRESSION_GUIDANCE[merged],
        "low_operability": low_op,
    }


# TODO(5b-2b): 도메인 표현 adapter — 커지면 expression_clamp.py/domain_expression.py로 분리.
# 파서 Domain enum 비종속(str 입력). education→study_document, 나머지는 동명 매핑.
_DOMAIN_KEY = {
    "career": "career", "wealth": "wealth", "relationship": "relationship",
    "relocation": "relocation", "education": "study_document",
}
# 등록 domain·class 누락 대비 변형 등급 → 6 정규 등급 매핑(§12-2: +주의/주의는 재사용).
_EXPRESSION_CLASS_CANON = {"조건부·유보+주의": "조건부·유보", "주의": "주의/흉"}


def domain_to_expression_key(domain: str | None) -> str | None:
    """파서 Domain.value(str) → 표현 key. GENERAL/미상/건강 등 미매핑은 None(base fallback)."""
    if not domain:
        return None
    return _DOMAIN_KEY.get(domain.lower())


def domain_expression_phrase(
    domain_key: str | None, expression_class: str, base_guidance: str
) -> str:
    """expression_class → 도메인 문구(5b-2b). 미상/미매핑 domain은 base_guidance(5b-2a) fallback.

    등록 domain인데 등급 문구가 없으면 KeyError(config 오류 — 완전성 테스트로 방지).
    """
    if not domain_key or domain_key not in DOMAIN_EXPRESSION_PHRASE:
        return base_guidance
    canon = _EXPRESSION_CLASS_CANON.get(expression_class, expression_class)
    return DOMAIN_EXPRESSION_PHRASE[domain_key][canon]
