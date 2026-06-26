# 지역 오행 엔진 외부 지형 데이터 수급·변환 패키지 v1

이 패키지는 원본 GIS 도형을 서비스 엔진에 그대로 넣지 않고, 지역 오행 판정에 필요한 대표 좌표 feature index로 압축하기 위한 실행/운영 템플릿입니다.

## 목표

- 행정구역 중심점 기준으로 어느 방향에 산·하천·호수·해안·산림이 있는지 계산
- 외부 원본 데이터는 수동/자동으로 수급하되, 엔진에는 경량 좌표 테이블만 저장
- 기존 `region_spatial_engine_p0_20230729.sqlite`의 `region_unit`과 결합 가능하도록 설계

## 최종 산출물

1. `external_geo_feature`
   - 산, 하천 anchor, 호수 중심점, 해안 anchor, 항구, 산림 patch 등의 대표 좌표
2. `region_feature_direction`
   - 읍면동 기준점과 feature 간 거리·방위·오행 신호
3. `region_directional_element_summary`
   - 읍면동 × 8방위 요약 오행 점수

## 수급 방식

- 자동 다운로드/API 가능: 일부 data.go.kr 파일, WFS/WMS, 공개 URL 파일
- 반자동/수동 다운로드 필요: 국토정보플랫폼 대용량 다운로드, 산림공간정보서비스 신청 다운로드, 환경공간정보서비스 로그인 자료신청
- 엔진 입력은 원본이 아니라 변환 결과 SQLite/CSV.GZ

## 기본 실행 흐름

```bash
# 1. 환경 점검
python scripts/00_check_environment.py

# 2. 수동 다운로드 파일을 data/raw 아래에 배치
mkdir -p data/raw/poi data/raw/river data/raw/coast data/raw/forest data/raw/dem

# 3. 점형 POI 변환: 산·고개·항구 등
python scripts/01_import_point_poi.py \
  --input data/raw/poi/ngii_poi.xlsx \
  --output work/external_geo_feature.poi.sqlite

# 4. 선형 데이터 anchor 변환: 하천/해안
python scripts/02_import_line_anchors.py \
  --input data/raw/river/river_centerline.shp \
  --feature-type river_anchor \
  --name-field RIV_NAM \
  --interval-m 1000 \
  --output work/external_geo_feature.river.sqlite

# 5. 면형 데이터 변환: 호수/습지/산림 patch
python scripts/03_import_polygon_anchors.py \
  --input data/raw/forest/forest_stand.shp \
  --feature-type forest_patch \
  --min-area-m2 50000 \
  --output work/external_geo_feature.forest.sqlite

# 6. region 기준 거리·방위 계산
python scripts/04_build_region_feature_direction.py \
  --region-db /path/to/region_spatial_engine_p0_20230729.sqlite \
  --features-db work/external_geo_feature.merged.sqlite \
  --output work/region_feature_direction.sqlite

# 7. 읍면동 × 8방위 요약 생성
python scripts/05_build_directional_summary.py \
  --direction-db work/region_feature_direction.sqlite \
  --output work/region_directional_element_summary.sqlite
```

## 권장 반경

- near_1km: 핵심 생활권
- mid_3km: 가까운 지형 영향
- wide_5km: 일반 지역 오행 영향
- outer_10km: 넓은 지형 배경

## 주의

- 하천·해안은 대표점 1개로 축약하지 말고 anchor point로 분할합니다.
- 산은 木이 아니라 土 중심으로 보고, 산림이 확인될 때 木 보조를 줍니다.
- 외부 데이터가 없으면 추정하지 않고 missing layer로 처리합니다.
- 원본 데이터 라이선스와 출처 표기는 별도 보관해야 합니다.
