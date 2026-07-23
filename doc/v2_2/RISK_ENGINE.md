# RISK_ENGINE.md — 위험 탐지 엔진 규격

> 2026-07-15 데굴님 제공 스펙 + 같은 날 조건부 승인 감수 사항을 규격으로 고정한 문서.
> docs/08~11과 동급의 **전체 규격**이다(절대 원칙 10) — 항목을 임의로 추가·삭제·재해석하지 않는다.

## 0. 목표 문장

> 사주서비스는 좋은 시기를 추천하는 데 그치지 않고, 사용자가 앞으로 겪을 수 있는 주요
> 부담과 위험을 사전에 인지하고 피해를 줄일 수 있도록 돕는다.

본질은 부정 문장의 양산이 아니라 **위험 관리**다. 다음 5가지가 함께 구현돼야 한다
(하나라도 빠지면 "요즘 조심하세요" 수준의 모호한 풀이 또는 공포 경고가 된다):

1. 불리 신호가 **별도의 위험 사건**을 생성한다 (감점·quality flip으로 소비 금지).
2. 기회 후보와 위험 후보를 **독립적으로 선별**한다 (한 풀에서 경쟁 금지).
3. **발생 가능성과 피해 규모를 구분**한다.
4. 사용자의 **실제 노출과 보호 요인**을 반영한다.
5. 경고와 함께 **예방 방법과 회복 시점**을 제공한다.

## 1. 아키텍처 — 기회·위험·회복 독립 산출

```text
운세 원시 신호 (Raw Signal Ledger — reducer·모디파이어 이전)
 ├─ Opportunity Engine (기존 EventEngineV2 6계층 — 불변)
 ├─ Risk Engine        (신규 — 위험 후보 독립 생성)
 └─ Protection/Recovery (R1/R2 — 보호 분석·회복 창 산출)
```

### 1-1. 입력 원칙 (R0 최우선 승인 조건)

위험 엔진은 **EventEngineV2의 최종 후보를 입력으로 쓰지 않는다.** 기존 파이프라인은 기신
배율 하향·공망 감점·favorability 전환·floor 미달 제거·Top-N 축소·병합을 이미 수행하므로,
그 뒤 데이터에는 위험 근거가 손실돼 있다. 위험 엔진의 입력은 `RawPeriodFacts`(원시 신호
스냅샷)다:

- 유입 십성(층위별) / 관계 발동(합충형파해, 자극 궁성) / 공망 활성
- 시점 유입 글자의 용기신 극성(合化·合去 반영) / 대상 기둥 12운성

구현: `EventEngineV2._score_target()`이 모디파이어 적용 **이전** 재료에서 스냅샷을 구성해
`RiskEngine.generate()`에 전달한다. 긍정 후보가 0건이어도(조기 반환) 위험 근거는 수집된다.

### 1-2. 근거 provenance — `RiskEvidence`

문자열 코드가 아니라 구조화 근거. `role`은 4분류:

| role | 의미 |
|---|---|
| `trigger` | 위험 발생 근거 |
| `amplifier` | 위험 강도 증가 |
| `mitigator` | 보호·완화 (protection 축) |
| `blocker` | 해당 위험의 발현 제한 |

`evidence_id = "{period_key}|{source}"` — source는 매칭 룰이 아니라 **바탕 원인 사실의
서명**(예: `relation:CHUNG:day_pillar`, `polarity:GI_STRONG`)이다. 서로 다른 룰이 같은
원인을 잡으면 evidence_id가 같아 중복 반영이 차단되고, 독립 출처 판정(source distinct)도
동일 원인 파생을 1개로 계산한다. (예: 세운 충 + 그 충의 파생 감점 + 그 충의 태그 = 출처 1개)

## 2. 개념 3분류 — 압박 ≠ 취약성 ≠ 사건 위험 (`RiskKind`)

| kind | 정의 | 사용자 노출 |
|---|---|---|
| `pressure` | 사건을 특정하지 않는 전반적 부담·소모 (피로 누적, 계획 차질, 긴장, 비용·책임 증가, 선택지 축소) | 시기 압박으로 서술 |
| `vulnerability` | 특정 영역의 보호력 약화 (검토력·집중력·완충력 저하) | **단독 노출 없음** — incident_risk 생성·심각도 상향의 중간 신호 |
| `incident_risk` | 구체 사건 가능성 형성 (계약 취소, 예상 밖 지출, 평가 불이익, 관계 단절, 일정 차질, 탈락·불리 배치) | 위험 사건으로 서술 |

추가로 **피해 규모**는 사건 발생과 별개다(같은 재물 손실 신호라도 무거래자와 대출·보증
보유자의 피해가 다름). 캘리브레이션도 3분리한다: `운의 압박 있었음 / 사건 발생함 /
실제 피해 컸음`은 서로 다른 결과다.

## 3. 위험 이벤트 사전 — `backend/dictionaries/risks/<domain>.json`

- **risk_id는 EventKeyV2와 별도 네임스페이스**다 (21키 하드 스위치 회피, 2026-07-15 승인).
  도메인별 접두 규약: FIN_/CAR_/LEG_/HLT_/REL_/MOV_/SEL_ (lint 강제 — 파일 간 충돌 차단).
- 도메인 7종: finance / career / contract_legal / health_safety / relationship /
  relocation / selection (스펙 §3의 위험 목록 전수를 항목화).
- 기존 `SignalSpec`을 재사용하지 않는다 — 위험 전용 룰 스키마(`RiskRuleSpec`)로
  trigger/amplifier/mitigator/blocker를 분리한다.

항목 스키마 (pydantic: `RiskItem`, `dictionaries.py`):

```json
{
  "riskId": "FIN_CASHFLOW_PRESSURE",
  "domain": "finance",
  "kind": "incident_risk | pressure | vulnerability",
  "riskFamily": "cashflow",
  "relatedDomains": ["contract_legal"],
  "baseImpact": 0.65,
  "triggerRules": [ { "id": "...", "group": "event_shape", "strength": 0.6, "...조건(AND)..." } ],
  "amplifierRules": [],
  "mitigatorRules": [],
  "blockerRules": [],
  "minimumEvidence": {
    "triggerCount": 1,
    "independentSourceCount": 2,
    "requiredGroups": ["event_shape", "target_activation"]
  },
  "manifestations": [ { "id": "unexpected_spend", "ko": "예상하지 못한 지출 발생" } ],
  "prohibitedClaims": ["파산 단정"],
  "allowedClaimScope": ["관리 필요성", "검토 필요성", "가능한 발현 형태"],
  "claimCeiling": "conditional_warning",
  "reviewed": false
}
```

룰 조건 축(전부 AND, 최소 1개 필수): `tenGod` / `tenGodGroup` / `relation`(+`relationPalace`,
`relationTargetTenGod(Group)` — **무엇을 충·형했는가**) / `polarityRoleIn` / `voidActive` /
`twelveStageIn`. 각 룰은 신호 역할 그룹(`group`)을 갖는다(§3-1).

**minimum_evidence 정책**: 개수(`independentSourceCount` — incident_risk ≥2 lint 강제)와
별개로 `requiredGroups`가 **서로 다른 필수 신호 그룹**을 요구한다 — '약한 범용 신호
2개'와 '사건 형태 1 + 대상 활성 1'을 구분하기 위함(2026-07-15 감수). incident_risk는
감수 승격(reviewed:true) 시 `event_shape`·`target_activation` 포함 + generic 그룹 trigger
금지가 lint로 강제된다.

**표현 정책**: 건강·법률은 블랙리스트(`prohibitedClaims`)만으로 빈틈이 생긴다 — 허용
범위 화이트리스트(`allowedClaimScope`)와 표현 상한(`claimCeiling`: advisory/watch/
conditional_warning/warning)을 병용한다.

**도메인 교차 중복**: 같은 현실 사건(임대차 하자 → MOV 계약실패 + FIN 지출 + LEG 분쟁)이
여러 risk_id로 갈라질 때를 위해 `riskFamily`/`relatedDomains`로 통합 키를 저작한다 —
최종 출력은 주 위험 1건 + 파생 영향 설명(별도 3건처럼 부풀리지 않음, R2 배선).

### 3-1. 공통 신호 역할 매트릭스 (표 A — 2026-07-15 감수 확정)

**핵심 원칙: 기신·공망·12운성은 원칙적으로 독립 사건 트리거가 아니다** — 사건 종류를
결정하지 않고 방향·부담을 키우는 증폭·취약 신호다. 극성·공망·운성 조건만으로 구성된
룰은 event_shape/target_activation 그룹이 될 수 없다(스키마 강제). **incident_risk는
반드시 사건 형태(event_shape)와 대상 활성(target_activation) 근거를 모두 가져야 한다.**

| 신호 | 기본 역할 | 독립 트리거 | 도메인 지정 |
|---|---|---|---|
| 기신(polarityRole) | amplifier | 아니오 | 아니오 |
| 공망(voidActive) | vulnerability/amplifier | 원칙적으로 아니오 | 대상에 따라 |
| 충(CHUNG) | activation/disruption | 조건부 | **대상 정보 필요**(relationTarget*) |
| 형(HYEONG) | persistence/conflict | 조건부 | 대상 정보 필요 |
| 겁재(JIECAI) | event_shape 후보 | 조건부 | 재물·관계 맥락(동반 조건) 필요 |
| 편재(PIANCAI) | volatility | 단독 불가 | 재물 |
| 12운성(twelveStageIn) | operability/amplifier | 단독 불가 | 제한적 |
| 궁위 활성(relationPalace) | target_activation | 보조 | 예 |
| 다층 반복 | persistence(R1) | 단독 불가 | 기존 대상 계승 |

**targeted_event_shape**(2026-07-15 감수 3차 확정): 사건 형태와 피자극 대상이 하나의
구조화된 사실에 함께 담긴 경우 — '대상이 특정된 일반 관계'(targeted_relation —
`target_activation`으로 저작)와 구분한다. 관계+십성(군) 대상만으로는 성립하지 않고
(스키마 강제) 다음 중 하나가 필요하다: ①궁위가 사건 형태를 정의(배우자궁이 관계
변동형 충·형의 직접 대상) ②사건 구조 십성 동반(겁재-재성 경쟁 구조가 재성을 직접
대상으로, 상관 동반 관성 피격, 편관 동반 형). **한 사실이 두 의미를 충족해도 독립
원인은 1개**로 계산하며(원인 서명 원칙), 독립 원인 1개 후보는 R1 등급에서 watch
상한이다 — 후보 생성 조건과 높은 경고 등급 조건은 다르다.

증거 계약(`evidenceContract`) — requiredGroups의 상위 표현:

```json
{ "anyOf": [ { "allOfGroups": ["event_shape", "target_activation"] },
             { "allOfGroups": ["targeted_event_shape"] } ],
  "minIndependentCauses": 1 }
```

**생성 조건 ≠ 등급 조건(감수 4차 재확인)**: 구조(shape+activation 또는 targeted)가
충족되면 독립 원인 1개도 후보는 생성된다(R1 등급 watch 상한) — 하나의 강한 구조
신호만 있어도 '주의해서 볼 후보'는 남긴다. `minIndependentCauses ≥ 2` 강제는 전체
저작 원칙이 아니라 **예외적 위험별 정책**으로, `candidatePolicy: "multi_cause_only"`
+ `rationale` 명시가 스키마로 강제된다(현재 유일 사용: HLT_CHRONIC_FLAREUP — 건강
단일 근거 오경고 통제).

**targeted_event_shape 관계 유형 allowlist**: 궁위 특정만으로 모든 관계가 사건
형태가 되지 않는다 — 충·형·파·해만 허용(우호 결합 HAP·복음 BOKEUM 스키마 거부).
잔여 항목 변환 시 '궁위가 있으니 targeted' 식 기계 변환 금지.

**reviewed 메타데이터(감수 5차 — 누적 구조)**: `reviewed:true`는 `reviewScopes`
(배열 — 통과한 감수 단계 누적: `shadow_structure`=사전 구조·shadow 감수(**사용자
노출 승인 아님**) / `scoring`(R1) / `selection`(R2) / `exposure`(R3)) +
`reviewVersions`(scope→차수) + `reviewedRuleHash` 필수(lint). **감수 무효화 가드**:
룰 본문(트리거·증폭·완화·차단·증거 계약·kind)을 고치면 해시 불일치로 lint가
실패한다 — 재감수 후 `risk_rule_hash()`로 재스탬프해야 한다(표현 정책 prohibited/
allowedClaim 변경은 exposure 감수 소관이라 해시 무관).

**관계 의미 계층**: disruptive_strong(충·형 — 단독 targeted 가능) /
disruptive_weak(파·해 — target_activation만, 단독 발화 불가·R1 등급 advisory/watch
상한) / conditional_binding(합거·묶임 등 특수 합 — relationEffect 축 필요, R1 백로그)
/ recurrence(복음 — persistence·amplifier 소관, R1) / supportive(일반 합 — 위험 사건
형태 아님, 거부).

kind별 최소 계약(reviewed:true 승격 시 lint 강제):

```text
pressure       — 비generic trigger(도메인 관련 activation 등) 1개 이상
vulnerability  — target_activation·targeted_event_shape 또는 event_shape 1개 이상
incident_risk  — (event_shape + target_activation) 또는 targeted_event_shape
                 + generic trigger 금지. polarity는 증폭 요소.
critical 승격  — 독립 원인 2개 이상 + 노출 CONFIRMED + 보호 부족 (R1)
```

### 3-2. 관계 대상 매칭 우선순위

RelationFact provenance: 궁위(palace) · 자리(position: stem/branch) · 피자극 글자
(target_letter) · 피자극 십성(target_ten_god) · 관계 종류 · 층위 · 기간. 매칭 정밀도
우선순위: ①정확한 궁위·자리 ②정확한 천간·지지 글자(relationTargetLetter) ③십성
(relationTargetTenGod) ④십성군(relationTargetTenGodGroup) ⑤도메인 일반 활성.
`relationTargetTenGodGroup`만 맞다고 배우자·직업·현금흐름 위험을 동시에 만들면 안
된다 — 궁위·글자 조건과 risk_family 억제로 분리한다. 잔여 갭(R1 백로그): 원국 취약
구조, 투간·통근 작동성, 구조 패턴, 성별 의존 배우자성.

건강·안전 도메인은 질병명·사망을 단정하지 않고 **부담 부위와 위험 행동을 경고**하는
방식으로만 저작한다(`prohibitedClaims` + 기존 PROHIBITIONS 계열 준수).

### 3-3. 관계 컨텍스트 — `RelationshipContext` (감수 16차 · env r0.5.7)

REL 차수 불변식: **관계 위험은 십성·궁위만으로 현실의 상대를 만들어내지 않는다.**
배우자궁 충은 관계 영역의 구조적 활성일 뿐이며, "현재 연인·배우자가 있다/갈등한다/
소원해진다"는 전부 현실 노출(RelationshipContext)이 공급한다.

- 필드: `target_role`(역할 어휘: current_partner/spouse/dating_partner/family_member/
  friend_peer/business_partner/colleague/broader_social) · `target_id`(익명 대상 서명 —
  실명 저장 금지, 동반자 프로필 키 등) · `exposure_status` · `financial_tie` ·
  `shared_responsibility` · `relationship_status`/`current_contact_state`(R1 예약) ·
  `is_question_target`.
- 공급원: ①2단계 프로필(항상 선택 — 부재≠DENIED) ②동반자 등록·관계힌트 —
  **테마사주·AI채팅의 궁합/함께보기에서는 등록된 동반자가 role·target_id 확인된
  컨텍스트로 주입된다**(궁합 대상은 `is_question_target=true`) ③질문 명시. R3/R5에서
  companion 레이어·프로필과 배선한다.
- 3상태: 허용 역할 컨텍스트 존재=`matched`(그 관계의 유효 노출 사용) / 질문 직접
  대상의 확인 역할이 허용 밖=`mismatched`(BLOCKED, fallback 금지 — 친구 궁합에서
  배우자 항목 미생성) / 그 외=`unknown`(유효 노출 UNKNOWN — 구조 보존).
- **UNKNOWN 노출 차등(감수 17차)**: 역할 특정 항목의 조건부 표현("현재 관계가
  있다면")은 `matched`(관계 확인 또는 관계가 질문 대상 — 연애운 질문 등)에서만 —
  `unknown`이면 unknownExposable=true여도 비노출(총운·재물운에서 partner·peer 후보
  상시 조건부 경고 반복 차단, 엔진이 exposable_when_unknown을 기계적으로 끔). 역할
  무관 항목은 기존대로 exposurePolicy가 정한다. `is_question_target`은 "질문의 직접
  분석 대상"만 의미한다 — exposure·금전 거래·공동 책임·관계 상태를 자동 확인하지
  않는다(궁합 대상이어도 financial_tie 미확인=UNKNOWN 유지).
- 유효 노출 유도: `requiresFinancialTie`(대인 금전 사건)·`requiresSharedResponsibility`
  (가족 부담) — 컨텍스트 값 False→해당 관계 DENIED, None(미확인)→CONFIRMED여도
  UNKNOWN 강등. 겁재·재성만으로 "친구에게 돈을 빌려줬다"를 추론하지 않는다.
- partner DENIED → partner-specific 후보 BLOCKED, **일반 대인 pressure로 자동 전환
  금지**(fallback 금지 불변식).
- 억제 확장: relationship 도메인의 흡수 범위는 family가 아니라 **같은 상대**(같은
  period + target_id·역할 호환) — 같은 상대·같은 원인의 감정 충돌·오해·신뢰 저하·
  거리감은 대표 1건 + 보조 역할(supporting_manifestation/background_vulnerability/
  possible_trajectory)로 수렴하고, 다른 상대(배우자 A vs 친구 B)는 원인을 공유해도
  병존한다. 감수 17차 강화: ①target_id 미확인 후보를 한 상대처럼 합치지 않는다 —
  같은 target_id가 아니면 **관계 사실(relation 원자) 공유 필수**(십성 유입 공유만으로
  수렴 금지: 부모 부담 vs 형제 오해) ②cross-family 흡수는 사전 `absorbedRoleHint`로
  수렴이 명시된 항목만(감정 충돌·소통·신뢰·거리감) — FAMILY_BURDEN·PEER_FINANCIAL은
  같은 상대·같은 원인이어도 별개 현실 문제라 자동 흡수 금지 ③대표 선택은 사전 순서
  무관 결정적 비교자(노출 적격→구체 상대(target_id)→역할 특정→specificityRank→
  canonical risk_id).

파이프라인: 절대 원칙 5 그대로 — validate(`scripts/validate_dictionaries.py`, 스키마
`RiskMappingFile` 등록·lint `_lint_risk_mapping`) → compile → regression → 배포.

### 3-4. 이동·주거 컨텍스트 — `MobilityContext` (감수 18차 · env r0.5.8)

MOV 차수 불변식: **운 신호만으로 이사 계획·계약·차량·통근의 존재를 만들지 않으며,
"원치 않는 이동"은 preference=undesired 확인이 결정한다**(신호로 비자발 판단 금지).

- 필드: `target_type`(8종: residential_move/housing_search/housing_contract/
  workplace_relocation/temporary_stay/commute_change/travel_transport/vehicle_use) ·
  `stage`(8종: no_plan~settled) · `preference`(desired/neutral/undesired — **적격성
  미사용, R3 표현 전용**) · `housing_tenure`(R1 예약) · `exposure_status` ·
  `repair_responsibility`/`commute_dependency`/`vehicle_exposure`(실질 조건 —
  False→DENIED, None→UNKNOWN 강등) · `active_contract`(stage 축이 대체)/
  `assignment_authority`(R1 예약).
- 컨텍스트는 **목록**(감수 19차) — 같은 시기 복수 계획(현 집 계약 종료·새 집 계약·
  임시 숙소·통근 조정·차량)을 `episode_id`(익명 계획 키)로 구분한다. 항목별로 축이
  호환되는 최적 컨텍스트를 선택하며, `is_question_target` 컨텍스트의 축이 항목 허용
  밖일 때만 MISMATCHED(BLOCKED — 발령 질문에서 주거 항목). 질문 대상이 아닌
  컨텍스트의 불일치는 UNKNOWN(다른 계획이 있을 수 있음). **발령(CAR) 질문이라도 별도
  residential_move·commute_change 컨텍스트가 확인되면 MOV 후보는 matched로 병존**
  (과소탐지 방지 — 조건 6).
- UNKNOWN 노출 차등(감수 19차): 구체 항목(계약·수리·통근·차량 — required_for_exposure/
  confirmed_required)은 축 미확인 시 **하드 비노출**. 일반 이동 압박
  (required_for_warning — RELOCATION_PRESSURE)은 축 미확인에서도 조건부 서술
  ('거주·이동 조건을 조정할 변수' 수준, advisory 상한) 유지 — 예상 못한 이동 압박
  경고 목적. 경고(warning) 승격은 계획 확인 필요.
- 수렴 조건(감수 19차): 같은 이동 episode = 같은 episode_id(상이하면 병존) + **stage
  호환**(명시 stage 집합이 상호 배타면 같은 원인·family여도 흡수 금지 — 계약 전
  단계의 계약 차질 vs 정착 후 통근·적응 부담은 별개 국면) + relation 원자 공유 +
  absorbedRoleHint.
- 소유권: 발령·보직=CAR primary(workplace_relocation 제외로 MISMATCHED) / 계약 문서·
  법적 책임=LEG primary / 보증금·수리비 금전=FIN 파생(crossDomainEffects) / 거주
  이동·일정·적응=MOV primary / 이동 안전=안전 권고 톤(사고·부상 단정 금지, HLT 파생).
- 수렴: 현실 대상 수렴 도메인={relationship, relocation} — 같은 이동 episode(relation
  원자 공유+absorbedRoleHint)의 일정 차질=supporting_manifestation, 통근·적응 부담=
  impact_amplifier로 대표(계약 무산·이동 압박)에 수렴. 하자·수리비, 차량 문제는 별개
  현실 문제(hint 없음 — 자동 흡수 금지).

### 3-5. 건강 컨텍스트 — `HealthContext` (감수 21차 · env r0.5.9)

HLT 차수 불변식: **건강 질문이나 명리 신호만으로 질병·치료·신체 부위를 만들어내지
않으며, 기존 질환·치료·신체적 업무 부담이 실제로 확인된 경우에만 해당 맥락의 위험을
설명한다.** 질병명·진단·부위는 컨텍스트에 저장하지 않고 룰 식별자로도 쓰지 않는다.

- 필드: `context_type`(7종+미확인: general_wellness/existing_condition/current_symptom/
  treatment_process/recovery_process/physical_workload/sleep_schedule_load) ·
  `condition_status`(none/managed/currently_uncomfortable/recently_worsened) ·
  `treatment_status`(none/monitoring/ongoing/recent_procedure) · `recovery_status` ·
  `physical_demand`(none/low/moderate/high/shift_or_irregular) · `exposure_status` ·
  `health_episode_id`(익명 — 기존 불편 관리 vs 치료 회복 vs 교대 근무 부담 분리,
  episode별 후보 분리·수렴 경계) · `is_question_target`.
- 실질 조건 4종(requiresExistingCondition/TreatmentProcess/RecoveryProcess/
  PhysicalDemand): 상태 'none'(명시 부재)→DENIED, None(미확인)→CONFIRMED여도 UNKNOWN
  강등. physical_demand는 none·low→DENIED(**직업 존재만으로 신체 부하 추론 금지**).
- **건강 질문(is_question_target)은 질환·치료 존재를 자동 확인하지 않는다** — 상태
  미확인이면 일반 컨디션 advisory(required_for_warning)만 가능하고, 질환·치료·신체
  부담 특정 항목(confirmed_required/required_for_exposure + unknownExposable=false)은
  비노출("질환이 있다면" 우회 금지).
- kind 원칙: 건강 위험은 pressure·vulnerability로만 저작한다 — 질병 발생·악화·부상·
  수술·입원·특정 장기/정신질환은 사주 신호로 incident화하지 않는다(사전 전수 fixture).
- 수렴: 수렴 도메인={relationship, relocation, health_safety} — 같은 건강 episode에서
  대표 pressure ├ 피로·컨디션=supporting ├ 회복 여력=background_vulnerability
  └ 지속 시 기능 부담=possible_trajectory(REL 불변식 동일). 다른 episode는 병존.
- 소유권: 업무량·근무 책임=CAR(같은 원인은 trigger_cause_atoms 연결 — 1회 계산) /
  치료비=FIN 파생(medical_cost_exposure) / 보험·보상·법적 책임=LEG / 차량·교통 사건=
  MOV primary(HLT는 이동 중 주의력 압박 — MobilityContext 재사용) / **실제 부상·질병
  진단=위험 엔진 예측 대상 아님**.

### 3-6. 법적 절차 컨텍스트 — `LegalProcessContext` (감수 23차 · env r0.5.11)

LEG 재검토 불변식: **문서·지연·계약·분쟁 신호가 있다는 이유만으로 모든 절차가 법적
위험으로 복제되지 않으며, 실제로 진행 중인 계약·행정·분쟁 episode에 해당하는 LEG
후보만 남긴다.** Selection 어휘를 재사용하지 않는다(공통 3상태 판정기·episode
identity·stage 억제·노출 게이트·결정적 병합만 공유).

- 필드: `target_type`(8종: contract/administrative_application/permit_registration/
  settlement_recovery/rights_obligation/dispute/litigation/claim_compensation) ·
  `stage`(12종: drafting~closed — **active_contract 포함, 감수 23차 커밋 조건**) ·
  `exposure_status` · `existing_dispute`/
  `existing_litigation`(False=DENIED·미확인=강등 — 분쟁·소송 존재 추론 금지) ·
  `document_responsibility`/`response_obligation`(R1 예약) · `process_episode_id`
  (익명 — 전세 계약 vs 인허가 vs 진행 분쟁 분리) · `is_question_target`.
- 소유권: 선발 서류=SEL / 채용 지연=CAR / 이사 일정=MOV / 금전 정산=FIN — 공식 행정·
  허가·등록·신고 절차와 법적 효력·권리·의무 문서만 LEG primary.
- 수렴: 수렴 도메인={REL, MOV, HLT, **LEG**} — 같은 process episode에서 구체 대표
  ├ ADMIN_DELAY=supporting ├ REVIEW_CAPACITY=background └ DOCUMENT_ERROR=supporting
  (독립 targeted 원인이면 병존). DISPUTE/LITIGATION은 exposure-aware 대표(소송
  requiresExistingLitigation 미확인 시 dispute 대표·소송 부담 비노출).
- **같은 현실 대상 판정 일반화(감수 23차)**: 확인된 동일성 = 같은 상대(target_id)
  또는 같은 이동·건강·법적 episode — episode 동일이 확인되면 relation 원자가 없는
  구조 신호(검토 취약 등)도 그 절차의 배경으로 수렴한다.
- **vulnerability 단독 노출 없음 명문화**: is_exposable이 vulnerability를 항상
  비노출로 판정(§2 원칙의 기계화) — 취약성이 대표가 되어 노출 가능한 압박 경고를
  지우던 역전(FIN_BUFFER_WEAK→CASHFLOW 42건) 해소.

감수 23차 **커밋 조건**(데굴님 검토 — env r0.5.11로 일괄 반영, LEG 7항목 승격):

- **PENALTY_LIABILITY C8 편입**: 제재·의무 위반 계열은 결과 단정 위험이 가장 높다 —
  감수 반납 후 formal process exposure(대상 5종·성립 전/종결 stage 제외) +
  `unknownExposable=false`(위반·제재 미확인 시 결과형 경고 비노출, "~라면" 우회
  금지)로 재승격. 금지 표현에 벌금·과태료·처벌·유죄·행정처분 단정 추가.
- **LITIGATION_ESCALATION → LITIGATION_PROCESS_BURDEN**(incident→**pressure**):
  requiresExistingLitigation=이미 소송 중이므로 '소송 확대 사건'이 아니라 진행 중
  절차의 부담이다(kind 정합성 개선 — structural incident 0.95→0.92는 룰 약화가
  아니라 재분류 효과). 분쟁→소송 전환 탐지는 별도 stage-transition shape 확보 전
  저작 금지.
- **CONTRACT_TERMINATION=active_contract stage 필수**: 협상 중 미성립(negotiating)
  은 종료 위험이 아니다(도메인별 setback 소관) — stage 축으로 기계 차단.
- **closed stage 명시 opt-in**: 종결 절차 컨텍스트는 stage 목록에 closed를 명시한
  항목만 매칭(무관 항목 포함 신규 후보 생성·흡수 차단, 사후 정산·청구는 별도
  episode로 병존).
- **vulnerability 대표 금지 일반화**: 단독 노출 없음에 더해 어느 도메인에서도 다른
  후보를 흡수하는 대표가 될 수 없다(RCW 역할 보장의 기계 강제 — 전 도메인 synthetic
  fixture 고정).
- **RCW 재측정**(confirmed 시나리오 4종: all_unknown/active_contract/행정/분쟁·소송):
  observed 90(잠재 구조 — `observed latent vulnerability 40.9%`로 표기, '활성 위험
  40.9%' 표기 금지) · **독립 사용자 노출 0 · 독립 family 기여 0 · 대표 흡수 0**
  (전 시나리오) — 절차 확인(matched) 시에도 background 수렴만 가능.

## 4. 타입 계층 (`shared_types/risk_engine.py`)

- `RiskCandidate` — **원자 후보** (단일 `period_key`). R0 산출물. 점수·등급 없음.
- `RiskEpisode` — **병합된 위험 구간** (start/peak/end). R2 산출물. R0에서는 타입만 고정.
  - 원자 후보 생성과 기간 병합의 책임 분리 — R2에서 병합 알고리즘을 독립 교체 가능.
- `RiskScoreComponents` — 6축(전부 0~1 정규화). R1 산출물.
- `ProtectiveFactor` / `RecoveryWindow` — 보호(현재)와 회복(사후)의 분리 타입.
- `ExposureStatus` — CONFIRMED / DENIED / UNKNOWN / NOT_APPLICABLE.
- `RiskLevel` — advisory / watch / warning / critical.

### 4-0. 적격 상태 불변식 (`EligibilityStatus` — 2026-07-15 감수 2차)

'matched'는 룰 평가 결과일 뿐 후보 적격 상태가 아니다. 4상태로 분리한다:

| 상태 | 의미 | 활성 집계 |
|---|---|---|
| `insufficient_evidence` | 일부 룰은 맞지만 증거 계약 미충족 | 제외(observed에만 포함) |
| `eligible` | 필수 증거 계약 충족 | 포함 |
| `mitigated` | 성립하되 보호 신호로 위험도 하향(R1) | 포함 |
| `blocked` | 노출 부재·대상 부재 등 발현 대상 제외 | 제외(기록 보존) |

활성 판정은 `is_active()` 단일 함수: eligible/mitigated이면서 특이도 억제
(`suppressed_by_specificity`)되지 않은 후보. **`is_active()`는 '구조적 활성'에
한정된다(2026-07-15 감수 3차)** — 사용자 노출 가능을 뜻하지 않는다. R1 이후
`is_score_qualified`, R3 이후 `is_exposable`(claimCeiling·등급·노출 정책)이 별도
판정으로 추가되며, 사용자 노출은 반드시 exposable을 거친다.

**매칭 fallback 금지**: provenance에 더 구체적인 대상 정보(궁위 등)가 있고 그 정보가
룰과 불일치하면, 하위 일반화 축(십성군 동일 등)이 그 룰을 구제하지 못한다(AND 결합 —
테스트 고정). 궁위 무관 매칭을 원하면 룰 자체가 궁위 조건 없는 일반 룰이어야 한다.

**원인별 완화(전역 완화 금지)**: 용희신이 강하다는 극성 사실 단독으로는 계약 분쟁·
배우자궁 충·재성 경쟁 등 모든 위험이 자동 완화되지 않는다 — 극성 단독 mitigator는
근거로만 보존되고, 실질 조건(관계 완화·통관 십성 등 원인·대상 제어 표현) 동반
mitigator만 MITIGATED로 전환한다. 투간·통근 작동성(operability)·mitigation_target
연동은 R1에서 확장한다.

```text
blocker는 후보 기록을 삭제하지 않는다.
그러나 활성 위험 후보 집계(R2 슬롯·R4 오경고 분모)에서는 제외한다.
mitigator는 후보를 유지하고 강도를 낮춘다(R1).
recovery는 현재 후보의 적격성이나 점수를 낮추지 않는다.
```

**blocker ≠ 반대 극성.** 반대 극성은 룰 불일치 조건일 뿐이다. 차단은 3종으로 분리한다:
- **hard blocker**(→BLOCKED): 위험 신호와 동시에 존재할 수 있는 차단 조건 — 대상
  글자·궁위의 원국 부재, 노출 `DENIED`/`NOT_APPLICABLE`(엔진이 자동 처리), 요구 대상
  불일치.
- **mitigator**(→MITIGATED): 용희신 제어, 통관, 충 완화 합, 제도적 보호, 완충력.
  YONG_STRONG은 blocker가 아니라 mitigator다(개정 7항목 반영).
- **claim ceiling**(후보 유지·표현 제한): 노출 미입력, 비특이적 건강 근거, 성별 정보
  부재 등 — R3 직렬화기에서 강제.

### 4-0-1. 특이도 우선 억제 (동일 원인의 다중 후보 — cap이 아니라 대표 결정)

동일 원인에서 여러 후보가 생성되면 사후 cap이 아니라 **대표 후보**를 정한다:
`구체 대상 사건(3) > 도메인 일반 사건(2) > 취약성(1) > 전반 압박(0)` (`specificityRank`,
미지정 시 kind로 유도). 억제 조건: 동일 period + 동일 `risk_family` + trigger 원인
원자(cause atom) 공유 + 더 구체적 활성 후보 존재. **흡수는 삭제가 아니라 역할
전환이다** — 흡수 후보는 `absorbed_role`을 부여받아 대표 아래에서 유지된다:
`supporting_manifestation`(동일 도메인 하위 사건) / `impact_amplifier`(압박 — 예상
영향, R1 impact 계산) / `background_vulnerability`(취약성 — 피해 확대 요인, R1
exposure 계산) / `secondary_domain_effect`(교차 도메인 파생) / `possible_trajectory`(감수 16차 —
대표 위험 진행 시의 궤적, 거리감 등 전개 방향 서술 전용). 사전 `absorbedRoleHint`가
있으면 kind 기본값 대신 그 역할을 쓴다. family가 다르면(재성
피격→지출 vs 배우자궁 피격→관계 재조정) 같은 충에서 나와도 별개 위험으로 병존한다.
`relatedDomains`는 후보 복제용이 아니라 주 도메인 후보에 파급 도메인을 부착하는
용도다 — 독립 추가 근거가 있을 때만 교차 도메인 후보를 별도 생성한다.

감수 16차 일반화: 대표는 그룹 최상위 1건 고정이 아니라 **선호 순서(노출 적격성 →
특이도)대로 원인을 공유하는 첫 적격 대표**를 후보별로 찾는다(이미 흡수된 후보는 대표
불가 — `primary_risk_id`는 항상 활성 대표). relationship 도메인의 억제 범위는 §3-3
(같은 상대)을 따른다. 같은 원인의 FIN·REL 교차 도메인 동시 활성(예: 겁재-재성 충 →
FIN_UNEXPECTED_EXPENSE + 대인 금전 사건)의 대표 선정은 R2 Episode 병합 소관 —
R0.5는 양쪽 구조 보존(REL 쪽은 노출 CONFIRMED 전 비노출이라 사용자 중복 없음).

### 4-1. protection ≠ recovery (필수 분리)

- **protection(보호)**: 현재 위험의 발생 가능성·피해를 낮춤 — 용희신 제어, 통관, 합에 의한
  충 완화, 문서·절차 보호, 실제 노출 없음. → 점수의 차감 축.
- **recovery(회복)**: 위험·압박 **이후**의 정상화 흐름 — 다음 기간 기신 약화, 보호 오행
  유입, 충돌 해소. → `recovery_window`로 **별도 산출**. 현재 위험 점수에서 빼지 않는다.
  (위험 강+회복 빠름 vs 위험 중+회복 늦음을 구분해야 하므로.)
- 좋은 신호가 있어도 위험을 **삭제하지 않는다**: "위험 신호는 있으나 보호 요인이 있어
  실제 피해가 커질 가능성은 낮다"로 서술한다.

### 4-2. risk_level ≠ confidence (독립 축)

- `risk_level`: 얼마나 주의할 문제인가. `confidence`: 이 판정의 근거가 얼마나 충분한가.
- 영향도 크지만 근거 약함 → warning + confidence low / 발생 가능성 높지만 피해 작음 →
  watch + confidence high.
- confidence가 높다고 critical이 되거나, risk_level이 높다고 확신형 문장을 생성하면 안 된다.

## 5. 위험 점수 — R1 규격 (위험 사전 감수 이후 구현)

```text
risk_priority = occurrence × impact × exposure + persistence + compound − protection
```

- 전 축 **0~1 정규화** 선행. 곱셈 구조(occurrence×impact×exposure)라 셋 중 하나가 낮으면
  과장 경고가 줄어든다.
- 축 역할: occurrence=운 신호 / impact=사전 base_impact prior / exposure=사용자 현실 /
  persistence=기간 반복성 / compound=다른 위험으로 확산 / protection=현재 완충.
- **중복 방지 불변식**:
  - 한 evidence_id는 occurrence 직접 점수에 **한 번만** 반영.
  - persistence는 **기간 반복 횟수만** 반영(같은 신호를 재합산하지 않음).
  - compound는 **별도의 다른 risk_id 연결이 있을 때만** 반영.
- 연쇄 구조(직업 갈등→퇴사 압박→소득 감소→현금흐름 악화)는 개별 사건 3개가 아니라
  **복합 위험 시나리오**로 묶는다(compound).
- **possible_trajectory 불변식(감수 17차)**: trajectory로 흡수된 후보(거리감 등)는
  "현재 압박이 지속될 경우 나타날 수 있는 후속 양상"으로 한정한다 — occurrence 점수
  증가·독립 원인 수 증가·별도 incident 생성·위험 등급 상승에 **일절 기여 금지**.
  독립된 추가 원인이 있을 때만 별도 active 후보가 될 수 있다(그 경우 흡수되지 않음).
  표현도 "관계가 멀어진다"가 아니라 "조율이 오래 지연되면 거리감이 커질 수 있다"
  수준으로 제한.
- **교차 도메인 1회 계산 불변식(감수 17차)**: 같은 원인(공유 relation 원자 —
  `RiskCandidate.trigger_cause_atoms`가 연결 키)에서 생성된 FIN+REL 병존 후보는
  구조 후보 2개를 보존하되, independent cause **1회**·occurrence 직접 점수 **1회**만
  계산하고 사용자 risk budget에서는 R2가 대표 1개를 선택한다(양쪽 노출 확인 시에도
  중복 노출 금지 — episode 병합 키에 trigger_cause_atoms 교집합 사용).

### 5-1. exposure 정책 (미입력 숫자 대체 금지)

`ExposureStatus`로 상태를 분리하며 UNKNOWN을 0.5 같은 중간값으로 대체하지 않는다.

| 상태 | 처리 |
|---|---|
| CONFIRMED | 노출 반영, critical 허용 조건 충족 가능 |
| DENIED | 해당 위험 하향(삭제 아님 — "현재 노출 없음" 보호 요인) |
| UNKNOWN | risk_level 상한 **warning**, 발현 형태 2~3개 조건부 제시("현재 해당 활동을 하고 있다면"), critical 금지 |
| NOT_APPLICABLE | 해당 위험 스킵 |

### 5-2. critical 필수 조건 (전부 동시 충족)

```text
occurrence 높음 AND impact 높음 AND exposure = CONFIRMED
AND 독립 신호 계층 2개 이상 (동일 원인 파생은 1개로 계산)
AND 근접 시점 AND protection 낮음 AND confidence 중간 이상
```

사용자 노출 문구는 내부 명칭(critical) 대신 "강한 주의가 필요한 시기"로 변환한다
(건강·법률·재정 영역 특히).

### 5-3. 노출 밴드

| 등급 | 의미 | 노출 방식 |
|---|---|---|
| advisory | 약한 부담·초기 신호 | 참고 |
| watch | 주의 가능성 | 체크 사항 제공 |
| warning | 여러 신호 중첩 | 주요 위험으로 노출 |
| critical | 고영향·고노출·근접 시점 | 최상단 경고 (매우 제한적) |

## 6. 기간 병합·후보 선별 — R2 규격

### 6-1. 병합 (RiskEpisode)

병합 키: `risk_id + cause_signature + domain + exposure_target` — risk_id 단독 금지
(같은 현금흐름 압박이라도 8월=수입 지연 / 9월=계약금 지출 / 10월=가족 비용이면 원인
구조에 따라 분리). 규칙:

- 동일 원인 연속 → 병합, 원인이 크게 바뀌면 episode 분리, 1개월 공백 허용 여부는 파라미터.
- peak는 단순 최고 점수가 아니라 confidence 동반 고려.
- 장기 압박(pressure)과 특정 월 사건 발동(incident_risk)은 별도 표시.

```text
잘못된 출력: 재물 손실 2026-08 / 재물 손실 2026-09 / 재물 손실 2026-10
개선된 출력: 2026년 8~10월 재물 압박 (최대 위험: 9월, 주요 형태: 예상 밖 지출·계약금 문제)
```

### 6-2. 선별 — 긍정·위험 경쟁 금지 + 질문 유형별 min/max 정책

슬롯은 고정값이 아니라 `opportunity_max / risk_min_if_warning / risk_max / recovery_max`
정책으로 정의한다:

| 질문 유형 | 위험 노출 |
|---|---|
| 총운·앞으로 주요 사건 | watch 이상 최대 3건 |
| 특정 도메인 운 | 해당 도메인 최대 2건 |
| 좋은 시기 탐색 | warning 이상만 중단 경고 |
| 위험·주의 시기 질문 | advisory 포함 상세 노출 |
| 택일 | 해당 날짜와 직접 연결된 위험만 |

- 동일 도메인 최대 2건, 서로 다른 원인의 사건은 별도 보존.
- **고위험 강제 보존은 warning 이상이 존재할 때만** — 낮은 위험을 억지로 채우지 않는다
  (항상 나쁜 일이 있는 것처럼 보이는 것 방지).
- 위험도가 기준을 넘으면 긍정 사건 점수와 무관하게 반드시 노출.

## 7. 답변 계약 — R3 규격

warning 이상은 trailing 부록이 아니라 **우선 서술 계약**으로 전달한다(긴 답변 잘림·부록화
방지):

```text
answer_contract:
1. 가장 주의할 시기 (warning 이상 존재 시 먼저 요약)
2. 가능한 위험 형태 (단정 아님 — 발현 형태 2~3개)
3. 근거 (신호 반복·보호 약화)
4. 위험을 키우는 행동
5. 위험을 낮추는 방법 (체크포인트)
6. 회복 시점 (recovery_window)
```

- LLM은 이 구조화 데이터를 문장으로 설명만 한다 — 위험을 새로 추측하지 않는다(절대 원칙 1·2).
- 단정·공포형 표현 가드: prohibited_claims + 기존 StyleRules/PROHIBITIONS 계열 재사용.
- 리포트는 목차 불변 — C-06(주의 시기·리스크)/F-18/RL-05/**Y-09**(감수 62차 추가)에 조건부 부착 + 총평 교차 참조. 보고서 단위 1회 계산 후 (product, domain) owner resolver로 섹션에 partition — 동일 canonicalEpisodeKey 상세 노출은 보고서 전체 1회(중복=결정적 dedup+운영 오류), allowed_years는 정확한 집합(교집합 의미론)으로 필터.
- 목표 프레임: "무서운 시기"가 아니라 **관리할 수 있는 시기**.

### 7-1. 토큰 정책 (2026-07-15 결정)

- **일괄 30,000 상향 보류.** R0~R2는 현행 CALL_LIMITS 유지.
- 위험 데이터는 압축 구조로 shadow 저장. R3에서 실제 위험 블록 토큰 p50/p95 실측 →
  `risk_context_reserve`(1,500~3,000 토큰) 부여 + 초과가 확인된 호출만 개별 상향
  (docs/09 8장 개정 + 사용자 승인 동반).

## 8. 게이트 — 3단계 모드

`risk_engine_config.RISK_ENGINE_MODE` (`RiskEngineMode`):

- `off`: 계산하지 않음 — 기존 출력 **byte-identical** (기본값).
- `shadow`: 계산하되 사용자 답변·리포트·LLM 입력·토큰에 미주입 — 구조화 로그
  (`EventEngineV2.risk_shadow`)/QA 전용.
- `expose`: 선별된 위험만 노출 (R3 배선 전까지 shadow와 동일 동작). 노출 승격 시
  `RISK_ENGINE_EXPOSE_WARNING`/`RISK_ENGINE_EXPOSE_CRITICAL` 세분 게이트 추가 예정.

## 9. 검증 — R4 규격

- 골든 세트: 과거 어려운 사건 + **미발생·노출 없음 데이터 포함**. 라벨 3분리(압박만 /
  사건 발생 / 피해 컸음) + 시도·노출 여부, 발생 월, 체감 강도, 대응 가능성·효과, 발현 형태.
- 지표: 위험 재현율, 경고 정밀도, **고위험 누락률(초기 최우선)**, 심각한 오경고율, 시점
  적중 오차, 기간 겹침률, 도메인 적합도, 중복률, 보호 요인 판정 정확도, 경고 후 행동
  가능성, 긍정·위험 균형, 노출 없음 시 경고 하향 여부.
- 초기: 중대 위험 누락 방지 우선의 shadow 검증. 사용자 노출 전환 시 높은 임계값 적용.

## 10. 로드맵

| 단계 | 내용 | 상태 |
|---|---|---|
| R0 | 규격·타입·사전 초안·엔진 뼈대·shadow 회귀 | 완료(커밋 fe939f8) |
| R0.5 | 위험 사전 감수 및 후보 밀도 검증 | **진행 중** |
| R1 | 6축 점수·보호 분석·exposure·등급 (사전 감수 후) | 대기 |
| R2 | Episode 병합·최대 위험 월·분리 선별(min/max 정책)·risk_family 통합 | 대기 |
| R3 | 답변 계약·표현 가드·토큰 실측·reserve | 대기 |
| R4 | 골든 세트·shadow 비교·임계값 도메인별 조정 | 대기 |
| R5 | 개인화(현실 노출 확장·개인 민감도) | 대기 |

### 10-1. R0.5 절차 (2026-07-15 확정 순서 · 2차 감수 반영)

1. 공통 신호 역할 매트릭스 확정(§3-1) — 완료(targeted_event_shape 포함)
2. 증거 계약(`requiredGroups`/`evidenceContract`) 스키마·엔진 지원 — 완료
3. RawPeriodFacts 대상 provenance(피자극 십성·글자·궁위·자리) — 완료.
   잔여 갭(R1 백로그): 원국 취약 구조, 투간·통근 작동성, 구조 패턴, 성별 의존
   배우자성, 동일 원인의 다계층 반복 추적.
4. 대표 7항목 기준 샘플 개정 — 완료(`RISK_DICTIONARY_REVIEW.md` §1, 확정 대기)
5. 단계별 밀도 리포트(observed/eligible/active) + 10차트 코퍼스 — 완료(기준선·개정
   후 실측, §10-2)
6. 잔여 37항목 일괄 적용 → 재실측 → reviewed:true 전환(사용자 감수)
7. 이후 R1 착수

### 10-2. 밀도 지표·목표 (2026-07-15 감수 2차)

단계 분리: `observed`(룰 1개 이상 매칭) → `eligible`(증거 계약 충족) → `active`
(blocker·특이도 억제 통과, `is_active`) → `exposable`(claimCeiling·등급 통과 — R3).
목표는 raw가 아니라 **active·unique risk family 기준**이다:

```text
active incident / period ≤ 1.5          (p90 ≤ 3 권장)
active unique risk family / period ≤ 3
단일 원인의 활성 family 확산 ≤ 2 (명시적 교차 도메인 연쇄만 3)
incident 항목의 코퍼스 발동률 >40% = 0건 (개별 차트가 아니라 코퍼스 전체 기준,
  일반 코퍼스 목표 20~25% 이하 — 차트 고유의 반복 구조라면 높은 발동률 자체는 오류 아님)
동일 incident 최장 연속 발동 > 기간의 50% = 수동 검토(범용 룰 의심)
vulnerability/pressure >40% = 자동 실패 아님·수동 검토(내부 보조 신호는 별도 관리)
```

발동률 분모 정의: 해당 위험이 1회 이상 활성인 **적용 차트** 기준(리포트에 적용/전체
병기). 재실측 시 평균 외에 p50/p90/최댓값, unique cause atom/period, 특이도 흡수
전후, BLOCKED/MITIGATED/INSUFFICIENT 비율, 상시 발동 항목을 함께 보고한다.

**과소탐지 지표(감수 4차 — 밀도만 최적화 금지)**: reviewed 항목별 양성 fixture
recall = 100%(pytest CI 강제 — 명확 양성·단일 원인 양성·유사 음성 4종·보호 동반),
어려운 사건 골든 recall(R4), 단일 원인 watch 후보 생존율, mitigated 후보 보존율.
목표는 후보 수 최소화가 아니라 **구체 위험은 희소하게, 실제 사건 구조가 충분한
후보는 watch 수준으로라도 반드시 생존**이다.

**다층 중첩 cause 계산**: 같은 관계·같은 대상의 반복은 원인 1개(중첩은 R1
layer_convergence/occurrence 증폭 근거로 보존 — 독립 원인 수를 올리지 않음), 대운
충 + 세운 형처럼 **다른 방식**이 같은 대상을 치면 독립 원인 2개. 파생 태그·
favorability·modifier는 원인의 해석 결과이지 새 원인이 아니다(원시 사실만 수집하는
RawPeriodFacts 설계로 원천 차단). 계층 태그 관계 사실 수집은 R1 백로그.

pressure는 자주 발생할 수 있다 — 개별 빈도보다 연속 기간·도메인 편향을 보고, 노출은
watch 이상 또는 위험 질문에 한정한다(§6-2). "사건보다 압박이 많다"가 목표가 아니라
**구체 사건은 구체 근거가 있을 때만 희소하게 생성된다**가 목표다. 임계값 확정은 기준
차트 1건이 아니라 코퍼스(10~20차트: 신강·신약, 오행 과다·부재, 관계 다·소, 보호
강·약, 골든 사례)의 p50/p90/최댓값·kind별·차트별 상시 발동 분포로 한다.
