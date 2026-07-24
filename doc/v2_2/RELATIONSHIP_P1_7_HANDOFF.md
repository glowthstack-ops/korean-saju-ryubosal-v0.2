# P1-7 관찰 지도 — 벡터 ↔ legacy 비교 handoff (2026-07-24)

> **감사 결과 보고서. 수정 지침이 아니다.** P1-7의 산출물은 "신규 P1 벡터가 legacy보다
> 우수하다"는 결론이 아니라, **어디서 일치하고·어디서 cap이 정보를 지우고·어떤 event key가
> 구조를 소비하지 않고·어디서 후보가 생성되지 않고·어디서 방향 의미가 혼합되고·어디는 P1
> 근거가 부족해 보류해야 하는가**의 관찰 지도다. 실제 수정은 P2(벡터 캘리브레이션) 또는
> P3(증거 계약·후보 승격)에서 **별도 승인**으로 진행한다. 본 감사 전 구간에서 score·rank·
> candidate·Top-N·LLM/report/risk payload delta = 0.

## 0. 두 관측 경로 — 분모를 합치지 않는다 (§9·§11)

| 경로 | 목적 | 분모 | 상태 |
|---|---|---|---|
| **Deterministic harness**(`scripts/audits/relationship_p1_7/`) | 구조·원인 **재현** — exact 벡터 + legacy 후보 전량 | fixture 6종 · record 331건 | 완료 |
| **Production coarse aggregate**(`cmp.prod.v1`) | 재현된 현상이 실제 요청 분포에 **얼마나 자주** 나타나는지 대리 지표 | 라이브 요청(관측 기간) | 배선 완료 · **표본 축적 대기** |

> fixture는 확률 표본이 아니라 구조 재현용이다. `deterministic 331건 + production N건 = 총 표본`
> 식의 합산은 금지한다(§11). deterministic이 현상을 재현하고, production coarse가 그 현상의
> 관측 가능한 대리 지표 빈도를 확인한다.

---

## A. 확정된 구조적 관찰 (deterministic — 재현 가능)

331 record 기준. 중첩 독립 finding은 primary_class 하나가 가리는 복합 현상을 보존한다
(합계 ≠ record 수).

### A-1. legacy cap 포화 — 단일 root부터 압축

매트릭스 A(Root 수 × cap): root=1에서 이미 cap 34건, root=2에서 19건.

> legacy cap 22는 **복수 root의 복합성만 압축하는 것이 아니다.** 단일 root 안에서도 relation
> kind·원시 강도가 강한 사례를 동일한 +22로 포화시킨다(root=1 cap 34건이 입증). primary class
> `LEGACY_CAP_SATURATED`는 28건이지만 독립 finding `cap_saturated`는 53건 — **25건은 다른
> primary(방향 혼합·부재 등) 뒤에 가려져 있었다.** 이는 event-independent 구조 벡터의 필요성을
> 뒷받침하는 강한 관찰이다.

### A-2. event family 신호 소비 비대칭 (coverage gap)

primary `legacy_event_key_blind_spot` 41건 · 독립 finding `legacy_event_key_coverage_gap` 135건.

> 동일 기간·구조에서 일부 family만 relation 신호를 소비한다(매트릭스 B: kind combo별 family
> 생성 수 비대칭). **이것이 의도된 사건별 계약인지 구현 사각지대인지는 이 단계에서 판정하지
> 않는다** — P3 증거 계약 검토 대상. 명칭을 "blind spot"으로 확정하지 않고 "coverage gap"으로
> 중립 서술하는 이유(§5-2).

### A-3. 활성과 유지 품질의 legacy 단일 스칼라 압축

독립 finding `negative_stability_with_positive_delta` 88건. 매트릭스 C에서 `stab=negative/
sep=evaluated` 축인데 legacy delta가 capped_22·high로 나타나는 분포.

> **오류 확정이 아니다.** legacy relation delta는 관계의 **활성·변화 가능성**을 올리는 단일
> 양수값이고, P1 벡터는 activation(변화 강도)과 stability(유지 품질)를 **분리**한다. 따라서
> `positive legacy delta + negative stability`는 즉시 모순이 아니라 "관계 변화는 강하지만 유지
> 압력은 불리"의 동시 성립일 수 있다. 이 현상은 **legacy 단일 스칼라에 활성과 관계 품질이 함께
> 압축된 것**으로 기술한다(방향 오류가 아니라 의미 압축).

### A-4. 벡터 존재 · 후보 미생성

primary `legacy_candidate_absent` 107건 · 독립 finding `all_candidates_absent` 57건 ·
`strong_activation_candidate_absent` 15건 · `multi_root_candidate_absent` 22건.

> 벡터는 관계 구조 활성을 관측하는데 legacy ten-god branching이 사건 후보를 만들지 않은 기간.
> **오류가 아니다.** 가능한 원인은 복수: legacy branching의 의도된 gate / event-key별 신호 소비
> 공백 / P1 activation 범위가 사건 후보보다 넓음 / 관계 변화는 있으나 특정 사건 승격 근거 부족 /
> fixture 구성이 미생성 조건을 상대적으로 많이 포함. **원인은 미확정 — P3 증거 계약·후보 승격
> 검토로 전달.**

### A-5. P1 미평가 축은 여전히 판단 불가

exposure·realization·experience_valence·formalization은 P1에서 평가하지 않는다. **0으로
비교하지 않고** `INSUFFICIENT_EVIDENCE` 분포만 감사한다. 이 축들에 대한 판정은 P3 증거 계약
이후에만 가능하다.

---

## B. Production coarse 관찰 (cmp.prod.v1 — 배선 완료, 표본 대기)

라이브 경로는 `relation_delta = None`이라 **delta·cap 의존 분류를 만들 수 없다.** 확정 가능한
관측만 집계한다(§6·§7).

### 관측 가능 (COARSE)
- 벡터 coverage: activation/stability/separation status·histogram, root bucket, kind combo,
  unresolved bucket
- 관계 후보 coverage: 전체 유무 + family별(new_relationship·relationship_change·marriage_signal) present/absent
- P3 우선순위 신호: `vector_present/strong/multi_root_all_candidates_absent`(중첩 카운터)
- P2 캘리브레이션 신호: strong 비율·negative stability 비율·separation evaluated 비율·
  OTHER_BOUNDED 비율·unresolved 비율

### 관측 불가 (production에서 생성 금지)
`LEGACY_CAP_SATURATED` · `LEGACY_EVENT_KEY_BLIND_SPOT` · `REVIEW_REQUIRED_DIRECTION_MISMATCH` ·
`ALIGNED` · `LEGACY_ONLY_SIGNAL` — 전부 delta·cap 의존. `relation_delta=None`을 delta=0·
uncapped·negative·candidate absent 중 어느 것으로도 해석하지 않는다. audit 결손(JOIN_*/
PROJECTION_FAILURE)은 `not_observable`로 분리하고 부재로 집계하지 않는다(§9).

### 상태
```
production aggregate wiring   = 완료 (chat 배선 · 실 스모크 observed=22)
production empirical validation = 표본 축적 대기 (§11)
```

> deterministic harness에서 재현한 현상이 실제 요청 분포에서도 의미 있는 빈도로 나타나는지를,
> 표본이 쌓인 뒤 이 coarse aggregate로 확인한다.

---

## C. P2 전달 — 벡터 캘리브레이션 (벡터 자체만)

P2는 **벡터 값 분포만** 조정한다. 후보·점수·cap은 건드리지 않는다.

- `SECONDARY_FACTOR 0.3`(root 보조 기여 계수)
- activation band 경계 `6/12/20`
- stability support/pressure 가중
- separation 서열 가중(충 1.0 / 형 0.6 / 해·파 0.55)
- root 수 증가에 따른 activation 값 분포(매트릭스 A의 root별 분포 참조)
- kind combo별 band 분포(매트릭스 B·C)
- strong activation 비율(coarse aggregate B에서 확인)

근거: A-1(단일 root 압축), A-3(활성/품질 분리 분포), C 매트릭스.

---

## D. P3 전달 — 사건 증거 계약·후보 승격

P3는 **후보 생성 공백과 증거 계약**을 다룬다.

- candidate absent (A-4) — 벡터 활성인데 후보 미생성: 증거 계약으로 승격 조건 정의
- family coverage gap (A-2) — event-key별 신호 소비 비대칭: 의도된 계약 vs 사각지대 판정
- 관계 활성과 formalization 분리 — activation이 결혼 의미로 소비될 때 별도 품질 증거 요구 여부
- negative stability + marriage_signal 병존 (A-3) — 결속 확정 의미 family에 대한 방향 증거
- positive realization evidence — 현실 접촉·성사 증거 계약(P1 미평가 축)
- commitment/formalization evidence — 결속·공식화 증거(P1 미평가 축)
- distancing/separation evidence — 종료 압력 증거의 현실 marker

근거: A-2·A-4·A-5.

---

## E. Legacy 별도 기술 부채

cap 자체는 P2 벡터 캘리브레이션·P3 증거 계약만으로 완전히 해결되지 않을 수 있다. 아래는 별도
migration/compatibility 과제로 표시한다.

- `legacy relation cap 22`(`relation_palace_engine._MAX_RELATION_DELTA`) — 구조 정보 소실원
- event family별 delta 소비 차이(매트릭스 B)
- legacy 후보 랭킹·점수 호환성 유지 여부(cap 제거 시 회귀 범위)

> 이 과제는 P1 벡터가 shadow에서 승격되는 시점(P4 이후)에 legacy 파이프라인 변경과 함께
> 검토한다. P1-7 단계에서는 **관찰만** 기록한다.

---

## F. 완료 게이트 판정

### P1-7 감사 게이트 (16항)
P1-6 결과 읽기 전용 비교 · 비교 과정 delta 0 · 기간·family·축 분리 · evidence≠root ·
delta≠activation 동일 척도 취급 안 함 · cap 후보/기간 분리 · candidate absent 비오류 ·
event-key gap family별 분리 · direction mismatch 보수 분류 · P1 미평가 축 0 비교 금지 ·
deterministic/production 분리 · 별도 allowlist DTO · PII·간지·trigger·evidence ID 미노출 ·
성별/일간 음양 stratification · LLM·리포트·가드 미노출 · ruff·mypy·suite clean → **전항 충족**.

### P1-7d-lite coarse aggregate 게이트 (15항)
production COARSE만 · relation_delta None을 0으로 변환 안 함 · delta·cap 의존 class 0건 ·
audit 결손 비-absent(not_observable 분리) · 전체 부재 vs family별 부재 분리 · 부재 비오류 ·
strong·multi-root 부재 중첩 보존 · axis insufficient는 value bucket 미포함 · deterministic·
production 분모 분리 · 별도 `cmp.prod.v1` allowlist · P1-6 telemetry 의미 불변 · PII·간지·
period identity·trigger ID 미노출 · score·rank·candidate·Top-N delta 0 · LLM·report·risk
payload 미노출 · ruff·mypy·suite clean → **전항 충족**.

**P1-7 종료.** 다음 관계 이벤트 작업은 P2(캘리브레이션)·P3(증거 계약)로 분기하며, 각각 본
handoff의 C·D 섹션을 착수 근거로 별도 승인받는다.
