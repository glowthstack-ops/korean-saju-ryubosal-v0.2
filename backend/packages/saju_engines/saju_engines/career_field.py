"""직업 분야(십성 기능) 근거 엔진 — '어떤 분야/직종이 맞나·제안이 올까' 질문용 (2026-09-10).

명식의 십성 분포(effective_percent)·억부 역할(用喜忌仇閑)·격국·구조 패턴(식신생재 등)·현재
운 천간 십성을 사전(`career_fields.json`)의 직업 기능 표에 대응해 **서술 근거**를 만든다.
점수·판정을 만들지 않으며(LLM 계산 금지 원칙의 반대편 — 엔진이 사실을, LLM 이 문장을),
"십성이 있다고 적성 확정·없다고 부적합" 단정은 사전 원칙으로 금지한다.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from saju_manse_analysis.distribution.ten_god_distribution import compute_ten_god_distribution

from saju_shared_types.career_fields import (
    CareerFieldDict,
    CareerFieldFacts,
    CombinationHit,
    ConditionHit,
    IncomingChannel,
    OrientationFacts,
    ProminentTenGod,
)
from saju_shared_types.constants import BRANCH_ELEMENT, STEM_ELEMENT, hidden_stems_for
from saju_shared_types.enums import Branch, HiddenStemType, Stem
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
    today: date | None = None,
) -> CareerFieldFacts:
    """명식에서 직업 분야 근거를 만든다(순수 함수).

    Args:
        result: 만세력 통합 결과(pillars·yongsin_analysis·geokguk 사용).
        incoming: 현재 운 [(라벨, 천간 십성 한글)] — 제안·기회가 들어오는 통로. 없으면 생략.
        dictionaries_dir: 사전 루트(테스트 오버라이드).
        today: 기준일 — 주면 현재 대운(간지·십성)을 간지론 층(직업 유형 축·사업 시기)에 쓴다.

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
    # 간지론 번역층(2026-10-16 데굴님 승인) — 직업 유형 축·궁위 우선·관성 위치·업종·사업 시기.
    _apply_ganji_school(facts, result, dictionary, group_pct, dist, today)
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
    lines += _render_ganji_school(facts)
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


# ── 간지론 번역층 (2026-10-16 데굴님 승인 — 외부 강의 「제2강 직업선택」) ────────────────
# 전부 서술 전용(inert)이며 '[간지론 관점]' 머리말 아래 "간지론에서는 ~로 본다"로 서술한다.
_AUTHORITY_KO = {"정관", "편관"}
_RESOURCE_KO = {"정인", "편인"}
_OUTPUT_KO = {"식신", "상관"}
_WEALTH_KO = {"정재", "편재"}
_PEER_KO = {"비견", "겁재"}
_PALACE_ORDER = ("년", "월", "일", "시")
_BUSINESS_TYPE_TOP_N = 3  # 업종 결 상한(토큰) — 비중 상위부터
_PALACE_WEIGHT_KEY = {
    "월지": "month_branch", "월간": "month_stem", "년간": "year_stem", "년지": "year_branch",
    "일지": "day_branch", "시간": "hour_stem", "시지": "hour_branch",
}


def _palace_ten_gods(result: ManseV2Result) -> dict[str, str]:
    """궁위 → 십성(천간·지지 본기). 일간 자리는 본인이라 뺀다."""
    p = result.pillars
    if p is None:
        return {}
    out: dict[str, str] = {}
    for name, pillar in zip(_PALACE_ORDER, (p.year, p.month, p.day, p.hour), strict=True):
        if pillar is None:
            continue
        if name != "일":
            out[f"{name}간"] = pillar.stem_ten_god
        out[f"{name}지"] = pillar.branch_main_ten_god
    return out


def _current_daewoon(result: ManseV2Result, today: date | None) -> tuple[str, str, str] | None:
    """기준일의 대운 (간지, 천간 십성, 지지 십성). 없으면 None."""
    if today is None or result.luck_cycles is None:
        return None
    for d in result.luck_cycles.daewoon_table:
        if d.approx_start_date <= today < d.approx_end_date:
            return (d.ganji, d.stem_ten_god, d.branch_ten_god)
    return None


def _stem_rooted(stem: str, branches: list[str]) -> bool:
    """천간이 원국 지지들의 본기·중기에 같은 오행 뿌리를 갖는가(여기는 뿌리로 안 침)."""
    try:
        el = STEM_ELEMENT[Stem(stem)]
    except ValueError:
        return False
    for b in branches:
        try:
            for hstem, htype, _w in hidden_stems_for(Branch(b)):
                if htype is HiddenStemType.RESIDUAL:
                    continue
                if STEM_ELEMENT[hstem] is el:
                    return True
        except ValueError:
            continue
    return False


def _axis_of(ten_god: str, rule) -> str:
    g = _GROUP_OF.get(ten_god, "")
    if g in rule.workplace_groups:
        return "workplace"
    if g in rule.business_groups:
        return "business"
    return ""


def _career_orientation(
    result: ManseV2Result, dictionary: CareerFieldDict, group_pct: dict[str, float],
    palace: dict[str, str], clash_members: set[str], daewoon: tuple[str, str, str] | None,
) -> OrientationFacts | None:
    """직업 유형 축(직장형/상업형/혼합) — 간지론: 월지 우선 → 월간 → 년주 → 일지, 분포 보조,
    월지 충 간섭 감점. 판정이 아니라 '결이 맞는 방식'의 표식이다."""
    rule = dictionary.orientation
    if rule is None or result.pillars is None:
        return None
    wp = bp = 0.0
    basis: list[str] = []
    for pal, wkey in _PALACE_WEIGHT_KEY.items():
        tg = palace.get(pal)
        if not tg:
            continue
        weight = float(rule.weights.get(wkey, 0.0))
        axis = _axis_of(tg, rule)
        if axis == "workplace":
            wp += weight
            basis.append(f"{pal} {tg}(관·인 +{weight:g})")
        elif axis == "business":
            bp += weight
            basis.append(f"{pal} {tg}(식·재 +{weight:g})")
    wd = sum(group_pct.get(g, 0.0) for g in rule.workplace_groups)
    bd = sum(group_pct.get(g, 0.0) for g in rule.business_groups)
    if wd - bd >= rule.distribution_margin_pct:
        wp += rule.distribution_weight
        basis.append(f"분포 관·인 {wd:.0f}% > 식·재 {bd:.0f}%(+{rule.distribution_weight:g})")
    elif bd - wd >= rule.distribution_margin_pct:
        bp += rule.distribution_weight
        basis.append(f"분포 식·재 {bd:.0f}% > 관·인 {wd:.0f}%(+{rule.distribution_weight:g})")
    mb = result.pillars.month.branch
    if mb in clash_members:
        axis = _axis_of(palace.get("월지", ""), rule)
        if axis == "workplace":
            wp -= rule.clash_penalty
            basis.append(f"월지 {mb} 충 간섭(관·인 −{rule.clash_penalty:g})")
        elif axis == "business":
            bp -= rule.clash_penalty
            basis.append(f"월지 {mb} 충 간섭(식·재 −{rule.clash_penalty:g})")
    diff = wp - bp
    if diff >= rule.decide_margin:
        key = "workplace"
    elif -diff >= rule.decide_margin:
        key = "business"
    else:
        key = "mixed"
    dw_axis = ""
    if daewoon is not None:
        ganji, stg, btg = daewoon
        axes = {a for a in (_axis_of(stg, rule), _axis_of(btg, rule)) if a}
        if axes == {"workplace"}:
            dw_axis = f"현재 대운 {ganji}({stg}·{btg})이 관·인 축을 받친다"
        elif axes == {"business"}:
            dw_axis = f"현재 대운 {ganji}({stg}·{btg})이 식·재 축을 받친다"
        elif axes:
            dw_axis = f"현재 대운 {ganji}({stg}·{btg})은 두 축에 걸쳐 있다"
        else:
            dw_axis = f"현재 대운 {ganji}({stg}·{btg})은 비겁 축 — 어느 쪽도 직접 받치지 않는다"
    return OrientationFacts(
        label=rule.labels.get(key, key), key=key, workplace_axis=round(wp, 2),
        business_axis=round(bp, 2), basis=basis, reading=rule.readings.get(key, ""),
        daewoon_axis=dw_axis,
    )


def _palace_lines(dictionary: CareerFieldDict, palace: dict[str, str], axis_key: str) -> list[str]:
    pp = dictionary.palace_priority
    if pp is None or not palace:
        return []
    parts = [
        f"{pal} {palace[pal]}({pp.palace_meaning.get(pal, '')})"
        for pal in pp.order if palace.get(pal)
    ]
    lines = ["궁위 우선(월지→월간→년주→일지): " + " · ".join(parts)]
    target = (_AUTHORITY_KO | _RESOURCE_KO) if axis_key == "workplace" else (
        (_OUTPUT_KO | _WEALTH_KO) if axis_key == "business" else set()
    )
    if target:
        hits = [f"{pal}({pp.timing.get(pal, '')})" for pal in pp.order
                if palace.get(pal) in target and pp.timing.get(pal)]
        if hits:
            label = "관·인" if axis_key == "workplace" else "식·재"
            lines.append(f"사용 시기(근묘화실): {label} 자리 " + ", ".join(hits))
    return lines


def _officer_lines(
    result: ManseV2Result, dictionary: CareerFieldDict, palace: dict[str, str],
    daewoon: tuple[str, str, str] | None,
) -> list[str]:
    """관성 위치·통근·정편·관인 인접 설명(간지론 직장인 사주 ②~⑦·⑩)."""
    op = dictionary.officer_position
    p = result.pillars
    if op is None or p is None:
        return []
    pillars = [x for x in (p.year, p.month, p.day, p.hour) if x is not None]
    branches = [x.branch for x in pillars]
    stem_auth = [x for x in pillars if x.stem_ten_god in _AUTHORITY_KO]
    branch_auth = [x for x in pillars if x.branch_main_ten_god in _AUTHORITY_KO]
    if not stem_auth and not branch_auth:
        return []
    t = op.items
    lines: list[str] = []
    if stem_auth:
        rooted = any(_stem_rooted(x.stem, branches) for x in stem_auth)
        where = "·".join(f"{x.stem}" for x in stem_auth)
        lines.append(f"관성 천간 {where}: " + (t["stem_rooted"] if rooted else t["stem_unrooted"]))
    else:
        where = "·".join(x.branch for x in branch_auth)
        lines.append(f"관성 지지 {where}: " + t["branch_only"])
    kinds = {x.stem_ten_god for x in stem_auth} | {x.branch_main_ten_god for x in branch_auth}
    if "정관" in kinds:
        lines.append(t["jeonggwan"])
    if "편관" in kinds:
        lines.append(t["pyeongwan"])
    # 관·인 인접: 같은 기둥(천간·지지) 또는 이웃 기둥.
    idx_auth = {
        i for i, x in enumerate(pillars)
        if x.stem_ten_god in _AUTHORITY_KO or x.branch_main_ten_god in _AUTHORITY_KO
    }
    idx_res = {
        i for i, x in enumerate(pillars)
        if x.stem_ten_god in _RESOURCE_KO or x.branch_main_ten_god in _RESOURCE_KO
    }
    adjacent = any(abs(a - r) <= 1 for a in idx_auth for r in idx_res)
    if adjacent:
        lines.append(t["resource_adjacent"])
    elif not idx_res:
        lines.append(t["resource_absent"])
        if daewoon is not None and (daewoon[1] in _RESOURCE_KO or daewoon[2] in _RESOURCE_KO):
            lines.append(f"대운 {daewoon[0]} 인성: " + t["daewoon_resource"])
    if len(stem_auth) + len(branch_auth) >= 3:
        lines.append(t["authority_many"])
    return lines


def _business_lines(
    result: ManseV2Result, dictionary: CareerFieldDict, group_pct: dict[str, float],
    dist: dict[str, float], palace: dict[str, str],
) -> list[str]:
    """상업 업종 결(십성별·위치별) + 관계 규칙(간지론 2-1 ①~⑮)."""
    bt, br = dictionary.business_types, dictionary.business_rules
    p = result.pillars
    if bt is None or br is None or p is None:
        return []
    t = dictionary.thresholds
    pillars = [x for x in (p.year, p.month, p.day, p.hour) if x is not None]
    stems_tg = [x.stem_ten_god for x in pillars if x.stem_ten_god != "일간"]
    branches_tg = [x.branch_main_ten_god for x in pillars]
    lines: list[str] = []
    # 업종 결 후보(십성 비중 순) — 토큰 상한으로 상위 _BUSINESS_TYPE_TOP_N 만 싣는다.
    cands: list[tuple[float, str, str]] = []
    sik = float(dist.get("식신", 0.0))
    if "식신" in stems_tg:
        cands.append((sik, "식신_천간", f"천간 식신 {sik:.0f}%"))
    if "식신" in branches_tg:
        cands.append((sik, "식신_지지", f"지지 식신 {sik:.0f}%"))
    for tg, key in (("상관", "상관"), ("정재", "정재"), ("정인", "정인"), ("편인", "편인"),
                    ("겁재", "겁재_양인")):
        pct = float(dist.get(tg, 0.0))
        if pct >= t.prominent_pct:
            cands.append((pct, key, f"{tg} {pct:.0f}%"))
    pc = float(dist.get("편재", 0.0))
    if pc >= t.prominent_pct:
        no_out = group_pct.get("output", 0.0) < t.prominent_pct
        cands.append((pc, "편재", f"편재 {pc:.0f}%" + ("·식상 미약" if no_out else "")))
    cands.sort(key=lambda x: -x[0])
    for _pct, key, evidence in cands[:_BUSINESS_TYPE_TOP_N]:
        item = bt.items.get(key)
        if item is not None:
            lines.append(f"업종 결 {key.replace('_', ' ')}({evidence}): {item.meaning} — "
                         + ", ".join(item.types))
    # 관계 규칙
    out_idx = {i for i, x in enumerate(pillars)
               if x.stem_ten_god in _OUTPUT_KO or x.branch_main_ten_god in _OUTPUT_KO}
    wea_idx = {i for i, x in enumerate(pillars)
               if x.stem_ten_god in _WEALTH_KO or x.branch_main_ten_god in _WEALTH_KO}
    auth_present = any(tg in _AUTHORITY_KO for tg in stems_tg + branches_tg)
    res_present = any(tg in _RESOURCE_KO for tg in stems_tg + branches_tg)
    peer_branch = any(tg in _PEER_KO for tg in branches_tg)
    signals: set[str] = set()
    if out_idx and wea_idx:
        if any(abs(o - w) <= 1 for o in out_idx for w in wea_idx):
            signals.add("output_wealth_adjacent")
        else:
            signals.add("output_wealth_apart")
    elif wea_idx and not out_idx:
        signals.add("wealth_without_output")
    jeonggwan = "정관" in stems_tg or "정관" in branches_tg
    if jeonggwan and group_pct.get("authority", 0.0) >= t.strong_pct and wea_idx:
        signals.add("officer_strong_wealth")
    if group_pct.get("peer", 0.0) >= t.strong_pct and auth_present:
        signals.add("peer_many_officer")
    if not peer_branch:
        signals.add("peer_no_branch")
    if not res_present:
        signals.add("resource_absent_lease")
    wealth_els = sorted({
        _letter_element(x.stem) for x in pillars if x.stem_ten_god in _WEALTH_KO
    } | {
        _letter_element(x.branch) for x in pillars if x.branch_main_ten_god in _WEALTH_KO
    } - {""})
    if wealth_els:
        signals.add("wealth_letter")
    for rule in br.items:
        if rule.signal in signals:
            text = rule.text
            if rule.signal == "wealth_letter":
                text = text.format(element="·".join(wealth_els))
            lines.append(text)
    return lines


def _timing_lines(
    dictionary: CareerFieldDict, group_pct: dict[str, float],
    daewoon: tuple[str, str, str] | None,
) -> list[str]:
    bt = dictionary.business_timing
    if bt is None:
        return []
    lines: list[str] = []
    if daewoon is not None:
        ganji, stg, btg = daewoon
        if (stg in _RESOURCE_KO or btg in _RESOURCE_KO) and (
            group_pct.get("output", 0.0) >= dictionary.thresholds.prominent_pct
        ):
            lines.append(f"대운 {ganji}({stg}·{btg}): " + bt.resource_daewoon_controls_output)
        elif stg in (_OUTPUT_KO | _WEALTH_KO) or btg in (_OUTPUT_KO | _WEALTH_KO):
            lines.append(f"대운 {ganji}({stg}·{btg}): " + bt.business_daewoon_supports)
    lines.append(bt.daewoon_over_sewoon)
    return lines


def _apply_ganji_school(
    facts: CareerFieldFacts, result: ManseV2Result, dictionary: CareerFieldDict,
    group_pct: dict[str, float], dist: dict[str, float], today: date | None,
) -> None:
    """간지론 번역층 전체를 facts 에 채운다(사전 절이 없으면 아무것도 하지 않는다)."""
    gs = dictionary.ganji_school
    if gs is None or result.pillars is None:
        return
    facts.school_label = gs.label
    facts.school_narration = gs.narration
    palace = _palace_ten_gods(result)
    sa = result.structure_analysis
    inters = list(sa.interactions) if sa is not None else []
    clash_members = {m for i in inters if i.relation_type == "clash" for m in i.members}
    daewoon = _current_daewoon(result, today)
    facts.orientation = _career_orientation(
        result, dictionary, group_pct, palace, clash_members, daewoon,
    )
    axis_key = facts.orientation.key if facts.orientation is not None else ""
    facts.palace_lines = _palace_lines(dictionary, palace, axis_key)
    facts.officer_lines = _officer_lines(result, dictionary, palace, daewoon)
    wn = dictionary.workplace_notes
    if wn is not None and group_pct.get("resource", 0.0) >= dictionary.thresholds.excess_pct:
        facts.workplace_lines = [wn.resource_excess]
    if axis_key != "workplace":  # 상업형·혼합형에만 업종·사업 시기 결
        facts.business_lines = _business_lines(result, dictionary, group_pct, dist, palace)
        facts.timing_lines = _timing_lines(dictionary, group_pct, daewoon)


def _render_ganji_school(facts: CareerFieldFacts) -> list[str]:
    """'[간지론 관점]' 블록 — 학파 서술("간지론에서는 ~로 본다"), 판정·점수 아님."""
    if not facts.school_label or facts.orientation is None:
        return []
    o = facts.orientation
    nar = facts.school_narration or f"{facts.school_label}에서는"
    lines = [
        f"[{facts.school_label} 관점 — 직업 유형 축·궁위·관성 위치·업종·사업 시기 "
        f"(학파 서술: '{nar} ~로 본다'로 쓸 것, 억부 용신 판정과 별개·단정 금지)]",
        f"- 직업 유형 축: {o.label}(관·인 {o.workplace_axis:g} vs 식·재 {o.business_axis:g}) — "
        f"근거 {', '.join(o.basis) if o.basis else '해당 궁위 없음'}. {nar} {o.reading}",
    ]
    if o.daewoon_axis:
        lines.append(f"- 대운 축: {o.daewoon_axis}")
    lines += [f"- {x}" for x in facts.palace_lines]
    lines += [f"- 관성 위치(직장 축): {x}" for x in facts.officer_lines]
    lines += [f"- 보조: {x}" for x in facts.workplace_lines]
    lines += [
        f"- {x}" if x.startswith("업종 결") else f"- 업종 규칙: {x}" for x in facts.business_lines
    ]
    lines += [f"- 사업 시기: {x}" for x in facts.timing_lines]
    return lines
