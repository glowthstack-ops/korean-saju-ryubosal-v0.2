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
**상세 설계는 §14**(풍수 형국·방위 역할 — 사신사·좌향·팔택·비보, 감수 대기).

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
| P4-Data(Tier B) | 무로그인 지형 연결(OSM 실폴리곤+토지피복/수계 + NE 해/육 + Copernicus DEM), 면적비·고도·경사 산출 파이프라인(scripts/build_geo_features.py) | 유 | 연결완료·활성대기(가중 감수) |
| P5-1 | 풍수 형국·방위 역할 스캐폴딩(§14) — TerrainRole/FormEffect/FengshuiFormProfile/사신사 sector 함수 + 결과 블록 graceful, 무보정 | 무 | 설계 §14 |
| P5-2 | 이산 feature 추출(OSM peak/waterway/road/rail→external_feature→region_feature_direction) | 유 | 설계 §14 |
| P5-3 | 형국 채점·도로/팔택 가중 활성(전문가 감수 후) + golden 재생성 | 유 | 감수 대기 |

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

### P4-SearchSeed — 검색 기반 부트스트랩(2026-06-26, 공식 GIS 전 빠른 경로)

공식 GIS 원천 수급(수동·로그인) 전, 시군구명 + 지형 키워드 검색 → 좌표 API로 external_geo_feature를
빠르게 생성하는 부트스트랩. **읍면동 전수 검색 금지** — 시군구 250 × 키워드 9 = 2,250건만, 읍면동은
추천 후보/사용자 질의 시 on-demand 확장. 검색 데이터는 오탐이 있어 카테고리 거름 + 낮은 confidence
(카테고리 0.70/이름 0.55/검색어 0.45, 중복+0.10) + review_status로 검수 전 신호임을 강제(절대원칙 5).

- 코어 [search_seed.py](../../../backend/packages/saju_engines/saju_engines/search_seed.py): 키워드,
  classify_feature_type(카테고리>이름>검색어, 비지형 reject), 오행 매핑, 등거리 투영(pyproj 불필요),
  300m 중복 병합. 방위 집계는 공유 코어 [region_directional.py](../../../backend/packages/saju_engines/saju_engines/region_directional.py)
  (build_directional_summaries — GIS·검색 공용)로 추출.
- 스크립트 5종: build_search_seed_queries(쿼리) → fetch_search_seed_features(Kakao Local provider,
  키 환경변수 KAKAO_REST_API_KEY·없으면 graceful·provider 주입 테스트) → classify → dedupe →
  build_search_seed_direction_summary(lon/lat 등거리 투영 → 방위 요약 json/csv, provisional).
- 산출은 doc/gis/search_seed/(gitignore). 검색 기반은 provisional이라 compiled 운영본 자동 덮어쓰기
  금지 — 검수 후 수동 승격(공식 GIS 확보 시 교체). 하천/해안은 대표 feature로만(공식 anchor로 교체).
- 활성: KAKAO 키 설정 → 5스크립트 순차 실행 → region_directional_summary_search_seed.json →
  (검수 후) compiled로 승격 → DirectionalFeatureAdapter 활성.

### P4-Data Acceptance Layer + emd 계산/sig surface + 무데이터 가드(2026-06-26)

데이터 받기 전 디버깅 비용을 줄이는 마무리 작업(사용자 확정).

- **수용 계층**(입구 검증): [geo_acceptance.py](../../../backend/packages/saju_engines/saju_engines/geo_acceptance.py)
  + CLI 3종(inspect_geo_source·validate_external_geo_sources·build_external_geo_acceptance_report) +
  [doc/gis_external_data_acceptance.md](../../gis_external_data_acceptance.md). 다운로드 원본이 변환
  가능 상태인지 13항목 판정(좌표·CRS·인코딩·feature_type·한반도 범위·geometry 등). csv/jsonl/geojson은
  순수 파이썬 전수, shp/gpkg는 geopandas 있으면 전수·없으면 메타 안내. fail이면 변환 금지(게이트).
- **emd 계산 / sig surface**(요구사항 1): 추천 계산 단위는 읍면동(emd) 유지, 표시만 시군구 grouping.
  recommend_payload가 computed_level=eup_myeon_dong / surface_level=sig / surface[].top_emd_candidates
  제공. _select_candidates 전국 폴백을 '요청 해상도' 기준으로 수정(emd 요청 시 읍면동 후보 유지).
  chat은 emd 계산→시군구로 묶어 '세부 동' 동반 표시.
- **무데이터 문구 가드**(요구사항 2): payload.terrain_data_available + REGION_REASONING_DIRECTIVE가
  외부 지형 미연결 시 '북쪽에 산/남쪽에 하천/배산임수/풍수 완성' 류 실제 지형 주장을 금지. 권장
  문구는 '지명·한자·음운·방위·기초 스키마 기반 1차 추정'.

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

---

## 14. 풍수 형국·방위 역할 레이어 (V2 확장 — 2026-06-26 설계검토 반영)

> 데굴님 외부 자료(산·물·도로·좌향·양택 길흉 결합 체계) 검토를 본 엔진과 정합하게 정리한 **설계
> 초안**이다. 채점 가중은 **명리 표준 규격 없는 자체 기준(reviewed:false)** 이므로 전문가 감수
> 전 활성화 금지(절대원칙 5). 데이터 연결만으로는 부족함을 P4-Data에서 확인했다 — 가중 보정이
> 별도 감수 단계다. 본 절은 §4-5(풍수 형국 V2)·§4-4(방위)의 상세 확장이다.

### 14-0. 분리 계약 (핵심 — 점수 미혼합)

판정을 4계층으로 분리하고 **점수를 섞지 않는다**. 각 계층은 독립 evidence로 산출·저장·게이트한다.

```
A. Region Element Profile  → 이 지역이 木火土金水 중 무엇이 강한가 (고정, §4·§5)
B. Fengshui Form Profile   → 산·물·도로·개활의 배치 품질이 좋은가/나쁜가 (14-4)
C. Personal Direction Match→ 사용자 기준 이 방향/좌향이 맞는가 (용신 혼합=14, 팔택 optional=14-6)
D. Recommendation Result   → A+B+C 결합 + 비보 제안 (가중 결합, 14-9)
```

근거: 水가 강한 지역이라도 사용자에게 水가 기신이면 A는 감점, 그러나 물이 감싸 흐르면 B는 가산
일 수 있다 — A(오행 길흉)와 B(형국 품질)는 **다른 축**이라 한 점수로 합치면 정보가 소실된다.
기존 `RegionRecommendationExplanation`(element_vector·fit_summary·evidence·missing_layers)에
`fengshui_form`·`personal_direction`·`remedy` 블록을 **추가**해 분리 유지한다(14-9).

### 14-1. terrain_role / form_effect enum (feature 의미 세분)

기존 `external_feature.feature_type`(mountain|river|lake|coast|forest…)에 **역할(role)** 을
덧붙인다. feature_type=무엇인가, terrain_role=어떻게 작용하는가.

```
TerrainRole = mountain_support | forest_support | river_flow | lake_water | coast_water
            | valley_water | road_rush | rail_metal | open_field | urban_heat | industrial_metal
FormEffect  = back_support | front_open | left_dragon | right_tiger | water_embrace
            | road_rush | water_escape | excessive_pressure | isolated_flat | neutral
```

오행 매핑은 §4-1·`region_geo_signal_rules`를 재사용(이미 구현됨): **산=土 기본, 산림 확인 시 木
보조**(山 context_rule default 土 / alt 木), 浦=水(harbor면 金 보조). 도로·철도는 14-5.

### 14-2. 방향성 feature 모델 + 좌향 두 모드

기존 sqlite `region_feature_direction`(region_code·feature_id·direction_code·bearing_deg·
distance_m·within_region_yn·element_signal·signal_weight)이 이 모델의 저장소다 — **채우기만
대기**. anchor 기준 8방위 feature를 읽어 `top_features`(name·type·distance·element_signal·
terrain_role)로 집계한다([region_directional.py](../../../backend/packages/saju_engines/saju_engines/region_directional.py) 확장).

- **모드 A(좌향 없음)** — 지역 자체 판단: 북/동/남/서/간방별 산·물·도로 분포만. *현행 8방위 집계.*
- **모드 B(좌향 있음)** — 집·아파트·이사지: `facing_bearing`로 전후좌우 sector 변환. **신규.**
  ```
  front = facing_bearing ; back = +180° ; left = −90° ; right = +90°
  ```
  → "북쪽 산이 항상 현무" 오류 방지(남향=북산 현무, 동향=서산 현무). DirectionalSectorProfile.

### 14-3. 사신사 구조 (모드 B 위)

```
현무(back)  = 뒤 산·구릉 → 안정·보호 → back_mountain_score
주작(front) = 앞 개활·물·도로·시야 → front_water_score + open_front_score
청룡(left)  = 좌 산세·녹지 흐름 → left_dragon_score
백호(right) = 우 산세(과하지 않게) → right_tiger_score
```

### 14-4. FengshuiFormProfile 스키마 + 채점 (B 계층)

```sql
CREATE TABLE region_fengshui_form_profile (
  region_code TEXT PRIMARY KEY,
  back_mountain_score REAL, front_water_score REAL, left_dragon_score REAL,
  right_tiger_score REAL, open_front_score REAL,
  road_rush_penalty REAL, water_escape_penalty REAL,
  excessive_pressure_penalty REAL, isolated_flat_penalty REAL,
  form_quality_score REAL,            -- 가산 − 페널티 종합(B 단일 품질)
  confidence REAL DEFAULT 0.5, evidence_json TEXT
);
```

`form_quality_score`는 **B 계층 단독** 품질이며 A(오행 벡터)에 더하지 않는다. 가중·임계는 감수 대상.

### 14-5. 물길·도로/철도 특수 처리

- **하천**: 가까운 물=水. 유향 미상이면 `flow_known=false`·`form_effect=water_signal_only`로
  水 신호만. P5에서 line geometry 확보 시 곡류(감싸=가산)/직류(直沖=충)/수구(빠짐=불안정) 판정.
- **도로·철도(현대 물길, 성질 다름)**: 곡선·접근성→火/金 보조, 직선 정면=`road_rush_penalty`,
  고속·철도 인접=金 강+소음 살기. feature_subtype: major_road_anchor·road_intersection·
  railway_anchor·station_poi·bridge_poi·tunnel_poi. 매핑 예(감수 전 초안):
  ```
  major_road_anchor {火0.45 金0.35 土0.20} | road_intersection {火0.60 金0.30 土0.10}
  railway_anchor    {金0.70 火0.20 土0.10} | station_poi       {金0.45 火0.35 土0.20}
  ```
  → `transport_access`/`modern_activity` 레이어(region_layer_weights에 이미 계획됨)로 귀속.

### 14-6. 팔택/본명궁 — optional 개인 방위 (C 계층, 보조)

`personal_direction_engine.py`(신규, optional). 입력 birth_year·gender·direction_model=
"paltaek_optional" → 생기/천의/… 길방·절명/… 흉방. **가드레일**: 사주 용희신 기반 추천과 **다른
체계**라 절대 섞지 않고 **항상 보조**(판정 우선순위 원칙: 길흉=용신/기신이 1차). 기본 비활성,
사용자 선택 시만. [region_direction.py](../../../backend/packages/saju_engines/saju_engines/region_direction.py)가
이미 "후천팔괘=좌향용 별개 체계"로 분리 명시 — 그 경계를 따른다.

### 14-7. 비보/보완 제안 (D 계층 부가)

지역이 완벽하지 않아도 "어떻게 보완하나"를 안내(서비스 가치 큼). 단정 금지(절대원칙 3).

```
RemedySuggestion = { issue, recommendation, element_to_add[], element_to_reduce[] }
```

오행 보완(생활권 선택)·기신 회피 표:
```
필요 木→숲·공원·산록 / 火→남향·채광·상권 / 土→구릉·평지·학교관공서 주변
     金→역세권·도로망·계획도시 / 水→강·호수·바다·유동인구
기신 木→숲과다·습목 / 火→과상권·열섬 / 土→답답한 분지·산압 / 金→공업·철도대로변 / 水→강변저지·습지
```

### 14-8. SearchSeed CSV 컬럼 확장

기존 컬럼(feature_id…element_water,confidence,review_status,raw_json)에 추가:
`feature_subtype, terrain_role, form_effect, is_supportive, is_penalty`.
(P4-SearchSeed 산출물은 reviewed:false — §10 SearchSeed 절차 동일.)

### 14-9. 추천 결과 출력 구조 (분리 유지)

`RegionRecommendationExplanation`에 블록 추가(계산은 엔진, LLM엔 결과만 — 절대원칙 1·9):
```
region_element  : {dominant_elements, summary}            # A
fengshui_form   : {summary, positive[], caution[]}        # B (미공급 시 caution=["미확인"])
personal_match  : {summary}                               # C (팔택 활성 시만)
remedy          : RemedySuggestion[]                      # D
```
미공급 레이어는 감점 아닌 표시(missing_layers, 절대원칙 11).

### 14-10. 구현 순서 (P5) + 감수 게이트

```
P5-1 스캐폴딩(무보정·회귀 무영향): TerrainRole·FormEffect·FengshuiFormProfile·
     DirectionalSectorProfile·RemedySuggestion 타입 + 사신사 sector 변환 함수 +
     추천 결과 fengshui_form 블록(빈 값 graceful, 점수 0).
P5-2 이산 feature 추출: OSM natural=peak / waterway(line) / road(line) / railway →
     external_feature → region_feature_direction(bearing·distance·within·terrain_role).
     ※ P4-Data의 '면적 비율'과 별개 추출(점·선 feature·방위).
P5-3 채점·가중(전문가 감수 후 활성): form_quality·penalty·도로/철도 매핑·팔택 →
     region_layer_weights/region_geo_signal_rules 보정 → golden 픽스처 재생성.
```

### 14-11. 설계 가드레일 (피해야 할 것 — §11 보강)

```
4. A(오행)·B(형국)·C(방위)·팔택 점수를 한 숫자로 합치지 말 것 — 분리 evidence 유지.
5. 팔택/본명궁이 용희신 길흉을 덮지 말 것 — 항상 보조·optional.
6. 방위 역할(현무 등)은 좌향(facing) 입력에서 계산 — region_profile에 고정 저장 금지.
7. 형국·도로·팔택 가중은 reviewed:false — 전문가 감수 전 활성/출시 금지(절대원칙 5).
```

### 14-12. P5-3 활성화 보정 기준 (데굴님 감수 확정 2026-06-26)

> reviewed:false 가중을 푸는 **권위 결정**. 핵심: 정확한 지형 데이터를 *어디에* 반영하느냐 —
> 방향성 지형을 region profile에 직접 합산하지 말고, 형국 레이어로 분리하고, 추천 점수엔 작은
> 보정값으로만. 팔택 기본 OFF.

**명칭 분리(혼동 금지)**
```
relative_direction   = 사용자 현재 위치 기준 후보 지역의 방향(기존, region_element_engine 그대로)
directional_terrain  = 후보 지역 '내부' 기준 산·물·숲·해안의 8방위 분포(P5-2 산출 — NEW)
fengshui_form        = directional_terrain을 풍수 형국으로 해석한 결과(FengshuiFormProfile)
```
P5-2 directional 요약을 relative_direction이라 부르지 않는다(§14-11 가드 보강).

**활성화 순서(고정)**
```
1) directional_terrain evidence 노출(shadow — recommendation score 영향 0, LLM 설명 근거만)
2) nearby_discrete_geo_layer 보수 반영(지역 오행 보강, max 가중 0.18)
3) form_quality 별도 계산(FengshuiFormProfile, region_element_vector와 분리)
4) road_rush는 좌향(facing_bearing) 있을 때만
5) 팔택 기본 OFF
```

**지역 오행 레이어 우선순위**
```
면적비 GIS(region_geo_features forest/water/mountain) > 이산 방향성(P5-2) > 한자 > 음운
nearby_discrete_geo_layer 가중 cap 0.18 (P3 집계형 있으면 그쪽 우선)
```

**추천 점수 결합 + cap(첫 릴리즈 보수 → 검수 후 확장)**
```
final = base_match_score(용희기구신×지역오행, 주판정)
        + directional_terrain_bonus   첫 cap ±3  (확장 ±4)
        + form_quality_bonus          첫 cap ±5  (확장 ±8)
        − road_rail_penalty           첫 cap −4  (확장 −6)
        + paltaek_bonus               기본 0(OFF) (옵션 ON 시 ±5)
form_quality·directional은 base_match_score를 뒤집지 못한다(보정만).
```

**form_quality 산식(좌향 없음 — 지역 단위, 사신사 단정 금지)**
```
raw = 0.25*mountain_support + 0.20*water_access + 0.20*forest_support
      + 0.15*terrain_balance − 0.20*overwater_penalty − 0.15*isolation_penalty
adjusted = raw * confidence ; score_bonus = clamp(adjusted*8, −8, +8)  # 첫 릴리즈 ±5 cap
```
**form_quality 산식(좌향 있음 — 사신사 전후좌우, facing_bearing 입력 시만)**
```
raw = 0.30*back_mountain + 0.20*front_water_or_open + 0.15*left_dragon
      + 0.10*right_tiger_balance − 0.20*front_blocked − 0.20*road_rush − 0.15*overwater
form_quality_bonus cap ±10(확장)
```

**도로·철도(§14-5 확정)** — region element에 넣지 않음(use_as_region_element=false). 선형은 form
penalty(road_rush)로만 소비. node(역·교차로)만 modern_activity 보조(station_poi는 element 가능).
```
좌향 없음: 도로/철도 100m 이내 pressure_candidate, 300m 이내 minor — 기록만(판정 강제 금지)
좌향 있음: front sector ±22.5° 안 + 300m 이내 + bearing 일치 → road_rush_penalty
  major front 300m −0.04 / 100m −0.07 ; rail front 300m −0.06 / 100m −0.10 ; total cap −6
```

**팔택** — 타입·옵션만, 기본 OFF. 사용자 질문이 '길방위/잘 방향/집 방향'일 때만 ON. 설명은 사주
오행 기준과 분리("방위론 기준으로는 보조적으로…"), '동쪽=무조건 길방' 류 단정 금지. cap ±5.

**거리 감쇠 버킷 + feature별 영향 반경**
```
0~1km 1.00 / 1~3km 0.70 / 3~5km 0.45 / 5~10km 0.20 / 10km 초과 제외
mountain_peak 10km · coast_anchor 10km · lake_centroid 7km · river_anchor 5km · forest_patch 5km
```

**OSM/NE confidence(공식 GIS보다 낮게)**
```
mountain_peak 0.70 · coast_anchor 0.75 · river_anchor 0.65 · lake_centroid 0.65 · forest_patch 0.60
manual_verified +0.15 · official_gis +0.15~0.25
```

**golden 20+ 카테고리**: 산지형(청운효자·정릉·장전·대관령)·수변형(망원·잠실·미사·우동)·산수혼합
(청운효자·조안·신북·단양)·평야도시(역삼·동성로·반곡·요촌)·해안(우동·연안·주문진·애월). 기대:
산=木 단정 금지 / 수변·해안 무조건 길 금지 / 복합 단일오행 금지 / 도시형 火金은 modern layer.

**P5-3 금지사항(고정)**
```
1 directional_terrain을 relative_direction이라 부르지 말 것
2 산을 木으로 단정하지 말 것       3 하천/해안 있으면 무조건 길 금지
4 좌향 없이 사신사 길흉 강판정 금지  5 도로/철도를 무조건 오행 점수에 넣지 말 것
6 팔택을 기본 추천 점수에 섞지 말 것  7 form_quality가 base_match_score를 뒤집지 못하게
8 OSM/NE confidence를 공식 GIS보다 높게 두지 말 것
```

### 14-13. 전문가 ground truth 기반 레이어 가중 역보정 (2026-06-26)

전문가 감수 시군구 오행 217개를 ground truth로 삼아 base 레이어 가중을 측정·역보정했다(데굴님 지시 #3).
전문가 override를 끈 상태에서 각 레이어의 1순위 일치율:

```
한자 단독                         72.6% (156/215) — 최고. 명리 한자 의미가 전문가와 가장 부합
draft geo-ON(physical 0.45)       35.9%           — 지형 우위가 일치율을 절반 이하로 붕괴
per-signal: forest 66.4 / water 63.6 / urban 65.4 — 단일 지형 신호도 한자 baseline 미달
calibrated geo-ON(아래 base)      72.8%           — 한자 1차 + 지형 보조로 회복(neutral~소폭↑)
```

**해석**: 전문가 오행은 **지명 한자(명리) 기반**이라 지형 면적비(forest/water/mountain)와는 다른 축이다.
지형을 가중 1차로 두면(초안 physical_geography 0.45) 명리와 어긋나 일치율이 붕괴한다. 따라서:

- **base 재보정**: hanja_place_name 0.15→**0.45**(1차), physical_geography 0.45→**0.10**, landcover
  0.20→**0.15**, relative_direction 0.10→0.15, fengshui 0.07→0.10, phonetic 0.03→0.05. 지형은 명리
  한자를 보조하는 minor 레이어로 재배치 — geo 활성 시 일치율 36%→72.8% 회복.
- geo-OFF 프로필(현 운영)은 한자가 음운(cap 0.03) 위로 이미 지배해 변화 없음(golden 불변).
- discrete(P5-3B, EMD 0.18)는 EMD 단위라 SIG 전문가로 직접 검증 불가하나 0 dominant flip(neutral) 유지.
- **결론**: 전문가 수록 시군구는 권위 override(§14-12 통합)로 100% 정합. 미수록(통합시 자치구·EMD)은
  한자 1차+지형 보조의 보정 가중으로 전문가 경향에 최대한 근접. 지형 면적비를 명리 오행의 1차 근거로
  쓰지 않는다(검증된 원칙).
