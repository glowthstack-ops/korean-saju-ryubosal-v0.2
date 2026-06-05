"""격국 분석: 월지 정기 주격, 투간, 성격/패격/중성, 보조 구조, 안정도.

격국은 참고/보조 레이어다(단독 용신 확정 금지).
"""

from __future__ import annotations

from saju_shared_types.constants import STEM_ELEMENT, main_hidden_stem, ten_god
from saju_shared_types.enums import Branch, Stem, TenGod
from saju_shared_types.pillars import FourPillarsResult
from saju_shared_types.structure import GeokgukResult, StructureAnalysis

# 월지 정기 십성 → 주격 명칭 (비견/겁재는 건록/양인 특수 월령 구조).
_SPECIAL = {TenGod.BIGYEON: "건록격", TenGod.GEOMJAE: "양인격"}


def detect_geokguk(
    pillars: FourPillarsResult,
    day_master: Stem,
    structure: StructureAnalysis,
    gongmang_branches: list[str],
) -> GeokgukResult:
    month = pillars.month
    month_branch = Branch(month.branch)
    main_stem = main_hidden_stem(month_branch)
    main_ten_god = TenGod(month.branch_main_ten_god)

    main_structure = _SPECIAL.get(main_ten_god, f"{main_ten_god.value}격")

    # 투간: 월지 정기가 천간에 드러났는가 / 같은 십성이 드러났는가.
    heavenly = [pillars.year.stem, pillars.month.stem, pillars.hour.stem if pillars.hour else None]
    heavenly_stems = [Stem(s) for s in heavenly if s is not None]
    main_qi_exposed = main_stem in heavenly_stems
    same_ten_god_exposed = any(
        ten_god(day_master, s) == main_ten_god for s in heavenly_stems
    )
    exposed_position = None
    for pos in ("year", "month", "hour"):
        p = getattr(pillars, pos)
        if p is not None and Stem(p.stem) == main_stem:
            exposed_position = pos
            break
    exposure_strength = (
        "strong" if main_qi_exposed else "medium" if same_ten_god_exposed else "weak"
    )

    # 월지 손상 여부 (충/형/자형/공망).
    month_damaged_rels = [
        i
        for i in structure.interactions
        if "month" in i.positions and i.relation_type in ("clash", "punishment", "self_punishment")
    ]
    month_void = month.branch in set(gongmang_branches)

    # 손상 사유는 실제 관계 유형으로 라벨링한다(충/형/자형 구분).
    _REASON_BY_REL = {
        "clash": "month_branch_clashed",
        "punishment": "month_branch_punished",
        "self_punishment": "month_branch_self_punished",
    }
    reasons: list[str] = []
    if main_qi_exposed:
        reasons.append("main_qi_exposed")
    if not month_damaged_rels:
        reasons.append("month_branch_supported")
    for i in month_damaged_rels:
        reasons.append(_REASON_BY_REL.get(i.relation_type, "month_branch_damaged"))
    if month_void:
        reasons.append("month_branch_void")

    if month_damaged_rels or month_void:
        formation_level = "패"
    elif main_qi_exposed or same_ten_god_exposed:
        formation_level = "성"
    else:
        formation_level = "중성"

    stability_score = round(structure.stability.geokguk_stability, 4)
    stability_label = (
        "안정" if stability_score >= 0.9 else "불안정" if stability_score < 0.75 else "보통"
    )

    # 보조 구조: 월지 외 천간 십성의 발현(보조격 표현 금지 → "발현").
    auxiliary: list[str] = []
    for pos, label in (("year", "년주"), ("month", "월간"), ("hour", "시주")):
        p = getattr(pillars, pos)
        if p is None:
            continue
        stem = Stem(p.stem)
        if stem == day_master and pos == "day":
            continue
        tg = ten_god(day_master, stem)
        if pos == "month" and stem == main_stem:
            continue  # 주격 본기와 동일하면 보조로 중복 표기하지 않음
        auxiliary.append(f"{label} {tg.value} 발현")

    return GeokgukResult(
        main_structure=main_structure,
        basis={
            "month_branch": str(month_branch),
            "main_hidden_stem": str(main_stem),
            "main_ten_god": main_ten_god.value,
            "main_element": str(STEM_ELEMENT[main_stem]),
        },
        exposure={
            "main_qi_exposed": main_qi_exposed,
            "same_ten_god_exposed": same_ten_god_exposed,
            "exposed_position": exposed_position,
            "exposure_strength": exposure_strength,
        },
        formation_level=formation_level,
        stability={"score": stability_score, "label": stability_label, "reasons": reasons},
        auxiliary_structures=auxiliary,
        warnings=["격국은 참고 레이어이며 단독 용신 확정 근거로 사용하지 않는다."],
        explanation=[
            f"월지 {month_branch} 정기 {main_stem}({main_ten_god.value}) 기준 {main_structure}, "
            f"투간={'있음' if main_qi_exposed else '없음'}, 성격={formation_level}",
        ],
    )
