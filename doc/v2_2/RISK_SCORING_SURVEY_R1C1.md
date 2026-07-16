> R1-c1/c2 전수 측정 고정본(감수 30·31차) — 재생성: `python scripts/risk_scoring_survey.py`
> 출력 결정적 — 본 파일과의 diff = 점수 의미 회귀 신호.

# R1-c1 위험 점수 전수 측정 — risk-score-r1.0.4-shadow
semantics cause-semantics-v3 · config b010e439c6902d29 · semantics 607f75c4a8dfc72c
compound=연결된 effect graph(shared canonical cause)만 · is_question_target=context confidence 제외(fixture 고정)

# 모집단 1 — 전체 구조 코퍼스(컨텍스트 없음·suppression baseline 동일)
## cohort 규모: A_structural_active 914 · B_eligible 1028 · C_context_exposable 281 · D_rankable_positive 175 · E_blocked_insufficient 2384 · F_vulnerability_active 271
structural priority(A군): p50 0.160 · p90 0.380 · max 1.401 · n=914
rankable raw(C군): p50 -0.116 · p90 0.232 · max 1.221 · n=281
rankable capped(C군): p50 0.000 · p90 0.232 · max 1.000 · n=281
비rankable(활성·capped=0): 739 — rankable 분포(D군 175)에 미포함(median 왜곡 방지)
## 도메인별 structural(A군) / rankable capped(D군)
  career         structural p50 0.075 · p90 0.680 · max 1.401 · n=58 | rankable p50 0.293 · p90 1.000 · max 1.000 · n=16
  contract_legal structural p50 0.160 · p90 0.360 · max 0.760 · n=202 | rankable p50 0.200 · p90 0.200 · max 0.200 · n=28
  finance        structural p50 0.160 · p90 0.425 · max 0.868 · n=194 | rankable p50 0.194 · p90 0.237 · max 0.657 · n=77
  health_safety  structural p50 0.180 · p90 0.368 · max 0.553 · n=136 | rankable p50 0.200 · p90 0.394 · max 0.394 · n=16
  relationship   structural p50 0.003 · p90 0.351 · max 0.859 · n=161 | rankable p50 0.121 · p90 0.400 · max 0.584 · n=17
  relocation     structural p50 0.160 · p90 0.250 · max 0.420 · n=102 | rankable p50 0.124 · p90 0.138 · max 0.138 · n=6
  selection      structural p50 0.256 · p90 0.521 · max 0.976 · n=61 | rankable p50 0.200 · p90 0.600 · max 0.600 · n=15
## 상한 집중 진단(D군 n=175):
  raw_gt_1 3건(1.7%) · raw_gt_1_2 3건(1.7%) · raw_ge_1 3건(1.7%) · capped_eq_1 3건(1.7%)
  raw p90 0.400 · p95 0.584 · p99 1.216
  capped=1 후보 risk_id 다양성: 1종
  상위 10% 동점: 5/17 · unique raw 12 — 다수 동점이면 R2 순위 분별력 저하(감수 판단)
  raw<0 0건(0.0%)(D군은 capped>0 정의라 0이어야 정상)
  net_priority_raw(C군): raw<0 182건(64.8%) · capped=0 182건 · protection로 0 하강 182건 — capped 하한 0·raw 보존
  exposure_at_max_rate(CONFIRMED 범주값 — 포화 아님): 0건(0.0%)
  component_clamped(계산값 cap 도달, A군): persistence 4건(0.4%)
상위 10%(D군) 축 원값 평균(6축 전부): occurrence 0.781, impact 0.535, exposure 0.388, persistence 0.541, compound 0.000, protection 0.050
상위 10% 가중 기여(공식 항별 평균): occ×imp×exp +0.169, persistence +0.541, compound +0.000, -protection -0.050 · cap-loss 평균 0.039
상위 10% 중 unresolved effect 연결 보유: 17/17 — 다수면 가중 확정 보류(감수 기준)
## compound 진단: compound>0 후보 0 · unresolved effect 연결 보유 3371(98%) · episode_count_only_violations 0(fixture 강제) · void_target_mismatch 0(구조적 — 전역 void)
## persistence 진단: unique cause lineages 1061 · 다기간 lineage 793 · candidate persistence 부여 1034 — 포트폴리오 원천은 lineage(후보 합산 금지)
## confidence: structural p50 0.600 · p90 0.800 · max 1.000 · n=914 | context p50 0.500 · p90 0.500 · max 0.500 · n=914
context 축 상태 합(A군): confirmed 0, conflicted 0, required 477, unknown 477

# 모집단 2 — profile overlay: A_all_unknown
## cohort 규모: A_structural_active 914 · B_eligible 1028 · C_context_exposable 281 · D_rankable_positive 175 · E_blocked_insufficient 2384 · F_vulnerability_active 271
structural priority(A군): p50 0.160 · p90 0.380 · max 1.401 · n=914
rankable raw(C군): p50 -0.116 · p90 0.232 · max 1.221 · n=281
rankable capped(C군): p50 0.000 · p90 0.232 · max 1.000 · n=281
비rankable(활성·capped=0): 739 — rankable 분포(D군 175)에 미포함(median 왜곡 방지)
## 도메인별 structural(A군) / rankable capped(D군)
  career         structural p50 0.075 · p90 0.680 · max 1.401 · n=58 | rankable p50 0.293 · p90 1.000 · max 1.000 · n=16
  contract_legal structural p50 0.160 · p90 0.360 · max 0.760 · n=202 | rankable p50 0.200 · p90 0.200 · max 0.200 · n=28
  finance        structural p50 0.160 · p90 0.425 · max 0.868 · n=194 | rankable p50 0.194 · p90 0.237 · max 0.657 · n=77
  health_safety  structural p50 0.180 · p90 0.368 · max 0.553 · n=136 | rankable p50 0.200 · p90 0.394 · max 0.394 · n=16
  relationship   structural p50 0.003 · p90 0.351 · max 0.859 · n=161 | rankable p50 0.121 · p90 0.400 · max 0.584 · n=17
  relocation     structural p50 0.160 · p90 0.250 · max 0.420 · n=102 | rankable p50 0.124 · p90 0.138 · max 0.138 · n=6
  selection      structural p50 0.256 · p90 0.521 · max 0.976 · n=61 | rankable p50 0.200 · p90 0.600 · max 0.600 · n=15
## 상한 집중 진단(D군 n=175):
  raw_gt_1 3건(1.7%) · raw_gt_1_2 3건(1.7%) · raw_ge_1 3건(1.7%) · capped_eq_1 3건(1.7%)
  raw p90 0.400 · p95 0.584 · p99 1.216
  capped=1 후보 risk_id 다양성: 1종
  상위 10% 동점: 5/17 · unique raw 12 — 다수 동점이면 R2 순위 분별력 저하(감수 판단)
  raw<0 0건(0.0%)(D군은 capped>0 정의라 0이어야 정상)
  net_priority_raw(C군): raw<0 182건(64.8%) · capped=0 182건 · protection로 0 하강 182건 — capped 하한 0·raw 보존
  exposure_at_max_rate(CONFIRMED 범주값 — 포화 아님): 0건(0.0%)
  component_clamped(계산값 cap 도달, A군): persistence 4건(0.4%)
상위 10%(D군) 축 원값 평균(6축 전부): occurrence 0.781, impact 0.535, exposure 0.388, persistence 0.541, compound 0.000, protection 0.050
상위 10% 가중 기여(공식 항별 평균): occ×imp×exp +0.169, persistence +0.541, compound +0.000, -protection -0.050 · cap-loss 평균 0.039
상위 10% 중 unresolved effect 연결 보유: 17/17 — 다수면 가중 확정 보류(감수 기준)
## compound 진단: compound>0 후보 0 · unresolved effect 연결 보유 3371(98%) · episode_count_only_violations 0(fixture 강제) · void_target_mismatch 0(구조적 — 전역 void)
## persistence 진단: unique cause lineages 1061 · 다기간 lineage 793 · candidate persistence 부여 1034 — 포트폴리오 원천은 lineage(후보 합산 금지)
## confidence: structural p50 0.600 · p90 0.800 · max 1.000 · n=914 | context p50 0.500 · p90 0.500 · max 0.500 · n=914
context 축 상태 합(A군): confirmed 0, conflicted 0, required 477, unknown 477

# 모집단 2 — profile overlay: B_typical_confirmed
## cohort 규모: A_structural_active 915 · B_eligible 1028 · C_context_exposable 344 · D_rankable_positive 221 · E_blocked_insufficient 2384 · F_vulnerability_active 271
structural priority(A군): p50 0.175 · p90 0.380 · max 1.401 · n=915
rankable raw(C군): p50 -0.088 · p90 0.502 · max 1.221 · n=344
rankable capped(C군): p50 0.000 · p90 0.502 · max 1.000 · n=344
비rankable(활성·capped=0): 694 — rankable 분포(D군 221)에 미포함(median 왜곡 방지)
## 도메인별 structural(A군) / rankable capped(D군)
  career         structural p50 0.075 · p90 0.680 · max 1.401 · n=58 | rankable p50 0.293 · p90 1.000 · max 1.000 · n=16
  contract_legal structural p50 0.160 · p90 0.360 · max 0.760 · n=208 | rankable p50 0.200 · p90 0.975 · max 1.000 · n=55
  finance        structural p50 0.160 · p90 0.425 · max 0.868 · n=194 | rankable p50 0.194 · p90 0.237 · max 0.657 · n=77
  health_safety  structural p50 0.180 · p90 0.368 · max 0.553 · n=136 | rankable p50 0.200 · p90 0.394 · max 0.394 · n=16
  relationship   structural p50 0.003 · p90 0.351 · max 0.859 · n=156 | rankable p50 0.100 · p90 0.502 · max 0.584 · n=36
  relocation     structural p50 0.160 · p90 0.250 · max 0.420 · n=102 | rankable p50 0.124 · p90 0.138 · max 0.138 · n=6
  selection      structural p50 0.256 · p90 0.521 · max 0.976 · n=61 | rankable p50 0.200 · p90 0.600 · max 0.600 · n=15
## 상한 집중 진단(D군 n=221):
  raw_gt_1 7건(3.2%) · raw_gt_1_2 3건(1.4%) · raw_ge_1 7건(3.2%) · capped_eq_1 7건(3.2%)
  raw p90 0.638 · p95 0.810 · p99 1.216
  capped=1 후보 risk_id 다양성: 3종
  상위 10% 동점: 6/22 · unique raw 16 — 다수 동점이면 R2 순위 분별력 저하(감수 판단)
  raw<0 0건(0.0%)(D군은 capped>0 정의라 0이어야 정상)
  net_priority_raw(C군): raw<0 198건(57.6%) · capped=0 198건 · protection로 0 하강 198건 — capped 하한 0·raw 보존
  exposure_at_max_rate(CONFIRMED 범주값 — 포화 아님): 68건(7.4%)
  component_clamped(계산값 cap 도달, A군): persistence 4건(0.4%)
상위 10%(D군) 축 원값 평균(6축 전부): occurrence 0.737, impact 0.634, exposure 0.877, persistence 0.318, compound 0.375, protection 0.211
상위 10% 가중 기여(공식 항별 평균): occ×imp×exp +0.420, persistence +0.318, compound +0.375, -protection -0.211 · cap-loss 평균 0.052
상위 10% 중 unresolved effect 연결 보유: 22/22 — 다수면 가중 확정 보류(감수 기준)
## compound 진단: compound>0 후보 55 · unresolved effect 연결 보유 3371(98%) · episode_count_only_violations 0(fixture 강제) · void_target_mismatch 0(구조적 — 전역 void)
## persistence 진단: unique cause lineages 1061 · 다기간 lineage 793 · candidate persistence 부여 1034 — 포트폴리오 원천은 lineage(후보 합산 금지)
## confidence: structural p50 0.600 · p90 0.800 · max 1.000 · n=915 | context p50 0.500 · p90 0.500 · max 1.000 · n=915
context 축 상태 합(A군): confirmed 68, conflicted 0, required 483, unknown 415

# 모집단 2 — profile overlay: C_high_exposure
## cohort 규모: A_structural_active 851 · B_eligible 967 · C_context_exposable 361 · D_rankable_positive 246 · E_blocked_insufficient 2445 · F_vulnerability_active 271
structural priority(A군): p50 0.160 · p90 0.368 · max 1.401 · n=851
rankable raw(C군): p50 0.003 · p90 0.584 · max 1.446 · n=361
rankable capped(C군): p50 0.003 · p90 0.584 · max 1.000 · n=361
비rankable(활성·capped=0): 605 — rankable 분포(D군 246)에 미포함(median 왜곡 방지)
## 도메인별 structural(A군) / rankable capped(D군)
  career         structural p50 0.075 · p90 0.680 · max 1.401 · n=58 | rankable p50 0.212 · p90 1.000 · max 1.000 · n=19
  contract_legal structural p50 0.160 · p90 0.360 · max 0.760 · n=208 | rankable p50 0.275 · p90 1.000 · max 1.000 · n=55
  finance        structural p50 0.160 · p90 0.425 · max 0.868 · n=194 | rankable p50 0.194 · p90 0.237 · max 0.657 · n=77
  health_safety  structural p50 0.180 · p90 0.368 · max 0.553 · n=136 | rankable p50 0.200 · p90 0.619 · max 0.869 · n=22
  relationship   structural p50 0.003 · p90 0.351 · max 0.859 · n=156 | rankable p50 0.121 · p90 0.502 · max 0.820 · n=46
  relocation     structural p50 0.160 · p90 0.250 · max 0.420 · n=99 | rankable p50 0.370 · p90 0.570 · max 0.950 · n=27
## 상한 집중 진단(D군 n=246):
  raw_gt_1 10건(4.1%) · raw_gt_1_2 8건(3.3%) · raw_ge_1 10건(4.1%) · capped_eq_1 10건(4.1%)
  raw p90 0.701 · p95 0.869 · p99 1.338
  capped=1 후보 risk_id 다양성: 4종
  상위 10% 동점: 8/24 · unique raw 16 — 다수 동점이면 R2 순위 분별력 저하(감수 판단)
  raw<0 0건(0.0%)(D군은 capped>0 정의라 0이어야 정상)
  net_priority_raw(C군): raw<0 175건(48.5%) · capped=0 175건 · protection로 0 하강 175건 — capped 하한 0·raw 보존
  exposure_at_max_rate(CONFIRMED 범주값 — 포화 아님): 112건(13.2%)
  component_clamped(계산값 cap 도달, A군): compound 10건(1.2%), persistence 4건(0.5%)
상위 10%(D군) 축 원값 평균(6축 전부): occurrence 0.698, impact 0.610, exposure 0.925, persistence 0.217, compound 0.573, protection 0.193
상위 10% 가중 기여(공식 항별 평균): occ×imp×exp +0.400, persistence +0.217, compound +0.573, -protection -0.192 · cap-loss 평균 0.104
상위 10% 중 unresolved effect 연결 보유: 24/24 — 다수면 가중 확정 보류(감수 기준)
## compound 진단: compound>0 후보 190 · unresolved effect 연결 보유 3371(98%) · episode_count_only_violations 0(fixture 강제) · void_target_mismatch 0(구조적 — 전역 void)
## persistence 진단: unique cause lineages 1061 · 다기간 lineage 793 · candidate persistence 부여 1034 — 포트폴리오 원천은 lineage(후보 합산 금지)
## confidence: structural p50 0.400 · p90 0.800 · max 1.000 · n=851 | context p50 0.500 · p90 1.000 · max 1.000 · n=851
context 축 상태 합(A군): confirmed 112, conflicted 0, required 415, unknown 303

# 모집단 2 — profile overlay: D_multi_selection
## cohort 규모: A_structural_active 933 · B_eligible 1047 · C_context_exposable 347 · D_rankable_positive 210 · E_blocked_insufficient 2572 · F_vulnerability_active 271
structural priority(A군): p50 0.160 · p90 0.385 · max 1.401 · n=933
rankable raw(C군): p50 -0.098 · p90 0.304 · max 1.221 · n=347
rankable capped(C군): p50 0.000 · p90 0.304 · max 1.000 · n=347
비rankable(활성·capped=0): 723 — rankable 분포(D군 210)에 미포함(median 왜곡 방지)
## 도메인별 structural(A군) / rankable capped(D군)
  career         structural p50 0.075 · p90 0.680 · max 1.401 · n=58 | rankable p50 0.304 · p90 1.000 · max 1.000 · n=20
  contract_legal structural p50 0.160 · p90 0.360 · max 0.760 · n=202 | rankable p50 0.200 · p90 0.200 · max 0.200 · n=28
  finance        structural p50 0.160 · p90 0.425 · max 0.868 · n=194 | rankable p50 0.194 · p90 0.237 · max 0.657 · n=77
  health_safety  structural p50 0.180 · p90 0.368 · max 0.553 · n=136 | rankable p50 0.200 · p90 0.394 · max 0.394 · n=16
  relationship   structural p50 0.003 · p90 0.351 · max 0.859 · n=161 | rankable p50 0.121 · p90 0.400 · max 0.584 · n=17
  relocation     structural p50 0.160 · p90 0.250 · max 0.420 · n=102 | rankable p50 0.124 · p90 0.138 · max 0.138 · n=6
  selection      structural p50 0.113 · p90 0.626 · max 0.976 · n=80 | rankable p50 0.350 · p90 0.600 · max 0.850 · n=46
## 상한 집중 진단(D군 n=210):
  raw_gt_1 3건(1.4%) · raw_gt_1_2 3건(1.4%) · raw_ge_1 3건(1.4%) · capped_eq_1 3건(1.4%)
  raw p90 0.444 · p95 0.600 · p99 1.216
  capped=1 후보 risk_id 다양성: 1종
  상위 10% 동점: 8/21 · unique raw 13 — 다수 동점이면 R2 순위 분별력 저하(감수 판단)
  raw<0 0건(0.0%)(D군은 capped>0 정의라 0이어야 정상)
  net_priority_raw(C군): raw<0 212건(61.1%) · capped=0 212건 · protection로 0 하강 212건 — capped 하한 0·raw 보존
  exposure_at_max_rate(CONFIRMED 범주값 — 포화 아님): 66건(7.1%)
  component_clamped(계산값 cap 도달, A군): persistence 4건(0.4%)
상위 10%(D군) 축 원값 평균(6축 전부): occurrence 0.748, impact 0.493, exposure 0.310, persistence 0.562, compound 0.071, protection 0.055
상위 10% 가중 기여(공식 항별 평균): occ×imp×exp +0.123, persistence +0.562, compound +0.071, -protection -0.055 · cap-loss 평균 0.031
상위 10% 중 unresolved effect 연결 보유: 21/21 — 다수면 가중 확정 보류(감수 기준)
## compound 진단: compound>0 후보 62 · unresolved effect 연결 보유 3578(98%) · episode_count_only_violations 0(fixture 강제) · void_target_mismatch 0(구조적 — 전역 void)
## persistence 진단: unique cause lineages 1061 · 다기간 lineage 793 · candidate persistence 부여 1144 — 포트폴리오 원천은 lineage(후보 합산 금지)
## confidence: structural p50 0.600 · p90 0.800 · max 1.000 · n=933 | context p50 0.500 · p90 0.500 · max 1.000 · n=933
context 축 상태 합(A군): confirmed 66, conflicted 0, required 496, unknown 430

## compound 증분 민감도(C overlay·기준 0.25)
  inc=0.00: top10 overlap 4/10 · 기준 top10 내 역전 29 · rankable>0 224 · compound가 최대 항 0
  inc=0.10: top10 overlap 7/10 · 기준 top10 내 역전 29 · rankable>0 238 · compound가 최대 항 6
  inc=0.15: top10 overlap 9/10 · 기준 top10 내 역전 26 · rankable>0 240 · compound가 최대 항 11
## exposure UNKNOWN 가중 ablation(기준 0.55)
  unknown_w=1.000: top10 overlap 10/10 · rankable>0 300
  unknown_w=0.775: top10 overlap 10/10 · rankable>0 264
  unknown_w=0.300: top10 overlap 10/10 · rankable>0 229

## pairwise golden(기대 순서 명시 — 감수 대상)
  같은 구조: CONFIRMED 0.300 > 허용 UNKNOWN 0.165 > 비노출 0.000 — PASS
  강한 구조+허용 UNKNOWN 0.308 vs 약한 구조+CONFIRMED 0.120 → 기대: 구조 우위 유지 — PASS
  근접 구조(0.55 vs 0.5)+노출 차이: UNKNOWN 0.181 vs CONFIRMED 0.300 → 기대: 근접 구조에선 확인된 현실이 우선 — PASS

## 단조성 검증: 8종 전부 단위 fixture로 고정(test_risk_scoring_r1a — 원인 추가↛occ 감소·protection↛priority 증가·CONFIRMED→UNKNOWN↛증가·supporting/vuln↛occ 증가·무관 episode 불변·입력 순서 byte 불변·same-role episode 추가↛compound 증가·보조 cause 증감↛persistence 감소)
