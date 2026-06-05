# 류보살 v2 — 만세력 엔진 (Saju v2 Manse Engine)

LLM에 의존하지 않는 **결정론적 만세력 계산 엔진**. v1의 리팩터링이 아니라 별도 도메인·
별도 API·별도 계산 엔진으로 구축하는 Greenfield 시스템이다. 구현 기준은
[`doc/v2_1/`](doc/) 의 v2.1 명세이며, 권장 읽기 순서는
[`saju_v2_engine_document_index.md`](doc/v2_1/saju_v2_engine_document_index.md) 를 따른다.

## 현재 범위 (Phase 0–6, 백엔드 엔진)

- ✅ 입력 정규화 (양력 / 음력·윤달 → `korean_lunar_calendar`)
- ✅ 시간 보정: IANA timezone·역사적 DST, 경도 보정, 균시차(NOAA), 진태양시 + **시주 변화 표시**
- ✅ 절기 기준 월주, 년/월/일/시주 + 지장간·십성·12운성·공망·납음·궁성
- ✅ 세력분석: 오행/십성 분포(raw/hidden/effective), 통근·득령/득지/득세, **신강약 9단계**(신왕≠신강 게이트)
- ✅ 구조작용: 합충형파해·병존·간여지동·합화 판정·안정도·structure_modifier, **격국**(성/중성/패)
- ✅ **용신 후보**(특수격 검사 → 모델별 후보 → candidate/probable, 검증 전 확정 금지)
- ✅ **대운/세운/월운/일운** (reference_date 옵션) + 용신 관계
- ✅ **용신 검증 루프**: 질문 5종 생성 + 피드백 점수화 → calibrated/probable/uncertain
- ✅ **전체 신살** (12신살·귀인·흉신 등, 강도·궁성·십성 context, 용신 결정 미사용)
- ✅ API: `POST /api/v2/manse/calculate`, `POST /api/v2/manse/calibration/feedback`
- ✅ 골든 회귀(지역/DST/자시경계/윤달/공망), 결정론·버전·trace 고정

프론트엔드(`apps/web`)는 초기 결정상 보류(백엔드 엔진 우선). `ManseV2Result`의 10개 레이어
(time_correction…traditional_extras)가 모두 산출된다.

## 구조

```
packages/shared_types   # enums, 상수 테이블(단일 출처), pydantic 스키마
packages/manse_core     # calendar · time_correction · pillars 계산 엔진
apps/api                # FastAPI: routers / services / location
data/solar_terms        # 사전 생성된 절기 테이블 (재현성)
data/location_db        # 시드 좌표/타임존
data/test_fixtures      # 회귀 fixture
scripts                 # generate_solar_terms.py
tests                   # unit / integration / regression
```

## 실행

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python scripts/generate_solar_terms.py          # 절기 테이블 생성 (1회)
pytest                                           # 단위·회귀·통합 테스트
uvicorn saju_api.main:app --reload               # API 기동
```

예시 요청:

```bash
curl -X POST localhost:8000/api/v2/manse/calculate -H 'content-type: application/json' \
  -d '{"calendar_type":"solar","birth_date":"1980-11-22","birth_time":"09:08",
       "birth_place_name":"서울","gender":"male"}'
```

## 검증 앵커 (Golden Fixture)

`1980-11-22 09:08 서울 남성` → 년 **庚申** · 월 **丁亥** · 일 **己亥** ·
시(일반시) **己巳** → 진태양시 적용 시 **戊辰** (시주 변경 표시), 공망 辰巳, 순행대운.

## 설계 원칙 (엔진 절대 원칙)

1. LLM은 사주를 계산하지 않는다 — 모든 계산은 결정론적 엔진에서.
2. 동일 입력 → 항상 동일 JSON. 모든 결과에 `metadata`(engine/ruleset/tzdata/solar_terms
   버전) 와 `trace` 를 남긴다.
3. 월주는 음력 월이 아니라 **절기 기준**.
4. 진태양시 적용 전후 시주 변화 여부를 반드시 표시한다.
5. 통근/득지, 오행/십성/신강약/용신은 분리된 레이어로 다룬다(후속 단계).
