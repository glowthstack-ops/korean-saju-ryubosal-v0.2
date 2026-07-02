"""구조 패턴 감지기 — 기존 분석 결과를 표준 pattern_id 로 재라벨링하는 어댑터.

설계: `doc/v2_2/docs/13_STRUCTURE_PATTERNS.md` (Step ②).

핵심 원칙(설계 §9, inert 확장):
- **기존 감지기 재사용 우선**. 격국 파격(`geokguk_eval._detect_failures`), 격국명,
  종격, 합 작용(`resolve_stem_hap`)을 그대로 읽어 pattern_id 로 매핑한다.
- 신규 감지(`new:`)는 P0 미보유 패턴만 최소 구현(생·순환/제어의 십성 병존 감지).
- **길흉·confidence·favorability 를 만들지 않는다.** `strength` 는 성립 강도(0~1)뿐.
- 이 감지기는 사건 라벨을 생성하지 않는다 — 사전의 `domain_hints`(후보)만 승계.

반환은 감지된 **전체** 목록(내부 보존·회귀 검증용). LLM 노출용 상위 N 선별은
`select_llm_patterns()` 가 담당한다(Step ④에서 배선).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from saju_manse_analysis.relations.hap_modes import resolve_stem_hap
from saju_manse_analysis.structure.geokguk_eval import _group_counts, _tg_counts

from saju_shared_types.constants import (
    STEM_ELEMENT,
    group_elements,
    hidden_stems_for,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem, TenGod
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.structure_patterns import (
    DetectedPattern,
    StructurePatternDict,
    StructurePatternEntry,
)

from .health_vulnerability import analyze_health_vulnerability
from .wealth_capacity import analyze_wealth_capacity

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
_STORAGE_CLASH_PAIRS = (("辰", "戌"), ("丑", "未"))  # 묘고 충 지지쌍(충개고)
_COMPILED_DEFAULT = Path(__file__).resolve().parents[3] / "compiled"
STRUCTURE_PATTERNS_VERSION = "1.0.0"


@lru_cache(maxsize=8)
def load_structure_patterns(
    dictionaries_dir: Path = _DICTS_DEFAULT, compiled_dir: Path = _COMPILED_DEFAULT
) -> StructurePatternDict:
    """구조 패턴 사전 로드(캐시). 컴파일 스냅샷 우선, 없으면 원본 폴백(CLAUDE.md 원칙 5)."""
    snapshot = compiled_dir / f"structure_patterns_v{STRUCTURE_PATTERNS_VERSION}.json"
    if snapshot.exists():
        return StructurePatternDict.model_validate(json.loads(snapshot.read_text("utf-8")))
    raw = json.loads((dictionaries_dir / "structure_patterns.json").read_text("utf-8"))
    return StructurePatternDict.model_validate(raw)


# ── 어댑터 매핑 테이블 (기존 감지기 → pattern_id) ──────────────────────────

# 격국 파격 type(geokguk_eval._detect_failures) → pattern_id.
_FAILURE_TO_PID: dict[str, str] = {
    "shangguan_attacks_officer": "SANGGWAN_GYEONGWAN",
    "mixed_officer_killing": "GWANSAL_HONJAP",
    "killing_overwhelms_weak": "GWANDA_SINYAK",
    "wealth_overwhelms_weak": "JAEDA_SINYAK",
    "pyeonin_dosik": "PYEONIN_DOSIK",
    "bigyeob_jaengjae": "GUNGEOP_JAENGJAE",
    "killing_uncontrolled": "GWANSAL_MUJE",
    "resource_overload": "INDA_SINYAK",
    "officer_combined_away": "HAPGEO",
}

# 파격이 '구제(rescued)'되면 파생되는 제어/통관 패턴 (rescue_evidence 부분일치, ""=무조건).
_RESCUE_DERIVED: dict[str, list[tuple[str, str]]] = {
    "mixed_officer_killing": [("SIKSIN_JESAL", "식신"), ("GWANSAL_YUJE", "")],
    "killing_overwhelms_weak": [
        ("SAL_IN_SANGSAENG", "인성"), ("SIKSIN_JESAL", "식신"),
        ("SALJUNG_YONGIN", "인성"), ("SALJUNG_YONGSIK", "식신"),  # P1 살중용인/용식(F3)
    ],
}

# 전왕(일행득기) special_pattern.name(dominant) → pattern_id (P2, F3).
_DOMINANT_NAME_TO_PID: dict[str, str] = {
    "곡직격": "GOKJIK_GYEOK", "염상격": "YEOMSANG_GYEOK", "가색격": "GASAEK_GYEOK",
    "종혁격": "JONGHYEOK_GYEOK", "윤하격": "YUNHA_GYEOK",
}

# 오행 극제 물상(A多B): (과다 원소, 극/설 당하는 원소, pattern_id) (P1, F3).
_ELEMENT_OVERWHELM: list[tuple[str, str, str]] = [
    ("土", "金", "TODA_GEUMMAE"), ("水", "木", "SUDA_MOKBU"), ("木", "土", "MOKDA_TOBUNG"),
    ("火", "金", "HWADA_GEUMSAK"), ("金", "木", "GEUMDA_MOKJEOL"), ("土", "水", "TODA_SUTAK"),
    ("水", "火", "SUDA_HWAMYEOL"),
]
_STRONG_BANDS = {"신강", "태신강", "극신강"}
_STORAGE_BRANCHES = {"辰", "戌", "丑", "未"}  # 사고(잡기) 지지
_WEALTH_OFFICER_TG = {TenGod.JEONGJAE, TenGod.PYEONJAE, TenGod.JEONGGWAN, TenGod.PYEONGWAN}

# 격국 주격명 → pattern_id (P0 미보유 격은 매핑 생략).
_GEOK_NAME_TO_PID: dict[str, str] = {
    "정관격": "JEONGGWAN_GYEOK",
    "편관격": "CHILSAL_GYEOK",
    "식신격": "SIKSIN_GYEOK",
    "상관격": "SANGGWAN_GYEOK",
    "정인격": "JEONGIN_GYEOK",
    "편인격": "PYEONIN_GYEOK",
}

# 종격(special_pattern.name) → pattern_id.
_FOLLOW_NAME_TO_PID: dict[str, str] = {
    "종재격": "JONGJAE_GYEOK",
    "종살격": "JONGSAL_GYEOK",
    "종아격": "JONGA_GYEOK",  # P2, F3
    "종세격": "JONGSE_GYEOK",  # P2, F3
}

# 생·순환/제어 병존 규칙: pattern_id → (필수 개별 십성, 필수 그룹). 둘 다 충족 시 감지.
# exam_outcome_patterns 의 '패턴 쌍이 모두 있으면 적용'을 원국 구조로 일반화(detector_source: new).
_PRESENCE_RULES: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    ("SIKSIN_SAENGJAE", ("식신",), ("wealth",)),
    ("SANGGWAN_SAENGJAE", ("상관",), ("wealth",)),
    ("SIKSANG_SAENGJAE", ("식신", "상관"), ("wealth",)),
    ("JAE_SAENGGWAN", ("정관",), ("wealth",)),
    ("GWAN_IN_SANGSAENG", ("정관",), ("resource",)),
    ("SAL_IN_SANGSAENG", ("편관",), ("resource",)),
    ("JAE_SAENGSAL", ("편관",), ("wealth",)),
    ("SIKSIN_JESAL", ("식신", "편관"), ()),
    ("SANGGWAN_JESAL", ("상관", "편관"), ()),
    ("SANGGWAN_PAEIN", ("상관", "정인"), ()),  # P1, F3 — 상관패인
]


_MAX_LLM_PATTERNS = 6  # LLM 노출 상한(설계 §8, 토큰 가드).


def select_llm_patterns(
    patterns: list[DetectedPattern],
    *,
    domains: set[str] | None = None,
    max_count: int = _MAX_LLM_PATTERNS,
) -> list[DetectedPattern]:
    """LLM 노출용 상위 N 선별. 전체 감지는 호출측이 별도 보존한다(내부/LLM 분리, 설계 §8).

    `domains`(질문 도메인의 EventKeyV2 집합)가 주어지면 domain_hints 가 겹치는 패턴을 앞으로
    정렬(도메인 우선)한 뒤 상위 N 을 취한다 — 매칭이 6개 미만이면 나머지는 strength 순으로
    채워 빈 목록을 만들지 않는다(soft filter). `domains=None`(일반 질문)이면 strength desc 결정적.
    질문 가변 경로 전용이며, 캐시 프리픽스에는 넣지 않는다(질문마다 값이 달라짐).
    """
    ranked = sorted(patterns, key=lambda d: d.strength, reverse=True)
    if domains:
        ranked = sorted(ranked, key=lambda d: bool(set(d.domain_hints) & domains), reverse=True)
    return ranked[:max_count]


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def detect_structure_patterns(
    result: ManseV2Result, *, dictionaries_dir: Path = _DICTS_DEFAULT
) -> list[DetectedPattern]:
    """원국 결과에서 구조 패턴을 감지한다(strength desc 정렬, 전체 반환).

    Args:
        result: 만세력 통합 결과. `pillars`/`geokguk`/`structure_analysis`/
            `yongsin_analysis` 를 읽는다(없으면 해당 감지 생략).
        dictionaries_dir: 사전 디렉토리(테스트 오버라이드용).

    Returns:
        감지된 `DetectedPattern` 전체(중복 pattern_id 없음). 길흉 미확정.
    """
    dic = load_structure_patterns(dictionaries_dir)
    by_id: dict[str, StructurePatternEntry] = {p.pattern_id: p for p in dic.patterns}
    out: list[DetectedPattern] = []
    seen: set[str] = set()

    def emit(pid: str, strength: float, scope: str, extra: tuple[str, ...] = ()) -> None:
        if pid in seen:
            return
        entry = by_id.get(pid)
        if entry is None:
            return
        seen.add(pid)
        ev = list(entry.evidence) + [e for e in extra if e]
        out.append(
            DetectedPattern(
                pattern_id=entry.pattern_id,
                name_ko=entry.name_ko,
                family=list(entry.family),
                strength=round(_clamp(strength, 0.0, 1.0), 3),
                scope=scope,
                polarity_mode=entry.polarity_mode,
                favorability=None,
                domain_hints=list(entry.domain_hints),
                evidence=ev,
                llm_tag=entry.llm_tag,
            )
        )

    pillars = result.pillars
    if pillars is None:
        return out

    counts = _tg_counts(pillars)
    groups = _group_counts(counts)
    total = sum(groups.values()) or 1

    # ── A. 격국 (adapter: GeokgukResult) ──
    geok = result.geokguk
    if geok is not None:
        conf = geok.evaluation.pattern_confidence if geok.evaluation is not None else 0.5
        main_pid = _GEOK_NAME_TO_PID.get(geok.main_structure or "")
        if main_pid:
            emit(main_pid, conf, "natal", (f"주격 {geok.main_structure}",))
        sp = geok.special_pattern
        if sp is not None and sp.get("type") == "follow":
            fpid = _FOLLOW_NAME_TO_PID.get(str(sp.get("name", "")))
            if fpid:
                emit(fpid, float(sp.get("confidence", 0.5)), "natal", (str(sp.get("name", "")),))
        if sp is not None and sp.get("type") == "dominant":  # 전왕(일행득기) — P2, F3
            dpid = _DOMINANT_NAME_TO_PID.get(str(sp.get("name", "")))
            if dpid:
                emit(dpid, float(sp.get("confidence", 0.5)), "natal", (str(sp.get("name", "")),))

        # ── B. 파격 어댑터 (conflict/overload/control) ──
        if geok.evaluation is not None:
            for f in geok.evaluation.failures:
                if not f.get("active"):
                    continue
                ftype = str(f.get("type", ""))
                rescued = bool(f.get("rescued"))
                pid = _FAILURE_TO_PID.get(ftype)
                if pid:
                    emit(pid, 0.5 if rescued else 0.75, "natal", (str(f.get("evidence", "")),))
                for dpid, needle in _RESCUE_DERIVED.get(ftype, []):
                    if rescued and (needle == "" or needle in str(f.get("rescue_evidence", ""))):
                        emit(dpid, 0.55, "natal", (str(f.get("rescue_evidence", "")),))

    # ── C. 생·순환/제어 병존 감지 (new: exam 로직 일반화) ──
    for pid, need_gods, need_groups in _PRESENCE_RULES:
        if all(counts.get(g, 0) >= 1 for g in need_gods) and all(
            groups.get(grp, 0) >= 1 for grp in need_groups
        ):
            members_total = sum(counts.get(g, 0) for g in need_gods) + sum(
                groups.get(grp, 0) for grp in need_groups
            )
            emit(pid, _clamp(0.4 + 0.1 * members_total, 0.4, 0.85), "natal")

    # 비겁탈재(new): 비겁 2+ & 재성 존재 & 군겁쟁재(강)까지는 아닌 경증(과발화 방지).
    if (
        "BIGEOP_TALJAE" not in seen
        and "GUNGEOP_JAENGJAE" not in seen
        and groups["peer"] >= 2
        and groups["wealth"] >= 1
    ):
        emit("BIGEOP_TALJAE", _clamp(0.35 + 0.1 * groups["peer"], 0.35, 0.7), "natal")

    # 인다신약 병존 폴백(new): 인성 과다(≥40%) + 실행 축(식상+재) 미약.
    if "INDA_SINYAK" not in seen and groups["resource"] / total >= 0.40 and (
        groups["output"] + groups["wealth"]
    ) / total <= 0.20:
        emit("INDA_SINYAK", _clamp(0.4 + groups["resource"] / total, 0.4, 0.8), "natal")

    # ── D. 합 작용 (adapter: resolve_stem_hap) — 합래/합거/합반 ──
    canon = result.yongsin_analysis.canonical_roles if result.yongsin_analysis is not None else {}
    fav = {el: role for el, role in canon.items() if role}
    for r in resolve_stem_hap(pillars, fav):
        scope = "luck" if r.luck_origin else "natal"
        pair = f"{r.pair[0]}{r.pair[1]}합"
        if r.hap_mode == "transform":
            continue  # 합화(化)는 P0 combination_clash 밖 — 합화격/용신 계층 소관
        if r.direction == "away":
            emit("HAPGEO", 0.6, scope, (pair,))
        elif r.direction == "toward":
            emit("HAPRAE", 0.6, scope, (pair,))
        if r.hap_mode == "bind":
            emit("HAPBAN", 0.55, scope, (pair,))
        if r.contend:  # 쟁합·투합 — P1, F3
            emit("JAENGHAP", 0.55, scope, (pair,))

    # ── E. 충동 / 합충병견 / 충중봉합 (adapter: StructureAnalysis.interactions) ──
    # relation_type 은 영문 enum 값(clash / six_combination / three_harmony / stem_combination /
    # directional / half_harmony / ...). 한글이 아님에 주의.
    sa = result.structure_analysis
    if sa is not None:
        has_hap = False
        hap_members: set[str] = set()
        chung_member_sets: list[set[str]] = []
        for it in sa.interactions:
            rt = it.relation_type
            if "combination" in rt or "harmony" in rt or rt == "directional":  # 합류(천간합~방합)
                has_hap = True
                hap_members |= set(it.members)
            if rt == "clash":  # 지지충
                if not chung_member_sets:
                    emit("CHUNGDONG", 0.6, "natal", ("".join(it.members),))
                chung_member_sets.append(set(it.members))
        if has_hap and chung_member_sets:  # 합충병견 — P1(F4)
            emit("HAPCHUNG_BYEONGGYEON", 0.55, "natal", ("합·충 공존",))
            if any(cm & hap_members for cm in chung_member_sets):  # 충중봉합
                emit("CHUNGJUNG_BONGHAP", 0.5, "natal", ("충-합 지지 공유",))
        # 제살태과(new, P1): 편관 존재 + 식상이 편관을 과도 제어.
        if counts.get("편관", 0) >= 1 and groups["output"] >= 2 * groups["officer"] and (
            groups["output"] >= 2
        ):
            emit("JESAL_TAEGWA", 0.5, "natal", ("식상 과다·편관 과제어",))

    # ── F. 묘고(墓庫) 구조 (adapter: health_vulnerability 입묘 / wealth_capacity 개고) ──
    # 원국 구조 존재만 감지한다(운 activation 은 EventEngine 소관). 셋 다 natal 판정 가능.
    natal_branches = {
        p.branch
        for pos in ("year", "month", "day", "hour")
        if (p := getattr(pillars, pos)) is not None
    }
    hv = analyze_health_vulnerability(result)
    if hv.day_master_tomb_branch in natal_branches or hv.food_god_tomb_branch in natal_branches:
        emit("IPMYO", 0.55, "natal", ("일간/식신 묘지 지지 존재",))
    if any(a in natal_branches and b in natal_branches for a, b in _STORAGE_CLASH_PAIRS):
        emit("CHUNGGAE", 0.6, "natal", ("묘고 충 지지쌍 존재",))
    if analyze_wealth_capacity(result).storage_repeat:
        emit("GAEGO", 0.5, "natal", ("동일 묘고 병존(충개고 잠재)",))

    # 득비이재(new, P1): 재다신약을 비겁으로 운용.
    if "DEUKBI_IJAE" not in seen and "JAEDA_SINYAK" in seen and groups["peer"] >= 1:
        emit("DEUKBI_IJAE", 0.5, "natal", ("재다신약+비겁 운용",))

    # ── G. 오행 물상 · 신강약×재성 (F3, adapter: force_analysis) ──
    force = result.force_analysis
    if force is not None:
        fe = force.five_elements
        exc = set(fe.excessive_elements)
        defi = set(fe.deficient_elements)
        vis = fe.visible_percent
        band = force.strength.band
        ge = group_elements(STEM_ELEMENT[Stem(pillars.day.stem)])
        dm_el, wealth_el, resource_el = str(ge["peer"]), str(ge["wealth"]), str(ge["resource"])

        for strong_el, weak_el, pid in _ELEMENT_OVERWHELM:  # 오행 극제 물상
            if strong_el in exc and vis.get(weak_el, 0.0) > 0 and weak_el not in exc:
                emit(pid, 0.55, "natal", (f"{strong_el}과다·{weak_el} 존재",))
        if dm_el == "木" and vis.get("火", 0.0) > 0 and "火" not in defi:
            emit("MOKHWA_TONGMYEONG", 0.55, "natal", ("木일간·火 통명",))
        if dm_el == "金" and vis.get("水", 0.0) > 0 and "水" not in defi:
            emit("GEUMSU_SANGGWAN", 0.55, "natal", ("金일간·水 식상",))
        if wealth_el in exc and vis.get(resource_el, 0.0) > 0:  # 재극인/탐재괴인(재 과다)
            emit("JAE_GEUGIN", 0.6, "natal", (f"재({wealth_el})과다·인({resource_el})",))
            if resource_el in defi:
                emit("TAMJAE_GOEIN", 0.6, "natal", (f"재과다·인({resource_el}) 훼손",))
        if band in _STRONG_BANDS:  # 신왕재왕/재약
            if wealth_el in exc or vis.get(wealth_el, 0.0) >= 20:
                emit("SINWANG_JAEWANG", 0.55, "natal", (f"{band}·재({wealth_el}) 왕",))
            elif wealth_el in defi or vis.get(wealth_el, 0.0) < 8:
                emit("SINWANG_JAEYAK", 0.5, "natal", (f"{band}·재({wealth_el}) 약",))
        su, hwa = vis.get("水", 0.0), vis.get("火", 0.0)  # 수화기제/미제 — P1(F4)
        if su > 0 and hwa > 0:
            both_healthy = "水" not in defi and "火" not in defi
            if su >= 15 and hwa >= 15 and both_healthy and abs(su - hwa) <= 15:
                emit("SUHWA_GIJE", 0.5, "natal", ("水火 균형",))
            elif "水" in defi or "火" in defi or abs(su - hwa) >= 30:
                emit("SUHWA_MIJE", 0.5, "natal", ("水火 불균형",))

    # 양인합살(adapter, P1): 양인격 + 편관.
    if geok is not None and geok.main_structure == "양인격" and counts.get("편관", 0) >= 1:
        emit("YANGIN_HAPSAL", 0.6, "natal", ("양인격+편관",))

    # 상관용인/상관상진(adapter, P1/F4): 상관격 기반.
    if geok is not None and geok.main_structure == "상관격":
        if groups["resource"] >= 1:
            emit("SANGGWAN_YONGIN", 0.55, "natal", ("상관격+인성",))
        if groups["officer"] == 0:
            emit("SANGGWAN_SANGJIN", 0.55, "natal", ("상관격·관성 부재",))

    # 잡기재관격(P2, F5): 월지 사고(辰戌丑未) 지장간에 재/관 → 투간 여부로 강도.
    month = pillars.month
    if month is not None and month.branch in _STORAGE_BRANCHES:
        dm = Stem(pillars.day.stem)
        natal_stems = {
            p.stem for pos in ("year", "month", "day", "hour")
            if (p := getattr(pillars, pos)) is not None
        }
        found: TenGod | None = None
        revealed = False
        for hs, _kind, _w in hidden_stems_for(Branch(month.branch)):
            if ten_god(dm, hs) in _WEALTH_OFFICER_TG:
                found = ten_god(dm, hs)
                if str(hs) in natal_stems:  # 투간
                    revealed = True
        if found is not None:
            note = f"월지 잡기 {found.value}" + ("(투간)" if revealed else "(미투간·개고 대기)")
            emit("JAPGI_JAEGWAN_GYEOK", 0.6 if revealed else 0.45, "natal", (note,))

    out.sort(key=lambda d: d.strength, reverse=True)
    return out
