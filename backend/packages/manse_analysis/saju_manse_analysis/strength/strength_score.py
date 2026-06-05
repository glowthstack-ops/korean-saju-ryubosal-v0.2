"""신강/신약 9단계 점수 + 신왕/신강 분리 게이트 (strength_9_band spec)."""

from __future__ import annotations

from saju_shared_types.constants import (
    main_hidden_stem,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem, TenGod
from saju_shared_types.pillars import FourPillarsResult

from .._chart import view
from .strength_v1 import compute_v1, is_borderline_v1

_ALLY_GROUPS = {TenGod.BIGYEON, TenGod.GEOMJAE, TenGod.JEONGIN, TenGod.PYEONIN}
_NEUTRAL_BANDS = {"중화", "중화신약", "중화신강"}


def classify_band(score: float) -> str:
    from .strength_v1 import _label
    return _label(score)


def is_borderline(score: float) -> bool:
    return is_borderline_v1(score)


def side_balance_score(groups: dict[str, float]) -> float:
    ally = groups["peer"] * 1.00 + groups["resource"] * 0.85
    pressure = groups["output"] * 0.55 + groups["wealth"] * 0.75 + groups["officer"] * 1.00
    denom = ally + pressure
    if denom <= 1e-6:
        return 50.0
    return 100 * ally / denom


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _is_ally_branch(dm: Stem, branch: Branch) -> bool:
    return ten_god(dm, main_hidden_stem(branch)) in _ALLY_GROUPS


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
) -> dict:
    """신강·신약 v1.3 — 8성분 합산(strength_v1) + 가종격 분기 + 신강 게이트."""
    cv = view(pillars)
    dm = cv.day_master
    warnings: list[str] = []

    v1 = compute_v1(pillars)
    score = v1["score"]
    band = v1["label"]
    root_total = v1["root_total"]
    borderline = is_borderline(score)

    # confidence — |score| 가 클수록(밴드 중심에서 멀수록) 명료. 관계 안정도 가미.
    magnitude = _clamp(abs(score) / 80, 0, 1)
    confidence = round(_clamp(0.45 + 0.40 * magnitude + 0.15 * relation_stability, 0, 1), 4)
    requires_validation = band in _NEUTRAL_BANDS or borderline or confidence < 0.70

    # 신강 최소 조건 게이트 (신왕 ≠ 신강).
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
    if v1["jong"]["active"]:
        warnings.append(f"가종격(假從) 신호: {v1['jong']['evidence']} → 억부 우선 검토")
    if root_total >= 40 and not gate["passed"]:
        warnings.append("rooted_but_not_strong: 신왕하나 신강 게이트 미통과")

    rootedness_label = (
        "무근" if root_total < 10 else
        "약근" if root_total < 25 else
        "보통" if root_total < 45 else "신왕"
    )

    return {
        "score": score,
        "band": band,
        "borderline": borderline,
        "confidence": confidence,
        "requires_validation": requires_validation,
        "components": v1["components"],  # 8성분 (root_score 키 포함)
        "basis": {},  # filled by aggregator from rooting
        "rootedness": {"label": rootedness_label, "score": round(root_total, 2)},
        "strong_chart_gate": gate,
        "explanation": [
            f"v1.3 score={score} ({band}); "
            + "; ".join(f"{k}={v}" for k, v in v1["components"].items()),
            f"가종격={'O' if v1['jong']['active'] else 'X'} ({v1['jong']['evidence']})",
        ],
        "warnings": warnings,
        "_side_balance_score": 0.0,
    }
