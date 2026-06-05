# 사주서비스 v2 — 합충형파해·구조 작용 명세서

> 목적: 원국 내 천간/지지 관계를 계산하고, 오행·십성·궁성·용신 안정도에 미치는 영향을 구조화하기 위한 명세서.  
> 원칙: 합충형파해는 길흉 단정이 아니라 작동성, 손상, 묶임, 변동성, 사건화 가능성을 계산하는 구조 레이어다.

---

## 1. 대상 관계

```text
천간:
- 천간합
- 천간충/극 관계
- 합화 가능성
- 합반/합거/합래 후보

지지:
- 육합
- 삼합
- 반합
- 방합
- 충
- 형
- 자형
- 파
- 해
- 병존
- 간여지동
```

---

## 2. 출력 구조

```yaml
structure_analysis:
  stem_relations:
  branch_relations:
  transformed_candidates:
  palace_interactions:
  affected_elements:
  affected_ten_gods:
  stability:
    yongsin_stability:
    geokguk_stability:
    root_stability:
  volatility_score:
  calculation_trace:
```

---

## 3. 관계 작용 유형

```yaml
relation_effect_type:
  activation:
    description: 해당 기운이 자극됨

  lock:
    description: 합으로 묶여 작동이 제한됨

  removal:
    description: 합거/충거 등으로 기능이 약화됨

  transformation:
    description: 합화 조건 충족 시 새 오행 흐름으로 변환

  conflict:
    description: 충·형·해로 불안정성 증가

  repetition:
    description: 병존/자형으로 반복·증폭
```

---

## 4. 합화 판정

합이 있다고 무조건 화하지 않는다.

필수 조건:

```text
1. 월령이 합화 오행을 지지
2. 합화 오행의 뿌리 존재
3. 방해하는 충/극이 약함
4. 천간 또는 지지 흐름이 합화 방향
5. 반대 오행이 고립 또는 무력
```

출력:

```yaml
transformation_check:
  exists: true
  possible: true
  confirmed: false
  confidence:
  blockers:
```

---

## 5. 합반/합거/합래/합류/합동 정책

```yaml
hapban:
  description: 합이 성립하지만 화하지 못하고 묶임
  effect:
    actionability: decrease
    stability: mixed

hapgeo:
  description: 특정 글자의 기능이 합으로 제거/약화
  condition:
    - 상대가 강함
    - 내 글자가 약함
    - 합 후 실질 기능 저하

haprae:
  description: 운 또는 외부 글자가 원국의 글자를 끌어와 작동
  condition:
    - 운 글자가 원국 글자를 합으로 자극
    - 해당 십성/궁성이 사건화

hapryu:
  description: 같은 흐름으로 합류하여 세력 강화
  condition:
    - 합이 특정 오행 흐름을 강화
    - 방합/삼합과 동반 가능

hapdong:
  description: 합으로 함께 움직이며 사건성이 증가
  condition:
    - 합이 해소/이동/변동과 연결
    - 충과 동반 시 강도 증가
```

MVP에서는 후보 태그로만 출력하고, 점수화는 보수적으로 한다.

---

## 6. 궁성 연결

각 지지는 궁성에 연결된다.

```yaml
palace_map:
  year_branch: 뿌리·가족궁
  month_branch: 직업·환경궁
  day_branch: 배우자궁
  hour_branch: 자녀·결과궁
```

관계는 궁성 간 작용으로도 출력한다.

```yaml
palace_interaction:
  relation: 충
  positions: [day, hour]
  palaces: [배우자궁, 자녀·결과궁]
  severity:
  event_domains:
```

---

## 7. 안정도 계산

```yaml
stability_modifier:
  harmonious_relation: +0.05
  clash: -0.12
  punishment: -0.10
  harm: -0.08
  break: -0.08
  self_punishment: -0.12
  combination_lock: -0.05
  confirmed_transformation: depends_on_model
```

사용처:

```text
- 용신 안정도
- 격국 안정도
- 통근 안정도
- 검증 연도 선택
```

---

## 8. 구현 금지 사항

```text
1. 합을 무조건 합화 처리하지 말 것.
2. 충을 단순 삭제로 처리하지 말 것.
3. 형파해를 길흉 단정으로만 출력하지 말 것.
4. 궁성 영향을 누락하지 말 것.
5. 합래/합거/합반을 확정값으로 남발하지 말 것.
6. 구조 작용만으로 용신을 확정하지 말 것.

---

# v2.1 보완 — 운의 변환 오행과 궁성 의미 강화

## 1. 운의 합화/합류 변환

원국뿐 아니라 대운·세운·월운과 원국의 관계에서도 raw element와 transformed element를 분리한다.

```yaml
luck_relation_transformation:
  raw_element:
  transformed_element:
  confidence:
  reason:
    - branch_combination_with_daewoon
    - branch_combination_with_natal
    - wang_branch_present
```

## 2. 왕지 동반 보정

```yaml
wang_branch_transformation_bonus:
  if_wang_branch_participates: +0.10
  if_month_branch_participates: +0.07
  if_day_branch_participates: +0.05
```

## 3. 궁성 의미 레이어

```yaml
palace_semantic_layer:
  year: 뿌리·가족·배경
  month: 직업·환경·내면 욕망
  day: 배우자·현실 기반·건강·직업 체감
  hour: 자녀·결과·미래·실행
```
