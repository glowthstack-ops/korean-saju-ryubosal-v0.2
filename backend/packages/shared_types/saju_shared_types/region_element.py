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
    evidence: list[EvidenceBundle] = Field(default_factory=list)  # Graph RAG 경로(P4)


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
    "RegionAdminUnit",
    "RegionAdminSnapshot",
    "RegionUnitInput",
    "RegionElementProfile",
    "TargetElements",
    "RegionRecommendationQuery",
    "RegionFitItem",
    "RegionRecommendationResult",
    "RegionProfilesMeta",
    "RegionProfilesSnapshot",
]
