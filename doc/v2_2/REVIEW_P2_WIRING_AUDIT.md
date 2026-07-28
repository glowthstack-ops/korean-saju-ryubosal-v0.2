# P2-3a — 운영 경로 배선 감사

> 상태: **배선 완료** · 기록일 2026-07-27 · 갱신 2026-07-28
>
> 선행: `00732ef`(P2-2c). 아래 §1~§10은 **배선 전 감사 기록**이며, 실사에서 전제 두
> 가지가 틀린 것으로 확인됐다. 확정 판정과 정정은 **§11**을 먼저 읽을 것.

## 0. 결론 먼저

```
커리어 Episode가 build_llm_input보다 450줄 뒤에서 읽힌다.
→ 후보 축소가 이미 끝난 뒤라 P2 scope를 붙일 수 없다.
```

지적하신 실패 유형(**Episode가 너무 늦게 읽힘**)이 코드에 그대로 있다. 게이트 수식이
아니라 이 순서가 P2-3의 실제 위험이다.

---

## 1. 현행 호출 순서 (`chat_service.chat`, 2997행~)

```
3314  subject_id 확정          (동반자 분기)
3505~ candidates 생성          score_legacy_personalized → 도메인 필터 → 지평 필터
3979  build_llm_input(...)     ← 내부에서 reduce_candidates 실행 · Top-N 확정
4433  _prepare_career_transition_block(question, thread_id, subject_id,
                                        candidates=candidates)
                                ← 여기서 처음 career Episode를 읽는다
```

`subject_id`와 `candidates`는 충분히 앞서 있어 문제가 없다. **문제는 Episode 하나다.**

```
필요한 순서   Episode 읽기 → process context → scope → 후보 축소
현재 순서     후보 축소 → Episode 읽기
```

---

## 2. 후보 축소 지점 — 단일하다

`chat_service`는 `reduce_candidates`를 직접 호출하지 않는다. `build_llm_input`(3979)
한 곳만 부르고, 축소는 그 안에서 일어난다.

```
build_llm_input()
  → reduce_with_context() 또는 select_overview_candidates()
  → _to_llm_candidate()
```

**축소 진입점이 하나라 배선 지점도 하나다.** 여섯 경로가 서로 다른 reducer를 쓰는
상황은 아니다 — 이건 다행이다.

### 리포트는 별개 경로다

`report_service`는 `reduce_candidates` · `build_llm_input`을 쓰지 않는다(참조 0건).
따라서 **공용 reducer를 통한 의도치 않은 리포트 영향은 없다.** D2 사이클의 독립성이
구조적으로 보장된다. surface guard를 따로 만들 필요가 없다.

---

## 3. Episode 조회 구조

```python
_prepare_career_transition_block(
    question, thread_id=thread_id, subject_id=subject_id, candidates=candidates
)
  → career_chat_consumer.CAREER_TRANSITION_CHAT_ENABLED  (플래그)
  → _career_shadow_repository().load(thread_id, subject_id)
  → career_chat_consumer.prepare_career_chat_block(...)
```

두 가지가 걸린다.

```
① 플래그 종속
   CAREER_TRANSITION_CHAT_ENABLED가 OFF면 Episode를 아예 읽지 않는다.
   P2가 이 플래그에 종속되면 "커리어 게이트가 이 플래그 상태에 따라 켜졌다 꺼졌다"가 된다.

② 저장소 조회 시점
   load()가 여기서만 호출된다. P2가 후보마다 다시 조회하면 요청당 N회 I/O가 된다.
```

---

## 4. 제안 배선안

### 4-1. 요청당 1회 process context를 앞으로 끌어올린다

```python
@dataclass(frozen=True)
class RequestProcessContext:
    subject_id: str | None
    resolved_facts: tuple[ProcessFact, ...]
    source_status: ProcessCoverage   # 정상 or SOURCE_UNAVAILABLE
```

생성 위치는 **`candidates` 확정 직후 · `build_llm_input` 직전**이다.

```
3505~ candidates 생성
      ↓ (신규) build_request_process_context(...)   ← 여기
3979  build_llm_input(..., process_context=ctx)
4433  _prepare_career_transition_block(...)          ← 기존 유지(직교)
```

후보별로 저장소를 다시 조회하지 않는다 — 모든 후보가 같은 context를 읽는다.

### 4-2. Episode 조회를 P2가 독립적으로 한다

`_prepare_career_transition_block`을 앞으로 옮기지 않는다. 그 함수는 LLM 지시문
생성이 책임이고 자체 플래그를 갖는다 — 옮기면 그 기능의 동작 순서가 바뀐다.

대신 P2가 같은 저장소를 **직접 한 번** 읽는다.

```python
repo = _career_shadow_repository()
loaded = repo.load(thread_id, subject_id)   # 실패 시 SOURCE_UNAVAILABLE
snapshots = [build_career_process_snapshot(ep) for ep in loaded.episodes]
```

```
장점  CAREER_TRANSITION_CHAT_ENABLED와 독립 — P2 게이트가 남의 플래그에 흔들리지 않는다
비용  같은 요청에서 저장소를 최대 2회 읽는다(지시문용 1 + P2용 1)
      → 요청 스코프 캐시로 1회로 줄일 수 있으나, 이번엔 정확성을 우선하고
        중복 조회는 계측 후 판단한다
```

⚠ `load()` 실패를 예외로 흘리지 않는다. `ProcessCoverage.SOURCE_UNAVAILABLE`로
바꿔 **"사실 없음"이 아니라 "읽지 못함"으로 전달**한다.

### 4-3. scope는 축소 **전에** 붙인다

```python
# build_llm_input 내부, reduce_candidates 호출 직전
for c in candidates:
    c.process_scope = resolve_candidate_scope(
        c.candidate_source_layers, c.event_key,
        facts=ctx.resolved_facts, subject_id=ctx.subject_id,
        coverage_override=ctx.source_status,
    )
```

Top-N을 뽑은 뒤 붙이면 이미 탈락한 후보를 교정할 수 없다.

---

## 5. 미해결 — "단기 안내에 남긴다"의 실제 채널

지적하신 항목을 확인했다. **현재 별도 단기 신호 채널이 없다.**

```
있는 것   event_candidates (주요 사건 목록)
          out_of_range 참고 후보 (배경 맥락 전용)
          date_selection 블록 (택일 전용)
없는 것   단기 접촉·조정·마찰 전용 채널
```

따라서 P2-3 첫 릴리즈에서는 정직하게 이렇게 기록해야 한다.

```
LOCAL_TRIGGER_ONLY
  → 주요 사건 Top-N 제외
  → 단기 안내 전달은 미구현
  → 감사 데이터에만 보존
```

새 사용자 섹션 추가는 UX 변경이라 별도 사이클로 분리한다. "제외했지만 단기 안내로
살아 있다"고 쓰면 사실과 다르다.

---

## 6. 여섯 경로 초기 동작 (배선 후 예상)

| 경로 | P2-3 초기 |
|---|---|
| 이직 | career AUTHORITATIVE — 게이트 적용 |
| 연애·결혼 | UNSUPPORTED — legacy bypass |
| 계약·대출·이사 | move active만 trigger, 나머지 bypass |
| 재물 변화 | 대부분 bypass |
| 열린 사건 날짜 | 호환 active가 있을 때만 trigger |
| 일반 길일 | 진행 과정 없음 → career 키는 local-only, 그 외 bypass |

열린 사건 날짜와 일반 길일이 갈리는 지점:

```
"이미 면접을 봤고 결과 발표일 중 어떤 날이 나을까"
  → CAREER_OPPORTUNITY/RESULT_PENDING active → JOB_GAIN trigger 허용

"그냥 취업하기 좋은 날 알려줘"
  → 진행 과정 없음 → career는 AUTHORITATIVE → ENFORCE_LOCAL_ONLY
```

---

## 7. baseline 확보 범위

배선 전에 고정한다.

```
후보 event_key · period · raw score · effective score
confidence · grade · rank · Top-N membership
최종 LLM candidate 순서
```

fixture:

```
PROV-3 12명식
커리어 Episode 없음 / 외부 면접 / 내부 승진 / 퇴사 통보 / 입사·온보딩
이사 결정 사실 있음 / 없음
대출·연애·선발 (unsupported)
저장소 장애
긍정 MINOR / 부정 MINOR
```

---

## 8. 슬라이스 분할

```
P2-3a  배선 + baseline        출력 불변
P2-3b  실제 reducer dual-run   legacy 반환, scoped는 감사 전용
P2-3c  플래그 ON               Top-N membership 변경 허용
P2-4   −6 제거                 confidence 강등은 유지
```

---

## 9. 확정이 필요한 것

```
1. Episode를 P2가 독립 조회할지(§4-2 제안) vs
   _prepare_career_transition_block을 앞으로 옮길지
   → 후자는 기존 기능의 동작 순서를 바꾼다

2. CAREER_TRANSITION_CHAT_ENABLED가 OFF일 때 P2 커리어 게이트를 어떻게 할지
   → 독립 조회면 게이트는 계속 동작한다. 이게 맞는지 확인 필요

3. 저장소 2회 조회를 허용할지, 요청 스코프 캐시를 이번에 만들지

4. "단기 안내 미구현"을 그대로 두고 P2-3을 진행할지
   → LOCAL_TRIGGER_ONLY 후보는 당분간 사용자에게 아예 안 보인다
```

특히 4번이 사용자 영향이 크다. 이직 질문에서 minor-only 후보가 Top-N에서 빠지면
**그 후보는 어디에도 나타나지 않는다.**

---

## 10. 관련 코드

- `chat_service.chat` 2997행 — `subject_id` 3314 · `candidates` 3505~ ·
  `build_llm_input` 3979 · `_prepare_career_transition_block` 4433
- `chat_service._career_shadow_repository` 4698 · `_prepare_career_transition_block` 4713
- `context_reducer.build_llm_input` — 유일한 축소 진입점
- `report_service` — `reduce_candidates`·`build_llm_input` 미사용(D2 독립성 확보)
- `process_event_compatibility.resolve_candidate_scope` — 배선 대상

---

# 11. 실사 정정과 확정 판정 (2026-07-28)

§1~§10을 실제 타입·producer 기준으로 검증한 결과 **전제 두 가지가 틀렸다.** 아래가
정정된 사실이며, 데굴님 확정 계약을 함께 기록한다.

## 11-0. 감사 계약 9항목 실사 결과

| 항목 | 실사 결과 |
|---|---|
| stage SSOT | **2축** — `frontier_stage`(진행 위치, 미관찰 단계로도 전진) vs `observed_stages[-1]`(=`current_confirmed_stage`, 확인 사실). 물리 원본은 `career_journal`(append-only), `stage_history`는 투영 |
| 목록 조회 API | `repository.load(thread_id, subject_id) -> LoadedShadowState`, `.store.episodes: tuple`. 정렬 = journal replay 순서 |
| 트랙별 다중 Episode | 다중 가능. **Episode는 `opportunity`·`entry` 2트랙만 소유** |
| terminal 포함 | 포함(제거 안 함). `lifecycle_status=CLOSED`로 남음 |
| episode_id 고유 범위 | store 스코프(`thread_id:subject_id`) 내 유일. **전역 유일 아님** → 감사 ID는 scope 포함 |
| EntryScope 저장 위치 | `CareerTransitionEpisode.entry_scope` — **Episode 필드**(TrackState 아님) |
| OBSERVABLE_HARD_FACT 판정 필드 | **필드가 없다.** command 레벨 게이트(`career_transition_reducer._plan_fact`)에서 거부되고 저장되지 않음 → `observed_stages`에 있다는 것이 구조적 통과 증거 |
| 현재성·종료성 | **4필드 분산** — `lifecycle_status` + `close_reason` + `Episode.outcome` + `realization_status` |
| 실패 vs 빈 결과 | 빈 결과 = `LoadedShadowState(빈 store, revision=0)`. 실패 = **psycopg 예외 전파**. **제3 상태 `contract_mismatch=True`** 존재 |

## 11-1. F1 — `entry_scope` producer가 0개다

`entry_scope`를 쓰는 곳은 선언 1줄뿐이고 reducer·parser·command 어디도 채우지 않아
**항상 `None`**이다. 그런데 매칭은 fail-closed라 `CAREER_EXTERNAL_OPPORTUNITY`·
`CAREER_ENTRY_*`·`CAREER_INTERNAL_PROMOTION`이 전부 불성립한다(`entry_scopes=None`인
`CAREER_EXIT`만 성립). 즉 §6의 대표 시나리오가 현행 코드에서 열리지 않는다.

**확정**: 규칙 완화 금지. `entry_scope=None`은 `ENTRY_SCOPE_MISMATCH`가 아니라
신설 `ENTRY_SCOPE_UNAVAILABLE` → `BYPASS_INCOMPLETE_COVERAGE`로 처리한다.

```
ENTRY_SCOPE_MISMATCH      명시된 scope가 규칙과 다름           → 판정 성립(ENFORCE)
ENTRY_SCOPE_UNAVAILABLE   판정 입력 자체가 없음(producer 부재) → bypass
```

**dual-run 집계**: `retained_active_trigger_count = 0`으로 기록 금지.
`measurable_active_trigger_count` / `entry_scope_unavailable_count` /
`exit_active_trigger_count`로 분리한다. 커리어 opportunity·entry의 active trigger는
`BLOCKED_BY_ENTRY_SCOPE_PRODUCER`로 보고한다.

**선행 과제 `CARR-SCOPE`** — parser·command·reducer에 producer 구현, explicit hard
fact에서만 scope 생성, 외부/내부승진/내부전보/내부지역 구분, 기존 Episode migration
또는 UNKNOWN 정책. **P2-3c 커리어 canary의 선행 조건**이다.

`INTERNAL_LOCATION`은 중립 enum에 값을 추가해 보존한다(합치기 금지, 호환 규칙 없이
fail-closed).

## 11-2. F2 — Exit 트랙은 Episode에 없다

§4-2의 `[build_career_process_snapshot(ep) for ep in loaded.episodes]`는 **퇴사 사실을
통째로 누락**한다. Exit은 `current_employment.exit_state`가 단독 소유한다(D4).

**확정 구성**:

```
episodes[]  ├─ opportunity  → CAREER_OPPORTUNITY   instance_key = episode_id
            └─ entry        → CAREER_ENTRY          instance_key = episode_id
current_employment.exit_state → CAREER_EXIT         instance_key = employment_context_id
```

`employment_context_history`는 초기 게이트 입력에서 **제외**한다(현재 사건 예외에
불필요 · 과거 맥락 혼입 위험 · supersession 범위 확대).

## 11-3. F3 — 커리어 블록은 조회가 아니라 조회→기록이다

§3의 `load()` 서술이 틀렸다. 실제는 `process_career_turn` = **load → parse → reducer
→ save**다. 따라서 "P2가 앞에서 1회 load"만으로는 요청 내 상태 불일치가 그대로 남고
조회도 2회가 된다.

**확정**: 함수 위치는 유지하되 `process_career_turn`을 준비/실행으로 분리한다.

```
subject_id 확정 직후
  → prepare_career_turn()      load 1회 + parse 1회 → PreparedCareerTurn
  → build_career_process_snapshots(pre-turn store)
  → build_request_process_context(+ current-turn explicit facts)
  → build_llm_input(process_context=…)              ← 축소 전 scope 부착
  → _prepare_career_transition_block(prepared=…)    ← 같은 준비 결과 재사용(reducer·save)
```

P2는 pre-turn store를 보므로 1턴 지연이 생기지만, **이번 턴 사실은
`CURRENT_TURN_EXPLICIT` 경로로 이미 P2 컨텍스트에 들어간다**(supersede 우선순위가
Episode origin보다 높다). 파서 결과도 재사용해 "P2가 본 사실 ≠ 저장되는 사실"을 막는다.

`CAREER_TRANSITION_CHAT_ENABLED`와 **독립**이다 — 그 플래그는 지시문 블록 노출만
정하고, 저장소에 hard fact가 있으면 P2는 그것을 쓴다.

## 11-4. 저장소 4상태

```
LOADED_WITH_FACTS   정상 판정
LOADED_EMPTY        정상 판정(커리어는 AUTHORITATIVE라 '없음' 확정 가능)
LOAD_FAILED         → BYPASS_PROCESS_SOURCE_UNAVAILABLE
CONTRACT_MISMATCH   → BYPASS_PROCESS_CONTRACT_MISMATCH   (신설 — 사유 분리)
```

`contract_mismatch` projection은 소비하지 않는다(스냅샷을 만들지 않는다).

## 11-5. 확정 변환표

`FACT_STAGE_MAPPING`이 유일한 stage 파생 경로이고 fact type이 8종이라, **실제로
`observed_stages`에 나타날 수 있는 단계는 7개**다. 나머지 13개는 타입 레이어 예약값이며
producer가 없어 **fail-closed**(스냅샷 미생성)로 둔다.

| fact_type | 커리어 단계 | family | ProcessStage | 판정 |
|---|---|---|---|---|
| `APPLICATION_SUBMITTED` | OPPORTUNITY.APPLICATION | CAREER_OPPORTUNITY | `APPLIED` | active |
| `INTERVIEW_COMPLETED` | OPPORTUNITY.INTERVIEW | CAREER_OPPORTUNITY | `RESULT_PENDING` | active |
| `WRITTEN_OFFER_RECEIVED` | OPPORTUNITY.OFFER_RECEIVED | CAREER_OPPORTUNITY | `IN_REVIEW` | active |
| `OFFER_ACCEPTED` | OPPORTUNITY.AGREEMENT | CAREER_OPPORTUNITY | `APPROVED` | active |
| `NOTICE_GIVEN` | EXIT.NOTICE_GIVEN | CAREER_EXIT | `NOTICE_GIVEN` | active |
| `EXIT_COMPLETED` | EXIT.EXITED | CAREER_EXIT | `COMPLETED` | terminal |
| `JOINED` / `TRANSFER_COMPLETED` | ENTRY.JOINED | CAREER_ENTRY | `COMPLETED` | terminal |

- `INTERVIEW_COMPLETED`는 면접 **완료** 사실이므로 `INTERVIEWING`이 아니다.
- `WRITTEN_OFFER_RECEIVED`는 회사 제안 존재 · 본인 수락 미확인이라 `APPROVED`가 아니다.
- `JOINED`에서 온보딩 진행을 추정하지 않는다 — 별도 관찰 사실이 필요하다.

## 11-6. lifecycle terminal override

정규화 순서는 **base stage → 종료 상태 확인 → terminal override**다. 단계 이름만 보면
`OFFER_RECEIVED`(=IN_REVIEW)인 Episode가 이미 닫혀 있어도 active로 남는다.

| 종료 사유 | ProcessStage | 의미 |
|---|---|---|
| `SCREENING_REJECTED` · `INTERVIEW_REJECTED` · `PROBATION_FAILED` | `REJECTED` | 상대가 거절 |
| `POSITION_CLOSED` · `OFFER_WITHDRAWN` · `AGREEMENT_FAILED` | `CANCELLED` | 기회가 사라짐 |
| `CANDIDATE_WITHDRAWAL` · `OTHER_OFFER_CHOSEN` · `COUNTEROFFER_ACCEPTED` | `ABANDONED` | 본인이 다른 선택 |
| `VOLUNTARY_EXIT` · `EMPLOYER_INITIATED_EXIT` · `EARLY_EXIT` | `COMPLETED` | 정상 종료 |
| 사유 없음 · 미해석 | `CANCELLED` | 세부는 잃되 **active로 남기지 않는다** |

`Episode.outcome`(REALIZED→COMPLETED / CLOSED_UNREALIZED→미해석 / SUPERSEDED→ABANDONED)과
`realization_status`도 같은 override에 참여한다. 종료 사유가 늘어나면
`test_every_close_reason_is_mapped`가 먼저 깨진다.

## 11-7. P2-3a 완료 상태

| 완료 기준 | 상태 |
|---|---|
| CareerEpisodeStore 요청당 1회 조회 | ✅ `prepare_career_turn` + 계측 테스트 |
| CareerEpisode → CareerProcessSnapshot 실제 DTO 변환 | ✅ `career_process_adapter` |
| active·terminal Episode 모두 보존 | ✅ terminal override |
| episode_id → process_instance_key 보존 | ✅ (Exit는 employment_context_id) |
| OBSERVABLE_HARD_FACT만 사용 | ✅ 구조적 파생(`observed_stages`) |
| RequestProcessContext 실제 chat 요청 연결 | ✅ `_build_request_process_context` |
| 후보 축소 전 전 후보 scope 산출 | ✅ `resolve_process_scopes`(감사 건수 > Top-N 검증) |
| 기존 career block이 같은 context 재사용 | ✅ `prepared=` 전달 |
| 저장소 실패 → 사유별 bypass | ✅ 4상태 분리 |
| 점수·등급·confidence·rank·Top-N·프롬프트 불변 | ✅ payload JSON 동일 회귀 2종 |

**남은 것**: P2-3b dual-run(§9 형식), 그 전에 `CARR-SCOPE`.
