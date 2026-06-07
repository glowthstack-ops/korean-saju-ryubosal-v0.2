"""격국 평가 — 신뢰도/성패/파격구제/명확도/최종가중치 (v1 geokguk_master_v2 v2 이식).

용신 후보 우선순위 '보정 레이어'이며 단독 확정자가 아니다. 격국 신뢰도는 '성공 크기'가 아니라
'삶의 무대(직업성·역할)의 선명도'를 뜻한다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from saju_shared_types.constants import STEM_ELEMENT, ten_god
from saju_shared_types.enums import Branch, Stem, TenGod
from saju_shared_types.pillars import FourPillarsResult
from saju_shared_types.structure import GeokgukEvaluation, StructureAnalysis

# 십성 → 그룹(family) key.
_GROUP_OF: dict[str, str] = {
    TenGod.BIGYEON.value: "peer", TenGod.GEOMJAE.value: "peer",
    TenGod.JEONGIN.value: "resource", TenGod.PYEONIN.value: "resource",
    TenGod.SIKSIN.value: "output", TenGod.SANGGWAN.value: "output",
    TenGod.JEONGJAE.value: "wealth", TenGod.PYEONJAE.value: "wealth",
    TenGod.JEONGGWAN.value: "officer", TenGod.PYEONGWAN.value: "officer",
}
# 격국명 → 격신 그룹.
_GEOK_GROUP: dict[str, str] = {
    "정관격": "officer", "편관격": "officer",
    "정재격": "wealth", "편재격": "wealth",
    "식신격": "output", "상관격": "output",
    "정인격": "resource", "편인격": "resource",
    "건록격": "peer", "양인격": "peer", "월겁격": "peer",
}
# 격국명 → 상신 그룹(들). (v1 §6 success_condition)
_GEOK_SANGSIN: dict[str, list[str]] = {
    "정관격": ["wealth", "resource"],
    "편관격": ["output", "resource"],
    "정재격": ["output", "peer"],
    "편재격": ["output", "peer", "officer"],
    "식신격": ["wealth"],
    "상관격": ["resource", "wealth"],
    "정인격": ["officer"],
    "편인격": ["wealth", "output"],
    "건록격": ["wealth", "officer"],
    "양인격": ["officer", "output"],
    "월겁격": ["officer", "output"],
}

_WEAK = {"극신약", "태신약", "신약", "중화신약"}
_STRONG = {"중화신강", "신강", "태신강", "극신강"}
_GROUP_KO = {"peer": "비겁", "resource": "인성", "output": "식상",
             "wealth": "재성", "officer": "관성"}

# ── 격 후보(월지 지장간 정기/중기/여기) ──────────────────────────────────────
_STAGE_BASE = {"main": 30, "middle": 20, "residual": 15}  # 위계별 격 성립 기본점
_STAGE_RANK = {"main": 3, "middle": 2, "residual": 1}
_STAGE_KO = {"main": "정기", "middle": "중기", "residual": "여기"}
# 양인(羊刃) 지지 — 양간만 성립. 일간 → 월지가 이 지지일 때만 양인격(음간엔 양인 없음).
_YANGIN = {
    Stem.GAP: Branch.MYO, Stem.BYEONG: Branch.O, Stem.MU: Branch.O,
    Stem.GYEONG: Branch.YU, Stem.IM: Branch.JA,
}


def pattern_name(
    tg: TenGod, day_master: Stem | None = None, month_branch: Branch | None = None,
) -> str:
    """십성 → 격국명. 비견=건록격, 겁재=양인격(양간+양인지지)/월겁격(그 외)."""
    if tg == TenGod.BIGYEON:
        return "건록격"
    if tg == TenGod.GEOMJAE:
        if day_master is not None and _YANGIN.get(day_master) == month_branch:
            return "양인격"
        return "월겁격"
    return f"{tg.value}격"


@dataclass
class GeokCandidate:
    name: str
    stem: Stem
    ten_god: TenGod
    hidden_type: str  # main/middle/residual
    ratio: float
    revealed_position: str | None  # 천간 투간 위치(month 우선) / None

    @property
    def revealed(self) -> bool:
        return self.revealed_position is not None


def build_candidates(pillars: FourPillarsResult, day_master: Stem) -> list[GeokCandidate]:
    """월지 지장간 전체(정기/중기/여기)를 격 후보로 산출. 투간 위치 포함."""
    month_branch = Branch(pillars.month.branch)
    chart_stems = {
        pos: Stem(getattr(pillars, pos).stem)
        for pos in ("year", "month", "hour")
        if getattr(pillars, pos) is not None
    }
    cands: list[GeokCandidate] = []
    for h in pillars.month.hidden_stems:
        stem = Stem(h.stem)
        tg = ten_god(day_master, stem)
        name = pattern_name(tg, day_master, month_branch)
        rev_pos = None
        for pos in ("month", "year", "hour"):  # 월간 투간 우선
            if chart_stems.get(pos) == stem:
                rev_pos = pos
                break
        cands.append(GeokCandidate(name, stem, tg, h.type, float(h.weight), rev_pos))
    return cands


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _tg_counts(pillars: FourPillarsResult) -> Counter[str]:
    """개별 십성 카운트 — 천간(일간 제외) + 지지 본기."""
    c: Counter[str] = Counter()
    for pos in ("year", "month", "hour"):
        p = getattr(pillars, pos)
        if p is not None:
            c[p.stem_ten_god] += 1
    for pos in ("year", "month", "day", "hour"):
        p = getattr(pillars, pos)
        if p is not None:
            c[p.branch_main_ten_god] += 1
    return c


def _group_counts(counts: Counter[str]) -> dict[str, int]:
    g = {k: 0 for k in ("peer", "resource", "output", "wealth", "officer")}
    for tg, n in counts.items():
        grp = _GROUP_OF.get(tg)
        if grp:
            g[grp] += n
    return g


def _geoksin_rooted(pillars: FourPillarsResult, geoksin: Stem) -> bool:
    """격신(월지 정기) 오행이 지지 지장간에 ≥2회 통근."""
    el = STEM_ELEMENT[geoksin]
    cnt = 0
    for pos in ("year", "month", "day", "hour"):
        p = getattr(pillars, pos)
        if p is None:
            continue
        if any(STEM_ELEMENT[Stem(h.stem)] == el for h in p.hidden_stems):
            cnt += 1
    return cnt >= 2


def _month_clashed(structure: StructureAnalysis) -> bool:
    return any(
        "month" in i.positions and i.relation_type in ("clash", "punishment", "self_punishment")
        for i in structure.interactions
    )


def _geoksin_combined_away(structure: StructureAnalysis) -> bool:
    """월지가 합으로 변질(합거 근사) — 월지 멤버가 confirmed 변환에 포함."""
    for t in structure.transformed_candidates:
        if t.confirmed and any("month" in str(m) for m in t.members):
            return True
    return any(
        "month" in i.positions and i.relation_type in ("six_combination", "삼합", "combine")
        for i in structure.interactions
    )


# ── confidence (0~100, A~E) — 후보별 7요소(위계/투간/통근/상신/파격/청정) ──

def score_candidate(
    pillars: FourPillarsResult, cand: GeokCandidate,
    groups: dict[str, int], has_failures: bool, clean: bool,
) -> tuple[int, list[dict]]:
    """격 후보 신뢰도(0~100). 위계 base + 이 후보의 투간 + 통근 + 상신 + 무파격 + 청정."""
    factors: list[dict] = []
    score = 0

    def add(label: str, got: int, mx: int, note: str) -> None:
        nonlocal score
        score += got
        factors.append({"factor": label, "score": got, "max": mx, "note": note})

    add("월지 위계 격 성립", _STAGE_BASE.get(cand.hidden_type, 0), 30,
        _STAGE_KO.get(cand.hidden_type, "?"))
    rev = 25 if cand.revealed_position == "month" else 15 if cand.revealed else 0
    add("격신 투간", rev, 25, cand.revealed_position or "없음")
    add("격신 통근", 15 if _geoksin_rooted(pillars, cand.stem) else 0, 15, str(cand.stem))
    sangsin = _GEOK_SANGSIN.get(cand.name, [])
    add("상신 존재", 15 if any(groups.get(g, 0) >= 1 for g in sangsin) else 0, 15,
        "·".join(_GROUP_KO[g] for g in sangsin) or "매핑없음")
    add("명확한 파격 없음", 0 if has_failures else 10, 10, "파격" if has_failures else "없음")
    add("청정 구조", 5 if clean else 0, 5, "청" if clean else "혼잡")
    return score, factors


def _confidence_grade(c: int) -> str:
    return "A" if c >= 80 else "B" if c >= 60 else "C" if c >= 40 else "D" if c >= 20 else "E"


# ── 파격 / 구제 ───────────────────────────────────────────────────────────

def _detect_failures(
    counts: Counter[str], groups: dict[str, int], band: str,
    month_clashed: bool, month_void: bool, pattern_name: str | None = None,
    structure: StructureAnalysis | None = None, day_master: Stem | None = None,
) -> list[dict]:
    total = sum(groups.values()) or 1
    weak = band in _WEAK
    out: list[dict] = []

    def add(dtype: str, active: bool, evidence: str, rescued: bool, rescue_ev: str) -> None:
        out.append({"type": dtype, "active": active, "evidence": evidence,
                    "rescued": rescued, "rescue_evidence": rescue_ev})

    g = groups
    sg = counts  # 개별

    # 상관견관
    if sg.get("상관", 0) >= 1 and sg.get("정관", 0) >= 1:
        resc = g["resource"] >= 1 or g["wealth"] >= 1
        add("shangguan_attacks_officer", True, "상관+정관",
            resc, "인성/재성 통관" if resc else "통관 없음")
    # 관살혼잡
    if sg.get("편관", 0) >= 1 and sg.get("정관", 0) >= 1:
        resc = sg.get("식신", 0) >= 1 or g["resource"] >= 1
        add("mixed_officer_killing", True, "정관+편관",
            resc, "식신제살/인성화살" if resc else "제·화 없음")
    # 살중신약
    if g["officer"] >= 2 and weak:
        resc = sg.get("식신", 0) >= 1 or g["resource"] >= 1 or g["peer"] >= 2
        add("killing_overwhelms_weak", True, f"관성{g['officer']}+{band}",
            resc, "식신/인성/비겁 보강" if resc else "제·화·부조 없음")
    # 재다신약
    if g["wealth"] / total >= 0.30 and weak:
        resc = g["peer"] >= 2 or g["resource"] >= 1
        add("wealth_overwhelms_weak", True, f"재성{int(g['wealth'] / total * 100)}%+{band}",
            resc, "비겁/인성 보강" if resc else "부조 없음")
    # 편인도식
    if sg.get("편인", 0) >= 1 and sg.get("식신", 0) >= 1:
        resc = g["wealth"] >= 1
        add("pyeonin_dosik", True, "편인+식신",
            resc, "재성 제인" if resc else "재성 없음")
    # 비겁쟁재
    if g["peer"] / total >= 0.35 and g["wealth"] / total >= 0.10:
        resc = g["officer"] >= 1 or g["output"] >= 1
        add("bigyeob_jaengjae", True,
            f"비겁{int(g['peer'] / total * 100)}%+재성{int(g['wealth'] / total * 100)}%",
            resc, "관성 제겁/식상 화겁" if resc else "관·식 없음")
    # 월지 충
    if month_clashed:
        add("chung_month_branch", True, "월지 충/형", False, "운 충·합 자극 시 가변")
    # 월지 공망
    if month_void:
        add("void_month_branch", True, "월지 공망", False, "운 충·합 자극 시 활성")

    # ── 격별 맞춤 위험 (선택 격이 주어질 때만) ──
    # 칠살격 무제: 편관격인데 제살(식신)·화살(인성)·합살(양인) 모두 없음.
    if pattern_name == "편관격" and sg.get("식신", 0) == 0 and g["resource"] == 0 and g["peer"] < 2:
        add("killing_uncontrolled", True, "편관격 제·화·합살 부재",
            False, "식신제살/인성화살/양인합살 필요")
    # 인성과다: 인격인데 인성이 과다(≥40%)로 식상이 막힘.
    if pattern_name in ("정인격", "편인격") and g["resource"] / total >= 0.40:
        resc = g["wealth"] >= 1
        add("resource_overload", True, f"인성{int(g['resource'] / total * 100)}%",
            resc, "재성 제인(설인)" if resc else "재성 없음")
    # 상관 무로: 상관격인데 패인(인성)·생재(재성)가 모두 없어 상관이 방치됨.
    if pattern_name == "상관격" and g["resource"] == 0 and g["wealth"] == 0:
        add("shanggwan_unguided", True, "상관격 패인·생재 부재",
            False, "인성 패인/재성 생재 필요")
    # 정관 합거: 정관격인데 정관(격신)이 천간합으로 묶임 → 격신 변질.
    if pattern_name == "정관격" and structure is not None and day_master is not None:
        officer_combined = any(
            ten_god(day_master, Stem(m)) == TenGod.JEONGGWAN
            for i in structure.interactions if i.relation_type == "stem_combination"
            for m in i.members
        )
        if officer_combined:
            resc = sg.get("정관", 0) >= 2  # 쟁합(정관 2개+)이면 합거 완화
            add("officer_combined_away", True, "정관 천간합 합거",
                resc, "쟁합 완화" if resc else "합거 손상")

    return out


# ── 성패 score (-100~100) — geokguk_master_v2 success_failure_factors 6요소 ──

# 일간 감당력(factor 2) band별 raw.
_DM_CAPABILITY = {
    "극신약": -70, "태신약": -45, "신약": -40, "중화신약": -10,
    "중화": 20, "중화신강": 40, "신강": 50, "태신강": 30, "극신강": 10,
}


def _success_failure(
    pillars: FourPillarsResult, cand: GeokCandidate, band: str,
    sangsin_groups: list[str], groups: dict[str, int],
    failures: list[dict], structure: StructureAnalysis, clean: bool,
) -> tuple[float, str, str]:
    # 1) 격신 성형 (0.20)
    f1 = 20.0  # 월령(격이 월지 기반)
    if _geoksin_rooted(pillars, cand.stem):
        f1 += 40
    if cand.revealed:  # 선택 격신의 투간
        f1 += 30
    if _month_clashed(structure):
        f1 -= 50
    if _geoksin_combined_away(structure):
        f1 -= 30
    # 격별 가중: 식신격 도식(편인이 격신 식신을 직접 극)은 격을 직접 깬다 → 추가 감점.
    if cand.name == "식신격" and any(
        f["type"] == "pyeonin_dosik" and f["active"] and not f["rescued"] for f in failures
    ):
        f1 -= 25
    f1 = _clamp(f1, -100, 100)
    # 2) 일간 감당력 (0.20)
    f2 = _DM_CAPABILITY.get(band, 0)
    # 3) 상신 존재 (0.20)
    f3 = 40 if any(groups.get(g, 0) >= 1 for g in sangsin_groups) else -30
    # 4) 파격 없음 (0.20, 역)
    active = [f for f in failures if f["active"]]
    f4 = 50 if not active else -25 * min(len(active), 3)
    # 5) 구제 존재 (0.15)
    f5 = 0.0
    if active:
        rescued = sum(1 for f in active if f["rescued"])
        f5 = rescued / len(active) * 60 - 30
    # 6) 청탁 (0.05)
    f6 = 50 if clean else -20

    score = _clamp(
        f1 * 0.20 + f2 * 0.20 + f3 * 0.20 + f4 * 0.20 + f5 * 0.15 + f6 * 0.05, -100, 100
    )
    if score >= 70:
        grade, label = "complete_success", "완전 성격"
    elif score >= 40:
        grade, label = "partial_success", "성격이나 약간 혼잡"
    elif score >= -10:
        grade, label = "mixed", "반성반패"
    elif score >= -30:
        grade, label = "failure_with_rescue", "패격이나 구제 있음"
    elif score >= -70:
        grade, label = "clear_failure", "명확한 패격"
    else:
        grade, label = "severe_muddiness", "심한 혼탁"
    return round(score, 1), grade, label


# ── clarity + final_weight ────────────────────────────────────────────────

_CLARITY_MULT = {
    "very_clear": 1.60, "clear_but_mixed": 1.20, "unclear": 0.80,
    "weak_gukguk_priority": 0.60, "special_pattern_uncertain": 1.30,
}
_CLARITY_POLICY = {
    "very_clear": "격국 중심으로 해석한다.",
    "clear_but_mixed": "격국을 중심으로 보되 억부용신으로 보완한다.",
    "unclear": "격국 단정보다 억부·조후 용신 중심으로 해석한다.",
    "weak_gukguk_priority": "격국은 보조 설명으로만 사용한다.",
    "special_pattern_uncertain": "정격·종격 양쪽 가능성을 함께 비교한다.",
}
_BASE_WEIGHT = 0.25


def _clarity_level(confidence: int, sf_score: float, band: str, root_score: float) -> str:
    if band in ("극신약", "태신약") and root_score < 8.0:
        return "special_pattern_uncertain"  # 종격 의심
    if confidence >= 80 and sf_score >= 40:
        return "very_clear"
    if confidence >= 60 and sf_score >= -10:
        return "clear_but_mixed"
    if confidence >= 40:
        return "unclear"
    if band in _WEAK:
        return "weak_gukguk_priority"
    return "unclear"


def _final_weight(level: str) -> tuple[float, str]:
    # geokguk_master_v2 final_gukguk_application_formula 해석 구간.
    raw = _BASE_WEIGHT * _CLARITY_MULT.get(level, 1.0)
    final = round(_clamp(raw, 0.10, 0.60), 3)
    if final >= 0.46:
        interp = "격국 또는 특수격의 핵심 기준으로 사용"
    elif final >= 0.36:
        interp = "격국 중심 해석 가능"
    elif final >= 0.21:
        interp = "격국을 주요 참고 축으로 사용"
    else:
        interp = "격국은 보조 참고"
    return final, interp


# ── 후보 랭킹 / 출력 / 특수격 신호 ────────────────────────────────────────────

def score_all_candidates(
    pillars: FourPillarsResult, cands: list[GeokCandidate],
    force, structure: StructureAnalysis, gongmang_branches: list[str],
) -> list[tuple[GeokCandidate, int, list[dict]]]:
    """후보별 confidence 산출 후 (confidence desc, 위계 desc)로 정렬. force=None이면 위계/투간만."""
    if force is not None:
        counts = _tg_counts(pillars)
        groups = _group_counts(counts)
        band = force.strength.band
        month_void = pillars.month.branch in set(gongmang_branches)
        failures = _detect_failures(counts, groups, band, _month_clashed(structure), month_void)
        has_failures = any(f["active"] for f in failures)
        total = sum(groups.values()) or 1
        clean = all(v / total < 0.50 for v in groups.values())
    else:
        groups = {k: 0 for k in ("peer", "resource", "output", "wealth", "officer")}
        has_failures, clean = False, True
    scored = [(c, *score_candidate(pillars, c, groups, has_failures, clean)) for c in cands]
    scored.sort(key=lambda t: (t[1], _STAGE_RANK.get(t[0].hidden_type, 0)), reverse=True)
    return scored


def candidate_dict(cand: GeokCandidate, confidence: int, status: str) -> dict:
    """격 후보를 화면/디버그용 dict로 직렬화(이름·출처·위계·투간·신뢰도·상태)."""
    stage = _STAGE_KO.get(cand.hidden_type, "?")
    return {
        "name": cand.name,
        "ten_god": cand.ten_god.value,
        "hidden_stem": str(cand.stem),
        "hidden_type": cand.hidden_type,
        "hidden_stage": stage,
        "hidden_ratio": round(cand.ratio, 3),
        "source": f"월지 {stage} {cand.stem}",
        "revealed": cand.revealed,
        "revealed_position": cand.revealed_position,
        "confidence": confidence,
        "status": status,
    }


_DOMINANT_NAME = {"木": "곡직격", "火": "염상격", "土": "가색격", "金": "종혁격", "水": "윤하격"}
_FOLLOW_NAME = {"wealth": "종재격", "officer": "종살격", "output": "종아격"}


def special_signal(force, pillars: FourPillarsResult) -> dict | None:
    """종격/전왕 신호(정격과 병행 검토용). 확정 아님 — 화면/용신 보조 가중치."""
    band = force.strength.band
    root = float(force.strength.components.get("root_score", 0.0))
    fe = force.five_elements
    pct = fe.season_adjusted_element_strength or fe.distribution_environment
    if pct:
        strongest = max(pct, key=lambda e: pct[e])
        maxp = pct[strongest]
        if maxp >= 60.0 and band in ("신강", "태신강", "극신강"):
            return {
                "name": _DOMINANT_NAME.get(strongest, "전왕격"),
                "type": "dominant",
                "confidence": round(min((maxp - 50) / 50, 0.95), 3),
                "reason": f"{strongest} {maxp}% 압도 + {band} → 전왕/일행득기 가능",
            }
    if band in ("극신약", "태신약") and root < 8.0:
        counts = _tg_counts(pillars)
        groups = _group_counts(counts)
        ext = {g: groups[g] for g in ("wealth", "officer", "output")}
        top = max(ext, key=lambda g: ext[g]) if any(ext.values()) else ""
        return {
            "name": _FOLLOW_NAME.get(top, "종세격"),
            "type": "follow",
            "confidence": round(min(max((10 - root) / 10, 0.0), 0.9), 3),
            "reason": f"극신약+무근(root={root:.1f}) → 종격 가능",
        }
    return None


def evaluate_geokguk(
    pillars: FourPillarsResult,
    cand: GeokCandidate,
    force,  # ForceAnalysis (avoid import cycle)
    structure: StructureAnalysis,
    gongmang_branches: list[str],
) -> GeokgukEvaluation:
    """선택 격 후보 기준 전체 평가 — 신뢰도(7요소)·성패(6요소)·파격/구제·명확도·최종가중치."""
    name = cand.name
    counts = _tg_counts(pillars)
    groups = _group_counts(counts)
    month_void = pillars.month.branch in set(gongmang_branches)
    band = force.strength.band
    root_score = float(force.strength.components.get("root_score", 0.0))

    failures = _detect_failures(
        counts, groups, band, _month_clashed(structure), month_void,
        cand.name, structure, Stem(pillars.day.stem),
    )
    damage_types = [f["type"] for f in failures if f["active"]]
    total_active = len(damage_types)
    total_rescued = sum(1 for f in failures if f["active"] and f["rescued"])
    total = sum(groups.values()) or 1
    clean = all(v / total < 0.50 for v in groups.values())  # 청정(한 그룹 50% 미만)

    confidence, conf_factors = score_candidate(
        pillars, cand, groups, total_active > 0, clean
    )
    grade = _confidence_grade(confidence)

    sangsin_groups = _GEOK_SANGSIN.get(name, [])
    sf_score, sf_grade, sf_label = _success_failure(
        pillars, cand, band, sangsin_groups, groups, failures, structure, clean
    )

    level = _clarity_level(confidence, sf_score, band, root_score)
    final_weight, fw_interp = _final_weight(level)

    expr = (
        "격국 무대(직업성·역할)가 매우 선명" if confidence >= 80 else
        "격국 무대가 비교적 선명" if confidence >= 60 else
        "격국 무대가 혼재" if confidence >= 40 else "격국 무대가 흐릿"
    )

    return GeokgukEvaluation(
        confidence_score=confidence,
        pattern_confidence=round(confidence / 100, 3),
        confidence_grade=grade,
        confidence_factors=conf_factors,
        success_failure_score=sf_score,
        success_failure_grade=sf_grade,
        success_failure_label=sf_label,
        damage_types=damage_types,
        failures=failures,
        total_active=total_active,
        total_rescued=total_rescued,
        clarity_level=level,
        clarity_policy=_CLARITY_POLICY.get(level, ""),
        final_weight=final_weight,
        final_weight_interpretation=fw_interp,
        social_expression=expr,
    )
