# 위험 엔진 3프로필 노출 단계 baseline (감수 24차 — R1 진입 게이트)

> 최종 고정: 2026-07-16 · SEL-e(다중 선발 episode — 감수 25차) 반영 ·
> env risk-engine-r0.5.12 · 해시 v8 · reviewed 49(전 도메인 unreviewed 0) ·
> 코퍼스 seoul-busan-10 (year+month, 220기간) · A/B/C 지표는 C8-f 고정본과 완전
> 동일(의도 변화 없음 확인), D_multi_selection 신설
>
> **용도**: TYP-0(테스트 타입 부채 정리) 전후·R1 착수 전 지표 **완전 일치** 비교 기준
> (허용 오차 없음 — TYP-0은 런타임 동작 불변 차수).
> 기계 판독 고정본: `doc/v2_2/RISK_PROFILE_BASELINE.json`
> 검증: `python scripts/risk_profile_baseline.py --check` (exact match, 기록 시점
> 메타만 제외 — env·사전 해시·프로필 컨텍스트 해시 불일치도 실패)
> 사람 판독 리포트: `python scripts/risk_shadow_density.py --profile-scenarios`

## 프로필 정의 (데굴님 §8 설계)

| 프로필 | 구성 | 측정 대상 |
|---|---|---|
| A `all_unknown` | 전 컨텍스트 미확인·질문 대상 없음 | projected 하한(required_for_warning advisory만) |
| B `typical_confirmed` | 파트너 확인(partner_1) + 일반 건강 질문(상태 미확인) + 진행 중 계약 1건(contract_1). 이사·소송·치료·대인 금전거래 없음 | 일반 사용자 노출 밀도 |
| C `high_exposure` | 채용 결과 대기 + 이사 계약(housing_move_1) + 진행 계약(active_contract_1) + 파트너(partner_1) + 치료 중(treatment_1) — 전부 서로 다른 익명 episode, boolean 무차별 true 금지 | R2 risk budget 상한 |
| D `multi_selection` | employment_hiring_1(result_wait) + examination_1(assessment) + examination_2(result_wait) + lottery_draw_1(draw·lottery_draw) — 서로 다른 target type 병존과 **동일 target type 복수 episode 병존**을 동시 검증(SEL-e 회귀). C의 의미 불변 | 다중 선발 episode 정확성 |

제약: 직업 역할(전역 노출 축)은 R5 프로필 배선 전이라 3프로필 모두 UNKNOWN —
career 구체 항목(required_for_exposure)은 하한으로 측정된다.

## 측정 결과 (2026-07-16 SEL-e 반영 최종 고정 — A/B/C는 C8-f와 동일)

| 지표 | A all_unknown | B typical | C high | D multi_sel |
|---|---|---|---|---|
| 활성/기간 | 4.15 | 4.16 | 3.87 | 4.24 |
| context-exposable/기간 | **1.28** | **1.56** | **1.64** | **1.58** |
| kind(활성) incident/pressure/vuln | 192/451/271 | 198/446/271 | 171/409/271 | 213/449/271 |
| 활성 family/기간 p50·p90·max | 4·8·13 | 4·8·13 | 4·7·11 | 4·7·13 |
| 노출 가능 family/기간 p50·p90·max | 2·3·6 | 2·4·6 | 2·4·6 | 2·4·8 |
| 단일 원인 family 확산 max | 9 | 9 | 7 | 9 |
| 교차 도메인 공유 원인(기간·원인) | 398 | 399 | 372 | 392 |
| UNKNOWN 보존(활성·비노출) | 633 | 571 | 490 | 586 |
| blocked_unique_candidates(축 MISMATCHED) | 0(0) | 0(0) | 468(468) | 202(202) |

episode별 활성 후보:
- B: legal:contract_1=32 · relationship:partner_1=36
- C: health:treatment_1=6 · legal:active_contract_1=32 · mobility:housing_move_1=38 ·
  relationship:partner_1=36

BLOCKED 집계 명칭 확정(감수 26차 — 데굴님 §2: 927류는 '차단 사유'가 아니라
BLOCKED 후보에 기록된 전체 eligibility·evidence 사유 pair, 스크립트 불변식 assert):
- **blocked_unique_candidates**(후보 identity 중복 제거) /
  **blocking_axis_reason_pairs**(축 mismatch 계열 — 실제 차단 사유) /
  **evidence_deficiency_reason_pairs**(증거 미충족 계열 — INSUFFICIENT 유래 동반
  기록, 차단 사유 아님) / **blocked_candidate_all_reason_pairs**(전 사유 pair) /
  **blocked_raw_rule_hits**(중복 기록 포함).
- C: unique **468** · blocking_axis **520** · deficiency **407**(unmet 406+
  unlinked 1) · all 927 · raw 927.
- 축 조합(unique 후보): target_type_only 214 + stage_only 202 +
  target_type_and_stage 52 = 468 ✓ / 214 + 202 + 2×52 = 520 ✓.
- D: unique **202** · blocking_axis 251(stage 202 + mode 49) · deficiency 180 ·
  all 431 · raw 431.
- 도메인: C·D 모두 selection 전량 — 타 도메인 오차단 0.

도메인 기여도(unique 기간·family):
- A: LEG 193 / REL 159 / FIN 152 / HLT 135 / MOV 102 / CAR 52 / SEL 45
- B: LEG 193 / REL 154 / FIN 152 / HLT 135 / MOV 102 / CAR 52 / SEL 45
- C: LEG 193 / REL 154 / FIN 152 / HLT 135 / MOV 99 / CAR 52 / **SEL 0**

## D_multi_selection 필수 결과 (감수 25차 — SEL-e 해소 확인)

- **episode별 활성 후보**: employment_hiring_1=4 · examination_1=25 ·
  examination_2=32 · lottery_draw_1=23 — 서로 다른 target type 병존과 동일
  target type 복수 episode(시험 2건) 병존이 모두 보존된다.
- **채용 episode의 차단이 다른 episode로 전파되지 않음**: D의 BLOCKED 202는
  전량 stage 사유(waitlist·eligibility_check 등 실재하지 않는 단계의 항목) —
  C에서 468이던 소유권 차단이 D에선 시험·추첨 episode가 살아 있어 202로 줄고
  SEL 기여 0→33으로 복원된다.
- **exposable 밀도 1.58/기간·family p90 4**: episode 4건 병존에도 노출 후보가
  무제한 비례 증가하지 않는다(R2 선별 ≤3 입력 규모 유지, family max 6→8).
- 감수 24차에 기록했던 단수 SelectionContext 한계는 SEL-e(env r0.5.12)로 해소 —
  R3/R5의 '질문 대상 선발 1건만 주입' 임시 제약도 함께 해제 가능(배선 시점에
  복수 episode 공급으로 전환).

## 해석

- 노출 밀도 계층이 설계대로 단조 증가: 하한 1.28 → 일반 1.56 → 상한 1.64/기간.
  노출 가능 family p90은 3→4 — R2 최종 선별 목표(selected family ≤3)의 입력
  규모로 적정(raw structural family는 3으로 자르지 않는다 — 데굴님 §9).
- C에서 활성/기간이 오히려 감소(4.15→3.87): 컨텍스트 확인이 후보를 늘리는 게
  아니라 mismatch 차단·수렴을 늘린다(설계 의도).
- C8-f 재분류 효과: incident 192~171/pressure 451~409(구 PENALTY 이동),
  exposable·family·fanout·교차 원인 지표는 전부 불변 — kind 정합화가 노출 표면을
  바꾸지 않음을 확인.
- vulnerability 271은 세 프로필 동일(구조 잠재 신호 — 노출·집계 비기여는 C8
  fixture·RCW 지표가 보장).
- 교차 도메인 공유 원인 372~399: R1 occurrence 1회 계산 규격의 검증 표본(진입
  게이트 6번).
