"""EventEngineV2 (Phase 7) — 재설계 6계층을 거버닝 스택으로 묶는 통합 엔진.

만세 결과의 운(대운·세운·월운·일운)을 **거버닝 스택**으로 결합한다: 세운 후보는 관할 대운+세운의
십성으로, 월운은 +월운, 일운은 +일운까지 한 신호셋으로 모아 십성 조합 후보를 만든 뒤
12운성→층위·흐름→게이트→관계·궁성→용신 품질→랭커 순으로 보정한다. 같은 입력이면 같은 출력.

reviewed:false 사전 초안 기반이므로 점수 절대값보다 상대 순위·신호·confidence_level을 신뢰한다
(docs/07 리스크 1). LLM은 이 점수를 계산하지 않는다(절대 원칙 1).
"""

from __future__ import annotations

from pathlib import Path

from saju_shared_types.constants import BRANCH_ELEMENT, STEM_ELEMENT
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.event_engine import (
    TEN_GOD_GROUP,
    TWELVE_STAGE_KO_TO_KEY,
    ConfidenceLevel,
    EventCandidateV2,
    EventQuality,
    LuckLayer,
    Pillar4,
    PolarityRole,
    RelationKind,
    TenGod,
    TenGodGroup,
    TwelveStage,
    lei_rank_key,
)
from saju_shared_types.event_taxonomy_v2 import (
    CONFIDENCE_KO,
    EVENT_TYPE,
    PALACE_KO,
    QUALITY_KO,
)
from saju_shared_types.events import (
    Confidence,
    EventCandidate,
    EventPolarity,
    EventType,
    Signal,
)
from saju_shared_types.ganji_calendar import GanjiLevel, RelationHit, RelationType
from saju_shared_types.life_event import LifeEventRow
from saju_shared_types.luck import DaewoonItem, LuckPillar
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.wealth_capacity import WealthCapacity

from .addendum_gate_modifier import AddendumGateModifier, GateContext
from .cohort_calibration import CohortStats
from .event_ranker import EventRanker, RankContext
from .event_scoring import favorability_map
from .ganji_calendar import relation_hits
from .layer_flow_modifier import LayerFlowModifier
from .life_fit_ranker import LifeFitRanker
from .llm_event_serializer import reason_codes_ko
from .reality_context import RealityContext
from .relation_palace_engine import RelationActivation, RelationPalaceEngine
from .ten_god_brancher import TenGodEventBrancher
from .twelve_stage_modifier import TwelveStageModifier
from .wealth_activation_modifier import WealthActivationModifier
from .wealth_capacity import analyze_wealth_capacity, detect_wealth_activations
from .yongi_quality_engine import YongiQualityEngine

# 만세 운 계층 → 새 엔진 LuckLayer.
_LEVEL_TO_LAYER: dict[GanjiLevel, LuckLayer] = {
    GanjiLevel.DAEWOON: LuckLayer.DAEWOON,
    GanjiLevel.YEAR: LuckLayer.SEWOON,
    GanjiLevel.MONTH: LuckLayer.WOLWOON,
    GanjiLevel.DAY: LuckLayer.ILWOON,
}
# 합충형파해 RelationType → 발동 종류(RelationKind). 공망류는 None(GateContext.void_active로 처리).
_REL_KIND = {
    RelationType.STEM_COMBINATION: "HAP",
    RelationType.SIX_COMBINATION: "HAP",
    RelationType.THREE_HARMONY_CONTRIB: "HAP",
    RelationType.DIRECTIONAL_CONTRIB: "HAP",
    RelationType.BRANCH_CLASH: "CHUNG",
    RelationType.BRANCH_BREAK: "PA",
    RelationType.HARM: "HAE",
    RelationType.PUNISHMENT_TRIPLE: "HYEONG",
    RelationType.PUNISHMENT_MUTUAL: "HYEONG",
    RelationType.SELF_PUNISHMENT: "HYEONG",
}
_VOID_TYPES = {
    RelationType.VOID_FILL,
    RelationType.VOID_TRIGGER_CLASH,
    RelationType.VOID_RELEASE_COMBINE,
}
_POS_PILLAR: dict[str, Pillar4] = {
    "year": Pillar4.YEAR, "month": Pillar4.MONTH,
    "day": Pillar4.DAY, "hour": Pillar4.HOUR,
}
# 오행 용기신 역할(한글) → 극성.
_FAV_ROLE: dict[str, PolarityRole] = {
    "용신": PolarityRole.YONG, "희신": PolarityRole.HEE,
    "기신": PolarityRole.GI, "구신": PolarityRole.GI,
}
# 오행 상생(생, 生): 木→火→土→金→水→木. 한신의 간접 길흉 판정에 쓴다.
_GENERATES: dict[str, str] = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
# TenGod → 그룹 문자열(RankContext 신호 분류용).
_GROUP_OF: dict[TenGod, str] = {g: grp.value for g, grp in TEN_GOD_GROUP.items()}

# 정렬은 공식 정렬축 lei_rank_key를 쓴다(LIFE_EVENT_INFERENCE.md §1, 엔진·랭커 공용).
# 엔진 단독에선 life_fit·personal_match=0이라 (사건화 강도, display score) 순서로 환원된다.
_rank_key = lei_rank_key


class EventEngineV2:
    """6계층 통합 — score/score_years는 EventCandidateV2 목록을 반환한다."""

    def __init__(self, dictionaries_dir: Path) -> None:
        """재설계 6계층 + 만세 신호 추출에 필요한 사전을 로드한다."""
        self._brancher = TenGodEventBrancher(dictionaries_dir)
        self._stage = TwelveStageModifier(dictionaries_dir)
        self._flow = LayerFlowModifier(dictionaries_dir)
        self._gate = AddendumGateModifier()
        self._relpalace = RelationPalaceEngine(dictionaries_dir)
        self._yongi = YongiQualityEngine(dictionaries_dir)
        self._wealth_act = WealthActivationModifier()
        self._ranker = EventRanker(dictionaries_dir)

    # ── 공개 API ─────────────────────────────────────────────────

    def score(
        self,
        result: ManseV2Result,
        levels: set[GanjiLevel] | None = None,
        fav_override: dict[str, str] | None = None,
        *,
        occupation_status: str | None = None,
        relationship_status: str | None = None,
    ) -> list[EventCandidateV2]:
        """만세 결과의 운을 거버닝 스택으로 스코어링해 EventCandidateV2 목록을 산출한다."""
        if result.pillars is None or result.luck_cycles is None:
            return []
        wanted = levels or set(GanjiLevel)
        fav_map = fav_override if fav_override is not None else favorability_map(result)
        capacity = analyze_wealth_capacity(result)  # 원국 횡재 그릇(1회 — 발동 가산 배율)
        idx = _StackIndex(result)
        out: list[EventCandidateV2] = []
        if GanjiLevel.DAEWOON in wanted:
            for dwi in result.luck_cycles.daewoon_table:
                label = f"{dwi.approx_start_date.year}~{dwi.approx_end_date.year}"
                out += self._score_target(
                    result, GanjiLevel.DAEWOON, label, _daewoon_pillar(dwi), idx, fav_map,
                    occupation_status, relationship_status, capacity,
                )
        for level, pillars in (
            (GanjiLevel.YEAR, result.luck_cycles.yearly_luck),
            (GanjiLevel.MONTH, result.luck_cycles.monthly_luck),
            (GanjiLevel.DAY, result.luck_cycles.daily_luck),
        ):
            if level in wanted:
                for p in pillars:
                    out += self._score_target(
                        result, level, p.label, p, idx, fav_map,
                        occupation_status, relationship_status, capacity,
                    )
        return sorted(out, key=_rank_key)

    def score_years(
        self,
        result: ManseV2Result,
        years: list[int],
        fav_override: dict[str, str] | None = None,
        *,
        occupation_status: str | None = None,
        relationship_status: str | None = None,
    ) -> list[EventCandidateV2]:
        """지정 세운 연도를 직접 스코어링한다(용신 검증용 — 과거 연도 포함)."""
        if result.pillars is None or result.luck_cycles is None:
            return []
        fav_map = fav_override if fav_override is not None else favorability_map(result)
        capacity = analyze_wealth_capacity(result)
        idx = _StackIndex(result)
        out: list[EventCandidateV2] = []
        for y in years:
            p = idx.sewoon_by_year.get(y)
            if p is None:
                continue
            out += self._score_target(
                result, GanjiLevel.YEAR, p.label, p, idx, fav_map,
                occupation_status, relationship_status, capacity,
            )
        return sorted(out, key=_rank_key)

    # ── 레거시 호환 API (다운스트림 DTO) ─────────────────────────

    def score_legacy(
        self,
        result: ManseV2Result,
        levels: set[GanjiLevel] | None = None,
        fav_override: dict[str, str] | None = None,
        *,
        occupation_status: str | None = None,
        relationship_status: str | None = None,
    ) -> list[EventCandidate]:
        """score()를 레거시 EventCandidate 목록으로 변환(다운스트림 호환)."""
        return [to_legacy_candidate(c) for c in self.score(
            result, levels, fav_override,
            occupation_status=occupation_status, relationship_status=relationship_status,
        )]

    def score_legacy_years(
        self,
        result: ManseV2Result,
        years: list[int],
        fav_override: dict[str, str] | None = None,
        *,
        occupation_status: str | None = None,
        relationship_status: str | None = None,
    ) -> list[EventCandidate]:
        """score_years()를 레거시 EventCandidate 목록으로 변환(용신 검증 호환)."""
        return [to_legacy_candidate(c) for c in self.score_years(
            result, years, fav_override,
            occupation_status=occupation_status, relationship_status=relationship_status,
        )]

    def score_legacy_personalized(
        self,
        result: ManseV2Result,
        levels: set[GanjiLevel] | None = None,
        fav_override: dict[str, str] | None = None,
        *,
        signature: list[LifeEventRow] | None = None,
        reality_context: RealityContext | None = None,
        cohort: CohortStats | None = None,
    ) -> list[EventCandidate]:
        """score() → LifeFitRanker(개인 시그니처·코호트·현실 맥락) → 레거시 후보.

        시그니처·맥락·코호트가 전부 없으면 score_legacy()와 동치(LEI 필드 0). subject_id로 조회한
        개인 시그니처·코호트가 있으면 LEI 정렬축(life_fit>confidence>personal_match>score)이 출력에
        반영된다(다운스트림 정렬도 LEI-aware). DB 게이트는 호출 서비스가 담당.
        """
        v2 = self.score(result, levels, fav_override)
        v2 = LifeFitRanker().rank(
            v2, signature=signature, reality_context=reality_context, cohort=cohort,
        )
        return [to_legacy_candidate(c) for c in v2]

    @staticmethod
    def readable_path(candidate: EventCandidate) -> list[str]:
        """후보 근거 경로(reason_codes) → 사람용 한글 경로."""
        return reason_codes_ko(candidate.evidence_path)

    # ── 한 시점 스코어링 ──────────────────────────────────────────

    def _score_target(
        self,
        result: ManseV2Result,
        level: GanjiLevel,
        label: str,
        target: LuckPillar,
        idx: _StackIndex,
        fav_map: dict[str, str],
        occupation_status: str | None,
        relationship_status: str | None,
        capacity: WealthCapacity,
    ) -> list[EventCandidateV2]:
        """거버닝 스택으로 한 시점의 후보를 만들고 6계층 보정을 적용한다."""
        stack = idx.stack_for(level, label, target)
        if not stack:
            return []
        signals = [
            s
            for layer, pillar in stack
            for s in self._brancher.collect_from_pillar(pillar, layer)
        ]
        if not signals:
            return []
        cands = self._brancher.branch(signals, label)
        if not cands:
            return []
        # 12운성 상태 — 스택 각 층 지지 운성.
        stage_by_layer = {
            layer: st
            for layer, pillar in stack
            if (st := _stage_of(pillar)) is not None
        }
        cands = self._stage.apply(cands, stage_by_layer)
        cands = self._flow.apply(cands, signals)
        # 게이트 — 스택 전체 십성, 층위, 공망, 프로필.
        present_gods = {s.ten_god for s in signals}
        layers = {layer for layer, _ in stack}
        hits = self._relation_hits(result, level, target)
        void_active = any(h.type in _VOID_TYPES for h in hits)
        gate_ctx = GateContext(
            present_gods=present_gods, layers=layers, void_active=void_active,
            occupation_status=occupation_status, relationship_status=relationship_status,
        )
        cands = self._gate.apply(cands, gate_ctx)
        # 발동·궁성 — 해당 시점 관계 적중.
        activations = _activations(hits, _LEVEL_TO_LAYER[level])
        cands = self._relpalace.apply(cands, activations)
        # 용신 품질 — 시점 유입 글자 오행의 용기신 역할.
        role = _period_role(target, fav_map)
        if role is not PolarityRole.NEUTRAL:
            cands = [c.model_copy(update={"polarity_role": role}) for c in cands]
            cands = self._yongi.apply(cands)
        # 횡재 발동 — 원국 그릇 × 운 완성(재성국/충개고/투간/식상생재)을 재물 후보에 보수 가산.
        cands = self._wealth_act.apply(
            cands, capacity, self._wealth_activations(result, stack, capacity),
        )
        # 증거 등급·충돌 해결.
        rank_ctx = _rank_context(
            activations, present_gods, cands, occupation_status, relationship_status,
        )
        return self._ranker.rank(cands, rank_ctx)

    def _relation_hits(
        self, result: ManseV2Result, level: GanjiLevel, target: LuckPillar
    ) -> list[RelationHit]:
        """시점 기둥의 합충형파해·공망 적중."""
        assert result.pillars is not None
        return relation_hits(
            level, target.stem, target.branch,
            target.relations_to_chart, target.gongmang_activation, result.pillars,
        )

    def _wealth_activations(
        self,
        result: ManseV2Result,
        stack: list[tuple[LuckLayer, LuckPillar]],
        capacity: WealthCapacity,
    ) -> list[str]:
        """거버닝 스택(운)+원국으로 그 시점 재물 발동을 판정한다(운 완성 경로 포함, Phase 2)."""
        assert result.pillars is not None
        p = result.pillars
        day_pillar = p.day
        if day_pillar is None:
            return []
        natal_branches = {
            pil.branch for pil in (p.year, p.month, p.day, p.hour) if pil is not None
        }
        luck_branches = {pillar.branch for _layer, pillar in stack}
        luck_stem_elements = {
            str(STEM_ELEMENT[Stem(pillar.stem)]) for _layer, pillar in stack
        }
        return detect_wealth_activations(
            day_element=str(STEM_ELEMENT[Stem(day_pillar.stem)]),
            wealth_element=capacity.wealth_element,
            natal_branches=natal_branches,
            luck_branches=luck_branches,
            luck_stem_elements=luck_stem_elements,
        )


# ── 거버닝 스택 인덱스 ─────────────────────────────────────────────


class _StackIndex:
    """관할 대운·세운·월운 조회 인덱스(거버닝 스택 구성용)."""

    def __init__(self, result: ManseV2Result) -> None:
        lc = result.luck_cycles
        assert lc is not None
        self.dw_by_year: dict[int, DaewoonItem] = {}
        self.sewoon_by_year: dict[int, LuckPillar] = {}
        self.wolwoon_by_ym: dict[str, LuckPillar] = {}
        for dwi in lc.daewoon_table:
            for y in range(dwi.approx_start_date.year, dwi.approx_end_date.year + 1):
                self.dw_by_year.setdefault(y, dwi)
            for p in dwi.sewoon or []:
                if p.label.isdigit():
                    self.sewoon_by_year.setdefault(int(p.label), p)
        for p in lc.yearly_luck:
            if p.label.isdigit():
                self.sewoon_by_year[int(p.label)] = p
        for p in lc.monthly_luck:
            self.wolwoon_by_ym.setdefault(p.label, p)

    def stack_for(
        self, level: GanjiLevel, label: str, target: LuckPillar
    ) -> list[tuple[LuckLayer, LuckPillar]]:
        """시점 종류에 따라 (층위, 기둥) 스택을 구성한다(상위 관할 운 + 시점)."""
        if level is GanjiLevel.DAEWOON:
            return [(LuckLayer.DAEWOON, target)]
        year = int(label[:4]) if label[:4].isdigit() else None
        stack: list[tuple[LuckLayer, LuckPillar]] = []
        if year is not None:
            dwi = self.dw_by_year.get(year)
            if dwi is not None:
                stack.append((LuckLayer.DAEWOON, _daewoon_pillar(dwi)))
        if level is GanjiLevel.YEAR:
            stack.append((LuckLayer.SEWOON, target))
            return stack
        # 월운·일운: 관할 세운 추가.
        if year is not None and year in self.sewoon_by_year:
            stack.append((LuckLayer.SEWOON, self.sewoon_by_year[year]))
        if level is GanjiLevel.MONTH:
            stack.append((LuckLayer.WOLWOON, target))
            return stack
        # 일운: 관할 월운(YYYY-MM) 추가 후 일운.
        ym = label[:7]
        if ym in self.wolwoon_by_ym:
            stack.append((LuckLayer.WOLWOON, self.wolwoon_by_ym[ym]))
        stack.append((LuckLayer.ILWOON, target))
        return stack


# ── 보조 함수 ──────────────────────────────────────────────────────


def _daewoon_pillar(d: DaewoonItem) -> LuckPillar:
    """대운 항목을 LuckPillar로 투영(스택 신호 수집·운성용)."""
    return LuckPillar(
        label=d.ganji, period_type="daewoon", ganji=d.ganji,
        stem=d.stem, branch=d.branch,
        stem_ten_god=d.stem_ten_god, branch_ten_god=d.branch_ten_god,
        twelve_unseong=d.twelve_unseong,
        relations_to_chart=d.relations_to_chart,
        gongmang_activation=d.gongmang_activation,
        luck_sinsal=d.luck_sinsal,
    )


def _stage_of(pillar: LuckPillar) -> TwelveStage | None:
    """기둥 지지 12운성(한글) → TwelveStage enum."""
    return TWELVE_STAGE_KO_TO_KEY.get(pillar.twelve_unseong or "")


def _activations(hits: list[RelationHit], layer: LuckLayer) -> list[RelationActivation]:
    """합충형파해 적중 → (관계종류, 자극궁, 층위) 발동 목록(공망류 제외)."""
    out: list[RelationActivation] = []
    for hit in hits:
        kind = _REL_KIND.get(hit.type)
        if kind is None:
            continue
        position = "stem" if hit.type is RelationType.STEM_COMBINATION else "branch"
        for ref in hit.natal_refs:
            palace = _POS_PILLAR.get(ref.position)
            if palace is not None:
                out.append(RelationActivation(
                    RelationKind(kind), palace, layer, position=position,
                ))
    return out


def _han_gen_role(element: str, fav_map: dict[str, str]) -> PolarityRole | None:
    """한신 오행의 간접(생, 生) 길흉 — 생하는 대상의 역할로 약한 길/흉을 판정.

    element가 한신일 때만 동작한다. 한신이 생하는 오행이 용신·희신이면 약한 길(HAN_GOOD),
    기신·구신이면 약한 흉(HAN_BAD), 그 외(한신/무관)면 None(중립). 한신이 아니면 None.
    """
    if fav_map.get(element) != "한신":
        return None
    generated_role = _FAV_ROLE.get(fav_map.get(_GENERATES.get(element, ""), ""))
    if generated_role in (PolarityRole.YONG, PolarityRole.HEE):
        return PolarityRole.HAN_GOOD
    if generated_role is PolarityRole.GI:
        return PolarityRole.HAN_BAD
    return None


def _period_role(target: LuckPillar, fav_map: dict[str, str]) -> PolarityRole:
    """시점 유입 글자(천간 우선, 지지 보조) 오행의 용기신 역할 → 극성.

    1) 직접 역할(용·희·기·구) — 천간 우선, 지지 보조. 2) 천간·지지 모두 직접 역할이 없을 때만
    한신의 생(生) 관계로 간접 길흉(약)을 판정한다(직접 신호를 덮지 않는 보조 계층).
    """
    try:
        stem_el = str(STEM_ELEMENT[Stem(target.stem)])
        branch_el = str(BRANCH_ELEMENT[Branch(target.branch)])
    except (KeyError, ValueError):
        return PolarityRole.NEUTRAL
    stem_lbl = fav_map.get(stem_el, "")
    branch_lbl = fav_map.get(branch_el, "")
    # 0) 천간·지지가 같은 방향으로 겹친 강한 신호 — 모두 용신(강한 용신운)/모두 흉(기·구).
    if stem_lbl == "용신" and branch_lbl == "용신":
        return PolarityRole.YONG_STRONG
    if stem_lbl in ("기신", "구신") and branch_lbl in ("기신", "구신"):
        return PolarityRole.GI_STRONG
    # 1) 직접 역할(천간 우선).
    for lbl in (stem_lbl, branch_lbl):
        direct = _FAV_ROLE.get(lbl)
        if direct is not None:
            return direct
    # 2) 직접 역할 없음 → 한신 생(生) 간접 길흉(천간 우선).
    for el in (stem_el, branch_el):
        indirect = _han_gen_role(el, fav_map)
        if indirect is not None:
            return indirect
    return PolarityRole.NEUTRAL


def _rank_context(
    activations: list[RelationActivation],
    present_gods: set[TenGod],
    cands: list[EventCandidateV2],
    occupation_status: str | None,
    relationship_status: str | None,
) -> RankContext:
    """충돌 해결 priority_rules가 참조하는 컨텍스트 플래그를 도출한다."""
    flags: set[str] = set()
    palaces = {a.palace for a in activations}
    if Pillar4.DAY in palaces:
        flags.add("day_branch_activated")
    if Pillar4.MONTH in palaces:
        flags.add("month_pillar_activated")
    if Pillar4.HOUR in palaces:
        flags.add("hour_pillar_activated")
    groups = {TenGodGroup(_GROUP_OF[g]) for g in present_gods if g in _GROUP_OF}
    has_wealth = TenGodGroup.WEALTH in groups
    has_authority = TenGodGroup.AUTHORITY in groups
    has_output = TenGodGroup.OUTPUT in groups
    has_resource = TenGodGroup.RESOURCE in groups
    has_peer = TenGodGroup.PEER in groups
    if has_wealth or has_authority:
        flags.add("wealth_or_authority_signal")
    if has_resource or has_wealth:
        flags.add("resource_or_wealth_signal")
    if has_authority or has_output:
        flags.add("authority_or_output_signal")
    if has_output:
        flags.add("output_signal")
    if has_wealth:
        flags.add("wealth_signal")
    if has_peer:
        flags.add("peer_signal")
    if relationship_status in ("dating", "married"):
        flags.add("relationship_context_exists")
    if occupation_status in ("employee", "business_owner", "freelancer"):
        flags.add("career_context_exists")
    if occupation_status != "business_owner":
        flags.add("no_business_context")
    if relationship_status in (None, "single", "divorced"):
        flags.add("childbirth_profile_gate_false")
    ekeys = {str(c.event_key) for c in cands}
    if "relocation" in ekeys and Pillar4.DAY in palaces:
        flags.add("relocation_relation_signal_exists")
    return RankContext(flags=flags)


# ── 레거시 어댑터 (EventCandidateV2 → 다운스트림 DTO EventCandidate) ──
# 하드 스위치: 새 엔진이 산출하되 다운스트림(context_reducer·report·chat·past_validation)은
# 기존 EventCandidate를 소비한다. 새 차원(품질·확신도·궁성·단계)은 동반 신호로 표면화(풍부화).
_CONF_TO_LEGACY: dict[ConfidenceLevel, Confidence] = {
    ConfidenceLevel.HIGH_PROBABILITY_EVENT: Confidence.HIGH,
    ConfidenceLevel.STRONG_EVENT_CANDIDATE: Confidence.MEDIUM_HIGH,
    ConfidenceLevel.EVENT_CANDIDATE: Confidence.MEDIUM,
    ConfidenceLevel.WEAK_EVENT_CANDIDATE: Confidence.MEDIUM_LOW,
    ConfidenceLevel.THEME_ONLY: Confidence.LOW,
}
_QUALITY_TO_POLARITY: dict[EventQuality, EventPolarity] = {
    EventQuality.OPPORTUNITY: EventPolarity.POSITIVE,
    EventQuality.ACHIEVEMENT: EventPolarity.POSITIVE,
    EventQuality.RESOLUTION: EventPolarity.POSITIVE,
    EventQuality.LOSS: EventPolarity.NEGATIVE_OR_FORCED,
    EventQuality.PRESSURE: EventPolarity.NEGATIVE_OR_FORCED,
    EventQuality.CONFLICT: EventPolarity.NEGATIVE_OR_FORCED,
    EventQuality.DELAY: EventPolarity.CONDITIONAL,
    EventQuality.MIXED: EventPolarity.CONDITIONAL,
}
_EVENT_TYPE_LEGACY: dict[str, EventType] = {
    "progress": EventType.PROGRESS, "instant": EventType.INSTANT, "hybrid": EventType.HYBRID,
}


def to_legacy_candidate(c: EventCandidateV2) -> EventCandidate:
    """EventCandidateV2 → 레거시 EventCandidate(다운스트림 DTO). 신 차원은 동반 신호로 표면화."""
    quality_txt = QUALITY_KO.get(c.quality, "") if c.quality else ""
    conf_txt = CONFIDENCE_KO.get(c.confidence_level, "")
    palace_txt = PALACE_KO.get(c.palace, "") if c.palace else ""
    head = [b for b in (conf_txt, quality_txt, palace_txt, c.event_phase) if b]
    signals: list[Signal] = []
    if head:  # 사건화 강도·품질·궁성·단계 — LLM 입력 풍부화(첫 동반 신호).
        signals.append(Signal(
            type="materialization", name="materialization",
            effect=" · ".join(head), weight=float(c.score),
        ))
    for ko in reason_codes_ko(c.reason_codes):
        signals.append(Signal(type="reason", name=ko, effect=ko, weight=0.0))
    # 불안정 신호 텍스트 보존(공망 → context_reducer 검토월 판정).
    if any(r.startswith("VOID_") for r in c.reason_codes):
        signals.append(Signal(type="void", name="void", effect="공망 지연", weight=0.0))
    polarity = (
        _QUALITY_TO_POLARITY.get(c.quality, EventPolarity.NEUTRAL)
        if c.quality else EventPolarity.NEUTRAL
    )
    etype = _EVENT_TYPE_LEGACY.get(EVENT_TYPE.get(c.event_key, "progress"), EventType.PROGRESS)
    return EventCandidate(
        event_key=c.event_key,
        event_type=etype,
        period=c.period,
        score=c.score,
        confidence=_CONF_TO_LEGACY.get(c.confidence_level, Confidence.LOW),
        polarity=polarity,
        signals=signals,
        evidence_path=list(c.reason_codes),
        raw_total=c.raw_score,
        life_fit=c.life_fit,
        personal_match=c.personal_match,
    )
