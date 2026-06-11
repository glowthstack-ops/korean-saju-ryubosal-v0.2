# 01. 전체 아키텍처

## 설계 목표

기존 사주 서비스의 실패 패턴:

```
만세력 계산 → LLM에 모든 정보 전달 → LLM이 임의 해석
→ 과추론 / 일관성 부족 / 토큰 폭발 / 질문과 무관한 답변
```

v2의 역할 분리:

| 담당 | 역할 |
|---|---|
| 만세력 엔진 (완성) | 계산의 유일한 진실 공급원 (Single Source of Truth) |
| 사주 구조 분석 엔진 | 신강약 / 용신·희신·기신 / 격국 / 분포 |
| Event Engine 군 | 시기별 이벤트 가능성 점수화 |
| Graph RAG | 근거 경로 + 해석 규칙 + 금기 규칙 제공 |
| Conversation Layer | 대화 맥락·참조어·스레드 관리 |
| Orchestrator | 질문 구조화 → 어떤 엔진을 호출할지 결정 |
| Context Reduction | 무엇을 버릴지 결정 (토큰 최적화) |
| Precompute Store + Topic Builder | 운 복합 조합 사전계산(T0~T2) + 주제별 동적 컨텍스트 산출 (docs/09) |
| LLM | 설명(통변 문장화)만 담당 — 페르소나 어투 적용 (docs/10) |

## 전체 데이터 흐름

```
사용자 질문
    │
    ▼
┌─────────────────────────────────────────┐
│ Conversation Layer                      │
│  ├─ Conversation State Engine           │  현재 토픽/대상/시간범위
│  ├─ Entity Tracking Engine              │  "그 사람", "그때" 해석
│  └─ Question Linking Engine             │  새 질문 vs 이전 질문의 확장
└─────────────────────────────────────────┘
    │  (resolved query + thread context)
    ▼
┌─────────────────────────────────────────┐
│ Question Orchestrator                   │
│  ├─ Query Parser → Intent JSON          │  query_type / domain / time_scope
│  ├─ Broad Query Rewriter                │  너무 넓으면 좁힌 선택지 제안
│  ├─ Event Type Classifier               │  progress / instant / hybrid
│  └─ Execution Planner                   │  호출할 엔진 + 순서 결정
└─────────────────────────────────────────┘
    │  (execution plan)
    ▼
┌─────────────────────────────────────────┐
│ Precompute Store (docs/09)              │
│  T0 원국·구조 / T1 대운·세운·월운 복합   │
│  T2 일운 복합 (일 단위 갱신)             │
│  → Topic Context Builder (M01~M15)      │
│    주제별 동적 컨텍스트 산출 (수치 확정)  │
└─────────────────────────────────────────┘
    │  (TopicContext)
    ▼
┌─────────────────────────────────────────┐
│ Analysis Engines                        │
│                                         │
│ [계산]  만세력 엔진(기존) → 구조 분석    │
│ [예측]  Event Scoring → Event Form      │
│         → Timeline → Manifestation      │
│ [사용자] Self Profile → Advice          │
│ [신뢰]  Past Validation                 │
│ [생활]  Lifestyle Fortune               │
│ [택일]  Date Selection + Calendar Rule  │
│         + Risk Avoidance                │
└─────────────────────────────────────────┘
    │  (이벤트 후보 + 점수 + 신호)
    ▼
┌─────────────────────────────────────────┐
│ Event Graph RAG                         │
│  근거 경로(evidence path) 검색·압축      │
│  해석 규칙 / 금기 규칙 첨부              │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ Context Reduction Engine                │
│  intent에 필요한 노드/간지/규칙만 선별   │
└─────────────────────────────────────────┘
    │  (LLM Input Contract — docs/06 참조)
    ▼
LLM (통변 생성: 계산 없음, 설명만)
```

## 계층별 책임 경계

### 1. 계산 레이어 (Deterministic)
- 만세력 엔진 (기존), 사주 구조 분석 엔진, 간지달력
- 입력이 같으면 출력이 항상 같다. LLM·랜덤 요소 없음.

### 2. 예측 레이어 (Rule-based Scoring)
- Event Scoring → Event Form → Timeline → Manifestation
- 사전(JSON) 기반 룰 + 가중치. 점수는 0~100 정수.
- **이벤트 2종 분리 필수**:
  - `progress`: 장기 진행형 (이직, 연애, 사업 전환 등) → Timeline/Manifestation 적용
  - `instant`: 즉효성 실행일 (계약, 수술, 시험, 로또 구매 등) → Date Selection 적용
  - `hybrid`: 이사처럼 둘 다 (준비=progress, 당일=instant)

### 3. 사용자 레이어
- Self Profile (성향 → 현실화 방식 분석, 성격검사화 금지)
- Advice ("그래서 뭘 해야 하나"에 답)
- Past Validation (과거 사건 복원 → 신뢰 형성. 미래 예측보다 먼저 노출)

### 4. 생활 운세 레이어 (인생 이벤트 엔진과 분리)
- Lifestyle Fortune (일일/주간/연간, 고정 출력 템플릿)
- Date Selection (택일 = 날짜 후보 랭킹 문제)
- Calendar Rule (손없는 날/절기/공휴일 — 명리 계산이 아닌 민속·캘린더 규칙)

### 5. 대화/오케스트레이션 레이어
- 서비스 품질을 실제로 결정하는 계층. 사용자는 "정확한 간지 계산"이 아니라 "내 질문을 이해하고 맥락을 이어 답했는가"로 평가한다.

## 핵심 시간 모델

```
대운  = 큰 배경 (10년)          — 장기 질문이면 전체 제공
세운  = 올해의 허용/압박         — 이벤트 점수 상위(score≥70 또는 Top5)만 제공
월운  = 그 달의 활성 주제        — 선택된 세운 안에서만 제공
일운  = 실제 실행일             — 날짜 추천(택일) 질의에서만 제공
```

이 계층형 압축 규칙이 토큰 절감과 정확도의 핵심이다.

## Trigger / Execution 분리 모델

```
Trigger Month (신호 발생) ≠ Execution Month (실제 행동/결과)

이직 예시:
  2026-06 awareness   (갑기합 → 변화 생각 시작)
  2026-07 exploration (탐색)
  2026-08 action      (사해충 → 실제 행동)
  2026-09 decision    (결정)

Activation Window: { start: "2026-06", end: "2026-11" }
```

점수도 분리: `interest_score` / `action_score` / `completion_score`.

## 신뢰 형성 플로우 (서비스 UX 순서)

```
사주 입력 → Past Validation (과거 검증, 근거 기반)
→ 사용자 확인 → 신뢰도 계산 (Confidence Calibration)
→ 미래 흐름 제시 → 행동 조언
```

과거 검증은 콜드리딩이 아니라 반드시 근거 경로(예: 2009 입학 ← 정관 활성 ← 문서성 증가, score 91)를 동반한다.


## 풀이 상품 3종과의 관계 (docs/10)

총운 풀이(RPT_FULL, A4 50장) / 주제별 집중 풀이(RPT_FOCUS, A4 15장) / 대화형(CHAT)은 모두 **동일한 Precompute Store + Topic Builder를 공유**한다. 보고서 = 고정 목차의 섹션별로 대화형 파이프라인을 반복 실행해 조립한 것이며, 별도 분석 경로를 만들지 않는다.
