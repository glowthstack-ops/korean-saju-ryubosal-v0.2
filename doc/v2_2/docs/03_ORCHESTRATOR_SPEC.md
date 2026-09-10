# 03. 오케스트레이터 & 대화 계층 스펙

서비스 성패를 결정하는 계층. 사용자는 "내 질문을 이해하고 맥락을 이어 답했는가"로 평가한다.
이 과정에서 "정확한 간지 계산값"을 제시하면 신뢰도를 얻을 수 있지만 환각으로 부정확한 값을 제시하면 신뢰도가 크게 하락한다.

---

## A. Conversation Layer

### A0. Subject Resolution Engine (대상 결정 — 최우선)

이전 버전은 n명의 동반자 등록을 지원했고, 실사용에서 **대상 혼동이 가장 치명적인 오류**였다 (실로그: "너 내 사주랑 아들사주를 헷갈려서 내 사주로 풀이했는데 다시 체크해봐"). 모든 메시지는 intent 파싱 전에 대상부터 확정한다. 패턴 전수는 docs/08 A차원(13패턴) 참조.

처리 순서:
```
1. 명시 대상 추출
   - 호칭/관계어: "남편의", "엄마의", "아들 운"           → companion 매핑
   - 별칭/번호: "1호", "신랑", "아가"                     → alias 테이블 → companionId
   - 인라인 출생정보: "91년 10월 31일 오후 3시 부천"       → inline_temp 생성 (양/음력, 시각·출생지 유무 모두 파싱)
2. 모드 판별
   - "나를 제외하고"                                     → compare_exclude_self
   - "둘의 사주를 종합해서", "우리 가족"                  → group_aggregate
   - "궁합", "나랑 맞아?"                                → pairwise
   - "누가/누구야??" + 후보 N명                          → ranking
3. 전환/정정 발화
   - "본인 사주로 봐줘"                                  → subject=self 복귀
   - "등록했어", "지금 추가한 친구야"                     → 직전 UI 등록 이벤트와 결합, 미해결 시 확인 질문
   - "내 사주랑 아들사주를 헷갈렸어"                      → subject 교체 + 동일 intent 재실행 + 오류 인정
4. 무엇도 없으면                                         → 직전 턴 subject 상속, 그것도 없으면 self
```

```typescript
interface SubjectResolution {
  subjects: SubjectRef[];
  subjectMode: SubjectMode;
  unresolved: string[];      // 매핑 실패한 호칭 → 사용자 확인 질문 생성
  aliasUpdates: { alias: string; companionId: string }[];  // "1호" 학습
}
```

규칙:
- inline_temp도 반드시 Entity Tracking에 등록한다. 후속 턴의 **누적 참조**("이 3명과 앞서 물어본 2명까지 포함했을 때")를 지원해야 한다 (실측 존재).
- 시각 미상 inline은 3주(시주 제외) 모드 + 신뢰도 하향 플래그.
- 동반자 등록 UI 이벤트(추가/수정)는 대화 타임라인에 시스템 이벤트로 삽입해 "등록했어" 발화와 연결한다.

### A1. Conversation State Engine

현재 대화가 무엇을 다루는지 관리.

```typescript
interface ConversationState {
  threadId: string;
  activeSubjects: SubjectRef[];        // 현재 분석 대상 (self 외 가능)
  activeTopic: Domain | null;          // 'relationship'
  activePerson: EntityRef | null;      // 'current_partner'
  activeTimeScope: string | null;      // '2027'
  activeEvent: EventKey | null;        // 'new_relocation'
  activeConstraints: Record<string, unknown>; // 누적 조건 (방위 등 — F3)
  anchorDates: { label: string; date: string }[]; // "투표일 6/3" 등 외부 일정 (C11)
  lastIntent: IntentJson | null;
  lastResults: ResultSummaryRef[];     // 직전 답변에서 제시한 이벤트/시기/명리 판정 요약
  repeatCount: number;                 // 동일 질문 반복 감지 (F7) — 2회 이상이면 다른 각도 제시
}
```

### A2. Entity Tracking Engine

참조어("그 사람", "그 회사", "그때", "이번 운") 해석.

```typescript
interface TrackedEntity {
  id: string;                          // 'partner_1', 'temp_19980723_f'
  type: 'person' | 'event' | 'period' | 'place' | 'daewoon' | 'anchor_date' | 'claim';
  label: string;                       // '현재 연애 상대', '1998.07.23 여자'
  sourceTurn: number;
  sourceRole: 'user' | 'assistant';    // 시스템 답변 발 엔티티 구분
  attributes: Record<string, unknown>;
}
```

엔티티 생성 시점:
- 시스템 답변에서 새 대상이 제시될 때(예: "2026년 하반기 연애 후보")도 등록 — "그 사람은 어떤 사람이야?" 해석용
- **시스템이 내린 명리 판정도 `claim` 엔티티로 등록** — 실측 이의 제기("내 배우자운이 인목이라고 했잖아?", "아들은 편인격 아니야?")가 직전 발화가 아닌 수 턴 전 판정을 참조하기 때문
- 인라인 인물(A6/A7), 외부 일정(C11), 장소("광명 집") 모두 등록

### A3. Question Linking Engine

새 질문 vs 이전 질문의 확장 판별. 실측 연속성 패턴 9종은 docs/08 F 참조.

```typescript
interface LinkResult {
  isFollowUp: boolean;
  parentIntentId: string | null;
  inheritedSlots: Partial<IntentJson>; // 생략된 도메인/시간/대상을 직전 intent에서 상속
  linkKind: 'time_shift'      // "5월은 어때?" → "6월은?" — 시점만 교체 (F2)
          | 'domain_shift'    // "그럼 이직은 어때?" — 도메인만 교체, 시점·대상 유지 (F1)
          | 'subject_shift'   // "남편은?" — 대상만 교체
          | 'constraint_add'  // "남동쪽으로 간다면" — 조건 누적 (F3)
          | 'drill_down'      // "세부적으로 시기별로" — granularity 상향 (F8)
          | 'challenge'       // 이의/정정 (B9/B10) → Q12 라우팅
          | 'new';
  confidence: number;
}
```

판별 규칙(우선순위):
1. 명시적 참조어/판정 인용 존재 → follow-up 확정, Entity Tracking으로 해석
2. 단답(10자 이하 — 실측 11%)이고 시점·도메인·대상 중 1개 슬롯만 존재 → 해당 슬롯만 교체, 나머지 전부 상속. "내일운세 → 모레는? → 글피는?" 체인 포함 (B2/B3)
3. 도메인/시간 슬롯이 비어 있고 직전 intent와 의미 연결("그럼 준비는 언제부터?") → 슬롯 상속
4. 완전히 새로운 도메인+대상 명시 → 새 스레드 생성
5. 애매하면 LLM 분류기 1회 호출 (경량 모델, JSON 출력 강제)

추가 규칙:
- time_shift 후속에 비교 어조("그럼 그냥 6월이 낫겠네?")가 있으면 직전 시점과의 **비교 응답**을 생성한다.
- 사용자의 현실 업데이트("11월에 합격해서 12월부터 다니는 중") → Reality Context 갱신 + 관련 캐시 무효화 (F9)

---

## B. Question Orchestrator

### B1. Question Taxonomy (Query Type — 14종)

모든 질문은 정확히 하나의 query_type으로 분류된다. **단, 한 메시지에 복수 질문이 있으면 multi-intent 배열로 파싱한다 (실측 7.5%, docs/08 B4·B5).**

| ID | query_type | 예시 (실사용 로그) | 주 출력 |
|---|---|---|---|
| Q1 | fortune_overview | "앞으로 나는 어떻게 될까", "올해 운세" | 대운 흐름 + 고점 이벤트 |
| Q2 | domain_analysis | "재물운 풀이해줘" | 분야 점수/강약점/주요 시기 |
| Q3 | timing_search | "언제 결혼할까", "문창귀인이 언제 들어와?" | 후보 연/월 + 가능성 |
| Q4 | date_recommendation | "이사가기 좋은 날", "로또 사기 좋은 날과 방향" | 추천 날짜 랭킹 (+방위/시간대) |
| Q5 | event_explanation | "내 초년운은 왜 힘들었을까", "언제인지 맞춰봐", "내가 그때 왜 그랬을까" | 과거 사건 원인 + 역검증 + 과거 행동 회고(2026-09-06) |
| Q6 | comparison | 하위 3종: ⓐ compatibility "남편이랑 내 궁합" ⓑ competition "둘 중 누가 당선될까" ⓒ ranking "5명 중 나랑 합이 좋은 사람은 누구야" | 적합도 / 상대 우열 / 순위 |
| Q7 | decision_support | "회사 생활 vs 자영업 어떤 게 맞아?", "분양에 도전해?" | 선택지별 장단/위험/추천 |
| Q8 | chart_analysis | "내 용신이 뭐야", "나를 mbti로 설명하면?", "나는 왜 끝에 가면 항상 이렇게 하나" | 명식 구조/특징 + 반복 행동 패턴(2026-09-06) |
| Q9 | relationship_analysis | "남편과의 사이는 어때?", "부모복 아내복 자식복" | 관계 패턴/개선점 |
| Q10 | remedy | "조심해야 할 부분 있어?", "공망 보완할 방법은", "맞는 음식", "잘 맞는 절 추천" | 회피 시기/주의 행동/오행 보완 |
| Q11 | terminology_education | "월주 공망이 무슨 뜻이야", "용신 희신 구신 기신은 뭐야?" | 용어 설명 (+본인 사주 적용 예) — 풀이 파이프라인 미진입 가능 |
| Q12 | feedback_correction | "아들은 편인격 아니야?", "다 틀렸어, 실제로는 2023~2025년이었어" | 직전 답변 검토 + 정정/적재 (cases.jsonl) |
| Q13 | emotional_support | "아빠는 너무 날 혼내 그래서 스트레스야" | 공감 우선, 풀이는 동의 시에만 |
| Q14 | out_of_scope | 프롬프트 탐침, 로또 번호 요청, 악의 요청, 잡담 | 고정 정책 응답 / 정중 거절 / 스몰톡 |

**Q6 세분 규칙**:
- ⓐ compatibility: 관계 유형(부부/연인/부모자식/친구/동료/동업) 추출 — 유형별 graphScope 다름
- ⓑ competition: 본인 제외 가능("나를 제외하고"), 판정 기준일(투표일/개표일/발표일) 추출, **당락·승패 단정 금지** 정책 첨부 (docs/08 E)
- ⓒ ranking: 등록 동반자 + 인라인 제3자 + 과거 턴 임시 인물을 모두 후보 집합으로 구성

### B2. Intent JSON 표준 (v2 — 실측 패턴 반영)

한 메시지는 `ParsedMessage`로 파싱되며, 내부에 1개 이상의 IntentJson을 가진다.

```typescript
interface ParsedMessage {
  intents: IntentJson[];               // 다중 질문(실측 7.5%) — 답변도 intent 수만큼 섹션 보장
  isFollowUp: boolean;
  inheritedFrom?: string;              // 상속한 parent intent ID
  outputStyle?: OutputStyle;           // 메시지 전체 적용 (docs/08 B14)
  realityContextUpdates?: string[];    // 서사에서 추출한 현실 정보 ("11월에 합격해서 12월부터 다니는 중")
}

interface IntentJson {
  intentId: string;
  queryType: QueryType;                // Q1~Q14

  // ── 대상 (docs/08 A차원 — 가장 큰 누락 위험) ──
  subjects: SubjectRef[];              // 1명 이상. 기본 [self]
  subjectMode: 'single' | 'pairwise'   // pairwise=궁합(본인↔동반자)
             | 'group_aggregate'       // 가구 합산 ("둘의 사주를 종합해서")
             | 'compare_exclude_self'  // "나를 제외하고 동반자끼리"
             | 'ranking';              // 다자 순위
  relationType?: 'spouse' | 'lover' | 'parent_child' | 'sibling' | 'friend'
               | 'colleague' | 'boss' | 'business_partner' | 'rival' | 'unknown';

  domain: Domain;
  domains?: Domain[];                  // 결합 질문 ("이직운과 재물운") — 주 domain + 부가
  eventKey?: EventKey;
  eventKeys?: EventKey[];              // "이직 관련 운과 재혼운, 재혼 후 자녀" 류

  // ── 시점 (docs/08 C차원 18패턴 수용) ──
  timeScope: 'long_term' | 'mid_term' | 'short_term' | 'date_level' | 'hour_level'
           | 'past' | 'life_stage' | 'daewoon_unit' | 'timeless';
  timeRange: {
    type: 'relative' | 'absolute' | 'deadline' | 'age_based' | 'anchor_based'
        | 'user_ranges' | 'open_when';
    start?: string; end?: string;
    endOffsetDays?: number;            // "6개월 안에" → 184
    deadline?: string;                 // "2027년 2월까지 완료" (C9)
    age?: { from?: number; to?: number };          // "20살 전까지" (C12)
    anchorDates?: { label: string; date: string }[]; // "투표일 6/3, 개표 6/4" (C11)
    ranges?: { label: string; start: string; end: string }[]; // "26-27 / 28-30 / 31-33년" (C10)
    lifeStage?: '초년' | '청년' | '중년' | '말년' | '평생';   // (C13)
    granularity: 'daewoon' | 'year' | 'month' | 'day' | 'hour';
    urgency?: 'asap' | null;           // "빠를수록 좋아" (C16)
    granularityOverride?: boolean;     // "월로 따지면 어때?" — 사용자가 분석 단위 지정 (C18)
  };

  // ── 조건/제약 ──
  constraints: {
    direction?: Direction | 'unknown'; // 8방위. 기준점 = 사용자 현 거주지
    locationBase?: string;             // 방위 계산 기준. 기본값 = 프로필 residence.region (docs/11),
                                       // 발화 명시("지금 사는 곳은 일산 동구")가 있으면 발화 우선
    sonEomneunNal?: boolean;
    conditional?: string;              // 가정형 조건 원문 ("남동쪽으로 이사한다면") (B7)
    branchScenario?: boolean;          // 결과 조건부 ("당선되면 이후 운까지") (B8)
    chainedSchedule?: { step: string; offsetFrom?: string; window?: string }[];
                                       // "계약 후 2~3개월 안에 이사" 역산 체인 (C9)
    realityConstraints?: string[];     // 주말만 가능 등
    excludeOptions?: string[];         // "정밀기술자격은 하기 싫어. 다른 거 추천해줘"
  };

  output: OutputStyle;
}

interface OutputStyle {
  format: 'ranked_dates' | 'timeline' | 'report' | 'comparison' | 'slots' | 'narrative';
  maxResults?: number;
  scoreDisplay?: 'hundred_scale' | 'grade' | 'none';  // "100점 만점에 몇점?" (B14)
  rankRange?: number;                  // "1등부터 20등까지"
  toneOverride?: string;               // "동화처럼 이야기해줘"
  detailLevel?: 'summary' | 'detailed'; // "세부적으로 시기별로 알려주세요" (F8)
}

interface SubjectRef {
  kind: 'self' | 'companion' | 'inline_temp' | 'partial_info';
  companionId?: string;                // 등록 동반자 ID. 별칭("1호","신랑","아가") 매핑 거침
  inlineBirth?: {                      // 미등록 제3자 (A6/A7)
    date: string; time?: string;       // 시각 없으면 3주 모드 (A13)
    calendarType: 'solar' | 'lunar';
    gender?: 'M' | 'F';
    birthplace?: string;
  };
  label: string;                       // 대화 표시명 ("1998.07.23 여자")
  entityId: string;                    // Entity Tracking 등록 ID — 후속 턴 누적 참조용 (F4)
}
```

### B3. Broad Query Rewriter

판정 축에 **대상(subject)** 을 추가한다 (동반자 기능 때문에 시점·분야가 있어도 대상이 모호할 수 있다).

| 시점 | 분야 | 대상 | 처리 |
|---|---|---|---|
| ✗ | ✗ | 확정 | too_broad → 선택지 제안 (실행하지 않음) |
| ✓ | ✗ | 확정 | 종합운 실행 (Lifestyle/Overview 템플릿 부여) |
| ✗ | ✓ | 확정 | 분야별 기본 기간 자동 적용 (연애=6개월, 직업=1년 등 defaults 사전) |
| ✓ | ✓ | 확정 | 바로 실행 |
| - | - | 모호 | **대상 확인 질문 우선** ("어느 분 사주로 볼까요? 본인 / 1호(아들)") — 실측 최다 오류가 대상 혼동이므로 추측 실행 금지 |

too_broad 응답 형식:

```json
{
  "queryStatus": "too_broad",
  "originalQuery": "앞으로 내 운세 알려줘",
  "rewriteSuggestions": [
    { "label": "향후 3개월 전체 흐름", "queryType": "fortune_overview", "timeScope": "short_term" },
    { "label": "올해 직업운", "queryType": "domain_analysis", "domain": "career" },
    { "label": "향후 6개월 연애운", "queryType": "domain_analysis", "domain": "relationship" }
  ]
}
```

핵심: 질문을 거절하는 게 아니라 **실행 가능한 형태로 바꿔 제안**한다.
예외: 단답 후속(docs/08 B2 — 실측 11%)은 슬롯 상속으로 대부분 해결되므로 too_broad 판정 전에 Question Linking을 먼저 거친다 — "3개월 이내에?"는 too_broad가 아니다.
예외 2 (사건 서술형, 2026-08-11 확정): **과거 사건 서술절 + 우려 표현 + 막연 미래 질의**가 모두 있으면("그간 집안 자랑을 했었는데 그게 발목을 잡을 것 같아. 앞으로 어떻게 될까?") 시점·분야가 없어도 되묻지 않고 실행한다 — 상황을 서술한 사용자에게 범위를 되물으면 서술이 통째로 무시된다(실사용 3연속 바운스 보고). 서술 범위는 답변 지평 정책(docs/16)이 잡는다. 무맥락 광질문("앞으로 내 운세 알려줘")은 3신호 미충족으로 기존대로 좁힌다.

### B4. Execution Planner

queryType + eventType별 고정 실행 템플릿. LLM이 "어떻게 계산할까"를 생각하지 않게 한다.

```
Q1 fortune_overview (long_term):
  대운 전체 스캔 → 세운 이벤트 후보 탐지(score 필터)
  → 상위 연도만 월운 분석(선택) → Past Validation 요약 첨부 → LLM

Q3 timing_search (progress event):
  Event Scoring(기간 전체) → Timeline → Manifestation → Advice → LLM

Q4 date_recommendation (instant/hybrid):
  macro flow 확인 → 월운 적합 필터 → 일운 후보 생성
  → Risk filter → Calendar Rule → Reality Constraint → 랭킹 → LLM
  + 방위 요청 시: direction_rules 적용 (기준점 = constraints.locationBase)
  + 시간대 요청 시(docs/08 C17): 선정일 내 시진 적합도 추가
  + 체인 스케줄(C9): 데드라인에서 역산 → 후행 이벤트(이사) 창 확정 → 선행(계약) 창 배치

Q5 event_explanation (past):
  과거 간지달력 → Event Scoring(역방향) → evidence path → LLM
  "맞춰봐" 신호(C15) → Past Validation 모드: 후보 제시 후 사용자 확인 유도
  중립 회고("그때 왜 그랬을까", 2026-09-06) — 고정 시점에 대한 후회·평가 질문(흐름표 불요):
    후속 턴이면 대화 상태에서 시점·도메인 승계(time_shift) → 그 시기 대운·세운 = 배경 신호
    승계 맥락 없음 → 구조 답변(시점 창·후보·흐름표 없음) + 시점·사건 확인 질문
    + RETRO_BEHAVIOR_DIRECTIVE(3층 분리 — 원국·궁위=성향 구조 / 대운·세운=당시 배경·압력
      (원인 아님, 인과 확정 금지) / 실제 행동·결과=별도 사실, 미서술 시 사건 창작 금지)

Q8 chart_analysis (structural, 시점·이벤트 데이터 불요):
  원국 구조(십성 세력·격국·신강약·용신) + 명식 해석 자료(궁위별 십성·12운성) + 구조 블록 → LLM
  반복 행동 패턴("왜 항상 이렇게 하나", 2026-09-06) → BEHAVIOR_PATTERN_DIRECTIVE
    (3층 분리 + 관리 프레임. 궁위→행동 단계 연결은 정통 규칙이 아닌 **서사화용 해석 규칙**이며
     보조 단서 — 시주=후반·결과·표출 자리라 마무리 단계와 연결 가능, '천간=마음/지지=행동/
     운성=태도' 고정 등식 금지)

Q6 comparison:
  ⓐ compatibility: 대상별 ChartAnalysis → Compatibility Engine(E13) → 관계 유형별 풀이
  ⓑ competition:   대상별 판정일(anchor_date) 운세 강도 + 해당 이벤트 신호 → 상대 우열
                    + 당락·승패 단정 금지 규칙 첨부 (docs/08 E)
  ⓒ ranking:       후보 집합(등록 동반자 + 인라인 + 과거 턴 누적 참조) × pairwise 점수 → 순위

Q7 decision_support:
  선택지별 Event Scoring + Manifestation → 비교표 → LLM
  excludeOptions 반영 (사용자가 거른 선택지 재제안 금지)

Q10 remedy:
  대상 명식의 약점/리스크 노드 → remedy 사전(시기회피/주의행동/오행보완 — docs/08 D-3) → Advice → LLM

Q11 terminology_education:
  용어 사전 + (대상 사주 내 해당 요소 있으면) 적용 예시 → LLM. Event 파이프라인 미호출

Q12 feedback_correction:
  claim 엔티티 조회 → 엔진 재검산 → 일치: 근거 재설명 / 불일치: 정정 + 오류 인정
  사실 피드백("실제로는 11월이었어") → cases.jsonl 적재 + Confidence Calibration 갱신
  내부 개선책(CoT/RAG/프롬프트 수정안)은 사용자에게 노출하지 않음

Q13 emotional_support:
  공감 응답 (엔진 미호출) → 사용자가 원할 때만 관련 도메인 풀이 제안. 위기 신호 시 전문기관 안내

Q14 out_of_scope:
  고정 정책 응답: 프롬프트/모델 정보 비공개 · 로또 번호 거부(날짜·방향 대안 제시) · 악의 거절 · 스몰톡
```

**다중 intent 처리 (docs/08 B4/B5)**: ParsedMessage.intents를 순회하며 plan 배열을 생성한다. 공유 가능한 엔진 결과(동일 대상·기간의 Event Scoring)는 1회만 계산해 재사용. 답변은 intent별 섹션으로 분리해 **부분 질문 누락을 구조적으로 차단**한다.

실행 계획 산출물:

```typescript
interface ExecutionPlan {
  intent: IntentJson;
  eventType: 'progress' | 'instant' | 'hybrid' | 'none';
  engineCalls: { engine: string; params: Record<string, unknown> }[];  // 순서 보장
  dictionaryScope: string[];          // 로드할 사전: ['common', 'events/relocation', 'calendar']
  graphScope: EventKey[];             // Graph RAG 검색 서브그래프 범위
  perSubject: boolean;                // 다중 대상이면 대상별 호출 후 집계
}
```

### B5. Context Reduction Engine

LLM 입력 직전 최종 필터. 규칙:

1. **간지 계층 압축**: 대운 전체 / 선택된 세운만 / 선택 세운 내 월운만 / 택일 시에만 일운
2. **그래프 노드**: intent의 graphScope에 해당하는 evidence path 노드만
3. **사전**: dictionaryScope 외 로드 금지
4. **이벤트 후보**: Top N (기본 3~5) + score 임계값
5. **모든 이벤트 후보에는 해당 간지와 대운 맥락을 반드시 포함** — LLM은 간지를 계산할 수 없다

---

## C. 분야별 Graph 조회 범위 (graphScope 기본값)

| domain | 조회 노드 |
|---|---|
| career | 관성(정관/편관), 인성, 식상(퇴사 신호), 이동, 계약, 승진 |
| relationship | 배우자궁(일지), 재성/관성(성별별), 도화, 홍염, 합충, 이별 신호 |
| relocation | 역마, 충, 이동성 합, 대운 교체기, 공망 활성 |
| wealth | 재성, 식상생재, 비겁(탈재), 문서 |
| education | 인성, 문서, 관성, 시험 신호 |
| health | 일간 오행 충극, 형, 12운성 쇠약 단계 |


**총운 조망 선별의 fan-out 캡 (2026-09-10 사용자 승인 — daily 클론 감사 이식).** `reduce_overview_candidates` 는 의미 클러스터(사건×길흉 방향×지배 신호) 다변화(2026-07-14 확정) 위에 **같은 (시기, 지배 신호)에서 갈라진 사건 상한 2**(`OVERVIEW_FANOUT_CAP`)를 둔다. 세 패스(co-top→커버리지→충원)를 top_n 의 3배 예산으로 돌린 뒤 캡을 적용하고 top_n 으로 자른다(재충원). 접힌 사건은 대표 후보의 메타("같은 시기·같은 신호에서 갈라진 사건(접힘): …")로 남겨 LLM 이 별개 사건으로 나열하지 않고 한 흐름의 다른 얼굴로 서술하게 한다. 리포트 부록 점수표(`select_table_candidates`)도 같은 캡을 쓴다. 40명식 shadow: 채팅 클론 쌍 2.05→1.23/명식, 시기 3.48→3.77, 도메인 3.20→3.33 / 리포트 클론 9.03→4.45, 시기당 최대 행 3.77→2.00. 판정·점수 불변(선별만). 반대 방향 동시 노출(같은 시기·같은 도메인·반대 방향)은 실측 0건이며 `test_selection_contradiction_guard.py` 가 고정한다.