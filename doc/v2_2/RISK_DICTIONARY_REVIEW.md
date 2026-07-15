# RISK_DICTIONARY_REVIEW.md — 위험 사전 감수 (R0.5)

> 2026-07-15 감수 지시에 따른 작업 문서. 표 A(공통 신호 역할 매트릭스)는 RISK_ENGINE.md
> §3-1에 규격으로 고정했고, 본 문서는 **대표 7항목 기준 샘플의 개정안**과 잔여 37항목
> 일괄 규칙, 밀도 기준선을 담는다. 데굴님 확정 후 44항목 전체에 적용한다.

## 0. 밀도 기준선 (수정 전 — 2026-07-15 실측)

기준 차트(1980-11-22 서울 남) 세운 10년 + 월운 12개월(총 22기간), 초안 사전 그대로:

| 지표 | 값 | 판정 |
|---|---|---|
| 기간당 평균 후보 | 6.82 | 과다 |
| 활성 후보 존재 기간 | 81.8% | 과다(경고 임계 90% 미만이나 높음) |
| incident 존재 기간 | 40.9% | 과다 |
| incident : pressure | 54 : 67 | 양호(역전 없음) |
| 최다 원인 확산 | 충 1건 → **11개 risk_id** | **심각** |
| 발동률 >50% risk_id | LEG_REVIEW_CAPACITY_WEAK 54.5%, FIN_BUFFER_WEAK 50.0% | 과다 |
| blocked 후보 | 0 | blocker 미작동(전부 극성 단일값이라 trigger와 동시 성립 불가) |

원인 진단: ①충·형 trigger가 **대상 무관**(재성 충=배우자궁 충=사회궁 충 동일 취급)
②기신 극성이 여러 항목의 독립 trigger로 반복 ③vulnerability가 GI_STRONG 단독 발동.
→ 모두 표 A 원칙 위반. 개정 방향: 기신은 amplifier로 강등, 관계 trigger에 대상
(`relationTargetTenGod(Group)`) 또는 궁위 필수, incident는 requiredGroups
[event_shape, target_activation] 필수.

## 1. 대표 7항목 개정안 (도메인별 1건 — 기준 샘플)

공통 변경(7항목 전부):
- `minimumEvidence.requiredGroups = ["event_shape", "target_activation"]` (incident)
- 기신·공망·운성 단독 trigger → **amplifier로 이동** (독립 트리거 금지)
- mitigator: 용·희신 작동 + 통관 성격(인성 등 항목별) / blocker: YONG_STRONG 유지 +
  실노출 기반 차단(exposure DENIED/NOT_APPLICABLE)은 R5에서 배선
- 건강·법률·재정: `allowedClaimScope` + `claimCeiling` 저작

### 1-1. FIN_UNEXPECTED_EXPENSE (finance · incident · family: cashflow)

| 구분 | 개정안 |
|---|---|
| 사건 정의 | 예상하지 못한 지출·계약금/환불 문제·비용성 사건 |
| event_shape | ①겁재-재성 동반 유입(JIECAI + tenGodGroup wealth — 탈재 구조) ②재물 유출 방향 조합(PIANCAI + JIECAI 동반) |
| target_activation | 재성이 충·형·파의 **직접 대상**(relation CHUNG/HYEONG/PA + relationTargetTenGodGroup wealth) |
| amplifier | 기신·GI_STRONG(방향), 공망(회수·정산 지연), 형 동반 |
| mitigator | 용·희신 작동, 합(충 완화), 정인(문서·보존) |
| blocker | YONG_STRONG / (R5) 거래·계약 노출 없음 |
| manifestation | 예상 밖 지출 / 계약금·환불 문제 / 가족·경조사 비용 |
| claimCeiling | warning · 허용: 가능한 발현 형태, 대비 행동 |
| prohibited | 손실 금액·시점 확정 단정 |
| min evidence | trigger 2 · 독립 출처 2 · 필수 그룹 2종 |
| 대표 오경고 | 재성 무관 충 + 기신만으로 발동(현행) → 대상 조건으로 차단 |

기존 `겁재+기신/충+기신/편재+기신`은 **FIN_CASHFLOW_PRESSURE(pressure)로만** 사용.

### 1-2. CAR_ORG_CONFLICT (career · incident · family: workplace_conflict)

| 구분 | 개정안 |
|---|---|
| event_shape | 상관-관성 동시(SHANGGUAN + tenGodGroup authority — 상관견관 구조) |
| target_activation | ①관성 피격(relation CHUNG/HYEONG + relationTargetTenGodGroup authority) ②월주(사회궁) 충(relation CHUNG + relationPalace month_pillar) |
| amplifier | 기신 방향, 형 동반(갈등 장기화) |
| mitigator | 인성(상관 제어 통관), 용·희신, 합 |
| 대표 오경고 | 상관 단독 기신(구설 압박 — pressure 소관)으로 조직 충돌 단정 |

### 1-3. LEG_PENALTY_LIABILITY (contract_legal · incident · family: liability)

| 구분 | 개정안 |
|---|---|
| event_shape | 형 발동 + 편관 유입 동반(relation HYEONG + tenGod QISHA — 강제 조정·책임 구조) |
| target_activation | 관성/인성(책임·문서) 피격(relationTargetTenGodGroup authority 또는 resource) |
| amplifier | 기신·GI_STRONG, 충 동반 |
| mitigator | 정인(절차·문서 보호), 용·희신 |
| claimCeiling | conditional_warning · 허용: 검토 필요성, 책임 범위 확인 권고 |
| prohibited | 배상 금액·법적 결과·승패 단정 |
| 대표 오경고 | 대상 무관 형(예: 자형)만으로 위약·배상 발동 |

### 1-4. HLT_CHRONIC_FLAREUP (health_safety · incident · family: health_condition)

| 구분 | 개정안 |
|---|---|
| event_shape | 형 + 병/사 운성 동반(relation HYEONG + twelveStageIn [BYEONG, SA] — 컨디션 저하기 신체 조정 신호) |
| target_activation | 일지·시지(신체·일상 궁) 충(relation CHUNG + relationPalace day/hour_pillar) |
| amplifier | 기신·GI_STRONG, 공망 |
| mitigator | 인성(회복·휴식), 용·희신 |
| claimCeiling | **conditional_warning 고정**(노출 UNKNOWN 시 항상 조건부) · 허용: 관리 필요성, 검진 권고, 부담 부위·위험 행동 |
| prohibited | 질병명·발병 시점·수술·사망 단정, 의료 진단 대체 |
| 대표 오경고 | 기신 강 + 쇠약 운성만으로 재발 경고(압박 소관) |

### 1-5. REL_PARTNER_READJUST (relationship · incident · family: partner_relation)

| 구분 | 개정안 |
|---|---|
| event_shape | 관계 교란 십성 유입(JIECAI 또는 SHANGGUAN + 기신 방향 — 동반 조건) |
| target_activation | 배우자궁(일지) 충·형 직접 자극(relation CHUNG/HYEONG + relationPalace day_pillar) |
| amplifier | GI_STRONG, 공망(소통 공백) |
| mitigator | 합(관계 재결속), 인성(숙고), 용·희신 |
| prohibited | 이별·이혼 단정, 상대방 귀책 단정 |
| 잔여 갭(R1) | 배우자성(남=재성/여=관성) 피격 조건은 성별 의존 — 스키마에 성별 축이 없어 R1에서 marriage_flow.gender 연동 검토 |
| 대표 오경고 | 일지 무관 겁재 기신만으로 관계 재조정 단정 |

### 1-6. MOV_CONTRACT_FAIL (relocation · incident · family: housing_contract)

| 구분 | 개정안 |
|---|---|
| event_shape | 문서성(인성) 공망(voidActive + tenGodGroup resource) 또는 문서 파열(relation PA + relationTargetTenGodGroup resource) |
| target_activation | 일지(주거 근접 궁) 충 또는 인성 피격(relation CHUNG + relationPalace day_pillar / relationTargetTenGodGroup resource) |
| amplifier | 기신 방향, 해(일정 어긋남) |
| mitigator | 정인 회복, 합, 용·희신 |
| riskFamily | housing_contract — relatedDomains: [finance, contract_legal] (임대차 하자 1사건이 MOV/FIN/LEG 3건으로 부풀지 않도록 R2 통합) |
| 대표 오경고 | 무관 공망 + 무관 충 2출처로 발동(현행) |

### 1-7. SEL_UNWANTED_PLACEMENT (selection · incident · family: placement)

| 구분 | 개정안 |
|---|---|
| event_shape | 관성(외부 결정권) 유입 + 충 동반(relation CHUNG + tenGodGroup authority) |
| target_activation | 관성 피격(relationTargetTenGodGroup authority) 또는 월주(사회궁) 충 |
| amplifier | 기신 방향, 형(조건 시비) |
| mitigator | 용·희신, 인성(절차 보호) |
| prohibited | 배치 결과 확정 단정 (선발·배치 코어 무작위성 캡 준수) |
| 대표 오경고 | 관성 무관 충 + 기신으로 배치 불이익 단정 |

## 2. 잔여 37항목 일괄 규칙 (7항목 확정 후 적용)

1. **기신 단독 trigger 전량 amplifier로 이동.** GI_STRONG 단독 trigger는 pressure에만
   허용(예: HLT_FATIGUE_ACCUMULATION), incident·vulnerability에서는 금지.
2. **관계(충·형·파·해) trigger에 대상 필수**: `relationTargetTenGod(Group)` 또는
   `relationPalace` 중 최소 1개. 대상 무관 관계 룰은 amplifier로만.
3. **vulnerability도 영역 활성 동반**: GI_STRONG 단독 발동(LEG_REVIEW_CAPACITY_WEAK
   54.5%, FIN_BUFFER_WEAK 50.0%) → 관련 영역 신호(문서=resource, 재물=wealth) 동반
   조건 추가로 발동률 목표 ≤25%.
4. **모든 incident에 requiredGroups [event_shape, target_activation]** + 그룹 라벨 저작.
5. **riskFamily 저작**: housing_contract(MOV/FIN/LEG), cashflow(FIN 3종),
   workplace_exit(CAR 2종) 등 교차 도메인 사건 통합 키.
6. **건강·법률 전 항목에 allowedClaimScope + claimCeiling** (건강 incident는
   conditional_warning 고정).
7. 수정 후 밀도 재실측 목표: 기간당 평균 후보 ≤3, incident 존재 기간 ≤20%, 단일 원인
   확산 ≤3 risk_id, 발동률 >40% 항목 0건.

## 3. 감수 진행 상태

| 단계 | 상태 |
|---|---|
| 표 A 매트릭스 | 규격 반영 완료(RISK_ENGINE.md §3-1) — **데굴님 확정 대기** |
| requiredGroups·대상 provenance·eligibility 지원 | 구현 완료 |
| 대표 7항목 개정안 | 본 문서 §1 — **데굴님 확정 대기** |
| 잔여 37항목 적용 | 7항목 확정 후 |
| 밀도 재실측 | 44항목 개정 후 |
| reviewed:true 전환 | 재실측 통과 + 데굴님 승인 후 |
