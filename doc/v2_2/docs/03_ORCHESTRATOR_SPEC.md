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
   - 1인칭 주어·소유 표지("내가 …", "나는", "난", "제가", "내 사주") + 동반자 지칭 없음
                                                          → subject=self 복귀(4순위 상속보다 우선, 2026-10-28).
                                                            관점 표현("내가 보기엔")·1인칭 복수("우리가")는 제외
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
  assistantCommitments: AssistantCommitment[]; // 시스템 발언 원장(2026-10-01) — 답변의 추천·비권장·판정 문장 원문
                                       // {quote, sourceTurn, polarity, status: active|superseded, supersededByTurn}
  lastChallengeContext: Record<string, unknown>; // 이번 턴 정정 감사 맥락 {challenge, matched[], excluded[]}
}
```

**시스템 발언 원장(assistantCommitments, 2026-10-01 데굴님 승인)** — 사용자 제공 사실 원장(user_facts)과 대칭.
"시스템이 무엇을 말했는가"의 증거이며 옳다는 증거는 아니다. 답변 확정 시(동기·비동기 경로 공통) 추천·비권장·판정
수행 표지 문장을 rules-first 로 추출해 축적(캡 24)하고, 같은 대상어(색 범주 정규화 포함)에 반대 극성 발언이 오면 이전 건을
**삭제하지 않고 superseded 로 남긴다**(요약 메모리에 '초록은 나쁨'만 남으면 "네가 추천했잖아"에 답할 수 없다). 이의 턴·선택지
확인 턴에서 사용자 발화와 어휘가 겹치는 문장을 `[이전 발언 원문]`(턴·극성·상태 라벨)으로 주입한다. 구현
`saju_engines/assistant_commitments.py`, 감사 `commitment_audit.py`(shadow 로그 — 재생성·교체 없음, 실로그 web-mup4m82l 계기).

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
0. **이의·인용 반문은 최우선 challenge**(2026-10-01) — 2인칭 지칭+인용·수행 표지("니가 … 추천해줬잖아", "네가 좋다고 했잖아")
   또는 시점 참조+발화 동사("아까는 9월이 좋다고 말했잖아") → `challenge`(Q12). offer-slot/offer-answer(되물음 답) 판정보다
   **앞**에 둔다 — 실로그에서 이의가 직전 되물음의 '답'으로 링크돼 LLM이 자기 발언을 부인했다. 1인칭 주어·과거 사실 절
   ("내가 아까 말한", "3년 전에 이사했잖아")은 제외. 규칙 SSOT `saju_engines/challenge_detect.py`(파서 Q12와 공유).
   요청·의문형 후속("다른 색을 추천해줘", "녹색을 추가해도 돼?")에도 되물음 답 지시를 붙이지 않는다.
0b. **선택지 확인 후속** — 발화가 원장(assistantCommitments)에서 추천·비권장한 대상어를 언급하고 새 도메인·새 풀이 요청이
   없으면 `constraint_add` 로 잇는다("녹색을 추가해도 돼?"가 NEW 로 끊기던 결함).
1. 명시적 참조어/판정 인용 존재 → follow-up 확정, Entity Tracking으로 해석
2. 단답(10자 이하 — 실측 11%)이고 시점·도메인·대상 중 1개 슬롯만 존재 → 해당 슬롯만 교체, 나머지 전부 상속. "내일운세 → 모레는? → 글피는?" 체인 포함 (B2/B3)
3. 도메인/시간 슬롯이 비어 있고 직전 intent와 의미 연결("그럼 준비는 언제부터?") → 슬롯 상속
   - 시점 슬롯 예외: '언제'류 시점-탐색 후속은 직전 시점 창을 잇지 않는다(스스로 탐색). 단 **직전이 택일(유계 창)이고 최상급·선택 표지("그럼 가장 좋은 날은 언제야?", "그중 제일 좋은 하루")가 붙은 후속**은 직전 답의 후보 중 하나를 고르는 질문이라 택일 유형·사건·시점 창을 그대로 잇는다(`_BEST_PICK_RE`, 2026-09-30 실로그: 로또 택일 뒤 최상급 후속이 10년 창 timing_search로 열려 계약·문서 답으로 이탈). 새 도메인·사건이 붙으면 예외 아님.
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
  careerField?: boolean;               // 직업 분야·직종·적성 질문(docs/08 career, 2026-09-10) — 원국 십성 기능 축, 시점 미승계

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
    dates?: string[];                  // "10월 7일과 9일" — 낱낱이 지목한 날(ISO, 최대 4). start/end 는 min~max 스팬이며
                                       // 사이 날은 대상이 아니다. 연속 범위("7일부터 9일까지")는 start/end 만 쓰고 비운다 (C5d, 2026-10-02)
    weekFrame?: 'sun_sat' | null;      // 주 단위 창의 요일 경계. 'sun_sat' = 일요일~토요일(로또 판매 회차·사용자 지정
                                       // "일요일부터 토요일까지"). null = 기본 월~일 또는 주 단위 아님 (C4·C3.4, 2026-10-04)
    weekLabel?: '이번 주' | '다음 주' | '다다음 주' | null; // 사용자가 쓴 주 호칭 — 택일 블록 '기간 기준' 줄에 실어 답이 호칭을 바꿔 부르지 않게 한다
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
  (2026-10-01) 시스템 발언 원장 검색 → [이전 발언 원문] 주입 → **정정 답 계약**(`_CHALLENGE_DIRECTIVE`):
    ①이전 발언 확인(원문 있으면 인정, 없으면 '드리지 않았다') ②모순 분류 — (a)같은 정보로 번복→철회 (b)새 조건으로
    변경→이유 (c)조건 달라 양립 (d)판단 불가→확인 ③유지·철회 범위(설명 보완 아닌 추천 수정) ④배제 조건·사용자 해석
    반영 후속. 새 월별 흐름·성격 서사 생성 금지. 답변 후 shadow 감사(no_acknowledgment / excluded_reoffered /
    effect_assertion) 로그만.
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

### B6. Question Frame — 질문 이해 층 (소형 로컬 LLM, 2026-10-28 데굴님 승인)

질문 처리를 두 영역으로 나눈다.

| 영역 | 담당 | 구현 | 산출 |
|---|---|---|---|
| **결정론 영역** | 어휘·형태소 → 슬롯(대상·도메인·사건·시점·플래그) → planner → 엔진 → Graph RAG → Context Reduction | `query_parser` + 임베딩 보조기(rules-first) | IntentJson — **점수·간지·시점·판정의 유일한 출처**(절대 원칙 1·9) |
| **질문 이해 영역** | 질문 전체의 의도(무엇을·어떤 형태로 답해야 하는가) | 소형 로컬 LLM 1회 호출(`llm_config.question_frame`, Ollama `gemma4:e2b`, think=false, temperature 0) | `QuestionFrame` — enum 닫힌 집합만 |

**QuestionFrame 스키마**(`saju_shared_types/question_frame.py`): `ask_kind`(recommendation/judgment/timing/explanation/comparison/venting/meta/unknown) · `lifestyle_item`(food/color/clothing/direction/place/activity/grooming/none) · `answer_shape`(short_pick/analysis/compare_table/timeline/empathy_first/policy) · `brevity`(short/normal) · `topic_object`(≤20자 명사구). 간지·점수·날짜·판정 필드는 없다. **라우팅 필드 `lifestyle_item`이 집합 밖이면 프레임 전체를 버린다**; 형태 전용 필드(ask_kind·answer_shape·brevity)는 집합 밖 값을 기본값(unknown/analysis/normal)으로 정규화한다 — 소형 모델이 키 간 후보를 섞는 실측('침대헤드방향은?' → ask_kind "none") 때문이며, 이 셋은 지시문에만 쓰여 라우팅·점수에 닿지 않는다(2026-10-28).

**쓰임 두 가지만**: ①답 형태 지시문(`answer_shape`·`topic_object`) ②**룰이 Q1 FORTUNE_OVERVIEW + GENERAL 폴백으로 떨어진 턴**의 라우팅 보정(`is_rule_fallback`). 룰이 확정한 유형·도메인은 프레임이 덮어쓰지 않는다(데굴님 동의, 2026-10-28).

**도입 순서(필수)**: shadow(백그라운드 스레드, 로그 전용 — `question_frame_service.observe_async`, 답변·라우팅·지연 영향 0, `SAJU_QUESTION_FRAME_SHADOW=1`) → `scripts/measure_question_frame.py`로 불일치율·지연 측정(모집단 = `tests/fixtures/intent_eval.jsonl` + docs/08 예시 + 저장 채팅 발화) → 불일치 표본(`lifestyle_on_overview_fallback` 전수, 그 외 라벨 5건) 데굴님 검수 → 게이트 ON 은 별도 승인. 서버 부재·타임아웃·파싱 실패는 관측 실패 1건으로만 남고 기능을 막지 않는다(절대 원칙 11).

**게이트 ON(2026-10-28 데굴님 "우선 켜고")** — `SAJU_QUESTION_FRAME_GATE=1`, `question_frame_service.correct_if_fallback`: 룰 보강(임베딩 도메인·시점·비교 모드)까지 끝난 intent 가 `is_rule_fallback`이면 **동기** 호출(p50 ≈0.3~0.7s) 후 `apply_frame_correction` — `GATE_ITEMS` = color→Q10+`color_question`(+지목 색) / direction→Q10+`direction_question`(목적 전체 방향판) / food→Q10+`food_question`(+지목 음식) / place→RELOCATION 분야 분석. 보정 턴은 shadow 기록에 `applied:<item>` 라벨을 더한다. 폴백 턴이 아니면 동기 호출 자체를 하지 않고 shadow 로만 넘어간다(룰 확정 불변).
- **activity/clothing/grooming(A안, 2026-10-28 데굴님 "권장대로")** — 검색(1차·확장) 결과 셋 다 통용 명리 기준이 없다: 오행↔옷 대응은 **색**만 반복 확인(소재·패턴은 개인 블로그 수준), 이발·손톱 택일(통서 제두·정수족갑)은 현대 자료 없음, 행동 가부는 건제12신·황도흑도 같은 **택일 체계**만 존재. 그래서 새 사전을 만들지 않는다: `clothing` → 색 층(Q10 + `color_question`), `activity`·`grooming` → Q10 + `activity_question`(+`activity_topic`) 로 **답 형태 지시만**(`ACTIVITY_JUDGMENT_DIRECTIVE` — 그날 일운 길흉으로 '무난/조절/권하지 않음' 판정, 영역별 총운 금지, 기신이어도 '하지 말라' 단정 금지, 의료 조언 아님). 시점이 없으면('운동 계속 해도 돼?') too_broad 면제 대상이 아니라 B3 판정표대로 되묻는다. 건제12신·황도는 택일 엔진 확장으로 따로 다룬다(미착수).
- 동반 교정: B3 판정표에서 **오행 생활화 Q10(색·방향·음식 표지)은 시점·분야 없이도 too_broad 가 아니다**(원국 용희기구한 기준, 방향판·색/음식 표가 곧 답 — docs/19 §6-1). 이전엔 '어떤 방향이 좋을까'·'저녁 메뉴 추천해줘'·'커튼 색 추천해줘'가 전부 좁혀볼까요로 바운스됐다.
- 예열: 4.6GB 모델 콜드 로드는 3초 타임아웃 안에 끝나지 않고, 끊긴 연결은 Ollama 가 적재를 중단해 다음 호출도 콜드 로드가 된다. 앱 lifespan 에서 `warm_up()`(180초, 백그라운드) 1회 + 프로파일 `keep_alive: 24h`.
- 기동 절차: `scripts/ensure_ollama.sh`(멱등 — 플래그 OFF 면 no-op, 서버 응답 확인 → 없으면 사용자 레벨 `ollama serve` 기동 → 모델 없으면 pull, 실패해도 exit 0)를 `scripts/dev.sh`·`scripts/restart_backend.sh` 가 백엔드 기동 전에 호출한다. Ollama 부재 시 백엔드는 룰만으로 정상 기동(절대 원칙 11). 영구화는 systemd 유닛 `OLLAMA_HOST` 포트 지정(sudo, README).
- 측정 재현: `python scripts/measure_question_frame.py --db` — 2026-10-28 v2: 531건, 프레임 OK 515, p50 312ms/p95 394ms, `lifestyle_on_overview_fallback` 15(검수 13 진짜 결함 ≈87%). venting/meta/timing 라벨은 룰이 더 정확해 보정에 쓰지 않는다.

**운용 메모(실측 2026-10-28, RTX 4060 8GB)**: `think=false` 필수(켜면 추론 토큰이 출력을 비움) · Ollama `format`(JSON 스키마 grammar)은 쓰지 않는다(325ms → 2.8~15s, 결과 동일 — `parse_frame`이 검증) · 11434 는 WSL2 에서 Windows 예약 포트 범위라 `SAJU_OLLAMA_BASE_URL`로 포트를 지정한다.

배경: 룰 파서 1,490줄·임베딩 보조기 4종으로도 "오늘 점심은 뭘 먹는게 좋을까"가 Q1 폴백 → '오늘' 하나로 일운 총운이 되었다(2026-10-28 실로그). 어휘 추가는 사례 하나를 고치고 같은 계열('오늘 옷·머리·운동·약속')을 남긴다 — 그 계열을 질문 이해 층이 맡는다. docs/07 T3.1(경량 LLM 1차 + 룰 폴백)의 원설계를 "룰 1차 + 프레임 보정"으로 뒤집어 복원한 것이다.

---

### B7. 2026-10-28 실답 교정 — 이직 완료 사실·되물음 답·사실 단언형 이의·'몇 년도' 지평·설명 요청·해외 근무 층 (데굴님 승인)

실로그 두 스레드(web-mvrpyw6m·web-mvrq8ocg)에서 '이직'이라는 단어만으로 완료형·부정형 발화까지 앞으로의 이직
사건(`career_change`)으로 잡혀 2027년 진입 창 서술로 흐른 결함과, 해외 근무·설명 요청·'몇 년도' 질문의 경로 부재를
한 묶음으로 교정했다. 규칙 기반이며 LLM 판정은 없다(절대원칙 1).

| 항목 | 규칙 | SSOT |
|---|---|---|
| 완료형 이직 보고 | 한 절 안의 이직 어휘(이직·전직·입사·회사/직장 옮기-·새 직장 들어가-)+완료형 어미. 가정('이직하면')·소원('했으면')·부정('안 했')·제3자('남편이 이직') 제외. 파서는 보고 구간을 뺀 잔여 텍스트로 사건을 감지하고(`IntentJson.job_changed_reported`), '또/다시 이직'을 물으면 새 이직 사건 유지 | `saju_engines.job_change_report` |
| 사실 원장 `job_changed` | 단수 supersede 슬롯. 블록 주석: "이직은 이미 일어났다 — 앞으로의 이직·채용 제안·면접·스카우트 시기 서술 금지, 현 직장 적응·업무 부담·안정 시기 흐름으로" | `user_facts._FACT_RULES` |
| 채팅 | 이번 턴 보고 또는 원장 확정 사실이 있고 새 이직을 묻지 않으면: 의도의 이직·입사 사건 키 제거(지평·진입 두 칸 차단) + 후보에서 `career_change`·`job_gain` 제외 + 말미 `[이직 완료 …]` 지시 | `chat_service._JOB_CHANGED_DIRECTIVE` |
| 되물음 답 링크 | offer-slot/offer-answer 의 도메인 판정은 보고 구간을 뺀 잔여 텍스트로. 잔여에 분야 어휘('업무')가 남아도 직전 도메인이 GENERAL 이거나 같은 분야면 되물음 답으로 잇는다 | `conversation.link_question` |
| 되물음 답 → 시점 탐색 승계 | 직전이 TIMING_SEARCH('언제쯤 안정될까')이고 되물음(last_offer)이 있으며 이번 턴이 사건·자체 시점 없이 총운/분야 분석으로 떨어지거나 약한 후속 규칙으로 유형만 먼저 승계됐으면 TIMING_SEARCH 와 개방형 시점을 이어받는다(일반 시점 승계는 시작일 없는 open_when 을 잇지 않는다 — 2026-10-28 실로그 "그냥 일 적당히 있었으면 좋겠어") | `conversation.process_turn` |
| 소원·조건형 회고 제외 | 채팅 방향 판정은 과거 표지·축약 과거형 검사 전에 '~았/었/했/갔/왔/됐으면' 구간을 가린다("있었으면 좋겠어"의 '있었'이 회고 모드를 켜 2022~2024년을 되짚던 결함). 반사실 회고('갔었으면 어땠을까')는 뒤의 '어땠'이 남아 그대로 회고 | `chat_service._WISH_CONDITIONAL_RE` |
| 1인칭 본인 복귀 | A0 3단계 보강 — 별칭·관계어·인라인 출생정보가 없고 1인칭 표지(내가/나는/난/나도/나만/나의/제가/저는/저도/저의/내·제 사주·명식)가 있으면 직전 대상(동반자)을 상속하지 않고 본인으로 확정. 관점 표현('내가 보기엔'·'제 생각엔')·'우리/저희'는 제외. SELF 는 스레드 기준 명식 | `conversation._FIRST_PERSON_SUBJECT_RE` |
| 사실 단언형 이의 | '아니/아뇨/아니요' 머리 + (1인칭·이미·벌써) + 완료형 + 강조 종결(다니까/라니까/다고/거든/잖아/니까), 또는 '이미/벌써 … 완료형+강조 종결'. 1인칭이어도 이의. 강조 종결 없는 '아니 이직했어'는 보고(사실 원장) | `challenge_detect.ASSERTED_FACT_REBUTTAL_RE` |
| '몇 년도' 지평 | `YEAR_WHEN_RE`(몇 년도/몇 년에/어느 해) → Q3 + `open_when`(YEAR). horizon `year_when` = 향후 5년 연 단위(월 상세 0, 진입 두 칸 없음). 지시: 첫 문장 "향후 5년을 기준으로 보면", 창 밖 서술 금지, 끝 한 줄 "이후 기간은 연도 범위를 지정해 달라(예: 2032년부터 2036년까지)" | `time_parser.YEAR_WHEN_RE`·`horizon.YEAR_WHEN_SPAN_YEARS` |
| 이후 기간 지정 | '2032년부터 2036년까지는?'·'2032~2036년은?'(연도 범위만) → TIME_SHIFT(길이 무관). '2032년 이후는?' → 2032~2036 절대 창(종전 C8c 가 오늘+2032년으로 오파싱). '그 이후 5년은?'·'그 다음은?' → 직전 창 끝 다음 해부터 N년(기본 5; 직전이 개방형이면 올해부터 5년을 직전 창으로). 주제(query_type·사건·해외 근무 유형) 승계 | `conversation._YEAR_RANGE_ONLY_RE`·`_AFTER_WINDOW_RE`·`_inherit_after_window` |
| 설명 요청 | 요청 표지(쉽게/풀어서/자세히 설명·무슨 뜻) + 참조어('위의 내용') 또는 요청 문장 앞 인용 본문 15자 이상 → `dialogue_act="explain_request"`, `explain_target`=인용 본문. 인용 문장을 질문 조각으로 쪼개지 않고, 시점·사건을 비운다. 링크 DRILL_DOWN, 직전 유형·시점 미승계. 채팅: 후보·월별 표·지평 없음, too_broad 면제, `[설명 요청 …] [인용] …` 지시(여섯 문장 이내, 새 기간·삼재 금지) | `query_parser.detect_explain_request`·`chat_service._EXPLAIN_REQUEST_DIRECTIVE` |
| 해외 근무 층 | 유형 감지(주재원·발령/파견·출장/해외 취업/이민/미지정) → 도메인 직업(이민=이동), 주 사건 `relocation`, 동반 사건=유형별 직업 키. 채팅 말미 `[해외 근무 신호]` 연도표(이동 후보 최고점 × 직업 후보 최고점 → 강/중/이동만/직업만/없음 + 세운 십성 힌트) + 해석 규칙 6조. 설계 SSOT: `doc/v2_2/OVERSEAS_WORK_LAYER.md` | `saju_engines.overseas_work` |

회귀: `tests/unit/test_job_change_overseas_explain_20261028.py`(엔진 36건 + 채팅 dry-run 4건).

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