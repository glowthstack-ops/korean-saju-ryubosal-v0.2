# 외적 인상·매력 신호 (External Impression / Charm Signal) — v1

> 전문가 영상 자료("사주로 보는 미모", 자동자막 복원) + 사용자 1차 리뷰(2026-07-01) 기반.
> 본 문서가 **외적 인상·매력 신호의 단일 진실 공급원(SSOT)** 이며, `structural_context`(원국 구조
> 해석 블록)에 얹는 보조 신호를 정의한다. `docs/02`(구조 분석)·`docs/06`(LLM 입력 계약
> `structural_context`)·`marriage_resource`(`charm_present`)의 관련 항목을 보강한다.
> 본 문서는 **초안(reviewed:false)** 이며 검수 게이트(validate→compile→regression) 전
> 운영 반영 금지(절대원칙 5). 가중치·임계는 단일 영상 가설의 **잠정값**이며 캘리브레이션 전 미보장.

## 0. 핵심 원칙 (먼저 고정)

> **이 모듈은 "미인 판정"이 아니라, 원국에서 드러나는 외적 인상·분위기·표현 매력·관계적 끌림을
> 보조적으로 해석한다.** "예쁘다/못생겼다"는 단정하지 않으며, 부정 평가는 어떤 형태로도 출력하지
> 않는다(미해당 시 완전 무언급). 도화·식상·화기·금수상관 같은 신호는 **엔진이 코드로 판정**하고
> LLM에는 정제된 태그·문구만 넘긴다(원자료 과잉해석 방지, 절대원칙 1·2).

**성격**: 이 정보는 **재미 위주(entertainment-oriented)** 다. 따라서 아래 하드 가드는 지키되,
과잉 면책·반복 경고로 위축시키지 않는다. 톤은 가볍고 긍정적으로 간다(생활형 횡재 정책과 동일 결).

**모듈명**: `external_impression_profile` / 타입 `ExternalImpressionProfile`
(내부 코드에서 `appearance`/`미인` 네이밍 금지 — 리스크 및 오해 소지).

**not_purpose (금지 목적)**:
- 미모/외모 단정, 외모 점수화
- 부정적 외모 평가("외모가 떨어진다" 등)
- 성적 매력 단정, 성별 고정관념 강화

## 1. 신호 목록 (legacy → modern 재해석)

각 신호는 **엔진이 이미 계산한 값만 조회**한다(신규 명리 계산 금지). 참조 소스:
- 십성 그룹: `compute_ten_god_distribution()` → `groups["output"]`(식상), `groups["officer"]`(관성)
- 오행 분포: `compute_element_distribution()` → `distribution`, `season_adjusted_element_strength`, `strongest_element`
- 지지/일간: `pillars.four_pillars` (지지 집합), `day_pillar.stem` (일간)
- 도화·홍염 신살: `derive_natal_sinsal_modifiers()` / `MarriageResourceProfile.charm_present`

| code | legacy | 판정 술어(코드) | 성별 | modern 의미 |
|---|---|---|---|---|
| `METAL_WATER_EXPRESSION` | 금수상관 | 일간 오행=金(庚·辛) AND 원국 水 유효세력 > 임계 | 공통 | 청량감·세련된 말투·맑고 정돈된 분위기 |
| `METAL_WATER_OFFICER`(가산) | 금수상관+관성 | 위 성립 AND `groups["officer"]` > 임계 | 공통 | 정돈감·품격·사회적 호감이 더해짐 |
| `OUTPUT_EXPRESSION` | 식상 왕성 | `groups["output"]` 분포율이 적정대역 | 공통(legacy=여성중심) | 표정·리액션·자기표현·스타일링·콘텐츠성 매력 |
| `DAY_BRANCH_PEACH` | 일지 도화성 | 일지 ∈ {子·午·卯·酉} | 공통 | 가까운 관계에서 기억되는 인상·관계적 끌림 |
| `ACTUAL_DOHWA_OR_HONGYEOM` | 도화·홍염 | 신살 엔진이 도화/홍염 판정(`charm_present`) | 공통 | 시선·호기심을 끄는 분위기 |
| `NON_DAY_PEACH_BRANCH` | 도화 글자(일지 외) | 년/월/시 지지에 {子·午·卯·酉} 존재 | 공통 | 도화성/왕지 분위기 보조(약) |
| `FIRE_VISIBILITY` | 화기 왕성 | 火 분포율 ≥ 임계 OR 계절보정 火 강 OR `strongest_element==火`(심한 손상 없음) | 공통(legacy=여성중심) | 밝음·생기·표정·색감·무대성·화면성 |
| `YIN_HAI_TONE` | 寅·亥 인상 | 일지 ∈ {寅·亥}(강) / 년·월지에 존재(약) | 공통 | 寅=생동감·신선함 / 亥=부드러움·깊이감 |

**note-only (스코어 미포함)**:
- `WOOD_TONE`(甲乙 목 多): "머리숱" 직접 표현 금지. "목기의 생기·성장감·부드러운 선·관리된 인상"으로만, 내부 note.
- 반전 코멘트(옛 미인관): 미반영(면책성 사족 배제).

**legacy 성별 처리**: `OUTPUT_EXPRESSION`·`FIRE_VISIBILITY`는 원문이 여성중심이나 **현대 해석상 남녀
공통** 적용한다(사용자 2026-07-01 리뷰로 앞선 "여성전용" 결정 대체). 원문 맥락은
`legacy_female_centric: true` 플래그로만 보존하고 판정/노출에는 영향 없음.

**`gender=unknown` 정책**: 성별 미상 시
- common signal은 정상 계산(남녀 공통이므로).
- **legacy 성별 note는 숨김**(여성전용 legacy 문구가 성별 미상에서 노출되면 위험).
- `confidence = "low"`.
- 노출은 **직접 질문이거나 strong 대역일 때만** 허용(notable 단독으론 미노출).

## 2. 가중치 스코어링

단순 개수 카운트가 아니라 가중 합산(일지 도화와 년지 亥를 동일 1점 취급하면 과발동).

**primary_signals**:
| code | weight |
|---|---|
| `DAY_BRANCH_PEACH` | 1.2 |
| `ACTUAL_DOHWA_OR_HONGYEOM` | 1.0 |
| `METAL_WATER_OFFICER` (= METAL_WATER_EXPRESSION 성립 + 관성) | 1.0 |
| `OUTPUT_EXPRESSION` (적정대역) | 0.8 |
| `FIRE_VISIBILITY` (강) | 0.8 |

**secondary_signals**:
| code | weight |
|---|---|
| `METAL_WATER_EXPRESSION` (관성 없음, 약) | 0.5 |
| `NON_DAY_PEACH_BRANCH` | 0.3 |
| `YIN_HAI_TONE` (일지) | 0.5 |
| `YIN_HAI_TONE` (년·월지) | 0.2 |
| `WOOD_TONE` | 0.0 (note-only) |

> `METAL_WATER_EXPRESSION`은 관성 유무로 배타 배점한다: 관성 있으면 `METAL_WATER_OFFICER` 1.0
> (full signal, primary), 없으면 0.5 (weak, secondary). 이중 계상 금지.

**임계 band**:
```
weak    : 1.0 <= score < 1.8
notable : 1.8 <= score < 2.8
strong  : score >= 2.8
```

**OUTPUT_EXPRESSION 세부 대역**(식상 분포율):
```
< 18%        : 약함 (미부여)
18% ~ 35%    : 표현 매력 안정 (weight 0.8 부여)
> 35%        : 표현성 과다 — 부여하되 overactive_note("표현이 강해 호불호가 생길 수 있음")
```

**FIRE_VISIBILITY / 도화계 임계**: 초기값 25%(분포율 or 계절보정 강). 회귀 픽스처로 튜닝.

## 3. 노출 정책 (surface policy)

**기본값: hidden.** `structural_context`에는 넣되 **intent allowlist**로 노출을 게이트한다.
사용자가 "이직운/건강운"을 물었는데 매력 신호가 튀어나오면 신뢰도가 떨어진다.

```
surface 조건 (AND):
  1. is_notable == True  (score >= 1.8 AND primary_signal_count >= 1 AND category_count >= 2)
  2. intent in ALLOW  또는  사용자가 외모·매력·첫인상·도화·이성에게 보이는 모습을 직접 질문

ALLOW intents : love, marriage, compatibility, relationship, personality, self_image, appearance_question
SUPPRESS intents : career, wealth, health, education, relocation, date_selection
exception : 사용자가 직접 외모/매력/인상을 물으면 SUPPRESS 무시하고 노출
never_surface_negative : True  (부정·미달 서술 출력 금지)
```

- `weak` 대역(1.0~1.8)은 직접 질문 시에만 매우 조심스럽게, 그 외 무언급.
- `notable`/`strong`은 ALLOW intent에서 노출.

## 4. 출력 가드 (output_guard)

하드 금지(위반 시 차단):
- 예쁘다/잘생겼다/미인 **단정** 금지 → "인상·분위기·끌림이 잘 드러나는 구조"로
- 못생김·외모 부족 등 **부정 평가** 금지
- "방정맞다" 금지 → "표현이 앞서 보일 수 있다"
- 성적 매력 표현 금지
- 성별 고정 표현("남자/여자에게 잘 먹힌다") 금지
- 질문 맥락 없으면 무언급

톤(재미 위주 — 과잉 조심 금지):
- 면책·경고 **반복 금지**, 가볍고 긍정적으로.
- 단정만 피하면 자신감 있는 서술 허용("가까운 관계에서 인상이 쉽게 남는 편").

**금지어 테스트 목록**(회귀 테스트에서 출력 문구에 포함 시 실패 처리):
`미인`, `예쁘다`, `잘생겼다`, `못생겼다`, `방정맞다`, `섹시하다`, `성적 매력`,
`남자에게 잘 먹힌다`, `여자에게 잘 먹힌다`.

## 5. 현대적 해석 문구 (템플릿 — 즉석 작문 금지, docs/11 5-3 결)

- **금수상관+관성**: "말투·분위기·인상이 맑고 세련되게 보이는 구조입니다. 관성이 받쳐주면 튐보다
  정돈감·품격이 더해져 사회적 호감으로 이어지기 쉽습니다."
- **식상 왕성**: "표정·말·리액션·스타일링처럼 자신을 드러내는 방식이 눈에 띕니다. 외모 자체보다
  '표현 매력'·'콘텐츠성 있는 인상'으로 보는 편이 자연스럽습니다."
- **일지 도화**: "가까운 관계 안에서 인상이 쉽게 남고 상대가 호기심을 느끼기 쉬운 구조입니다.
  (외모 단정이 아니라 관계 장면에서의 끌림 신호)"
- **화기 왕성**: "밝음·생기·표정·색감·무대성이 살아납니다. 사진·영상·대면에서 존재감이 드러나는
  타입으로 볼 수 있습니다."
- **寅·亥**: "寅은 생동감·신선함, 亥는 부드러움·깊이감. 단독 판정보다 전체 인상 톤을 보조합니다."

## 6. 통합 지점 (구현 매핑)

| 산출/주입 | 위치 |
|---|---|
| 타입 정의 | `backend/packages/shared_types/saju_shared_types/external_impression.py` — `ExternalImpressionProfile`, `ImpressionSignal` |
| 판정 엔진 | `backend/packages/saju_engines/saju_engines/external_impression.py` — `analyze_external_impression(chart, gender) -> ExternalImpressionProfile` (순수함수) |
| 지시문 직렬화 | `saju_engines/structural_context.py` — `external_impression_lines(profile, intent) -> list[str]` (allowlist·is_notable 게이트, 미해당 시 `[]`) |
| LLM 입력 결합(채팅) | `chat_service._structural_context()` → `LlmInput.structural_context` append |
| LLM 입력 결합(리포트) | `report_service._ReportData.external_impression_block()` → 관계·자산 섹션(`_MARRIAGE_RESOURCE_SECTIONS`)에 합성 RELATIONSHIP intent로 append |
| 회귀 픽스처 | `backend/tests/` — 아래 §6.1 최소 6개 케이스 |

### 6.1 회귀 테스트 (최소 6개)

1. 금수상관 + 관성 있음 → `METAL_WATER_OFFICER` primary 1.0
2. 금수상관 + 관성 없음 → `METAL_WATER_EXPRESSION` secondary 0.5, **단독 노출 금지**
3. 일지 도화 + 식상 적정(18~35%) → notable 노출
4. 단순 子午卯酉만 존재(일지 아님) → 0.3, **단독 notable 노출 금지**
5. score notable이지만 `career` intent → suppress(무언급)
6. 사용자가 외모 직접 질문 → allowlist 예외로 노출
+ 금지어 미출현 검증(§4 목록)을 문구 생성 케이스에 부가.

**출력 계약**(`ExternalImpressionProfile`):
```
signals_matched: list[ImpressionSignal]   # code, weight, band, legacy, modern_meaning, notes
score: float
primary_signal_count: int
category_count: int
band: "none" | "weak" | "notable" | "strong"
is_notable: bool                          # score>=1.8 AND primary>=1 AND category>=2
legacy_female_centric_used: bool          # 진단용
```

비노출: 내부 가중치·퍼센트·score 원값은 LLM에 넘기지 않는다(정량화 오류 방지). 태그·문구만.

## 7. 확정 결정 로그 (2026-07-01 사용자 리뷰)

1. 모듈명 `external_impression_profile`(미인 판정 아님).
2. C1 관성 없음 → 미카운트 아님, **약신호 0.5**. 관성 있으면 full 1.0.
3. C4 = 실제 도화·홍염 신살(1.0) / 단순 子午卯酉 존재(0.3) **2층 분리**.
4. C2/C5 임계 25% 시작, OUTPUT은 18~35% 적정·35%↑ 과다 대역.
5. 반전 코멘트·머리숱 → 미모 스코어 제외(머리숱 서비스 노출 비추천, note-only).
6. C2/C5 **남녀 공통 + legacy 플래그**(앞선 여성전용 결정 대체).
7. 단순 "2개 이상" 대신 **가중 스코어 + primary≥1 + category≥2**.
8. `structural_context` 주입에 **intent allowlist** 적용.
9. 재미 위주 정보 — 하드 가드 유지하되 과잉 조심·면책 남발 금지.
