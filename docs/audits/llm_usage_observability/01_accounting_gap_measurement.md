# LLM 사용량 회계 공백 측정 (LLM-USAGE-OBSERVABILITY-01)

```yaml
verdict:
  - USAGE_ACCOUNTING_DEPENDS_ON_APP_LIFESPAN
  - USAGE_ACCOUNTING_MISSING_OUTSIDE_APP_LIFESPAN
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

## 7. 다음 슬라이스 후보 — 아직 고르지 않음

```
① 앱 밖 프로세스에도 sink 를 붙이는 경로   배치·스크립트가 스스로 setup() 을 부르게
② 실패·재시도 시도 회계                    시도 단위 카운터(성공 여부와 분리)
③ 드롭 카운터                              sink 예외를 세는 최소 지표
④ 귀속 강제                                owner_id·ref_id 없는 호출을 식별 가능하게
```

①~④ 는 서로 독립이고 비용·위험이 다르다. 어느 것을 먼저 닫을지는 결정이 필요하다.
