# LLM 비용 소진 일시 중단·재개 프로세스 (SSOT)

> 2026-10-06 데굴님 승인 설계(추천안 4건 그대로). 구현 상태는 §8.
> 관련: `backend/config/llm_config.json`(options), `migrations/019_llm_service_state.sql`,
> `apps/api/saju_api/services/{llm_client,llm_service_state,llm_resume_service,report_job_runner}.py`.

## 1. 배경과 목표

종전에는 공급자 429를 네트워크 오류·5xx·타임아웃과 같은 "일시 오류"로 취급했다. 비용 소진
상태에서도 매 요청마다 메인→폴백을 다시 때리고, 양쪽 모두 실패하면 호출처가 각자 일반 오류
문구로 마감했다. 중단 상태가 어디에도 저장되지 않아 "중단 중"이라는 개념 자체가 없었고,
관리자는 에러 그룹 급증이나 사용자 신고로만 알 수 있었다.

목표 네 가지.

1. 비용 소진을 **명시 신호로 분류**해 일시 오류와 구분한다.
2. **중단 상태를 DB에 영속**해 채팅·리포트·일운 교정·health가 같은 상태를 본다(재기동 후 유지).
3. 관리자가 결제 후 **프로브 검증을 거쳐 수동 재개**한다(자동 복귀 없음 — 불필요한 반복 재개 방지).
4. 재개 시 **가치가 남은 미완료 작업만** 이어간다(중단 시점 채팅·지난 날짜 일운은 무시).

## 2. 상태 모델

단일 행 테이블 `llm_service_state`(migration 019).

| 필드 | 의미 |
|---|---|
| `state` | `active` \| `suspended` |
| `reason` | `quota_exhausted` \| `manual` |
| `suspended_at` / `resumed_at` / `resumed_by` | 전이 시각·재개 관리자 |
| `providers` | 공급자별 기록 `{provider, model, kind, detail, since, until}` — `kind`=`quota`(명시 소진) / `cooldown`(애매한 429, 자동 복귀). `until`이 지나면 다시 시도한다. suspended 중엔 `until=null`(무기한). |
| `last_probe` | 마지막 재개 프로브 결과(콘솔 표시) |

읽기는 프로세스 내 5초 캐시(`llm_service_state.current`), 쓰기는 즉시 무효화. DSN 미설정
환경(테스트·무DB)은 메모리 백엔드. 저장소 장애 시 조회는 **active 로 간주**한다(상태 조회
실패가 서비스를 막지 않는다).

## 3. 소진 분류 (`llm_client.classify_provider_error`)

하드 중단은 오분류 비용이 크다(관리자가 올 때까지 서비스가 멈춘다). 그래서 **명시 신호에만**
`quota`를 주고, 나머지는 종전의 일시 오류 경로(재시도·폴백)로 보낸다.

| 공급자 | `quota` (하드 소진) | `transient` (종전 경로) |
|---|---|---|
| OpenAI | 429 + `error.type/code == insufficient_quota`, 402 | 429 `rate_limit_exceeded`, 5xx, 타임아웃 |
| Gemini | 429 RESOURCE_EXHAUSTED 중 quotaId/메시지에 `PerDay`·`Daily`·`billing`, 400/403 중 `billing` | 429 `PerMinute`, 범용 문구만 있는 429, 5xx, 타임아웃 |

`quota`는 `ProviderQuotaExhausted(provider, model, detail)`(RuntimeError 하위)로 올린다 —
기존 except 절이 그대로 잡는다.

## 4. 전이 규칙 (`llm_client.generate_reading`)

```
suspended?  → 즉시 LLMServiceSuspended (가드·네트워크 어디에도 닿지 않음)
메인: 키 있음 && 쿨다운 아님 → 호출. quota → 기록(쿨다운 15분) + 폴백으로. 일시 오류 → 재시도 후 폴백.
폴백: 키 있음 && 쿨다운 아님 → 호출. quota → 기록.
키 있는 공급자 전부가 quota 로 막힘 → suspend() (system_errors 1건, 메시지 고정) → LLMServiceSuspended
그 외 → 종전 RuntimeError("메인·폴백 모두 실패")
```

- **메인만 소진**: 폴백으로 계속 서비스한다. 메인은 `provider_cooldown_seconds`(기본 900초) 동안
  호출하지 않아 실패 호출이 반복되지 않는다. 쿨다운이 지나면 한 번 다시 시도한다(여전히 소진이면
  재기록 — 경고 1건은 '새로 막힐 때'만 쌓인다).
- **폴백 키가 없고 메인이 소진**이면 "키 있는 공급자 전부 소진" → 중단.
- 중단 전이 기록: `system_errors` source=`llm` kind=`llm_service_suspended`, 메시지 상수
  `LLM 서비스 일시 중단 — 공급자 비용 소진`(fingerprint 안정 → 재개 시 resolve). 상세는 detail.
- 공급자 소진 기록: kind=`llm_provider_quota_exhausted`, severity=warning.

## 5. 중단 중 각 표면의 동작

| 표면 | 동작 |
|---|---|
| 채팅 신규 질문 | pending 을 만들지 않고 즉시 `status="suspended"` + 안내문. 로그인+스레드면 질문·안내문을 스레드에 남긴다(정책 응답과 같은 경로). 큐에 넣지 않는다. |
| 채팅 생성 중이던 pending | `status='error'` + 안내문, `meta.reason='llm_suspended'`. **재개 시 되살리지 않는다.** |
| 리포트 신규 요청 | 503 + `SUSPENDED_REPORT_DETAIL`. 잡 미생성(큐 적재 시 재개 때 비용이 한꺼번에 나간다 — 거부로 결정). |
| 리포트 진행 중 잡 | `status='queued'` + `error='LLM_SUSPENDED'`, 통과 섹션과 재실행 컨텍스트를 `result`에 보존. 프론트는 "대기 중" + 보류 안내. |
| 일운 교정 | `polish_board` 가 중단 예외를 받으면 **RAW 유지**(FAILED 아님). `maybe_schedule_polish` 는 예약하지 않고 `_attempted` 에도 넣지 않는다. `generate_and_polish` 는 보드 생성(엔진)만. 원문 보드는 그대로 제공. |
| `/health`, `/api/v2/service/status` | `llm_service: {state, reason, suspended_at}` (공개 최소 필드). 프론트 채팅 화면이 진입 시 읽어 배너를 띄운다. |

## 6. 관리자 재개 (`/api/v2/admin/llm/*`, require_admin)

- `GET state`: 전체 스냅샷 + `pending{suspended_report_jobs, daily_board}` + `providers_configured`.
- `POST resume`:
  1. 키 있는 공급자마다 소액 프로브(출력 `probe_max_tokens`=8, usage surface=`probe`).
  2. 통과 공급자 **0** → 409(프로브 상세) + 상태 유지, `last_probe` 만 갱신.
  3. 통과 공급자 ≥1 → `active` 전이. 여전히 소진인 공급자는 쿨다운으로 남긴다(일부 결제만 복구된
     경우에도 재개 가능 — 설계안의 "한 곳이라도 소진이면 409"를 이렇게 완화했다).
  4. 중단 기록 resolve, 보류 리포트 잡을 원자적으로 클레임(`UPDATE … WHERE status='queued' AND
     error='LLM_SUSPENDED' RETURNING`) → 중복 클릭에도 1회.
  5. 재개 작업은 백그라운드: 클레임 잡 이어 돌리기 + 게시 기준일 일운 보드 교정.
  6. 이미 active 면 프로브만 갱신하고 no-op(200).
- `POST suspend {reason}`: 수동 중단(점검·비용 통제).

### 재개 작업 선별 규칙

| 대상 | 재개 | 무시 |
|---|---|---|
| 리포트 잡 | 보류 마커 잡 전부 — 통과 섹션 재사용(`prior_sections`), 대상 사주 삭제 시 fail | 일반 `failed` |
| 일운 교정 | `threads_publish_date(now)` 보드 하나, RAW 일 때만 | 지난 날짜, 보드 없음(lazy 가 만든다), 이미 교정됨 |
| 채팅 | 없음 | 중단 중·시점 질문 전부 |

## 7. 리포트 부분 보존 (report_builder)

- `ReportBuilder(section_sink=…)`: 섹션 1개 확정마다 호출. 실행기(`report_job_runner`)가 통과 섹션을
  모아 중단 시 `result.partial_sections` 에 저장한다.
- `build(spec, prior_sections=…)`: 통과 섹션은 LLM 을 다시 부르지 않고 채택. 용신 확정 섹션이
  재사용되면 컨텍스트만 다시 만들어 이후 검사 기준(용신)을 전파한다. 통과하지 못한 항목은 재생성.
- 재실행 컨텍스트 `result.resume = {subject_id, today, display_name}`; 출생정보·상대는 재개 시
  SubjectStore 로 다시 해석한다.

## 8. 구현 상태 (2026-10-06)

| 항목 | 상태 |
|---|---|
| 분류기·예외·단락·쿨다운·중단 전이 (`llm_client`) | 완료 |
| 상태 저장소·서비스 (`llm_service_state_store`, `llm_service_state`, migration 019) | 완료 |
| 채팅 라우터(즉시 안내·pending 마감·동기 경로 전이) | 완료 |
| 리포트(503·보류·부분 보존·재개 실행기 `report_job_runner`) | 완료 |
| 일운 교정(RAW 유지·예약 차단·재개 헬퍼) | 완료 |
| 관리자 API 3종 + `llm_resume_service` | 완료 |
| health·공개 상태 엔드포인트 | 완료 |
| 프론트(채팅 배너·suspended 응답·관리자 카드·리포트 보류 안내) | 완료 |
| 테스트 | `tests/unit/test_llm_service_suspension.py`(17), `test_report_builder_resume.py`(2), `test_daily_polish_suspended.py`(4), `test_report_job_runner_suspend.py`(5), `tests/integration/test_llm_suspension_api.py`(5) |

### 운영 메모
- 운영 DB 에 019 는 백엔드 기동(lifespan `llm_service_state.setup()`)이 멱등 적용한다.
- 쿨다운·프로브 토큰은 `llm_config.json` options 에서만 바꾼다.
- 미결: 월 예산 상한 경보(`llm_usage` 합계 기반)는 이번 범위 밖 — 필요 시 별도 승인.
