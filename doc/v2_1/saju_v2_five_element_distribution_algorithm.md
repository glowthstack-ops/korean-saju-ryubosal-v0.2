# 사주서비스 v2 — 오행분포 계산 알고리즘 독립 명세서

> 문서 목적: v2 만세력 엔진에서 **사주 원국 내 오행분포**를 계산하기 위한 독립 구현 명세서이다.  
> 적용 범위: 원국 4주 8자, 지장간, 월지/절기, 천간·지지, 투간/통근, 원국 내 합충형파해, 병존/간여지동, 공망, 조후 정보.  
> 제외 범위: 대운·세운·월운에 의한 변화는 이 문서의 오행분포 계산에 포함하지 않는다. 대운/세운은 별도 `luck_effect` 레이어에서 계산한다.

---

## 1. 핵심 원칙

오행분포는 하나의 숫자로 단정하면 안 된다. v2에서는 오행분포를 최소 4개 레이어로 분리한다.

```text
1. raw_visible_distribution
   - 천간 4개 + 지지 4개의 표면 오행 분포
   - 가장 단순한 원국 오행 구성

2. hidden_base_distribution
   - 지장간 본기/중기/여기를 반영한 기본 분포
   - 지지 내부의 실제 구성 반영

3. effective_force_distribution
   - 월령, 투간, 통근, 지지 위치, 원국 내 합충형파해 등을 반영한 실세력 분포
   - 신강약, 용신 후보, 과다/부족 판단에 사용하는 핵심 분포

4. climate_context
   - 조후, 한난조습, 건조/습윤, 온도/수분/계절성
   - 오행 점수 자체를 직접 덮어쓰기보다 별도 축으로 제공
```

중요:

```text
오행분포 = 원국 내 힘의 분포
조후 = 원국의 기후/환경 조건
신강약 = 일간 중심 세력 판정
용신 = 신강약 + 구조 + 조후 + 검증을 통합한 전략 판단
```

따라서 `목이 부족하다 = 목이 용신이다`로 연결하면 안 된다.

---

## 2. 최상위 출력 구조

```yaml
five_element_analysis:
  scope: natal_chart_only

  raw_visible_distribution:
    wood:
    fire:
    earth:
    metal:
    water:
    percent:

  hidden_base_distribution:
    wood:
    fire:
    earth:
    metal:
    water:
    percent:

  effective_force_distribution:
    wood:
    fire:
    earth:
    metal:
    water:
    percent:

  climate_context:
    temperature_axis:
    moisture_axis:
    dryness_axis:
    coldness_axis:
    season:
    johu_notes:

  diagnostics:
    strongest_element:
    weakest_element:
    excessive_elements:
    deficient_elements:
    isolated_elements:
    dominant_flow_candidate:
    calculation_warnings:

  calculation_trace:
    heavenly_stems:
    earthly_branches:
    hidden_stems:
    month_command_modifier:
    position_modifier:
    rooting_modifier:
    exposing_modifier:
    relation_modifier:
    void_modifier:
    coexistence_modifier:
    final_normalization:
```

---

## 3. 입력 데이터 요구사항

오행분포 계산 전에 `manse-core`는 아래 정보를 제공해야 한다.

```yaml
chart:
  pillars:
    year:
      stem:
      branch:
    month:
      stem:
      branch:
    day:
      stem:
      branch:
    hour:
      stem:
      branch:

  hidden_stems:
    year_branch:
      residual:
      middle:
      main:
    month_branch:
    day_branch:
    hour_branch:

  solar_term_basis:
    previous_term:
    next_term:
    days_since_term:
    days_until_next_term:
    month_branch:
    seasonal_phase:

  relations:
    stem_combinations:
    branch_six_combinations:
    three_harmony:
    directional_combinations:
    clashes:
    punishments:
    harms:
    breaks:
    self_punishments:

  void:
    day_pillar_void_branches:
    affected_positions:

  structural_amplifiers:
    stem_duplication:
    branch_duplication:
    gan_yeo_ji_dong:
```

---

## 4. 오행 매핑

### 4.1 천간 오행

```yaml
stems:
  갑: 목
  을: 목
  병: 화
  정: 화
  무: 토
  기: 토
  경: 금
  신: 금
  임: 수
  계: 수
```

### 4.2 지지 표면 오행

```yaml
branches_surface:
  인: 목
  묘: 목
  진: 토
  사: 화
  오: 화
  미: 토
  신: 금
  유: 금
  술: 토
  해: 수
  자: 수
  축: 토
```

### 4.3 지장간

구현 시 반드시 한글/한자 enum을 모두 지원한다.

```yaml
hidden_stems:
  자:
    main: 계

  축:
    residual: 계
    middle: 신
    main: 기

  인:
    residual: 무
    middle: 병
    main: 갑

  묘:
    main: 을

  진:
    residual: 을
    middle: 계
    main: 무

  사:
    residual: 무
    middle: 경
    main: 병

  오:
    middle: 기
    main: 정

  미:
    residual: 정
    middle: 을
    main: 기

  신:
    residual: 무
    middle: 임
    main: 경

  유:
    main: 신

  술:
    residual: 신
    middle: 정
    main: 무

  해:
    middle: 갑
    main: 임
```

주의:

```text
지장간 구성은 유파에 따라 일부 표현 차이가 있을 수 있으므로,
v2에서는 default table을 명시하고 config로 교체 가능하게 한다.
```

---

## 5. 레이어 1 — raw_visible_distribution

### 5.1 목적

가장 단순한 원국 구성 확인용이다.

```text
천간 4개 + 지지 표면 오행 4개를 동일 가중치 또는 위치 가중치로 계산한다.
```

### 5.2 기본 가중치

MVP에서는 단순 가중치로 시작한다.

```yaml
raw_visible_weight:
  each_heavenly_stem: 1.0
  each_earthly_branch_surface: 1.0
```

고도화 옵션:

```yaml
raw_visible_position_weight:
  year_stem: 0.9
  month_stem: 1.1
  day_stem: 1.0
  hour_stem: 0.95

  year_branch: 0.9
  month_branch: 1.3
  day_branch: 1.15
  hour_branch: 1.0
```

권장:

```text
사용자 표시용 raw 분포는 단순 가중치,
판정용 effective 분포는 위치 가중치를 사용한다.
```

---

## 6. 레이어 2 — hidden_base_distribution

### 6.1 목적

지지 내부의 지장간을 반영한 기본 오행분포다.  
v1의 “지장간 반영 오행분포”에 해당하지만, v2에서는 보정 전/후를 분리한다.

### 6.2 지장간 본기/중기/여기 가중치

기본값:

```yaml
hidden_stem_base_weight:
  main: 0.70
  middle: 0.20
  residual: 0.10
```

단일 지장간만 있는 지지는 1.00으로 처리한다.

```yaml
single_hidden_stem_branch:
  자: 계 1.00
  묘: 을 1.00
  유: 신 1.00
```

오지 `오`처럼 본기/중기만 있는 경우:

```yaml
two_hidden_stem_branch:
  main: 0.75
  middle: 0.25
```

주의:

```text
본기/중기/여기 가중치는 고정값으로 시작하되,
절기 내 일수에 따라 사령 지장간 가중치를 변경하는 고도화 옵션을 별도 제공한다.
```

---

## 7. 레이어 3 — effective_force_distribution

### 7.1 목적

신강약, 용신 후보, 과다/부족 판단에 사용하는 핵심 분포다.  
다음 요소를 반영한다.

```text
1. 천간 위치
2. 지지 위치
3. 지장간 본기/중기/여기
4. 월지/월령 계절 보정
5. 투간 보정
6. 통근 보정
7. 원국 내 합충형파해 보정
8. 공망 보정
9. 병존/간여지동 보정
10. 고립/과다 판단
```

---

## 8. 기본 파워 계산

### 8.1 천간 위치 가중치

```yaml
heavenly_stem_position_weight:
  year: 8
  month: 12
  day: 0
  hour: 10
```

일간은 기준점이므로 오행분포 판정에서 두 가지 방식으로 처리한다.

```text
표시용 오행분포:
  일간 포함 가능

신강약/용신 판정용 오행분포:
  일간은 기준점이므로 별도 보관하고,
  ally/pressure 계산에서는 일간 자체를 과대 반영하지 않도록 조정
```

권장 출력:

```yaml
day_stem_policy:
  display_distribution: included
  force_distribution: separated_as_reference
```

### 8.2 지지 위치 가중치

```yaml
earthly_branch_position_weight:
  year: 12
  month: 28
  day: 24
  hour: 16
```

월지와 일지를 높게 보는 이유:

```text
월지 = 계절권, 사회 환경, 월령
일지 = 일간의 직접 기반, 배우자궁, 체감 기반
```

### 8.3 지장간 세부 가중치

```yaml
hidden_stem_effective_weight:
  main: 1.00
  middle: 0.60
  residual: 0.35
```

계산식:

```python
hidden_power = branch_position_weight * hidden_stem_effective_weight
```

---

## 9. 월지/월령 보정

### 9.1 원칙

월지는 단순히 월지 오행 하나를 크게 더하는 항목이 아니다.  
월지는 전체 원국의 계절적 강약 계수로 작동한다.

```text
월지 보정은:
1. 월지 자체의 지장간 파워
2. 계절상 왕상휴수사
3. 조후 상태
4. 절기 내 사령 지장간
을 분리해서 처리한다.
```

### 9.2 계절 계수

```yaml
season_coefficient:
  wang: 1.30
  xiang: 1.15
  xiu: 1.00
  qiu: 0.80
  si: 0.65
```

각 오행이 월령에서 어떤 상태인지 판정해 각 오행 파워에 곱한다.

예:

```python
adjusted_element_power[element] = raw_element_power[element] * season_coefficient[element_state_in_month]
```

### 9.3 월지 본기 강조

월지의 본기는 원국 전체 분위기를 잡기 때문에 추가 보정한다.

```yaml
month_branch_main_qi_bonus:
  main_hidden_stem_element: +0.12
```

구현:

```python
if hidden_stem_is_month_branch_main_qi:
    power *= 1.12
```

### 9.4 절기 내 사령 지장간 옵션

고도화 옵션으로 `days_since_term`을 사용해 사령 지장간을 반영한다.

```yaml
seasonal_hidden_stem_command:
  enabled: false_by_default
  use_days_since_solar_term: true
```

사용 예:

```text
해월 안에서도 초입/중기/말기에 따라 무/갑/임의 체감 비중이 달라질 수 있다.
MVP에서는 고정 지장간 비율을 사용하고,
고도화 단계에서 사령일수 테이블을 추가한다.
```

---

## 10. 투간 보정

### 10.1 정의

지장간의 오행 또는 십성이 천간에 드러난 경우, 해당 기운은 현실화/표면화된 것으로 본다.

### 10.2 계산 정책

```yaml
exposure_modifier:
  same_hidden_stem_exposed_in_heavenly_stem: +0.15
  same_element_exposed_in_heavenly_stem: +0.08
  exposed_in_month_stem_extra: +0.05
```

예:

```text
월지 해의 정기 임수가 천간 임으로 투간하면 수 기운의 현실 작동성을 높인다.
같은 수 오행인 계수가 투간한 경우는 약한 보정만 적용한다.
```

주의:

```text
투간 보정은 오행의 양을 새로 만드는 것이 아니라,
이미 존재하는 지장간 기운의 작동성을 높이는 보정이다.
```

---

## 11. 통근 보정

### 11.1 정의

천간이 지지 지장간에 뿌리를 두고 있는지 확인한다.

### 11.2 적용 대상

통근 보정은 두 곳에 사용한다.

```text
1. 오행분포 effective_force_distribution
2. 신강약 root_score
```

단, 두 계산은 같은 값이 아니다.

```text
오행분포의 통근 보정:
  특정 천간 오행의 실세력 증가

신강약의 통근 보정:
  일간이 버틸 수 있는 기반 증가
```

### 11.3 계산 정책

```yaml
rooting_modifier:
  heavenly_stem_has_same_stem_root:
    strong_root: +0.18
    medium_root: +0.12
    weak_root: +0.06

  heavenly_stem_has_same_element_root:
    strong_root: +0.12
    medium_root: +0.08
    weak_root: +0.04
```

강도 판정:

```yaml
root_strength_by_position:
  month_branch: strong
  day_branch: strong
  hour_branch: medium
  year_branch: weak
```

지장간 위치 보정:

```yaml
root_strength_by_hidden_stem:
  main: strong
  middle: medium
  residual: weak
```

---

## 12. 원국 내 관계 보정

### 12.1 원칙

합충형파해는 원국 내 오행의 작동성에 영향을 준다.  
다만 오행 자체를 완전히 삭제하거나 새로 생성하는 방식은 위험하다.

따라서 v2에서는 관계 보정을 세 단계로 둔다.

```text
1. activation: 기운이 자극됨
2. weakening: 안정성이 약화됨
3. transformation: 조건 충족 시 오행 흐름이 변환됨
```

---

### 12.2 육합

```yaml
six_combination:
  no_transformation:
    both_elements_activation: +0.05
    actionability_lock: -0.05
  transformation_possible:
    original_elements_loss: -0.20
    transformed_element_gain: +0.25
  transformation_confirmed:
    original_elements_loss: -0.40
    transformed_element_gain: +0.45
```

주의:

```text
육합이 있다고 무조건 합화하지 않는다.
합화 조건은 월령, 뿌리, 방해 요소, 천간 투출을 함께 확인한다.
```

---

### 12.3 삼합/방합

```yaml
three_harmony:
  complete:
    target_element_gain: +0.35
    member_element_activation: +0.10
  half:
    target_element_gain: +0.18
  directional_combo:
    target_element_gain: +0.30
```

주의:

```text
삼합 완성 여부와 반합은 구분한다.
월지가 포함된 삼합은 가중치를 높인다.
```

추가 보정:

```yaml
combo_contains_month_branch_bonus: +0.07
combo_contains_day_branch_bonus: +0.05
```

---

### 12.4 충

```yaml
branch_clash:
  both_activation: +0.08
  stability_loss: -0.12
  weak_root_damage: -0.25
  strong_root_damage: -0.10
```

충은 단순히 해당 오행을 제거하지 않는다.

```text
충 = 자극 + 변동 + 불안정
```

따라서 오행분포에는 다음을 남긴다.

```yaml
clash_effect:
  activated_elements:
  damaged_roots:
  volatility_score:
```

---

### 12.5 형·파·해·자형

```yaml
punishment:
  activation: +0.05
  stability_loss: -0.10

self_punishment:
  repeated_element_amplification: +0.06
  inner_friction: +0.12

break:
  stability_loss: -0.08
  relation_damage: -0.05

harm:
  hidden_instability: -0.08
  indirect_damage: -0.05
```

자형의 경우:

```text
같은 지지가 반복되거나 특정 자형 구조가 있으면 해당 오행이 강화되면서도 내부 마찰이 증가한다.
따라서 오행량은 약간 증가하지만 안정도는 감소한다.
```

---

## 13. 공망 보정

### 13.1 원칙

공망은 원국 오행을 완전히 삭제하지 않는다.  
원국 내에서는 “배경적 약화/비실체성”으로 표시하고, 대운·세운에서 자극될 때 사건화한다.

### 13.2 계산 정책

```yaml
void_modifier:
  affected_branch_base_power_multiplier: 0.85
  hidden_stem_power_multiplier: 0.85
  display_as_void: true
  do_not_remove_element: true
```

주의:

```text
공망 지지가 월지 또는 일지인 경우에는 과도한 차감 금지.
원국의 핵심 구조를 삭제하면 오판 가능.
```

권장:

```text
오행분포에는 0.85 정도의 약한 차감만 적용하고,
별도 gongmang_context에 활성 조건을 기록한다.
```

---

## 14. 병존/간여지동 보정

### 14.1 병존

```yaml
coexistence_modifier:
  same_heavenly_stem_adjacent:
    element_gain: +0.06
    expression_intensity_gain: +0.10

  same_branch_adjacent:
    element_gain: +0.10
    branch_theme_amplification: +0.15
    self_friction_if_applicable: +0.08
```

예:

```text
해해 병존 → 수 오행, 정재 구조, 월지·일지 관련 궁성 증폭
기기 병존 → 토 오행, 비견/일간 자기성 증폭
```

### 14.2 간여지동

```yaml
gan_yeo_ji_dong_modifier:
  same_element_stem_branch:
    element_purity_gain: +0.08
    pillar_focus_gain: +0.12
```

주의:

```text
간여지동은 용신을 직접 바꾸는 요소가 아니라,
해당 주의 오행 순수성과 사건화 강도를 높이는 보정이다.
```

---

## 15. 조후와 오행분포의 관계

### 15.1 핵심 정책

조후는 오행분포를 직접 덮어쓰지 않는다.

```text
좋은 방식:
  오행분포는 오행의 세력
  조후는 기후 조건
  용신 후보 산출에서 둘을 함께 참조

나쁜 방식:
  겨울이면 무조건 화 점수 대폭 증가
  여름이면 무조건 수 점수 대폭 증가
```

### 15.2 climate_context 출력

```yaml
climate_context:
  season_branch: 해
  season_group: winter
  temperature:
    cold: high
    heat: low
  moisture:
    wet: high
    dry: low
  dryness:
    score: 0.20
  coldness:
    score: 0.82
  johu_candidates:
    - fire
    - earth_if_too_wet
  notes:
    - 해월로 한습 경향
    - 수기 강세가 체감 환경을 차갑고 습하게 만들 수 있음
```

### 15.3 조후가 오행분포에 주는 제한적 영향

조후는 effective_force_distribution에 직접 큰 가산을 하지 않는다.  
다만 특정 오행의 “작동성”에는 약한 보정을 줄 수 있다.

```yaml
johu_operability_modifier:
  excessive_cold_reduces_fire_operability: -0.05
  excessive_heat_reduces_water_operability: -0.05
  excessive_damp_reduces_earth_stability: -0.04
  excessive_dry_reduces_wood_growth: -0.04
```

권장:

```text
MVP에서는 조후 보정을 오행분포에 반영하지 말고 climate_context로만 출력한다.
v2.1 이후 operability_modifier를 실험 적용한다.
```

---

## 16. 부족/과다/고립 판정

### 16.1 부족 오행

```yaml
deficient_threshold:
  percent_below: 8.0
  absolute_power_below: configurable
```

단, 부족 오행이 무조건 용신은 아니다.

```text
부족 오행은 보완 후보일 뿐이다.
일간 기준 십성 역할, 신강약, 조후, 구조를 함께 봐야 한다.
```

### 16.2 과다 오행

```yaml
excessive_threshold:
  percent_above: 35.0
  dominant_threshold: 45.0
```

과다 오행은 아래를 같이 확인한다.

```text
1. 월령을 얻었는가
2. 삼합/방합으로 강화되었는가
3. 병존으로 반복되는가
4. 천간에 투간했는가
5. 통근했는가
6. 일간에 유리한가 불리한가
```

### 16.3 고립 오행

고립은 단순히 비율이 낮은 것과 다르다.

```yaml
isolated_element_conditions:
  - percent_below: 8.0
  - no_visible_stem: true
  - no_strong_root: true
  - surrounded_by_controlling_element: true
  - damaged_by_clash_or_harm: true
```

고립 출력:

```yaml
isolated_elements:
  - element: 목
    isolation_score: 0.72
    risk_level: medium
    reason:
      - 천간 투출 없음
      - 지장간에만 약하게 존재
      - 금/토 세력에 눌림
```

---

## 17. 최종 정규화

각 레이어는 raw score를 계산한 후 백분율로 변환한다.

```python
percent[element] = element_score[element] / sum(element_score.values()) * 100
```

주의:

```text
차감 보정으로 특정 오행 점수가 음수가 되면 0으로 clamp한다.
모든 오행 합이 0이 되는 경우는 오류로 처리한다.
```

---

## 18. 출력 예시

```json
{
  "five_element_analysis": {
    "scope": "natal_chart_only",
    "raw_visible_distribution": {
      "scores": {
        "wood": 0,
        "fire": 2,
        "earth": 2,
        "metal": 2,
        "water": 2
      },
      "percent": {
        "wood": 0.0,
        "fire": 25.0,
        "earth": 25.0,
        "metal": 25.0,
        "water": 25.0
      }
    },
    "hidden_base_distribution": {
      "scores": {
        "wood": 0.4,
        "fire": 1.2,
        "earth": 2.2,
        "metal": 1.7,
        "water": 2.5
      },
      "percent": {
        "wood": 5.0,
        "fire": 15.0,
        "earth": 27.5,
        "metal": 21.25,
        "water": 31.25
      }
    },
    "effective_force_distribution": {
      "scores": {
        "wood": 4.1,
        "fire": 19.7,
        "earth": 19.8,
        "metal": 16.2,
        "water": 40.2
      },
      "percent": {
        "wood": 4.1,
        "fire": 19.7,
        "earth": 19.8,
        "metal": 16.2,
        "water": 40.2
      },
      "strongest_element": "water",
      "weakest_element": "wood"
    },
    "climate_context": {
      "season_group": "winter",
      "coldness": 0.82,
      "moisture": 0.78,
      "johu_candidates": ["fire", "earth_if_damp_excessive"]
    },
    "diagnostics": {
      "excessive_elements": ["water"],
      "deficient_elements": ["wood"],
      "isolated_elements": ["wood"],
      "calculation_warnings": [
        "부족 오행은 자동 용신이 아님",
        "조후는 오행분포와 별도 축으로 판단"
      ]
    }
  }
}
```

---

## 19. 구현 의사코드

```python
def calculate_five_element_analysis(chart: NatalChart) -> FiveElementAnalysis:
    raw = calculate_raw_visible_distribution(chart)

    hidden_base = calculate_hidden_base_distribution(
        branches=chart.branches,
        hidden_stems=chart.hidden_stems
    )

    base_power = calculate_position_weighted_power(
        stems=chart.stems,
        branches=chart.branches,
        hidden_stems=chart.hidden_stems
    )

    seasonal_power = apply_month_command_modifier(
        element_power=base_power,
        month_branch=chart.month.branch,
        solar_term_basis=chart.solar_term_basis
    )

    exposed_power = apply_exposure_modifier(
        element_power=seasonal_power,
        stems=chart.stems,
        hidden_stems=chart.hidden_stems
    )

    rooted_power = apply_rooting_modifier(
        element_power=exposed_power,
        stems=chart.stems,
        branches=chart.branches,
        hidden_stems=chart.hidden_stems
    )

    relation_power, relation_trace = apply_natal_relation_modifier(
        element_power=rooted_power,
        relations=chart.relations
    )

    void_power, void_trace = apply_void_modifier(
        element_power=relation_power,
        void=chart.void
    )

    amplified_power, amplifier_trace = apply_structural_amplifier_modifier(
        element_power=void_power,
        amplifiers=chart.structural_amplifiers
    )

    effective = normalize_to_percent(amplified_power)

    climate_context = calculate_climate_context(
        chart=chart,
        effective_distribution=effective
    )

    diagnostics = diagnose_distribution(
        effective_distribution=effective,
        climate_context=climate_context,
        trace=[relation_trace, void_trace, amplifier_trace]
    )

    return FiveElementAnalysis(
        scope="natal_chart_only",
        raw_visible_distribution=raw,
        hidden_base_distribution=hidden_base,
        effective_force_distribution=effective,
        climate_context=climate_context,
        diagnostics=diagnostics,
    )
```

---

## 20. 테스트 케이스

### 20.1 기본 테스트

```text
1. 천간/지지 표면 오행만 계산되는지
2. 지장간 본기/중기/여기가 반영되는지
3. 월지 가중치가 과도하게 중복 반영되지 않는지
4. 조후가 오행분포를 직접 왜곡하지 않는지
5. 일간 포함/분리 정책이 구분되는지
```

### 20.2 엣지 테스트

```text
1. 목이 0%에 가까운 명식
2. 특정 오행이 45% 이상인 명식
3. 월지가 공망인 명식
4. 일지가 공망인 명식
5. 삼합이 완성된 명식
6. 육합은 있으나 합화 조건이 부족한 명식
7. 충으로 유일한 뿌리가 손상된 명식
8. 지지병존이 있는 명식
9. 간여지동이 있는 명식
10. 조후상 매우 춥지만 화 오행도 약한 명식
```

---

## 21. 구현 금지 사항

```text
1. 부족한 오행을 자동으로 용신으로 처리하지 말 것.
2. 월지만 보고 특정 오행을 무조건 크게 가산하지 말 것.
3. 육합을 무조건 합화로 처리하지 말 것.
4. 공망 오행을 0으로 삭제하지 말 것.
5. 조후 보정을 오행분포에 직접 대량 반영하지 말 것.
6. 대운/세운을 원국 오행분포에 섞지 말 것.
7. 통근과 득지를 같은 개념으로 처리하지 말 것.
8. 오행분포 하나만으로 신강약을 확정하지 말 것.
9. 오행분포 하나만으로 용신을 확정하지 말 것.
```

---

## 22. Codex 구현 작업 단위

```text
1. FiveElement enum 정의
2. Stem/Branch → FiveElement 매핑 구현
3. HiddenStem table 구현
4. RawVisibleDistribution 계산
5. HiddenBaseDistribution 계산
6. PositionWeightedPower 계산
7. MonthCommandModifier 구현
8. ExposureModifier 구현
9. RootingModifier 구현
10. NatalRelationModifier 구현
11. VoidModifier 구현
12. StructuralAmplifierModifier 구현
13. ClimateContext 계산
14. Diagnostics 계산
15. JSON schema 작성
16. Unit test 작성
```

---

## 23. 완료 기준

```text
1. 원국만으로 오행분포가 계산된다.
2. raw/base/effective/context 레이어가 분리되어 출력된다.
3. 지장간/월지/천간지지/조후 관련 보정이 trace로 남는다.
4. 공망/합충형파해/병존/간여지동이 원국 내 보정으로 반영된다.
5. 조후는 별도 climate_context로 출력된다.
6. 최종 effective_force_distribution의 합은 100%다.
7. 부족/과다/고립 오행이 진단된다.
8. 오행분포 결과만으로 용신을 확정하지 않는다.

---

# v2.1 보완 — 토 지지 contextual flow

## 1. 진술축미를 단순 토로만 처리하지 않는다

```yaml
earth_branch_context_policy:
  진:
    default: wet_earth
    possible_flow: water_wood_storage
  술:
    default: dry_earth
    possible_flow: fire_metal_storage
  축:
    default: cold_wet_earth
    possible_flow: water_metal_storage
  미:
    default: hot_dry_earth
    possible_flow: fire_wood_storage
```

## 2. 축토의 수 작동성

```yaml
chou_water_flow_boost:
  conditions:
    - cold_season_or_night_context
    - gui_water_present_or_relevant
    - hidden_flow_earth_to_metal_to_water
  effects:
    water_operability_gain: +0.10
    earth_surface_reliability_down: -0.05
    mark_as_contextual_earth: true
```

정책:

```text
축토를 수로 완전 변환하지 않는다.
표면 오행 earth와 contextual_flow water를 병렬 보관한다.
```
