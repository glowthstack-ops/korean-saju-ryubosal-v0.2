# P2-2a — active-process 데이터 감사와 호환 계약

> 상태: **감수 대기** · 기록일 2026-07-27 · 코드 변경 없음
>
> 선행: `6420902`(P2-1 EventScope 산출). P2-2 배선 전 실제 슬롯을 먼저 확인한다.

## 0. 결론 먼저

```
커리어      구조화된 stage 보유 — 즉시 사용 가능
연애·선발    구조화된 stage 보유 — 다만 "관측 상태"이지 "사용자 명시 사실"이 아니다
계약·대출·이사  구조화된 process 상태가 **없다**
             원장은 도메인 슬롯이 아니라 어법 슬롯이다
```

**계약·대출·이사에 대해 "대출 심사 중"을 `ProcessFamily=LOAN_REVIEW, stage=IN_REVIEW`로
읽어낼 경로가 현재 존재하지 않는다.** 설계안이 요구한 매핑표를 지금 만들면 입력이
없는 표가 된다.

---

## 1. 실사 결과 — 데이터 원천별

### 1-1. 커리어 — 3트랙 stage 완비

```python
OpportunityStage  CONTACT · APPLICATION · SCREENING · INTERVIEW
                  OFFER_RECEIVED · OFFER_REVIEW · NEGOTIATING · AGREEMENT
ExitStage         UNDECIDED · NOTICE_PLANNED · NOTICE_GIVEN
                  COUNTEROFFER · HANDOVER · EXITED
EntryStage        START_DATE_PENDING · START_DATE_FIXED · CONTRACT_APPROVED
                  JOINED · PROBATION · STABILIZED
EntryScope        EXTERNAL_EMPLOYER · INTERNAL_ROLE · INTERNAL_DEPARTMENT
```

종료 상태도 별도로 있다(`INTERVIEW_REJECTED` · `OFFER_WITHDRAWN` ·
`COUNTEROFFER_ACCEPTED` · `OTHER_OFFER_CHOSEN`).

`career_fact_parser.parse_career_fact()`가 발화에서 사실을 뽑고,
`CareerParsedFact.is_transition_eligible`이 `OBSERVABLE_HARD_FACT`만 통과시킨다 —
**"이직하고 싶다" 류 욕구를 이미 걸러낸다.**

`EntryScope`가 있어 설계안이 요구한 구분이 가능하다.

```
외부 면접 진행 중  → EntryScope.EXTERNAL_EMPLOYER  → promotion 불허
승진 심사 중       → EntryScope.INTERNAL_ROLE      → promotion 허용
```

### 1-2. 연애 — stage는 있으나 출처가 다르다

```python
RelationshipStage  NONE · AWARENESS · CONTACT · DATING
                   COMMITMENT · FORMALIZATION · MARRIED
```

⚠ 이 stage는 **엔진이 추정한 관계 상태**이지 사용자가 명시한 진행 사실이 아니다.
D1 감사에서 "연애는 플래그만"이라고 기록한 것이 이 지점이다.

```
"소개팅 날짜가 잡혔어"  → 사용자 명시 사실 (P2-2가 원하는 것)
RelationshipStage.CONTACT → 엔진 추정 (P2-2가 쓰면 안 되는 것)
```

둘을 구분하지 않고 stage를 그대로 예외 근거로 쓰면 **엔진 추정이 자기 자신의 게이트를
열어주는 순환**이 된다.

### 1-3. 선발 — stage 완비, 다만 shadow

```python
SelectionStage  OPPORTUNITY_OPEN · APPLICATION · ELIGIBILITY · SELECTION
                ALLOCATION · PREFERENCE_MATCH · ACCEPTANCE · EXECUTION · ADAPTATION
```

`APPLICATION` · `SELECTION` 대기는 설계안의 `SELECTION_PENDING`에 대응한다.
다만 D1 감사대로 shadow-first라 운영 승격 여부를 확인해야 한다.

### 1-4. 계약·대출·이사 — **구조화된 process 상태 없음**

`user_facts.py`의 슬롯은 도메인이 아니라 **어법**으로 나뉜다.

```python
completed        "이미 계약도 끝냈고"
remaining        "잔금만 남았"
fixed_schedule   "9월 30일에 이사가 예정"   (singleton)
planned_task     "8월에는 대출 신청"
day_plan         "그날 이사"
stated_purpose   "주택을 사기 위한 대출"
unchangeable     "변경 불가"
folk_condition   "손없는 날"
relationship_status / marital_correction
```

저장 형태는 **인용 원문(quote)**이다. 정규화된 값이 아니다(오해석이 적다는 이유로
의도된 설계). 따라서 다음이 성립하지 않는다.

```
원장 조회  loan_review == "in_progress"   ← 이런 슬롯이 없다
실제       planned_task = "8월에는 대출 신청"  ← 원문 인용
```

`stated_purpose`에 "대출"이 들어 있어도 그것이 **심사 중인지, 계획인지, 거절됐는지**를
구조로 알 수 없다. 추출은 rules-first 정규식이며 LLM을 쓰지 않는다(절대원칙 1·9).

---

## 2. 그래서 매핑표를 지금 만들면 안 된다

설계안의 표는 `ProcessFamily × ProcessStage → event allowlist` 구조다. 입력이 있어야
성립한다.

```
CAREER_APPLICATION / CAREER_TRANSITION / INTERNAL_PROMOTION   입력 있음 ✓
SELECTION_PENDING                                             입력 있음(shadow) △
RELATIONSHIP_*                                                엔진 추정만 ✗
CONTRACT_REVIEW / LOAN_REVIEW / MOVE_COORDINATION             입력 없음 ✗
```

절반이 빈 표가 된다. 그리고 빈 칸이 있는 채로 P2-3 게이트를 켜면, 지적하신 회귀가
**정확히 계약·대출·이사·연애에서** 발생한다.

```
"대출 심사 중인데 계약하기 좋은 날 봐줘"
→ 원장에 quote는 남지만 process family로 해소되지 않음
→ NO_EVIDENCE → LOCAL_TRIGGER_ONLY
→ 사용자가 명시했는데도 후보가 주요 목록에서 빠진다
```

---

## 3. 선택지

### 안 1 — process 추출기를 먼저 만든다 (권장)

`user_facts.py`와 같은 rules-first 방식으로 **process family + stage 추출기**를 추가한다.
기존 어법 슬롯은 그대로 두고 병행한다(원장 계약 불변).

```
"대출 심사 중"        → LOAN_REVIEW / IN_REVIEW
"대출 신청했어"        → LOAN_REVIEW / APPLIED
"대출 거절됐어"        → LOAN_REVIEW / REJECTED   (terminal)
"계약서 검토 중"       → CONTRACT_REVIEW / IN_REVIEW
"이사 날짜 조율 중"    → MOVE_COORDINATION / NEGOTIATING
"소개팅 날짜 잡혔어"   → RELATIONSHIP_CONTACT / SCHEDULED
"추첨 결과 기다려"     → SELECTION_PENDING / RESULT_PENDING
"대출 받아볼까 생각 중" → 추출 안 함 (욕구)
```

```
장점  P2-3 게이트를 전 도메인 동일 성숙도로 켤 수 있다
      커리어의 OBSERVABLE_HARD_FACT 기준을 그대로 재사용
비용  정규식 사전 + 종료 상태 표현 + 회귀 — 중간 규모
위험  욕구/검토 의향을 진행으로 오분류하면 게이트가 헐거워진다
      → 커리어처럼 "관측 가능한 사실"만 통과시키는 기준 필요
```

### 안 2 — 커리어·선발만 열고 나머지는 UNKNOWN fail-safe

```
계약·대출·이사·연애  process 근거 없음 → SOURCE_UNAVAILABLE 취급
                     → EventScope.UNKNOWN → 기존 동작 유지(게이트 미적용)
```

```
장점  회귀 없음. 커리어에서 P2 효과를 먼저 검증
단점  P2의 사용자 영향 절반이 미적용. 도메인별 동작이 갈린다
      PROV-3 실측상 MINOR의 relationship 221 · wealth 49가 방치된다
```

### 안 3 — 현재 발화만 우선 처리

설계안 §6의 우선순위 중 1번(현재 발화)만 먼저 구현하고 원장·Episode는 뒤로 미룬다.

```
장점  "지금 말한 사실이 무시되는" 최악의 회귀를 먼저 막는다
단점  이전 턴 사실이 승계되지 않아 멀티턴에서 다시 끊긴다
```

---

## 4. 권고

**안 1**을 권한다. 안 2는 PROV-3에서 실측한 relationship 221건·wealth 49건을 방치하고,
안 3은 이 리포의 멀티턴 승계 정책(`user-facts-ledger`)과 어긋난다.

다만 안 1은 P2-2b 이전에 **별도 슬라이스**가 되어야 한다.

```
P2-2a-1  process 추출기 (rules-first) + 종료 상태 + 회귀
         → docs/구현 분리. 원장 기존 슬롯 불변
P2-2b    ActiveProcessEvidence 정규화 (현재 발화 + 원장 + Episode)
P2-2c    EventScope 연결
P2-3     Top-N 게이트
```

---

## 5. 안 1을 택할 경우 확정이 필요한 것

```
1. process family 목록을 설계안 그대로 갈지, 이 리포 도메인에 맞춰 조정할지
2. 관계 stage를 '사용자 명시 사실'과 '엔진 추정'으로 분리 저장할지
   (현재 RelationshipStage 하나에 섞여 있다)
3. 선발 shadow를 P2 예외 근거로 승격할지 (D1에서 보류했던 항목)
4. 종료 상태 표현 목록 — "거절됐어" · "취소됐어" · "안 하기로 했어" · "끝났어"
5. subject 구분 — 동반자 사실이 본인 후보를 열지 않도록 (P2-2b 필수)
```

특히 2번이 중요하다. 분리하지 않으면 엔진 추정이 자기 게이트를 여는 순환이 생긴다.

---

## 6. 관련 코드

- `shared_types/career_transition.py` — `OpportunityStage` · `ExitStage` · `EntryStage` · `EntryScope`
- `shared_types/career_commands.py` — `CareerFactType` · 종료 상태
- `saju_engines/career_fact_parser.py` — `parse_career_fact` · `is_transition_eligible`
- `shared_types/relationship_event.py` — `RelationshipStage`(엔진 추정)
- `shared_types/selection_allocation.py` — `SelectionStage`(shadow)
- `saju_engines/user_facts.py` — 어법 슬롯 10종 · rules-first 추출
- `saju_engines/layer_evidence_scope.py` — `derive_event_scope(active_process=...)` 배선 지점
