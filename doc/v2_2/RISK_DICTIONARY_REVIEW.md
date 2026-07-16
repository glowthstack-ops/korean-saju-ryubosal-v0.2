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

## 3. 대표 7항목 개정 실룰 반영 (2026-07-15 감수 2차 — 사전 JSON 적용 완료)

§1 개정안이 실제 사전에 반영됐다. 공통 적용 사항:

- 기신·공망 trigger → **amplifier로 강등**, YONG_STRONG blocker → **mitigator로 강등**
  (blocker는 trigger와 동시 성립 가능한 차단 조건만 — 노출 기반 차단은 엔진이
  exposure_status로 자동 처리).
- 모든 관계 trigger에 대상(`relationTargetTenGodGroup`) 또는 궁위 부여 + `group` 라벨.
- `evidenceContract` 저작: FIN/LEG/REL = targeted 단독 경로, CAR/MOV/SEL =
  (event_shape+target_activation) 또는 targeted, **HLT = event_shape+target_activation
  필수 + 독립 원인 2(가장 엄격, targeted 단독 경로 없음)**.
- riskFamily·specificityRank 저작: cashflow(FIN 3종)·workplace_conflict·liability·
  health_condition(HLT 5종)·partner_relation(REL 3종)·housing_contract(MOV, related:
  finance/contract_legal)·placement.
- 건강·법률·관계: allowedClaimScope + claimCeiling(conditional_warning) 저작.
- REL_PARTNER_READJUST: 배우자궁(일지) 충·형만 생성 경로 — **배우자성(성별 의존)
  근거는 R1 성별 축 연동 전까지 미저작**, "배우자 문제 단정" prohibited.

## 4. 밀도 실측 — 단계별 지표 (10차트 코퍼스, 세운+월운 22기간/차트)

`scripts/risk_shadow_density.py` (observed/eligible/active 분리, is_active 기준):

| 지표 | 실측 | 목표 | 판정 |
|---|---|---|---|
| 활성/기간 평균 | 6.63 | (family 기준 ≤3) | 미달 — 미개정 37항목 기인 |
| active incident/기간 | 3.12 | ≤1.5 | 미달 — 미개정 항목 기인 |
| 활성 family/기간 p50/p90 | 6 / 15 | ≤3 | 미달 — 미개정 항목은 family 미저작(항목=family로 집계) |
| 단일 원인 활성 family 확산 max | 12 | ≤2(예외 3) | 미달 — 전부 미개정 항목 |
| 개정 7항목 발동률 | FIN_UEX 27.3%(>40% 차트 1/7) 등 | ≤20~25% | 근접 — 37항목 적용 후 재평가 |
| 발동률>40% 경고 | LEG_REVIEW_CAPACITY_WEAK 45.5%, CAR_WORK_OVERLOAD 41.8% (전부 미개정) | incident 0건 | 미개정 vulnerability/pressure |

해석: **경고 신호는 전부 미개정 37항목에서 발생** — 개정 7항목은 대상 조건·증거
계약으로 발동률이 목표 범위에 근접했고, 특이도 억제(차트당 10~24건 흡수)와
INSUFFICIENT 분리(observed 대비 eligible 약 45%)가 실측에서 작동함을 확인. 잔여
37항목에 §2 일괄 규칙을 적용해야 목표에 도달한다.

## 5. 감수 진행 상태 (2026-07-15 3차 — 표 A·대표 7항목 확정)

| 단계 | 상태 |
|---|---|
| 표 A 매트릭스 + targeted_event_shape | **확정**(성립 조건 강화: 궁위 정의 또는 구조 십성 동반 — 대상 특정 일반 관계는 target_activation) |
| 불변식 4종(fallback 금지·원인별 완화·흡수 역할 보존·cause_atom 정규화) | 구현·테스트 고정 완료 |
| 대표 7항목 실룰 | **shadow 기준 룰로 확정 — reviewed:true 전환**(사전 구조·shadow 감수 완료 의미이며 사용자 노출 승인 아님. RISK_ENGINE_MODE는 계속 off/shadow) |
| 커밋 | A=c4628e1(인프라) · B=보완+7항목+fixture+계측(본 차수) |
| 잔여 37항목 적용 | **승인됨** — §2 일괄 규칙 + 변환 직후 reviewed:false, 엔진 로직 변경 필요 시 사전 커밋과 분리 |
| 밀도 재실측·목표 판정 | 37항목 적용 후(§4 + RISK_ENGINE.md §10-2 확정 기준) |
| 37항목 reviewed:true 전환 | 재실측 통과 + 도메인별 표본 감수 후 |

## 6. 잔여 항목 작업 manifest (감수 5차 확정 — 코드 기준 재집계)

미개정 = **FIN 6 + LEG 5 = 11항목**(이전 보고의 "10항목"은 오류 — FIN_BUFFER_WEAK 누락 집계).
커밋 분리: **C1 = FIN 6항목 → fixture → FIN 전용 밀도 → 감수 / C2 = LEG 5항목 →
fixture → LEG 전용 밀도 → 교차 도메인 중복 검사 → 감수.**

| risk_id | 현재 kind | 변경 후 kind | exposure 필요(R1) | claim 방향 |
|---|---|---|---|---|
| FIN_CASHFLOW_PRESSURE | pressure | pressure | 선택 | 구체 손실 단정 금지, 반복성·완충력 중심 |
| FIN_INVESTMENT_LOSS | incident | incident(조건부) | **필수**(투자 노출 CONFIRMED — UNKNOWN이면 "투자를 한다면 변동성 관리" 조건부) | 손실 단정 금지 |
| FIN_DEBT_GUARANTEE_BURDEN | incident | incident(조건부) | **필수**(대출·보증 노출 — 없으면 BLOCKED/N.A. 겁재·재성만으로 보증 추론 금지) | 책임 발생 단정 금지 |
| FIN_INCOME_DELAY | incident | incident | 준필수(급여·매출·정산 대상 존재) — "소득 감소"와 "지급 지연" 분리 | 소득 상실 단정 금지 |
| FIN_SETTLEMENT_DISPUTE | incident | incident | 준필수(계약·정산 관계) — LEG와 primary domain 결정(risk_family) | 법적 분쟁 단정 금지 |
| FIN_BUFFER_WEAK | vulnerability | vulnerability | 선택 | 내부 보조 — 독립 경고보다 impact_amplifier 흡수 우선 |
| LEG_CONTRACT_CANCEL | incident | incident | 준필수(진행 계약) | 파기 확정 금지 |
| LEG_DOCUMENT_ERROR | incident | incident | 선택 | — |
| LEG_ADMIN_DELAY | incident | incident 또는 pressure 강등 검토(무대상 지연) | 준필수(절차 진행) | — |
| LEG_DISPUTE_LITIGATION | incident | incident(조건부) | **필수**(분쟁·소송 노출) | 승패·처벌 단정 금지 |
| LEG_REVIEW_CAPACITY_WEAK | vulnerability | vulnerability | 선택 | 내부 보조(발동률 45.5% — 영역 활성 동반 조건으로 하향) |

공통: 기신·공망·운성 trigger → amplifier, 관계 trigger에 대상/궁위(파·해는
target_activation만), FIN 항목별 상이한 증거 계약(동일 계약 복제 금지),
riskFamily(cashflow/liability/settlement 등) 저작, 변환 직후 reviewed:false.
중간 밀도는 전체/개정 항목만/미개정 제외/동일 항목 delta 4종 분리 보고.

## 7. C3 본 차수 재분류 manifest (감수 12차 확정 — "incident 8개" 전제 폐기)

| 현재 항목 | 처리 | kind |
|---|---|---|
| CAR_EVALUATION_DISADVANTAGE | 평가상 불리 요소 위험(결과 단정 금지, ID 완화 검토: EVALUATION_SETBACK_RISK) | 조건부 incident(근거 부족 시 pressure 강등) |
| CAR_UNWANTED_TRANSFER | CAR_REASSIGNMENT_RISK로 — "원치 않음"은 preference CONFIRMED에서만, 사업자·프리랜서 NOT_APPLICABLE | 조건부 incident |
| CAR_EXIT_PRESSURE | 이탈 압박(해고·퇴사 확정 사건 자동 생성 금지 — 종료 사건은 별도 강한 계약+노출) | **pressure** |
| CAR_HIRING_DELAY_REJECTION | **분리**: HIRING_PROCESS_DELAY(pressure) + HIRING_OUTCOME_SETBACK(incident, 지원 노출 필수, 불합격 단정 금지) | pressure + incident |
| SEL_DOCUMENT_OMISSION | SEL_DOCUMENT_DEFECT_RISK — 서류 결함·확인 위험(application_document 단계) | 조건부 incident |
| SEL_ELIGIBILITY_SHORTFALL | SEL_ELIGIBILITY_REVIEW_RISK — 자격 미달 단정 금지(외부 정보), 심사 부담 | **pressure**(자격 데이터 연결 시 incident 승격) |
| SEL_LOTTERY_MISS | **폐기** → SEL_DRAW_OUTCOME_UNCERTAINTY(lottery_draw 전용, 당첨 확률 표현 금지 — 확률은 외부 데이터 필요) | **pressure** |
| SEL_WAITLIST_DELAY | 분기: WAITLIST_PROLONGATION(confirmed_required — 대기명단 추론 금지) vs 일반 RESULT_DELAY | pressure |

공통: 선발은 방식(applicableSelectionModes) + **단계(applicableSelectionStages —
application_document/eligibility_check/assessment/draw/result_wait/waitlist/
placement_allocation)** 2축 — C3-c에서 stage 축 추가 시 적격성 영향이면
reviewEnvironmentVersion 갱신. 커밋 구조: C3-a(두 pressure 마감 — 완료) →
C3-b(CAR 4) → C3-c(SEL 4 + mode/stage 모델).

## 8. REL 차수(C5 — 감수 16차) manifest (데굴님 착수 조건 7건 고정)

**차수 불변식(데굴님 확정)**: 관계 위험은 십성이나 궁위만으로 현실의 상대를
만들어내지 않으며, 동일한 상대와 동일한 원인에서 나온 감정 충돌·오해·신뢰 저하·
거리감은 하나의 대표 위험과 보조 발현으로 정리한다.

착수 조건 반영: ①pressure·vulnerability·조건부 incident 재분류(아래 표) ②역할별
exposure(RelationshipContext — partner/family/peer/business) ③같은 상대·같은 원인
대표+흡수 역할(supporting_manifestation/background_vulnerability/possible_trajectory)
④배우자궁 활성≠partner exposure 분리(UNKNOWN=조건부, DENIED=차단·fallback 금지)
⑤PEER_FINANCIAL과 FIN 소유권 분리(requiresFinancialTie·confirmed_required·R2 병합
소관 명시) ⑥관계 컨텍스트 적격성 사용 → env `risk-engine-r0.5.7` + 해시 v5(적용
가능성 축·관계 실질 조건 편입) — reviewed 30항목 재스탬프 ⑦reviewed 수량 자동
manifest(`scripts/risk_review_manifest.py` → `doc/v2_2/RISK_REVIEW_MANIFEST.json`,
회귀 `tests/regression/test_risk_review_manifest.py`).

| 이전 항목 | 처리 | kind | family | rank | 역할/노출 |
|---|---|---|---|---|---|
| REL_PARTNER_READJUST | 재저작(reviewed 반납 — 재감수 대상) | incident→**pressure** | relationship_adjustment | 3 | spouse·current_partner·dating_partner / required_for_exposure(UNKNOWN=advisory 조건부) |
| REL_EMOTIONAL_CLASH | 재저작 | incident→**pressure** | communication_conflict | 2 | 역할 무관 / 흡수 힌트 supporting_manifestation |
| REL_MISUNDERSTANDING_SLIP | **개명** REL_COMMUNICATION_MISALIGNMENT | incident→**pressure** | communication_conflict | 2 | 역할 무관 / 흡수 힌트 supporting_manifestation |
| REL_TRUST_EROSION | **개명** REL_TRUST_STABILITY_WEAK | pressure→**vulnerability** | relationship_stability | 1 | structural_weakness(겁재)+파 계약 — 단독 겁재 미활성 |
| REL_DISTANCE_ESTRANGE | **개명** REL_DISTANCE_PRESSURE | **pressure** | relationship_stability | 1 | 공망·묘절·편인=amplifier 강등 / 흡수 힌트 possible_trajectory |
| REL_FAMILY_BURDEN | 재저작 | **pressure** | family_responsibility | 3 | family_member / requiresSharedResponsibility(돌봄·재정·주거·의사결정 — 미확인 시 CONFIRMED 강등) |
| REL_MONEY_BETWEEN_PEERS | **개명** REL_PEER_FINANCIAL_ENTANGLEMENT_RISK | **조건부 incident** | peer_finance | 3 | friend_peer·colleague·business_partner / confirmed_required+requiresFinancialTie, unknownExposable=false, 2독립 원인(multi_cause_only) |

**C4-f(HOS 후속)**: CAR_HIRING_OUTCOME_SETBACK에 결과 단계 게이트
`applicableSelectionStages: [result_wait, final_decision]`(어휘에 final_decision 신설)
— 지원·면접 단계 통지 어긋남 미적용(절차 지연은 HIRING_PROCESS_DELAY), fixture 3종.

**REL 밀도 실측(10차트, 세운+월운, 관계 컨텍스트 부재=전 REL UNKNOWN 가정)**:
family 도메인 기여도 relationship 32%→**19%**(contract_legal 23%가 최대로 교대) ·
REL 활성 family/기간 p50 1·p90 2·max 3 · REL 단일 원인 확산 max **2**(목표 ≤1·독립
발현 예외 2 이내) · 흡수 역할 실측 possible_trajectory 13·supporting 6·background 4 ·
REL 발동률 최고 FAMILY_BURDEN 27.7%(>40% 차트 0) · partner DENIED 오발동=0(단위
fixture 고정). 전체 지표 개선: structural incident/기간 1.75→1.22, exposure-qualified
0.65. 잔여 경고: 전역 단일 원인 확산 max 9(>3) — 미개정 MOV·HLT + 교차 도메인 관측
후보가 원천(다음 차수 대상), LEG_REVIEW_CAPACITY_WEAK 37.3%(vulnerability 수동 검토
대상 유지).

**테마사주·AI채팅 궁합 연동(설계 고정, 배선 R3/R5)**: 궁합·함께보기의 동반자 관계힌트
→ RelationshipContext(role·target_id 확인, `is_question_target=true`) — 친구 궁합에서
배우자 항목 MISMATCHED 차단, 해당 동반자 관련 REL 후보만 target_id로 선별.

상태: REL 7항목 reviewed:false(표본 감수 대기 — 승격 시 reviewed_total 30→37,
자동 manifest로 확인).

### 8-1. 감수 17차 — 커밋 전 필수 조건 7건 반영 (데굴님 조건부 승인 후속)

1. **대표 선택 결정성**: 비교자=(노출 적격 → 구체 상대(target_id) → 역할 특정 →
   specificityRank → canonical risk_id) — 사전 항목 순서 역순 엔진과 결과 동일
   fixture(`test_representative_deterministic_under_item_order`). 대표 체인 금지 유지
   (A├─B supporting └─C trajectory, B→C 없음).
2. **target_id 미확인 수렴 제한**: 같은 target_id가 아니면 관계 사실(relation 원자 —
   대상 객체 서명 내장) 공유 필수 — 십성 유입(겁재)만 공유한 부모 부담 vs 형제 오해
   수렴 금지 fixture. 실측: 십성 원자 단독 흡수(background 4건)가 병존으로 전환.
3. **is_question_target 의미 제한**: 질문 직접 대상만 의미 — exposure·금전 거래·공동
   책임 자동 확인 금지 fixture(궁합 대상 친구 + financial_tie 미확인 → 비노출 유지).
4. **FAMILY_BURDEN 월주 조건부**: 년주=단독 경로 유지, 월주=가족 육친 대상(인성=부모·
   비겁군=형제) 피격 provenance 명시 발동만(월주 충+일반 기신 → 미생성 — 직업 변화의
   가족 문제 오역 차단). 발동률 27.7%→20.0%. 배우자=PARTNER_READJUST 소유권 명시.
5. **possible_trajectory R1 불변식 기록**(RISK_ENGINE.md §5): occurrence·독립 원인·
   incident 생성·등급 상승 기여 금지, 표현 "지연되면 거리감이 커질 수 있다" 수준 한정.
6. **교차 도메인 연결 키**: `RiskCandidate.trigger_cause_atoms`(정렬 trigger 원인
   원자) — FIN·REL 같은 원인 병존 후보의 R1 1회 계산·R2 대표 1개 선택 재료.
   공유 relation 원자 fixture 고정.
7. **r0.5.6→r0.5.7 비REL diff 실측(10차트·비REL 2,759건)**: 기존 대표 변경 **0** ·
   신규 흡수 **0** · 흡수 해제 **0** — 전역 알고리즘 변경의 비REL 무영향 확정.

추가: UNKNOWN 노출 차등 — 역할 특정 항목의 조건부 노출은 alignment=matched(관계
확인·질문 대상)에서만(엔진이 exposable_when_unknown 기계 차단), 연애 질문 fixture로
조건부 경로 보존 확인. cross-family 흡수는 absorbedRoleHint 명시 항목만(TRUST에 hint
명시 — FAMILY_BURDEN·PEER_FINANCIAL 자동 흡수 금지). final_decision 어휘 의미 제한
(내부 승인·최종 판단 실제 진행 중 단계만 — 결과 궁금증만으로 추론 금지) 주석 고정.

**재실측(17차 반영)**: relationship 기여 17%(3위 — contract_legal 23% 1위 유지:
R1 진입 전 C2 cross-family 재검토 후보), REL family/기간 p50 1·p90 2·max 4(십성 원자
단독 수렴 해제로 정당 병존 증가), REL 확산 max 2 유지, FAMILY_BURDEN 20.0%,
전체 family p50 4·p90 8·max 13, 전역 확산 max 8(미개정 MOV·HLT 원천). 밀도는 전
REL UNKNOWN 가정 — 3프로필 시나리오(all_unknown/typical_confirmed/high_exposure)
재실측은 MOV·HLT 차수 후 예정.

## 9. MOV 차수(C6 — 감수 18차) manifest (데굴님 착수 조건 6건 선행 고정)

**차수 불변식**: 이동·주거 위험은 운 신호만으로 이사 계획·계약·차량·통근의 존재를
만들어내지 않으며, "원치 않는 이동"은 사주 신호가 아니라 preference=undesired 확인이
결정한다. 같은 이동 episode의 일정 지연·계약 문제·수리비·적응 부담은 대표 1건+보조
역할로 수렴한다.

### 9-1. MobilityContext (조건 2·3·6 — 적격성 사용 → env r0.5.8)

- target_type 8종: residential_move / housing_search / housing_contract /
  workplace_relocation / temporary_stay / commute_change / travel_transport / vehicle_use
- stage 8종: no_plan / considering / searching / negotiating / contracted / preparing /
  moving / settled
- preference: desired / neutral / undesired (None=미확인) — **적격성 미사용, R3 표현
  전용**(undesired 확인 시에만 '원치 않는' 표현. 신호만으로 비자발 판단 금지)
- housing_tenure: owner / renter / family_home / dormitory / company_housing / temporary
- 추가 현실 노출: active_contract(stage 축이 대체 — 별도 flag 없음) ·
  repair_responsibility · commute_dependency · vehicle_exposure ·
  assignment_authority(R1 예약 — CAR 소유권 보조)
- 3상태(target_type·stage 축): MISMATCHED=BLOCKED(fallback 금지) / UNKNOWN=구조 보존
  +**하드 비노출**(selection 축과 동일 — 이사·차량 특정 표현은 계획 확인 없이 불가) /
  MATCHED=exposurePolicy 소관(조건부 표현 포함)

### 9-2. 재분류·소유권 (조건 1·4)

| 항목 | 처리 | kind | family | rank | target/stage/노출 |
|---|---|---|---|---|---|
| MOV_CONTRACT_FAIL(reviewed) | 축·정책 추가(구조 변경 — C6 재스탬프, 감수 대상) | incident 유지 | housing_contract | 3 | residential_move·housing_search·housing_contract / searching·negotiating·contracted / required_for_exposure |
| MOV_SCHEDULE_DISRUPTION | incident→**pressure** 재분류, 공망 트리거 강등(문서·계획 공망 shape=인성 동반) | pressure | move_execution | 2 | residential_move·housing_contract·temporary_stay / contracted·preparing·moving / required_for_exposure · 흡수 힌트 supporting_manifestation |
| MOV_DEFECT_REPAIR_COST | 계약 강화(겁재+인성 동반 shape+주거 피격 linked) | incident | housing_defect | 3 | residential_move·housing_contract·temporary_stay / requiresRepairResponsibility(미확인=UNKNOWN 강등·없음 확인=DENIED) |
| MOV_COMMUTE_BURDEN | 운성 트리거→amplifier 강등 | pressure | mobility_load | 1 | commute_change·workplace_relocation·travel_transport·residential_move / requiresCommuteDependency · 흡수 힌트 impact_amplifier |
| MOV_UNWANTED_MOVE | **개명** MOV_RELOCATION_PRESSURE(비자발 전제 명칭 제거) | incident→**pressure** | relocation_change | 2 | residential_move·temporary_stay(발령·보직=CAR REASSIGNMENT primary — workplace 제외) |
| MOV_VEHICLE_TRANSPORT_ISSUE | 조건부 사건화 | incident | vehicle_transport | 3 | vehicle_use·travel_transport·commute_change / requiresVehicleExposure+unknownExposable=false(차량 존재 추론 금지) |

**소유권(조건 4)**: 직장 발령·보직=CAR primary(MOV_RELOCATION_PRESSURE는 workplace
MISMATCHED) / 주택 계약 해지·문서·법적 책임=LEG primary(MOV_CONTRACT_FAIL은 '이사
진행 무산'이라는 주거 현실 사건 — crossDomainEffects로 LEG·FIN 연결) / 계약금·보증금·
수리비 금전=FIN 파생(crossDomainEffects) / 거주 이동·일정·적응=MOV primary /
교통·이동 안전=안전 권고 톤(사고·부상 단정 금지, HLT 파생).

### 9-3. 같은 이동 episode 수렴 (조건 5)

현실 대상 수렴 도메인을 relationship→{relationship, relocation}으로 확장: 같은 관계
사실(relation 원자) 공유 + absorbedRoleHint 명시 항목만 cross-family 흡수. 수렴 트리:

```text
대표(계약 무산 또는 이동 압박)
├─ 일정 차질 → supporting_manifestation
└─ 통근·적응 부담 → impact_amplifier
하자·수리비, 차량 문제 → 별개 현실 문제(자동 흡수 금지 — hint 없음)
```

### 9-4. 억제 회귀 자동 게이트 (감수 17차 §7 후속)

`scripts/risk_suppression_baseline.py` 신설 — 억제 결과(차트·기간·risk_id→대표)
baseline을 git 추적하고, 억제 의미 변경 차수마다 --check로 diff를 산출해 감수 보고에
포함한다(비대상 도메인 대표 변경>0 → env 갱신+표본 재감수). 승인 후 --write 재생성.

### 9-5. C6 구현 결과 (감수 18차 — 표본 감수 대기)

- **env r0.5.8 + 해시 v6**(이동 축·이동 실질 조건 structure 편입) — reviewed 37 재스탬프.
  MOV_CONTRACT_FAIL(reviewed)은 축·정책 추가로 구조 변경(reviewVersion "C6") — 재감수 대상.
- 재저작 5 + CONTRACT_FAIL 메타: manifest §9-2 그대로. 밀도 교정 1건 — COMMUTE_BURDEN의
  해(HAE) 트리거 제거(31.8%·>40% 차트 4 → 충 단독 회귀). RELOCATION_PRESSURE에 수렴
  hint(supporting_manifestation — 구체 사건 대표 존재 시 수렴, 단독일 땐 대표).
- fixture 13종(test_risk_mov_c6.py): 항목별 recall 6 + 발령=CAR 소유권 차단 + 타 도메인
  무영향 + 축 UNKNOWN 하드 비노출 + stage MISMATCHED + 차량 추론 금지(미확인 비노출·
  없음 차단) + 통근 의존 강등 + 같은 이동 episode 수렴(대표 1 family) + 하자 병존 +
  preference 적격성 무영향.
- **억제 baseline 게이트 신설**(scripts/risk_suppression_baseline.py, §9-4): C5 시점
  baseline 3,330건 대비 diff — **relocation 도메인만 변경**(신규 흡수 21=episode 수렴,
  후보 소실 214·신규 155=재저작·개명·계약 강화), 타 도메인 0건.
- 밀도: relocation 기여 14%→**12%**, MOV family/기간 p50 1·p90 2·max 3, MOV 단일 원인
  확산 max 2, 흡수 실측 impact_amplifier 44·supporting 6. structural incident/기간
  1.22→**1.09**, exposure-qualified 0.31(이동 축 게이트 반영 — UNKNOWN 가정 하한).
  context-exposable family/기간 p50 3·p90 4·max 8(계층화 목표 ≤4~5 이내). 전체 family
  max 12 구성 실측: 7도메인 12 family 정당 병존(단일 상대·원인 복제 아님).
- 상태: MOV 5항목 reviewed:false(표본 감수 대기 — 승격 시 37→42), CONTRACT_FAIL은
  reviewed 유지+C6 재스탬프(구조 변경 감수 필요). RISK_ENGINE_MODE=off 유지.

### 9-6. 감수 19차 — C6 커밋·승격 전 필수 조건 8건 반영 (표본 감수 대기)

1. **감수 절차 교정**: MOV_CONTRACT_FAIL을 승인 전 reviewed 해제(reviewPending="C6",
   scope·해시 제거 — manifest 37→**36**). 절차 자동화: `scripts/risk_restamp.py` —
   git HEAD 구조 본문과 비교해 내용 불변 항목만 env 재스탬프, 내용 변경 항목은 자동
   강등(reviewPending) + reviewed:true·reviewPending 동시 존재 lint 금지.
2. **canonical ID 완화**: MOV_CONTRACT_FAIL→**MOV_CONTRACT_SETBACK_RISK**(허용 의미=
   협의 차질·조건 변경·일정 재조정, 금지=무산·실패·이사 불가 단정 — manifest·claim 개정).
3. **stage 호환 억제**: mobility_stages 상호 배타 시 수렴 금지 — 계약 episode에서 일정
   차질(contracted 교집합)만 수렴, 통근 부담(moving·settled)은 수렴 금지 fixture.
   이사 후 episode에서는 이동 압박 대표 아래 통근=impact_amplifier 수렴 fixture.
4. **mobility episode_id**: 익명 계획 키 — 서로 다른 계획(새 집 계약 vs 통근 조정)은
   원인을 공유해도 병존 fixture. 수렴 우선순위: episode_id > 대상 provenance > 원인 공유.
5. **UNKNOWN 차등**: RELOCATION_PRESSURE=required_for_warning(축 미확인에서도 '거주·
   이동 조건을 조정할 변수' 수준 조건부 — 예상 못한 이동 압박 경고 보존), 구체 항목은
   하드 비노출 유지. is_exposable이 exposure_requirement로 차등 판정.
6. **workplace 병존**: 컨텍스트 목록+is_question_target — 발령 질문 단독=MISMATCHED,
   발령+별도 주거 이동 확인=CAR·MOV 병존(episode 연결) fixture.
7. **confirmed 시나리오 실측**(scripts/risk_shadow_density.py --mov-scenarios, 10차트):
   노출 가능 MOV 후보 — 계획 없음 25 / 이사 진행 38 / 통근 의존 52 / 정착+수리 56
   (활성 99 동일 — 구조 불변·노출만 차등). 노출 가능 family/기간 p50·p90 1(max 2),
   단일 원인 확산 max 2, 차단 0. 하드 비노출로 낮아진 0.31과 실제 노출 밀도 분리 확인.
8. **하자·수리·적응 분리**: DEFECT→**MOV_HOUSING_DEFECT_RISK**(하자·수리 필요 전용,
   비용=FIN repair_cost_exposure·책임=LEG contract_responsibility_review 파생, cause
   atom 보존), COMMUTE에서 '정착 적응 피로' manifest 제거(통근 전용 — 정착·적응
   pressure 신설 여부는 감수 질문), 단계=이사 이후.

**baseline diff 분류 확장**(--rename, 항목별 delta): relocation만 변경 — rename-
equivalent 130/130, 신규 흡수 20(episode 수렴), 소실 200(UNWANTED 68·VEHICLE 43·
DEFECT 43·SCH 32·CMT 14 — 계약 강화·트리거 제거 의도 결과), 신규 141(재저작 경로),
타 도메인 0. 상태: MOV 6항목 전부 reviewed:false(감수 대기 — 승격 시 36→42).

### 9-7. 감수 20차 — C6 마감 조건 4건 반영·승격 (데굴님 조건부 승인 이행)

1. **restamp 기준 교체**: 불변 판정의 1차 기준=git HEAD→**저장된 reviewHashes**(작업
   순서 비의존 — 변경이 먼저 커밋돼도 강등). HEAD 비교는 해시 스키마 이행
   (--schema-migration)의 보조 진단으로 격하. 필수 회귀 3종
   (tests/unit/test_risk_restamp.py): 룰 변경=커밋 여부 무관 강등·부분 스탬프=변경
   취급·현 리포 정합 0건.
2. **MOV_HOUSING_DEFECT_RISK 적격성 분리**: requiresRepairResponsibility를 본체에서
   제거(임차인도 입주 지연·사용 불편·보수 요청을 겪음 — 과소탐지 방지). 수리 책임은
   FIN 파생(repair_cost_exposure) 게이트 전용(DENIED→비용 파생만 차단, R1 배선).
   repair DENIED에서 본체 활성·노출 유지 fixture.
3. **RELOCATION_PRESSURE DENIED 정책 확정**: 계획 DENIED('계획 전혀 없음' 명시)=
   BLOCKED — UNKNOWN(advisory 조건부)과 동일 처리 금지, 구체 이사·이전 표현 차단
   (prohibitedClaims 명시). 일반 생활환경 fallback은 저작하지 않음(fallback 금지 —
   필요 시 R3 별도 감수). fixture 고정.
4. **episode identity**: 이동 게이트 항목은 **episode별 후보 분리 생성**(같은
   risk_id+기간+episode 2개→후보 2개, exposure·정렬 독립) + 같은 episode 중복
   컨텍스트=입력 순서 무관 결정적 병합 + episode 경계가 흡수 범위를 가름(한 episode
   대표가 다른 episode 미흡수) fixture 3종.

시나리오 비율 지표 추가: exposable/active 25.3%(계획 없음)→38.4%(이사)→52.5%(통근)
→56.6%(정착+수리), blocked 0%, UNKNOWN 보존 74.7%~43.4%. '계획 없음 25'는 전량
RELOCATION_PRESSURE 조건부(advisory) — DENIED와 구분 fixture로 고정.

**승격(감수 20차 조건부 승인 이행)**: MOV_CONTRACT_SETBACK_RISK 재승격 + 신규 5 승격
(reviewVersions "C6") — **reviewed 36→42**(자동 manifest 확인), restamp 가드 42건
정합. 억제 baseline을 C6 확정 상태로 재기록(--write, 다음 HLT 차수의 기준선).

## 10. HLT 차수(C7 — 감수 21차) manifest (데굴님 착수 조건 8건 선행 고정)

**차수 불변식(데굴님 확정)**: 건강 질문이나 명리 신호만으로 질병·치료·신체 부위를
만들어내지 않으며, 기존 질환·치료·신체적 업무 부담이 실제로 확인된 경우에만 해당
맥락의 위험을 설명한다.

### 10-1. 범위·수량 (조건 1)

기존 reviewed HLT_CHRONIC_FLAREUP은 HealthContext 적용·개명으로 구조가 변경되므로
**착수 시점에 강등**(reviewPending="C7") — reviewed 42→41. 재저작 대상 6 + **신설 2
(감수 질문 — 데굴님 §11 노출 정책·§15 필수 fixture가 치료·회복 및 신체 부담 항목을
전제하므로 저작 포함, 감수에서 거부 시 제거)**:

| 항목 | 처리 | kind | family | exposure |
|---|---|---|---|---|
| HLT_CHRONIC_FLAREUP | 강등+**개명 HLT_EXISTING_CONDITION_STRAIN**(악화 전제 완화) | incident→**pressure**(rank 3) | existing_condition | confirmed_required+requiresExistingCondition, unknownExposable=false |
| HLT_FATIGUE_ACCUMULATION | 재저작(generic 전용 트리거 교체) | pressure(rank 2) | vitality_load | required_for_warning(일반 컨디션 advisory) · 흡수 힌트 supporting |
| HLT_CONDITION_DECLINE | **개명 HLT_RECOVERY_CAPACITY_WEAK**(저하 전제 완화) | pressure→**vulnerability**(rank 1) | recovery_capacity | not_required(단독 노출 없음 원칙) · 흡수 힌트 background |
| HLT_FOCUS_DROP | 재저작(기신 편인 구조 약화) | vulnerability(rank 1) | vitality_load | not_required · 흡수 힌트 background |
| HLT_MOBILITY_ACCIDENT_CAUTION | **개명 HLT_MOBILITY_SAFETY_CAUTION**(사고 결과형 완화) — 이동 노출은 MobilityContext 재사용 | incident→**pressure**(rank 2) | mobility_safety | required_for_exposure+이동 축(vehicle_use·travel_transport·commute_change) |
| HLT_CHECKUP_NEED | 재저작('치료·시술 검토' 문구 제거 — 검진·관리 권고 전용) | incident→**pressure**(rank 2) | health_management | required_for_warning |
| **신설** HLT_TREATMENT_RECOVERY_LOAD | 치료·회복 과정 부담(§11·§15 근거) | pressure(rank 3) | treatment_recovery | confirmed_required+requiresTreatmentProcess(또는 recovery), unknownExposable=false |
| **신설** HLT_PHYSICAL_WORKLOAD_STRAIN | 직업적 신체 부담(§11·§15 근거 — 직업 존재≠신체 부하) | pressure(rank 3) | physical_workload | required_for_exposure+requiresPhysicalDemand |

승격 시: 41+8=**49**(신설 2 거부 시 47) — 자동 manifest로 확인.

### 10-2. HealthContext (조건 3·4·7)

질병명·진단·부위는 저장·식별자 사용 금지. 필드: context_type(8종: general_wellness/
existing_condition/current_symptom/treatment_process/recovery_process/physical_workload/
sleep_schedule_load/unknown) · condition_status(none/managed/currently_uncomfortable/
recently_worsened) · treatment_status(none/monitoring/ongoing/recent_procedure) ·
recovery_status(none/in_progress/recently_completed) · physical_demand(none/low/
moderate/high/shift_or_irregular) · exposure_status · **health_episode_id**(익명 —
기존 불편 관리 vs 치료 회복 vs 교대 근무 부담 분리, episode별 후보 분리·수렴 경계)
· is_question_target. 유도: 상태 "none"(명시 부재)→DENIED, None(미확인)→CONFIRMED여도
UNKNOWN 강등, physical_demand는 none/low→DENIED. **건강 질문(is_question_target)이
질환·치료 존재를 자동 확인하지 않는다** — 일반 컨디션 advisory만 가능.

### 10-3. 수렴·소유권 (조건 5·6)

수렴 도메인에 health_safety 추가(같은 건강 episode + relation 원자 공유 + hint):
대표 pressure ├ 피로·컨디션=supporting ├ 회복 여력=background └ 지속 시 기능 부담=
possible_trajectory(REL과 동일 불변식 — occurrence·원인·등급 기여 금지). 소유권:
업무량·근무 책임=CAR / 그 업무의 신체 부담=HLT(교차 — trigger_cause_atoms 보존) /
치료비·의료비=FIN / 보험·보상·법적 책임=LEG / 차량·교통=MOV primary(HLT는 주의력
압박, 이동 노출은 MobilityContext 재사용) / **실제 부상·질병 진단=예측 대상 아님**.

### 10-4. env·게이트 (조건 7·8)

적격성 의미 변경 → env **r0.5.9** + 해시 **v7**(healthContextTypes·건강 requires 4종
편입) — reviewed 42 재스탬프는 --schema-migration(저장 해시 기준 도구, HEAD 보조
진단, 사유 WORKLOG 기록). C6 baseline(3,271건+메타데이터) 대비 **비HLT 대표·흡수
변화 0** 게이트 — HLT 도메인 변화만 허용(분류 보고).

### 10-5. C7 구현 결과 (감수 21차 — 표본 감수 대기)

- **env r0.5.9 + 해시 v7**(건강 축·실질 조건 4종 편입). 재스탬프는 신설 도구 절차
  준수: `risk_restamp.py --restamp --schema-migration` — 저장 해시 기준 1차 판정,
  HEAD 본문 비교는 스키마 이행 보조(41건 불변 재스탬프·변경 0, 사유=해시 v7 이행).
- **HLT_CHRONIC_FLAREUP 착수 강등**(reviewed 42→**41**) + 개명 HLT_EXISTING_
  CONDITION_STRAIN(incident→pressure — 질환 악화 사건화 금지, confirmed_required+
  requiresExistingCondition+unknownExposable=false).
- 재저작·개명: RECOVERY_CAPACITY_WEAK(→vulnerability·회복 자원 공망 구조),
  FOCUS_DROP(기신 편인 구조 약화), MOBILITY_SAFETY_CAUTION(사고 결과형 완화·
  incident→pressure·MobilityContext 재사용), CHECKUP_NEED(incident→pressure·치료
  표현 제거), FATIGUE_ACCUMULATION(경로 2종 — 강한 기신 관살 shape+비겁 피격 TA,
  밀도 교정 42.7%→18.2%·최장 연속 8→2개월). **신설 2(감수 질문)**: TREATMENT_
  RECOVERY_LOAD·PHYSICAL_WORKLOAD_STRAIN(§11 노출 정책·§15 fixture 근거 — 거부 시
  제거, 승격 시 41→49, 거부 시 47).
- fixture 19종(test_risk_hlt_c7.py): 질문≠질환(자동 CONFIRMED 금지)·DENIED 차단·
  CONFIRMED 노출·치료 미확인 비노출·신체 부담 축(low=차단)·episode 분리·같은 episode
  수렴(supporting)·질병명/수술/입원 토큰 사전 전수 차단·**HLT 전 항목 pressure/
  vulnerability(런타임+사전 이중)**·강등 상태 확인.
- **baseline 게이트(메타데이터 포함)**: C6 기준 3,271건 대비 diff **전량 health_safety**
  (rename 76/76·신규 흡수 6·대표 변경 3·소실 145·신규 248 — PWS 신설 103 포함),
  **비HLT 변화 0**(조건 8 충족).
- 시나리오 5종(--hlt-scenarios, vulnerability는 단독 노출 없음 원칙으로 노출 지표
  제외): exposable/active 22.5%(all_unknown=건강 질문만과 동일 — 질문이 아무것도
  확인하지 않음 검증)→25.8%(치료)→27.5%(신체 부담), **특정 항목 미확인 오노출 0**,
  노출 family/기간 p90 1. '기존 질환 확인' 시나리오의 노출 증가가 미미한 것은 ECS
  2원인 계약의 희소 생성 정책 결과(코퍼스 내 성립 기간 희소).
- 밀도: health_safety 기여 20%(2위 — vulnerability 2종 구조 관측 증가분, 노출 지표
  아님), HLT family/기간 p90 2·단일 원인 확산 max 2, structural incident/기간
  1.09→**1.00**, 경고=전역 확산 9(교차 도메인 관측 — R2 episode 병합 소관)뿐.
- 상태: HLT 8항목 전부 reviewed:false(표본 감수 대기), RISK_ENGINE_MODE=off 유지.

### 10-6. 감수 22차 — C7 마감 조건 4건 반영·승격 49 (데굴님 조건부 승인 이행)

1. **FATIGUE 재저작**: GI_STRONG을 event_shape에서 제거(길흉 강도≠사건 형태 —
   amplifier·심각도 전용). 계약=의미 있는 소모 shape(기신 식상=설기 또는 기신 관살=
   책임 과다) AND 체력 기반(비겁군) 충·형 피격. 필수 테스트 2종: GI_STRONG 단독=미활성
   / shape+피격+GI_STRONG=활성·증폭 근거. 커밋 B test_pressure_only도 신계약으로 개정.
2. **ECS 1원인 watch 복원**: minIndependentCauses=2·multi_cause_only 제거(생성 조건≠
   등급 조건 원칙 — 질환 CONFIRMED+연결 원인 1개=watch, 2원인·convergence=warning은
   R1). 단일 targeted 이중 역할 경로(HYEONG 일지) 추가 + fixture. 코퍼스 실측에서
   여전히 성립 희소(형+병·사 운성 동반 조건) — 계약이 아니라 신호 희소성의 결과.
3. **shift_or_irregular 분리**: 확인 취급 집합 도입(physical=moderate/high만) —
   shift 단독=UNKNOWN 강등·비노출 fixture. schedule_load 필드 예약(R3). **monitoring
   비확인**(치료 중 단정 금지 — ongoing/recent_procedure만) fixture. TRL manifestation
   단계 분기(treatment_load/recovery_load — R3 상호 혼용 금지 규격).
4. **차량 episode MOV primary**: 이동 게이트 후보의 교차 도메인 수렴 그룹(mobility_
   gated 마커) — 같은 원인에서 MOV_VEHICLE 대표, HLT 안전 주의=impact_amplifier 수렴
   fixture. 차량 없는 이동자(travel_transport+vehicle_exposure=false)는 MOV 차단·HLT
   단독 활성(정당 병존 recall 원천).

**노출 역전 방지 불변식 일반화(조건 1의 파생 — 의도된 변경 허용 목록)**: 대표 흡수
적격성을 is_exposable 전체 기준으로 확장(비노출 후보는 노출 가능 후보를 흡수 불가)
+ is_exposable에 confirmed_required 미충족=비노출 명시화. **비HLT 파생 30건**(C6 감수
§7 규칙에 따른 기록): REL — 책임 미확인 FAMILY_BURDEN(비노출)이 DISTANCE·CLASH
advisory를 더는 흡수하지 못함(흡수 해제 12·대표 변경 3), MOV — 미확인 CONTRACT_
SETBACK이 RELOCATION 조건부 advisory를 못 지움(해제 6·COMMUTE 신규 흡수 3). 전부
"숨은 후보가 보이는 경고를 지우는" 역전의 제거 — env r0.5.9 정의에 포함.

vulnerability 추적 신설: 활성/기간 1.20 · 대표 흡수 23 · 승격 기여 0(R1 원칙).
시나리오 재실측: 오노출 0 유지, 신체 부담 확인 시 PWS 대표 승격+피로 supporting 수렴.
structural incident 1.00(감소분 구성: CHRONIC kind 재분류 주요인 — 트리거 강화·
suppression 부차). **HLT 8항목 승격(C7) — reviewed 49(health 8/8, unreviewed 0)**,
restamp 가드 49건 정합, baseline은 C7 확정 상태로 재기록.

## 11. LEG 재검토 차수(C8 — 감수 23차) manifest (데굴님 착수 기준 9건 선행 고정)

**차수 불변식(데굴님 확정)**: 문서·지연·계약·분쟁 신호가 있다는 이유만으로 모든
절차가 법적 위험으로 복제되지 않게 하고, 실제로 진행 중인 계약·행정·분쟁 episode에
해당하는 LEG 후보만 남긴다.

1. **감수 반납**: LEG 6항목(CONTRACT_CANCEL·DOCUMENT_ERROR·ADMIN_DELAY·DISPUTE_RISK·
   LITIGATION_ESCALATION·REVIEW_CAPACITY_WEAK) 착수 강등 — reviewed 49→**43**.
   PENALTY_LIABILITY(대표 7)는 이번 차수 축 미부여 유지(**감수 질문** — 규정 위반·
   책임 항목의 process 축 부여는 별도 판단).
2. **LegalProcessContext 신설**(SelectionContext 어휘 재사용 금지 — 공통 3상태
   판정기·episode identity·stage 억제·노출 게이트·결정적 병합만 공유):
   process_episode_id · target_type 8종(contract/administrative_application/
   permit_registration/settlement_recovery/rights_obligation/dispute/litigation/
   claim_compensation) · stage 11종(drafting/negotiating/submission/review/
   supplement_request/decision_wait/response_required/settlement/dispute_active/
   litigation_active/closed) · exposure · existing_dispute · existing_litigation ·
   document_responsibility/response_obligation(R1 예약) · is_question_target.
3. 재분류·소유권: CONTRACT_CANCEL→**LEG_CONTRACT_TERMINATION_RISK**(결과형 완화,
   active contract=target contract+exposure CONFIRMED) / DOCUMENT_ERROR=법적 효력·
   권리 문서 한정(선발 서류=SEL·주거 계약 진행=MOV primary), rank 3→2(계약 종료·소송
   대표 아래 수렴 가능) / ADMIN_DELAY=공식 행정·허가·등록 절차 한정(채용=CAR·선발=
   SEL·이사=MOV·정산=FIN primary) / DISPUTE=권리·의무·청구 대상 필요 /
   LITIGATION=confirmed_required+**requiresExistingLitigation** / REVIEW_CAPACITY_
   WEAK=vulnerability 유지·단독 노출 없음·background 수렴(신호 삭제가 아니라 process
   연결·episode·흡수로 37.3% 관리).
4. 수렴(같은 process episode·같은 원인): 구체 대표 ├ ADMIN_DELAY=supporting ├
   REVIEW_CAPACITY=background └ DOCUMENT_ERROR=supporting(독립 targeted 없으면).
   DISPUTE/LITIGATION은 exposure-aware 대표 원칙 유지(소송 미확인 시 dispute 대표).
   다른 process_episode_id=병존.
5. env **r0.5.10** + 해시 **v8**(legal 축·조건 편입), 재스탬프 43(--schema-migration).
6. C7 baseline(3,412건) 대비 **비LEG 변화=명시 허용 목록 외 0** 게이트.

### 11-1. C8 구현 결과 (감수 23차 — 표본 감수 대기)

- env **r0.5.10** + 해시 **v8**, LEG 6항목 착수 강등(reviewed 49→**43**, PENALTY_
  LIABILITY 유지 — 축 부여는 감수 질문), 재스탬프 43(--schema-migration).
- LegalProcessContext(§11-2 규격 그대로) + episode별 후보 분리·stage 억제·노출 차등
  전부 공통 기계 재사용. 개명 LEG_CONTRACT_TERMINATION_RISK. LITIGATION=
  requiresExistingLitigation+unknownExposable=false.
- **vulnerability 단독 노출 없음 명문화**(is_exposable) — 의도 변경 허용 목록:
  FIN_BUFFER_WEAK(취약성 대표)가 CASHFLOW_PRESSURE(노출 가능 압박)를 지우던 역전
  42건 해제(비LEG 파생 유일 항목 — baseline 분류 확인). **같은 현실 대상 판정
  일반화**: 관계 target_id → +이동·건강·법적 episode 동일성.
- fixture 8종(test_risk_leg_c8.py) + c2 개정(컨텍스트 기반 분쟁·소송 대표, 개명):
  process 없는 인성 약화=RCW 비노출 / 선발 서류=SEL·채용 대기=CAR(LEG 비노출) /
  허가·등록 진행=ADMIN 노출 / 같은 episode 수렴(문서 대표+지연 supporting+검토
  background, 활성 family 1) / 다른 episode 병존 / 진행 계약 필요.
- 밀도: structural incident 1.00→**0.95**, LEG family/기간 p90 2. **감수 판단 지점
  2건**: ①RCW 구조 발동 40.9%(노출은 0 — 코퍼스에 legal ctx 없어 흡수 미발생, 신호
  삭제 대신 비노출·수렴 통제 — 사용자 지시 방향) ②LEG 단일 원인 확산 max 3 실측
  구성 = 계약 종료(비노출)+분쟁(비노출)+**PENALTY_LIABILITY(미개정 — 유일 노출
  경로)**: 서로 다른 법적 현실 문제의 병존이나, PENALTY 축 부여 여부가 남은 변수.
- 상태: LEG 6항목 reviewed:false(표본 감수 대기 — 승격 시 43→49 복귀).

### 11-2. C8 감수 23차 결론 — 커밋 조건 반영·LEG 7항목 승격 (2026-07-16)

데굴님 결론: 기본 구조·6항목 재저작 방향·인프라(LegalProcessContext·env·해시 v8·
vulnerability 단독 노출 차단·비LEG 42건)는 승인, **6항목만의 재승격은 보류** —
아래 조건을 닫고 PENALTY 포함 **7항목** 반납→재승격(reviewed 49−7=42→49).

| # | 조건 | 반영 |
|---|---|---|
| 1 | PENALTY도 감수 반납 후 LegalProcessContext 적용 | 대상 5종(contract/rights_obligation/행정/허가/claim)+성립 전·종결 제외 stage 9종+`unknownExposable=false`(결과형 경고는 위반·제재 노출 확인 필수). 금지 표현에 벌금·과태료·처벌·유죄·행정처분 단정 추가 |
| 2 | LITIGATION_ESCALATION kind·명칭 재확정 | **LEG_LITIGATION_PROCESS_BURDEN · incident→pressure**(이미 소송 중=절차 부담, 사건 아님). 단계 전환 탐지는 별도 shape 확보 전 저작 금지. requiresExistingLitigation 유지 |
| 3 | RCW 40.9% 실제 절차 시나리오 재측정 | `--leg-scenarios` 4종(all_unknown/active_contract/행정/분쟁·소송): observed 90 전부 잠재 구조 — **독립 노출 0·독립 family 기여 0·대표 흡수 0**(전 시나리오, 목표 충족). 표기=observed latent vulnerability 40.9%·standalone exposable 0 |
| 4 | episode·stage·소유권 fixture 보강 | c8 fixture 8→**19종**: PENALTY 3종(무절차 비노출·의무 절차 노출·성립 전 비노출)/RCW 역할 보장/중복 컨텍스트 결정적 병합(입력 순서 무관)/stage 상호 배타 수렴 금지/closed 신규 생성 제한/이사 일정=MOV·선발 대기=SEL·관계 신뢰=REL 소유권/vulnerability 역전 방지 **전 도메인 synthetic**(7도메인 파라미터라이즈) |

파생 확정(권장 조건): ①stage `active_contract` 신설(12종) — TERMINATION은 이
stage 없이 노출 불가(negotiating 대체 불가) ②closed=명시 opt-in(엔진 규칙 — 종결
절차는 신규 LEG 후보 생성·흡수 불가, 사후 정산·청구는 별도 episode 병존)
③vulnerability 대표 금지 일반화(어느 도메인에서도 흡수 대표 불가 — 엔진 규칙+
synthetic fixture) ④`document_responsibility`/`response_obligation`은 R1 예약 유지.

- env **r0.5.10→r0.5.11**(vuln 대표 금지·closed opt-in·active_contract) — 타 도메인
  42건 env-only 재스탬프(내용 불변 확인), LEG 7항목 승격 스탬프.
- 밀도: structural incident 0.95→**0.92**(BURDEN pressure 재분류 효과 — 룰 약화
  아님), LEG family/기간 p90 2 유지, LEG 단일 원인 확산 max 3(=계약 종료+분쟁+제재,
  전부 비노출 구조 병존 — 노출 대표는 시나리오 실측 p90 1~3).
- baseline(3,412건) diff 전수 분류: FIN 42건(승인된 역전 해소·비LEG 유일)/개명 이동
  50+31건/같은 원인 LEG 구조 수렴 11건(비노출 단계)/RCW 흡수 해제 8건(episode 없는
  흡수 차단 — C8 설계). --write 재기록(env r0.5.11).
- **reviewed 49(전 도메인 unreviewed 0)** · manifest 재생성 · pytest 1960 ·
  ruff clean · mypy(C8 대상 파일 clean — 기존 테스트 타입 부채 142건 별도 보고).

### 11-3. C8 승인 확정(감수 24차) 및 R1 진입 게이트 (2026-07-16)

데굴님 최종 결정: 커밋 03eeac5·7항목 재승격·reviewed 49·env r0.5.11 **전부 승인 —
C8 마감 완료(재오픈 없음)**. RCW 40.9%는 latent 구조 관측률로 허용(단독 노출·대표·
독립 family·occurrence 기여 금지가 전부 기계 보장됐으므로 룰 축소 사유 아님).

R1 착수 전 별도 게이트(§10):

1. **PENALTY kind 정합화(감수 질문)**: 현 허용 표현(기한·요건 확인/의무 이행 점검/
   대응 준비)이 전부 점검 수준 — 실질 의미가 준법·의무 이행 pressure에 가깝다.
   R1 impact prior·risk budget 왜곡 방지를 위해 다음 중 하나로 확정:
   ⓐ formal violation/sanction exposure CONFIRMED+구체 제재 대상+독립 targeted
   shape 조건의 conditional incident 유지 ⓑ LEG_COMPLIANCE_OBLIGATION_PRESSURE 류
   pressure 재분류. — C8 재오픈 아님, R1 진입 게이트.
2. RCW 지표 분리(완료): rcw_became_representative=0 필수 / rcw_absorbed_as_
   background=정상 발생 가능 / rcw_standalone_exposable=0 필수.
3. 3프로필 baseline 고정(완료 — RISK_PROFILE_BASELINE.md): 하한 1.28/일반 1.56/
   상한 1.64 exposable/기간, R2 최종 선별 목표는 selected family ≤3 유지(raw
   structural 3 컷 금지).
4. **TYP-0**(테스트 타입 부채 142건): mypy production=0 즉시, tests=baseline 증가
   금지 → 별도 차수 0. 완료 조건 = mypy 0 + pytest 불변 + risk baseline diff 0 +
   3프로필 지표 불변. 순서상 R1보다 먼저.
5. 프로필별 양성 fixture recall 유지 / 교차 도메인 동일 cause occurrence 1회 규격 /
   possible_trajectory·vulnerability occurrence 기여 0 / R1 전 baseline commit·env·
   사전 해시 고정.

### 11-4. C8-f — 구 PENALTY kind 정합화 (감수 24차 확정, 2026-07-16)

데굴님 결정: 현 계약(허용 표현=점검 수준·노출=절차 확인 수준·결과 표현 전부 금지)
에서 kind는 **pressure가 맞다** — 재분류 확정.

- **LEG_PENALTY_LIABILITY → LEG_COMPLIANCE_OBLIGATION_PRESSURE**: kind incident_
  risk→pressure, claimCeiling conditional_warning→watch, manifestations 3종 교체
  (기한·요건 재확인 필요/의무 이행 상태 점검 필요/공식 대응 자료 정리 부담).
  prohibitedClaims·exposurePolicy(required_for_exposure+unknownExposable=false)·
  대상 5종·stage 9종·family liability(FIN_DEBT_GUARANTEE 수렴)·rank 3 유지.
- 별도 제재 incident는 actual violation exposure CONFIRMED + formal sanction
  proceeding CONFIRMED + 독립 event shape 데이터 확보 전 저작 금지(항목 note 명문화).
- 절차: 반납(49→48)→개명·전환→재승격(**49**). env r0.5.11·해시 v8 유지(사전
  structure/selection/exposure 해시 변경 — 엔진 의미 불변). suppression baseline
  diff=개명 이동뿐(비LEG 0)·재기록. 재측정: structural incident 0.92→**0.87**,
  나머지 지표 불변.
- **profile baseline 기계 판독 고정본 신설**(데굴님 §4): RISK_PROFILE_BASELINE.
  json + scripts/risk_profile_baseline.py --write/--check(완전 일치 원칙 — TYP-0
  게이트). blocked 분해 지표(도메인·risk_id·사유별) 추가.
- **SEL 45→0 범위 확정**(데굴님 추가 확인): C의 차단 468 전량 selection 도메인·
  selection 축 사유 — 채용 episode 국한 정상. **감수 질문**: SelectionContext는
  단수·episode 없음 → "채용+일반 선발 동시 episode" 병존 불변식은 selection 축
  episode 확장(SEL-e 차수) 전에는 표현 불가. 확장 전 R3/R5 배선은 질문 대상 선발
  1건만 주입하는 제약을 둔다.

다음 순서(데굴님 확정): TYP-0(테스트 타입 부채 142→0) → profile·suppression
baseline exact match 확인 → R1 착수.

## 12. SEL-e 차수(감수 25차) — 다중 선발 episode (2026-07-16)

데굴님 착수 승인 + 필수 기준 10건 확정 반영. 차수 불변식: **취업 지원 결과 대기와
별도 자격시험·추첨 지원이 동시에 실재할 수 있다 — 한 선발 건의 소유권 차단이 다른
선발 건의 후보를 지우지 않는다.**

1. **SelectionContext 확장**(단수→복수): `episode_id`(target_type과 별개의 명시 키
   — 같은 유형 2건 병존), `exposure_status`(UNKNOWN=전역 노출 인자 사용 — 단수
   하위 호환), `is_question_target`(기본 True — 단수 시절 질문 대상 의미 보존,
   프로필 유래 존재 정보는 False 명시).
2. **후보 identity**: risk_id + period + selection_episode_id(+target 축) —
   같은 risk_id라도 episode가 다르면 후보 분리 보존(examination_1/2 fixture).
3. **episode별 소유권**: mismatch는 해당 episode에만 적용 — 호환 episode가 있으면
   그 해석이 우선(전파 금지). 질문 대상 컨텍스트가 전부 명시적으로 축 밖일 때만
   BLOCKED(단수 시절 의미 보존 — 기존 축 사유 코드 유지). 소유권 매트릭스는
   risk_id×target_type×stage 그대로(채용+서류=SEL_DOCUMENT 적용 fixture).
4. **결정적 병합·보완 vs CONTEXT_CONFLICT**: 같은 episode의 중복 컨텍스트는 입력
   순서 무관 병합, 축별 명시 값 1개면 보완(stage만 아는 입력+mode를 아는 입력),
   서로 다른 명시 값 충돌이면 임의 우선순위 없이 selection_context_conflict —
   구조 보존·is_exposable 차단·suppression_reasons 위생 로그.
5. **수렴 경계**: 서로 다른 selection episode는 같은 cause를 공유해도 자동 흡수
   금지(구조 후보 병존 — R1 shared-cause 1회 계산은 trigger_cause_atoms 연결).
6. **env r0.5.11→r0.5.12**(엔진 적격성·후보 identity 변경), 해시 v8 유지(사전
   필드 불변). 감수 반납 SEL 7+CAR_HIRING 2=9항목(49→40)→재승격(49). 타 40건
   env-only 재스탬프(내용 불변). 단수 selection_context와 [ctx]는 결과 동일
   (byte-identical fixture).
7. **blocked 집계 3층 확정**(선행 — 데굴님 §4): unique(468) / candidate×reason
   pairs(927 — target·stage 축만 520=214+202+2×52 불변식 assert 내장) / raw rule
   hits(927). 927은 selection 축 외 사유(evidence_groups_unmet 406 등)를 포함한
   후보×사유 pair였음 — 명칭 정정.
8. **검증**: fixture 8종(test_risk_sel_e.py — 병존 2·미전파·복수 episode·결정적
   병합/보완·충돌·legacy 동등·문서 매트릭스) + 기존 위험 테스트 198건 불변 +
   suppression baseline diff 0(3,412건 — 코퍼스 무선발 컨텍스트) + **A/B/C profile
   지표 완전 동일**(의도 변화 없음) + **D_multi_selection 신설**: episode별 활성
   hiring 4/exam_1 25/exam_2 32/lottery 23, BLOCKED 202(전량 stage 사유 — C의
   소유권 468이 episode 병존으로 축소, SEL 기여 0→33 복원), exposable 1.58/기간·
   family p90 4(episode 수 무제한 비례 없음). pytest 1968·ruff·mypy 0 clean.
9. R3/R5의 '질문 대상 선발 1건만 주입' 임시 제약 해제 가능(배선 시 복수 episode
   공급 전환 — 배선 차수 소관).

## 13. R1-a 차수(감수 26차 착수) — 점수 인프라·shadow 전용 (2026-07-16)

데굴님 R1 착수 승인 + 불변식 7건 반영. **R1 성공 조건: 동일한 원인을 여러 도메인·
episode에서 한 번만 평가하고, 점수 계산이 이미 감수된 적격성·노출·대표 선택을 단
한 건도 변경하지 않는 것.**

- 선행: blocked 지표 명칭 분리 — `blocking_axis_reason_pairs`(축 mismatch=실제
  차단)/`evidence_deficiency_reason_pairs`(INSUFFICIENT 계열 동반 기록)/
  `blocked_candidate_all_reason_pairs`/`blocked_raw_rule_hits`. C=468/520/407/927,
  D=202/251/180/431(D의 blocking_axis에 mode 49 포함 — 사유 전량 표시).
- **saju_engines/risk_scoring.py 신설**(순수 함수·shadow 전용 — 랭킹·노출·등급
  없음): ①`score_shadow()` — 6축 RiskScoreComponents+confidence만 채운 사본 반환
  (그 외 필드 byte 불변 fixture) ②occurrence=TRIGGER 근거의 source(원인 사실)
  단위 포화형 결합 1-Π(1-s) — evidence 1회·같은 대상 충+형=원인 2·다층 반복=원인
  1(layer convergence는 confidence 진단만) ③`cause_occurrence_table()` —
  (period, cause_atom)당 1회 계산 표(포트폴리오·episode 합산의 원천 — 후보 합산
  금지) ④compound=같은 기간 원인 공유하는 **다른 risk_id** 연결만(교차 도메인
  확산 축 — occurrence 중복 가산 아님) ⑤persistence=반복 기간 수만((n-1)/5 cap)
  ⑥protection=실질 조건 동반 mitigator만(극성 단독 0)·미래 회복 반영 금지
  ⑦`risk_priority()` — §5 공식 total은 마지막 한 번, (raw, capped) 병행 반환·
  후보에 저장하지 않음(포화 진단=raw, 소비=capped).
- 기여 0 역할 fixture: polarity amplifier·context(episode·질문 대상·CONFIRMED·
  conflict)·mitigator가 occurrence를 올리지 못함. D-프로필 golden 축소판(시험 2
  episode 같은 원인 → cause 표 1항목·동일 평가).
- 버전: **env r0.5.12 유지**(후보 생성·적격성·suppression 불변 — suppression
  baseline diff 0·A/B/C/D 지표 불변으로 실증), 점수 의미는
  **`RISK_SCORING_VERSION = "risk-score-r1.0.0-shadow"`** 별도 추적. 감수 scope는
  shadow_structure 유지 + R1-c에서 `shadow_scoring` 추가 예정.
- 가중치·매핑(exposure 상태 가중 1.0/0.55/0.15/0.0, persistence span 5, compound
  0.25/연결, confidence 휴리스틱)은 전부 **잠정값 — R1-b/c 실측 후 감수 확정
  대상**(UNKNOWN 0.55는 사실 대체가 아니라 투명한 랭킹 정책 가중, §5-1 상한
  warning 별도).
- fixture 9종(test_risk_scoring_r1a.py). pytest 1977·ruff·mypy 0(519파일)·전
  baseline exact match·manifest 일치.
- 다음: R1-b(대표 항목 표본 — kind·컨텍스트 조합) → R1-c(49항목 shadow scoring
  분포·포화율·A/B/C/D 비교·recall 생존 + shadow_scoring scope 감수).

### 13-1. R1-a 후속 보완(감수 26차 확정 5건 — R1-b 착수 전) (2026-07-16)

1. **cause identity 계약 명시**: 관계 원자 `relation:<종류>:<궁위>:<자리>[:<글자>]
   [:<십성>]`은 매처가 사실 기반으로 만든 canonical 서명으로 **target_object_
   signature 내장** — 같은 관계+다른 대상=원인 2, 같은 대상+다른 관계=원인 2,
   같은 대상·관계 다층=원인 1(+supporting layer, convergence 진단). 같은 사실의
   재표현 룰은 같은 source 서명(root-fact dedup 자동). 로직 변경 불필요 —
   계약을 docstring+fixture 3종으로 고정.
2. **DENIED ranking 가중 0.15 제거**: exposure 축 = rankable 가중으로 재정의 —
   `is_exposable` 미통과(DENIED·NOT_APPLICABLE·confirmed_required+UNKNOWN·
   unknownExposable=false·CONTEXT_CONFLICT·vulnerability·축 미확인 구체 항목)는
   전부 **0**. 통과 후보만 CONFIRMED 1.0/UNKNOWN(조건부 허용 항목) 0.55 잠정.
3. **structural vs rankable 분리**: `structural_priority()`(exposure 제외) 신설 —
   DENIED counterfactual·오경고 분석 등 구조 진단 전용(노출·선별 사용 금지).
4. **compound = 독립 exposable 효과군**: risk_id 개수 기준 폐기 — 다른 risk_
   family + is_exposable + 미흡수 연결만(같은 family=alias·파생, supporting·
   vulnerability·비노출 연결=복합 위험 아님). fixture 4상황 고정.
5. **persistence = 최장 연속 구간**: 단순 반복 기간 수 폐기 — 같은 계열의
   longest contiguous run((run-1)/5 cap). 간헐 3회=run 1(0.0)≠연속 3개월(0.4).
   월운 라벨 존재 시 월 연속만 계산 — 같은 달을 지지하는 연운 라벨은 기간 중복이
   아니라 layer convergence. total/gap-adjusted 비교는 R1-b 측정 병행 출력.

`RISK_SCORING_VERSION` r1.0.0→**r1.0.1-shadow**(점수 의미 변경 — env r0.5.12
불변). fixture 9→**14종**. pytest 1982·mypy 0·전 baseline exact match.

## 14. R1-b 차수(감수 27차) — 표본 검증·슬라이스 1 (2026-07-16)

데굴님 착수 조건 2건(첫 슬라이스) + 표본 리포트. 감수 목표(데굴님 확정): **같은
원인은 하나로 계산되고, 다른 대상·작동 방식은 분리되며, 현실 exposure는 구조 발생
근거를 바꾸지 않고, 반복·복합·보호 축이 occurrence를 다시 복제하지 않는다.**

1. **cause namespace 계약 검증기**: TRIGGER 원자는 ①target 내장 canonical
   (relation:* — 궁위·자리·글자·십성 서명) ②명시적 전역 사실(ten_god:*=유입 자체가
   사실 / void=시점 공망 / stage:*=스냅샷당 대상 1개라 기간 내 유일)만 허용 —
   미상 namespace는 cause_occurrence_table이 **거부**(조용한 과소/과대 dedup 차단).
   polarity:*는 진입 전 필터. 엔진 실후보 전 도메인 관측 조합 전수 통과 fixture.
2. **structural/rankable 완전 분리**: `compound_family_links(exposable_only=
   False)`=구조 연결(exposure 무관 — 진단 전용) vs True=rankable(components.
   compound 재료). `structural_priority`는 compound 축 **제외**(exposability 내장
   축이 구조 진단에 새는 것 차단). 필수 fixture: CONFIRMED↔DENIED 전환 시
   structural(occ·impact·persistence·protection·priority·구조 연결) 완전 동일,
   rankable(exposure·compound·total)만 변화. 점수층 자체 방어 추가: DENIED/
   NOT_APPLICABLE 상태는 rankable 가중·연결 판정 모두 0(엔진 BLOCKED와 무관).
3. **persistence 경계 확정**: 연도 경계(2026-12→2027-02)=canonical month index로
   연속 3(0.4) / **상위 layer 직렬화 구분** — 세운 원인이 월 후보 12개에 복제된
   계열은 period-native trigger(월=월운·일운, 연=세운) 없음 → 지속 근거 아님(0.0),
   occurrence도 불변. persistence 키=lineage(risk_id+전 축 episode 서명 — 기간
   가로지름), cause instance(기간 내 원인)와 구분.
4. **표본 리포트**(scripts/risk_scoring_sample.py → RISK_SCORING_SAMPLE_R1B.md
   고정): 표본 7종 — cause identity(관계 3경계+비관계 전역+미상 거부)/exposure
   정책(CONFIRMED>허용 UNKNOWN>비노출 0, DENIED counterfactual 보존)/structural
   불변/compound 4상황/persistence 4상황/D-golden 다중 episode(후보 2·cause row
   1·평가 동일·compound 비증가)/protection(occurrence 불변·net 완화·극성 0·미래
   회복 반영 경로 없음 구조 보장). **예상 불변식 26개 전부 PASS**(§9 필드 전체
   출력 — 절대 점수가 아니라 관계 감수용).

`RISK_SCORING_VERSION` r1.0.1→**r1.0.2-shadow**(structural compound 제외·native
persistence — env r0.5.12 불변). fixture 14→19종. pytest 1987·mypy 0(520파일)·전
baseline exact match. 다음: R1-c(49항목 shadow scoring 전수 — 분포 p50/p90/max·
축 기여도·포화율(raw>1·raw>1.2·capped=1·축별 cap 도달률·상위 10% 축 구성)·
A/B/C/D 프로필 비교·양성 fixture score 생존 + shadow_scoring scope 감수).

## 15. R1-c0 차수(감수 28차) — 점수 의미론 고정 슬라이스 (2026-07-16)

데굴님 필수 보완 7건: **원자를 고유하게 식별하는 데 성공했더라도, 시점 상태·비공망·
취약성 같은 보조 조건까지 발생 원인으로 계산하면 점수는 결정적이지만 의미적으로
잘못될 수 있다.**

1. **occurrence 의미 registry**(canonical identity ≠ occurrence 적격):
   relation:*/ten_god:*=CAUSE · void=CONDITIONAL_CAUSE(단독=원인 아님 — CAUSE
   원자 동반 감수 룰의 조건으로만) · no_void=GATE_OR_PROTECTION(기여 0) ·
   stage:*=ACTIVATION_OR_CONFIDENCE(occurrence row 금지·confidence 보조 예약) ·
   polarity:*=AMPLIFIER · 미상=fail-closed 거부. CAUSE 원자 동반 source만
   occurrence 재료·cause table row도 CAUSE만. fixture: 상태 원자 추가 →
   occurrence·원인 수 불변 / 형+병 운성 → row 1 / 조건부 void → CAUSE 원자만
   row / ten_god semantic collapse(source·layer 반복=1개·layer는 confidence만).
2. **persistence = cause lineage**: 계열 키 = risk_id + **연결 episode 서명**
   (항목이 게이트하는 축만 — 무관 episode 자동 제외) + **CAUSE 원자 집합**.
   원인 교체형 연속(1월 충→2월 형→3월 유입)은 cause run 1 — 효과 연속은
   `effect_contiguous_runs()` 진단(R2 episode 분석 재료)으로만. gap 분리 fixture,
   무관 health episode 추가 → 계약 후보 전 점수·필드 byte 불변(엔진 fixture).
3. **compound normalized effect identity**: (kind, 연결 episode 서명) — 같은
   episode·같은 kind의 교차 family 복제(계약 일정 차질의 MOV·LEG·FIN 병렬)는
   compound 0, 다른 episode 독립 효과만 0.25. episode-free 쌍은 동일성 주장
   불가(후보별 고유 identity — riskFamily 교차 도메인 통합 저작+R2 대표 소관,
   **효과 role 어휘 정식화는 감수 질문**).
4. **confidence 분리**: candidate.confidence=structural(provenance·독립 근거·
   layer corroboration — context 무관 fixture) / `context_confidence()`=진단
   함수(CONFIRMED 1.0·UNKNOWN 0.5·conflict/DENIED/NA 0.0). context CONFIRMED가
   structural을 못 올리고 UNKNOWN이 occurrence를 못 내림(fixture).
5. **감수 hash 재료**: `scoring_config_hash()`(공식·가중·cap·매핑 전부 —
   ea789b931ee68d29) + `cause_semantics_hash()`(registry·정규화 —
   9f2e80bd80731edb) + CAUSE_SEMANTICS_VERSION=v2. R1-c2의 shadow_scoring
   scope 스탬프에 포함 — 잠정값(UNKNOWN 0.55·span 5·compound 0.25) 변경 시
   감수 자동 강등.

`RISK_SCORING_VERSION` r1.0.2→**r1.0.3-shadow**(env r0.5.12 불변). fixture
19→**26종**, 표본 리포트 불변식 **27개 전부 PASS**(고정본 갱신). pytest 1994·
mypy 0(520파일)·전 baseline exact match. 다음: R1-c1(49항목 전수 — cohort 분리
측정(A structural active/B ELIGIBLE/C context-exposable/D rankable>0/E BLOCKED·
INSUFFICIENT/F vulnerability), structural·rankable 분포 분리, 포화 지표 + 단조성
검증(원인 추가↛occ 감소·protection 추가↛priority 증가·CONFIRMED→UNKNOWN↛증가·
supporting/vuln 추가↛occ 증가·무관 episode↛변화·입력 순서 byte 불변)) →
R1-c2(가중 확정·shadow_scoring scope 승격).

### 15-1. R1-c0 후속(감수 29차 확정 6건 — R1-c1 착수 전) (2026-07-16)

지속성 = "같은 위험 이름의 연속"이 아니라 "같은 **원인**의 연속", 복합성 = "후보·
episode 개수"가 아니라 "서로 다른 **현실 효과**의 동시 존재"(데굴님 확정).

1. **persistence = 개별 cause lineage**: 키 = (risk_id, 연결 episode 서명,
   canonical cause_atom **1개**) — 보조 원인 증감({A}→{A,B}→{A})이 지속성을 못
   끊는다(A run 3=0.4). 후보 persistence = 지지 원인 lineage 중 최장 run. 묶음
   연속은 `trigger_bundle_contiguous_runs()`(진단 — {A,B}×3=bundle 3), 효과
   연속은 `effect_contiguous_runs()`(R2 재료). 원인 전체 교체({A}→{B}→{C})=run
   1·effect run 3(기존 fixture 유지).
2. **normalized effect role registry**: riskFamily는 교차 도메인 통합이
   liability 1건뿐(대부분 도메인 내부 키)이라 부족 — 데굴님 최소 어휘 기반
   49항목 전수 role 매핑을 **scoring 계층 registry**로 잠정 도입(cause_semantics_
   hash에 포함 — 변경=감수 강등. **사전 필드(normalizedEffectRole) 편입 여부는
   감수 질문**). 문서 결함(LEG·SEL)=같은 role 통합.
3. **compound = 서로 다른 role의 개수**: 같은 role은 family·도메인·episode 수와
   무관하게 복제/반복 폭(폭은 R2 breadth 소관). §8 fixture 5종: 같은 episode+
   다른 role=0.25 / 같은 role(교차 도메인)=0 / episode 수만 증가=0 / episode-
   free 미해결=**0 + unresolved 진단**(fail-closed — 고유 identity 부여 방식
   폐기: 독립성 증명 불가=제외). `compound_unresolved_counts()` 진단 신설.
4. **targeted void 계약**: 현재 매처의 void는 시점 전역 상태(궁위 무관) —
   궁위 지정 void 원자는 미정의 namespace로 fail-closed 거부됨을 fixture로 고정
   (도입 시 동반 CAUSE와의 target 일치 검증을 registry에 정의해야 함 — 배우자궁
   void가 계약 CAUSE의 조건이 되는 경로 차단).
5. **context confidence 축별 평가**: `context_axes()` — 후보가 요구하는 축만
   (required/confirmed/unknown/conflicted 분해, R1-c1 리포트 출력). 점수 미포함
   진단 유지.
6. 버전·해시: `RISK_SCORING_VERSION` r1.0.3→**r1.0.4-shadow**, CAUSE_SEMANTICS_
   VERSION v3(role registry·per-cause lineage 편입 — 해시 자동 변경). env
   r0.5.12 불변(전 baseline exact match).

fixture 26→**28종**, 표본 불변식 **31개 전부 PASS**(고정본 갱신 — {A}→{A,B}→{A}
지속·교차 role 복제·episode-free fail-closed·episode 수 비증가 포함). pytest
1996·mypy 0(520파일). R1-c1 추가 진단 예약: cause_set_churn_count·unresolved_
effect_identity_rate·episode_count_only_compound_violations(0 목표)·void_target_
mismatch_count(0 목표).

## 16. R1-c1 차수(감수 30차) — 49항목 전수 shadow scoring 측정 (2026-07-16)

착수 조건 반영: compound=연결된 effect graph(shared canonical cause)만(무연결
co-period=0 fixture) · is_question_target=context confidence 제외(fixture) ·
**이중 모집단**(전체 구조 코퍼스 + A/B/C/D overlay 별도 표) · 단조성 8종 fixture
고정. 측정 고정본: doc/v2_2/RISK_SCORING_SURVEY_R1C1.md.

### 16-1. 핵심 결과 (전 지표는 고정본 참조)

- **포화 없음**: raw>1 1~4%(구조 3/175, C-overlay 10/246), raw>1.2 최대 8건,
  축별 cap 도달 미미(exposure 7~13%=CONFIRMED 자체, persistence 0%) — 기존 사건
  엔진의 100점 포화 문제 재현 없음. total은 마지막 1회 계산 구조가 유효.
- **상위 10% 축 구성이 컨텍스트에 따라 건강하게 이동**: 구조 코퍼스=occurrence
  0.78·persistence 0.54 주도(compound 0 — episode 없음), C-overlay=exposure
  0.925·compound 0.573 상승 — cap·exposure가 분포를 왜곡하지 않고 컨텍스트
  확인이 상위 후보를 결정.
- **cohort 분리 유효**: 구조 코퍼스 A 914/C 281/D 175 — 비rankable 739가
  rankable 분포에서 제외되어 median 왜곡 없음(C군 rankable raw p50 -0.116 →
  D군 기준 보고).
- **감수 판단 지점 — unresolved effect identity**: 코퍼스 후보의 98%가
  episode-free라 cause 공유 연결이 전부 unresolved(fail-closed 0), **상위 10%
  후보 전원이 unresolved 연결 보유** — 데굴님 기준(다수면 가중 확정 보류)에
  해당. 원인은 측정 코퍼스의 구조적 특성(컨텍스트 미공급)이며, compound 자체는
  overlay에서 정상 작동(B 55·C 190·D 62건). **결론: compound 가중(0.25/cap)
  확정은 R1-c2의 normalizedEffectRole 사전 편입+episode 공급 시나리오 재측정
  후로 보류**(다른 축 가중은 확정 가능 후보).
- persistence 진단: unique lineage 1,061 · 다기간 793 · 후보 부여 1,034 —
  포트폴리오 원천=lineage 규격 확인. LEG D군 rankable이 균일(0.200)한 것은
  UNKNOWN 조건부 항목의 동일 구성(occ 0.5×imp 0.65×exp 0.55) — 실컨텍스트
  overlay(B/C)에서 1.000까지 분화 확인.
- 검증: 모집단 1 ≡ overlay A(all_unknown) 완전 동일(회귀 상호 검증),
  episode_count_only_violations 0 · void_target_mismatch 0 · 단조성 8종 fixture.

### 16-2. R1-c2 계획(감수 승인 대기)

①**normalizedEffectRole 사전 SSOT 편입**(감수 30차 지시): scoring registry →
사전 필드 이동, lint(49항목 전원 존재·enum 외 금지·kind 혼동 금지·변경 시
shadow_scoring 강등), dictionary hash 변경(v9 여부 포함 감수) ②episode 공급
시나리오에서 compound·unresolved 재측정 ③가중 확정(compound 제외 축 우선) ④
shadow_scoring scope 감수·스탬프(reviewHashes에 scoring_config_hash+
cause_semantics_hash 포함, 기존 shadow_structure 해제 금지).

## 17. R1-c2 차수(감수 31차) — 보고 정정·role SSOT·민감도/ablation (가중 확정 감수 대기)

### 17-1. R1-c1 보고서 표기 정정(데굴님 지적 5건)

①count/rate 분리(raw_gt_1/raw_gt_1_2/raw_ge_1/capped_eq_1 각각 건수+비율 —
구조 D군: 전부 3건(1.7%), '14%'/'713%'류 오독 표기 제거) ②exposure 1.0 =
CONFIRMED 범주값(exposure_at_max_rate)과 계산값 clamp(component_clamped —
persistence 4건 0.4%뿐)를 분리 집계 ③'포화 없음'→**'병적 상한 집중 없음'**:
capped=1 후보 risk_id 다양성(구조 1종)·상위 10% 동점(5/17·unique raw 12)·
p90/p95/p99 병기 ④상위 10% 6축 원값+**가중 기여(공식 항별)**+cap-loss —
**발견: 구조 코퍼스 상위는 persistence(+0.541)가 곱항(+0.169)의 3배로 주도**,
C overlay에선 곱항·compound가 역전 ⑤net_priority_raw(C군) 명칭·raw<0
64.8%(182건 — 전량 protection 감점)·capped=0·protection 0 하강 분리 보고.

### 17-2. normalizedEffectRole 사전 SSOT 편입(해시 v9)

- 사전 필드 `normalizedEffectRole`(+`normalizedEffectRoleByContext` 스키마 지원
  — 저작·소비는 감수 질문) 신설, 49항목 전수 저작(기존 registry 매핑 이관 후
  코드 registry 삭제 — scoring은 후보 복사 필드 소비).
- lint: enum(_RISK_EFFECT_ROLES 43종) 외 금지·kind 값 혼동 금지·(승격 시) 존재
  필수. **해시 스키마 v8→v9**: `shadow_scoring` scope 신설(본문=role·ByContext·
  baseImpact) — role 변경은 shadow_scoring만 강등(shadow_structure 유지),
  스탬프에 scoring_config_hash·cause_semantics_hash 병기 예정.
- scope별 pending: `reviewPendingScopes: ["shadow_scoring"]` 49항목 표시(항목
  전체 강등 없음 — shadow_structure 49/49 유지, shadow_scoring 0/49 감수 대기).
- v9 이행 재스탬프 49건(--schema-migration — 본문 불변 확인), env r0.5.12 불변,
  baseline 메타 갱신(지표 diff 0 확인 후 재기록).

### 17-3. E1~E6·민감도·ablation·pairwise (고정본 RISK_SCORING_SURVEY_R1C1.md)

- E1~E6은 전부 단위 fixture로 고정 완료(§8 — 교차 role 복제 0/다른 role 0.25/
  episode 수 비증가/독립 가능/episode-free 0+진단/무연결 0).
- **compound 증분 민감도(C overlay·기준 0.25)**: inc=0 → top10 overlap 4/10
  (compound가 상위 순위의 주 결정자), 0.10 → 7/10, 0.15 → 9/10(역전 26,
  compound 최대 항 11건). 데굴님 지적대로 0.25는 작지 않음 — **0.10~0.15
  구간이 완만(권고: 0.15 우선 검토)**, 확정은 감수 소관.
- **exposure UNKNOWN 가중 ablation**: 1.0/0.775/0.3 전 구간 top10 overlap
  10/10 — 상위 순위는 UNKNOWN 가중에 둔감(상위=CONFIRMED 위주), exposure가
  상위를 과도 지배하지 않음.
- **pairwise golden 3종 PASS**(기대 순서 명시): 같은 구조 CONFIRMED 0.300 >
  허용 UNKNOWN 0.165 > 비노출 0 / 강한 구조+UNKNOWN 0.308 > 약한 구조+
  CONFIRMED 0.120(구조 우위 유지) / 근접 구조에선 확인된 현실 우선(0.300 >
  0.181).

### 17-4. 감수 대기 항목(데굴님 확정 필요)

①compound 증분 확정(0.15 vs 0.25 — 민감도 표 기준) ②exposure UNKNOWN 0.55
유지 여부(ablation상 상위 영향 없음) ③persistence 주도 진입(구조 코퍼스 상위
기여 3배)의 허용 여부·span 5 확정 ④capped=1 3건(단일 risk_id — CAR 계열)
개별 확인 ⑤ByContext 저작 여부(TRL 등) ⑥확정 후 shadow_scoring 49항목 스탬프
(reviewHashes에 scope 해시+config/semantics hash 병기).

## 18. R1-c2b 교정 차수(감수 32차) — 공식 modifier 전환·taxonomy·ByContext (2026-07-16)

데굴님 확정: **지속성·복합성·보호는 기본 위험을 보정해야지, 기본 위험보다 더 강한
독립 점수원으로 작동해서는 안 된다.** compound 0.25 기각·persistence additive
보류·protection 감점 재검토 반영.

1. **공식 modifier 전환**(RISK_SCORING_VERSION r1.0.4→**r1.1.0-shadow**):
   `raw = exposure × (occ×impact) × (1+persistence+compound) × (1−protection)`,
   structural = `(occ×impact) × (1+persistence) × (1−protection)`(exposure·
   compound 제외 유지). 성질: 비노출은 지속·복합으로 부활 불가 / persistence
   기여 상한 = base×1(fixture: 약한 원인 6개월 지속 < 강한 단기) / UNKNOWN
   가중이 전 양의 항에 일관 적용(§8) / protection 비례 완화.
2. **3대 문제 전면 해소(재측정 실증)**: ①persistence 주도 — 상위 10% 가중 기여
   base +0.217~0.328 주도, persistence항 +0.05~0.06(base의 ~1/4) ②protection
   음수 양산 — raw<0 0건(구 64.8%)·0 하강 0건 ③**CAR capped 3건 자연 해소 —
   전 모집단 capped=1 **0건**(persistence additive가 원인이었음 확증), raw p99
   0.364(구조 D군).
3. **compound**: 잠정 증분 0.25→**0.10**(기각 반영 — 보수 후보). 새 공식 민감도
   (기준 0.10): 0→top10 overlap 8/10·0.15→10/10·0.25→7/10 — 0.10~0.15 구간
   안정, compound 항이 persistence를 넘는 후보 0. 확정은 R1-c3 감수.
4. **role taxonomy audit**: 49항목 **40종**(병합 3건 적용·감수 질문 —
   hiring_delay+selection_delay+waitlist→result_wait_delay / compliance+
   financial_liability→liability_obligation(기존 family=liability와 일관)) ·
   singleton 32 · 공유 8 · 도메인 간 3종. shared-cause 쌍: same-role 0 ·
   different-role 68 · unresolved 1,873(episode-free). singleton 32의 개별
   심사(독립 현실 효과 여부)는 R1-c3 감수 대상.
5. **ByContext 저작·소비**: TRL = treatment_process→treatment_management /
   recovery_process→recovery_adjustment. 엔진이 매칭된 건강 context branch로
   role 해소(치료≠회복 fixture), lint(base role 필수=항상 해소·key enum 검사).
6. exposure ablation(새 공식): UNKNOWN 가중이 전 항에 곱해져 상위 민감도가
   상승(overlap 6~7/10 — 구 10/10) — UNKNOWN cohort 분리 측정은 R1-c3 계속.
   pairwise 3종·protection pairwise·span 5/8/12 비교 전부 PASS·고정.

게이트: pytest 2000·mypy 0(521)·baseline 지표 diff 0(사전 해시 메타만 재기록)·
manifest 일치(shadow_structure 49/49·shadow_scoring 0/49 유지). **R1-c3 감수
대상**: compound 증분(0.10 vs 0.15)·span(5 유지 여부 — 비교표)·singleton 32
심사·UNKNOWN 0.55(shadow 잠정 승인 유지)·shadow_scoring 49 스탬프.

## 19. R1-c3 차수(감수 33차) — 최종 확정·shadow_scoring 49/49 스탬프 (2026-07-16)

감수 33차 확정 반영: modifier 공식·span 5·compound 0.10·result_wait_delay 병합·
TRL ByContext·protection 공식 **승인** / liability_obligation 병합 **기각** /
compound 0.25 기각 유지.

1. **liability 분리**: compliance_obligation(준법 의무 — 기한·요건 이행 관리) /
   guarantee_or_contractual_liability(보증·계약상 금전 책임) — 같은 cause 병존
   시 compound 계산 가능해야 하는 다른 현실 효과. '3번째 병합' 공개: 별도 어휘가
   아니라 SEL_WAITLIST의 result_wait_delay 계열 흡수(승인된 병합에 포함).
2. **protection cap 0.70 하드 가드**: positive base+최대 보호 → rankable>0
   fixture(존재 삭제 금지·단조 감소·occ/imp/exp 불변), config hash 편입.
3. **additive 상한 회귀 golden**: 구 공식이면 상한(1.26)인 지속 조합이 modifier
   에선 0.52 — persistence 가중 변경 재발 방지 fixture.
4. **UNKNOWN 0.55 국소 민감도 — 승인 기준 전부 충족**: w 0.40/0.50/0.60/0.70
   비교 — 0.50 top25 overlap 100%·0.60 92%(기준 ≥85%) · threshold crossing 0 ·
   CONFIRMED 최고점 추월 UNKNOWN 0 · UNKNOWN-only cohort p50 0.125/p90 0.210.
   → **0.55 shadow 확정**.
5. **shared-cause different-role 연결쌍 감수 표**: 68쌍=unique 16조합 산출(고정본)
   — 최다 compliance↔dispute 13×(분리 복원의 정당성 실증: 의무 이행 부담과
   분쟁 위험은 같은 원인의 다른 결과·병존 compound 정당). 전 조합이 '같은
   원인이 만든 실제로 다른 결과' 유형 — different role 유지 판정(감수 확인 대상
   표는 고정본 §shared-cause).
6. **ByContext 자동 탐색**: branch 2+ 항목 3건 — TRL(저작됨)·ECS(existing_
   condition/current_symptom — 같은 '기존 불편 부담' 계열, base 단일 유지)·
   PWS(physical_workload/sleep_schedule_load — sleep branch는 확인 취급이 아니라
   노출 경로 없음, base 유지). 추가 저작 불요 판정(감수 확인).
7. **shadow_scoring 49/49 스탬프**: reviewScopes에 shadow_scoring 추가(R1),
   scope 해시 스탬프, reviewPendingScopes 해제. manifest에 **risk_scoring_
   version·scoring_config_hash·cause_semantics_hash 병기** — 공식·가중·registry
   변경 시 manifest diff→회귀 테스트 실패→재감수 신호(자동 강등 트리거).
   RISK_SCORING_VERSION **r1.1.1-shadow**.

manifest: shadow_structure 49/49 · **shadow_scoring 49/49**. 게이트: pytest
2002·mypy 0(521)·baseline 지표 diff 0(사전 해시 메타 재기록)·restamp 검증
불변 49. **다음: R2 착수**(episode 병합·risk budget·대표 선택 — 병합 키에
trigger_cause_atoms 교집합, cause 표 기반 포트폴리오 1회 계산).

## 20. R2 차수(감수 34차) manifest — episode 병합·대표·budget·portfolio·recovery
(데굴님 착수 기준 선행 고정, 2026-07-16)

**차수 성공 조건(데굴님 확정)**: 같은 현실 건은 도메인과 위험 항목이 달라도 하나의
episode로 묶고, 같은 원인은 여러 episode에 연결돼도 포트폴리오에서 한 번만
계산하며, 보여줄 위험이 부족할 때 budget을 채우기 위해 약한 위험을 만들지 않는다.

1. **3-identity 분리(병합 키 수정 — R0 자리표시 키 폐기)**: reality episode
   identity(명시 context episode_id + exposure target 서명 + stage·기간 호환) /
   cause identity(canonical cause_atom·lineage) / effect identity(normalized
   EffectRole). **risk_id·domain은 key에서 제외 — episode 구성원 속성**(주택
   계약 episode에 MOV·LEG·FIN 후보가 함께 묶여야 함).
2. **병합 규칙**: 명시 episode_id(전 축) 우선 — 같은 explicit id+stage 호환이면
   cause가 달라도 병합. 명시 id 부재 fallback은 보수적: 같은 exposure target
   서명+같거나 인접 기간+shared canonical cause+stage 호환+**동일 현실 건
   ownership 계약**(현 시점 잔여 계약=같은 riskFamily — 교차 통합 감수 키) 전부
   충족 시만. 동일성 입증 불가=병합 금지(fail-closed). cause 교집합은 identity가
   아니라 연결 근거(다른 episode+같은 cause=병합 금지·portfolio 1회).
3. **RiskEpisode 구조(§8 권장안)**: episode_id·target_signature·start/end·
   stages·member/representative/supporting/background ids·canonical_cause_ids·
   effect_roles·domains·exposure_status·structural/context confidence·
   recovery_window. 대표 선택 후에도 supporting·vulnerability·trajectory 역할
   보존(삭제 금지 — 출력 압축만).
4. **대표 자격**: context-exposable + rankable>0 + kind≠vulnerability + 비흡수.
   비교 순서: ①explicit primary ownership ②exposure 적격성 ③effect
   specificity ④rankable score ⑤structural confidence ⑥deterministic risk_id.
   점수가 primary owner를 밀어내지 못하고, 비노출 구체 후보가 노출 가능한 일반
   후보를 제거하지 못한다(R0.5 역전 방지 유지).
5. **risk budget**: hard_min=0(적격 없으면 0개 — 약한/BLOCKED 끌어올림 금지),
   soft_target(단일 도메인 1~2·overview 2~3), hard_max(2/3). 순서: episode
   중복 제거→같은 effect role 제거→shared cause 제거→budget→동점에서만 도메인
   다양성 soft tie-break(강제 다양성 금지 — 같은 도메인 3 episode 허용). 누락
   이유 기록.
6. **portfolio 합산**: 원천=unique canonical cause 표·unique persistent
   lineage·distinct resolved effect roles·unique reality episodes. 금지=후보
   rankable 합·episode별 occurrence 합·같은 cause persistence 반복·supporting/
   vulnerability 재가산. total 필요 시 unique cause 원천 포화 결합.
7. **recovery window**: 현재 점수와 완전 독립(별도 전망 — 점수·순위 불변
   fixture). 성립=주요 cause lineage 종료·약화+protection 강화+불리 stage 종료
   보수 판정. 출력=earliest_relief_window·stable_recovery_window·recovery_
   confidence·reasons. 단정 표현 금지(반드시 해결·완전 소멸·회복 운이라 현재
   위험 낮음).
8. **버전·감수**: env r0.5.12 유지, **RISK_SELECTION_VERSION=risk-select-
   r2.0.0-shadow** 신설, manifest에 selection_policy_hash 병기(병합 정책·stage
   호환·대표 순서·budget·portfolio dedup·recovery 정책). scope shadow_selection
   0/49 — 스탬프는 R2 측정·감수 후.
9. **필수 fixture(§13)**: 병합 4(같은 explicit episode+다른 risk_id·domain=1
   episode / 다른 episode+같은 cause=2 episode·portfolio 1회 / 같은 episode+
   다른 cause=1 episode·cause 2 / 명시 없음+같은 cause·다른 target=병합 금지),
   대표 2(비노출 구체 vs 노출 일반 — 일반 대표·구체 background / vulnerability
   고득점 대표 불가), budget 3(적격 0→0 / episode 후보 5→대표 1 / episode 4·
   max 3→상위 3+누락 기록), recovery 1(추가→현재 점수·순위 byte 불변).

### 20-1. R2-a 후속(감수 35차 확정 6건 — R2-b 착수 전) (2026-07-16)

핵심 위험(데굴님): 이름이 우연히 같은 local episode 병합 / 같은 원인·role 이유의
현실 episode 삭제 / 지평 끝 일시 비활성의 안정 회복 오판 — 전부 차단.

1. **축 namespace + reality alias 계약**: local episode id는 (축, id) 서명이라
   문자열 우연 일치로 병합 불가(fixture: mobility:case_1 ≠ legal:case_1). 교차
   도메인 병합은 컨텍스트 5종에 신설한 `reality_episode_id`(명시 alias)가 유일
   경로 — 엔진이 매칭 컨텍스트에서 후보로 복사(상충=None fail-closed). 병합
   우선순위: reality alias → 축 explicit → fallback. 같은 local id+상충 alias=
   분리(fixture).
2. **대표 정렬에 primary ownership 선두**: 자격 필터(exposable·rankable>0·
   비취약·비흡수)와 정렬(ownership→specificity→rankable→confidence→id) 분리.
   ownership proxy=자기 도메인 소유 축 episode 직접 매칭(_DOMAIN_AXIS_EPISODE —
   **잠정 매핑·감수 질문**, policy hash 포함). fixture: 점수·특이도 높은 비소유
   FIN 후보가 LEG 소유 후보를 밀어내지 못함.
3. **budget soft tie-break(hard dedup 폐지)**: 다른 현실 episode의 같은 effect
   role·shared cause는 제거 금지 — 적격≤hard_max면 중복이라도 전부 선택(시험
   결과 대기 2건 fixture: 둘 다 보존·portfolio 원인 1회), 초과 시 novelty(role
   0.02·cause 0.01·domain 0.005 — 동점 수준)만 greedy 우선도에 가산. 누락
   taxonomy: NO_EXPOSABLE_REPRESENTATIVE/BUDGET_HARD_MAX/LOWER_PRIORITY
   (redundancy는 사유 아님).
4. **fallback transitive over-merge 차단**: fallback 그룹은 (대상·원인·family)
   완전 일치만 — pairwise 연쇄 bridge 불가(fixture: A↔B·B↔C 부분 겹침 → 3분리).
5. **recovery right-censoring·quiet span·다중 cause**: earliest_relief=첫
   primary cause 완화 다음 기간(confidence 0.2 보수) / stable=모든 primary
   cause 종료+quiet 2 native 기간이 지평 안에 실재할 때만(0.4) / 지평 끝 일시
   비활성=stable 미산출+`right_censored_quiet_span` 기록 / 한 cause 지속=
   `other_primary_cause_ongoing`(earliest만). 점수·순위 불변 유지.
6. **episode confidence 팽창 방지**: 대표 기준 집계(구성원 합산 없음) —
   duplicate supporting 추가 fixture로 불변 고정.

RISK_SELECTION_VERSION r2.0.0→**r2.0.1-shadow**(policy hash 갱신 — 병합 우선
순위·ownership 매핑·soft budget·censoring 편입). fixture 10→**19종**. pytest
2021·mypy 0(523)·전 baseline 지표 불변(profile 컨텍스트 해시 메타만 재기록).
R2-b 측정 지표(§12)는 스크립트 설계에 반영 예정.

## 21. R1-T/R2-a2 차수(감수 36차) — 교운기 temporal modifier·R2-a 잔여 보완 (2026-07-16)

**교운기 계약(데굴님 확정)**: 교운기는 위험 후보를 만드는 원인이 아니라 이미 성립한
위험 구조의 시점 민감도를 높이는 modifier이며, 이벤트 엔진의 커널을 단일 SSOT로
공유하고, 후보 적격성·원인 수·persistence·episode identity에는 절대 개입하지 않는다.

1. **커널 SSOT**: `event_scoring.daewoon_transition_weight`(exp(-(d/365)^1.0)
   라플라스형 — 분포명 단정 대신 kernel로 지칭) 직접 import·MIN 0.05 게이트 공유
   (복제 0). 대칭·감쇠 fixture.
2. **transitionSensitivity 사전 필드**(해시 **v10** — shadow_scoring scope 편입):
   none/low/medium/high enum·**vulnerability=none lint 강제**. 49항목 잠정 저작
   (전환성=직업·주거·관계·계약/선발 결과 high — 감수 대상). 계수(0/0.25/0.6/1.0)·
   MAX_BONUS 0.5 잠정.
3. **공식**: `timed_base = base × (1 + weight×coef×MAX_BONUS)` — rankable·
   structural 모두 적용(exposure·(1+per+cmp)·(1−prot) 구조 유지). score_shadow에
   transition_weights(기간→커널값) 입력 — None=기존 결과 byte 불변. 후보
   transition_bonus 파생 필드(적격성·cause table 불개입).
4. **불변식 fixture 7종**: 커널 대칭·후보 전 필드 불변(bonus만)·base=0 부활
   차단·비노출 부활 차단·커널 다월≠persistence·민감도 none/vulnerability 0·
   (selection) 교운 보정 후 ownership 유지+recovery 비생성.
5. **overlay 실측**(C overlay·커널 3단): 교운일 평균 상승률 27.0%(top10 신규 4·
   capped=1 4) / ±1년 9.9%(신규 2·포화 0) / ±2년 3.6%(신규 1) — 감쇠 의도대로,
   포화는 교운일 중심 4건(감수 확인 대상). shadow_scoring 49/49 **R1-T 재스탬프**
   (RISK_SCORING_VERSION **r1.2.0-shadow**·config hash에 transition 편입).

**R2-a 잔여 보완 5건**: ①alias 상충=CONFLICT 상태 보존(reality_conflict 필드 —
fallback 재진입 금지·단독 episode·identity 품질 0) ②novelty **near-tie(ε=0.02)
전용 lexicographic**(숫자 가산 폐지 — 큰 점수차 역전 금지 fixture) ③earliest
relief=대표의 **최고 기여(최강 trigger) primary cause** 완화 기준(보조 원인 종료
로 미생성 fixture) ④episode context confidence=대표 required 축 충족도×identity
품질(reality 1.0/explicit 0.9/fallback 0.6/conflict 0.0 — 잠정) ⑤ownership
사전 계약(primaryOwnership axis·targetTypes·stages)은 R2-c 전 편입 예정 —
_DOMAIN_AXIS_EPISODE는 adapter(감수 질문 유지), proxy audit는 R2-b 측정 항목.
RISK_SELECTION_VERSION **r2.0.2-shadow**. fixture 총 29종(selection)+44종
(scoring). pytest 2031·mypy 0(523)·suppression baseline diff 0·manifest 일치.

**감수 대기**: transitionSensitivity 49항목 저작·계수/MAX_BONUS·교운일 포화 4건·
같은 reality alias+target 충돌 fixture(컨텍스트 수준 — 표현 불가 항목 기록).
다음: R2-b 전수 측정(기존 + A-T/B-T/C-T/D-T 교운 overlay + ownership audit).

## 22. 감수 37차 조건 차수 — scope 절차 교정·reality type·anchor-bucket·temporal 감수 재료 (2026-07-16)

**절차 교정(조건1 — 데굴님 지적)**: 잠정(미감수) temporal 계수·MAX_BONUS를
shadow_scoring 49/49로 재스탬프한 것은 "미확정 가중치를 reviewed로 스탬프 금지"
원칙 위반 — **shadow_temporal scope 신설**로 교정.

1. **shadow_temporal scope 분리(조건1)**: `_RISK_REVIEW_SCOPES`에 shadow_temporal
   추가, risk_scope_hash의 shadow_scoring 본문에서 transitionSensitivity **제거**
   (기 감수된 shadow_scoring 오염 방지) → 신설 shadow_temporal 본문으로 이동.
   49항목 reviewVersions.shadow_scoring="R1" 복원 + reviewPendingScopes=
   ["shadow_temporal"](0/49 — 계수·MAX_BONUS·저작 감수 후 스탬프).
   `transition_policy_hash()` 신설(커널 참조·계수·MAX_BONUS·MIN·공식 —
   scoring_config_hash에서 transition 블록 분리)·manifest 병기.
2. **reality_episode_type(조건5)**: 7종 enum(housing_contract/employment_selection/
   legal_proceeding/relationship/treatment_recovery/travel_mobility/financial_claim).
   컨텍스트 5종·RiskCandidate에 필드 추가. 같은 alias라도 ①type 2종 비호환
   ②enum 밖 값이면 CONFLICT(fail-closed — 오부여 alias의 오병합을 엔진 해석과
   build_episodes 병합 시점 이중 감지, 후보별 단독 conflict episode). type 한쪽
   미기재(None)는 상충 증거 아님(병합 유지). fixture 2종(병합 계층+엔진 전파).
3. **anchor-bucket near-tie(조건6)**: pairwise '차이≤ε' 비교는 비추이적이라 연쇄
   확장 가능 → ①최고 미배정 점수=anchor ②anchor 기준 ≤ε(0.02)만 bucket(소진까지
   anchor 고정 — 연쇄 편입 금지) ③bucket 내부만 novelty 순서(bucket 경계가 점수
   역전 불가를 강제) ④다음 anchor. NO_EXPOSABLE drop도 episode_key 정렬. fixture
   3종: 연쇄 확장 차단(A–B≤ε<A–C·B–C≤ε 배치)·bucket 내부 novelty 우선·**입력
   permutation 전수(episode×candidate 순서) byte-identical**.
4. **dominant cause 동률 relief(조건7)**: earliest relief의 기준 cause를 단일
   최강에서 **strength ≥ max−ε(0.02 잠정) 집합 전체**로 — 동률이면 집합의 마지막
   종료가 relief 기준(하나만 끝난 시점을 완화로 부르면 낙관 편향, fail-closed).
   fixture 2종(동률 지속=미산출·명확 최강=단독 기준). RISK_SELECTION_VERSION
   **r2.0.3-shadow**·selection_policy_hash 갱신.
5. **temporal 감수 재료(조건2·3·4 — survey 확장)**:
   - 조건2 교운일 capped=1 4건 개별: LEG_COMPLIANCE_OBLIGATION_PRESSURE 3기간
     (raw 1.071 — 무교운도 rank 1~3·bonus +0.125로 상한 기여 미미) +
     MOV_CONTRACT_SETBACK_RISK 2027-01(raw 1.008 — bonus +0.500, rank 11→4).
     top10 신규 4건 전부 MOV_CONTRACT_SETBACK_RISK(high·+0.500): rank 11→4·
     15→5·16→6·19→9.
   - 조건3 MAX_BONUS 민감도(교운일 w=1.0 최악점): 0.30=상승 16.2%·overlap 7/10·
     포화 3 / 0.40=21.6%·6/10·포화 3 / 0.50=27.0%·6/10·포화 4.
   - 조건4 transitionSensitivity 저작 audit: high 8·medium 10·low 26·none 5.
     high 전량 표(도메인 아닌 상태 전환성 기준 감수용 — CAR 3·LEG 1·MOV 2·
     REL 1·SEL 1)·medium 10종 목록.

**게이트**: pytest 2037(fixture selection 36종·+7)·ruff clean·mypy 0(523)·
suppression baseline diff 0(3412 — meta만 갱신)·profile baseline **값 byte
동일**(meta 해시만 갱신: dictionary v10 scope 재편·context 필드 추가)·manifest
일치·survey 재생성 byte-identical. 측정 고정본 갱신(RISK_SCORING_SURVEY_R1C1).

**감수 대기(shadow_temporal 0/49)**: 계수(0/0.25/0.6/1.0)·MAX_BONUS(0.30/0.40/
0.50 중 확정)·high 8종 저작 — 확정 후 스탬프. dominant ε=0.02·identity 품질
계수는 shadow_selection 감수 시 확정. 다음: R2-b 전수 측정 착수(승인 완료 —
기존 §12 지표 + A-T/B-T/C-T/D-T 교운 overlay + ownership proxy audit +
fallback under-merge).

## 23. 감수 38차 preflight + R2-b 전수 선별 측정 (2026-07-16)

**preflight 4건(데굴님 지시 — 후보 생성·R1 구조 불변)**:

1. **MOV_CONTRACT_SETBACK_RISK high→medium**: manifestation이 협의 차질·조건
   재협상·일정 재조정(전환 과정의 차질)이고 "계약 무산 단정"은 prohibited —
   상태 전환 확정이 아니므로 medium. 판정 근거를 사전 필드
   transitionSensitivityNote(해시 비대상 주석)로 명문화. sensitivity 분포
   high 7·medium 11·low 26·none 5.
2. **reality identity 3상태**: resolved(전원 type 보유·호환)=1.0 /
   partial(alias 동일·type 일부·전부 미기재 — **병합 유지, 완전 identity 아님**)
   =0.85 잠정 / conflict=0.0. RiskEpisode.reality_identity_status 필드 신설,
   context confidence 차등(resolved > explicit 0.9 > partial > fallback 0.6).
3. **선별 정렬=raw**: 대표·budget 정렬을 capped→raw_rankable_priority로 —
   capped는 표시·상한 진단 전용(cap 초과 후보의 1.0 동점 뭉침 금지). 자격
   게이트는 capped>0 유지(raw>0과 동치). fixture: raw 1.224 vs 1.148(capped
   둘 다 1.0)의 budget·대표 순서.
4. **ε 경계 정규화**: near-tie·dominant 차이값을 round(9) 후 ε 비교 —
   0.300−0.280=0.0200…18 같은 이진 오차가 경계(=0.020) 판정을 뒤집지 않음.
   경계 fixture(0.020=같은 bucket·0.021=다른 bucket). dominant strength는
   cause별 trigger evidence **max**(누적 가산 금지) 확인 주석화.
   RISK_SELECTION_VERSION **r2.0.4-shadow**·policy hash 갱신. fixture +3
   (selection 36종). 게이트: pytest 2040·mypy 0(524)·suppression diff 0·
   profile baseline 값 byte 동일(meta 해시만)·manifest 일치.

**R2-b 전수 선별 측정**(scripts/risk_selection_survey.py — 고정본
RISK_SELECTION_SURVEY_R2B.md, 재실행 byte-identical):

- **모집단**: 프로필 A/B/C/D + **E_reality_linked 신설**(스크립트 국소 —
  이동·계약 컨텍스트에 같은 reality alias 부여, 치료는 type 미기재) × 코퍼스
  10차트(year+month), 차트 단위 병합.
- **episode 형성**: A 735(전량 fallback)·B 715(explicit 16)·C 653(explicit
  29)·D 718(explicit 30)·E 701(**reality 13 — resolved 10·partial 3,
  다도메인 episode 6** — 교차 도메인 병합 실측 최초). 구성원 p50 1·p90 2.
- **대표·ownership**: 대표 보유 210~245/프로필 · ownership 대표=explicit 축
  매칭 수와 일치(A 0·B 16·C 29·D 30·E 13) — proxy 매핑 오적용 0.
- **budget**: 전 차트 hard_max 3 도달, 누락 taxonomy 정상(BUDGET_HARD_MAX
  10/프로필·LOWER_PRIORITY·NO_EXPOSABLE 분리). recovery earliest 135~169·
  stable 87~115·censored 39~50(우측 검열 작동).
- **fallback 분리 잔존 진단**: 같은 (대상·family) 3+ 분리 60~69 — cause
  상이·비인접의 fail-closed 분리(위반 아님, R2-c explicit id 저작·ownership
  사전 편입 후보군).
- **교운 overlay(episode 압축 이후 기준)**: matrix = sensitivity(적용안
  medium/비교안 MOV high) × MAX_BONUS(0.20/0.30), 교운일 w=1.0 최악점.
  - **episode top10 overlap**: 적용안 9~10/10 전 프로필(±1년 10/10). **비교안
    (high)은 C-T에서 MOV_CONTRACT_SETBACK 신규 진입으로 9/10** — medium 조정이
    감수 지적의 독점 진입을 정확히 제거.
  - candidate-level 신규 top10 진입: 적용안에서 단일 id 독점 없음(최대
    REL_PARTNER_READJUST 3~4·MOV_RELOCATION_PRESSURE 2~4 — 전부 high/medium
    항목). 민감도별 상승률 분리: high 20/30%·medium 12/18%·low 5/7.5%
    (MB 0.20/0.30).
  - **판정 5기준 × 4변형 × 5프로필: 전부 PASS** — episode top10 overlap ≥80%·
    신규 진입 단일 risk_id 미집중(≤2)·cap 동점이 선택을 결정하지 않음(raw
    정렬 — cap이면 동점이었을 쌍 0·자연 raw 동점은 D 13~15=동일 구조 시험
    episode 병존, novelty·key로 결정적 처리)·**ownership override 0**·
    low/none 항목 top10 신규 진입 0.
  - MAX_BONUS 0.20 vs 0.30: episode-level 판정 차이 없음(candidate 평균 상승
    9.4~11.0% vs 14.1~16.5%) — **확정은 데굴님 소관**(0.30도 episode 기준
    안정 — candidate 노이즈 억제를 우선하면 0.20).

**감수 대기**: shadow_temporal 0/49 스탬프 — sensitivity 저작(high 7 확정
여부)·MAX_BONUS(0.20/0.30 택일)·계수 형태 확정 후. partial 0.85·dominant
ε=0.02·_DOMAIN_AXIS_EPISODE는 shadow_selection 감수 시 확정. 다음: R2-c —
primaryOwnership 사전 계약 편입 + shadow_selection·shadow_temporal 감수·스탬프.

## 24. 감수 39차 — temporal 확정·shadow_temporal 49/49 스탬프·R2-c ownership 사전 편입 (2026-07-16)

**temporal 확정(데굴님)**: MAX_BONUS **0.20**(0.30 보조 비교 기록·0.40/0.50
기각 — "같은 episode 결과면 더 작은 modifier"), sensitivity 계수(0/0.25/0.6/
1.0) 유지, 커널·MIN 0.05·공식 최종 승인. RISK_SCORING_VERSION
**r1.2.1-shadow**.

1. **high 항목별 재판정(승인 조건 적용)**: 감수 기준(직접 상태 전환 결과=high /
   전환 과정의 조정·차질=medium)으로 7종 개별 판정 —
   **REL_PARTNER_READJUST high→medium**(manifestation이 "재조정 국면·차이
   표면화·대화 필요" = medium 기준 "관계 재조정 과정의 부담"에 정확히 해당,
   관계 상태의 명시적 변경 아님). 나머지 6종 high 확정: CAR_REASSIGNMENT
   (보직·근무지 변경)·CAR_EXIT_PRESSURE(역할 이탈·전환 — 일반 부담 아님)·
   CAR_HIRING_OUTCOME_SETBACK(결과 확정)·LEG_CONTRACT_TERMINATION(계약 종료)·
   MOV_RELOCATION_PRESSURE(거주 상태 전환 방향)·SEL_UNWANTED_PLACEMENT(배치
   결과). 최종 분포 **high 6·medium 12·low 26·none 5**. 항목별 근거를
   transitionSensitivityNote(비해시 주석)로 저작하고 **manifest에
   transition_sensitivity_distribution + high 근거표 병기**.
2. **shadow_temporal 49/49 스탬프**: reviewVersions.shadow_temporal="R1-T",
   scope 해시(transitionSensitivity 본문) 저장, reviewPendingScopes 해소.
   현 상태: structure 49 · scoring 49 · **temporal 49** · selection 0.
   sensitivity·계수·MAX_BONUS 변경 시 shadow_temporal만 자동 강등(scope 분리).
3. **R2-c primaryOwnership 사전 편입(proxy → SSOT)**: RiskPrimaryOwnership
   모델(axis: selection/mobility/health/legal/relationship/**none** +
   targetTypes/stages 선택 제약). 49항목 저작 — 도메인≠축: 채용 2종=selection,
   FIN 절차형 3종(보증·지급지연·정산분쟁)=legal, HLT 차량 안전=mobility(교차
   gate), 축 episode가 없는 역할·구조 기반 14종=none 명시. lint: reviewed
   전원 계약 존재·axis enum·targetTypes/stages applicable 부분집합·axis=none
   제약 금지. **selection scope 해시에 편입**(미스탬프 scope 확장 — 스키마
   v10 유지, 변경 시 shadow_selection만 자동 pending).
4. **ownership 소비 교체 + partial 가드**: 후보에 primary_ownership_axis
   전파(엔진), _ownership_rank = 계약 축의 **명시 local episode 직접 매칭**만
   성립 — reality alias(partial 포함)는 병합 근거일 뿐 ownership 증거 금지
   (함수가 reality_episode_id를 참조하지 않음 + fixture). (구) 도메인 proxy
   _DOMAIN_AXIS_EPISODE는 판정 미사용(audit 비교 전용 보존).
5. **ε 해시 명시화**: epsilon_boundary={digits 9, near_tie 0.02, dominant
   0.02, boundary "<="} 구조화 편입. RISK_SELECTION_VERSION **r2.1.0-shadow**.
6. **proxy audit(4분류·전 프로필)**: static — proxy_match 34 ·
   proxy_mismatch 1(HLT_MOBILITY_SAFETY_CAUTION: proxy는 health 축·계약은
   mobility 교차 소유 — 의도 반영) · ownership_not_applicable 14. behavioral —
   후보 rank 불일치 **0** · proxy였다면 대표가 달라졌을 episode **0**(proxy
   제거로 최종 대표 변화 없음 — 안전 교체 실증).
7. **재측정(고정본 갱신)**: 확정안(medium×0.20) 판정 5기준 전 프로필 PASS
   유지(episode top10 overlap 9~10/10·ownership override 0·low 신규 0·cap
   동점 0). scoring survey에 0.20 확정 표기(0.20/0.30/0.40/0.50 비교 보존).

**게이트**: pytest 2041·ruff clean·mypy 0(524)·suppression diff 0·profile
baseline 값 byte 동일(감수 36차 원본 대비 — meta 해시만 갱신)·manifest 일치·
survey 2종 재생성 byte-identical.

**감수 대기(shadow_selection 스탬프 전 확정 목록 — §10)**: primaryOwnership
계약 49건(본 차수 저작), near-tie·dominant ε=0.02, identity quality(1.0/0.9/
0.85/0.6/0.0), quiet span 2, relief confidence(0.2/0.4), 질문 유형별
hard_max·soft_target, partial≠ownership 계약(본 차수 구현).

## 25. 감수 40차 — temporal high 4 최종·recovery 계약 교정·budget 표·shadow_selection 49/49 (2026-07-16)

**감수 결정 반영**: shadow_selection 스탬프 전 필수 4건 완료 + 스탬프.

1. **CAR_EXIT_PRESSURE·MOV_RELOCATION_PRESSURE high→medium**(REL과 동일
   기준 적용 — 퇴직·이탈 '압박·고민'≠실제 퇴직 확정, 이동 '필요성·검토'≠실제
   이사 실행. PRESSURE 명칭·prohibited와 정합). 근거 note 저작(실제 전환
   항목(CAR_EXIT_TRANSITION 등) 신설 시에만 high 재론 명시). **최종 분포
   high 4·medium 14·low 26·none 5** — manifest 근거표는 high 4종만 잔존
   (강등 3종 근거는 사전 note+본 고정본에 보존: REL_PARTNER_READJUST·
   CAR_EXIT_PRESSURE·MOV_RELOCATION_PRESSURE = 전환 '과정'의 부담·조정).
   shadow_temporal 2종 해시 재계산·R1-T2 재스탬프(47종 R1-T 유지) — 49/49
   유지. RISK_SCORING_VERSION **r1.2.2-shadow**. **delta survey**: candidate
   평균 상승률 9.4→8.3%(교운일·MB 0.20), 강등 2종이 candidate top10 신규
   진입에서 소멸, episode 판정 5기준 전 프로필 PASS 유지.
2. **recovery confidence = cap × episode.context_confidence**(고정값 기각
   반영): earliest cap 0.20 · stable cap 0.40 — fallback(0.6)·partial(0.85)
   episode가 resolved와 같은 회복 확신을 받는 과대 표시 제거. right-censored
   는 stable 자체 미생성 유지. fixture: resolved vs fallback 동일 구조에서
   confidence 차등 검증.
3. **quiet span 월 단위 계약**: stable은 **month-native episode만** 산출
   (quiet 2=2개월), quiet 계수도 월 라벨 지평만. 비월 episode는 earliest만
   + `stable_month_native_only` 기록. **효과(재측정 — 프로필별 명시,
   감수 41차 표기 정정)**: stable 산출 건수 A 95→6 · B 100→6 · C 92→7 ·
   D 115→6 · E 87→6(비월 분류 stable_month_native_only A 73·B 85·C 85·
   D 95·E 71) — 연 단위 episode의 '2기간=2년 quiet' 오해석 전량 차단,
   기존 stable 대부분이 연 단위였음이 드러남. fixture: 연 단위 episode
   stable 미산출.
4. **질문 유형별 budget 표 고정**(권장 초기 정책 채택): specific_event
   1/2 · single_domain_period 2/2 · period_overview 3/3 ·
   multi_episode_compare 3/4 · episode_followup 1/2(soft/hard). hard_min 0
   공통·soft_target=최소 출력 아님(적격 부족 시 미달 허용 fixture)·미상
   유형 fail-closed 오류. budget_for() 헬퍼 + policy hash 편입.
5. **axis=none 불변식 fixture**: ownership 미적용 항목도 exposable·rankable
   이면 대표·선택 가능(우선권 가산만 부재) — 같은 episode에 owner 후보가
   있으면 owner 우선.
6. **shadow_selection 49/49 스탬프(R2-c)**: scope 명칭 shadow_selection
   신설(본문=selection scope: riskFamily·relatedDomains·crossDomainEffects·
   specificityRank·absorbedRoleHint·**primaryOwnership**). 확정값: ownership
   계약 49건·near-tie/dominant ε=0.02(각각 별도 필드)·identity quality
   (1.0/0.9/0.85/0.6/0.0 — resolved=type 완비·호환 필수)·quiet span 2(월)·
   relief confidence cap(0.2/0.4)·budget 표. RISK_SELECTION_VERSION
   **r2.2.0-shadow**.

**최종 상태**: shadow_structure 49 · shadow_scoring 49 · shadow_temporal 49
· **shadow_selection 49** (RISK_ENGINE_MODE 기본 off — 노출 승인 아님).

**게이트**: pytest 2045·ruff clean·mypy 0(524)·suppression diff 0·profile
baseline 값 byte 동일(meta만)·manifest 일치·survey 2종 byte-identical.

**다음**: R3(노출 계층 — warning 우선 서술 계약·risk_level 밴드·R2 선별
결과의 LLM 입력 직렬화·prohibited/allowed claim 강제·partial identity 단정
금지 표현 계약). recovery stable의 연 단위 정책(quietSpanByLayer)은 실사용
지평 설계 후 별도 감수.

## 26. R3 차수(감수 41차 착수 승인) manifest — 노출 계층 선행 고정 (2026-07-16)

**핵심 원칙(데굴님)**: 위험 수준은 점수를 다시 계산하는 계층이 아니라, **이미
감수된 episode를 현실 확인 수준과 근거 독립성에 맞는 문장 강도로 변환하는
계층**이다. R3는 R1 점수·R2 선택 집합을 절대 변경하지 않는다.

착수 전 고정 8건(감수 41차 지시):

1. **numeric band ↔ presentation level 분리**: numeric_band=대표 raw 점수의
   잠정 구간(밴드 경계는 shadow_presentation 감수 대상) /
   presentation_level=numeric_band에 exposure policy·kind·독립 원인·identity
   품질·context confidence 게이트를 적용한 표현 단계. level 산출은 R1
   score·R2 selection에 역영향 금지(byte 불변 fixture).
2. **level 상한 매트릭스**: confirmed_required+UNKNOWN=NONE ·
   DENIED/NOT_APPLICABLE/CONFLICT=NONE · incident_risk+UNKNOWN=WATCH 이하 ·
   pressure+허용 UNKNOWN=WARNING 이하 · vulnerability=ADVISORY 이하 ·
   CONFIRMED=밴드+추가 조건. 내부 enum NONE/ADVISORY/WATCH/WARNING/CRITICAL,
   사용자 표시명 완화(critical→'높은 주의').
3. **critical gate — '독립 2계층' 폐기, 독립 canonical cause ≥ 2**: 같은
   cause의 대운·세운 반복=원인 1개(layer corroboration은 confidence 소관).
   critical = numeric critical + CONFIRMED + 독립 canonical cause ≥2 +
   대표 비취약 + context conflict 없음 + context confidence 기준 +
   **identity resolved/explicit**(partial·fallback은 교차 도메인 결합 근거의
   critical 금지).
4. **R2 불변식**: R3 산출 전후 selected episode ids·대표·budget 누락 기록
   byte-identical. R3는 episode 추가·삭제·재선택 금지, warning-first는 R2
   선택 집합 안의 **stable sort**(bucket: CRITICAL·WARNING→WATCH→ADVISORY,
   bucket 내 R2 순서 유지). 경고 0건이어도 억지 경고 금지 + '특별한 위험
   없음' 단정도 금지.
5. **episode level 원천 = 대표 raw**: 구성원 점수 합산·supporting 개수
   승격 금지. 추가 반영은 R1 기 감수 정보만(unique 독립 cause·resolved
   distinct effect role·confirmed exposure).
6. **identity phrase mode 4종**: confirmed_same_episode(resolved) /
   explicit_local_episode(explicit) / possibly_related(partial·fallback) /
   separate_due_to_conflict(conflict). partial을 하나의 확정 현실 사건으로
   서술 금지(qualifier 필수).
7. **claim policy = 기계 판정 payload**: episode별 allowed_claim_codes ·
   prohibited_claim_codes(전역+항목 결합) · required_qualifiers 직렬화 —
   프롬프트 문구가 아니라 코드. recovery 표현 계약(단정 금지·confidence
   숫자/퍼센트 비노출 — band만). raw 소수값·내부 risk_id·cause atom 원문·
   manifest hash는 LLM 비노출(점수는 scoreBand: low/moderate/elevated/high).
8. **token guard 압축 순서**: P0(전역 claim guard·대표 요약·level·exposure/
   identity qualifier) → P1(주요 cause 설명·claim codes·warning 세부) →
   P2(supporting role·recovery window) → P3(진단). prohibited claim·partial/
   UNKNOWN qualifier·warning 대표 요약은 절대 우선 제거 금지. 선택된
   episode의 조용한 삭제 금지(불가피 시 compact 표현).

**모드 계약**: R3 초기 = SHADOW(payload 계산·검증만 — 기존 LLM prompt에
비주입·주입 후 '사용 금지' 지시 방식 불허). EXPOSE는 감수된 payload만.

**감수 표면**: scope **shadow_presentation 0/49** 신설(항목 본문=
manifestations·claim 정책·claimCeiling·exposurePolicy),
RISK_PRESENTATION_VERSION=**risk-present-r3.0.0-shadow**,
presentation_policy_hash(밴드 경계·상한 매트릭스·critical gate·정렬·phrase
정책·claim code 정책·recovery 문구 정책·token 예산/압축 순서·점수/confidence
노출 정책) manifest 병기.

**필수 fixture(§19)**: level 5종(같은 점수 CONFIRMED>UNKNOWN>비노출 ·
UNKNOWN incident≤WATCH · vulnerability≤ADVISORY · 층 반복≠독립 2원인 ·
CONFIRMED+독립 2원인+critical 밴드=critical 가능) · R2 불변 byte 3종 ·
partial qualifier 필수 · recovery 추가=level 불변 · token guard 보존 ·
SHADOW=기존 LLM 입력 byte 불변.

### 26-1. R3-a 구현 결과 (2026-07-16 — shadow 전용·프롬프트 미배선)

`risk_presentation.py` 신설(순수 함수 — 사전·LLM 미접근, 표현 payload만):

- **numeric band / presentation level 분리**: 밴드 경계 잠정(critical 0.40·
  warning 0.25·watch 0.12·advisory >0 — C overlay 분포 기반, 감수 대상).
  level = 밴드 + 상한 매트릭스(§26-2 그대로) — R1/R2에 역영향 없음(순수).
- **critical gate**: CONFIRMED + **독립 canonical cause ≥2**(atom 유일성 —
  다층 반복=1, fixture) + 비취약 + conflict 없음 + context confidence ≥0.5
  (잠정) + identity resolved/explicit(partial·fallback 금지) — 미충족 시
  warning 하향.
- **warning-first**: bucket(critical·warning→watch→advisory→none) 사이만
  stable sort, bucket 내 R2 순서 유지. NONE level도 payload 보존(조용한
  삭제 금지 — 비노출 사유 추적).
- **identity phrase mode 4종** + required qualifiers(conditional_exposure/
  possibly_related/non_assertive_recovery — P0 절대 보존).
- **claim payload**: 전역 prohibited 7코드+allowed 4코드, 항목
  prohibitedClaims·allowedClaimScope·manifestation 결합(호출부가 사전 공급).
  raw 소수값·내부 risk_id·cause atom·hash 비노출 — scoreBand(low/moderate/
  elevated/high)·confidenceBand(limited/moderate/supported)만.
- **token guard**: P0(level·라벨·대표 요약·domains·exposure·phrase mode·
  qualifier·prohibited) → P1(allowed·cause 수·scoreBand·confidenceBand) →
  P2(effect role·supporting 수·recovery window·recoveryConfidenceBand) →
  P3(진단). 예산 부족 시 P3→P2→P1 전 episode 일괄 탈락 — P0는 예산 초과여도
  보존, episode 삭제 없음(fixture: 예산 10자에서도 전 episode·prohibited·
  qualifier 잔존).
- **SHADOW 구조 보장**: 모듈이 어떤 프롬프트 빌더·엔진 경로에도 import되지
  않음을 fixture가 grep으로 강제(주입 후 '사용 금지' 지시 방식 원천 차단).
- **감수 표면**: RISK_PRESENTATION_VERSION=risk-present-r3.0.0-shadow ·
  presentation_policy_hash(밴드·매트릭스·gate·정렬·phrase·claim·recovery
  문구·token tier·노출 정책) manifest 병기 · scope **shadow_presentation
  0/49** 신설(본문=manifestations·claim 정책·claimCeiling·exposurePolicy).

fixture 11종(test_risk_presentation_r3.py — §19 전 항목): level 5종(같은
점수 CONFIRMED>UNKNOWN>비노출·UNKNOWN incident≤watch·pressure≤warning·
confirmed_required+UNKNOWN=none·vulnerability≤advisory·층 반복≠독립 2원인·
critical gate 4분기) · R2 불변(선택·대표·누락 byte + 입력 episode model_dump
불변) · warning-first stable · recovery 추가=level 불변 · partial qualifier
필수 · token guard 극단 예산 · SHADOW 미배선. **게이트**: pytest 2056·ruff
clean·mypy 0(526)·suppression diff 0·profile baseline exact·manifest 일치.

**감수 대기**: 밴드 경계(0.40/0.25/0.12)·critical context confidence 하한
(0.5)·confidence band 경계(0.3/0.6)·claim 코드 어휘·사용자 표시명 — R3-b
전수 측정(프로필별 level 분포·cap 강등 사유·critical 발생률·token 압축
실측) 후 shadow_presentation 스탬프.

### 26-2. R3-a preflight(감수 42차 6건) + R3-b 전수 측정 (2026-07-16)

**preflight 6건(스탬프 전 완료 조건)**:

1. **항목 ceiling 실적용(조건1)**: final level = min(전역 상한, item
   claimCeiling, exposurePolicy의 UNKNOWN ceiling). 사전 어휘 정규화
   fail-closed(`conditional_warning`→warning — 조건성은 qualifier 소관,
   미등록 값 오류). fixture: 같은 점수·exposure에서 ceiling만
   warning→advisory 변경 시 level만 하향·R1/R2 불변, ceiling "none"=
   비노출+CLAIM_CEILING_NONE.
2. **critical_eligible_cause_ids 분리(조건2)**: episode 전체 원인이 아니라
   대표 직접 지지 CAUSE + 독립 exposable primary effect(대표와 다른 role의
   비흡수·비취약·노출 가능 구성원)의 CAUSE만 — vulnerability·absorbed
   supporting·비노출·partial 교차 연결 제외. fixture 3종(대표1+supporting1
   =1 / 대표1+독립 effect1=2 / partial=대표만).
3. **audit/LLM payload 분리(조건3 — NONE의 LLM 보존 기각 반영)**:
   presentation_records(전 episode·NONE 포함·omission reason 4종·강등 사유
   primary/all·진단)와 llm_risk_episodes(ADVISORY 이상만·진단 없음) 분리.
   fixture: 3선택+1 NONE → records 3·llm 2·사유 보존.
4. **claim 충돌·미등록(조건4)**: prohibited always wins(effective allowed
   에서 제거), 미등록 코드 fail-closed 오류. 항목 prohibitedClaims 원문은
   감수된 짧은 지침으로 병기(런타임 강제는 코드).
5. **token guard 재설계(조건5)**: 전역 7+4 코드는 payload 최상단 1회
   (episode 반복 제거), token 추정(ceil(chars/3) 잠정), P2→P1→P0 →
   **P0_COMPACT 고정 축약**(level·domains·role 1·qualifier·항목 금지 코드
   + compressionMode/tokenBudgetOverflow 표시) — episode 삭제·qualifier/
   prohibited 제거는 어떤 단계에도 없음.
6. **OFF vs SHADOW 최종 LLM 입력 byte-identical(조건6)**: grep(미배선)은
   보조 — 실제 `serialize_candidate_v2` 직렬화 결과 byte 비교 + SHADOW
   presentation payload 생성 후에도 불변(통합 fixture, 기준 차트).
   numeric band 입력=대표 **capped**(조건 §2 — R2 정렬 raw와 분리) 계약
   해시·fixture 포함. RISK_PRESENTATION_VERSION **r3.0.1-shadow**.

**R3-b 전수 측정**(scripts/risk_presentation_survey.py — 고정본
RISK_PRESENTATION_SURVEY_R3B.md, byte-identical):

- **level 분포(선택 후)**: A watch 21·advisory 9 / B warning 4·watch 21·
  advisory 5 / C warning 14·watch 12·advisory 4 / D warning 11·watch 13·
  advisory 6 / E warning 7·watch 17·advisory 6 — **critical 전 프로필
  0건**(정상 — 개수를 만들기 위한 경계 하향 없음), none 0(budget 선택
  후보는 전부 노출 가능 상태였음), 전체 episode 기준 none 428~520은 대표
  없는 잠재 구조(선택 전 단계).
- **강등 사유(3층)**: unique 8~17/프로필, primary=EXPOSURE_POLICY_CEILING
  (5~10)·ITEM_CLAIM_CEILING(1~8)·INCIDENT_UNKNOWN_CAP(1~3) — 항목 ceiling이
  실제로 작동(조건1 실증).
- **claim 검증**: partial qualifier 누락 0 · 전역 prohibited 상존 ·
  same_episode_certainty/recovery_guarantee 전역 금지 유지.
- **token guard 실측**: budget 256=전 차트 P0_COMPACT+overflow(최소 표현
  p50 329·max 344 tokens — 256은 R2 hard_max 3 기준 부족), 512=P0_COMPACT
  (overflow 0), 1024=P1~P2, 2048=P2(full). episode 보존 30/30 전 구간.
  전역 dedup 절감 ≈2,093 tokens(반복 대비, 프로필 C 10차트 합).
- **경계 국소 민감도(C)**: watch 0.10/0.12/0.15 — 분포 불변(경계 부근 후보
  없음), warning 0.22/0.25/0.28 — 16/14/12로 완만, critical 0.35/0.40/
  0.45·conf 0.50/0.65/0.75 — 전부 불변(critical 후보 자체가 없어 하한
  변별 불가 — **확정 판단은 critical 발생 코퍼스 확보 후**가 정직).

**게이트**: pytest 2062(fixture presentation 16종+통합 1종)·ruff clean·
mypy 0(527)·suppression diff 0·profile baseline exact·manifest 일치.

**감수 대기(shadow_presentation 스탬프 전)**: 밴드 경계(0.40/0.25/0.12 —
warning 축만 실질 변별)·critical conf 하한(현 코퍼스 변별 불가 — 보수적으로
높은 값 권장)·token budget 기본값(512=compact/1024=full 경계)·표시명 golden
문장·estimator(ceil/3) — 데굴님 확정 후 스탬프.

### 26-3. 감수 43차 확정 반영 + shadow_presentation 49/49 스탬프 (2026-07-16)

**확정값(데굴님)**: warning 0.25 **확정** · watch 0.12/critical 0.40
**shadow 확정**(critical은 코퍼스 양성 0 — 실분포 검증 pending) ·
critical context confidence **0.75 확정**(보수 정책값 — CRITICAL_POLICY_
VALIDATION={synthetic passed·corpus 0·empirical pending·EXPOSE 전 golden
corpus 또는 critical→warning 하향 게이트 필요}를 policy hash에 기록) ·
token budget **기본 1024·안전 하한 512·256=EXPOSE 미지원** · 표시명 확정
(참고 신호/관찰 필요/주의 필요/**우선 점검 필요**).

**스탬프 전 수정 2건**:

1. **estimator 교체(ceil(chars/3) 기각)**: 1순위=모델 tokenizer adapter
   주입(counter 파라미터 — EXPOSE 배선 시 provider token-count 연결),
   fallback=보수적 다국어(ascii 4:1 + **비ascii 1:1** × 1.10 + wrapper 8)
   — 한국어에 /3 적용 금지·과소 추정 불허. fixture: 한국어 600자 ≥ 600
   토큰(구 추정 200의 과소 차단).
2. **token fail-closed**: budget < 512 또는 P0_COMPACT조차 초과 →
   **riskEpisodes=[] + exposureSuppressedReason=TOKEN_BUDGET_INSUFFICIENT**
   (감사 기록 유지) — tokenBudgetOverflow 상태로 주입하는 경로 자체를 제거.
   fixture 4분기(256=비주입 / 512=compact 주입 / 충분=full / episode 다수
   =512여도 비주입).

**재측정(고정본 갱신 — 보수 estimator 기준)**: 256=전 차트 fail-closed
비주입(0/30) · 512=P0_COMPACT 주입 30/30(최소 주입 표현 p50 272·max 285
tokens) · 1024=P1 6·P2 4 · 2048=full — **기본 1024가 P1~P2 유지 경계임을
재확인**. 단위 라벨 명확화(§3 지적): 분포=episode 건수·10차트 합산, 민감도
=선택 후 C 프로필 합산(warning_episode_count).

**shadow_presentation 49/49 스탬프(R3-b)** — 본문=manifestations·claim
정책·claimCeiling·exposurePolicy. RISK_PRESENTATION_VERSION
**r3.1.0-shadow**. 최종 상태:

    shadow_structure     49/49
    shadow_scoring       49/49
    shadow_temporal      49/49
    shadow_selection     49/49
    shadow_presentation  49/49  (RISK_ENGINE_MODE 기본 off — 노출 승인 아님)

**게이트**: pytest 2064(presentation fixture 18종)·ruff clean·mypy 0(527)·
suppression diff 0·profile baseline 값 불변·manifest 일치·survey
byte-identical.

**다음(EXPOSE 게이트 설계 — presentation 스탬프 후 착수 승인)**: 질문
유형별 주입 조건·critical→warning 하향 게이트(golden corpus 확보 전)·모델
tokenizer adapter 배선·R5(질문 파이프라인) 연동 지점 — manifest 선행 고정
후 진행.

## 27. R4 차수(감수 44차 착수 승인) manifest — EXPOSE 게이트 선행 고정 (2026-07-16)

**핵심 원칙(데굴님)**: 위험 payload 자체가 안전하게 만들어졌더라도, 실제
모델·질문·프롬프트의 남은 토큰과 감수 상태를 모두 확인하기 전에는 절대
주입하지 않는다.

착수 전 고정 8건(감수 44차 지시):

1. **tokenizer 필수**: tokenCountMode 3분류(PROVIDER_EXACT/MODEL_TOKENIZER/
   HEURISTIC_FALLBACK). heuristic은 SHADOW 측정 전용 — **EXPOSE 주입 금지**
   (adapter 부재 시 exposureSuppressedReason=TOKENIZER_UNAVAILABLE
   fail-closed). fallback을 상한으로 부풀리는 대신 정확한 adapter를 필수
   조건으로 둔다.
2. **최종 prompt 전체 headroom 기준**: available_risk_tokens =
   model_context_limit − base_prompt − user_input − existing_context −
   response_reserve − safety_headroom. effective_risk_budget =
   min(질문 유형 token budget, DEFAULT 1024, available). <512 = 비주입 —
   위험 payload가 기존 본문·용신·사건 근거를 밀어내지 않는다.
3. **R2 episode budget ≠ R3 token budget**: episode_budget_for(개수)와
   exposure_token_budget_for(직렬화 길이) 분리. 초기 token 정책:
   specific_event 768 · single_domain_period 1024 · period_overview 1024 ·
   multi_episode_compare 1024 · episode_followup 768(항상 headroom과 min).
4. **computed vs exposed level 분리**: computedPresentationLevel(감사 보존)
   과 exposedPresentationLevel(LLM 전달) — critical은 양성 코퍼스 확보 전
   **warning으로 하향**(item-level exposureDowngradeReason=
   CRITICAL_EMPIRICAL_VALIDATION_PENDING — payload 전체 차단 사유 아님).
   critical_validation_state는 presentation policy hash에서 **분리**(실증
   상태 변화가 49항목 shadow_presentation 감수를 강등하지 않음 — EXPOSE
   게이트 감수 상태만 변경).
5. **단일 fail-closed 게이트**: evaluate_risk_exposure_gate — mode·질문
   allowlist·temporal scope(과거 회고=비주입)·risk intent·전 scope
   reviewed·manifest/policy hash 일치·tokenizer·effective budget≥512·
   비어 있지 않은 llmRiskEpisodes·claim lint·직렬화 성공 전부 통과 시만
   주입. reason codes: MODE_NOT_EXPOSE/QUESTION_TYPE_NOT_ALLOWED/
   SCOPE_NOT_REVIEWED/POLICY_HASH_MISMATCH/TOKENIZER_UNAVAILABLE/
   TOKEN_BUDGET_INSUFFICIENT/NO_EXPOSABLE_EPISODE/CLAIM_POLICY_ERROR/
   SERIALIZATION_ERROR(+item-level CRITICAL_EMPIRICAL_VALIDATION_PENDING).
6. **질문 컨텍스트 조건**: questionType 단독이 아니라 temporalScope(과거
   회고 제외)·targetDomains·targetEpisodeIds·riskIntentAllowed 병합 판정.
   미등록·불명확 유형은 fail-closed 비주입.
7. **전역 pipeline scope**: EXPOSE는 항목 49건 scope가 아니라 전역 계약 —
   manifest에 expose_pipeline{reviewed:false, expose_policy_hash} 병기.
   RISK_EXPOSURE_VERSION=**risk-expose-r4.0.0-gated**.
8. **canary rollout**: 모드 4단(OFF/SHADOW/**EXPOSE_CANARY**/EXPOSE) —
   canary는 allowlist 계정·감수 질문 유형·critical 강제 하향·adapter 지원
   모델·충분한 headroom에만. 관측값: attempt/injected/suppressed(사유별)/
   compression 분포/estimate vs actual/level 분포/critical downgraded/
   claim violation.

**주입 위치 계약(R5 연동)**: R3가 FULL/P2/P1/P0/P0_COMPACT/SUPPRESSED 중
하나를 **완성된 단위로** 선택해 prompt builder에 전달 — 일반 context
reducer가 위험 payload 필드를 임의 삭제하는 경로 금지. risk payload가
suppressed면 모델이 위험 내용을 임의 보충하지 않도록 전역 계약 유지.
warning-first는 서술 순서 규칙(신규 위험 생성 아님).

### 27-1. R4-a 구현 결과 (2026-07-16 — gated·프롬프트 미배선)

`risk_exposure.py` 신설(순수 — 파일·프롬프트 미접근, 단일 fail-closed 게이트):

- **tokenCountMode 3분류** + EXPOSE 허용은 PROVIDER_EXACT/MODEL_TOKENIZER만
  — heuristic fallback 또는 adapter 부재=TOKENIZER_UNAVAILABLE 비주입.
- **headroom 기반 예산**: available_risk_tokens(limit−base−user−context−
  reserve−safety 256) → effective=min(질문 유형 budget, DEFAULT 1024,
  available), <512 비주입. **R2 episode budget과 분리**:
  exposure_token_budget_for(specific 768·single_domain 1024·overview 1024·
  compare 1024·followup 768, 미등록 fail-closed).
- **computed/exposed level 분리**: apply_exposure_levels — critical은 실증
  pending 동안 exposed=warning(item-level CRITICAL_EMPIRICAL_VALIDATION_
  PENDING), 감사 record에 computed 보존, LLM 직렬화에는 exposed만(computed·
  하향 사유 필드 제거). critical_validation_state를 presentation policy
  hash에서 **분리**(상태 변화≠49항목 감수 강등 — manifest expose_pipeline에
  병기).
- **evaluate_risk_exposure_gate**: mode(OFF/SHADOW=MODE_NOT_EXPOSE·
  EXPOSE_CANARY=allowlist 필수) → 질문 게이트(allowlist+temporal past_only
  비주입+risk_intent) → scope reviewed → policy hash 일치 → tokenizer →
  effective budget≥512 → 비어 있지 않은 episodes → critical 하향 → 직렬화
  (claim lint ValueError=CLAIM_POLICY_ERROR·기타=SERIALIZATION_ERROR·
  suppressed 문서=TOKEN_BUDGET_INSUFFICIENT). 전 조건 통과 시만 inject=true
  + 관측값(attempted/injected/reason/effective_budget/compression/episode
  수/critical_downgraded).
- **모드 4단**: RiskEngineMode에 EXPOSE_CANARY 추가(OFF 기본 불변).
- **감수 표면**: RISK_EXPOSURE_VERSION=risk-expose-r4.0.0-gated ·
  expose_policy_hash(토큰 모드·예산 공식·질문 게이트·level 분리·reason
  codes·모드·주입 위치 계약·관측값) · manifest expose_pipeline
  {reviewed:false, hash, critical_validation_state} — **전역 pipeline
  scope**(항목 49건 아님).

fixture 10종(test_risk_exposure_r4.py — §13 전 항목): tokenizer 부재/
heuristic 비주입 · adapter actual 계수 우선(과대 계수→비주입) · 전체 prompt
headroom<512 비주입(payload 단독 크기 아님) · computed CRITICAL→exposed
WARNING+감사 보존+원본 불변 · scope/hash 불일치 비주입 · OFF/SHADOW/CANARY
게이트 · past_only/intent/미등록 유형 비주입 · episode/token budget 분리 ·
P0_COMPACT 초과=전체 비주입 · 주입 직렬화에 exposed만+관측값.

**게이트**: pytest 2074·ruff clean·mypy 0(529)·suppression diff 0·profile
baseline exact·manifest 일치. RISK_ENGINE_MODE 기본 off 불변(주입 배선은
R5 파이프라인 차수 — 게이트 함수만 존재, 호출 경로 없음).

**감수 대기**: expose_pipeline reviewed:false — 배선(R5 질문 파이프라인
주입 지점·tokenizer adapter 실물·canary allowlist 정책) 감수 후 EXPOSE_
CANARY 개시. safety headroom 256·질문 유형 token 표는 잠정(canary 실측 후
확정).

## 28. R5 차수(감수 45차 착수 승인) manifest — 배선·출력 감사 선행 고정 (2026-07-16)

**핵심 원칙(데굴님)**: 감수된 위험 block을 안전하게 만들었다는 사실만으로는
충분하지 않다 — 실제 모델이 받은 **최종 프롬프트**와 실제 생성한 **최종
문장**까지 감수 계약을 지켜야 노출을 허용할 수 있다.

**슬라이스**: R5-a=게이트 확장·RiskPromptBlock·answer claim audit(채팅 배선
전 계층 — 본 차수) / R5-b=chat_service 실배선·tokenizer adapter 실물·canary
allowlist 정책(다음 차수). EXPOSE_CANARY 개시는 R5-b 통합 fixture +
expose_pipeline reviewed=true 후.

EXPOSE_CANARY 개시 전 필수 4건(감수 45차):

1. **최종 prompt 2차 계수**: 사전 headroom 통과 후, 위험 block을 포함해
   조립된 최종 prompt를 **동일 tokenizer로 재계수** — 초과 시 더 작은
   compression(FULL→P2→P1→P0→P0_COMPACT) 재시도, 그래도 초과면
   FINAL_PROMPT_TOKEN_OVERFLOW 비주입. 사전 계산만으로 주입 금지.
2. **tokenizer-모델 일치**: counter.model_id == llm_config resolved model —
   불일치=TOKENIZER_MODEL_MISMATCH 비주입. alias 해소 후 counter 선택,
   fallback 라우팅 시 재계수.
3. **suppressed guard 계약**: 구조화 riskEpisodes 부재 시 일반 사건 후보를
   위험·경고·사고·손실 주장으로 확대 해석 금지(계약 검토 권고 수준은 유지 —
   과잉 차단 금지). guard block은 **EXPOSE 계열 모드에만** 추가(OFF/SHADOW
   prompt byte 불변 유지).
4. **answer claim audit(사후 검사)**: 규칙 기반 — 확정 발생·사고/질병/법적
   결과 단정·금전 손실 확정·partial 동일 건 단정·recovery 보장·exposed
   level 초과 표현. 위반 시 사용자 전달 전 재작성/위험 단락 제거/전체
   fail-closed(위반 기록만 남기고 그대로 노출 금지 — prompt 지시만으로
   claim 강제 완료로 판단 금지).

게이트 보강(감수 45차):
- kill switch(RISK_EXPOSURE_KILL_SWITCH — 게이트 최앞, mode 무관 비주입).
- EXPOSE_PIPELINE_NOT_REVIEWED reason 분리(현 reviewed=false → 모든 조건
  충족이어도 비주입 fixture).
- suppression reason: primary + all(저비용 정적 조건은 일괄 수집, tokenizer·
  직렬화는 정적 통과 후만) — primary 순서는 policy hash 포함.
- 질문 게이트: boolean intent → **riskExposurePolicy enum**(ALLOW_IMPLICIT/
  REQUIRE_EXPLICIT/DENY — 미래 overview·single_domain=implicit, 과거
  회고=DENY). 혼합 기간은 R2 선택 episode 기간 ∩ 미래 질문 범위만 노출.
- critical_validation_state를 expose_policy_hash에 포함, 미등록/손상 상태
  =critical 하향 유지(fail-closed).
- **RiskPromptBlock immutable**: serialized_text·compression_mode·
  exact_token_count·immutable=true — reducer는 내부 편집 금지, 부족 시 R3
  serializer에 더 작은 mode 요청.
- canary 기본 거부: allowlist 부재·식별값 없음·조회 실패·설정 누락·미등록
  모델/질문 유형 전부 비주입. allowlist는 내부 subject ID 기준.

버전: R5-a=risk-expose-**r4.0.1-gated**(게이트 의미 확장), R5-b 배선 완료
시 **r4.1.0-canary**. expose_pipeline.reviewed=true는 R5-b 통합 fixture
감수 후.

### 28-1. R5-a 구현 결과 (2026-07-16 — 배선 전 계층·chat 미연결)

게이트 확장(risk_exposure — r4.0.1-gated):

- **kill switch**(게이트 최앞·mode 무관)·**EXPOSE_PIPELINE_NOT_REVIEWED**
  분리(현 reviewed=false → 모든 조건 충족이어도 비주입 fixture)·
  **TOKENIZER_MODEL_MISMATCH**(counter.model_id ≠ resolved model — 부재
  포함) 신설.
- **primary + all suppression reasons**: 정적 저비용 조건(kill switch·mode·
  canary·질문·scope·pipeline·hash·tokenizer·모델 일치) 일괄 수집, primary=
  고정 순서(policy hash 포함)의 첫 항목 — 예산·직렬화는 정적 통과 후만.
- **riskExposurePolicy enum**(ALLOW_IMPLICIT/REQUIRE_EXPLICIT/DENY):
  감수 5유형 전부 ALLOW_IMPLICIT('위험' 단어 없이 허용 — fixture), 미등록
  =DENY, REQUIRE_EXPLICIT만 intent 검사. **혼합 기간**:
  filter_payload_to_future_scope — R2 선택 episode 기간 ∩ 미래 질문
  범위만(records·llm 병행 필터·입력 불변).
- **critical state fail-closed**: 명시 "validated"가 아니면(미등록·손상
  포함) 하향 유지. critical_validation_state를 expose_policy_hash에 포함.
- **RiskPromptBlock**(frozen — serialized_text·compression_mode·
  exact_token_count·immutable) + **finalize_risk_prompt_block**: tier별
  ①block budget 계수 ②최종 prompt 조립 후 **동일 counter 재계수**
  ③한도 내면 채택, 전부 초과=FINAL_PROMPT_TOKEN_OVERFLOW 비주입(사전
  headroom만으로 주입 금지). reducer 내부 편집 불가(frozen fixture).
- **suppressed guard block**(RISK_EXPOSURE_GUARD_BLOCK — EXPOSE 계열
  전용): 구조화 block 부재 시 일반 후보의 위험 승격 금지 + 권고 수준 표현
  허용(과잉 차단 금지) + level≠확률·qualifier 유지·prohibited 미생성.
  OFF/SHADOW 미참조를 grep fixture로 강제(apps 전체 0 hit — R5-b 배선 시
  EXPOSE 분기 내에서만 허용).
- **answer claim audit**(risk_claim_audit — 결정적 패턴·LLM 미사용):
  확정 발생·사고/질병/법적 단정·금전 손실 확정·동일 사건 단정·recovery
  보장·항목 원문·level 격상 검사 → ALLOW/REVISE_REQUIRED(위반 시 재작성/
  제거/차단 — 기록만 남기고 노출 금지).

fixture 16종(기존 10 + R5-a 6): kill switch 순서·pipeline not reviewed·
모델 불일치·혼합 기간 필터(게이트 경유 포함)·2차 계수 3분기(채택/재압축/
비주입)·claim audit(위반·권고 통과)·guard block EXPOSE 전용. **게이트**:
pytest 2080·ruff clean·mypy 0(530)·baseline 불변·manifest 일치.

**R5-b(다음 차수 — 배선)**: chat_service 주입 지점(EXPOSE 분기 —
OFF/SHADOW prompt byte 불변), 질문 파서→questionType/temporalScope/
future_period_range 매핑, tokenizer adapter 실물(llm_config resolved
model→counter registry), canary allowlist(내부 subject ID)·kill switch
env, answer audit 배선(위반 시 재생성 흐름), 통합 fixture(§14 전체) →
expose_pipeline reviewed=true 감수 → r4.1.0-canary → EXPOSE_CANARY 개시.

### 28-2. R5-b 실배선 구현 결과 (2026-07-16 — canary 개시 전·비주입 고정)

**완료 조건 반영(감수 46차)**:

1. **FULL 명시(§5)**: RENDER_TIERS=FULL(=P2 별칭·최대 표현)→P1→P0→
   P0_COMPACT — finalize가 FULL부터 시도, 진단(diagnostics)은 어떤 tier에도
   미포함(감사 전용) 명시.
2. **감사 records 전량 보존(§4)**: filter_payload_to_future_scope 재설계 —
   OUTSIDE_FUTURE_SCOPE/IN_SCOPE 표시 후 **llmRiskEpisodes만** 필터.
   판정=primary activity 기간(recovery window·supporting 단독·배경
   vulnerability의 미래 존재는 재노출 사유 아님 — docstring 계약).
3. **RiskPromptBlock checksum(§7)**: content_hash(sha256[:16]) +
   verify_risk_block_integrity(원문 포함+해시 일치) — 복사 후 변형·wrapper
   훼손 탐지, 실패=비주입. reducer는 그대로 포함/작은 tier 재요청/전체
   비주입만.
4. **instruction/guard 분리(§8)**: RISK_EXPOSURE_INSTRUCTION_BLOCK(주입
   시 — level≠확률·qualifier 유지·claim code 준수·표시 수준 초과 금지)과
   RISK_EXPOSURE_SUPPRESSED_GUARD(비주입 시 — 일반 후보 위험 승격 금지·권고
   허용) — 둘 다 EXPOSE 계열 전용·최종 token 계수 대상(finalize builder
   계약).
5. **episode별 claim audit(§10·12)**: audit_risk_sections — 구조화 risk
   section별 검사(qualifier 존재를 episode 단위로 — 전역 출현 오인 차단)
   + **전체 답변 감사 병행**(mainAnswer 위반 검출 fixture).
6. **재작성 상태기(§11)**: plan_remediation — DELIVER/REVISE(1회)/
   REGENERATE_WITHOUT_RISK/BLOCK, MAX_RISK_REVISION_ATTEMPTS=1(정책 해시
   포함) — 위반 초안 직접 전달 경로 없음.
7. **claim audit 감수 표면(§16)**: RISK_CLAIM_AUDIT_VERSION=
   risk-claim-audit-r5.0.0 · claim_audit_policy_hash(패턴 registry·
   qualifier 어휘·격상 패턴·부정문 정책·재작성 횟수) — expose_policy_hash에
   포함(정책 변경=expose 재감수 신호).
8. **canary 정책(§3·14)**: RISK_CANARY_QUESTION_TYPES=초기 3유형(specific·
   single_domain·overview — compare/followup 2차), RISK_EXPOSE_CANARY_
   SUBJECT_IDS(인증 내부 subject ID·기본 빈 set=전부 거부·로그는 해시),
   RISK_EXPOSURE_KILL_SWITCH(게이트 최앞).

**chat_service 배선**: EXPOSE 계열 모드에서만 실행되는 단일 분기(prompt
최종 조립 직후) → risk_exposure_service.apply_risk_exposure — 현 단계는
expose_pipeline.reviewed=false 고정 + adapter 부재 + 질문 매핑 미공급이라
게이트가 **전부 비주입**하고 suppressed guard만 부착(위험 정보는 어떤
필드로도 미주입 — '"riskEpisodes"' 부재 fixture). OFF/SHADOW는 분기 자체
미실행 — **실제 chat 최종 prompt·system byte-identical 통합 fixture**.

fixture: unit 16종 갱신(FULL·records 보존) + 통합 8종(OFF/SHADOW byte
불변·canary suppressed guard 차등·게이트 관측 fail-closed·kill switch·
재작성 흐름·episode별 qualifier·checksum·미래 필터 보존). **게이트**:
pytest 2088·ruff clean·mypy 0(532)·suppression diff 0·profile baseline
exact·manifest 일치(claim_audit_policy_hash 반영).

**canary 개시 잔여(EXPOSE_CANARY 전 감수 필수)**: ①모델 tokenizer adapter
실물(llm_config resolved model→counter registry — TOKENIZER_MODEL_MISMATCH
는 게이트 구현 완료) ②질문 파서→questionType/temporalScope/future_period_
range 매핑 감수 ③구조화 출력 envelope(risk_guidance) 프롬프트 계약 ④audit
재작성 흐름의 LLM 재호출 배선 ⑤expose_pipeline reviewed=true 전환 감수 →
r4.1.0-canary.

### 28-3. 감수 47차 — BYPASS/SUPPRESSED/INJECTED 분리 (2026-07-16)

**핵심 교정(데굴님 지적)**: "위험 파이프라인 적용 대상이 아닌 요청은 '위험
정보가 없는 노출 요청'이 아니라 '노출 파이프라인을 전혀 거치지 않은 기존
요청'이다 — 진단 로그만 남기고 프롬프트는 한 바이트도 바뀌면 안 된다."
직전 구현은 canary 비허용·pipeline 미감수 요청에도 suppressed guard를
붙여 모델 행태를 바꿀 수 있었다(기각 반영).

1. **ExposureDisposition 3상태**: BYPASS(정적 사유 — kill switch·mode·
   canary·질문 정책·scope·pipeline 미감수·hash·tokenizer/모델) → guard조차
   없이 **prompt 완전 불변**·진단 로그만 / SUPPRESSED(런타임 사유 — 예산·
   episode 부재·직렬화·final overflow) → suppressed guard만 / INJECTED →
   instruction + 감수 block. reason→disposition 매핑을 expose_policy_hash에
   편입.
2. **§2 필수 회귀 fixture 4종**: ①canary 비허용 → BYPASS·실제 chat 최종
   prompt baseline byte-identical ②canary 허용+pipeline 미감수 → BYPASS·
   guard 없음 ③감수·허용·tokenizer 정상+episode 없음 → SUPPRESSED·guard만
   ④전 조건 충족 → INJECTED·instruction+block(실주입 유일 경로). kill
   switch도 BYPASS(prompt 불변) 검증.
3. **FULL alias 정리**: render tier에서 "P2" 별칭 제거 — FULL 단일 명칭
   (survey·로그 이중 집계 방지).
4. **단일 삽입 검증**: wrap_risk_block(BEGIN_RISK_BLOCK:<hash>…
   END_RISK_BLOCK) + verify_risk_block_integrity 강화 — 시작/종료 marker
   각 1회·본문 1회·checksum 일치(hash가 맞아도 중복 삽입=실패 fixture).
5. **RISK_EXPOSE_PIPELINE_REVIEWED config**(기본 False — manifest
   reviewed와 함께 감수 후 1줄 전환): False면 게이트가 BYPASS 처리.

**게이트**: pytest 2090·ruff clean·mypy 0(532)·baseline 불변·manifest 일치.
EXPOSE_CANARY 개시 잔여(§28-2 목록에 추가): 구조화 risk_guidance envelope
불변식(episode_key ⊆ llm episodes·중복/미등록 실패·warning-first 순서·
renderer 후 최종 문자열 재감사), claim audit FP/FN 코퍼스(안전 부정문·우회
확정문) + canary 관측 지표(violation/revision/regenerate/block rate).

### 28-4. 감수 48차 반영 — SSOT 분리·integrity 재조립·registry·envelope·FP/FN (2026-07-16)

1. **decision reason 스키마(§2)**: 게이트 정본=primary_decision_reason/
   all_decision_reasons(BYPASS 사유는 suppression이 아님 — 기존 키는 하위
   호환 별칭으로 병기·마이그레이션 후 제거), 관측은 disposition별 분리 집계.
2. **감수 SSOT 분리(§4 — 권고 채택)**: RISK_EXPOSE_PIPELINE_REVIEWED 제거
   → **RISK_EXPOSURE_RUNTIME_ENABLED**(활성화만 결정). 감수 사실은
   manifest가 SSOT: 서비스가 RISK_REVIEW_MANIFEST.json에서
   expose_pipeline.reviewed + **expose_policy_hash 런타임 실비교**(로드
   실패·필드 부재·불일치=fail-closed). 게이트 주입 조건=manifest reviewed
   AND hash 일치 AND runtime enabled AND mode. fixture: 한쪽만 true(runtime
   만/manifest만) → BYPASS, hash 불일치 → BYPASS(POLICY_HASH_MISMATCH).
3. **integrity 실패 재조립 계약(§7)**: RISK_BLOCK_INTEGRITY_ERROR(SUPPRESSED
   부류) 신설 + resolve_block_integrity_failure — instruction만 남는 상태
   금지: INJECTED→SUPPRESSED 강등·전부 제거·guard 삽입·전체 재계수 계약
   (부분 편집 금지). policy hash 명시.
4. **tokenizer adapter registry 골격(§10-③)**: token_counter_registry —
   resolved model ID 기반 해소·heuristic mode 등록 금지·기본 빈
   registry(미등록=BYPASS)·fallback 라우팅 시 재해소+전체 재계수 계약
   docstring. 실물 adapter는 canary 차수에서 감수와 함께 등록.
5. **risk_guidance envelope 불변식(§10-⑤)**: validate_risk_guidance_
   envelope — 미등록 episode_key/중복/exposed level 초과/warning-first
   순서 위반 검출(위반=REVISE 경로).
6. **claim audit FP/FN 보강(§11 — r5.1.0)**: 부정문 예외(매치 직후 25자 내
   '아닙니다' 등 5표지 — "사고가 난다는 뜻은 아닙니다" 통과 fixture) +
   우회 단정 패턴(circumvented_certainty: "피하기 어려운 흐름"·"이어지는
   수순"·"현실화될 가능성이 매우 높"·"기정사실") — claim_audit_policy_hash
   변경(=expose 재감수 신호, 본 감수 지시로 정당).

fixture +6(통합 22종). **게이트**: pytest 2096·ruff clean·mypy 0(533)·
baseline 불변·manifest 일치. expose_pipeline.reviewed=false·RISK_ENGINE_
MODE=off·RISK_EXPOSURE_RUNTIME_ENABLED=false 유지(3중 잠금).

**잔여(canary 개시 전)**: ④질문 파서 SSOT 매핑 ⑥재작성·재생성 LLM 실배선
⑦provider 직전 검증 배선(전용 message slot 권장) ⑧renderer 후 최종 문자열
재감사 ⑨expose_pipeline 감수(manifest reviewed=true) ⑩r4.1.0-canary.

### 28-5. 감수 49차 반영 — snapshot·재조립 상한·인터페이스·누락 정책·절 단위 부정문 (2026-07-16)

1. **별칭 계약(§1)**: 구 suppression 필드=정본(decision reasons) 복사만 —
   별도 계산 금지·불일치 0 fixture(OFF·EXPOSE 양쪽)·r4.2.0 제거 예정 명시.
2. **ManifestSnapshot(§2)**: 파일 **단일 read** → 불변 snapshot(reviewed·
   hash_ok·schema_version·snapshot_hash) — 요청 전체가 동일 snapshot 사용
   (배포 중 교체의 혼합 상태 차단). parse 실패·schema 미지원(허용=10)·필드
   부재 전부 fail-closed. 관측에 manifest_snapshot_hash·schema_version
   병기(원문 미기록).
3. **재조립 상한(§3)**: MAX_SUPPRESSED_REBUILD_ATTEMPTS=1(INITIAL→REBUILD→
   TERMINAL — 재귀 금지), guard 포함 prompt조차 예산 초과 시
   SUPPRESSED_GUARD_TOKEN_OVERFLOW + **RISK_SAFE_RESPONSE_REQUIRED**
   (결정적 fallback/안전 재생성/BLOCK — guard 없는 조용한 원 prompt 호출
   경로 없음). policy hash 편입.
4. **TokenCounter 인터페이스(§4)**: ProviderRequest(전 message·schema·
   config) + count_request 정본 — 문자열 단건이 아니라 provider 전송 요청
   전체를 계수. provider_id·counter_version 필드. adapter 등록과 canary
   활성화 분리(shadow 계수 검증 후 감수) 원칙 문서화.
5. **warning 누락 정책 + envelope schema(§5)**: exposed WARNING 이상=출력
   필수(MISSING_REQUIRED_RISK_EPISODE→REVISE), WATCH/ADVISORY 생략 허용.
   미지 필드·빈 episode_key·빈 text 금지, level은 입력과 **정확 일치**
   (초과=EXCEEDS·상이=MISMATCH), 부재(None)와 빈 배열 구분은 호출부 계약.
6. **절 단위 부정문(§6 — 25자 창 기각·r5.2.0)**: 매치가 속한 절의 부정
   표지만 인정(절 경계=문장 부호+역접 접속 — "하지만" 뒤 재단정은 별도
   판정), 이중 부정("않는다고 볼 수는 없" 등)은 예외 제외 + 위반 패턴으로
   직접 편입. **필수 코퍼스 4종 fixture**: 안전 부정문 허용/역접 재단정
   위반/이중 부정 위반/부정+우회 단정 위반.

fixture +6(통합 28종). **게이트**: pytest 2102·ruff clean·mypy 0(533)·
baseline 불변·manifest 일치. 3중 잠금 유지.

**잔여(canary 개시 전)**: 질문 파서 SSOT 매핑 → adapter 실물 shadow 등록·
계수 검증 → 구조화 output envelope 배선 → 재작성/재생성 LLM 실배선 →
provider 직전 검증 → renderer 후 최종 감사 → expose_pipeline 감수 →
r4.1.0-canary(별도 커밋 전환).

### 28-6. 감수 50차 반영 — 파서 SSOT 매핑·safe response 순서·validation 상태기·부분수열·evidence (2026-07-16)

1. **질문 파서 SSOT 매핑(§9-① — risk_question_mapping)**: IntentJson
   정본에서만 매핑(새 분류기 없음) — FORTUNE_OVERVIEW→period_overview·
   DOMAIN_ANALYSIS→single_domain_period·EVENT_EXPLANATION/DECISION_SUPPORT
   →specific_event·COMPARISON→multi_episode_compare(canary allowlist가
   차단). **fail-closed**: 미등록 query_type(chart_analysis·remedy 등)·
   불명확 time_scope(TIMELESS·LIFE_STAGE)·미래 질문의 time_range 부재/라벨
   비정형·비단독 subject(동반자 위험 노출은 별도 감수 전 금지)=None →
   BYPASS. TIMING_SEARCH(좋은 시기 탐색)는 적합성 별도 감수 전 미매핑.
   PAST→past_only(게이트 차단). Domain→위험 도메인 매핑(wealth→finance·
   health→health_safety·education→selection). chat_service가 intent를
   서비스에 전달(파서 정본 소비).
2. **safe response 순서 고정(§3)**: RISK_SAFE_RESPONSE_SEQUENCE + plan_
   safe_response — 안전 재생성 1회→renderer 후 전체 감사→통과=전달/실패=
   결정적 fallback→fallback 감사 실패=BLOCK(호출부 임의 선택 금지·최종
   감사 생략 경로 없음). policy hash 편입.
3. **strict manifest schema + canonical hash(§2)**: 필수 필드 부재·타입
   불일치=실패(get 기본값 제거), snapshot_hash를 canonical parsed JSON
   (sort_keys) 기준으로 — 공백·키 순서 차이에 불변.
4. **adapter 검증 상태기(§4)**: UNREGISTERED/SHADOW_VALIDATING(등록
   직후)/VALIDATED/SUSPENDED — resolve_validated_counter는 **VALIDATED만**
   반환(EXPOSE 자격), shadow 측정은 resolve_counter. calibration 용어
   (counted vs provider_reported·delta·relative_error) 문서화.
5. **envelope 보강(§5·6)**: 생성 순서=입력 순서의 **부분수열**(watch/
   advisory 생략 허용·역전 금지 — ORDER_NOT_SUBSEQUENCE),
   validate_injected_guidance_presence(None=RISK_GUIDANCE_FIELD_MISSING·
   []=필수 warning 있으면 실패), audit_rendered_output(내부 episode_key의
   최종 Markdown 노출=INTERNAL_KEY_LEAKED).
6. **audit evidence + FP/FN 확장(§7·8 — r5.3.0)**: violation에 matched_
   span·clause_text(80자)·negation_status·exception_applied 보존(원문
   장기 저장 없음), 확률 가장 단정("거의 확실하게"·"사실상 결과가 정해진"
   등)·부정 뒤 재강화("실질적으로 손해를 피하기") 패턴 편입.

fixture +5(통합 33종). **게이트**: pytest 2107·ruff clean·mypy 0(534)·
baseline 불변·manifest 일치. 3중 잠금 유지.

**잔여(canary 개시 전)**: adapter 실물 shadow 등록·provider 계수 대조 →
구조화 output envelope의 provider schema 강제 배선 → 재작성/재생성 LLM
실배선(plan_remediation·plan_safe_response 소비) → provider 직전 검증
(snapshot 동일성·validated counter·token·marker·checksum·disposition) →
renderer 후 최종 감사 배선 → expose_pipeline 감수 → 별도 커밋 canary 전환.
