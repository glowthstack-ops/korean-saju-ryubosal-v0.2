# near-tie 대안성 감사 (CAL-ROLE-MARGIN-CENSUS / MC-B)

```yaml
verdict:
  - RUNNER_UP_REPLAY_COMPLETED_FOR_ALL_NEAR_TIE_CASES
  - ALTERNATIVE_TAXONOMY_STRUCTURALLY_DEGENERATE
  - ROLE_MAP_DIFFERENCE_HAS_NO_DISCRIMINATING_POWER
  - REPLACEMENT_DISCRIMINATOR_REQUIRED
  - MC_C_STILL_BLOCKED
```

near-tie 3건을 01c1 규칙으로 재생했고 전부 성공했다. 그런데 **분류 체계 자체가
성립하지 않는다.**

---

## 1. 계획한 분류가 퇴화한다

MC-B 는 near-tie 를 셋으로 나눌 계획이었다.

```
NEAR_TIE_ROLE_MAP_ALTERNATIVE          역할표가 실제로 다름
NEAR_TIE_PROVENANCE_ONLY_ALTERNATIVE   역할표는 같고 실현 경로만 다름
NEAR_TIE_SEMANTICALLY_EQUIVALENT       역할표까지 같음
```

**뒤의 둘은 도달할 수 없다.** 표본이 작아서가 아니라 구조 때문이다.

```python
useful: dict[str, tuple[float, str, str]] = {}
...
table[el] = (score, model, role)      # ← 오행이 키다
```

후보표가 오행 키 dict 이므로 같은 오행이 두 번 오를 수 없고, 상위 두 후보는 **언제나 다른
오행**이다. 역할표의 `yongsin` 칸은 확정된 오행 그 자체이므로, 오행이 다르면 역할표가
다를 수밖에 없다.

MC-A 의 `same_element_pairs: 0` 도 관측이 아니라 이 구조의 귀결이었다.

---

## 2. 실측 — 13/13 이 role-map alternative

near-tie 만이 아니라 **전 구간**을 재생해 대조했다.

```
      margin   chart              pair    primary origin   alternate origin   class
  0.002860 *   1990-05-15 09:30   水>金    complete_model   complete_model     ROLE_MAP_ALTERNATIVE
  0.010000 *   1992-07-20 14:00   金>水    static_fallback  static_fallback    ROLE_MAP_ALTERNATIVE
  0.010825 *   1987-08-05 21:00   土>水    complete_model   static_fallback    ROLE_MAP_ALTERNATIVE
  0.021741     1988-03-05 10:30   木>金    complete_model   static_fallback    ROLE_MAP_ALTERNATIVE
  0.041715     1980-11-22 09:40   土>火    complete_model   complete_model     ROLE_MAP_ALTERNATIVE
  0.044235     1980-11-22 09:08   土>火    complete_model   complete_model     ROLE_MAP_ALTERNATIVE
  0.051000     1990-03-03 10:00   木>金    static_fallback  static_fallback    ROLE_MAP_ALTERNATIVE
  0.051570     1985-04-18 16:00   火>木    support_special  complete_model     ROLE_MAP_ALTERNATIVE
  0.053730     1990-03-15 10:00   火>土    complete_model   complete_model     ROLE_MAP_ALTERNATIVE
  0.185000     1990-05-05 13:30   木>土    static_fallback  static_fallback    ROLE_MAP_ALTERNATIVE
  0.213910     1985-05-05 14:00   木>金    complete_model   static_fallback    ROLE_MAP_ALTERNATIVE
  0.775000     1985-03-05 12:00   木>火    static_fallback  static_fallback    ROLE_MAP_ALTERNATIVE
  0.800000     1985-03-15 14:30   土>金    static_fallback  static_fallback    ROLE_MAP_ALTERNATIVE

  * = near-tie (raw margin <= 0.02)
```

```yaml
role_map_alternative: 13 / 13
near_tie_subset:       3 / 3
discriminating_power:  NONE
```

margin `0.80` 짜리도 role-map alternative 다. **"역할표가 달라지는가" 로는 아무것도
걸러내지 못한다.** 이 판별자로 임계값을 정당화하면 항상 참인 조건을 근거처럼 쓰게 된다.

---

## 3. near-tie 3건의 실현 경로

분류는 무의미해도 **provenance 자체는 실제 정보다.**

### A — margin 0.00286 · 水 > 金

```
primary    水  eokbu_normal        조회 성공 · 완비   → 승격   conf 0.5143
           水용 / 木희 / 土기 / 金구 / 火한            COMPLETE_MODEL_ROLE_MAP
alternate  金  support_day_master  조회 성공 · 완비   → 승격   conf 0.5
           金용 / 土희 / 火기 / 木구 / 水한            COMPLETE_MODEL_ROLE_MAP
```

**양쪽 다 완비 모델맵이다.** 폴백이 전혀 개입하지 않은, 두 온전한 모델의 경쟁이다.

### B — margin 0.01 · 金 > 水

```
primary    金  pattern_sangsin  조회 성공 · 부분맵 → 폴백   conf 0.85
           金용 / 土희 / 火기 / 木구 / 水한            STATIC_FALLBACK_ROLE_MAP
alternate  水  johu             조회 성공 · 부분맵 → 폴백   conf 0.4
           水용 / 金희 / 土기 / 火구 / 木한            STATIC_FALLBACK_ROLE_MAP
```

**primary 조차 완비 모델맵이 아니다.** 양쪽 다 정적 폴백이며 직접 원인은
`STATIC_FALLBACK_FROM_INCOMPLETE_MODEL_MAP` 이다.

### C — margin 0.010825 · 土 > 水

```
primary    土  eokbu_normal     조회 성공 · 완비   → 승격   conf 0.6033
           土용 / 金희 / 木기 / 火구 / 水한            COMPLETE_MODEL_ROLE_MAP
alternate  水  pattern_sangsin  조회 성공 · 부분맵 → 폴백   conf 0.7
           水용 / 金희 / 土기 / 火구 / 木한            STATIC_FALLBACK_ROLE_MAP
```

`STATIC_FALLBACK_FROM_INCOMPLETE_MODEL_MAP`. 01c1-b1 결과를 인용하지 않고 같은
스키마로 다시 재생해 얻었다.

### 조합

```
승격 / 승격       A · 1980-11-22 두 건 · 1990-03-15
폴백 / 폴백       B · 1990-03-03 · 1990-05-05 · 1985-03-05 · 1985-03-15
승격 / 폴백       C · 1988-03-05 · 1985-05-05
특수분기 / 승격   1985-04-18
```

`STATIC_FALLBACK_FROM_MODEL_LOOKUP_MISS` 와
`STATIC_FALLBACK_FROM_UNSUPPORTED_SPECIAL_ROLE` 는 이 코호트에 없다.

---

## 4. 그래서 대체 계약이 답해야 하는 질문이 바뀐다

원래 질문은 "어떤 차이를 실질적인 대안으로 보존할 것인가" 였고, MC-B 는 그 판별자로
역할표 차이를 쓰려 했다. 그 판별자는 못 쓴다.

남은 후보는 최소한 다음이며 **아직 아무것도 고르지 않았다.**

```
① 하류 영향   두 역할표가 P2 작동성·P3 투영에서 실제로 다른 결론을 내는가
② 실현 품질   alternate 가 완비 모델맵인가 정적 폴백인가
              (A 는 양쪽 완비, C 는 alternate 가 폴백 — 대안의 무게가 다르다)
③ 점수 근접   현재의 margin 임계값. MC-A 에서 밀도 근거 없음이 확인됐다
```

②는 이 코호트에서 실제로 갈린다 — near-tie 3건 중 A 만 양쪽 완비이고, B 는 양쪽 폴백,
C 는 alternate 만 폴백이다. 다만 이것을 판별자로 쓸지는 명리적 판단이 필요하다.

---

## 5. 이 감사가 말하지 못하는 것

```yaml
which_discriminator_is_correct: NOT_DETERMINED
threshold_selection:            NOT_IDENTIFIED
population_expansion:           STILL_REQUIRED
```

13 independent charts 로는 어떤 판별자를 써도 비율이 개별 사례 하나에 좌우된다.
MC-C 는 계속 열지 않는다.

---

## 6. 회귀로 고정한 것

`backend/tests/unit/test_near_tie_alternative_degeneracy.py`

```
후보표가 오행 키 dict 이다
상위 두 후보의 오행이 겹치지 않는다
역할표의 용신 칸은 확정된 오행 그 자체다
margin 과 무관하게 전건 역할표가 다르다
SEMANTICALLY_EQUIVALENT·PROVENANCE_ONLY 로 분류되는 사례가 없다
실현 경로 조합은 3종 이상이고 primary 도 완비 모델맵만 나오지 않는다
```

**분류 결과가 아니라 분류가 성립하지 않는다는 사실**을 고정한다. 나중에 후보표가
오행 키가 아니게 되면 이 회귀가 먼저 깨져 재검토를 강제한다.
