# 사주서비스 v2 — 용신 후보 산출 알고리즘 명세서

> 목적: 용신·희신·기신·구신을 최초부터 확정하지 않고, 복수 후보와 신뢰도/검증 필요 여부를 산출하는 명세서.  
> 원칙: 용신은 계산값이 아니라 검증 가능한 전략 모델이다.

---

## 1. 입력

```yaml
yongsin_input:
  pillars:
  five_element_analysis:
  ten_god_analysis:
  strength_analysis:
  structure_analysis:
  geokguk_analysis:
  climate_context:
```

---

## 2. 출력

```yaml
yongsin_analysis:
  status: candidate | calibrated | uncertain
  special_case_checks:
  candidate_models:
  useful_candidates:
  unfavorable_candidates:
  final:
    yongsin:
    heesin:
    gisin:
    gusin:
    hansin:
    confidence:
  requires_validation:
```

초기 계산 직후 `status`는 기본적으로 `candidate`다.

---

## 3. 특수 케이스 우선순위

```text
1. 시간 경계/계산 불안정
2. 합화/화기격 후보
3. 전왕/일행득기 후보
4. 종격 후보
5. 통관 필요 구조
6. 고립/병약/건강 리스크
7. 조후 후보
8. 부일간/신약 보조
9. 일반 억부
10. 격국 참고
```

---

## 4. 모델별 규칙

### 4.1 부일간/신약 보조 모델

조건:

```text
신약 이하
종격 조건 미충족
일간을 돕는 인성/비겁 필요
```

후보:

```text
용신 후보: 비겁 또는 인성
희신 후보: 용신을 생조하거나 보조하는 오행
기신 후보: 관살/재성/식상 중 압박이 큰 그룹
```

### 4.2 일반 신강 억부 모델

조건:

```text
신강 이상
전왕 조건 미충족
```

후보:

```text
용신 후보: 식상, 재성, 관성
기신 후보: 비겁, 인성 과다
```

### 4.3 조후 모델

조건:

```text
한난조습 불균형
중화권 또는 억부 후보 불명확
```

후보:

```text
추움/습함: 화, 조토 등
더움/건조: 수, 습윤 보완 등
```

주의:

```text
조후 단독 확정 금지.
```

### 4.4 통관 모델

조건:

```text
강한 두 오행이 극단적으로 대치
중간에서 생의 흐름을 만드는 오행 필요
```

예:

```yaml
wood_vs_earth:
  bridge: fire
earth_vs_water:
  bridge: metal
water_vs_fire:
  bridge: wood
fire_vs_metal:
  bridge: earth
metal_vs_wood:
  bridge: water
```

### 4.5 고립/병약 모델

조건:

```text
특정 오행/십성이 고립, 손상, 무근
```

정책:

```text
최종 용신과 분리 가능.
health_support 또는 risk_support로 표시.
```

### 4.6 종격 모델

조건:

```text
극신약
일간을 돕는 뿌리/인성이 거의 없음
특정 세력을 따르는 구조
```

정책:

```text
따르는 세력을 용신 방향으로 본다.
일간을 억지로 돕는 인성/비겁은 기신일 수 있다.
```

### 4.7 전왕/일행득기 모델

조건:

```text
특정 오행이 압도적
월령/지지 흐름이 한 방향
반대 오행이 무력
```

정책:

```text
왕한 흐름을 순행시키는 오행을 후보로 본다.
정면으로 극하는 오행은 기신 후보가 될 수 있다.
```

---

## 5. 후보 통합

각 모델은 다음 형식으로 후보를 반환한다.

```yaml
candidate_model:
  model:
  yongsin:
  heesin:
  gisin:
  gusin:
  hansin:
  confidence:
  reason:
  requires_validation:
```

통합 점수:

```python
candidate_score = (
    model_confidence * 0.45
  + strength_alignment * 0.20
  + structure_alignment * 0.15
  + climate_alignment * 0.10
  + geokguk_alignment * 0.05
  + stability_score * 0.05
)
```

---

## 6. 후보 개수

```yaml
useful_candidates:
  max_count: 2

unfavorable_candidates:
  max_count: 2
```

후보 간 점수 차이가 작으면 둘 다 유지한다.

```text
top1 - top2 < 0.12이면 경쟁 후보로 유지
```

---

## 7. 확정 정책

계산만으로 확정하지 않는다.

```yaml
decision_policy:
  initial_status: candidate
  require_user_validation: true
```

예외적으로 확정에 가까운 경우:

```text
- 여러 모델이 같은 용신을 지목
- 신강약 confidence가 높음
- 특수격 후보 없음
- 구조 안정도 높음
```

그래도 내부 status는 `probable`까지만 허용하고, `calibrated`는 사용자 검증 후에만 사용한다.

---

## 8. 출력 예시

```json
{
  "yongsin_analysis": {
    "status": "candidate",
    "candidate_models": [
      {
        "model": "support_day_master",
        "label": "부일간형",
        "yongsin": "토",
        "heesin": "화",
        "gisin": "목",
        "gusin": "수",
        "hansin": "금",
        "confidence": 0.63,
        "requires_validation": true,
        "reason": [
          "신약 판정",
          "재성 수 세력 우세",
          "비겁 토로 일간 직접 보강 필요"
        ]
      }
    ],
    "useful_candidates": [
      {"element": "토", "score": 0.63},
      {"element": "화", "score": 0.48}
    ],
    "unfavorable_candidates": [
      {"element": "수", "score": 0.71},
      {"element": "목", "score": 0.55}
    ]
  }
}
```

---

## 9. 구현 금지 사항

```text
1. 부족 오행을 자동 용신 처리하지 말 것.
2. 신약이면 무조건 인성만 용신 처리하지 말 것.
3. 신강이면 무조건 관성만 용신 처리하지 말 것.
4. 종격/전왕 검사 없이 극단 명식을 일반 억부로 처리하지 말 것.
5. 조후용신을 단독 확정하지 말 것.
6. 사용자 검증 전 calibrated 상태로 만들지 말 것.

---

# v2.1 보완 — 신약 억부용신 3분기와 중화사주

## 1. 신약 억부용신 3분기

특수격이 아닌 신약/중화신약 명식의 억부용신 후보는 비겁/인성/식상 중 하나로 분기한다.

```yaml
weak_chart_eokbu_submodels:
  output_as_yongsin:
    condition:
      - day_master_rootedness in [신왕, strong]
      - officer_group_strong
    yongsin_group: output
  resource_as_yongsin:
    condition:
      - day_master_has_root
      - wealth_group_strong or output_group_strong
    yongsin_group: resource
    heesin_group: officer
  peer_as_yongsin:
    condition:
      - not output_as_yongsin
      - not resource_as_yongsin
    yongsin_group: peer
```

## 2. 중화신약 + 신왕 모델

```yaml
rooted_but_not_strong_model:
  conditions:
    - day_master_rootedness in [신왕, strong]
    - strong_chart_gate_passed == false
    - strength_band in [중화신약, 중화]
  requires_validation: true
```

## 3. 용신운 사건 평가

용신운이라도 병·사고·갈등은 생길 수 있다. 검증 루프에서는 사건 발생 여부가 아니라 `회복 속도`, `수습 여부`, `최종 결과`까지 평가한다.
