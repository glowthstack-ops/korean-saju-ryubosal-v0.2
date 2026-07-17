# RISK EXPOSE — 통합 pre-canary 감수 자료 (2026-07-17)

> 감수 61차 §10 방식: freeze(`1b52cc2`) 후 구현 커밋(`811ccdd`·`1caaf4c`·
> `e12fa4d`·본 커밋)을 묶은 **통합 감수 1회** 요청 자료. 상세 차수 기록은
> RISK_DICTIONARY_REVIEW.md §22~§28-17.

## 1. 현재 잠금 상태 (전부 코드 확인 가능)

| 잠금 | 값 | 위치 |
|---|---|---|
| RISK_ENGINE_MODE | "off" | risk_engine_config.py |
| RISK_EXPOSURE_KILL_SWITCH | False (True=전 모드 즉시 BYPASS) | 〃 |
| RISK_EXPOSURE_RUNTIME_ENABLED | False | 〃 |
| expose_pipeline.reviewed | **false** ← 본 감수 대상 | RISK_REVIEW_MANIFEST.json |
| validatedTokenCounters(gemini-3-flash-preview) | reviewed=**true** (감수 61차 §8) | 〃 |
| canary allowlist | 빈 집합(기본 거부) | risk_engine_config.py |

## 2. 감수 완료 축 (5 scope 49/49 + adapter)

- shadow_structure/scoring/temporal/selection/presentation: 전 49항목 스탬프.
- tokenizer adapter: PROVIDER_EXACT(countTokens) — **native 36표본
  (attempt shape 12형) 전부 counted==reported(delta 0)**, corpus
  `b00716ee…902ce1`(full SHA-256), shape digest 7종 이름 결속,
  rerouting 3건 별도 부록(최종 모델 기준 집계).

## 3. 실행 경로 계약 (구현 완료·fixture 고정)

### 3-1. Disposition 3상태 (chat_service 분기)
- BYPASS: prompt/system/schema **byte 불변**, flow 미실행, 기존
  generate_reading 그대로.
- SUPPRESSED: 기존 경로 + suppressed guard 1블록만.
- INJECTED: instruction + checksum wrapped block + Gemini transport
  schema + run_injected_risk_flow(아래 3-3).

### 3-2. Startup (bootstrap_risk_exposure — EXPOSE_CANARY 포함)
artifact 재해시(native corpus+전체) → adapter 명시 등록(corpus hash
주입) → stamp_runtime_adapter_state(**VALIDATED=검증 결과 파생** —
manifest 7요소·suspension·artifact 전부 충족 시만). 실패=미등록(전부
BYPASS)+정적 reason: RISK_BOOTSTRAP_{TOPOLOGY_MISMATCH,ARTIFACT_INVALID,
MANIFEST_MISMATCH,ADAPTER_UNAVAILABLE}. worker>1 환경 신호(WEB_
CONCURRENCY 등) 감지=TOPOLOGY_MISMATCH.

### 3-3. INJECTED 실호출 상태기 (run_injected_risk_flow)
INITIAL → envelope/presence/부분수열/order-hash/episode별 claim 감사 →
위반 시 REVISION_1(최소 입력 — 내부 ID 금지) → 재위반·reroute 감지 시
REGENERATE_WITHOUT_RISK(baseline+guard 완전 재조립·bytes 일치) →
renderer(_normalize_ganji_gloss) → **최종 사용자 문자열 감사**(Unicode
변형·발급 ref 대조) → DELIVER_GENERATED / DELIVER_SAFE_FALLBACK(fallback
도 최종 감사 통과 시만) / BLOCK(전달 없음 — chat은 위험 무관 일반 실패
문구). attempt마다: 모델 재해소·suspension 최신 확인·전체 재계수·shape
digest 대조(REQUEST_SHAPE_NOT_REVIEWED)·block integrity·context 결속.
실행 context(RiskExecutionContext)는 요청당 1회 — manifest 버전 혼합
없음. 종료 후 attempt별 counted vs provider 보고 전체 input 대조
(undercount 1건=전역 SUSPENDED tombstone)·cached>0=CACHE_PATH_
UNVALIDATED identity 차단.

### 3-4. Rerouting (canary 초기 보수 정책)
위험 attempt 중 모델 변경 감지=위험 revision 중단(초안 미전송) →
REGENERATE 직행. 미감수 모델(gemini-2.5-flash 포함)=validated counter
없음 → BYPASS. **모델별 context limit 재해소·REEVALUATE_GATE 실배선은
canary 이후 확장**(현재는 어떤 rerouted 모델로도 위험 요청이 나가지
않는 구조로 대체). 전송 전 resolved model 미확정 provider 경로=BYPASS
(routingControlMode=APPLICATION_CONTROLLED 전제 — Gemini REST 직접
호출로 충족).

## 4. 베타 적용 상태 (2026-07-17 — 데굴님 결정: preflight 절차 생략)

현 환경=테스트 상태로 확인되어 별도 운영 preflight 없이 **베타 테스터
대상 전면 적용(RISK_ENGINE_MODE=expose)**으로 전환했다. 활성화 값은
`.env.risk`(gitignore — dev.sh가 기동 시 source, pytest는 읽지 않음):
mode=expose · runtime_enabled=true · topology=single_host_single_process
· 테스트용 HMAC 키(base64 48B). 감수된 게이트는 하나도 완화하지 않았다
— 게이트가 요구하는 값을 충족시켜 통과하는 방식.

smoke(scripts/risk_canary_smoke.py) 결과 **7/7 통과**: mode·runtime·
topology·HMAC 유효·bootstrap **VALIDATED**(실 artifact·manifest·
suspension 검증 파생)·비대상 질문 BYPASS(byte 불변)·대상 질문 감수 경로
산출(SUPPRESSED — smoke는 payload 없음).

중단 절차: `.env.risk` 삭제 또는 RISK_ENGINE_MODE=off 후 재기동 —
기존 답변 경로 byte-identical 복귀(fixture 검증).

## 5. Canary 관측 계획 (감수 61차 §12)

disposition 비율 / WATCH 생략률 / WARNING 누락·revision 성공률 /
renderer 후 감사 차단률 / safe fallback 발생률 / token tier 분포 /
counted vs reported drift(undercount=자동 전역 차단) / cached_input
관측(>0=자동 identity 차단) / rerouting 발생률 / 경고 편향·품질 영향
(사용자 피드백). 관측 필드는 attempt 기록 7종+observability에 존재.

## 6. 알려진 한계 (canary 범위 제한 근거)

- 파일 suspension backend는 단일 호스트·단일 프로세스 전제(다중 worker
  =공유 backend 필요 — 게이트가 topology로 차단).
- implicit cache 경로 미감수(관측 시 자동 차단으로 대체).
- multi_episode_compare·episode_followup 질문 유형 미개방(1차 canary
  3유형만).
- REEVALUATE_GATE(감수된 모델로의 rerouting 계속 진행) 미배선 — 전부
  REGENERATE로 보수 처리.

## 7. r4.1.0-canary 전환 (2026-07-17 — 통합 감수 승인 후)

- RISK_EXPOSURE_VERSION = risk-expose-**r4.1.0-canary**(policy hash
  재스탬프·manifest 재생성).
- **활성화=환경변수로만**(코드 기본값 전부 잠금 유지 — env 미설정·오타·
  비정상 값=off/False/dev키, fixture 고정): RISK_ENGINE_MODE·
  RISK_EXPOSURE_RUNTIME_ENABLED·RISK_DEPLOYMENT_TOPOLOGY·
  RISK_AUDIT_HMAC_KEY_B64(base64, 32B+ 미만=기본키=차단)·
  RISK_EXPOSE_CANARY_SUBJECT_IDS(콤마 구분). .env.example에 안내.
- smoke: scripts/risk_canary_smoke.py — §9 항목(모드·runtime·topology·
  운영 키·allowlist·bootstrap VALIDATED·비대상 BYPASS byte 불변) 점검
  후 내부 계정 1건 실요청 관측 확인.
- 관측 라벨: 응답 폐기는 attempt 기록의 TOKEN_UNDERCOUNT_DETECTED /
  CACHE_PATH_UNVALIDATED로 구분 집계(원인·복구 절차 상이).
- 중단 절차: RISK_ENGINE_MODE=off(1순위 — byte 복귀 fixture) → 필요 시
  RUNTIME_ENABLED=false → baseline 회귀 확인.
