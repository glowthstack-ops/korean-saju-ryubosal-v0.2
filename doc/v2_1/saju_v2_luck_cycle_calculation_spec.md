# 사주서비스 v2 — 대운·세운·월운 계산 명세서

> 목적: LLM 없이 대운·세운·월운을 산출하고, 원국과의 관계 및 용신 후보 검증용 운 데이터를 제공하기 위한 명세서.

---

## 1. 범위

```text
- 대운 순행/역행
- 대운 시작 시점
- 10년 대운표
- 세운
- 월운
- 원국과 운의 합충형파해
- 용신/기신 후보와의 관계
- 검증 질문용 운 후보 추출 데이터
```

---

## 2. 대운 순역

대운 순역은 서비스 정책에 따라 계산한다.

```yaml
daewoon_direction_input:
  gender_for_daewoon:
  year_stem_yin_yang:
  direction:
```

일반 정책 예:

```text
양남음녀 순행
음남양녀 역행
```

단, 이 정책은 config로 분리한다.

---

## 3. 대운 시작 시점

절기까지의 시간 차이를 기준으로 대운 시작 나이를 산출한다.

```yaml
daewoon_start:
  nearest_solar_term:
  time_delta_days:
  conversion_rule:
    three_days_one_year:
  start_age:
  start_date:
```

MVP에서는 기존 v1과 동일한 기준을 fixture로 검증한다.

---

## 4. 대운 산출

```yaml
daewoon_item:
  index:
  start_age:
  start_date:
  end_date:
  ganji:
  stem_ten_god:
  branch_ten_god:
  twelve_unseong:
  relations_to_chart:
  yongsin_candidate_relation:
  volatility_score:
```

---

## 5. 세운 산출

세운은 양력/절기 기준 연도로 산출한다.

```yaml
yearly_luck_item:
  year:
  ganji:
  stem_ten_god:
  branch_ten_god:
  relations_to_chart:
  activated_elements:
  activated_ten_gods:
  palace_activation:
```

입춘 기준 적용 여부를 명확히 한다.

---

## 6. 월운 산출

월운은 해당 연도 월간지와 절기 구간으로 산출한다.

```yaml
monthly_luck_item:
  year_month:
  solar_term_range:
  ganji:
  stem_ten_god:
  branch_ten_god:
  relations_to_chart:
```

---

## 7. 원국과 운의 관계

운은 원국 오행분포를 직접 바꾸지 않는다.  
별도 `luck_effect`로 계산한다.

```yaml
luck_effect:
  period:
  activated_elements:
  activated_ten_gods:
  relation_events:
  yongsin_alignment_score:
  gisin_alignment_score:
  volatility_score:
  event_domains:
```

---

## 8. 검증 루프 연동

용신 검증 질문 생성 시 사용한다.

```text
- 용신 후보가 들어오는 해
- 기신 후보가 들어오는 해
- 대운과 세운이 같은 방향으로 작동하는 해
- 원국 핵심 궁성이 자극되는 해
- 충/합/형으로 사건성이 큰 해
```

---

## 9. 출력 예시

```yaml
luck_cycles:
  current_age:
  current_daewoon:
  daewoon_table:
  yearly_luck:
  monthly_luck:
  calibration_candidate_periods:
```

---

## 10. 구현 금지 사항

```text
1. 대운/세운을 원국 오행분포에 섞지 말 것.
2. 입춘 기준 여부를 숨기지 말 것.
3. 대운 시작일 산출 근거를 숨기지 말 것.
4. 세운만 보고 길흉을 단정하지 말 것.
5. 용신 후보 미확정 상태에서 운의 길흉을 확정 표현하지 말 것.

---

# v2.1 보완 — 대운 상하반기·운의 변환 오행·운성 이벤트

## 1. 대운 상반기/하반기

```yaml
daewoon_phase:
  first_half:
    years: 0-4
    dominant_component: stem
  second_half:
    years: 5-9
    dominant_component: branch
```

## 2. 운의 raw/transformed 분리

```yaml
luck_effect:
  raw_luck_elements:
  transformed_luck_elements:
  transformation_confidence:
  final_luck_alignment:
```

## 3. 운성 절의 이벤트 태그

```yaml
luck_unseong_event_tags:
  unseong: 절
  possible_event_domains:
    - relocation
    - career_change
    - academic_change
    - major_environment_change
    - identity_shift
```

## 4. 용신운 사건 평가

용신운은 “사건 없음”이 아니라 “수습/회복/결과 개선”으로도 나타날 수 있다.
