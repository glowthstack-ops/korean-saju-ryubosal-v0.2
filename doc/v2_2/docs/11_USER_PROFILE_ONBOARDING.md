# 11. 사용자 정보 수집(2단계) & 페르소나 설정

> **이 문서의 필드 목록·enum 값·분류 체계·조합 규칙은 예시가 아니라 전체 규격이다.**
> Claude Code는 필드·값·분류를 임의로 추가·삭제·재해석하지 않는다. 변경은 사용자 승인 필요.

---

## 1. 수집 구조 개요

```
1단계 (필수)  : 사주 계산에 필요한 최소 정보 — 미완료 시 서비스 진입 불가
2단계 (선택)  : 현재 상황 이해 + 물상 풀이용 — 전체/부분 스킵 가능, 언제든 추가·수정
페르소나 설정 : 상담가 캐릭터 + 어투 + 난이도 + 호칭 — 기본값 제공, 언제든 변경
```

원칙:
1. 2단계 미입력은 어떤 기능도 차단하지 않는다. 정밀도만 달라진다 (4장 영향표).
2. **Just-in-time 수집**: 질문 처리에 2단계 필드가 필요해지면 그 시점에 1회만 요청한다. 거절 시 같은 세션에서 재요청 금지, 미입력 한계를 답변에 명시.
3. 대화 중 자연 발화에서 추출된 정보(docs/03 realityContextUpdates)는 **사용자 확인 후** 프로필에 저장한다. 무단 저장 금지.
4. 모든 2단계 필드는 사용자가 개별 삭제 가능. 삭제 즉시 관련 캐시(Reality Context modifier) 무효화.

---

## 2. 1단계 — 기본 정보 (전체 필드 규격)

```typescript
interface BasicProfile {
  // 사주 계산 필수
  birthDate: string;                    // 'YYYY-MM-DD'
  calendarType: 'solar' | 'lunar';
  isLeapMonth: boolean;                 // 음력 윤달 — lunar일 때만 노출
  birthTime: string | null;             // 'HH:mm'. null = 시간 모름
  birthTimeUnknown: boolean;            // true → 3주(시주 제외) 모드 (docs/08 A13)
  birthTimeApprox?: '새벽' | '아침' | '낮' | '저녁' | '밤' | null;
                                        // 시간 모름이지만 대략 아는 경우 — 시주 후보 2~3개 병기 모드
  birthPlace: {
    country: string;                    // 기본 'KR'
    city: string;                       // 시/군 단위 — 진태양시(경도) 보정용
    longitude?: number;                 // city → 좌표 변환은 시스템이 수행, 사용자 입력 아님
  };
  gender: 'M' | 'F';
  multipleBirth?: {                     // 쌍둥이/다태아 — 2-2장 규격. 미입력 = 해당 없음
    total: number;                      // 2=쌍둥이, 3=세쌍둥이 (2 이상)
    order: number;                      // 출생 순서 1~total
  };
  // 표시용
  displayName: string;                  // 호칭 조합에 사용 (2~10자)
}
```

규칙 (전체):
- `birthPlace`는 진태양시 보정과 야자시/조자시 처리의 입력이다. 기존 만세력 엔진의 보정 방식을 그대로 사용하며 재구현 금지.
- `birthTimeUnknown=true`: 시주 제외 3주 분석 + 모든 출력에 정밀도 한계 1회 고지. `birthTimeApprox` 제공 시 해당 시간대의 시주 후보를 병기하되 단일 확정 금지.
- 해외 출생(country≠KR): 현지 시각 기준 입력 + 시스템이 시차·경도 보정. 미지원 지역이면 보정 불가 고지 후 표준시 계산.
- 수정 시: 해당 subject의 T0~T2 사전계산 전체 무효화 (docs/09).
- 동반자 등록도 동일 스키마를 사용한다 (docs/02 E14 Companion.birth와 통합). 동반자 역시 `multipleBirth` 입력 가능.

### 2-2. 쌍둥이/다태아 시주 조정 (전체 규격)

같은 시각에 태어난 다태아는 시주가 동일해져 구분 풀이가 불가능하다. 출생 순서에 따라 시주를 전진시키는 해석법을 적용한다.

**조정 규칙 (전체)**:

```
order = 1 (첫째)        : 입력값 그대로 — 변형 없음 (단일 차트)
order = n (n ≥ 2)       : 시주 간지를 60갑자 순서로 (n-1)칸 전진
                          (= 시지를 (n-1) 시진 전진 + 시두법 재계산과 동일 결과)

예) 기준 시주가 乙丑(축시)일 때
    둘째  → 丙寅(인시)
    셋째  → 丁卯(묘시)
```

**경계 처리 (규격 — 임의 변경 금지)**:
- 시지가 亥時를 넘어 子時로 넘어가는 경우(wrap): **일주·년주·월주는 변경하지 않는다.** 실제 출생일은 동일하기 때문이다. 조정되는 것은 시주 1개 기둥뿐이다.
- wrap 발생 시 시간(천간)은 원 일간 기준 시두법으로 산출한다 (야자시/조자시 유파 쟁점이 있으므로 `twin_wrap_convention` 플래그를 사전에 두고, 기본값은 위 규칙. 변경은 사용자 승인 필요).

**차트 변형(variant) 관리**:

```typescript
type ChartVariant = 'original' | 'twin_adjusted';

interface ChartVariantState {
  available: ChartVariant[];        // order=1: ['original'] / order≥2: 둘 다
  active: ChartVariant;             // order≥2 기본값: 'twin_adjusted'
  twinShift: number;                // order - 1
}
```

- order ≥ 2 등록 시 두 변형을 모두 생성·보관하되, **사전계산(T0~T2)과 풀이는 active 변형으로만** 수행한다. 비활성 변형은 T0만 보관 (비용 통제). 전환 시 해당 변형의 T1/T2를 재계산한다.
- 사용자는 설정에서 언제든 변형을 전환할 수 있다. 전환은 출생정보 수정과 동일한 캐시 무효화를 따른다 (docs/09).
- 보고서(RPT_*)는 생성 시점의 active 변형을 부록 재현성 파라미터에 기록한다 (docs/10 8장).

**사용자 안내 문구 (고정 템플릿 — 즉석 작문 금지)**:

```
{order_label}(둘째/셋째...)로 태어난 쌍둥이는 같은 시각에 태어나도
시주(時柱)를 한 시진씩 뒤로 보는 해석법이 있어요.
지금은 조정된 시주({adjusted_ganji})로 풀이하고 있습니다.
실제 태어난 시간 그대로의 시주({original_ganji}) 풀이 —
특히 시주가 담당하는 영역(말년·자녀·아랫사람·내면)이
더 잘 맞는다고 느껴지면 설정에서 원본으로 전환해 보세요.
```

(active='original'로 쓰는 사용자에게는 반대 방향 문구를 동일 템플릿 구조로 노출: "시주 영역 풀이가 잘 맞지 않는다면 조정본을 사용해 보세요.")
노출 시점: ① 등록 직후 1회 ② 시주 관련 풀이(말년운/자녀운 등) 첫 응답에 1회. 그 외 반복 노출 금지.

**Past Validation 연계 (권장 기능)**: order ≥ 2 사용자가 과거 검증(M14)을 진행하면 두 변형으로 각각 후보를 산출해 적중률을 비교하고, 더 잘 맞는 변형을 추천할 수 있다. 단 추천만 하고 전환은 사용자 결정 — 자동 전환 금지.

**유파 한계 (정직 기록)**: 시주 전진법은 통용되는 관습 중 하나일 뿐이며 시각 그대로 보는 유파도 있다. 시스템은 본 규격을 기본으로 하되 단정하지 않고, 안내 문구로 선택권을 사용자에게 둔다.

---

## 3. 2단계 — 추가 정보 (전체 필드 규격, 전 필드 스킵 가능)

```typescript
interface ExtendedProfile {
  occupation?: {
    categoryId: string;                 // 3-1 분류표의 ID (O01~O18) — 자유 텍스트 아님
    detail?: string;                    // 선택 자유 기술 (예: "백엔드 개발자") ≤30자
    employmentForm?: '정규직' | '계약직' | '프리랜서' | '자영업' | '법인대표' | '무급가족종사' | null;
  };
  residence?: {
    region: string;                     // 행정구역 (시/군/구 단위) — M10 locationBase 기본값
    livingRoomFacing?: Direction8 | 'unknown';   // 거실 기준 향(向) — 풍수/배치 질문용
  };
  maritalStatus?: '미혼' | '연애중' | '기혼' | '재혼' | '별거' | '이혼' | '사별';
                                        // '별거'는 실로그 존재 — 누락 금지
  children?: {
    count: number;                      // 0 허용
    items: {
      label: string;                    // '첫째', '둘째' 또는 이름
      gender?: 'M' | 'F';
      birth?: BasicProfile['birthDate'] 등 출생 정보 부분집합;  // 입력 시 동반자 등록 제안
      registeredCompanionId?: string;   // 동반자 전환 완료 시 연결
    }[];
  };
}

type Direction8 = 'N' | 'NE' | 'E' | 'SE' | 'S' | 'SW' | 'W' | 'NW';
```

### 3-1. 직업 분류표 (물상 풀이용 — 전체 18종 규격)

자유 텍스트가 아니라 **닫힌 분류**를 선택하게 한다. 물상 매핑(십성/오행 발현 형태)은 `occupation_taxonomy.json`에 두며, 매핑 내용은 전 항목 `reviewed:false`로 시작한다 (도메인 검수 필수).

| ID | 대분류 | 물상 축 (초기 매핑 — 검수 대상) |
|---|---|---|
| O01 | 사무/행정/기획 | 정관·정인 |
| O02 | 공무원/군인/경찰/소방 | 정관·편관 |
| O03 | 경영/임원/관리직 | 관성·편재 |
| O04 | 영업/판매/유통 | 편재·식상 |
| O05 | 금융/회계/세무/투자 | 정재·편재 |
| O06 | 교육/강의/연구 | 인성·식신 |
| O07 | 의료/보건/약무 | 인성·식상·현침 |
| O08 | 법률/특허/감사 | 관성·인성 |
| O09 | IT/개발/엔지니어링 | 식상·편인 |
| O10 | 제조/생산/기술직 | 식신·비견 |
| O11 | 예술/창작/디자인/콘텐츠 | 상관·식신 |
| O12 | 방송/연예/스포츠 | 상관·비겁 |
| O13 | 서비스/요식/미용/접객 | 식상·재성 |
| O14 | 운송/물류/항공/여행 | 역마·편재 |
| O15 | 건설/부동산/농림수산 | 토·목 물상 |
| O16 | 종교/상담/복지/활인업 | 편인·인성 |
| O17 | 학생/수험생 | 인성 (학업 모드) |
| O18 | 주부/무직/구직/은퇴 | 상태형 — 물상 보정 없음, 도메인 기본값 조정만 |

용도 (전체):
1. **물상 해석**: Event Form Engine(E3)에서 같은 신호의 발현 형태 확률 보정 (예: 역마 + O14 → "출장/노선 변경" 가중).
2. **Reality Context**: Manifestation(E6) contextModifier 입력.
3. **Past Validation**: 직업 변화 이벤트 검증 대조.
4. **어휘 선택**: LLM 서술 시 직업 맥락 어휘 (계산 아님, 문체만).

### 3-2. 거실 기준 방향 (livingRoomFacing)

- 정의: 거실 주 창(베란다) 방향이 향하는 8방위. 사용자가 모르면 'unknown'.
- 용도: 풍수 배치 질문(docs/08 D2-2 "책상 침대 방향"), 거주 공간 방위 보정. **이사 방위 계산(M10)의 기준점은 residence.region이며 livingRoomFacing이 아니다** — 혼용 금지.
- 명리 표준이 아닌 풍수 영역이므로 관련 보정 규칙은 `housing_rules.json`에만 정의된 것을 사용 (임의 규칙 발명 금지, docs/09 9장).

### 3-3. 결혼 상태 / 자녀

- maritalStatus는 M01/M02(연애·결혼 모듈)의 분기 입력: 기혼자의 "연애운" 질문은 배우자 관계운으로 우선 해석 + 확인, 이혼/사별은 재혼 모듈 경로.
- children.items에 출생 정보가 입력되면 **동반자 등록을 제안**한다 (강제 아님). 등록 시 E14 Companion으로 전환되고 isMinor 자동 판정 → 미성년 보호 정책(docs/08 G2) 연동.

---

## 4. 미입력 영향표 (전체 — 스킵 시 동작 규격)

| 미입력 필드 | 영향 받는 기능 | 미입력 시 동작 |
|---|---|---|
| birthTime (1단계) | 시주 전체, 말년·자녀궁 정밀도 | 3주 모드 + 한계 고지 (차단 아님) |
| birthPlace.city | 진태양시 보정 | 표준시 계산 + 경계 시각(시 경계 ±30분) 출생자에게만 고지 |
| occupation | E3 발현 형태 보정, E6 modifier | 보정 0, 일반형 발현 확률 사용 |
| residence.region | M10 방위 기준점, 지역 질문 | 질문 시점에 just-in-time 요청. 거절 시 방위 답변 불가 고지, 날짜 추천은 정상 |
| livingRoomFacing | 풍수 배치 질문 | 해당 질문에서만 1회 요청 |
| maritalStatus | M01/M02 분기 | '미혼' 가정하지 않음 — 모호하면 확인 질문 |
| children | 자녀 관련 질문 | 질문 시 인라인 정보(docs/08 A6)로 처리 + 등록 제안 |

**구현 가드**: 2단계 필드 부재를 이유로 오류를 던지거나 기능을 숨기는 코드 금지. 모든 모듈은 optional 입력으로 설계한다.

---

## 5. 페르소나 설정 (조합형 — 고정 프리셋 폐지)

이전 버전의 고정 연령·성별 페르소나를 폐지하고, 사용자가 5개 축을 직접 조합한다.

### 5-1. PersonaConfig (전체 축·값 규격)

```typescript
interface PersonaConfig {
  counselorGender: 'female' | 'male' | 'neutral';
  counselorAgeBand: '20s' | '30s' | '40s' | '50s' | '60s_plus';
  speech: {
    politeness: 'jondae' | 'banmal';            // 존대 / 반말
    style: 'haeyo' | 'hapsyo' | 'hagae' | 'banmal_chae';
    // 유효 조합 (전체): jondae→haeyo|hapsyo, banmal→banmal_chae|hagae. 그 외 조합은 UI에서 비활성
  };
  difficulty: 'easy' | 'standard' | 'expert';
  // easy    : 명리 용어 최소화, 생활 비유 중심. 간지·십성 언급 시 즉시 풀어쓰기
  // standard: 용어 + 풀어쓰기 병기 (기본값)
  // expert  : 원전 용어 적극 사용, 지장간·격국 수준 해설 포함
  userHonorific: {
    type: 'preset' | 'custom';
    presetId?: 'name_nim'      // '{displayName}님' (기본값)
             | 'nim_only'      // '님' 생략형 존칭 문장
             | 'name_only'     // '{displayName}' (반말 전용)
             | 'neo'           // '너' (반말 전용)
             | 'jane'          // '자네' (hagae 전용)
             | 'gogaeknim'     // '고객님'
             | 'seonsaengnim'; // '선생님'
    customText?: string;       // ≤10자. 금칙어 필터 통과 필수. politeness와 모순 시 거부
  };
}
```

기본값: `{ female, 40s, jondae+haeyo, standard, name_nim }`.

### 5-2. 조합 제약 (전체)

1. `politeness=jondae` ↔ honorific `neo`/`name_only` 불가. `banmal` ↔ `gogaeknim`/`seonsaengnim` 불가. `jane`는 `hagae`에서만.
2. **미성년 사용자(본인) 세션**: counselor 축 자유, 단 보호 톤 규칙(docs/08 G2)이 페르소나보다 우선. difficulty는 easy로 강제 하향하지 않되 expert 선택 시에도 단정·공포 표현 제한 동일.
3. counselorGender/AgeBand는 **어휘 톤 사전(persona_lexicon.json)의 1인칭·감탄·완곡 표현 선택에만** 사용한다. 풀이 내용·점수·판정에 영향 금지.
4. 페르소나는 사용자 전역 설정 + 세션 단위 임시 변경 가능("동화처럼 이야기해줘" 류 일회 toneOverride는 docs/03 OutputStyle로 처리하며 PersonaConfig를 변경하지 않는다).

### 5-3. 페르소나 프롬프트 블록 — 조립 템플릿 (전문, 규격)

LLM 시스템 프롬프트에 삽입되는 블록은 아래 템플릿의 슬롯 치환으로만 생성한다. 즉석 작문 금지.
템플릿은 두 부분이다 — ① 5축 슬롯 치환부 ② 슬롯이 없는 **공통 고정 문단**(문장 결). ②는 페르소나
조합과 무관하게 동일하게 붙으며, AI 문체의 세 패턴(주어·목적어를 꼬박 쓰는 완결성, 정석 어순만의
나열, 일정한 문장 길이)을 푸는 지침이다(2026-09-01 추가). 구현 SSOT: `saju_engines/persona.py`
`_PERSONA_TEMPLATE`.

개정 이력(코드와 동기화): 호칭 줄 "최대 2회 호명"(2026-06-14, 호칭 과다 반복 실로그) · 말버릇 줄
"현재 말투로 변환"(2026-06-23, 반말 페르소나에 해요체 말버릇이 그대로 끼던 결함) · 공통 고정 문단
(2026-09-01).

```
[페르소나 — 필수 준수]
당신은 {counselorAgeBand_label} {counselorGender_label} 사주 상담가다.
호칭은 "{resolvedHonorific}"만 허용한다(다른 호칭 금지). 그러나 답변/섹션 전체에서 최대 2회까지만 호명한다 — 첫머리에 한 번이면 충분하다. 문장이나 문단을 호칭으로 시작하는 습관을 금지하고(거의 모든 문장을 호칭으로 여는 것 금지), 이후 문장은 호칭 없이 바로 서술한다.
말투: {style_label}로만 말한다. 허용 종결어미: {endings_list}. 이 목록 밖 종결어미 사용 금지.
존대 수준: {politeness_label}. 혼용 금지.
풀이 난이도: {difficulty_rule}
1인칭·말버릇: {lexicon_phrases} 같은 말버릇의 결만 참고하되, 반드시 위 말투·종결어미로 바꿔 쓴다 — 예시가 해요체로 적혀 있어도 그대로 박지 말고 현재 말투로 변환할 것(예: 반말체면 '이 흐름 좋네요'→'이 흐름 좋네', '필요해요'→'필요해'). 다른 말투의 종결어미를 그대로 끼워 넣지 말 것(남용 금지, 응답당 2회 이하).
금지: 페르소나를 이유로 점수·날짜·간지·판정을 바꾸는 것. 사실 데이터는 입력 그대로 전달한다.

[문장 결 — 모든 페르소나 공통]
정보를 나열한 글이 아니라, 상담가 한 사람이 생각을 정리해 상대에게 건네는 말처럼 쓴다. 문장은 깔끔하되 너무 매끈하지 않게 — 약간의 호흡과 비어 있음, 말하듯 이어지는 흐름을 살린다.
앞뒤 문맥으로 알 수 있는 주어(특히 상대를 가리키는 말)와 되풀이되는 목적어는 생략하고 이어 쓴다. 같은 표현이 반복되면 덜어내고, 문장이 조금 비어 보여도 흐름이 사는 쪽을 택한다.
어순을 한 형태로 고정하지 않는다. "A는 B이다" 식 설명문만 잇지 말고, 문맥에 맞을 때는 결론을 앞에 두거나 짧은 구어체 문장을 섞어 리듬을 만든다. 억지스러운 도치나 과한 감정 표현은 넣지 않는다.
문장 길이에 차이를 둔다. 어떤 문장은 짧게 끊고, 어떤 문장은 맥락을 이어 길게 가져간다. 비슷한 길이의 문장이 줄지어 반복되지 않게 한다.
말줄임표·쉼표·여운이 남는 표현은 사람이 실제로 잠깐 멈춰 생각할 법한 자리에만 쓴다. 분위기를 내려고 넣지 않는다.
다음 상투구는 더 구체적인 문장으로 바꿔 쓴다: "이유는 단순하다", "결론적으로", "핵심은 다음과 같다", "중요한 것은", "~라고 할 수 있습니다", "~하는 것이 중요합니다".
이 변주는 모두 위의 종결어미·존대 수준·호칭 규칙 안에서 이루어진다.
```

공통 고정 문단의 설계 근거: 부정형 지시("~하지 마")보다 긍정형 프레임이 모델에 잘 먹히고, "완벽히 배제·엄격히
준수" 같은 강한 명령어나 말줄임표 강제는 오히려 "자연스러워 보이려 애쓰는 글"을 만들므로 "문맥에 맞을 때만"으로
묶는다. 마지막 줄은 5-4 준수 검사(종결어미 비율·존대 혼용)와 충돌하지 않도록 변주를 어투 규칙 안으로 잠근다.

슬롯 값 사전(`persona_lexicon.json` — 전체 구조):

```json
{
  "endings": {
    "haeyo":       ["~예요", "~이에요", "~보여요", "~좋겠어요", "~할 수 있어요", "~네요"],
    "hapsyo":      ["~입니다", "~합니다", "~보입니다", "~바랍니다"],
    "hagae":       ["~하네", "~일세", "~보게", "~함이 좋겠네"],
    "banmal_chae": ["~야", "~어", "~지", "~해봐", "~같아", "~거든"]
  },
  "difficulty_rules": {
    "easy":     "명리 용어를 쓰지 않거나, 쓸 경우 즉시 일상어로 바꿔 말한다. 비유 1개 이상.",
    "standard": "용어를 쓰되 괄호나 이어지는 문장으로 풀어쓴다.",
    "expert":   "십성·지장간·격국 용어를 정확히 사용하고 근거 경로를 용어 그대로 인용한다."
  },
  "lexicon": {
    "byGenderAge": { "...": "1인칭/감탄/완곡 표현 후보 — 전 항목 reviewed:false, 도메인·UX 검수 후 확정" }
  }
}
```

### 5-4. 페르소나 준수 검사 (docs/10 7장 갱신)

검사 6번(페르소나)은 다음으로 교체한다: ① 종결어미가 선택 style의 endings 화이트리스트 내 비율 ≥95% ② resolvedHonorific 외 호칭 미사용 ③ politeness 혼용 없음 ④ difficulty=easy일 때 미해설 전문용어 출현 0건. 위반 시 해당 응답/섹션 재생성.

---

## 6. 저장·연동 (전체)

```sql
CREATE TABLE user_profiles (
  user_id        TEXT PRIMARY KEY,
  basic          JSONB NOT NULL,        -- BasicProfile
  extended       JSONB,                 -- ExtendedProfile (전체/부분 null 허용)
  persona        JSONB NOT NULL,        -- PersonaConfig (기본값 채움)
  extended_completed_at TIMESTAMPTZ,    -- null = 2단계 스킵 상태
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

연동 지점 (전체):
1. BasicProfile → 만세력 엔진 입력 + T0 계산 트리거 (docs/09)
2. ExtendedProfile.occupation → E3/E6 + occupation_taxonomy.json
3. ExtendedProfile.residence.region → IntentJson.constraints.locationBase 기본값 (docs/03)
4. ExtendedProfile.maritalStatus/children → M01/M02/M04/M05 분기 + E14 동반자 제안
5. PersonaConfig → 프롬프트 블록 조립(5-3) + 정합성 검사(5-4) + docs/06 persona 필드
6. 대화 추출 갱신(F9) → 사용자 확인 → extended 갱신 → 관련 캐시 무효화

## 7. 사전 추가 (docs/05 레이아웃에 반영)

```
occupation_taxonomy.json   # O01~O18 + 물상 매핑 (reviewed:false 시작)
persona_lexicon.json       # endings/difficulty_rules/성별·연령 어휘 (lexicon은 reviewed:false)
honorific_presets.json     # 호칭 프리셋 + 금칙어 필터 목록
```

## 8. 리스크 (정직 기록)

1. occupation 물상 매핑과 persona lexicon은 도메인/UX 검수 전까지 reviewed:false — 검수 전 출시 금지.
2. 거실 방향 기반 풍수 보정은 명리 외 영역으로 근거가 약함 — housing_rules에 정의된 최소 규칙 외 적용 금지.
3. 결혼/자녀는 민감정보 — 개별 삭제, 풀이 외 용도 사용 금지, LLM 입력에는 해당 질문에 필요한 필드만 전달 (전체 프로필 일괄 주입 금지).
4. 호칭 custom 입력은 악용 가능(욕설/타인 사칭) — 금칙어 필터 + 길이 제한 필수.
