# 사주서비스 v2 — 만세력 페이지 UI 명세서

> 목적: LLM에 의존하지 않는 안정적인 만세력 엔진의 결과를 사용자가 직관적으로 확인할 수 있도록, 전통 만세력 앱 형태를 기반으로 한 v2 UI 구조를 정의한다.  
> 기준: 사용자가 제공한 예시 화면처럼 `시주 | 일주 | 월주 | 년주` 4주 보드를 중심으로 구성하되, v2의 시간 보정/진태양시/신강약/용신 후보/전체 신살 표시 정책을 반영한다.

---

## 1. UI 핵심 방향

```text
전통 만세력 판형 유지
+ 시간 모름/시간 입력 상태 명확화
+ 진태양시 적용 전후 표시
+ 4주 보드 중심
+ 형충회합/신살/십성/12운성 전체 표시
+ 상세 항목은 필터와 접기 패널로 정리
```

v2 만세력 페이지는 “해석 문장”보다 먼저 **계산 결과를 신뢰할 수 있게 보여주는 화면**이어야 한다.

---

## 2. 페이지 전체 구조

권장 순서:

```text
1. 상단 출생정보 요약 바
2. 시간 보정/진태양시 정보 카드
3. 4주 만세력 보드
4. 형충회합·구조 작용 요약 영역
5. 오행/십성/공망/월령 quick summary bar
6. 상세 필터 바
7. 상세 패널
   - 지장간
   - 십성
   - 오행분포
   - 십성분포
   - 신강약 9단계
   - 격국
   - 용신 후보
   - 전체 신살
   - 대운/세운/월운
```

---

## 3. 상단 출생정보 요약 바

예시:

```text
(양력) 1999년 10월 31일 09:08 · 출생지 서울 · 남성 · 순행대운
```

시간 모름:

```text
(양력) 1999년 10월 31일 시모름 · 출생지 서울 · 남성 · 대운방향 계산 가능
```

필드:

```yaml
birth_summary_bar:
  calendar_type:
  solar_date:
  lunar_date:
  is_leap_month:
  input_time:
  time_status: known | unknown
  birth_place:
  gender_for_daewoon:
  daewoon_direction:
  current_age:
```

---

## 4. 시간 보정/진태양시 카드

v2 차별점으로 반드시 표시한다.

```yaml
true_solar_time_card:
  input_local_time:
  timezone:
  dst_applied:
  longitude:
  longitude_correction_minutes:
  equation_of_time_minutes:
  true_solar_time:
  civil_hour_pillar:
  true_solar_hour_pillar:
  hour_pillar_changed:
  warnings:
```

표시 예:

```text
입력시각: 09:08
진태양시: 08:50
시주 변화: 있음
일반시 기준: 기사시
진태양시 기준: 무진시
```

시간 모름이면:

```text
시간 미입력 상태입니다.
시주, 시주 기준 신살, 일부 형충회합, 신강약/용신 신뢰도가 제한됩니다.
```

---

## 5. 4주 만세력 보드

컬럼 순서:

```text
시주 | 일주 | 월주 | 년주
```

각 컬럼 구조:

```yaml
pillar_column:
  title: 시주 | 일주 | 월주 | 년주
  ganji_label:
  top_relation_label: 합 | 충 | 합충 | -
  stem_ten_god:
  stem_tile:
    character:
    element:
    color:
    polarity:
  branch_tile:
    character:
    element:
    color:
    contextual_flow_element:
  branch_ten_god:
  hidden_stems:
  twelve_unseong:
  nabeum:
  void_badge:
  uncertainty_badge:
```

---

## 6. 시간 모름 모드

시간 미입력 시에도 시주 컬럼은 유지한다.

```yaml
unknown_hour_mode:
  hour_column:
    stem: "?"
    branch: "?"
    status: unknown
    display_color: neutral
  affected_sections:
    - hour_pillar
    - hour_hidden_stems
    - hour_ten_god
    - hour_unseong
    - hour_sinsal
    - some_structure_relations
    - yongsin_confidence
```

정책:

```text
시간 모름이어도 년·월·일주는 정상 표시한다.
시간 미상으로 인한 불확실성은 confidence와 warning에 반영한다.
```

---

## 7. 시간 입력 모드

시간 입력 시 시주 전체를 표시한다.

```yaml
known_hour_mode:
  hour_pillar_resolved: true
  show_civil_vs_true_solar_comparison: true
```

진태양시 적용으로 시주가 바뀌면 상단과 시주 컬럼에 강조한다.

```yaml
hour_change_badge:
  label: 진태양시 시주 변경
  severity: high
```

---

## 8. 오행 색상 규칙

```yaml
element_color:
  wood:
    background: green
    text: white
  fire:
    background: red
    text: white
  earth:
    background: yellow_or_ochre
    text: black
  metal:
    background: white_or_light_gray
    text: black
  water:
    background: black_or_dark_gray
    text: white
```

접근성:

```text
- 색만으로 구분하지 말고 글자/라벨을 함께 표시한다.
- 모바일에서도 대비를 유지한다.
```

---

## 9. 형충회합·구조 작용 영역

예시 화면의 연한 노란 영역을 계승한다.

표시 항목:

```text
- 천간합
- 지지육합
- 삼합
- 방합
- 반합
- 충
- 형
- 자형
- 파
- 해
- 귀문
- 암합
- 병존
- 간여지동
```

구조:

```yaml
structure_summary_panel:
  by_position:
    hour:
    day:
    month:
    year:
  relations:
    - relation:
      from:
      to:
      arrow:
      confidence:
      transformed_candidate:
```

---

## 10. Quick Summary Bar

4주 보드 아래에 표시한다.

```yaml
quick_summary_bar:
  five_element_raw_count:
  five_element_effective_percent:
  gongmang:
  cheoneul_gwiin:
  month_command:
  strength_band:
  yongsin_candidates:
```

예시:

```text
木 0, 火 1, 土 2, 金 2, 水 3
공망: [年]午未 [日]辰巳 · 천을귀인: 亥酉 · 월령: 戌
신강약: 중화신약 · 용신 후보: 화/토
```

---

## 11. 상세 필터 바

기본 필터:

```text
[✓] 십성
[✓] 신살
[✓] 12운성
[✓] 형충회합
[✓] 지장간
[ ] 납음
[ ] 오행분포
[ ] 십성분포
[ ] 신강약
[ ] 격국
[ ] 용신 후보
[ ] 대운
```

---

## 12. 전체 신살 UI

v2는 계산 가능한 신살을 모두 표시한다.

표시 방식:

```yaml
sinsal_panel:
  view_modes:
    - by_pillar
    - by_category
  categories:
    - 12신살
    - 귀인/길신
    - 학업/문서
    - 이동/변동
    - 관계/고독
    - 건강/사고
    - 재물/복록
    - 기타 전통 신살
```

각 항목:

```yaml
sinsal_item:
  name:
  category:
  position:
  basis:
  palace:
  ten_god_context:
  element_context:
  intensity:
  repeated:
  interpretation_tags:
  use_for_yongsin_decision: false
```

---

## 13. 반응형 정책

```yaml
responsive_policy:
  desktop:
    layout: four_columns_full_width
  tablet:
    layout: four_columns_compact
  mobile:
    layout: horizontal_scroll
    sticky_top_summary: true
    collapsible_detail_panels: true
```

---

## 14. 컴포넌트 목록

```text
- MansePage
- BirthSummaryBar
- TrueSolarTimeInfoCard
- PillarBoard
- PillarColumn
- GanjiTile
- HiddenStemRows
- StructureSummaryPanel
- QuickSummaryBar
- DetailFilterBar
- SinsalPanel
- FiveElementPanel
- TenGodPanel
- StrengthPanel
- GeokgukPanel
- YongsinCandidatePanel
- LuckCyclePanel
```

---

## 15. 구현 금지 사항

```text
1. 시간 모름일 때 시주를 임의 추정하지 말 것.
2. 진태양시 적용 시주 변경을 숨기지 말 것.
3. 신살을 일부만 계산하거나 일부만 반환하지 말 것.
4. 색상만으로 오행을 구분하지 말 것.
5. 모바일에서 4주 구조를 깨뜨리지 말 것.
6. 용신 후보를 UI에서 확정값처럼 표시하지 말 것.
```
