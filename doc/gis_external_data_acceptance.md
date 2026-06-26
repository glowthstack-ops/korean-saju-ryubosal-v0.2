# 외부 지형 데이터 수용 계층 (P4-Data Acceptance Layer)

사람이 다운로드한 정부 GIS 원본이 **엔진 변환 가능 상태인지 변환 전에 자동 판정**하는 입구
검증 계층이다. 실제 변환·엔진 결과는 바꾸지 않는다. 목적: 데이터를 받았을 때 "엔진 문제"가
아니라 "데이터 입구 문제"로 빌드가 깨지는 것을 사전에 잡는다.

## 구성

- 코어: [backend/packages/saju_engines/saju_engines/geo_acceptance.py](../backend/packages/saju_engines/saju_engines/geo_acceptance.py)
- CLI:
  - `python backend/scripts/inspect_geo_source.py <파일> [--json]` — 원본 1개 판정
  - `python backend/scripts/validate_external_geo_sources.py [경로...]` — 묶음 게이트(fail→종료 1)
  - `python backend/scripts/build_external_geo_acceptance_report.py [경로...] [--out DIR]`
    — `external_geo_acceptance_report.{json,md}` 산출
- 검증 사전: `region/region_geo_feature_elements.json`의 feature_type(element rule 매핑 가능 판정)

## 검증 항목(13)

1. 파일 존재 2. 인코딩(utf-8/utf-8-sig/cp949) 3. 좌표 컬럼/geometry 존재 4. CRS 존재
5. EPSG:5179/WGS84 변환 가능 6. 필수 컬럼 매핑(좌표=필수, 이름/타입=권장) 7. feature_type 추론
8. 좌표가 한반도 범위 9. geometry empty/invalid 10. row count>0 11. line anchor 생성 가능
12. polygon representative point 생성 가능 13. element rule 매핑 가능

## 판정 규칙

- **fail**: 변환 금지(파일 없음·좌표 없음·행 0·파싱 실패·미지원 포맷).
- **warning**: 변환 가능하나 확인 필요(CRS 미상→좌표 범위 추정·이름/타입 컬럼 미검출·line/polygon
  → anchor/representative point 변환 필요·미정의 feature_type→unknown·범위 이탈).
- **pass**: 그대로 변환 진행 가능.

원칙: CRS 없으면 좌표 범위로 추정하되 warning. feature_type 확정 불가는 unknown(warning, fail 아님).
geometry 없이 lon/lat만 있으면 point source로 처리 가능.

## 포맷별 검증 수준

| 포맷 | 검증 | 비고 |
|---|---|---|
| csv/tsv/jsonl | 전수(순수 파이썬) | point source. 좌표·컬럼·범위·타입 |
| geojson | 전수(순수 파이썬) | geometry type·CRS·empty·count |
| shp/gpkg | geopandas 있으면 전수, 없으면 메타(.prj)만 | 미설치 시 "geopandas 설치 또는 geojson 변환" 안내(감점 아님) |
| xlsx | 미지원 | csv 변환 후 재검증 |

## 권장 워크플로(데이터 수급 후)

```bash
# 1) 다운로드 원본을 doc/gis 에 배치(또는 경로 지정)
# 2) 게이트 검증 — fail이면 변환 중단
python backend/scripts/validate_external_geo_sources.py doc/gis/raw/
# 3) 리포트 산출(검토·이력)
python backend/scripts/build_external_geo_acceptance_report.py doc/gis/raw/
# 4) pass/warning이면 상류 변환(doc/gis_region 툴킷)으로 external_geo_features.csv /
#    region_geo_features.jsonl 생성 후 백엔드 빌드:
python backend/scripts/build_region_directional_summary.py   # 방향성(산/하천/해안)
python backend/scripts/build_region_profiles.py              # physical/landcover(토지피복/임상도)
```

수급 우선순위(docs/12): ①POI+하천+해안 ②토지피복+임상도 ③DEM(풍수). 각 단계는 독립 활성.
