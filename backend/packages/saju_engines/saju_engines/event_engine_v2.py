"""EventEngineV2 (Phase 7) — 재설계 6계층을 거버닝 스택으로 묶는 통합 엔진.

만세 결과의 운(대운·세운·월운·일운)을 **거버닝 스택**으로 결합한다: 세운 후보는 관할 대운+세운의
십성으로, 월운은 +월운, 일운은 +일운까지 한 신호셋으로 모아 십성 조합 후보를 만든 뒤
12운성→층위·흐름→게이트→관계·궁성→용신 품질→랭커 순으로 보정한다. 같은 입력이면 같은 출력.

reviewed:false 사전 초안 기반이므로 점수 절대값보다 상대 순위·신호·confidence_level을 신뢰한다
(docs/07 리스크 1). LLM은 이 점수를 계산하지 않는다(절대 원칙 1).
"""

from __future__ import annotations

import math
import threading as _threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType

from saju_manse_analysis.relations.hap_modes import resolve_stem_hap
from saju_manse_analysis.yongsin.operational_role_config import is_unfavorable_role

from saju_shared_types.constants import BRANCH_ELEMENT, STEM_ELEMENT
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.event_engine import (
    TEN_GOD_GROUP,
    TEN_GOD_KO_TO_KEY,
    TWELVE_STAGE_KO_TO_KEY,
    ConfidenceLevel,
    EventCandidateV2,
    EventKeyV2,
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
from saju_shared_types.risk_engine import RiskCandidate, RiskEngineMode
from saju_shared_types.wealth_capacity import WealthCapacity

from .addendum_gate_modifier import AddendumGateModifier, GateContext
from .career_mobility_modifier import CareerMobilityContext, CareerMobilityModifier
from .cohort_calibration import CohortStats
from .contribution_provenance import (
    CandidateAlignment,
    EvidenceRole,
    FavorabilityEffect,
    FormulaRelation,
    ModifierContributionEvidence,
    OccurrenceAttribution,
    ProvenanceRecorder,
    SupportEligibility,
)
from .daewoon_background import (
    DaewoonHwaBackground,
    derive_daewoon_hwa_background,
)
from .event_ranker import EventRanker, RankContext
from .event_scoring import daewoon_transition_boost, favorability_map
from .exam_outcome_modifier import ExamOutcomeModifier
from .ganji_calendar import relation_hits
from .layer_evidence_scope import normalize_layers
from .layer_flow_modifier import LayerFlowModifier
from .life_fit_ranker import LifeFitRanker
from .llm_event_serializer import reason_codes_ko
from .marriage_awareness_seed import produce_mt1_awareness_seeds
from .marriage_directional_tag import apply_mt3_directional_tags
from .marriage_emergence_modifier import (
    MarriageEmergenceModifier,
    analyze_marriage_emergence_natal,
)
from .marriage_flow_modifier import (
    MarriageFlowModifier,
    MarriageFlowNatal,
    analyze_marriage_flow_natal,
    apply_marriage_gender_weight,
    detect_marriage_flow_activations,
)
from .reality_context import RealityContext
from .relation_palace_engine import RelationActivation, RelationPalaceEngine
from .risk_engine import (
    HealthContext,
    LegalProcessContext,
    MobilityContext,
    RelationFact,
    RelationshipContext,
    RiskEngine,
    SelectionContext,
    build_raw_period_facts,
)
from .ten_god_brancher import TenGodEventBrancher, TransitSignal
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
# 천간충 4쌍(甲庚·乙辛·丙壬·丁癸) — 만세 calendar 관계 경로엔 없어 어댑터로 직접 계산한다
# (manse_core 불변, CLAUDE.md "어댑터만 추가"). 천충지충 동시 퇴직 리스크 판정용(자료 13-1).
_STEM_CLASH_PAIRS: frozenset[frozenset[str]] = frozenset({
    frozenset({"甲", "庚"}), frozenset({"乙", "辛"}),
    frozenset({"丙", "壬"}), frozenset({"丁", "癸"}),
})
# 이직 분류(자료 12) — 최종 favorability 임계. 이하=압박성, 이상=기회성, 사이=중립.
_JOBCHANGE_PRESSURE_TH = -0.2
_JOBCHANGE_OPPORTUNITY_TH = 0.2
# TenGod → 그룹 문자열(RankContext 신호 분류용).
_GROUP_OF: dict[TenGod, str] = {g: grp.value for g, grp in TEN_GOD_GROUP.items()}

# 정렬은 공식 정렬축 lei_rank_key를 쓴다(LIFE_EVENT_INFERENCE.md §1, 엔진·랭커 공용).
# 엔진 단독에선 life_fit·personal_match=0이라 (사건화 강도, display score) 순서로 환원된다.
_rank_key = lei_rank_key


@dataclass(frozen=True)
class RelationActivationProjection:
    """관계 벡터 shadow용 발동 1건 불변 projection(P1-6 §12).

    스코어링이 이미 만든 RelationActivation의 primitive 복사 — 원본 객체를 들고
    나가지 않아 사이드카가 엔진 상태를 변형할 경로가 없다.
    """

    kind: str                   # RelationKind.value
    palace: str                 # Pillar4.value
    layer: str                  # LuckLayer.value
    position: str               # 'stem' | 'branch'
    hap_subtype: str | None
    element: str | None


@dataclass(frozen=True)
class RelationshipShadowProjection:
    """기간 1건의 관계 탐지 결과 불변 snapshot(P1-6 §12 — chat 배선 계약).

    수집 시점 = relpalace 단계(기존 탐지 결과가 전부 계산된 직후). 탐지기 재호출·
    yield 변경 없이 이미 존재하는 값만 primitive로 복사한다 — 신호·후보 0으로
    조기 반환된 기간은 legacy도 비평가라 관측 대상이 아니다.
    """

    layer: str                              # LuckLayer.value(채점 대상 층)
    label: str                              # 기간 라벨('2027'/'2027-04'/'1995~2004')
    luck_stem: str                          # 운 천간(한자) — EXACT trigger 재료
    luck_branch: str                        # 운 지지(한자)
    activations: tuple[RelationActivationProjection, ...]
    spouse_palace_clashed: bool             # 일지 충 동반(MT2 blocker 판정 재료)


class EventEngineV2:
    """6계층 통합 — score/score_years는 EventCandidateV2 목록을 반환한다."""

    def __init__(
        self,
        dictionaries_dir: Path,
        *,
        enable_mt1_awareness: bool = False,
        enable_mt2_emergence: bool = False,
        enable_mt3_directional: bool = False,
        enable_mt4_subtype: str = "off",
        risk_mode: str | None = None,
        daewoon_hwa_mode: str = "current",
        enable_resource_clash_renewal: bool = False,
    ) -> None:
        """재설계 6계층 + 만세 신호 추출에 필요한 사전을 로드한다.

        Args:
            dictionaries_dir: 사전 원본 루트.
            enable_mt1_awareness: MT1 일간 干合 awareness seed 생성 활성화(기본 OFF — feature
                flag). OFF면 seed producer를 완전히 비활성화해 기존 결과가 불변이다
                (MARRIAGE_TIMING_ENHANCEMENT §6, reviewed:false).
            enable_mt2_emergence: MT2 일지 투출 글자 운 회귀 증폭 활성화(기본 OFF — feature flag).
                OFF면 modifier를 완전히 비활성화해 기존 결과가 불변이다(§7, reviewed:false).
            enable_mt3_directional: MT3 방합 배우자궁 게이트 태깅 활성화(기본 OFF — feature flag).
                점수는 안 바꾸고 reason_code 태그만 부여한다(§8, A안). OFF면 결과 불변.
            enable_mt4_subtype: MT4 관계 도메인 HAP 합 종류 재가중(§9). 'off'(기본)=불변 /
                'shadow'=점수·reason 불변 + diagnostics(mt4_shadow)만 기록 / 'apply'=실제 재분배.
            risk_mode: 위험 엔진 모드 강제("off"/"shadow"/"expose", RISK_ENGINE.md). None(기본)
                이면 risk_engine_config.RISK_ENGINE_MODE를 score() 호출 시점에 읽는다(테스트
                monkeypatch 가능). off면 위험 계산을 전혀 하지 않아 기존 출력이 byte-identical.
            daewoon_hwa_mode: 대운 합화 배경 처리(기본 'current' — 기존 ±3% 랭킹 반영).
                'post_selection'이면 점수·reason_codes를 건드리지 않고 시점 배경 맵만
                채운다(DW-HWA 감사 판정 반영). 기본값이 'current'라 production 불변.
            enable_resource_clash_renewal: 인성 동요 신호(기본 OFF — feature flag,
                2026-08-10 승인). 운 충이 원국 인성 글자를 칠 때 문서 교체 계열
                (contract_document/relocation/career_change) 가산 + 인성군 세력 게이트
                (relation_target_ten_god_rules, reviewed:false). OFF면 기존 결과 불변.
        """
        self._enable_mt1_awareness = enable_mt1_awareness
        self._enable_mt2_emergence = enable_mt2_emergence
        self._enable_mt3_directional = enable_mt3_directional
        self._mt4_mode = enable_mt4_subtype
        self._enable_resource_clash_renewal = enable_resource_clash_renewal
        # MT4 shadow 진단 사이드채널(결과 payload·LLM 입력 미포함 — debug-only). score()마다 초기화.
        self.mt4_shadow: list[dict] = []
        # ── 위험 엔진 R0(RISK_ENGINE.md) — 기회 파이프라인과 독립 shadow 사이드채널 ──
        # risk_shadow는 LLM 입력·리포트·토큰에 주입하지 않는다(구조화 로그/QA 전용).
        self._risk_mode_override = risk_mode
        self.risk_shadow: list[RiskCandidate] = []
        # 요청 로컬 위험 수집 sink(감수 62차 P0③ — 싱글턴 scorer의 비동기/
        # 스레드 interleaving 오귀속 차단): score() 동안 thread-local에
        # 수집하고, EXPOSE 경로는 take_risk_shadow()(불변 tuple)만 읽는다.
        # self.risk_shadow는 레거시 QA 사이드채널로만 유지(EXPOSE 사용 금지).
        self._daewoon_hwa_mode = daewoon_hwa_mode
        # 대운 합화 시점 배경 sink — risk_shadow와 동일한 요청 로컬 패턴.
        # 싱글턴 필드로 두면 동시 요청에서 마지막 호출분에 덮인다. 이 맵은 (랭킹이 아니라)
        # 서사 렌더러가 실제로 읽을 값이므로 요청 로컬이어야 한다.
        self._dw_bg_tls = _threading.local()
        self._risk_tls = _threading.local()
        # 관계 벡터 shadow projection sink(P1-6 §12) — risk_shadow와 동일한 요청
        # 로컬 패턴: score() 동안 thread-local에 수집, take_relationship_shadow()로
        # 이 호출분의 불변 tuple만 소비한다(점수·후보·가드 어디에도 관여하지 않음).
        self._rel_shadow_tls = _threading.local()
        # shadow 컨텍스트(감수 19차 — QA·시나리오 밀도 전용): set_risk_shadow_contexts로
        # 주입하면 shadow 후보 생성에 현실 컨텍스트(선발·관계·이동)가 반영된다.
        # LLM 입력·긍정 파이프라인과 무관하며 off 모드에선 사용되지 않는다.
        self._risk_shadow_selection: SelectionContext | None = None
        self._risk_shadow_relationships: list[RelationshipContext] | None = None
        self._risk_shadow_mobility: list[MobilityContext] | None = None
        self._risk_shadow_health: list[HealthContext] | None = None
        self._risk_shadow_legal: list[LegalProcessContext] | None = None
        self._risk_shadow_selections: list[SelectionContext] | None = None
        try:
            self._risk: RiskEngine | None = RiskEngine(dictionaries_dir)
        except FileNotFoundError:
            # fresh-clone graceful — risks/ 사전이 없으면 위험 엔진만 비활성(기존 기능 무영향).
            self._risk = None
        self._brancher = TenGodEventBrancher(dictionaries_dir)
        self._stage = TwelveStageModifier(dictionaries_dir)
        self._flow = LayerFlowModifier(dictionaries_dir)
        self._gate = AddendumGateModifier()
        self._relpalace = RelationPalaceEngine(dictionaries_dir)
        self._yongi = YongiQualityEngine(dictionaries_dir)
        self._exam = ExamOutcomeModifier(dictionaries_dir)
        self._career_mobility = CareerMobilityModifier(dictionaries_dir)
        self._wealth_act = WealthActivationModifier()
        self._marriage_flow = MarriageFlowModifier()
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
        occupation_category: str | None = None,
        provenance_recorder: ProvenanceRecorder | None = None,
    ) -> list[EventCandidateV2]:
        """만세 결과의 운을 거버닝 스택으로 스코어링해 EventCandidateV2 목록을 산출한다.

        provenance_recorder는 P2-PROV 감사 전용이다. None이면(운영 기본) 아무것도
        기록하지 않고 기존 실행 경로·결과와 완전히 동일하다.

        위험 shadow는 호출 스레드 로컬 sink에 수집된다(감수 62차 P0③) —
        직후 take_risk_shadow()로 **이 호출분의 불변 tuple**을 얻는다.
        싱글턴 필드(self.risk_shadow)는 레거시 QA 전용이며 동시 요청에서
        마지막 호출분으로 덮일 수 있으므로 EXPOSE 경로에서 읽지 않는다.
        """
        sink: list[RiskCandidate] = []
        rel_sink: list[RelationshipShadowProjection] = []
        dw_bg_sink: dict[str, DaewoonHwaBackground] = {}
        self._risk_tls.sink = sink
        self._rel_shadow_tls.sink = rel_sink
        self._dw_bg_tls.sink = dw_bg_sink
        try:
            out = self._score_impl(
                result, levels, fav_override,
                occupation_status=occupation_status,
                relationship_status=relationship_status,
                occupation_category=occupation_category,
                provenance_recorder=provenance_recorder)
        finally:
            self._risk_tls.sink = None
            self._risk_tls.last = tuple(sink)
            self.risk_shadow = sink  # 레거시 QA 사이드채널(EXPOSE 금지)
            self._rel_shadow_tls.sink = None
            self._rel_shadow_tls.last = tuple(rel_sink)
            self._dw_bg_tls.sink = None
            self._dw_bg_tls.last = MappingProxyType(dict(dw_bg_sink))
        return out

    def take_daewoon_hwa_backgrounds(self) -> Mapping[str, DaewoonHwaBackground]:
        """직전 score() 호출(같은 스레드)의 시점 배경 맵 — 불변. **소비하면 비운다.**

        **대표 선정 이후 서사 렌더러 전용.** 후보에 필드로 달지 않았으므로
        `_CANDIDATE_RANK_KEY`·eligibility·period grouping 은 이 값에 접근할 수 없다.

        take 즉시 비우는 것이 계약이다. chat_service 의 scorer 는 모듈 싱글턴이고 워커
        스레드는 재사용되므로, 남겨두면 **score() 를 부르지 않는 조기 반환 요청**
        (need_subject·too_broad·정책 응답)이 직전 요청의 배경 맵을 그대로 본다. 실측으로
        재현했다 — 요청 A 채점 후 123건, score 를 부르지 않은 다음 take 에서도 123건.
        """
        # take-and-reset — 읽기와 비우기 사이에 다른 소비자가 끼어들 여지를 두지 않는다.
        empty: Mapping[str, DaewoonHwaBackground] = MappingProxyType({})
        out = getattr(self._dw_bg_tls, "last", None) or empty
        self._dw_bg_tls.last = empty
        return out

    def take_risk_shadow(self) -> tuple[RiskCandidate, ...]:
        """직전 score() 호출(같은 스레드)의 위험 shadow — 불변 tuple.

        요청 로컬 subject_id→risk 결과 맵 구성 전용(감수 62차 P0③).

        **`take_` 라는 이름과 달리 소비하지 않는다(peek).** 저장값을 비우지 않으므로
        반복 호출은 같은 snapshot 을 돌려준다. 2026-07-31 저장소 계약 감사에서 확인:
        production 호출부는 전부 같은 함수 안에서 score() 뒤 직선으로 오고 요청당
        1회만 호출해, score 없는 후속 take 로 이전 요청 값을 읽는 경로가 없다.
        EXPOSE 파이프라인 회귀 범위가 넓어 consume 전환은 하지 않았다 — 관측 이름을
        위해 동작 계약을 바꾸는 일이 되기 때문이다.
        """
        return tuple(getattr(self._risk_tls, "last", ()) or ())

    def take_relationship_shadow(self) -> tuple[RelationshipShadowProjection, ...]:
        """직전 score() 호출(같은 스레드)의 관계 탐지 불변 projection(P1-6 §12).

        관계 벡터 sidecar 전용 — 후보·점수·LLM 입력 경로에서 읽지 않는다.

        **`take_` 라는 이름과 달리 소비하지 않는다(peek).** `take_risk_shadow` 와 같은
        계약이며 같은 감사에서 확인했다. sidecar 는 요청당 1회만 조회하고 take 이후
        재조회하지 않는다.
        """
        return tuple(getattr(self._rel_shadow_tls, "last", ()) or ())

    def _score_impl(
        self,
        result: ManseV2Result,
        levels: set[GanjiLevel] | None = None,
        fav_override: dict[str, str] | None = None,
        *,
        occupation_status: str | None = None,
        relationship_status: str | None = None,
        occupation_category: str | None = None,
        provenance_recorder: ProvenanceRecorder | None = None,
    ) -> list[EventCandidateV2]:
        self.mt4_shadow = []  # MT4 shadow 진단 사이드채널 초기화(이번 호출분만)
        if result.pillars is None or result.luck_cycles is None:
            return []
        wanted = levels or set(GanjiLevel)
        fav_map = fav_override if fav_override is not None else favorability_map(result)
        capacity = analyze_wealth_capacity(result)  # 원국 횡재 그릇(1회 — 발동 가산 배율)
        marriage_flow = analyze_marriage_flow_natal(result)  # 원국 비식재 결혼 그릇(1회)
        idx = _StackIndex(result)
        out: list[EventCandidateV2] = []
        if GanjiLevel.DAEWOON in wanted:
            for dwi in result.luck_cycles.daewoon_table:
                label = f"{dwi.approx_start_date.year}~{dwi.approx_end_date.year}"
                out += self._score_target(
                    result, GanjiLevel.DAEWOON, label, _daewoon_pillar(dwi), idx, fav_map,
                    occupation_status, relationship_status, capacity, marriage_flow,
                    occupation_category, provenance_recorder,
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
                        occupation_status, relationship_status, capacity, marriage_flow,
                        occupation_category, provenance_recorder,
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
        occupation_category: str | None = None,
    ) -> list[EventCandidateV2]:
        """지정 세운 연도를 직접 스코어링한다(용신 검증용 — 과거 연도 포함)."""
        self.mt4_shadow = []  # MT4 shadow 진단 사이드채널 초기화(이번 호출분만)
        self.risk_shadow = []  # 위험 shadow 사이드채널 초기화(이번 호출분만)
        if result.pillars is None or result.luck_cycles is None:
            return []
        fav_map = fav_override if fav_override is not None else favorability_map(result)
        capacity = analyze_wealth_capacity(result)
        marriage_flow = analyze_marriage_flow_natal(result)
        idx = _StackIndex(result)
        out: list[EventCandidateV2] = []
        for y in years:
            p = idx.sewoon_by_year.get(y)
            if p is None:
                continue
            out += self._score_target(
                result, GanjiLevel.YEAR, p.label, p, idx, fav_map,
                occupation_status, relationship_status, capacity, marriage_flow,
                occupation_category,
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
        occupation_status: str | None = None,
        relationship_status: str | None = None,
        occupation_category: str | None = None,
    ) -> list[EventCandidate]:
        """score() → LifeFitRanker(개인 시그니처·코호트·현실 맥락) → 레거시 후보.

        시그니처·맥락·코호트가 전부 없으면 score_legacy()와 동치(LEI 필드 0). subject_id로 조회한
        개인 시그니처·코호트가 있으면 LEI 정렬축(life_fit>confidence>personal_match>score)이 출력에
        반영된다(다운스트림 정렬도 LEI-aware). DB 게이트는 호출 서비스가 담당.

        occupation_status·relationship_status는 user_profile_event_gate 분기에, occupation_category
        (O0x)는 특수직군 충형 길화(자료 9-6)에 쓰인다(미입력이면 보정 없음 — 규칙11).
        """
        v2 = self.score(
            result, levels, fav_override,
            occupation_status=occupation_status, relationship_status=relationship_status,
            occupation_category=occupation_category,
        )
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
        marriage_flow: MarriageFlowNatal,
        occupation_category: str | None = None,
        provenance_recorder: ProvenanceRecorder | None = None,
    ) -> list[EventCandidateV2]:
        """거버닝 스택으로 한 시점의 후보를 만들고 6계층 보정을 적용한다.

        provenance_recorder가 있으면 base 기여(brancher)와 대운 합화 배경 보정을
        **실제 파이프라인 위치에서** 관측한다. 계산에는 개입하지 않는다.
        """
        stack = idx.stack_for(level, label, target)
        if not stack:
            return []
        # 동일계열 집중(운 간여지동) 배율은 채점 대상 층에만 — 배경층 일괄 증폭 방지.
        target_layer = _LEVEL_TO_LAYER[level]
        signals = [
            s
            for layer, pillar in stack
            for s in self._brancher.collect_from_pillar(
                pillar, layer, is_target=layer is target_layer,
            )
        ]
        # ── 위험 엔진 R0 shadow(RISK_ENGINE.md) — reducer·모디파이어 이전 원시 신호 소비 ──
        # 긍정 후보가 없어도(아래 조기 반환) 위험 근거는 남아야 하므로 조기 반환보다 앞에
        # 둔다. OFF면 아무 계산도 하지 않아 기존 결과가 byte-identical이다(수집은 읽기 전용 —
        # cands·signals를 변형하지 않는다).
        self._collect_risk_shadow(result, level, label, target, signals, fav_map)
        if not signals:
            return []
        # 사건 '종류'는 십성(세운·월운)이 결정한다 — 합화는 여기(라벨 생성기)에 넣지 않는다.
        cands = self._brancher.branch(
            signals, label, provenance_recorder=provenance_recorder
        )
        # MT1 — 일간 干合 배우자성 awareness seed '생성'(modifier 아님, feature flag·기본 OFF).
        # branch 직후 합류시켜 이후 6계층 보정·랭킹·soft_cap을 동일하게 거친다.
        if self._enable_mt1_awareness:
            cands = [
                *cands,
                *produce_mt1_awareness_seeds(target, result, fav_map, marriage_flow.gender, label),
            ]
        if not cands:
            return []
        # 배우자성 성별 가중(③) — 남=재성·여=관성. 반대 성별 별만으로 뜬 결혼신호를 amplifier 전에
        # 약화(남:정관 단독=직위·자식 / 여:재성 단독=시댁). base 교정이라 브랜칭 직후 적용.
        cands = apply_marriage_gender_weight(cands, marriage_flow.gender)
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
        # 공망 자극 종류 분리(2026-08-21 확정 의미론) — 충발만 지연, 전실·합은 신호만.
        void_kinds: set[str] = set()
        for h in hits:
            if h.type is RelationType.VOID_TRIGGER_CLASH:
                void_kinds.add("clash")
            elif h.type is RelationType.VOID_FILL:
                void_kinds.add("fill")
            elif h.type is RelationType.VOID_RELEASE_COMBINE:
                void_kinds.add("combine")
        void_active = bool(void_kinds)
        gate_ctx = GateContext(
            present_gods=present_gods, layers=layers, void_active=void_active,
            void_kinds=void_kinds,
            occupation_status=occupation_status, relationship_status=relationship_status,
        )
        cands = self._gate.apply(cands, gate_ctx)
        # 발동·궁성 — 해당 시점 관계 적중(+ 일지 복음 발동: 운 지지=원국 일지).
        layer = target_layer
        activations = (
            _activations(hits, layer, result) + _bokeum_activations(result, target, layer)
        )
        # P1-6 §12 — 관계 벡터 shadow projection 수집(읽기 전용 — cands·hits·
        # activations를 변형하지 않고 primitive만 복사한다. 탐지 재호출 0).
        rel_shadow_sink = getattr(self._rel_shadow_tls, "sink", None)
        if rel_shadow_sink is not None:
            rel_shadow_sink.append(RelationshipShadowProjection(
                layer=layer.value, label=label,
                luck_stem=target.stem, luck_branch=target.branch,
                activations=tuple(RelationActivationProjection(
                    kind=a.kind.value, palace=a.palace.value, layer=a.layer.value,
                    position=a.position, hap_subtype=a.hap_subtype,
                    element=a.element,
                ) for a in activations),
                spouse_palace_clashed=any(
                    h.type is RelationType.BRANCH_CLASH
                    and any(r.position == "day" for r in h.natal_refs)
                    for h in hits
                ),
            ))
        day_el = (
            str(STEM_ELEMENT[Stem(result.pillars.day.stem)])
            if self._mt4_mode != "off" and result.pillars and result.pillars.day
            else ""
        )
        # 인성 동요 신호(feature flag) — 원국 십성군 세력 %는 약근 게이트 판정용.
        group_powers = (
            dict(result.force_analysis.ten_gods.groups)
            if self._enable_resource_clash_renewal and result.force_analysis is not None
            else None
        )
        cands = self._relpalace.apply(
            cands, activations,
            mt4_mode=self._mt4_mode, gender=marriage_flow.gender,
            day_element=day_el, shadow_sink=self.mt4_shadow,
            renewal_enabled=self._enable_resource_clash_renewal,
            ten_god_group_powers=group_powers,
        )
        # 용신 품질 — 시점 유입 글자 오행의 용기신 역할. 본 천간이 합화(化)면 化神 오행으로 길흉
        # 판단(生剋制化 우선 — 사건 종류는 불변, 길흉만 化神 기준). 대운 배경 합화는 제외(국소).
        # 生剋制化 우선순위(化 > 制): 합화면 化神 길흉, 아니면 합거(기신 무력화) 여부를 본다.
        hwa_el = _target_hwa_element(target, result, fav_map)
        stem_bound = _target_stem_bound(target, result, fav_map) if hwa_el is None else False
        role = _period_role(target, fav_map, stem_element=hwa_el, stem_bound=stem_bound)
        # 접힘 전 천간/지지 역할 라벨 보존(P0-1) — NEUTRAL이어도 evidence는 남긴다(INV-E).
        stem_lbl, branch_lbl = _period_role_labels(
            target, fav_map, stem_element=hwa_el, stem_bound=stem_bound
        )
        role_labels = {"stem_role": stem_lbl, "branch_role": branch_lbl}
        if role is not PolarityRole.NEUTRAL:
            note = (
                f"HWA_길흉_{hwa_el}" if hwa_el
                else ("制_합거_흉무력화" if stem_bound else "")
            )
            cands = [  # provenance-audit: not-risk (EventCandidateV2)
                c.model_copy(update={
                    "polarity_role": role,
                    **role_labels,
                    **({"reason_codes": [*c.reason_codes, note]} if note else {}),
                })
                for c in cands
            ]
            cands = self._yongi.apply(cands)
        else:
            cands = [  # provenance-audit: not-risk (EventCandidateV2)
                c.model_copy(update=role_labels) for c in cands
            ]
        # 시험·합격·취업 결과 길흉 — 십성 구조 합·불 패턴으로 favorability만 보정(점수 불변,
        # 자료 9-3·9-4). 극성 NEUTRAL이어도 적용되도록 yongi 블록 밖에서 호출한다.
        cands = self._exam.apply(cands, present_gods)
        # 직업운 결과 길흉 — 특수직군 충형 길화(9-6) + 천충지충 퇴직 리스크(13-1). favorability만.
        cands = self._career_mobility.apply(cands, CareerMobilityContext(
            present_gods=present_gods,
            activation_kinds={a.kind.value for a in activations},
            stem_clash=_has_stem_clash(target.stem, result),
            branch_clash=any(h.type is RelationType.BRANCH_CLASH for h in hits),
            occupation_category=occupation_category,
        ))
        # 횡재 발동 — 원국 그릇 × 운 완성(재성국/충개고/투간/식상생재)을 재물 후보에 보수 가산.
        cands = self._wealth_act.apply(
            cands, capacity, self._wealth_activations(result, stack, capacity),
        )
        # 비식재 흐름 결혼 발동 — 원국 비식재 그릇 × 운 식재/재생관 보강을 결혼·관계 후보에 보수
        # 가산(증폭만). 시점 십성군을 그룹값으로 환원해 발동 판정.
        present_groups = {_GROUP_OF[g] for g in present_gods if g in _GROUP_OF}
        cands = self._marriage_flow.apply(
            cands, marriage_flow,
            detect_marriage_flow_activations(present_groups, marriage_flow.gender),
        )
        # MT2 — 일지 투출 글자 운 회귀 증폭(증폭만·feature flag·기본 OFF). 회귀 글자가 일지 충에
        # 관여하면 긍정 증폭하지 않고 stability 하향 태그만 남긴다(spouse_palace_clashed).
        if self._enable_mt2_emergence:
            spouse_palace_clashed = any(
                h.type is RelationType.BRANCH_CLASH
                and any(r.position == "day" for r in h.natal_refs)
                for h in hits
            )
            cands = MarriageEmergenceModifier.apply(
                cands, analyze_marriage_emergence_natal(result),
                target.stem, spouse_palace_clashed,
            )
        # MT3 — 방합이 일지(배우자궁)를 물면 관계 후보에 태그만 부여(점수 무변경·증폭 아님,
        # feature flag·기본 OFF). 런타임 점수 보강은 relation_palace(HAP/DAY)가 이미 처리한다.
        if self._enable_mt3_directional:
            cands = apply_mt3_directional_tags(cands, hits, result, marriage_flow.gender)
        # 대운 합화 체용 배경 — 대운 化神의 용기신 역할로 성패율에 약한 배경 보정(직접 치환 아님).
        dw_role = _daewoon_hwa_role(stack, result, fav_map)
        # 시점 배경 수집 — 모드와 무관하게 채운다. 맵 계산이 대표 선정 전이어도 무방하며,
        # 중요한 것은 **소비가 선정 이후에만 가능하고 선별 경로로 전달되지 않는 것**이다.
        _dw_sink = getattr(self._dw_bg_tls, "sink", None)
        if _dw_sink is not None:
            _dw_sink[label] = derive_daewoon_hwa_background(dw_role)
        cands = _apply_daewoon_hwa_background(
            cands, dw_role,
            provenance_recorder=provenance_recorder,
            period=label,
            daewoon_occurrence_id=_daewoon_occurrence_id(stack),
            mode=self._daewoon_hwa_mode,
        )
        # 증거 등급·충돌 해결(랭커의 등급 보너스도 raw 누적의 일부).
        rank_ctx = _rank_context(
            activations, present_gods, cands, occupation_status, relationship_status,
        )
        ranked = self._ranker.rank(cands, rank_ctx)
        # 포화 제어 — 단계별 하드 클램프를 없앤 누적 raw에 최종 soft_cap만 적용(매달 100 포화 해소,
        # 순위 보존). raw_score에 cap 전 누적을 남겨 2차 계열 인지 감쇠의 계측으로 쓴다.
        capped = [_apply_soft_cap(c) for c in ranked]
        # 교운 가중 복원(2026-06-23) — 전환성 이벤트는 교운일 근접도로 raw_score(랭킹축, 비포화)에
        # 곱셈 배율을 가산 기여로 반영한다. 구 EventScorer의 daewoonTransition 신호 가중이 21키
        # 재설계에서 누락된 회귀 복원. 유력 달 판정은 strength_rank(raw_total=raw_score)로 가므로
        # 이 보정이 직접 반영된다. display score·activation(포화 채널)은 base raw 기준 그대로 둬
        # 변별·포화 특성을 보존한다(사건 종류·극성 불변). 대운 후보는 midpoint=None으로 제외.
        midpoint = _period_midpoint(level, label)
        if midpoint is None or not idx.jiao_dates:
            return capped
        boosted: list[EventCandidateV2] = []
        for c in capped:
            new_raw, w = daewoon_transition_boost(
                c.raw_score, midpoint, idx.jiao_dates, c.event_key,
            )
            if w <= 0.0:
                boosted.append(c)
                continue
            delta = round(new_raw - c.raw_score, 2)
            # provenance-audit: not-risk (EventCandidateV2)
            boosted.append(c.model_copy(update={
                "raw_score": round(new_raw, 2),
                "contributions": {**c.contributions, "daewoon_transition": delta},
                "reason_codes": [*c.reason_codes, f"DAEWOON_TRANSITION_BOOST_{w:.2f}"],
            }))
        return boosted

    def _relation_hits(
        self, result: ManseV2Result, level: GanjiLevel, target: LuckPillar
    ) -> list[RelationHit]:
        """시점 기둥의 합충형파해·공망 적중."""
        assert result.pillars is not None
        return relation_hits(
            level, target.stem, target.branch,
            target.relations_to_chart, target.gongmang_activation, result.pillars,
        )

    # ── 위험 엔진 R0 shadow (RISK_ENGINE.md) ─────────────────────

    def _active_risk_mode(self) -> RiskEngineMode:
        """유효 위험 모드 — 생성자 강제값 우선, 없으면 config를 호출 시점에 읽는다."""
        raw = self._risk_mode_override
        if raw is None:
            from . import risk_engine_config
            raw = risk_engine_config.RISK_ENGINE_MODE
        try:
            return RiskEngineMode(raw)
        except ValueError:
            return RiskEngineMode.OFF  # 미상 값은 안전하게 OFF(byte-identical)로 처리.

    def set_risk_shadow_contexts(
        self,
        selection_context: SelectionContext | None = None,
        selection_contexts: list[SelectionContext] | None = None,
        relationship_contexts: list[RelationshipContext] | None = None,
        mobility_contexts: list[MobilityContext] | None = None,
        health_contexts: list[HealthContext] | None = None,
        legal_contexts: list[LegalProcessContext] | None = None,
    ) -> None:
        """shadow 후보 생성용 현실 컨텍스트 주입(감수 19·21차 — QA·시나리오 밀도 전용).

        프로필·질문 컨텍스트가 확인된 시나리오의 위험 밀도를 실측하기 위한 통로다.
        긍정 파이프라인·LLM 입력에는 어떤 영향도 없다(risk_shadow 사이드채널 한정).
        """
        self._risk_shadow_selection = selection_context
        self._risk_shadow_selections = selection_contexts
        self._risk_shadow_relationships = relationship_contexts
        self._risk_shadow_mobility = mobility_contexts
        self._risk_shadow_health = health_contexts
        self._risk_shadow_legal = legal_contexts

    @staticmethod
    def _yeokma_reference_sets(result: ManseV2Result) -> dict[str, set[str]]:
        """기준 지지(연·일지)별 실제 역마 글자 — 삼합국 상대 계산(사고수 확장 2026-07-23).

        글자살(寅申巳亥 보유)로 판정하지 않는다(승인 조건 1). relativeStarMatch 룰이
        이 집합과 피자극 글자를 대조한다. pillars 부재 시 빈 dict(fail-closed).
        """
        pillars = result.pillars
        if pillars is None:
            return {}
        from .relationship_relative_sinsal import get_relative_sinsal
        out: dict[str, set[str]] = {}
        for ref, pil in (("year_branch", pillars.year), ("day_branch", pillars.day)):
            if pil is None:
                continue
            out[ref] = {
                b.value for b in Branch
                if get_relative_sinsal(Branch(pil.branch), b).sinsal == "역마살"
            }
        return out

    def _collect_risk_shadow(
        self,
        result: ManseV2Result,
        level: GanjiLevel,
        label: str,
        target: LuckPillar,
        signals: list[TransitSignal],
        fav_map: dict[str, str],
    ) -> None:
        """한 시점의 원시 신호를 위험 엔진에 넘겨 원자 후보를 shadow 수집한다.

        OFF면 즉시 반환(계산 없음 — 기존 출력 byte-identical). SHADOW/EXPOSE(R0에선 동작
        동일)면 모디파이어 적용 전 재료(십성 신호·관계 적중·시점 극성·공망·운성)로
        RawPeriodFacts를 구성해 risk_shadow에 누적한다. 긍정 파이프라인의 어떤 상태도
        변형하지 않는다(읽기 전용). 관계 적중은 시점당 1회 재계산(순수 함수)이라 안전하다.
        """
        if self._active_risk_mode() is RiskEngineMode.OFF or self._risk is None:
            return
        ten_god_layers: dict[TenGod, set[LuckLayer]] = {}
        for s in signals:
            ten_god_layers.setdefault(s.ten_god, set()).add(s.layer)
        hits = self._relation_hits(result, level, target)
        layer = _LEVEL_TO_LAYER[level]
        # 피자극 대상 provenance — 충·형은 '무엇을 쳤는가'로 도메인이 갈리므로(재성 충≠
        # 배우자궁 충≠사회궁 충) 자극 궁성의 천간/지지 십성·글자를 사실에 보존한다.
        relations: list[RelationFact] = []
        for a in _activations(hits, layer, result):
            god, letter = _natal_target(result, a.palace, a.position)
            relations.append(RelationFact(
                kind=a.kind, palace=a.palace, position=a.position,
                target_ten_god=god, target_letter=letter,
            ))
        hwa_el = _target_hwa_element(target, result, fav_map)
        stem_bound = _target_stem_bound(target, result, fav_map) if hwa_el is None else False
        facts = build_raw_period_facts(
            period_key=label,
            layer=layer,
            ten_god_layers=ten_god_layers,
            relations=relations,
            void_active=any(h.type in _VOID_TYPES for h in hits),
            polarity_role=_period_role(
                target, fav_map, stem_element=hwa_el, stem_bound=stem_bound,
            ),
            twelve_stage=_stage_of(target),
            yeokma_by_reference=self._yeokma_reference_sets(result),
        )
        _sink = getattr(self._risk_tls, "sink", None)
        if _sink is None:  # score() 밖 직접 호출(테스트 등) — 레거시 경로
            _sink = self.risk_shadow
        _sink.extend(self._risk.generate(
            facts,
            selection_context=self._risk_shadow_selection,
            selection_contexts=self._risk_shadow_selections,
            relationship_contexts=self._risk_shadow_relationships,
            mobility_contexts=self._risk_shadow_mobility,
            health_contexts=self._risk_shadow_health,
            legal_contexts=self._risk_shadow_legal,
        ))

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
        # 정확 교운일(대운 시작) — 교운 가중(전환성 이벤트 곱셈 배율)의 거리 기준. 만세 엔진
        # trace에 ISO 문자열로 들어온다(approx_start_date는 대략값이라 쓰지 않음).
        self.jiao_dates: list[date] = []
        for x in (lc.trace.get("exact_jiao_un_dates", []) if lc.trace else []):
            try:
                self.jiao_dates.append(date.fromisoformat(x) if isinstance(x, str) else x)
            except (ValueError, TypeError):
                continue
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


def _period_midpoint(level: GanjiLevel, label: str) -> date | None:
    """기간 라벨의 대표 날짜(교운 거리 계산용). 연=7/1, 월=15일, 일=당일.

    대운 후보(label='YYYY~YYYY')는 교운 가중 대상이 아니므로 None을 반환한다.
    """
    try:
        if level is GanjiLevel.YEAR:
            return date(int(label[:4]), 7, 1)
        if level is GanjiLevel.MONTH:
            return date(int(label[:4]), int(label[5:7]), 15)
        if level is GanjiLevel.DAY:
            return date.fromisoformat(label[:10])
    except (ValueError, TypeError):
        return None
    return None


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


def _natal_target(
    result: ManseV2Result, palace: Pillar4, position: str
) -> tuple[TenGod | None, str | None]:
    """관계 발동의 피자극 글자(자극 궁성의 천간/지지) — (십성, 글자) provenance.

    한글 십성을 로마자 enum으로 환원한다. 일간(비교 기준 자신)·미정의 라벨은 십성 None,
    글자는 있으면 그대로 보존한다(정밀 매칭·자리 구분용 — 2026-07-15 감수 2차).
    """
    if result.pillars is None:
        return None, None
    natal = {
        Pillar4.YEAR: result.pillars.year, Pillar4.MONTH: result.pillars.month,
        Pillar4.DAY: result.pillars.day, Pillar4.HOUR: result.pillars.hour,
    }.get(palace)
    if natal is None:
        return None, None
    if position == "stem":
        return TEN_GOD_KO_TO_KEY.get(natal.stem_ten_god or ""), natal.stem or None
    return TEN_GOD_KO_TO_KEY.get(natal.branch_main_ten_god or ""), natal.branch or None


# MT4(§9): HAP으로 붕괴되는 합의 원 종류(subtype) 보존 — RelationType → subtype 라벨.
_HAP_SUBTYPE: dict[RelationType, str] = {
    RelationType.SIX_COMBINATION: "six_harmony",
    RelationType.THREE_HARMONY_CONTRIB: "three_harmony",
    RelationType.DIRECTIONAL_CONTRIB: "directional",
    RelationType.STEM_COMBINATION: "stem",
}


def _activations(
    hits: list[RelationHit], layer: LuckLayer, result: ManseV2Result
) -> list[RelationActivation]:
    """합충형파해 적중 → (관계종류, 자극궁, 층위) 발동 목록(공망류 제외).

    피자극 원국 글자의 십성(target_ten_god)을 함께 보존한다 — 충·형은 '무엇을
    쳤는가'로 의미가 갈리므로(인성 충=문서 동요 등). 기존 필드·순서는 불변.
    """
    out: list[RelationActivation] = []
    for hit in hits:
        kind = _REL_KIND.get(hit.type)
        if kind is None:
            continue
        position = "stem" if hit.type is RelationType.STEM_COMBINATION else "branch"
        subtype = _HAP_SUBTYPE.get(hit.type)  # HAP일 때만 채워짐(MT4용)
        for ref in hit.natal_refs:
            palace = _POS_PILLAR.get(ref.position)
            if palace is not None:
                target_god, _ = _natal_target(result, palace, position)
                out.append(RelationActivation(
                    RelationKind(kind), palace, layer, position=position,
                    hap_subtype=subtype, element=hit.element,
                    # 관측 가능성 — 어느 운 글자가 어느 원국 글자를 건드렸는지.
                    # 점수·reason_codes 에는 영향이 없다(2026-07-31).
                    relation_id=hit.relation_id,
                    luck_stem=hit.luck_ref.stem or "",
                    luck_branch=hit.luck_ref.branch or "",
                    natal_stem=ref.stem or "",
                    natal_branch=ref.branch or "",
                    target_ten_god=target_god.value if target_god else None,
                ))
    return out


def _bokeum_activations(
    result: ManseV2Result, target: LuckPillar, layer: LuckLayer
) -> list[RelationActivation]:
    """복음(伏吟) 발동 — 운 지지가 원국 일지(배우자궁)와 같은 글자일 때 일지궁 자극 1건.

    복음은 합충형파해 RelationType에 없어 _activations가 잡지 못한다(자료: 일지 복음 해는
    결혼·관계 형성의 보조 트리거). 일지(배우자궁)에 한정해 BOKEUM 발동을 합성하며, 단독으로
    사건을 만들지 않고 relation_palace_modifier가 기존 marriage_signal 후보를 강화한다(자극궁
    event_domains 교집합일 때만). 층위 가중(sewoon>wolwoon>ilwoon)은 사전이 처리한다.

    Args:
        result: 만세 결과(pillars.day 필요).
        target: 점수 대상 운 기둥.
        layer: 대상 층위(세운/월운/일운/대운).

    Returns:
        일지 복음이면 BOKEUM 발동 1건, 아니면 빈 목록.
    """
    if result.pillars is None or result.pillars.day is None:
        return []
    if target.branch and target.branch == result.pillars.day.branch:
        return [RelationActivation(
            RelationKind.BOKEUM, Pillar4.DAY, layer, position="branch",
            relation_id="bokeum_day_branch",
            luck_branch=target.branch or "",
            natal_branch=result.pillars.day.branch or "",
        )]
    return []


# 포화 제어 soft_cap — knee 이하는 그대로, 이상은 100에 완만히 접근(거의 정확히 100 안 됨).
# raw 85→85, 100→약 91.8, 120→약 96.3, 150→약 98.9. 순위 보존(단조 증가).
_SOFT_KNEE = 85.0
_SOFT_TAU = 25.0

# 극성 역할 → 결과 길흉 기준값(−1.0~+1.0). 용기신 오행 신호 세기에 비례한 유불리.
# 직접 역할(용·희·기) > 한신 간접(생, 生). NEUTRAL은 길흉 미정(0.0).
_ROLE_FAV: dict[PolarityRole, float] = {
    PolarityRole.YONG_STRONG: 1.0,
    PolarityRole.YONG: 0.7,
    PolarityRole.HEE: 0.5,
    PolarityRole.HAN_GOOD: 0.3,
    PolarityRole.NEUTRAL: 0.0,
    PolarityRole.HAN_BAD: -0.3,
    PolarityRole.GI: -0.7,
    PolarityRole.GI_STRONG: -1.0,
}


def _soft_cap(raw: float) -> float:
    """누적 raw 점수를 표시용(≤100)으로 압축. knee 이하 항등, 이상은 지수 포화."""
    if raw <= _SOFT_KNEE:
        return raw
    return 100.0 - (100.0 - _SOFT_KNEE) * math.exp(-(raw - _SOFT_KNEE) / _SOFT_TAU)


def _apply_soft_cap(c: EventCandidateV2) -> EventCandidateV2:
    """누적 raw를 raw_score에 보존하고 score를 soft_cap 표시값으로 교체한다.

    동시에 활성/길흉 이중 채널을 확정한다(자료 0·15장). activation은 길흉(yongi) 기여를 뺀
    사건 형성도, favorability는 극성 기준값에 모디파이어 보정(fav_adj — 예: 시험 합·불 패턴)을
    더해 [−1, 1]로 클램프한 결과 유불리. 사건 종류·점수는 바꾸지 않는 파생 출력이다.
    """
    raw = float(c.score)
    yongi = c.contributions.get("yongi", 0.0)
    activation = round(_soft_cap(max(0.0, raw - yongi)), 2)
    fav = _ROLE_FAV.get(c.polarity_role, 0.0) + c.contributions.get("fav_adj", 0.0)
    favorability = round(max(-1.0, min(1.0, fav)), 3)
    update: dict = {
        "score": round(_soft_cap(raw)),
        "raw_score": round(raw, 2),
        "activation": activation,
        "favorability": favorability,
    }
    # 이직 분류(자료 12) — 최종 길흉으로 압박성/기회성 라벨(reason_code, 점수 불변).
    if c.event_key is EventKeyV2.CAREER_CHANGE:
        if favorability <= _JOBCHANGE_PRESSURE_TH:
            update["reason_codes"] = [*c.reason_codes, "JOBCHANGE_PRESSURE_DRIVEN"]
        elif favorability >= _JOBCHANGE_OPPORTUNITY_TH:
            update["reason_codes"] = [*c.reason_codes, "JOBCHANGE_OPPORTUNITY"]
    return c.model_copy(update=update)  # provenance-audit: not-risk (EventCandidateV2)


def _has_stem_clash(target_stem: str, result: ManseV2Result) -> bool:
    """그 시점 운 천간이 원국 천간(년·월·일·시)과 천간충을 이루는지(어댑터 — 4쌍 고정)."""
    if not target_stem or result.pillars is None:
        return False
    p = result.pillars
    return any(
        pil is not None and frozenset({target_stem, pil.stem}) in _STEM_CLASH_PAIRS
        for pil in (p.year, p.month, p.day, p.hour)
    )


def _target_hwa_element(
    target: LuckPillar, result: ManseV2Result, fav_map: dict[str, str]
) -> str | None:
    """그 시점 본 천간(세운·월운 등)이 confirmed 합화면 化神 오행(한자)을 반환(아니면 None).

    生剋制化 우선(化): 사건 라벨은 본 운의 원래 십성·궁위·관계작용(합충형파해)이 결정하고, 합화는
    그 사건의 길흉·강약·성패 판단에만 반영한다(사용자 확정 2026-06-16). 본 천간이 합화하면 化神
    오행으로 '용신/기신=길흉'을 본다 — 사건 종류·개수는 불변. 일간 자합(본신지합)은
    hap_mode!='transform'이라 제외. 대운 합화는 per-월 길흉/본신 십성을 직접 치환하지 않으며,
    대운 기간의 체용·용신 적합도·성패율에 배경값으로만 반영한다(_apply_daewoon_hwa_background).
    """
    if result.pillars is None or not target.stem:
        return None
    try:
        resolutions = resolve_stem_hap(result.pillars, fav_map, luck_stems=[target.stem])
    except (ValueError, KeyError):
        return None
    for res in resolutions:
        if not (
            res.luck_origin and res.transform_tier == "confirmed"
            and res.hap_mode == "transform" and res.transform_element
        ):
            continue
        # 그 합에 본 천간(target.stem)이 운 자리로 참여했는지 확인.
        if any(
            pos == "luck" and st == target.stem
            for pos, st in zip(res.positions, res.pair, strict=False)
        ):
            return res.transform_element
    return None


# 대운 합화 체용 배경 보정(슬라이스 2) — 길/흉 품질 집합 + 보정폭(잠정, Phase 4 캘리브레이션).
_GOOD_Q = {EventQuality.OPPORTUNITY, EventQuality.ACHIEVEMENT, EventQuality.RESOLUTION}
_BAD_Q = {EventQuality.LOSS, EventQuality.PRESSURE, EventQuality.CONFLICT}
_DAEWOON_HWA_BG = 0.03


def _daewoon_hwa_role(
    stack: list[tuple[LuckLayer, LuckPillar]],
    result: ManseV2Result,
    fav_map: dict[str, str],
) -> PolarityRole | None:
    """현재 대운 천간이 confirmed 합화면 化神 오행의 용기신 역할(체용 배경값). 아니면 None.

    대운 합화는 사건 라벨·본신 십성을 치환하지 않고, 대운 기간의 성패율(길흉)에만 약한 배경으로
    반영한다(10년 배경 체질 변화). 본신지합(일간 자합)은 hap_mode!='transform'이라 제외.
    """
    if result.pillars is None:
        return None
    dw_stem = next((p.stem for layer, p in stack if layer is LuckLayer.DAEWOON), None)
    if not dw_stem:
        return None
    try:
        resolutions = resolve_stem_hap(result.pillars, fav_map, luck_stems=[dw_stem])
    except (ValueError, KeyError):
        return None
    for res in resolutions:
        if (
            res.luck_origin and res.transform_tier == "confirmed"
            and res.hap_mode == "transform" and res.transform_element
            and any(
                pos == "luck" and st == dw_stem
                for pos, st in zip(res.positions, res.pair, strict=False)
            )
        ):
            return _FAV_ROLE.get(fav_map.get(res.transform_element, ""))
    return None


def _daewoon_occurrence_id(stack: list[tuple[LuckLayer, LuckPillar]]) -> str:
    """관측용 대운 식별자 — **request-local**이다.

    `_daewoon_pillar`가 `label=간지`라 기간 표현이 없어 전역 식별자가 되지 못한다.
    서로 다른 요청의 감사 행을 이 값만으로 합치면 안 된다(설계 §14-7).
    """
    for layer, pillar in stack:
        if layer is LuckLayer.DAEWOON:
            return f"daewoon:{pillar.ganji}:{pillar.stem}{pillar.branch}"
    return ""


def _apply_daewoon_hwa_background(
    cands: list[EventCandidateV2],
    dw_role: PolarityRole | None,
    *,
    provenance_recorder: ProvenanceRecorder | None = None,
    period: str = "",
    daewoon_occurrence_id: str = "",
    mode: str = "current",
) -> list[EventCandidateV2]:
    """대운 합화 化神의 용기신 역할로 사건 성패율에 약한 배경 보정(직접 치환 아님).

    보강 대운(化神 용·희): 길 사건↑·흉 사건 완화. 압력 대운(化神 기·구): 흉 사건↑·길 사건↓.
    폭은 작고 잠정(체용 배경) — 사건 종류·개수는 불변. 같은 대운 내 길/흉 상대 성패만 미세 조정.

    P2-PROV-2a: 6종 modifier 중 **유일하게 특정 대운 occurrence를 집어낼 수 있어**
    관측 대상이다. 다만 분기가 `event_key`가 아니라 `quality`(길/흉)군이라, occurrence를
    특정할 수 있다는 것이 곧 "이 사건의 발생을 대운이 지지했다"는 뜻은 아니다.
    그래서 `support_eligibility=REVIEW_REQUIRED`로 남기고 승격은 감수에 맡긴다.

    감사(DW-HWA, 2026-07-31)가 그 감수였고 정합은 입증되지 않았다. `mode='post_selection'`
    이 그 결론을 반영한 경로다 — 점수·reason 을 건드리지 않고 배경은 `daewoon_background`
    의 시점 맵으로 옮긴다. 기본값은 `'current'`(기존 동작)라 production 은 불변이다.

    Args:
        cands: 보정 대상 후보.
        dw_role: 대운 化神의 용기신 역할(None·NEUTRAL이면 무보정).
        provenance_recorder: 감사 수집기. None이면 기존 동작과 완전히 동일하다.
        period: 관측 기록용 시점 라벨(recorder가 있을 때만 사용).
        daewoon_occurrence_id: 관측 기록용 대운 식별자(request-local).
        mode: 'current'(기본 — 점수 ±3% 반영) | 'post_selection'(점수·reason 불변).
    """
    if dw_role is None or dw_role is PolarityRole.NEUTRAL:
        return cands
    if mode == "post_selection":
        # 감사 판정(DAEWOON_HWA_RANKING_EFFECT_NOT_JUSTIFIED_ON_AUDITED_FIXTURES) 반영 —
        # 점수도 reason_codes 도 건드리지 않는다. 배경은 `daewoon_background` 의 시점 맵이
        # 담고 대표 선정 이후 서사에서만 소비된다.
        #
        # `reason_codes` 에 태그만 남기고 기여를 0 으로 두는 방식은 채택하지 않았다 —
        # 점수에 영향이 없어도 근거 목록을 읽는 guard·리포트·감사가 여전히 occurrence
        # evidence 로 오독한다. 문자열 계약은 `DaewoonHwaBackground.evidence_code` 가 잇는다.
        if provenance_recorder is not None:
            for c in cands:
                provenance_recorder.record_modifier(period, _daewoon_hwa_evidence(
                    c, None, c.score, daewoon_occurrence_id
                ))
        return cands
    boon = dw_role in (PolarityRole.YONG, PolarityRole.HEE)
    tag = f"DAEWOON_HWA_BG_{'보강' if boon else '압력'}"
    out: list[EventCandidateV2] = []
    for c in cands:
        if c.quality in _GOOD_Q:
            factor = 1 + _DAEWOON_HWA_BG if boon else 1 - _DAEWOON_HWA_BG
        elif c.quality in _BAD_Q:
            factor = 1 - _DAEWOON_HWA_BG if boon else 1 + _DAEWOON_HWA_BG
        else:
            if provenance_recorder is not None:
                # 품질 미상 후보는 호출은 됐으나 적용 조건을 만족하지 못했다.
                provenance_recorder.record_modifier(period, _daewoon_hwa_evidence(
                    c, None, c.score, daewoon_occurrence_id
                ))
            out.append(c)
            continue
        new_score = max(0, round(c.score * factor))
        # provenance-audit: not-risk (EventCandidateV2)
        out.append(c.model_copy(update={
            "score": new_score,
            "reason_codes": [*c.reason_codes, tag],
            "contributions": {**c.contributions, "daewoon_hwa": float(new_score - c.score)},
        }))
        if provenance_recorder is not None:
            provenance_recorder.record_modifier(period, _daewoon_hwa_evidence(
                c, factor, new_score, daewoon_occurrence_id
            ))
    return out


def _daewoon_hwa_evidence(
    c: EventCandidateV2,
    factor: float | None,
    new_score: int,
    occurrence_id: str,
) -> ModifierContributionEvidence:
    """대운 합화 배경 보정 1건을 관측 레코드로 만든다(계산에 되먹이지 않는다).

    `factor=None`은 품질 미상이라 적용 조건을 만족하지 못한 경우다.

    발생 방향(`candidate_alignment`)과 결과 유불리(`favorability_effect`)를 분리한다 —
    흉 사건 점수를 올리면 발생은 `SUPPORTS`지만 결과는 `WORSENS`다.
    """
    if factor is None:
        return ModifierContributionEvidence(
            modifier_id="daewoon_hwa_background",
            event_key=str(c.event_key),
            role=EvidenceRole.QUALITY_ADJUSTER,
            candidate_specific=False,  # quality군 단위 — event_key로 분기하지 않는다
            occurrence_attribution=OccurrenceAttribution.CANDIDATE,
            support_eligibility=SupportEligibility.REVIEW_REQUIRED,
            source_occurrence_ids=(occurrence_id,) if occurrence_id else (),
            source_layers=(str(LuckLayer.DAEWOON),),
            formula_relation=FormulaRelation.UNRELATED,
            value_before=float(c.score),
            value_after=float(c.score),
            invoked=True,
            eligible=False,
        )
    pre = c.score * factor - c.score
    delta = new_score - c.score
    good = c.quality in _GOOD_Q
    up = factor > 1.0
    return ModifierContributionEvidence(
        modifier_id="daewoon_hwa_background",
        event_key=str(c.event_key),
        role=EvidenceRole.QUALITY_ADJUSTER,
        candidate_specific=False,
        occurrence_attribution=OccurrenceAttribution.CANDIDATE,
        support_eligibility=SupportEligibility.REVIEW_REQUIRED,
        source_occurrence_ids=(occurrence_id,) if occurrence_id else (),
        source_layers=(str(LuckLayer.DAEWOON),),
        # base 승자 formula와 무관하게 quality만 보고 적용된다.
        formula_relation=FormulaRelation.UNRELATED,
        value_before=float(c.score),
        value_after=float(new_score),
        pre_quantized_effect=float(pre),
        numeric_effect=float(delta),
        invoked=True,
        eligible=True,
        changed_numeric_value=delta != 0,
        candidate_alignment=(
            CandidateAlignment.SUPPORTS if up else CandidateAlignment.OPPOSES
        ),
        favorability_effect=(
            (FavorabilityEffect.IMPROVES if up else FavorabilityEffect.WORSENS)
            if good
            else (FavorabilityEffect.WORSENS if up else FavorabilityEffect.IMPROVES)
        ),
    )


def _target_stem_bound(
    target: LuckPillar, result: ManseV2Result, fav_map: dict[str, str]
) -> bool:
    """본 천간이 기·구신(흉)인데 합거(合去)로 묶여 흉이 제거되면 True — 制/탐합망극 흉 무력화.

    生剋制化의 制: 기신이 합으로 묶이면 극(흉) 작용을 못 한다(탐합망극). 이때 그 천간의 흉 역할을
    길흉 판정에서 건너뛴다(사건 종류·개수 불변). 길신 묶임(harm)은 무력화 대상이 아니다(별도).
    합거(direction 'away')만 대상 — 합반(부분 묶임)은 제외(보수적).
    """
    if result.pillars is None or not target.stem:
        return False
    try:
        stem_el = str(STEM_ELEMENT[Stem(target.stem)])
    except (KeyError, ValueError):
        return False
    if not is_unfavorable_role(fav_map.get(stem_el)):
        return False
    try:
        resolutions = resolve_stem_hap(result.pillars, fav_map, luck_stems=[target.stem])
    except (ValueError, KeyError):
        return False
    return any(
        res.luck_origin and res.hap_mode == "bind" and res.direction == "away"
        and any(a.stem == target.stem and a.effect == "boon" for a in res.affected)
        for res in resolutions
    )


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


def _period_role(
    target: LuckPillar,
    fav_map: dict[str, str],
    stem_element: str | None = None,
    stem_bound: bool = False,
) -> PolarityRole:
    """시점 유입 글자(천간 우선, 지지 보조) 오행의 용기신 역할 → 극성.

    1) 직접 역할(용·희·기·구) — 천간 우선, 지지 보조. 2) 천간·지지 모두 직접 역할이 없을 때만
    한신의 생(生) 관계로 간접 길흉(약)을 판정한다(직접 신호를 덮지 않는 보조 계층).
    stem_element: 본 천간이 합화(化)했을 때의 化神 오행 — 길흉을 化神 기준으로 본다(生剋制化 우선).
    stem_bound: 본 천간이 합거(制)로 묶여 흉이 무력화되면 True — 천간을 길흉 판정에서 건너뛴다.
    """
    try:
        stem_el = stem_element or str(STEM_ELEMENT[Stem(target.stem)])
        branch_el = str(BRANCH_ELEMENT[Branch(target.branch)])
    except (KeyError, ValueError):
        return PolarityRole.NEUTRAL
    # 制/합거 무력화 — 묶인 천간은 역할 없음(빈 라벨)으로 처리해 흉을 끌지 않게 한다.
    stem_lbl = "" if stem_bound else fav_map.get(stem_el, "")
    branch_lbl = fav_map.get(branch_el, "")
    # 0) 천간·지지가 같은 방향으로 겹친 강한 신호 — 모두 용신(강한 용신운)/모두 흉(기·구).
    if stem_lbl == "용신" and branch_lbl == "용신":
        return PolarityRole.YONG_STRONG
    if is_unfavorable_role(stem_lbl) and is_unfavorable_role(branch_lbl):
        return PolarityRole.GI_STRONG
    # 1) 직접 역할(천간 우선).
    for lbl in (stem_lbl, branch_lbl):
        direct = _FAV_ROLE.get(lbl)
        if direct is not None:
            return direct
    # 2) 직접 역할 없음 → 한신 생(生) 간접 길흉(천간 우선 — 묶인 천간은 제외).
    elems = (branch_el,) if stem_bound else (stem_el, branch_el)
    for el in elems:
        indirect = _han_gen_role(el, fav_map)
        if indirect is not None:
            return indirect
    return PolarityRole.NEUTRAL


def _period_role_labels(
    target: LuckPillar,
    fav_map: dict[str, str],
    stem_element: str | None = None,
    stem_bound: bool = False,
) -> tuple[str, str]:
    """시점 유입 천간/지지 오행의 역할 라벨 두 개를 접지 않고 보존(P0-1, 2026-08-21).

    _period_role이 PolarityRole 1개로 접으면서 버리던 원천 라벨('용신'~'한신'|'')을
    독립 evidence로 돌려준다. 합화(化)·합거(制) 처리 기준은 _period_role과 동일.
    ⚠ INV-E: "천간=결과축, 지지=과정축" 같은 단계 의미 부여 금지 — 라벨은 evidence 전용.
    """
    try:
        stem_el = stem_element or str(STEM_ELEMENT[Stem(target.stem)])
        branch_el = str(BRANCH_ELEMENT[Branch(target.branch)])
    except (KeyError, ValueError):
        return "", ""
    return ("" if stem_bound else fav_map.get(stem_el, ""), fav_map.get(branch_el, ""))


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

# 12운성 event_phase 내부값 → 한글 라벨(P0-5, 2026-08-21). 그동안 영문 원시값
# (formalization 등)이 동반 신호 문자열로 프롬프트까지 그대로 누출되던 버그 수정.
# 값 목록 SSOT = dictionaries/event_engine/twelve_stage_modifier.json의 event_phase.
_EVENT_PHASE_KO: dict[str, str] = {
    "new_start": "새 국면 시작",
    "exposure_volatility": "노출·변동",
    "formalization": "공식화 단계",
    "stabilization": "안정화 단계",
    "peak": "정점 단계",
    "decline_adjustment": "조정·숨고르기",
    "fatigue_problem": "피로·문제 표면화",
    "closure_hidden": "마무리·잠복",
    "storage_concealment": "갈무리·보관",
    "cut_reset": "단절·재정비",
    "conception_planning": "구상·기획",
    "nurturing_preparation": "준비·육성",
}


def to_legacy_candidate(c: EventCandidateV2) -> EventCandidate:
    """EventCandidateV2 → 레거시 EventCandidate(다운스트림 DTO). 신 차원은 동반 신호로 표면화."""
    quality_txt = QUALITY_KO.get(c.quality, "") if c.quality else ""
    conf_txt = CONFIDENCE_KO.get(c.confidence_level, "")
    palace_txt = PALACE_KO.get(c.palace, "") if c.palace else ""
    phase_txt = _EVENT_PHASE_KO.get(c.event_phase or "", c.event_phase or "")
    head = [b for b in (conf_txt, quality_txt, palace_txt, phase_txt) if b]
    signals: list[Signal] = []
    if head:  # 사건화 강도·품질·궁성·단계 — LLM 입력 풍부화(첫 동반 신호).
        signals.append(Signal(
            type="materialization", name="materialization",
            effect=" · ".join(head), weight=float(c.score),
        ))
    for ko in reason_codes_ko(c.reason_codes):
        signals.append(Signal(type="reason", name=ko, effect=ko, weight=0.0))
    # 불안정 신호 텍스트 보존(공망 충발 → context_reducer 검토월 판정). 서브타입 구분
    # (2026-08-21 확정 의미론): 지연은 충발(VOID_delay)만, 전실·합은 별도 라벨 —
    # '해소'가 '지연·공허'로 서술되던 결함(申·巳 육합 사례) 차단.
    if any(r.startswith("VOID_delay") for r in c.reason_codes):
        signals.append(Signal(type="void", name="void", effect="공망 지연", weight=0.0))
    if "VOID_FILL" in c.reason_codes:
        signals.append(Signal(
            type="void", name="void_fill", effect="공망 전실(실체화)", weight=0.0,
        ))
    if "VOID_COMBINE_RELEASE" in c.reason_codes:
        signals.append(Signal(
            type="void", name="void_combine",
            effect="공망 해소·접촉(합 — 억제 완화)", weight=0.0,
        ))
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
        quality=c.quality.value if c.quality else None,  # 방향(길흉) 보존
        timing=c.timing.value,  # 타이밍(즉시/지연) 보존
        signals=signals,
        evidence_path=list(c.reason_codes),
        # 평가 스택 층위 보존 — EventCandidateV2.source_layers는 이름과 달리 후보별
        # 기여가 아니라 그 시점 signal stack 전체의 층위다(브랜처가 후보 루프 밖에서
        # 한 번 계산해 전 후보에 같은 값을 넣는다). 이름으로 의미를 고정한다.
        stack_layers=normalize_layers(c.source_layers),
        # 후보별 기여 층위 — base 승자 근거에서만 온다(PROV-4 §17-5).
        candidate_source_layers=list(c.candidate_source_layers),
        raw_total=c.raw_score,
        life_fit=c.life_fit,
        personal_match=c.personal_match,
        favorability=c.favorability,  # 결과 길흉 채널 — 다운스트림 LLM 입력까지 전달
        # 활성 채널 복구(P0-1) — favorability와 독립 유지(INV-C: 단일 축 재합성 금지).
        activation=c.activation,
        # 천간/지지 역할 라벨 — 독립 evidence 전용(INV-E: 단계 의미 부여 금지).
        stem_role=c.stem_role,
        branch_role=c.branch_role,
    )
