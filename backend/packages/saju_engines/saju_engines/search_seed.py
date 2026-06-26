"""검색 기반 지형 feature 부트스트랩 코어(P4-SearchSeed, docs/12).

공식 GIS 원천 수급 전, 행정구역명 + 지형 키워드 검색 결과를 지역 오행 엔진용 feature로 빠르게
정규화한다. 본 모듈은 API 호출을 제외한 순수 로직(쿼리 키워드·feature_type 분류·오행 매핑·신뢰도·
등거리 투영·중복 병합)만 담는다 — 네트워크/키 의존은 fetch 스크립트가 담당(provider 주입).

검색 데이터는 오탐(카페·식당명에 '산'/'계곡')이 섞이므로 카테고리 거름 + 낮은 confidence +
review_status로 검수 전 신호임을 강제한다(절대원칙 5). 하천/해안은 대표 feature로만 쓴다
(추후 공식 GIS anchor로 교체).
"""

from __future__ import annotations

import math
import re

from pydantic import BaseModel, Field

# 1단계 검색 키워드(시군구명에 붙임). 읍면동 전수 금지 — 후보/질의 지역만 확장.
QUERY_KEYWORDS: tuple[str, ...] = (
    "산", "하천", "강", "계곡", "호수", "저수지", "해변", "항구", "공원",
)
# feature_type → 분류 키워드(카테고리/이름 매칭). 긴 키워드 우선(오탐 완화).
_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "valley_anchor": ("계곡", "폭포"),
    "lake_centroid": ("저수지", "호수", "호", "못"),
    "coast_anchor": ("해수욕장", "해변", "해안", "갯벌"),
    "port": ("항구", "포구", "선착장", "나루", "항"),
    "forest_patch": ("자연휴양림", "수목원", "숲"),
    "park_green": ("근린공원", "생태공원", "공원"),
    "river_anchor": ("하천", "개천", "강", "천"),
    "mountain_peak": ("봉우리", "고개", "산", "봉", "악", "령", "재"),
}
# 비지형(오탐) 카테고리 — 이런 장소는 reject.
_REJECT_CATEGORY = (
    "음식점", "카페", "술집", "주점", "숙박", "쇼핑", "병원", "약국", "학교", "학원",
    "마트", "편의점", "미용", "은행", "주유소", "부동산", "기업", "아파트",
)
# 지형 카테고리 신호(카테고리 매칭 = 강신뢰).
_GEO_CATEGORY = ("관광", "명소", "자연", "공원", "산", "하천", "해수욕장", "휴양")

_CONF_CATEGORY = 0.70  # 카테고리 일치 + 좌표 + 이름 규칙
_CONF_NAME = 0.55  # 이름 규칙만
_CONF_QUERY = 0.45  # 검색어 추론만
_CONF_MULTI_BONUS = 0.10  # 중복 출처 2+
_CONF_MAX = 0.85  # 자동 상한(수동 검수=0.90)

# 등거리 투영(거리·방위용). 한반도 중심 위도 36° 기준 평면 근사(km 버킷·8방위에 충분).
_R = 6_371_000.0
_LAT0 = math.radians(36.0)
_COS0 = math.cos(_LAT0)
_DEDUPE_RADIUS_M = 300.0


class SearchSeedFeature(BaseModel):
    """검색 기반 지형 feature 1건(검수 전 초안). source=search_seed."""

    feature_id: str
    source: str = "search_seed"
    search_query: str = ""
    region_code: str = ""
    region_level: str = ""
    region_name_ko: str = ""
    feature_name: str
    feature_type: str = ""
    feature_subtype: str = ""
    lon: float
    lat: float
    element_wood: float = 0.0
    element_fire: float = 0.0
    element_earth: float = 0.0
    element_metal: float = 0.0
    element_water: float = 0.0
    confidence: float = Field(default=0.45, ge=0.0, le=1.0)
    review_status: str = "needs_review"  # auto_high_confidence/needs_review/rejected/verified
    source_count: int = 1
    matched_regions: list[str] = Field(default_factory=list)
    raw_json: str = ""


def project_equirect(lon: float, lat: float) -> tuple[float, float]:
    """lon/lat → 등거리 평면(미터). anchor·feature 동일 투영으로 거리/방위 정합."""
    return (_R * math.radians(lon) * _COS0, _R * math.radians(lat))


def classify_feature_type(
    name: str, category: str = "", query_keyword: str = ""
) -> tuple[str | None, str]:
    """장소명·카테고리·검색어 → (feature_type, matched_by). 비지형이면 (None, 'rejected').

    matched_by: 'category'(강) / 'name'(중) / 'query'(약) / 'rejected'.
    """
    cat = category or ""
    if any(r in cat for r in _REJECT_CATEGORY):
        return None, "rejected"
    # 1) 카테고리 키워드(가장 강한 신호).
    geo_cat = any(g in cat for g in _GEO_CATEGORY)
    for ftype, kws in _TYPE_KEYWORDS.items():
        if any(kw in cat for kw in kws):
            return ftype, "category" if geo_cat else "name"
    # 2) 이름 규칙(접미/포함).
    for ftype, kws in _TYPE_KEYWORDS.items():
        if any(name.endswith(kw) or (len(kw) >= 2 and kw in name) for kw in kws):
            return ftype, "name"
    # 3) 검색어 기반 추론(가장 약함).
    if query_keyword:
        for ftype, kws in _TYPE_KEYWORDS.items():
            if query_keyword in kws or query_keyword == ftype:
                return ftype, "query"
    return None, "rejected"


def element_vector_for(feature_type: str, rules: dict) -> dict[str, float]:
    """feature_type → 오행 벡터(region_geo_feature_elements.json feature_type_rules)."""
    return dict(rules.get("feature_type_rules", {}).get(feature_type, {}))


def base_confidence(matched_by: str) -> float:
    """매칭 강도 → 기본 신뢰도."""
    return {"category": _CONF_CATEGORY, "name": _CONF_NAME}.get(matched_by, _CONF_QUERY)


def _normalize_name(name: str) -> str:
    """feature_name 정규화(공백·괄호·접미 행정어 제거) — 중복 판정 키."""
    n = re.sub(r"\(.*?\)", "", name)
    n = re.sub(r"\s+", "", n)
    return n.strip()


def dedupe(features: list[SearchSeedFeature]) -> list[SearchSeedFeature]:
    """같은 이름 + 300m 이내 + 같은 type → 병합. source_count·matched_regions·confidence 갱신."""
    used = [False] * len(features)
    projected = [project_equirect(f.lon, f.lat) for f in features]
    out: list[SearchSeedFeature] = []
    for i, f in enumerate(features):
        if used[i]:
            continue
        used[i] = True
        cluster = [f]
        xi, yi = projected[i]
        key = _normalize_name(f.feature_name)
        for j in range(i + 1, len(features)):
            if used[j]:
                continue
            g = features[j]
            if g.feature_type != f.feature_type:
                continue
            if _normalize_name(g.feature_name) != key:
                continue
            xj, yj = projected[j]
            if math.hypot(xi - xj, yi - yj) <= _DEDUPE_RADIUS_M:
                used[j] = True
                cluster.append(g)
        out.append(_merge_cluster(cluster))
    return out


def _merge_cluster(cluster: list[SearchSeedFeature]) -> SearchSeedFeature:
    """중복 클러스터 → 대표 1건(출처 수·지역·신뢰도 병합)."""
    rep = cluster[0].model_copy(deep=True)
    rep.source_count = len(cluster)
    regions: list[str] = []
    for c in cluster:
        for r in [c.region_name_ko, *c.matched_regions]:
            if r and r not in regions:
                regions.append(r)
    rep.matched_regions = regions
    if len(cluster) >= 2 and rep.review_status != "verified":
        rep.confidence = min(_CONF_MAX, rep.confidence + _CONF_MULTI_BONUS)
    return rep
