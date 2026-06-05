# 사주서비스 v2 — 세력분석 연동 명세서

> 문서 목적: 오행분포 계산 결과를 신강약 9단계, 십성분포, 용신 후보, 조후, 구조 분석과 어떻게 연결할지 정의한다.  
> 전제: 오행분포는 원국 내 계산값이며, 대운·세운은 별도 운 영향 레이어에서 결합한다.

---

## 1. 세력분석 전체 구조

```yaml
force_analysis:
  five_element_analysis:
  ten_god_distribution:
  visible_hidden_analysis:
  rooting_analysis:
  strength_analysis:
  climate_context:
  structure_influence_summary:
```

`force_analysis`는 용신 확정이 아니라, 용신 후보 산출의 입력값이다.

---

## 2. 오행분포와 신강약의 관계

오행분포는 신강약 산출의 일부 근거일 뿐이다.

```text
신강약 = 월령 + 통근/득지 + 내 편/반대편 세력 + 구조 보정
오행분포 = 세력분포 입력값
```

신강약 공식:

```python
strength_score = (
    0.35 * season_score
  + 0.35 * root_score
  + 0.30 * side_balance_score
  + structure_modifier
)
```

오행분포는 주로 `side_balance_score` 계산에 사용한다.

---

## 3. 일간 기준 세력 변환

오행분포를 일간 기준 십성 세력으로 변환한다.

예: 기토 일간

```yaml
day_master: earth

element_to_ten_god_group:
  earth: peer
  fire: resource
  metal: output
  water: wealth
  wood: officer
```

그룹별 의미:

```text
peer = 비겁, 일간 직접 강화
resource = 인성, 일간 생조
output = 식상, 일간 기운 배출
wealth = 재성, 일간이 감당해야 하는 대상
officer = 관살, 일간을 제어/압박
```

---

## 4. ally_power / pressure_power 계산

```python
ally_power = peer_power * 1.00 + resource_power * 0.85

pressure_power = (
    output_power * 0.55
  + wealth_power * 0.75
  + officer_power * 1.00
)
```

가중치 이유:

| 그룹 | 영향 | 가중치 |
|---|---|---:|
| 비겁 | 직접 강화 | 1.00 |
| 인성 | 생조 | 0.85 |
| 식상 | 설기 | 0.55 |
| 재성 | 소모·감당 | 0.75 |
| 관살 | 직접 압박 | 1.00 |

`side_balance_score`:

```python
side_balance_score = 100 * ally_power / max(ally_power + pressure_power, 1e-6)
```

---

## 5. 십성분포와 오행분포의 차이

오행분포와 십성분포는 같은 데이터를 다른 기준으로 본 결과다.

```text
오행분포 = 목화토금수의 물리적/구조적 세력
십성분포 = 일간 기준 역할 분포
```

따라서 출력은 둘 다 필요하다.

```yaml
ten_god_distribution:
  raw:
  hidden_adjusted:
  effective:
  strongest_ten_god:
  missing_ten_gods:
  hidden_only_ten_gods:
```

주의:

```text
없는 십성이 지장간에 있으면 hidden_only로 분류한다.
천간에 없다고 완전히 없는 것으로 해석하지 않는다.
```

---

## 6. visible_hidden_analysis

드러난 기운과 숨어 있는 기운을 분리한다.

```yaml
visible_hidden_analysis:
  visible_elements:
    stems:
    branch_surfaces:
  hidden_elements:
    hidden_stems:
  hidden_only_ten_gods:
  exposed_hidden_stems:
  exposure_score:
```

투간된 지장간은 현실 작동성이 증가한다.

```yaml
exposure_result:
  hidden_stem: 임
  element: water
  exposed_in_stem: true
  exposed_position: none | year | month | hour
  operability_bonus:
```

---

## 7. rooting_analysis

통근 분석은 별도 카드로 제공한다.

```yaml
rooting_analysis:
  heavenly_stems:
    year_stem:
      stem:
      ten_god:
      rooted:
      roots:
      root_strength:
    month_stem:
    day_stem:
    hour_stem:

  day_master_root:
    direct_root_score:
    resource_root_score:
    damaged_roots:
    final_root_score:
```

주의:

```text
통근이 있어도 신강일 필요는 없다.
통근은 뿌리의 존재이고, 신강약은 월령·세력·압박까지 포함한 종합 판정이다.
```

---

## 8. 신강/신약 9단계 출력

```yaml
strength_analysis:
  score:
  band:
  confidence:
  borderline:
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
```

9단계:

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

---

## 9. 오행 과다/부족과 용신 후보의 연결

오행 과다/부족은 용신 후보 산출에 들어가지만, 직접 용신이 아니다.

```text
부족 오행:
  보완 후보가 될 수 있음
  하지만 일간을 극하면 기신일 수 있음

과다 오행:
  기신 후보가 될 수 있음
  하지만 전왕/종격이면 용신 방향일 수 있음
```

예시:

```text
기토 일간에서 목이 부족하더라도,
신약한 기토를 목 관성이 극하면 목은 기신 후보가 될 수 있다.
```

---

## 10. 조후와 세력분석 연결

조후는 `climate_context`로 제공하고 용신 후보 산출 단계에서 참조한다.

```yaml
climate_context:
  coldness_score:
  heat_score:
  dryness_score:
  dampness_score:
  johu_candidates:
  johu_risk:
```

정책:

```text
조후는 effective_force_distribution을 직접 대량 수정하지 않는다.
조후용신 모델에서 별도 후보로 평가한다.
```

---

## 11. 구조 분석과 세력분석 연결

합충형파해, 공망, 병존, 간여지동은 세력분석에 다음 영향을 준다.

```yaml
structure_influence_summary:
  activated_elements:
  weakened_roots:
  transformed_elements:
  volatility_score:
  stability_score:
  palace_affected:
```

사용처:

```text
1. effective_force_distribution 보정
2. strength_analysis structure_modifier
3. yongsin_stability 계산
4. calibration period selection
```

---

## 12. 용신 후보 모델로 전달하는 입력

`yongsin_analysis`는 아래 데이터를 입력받는다.

```yaml
yongsin_input:
  day_master:
  five_element_effective_distribution:
  ten_god_effective_distribution:
  strength_analysis:
  rooting_analysis:
  climate_context:
  special_structure_checks:
  structure_influence_summary:
  geokguk:
```

---

## 13. 모델별 사용 방식

### 13.1 부일간/신약 보조 모델

사용 데이터:

```text
strength band
ally_power
pressure_power
day_master_root
resource_power
officer/wealth excess
```

결과:

```text
신약이면 인성/비겁 후보
단, 종격 가능성 먼저 검사
```

### 13.2 일반 신강 억부 모델

사용 데이터:

```text
strength band
excessive peer/resource
output/wealth/officer availability
```

결과:

```text
신강이면 식상/재성/관성 후보
단, 전왕 가능성 먼저 검사
```

### 13.3 조후 모델

사용 데이터:

```text
climate_context
month_branch
temperature/moisture axis
```

결과:

```text
한난조습 보정 후보
단독 확정 금지
```

### 13.4 통관 모델

사용 데이터:

```text
conflict_pair
bridge_element
relation severity
```

결과:

```text
오행 충돌을 생의 흐름으로 전환하는 후보
```

### 13.5 고립/병약 모델

사용 데이터:

```text
isolated_elements
damaged_roots
health_risk
```

결과:

```text
최종 용신과 분리 가능한 건강/리스크 보완 요소
```

---

## 14. 최종 force_analysis 출력 예시

```json
{
  "force_analysis": {
    "five_element_analysis": {
      "effective_force_distribution": {
        "percent": {
          "wood": 4.1,
          "fire": 19.7,
          "earth": 19.8,
          "metal": 16.2,
          "water": 40.2
        }
      }
    },
    "ten_god_distribution": {
      "effective": {
        "peer": 11.5,
        "resource": 22.0,
        "output": 18.1,
        "wealth": 43.7,
        "officer": 4.6
      },
      "strongest": "wealth",
      "missing_visible": ["식신", "편재", "편관"]
    },
    "rooting_analysis": {
      "day_master_root": {
        "final_root_score": 42,
        "label": "partial"
      }
    },
    "strength_analysis": {
      "score": 32.6,
      "band": "신약",
      "confidence": 0.68,
      "requires_validation": true
    },
    "climate_context": {
      "season_group": "winter",
      "coldness_score": 0.82,
      "dampness_score": 0.78
    }
  }
}
```

---

## 15. 구현 금지 사항

```text
1. 오행분포 퍼센트만으로 신강약을 확정하지 말 것.
2. 십성분포와 오행분포를 하나로 합쳐버리지 말 것.
3. 조후를 오행분포에 직접 강하게 섞지 말 것.
4. 통근이 있다는 이유만으로 신강 판정하지 말 것.
5. 부족 오행을 바로 용신으로 올리지 말 것.
6. 세력분석에 대운/세운을 섞지 말 것.
```

---

## 16. Codex 작업 단위

```text
1. force_analysis schema 작성
2. element_to_ten_god_group 변환 구현
3. ten_god_distribution 구현
4. visible_hidden_analysis 구현
5. rooting_analysis 구현
6. strength_analysis 입력 연결
7. climate_context 연결
8. yongsin_input DTO 작성
9. force_analysis 단위 테스트 작성
