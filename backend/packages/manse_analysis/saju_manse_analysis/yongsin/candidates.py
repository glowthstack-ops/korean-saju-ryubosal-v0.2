"""용신 후보 모델 산출 및 통합.

원칙: 부족 오행을 자동 용신 처리하지 않고, 신약/신강을 일률 처리하지 않으며,
특수격을 억부보다 먼저 검사한다. 최초 status 는 candidate (검증 전 calibrated 금지).
"""

from __future__ import annotations

from saju_shared_types.analysis import ForceAnalysis
from saju_shared_types.constants import (
    BRANCH_CLASHES,
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
    ElementRole,
    YongsinCandidateModel,
)

from ..relations.hap_modes import resolve_stem_hap
from .johu_dict import load_johu_table
from .operational_role_config import (
    CLIMATE_HARMFUL_REASON,
    CONDITION_TEMPLATES,
    GYEOKGAK_ALLOWLIST,
    OFFICER_HAP_REASON,
    OPERABILITY_PENALTY,
    OPERABILITY_REASON,
    OPERATIONAL_ROLE_CLASS,
    TEN_GOD_HAP_MODE_PHRASE,
    TEN_GOD_HAP_REASON,
)
from .role_realization import (
    _ROLE_KEYS,
    _WEAK,
    RoleRealizationChartContext,
    _e,
    resolve_realized_roles,
)
from .special_cases import detect_special_cases

# 격각(隔位, 비인접) 판정용 인접 자리쌍 — 年月·月日·日時 만 인접. 나머지(年日·年時·月時)=격각.
_ADJ_POSITION_PAIRS = frozenset({
    frozenset({"year", "month"}),
    frozenset({"month", "day"}),
    frozenset({"day", "hour"}),
})

# 2계층 역할(YONGSIN_OPERATIONAL_ROLE_SPEC) — 한글 라벨(키 순서 `_ROLE_KEYS` 는
# role_realization 이 SSOT).
_ROLE_KO = {
    "yongsin": "용신", "heesin": "희신", "gisin": "기신",
    "gusin": "구신", "hansin": "한신",
}

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
    "food_rescue": "eokbu",  # 화인통관(偏印奪食/印旺克食 구제) — 財損印과 같은 축에서 경쟁
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


def _classify_roles(yongsin_el: str | None) -> dict[str, str | None]:
    """용신 기준 생극 순환으로 희·기·구·한을 1개씩 배정(用喜忌仇閑 5오행 분할).

    canonical 정의를 따른다 — 용신을 중심으로 오행 상생·상극이 한 바퀴 돌며 5역할이 결정된다.
      - 희신: 용신을 생하는 오행(生용신).
      - 기신: 용신을 극하는 오행(克용신) — 항상. 용신을 직접 깨는 오행이므로 강약과 무관.
      - 구신: 기신을 생하는 오행(生기신). 기신을 돕고 희신을 극한다.
      - 한신: 용신이 생하는 오행(나머지).
    신강·신약은 어느 십성을 용신으로 뽑느냐에서 이미 반영되므로, 역할 배정 단계에서는
    생극 순환만으로 정합성을 유지한다(용신을 극하는 오행이 한신으로 새는 모순 방지 — 예:
    신강 戊土 재격 용신 水에서 土克水의 土는 한신이 아니라 기신, 과다 인성 火는 구신).
    통관(bridge)·종격/직접보강은 순환을 따르지 않으므로 호출부에서 별도 배정한다.
    """
    if not yongsin_el:
        return {k: None for k in ("yongsin", "heesin", "gisin", "gusin", "hansin")}
    y = Element(yongsin_el)
    gisin = next(_e(x) for x in Element if CONTROLS[x] == y)            # 극용신
    heesin = next(_e(x) for x in Element if GENERATES[x] == y)          # 생용신
    gusin = next(_e(x) for x in Element if GENERATES[x] == Element(gisin))  # 생기신
    hansin = _e(GENERATES[y])                                          # 용신생 (나머지)
    return {
        "yongsin": yongsin_el,
        "heesin": heesin,
        "gisin": gisin,
        "gusin": gusin,
        "hansin": hansin,
    }


def _role_by_element(role_map: dict[str, str | None]) -> dict[str, str]:
    """{역할키: 오행} → {오행: 역할키} 역인덱스(None 오행은 제외)."""
    return {element: role_key for role_key, element in role_map.items() if element}


def _operational_role_map(
    selected_model: YongsinCandidateModel | None,
    canonical_roles: dict[str, str | None],
    *,
    adopt_model_map: bool,
) -> dict[str, str | None]:
    """작동 역할맵: 선택 모델이 5역할 완비면 그 자체맵, 아니면 canonical 폴백.

    Phase 0 — 모델 자체 역할맵 존중만 한다(조후 강등·합·작동성 보정은 Phase 2~4).
    부분맵 모델(johu/pattern/disease/bridge/dominant/follow 등 일부 역할 None)은
    canonical(= 현행 final 5역할)을 그대로 써 None 역할이 새지 않도록 한다.

    adopt_model_map=False 이면(=final 이 통관/부일간 특수분기로 정적 순환을 의도적으로
    교정한 경우) 모델 자체맵 대신 canonical 을 쓴다 — 특수분기의 교정을 되돌리지 않기 위함.
    """
    if (
        adopt_model_map
        and selected_model is not None
        and all(getattr(selected_model, k) for k in _ROLE_KEYS)
    ):
        return {k: getattr(selected_model, k) for k in _ROLE_KEYS}
    return dict(canonical_roles)


def _build_operational_roles(
    canonical_roles: dict[str, str | None],
    operational_map: dict[str, str | None],
) -> list[ElementRole]:
    """canonical/operational 역할맵을 오행별 ElementRole 목록으로 직렬화."""
    canonical_by_element = _role_by_element(canonical_roles)
    operational_by_element = _role_by_element(operational_map)
    roles: list[ElementRole] = []
    for element, canonical_key in canonical_by_element.items():
        operational_key = operational_by_element.get(element, canonical_key)
        roles.append(
            ElementRole(
                element=element,
                canonical_role=_ROLE_KO[canonical_key],
                operational_role=_ROLE_KO[operational_key],
            )
        )
    return roles


def _overloaded_element(groups: dict[str, float], g: dict[str, Element]) -> str | None:
    """원국에서 과다(병)로 작동하는 십성의 오행(없으면 None). 기존 과다 판정 함수만 사용."""
    if _officer_heavy(groups):
        return _e(g["officer"])
    if _output_heavy(groups):
        return _e(g["output"])
    if _resource_overload(groups):
        return _e(g["resource"])
    if _bigyeob_overload(groups):
        return _e(g["peer"])
    return None


def _dedupe(items: list[str]) -> list[str]:
    """기존 순서를 보존하며 중복 제거."""
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


_NOTE_PROVENANCE = " (base_model_role="


def _compose_note(
    body_sentences: list[str], base_role: str, canon_role: str, sources: list[str]
) -> str:
    """서술 본문 + 합성 출처(base/canonical 역할·synthesized_by)를 고정 포맷으로 결합."""
    body = " ".join(s for s in body_sentences if s).strip()
    suffix = (
        f"(base_model_role={base_role}; canonical_role={canon_role}; "
        f"synthesized_by={'+'.join(sources)})"
    )
    return f"{body} {suffix}".strip() if body else suffix


def _parse_note(note: str | None) -> tuple[list[str], list[str]]:
    """기존 note 를 (서술 본문 문장, synthesized_by 출처)로 분해. 출처 미상이면 ([note], [])."""
    if not note or _NOTE_PROVENANCE not in note:
        return ([note] if note else []), []
    head, _, tail = note.partition(_NOTE_PROVENANCE)
    sources = (
        tail.split("synthesized_by=")[1].rstrip(")").split("+")
        if "synthesized_by=" in tail else []
    )
    return ([head] if head else []), sources


def _with_condition(
    er: ElementRole,
    label: str,
    canonical_by_element: dict[str, str],
    operational_by_element: dict[str, str],
    synthesized_by: list[str],
    extra_negative: list[str] | None = None,
) -> ElementRole:
    """ElementRole 을 조건부/합성 라벨로 재구성 + 템플릿 조건문 + 합성 출처를 note 에 기록.

    synthesized_by 는 호출부에서 고정 순서로 전달한다(note 안정성 — 예: overload_condition+
    climate_harmful). negative_when 은 템플릿 + extra 를 순서 보존하며 dedupe 한다.
    """
    tmpl = CONDITION_TEMPLATES[label]
    base_role = _ROLE_KO.get(operational_by_element.get(er.element, ""), "?")
    canon_role = _ROLE_KO.get(canonical_by_element.get(er.element, ""), "?")
    return ElementRole(
        element=er.element,
        canonical_role=er.canonical_role,
        operational_role=label,
        positive_when=list(tmpl["positive_when"]),
        negative_when=_dedupe(list(tmpl["negative_when"]) + list(extra_negative or [])),
        note=_compose_note([str(tmpl["note"])], base_role, canon_role, synthesized_by),
    )


def _enrich_element(
    er: ElementRole,
    canonical_by_element: dict[str, str],
    operational_by_element: dict[str, str],
    *,
    add_positive: list[str],
    add_negative: list[str],
    add_note: list[str],
    add_source: str,
) -> ElementRole:
    """기존 ElementRole 의 operational_role(라벨)은 유지하고 조건문·note 출처만 보강한다.

    조건부 라벨이 이미 있으면 그 본문/출처에 누적(synthesized_by 끝에 add_source 추가 — 고정 순서),
    plain 라벨이면 note 를 새로 만든다. positive/negative_when 은 순서 보존 dedupe.
    """
    body, sources = _parse_note(er.note)
    body = body + add_note
    sources = _dedupe(sources + [add_source])
    base_role = _ROLE_KO.get(operational_by_element.get(er.element, ""), "?")
    canon_role = _ROLE_KO.get(canonical_by_element.get(er.element, ""), "?")
    return ElementRole(
        element=er.element,
        canonical_role=er.canonical_role,
        operational_role=er.operational_role,  # ★ 라벨 불변(Phase 3 DP2)
        positive_when=_dedupe(list(er.positive_when) + add_positive),
        negative_when=_dedupe(list(er.negative_when) + add_negative),
        note=_compose_note(body, base_role, canon_role, sources),
    )


def _annotate_overload_conditions(
    roles: list[ElementRole],
    canonical_roles: dict[str, str | None],
    operational_map: dict[str, str | None],
    groups: dict[str, float],
    g: dict[str, Element],
) -> list[ElementRole]:
    """과다(병) 기반 조건부 라벨 부여(Phase 1).

    - 과다 십성이면서 canonical 희신(生용신)인 오행 → "조건부 희신/병"(이론상 희신 + 실제 병).
    - 과다 오행을 극하는 canonical 구신/기신 오행 → "조건부 제살보조".
    조후(_climate_harmful)는 쓰지 않는다(Phase 2). 호출부에서 model_map 채택 케이스에만 적용한다.
    """
    over_el = _overloaded_element(groups, g)
    if over_el is None:
        return roles
    canonical_by_element = _role_by_element(canonical_roles)
    operational_by_element = _role_by_element(operational_map)
    out: list[ElementRole] = []
    for er in roles:
        el = er.element
        if el == over_el and canonical_by_element.get(el) == "heesin":
            out.append(_with_condition(
                er, "조건부 희신/병", canonical_by_element, operational_by_element,
                synthesized_by=["overload_condition"],
            ))
        elif el == over_el and canonical_by_element.get(el) == "hansin":
            # 희신=과다(병) 교정으로 병 오행이 한신으로 강등된 케이스(살중용인의 관살 등) —
            # 중립 한신이 아니라 '중첩 유입 시 기신성'인 조건부 한신으로 표기(점수 불변).
            out.append(_with_condition(
                er, "조건부 한신/병", canonical_by_element, operational_by_element,
                synthesized_by=["overload_condition"],
            ))
        elif (
            CONTROLS[Element(el)] == Element(over_el)
            and canonical_by_element.get(el) in ("gusin", "gisin")
        ):
            out.append(_with_condition(
                er, "조건부 제살보조", canonical_by_element, operational_by_element,
                synthesized_by=["overload_condition"],
            ))
        else:
            out.append(er)
    return out


def _annotate_climate_conditions(
    roles: list[ElementRole],
    month_branch: Branch,
    force: ForceAnalysis,
    canonical_roles: dict[str, str | None],
    operational_map: dict[str, str | None],
) -> list[ElementRole]:
    """조후 가드(_climate_harmful)를 operational 역할에 연결(Phase 2).

    - climate_harmful(한습 水 / 조열 火)이 operational 희신 → "조건부 희신/병"(한습/조열 사유).
      이미 "조건부 희신/병"(Phase 1 과다)이면 한습 negative_when 추가 + 출처 병합.
    - climate_need(한습→火 / 조열→水)이 operational 희신/한신 → "조후보조신" 격상.
    harmful is None(조후 병 미감지)이면 격상·강등 모두 no-op. model_map 채택 케이스에서만 호출.
    """
    harmful = _climate_harmful(month_branch, force)
    if harmful is None:
        return roles
    if month_branch in _COLD_MONTHS:
        need, direction = _e(Element.FIRE), "cold"
    else:  # _HOT_MONTHS (harmful is not None 이므로 둘 중 하나)
        need, direction = _e(Element.WATER), "hot"
    canonical_by_element = _role_by_element(canonical_roles)
    operational_by_element = _role_by_element(operational_map)
    climate_neg = [CLIMATE_HARMFUL_REASON[direction]]
    out: list[ElementRole] = []
    for er in roles:
        el = er.element
        if el == need and er.operational_role in ("희신", "한신"):
            out.append(_with_condition(
                er, "조후보조신", canonical_by_element, operational_by_element,
                synthesized_by=["climate_need"],
            ))
        elif el == harmful and er.operational_role in ("조건부 희신/병", "조건부 한신/병"):
            # 과다(병) 라벨에 조후 역행 사유를 병합(라벨 유지) — 희신/한신 강등형 공통.
            out.append(_with_condition(
                er, er.operational_role, canonical_by_element, operational_by_element,
                synthesized_by=["overload_condition", "climate_harmful"],
                extra_negative=climate_neg,
            ))
        elif el == harmful and er.operational_role == "희신":
            out.append(_with_condition(
                er, "조건부 희신/병", canonical_by_element, operational_by_element,
                synthesized_by=["climate_harmful"], extra_negative=climate_neg,
            ))
        else:
            out.append(er)
    return out


def _ten_god_hap_placement(
    acc: dict[str, list[str]], domain: str, mode: str, role_class: str
) -> None:
    """官 외 십성 합 맥락을 role class 별로 positive/negative/note 에 배치(#7).

    favorable=유익 작용 묶임/지연(negative), unfavorable=병/부담 완화(positive·contend negative),
    conditional=단순 길흉화 금지·note 중심(쟁합만 negative), neutral=note. transform=note only.
    """
    phrase = f"{domain} {TEN_GOD_HAP_MODE_PHRASE[mode]}"
    if mode == "transform":
        acc["note"].append(phrase)
        return
    if role_class == "favorable":
        acc["neg"].append(f"{phrase} — 유익 작용 지연·불안정")
    elif role_class == "unfavorable":
        if mode == "contend":
            acc["neg"].append(f"{phrase} — 불안정")
        else:  # bind/away
            acc["pos"].append(f"{phrase} — 부담/병 묶여 완화 가능")
    elif role_class == "conditional":
        acc["note"].append(f"{phrase} — 조건부 역할: 단순 길흉화 금지(완화·지연 양면)")
        if mode == "contend":
            acc["neg"].append(f"{phrase} — 불안정")
    else:  # neutral
        acc["note"].append(phrase)


def _annotate_ten_god_hap_context(
    roles: list[ElementRole],
    pillars: FourPillarsResult,
    g: dict[str, Element],
    canonical_roles: dict[str, str | None],
    operational_map: dict[str, str | None],
) -> list[ElementRole]:
    """官 외 십성(財/印/食傷/比劫) 합 맥락 주석(#7). 라벨 불변 — note·조건만 enrich.

    官殺은 Phase 3 officer_hap 가 처리하므로 제외(중복 방지). 합화 confirmed 라도 role 전환·세력
    재산정 없이 note 만(transform). favorability 는 canonical 기준. 배치는 element 의 operational
    role class 로 결정(conditional 은 단순 길흉화 금지·note 중심).
    """
    el2role = {_e(v): k for k, v in g.items()}
    canonical_by = _role_by_element(canonical_roles)
    operational_by = _role_by_element(operational_map)
    fav = {el: _ROLE_KO[k] for el, k in canonical_by.items()}
    role_label = {er.element: er.operational_role for er in roles}

    acc: dict[str, dict[str, list[str]]] = {}
    for r in resolve_stem_hap(pillars, fav):
        modes: set[str] = set()
        if r.hap_mode == "transform":
            modes.add("transform")
        elif r.hap_mode == "bind":
            modes.add("bind")
        if r.contend:
            modes.add("contend")
        if r.direction == "away":
            modes.add("away")
        if not modes:
            continue
        for a in r.affected:
            grp = el2role.get(a.element)
            if grp is None or grp == "officer":  # 官殺은 Phase 3
                continue
            domain = TEN_GOD_HAP_REASON.get(grp)
            if domain is None:
                continue
            role_class = OPERATIONAL_ROLE_CLASS.get(
                role_label.get(a.element, ""), "neutral"
            )
            bucket = acc.setdefault(a.element, {"pos": [], "neg": [], "note": []})
            for mode in modes:
                _ten_god_hap_placement(bucket, domain, mode, role_class)

    if not acc:
        return roles
    return [
        _enrich_element(
            er, canonical_by, operational_by,
            add_positive=_dedupe(acc[er.element]["pos"]),
            add_negative=_dedupe(acc[er.element]["neg"]),
            add_note=_dedupe(acc[er.element]["note"]),
            add_source="ten_god_hap",
        ) if er.element in acc else er
        for er in roles
    ]


def _pillar_list(pillars: FourPillarsResult) -> list:
    """원국 주(년월일+시). 시주 없으면 3주."""
    out = [pillars.year, pillars.month, pillars.day]
    if pillars.hour is not None:
        out.append(pillars.hour)
    return out


def _gyeokgak_operability_factors(
    yongsin_el: str, pillars: FourPillarsResult
) -> list[tuple[str, float, str]]:
    """격각(비인접) 형/해 통관손상 allowlist 적용(Phase 4b). (factor, weight, reason) 목록.

    이벤트/관계 판정은 미수정 — operability 전용. 인접쌍(年月·月日·日時)은 이벤트 레이어 영역이라
    제외하고 비인접(격각)만 본다. 동일 factor 는 1회만(중복 子/卯 무관).
    """
    pos_of: dict[str, list[str]] = {}
    for pos, p in (
        ("year", pillars.year), ("month", pillars.month),
        ("day", pillars.day), ("hour", pillars.hour),
    ):
        if p is not None:
            pos_of.setdefault(p.branch, []).append(pos)
    out: list[tuple[str, float, str]] = []
    for entry in GYEOKGAK_ALLOWLIST:
        if yongsin_el not in entry["yongsin_elements"]:
            continue
        b1, b2 = entry["branches"]
        gyeokgak = any(
            pa != pb and frozenset({pa, pb}) not in _ADJ_POSITION_PAIRS
            for pa in pos_of.get(b1, []) for pb in pos_of.get(b2, [])
        )
        if gyeokgak:
            out.append((entry["factor"], float(entry["weight"]), str(entry["reason"])))
    return out


def _yongsin_void_clash_factors(
    yongsin_el: str, pillars: FourPillarsResult
) -> list[tuple[str, float]]:
    """용신 통근 지지의 공망·충(#6a). 통근(지지)만 대상 — 투출 천간 자리는 후속.

    yongsin_void: 통근 지지가 **전부 공망**일 때만(solid root 1개라도 있으면 미적용 — 과발동 방지).
    yongsin_clash: 용신 통근 지지가 원국 다른 지지와 六沖일 때(원국 아무 곳 충이 아님). 통근이
    없으면 둘 다 미적용(no_root 만). relations·이벤트 미수정 — operability 전용.
    """
    ps = _pillar_list(pillars)
    roots = [p for p in ps if any(hs.element == yongsin_el for hs in p.hidden_stems)]
    out: list[tuple[str, float]] = []
    if not roots:
        return out
    if all(p.gongmang_hit for p in roots):
        out.append(("yongsin_void", OPERABILITY_PENALTY["yongsin_void"]))
    chart_branches = [Branch(p.branch) for p in ps]
    root_branches = {Branch(p.branch) for p in roots}
    if any(
        rb != ob and frozenset({rb, ob}) in BRANCH_CLASHES
        for rb in root_branches for ob in chart_branches
    ):
        out.append(("yongsin_clash", OPERABILITY_PENALTY["yongsin_clash"]))
    return out


_ISOLATION_DAMAGE = {"yongsin_clash", "yongsin_void", "gyeokgak_zimao"}


def _yongsin_isolation_applies(
    yongsin_el: str, pillars: FourPillarsResult, existing_factors: list[str]
) -> bool:
    """용신 고립(#6b-1) — 보수적 4조건 AND. 과발동 방지를 위해 전부 충족할 때만 True.

    ①present(투간 or 통근) ②생조부재(生용신 오행이 천간·지장간 어디에도 없음) ③단일출처(용신
    오행 출처가 정확히 1개 — 천간+지지 동시 또는 통근 2개+면 고립 아님) ④손상동반(yongsin_clash/
    yongsin_void/gyeokgak_zimao 중 ≥1). distribution·세력 미변경 — operability 전용.
    """
    if not (_ISOLATION_DAMAGE & set(existing_factors)):  # ④ 손상 동반
        return False
    ps = _pillar_list(pillars)
    transmit_count = sum(1 for p in ps if p.stem_element == yongsin_el)
    root_count = sum(
        1 for p in ps if any(hs.element == yongsin_el for hs in p.hidden_stems)
    )
    if transmit_count + root_count != 1:  # ① present(≥1) + ③ 단일출처(정확히 1)
        return False
    heesin = _e(next(x for x in Element if GENERATES[x] == Element(yongsin_el)))
    saengjo = any(p.stem_element == heesin for p in ps) or any(
        hs.element == heesin for p in ps for hs in p.hidden_stems
    )
    return not saengjo  # ② 생조 부재


def _yongsin_bound_factor(
    yongsin_el: str,
    pillars: FourPillarsResult,
    canonical_roles: dict[str, str | None],
) -> bool:
    """용신 합반(#6b-2) — 용신 투출 천간이 bind(합반)/contend(쟁합)로 묶임.

    용신 미투출이면 False(no_transmit 영역). 合化 confirmed(transform)·합거(away)는 제외 —
    묶임/불안정만 본다. favorability 는 canonical 기준(Phase 3 일관·순환참조 방지). distribution·
    세력 미변경 — operability factor 만.
    """
    ps = _pillar_list(pillars)
    if not any(p.stem_element == yongsin_el for p in ps):  # ① 용신 투출 아님
        return False
    fav = {el: _ROLE_KO[k] for el, k in _role_by_element(canonical_roles).items()}
    for r in resolve_stem_hap(pillars, fav):
        if r.hap_mode == "transform" or r.direction == "away":  # 合化·합거 제외
            continue
        if (r.hap_mode == "bind" or r.contend) and any(
            a.element == yongsin_el for a in r.affected
        ):
            return True
    return False


def _compute_yongsin_operability(
    yongsin_el: str,
    pillars: FourPillarsResult,
    resource_el: str,
    canonical_roles: dict[str, str | None],
) -> tuple[float, list[str], list[str]]:
    """용신 작동성: 투간/통근·정편인(4a) + 격각 통관손상(4b) penalty(감점형, ≤1.0).

    정/편인은 ten_god(=Pillar.stem_ten_god) 기준. 印 용신이 투출했고 정인 없이 편인만일 때만
    pyeonin_only(印 투간無면 no_transmit 만, 중복 없음). 적용 순서 고정:
    no_transmit→no_root→pyeonin_only→격각(allowlist). round 는 최종 1회.
    반환: (operability, factor keys, 표시 사유 list).
    """
    ps = _pillar_list(pillars)
    transmitted = any(p.stem_element == yongsin_el for p in ps)
    rooted = any(hs.element == yongsin_el for p in ps for hs in p.hidden_stems)
    op = 1.0
    factors: list[str] = []
    reasons: list[str] = []
    if not transmitted:
        op *= 1.0 - OPERABILITY_PENALTY["no_transmit"]
        factors.append("no_transmit")
        reasons.append(OPERABILITY_REASON["no_transmit"])
    if not rooted:
        op *= 1.0 - OPERABILITY_PENALTY["no_root"]
        factors.append("no_root")
        reasons.append(OPERABILITY_REASON["no_root"])
    if yongsin_el == resource_el and transmitted:
        yong_gods = [p.stem_ten_god for p in ps if p.stem_element == yongsin_el]
        if "편인" in yong_gods and "정인" not in yong_gods:
            op *= 1.0 - OPERABILITY_PENALTY["pyeonin_only"]
            factors.append("pyeonin_only")
            reasons.append(OPERABILITY_REASON["pyeonin_only"])
    for factor, weight, reason in _gyeokgak_operability_factors(yongsin_el, pillars):
        op *= 1.0 - weight
        factors.append(factor)
        reasons.append(reason)
    for factor, weight in _yongsin_void_clash_factors(yongsin_el, pillars):  # #6a
        op *= 1.0 - weight
        factors.append(factor)
        reasons.append(OPERABILITY_REASON[factor])
    if _yongsin_isolation_applies(yongsin_el, pillars, factors):  # #6b-1
        op *= 1.0 - OPERABILITY_PENALTY["yongsin_isolation"]
        factors.append("yongsin_isolation")
        reasons.append(OPERABILITY_REASON["yongsin_isolation"])
    if _yongsin_bound_factor(yongsin_el, pillars, canonical_roles):  # #6b-2
        op *= 1.0 - OPERABILITY_PENALTY["yongsin_bound"]
        factors.append("yongsin_bound")
        reasons.append(OPERABILITY_REASON["yongsin_bound"])
    return round(op, 4), factors, reasons


def _with_operability(
    er: ElementRole, operability: float, factors: list[str], reasons: list[str]
) -> ElementRole:
    """용신 ElementRole 에 operability 수치·factor key·표시 사유(negative_when)를 부착."""
    return ElementRole(
        element=er.element,
        canonical_role=er.canonical_role,
        operational_role=er.operational_role,
        positive_when=list(er.positive_when),
        negative_when=_dedupe(list(er.negative_when) + reasons),
        note=er.note,
        operability=operability,
        operability_factors=list(factors),
    )


def _annotate_officer_hap_context(
    roles: list[ElementRole],
    pillars: FourPillarsResult,
    g: dict[str, Element],
    geokguk: GeokgukResult,
    canonical_roles: dict[str, str | None],
    operational_map: dict[str, str | None],
) -> list[ElementRole]:
    """官殺 합 맥락(합반/쟁합/합거/합화 + 관살혼잡)을 官殺 ElementRole 에 주석으로 보강(Phase 3).

    operational_role 라벨은 바꾸지 않고(DP2) note·positive/negative_when 만 enrich. 세력 재산정·
    분포 차감은 하지 않는다(Option A 영역). favorability 는 canonical/final 기준으로 넘긴다(DP3).
    배치 규칙(데굴님 추가조건 1~3): 합반/합화=positive·note, 쟁합/관살혼잡=negative,
    합거=note(官이 병이면 positive).
    """
    officer_el = _e(g["officer"])
    canonical_by_element = _role_by_element(canonical_roles)
    operational_by_element = _role_by_element(operational_map)
    fav = {el: _ROLE_KO[k] for el, k in canonical_by_element.items()}
    officer_role = next(
        (r.operational_role for r in roles if r.element == officer_el), None
    )
    officer_is_disease = officer_role == "조건부 희신/병"

    add_pos: list[str] = []
    add_neg: list[str] = []
    add_note: list[str] = []
    for r in resolve_stem_hap(pillars, fav):
        if not any(a.element == officer_el for a in r.affected):
            continue
        if r.hap_mode == "bind":
            add_pos.append(OFFICER_HAP_REASON["bind"])
        if r.hap_mode == "transform" and r.transform_tier == "confirmed":
            add_pos.append(OFFICER_HAP_REASON["transform_confirmed"])
        if r.contend:
            add_neg.append(OFFICER_HAP_REASON["contend"])
        if r.direction == "away":
            (add_pos if officer_is_disease else add_note).append(
                OFFICER_HAP_REASON["away"]
            )

    ev = geokguk.evaluation
    if ev is not None and "mixed_officer_killing" in ev.damage_types:
        add_neg.append(OFFICER_HAP_REASON["mixed_officer_killing"])

    if not (add_pos or add_neg or add_note):
        return roles  # 官 합·혼잡 없음 → no-op
    return [
        _enrich_element(
            r, canonical_by_element, operational_by_element,
            add_positive=_dedupe(add_pos), add_negative=_dedupe(add_neg),
            add_note=_dedupe(add_note), add_source="officer_hap",
        ) if r.element == officer_el else r
        for r in roles
    ]


def _semantic_tiebreak_key(
    el: str,
    yongsin_el: str,
    g: dict[str, Element],
    groups: dict[str, float],
    pillars: FourPillarsResult,
    force: ForceAnalysis,
    month_branch: Branch,
) -> tuple:
    """동점 후보 의미론 정렬키(감수 확정 2026-07-13 ③) — 클수록 우선.

    순서: ①dominant_need 일치(기후 축 직접 교정) ②주 병 직접 해결(과다 오행 극)
    ③주용신 보호(生용신) ④조후 악화 없음 ⑤생극 흐름 완성(용신 설기 경로)
    ⑥operability(통근) ⑦결정적 오행 순서. **점수·confidence·역할 불변 — 동점 후보의
    선택 순서만 결정하는 독립 정렬 레이어**이며, 전역 고정 역할 순위를 두지 않는다
    (극조열 명식은 climate_helper, 통관 명식은 mediator 가 앞서는 식으로 ①이 결정).
    """
    axes = _climate_axes(pillars, force)
    axis_key = str(axes["primary_climate_axis"]).removeprefix("severe_")
    corrective = _AXIS_CORRECTIVE.get(axis_key)
    matches_dominant_need = corrective is not None and Element(el) is corrective
    over_el = _overloaded_element(groups, g)
    resolves_disease = over_el is not None and CONTROLS[Element(el)] is Element(over_el)
    protects_yongsin = GENERATES[Element(el)] is Element(yongsin_el)
    not_worsen_climate = el != (_climate_harmful(month_branch, force) or "")
    completes_flow = GENERATES[Element(yongsin_el)] is Element(el)
    rooted = any(
        h.element == el
        for p in (pillars.year, pillars.month, pillars.day, pillars.hour)
        if p is not None
        for h in p.hidden_stems
    )
    # 마지막 키: 재현성 확보용 오행 순서(의미 판정이 모두 같을 때만 작동).
    deterministic = -sorted(_e(e) for e in Element).index(el)
    return (
        matches_dominant_need, resolves_disease, protects_yongsin,
        not_worsen_climate, completes_flow, rooted, deterministic,
    )


_TIEBREAK_REASONS = (
    "dominant_need 일치(기후 축 직접 교정)", "주 병(과다 오행) 직접 극",
    "주용신 보호(生용신)", "조후 악화 없음", "생극 흐름 완성(용신 설기)",
    "통근(operability)", "결정적 오행 순서",
)


def _classify_bridge_roles(
    g: dict[str, Element],
    groups: dict[str, float],
    detail: str | None,
    useful: dict[str, tuple[float, str, str]],
    yongsin_el: str,
    pillars: FourPillarsResult,
    force: ForceAnalysis,
    month_branch: Branch,
) -> tuple[dict[str, str | None], str | None]:
    """통관용신은 과다한 상극 축 사이를 잇는 오행이므로 억부식 극관계 배정을 쓰지 않는다.

    반환: (역할맵, 동점 타이브레이크 사유 또는 None). 희신 폴백에서 점수가 동일한
    후보들만 의미론 정렬(감수 ③)을 거친다 — 비동점 결과는 불변.
    """
    roles_of = {_e(v): k for k, v in g.items()}  # 오행 → 십성 역할
    elements = {_e(e) for e in Element}
    total = sum(groups.values()) or 1.0
    tiebreak_reason: str | None = None

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
        # sorted 순회 필수: set 순서는 프로세스 해시 시드에 따라 달라 max() 동점 시 결과가
        # 흔들린다(실측 — 1953-01-15 희신 火/木 플립). 결정적 순서로 고정한다.
        gisin = max(
            sorted(e for e in elements if e != yongsin_el and e != heesin),
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
            sorted(remaining_for_gusin),
            key=lambda el: groups.get(roles_of[el], 0.0) / total,
        ) if remaining_for_gusin else None

    if heesin is None:
        remaining_for_hee = sorted(elements - {yongsin_el, gisin, gusin})
        if remaining_for_hee:
            best_score = max(
                useful.get(el, (0.0, "", ""))[0] for el in remaining_for_hee
            )
            tied = [
                el for el in remaining_for_hee
                if useful.get(el, (0.0, "", ""))[0] == best_score
            ]
            if len(tied) <= 1:
                heesin = tied[0] if tied else None
            else:
                # 감수 ③: 동점만 의미론 정렬 — 점수·역할 불변, 사유 기록(재현성).
                keyed = sorted(
                    tied,
                    key=lambda el: _semantic_tiebreak_key(
                        el, yongsin_el, g, groups, pillars, force, month_branch
                    ),
                    reverse=True,
                )
                heesin = keyed[0]
                if len(keyed) > 1:
                    k0 = _semantic_tiebreak_key(
                        keyed[0], yongsin_el, g, groups, pillars, force, month_branch
                    )
                    k1 = _semantic_tiebreak_key(
                        keyed[1], yongsin_el, g, groups, pillars, force, month_branch
                    )
                    idx = next(
                        (i for i, (a, b) in enumerate(zip(k0, k1, strict=True)) if a != b),
                        len(_TIEBREAK_REASONS) - 1,
                    )
                    tiebreak_reason = (
                        f"동점 희신 타이브레이크: {heesin} 선택 — "
                        f"{_TIEBREAK_REASONS[min(idx, len(_TIEBREAK_REASONS) - 1)]}"
                        f" (경합: {'/'.join(keyed)})"
                    )

    hansin = next(
        (e for e in sorted(elements) if e not in {yongsin_el, heesin, gisin, gusin}), None
    )
    return {
        "yongsin": yongsin_el,
        "heesin": heesin,
        "gisin": gisin,
        "gusin": gusin,
        "hansin": hansin,
    }, tiebreak_reason


def _resource_excess_model(
    g: dict[str, Element],
    strength,
    operability_mult: float = 1.0,
    operability_notes: tuple[str, ...] = (),
) -> YongsinCandidateModel:
    """재성용신형(財損印): 인성과다 신강 → 재성으로 인성 제어, 관성으로 일간 억제.

    operability_mult 는 재성의 '단독 용신 완성도' 감점 계수(P1, 2026-07-13 데굴님 감수).
    무근·실령·피극 재성은 필요성(制印·成財)은 유지하되 단독 선택 능력만 낮춘다 —
    金 자체는 치료 경로 모델(food_rescue)의 희신으로 살아남는다.
    """
    conf = round(
        min(0.55 + max(strength.score - 50.0, 0.0) / 60, 0.9) * operability_mult, 4
    )
    return YongsinCandidateModel(
        model_type="wealth_breaks_resource",
        label="재성용신형(財損印·인성과다)",
        yongsin=_e(g["wealth"]), heesin=_e(g["officer"]),
        gisin=_e(g["resource"]), gusin=_e(g["peer"]), hansin=_e(g["output"]),
        confidence=conf,
        reasons=[
            "인성 과다 → 재성으로 인성 제어(財損印)",
            "관성으로 일간 억제·조후, 식상은 인성에 극당해 무력",
            *operability_notes,
        ],
    )


def _food_transparent_position(pillars: FourPillarsResult) -> str | None:
    """식신 '투간' 주(柱) 위치 — 없으면 None.

    상관 투간은 대상이 아니다(동일 규칙 자동 적용 금지 — 상관 구조는 별도 규칙 확정 전
    미발동, 데굴님 2026-07-13). 일간(day)은 투간 개념에서 제외.
    """
    for pos in ("month", "hour", "year"):  # 월간이 가장 강한 신호라 우선 탐색
        p = getattr(pillars, pos)
        if p is not None and p.stem_ten_god == "식신":
            return pos
    return None


def _output_disease(
    pillars: FourPillarsResult, groups: dict[str, float]
) -> tuple[str, list[str]] | None:
    """印이 食神을 억누르는 병 감지 — 특수형(偏印奪食)이 일반형(印旺克食)을 포함한다.

    2계층(중복 가산 금지, 데굴님 2026-07-13):
      - indirect_resource_robs_food(偏印奪食): 식신 투간 + '편인'과의 직접 접촉
        (같은 주 천간-지지 본기 대립이 최강 신호, 인접 주 천간 편인도 인정).
      - excessive_resource_controls_output(印旺克食): 접촉 없이 인성과다 + 식신 투간.
        正印 중심(편인 접촉 없음)은 이 낮은 강도로만 감지된다.
    전제: 인성과다(_resource_overload)는 호출부에서 이미 성립.
    반환: (kind, evidence 문구 목록) 또는 None(식신 미투간).
    """
    food_pos = _food_transparent_position(pillars)
    if food_pos is None:
        return None
    evidence = [f"{food_pos}간 식신 투간"]
    food_pillar = getattr(pillars, food_pos)
    # 같은 주 지지 본기가 편인 — 도식(偏印奪食) 직접 접촉의 최강 신호.
    if food_pillar.branch_main_ten_god == "편인":
        evidence.append(f"{food_pos}지 본기 편인 — 같은 주 내 偏印奪食 직접 대립")
        return "indirect_resource_robs_food", evidence
    # 인접 주 천간 편인 접촉.
    for pos in ("year", "month", "day", "hour"):
        p = getattr(pillars, pos)
        if p is None or pos == food_pos:
            continue
        if (
            p.stem_ten_god == "편인"
            and frozenset({pos, food_pos}) in _ADJ_POSITION_PAIRS
        ):
            evidence.append(f"{pos}간 편인 — 인접 천간 偏印奪食 접촉")
            return "indirect_resource_robs_food", evidence
    evidence.append("편인 직접 접촉 없음 — 일반 印旺克食(낮은 강도)")
    return "excessive_resource_controls_output", evidence


# 통관(비겁) 추가 가용량이 이 값 이상이면 '이미 충분' — 火 추가 승격 억제.
_MEDIATOR_SUFFICIENT = 0.45

# mediator 오행 자체가 계절 보정 분포에서 이 비율 이상이면 '부족한 통관재' 전제 붕괴.
_MEDIATOR_SATURATED = 0.25


def _mediator_promotion_veto(
    band: str, month_branch: Branch, mediator_el: Element, force: ForceAnalysis
) -> str | None:
    """화인통관 mediator(비겁) 주용신 승격 금지 사유 — 없으면 None.

    비겁 mediator는 일간 오행 자체라 다음 상황에서 승격이 병을 키운다
    (2026-07-13 데굴님 감수 — 1965-05-15 乙巳 辛巳 己巳 庚午 회귀 사례):
      ① 극신강 — 비겁 보강이 신강을 악화(태신강은 mediator 부족 시 허용 — 庚寅판 보존).
      ② mediator 오행 자체가 이미 과다(포화) — '부족한 통관재를 보충한다'는 전제 붕괴.
      ③ 조후 악화 — 조열월(巳午未) 土 mediator(건토 심화·金 매몰),
         한습월(亥子丑) 水 mediator(한기 심화).
    차단해도 병 감지 자체는 유효 — 財損印 등 다른 치료 후보가 경쟁을 이어받는다.
    """
    if band == "극신강":
        return "극신강 — 비겁 mediator 승격은 신강 악화(strength_aggravation)"
    fe = force.five_elements
    dist = fe.season_adjusted_element_strength or fe.distribution_environment
    total = sum(dist.values()) or 1.0
    if dist.get(mediator_el, 0.0) / total >= _MEDIATOR_SATURATED:
        return "통관재 자체가 이미 과다(mediator_already_saturated)"
    if month_branch in _HOT_MONTHS and mediator_el is Element.EARTH:
        return "조열월 土 mediator — 건토 심화·金 매몰(dry_earth_aggravation)"
    if month_branch in _COLD_MONTHS and mediator_el is Element.WATER:
        return "한습월 水 mediator — 한기 심화(climate_aggravation)"
    return None


def _additional_mediator_operability(
    pillars: FourPillarsResult, peer_el: Element
) -> tuple[float, list[str]]:
    """일간 자신을 '제외'한 추가 통관(비겁 오행) 가용량(0~1).

    일간의 존재는 구조의 주체일 뿐 '통관 오행이 충분히 공급됨'을 뜻하지 않는다
    (데굴님 감수 #4 — 일간 丙만 보고 노출 火 충분으로 오판 금지). 지장간 중·여기는
    잠재 상태(발아 단계)라 왕지·투간과 같은 활성도로 합산하지 않는다(감수 #2).
      - 천간 비견·겁재(일간 제외): +0.4/개 (노출 — 즉시 작동)
      - 지지 본기가 비겁 오행(왕지 통근): +0.35/개
      - 지장간 중·여기 비겁 오행(잠재): +0.10/개 (운·투출로 활성화 필요)
      - 월령 본기가 비겁 오행(득령): +0.2
    """
    score = 0.0
    factors: list[str] = []
    peer = _e(peer_el)
    for pos in ("year", "month", "hour"):  # day 천간 = 일간 자신 → 제외
        p = getattr(pillars, pos)
        if p is not None and p.stem_element == peer:
            score += 0.4
            factors.append(f"exposed_peer:{pos}")
    for pos in ("year", "month", "day", "hour"):
        p = getattr(pillars, pos)
        if p is None:
            continue
        for h in p.hidden_stems:
            if h.element != peer:
                continue
            if h.type == "main":
                score += 0.35
                factors.append(f"strong_branch:{pos}:{p.branch}")
            else:
                score += 0.10
                factors.append(f"rooted_latent:{pos}:{p.branch}")
    if pillars.month.branch_element == peer:
        score += 0.2
        factors.append("seasonal:month")
    return round(min(score, 1.0), 4), factors


def _wealth_standalone_operability(
    pillars: FourPillarsResult,
    g: dict[str, Element],
    month_branch: Branch,
    force: ForceAnalysis,
) -> tuple[float, tuple[str, ...]]:
    """재성의 '단독 용신 완성도' 계수(0~1)와 근거 — 필요성과 분리(데굴님 감수 #2).

    감지 신호(모두 원국 데이터): ①무근(지지 지장간에 재성 오행 전무) ②실령(월지 본기가
    재성이 극하는 오행 — 예: 봄철 金은 木 제어에 소모) ③일간 피극(재성 투간 주가 일간과
    인접해 극을 직접 받음). 무근이 아닐 때는 감점하지 않는다(진짜 財損印 보존).

    climate_need_preservation(2026-07-13 데굴님 감수 — 1965-05-15 회귀): 극단 한열월의
    조후 필요신(조열월 水 / 한습월 火)이 원국에 부재·미약하면 그것은 '결핍의 증거'이지
    필요도 감점 사유가 아니다 — canonical 감점을 걸지 않고, 무근·부재 감점은 작동성
    계층(Phase 4a operability no_root)에만 남긴다.
    """
    wealth = _e(g["wealth"])
    rooted = any(
        h.element == wealth
        for pos in ("year", "month", "day", "hour")
        for p in (getattr(pillars, pos),)
        if p is not None
        for h in p.hidden_stems
    )
    if rooted:
        return 1.0, ()
    johu_need = (
        _e(Element.WATER) if month_branch in _HOT_MONTHS
        else _e(Element.FIRE) if month_branch in _COLD_MONTHS else None
    )
    if wealth == johu_need:
        fe = force.five_elements
        dist = fe.season_adjusted_element_strength or fe.distribution_environment
        total = sum(dist.values()) or 1.0
        if dist.get(g["wealth"], 0.0) / total < 0.22:  # _climate_harmful 과 동일 임계
            return 1.0, (
                "조후 필요신 부재/미약 — 필요도 감점 미적용(climate_need_preservation), "
                "무근 감점은 작동성(operability) 계층에서만 반영",
            )
    mult = 0.55
    notes = ["재성 무근 — 단독 용신 완성도 낮음(필요성은 유지, 희신 후보로 존속)"]
    if pillars.month.branch_element == _e(CONTROLS[g["wealth"]]):
        mult *= 0.9
        notes.append("재성 실령(월령이 재성의 극 대상 — 제어에 소모)")
    dm_controls_wealth = CONTROLS[g["peer"]] == g["wealth"]
    if dm_controls_wealth and pillars.hour is not None and (
        pillars.hour.stem_element == wealth or pillars.year.stem_element == wealth
    ):
        mult *= 0.9
        notes.append("투간 재성이 왕한 일간 계열의 극에 노출")
    notes.append("土 생조·통근을 얻는 운에서 실질 작동(운 판정 참고)")
    return round(mult, 4), tuple(notes)


def _food_rescue_model(
    g: dict[str, Element],
    strength,
    kind: str,
    evidence: list[str],
    mediator_cap: float,
    pillars: FourPillarsResult,
) -> YongsinCandidateModel:
    """치료 경로 모델(食神 구제): 비겁(火)로 化印·통관해 木→火→土→金 식신생재를 복원.

    병 감지(偏印奪食/印旺克食)와 치료 경로 평가를 분리(데굴님 감수 #3) — 이 모델은
    치료 중재의 결과다: transform_resource(비겁)=주 치료, control_resource(재성)=보조
    (필요성 높음·작동성 낮음 → 희신), restore_output(식상)=보호 대상(5역할 분할상 한신,
    operational 주석으로 protected_output 보존).
    """
    special = kind == "indirect_resource_robs_food"
    conf = 0.62 if special else 0.55
    conf += min(max(strength.score - 50.0, 0.0) / 100, 0.12)  # 신강할수록 절실
    wealth = _e(g["wealth"])
    wealth_transparent = any(
        p is not None and p.stem_element == wealth
        for p in (pillars.year, pillars.month, pillars.hour)
    )
    if wealth_transparent:
        conf += 0.08  # 食透+財透 — 식신생재 경로가 천간에 성립
    if mediator_cap < 0.30:
        conf += 0.06  # 추가 통관 화력 절핍 — 보충 필요성 급증
    label = "화인통관형(偏印奪食 구제)" if special else "화인통관형(印旺克食)"
    subtype = "pyeonin_talsik" if special else "inwang_geuksik"
    return YongsinCandidateModel(
        model_type=f"food_rescue:{subtype}",
        label=label,
        yongsin=_e(g["peer"]), heesin=wealth,
        gisin=_e(g["resource"]), gusin=_e(g["officer"]), hansin=_e(g["output"]),
        confidence=round(min(conf, 0.88), 4),
        reasons=[
            *evidence,
            "비겁으로 化印·통관(木克土 → 木生火生土) — 식신 보호·생조",
            "재성은 制印·成財 희신(필요성 높음·원국 작동성 낮음 — 생조·통근 운에서 작동)",
            "관성은 과다 인성을 재생(官印相生 경로)해 구신",
            "식상은 보호 대상(protected_output) — 통관 성립 시 식신생재의 중추",
            "주의: 통관 오행 과다 시 무근 재성을 직접 극 — 상한 필요",
        ],
    )


def _disease_remedy_binding(
    pillars: FourPillarsResult,
    g: dict[str, Element],
    canonical_roles: dict[str, str | None],
) -> tuple[str, str] | None:
    """치료 오행(희신) 천간과 병 오행(기신) 천간의 합 — 이원 평가 신호(P3).

    乙庚合류: 합은 ①과다 병 천간의 직접 작동을 일부 구속(disease_attenuation,
    beneficial_binding)하면서 ②치료 천간 자신도 묶어 직접 제어력을 일부 낮춘다
    (remedy_operability). **설명 전용 — 점수·역할·confidence 에 반영하지 않는다**
    (score_delta 0, 데굴님 감수 2026-07-13). 동일 신호 소비 가드: 이 합 신호는 여기서만
    소비하며 모델 confidence(財損印/food_rescue)는 합을 점수화하지 않는다 — 중복 가산 없음.
    반환: (긍정 문구, 부정 문구) 또는 None(해당 합 없음/차단).
    """
    gisin_el = canonical_roles.get("gisin")
    heesin_el = canonical_roles.get("heesin")
    if not gisin_el or not heesin_el:
        return None
    fav = {el: _ROLE_KO[rk] for rk in _ROLE_KEYS if (el := canonical_roles.get(rk))}
    for r in resolve_stem_hap(pillars, fav):
        pair_els = {_e(STEM_ELEMENT[Stem(s)]) for s in r.pair}
        if pair_els != {gisin_el, heesin_el}:
            continue
        # 차단(간격극)·격위 약화도 방향성 참고로 기록하되 강도 한정어를 명시한다 —
        # 데굴님 감수: 단순 '庚 무력화'가 아니라 이원(구속 이득/자기 묶임) 방향성 보존.
        if r.blocked:
            grade = f" ({r.block_reason} 차단 — 실질 작용 제한, 방향성 참고)"
        elif r.weakened:
            grade = " (격위·저강도)"
        else:
            grade = ""
        pair_txt = "".join(r.pair)
        return (
            f"천간합 {pair_txt} — 과다 병({gisin_el}) 천간의 직접 작동 일부 구속"
            f"(beneficial_binding){grade}",
            f"천간합 {pair_txt} — 자신도 묶여 직접 제어력 일부 감소"
            f"(remedy_operability){grade} · 점수 불변(설명 전용)",
        )
    return None


def _annotate_food_rescue_context(
    roles: list[ElementRole],
    canonical_roles: dict[str, str | None],
    pillars: FourPillarsResult,
    g: dict[str, Element],
) -> list[ElementRole]:
    """화인통관(food_rescue) 채택 시 구조 주석 — 역할 라벨·세력 불변, note/조건만 보강.

    데굴님 감수(2026-07-13) 반영: ①용신(비겁)은 化印·통관·생식신이되 과다 시 무근 재성
    직접 극 상한 ②희신(재성)은 필요성/작동성 분리 ③한신(식상)은 '보호 대상'
    (protected_output) — 단순 중립이 아님 ④구신(관성)은 官印相生으로 병 재생 경로
    ⑤희신-기신 천간합은 이원 평가(구속=이득 / 자기 묶임=감소, 설명 전용).
    """
    by_element = _role_by_element(canonical_roles)
    binding = _disease_remedy_binding(pillars, g, canonical_roles)
    out: list[ElementRole] = []
    for er in roles:
        role_key = by_element.get(er.element)
        if role_key == "yongsin":
            out.append(er.model_copy(update={
                "positive_when": [
                    *er.positive_when,
                    "과다 인성을 소화(化印)하고 木克土를 木生火生土 통관으로 전환",
                ],
                "negative_when": [
                    *er.negative_when,
                    "통관 오행 과다 시 무근 재성(희신)을 직접 극 — 상한 필요",
                ],
            }))
        elif role_key == "heesin":
            out.append(er.model_copy(update={
                "note": "制印·成財 — 필요성 높음, 원국 작동성 낮음(무근): "
                        "생조·통근을 얻는 운에서 강하게 작동",
                **({
                    "positive_when": [*er.positive_when, binding[0]],
                    "negative_when": [*er.negative_when, binding[1]],
                } if binding else {}),
            }))
        elif role_key == "hansin":
            out.append(er.model_copy(update={
                "note": "보호 대상 식신(protected_output) — 통관 성립 시 식신생재의 중추, "
                        "인성 왕 상태에서 단독 보강은 재피극 위험",
            }))
        elif role_key == "gusin":
            out.append(er.model_copy(update={
                "note": "관성이 과다 인성을 재생(官印相生) — 병 강화 방향. "
                        "조후 필요 시 壬/癸 기능 차이는 별도 평가",
            }))
        else:
            out.append(er)
    return out


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


def _johu_model_legacy(month_branch: Branch) -> YongsinCandidateModel | None:
    """조후 보조형(레거시): 한난 불균형 시 화/수 후보 — 사전 부재 시 폴백(graceful)."""
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


# 기후 축 severity 임계 — |값| ≥ _SEVERE 면 emergency 가산 자격, ≥ _MILD 면 축 성립.
_CLIMATE_SEVERE = 40.0
_CLIMATE_MILD = 20.0
# 축 → 직접 교정 오행(감수 ②: 한→火, 열→水, 조→水, 습→火. 매개·억부 오행은 조후 축 아님).
_AXIS_CORRECTIVE: dict[str, Element] = {
    "cold": Element.FIRE, "heat": Element.WATER,
    "dry": Element.WATER, "damp": Element.FIRE,
}


def _climate_axes(pillars: FourPillarsResult, force: ForceAnalysis) -> dict:
    """한난·조습 2축 severity 판정(감수 ② 판정 순서 1~3단계, 분포+지지 기반).

    temperature = (火세+열지지 가중) − (水세+한지지 가중),
    moisture   = (火세+조토 未戌 가중) − (水세+습토 丑辰 가중).
    |값| ≥ 40 → severe_*, ≥ 20 → 축 성립, 미만 → neutral. primary = |값| 큰 축
    (동률 시 temperature 우선 — 결정성). 억부·통관·격국 필요는 이 축이 아니다.
    """
    fe = force.five_elements
    dist = fe.season_adjusted_element_strength or fe.distribution_environment
    total = sum(dist.values()) or 1.0
    fire = dist.get(Element.FIRE, 0.0) / total * 100
    water = dist.get(Element.WATER, 0.0) / total * 100
    branches = [
        Branch(p.branch)
        for p in (pillars.year, pillars.month, pillars.day, pillars.hour)
        if p is not None
    ]
    hot_b = sum(1 for b in branches if b in _HOT_MONTHS)
    cold_b = sum(1 for b in branches if b in _COLD_MONTHS)
    dry_soil = sum(1 for b in branches if b in (Branch.MI, Branch.SUL))
    damp_soil = sum(1 for b in branches if b in (Branch.CHUK, Branch.JIN))
    temp = (fire + 5 * hot_b) - (water + 5 * cold_b)
    moist = (fire + 10 * dry_soil) - (water + 10 * damp_soil)

    def _label(v: float, pos: str, neg: str) -> str:
        if v >= _CLIMATE_SEVERE:
            return f"severe_{pos}"
        if v >= _CLIMATE_MILD:
            return pos
        if v <= -_CLIMATE_SEVERE:
            return f"severe_{neg}"
        if v <= -_CLIMATE_MILD:
            return neg
        return "neutral"

    t_axis = _label(temp, "heat", "cold")
    m_axis = _label(moist, "dry", "damp")
    if t_axis == "neutral" and m_axis == "neutral":
        primary = "neutral"
    elif abs(temp) >= abs(moist):
        primary = t_axis if t_axis != "neutral" else m_axis
    else:
        primary = m_axis if m_axis != "neutral" else t_axis
    return {
        "temperature_axis": t_axis,
        "moisture_axis": m_axis,
        "primary_climate_axis": primary,
        "temperature_value": round(temp, 1),
        "moisture_value": round(moist, 1),
    }


def _johu_model(
    month_branch: Branch,
    day_stem: Stem,
    pillars: FourPillarsResult,
    force: ForceAnalysis,
) -> YongsinCandidateModel | None:
    """조후 보조형 v3(감수 확정 2026-07-13): canonical need(사전) × 기후 축(계산) 분리.

    사전 셀 = canonical climate need(천간 단위, 壬≠癸). 계산 레이어가 기후 축 severity 를
    판정해, **severe 축을 직접 교정하는 천간**(셀 내 primary→secondary 순 탐색)이 부재할
    때만 emergency 가산(+0.15, 교정 오행 <5% 시 +0.10)한다 — 감수 ②: 억부·매개·단순
    결핍 오행은 조후 가산 대상이 아니다. 교정 천간이 있으면 그 오행이 직접 조후신으로
    후보가 되고(게이트 5 — 매개신보다 뒤로 밀리지 않음), severe 축이 없으면 셀 primary
    오행이 climate_helper(기본 신뢰도)로만 제시된다. avoid 천간 투간 시 주석.
    사전 부재 시 레거시 한습/조열 폴백.
    """
    table = load_johu_table()
    if table is None:
        return _johu_model_legacy(month_branch)
    cell = table.get(str(day_stem), {}).get(str(month_branch))
    if not isinstance(cell, dict):
        return None

    def _stems(key: str) -> list[str]:
        vals = cell.get(key, [])
        return [str(s) for s in vals] if isinstance(vals, list) else []

    primary_stems = _stems("primary")
    secondary_stems = _stems("secondary")
    avoid_stems = _stems("avoid")
    if not primary_stems:
        return None
    ordered = primary_stems + secondary_stems
    extreme = month_branch in (_COLD_MONTHS | _HOT_MONTHS)
    natal = [
        p for p in (pillars.year, pillars.month, pillars.day, pillars.hour)
        if p is not None
    ]
    transparent = {p.stem for p in natal}
    hidden = {h.stem for p in natal for h in p.hidden_stems}
    axes = _climate_axes(pillars, force)
    primary_axis: str = axes["primary_climate_axis"]
    severe = primary_axis.startswith("severe_")
    axis_key = primary_axis.removeprefix("severe_")
    corrective_el = _AXIS_CORRECTIVE.get(axis_key)

    reasons = [
        f"궁통보감 조후: {month_branch}월 {day_stem}일간 → {'·'.join(ordered)}"
        f" (최우선 {primary_stems[0]})",
        f"기후 축: 한난={axes['temperature_axis']} 조습={axes['moisture_axis']}"
        f" → primary={primary_axis}",
        "조후는 단독 확정 금지, 억부와 함께 검증",
    ]
    conf = 0.4 if extreme else 0.35
    yong_el = STEM_ELEMENT[Stem(primary_stems[0])]

    # severe 축 + 셀 내 직접 교정 천간 → emergency 평가(부재 시에만 가산).
    if severe and corrective_el is not None:
        # 반대 축을 severe 로 악화시키는 교정은 승격 금지(감수 ② 5단계).
        other_axis = (
            axes["moisture_axis"] if axis_key in ("cold", "heat")
            else axes["temperature_axis"]
        )
        worsens = (
            (corrective_el is Element.FIRE and other_axis in ("severe_dry", "severe_heat"))
            or (corrective_el is Element.WATER and other_axis in ("severe_damp", "severe_cold"))
        )
        corrective_stem = next(
            (s for s in ordered if STEM_ELEMENT[Stem(s)] is corrective_el), None
        )
        if worsens:
            reasons.append(
                f"교정 오행 {corrective_el}가 반대 축({other_axis})을 악화 — 승격 억제"
            )
        elif corrective_stem is None:
            reasons.append(
                f"severe {axis_key} 축이나 셀 내 직접 교정 천간 없음 — 구조 참고만"
            )
        else:
            yong_el = corrective_el
            if corrective_stem in transparent:
                reasons.append(f"{corrective_stem} 투간 — 조후 천간 충족")
            elif corrective_stem in hidden:
                reasons.append(
                    f"{corrective_stem} 지장간 존재 — 잠재 충족(투출·운에서 활성화)"
                )
            else:
                conf += 0.15
                same_el_alts = sorted(
                    s for s in (transparent | hidden)
                    if s != corrective_stem and STEM_ELEMENT[Stem(s)] is corrective_el
                )
                if same_el_alts:
                    reasons.append(
                        f"교정 천간 {corrective_stem} 부재 — 동일 오행 "
                        f"{'·'.join(same_el_alts)} 존재는 완전한 대체가 아님(壬≠癸류)"
                    )
                else:
                    reasons.append(f"교정 천간 {corrective_stem} 부재 — 조후 결핍")
                fe = force.five_elements
                dist = fe.season_adjusted_element_strength or fe.distribution_environment
                total = sum(dist.values()) or 1.0
                if dist.get(corrective_el, 0.0) / total < 0.05:
                    conf += 0.10
                    reasons.append("교정 오행 자체가 사실상 전무 — 조후 결핍 극심")
    else:
        # 비 severe: 셀 primary 는 canonical need 참고(climate_helper) — 가산 없음.
        p0 = primary_stems[0]
        if p0 in transparent:
            reasons.append(f"{p0} 투간 — canonical need 충족")
        elif p0 in hidden:
            reasons.append(f"{p0} 지장간 존재 — 잠재 충족")
        else:
            reasons.append(f"최우선 {p0} 부재 — 운에서의 보충 참고(가산 없음)")

    for s in avoid_stems:
        if s in transparent:
            reasons.append(f"기피 천간 {s} 투간 — 조후 저해(고전 명시)")
    return YongsinCandidateModel(
        model_type="johu",
        label="조후 보조형(궁통보감)",
        yongsin=_e(yong_el),
        confidence=round(conf, 4),
        reasons=reasons,
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
                "가종(假從): 억부(印·比)와 종격(순응)이 경쟁 — 사용자 검증 필요"
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
                # P1(2026-07-13): 재성 단독 완성도 계수 — 무근·실령·피극이면 감점(필요성 유지).
                w_mult, w_notes = _wealth_standalone_operability(
                    pillars, g, month_branch, force
                )
                models.append(_resource_excess_model(g, strength, w_mult, w_notes))
                # P2: 印食 병 감지 + 치료 중재 — 추가 통관 화력이 부족할 때만 火 승격 후보.
                disease = _output_disease(pillars, groups)
                if disease is not None:
                    kind, evidence = disease
                    med_cap, _med_factors = _additional_mediator_operability(
                        pillars, g["peer"]
                    )
                    veto = _mediator_promotion_veto(
                        band, month_branch, g["peer"], force
                    )
                    if med_cap >= _MEDIATOR_SUFFICIENT:
                        warnings.append(
                            "印食 병 감지되었으나 통관 오행이 이미 충분 — 승격 억제, "
                            f"가용량 {med_cap}"
                        )
                    elif veto is not None:
                        warnings.append(
                            f"印食 병 감지되었으나 mediator 승격 차단: {veto}"
                        )
                    else:
                        models.append(_food_rescue_model(
                            g, strength, kind, evidence, med_cap, pillars
                        ))
                        warnings.append(
                            "印食 병 감지: 화인통관(비겁) 치료 후보 추가 — "
                            f"추가 통관 가용량 {med_cap}"
                        )
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
            w_mult, w_notes = _wealth_standalone_operability(
                pillars, g, month_branch, force
            )
            models.append(_resource_excess_model(g, strength, w_mult, w_notes))
            warnings.append("중화 구간: 인성과다(財損印) 후보 조건부 추가")
            disease = _output_disease(pillars, groups)
            if disease is not None:
                kind, evidence = disease
                med_cap, _med_factors = _additional_mediator_operability(
                    pillars, g["peer"]
                )
                veto = _mediator_promotion_veto(band, month_branch, g["peer"], force)
                if med_cap < _MEDIATOR_SUFFICIENT and veto is None:
                    models.append(_food_rescue_model(
                        g, strength, kind, evidence, med_cap, pillars
                    ))
                    warnings.append(
                        "중화 구간: 印食 병 감지 — 화인통관 치료 후보 조건부 추가"
                    )
        warnings.append("중화 구간: 경쟁 모델 동시 제시, 사용자 검증 필요")

    # 조후: _johu_model이 한습(亥子丑)·조열(巳午未)만 모델을 내므로(辰·戌은 None) 그대로 사용.
    # (丑=한겨울·未=한여름은 土월이라도 조후가 핵심 — 월령오행으로 걸러내면 안 됨.)
    johu = _johu_model(month_branch, dm, pillars, force)
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
    if strength.borderline:
        warnings.append(
            f"신강약 경계: 점수 {strength.score}가 밴드 경계권 — 용희신 단정 보류"
        )
    if competing:
        warnings.append(
            "용신 후보 경합: 상위 후보 점수 차가 작아 사용자 검증 필요"
        )
    if (
        johu is not None
        and useful_candidates
        and useful_candidates[0].element != johu.yongsin
        and abs(useful_candidates[0].score - next(
            (c.score for c in useful_candidates if c.element == johu.yongsin), 0.0
        )) < 0.08
    ):
        warnings.append("조후 경계: 조후 후보가 근소 차이로 밀림 — 한난습조 맥락 병행 검토")
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
    # 실현 경계(CAL-ROLE-BORDERLINE-01c1-a): 용신 오행이 정해진 뒤의 5역할 확정을
    # 순수 경계로 뽑았다. 판정 순서·규칙은 그대로다 — 특수분기가 모델맵 승격보다 앞서고,
    # 정적 생극 순환은 부분맵 모델과 특수분기의 폴백 전용이다.
    #
    # 모델맵 채택(2026-07-12 데굴님 확정 — 전면): 정적 생극 순환은 원국 과다·강약·구조를
    # 무시하고 배정한다(실사용 오류: 살중용인에서 '水生木이니 水=희신'이 관살 압박을 길로
    # 판정 / 신강 억부 희=비겁 / 군겁쟁재 희=재성 / 식상과다 희=관성 / 인성과다 병을 한신·
    # 구신으로 방치). 각 모델의 자체 역할맵이 구조 교정값이므로 **5역할 완비 선택 모델은
    # final 도 자체맵을 채택**한다.
    realization = resolve_realized_roles(
        chart_context=RoleRealizationChartContext(
            group_elements=g,
            group_strengths=groups,
            strength_band=band,
            pillars=pillars,
            force=force,
            month_branch=month_branch,
            bridge_required_detail=checks["bridge_required"].detail,
        ),
        selected_yongsin_element=yongsin_el,
        useful_scores=useful,
        model_outputs=models,
        top_model_type=top_model,
        static_classifier=_classify_roles,
        bridge_classifier=_classify_bridge_roles,
    )
    warnings.extend(realization.warnings)  # 통관 동점 타이브레이크 사유 — 순서 유지
    roles = realization.final_role_map.as_dict()
    selected_model = realization.selected_model
    model_complete = realization.model_complete
    model_map_promoted = realization.model_map_promoted

    final = {
        **roles,
        "confidence": round(model_conf.get(top_model or "", 0.0), 4),
        "selected_model": top_model,
    }

    # 2계층 역할(YONGSIN_OPERATIONAL_ROLE_SPEC Phase 0): canonical=현행 final 5역할 미러,
    # operational=실제 선택 모델의 자체 역할맵을 5역할 완비 시 채택, 부분맵이면 canonical 폴백.
    canonical_roles: dict[str, str | None] = {k: roles.get(k) for k in _ROLE_KEYS}
    # final 이 정적 생극 순환(_classify_roles) 그대로이거나 위 희신 과다 교정으로 이미
    # 모델맵을 채택했을 때만 모델 자체맵 채택. bridge_tonggwan·부일간(무비겁) 특수분기는
    # canonical 이 이미 맥락 교정값이므로 폴백.
    static_roles = _classify_roles(yongsin_el)
    final_is_static = all(
        canonical_roles[k] == static_roles.get(k) for k in _ROLE_KEYS
    )
    model_map_adopted = (final_is_static or model_map_promoted) and model_complete
    operational_map = _operational_role_map(
        selected_model, canonical_roles, adopt_model_map=model_map_adopted
    )
    operational_roles = _build_operational_roles(canonical_roles, operational_map)
    # Phase 1: 과다(병) 기반 조건부 라벨. model_map 을 채택한 케이스에만 적용해
    # fallback/부분맵(bridge·disease·support 특수분기)에 조건부 라벨이 새지 않게 한다.
    # Phase 2: 조후 가드(_climate_harmful) 연결 — climate_need 격상·climate_harmful 강등.
    if model_map_adopted:
        operational_roles = _annotate_overload_conditions(
            operational_roles, canonical_roles, operational_map, groups, g
        )
        operational_roles = _annotate_climate_conditions(
            operational_roles, month_branch, force, canonical_roles, operational_map
        )
        # Phase 3: 官殺 합 맥락(합반/쟁합/합거/합화 + 관살혼잡) 주석 보강(라벨 불변, 세력 불변).
        operational_roles = _annotate_officer_hap_context(
            operational_roles, pillars, g, geokguk, canonical_roles, operational_map
        )
        # #7: 官 외 십성(財/印/食傷/比劫) 합 맥락 주석(라벨·세력 불변, conditional=note 중심).
        operational_roles = _annotate_ten_god_hap_context(
            operational_roles, pillars, g, canonical_roles, operational_map
        )
        # 화인통관(food_rescue) 채택 시 구조 주석 — 보호 대상 식상·재성 필요/작동 분리·
        # 희신-기신 천간합 이원 평가(P3, 설명 전용) 등.
        if top_model and top_model.startswith("food_rescue"):
            operational_roles = _annotate_food_rescue_context(
                operational_roles, canonical_roles, pillars, g
            )
    # Phase 4a/4b: 용신 작동성(operability) — 투간/통근·정편인(4a) + 子卯 격각 통관손상(4b)
    # penalty(용신 원소만, final 불변·이벤트 불변). model_map 채택 케이스 + johu 선택
    # 케이스에 산정 — 조후 필요신은 canonical 필요도를 보존하되 무근·부재 감점은 반드시
    # 작동성 계층에 남아야 한다(climate_need_preservation, 2026-07-13 데굴님 감수).
    if yongsin_el and (model_map_adopted or top_model == "johu"):
        op_value, op_factors, op_reasons = _compute_yongsin_operability(
            yongsin_el, pillars, _e(g["resource"]), canonical_roles
        )
        operational_roles = [
            _with_operability(r, op_value, op_factors, op_reasons)
            if r.element == yongsin_el else r
            for r in operational_roles
        ]

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
        canonical_roles=canonical_roles,
        operational_roles=operational_roles,
        flow_circulation=flow,
        requires_validation=True,
        warnings=warnings,
    )
