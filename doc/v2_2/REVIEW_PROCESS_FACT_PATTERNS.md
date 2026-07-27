# P2-PROC-2 사전조사 — 명시적 진행 사실 표현 자료 감사

> 상태: **감수 대기** · 기록일 2026-07-27 · 코드 변경 없음
>
> 판정: **INSUFFICIENT** — 실로그 카탈로그로 5개 도메인 추출 사양을 만들 수 없다.

## 1. 조사 범위와 검색어

```
자료   doc/v2_2/docs/08_QUESTION_PATTERNS.md (251줄)
       backend/tests/fixtures/*.jsonl
       backend/tests/**(테스터 회귀 문장)

도메인 계약 · 대출 · 이사 · 연애·만남 · 선발·추첨·지원
검색어 대출 소개팅 추첨 청약 심사 면접 지원했 접수 승인 거절 탈락 당첨
       계약 이사
```

## 2. 도메인별 발견 건수 — 카탈로그

```
대출     0        소개팅   0        추첨     0
청약     0        심사     0        면접     0
접수     0        승인     0        탈락     0
지원했   1        거절     3        당첨     2
계약     6        이사     9
```

`거절`·`당첨`은 진행 사실이 아니라 **정책 문장**(악의성 요청 거절, 당첨 단정 금지)이다.
`지원했` 1건도 진행 사실 문장이 아니다.

**5개 도메인 중 3개(대출·선발·연애 접점)는 표현이 0건이다.**

## 3. 왜 0건인가 — 자료 성격의 문제

`08_QUESTION_PATTERNS.md`는 **2,255건 원본이 아니라 그것을 추상화한 패턴 카탈로그**다
(251줄). 각 패턴에 예시 문장이 1~3개 붙어 있을 뿐이고, 원본 로그는 이 리포에 없다.

```
카탈로그가 담는 것   질문의 형식·시점 표현·intent 분류·대화 연속성 패턴
카탈로그가 안 담는 것  사용자가 밝힌 현실 진행 사실의 표현 변형
```

즉 **자료 자체가 이 조사에 맞지 않는다.** "카탈로그에 있을 것"이라는 제 가정이 틀렸다.

## 4. 그래도 건진 것 — 진행 사실 문장 3개

### F9 (대화 연속성) — 유일한 완전한 ACTIVE 사례

```
"11월에 합격해서 12월부터 다니는 중인데 이 자리는 나와 안 맞아"

도메인   career
분해     합격(TERMINAL: 채용 과정 종료) + 다니는 중(ACTIVE: CAREER_ENTRY/PROBATION)
주체     self · 현재성 current
근거구절 "합격해서" · "다니는 중"
추출가능 high-confidence
```

**한 문장에 terminal과 active가 공존하는** 사례로, 지적하신 near-miss 유형에 정확히 해당한다.
카탈로그가 이를 `Reality Context 갱신 후 재분석`으로 이미 규정하고 있다.

### C9 (데드라인 역산) — PLANNED, ACTIVE 아님

```
"대부분 계약 후 2~3개월 안에 이사날을 잡게 돼. 2027년 2월까지 이사를 완료하고 싶어.
 계약에 적당한 달과 이사에 적당한 달을 정해줘"

intent   PLANNED_OR_INTENDED (완료하고 싶어 = 목표 진술)
판정     process evidence 생성 안 함 — 계약·이사 어느 단계도 시작되지 않았다
```

이 문장이 중요한 이유: **날짜 선택 질문의 전형인데 진행 사실이 아니다.** P2 게이트가
켜지면 이런 질문의 후보는 정상적으로 `LOCAL_TRIGGER_ONLY`가 되어야 한다.

### A11 — 준비 중, 경계 사례

```
"올해 이사를 준비하고 있어. 둘의 사주를 종합해서 언제 이사를 가는게 좋을지"

intent   PLANNED_OR_INTENDED ("준비하고 있어"는 관측 가능한 단계가 아니다)
주체     pairwise (가구 단위)
추출가능 ambiguous — 계약·날짜 확정 여부가 문장에 없다
```

## 5. 테스터 회귀 문장 4종 — 실제 자산은 여기 있다

`tests/unit/test_user_facts.py` · `tests/integration/test_chat_pipeline.py`에 보존돼 있다.

```
"나는 9월 30일에 이사가 결정되었어. 8~9월 동안 은행 대출과 인테리어를 진행해야되는데"
"계약서는 이미 다 썼고 그 날은 짐만 옮기는 날이야."
```

### 예비 분해

| 구절 | family | stage | intent | 비고 |
|---|---|---|---|---|
| 9월 30일에 이사가 결정되었어 | `MOVE_PROCESS` | `IN_PROGRESS` | ACTIVE | §8-3 — 날짜 포함만으로 SCHEDULED 아님 |
| 계약서는 이미 다 썼고 | `CONTRACT_PROCESS` | `COMPLETED` | **TERMINAL** | 과정 종료 |
| 8~9월 동안 은행 대출을 진행해야되는데 | `LOAN_PROCESS` | — | PLANNED | "해야되는데" = 미착수 |
| 주택을 사기 위한 대출 | — | — | — | **목적 설명 · evidence 없음** |

⚠ 지적하신 대로 **원장 누락 회귀와 P2 예외 자격은 별개다.** 네 문장 모두 원장에는
저장돼야 하지만(그게 그 회귀의 목적), `ACTIVE_PROCESS_TRIGGER`를 여는 것은
`이사 IN_PROGRESS`(decision_confirmed) 하나뿐이다. "계약서 다 썼고"는 오히려 **terminal이라 닫는다.**

## 6. 충분성 판정

```
career        PARTIAL      F9 1건 + Episode 구조 완비 → 구조로 보완 가능
move          PARTIAL      테스터 회귀 1건 + 카탈로그 준비/데드라인 2건
contract      PARTIAL      테스터 회귀 1건(terminal) — active 표현 없음
loan          INSUFFICIENT 진행 표현 0건 (테스터 문장도 PLANNED)
relationship  INSUFFICIENT 소개팅·만남 진행 표현 0건
selection     INSUFFICIENT 추첨·청약·지원 진행 표현 0건
```

**어느 도메인도 SUFFICIENT가 아니다.** active·terminal·near-miss 3종을 모두 갖춘
도메인이 없다.

## 7. 그래서 P2-PROC-2를 지금 시작하면 안 된다

정규식 사전을 지금 쓰면 **6개 도메인 중 4개가 순수 합성**이 된다. `user_facts.py`가
2026-07-22에 겪은 실패(추측 패턴 → 테스터 실문장 4종 전부 미추출)와 같은 조건이다.

## 8. 확정 (2026-07-27 데굴님 승인) — 축소 개방

### 8-1. 보류 도메인은 `EventScope.UNKNOWN`이 아니라 **게이트 BYPASS**

`UNKNOWN`은 "selected base를 복원하지 못했다"는 뜻이다. 보류 도메인은 그게 아니다 —
**층위 판정은 확정됐고(MINOR_ONLY), 모르는 것은 활성 process의 존재 여부**다.
두 상태를 섞으면 감사에서 원인을 구분할 수 없다.

```python
class ProcessCoverage(StrEnum):
    AUTHORITATIVE = "AUTHORITATIVE"        # active 없음을 확정할 수 있다
    POSITIVE_ONLY = "POSITIVE_ONLY"        # 있을 때만 안다
    TERMINAL_ONLY = "TERMINAL_ONLY"        # 닫는 것만 안다
    UNSUPPORTED = "UNSUPPORTED"            # 판단 근거 없음
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


class EventGateAction(StrEnum):
    ENFORCE_MAJOR = "ENFORCE_MAJOR"
    ENFORCE_ACTIVE_TRIGGER = "ENFORCE_ACTIVE_TRIGGER"
    ENFORCE_LOCAL_ONLY = "ENFORCE_LOCAL_ONLY"
    BYPASS_UNSUPPORTED_PROCESS_COVERAGE = "BYPASS_UNSUPPORTED_PROCESS_COVERAGE"
    BYPASS_PROCESS_SOURCE_UNAVAILABLE = "BYPASS_PROCESS_SOURCE_UNAVAILABLE"
```

| coverage | active 발견 | 발견 안 됨 |
|---|---|---|
| `AUTHORITATIVE` | `ENFORCE_ACTIVE_TRIGGER` | `ENFORCE_LOCAL_ONLY` |
| `POSITIVE_ONLY` | `ENFORCE_ACTIVE_TRIGGER` | **BYPASS** |
| `TERMINAL_ONLY` | 해당 없음 | **BYPASS** |
| `UNSUPPORTED` | 해당 없음 | **BYPASS** |
| `SOURCE_UNAVAILABLE` | 해당 없음 | **BYPASS** |

보류 도메인의 기록 형태:

```
layer_evidence_scope = MINOR_ONLY          ← 확정 사실. 계속 shadow 산출
raw_event_scope      = LOCAL_TRIGGER_ONLY  ← 산출은 하되
gate_action          = BYPASS_UNSUPPORTED_PROCESS_COVERAGE  ← 적용은 안 함
```

**어느 도메인에서 왜 게이트가 적용되지 않았는지 감사할 수 있다.**

### 8-2. 도메인별 1차 coverage

```
career        AUTHORITATIVE   Episode 3트랙 + hard fact + EntryScope
move          POSITIVE_ONLY   고정밀 결정·확정 패턴만
contract      TERMINAL_ONLY   닫는 용도만 — 게이트는 미개방
loan          UNSUPPORTED
relationship  UNSUPPORTED
selection     UNSUPPORTED
```

### 8-3. 이사 — `SCHEDULED`와 `IN_PROGRESS`를 가른다

`"9월 30일에 이사가 결정되었어"`는 문법적으로 두 가지로 읽힌다.

```
9월 30일에 이사하기로 확정됐다
9월 30일에 이사 결정이 내려졌다
```

날짜가 포함됐다는 이유만으로 `SCHEDULED`로 만들지 않는다.

```
"이사 날짜/입주일/이삿날이 …로 확정"  → MOVE_PROCESS / SCHEDULED
"…에 이사가 결정"                     → MOVE_PROCESS / IN_PROGRESS
                                        stage_detail = decision_confirmed
```

열 수 있는 사건도 제한한다.

```
허용   이사 준비 · 일정 조율 · 입주·잔금·업체 coordination · 실행 과정
불허   부동산 횡재 · 계약 성사 전반 · 큰 재물 증가
```

### 8-4. 계약 — 파서는 만들되 게이트는 열지 않는다

```
TERMINAL_ONLY가 할 수 있는 것   기존 active 계약 사실을 닫는다
할 수 없는 것                   active가 없다고 확정 · minor 후보를 LOCAL로 강제
```

active 계약 표현을 탐지할 수 없으므로 "발견 안 됨 = 진행 중 계약 없음"이 성립하지 않는다.
active 표현이 확보되면 `POSITIVE_ONLY` → 회귀 축적 후 `AUTHORITATIVE`로 단계 승격한다.

### 8-5. 운영 원문 로그는 `UNAVAILABLE`로 간주

P2 1차 개방을 로그 확보에 의존시키지 않는다. 2차 개방 자료의 우선순위는 다음이다.

```
1. 기존 테스터 회귀 문장
2. 베타 테스트에서 명시적으로 제출된 누락 문장
3. 현재 대화의 rules-first extractor shadow 결과
4. 최소한의 curated near-miss
```

원문 저장 정책을 유지한다면 자동 수집 대신 **명시적 제출** 방식이 맞다. 운영 로그가
나중에 확인되더라도 개인정보·저장 동의·보존 정책을 먼저 확인한 뒤 사용한다.

---

## 9. P2-PROC-2 구현 범위 (축소)

```
career   기존 hard-fact Episode 어댑터 — 정규식 불필요
move     결정·확정·날짜 확정·예약 고정밀 positive 패턴
contract 완료·취소·무산·포기 terminal 패턴
loan · relationship · selection   파서 없음 · coverage=UNSUPPORTED
```

### 골든 fixture

| 문장 | Process 결과 | P2 예외 |
|---|---|---|
| 11월에 합격해서 12월부터 다니는 중인데 | `CAREER_OPPORTUNITY/COMPLETED` + `CAREER_ENTRY/IN_PROGRESS` | 허용(Entry) |
| 2027년 2월까지 이사를 완료하고 싶어 | PLANNED_OR_INTENDED | 불허 |
| 이사가 결정되었어 | `MOVE/IN_PROGRESS` | 허용 |
| 계약서는 이미 다 썼고 | `CONTRACT/COMPLETED` | 불허·종료 |
| 8~9월 동안 은행 대출을 진행해야 | PLANNED | 불허 |
| 주택을 사기 위한 대출 | evidence 없음 | 불허 |

⚠ F9는 한 문장에 terminal(합격)과 active(다니는 중)가 공존하지만 **서로 다른 family**라
하나가 다른 하나를 덮지 않아야 한다. `supersede()`가 (subject, family) 단위인 이유다.

---

## 10. 관련 코드·자료
- `doc/v2_2/docs/08_QUESTION_PATTERNS.md` — 패턴 카탈로그(원본 로그 아님)
- `backend/tests/unit/test_user_facts.py` — 테스터 회귀 4종 보존
- `backend/tests/integration/test_chat_pipeline.py` — 동일 문장 파이프라인 회귀
- `saju_engines/career_fact_parser.py` — `OBSERVABLE_HARD_FACT` 기준(재사용 대상)
- `saju_engines/user_facts.py` — `fixed_schedule` 슬롯(move 재사용 후보)
- `shared_types/process_fact.py` — P2-PROC-1 모델(0f67994)
