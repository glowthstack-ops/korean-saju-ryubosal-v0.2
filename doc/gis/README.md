# Region Spatial Engine P0 (20230729)

이 패키지는 지역 오행 판정을 위한 **계산용 경량 공간 데이터**입니다. 지도 시각화용 경계 GeoJSON/GeoPackage가 아니라, 엔진이 바로 읽을 수 있는 행정구역 중심점·대표점·bbox·방위 probe 좌표를 제공합니다.

## 포함 파일

- `region_spatial_engine_p0_20230729.sqlite`
  - 엔진 권장 입력. `region_unit`, `emd_direction_probe`, `external_feature`, `region_feature_direction` 테이블 포함.
- `region_units_compact_20230729.csv`
  - 시도/시군구/읍면동 전체 5,332개 행정구역의 코드, 이름, 중심점, 대표점, bbox, 면적.
- `region_units_compact_20230729.jsonl`
  - 동일 데이터의 JSONL 버전.
- `emd_direction_probe_points_20230729.csv.gz`
  - 읍면동 5,065개 × 8방위 × 4거리(1/3/5/10km) = 162,080개 probe 좌표.
- `region_spatial_engine_schema.sql`
  - 백엔드 DB 이식용 스키마.
- `region_spatial_engine_metadata_20230729.json`
  - 생성 메타데이터와 한계.

## 핵심 사용법

1. `region_unit`에서 사용자 후보 지역의 `anchor_x_5179`, `anchor_y_5179`를 읽습니다.
2. 산/하천/호수/해안/DEM 같은 외부 feature 데이터를 `external_feature`에 넣습니다.
3. 지역 anchor → feature 좌표의 거리와 bearing을 계산해 `region_feature_direction`에 저장합니다.
4. 산은 土/木, 하천은 水, 해안은 水, 공업·도로·철도는 金, 남향·개활·상업 열기는 火 신호로 변환합니다.

## 현재 한계

업로드된 원천 파일은 행정구역 경계뿐입니다. 산, 하천, 호수, 해안, 산림, 고도 데이터가 포함되어 있지 않아 이번 P0에서는 “어느 방향에 실제 산/하천이 있다”는 값까지 채울 수 없습니다. 대신 해당 데이터를 결합하기 위한 좌표 anchor와 방위 probe 구조를 생성했습니다.

## 좌표계

원본에 `.prj`가 없어 CRS가 명시되어 있지 않았습니다. 좌표 범위상 `EPSG:5179`로 부여했고, WGS84 lon/lat도 함께 제공합니다.
