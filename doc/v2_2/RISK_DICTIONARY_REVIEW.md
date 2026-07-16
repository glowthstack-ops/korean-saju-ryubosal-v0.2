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
