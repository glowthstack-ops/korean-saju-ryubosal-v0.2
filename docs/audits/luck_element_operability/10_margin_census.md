# 용신 결정 margin 분포 감사 (CAL-ROLE-MARGIN-CENSUS / MC-A)

```yaml
verdict:
  - INDEPENDENT_SAMPLE_UNIT_CORRECTED
  - GENDER_DUPLICATION_EXCLUDED
  - REFERENCE_DATE_DUPLICATION_EXCLUDED
  - MARGIN_DISTRIBUTION_MEASURED
  - THRESHOLD_0_02_NOT_DENSITY_DERIVED
  - THRESHOLD_0_02_OPERATIONALLY_VALID_BUT_NOT_IDENTIFIED
  - SAMPLE_SIZE_INSUFFICIENT_FOR_THRESHOLD_SELECTION
  - MC_C_BLOCKED_PENDING_POPULATION_EXPANSION
```

`0.02` 를 틀린 값으로 볼 근거는 없다. 다만 **데이터가 지지한 최적값도 아니다** —
legacy operational cutoff 로만 유지하고 `empirically calibrated` 라는 의미를 붙이지 않는다.

production 을 바꾸지 않았다. resolver 그대로 돌리고 점수·선택·출력을 읽기만 했다.
runner-up 강제 재생은 MC-B 이며 여기서는 하지 않았다.

재현: `python scripts/audits/measure_role_margin_census.py --out var/audit/role_margin_census`

---

## 1. 모집단 — N 은 26 이 아니라 13 이다

```yaml
population_rows:          26      # 13 명식 × 남녀
charts:                   13
gender_invariant_charts:  13      # 13/13
independent_samples:      13
```

**성별은 원국 용신 판정을 바꾸지 않는다.** 13건 전부 남녀의 raw margin·용신·선택
모델·실현 출처가 같았다. 성별 행 두 개는 독립 표본이 아니라 **같은 관측의 반복**이다.
26으로 세면 표본이 두 배로 부풀어 임계값 판단이 왜곡된다.

표기는 다음으로 고정한다.

```
26 evaluated gender rows from 13 independent charts;
effective independent sample size = 13
```

`role_candidates.py` 가 "26 표본" 이라고 적어 둔 것도 같은 이유로 과대 표기였고 함께
고쳤다(문구만 — 계산·선택 불변).

기준일도 곱하지 않았다 — 용신 판정은 원국만 쓰므로 `2024-06-15 / 2026-07-27 /
2031-03-01` 이 같은 결과를 낸다(실측). 곱하면 같은 행이 3번 들어간다.

모집단은 `measure_luck_element_operability_shadow` 와 **같은 픽스처**다. 무작위 생성을
넣지 않았다 — 코호트가 달라지면 이전 측정과 비교할 수 없다.

---

## 2. 분포

```
=0              0
(0, 0.005]      1
(0.005, 0.01]   1
(0.01, 0.02]    1
(0.02, 0.03]    1
(0.03, 0.05]    2
(0.05, 0.10]    3
> 0.10          4
```

```yaml
exact_ties:         0     # raw margin == 0
display_ties:       0     # raw > 0 인데 표시 점수가 같음
same_element_pairs: 0     # top1·top2 오행이 같은 경우
same_model_pairs:   2     # top1·top2 를 같은 model_type 이 만든 경우
```

정확한 동점도, 반올림 동점도 없다. 두 후보의 오행이 같은 경우도 없다 — 즉 이 코호트의
runner-up 은 **전부 다른 오행**이다.

### 누적

```
<= 0.01   2 / 13   (15.4%)
<= 0.02   3 / 13   (23.1%)
<= 0.03   4 / 13   (30.8%)
<= 0.05   6 / 13   (46.2%)
```

---

## 3. 0.02 는 변곡점이 아니다

raw margin 오름차순(13건 전부):

```
0.002860   1990-05-15 09:30   水 > 金   top2 support_day_master
0.010000   1992-07-20 14:00   金 > 水   top2 johu
0.010825   1987-08-05 21:00   土 > 水   top2 pattern_sangsin
───────────────────────────────────  ← 0.02 는 이 간격 안에 있다 (폭 0.010916)
0.021741   1988-03-05 10:30   木 > 金   top2 officer_controls_peer
0.041715   1980-11-22 09:40   土 > 火   top2 resource_as_yongsin
0.044235   1980-11-22 09:08   土 > 火   top2 resource_as_yongsin
0.051000   1990-03-03 10:00   木 > 金   top2 pattern_sangsin
0.051570   1985-04-18 16:00   火 > 木   top2 resource_as_yongsin
0.053730   1990-03-15 10:00   火 > 土   top2 support_day_master
0.185000   1990-05-05 13:30   木 > 土   top2 disease_remedy:shangguan_attacks_officer
0.213910   1985-05-05 14:00   木 > 金   top2 johu
0.775000   1985-03-05 12:00   木 > 火   top2 pattern_sangsin
0.800000   1985-03-15 14:30   土 > 金   top2 disease_remedy:killing_overwhelms_weak
```

`0.02` 는 `0.010825` 와 `0.021741` 사이의 **빈 구간 안**에 있다. 그 구간 어디를 잘라도
분할 결과가 같다.

비교가 `raw_margin <= threshold` 일 때, 동일한 분할을 주는 범위는 다음이다. **표시값이
아니라 원시값 기준**이다 — 점수가 float 연산 산물이라 반올림값으로 적으면 경계 판정이
흔들린다.

```
0.01082500000000001  ≤  threshold  <  0.021741
        (표시 0.010825)                (표시 0.021741)

범위 안 어떤 값이든  →  near-tie 3건으로 동일
```

near-tie 3건의 raw 값도 원값으로 남긴다.

```
0.00286000000000001    0.00999999999999997    0.01082500000000001
```

즉 이 표본에서 `0.02` 는 **틀리지 않지만 유일하게 결정되지도 않는다.** 밀집 구간과
희소 구간을 가르는 자연 경계가 아니라 넓은 빈틈 안의 임의값이다.

버킷 자체도 평탄하다 — `(0,0.005]`·`(0.005,0.01]`·`(0.01,0.02]`·`(0.02,0.03]` 이 각각
1건이다. 임계값 근처에서 밀도가 꺾이는 지점이 없다.

---

## 4. near-tie 가 한 모델의 부산물이 아니다

top2 를 만든 모델은 7종으로 흩어져 있다.

```
resource_as_yongsin                       3
pattern_sangsin                           3
johu                                      2
support_day_master                        2
officer_controls_peer                     1
disease_remedy:killing_overwhelms_weak    1
disease_remedy:shangguan_attacks_officer  1
```

near-tie 3건의 top2 도 `support_day_master` · `johu` · `pattern_sangsin` 으로 각각
다르다. 특정 모델이 경쟁을 만들어 내는 구조는 아니다.

### primary 실현 출처

```
complete_model_role_map               7
static_fallback_role_map              5
support_day_master_special_role_map   1
```

---

## 5. 이 감사가 말하지 못하는 것

```yaml
sample_size_sufficient_for_threshold_selection: NO
```

**13건으로는 변곡점을 찾을 수 없다.** 버킷당 0~4건이라 밀도 추정이 성립하지 않고,
`<= 0.02` 가 3건이라 MC-B 의 대안 유형 분류도 3건 위에서 이뤄진다.

임계값을 데이터로 정하려면 모집단을 늘려야 한다. 다만 **무작위 생성으로 늘리면 안
된다** — 기존 감사와 비교 가능성이 깨진다. 픽스처 확장은 별도 결정 사항이다.

지금 말할 수 있는 것은 이것뿐이다.

```
0.02 는 이 표본의 밀도 구조에서 도출된 값이 아니다
0.011 ~ 0.021 의 어떤 값도 같은 분할을 준다
정확한 동점·반올림 동점은 이 코호트에 없다
```

---

## 6. MC-B 로 넘기는 것

```yaml
near_tie_charts: 3          # <= 0.02
  - {margin: 0.002860, pair: "水 > 金", top2_model: support_day_master}
  - {margin: 0.010000, pair: "金 > 水", top2_model: johu}
  - {margin: 0.010825, pair: "土 > 水", top2_model: pattern_sangsin}
```

MC-B 는 이 3건에 대해 runner-up standalone fresh replay 를 돌려 다음으로 분류한다.

```
NEAR_TIE_SEMANTICALLY_EQUIVALENT     역할표까지 동일 — 대안으로 보여줄 실익 낮음
NEAR_TIE_PROVENANCE_DIFFERENT        역할표는 같고 실현 경로만 다름
NEAR_TIE_ROLE_MAP_ALTERNATIVE        역할표가 실제로 달라짐 — genuine alternative
REPLAY_UNAVAILABLE
```

01c1 에서 확보한 강제 재생 규칙을 그대로 쓴다 — 용신 오행 하나만 강제하고, primary
산출을 runner-up 입력으로 재사용하지 않으며, `selected_model_ref` identity 는 비교에서
제외하고, 폴백은 **결과와 원인을 따로** 기록한다.

사례 A(0.010825)의 runner-up 은 01c1-b1 에서 이미 재생했다 —
`NEAR_TIE_ROLE_MAP_ALTERNATIVE` 이며 직접 원인은
`STATIC_FALLBACK_FROM_INCOMPLETE_MODEL_MAP` 이다.
