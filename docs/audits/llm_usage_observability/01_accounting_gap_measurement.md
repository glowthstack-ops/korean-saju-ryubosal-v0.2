# LLM 사용량 회계 공백 측정 (LLM-USAGE-OBSERVABILITY-01)

```yaml
verdict:            # 초판. 8장에서 좁혔다 — 아래 판정은 그대로 두고 정정 이력으로 남긴다
  - USAGE_ACCOUNTING_DEPENDS_ON_APP_LIFESPAN
  - USAGE_ACCOUNTING_MISSING_OUTSIDE_APP_LIFESPAN   # ← 너무 넓었다
  - USAGE_ACCOUNTING_IDENTITY_INCOMPLETE
  - FAILED_AND_RETRIED_ATTEMPTS_NOT_ACCOUNTED
  - USAGE_ACCOUNTING_SILENTLY_DROPPED_ON_SINK_ERROR
  - USAGE_ACCOUNTING_NOT_BUFFERED   # flush 의존 없음 — 이 항목만 정상
```

측정만 한다. production 무변경, 실호출 없음(공급자 호출부만 모의로 교체).

핵심 질문: **애플리케이션 수명주기 밖에서 실행된 합법적인 LLM 호출이 비용 기록 없이
성공할 수 있는가?** 답은 **그렇다**.

---

## 1. 계기

`daily_fortune_polish` 조사에서 공급자 콘솔 24건 / `llm_usage` 1건으로 갈렸다.
차이는 테스트가 낸 실호출이었고(commit `b1ff3f6` 에서 차단), 그때 **왜 기록이 남지
않았는가**는 별도 트랙으로 열어 두었다. 이 감사가 그 트랙이다.

---

## 2. 배선 구조

```
_lifespan (FastAPI)
  └ contextlib.suppress(Exception)
      └ usage_logging.setup()
          ├ PricingStore() · UsageStore()      DSN 없으면 ValueError → return False
          ├ migrate() · seed_defaults()
          └ llm_client.set_usage_sink(_sink)   ← 유일한 주입 지점
```

`llm_client._emit_usage` 는 `_usage_sink is None` 이면 **조용히 반환**한다.

---

## 3. 측정 결과

### A. 앱 밖 프로세스의 sink 상태

```
llm_client._usage_sink   None
usage_logging._usage     None
```

### B. sink 없이 호출이 성공하는가 — **그렇다**

```
generate_reading(...)  →  응답 반환 성공
usage 기록             →  0건
```

과금은 발생하고 기록은 남지 않는다. pytest·감사 스크립트·배치·smoke 등
**앱 lifespan 밖의 모든 프로세스**가 여기에 해당한다.

### C. sink 가 받는 필드

```
surface  model  provider  is_fallback
input_tokens  output_tokens  cached_tokens
owner_id  product_code  call_type  ref_id
```

`chat_single` 기본 호출에서 `owner_id = None` · `ref_id = None` 이었다. 호출부가 명시로
넘기지 않으면 **귀속 주체 없이 적재**된다.

### D. 실패·재시도 — 기록되지 않는다

```
공급자 시도 횟수   2   (메인 1 + 폴백 1)
usage 기록 건수   0
```

`_emit_usage` 는 성공 분기에서만 호출된다. 공급자가 200 을 돌려주고도 파싱이 실패하는
경우처럼 **과금은 됐는데 실패로 처리되는 호출이 회계에서 통째로 빠진다.**

`COST_LEDGER`(in-process)도 성공분만 센다 — DB 와 같은 공백을 공유한다.

### E. sink 오류는 조용히 삼켜진다

```python
def _emit_usage(**fields):
    if _usage_sink is None: return
    try: _usage_sink(**fields)
    except Exception: pass      # 응답 우선
```

DB 장애·연결 실패 시 기록만 사라지고 아무 신호도 남지 않는다. 응답을 막지 않는 정책
자체는 타당하지만, **드롭 사실을 세는 카운터가 없다.**

### F. 버퍼링·flush 의존 — 없음

`UsageStore.record` 는 호출마다 즉시 INSERT 한다. 프로세스 종료 전 flush 에 의존하지
않는다. 측정 항목 중 유일하게 정상이다.

---

## 4. 그래서 `llm_usage` 로 할 수 있는 말과 없는 말

```
할 수 있다   앱 lifespan 안에서 성공한 호출의 비용
할 수 없다   실제 총 지출
             앱 밖 프로세스의 호출
             실패·재시도로 소모된 과금
             DB 장애 중 유실된 기록
```

**비용 이상을 조사할 때 DB 침묵을 "호출 없음" 으로 읽으면 안 된다.** 이번 일운 사건이
정확히 그 오독이 가능했던 상황이었다.

---

## 5. 재현

```python
from saju_api.services import llm_client, usage_logging
assert llm_client._usage_sink is None          # 앱 밖
llm_client._PROVIDERS["gemini"] = lambda *a: ("본문", 500, 300, 120)
llm_client.generate_reading("질문", call_type="chat_single")   # 성공, 기록 0
```

실호출을 내지 않는다 — 공급자 호출부만 모의로 바꾼다.

---

## 5-1. 이 감사 중에 같은 유형의 사고가 한 번 더 났다

게이트를 cwd 독립으로 고친 직후(`421d956`), **게이트를 호출하는 감시 명령**이 같은
함정에 빠졌다.

```bash
before=$(sha256sum "오늘의운세.txt" | cut -d' ' -f1)   # 상대 경로 — 실패, 빈 문자열
after=$(sha256sum "오늘의운세.txt" | cut -d' ' -f1)    # 실패, 빈 문자열
[ "$before" = "$after" ] && echo YES                    # "" == "" → YES
```

게이트는 `exit=127` 로 아예 실행되지 않았는데 감시는 `export_content_identical=YES` 를
찍었다. 앞선 사고가 **미실행을 실패로** 오인한 것이라면 이번엔 **미실행을 통과로**
오인했다. 후자가 더 위험하다.

교훈은 게이트 스크립트만 고쳐서는 부족하다는 것이다.

```
호출부도 절대 경로를 쓴다
전제 실패를 통과로 접지 않는다 — test -f · test -n 으로 즉시 중단
빈 값끼리의 비교를 "동일" 로 읽지 않는다
```

재실행 결과는 정상이었다(`3bacfc0` · `VALID_SUITE_PASS` · 게이트 4종 전부 `RAN`).

---

## 6. 이 감사가 하지 않은 것

```yaml
수정:            없음 — 측정 슬라이스다
경로별 호출 수:   미측정 — call_type 상수가 호출부에 흩어져 있어 정적 집계로는 부정확
원격/운영 집계:   미접근
```

`call_type` 별 실제 호출 분포는 정적 grep 으로는 셀 수 없다(대부분 변수·기본값으로
전달된다). 필요하면 운영 로그나 sink 계측으로 따로 측정해야 한다.

---

## 7. 진입점 열거 — ①의 전제가 무너졌다

①(앱 밖 sink 배선)을 착수하려고 호출부를 전수 열거했더니 대상이 없었다.

```
generate_reading 호출부
  apps/api/.../daily_fortune_polish.py     앱 안
  apps/api/.../report_service.py           앱 안
  apps/api/routers/chat.py                 앱 안
  apps/api/.../chat_service.py             앱 안
  tests/unit/*                             실호출 차단됨(b1ff3f6)

앱 밖 production 호출부   0
배치·크론 호출부          0   (일운 pregen 루프는 앱 안이다)
```

**앱 밖에서 `generate_reading` 을 부르는 production 코드가 하나도 없다.** `ensure_sink()`
같은 초기화 경로를 만들어도 오늘 호출부가 0개다 — 방어 코드가 아니라 **쓰이지 않는
추상화**가 되고, 문서상 "앱 밖 회계가 해결됐다" 는 오해까지 만든다.

### 실재하는 구멍은 성격이 다른 하나뿐

`scripts/smoke_openai_fallback.py` 는 앱 밖에서 실제 유료 호출을 낸다(opt-in, 3건).
그런데 `generate_reading` 이 아니라 `llm_client._call_openai` 를 **직접** 부른다.

```
_call_openai 직접 호출 → 회계 깔때기 우회 → COST_LEDGER·llm_usage 어디에도 없음
```

sink 를 붙여도 잡히지 않는다. 그리고 이 우회는 **의도적**이다 — smoke 의 목적이
"production 어댑터가 만드는 요청 그대로" 를 검증하는 것이라 상위 계층을 타면 안 된다.

---

## 8. 정정된 판정

3장의 관측 자체는 유효하다. 다만 판정 문구가 실제 도달 가능성보다 넓었다.

```
USAGE_ACCOUNTING_MISSING_OUTSIDE_APP_LIFESPAN     ← 너무 넓다
```

정확한 판정은 다음이다.

```yaml
NO_CURRENT_OUTSIDE_LIFESPAN_PRODUCTION_ENTRYPOINT
OUTSIDE_LIFESPAN_ACCOUNTING_GAP_NOT_PRODUCTION_REACHABLE
OPT_IN_DIAGNOSTIC_PAID_CALL_OUTSIDE_COST_LEDGER
```

공백이 없다는 뜻이 아니라, **오늘 production 경로로는 도달하지 않는다**는 뜻이다.

---

## 9. 이 트랙에서 실제로 한 조치

### ①-a 미구현

```
ENSURE_SINK_IMPLEMENTATION_DEFERRED_UNTIL_REAL_ENTRYPOINT
NO_ZERO_CALLSITE_INFRASTRUCTURE_ADDED
```

대신 체크리스트만 남긴다. **앱 밖 유료 호출 진입점을 추가할 때:**

```
명시적 usage sink 구성
operation identity 부여
sink 실패 정책 검증
유료 호출 회귀 추가
```

### ①-b smoke 를 명시적 예외로 고정

회계에 억지로 편입하지 않는다. 대신 실행 결과에 범위를 드러낸다.

```
billing_scope=diagnostic_unledgered usage_ledger_recorded=false live_call_opt_in=...
```

`--confirm-live-call` 지정 시 비용 발생·미기록 사실을 한 줄로 더 알린다. smoke 전용
회계 카운터나 sink 직접 기록은 만들지 않는다 — 시작하면 operation identity·중복 기록·
불완전 usage 응답까지 함께 설계해야 한다.

```
DIAGNOSTIC_PAID_CALL_EXPLICITLY_EXCLUDED_FROM_APP_LEDGER
DIAGNOSTIC_ACCOUNTING_SCOPE_VISIBLE
PRODUCTION_USAGE_ACCOUNTING_UNAFFECTED
```

### ③ silent drop → observable drop

production 에서 실제 도달 가능한 유일한 결함이었다.

```python
except Exception as exc:
    _logger.error("event=usage_accounting_sink_write_failed sink_type=... "
                  "exception_type=... call_type=... ref_id=... ")
```

통지는 **error sink 를 타지 않는다** — 드롭을 세는 수단이 함께 드롭되면 계측이 무의미하다.
새 관측 시스템을 만들지 않고 기존 구조화 로그에 오류 이벤트만 추가했다.

지킨 불변식.

```
사용자 응답 정책 불변      LLM 호출 수 불변
sink 실패를 재시도하지 않음  회계 실패가 본 요청을 실패시키지 않음
sink 미주입은 실패가 아니다(앱 밖에서 오류 로그를 쏟지 않는다)
```

### ②·④ 미개방

```
FAILED_ATTEMPT_ACCOUNTING_DEFERRED_PENDING_OBSERVED_RETRY_OR_COST_DRIFT
ATTRIBUTION_ENFORCEMENT_DEFERRED_PENDING_NON_REQUEST_CALLER
```

②는 작은 관측 패치가 아니라 provider-attempt 회계 모델 설계다(SDK 내부 재시도 범위 ·
요청 도달 여부 · 실패 요청의 과금 여부 · usage 미보고의 표현 · 논리 연산과 시도의 분리).
실제 비용 불일치나 retry 증거가 확보될 때 별도 트랙으로 연다.

④는 강제할 대상이 없다 — 앱 밖 production 호출부가 0이다.

---

## 10. 트랙 종료 상태

```yaml
CURRENT_PRODUCTION_USAGE_PATHS_ACCOUNTED
NO_OUTSIDE_LIFESPAN_PRODUCTION_CALLER
DIAGNOSTIC_PAID_CALL_EXPLICITLY_UNLEDGERED
SINK_FAILURE_OBSERVABLE
ATTEMPT_LEVEL_ACCOUNTING_DEFERRED
IDENTITY_ENFORCEMENT_DEFERRED
NO_UNUSED_SINK_INFRASTRUCTURE_ADDED
```
