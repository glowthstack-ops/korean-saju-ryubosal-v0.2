"""직업 분야(십성 기능) 근거 엔진 — '어떤 분야/직종이 맞나·제안이 올까' 질문용 (2026-09-10).

명식의 십성 분포(effective_percent)·억부 역할(用喜忌仇閑)·격국·구조 패턴(식신생재 등)·현재
운 천간 십성을 사전(`career_fields.json`)의 직업 기능 표에 대응해 **서술 근거**를 만든다.
점수·판정을 만들지 않으며(LLM 계산 금지 원칙의 반대편 — 엔진이 사실을, LLM 이 문장을),
"십성이 있다고 적성 확정·없다고 부적합" 단정은 사전 원칙으로 금지한다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from saju_manse_analysis.distribution.ten_god_distribution import compute_ten_god_distribution

from saju_shared_types.career_fields import (
    CareerFieldDict,
    CareerFieldFacts,
    CombinationHit,
    ConditionHit,
    IncomingChannel,
    ProminentTenGod,
)
from saju_shared_types.constants import BRANCH_ELEMENT, STEM_ELEMENT
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.manse_result import ManseV2Result

from .direction_suggestion import build_direction_facts
from .event_scoring import favorability_map
from .structure_patterns import detect_structure_patterns

# ── 격국·신살 조건층(2026-10-15, 외부 교재 기타절 번역) — 보조 신호, 단독 확정 금지 ──
_HYEONCHIM = {"甲", "辛", "卯", "午", "申"}
_PUNISH_SETS = ({"寅", "巳", "申"}, {"丑", "戌", "未"})
_FIRE_TRINE = {"寅", "午", "戌"}
_STORAGE_LIFE = {"辰", "戌", "巳", "亥"}
_FAVORABLE_ROLES = {"용신", "희신"}


def _letter_element(ch: str) -> str:
    try:
        return str(STEM_ELEMENT[Stem(ch)])
    except ValueError:
        try:
            return str(BRANCH_ELEMENT[Branch(ch)])
        except ValueError:
            return ""


def _evaluate_conditions(
    result: ManseV2Result, dictionary: CareerFieldDict, group_pct: dict[str, float],
) -> list[ConditionHit]:
    """사전 `conditions` 의 signal 을 원국 사실로 판정한다(근거 문자열 동반). 점수 아님."""
    p = result.pillars
    if p is None:
        return []
    pillars = [x for x in (p.year, p.month, p.day, p.hour) if x is not None]
    stems = [x.stem for x in pillars]
    branches = [x.branch for x in pillars]
    letters = stems + branches
    day = p.day_master
    fav = favorability_map(result)
    sa = result.structure_analysis
    inters = list(sa.interactions) if sa is not None else []
    clash_members = {m for i in inters if i.relation_type == "clash" for m in i.members}
    punish_members = {m for i in inters if i.relation_type == "punishment" for m in i.members}
    trine_members = {m for i in inters if i.relation_type == "three_harmony" for m in i.members}
    strong = dictionary.thresholds.strong_pct

    def fav_of(ch: str) -> bool:
        return fav.get(_letter_element(ch)) in _FAVORABLE_ROLES

    def fav_el(el: str) -> bool:
        return fav.get(el) in _FAVORABLE_ROLES

    hits: list[ConditionHit] = []
    for rule in dictionary.conditions:
        ev = ""
        s = rule.signal
        if s == "hyeonchim_favorable":
            got = [c for c in letters if c in _HYEONCHIM]
            if len(got) >= 2 and any(fav_of(c) for c in got):
                ev = "현침 글자 " + "·".join(dict.fromkeys(got)) + " 중 희용신 오행 있음"
        elif s == "three_punishment_favorable":
            for ps in _PUNISH_SETS:
                got = sorted(punish_members & ps)
                if len(got) >= 2 and any(fav_of(c) for c in got):
                    ev = "형 " + "·".join(got) + " 의 오행이 희용신"
                    break
        elif s == "fire_day_or_yong":
            if day == "丙":
                ev = "丙 일간"
            elif fav_el("火"):
                ev = "火 희용신"
        elif s == "fire_trine_or_byeongjeong":
            if day in ("丙", "丁"):
                ev = f"{day} 일간"
            elif _FIRE_TRINE <= trine_members:
                ev = "寅午戌 화국"
            elif len([b for b in branches if b in _STORAGE_LIFE]) >= 3:
                ev = "辰戌巳亥 " + "·".join(b for b in branches if b in _STORAGE_LIFE)
        elif s == "jeong_day_or_peer_many":
            if day == "丁":
                ev = "丁 일간"
            elif group_pct.get("peer", 0.0) >= strong:
                ev = f"비겁 {group_pct.get('peer', 0.0):.0f}%"
        elif s == "metal_yong":
            if fav_el("金"):
                ev = "金 희용신"
        elif s == "earth_water_yong":
            got = [el for el in ("土", "水") if fav_el(el)]
            if got:
                ev = "·".join(got) + " 희용신"
        elif s == "military_signals":
            mil = [c for c in stems if c in ("戊", "庚", "壬")]
            punish = next((sorted(punish_members & ps) for ps in _PUNISH_SETS
                           if len(punish_members & ps) >= 2), [])
            storage = [b for b in branches if b in _STORAGE_LIFE]
            if len(mil) >= 2:
                ev = "천간 " + "·".join(mil)
            elif punish:
                ev = "형 " + "·".join(punish)
            elif len(storage) >= 3:
                ev = "辰戌巳亥 " + "·".join(storage)
        elif s == "yongsin_clashed":
            got = sorted(c for c in clash_members if fav_of(c))
            if got:
                ev = "충에 걸린 희용신 지지 " + "·".join(got)
        elif s == "wood_yong_jinsul_clash":
            if fav_el("木") and {"辰", "戌"} <= clash_members:
                ev = "木 희용신 + 辰戌 충"
        elif s == "water_yong_output":
            if fav_el("水") and group_pct.get("output", 0.0) >= strong:
                ev = f"水 희용신 + 식상 {group_pct.get('output', 0.0):.0f}%"
        if ev:
            hits.append(ConditionHit(
                id=rule.id, field=rule.field, condition=rule.condition, evidence=ev,
                jobs=list(rule.jobs),
            ))
    return hits

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
#: 로마자(TenGod enum) ↔ 한글 — direction facts 의 역할 표는 로마자 키.
ROMAN_TO_KO: dict[str, str] = {
    "BIJIAN": "비견", "JIECAI": "겁재", "SHISHEN": "식신", "SHANGGUAN": "상관",
    "PIANCAI": "편재", "ZHENGCAI": "정재", "QISHA": "편관", "ZHENGGUAN": "정관",
    "PIANYIN": "편인", "ZHENGYIN": "정인",
}
_GROUP_OF: dict[str, str] = {
    "비견": "peer", "겁재": "peer", "식신": "output", "상관": "output",
    "편재": "wealth", "정재": "wealth", "편관": "authority", "정관": "authority",
    "편인": "resource", "정인": "resource",
}
_FAVORABLE = {"용신", "희신"}


@lru_cache(maxsize=4)
def load_career_fields(dictionaries_dir: Path = _DICTS_DEFAULT) -> CareerFieldDict:
    """사전 로드(검증 포함, 캐시)."""
    raw = json.loads((dictionaries_dir / "career_fields.json").read_text(encoding="utf-8"))
    return CareerFieldDict.model_validate(raw)


def _group_pct(dist: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for tg, pct in dist.items():
        g = _GROUP_OF.get(tg)
        if g:
            out[g] = out.get(g, 0.0) + float(pct)
    return out


def _role_of(roles: dict[str, str], ten_god_ko: str) -> str:
    roman = next((r for r, k in ROMAN_TO_KO.items() if k == ten_god_ko), "")
    return roles.get(roman) or roles.get(_GROUP_OF.get(ten_god_ko, ""), "") or ""


def _group_role(roles: dict[str, str], group: str) -> str:
    return roles.get(group, "")


def _evaluate_modifiers(
    dictionary: CareerFieldDict, group_pct: dict[str, float], roles: dict[str, str], band: str
) -> list[str]:
    """용희신 조건표 6행을 기계적으로 평가해 성립한 id 목록을 돌려준다.

    '강함' = 군 비중 ≥ strong_pct, '과다' ≥ excess_pct, '일간 감당' = 신약이 아님(신강·중화),
    '유리' = 군 역할이 용신·희신, '필요' = 군 역할이 용신·희신(보완 역할). 문턱은 사전
    thresholds(감수 대상)이며 판정이 아니라 어떤 서술 조건이 성립하는지의 표식이다.
    """
    t = dictionary.thresholds
    strong = {g: v >= t.strong_pct for g, v in group_pct.items()}
    excess = {g: v >= t.excess_pct for g, v in group_pct.items()}
    fav = {
        g: _group_role(roles, g) in _FAVORABLE
        for g in ("output", "wealth", "authority", "resource", "peer")
    }
    bearable = band != "신약"
    hits: list[str] = []
    if strong.get("output") and bearable and fav["wealth"]:
        hits.append("output_strong_bearable_wealth_favorable")
    if strong.get("output") and not bearable and fav["resource"]:
        hits.append("output_strong_weak_dm_resource_needed")
    if strong.get("authority") and fav["resource"]:
        hits.append("authority_strong_resource_favorable")
    if strong.get("wealth") and not bearable:
        hits.append("wealth_strong_weak_dm")
    if excess.get("resource") and fav["output"]:
        hits.append("resource_excess_output_favorable")
    if strong.get("peer") and fav["output"] and fav["wealth"]:
        hits.append("peer_strong_output_wealth_favorable")
    return hits


def build_career_field_facts(
    result: ManseV2Result,
    incoming: list[tuple[str, str]] | None = None,
    dictionaries_dir: Path = _DICTS_DEFAULT,
) -> CareerFieldFacts:
    """명식에서 직업 분야 근거를 만든다(순수 함수).

    Args:
        result: 만세력 통합 결과(pillars·yongsin_analysis·geokguk 사용).
        incoming: 현재 운 [(라벨, 천간 십성 한글)] — 제안·기회가 들어오는 통로. 없으면 생략.
        dictionaries_dir: 사전 루트(테스트 오버라이드).

    Returns:
        CareerFieldFacts — 두드러진 십성(비중 상위, 역할·직업군), 성립 배합, 용희신 조건,
        통로, 원칙.
    """
    dictionary = load_career_fields(dictionaries_dir)
    facts = CareerFieldFacts(principles=list(dictionary.principles))
    if result.pillars is None:
        return facts
    facts.day_master = result.pillars.day_master
    dist = compute_ten_god_distribution(result.pillars).get("effective_percent", {})
    dfacts = build_direction_facts(result)
    roles = dict(dfacts.yongsin_roles)
    facts.strength_band = dfacts.strength_band
    gk = getattr(result, "geokguk", None)
    facts.geokguk = str(getattr(gk, "main_structure", "") or "") if gk is not None else ""
    t = dictionary.thresholds
    ranked = sorted(dist.items(), key=lambda kv: -float(kv[1]))
    for tg, pct in ranked[: t.prominent_top_n]:
        if float(pct) < t.prominent_pct or tg not in dictionary.ten_gods:
            continue
        spec = dictionary.ten_gods[tg]
        facts.prominent.append(ProminentTenGod(
            ten_god=tg, percent=round(float(pct), 1), role=_role_of(roles, tg),
            job_groups=list(spec.job_groups), distinction=spec.distinction, caution=spec.caution,
        ))
    # 배합 — 구조 패턴 감지기(pattern_id) 우선, 파생 규칙은 군 활성으로.
    detected = {p.pattern_id: p.strength for p in detect_structure_patterns(result)}
    active_groups = {_GROUP_OF[ROMAN_TO_KO[r]] for r in dfacts.ten_god_active if r in ROMAN_TO_KO}
    group_pct = _group_pct(dist)
    for combo in dictionary.combinations:
        strength = 0.0
        if combo.pattern_id and combo.pattern_id in detected:
            strength = float(detected[combo.pattern_id])
        elif combo.derived_rule == "peer_and_output_active":
            if {"peer", "output"} <= active_groups:
                strength = 0.5
        elif combo.derived_rule == "resource_and_output_active_no_dosik":
            if {"resource", "output"} <= active_groups and "PYEONIN_DOSIK" not in detected:
                strength = 0.5
        if strength > 0:
            facts.combinations.append(CombinationHit(
                name=combo.name, strength=round(strength, 2), mechanism=combo.mechanism,
                jobs=list(combo.jobs), condition=combo.condition,
            ))
    hit_ids = _evaluate_modifiers(dictionary, group_pct, roles, facts.strength_band)
    facts.modifiers = [m for m in dictionary.yongsin_modifiers if m.id in hit_ids]
    # 격국·신살 조건층(2026-10-15) — 보조 신호(단독 확정 금지), 근거 글자·오행 동반.
    facts.conditions = _evaluate_conditions(result, dictionary, group_pct)
    for label, tg in incoming or []:
        inc_spec = dictionary.ten_gods.get(tg)
        if inc_spec is None:
            continue
        facts.incoming.append(IncomingChannel(
            label=label, ten_god=tg, role=_role_of(roles, tg),
            job_groups=list(inc_spec.job_groups),
        ))
    return facts


def render_career_field_lines(facts: CareerFieldFacts) -> list[str]:
    """LLM 입력 블록 — 사실만(점수 아님). 빈 근거면 빈 목록."""
    if (
        not facts.prominent and not facts.combinations and not facts.incoming
        and not facts.conditions
    ):
        return []
    lines = ["[직업 분야 근거 — 엔진 확정(십성 기능 표, 판정 아님)]"]
    head = f"일간 {facts.day_master}" if facts.day_master else ""
    if facts.strength_band:
        head += f" · {facts.strength_band}"
    if facts.geokguk:
        head += f" · 격국 {facts.geokguk}"
    if head:
        lines.append(head.strip(" ·"))
    for p in facts.prominent:
        role = f"({p.role})" if p.role else ""
        lines.append(
            f"- 두드러진 십성 {p.ten_god}{role} {p.percent:.0f}%: {p.distinction} — "
            f"직업군 {', '.join(p.job_groups)} / 점검: {p.caution}"
        )
    for c in facts.combinations:
        lines.append(
            f"- 배합 {c.name}(강도 {c.strength:.2f}): {c.mechanism} — 직무 예 {', '.join(c.jobs)} "
            f"(성립 조건: {c.condition})"
        )
    for m in facts.modifiers:
        lines.append(f"- 용희신 조건 성립: {m.condition} → {m.reading}")
    if facts.conditions:
        lines.append(
            "[격국·신살 조건 — 보조 신호(통설, 단독 확정 금지). 위 십성 기능과 맞물릴 때만 분야를 "
            "좁히는 근거로 쓸 것]"
        )
        for cond in facts.conditions:
            lines.append(
                f"- {cond.field}: {cond.condition} — 근거 {cond.evidence} → "
                f"직업군 {', '.join(cond.jobs)}"
            )
    for inc in facts.incoming:
        role = f"({inc.role})" if inc.role else ""
        groups = ", ".join(inc.job_groups)
        lines.append(f"- 제안·기회 통로 {inc.label} 천간 {inc.ten_god}{role}: 직업군 {groups}")
    lines.append("원칙: " + " / ".join(facts.principles[:3]))
    return lines
