# 역할 실현 provenance 중간 감사 (CAL-ROLE-BORDERLINE-01c0)

```yaml
overall: ROLE_REALIZATION_PROVENANCE_INCOMPLETE
```

**완료 감사가 아니라 checkpoint 다.** runner-up 을 동일한 production 실현 경로로 재생할 수
있는지가 아직 증명되지 않았다.

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

```
1. 실현 경계를 순수 resolver 로 추출 (inert refactor — production byte 불변)
2. primary 土 를 강제 입력해 기존 canonical 5역할 완전 재현
3. 동일 입력에서 selected_yongsin_element 만 水 로 바꿔 재실행
4. 실행 순서 독립성 확인 (土→水 / 水→土 / 水 단독 결과 동일)
```

2가 실패하면 3으로 넘어가지 않는다.

### 판정 분기

```
C1-B   primary 재현 성공 + runner-up 독립 실행 성공 + 순서 독립 + 선택 feedback 없음
       → YongsinDecisionSet 계약 진행

C2     primary 전용 mutable 상태 의존 · selected_model 결합 불가 · 순서 의존
       → runner-up 오행·점수·margin 만 보존, P2/P3 alternate projection 금지
```

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
