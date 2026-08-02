# 활성도 해상도 후보 비교 (CAL-ACTIVATION-RESOLUTION-01a)

```yaml
candidate_a:
  discrimination: PASS
  wording_risk: HIGH
  production_fit: REVIEW

candidate_b:
  discrimination: PASS
  double_count_risk: REVIEW
  production_fit: REVIEW

candidate_c:
  discrimination: PASS
  ordering_policy_required: true
  production_fit: REVIEW

overall:
  verdict: ACTIVATION_RESOLUTION_MEASUREMENT_COMPLETE
  production_choice: NOT_YET_SELECTED
```

**production 변경 0.** `ActivationLevel`·`RoleActivationResult`·P2-3 매핑·직렬화 모두 그대로다.
후보는 `scripts/audits/_activation_resolution_candidates.py` 의 별도 타입으로만 투영했다.

후보 A 를 빼면 "등급 자체를 나누는 방식" 과 "기존 등급에 보조 해상도를 붙이는 방식" 의 비교가
불가능해진다. 그렇다고 production enum 을 먼저 확장하면 measurement-only 원칙을 어긴다.

---

## 1. 문제

`CAL-ROOT-DEPTH-01` 이 52 target 을 `FULLY_OPERABLE → OPERABLE` 로 옮겼지만 P2-3 매핑이
두 등급을 모두 `HIGH` 로 보내 **P3 입력은 달라지지 않았다**(activation_changed 0).

```
operability   0.90 → 0.75
activation    HIGH → HIGH
```

---

## 2. 모집단

```
평가 target                312
root-depth migrated         52
FULLY vs OPERABLE 쌍      3107   같은 역할·같은 축에서 두 등급이 만나는 쌍
```

01a~01d 와 같은 78입력·312 target 이다.

---

## 3. 후보

세 후보를 **같은 구조**로 투영했다. 형태가 다르면 차이가 정책 탓인지 표현 탓인지 알 수 없다.

```
A  등급 세분        FULLY → VERY_HIGH (감사 전용 밴드)
B  anchor 병행      등급 유지, P2-2 의 operability_anchor 를 그대로 소비
C  자격 태그        등급 유지, HIGH 구간에만 FULL / STANDARD
```

`VERY_HIGH` 는 **후보 A 식별용 실험 라벨**이다. 제품 용어도, 사용자 노출 enum 후보도 아니다.
B 는 새 수치를 만들지 않는다 — 이미 P2-2 에 있는 값을 읽는다. C 는 첫 측정에서 HIGH 구간에만
태그를 붙인다(다른 등급까지 넓히면 비교 범위가 불필요하게 커진다).

`structural_tension` 은 변경하지 않았다. 활성도 해상도와 긴장도 해상도를 동시에 바꾸면 원인을
분리할 수 없다.

---

## 4. 결과

```
                              A      B      C
52건 구분                     52     52     52
FULLY vs OPERABLE 쌍 구분   3107   3107   3107
남은 동점 쌍                    0      0      0
activation level 변경         157      0      0
```

**세 후보 모두 구분력은 동일하다.** 52건과 3107쌍을 전부 가른다. 차이는 구분 여부가 아니라
**무엇을 대가로 치르는가** 다.

A 만 활성도 등급 자체를 157건에서 바꾼다(`FULLY` 인 모든 target). B·C 는 0건이다.

### 후보 A 의 `VERY_HIGH` 분포

```
adverse       64
favorable     51
mitigation    51
neutral       42
```

유리 축(51+51)보다 **불리 축(64)이 더 많다.**

---

## 5. 표현 위험

### A — 높음

```
GI/GU + FULLY   → adverse VERY_HIGH   64건
HAN + FULLY     → neutral VERY_HIGH   42건
```

좋은 신호만 강해지는 것이 아니다. 불리 역할에도 같은 강도가 적용되어 "매우 강한 불리함" 처럼
과장될 위험이 있고, 실측에서 그쪽이 더 많다. `neutral VERY_HIGH` 는 사용자 문구로도 어색하다.

audit band 가 내부적으로 유효하다는 것이 사용자 노출 enum 으로 적합하다는 뜻은 아니다.
새 최상급 표현을 만들어야 하고, 유리·불리 양쪽의 단정 강도가 함께 올라간다.

### B — 낮음 (단 이중 가중 위험)

기존 표현이 그대로다. 수치를 사용자에게 노출하지 않으면 문구 위험은 낮다.

다만 `activation_anchor` 와 `operability_anchor` 는 **독립 증거가 아니라 같은 P2 상태의 두
표현**이다. P3 가 둘을 곱하거나 더하면 같은 것을 두 번 센다.

```
금지   HIGH 0.75 + operability 0.90 → 두 번 가산
```

소비 계약을 셋 중 하나로 제한해야 한다: 동점 해소 전용 / 등급 내부 세부 순서 전용 /
풀이 qualifier 선택 전용.

### C — 낮음

기존 표현이 그대로이고 "충분히 작동 / 일반적으로 작동" 같은 제한적 설명이 가능하다.

다만 **태그를 붙였다고 순서가 생기지는 않는다.** 표현상 구분(`representationally_distinct`)과
정렬 가능성은 다르며, C 는 `FULL > STANDARD` 우선순위를 별도로 정의해야 한다.

---

## 6. 비교표

| 기준 | A | B | C |
|---|---:|---:|---:|
| 52건 구분 | PASS | PASS | PASS |
| production schema 변경 | 큼 | 없음/작음 | 중간 |
| 기존 사용자 표현 유지 | 어려움 | 가능 | 가능 |
| 정렬 정책 명확성 | 높음 | 높음 | 추가 정책 필요 |
| 이중 가중 위험 | 낮음 | **높음** | 낮음 |
| 불리 신호 과장 위험 | **높음** | 낮음 | 낮음 |
| 설명 가능성 | 보통 | 낮음~보통 | 높음 |

이 표만으로 production 후보를 확정하지 않는다.

---

## 7. 측정하지 않은 것

```
실제 사건 점수 공식        만들지 않음 — P3 가 아직 없다
P3 후보 순위 변화 실측      불가 (위와 같은 이유)
structural_tension 해상도  이번 범위 밖
사용자 문구 실사용 검증     별도 감수 필요
```

정렬은 "쌍이 구분되는가" 로만 쟀다. 임의의 점수 공식을 만들면 그 공식의 성질을 재게 된다.

---

## 재현

```bash
cd backend
python scripts/audits/measure_luck_element_operability_shadow.py \
  --out artifacts/audits/luck_element_operability \
  --ablation activation-resolution-candidates-v1
```

옵션 없이 실행하면 기존 분포 요약이 그대로 나온다(확인함). 후보 투영은 `--ablation` 지정 시에만
생성된다.

`scripts/audits/_activation_resolution_candidates.py` 는 production 타입을 읽되, production
코드는 이 모듈을 import 하지 않는다.
