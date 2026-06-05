# 류보살 v2 (Ryubosal v2)

LLM에 의존하지 않는 **결정론적 만세력 엔진**을 기반으로 한 사주 서비스 v2. v1 리팩터링이
아니라 별도 도메인·별도 계산 엔진으로 구축하는 Greenfield 시스템이다. 구현 기준은
[`doc/v2_1/`](doc/) 의 v2.1 명세이며, 권장 순서는
[`saju_v2_engine_document_index.md`](doc/v2_1/saju_v2_engine_document_index.md) 를 따른다.
작업 이력은 [`doc/WORKLOG.md`](doc/WORKLOG.md) 에 단계별로 기록한다.

## 서비스 구성 (모노레포)

```
saju_v2/
  backend/      # ✅ 결정론적 만세력 계산 엔진 + API (Python/FastAPI)
  frontend/     # ✅ 서비스 #1: 만세력 + 간지달력 페이지뷰 웹 (Next.js/TS)
  doc/          # v2.1 명세 번들 + 작업 이력 (전체 서비스 공통 기준)
```

> 서비스 #1 = 페이지뷰/광고 수익형(만세력·대운/세운/월운·간지달력)이 구현되어 있다.
> 서비스 #2(대화형 LLM 사주), 어드민 등은 후속 마일스톤이다.

## 프론트엔드 (서비스 #1)

Next.js App Router. 만세력은 클라이언트 렌더(개인정보는 IndexedDB에 Web Crypto로 암호화 저장,
서버 미저장), 간지달력은 SSR(SEO). 계산은 모두 백엔드 API 호출.

```bash
cd frontend
npm install
NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev   # 백엔드와 함께 기동
npm test && npm run build
```

## 백엔드

만세력 계산 엔진(시간보정·원국·세력분석·구조작용·격국·용신·운·신살·검증 루프)과
FastAPI 서버. 상세는 [`backend/README.md`](backend/README.md) 참고.

```bash
cd backend
pip install -e ".[dev]"
python scripts/generate_solar_terms.py     # 절기 테이블 생성 (1회)
pytest                                      # 단위·회귀·통합 테스트
uvicorn saju_api.main:app --reload         # API 기동
```

## 핵심 원칙

1. LLM은 사주를 계산하지 않는다 — 모든 계산은 결정론적 엔진에서.
2. 동일 입력 → 항상 동일 JSON. 결과에 버전·trace 기록.
3. 월주는 절기 기준, 진태양시 시주 변화 표시, 용신은 후보→검증→확정 흐름.
