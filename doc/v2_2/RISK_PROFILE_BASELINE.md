# 위험 엔진 3프로필 노출 단계 baseline (감수 24차 — R1 진입 게이트)

> 생성: 2026-07-16 · 기준 커밋 03eeac5(C8 마감) · env risk-engine-r0.5.11 · 해시 v8 ·
> reviewed 49(전 도메인 unreviewed 0) · 코퍼스 seoul-busan-10 (year+month, 220기간)
>
> **용도**: TYP-0(테스트 타입 부채 정리) 전후·R1 착수 전 지표 불변 비교의 기준.
> 재생성: `python scripts/risk_shadow_density.py --profile-scenarios`
> — 출력은 결정적이므로 아래 수치와의 diff가 곧 회귀 신호다.

## 프로필 정의 (데굴님 §8 설계)

| 프로필 | 구성 | 측정 대상 |
|---|---|---|
| A `all_unknown` | 전 컨텍스트 미확인·질문 대상 없음 | projected 하한(required_for_warning advisory만) |
| B `typical_confirmed` | 파트너 확인(partner_1) + 일반 건강 질문(상태 미확인) + 진행 중 계약 1건(contract_1). 이사·소송·치료·대인 금전거래 없음 | 일반 사용자 노출 밀도 |
| C `high_exposure` | 채용 결과 대기 + 이사 계약(housing_move_1) + 진행 계약(active_contract_1) + 파트너(partner_1) + 치료 중(treatment_1) — 전부 서로 다른 익명 episode, boolean 무차별 true 금지 | R2 risk budget 상한 |

제약: 직업 역할(전역 노출 축)은 R5 프로필 배선 전이라 3프로필 모두 UNKNOWN —
career 구체 항목(required_for_exposure)은 하한으로 측정된다.

## 측정 결과 (2026-07-16 고정)

| 지표 | A all_unknown | B typical | C high |
|---|---|---|---|
| 활성/기간 | 4.15 | 4.16 | 3.87 |
| context-exposable/기간 | **1.28** | **1.56** | **1.64** |
| kind(활성) incident/pressure/vuln | 203/440/271 | 209/435/271 | 182/398/271 |
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

도메인 기여도(unique 기간·family):
- A: LEG 193 / REL 159 / FIN 152 / HLT 135 / MOV 102 / CAR 52 / SEL 45
- B: LEG 193 / REL 154 / FIN 152 / HLT 135 / MOV 102 / CAR 52 / SEL 45
- C: LEG 193 / REL 154 / FIN 152 / HLT 135 / MOV 99 / CAR 52 / **SEL 0**

## 해석

- 노출 밀도 계층이 설계대로 단조 증가: 하한 1.28 → 일반 1.56 → 상한 1.64/기간.
  노출 가능 family p90은 3→4로 상승 — R2 최종 선별 목표(선택 family ≤3)의 입력
  규모로 적정(raw structural family는 3으로 자르지 않는다 — 데굴님 §9).
- C의 BLOCKED 468 전량이 축 MISMATCHED: 채용 결과 대기(employment_hiring)
  컨텍스트가 SEL 항목을 소유권 차단(SEL 기여 45→0, CAR primary) — 인위적 후보
  폭발이 아니라 소유권 라우팅이 작동함을 보여준다.
- C에서 활성/기간이 오히려 감소(4.15→3.87): 컨텍스트 확인이 후보를 늘리는 게
  아니라 mismatch 차단·수렴을 늘린다(설계 의도).
- vulnerability 271은 세 프로필 동일(구조 잠재 신호 — 노출·집계 비기여는 C8
  fixture·RCW 지표가 보장).
- 교차 도메인 공유 원인 372~399: R1 occurrence 1회 계산 규격의 대상 규모(진입
  게이트 6번 — trigger_cause_atoms 연결 검증 표본).
