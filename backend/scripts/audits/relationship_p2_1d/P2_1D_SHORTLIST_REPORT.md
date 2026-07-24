# P2-1D shortlist harness — 7 profile × 331 harness

spec p2.1d.v1 · calibration cal-2026-07-24.1 · fixture 6·기간 132. **감사 전용·읽기 전용·production delta 0.** 자동 최적 선정 없음(§10) — P2-3 감수 자료. 임계값 사전 등록(SSOT §3-3). D3(CHUNG bonus)는 dict(S1) 변경이라 별도(§7 단일 변경 유지 — 본 harness는 calibration 단위 6 profile).

## 0. 사전 등록 임계값(§3-3 — 결과 관찰 전 고정)

- band collapse ≥ 0.85 (eligible n≥20, EVALUATED만)
- root=1 overactivation ≥ max(baseline×2, baseline+0.1)
- root≥2 underactivation ≤ baseline−0.2 또는 baseline×0.5
- baseline root=1 strong 0.03·root≥2 strong 0.526

## 1. profile별 review flag(자동 탈락 아님·중첩 가능)

| profile | status | act band 분포 | root1 strong | root2+ strong |
|---|---|---|--:|--:|
| D0_baseline | PASS | {"low": 9, "weak": 30, "moderate": 35, "strong": 12} | 0.03 | 0.526 |
| D1_C1_act_conservative | PASS | {"low": 9, "weak": 31, "moderate": 37, "strong": 9} | 0.015 | 0.421 |
| D2_C1_prs_conservative | PASS | {"low": 9, "weak": 30, "moderate": 35, "strong": 12} | 0.03 | 0.526 |
| D4_stab_CHUNG_conservative | PASS | {"low": 9, "weak": 30, "moderate": 35, "strong": 12} | 0.03 | 0.526 |
| D5_sep_conservative | PASS | {"low": 9, "weak": 30, "moderate": 35, "strong": 12} | 0.03 | 0.526 |
| D6_HAP_support_up | PASS | {"low": 9, "weak": 30, "moderate": 35, "strong": 12} | 0.03 | 0.526 |

## 2. profile disagreement 경계 사례(§8 — P2-3 감수용 상위 15)

총 15건. band/sign/sep 판단이 갈리는 사례.

| roots | 갈림축수 | reasons | D0 | D1 | D2 | D4 | D5 | D6 |
|--:|--:|---|---|---|---|---|---|---|
| 1 | 1 | act_band,C0!=C1act_band | strong/neg | moderate/neg | strong/neg | strong/neg | strong/neg | strong/neg |
| 1 | 1 | sep_band | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg |
| 2 | 1 | act_band,C0!=C1act_band | strong/neg | moderate/neg | strong/neg | strong/neg | strong/neg | strong/neg |
| 1 | 1 | act_band,C0!=C1act_band | moderate/pos | weak/pos | moderate/pos | moderate/pos | moderate/pos | moderate/pos |
| 1 | 1 | sep_band | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg |
| 1 | 1 | sep_band | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg |
| 2 | 1 | stab_sign | strong/zero | strong/zero | strong/zero | strong/zero | strong/zero | strong/pos |
| 2 | 1 | act_band,C0!=C1act_band | strong/neg | moderate/neg | strong/neg | strong/neg | strong/neg | strong/neg |
| 1 | 1 | sep_band | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg |
| 1 | 1 | sep_band | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg |
| 1 | 1 | sep_band | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg |
| 1 | 1 | sep_band | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg |
| 1 | 1 | sep_band | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg |
| 2 | 1 | stab_sign | strong/zero | strong/zero | strong/zero | strong/zero | strong/zero | strong/pos |
| 1 | 1 | sep_band | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg | moderate/neg |

## 3. 관찰(§10·§11 — 자동 채택 없음)

- 이 자료는 P2-3 사람 감수용이다. review flag가 붙은 profile도 통계 모양만으로 제거하지 않는다. C0/C1 최종 채택은 감수에서(activation에 낮은 factor·pressure에 다른 factor가 여러 의미 사례에서 반복 적절할 때만 C1).
- 하드 불변식·NOT_ADMISSIBLE·production delta는 별도 게이트(FAIL) — 본 harness profile은 전부 admissible(D5 separation ordering 유지). 분모 분리: 331 harness 전용(fixture·lattice 미합산).

