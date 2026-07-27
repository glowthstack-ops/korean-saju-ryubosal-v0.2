# D1 시작 계약 — 채팅 도메인 경로 감사

> 상태: **감사 대기** · 기록일 2026-07-27 · 코드 변경 없는 조사부터 시작
>
> 챗 총운(일·월·연)에는 계층형 grounding·층위 캡이 적용됐지만, **도메인 질문
> (이직·연애·계약·재물·날짜)은 미적용**이다. 어디서 끊기는지 먼저 확인한다.

## 0. 왜 D1이 먼저인가

`P3-2`·`P4`는 사용자 결과를 실제로 뒤집는지 아직 미확인인 조사 단계인 반면, D1은
이직·연애·계약 답변에 **직접 영향**을 준다. 사용자 품질 우선이면 D1이 앞선다.

## 1. 분류 규약 — A~E는 복수 태그다

한 경로가 동시에 여러 결함을 가질 수 있다. 하나만 고르면 실제 수정 범위를 잃는다.

```
A  완비                                    ← 단독 태그
B  계산은 있으나 LLM grounding 누락          ┐
C  local scope 누락 — 아래 둘로 세분한다     │ 복수 선택 가능
D  상위 governing stack 누락                │
E  Episode·사용자 현실 과정 연동 필요         ┘
```

`C`는 두 개념이 섞이지 않도록 나눈다.

```
C1 총운형 local polarity 상태 없음
   = 카테고리의 긍정·부정 우세 범위(LOCAL_FAVORABLE_ONLY / LOCAL_ADVERSE_ONLY)
   → 도메인 이벤트 경로에는 **필수가 아닐 수 있다**

C2 이벤트형 local scope 없음
   = 사건 후보의 자격·표현 범위(LOCAL_TRIGGER_ONLY)
   → P2에서 구현. 총운 슬롯 점수 파이프라인을 도메인에 붙일 필요는 없다
     (source_layers · SUPPRESS_minor_layer_only · 상위 사건 provenance ·
      Episode·user-facts 만으로 판정 가능)
```

6개 경로의 실질 결함은 **C2**다.

예: 상위 stack 있음 + local 상태 계산됨 + LLM payload 누락 + Episode 필요 → **`B + E`**

## 2. E는 P2의 적용 범위가 아니다 (중요 정정)

`P2 LOCAL_TRIGGER_ONLY`의 적용 조건은 **Episode 필요 여부가 아니라 minor-layer-only
사건 후보의 존재**다.

```
P2 적용 후보
  월·일운 신호만으로 사건 후보 생성
  AND 상위 사건 근거 없음
  AND 활성 Episode·확정된 현실 과정 없음
  → LOCAL_TRIGGER_ONLY

P2 예외 근거
  E 경로에서 확인된 active Episode 또는 사용자 제공 현실 진행 사실
```

즉 `E`는 **게이트를 통과시킬 예외 근거가 필요한 경로**이지 게이트 대상이 아니다.
`B·C·D` 여부와 무관하게 minor-layer-only 후보가 생기는 모든 경로가 P2 대상이다.

## 3. 매트릭스 — 계산 / 보존 / 전달을 분리한다

엔진에는 있는데 LLM에 없으면 `B`, 엔진 자체에 없으면 `C` 또는 `D`다. 세 단계를
반드시 나눠 기록한다.

```
상태가 계산되는가 → reducer·adapter에서 보존되는가 → LLM이 실제로 받는가
```

| 경로 | 상위 stack 산출 | 간지 polarity 보존 | local 상태 산출 | local 상태 LLM 전달 | Episode/현실 사실 | 주요 사건 랭킹 게이트 | LLM grounding | 분류 |
|---|---|---|---|---|---|---|---|---|
| 이직 | | | | | | | | |
| 연애·결혼 | | | | | | | | |
| 계약·대출·이사 | | | | | | | | |
| 재물 변화 | | | | | | | | |
| 날짜 선택 — 열린 사건 | | | | | | | | |
| 날짜 선택 — 일반 길일 | | | | | | | | |

## 4. 날짜 선택은 두 행으로 나눈다

하나로 보면 안 된다 — 정반대 처리가 필요하다.

```
열린 사건의 날짜 선택
  잡힌 면접일 · 계약 체결 후보일 · 발표일 · 이사 후보일 · 입사일
  → ACTIVE PROCESS. 일운이 정당한 trigger가 된다

사건 없는 일반 길일 탐색
  "이번 달 좋은 날" · "돈 들어오기 좋은 날" · "이직 성사될 날"
  → NO ACTIVE PROCESS + minor-only signal
  → LOCAL_TRIGGER_ONLY. 주요 사건 성사일로 제시 금지
```

## 5. 경로 감사 순서 — 실제 필드명을 기록한다

추측 구현을 막기 위해 각 단계의 **실제 필드명**을 남긴다.

```
intent/router → time range 파싱 → event candidate 생성
→ EventEngine governing stack → polarity · source_layers
→ local-only 상태 또는 minor-only 판정
→ ranker / context reducer → Episode · user-facts 예외
→ LLM payload → 최종 narrative audit
```

## 6. 도메인마다 대조할 3+1 사례

```
1. 상위 지지 있음 + 월·일운 촉발          → 주요 사건 후보 가능
2. 상위 지지 없음 + 월·일운만 강함 + 현실 과정 없음  → LOCAL_TRIGGER_ONLY 후보
3. 상위 지지 없음 + 월·일운만 강함 + 현실 과정 진행 중 → 접촉·결정·결과 trigger 허용

4. (부정 방향) 일운만 불리
   → 이별·해고·계약 파기·큰 손실 **사건 생성 금지**
   → 국소 마찰·재확인 안내는 허용
```

## 7. 경로별 종료 형태

```
이직
- 분류: B + E
- 상위 stack: 계산됨 / polarity: 보존됨
- local-only: 계산되나 LLM payload 누락
- Episode: career_transition에서 사용 가능
- P2 조치: reducer에 event_scope 추가, active Episode 예외 연결
```

각 경로를 아래 중 하나로 닫는다.

```
변경 없음 — 이미 완비
grounding만 보강
local-only 소비 추가
governing stack 보완
P2 예외 연결
P5 선행 필요
```

## 8. 이번 감사에서 변경하지 않는 것

```
production 점수 · 상태 · 순위
운영 플래그
챗 총운 경로(이미 배포·검증 완료)
리포트 경로(D2 별도 사이클)
무료 오늘의 사주(D0 대상 없음 판정)
```

D1은 **코드 변경 없는 매트릭스 산출**이 1차 산출물이다. 보완 구현은 분류가 끝난 뒤
경로별로 분리해 착수한다.

## 9. 관련 코드

- `saju_api/services/chat_service.py` — intent 라우팅 · `_build_period_fortune`(총운 전용)
- `saju_engines/event_engine_v2.py` — `stack_for`(상위 관할 운 스택)
- `saju_engines/event_ranker.py` — `SUPPRESS_minor_layer_only`(현행 −6)
- `saju_engines/context_reducer.py` — LLM payload 직렬화
- `saju_engines/career_chat_consumer.py` · `career_shadow_repository` — Episode
- `saju_engines/v2_scoring.py` · `period_role_summary.py` — 총운 전용 local-only 상태


## 10. 1차 감사 결과 (2026-07-27)

| 경로 | 상위 stack | polarity | local 상태 | 후보별 층위 grounding | Episode/현실 사실 | major-event 게이트 | 분류 |
|---|---|---|---|---|---|---|---|
| 이직 | ✅ 스택만 | ✅ | ❌ C2 | ❌ **B 미해소** | ✅ career Episode | △ `−6`(dormant) | B + C2 |
| 연애·결혼 | ✅ 스택만 | ✅ | ❌ C2 | ❌ **B 미해소** | △ 플래그만 | △ `−6`(dormant) | B + C2 + E |
| 계약·대출·이사 | ✅ 스택만 | ✅ | ❌ C2 | ❌ **B 미해소** | ❌ | △ `−6`(dormant) | B + C2 + E |
| 재물 변화 | ✅ 스택만 | ✅ | ❌ C2 | ❌ **B 미해소** | ❌ | △ `−6`(dormant) | B + C2 + E |
| 날짜 — 열린 사건 | ✅ 스택만 | ✅ | ❌ C2 | ❌ **B 미해소** | △ shadow-first | △ `−6`(dormant) | B + C2 + E |
| 날짜 — 일반 길일 | ✅ 스택만 | ✅ | ❌ C2 | ❌ **B 미해소** | — | △ `−6`(dormant) | B + C2 |

> 2026-07-27 2차 정정 — 1차 기록에서 `LLM 전달: B → 해소`로 적었으나 **사실이 아니다.**
> 아래 §11 참조. 후보별 층위 grounding은 여전히 미해결이다.

### 확인된 사실 (2차 정정 반영)

```
상위 stack은 전 경로에 있다 — 다만 이는 '평가 스택 구성'이지 '이 후보를 상위 운이
지지했다'가 아니다. stack_for()가 관할 상위 운을 항상 붙이므로 구분이 안 된다.

LLM은 층위를 못 본다 — LlmEventCandidate에 후보별 층위가 없다. D1-B로 전달 배선을
만들었으나 전달할 데이터(후보별 기여 층위)가 애초에 존재하지 않는다.

local-only 상태는 총운(v2_scoring) 전용이다. 이벤트 경로에 필요한 것은 C1이 아니라 C2다.

Episode는 커리어만 실질 보유 — 연애는 플래그, 선발은 shadow-first, 계약·재물은 전무.
```

## 11. 2차 정정 — D1-B 배선 결함과 P2 전제 붕괴 (2026-07-27)

### 무엇이 틀렸나

```
1차 기록: 6경로 모두 'LLM 전달 B → 해소'
실제:     _layer_grounding()이 운영 경로에서 항상 None을 반환했다

원인 ①  to_legacy_candidate가 층위를 legacy DTO로 옮기지 않았다
원인 ②  테스트가 실제 DTO 대신 SimpleNamespace 덕타이핑 스텁을 썼다
        → 분류 로직은 통과했지만 배선은 한 번도 검증되지 않았다
```

문서가 요구한 `계산 → 보존 → 전달` 3단 구분에서 **보존 단계를 검증 없이 ✅로 기록**한 것이
직접 원인이다. 이후 유사 감사에서는 실제 DTO를 통과시키기 전에 ✅를 쓰지 않는다.

### 더 근본적인 문제 — 측정 대상 오류

원인 ①을 고치고 실측하자 다음이 드러났다.

```
ten_god_brancher.py:264
  layers = sorted({s.layer for s in signals}, ...)   # 후보 루프 '밖'에서 1회 계산
  for event_key, a in acc.items():
      EventCandidateV2(..., source_layers=layers)    # 전 후보 동일값

_Acc가 추적하는 것: score · quality · src_strength · reasons · ten_gods
_Acc가 추적하지 않는 것: 층위
```

즉 `EventCandidateV2.source_layers`는 이름과 달리 **후보별 기여가 아니라 그 시점 평가
스택 전체의 층위**다. 실측(1980-11-22, 연·월·일 전 레벨):

```
후보 744건
  스택 기준 UPPER_SUPPORTED  744 (100%)
  스택 기준 MINOR_ONLY         0
  SUPPRESS_minor_layer_only 발동  0건
```

`UPPER_SUPPORTED 100%`는 사실이 아니라 **측정 대상을 잘못 고른 결과**다.

### P2에 대한 귀결

```
P2 LOCAL_TRIGGER_ONLY의 대상 모집단이 현재 데이터로는 0이다.
게이트를 구현해도 아무 후보도 분류되지 않는다.
→ 후보별 contribution provenance 확보 전까지 P2 보류.
```

### `−6` 감산에 대한 판정 범위 제한

```
확인된 것: ten_god_brancher 경로 · 1980-11-22 차트 744후보에서 발동 0건 (dormant)
확인되지 않은 것: 다른 producer·legacy 생성기·fixture가 후보별 층위를 넣는지

→ 전역 dead code로 확정하지 않는다. P2 게이트가 작동하기 전에는 제거하지 않는다.
```

### 단계 0에서 실제로 한 것 (B안)

```
legacy DTO에 stack_layers 추가 — '평가 스택 구성'이라는 정확한 의미로 보존
legacy DTO에 candidate_source_layers 추가 — 현재 항상 빈 값(수집 전)
classify_layer_evidence_scope는 candidate_source_layers만 읽는다
  → 비면 UNKNOWN. stack_layers로 상위 지지를 판정하는 경로를 원천 차단
'세운 또는 대운의 지지도 있음' 문구 제거 — 후보 100%에 붙던 미검증 주장
실제 DTO 통합 테스트 추가(스텁 금지)

점수·등급·순위·Top-N·프롬프트 텍스트 모두 불변
```

### 후속 작업 분리

```
P2-PROV (신규 선행)
  _Acc가 기여를 더하는 '그 순간' provenance를 기록한다(최종 후보에서 역산하지 않는다).
  점수·등급·순위·Top-N·API·LLM 모두 불변. shadow 감사 전용.

  ⚠ 십성 이름 역산(source_ten_gods ∩ signals)은 탐색용이며 production 근거로 쓰지 않는다.
    같은 십성이 여러 층위에 있으면 실제 기여하지 않은 층위까지 귀속된다.
    relation·quality·src_strength·합충형파해·domain modifier도 개입한다.

  감사 시 단위를 명시한다 — 세 분류의 합은 unique_candidate_id_count와 일치해야 한다:
    candidate_count / candidate_contribution_count / unique_candidate_id_count
    UPPER_SUPPORTED · MINOR_ONLY · UNKNOWN candidate 수

감수 (P2-PROV 이후)
  대운·세운 기여가 하나라도 있으면 '상위 사건 근거 있음'인가?
  최소 기여량이 필요한가 / 같은 event formula여야 하는가 / polarity 보조도 지지인가
  상위 운이 부정 기여한 경우 / 상위와 하위가 반대 방향인 경우

P2 (감수 이후)
  candidate_source_layers → EventScope → Episode 예외 → Top-N 게이트 → −6 제거
```
