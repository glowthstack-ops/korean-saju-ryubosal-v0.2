> R1-T/R2-a2 전수 측정 고정본(감수 36차) — 재생성: `python scripts/risk_scoring_survey.py`
> 출력 결정적 — 본 파일과의 diff = 점수 의미 회귀 신호.

# R1-c1 위험 점수 전수 측정 — risk-score-r1.2.0-shadow
semantics cause-semantics-v3 · config 6b2d452d8c23d425 · semantics 607f75c4a8dfc72c
compound=연결된 effect graph(shared canonical cause)만 · is_question_target=context confidence 제외(fixture 고정)

# 모집단 1 — 전체 구조 코퍼스(컨텍스트 없음·suppression baseline 동일)
## cohort 규모: A_structural_active 914 · B_eligible 1028 · C_context_exposable 281 · D_rankable_positive 281 · E_blocked_insufficient 2384 · F_vulnerability_active 271
structural priority(A군): p50 0.195 · p90 0.362 · max 0.802 · n=914
rankable raw(C군): p50 0.118 · p90 0.203 · max 0.441 · n=281
rankable capped(C군): p50 0.118 · p90 0.203 · max 0.441 · n=281
비rankable(활성·capped=0): 633 — rankable 분포(D군 281)에 미포함(median 왜곡 방지)
## 도메인별 structural(A군) / rankable capped(D군)
  career         structural p50 0.226 · p90 0.399 · max 0.802 · n=58 | rankable p50 0.125 · p90 0.317 · max 0.441 · n=54
  contract_legal structural p50 0.175 · p90 0.304 · max 0.672 · n=202 | rankable p50 0.000 · p90 0.000 · max 0.000 · n=0
  finance        structural p50 0.193 · p90 0.379 · max 0.662 · n=194 | rankable p50 0.129 · p90 0.213 · max 0.364 · n=126
  health_safety  structural p50 0.180 · p90 0.346 · max 0.423 · n=136 | rankable p50 0.158 · p90 0.233 · max 0.233 · n=14
  relationship   structural p50 0.202 · p90 0.362 · max 0.643 · n=161 | rankable p50 0.088 · p90 0.166 · max 0.258 · n=56
  relocation     structural p50 0.225 · p90 0.315 · max 0.420 · n=102 | rankable p50 0.096 · p90 0.138 · max 0.140 · n=31
  selection      structural p50 0.270 · p90 0.399 · max 0.601 · n=61 | rankable p50 0.000 · p90 0.000 · max 0.000 · n=0
## 상한 집중 진단(D군 n=281):
  raw_gt_1 0건(0.0%) · raw_gt_1_2 0건(0.0%) · raw_ge_1 0건(0.0%) · capped_eq_1 0건(0.0%)
  raw p90 0.203 · p95 0.239 · p99 0.364
  capped=1 후보 risk_id 다양성: 0종
  상위 10% 동점: 5/28 · unique raw 23 — 다수 동점이면 R2 순위 분별력 저하(감수 판단)
  raw<0 0건(0.0%)(D군은 capped>0 정의라 0이어야 정상)
  net_priority_raw(C군): raw<0 0건(0.0%) · capped=0 0건 · protection로 0 하강 0건 — capped 하한 0·raw 보존
  exposure_at_max_rate(CONFIRMED 범주값 — 포화 아님): 0건(0.0%)
  component_clamped(계산값 cap 도달, A군): persistence 4건(0.4%)
상위 10%(D군) 축 원값 평균(6축 전부): occurrence 0.810, impact 0.573, exposure 0.550, persistence 0.286, compound 0.000, protection 0.133
상위 10% 가중 기여(공식 항별 평균): base(E×B) +0.217, persistence항 +0.060, compound항 +0.000, -protection손실 -0.049 · cap-loss 평균 0.000
상위 10% 중 unresolved effect 연결 보유: 28/28 — 다수면 가중 확정 보류(감수 기준)
## compound 진단: compound>0 후보 0 · unresolved effect 연결 보유 3371(98%) · episode_count_only_violations 0(fixture 강제) · void_target_mismatch 0(구조적 — 전역 void)
## persistence 진단: unique cause lineages 1061 · 다기간 lineage 793 · candidate persistence 부여 1034 — 포트폴리오 원천은 lineage(후보 합산 금지)
## confidence: structural p50 0.600 · p90 0.800 · max 1.000 · n=914 | context p50 0.500 · p90 0.500 · max 0.500 · n=914
context 축 상태 합(A군): confirmed 0, conflicted 0, required 477, unknown 477

# 모집단 2 — profile overlay: A_all_unknown
## cohort 규모: A_structural_active 914 · B_eligible 1028 · C_context_exposable 281 · D_rankable_positive 281 · E_blocked_insufficient 2384 · F_vulnerability_active 271
structural priority(A군): p50 0.195 · p90 0.362 · max 0.802 · n=914
rankable raw(C군): p50 0.118 · p90 0.203 · max 0.441 · n=281
rankable capped(C군): p50 0.118 · p90 0.203 · max 0.441 · n=281
비rankable(활성·capped=0): 633 — rankable 분포(D군 281)에 미포함(median 왜곡 방지)
## 도메인별 structural(A군) / rankable capped(D군)
  career         structural p50 0.226 · p90 0.399 · max 0.802 · n=58 | rankable p50 0.125 · p90 0.317 · max 0.441 · n=54
  contract_legal structural p50 0.175 · p90 0.304 · max 0.672 · n=202 | rankable p50 0.000 · p90 0.000 · max 0.000 · n=0
  finance        structural p50 0.193 · p90 0.379 · max 0.662 · n=194 | rankable p50 0.129 · p90 0.213 · max 0.364 · n=126
  health_safety  structural p50 0.180 · p90 0.346 · max 0.423 · n=136 | rankable p50 0.158 · p90 0.233 · max 0.233 · n=14
  relationship   structural p50 0.202 · p90 0.362 · max 0.643 · n=161 | rankable p50 0.088 · p90 0.166 · max 0.258 · n=56
  relocation     structural p50 0.225 · p90 0.315 · max 0.420 · n=102 | rankable p50 0.096 · p90 0.138 · max 0.140 · n=31
  selection      structural p50 0.270 · p90 0.399 · max 0.601 · n=61 | rankable p50 0.000 · p90 0.000 · max 0.000 · n=0
## 상한 집중 진단(D군 n=281):
  raw_gt_1 0건(0.0%) · raw_gt_1_2 0건(0.0%) · raw_ge_1 0건(0.0%) · capped_eq_1 0건(0.0%)
  raw p90 0.203 · p95 0.239 · p99 0.364
  capped=1 후보 risk_id 다양성: 0종
  상위 10% 동점: 5/28 · unique raw 23 — 다수 동점이면 R2 순위 분별력 저하(감수 판단)
  raw<0 0건(0.0%)(D군은 capped>0 정의라 0이어야 정상)
  net_priority_raw(C군): raw<0 0건(0.0%) · capped=0 0건 · protection로 0 하강 0건 — capped 하한 0·raw 보존
  exposure_at_max_rate(CONFIRMED 범주값 — 포화 아님): 0건(0.0%)
  component_clamped(계산값 cap 도달, A군): persistence 4건(0.4%)
상위 10%(D군) 축 원값 평균(6축 전부): occurrence 0.810, impact 0.573, exposure 0.550, persistence 0.286, compound 0.000, protection 0.133
상위 10% 가중 기여(공식 항별 평균): base(E×B) +0.217, persistence항 +0.060, compound항 +0.000, -protection손실 -0.049 · cap-loss 평균 0.000
상위 10% 중 unresolved effect 연결 보유: 28/28 — 다수면 가중 확정 보류(감수 기준)
## compound 진단: compound>0 후보 0 · unresolved effect 연결 보유 3371(98%) · episode_count_only_violations 0(fixture 강제) · void_target_mismatch 0(구조적 — 전역 void)
## persistence 진단: unique cause lineages 1061 · 다기간 lineage 793 · candidate persistence 부여 1034 — 포트폴리오 원천은 lineage(후보 합산 금지)
## confidence: structural p50 0.600 · p90 0.800 · max 1.000 · n=914 | context p50 0.500 · p90 0.500 · max 0.500 · n=914
context 축 상태 합(A군): confirmed 0, conflicted 0, required 477, unknown 477

# 모집단 2 — profile overlay: B_typical_confirmed
## cohort 규모: A_structural_active 915 · B_eligible 1028 · C_context_exposable 344 · D_rankable_positive 344 · E_blocked_insufficient 2384 · F_vulnerability_active 271
structural priority(A군): p50 0.195 · p90 0.362 · max 0.802 · n=915
rankable raw(C군): p50 0.136 · p90 0.279 · max 0.728 · n=344
rankable capped(C군): p50 0.136 · p90 0.279 · max 0.728 · n=344
비rankable(활성·capped=0): 571 — rankable 분포(D군 344)에 미포함(median 왜곡 방지)
## 도메인별 structural(A군) / rankable capped(D군)
  career         structural p50 0.226 · p90 0.399 · max 0.802 · n=58 | rankable p50 0.125 · p90 0.317 · max 0.441 · n=54
  contract_legal structural p50 0.192 · p90 0.307 · max 0.672 · n=208 | rankable p50 0.348 · p90 0.573 · max 0.728 · n=32
  finance        structural p50 0.193 · p90 0.379 · max 0.662 · n=194 | rankable p50 0.129 · p90 0.213 · max 0.364 · n=126
  health_safety  structural p50 0.180 · p90 0.346 · max 0.423 · n=136 | rankable p50 0.158 · p90 0.233 · max 0.233 · n=14
  relationship   structural p50 0.202 · p90 0.362 · max 0.643 · n=156 | rankable p50 0.134 · p90 0.231 · max 0.451 · n=87
  relocation     structural p50 0.225 · p90 0.315 · max 0.420 · n=102 | rankable p50 0.096 · p90 0.138 · max 0.140 · n=31
  selection      structural p50 0.270 · p90 0.399 · max 0.601 · n=61 | rankable p50 0.000 · p90 0.000 · max 0.000 · n=0
## 상한 집중 진단(D군 n=344):
  raw_gt_1 0건(0.0%) · raw_gt_1_2 0건(0.0%) · raw_ge_1 0건(0.0%) · capped_eq_1 0건(0.0%)
  raw p90 0.279 · p95 0.368 · p99 0.573
  capped=1 후보 risk_id 다양성: 0종
  상위 10% 동점: 9/34 · unique raw 25 — 다수 동점이면 R2 순위 분별력 저하(감수 판단)
  raw<0 0건(0.0%)(D군은 capped>0 정의라 0이어야 정상)
  net_priority_raw(C군): raw<0 0건(0.0%) · capped=0 0건 · protection로 0 하강 0건 — capped 하한 0·raw 보존
  exposure_at_max_rate(CONFIRMED 범주값 — 포화 아님): 68건(7.4%)
  component_clamped(계산값 cap 도달, A군): persistence 4건(0.4%)
상위 10%(D군) 축 원값 평균(6축 전부): occurrence 0.742, impact 0.625, exposure 0.868, persistence 0.212, compound 0.112, protection 0.156
상위 10% 가중 기여(공식 항별 평균): base(E×B) +0.328, persistence항 +0.054, compound항 +0.037, -protection손실 -0.099 · cap-loss 평균 0.000
상위 10% 중 unresolved effect 연결 보유: 34/34 — 다수면 가중 확정 보류(감수 기준)
## compound 진단: compound>0 후보 55 · unresolved effect 연결 보유 3371(98%) · episode_count_only_violations 0(fixture 강제) · void_target_mismatch 0(구조적 — 전역 void)
## persistence 진단: unique cause lineages 1061 · 다기간 lineage 793 · candidate persistence 부여 1034 — 포트폴리오 원천은 lineage(후보 합산 금지)
## confidence: structural p50 0.600 · p90 0.800 · max 1.000 · n=915 | context p50 0.500 · p90 0.500 · max 1.000 · n=915
context 축 상태 합(A군): confirmed 68, conflicted 0, required 483, unknown 415

# 모집단 2 — profile overlay: C_high_exposure
## cohort 규모: A_structural_active 851 · B_eligible 967 · C_context_exposable 361 · D_rankable_positive 361 · E_blocked_insufficient 2445 · F_vulnerability_active 271
structural priority(A군): p50 0.192 · p90 0.351 · max 0.802 · n=851
rankable raw(C군): p50 0.149 · p90 0.346 · max 0.728 · n=361
rankable capped(C군): p50 0.149 · p90 0.346 · max 0.728 · n=361
비rankable(활성·capped=0): 490 — rankable 분포(D군 361)에 미포함(median 왜곡 방지)
## 도메인별 structural(A군) / rankable capped(D군)
  career         structural p50 0.226 · p90 0.399 · max 0.802 · n=58 | rankable p50 0.125 · p90 0.219 · max 0.441 · n=58
  contract_legal structural p50 0.192 · p90 0.307 · max 0.672 · n=208 | rankable p50 0.363 · p90 0.612 · max 0.728 · n=32
  finance        structural p50 0.193 · p90 0.379 · max 0.662 · n=194 | rankable p50 0.129 · p90 0.213 · max 0.364 · n=126
  health_safety  structural p50 0.180 · p90 0.346 · max 0.423 · n=136 | rankable p50 0.194 · p90 0.405 · max 0.442 · n=20
  relationship   structural p50 0.202 · p90 0.362 · max 0.643 · n=156 | rankable p50 0.134 · p90 0.254 · max 0.496 · n=87
  relocation     structural p50 0.225 · p90 0.315 · max 0.420 · n=99 | rankable p50 0.225 · p90 0.346 · max 0.462 · n=38
## 상한 집중 진단(D군 n=361):
  raw_gt_1 0건(0.0%) · raw_gt_1_2 0건(0.0%) · raw_ge_1 0건(0.0%) · capped_eq_1 0건(0.0%)
  raw p90 0.346 · p95 0.429 · p99 0.612
  capped=1 후보 risk_id 다양성: 0종
  상위 10% 동점: 11/36 · unique raw 25 — 다수 동점이면 R2 순위 분별력 저하(감수 판단)
  raw<0 0건(0.0%)(D군은 capped>0 정의라 0이어야 정상)
  net_priority_raw(C군): raw<0 0건(0.0%) · capped=0 0건 · protection로 0 하강 0건 — capped 하한 0·raw 보존
  exposure_at_max_rate(CONFIRMED 범주값 — 포화 아님): 112건(13.2%)
  component_clamped(계산값 cap 도달, A군): persistence 4건(0.5%)
상위 10%(D군) 축 원값 평균(6축 전부): occurrence 0.729, impact 0.613, exposure 0.938, persistence 0.161, compound 0.153, protection 0.147
상위 10% 가중 기여(공식 항별 평균): base(E×B) +0.348, persistence항 +0.043, compound항 +0.052, -protection손실 -0.097 · cap-loss 평균 0.000
상위 10% 중 unresolved effect 연결 보유: 36/36 — 다수면 가중 확정 보류(감수 기준)
## compound 진단: compound>0 후보 190 · unresolved effect 연결 보유 3371(98%) · episode_count_only_violations 0(fixture 강제) · void_target_mismatch 0(구조적 — 전역 void)
## persistence 진단: unique cause lineages 1061 · 다기간 lineage 793 · candidate persistence 부여 1034 — 포트폴리오 원천은 lineage(후보 합산 금지)
## confidence: structural p50 0.400 · p90 0.800 · max 1.000 · n=851 | context p50 0.500 · p90 1.000 · max 1.000 · n=851
context 축 상태 합(A군): confirmed 112, conflicted 0, required 415, unknown 303

# 모집단 2 — profile overlay: D_multi_selection
## cohort 규모: A_structural_active 933 · B_eligible 1047 · C_context_exposable 347 · D_rankable_positive 347 · E_blocked_insufficient 2572 · F_vulnerability_active 271
structural priority(A군): p50 0.195 · p90 0.362 · max 0.802 · n=933
rankable raw(C군): p50 0.135 · p90 0.258 · max 0.441 · n=347
rankable capped(C군): p50 0.135 · p90 0.258 · max 0.441 · n=347
비rankable(활성·capped=0): 586 — rankable 분포(D군 347)에 미포함(median 왜곡 방지)
## 도메인별 structural(A군) / rankable capped(D군)
  career         structural p50 0.226 · p90 0.399 · max 0.802 · n=58 | rankable p50 0.129 · p90 0.304 · max 0.441 · n=58
  contract_legal structural p50 0.175 · p90 0.304 · max 0.672 · n=202 | rankable p50 0.000 · p90 0.000 · max 0.000 · n=0
  finance        structural p50 0.193 · p90 0.379 · max 0.662 · n=194 | rankable p50 0.129 · p90 0.213 · max 0.364 · n=126
  health_safety  structural p50 0.180 · p90 0.346 · max 0.423 · n=136 | rankable p50 0.158 · p90 0.233 · max 0.233 · n=14
  relationship   structural p50 0.202 · p90 0.362 · max 0.643 · n=161 | rankable p50 0.088 · p90 0.166 · max 0.258 · n=56
  relocation     structural p50 0.225 · p90 0.315 · max 0.420 · n=102 | rankable p50 0.096 · p90 0.138 · max 0.140 · n=31
  selection      structural p50 0.256 · p90 0.412 · max 0.601 · n=80 | rankable p50 0.243 · p90 0.399 · max 0.412 · n=62
## 상한 집중 진단(D군 n=347):
  raw_gt_1 0건(0.0%) · raw_gt_1_2 0건(0.0%) · raw_ge_1 0건(0.0%) · capped_eq_1 0건(0.0%)
  raw p90 0.258 · p95 0.317 · p99 0.412
  capped=1 후보 risk_id 다양성: 0종
  상위 10% 동점: 19/34 · unique raw 15 — 다수 동점이면 R2 순위 분별력 저하(감수 판단)
  raw<0 0건(0.0%)(D군은 capped>0 정의라 0이어야 정상)
  net_priority_raw(C군): raw<0 0건(0.0%) · capped=0 0건 · protection로 0 하강 0건 — capped 하한 0·raw 보존
  exposure_at_max_rate(CONFIRMED 범주값 — 포화 아님): 66건(7.1%)
  component_clamped(계산값 cap 도달, A군): persistence 4건(0.4%)
상위 10%(D군) 축 원값 평균(6축 전부): occurrence 0.741, impact 0.534, exposure 0.868, persistence 0.171, compound 0.000, protection 0.079
상위 10% 가중 기여(공식 항별 평균): base(E×B) +0.304, persistence항 +0.039, compound항 +0.000, -protection손실 -0.033 · cap-loss 평균 0.000
상위 10% 중 unresolved effect 연결 보유: 34/34 — 다수면 가중 확정 보류(감수 기준)
## compound 진단: compound>0 후보 61 · unresolved effect 연결 보유 3578(98%) · episode_count_only_violations 0(fixture 강제) · void_target_mismatch 0(구조적 — 전역 void)
## persistence 진단: unique cause lineages 1061 · 다기간 lineage 793 · candidate persistence 부여 1144 — 포트폴리오 원천은 lineage(후보 합산 금지)
## confidence: structural p50 0.600 · p90 0.800 · max 1.000 · n=933 | context p50 0.500 · p90 0.500 · max 1.000 · n=933
context 축 상태 합(A군): confirmed 66, conflicted 0, required 496, unknown 430

## effect role taxonomy audit(감수 32차)
  항목 49 · role 41종 · singleton 34 · 공유 7 · 도메인 간 공유 2종(['document_defect', 'result_wait_delay'])
  공유 role: document_defect(2), financial_outflow(2), payment_recovery(2), relationship_conflict(2), result_wait_delay(3), selection_outcome(2), vitality_load(2)
  shared-cause 연결쌍: same-role 0 · different-role 68 · unresolved 1873

## shared-cause different-role 연결쌍(unique 조합 16 — 감수 재료)
    13× LEG_COMPLIANCE_OBLIGATION_PRESSURE[compliance_obligation] ↔ LEG_DISPUTE_RISK[legal_dispute]
    10× MOV_RELOCATION_PRESSURE[relocation_pressure] ↔ REL_PARTNER_READJUST[partner_readjustment]
     8× MOV_CONTRACT_SETBACK_RISK[contract_setback] ↔ REL_PARTNER_READJUST[partner_readjustment]
     5× LEG_COMPLIANCE_OBLIGATION_PRESSURE[compliance_obligation] ↔ LEG_CONTRACT_TERMINATION_RISK[contract_termination]
     5× LEG_CONTRACT_TERMINATION_RISK[contract_termination] ↔ LEG_DISPUTE_RISK[legal_dispute]
     4× HLT_TREATMENT_RECOVERY_LOAD[treatment_management] ↔ MOV_CONTRACT_SETBACK_RISK[contract_setback]
     4× LEG_COMPLIANCE_OBLIGATION_PRESSURE[compliance_obligation] ↔ REL_PARTNER_READJUST[partner_readjustment]
     4× LEG_DISPUTE_RISK[legal_dispute] ↔ REL_PARTNER_READJUST[partner_readjustment]
     3× LEG_CONTRACT_TERMINATION_RISK[contract_termination] ↔ MOV_RELOCATION_PRESSURE[relocation_pressure]
     2× HLT_TREATMENT_RECOVERY_LOAD[treatment_management] ↔ REL_PARTNER_READJUST[partner_readjustment]
     2× LEG_COMPLIANCE_OBLIGATION_PRESSURE[compliance_obligation] ↔ MOV_RELOCATION_PRESSURE[relocation_pressure]
     2× LEG_CONTRACT_TERMINATION_RISK[contract_termination] ↔ MOV_CONTRACT_SETBACK_RISK[contract_setback]
     2× LEG_CONTRACT_TERMINATION_RISK[contract_termination] ↔ REL_PARTNER_READJUST[partner_readjustment]
     2× LEG_DISPUTE_RISK[legal_dispute] ↔ MOV_RELOCATION_PRESSURE[relocation_pressure]
     1× HLT_TREATMENT_RECOVERY_LOAD[treatment_management] ↔ MOV_SCHEDULE_DISRUPTION[schedule_disruption]
     1× MOV_CONTRACT_SETBACK_RISK[contract_setback] ↔ MOV_SCHEDULE_DISRUPTION[schedule_disruption]

## ByContext 자동 탐색(context branch 2+ 항목)
  HLT_EXISTING_CONDITION_STRAIN: branches=['existing_condition', 'current_symptom'] · ByContext 단일 base role
  HLT_TREATMENT_RECOVERY_LOAD: branches=['treatment_process', 'recovery_process'] · ByContext 저작됨
  HLT_PHYSICAL_WORKLOAD_STRAIN: branches=['physical_workload', 'sleep_schedule_load'] · ByContext 단일 base role

## capped=1 후보 상세(0건 — 개별 감수 재료)

## compound 증분 민감도(C overlay·기준 0.10 — 0.25는 기각(감수 32차))
  inc=0.00: top10 overlap 8/10 · 기준 top10 내 역전 4 · rankable>0 361 · compound 항이 persistence 우위 0 · top10 신규 진입 2
  inc=0.15: top10 overlap 10/10 · 기준 top10 내 역전 9 · rankable>0 361 · compound 항이 persistence 우위 0 · top10 신규 진입 0
  inc=0.25: top10 overlap 7/10 · 기준 top10 내 역전 11 · rankable>0 361 · compound 항이 persistence 우위 0 · top10 신규 진입 3
## exposure UNKNOWN 가중 ablation(기준 0.55)
  unknown_w=1.000: top10 overlap 6/10 · rankable>0 361
  unknown_w=0.775: top10 overlap 7/10 · rankable>0 361
  unknown_w=0.300: top10 overlap 7/10 · rankable>0 361

## UNKNOWN 가중 국소 민감도(기준 0.55 — 감수 33차)
  UNKNOWN-only cohort(양수): n=249 · p50 0.125 · p90 0.210
  w=0.40: top25 overlap 22/25(88%) · top50 43/50 · threshold crossing 0 · CONFIRMED 최고점 추월 UNKNOWN 0
  w=0.50: top25 overlap 25/25(100%) · top50 50/50 · threshold crossing 0 · CONFIRMED 최고점 추월 UNKNOWN 0
  w=0.60: top25 overlap 23/25(92%) · top50 50/50 · threshold crossing 0 · CONFIRMED 최고점 추월 UNKNOWN 0
  w=0.70: top25 overlap 20/25(80%) · top50 47/50 · threshold crossing 0 · CONFIRMED 최고점 추월 UNKNOWN 0
  승인 기준(0.50↔0.60 top-25 ≥85%): PASS

## 교운기 overlay(커널 SSOT — 이벤트 엔진 함수 공유)
  교운일(w=1.000): 평균 상승률 27.0% · top10 overlap 6/10(신규 4) · transition이 최대 modifier 249 · capped=1 4
  ±1년(w=0.368): 평균 상승률 9.9% · top10 overlap 8/10(신규 2) · transition이 최대 modifier 210 · capped=1 0
  ±2년(w=0.135): 평균 상승률 3.6% · top10 overlap 9/10(신규 1) · transition이 최대 modifier 185 · capped=1 0

## pairwise golden(기대 순서 명시 — 감수 대상)
  같은 구조: CONFIRMED 0.300 > 허용 UNKNOWN 0.165 > 비노출 0.000 — PASS
  강한 구조+허용 UNKNOWN 0.308 vs 약한 구조+CONFIRMED 0.120 → 기대: 구조 우위 유지 — PASS
  근접 구조(0.55 vs 0.5)+노출 차이: UNKNOWN 0.181 vs CONFIRMED 0.300 → 기대: 근접 구조에선 확인된 현실이 우선 — PASS

## persistence span 비교·pairwise(감수 32차 — 기대 순서 명시)
  span=5: 강한 단기 0.560 vs 약한 6개월 지속 0.240(기대: 단기 우위 PASS) · 중간 4개월 지속 0.480(단기 우위)
  span=8: 강한 단기 0.560 vs 약한 6개월 지속 0.195(기대: 단기 우위 PASS) · 중간 4개월 지속 0.412(단기 우위)
  span=12: 강한 단기 0.560 vs 약한 6개월 지속 0.170(기대: 단기 우위 PASS) · 중간 4개월 지속 0.375(단기 우위)

## protection pairwise(비례 완화)
  보호 없음 0.300 > 약한 보호 0.210 > 강한 보호 0.060 — PASS(강한 보호도 0으로 소거하지 않음 — 완화이지 삭제 아님)

## 단조성 검증: 8종 전부 단위 fixture로 고정(test_risk_scoring_r1a — 원인 추가↛occ 감소·protection↛priority 증가·CONFIRMED→UNKNOWN↛증가·supporting/vuln↛occ 증가·무관 episode 불변·입력 순서 byte 불변·same-role episode 추가↛compound 증가·보조 cause 증감↛persistence 감소)
