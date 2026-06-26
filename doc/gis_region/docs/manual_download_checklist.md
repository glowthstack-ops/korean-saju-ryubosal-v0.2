# 외부 지형 데이터 수동 수급 체크리스트

## 1. 먼저 받을 데이터

- 국토지리정보원 국가관심지점정보 POI: 산/봉우리/고개/항구 후보
- VWorld 또는 국토지리정보원 하천중심선/실폭하천: 하천 anchor 후보
- 국립해양조사원 해안선: 해안 anchor 후보

## 2. 두 번째로 받을 데이터

- 산림청 임상도: 산림 patch와 forest ratio
- 환경공간정보서비스 토지피복지도: 산림/수역/습지/시가화 보조

## 3. P4/P5 확장용

- 국토지리정보원 DEM: 배산임수, 분지, 경사, 고도차
- WAMIS 수자원단위지도: 유역 맥락, 행정구역 편입률

## 4. 저장 규칙

```
data/raw/poi/
data/raw/river/
data/raw/coast/
data/raw/forest/
data/raw/landcover/
data/raw/dem/
```

## 5. 수급 후 반드시 기록할 메타데이터

- source_name
- provider
- download_url
- downloaded_at
- source_date 또는 수정일
- license/이용허락범위
- 원본 좌표계
- 원본 파일명
- 변환 스크립트 버전

## 6. 엔진 반영 금지 사항

- 원본 polygon/line 전체를 서비스 엔진에 직접 적재하지 않는다.
- 하천/해안은 단일 centroid로 축약하지 않는다.
- 산은 무조건 木으로 분류하지 않는다.
- 출처가 불분명한 좌표는 confidence를 0.3 이하로 둔다.
