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

from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.structure_patterns import (
    DetectedPattern,
    StructurePatternDict,
    StructurePatternEntry,
)

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
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
    "killing_overwhelms_weak": [("SAL_IN_SANGSAENG", "인성"), ("SIKSIN_JESAL", "식신")],
}

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
]


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

    # ── E. 충동 (adapter: StructureAnalysis.interactions) ──
    sa = result.structure_analysis
    if sa is not None:
        for it in sa.interactions:
            if "충" in it.relation_type:
                emit("CHUNGDONG", 0.6, "natal", ("".join(it.members),))
                break

    # NOTE(설계 §5): 충개(沖開)·입묘(入墓)·개고(開庫)는 묘고 신호가 다른 엔진
    # (wealth_capacity·structural_context)에 있어 결과 컨텍스트 배선이 필요하다.
    # 사전에는 정의되어 있으며(Step ①) 감지는 Step ④ LLM 배선에서 연결한다.

    out.sort(key=lambda d: d.strength, reverse=True)
    return out
