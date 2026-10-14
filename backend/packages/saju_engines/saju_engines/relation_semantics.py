"""관계 판정 → 구조화 의미(RelationSemantics) 파생 — P0 (2026-07-27 데굴님 확정).

`resolve_stem_hap` / `resolve_branch_hap`의 판정 결과를 직교 3축(성립/化/묶임)으로
재표현한다. **판정을 다시 하지 않는다** — 매핑만 한다(절대원칙 1).

배경: 일진 壬寅 · 원국 亥 사례에서 엔진은 `亥寅合 → 합반(化 불성·묶임) · 합거 ·
壬 정재=구신 유리(흉 제거)`로 판정했는데, LLM이 "합하여 기신 木을 강화한다"로
정반대 서술을 냈다. 렌더 문장을 늘리는 것만으로는 LLM의 자체 지식('寅亥合은 木')이
엔진 판정을 덮는 것을 막지 못하므로, 금지 해석을 명시하고 생성 후 구조화 감사를 건다.
"""

from __future__ import annotations

from saju_manse_analysis.relations.hap_modes import (
    BranchHapResolution,
    StemHapResolution,
    resolve_branch_hap,
    resolve_stem_hap,
)

from saju_shared_types.constants import (
    BRANCH_INDEX,
    BRANCH_KO,
    ELEMENT_KO,
    STEM_INDEX,
    STEM_KO,
)
from saju_shared_types.enums import Branch, Element, Stem
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.relation_semantics import (
    BindingState,
    EffectFavorability,
    EffectKind,
    FormationState,
    RelationEffect,
    RelationOccurrence,
    RelationSemantics,
    TransformationState,
)

from .event_scoring import favorability_map

# 역할 → 효과 유불리. 한신은 사전(favorability_rules.json)에서 'conditional'(주변 신호에
# 따라 가변)이라 단정하지 않고 MIXED로 둔다 — 임의로 0(중립)으로 축약하지 않는다.
_ROLE_FAVORABILITY: dict[str, EffectFavorability] = {
    "용신": EffectFavorability.BENEFICIAL,
    "희신": EffectFavorability.BENEFICIAL,
    "기신": EffectFavorability.ADVERSE,
    "구신": EffectFavorability.ADVERSE,
    "한신": EffectFavorability.MIXED,
}
# 엔진 AffectedGod.effect(boon/harm/neutral) → 효과 유불리.
_EFFECT_FAVORABILITY: dict[str, EffectFavorability] = {
    "boon": EffectFavorability.BENEFICIAL,
    "harm": EffectFavorability.ADVERSE,
    "neutral": EffectFavorability.MIXED,
}
# 표시 라벨 접미 — 엔진 렌더(hap_lines)와 동일 표기를 유지한다(육합은 '合').
_KIND_KO = {
    "six": "合",
    "three_harmony": "삼합",
    "half": "반합",
    "directional": "방합",
    "stem_combination": "合",
}


def _role_favorability(role: str) -> EffectFavorability:
    """용희기구한 역할 → 효과 유불리(미상은 MIXED)."""
    return _ROLE_FAVORABILITY.get(role, EffectFavorability.MIXED)


def _stem_label(pair: tuple[str, str]) -> str:
    """천간합 표시 라벨 — 천간 표준순(甲→癸)으로 정규화해 중복 표기를 막는다."""
    a, b = sorted(pair, key=lambda s: STEM_INDEX[Stem(s)])
    return f"{a}{b}合"


def derive_stem_semantics(r: StemHapResolution, fav: dict[str, str]) -> RelationSemantics:
    """천간합 판정 1건 → 구조화 의미.

    Args:
        r: 엔진이 판정한 천간합 결과.
        fav: 오행 → 용희기구한 역할 맵.

    Returns:
        직교 3축으로 재표현된 RelationSemantics.
    """
    if r.blocked:
        formation = FormationState.NOT_FORMED
        transformation = TransformationState.NOT_APPLICABLE
        binding = BindingState.NONE
    elif r.hap_mode == "transform":
        formation = FormationState.FORMED
        transformation = TransformationState.TRANSFORMED
        binding = BindingState.NONE
    elif r.hap_mode == "combine_self":
        formation = FormationState.FORMED
        transformation = (
            TransformationState.TRANSFORMED
            if r.chart_transform
            else TransformationState.NO_TRANSFORMATION
        )
        binding = BindingState.NONE
    else:  # bind — 합반(+합거)
        formation = FormationState.FORMED
        transformation = TransformationState.NO_TRANSFORMATION
        binding = BindingState.REMOVED if r.direction == "away" else BindingState.BOUND

    effects = [
        RelationEffect(
            target=a.stem,
            ten_god=a.ten_god,
            role=a.role,
            effect=EffectKind.SUPPRESSED,
            favorability=_EFFECT_FAVORABILITY.get(a.effect, EffectFavorability.MIXED),
        )
        for a in r.affected
    ]
    el = r.transform_element
    if transformation is TransformationState.TRANSFORMED and el:
        effects.append(RelationEffect(
            target=el, role=fav.get(el, ""), effect=EffectKind.STRENGTHENED,
            favorability=_role_favorability(fav.get(el, "")),
        ))

    sem = RelationSemantics(
        relation_label=_stem_label(r.pair),
        members=tuple(sorted(r.pair, key=lambda s: STEM_INDEX[Stem(s)])),
        occurrences=[
            RelationOccurrence(char=c, position=p)
            for c, p in zip(r.pair, r.positions, strict=False)
        ],
        kind="stem_combination",
        formation_state=formation,
        transformation_state=transformation,
        binding_state=binding,
        transform_element=el,
        transform_tier=r.transform_tier,
        role=fav.get(el, "") if el else "",
        luck_origin=r.luck_origin,
        effects=effects,
    )
    _fill_interpretations(sem)
    return sem


def derive_branch_semantics(r: BranchHapResolution) -> RelationSemantics:
    """지지합(육합/삼합/반합/방합) 판정 1건 → 구조화 의미.

    방합은 엔진이 `notes=['방합 — 기존 오행 강화(변화 아님)']`로 명시하듯 化 개념이
    아니므로 transformation_state=NOT_APPLICABLE로 둔다(化 확정/조건부로 표기 금지).
    """
    # 판정은 엔진 hap_mode·direction·affected가 한다. 관계 **이름**으로 추정하지 않는다
    # — 반합(半合)을 합반(合絆)으로 옮기면 없는 묶임을 만들어낸다(2026-07-27 실측 결함).
    if r.hap_mode == "transform":
        formation = FormationState.FORMED
        transformation = TransformationState.TRANSFORMED
        binding = BindingState.NONE
    elif r.hap_mode == "strengthen":  # 방합 완성 — 化가 아니라 기존 오행 강화
        formation = FormationState.FORMED
        transformation = TransformationState.NOT_APPLICABLE
        binding = BindingState.NONE
    elif r.hap_mode == "partial":  # 반합·부분 방합 — 국 미완성, 묶임 아님
        # 엔진은 반합에 'transform'을 절대 반환하지 않는다(hap_mode = transform if full
        # else partial). 즉 반합은 化 판정의 대상이 아니므로 NO_TRANSFORMATION(化 불성,
        # 조건이 갖춰지면 化할 수 있다는 미결 상태)이 아니라 NOT_APPLICABLE이다.
        formation = FormationState.PARTIAL
        transformation = TransformationState.NOT_APPLICABLE
        binding = BindingState.NONE
    else:  # bind — 합반(+합거)
        formation = FormationState.FORMED
        transformation = TransformationState.NO_TRANSFORMATION
        # 합거는 엔진이 direction='away'를 명시할 때만 단정한다.
        binding = BindingState.REMOVED if r.direction == "away" else BindingState.BOUND

    effects = [
        RelationEffect(
            target=a.stem,
            ten_god=a.ten_god,
            role=a.role,
            effect=EffectKind.SUPPRESSED,
            favorability=_EFFECT_FAVORABILITY.get(a.effect, EffectFavorability.MIXED),
        )
        for a in r.affected
    ]
    el = r.transform_element
    if el and binding is BindingState.NONE:
        kind = (
            EffectKind.PARTIALLY_STRENGTHENED
            if formation is FormationState.PARTIAL
            else EffectKind.STRENGTHENED
        )
        effects.append(RelationEffect(
            target=el, role=r.role, effect=kind,
            favorability=_role_favorability(r.role),
        ))

    # 지지 표준순(子→亥)으로 정규화 — 라벨이 입력 순서에 따라 '午寅/寅午'로 흔들리면
    # 로그 집계와 P1 클러스터 키가 갈라진다. relations.json도 같은 순서를 쓴다
    # (rel_寅午戌三合 · rel_卯未亥三合 · rel_巳午未方合).
    members = tuple(sorted(r.members, key=lambda b: BRANCH_INDEX[Branch(b)]))
    sem = RelationSemantics(
        relation_label=f"{''.join(members)}{_KIND_KO.get(r.kind, '合')}",
        members=members,
        occurrences=[
            RelationOccurrence(char=c, position=p)
            for c, p in zip(r.members, r.positions, strict=False)
        ],
        kind=r.kind,
        formation_state=formation,
        transformation_state=transformation,
        binding_state=binding,
        transform_element=el,
        transform_tier=r.transform_tier,
        role=r.role,
        luck_origin=r.luck_origin,
        effects=effects,
    )
    _fill_interpretations(sem)
    return sem


#: 용희기구한 → 사용자용 쉬운 말. terminology.json 정의를 그대로 따른다(새 문안 금지 — 원칙 10).
_ROLE_PLAIN: dict[str, str] = {
    "용신": "가장 필요한 기운",
    "희신": "도와주는 반가운 기운",
    "기신": "부담스러운 기운",
    "구신": "부담을 키우는 기운",
    "한신": "큰 영향 없이 곁에 있는 기운",
}
#: 라벨 접미 한글화 — '合'만 바꾸고 '반합'·'방합'·'삼합'은 그대로 쓴다.
_LABEL_SUFFIX_KO: dict[str, str] = {"合": "합"}


def _char_ko(c: str) -> str:
    """간지 한 글자의 한글 음('巳' → '사'). 모르는 글자는 빈 문자열."""
    if c in {x.value for x in Stem}:
        return STEM_KO[Stem(c)]
    if c in {x.value for x in Branch}:
        return BRANCH_KO[Branch(c)]
    return ""


def _element_ko(el: str) -> str:
    """오행 한 글자의 한글 음('水' → '수'). 모르는 값은 빈 문자열."""
    try:
        return ELEMENT_KO[Element(el)]
    except ValueError:
        return ""


def _el_with_ro(el: str) -> str:
    """오행 + 조사 '(으)로' — 한글 음 받침 기준('火로'·'木으로'). 'ㄹ' 받침·무받침은 '로'."""
    ko = _element_ko(el)
    if not ko:
        return f"{el}(으)로"
    jong = (ord(ko[-1]) - 0xAC00) % 28
    return f"{el}로" if jong in (0, 8) else f"{el}으로"


def _label_with_ko(sem: RelationSemantics) -> str:
    """관계 라벨 + 한글 음 병기('巳申合(사신합)'·'午戌반합(오술반합)')."""
    ko = "".join(_char_ko(c) for c in sem.members)
    if len(ko) != len(sem.members):
        return sem.relation_label
    suffix = sem.relation_label[len("".join(sem.members)):]
    return f"{sem.relation_label}({ko}{_LABEL_SUFFIX_KO.get(suffix, suffix)})"


def _el_with_ko(el: str) -> str:
    """오행 한글 병기('水(수)')."""
    ko = _element_ko(el)
    return f"{el}({ko})" if ko else el


def _role_sentence(el: str, role: str | None) -> str:
    """화신·강화 오행의 역할을 쉬운 말 + 원어 괄호로 붙인다. 역할이 없으면 생략.

    '나에게'가 아니라 '이 사주에서'로 쓴다 — 동반자 사주 풀이에도 같은 문장이 실린다.
    """
    plain = _ROLE_PLAIN.get(role or "")
    if not plain:
        return ""
    return f" 이 {el} 기운은 이 사주에서 {plain}({role})입니다."


def _effect_target_ko(e: RelationEffect) -> str:
    """억제 대상 표기 '丙(병) 정인'."""
    ko = _char_ko(e.target)
    name = f"{e.target}({ko})" if ko else e.target
    return f"{name} {e.ten_god}".strip()


def _build_canonical_claim(sem: RelationSemantics) -> str:
    """엔진 확정값만으로 구성한 관계 서술 문장 — 일반 사용자용 쉬운 말(2026-10-13 개정).

    이 문장은 세 곳에서 같은 값으로 쓰인다 — ① 생성 전 LLM 입력(그대로 쓰거나 생략만
    하도록 지시) ② 생성 후 역전 문장의 교체본 ③ 안전 템플릿. 프롬프트와 복구본이 같은
    SSOT라 교체가 '예외 처리'가 아니라 정상 기능이 된다(2026-07-27 데굴님 확정).

    표현 원칙(2026-10-13 데굴님 승인): 용어를 모르는 사용자가 읽는 문장이므로 판정을 쉬운
    말로 먼저 쓰고 원어(합거·합반·합화, 용희기구한)는 괄호로 한 번만 남긴다. 합거는 전문가
    감수대로 '제거'가 아니라 '크게 약해짐'(완화)으로 쓴다. 역할 쉬운 말은 terminology.json
    정의를 따른다. 간지·오행은 한글 음을 병기하고, 오행 뒤에 조사를 직접 붙이지 않고
    '○(○) 기운으로'로 써서 '水으로' 류 오류를 없앤다. 감사기 키워드와의 정합: 묶임이 없는
    관계에는 '붙잡·묶' 어휘를 쓰지 않고, 化가 아닌 관계의 '바뀌'는 항상 부정형으로만 쓴다.

    Args:
        sem: 관계 구조화 의미(엔진 판정 3축 + 효과).

    Returns:
        사용자에게 그대로 보여도 되는 한국어 확정 문장.
    """
    el = sem.transform_element or ""
    head = f"{_label_with_ko(sem)}은 이번 운에서 "
    if sem.formation_state is FormationState.NOT_FORMED:
        body = "조건이 갖춰지지 않아 실제로 작용하지 않습니다."
    elif sem.binding_state is BindingState.REMOVED:
        # 합거는 엔진이 direction='away'로 명시한 경우에만 쓴다.
        body = (
            "두 글자가 서로 붙잡혀, "
            + (f"새로운 {_el_with_ko(el)} 기운으로 바뀌지는 않고 " if el else "")
            + "붙잡힌 글자의 작용이 크게 약해집니다(합거)."
        )
    elif sem.binding_state is BindingState.BOUND:
        body = "두 글자가 서로 붙잡혀 각자의 작용이 둔해지지만, " + (
            f"새로운 {_el_with_ko(el)} 기운으로 바뀌지는 않습니다(합반)."
            if el else "그 이상의 변화는 없습니다(합반)."
        )
    elif sem.transformation_state is TransformationState.TRANSFORMED and el:
        body = (
            f"두 글자가 손을 잡고 {_el_with_ko(el)} 기운으로 바뀝니다(합화)."
            + _role_sentence(el, sem.role)
        )
    elif sem.formation_state is FormationState.PARTIAL and el:
        # 반합·부분 방합 — 국 미완성. 묶임이 아니라 보조 강화다. '합화 미확정'처럼 조건이
        # 갖춰지면 化할 수 있는 미결 상태로 읽히지 않도록 化 어휘 자체를 쓰지 않는다
        # (2026-07-27 데굴님 지적).
        what = (
            "같은 계절의 글자끼리 모였지만 세 글자가 다 모이지는 않아"
            if sem.kind == "directional"
            else "세 글자가 모여야 완성되는 조합 중 두 글자만 모여"
        )
        body = (
            f"{what}, {_el_with_ko(el)} 기운을 조금 보태 주는 정도입니다."
            + _role_sentence(el, sem.role)
        )
    elif sem.transformation_state is TransformationState.NOT_APPLICABLE and el:
        what = (
            "같은 계절의 글자 세 개가 모두 모여"
            if sem.kind == "directional"
            else "세 글자가 모두 모여"
        )
        body = f"{what} {_el_with_ko(el)} 기운을 크게 키웁니다." + _role_sentence(el, sem.role)
    else:
        body = "눈에 띄는 추가 작용은 확인되지 않았습니다."

    boon = [e for e in sem.effects
            if e.effect is EffectKind.SUPPRESSED
            and e.favorability is EffectFavorability.BENEFICIAL]
    harm = [e for e in sem.effects
            if e.effect is EffectKind.SUPPRESSED
            and e.favorability is EffectFavorability.ADVERSE]
    tail = ""
    if boon:
        names = "·".join(_effect_target_ko(e) for e in boon)
        tail += f" 그 덕분에 {names}의 부담스러운 작용은 오히려 가벼워집니다."
    if harm:
        names = "·".join(_effect_target_ko(e) for e in harm)
        tail += f" 그 대신 {names}의 좋은 작용도 이번에는 힘을 덜 씁니다."
    return head + body + tail


def _fill_interpretations(sem: RelationSemantics) -> None:
    """허용·금지 해석과 canonical claim을 채운다(감사 판정은 구조화 필드가 한다)."""
    el = sem.transform_element or ""
    allowed: list[str] = []
    forbidden: list[str] = []

    if sem.formation_state is FormationState.NOT_FORMED:
        allowed.append("성립하지 않아 작용 없음")
        forbidden.append("성립했다고 서술")
        if el:
            forbidden.append(f"{_el_with_ro(el)} 합화했다고 서술")
    elif sem.binding_state is not BindingState.NONE:
        allowed.append("묶임(합반) — 化는 이루어지지 않음")
        if sem.binding_state is BindingState.REMOVED:
            allowed.append("합거 — 묶인 글자의 작용이 끌려가 제거")
        else:
            forbidden.append("합거·제거로 단정(묶임까지만 판정됨)")
        if el:
            forbidden.append(f"{_el_with_ro(el)} 합화했다고 서술")
            forbidden.append(f"{el} 기운이 강해진다고 서술")
    elif sem.transformation_state is TransformationState.TRANSFORMED and el:
        allowed.append(f"{el}({sem.role or '역할 미상'})으로 합화")
        forbidden.append("합이 불성립·무산됐다고 서술")
        forbidden.append(f"{el} 아닌 다른 오행으로 합화했다고 서술")
    elif sem.formation_state is FormationState.PARTIAL and el:
        allowed.append(f"{el}({sem.role or '역할 미상'}) 작용의 보조적 강화(국 미완성)")
        forbidden.append("서로 묶였다·합거됐다고 서술(묶임 판정 없음)")
        forbidden.append(f"{el}국이 성립했다·{_el_with_ro(el)} 합화했다고 서술")
    elif sem.transformation_state is TransformationState.NOT_APPLICABLE and el:
        allowed.append(f"{el} 기운 강화(化가 아니라 기존 오행 강화)")
        forbidden.append(f"{_el_with_ro(el)} 합화(化)했다고 서술")
        forbidden.append("서로 묶였다·합거됐다고 서술(묶임 판정 없음)")

    for eff in sem.effects:
        if eff.effect is EffectKind.SUPPRESSED:
            forbidden.append(f"{eff.target} 기운이 강해진다고 서술")
            if eff.favorability is EffectFavorability.BENEFICIAL:
                allowed.append(f"{eff.target}({eff.role or '역할 미상'})의 불리한 작용이 완화")
                forbidden.append(f"{eff.target} 억제를 불리·악화 요인으로 단정")
            elif eff.favorability is EffectFavorability.ADVERSE:
                allowed.append(f"{eff.target}({eff.role or '역할 미상'})의 이로운 작용이 묶임")

    sem.allowed_interpretations = list(dict.fromkeys(allowed))
    sem.forbidden_interpretations = list(dict.fromkeys(forbidden))
    sem.canonical_claim = _build_canonical_claim(sem)


def collect_luck_relation_semantics(
    result: ManseV2Result,
    luck_stems: list[str] | None = None,
    luck_branches: list[str] | None = None,
) -> list[RelationSemantics]:
    """운(運) 관여 합의 구조화 의미 목록 — 운 스택 전체를 한 번에 넘길 수 있다.

    Args:
        result: 만세 결과(원국 + 용희기구한 판정 근거).
        luck_stems: 운 천간 목록(대운·세운·월운·일운 등, 중복 허용).
        luck_branches: 운 지지 목록.

    Returns:
        운이 관여한 합만 담은 RelationSemantics 목록(라벨 기준 중복 제거).
    """
    if result.pillars is None:
        return []
    fav = favorability_map(result)
    p = result.pillars
    out: list[RelationSemantics] = []
    if luck_stems:
        out += [
            derive_stem_semantics(r, fav)
            for r in resolve_stem_hap(p, fav, luck_stems=luck_stems)
            if r.luck_origin
        ]
    if luck_branches:
        out += [
            derive_branch_semantics(r)
            for r in resolve_branch_hap(p, fav, luck_branches=luck_branches)
            if r.luck_origin
        ]
    seen: set[str] = set()
    unique: list[RelationSemantics] = []
    for sem in out:
        if sem.relation_label in seen:
            continue
        seen.add(sem.relation_label)
        unique.append(sem)
    return unique


def forbidden_interpretation_line(sem: RelationSemantics) -> str:
    """LLM 입력용 '해석 고정' 한 줄 — 금지 해석이 없으면 빈 문자열."""
    if not sem.forbidden_interpretations:
        return ""
    return (
        f"[해석 고정 {sem.relation_label}] 허용: "
        + (" / ".join(sem.allowed_interpretations) or "판정 그대로")
        + " · 금지: "
        + " / ".join(sem.forbidden_interpretations)
    )
