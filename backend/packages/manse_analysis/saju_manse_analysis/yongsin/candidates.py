"""용신 후보 모델 산출 및 통합.

원칙: 부족 오행을 자동 용신 처리하지 않고, 신약/신강을 일률 처리하지 않으며,
특수격을 억부보다 먼저 검사한다. 최초 status 는 candidate (검증 전 calibrated 금지).
"""

from __future__ import annotations

from saju_shared_types.analysis import ForceAnalysis
from saju_shared_types.constants import (
    CONTROLS,
    GENERATES,
    STEM_ELEMENT,
    group_elements,
)
from saju_shared_types.enums import Branch, Element, Stem
from saju_shared_types.pillars import FourPillarsResult
from saju_shared_types.structure import GeokgukResult, StructureAnalysis
from saju_shared_types.yongsin import (
    AggregatedYongsinResult,
    ElementCandidate,
    YongsinCandidateModel,
)

from .special_cases import detect_special_cases

_WEAK = {"극신약", "태신약", "신약", "중화신약"}
_NEUTRAL = {"중화", "중화신강"}
_STRONG = {"신강", "태신강", "극신강"}
_COLD_MONTHS = {Branch.HAE, Branch.JA, Branch.CHUK}
_HOT_MONTHS = {Branch.SA, Branch.O, Branch.MI}

# 모델 → 용신 판단 축. (격국/병약/조후는 보정 레이어, 특수격은 우선)
_AXIS_OF: dict[str, str] = {
    "support_day_master": "eokbu", "resource_as_yongsin": "eokbu",
    "output_as_yongsin": "eokbu", "eokbu_normal": "eokbu",
    "wealth_breaks_resource": "eokbu", "officer_controls_peer": "eokbu",
    "resource_curbs_output": "eokbu", "resource_pattern_officer": "eokbu",
    "johu": "johu", "pattern_sangsin": "pattern", "disease_remedy": "disease",
    "dominant_one_element": "special", "follow_structure": "special",
    "bridge_tonggwan": "bridge",
}


def _axis_of(model_type: str) -> str:
    """Model instance keys may carry a suffix, e.g. disease_remedy:pyeonin_dosik."""
    return _AXIS_OF.get(model_type.split(":", 1)[0], "eokbu")


# 종격 세분: 압도 세력 그룹 → 종격 명칭.
_FOLLOW_SUBTYPE: dict[str, str] = {
    "output": "종아격(從兒格)", "wealth": "종재격(從財格)", "officer": "종살격(從殺格)",
}
# 파격(damage) → 약신(repair) 그룹.
_DAMAGE_REPAIR: dict[str, str] = {
    "shangguan_attacks_officer": "resource",   # 인성으로 상관 제어
    "mixed_officer_killing": "output",          # 식신제살
    "killing_overwhelms_weak": "resource",      # 살인상생
    "wealth_overwhelms_weak": "peer",           # 비겁 부조
    "pyeonin_dosik": "wealth",                  # 재성으로 편인 제어
    "bigyeob_jaengjae": "officer",              # 관성으로 비겁 제어
}


def _e(el: Element) -> str:
    return str(el)


def _strongest_pressure(groups: dict[str, float]) -> str:
    pressure = {k: groups[k] for k in ("output", "wealth", "officer")}
    return max(pressure, key=lambda g: pressure[g])


def _support_model(g: dict[str, Element], strength) -> YongsinCandidateModel:
    """부일간형: 신약 일간을 비겁으로 직접 보강 (용=비겁, 희=인성, 기=관살, 구=재성, 한=식상)."""
    # 통합형 강약(0~100, 중화 50). 약할수록(50에서 멀수록) 부일간 신뢰도가 높다.
    conf = round(min(0.5 + max(50.0 - strength.score, 0.0) / 60, 0.85), 4)
    return YongsinCandidateModel(
        model_type="support_day_master",
        label="부일간형(비겁 보강)",
        yongsin=_e(g["peer"]), heesin=_e(g["resource"]),
        gisin=_e(g["officer"]), gusin=_e(g["wealth"]), hansin=_e(g["output"]),
        confidence=conf,
        reasons=["신약 일간을 비겁으로 직접 보강", "관살이 일간을 압박하므로 기신"],
    )


def _resource_model(g: dict[str, Element], strength) -> YongsinCandidateModel:
    """인성용신형: 재성·식상으로 빠지는 기운을 인성으로 회복 (관인상생, 희=관살)."""
    # 통합형 강약 거리 기준(부일간형보다 base·기울기를 낮게 — 2차 후보).
    conf = round(min(0.45 + max(50.0 - strength.score, 0.0) / 75, 0.78), 4)
    return YongsinCandidateModel(
        model_type="resource_as_yongsin",
        label="인성용신형(관인상생)",
        yongsin=_e(g["resource"]), heesin=_e(g["officer"]),
        gisin=_e(g["wealth"]), gusin=_e(g["output"]), hansin=_e(g["peer"]),
        confidence=conf,
        reasons=["재성/식상 누출을 인성으로 회복", "관성이 인성을 생조(관인상생)"],
    )


def _output_model(g: dict[str, Element], strength) -> YongsinCandidateModel:
    """식상용신형: 신왕하나 관살이 강할 때 식상으로 관살을 제어."""
    return YongsinCandidateModel(
        model_type="output_as_yongsin",
        label="식상용신형(제살)",
        yongsin=_e(g["output"]), heesin=_e(g["peer"]),
        gisin=_e(g["officer"]), gusin=_e(g["wealth"]), hansin=_e(g["resource"]),
        confidence=0.55,
        reasons=["신왕 + 관살 강 → 식상으로 제어"],
    )


def _eokbu_strong_model(g: dict[str, Element], strength) -> YongsinCandidateModel:
    """일반 억부(신강): 식상 설기 + 재성, 기신=인성/비겁."""
    # 통합형 강약 거리 기준. 강할수록(50에서 위로 멀수록) 설기·재관 신뢰도가 높다.
    conf = round(min(0.5 + max(strength.score - 50.0, 0.0) / 60, 0.85), 4)
    return YongsinCandidateModel(
        model_type="eokbu_normal",
        label="억부형(설기·재관)",
        yongsin=_e(g["output"]), heesin=_e(g["wealth"]),
        gisin=_e(g["resource"]), gusin=_e(g["peer"]), hansin=_e(g["officer"]),
        confidence=conf,
        reasons=["신강 일간을 식상으로 설기", "인성/비겁 과다는 기신"],
    )


def _resource_overload(groups: dict[str, float]) -> bool:
    """인성과다(印重) — 인성이 압도적으로 큰 신강. 식상 설기보다 재성 제어가 맞다."""
    total = sum(groups.values()) or 1.0
    resource = groups.get("resource", 0.0)
    return resource / total >= 0.35 and resource > groups.get("peer", 0.0) * 1.5


def _resource_overload_strict(groups: dict[str, float]) -> bool:
    """중화신강용 엄격 인성과다 — 비중·비겁 대비 우세를 더 높게 본다(곧바로 확정 금지)."""
    total = sum(groups.values()) or 1.0
    resource = groups.get("resource", 0.0)
    return resource / total >= 0.40 and resource > groups.get("peer", 0.0) * 2.0


def _bigyeob_overload(groups: dict[str, float]) -> bool:
    """비겁과다(군겁쟁재) — 비겁이 재성을 압도하는 신강. 재성은 군겁대상이라 용·희 부적격."""
    total = sum(groups.values()) or 1.0
    peer = groups.get("peer", 0.0)
    return peer / total >= 0.35 and peer > groups.get("wealth", 0.0) * 1.5


def _officer_heavy(groups: dict[str, float]) -> bool:
    """관살과다(살중) — 관성이 비겁을 압도하는 신약. 비겁은 관극비로 깨져 인성(살인상생)이 정석."""
    total = sum(groups.values()) or 1.0
    officer = groups.get("officer", 0.0)
    return officer / total >= 0.30 and officer > groups.get("peer", 0.0) * 1.5


def _output_heavy(groups: dict[str, float]) -> bool:
    """식상과다 — 식상이 압도하는 신약. 인성으로 제식상·생일간(印制食). 비겁은 식상을 생해 악화."""
    total = sum(groups.values()) or 1.0
    output = groups.get("output", 0.0)
    return output / total >= 0.35 and output > groups.get("peer", 0.0) * 1.5


def _johu_or_disease_active(month_branch: Branch, geokguk: GeokgukResult) -> bool:
    """조후(한습·조열 월령) 또는 병증(파격 2건+)이 우선되는 상황인가."""
    ev = geokguk.evaluation
    active = ev.total_active if ev else 0
    cold_hot = month_branch in (_COLD_MONTHS | _HOT_MONTHS)
    return cold_hot or active >= 2


def _jaeda_sinyak(groups: dict[str, float]) -> bool:
    """재다신약 — 재성이 인성을 압도(재극인·무근)하고 일간보다 강함. 인성은 용·희 부적격."""
    return groups["wealth"] > groups["resource"] * 3 and groups["wealth"] > groups["peer"]


def _climate_harmful(month_branch: Branch, force: ForceAnalysis) -> str | None:
    """조후 역행 원소(용·희 부적격). 한습(亥子丑)+火 미약 → 水, 조열(巳午未)+水 미약 → 火."""
    dist = force.five_elements.season_adjusted_element_strength or {}
    total = sum(dist.values()) or 1.0
    if month_branch in _COLD_MONTHS and dist.get(Element.FIRE, 0.0) / total < 0.22:
        return _e(Element.WATER)
    if month_branch in _HOT_MONTHS and dist.get(Element.WATER, 0.0) / total < 0.22:
        return _e(Element.FIRE)
    return None


def _classify_roles(
    g: dict[str, Element],
    groups: dict[str, float],
    band: str,
    useful: dict[str, tuple[float, str, str]],
    unfavorable: dict[str, tuple[float, str, str]],
    yongsin_el: str | None,
) -> dict[str, str | None]:
    """용신을 중심으로 기신·구신·희신·한신을 강약·생극으로 1개씩 배정(5오행 분할).

    억부에서 용신과 '병(기신)'은 항상 극 관계이므로 기신 후보는 {극용신, 용신극} 둘뿐이다.
      - 신약: 생조(인성·비겁)가 용신 → 기신은 그 용신을 직접 극하는 쪽(극용신, 예: 재극인·관극비).
      - 신강: 설기·소모·극(식상·재성·관성)이 용신 → 기신은 과다한 생조(인성·비겁) 쪽.
    기신 확정 후: 구신=생기신, 남은 둘 중 강약상 길한 쪽=희신(단 그 길신이 스스로 과다·포화면
    설기 쪽으로 교체), 나머지=한신. (희신은 생용신뿐 아니라 기신 제어·설기 오행도 포함.)
    """
    if not yongsin_el:
        return {k: None for k in ("yongsin", "heesin", "gisin", "gusin", "hansin")}
    roles_of = {_e(v): k for k, v in g.items()}  # 오행 → 십성 역할
    total = sum(groups.values()) or 1.0
    drain_grps = {"output", "wealth", "officer"}  # 설·소모·극 (신강 길/신약 병)
    boost_grps = {"resource", "peer"}             # 생·조 (신약 길/신강 병)
    strong = band in ("신강", "태신강", "극신강", "중화신강")
    weak = band in _WEAK  # 신약군(중화신약 포함)

    def _ratio(el: str) -> float:
        return groups.get(roles_of[el], 0.0) / total

    def _gen_of(el: str) -> str:  # el 을 생하는 오행(생el)
        return next(_e(x) for x in Element if GENERATES[x] == Element(el))

    def _ctrl_of(el: str) -> str:  # el 을 극하는 오행(극el)
        return next(_e(x) for x in Element if CONTROLS[x] == Element(el))

    geuk_yong = _ctrl_of(yongsin_el)                # 극용신
    yong_geuk = _e(CONTROLS[Element(yongsin_el)])   # 용신극
    cands = [geuk_yong, yong_geuk]

    def _badness(el: str) -> float:
        grp = roles_of[el]
        if weak:  # 신약: 설기/극 십성이 병, 용신을 직접 극하는 쪽(극용신)에 가중.
            base = 1.0 if grp in drain_grps else 0.0
            return base + (0.5 if el == geuk_yong else 0.0) + 0.3 * _ratio(el)
        if strong:  # 신강: 생조(인성·비겁) 과다가 병.
            return (1.0 if grp in boost_grps else 0.0) + _ratio(el)
        # 중화: 분포·투표 기반.
        return _ratio(el) + unfavorable.get(el, (0.0, "", ""))[0] - useful.get(el, (0.0, "", ""))[0]

    gisin = max(cands, key=_badness)
    gusin = _gen_of(gisin)  # 생기신
    remaining = [e for e in sorted(roles_of) if e not in (yongsin_el, gisin, gusin)]

    def _favorable(el: str) -> bool:
        grp = roles_of[el]
        if weak:
            return grp in boost_grps   # 신약: 생조가 길
        if strong:
            return grp in drain_grps   # 신강: 설기가 길
        return False

    fav = [e for e in remaining if _favorable(e)]
    if fav:
        heesin = min(fav, key=_ratio)  # 덜 과다한 길신 우선
        if _ratio(heesin) >= 0.33:     # 길신이 스스로 과다·포화 → 설기 쪽(남은 오행)으로 교체
            alt = [e for e in remaining if e != heesin]
            if alt:
                heesin = alt[0]
    elif remaining:
        heesin = min(remaining, key=_ratio)  # 둘 다 흉이면 덜 과다한 쪽
    else:
        heesin = None
    hansin = next((e for e in remaining if e != heesin), None)
    return {
        "yongsin": yongsin_el,
        "heesin": heesin,
        "gisin": gisin,
        "gusin": gusin,
        "hansin": hansin,
    }


def _classify_bridge_roles(
    g: dict[str, Element],
    groups: dict[str, float],
    detail: str | None,
    useful: dict[str, tuple[float, str, str]],
    yongsin_el: str,
) -> dict[str, str | None]:
    """통관용신은 과다한 상극 축 사이를 잇는 오행이므로 억부식 극관계 배정을 쓰지 않는다."""
    roles_of = {_e(v): k for k, v in g.items()}  # 오행 → 십성 역할
    elements = {_e(e) for e in Element}
    total = sum(groups.values()) or 1.0

    # 통관 보조는 기존 억부/격국 모델이 명시한 희신을 우선한다.
    heesin = next(
        (
            el for el, (_score, _model, role) in sorted(
                useful.items(), key=lambda kv: kv[1][0], reverse=True
            )
            if el != yongsin_el and role == "heesin"
        ),
        None,
    )

    # detail 예: "木→火→土|통관용신=火". 앞쪽 과다·충돌 원소를 병으로 본다.
    gisin = None
    if detail and "→" in detail:
        source = detail.split("|", 1)[0].split("→", 1)[0]
        if source in elements and source != yongsin_el:
            gisin = source
    if gisin is None:
        gisin = max(
            (e for e in elements if e != yongsin_el and e != heesin),
            key=lambda el: groups.get(roles_of[el], 0.0) / total,
        )

    # 구신은 통관 흐름의 도착점 또는 기신을 생하는 오행보다, 실제 흐름을 막는 다음 과다축으로 둔다.
    gusin = None
    if detail and "→" in detail:
        parts = detail.split("|", 1)[0].split("→")
        if len(parts) >= 3 and parts[2] in elements and parts[2] not in {yongsin_el, heesin, gisin}:
            gusin = parts[2]
    if gusin is None:
        remaining_for_gusin = elements - {yongsin_el, heesin, gisin}
        gusin = max(
            remaining_for_gusin,
            key=lambda el: groups.get(roles_of[el], 0.0) / total,
        ) if remaining_for_gusin else None

    if heesin is None:
        remaining_for_hee = elements - {yongsin_el, gisin, gusin}
        heesin = max(
            remaining_for_hee,
            key=lambda el: useful.get(el, (0.0, "", ""))[0],
        ) if remaining_for_hee else None

    hansin = next(
        (e for e in sorted(elements) if e not in {yongsin_el, heesin, gisin, gusin}), None
    )
    return {
        "yongsin": yongsin_el,
        "heesin": heesin,
        "gisin": gisin,
        "gusin": gusin,
        "hansin": hansin,
    }


def _resource_excess_model(g: dict[str, Element], strength) -> YongsinCandidateModel:
    """재성용신형(財損印): 인성과다 신강 → 재성으로 인성 제어, 관성으로 일간 억제."""
    conf = round(min(0.55 + max(strength.score - 50.0, 0.0) / 60, 0.9), 4)
    return YongsinCandidateModel(
        model_type="wealth_breaks_resource",
        label="재성용신형(財損印·인성과다)",
        yongsin=_e(g["wealth"]), heesin=_e(g["officer"]),
        gisin=_e(g["resource"]), gusin=_e(g["peer"]), hansin=_e(g["output"]),
        confidence=conf,
        reasons=[
            "인성 과다 → 재성으로 인성 제어(財損印)",
            "관성으로 일간 억제·조후, 식상은 인성에 극당해 무력",
        ],
    )


def _resource_pattern_officer_model(g: dict[str, Element], strength) -> YongsinCandidateModel:
    """인수격·인성과다: 관성으로 격의 상신/조후를 세우고 재성으로 탁한 인성을 제어."""
    conf = round(min(0.58 + max(strength.score - 50.0, 0.0) / 58, 0.92), 4)
    return YongsinCandidateModel(
        model_type="resource_pattern_officer",
        label="인수격 관성용신형(관성 상신·재성 보조)",
        yongsin=_e(g["officer"]), heesin=_e(g["wealth"]),
        gisin=_e(g["resource"]), gusin=_e(g["peer"]), hansin=_e(g["output"]),
        confidence=conf,
        reasons=[
            "인수격에서 인성이 과다하면 관성으로 격의 상신을 세움",
            "재성은 과다한 인성을 제어해 관성을 보조",
        ],
    )


def _bigyeob_rob_model(g: dict[str, Element], strength) -> YongsinCandidateModel:
    """군겁쟁재형: 비겁 태왕 → 관성으로 제압·식상으로 통관. 재성 직접은 군겁쟁재(한신)."""
    conf = round(min(0.55 + max(strength.score - 50.0, 0.0) / 60, 0.9), 4)
    return YongsinCandidateModel(
        model_type="officer_controls_peer",
        label="군겁쟁재형(관성 제겁)",
        yongsin=_e(g["officer"]), heesin=_e(g["output"]),
        gisin=_e(g["peer"]), gusin=_e(g["resource"]), hansin=_e(g["wealth"]),
        confidence=conf,
        reasons=[
            "비겁 태왕 → 관성으로 제압(관극비)",
            "식상으로 통관(비겁→식상→재), 재성 직접은 군겁쟁재",
        ],
    )


def _kill_to_resource_model(g: dict[str, Element], strength) -> YongsinCandidateModel:
    """살인상생형(살중용인): 관살 태왕 → 인성으로 살을 화하고 일간 생. 비겁은 방조(희)."""
    conf = round(min(0.6 + max(50.0 - strength.score, 0.0) / 55, 0.9), 4)
    return YongsinCandidateModel(
        model_type="resource_as_yongsin",
        label="살인상생형(살중용인)",
        yongsin=_e(g["resource"]), heesin=_e(g["peer"]),
        gisin=_e(g["wealth"]), gusin=_e(g["output"]), hansin=_e(g["officer"]),
        confidence=conf,
        reasons=[
            "관살 태왕 → 인성으로 살을 화함(살인상생)",
            "비겁은 일간 방조(희신), 재성은 재생살·재극인으로 기신",
        ],
    )


def _output_overload_model(g: dict[str, Element], strength) -> YongsinCandidateModel:
    """인성제식상형(식상과다 신약): 인성으로 식상 제어·생일간(印制食). 비겁 방조, 관성 관인상생."""
    conf = round(min(0.6 + max(50.0 - strength.score, 0.0) / 55, 0.9), 4)
    return YongsinCandidateModel(
        model_type="resource_curbs_output",
        label="인성제식상형(식상과다)",
        yongsin=_e(g["resource"]), heesin=_e(g["peer"]),
        gisin=_e(g["output"]), gusin=_e(g["wealth"]), hansin=_e(g["officer"]),
        confidence=conf,
        reasons=[
            "식상 과다 → 인성으로 제어·생일간(印制食)",
            "식상이 병(기신)·재성 구신, 관성은 관인상생(한신)",
        ],
    )


def _johu_model(month_branch: Branch, g: dict[str, Element]) -> YongsinCandidateModel | None:
    """조후 보조형: 한난 불균형 시 화/수 후보 (단독 확정 금지)."""
    if month_branch in _COLD_MONTHS:
        yong = Element.FIRE
        reason = "겨울/한습 월령 → 화로 조후"
    elif month_branch in _HOT_MONTHS:
        yong = Element.WATER
        reason = "여름/조열 월령 → 수로 조후"
    else:
        return None
    return YongsinCandidateModel(
        model_type="johu",
        label="조후 보조형",
        yongsin=_e(yong),
        confidence=0.4,
        reasons=[reason, "조후는 단독 확정 금지, 억부와 함께 검증"],
        is_auxiliary=True,
    )


def _pattern_model(geokguk: GeokgukResult, g: dict[str, Element]) -> YongsinCandidateModel | None:
    """격국용신형: 성격(成格) 시 상신 그룹을 용신 후보로(보정 레이어). 패격이면 병약이 담당."""
    ev = geokguk.evaluation
    if ev is None or ev.pattern_confidence < 0.4 or geokguk.formation_level == "패":
        return None
    sangsin = _GEOK_SANGSIN_GROUPS.get(geokguk.main_structure or "", [])
    if not sangsin:
        return None
    return YongsinCandidateModel(
        model_type="pattern_sangsin", label="격국용신형(상신)",
        yongsin=_e(g[sangsin[0]]),
        heesin=_e(g[sangsin[1]]) if len(sangsin) > 1 else None,
        confidence=round(ev.pattern_confidence, 4),
        reasons=[
            f"{geokguk.main_structure} 성격 → 상신 격국용신 후보",
            "단독 확정 금지(보정 레이어)",
        ],
        is_auxiliary=True,
    )


def _disease_models(
    geokguk: GeokgukResult, g: dict[str, Element]
) -> list[YongsinCandidateModel]:
    """병약용신형: 격국 파격 원인(damage_types)을 제거하는 약신 후보."""
    ev = geokguk.evaluation
    if ev is None:
        return []
    out: list[YongsinCandidateModel] = []
    seen: set[str] = set()
    for dmg in ev.damage_types:
        grp = _DAMAGE_REPAIR.get(dmg)
        if grp is None or grp in seen:
            continue
        seen.add(grp)
        out.append(YongsinCandidateModel(
            model_type=f"disease_remedy:{dmg}", label="병약용신형(약신)",
            yongsin=_e(g[grp]),
            confidence=0.5,
            reasons=[f"파격({dmg}) 제거 약신", "병약은 패격 보정 후보"],
            is_auxiliary=True,
        ))
    return out


_GEOK_SANGSIN_GROUPS: dict[str, list[str]] = {
    "정관격": ["wealth", "resource"], "편관격": ["output", "resource"],
    "정재격": ["output", "peer"], "편재격": ["output", "peer"],
    "식신격": ["wealth"], "상관격": ["resource", "wealth"],
    "정인격": ["officer"], "편인격": ["wealth", "output"],
    "건록격": ["wealth", "officer"], "양인격": ["officer", "output"],
    "월겁격": ["officer", "output"],
}


def _select_axis_weights(
    band: str, month_branch: Branch, geokguk: GeokgukResult, special: bool,
    bridge_required: bool = False,
) -> dict[str, float]:
    """상황별 동적 축 가중치(사용자 §10). 신약은 억부 우선 → 용신 안정."""
    if special:
        return {
            "special": 1.0, "bridge": 0.1, "eokbu": 0.1,
            "johu": 0.1, "pattern": 0.1, "disease": 0.1,
        }
    if bridge_required:
        return {
            "bridge": 0.45, "eokbu": 0.20, "disease": 0.20,
            "pattern": 0.15, "johu": 0.10, "special": 0.1,
        }
    ev = geokguk.evaluation
    active = ev.total_active if ev else 0
    fw = ev.final_weight if ev else 0.15
    # 丑(한겨울)·未(한여름)은 土월이라도 한난이 극단 → 조후 대상에 포함.
    cold_hot = month_branch in (_COLD_MONTHS | _HOT_MONTHS)
    if band in _WEAK:  # 신약/중화신약 → 억부 우선(종격은 special에서 처리)
        return {
            "eokbu": 0.45, "johu": 0.25, "pattern": 0.15,
            "disease": 0.15, "bridge": 0.1, "special": 0.1,
        }
    if active >= 2:  # 파격 뚜렷 → 병약 우선
        return {
            "disease": 0.35, "eokbu": 0.25, "johu": 0.20,
            "pattern": 0.20, "bridge": 0.1, "special": 0.1,
        }
    if cold_hot:  # 중화/신강 + 한습·조열 → 조후 우선
        return {
            "johu": 0.40, "eokbu": 0.25, "pattern": 0.20,
            "disease": 0.15, "bridge": 0.1, "special": 0.1,
        }
    if fw >= 0.30:  # 격국 선명 → 격국 우선
        return {
            "pattern": 0.40, "eokbu": 0.25, "johu": 0.20,
            "disease": 0.15, "bridge": 0.1, "special": 0.1,
        }
    return {
        "eokbu": 0.35, "johu": 0.20, "pattern": 0.25,
        "disease": 0.20, "bridge": 0.1, "special": 0.1,
    }


def _weak_band_models(
    g: dict[str, Element], groups: dict[str, float], strength, force: ForceAnalysis
) -> list[YongsinCandidateModel]:
    """신약(극신약~중화신약) 억부 1차 후보. follow(진종)·special 미해당 시 사용."""
    sp = _strongest_pressure(groups)
    rooted_strong = strength.rootedness.get("label") == "신왕"
    has_root = bool(force.rooting.tonggeun)
    out: list[YongsinCandidateModel] = []
    if groups.get("peer", 0.0) <= 0.0 and groups.get("resource", 0.0) > 0.0:
        # 비겁이 전무하면 인성으로 식상을 제어하기 전에 일간 자체의 불씨를 세우는
        # 직접 보강을 1순위로 둔다. 남은 인성은 희신/경쟁 후보로 검증한다.
        out.append(_support_model(g, strength))
        out.append(_resource_model(g, strength))
    elif _output_heavy(groups):
        # 식상과다 → 인성으로 제식상·생일간(印制食). 비겁은 식상을 생해 악화 → 부일간형 제외.
        out.append(_output_overload_model(g, strength))
    elif _officer_heavy(groups):
        # 살중(관살 태왕) → 살인상생(인성) 우선, 비겁은 방조. 뿌리 강하면 식신제살도 경쟁.
        out.append(_support_model(g, strength))
        out.append(_kill_to_resource_model(g, strength))
        if rooted_strong:
            out.append(_output_model(g, strength))
    else:
        out.append(_support_model(g, strength))
        if rooted_strong and sp == "officer":
            out.append(_output_model(g, strength))
        elif has_root and sp in ("wealth", "output") and not _jaeda_sinyak(groups):
            # 재다신약은 재극인으로 인성용신 불가 → 인성용신형 제외(부일간형만).
            out.append(_resource_model(g, strength))
    return out


def _circulation(force: ForceAnalysis) -> dict:
    """유통(流通): 오행이 상생(목→화→토→금→수)으로 막힘없이 순환하는 정도.

    신약이라도 흐름이 원활하면 한쪽 고립이 적어 유연·적응형으로 본다(정보성 지표).
    """
    fe = force.five_elements
    pct = fe.season_adjusted_element_strength or fe.distribution_environment
    present = {e for e, p in pct.items() if p >= 8.0}
    links = sum(1 for el in Element if str(el) in present and str(GENERATES[el]) in present)
    n_present = len(present)
    return {
        "score": round(links / 5.0, 3),  # 상생 고리 5개 중 성립 비율
        "sheng_links": links,
        "present_elements": sorted(present),
        "all_five_present": n_present == 5,
        "smooth": links >= 4 and n_present >= 4,
    }


def build_yongsin(
    pillars: FourPillarsResult,
    force: ForceAnalysis,
    structure: StructureAnalysis,
    geokguk: GeokgukResult,
) -> AggregatedYongsinResult:
    dm = Stem(pillars.day.stem)
    dm_el = STEM_ELEMENT[dm]
    g = group_elements(dm_el)
    groups = force.ten_gods.groups
    strength = force.strength
    band = strength.band
    month_branch = Branch(pillars.month.branch)

    checks = detect_special_cases(force, structure)
    models: list[YongsinCandidateModel] = []
    warnings: list[str] = []
    is_pseudo_follow = False
    pseudo_model: YongsinCandidateModel | None = None

    # 특수격 우선
    if checks["dominant_one_element"].detected:
        # 오행 과다/부족은 월령 보정 세력 기준. 폴백도 보정이 섞인 effective 대신
        # '원점수' 환경 분포(일간 제외)를 쓴다(통근/투간/공망 중복 반영 방지).
        fe = force.five_elements
        sas = fe.season_adjusted_element_strength or fe.distribution_environment
        strongest = max(sas, key=lambda e: sas[e])
        models.append(YongsinCandidateModel(
            model_type="dominant_one_element", label="전왕/일행득기형",
            yongsin=strongest, heesin=_e(g["output"]),
            confidence=round(checks["dominant_one_element"].confidence, 4),
            reasons=["특정 오행이 압도적 → 왕한 흐름을 순행", "정면으로 극하는 오행은 기신"],
        ))
    elif checks["follow_structure"].detected:
        detail = checks["follow_structure"].detail or ""
        is_pseudo_follow = detail.startswith("pseudo")
        sp_follow = _strongest_pressure(groups)
        follow_el = g[sp_follow]
        subtype = _FOLLOW_SUBTYPE[sp_follow]
        follow_model = YongsinCandidateModel(
            model_type="follow_structure",
            label=("가종격(假從)·" + subtype) if is_pseudo_follow else subtype,
            yongsin=_e(follow_el), gisin=_e(g["peer"]),
            confidence=round(checks["follow_structure"].confidence, 4),
            reasons=(
                [f"극신약·무근 → 가장 강한 세력({subtype})에 순응", "억지로 돕는 비겁/인성은 기신"]
                + (
                    ["인성이 약하게 남아 가종(假從) — 운에서 비겁·인성 입운 시 파격, 검증 필요"]
                    if is_pseudo_follow else []
                )
            ),
        )
        if is_pseudo_follow:
            # 가종: 억부(印·比)를 1차 후보로 정상 산출, 종격(순응)은 병기(비집계·검증 위임).
            models.extend(_weak_band_models(g, groups, strength, force))
            pseudo_model = follow_model
            warnings.append(
                "pseudo_follow(가종): 억부(印·比)와 종격(순응)이 경쟁 — 사용자 검증 필요"
            )
        else:
            models.append(follow_model)
    elif band in _WEAK:
        models.extend(_weak_band_models(g, groups, strength, force))
    elif band in _STRONG:
        if _resource_overload(groups):
            if geokguk.main_structure in ("정인격", "편인격"):
                models.append(_resource_pattern_officer_model(g, strength))
            else:
                models.append(_resource_excess_model(g, strength))  # 인성과다 → 財損印
        elif _bigyeob_overload(groups):
            models.append(_bigyeob_rob_model(g, strength))  # 비겁과다 → 군겁쟁재(관성 제겁)
        else:
            models.append(_eokbu_strong_model(g, strength))
    else:  # 중화권 — 경쟁 모델 강제 + 검증
        models.append(_support_model(g, strength))
        models.append(_eokbu_strong_model(g, strength))
        # 중화신강 + 뚜렷한 인성과다 + 조후·병증 비우선일 때만 財損印을 '경쟁 후보'로 조건부 추가.
        # (곧바로 확정하지 않고 축가중·신뢰도 경쟁에 맡긴다 — 중화권 안전성 우선.)
        if (
            band == "중화신강"
            and _resource_overload_strict(groups)
            and not _johu_or_disease_active(month_branch, geokguk)
        ):
            models.append(_resource_excess_model(g, strength))
            warnings.append("neutral_zone: 인성과다(財損印) 후보 조건부 추가")
        warnings.append("neutral_zone: 경쟁 모델 동시 제시, 사용자 검증 필요")

    # 조후: _johu_model이 한습(亥子丑)·조열(巳午未)만 모델을 내므로(辰·戌은 None) 그대로 사용.
    # (丑=한겨울·未=한여름은 土월이라도 조후가 핵심 — 월령오행으로 걸러내면 안 됨.)
    johu = _johu_model(month_branch, g)
    if johu is not None:
        models.append(johu)
    # 격국(상신)·병약(약신) 보정 축 — 용신을 단독 확정하지 않고 후보 우선순위만 조정.
    pattern = _pattern_model(geokguk, g)
    if pattern is not None:
        models.append(pattern)
    # 인성과다면 '인성(印)을 약신으로 쓰는 병약'은 역효과 → 제외.
    suppress_resource = _resource_overload(groups)
    for dis in _disease_models(geokguk, g):
        if suppress_resource and dis.yongsin == _e(g["resource"]):
            continue
        models.append(dis)
    if checks["bridge_required"].detected:
        det = checks["bridge_required"].detail or ""
        warnings.append(f"통관 가능 구조: {det}")
        # 통관 오행이 약하면(약신) 실제 용신 후보로 승격(보정 축에서 경쟁).
        if "통관용신=" in det:
            med = det.split("통관용신=")[1]
            models.append(YongsinCandidateModel(
                model_type="bridge_tonggwan", label="통관용신형",
                yongsin=med, confidence=0.5,
                reasons=[
                    f"상극({det.split('|')[0]})을 상생으로 잇는 통관 오행 {med}",
                    "약한 통관 오행을 약신으로 보강",
                ],
                is_auxiliary=True,
            ))
    if checks["isolation_health"].detected:
        warnings.append(f"고립/병약 리스크: {checks['isolation_health'].detail} (건강 레이어)")

    # 동적 축 가중치(상황별) — 격국/조후/병약을 '보정 레이어'로 반영, 신약은 억부 우선.
    # 가종(pseudo)은 special 단독 주도가 아니라 억부와 경쟁시키므로 special 취급에서 제외.
    special = checks["dominant_one_element"].detected or (
        checks["follow_structure"].detected and not is_pseudo_follow
    )
    axis_weights = _select_axis_weights(
        band, month_branch, geokguk, special,
        bridge_required=checks["bridge_required"].detected,
    )

    def _w(model_type: str) -> float:
        return axis_weights.get(_axis_of(model_type), 0.2)

    # 후보 통합: 용신/희신 → useful, 기신/구신 → unfavorable. 점수 = 모델 신뢰도 × 축 가중치.
    useful: dict[str, tuple[float, str, str]] = {}
    unfavorable: dict[str, tuple[float, str, str]] = {}

    def _put(table: dict[str, tuple[float, str, str]], el: str | None,
             score: float, model: str, role: str) -> None:
        if el and score > table.get(el, (0.0, "", ""))[0]:
            table[el] = (score, model, role)

    for m in models:
        w = _w(m.model_type)
        _put(useful, m.yongsin, m.confidence * w, m.model_type, "yongsin")
        _put(useful, m.heesin, m.confidence * w * 0.85, m.model_type, "heesin")
        _put(unfavorable, m.gisin, m.confidence * w, m.model_type, "gisin")
        _put(unfavorable, m.gusin, m.confidence * w * 0.9, m.model_type, "gusin")

    # 축별 기여 요약(어느 축이 어떤 오행을 얼마로 밀었는가).
    axes_summary: list[dict] = []
    for axis in ("special", "bridge", "eokbu", "johu", "pattern", "disease"):
        contrib = [
            (m.yongsin, m.confidence * axis_weights.get(axis, 0.0))
            for m in models if _axis_of(m.model_type) == axis and m.yongsin
        ]
        if contrib:
            top_el, top_sc = max(contrib, key=lambda x: x[1])
            axes_summary.append({
                "axis": axis, "weight": round(axis_weights.get(axis, 0.0), 3),
                "top_element": top_el, "score": round(top_sc, 4),
            })
    axes_summary.sort(key=lambda a: a["score"], reverse=True)  # 기여 점수 내림차순

    # 부적격 원소 강등(용·희 → 불리).
    def _demote(el: str | None, tag: str) -> None:
        if el and el in useful:
            sc = useful.pop(el)
            _put(unfavorable, el, sc[0] * 0.9, sc[1], tag)

    # ① 조후 역행(한습 水 / 조열 火)은 용·희 부적격.
    _demote(_climate_harmful(month_branch, force), "climate_demote")
    # ② 극파 무력: 용/희 원소가 그것을 극하는 그룹에게 압도(>3배·최강군)당하면 강등
    #    (재다→인성, 군겁→재성, 인성과다→식상, 상관견관→관성 등 일괄).
    #    단 비겁(일간 동기·방조 유효)·조후 필요 원소(한습 火/조열 水)는 보존.
    _ctrl_grp = {"wealth": "peer", "resource": "wealth", "output": "resource", "officer": "output"}
    _johu_need = (
        _e(Element.FIRE) if month_branch in _COLD_MONTHS
        else _e(Element.WATER) if month_branch in _HOT_MONTHS else None
    )
    _el2grp = {str(v): k for k, v in g.items()}
    _mx = max(groups.values()) if groups else 0.0
    for _el in list(useful):
        if _el == _johu_need:
            continue
        _grp = _el2grp.get(_el)
        _ctrl = _ctrl_grp.get(_grp or "")
        if _grp is None or _ctrl is None:
            continue
        if groups[_ctrl] > groups[_grp] * 3 and groups[_ctrl] >= _mx and groups[_ctrl] > 0:
            _demote(_el, f"overwhelmed_by_{_ctrl}")

    useful_sorted = sorted(
        useful.items(), key=lambda kv: (kv[1][2] == "yongsin", kv[1][0]), reverse=True
    )[:2]
    unfav_sorted = sorted(unfavorable.items(), key=lambda kv: kv[1][0], reverse=True)[:2]
    useful_candidates = [
        ElementCandidate(element=e, score=round(s, 4), model=mdl, reason=role)
        for e, (s, mdl, role) in useful_sorted
    ]
    unfavorable_candidates = [
        ElementCandidate(element=e, score=round(s, 4), model=mdl, reason=role)
        for e, (s, mdl, role) in unfav_sorted
    ]

    # 확정 정책: 검증 전에는 candidate. 단일 모델·고신뢰·특수격 없음·경쟁 미존재면 probable.
    any_special = any(c.detected for c in checks.values())
    competing = len(useful_candidates) >= 2 and (
        useful_candidates[0].score - useful_candidates[1].score < 0.12
    )
    if len(models) == 1 and strength.confidence >= 0.7 and not any_special and not competing:
        status = "probable"
    else:
        status = "candidate"

    # selected_model/confidence는 실제 top 용신을 만든 모델로 보고(첫 생성 모델 아님).
    model_conf = {m.model_type: m.confidence for m in models}
    top_model = useful_candidates[0].model if useful_candidates else (
        models[0].model_type if models else None
    )
    # 용·희·기·구·한 최종 배정: 용신 기준 생극 구조로 1개씩 분할.
    yongsin_el = next(
        (e for e, (_s, _mdl, role) in useful_sorted if role == "yongsin"),
        useful_candidates[0].element if useful_candidates else None,
    )
    roles = _classify_roles(g, groups, band, useful, unfavorable, yongsin_el)
    if top_model == "bridge_tonggwan" and yongsin_el:
        roles = _classify_bridge_roles(
            g, groups, checks["bridge_required"].detail, useful, yongsin_el
        )
    elif (
        top_model == "support_day_master"
        and band in _WEAK
        and groups.get("peer", 0.0) <= 0.0
        and yongsin_el == _e(g["peer"])
    ):
        roles = {
            "yongsin": _e(g["peer"]),
            "heesin": _e(g["resource"]),
            "gisin": _e(g["output"]),
            "gusin": _e(g["wealth"]),
            "hansin": _e(g["officer"]),
        }
    final = {
        **roles,
        "confidence": round(model_conf.get(top_model or "", 0.0), 4),
        "selected_model": top_model,
    }

    # 가종(pseudo) 종격 모델은 집계에 넣지 않고 후보 목록에만 병기(억부 1차 결과는 유지).
    if pseudo_model is not None:
        models.append(pseudo_model)

    # 유통(流通) 흐름 점수 — 정보성. 신약이라도 상생 순환이 원활하면 완화 해석 메모.
    flow = _circulation(force)
    if flow["smooth"] and band in _WEAK:
        warnings.append(
            f"유통 양호(상생 고리 {flow['sheng_links']}/5): 신약이나 오행 순환 원활 — "
            "고립 적고 유연·적응형(신약 정도 완화 해석)"
        )

    return AggregatedYongsinResult(
        status=status,
        special_case_checks=checks,
        candidate_models=models,
        useful_candidates=useful_candidates,
        unfavorable_candidates=unfavorable_candidates,
        axis_weights=axis_weights,
        axes=axes_summary,
        final=final,
        flow_circulation=flow,
        requires_validation=True,
        warnings=warnings,
    )
