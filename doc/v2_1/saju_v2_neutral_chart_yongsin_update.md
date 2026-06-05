# 사주서비스 v2 — 중화사주 용신 판정 보완 명세서

> 목적: 중화사주, 중화신약, 중화신강, 신왕하지만 신강은 아닌 명식의 용신 후보 산출 오류를 줄이기 위한 보완 명세서.  
> 핵심: 뿌리가 튼튼하다고 신강은 아니다. 신왕과 신강은 분리한다.

---

## 1. 핵심 개념 분리

```text
신왕:
  일간이 지지에 뿌리를 튼튼하게 두고 있음

신강:
  월지/일지 포함 전체 세력이 일간 편으로 기울어 있음

중화신약:
  전체 점수는 중화권이나 일간 편이 우세하지 않고 약한 쪽으로 기움

중화신강:
  전체 점수는 중화권이나 일간 편이 다소 우세함
```

---

## 2. 신강 최소 조건 게이트

```yaml
minimum_strong_condition:
  month_or_day_branch_ally:
    required: true
    ally_types: [peer, resource]
  another_ally_position_exists:
    required: true
  result:
    pass: can_be_strong_candidate
    fail: cannot_auto_classify_as_strong
```

규칙:

```text
월지 또는 일지 중 하나가 비겁/인성으로 일간의 편이어야 한다.
그 외 자리에도 내 편이 하나 이상 있어야 한다.
이 조건을 통과하지 못하면 root_score가 높아도 신강 확정 금지.
```

---

## 3. 신왕 판정

```yaml
day_master_rootedness:
  label: 무근 | 약근 | 보통 | 신왕
  score:
  root_sources:
    - position:
      hidden_stem:
      strength:
  damaged_roots:
  final_rootedness:
```

신왕은 신강과 별도 필드로 표시한다.

```yaml
strength_analysis:
  band: 중화신약
  rootedness: 신왕
  strong_chart_gate_passed: false
```

---

## 4. 중화권 판정 정책

```yaml
neutral_zone_policy:
  bands: [중화신약, 중화, 중화신강]
  auto_yongsin_confirm: false
  require_competing_models: true
  require_calibration: true
```

---

## 5. 신약 억부용신 3분기

특수격 제외 후 신약/중화신약의 억부용신 후보는 세 갈래다.

```yaml
weak_chart_eokbu_submodels:
  output_as_yongsin:
    condition:
      - day_master_rootedness in [신왕, strong]
      - officer_group_strong: true
    yongsin_group: output
    purpose: 강한 관성을 식상으로 제어

  resource_as_yongsin:
    condition:
      - day_master_has_root: true
      - wealth_group_strong or output_group_strong
    yongsin_group: resource
    heesin_group: officer
    purpose: 재성/식상으로 빠지는 기운을 인성으로 회복

  peer_as_yongsin:
    condition:
      - not output_as_yongsin
      - not resource_as_yongsin
    yongsin_group: peer
    purpose: 일간 직접 보강
```

---

## 6. 중화신약 + 신왕 모델

```yaml
rooted_but_not_strong_model:
  label: 신왕하지만 신강은 아님
  conditions:
    - day_master_rootedness in [신왕, strong]
    - strong_chart_gate_passed: false
    - strength_band in [중화신약, 중화]
  yongsin_policy:
    - if wealth_or_output_strong: resource_candidate
    - if officer_strong: output_candidate
    - else: peer_candidate
  requires_validation: true
```

---

## 7. 검증 질문 보완

```yaml
neutral_chart_calibration_questions:
  compare_flows:
    - fire_earth_vs_metal_water
    - peer_resource_vs_wealth_output
    - officer_pressure_vs_output_control
  include_behavior_change: true
  include_recovery_outcome: true
```

추가 질문 도메인:

```yaml
additional_event_domains:
  behavior_change:
    - 대외활동 증가
    - 성격 변화
    - 독립성 증가
    - 사회적 네트워크 확대
    - 리더십 증가
  self_direction:
    - 진로 재설정
    - 전공 변경
    - 재수/재입학
    - 새로운 목표 설정
```

---

## 8. 용신운 사건 평가 보완

```yaml
event_outcome_detail:
  event_occurred:
  event_type:
  severity: mild | medium | severe
  recovery_speed: fast | normal | slow
  lasting_damage: none | minor | major
  final_outcome: resolved | ongoing | worsened
```

---

## 9. 토 지지 contextual flow

토 지지는 단순 토로만 처리하지 않는다.

```yaml
earth_branch_context:
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

축토 보완:

```yaml
chou_water_flow_boost:
  conditions:
    - cold_season_or_night_context
    - gui_water_present_or_relevant
    - hidden_flow_earth_to_metal_to_water
  effects:
    water_operability_gain:
    earth_surface_reliability_down:
    mark_as_contextual_earth: true
```

---

## 10. 운의 변환 오행

대운·세운은 raw element와 transformed element를 분리한다.

```yaml
luck_effect:
  raw_luck_elements:
  transformed_luck_elements:
  transformation_confidence:
  reason:
  final_luck_alignment:
```

---

## 11. 대운 상반기/하반기

```yaml
daewoon_phase:
  first_half:
    years: 0-4
    dominant_component: stem
  second_half:
    years: 5-9
    dominant_component: branch
```

---

## 12. 구현 금지 사항

```text
1. 뿌리가 튼튼하다는 이유만으로 신강 판정하지 말 것.
2. 중화권에서 단일 용신을 확정하지 말 것.
3. 신약 용신을 비겁/인성만으로 단순화하지 말 것.
4. 용신운에 나쁜 사건이 있었다는 이유만으로 모델을 즉시 폐기하지 말 것.
5. 축토/진술축미를 모두 같은 토로만 처리하지 말 것.
6. 운의 합화/합류 변환을 무시하지 말 것.
```
