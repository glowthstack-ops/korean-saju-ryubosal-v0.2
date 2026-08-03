# 사용자 결과 차이 측정 (CAL-ROLE-MARGIN-CENSUS / MC-E1)

```yaml
verdict:
  - PRIMARY_SHADOW_PARITY_CONFIRMED
  - USER_OUTCOME_DIVERGENCE_DISTRIBUTION_MEASURED
  - PRODUCTION_DOWNSTREAM_DISCRIMINATOR_STRUCTURALLY_DEGENERATE
  - CLAIM_AXIS_SET_IS_NOT_ROLE_SENSITIVE
  - MARGIN_AS_ALTERNATIVE_SELECTOR_NOT_SUPPORTED
  - INTERNAL_DISCRIMINATOR_SEARCH_STOPPED
  - GOLDEN_COHORT_REQUIRED
```

재현: `python scripts/audits/measure_user_outcome_divergence.py --out var/audit/user_outcome`

내부 축이 아니라 **production 이 실제로 만드는 사용자 출력**(`_build_period_fortune`)을 비교했다.

---

## 1. 플래그를 맞추지 않으면 다른 구성을 재게 된다

기본 환경으로 돌리면 계층형 grounding 이 통째로 꺼진다(실측: `hierarchy_lines` 0줄).
운영 서버 프로세스와 같은 플래그를 **import 전에** 세팅해야 모듈 상수에 반영된다.

```
SAJU_PERIOD_HIERARCHY_ENABLED         true
SAJU_RELATION_SEMANTIC_PATCH_ENABLED  true
SAJU_PILLAR_POLARITY_V2_ENABLED       true
SAJU_LOCAL_ADVERSE_ONLY_ENABLED       true
SAJU_SAFE_TEMPLATE_FALLBACK_ENABLED   true
SAJU_EVENT_PROCESS_DUAL_RUN_ENABLED   true
SAJU_EVENT_LOCAL_TRIGGER_GATE_ENABLED false
```

플래그 집합은 산출물에 기록한다 — 나중에 구성이 바뀌면 이 측정과 비교할 수 없다.

## 2. primary parity — 통과

```yaml
primary_parity_failures: []     # overlay 설치·복원 뒤 primary 출력 byte 동일
overlay_failures:        []     # 설치 시 alternate 조회 · 복원 시 primary 조회 확인
```

overlay 는 context manager 로 감싸 사례마다 설치·복원하고, 설치 시점과 복원 시점 양쪽에서
실제 조회 결과를 검사했다. 이 게이트가 통과해야 alternate 차이를 어댑터 결함이 아닌
실제 의미로 볼 수 있다.

## 3. 결과

```yaml
USER_OUTPUT_IDENTICAL:           0 / 13
SURFACE_ONLY_DIVERGENCE:         1 / 13
RENDERED_CONCLUSION_DIVERGENCE: 12 / 13
AXIS_SET_DIVERGENCE:             0 / 13
```

```
                 margin  near   divergence                  primary → alternate direction
    0.00286000000000001  True   RENDERED_CONCLUSION         MIXED_ACROSS_LAYERS → MIXED_ACROSS_LAYERS
    0.00999999999999997  True   RENDERED_CONCLUSION         BACKGROUND_SUPPORT_TARGET_FRICTION → MIXED_ACROSS_LAYERS
    0.01082500000000001  True   RENDERED_CONCLUSION         MIXED_ACROSS_LAYERS → CONSISTENT_PRESSURE
               0.021741  False  RENDERED_CONCLUSION         CONSISTENT_PRESSURE → MIXED_ACROSS_LAYERS
               0.041715  False  RENDERED_CONCLUSION         MIXED_ACROSS_LAYERS → BACKGROUND_PRESSURE_TARGET_RELIEF
    0.04423500000000002  False  RENDERED_CONCLUSION         MIXED_ACROSS_LAYERS → BACKGROUND_PRESSURE_TARGET_RELIEF
    0.05099999999999997  False  RENDERED_CONCLUSION         NO_CLEAR_DIRECTION → CONSISTENT_PRESSURE
               0.051570  False  RENDERED_CONCLUSION         CONSISTENT_SUPPORT → NO_CLEAR_DIRECTION
    0.05372999999999997  False  SURFACE_ONLY                MIXED_ACROSS_LAYERS → MIXED_ACROSS_LAYERS
                  0.185  False  RENDERED_CONCLUSION         MIXED_ACROSS_LAYERS → BACKGROUND_PRESSURE_TARGET_RELIEF
                0.21391  False  RENDERED_CONCLUSION         NO_CLEAR_DIRECTION → CONSISTENT_PRESSURE
    0.77499999999999999  False  RENDERED_CONCLUSION         MIXED_ACROSS_LAYERS → CONSISTENT_SUPPORT
                   0.80  False  RENDERED_CONCLUSION         BACKGROUND_PRESSURE_TARGET_RELIEF → CONSISTENT_PRESSURE
```

**사용자 출력이 같은 사례가 하나도 없다.** margin `0.80` 짜리도 결론 표현이 뒤집힌다
(`BACKGROUND_PRESSURE_TARGET_RELIEF → CONSISTENT_PRESSURE`). near-tie 3건과 대조군
10건의 양상이 같다.

```
MARGIN_AS_ALTERNATIVE_SELECTOR_NOT_SUPPORTED
```

## 4. 예상과 달랐던 것 — claim 축은 역할에 둔감하다

```yaml
AXIS_SET_DIVERGENCE: 0 / 13
```

`narrative_axis` 집합이 **한 건도 바뀌지 않았다.** MC-E0 에서 이 축 집합을 "설명 의무의
근사" 로 삼았는데, 이 코호트에서는 역할표를 바꿔도 축 구성이 그대로다. 관측된 축은
`mitigation` · `neutral_activation` · `structural_tension` 계열이고, 역할 부호에 의존하는
강화 분기(`favorable_activation`/`adverse_activation`)가 이 표본에서 거의 뜨지 않는다.

즉 **의무 근사축은 판별자로 아무것도 하지 않고**, 실제로 갈리는 것은 층별 역할 상태에서
나오는 방향 분류다.

## 5. 유일한 예외 1건

`1990-03-15 10:00` (margin 0.0537) 만 의미론 서명이 완전히 같고 렌더 문장만 다르다.
역할 이름이 문장에 그대로 들어가기 때문이다(`천간 甲(기신·불리)`). MC-D 에서 역할
class 가 바뀌지 않았던 사례와 같은 명식이다.

1/13 은 근거가 되지 못한다. 다만 "두 역할표가 같은 결론을 주는 명식이 존재한다" 는 사실
자체는 기록해 둔다 — 전건 항등이 아니라는 뜻이다.

## 6. 판정 — 내부 축 탐색을 멈춘다

```
role-map 차이        13/13 항상 참        MC-B
P2 결정 차이          13/13 항상 참        MC-D
P2 역할 class 차이    12/13               MC-D
사용자 출력 차이       13/13 (의미론 12)    MC-E1
claim 축 집합 차이     0/13                MC-E1 — 반대 방향으로 무의미
점수 근접 0.02        밀도 근거 없음        MC-A
```

문서에 적어 둔 종료 조건대로 **새 내부 축을 더 찾지 않는다.**

```
INTERNAL_DISCRIMINATOR_SEARCH_STOPPED
GOLDEN_COHORT_REQUIRED
```

역할표를 바꾸면 사용자 답이 거의 항상 달라진다는 것은, 뒤집어 말하면 **용신 선택이
사용자 결과를 지배한다**는 뜻이다. 그래서 "대안을 보존할 가치가 있는가" 는 내부 구조
비교로 답할 수 없다. 실제 질문·기간·사건과 **정답 판정 기준**이 있는 golden cohort 에서
"어느 쪽이 맞았는가" 를 봐야 한다.

## 7. 다음 트랙에 넘기는 것

```yaml
YongsinDecisionSet_replacement:  blocked      # 판별자 미확정
POPULATION_EXPANSION:            blocked      # 판별자 미확정 — 늘려도 같은 항등식을 더 셀 뿐
golden_cohort:                   required     # 실측 정답이 있는 사례 필요
0.02:                            legacy operational cutoff 로만 유지
model_complete / fallback:       provenance 전용 (MC-D)
role_class:                      구성요소 전용 (MC-E0)
```
