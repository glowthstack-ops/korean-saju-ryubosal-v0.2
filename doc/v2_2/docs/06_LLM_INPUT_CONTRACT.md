# 06. LLM 입력 계약 (Input Contract)

LLM에 전달되는 데이터의 표준 포맷. **이 계약을 벗어난 정보는 LLM에 넣지 않는다.**

## 구성 (4요소 — 모두 필수)

```
① 압축 간지달력 (calendar_context)   — LLM은 간지를 계산할 수 없으므로 반드시 제공
② 이벤트 후보 + 점수 (event_candidates)
③ 근거 경로 (evidence)               — Graph RAG 산출
④ 해석 제한 규칙 (style_rules)       — 금기 표현 + 템플릿 + 표현 강도
```

❌ 전체 간지달력 / 전체 사전 / 원시 그래프
✅ 선택된 기간의 압축 간지달력 + 이벤트 후보 + 근거 + 제한 규칙

## 표준 스키마

```typescript
interface LlmInput {
  userQuestion: string;
  resolvedIntent: IntentJson;            // 참조어 해석 완료된 intent

  birthChartSummary: {
    dayMaster: Stem;
    pillars: { year: string; month: string; day: string; hour: string };  // '庚申' 형태
    voidBranches: Branch[];
    strength: string;                    // '중화신강'
    usefulGods: { yongsin: Element[]; gisin: Element[] };
  };

  calendarContext: {
    daewoon: { period: string; ganji: string; ageRange: string }[];       // 장기 질문이면 전체
    selectedYears?: { year: number; ganji: string; daewoon: string; reasonSelected: string }[];
    selectedMonths?: { period: string; ganji: string; year: string }[];   // 선택 세운 내에서만
    selectedDays?: { date: string; ganji: string }[];                     // 택일에서만
  };

  eventCandidates: {
    eventKey: EventKey;
    period: string;
    ganji: string;                       // 해당 시점 간지 — 반드시 포함
    daewoonContext: string;              // 대운 맥락 — 반드시 포함
    score: number;
    confidence: string;
    polarity: string;
    timeline?: EventTimeline;            // progress 이벤트
    realizationScore?: number;           // Manifestation 결과
    likelyForms?: string[];
  }[];

  evidence: {
    eventKey: EventKey;
    readablePaths: string[][];           // 사람이 읽는 근거 경로
    contradicts: string[];               // 반대 근거 — 단정 방지용
  }[];

  pastValidation?: { summary: string; calibratedConfidence?: number };

  styleRules: {
    prohibited: string[];                // ["반드시 이직한다", "무조건 헤어진다", "확정적으로 발생한다"]
    templates: string[];                 // 해당 이벤트×polarity 템플릿
    toneGuide: string;                   // 점수→표현 강도 가이드
    llmInstruction: string;              // 예: "이직 가능성이 높다고 표현하되 확정 금지.
                                         //      환경 변화 압박과 선택 가능성을 구분해 설명할 것."
  };

  outputFormat?: { type: 'report' | 'ranked_dates' | 'timeline' | 'slots'; slots?: string[] };

  persona: {                                        // docs/11 5장 — 문체 전용, 사실 불변
    config: PersonaConfig;
    promptBlock: string;          // 5-3 템플릿으로 사전 조립된 블록 — LLM이 즉석 작문하지 않음
    resolvedHonorific: string;
  };
  userProfileContext?: {                            // docs/11 — 해당 질문에 필요한 필드만 (전체 주입 금지)
    occupationCategory?: string;  // O01~O18
    residenceRegion?: string;
    maritalStatus?: string;
  };
  sectionMode?: {                                   // 보고서 섹션 생성 시에만
    productCode: 'RPT_FULL' | 'RPT_FOCUS';
    sectionId: string; sectionTitle: string;
    targetChars: { min: number; max: number };
    fixedFacts: string[];        // 선행 섹션 확정 사실 (용신 등) — 모순 금지
  };
  budget: { maxInputTokens: number; maxOutputChars: number };  // docs/09 8장 한도
}
```

## 점수 → 표현 강도 매핑 (toneGuide 기본)

| score | 표현 |
|---|---|
| 85+ | "~신호가 매우 강합니다" |
| 70~84 | "~가능성이 높습니다" |
| 55~69 | "~흐름이 나타날 수 있습니다" |
| 40~54 | "~조짐이 약하게 있습니다" |
| <40 | 언급 생략 또는 "뚜렷한 신호는 없습니다" |

## 표현 원칙 (시스템 프롬프트에 고정)

1. 사건 발생이 아니라 **"변화 에너지의 활성화"**로 표현
2. Trigger → 진행 → 결과 구조로 설명 (예: "6월 생각 강해짐 → 7~8월 행동 가능성 → 9~10월 결과")
3. windfall/speculation: "당첨/수익" 단정 금지 → "단기 재물 변동성 / 투기 충동 / 예상 밖 수입·지출"
4. 제공된 간지·점수·근거 외의 명리 계산 시도 금지 — 데이터에 없으면 "해당 정보는 제공되지 않았다"로 처리
5. 기존 프롬프트 시스템의 `[필수 준수]` 블록 패턴 유지: 지시는 명령형으로, 데이터와 분리
6. 페르소나는 어투만 결정한다. 점수·날짜·간지·판정은 페르소나와 무관하게 동일해야 하며, 위반은 정합성 검사(docs/10 7장)에서 차단된다
7. LLM은 docs/09 0장의 "LLM 금지 작업" 7항목을 수행하지 않는다 — 입력에 없는 수치·간지·규칙이 필요하면 "제공되지 않음"으로 처리

## 좋은 입력 예 (요약)

```
"2026년 6월은 甲午월이고(壬辰대운 내), 원국 己日干과 甲己合이 발생하며,
午火가 인성을 강화하고, 巳亥沖 구조와 공망 巳 활성화가 함께 있으므로
career_change 78점, relocation 72점으로 계산되었다."
```

LLM은 이 사실들을 자연어로 풀어 설명만 한다.
