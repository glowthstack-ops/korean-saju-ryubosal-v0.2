# P2-1B 민감도 harness — jaenghap_support_weaken × secondary_factor

spec p2.1b.v1 · baseline SF30·JW50 · calibration cal-2026-07-24.1 · band B0 고정(§5). **감사 전용·읽기 전용·production delta 0.** stability 집중 — band 미교차.

## 0. 불변식 게이트(§7·§9)

- 전체 위반: **0** (PASS)
- 검사: weaken=0 수치 동일 · JW↑ target/total support·stability net 비증가 · pressure/activation/separation/count JW 불변 · 비대상 root drift 0 · support≥0 · 중복=1× · missing/multi-root 적용 0

## 1. 사례별 target support 감소(SF30 · JW sweep)

| 사례 | JW00 | JW25 | JW50 | JW75 | retention(JW75/JW00) |
|---|--:|--:|--:|--:|--:|
| pure_support | 0.3 | 0.255 | 0.21 | 0.165 | 0.55 |
| target_vs_nontarget | 0.3 | 0.255 | 0.21 | 0.165 | 0.55 |
| support_pressure_mix | 0.3 | 0.255 | 0.21 | 0.165 | 0.55 |
| same_root_mix | 0.3 | 0.255 | 0.21 | 0.165 | 0.55 |
| duplicate_modifier | 0.3 | 0.255 | 0.21 | 0.165 | 0.55 |
| wrong_target | 0.0 | 0.0 | 0.0 | 0.0 | — |
| multi_root_target | 0.0 | 0.0 | 0.0 | 0.0 | — |
| boundary_sign_flip | 0.3 | 0.255 | 0.21 | 0.165 | 0.55 |

## 2. stability net 부호 · sign flip(SF30 발췌)

| 사례 | JW00 | JW25 | JW50 | JW75 |
|---|---|---|---|---|
| pure_support | pos | pos | pos | pos |
| target_vs_nontarget | pos | pos | pos | pos |
| support_pressure_mix | neg | neg | neg | neg |
| same_root_mix | neg | neg | neg | neg |
| duplicate_modifier | pos | pos | pos | pos |
| wrong_target | pos | pos | pos | pos |
| multi_root_target | pos | pos | pos | pos |
| boundary_sign_flip | zero | neg | neg | neg |

## 3. SF × JW 교차표(§8 — 공통 SF 유지 여부 판단 근거·P2-1C)

| SF | JW | stability_negative_rate | sign_flip_count |
|---|---|--:|--:|
| SF00 | JW00 | 0.25 | 0 |
| SF00 | JW25 | 0.375 | 1 |
| SF00 | JW50 | 0.375 | 1 |
| SF00 | JW75 | 0.375 | 1 |
| SF30 | JW00 | 0.25 | 0 |
| SF30 | JW25 | 0.375 | 1 |
| SF30 | JW50 | 0.375 | 1 |
| SF30 | JW75 | 0.375 | 1 |
| SF60 | JW00 | 0.25 | 0 |
| SF60 | JW25 | 0.375 | 1 |
| SF60 | JW50 | 0.375 | 1 |
| SF60 | JW75 | 0.375 | 1 |

## 4. scope 안전성(§8)

- 비대상 root support drift·미해소/multi-root 수치 적용: **0**(§0 게이트). wrong_target·multi_root_target은 JW 전 support 불변 확인.
- multi_root_target: modifier_multi_root_hold_count ≥ 1(보류 계측).

## 5. synthesizer 발견(§7 중복 idempotency — P2 수정 대상 아님)

- derived modifier 중복 idempotent: **OK**.

## 6. 관찰(§P2-1C 전달 — 최적 profile 선정 아님)

- 이 사례군에서 sign flip은 **JW가 구동**(boundary_sign_flip: JW25에서 zero→neg), SF는 미결합(단일 root 경계 사례라 SF 무영향). SF가 same-root multi-pressure를 키워 sign에 결합하는지는 별도 경계 사례 필요(공유 계수 §3-1).
- supersession remap(§6-8)은 합성기 `resolve_canonical_evidence_id`가 담당 — P1-6 회귀에서 검증됨(PROVISIONAL P→EXACT E 해소 후 E root 1회 적용). 본 harness는 JW 민감도 전용이라 재검증하지 않는다.

