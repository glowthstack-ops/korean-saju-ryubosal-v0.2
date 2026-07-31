# 운 오행 실현도 — 기준선 측정 (0A·0B)

`Luck Element Operability` 착수 전, **무엇이 이미 있고 무엇이 없는지**를 재현 가능하게 고정한다.
코드·테스트 assertion·production 출력은 변경하지 않았다.

```
실행 커밋   a9d037b9cd935535c8b6c5b4f707051812003cf3
활성 플래그  DAEWOON_HWA_MODE=current (미설정 기본값)
            RISK_ENGINE_MODE=off      (미설정 기본값)
production 영향  없음
```

이 문서는 두 층을 **분리해서** 적는다. 후속 구현자가 관측값과 설계 결론을 혼동하지 않게 하려는
것이다.

- **관측** — 실행해서 나온 사실
- **판단** — 그로부터 확정한 개발 범위

---

## 0A. 원국 판정 대조

### 입력

```
1987-08-05 21:00 +09:00 · 서울
→ 丁卯 丁未 丙戌 戊戌
```

명세는 명식만 주어 생년월일시를 역산했다. **21:00 이어야 시주가 戊戌**이며 19:00~20:30 은
丁酉가 된다.

### 관측

| 항목 | source_claim | engine_native | 판정 |
|---|---|---|---|
| 용신 | 水 | 土 | MISMATCH |
| 희신 | 金 | 金 | MATCH |
| 기신 | 土 | 木 | MISMATCH |
| 구신 | 火 | 火 | MATCH |
| 한신 | 木 | 水 | MISMATCH |
| 종격 거부 | true | true | MATCH |
| 신왕식왕 | strong_output | — | NOT_EXPRESSED |

```
강약        56.2 · 中和身强 · borderline=True · confidence=0.1535
오행분포     土 39.1 · 火 37.3 · 木 18.2 · 金 5.5 · 水 0.0
선택 모델    eokbu_normal
```

### 최초 분기점

```
axes   eokbu   → 土  0.1508   ← 채택
       pattern → 水  0.1400
margin 0.0108
```

억부축이 土(식상 설기)를, 격국축이 水(관성)를 1위로 낸다. 출처는 격국축 해석에 가깝다.

엔진은 이 불안정을 **스스로 보고하고 있다**.

```
requires_validation: True
warnings:
  중화 구간: 경쟁 모델 동시 제시, 사용자 검증 필요
  신강약 경계: 점수 56.2가 밴드 경계권 — 용희신 단정 보류
  용신 후보 경합: 상위 후보 점수 차가 작아 사용자 검증 필요
  조후 경계: 조후 후보가 근소 차이로 밀림
```

### 판단

```yaml
classification:
  canonical_role_difference: MODEL_SELECTION_DIFFERENCE
  likely_cause: EOKBU_VS_STRONG_OUTPUT_INTERPRETATION
  school_difference: POSSIBLE_NOT_CONFIRMED
  engine_defect: false

development_policy:
  source_claim_overrides_production: false
  blocks_operability_development: false
  register_for_role_selection_review: true
```

`SCHOOL_DIFFERENCE`로 확정하지 않은 이유는, 출처가 우리 엔진의 pattern axis 와 같은 계산법을
썼다고 확인된 바 없기 때문이다.

**후속 영향** — 명세의 Fixture 3·5·7 이 모두 `水 = 용신`을 전제한다. 현재 엔진에서 水 는
한신이므로, 그대로 쓰면 "용신이 억제됐다"가 아니라 "한신이 억제됐다"가 되어 사례의 의미가
성립하지 않는다. 그래서 실현도 검증은 **출처 역할 지도를 test-only 로 주입한 전용 fixture**로
한다(§P1 이후).

---

## 0B. 기존 resolver 표현 범위

`resolve_branch_hap(pillars, favorability, luck_branches=[...])`

### 관측 1 — 순서 비의존성

```
[酉, 未] → 4건
[未, 酉] → 4건
결과 동일: True
```

### 관측 2 — 공유 노드 卯 (己酉 대운 + 癸未 세운)

```
six          卯戌   tier=conditional  mode=bind     →火
six          卯戌   tier=conditional  mode=bind     →火
half         卯未   tier=none         mode=partial  →木
directional  戌酉   tier=conditional  mode=partial  →金   co_relations=['해:戌酉']
```

- `卯酉冲`이 목록에 **없다**. resolver 소스에는 충 처리가 있으나, `卯未`와의 인과 연결이
  출력에 나타나지 않는다.
- `co_relations`는 방합에만 채워진다.
- `卯戌`이 2건 — 원국 戌 이 일지·시지 둘이라 같은 卯 가 두 관계에 참여한다.

### 관측 3 — 亥卯未 후보 (己酉 대운 + 丁亥 세운)

```
three_harmony 卯未亥  tier=none  mode=transform  →木  royal_included=True
```

`tier=none` 인데 `mode=transform` 이다. 두 필드가 서로 다른 방향을 가리킨다.

### 관측 4 — 상태 이력

```
resolve_branch_hap 이 이전 변환 상태를 입력받는가: False
```

매번 재계산한다. 대운에서 형성된 변환을 세운의 충이 해제하는 경로가 **입력 자체에 없다**.

```yaml
before:   {original_element: WATER, resolved_element: WOOD, transform_state: TRANSFORMED}
incoming: {type: CLASH, relation: SI_HAI}
after:
  current_existing_output: BLOCKED_OR_NONE
  can_express_reversion: false
  missing_state: TRANSFORMATION_REVERSED
```

### 판단

| | 결론 |
|---|---|
| 순서 비의존성 | **신규 구현 불필요** — 이미 성립. 회귀로만 고정 |
| 공유 노드 경쟁 관계 표현 | 신규 필요 |
| tier/mode 의미 정규화 | 신규 필요 (관측값 병기부터) |
| 상태 이력 | 신규 필요 |
| `TRANSFORMATION_REVERSED` | **진짜 신규** — 기존 blocked/partial/none 조합으로 간접 표현되지 않는다. 상태 이력이 없어서다 |

P1-b(상태 이력)가 P1-c(환원)의 선행조건임이 측정으로 확인됐다.

---

## 卯戌 2건 — 중복 제거 대상이 아니다

원국 戌 이 둘이므로 서로 다른 **관계 인스턴스**다.

```
natal.year.卯 ↔ natal.day.戌
natal.year.卯 ↔ natal.hour.戌
```

하나로 지우면 궁위·위치 근거가 사라지고, 둘을 독립 원인으로 전량 가산하면 과대계산이 된다.
세 층을 분리한다.

```
relation_family    six_harmony:卯戌
relation_instance  위 두 건 — 보존
shared_node        natal.year.卯
```

**"卯 가 두 번 소모된다"로 모델링하지 않는다.** 지지가 관계에 참여할 때 물리적 소모가 일어나는
것이 아니므로, 공유 노드와 **상충하는 결과 방향을 평가하는 문제**로 표현한다.

---

## 후속 범위

```
P1-a  shadow 관계 그래프
      노드·엣지·링크 생성, 공유 노드·경쟁 방향·잠재 차단 링크
      기존 resolver 출력 불변(byte), co_relations 재사용 금지 — 신규 필드
      링크 이름은 결과 확정형(BLOCKED_BY)이 아니라 POTENTIALLY_* 로 시작

P1-b  상태 이력 (최초 정체성 → 결합 후보 → 변환 → 방해 → 해제 → 환원)
P1-c  TRANSFORMATION_REVERSED
P2    실현도 (뿌리·간접생조·생조원 충·절각·12운성·복합조건 cap)
P3    이벤트·풀이 연결
P4    외부 현실조건 (narrative-only)
```

### P1-a 에서 아직 하지 않을 것

```
어느 합이 최종 승자인지 결정
卯酉冲이 실제로 卯未를 차단했다고 확정
tier=none / mode=transform 의미 변경
이전 층 resolved_element 보존 · 변환 해제 · 환원
effective_quality 계산 · 생산 점수 반영
```

`tier=none, mode=transform` 은 기존 필드를 고치지 않고 관찰값만 병기한다.

```yaml
existing:
  tier: none
  mode: transform
normalized_observation:
  transformation_intent: present
  transformation_completion: unconfirmed
  semantic_conflict: true
```

---

## 별건 등록

**경계 명식의 용신 모델 선택 감수** — 이 사례를 자료로 등록한다.

```
중화신강 · borderline · confidence 0.1535 · requires_validation
eokbu 0.1508 vs pattern 0.1400 (margin 0.0108) · 조후 후보도 근소 탈락

질문: 단일 용신을 확정할 것인가 / 복수 후보를 유지할 것인가 /
      구조 라벨을 타이브레이크에 쓸 것인가
```

이 감수 결과를 기다리느라 실현도 개발을 막지 않는다.
