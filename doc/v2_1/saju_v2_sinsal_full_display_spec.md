# 사주서비스 v2 — 전체 신살 계산·표시 명세서

> 목적: v2 만세력에서 계산 가능한 신살을 선별 누락 없이 모두 제공하되, 해석 가중치와 사용처를 명확히 구분하기 위한 명세서.  
> 원칙: 신살은 전체 표시한다. 단, 신강약·용신·격국 결정의 핵심 근거로 직접 사용하지 않는다.

---

## 1. 핵심 정책

```yaml
sinsal_policy:
  calculate_all_available: true
  display_all_available: true
  allow_filtering: true
  use_for_yongsin_decision: false
  use_for_strength_decision: false
  use_for_geokguk_decision: false
  use_for_interpretation_tags: true
  use_for_event_domain_hint: true
```

---

## 2. 출력 구조

```yaml
sinsal_analysis:
  scope: natal_chart_only
  display_policy: show_all

  summary:
    repeated:
    major_positive:
    major_caution:
    palace_sensitive:
    structure_overlapped:

  by_pillar:
    year:
    month:
    day:
    hour:

  by_category:
    twelve_sinsal:
    noble_stars:
    academic_document:
    movement_change:
    relationship_social:
    isolation_conflict:
    health_risk:
    wealth_status:
    spiritual_intuition:
    miscellaneous:

  full_list:
    - name:
      category:
      position:
      basis:
      palace:
      ten_god_context:
      element_context:
      intensity:
      repeated:
      activated_by_relations:
      interpretation_tags:
      caution_tags:
      use_for_yongsin_decision: false
```

---

## 3. 카테고리

```yaml
sinsal_categories:
  twelve_sinsal:
    description: 12신살
  noble_stars:
    examples: [천을귀인, 천덕귀인, 월덕귀인, 태극귀인, 문창귀인, 학당귀인]
  academic_document:
    examples: [문창, 학당, 관귀학관]
  movement_change:
    examples: [역마, 지살]
  relationship_social:
    examples: [도화, 홍염, 금여]
  isolation_conflict:
    examples: [고신, 과숙, 귀문, 원진]
  health_risk:
    examples: [백호, 현침, 양인]
  wealth_status:
    examples: [금여록, 암록, 협록]
```

---

## 4. 중요도/강도 계산

```yaml
sinsal_intensity_factors:
  repeated_same_sinsal: +0.20
  appears_on_month_or_day: +0.15
  appears_on_day_branch: +0.12
  overlaps_with_clash_or_punishment: +0.12
  overlaps_with_void_branch: -0.05
  overlaps_with_yongsin_candidate: context_only
  overlaps_with_gisin_candidate: context_only
```

강도 라벨:

```text
low
medium
high
very_high
```

---

## 5. 주별 표시

```yaml
by_pillar:
  year:
    palace: 뿌리·가족궁
    sinsal:
  month:
    palace: 직업·환경궁
    sinsal:
  day:
    palace: 배우자·현실기반궁
    sinsal:
  hour:
    palace: 자녀·결과궁
    sinsal:
```

시간 모름이면:

```yaml
hour_unknown_policy:
  hour_sinsal_status: unknown
  show_warning: true
```

---

## 6. 신살과 구조 작용 연결

신살은 아래와 연결해 표시한다.

```text
- 위치
- 궁성
- 십성
- 오행
- 공망 여부
- 합충형파해 자극 여부
```

예:

```yaml
sinsal_item:
  name: 현침살
  position: year
  palace: 뿌리·가족궁
  ten_god_context: 상관
  element_context: 금
  activated_by_relations:
    - 신사형
  intensity: medium
```

---

## 7. UI 표시 정책

기본:

```text
주별 전체 신살 표시
```

추가 보기:

```text
카테고리별 보기
중요도순 보기
반복 신살 보기
주의 신살 보기
```

---

## 8. 해석 정책

```text
신살은 사건 분야, 성향, 주의 포인트를 보조한다.
신살만으로 길흉을 단정하지 않는다.
신살만으로 용신/기신을 바꾸지 않는다.
```

---

## 9. 테스트

```text
1. 모든 신살 계산 결과가 full_list에 포함되는지
2. 주별 표시와 카테고리별 표시가 동일 source를 참조하는지
3. 같은 신살 반복 시 intensity가 증가하는지
4. 시간 모름일 때 시주 신살이 unknown 처리되는지
5. 신살이 strength/yongsin/geokguk 점수에 직접 반영되지 않는지
```

---

## 10. 구현 금지 사항

```text
1. 중요 신살만 계산하고 나머지를 생략하지 말 것.
2. 신살을 용신 결정 근거로 직접 사용하지 말 것.
3. 시간 모름인데 시주 신살을 임의 생성하지 말 것.
4. 신살 이름만 나열하고 위치/근거/궁성을 누락하지 말 것.
5. 반복 신살 강도 계산을 누락하지 말 것.
```
