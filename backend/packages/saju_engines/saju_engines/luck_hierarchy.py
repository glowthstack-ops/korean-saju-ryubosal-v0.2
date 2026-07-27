"""계층형 운 grounding 빌더 (P1 — 2026-07-27 데굴님 확정).

입력 두 개를 **결합만** 한다.
  - composite `InteractionHit`: 어떤 층위의 어떤 글자가 참여했는가(층위의 유일한 출처)
  - P0 `RelationSemantics`: 그 관계가 무슨 의미인가(성립/化/묶임/효과/확정 문장)

관계 이름으로 결과 오행·합화·합반을 다시 추정하지 않는다. 클러스터는 표현 뷰이며
원본 관계를 복사·변형하지 않고 ID만 참조한다(절대원칙 1·10).
"""

from __future__ import annotations

from saju_shared_types.luck_hierarchy import (
    HierarchyInteraction,
    HierarchyParticipant,
    InteractionCluster,
    InteractionSummary,
    LuckHierarchy,
    ParticipantLayer,
    PillarSummary,
    SemanticResolutionStatus,
    normalize_participant_layer,
)
from saju_shared_types.precompute import InteractionHit, LuckComposite
from saju_shared_types.relation_semantics import (
    BindingState,
    EffectKind,
    FormationState,
    RelationSemantics,
)

#: composite InteractionKind → P0 semantics.kind 후보. 같은 글자쌍이라도 합/파처럼
#: 종류가 다르면 다른 관계이므로 종류까지 맞춰야 오매칭이 나지 않는다.
_KIND_FAMILY: dict[str, frozenset[str]] = {
    "stem_combine": frozenset({"stem_combination"}),
    "branch_six_combine": frozenset({"six"}),
    "branch_three_combine": frozenset({"three_harmony", "half"}),
    "branch_directional": frozenset({"directional"}),
}
#: 클러스터로 묶을 수 있는 효과 계열 — '강화'끼리만. 묶임(SUPPRESSED)은 강화와
#: 같은 현상이 아니므로 결과 오행이 같아도 합치지 않는다.
_STRENGTHEN_KINDS = frozenset({EffectKind.STRENGTHENED, EffectKind.PARTIALLY_STRENGTHENED})
#: 대표(primary) 우선순위 — 완성 국·방합 > 왕지 포함 반합 > 육합 > 부분.
_PRIMARY_RANK: dict[str, int] = {
    "branch_directional": 0,
    "branch_three_combine": 1,
    "branch_six_combine": 2,
    "stem_combine": 3,
}


def _semantics_index(
    semantics: list[RelationSemantics],
) -> dict[tuple[frozenset[str], str], RelationSemantics]:
    """(구성 글자 집합, kind) → 의미. 라벨이 아니라 글자·종류로 매칭한다."""
    return {(frozenset(s.members), s.kind): s for s in semantics}


def _match_semantics(
    hit: InteractionHit,
    index: dict[tuple[frozenset[str], str], RelationSemantics],
) -> RelationSemantics | None:
    """상호작용 1건에 대응하는 P0 의미를 찾는다(없으면 None — 충·형·파·해 등)."""
    chars = frozenset(p.ganji for p in hit.participants)
    for kind in _KIND_FAMILY.get(hit.kind.value, frozenset()):
        found = index.get((chars, kind))
        if found is not None:
            return found
    return None


def _to_interaction(
    hit: InteractionHit, sem: RelationSemantics | None
) -> HierarchyInteraction | None:
    """InteractionHit + P0 의미 → 계층 관계. 층위 미상이면 None(fail-closed)."""
    participants: list[HierarchyParticipant] = []
    for p in hit.participants:
        layer = normalize_participant_layer(p.source.value)
        if layer is None:
            return None
        participants.append(HierarchyParticipant(char=p.ganji, layer=layer))
    out = HierarchyInteraction(
        interaction_id=hit.relation_id,
        kind=hit.kind.value,
        participants=participants,
        base_intensity=hit.base_weight,
    )
    if sem is not None:
        # P0 확정값 복사 — 여기서 다시 판정하지 않는다.
        out.relation_label = sem.relation_label
        out.result_element = sem.transform_element
        out.formation_state = sem.formation_state
        out.transformation_state = sem.transformation_state
        out.binding_state = sem.binding_state
        out.effects = list(sem.effects)
        out.canonical_claim = sem.canonical_claim
        out.semantic_resolution_status = SemanticResolutionStatus.RESOLVED
        return out

    if hit.kind.value in _KIND_FAMILY:
        # 합 계열인데 의미 SSOT(resolve_*_hap)가 성립을 인정하지 않았다 — 두 엔진의
        # 판정이 갈린다. 성립 여부가 확정될 때까지 서술·클러스터·점수에서 뺀다.
        out.semantic_resolution_status = SemanticResolutionStatus.ENGINE_CONFLICT
        out.formation_confirmed = False
        out.narrative_eligible = False
        out.cluster_eligible = False
        out.score_eligible = False
        out.exclusion_reason = (
            "탐지기는 성립으로 보지만 의미 판정기는 미성립 — 엔진 불일치"
        )
    else:
        # 충·형·파·해·원진 — 성립은 확정이나 化·묶임 개념의 대상이 아니다.
        # 서술(층간 긴장)에는 쓰되 길흉 부호는 이번 릴리즈에서 판정하지 않는다.
        out.semantic_resolution_status = SemanticResolutionStatus.STRUCTURAL_ONLY
        out.cluster_eligible = False
        out.score_eligible = False
        out.exclusion_reason = "길흉 부호 미판정 관계(변동성만 반영 대상)"
    return out


def _strengthen_kind(inter: HierarchyInteraction) -> EffectKind | None:
    """이 관계가 결과 오행을 '강화'하는가 — 그 효과 종류(아니면 None).

    묶임(합거)은 결과 오행이 같아도 강화가 아니다. 午未合은 result_element=火이지만
    엔진 판정은 합거(丁 편인·희신, 己 비견·용신이 묶임)라, 火 강화 클러스터에 넣으면
    의미가 뒤집힌다. 판정이 확정되지 않은 관계(ENGINE_CONFLICT)도 제외한다.
    """
    if not inter.cluster_eligible:
        return None
    if inter.semantic_resolution_status is not SemanticResolutionStatus.RESOLVED:
        return None
    if inter.binding_state is not BindingState.NONE or not inter.result_element:
        return None
    for eff in inter.effects:
        if eff.effect in _STRENGTHEN_KINDS and eff.target == inter.result_element:
            return eff.effect
    return None


def _primary_of(candidates: list[HierarchyInteraction]) -> HierarchyInteraction:
    """대표 관계 — 완성 국 우선, 다음 사전 강도, 마지막은 ID로 결정론 고정."""
    return min(
        candidates,
        key=lambda i: (
            0 if i.formation_state is FormationState.FORMED else 1,
            _PRIMARY_RANK.get(i.kind, 9),
            -i.base_intensity,
            i.interaction_id,
        ),
    )


def _build_clusters(interactions: list[HierarchyInteraction]) -> list[InteractionCluster]:
    """같은 오행을 강화하는 관계 중 참여 글자가 겹치는 것만 묶는다.

    묶는 조건은 ①결과 오행 동일 ②효과가 강화 계열 ③참여 발생(occurrence) 중첩이다.
    중첩이 없으면 서로 독립적인 현상일 수 있으므로 묶지 않는다 — 문장이 몇 개 중복되는
    것보다 서로 다른 관계를 하나로 잘못 묶는 쪽이 더 위험하다(데굴님 확정).
    """
    by_element: dict[str, list[HierarchyInteraction]] = {}
    for inter in interactions:
        if _strengthen_kind(inter) is not None and inter.result_element:
            by_element.setdefault(inter.result_element, []).append(inter)

    clusters: list[InteractionCluster] = []
    for element, group in sorted(by_element.items()):
        if len(group) < 2:
            continue
        # 발생 중첩으로 연결 요소를 만든다(중첩 없는 관계는 자기 자신만의 그룹).
        remaining = list(group)
        while remaining:
            seed = remaining.pop(0)
            component = [seed]
            covered = set(seed.occurrence_ids)
            changed = True
            while changed:
                changed = False
                for cand in list(remaining):
                    if cand.occurrence_ids & covered:
                        component.append(cand)
                        covered |= cand.occurrence_ids
                        remaining.remove(cand)
                        changed = True
            if len(component) < 2:
                continue
            primary = _primary_of(component)
            kind = _strengthen_kind(primary)
            if kind is None:  # 방어 — group 구성상 도달하지 않는다
                continue
            supporting = sorted(
                i.interaction_id for i in component
                if i.interaction_id != primary.interaction_id
            )
            occ = "|".join(sorted(covered))
            clusters.append(InteractionCluster(
                cluster_definition_id=f"{element}:{kind.value}:{occ}",
                result_element=element,
                effect_kind=kind,
                primary_interaction_id=primary.interaction_id,
                supporting_interaction_ids=supporting,
            ))
    return clusters


def build_luck_hierarchy(
    composites: list[LuckComposite],
    target_level: str,
    target_key: str,
    semantics: list[RelationSemantics],
    stack_keys: dict[str, str] | None = None,
) -> LuckHierarchy:
    """이번 요청의 계층형 운 grounding을 조립한다.

    관계는 대상 기간 composite만이 아니라 **요청 스택 전체**(일·월·연)의 composite에서
    모은다. composite는 '그 레벨 소스가 참여한' 상호작용만 담으므로, 일진이 끼지 않는
    巳午未 방합(원국 시지 巳 + 세운 午 + 월운 未)은 월운 composite에만 존재한다.
    대상 레벨만 읽으면 상위 운이 만드는 결합이 통째로 빠진다(2026-07-27 실측).

    Args:
        composites: 이 기간에 대해 빌드된 LuckComposite 목록.
        target_level: 대상 기간 레벨 값('day'|'month'|'year').
        target_key: 대상 기간 키('2026-07-27' 등).
        semantics: P0가 확정한 관계 의미(운 관여분).
        stack_keys: 레벨 값 → 기간 키. 요청 스택을 명시해 인접 기간·후보 탐색 기간의
            관계가 섞이는 것을 막는다. 미지정 시 대상 레벨만 사용한다.

    Returns:
        원본 관계 전체 + 표현 클러스터를 담은 LuckHierarchy.
    """
    target = next(
        (c for c in composites
         if c.level.value == target_level and c.period_key == target_key),
        None,
    )
    if target is None:
        return LuckHierarchy(requested_period=target_key, requested_level=target_level)
    scope = dict(stack_keys or {})
    scope[target_level] = target_key
    in_scope = [c for c in composites if scope.get(c.level.value) == c.period_key]

    # 활성 층위 — 대상 기간 composite의 parent_context + 자기 간지. 다른 기간의
    # composite는 보지 않는다(무관한 연도 간지 혼입 방지, 2026-07-27 회귀).
    parent = target.parent_context
    layer_ganji: list[tuple[ParticipantLayer, str]] = []
    if parent.daewoon:
        layer_ganji.append((ParticipantLayer.DAEWOON, parent.daewoon))
    if parent.year:
        layer_ganji.append((ParticipantLayer.ANNUAL, parent.year))
    if parent.month:
        layer_ganji.append((ParticipantLayer.MONTHLY, parent.month))
    own_layer = {
        "day": ParticipantLayer.DAILY,
        "month": ParticipantLayer.MONTHLY,
        "year": ParticipantLayer.ANNUAL,
    }.get(target_level)
    own = f"{target.ganji.stem}{target.ganji.branch}"
    if own_layer is not None and all(lg[0] is not own_layer for lg in layer_ganji):
        layer_ganji.append((own_layer, own))
    active_layers = [
        PillarSummary(layer=layer, ganji=g, stem=g[0], branch=g[1])
        for layer, g in layer_ganji
        if len(g) >= 2
    ]

    index = _semantics_index(semantics)
    interactions: list[HierarchyInteraction] = []
    excluded: list[str] = []
    seen: set[tuple[str, frozenset[str], str, str]] = set()
    for comp in in_scope:
        for hit in comp.interactions:
            inter = _to_interaction(hit, _match_semantics(hit, index))
            if inter is None:
                if hit.relation_id not in excluded:
                    excluded.append(hit.relation_id)
                continue
            # 같은 관계가 여러 레벨 composite에 중복 기록될 수 있다. 라벨만으로
            # 묶으면 안 된다 — 원국 월지 亥와 일지 亥가 각각 만드는 관계는 라벨이
            # 같아도 서로 다른 발생이다. 참여 발생과 의미 효과까지 같을 때만 동일로 본다.
            key = (
                hit.relation_id,
                frozenset(inter.occurrence_ids),
                inter.result_element or "",
                inter.binding_state.value if inter.binding_state else "",
            )
            if key in seen:
                continue
            seen.add(key)
            interactions.append(inter)

    # 같은 관계를 상위 레벨 composite가 더 적은 참여 글자로도 기록한다(예: 연 레벨은
    # 巳午未 방합을 巳+午 2자로 본다). 참여가 부분집합인 쪽은 같은 현상의 축소판이므로
    # 표현에서 뺀다 — 의미를 바꾸는 것이 아니라 중복 표기를 지우는 것이다.
    interactions = [
        inter for inter in interactions
        if not any(
            other is not inter
            and other.interaction_id == inter.interaction_id
            and inter.occurrence_ids < other.occurrence_ids
            for other in interactions
        )
    ]

    clusters = _build_clusters(interactions)
    clustered = {mid for c in clusters for mid in c.member_ids}
    layers = sorted(
        {p.layer for i in interactions for p in i.participants},
        key=lambda x: list(ParticipantLayer).index(x),
    )
    return LuckHierarchy(
        requested_period=target_key,
        requested_level=target_level,
        active_layers=active_layers,
        interactions=interactions,
        clusters=clusters,
        interaction_summary=InteractionSummary(
            total_interactions=len(interactions),
            cross_layer_interactions=sum(1 for i in interactions if i.crosses_luck_layers),
            clustered_interactions=len(clustered),
            unclustered_interactions=len(interactions) - len(clustered),
            layers_present=layers,
        ),
        excluded_unknown_sources=excluded,
    )
