# P2-1C-1 harness — secondary factor 구조 C0 vs C1

spec p2.1c1.v1 · baseline C0 A0.30/P0.30 · calibration cal-2026-07-24.1 · lattice 6 case. **감사 전용·읽기 전용·production delta 0.** C2 미포함(조건부 §10). 자동 채택 없음(§14).

## 0. 불변식 게이트(§13)

- 전체 위반: **0** (PASS)
- 검사: C0 A0.3/P0.3==BASELINE · activation factor→stability/separation 불변 · pressure factor→activation 불변 · cross-root factor 무영향 · same-root activation 비감소

## 1. 축별 factor 독립 sensitivity(§8·§9 — finite difference)

> C1의 핵심: activation factor는 activation만, pressure factor는 stability·separation만 움직여야 한다(축간 분리). d(축)/d(factor) — 0이면 그 축은 해당 factor와 무관.

| 사례 | dAct/dA | dStab/dA | dSep/dA | dAct/dP | dStab/dP | dSep/dP |
|---|--:|--:|--:|--:|--:|--:|
| same_CHUNG_HYEONG | 15.55 | 0.0 | 0.0 | 0.0 | -0.8 | 0.6 |
| cross_CHUNG_HYEONG | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| single_CHUNG | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| single_HYEONG | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| same_HAP_CHUNG | 13.6033 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| root_3_CHUNG | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## 2. 축간 동조 대비 — C0(공유) vs C1(분리)

> **핵심 관찰(§8)**: C0는 단일 factor가 세 축을 동시에 움직인다. C1은 activation factor의 dStab/dA·dSep/dA=0, pressure factor의 dAct/dP=0으로 activation을 pressure에서 분리한다.

### C0 단일 factor sensitivity(세 축 동조)

| 사례 | dAct | dStab | dSep |
|---|--:|--:|--:|
| same_CHUNG_HYEONG | 15.55 | -0.8 | 0.6 |
| cross_CHUNG_HYEONG | 0.0 | 0.0 | 0.0 |
| single_CHUNG | 0.0 | 0.0 | 0.0 |
| single_HYEONG | 0.0 | 0.0 | 0.0 |
| same_HAP_CHUNG | 13.6033 | 0.0 | 0.0 |
| root_3_CHUNG | 0.0 | 0.0 | 0.0 |

> same_CHUNG_HYEONG: C0에서 단일 factor가 activation(+15.55)·stability·separation을 **동시에** 움직인다 — activation 복합만 억제하려 해도 stability/separation이 함께 바뀐다. C1(§1)은 dStab/dA=dSep/dA=0으로 이 동조를 끊는다. 이것이 C1 채택의 핵심 근거(단, 채택은 §14 Pareto 판단).

## 3. 축별 root 구별력 retention(§8)

### activation (activation factor sweep · pressure 0.3 고정)

| factor | same | cross | retention |
|--:|--:|--:|--:|
| 0.0 | 19.435 | 34.983 | 0.444 |
| 0.15 | 21.767 | 34.983 | 0.378 |
| 0.3 | 24.099 | 34.983 | 0.311 |
| 0.45 | 26.432 | 34.983 | 0.244 |
| 0.6 | 28.764 | 34.983 | 0.178 |

### separation (pressure factor sweep · activation 0.3 고정)

| factor | same | cross | retention |
|--:|--:|--:|--:|
| 0.0 | 1.0 | 1.6 | 0.375 |
| 0.15 | 1.09 | 1.6 | 0.319 |
| 0.3 | 1.18 | 1.6 | 0.263 |
| 0.45 | 1.27 | 1.6 | 0.206 |
| 0.6 | 1.36 | 1.6 | 0.15 |

## 4. C0 대각 회귀(P2-1A activation과 일치)

| factor | same_CHUNG_HYEONG activation |
|--:|--:|
| 0.0 | 19.435 |
| 0.15 | 21.767 |
| 0.3 | 24.099 |
| 0.45 | 26.432 |
| 0.6 | 28.764 |

## 5. 관찰(§14 — Pareto·자동 채택 금지)

- C1은 activation을 pressure에서 분리해, activation 복합을 억제하면서 stability/separation은 유지(또는 반대)할 수 있게 한다. 채택 여부는 축별 root 구별력·축간 동조 감소·파라미터 수(1개 추가)·경계 사례 감수의 Pareto로 판단 — **단일 점수 자동 결정 금지**.
- stability와 separation은 C1에서 여전히 동일 pressure factor를 공유하므로 동조가 남는다(C1 구조적 한계 — C2 진입은 §10 조건 충족 시).

