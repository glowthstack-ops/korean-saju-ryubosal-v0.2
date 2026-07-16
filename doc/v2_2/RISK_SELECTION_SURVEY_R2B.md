> R2-b/R2-c 전수 선별 측정 고정본(감수 39차 — MAX_BONUS 0.20 확정·REL medium·primaryOwnership 사전 계약 소비) — 재생성: `python scripts/risk_selection_survey.py`
> 출력 결정적 — 본 파일과의 diff = 선별 의미 회귀 신호.

# R2-b 위험 선별 전수 측정 — risk-select-r2.1.0-shadow
scoring risk-score-r1.2.1-shadow · policy 00776ae5464df8cb · transition 49df076a0ad56cc1
episode 병합=차트 단위 · budget hard_max 3 · 교운일 커널 w=1.000(2026-06-01) — MAX_BONUS 0.20 확정·REL_PARTNER_READJUST medium(감수 39차)·ownership=사전 primaryOwnership 계약

## profile A_all_unknown — episode 형성·선별
  episode 735 · key 분포 fallback 735
  reality identity: 없음
  구성원 크기: p50 1.000 · p90 2.000 · max 17.000 · n=735 · 다도메인 episode 0
  대표 보유 215/735 · ownership 대표 0 · 도메인 career 41 · finance 105 · health_safety 14 · relationship 37 · relocation 18
  context confidence(대표 보유): p50 0.300 · p90 0.300 · max 0.300 · n=215
  budget(hard_max 3): 선택 p50 3.000 · p90 3.000 · max 3.000 · n=10 · 누락 BUDGET_HARD_MAX 10 · LOWER_PRIORITY 175 · NO_EXPOSABLE_REPRESENTATIVE 520
  recovery: 산출 142 · earliest 142 · stable 95 · 사유 all_primary_causes_quiet 95 · cause_relief 218 · other_primary_cause_ongoing 8 · right_censored_quiet_span 39
  portfolio 원천: unique cause 합 226(후보 점수 합산 없음 — 진단 표 원천)
  fallback 분리 잔존 진단(같은 대상·family ≥3 — cause 상이·비인접의 fail-closed 분리, under-merge 후보군): 69
  proxy audit(risk_id static): ownership_not_applicable 14 · proxy_match 34 · proxy_mismatch 1
  proxy audit(behavioral): 후보 rank 불일치 0 · proxy였다면 대표가 달라졌을 episode 0

## A-T 교운 overlay(episode 압축 이후 기준)
  ### medium(확정안) × MAX_BONUS=0.20 (교운일 w=1.0)
    [candidate] 평균 상승률 9.4% · top10 신규 진입 risk_id: CAR_REASSIGNMENT_RISK(3) · MOV_RELOCATION_PRESSURE(1) · CAR_EXIT_PRESSURE(1)
    [candidate] 민감도별 평균 상승률: high 20.0% · low 5.0% · medium 12.0%
    [episode] top10 overlap 10/10 · 신규 없음
    [episode] 대표 변경 12 · 도메인 대표 변경 5 · ownership 유지 0 · ownership override 0 · budget 선택 변경 차트 5
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 2
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### medium(비교 0.30) × MAX_BONUS=0.30 (교운일 w=1.0)
    [candidate] 평균 상승률 14.1% · top10 신규 진입 risk_id: CAR_REASSIGNMENT_RISK(5) · MOV_RELOCATION_PRESSURE(4) · CAR_EXIT_PRESSURE(1) · CAR_EVALUATION_SETBACK_RISK(1)
    [candidate] 민감도별 평균 상승률: high 30.0% · low 7.5% · medium 18.0%
    [episode] top10 overlap 10/10 · 신규 없음
    [episode] 대표 변경 12 · 도메인 대표 변경 5 · ownership 유지 0 · ownership override 0 · budget 선택 변경 차트 7
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 2
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### high(비교안) × MAX_BONUS=0.20 (교운일 w=1.0)
    [candidate] 평균 상승률 9.4% · top10 신규 진입 risk_id: CAR_REASSIGNMENT_RISK(3) · MOV_RELOCATION_PRESSURE(1) · CAR_EXIT_PRESSURE(1)
    [candidate] 민감도별 평균 상승률: high 20.0% · low 5.0% · medium 12.0%
    [episode] top10 overlap 10/10 · 신규 없음
    [episode] 대표 변경 12 · 도메인 대표 변경 5 · ownership 유지 0 · ownership override 0 · budget 선택 변경 차트 5
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 2
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### high(비교안) × MAX_BONUS=0.30 (교운일 w=1.0)
    [candidate] 평균 상승률 14.1% · top10 신규 진입 risk_id: CAR_REASSIGNMENT_RISK(5) · MOV_RELOCATION_PRESSURE(4) · CAR_EXIT_PRESSURE(1) · CAR_EVALUATION_SETBACK_RISK(1)
    [candidate] 민감도별 평균 상승률: high 30.0% · low 7.5% · medium 18.0%
    [episode] top10 overlap 10/10 · 신규 없음
    [episode] 대표 변경 12 · 도메인 대표 변경 5 · ownership 유지 0 · ownership override 0 · budget 선택 변경 차트 7
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 2
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### 참고 — medium(확정안)×0.20, ±1년(w=0.368): episode top10 overlap 10/10

## profile B_typical_confirmed — episode 형성·선별
  episode 715 · key 분포 explicit 16 · fallback 699
  reality identity: 없음
  구성원 크기: p50 1.000 · p90 2.000 · max 17.000 · n=715 · 다도메인 episode 0
  대표 보유 227/715 · ownership 대표 16 · 도메인 career 41 · contract_legal 6 · finance 105 · health_safety 14 · relationship 43 · relocation 18
  context confidence(대표 보유): p50 0.300 · p90 0.300 · max 0.900 · n=227
  budget(hard_max 3): 선택 p50 3.000 · p90 3.000 · max 3.000 · n=10 · 누락 BUDGET_HARD_MAX 10 · LOWER_PRIORITY 187 · NO_EXPOSABLE_REPRESENTATIVE 488
  recovery: 산출 154 · earliest 154 · stable 100 · 사유 all_primary_causes_quiet 100 · cause_relief 235 · other_primary_cause_ongoing 8 · right_censored_quiet_span 46
  portfolio 원천: unique cause 합 226(후보 점수 합산 없음 — 진단 표 원천)
  fallback 분리 잔존 진단(같은 대상·family ≥3 — cause 상이·비인접의 fail-closed 분리, under-merge 후보군): 67
  proxy audit(risk_id static): ownership_not_applicable 14 · proxy_match 34 · proxy_mismatch 1
  proxy audit(behavioral): 후보 rank 불일치 0 · proxy였다면 대표가 달라졌을 episode 0

## B-T 교운 overlay(episode 압축 이후 기준)
  ### medium(확정안) × MAX_BONUS=0.20 (교운일 w=1.0)
    [candidate] 평균 상승률 9.9% · top10 신규 진입 risk_id: REL_PARTNER_READJUST(2) · MOV_RELOCATION_PRESSURE(2) · LEG_CONTRACT_TERMINATION_RISK(1) · CAR_REASSIGNMENT_RISK(1)
    [candidate] 민감도별 평균 상승률: high 20.0% · low 5.0% · medium 12.0%
    [episode] top10 overlap 9/10 · 신규 CAR_EXIT_PRESSURE
    [episode] 대표 변경 10 · 도메인 대표 변경 3 · ownership 유지 16 · ownership override 0 · budget 선택 변경 차트 3
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 1
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### medium(비교 0.30) × MAX_BONUS=0.30 (교운일 w=1.0)
    [candidate] 평균 상승률 14.9% · top10 신규 진입 risk_id: REL_PARTNER_READJUST(3) · MOV_RELOCATION_PRESSURE(2) · LEG_CONTRACT_TERMINATION_RISK(1) · CAR_REASSIGNMENT_RISK(1)
    [candidate] 민감도별 평균 상승률: high 30.0% · low 7.5% · medium 18.0%
    [episode] top10 overlap 9/10 · 신규 CAR_EXIT_PRESSURE
    [episode] 대표 변경 10 · 도메인 대표 변경 3 · ownership 유지 16 · ownership override 0 · budget 선택 변경 차트 4
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 1
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### high(비교안) × MAX_BONUS=0.20 (교운일 w=1.0)
    [candidate] 평균 상승률 9.9% · top10 신규 진입 risk_id: REL_PARTNER_READJUST(2) · MOV_RELOCATION_PRESSURE(2) · LEG_CONTRACT_TERMINATION_RISK(1) · CAR_REASSIGNMENT_RISK(1)
    [candidate] 민감도별 평균 상승률: high 20.0% · low 5.0% · medium 12.0%
    [episode] top10 overlap 9/10 · 신규 CAR_EXIT_PRESSURE
    [episode] 대표 변경 10 · 도메인 대표 변경 3 · ownership 유지 16 · ownership override 0 · budget 선택 변경 차트 3
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 1
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### high(비교안) × MAX_BONUS=0.30 (교운일 w=1.0)
    [candidate] 평균 상승률 14.9% · top10 신규 진입 risk_id: REL_PARTNER_READJUST(3) · MOV_RELOCATION_PRESSURE(2) · LEG_CONTRACT_TERMINATION_RISK(1) · CAR_REASSIGNMENT_RISK(1)
    [candidate] 민감도별 평균 상승률: high 30.0% · low 7.5% · medium 18.0%
    [episode] top10 overlap 9/10 · 신규 CAR_EXIT_PRESSURE
    [episode] 대표 변경 10 · 도메인 대표 변경 3 · ownership 유지 16 · ownership override 0 · budget 선택 변경 차트 4
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 1
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### 참고 — medium(확정안)×0.20, ±1년(w=0.368): episode top10 overlap 10/10

## profile C_high_exposure — episode 형성·선별
  episode 653 · key 분포 explicit 29 · fallback 624
  reality identity: 없음
  구성원 크기: p50 1.000 · p90 2.000 · max 17.000 · n=653 · 다도메인 episode 0
  대표 보유 225/653 · ownership 대표 29 · 도메인 career 44 · contract_legal 6 · finance 105 · health_safety 17 · relationship 43 · relocation 10
  context confidence(대표 보유): p50 0.300 · p90 0.900 · max 0.900 · n=225
  budget(hard_max 3): 선택 p50 3.000 · p90 3.000 · max 3.000 · n=10 · 누락 BUDGET_HARD_MAX 10 · LOWER_PRIORITY 185 · NO_EXPOSABLE_REPRESENTATIVE 428
  recovery: 산출 150 · earliest 150 · stable 92 · 사유 all_primary_causes_quiet 92 · cause_relief 233 · other_primary_cause_ongoing 8 · right_censored_quiet_span 50
  portfolio 원천: unique cause 합 221(후보 점수 합산 없음 — 진단 표 원천)
  fallback 분리 잔존 진단(같은 대상·family ≥3 — cause 상이·비인접의 fail-closed 분리, under-merge 후보군): 60
  proxy audit(risk_id static): ownership_not_applicable 14 · proxy_match 34 · proxy_mismatch 1
  proxy audit(behavioral): 후보 rank 불일치 0 · proxy였다면 대표가 달라졌을 episode 0

## C-T 교운 overlay(episode 압축 이후 기준)
  ### medium(확정안) × MAX_BONUS=0.20 (교운일 w=1.0)
    [candidate] 평균 상승률 9.8% · top10 신규 진입 risk_id: REL_PARTNER_READJUST(2) · CAR_REASSIGNMENT_RISK(1) · FIN_SETTLEMENT_DISPUTE(1) · MOV_RELOCATION_PRESSURE(1)
    [candidate] 민감도별 평균 상승률: high 20.0% · low 5.0% · medium 12.0%
    [episode] top10 overlap 10/10 · 신규 없음
    [episode] 대표 변경 7 · 도메인 대표 변경 0 · ownership 유지 29 · ownership override 0 · budget 선택 변경 차트 1
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 1
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### medium(비교 0.30) × MAX_BONUS=0.30 (교운일 w=1.0)
    [candidate] 평균 상승률 14.6% · top10 신규 진입 risk_id: REL_PARTNER_READJUST(3) · CAR_REASSIGNMENT_RISK(2) · MOV_RELOCATION_PRESSURE(2) · FIN_SETTLEMENT_DISPUTE(1)
    [candidate] 민감도별 평균 상승률: high 30.0% · low 7.5% · medium 18.0%
    [episode] top10 overlap 10/10 · 신규 없음
    [episode] 대표 변경 7 · 도메인 대표 변경 0 · ownership 유지 29 · ownership override 0 · budget 선택 변경 차트 3
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 1
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### high(비교안) × MAX_BONUS=0.20 (교운일 w=1.0)
    [candidate] 평균 상승률 10.0% · top10 신규 진입 risk_id: REL_PARTNER_READJUST(2) · CAR_REASSIGNMENT_RISK(1) · FIN_SETTLEMENT_DISPUTE(1) · MOV_RELOCATION_PRESSURE(1)
    [candidate] 민감도별 평균 상승률: high 20.0% · low 5.0% · medium 12.0%
    [episode] top10 overlap 9/10 · 신규 MOV_CONTRACT_SETBACK_RISK
    [episode] 대표 변경 7 · 도메인 대표 변경 0 · ownership 유지 29 · ownership override 0 · budget 선택 변경 차트 2
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 1
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### high(비교안) × MAX_BONUS=0.30 (교운일 w=1.0)
    [candidate] 평균 상승률 15.0% · top10 신규 진입 risk_id: REL_PARTNER_READJUST(3) · CAR_REASSIGNMENT_RISK(2) · MOV_RELOCATION_PRESSURE(2) · FIN_SETTLEMENT_DISPUTE(1)
    [candidate] 민감도별 평균 상승률: high 30.0% · low 7.5% · medium 18.0%
    [episode] top10 overlap 9/10 · 신규 MOV_CONTRACT_SETBACK_RISK
    [episode] 대표 변경 7 · 도메인 대표 변경 0 · ownership 유지 29 · ownership override 0 · budget 선택 변경 차트 5
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 1
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### 참고 — medium(확정안)×0.20, ±1년(w=0.368): episode top10 overlap 10/10

## profile D_multi_selection — episode 형성·선별
  episode 718 · key 분포 explicit 30 · fallback 688
  reality identity: 없음
  구성원 크기: p50 1.000 · p90 2.000 · max 17.000 · n=718 · 다도메인 episode 0
  대표 보유 245/718 · ownership 대표 30 · 도메인 career 43 · finance 105 · health_safety 14 · relationship 37 · relocation 18 · selection 28
  context confidence(대표 보유): p50 0.300 · p90 0.900 · max 0.900 · n=245
  budget(hard_max 3): 선택 p50 3.000 · p90 3.000 · max 3.000 · n=10 · 누락 BUDGET_HARD_MAX 10 · LOWER_PRIORITY 205 · NO_EXPOSABLE_REPRESENTATIVE 473
  recovery: 산출 169 · earliest 169 · stable 115 · 사유 all_primary_causes_quiet 115 · cause_relief 270 · other_primary_cause_ongoing 8 · right_censored_quiet_span 46
  portfolio 원천: unique cause 합 226(후보 점수 합산 없음 — 진단 표 원천)
  fallback 분리 잔존 진단(같은 대상·family ≥3 — cause 상이·비인접의 fail-closed 분리, under-merge 후보군): 62
  proxy audit(risk_id static): ownership_not_applicable 14 · proxy_match 34 · proxy_mismatch 1
  proxy audit(behavioral): 후보 rank 불일치 0 · proxy였다면 대표가 달라졌을 episode 0

## D-T 교운 overlay(episode 압축 이후 기준)
  ### medium(확정안) × MAX_BONUS=0.20 (교운일 w=1.0)
    [candidate] 평균 상승률 11.0% · top10 신규 진입 risk_id: MOV_RELOCATION_PRESSURE(2) · CAR_REASSIGNMENT_RISK(1) · SEL_UNWANTED_PLACEMENT(1)
    [candidate] 민감도별 평균 상승률: high 20.0% · low 5.0% · medium 12.0%
    [episode] top10 overlap 9/10 · 신규 CAR_EXIT_PRESSURE
    [episode] 대표 변경 12 · 도메인 대표 변경 5 · ownership 유지 30 · ownership override 0 · budget 선택 변경 차트 4
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 18
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### medium(비교 0.30) × MAX_BONUS=0.30 (교운일 w=1.0)
    [candidate] 평균 상승률 16.5% · top10 신규 진입 risk_id: MOV_RELOCATION_PRESSURE(4) · CAR_REASSIGNMENT_RISK(1) · SEL_UNWANTED_PLACEMENT(1)
    [candidate] 민감도별 평균 상승률: high 30.0% · low 7.5% · medium 18.0%
    [episode] top10 overlap 9/10 · 신규 CAR_EXIT_PRESSURE
    [episode] 대표 변경 12 · 도메인 대표 변경 5 · ownership 유지 30 · ownership override 0 · budget 선택 변경 차트 5
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 21
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### high(비교안) × MAX_BONUS=0.20 (교운일 w=1.0)
    [candidate] 평균 상승률 11.0% · top10 신규 진입 risk_id: MOV_RELOCATION_PRESSURE(2) · CAR_REASSIGNMENT_RISK(1) · SEL_UNWANTED_PLACEMENT(1)
    [candidate] 민감도별 평균 상승률: high 20.0% · low 5.0% · medium 12.0%
    [episode] top10 overlap 9/10 · 신규 CAR_EXIT_PRESSURE
    [episode] 대표 변경 12 · 도메인 대표 변경 5 · ownership 유지 30 · ownership override 0 · budget 선택 변경 차트 4
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 18
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### high(비교안) × MAX_BONUS=0.30 (교운일 w=1.0)
    [candidate] 평균 상승률 16.5% · top10 신규 진입 risk_id: MOV_RELOCATION_PRESSURE(4) · CAR_REASSIGNMENT_RISK(1) · SEL_UNWANTED_PLACEMENT(1)
    [candidate] 민감도별 평균 상승률: high 30.0% · low 7.5% · medium 18.0%
    [episode] top10 overlap 9/10 · 신규 CAR_EXIT_PRESSURE
    [episode] 대표 변경 12 · 도메인 대표 변경 5 · ownership 유지 30 · ownership override 0 · budget 선택 변경 차트 5
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 21
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### 참고 — medium(확정안)×0.20, ±1년(w=0.368): episode top10 overlap 10/10

## profile E_reality_linked — episode 형성·선별
  episode 701 · key 분포 fallback 688 · reality 13
  reality identity: partial 3 · resolved 10
  구성원 크기: p50 1.000 · p90 2.000 · max 22.000 · n=701 · 다도메인 episode 6
  대표 보유 210/701 · ownership 대표 13 · 도메인 career 41 · contract_legal 5 · finance 105 · health_safety 17 · relationship 37 · relocation 5
  context confidence(대표 보유): p50 0.300 · p90 0.300 · max 1.000 · n=210
  budget(hard_max 3): 선택 p50 3.000 · p90 3.000 · max 3.000 · n=10 · 누락 BUDGET_HARD_MAX 10 · LOWER_PRIORITY 170 · NO_EXPOSABLE_REPRESENTATIVE 491
  recovery: 산출 135 · earliest 135 · stable 87 · 사유 all_primary_causes_quiet 87 · cause_relief 215 · other_primary_cause_ongoing 8 · right_censored_quiet_span 40
  portfolio 원천: unique cause 합 226(후보 점수 합산 없음 — 진단 표 원천)
  fallback 분리 잔존 진단(같은 대상·family ≥3 — cause 상이·비인접의 fail-closed 분리, under-merge 후보군): 67
  proxy audit(risk_id static): ownership_not_applicable 14 · proxy_match 34 · proxy_mismatch 1
  proxy audit(behavioral): 후보 rank 불일치 0 · proxy였다면 대표가 달라졌을 episode 0

## E-T 교운 overlay(episode 압축 이후 기준)
  ### medium(확정안) × MAX_BONUS=0.20 (교운일 w=1.0)
    [candidate] 평균 상승률 9.5% · top10 신규 진입 risk_id: LEG_CONTRACT_TERMINATION_RISK(1) · CAR_EXIT_PRESSURE(1) · CAR_REASSIGNMENT_RISK(1)
    [candidate] 민감도별 평균 상승률: high 20.0% · low 5.0% · medium 12.0%
    [episode] top10 overlap 10/10 · 신규 없음
    [episode] 대표 변경 7 · 도메인 대표 변경 0 · ownership 유지 13 · ownership override 0 · budget 선택 변경 차트 1
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 2
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### medium(비교 0.30) × MAX_BONUS=0.30 (교운일 w=1.0)
    [candidate] 평균 상승률 14.2% · top10 신규 진입 risk_id: CAR_REASSIGNMENT_RISK(3) · LEG_CONTRACT_TERMINATION_RISK(2) · MOV_RELOCATION_PRESSURE(1) · CAR_EXIT_PRESSURE(1)
    [candidate] 민감도별 평균 상승률: high 30.0% · low 7.5% · medium 18.0%
    [episode] top10 overlap 10/10 · 신규 없음
    [episode] 대표 변경 7 · 도메인 대표 변경 0 · ownership 유지 13 · ownership override 0 · budget 선택 변경 차트 4
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 1
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### high(비교안) × MAX_BONUS=0.20 (교운일 w=1.0)
    [candidate] 평균 상승률 9.7% · top10 신규 진입 risk_id: MOV_CONTRACT_SETBACK_RISK(1) · CAR_EXIT_PRESSURE(1) · CAR_REASSIGNMENT_RISK(1)
    [candidate] 민감도별 평균 상승률: high 20.0% · low 5.0% · medium 12.0%
    [episode] top10 overlap 10/10 · 신규 없음
    [episode] 대표 변경 7 · 도메인 대표 변경 0 · ownership 유지 13 · ownership override 0 · budget 선택 변경 차트 1
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 2
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### high(비교안) × MAX_BONUS=0.30 (교운일 w=1.0)
    [candidate] 평균 상승률 14.6% · top10 신규 진입 risk_id: CAR_REASSIGNMENT_RISK(3) · MOV_CONTRACT_SETBACK_RISK(2) · MOV_RELOCATION_PRESSURE(1) · LEG_CONTRACT_TERMINATION_RISK(1) · CAR_EXIT_PRESSURE(1)
    [candidate] 민감도별 평균 상승률: high 30.0% · low 7.5% · medium 18.0%
    [episode] top10 overlap 9/10 · 신규 MOV_CONTRACT_SETBACK_RISK
    [episode] 대표 변경 7 · 도메인 대표 변경 0 · ownership 유지 13 · ownership override 0 · budget 선택 변경 차트 4
    [episode] cap이면 동점이었을 선택쌍(raw로 분별) 0 · 자연 raw 동점(동일 구조 병존 — novelty·key 결정) 1
    판정: episode top10 overlap ≥ 80% PASS · 신규 진입 단일 risk_id 미집중(≤2) PASS · cap 동점이 선택을 결정하지 않음(raw 정렬) PASS · ownership override = 0 PASS · low/none 항목 top10 신규 진입 0 PASS
  ### 참고 — medium(확정안)×0.20, ±1년(w=0.368): episode top10 overlap 10/10
