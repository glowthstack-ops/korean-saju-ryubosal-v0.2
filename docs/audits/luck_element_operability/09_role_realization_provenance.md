# 역할 실현 provenance 중간 감사 (CAL-ROLE-BORDERLINE-01c0)

```yaml
overall: C1B_PROVENANCE_DEPENDENT_ALTERNATIVE      # 01c1-c 확정
```

01c0 은 `ROLE_REALIZATION_PROVENANCE_INCOMPLETE` checkpoint 로 닫혔고, 01c1 의 세 슬라이스가
그 미결을 해소했다. 아래 1~3장은 **01c0 시점의 기록을 그대로 둔다** — 정정 이력이 감사의
본체이므로 결론이 바뀌었다고 덮어쓰지 않는다. 최종 판정은 7장에 있다.

### 검증 관계

```yaml
validated_base_head:   eeaed83
validated_fingerprint: f32757b
checkpoint_commit:     c8e7b4b
```

스위트는 **커밋 직전의 동일 트리**를 검증했고 `c8e7b4b` 가 그 검증된 변경을 담았다.
커밋 해시 자체가 검증된 것이 아니다 — 이 구분을 흐리면 "커밋이 통과했다" 는 표현이
검증 범위를 실제보다 넓게 만든다.

---

## 1. 확정된 것

```yaml
canonical_selection_stage: VERIFIED
canonical_realization_stage: PARTIALLY_VERIFIED

selection_candidate_type: YONGSIN_ELEMENT
selection_score_contract: FINAL_COMPARABLE_SELECTION_SCORE

primary:   {element: 土, score: 0.1508, model: eokbu_normal,    confidence: 0.6033}
runner_up: {element: 水, score: 0.1400, model: pattern_sangsin, confidence: 0.7000}
decision_margin: 0.0108

score_contract:
  formula: model_confidence × axis_weight        # role=heesin 이면 ×0.85
  aggregation: per-element max                   # 합산 아님
  confidence: CONFIDENCE_IS_WEIGHTED_SELECTION_INPUT
  confidence_ranking: CONFIDENCE_IS_NOT_STANDALONE_RANKING_SCORE

canonical_realization:
  base_classification: FALLBACK_ONLY
  complete_model_map_promotion: CONFIRMED
  special_branch_precedence: CONFIRMED
  model_contribution_dependency: CONFIRMED

primary_case_a:
  selected_model: eokbu_normal
  model_complete: true
  model_map_promoted: true
  canonical_origin: COMPLETE_MODEL_ROLE_MAP

runner_up_case_a:
  probable_top_model: pattern_sangsin      # 미재생 — probable
  model_complete: false                    # 부분맵 관측
  probable_fallback: _classify_roles       # 미재생 — probable
  actual_replay_result: NOT_YET_VERIFIED

counterfactual_role_realization: NOT_YET_ESTABLISHED
scenario: PENDING_C1B_OR_C2
```

### 실현 경로

```python
roles = _classify_roles(yongsin_el)              # 정적 생극 — 폴백 전용
if bridge_tonggwan:            roles = _classify_bridge_roles(...); special = True
elif support_day_master 특수:   roles = {...};                      special = True

selected_model = top_model·yongsin_el 일치 중 최고 confidence
model_complete  = selected_model 의 5역할이 모두 채워짐
model_map_promoted = not special and model_complete
if model_map_promoted:
    roles = 선택 모델의 자체 역할표          # ← canonical 의 실제 출처
```

사례 A는 `eokbu_normal` 이 완비이므로 승격 경로다.

```
canonical   土 용 / 金 희 / 木 기 / 火 구 / 水 한   ← eokbu_normal 자체맵
_classify   土 용 / 火 희 / 木 기 / 水 구 / 金 한   ← 쓰이지 않은 폴백
```

### 선택 점수 분해

```
土   0.6033 × 0.25 = 0.150825 → 0.1508      eokbu 축
水   0.7000 × 0.20 = 0.140000 → 0.1400      pattern 축
```

**순서를 뒤집은 것은 confidence 가 아니라 축 가중치다.** confidence 는 낮은 쪽(0.6033)이
이겼다. confidence 는 점수의 곱셈 인수이고, 단독으로는 순위를 결정하지 않는다.

---

## 2. 정정 원장 — 역할 provenance

이번 감사에서는 결론보다 **어떤 주장이 왜 철회됐는지**가 중요하다.

| 이전 주장 | 상태 | 현재 확인된 사실 |
|---|---|---|
| canonical 은 `_classify_roles(yongsin)` 결과 | **철회** | 완비 모델맵이 있으면 그 모델 역할표로 승격 |
| canonical 은 후보 모델 선택과 무관 | **철회** | 실현이 `selected_model` 과 모델 완전성에 의존 |
| `confidence` 가 최종 selection score 자체 | **철회** | `confidence × axis_weight` 가 selection score 를 구성 |
| `confidence` 는 선택에 사용되지 않는다 | **재철회** | 실제 점수 계산의 곱셈 인수다 |
| `confidence` 단독 순위로 primary 가 정해진다 | **기각** | 축 가중치가 함께 작용한다 |
| `0.1508/0.1400` 은 진단 점수 | **철회** | 동일 척도의 실제 용신 오행 선택 점수 |
| `competing` 이 canonical 선택을 바꿈 | **기각** | warning 과 probable 승격 차단에만 쓰인다 |
| `_classify_roles(水)` 가 곧 runner-up canonical | **미확정** | 水 경로의 top model·완전성·특수분기를 재실행해야 한다 |

`confidence` 행은 **한 번 철회한 뒤 다시 정정한 항목**이다. "보고용일 뿐" 이라는 첫 정정이
과잉이었고, `candidates.py` 의 `_put(useful, m.yongsin, m.confidence * w, ...)` 가 실제
계산식이다. 기록을 덮어쓰지 않고 재정정 이력으로 남긴다.

---

## 3. 정정 원장 — 감사 방법론

역할 의미론의 근거가 아니라 **감사 절차의 결함**이다. 위 표와 섞지 않는다.

| 이전 주장 | 상태 | 결함 유형 |
|---|---|---|
| `adapter_identity_hash` 가 null | **철회** | 없는 키 조회 결과 `None` 을 실제 null 필드로 오인 |
| `candidate_models.model/score` 가 비어 있음 | **철회** | 실제 필드는 `model_type`·`confidence` — 같은 오류 반복 |
| 미도달 규칙은 R41 하나 | **철회** | `R01_UNKNOWN_ROOT` 도 미도달(방어 가드) |
| `competing` 이 `yongsin_el` 대입보다 뒤에서 계산 | **철회** | 소스 위치를 의미론 소비처로 오인 |

### probe 계약

```
실제 schema 필드를 먼저 열거한다
정의되지 않은 키 접근은 즉시 실패시킨다
dict.get 으로 추정 필드를 조회하지 않는다
None 값과 필드 부재를 구분한다
값의 의미는 필드 존재 여부가 아니라 실제 소비처까지 추적한다
소스 순서는 데이터 흐름의 대체 증거로 쓰지 않는다
파생값은 계산식의 모든 인수를 확인한다
```

`competing` 의 진단 전용 판정은 소스 순서가 아니라 두 층으로만 뒷받침한다.

```
AST   competing 을 읽는 지점의 소비처가 warnings.append 와 status 대입 둘뿐이다
행동  competing 참·거짓 코호트 양쪽에서 실현 규칙(모델맵 승격/특수분기)이 동일하다
```

status 승격 차이는 **행동으로 증명되지 않았다** — 관측 코호트 8건은 전건 `candidate` 이고
`probable` 은 `len(models) == 1` 을 함께 요구해 도달하지 않는다. AST 소비처 사실로만
고정하고 행동 근거가 있는 것처럼 적지 않는다.

---

## 4. 다음 슬라이스 — CAL-ROLE-BORDERLINE-01c1

```
Runner-up canonical realization replay
```

한 번에 구현하지 않는다. 세 단계로 나누고 각 단계에 독립 승인점을 둔다.

```
01c1-a   역할 실현 경계 inert 추출
01c1-b   primary·runner-up 독립 재생
01c1-c   provenance 판정과 종료 감사
```

### 01c1-a — 실현 resolver 추출

기존 production 경로를 다음 경계로 감싼다. **동작을 바꾸지 않는 inert refactor 다.**

```python
resolve_realized_roles(
    *,
    chart_context,
    selected_yongsin_element,
    useful_candidates,
    model_outputs,
) -> RoleRealizationResult
```

결과가 보존해야 하는 것.

```
selected_yongsin_element   top_model            selected_model
special_roles              model_complete       model_map_promoted
base_role_map              final_role_map       reason_codes
```

하드 게이트.

```
기존 canonical 역할표 전건 동일
기존 selected_model 동일
기존 confidence·status·warnings 동일
후보 점수·순위 동일
production 응답·LLM 입력 동일
```

### 01c1-b — primary 부터 재생

**primary 재현이 첫 번째 승인점이다.** 사례 A 의 실제 선택인 土 만 먼저 넣는다.

```
forced yongsin = 土
→ selected_model      eokbu_normal
→ model_complete      true
→ model_map_promoted  true
→ final_role_map      기존 canonical 과 5역할 전부 동일
```

하나라도 다르면 **runner-up 재생으로 넘어가지 않는다.**

성공한 뒤에야 같은 원본 입력에서 水 를 넣는다.

```
forced yongsin = 水
→ top_model · selected_model · model_complete · special branch · model_map_promoted
   를 모두 실제 재계산·재판정하고 final_role_map 을 산출한다
```

외부 역할표는 기대값이 아니라 **산출 후 비교 대상**으로만 쓴다.

#### 순서 독립성

각 실행은 fresh context 에서 수행한다.

```
土 단독 · 水 단독 · 土→水 · 水→土 · 水→水 반복
```

성립해야 하는 것.

```
水 final_role_map · selected_model · model_map_promoted 전건 동일
土 결과도 실행 순서와 무관
원본 model_outputs·useful_candidates 불변
```

primary 실행에서 변형된 `roles`·model 객체·request-local dict 를 runner-up 실행에
재사용하지 않는다.

#### 선택 단계로의 feedback 확인

실현 resolver 가 다음을 수정하지 않는지 **별도로** 고정한다.

```
useful score · useful_sorted · yongsin_el · competing · selected decision margin
```

실현 경로가 이 값을 다시 쓰면 C1-B 가 아니라 선택·실현 결합 문제를 다시 연다.

### 01c1-c — 판정

#### C1-B

```yaml
scenario: C1B_PROVENANCE_DEPENDENT_ALTERNATIVE
primary_replay:     PASS
runner_up_replay:   PASS
order_independence: PASS
model_provenance:   AVAILABLE
selection_feedback: NONE
```

runner-up 역할표의 origin 은 **실제 경로대로** 기록한다.

```
완전 모델맵 승격       → COUNTERFACTUAL_COMPLETE_MODEL_MAP
부분 모델 + 정적 폴백   → COUNTERFACTUAL_FALLBACK_ROLE_MAP
특수분기               → COUNTERFACTUAL_SPECIAL_ROLE_MAP
```

셋을 뭉뚱그려 "`_classify_roles` 파생" 이라고 부르지 않는다. 01c0 에서 실제로 그렇게
불러 canonical 의 출처를 잘못 고정했다. 8건 코호트 실측에서도 `MODEL_MAP` 과
`SPECIAL_BRANCH` 두 종류가 나왔고, bridge 계열 2건은 완비 모델이 아니면서 폴백도
아니었다.

#### C2

다음 중 하나라도 있으면 C2 다.

```
primary 를 추출한 resolver 로 재현하지 못함
runner-up selected_model 을 안정적으로 결합하지 못함
primary 실행의 mutable 상태가 필요함
실행 순서에 따라 결과가 달라짐
강제 yongsin 이 production 과 다른 보정 경로를 사용함
```

```yaml
scenario: C2_UNREALIZABLE_DECISION_ALTERNATIVE
runner_up_element:       AVAILABLE
runner_up_score:         AVAILABLE
counterfactual_role_map: UNAVAILABLE
```

이 경우 runner-up 오행·점수·margin 까지만 보존하고 P2/P3 alternate 투영은 금지한다.

---

## 5. 차단 상태

```yaml
eeaed83:
  contract: SUPERSEDED
  production_wiring: CANCELLED
  replacement: BLOCKED_BY_ROLE_REALIZATION_REPLAY

margin_census: BLOCKED
p3: BLOCKED
```

margin census 도 진행하지 않는다. runner-up 역할표를 동일 production 규칙으로 실현할 수
있는지 확인되지 않으면 margin 과 P2 축 materiality 를 교차측정할 기반이 없다.

`RoleCandidateSet` 의 비배선은 추정이 아니라 회귀로 고정했다 — production 트리
(`backend/apps`, `backend/packages`, tests·scripts 제외) 전체에서 `role_candidates` import 와
`RoleCandidateSet`/`RoleModelCandidate` 참조가 0이다.

---

## 6. 이번 커밋의 회귀 — 하드 게이트

`backend/tests/unit/test_yongsin_decision_provenance.py` (21건).

### 실현 출처

```
1  사례 A canonical == eokbu_normal 완전 역할표
2  사례 A canonical != _classify_roles(土)
3  model_complete && !special → model_map_promoted
4  부분맵 모델은 승격 불가
5  special_roles = True 는 모두 승격 게이트보다 앞에서 실행
```

### 선택 점수

```
6  confidence 는 useful score 의 실제 곱셈 인수
7  confidence 단독 순위(0.6033 < 0.7000)와 선택 결과가 반대
8  0.6033×0.25 = 0.150825 > 0.7000×0.20 = 0.140000 이 土 > 水 를 설명
   (반올림 전 Decimal 원시 정밀도로 비교한 뒤 보고값 0.1508/0.1400 과 대조)
9  margin 0.0108 · useful_sorted[:2] 로 alternate 최대 1개
```

### competing

```
10  정의 1개 · 소비처 AST 열거 = warnings.append 와 status 대입 둘뿐
11  competing 구간이 useful/useful_sorted/yongsin_el/roles/selected_model 을 재대입하지 않음
12  competing 참·거짓 코호트 양쪽에서 실현 출처가 MODEL_MAP 또는 SPECIAL_BRANCH
13  소스 위치·근접성 주장 없음 (관측 코호트 status 전건 candidate 임을 명시)
```

### 미확정 보존

```
14  _classify_roles(水) 는 static fallback 사실로만 고정
15  runner-up 水 의 final canonical assertion 없음
16  counterfactual role-map provenance 확정 없음
```

### 비배선

```
17  role_candidates production import 0
18  RoleCandidateSet·RoleModelCandidate production 참조 0
19  production 응답·score·rank 변경 0
```

**runner-up 水의 최종 역할표는 회귀 기대값으로 고정하지 않았다** — 아직 재생하지 않았다.
(01c1-b1 에서 재생했다. 7장 참조.)

---

## 7. 종료 감사 — CAL-ROLE-BORDERLINE-01c1-c

```yaml
scenario: C1B_PROVENANCE_DEPENDENT_ALTERNATIVE

primary_replay:                  PASS
runner_up_standalone_replay:     PASS
order_independence:              CONFIRMED
repeated_replay_idempotence:     CONFIRMED
input_immutability:              PASS
model_provenance:                AVAILABLE
selection_feedback:              NONE
counterfactual_role_realization: CONFIRMED
```

### 슬라이스별 커밋

```
57b020e  01c1-a   실현 경계 inert 추출 + primary 土 재현
ad8f7c2  01c1-b0  의미론 결과 / 모델 참조 분리 + top_model 상속 차단
bef4166  01c1-b1  水 단독 fresh replay
(이 커밋) 01c1-b2  5실행 순서 독립성 + 01c1-c 종료 감사
```

### 실현 경로 — 두 오행

```
土  eokbu_normal     조회 성공 · 완비   → 승격      COMPLETE_MODEL_ROLE_MAP
    土 용 / 金 희 / 木 기 / 火 구 / 水 한        confidence 0.6033

水  pattern_sangsin  조회 성공 · 부분맵 → 폴백      STATIC_FALLBACK_ROLE_MAP
    水 용 / 金 희 / 土 기 / 火 구 / 木 한        confidence 0.7
```

runner-up origin 은 `COUNTERFACTUAL_STATIC_FALLBACK_MAP` 이다.

**직접 원인을 함께 고정한다** — `STATIC_FALLBACK_FROM_INCOMPLETE_MODEL_MAP` 이지
`STATIC_FALLBACK_FROM_MODEL_LOOKUP_MISS` 가 아니다. 결과가 같아도 계약이 다르고, 01c1-b0
이전이라면 후자로 잘못 기록됐다(아래).

### b0 이 판정을 갈랐다

`top_model` 은 production 에서 `useful_candidates[0].model` 로 **index 가 고정**돼 있었다.
그대로 두고 水 를 강제하면 primary 의 `eokbu_normal` 을 물려받고, 조회 키가
`model_type == eokbu_normal AND yongsin == 水` 가 되어 실패한다. 같은
`STATIC_FALLBACK`, 같은 역할표, **전혀 다른 근거**다.

오행 기준 도출로 바꾸고 두 규칙의 동치를 고정했다 — 정렬 키가 `(role == "yongsin", score)`
내림차순이라 yongsin 역할 후보가 있으면 index 0 이 곧 확정 용신의 후보이고, 없으면 용신
오행 자체가 index 0 에서 나온다(8건 코호트 실측).

### 순서 독립성

```
E1  fresh → 土        E2  fresh → 水        E3  fresh → 土 → 水
E4  fresh → 水 → 土    E5  fresh → 水 → 水
```

세션 사이에만 재포획하고 세션 안에서는 하지 않는다 — 중간에 다시 포획하면 앞 실행의
영향이 지워져 순서 의존성을 검출할 수 없다.

```
水 5종  E2 · E3.2 · E4.1 · E5.1 · E5.2   의미론 12필드 전건 동일
土 3종  E1 · E3.1 · E4.2                 의미론 12필드 전건 동일
입력 지문  모든 호출 전후 동일 (오행 제외 canonical fingerprint)
되먹임    두 번째 호출 입력에 첫 실행 산출물 identity 부재
```

`selected_model_ref` 는 입력 모델을 그대로 돌려주는 통과 참조라 입력에서 그 id 가 보이는
것은 되먹임이 아니다 — 구조 검사에서 분리했다.

### 사후 비교는 근거가 아니다

관측된 水 역할표가 `_classify_roles(水)` 와 같다. 실현 경로가 정적 폴백이었으니 당연하고,
**반대로 이 일치를 보고 경로를 추정하면 01c0 의 오류를 반복한다.** origin 은 산출로만 정했다.

### 해제되는 차단

```yaml
counterfactual_role_map: AVAILABLE      # 실현 경로·근거와 함께 보존 가능
margin_census:           UNBLOCKED
p3_alternate_projection: UNBLOCKED_PENDING_DESIGN

eeaed83:
  contract:           SUPERSEDED        # 유지
  production_wiring:  CANCELLED         # 유지
  replacement:        READY_FOR_DESIGN  # YongsinDecisionSet 은 RealizedRoleMap 을 재사용한다
```

`eeaed83` 은 여전히 배선하지 않는다. 대체 계약을 설계할 때 폐기된 `CanonicalRoleMap` 이
아니라 production 이 실제로 쓰는 `RealizedRoleMap` 을 재사용한다.
