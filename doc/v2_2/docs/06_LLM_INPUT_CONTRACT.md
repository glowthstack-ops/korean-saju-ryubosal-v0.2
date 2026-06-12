# 06. LLM 입력 계약 (Input Contract)

LLM에 전달되는 데이터의 표준 포맷. **이 계약을 벗어난 정보는 LLM에 넣지 않는다.**

## 구성 (5요소 — 모두 필수, v2.2.1 개정)

```
① 압축 간지달력 (calendar_context)   — LLM은 간지를 계산할 수 없으므로 반드시 제공
② 이벤트 후보 + 점수 (event_candidates)
③ 근거 경로 (evidence)               — Graph RAG 산출 + 해석 사전 텍스트 결합(의미 단계 포함, docs/04 7장 형식)
④ 해석 제한 규칙 (style_rules)       — 금기 표현 + 템플릿 + 표현 강도
⑤ 명식 구조 + 해석 자료 (chart_interpretation) — v2.2.1 신설:
   주별 십성·십이운성·신살·원국 내 합충·병존·간여지동 플래그(엔진 계산) +
   interpretations/ 사전 발췌(일주 엔트리 + 질문 주제 관련 십성·관계·신살 의미 텍스트)
```

❌ 전체 간지달력 / 전체 사전 / 원시 그래프
✅ 선택된 기간의 압축 간지달력 + 이벤트 후보 + 근거 + 제한 규칙 + 주제 관련 해석 발췌

## 프롬프트 2층 구조 & 캐시 (v2.2.1 신설)

직렬화 순서를 고정해 provider 프롬프트 캐시(Gemini implicit/explicit caching, OpenAI 자동
prompt caching)를 적중시킨다. **고정 prefix에는 날짜·세션 ID 등 가변 값을 넣지 않는다.**

```
[고정 prefix — 사용자별로 멀티턴·전 섹션에서 바이트 단위 동일 (캐시 대상)]
 1. 시스템 프롬프트 (전 사용자 공통)
 2. [원국·명식 구조]  : 4주 + 주별 십성·십이운성·신살 + 원국 내 합충·병존·간여지동·공망
 3. [명식 해석 자료]  : 일주 사전 엔트리 + 원국 활성 십성·신살·관계 해석 텍스트 발췌
──────────────────────────────────────────────────────────
[동적 suffix — 질문마다 변경]
 4. 기준 시점 / 간지달력(압축) / 이벤트 후보 / 근거 경로 / 월별·택일 / 지시 / 질문
```

총운 22섹션·집중 8섹션 생성처럼 동일 prefix 반복 호출이 확정된 경우 explicit caching을 사용한다.
토큰 한도는 docs/09 8장(v2.2.1 개정표)을 따른다 — 품질 우선, 고정 prefix 비용은 캐시로 흡수.

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

  chartInterpretation: {                 // ⑤ v2.2.1 신설 — 고정 prefix에 직렬화 (캐시 대상)
    pillarDetails: {                     // 주별 구조 (엔진 계산값)
      palace: 'year' | 'month' | 'day' | 'hour';
      ganji: string;
      stemTenGod: string;                // 천간 십성 (일간 주는 '일원')
      branchTenGod: string;              // 지지 본기 십성
      twelveStage: string;               // 십이운성
      sinsal: string[];                  // 해당 주 활성 신살
    }[];
    natalRelations: string[];            // 원국 내 합충형파해·병존·간여지동·복음 플래그
    iljuEntry: IljuInterpretation;       // interpretations/ilju.json 해당 엔트리 전체
    excerpts: {                          // 질문 주제 관련 해석 발췌 (Planner dictionaryScope 선별)
      kind: 'ten_god' | 'relation' | 'sinsal' | 'twelve_stage' | 'stem_branch';
      key: string;                       // '정관' | 'rel_甲己合' | ...
      text: string;                      // 사전의 해석 텍스트 (의미·발현·비유)
    }[];
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
4. **계산 금지 / 의미 서술 허용의 분리 (v2.2.1 개정)**: 간지·합충 성립·점수·날짜의 계산이나 변경은
   여전히 금지("해당 정보는 제공되지 않았다"로 처리). 단, **제공된 ⑤ 명식 해석 자료·근거 경로의
   의미 텍스트는 적극적으로 엮어 풍부하게 서술해야 한다** — 점수 낭독이 아니라 "이 글자가 당신에게
   무엇이고, 지금 들어온 글자와 어떤 관계를 맺어 이런 신호가 되는가"의 이야기로 설명한다
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
