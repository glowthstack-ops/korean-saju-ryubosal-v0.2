# 사용자 결과 서명 계약 (CAL-ROLE-MARGIN-CENSUS / MC-E0)

```yaml
verdict:
  - USER_OUTCOME_SIGNATURE_DEFINED
  - OBLIGATION_FIELDS_DO_NOT_EXIST_IN_PRODUCTION
  - ROLE_CLASS_RETAINED_AS_COMPONENT_ONLY
  - DOWNSTREAM_LAYER_EXISTS_CORRECTION_RECORDED
  - MC_E1_FEASIBLE_WITH_AUDIT_OVERLAY
  - P3_DESIGN_DEFERRED_PENDING_SEMANTIC_CONTRACT
  - POPULATION_EXPANSION_PENDING_DISCRIMINATOR
```

production 무변경. 이 슬라이스는 **무엇을 "다른 답" 으로 볼 것인가**만 정의한다.

---

## 1. 먼저 정정 — 하류 층은 이미 있다

MC-D 문서 초판에 "P2 위의 결합·기간·사건 축은 아직 없다" 고 적었다. **틀렸다.**

```
build_luck_hierarchy          관계 계층 SSOT
  ↓
build_period_role_summary     기간 역할 요약 — favorability_map(chart) 소비
  ↓
render_period_role_summary    사용자 서술
render_hierarchy_narrative
  ↓
build_v2_scoring              P3 점수 — classify_relation_polarity 소비
```

`SAJU_PERIOD_HIERARCHY_ENABLED=true` 로 운영 중이고 `chat_service` 가 이 경로를 탄다.
**없는 것은 층이 아니라 "무엇이 달라져야 다른 답인가" 의 계약**이다. MC-E 가 그 계약이다.

---

## 2. 서명은 기존 값으로만 만든다

새 severity·확률 모델을 만들지 않는다. 아래는 전부 production 에 이미 있는 값이다.

### 방향

```yaml
overall_direction:   HierarchySummary
  CONSISTENT_SUPPORT · CONSISTENT_PRESSURE
  BACKGROUND_SUPPORT_TARGET_FRICTION · BACKGROUND_PRESSURE_TARGET_RELIEF
  MIXED_ACROSS_LAYERS · NO_CLEAR_DIRECTION

target_state:        PillarState
  FAVORABLE · ADVERSE · NEUTRAL · MIXED · UNKNOWN

background_state:    BackgroundState
  SUPPORT · PRESSURE · MIXED · NEUTRAL · NONE · UNKNOWN
```

`UNKNOWN` 은 중립이 아니다 — 서명에서도 구분해 보존한다.

### 서술 축

`classify_relation_polarity` 가 관계마다 내는 `narrative_axis` 의 **집합**.

```
favorable_activation · adverse_activation · mitigation · loss
mixed_binding · neutral_activation · structural_tension
```

이 7축은 MC-E 를 위해 만든 것이 아니라 **P1 렌더와 P3 점수가 공유하는 기존 SSOT** 다.

### 점수 노출 상태

```yaml
activation_status:  V2ActivationStatus
  ACTIVE · INCOMPLETE_COVERAGE · INVARIANT_FAILED · DISABLED

score_exclusions:   ScoreExclusionReason 분포
  NONE · STRUCTURAL_ONLY · ENGINE_CONFLICT · MIXED_UNALLOCATED
  UNKNOWN_ROLE · DERIVATION_UNAVAILABLE
```

### 구성요소 전용

```yaml
role_class:          favorable / adverse / neutral   # 단독 판정 금지
completeness_pair:   complete·fallback 조합           # provenance 전용 (MC-D)
```

---

## 3. 제외한 필드 — production 에 값이 없다

계약 초안의 다음 항목은 **만들지 않았다.**

| 필드 | 상태 | 확인 |
|---|---|---|
| `caution_required` | 제외 | production 에 해당 값·정책 없음 |
| `mitigation_required` | 제외 | 없음 |
| `loss_warning_allowed` | 제외 | 없음 |
| `dominant_claim_axis` | 제외 | 축 우선순위 정의 없음 |
| `severity_band` | 제외 | 없음 |

`section_claim_audit` 은 **금지 주장**(상속 시기·법적 분쟁 시기 등)을 막는 모듈이고
"무엇을 반드시 말해야 하는가" 의 의무 모델이 아니다. 이름이 비슷해 혼동하기 쉽다.

### 그래서 판정 갈래 하나가 직접 측정되지 않는다

```
USER_OUTCOME_OBLIGATION_DIVERGENCE   직접 측정 불가
```

의무 값이 없으므로 "한쪽만 caution 필수" 같은 판정을 낼 근거가 없다. 대신 **서술 축
집합의 차이**로 근사한다.

```
claim_axes 집합이 달라짐   →  설명에 들어갈 축이 달라진다는 뜻
                              (의무 판정은 아니다 — 근사임을 서명에 명시)
```

의무 모델을 새로 만들어 이 갈래를 채우지 않는다. 그건 감사가 아니라 설계이고, 지금
만들면 측정하려던 대상을 측정자가 정의해 버린다.

---

## 4. 비교 규약

13 independent charts 전체. near-tie 3건 + 대조군 10건을 함께 본다 — MC-B·MC-D 에서
대조군이 두 번 판정을 뒤집었다.

### 고정할 입력

```
model_outputs · chart context · useful candidate set
composites(기간 스택) · relation semantics · resolver/config version
```

바뀌는 것은 role realization 하나뿐이어야 한다.

### 비교에서 제외

```
오행 이름 자체            역할표 순열 차이 그 자체
selected_model_ref        model_complete · fallback 여부 · fallback provenance
```

`model_complete`·fallback 은 감사 메타데이터로 계속 보존하되 **사용자 결과 차이의 근거로
쓰지 않는다**(MC-D: margin·결정과 무상관).

### 분류

```
USER_OUTCOME_IDENTICAL              방향·축 집합·상태 전부 동일
USER_OUTCOME_NUMERIC_ONLY           내부 수치만 다름
USER_OUTCOME_AXIS_SET_DIVERGENCE    claim_axes 집합이 달라짐 (의무 근사)
USER_OUTCOME_DIRECTION_FLIP         overall_direction·target_state 가 뒤집힘
```

`OBLIGATION_DIVERGENCE` 대신 `AXIS_SET_DIVERGENCE` 를 쓴다 — 측정할 수 없는 것을
측정한 것처럼 이름 붙이지 않는다.

---

## 5. MC-E1 실행 가능성

in-process 로 확인했다. DB 불필요.

```
CompositeBuilder(dictionaries/) → build(result, ...)   ✔ 동작 (natal·daewoon·year·month)
favorability_map(result)                               ✔ {土용 金희 木기 火구 水한}
```

### 다만 주의할 결합이 있다

`CompositeBuilder.build` 는 **내부에서** `favorability_map(result)` 를 호출한다. 즉
composite 자체가 production 역할표에 물려 있다. alternate 실행은 composite 단계부터
alternate 역할표를 써야 하며, 그러려면 감사 overlay 가 그 조회를 대체해야 한다.

```
MC_E1_FEASIBLE_WITH_AUDIT_OVERLAY
```

production 에 파라미터를 뚫지 않는다. overlay 는 감사 스크립트 안에만 두고, primary
실행은 overlay 없이 돌려 **production 산출과 일치하는지 먼저 확인**한다 — 01c1-b1 에서
쓴 것과 같은 순서다. primary 재현이 실패하면 alternate 로 넘어가지 않는다.

---

## 6. 열려 있는 상태

```yaml
USER_OUTCOME_DIVERGENCE_DISTRIBUTION_MEASURED: not_started   # MC-E1
REPLACEMENT_DISCRIMINATOR_STATUS_DETERMINED:   not_started   # MC-E2
YongsinDecisionSet_replacement:                blocked       # MC-E3, 판별력 확인 후
POPULATION_EXPANSION:                          pending_discriminator
```

지금까지 탈락한 판별자는 10~12번 문서에 있다. MC-E1 도 13/13 으로 나오면 새 내부 축을
더 찾지 말고 실제 질문·기간·사건이 포함된 golden cohort 로 넘어간다.
