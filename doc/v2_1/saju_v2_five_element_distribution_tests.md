# 사주서비스 v2 — 오행분포 테스트 및 엣지케이스 명세서

> 문서 목적: 오행분포 계산 알고리즘의 품질을 검증하기 위한 테스트 케이스, 엣지케이스, 회귀 테스트 기준을 정의한다.  
> 전제: 오행분포는 원국 내 계산으로 한정하고, 대운·세운·월운은 포함하지 않는다.

---

## 1. 테스트 기본 원칙

오행분포 테스트는 단순 퍼센트 일치만 확인하지 않는다.

검증해야 할 것:

```text
1. raw/base/effective/context 레이어가 분리되는가
2. 지장간이 본기/중기/여기로 반영되는가
3. 월지 보정이 과도하게 중복되지 않는가
4. 투간/통근이 작동성 보정으로 반영되는가
5. 합충형파해가 삭제가 아니라 활성/손상/변환으로 처리되는가
6. 공망이 0 처리되지 않는가
7. 조후가 오행분포와 분리되어 climate_context로 제공되는가
8. 부족 오행을 용신으로 자동 처리하지 않는가
```

---

## 2. 필수 단위 테스트

### 2.1 천간/지지 매핑 테스트

```text
입력: 10천간, 12지지
기대:
- 각 천간의 오행이 정확히 매핑된다.
- 각 지지 표면 오행이 정확히 매핑된다.
```

### 2.2 지장간 테이블 테스트

```text
입력: 12지지
기대:
- 본기/중기/여기가 누락 없이 반환된다.
- 단일 지장간 지지는 1.0으로 정규화된다.
- 본기/중기/여기 가중치 합이 1.0이다.
```

### 2.3 raw_visible_distribution 테스트

```text
입력: 천간 4개, 지지 4개
기대:
- 천간/지지 표면 오행만 반영된다.
- 지장간은 반영되지 않는다.
- 총합은 100%로 정규화된다.
```

### 2.4 hidden_base_distribution 테스트

```text
입력: 지지 4개
기대:
- 지장간 본기/중기/여기가 반영된다.
- 천간 위치 보정은 반영하지 않는다.
- 월령 보정은 반영하지 않는다.
```

### 2.5 effective_force_distribution 테스트

```text
입력: 원국 전체
기대:
- 천간 위치 가중치가 반영된다.
- 지지 위치 가중치가 반영된다.
- 월지/월령 보정이 반영된다.
- 투간/통근 보정이 trace에 남는다.
- 최종 합은 100%다.
```

---

## 3. 엣지케이스 테스트

### 3.1 특정 오행 0% 또는 극소 케이스

목표:

```text
부족 오행 진단이 작동하는지 확인한다.
부족 오행을 자동으로 용신 처리하지 않는지 확인한다.
```

기대 출력:

```yaml
deficient_elements:
  - element: wood
    reason:
      - effective_percent_below_threshold
    auto_yongsin: false
```

---

### 3.2 특정 오행 과다 케이스

목표:

```text
과다 오행과 전왕/종격 후보를 구분한다.
```

기대 출력:

```yaml
excessive_elements:
  - water

dominant_flow_candidate:
  detected: true | false
  confidence:
```

주의:

```text
과다하다고 무조건 제어 대상으로 처리하지 않는다.
전왕/종격 가능성은 yongsin special check로 넘긴다.
```

---

### 3.3 월지 공망 케이스

목표:

```text
월지가 공망이어도 오행을 삭제하지 않는지 확인한다.
```

기대:

```yaml
void_modifier:
  applied: true
  multiplier: 0.85
  removed: false
```

---

### 3.4 일지 공망 케이스

목표:

```text
일지 공망이 원국 기반과 궁성 해석에 표시되는지 확인한다.
```

기대:

```yaml
gongmang_context:
  affected_position: day
  branch_power_removed: false
  activation_required: true
```

---

### 3.5 육합 있으나 합화 미성립

목표:

```text
육합을 무조건 합화로 처리하지 않는지 확인한다.
```

기대:

```yaml
six_combination:
  exists: true
  transformation_confirmed: false
  transformed_element_gain: 0
  actionability_lock_applied: true
```

---

### 3.6 합화 성립 후보

목표:

```text
월령, 뿌리, 방해 요소가 충족될 때만 합화 후보로 처리하는지 확인한다.
```

기대:

```yaml
transformation:
  possible: true
  confidence:
  original_elements_loss:
  transformed_element_gain:
```

---

### 3.7 삼합 완성 케이스

목표:

```text
삼합 완성이 target element를 강화하는지 확인한다.
```

기대:

```yaml
three_harmony:
  complete: true
  target_element_gain_applied: true
```

---

### 3.8 반합 케이스

목표:

```text
반합과 삼합 완성을 구분한다.
```

기대:

```yaml
three_harmony:
  complete: false
  half: true
  target_element_gain_lower_than_complete: true
```

---

### 3.9 충으로 유일한 뿌리 손상

목표:

```text
오행 자체를 삭제하지 않고 root damage로 반영하는지 확인한다.
```

기대:

```yaml
clash_effect:
  both_activation: true
  damaged_roots:
    - element:
      position:
      damage_level:
```

---

### 3.10 해해 병존 케이스

목표:

```text
지지병존이 해당 오행 증폭과 내부 마찰을 동시에 남기는지 확인한다.
```

기대:

```yaml
coexistence:
  same_branch_adjacent: true
  element_gain_applied: true
  inner_friction_recorded: true
```

---

### 3.11 천간 병존 케이스

목표:

```text
동일 천간 반복이 표면 작동성을 강화하는지 확인한다.
```

기대:

```yaml
stem_duplication:
  detected: true
  element_gain_applied: true
  expression_intensity_gain: true
```

---

### 3.12 간여지동 케이스

목표:

```text
간여지동이 용신을 직접 바꾸지 않고 구조 증폭으로만 처리되는지 확인한다.
```

기대:

```yaml
gan_yeo_ji_dong:
  detected: true
  element_purity_gain: true
  direct_yongsin_change: false
```

---

### 3.13 매우 추운 조후 + 화 부족 케이스

목표:

```text
조후 후보가 climate_context에 표시되지만 오행분포를 직접 왜곡하지 않는지 확인한다.
```

기대:

```yaml
climate_context:
  coldness_score: high
  johu_candidates:
    - fire

effective_force_distribution:
  fire_percent:
    not_artificially_inflated: true
```

---

### 3.14 매우 더운 조후 + 수 부족 케이스

기대:

```yaml
climate_context:
  heat_score: high
  johu_candidates:
    - water

effective_force_distribution:
  water_percent:
    not_artificially_inflated: true
```

---

### 3.15 토월 케이스

목표:

```text
진술축미를 단순히 같은 토로만 처리하지 않고, 습토/조토/계절 전환성을 trace에 남기는지 확인한다.
```

기대:

```yaml
earth_month_context:
  branch: 축 | 진 | 미 | 술
  damp_or_dry:
  seasonal_transition:
  note:
```

---

## 4. 회귀 테스트 fixture

### 4.1 사용자 기준 예시

```yaml
fixture_name: 1980-11-22_09-08_Seoul_male
input:
  date: 1980-11-22
  time: 09:08
  place: Seoul
  longitude: 126.978
  timezone: Asia/Seoul
expected_core:
  year_pillar: 경신
  month_pillar: 정해
  day_pillar: 기해
  hour_pillar: 기사
expected_distribution_properties:
  strongest_element_candidate: water
  weakest_element_candidate: wood
  has_hidden_wood: true
  has_water_duplication: true
  month_branch_element: water
  day_branch_element: water
notes:
  - 수가 강하게 나오는 구조
  - 목은 지장간에 있으나 표면 투출이 약함
  - 목 부족이 자동 용신을 의미하지 않음
```

정확한 퍼센트는 알고리즘 확정 후 lock한다.

---

## 5. Snapshot 테스트 기준

초기에는 퍼센트 소수점까지 lock하지 않는다.

단계:

```text
1단계:
  strongest/weakest, excessive/deficient, trace 존재 여부를 검증

2단계:
  알고리즘 안정화 후 소수점 1자리 기준 snapshot 고정

3단계:
  v2.1 이후 사령 지장간/조후 operability 추가 시 snapshot 버전 분리
```

---

## 6. 테스트 데이터 작성 형식

```json
{
  "name": "case_name",
  "input_chart": {
    "year": "庚申",
    "month": "丁亥",
    "day": "己亥",
    "hour": "己巳"
  },
  "expected": {
    "raw_visible_distribution": {
      "strongest_any_of": ["fire", "earth", "metal", "water"]
    },
    "hidden_base_distribution": {
      "contains_hidden_wood": true
    },
    "effective_force_distribution": {
      "strongest": "water",
      "weakest": "wood"
    },
    "diagnostics": {
      "deficient_elements_contains": ["wood"],
      "excessive_elements_contains": ["water"]
    },
    "policies": {
      "deficient_element_auto_yongsin": false,
      "gongmang_removed": false,
      "johu_direct_inflation": false
    }
  }
}
```

---

## 7. 품질 게이트

PR 머지 전 체크리스트:

```text
- [ ] raw/base/effective/context 레이어가 모두 존재한다.
- [ ] 지장간 가중치 합이 1.0이다.
- [ ] effective_force_distribution 합이 100%다.
- [ ] 조후가 climate_context로 분리된다.
- [ ] 공망 지지가 0 처리되지 않는다.
- [ ] 육합이 자동 합화되지 않는다.
- [ ] 부족 오행이 자동 용신 처리되지 않는다.
- [ ] 대운/세운이 원국 오행분포에 섞이지 않는다.
- [ ] calculation_trace가 출력된다.
- [ ] fixture 기반 회귀 테스트가 통과한다.
```

---

## 8. 구현 금지 사항 테스트

아래는 반드시 실패 테스트로 작성한다.

```text
1. 공망 오행을 0으로 삭제하면 실패
2. 겨울월이라는 이유로 화 오행분포를 강제로 크게 올리면 실패
3. 육합만 보고 합화로 변환하면 실패
4. 부족 오행을 용신으로 자동 설정하면 실패
5. 통근이 있다는 이유만으로 신강 판정하면 실패
6. 대운/세운이 원국 effective_force_distribution에 포함되면 실패
```

---

## 9. Codex 테스트 구현 순서

```text
1. mapping unit test
2. hidden stem unit test
3. raw distribution test
4. hidden base distribution test
5. effective force distribution smoke test
6. relation modifier test
7. void modifier test
8. climate context separation test
9. policy failure test
10. regression fixture test
```
