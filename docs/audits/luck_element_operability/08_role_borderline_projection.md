# 경계 명식 역할 후보 투영 (CAL-ROLE-BORDERLINE-01a)

```yaml
measurement: PASS
production_nonregression: PASS
role_candidate_prevalence: MEASURED
projection_materiality: PERVASIVE_AXIS_DIVERGENCE
canonical_role_decision: NOT_YET_SELECTED
p3_role_consumption_contract: NOT_YET_SELECTED

overall: ROLE_BORDERLINE_MEASUREMENT_COMPLETE
```

**어느 역할표가 맞는지 판정하지 않는다.** 이 감사의 결과는 역할 정답이 아니라 **역할
불확실성의 영향도**다.

---

## 1. 측정 방식

P2-1 profile 과 P2-2 evaluation 을 **한 번만** 계산하고 P2-3 만 두 번 실행했다. 후보별로
프로필이나 등급을 다시 계산하면 역할 선택이 작동성 평가에 역으로 침투한다.

```
invariant_breaks   0
```

두 후보에서 `operability_status` 와 `operability_anchor` 가 모두 같음을 target 마다 확인했다.
달라진 것은 `canonical_role` 과 활성 축뿐이다.

---

## 2. 사례 A 결과

```
1987-08-05 21:00 서울 · 丁卯 丁未 丙戌 戊戌
기간 3 (2024·2026·2031) · target 12
```

```
차이 있는 target        9 / 12
  favorable_adverse_flip   3     ← 유리 ↔ 불리 직접 반전
  adverse_neutral_shift    4
  favorable_neutral_shift  2

역할 전환
  용신 → 기신   3
  기신 → 한신   4
  한신 → 용신   2

기간 signature
  polarity_flip_present            2 / 3
  neutral_reclassification_only    1 / 3
```

### 반전이 가장 나쁜 자리에 걸렸다

```
flip_by_operability   fully_operable 3
```

세 건의 유리↔불리 반전이 **전부 `FULLY_OPERABLE`** 이다. 작동성이 낮은 자리에서 반전됐다면
영향이 제한적이라고 볼 수 있지만, 실제로는 가장 강하게 작동하는 자리에서 축이 뒤집힌다.

```
土   ENGINE_NATIVE 용신 → PATTERN 후보 기신
     FULLY_OPERABLE 에서 favorable → adverse
```

`PERVASIVE_AXIS_DIVERGENCE` 로 분류한 근거다(3기간 중 2기간에서 반복).

이 판정은 **어느 후보가 맞다는 뜻이 아니다.** 의미는 하나다.

> P3 가 단일 역할표만 받으면 후보 선택에 따라 결과 **방향**이 실질적으로 달라진다.

---

## 3. existing-fixture borderline census

```
고유 명식(성별 포함)        26
requires_validation         26   (전건)
복수 후보 오행 보유          26   (전건)
축 점수 margin < 0.02        8
최상위 축   eokbu 14 · pattern 8 · special 4
```

### `requires_validation` 은 판별력이 없다

**26/26 이 전건 True 다.** 이 플래그로는 "이 명식이 경계인가" 를 가릴 수 없다. 경계 판별에
쓰려면 축 점수 margin 같은 연속값이 필요하며, `margin < 0.02` 기준으로는 8/26(30.8%)이다.

복수 후보 오행도 전건이라 마찬가지다 — 후보가 여럿이라는 사실 자체는 흔하고, 문제는 **그
후보들이 서로 다른 축으로 보내는가** 다.

이 수치를 실제 사용자 비율로 읽지 않는다. 기존 fixture 는 경계·회귀 사례가 과대표집돼
있다(`existing-fixture borderline census`).

---

## 4. 하지 않은 것

```
억부 土와 pattern 水 중 무엇이 정답인지 판정      하지 않음
과거 사건으로 후보 자동 선택                      하지 않음
두 후보 activation 합산·평균                     하지 않음
후보 간 cross-axis order key 비교                하지 않음
P3 사건 점수 생성                                하지 않음
사용자 동시 노출                                 하지 않음
production schema·callsite 변경                  없음
```

특히 **"현재 운에서 水가 강하게 작동하므로 水 용신 후보를 채택한다"** 류의 선택은 원국 역할
후보와 기간 작동성 사이에 누수를 만들므로 배제했다.

`SOURCE_FIXTURE` 는 감사 하네스의 명시적 후보 역할표로만 썼고 production wrapper 에 넣지
않았다.

---

## 5. 이 결과가 요구하는 것

`PERVASIVE_AXIS_DIVERGENCE` 이므로 지시된 분기 중 세 번째에 해당한다 — **P3 전에 후보 보존
계약이 필요하다.**

```
production canonical role   ENGINE_NATIVE 유지
alternate role candidate    구조화해서 보존
P3 primary output           canonical 만 소비
P3 shadow sensitivity       alternate 도 별도 투영
두 결과 합산                금지
사용자 동시 노출             초기에는 금지
```

즉 처음부터 혼합 풀이로 가지 않고 `canonical interpretation` 과
`alternate-candidate sensitivity` 를 분리한다.

### 구조축 tie-break 는 지금 검토 대상이 아니다

margin 이 작다는 이유만으로 새 tie-break 를 만들면 안 된다. 명리적으로 독립적인 구조 근거와
후보 점수와 중복되지 않는 판정 축이 먼저 필요하며, 특정 기간의 운이나 실제 사건을 쓰지 않아야
한다. 현재 census 로는 그 조건이 갖춰졌는지 알 수 없다.

---

## 재현

```bash
cd backend
python scripts/audits/measure_role_borderline_projection.py \
  --out artifacts/audits/luck_element_operability
```

---

## 6. 다음

```
CAL-ROLE-BORDERLINE-01b   후보 보존 계약 선택 (단일 canonical / 후보 보존 / tie-break)
→ 계약 구현·종료 감사
→ P3 이벤트·풀이 연결
```
