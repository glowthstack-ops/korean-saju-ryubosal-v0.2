"""용신 후보 모델 산출 및 통합.

원칙: 부족 오행을 자동 용신 처리하지 않고, 신약/신강을 일률 처리하지 않으며,
특수격을 억부보다 먼저 검사한다. 최초 status 는 candidate (검증 전 calibrated 금지).
"""

from __future__ import annotations

from saju_shared_types.analysis import ForceAnalysis
from saju_shared_types.constants import (
    SEASON_ELEMENT_BY_MONTH,
    STEM_ELEMENT,
    group_elements,
)
from saju_shared_types.enums import Branch, Element, Stem
from saju_shared_types.pillars import FourPillarsResult
from saju_shared_types.structure import GeokgukResult, StructureAnalysis
from saju_shared_types.yongsin import (
    AggregatedYongsinResult,
    ElementCandidate,
    YongsinCandidateModel,
)

from .special_cases import detect_special_cases

_WEAK = {"극신약", "태신약", "신약", "중화신약"}
_NEUTRAL = {"중화", "중화신강"}
_STRONG = {"신강", "태신강", "극신강"}
_COLD_MONTHS = {Branch.HAE, Branch.JA, Branch.CHUK}
_HOT_MONTHS = {Branch.SA, Branch.O, Branch.MI}

# 모델 → 용신 판단 축. (격국/병약/조후는 보정 레이어, 특수격은 우선)
_AXIS_OF: dict[str, str] = {
    "support_day_master": "eokbu", "resource_as_yongsin": "eokbu",
    "output_as_yongsin": "eokbu", "eokbu_normal": "eokbu",
    "johu": "johu", "pattern_sangsin": "pattern", "disease_remedy": "disease",
    "dominant_one_element": "special", "follow_structure": "special",
}
# 파격(damage) → 약신(repair) 그룹.
_DAMAGE_REPAIR: dict[str, str] = {
    "shangguan_attacks_officer": "resource",   # 인성으로 상관 제어
    "mixed_officer_killing": "output",          # 식신제살
    "killing_overwhelms_weak": "resource",      # 살인상생
    "wealth_overwhelms_weak": "peer",           # 비겁 부조
    "pyeonin_dosik": "wealth",                  # 재성으로 편인 제어
    "bigyeob_jaengjae": "officer",              # 관성으로 비겁 제어
}


def _e(el: Element) -> str:
    return str(el)


def _strongest_pressure(groups: dict[str, float]) -> str:
    pressure = {k: groups[k] for k in ("output", "wealth", "officer")}
    return max(pressure, key=lambda g: pressure[g])


def _support_model(g: dict[str, Element], strength) -> YongsinCandidateModel:
    """부일간형: 신약 일간을 비겁으로 직접 보강 (용=비겁, 희=인성, 기=관살, 구=재성, 한=식상)."""
    conf = round(min(0.5 + (-strength.score) / 120, 0.85), 4)
    return YongsinCandidateModel(
        model_type="support_day_master",
        label="부일간형(비겁 보강)",
        yongsin=_e(g["peer"]), heesin=_e(g["resource"]),
        gisin=_e(g["officer"]), gusin=_e(g["wealth"]), hansin=_e(g["output"]),
        confidence=conf,
        reasons=["신약 일간을 비겁으로 직접 보강", "관살이 일간을 압박하므로 기신"],
    )


def _resource_model(g: dict[str, Element], strength) -> YongsinCandidateModel:
    """인성용신형: 재성·식상으로 빠지는 기운을 인성으로 회복 (관인상생, 희=관살)."""
    conf = round(min(0.45 + (-strength.score) / 150, 0.78), 4)
    return YongsinCandidateModel(
        model_type="resource_as_yongsin",
        label="인성용신형(관인상생)",
        yongsin=_e(g["resource"]), heesin=_e(g["officer"]),
        gisin=_e(g["wealth"]), gusin=_e(g["output"]), hansin=_e(g["peer"]),
        confidence=conf,
        reasons=["재성/식상 누출을 인성으로 회복", "관성이 인성을 생조(관인상생)"],
    )


def _output_model(g: dict[str, Element], strength) -> YongsinCandidateModel:
    """식상용신형: 신왕하나 관살이 강할 때 식상으로 관살을 제어."""
    return YongsinCandidateModel(
        model_type="output_as_yongsin",
        label="식상용신형(제살)",
        yongsin=_e(g["output"]), heesin=_e(g["peer"]),
        gisin=_e(g["officer"]), gusin=_e(g["wealth"]), hansin=_e(g["resource"]),
        confidence=0.55,
        reasons=["신왕 + 관살 강 → 식상으로 제어"],
    )


def _eokbu_strong_model(g: dict[str, Element], strength) -> YongsinCandidateModel:
    """일반 억부(신강): 식상 설기 + 재성, 기신=인성/비겁."""
    conf = round(min(0.5 + strength.score / 120, 0.85), 4)
    return YongsinCandidateModel(
        model_type="eokbu_normal",
        label="억부형(설기·재관)",
        yongsin=_e(g["output"]), heesin=_e(g["wealth"]),
        gisin=_e(g["resource"]), gusin=_e(g["peer"]), hansin=_e(g["officer"]),
        confidence=conf,
        reasons=["신강 일간을 식상으로 설기", "인성/비겁 과다는 기신"],
    )


def _johu_model(month_branch: Branch, g: dict[str, Element]) -> YongsinCandidateModel | None:
    """조후 보조형: 한난 불균형 시 화/수 후보 (단독 확정 금지)."""
    if month_branch in _COLD_MONTHS:
        yong = Element.FIRE
        reason = "겨울/한습 월령 → 화로 조후"
    elif month_branch in _HOT_MONTHS:
        yong = Element.WATER
        reason = "여름/조열 월령 → 수로 조후"
    else:
        return None
    return YongsinCandidateModel(
        model_type="johu",
        label="조후 보조형",
        yongsin=_e(yong),
        confidence=0.4,
        reasons=[reason, "조후는 단독 확정 금지, 억부와 함께 검증"],
        is_auxiliary=True,
    )


def _pattern_model(geokguk: GeokgukResult, g: dict[str, Element]) -> YongsinCandidateModel | None:
    """격국용신형: 성격(成格) 시 상신 그룹을 용신 후보로(보정 레이어). 패격이면 병약이 담당."""
    ev = geokguk.evaluation
    if ev is None or ev.pattern_confidence < 0.4 or geokguk.formation_level == "패":
        return None
    sangsin = _GEOK_SANGSIN_GROUPS.get(geokguk.main_structure or "", [])
    if not sangsin:
        return None
    return YongsinCandidateModel(
        model_type="pattern_sangsin", label="격국용신형(상신)",
        yongsin=_e(g[sangsin[0]]),
        heesin=_e(g[sangsin[1]]) if len(sangsin) > 1 else None,
        confidence=round(ev.pattern_confidence, 4),
        reasons=[
            f"{geokguk.main_structure} 성격 → 상신 격국용신 후보",
            "단독 확정 금지(보정 레이어)",
        ],
        is_auxiliary=True,
    )


def _disease_models(
    geokguk: GeokgukResult, g: dict[str, Element]
) -> list[YongsinCandidateModel]:
    """병약용신형: 격국 파격 원인(damage_types)을 제거하는 약신 후보."""
    ev = geokguk.evaluation
    if ev is None:
        return []
    out: list[YongsinCandidateModel] = []
    seen: set[str] = set()
    for dmg in ev.damage_types:
        grp = _DAMAGE_REPAIR.get(dmg)
        if grp is None or grp in seen:
            continue
        seen.add(grp)
        out.append(YongsinCandidateModel(
            model_type="disease_remedy", label="병약용신형(약신)",
            yongsin=_e(g[grp]),
            confidence=0.5,
            reasons=[f"파격({dmg}) 제거 약신", "병약은 패격 보정 후보"],
            is_auxiliary=True,
        ))
    return out


_GEOK_SANGSIN_GROUPS: dict[str, list[str]] = {
    "정관격": ["wealth", "resource"], "편관격": ["output", "resource"],
    "정재격": ["output", "peer"], "편재격": ["output", "peer"],
    "식신격": ["wealth"], "상관격": ["resource", "wealth"],
    "정인격": ["officer"], "편인격": ["wealth", "output"],
    "건록격": ["wealth", "officer"], "양인격": ["officer", "output"],
}


def _select_axis_weights(
    band: str, month_branch: Branch, geokguk: GeokgukResult, special: bool
) -> dict[str, float]:
    """상황별 동적 축 가중치(사용자 §10). 신약은 억부 우선 → 용신 안정."""
    if special:
        return {"special": 1.0, "eokbu": 0.1, "johu": 0.1, "pattern": 0.1, "disease": 0.1}
    ev = geokguk.evaluation
    active = ev.total_active if ev else 0
    fw = ev.final_weight if ev else 0.15
    cold_hot = (
        month_branch in (_COLD_MONTHS | _HOT_MONTHS)
        and SEASON_ELEMENT_BY_MONTH[month_branch] != Element.EARTH
    )
    if band in _WEAK:  # 신약/중화신약 → 억부 우선(종격은 special에서 처리)
        return {"eokbu": 0.45, "johu": 0.25, "pattern": 0.15, "disease": 0.15, "special": 0.1}
    if active >= 2:  # 파격 뚜렷 → 병약 우선
        return {"disease": 0.35, "eokbu": 0.25, "johu": 0.20, "pattern": 0.20, "special": 0.1}
    if cold_hot:  # 중화/신강 + 한습·조열 → 조후 우선
        return {"johu": 0.40, "eokbu": 0.25, "pattern": 0.20, "disease": 0.15, "special": 0.1}
    if fw >= 0.30:  # 격국 선명 → 격국 우선
        return {"pattern": 0.40, "eokbu": 0.25, "johu": 0.20, "disease": 0.15, "special": 0.1}
    return {"eokbu": 0.35, "johu": 0.20, "pattern": 0.25, "disease": 0.20, "special": 0.1}


def build_yongsin(
    pillars: FourPillarsResult,
    force: ForceAnalysis,
    structure: StructureAnalysis,
    geokguk: GeokgukResult,
) -> AggregatedYongsinResult:
    dm = Stem(pillars.day.stem)
    dm_el = STEM_ELEMENT[dm]
    g = group_elements(dm_el)
    groups = force.ten_gods.groups
    strength = force.strength
    band = strength.band
    month_branch = Branch(pillars.month.branch)

    checks = detect_special_cases(force, structure)
    models: list[YongsinCandidateModel] = []
    warnings: list[str] = []

    # 특수격 우선
    if checks["dominant_one_element"].detected:
        # 오행 과다/부족은 월령 보정 세력 기준(없으면 effective 폴백).
        fe = force.five_elements
        sas = fe.season_adjusted_element_strength or fe.effective_percent
        strongest = max(sas, key=lambda e: sas[e])
        models.append(YongsinCandidateModel(
            model_type="dominant_one_element", label="전왕/일행득기형",
            yongsin=strongest, heesin=_e(g["output"]),
            confidence=round(checks["dominant_one_element"].confidence, 4),
            reasons=["특정 오행이 압도적 → 왕한 흐름을 순행", "정면으로 극하는 오행은 기신"],
        ))
    elif checks["follow_structure"].detected:
        strongest_pressure = _strongest_pressure(groups)
        follow_el = g[strongest_pressure]
        models.append(YongsinCandidateModel(
            model_type="follow_structure", label="종격형",
            yongsin=_e(follow_el), gisin=_e(g["peer"]),
            confidence=round(checks["follow_structure"].confidence, 4),
            reasons=["극신약 + 무근 → 따르는 세력이 용신", "억지로 돕는 비겁/인성은 기신"],
        ))
    elif band in _WEAK:
        models.append(_support_model(g, strength))
        sp = _strongest_pressure(groups)
        rooted_strong = strength.rootedness.get("label") == "신왕"
        has_root = bool(force.rooting.tonggeun)
        if rooted_strong and sp == "officer":
            models.append(_output_model(g, strength))
        elif has_root and sp in ("wealth", "output"):
            models.append(_resource_model(g, strength))
    elif band in _STRONG:
        models.append(_eokbu_strong_model(g, strength))
    else:  # 중화권 — 경쟁 모델 강제 + 검증
        models.append(_support_model(g, strength))
        models.append(_eokbu_strong_model(g, strength))
        warnings.append("neutral_zone: 경쟁 모델 동시 제시, 사용자 검증 필요")

    johu = _johu_model(month_branch, g)
    if johu is not None and SEASON_ELEMENT_BY_MONTH[month_branch] != Element.EARTH:
        models.append(johu)
    # 격국(상신)·병약(약신) 보정 축 — 용신을 단독 확정하지 않고 후보 우선순위만 조정.
    pattern = _pattern_model(geokguk, g)
    if pattern is not None:
        models.append(pattern)
    models.extend(_disease_models(geokguk, g))
    if checks["bridge_required"].detected:
        warnings.append(f"통관 가능 구조: {checks['bridge_required'].detail}")
    if checks["isolation_health"].detected:
        warnings.append(f"고립/병약 리스크: {checks['isolation_health'].detail} (건강 레이어)")

    # 동적 축 가중치(상황별) — 격국/조후/병약을 '보정 레이어'로 반영, 신약은 억부 우선.
    special = checks["dominant_one_element"].detected or checks["follow_structure"].detected
    axis_weights = _select_axis_weights(band, month_branch, geokguk, special)

    def _w(model_type: str) -> float:
        return axis_weights.get(_AXIS_OF.get(model_type, "eokbu"), 0.2)

    # 후보 통합: 용신/희신 → useful, 기신/구신 → unfavorable. 점수 = 모델 신뢰도 × 축 가중치.
    useful: dict[str, tuple[float, str, str]] = {}
    unfavorable: dict[str, tuple[float, str, str]] = {}

    def _put(table: dict[str, tuple[float, str, str]], el: str | None,
             score: float, model: str, role: str) -> None:
        if el and score > table.get(el, (0.0, "", ""))[0]:
            table[el] = (score, model, role)

    for m in models:
        w = _w(m.model_type)
        _put(useful, m.yongsin, m.confidence * w, m.model_type, "yongsin")
        _put(useful, m.heesin, m.confidence * w * 0.85, m.model_type, "heesin")
        _put(unfavorable, m.gisin, m.confidence * w, m.model_type, "gisin")
        _put(unfavorable, m.gusin, m.confidence * w * 0.9, m.model_type, "gusin")

    # 축별 기여 요약(어느 축이 어떤 오행을 얼마로 밀었는가).
    axes_summary: list[dict] = []
    for axis in ("special", "eokbu", "johu", "pattern", "disease"):
        contrib = [
            (m.yongsin, m.confidence * axis_weights.get(axis, 0.0))
            for m in models if _AXIS_OF.get(m.model_type) == axis and m.yongsin
        ]
        if contrib:
            top_el, top_sc = max(contrib, key=lambda x: x[1])
            axes_summary.append({
                "axis": axis, "weight": round(axis_weights.get(axis, 0.0), 3),
                "top_element": top_el, "score": round(top_sc, 4),
            })
    axes_summary.sort(key=lambda a: a["score"], reverse=True)  # 기여 점수 내림차순

    useful_sorted = sorted(useful.items(), key=lambda kv: kv[1][0], reverse=True)[:2]
    unfav_sorted = sorted(unfavorable.items(), key=lambda kv: kv[1][0], reverse=True)[:2]
    useful_candidates = [
        ElementCandidate(element=e, score=round(s, 4), model=mdl, reason=role)
        for e, (s, mdl, role) in useful_sorted
    ]
    unfavorable_candidates = [
        ElementCandidate(element=e, score=round(s, 4), model=mdl, reason=role)
        for e, (s, mdl, role) in unfav_sorted
    ]

    # 확정 정책: 검증 전에는 candidate. 단일 모델·고신뢰·특수격 없음·경쟁 미존재면 probable.
    any_special = any(c.detected for c in checks.values())
    competing = len(useful_candidates) >= 2 and (
        useful_candidates[0].score - useful_candidates[1].score < 0.12
    )
    if len(models) == 1 and strength.confidence >= 0.7 and not any_special and not competing:
        status = "probable"
    else:
        status = "candidate"

    final = {
        "yongsin": useful_candidates[0].element if useful_candidates else None,
        "heesin": useful_candidates[1].element if len(useful_candidates) > 1 else None,
        "gisin": unfavorable_candidates[0].element if unfavorable_candidates else None,
        "gusin": unfavorable_candidates[1].element if len(unfavorable_candidates) > 1 else None,
        "confidence": models[0].confidence if models else 0.0,
        "selected_model": models[0].model_type if models else None,
    }

    return AggregatedYongsinResult(
        status=status,
        special_case_checks=checks,
        candidate_models=models,
        useful_candidates=useful_candidates,
        unfavorable_candidates=unfavorable_candidates,
        axis_weights=axis_weights,
        axes=axes_summary,
        final=final,
        requires_validation=True,
        warnings=warnings,
    )
