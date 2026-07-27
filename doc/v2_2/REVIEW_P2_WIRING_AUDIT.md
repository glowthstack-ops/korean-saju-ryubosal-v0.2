# P2-3a — 운영 경로 배선 감사

> 상태: **감수 대기** · 기록일 2026-07-27 · 코드 변경 없음
>
> 선행: `00732ef`(P2-2c). 순수 함수는 완성됐고, 실제 요청 경로에 아직 연결돼 있지 않다.

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
