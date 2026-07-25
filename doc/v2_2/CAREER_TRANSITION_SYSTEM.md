# CAREER_TRANSITION_SYSTEM — 이직·커리어 전이 사건 시스템 (SSOT)

> 이 문서는 이직/취업/퇴사/입사/전보를 **하나의 운이 아니라 세 트랙(기회·종료·진입)이 병렬로 움직이는 사건 그래프**로 다루기 위한 단일 진실 원천(SSOT)이다. 관계 도메인의 `RELATIONSHIP_EVENT_SYSTEM.md`와 동일한 절차(SSOT → 어휘·런타임 감사 → 게이트 → shadow 구현 → 캘리브레이션 → beta 노출)를 따른다.
>
> **작성 상태**: §0~§9 = 1차 검토 단위(불변식·구조 뼈대). §10~§17 및 부록 = 후속. 본 문서에 정의되지 않은 명리 규칙은 §10 증거계약에서 **감수 대상**으로만 표기하며 감수 전 구현하지 않는다(리포 규칙 10).

---

## §0. 확정 결정표

| # | 결정 | 근거·불변식 |
|---|---|---|
| D1 | **신규 canonical event_key를 만들지 않는다.** 단계·결과·종료사유는 `career_change`/`job_gain`/`promotion` 위의 **타입 레이어**로 표현한다. | INV-5. 21키 taxonomy·캘리브레이션 보존 |
| D2 | 이직은 **3 병렬 트랙**(Opportunity·Exit·Entry)이다. 단일 선형 상태로 저장하지 않는다. | INV-1 |
| D3 | 상태는 **회사별 `CareerTransitionEpisode`**로 저장한다. 복수 지원을 동시 표현한다. | INV-2 |
| D4 | **현 직장 Exit 트랙은 Episode에 복제하지 않고 별도 `current_employment_context`가 단독 소유**한다. 오퍼 수락 시 선택 Episode와 링크한다. | §6, INV-1 |
| D5 | 단계 enum은 **트랙별 분리**(`OpportunityStage`/`ExitStage`/`EntryStage`) + `CareerStageRef{track, stage}`. `CareerTransitionStage`는 외부 계약/tagged wrapper 명칭으로만. | INV-5 보정 |
| D6 | 사실·예측 상태는 **Episode 전체가 아니라 트랙별**로 보유하며, `resolved_stage`(사용자 발화 규칙 해소)와 `forecast_stage`(엔진 제시)를 구분한다. | INV-6 보정, §7 |
| D7 | 출력·전이는 **단계별 효과 벡터**를 사용한다. `activation`/`favorability`는 상위 요약값으로만 유지한다. | INV-3 |
| D8 | 완료 성사도는 전역 공식이 아니라 **`CareerTransitionKind.required_gates`의 병목**으로 계산한다. Kind는 **전환 결과유형**(EXTERNAL_MOVE/JOB_GAIN_FROM_UNEMPLOYED/RESIGNATION_ONLY/INTERNAL_TRANSFER)이다. | INV-4 보정, §9 |
| D9 | **제한형 현실·과정 축**만 둔다: `candidate_intent`·`candidate_readiness`·`process_activation`·`counterparty_evidence`. `employer_interest`는 **산출 금지 필드**(신규 구축 대상 아님). | INV-7 |
| D10 | `SelectionState`는 **전이 그래프 구현 패턴만 복제**한다(`can_transition`·허용/금지·종료/재개·상태별 계약). enum·`ModeGuard`·무작위성 캡은 미사용. | INV-8 |
| D11 | `PredictionEngines`(단계 타임라인·ActivationWindow·성사도)는 **재사용 확정 자산이 아니라 P0-B shadow 적합성 검증 대상**이다. `CareerStageAdapter` 뒤 shadow 경로로만 각성한다. | INV-9 |
| D12 | 카테고리는 3분리한다: `event_domain="career"` / `transition_family="move"` / `calibration_domain="career"`. **단, P0 동안 기존 `EVENT_CATEGORY` 두 정의는 byte 불변으로 유지**하고, 3분리 필드는 shadow 계약으로 정의한다. 소비처 전환·기존 필드 폐기는 후속 Phase 결정. | INV-10 + INV-13 |
| D13 | P0는 **기존 출력 byte 불변**. 오늘의 운세는 **미배선 유지**. | INV-13, INV-14 |
| D14 | 소비 표면은 **AI 채팅 + 테마/총운·집중 리포트**. 억지 통합 금지. | §2 |
| D15 | **사실 완료(`realization_status`)와 예측 성사도(`forecast_completion_readiness`)를 분리**한다. 점수·명식·forecast는 실제 완료를 생성·취소하지 않는다. | INV-15, §9 |
| D16 | 트랙 상태는 단일 `completed_stage`가 아니라 **`stage_history` + `lifecycle_status` + `close_reason`** 구조로 보존한다. `resolved_stage`는 저장 상태가 아니라 **resolver 출력**이다. | INV-6 보정², §7 |
| D17 | 트랙 내부 전이 외에 **교차 트랙 게이트**(Entry 진입·Episode 연결·전환 완료)와 **고용 컨텍스트 승격 원자성**을 강제한다. | INV-16·INV-17, §5 |
| D18 | `EntryTrack`은 "새 회사 입사"가 아니라 **목적지 진입**(외부 입사 또는 내부 역할·부서·근무지 실행)이며 `entry_scope`로 구분한다. `INTERNAL_TRANSFER`를 담는다. | §3·§5 |
| D19 | **P0는 단일 primary employment만 관리**한다. 겸업·복수 고용·법인+개인사업 병행은 별도 확장 범위이며, 감지돼도 단일 Exit로 임의 병합하지 않는다. | §6, 명문화 A |
| D20 | **태도 / 절차 단계 / 전환 유형을 서로 다른 필드가 소유**한다. 태도=`CareerProcessMode`(NOT_SEARCHING/PASSIVE_EXPLORATION/ACTIVE_JOB_SEARCH/EXIT_ONLY), 절차 단계=`OpportunityStage` 등(오퍼 검토·협상 포함), 유형=`transition_kind`(해소)·`intended_kind`(목표) **nullable**(UNKNOWN enum 금지). 현재 질문 대상은 비저장 `CareerQueryFocus`. 사주는 유형을 확정하지 않음. | §6·§9 |
| D21 | 캘리브레이션 family cap은 `calibration_domain`이 아니라 **파생 `calibration_cap_key`**(career_transition/employment_entry/promotion/relocation)를 쓴다(설계 B). 같은 커리어 도메인에서도 사건별 검증을 보존(INV-12 정합). 질문 수 상한은 도메인별 총량으로 별도 관리. | §11-8 |

### 20 불변식 (요약)
- **INV-1** 3 병렬 트랙·순서 교차 허용·`completion` 단일값 금지
- **INV-2** 회사별 Episode·대상 해소 우선순위
- **INV-3** 단계별 효과 벡터, activation/favorability는 요약값
- **INV-4** 성사도 = `Kind.required_gates` 병목
- **INV-5** 신규 event_key 0, 트랙별 stage enum
- **INV-6** 트랙별 `resolved_stage`/`forecast_stage`, 사실/예측 타입 분리
- **INV-7** 제한형 축, `employer_interest` 산출 금지
- **INV-8** SelectionState 전이 패턴만 복제
- **INV-9** PredictionEngines shadow 적합성 검증 대상
- **INV-10** category 3분리(+P0 byte 불변)
- **INV-11** 한 신호의 다단계 중복 가점 금지(기여값 감사)
- **INV-12** 캘리브레이션 축 분리(occurrence/outcome/experience/settlement, no_signal·no_attempt·not_reached·unknown 병합 금지)
- **INV-13** P0 기존 출력 byte 불변
- **INV-14** 오늘의 운세 미배선 유지
- **INV-15** 사실 완료(`realization_status`) ≠ 예측 성사도(`forecast_completion_readiness`) — 점수·명식·forecast는 실제 완료를 생성·취소하지 않음
- **INV-16** 교차 트랙 정합 — Entry 진입·Episode 연결·전환 완료에 명시적 교차 트랙 게이트
- **INV-17** 고용 컨텍스트 승격 원자성 — 외부 이직 완료 시 기존 종료 + 대상 승격을 하나의 상태 변경으로
- **INV-18** 신호 ≠ 단계 사실 — 명리 신호는 단계별 forecast·효과 벡터에만 기여하고, 사용자의 지원·오퍼·퇴사·입사 사실이나 상대 회사의 행동을 생성하지 않음(§10 서두)
- **INV-19** Legacy form non-scoring — 기존 `event_forms`의 확률·가중값은 단계 벡터·병목 성사도·`forecast_completion_readiness`에 입력하지 않음(의미 분류와 shadow 출력 비교에만 사용)
- **INV-20** Category compatibility — 전환 기간에 기존 `EVENT_CATEGORY`는 **직렬화 호환성**을, 신규 3분리 필드는 **의미 소유권**을 갖는다. 동일 소비자가 legacy category와 신규 필드를 **동시에 집계·가점하지 않는다**(§11)

---

## §1. 범위 · 비범위

**범위**
- 외부 이직, 재직자 구직·오퍼 탐색, 무직 상태 취업, 퇴사 단독, 내부 전보·직무 변경, 복수 오퍼 비교.
- 각 단계의 강도·방향·성사·정착을 분리해 "어디까지 진행되는 운인지"를 서술.

**비범위 (P0 기준)**
- 오늘의 운세(데일리) 배선 — 유지(INV-14). 데일리 `news`("좋은소식")는 별개 도메인이며 커리어 엔진과 배선하지 않는다.
- 신규 canonical event_key 추가.
- `employer_interest`(회사 실제 채용 의사) 산출.
- 기존 점수·출력 변경(P0는 shadow·타입 정의만).

---

## §2. 소비 표면 분리

| 표면 | 역할 | P0 |
|---|---|---|
| AI 채팅 | 단계 진단 + 다음 단계 forecast + 사용자 사실 상속 서술 | shadow only |
| 테마/총운·집중 리포트 | 커리어 섹션(단계 벡터 기반 서술·복수 회사 비교) | shadow only |
| 오늘의 운세 | **미배선 유지** | — |

세 표면을 억지로 하나의 서술로 통합하지 않는다(관계 SSOT §2 원칙 복제). 섹션 소유권·토큰 예산은 §12에서 정의.

---

## §3. 3층 모델 + 3 병렬 트랙

세 개념을 분리한다(관계 SSOT §3의 "발현단계 ≠ 관계단계 ≠ 관계상태" 복제).

1. **발현 단계(event_phase)** — 십이운성이 부여하는 사건 상태(new_start/peak/cut_reset 등). 기존 자산, 트랙과 무관한 축.
2. **커리어 단계(CareerStage)** — 트랙별 진행 위치. **트랙마다 별도 enum**.
3. **트랙 상태(track state)** — 각 트랙의 열림/진행/종료/재개 + 종료사유.

### 3 병렬 트랙

```
A. Opportunity 트랙 (새 기회)
   contact → application → screening → interview → offer_received → offer_review → negotiating → agreement
   (offer_review·negotiating·agreement 는 별도 트랙이 아니라 Opportunity 후반 단계.
    agreement 안정도는 agreement_quality 효과축)

B. Exit 트랙 (현 직장 종료) — current_employment_context 가 소유
   undecided → notice_planned → notice_given → counteroffer → handover → exited

C. Entry 트랙 (목적지 진입 — 새 회사 입사 또는 내부 역할·부서·근무지 실행)
   start_date_pending → start_date_fixed → contract_approved → joined → probation → stabilized
   entry_scope = EXTERNAL_EMPLOYER | INTERNAL_ROLE | INTERNAL_DEPARTMENT | INTERNAL_LOCATION
```

`INTERNAL_TRANSFER`는 Exit·외부 합의 없이 **같은 조직 내 목적지 진입**이므로 Entry 트랙에 `entry_scope=INTERNAL_*`로 담는다(§9 required_gates 참조). Entry를 "새 회사 입사"로 좁게 정의하지 않는다(D18).

세 트랙은 순서가 교차할 수 있다: 오퍼 전 퇴사, 수락 후 통보 지연, 퇴사 후 입사 취소, 입사일 확정 후 내부 승인 연기, 카운터오퍼 수락으로 외부 이직 철회 등. 따라서 `completion` 단일값 금지(INV-1).

트랙별 stage enum(§5)으로 `INTERVIEWING → HANDOVER` 같은 트랙 교차 무의미 전이를 **타입 수준에서 원천 차단**한다.

---

## §4. 효과 벡터 산출 책임표 + 이중반영 금지

기존 `activation`/`favorability`는 **상위 요약값으로만** 유지하고, 출력·전이는 아래 단계 벡터를 사용한다(INV-3).

| 효과 축 | 정의 | 트랙 | 주 산출 책임(잠정, §10 감수) |
|---|---|---|---|
| `opportunity_activation` | 기회·접촉이 형성되는 정도 | A | 관성·인성·역마·연결 신호 |
| `selection_progress` | 서류·면접·평가 절차 진행도 | A | 식상·관성 관계 |
| `agreement_quality` | 직무·보상·문서·전달의 합의 안정도 | A(후반) | 관·재·인·식 안정 조합 |
| `exit_pressure` | 현 직장 이탈 압력 | B | 식상제관·충·파·역마 (감수 대상) |
| `exit_friction` | 통보·인수인계·규정상 마찰 | B | 인성·관성 절차 |
| `entry_realization` | 실제 입사 현실화 | C | 관성·인성 정착 |
| `stabilization` | 수습·역할 정착 | C | 비겁·식상·관성 |

**이중반영 금지(INV-11)**: 한 원천 신호는 하나의 효과 축에만 1차 기여한다. 동일 신호가 여러 단계·축에 중복 가점되지 않도록 **기여값 감사**(관계 SSOT §4-1 복제)를 shadow 지표(§15)로 계측한다.

**요약값 유지**: `activation` = 전체 프로세스가 움직이는 정도, `favorability` = 전체 방향 요약. 이 둘은 기존 소비처 호환을 위해 유지하되, 단계별 상반(예: 합격 원활·처우 불리)을 평균으로 뭉개지 않도록 서술은 벡터를 사용한다.

---

## §5. 상태 전이 그래프

`SelectionState`의 **전이 그래프 구현 패턴만 복제**한다(INV-8): 허용/금지 전이 테이블 + `can_transition()` + 종료/재개 + 상태별 설명 계약. `SelectionStage` enum·`ModeGuard`·무작위성 캡은 쓰지 않는다.

### 트랙별 stage enum (D5)

```python
class CareerTrack(StrEnum): OPPORTUNITY; EXIT; ENTRY

class OpportunityStage(StrEnum):
    CONTACT; APPLICATION; SCREENING; INTERVIEW
    OFFER_RECEIVED; OFFER_REVIEW; NEGOTIATING; AGREEMENT   # 오퍼 검토·협상은 단계가 소유
class ExitStage(StrEnum):
    UNDECIDED; NOTICE_PLANNED; NOTICE_GIVEN; COUNTEROFFER; HANDOVER; EXITED
class EntryStage(StrEnum):
    START_DATE_PENDING; START_DATE_FIXED; CONTRACT_APPROVED; JOINED; PROBATION; STABILIZED

class CareerStageRef:            # 트랙 교차 전이를 타입 수준에서 차단
    track: CareerTrack
    stage: OpportunityStage | ExitStage | EntryStage
```

### 트랙 상태 구조 (단일 stage 값 금지 — D16)

트랙 상태는 진행 이력·lifecycle·종료사유를 분리 보존한다. 단일 `completed_stage`는 재개·후퇴·반복을 표현하지 못하므로 쓰지 않는다.

```python
class TrackState:
    current_confirmed_stage: CareerStageRef | None   # 승인 반영된 현실 단계
    lifecycle_status: OPEN | IN_PROGRESS | CLOSED
    close_reason: CareerTransitionCloseReason | None
    stage_history: list[StageHistoryItem]            # 사용자 확인 진행 이력
    last_updated_at: str
    source_fact_id: str | None

class StageHistoryItem:
    stage: CareerStageRef
    status: str
    occurred_at: str
    source: str
    evidence_id: str | None
```

### 종료·재개 + 상태/종료사유 분리 (명문화 B)

`NEGOTIATION_FAILED`를 단일 단계·단일 Outcome으로 두지 않는다. **단계 / lifecycle / 종료사유 / 결과**를 분리한다.

```
last_stage      = NEGOTIATING
lifecycle_status = CLOSED
close_reason     = AGREEMENT_FAILED     # CareerTransitionCloseReason
outcome          = CLOSED_UNREALIZED    # CareerTransitionOutcome
```

전이 그래프는 "선발→취소→재선발" 류 재개 서사를 허용한다(SelectionState 패턴). 재개 시 `stage_history`에 이력이 누적되고 `lifecycle_status`가 OPEN/IN_PROGRESS로 복귀할 수 있다.

### current_employment 링크 (D4)

오퍼 수락 시 `current_employment_context.exit_track`을 선택 Opportunity Episode와 링크:

```
exit_track.linked_episode_id = <선택 Episode id>
```

퇴사 단독은 링크 없이 존재 가능: `linked_episode_id = None`, `transition_kind = RESIGNATION_ONLY`.

### 교차 트랙 게이트 (INV-16)

트랙은 독립 진행하되, 아래 지점에는 명시적 교차 게이트를 적용해 모순 상태를 차단한다.

- **Entry 진입 조건**: `Entry.START_DATE_FIXED`는 같은 Episode의 Opportunity 합의·수락 사실, 또는 사용자가 직접 밝힌 입사일 확정 예외 사실이 있을 때만 허용.
- **외부 이직 완료**: `EXTERNAL_MOVE completed` = 같은 Episode의 `Entry.JOINED` **+** `current_employment_context.exit_track = EXITED`. 순서 무관하나 두 사실은 같은 전환에 연결되어야 함.
- **오퍼 철회**: `Opportunity.OFFER_WITHDRAWN` → Entry가 JOINED 전이면 Entry 종료 가능. 이미 EXITED인 Exit 상태를 자동 복원하지 않음.
- **대상 변경**: `exit_track.linked_episode_id`를 B사→C사로 단순 덮어쓰지 않고 **링크 변경 이력**을 남김.

### 고용 컨텍스트 승격 원자성 (INV-17)

외부 이직 완료 시 아래를 **하나의 원자적 상태 변경**으로 처리한다. 중간 실패로 "입사 완료인데 현재 직장이 여전히 이전 회사"가 남으면 이후 풀이 전부 오염.

```
기존 current employment  → archived
target episode employer  → new current_employment_context
exit_track               → 초기화 또는 새 컨텍스트 생성
```

중간 종료 분기(서류 탈락·면접 탈락·오퍼 철회·지원 철회·협상 결렬·카운터오퍼 수락·퇴사일 연기·입사 취소·수습 탈락·직무 불일치 등)의 전체 fixture 목록은 §13.

---

## §6. Episode 저장소 + 대상 해소

현 직장 Exit 상태를 회사별 Episode에 복제하면 충돌하므로(D4), **Exit는 `current_employment_context`가 단독 소유**한다.

```
CareerEpisodeStore
├─ current_employment_context
│   └─ exit_track: ExitTrackState        # 단독 소유 (복제 금지)
├─ opportunity_episode["A사"]
│   ├─ opportunity_track: OpportunityTrackState
│   └─ entry_track: EntryTrackState
└─ opportunity_episode["B사"]
    ├─ opportunity_track
    └─ entry_track
```

```python
class CareerTransitionEpisode:
    target_company: str | None
    target_role: str | None
    source: OpportunitySource | None      # recruiter/referral/direct/internal
    transition_kind: CareerTransitionKind | None   # 현실 증거로 해소(미확정=None)
    intended_kind: CareerTransitionKind | None      # 사용자가 밝힌 목표
    opportunity: OpportunityTrackState
    entry: EntryTrackState
    outcome: CareerTransitionOutcome | None
```

### 현재 턴 라우팅 — CareerQueryFocus (저장 상태 아님)

"사용자가 지금 무엇을 묻는가"는 저장 권위 상태가 아니라 **현재 턴 라우팅값**으로만 둔다(태도/단계/유형 필드와 중복 소유 금지).

```python
class CareerQueryFocus(StrEnum):     # 턴 단위 라우팅 (비저장)
    OPPORTUNITY; OFFER; AGREEMENT; EXIT; ENTRY; STABILIZATION
```

### P0 범위 — 단일 primary employment (D19)

P0에서는 한 시점에 **하나의 primary employment만 현재 직장으로 관리**한다. 겸업·복수 고용·법인+개인사업 병행은 별도 확장 범위이며, 감지돼도 단일 Exit 상태로 임의 병합하지 않는다("A회사 퇴사, B회사 유지" 류에서 전역 Exit 모호화 방지). 확장 시 `current_employment_context`를 다중으로 승격하는 것은 후속 Phase 결정.

### 대상 해소 우선순위 (INV-2)
```
질문에 명시된 회사
> 직전 턴의 active episode
> 사용자가 명시한 직무·오퍼
> 유일하게 열린 episode
> 해소 불가(되묻기)
```
회사명이 없어도 별칭("그 회사", "두 번째 면접 본 곳", "연봉 더 준다는 곳")을 해소해야 한다. 해소 실패 시 추측하지 않고 확인 질문(리포 규칙 7).

---

## §7. 사실 · 추론 타입 분리

소유권을 저장 상태와 파생·해석 출력으로 나눈다(INV-6 보정²). `resolved_stage`는 **저장 필드가 아니라 resolver의 이번 턴 출력**이며, 적용 게이트를 통과한 뒤에만 저장 상태(`current_confirmed_stage`·`stage_history`)를 갱신한다.

| 값 | 소유권 | 저장? | 의미 |
|---|---|---|---|
| `current_confirmed_stage` | 상태 저장소 | ✅ (TrackState) | 승인 반영된 현실 단계 |
| `stage_history` | 상태 저장소 | ✅ (TrackState) | 사용자 확인 진행 이력(재개·후퇴·반복 보존) |
| `resolved_stage` | 파서·resolver 출력 | ❌ (턴 단위) | 발화를 규칙으로 해소한 이번 턴 해석 |
| `forecast_stage` | 사주 엔진 | ❌ (파생) | 엔진이 제시한 이후 활성 단계 |

```python
class CareerStageResolution:      # resolver 출력 (저장 상태 아님)
    resolved_stage: CareerStageRef
    target_episode_id: str | None
    temporal_status: CURRENT | PAST | PLANNED | HYPOTHETICAL
    confidence: float
    evidence_refs: list[str]
```

적용 흐름: `resolved_stage`(해석) → 적용 게이트(temporal=CURRENT·확정) → `current_confirmed_stage`+`stage_history` 갱신. 관계 resolver의 temporal 규칙은 재사용하되, 그 **저장 모델까지 무비판 복제하지 않는다**(관계 resolver도 shadow 중심).

예: `episode["B사"].opportunity.current_confirmed_stage = OFFER` 이면서 `current_employment_context.exit_track.current_confirmed_stage = UNDECIDED` 가 동시에 성립("오퍼는 받았지만 퇴사 통보 전"). Episode 전체에 단일 confirmed 값을 두지 않는다.

### 불변식
- 사주 신호만으로 `current_confirmed_stage`나 완료(`realization_status=COMPLETED`)를 올리지 않는다. 엔진은 `forecast_stage`까지만(§9 INV-15).
- "오퍼 가능성"은 `forecast_stage=OFFER`이지 `current_confirmed_stage=OFFER`가 아니다.
- "지원할 생각이다"는 계획이지 `APPLICATION` 제출이 아니다(temporal: planned).
- "전에 면접 봤다"는 과거 Episode이지 현재 열린 Episode로 단정하지 않는다(temporal: past).
- 사용자가 "오퍼를 거절했다" → 해당 Episode만 종료(CLOSED), 전체 이직 의향까지 종료하지 않는다.
- `resolved_stage`는 사용자 발화 기반 — 사주 엔진이 현실 현재 단계를 추정하는 것처럼 보이지 않게 한다.

시점 정합(current/past/planned/hypothetical)은 `relationship_state_resolver`의 temporal 규칙을 재사용한다(§17).

---

## §8. 제한형 현실 · 과정 축

`employer_interest`(회사 실제 의사)는 사용자 명식으로 산출하지 않는다(INV-7). 대신 아래 4축만 둔다. `candidate_interest`를 명식에서 산출하지 않는다 — "제안받았지만 갈 생각 없음"을 명식이 이기지 못하기 때문.

| 축 | 소유권(출처) | 정의 |
|---|---|---|
| `candidate_intent` | **사용자 사실** | 사용자가 밝힌 이직·잔류 의사 |
| `candidate_readiness` | 엔진 해석 | 행동·결정 여건(명식) |
| `process_activation` | 엔진 해석 | 선발·협상 절차가 움직이는 정도 |
| `counterparty_evidence` | **사용자 사실·확인된 외부 사건** | 면접 요청·오퍼 등 회사 측 사실 |
| `employer_interest` | **산출 금지** | 회사 실제 채용 의사 — 명식 추정 불가 |

**표현 제한**: "평가 기회·선발 과정이 활성화될 수 있는 시기"까지만. "회사가 당신을 반드시 선택한다"류 단정 금지(리포 규칙 3). 회사 측 의향은 `counterparty_evidence`(사용자가 밝힌 사실)가 있을 때만 상태에 반영한다.

---

## §9. 사실 완료 vs 예측 성사도 (Kind별 required_gates)

**사실 완료와 예측 성사도를 분리한다(INV-15).** 병목 점수는 "앞으로 완료될 여건"만 산출하며 실제 완료 사실을 승격·취소하지 않는다.

```python
realization_status:              # 사용자 확인 사실만으로 결정
    NOT_STARTED | IN_PROGRESS | COMPLETED | CLOSED_UNREALIZED
forecast_completion_readiness: float | None   # 병목 점수(전망)
```

- `realization_status = COMPLETED`는 **사용자 확인 사실만으로** 결정. 점수·명식·forecast는 이를 생성·취소하지 않는다.
- 합의·퇴사·입사 예상 점수가 모두 높아도 실제 입사 전이면 → `IN_PROGRESS` + `forecast_completion_readiness = high`.
- 이미 입사했다는 사용자 사실이 있으면 운 점수가 낮아도 → `COMPLETED`.

### 병목 공식 (전망만)

`forecast_completion_readiness`는 전역 고정 공식이 아니라 **`CareerTransitionKind.required_gates`의 병목**이다(INV-4). 급격한 `min` 대신 조화평균/penalty 가능하나 원칙은 "초기 단계 고점이 후속 미성립을 덮지 못한다".

```python
forecast_completion_readiness(kind) = bottleneck(   # min / 조화평균 / penalty
    gate_readiness(g) for g in kind.required_gates
)
```

### 세 축 소유권 분리 — 태도 / 절차 단계 / 전환 유형

**사용자 태도, 현재 절차 단계, 전환 유형은 서로 다른 필드가 소유한다.** 한 사실을 두 필드가 중복 소유하지 않는다(정합성 붕괴 방지).

```python
class CareerTransitionKind(StrEnum):     # 전환 결과유형(4종)
    EXTERNAL_MOVE; JOB_GAIN_FROM_UNEMPLOYED; RESIGNATION_ONLY; INTERNAL_TRANSFER

# Episode 유형: 미확정과 실제 유형을 섞지 않도록 nullable + 해소 상태로 표현(UNKNOWN enum 금지)
transition_kind: CareerTransitionKind | None   # 현실 증거로 해소된 유형(없으면 None)
intended_kind:   CareerTransitionKind | None   # 사용자가 밝힌 목표(없으면 None)
# 사주 신호는 두 값을 확정하지 않는다.

class CareerProcessMode(StrEnum):        # 사용자 구직 '태도'만 소유(절차 단계 아님)
    NOT_SEARCHING; PASSIVE_EXPLORATION; ACTIVE_JOB_SEARCH; EXIT_ONLY
```

**오퍼 검토·협상은 `OpportunityStage`(OFFER_RECEIVED/OFFER_REVIEW/NEGOTIATING)가 소유**하고 `process_mode`에 넣지 않는다(중복 소유 금지). "현재 무엇을 묻는가"는 저장 권위 상태가 아니라 턴 단위 라우팅값 `CareerQueryFocus`(§6)로 둔다.

예:
```
재직 중 막연히 이직 고민:
  transition_kind = None; intended_kind = EXTERNAL_MOVE; process_mode = PASSIVE_EXPLORATION
외부 회사 지원 완료:
  transition_kind = EXTERNAL_MOVE; process_mode = ACTIVE_JOB_SEARCH
  opportunity.current_confirmed_stage = APPLICATION
```

### Kind별 필수 관문 + 완료 상태 정의

| CareerTransitionKind | required_gates | `COMPLETED`로 보는 상태 |
|---|---|---|
| `EXTERNAL_MOVE` | agreement · exit · entry | agreement accepted **+** current employment exited **+** target company joined |
| `JOB_GAIN_FROM_UNEMPLOYED` | selection · agreement · entry (exit 불필요) | agreement accepted **+** target company joined |
| `RESIGNATION_ONLY` | exit (연결 Episode 불필요) | current employment exited |
| `INTERNAL_TRANSFER` | internal decision(Opportunity) · assignment execution(Entry, `entry_scope=INTERNAL_*`) | internal decision confirmed **+** assignment executed |

이 정의로 "퇴사 단독"·"무직자 취업"·"내부 전보"가 exit/entry 부재로 영원히 미완료로 계산되는 오류를 방지한다. 재직 탐색(`transition_kind=None`·`intended_kind=EXTERNAL_MOVE`)은 외부 지원·오퍼 등 현실 증거로 `transition_kind`가 해소되고, 오퍼 수락 시점에 exit·entry 관문이 실제로 활성화된다.

---

## §10. 사건별 증거 계약

> **INV-18 (서두 불변식)**: 명리 신호는 **단계별 forecast와 효과 벡터에만** 기여한다. 사용자의 지원·오퍼·퇴사·입사 **사실**이나 상대 회사의 **행동**을 생성하지 않는다. 사실은 `user_facts`/`counterparty_evidence`만 만든다(§7·§8).

### 두 증거 계열은 분리한다 (같은 파이프라인 금지)

| | `CareerEvidenceContract` | `CounterpartyEvidence` |
|---|---|---|
| 출처 | 원국·운·구조패턴 등 **엔진 유래** | 사용자가 밝힌 **상대 회사의 관측 행동** |
| 기여 | forecast·효과 벡터 **only** | **현실 상태 해소**(confirmed/lifecycle) |
| 감수 | 명리 감수 상태 적용(부록 B) | **명리 감수 상태 미적용** |

두 계열을 하나의 증거 파이프라인에 넣지 않는다.

### 1) CareerEvidenceContract — 명리(엔진 유래) 증거

각 증거는 **감수 대상**이며(리포 규칙 10), 아래로 고정한다. 본 문서는 스키마·소유권·상태만 정의하고, 실제 명리 매핑값·가중치는 부록 B 감수를 통과한 뒤에만 채운다. **효과 방향(`direction`)은 가중치와 달리 감수 계약에 반드시 포함**한다.

```python
class CareerEvidenceContract:
    evidence_id: str                 # 이 신호를 '특정 축에 사용하는 계약'의 식별자
    signal_ref: str                  # 원천 신호 식별자(여러 계약이 공유)
    source_type: EvidenceSourceType  # ten_god / relation / unseong / structure_pattern / occupation_gate
    target: EvidenceTarget           # 아래 구조 객체
    effect: EvidenceEffect           # 아래 구조 객체(방향 포함)
    allowed_usage: list[str]         # 허용 소비(예: forecast_stage, effect_vector)
    prohibited_usage: list[str]      # 금지 소비(예: confirmed_stage 승격, employer_interest)
    applicability_conditions: list[str]
    exclusion_conditions: list[str]
    review_status: EvidenceReviewStatus    # 지식 타당성(부록 B)
    runtime_status: EvidenceRuntimeStatus  # 배포 상태(부록 B) — P0 기본 INERT/SHADOW

class EvidenceTarget:                      # 단계 대상과 축 대상을 구분
    kind: STAGE | AXIS
    track: CareerTrack | None              # OPPORTUNITY / EXIT / ENTRY (없으면 트랙 무관)
    ref: str                               # CareerStageRef 또는 효과 축 이름

class EvidenceEffect:
    type: ACTIVATION | READINESS | QUALITY | FRICTION | DELAY | STABILITY | FORM_HINT
    direction: INCREASE | DECREASE | MIXED | NEUTRAL     # 감수 필수
```

예: `target={kind:AXIS, track:EXIT, ref:"exit_friction"}`, `effect={type:FRICTION, direction:INCREASE}`.

**effect type 의미**: ACTIVATION(사건 형성도) · READINESS(단계 진행 여건) · QUALITY(방향·품질) · FRICTION(마찰) · DELAY(지연 — 실패 아님) · STABILITY(정착) · FORM_HINT(발현 형태 shadow 힌트).

#### 소비 규칙 (스키마 불변식)
- `effect.type ∈ {ACTIVATION, READINESS, QUALITY, FRICTION, DELAY, STABILITY}` 만 forecast·효과 벡터에 기여. **`current_confirmed_stage`/`realization_status` 승격 금지**(INV-15·18).
- `FORM_HINT`는 shadow 힌트일 뿐 현실 상태나 `transition_kind`를 확정하지 않는다.
- 한 `evidence_id`는 하나의 `target.ref`에만 1차 기여(다단계 중복 가점 금지, INV-11). `process_activation`은 단계 벡터의 **파생 요약값**이며 독립 가점원이 아니다.
- **`signal_ref` ≠ `evidence_id`**: 하나의 원신호(예: `STRUCT_GWAN_IN_SANGSAENG`)가 여러 축에 쓰이면 계약을 나누되 **같은 `signal_ref`를 공유**해 출처 추적·중복 감사를 유지한다. 무관한 증거로 복제하지 않는다.

### 2) CounterpartyEvidence — 현실(사용자 사실) 증거

회사의 **숨은 의향은 계산하지 않고 관측된 외부 행동만 저장**한다(`employer_interest` 산출 금지, INV-7).

```python
class CounterpartyEvidence:
    evidence_type: str          # 리크루터 연락 / 면접 요청 / 자료 요청 / 구두·서면 오퍼 /
                                #  내부 승인 대기 / 오퍼 철회 …
    episode_id: str
    observed_at: str
    temporal_status: CURRENT | PAST | PLANNED | HYPOTHETICAL
    source_fact_id: str
    evidence_strength: HARD | SOFT
```

- 서면 오퍼 = `HARD` / 리크루터 연락 = `SOFT`.
- "분위기가 좋았다" = 회사 의향 증거가 아닌 **사용자 평가** → confirmed evidence 아님.
- "회사에서 뽑으려는 것 같다" = **추측** → confirmed evidence 승격 금지.

### 3) `event_forms` 9종 재분류 (legacy 표현 분류 — 증거 아님)

`event_forms`는 증거가 아니라 **legacy 표현 분류**다. 한 형태가 여러 차원을 동시에 소유하지 않도록 `source/kind/cause/form`으로 분해한다.

| 기존 형태 | 신규 의미 |
|---|---|
| 스카우트 제의 | `opportunity_source=RECRUITER_OR_SCOUT` |
| 자발적 퇴사 | `exit_cause=VOLUNTARY` |
| 권고사직·구조조정 | `exit_cause=EMPLOYER_INITIATED` |
| 회사 이동 | `transition kind/form` |
| 역할·직무 변경 | `internal transition form` |
| 업종 변경 | `transition_form` |
| 조직개편·배치전환 | `cause/form`, 내부 이동 후보 |
| 이직 동반 퇴사 | **원자적 FORM_HINT 아님** — Opportunity(외부 이동 Episode) + Exit(해당 Episode 연결 종료)가 함께 성립할 때의 **교차 트랙 렌더링 결과** |
| 휴직·일시중단 | **3트랙 밖 `ADJACENT_EMPLOYMENT_STATE`** — 직접 매핑 보류 |

> **INV-19 (Legacy form non-scoring)**: 기존 `event_forms`의 확률·가중값은 `CareerStageAdapter`의 단계 벡터, 병목 성사도, `forecast_completion_readiness`에 **입력하지 않는다**. P0-B에서는 **의미 분류와 shadow 출력 비교에만** 사용한다.

---

## §11. category 3분리 — 공존·전환 계약

> **INV-20 (Category compatibility)**: 전환 기간에는 기존 `EVENT_CATEGORY`가 **직렬화 호환성**을 소유하고, 신규 3분리 필드가 **의미 소유권**을 갖는다. **동일 소비자가 legacy category와 신규 필드를 동시에 집계·가점하지 않는다.**

본 절은 기존 두 `EVENT_CATEGORY` 정의를 즉시 변경하는 구현안이 **아니다**. 기존 필드와 신규 의미축의 **공존·전환 계약**을 고정한다.

### 11-1. 문제 — 하나의 `category`가 세 역할을 겸함

`career_change`의 `category="move"`가 서로 다른 세 목적에 동시에 쓰인다.

| 목적 | 현재 소비 | 문제 |
|---|---|---|
| 라우팅·리포트 도메인 | `EVENT_DOMAIN="career"`(별도, 정상) | — |
| 이직↔이사 형제 발현 | `manifestation_branch`가 "정확히 2멤버 계열"로 move 사용 | **보존 필요** |
| 캘리브레이션 집계 | `question_generator` family cap이 raw `category`로 dedup | **이직·이사가 같은 슬롯 공유 → 오염** |

`CATEGORY_TO_CALIB_DOMAIN`은 이미 `move→career`로 접히므로 **도메인 매핑은 정상**이나, family cap은 fold 이전의 raw `category`를 쓰기 때문에 이직과 이사가 서로를 밀어낸다.

### 11-2. 신규 3분리 필드 (의미 소유권)

```python
event_domain: str        # "career" — 라우팅·리포트·도메인 소유권
transition_family: str   # "move"   — 이직↔이사 형제 발현 전용
calibration_domain: str  # "career" — 질문 중복 제거(family cap)·피드백 집계
```

- **`event_domain="career"`**: 질의 라우팅, 리포트 섹션 귀속, 토픽 빌더 도메인.
- **`transition_family="move"`**: `manifestation_branch`의 형제 발현 판정 **전용**. 이 축은 캘리브레이션·라우팅에 쓰지 않는다.
- **`calibration_domain="career"`**: 검증 질문 family cap 키와 피드백 집계 단위. 이직과 이사를 **다른 cap 슬롯**으로 분리한다.

### 11-3. reader별 목표 필드와 전환 Phase

| reader | 현재 소비 | 목표 필드 | 전환 Phase |
|---|---|---|---|
| `manifestation_branch` (형제 발현) | `EVENT_CATEGORY`(taxonomy_v2) | `transition_family` | 의미 동일 — 후속(무행동 가능) |
| `scoring_operational._EVENT_GROUP` (동일 계열 판정) | `EVENT_CATEGORY`(taxonomy_v2) | `transition_family` | 후속(의미 재검증 대상, §17 ③) |
| `manse_service` (API·직렬화 경계) | `EVENT_CATEGORY` → `CalibrationEventItem.category` | **legacy 유지**(직렬화 호환) | 전환 없음(INV-20) |
| `question_generator` (family cap·도메인) | `e.category` raw + `CATEGORY_TO_CALIB_DOMAIN` | `calibration_domain` | **오염 해소 대상 — 우선 전환** |
| `feedback_scorer` (MAJOR_CATEGORIES 가중) | `ev.category` | `calibration_domain` | question_generator와 동시 전환 |

P0에서는 **어떤 reader도 전환하지 않는다**(byte 불변, INV-13). 위 표는 후속 Phase의 목표 상태다.

### 11-4. 의미 해소의 단일 소유자 — `ResolvedEventSemantics`

reader마다 fallback을 각자 구현하면 drift가 생긴다(예: question_generator는 event_key 기준, feedback_scorer는 legacy category 기준). **각 reader는 자체 매핑표를 만들지 않고 공통 resolver만 소비**한다.

```python
def resolve_event_semantics(event_key, explicit_fields, legacy_category) -> ResolvedEventSemantics: ...

class ResolvedEventSemantics:
    event_domain: str
    transition_family: str | None
    calibration_domain: str
    resolution_source: ResolutionSource
    contract_version: str

class ResolutionSource(StrEnum):
    CANONICAL            # canonical event_key 매핑으로 해소
    EXPLICIT_VALIDATED   # 신규 필드가 canonical과 일치 검증됨
    LEGACY_FALLBACK      # event_key 부재로 legacy 보조 사용
    LEGACY_AMBIGUOUS     # 모호 — fail-closed
    INVALID_MISMATCH     # 신규 필드가 canonical과 충돌
```

**권위 규칙**
- canonical `event_key` 매핑이 **의미 SSOT**다.
- 신규 필드는 canonical 의미의 **직렬화·전달본**이다.
- 신규 필드가 canonical 매핑과 충돌하면 그대로 신뢰하지 않는다(`INVALID_MISMATCH`).
- **legacy category는 신규 의미의 권위 소스가 아니다.**
- 해소 우선순위: ①canonical event_key SSOT → ②신규 필드가 있으면 canonical과 일치 검증 → ③event_key가 없을 때만 legacy category 보조 → ④legacy category만으로 `transition_family` 확정 금지 → ⑤모호하면 `LEGACY_AMBIGUOUS`로 **fail-closed**.

### 11-5. legacy fallback — `transition_family` 단독 유도 금지

> **`transition_family`는 legacy category에서 단독 유도하지 않는다. canonical `event_key`별 명시 매핑만 허용한다.**

**근거(실측, SHA dbae796)**: canonical `EVENT_CATEGORY`(taxonomy_v2)의 `move`는 **정확히 2멤버**(`career_change`·`relocation`)이며 이것이 `manifestation_branch`의 "정확히 2멤버 계열" 규칙 근거다. 반면 legacy `calibration.py`의 `move`는 **4멤버**(`career_change`·`resignation`·`relocation`·`travel`)다. legacy로 `transition_family`를 유도하면 **여행·퇴사가 이직↔이사 형제 가족에 유입**되어 형제 발현이 깨지고, 이사 피드백이 career calibration으로 다시 접힐 수 있다.

#### canonical event_key별 명시 매핑

| event_key | event_domain | transition_family | calibration_domain |
|---|---|---|---|
| `career_change` | career | move | career |
| `relocation` | relocation | move | relocation |
| `job_gain` | career | **없음(None)** | career |
| `promotion` | career | **없음(None)** | career |
| (legacy `resignation`) | career | **없음** — canonical `career_change`로 정규화 후 해소 | career |
| (legacy `travel`) | 현행 도메인 유지 | **없음** — legacy `move`라는 이유로 형제 가족에 넣지 않음 | 현행 도메인 |

`transition_family=None`이 기본이며, 형제 발현 대상만 명시적으로 값을 갖는다. canonical `EventKeyV2`에 `travel`은 존재하지 않는다(legacy 문자열 전용).

fallback은 **읽기 전용 해소**이며 신규 필드를 소급 생성·저장하지 않는다.

### 11-6. 이중 소비 금지 (INV-20)

- 한 소비자는 legacy `category` **또는** 신규 필드 중 **하나만** 집계·가점에 쓴다. 혼용 금지.
- **원자성 단위**: "한 reader의 **한 실행 경로**에서 legacy와 신규 의미를 동시에 집계하지 않는다." 단, rollout 동안 **서로 다른 reader가 서로 다른 Phase에 있는 것은 허용**된다.
- `manse_service`는 P0에서 **legacy category 직렬화 소유권을 계속 유지**한다. 의미 해소 reader로 전환하지 않으며, **내부 소비자가 `manse_service`의 legacy 직렬화 값을 의미 SSOT로 역사용하는 것을 금지**한다. 신규 필드를 API에 추가할지는 별도 schema-version 결정으로 남긴다.

### 11-7. 캐시·저장·API·LLM 직렬화 호환성

| 표면 | P0 계약 |
|---|---|
| API 응답(`CalibrationEventItem.category`) | 값·의미 불변. 신규 필드는 추가 시에도 optional |
| 프론트 표시 라벨(`EVENT_CATEGORY_LABEL` "이동(이직·이사)") | 불변 |
| 저장(피드백·검증 응답) | 기존 category 기준 과거 데이터 **재해석 금지**. 단 **어느 의미 계약으로 분류됐는지는 보존** — 신규 데이터에 `calibration_semantics_version` 기록, 또는 조회 시점에 **버전 있는 해소** 수행 |
| 캐시 키 | 전환 시 `question_generator` 캐시가 이전 family-cap 결과를 유지할 수 있으므로, **캐시 키에 `category_semantics_version` 포함** 또는 전환 시 해당 **캐시 namespace 폐기** 중 하나를 후속 구현 계약에 포함 |
| LLM 직렬화 | 신규 필드는 P0에서 LLM 입력에 넣지 않음(shadow 계측 전용) |

### 11-8. calibration family-cap 행렬 (§13 executable fixture 후보)

`calibration_domain`을 그대로 cap 키로 쓰면 `career_change`·`job_gain`·`promotion`이 서로를 밀어낸다. **설계 B를 채택한다**(D21).

- **설계 A** `family_cap_key = calibration_domain` — 도메인당 질문 수 제한 우선. 이직·취업·승진 경쟁이 의도된 동작.
- **설계 B(채택)** 저장 필드를 늘리지 않고 **파생 cap 키**를 둔다:
  ```
  calibration_cap_key ∈ { career_transition, employment_entry, promotion, relocation }
  ```
  근거: INV-12(캘리브레이션 축 분리·병합 금지)와 정합하며, 같은 커리어 도메인에서도 **사건별 검증을 보존**한다. 질문 수 상한은 cap 키가 아니라 도메인별 총량 제한으로 별도 관리한다.

| 조합 | 기대 결과(설계 B) |
|---|---|
| 이직 + 이사 | 다른 `calibration_domain` → **둘 다 유지** |
| 이직 + 취업 | 다른 cap 키(career_transition / employment_entry) → **둘 다 유지** |
| 이직 + 승진 | 다른 cap 키 → **둘 다 유지** |
| 취업 + 승진 | 다른 cap 키 → **둘 다 유지** |
| 같은 이직의 여러 기간 | 같은 cap 키 → **기간 중복 축약**(대표 1건, 축약 규칙은 §14에서 확정) |
| 이직 + 이사 + 취업 | 전체 질문 수·정렬 순서를 fixture로 고정 |

형제 발현(`manifestation_branch`)은 신규 필드 도입 후에도 **이직↔이사 형제 관계가 유지**되어야 한다(`transition_family="move"` 보존). 즉 **"형제 발현은 유지 + 캘리브레이션은 분리"** 가 동시에 성립해야 한다.

### 11-9. rollout 불일치 텔레메트리

전환 기간에 다음을 계측한다(§15 shadow 지표에 포함).

```
semantics_resolution_source        # ResolutionSource 분포
canonical_explicit_mismatch        # 신규 필드가 canonical과 충돌(INVALID_MISMATCH)
legacy_ambiguous_fallback          # LEGACY_AMBIGUOUS fail-closed 건수
dual_consume_blocked               # 한 소비자가 legacy·신규 동시 집계 위반(0이어야 함)
  └ legacy_vs_new_question_selection_diff   # shadow 비교: 질문 선택 결과 차이(세부 라벨)
family_cap_collision               # 같은 cap 슬롯 공유로 탈락한 건수
```

---

## §12~§17 및 부록 A — 후속 작성 단위

목차 번호는 유지하되 **작성 순서**는 다음으로 한다(소비 배선은 증거·fixture·감사 지표 확정 후에 작성해 과도 노출 방지):

```
§13 fixture → §14 캘리브레이션 → §15 shadow 지표
→ §12 소비 배선 → §16 로드맵 → §17 재사용표
```

- §12 소비 배선(chat 디렉티브·리포트 섹션 소유권·토큰) · §13 중간 종료·재개·교차 전이 fixture(Opportunity/Exit/Entry 3트랙 + 트랙 간 결합) · §14 캘리브레이션 축(occurrence/outcome/experience/settlement) · §15 shadow 오류 지표 · §16 로드맵 P0~P5 · §17 재사용 3등급(①그대로 보존 ②어댑터 뒤 재사용 ③의미 재검증 후 재사용) · 부록 A 어휘·런타임 감사 결과(2026-07-25, SHA dbae796).

---

## 부록 B. 명리 규칙 감수 목록 (초안)

각 규칙은 즉시 승인·반려하지 않고 상태 머신으로 추적한다. **지식 타당성(review)과 배포 상태(runtime)는 별도 상태 머신**이며 같은 속도로 움직이지 않는다.

```python
class EvidenceReviewStatus(StrEnum):     # 지식 타당성만
    UNREVIEWED          # 등록만
    SOURCE_DOCUMENTED   # 명리 출처·근거 문서화
    EXPERT_REVIEWED     # 전문가 감수 통과
    REJECTED            # 반려

class EvidenceRuntimeStatus(StrEnum):    # 배포 상태만
    INERT; SHADOW; BETA; LIVE; DISABLED
```

### 승격 조건 (배포 적격성)

`deployment_eligibility`는 저장 필드가 아니라 아래 조건으로 **계산되는 파생값**으로 다룬다.

```
SHADOW      : review ≥ SOURCE_DOCUMENTED + 안전상 금지 표현 차단 + 사용자 출력 미노출
BETA / LIVE : review = EXPERT_REVIEWED + fixture 통과 + shadow 기준 통과 + 별도 노출 승인
REJECTED    : runtime_status 는 INERT 또는 DISABLED 만 허용
```

### 상태 전이

```
Review : UNREVIEWED → SOURCE_DOCUMENTED → EXPERT_REVIEWED
         (UNREVIEWED / SOURCE_DOCUMENTED / EXPERT_REVIEWED → REJECTED)
Runtime: INERT → SHADOW → BETA → LIVE     (어느 단계에서든 → DISABLED)
```

두 상태는 독립적이다. 예: `review=EXPERT_REVIEWED, runtime=INERT`(감수 완료·미구현) / `review=SOURCE_DOCUMENTED, runtime=SHADOW`(최종 감수 전 내부 계측만) / `review=REJECTED, runtime=DISABLED`(사용 금지).

### 감수 무효화 규칙

> 증거의 **의미·적용 조건(`applicability_conditions`/`exclusion_conditions`)·대상 축(`target`)·효과 방향(`effect.direction`)·출처(`source_ref`)** 가 변경되면 이전 `EXPERT_REVIEWED` 상태를 승계하지 않고 최소 `SOURCE_DOCUMENTED`로 되돌린다.

### 감수 대장 컬럼

```
evidence_id | signal_ref | source_ref | applicability_conditions | exclusion_conditions
| review_status | review_version | reviewer | reviewed_at
```

### 감수 우선순위 (위험·오해 순)

| 순위 | 규칙군 | 이유 | 대표 후보(감수 대상 — 미확정) |
|---|---|---|---|
| 1 | 퇴사·강제이탈 | 위험 서술 유발 | 천충지충+관성=exit 압력, 식상제관=exit 신호, 권고사직 cause |
| 2 | 오퍼·합의·입사 | 성사 오해 유발 | 정관+인성=agreement/entry, 관인상생=취업, 완료 단정 위험 |
| 3 | 구조↔운 활성화 연결 | natal 구조와 시점 활성화 브리지 | 식상제관·상관견관의 단계 전이 연결 |
| 4 | 합·충·형·파·해 단계 역할 | 변화강도≠결과품질 분리 | 충=면접 변화강도, 합=수렴, 형·파·해=지연·충돌 |
| 5 | 십성 보조 단계 매핑 | 영향 낮음 | 관/인/재/식의 단계별 보조 기여 |

각 규칙 행은 §10 `CareerEvidenceContract`의 `evidence_id`와 1:1로 연결되고(같은 원신호는 `signal_ref` 공유), review·runtime 두 상태로 각각 관리된다. 명리 매핑값·가중치 채움과 라이브 배선은 감수 통과 후 별도 Phase다. `CounterpartyEvidence`(현실 증거)는 명리 감수 대상이 아니므로 본 대장에 등재하지 않는다.
