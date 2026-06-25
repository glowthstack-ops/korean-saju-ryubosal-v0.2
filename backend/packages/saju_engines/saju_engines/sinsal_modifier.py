"""신살 보정 derive 엔진 — 원천 SinsalItem → SinsalModifier(파생 해석).

SINSAL_MODIFIER_SPEC §3·§4·§7·§8. 순수 함수: (chart, domain, ...) → list[SinsalModifier].
원천 신살(SinsalItem)·event_score 를 바꾸지 않는다(Phase A enrichment 전용). 위치(궁성)·도메인
정렬·생애단계(대운 우선)·운 재활성화를 합성해 한글 강도어/효과 태그까지 산출한다.

신살은 보조 레이어 — 단독 사건 생성 금지. 길성=완충·도움 / 흉살=리스크·주의 / 중립=변동.
"""

from __future__ import annotations

from datetime import date

from saju_manse_analysis.sinsal.sinsal_catalog import CATALOG_META

from saju_shared_types.luck import DaewoonItem, LuckPillar
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.sinsal import LlmSinsalModifier, SinsalModifier

from . import sinsal_modifier_config as cfg

_PILLARS = ("year", "month", "day", "hour")


def _polarity_of(name: str) -> str:
    """catalog 의 길흉 성향(positive/caution/neutral). 미등록은 neutral."""
    meta = CATALOG_META.get(name)
    return str(meta.get("polarity", "neutral")) if meta else "neutral"


def _birth_year(chart: ManseV2Result) -> int | None:
    raw = (chart.input_summary or {}).get("birth_date", "")
    return int(raw[:4]) if isinstance(raw, str) and raw[:4].isdigit() else None


def _life_stage(chart: ManseV2Result, reference_date: date | None) -> str:
    """생애단계 — 대운 우선(chart current_age) → 나이 fallback → 시점미상 'middle'(§8)."""
    age: int | None = None
    lc = chart.luck_cycles
    if lc is not None and lc.current_age is not None:  # 1순위: 대운 배치 기반 현재 나이
        age = lc.current_age
    elif reference_date is not None:  # 2순위: 질문 시점 나이
        by = _birth_year(chart)
        if by is not None:
            age = reference_date.year - by
    if age is None:  # 3순위: 시점 미상
        return "middle"
    for stage, lo, hi in cfg.LIFE_STAGE_AGE_BANDS:
        if lo <= age <= hi:
            return stage
    return "late"


def _current_luck(chart: ManseV2Result) -> tuple[DaewoonItem | None, LuckPillar | None]:
    """현재 대운 item · 현재 세운 pillar(없으면 None) — 재활성화 판정 공용."""
    lc = chart.luck_cycles
    if lc is None:
        return None, None
    daewoon = None
    idx = lc.current_daewoon_index
    if idx is not None and 0 <= idx < len(lc.daewoon_table):
        daewoon = lc.daewoon_table[idx]
    sewoon = None
    if lc.current_year is not None:
        sewoon = next((p for p in lc.yearly_luck if p.label == str(lc.current_year)), None)
    return daewoon, sewoon


def _luck_touch_chars(chart: ManseV2Result) -> tuple[set[str], set[str]]:
    """현재 대운+세운이 합·충·형·해로 건드린 '원국 글자' 집합(지지, 천간).

    relations_to_chart 포맷 '<유형>:<운글자>-<원국글자>' 에서 원국 글자(뒤쪽)를 추출한다.
    원소만 있는 삼합/방합완성(예 '삼합완성:火')은 자리 특정 불가 → 제외(정밀도 우선).
    """
    branches: set[str] = set()
    stems: set[str] = set()
    daewoon, sewoon = _current_luck(chart)
    rel_sources: list[list[str]] = [
        luck.relations_to_chart for luck in (daewoon, sewoon) if luck is not None
    ]
    for rels in rel_sources:
        for r in rels:
            if ":" not in r:
                continue
            kind, _, body = r.partition(":")
            if kind not in cfg.REACTIVATION_RELATION_PREFIXES:
                continue
            if "-" not in body:
                continue  # 원소만(삼합완성:火) → 스킵
            natal_char = body.split("-", 1)[1]
            if kind == "천간합":
                stems.add(natal_char)
            else:
                branches.add(natal_char)
    return branches, stems


def _is_reactivated(
    chart: ManseV2Result, position: str, name: str,
    touched_branches: set[str], touched_stems: set[str],
) -> bool:
    """그 주(position)가 운에 의해 재활성화됐는가(§8-3) — 합충/복음/동일 신살 재출현."""
    pillars = chart.pillars
    if pillars is None:
        return False
    pillar = getattr(pillars, position, None)
    if pillar is None:
        return False
    if pillar.branch in touched_branches or pillar.stem in touched_stems:
        return True
    # 동일 신살이 현재 운 신살로 재출현 → 재활성화.
    daewoon, sewoon = _current_luck(chart)
    luck_names: set[str] = set()
    for luck in (daewoon, sewoon):
        if luck is not None:
            luck_names |= {s.name for s in luck.luck_sinsal}
    return name in luck_names


def _domain_pillar_weight(domain: str, position: str) -> float:
    override = cfg.DOMAIN_OVERRIDE.get(domain)
    if override is not None:
        return override.get(position, cfg.PILLAR_DEFAULT_WEIGHT[position])
    return cfg.PILLAR_DEFAULT_WEIGHT[position]


def _domain_match(domain: str, position: str, question_keywords: list[str] | None) -> bool:
    """질문 intent ∩ 궁성 정렬(§7). enum 도메인=가중 임계, GENERAL=키워드 보조 매칭."""
    if domain in cfg.DOMAIN_OVERRIDE:
        return _domain_pillar_weight(domain, position) >= cfg.DOMAIN_MATCH_THRESHOLD
    # GENERAL 등: palace_tags/scope 와 질문 키워드의 정렬.
    if not question_keywords:
        return False
    pool = set(cfg.PILLAR_PALACE_TAGS[position]) | set(cfg.PILLAR_SCOPE[position])
    return any(kw in tag or tag in kw for kw in question_keywords for tag in pool)


def _activation_status(mode: str, reactivated: bool, domain_match: bool) -> str:
    if reactivated:
        return "strongly_activated" if domain_match else "activated"
    if mode == "direct":
        return "activated"
    if mode == "seed":
        return "latent"
    return "background"  # emerging | background | accumulated


def _effect_tags(name: str, polarity: str) -> list[str]:
    tags = cfg.EFFECT_TAGS.get(name)
    if tags:
        return list(tags)
    return [cfg.POLARITY_DEFAULT_EFFECT.get(polarity, "변동·특수성")]


def derive_natal_sinsal_modifiers(
    chart: ManseV2Result,
    domain: str = "general",
    *,
    reference_date: date | None = None,
    question_keywords: list[str] | None = None,
) -> list[SinsalModifier]:
    """원국 신살 → SinsalModifier 목록(파생 해석). 신살 없으면 빈 리스트(규칙 11 무해).

    Args:
        chart: 만세 계산 결과(traditional_extras.sinsal 사용).
        domain: 질문 도메인(Domain enum 값 문자열; 'general' 기본).
        reference_date: 생애단계 나이 fallback 기준(대운 정보 없을 때).
        question_keywords: GENERAL 도메인 보조 매칭용 질문 키워드.

    Returns:
        SinsalModifier 리스트(원천 SinsalItem 순서). internal_* 는 LLM 미노출.
    """
    extras = chart.traditional_extras
    if extras is None or extras.sinsal is None:
        return []
    stage = _life_stage(chart, reference_date)
    touched_branches, touched_stems = _luck_touch_chars(chart)
    out: list[SinsalModifier] = []
    for item in extras.sinsal.full_list:
        position = item.position
        if position not in _PILLARS:
            continue
        polarity = _polarity_of(item.name)
        mode, stage_weight = cfg.LIFE_STAGE_CURVE[position][stage]
        reactivated = _is_reactivated(
            chart, position, item.name, touched_branches, touched_stems,
        )
        domain_match = _domain_match(domain, position, question_keywords)
        base = _domain_pillar_weight(domain, position)
        weight = base * stage_weight + (cfg.REACTIVATION_WEIGHT_BOOST if reactivated else 0.0)
        weight = round(min(weight, 1.2), 3)
        factors = [
            f"pos:{position}", f"domain:{domain}:{base}",
            f"stage:{stage}:{mode}:{stage_weight}",
        ]
        if reactivated:
            factors.append("reactivated:+0.25")
        out.append(SinsalModifier(
            name=item.name,
            polarity=polarity,
            position=position,
            source="natal",
            scope=list(cfg.PILLAR_SCOPE[position]),
            palace_tags=list(cfg.PILLAR_PALACE_TAGS[position]),
            domain_match=domain_match,
            activation_status=_activation_status(mode, reactivated, domain_match),
            life_stage=stage,
            life_stage_mode=mode,
            effect_tags=_effect_tags(item.name, polarity),
            llm_strength=cfg.strength_band(weight),
            internal_weight=weight,
            internal_factors=factors,
        ))
    return out


def _payload_tier(m: SinsalModifier) -> int:
    """payload 우선순위 tier(작을수록 우선) — 가드 §우선순위."""
    background = m.activation_status in ("background", "latent")
    if m.domain_match and m.activation_status == "strongly_activated":
        return 1
    if m.domain_match and m.activation_status == "activated":
        return 2
    if m.domain_match and background:
        return 3
    if (not m.domain_match) and m.activation_status == "strongly_activated":
        return 4
    return 5  # domain_match=False 배경/잠재(년주 배경 길성·흉살 등)


def select_llm_sinsal_modifiers(
    modifiers: list[SinsalModifier],
    max_per_event: int = cfg.SINSAL_PAYLOAD_MAX_PER_EVENT,
) -> list[LlmSinsalModifier]:
    """후보 payload 노출용 pruning(가드) — 우선순위·개수 상한 적용 → LLM subset 반환.

    우선순위: domain_match+strongly > +activated > +background > (불일치)+strongly.
    상한: 총 max_per_event(기본 3); domain_match=False 최대 1; 년주 background 최대 1.
    domain_match=False 배경(tier5)은 년주 background 길성/흉살만 허용한다.
    """
    ranked = sorted(modifiers, key=lambda m: (_payload_tier(m), -m.internal_weight, m.name))
    out: list[LlmSinsalModifier] = []
    dm_false = 0
    year_bg = 0
    for m in ranked:
        if len(out) >= max_per_event:
            break
        tier = _payload_tier(m)
        if tier == 5:
            # domain_match=False 배경은 년주 background 길성/흉살만(§가드).
            is_year_bg = m.position == "year" and m.activation_status in ("background", "latent")
            if not is_year_bg or year_bg >= cfg.SINSAL_PAYLOAD_MAX_YEAR_BACKGROUND:
                continue
        if not m.domain_match:
            if dm_false >= cfg.SINSAL_PAYLOAD_MAX_DOMAIN_UNMATCHED:
                continue
            dm_false += 1
            if tier == 5:
                year_bg += 1
        out.append(m.to_llm())
    return out
