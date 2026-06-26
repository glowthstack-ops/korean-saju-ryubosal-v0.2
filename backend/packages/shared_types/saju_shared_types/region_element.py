"""지역 오행 추천 엔진 입출력 schemas (v2.2 P0, docs/12).

지역 자체의 고유 오행(고정·사전계산)과 사용자 기준 추천 오행(가변·요청 시점 계산)을 분리한다
(docs/12 §0). 본 모듈은 두 축의 계약 타입을 정의한다:

- 고유 오행: `RegionElementProfile`(5차원 벡터 + dominance + evidence) — 빌드 타임에 산출해
  compiled 스냅샷에 저장(절대원칙 9).
- 추천: `RegionRecommendationQuery` → `RegionRecommendationResult` — 요청 시점에 사용자
  용/희/기/구신·거주지·의도로 매칭(LLM은 설명만, 절대원칙 1·2).

방위는 지역 고유값이 아니라 base_location에 의존하므로 프로필에 저장하지 않는다(docs/12 §4-4).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .enums import Element
from .graph import EvidenceBundle

# 오행 5종 한자 키 — 벡터 직렬화 표준 키 순서(木火土金水).
_ELEMENT_KEYS: tuple[str, ...] = tuple(e.value for e in Element)


class RegionResolution(StrEnum):
    """지역 해상도(연산·후보 단위). 1차 구현은 eup_myeon_dong까지(docs/12 §2)."""

    SIDO = "sido"
    SIGUNGU = "sigungu"
    EUP_MYEON_DONG = "eup_myeon_dong"
    RI = "ri"


class LayerType(StrEnum):
    """오행 판정 레이어(docs/12 §4·§5). 가중·confidence는 레이어 단위로 적용된다."""

    PHYSICAL_GEOGRAPHY = "physical_geography"  # §4-1 실제 지형(최고 비중)
    LANDCOVER_HYDRO_FOREST = "landcover_hydro_forest"  # §3-C 토지피복·수계·산림
    HANJA_PLACE_NAME = "hanja_place_name"  # §4-2 지명 한자(보조)
    RELATIVE_DIRECTION = "relative_direction"  # §4-4 방위(사용자 기준·추천 시점)
    FENGSHUI_FORM = "fengshui_form"  # §4-5 풍수 형국(V2)
    PHONETIC_READING = "phonetic_reading"  # §4-3 독음 음운(≤3%)


class TerrainRole(StrEnum):
    """방향성 지형 feature의 작용 역할(docs/12 §14-1). feature_type=무엇 / terrain_role=어떻게."""

    MOUNTAIN_SUPPORT = "mountain_support"  # 산·구릉 받침(土, 산림 시 木 보조)
    FOREST_SUPPORT = "forest_support"  # 산림 피복(木)
    RIVER_FLOW = "river_flow"  # 하천 흐름(水)
    LAKE_WATER = "lake_water"  # 호수·저수지(水)
    COAST_WATER = "coast_water"  # 해안·바다(水)
    VALLEY_WATER = "valley_water"  # 계곡 수(水, 산지면 土 보조)
    ROAD_RUSH = "road_rush"  # 도로 직충(火/金 + 페널티)
    RAIL_METAL = "rail_metal"  # 철도(金)
    OPEN_FIELD = "open_field"  # 개활·평지(土)
    URBAN_HEAT = "urban_heat"  # 도심 열섬(火)
    INDUSTRIAL_METAL = "industrial_metal"  # 산업지(金)


class FormEffect(StrEnum):
    """풍수 형국 작용(docs/12 §14-1). 가산(support)·페널티(penalty)·중립으로 분류."""

    BACK_SUPPORT = "back_support"  # 현무 받침(가산)
    FRONT_OPEN = "front_open"  # 주작 개활(가산)
    LEFT_DRAGON = "left_dragon"  # 청룡(가산)
    RIGHT_TIGER = "right_tiger"  # 백호(가산)
    WATER_EMBRACE = "water_embrace"  # 감싸 흐르는 물(가산)
    ROAD_RUSH = "road_rush"  # 도로 직충(페널티)
    WATER_ESCAPE = "water_escape"  # 수구 빠짐(페널티)
    EXCESSIVE_PRESSURE = "excessive_pressure"  # 과도한 압박(페널티)
    ISOLATED_FLAT = "isolated_flat"  # 고립 평지(페널티)
    NEUTRAL = "neutral"


class RegionLevel(StrEnum):
    """행정구역 레벨(doc/gis region_unit.region_level). 프로필·상속 계층의 키."""

    CTPRVN = "ctprvn"  # 시도(17)
    SIG = "sig"  # 시군구(250)
    EMD = "emd"  # 읍면동(5,065) — P1 추천 기본 후보 단위


class DominanceType(StrEnum):
    """오행 우세 등급(docs/12 §5, P1 confidence 밴드 반영 — 사용자 확정 2026-06-26).

    P1은 한자·음운·기존자산·상속 중심이라 confidence가 낮은 지역이 많다. 따라서 신뢰도
    밴드를 1차 게이트로 두고(unknown<0.35≤weak<0.55), 0.55 이상에서만 우세 등급을 내린다.
    """

    UNKNOWN = "unknown"  # confidence < 0.35 — 판정 보류
    WEAK = "weak"  # 0.35 ≤ confidence < 0.55 — 약한 추정(단정 금지)
    SINGLE = "single_dominant"  # 단일 우세
    COMPOSITE = "composite_dominant"  # 복합 우세
    CONTESTED = "contested"  # 경합(우세 불명확)


class IntentMode(StrEnum):
    """질문 의도별 추천 모드(docs/12 §7). 레이어 가중을 치환한다(점수 산식만, 단정 금지)."""

    RELOCATION = "relocation"  # 이사·거주
    CAREER = "career"  # 직장·사업
    HEALING = "healing"  # 휴식·치유·여행
    GENERAL = "general"  # 기본


class ElementVector(BaseModel):
    """오행 5차원 벡터(0 이상). 합이 1일 필요는 없으나 정규화 후 저장을 권장한다.

    한자 키 dict와 상호 변환을 제공한다 — 엔진 내부 산식은 dict를 쓰고, 저장/전달은 본 모델을
    쓴다. 필드명은 Python 식별자 제약상 영문(오행 enum과 1:1)이다.
    """

    wood: float = Field(default=0.0, ge=0.0)  # 木
    fire: float = Field(default=0.0, ge=0.0)  # 火
    earth: float = Field(default=0.0, ge=0.0)  # 土
    metal: float = Field(default=0.0, ge=0.0)  # 金
    water: float = Field(default=0.0, ge=0.0)  # 水

    def as_map(self) -> dict[str, float]:
        """한자 키 dict로 변환({'木':..,'火':..,'土':..,'金':..,'水':..})."""
        return {
            Element.WOOD.value: self.wood,
            Element.FIRE.value: self.fire,
            Element.EARTH.value: self.earth,
            Element.METAL.value: self.metal,
            Element.WATER.value: self.water,
        }

    @classmethod
    def from_map(cls, data: dict[str, float]) -> ElementVector:
        """한자 키 dict에서 생성(누락 오행은 0)."""
        return cls(
            wood=data.get(Element.WOOD.value, 0.0),
            fire=data.get(Element.FIRE.value, 0.0),
            earth=data.get(Element.EARTH.value, 0.0),
            metal=data.get(Element.METAL.value, 0.0),
            water=data.get(Element.WATER.value, 0.0),
        )

    def normalized(self) -> ElementVector:
        """합이 1이 되도록 정규화. 합이 0이면 그대로 반환(보정 없음, 절대원칙 11)."""
        total = self.wood + self.fire + self.earth + self.metal + self.water
        if total <= 0.0:
            return self
        return ElementVector.from_map({k: v / total for k, v in self.as_map().items()})


class RegionElementEvidence(BaseModel):
    """오행 판정 근거 1건(레이어 단위). 사용자/개발자 노출 및 Graph RAG 경로의 원천(docs/12 §8)."""

    layer_type: LayerType
    source_name: str  # 출처(예: '임상도', '지명유래집', 'region_elements.json')
    evidence_text: str  # 근거 설명(한글)
    element: str  # 이 근거가 가리키는 오행(한자) — 미특정이면 빈 문자열
    weight: float = Field(ge=0.0)  # 레이어 내 기여 가중
    confidence: float = Field(ge=0.0, le=1.0)


class RegionGeoFeature(BaseModel):
    """지형·수계·토지피복 feature 1건(docs/12 §3-C·§4-1). P3 어댑터 입력.

    GIS 공급 시 채운다(환경공간정보 토지피복·산림청 임상도·실폭하천·WAMIS·DEM). 미상 필드는
    None — 어댑터는 None을 건너뛰고 공급된 신호만 physical_geography/landcover_hydro_forest
    레이어로 변환한다(절대원칙 11). ratio/score는 0~1, density·고도는 region_geo_signal_rules의
    norm으로 정규화한다.
    """

    region_id: str
    legal_dong_code: str = ""
    mean_elevation: float | None = None
    elevation_p70: float | None = None
    slope_mean: float | None = None
    slope_p70: float | None = None
    forest_area_ratio: float | None = None
    water_area_ratio: float | None = None
    river_length_density: float | None = None
    coast_distance_m: float | None = None
    coast_touch_yn: bool | None = None
    wetland_ratio: float | None = None
    agricultural_ratio: float | None = None
    urban_built_ratio: float | None = None
    industrial_ratio: float | None = None
    road_density: float | None = None
    rail_density: float | None = None
    south_facing_slope_ratio: float | None = None
    basin_score: float | None = None
    mountain_score: float | None = None
    plain_score: float | None = None
    source_version: str = ""


class RegionAdminUnit(BaseModel):
    """행정구역 레이어 1건(docs/12 §3-A). 법정동(법정구역) 코드가 연산 기본 키다.

    P2 경량 registry(build_region_admin.py) — 지명 해소·표시·면적 정규화용. 좌표는 프로필이
    보유하므로(중복 방지) 기본 미수록(None). centroid/area는 미상이면 None.
    """

    region_id: str
    legal_dong_code: str
    region_level: RegionLevel = RegionLevel.EMD
    sido_name: str
    sigungu_name: str = ""
    eup_myeon_dong_name: str = ""
    ri_name: str = ""
    full_name: str
    parent_code: str | None = None
    active_yn: bool = True
    centroid_lat: float | None = None
    centroid_lon: float | None = None
    area_m2: float | None = None


class RegionAdminSnapshot(BaseModel):
    """행정구역 registry 스냅샷(compiled/region_admin_units_vX.json, docs/12 §2·§3-A).

    지명 → region_code 해소(RegionNameResolver)와 scope(시도/수도권) 후보 열거의 원천.
    """

    model_version: str
    source_gis_version: str = ""
    reviewed: bool = False  # GIS 행정데이터 기반 — 오행 판정과 무관하나 운영 일관성상 플래그
    profile_counts: dict[str, int] = Field(default_factory=dict)  # ctprvn/sig/emd
    items: list[RegionAdminUnit] = Field(default_factory=list)


class RegionUnitInput(BaseModel):
    """프로필 빌드 입력 1건(doc/gis region_units_compact + 한자 조인 결과).

    엔진은 한자명을 직접 갖지 않는 GIS 데이터를 받으므로, 시군구 단위에서 region_elements.json
    조인으로 얻은 `hanja`/`fallback_elements`만 한자 레이어로 쓴다(D2). 좌표는 고정 지리값으로
    저장하되 '방위'는 저장하지 않는다(추천 시점 계산, docs/12 §4-4).
    """

    region_code: str
    region_level: RegionLevel
    parent_code: str | None = None
    full_name_ko: str
    region_name_ko: str = ""  # 음운 레이어 입력(읍면동/시군구/시도명)
    hanja: str | None = None  # 시군구 한자명(region_elements.json 조인) — 없으면 음운/상속
    fallback_elements: list[str] = Field(default_factory=list)  # 한자 토큰 미매칭 시 폴백(D2)
    centroid_lat: float | None = None
    centroid_lon: float | None = None
    anchor_lat: float | None = None  # 대표 내부점(방위 기준, engine_anchor_rule)
    anchor_lon: float | None = None


class RegionElementProfile(BaseModel):
    """지역 고유 오행 프로필(고정·사전계산). compiled 스냅샷 저장 단위(docs/12 §8).

    방위는 포함하지 않는다(사용자 기준값, docs/12 §4-4). 좌표(centroid/anchor)는 고정 지리값이며
    추천 시점 방위 계산의 기준점으로만 쓴다. calculated_at은 빌드 시 스탬프.
    """

    region_id: str  # = region_code(연산 기본 키)
    region_code: str = ""
    region_level: RegionLevel = RegionLevel.EMD
    parent_code: str | None = None
    legal_dong_code: str = ""
    full_name: str
    model_version: str
    element_vector: ElementVector
    dominant_type: DominanceType
    dominant_elements: list[str] = Field(default_factory=list)  # 한자, 우세순
    confidence: float = Field(ge=0.0, le=1.0)
    source_layers: list[str] = Field(default_factory=list)  # 기여 레이어/메커니즘 라벨(스냅샷 경량)
    centroid_lat: float | None = None
    centroid_lon: float | None = None
    anchor_lat: float | None = None
    anchor_lon: float | None = None
    evidence: list[RegionElementEvidence] = Field(default_factory=list)  # 상세 근거(추천 시 생성)
    calculated_at: str = ""  # ISO8601(빌드 시 주입)


class TargetElements(BaseModel):
    """사용자 용/희/기/구신 + 보완 필요 오행(docs/12 §6). 한자 리스트.

    역할→점수 변환표(용신+1.0/희신+0.65/보완+0.45/한신0/구신−0.6/기신−1.0)는
    region_dominance_rules.json(user_match.role_scores)이 보유한다(docs/12 §6).
    """

    yongsin: list[str] = Field(default_factory=list)
    huisin: list[str] = Field(default_factory=list)
    gisin: list[str] = Field(default_factory=list)
    gusin: list[str] = Field(default_factory=list)
    boost: list[str] = Field(default_factory=list)  # 보완 필요 오행(선택)


class RegionRecommendationQuery(BaseModel):
    """지역 추천 질의(docs/12 §1). base_location 없으면 방위 레이어 제외(절대원칙 11)."""

    target_elements: TargetElements
    user_question: str = ""
    base_location: str | None = None  # 현재 거주지(방위 기준점)
    candidate_scope: str | None = None  # 후보 범위(예: '수도권', 시도명) — None이면 전국
    candidate_regions: list[str] | None = None  # 명시 후보(있으면 우선)
    resolution: RegionResolution = RegionResolution.EUP_MYEON_DONG
    intent_mode: IntentMode = IntentMode.RELOCATION
    top_n: int = Field(default=5, ge=1, le=50)


class RegionFitItem(BaseModel):
    """추천 지역 1건(사용자 기준 매칭 결과, docs/12 §1·§6)."""

    region_name: str
    legal_dong_code: str = ""
    dominant_elements: list[str] = Field(default_factory=list)
    element_vector: ElementVector
    match_score: int = Field(ge=0, le=100)
    avoid_score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0.0, le=1.0)
    reason_summary: str = ""
    evidence: list[str] = Field(default_factory=list)  # 사용자 노출용 근거 문구
    direction: str = ""  # 방위 라벨(base_location 있을 때만; 빈 문자열=미산출)
    direction_fit: str = ""  # 방위 적합 라벨(region_direction 재사용)
    risk_flags: list[str] = Field(default_factory=list)  # 예: water_overload_possible


class RegionRecommendationResult(BaseModel):
    """지역 추천 엔진 최종 산출. LLM에는 본 결과 + 압축 근거만 전달(설명 대상, docs/12 §9)."""

    recommended_regions: list[RegionFitItem] = Field(default_factory=list)
    intent_mode: IntentMode = IntentMode.RELOCATION
    notes: list[str] = Field(default_factory=list)  # 보류·주의(예: confidence 부족 지역 다수)
    explanations: list[RegionRecommendationExplanation] = Field(default_factory=list)  # P4-2
    evidence: list[EvidenceBundle] = Field(default_factory=list)  # Graph RAG 경로(P4)


class RegionFitFactor(BaseModel):
    """추천 적합 근거 1건(오행 단위, docs/12 §6·§9, P4-2). 역할별 긍정/부정 분리용."""

    element: str  # 한자 오행
    role: str  # 용신/희신/보완/한신/구신/기신
    weight: float = Field(ge=0.0)  # 지역 벡터 내 비중
    reason: str  # 단정 금지 자연어(유리/보완성/부담 가능)


class RegionFitSummary(BaseModel):
    """적합 요약 — 사용자 역할 기준 긍정/부정/중립 분리(P4-2)."""

    positive: list[RegionFitFactor] = Field(default_factory=list)
    negative: list[RegionFitFactor] = Field(default_factory=list)
    neutral: list[RegionFitFactor] = Field(default_factory=list)


class RegionRecommendationEvidence(BaseModel):
    """레이어 단위 근거 신호(P4-2). 외부 지형 데이터 공급 시 signal이 세분화된다."""

    layer: str  # geo/hanja/phonetic/inheritance/direction
    signal: str  # 신호명(예: mountain_score·山·full_name)
    element: str = ""  # 가리키는 오행(한자, 미특정 빈 문자열)
    strength: float = Field(default=0.0, ge=0.0)  # 0~1 신호 강도
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class RegionMissingLayer(BaseModel):
    """미공급 레이어(P4). 점수를 감점하지 않고 표시만 한다(절대원칙 11)."""

    layer: str
    reason: str = ""


class RegionRecommendationExplanation(BaseModel):
    """추천 1건의 구조화 설명 payload(P4-2·P4-3). LLM에는 이 결과만 전달(계산 금지)."""

    region_code: str
    full_name_ko: str
    match_score: int = Field(ge=0, le=100)
    avoid_score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0.0, le=1.0)
    dominant_elements: list[str] = Field(default_factory=list)
    element_vector: ElementVector
    fit_summary: RegionFitSummary
    evidence: list[RegionRecommendationEvidence] = Field(default_factory=list)
    missing_layers: list[RegionMissingLayer] = Field(default_factory=list)
    direction: str = ""  # base_location 있을 때만
    direction_fit: str = ""
    intent_mode: IntentMode = IntentMode.RELOCATION
    intent_weights: dict[str, float] = Field(default_factory=dict)  # 재정규화된 유효 가중


class RelocationRegionCandidate(BaseModel):
    """택일 엔진 결합용 지역 후보(P4-4). '어디'를 '언제'로 넘기는 bridge 페이로드."""

    region_code: str
    full_name_ko: str
    region_elements: list[str] = Field(default_factory=list)  # 우세 오행(한자)
    element_vector: ElementVector
    direction_from_base: str = ""  # 8방위 코드/라벨(base 있을 때)
    direction_elements: list[str] = Field(default_factory=list)
    match_score: int = Field(ge=0, le=100)


class RegionTaekilContext(BaseModel):
    """지역→택일 결합 컨텍스트(P4-4). 실제 택일 점수는 date_selection 엔진이 산출(역할 분리)."""

    event_type: str  # relocation 등
    target_region: RelocationRegionCandidate
    date_range: dict[str, str] = Field(default_factory=dict)  # {start, end}
    user_chart_context: dict = Field(default_factory=dict)  # 오케스트레이터 패스스루


class ExternalGeoFeature(BaseModel):
    """외부 지형 feature 대표 좌표 1건(P4-Data, doc/gis_region external_geo_feature 계약).

    원본 SHP를 엔진에 넣지 않고 대표 좌표 index만 적재한다(사용자 확정 2026-06-26). point는 그대로,
    line(하천·해안)은 500m~1km anchor로, polygon(호수·산림)은 centroid/대표점으로 압축한다.
    element_*는 feature_type별 오행 매핑(region_geo_feature_elements.json) 결과를 보존한다.
    """

    feature_id: str
    feature_type: str  # mountain_peak/river_anchor/coast_anchor/forest_patch/... (13종 enum)
    feature_subtype: str = ""
    feature_name: str = ""
    source_name: str = ""
    source_feature_id: str = ""
    x_5179: float
    y_5179: float
    lon: float | None = None
    lat: float | None = None
    elevation_m: float | None = None
    area_m2: float | None = None
    length_m: float | None = None
    element_wood: float = 0.0
    element_fire: float = 0.0
    element_earth: float = 0.0
    element_metal: float = 0.0
    element_water: float = 0.0
    importance: float = 1.0
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    anchor_role: str = ""
    anchor_index: int | None = None
    parent_feature_id: str = ""

    def element_map(self) -> dict[str, float]:
        """오행 한자 dict({木,火,土,金,水})로 변환."""
        return {
            "木": self.element_wood, "火": self.element_fire, "土": self.element_earth,
            "金": self.element_metal, "水": self.element_water,
        }


class RegionDirectionalTopFeature(BaseModel):
    """방위별 대표 기여 feature(설명·evidence용)."""

    feature_id: str = ""
    name: str = ""
    type: str = ""
    distance_m: float = Field(default=0.0, ge=0.0)
    influence: float = Field(default=0.0, ge=0.0)


class RegionDirectionalElementSummary(BaseModel):
    """읍면동 × 8방위 주변 지형 오행 요약(P4-Data, 지역 고정·사전계산).

    '지역 주변 어느 방향에 산/물'은 사용자 무관 고정 사실이므로 사전계산한다 — §4-4가 금지하는
    '사용자 기준 이동 방위 적합 저장'과 다르다(별도 summary). direction_code: N/NE/E/SE/S/SW/W/NW.
    """

    region_code: str
    direction_code: str
    wood_score: float = 0.0
    fire_score: float = 0.0
    earth_score: float = 0.0
    metal_score: float = 0.0
    water_score: float = 0.0
    nearest_mountain_m: float | None = None
    nearest_river_m: float | None = None
    nearest_water_m: float | None = None
    nearest_coast_m: float | None = None
    nearest_forest_m: float | None = None
    top_features: list[RegionDirectionalTopFeature] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class RegionDirectionalSummarySnapshot(BaseModel):
    """방위별 지형 요약 스냅샷(compiled/region_directional_summary_vX.json, P4-Data)."""

    model_version: str
    source_version: str = ""
    reviewed: bool = False
    region_count: int = 0
    items: list[RegionDirectionalElementSummary] = Field(default_factory=list)


class DirectionalFeature(BaseModel):
    """방향성 외부 지형 feature 1건(P4-5 계약). 외부 데이터 공급 전까지 비어 있음."""

    feature_type: str  # mountain/river/lake/coast/...
    feature_name: str = ""
    direction_code: str = ""
    distance_m: float = Field(default=0.0, ge=0.0)
    bearing_deg: float = 0.0
    element_signal: dict[str, float] = Field(default_factory=dict)


class DirectionalFeatureResult(BaseModel):
    """방향성 지형 판정 결과(P4-5 스텁). available=False면 점수 미개입·missing 표시만."""

    region_code: str
    available: bool = False
    reason: str = ""
    features: list[DirectionalFeature] = Field(default_factory=list)
    directional_element_vector: ElementVector = Field(default_factory=ElementVector)


class FengshuiFormResult(BaseModel):
    """풍수 형국 판정 결과(P4-5 스텁). DEM 미공급 → available=False."""

    region_code: str
    available: bool = False
    reason: str = ""
    signals: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DirectionalSectorProfile(BaseModel):
    """좌향(facing) → 전후좌우 sector(docs/12 §14-2·§14-3, 모드 B). 사신사 판정 기준.

    facing_bearing 입력 시에만 산출(없으면 모드 A=8방위 분포만). region_profile에 고정 저장 금지
    (방위는 사용자 좌향 기준값 — 절대원칙: §4-4·§14-11). sector는 한국 8방위 라벨(region_direction
    컨벤션과 동일: 북/북동/동/남동/남/남서/서/북서).
    """

    facing_bearing: float = Field(ge=0.0, lt=360.0)
    front_sector: str  # 주작
    back_sector: str  # 현무
    left_sector: str  # 청룡
    right_sector: str  # 백호


class FengshuiFormProfile(BaseModel):
    """풍수 형국 점수(docs/12 §14-4, B 계층). 오행 벡터(A)와 섞지 않는 별도 품질 축.

    채점 가중·임계는 reviewed:false 자체 기준 — 전문가 감수 전 활성 금지(§14-11·절대원칙 5).
    모든 점수 0 기본 → 미공급/스캐폴딩 단계에서 graceful(추천 점수 미개입).
    """

    region_code: str
    back_mountain_score: float = 0.0  # 현무
    front_water_score: float = 0.0  # 주작 물
    left_dragon_score: float = 0.0  # 청룡
    right_tiger_score: float = 0.0  # 백호
    open_front_score: float = 0.0  # 주작 개활
    road_rush_penalty: float = 0.0
    water_escape_penalty: float = 0.0
    excessive_pressure_penalty: float = 0.0
    isolated_flat_penalty: float = 0.0
    form_quality_score: float = 0.0  # 가산 − 페널티 종합(B 단독)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    available: bool = False  # 데이터·감수 전 False
    evidence: list[str] = Field(default_factory=list)


class RemedySuggestion(BaseModel):
    """비보/보완 제안(docs/12 §14-7, D 부가). 부족·과한 기운을 생활권 선택으로 보완. 단정 금지."""

    issue: str  # 예: water_overload·metal_excess
    recommendation: str  # 단정 금지 자연어
    element_to_add: list[str] = Field(default_factory=list)  # 한자 오행
    element_to_reduce: list[str] = Field(default_factory=list)


class PaltaekDirection(BaseModel):
    """팔택 방위 1건(생기/천의/… 또는 절명/…)."""

    direction: str  # 한국 8방위
    grade: str  # high/medium/avoid
    label: str  # 생기·천의·연년·복위 / 화해·육살·오귀·절명


class PaltaekResult(BaseModel):
    """팔택/본명궁 개인 길방위(docs/12 §14-6, optional·기본 OFF). 사주 용희신과 '별개 체계'다 —

    추천 점수에 기본 미반영(enabled=False), 사용자가 '길방위·잘 방향·집 방향'을 물을 때만 보조로
    켠다. 절대 용희신 우선 판정을 덮지 않는다(판정 우선순위 원칙). 본명궁 산식은 reviewed:false
    감수 대기 — enabled여도 산식 미구현 단계에서는 confidence 0.
    """

    enabled: bool = False
    auspicious_directions: list[PaltaekDirection] = Field(default_factory=list)
    inauspicious_directions: list[PaltaekDirection] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    system: str = "paltaek"


class RegionProfilesMeta(BaseModel):
    """프로필 스냅샷 메타(compiled/region_element_profiles_vX.meta.json, docs/12 §8).

    P1 산출의 단위·레이어·조인 커버리지를 기록해 시군구 230 퇴행을 막고(emd 카운트 검증),
    GIS 레이어 미반영 상태(direction_included=False)를 명시한다.
    """

    model_version: str
    source_gis_version: str
    direction_included: bool = False  # P1은 방위를 프로필에 저장하지 않음
    layers: list[str] = Field(default_factory=list)
    profile_counts: dict[str, int] = Field(default_factory=dict)  # ctprvn/sig/emd
    hanja_join: dict[str, int] = Field(default_factory=dict)  # 한자 조인 매칭/전체
    calculated_at: str = ""


class RegionProfilesSnapshot(BaseModel):
    """프로필 스냅샷 파일 본체(compiled/region_element_profiles_vX.json)."""

    model_version: str
    source_gis_version: str = ""
    reviewed: bool = False  # 자체 기준 초안 — 검수 전(절대원칙 5)
    meta: RegionProfilesMeta
    items: list[RegionElementProfile] = Field(default_factory=list)


__all__ = [
    "RegionResolution",
    "RegionLevel",
    "LayerType",
    "DominanceType",
    "IntentMode",
    "ElementVector",
    "RegionElementEvidence",
    "RegionGeoFeature",
    "RegionAdminUnit",
    "RegionAdminSnapshot",
    "RegionUnitInput",
    "RegionElementProfile",
    "TargetElements",
    "RegionRecommendationQuery",
    "RegionFitItem",
    "RegionRecommendationResult",
    "RegionFitFactor",
    "RegionFitSummary",
    "RegionRecommendationEvidence",
    "RegionMissingLayer",
    "RegionRecommendationExplanation",
    "RelocationRegionCandidate",
    "RegionTaekilContext",
    "ExternalGeoFeature",
    "RegionDirectionalTopFeature",
    "RegionDirectionalElementSummary",
    "RegionDirectionalSummarySnapshot",
    "DirectionalFeature",
    "DirectionalFeatureResult",
    "FengshuiFormResult",
    "TerrainRole",
    "FormEffect",
    "DirectionalSectorProfile",
    "FengshuiFormProfile",
    "RemedySuggestion",
    "PaltaekDirection",
    "PaltaekResult",
    "RegionProfilesMeta",
    "RegionProfilesSnapshot",
]
