# 09. 사전계산 파이프라인 & 동적 컨텍스트 (Precompute & Topic Context)

> **이 문서의 모든 목록(상호작용 유형, 레벨 조합, 토픽 모듈, 갱신 정책)은 예시가 아니라 전체 규격이다.**
> Claude Code는 목록의 항목을 임의로 추가·삭제·축약·순서변경하지 않는다. 변경이 필요하면 구현 전에 사용자 승인을 받는다.

## 0. 설계 원칙

```
[엔진 — 결정적 계산]
  운의 복합 조합·작용을 전부 사전계산해 저장
  → 주제별 Topic Context Builder가 필요한 부분만 참조
  → 이벤트 가능성 / 시기별 성향 변화 등 동적 컨텍스트를 수치로 산출

[LLM — 문체 전용]
  완성된 동적 컨텍스트를 받아
  페르소나 어투로 "전달"만 한다
```

목적: 이사처럼 시기 × 지역오행 × 주거타입 × n명 그룹 사주가 결합되는 질의를 LLM 추론에 맡기면 thinking token이 폭발해 원가 리스크가 된다. **조합·필터·점수화는 전부 코드에서 끝내고, LLM 입력은 결론 테이블 + 근거 요약으로 제한한다.**

### LLM 금지 작업 (전체 목록 — 시스템 프롬프트와 코드 가드 양쪽에 적용)

1. 간지 계산 (원국/대운/세운/월운/일운/시진)
2. 합충형파해·공망·신살의 성립 여부 판단
3. 이벤트 점수·순위·날짜 후보의 산출 또는 변경
4. 다중 대상(그룹) 점수의 합산·비교
5. 방위/지역/주거타입 적합도 계산
6. 제공되지 않은 기간·대상에 대한 추정 답변
7. 사전(JSON)에 없는 명리 규칙의 즉석 적용

LLM 허용 작업: 제공된 수치·근거의 자연어 서술, 페르소나 어투 적용, 우선순위에 따른 서술 분량 배분, 사용자 질문 표현과의 연결.

---

## 1. 3계층 사전계산 구조

| Tier | 이름 | 내용 | 갱신 트리거 (전체) |
|---|---|---|---|
| **T0** | Static Chart Layer | 원국 4주, 지장간, 십성 매핑, 12운성, 신살, 공망, **원국 내부 상호작용 전체**, 신강약/격국/용신, Self Profile 베이스, 평생 대운 리스트 | ① 대상 등록 시 ② 출생정보 수정 시 ③ 사전 버전 변경 시 |
| **T1** | Slow Luck Layer | 대운×원국 / 세운×(원국+대운) / 월운×(원국+대운+세운) 상호작용 + 레벨간 상호작용 | 대운: 교체일·등록 시 / 세운: 입춘 경계·등록 시 / 월운: 절입일 경계·등록 시 / 사전 버전 변경 시 |
| **T2** | Daily Luck Layer | 일운×(원국+대운+세운+월운) 상호작용, 당일 활성 신호 종합 | ① 매일 00:00 KST 배치(활성 대상) ② lazy 계산+캐시(비활성 대상) ③ 사전 버전 변경 시 |

활성 대상 정의: 최근 30일 내 대화 이력이 있거나 일일운세 구독 중인 self + 그 동반자 전원. 그 외는 첫 요청 시 lazy 계산 후 당일 TTL 캐시. (전 사용자 일일 배치는 낭비 — 비용 통제 목적)

무효화 규칙: 사전(`compiled/event_graph_vX`) 버전이 바뀌면 T0~T2 전체 무효화 후 재계산. 출생정보 수정 시 해당 대상의 T0~T2 무효화.

쌍둥이 변형(docs/11 2-2): LuckComposite 키에 chartVariant를 포함한다(`subjectId` → `subjectId#variant`). **active 변형만 T1/T2를 유지**하고 비활성 변형은 T0만 보관. 변형 전환 = 출생정보 수정과 동일한 무효화·재계산 경로.

---

## 2. 상호작용 탐지 — 전체 목록 (규격)

탐지기는 아래 관계를 **모두** 검사한다. 이 표가 `relations.json`의 필수 수록 범위다.

### 2-1. 천간 관계
| 유형 | 전체 조합 |
|---|---|
| 천간합 (5) | 甲己合(土) · 乙庚合(金) · 丙辛合(水) · 丁壬合(木) · 戊癸合(火) — 모드: 합화/합반/합래/합거 |
| 천간충 (4) | 甲庚沖 · 乙辛沖 · 丙壬沖 · 丁癸沖 |

### 2-2. 지지 관계
| 유형 | 전체 조합 |
|---|---|
| 육합 (6) | 子丑(土) · 寅亥(木) · 卯戌(火) · 辰酉(金) · 巳申(水) · 午未(火) |
| 삼합 (4) | 申子辰(水) · 亥卯未(木) · 寅午戌(火) · 巳酉丑(金) — **반합(2자) 탐지 포함, 왕지 포함 여부 플래그** |
| 방합 (4) | 寅卯辰(木·東) · 巳午未(火·南) · 申酉戌(金·西) · 亥子丑(水·北) — 반합 포함 |
| 충 (6) | 子午 · 丑未 · 寅申 · 卯酉 · 辰戌 · 巳亥 |
| 형 | 寅巳申(삼형) · 丑戌未(삼형) — 부분형(2자) 탐지 포함 / 子卯(상형) / 자형: 辰辰 · 午午 · 酉酉 · 亥亥 |
| 파 (6) | 子酉 · 午卯 · 巳申 · 寅亥 · 辰丑 · 戌未 |
| 해 (6) | 子未 · 丑午 · 寅巳 · 卯辰 · 申亥 · 酉戌 |
| 원진 (6) | 子未 · 丑午 · 寅酉 · 卯申 · 辰亥 · 巳戌 — 기본 활성 |
| 암합 | 유파 차이가 큼 → **기본 비활성**, `relations.json`의 `enabled` 플래그로만 활성화. 임의 구현 금지 |

### 2-3. 구조 플래그
공망 활성(운 지지가 공망지에 해당/공망지 충발), 복음(동주 반복), 반음(충 구조의 운 재현), 병존, 간여지동, 백호/괴강 등 신살 활성 — 신살 목록은 기존 만세력 엔진의 신살 산출 결과를 그대로 사용 (재정의 금지).

### 2-4. 레벨 조합 — 전체 11종 (규격)

탐지 대상 소스 = { 원국(4주), 대운, 세운, 월운, 일운 }

```
P01 원국 내부 (주간: 년-월, 년-일, 년-시, 월-일, 월-시, 일-시)   [T0]
P02 원국 × 대운                                                  [T1]
P03 원국 × 세운                                                  [T1]
P04 원국 × 월운                                                  [T1]
P05 원국 × 일운                                                  [T2]
P06 대운 × 세운                                                  [T1]
P07 대운 × 월운                                                  [T1]
P08 대운 × 일운                                                  [T2]
P09 세운 × 월운                                                  [T1]
P10 세운 × 일운                                                  [T2]
P11 월운 × 일운                                                  [T2]
```

다자(3자 이상) 관계 — 삼합·방합·삼형은 **소스 혼합 성립을 허용**한다 (예: 원국 申 + 세운 子 + 일운 辰 = 申子辰 삼합). 탐지기는 모든 소스의 지지를 풀(pool)로 모아 3자 조합을 검사하고, 성립 시 참여 소스를 기록한다. 이것이 "운의 복합적인 조합"의 핵심이며 누락 금지.

---

## 3. LuckComposite 스키마 (저장 단위)

```typescript
/** (subjectId, level, periodKey)당 1레코드. 다운스트림 전체의 단일 참조원(SSOT). */
interface LuckComposite {
  subjectId: string;
  level: 'natal' | 'daewoon' | 'year' | 'month' | 'day';
  periodKey: string;            // 'natal' | 'DW:壬辰' | '2026' | '2026-06' | '2026-06-10'
  ganji: { stem: Stem; branch: Branch };
  parentContext: {              // 상위 레벨 간지 — LLM 입력 시 함께 전달 (계산 불가 보완)
    daewoon?: string; year?: string; month?: string;
  };
  tenGod: { stem: TenGod; branchMain: TenGod };   // 일간 기준
  twelveStage: TwelveStage;
  favorability: '용신' | '희신' | '한신' | '기신' | '구신';   // 오행 기준 판정
  interactions: InteractionHit[];                  // 2장 전체 목록 기준 탐지 결과
  structureFlags: string[];                        // 공망활성/복음/반음/병존...
  shinsalActive: string[];
  domainSignals: DomainSignal[];                   // 사전 매핑 통과 후의 도메인별 신호 합산
  dictVersion: string;
  computedAt: string;
}

interface InteractionHit {
  relationId: string;           // 'rel_甲己合'
  kind: 'stem_combine' | 'stem_clash' | 'branch_six_combine' | 'branch_three_combine'
      | 'branch_directional' | 'branch_clash' | 'branch_punish' | 'branch_break'
      | 'branch_harm' | 'wonjin' | 'self_punish' | 'structure';
  participants: { source: 'natal_year'|'natal_month'|'natal_day'|'natal_hour'
                        |'daewoon'|'year'|'month'|'day'; ganji: string }[];
  partial: boolean;             // 반합/부분형 여부
  modeCandidates: string[];     // 합화/합반/합래/합거
  baseWeight: number;
}

interface DomainSignal {        // Topic Builder가 소비하는 최소 단위
  domain: Domain;
  eventKey?: EventKey;
  weight: number;               // 보정 완료된 가중치 (favorability 반영)
  sourceInteraction: string;    // relationId 역추적용
}
```

PostgreSQL 저장 (전체 정의):

```sql
CREATE TABLE luck_composites (
  subject_id   TEXT NOT NULL,
  level        TEXT NOT NULL CHECK (level IN ('natal','daewoon','year','month','day')),
  period_key   TEXT NOT NULL,
  dict_version TEXT NOT NULL,
  payload      JSONB NOT NULL,          -- LuckComposite 직렬화
  computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (subject_id, level, period_key, dict_version)
);
CREATE INDEX idx_lc_subject_level ON luck_composites (subject_id, level);
-- day 레벨 보존 기간: 과거 90일 / 미래 400일 외 삭제 배치 (스토리지 통제)
```

---

## 4. Topic Context Builder — 모듈 전체 목록 (규격 15종)

각 모듈은 `(subjects, period, LuckComposite[], dictionaries) => TopicContext`인 순수 함수다.
**아래 15종이 전체이며, 새 주제는 모듈 추가로만 대응한다 (기존 모듈에 분기 추가 금지).**

| # | moduleId | 담당 질의 | 참조 Composite | 전용 사전 | 산출 핵심 |
|---|---|---|---|---|---|
| M01 | love_timing | 연애+시기, 재회 | natal + year/month (대상 기간) | events/relationship | 연애 이벤트 후보 시계열 + 상대 유형 신호 |
| M02 | marriage | 결혼/이혼/재혼 | natal + daewoon + year | events/relationship | 결혼 적합 연/월 + 배우자궁 상태 |
| M03 | personality_traits | 성격/취향 + **시기별 변화** | natal + daewoon + year | trait_mapping | 기본 성향 + 기간별 활성 십성 시프트 (5장) |
| M04 | parents_fortune | 부모님운, 부모 관계 | natal(인성·년월주) + 부모 등록 시 그 사주 | relation_profiles | 육친 구조 + 기간 리스크/기회 |
| M05 | children | 자녀운, 자녀 사주 | natal(식상·시주) + 자녀 subject | relation_profiles, events/education | 자녀 이벤트 + 부모-자녀 축 |
| M06 | workplace_relations | 직장 내 관계(상사/동료) | natal(관성·비겁) + month | relation_profiles | 갈등/협력 신호 시계열 |
| M07 | career | 취업/이직/승진/퇴사 | natal + daewoon + year + month | events/career_change | 이벤트 후보 + 타임라인 단계 |
| M08 | business | 창업/사업/동업 | natal + daewoon + year | events/wealth, relation_profiles | 사업 적합 구조 + 시기 |
| M09 | wealth | 재물/유산/횡재/투기 | natal + year + month (+day: 횡재) | events/wealth | 재물 흐름 + windfall 제한 신호 |
| M10 | relocation_composite | **이사 (복합)** | 그룹 전원의 month + day | events/relocation, calendar/*, region_elements, housing_rules | 7장 전체 사양 참조 |
| M11 | health | 건강/수술 시기 | natal + year + month + day(수술일) | events/health | 리스크 시기 + 회피일 |
| M12 | education_exam | 학업/시험/합격 | natal + year + month (+anchor일) | events/education | 학습 적기 + 시험일 적합 |
| M13 | bond_compare | 궁합/경쟁/랭킹 | 대상별 natal (+판정일 day) | relation_profiles | E12/E13 입력 생성 |
| M14 | past_validation | 과거 검증 | natal + 과거 daewoon/year | events/* 전체 | 과거 이벤트 후보 (역방향) |
| M15 | lifestyle | 일일/주간/연간 종합 | day/month/year composite | templates/format_slots | 고정 슬롯 점수 |

오케스트레이터 업무 분장 (재확정):

```
Conversation Layer  : 대상·맥락 확정 (docs/03 A0~A3)
Query Parser        : ParsedMessage(intents[]) 생성
Execution Planner   : intent → 호출할 모듈(M01~M15) + 기간 + 레벨 결정
Precompute Store    : LuckComposite 제공 (없으면 lazy 계산)
Topic Builder       : 동적 컨텍스트(TopicContext) 산출 — 모든 수치 확정
Context Reduction   : TopicContext를 LLM 입력 계약(docs/06)으로 압축
LLM                 : 페르소나 어투 서술만
```

---

## 5. TopicContext 표준 스키마

```typescript
interface TopicContext {
  moduleId: string;                       // 'M10'
  subjects: SubjectRef[];
  period: { start: string; end: string; granularity: string };
  calendarContext: CompressedCalendar;    // docs/06과 동일 — 간지는 항상 동반
  findings: Finding[];                    // 모듈별 핵심 산출 (점수 확정 완료)
  timeSeries?: { periodKey: string; ganji: string; score: number; signals: string[] }[];
  rankedResults?: RankedItem[];           // 택일/랭킹형
  traitShifts?: TraitShift[];             // M03 전용 (8장)
  groupAggregation?: GroupAggReport;      // 다중 대상
  evidence: EvidenceBundle[];             // Graph RAG readable path
  styleRules: StyleRules;                 // 금기/톤/단정금지
  budget: { maxInputTokens: number; maxOutputChars: number };  // 9장 거버넌스
}
```

`findings`, `rankedResults`의 모든 수치는 Topic Builder에서 확정된다. LLM 입력 이후 어떤 수치도 변하지 않는다 (정합성 검사로 검증 — docs/10 7장).

---

## 6. 시기별 성격/취향 변화 계산 (M03 사양)

원국 성향은 고정이지만, 대운·세운이 십성 분포를 일시적으로 가산해 "그 시기의 나"가 달라진다. 계산식 (전체):

```
effectiveTenGodDist(period) =
    natalDist                  × W_natal
  + daewoonContribution        × W_daewoon
  + yearContribution           × W_year

기본 가중치 (trait_mapping.json, reviewed:false — 도메인 검수 필수):
  W_natal = 1.0, W_daewoon = 0.45, W_year = 0.25
contribution = 해당 운 간지의 십성(천간 1.0 + 지지 본기 0.7) × favorability 보정(용신 +20% / 기신 -20%는 '발현 질' 플래그로만, 분포 자체는 미조정)
```

산출:

```typescript
interface TraitShift {
  periodKey: string;            // 'DW:壬辰' | '2026'
  dominantTenGods: TenGod[];    // 상위 2~3
  risingTraits: string[];       // trait_mapping 사전의 십성→성향 어휘
  fadingTraits: string[];
  qualityFlag: 'favorable' | 'pressured' | 'mixed';  // 기신 활성 시 pressured
  evidence: string[];
}
```

용도: "요즘 왜 이런 게 끌리지?", 시기별 취향 변화, 대운 교체기 성향 전환 서술. MBTI식 고정 유형화 금지 원칙(docs/02 E5)은 동일 적용.

---

## 7. 이사 Composite Resolver (M10) — 전체 사양

입력 (전체 필드):

```typescript
interface RelocationQuery {
  groupSubjects: SubjectRef[];            // 1~n명
  aggregationRule: 'householder_primary' | 'balanced' | 'protect_weakest';
  weights?: Record<string, number>;       // 구성원별 가중 (기본: 호주 0.5 / 배우자 0.3 / 기타 균등)
  period: { start: string; end: string }; // 데드라인 역산(C9) 결과 반영
  currentLocation: string;                // 방위 기준점 (필수 — 없으면 확인 질문)
  candidateDirections?: Direction[];      // 미지정 시 8방위 전부
  candidateRegions?: string[];
  housingType?: 'buy' | 'jeonse' | 'monthly' | 'new_build' | 'old_build';
  realityConstraints: string[];           // 주말만/업체 가능일 등
  chainedSchedule?: ChainStep[];          // 계약→이사 체인
}
```

처리 단계 (전체 — 순서 고정, 전부 코드 계산):

```
S1  구성원별 이동운 시계열 추출: month-level LuckComposite에서 relocation DomainSignal
S2  그룹 집계: aggregationRule + weights → groupMonthScore. 구성원별 경고(이동운 충돌) 별도 기록
S3  월 후보 확정: groupMonthScore 상위 + macro flow(대운/세운 허용) 통과 월만
S4  일 후보 생성: 후보 월 내 day-level Composite → dayExecutionScore
S5  방위 적합: direction_rules(개인 용신 오행→방위) × region_elements(후보 지역 오행)
    → 방위 미정이면 방위별 분리 산출 (단일 답 강제 금지)
S6  주거 타입 보정: housing_rules.json — buy: 문서운+재물운 가중 / jeonse·monthly: 문서운 가중
    / new_build·old_build: 보정 없음(명리 근거 부족 — 임의 규칙 발명 금지, 사전에 정의된 것만)
S7  Calendar Rule: 손없는 날, 공휴일/주말, 금기일 필터
S8  Reality Constraint 필터
S9  체인 스케줄: 데드라인 역산 → 이사 창 확정 → 계약 창 배치 (각각 S4~S8 반복)
S10 최종 랭킹 — 산출 형식:
```

```typescript
interface RelocationResult {
  recommendedPlan: {
    contractWindow?: RankedItem[];        // 체인 모드 시
    moveDates: RankedItem[];              // 날짜별: date, ganji, finalScore,
                                          //   부분점수 5종(macro/month/day/calendar/reality),
                                          //   directionFit: Record<Direction, number>,
                                          //   memberWarnings: { subjectLabel, signal }[]
  };
  groupSummary: { monthlyScores: ...; conflicts: ... };
  avoidDates: { date: string; reason: string }[];
  evidence: EvidenceBundle[];
}
```

LLM에는 `RelocationResult` + 압축 간지만 전달한다. **LLM이 받는 것은 "계산할 문제"가 아니라 "설명할 결론"이다.** 예상 입력: 2,500~4,500 토큰 (그룹 4인 기준) — 전체 간지달력 투입 대비 1/20 이하.

---

## 8. 토큰 예산 거버넌스 (전체 한도표)

| 호출 유형 | LLM 입력 상한 | LLM 출력 상한 | extended thinking |
|---|---|---|---|
| 대화형 단건 응답 | 6,000 tok | 1,200 tok | **비활성** (계산 완료 데이터 수신이므로 불필요) |
| 대화형 — 동반자 비교 | 8,000 tok | 1,600 tok | 비활성 |
| Query Parser (경량 모델) | 2,000 tok | 300 tok | 비활성 |
| 집중 풀이 섹션 1개 | 5,000 tok | 4,500자(≈3,500 tok) | 비활성 |
| 총운 풀이 섹션 1개 | 5,000 tok | 4,500자 | 비활성 |
| 정합성 검사 LLM 패스(선택) | 8,000 tok | 500 tok | 비활성 |

가드 구현: LLM 호출 래퍼가 입력 토큰을 측정해 상한 초과 시 **호출 전 예외** → Context Reduction 재실행. 상한을 늘리는 코드 수정은 금지(사용자 승인 필요). 모든 호출의 입출력 토큰을 로깅해 상품별 원가 대시보드에 집계한다.

---

## 9. 리스크 / 도메인 검수 필요 항목 (정직 기록)

1. **region_elements.json (지역오행)**: 명리학에 표준 규격이 없다. 자체 기준(지명 한자 오행/지형/방위)을 세워야 하며 전 항목 `reviewed:false`로 시작 — 사용자 검수 전 출시 금지.
2. **housing_rules.json**: 주거 타입별 보정은 학술 근거가 약하다. 문서운/재물운 연결 등 사전에 정의된 최소 규칙만 사용하고, 근거 없는 타입 보정(신축/구축 등)은 0 보정으로 둔다.
3. **암합·귀문**: 유파 차이로 기본 비활성. 활성화는 사전 플래그 + 사용자 결정.
4. **T2 일일 배치 비용**: 활성 대상 수 × 동반자 수에 비례. 초기에는 lazy 우선, 구독 기능 도입 시 배치 전환을 측정 후 결정.
5. **가중치 전반** (W_daewoon=0.45 등): 추정 초기값. cases.jsonl 누적 전까지 절대값 신뢰 금지, 상대 비교만 사용.
