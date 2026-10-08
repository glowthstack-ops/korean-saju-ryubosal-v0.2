"""격국 분석: 월지 지장간 다후보 산출 + 투간/통근 랭킹 + 성격/패격/신뢰도 + 특수격 신호.

격국은 참고/보조 레이어다(단독 용신 확정 금지).
월지 정기 1글자만 보지 않고, 월지 지장간(정기/중기/여기) 전체를 후보로 만들어
confidence(위계·투간·통근·상신·파격·청정)로 랭킹한 뒤 주격 1 + 보조격 N을 산출한다.
"""

from __future__ import annotations

from saju_shared_types.constants import STEM_ELEMENT, ten_god
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.pillars import FourPillarsResult
from saju_shared_types.structure import GeokgukResult, StructureAnalysis

from ..relations.hap_modes import detect_hwagi
from .geokguk_eval import (
    build_candidates,
    candidate_dict,
    evaluate_geokguk,
    score_all_candidates,
    special_signal,
)

_REASON_BY_REL = {
    "clash": "month_branch_clashed",
    "punishment": "month_branch_punished",
    "self_punishment": "month_branch_self_punished",
}
# 특수격 주격 치환 임계값(타입별, 보수적). 미만이면 정격 유지 + '병행 검토' 신호만.
#   dominant 0.60 ≈ 압도 오행 80%+, follow 0.70 ≈ root_score ≤ 3(거의 무근).
#   → 가전왕/가종격(경계)은 치환하지 않고 병행 표기해 오확정을 막는다.
_OVERRIDE_MIN = {"dominant": 0.60, "follow": 0.70, "transform": 0.60}


_GK_LABEL = {None: "신호 없음", False: "가능성(미확정)", True: "확정"}
_YS_LABEL = {None: "없음", "real": "진종(眞從)", "pseudo": "가종(假從)"}


def _follow_consistency(special: dict | None, force, structure: StructureAnalysis) -> dict | None:
    """종격 두 기준(격국 신호 vs 용신 특수격 검출)의 판정과 일치 여부 — 표기 전용(C1-c C안).

    격국은 root_score<8(override 는 root≤3)만 보고, 용신 검출기는 root 외에 비겁·인성 세력비로도
    종격을 잡는다(root_score 가 인성 통근을 포함해 교과서 종격도 root≥8 이 되는 경우 대비). 두
    기준의 임계는 그대로 두고, 어느 한쪽이라도 종격을 보면 결과를 나란히 적는다. 점수·역할·격국
    불변.
    """
    from ..yongsin.special_cases import detect_special_cases

    gk_type = str(special.get("type")) if special else None
    if gk_type == "transform":
        # 화기격(진화)이 주격을 치환하면 종격 두 기준 비교는 무의미 — 화기격 우선(codex 10.6).
        return {"status": "superseded_by_transform", "geokguk_signal": gk_type,
                "geokguk_override": bool(special.get("override")) if special else None,
                "geokguk_label": "화기격 우선", "yongsin_follow_kind": None,
                "yongsin_label": "-", "note": "화기격(진화) 성립 — 종격 판정은 적용하지 않는다."}
    gk_follow = special is not None and gk_type == "follow"
    gk_override: bool | None = (
        bool(special.get("override")) if special is not None and gk_follow else None
    )
    ys = detect_special_cases(force, structure).get("follow_structure")
    ys_kind = str(ys.detail).split(":")[0] if ys is not None and ys.detected else None
    if not gk_follow and ys_kind is None:
        return None
    consistent = gk_follow and gk_override is True and ys_kind == "real"
    gk_label = _GK_LABEL[gk_override] if gk_follow else _GK_LABEL[None]
    ys_label = _YS_LABEL.get(ys_kind, "없음")
    if consistent:
        note = "격국과 용신 기준이 모두 종격으로 확정 — 일치."
    elif gk_follow and gk_override is False and ys_kind:
        note = ("격국은 종격 가능성만 보고(무근 정도 부족) 용신 검출기는 종격으로 본다 — "
                "용신은 종격 모델을 쓰지만 조후 역행 시 강등될 수 있다.")
    elif not gk_follow and ys_kind:
        note = ("격국 기준으로는 종격 신호가 없고(인성 통근이 root_score 에 포함) 용신 검출기는 "
                "세력비로 종격을 본다 — 격국 표기는 정격, 용신은 종격 모델.")
    else:
        note = "격국은 종격 신호를 보지만 용신 검출기는 종격으로 보지 않는다."
    return {
        "status": "consistent" if consistent else "mismatch",
        "geokguk_signal": gk_type, "geokguk_override": gk_override,
        "geokguk_label": gk_label,
        "yongsin_follow_kind": ys_kind, "yongsin_label": ys_label,
        "note": note,
    }


def detect_geokguk(
    pillars: FourPillarsResult,
    day_master: Stem,
    structure: StructureAnalysis,
    gongmang_branches: list[str],
    force=None,  # ForceAnalysis — 격국 평가(신뢰도/성패/가중치)용
) -> GeokgukResult:
    """월지 지장간 전체를 격 후보로 산출·랭킹해 주격/보조격·성격·특수격 신호를 반환한다.

    정기 1글자 단일 확정이 아니라 (정기/중기/여기)×투간/통근/상신/청정을 confidence로
    랭킹해 주격을 고르고, 종격/전왕 강신호(≥임계)면 주격을 특수격으로 치환한다.
    격국은 보조 레이어이며 단독으로 용신을 확정하지 않는다.
    """
    month = pillars.month
    month_branch = Branch(month.branch)

    # 1) 월지 지장간 전체를 격 후보로 산출 → confidence 랭킹(투간/위계 반영).
    cands = build_candidates(pillars, day_master)
    scored = score_all_candidates(pillars, cands, force, structure, gongmang_branches)
    selected, sel_conf, _ = scored[0]
    candidates_out = [
        candidate_dict(c, conf, "주격" if i == 0 else "보조후보")
        for i, (c, conf, _f) in enumerate(scored)
    ]

    jeonggyeok_name = selected.name  # 정격(월지 지장간 기반) 주격
    main_structure = jeonggyeok_name
    main_ten_god = selected.ten_god
    main_stem = selected.stem

    # 2) 투간(선택 격신 기준).
    hour_stem = pillars.hour.stem if pillars.hour else None
    heavenly_stems = [
        Stem(s)
        for s in (pillars.year.stem, pillars.month.stem, hour_stem)
        if s is not None
    ]
    main_qi_exposed = selected.revealed
    same_ten_god_exposed = any(ten_god(day_master, s) == main_ten_god for s in heavenly_stems)
    exposure_strength = (
        "strong" if main_qi_exposed else "medium" if same_ten_god_exposed else "weak"
    )

    # 3) 월지 손상(충/형/자형/공망).
    month_damaged_rels = [
        i
        for i in structure.interactions
        if "month" in i.positions and i.relation_type in ("clash", "punishment", "self_punishment")
    ]
    month_void = month.branch in set(gongmang_branches)

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

    # 4) 보조 구조: 월지 외 천간 십성의 발현(보조격 표현 금지 → "발현").
    auxiliary: list[str] = []
    for pos, label in (("year", "연주"), ("month", "월간"), ("hour", "시주")):
        p = getattr(pillars, pos)
        if p is None:
            continue
        stem = Stem(p.stem)
        tg = ten_god(day_master, stem)
        if pos == "month" and stem == main_stem:
            continue  # 주격 격신과 동일하면 보조로 중복 표기하지 않음
        auxiliary.append(f"{label} {tg.value} 발현")

    # 5) 선택 격 기준 전체 평가 + 종격/전왕 신호(정격과 병행 검토).
    evaluation = (
        evaluate_geokguk(pillars, selected, force, structure, gongmang_branches)
        if force is not None
        else None
    )
    # 성격/패격은 평가의 성패와 일관되게 — 월지 손상 하나로 단정하지 않는다.
    if evaluation is not None:
        formation_level = {
            "complete_success": "성", "partial_success": "성",
            "mixed": "중성",
            "failure_with_rescue": "패", "clear_failure": "패", "severe_muddiness": "패",
        }.get(evaluation.success_failure_grade, formation_level)

    special = special_signal(force, pillars) if force is not None else None
    # 특수격 강신호(≥0.5)면 주격을 특수격으로 치환(정격은 candidates·special.jeonggyeok로 병기).
    if special is not None:
        gate = _OVERRIDE_MIN.get(str(special.get("type")), 0.60)
        special["override"] = special["confidence"] >= gate
        special["jeonggyeok"] = jeonggyeok_name
        if special["override"]:
            main_structure = special["name"]
            formation_level = "특수격"
    follow_consistency = (
        _follow_consistency(special, force, structure) if force is not None else None
    )
    # 화기격 가화(假化) 후보는 주격을 치환하지 않고 경고로만 남긴다(2026-10-08 데굴님 결정:
    # 가화 확정 라벨 변경 보류).
    hwagi_warnings: list[str] = []
    _hw = detect_hwagi(pillars)
    if _hw is not None and _hw.kind == "pseudo":
        hwagi_warnings.append(
            f"화기격 후보(가화): {''.join(_hw.pair)}합 化{_hw.target_element} — "
            + "; ".join(_hw.reasons[1:]) + " (주격 치환 없음)"
        )

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
            "exposed_position": selected.revealed_position,
            "exposure_strength": exposure_strength,
        },
        formation_level=formation_level,
        stability={"score": stability_score, "label": stability_label, "reasons": reasons},
        auxiliary_structures=auxiliary,
        candidates=candidates_out,
        special_pattern=special,
        follow_consistency=follow_consistency,
        evaluation=evaluation,
        warnings=(
            ["격국은 참고 레이어이며 단독 용신 확정 근거로 사용하지 않는다."]
            + (["특수격(종격/전왕/화기격) 신호가 있어 정격과 병행 검토한다."] if special else [])
            + hwagi_warnings
        ),
        explanation=[
            f"월지 {month_branch} {selected.hidden_type} {main_stem}({main_ten_god.value}) 정격 "
            f"{jeonggyeok_name}, 투간={'있음' if main_qi_exposed else '없음'}, "
            f"신뢰도={sel_conf}, 성격={formation_level}"
            + (
                f" · 특수격 {special['name']}"
                f"({'주격 치환' if special.get('override') else '병행 검토'})"
                if special else ""
            ),
        ],
    )
