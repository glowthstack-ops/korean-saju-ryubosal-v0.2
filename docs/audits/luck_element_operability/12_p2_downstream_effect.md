# 대안 역할표의 P2 하류 영향 감사 (CAL-ROLE-MARGIN-CENSUS / MC-D)

```yaml
verdict:
  - P2_EFFECT_DISTRIBUTION_MEASURED
  - P2_DISCRIMINATOR_STRUCTURALLY_DEGENERATE
  - OPERABILITY_GRADE_IS_ROLE_INDEPENDENT
  - MODEL_COMPLETENESS_RETAINED_AS_PROVENANCE_ONLY
  - POPULATION_EXPANSION_PENDING_DISCRIMINATOR
  - P3_INFERENCE_NOT_ATTEMPTED
```

재현: `python scripts/audits/measure_p2_downstream_effect.py --out var/audit/p2_downstream`

---

## 1. 결과 — 또 항상 참이다

```yaml
charts:                 13          # baseline cohort
divergence_distribution:
  P2_DECISION_DIVERGENCE: 13
decision_divergence:
  total:       13/13
  near_tie:     3/3
  wide_margin: 10/10
```

MC-B 의 role-map 차이와 **똑같이 판별력이 없다.** margin `0.80` 짜리도 P2 결정이 갈린다.

near-tie 3건만 돌렸다면 "3/3 P2 결정 차이" 로 닫고 임계값의 근거처럼 썼을 것이다.
전 구간 대조가 다시 그것을 막았다.

---

## 2. 왜 항상 참인가 — 구조

```yaml
statuses_identical_everywhere: true
```

**실현도 등급은 역할표에 독립이다.**

```
등급(OperabilityStatus)   대상 오행의 profile 로만 결정된다 — 역할과 무관
투영(activation axis)     같은 등급을 어느 축에 올릴지만 역할이 정한다
```

두 역할표는 5오행을 역할에 배정하는 서로 다른 순열이다. 운 간지 대상(대운·세운 천간·지지
4자리)이 그 순열 차이에 걸리면 축이 바뀌고, 그러면 P2 산출이 자동으로 갈린다.

즉 MC-D 가 측정한 것은 "대안이 더 나은가" 가 아니라 **"두 순열이 다른가"** 였고, 그건
MC-B 에서 이미 항상 참이라고 확인된 명제다.

---

## 3. 역할 class 수준으로 좁히면 12/13

`용·희 / 기·구 / 한` 3분류로만 보면 한 건이 갈리지 않는다.

```
                 margin  near   결정차이  class차이  completeness
    0.00286000000000001  True      4         4      complete/complete
    0.00999999999999997  True      4         1      fallback/fallback
    0.01082500000000001  True      2         2      complete/fallback
               0.021741  False     4         1      complete/fallback
               0.041715  False     4         1      complete/complete
    0.04423500000000002  False     4         1      complete/complete
    0.05099999999999997  False     4         4      fallback/fallback
               0.051570  False     4         4      complete/complete
    0.05372999999999997  False     4         0      complete/complete   ← class 불변
                  0.185  False     4         4      fallback/fallback
                0.21391  False     4         4      complete/fallback
    0.77499999999999999  False     4         3      fallback/fallback
                   0.80  False     4         2      fallback/fallback
```

`1990-03-15 10:00` 은 역할 **이름**은 바뀌지만(용↔희 등) 유리·불리·중립 **분류**는 그대로다.
두 역할표가 운 간지에 대해 같은 길흉 구도를 준다는 뜻이다.

```yaml
role_class_divergence: 12 / 13
```

12/13 도 판별자로 쓰기엔 거의 항상 참이다. 다만 **완전히 항상 참은 아니라는 점**이
role-map 차이·P2 결정 차이와 다르다. 사용자에게 보이는 축(길흉 구도)에 가장 가까운
비교이기도 하다. 후보로 기록만 하고 채택하지 않는다 — 13건에서 1건 차이는 근거가 되지
못한다.

---

## 4. 완비/폴백 조합은 판별자가 아니다

```yaml
completeness_pairs:
  complete/complete: 5
  fallback/fallback: 5
  complete/fallback: 3
```

세 조합이 margin 구간 전체에 흩어져 있고 P2 결정 차이와도 상관이 없다(전건 divergence).

`완비 모델맵 대안이 명리적으로 더 유효하다` 는 명제는 **아직 입증되지 않았다.** 01c1 에서
정적 폴백도 의도된 역할표를 안정적으로 산출함을 확인했으므로, 폴백 여부를 대안 가치의
기준으로 쓰면 구현 provenance 를 명리적 의미로 오인하게 된다.

```
MODEL_COMPLETENESS_RETAINED_AS_PROVENANCE_ONLY
```

보조 메타데이터로는 유지한다 — `complete/complete` · `fallback/fallback` ·
`complete/fallback` 조합 자체는 대안의 성격을 설명하는 데 쓸 수 있다.

---

## 5. 지금까지 탈락한 판별자

```
role-map 차이       13/13 항상 참        MC-B
P2 결정 차이         13/13 항상 참        MC-D
P2 역할 class 차이   12/13 거의 항상 참    MC-D — 후보로만 기록
완비/폴백 조합       margin·결정과 무상관  MC-D — provenance 전용
점수 근접(0.02)      밀도 근거 없음        MC-A — legacy cutoff 로만 유지
```

**남은 방향은 더 구체적인 사용자 결과축이다.** 이 감사가 본 P2 는 노드 하나의 작동성까지고,
대안이 "다른 결론" 을 내는지는 그 위 층에서 물어야 한다.

이 감사는 그 위 층으로의 추론을 시도하지 않았다(`P3_INFERENCE_NOT_ATTEMPTED`).

> **정정(MC-E0, 2026-08-03).** 초판은 "그 위의 결합·기간·사건 축은 아직 없다" 고 적었다.
> **틀렸다.** `build_period_role_summary`(기간 역할 요약) → `render_period_role_summary`
> (사용자 서술) → `build_v2_scoring`(P3 점수) 이 이미 운영 중이며
> `SAJU_PERIOD_HIERARCHY_ENABLED` 로 켜져 있다. 없는 것은 층이 아니라 **"무엇이 달라져야
> 다른 답인가" 의 계약**이다. 자세한 것은 13번 문서.

---

## 6. 모집단 확장은 아직

```yaml
POPULATION_EXPANSION_PENDING_DISCRIMINATOR
```

판별자가 없는 상태에서 표본만 늘리면 이미 퇴화한 조건을 더 많이 세게 된다. 확장은 판별자
후보가 확인된 뒤 층화(margin 구간 · 완비/폴백 조합 · 오행 조합 · model_type 조합 ·
divergence 유무)로 한다. 기존 13건은 `baseline cohort` 로 고정하고 새 사례는
`expansion cohort` 로 분리한다.

---

## 7. 회귀로 고정한 것

`backend/tests/unit/test_p2_role_map_independence.py` (대표 4건)

```
등급·규칙·앵커가 두 역할표에서 동일       ← 핵심 불변식
대상 자리·오행은 그대로, 역할 배정만 변함
대표 전건에서 역할 배정이 갈린다(판별력 없음)
```

첫 항목이 이 감사의 근간이다. 깨지면 "역할이 실현도를 만든다" 는 순환이 생기고, 대안
비교의 전제(같은 등급을 다른 축에 올린 것뿐)가 무너진다.
