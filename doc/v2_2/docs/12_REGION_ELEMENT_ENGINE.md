# 12. 지역 오행 추천 엔진 (Region Element Engine)

> 본 문서는 사용자 확정 설계(2026-06-26 대화)를 본 리포(Python) 규격으로 옮긴 **권위 스펙**이다.
> docs/02·09의 엔진/사전계산 원칙을 따르며, 항목·목록·산식은 "예시"가 아니라 전체 규격이다
> (CLAUDE.md 절대원칙 10). 문서에 없는 명리 규칙·보정이 필요해 보이면 구현하지 말고 질문한다.

## 0. 한 줄 정의

**지역 자체의 고유 오행(고정)** 과 **사용자 기준 추천 오행(가변)** 을 분리한다. 지역 오행은
빌드 타임에 5차원 벡터로 사전계산해 스냅샷에 저장하고(고정), 추천은 요청 시점에 사용자의
용/희/기/구신·현재 거주지·질문 의도로 매칭한다(가변). LLM은 계산하지 않고 evidence를
자연어로 설명만 한다(절대원칙 1·2).

## 1. 엔진의 역할

입력(요청):

```json
{
  "user_question": "나에게 맞는 이사 지역을 추천해줘",
  "target_elements": { "yongsin": ["木"], "huisin": ["火"], "gisin": ["金"], "gusin": ["土"] },
  "base_location": "서울특별시 마포구",
  "candidate_scope": "수도권",
  "resolution": "eup_myeon_dong",
  "intent_mode": "relocation"
}
```

출력(추천):

```json
{
  "recommended_regions": [
    {
      "region_name": "경기도 ○○시 ○○읍",
      "legal_dong_code": "412xxxxxxx",
      "dominant_elements": ["木", "水"],
      "element_vector": { "木": 0.38, "火": 0.12, "土": 0.18, "金": 0.07, "水": 0.25 },
      "match_score": 84, "avoid_score": 11, "confidence": 0.76,
      "reason_summary": "산림·하천 비중이 높고 지명 한자·지형 신호가 木·水로 수렴. 용신 木 보완성이 높음.",
      "evidence": ["산림 비율 높음", "하천 접근성 있음", "지명 한자 木 계열", "현재 거주지 기준 동남동"],
      "risk_flags": ["water_overload_possible"]
    }
  ]
}
```

**관심 분리 원칙**: 지역 오행 프로필에는 *방위*를 저장하지 않는다(방위는 base_location에 따라
바뀌는 사용자 기준 값이므로 추천 시점 계산). docs §4-4·§11 참조.

## 2. 행정구역 기준 — 법정동을 기본 키로

내부 연산 우선순위:

```
1순위: 법정동/읍면동 코드 (legal_dong_code)   — 고유 ID
2순위: 법정구역 polygon                        — 지형·수계 overlay
3순위: 행정동 alias                            — 표시 보조
4순위: 사용자 표시용 주소명 (full_name)
```

행정동은 표시에만 함께 노출하고, 엔진 내부 연산은 법정동 기준으로 한다. 1차 구현 해상도는
**전국 법정동 전체**(사용자 확정). 동/읍 단위까지 구분하되, 농촌은 리(里) 단위 확장 여지를 남긴다.

데이터 출처(수집 대상, §10):
- 법정동 코드: 행정안전부 행정표준코드 / 국토교통부 전국 법정동(월간 갱신)
- 경계 polygon: 국토교통부 일별법정구역정보(SHP)

## 3. 데이터 레이어 (수집 규격)

### A. 행정구역 레이어 — `region_admin_unit`

| 필드 | 용도 |
|---|---|
| region_id | 내부 고유 ID |
| legal_dong_code | 법정동 코드(연산 기본 키) |
| sido / sigungu / eup_myeon_dong / ri | 단계별 명칭 |
| full_name | 표시용 전체 주소명 |
| active_yn, created_at, deleted_at | 과거명·폐지 처리 |
| parent_code | 상위 코드 |
| centroid(lat,lon), area_m2 | 방위·거리·면적 정규화 |

### B. 지명·한자·독음 레이어 — `region_name_fact`

지명의 *의미*를 오행 신호로 변환하기 위한 레이어. 수집 우선순위:

```
1순위: 국토지리정보원 지명유래집 / 지명조사철
2순위: 지자체 공식 지명 유래
3순위: 문화재·향토지
4순위: 사전 기반 한자 후보
5순위: LLM 추정 — confidence 낮게
```

필드: hangul_name, hanja_name, reading, old_name, name_origin_text, source_type,
source_ref, confidence. **한자만으로 지역 오행을 확정하지 않는다**(§11 원칙 1).

### C. 지형·수계·토지피복 레이어 — `region_geo_feature`

지역 오행의 핵심(가중 최대). 출처: 환경공간정보서비스(토지피복지도), 산림청 임상도(1:5000),
VWorld/연속수치지형도 실폭하천, WAMIS 수자원단위지도, DEM.

필드(규격): mean_elevation, elevation_p70, slope_mean, slope_p70, forest_area_ratio,
water_area_ratio, river_length_density, coast_distance_m, coast_touch_yn, wetland_ratio,
agricultural_ratio, urban_built_ratio, industrial_ratio, road_density, rail_density,
south_facing_slope_ratio, basin_score, mountain_score, plain_score, source_version.

## 4. 오행 판정 방식 (레이어별 벡터)

최종 지역 오행은 단일 판정이 아니라 **레이어별 벡터의 가중합**을 5차원으로 저장한다:
`{木,火,土,金,水}`. "이 지역은 木"이 아니라 "木 우세, 水 보조"로 표현한다.

### 4-1. 실제 지형 기반(최고 비중)

| 오행 | 지형 신호 |
|---|---|
| 木 | 산림·숲·수목·공원·녹지·완만한 산록·생장성 |
| 火 | 남향·일조·고지대 노출·상업 활동·열섬·광장성 |
| 土 | 산·구릉·평야·농지·대지·중심부·안정 지반 |
| 金 | 암반·돌산·광물·공업지·도로/철도/금속 인프라·서쪽성 |
| 水 | 강·하천·호수·바다·습지·저지대·항구·계곡 |

핵심: **山을 무조건 木으로 보지 않는다.** 산 지형성은 土, 산림 피복이 강할 때 木. 조합 예:
`산지+숲→土+木`, `강변+상업→水+火`, `해안+항구+공업→水+金`, `평야+농지→土+木`, `돌산+공업→土+金`.

### 4-2. 지명 한자 기반(보조)

대표 한자: 木(木林森松竹梅柳桂東靑) / 火(火炎日陽光明南赤) / 土(土山岳峰原田坪城基垈中黃) /
金(金鐵銀銅鑛錫石西白) / 水(水江河川海湖泉浦津溪谷北黑).

문맥 의존 글자는 규칙으로 처리: `山`=土(산림 강하면 木 보조), `石`=土(광물·금속 연결 시 金),
`谷`=水(산지면 土 보조), `田`=土(생장성 木 보조), `浦/津`=水(항만 산업 金 보조). 글자별
weight를 매겨 `name_element_vector`로 합성하고 confidence를 부여한다.

### 4-3. 한글 독음·음운 오행(낮은 비중, ≤3%)

초성 매핑: `ㄱㅋ→木` / `ㄴㄷㄹㅌ→火` / `ㅇㅎ→土` / `ㅅㅈㅊ→金` / `ㅁㅂㅍ→水`. 학파 차가
크고 지형보다 신뢰도가 낮아 보조 신호로만 쓴다.

### 4-4. 방위 오행(지역 고유값 아님 — 추천 시점 계산)

base_location → 후보 centroid → bearing → 방위 오행. **`region_element_profile`에 저장 금지.**
기존 [region_direction.py](../../../backend/packages/saju_engines/saju_engines/region_direction.py)의
명리형 혼합 모델(사정 단일 / 간방 45:45:10 + 土 전환)을 그대로 재사용한다. 후천팔괘는 좌향용
별개 체계로 기본값 아님(데굴님 확정 2026-06-25).

### 4-5. 풍수 형국 보조 레이어(V2)

배산임수·산지 포위성·수구 방향·분지성·개활성·해안성·교통 관문성을 DEM/경계로 자동 판정.
오행을 직접 확정하기보다 "지역 품질 보정"에 가깝다: `배산임수→土+水 안정 가산`,
`분지→土 강·水 정체 보정`, `강변 개활→水+火`, `산림 계곡→木+水+土`.

## 5. 최종 오행 산식

기본 가중(레이어):

```
physical_geography    0.45
landcover_hydro_forest 0.20
hanja_place_name      0.15
relative_direction    0.10   (base_location 없으면 제외)
fengshui_form         0.07
phonetic_reading      0.03
```

```
region_element_vector = normalize(
    Σ_layer ( layer_vector × weight × layer_confidence )
)
```

**스텁 환경 재정규화(절대원칙 11)**: 미공급 레이어(confidence=0)는 제외하고, 그 부분집합으로
weight를 재정규화한다. P1에선 지형·토지·풍수가 미공급이므로 한자/음운/방위/좌표근사만으로
정규화 → GIS 공급 시 비중이 자동 이동한다.

dominance 등급:

```
단일 우세:  max_element ≥ 0.42 AND (1위−2위) ≥ 0.12
복합 우세:  (1위+2위) ≥ 0.62 AND (1위−2위) < 0.15
경합:      1위 < 0.35 OR top3 근접
판정 보류:  confidence < 0.45
```

## 6. 사용자 사주 매칭

사용자 오행 요구 벡터(역할 → 점수):

| 구분 | 점수 |
|---|---|
| 용신 | +1.00 |
| 희신 | +0.65 |
| 보완 필요 오행 | +0.45 |
| 한신 | 0 |
| 구신 | −0.60 |
| 기신 | −1.00 |

```
match_score = positive_alignment − negative_alignment + intent_bonus
            + confidence_bonus − overdominance_penalty
```

보정: `기신 오행 ≥ 0.30 → 강한 감점`, `구신 ≥ 0.35 → 중간 감점`, 용신이 있어도 기신이 함께
강하면 "조건부 추천", 오행 경합 지역은 "무난하지만 선명하지 않음". 0~100 스케일로 표기.

## 7. 질문 의도별 추천 모드(가중 치환)

| 모드 | 가중 핵심 |
|---|---|
| 이사·거주(relocation) | 지형0.50/풍수0.15/방위0.13/한자0.12/현대활동0.10 |
| 직장·사업(career) | 지형0.30/현대활동0.30/방위0.15/교통0.15/한자0.10 (金·火 별도) |
| 휴식·치유·여행(healing) | 지형0.45/산림수계0.30/풍수0.15/한자0.05/방위0.05 |
| 택일 연동 이사 | 지역 후보 선별 → 방위 오행 → 대운/세운/월운 → 일운 충형파해·손없는날 필터 → 최종일 |

지역 엔진은 "어디"를, 택일 엔진([date_selection.py](../../../backend/packages/saju_engines/saju_engines/date_selection.py))은
"언제"를 담당한다. 결합은 V2.

## 8. 데이터/스냅샷 구조

원본 사전(`backend/dictionaries/region/`):
- `region_hanja_tokens.json` — §4-2 글자→오행 + 문맥 규칙
- `region_phonetic.json` — §4-3 초성 오행
- `region_layer_weights.json` — §5 기본 + §7 의도별
- `region_dominance_rules.json` — §5 dominance 임계
- `geo/region_geo_feature.sample.json` — §3-C GIS feature 스키마/스텁 자리
- `region_admin_unit.json` — §3-A 법정동(P2, ingest_legal_dong.py 생성)

사전계산 스냅샷(`backend/compiled/`): `region_element_profiles_vX.json` — 지역별 5차원 벡터 +
dominance + evidence. 요청 시점엔 스냅샷 로드 후 사용자 매칭·방위만 계산(절대원칙 9).

## 9. 추천 결과 설명 구조

사용자용은 단정 없이 근거를 곁들인 자연어(LLM 생성), 개발자용은 evidence/feature 수치 포함.
단정 표현 금지(절대원칙 3) — "유리/보완성/기류"로 표현.

## 10. 구현 단계(이 리포 PR 단위)

| Phase | 내용 | GIS | 상태 |
|---|---|---|---|
| P0 | 본 설계 문서 + pydantic I/O 스키마 + 사전 스켈레톤(동작 변화 0) | 무 | ✅ |
| P1 | 한자(기존 흡수)+음운+방위(재사용)+상속 → 벡터·dominance·매칭, region_fit 승격, **읍면동 5,065** 프로필 스냅샷 | 무 | ✅ 2026-06-26 |
| P2 | 행정구역 registry(경량 admin) + 지명 해소기(RegionNameResolver) + scope 후보 열거 | 무 | ✅ 2026-06-26 |
| P3 | GIS feature 어댑터(지형/수계/토지피복/임상도/DEM) 스키마+어댑터+스텁, 공급 시 지형 레이어 활성화 | 유 | ✅ 2026-06-26 |
| P4-A | 의도별 가중 치환·evidence 구조화·chat 오케스트레이션·택일 bridge | 무 | ✅ 2026-06-26 |
| P4-B | 방향성 지형(산/하천/해안) — feature index→방위 요약 파이프라인+어댑터(데이터 공급 시 활성) | 유 | ✅ 2026-06-26 |
| P4-B(풍수) | 배산임수·분지 등 형국(DEM) — FengshuiFormAdapter 스텁(DEM 미공급) | 유 | 스텁 |

각 Phase = 타입 + 구현 + 단위 테스트 + 회귀 픽스처(완료 기준, docs/07).

### P1 구현 메모(사용자 확정 2026-06-26)

- 단위: 시군구가 아니라 **읍면동(emd) 5,065 포함** 5,332 단위 전체. 입력=doc/gis
  `region_units_compact_20230729`(계산용 경량 GIS). 엔진=[region_element_engine.py](../../../backend/packages/saju_engines/saju_engines/region_element_engine.py),
  빌더=[build_region_profiles.py](../../../backend/scripts/build_region_profiles.py),
  스냅샷=`compiled/region_element_profiles_v1.json`(+meta).
- **D1 음운 cap**: 음운 유효가중 0.03 절대 상한 + 신뢰도 비-기여(우세 판정은 한자/폴백/상속만).
- **D2 한자 소스**: region_hanja_tokens 토큰화 우선(248/250 시군구) → 미매칭은 region_elements
  큐레이션 오행으로 confidence 0.35 폴백(weak). `alt.when`(지형조건)은 P3 전까지 미발동.
- **계층 상속**: 한자 없는 읍면동은 부모 시군구 프로필 상속(신뢰도 감쇠). 시도·일부 시군구는
  음운만 → confidence 매우 낮춰 unknown(과확정 금지).
- **dominance 밴드**: confidence<0.35 unknown / <0.55 weak / 그 이상에서 single→composite→contested.
- **match_score**: raw_fit(Σ벡터×역할점수) − penalty(기신·구신 비중) , confidence 보정 + 저신뢰
  상한(conf<0.55→78, <0.40→65). 방위는 프로필 미저장·추천 시점 계산(§4-4).

### P2 구현 메모(사용자 확정 2026-06-26)

원래 P2(별도 admin_unit 적재)는 "데이터 미보유" 전제였으나 P1에서 이미 읍면동 5,065를
프로필에 적재(region_code·level·parent_code·full_name·anchor 보유)했으므로, 별도 admin 적재는
대부분 중복 → **이름 해소 계층 + 경량 admin registry**로 재정의(사용자 승인 옵션 A).

- 경량 registry: [build_region_admin.py](../../../backend/scripts/build_region_admin.py) →
  `compiled/region_admin_units_v1.json`(구조화 이름·area_m2·parent 트리만, 좌표는 프로필 재사용으로
  생략 — 5,332단위 1.4M). `RegionAdminUnit`에 region_level 추가, `RegionAdminSnapshot` 신설.
- 해소기 [RegionNameResolver](../../../backend/packages/saju_engines/saju_engines/region_element_engine.py):
  읍면동명 전국 590종 중복(효자동·사직동) 대응 — full_name 완전일치 → 시도 별칭 확장 토큰 포함
  → leaf 명 동률 시 leaf 정확일치로 좁힘. **끝까지 모호하면 추측 않고 후보 목록 반환**(절대원칙 7).
  scope: 수도권(서울·경기·인천)·시도(약식 포함)·상위지역 하위 트리(BFS) → 후보 region_code 열거.
- recommend() 배선: candidate_regions/base_location은 해소기로 코드 확정(모호 시 노트), candidate_scope는
  resolve_scope로 후보군 확정. 해소기 미로딩(admin_path None) 시 legacy full_name 매칭으로 graceful 폴백.

### P3 구현 메모(2026-06-26)

doc/gis sqlite의 `external_feature`·`region_feature_direction`는 0행(외부 지형 데이터 미공급,
README 한계) → P3는 §10 정의대로 **"스키마+어댑터+스텁, 공급 시 활성화"**. 외부 데이터 부재 시
빌드 산출은 P1/P2와 동일(지형 레이어 제외).

- 스키마: `RegionGeoFeature`(§3-C 집계 필드 — forest/water/mountain_score/slope/elevation 등),
  `region/region_geo_signal_rules.json`(§4-1 매핑: forest→木, water/river/wetland/coast→水,
  mountain_score→土(+木 alt), plain/basin→土, south_facing/elevation→火, industrial/road/rail→金).
  dictionaries 등록+lint, geo 샘플도 스키마 검증.
- 어댑터([region_element_engine.py](../../../backend/packages/saju_engines/saju_engines/region_element_engine.py)):
  `_geo_layers`가 feature를 physical_geography(0.45)·landcover_hydro_forest(0.20) 레이어 벡터로
  변환(정규화: ratio 0~1·density/고도 norm·bool). build_profile이 지형 레이어를 §5 결합에 추가→
  재정규화로 지형이 우세(절대원칙 11), **자체 지형 신호 있으면 부모 상속 차단**(own_signal 게이트).
  한자 문맥규칙 `alt.when`(D2 보류분)도 지형 신호 충족 시 활성(山+산림→土+木).
- 빌더: `build_region_profiles.py [units] [compiled] [geo]` — 지형 파일(기본
  doc/gis/region_geo_features.jsonl) 공급 시 활성, 부재 시 graceful(산출 동일).
- sqlite의 external_feature 포인트 모델 + region_feature_direction + emd_direction_probe(16만)는
  방향성 풍수(§4-5)용 → **P4-B**에서 활용(외부 데이터 공급 전제).

### P4 구현 메모(사용자 확정 2026-06-26 — A/B 분리)

외부 데이터 의존 여부로 분리: **P4-A는 구현, P4-B는 스텁+계약**. P4-A가 지역 엔진을 실사용
오케스트레이션에 연결한다.

- **P4-1 의도별 가중 치환**: `region/region_intent_weights.json`(IntentMode별 preset, career=직장·사업,
  healing=휴식·치유) + `RegionElementEngine.resolve_intent_weights(intent, available)` — 미공급 레이어
  제외 후 재정규화(절대원칙 11), phonetic 0.03 cap 유지, 미공급은 missing_layers로 보고(0점 감점 금지).
  아키텍처: 고정 프로필은 단일 벡터로 저장되므로 intent 전면 재가중은 지형 데이터+per-layer 저장이
  필요 → P4-A는 가중 해소 메커니즘 + explanation/missing 노출, match_score(고정 벡터)는 불변.
- **P4-2 evidence 구조화**: `RegionFitSummary`(positive/negative/neutral)·`RegionRecommendationEvidence`
  (layer/signal/element/strength/confidence)·`RegionMissingLayer`·`RegionRecommendationExplanation`.
  `explain_fit()`이 역할별 적합 근거 + 레이어 근거 + 미공급 레이어를 산출, recommend가 top_n에 부착.
- **P4-3 chat 오케스트레이션**: [region_recommendation_orchestrator.py](../../../backend/packages/saju_engines/saju_engines/region_recommendation_orchestrator.py)
  — 의도 라벨→IntentMode, 용희기구신→RegionRecommendationQuery, recommend→LLM payload(계산 금지
  지침 REGION_REASONING_DIRECTIVE 포함). LLM은 fit_summary·evidence로 설명만.
  - **chat 라우터 실배선(2026-06-26)**: chat_service `_region_recommendation_context`가 이사 의도
    + 목적지 미지정/시도·수도권 범위일 때 favorability_map→용희기구신으로 orchestrator를 호출해
    시군구 후보를 구조 블록에 surface(특정 시군구는 기존 `_relocation_region_context` 단건 궁합이
    담당). 거주지 있으면 방위도 산출. compiled 미빌드 시 graceful(None). 방향성 요약 있으면 주변
    지형 하이라이트 동반.
- **P4-4 택일 bridge**: `RelocationRegionCandidate`·`RegionTaekilContext` + `to_taekil_context()` —
  '어디(지역)'를 '언제(택일)' 엔진으로 넘기는 페이로드. 실제 택일 점수는 date_selection 책임(역할 분리).
- **P4-5 풍수/방향성 스텁**: [region_geo_stubs.py](../../../backend/packages/saju_engines/saju_engines/region_geo_stubs.py)
  — `FengshuiFormAdapter`(DEM 미공급→available=False), `DirectionalFeatureAdapter`. available=False는
  감점하지 않고 missing 표시만.

### P4-Data 구현 메모(외부 지형 feature index, 사용자 확정 2026-06-26)

"원본 SHP가 아니라 **feature coordinate index**"(사용자 §). 외부 지형은 대표 좌표로 압축해
**읍면동×8방위 주변 지형 오행 요약**을 사전계산한다. 데이터 수급/변환(SHP→좌표)은 상류 툴킷
[doc/gis_region](../../../doc/gis_region/)이 담당(geopandas/pyproj), 백엔드는 핸드오프 CSV를 받는다.

- **수급 우선순위(사용자 확정)**: ①국가관심지점 POI(산/고개/계곡/항구) ②하천중심선/실폭하천
  ③해안선 → ④임상도(산림) ⑤토지피복 → ⑥DEM(풍수) ⑦WAMIS. P4-B는 ①②③로 시작 가능.
- **계약 정렬**(doc/gis_region SQL과 1:1): `ExternalGeoFeature`(대표 좌표+오행벡터),
  `RegionDirectionalElementSummary`(읍면동×8방위 오행 점수+nearest_*+top_features). 오행 매핑은
  `region/region_geo_feature_elements.json`(툴킷 rules 미러, 13 feature_type, 거리 버킷 1/3/5/10km).
- **백엔드 빌더**: [build_region_directional_summary.py](../../../backend/scripts/build_region_directional_summary.py)
  — external_geo_feature.csv + 읍면동 anchor → 거리/bearing(atan2(dx,dy))/8방위/버킷 influence 감쇠/
  signal=오행벡터×influence×importance/방위별 합산 → compiled 요약. **순수 파이썬(EPSG:5179 평면,
  pyproj 불필요), 그리드 prefilter**로 5,065×N 가속. 외부 feature 부재 시 graceful(요약 미생성·스텁).
- **소비**: `DirectionalFeatureAdapter`가 요약 조회(없으면 available=False), 오케스트레이터 payload에
  주변 지형 하이라이트("북 1.8km 산")를 덧붙인다. 방위 요약은 지역 고정(주변 지형)이라 사전계산
  대상 — §4-4가 금지하는 '사용자 기준 이동 방위 저장'과 다르다(별도 summary).
- **준수**: 산=土(산림 시 木 보조)·하천/해안 다중 anchor(대표점 1개 축약 금지)·feature 없으면 추정
  금지(available=False, 감점 없음)·원본 SHP runtime 미의존(좌표 index만).

### 데이터 활성화 runbook(#1 수급 → #3 실활성, 2026-06-26)

엔진 **소비 코드는 전부 완성·검증**됐다(아래 핸드오프 파일만 드롭하면 즉시 활성). 원본 SHP→핸드오프
변환은 상류 데이터 prep(geopandas/pyproj 필요)이며, 정부 데이터는 로그인/신청 수동 다운로드다(자동화 불가).

| 핸드오프 파일(gitignore) | 산출 주체 | 소비 빌드 → 활성 레이어 |
|---|---|---|
| `doc/gis/region_geo_features.jsonl` (읍면동 집계: forest/water/mountain ratio 등 §3-C) | 토지피복·임상도 overlay(상류) | `build_region_profiles.py [units] [compiled] [geo]` → **physical_geography·landcover_hydro_forest**(프로필 벡터) |
| `doc/gis/external_geo_features.csv` (대표 좌표 점: 산/하천 anchor/해안/항만/산림 §6) | doc/gis_region 툴킷 01~03(POI/하천/해안 SHP) | `build_region_directional_summary.py` → **region_directional_summary**(방위별 주변 지형) |

활성 순서(사용자 수급 우선순위): ①POI+하천+해안 → external_geo_features.csv → 방향성 풍수.
②토지피복+임상도 overlay → region_geo_features.jsonl → physical/landcover. ③DEM → 풍수 형국
(FengshuiFormAdapter, 별도 알고리즘 — 미구현). 소비 경로는 합성 데이터로 회귀 테스트 고정
(test_region_geo_layer·test_region_directional). 핸드오프 미공급 시 전 빌드 graceful(P0~P4-A 산출 불변).

## 11. 설계 원칙(피해야 할 것)

1. 지명 한자만으로 오행 단정 금지 — 실제 지형과 다를 수 있다.
2. 방위 오행을 지역 고유 오행으로 저장 금지 — 사용자 위치에 따라 바뀐다.
3. 단일 오행으로만 추천 금지 — 현실 지역은 대부분 복합 오행(벡터로 저장).

## 12. 기존 자산 처리(흡수·승격, 사용자 확정)

- [region_elements.json](../../../backend/dictionaries/region_elements.json)(시군구 230, 한자 오행)
  → 새 엔진의 **한자 레이어(15%)** 로 흡수.
- [region_direction.py](../../../backend/packages/saju_engines/saju_engines/region_direction.py)
  → **방위 레이어(10%)** 로 내부 재사용.
- `relocation.py`의 `region_fit()` → 새 매칭 함수로 승격하되 기존 시그니처 호환 래퍼 유지.

## 13. Graph RAG 적용 범위(evidence 경로만, 사용자 확정)

[graph_builder.py](../../../backend/packages/saju_engines/saju_engines/graph_builder.py)에 노드
`region`·`region_layer_signal`, 엣지 `region→signal→element→{yongsin/huisin/gisin/gusin}`를 추가.
**점수 계산엔 미관여**, 근거 경로(evidence path) 직렬화 전용(P4).
