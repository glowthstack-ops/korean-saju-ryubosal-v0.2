# CAL-P1 설계 — 정적 결핍 vs 운 작동 이원 질문 + 성향 반박 결 태깅

> 상태: **CAL-P1 core 완료(2026-07-03)** — P1-a(스키마+태깅) ✅ P1-b(pair 생성·B 앵커
> 랭킹·suppress·cap·응답 축적) ✅ P1-c(A×B 매트릭스 LLM 힌트·chat/report 주입·FE 전용
> 렌더링) ✅. 남은 것(release/review 트랙): `RELEASE_CHECKLIST_CALIBRATION.md` —
> R-1 문구 감수 / R-2 denial_kind 실사용 보정 / R-3 모바일 실기기 확인.
>
> 출처: 실상담 사례 분석(`cases/1980_1122_job_report_case.md` §2-1 木 이원성) + QA-P0에서
> 관찰한 성향 반박의 결 차이. 상위 원리: `YONGSIN_OPERATIONAL_ROLE_SPEC.md`(정적 vs 작동
> 2계층), `docs/14_CALIBRATION_RESOLUTION.md`(발생/경험 분리·변동성 축).

## 0. 목적 — 한 문장

**"원국에 없어서 부족한 것"과 "운에서 들어와 실제로 압박·사건으로 작동하는 것"을, 같은
오행/십성이라도 분리해서 묻는다.** 둘은 모순이 아니다 — *없어서 허전하고, 들어오면
부담스러운 것*이 동시에 성립할 수 있다(木 사례 전형). 이 둘을 "木이 들어온 해가
좋았나요?" 하나로 합쳐 물으면 어느 쪽 신호인지 판별할 수 없다.

기준 사례(1980-11-22 기해일주): 원국 木 부재(관성 표면 부재) → 규칙·소속 기준의 결핍
체감(정적). 동시에 木 운 유입 시 관성 압박·직장 변화가 사건으로 작동(작동). 상담사
문서가 이 둘을 혼용해 "木=약이자 병"이라는 모순처럼 보였으나, 2계층으로 보면 정합.

## 1. 질문 축 2종

### 1-A. `static_deficiency_probe` — 정적 결핍 체감 확인

원국의 결핍/약세가 **평소 삶의 체감**으로 나타났는지 묻는다. 특정 연도에 앵커하지
않는 비시간형 질문(trait_probe와 동형, `period_type="trait"`).

- **트리거(결정론 엔진 predicate — LLM 판단 금지, 원칙 1)**:
  - 오행 축: `force_analysis.five_elements` 부재/최약 오행(`has_all_elements=False`의
    결핍 오행, 또는 element_presence '오행결핍'의 대상).
  - 십성 축: 십성 그룹(관성/재성/식상/인성/비겁)이 표면 부재(`visible_absent`가 그룹
    구성 십성을 모두 포함).
- **응답**: trait_probe와 동일 4지 → `agreed / mixed / denied / unclear`
  (대체로 그렇다 / 상황에 따라 다르다 / 그렇지 않다 / 잘 모르겠다) + 자유 한 줄(선택).
- **채점 비반영**(§5).

예시(木/관성 축):
> 일이나 진로에서 "내가 따라야 할 기준이나 체계가 분명하면 좋겠다"는 느낌이 있었나요?
> 평소에 진로 방향, 규칙, 소속감을 스스로 잡기 어렵다고 느낀 적이 있어도 자연스러운
> 구조예요.

### 1-B. `transit_activation_probe` — 운 작동 확인

같은 오행/십성이 **운에서 강하게 들어온 과거 해**에 실제로 작동(압박·변화·사건)했는지
묻는다. 연도 앵커형(기존 검증 질문과 동형).

- **연도 선택(결정론 — 2026-07-03 확정)**: 세운에서 target axis 오행이 활성인 해만 B
  후보. 대운 중첩은 **boost로만** 쓴다(무조건 우선 아님 — 교운기 변화와 축 작동을
  사용자가 구분하기 어렵기 때문). 랭킹:

  ```text
  B_anchor_score = sewoon_target_axis_strength   # 천간+지지 동시 활성 > 단일 활성
                 + daewoon_overlap_boost          # 대운 target axis 중첩
                 + recall_quality_bonus           # 기존 판별 score(깨끗한 해 등)
                 - transition_conflict_penalty    # q_transition 앵커와 동일 해=강, ±1년=약
  ```

  후보가 q_transition 앵커 해뿐이면 사용 가능하되, 질문 문구에 교운 중첩 단정 회피
  힌트를 붙인다: *"그 시기는 대운 전환감도 함께 있었을 수 있어요. 그중에서도 직장·책임·
  규칙·소속 압박이 실제로 강해졌는지 확인해 주세요."*
  **기본 q1~q5 생성 후 남은 연도에서 선택**(QA-P0 굶김 방지 불변식 승계).
- **응답 4지**: `strong / partial / none / unknown`
  (실제로 그런 압박·변화가 강했다 / 어느 정도 있었다 / 딱히 없었다 / 기억나지 않는다)
  + 자유 한 줄(선택).
- **채점 비반영**(§5). 단 mixed/변동성 검증(docs/14 §0 ④)과 겹치는 해는 향후 CAL-P2에서
  교차 참조 후보(이번 스코프 아님).

예시(木/관성 축, 직업 문맥):
> {YYYY}년(간지·나이)은 木 기운이 강하게 든 해예요. 그 무렵 퇴사·이직 고민, 조직의
> 압박, 책임 증가, 평가 부담 같은 변화가 실제로 있었나요?

### 1-C. 두 축의 관계 — CAL-P0 trait_probe suppress 규칙 (2026-07-03 확정)

- CAL-P0 `trait_probe`는 **표현 적중도**(해석 문구가 맞나) 확인용 단문, CAL-P1 A/B 쌍은
  **역할 판별 재료**(정적 결핍 vs 작동)를 모으는 구조화 질문.
- **P1 pair가 생성된 axis는 trait_probe 후보에서 제외(suppress)** — 같은 축을 두 번
  묻는 느낌 차단. pair 생성 불가면 기존 CAL-P0 trait_probe fallback 유지.
- 현침살 communication_style trait_probe는 P1 axis와 다르면 유지 가능.
- 추가 문항 cap ≤3을 넘으면 **P1 pair 우선, trait_probe drop**.
- 우선순위: `transition_probe > P1 static/transit pair > trait_probe`.

## 2. 쌍(pair) 생성 원칙 — 반드시 둘을 함께

1. **단독 생성 금지**: A(결핍 체감)와 B(운 작동)는 같은 축(pair_id 공유)에 대해 항상
   쌍으로 생성한다. B의 앵커 연도가 없으면(해당 오행 활성 해가 후보에 없음) **쌍 전체를
   생성하지 않는다** — A만 나가면 "결핍=보완 필요"로 기울어진 반쪽 신호가 된다.
2. **단일 좋다/나쁘다 질문으로 합치기 금지**: "木이 들어온 해가 좋았나요?"류 금지.
   A는 '부족하게 느꼈는가', B는 '실제로 작동했는가'만 묻는다(길흉 어휘 배제).
3. **cap**: 쌍 최대 1개(질문 2문항). CAL-P0 probe와 합산해 추가 문항 총 3개(교운 1 +
   trait/pair 계열 2)를 넘지 않는다 — 온보딩 피로 방지.
4. **축 선정 우선순위**(쌍이 여러 축에서 가능할 때): 용신 논쟁 축(candidate_models 간
   역할이 갈리는 오행) > 표면 부재 십성 그룹 > 부재 오행. 사례의 金/木처럼 감수
   플래그가 걸린 축이 있으면 그 축을 최우선(판별 정보 가치 최대).
5. **표시 순서(2026-07-03 확정)**: `transition_probe → A(static) → B(transit) → q1~q5 →
   trait_probe fallback`. A가 B보다 먼저 — 평소 체감을 먼저 물어 응답 오염 방지(B를
   먼저 물으면 그 해 기억이 평소 체감 응답을 물들인다). **내부 생성 순서는 QA-P0
   불변식대로** 기본 q1~q5 먼저 생성 → 남은 슬롯/연도에서 probe 생성 → 표시만 재배치.
6. **노출 위치(확정)**: 별도 후속 스텝을 만들지 않고 현행 CalibrationPanel에 합류
   (온보딩 피로가 더 큰 리스크). 모바일 과밀 시 P1 pair는 접기/간결 카드로 처리.

## 3. 오행/십성별 질문 쌍 예시 (초안 — 전 항목 감수 대상, reviewed:false)

> 문구는 사전(JSON)으로 관리한다(§8 P1-b, 원칙 5·12 — 즉석 작문 금지). 아래는 그 사전의
> 초안 규격이다. 길흉 단정·사건 단정 어휘 금지, 회상형 존대 유지.

### 3-1. 오행 축 (결핍 오행 기준)

| 축 | A. 결핍 체감 (평소) | B. 운 작동 (강세 해) |
|---|---|---|
| 木 | 방향·규칙·소속의 기준이 분명하면 좋겠다고 느꼈나요? | 그 해 책임·평가·조직 압박, 직장 변동이 실제로 강해졌나요? |
| 火 | 활력·표현·드러남이 부족하다고 느꼈나요? | 그 해 주목·발표·경쟁 같은 드러나는 일이 몰려 벅찼나요? |
| 土 | 생활 기반·안정 루틴이 약하다고 느꼈나요? | 그 해 거주·기반 이동이나 책임져야 할 일이 실제로 늘었나요? |
| 金 | 마무리·결단·기준 세우기가 어렵다고 느꼈나요? | 그 해 정리·단절·평가처럼 끊어내는 일이 실제로 몰렸나요? |
| 水 | 여유·회복·유연함이 부족하다고 느꼈나요? | 그 해 자금 흐름·정보·이동 변수가 실제로 출렁였나요? |

### 3-2. 십성 그룹 축 (표면 부재 그룹 기준)

| 축 | A. 결핍 체감 | B. 운 작동 |
|---|---|---|
| 관성 | 따라야 할 체계·소속·직업 기준이 부족하게 느껴졌나요? | 그 해 직장·책임·규칙·평가 압박이 실제로 강해졌나요? |
| 재성 | 실리·성과·현실 감각을 잡기 어렵다고 느꼈나요? | 그 해 돈·성과·현실 과제가 실제로 몰려 부담됐나요? |
| 식상 | 표현·시도·배출구가 부족하다고 느꼈나요? | 그 해 일 벌임·표현·활동이 실제로 과해져 지쳤나요? |
| 인성 | 배움·지지·쉴 언덕이 부족하다고 느꼈나요? | 그 해 공부·문서·의존할 일이 실제로 늘어 무거웠나요? |
| 비겁 | 내 편·추진 동력이 부족하다고 느꼈나요? | 그 해 경쟁·분배·주변 사람 문제가 실제로 불거졌나요? |

## 4. `trait_denial_kind` — 성향 반박 결 태깅

trait_probe·A축 응답의 자유 진술(`trait_statement`)을 **룰 기반으로만** 결 분류한다
(초기엔 LLM/임베딩 분류 금지 — 과분류 위험). 분류값도 채점 비반영.

```json
{
  "trait_denial_kind": {
    "absolute":    {"description": "성향 자체를 부정", "example": "저는 외로움을 거의 못 느껴요."},
    "situational": {"description": "특정 상황에서만 다름", "example": "글로는 괜찮은데 면접에서는 말을 못해요."},
    "temporal":    {"description": "시기에 따라 달라짐", "example": "예전에는 못했는데 요즘은 좀 나아졌어요."},
    "mixed":       {"description": "복수 결이 섞임", "example": "평소엔 괜찮은데 예전 면접에서는 너무 힘들었어요."},
    "unclear":     {"description": "분류 불가·정보 부족"}
  }
}
```

**초기 룰(키워드 — 초안, 실사용 진술 축적 후 보정)**:

- situational 표지: `면접`, `회의`, `사람 앞`, `발표`, `처음 보는`, `일할 때`, `집에서`,
  `~에서는`, `~할 때만`
- temporal 표지: `예전`, `옛날`, `요즘`, `최근`, `어릴 때`, `지금은`, `나이 들`, `~하고
  나서부터`
- absolute 표지(강부정): `전혀`, `아예`, `한 번도`, `항상 아니`, `거의 못`
- **우선순위**: situational과 temporal 표지가 **둘 다** 있으면 `mixed`. 하나만 있으면
  해당 결. 둘 다 없고 강부정 표지가 있으면 `absolute`. 그 외 `unclear`.
- 진술이 비어 있으면(선택 응답만) 태깅하지 않는다(null) — `unclear`와 구분(정보 없음 ≠
  분류 실패).

**활용(scoring 비반영)**: `situational`/`temporal`은 "성향이 틀렸다"가 아니라 **발현
조건 정보**다 — LLM 표현 힌트에 그 조건을 그대로 싣는다(예: "면접에서는" → 즉흥 대면
조건에서 잠복). `absolute`가 같은 축에서 반복 축적되면 expert_review 우선순위를 올린다
(역할 재검토 후보 — 단 CAL-P2 전까지 어떤 자동 조정도 금지).

## 5. Safety Invariants (불변식)

**금지**:
- 용신/희신/기신 role 변경 금지
- role confidence 조정 금지 (CAL-P2 후보로 보관만)
- event score 변경 금지 / favorability 변경 금지
- static_deficiency 응답으로 바로 용신 확정 금지
- transit_activation 응답으로 바로 기신 확정 금지
- trait 반박을 엔진 오류로 확정 금지
- 정적 결핍과 운 작동을 하나의 좋다/나쁘다 질문으로 합치기 금지
- 기본 q1~q5 구성 변형 금지(연도 선점 금지 — QA-P0 불변식 승계)

**허용**:
- `review_flags`/pair 피드백 축적 (`scoring_effect="none"`, `review_status="accumulate_only"`)
- LLM 표현 조정 힌트 생성 (§6-2)
- expert_review 자료 축적 (감수 시트 연계)
- CAL-P2에서 confidence 조정 **후보**로만 보관

## 6. 응답 저장·해석 스키마 (초안)

### 6-1. 저장 — `deficiency_pair_feedback`

```json
{
  "type": "deficiency_pair_feedback",
  "pair_id": "pair_wood_officer",
  "axis_type": "element | ten_god_group",
  "axis_id": "wood",
  "engine_basis": ["木 부재", "관성 표면 부재"],
  "static_response": "agreed | mixed | denied | unclear",
  "static_statement": "…",
  "static_denial_kind": "absolute | situational | temporal | mixed | unclear | null",
  "transit_year": 2016,
  "transit_response": "strong | partial | none | unknown",
  "transit_statement": "…",
  "scoring_effect": "none",
  "review_status": "accumulate_only"
}
```

### 6-2. 해석 매트릭스 (LLM 표현 힌트·감수 자료 전용 — 판정 비개입)

| 결핍 체감(A) | 운 작동(B) | 의미 | LLM 표현 힌트 방향 |
|---|---|---|---|
| agreed | strong/partial | **동시 성립**(木 사례 전형) | "없어서 허전 + 들어오면 부담"의 양면 서사. 기신 표현을 유지하되 결핍 서사를 병행하고, 두 상태를 모순으로 쓰지 말 것 |
| agreed | none | 결핍 체감만, 작동 미확인 | 결핍 보완 조언 위주. 운 유입 부담 서술은 단정하지 말 것 |
| denied | strong/partial | 작동만 확인 | 결핍 서사 억제(본인 비체감). 운 시기의 작동 부담·관리 위주 |
| denied | none | 양쪽 비체감 | 이 축 서술을 최소화·단정 회피 |
| mixed/unclear | any | 정보 부족 | 조건부 표현 유지, 확인 질문 여지 |

expert_review 관점: `agreed+strong` 축적은 해당 축의 정적/작동 분리 라벨(operational
spec)의 실측 지지 자료, `denied+none` 축적은 그 축 결핍 서사 자체의 재검토 자료가 된다.

## 7. 테스트 기준 (초안 — 구현 Phase에서 확정)

1. **쌍 생성**: A·B가 항상 함께 생성되고 pair_id를 공유한다. B 앵커 해가 없으면 쌍
   전체 미생성(A 단독 0건).
2. **cap**: 쌍 ≤1, CAL-P0 probe 포함 추가 문항 ≤3.
3. **기본 질문 불변**: probe/pair 유무와 무관하게 q1~q5 (id, year) 구성이 기준선과 동일
   (QA-P0 기준선 대조 방식 재사용).
4. **채점 불변식**: pair 응답 전 조합(agreed/denied × strong/none 등)에 대해
   model_scores·selected_model·final_* 동일.
5. **B 연도 선택**: 앵커 해의 activated_elements에 해당 축 오행 포함. 기본 질문 미사용
   연도에서만 선택.
6. **태깅 룰**: 대표 진술 각 결 2건 이상 + mixed 우선순위(둘 다 표지) + 빈 진술 null
   케이스 단위 테스트.
7. **힌트**: 해석 매트릭스 행별 힌트 문구 생성 조건 검증(denied+none → 최소화 힌트 등).
8. **문구 가드**: A/B 질문 문구에 단정·길흉 어휘(반드시/무조건/좋았나요·나빴나요류
   합성 질문) 부재.
9. **CAL-P0 회귀**: 기존 transition/trait probe 동작·기존 전체 스위트 불변.
10. **suppress**: P1 pair가 생성된 axis에서는 CAL-P0 trait_probe가 중복 노출되지 않는다.
11. **앵커 회피**: B 앵커 해가 q_transition과 같으면 다른 후보가 있을 때 회피한다.
12. **중첩 예외 문구**: 다른 후보가 없어 q_transition과 같은 해를 쓰는 경우에도 문구가
    단정되지 않는다(교운 중첩 회피 힌트 부착).
13. **총량 cap**: 추가 문항 총합이 cap ≤3을 넘지 않는다(초과 시 P1 pair 우선,
    trait_probe drop).

## 8. 구현 단계 제안 (본 문서 승인 후)

- **P1-a**: 스키마(pair 질문·응답·`deficiency_pair_feedback`·denial_kind) + 태깅 룰 함수
  (순수 함수, 단위 테스트).
- **P1-b**: 질문 쌍 사전(JSON, §3 초안 — validate 등록, reviewed:false) + 질문 생성기
  배선(축 선정·B 연도 선택·cap·기본 질문 보호) + scorer 축적·힌트.
- **P1-c**: FE 렌더링(A=trait형 재사용, B=연도 앵커형) + QA-P1(synthetic, QA-P0 하네스
  확장).

**미결 3건 — 2026-07-03 데굴님 확정(본문 반영 완료)**:
1. B 연도: 세운 활성 해 기본 + 대운 중첩 boost + 교운 앵커 동일/인접 penalty(§1-B).
2. 노출 위치: 현행 CalibrationPanel 합류, 표시 순서·cap·모바일 접기(§2-5·6).
3. suppress: P1 pair 생성 axis의 trait_probe 미노출, fallback 유지(§1-C).
