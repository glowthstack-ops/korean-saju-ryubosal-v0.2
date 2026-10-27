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

## 부록 — 연애운 강의 4편 대조: 결혼 자원 블록 확장 + 연애 유형 블록 (2026-10-25 데굴님 승인)

- 배경: 운세고 「연애운 폭발 시기」·도하도르 「셀프 리딩 1·2탄」·「결혼운」 4편 대조(`doc/v2_2/EXTERNAL_TEXT_GAP_LOVE_TIMING.md`). 점수층은 P0 결함 3건만 ON(삼합완성·반합성립·방합완성이 변환기에 없어 일지 반합·완성이 관계 궁위 가산에 전혀 안 들어가던 결함 + HAP 등급 배율, 편관 토큰), P1 실험 4종은 85사례 재생에서 적중 개선 없음(P1-3 은 오탐 +2)이라 OFF. 복구된 반합·완성 등급의 궁위 가산은 `hap_grade_scope` 로 일지 × 관계 사건에 한정(전 궁위 적용 시 입퇴사 실이력 정밀도 하락 — 한정 후 사례집 방향 오탐 8→7).
- `[결혼·자산 자원 구조]` 블록에 추가된 줄(전부 경향 어휘·점수 비개입): `배우자성 자리(배우자성 한정 — 고정 등식 아님…)`(천간=바라는 결·지지=실제 만남 환경, 간여지동 배우자성 기둥=100세 밴드 몰입 경향) / `배우자성 정/편 축(… 일지 이상형과 별개 축)` / `상대 나이대 경향(단정 아님 …)` / `결혼 시기·형태 프레임(늦은 결혼·비혼 모두 중립, 이혼 단정 금지)` / 배우자성 미투출 줄의 소유욕·구속 어휘 + 운 진입·이탈 프레임 / `재성 미투출 — 관계 유지 욕구` 줄.
- 블록 끝 `[연애 유형 — 십성군 분류(강의 번역층, 경향·단정 아님) …]` — 유형·근거·십성 의미·연애 심리·중시하는 것·다가가는 법·주의(+부 유형 1줄). 유형명은 '○○형', 상대 평가·낙인 금지 지시 포함.
- 운 도화 줄의 기준 괄호에 연지=타인 시선 / 일지=배우자궁 프레임 병기. 궁합 블록에 `비겁 과다(참고)` 보조 줄(카운트·톤 비반영).
- 토큰: 결혼 자원 블록이 최대 7~9줄 늘어난다(관계 도메인·총운에서만). 상한 변경 없음.


## 부록 — 관계 사건 후보의 '연애 운의 결' 줄 + 궁합 신호 2종 + 처음 들어오는 기운 (2026-10-27 데굴님 승인)

- `LlmEventCandidate.love_notes`(신규, 서술 전용): 관계 사건 후보(new_relationship·relationship_change·marriage_signal)의 기간 간지로 `saju_engines.love_period_notes` 가 고른 구절. ①운 지지가 일지를 충하면 급작스러운 시작·빠른 진행·강한 끌림·긴 여운 ②천간·지지 역할이 기·구신으로 모이면 '빠르게 빠져들고 오래 기억될 수 있다', 용·희신으로 모이면 '처음엔 확신·설렘이 덜할 수 있다'(엇갈리면 생략) ③원국 결핍 오행이 들어오면 '운이 지나면 관계의 결도 달라질 수 있다' ④운 천간 비견·식상·재성·관성의 연애 결(인성·겁재는 정의 없음 — 생략). 관계 도메인 질문(`_rel_focus`, 비연애 관계 제외)에서만 `  연애 운의 결(그럴 수 있다는 경향 — '반드시'·'운명'·'끝난다' 단정 금지): …` 로 렌더. 점수·순위·판정 불변.
- 궁합 `CompatSignalKind.WEAK_RESOURCE_PARTNER`(신약·태신약 쪽에게 상대 일간이 정인·편인)·`OUTPUT_YONGSIN_SUPPORT`(상대 일간의 식상 오행이 내 용·희신), 양방향. 둘 다 방향 '보완'(안정 카운트 포함)이며 **끌림 가중 1**(데굴님 "끌림 점수에 넣자"). 성별 조건은 두지 않는다.
- 기간 운 grounding `pillar_line` 끝 '처음 들어오는 기운' 구절(`chart_interpretation.first_arrival_note`): 세운 간지(대운 기둥은 `build_luck_grounding` 호출 경로가 없어 제외 — 재검토)의 오행이 용·희신인데 원국 표면 분포가 0이면 "바로 편해지기보다 낯섦·내면의 조정이 먼저 올 수 있다" 서술. 용신 판정(부재해도 필요는 유지 — 결정 D)과 점수는 바꾸지 않는다.
- 고정 prefix 해석 발췌 신규 kind: `ten_god_group`(십성다자 두 갈래), `favorability_face`(용신·기신 운의 다른 얼굴). 원국 관계 발췌에 충 성향 '성향:' 문장. 사전 규격은 docs/05 같은 날 절.

### 2차(같은 날, 데굴님 "일정 점수가 넘는 모든 사건을 표시" · "붙이는 게 낫겠어")

- **같은 영역 다른 사건 후보**(`LlmInput.family_candidates`, `context_reducer.family_extra_candidates`, 플래그 `SAJU_DOMAIN_FAMILY_SCOPE_ENABLED` 기본 ON): 비총운·비택일 특정 사건 질문에서 질문 사건 키가 아닌 같은 영역 계열(`_DOMAIN_EVENT_KEYS` — 관계=새 인연·관계 변화·결혼 신호·출산, 직업=이직·취업·승진·창업·확장·계약, 재물=재물 변화·횡재, 학업=입학·수료) 사건 중 질문 기간 안 70점 이상을 점수순 4건. `[같은 영역 다른 사건 후보 — …]` 블록에 후보 블록 형식(연애 운의 결 포함)으로 싣는다. **`event_candidates` 에는 섞지 않는다** — 진입 시기 두 칸(성사 달·움직이는 달)·상담 결론 판정이 질문 사건 후보만 읽기 때문이다(처음엔 후보 목록 자체를 넓혔다가 취업 질문의 움직이는 달 4개가 계약·승진 후보에 밀려 사라지는 회귀를 확인하고 분리했다). 질문 사건 후보가 0이면 '후보 없음' 지시에 '질문 사건에 한정 — 같은 영역 후보로 흐름을 설명'을 덧붙인다. 점수 불변.
- **같은 기간 다른 영역 신호**(`LlmInput.period_other_signals`, `period_other_signal_lines`, 플래그 `SAJU_PERIOD_OTHER_SIGNALS_ENABLED` 기본 ON): 질문 영역 계열 밖이면서 질문 기간 안 70점('가능성이 높습니다') 이상, 사건 키별 최고 1건, 점수순 4건. `[같은 기간 다른 영역 신호 — …한두 문장으로만…]` 블록으로 후보 블록 뒤에 싣고, 질문 영역 후보가 0이면 '후보 없음' 지시에 "질문 영역에 한정 — 기간 전체를 조용하다로 쓰지 말 것"을 덧붙인다. 총운·택일 질문 제외.
- **월별 표 연애 운의 결**(`MonthOverviewRow.love_note_labels`·`love_note_texts`): 그 달 관계 계열 후보가 하한 40 이상이면 `love_period_notes.love_period_note_items` 라벨을 단다. 관계 도메인 질문에서만 행 아래 `  └ 연애 운의 결: 라벨 · 라벨`, 표 아래 범례에 라벨별 구절을 한 번만 싣는다(열두 달 반복 방지).

### 3차(같은 날, 재검토 — 독립 리뷰 9건 반영)

- **기간 단위**: 같은 영역·다른 영역 블록 모두 `_granularity_ok` — 질문이 일·주 단위면 싣지 않고, 월 질문엔 월 후보만, 연 질문엔 연·월 후보. 겹침 판정만 쓰면 '오늘 연애운'에 '취업 @ 2026'이 붙었다.
- **'다른 영역' 기준**: `EVENT_DOMAIN`(event_taxonomy_v2). 직업 질문의 법적 갈등·결과물·공개 노출처럼 같은 이벤트 도메인 키는 다른 영역 줄에 올리지 않는다.
- **노출 제외**: 개운(REMEDY) 질문은 두 블록 미노출. 택일·명식 분석 질문은 월별 표 연애 운의 결 미노출. 월별 표 라벨 기준은 관계 3키(`LOVE_NOTE_EVENT_KEYS`, 출산 제외) 70점 이상.
- **가드 동기화**: 같은 영역 후보만 있는 턴에도 동반 신호 매트릭스·범위·위계 지시를 싣고, 결혼 출력 가드·시주 미상 극성 보류를 같은 영역 후보에도 적용한다. 토큰 가드 Tier 0 에서 다른 영역 줄을 버리고 같은 영역 후보를 1건으로 줄인다.
- **반복 방지**: 연애 운의 결 구절은 후보 간 한 번만(이후 '앞 후보와 같음').
- **머리말**: 같은 영역 블록 머리말에 질문 사건명을 넣고 '첫 판정 문장은 질문 사건 강도로만, 이 블록 사건으로 질문 사건이 유리하다고 바꿔 말하지 말 것'을 명시.
- **리포트**: 비연애 관계 짝 리포트(`non_romantic_pair`)와 자녀 섹션 F-17c 는 연애 운의 결 미노출, 연도별 상세 월별 표는 70점 이상 달만.
- 궁합 `WEAK_RESOURCE_PARTNER` 는 시주 미상으로 신강약 밴드가 미확정이면 내지 않는다.

### 4차(같은 날, 데굴님 "권장대로 진행하자") — 같은 영역 관계 후보 해석 틀 · 첫 판정 재료

- 배경: new_relationship 점수는 일지 궁위 가산이 없는 사각(부록 A-3 #2, 사례집 라벨 0건이라 미측정)이라, 같은 달 관계 진전 신호(결혼 신호·관계 변화)보다 낮게 잡힌다. 3차의 '첫 판정은 질문 사건 강도로만' 지시는 이 사각 키를 기준으로 강제해 폐기했다.
- `LlmInput.relationship_status`(신규, single·dating·married·미입력 ""): 채팅이 2단계 프로필 교제 상태를 payload 에 싣는다. 점수·선별 비개입.
- 같은 영역 블록 머리말: 첫 판정에 질문 사건 자체 강도와 이 영역의 강한 신호를 **함께** 밝히고, 한쪽만으로 '아무 일 없다'·'질문 사건 확정'으로 바꿔 말하지 않게 한다. 관계 질문이면 `(관계 영역 해석 틀)` 한 줄 — 교제 중=관계 진전·공식화, 혼자=이 시기 만남이 진지한 관계로 이어질 가능성, 기혼=부부 관계의 흐름, 미입력=두 경우를 한 문장씩.
- '후보 없음' 지시: 같은 영역 후보가 있으면 "질문하신 사건 자체의 후보는 약하거나 없다 — 같은 영역 후보와 함께 첫 판정을 세울 것"으로 바꾼다(기존 "뚜렷한 신호가 없습니다로 안내" 문구를 내지 않음).
- `family_verdict_directive`(채팅 말미 지시): 질문 사건이 70점 미만이고 같은 영역 후보가 있을 때 `[첫 판정 재료 — 엔진 확정] 질문하신 'X' 자체: 강도 / 같은 영역의 다른 사건: …` + 관계 질문은 교제 상태별 예시 문장. 블록 머리말만으로는 실답 첫 문장이 바뀌지 않았고(2건), 말미 재료를 넣은 뒤 두 사실이 함께 서술됐다(2건).

### 5차(같은 날) — 성립 불가 관계 주장 감사 · 반복 구조 · 관계 적중 중복 제거

- 답변 후처리: `impossible_relation_audit` 가 관계 표에 없는 두 간지 관계 주장 문장을 지운다(채팅 `finalize_answer_text`·리포트 섹션, 재호출 없음).
- 입력: 원국 해석 발췌 `repetition`, 기간 운 grounding '반복 구조(서술 전용)', `LlmEventCandidate.repetition_notes`(같은 기간 첫 후보에만 렌더). 규격은 docs/05 repetition_text 절.
- 엔진: `period_v2_config.RELATION_HIT_DEDUP_ENABLED`(기본 ON) — 같은 관계 문자열을 한 번만 해석해 원국 중복 글자의 N×N 발동을 막는다. 측정은 WORKLOG 2026-10-27 6차.
