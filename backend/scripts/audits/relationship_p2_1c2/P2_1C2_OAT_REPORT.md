# P2-1C-2 harness — weight OAT × 구조 anchor(S0/S1/S2)

spec p2.1c2.v1 · calibration cal-2026-07-24.1 · lattice 4 case. **감사 전용·읽기 전용·production delta 0.** OAT 한 번에 하나·자동 clamp 없음(§5). anchor: S0(C0 0.3)·S1(C1 A0.15/P0.30)·S2(C1 A0.30/P0.15).

## 0. 불변식 게이트(§11)

- 전체 위반: **0** (PASS)
- 검사: S0 A0.3==BASELINE · weight 하나 변경 시 비대상 축·status·count 불변

## 1. 구조 cross-check(§8 — factor routing 검증)

- stability OAT가 activation 구조(S0↔S1)에 불변: **True**
- activation OAT가 pressure 구조(S0↔S2)에 불변: **True**
> 두 값이 True면 factor routing 정상(activation 구조 차는 stability weight 효과에 무영향, pressure 구조 차는 activation bonus 효과에 무영향).

## 2. activation kind bonus OAT — S0 sensitivity(local/wide)

> parameter delta ≠ final activation delta(§4 — S1 dict bonus는 palace 가중 통과). local=±10%·wide=±20% finite difference.

| 사례:kind | baseline | local | wide |
|---|--:|--:|--:|
| same_CHUNG_HYEONG:HAP | 24.099 | 0.0 | 0.0 |
| cross_CHUNG_HYEONG:HAP | 34.983 | 0.0 | 0.0 |
| single_CHUNG:HAP | 19.435 | 0.0 | 0.0 |
| same_HAP_CHUNG:HAP | 23.516 | 4.08 | 4.08 |
| same_CHUNG_HYEONG:CHUNG | 24.099 | 19.435 | 19.435 |
| cross_CHUNG_HYEONG:CHUNG | 34.983 | 19.435 | 19.435 |
| single_CHUNG:CHUNG | 19.435 | 19.435 | 19.435 |
| same_HAP_CHUNG:CHUNG | 23.516 | 19.435 | 19.435 |
| same_CHUNG_HYEONG:HYEONG | 24.099 | 4.665 | 4.6625 |
| cross_CHUNG_HYEONG:HYEONG | 34.983 | 15.55 | 15.55 |
| single_CHUNG:HYEONG | 19.435 | 0.0 | 0.0 |
| same_HAP_CHUNG:HYEONG | 23.516 | 0.0 | 0.0 |
| same_CHUNG_HYEONG:PA | 24.099 | 0.0 | 0.0 |
| cross_CHUNG_HYEONG:PA | 34.983 | 0.0 | 0.0 |
| single_CHUNG:PA | 19.435 | 0.0 | 0.0 |
| same_HAP_CHUNG:PA | 23.516 | 0.0 | 0.0 |
| same_CHUNG_HYEONG:HAE | 24.099 | 0.0 | 0.0 |
| cross_CHUNG_HYEONG:HAE | 34.983 | 0.0 | 0.0 |
| single_CHUNG:HAE | 19.435 | 0.0 | 0.0 |
| same_HAP_CHUNG:HAE | 23.516 | 0.0 | 0.0 |

## 3. stability weight OAT — S0 sensitivity

| 사례:param | baseline(net) | local | wide |
|---|--:|--:|--:|
| same_CHUNG_HYEONG:support.HAP | -1.24 | 0.0 | 0.0 |
| cross_CHUNG_HYEONG:support.HAP | -1.8 | 0.0 | 0.0 |
| single_CHUNG:support.HAP | -1.0 | 0.0 | 0.0 |
| same_HAP_CHUNG:support.HAP | -0.7 | 0.3 | 0.3 |
| same_CHUNG_HYEONG:pressure.CHUNG | -1.24 | -1.0 | -1.0 |
| cross_CHUNG_HYEONG:pressure.CHUNG | -1.8 | -1.0 | -1.0 |
| single_CHUNG:pressure.CHUNG | -1.0 | -1.0 | -1.0 |
| same_HAP_CHUNG:pressure.CHUNG | -0.7 | -1.0 | -1.0 |
| same_CHUNG_HYEONG:pressure.HYEONG | -1.24 | -0.24 | -0.24 |
| cross_CHUNG_HYEONG:pressure.HYEONG | -1.8 | -0.8 | -0.8 |
| single_CHUNG:pressure.HYEONG | -1.0 | 0.0 | 0.0 |
| same_HAP_CHUNG:pressure.HYEONG | -0.7 | 0.0 | 0.0 |
| same_CHUNG_HYEONG:pressure.PA | -1.24 | 0.0 | 0.0 |
| cross_CHUNG_HYEONG:pressure.PA | -1.8 | 0.0 | 0.0 |
| single_CHUNG:pressure.PA | -1.0 | 0.0 | 0.0 |
| same_HAP_CHUNG:pressure.PA | -0.7 | 0.0 | 0.0 |
| same_CHUNG_HYEONG:pressure.HAE | -1.24 | 0.0 | 0.0 |
| cross_CHUNG_HYEONG:pressure.HAE | -1.8 | 0.0 | 0.0 |
| single_CHUNG:pressure.HAE | -1.0 | 0.0 | 0.0 |
| same_HAP_CHUNG:pressure.HAE | -0.7 | 0.0 | 0.0 |

## 4. separation weight OAT — S0 sensitivity

| 사례:param | baseline | local | wide |
|---|--:|--:|--:|
| same_CHUNG_HYEONG:CHUNG | 1.18 | 1.0 | 1.0 |
| cross_CHUNG_HYEONG:CHUNG | 1.6 | 1.0 | 1.0 |
| single_CHUNG:CHUNG | 1.0 | 1.0 | 1.0 |
| same_HAP_CHUNG:CHUNG | 1.0 | 1.0 | 1.0 |
| same_CHUNG_HYEONG:HYEONG | 1.18 | 0.18 | 0.18 |
| cross_CHUNG_HYEONG:HYEONG | 1.6 | 0.6 | 0.6 |
| single_CHUNG:HYEONG | 1.0 | 0.0 | 0.0 |
| same_HAP_CHUNG:HYEONG | 1.0 | 0.0 | 0.0 |
| same_CHUNG_HYEONG:PA | 1.18 | 0.0 | 0.0 |
| cross_CHUNG_HYEONG:PA | 1.6 | 0.0 | 0.0 |
| single_CHUNG:PA | 1.0 | 0.0 | 0.0 |
| same_HAP_CHUNG:PA | 1.0 | 0.0 | 0.0 |
| same_CHUNG_HYEONG:HAE | 1.18 | 0.0 | 0.0 |
| cross_CHUNG_HYEONG:HAE | 1.6 | 0.0 | 0.0 |
| single_CHUNG:HAE | 1.0 | 0.0 | 0.0 |
| same_HAP_CHUNG:HAE | 1.0 | 0.0 | 0.0 |

## 5. NOT_ADMISSIBLE profile(§5 — ordering 위반·자동 clamp 금지)

- 없음.

## 6. 구조별 weight 민감도 대비(§8 — S0/S1/S2)

> 같은 weight perturbation을 세 anchor에 적용. activation bonus는 S0=S2(pressure 구조 차 무관), stability weight는 S0=S1(activation 구조 차 무관)이 정상.

### stability pressure.CHUNG local sensitivity(anchor별)

| 사례 | S0 | S1 | S2 |
|---|--:|--:|--:|
| same_CHUNG_HYEONG | -1.0 | -1.0 | -1.0 |
| cross_CHUNG_HYEONG | -1.0 | -1.0 | -1.0 |
| single_CHUNG | -1.0 | -1.0 | -1.0 |
| same_HAP_CHUNG | -1.0 | -1.0 | -1.0 |

## 7. 관찰(§9·§10·§14 — Pareto·C2 보류)

- 이 결과는 C0/C1 구조 shortlist 확정과 weight 감수 후보 추림에 쓴다. 단일 점수 자동 채택·자동 최적 profile 선정 금지.
- C2 진입(§10)은 stability에 적절한 pressure weight/factor가 separation을 지속 과대·과소하거나 그 역이 반복될 때만. 축별 finite-diff 값이 다르다는 사실만으로는 근거 아님(축 단위가 다르므로 derivative 상이는 정상).

