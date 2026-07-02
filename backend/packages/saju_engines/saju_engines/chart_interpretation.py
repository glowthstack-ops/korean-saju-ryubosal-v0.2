"""⑤ 명식 구조 + 해석 자료 빌더 (v2.2.1, docs/06 chart_interpretation).

해석 사전(interpretations/)에서 사용자 명식과 관련된 텍스트만 발췌해
LLM 입력의 **고정 prefix**(캐시 대상)를 만든다. 규칙:

- 사용자별로 멀티턴·전 섹션에서 바이트 단위 동일해야 한다(가변 값 금지).
- 전체 사전 투입 금지(절대 원칙 2) — 일주 엔트리 + 원국 활성 십성·관계·운성 발췌만.
- 신살·암합은 보조 자료 — 목록만 제공하고 단독 결론 금지(2026-06-12 사용자 확정).
- 판정은 엔진 계산값(Pillar/StructureAnalysis)만 사용 — 본 모듈은 텍스트 결합만 한다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# TODO(Phase 5a): operational 라벨 class·밴드 mapper를 manse_analysis 에서 직접 import.
#   순환참조 없음(manse_analysis 는 saju_engines 미참조), config 상수만 사용.
#   shadow scoring/API 공용화 전 shared_types(또는 shared_config)로 이전할 것.
import saju_manse_analysis.yongsin.operational_role_config as _op_config
from saju_manse_analysis.yongsin.operational_role_config import (
    LUCK_OPERATIONAL_GUARD,
    OPERABILITY_FACTOR_SHORT,
    OPERABILITY_LEVEL_BANDS,
    OPERATIONAL_ROLE_CLASS,
)

from saju_shared_types.constants import (
    BRANCH_ELEMENT,
    STEM_ELEMENT,
    main_hidden_stem,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.llm_input import (
    ChartInterpretation,
    InterpretationExcerpt,
    PillarDetail,
    YongsinOperationalSummary,
)
from saju_shared_types.manse_result import ManseV2Result

_DICT_DIR = Path(__file__).resolve().parents[3] / "dictionaries"
_PALACE_KO = {"year": "연주", "month": "월주", "day": "일주", "hour": "시주"}
# 궁성 자리역할(항목 14) — 천간/지지 가족 궁. 자녀 유무·성별은 통설 기준 일반 배치.
_PALACE_ROLE = {
    "year": "천간 조부 · 지지 조모(뿌리·조상궁)",
    "month": "천간 부친 · 지지 모친(부모·사회궁)",
    "day": "천간 자신 · 지지 배우자(나·배우자궁)",
    "hour": "천간 아들 · 지지 딸(자녀·결과궁)",
}
# 원국 관계 중 명식 구조에 표기할 가시 관계 — 지장간 암합류는 보조라 제외(다이어그램 정책 동일).
_HIDDEN_RELATION_PREFIX = "hidden_"
# relations.json에 participants가 없는 패턴형 관계의 표시명.
_PATTERN_RELATION_KO = {
    "gan_yeo_ji_dong": "간여지동", "ganyeojidong": "간여지동",
    "byeongjon": "병존", "bokeum": "복음",
}
_MAX_RELATION_LINES = 8  # 원국 관계 표기 상한(고정 prefix 토큰 절제)
_MAX_RELATION_EXCERPTS = 4
_PATTERN_RELATION_TEXT_ID = {
    "gan_yeo_ji_dong": "rel_간여지동", "ganyeojidong": "rel_간여지동",
    "byeongjon": "rel_병존", "bokeum": "rel_복음",
}


def _load(name: str) -> dict:
    return json.loads((_DICT_DIR / "interpretations" / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _ilju_by_ganji() -> dict[str, dict]:
    return {item["ganji"]: item for item in _load("ilju.json")["items"]}


@lru_cache(maxsize=1)
def _ten_god_by_name() -> dict[str, dict]:
    return {item["tenGod"]: item for item in _load("ten_gods_text.json")["items"]}


@lru_cache(maxsize=1)
def _stage_by_name() -> dict[str, dict]:
    return {item["stage"]: item for item in _load("twelve_stages_text.json")["items"]}


@lru_cache(maxsize=1)
def _relation_text_by_id() -> dict[str, dict]:
    return {item["id"]: item for item in _load("relations_text.json")["items"]}


@lru_cache(maxsize=1)
def _sinsal_text_by_name() -> dict[str, dict]:
    return {item["name"]: item for item in _load("sinsal_text.json")["items"]}


@lru_cache(maxsize=1)
def _favorability_by_role() -> dict[str, dict]:
    return {item["role"]: item for item in _load("favorability_text.json")["items"]}


@lru_cache(maxsize=1)
def _relation_items_by_members() -> dict[frozenset[str], list[dict]]:
    """relations.json participants → 항목 역색인(이름·id 매칭용)."""
    data = json.loads((_DICT_DIR / "relations.json").read_text(encoding="utf-8"))
    index: dict[frozenset[str], list[dict]] = {}
    for item in data["items"]:
        if item.get("participants"):
            index.setdefault(frozenset(item["participants"]), []).append(item)
    return index


# relations_text.json id의 관계명 한자(간지 글자가 아님) — 역색인 키에서 제외.
_REL_NAME_CHARS = set("合沖冲破害刑怨嗔會会方三自六")


@lru_cache(maxsize=1)
def _luck_rel_text_index() -> dict[frozenset[str], list[dict]]:
    """relations_text.json을 '간지 글자 집합 → 항목'으로 역색인(운 형충회합 fromLuck 조회).

    일운의 relations_to_chart('육합:巳-申' 등)는 글자쌍으로 들어오므로, 항목 id에서
    관계명 한자(合·沖·破 등)를 뺀 간지 글자 집합으로 매칭해 fromLuck(운 성립 시
    의미)을 가져온다.
    """
    index: dict[frozenset[str], list[dict]] = {}
    for item in _load("relations_text.json")["items"]:
        chars = frozenset(
            c for c in item["id"]
            if "一" <= c <= "鿿" and c not in _REL_NAME_CHARS
        )
        if chars:
            index.setdefault(chars, []).append(item)
    return index


# 운 신살이 들어온 레벨 → 시기·작용력 라벨(운 위계 — 대운>세운>월>일).
_LUCK_LEVEL_KO = {
    "daewoon": "대운(10년·장기 배경)",
    "year": "세운(올해)",
    "month": "월운(이 달)",
    "day": "일운(이 날)",
}
# 일운 relations_to_chart 접두(한글) → relations_text.json type 후보.
_LUCK_REL_TYPE: dict[str, tuple[str, ...]] = {
    "육합": ("six_combination",),
    "삼합": ("three_harmony",),
    "방합": ("directional",),
    "충": ("branch_clash", "stem_clash"),
    "파": ("branch_break",),
    "해": ("harm",),
    "원진": ("wonjin",),
    "형": ("punishment_triple", "punishment_mutual", "self_punishment"),
    "자형": ("self_punishment",),
    "합": ("stem_combination", "six_combination"),
}


def build_luck_grounding(
    result: ManseV2Result, luck_pillar: object, domain_key: str | None = None
) -> dict:
    """기간 운(일운/월운/세운) grounding — 그 간지의 십성·십이운성·형충회합(운 의미)·신살·공망.

    기간 총운의 사실 근거(LLM은 간지를 계산할 수 없으므로 반드시 동반). 운에서
    들어온 간지가 원국과 맺는 관계를 의미와 함께 제공하되, 인생 사건의 실행이
    아니라 그 기간의 기운·조짐으로 읽는다. 신살·암합은 보조 자료로만(단독 결론 금지).

    Args:
        result: 일간 십성·용기신 판정을 위한 만세 결과.
        luck_pillar: 해당 기간 LuckPillar(ganji·십성·운성·relations_to_chart 등).
        domain_key: 표현 제한 도메인 키(career/wealth/...). None/미매핑은 base guidance
            (Phase 5b-2b — parser Domain enum 비종속·str만 받음). 후보 경로는 미전달.

    Returns:
        pillar_line / relation_lines / sinsal_lines / gongmang 키를 가진 dict.
    """
    from .event_scoring import favorability_map

    fav = favorability_map(result)
    day_master = result.pillars.day_master if result.pillars else ""
    ganji = getattr(luck_pillar, "ganji", "")
    note = incoming_ten_god_note(day_master, ganji, fav, natal_operational_role_map(result))
    stage_name = getattr(luck_pillar, "twelve_unseong", "")
    stage = _stage_by_name().get(stage_name)
    stage_txt = _first_sentence(stage["natal"], 110) if stage else ""
    pillar_line = (
        f"{note} · 십이운성 {stage_name}"
        + (f"({stage_txt})" if stage_txt else "")
        + f" · {getattr(luck_pillar, 'yongsin_alignment', '')}"
    )

    rel_index = _luck_rel_text_index()
    rel_lines: list[str] = []
    seen: set[str] = set()
    for raw in getattr(luck_pillar, "relations_to_chart", []) or []:
        if ":" not in raw or raw in seen:
            continue
        seen.add(raw)
        prefix, rest = raw.split(":", 1)
        if prefix.endswith("기여"):  # 삼합/방합 부분 가세(미약) — 글자쌍이 아니라 오행
            rel_lines.append(f"{prefix}: {rest} 기운에 부분 가세(미약)")
        else:
            members = frozenset(m for m in rest.replace("·", "-").split("-") if m)
            item = next(
                (it for it in rel_index.get(members, [])
                 if it["type"] in _LUCK_REL_TYPE.get(prefix, ())),
                None,
            )
            if item is not None:
                rel_lines.append(
                    f"{item['name']}({rest}): {_first_sentence(item['fromLuck'], 150)}"
                )
            else:
                rel_lines.append(f"{prefix}: {rest}")
        if len(rel_lines) >= 5:
            break

    # 운(運) 천간이 원국과 맺는 천간합의 작용 모드(합화/합반/합거)+신뢰도 — 엔진 판정.
    from .hap_lines import luck_hap_mode_lines  # 지역 import — 순환 의존 회피
    luck_stem = ganji[0] if len(ganji) >= 1 else ""
    luck_branch = ganji[1] if len(ganji) >= 2 else ""
    rel_lines.extend(luck_hap_mode_lines(
        result,
        [luck_stem] if luck_stem else None,
        [luck_branch] if luck_branch else None,
    ))

    # 운 신살은 들어온 운 레벨이 곧 시기·작용력 — 대운=장기 배경, 세운=올해, 월/일=단기.
    level_ko = _LUCK_LEVEL_KO.get(getattr(luck_pillar, "period_type", ""), "운")
    sinsal_lines: list[str] = []
    texts = _sinsal_text_by_name()
    for s in (getattr(luck_pillar, "luck_sinsal", []) or [])[:3]:
        name = getattr(s, "name", None) or (s.get("name") if isinstance(s, dict) else None)
        item = texts.get(name) if name else None
        if item is None:
            continue
        # 운 신살은 '체질'이 아니라 그 시기에 터지는 '사건' — fromLuck 우선(없으면 manifestation).
        body = item.get("fromLuck") or item["manifestation"]
        sinsal_lines.append(
            f"(보조·{level_ko} 유입) {name}: {_first_sentence(body, 110)} "
            f"양면 {_first_sentence(item['flipSide'], 80)}"
        )

    # 길흉 표현 제한(Phase 5b-2a) — 점수·순위 불변, 문장 강도만 clamp(단일 기간 블록만).
    # rollback: EXPRESSION_CLAMP_ENABLED=False 면 라인 미노출(즉시 off — 계산·shadow 무관).
    # 5b-2b: domain_key 있으면 등급을 도메인 언어로 번역(미상/미매핑은 base guidance).
    from .shadow_scoring import (  # 지역 import — 순환 의존 회피
        domain_expression_phrase,
        luck_expression_clamp,
    )
    clamp = (
        luck_expression_clamp(result, ganji)
        if _op_config.EXPRESSION_CLAMP_ENABLED else None
    )
    if clamp is not None:
        phrase = domain_expression_phrase(
            domain_key, clamp["expression_class"], clamp["guidance"]
        )
        limit = f"[표현 제한] {clamp['expression_class']} — {phrase}"
        if clamp["low_operability"] is not None:
            limit += f"; 용신운이나 작동성 낮아({clamp['low_operability']}) 강한 길운 단정 금지"
        pillar_line += f" · {limit}(점수·순위 불변)"

    gongmang = list(getattr(luck_pillar, "gongmang_activation", []) or [])
    return {
        "pillar_line": pillar_line,
        "relation_lines": rel_lines,
        "sinsal_lines": sinsal_lines,
        "gongmang": gongmang,
    }


def _first_sentence(text: str, limit: int = 160) -> str:
    """해석 텍스트의 첫 문장(토큰 절제) — '다.' 기준, 상한 길이 보호."""
    idx = text.find("다.")
    snippet = text[: idx + 2] if idx != -1 else text
    return snippet[:limit].strip()


def _match_relation_item(relation_type: str, members: list[str]) -> dict | None:
    """원국 상호작용 → relations.json 항목 매칭(동일 글자쌍의 합/파 동명이인은 type으로 변별)."""
    candidates = _relation_items_by_members().get(frozenset(members), [])
    if not candidates:
        return None
    for item in candidates:
        if item["type"] == relation_type:
            return item
    return candidates[0] if len(candidates) == 1 else None


def _serialize_ilju(entry: dict) -> str:
    """일주 엔트리 → 프롬프트 텍스트(basis는 내부 근거라 제외)."""
    animal = f"{entry['animal']['color']} {entry['animal']['name']}"
    traits = entry["traits"]
    return "\n".join([
        f"일주 {entry['ganji']} ({animal}) — {entry['imagery']}",
        entry["narrative"],
        "밝은 면: " + " / ".join(traits["light"]),
        "그림자: " + " / ".join(traits["shadow"]),
        f"배우자궁: {entry['spouse_palace_note']}",
    ])


# 작동 역할 요약 token 절제(Phase 5a). warnings 최대 개수 + 누적 char 예산(토큰 proxy):
# 우선순위 순으로 예산 내까지만 채택(초과 시 하위 warning부터 드롭).
_MAX_WARNINGS = 3
_WARNINGS_CHAR_BUDGET = 120


def _trim_warnings(warnings: list[str]) -> list[str]:
    """우선순위 보존하며 개수·char 예산 내로 자른다(초과 시 하위 warning 드롭)."""
    out: list[str] = []
    used = 0
    for w in warnings[:_MAX_WARNINGS]:
        if used + len(w) > _WARNINGS_CHAR_BUDGET:
            break
        out.append(w)
        used += len(w)
    return out


def _operability_level(operability: float | None) -> str:
    """operability 수치 → 표시용 밴드(높음/보통/낮음). None 이면 빈 문자열."""
    if operability is None:
        return ""
    if operability < OPERABILITY_LEVEL_BANDS["low"]:
        return "낮음"
    if operability < OPERABILITY_LEVEL_BANDS["mid"]:
        return "보통"
    return "높음"


def build_yongsin_operational_summary(
    result: ManseV2Result,
) -> YongsinOperationalSummary | None:
    """원국 기준 작동 역할 compact 요약(Phase 5a). 구형/부분 결과면 None(안전 fallback).

    operational_role 해석은 OPERATIONAL_ROLE_CLASS mapper 만 사용(문자열 substring 파싱 금지).
    warnings 는 deterministic 우선순위로 ≤3: ①조건부 희신/병 ②용신 operability 저하 ③조후/합/혼잡.
    점수·이벤트 판정 불변 — 이 요약은 작동성·조건부 해석 참고 자료일 뿐이다.
    """
    ya = result.yongsin_analysis
    if ya is None or not ya.operational_roles:
        return None
    primary = ya.final.get("yongsin") or ""
    yong_role = next((r for r in ya.operational_roles if r.element == primary), None)
    operability = yong_role.operability if yong_role else None

    main_support = [
        f"{r.element}: {r.operational_role}"
        for r in ya.operational_roles if r.operational_role == "조후보조신"
    ]
    conditional = [
        f"{r.element}: {r.operational_role}"
        for r in ya.operational_roles
        if OPERATIONAL_ROLE_CLASS.get(r.operational_role) == "conditional"
    ]

    # warnings — deterministic 우선순위(①조건부 희신/병 ②용신 작동성 ③구조), 간결 명령형.
    # 상세 수치·factor 는 위 블록 라인에 이미 있으므로 warning 은 imperative 만(토큰 절약).
    level = _operability_level(operability)
    warnings: list[str] = []
    cond_byung = [
        r.element for r in ya.operational_roles
        if r.operational_role == "조건부 희신/병"
    ]
    if cond_byung:
        warnings.append(f"{'·'.join(cond_byung)}: 자동 길신 처리 금지(정적 희신이나 과다·병)")
    if level == "낮음":
        warnings.append(f"{primary}: 용신이나 작동성 약함")
    has_structure = any(
        r.note and ("officer_hap" in r.note or "관살혼잡" in r.note)
        for r in ya.operational_roles
    ) or bool(main_support)
    if has_structure:
        warnings.append("관살혼잡·합·조후 맥락 — 작용 단순치 않음")

    factors = list(yong_role.operability_factors) if yong_role else []
    return YongsinOperationalSummary(
        primary_yongsin=primary,
        operability=operability,
        operability_level=level,
        operability_factors=factors,
        operability_factors_ko=[OPERABILITY_FACTOR_SHORT.get(f, f) for f in factors],
        main_support=main_support,
        conditional=conditional,
        warnings=_trim_warnings(warnings),
    )


def build_chart_interpretation(result: ManseV2Result) -> ChartInterpretation | None:
    """ManseV2Result → ⑤ 명식 구조+해석 자료(고정 prefix 콘텐츠).

    Args:
        result: 만세력 계산 결과(원국·구조분석·신살 포함).

    Returns:
        ChartInterpretation — pillars가 없으면 None.
    """
    if result.pillars is None:
        return None
    from .hap_lines import natal_hap_mode_lines  # 지역 import — 순환 의존 회피
    pillars = result.pillars
    by_pillar_sinsal: dict[str, list[str]] = {}
    if result.traditional_extras is not None and result.traditional_extras.sinsal is not None:
        by_pillar_sinsal = result.traditional_extras.sinsal.by_pillar

    details: list[PillarDetail] = []
    ten_god_names: list[str] = []
    for palace in ("year", "month", "day", "hour"):
        pillar = getattr(pillars, palace)
        if pillar is None:
            continue
        details.append(PillarDetail(
            palace=palace,
            palace_ko=_PALACE_KO[palace],
            ganji=pillar.ganji,
            stem_ten_god=pillar.stem_ten_god,
            branch_ten_god=pillar.branch_main_ten_god,
            twelve_stage=pillar.twelve_unseong,
            sinsal=by_pillar_sinsal.get(palace, []),
            palace_role=_PALACE_ROLE.get(palace, ""),
        ))
        for name in (pillar.stem_ten_god, pillar.branch_main_ten_god):
            if name and name != "일간" and name not in ten_god_names:
                ten_god_names.append(name)

    natal_relations, relation_ids = _natal_relations(result)
    excerpts = _build_excerpts(pillars.day, ten_god_names, relation_ids)
    excerpts += _sinsal_excerpts(result)
    excerpts += _favorability_excerpts(result)
    ilju_entry = _ilju_by_ganji().get(pillars.day.ganji)
    return ChartInterpretation(
        pillar_details=details,
        natal_relations=natal_relations,
        hap_modes=natal_hap_mode_lines(result),
        ilju_text=_serialize_ilju(ilju_entry) if ilju_entry else "",
        excerpts=excerpts,
        yongsin_operational_summary=build_yongsin_operational_summary(result),
    )


_MAX_AMHAP_LINES = 3  # 원국 암합 보조 표기 상한(항목 9)


def _natal_relations(result: ManseV2Result) -> tuple[list[str], list[str]]:
    """원국 내 가시 관계 + 병존/간여지동/복음 + 암합(보조) → (표시 줄, 해석 사전 id)."""
    lines: list[str] = []
    amhap: list[str] = []  # 암합류 — 보조 라벨로 분리 수집(항목 9)
    ids: list[str] = []
    if result.structure_analysis is None:
        return lines, ids
    sa = result.structure_analysis
    for inter in [*sa.interactions, *sa.amplifiers]:
        if inter.relation_type.startswith(_HIDDEN_RELATION_PREFIX):
            # 암합(천간-지장간/지장간-지장간) — 보조 자료로만, 단독 결론 금지.
            if len(amhap) < _MAX_AMHAP_LINES:
                members = "·".join(inter.members)
                palaces = "·".join(dict.fromkeys(inter.palaces)) if inter.palaces else ""
                amhap.append(f"{members}" + (f" ({palaces})" if palaces else ""))
            continue
        item = _match_relation_item(inter.relation_type, inter.members)
        label = (
            item["name"] if item
            else _PATTERN_RELATION_KO.get(inter.relation_type, inter.relation_type)
        )
        palaces = "·".join(dict.fromkeys(inter.palaces)) if inter.palaces else ""
        members = "·".join(inter.members)
        lines.append(f"{label}: {members}" + (f" ({palaces})" if palaces else ""))
        text_id = (
            item["id"] if item
            else _PATTERN_RELATION_TEXT_ID.get(inter.relation_type)
        )
        if text_id and text_id not in ids:
            ids.append(text_id)
        if len(lines) >= _MAX_RELATION_LINES:
            break
    if amhap:
        lines.append("암합(보조·단독 판정 금지): " + " / ".join(amhap))
    return lines, ids


def _build_excerpts(
    day_pillar, ten_god_names: list[str], relation_ids: list[str]
) -> list[InterpretationExcerpt]:
    """원국 활성 십성·일지 운성·원국 관계의 해석 발췌(전체 사전 투입 금지)."""
    excerpts: list[InterpretationExcerpt] = []
    ten_gods = _ten_god_by_name()
    for name in ten_god_names:
        item = ten_gods.get(name)
        if item is None:
            continue
        excerpts.append(InterpretationExcerpt(
            kind="ten_god", key=name,
            text=f"{item['core']} 원국: {_first_sentence(item['natal'], 200)}",
        ))
    stage_item = _stage_by_name().get(day_pillar.twelve_unseong)
    if stage_item is not None:
        excerpts.append(InterpretationExcerpt(
            kind="twelve_stage", key=day_pillar.twelve_unseong,
            text=f"{stage_item['core']} {_first_sentence(stage_item['natal'], 200)}",
        ))
    relation_texts = _relation_text_by_id()
    for rel_id in relation_ids[:_MAX_RELATION_EXCERPTS]:
        item = relation_texts.get(rel_id)
        if item is None:
            continue
        excerpts.append(InterpretationExcerpt(
            kind="relation", key=item["name"],
            text=_first_sentence(item["natal"], 200),
        ))
    return excerpts


_MAX_SINSAL_EXCERPTS = 5
# 궁성론(2026-06-12 사용자 확정) — 같은 신살도 자리에 따라 시기·대상·작용이 갈린다.
_SINSAL_PALACE_LABEL = {
    "year": "년주(조상·고향·초년)",
    "month": "월주(부모·직장·사회·청년 — 작용력 최대)",
    "day": "일주(나·배우자·장년)",
    "hour": "시주(자녀·내면·말년)",
}
_SOCIAL_PALACES = {"year", "month"}  # 年月 = 사회·대외 발현
_PERSONAL_PALACES = {"day", "hour"}  # 日時 = 개인·가정 발현


def _sinsal_positions(analysis: object) -> dict[str, list[str]]:
    """신살 이름 → 위치 목록(year/month/day/hour) 역색인 — 위치별 해석용."""
    out: dict[str, list[str]] = {}
    by_pillar = getattr(analysis, "by_pillar", {}) or {}
    for palace in ("year", "month", "day", "hour"):
        for name in by_pillar.get(palace, []):
            out.setdefault(name, []).append(palace)
    return out


def _sinsal_excerpts(result: ManseV2Result) -> list[InterpretationExcerpt]:
    """주요 신살의 해석 발췌 — 보조 자료 표기 의무(단독 결론 금지).

    summary의 주요 길신/주의 신살을 우선하고, 없으면 일주 신살로 보충한다. 각 신살은
    원국 위치(궁성)를 표기하고, 자리에 따른 발현 차이(年月=사회 / 日時=개인)를 함께
    제공한다 — 같은 신살도 시기·대상·작용이 달라지기 때문(궁성론).
    """
    if result.traditional_extras is None or result.traditional_extras.sinsal is None:
        return []
    analysis = result.traditional_extras.sinsal
    positions = _sinsal_positions(analysis)
    names: list[str] = []
    for name in [
        *analysis.summary.major_positive,
        *analysis.summary.major_caution,
        *analysis.by_pillar.get("day", []),
    ]:
        if name not in names:
            names.append(name)
    texts = _sinsal_text_by_name()
    excerpts: list[InterpretationExcerpt] = []
    for name in names:
        item = texts.get(name)
        if item is None:
            continue
        pos = positions.get(name, [])
        palace_note = (
            " [위치: " + ", ".join(_SINSAL_PALACE_LABEL[p] for p in pos) + "]"
            if pos else ""
        )
        # 위치별 발현(궁성론) — 자리에 사회궁(年月)/개인궁(日時)이 걸린 쪽만 덧붙인다.
        bypos = item.get("byPosition")
        pos_texts: list[str] = []
        if bypos and pos:
            if any(p in _SOCIAL_PALACES for p in pos):
                pos_texts.append(bypos["social"])
            if any(p in _PERSONAL_PALACES for p in pos):
                pos_texts.append(bypos["personal"])
        bypos_note = (" 위치별: " + " / ".join(pos_texts)) if pos_texts else ""
        # 양면 해석 동반(2026-06-12 사용자 확정) — 길신의 그림자·흉성의 빛을 함께.
        excerpts.append(InterpretationExcerpt(
            kind="sinsal", key=name,
            text=(
                f"(보조 — 단독 판정 금지){palace_note} {item['meaning']} "
                f"{_first_sentence(item['manifestation'])} "
                f"양면: {_first_sentence(item['flipSide'], 200)}{bypos_note}"
            ),
        ))
        if len(excerpts) >= _MAX_SINSAL_EXCERPTS:
            break
    return excerpts


def _favorability_excerpts(result: ManseV2Result) -> list[InterpretationExcerpt]:
    """구신·기신의 반전 해석 발췌 — 길흉 고정 금지, 조건부로 돕는 경우 포함(항목: 구신 반전).

    구신/기신은 흉신이지만 태과 제어·탐합망극·통관·제화로 사주를 돕는 반전이 있어,
    이 반전 조건을 LLM에 제공해 '무조건 나쁘다'는 단정을 막는다.
    """
    from .event_scoring import favorability_map

    fav = favorability_map(result)  # {오행 한자: 역할}
    texts = _favorability_by_role()
    excerpts: list[InterpretationExcerpt] = []
    for element, role in fav.items():
        if role not in ("구신", "기신"):
            continue
        item = texts.get(role)
        if item is None:
            continue
        excerpts.append(InterpretationExcerpt(
            kind="favorability", key=f"{element} {role}",
            text=f"{item['core']} 반전: {_first_sentence(item['reversal'], 260)}",
        ))
    return excerpts


def natal_operational_role_map(result: ManseV2Result) -> dict[str, str]:
    """원국(natal) 기준 {오행: operational_role}. operational_roles 없으면 빈 dict(구형 fallback).

    운 입자 해석 guard 용 — 운에서 들어온 오행이 원국에서 어떤 작동 역할인지(조건부 희신/병 등).
    """
    ya = result.yongsin_analysis
    if ya is None or not getattr(ya, "operational_roles", None):
        return {}
    return {r.element: r.operational_role for r in ya.operational_roles}


def _operational_tag(element: str, canonical_role: str | None, oper_role: str | None) -> str:
    """운 입자 오행 인라인 태그 — operational 이 guard 대상이면 '원국 작동' 표기(Phase 5b-1)."""
    base = f"{element} {canonical_role}" if canonical_role else element
    if oper_role and oper_role in LUCK_OPERATIONAL_GUARD:
        return f"({base} → 원국 작동: {oper_role})"
    return f"({base})"


def _operational_guard_suffix(elements: list[str], operational_map: dict[str, str]) -> str:
    """운 입자 오행별 guard suffix(오행별 1회 dedupe). 라벨별 문구는 config."""
    lines: list[str] = []
    seen: set[str] = set()
    for el in elements:
        role = operational_map.get(el)
        if role in LUCK_OPERATIONAL_GUARD and el not in seen:
            seen.add(el)
            lines.append(f"※ 운 {el}: {LUCK_OPERATIONAL_GUARD[role]}")
    return " ".join(lines)


def incoming_ten_god_note(
    day_master: str,
    ganji: str,
    fav_map: dict[str, str],
    operational_map: dict[str, str] | None = None,
) -> str:
    """운 유입 간지의 일간 기준 십성 해석 1줄(동적 suffix — 후보별 동반).

    천간·지지 십성을 함께 표기한다 — 단일 천간 십성만 보고 사건을 단정하는
    오류 방지(regression_2025_08: 甲申월 = 정관(甲)+상관(申) 복합). operational_map(원국 기준)이
    주어지면 운 오행의 원국 작동 역할(조건부 희신/병 등)을 함께 표기 + guard suffix(Phase 5b-1).
    operational_map=None/빈 dict 이면 기존 canonical 동작과 완전히 동일하다(explanation only).
    """
    if not day_master or len(ganji) < 2:
        return ""
    try:
        dm = Stem(day_master)
        stem = Stem(ganji[0])
        branch = Branch(ganji[1])
    except ValueError:
        return ""
    op = operational_map or {}
    stem_tg = str(ten_god(dm, stem))
    branch_tg = str(ten_god(dm, Stem(main_hidden_stem(branch).value)))
    # 운 천간/지지 오행의 용기신 역할도 명시 — '계수=구신' 같은 길흉을 LLM이 인지하게.
    stem_el = str(STEM_ELEMENT[stem])
    branch_el = str(BRANCH_ELEMENT[branch])
    stem_tag = _operational_tag(stem_el, fav_map.get(stem_el), op.get(stem_el))
    branch_tag = _operational_tag(branch_el, fav_map.get(branch_el), op.get(branch_el))
    head = (
        f"{ganji} 유입 = 천간 {ganji[0]} {stem_tg}{stem_tag} · "
        f"지지 {ganji[1]} {branch_tg}{branch_tag}"
    )
    item = _ten_god_by_name().get(stem_tg)
    if item is None:
        body = head
    else:
        parts = [head, "—", _first_sentence(item["incoming"])]
        fav = fav_map.get(stem_el)
        if fav == "용신":
            parts.append(_first_sentence(item["asYongsin"]))
        elif fav == "기신":
            parts.append(_first_sentence(item["asGisin"]))
        body = " ".join(parts)
    guard = _operational_guard_suffix([stem_el, branch_el], op)
    return f"{body} {guard}".strip() if guard else body
