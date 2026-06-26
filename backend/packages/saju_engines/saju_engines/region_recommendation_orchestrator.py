"""지역 추천 오케스트레이션 + 택일 결합 bridge (v2.2 P4-3·P4-4, docs/12 §6·§7·§9).

채팅/리포트 계층이 사용자 질문(intent·용희기구신·지역 scope)을 RegionRecommendationQuery로 바꾸고,
RegionElementEngine.recommend 결과를 LLM 입력 payload로 직렬화한다. LLM은 오행·점수·방위를 계산하지
않고 제공된 fit_summary·evidence로 설명만 한다(절대원칙 1·2). 택일 결합은 '어디'를 '언제(택일)'
엔진으로 넘기는 bridge payload까지만 만든다 — 실제 택일 점수는 date_selection 엔진 책임(역할 분리).
"""

from __future__ import annotations

from saju_shared_types.region_element import (
    IntentMode,
    RegionFitItem,
    RegionRecommendationExplanation,
    RegionRecommendationQuery,
    RegionResolution,
    RegionTaekilContext,
    RelocationRegionCandidate,
    TargetElements,
)

from .region_element_engine import RegionElementEngine
from .region_geo_stubs import DirectionalFeatureAdapter

# LLM 설명 지침(계산 금지·단정 금지·무데이터 지형 주장 금지). chat 계층이 프롬프트에 주입한다.
REGION_REASONING_DIRECTIVE = (
    "지역 오행·매칭 점수·방위는 엔진이 계산한 사실이다. 오행이나 점수를 새로 계산하지 말고, "
    "제공된 fit_summary(positive/negative)·evidence·방위로 '왜 유리하거나 부담일 수 있는지'를 "
    "단정 없이(유리·보완성·기류·부담 가능) 설명하라. missing_layers는 '지형 데이터 반영 전 1차 "
    "추정'이라고만 밝히고, 확정도가 낮으면 그 점을 함께 전한다. "
    "terrain_data_available=false면(directional_terrain.available=false 포함) "
    "'이 지역 북쪽에 산'·'남쪽에 하천'·'배산임수'·'풍수적으로 완성' 같은 실제 지형/방향 "
    "주장을 절대 하지 말 것 — 지명·한자·음운·방위·기초 스키마 기반 1차 추정임을 밝힌다. "
    "산·하천·해안·DEM 원천이 연결되면 지역별 지형 오행 정확도가 올라간다고 안내할 수 있다."
)
# 내부 계산 단위(emd)와 사용자 표시 단위(sig grouping) 분리(요구사항 1: 동·읍 단위 판별 유지).
_RESOLUTION_SURFACE = {
    RegionResolution.EUP_MYEON_DONG: "sig",
    RegionResolution.RI: "sig",
    RegionResolution.SIGUNGU: "sigungu",
    RegionResolution.SIDO: "sido",
}

# 의도 라벨(파서 토큰) → IntentMode. work_business=career, rest_healing=healing(docs/12 §7).
_INTENT_ALIASES: dict[str, IntentMode] = {
    "relocation": IntentMode.RELOCATION,
    "이사": IntentMode.RELOCATION,
    "거주": IntentMode.RELOCATION,
    "career": IntentMode.CAREER,
    "work_business": IntentMode.CAREER,
    "직장": IntentMode.CAREER,
    "사업": IntentMode.CAREER,
    "healing": IntentMode.HEALING,
    "rest_healing": IntentMode.HEALING,
    "휴식": IntentMode.HEALING,
    "치유": IntentMode.HEALING,
    "여행": IntentMode.HEALING,
    "general": IntentMode.GENERAL,
}


def resolve_intent_mode(label: str | None) -> IntentMode:
    """파서 의도 라벨 → IntentMode(미상은 GENERAL)."""
    if not label:
        return IntentMode.GENERAL
    return _INTENT_ALIASES.get(label.strip().lower(), IntentMode.GENERAL)


class RegionRecommendationOrchestrator:
    """파싱된 의도 → 지역 추천 질의 → 엔진 호출 → LLM payload 직렬화(순수 조립)."""

    def __init__(
        self,
        engine: RegionElementEngine,
        directional: DirectionalFeatureAdapter | None = None,
    ) -> None:
        self._engine = engine
        self._directional = directional

    def build_query(
        self,
        intent_mode: IntentMode,
        roles: dict[str, list[str]],
        base_location: str | None = None,
        candidate_scope: str | None = None,
        candidate_regions: list[str] | None = None,
        resolution: RegionResolution = RegionResolution.EUP_MYEON_DONG,
        top_n: int = 5,
    ) -> RegionRecommendationQuery:
        """의도·용희기구신·지역 scope → RegionRecommendationQuery(엔진 입력 계약)."""
        target = TargetElements(
            yongsin=roles.get("yongsin", []),
            huisin=roles.get("huisin", []),
            gisin=roles.get("gisin", []),
            gusin=roles.get("gusin", []),
            boost=roles.get("boost", roles.get("prefer_elements", [])),
        )
        return RegionRecommendationQuery(
            target_elements=target,
            base_location=base_location,
            candidate_scope=candidate_scope,
            candidate_regions=candidate_regions,
            resolution=resolution,
            intent_mode=intent_mode,
            top_n=top_n,
        )

    def recommend_payload(self, query: RegionRecommendationQuery) -> dict:
        """엔진 추천 → LLM 입력 payload(설명 대상 사실 + 지침). 계산은 전부 엔진이 끝냈다.

        내부 계산 단위(query.resolution, 보통 emd)는 그대로 두고, 표시용으로 시군구 grouping을
        함께 제공한다(요구사항 1: 동·읍 단위 계산 유지·시군구 surface). 방향성 어댑터가 있으면 각
        지역의 주변 지형('북 산·남 강')을 terrain으로 덧붙인다(P4-Data, 없으면 available=false).
        """
        result = self._engine.recommend(query)
        terrain_available = self._directional is not None and self._directional_has_data()
        regions: list[dict] = []
        for ex in result.explanations:
            payload = _explanation_payload(ex)
            if self._directional is not None:
                payload["directional_terrain"] = _directional_payload(
                    self._directional, ex.region_code
                )
            regions.append(payload)
        computed_level = query.resolution.value
        out = {
            "intent": query.intent_mode.value,
            "base_location": query.base_location,
            "directive": REGION_REASONING_DIRECTIVE,
            "terrain_data_available": terrain_available,
            "computed_level": computed_level,
            "surface_level": _RESOLUTION_SURFACE.get(query.resolution, computed_level),
            "regions": regions,
            "notes": result.notes,
        }
        if query.resolution in (RegionResolution.EUP_MYEON_DONG, RegionResolution.RI):
            out["surface"] = _group_by_sigungu(result.explanations)
        return out

    def _directional_has_data(self) -> bool:
        """방향성 요약이 실제로 적재됐는지(어떤 region이라도 available)."""
        if self._directional is None:
            return False
        return bool(getattr(self._directional, "_by_region", {}))


def _explanation_payload(ex: RegionRecommendationExplanation) -> dict:
    """설명 1건 → LLM 친화 dict(점수·근거·미공급 레이어 — 단정 금지 입력)."""
    return {
        "region_code": ex.region_code,
        "full_name_ko": ex.full_name_ko,
        "match_score": ex.match_score,
        "avoid_score": ex.avoid_score,
        "confidence": ex.confidence,
        "dominant_elements": ex.dominant_elements,
        "element_vector": ex.element_vector.as_map(),
        "fit_summary": {
            "positive": [
                {"element": f.element, "role": f.role, "weight": f.weight, "reason": f.reason}
                for f in ex.fit_summary.positive
            ],
            "negative": [
                {"element": f.element, "role": f.role, "weight": f.weight, "reason": f.reason}
                for f in ex.fit_summary.negative
            ],
        },
        "direction": ex.direction,
        "direction_fit": ex.direction_fit,
        "missing_layers": [m.layer for m in ex.missing_layers],
    }


def _group_by_sigungu(
    explanations: list[RegionRecommendationExplanation],
) -> list[dict]:
    """읍면동 추천을 시군구로 grouping(표시용). 계산 단위는 emd 유지, surface만 시군구.

    각 시군구 그룹: 대표 match_score(소속 emd 최고) + top_emd_candidates(코드·full_name·점수).
    그룹 순서는 대표 점수 내림차순.
    """
    groups: dict[str, dict] = {}
    for ex in explanations:
        sigungu = " ".join(ex.full_name_ko.split()[:-1]) or ex.full_name_ko
        g = groups.setdefault(sigungu, {
            "sigungu_full_name": sigungu, "match_score": 0, "top_emd_candidates": [],
        })
        g["match_score"] = max(g["match_score"], ex.match_score)
        g["top_emd_candidates"].append({
            "region_code": ex.region_code,
            "full_name_ko": ex.full_name_ko,
            "match_score": ex.match_score,
            "dominant_elements": ex.dominant_elements,
        })
    out = sorted(groups.values(), key=lambda g: -g["match_score"])
    for g in out:
        g["top_emd_candidates"].sort(key=lambda c: -c["match_score"])
        g["top_emd_candidates"] = g["top_emd_candidates"][:3]
    return out


def _directional_payload(adapter: DirectionalFeatureAdapter, region_code: str) -> dict:
    """주변 방향성 지형 → payload(available/벡터/하이라이트). 데이터 없으면 available=False."""
    result = adapter.evaluate(region_code)
    if not result.available:
        return {"available": False}
    highlights = [
        f"{f.direction_code} {f.feature_name or f.feature_type} {round(f.distance_m)}m"
        for f in result.features[:5]
    ]
    return {
        "available": True,
        "vector": result.directional_element_vector.as_map(),
        "highlights": highlights,
    }


def to_taekil_context(
    item: RegionFitItem,
    region_code: str,
    event_type: str = "relocation",
    date_range: dict[str, str] | None = None,
    user_chart_context: dict | None = None,
) -> RegionTaekilContext:
    """지역 추천 1건 → 택일 엔진 입력 컨텍스트(P4-4 bridge). 실제 택일 점수는 미산출(역할 분리).

    direction_elements는 방위 라벨(item.direction)에서 region_direction 혼합 모델 기준으로 채운다.
    """
    candidate = RelocationRegionCandidate(
        region_code=region_code,
        full_name_ko=item.region_name,
        region_elements=item.dominant_elements,
        element_vector=item.element_vector,
        direction_from_base=item.direction,
        direction_elements=_direction_elements(item.direction),
        match_score=item.match_score,
    )
    return RegionTaekilContext(
        event_type=event_type,
        target_region=candidate,
        date_range=date_range or {},
        user_chart_context=user_chart_context or {},
    )


def _direction_elements(direction: str) -> list[str]:
    """방위 라벨 → 구성 오행(region_direction 혼합 모델 재사용). 미상이면 빈 리스트."""
    from .region_direction import _DIRECTION_ELEMENTS

    return list(_DIRECTION_ELEMENTS.get(direction, {}).keys())
