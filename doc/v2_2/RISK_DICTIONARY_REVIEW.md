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
