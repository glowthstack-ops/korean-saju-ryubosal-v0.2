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

kind별 필수 그룹:

```text
pressure       — polarity·부담 계열 신호만으로 생성 가능(requiredGroups 선택)
vulnerability  — 보호력 저하 + 관련 영역 활성
incident_risk  — event_shape + target_activation 필수, polarity는 증폭 요소
```

건강·안전 도메인은 질병명·사망을 단정하지 않고 **부담 부위와 위험 행동을 경고**하는
방식으로만 저작한다(`prohibitedClaims` + 기존 PROHIBITIONS 계열 준수).

파이프라인: 절대 원칙 5 그대로 — validate(`scripts/validate_dictionaries.py`, 스키마
`RiskMappingFile` 등록·lint `_lint_risk_mapping`) → compile → regression → 배포.

## 4. 타입 계층 (`shared_types/risk_engine.py`)

- `RiskCandidate` — **원자 후보** (단일 `period_key`). R0 산출물. 점수·등급 없음.
- `RiskEpisode` — **병합된 위험 구간** (start/peak/end). R2 산출물. R0에서는 타입만 고정.
  - 원자 후보 생성과 기간 병합의 책임 분리 — R2에서 병합 알고리즘을 독립 교체 가능.
- `RiskScoreComponents` — 6축(전부 0~1 정규화). R1 산출물.
- `ProtectiveFactor` / `RecoveryWindow` — 보호(현재)와 회복(사후)의 분리 타입.
- `ExposureStatus` — CONFIRMED / DENIED / UNKNOWN / NOT_APPLICABLE.
- `RiskLevel` — advisory / watch / warning / critical.

### 4-0. 적격 상태 불변식 (`EligibilityStatus` — 2026-07-15 감수)

blocker/mitigator를 근거로만 남기면 shadow 통계에서 실제 활성 후보처럼 집계된다 —
상태를 분리한다: `matched` / `mitigated` / `blocked` (+`suppression_reasons`).

```text
blocker는 후보 기록을 삭제하지 않는다.
그러나 활성 위험 후보 집계(R2 슬롯·R4 오경고 분모)에서는 제외할 수 있다.
mitigator는 후보를 유지하고 강도를 낮춘다(R1).
recovery는 현재 후보의 적격성이나 점수를 낮추지 않는다.
```

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
- 리포트는 목차 불변 — C-06(주의 시기·리스크)/F-18/RL-05에 조건부 부착 + 총평 교차 참조.
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

### 10-1. R0.5 절차 (2026-07-15 확정 순서)

1. 공통 신호 역할 매트릭스 확정(§3-1) — 완료
2. `minimumEvidence.requiredGroups` 스키마·엔진 지원 — 완료
3. RawPeriodFacts 대상 provenance 보강(피자극 십성 `relationTarget*`) — 완료.
   잔여 갭(R1 백로그): 원국 취약 구조, 용신 canonical 역할 상세, 투간·통근 작동성,
   구조 패턴, 동일 원인의 다계층 반복 추적.
4. 44항목 도메인별 감수표 작성(대표 7항목 기준 샘플 우선 — `RISK_DICTIONARY_REVIEW.md`)
5. 점수 없는 shadow 후보 밀도 리포트(`scripts/risk_shadow_density.py`) — 기준선 실측 완료
6. 오발동 항목 수정 후 reviewed:true 전환(사용자 감수)
7. 이후 R1 착수
