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


def _e(el: Element) -> str:
    return str(el)


def _strongest_pressure(groups: dict[str, float]) -> str:
    pressure = {k: groups[k] for k in ("output", "wealth", "officer")}
    return max(pressure, key=lambda g: pressure[g])


def _support_model(g: dict[str, Element], strength) -> YongsinCandidateModel:
    """부일간형: 신약 일간을 비겁으로 직접 보강 (용=비겁, 희=인성, 기=관살, 구=재성, 한=식상)."""
    conf = round(min(0.5 + (50 - strength.score) / 100, 0.85), 4)
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
    conf = round(min(0.45 + (50 - strength.score) / 120, 0.78), 4)
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
    conf = round(min(0.5 + (strength.score - 50) / 100, 0.85), 4)
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
        strongest = max(force.five_elements.effective_percent,
                        key=lambda e: force.five_elements.effective_percent[e])
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
    if checks["bridge_required"].detected:
        warnings.append(f"통관 가능 구조: {checks['bridge_required'].detail}")
    if checks["isolation_health"].detected:
        warnings.append(f"고립/병약 리스크: {checks['isolation_health'].detail} (건강 레이어)")

    # 후보 통합: 용신/희신 → useful, 기신/구신 → unfavorable. 각 원소의 최고 점수를
    # 낸 모델(출처)과 역할을 함께 보관해 후보 provenance를 노출한다(검증 루프용).
    useful: dict[str, tuple[float, str, str]] = {}
    unfavorable: dict[str, tuple[float, str, str]] = {}

    def _put(table: dict[str, tuple[float, str, str]], el: str | None,
             score: float, model: str, role: str) -> None:
        if el and score > table.get(el, (0.0, "", ""))[0]:
            table[el] = (score, model, role)

    for m in models:
        _put(useful, m.yongsin, m.confidence, m.model_type, "yongsin")
        _put(useful, m.heesin, m.confidence * 0.85, m.model_type, "heesin")
        _put(unfavorable, m.gisin, m.confidence, m.model_type, "gisin")
        _put(unfavorable, m.gusin, m.confidence * 0.9, m.model_type, "gusin")

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
        final=final,
        requires_validation=True,
        warnings=warnings,
    )
