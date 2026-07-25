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

### 30 불변식 (요약)
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
- **INV-21** Calibration maturity — 예측 기간이 성숙하지 않았거나 Episode가 진행 중인 사례는 **실패·미도달로 확정하지 않으며 모델 품질 지표의 확정 분모에서 제외**한다. **안전·상태 무결성 지표는 성숙을 기다리지 않고 즉시 측정**한다(§14-2·§14-5·§15)
- **INV-22** Calibration orthogonality — 도달 상태·결말·시간 지연·사용자 체감·정착은 **서로 다른 축이 소유**하며, 하나의 enum 값이 둘 이상의 축을 대체하지 않는다(§14-3)
- **INV-23** Timing from occurrence — 단계 시점 오차는 **실제 발생 시점(또는 발생 범위)** 으로 계산한다. **관찰·입력 시점으로 대신 계산하지 않는다.** 예측 스냅샷은 불변이며 현재 모델 재계산값을 과거 예측처럼 쓰지 않는다(§14-5)
- **INV-24** Guard success ≠ violation — 안전장치가 정상 작동한 관측(`guard_outcome=BLOCKED`·`ROLLED_BACK` + 권위 상태 불변)은 **위반으로 집계하지 않는다.** 오류는 `VIOLATION`이거나 차단 뒤에도 권위 상태가 변경된 경우다(§15)
- **INV-25** Census before zero — 안전·무결성 지표는 **적용 가능한 실행 전수 계측**이 원칙이며, `violation_count=0`은 `measurement_status=ACTIVE` + `measured_count=eligible_count`일 때만 통과로 인정한다. **계측 누락(`measured_count=0`)은 통과가 아니라 측정 실패**다(§15-1)
- **INV-26** Consumer provenance — 사용자에게 전달되는 **단계·사실·forecast·근거 문장은 각각의 소유 출처를 유지**하며, LLM이 출처 간 상태를 **승격하거나 병합하지 않는다**(§12)
- **INV-27** Consumer visibility — **배포 자격이 없는 evidence·forecast는 사용자용 LLM 입력과 최종 응답에 영향을 주지 않는다.** 소비 자격은 LLM 판단이 아니라 **직렬화 전에 결정**한다(§12-1)
- **INV-28** Audited delivery — 최종 응답에서 **provenance 혼합·과장 위반**이 발견되면 그대로 전달하지 않으며, **재작성 또는 안전 fallback 후 다시 감사를 통과**해야 한다(§12-6)
- **INV-29** Atomic section handoff — 신규 전환 섹션의 **전달이 확정되기 전에는 기존 직업운 섹션의 상세 소유권을 축소하지 않는다.** 신규 섹션이 억제·실패·제거되면 **기존 섹션으로 완전히 복귀**한다(§12-4)
- **INV-30** Manual promotion authority — `SHADOW→BETA`·`BETA→LIVE`·`SOURCE_DOCUMENTED→EXPERT_REVIEWED`·품질 임계 최초 승인·변경은 **자동화하지 않는다.** 각 승격은 승인자·증거 패키지·승인 시점의 `build_sha`·`contract_version`·`config_snapshot_hash`를 기록한다(§16-6)

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

## §12. 소비 배선 (chat · report)

### 12-0. 소비 불변식

> **INV-26 (Consumer provenance)**: 전달되는 단계·사실·forecast·근거 문장은 각각의 **소유 출처를 유지**하며, LLM이 출처 간 상태를 **승격하거나 병합하지 않는다.**

- 사실 상태와 forecast를 **동일 문장 층위로 합치지 않는다.**
- 명리 신호가 **회사 행동·오퍼·합격·퇴사·입사를 생성하지 않는다**(INV-18).
- Episode를 해소하지 못하면 **특정 회사 단계로 서술하지 않는다.**
- 한 사건은 **하나의 섹션이 본문 소유권**을 가진다.
- chat·report 이외의 **daily 경로에는 배선하지 않는다**(INV-14).
- **LLM 입력 감사와 최종 응답 감사를 모두** 수행한다(§12-6).

### 12-1. Chat 입력 계약

전체 `CareerEpisodeStore`를 그대로 넣지 않고 **질문 관련 축약본**만 전달한다.

```
query_focus | resolved_episode | confirmed_track_states | current_facts
| forecast_stage_candidates | effect_vector | bottleneck
| blocking_factors | supporting_factors | prohibited_claims
```

각 값은 출처가 구분되어야 한다: `confirmed` / `resolved` / `forecast` / `unknown` / `not_applicable`.

**필드명이 사실처럼 보이지 않아야 한다.**

```
잘못된 예:  offer_expected = true
권장:      forecast_target_stage = OFFER
           forecast_readiness    = ...
```

#### 소비 자격은 직렬화 전에 결정한다 (INV-27)

`runtime_status`를 LLM에게 보여주고 판단시키지 않는다 — **직렬화 전에 소비 자격을 확정**해 자격 없는 항목은 payload에서 제외한다.

```python
class ConsumerVisibilityDecision(StrEnum):
    INTERNAL_ONLY | BETA_VISIBLE | LIVE_VISIBLE | SUPPRESSED
```

| 증거 runtime 상태 | 사용자용 LLM 입력 |
|---|---|
| `INERT` | **금지** |
| `SHADOW` | **금지** — 내부 관측 side-channel만 |
| `BETA` | allowlist·beta gate 통과 시만 |
| `LIVE` | deployment eligibility 충족 시 |
| `DISABLED`·`REJECTED` | **항상 금지** |

> **§10 연결**: `SOURCE_DOCUMENTED + SHADOW`는 내부 평가에 사용할 수 있으나 **사용자용 prompt·report payload에는 포함하지 않는다.** 사용자 서술에 영향을 줄 수 있는 증거는 `EXPERT_REVIEWED` 및 해당 runtime 승격 조건을 충족해야 한다.

### 12-2. Chat 서술 계약

출력 순서:

1. 사용자가 밝힌 **현재 진행 상태**
2. **현재 단계의 의미**
3. **다음 단계**에서 강하거나 약한 흐름
4. **병목·마찰·지연** 요인
5. 실제 **확인이 필요한 현실 조건**

허용 표현 예:

```
현재 확인된 사실은 면접 진행까지입니다.
명리 신호는 그 이후 단계 중 협상보다 면접 결과 통지 쪽의
활성도를 상대적으로 높게 평가합니다.
이는 회사의 합격 의사를 뜻하지 않으며,
실제 결과와 오퍼 여부는 별도로 확인해야 합니다.
```

금지 표현:

```
회사가 긍정적으로 보고 있습니다.
곧 오퍼가 옵니다.
이 시기에 퇴사하게 됩니다.
입사가 확정되는 흐름입니다.
```

### 12-3. Episode 해소 · query focus 분기

**일반 질문과 "특정 회사를 가리켰으나 해소 실패"를 구분한다.** "올해 전반적인 이직운은?"은 열린 Episode가 여러 개여도 해소 오류가 아니다.

```python
class CareerQueryResolution(StrEnum):
    GENERAL_CAREER                 # Episode 비특정 일반 질문
    EPISODE_SPECIFIC_RESOLVED
    EPISODE_SPECIFIC_UNRESOLVED
```

```
유일한 열린 Episode        → 자동 해소 허용
복수 Episode + 명시적 대상  → EPISODE_SPECIFIC_RESOLVED
복수 Episode + 모호한 대상  → EPISODE_SPECIFIC_UNRESOLVED
Episode 비특정 일반 질문     → GENERAL_CAREER (해소 오류 아님)
```

| 분기 | 허용 | 금지 |
|---|---|---|
| `GENERAL_CAREER` | Episode 중립적 활성도·병목 구조 설명 | 회사별 사실·면접·오퍼 상태 혼합, **"A사와 B사 중 어디가 된다"류 비교·합성** |
| `EPISODE_SPECIFIC_RESOLVED` | 해당 Episode의 사실·forecast만 | **다른 Episode evidence 혼입** |
| `EPISODE_SPECIFIC_UNRESOLVED` | 일반 흐름으로 제한 또는 대상 식별 요청 | 특정 회사 단계 추정, **여러 Episode 점수 합산**, **권위 상태 변경** |

리포트에서도 **복수 Episode를 하나로 합산하지 않는다** — 노출한다면 `Episode별 소구간` 또는 **결정적 Top-N 선택 규칙**을 쓴다.

### 12-4. Report 섹션 소유권

| 내용 | 본문 소유 섹션 |
|---|---|
| 전반적인 직업 변화 활성도 | 기존 직업운 요약 |
| 특정 Episode의 단계 진행 | **신규 Career Transition 섹션** |
| 퇴사 압력·마찰 | Career Transition의 Exit 트랙 |
| 입사·정착 | Entry · Stabilization |
| 구조패턴·점수 상세 | 부록 근거 섹션 |
| 사용자 현실 캘리브레이션 | 별도 현실 확인·피드백 영역 |

**기존 직업운 섹션과 신규 전환 섹션이 같은 이직 후보를 각각 자세히 설명하지 않는다.**

#### 소유권 이전은 원자적이다 (INV-29)

축소는 **신규 섹션의 전달이 확정된 경우에만** 적용한다.

```
Career Transition 블록이 생성됨 + 감사 통과 + 최종 응답에 실제 포함됨
→ 기존 직업운을 '한 줄 요약 + 신규 섹션 참조'로 축소

그 외(feature flag OFF · Episode 미해소 · 토큰 부족으로 블록 제거
     · 입력 감사 실패 · 최종 응답 감사 실패 · 신규 섹션 생성 오류)
→ 기존 직업운의 현재 동작을 그대로 유지(완전 복귀)
```

이 규칙은 §12-7 byte 불변과 직접 연결된다 — 신규 섹션이 억제되면 기존 응답이 그대로 남아야 한다.

### 12-5. 토큰 예산과 축약 우선순위

제거 순서(안전한 순):

```
세부 evidence 설명 → 보조 supporting factor
→ 낮은 순위 forecast stage → 과거 종료 Episode
```

**절대 제거 금지**:

```
confirmed/forecast 구분 | 현재 Episode 식별 | 핵심 bottleneck
| 금지 표현 지시 | 사실 근거 source
```

### 12-6. 이중 감사와 전달 제어 (INV-28)

감사는 측정에 그치지 않고 **전달 동작**을 결정한다 — 측정만으로는 잘못된 문장이 사용자에게 가는 것을 막지 못한다.

```
구조화 입력 생성 → PRE_INPUT_AUDIT → LLM 생성 → POST_OUTPUT_AUDIT
→ DELIVER | REWRITE | SAFE_FALLBACK | BLOCK
```

**A. 입력 감사(PRE_INPUT_AUDIT)** — 사실/forecast 분리 · Episode 해소 · **토큰 축약 후 필수 가드 잔존** · counterparty 추론 유입 여부 · 소비 자격(INV-27).

```python
class InputAuditAction(StrEnum):
    ALLOW | SUPPRESS_FIELD | BLOCK_NEW_BLOCK | FALLBACK_TO_LEGACY
```

예: **Episode collision 감지 시 해당 필드만 넘기지 않고 신규 블록 전체를 억제**(`BLOCK_NEW_BLOCK`).

**B. 출력 감사(POST_OUTPUT_AUDIT)** — completion overclaim · counterparty overclaim · confirmed/forecast 표현 혼합 · **다른 Episode 사실 혼입** · 구조화 값과 서술 불일치.

```python
class OutputAuditAction(StrEnum):
    DELIVER | REWRITE | SAFE_FALLBACK | BLOCK
```

필수 규칙:
- **rewrite 결과도 다시 감사**하며 **최대 rewrite 횟수 제한**
- 최종 감사 실패 시 **안전 fallback**
- **감사 전 원문 전달 금지**
- `counterparty_overclaim`·`completion_overclaim`·Episode 혼입은 **fail-closed**
- 감사 로그 추가는 허용하되 **권위 상태를 변경하지 않음**

**`narrative_completion_overclaim` 상태 전환**

```
§12 문서 작성 완료          → 아직 NOT_MEASURABLE_YET
최종 응답 감사 경로 실제 배선 → ACTIVE
BETA/LIVE인데 ACTIVE 아님   → 승격 차단
```

#### claim-level provenance ledger (INV-26 실행 구조)

최종 문장을 기계적으로 감사하려면 근거표가 필요하다.

```python
class ConsumerClaim:
    claim_id
    claim_scope        # CONFIRMED_FACT | USER_REPORTED_INFERENCE
                       # | FORECAST | GENERAL_GUIDANCE | UNKNOWN
    episode_id | track | stage
    source_refs
    evidence_strength
    visibility_decision
```

```
"현재 면접까지 진행됐습니다."          → CONFIRMED_FACT, source_fact_id 필요
"오퍼 단계의 활성도가 상대적으로 높습니다." → FORECAST, prediction_snapshot_id 필요
"회사가 긍정적으로 보고 있습니다."       → 대응 claim 없음 → counterparty_overclaim
```

ledger로 확인 가능한 것: forecast가 confirmed 문장으로 바뀌지 않았는가 · SOFT 증거가 HARD 사실로 승격되지 않았는가 · 다른 Episode 사실이 섞이지 않았는가 · 사용자 추측이 회사 의향으로 세탁되지 않았는가 · 서술된 단계에 실제 source·snapshot이 있는가.

응답 본문을 장기 저장하지 않으려면 **`claim_id`·source refs·위반 코드·응답 해시만** 감사 기록으로 남긴다.

### 12-7. byte 불변 범위

```
P0-B~P3 shadow : 기존 LLM 입력·최종 응답 변화 0
P4 beta        : 허용된 Career Transition 블록만 추가 가능,
                 기존 필드·점수·랭킹·문단 소유 내용 불변
feature flag OFF: 신규 블록 제거 후 기존 응답과 byte-identical
```

동적 ID·시간값 때문에 완전한 최종 응답 byte 비교가 어려우면, **비결정 필드를 제거한 canonical serialization**을 비교하도록 규격화한다.

---

## §13. fixture 계약

> **작성 원칙**: 이 절은 **수치·명리 매핑의 정답을 고정하지 않는다.** 검증 대상은 **상태·의미·소유권 불변식**이다. 명리 신호별 기대 효과 fixture는 부록 B 감수 진행에 따라 **별도로** 추가한다(감수 전 정답 고정 금지, 리포 규칙 10).

### 13-0. fixture 유형과 스키마

**원자적 전이 fixture와 다단계 scenario를 분리한다.** 정상 4흐름처럼 여러 단계를 거치는 것은 scenario로 두어 **중간 어느 단계에서 어긋났는지** 드러나게 한다(최종 상태만 검증하면 진단 불가).

```python
class CareerTransitionFixture:        # 원자적 전이 1건
    fixture_id
    initial_state
    input_fact_or_action
    expected_transition
    expected_rejections               # 금지 전이·승격 거부
    expected_history                  # stage_history 누적 결과
    expected_links                    # linked_episode_id 등
    expected_realization_status       # NOT_STARTED / IN_PROGRESS / COMPLETED / CLOSED_UNREALIZED

class CareerTransitionScenario:       # 다단계 흐름
    scenario_id
    initial_state
    steps: list[ScenarioStep]
    final_assertions

class ScenarioStep:
    step_id
    input_fact_or_action
    expected_transition
    expected_rejections
    expected_history_delta            # 누적이 아닌 단계별 증분
    expected_links
    expected_realization_status
```

**배치 원칙**: Kind별 정상 4흐름(외부 이직·무직 취업·퇴사 단독·내부 전보) = **scenario** / 개별 금지 전이·승격 거부 = **원자적 fixture**.

#### 공통 메타데이터 (기계적 감사용)

```
invariant_refs      # 이 fixture가 검증하는 INV 목록
decision_refs       # 관련 D 목록
fixture_class       # semantics / cap / state_machine / lifecycle / safety
expected_phase      # P0-B / P1 / … (어느 Phase에서 green이어야 하는가)
```

#### 상태 불변 기대값 (byte 불변 확인용)

변경되어야 하는 값뿐 아니라 **변경되면 안 되는 값**도 적는다. P0-B shadow에서 기존 엔진 불변 확인에 사용한다.

```
expected_unchanged:
  - EventCandidateV2.activation
  - EventCandidateV2.favorability
  - legacy_serialized_category
```

### 13-1. 의미 해소·category 회귀 fixture

`ResolvedEventSemantics`(§11-4) 자체를 검증한다.

| 입력 | 기대 |
|---|---|
| `career_change` | domain=career, family=move, cap=`career_transition` |
| `relocation` | domain=relocation, family=move, cap=`relocation` |
| `job_gain` | domain=career, family=**None**, cap=`employment_entry` |
| `promotion` | domain=career, family=**None**, cap=`promotion` |
| legacy `resignation` | canonical `career_change`로 **정규화 후** 동일 의미(별도 family 멤버 추가 금지) |
| legacy `travel` (category=move) | family=**None** — 이직↔이사 분기에서 **제외** |
| explicit field가 canonical과 일치 | `EXPLICIT_VALIDATED` |
| explicit field가 canonical과 충돌 | `INVALID_MISMATCH`, **fail-closed** |
| event_key 없이 legacy `move`만 존재 | `LEGACY_AMBIGUOUS`, **family 확정 금지** |
| `contract_version`/캐시 버전 불일치 | 이전 해소 결과 **재사용 금지**(재해소) |

형제 발현 가족은 canonical **`career_change ↔ relocation` 두 멤버만** 유지되어야 한다(§11-5 근거: canonical move=2멤버 vs legacy move=4멤버).

### 13-2. calibration-cap 조합 fixture

D21 행렬을 실행 가능한 후보로 옮긴다.

| 조합 | 기대 |
|---|---|
| 이직 + 이사 | 둘 다 유지 |
| 이직 + 취업 | 둘 다 유지 |
| 이직 + 승진 | 둘 다 유지 |
| 취업 + 승진 | 둘 다 유지 |
| 같은 이직의 여러 기간 | 아래 중복 식별 기준으로 축약 |
| 이직 + 이사 + 취업 | 세 cap key 모두 유지하되 **career 도메인 총량 상한** 적용 |

**도메인 총량 상한과 사건별 cap을 구분한다.** 총량 때문에 탈락한 항목을 "같은 family라 제거됨"으로 기록하면 안 된다.

```
selection_reason ∈ { KEPT, FAMILY_CAP_DEDUP, DOMAIN_TOTAL_CAP, LOW_CONFIDENCE, ... }
```

#### 중복 식별 기준 (같은 사건 판정)

```
duplicate_identity = canonical event_key
                   + calibration_cap_key
                   + 대상 Episode(또는 대상 회사)
                   + 시간창 중첩 여부
```

- `A사 이직 @2027-03` + `A사 이직 @2027-04` → **같은 Episode의 인접 기간** → 축약 가능.
- `A사 이직 @2027-03` + `B사 이직 @2027-04` → 같은 `career_transition` cap key라도 **다른 Episode** → **무조건 병합 금지**.

#### 결정적 타이브레이크 (회귀 안정성)

수치 정답은 고정하지 않되 **선택 순서는 결정적**이어야 한다.

```
activation 높은 후보 → 같으면 confidence → 같으면 시간상 빠른 후보
→ 같으면 stable candidate id
```

fixture 필수 필드: `duplicate_identity`, `retained_candidate`, `selection_reason`, `deterministic_tiebreak`.

### 13-3. 세 트랙 상태 머신 fixture

**정상 흐름 (Kind별) — 전부 `CareerTransitionScenario`(다단계)**

| scenario | steps | 특이 계약 |
|---|---|---|
| 외부 이직 | 지원→면접→오퍼→수락→퇴사→입사 | required_gates = agreement·exit·entry |
| 무직 취업 | 지원→오퍼→입사 | **Exit 불필요** |
| 퇴사 단독 | 통보→인수인계→퇴사 | **Episode 링크 불필요**(`linked_episode_id=None`) |
| 내부 전보 | 내부 결정→배치 실행 | **퇴사 없음**, `entry_scope=INTERNAL_*` |

각 step마다 `expected_transition`·`expected_history_delta`를 검증해 중간 이탈 지점을 특정한다.

**교차·예외 흐름**

- 오퍼 전에 퇴사(트랙 순서 교차)
- 수락 후 퇴사 통보 지연
- 퇴사 후 오퍼 철회 → **이미 EXITED인 Exit 자동 복원 금지**
- 입사일 확정 후 연기
- 내부 전보인데 **Exit가 생성되지 않음**
- 복수 Episode에서 **A사 면접·B사 협상이 섞이지 않음**(episode collision 0)

#### 교차 트랙 원자성 — 정상 + **실패 롤백** (INV-17)

정상: `Entry.JOINED` 반영 → 기존 current employment archive → 새 current employment 승격.

**실패 케이스 필수**: 2번째·3번째 변경이 실패하면 "이전 고용만 종료되고 새 고용은 없음" 같은 **반쪽 상태가 남지 않아야** 한다.

```
expected_transaction_result           = ROLLED_BACK
expected_authoritative_state_unchanged = True
expected_audit_event                   = TRANSACTION_ROLLED_BACK
```

> `expected_authoritative_state_unchanged`는 **`CareerEpisodeStore`와 current employment의 권위 상태 투영이 불변**이라는 뜻이다. 감사 로그·오류 텔레메트리·롤백 기록의 **추가까지 금지하는 의미가 아니다**(§15와 충돌 방지).

#### 대상 회사 변경 (B사 수락 → C사 선택)

- Exit 트랙의 **현재 링크는 정확히 하나**
- 기존 B사 링크는 **이력으로 보존**
- C사로 링크 변경
- **B사 Episode의 lifecycle/outcome 처리 명시**(CLOSED + close_reason)
- 단순 `linked_episode_id` **덮어쓰기 금지**

### 13-4. Episode 수명주기 fixture (재처리·정정·해소·재지원)

실제 대화에서는 같은 사실이 반복되고 정정되며 시간 역순으로 들어온다. §14 현실 캘리브레이션에도 직접 필요하다.

#### (a) 동일 사실 재전송 — idempotent

"오퍼를 받았어요"를 후속 턴에서 다시 말함 → `stage_history` **중복 추가 없음**, 동일 `source_fact_id` **재적용 없음**, 상태·링크 불변.

**멱등 키는 문장 텍스트가 아니다.** 같은 문장이라도 대상이 다르면 별개 사실이다("오퍼를 받았다"—A사 / "오퍼를 받았다"—B사).

```
idempotency_key = source_fact_id + target_episode_id + fact_type + operation_type
```

동일 `source_fact_id`의 재전달만 중복 적용하지 않으며, **다른 사실 ID는 같은 문장이어도 별개로 처리**한다.

#### (b) 사실 정정 (supersede / retract)

"오퍼를 받았어요" → "정정할게요. 오퍼가 아니라 리크루터 연락만 왔어요"

- 기존 사실의 **supersede 또는 retract 이력 보존**(물리 삭제 금지 — 보상 이벤트로 남김: `OFFER_RECEIVED → FACT_RETRACTED → RECRUITER_CONTACT_CONFIRMED`)
- `OFFER_RECEIVED` 확정 상태 **유지 금지**
- **단순 불법 상태 후퇴로 처리하지 않음** — `FACT_CORRECTION_RECONCILIATION`과 일반 `STATE_REGRESSION`을 **구분**
- **상태 투영은 정정된 단계로 단순 후퇴시키지 않고 `유효한 전체 사실 이력`으로 재계산한다.** 정정 이후 더 강한 현실 사실이 확인됐다면 그것이 우선한다. 예: "오퍼가 아니라 연락만" 정정 → 이후 "실제 입사했다" → 현재 상태는 **`JOINED` 유지**.

#### (c) 과거 사실의 역순 입력

"지난달 입사했고, 그 전주에 퇴사했어요"

- **발생일 기준으로 history 정렬**
- 현재 상태는 **입사 완료**
- 뒤늦게 입력된 과거 퇴사 사실이 현재 상태를 **퇴사 단계로 되돌리지 않음**

#### (d) Episode 해소 실패 — 모호한 별칭

A사 면접 중 + B사 협상 중 상태에서 "그 회사는 언제 결과가 나?"

```
EPISODE_UNRESOLVED
상태 변경 없음
forecast 대상 추정 금지
```

**유일하게 열린 Episode일 때만** "그 회사" 자동 해소 허용.

#### (e) 종료 후 재지원 — `NEW_EPISODE` vs `REOPEN_EPISODE`

- A사 Episode1이 서류 탈락으로 CLOSED → 몇 달 후 A사 **다른 포지션** 재지원 → **기본 `NEW_EPISODE`**(명시적 근거 없이 종료 Episode 재개 금지).
- 회사가 **같은 채용 건**을 다시 진행한다고 사용자가 밝힌 경우에만 **`REOPEN_EPISODE`** 허용.

**"같은 채용 건" 판정은 회사명만으로 부족하다.** 아래 식별 근거 중 하나가 필요하며, 근거가 부족하면 **항상 `NEW_EPISODE`가 기본**이다(§6 대상 해소와 연결).

```
채용 공고·requisition 식별자
동일 직무 + 동일 전형의 명시
사용자의 "중단됐던 같은 전형이 다시 열렸다" 확인
```

### 13-5. 금지 전이·사실/예측 분리 fixture (안전 회귀)

가장 중요한 회귀 묶음이다.

| # | 검증 | 근거 |
|---|---|---|
| 1 | forecast `OFFER`가 confirmed `OFFER`를 생성하지 않음 | INV-6·18 |
| 2 | 높은 병목 성사도가 `COMPLETED`를 생성하지 않음 | INV-15 |
| 3 | 사용자 입사 확인은 **낮은 운 점수와 무관하게** `COMPLETED` | INV-15 |
| 4 | 계획형 "지원하려 한다"가 `APPLICATION` 승격되지 않음 | §7 temporal=PLANNED |
| 5 | 과거형 "작년에 면접 봤다"가 현재 Episode를 덮지 않음 | §7 temporal=PAST |
| 6 | 추측 "뽑으려는 것 같다"가 **HARD** counterparty evidence가 되지 않음 | §10-2 |
| 7 | Entry 진입 근거 없이 `JOINED` 전이 금지 | INV-16 |
| 8 | 오퍼 철회가 이미 완료된 Exit를 자동 복원하지 않음 | INV-16 |
| 9 | 하나의 `signal_ref`가 동일 축에 중복 기여하지 않음 | INV-11 |
| 10 | legacy와 신규 의미를 **같은 실행 경로에서 이중 집계하지 않음** | INV-20 |

---

## §14. 캘리브레이션 축

### 14-0. 단위 — Episode × Track × Evaluated(Target) Stage

**전체 이직을 한 번에 성공·실패로 평가하지 않는다.** 캘리브레이션 단위는 "이직 사건 하나"가 아니라 **Episode × 트랙 × 평가 대상 단계(`target_stage`)** 다.

"도달 단계(Reached Stage)"는 `reach_status=REACHED`인 경우에만 성립하는 **결과값**이므로 단위 명칭에 쓰지 않는다 — `NOT_REACHED`·`PENDING`·`NOT_APPLICABLE` 레코드를 설명하지 못한다.

예) B사 Episode: Opportunity=오퍼 도달 / Exit=통보 안 함 / Entry=미도달
→ Opportunity occurrence는 **발생**, Exit는 `NO_ATTEMPT`, Entry는 `NOT_REACHED`. **전체를 단순 실패로 저장하지 않는다**(INV-12 축 병합 금지와 정합).

### 14-1. 캘리브레이션 레코드

```python
class CareerCalibrationRecord:
    calibration_record_id           # 안정적 레코드 ID(revision 참조 대상)
    episode_id
    transition_kind
    track
    target_stage                    # 평가 대상 단계
    reach_status                    # 게이트(occurrence보다 앞섬)
    reach_resolution_reason         # 왜 그 도달 상태인가(§14-2)
    occurrence
    outcome                         # DELAYED 없음 — timing 축이 소유
    timing_status                   # 별도 축(§14-3)
    experience
    settlement                      # EARLY_EXIT 없음 — lifecycle/Exit 소유
    settlement_reason
    stage_occurred_at               # 실제 발생 시점(INV-23)
    occurred_window_start           # 정확히 모를 때의 범위
    occurred_window_end
    time_precision                  # EXACT | DAY | MONTH | APPROXIMATE | UNKNOWN
    observed_at                     # 사용자가 알려준 시점(≠ 발생 시점)
    source_fact_ids
    calibration_semantics_version   # §11-7 버전 있는 해소
    # 예측 비교·성숙도·revision 참조는 §14-5
```

#### 논리 키와 revision 집계 규칙

```python
logical_calibration_key = episode_id + track + target_stage + prediction_snapshot_id
record_revision: int
supersedes_record_id: str | None
```

> 동일 `logical_calibration_key`에서는 **supersede되지 않은 최신 유효 revision만** 품질 지표에 포함한다. 과거 revision은 **감사 이력으로 보존**하되 분모·분자에 **중복 포함하지 않는다.**

이 규칙이 없으면 사용자가 정정할 때 기존 레코드와 수정 레코드가 모두 집계된다.

### 14-2. `reach_status` — occurrence보다 앞선 게이트

해당 단계에 **도달했는지**를 먼저 구분한다. 이 게이트를 거치지 않으면 미도달이 실패로 오염된다.

```python
class ReachStatus(StrEnum):
    REACHED          # 해당 목표 단계에 진입함
    NOT_REACHED      # Episode가 종료됐으며 그 단계까지 가지 못함
    PENDING          # Episode가 진행 중이라 도달 여부를 확정할 수 없음
    NO_ATTEMPT       # 사용자가 적용 가능한 행동을 시도하지 않기로 함
    NOT_APPLICABLE   # 해당 Kind에는 단계 자체가 적용되지 않음
    UNKNOWN          # 현실 정보를 알 수 없음
```

`IN_PROGRESS`는 두지 않는다 — 축이 다르다. "면접에 도달했고 결과 대기 중"은 `reach_status=REACHED` + `outcome=ONGOING`이며, 목표가 오퍼 단계인데 면접 진행 중이면 `target_stage=OFFER_RECEIVED` + `reach_status=PENDING`이다.

> **진행 중이라는 이유만으로 `NOT_REACHED`를 기록하지 않는다.** `NOT_REACHED`는 해당 단계에 도달할 기회가 **사실상 종료된 경우에만** 확정한다(INV-21). 이 구분이 없으면 §15에서 진행 중 사례가 `false_stage_advance`의 거짓 음성으로 들어간다.

| 상황 | Exit 트랙 값 |
|---|---|
| 무직 취업(`JOB_GAIN_FROM_UNEMPLOYED`) | **`NOT_APPLICABLE`** (실패도 `NO_ATTEMPT`도 아님) |
| 재직자가 아직 오퍼 전이라 퇴사 검토 안 함 | **`PENDING`**(Episode 진행 중) / Episode 종료 시 `NOT_REACHED` |
| 오퍼를 받았으나 본인이 퇴사 통보를 하지 않기로 함 | **`NO_ATTEMPT`** |
| 내부 전보 | 외부 입사·퇴사 = **`NOT_APPLICABLE`** |

#### `reach_resolution_reason` — 왜 그 도달 상태인가

```python
class ReachResolutionReason(StrEnum):
    UPSTREAM_STAGE_CLOSED      # 앞 단계에서 Episode가 종료됨
    USER_DECLINED_ACTION
    COUNTERPARTY_ENDED
    WINDOW_EXPIRED
    KIND_NOT_APPLICABLE
    INSUFFICIENT_OBSERVATION
    STILL_OPEN
    UNKNOWN
```

**중복 실패 증폭 방지**: 서류에서 종료된 Episode의 오퍼·협상·입사 단계는 모두 `NOT_REACHED`가 되지만 원인은 하나(`UPSTREAM_STAGE_CLOSED`)다. 이를 각각 독립 실패로 세면 **하나의 종료 사건이 여러 거짓 음성으로 증폭**된다. 따라서 §15는 두 집계를 **함께** 보고한다.

```
stage-level micro metric     # 단계별 성능
episode-level macro metric   # Episode 하나 기준 성능
```

### 14-3. 4축의 소유 의미

#### Occurrence — 단계 사건 자체가 실제로 있었는가
```
CONFIRMED | DENIED | UNCLEAR
```
주로 `reach_status=REACHED`일 때 적용한다. **`NOT_REACHED`를 `DENIED`로 변환하지 않는다.**

#### Outcome — 도달한 단계가 어떤 결론으로 끝났는가
```
SUCCEEDED | COUNTERPARTY_ENDED | USER_WITHDREW | MUTUAL_BREAKDOWN
| ONGOING | NOT_APPLICABLE | UNKNOWN
```
**`DELAYED`는 Outcome이 아니다**(INV-22). 지연은 결말과 동시 성립하므로("협상은 지연됐지만 진행 중", "입사일 연기됐지만 결국 입사 성공") 별도 timing 축이 소유한다. 기존 엔진도 quality와 timing을 독립 축으로 보존하므로 여기서 다시 합치지 않는다.

#### Timing — 시간 지연 상태 (별도 축)
```python
class CalibrationTimingStatus(StrEnum):
    ON_TIME | DELAYED | RESCHEDULED | UNKNOWN | NOT_APPLICABLE
```
필드를 늘리지 않으려면 Episode·Track의 timing history를 참조해 파생해도 되나, **`outcome`에 `DELAYED`를 두지 않는다.**

#### Experience — 사용자가 그 과정을 어떻게 체감했는가
```
VERY_POSITIVE | POSITIVE | MIXED | NEGATIVE | VERY_NEGATIVE | UNKNOWN
```
사건이 성사돼도 경험은 부정적일 수 있다(입사 성공 + 연봉·업무 부담으로 체감 부정).

#### Settlement — 해당 단계 이후 현실적으로 안정됐는가
```
STABLE | CONDITIONAL | UNSTABLE | TOO_EARLY_TO_TELL | NOT_APPLICABLE | UNKNOWN
```
**`EARLY_EXIT`는 settlement 값이 아니다**(INV-22) — 조기 퇴사 **사건의 소유자는 lifecycle/Exit 트랙**이다. 권위 상태로 중복 저장하지 않고 아래처럼 표현하거나 Episode `close_reason=EARLY_EXIT`에서 파생한다.

```
settlement        = UNSTABLE
settlement_reason = EARLY_EXIT     # 또는 close_reason 참조로 파생
```

**모든 단계에 동일하게 묻지 않는다** — 주로 Entry·내부 배치 후반 단계에 적용한다.

### 14-4. `reach_status` × 4축 유효성 행렬

허용 조합을 고정하지 않으면 모순 레코드가 생긴다(`NOT_APPLICABLE`+`CONFIRMED`, `NO_ATTEMPT`+`COUNTERPARTY_ENDED`, `REACHED`+`DENIED` 등).

| reach_status | occurrence | outcome | experience | settlement |
|---|---|---|---|---|
| `REACHED` | 보통 `CONFIRMED` | 실제 상태 | 응답 가능 | 적용 단계만 |
| `PENDING` | `NOT_APPLICABLE` 또는 미확정 | `NOT_APPLICABLE` | 목표 단계 기준 N/A | N/A |
| `NOT_REACHED` | `NOT_APPLICABLE` | `NOT_APPLICABLE` | `NOT_APPLICABLE` | `NOT_APPLICABLE` |
| `NO_ATTEMPT` | `NOT_APPLICABLE` | `NOT_APPLICABLE` | 시도하지 않은 체감은 **별도 기록** | N/A |
| `NOT_APPLICABLE` | 전부 `NOT_APPLICABLE` | N/A | N/A | N/A |
| `UNKNOWN` | `UNKNOWN` 또는 미응답 | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` |

#### 미응답 · UNKNOWN · NOT_APPLICABLE 3분리

```
null / absent    = 질문하지 않았거나 답변이 없음(응답률 문제)
UNKNOWN          = 사용자가 실제로 모른다고 답함(현실 불확실성)
NOT_APPLICABLE   = 구조적으로 질문 대상이 아님
```

미응답을 `UNKNOWN`으로 자동 저장하면 **응답률과 현실 불확실성이 섞인다**. 이 행렬은 §14 규격이자 §13 fixture의 검증 계약(`invalid_calibration_combination`)이다.

### 14-5. 예측 스냅샷 · 관찰 성숙도 참조 (§15 연결)

현실 레이블만으로는 **어느 예측과 비교할지** 알 수 없다. 레코드 본체 또는 별도 envelope에 다음을 둔다.

```
prediction_snapshot_id       # 아래 불변 스냅샷
evaluation_window_status
```

#### 예측 스냅샷 불변성 (INV-23)

`prediction_snapshot_id`가 가리키는 스냅샷은 **불변**이며 최소한 생성 당시의 **모델 버전·계약 버전·대상 Episode·목표 단계·예측 기간·단계 벡터·병목값**을 보존한다. **현재 모델로 재계산한 값을 과거 예측처럼 사용하지 않는다.**

#### 발생 시점 ≠ 관찰 시점 (INV-23)

`stage_timing_error`는 **실제 발생 시점**으로 계산한다. `observed_at`(사용자가 알려준 시점)으로 대체하지 않는다.

```
실제 오퍼 수령 2027-04-03 → stage_occurred_at
사용자가 알림   2027-05-10 → observed_at
```

정확히 모르면 `occurred_window_start`/`occurred_window_end` + `time_precision`(EXACT/DAY/MONTH/APPROXIMATE/UNKNOWN)으로 범위와 정밀도를 표현한다.

#### 관찰 성숙도

```python
class EvaluationWindowStatus(StrEnum):
    OPEN             # 아직 결과를 평가하기 이름
    MATURED          # 예측 기간이 끝나 평가 가능
    RIGHT_CENSORED   # 추적 종료·사용자 이탈로 끝까지 관찰하지 못함
    CANCELLED        # 예측 대상 자체가 무효화됨(아래 한정)
```

**성숙도 적용 범위는 지표 종류별로 다르다**(INV-21):

| 지표 부류 | 성숙도 규칙 |
|---|---|
| **안전·상태 무결성 지표** (false_stage_advance, completion_overclaim, counterparty_overclaim, forecast_to_confirmed_mutation, episode_collision, track_conflation, double_contribution, atomic_promotion_partial_commit) | **성숙을 기다리지 않고 모든 적용 가능한 shadow 실행에서 즉시 측정.** 예측 기간이 `OPEN`이어도 forecast가 confirmed를 변경했다면 **즉시 오류** |
| **모델 품질 지표** (stage_precision/recall, stage_timing_error, bottleneck_rank_agreement, settlement_prediction_alignment) | **확정 분모는 `MATURED`만.** `PENDING`·`OPEN`·`RIGHT_CENSORED`·`NOT_APPLICABLE`을 **실패로 계산하지 않음** |

`RIGHT_CENSORED`는 실패가 아니지만 **검열 비율을 반드시 별도 보고**한다 — 검열이 과도하면 정확도가 좋아 보이는 착시가 생긴다.

#### `CANCELLED` 한정

```
허용: 중복 예측 제거 / Episode 대상 해소 오류 / 사용자 정정으로 예측 대상 자체 무효화
      / 내부 시스템 계약 오류로 평가 불가능
금지: 사용자 지원 철회 / 회사 전형 종료 / 오퍼 거절 / 협상 결렬
```

후자는 **관찰된 현실 Outcome**이므로 `MATURED` 상태에서 `USER_WITHDREW`·`COUNTERPARTY_ENDED`·`MUTUAL_BREAKDOWN`으로 기록한다.

캘리브레이션 정정은 기존 레코드를 덮어쓰지 않고 `record_revision`+`supersedes_record_id`로 **이력을 보존**한다(§13 사실 정정 모델과 일관, 집계 규칙은 §14-1).

### 14-6. 필수 음성 사례 (구분 회귀)

| # | 구분해야 할 것 |
|---|---|
| 1 | 지원하지 않음 ≠ 지원 실패 |
| 2 | 면접 단계 미도달 ≠ 면접 탈락 |
| 3 | 오퍼를 거절함(`USER_WITHDREW`) ≠ 회사가 철회함(`COUNTERPARTY_ENDED`) |
| 4 | 입사 성공 + 체감 부정 **허용** |
| 5 | 입사 성공 + 조기 퇴사(`EARLY_EXIT`) **허용** |
| 6 | 퇴사 완료 + 새 회사 미입사 → Exit 발생, Entry `NOT_REACHED` |
| 7 | 무직 취업 → Exit `NOT_APPLICABLE` |
| 8 | 내부 전보 → 외부 입사·퇴사 `NOT_APPLICABLE` |
| 9 | 진행 중인 협상을 실패로 **조기 확정하지 않음**(`ONGOING`) |
| 10 | **사용자 모름(`UNKNOWN`)과 엔진 무신호(`no_signal`)를 같은 값으로 저장하지 않음** |

### 14-7. 캘리브레이션과 규칙 변경의 경계

**현실 캘리브레이션 데이터가 곧바로 명리 규칙을 변경하지 않는다.**

```
사용자 피드백 → 현실 레이블 저장 → 집계·감수 자료
→ 규칙 단위 분석 → 전문가 검토 → 별도 버전에서 조정
```

한 사용자의 "면접은 됐지만 힘들었다"를 근거로 `favorability`나 특정 evidence contract를 **즉시 바꾸지 않는다**. 발생(occurrence)과 경험(experience)을 분리한 이유가 여기에 있다. 규칙 조정은 부록 B의 `EvidenceReviewStatus` 경로를 거친다.

---

## §15. shadow 지표

### 15-0. 공통 envelope — 지표 분류와 관측 종류를 분리

**rollout 텔레메트리·감사 이벤트를 지표 3분류에 억지로 넣지 않는다.** 오류 발생과 안전장치의 정상 작동을 혼동하지 않기 위해 `observation_kind`·`guard_outcome`을 분리한다(INV-24).

```python
class MetricClass(StrEnum):
    SAFETY_OVERCLAIM | STATE_INTEGRITY | MODEL_QUALITY

class ObservationKind(StrEnum):
    METRIC_MEASUREMENT | ROLLOUT_TELEMETRY | AUDIT_EVENT

class GuardOutcome(StrEnum):
    NOT_APPLICABLE | ALLOWED | BLOCKED | ROLLED_BACK | VIOLATION
```

```
envelope:
  observation_id                        # 안정 생성 시 기본 멱등 키
  metric_name | metric_class | observation_kind
  guard_outcome | expected_guard_outcome
  observation_context                   # 아래 enum
  episode_id_hash | track | stage
  contract_version | model_version | resolution_source
  run_id | request_id | build_sha | config_snapshot_hash | input_digest
  observed_at
  audit_event | denominator_eligibility
```

```python
class ObservationContext(StrEnum):
    FIXTURE | GOLDEN_CORPUS | SHADOW_TRAFFIC | CANARY | BETA | LIVE
```

**의도된 fixture와 실제 트래픽 결함을 구분**하기 위해 `observation_context`·`expected_guard_outcome`이 필요하다.

```
context=FIXTURE, expected=BLOCKED, actual=BLOCKED           → 정상 통과
context=SHADOW_TRAFFIC, expected=ALLOWED, actual=BLOCKED    → 안전장치는 성공했으나
                                                              rollout 데이터 계약 결함
```

**중복 제거 키**(재시도·중복 전송 시 지표 이중 증가 방지):

```
observation_id                     # 안정적이면 이것을 기본 멱등 키로
(대체) metric_name + run_id + 대상 episode/track/stage + contract_version + audit_event
```

예: `legacy_ambiguous_fallback`은 구 데이터에서 예상되는 **관측값**이지 곧바로 오류가 아니다 / `dual_consume_blocked`는 **가드가 막은 사건**일 수 있다 / `TRANSACTION_ROLLED_BACK`은 원자성 **보호가 작동**했다는 감사 이벤트다 / `INVALID_MISMATCH`는 fail-closed 정상 작동과 실제 데이터 계약 오류를 구분해야 한다.

### 15-1. 지표 계약 · 계측 커버리지 (INV-25)

```
metric_name | metric_class | definition | numerator | denominator
| exclusions | grouping_dimensions | threshold | promotion_blocking | audit_event
```

**"오류 0"이 아니라 "전수 측정 후 오류 0"이어야 한다.** `violation_count=0`만으로는 계측 누락과 실제 무오류를 구분하지 못한다(`measured_count=0`은 통과가 아니라 **측정 실패**).

```python
class MetricMeasurementStatus(StrEnum):
    ACTIVE | NOT_MEASURABLE_YET | INSUFFICIENT_COVERAGE
    | INSUFFICIENT_SAMPLE | NO_ELIGIBLE_CASES | DEGRADED
```

지표 결과에 필수 포함:

```
eligible_count | measured_count | excluded_count | coverage_rate | measurement_status
```

**계산식과 경계 판정** (적용 대상 0건 ≠ 측정 실패):

```
total_observed_count = eligible_count + excluded_count
coverage_rate        = measured_count / eligible_count      # eligible_count > 0 일 때만 정의
```

| 조건 | 판정 |
|---|---|
| `eligible > 0`, `measured = 0` | **계측 실패 — 승격 차단** |
| `eligible > measured` | **불완전 계측 — 승격 차단** |
| `eligible = measured > 0` | **census 충족** |
| `eligible = 0` | 통과가 아니라 **`NO_ELIGIBLE_CASES`**(또는 `INSUFFICIENT_SAMPLE`) |

최소 표본이 필요한 품질 지표와 Kind별 보고에도 같은 원칙을 적용한다.

**승격 규칙 (안전·무결성 지표)**

```
measurement_status = ACTIVE
AND measured_count = eligible_count
AND violation_count = 0
```

안전·무결성 지표는 **표본 추출이 아니라 적용 가능한 실행 전수 계측**이 원칙이다. **명시된 sampling은 모델 품질 지표에만** 허용한다.

**`narrative_completion_overclaim` phase별 필수성**

```
§12 미배선 단계     → NOT_MEASURABLE_YET 허용
§12 배선 후 BETA/LIVE → NOT_MEASURABLE_YET 이면 승격 차단
```

### 15-2. 안전·과장 오류 (`SAFETY_OVERCLAIM`, 0 허용)

성숙을 기다리지 않고 **모든 적용 가능한 shadow 실행에서 즉시 측정**한다(INV-21).

| 지표 | 정의(좁힘) |
|---|---|
| `false_stage_advance` | **사용자 사실 또는 허용된 현실 증거 없이** 권위 `current_confirmed_stage`가 전진한 건수. 예측이 오퍼를 높게 봤으나 실제 오퍼가 없었던 것은 **이 지표가 아니라 `stage_precision`** 문제다 |
| `completion_overclaim` | 2층 측정: **`structured_completion_overclaim`**(구조 데이터가 실제 완료로 잘못 승격) / **`narrative_completion_overclaim`**(구조는 안전하나 LLM이 "성사된다·확정됐다"로 표현). 후자는 §12 소비 배선 이후 측정 가능 → 초기 `NOT_MEASURABLE_YET` 허용 |
| `counterparty_overclaim` | 회사 관심 추정 / 합격·채용 의사를 숨은 상태로 계산 / 연락·면접 분위기를 오퍼 의향으로 승격 / 명리 신호를 회사 행동으로 서술. **사용자가 밝힌 "서면 오퍼를 받았다"를 출력하는 것은 오류 아님** |
| `forecast_to_confirmed_mutation` | **forecast 저장·계산 경로가 authoritative fact/state를 변경**한 건수 |

**`forecast_to_confirmed_mutation`(원인) vs `false_stage_advance`(결과)**: 한 사건이 두 지표에 모두 잡힐 수 있다. 중복 집계 자체는 허용하되 **대시보드 총 오류를 단순 합산하지 않는다.**

### 15-3. 상태 무결성 오류 (`STATE_INTEGRITY`, 0 허용)

| 지표 | 계약 |
|---|---|
| `episode_collision` | 2분할: **`fact_episode_collision`**(A사 사실이 B사 Episode에 기록) / **`forecast_episode_collision`**(A사 예측 근거가 B사 후보에 합산) |
| `track_conflation` | 퇴사 완료를 이직 완료로 오인하는 등 트랙 혼동 |
| `employment_context_partial_commit` | 고용 컨텍스트 승격 중간 실패로 반쪽 상태 잔존(INV-17). *구 명칭 `atomic_promotion_partial_commit`은 승진(promotion) 이벤트와 혼동되어 사용하지 않는다* |
| `duplicate_fact_application` | 동일 `idempotency_key` 재적용 |
| `invalid_calibration_combination` | §14-4 유효성 행렬 위반 |
| `double_contribution` | 아래 중복 식별 키 기준 |
| `shadow_output_drift` | shadow 경로 활성화 **전후 기존 권위 출력 차이**(아래 phase별 범위) |
| `prediction_snapshot_mutation` | 과거 스냅샷의 `model_version`·`contract_version`·`target_stage`·`forecast_window`·`stage_vector`·`bottleneck` 중 **생성 후 변경**(INV-23 위반) |
| `superseded_revision_included` | supersede된 calibration revision이 **분자·분모에 포함**된 건수(§14-1) |

#### `shadow_output_drift` 검사 대상과 phase별 범위

```
검사 대상: score · raw_score · activation · favorability · confidence
          · ranking · legacy_serialized_category · 기존 EventCandidateV2 직렬화
```

| Phase | 불변 범위 |
|---|---|
| P0-B | 엔진·직렬화 불변 |
| P1~P3 | 기존 점수·랭킹·권위 상태 불변 |
| §12 소비 배선 전 | LLM·리포트 **입력** 불변 |
| §12 beta 배선 후 | **허용된 신규 블록 외** 기존 본문·필드 불변 |

`double_contribution` 중복 식별 키(§10 연결):

```
prediction_snapshot_id + candidate_id + period + evidence_id
+ target.axis_or_stage + contribution_role
```

- **허용**: 같은 `signal_ref`가 **서로 다른 검토된 `evidence_id`**를 통해 **서로 다른 축**에 기여.
- **위반**: 같은 `evidence_id`가 같은 축에 중복 가산 / legacy 점수와 신규 adapter 점수 동시 가산 / `process_activation` **파생값이 다시 원천 기여값으로 합산**.

### 15-4. 모델·품질 지표 (`MODEL_QUALITY`, 임계는 사후 승인)

확정 분모는 `MATURED`만(INV-21). 지표별 분모를 각각 고정한다.

| 지표 | 기본 분모 |
|---|---|
| `stage_reach_precision` | 특정 단계를 예측했고 `MATURED`된 대상 |
| `stage_reach_recall` | 현실에서 해당 단계가 확인되고 **대응 스냅샷이 있는** 대상 |
| `stage_timing_error` | `REACHED`이고 **발생 시점 정밀도가 허용 수준 이상**인 대상 |
| `bottleneck_rank_agreement` | 비교 가능한 단계가 **2개 이상**이며 현실 진행 순서가 해소된 Episode |
| `settlement_prediction_alignment` | Settlement 적용 단계이며 충분한 관찰 기간이 지난 대상 |

`stage_precision`/`stage_recall` 대신 **`stage_reach_precision`/`stage_reach_recall`** 을 쓴다 — 현실 단계 상태 자체가 아니라 **도달 예측**의 정확도임을 명확히 한다.

**분모에서 반드시 제외**: `NOT_APPLICABLE` · `PENDING` · `OPEN` · `RIGHT_CENSORED` · superseded revision · 대상 Episode 미해소.

**`NO_ATTEMPT`는 별도 보고**한다 — 모델이 무엇을 예측하도록 설계됐는지에 따라 다르며, **사용자 행동이 없어서 진행되지 않은 사례를 모델 거짓 음성으로 자동 계산하지 않는다.**

`time_precision=UNKNOWN`이나 지나치게 넓은 기간 범위는 `stage_timing_error`에서 **제외하되 제외율을 별도 보고**한다. `RIGHT_CENSORED` 비율도 별도 보고한다(§14-5).

**품질 결과 필수 필드** (점 추정치만으로 보고하지 않는다):

```
sample_count | confidence_interval | excluded_count_by_reason
| right_censored_rate | unknown_time_precision_rate
```

**임계값은 P0-A에서 확정하지 않는다**: shadow baseline 관측 → 분포 확인 → 전문가 감수 표본과 비교 → 임계 제안 → **별도 승인**. 임계는 **최소 표본 수를 충족한 Kind에서만** 제안한다 — 표본이 없는 `RESIGNATION_ONLY`·`INTERNAL_TRANSFER`를 전체 평균으로 숨기지 않는다.

### 15-5. micro / macro 집계와 Kind 층화

```
micro: 모든 평가 가능 Stage 레코드를 동일 가중
macro: Episode별로 먼저 집계한 뒤 Episode를 동일 가중
```

두 집계를 **명시적으로 분리 보고**한다(§14-2 `UPSTREAM_STAGE_CLOSED`로 인한 연쇄 미도달이 거짓 음성으로 증폭되지 않도록).

추가로 **Kind별 층화**가 필요하다 — 전체 평균만 보면 표본이 많은 외부 이직이 나머지 Kind의 결함을 가린다.

```
EXTERNAL_MOVE | JOB_GAIN_FROM_UNEMPLOYED | RESIGNATION_ONLY | INTERNAL_TRANSFER
```

### 15-6. 승격 차단 규칙 (0 허용 지표)

```
현재 candidate build의 적용 가능 실행에서 violation_count > 0
→ BETA/LIVE 승격 차단
→ 관련 run_id·fixture_id·audit_event 첨부
→ 수정 → 전체 fixture + shadow corpus 재측정
→ 0 확인 후에만 해제
```

**정상 가드 작동을 violation으로 세지 않는다**(INV-24):

```
guard_outcome ∈ {BLOCKED, ROLLED_BACK} + authoritative state 불변  → 보호 성공(위반 아님)
guard_outcome = VIOLATION  또는  차단 뒤에도 권위 상태 변경        → 오류
```

#### 두 종류의 차단 분리

정상 차단이라도 shadow corpus에서 **반복**되면(`dual_consume_blocked`·`INVALID_MISMATCH`·`TRANSACTION_ROLLED_BACK`·`legacy_ambiguous_fallback`) 사용자 안전은 지켰어도 그 버전은 **배포 준비가 되지 않은 상태**다.

```
safety_violation_blocking   : violation_count > 0            → 즉시 차단
rollout_readiness_blocking  : guard activation rate 임계 초과 → 원인 해소 전 승격 차단
```

| 관측 | 안전 위반 | rollout 준비 |
|---|---|---|
| 가드가 forecast→confirmed를 차단 | 아니오 | 낮은 빈도면 정상 |
| **모든 요청**에서 dual consume 차단 | 아니오 | **준비 미완료** |
| 권위 상태가 실제 변경됨 | **예** | 즉시 차단 |
| production shadow에서 canonical mismatch | 안전장치 성공 | **원인 해소 전 승격 차단** |
| 의도된 음성 fixture가 mismatch를 차단 | 아니오 | 정상 |

guard activation rate의 **임계값 자체는 §16에서** 정하되, **측정·차단 가능성은 §15에서 예약**한다.

---

## §16. rollout · 승격 로드맵

### 16-0. 단계 정의

각 단계는 아래 7속성을 갖는다: `entry_conditions` · `implementation_scope` · `required_fixtures` · `required_metrics` · `exit_conditions` · `rollback_target` · `user_visible_change`.

| 단계 | implementation_scope | user_visible_change | rollback_target |
|---|---|---|---|
| **P0-A** | 문서·감사 계약 확정, **코드 변경 0** | 없음 | — |
| **P0-B** | 저장소·adapter·shadow side-channel 스캐폴딩 | 없음 | P0-A |
| **P1** | 상태 머신·Episode·전이 그래프 shadow | 없음 | P0-B |
| **P2** | 단계 벡터·병목·support/blocker shadow | 없음 | P1 |
| **P3** | 사용자 사실 상속·resolver shadow | 없음 | P2 |
| **P4** | chat/report 소비 **beta** | 신규 블록 제한 노출 | P3(블록 suppress) |
| **P5** | 캘리브레이션·감수·**제한적 live** | 승인 surface | P4 |

단계별 요건 요약:

- **P0-A** — entry: 없음 / fixtures: 없음(계약만) / metrics: 없음 / exit: §0~§17·부록 확정 + 코드 변경 0 확인
- **P0-B** — entry: P0-A 완료 / fixtures: §13-1 의미 해소 + `expected_unchanged` / metrics: `shadow_output_drift=0` / exit: 엔진·직렬화 불변 확인
- **P1** — entry: P0-B exit / fixtures: §13-3 상태 머신 + §13-4 수명주기 / metrics: `episode_collision`·`employment_context_partial_commit`·`duplicate_fact_application`=0 / exit: 전이 그래프 census 충족
- **P2** — entry: P1 exit / fixtures: §13-2 cap 조합 / metrics: `double_contribution`=0 / exit: 기여값 감사 통과
- **P3** — entry: P2 exit / fixtures: §13-5 안전 회귀 / metrics: `false_stage_advance`·`forecast_to_confirmed_mutation`=0 / exit: 사실/예측 분리 census
- **P4** — entry: P3 exit + 관련 evidence `EXPERT_REVIEWED`+`BETA` / fixtures: §12 소비 계약 / metrics: `narrative_completion_overclaim`=**ACTIVE** + counterparty/completion overclaim=0 / exit: cohort별 게이트 통과
- **P5** — entry: P4 exit + 품질 임계 별도 승인 / fixtures: 전체 / metrics: 전체 + Kind별 표본 / exit: 승인된 surface 한정 live

### 16-1. 승격 게이트

**안전·무결성은 절대 게이트**다.

```
measurement_status = ACTIVE
measured_count = eligible_count
violation_count = 0
shadow_output_drift = 0
prediction_snapshot_mutation = 0
superseded_revision_included = 0
```

`NO_ELIGIBLE_CASES`는 **통과가 아니라 해당 cohort에 대한 증거 부재**로 기록한다.

**모델 품질 지표는 P0-A에서 임계값을 확정하지 않는다**:

```
baseline 관측 → 표본 수·CI 확인 → Kind별 분포
→ 전문가 감수 표본 비교 → 임계 제안 → 별도 승인
```

### 16-2. guard activation rate

```
guard_activation_rate
= 비정상 또는 억제 guard가 작동한 eligible user-facing run
  / 전체 eligible user-facing run
```

**분모 제외**: 의도된 음성 fixture · 내부 golden corpus의 expected BLOCK · `SHADOW` 내부 관측만 수행한 실행 · feature flag OFF · 구조적으로 신규 블록이 적용되지 않는 질문 · 중복 재시도 관측.

**분자는 원인별로 분해**한다:

```
pre_input_block_rate | rewrite_rate | safe_fallback_rate | final_block_rate
| episode_unresolved_rate | invalid_mismatch_rate
| dual_consume_block_rate | transaction_rollback_rate
```

정상 차단이라도 빈도가 승인 임계를 넘으면 `rollout_readiness_blocking = true`(§15-6). **수치 임계는 여기서 확정하지 않는다 — `TBD_BY_SHADOW_BASELINE`.**

### 16-3. 단계별 노출 범위

| 단계 | 권위 상태 변경 | 사용자 LLM 입력 | 최종 응답 | 캘리브레이션 |
|---|---|---|---|---|
| P0-B~P3 | **금지** | **금지** | 변화 없음 | 저장 금지 또는 내부 fixture만 |
| P4 canary | 사용자 사실만 허용 | allowlist만 | 신규 블록 제한 노출 | 별도 beta namespace |
| P4 beta | 허용된 cohort | beta visibility 통과분 | chat/report만 | revision 보존 |
| P5 live | 승인된 계약만 | live visibility | 승인 surface | 정식 집계 |

**`daily`는 모든 단계에서 미배선 고정**(INV-14).

### 16-4. cohort와 확대 순서

한 번에 전체 질문 유형을 열지 않는다.

```
1. GENERAL_CAREER, 단일 본인, 단일 Episode
2. EPISODE_SPECIFIC_RESOLVED, 단일 Episode
3. 복수 Episode 일반 질문
4. 퇴사 단독 · 무직 취업 · 내부 전보
5. report 노출
6. 복수 Episode 상세 · 후속 대화
```

`EPISODE_SPECIFIC_UNRESOLVED`는 **기능 확대 cohort가 아니라 항상 안전 분기**다.

**Kind별 표본이 확보되지 않은 상태에서 외부 이직 결과만으로 무직 취업·퇴사 단독·내부 전보까지 승격하지 않는다.**

### 16-5. 실패 · 롤백

```
안전 violation > 0
→ 즉시 신규 노출 중단 → legacy 경로 유지
→ 신규 authoritative write 차단 → 관련 build/config cohort 격리
```

rollout readiness 문제는 서비스를 멈추지 않는다:

```
사용자 응답은 fail-closed / 서비스 전체는 계속 운영
/ 신규 Career Transition 블록만 suppress
```

**롤백 시에도 보존**: 감사 이벤트 · prediction snapshot · calibration revision · guard 원인 · build/config hash. 단 **이 자료를 이후 사용자 응답에 재사용하지 않는다.**

### 16-6. 승인 권한 (INV-30)

다음 승격은 **자동화하지 않는다**:

```
SHADOW → BETA
BETA → LIVE
SOURCE_DOCUMENTED → EXPERT_REVIEWED
품질 임계값 최초 승인·변경
```

각각 **승인자 · 증거 패키지 · 승인 시점의 `build_sha`·`contract_version`·`config_snapshot_hash`** 를 기록한다.

### 16-7. 완료 정의

**P0-A 완료와 기능 출시를 구분한다.**

```
P0-A 완료 : SSOT·감사·fixture·calibration·metric·consumer·rollout 계약 완결
            + 코드 변경 0
기능 완료 : P0-B~P5 구현과 각 승격 게이트 통과
```

이 구분이 없으면 문서 완료 커밋이 **기능 출시 준비 완료로 오해**될 수 있다.

---

## §17 및 부록 A — 후속 작성 단위

```
§17 재사용 경계표 → 부록 A 감사 결과 본문화 → P0-A 완료 커밋
```

- §17 재사용 3등급(①그대로 보존 ②어댑터 뒤 재사용 ③의미 재검증 후 재사용) · 부록 A 어휘·런타임 감사 결과(2026-07-25, SHA dbae796).

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
