# 02. 엔진 상세 스펙

모든 엔진은 순수 함수 형태를 지향한다: `(input, dictionaries, options?) => output`.
입출력 타입은 `src/types/`에 정의하고 zod로 런타임 검증한다.

**주의**: 만세력 엔진에서 추출할 수 있는 데이터 리스트릃 확인하고, 아래 언급된 엔진들의 필요도와 보강여부를 재검증 후 실제 진행 게획에 반영한다.

---

## E0. 만세력 엔진 (기존 — 수정 금지)

기존 엔진의 출력을 신규 엔진들이 소비할 수 있도록 **어댑터 타입만** 추가한다.

```typescript
interface ManseResult {
  birthInfo: { datetime: string; calendarType: 'solar' | 'lunar'; gender: 'M' | 'F' };
  chartVariant: 'original' | 'twin_adjusted';   // 쌍둥이 시주 조정 (docs/11 2-2)
  twinShift: number;                            // 0 = 조정 없음. 시주만 (order-1)칸 전진, 일/월/년주 불변
  chart: {
    year: Pillar; month: Pillar; day: Pillar; hour: Pillar;
  };
  dayMaster: Stem;                    // 일간 (예: '己')
  voidBranches: Branch[];             // 공망 (예: ['辰','巳'])
  daewoonList: DaewoonPeriod[];       // 대운 전체
  // 세운/월운/일운은 기간 요청 시 생성
}

interface Pillar {
  stem: Stem; branch: Branch;
  hiddenStems: Stem[];                // 지장간
  tenGod: TenGod;                     // 십성
  twelveStage: TwelveStage;           // 12운성
  shinsal: string[];                  // 신살
}

interface GanjiCalendarEntry {
  level: 'daewoon' | 'year' | 'month' | 'day';
  period: string;                     // '2026' | '2026-06' | '2026-06-10' | '2026~2035'
  stem: Stem; branch: Branch;
  relationsWithChart: RelationHit[];  // 원국과의 합충형파해/공망활성 등
}

interface RelationHit {
  relationId: string;                 // 'rel_甲己合', 'rel_巳亥沖' 등 사전 키
  type: RelationType;                 // stem_combination | branch_clash | ...
  participants: { from: GanjiRef; to: GanjiRef }; // 운 측 / 원국 측 위치 포함
}
```

---

## E1. 사주 구조 분석 엔진 (chart-analysis)

**역할**: 원국의 구조 판정. 모든 후속 엔진의 보정 기준.

```typescript
interface ChartAnalysis {
  strength: '극신강' | '태신강' |'신강' | '중화신강' | '중화' | '중화신약' | '신약' | '태신약' |'극신약';
  gyeokguk: { type: string; isSpecial: boolean };   // 격국, 종격/화격 여부
  usefulGods: {
    yongsin: Element[];     // 용신
    huisin: Element[];      // 희신
    gisin: Element[];       // 기신
    gusin: Element[];       // 구신
    hansin: Element[];      // 한신
  };
  distribution: {
    elements: Record<Element, number>;
    tenGods: Record<TenGod, number>;
  };
  structuralFlags: string[]; // '인성과다', '재다신약', '관살혼잡', '식상생재' 등
}
```

**주의**: 용신 판정은 기존에 정리한 용신 산출 방법론(신강약 → 억부/조후/통관, 종격 예외, 습토/조토 구분, 제살태과 등)을 룰로 코드화한다. 자동 판정 신뢰도가 낮은 케이스는 `confidence` 필드로 표시하고 LLM 입력에 그대로 전달해 단정을 피하게 한다.

---

## E2. Event Scoring Engine (event)

**역할**: 특정 시점(대운/세운/월운/일운)에 어떤 이벤트가 발생할 가능성이 있는지 점수화. **가장 중요한 엔진.**

**입력**: ManseResult + ChartAnalysis + GanjiCalendarEntry[] + 사전(event_mappings, favorability_rules, relations)

**출력**:

```typescript
interface EventCandidate {
  eventKey: EventKey;                 // 'career_change' 등 — Event Taxonomy 참조
  eventType: 'progress' | 'instant' | 'hybrid';
  period: string;                     // '2026-06'
  score: number;                      // 0~100
  confidence: 'low' | 'medium_low' | 'medium' | 'medium_high' | 'high';
  polarity: 'positive' | 'negative_or_forced' | 'conditional' | 'neutral';
  signals: Signal[];
  evidencePath: string[];             // Graph RAG 근거 경로 (노드 ID 순서)
}

interface Signal {
  type: 'heavenly_stem_combine' | 'branch_clash' | 'void_activation'
      | 'ten_god_activation' | 'shinsal' | 'daewoon_transition' | string;
  name: string;                       // '甲己合'
  effect: string;                     // '직업/책임/환경 변화 자극'
  weight: number;                     // 양/음수 가능 (예: 공망 활성 -8)
}
```

**점수 산출 규칙**:
1. 관계 룰 사전에서 base_score를 가져온다.
2. favorability_rules로 보정 (용신 +, 기신 → polarity 변경 + 감점/강제성).
3. 동일 이벤트에 복수 신호 → weight 합산 후 0~100 클램프.
4. 계층 필터: 세운은 score≥70 또는 Top5만 다음 단계로.

### Event Taxonomy (EventKey 표준)

```
career_change, promotion, resignation, business_start
relationship_start, relationship_end, marriage, childbirth
relocation, contract, document
wealth_change ─┬─ income_change
               ├─ expense_risk
               ├─ windfall          # 로또 등 — 표현 제한 필수
               ├─ speculation_risk  # 주식 — 변동성/리스크 경고 중심
               └─ asset_volatility
education_start, education_complete, exam
health_issue, surgery, family_change, lawsuit, travel
```

---

## E3. Event Form Engine (event-form)

**역할**: 같은 신호도 발현 형태가 다름 (사해충 → 이사/출장/직무이동/장거리연애).

```typescript
interface EventFormResult {
  eventKey: EventKey;
  forms: { name: string; prob: number }[];  // prob 합 ≤ 1.0
}
```

형태 확률은 form 사전 + Self Profile + Reality Context로 보정.

---

## E4. Timeline Engine (timeline)

**역할**: "6월 이직운 = 6월 퇴사" 오해 해소. progress 이벤트에만 적용.

```typescript
interface EventTimeline {
  eventKey: EventKey;
  activationWindow: { start: string; end: string };   // '2026-06' ~ '2026-11'
  phases: { period: string; stage: 'awareness' | 'exploration' | 'action' | 'decision' | 'completion' }[];
  scores: { interest: number; action: number; completion: number };
}
```

stage 매핑 룰: 트리거 신호(합) 발생 월 = awareness, 충/이동 신호 강화 월 = action 등 신호 유형 → 단계 매핑 사전을 사용.

---

## E5. Self Profile Engine (self-profile)

**역할**: 성향이 이벤트의 **현실화 방식**을 결정. 성격검사(MBTI화) 금지.

```typescript
interface SelfProfile {
  decisionStyle: 'impulsive' | 'deliberate' | 'avoidant' | 'consensus';
  riskTolerance: number;        // 0~100
  executionPower: number;       // 0~100
  axes: { relationship: string; money: string; work: string; stress: string };
  manifestationTendency: string; // 'accumulate_then_move' 등 — 통변 문구 재료
}
```

산출 근거: 십성 분포, 일간 특성, 격국, 구조 플래그. 모든 축에 근거 노드 첨부.

---

## E6. Manifestation Engine (manifestation)

**역할**: 이벤트 발생 가능성 ≠ 현실화. 세 요소의 결합.

```typescript
interface ManifestationResult {
  eventKey: EventKey;
  eventScore: number;             // E2 결과
  profileModifier: number;        // E5 기반, 예: -15
  contextModifier: number;        // Reality Context 기반 (사용자 입력: 현 직업/연애/경제 상황)
  realizationScore: number;       // 합산 클램프
  likelyForms: string[];          // '이직 제안 검토', '역할 변경' 등
}
```

Reality Context의 1차 소스는 2단계 프로필(docs/11 — occupation/maritalStatus/children/residence)이고, 2차 소스는 대화 추출 갱신(F9, 사용자 확인 후)이다. 없으면 modifier 0 + confidence 하향. 필드 부재로 오류를 던지는 구현 금지 (docs/11 4장).

---

## E7. Past Validation Engine (past-validation)

**역할**: 과거 사건 복원 → 신뢰 형성. **미래 예측보다 먼저 실행/노출.**

**입력**: ManseResult + 과거 N년 간지달력
**출력**:

```typescript
interface PastValidationResult {
  candidates: { yearRange: string; eventKey: EventKey; score: number; evidencePath: string[] }[];
  // 사용자 확인 후:
  userFeedback?: { matched: boolean; actualEvent?: string }[];
  calibratedConfidence?: number;  // 신뢰도 % — 이후 미래 예측 표현 강도에 반영
}
```

**금지**: 콜드리딩식 두루뭉술 표현. 모든 후보에 evidence path 필수. 사용자 피드백은 cases.jsonl에 적재해 회귀 테스트·가중치 보정 자료로 사용.

---

## E8. Advice Engine (advice)

**역할**: "그래서 뭘 해야 하나"에 답. 이벤트+타임라인+프로파일 기반 행동 조언.

```typescript
interface AdviceResult {
  eventKey: EventKey;
  advice: { period: string; action: string; rationale: string }[];
  cautions: string[];             // '감정적 퇴사 금지' 등
}
```

조언 문구는 templates 사전에서 가져오되 LLM이 자연스럽게 재서술. 의료·법률·투자 단정 조언 금지 (특히 windfall/speculation 계열은 변동성 경고 톤 고정).

---

## E9. Lifestyle Fortune Engine (lifestyle)

**역할**: 일일/주간/연간 종합운. Event Engine보다 가볍고 반복 호출 최적화.

종합운은 사용자 intent가 약하므로 **고정 슬롯 템플릿**을 시스템이 부여:

```
일일: 핵심기운 / 일·공부 / 돈·소비 / 관계·연애 / 건강 / 주의행동 / 활용법
주간: 핵심흐름 / 좋은날 / 주의할날 / 일·돈·관계·건강 / 행동전략
연간: 핵심주제 / 상·하반기 / 직업 / 재물 / 관계 / 건강 / 주의시기 / 기회시기
```

```typescript
interface LifestyleFortune {
  period: string;
  fortuneType: 'daily' | 'weekly' | 'monthly' | 'yearly';
  scores: { work: number; money: number; relationship: number; health: number; decision: number };
  summaryTheme: string;
  slots: Record<string, SlotContent>;  // 템플릿 슬롯별 점수+신호
}
```

---

## E10. Date Selection Engine (date-selection) — 택일

**역할**: 날짜 후보 **랭킹** 문제. 상위 흐름이 허용하는 기간 안에서 실행일 최적화.

**계산 순서 (고정)**:
```
1. 대운/세운: 이 사건을 해도 되는 큰 흐름인가?       → macro_flow_score
2. 월운: 이번 달이 이 사건에 맞는 달인가?            → month_fit_score
3. 일운: 실행하기 좋은 날 랭킹                       → day_execution_score
4. 금기일/회피일 필터 (Risk Avoidance)
5. 손없는 날/공휴일/요일 등 Calendar Rule
6. 사용자 현실 제약 (주말만 가능, 업체 예약일 등)     → reality_fit_score
7. 목적별 가중치 합산 → 최종 랭킹
```

```typescript
interface DateCandidate {
  date: string;
  purpose: EventKey;
  scores: {
    macroFlow: number; monthFit: number; dayExecution: number;
    calendarRule: number; realityFit: number; final: number;
  };
  riskScore: number;
  reasons: string[];
  cautions: string[];
  recommendation: 'recommended' | 'acceptable' | 'avoid';
}
```

**목적별 가중치 프로파일 (purpose_profiles 사전)**:

| 목적 | 비중 큰 요소 |
|---|---|
| 이사 | 월운 + 일운 + 손없는 날 (hybrid: 준비 progress + 당일 instant) |
| 계약 | 일진 문서성 + 충돌 회피 |
| 결혼 | 세운/월운 관계 안정 + 충 회피 |
| 수술 | 일운 충극 회피 + 건강 리스크 회피 |
| 개업 | 대운/세운 비중 큼 |
| 주식/로또 | 일운 비중 축소, 변동성·과몰입 경고 중심 |

### E10-a. Calendar Rule Engine
손없는 날, 절기, 명절, 공휴일, 요일, 음력일, 민속 불리일. **명리 계산이 아닌 별도 규칙 데이터** (`calendar/son_eomneun_nal.json` 등). 손없는 날은 음력 끝자리 9·0일 규칙으로 계산 가능하므로 데이터+계산 혼합.

### E10-b. Risk Avoidance Engine (금기일/회피일)
좋은 날 선별과 별개로 피해야 할 날을 계산: 이사 금기일, 계약 금기일, 수술 회피일, 투자 과열일 등. 필터로 작동.

### E10-c. Reality Constraint
사용자 입력 제약(주말만, 오전만, 업체 가능일). "좋은 날"이 아니라 **가능한 날 중 가장 좋은 날**을 고른다.

---

## E11. Event Type Classifier

**역할**: 질문/이벤트를 progress / instant / hybrid로 분류. 오케스트레이터가 호출하며, 분류 결과에 따라 파이프라인이 갈린다.

```typescript
interface EventTypeResult {
  eventKey: EventKey;
  eventType: 'progress' | 'instant' | 'hybrid';
  progressRequired: boolean;
  instantRequired: boolean;
}
```

기본 분류는 Event Taxonomy 사전에 정적으로 정의하고, 질문 문맥("이사 준비" vs "이사 날짜")으로 오버라이드.

---

## E12. Competition Engine (경쟁/승부 비교) — 신규 (실측 기반)

**근거**: 실사용 로그에서 동반자 기능을 활용한 선거 당선 예측, 시험 합격 경쟁, 오디션 등 승부 질의가 실재 (docs/08 E). "나를 제외하고 동반자 두 사람만으로", 3인 이상 다자, 판정일 명시("투표일 6/3, 개표 6/4") 패턴 포함.

**입력**: SubjectRef[] (2인 이상) + 판정 기준일(anchor_date) + 경쟁 이벤트(eventKey: election/exam/audition...)
**처리**:
```
1. 대상별 판정일 기준 운세 강도 (일운+월운+세운, 해당 이벤트 신호 가중)
2. 대상별 해당 이벤트 evidence path
3. 상대 비교 → 우열 + 격차 폭
```
**출력**:
```typescript
interface CompetitionResult {
  anchorDate: string;
  candidates: { subject: SubjectRef; strengthScore: number; evidencePath: string[]; dataQuality: 'full' | 'no_hour' }[];
  relativeGap: 'clear' | 'narrow' | 'inconclusive';
  prohibitions: string[];   // 당락·승패 단정 금지 — templates 고정
}
```
**정책 (templates 레벨 고정)**:
- "X의 당일 운이 상대적으로 강하다" 수준까지만. 당락/승패/순위 확정 표현 금지.
- 실존 공인 비교: 출생 시각 미상이 일반적 → no_hour 모드 + 신뢰도 한계 명시. 선거·명예 관련 단정 리스크 차단.
- "당선되면 이후 운까지"(조건 분기, docs/08 B8): 조건 성립 시나리오를 별도 섹션으로 풀이.

## E13. Compatibility Engine (궁합/관계) — 신규

**근거**: compatibility 111건 + 텍스트상 궁합/관계 질의 88건+. 관계 유형이 다양함 (부부/연인/부모자식/형제/친구/동료/동업/상사).

**입력**: SubjectRef 2인 + relationType
**처리**: 관계 유형별로 보는 축이 다르다 (relation_profiles 사전):

| relationType | 주 분석 축 |
|---|---|
| spouse/lover | 일주 상호작용, 배우자궁, 재성↔관성, 합충, 도화/홍염 |
| parent_child | 인성↔식상 축, 육친 궁위, 기질 차이("기질적으로나 성향은 서로 어때") |
| business_partner | 재성/식상 보완, 비겁 경쟁, 신뢰 축 ("동업해보는 건 어떨까") |
| colleague/boss | 관성 구조, 갈등/보완 |

**출력**: 적합도(축별) + 관계 패턴 + 갈등 요소 + 운영 조언. 다자 ranking 모드는 pairwise 결과를 정렬해 제공하되, "끝난 인연 회고"(실측 존재) 같은 과거형 비교도 지원.

## E14. Subject Manager (동반자 관리) — 신규 인프라

**역할**: 등록 동반자 CRUD + 별칭 매핑 + 인라인 임시 인물 수명 관리.

```typescript
interface Companion {
  companionId: string;
  name?: string;
  aliases: string[];            // "1호", "신랑", "아가" — 대화에서 학습 (A9)
  relationToUser: RelationType;
  birth: { date: string; time?: string; calendarType: 'solar' | 'lunar'; birthplace?: string };
  gender?: 'M' | 'F';
  isMinor: boolean;             // 표현 제한 정책 연동 (docs/08 G2)
  multipleBirth?: { total: number; order: number };   // 쌍둥이 — docs/11 2-2 규격 동일 적용
  chartVariantState?: ChartVariantState;
  manseCache?: ManseResult;     // 등록 시 1회 계산 캐시 (active 변형 기준)
}
```

규칙:
- 인라인 임시 인물(inline_temp)은 세션 스코프로 유지하되, 재등장 시 등록 전환을 제안.
- UI 등록/수정 이벤트는 대화 타임라인에 삽입 — "등록했어" 발화 연결용.
- 시각 미상은 3주 모드 플래그를 ManseResult에 전파. birthTimeApprox(대략 시간대) 제공 시 시주 후보 병기 모드 (docs/11 2장).
- 2단계 프로필의 자녀 정보(children.items)에 출생정보가 있으면 동반자 등록을 제안하고, 등록 시 Companion으로 전환 + isMinor 자동 판정.

## E10 보강 — Date Selection 확장 (실측 반영)

1. **방위 결합 (docs/08 D2-1)**: 추천 날짜에 방위 적합도 결합. 기준점은 사용자 현 거주지(locationBase) — "지금 사는 곳은 일산 동구인데 꼭 정남쪽으로만?" 같은 상대 방위 질의 처리. 방위 미정이면 전방위 또는 방위별 분리 제시.
2. **시진(時) 단위 (C17)**: "로또 사러 가기 좋은 시간대" — 선정일 내 12시진 적합도. granularity: 'hour' 지원.
3. **체인 스케줄링 (C9)**: "계약 후 2~3개월 안에 이사, 2027년 2월까지 완료" — 데드라인 역산으로 후행 이벤트 창을 먼저 확정하고 선행 이벤트 창을 배치하는 다단계 모드.
4. **금지 출력**: 로또 번호 생성 요청은 어떤 형태로도 거부 (실측: "로또번호도 찍어줄 수 있나?"). 날짜/방향/시간대 추천으로 대체 + 당첨 단정 금지.

## E8 보강 — Advice/Remedy 확장 (fortune_remedy 105건)

remedy 하위 6분기(docs/08 D-3)를 advice 사전 카테고리로 구현: 시기 회피 / 주의 행동 / 기질 보완 / 구조 보완(공망 등) / 오행 생활화(색·방향·음식) / 민속 비방(단정 회피, 행동 전환). 의료·법률·투자 관련은 전문가 안내 문구 고정.
