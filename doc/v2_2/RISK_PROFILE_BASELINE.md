# 위험 엔진 3프로필 노출 단계 baseline (감수 24차 — R1 진입 게이트)

> 최종 고정: 2026-07-16 · C8-f(PENALTY→COMPLIANCE_OBLIGATION_PRESSURE 재분류) 반영 ·
> env risk-engine-r0.5.11 · 해시 v8 · reviewed 49(전 도메인 unreviewed 0) ·
> 코퍼스 seoul-busan-10 (year+month, 220기간)
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

제약: 직업 역할(전역 노출 축)은 R5 프로필 배선 전이라 3프로필 모두 UNKNOWN —
career 구체 항목(required_for_exposure)은 하한으로 측정된다.

## 측정 결과 (2026-07-16 C8-f 반영 최종 고정)

| 지표 | A all_unknown | B typical | C high |
|---|---|---|---|
| 활성/기간 | 4.15 | 4.16 | 3.87 |
| context-exposable/기간 | **1.28** | **1.56** | **1.64** |
| kind(활성) incident/pressure/vuln | 192/451/271 | 198/446/271 | 171/409/271 |
| 활성 family/기간 p50·p90·max | 4·8·13 | 4·8·13 | 4·7·11 |
| 노출 가능 family/기간 p50·p90·max | 2·3·6 | 2·4·6 | 2·4·6 |
| 단일 원인 family 확산 max | 9 | 9 | 7 |
| 교차 도메인 공유 원인(기간·원인) | 398 | 399 | 372 |
| UNKNOWN 보존(활성·비노출) | 633 | 571 | 490 |
| BLOCKED(축 MISMATCHED) | 0(0) | 0(0) | 468(468) |

episode별 활성 후보:
- B: legal:contract_1=32 · relationship:partner_1=36
- C: health:treatment_1=6 · legal:active_contract_1=32 · mobility:housing_move_1=38 ·
  relationship:partner_1=36

BLOCKED 분해(C — 데굴님 §3 요구, 감수 25차 표기 보완):
- **blocked_unique_candidates = 468** vs **blocked_reason_occurrences = 927**
  (한 후보가 복수 사유를 동시 보유 — 두 수치는 다른 지표다).
- 도메인: **selection=468 (전량)** — 타 도메인 차단 0.
- 사유(발생 기준): selection_target_type_mismatch 266 · selection_stage_mismatch
  254 · evidence_groups_unmet 406 · targets_unlinked 1.
- selection 축 조합(unique 후보 기준): target_type_only 214 · stage_only 202 ·
  target_type_and_stage 52 (합 = 468).

도메인 기여도(unique 기간·family):
- A: LEG 193 / REL 159 / FIN 152 / HLT 135 / MOV 102 / CAR 52 / SEL 45
- B: LEG 193 / REL 154 / FIN 152 / HLT 135 / MOV 102 / CAR 52 / SEL 45
- C: LEG 193 / REL 154 / FIN 152 / HLT 135 / MOV 99 / CAR 52 / **SEL 0**

## SEL 45→0 차단 범위 확인 (감수 24차 추가 확인 지시)

- blocked 분해로 확정: C의 차단 468건 전량이 selection 도메인·selection 축 사유 —
  employment_hiring 컨텍스트에 의한 소유권 차단이며 타 도메인 오차단 없음.
- **프로필 C의 선발 episode는 채용 1건뿐이므로 이 baseline은 정상**(채용 관련 선발
  후보 차단 = CAR primary 라우팅).
- **한계(감수 질문 — R1 전 결정 필요)**: 현재 SelectionContext는 단수이며 episode
  개념이 없다(C3-d 설계). 따라서 "employment_hiring_1 + general_selection_1 동시
  존재" 시나리오는 **엔진이 표현 자체를 못 하며**, 그런 사용자가 실재하면 채용
  컨텍스트가 일반 선발 후보까지 전역 차단한다. 데굴님 불변식(각 episode가 자기
  선발 후보를 유지·병존)을 충족하려면 selection 축도 이동·건강·법률처럼 복수
  컨텍스트+episode_id로 확장해야 한다(SEL-e 차수 — 엔진 의미 변경·env 갱신 수반).
  확장 전까지 R3/R5 배선에서 selection 컨텍스트는 질문 대상 선발 1건만 주입한다.

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
