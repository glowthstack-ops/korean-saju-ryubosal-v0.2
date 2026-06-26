# 실행 런북

## 1. 최소 P4-Data 수급

1. POI: 산/봉우리/고개/항구 후보를 받는다.
2. 하천: 하천중심선 또는 실폭하천을 받는다.
3. 해안선: 해안선 SHP를 받는다.

이 3개만 있으면 지역 중심 기준 “어느 방향에 土/水/金 신호가 있는가” 1차 판정이 가능하다.

## 2. 변환 순서

```bash
python scripts/01_import_point_poi.py --input data/raw/poi/ngii_poi.xlsx --output work/poi.sqlite
python scripts/02_import_line_anchors.py --input data/raw/river/river.shp --feature-type river_anchor --interval-m 1000 --output work/river.sqlite
python scripts/02_import_line_anchors.py --input data/raw/coast/coast.shp --feature-type coast_anchor --interval-m 1000 --output work/coast.sqlite
python scripts/06_merge_feature_sqlite.py --inputs work/poi.sqlite work/river.sqlite work/coast.sqlite --output work/external_geo_feature.sqlite
python scripts/04_build_region_feature_direction.py --region-db region_spatial_engine_p0_20230729.sqlite --features-db work/external_geo_feature.sqlite --output work/region_feature_direction.sqlite
python scripts/05_build_directional_summary.py --direction-db work/region_feature_direction.sqlite --output work/region_directional_element_summary.sqlite
```

## 3. 품질 점검 SQL

```sql
SELECT feature_type, COUNT(*) FROM external_geo_feature GROUP BY feature_type;
SELECT radius_bucket, COUNT(*) FROM region_feature_direction GROUP BY radius_bucket;
SELECT direction_code, COUNT(*) FROM region_directional_element_summary GROUP BY direction_code;
```

## 4. 반영 기준

- 읍면동의 8방위 중 최소 1개 방향에 feature가 있으면 P4 direction evidence 생성 가능
- 하천/해안 데이터만 있어도 水 판정은 가능
- 산 POI가 부족하면 산림/DEM/등고선을 보조로 추가
