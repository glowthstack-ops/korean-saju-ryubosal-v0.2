# Intent 유사도 보조 분류기 (Auxiliary Intent Classifier)

> 규칙 파서(query_parser)가 의도(domain)를 못 정한 경우에만 보조로 보강하는 임베딩 기반 분류기.
> rules-first · 보조 신호 전용 · 점수·간지·판정 미개입(절대원칙 1) · CPU·무API·torch-free 런타임.
> 2026-06-18 사용자 제안·측정·승인.

## 1. 배경 / 문제

규칙(키워드·정규식) 파서만으로는 "동일 의도, 다양한 표현"을 다 못 잡는다. 예: "주머니 사정
나아질까?"(재물), "혼삿길이 언제 열릴까"(결혼), "보금자리 옮기는 거"(이사)는 도메인 키워드가
없어 `domain=general`로 떨어지고, 그 결과 broad 안내("질문 범위가 넓어요")로 빠지거나 총운으로
흐른다. LLM 없이(절대원칙 9), 서버 CPU에서, API 비용 0으로 보조 신호를 더할 방법을 찾았다.

## 2. 측정 (동일 평가셋 40건 — 시드와 표현이 다른 보류 세트)

| 방식 | domain 정확도 | 레이턴시/쿼리 | 런타임 의존성 | 모델 |
|---|---|---|---|---|
| 규칙 파서 baseline | 42.5% | — | 0 | — |
| char n-gram 코사인 | 12.5% | 0.29ms | 0 | — |
| static model2vec + centroid | 70% | 0.13ms | numpy | ~30MB |
| **contextual ko-sroberta (ONNX int8)** | **100%** | **6.2ms** | onnxruntime+tokenizers | 110MB |

- char n-gram·정적 임베딩은 **글자 겹침/토큰 평균**이라 한국어 합성 의미("혼삿길"=결혼)를 못 만든다 → 70% 천장.
- **contextual 임베딩**이 그 벽을 깬다. int8 양자화로 440MB→110MB(정확도 손실 0), 6ms/CPU, torch-free.
- ⚠ 100%는 40건·수작업 평가셋이라 **방향성**이다. 운영 정확도는 더 낮으며 **실제 로그 평가셋으로 재검증** 필요(과적합 경계).

## 3. 아키텍처

- **모델**: `jhgan/ko-sroberta-multitask` → ONNX export → 동적 int8 양자화. 빌드: `scripts/build_intent_onnx.py`
  (빌드타임 전용 `[intent-build]` extra: torch/transformers/optimum). 산출물 `compiled/intent_onnx/`
  (110MB `.onnx`는 git 미추적 + `.sha256` 무결성, 토크나이저·설정은 추적).
- **런타임**: `saju_engines.intent_embedding.IntentEmbeddingClassifier` — onnxruntime + tokenizers +
  numpy(`[intent]` extra). mean-pooling 문장 임베딩 → intent별 **centroid** 코사인 최근접. torch 미사용.
- **결정론**: 고정 ONNX 스냅샷 + 고정 시드 코퍼스(`dictionaries/intent_seed_corpus.json`, docs/08 D-1 출처).
- **graceful**: 의존성·모델 부재 시 `available()=False`로 비활성 — 서버는 규칙 파서만으로 정상 기동
  (절대원칙 11 취지, fresh clone 무탈). 싱글턴 `get_intent_classifier()`로 1회 로드(기동 warm).

## 4. 통합 (rules-first 폴백)

`chat_service._augment_domain_by_similarity(intent, question)`:
- **`intent.domain is GENERAL`일 때만** 분류기 조회(규칙이 확신하면 규칙 우선 — 미개입).
- 게이트: `score ≥ 0.55` **및** `margin(top1−top2) ≥ 0.05` **및** 제안 domain ≠ general.
- 통과 시 **domain**(general→구체) + **event**(미지정 시)만 보강. **query_type·점수·간지·판정엔 미개입**.
- 미통과(저신뢰·모호)면 원본 유지 — 예: "오늘 기분이 좋아"는 general 그대로(오라우팅 안 함).
- 호출 위치: `intent = parsed.intents[0]` 직후, planner/assess 이전(보강된 intent가 하류로 전파).

임계·마진(0.55/0.05)은 토이 평가셋 기준 **초안** — 실제 로그 평가셋 확보 시 재튜닝 대상.

## 5. 향후

- 실제 로그 평가셋으로 임계·마진 캘리브레이션(현 100%는 토이셋).
- 시드 코퍼스 보강(의도당 예문↑·관용구·실로그) — event 정확도(현 ~44%) 개선 여지.
- query_type 보강(예: terminology/comparison 라우팅)은 영향 범위가 커 현재 보류.

## 구현 파일 맵

| 파일 | 역할 |
|---|---|
| `packages/saju_engines/.../intent_embedding.py` | 운영 분류기(torch-free, graceful, centroid+margin) |
| `dictionaries/intent_seed_corpus.json` | 시드 코퍼스(docs/08 D-1 출처, reviewed:false 초안) |
| `apps/api/.../chat_service.py` (`_augment_domain_by_similarity`) | rules-first 폴백 배선 |
| `scripts/build_intent_onnx.py` | ONNX export + int8 양자화(빌드타임 1회) |
| `scripts/eval_intent_onnx.py` | torch-free 런타임 정확도·레이턴시 측정 |
| `compiled/intent_onnx/` | 모델 스냅샷(.onnx git 미추적 + .sha256) |
| `tests/fixtures/intent_eval.jsonl` | 보류 평가셋(40건 — 방향성) |
| `pyproject.toml` `[intent]`/`[intent-build]` | 런타임/빌드타임 의존성 분리 |
