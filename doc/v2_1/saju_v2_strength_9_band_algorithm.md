# 사주서비스 v2 — 신강/신약 9단계 알고리즘 명세서

> 목적: 신강/신약을 이분법이 아니라 0~100 점수와 9단계 구간으로 판정하기 위한 독립 명세서.  
> 원칙: 신강약은 용신 확정이 아니라 용신 후보 산출의 1차 입력값이다.

---

## 1. 9단계 구간

```text
0~11   극신약
12~22  태신약
23~34  신약
35~44  중화신약
45~55  중화
56~65  중화신강
66~77  신강
78~88  태신강
89~100 극신강
```

경계값 ±2점은 borderline으로 표시한다.

---

## 2. 핵심 구성요소

```python
strength_score = (
    0.35 * season_score
  + 0.35 * root_score
  + 0.30 * side_balance_score
  + structure_modifier
)
```

구성:

```text
season_score = 득령
root_score = 득지/통근
side_balance_score = 내 편 vs 반대편 세력
structure_modifier = 합충형파해/공망/병존 등 구조 보정
```

---

## 3. season_score

월령 기준으로 일간 오행의 상태를 평가한다.

```yaml
season_score:
  wang: 90
  xiang: 75
  xiu: 50
  qiu: 35
  si: 20
```

토월은 별도 policy를 사용한다.

```yaml
earth_month_policy:
  진: 습토/봄말/목수잔기
  술: 조토/가을말/금화잔기
  축: 한습토/겨울말/수금잔기
  미: 조열토/여름말/화목잔기
```

---

## 4. root_score

일간이 지지에 뿌리를 두었는지 계산한다.

```yaml
branch_position_weight:
  month: 35
  day: 30
  hour: 18
  year: 12

hidden_stem_root_weight:
  main: 1.00
  middle: 0.60
  residual: 0.35
```

비겁 뿌리:

```python
root += position_weight * hidden_weight * 1.00
```

인성 뿌리:

```python
root += position_weight * hidden_weight * 0.65
```

주의:

```text
득지와 통근은 다르다.
통근은 지장간 뿌리의 존재이고,
득지는 일지/월지 등 핵심 지지가 일간을 직접 지지하는지다.
```

---

## 5. side_balance_score

오행분포/십성분포를 일간 기준 그룹으로 변환한다.

```python
ally_power = peer_power * 1.00 + resource_power * 0.85

pressure_power = (
    output_power * 0.55
  + wealth_power * 0.75
  + officer_power * 1.00
)

side_balance_score = 100 * ally_power / (ally_power + pressure_power)
```

---

## 6. structure_modifier

```yaml
structure_modifier_rules:
  day_master_root_clashed: -4
  only_root_damaged: -6
  strong_peer_duplication: +3
  strong_resource_support: +2
  day_branch_void: -2
  month_branch_void: -2
  transformation_against_day_master: -3
  transformation_supports_day_master: +3
  self_punishment_on_support_root: -2
```

modifier는 과도하게 커지지 않도록 제한한다.

```python
structure_modifier = clamp(structure_modifier, -10, +10)
```

---

## 7. confidence

```python
confidence = (
    0.35 * season_clarity
  + 0.30 * root_clarity
  + 0.20 * side_gap_clarity
  + 0.15 * relation_stability
)
```

신뢰도 낮음 조건:

```text
- 35~65점 중화권
- 경계값 ±2점
- 합화/종격/전왕 후보 존재
- timezone/시주 변경 불확실
- 월지/일지 공망 또는 충으로 핵심 뿌리 손상
```

---

## 8. 출력

```yaml
strength_analysis:
  score:
  band:
  borderline:
  confidence:
  components:
    season_score:
    root_score:
    side_balance_score:
    structure_modifier:
  basis:
    deukryeong:
    deukji:
    deukse:
    tonggeun:
  requires_validation:
  warnings:
```

---

## 9. 용신 후보와 연결

```text
극신약/태신약:
  종격 우선 검사
  종격 아니면 부일간 모델

신약:
  인성/비겁 후보

중화신약/중화/중화신강:
  억부 확정 금지
  조후/통관/검증 비중 증가

신강:
  식상/재성/관성 후보

태신강/극신강:
  전왕/일행득기 우선 검사
```

---

## 10. 구현 금지 사항

```text
1. 신강/신약을 boolean으로 처리하지 말 것.
2. 통근 있음만으로 신강 판정하지 말 것.
3. 오행분포 퍼센트만으로 신강약 확정하지 말 것.
4. 중화권에서 용신을 단정하지 말 것.
5. 종격/전왕 검사 없이 극신약/극신강 용신을 확정하지 말 것.

---

# v2.1 보완 — 중화사주·신왕/신강 분리

## 1. 신왕과 신강 분리

기존 `root_score`가 높으면 신강으로 기울 수 있었으나, v2.1에서는 `신왕`과 `신강`을 분리한다.

```yaml
strength_analysis:
  score:
  band:
  rootedness:
    label: 무근 | 약근 | 보통 | 신왕
    score:
  strong_chart_gate:
    month_or_day_branch_ally:
    another_ally_position_exists:
    passed:
```

규칙:

```text
신왕 = 일간의 뿌리가 튼튼함
신강 = 월지/일지 포함 전체 세력이 일간 편으로 기울어 있음
```

## 2. 신강 최소 조건 게이트

```text
월지 또는 일지 중 하나가 비겁/인성이어야 한다.
나머지 자리 중 하나 이상에도 비겁/인성이 있어야 한다.
이 조건 실패 시 root_score가 높아도 신강 확정 금지.
```

## 3. 중화권 정책

```yaml
neutral_zone_policy:
  bands: [중화신약, 중화, 중화신강]
  auto_yongsin_confirm: false
  require_competing_models: true
  require_calibration: true
```
