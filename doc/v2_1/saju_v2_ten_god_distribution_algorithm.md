# 사주서비스 v2 — 십성분포 계산 알고리즘 독립 명세서

> 문서 목적: v2 만세력 엔진에서 **사주 원국 내 십성분포**를 계산하기 위한 독립 구현 명세서이다.  
> 적용 범위: 원국 4주 8자, 일간 기준 십성 산출, 천간·지지 대표 십성, 지장간 십성, 월지/월령, 투간, 통근, 합충형파해, 공망, 병존/간여지동, 조후 컨텍스트.  
> 제외 범위: 대운·세운·월운에 의한 십성 변화는 이 문서에 포함하지 않는다. 운의 십성 변화는 별도 `luck_ten_god_effect` 레이어에서 계산한다.

---

## 1. 핵심 원칙

십성분포는 오행분포와 유사하지만, 다음 차이가 있다.

```text
오행분포:
  목·화·토·금·수의 세력 분포

십성분포:
  일간 기준으로 각 기운이 어떤 역할을 하는지의 분포
```

따라서 십성분포는 반드시 **일간 기준 관계**와 **음양 정/편 구분**을 포함해야 한다.

v2에서는 십성분포를 최소 4개 레이어로 분리한다.

```text
1. raw_visible_ten_god_distribution
   - 천간 노출 십성 + 지지 대표 십성 기준의 단순 분포
   - 사용자가 보는 표면 역할

2. hidden_base_ten_god_distribution
   - 지장간 본기/중기/여기를 반영한 잠재 십성 분포
   - 원국 내부에 숨어 있는 역할

3. effective_ten_god_distribution
   - 월지, 위치, 지장간, 투간, 통근, 원국 내 관계, 공망, 병존/간여지동을 반영한 실세력 십성분포
   - 신강약, 용신 후보, 직업/재물/관계 성향 판단의 주요 입력값

4. ten_god_context
   - 드러난 십성, 암장 십성, 없는 십성, 과다 십성, 고립 십성, 일간과의 작동 관계를 설명하는 진단 레이어
```

중요:

```text
십성분포는 용신을 직접 확정하지 않는다.
십성분포는 일간 기준 역할 분포이며,
용신은 신강약 + 구조 + 조후 + 특수격 + 사용자 검증을 통합해 판단한다.
```

---

## 2. 최상위 출력 구조

```yaml
ten_god_analysis:
  scope: natal_chart_only

  day_master:
    stem:
    element:
    polarity:

  raw_visible_ten_god_distribution:
    scores:
      비견:
      겁재:
      식신:
      상관:
      편재:
      정재:
      편관:
      정관:
      편인:
      정인:
    percent:
    visible_items:

  hidden_base_ten_god_distribution:
    scores:
    percent:
    hidden_items:

  effective_ten_god_distribution:
    scores:
    percent:
    strongest_ten_god:
    weakest_ten_god:
    group_distribution:
      peer:
      output:
      wealth:
      officer:
      resource:

  ten_god_context:
    visible_ten_gods:
    hidden_only_ten_gods:
    missing_visible_ten_gods:
    truly_absent_ten_gods:
    excessive_ten_gods:
    deficient_ten_gods:
    isolated_ten_gods:
    exposed_hidden_ten_gods:
    duplicated_ten_gods:
    damaged_ten_gods:
    activated_ten_gods:

  calculation_trace:
    heavenly_stems:
    branch_representatives:
    hidden_stems:
    position_modifier:
    month_command_modifier:
    exposure_modifier:
    rooting_modifier:
    relation_modifier:
    void_modifier:
    coexistence_modifier:
    final_normalization:
```

---

## 3. 입력 데이터 요구사항

십성분포 계산 전에 `manse-core`는 아래 정보를 제공해야 한다.

```yaml
chart:
  day_stem:
    value:
    element:
    polarity:

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

  five_element_analysis:
    effective_force_distribution:
    climate_context:

  solar_term_basis:
    month_branch:
    seasonal_phase:
    days_since_term:
    days_until_next_term:

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

## 4. 십성 산출 규칙

### 4.1 오행 관계

일간을 기준으로 상대 천간 또는 지장간의 오행 관계를 판정한다.

```text
나와 같은 오행 = 비겁 그룹
내가 생하는 오행 = 식상 그룹
내가 극하는 오행 = 재성 그룹
나를 극하는 오행 = 관성 그룹
나를 생하는 오행 = 인성 그룹
```

### 4.2 음양에 따른 정/편 구분

십성은 오행 관계와 음양 관계를 함께 봐야 한다.

```yaml
ten_god_mapping_policy:
  same_element:
    same_polarity: 비견
    opposite_polarity: 겁재

  generated_by_day_master:
    same_polarity: 식신
    opposite_polarity: 상관

  controlled_by_day_master:
    same_polarity: 편재
    opposite_polarity: 정재

  controlling_day_master:
    same_polarity: 편관
    opposite_polarity: 정관

  generating_day_master:
    same_polarity: 편인
    opposite_polarity: 정인
```

예시: 기토 일간

```yaml
day_master: 기토
polarity: 음
ten_gods:
  무: 겁재
  기: 비견
  경: 상관
  신: 식신
  임: 정재
  계: 편재
  갑: 정관
  을: 편관
  병: 정인
  정: 편인
```

주의:

```text
일간 자체는 십성분포의 기준점이다.
일간을 비견으로 자동 포함할지 여부는 별도 정책으로 분리한다.
```

---

## 5. 일간 처리 정책

십성분포에서 일간을 어떻게 처리할지 반드시 분리한다.

```yaml
day_stem_distribution_policy:
  raw_visible_display:
    include_day_stem_as_reference: true
    count_day_stem_as_bigeon: false

  effective_distribution:
    count_day_stem_as_bigeon: false
    store_as_day_master_reference: true

  explanation:
    일간은 모든 십성을 판정하는 기준이므로,
    주변 세력 분포 계산에서는 기본적으로 점수에 포함하지 않는다.
```

단, 사용자 화면에서는 일주 카드에 `천간 일간`으로 표시한다.

```text
일간 = 나 자신
비견 = 나와 같은 오행이 외부에 또 있는 경우
```

이 구분이 없으면 비견 점수가 과대 계산될 수 있다.

---

## 6. 레이어 1 — raw_visible_ten_god_distribution

### 6.1 목적

표면에 드러난 십성 흐름을 보여준다.

포함:

```text
1. 년간, 월간, 시간의 십성
2. 일간은 기준점으로 별도 표시
3. 지지 대표 십성
```

지지 대표 십성은 기본적으로 지장간 `본기` 기준으로 산출한다.

```yaml
branch_representative_policy:
  default: main_hidden_stem
  alternatives:
    - branch_surface_element
    - month_command_hidden_stem
```

권장:

```text
지지 십성 표시 = 본기 기준
지지 세력 계산 = 지장간 전체 기준
```

### 6.2 기본 가중치

```yaml
raw_visible_ten_god_weight:
  heavenly_stem:
    year: 1.0
    month: 1.0
    day: 0.0
    hour: 1.0

  branch_representative:
    year: 1.0
    month: 1.0
    day: 1.0
    hour: 1.0
```

사용자 표시용으로만 사용하고, 판정용은 `effective_ten_god_distribution`을 사용한다.

---

## 7. 레이어 2 — hidden_base_ten_god_distribution

### 7.1 목적

지장간의 십성을 반영한 잠재 역할 분포다.

### 7.2 지장간 가중치

오행분포 문서와 같은 기본값을 사용한다.

```yaml
hidden_stem_base_weight:
  main: 0.70
  middle: 0.20
  residual: 0.10
```

단일 지장간 지지는 1.00으로 처리한다.

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

---

## 8. 레이어 3 — effective_ten_god_distribution

### 8.1 목적

실제 작동 가능성이 높은 십성 세력을 계산한다.  
다음 요소를 반영한다.

```text
1. 천간 위치
2. 지지 위치
3. 지장간 본기/중기/여기
4. 월지/월령 보정
5. 투간 보정
6. 통근 보정
7. 원국 내 합충형파해 보정
8. 공망 보정
9. 병존/간여지동 보정
10. 조후 컨텍스트
```

---

## 9. 기본 파워 계산

### 9.1 천간 위치 가중치

```yaml
heavenly_stem_position_weight:
  year: 8
  month: 12
  day: 0
  hour: 10
```

일간은 기준점이므로 0이다.

### 9.2 지지 위치 가중치

지지는 본기/중기/여기 십성으로 분해해서 계산한다.

```yaml
earthly_branch_position_weight:
  year: 12
  month: 28
  day: 24
  hour: 16
```

### 9.3 지장간 유효 가중치

```yaml
hidden_stem_effective_weight:
  main: 1.00
  middle: 0.60
  residual: 0.35
```

계산식:

```python
hidden_ten_god_power = branch_position_weight * hidden_stem_effective_weight
```

---

## 10. 월지/월령 보정

### 10.1 원칙

월지는 십성분포에서 특히 중요하다.

월지는 다음 역할을 한다.

```text
1. 계절권
2. 격국 결정 근거
3. 사회 환경
4. 전체 원국에서 가장 강한 지지 가중치
```

### 10.2 월령 계수 적용

오행분포의 계절 계수를 십성으로 변환해 사용한다.

```python
element_state = get_element_state_in_month(stem.element, month_branch)
season_coeff = season_coefficient[element_state]
ten_god_power *= season_coeff
```

기본 계수:

```yaml
season_coefficient:
  wang: 1.30
  xiang: 1.15
  xiu: 1.00
  qiu: 0.80
  si: 0.65
```

### 10.3 월지 본기 십성 강조

월지 본기 십성은 격국과 현실 환경에 강하게 작동한다.

```yaml
month_branch_main_ten_god_bonus:
  multiplier: 1.12
```

주의:

```text
월지 본기 십성을 강조하되,
그 십성을 격국으로 확정하는 것은 geokguk_analysis에서 별도 처리한다.
```

### 10.4 절기 내 사령 지장간 옵션

고도화 옵션:

```yaml
seasonal_hidden_stem_command:
  enabled: false_by_default
  use_days_since_solar_term: true
```

설명:

```text
같은 해월이라도 절기 초입/중기/말기에 따라 무·갑·임의 체감 비중이 달라질 수 있다.
MVP에서는 고정 지장간 비율을 사용한다.
v2.1에서 사령일수 테이블을 적용한다.
```

---

## 11. 투간 보정

### 11.1 정의

지장간의 십성이 천간에 드러나면 작동성이 증가한다.

```text
지장간에만 있는 십성 = 잠재성
천간에 드러난 십성 = 표면 작동성
지장간 + 천간 동시 존재 = 현실화 가능성 증가
```

### 11.2 계산 정책

```yaml
ten_god_exposure_modifier:
  exact_hidden_stem_exposed:
    multiplier: 1.15

  same_ten_god_exposed:
    multiplier: 1.10

  exposed_in_month_stem_extra:
    multiplier: 1.05

  exposed_in_hour_stem_contextual:
    multiplier: 1.03

  exposed_in_year_stem_contextual:
    multiplier: 1.02
```

예:

```text
해월 지장간 임수가 있고 천간 임수가 투간하면 정재 작동성이 증가한다.
기토 일간에서 월간 정화는 편인으로 드러나므로 편인 작동성이 증가한다.
```

주의:

```text
투간 보정은 십성을 새로 생성하는 것이 아니라,
이미 원국 내 존재하는 십성의 작동성을 높이는 보정이다.
```

---

## 12. 통근 보정과 십성

### 12.1 십성분포에서 통근의 의미

통근은 천간의 작동성을 높인다.  
특히 천간 십성이 지지에 같은 천간 또는 같은 오행 뿌리를 가질 때 해당 십성의 실세력이 증가한다.

```yaml
ten_god_rooting_modifier:
  exact_stem_root:
    strong_root: 1.18
    medium_root: 1.12
    weak_root: 1.06

  same_element_root:
    strong_root: 1.12
    medium_root: 1.08
    weak_root: 1.04
```

### 12.2 일간 통근과 십성분포

일간 통근은 특정 십성분포에 직접 더하는 값이 아니라, `strength_analysis.root_score`에 반영한다.

```text
일간 통근:
  신강약 root_score에 반영

다른 천간 통근:
  해당 천간 십성의 작동성에 반영
```

예:

```text
시간 기토 비견이 지지 무토에 뿌리를 두면 비견 작동성이 증가한다.
일간 기토가 지지 무토에 뿌리를 두는 것은 일간 기반으로 별도 계산한다.
```

---

## 13. 원국 내 관계 보정

### 13.1 원칙

합충형파해는 십성의 “양”보다 “작동 방식”에 더 큰 영향을 준다.

v2에서는 관계 보정을 다음처럼 분리한다.

```text
1. activation: 십성 작동성 자극
2. damage: 십성 기반 손상
3. lock: 합으로 묶여 작동성 제한
4. transformation: 조건 충족 시 십성 역할 변환
5. volatility: 사건화 가능성 증가
```

---

### 13.2 천간합

천간합은 천간 십성에 직접 영향을 준다.

```yaml
stem_combination:
  no_transformation:
    involved_ten_gods_activation: 1.05
    actionability_lock: 0.95

  transformation_possible:
    original_ten_gods_multiplier: 0.85
    transformed_element_ten_god_gain: 1.20

  transformation_confirmed:
    original_ten_gods_multiplier: 0.65
    transformed_element_ten_god_gain: 1.35
```

주의:

```text
천간합이 있다고 무조건 합화하지 않는다.
합화 여부는 월령, 뿌리, 방해 요소, 전체 흐름을 확인한다.
```

---

### 13.3 지지육합

```yaml
branch_six_combination:
  no_transformation:
    involved_hidden_ten_gods_activation: 1.05
    actionability_lock: 0.95

  transformation_possible:
    original_hidden_ten_gods_multiplier: 0.85
    transformed_ten_god_gain: 1.20

  transformation_confirmed:
    original_hidden_ten_gods_multiplier: 0.65
    transformed_ten_god_gain: 1.35
```

---

### 13.4 삼합/방합

삼합/방합은 특정 오행으로 흐름을 만들고, 그 오행이 일간 기준 어떤 십성인지로 변환한다.

```yaml
three_harmony:
  complete:
    target_ten_god_gain: 1.35
    member_ten_gods_activation: 1.10

  half:
    target_ten_god_gain: 1.18

directional_combo:
  target_ten_god_gain: 1.30
```

추가 보정:

```yaml
combo_contains_month_branch_bonus: 1.07
combo_contains_day_branch_bonus: 1.05
```

---

### 13.5 충

충은 삭제가 아니라 자극과 손상으로 처리한다.

```yaml
branch_clash:
  involved_ten_gods_activation: 1.08
  stability_loss: 0.88
  weak_root_damage: 0.75
  strong_root_damage: 0.90
```

출력 trace:

```yaml
clash_effect:
  activated_ten_gods:
  damaged_ten_gods:
  affected_positions:
  affected_palaces:
  volatility_score:
```

---

### 13.6 형·파·해·자형

```yaml
punishment:
  involved_ten_gods_activation: 1.05
  stability_loss: 0.90

self_punishment:
  repeated_ten_god_amplification: 1.06
  inner_friction: 1.12

break:
  stability_loss: 0.92
  relation_damage: 0.95

harm:
  hidden_instability: 0.92
  indirect_damage: 0.95
```

자형의 경우:

```text
같은 지지가 반복되어 같은 십성이 증폭되지만,
내부 마찰과 반복 문제가 증가한다.
```

---

## 14. 공망 보정

### 14.1 원칙

공망은 해당 지지의 십성을 삭제하지 않는다.  
원국 내에서는 “실체화 약화/지연/비가시성”으로 처리한다.

```yaml
void_ten_god_modifier:
  affected_branch_ten_god_multiplier: 0.85
  hidden_ten_god_multiplier: 0.85
  display_as_void: true
  do_not_remove_ten_god: true
```

주의:

```text
공망 지지가 월지 또는 일지인 경우 과도한 차감 금지.
원국 핵심 구조를 삭제하면 신강약과 용신 후보가 크게 왜곡된다.
```

---

## 15. 병존/간여지동 보정

### 15.1 천간 병존

```yaml
same_heavenly_stem_duplication:
  ten_god_gain: 1.06
  expression_intensity_gain: 1.10
  adjacent_bonus: 1.03
```

예:

```text
기기 천간병존 → 비견/일간 자기성 증폭
```

### 15.2 지지 병존

```yaml
same_branch_duplication:
  hidden_ten_god_gain: 1.10
  branch_theme_amplification: 1.15
  self_friction_if_applicable: 1.08
```

예:

```text
해해 지지병존 → 정재, 정관/정재/겁재 등 해 지장간 관련 십성 반복
```

### 15.3 간여지동

```yaml
gan_yeo_ji_dong:
  same_element_stem_branch:
    ten_god_theme_purity_gain: 1.08
    pillar_focus_gain: 1.12
```

주의:

```text
간여지동은 십성 자체를 새로 만들지 않는다.
해당 주의 십성 테마 집중도를 높인다.
```

---

## 16. 조후와 십성분포의 관계

### 16.1 핵심 정책

조후는 십성분포 점수를 직접 크게 바꾸지 않는다.

```text
조후는 환경 조건이다.
십성분포는 역할 분포다.
용신 후보 단계에서 두 정보를 함께 참조한다.
```

### 16.2 제한적 작동성 보정

MVP에서는 조후를 십성분포에 직접 반영하지 않는다.  
다만 v2.1에서 아래처럼 작동성 보정을 실험할 수 있다.

```yaml
johu_ten_god_operability_modifier:
  excessive_cold:
    fire_related_ten_gods_operability: 0.95
  excessive_heat:
    water_related_ten_gods_operability: 0.95
  excessive_damp:
    earth_related_ten_gods_stability: 0.96
  excessive_dry:
    wood_related_ten_gods_growth: 0.96
```

권장:

```text
MVP:
  조후는 ten_god_analysis.calculation_trace에 참조만 남김.
  실제 점수에는 반영하지 않음.

v2.1:
  operability_modifier 실험 적용.
```

---

## 17. 없는 십성, 암장 십성, 진짜 부재

십성분포에서는 “없다”를 세 단계로 나눠야 한다.

```yaml
ten_god_presence_classification:
  visible:
    description: 천간 또는 지지 대표 십성에 드러남

  hidden_only:
    description: 천간에는 없으나 지장간에 존재

  absent:
    description: 천간, 지지 대표, 지장간 어디에도 없음
```

출력 예시:

```yaml
presence:
  visible_ten_gods:
    - 상관
    - 편인
    - 정재
    - 정인
    - 비견

  hidden_only_ten_gods:
    - 겁재
    - 정관

  missing_visible_ten_gods:
    - 식신
    - 편재
    - 편관

  truly_absent_ten_gods:
    - 식신
    - 편재
    - 편관
```

주의:

```text
천간에 없다고 없는 십성으로 단정하지 않는다.
지장간에 있으면 암장 십성으로 분류한다.
```

---

## 18. 십성 그룹 분포

개별 십성 10개 외에 5개 그룹 분포도 계산한다.

```yaml
ten_god_group_distribution:
  peer:
    members: [비견, 겁재]
  output:
    members: [식신, 상관]
  wealth:
    members: [편재, 정재]
  officer:
    members: [편관, 정관]
  resource:
    members: [편인, 정인]
```

사용처:

```text
1. 신강약 side_balance_score
2. 재성 과다 / 관살 과다 / 인성 과다 판단
3. 부일간 모델
4. 재다신약, 관살혼잡, 식상과다 등 구조 진단
```

---

## 19. 과다/부족/고립 십성 진단

### 19.1 과다 십성

```yaml
excessive_ten_god_threshold:
  individual_percent_above: 30.0
  group_percent_above: 40.0
```

예:

```yaml
excessive_ten_gods:
  - ten_god: 정재
    percent: 43.7
    group: wealth
    reason:
      - individual_above_threshold
      - group_wealth_above_threshold
```

### 19.2 부족 십성

```yaml
deficient_ten_god_threshold:
  individual_percent_below: 3.0
  group_percent_below: 8.0
```

주의:

```text
부족 십성은 반드시 나쁜 것이 아니다.
기능 결핍, 비가시성, 또는 현실화 지연으로 해석한다.
용신 후보와 직접 연결하지 않는다.
```

### 19.3 고립 십성

고립은 부족과 다르다.

```yaml
isolated_ten_god_conditions:
  - exists_only_in_hidden_stem: true
  - no_visible_stem: true
  - weak_hidden_position: true
  - damaged_by_relation: true
  - no_supporting_element_flow: true
```

출력:

```yaml
isolated_ten_gods:
  - ten_god: 정관
    isolation_score: 0.68
    reason:
      - 지장간 중기에만 존재
      - 천간 투출 없음
      - 충/해로 작동성 불안정
```

---

## 20. 십성 특수 구조 진단

십성분포는 다음 구조 진단의 입력값이 된다.

```yaml
ten_god_patterns:
  jaeda_sinyak:
    description: 재다신약
    condition:
      - wealth_group_high
      - strength_band_in_weak_side

  gwansal_mixed:
    description: 관살혼잡
    condition:
      - 편관 and 정관 both_visible_or_strong
      - officer_group_high

  siksang_excess:
    description: 식상과다
    condition:
      - output_group_high

  insung_excess:
    description: 인성과다
    condition:
      - resource_group_high

  bigyeop_excess:
    description: 비겁과다
    condition:
      - peer_group_high

  sanggwan_gyeongwan:
    description: 상관견관
    condition:
      - 상관 strong
      - 정관 visible_or_strong
      - relation_stability_low
```

주의:

```text
이 구조 진단은 최종 통변용 태그다.
자동으로 길흉을 단정하지 않는다.
```

---

## 21. 최종 정규화

각 레이어는 raw score를 계산한 후 백분율로 변환한다.

```python
percent[ten_god] = ten_god_score[ten_god] / sum(ten_god_score.values()) * 100
```

주의:

```text
차감 보정 후 음수가 되면 0으로 clamp한다.
총합이 0이면 오류로 처리한다.
일간은 effective_distribution에서 제외하고 day_master_reference로 보관한다.
```

---

## 22. 출력 예시

```json
{
  "ten_god_analysis": {
    "scope": "natal_chart_only",
    "day_master": {
      "stem": "己",
      "element": "earth",
      "polarity": "yin"
    },
    "raw_visible_ten_god_distribution": {
      "scores": {
        "비견": 1.0,
        "겁재": 0.0,
        "식신": 0.0,
        "상관": 2.0,
        "편재": 0.0,
        "정재": 2.0,
        "편관": 0.0,
        "정관": 0.0,
        "편인": 1.0,
        "정인": 1.0
      },
      "visible_items": [
        {
          "position": "year_stem",
          "stem": "庚",
          "ten_god": "상관"
        },
        {
          "position": "month_stem",
          "stem": "丁",
          "ten_god": "편인"
        },
        {
          "position": "hour_stem",
          "stem": "己",
          "ten_god": "비견"
        }
      ]
    },
    "effective_ten_god_distribution": {
      "percent": {
        "비견": 8.8,
        "겁재": 2.7,
        "식신": 0.0,
        "상관": 18.1,
        "편재": 0.0,
        "정재": 43.7,
        "편관": 0.0,
        "정관": 4.6,
        "편인": 11.5,
        "정인": 10.5
      },
      "strongest_ten_god": "정재",
      "group_distribution": {
        "peer": 11.5,
        "output": 18.1,
        "wealth": 43.7,
        "officer": 4.6,
        "resource": 22.0
      }
    },
    "ten_god_context": {
      "hidden_only_ten_gods": ["겁재", "정관"],
      "missing_visible_ten_gods": ["식신", "편재", "편관"],
      "truly_absent_ten_gods": ["식신", "편재", "편관"],
      "excessive_ten_gods": ["정재"],
      "calculation_warnings": [
        "천간에 없더라도 지장간에 있으면 암장 십성으로 분류한다.",
        "십성분포만으로 용신을 확정하지 않는다."
      ]
    }
  }
}
```

---

## 23. 구현 의사코드

```python
def calculate_ten_god_analysis(chart: NatalChart) -> TenGodAnalysis:
    day_master = chart.day_stem

    ten_god_mapper = TenGodMapper(day_master)

    raw_visible = calculate_raw_visible_ten_god_distribution(
        chart=chart,
        mapper=ten_god_mapper,
        count_day_stem=False,
        branch_representative_policy="main_hidden_stem"
    )

    hidden_base = calculate_hidden_base_ten_god_distribution(
        chart=chart,
        mapper=ten_god_mapper,
        hidden_stem_weights=DEFAULT_HIDDEN_STEM_BASE_WEIGHT
    )

    base_power = calculate_position_weighted_ten_god_power(
        chart=chart,
        mapper=ten_god_mapper,
        stem_position_weight=HEAVENLY_STEM_POSITION_WEIGHT,
        branch_position_weight=EARTHLY_BRANCH_POSITION_WEIGHT,
        hidden_stem_weight=HIDDEN_STEM_EFFECTIVE_WEIGHT
    )

    seasonal_power = apply_ten_god_month_command_modifier(
        ten_god_power=base_power,
        chart=chart,
        mapper=ten_god_mapper
    )

    exposed_power, exposure_trace = apply_ten_god_exposure_modifier(
        ten_god_power=seasonal_power,
        chart=chart,
        mapper=ten_god_mapper
    )

    rooted_power, rooting_trace = apply_ten_god_rooting_modifier(
        ten_god_power=exposed_power,
        chart=chart,
        mapper=ten_god_mapper
    )

    relation_power, relation_trace = apply_ten_god_relation_modifier(
        ten_god_power=rooted_power,
        chart=chart,
        mapper=ten_god_mapper
    )

    void_power, void_trace = apply_ten_god_void_modifier(
        ten_god_power=relation_power,
        chart=chart,
        mapper=ten_god_mapper
    )

    amplified_power, amplifier_trace = apply_ten_god_structural_amplifier_modifier(
        ten_god_power=void_power,
        chart=chart,
        mapper=ten_god_mapper
    )

    effective = normalize_ten_god_power(amplified_power)

    context = diagnose_ten_god_context(
        raw_visible=raw_visible,
        hidden_base=hidden_base,
        effective=effective,
        traces=[exposure_trace, rooting_trace, relation_trace, void_trace, amplifier_trace]
    )

    return TenGodAnalysis(
        scope="natal_chart_only",
        day_master=day_master,
        raw_visible_ten_god_distribution=raw_visible,
        hidden_base_ten_god_distribution=hidden_base,
        effective_ten_god_distribution=effective,
        ten_god_context=context
    )
```

---

## 24. 테스트 케이스

### 24.1 필수 테스트

```text
1. 일간별 십성 매핑이 정확한지
2. 음양 정/편 구분이 정확한지
3. 일간이 비견으로 자동 포함되지 않는지
4. 지지 대표 십성이 본기 기준으로 계산되는지
5. 지장간 십성이 본기/중기/여기로 계산되는지
6. 월지 본기 십성이 과도하게 중복되지 않는지
7. 투간 십성 보정이 trace에 남는지
8. 공망 십성이 0으로 삭제되지 않는지
9. 합충형파해가 activation/damage/lock/transform으로 기록되는지
10. 조후가 십성점수를 직접 크게 바꾸지 않는지
```

### 24.2 엣지 테스트

```text
1. 재성 과다 + 신약
2. 관살혼잡
3. 식상과다
4. 인성과다
5. 비겁과다
6. 천간에는 없고 지장간에만 있는 정관
7. 지지병존으로 같은 십성 반복
8. 공망 지지에 핵심 십성이 있는 경우
9. 합화 후보로 십성이 바뀔 가능성이 있는 경우
10. 일간과 동일 천간이 시간에 있는 경우
```

---

## 25. Codex 구현 작업 단위

```text
1. TenGod enum 정의
2. TenGodGroup enum 정의
3. Stem polarity 정의
4. day_master 기준 TenGodMapper 구현
5. raw_visible_ten_god_distribution 구현
6. hidden_base_ten_god_distribution 구현
7. effective_ten_god_distribution 구현
8. ten_god_group_distribution 구현
9. visible/hidden/absent classification 구현
10. excessive/deficient/isolated ten god 진단 구현
11. ten_god_pattern_detector 구현
12. JSON schema 작성
13. unit test 작성
14. regression fixture 작성
```

---

## 26. 구현 금지 사항

```text
1. 일간을 비견 점수에 자동 포함하지 말 것.
2. 천간에 없다는 이유로 십성이 완전히 없다고 판단하지 말 것.
3. 지장간 십성을 무시하지 말 것.
4. 월지 본기 십성을 격국 확정으로 바로 연결하지 말 것.
5. 십성분포만으로 용신을 확정하지 말 것.
6. 부족 십성을 자동으로 보완 대상 또는 용신으로 처리하지 말 것.
7. 공망 십성을 0으로 삭제하지 말 것.
8. 합을 무조건 합화로 처리하지 말 것.
9. 조후를 십성분포 점수에 직접 크게 반영하지 말 것.
10. 대운·세운 십성을 원국 십성분포에 섞지 말 것.
```

---

## 27. 완료 기준

```text
1. 원국만으로 십성분포가 계산된다.
2. raw_visible / hidden_base / effective / context 레이어가 분리된다.
3. 일간 기준 십성 매핑과 음양 정/편 구분이 정확하다.
4. 일간은 기준점으로 분리되어 비견 점수에 자동 포함되지 않는다.
5. 지장간 십성이 계산에 반영된다.
6. 월지/월령, 투간, 통근, 합충형파해, 공망, 병존/간여지동 보정 trace가 남는다.
7. 없는 십성, 암장 십성, 진짜 부재가 구분된다.
8. 과다/부족/고립 십성이 진단된다.
9. 십성 그룹 분포가 계산된다.
10. 십성분포 결과만으로 용신을 확정하지 않는다.

---

# v2.1 보완 — 십성 의미 태그와 월지/일지 의미

## 1. 십성 의미 태그

```yaml
ten_god_semantic_tags:
  정인: [제도권 학문, 학위, 보호, 정규 교육]
  편인: [특수 학문, 실용 기술, 응용 연구, 비주류 전문성, 특수교육, 다문화/비표준 영역]
  재성: [사회활동, 네트워크, 수입 활동, 대외 접촉, 현실 확장]
  편관: [간판, 브랜드, 명예, 압박, 난관, 권위 지향]
```

## 2. 월지/일지 의미 레이어

```yaml
palace_semantic_layer:
  month_branch:
    domain: career_environment_inner_desire
    visibility: inner_drive
  day_branch:
    domain: self_root_spouse_health_work_reality
    visibility: core_reality
```
