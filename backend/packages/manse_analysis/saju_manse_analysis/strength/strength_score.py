"""신강/신약 9단계 점수 + 신왕/신강 분리 게이트 (strength_9_band spec).

통합형: 우리 분포/통근/구조 값을 그대로 합산한다.
  score = clamp(0.35·season + 0.35·root + 0.30·side + structure_modifier, 0, 100)
  - season: SEASON_SCORE[season_state(일간오행, 월지)]  (월령)
  - root  : rooting.root_score                          (통근)
  - side  : side_balance_score(ten_god_groups)          (일간 기준 생조/극설 비율)
  - structure_modifier: 합충형파해·공망 보정(±10)

오행구족(모든 오행 존재)은 '구성 상태'일 뿐 신강약(세력 상태)과 분리해 별도 라벨로 둔다.
오행 편중도(imbalance)는 중화 단정의 보조 지표로 쓴다.
"""

from __future__ import annotations

from saju_shared_types.constants import (
    SEASON_SCORE,
    STEM_ELEMENT,
    main_hidden_stem,
    season_state,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem, TenGod
from saju_shared_types.pillars import FourPillarsResult

from .._chart import view

# 9단계 밴드 경계(0~100, 상한 inclusive). 태신약/태신강 포함(geokguk _WEAK/_STRONG와 정합).
_BAND_BOUNDS = [
    (28, "극신약"), (34, "태신약"), (42, "신약"), (47, "중화신약"), (53, "중화"),
    (58, "중화신강"), (66, "신강"), (75, "태신강"), (100, "극신강"),
]
_BOUNDARY_POINTS = [28, 34, 42, 47, 53, 58, 66, 75]
_BAND_RANK = {name: i for i, (_u, name) in enumerate(_BAND_BOUNDS)}  # 극신약0 … 극신강8
_ALLY_GROUPS = {TenGod.BIGYEON, TenGod.GEOMJAE, TenGod.JEONGIN, TenGod.PYEONIN}
_NEUTRAL_BANDS = {"중화신약", "중화", "중화신강"}
_IMBALANCE_NEUTRAL_MAX = 3.0  # 중화권이어도 이 이상 편중이면 '중화이나 편중'


def classify_band(score: float) -> str:
    for upper, name in _BAND_BOUNDS:
        if score <= upper:
            return name
    return "극신강"


def is_borderline(score: float) -> bool:
    return any(abs(score - b) <= 2 for b in _BOUNDARY_POINTS)


def side_balance_score(groups: dict[str, float]) -> float:
    """일간 기준 생조(비겁·인성) vs 극설(식상·재성·관성) 비율 → 0~100(50=중화)."""
    ally = groups["peer"] * 1.00 + groups["resource"] * 0.85
    pressure = groups["output"] * 0.60 + groups["wealth"] * 0.75 + groups["officer"] * 0.90
    denom = ally + pressure
    if denom <= 1e-6:
        return 50.0
    return 100 * ally / denom


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _is_ally_branch(dm: Stem, branch: Branch) -> bool:
    return ten_god(dm, main_hidden_stem(branch)) in _ALLY_GROUPS


def _imbalance(season_adjusted: dict[str, float]) -> tuple[float, str]:
    """오행 편중도(최대/최소) + 상태 라벨."""
    vals = list(season_adjusted.values())
    if not vals:
        return 1.0, "균형"
    ratio = max(vals) / max(min(vals), 1.0)
    if ratio >= 5.0:
        status = "심한 편중"
    elif ratio >= 3.0:
        status = "편중"
    elif ratio >= 2.0:
        status = "약한 편중"
    else:
        status = "균형"
    return round(ratio, 2), status


def evaluate_strong_gate(
    month_ally: bool, day_ally: bool, ally_labels: set[str]
) -> dict[str, bool]:
    """신강 최소 조건 게이트.

    ① 월지 또는 일지가 비겁/인성, ② 그 자리 외의 다른 자리에도 비겁/인성이 하나 이상.
    월지·일지가 모두 동류면 한쪽이 ②의 "다른 자리" 역할을 한다.
    """
    month_or_day_ally = month_ally or day_ally
    if month_ally and day_ally:
        another = True
    elif month_or_day_ally:
        satisfier = "month_branch" if month_ally else "day_branch"
        another = bool(ally_labels - {satisfier})
    else:
        another = bool(ally_labels)
    return {
        "month_or_day_branch_ally": month_or_day_ally,
        "another_ally_position_exists": another,
        "passed": month_or_day_ally and another,
    }


def compute_strength(
    pillars: FourPillarsResult,
    ten_god_groups: dict[str, float],
    root_score: float,
    structure_modifier: float,
    relation_stability: float,
    raw_visible: dict[str, float],
    season_adjusted: dict[str, float],
) -> dict:
    """통합형 신강약 — 월령·통근·일간세력비율·구조보정 합산 + 오행구족/편중 보조 라벨."""
    cv = view(pillars)
    dm = cv.day_master
    dm_el = STEM_ELEMENT[dm]
    warnings: list[str] = []

    season = float(SEASON_SCORE[season_state(dm_el, cv.month_branch)])
    side = side_balance_score(ten_god_groups)
    structure_modifier = _clamp(structure_modifier, -10, 10)

    score = _clamp(0.35 * season + 0.35 * root_score + 0.30 * side + structure_modifier, 0, 100)
    band = classify_band(score)
    # 캡 룰: 월령·통근·세력이 모두 중화 미만이면 신약 이상으로 올리지 않는다(오행구족·일부
    # 통근이 우연히 점수를 끌어올려도 신약 캡). season≤38 + root≤45 + side≤48.
    strength_capped = (
        season <= 38 and root_score <= 45 and side <= 48
        and _BAND_RANK[band] > _BAND_RANK["신약"]
    )
    if strength_capped:
        band = "신약"
    borderline = is_borderline(score)

    # 오행구족(구성 상태) — 표면(천간+지지)에 5오행이 모두 존재하는가. 암장-only는 불포함.
    has_all_elements = all(v > 0 for v in raw_visible.values()) if raw_visible else False
    element_presence_label = "오행구족" if has_all_elements else "오행결핍"
    # 오행 편중도(보조 지표).
    imbalance_ratio, element_balance_status = _imbalance(season_adjusted)

    # 중화권이어도 편중이 심하면 단정 보류.
    band_note = ""
    if band == "중화" and imbalance_ratio >= _IMBALANCE_NEUTRAL_MAX:
        band_note = "중화이나 편중 — 조후·통관 필요성 병행"

    # confidence — 각 성분의 명료도 + 관계 안정도.
    season_clarity = _clamp(abs(season - 50) / 40, 0, 1)
    root_clarity = _clamp(abs(root_score - 50) / 50, 0, 1)
    side_clarity = _clamp(abs(side - 50) / 50, 0, 1)
    confidence = round(
        0.35 * season_clarity + 0.30 * root_clarity + 0.20 * side_clarity
        + 0.15 * relation_stability,
        4,
    )
    requires_validation = band in _NEUTRAL_BANDS or confidence < 0.70 or borderline

    # 신강 최소 조건 게이트(신왕 ≠ 신강).
    month_ally = _is_ally_branch(dm, cv.month_branch)
    day_ally = _is_ally_branch(dm, cv.branches[2][1])
    ally_labels: set[str] = set()
    for pos, stem in cv.stems:
        if pos == "day":
            continue
        if ten_god(dm, stem) in _ALLY_GROUPS:
            ally_labels.add(f"{pos}_stem")
    for pos, branch in cv.branches:
        if ten_god(dm, main_hidden_stem(branch)) in _ALLY_GROUPS:
            ally_labels.add(f"{pos}_branch")
    gate = evaluate_strong_gate(month_ally, day_ally, ally_labels)

    if band in _NEUTRAL_BANDS:
        warnings.append("neutral_zone: 용신 단정 금지, 경쟁 모델/검증 필요")
    if root_score >= 50 and not gate["passed"]:
        warnings.append("rooted_but_not_strong: 신왕하나 신강 게이트 미통과")
    if strength_capped:
        warnings.append("capped_to_weak: 월령·통근·세력 모두 중화 미만 → 신약 캡 적용")
    if band_note:
        warnings.append(band_note)

    rootedness_label = (
        "무근" if root_score < 10 else
        "약근" if root_score < 30 else
        "보통" if root_score < 50 else "신왕"
    )

    # 판정 사유(일간 기준 세력 관점).
    reason: list[str] = []
    if has_all_elements:
        reason.append("오행은 모두 존재(오행구족)하나 신강약은 일간 세력 균형으로 판정")
    if season < 40:
        reason.append("월령(계절)이 일간을 돕지 않음")
    elif season > 60:
        reason.append("월령(계절)이 일간을 강하게 도움")
    if side < 48:
        reason.append("일간을 돕는 비겁·인성보다 식상·재성·관성 세력이 강함")
    elif side > 52:
        reason.append("일간을 돕는 비겁·인성 세력이 식상·재성·관성보다 강함")
    if root_score < 30:
        reason.append("통근(뿌리)이 약함")
    elif root_score >= 50:
        reason.append("통근(뿌리)이 튼튼함")
    if imbalance_ratio >= _IMBALANCE_NEUTRAL_MAX:
        reason.append(f"오행 편중(최대/최소 {imbalance_ratio}배) — 조후·통관 병행 검토")

    return {
        "score": round(score, 2),
        "band": band,
        "borderline": borderline,
        "confidence": confidence,
        "requires_validation": requires_validation,
        "components": {
            "season_score": round(season, 2),
            "root_score": round(root_score, 2),
            "side_balance_score": round(side, 2),
            "structure_modifier": structure_modifier,
        },
        "basis": {},  # filled by aggregator from rooting
        "rootedness": {"label": rootedness_label, "score": round(root_score, 2)},
        "strong_chart_gate": gate,
        "has_all_elements": has_all_elements,
        "element_presence_label": element_presence_label,
        "imbalance_ratio": imbalance_ratio,
        "element_balance_status": element_balance_status,
        "band_note": band_note,
        "reason": reason,
        "explanation": [
            f"score={round(score, 2)} ({band}); season={round(season, 1)}, "
            f"root={round(root_score, 1)}, side={round(side, 1)}, structure={structure_modifier}",
        ],
        "warnings": warnings,
        "_side_balance_score": round(side, 2),
    }
