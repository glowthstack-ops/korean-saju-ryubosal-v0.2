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
from saju_manse_analysis.sinsal.sinsal_catalog import SASAENG
from saju_manse_analysis.structure.geokguk_eval import _group_counts, _tg_counts

from saju_shared_types.constants import (
    BRANCH_ELEMENT,
    CONTROLS,
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

from .event_scoring import favorability_map
from .health_vulnerability import analyze_health_vulnerability
from .relationship_relative_sinsal import get_relative_sinsal
from .wealth_capacity import analyze_wealth_capacity

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
_STORAGE_CLASH_PAIRS = (("辰", "戌"), ("丑", "未"))  # 묘고 충 지지쌍(충개고)
_COMPILED_DEFAULT = Path(__file__).resolve().parents[3] / "compiled"
STRUCTURE_PATTERNS_VERSION = "1.2.0"  # 1.2.0: 용어 감사 63종+별칭 14건(2026-09-17)


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
    # F6(2026-09-17 용어 감사): 파격 구제 근거를 그대로 라벨화 — 관살제겁/재제효인.
    "bigyeob_jaengjae": [("GWANSAL_JEGEOP", "관성")],
    "pyeonin_dosik": [("JAEJE_HYOIN", "재성")],
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
# F6(2026-09-17): 과다 물상 확장 13종 — 기존 7종과 달리 '약한 쪽'에 세력 하한을 둔다
# (존재하되 결핍 또는 표면 세력 12% 미만). 생자 과다 3 · 설기 과다 5 · 반극 5.
_ELEMENT_OVERWHELM_WEAK: list[tuple[str, str, str]] = [
    ("木", "火", "MOKDA_HWASIK"), ("火", "土", "HWADA_TOCHO"), ("金", "水", "GEUMDA_SUTAK"),
    ("木", "水", "MOKDA_SUCHUK"), ("火", "木", "HWADA_MOKBUN"), ("土", "火", "TODA_HWAHOE"),
    ("金", "土", "GEUMDA_TOBYEON"), ("水", "金", "SUDA_GEUMCHIM"),
    ("木", "金", "MOKGYEON_GEUMGYEOL"), ("土", "木", "TOJUNG_MOKJEOL"),
    ("水", "土", "SUDA_TORYU"), ("火", "水", "HWAYEOM_SUYEOL"), ("金", "火", "GEUMDA_HWASIK"),
]
_WEAK_VIS = 12.0  # '존재하되 약' 표면 세력 상한(%)
_THICK_VIS = 30.0  # '두터움/왕' 표면 세력 하한(%) — 목토소통·토수지소
# 두 오행 배합(F6): (일간 오행, 상대 오행, pattern_id, 배제 과다 패턴, 일간 비신약 요구).
# 상생 3종은 일간이 신약이 아니고(약한 일간의 生은 설기) 상대 오행이 결핍이 아니며 대응
# 과다 물상이 미성립일 때, 상극 2종은 극당하는 쪽 일간이 버틸 때(비신약·상대 비과다) 성립.
# 글자 존재 ≠ 작용 성립 → depends 모드. 마지막 원소 = 상대 오행 과다 시 배제 여부.
_ELEMENT_HARMONY: list[tuple[str, str, str, str, bool]] = [
    ("火", "土", "HWATO_SEONGJA", "HWADA_TOCHO", False),
    ("土", "金", "TOGEUM_YUKSU", "TODA_GEUMMAE", False),
    ("水", "木", "SUMOK_CHEONGHWA", "SUDA_MOKBU", False),
    ("木", "金", "GEUMMOK_DONGRYANG", "GEUMDA_MOKJEOL", True),
    ("金", "火", "HWAGEUM_JUIN", "HWADA_GEUMSAK", True),
]
_WINTER_BRANCHES = {"亥", "子", "丑"}
_SUMMER_BRANCHES = {"巳", "午", "未"}
_TRANSFORM_GEOK: dict[str, str] = {  # 化神 오행 → 화기격 pattern_id (F6)
    "土": "HWATO_GYEOK", "金": "HWAGEUM_GYEOK", "水": "HWASU_GYEOK",
    "木": "HWAMOK_GYEOK", "火": "HWAHWA_GYEOK",
}
_RESOURCE_MODEL_TYPES = {"resource_as_yongsin", "resource_curbs_output", "resource_pattern_officer"}
_OUTPUT_MODEL_TYPES = {"eokbu_normal", "output_as_yongsin"}
_RESOURCE_TG = {TenGod.JEONGIN, TenGod.PYEONIN}
_STRONG_BANDS = {"신강", "태신강", "극신강"}
_WEAK_BANDS = {"신약", "태신약", "극신약"}  # 9단계 밴드(strength_score) 약측
_PUNISHMENT_TRIPLES = (frozenset({"寅", "巳", "申"}), frozenset({"丑", "戌", "未"}))
_SASAENG_STR = {str(b.value) for b in SASAENG}  # 사생지(寅申巳亥) 한자
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
                classical_note=entry.classical_note,
                aliases=list(entry.aliases),
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
    # 오행→역할 맵(favorability_map). canonical_roles 는 역할→오행 키라 뒤집어 쓰면 빈 맵이 된다
    # (F6 에서 발견·수정 — 이전엔 affected.role 이 항상 '' 이었다).
    fav = favorability_map(result)
    gwansal_mixed = counts.get("정관", 0) >= 1 and counts.get("편관", 0) >= 1
    for r in resolve_stem_hap(pillars, fav):
        scope = "luck" if r.luck_origin else "natal"
        pair = f"{r.pair[0]}{r.pair[1]}합"
        if r.chart_transform and r.transform_element and not r.luck_origin:  # 화기격 5종(F6)
            tpid = _TRANSFORM_GEOK.get(r.transform_element)
            if tpid:
                real = any("진화" in n for n in r.notes)
                emit(tpid, 0.6 if real else 0.45, "natal",
                     (pair, "진화(일간 무근)" if real else "가화(일간 유근)"))
        if r.hap_mode == "transform":
            continue  # 합화(化)는 P0 combination_clash 밖 — 합화격/용신 계층 소관
        affected_tg = {a.ten_god for a in r.affected}
        # 원국 합은 direction 없이 bind(합반)로만 판정되므로 거살/거관/기신합거는 bind·away 공통.
        bound_or_away = r.hap_mode == "bind" or r.direction == "away"
        if bound_or_away and gwansal_mixed:  # 거살유관/거관유살(F6): 관살 병존 + 편관/정관 묶임
            if "편관" in affected_tg and "정관" not in affected_tg:
                emit("GEOSAL_YUGWAN", 0.55, scope, (pair, "편관 합반·정관 잔류"))
            elif "정관" in affected_tg and "편관" not in affected_tg:
                emit("GEOGWAN_YUSAL", 0.55, scope, (pair, "정관 합반·편관 잔류"))
        if bound_or_away and any(a.role in ("기신", "구신") for a in r.affected):
            emit("GISIN_HAPGEO", 0.55, scope, (pair, "기·구신 합에 묶임"))  # 기신합거(F6)
        if r.direction == "away":
            emit("HAPGEO", 0.6, scope, (pair,))
        elif r.direction == "toward":
            emit("HAPRAE", 0.6, scope, (pair,))
        if r.hap_mode == "bind":
            emit("HAPBAN", 0.55, scope, (pair,))
            # 탐합망극(F6): 묶인 천간이 원국의 다른 천간(합 밖)을 극하는 오행이면 그 극이 약해진다.
            bound_pos = set(r.positions)
            other_els = {
                STEM_ELEMENT[Stem(p.stem)]
                for pos in ("year", "month", "day", "hour")
                if pos not in bound_pos and (p := getattr(pillars, pos)) is not None
            }
            if any(CONTROLS[STEM_ELEMENT[Stem(a.stem)]] in other_els for a in r.affected):
                emit("TAMHAP_MANGGEUK", 0.5, scope, (pair, "극하는 천간이 합에 묶임"))
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
        # 과다 물상 확장 13종(F6): 과다 + 상대 오행 '존재하되 약'(결핍 또는 12% 미만).
        for strong_el, weak_el, pid in _ELEMENT_OVERWHELM_WEAK:
            wv = vis.get(weak_el, 0.0)
            if strong_el in exc and wv > 0 and (weak_el in defi or wv < _WEAK_VIS):
                emit(pid, 0.5, "natal", (f"{strong_el}과다·{weak_el} 약({wv:.0f}%)",))
        if (
            dm_el == "木" and vis.get("火", 0.0) > 0 and "火" not in defi
            and "MOKDA_HWASIK" not in seen  # F6: 목다화식이면 '통명' 아님
        ):
            emit("MOKHWA_TONGMYEONG", 0.55, "natal", ("木일간·火 통명",))
        # 두 오행 배합(F6): 일간 오행 × 상대 오행. 대응 과다 물상 미성립이 전제.
        for base_el, other_el, pid, excl_pid, excl_other_exc in _ELEMENT_HARMONY:
            if dm_el != base_el or vis.get(other_el, 0.0) <= 0 or other_el in defi:
                continue
            if excl_pid in seen or band in _WEAK_BANDS:
                continue
            if excl_other_exc and other_el in exc:
                continue
            emit(pid, 0.5, "natal", (f"{base_el}일간({band})·{other_el} 존재",))
        if (  # 금백수청(F6): 금수상관 조건 + 일간 비신약 + 탁수·열조 배제(金/土/火 과다 없음).
            dm_el == "金" and vis.get("水", 0.0) > 0 and "水" not in defi
            and band not in _WEAK_BANDS and not ({"金", "土", "火"} & exc)
        ):
            emit("GEUMBAEK_SUCHEONG", 0.5, "natal", ("金일간·水 청",))
        if (  # 목토소통(F6): 土 일간 두터움 + 木 존재, 목다토붕 미성립.
            dm_el == "土" and vis.get("木", 0.0) > 0 and "木" not in defi
            and ("土" in exc or vis.get("土", 0.0) >= _THICK_VIS) and "MOKDA_TOBUNG" not in seen
        ):
            emit("MOKTO_SOTONG", 0.5, "natal", (f"土 두터움({vis.get('土', 0.0):.0f}%)·木 존재",))
        if (  # 토수지소(F6): 水 일간 왕 + 土 존재, 토다수탁 미성립.
            dm_el == "水" and vis.get("土", 0.0) > 0 and "土" not in defi
            and ("水" in exc or vis.get("水", 0.0) >= _THICK_VIS) and "TODA_SUTAK" not in seen
        ):
            emit("TOSU_JISO", 0.5, "natal", (f"水 왕({vis.get('水', 0.0):.0f}%)·土 존재",))
        # 조후 명칭(F6): 월지 계절 × 일간 오행 × 火/水 유무.
        natal_stem_els = {
            str(STEM_ELEMENT[Stem(p.stem)])
            for pos in ("year", "month", "day", "hour")
            if (p := getattr(pillars, pos)) is not None
        }
        mb = pillars.month.branch if pillars.month is not None else ""
        if dm_el == "木" and mb in _WINTER_BRANCHES and vis.get("火", 0.0) > 0:
            revealed = "火" in natal_stem_els
            emit("HANMOK_HYANGYANG", 0.55 if revealed else 0.45, "natal",
                 (f"겨울({mb})·火 " + ("투간" if revealed else "지장"),))
        fire_lack = "火" in defi or vis.get("火", 0.0) == 0
        water_lack = "水" in defi or vis.get("水", 0.0) == 0
        if dm_el in ("金", "水") and mb in _WINTER_BRANCHES and fire_lack:
            emit("GEUMHAN_SURAENG", 0.5, "natal", (f"겨울({mb})·火 결핍",))
        if dm_el in ("火", "土") and mb in _SUMMER_BRANCHES and water_lack:
            emit("HWAYEOM_TOJO", 0.5, "natal", (f"여름({mb})·水 결핍",))
        # 천간·지지 비유(F6): 글자 존재 기반, context_only(작용 성립은 별도).
        dm_stem = pillars.day.stem
        other_stems = [
            p.stem for pos in ("year", "month", "hour")
            if (p := getattr(pillars, pos)) is not None
        ]
        all_stems = set(other_stems) | {dm_stem}
        natal_branch_set = {
            p.branch for pos in ("year", "month", "day", "hour")
            if (p := getattr(pillars, pos)) is not None
        }
        if dm_stem == "乙" and "甲" in other_stems:
            emit("DEUNGRA_GYEGAP", 0.45, "natal", ("乙일간·甲 투출",))
        if {"丁", "甲", "庚"} <= all_stems:
            emit("BYEOKGAP_INJEONG", 0.5 if dm_stem == "丁" else 0.45, "natal",
                 ("丁·甲·庚 천간 동시",))
        elif {"丁", "庚"} <= all_stems:
            emit("JEONGHWA_YEONGEUM", 0.45, "natal", ("丁·庚 천간",))
        if dm_stem == "丁" and "丙" in other_stems:
            emit("BYEONGHWA_TALGWANG", 0.45, "natal", ("丁일간·丙 투출",))
        if "甲" in all_stems and ("土" in exc or vis.get("土", 0.0) >= _THICK_VIS):
            emit("GAPMOK_SOTO", 0.45, "natal", (f"甲·土 강({vis.get('土', 0.0):.0f}%)",))
        if "戊" in all_stems and "水" in exc:
            emit("MUTO_JESU", 0.45, "natal", ("戊·水 과다",))
        if dm_stem == "甲" and "水" in exc and "寅" in natal_branch_set:
            emit("SUTANG_GIHO", 0.45, "natal", ("甲일간·水 과다·寅",))
        if dm_stem == "甲" and "火" in exc and "辰" in natal_branch_set:
            emit("HWACHI_SEUNGRYONG", 0.45, "natal", ("甲일간·火 과다·辰",))
        # 십성 강약·균형(F6).
        officer_el = str(ge["officer"])
        off_vis, dm_vis = vis.get(officer_el, 0.0), vis.get(dm_el, 0.0)
        if (
            counts.get("편관", 0) >= 1 and band in ("중화", "중화신강", "신강")
            and dm_vis > 0 and 0.8 <= off_vis / dm_vis <= 1.25
            and (groups["output"] >= 1 or groups["resource"] >= 1)
        ):
            emit("SINSAL_YANGJEONG", 0.5, "natal", (f"관 {off_vis:.0f}%≈일간 {dm_vis:.0f}%",))
        if counts.get("편관", 0) >= 1 and groups["wealth"] >= 1 and band in _STRONG_BANDS and (
            officer_el in defi or off_vis < _WEAK_VIS
        ):
            emit("JAEJA_YAKSAL", 0.5, "natal", (f"{band}·편관 약({off_vis:.0f}%)·재성",))
        if counts.get("편관", 0) >= 1 and groups["wealth"] / total >= 0.30 and band in _WEAK_BANDS:
            emit("JAEDA_SAENGSAL", 0.55, "natal", (f"재성 {groups['wealth'] / total:.0%}·{band}",))
        if band in _STRONG_BANDS and groups["resource"] / total >= 0.35 and groups["peer"] >= 1:
            emit("INWANG_SINWANG", 0.5, "natal", (f"{band}·인성 {groups['resource'] / total:.0%}",))
        if band in _STRONG_BANDS and (
            groups["output"] + groups["wealth"] + groups["officer"]
        ) / total <= 0.15:
            emit("SINWANG_MUUI", 0.55, "natal", (f"{band}·식재관 통로 부재",))
        if band in _WEAK_BANDS and groups["output"] / total >= 0.35:
            emit("SEOLGI_TAEGWA", 0.5, "natal", (f"{band}·식상 {groups['output'] / total:.0%}",))
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

    # 살중제경(F6): 관살 2+ 이고 제(식상)·화(인성)가 있으나 관살 수에 못 미침.
    if groups["officer"] >= 2 and 1 <= groups["output"] + groups["resource"] < groups["officer"]:
        emit("SALJUNG_JEGYEONG", 0.5, "natal",
             (f"관살 {groups['officer']}·제화 {groups['output'] + groups['resource']}",))
    # 재관인상생(F6): 재·관·인 병존 + 재극인 미성립(관성이 통관).
    if (
        "JAE_SAENGGWAN" in seen
        and ("GWAN_IN_SANGSAENG" in seen or "SAL_IN_SANGSAENG" in seen)
        and "JAE_GEUGIN" not in seen and "TAMJAE_GOEIN" not in seen
        and force is not None
        and force.five_elements.visible_percent.get(
            str(group_elements(STEM_ELEMENT[Stem(pillars.day.stem)])["resource"]), 0.0
        ) >= _WEAK_VIS
    ):
        emit("JAEGWANIN_SANGSAENG", 0.5, "natal", ("재생관·관인상생 연쇄·재극인 없음·인성 유력",))
    # 용신 선택 모델 어댑터(F6): 식상설수/인다용재/기식취인 — 점수 불변, 라벨만.
    ya = result.yongsin_analysis
    selected_model = str(ya.final.get("selected_model") or "") if ya is not None else ""
    if force is not None:
        band_y = force.strength.band
        if (
            selected_model in _OUTPUT_MODEL_TYPES and band_y in _STRONG_BANDS
            and groups["output"] >= 1
        ):
            emit("SIKSANG_SEOLSU", 0.55, "natal", (f"{band_y}·모델 {selected_model}",))
    if selected_model == "wealth_breaks_resource" and groups["wealth"] >= 1:
        emit("INDA_YONGJAE", 0.55, "natal", ("모델 재성용신형(인성과다)",))
    if selected_model in _RESOURCE_MODEL_TYPES and counts.get("식신", 0) >= 1:
        emit("GISIK_CHWIIN", 0.5, "natal", (f"식신 존재·모델 {selected_model}",))
    # 용신 유력/무력(F6): 정적 용신 오행의 통근·표면 세력.
    if ya is not None and force is not None:
        yong_el = ya.canonical_roles.get("yongsin") or None  # 역할→오행 키
        if yong_el:
            rooted = any(
                hs.element == yong_el
                for pos in ("year", "month", "day", "hour")
                if (p := getattr(pillars, pos)) is not None
                for hs in p.hidden_stems
            )
            yv = force.five_elements.visible_percent.get(yong_el, 0.0)
            deficient = yong_el in force.five_elements.deficient_elements
            if rooted and yv >= _WEAK_VIS and not deficient:
                # 거의 모든 명식이 유력/무력 중 하나에 해당 → 상위 6 잠식 방지로 강도 낮춤.
                emit("YONGSIN_YURYEOK", 0.4, "natal", (f"용신 {yong_el} 통근·{yv:.0f}%",))
            elif not rooted or deficient:
                emit("YONGSIN_MURYEOK", 0.5, "natal",
                     (f"용신 {yong_el} " + ("무근" if not rooted else "결핍"),))
    # 성중유패/패중유성(F6): 격국 성패 등급 어댑터.
    if geok is not None and geok.evaluation is not None:
        ev = geok.evaluation
        if (
            ev.confidence_grade in ("A", "B") and ev.total_active >= 1
            and ev.total_rescued == 0 and ev.success_failure_grade != "failure_with_rescue"
        ):
            emit("SEONGJUNG_YUPAE", 0.5, "natal",
                 (f"격 신뢰 {ev.confidence_grade}·파격 {ev.total_active}·구제 없음",))
        elif ev.success_failure_grade == "failure_with_rescue":
            emit("PAEJUNG_YUSEONG", 0.5, "natal", (f"구제 {ev.total_rescued}/{ev.total_active}",))
    # 특수 배치(F6, 설명 태그 전용): 일록귀시·시상편재·천원일기.
    hour = pillars.hour
    if hour is not None:
        if hour.twelve_unseong == "건록":
            emit("ILROK_GWISI", 0.4, "natal", (f"시지 {hour.branch} 건록",))
        if hour.stem_ten_god == "편재" and any(
            hs.element == hour.stem_element
            for pos in ("year", "month", "day", "hour")
            if (p := getattr(pillars, pos)) is not None
            for hs in p.hidden_stems
        ):
            emit("SISANG_PYEONJAE", 0.45, "natal", (f"시간 {hour.stem} 편재 통근",))
        if len({p.stem for p in (pillars.year, pillars.month, pillars.day, hour)}) == 1:
            emit("CHEONWON_ILGI", 0.5, "natal", (f"4천간 {pillars.day.stem}",))

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
        # 잡기인수격(F6): 같은 규칙을 인성으로 — 월지 사고 지장간 인성 + 투간 여부.
        found_in: TenGod | None = None
        revealed_in = False
        for hs, _kind, _w in hidden_stems_for(Branch(month.branch)):
            if ten_god(dm, hs) in _RESOURCE_TG:
                found_in = ten_god(dm, hs)
                if str(hs) in natal_stems:
                    revealed_in = True
        if found_in is not None:
            note_in = f"월지 잡기 {found_in.value}" + ("(투간)" if revealed_in else "(미투간)")
            emit("JAPGI_INSU_GYEOK", 0.55 if revealed_in else 0.4, "natal", (note_in,))

    # ── H. 사고수 확장 — 역마·형 세분·행동/제어·건강 부담 (2026-07-23 승인안 A) ──
    # 역마는 글자살(寅申巳亥 보유)이 아니라 연지·일지 삼합국 기준 상대 12신살로
    # 산출한다(데굴님 정정). 사생지 충돌은 MOVEMENT_BRANCH_CLASH 보조 라벨로만.
    yeokma_refs: dict[str, list[str]] = {}  # 역마 지지(한자) → 기준 라벨(연지/일지)
    for ref_name, base_pos in (("연지", pillars.year), ("일지", pillars.day)):
        if base_pos is None:
            continue
        for nb in natal_branches:
            if get_relative_sinsal(Branch(base_pos.branch), Branch(nb)).sinsal == "역마살":
                yeokma_refs.setdefault(nb, []).append(ref_name)

    rel_kinds_by_branch: dict[str, set[str]] = {}  # 지지별 충·형·파·해 종류 집계
    if sa is not None:
        for it in sa.interactions:
            rt = it.relation_type
            mem = set(it.members)
            if rt in ("clash", "punishment", "self_punishment", "break", "harm"):
                kind = "punishment" if rt == "self_punishment" else rt
                for m in mem:
                    rel_kinds_by_branch.setdefault(m, set()).add(kind)
            ym = sorted(mem & set(yeokma_refs))
            mark = "".join(sorted(mem))
            if rt == "clash":
                if ym:
                    refs = "·".join(sorted(set(yeokma_refs[ym[0]])))
                    emit("YEOKMA_CLASH_ACTIVE", 0.65, "natal",
                         (f"{refs} 기준 역마 {ym[0]} 충({mark})",))
                elif mem & _SASAENG_STR:
                    emit("MOVEMENT_BRANCH_CLASH", 0.45, "natal", (f"이동지 충 {mark}",))
            if rt in ("punishment", "self_punishment"):
                if ym:
                    refs = "·".join(sorted(set(yeokma_refs[ym[0]])))
                    emit("YEOKMA_PUNISHMENT_ACTIVE", 0.6, "natal",
                         (f"{refs} 기준 역마 {ym[0]} 형({mark})",))
                elif mem & _SASAENG_STR:
                    emit("MOVEMENT_BRANCH_CLASH", 0.45, "natal", (f"이동지 형 {mark}",))
            if rt == "punishment" and "삼형" in it.notes:
                triple = next((t for t in _PUNISHMENT_TRIPLES if mem <= t), None)
                if triple is not None and len(mem) >= 3:
                    emit("THREE_PUNISHMENT_COMPLETE", 0.7, "natal", (f"삼형 완성 {mark}",))
                elif triple is not None:
                    missing = "".join(sorted(triple - mem))
                    emit("THREE_PUNISHMENT_PARTIAL", 0.5, "natal",
                         (f"부분 삼형 {mark}(미완 {missing} — 운 유입 시 완성)",))
            if rt == "punishment" and "무례지형" in it.notes:
                emit("ZI_MAO_PUNISHMENT", 0.5, "natal", (f"자묘형 {mark}",))
            if rt == "self_punishment":
                emit("SELF_PUNISHMENT", 0.5, "natal", (f"자형 {mark} 병존",))

    # 다중 관계 압박 — 동일 지지에 충·형·파·해 2종 이상.
    multi = sorted(
        (b for b, ks in rel_kinds_by_branch.items() if len(ks) >= 2),
        key=lambda b: -len(rel_kinds_by_branch[b]),
    )
    if multi:
        kinds = "·".join(sorted(rel_kinds_by_branch[multi[0]]))
        emit("MULTI_RELATION_STRESS", 0.55, "natal", (f"{multi[0]}: {kinds} 중첩",))

    # 동일 영역(오행) 반복 압박 — 같은 오행 지지가 충·형에 2회 이상 피격.
    elem_hits: dict[str, int] = {}
    for b, ks in rel_kinds_by_branch.items():
        if ks & {"clash", "punishment"}:
            el = str(BRANCH_ELEMENT[Branch(b)])
            elem_hits[el] = elem_hits.get(el, 0) + len(ks & {"clash", "punishment"})
    repeated = sorted((e for e, n in elem_hits.items() if n >= 2), key=lambda e: -elem_hits[e])
    if repeated:
        emit("SAME_AREA_REPEATED_STRESS", 0.5, "natal",
             (f"{repeated[0]} 축 반복 피격({elem_hits[repeated[0]]}회)",))

    # 행동 압력·제어·회복·조후 — force_analysis 기반(질병명 생성 금지, 힌트 전용).
    if force is not None:
        fe2 = force.five_elements
        exc2, defi2, vis2 = set(fe2.excessive_elements), set(fe2.deficient_elements), (
            fe2.visible_percent
        )
        band2 = force.strength.band
        act_ratio = (groups["output"] + groups["peer"]) / total
        ctrl_ratio = (groups["officer"] + groups["resource"]) / total
        if act_ratio >= 0.55 and band2 in _STRONG_BANDS:
            emit("ACTION_PRESSURE_EXCESS", _clamp(0.35 + act_ratio * 0.4, 0.4, 0.7), "natal",
                 (f"식상·비겁 {act_ratio:.0%}·{band2}",))
            if ctrl_ratio <= 0.20:
                emit("CONTROL_RESOURCE_DEFICIT", 0.6, "natal",
                     (f"제어 축(관·인) {ctrl_ratio:.0%}",))
        if band2 in _WEAK_BANDS and groups["resource"] / total <= 0.10:
            emit("RECOVERY_RESOURCE_WEAK", 0.55, "natal", (f"{band2}·인성 미약",))
        if band2 in _STRONG_BANDS and groups["output"] == 0:
            emit("FLOW_STAGNATION_BURDEN", 0.5, "natal", (f"{band2}·식상 부재",))
        if exc2:
            emit("ELEMENT_EXCESS_ACTIVE", _clamp(0.4 + 0.1 * len(exc2), 0.4, 0.7), "natal",
                 ("·".join(sorted(exc2)) + " 과다",))
        if defi2:
            emit("ELEMENT_DEFICIENCY_ACTIVE", _clamp(0.4 + 0.1 * len(defi2), 0.4, 0.7),
                 "natal", ("·".join(sorted(defi2)) + " 결핍",))
        heat = "火" in exc2 and ("水" in defi2 or vis2.get("水", 0.0) == 0)
        cold = "水" in exc2 and ("火" in defi2 or vis2.get("火", 0.0) == 0)
        if heat:
            emit("HEAT_DRYNESS_BURDEN", 0.55, "natal", ("火 과다·水 약",))
        if cold:
            emit("COLD_DAMP_BURDEN", 0.55, "natal", ("水 과다·火 약",))
        if heat or cold:
            emit("CLIMATE_IMBALANCE_ACTIVE", 0.5, "natal",
                 ("열조 부담" if heat else "한습 부담",))
        # 천한지동(F6): 한습 부담 + 천간에 火(丙丁) 부재 + (겨울 월지 또는 火 표면 0).
        if cold and not ({"丙", "丁"} & {
            p.stem for pos in ("year", "month", "day", "hour")
            if (p := getattr(pillars, pos)) is not None
        }):
            mb2 = pillars.month.branch
            if mb2 in _WINTER_BRANCHES or vis2.get("火", 0.0) == 0:
                emit("CHEONHAN_JIDONG", 0.55, "natal", (f"한습·火 천간 부재·월지 {mb2}",))

        # 인성 지원 약화 — 부재/잠복/약/피극 세분(단독 사건 판정 금지, 보조 라벨).
        ge2 = group_elements(STEM_ELEMENT[Stem(pillars.day.stem)])
        res_el2, wealth_el2 = str(ge2["resource"]), str(ge2["wealth"])
        dm2 = Stem(pillars.day.stem)
        res_state: str | None = None
        res_strength = 0.5
        if groups["resource"] == 0:
            latent = any(
                ten_god(dm2, hs) in (TenGod.JEONGIN, TenGod.PYEONIN)
                for nb in natal_branches
                for hs, _k, _w in hidden_stems_for(Branch(nb))
            )
            res_state, res_strength = ("LATENT_ONLY", 0.5) if latent else ("ABSENT", 0.6)
        elif res_el2 in defi2 or vis2.get(res_el2, 0.0) < 8:
            res_state = "WEAK"
        elif wealth_el2 in exc2:
            res_state, res_strength = "SUPPRESSED", 0.55
        if res_state is not None:
            emit("RESOURCE_SUPPORT_WEAK", res_strength, "natal", (f"상태: {res_state}",))

        # 재성 노출·보호 약 — 재성 투간 + 관성 부재/미약.
        revealed_wealth = any(
            ten_god(dm2, Stem(p2.stem)) in (TenGod.JEONGJAE, TenGod.PYEONJAE)
            for pos in ("year", "month", "hour")
            if (p2 := getattr(pillars, pos)) is not None
        )
        if revealed_wealth and (groups["officer"] == 0 or ctrl_ratio <= 0.08):
            emit("WEALTH_EXPOSURE_WITH_WEAK_CONTROL", 0.5, "natal",
                 ("재성 투간·관성 " + ("부재" if groups["officer"] == 0 else "미약"),))

    # 문서·권한 충돌 — 인·관·식상 병존 + 견제 우세(상관견관·제살태과 동반 등).
    if (
        groups["resource"] >= 1 and groups["officer"] >= 1 and groups["output"] >= 1
        and ("SANGGWAN_GYEONGWAN" in seen or "JESAL_TAEGWA" in seen
             or groups["output"] >= 2 * groups["officer"])
    ):
        emit("DOCUMENT_AUTHORITY_CONFLICT", 0.5, "natal", ("인·관·식상 견제 우세",))

    # 명의·권한 보조 — 비겁 경쟁 구조 동반 시에만(문맥 전용, secondaryEvidenceOnly).
    if ("GUNGEOP_JAENGJAE" in seen or "BIGEOP_TALJAE" in seen) and (
        groups["resource"] >= 1 or groups["officer"] >= 1
    ):
        emit("IDENTITY_AUTHORIZATION_STRESS", 0.35, "natal", ("비겁 경쟁+문서·권한 축",))

    # 예기 보조 신호 — 양인·백호·괴강·편관 중첩 2종+(단독 해석 금지).
    aux: set[str] = set()
    te = result.traditional_extras
    if te is not None and te.sinsal is not None:
        for s_item in te.sinsal.full_list:
            if s_item.name in ("양인", "백호", "괴강"):
                aux.add(s_item.name)
    if counts.get("편관", 0) >= 2:
        aux.add("편관 중첩")
    if len(aux) >= 2:
        emit("SHARP_INJURY_AUXILIARY", 0.45, "natal", ("·".join(sorted(aux)),))

    out.sort(key=lambda d: d.strength, reverse=True)
    return out
