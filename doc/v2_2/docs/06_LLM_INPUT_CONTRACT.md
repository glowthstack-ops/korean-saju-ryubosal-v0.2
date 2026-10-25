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
    pillars: { year: string; month: string; day: string; hour?: string };  // '庚申' 형태. 시주 미상이면 hour 생략
    // 시주 미상(2026-10-06, HOUR_UNKNOWN_POLICY.md): 3기둥 기준. 12시진 후보가 갈리는 항목은
    // strength/geokguk 에 '미확정(시주 미상 — 후보 …)'로 표기하고 usefulGods 는 비운다(길흉·처방 금지).
    hourUnknown?: boolean;
    hourUnknownItems?: ('strength_band' | 'geokguk' | 'useful_gods')[];
    hourUnknownNote?: string;              // 엔진 생성 1회 고지 문구
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
    incomingNote?: string;               // '해석' — 운 천간 십성 유입 1문장(행동 권유의 결)
    stageNote?: string;                  // '결(12운성)' — 12운성 유입 1문장(흐름·결과 서술의 결)
                                         // 둘 다 표현 결 층(2026-09-10, docs/17 §23 이식) — 문체 전용,
                                         // 점수·판정·간지 사실 불변. 리포트는 기간 클러스터의
                                         // '운 결(문체 전용): 행동=… / 흐름=…' 줄로 같은 정보를 싣는다.
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
                                         // + 표현 결 지시(TONE_LAYER_DIRECTIVE, 2026-09-10): 해석=행동 결,
                                         //   결(12운성)=흐름 결. stageNote 가 하나라도 있을 때 chat 에 부착,
                                         //   report 는 전 섹션 공통 prefix 에 부착.
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

## 부록 — 월·연 총운 입력의 사건 신호 보강 (2026-10-16 데굴님 승인, 2026-06-12 결정 부분 수정)

- 배경: 월·연 총운(`period_fortune`) 경로는 2026-06-12 결정으로 사건 후보를 비우고 생활 슬롯 점수만 실었다. 실사례(2026-10 권고사직 명식, "이번달 운세는 어때?")에서 '일·직업 100점' + '강한 용신운'만 남아 LLM이 '직장 유리·주도권'으로 읽었고, 엔진의 이동 후보(비겁 용신 시드)와 `[이동 주체 미상]` 지시문이 빠졌다.
- 보강 3종(`saju_engines.period_fortune_signals`, 서술 전용·점수 불변):
  1. **주요 사건 후보 Top-N(3)** — 해당 월(`YYYY-MM`)·연(`YYYY`) 후보를 점수순으로 `[이벤트 후보]` 블록 형식 그대로 싣는다(일 총운은 비움). 이동 후보가 실리면 `[이동 주체 미상]` 지시문이 후보 목록 기준으로 자동 부착된다.
  2. **슬롯 '주 신호'** — 슬롯 줄 끝에 `— 주 신호: 사건 라벨(방향[·이동·주체 미상])`을 붙이고 "(슬롯 점수는 활성 강도이지 길흉·유불리가 아니다)" 고지를 단다. 슬롯→도메인: 일·직업/직업=career·education, 재물=wealth, 관계·연애/관계=relationship, 건강=health.
  3. **이동 흐름 줄(조건부)** — 비겁 이동 시드(PEER_YONGSIN/GISIN_MOBILITY)가 있는 기간에만, 시드 역할(용신/기신) × **이후 운의 흐름**(다음 월운 3개 + 다음 세운 / 연: 다음 세운 2개의 용기신 역할 가중 평균 → 긍정/부정/엇갈림) 6칸 사전 `interpretations/mobility_flow_text.json`에서 한 칸을 고른다. 데굴님 정정(2026-10-16): 이동 뒤 기반이 좋은가는 비겁이 용신이라는 이유만으로 정해지지 않는다 — '나쁘지 않게 흐를 수 있다'는 **용신 + 이후 흐름 긍정**에만 허용(lint 고정). `transit_peer_mobility_text.json`의 용신·기신 문구도 "이동 뒤 흐름은 이후 운이 정한다"로 정정.
- 지시문(`_MONTHLY_INSTRUCTION`·`_YEARLY_INSTRUCTION`): 후보의 사건 종류를 해당 슬롯 서술에 활성화·가능성으로 반영, '강한 용신운'만으로 분야 유리 단정 금지, 이동 주체 미정, 이동 뒤 흐름은 [이동 흐름] 줄 판정만 근거.
- 회귀: `tests/unit/test_period_fortune_signals.py`(dry-run 월·연·일 경로, 선별 상한, 슬롯 주 신호, 이후 흐름 판정 3종, 역할×흐름 5칸 문구, 시드 없음 침묵, 사전 lint, 비겁 문구 정정).

## 부록 — 연 총운 '월주 상대 관점' 환경 블록 + 시대 기운 연도 (2026-10-25 데굴님 승인)

- 블록 `[월주 상대 관점 — 시절이 만드는 환경 (…)]` — 세운 전용. `[해당 연 총운]` 의 `세운:`(일간 기준 십성·십이운성 = 태도 입력)·`운 요약:` 줄 **바로 뒤**에 사실 줄 5개(환경 자리 / 월간 기준 세운 십성·12운성 / 세운 천간 기준 월주 십성·12운성 / 지지 관계 / 천간 관계 / 통근 비교) + 서술 규칙 1줄. 어휘는 전부 `interpretations/yearly_environment.json`에서 고르기만 한다(즉석 작문 없음). 월·일 총운에는 나가지 않는다.
- 지시문(`_YEARLY_INSTRUCTION`): 블록이 있으면 ①시절이 만드는 환경 한 문장 → ②`[세운:]` 줄로 그 환경에서 취하기 쉬운 태도 한 문장 → ③둘을 합친 한 해 주제를 **첫 판정 문단 바로 뒤**에 둘 것. 환경·태도는 길흉이 아니며 용희기신 판정을 바꾸지 않는다(답변 계약의 3진 판정 선언이 먼저).
- 리포트 F-11·Y-04: `[해당 연 세운 grounding — YYYY 干支 · 엔진 확정값(채팅 패리티)]` 블록(세운 줄·운 요약·환경 블록·형충회합·신살·공망·서술 순서)을 `[대운표]` 뒤, 시대 기운 앞에 싣는다. 섹션 입력 상한은 20,000→22,000(docs/09 §8 3차 상향).
- 시대 기운 헤더·연도: `[YYYY년 干支年 시대 기운 — …]` 로 연도를 박고(종전 '올해' 고정 라벨), 채팅은 질문이 단일 연(내년·YYYY년)을 지정하면 그 해를 쓴다(`chat_service._era_year`). 2026-10-25 실측: '내년 운세'에 2027 丁未 총운 블록과 함께 2026 丙午 시대 기운이 붙던 결함 교정.
- 계층 블록 라벨: 원국 참여자가 천간이면 '원국 월간 壬'(`participant_label`), 지지면 '원국 월지 寅'. 종전 `LAYER_KO` 궁위 고정 라벨이 丙壬沖의 壬을 '월지'로 표기하던 입력 계약 결함 교정.

## 부록 — 관계 확정 문장의 참여 글자 층위 라벨 + 층위 라벨 감사 (2026-10-25 데굴님 승인)

- 배경: 실답('올해 운세', 대운 壬辰·세운 丙午)에서 LLM 이 丁壬合을 "대운의 壬와 세운의 丁"으로 썼다 — 세운에 丁은 없고 실제는 원국 월간 丁 × 대운 壬. `[관계 확정 문장]`은 "두 글자가 손을 잡고"처럼 참여 글자 층위 없이 나갔고, 계층 블록은 연 총운에서 대운 composite(`DW:壬辰`)를 만들지 않아(`_YEAR_LEVELS`=MONTH·YEAR·NATAL, scope 에 daewoon 없음) 대운×원국 관계를 싣지 않는다 → 주어를 LLM 이 추측했다.
- 생성 전: `canonical_claim_lines(semantics, stack_ganji=…)` 가 각 문장 앞에 `丁壬合 [원국 월간 丁 + 대운 壬]:` 라벨을 붙인다(`saju_engines.layer_labels.participants_label` — 원국은 `RelationOccurrence.position` 으로 간·지 자리, 운('luck')은 `PeriodFortune.stack_ganji`(대상 기간 composite parent_context + 자기 간지)에서 층위를 찾는다. 스택에 없으면 '운 壬'). 헤더에 "대괄호의 층위를 다른 층위로 바꿔 부르지 말 것" 규칙.
- 생성 후: `saju_engines.layer_label_audit.audit_layer_labels` — '대운|세운|월운|일운|일진 (의|에서|에| ) 글자1자(병기)' 표기에서 글자가 그 층위 간지의 해당 자리(천간↔천간·지지↔지지)에 없으면, 실제 자리가 하나면 그 라벨로 바꿔 쓰고(원국 월간 丁 / 대운 壬), 여러 자리면 층위어만 지우며, 어디에도 없으면 둔다. 간지 2자 표기('세운 丙午')는 대상 아님. 로그 `layer_label_fixed`. 스택은 기간 총운의 `stack_ganji`, 없으면 현재 대운만.
- 미해결(승인 대기): 계층 블록에 대운×원국 관계를 싣는 것은 `build_v2_scoring` 범위(scope_keys)까지 바꾸므로 별도 결정 — 서술 전용으로 대운 composite 를 narrative 에만 합류시키는 안을 검토 대상으로 남긴다.
- 회귀: `tests/unit/test_layer_label_audit.py`(라벨 SSOT·실답 프롬프트 라벨·오표기 교정·모호 글자·미지 글자·간지 2자·일운→일진).
