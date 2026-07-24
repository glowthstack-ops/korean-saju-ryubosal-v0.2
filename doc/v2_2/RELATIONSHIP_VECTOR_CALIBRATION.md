# 관계 효과 벡터 캘리브레이션 명세 — P2-0 (RELATIONSHIP_EVENT_SYSTEM 부록 D)

> **status: spec_only.** P2-0은 코드·계수를 바꾸지 않는다. 이후 민감도 분석(P2-1)이
> 설계 원칙을 침범하지 않도록 **조정 가능한 값과 변경 금지 규칙의 경계**를 고정하는
> 단계다. 실제 값 변경은 P2-1 이후, 런타임 profile 전환은 P2-4에서 한다.

**최종 승인 문장(고정)**:
> P2는 activation·stability·separation_pressure 3축의 상대 강도와 band를 캘리브레이션한다.
> evidence 정밀도, 독립 root 정의, 중복 억제, 근거 없음의 상태 표현, event independence 및
> production delta 0은 변경하지 않는다. P2 결과는 shadow-only이며 P3 증거 계약 승인 전
> 후보 생성·점수·순위에 사용하지 않는다.

파라미터 레지스트리(기계 판독): `relationship_vector_calibration_spec.v1.json` (spec_only —
런타임 loader가 읽지 않는다).

---

## 1. 목적과 비목적

### 목적
같은 관계 구조에 대해 root 수·relation kind·modifier가 7축 중 **평가 가능한 3축**에
일관되고 과대하지 않게 반영되는지 검증하고, 의미상 적절한 **상대 강도와 band**를 결정한다.

### 비목적 (P2에서 하지 않는다)
- legacy relation delta 재현·상관계수 최대화
- legacy cap +22와 신규 strong band 일치
- legacy candidate 생성률에 벡터 분포 맞추기
- new_relationship 사각지대를 계수로 보정
- marriage_signal 양수 delta에 신규 stability 맞추기
- 후보 생성·점수·순위 연결(P3 이후)

> P1-7은 legacy의 구조 압축·coverage 차이를 **관찰**한 것이지 legacy를 정답 라벨로
> 제공한 것이 아니다(HANDOFF §C·§E). legacy 일치는 P2의 목적 함수가 아니다.

---

## 2. 현재 평가 가능 축 — P2 범위 제한

P2 캘리브레이션 범위는 evidence adapter가 실제 수치 평가 가능한 **3축**으로 제한한다.

```
activation
stability
separation_pressure
```

나머지 4축은 **P2에서 수치화·임시 계수 부여 금지**. P3 증거 계약 전까지 기존 상태 유지:

```
exposure            → status = INSUFFICIENT_EVIDENCE / value = None
realization         → status = INSUFFICIENT_EVIDENCE / value = None
experience_valence  → status = INSUFFICIENT_EVIDENCE / value = None
formalization       → status = INSUFFICIENT_EVIDENCE / value = None
```

> P2는 activation·stability·separation_pressure 3축의 캘리브레이션 단계다. 나머지 4축의
> evidence contract와 수치화는 P3 이후 별도 단계에서 다룬다.

---

## 3. 조정 가능 파라미터 (현재값 — `_effect_vector.py` SSOT)

| ID | 현재값 | 후보 탐색 범위 | 비고 |
|---|---|---|---|
| `same_root.secondary_factor` | 0.3 | 0.0 / 0.15 / 0.3 / 0.45 / 0.6 | 같은 root 최강 + 나머지×factor. 적용 **구조 불변** |
| `activation.band` | strong 20 / mod 12 / weak 6 | profile 안1~4(§C) | raw value와 band **분리**, bump 필수 |
| `activation.kind_strength` | dict base_bonus(HAP7·CHUNG10·HYEONG8·PA6·HAE4·BOKEUM5) | 감수·민감도 | 순위 바꿔도 activation≠길흉·성사 의미 유지 |
| `stability.support_weight` | HAP 0.3 | ≥0 | support 방향 고정 |
| `stability.pressure_weight` | CHUNG1.0·HYEONG0.8·HAE0.6·PA0.6 | ≥0 | pressure 방향 고정, `stability=support−pressure` |
| `stability.band` | weak≤−0.8 / mod<0.3 / strong | 감수 | signed band |
| `separation.pressure_weight` | CHUNG1.0·HYEONG0.6·HAE0.55·PA0.55 | ordering 제약(§E) | CHUNG≥나머지 유지 |
| `separation.band` | strong0.9 / mod0.55 / weak0.3 | 감수 | — |
| `modifier.jaenghap_support_weaken` | 0.5 | 감수·민감도 | 유일한 수치 modifier(§F) |
| `cross_root.synthesis` | 단순 합산 | **조건부 검토**(§G) | P2-0 확정 대상 아님 |

### 활성화 band 후보 profile (§C — 임의 조합 아닌 profile 단위 비교)
```
안 1:  6 / 12 / 20   (현재)
안 2:  6 / 15 / 24
안 3:  8 / 16 / 26
안 4: 10 / 18 / 28
```

### secondary_factor 탐색 범위 근거
`0.0` = 최강 relation만(기준선). `0.6` 이상 = 동일 root를 사실상 복수 원인처럼 계산할
위험 → 초기 탐색 상한.

### modifier 수치화 정책 (§F)
- **수치 조정 가능**: `jaenghap_support_weaken`(쟁합의 binding support 약화율)만.
- **수치화 금지·보수 유지**: 합거(blocker)·합반(delay/incompleteness)·관살혼잡(selection
  complexity)·multi-relation stress(focus dispersion) — 수치 근거 없는 임의 penalty 금지.
  메타데이터/blocker로만 유지.

### cross-root 합성 (§G — 조건부)
현재 서로 다른 root contribution을 단순 합산. P2-0에서 변경 확정하지 않고 검토 후보로 둔다
(단순 합산 / 완만한 감쇠 합산 / 상한 없는 합산 + band만 조정). 단 아래는 고정:
```
서로 다른 exact/component root > 동일 root 내부의 복수 kind
root가 늘수록 값이 감소하는 결과 금지
```

---

## 4. 변경 금지 불변식 (P2-0 핵심 산출물)

### Evidence 정밀도
```
EXACT > COMPONENT > PROVISIONAL
```
- superseded 잠정 evidence는 숫자 기여 금지
- PROVISIONAL은 retained·unresolved 계측만
- PROVISIONAL만 존재하면 수치 축 생성 금지

### Root 정의
```
독립 원인 수 = independent_root_trigger_count
```
- evidence count·semantic group count와 혼용 금지
- 동일 `signal_trigger_id` = root 1개
- RP와 MT2가 같은 운 글자 공유해도 root 1개
- stem과 branch가 다른 signal이면 root 2개

### 같은 root의 기여
- 동일 kind 중복은 1회만
- 다른 kind는 제한 복합 보정만(완전 단순 합산 금지)
- 입력 순서 불변 · duplicate 추가 시 결과 불변

### AxisStatus
```
근거 없음 → value=None → INSUFFICIENT_EVIDENCE
support와 pressure 실제 상쇄 → EVALUATED → value=0
```
- 근거 없음과 0 혼동 금지
- blocker-only는 BLOCKED 아니라 INSUFFICIENT_EVIDENCE
- positive base 없는 상태에서 BLOCKED 생성 금지

### Modifier
- modifier만으로 activation 생성 금지
- `affects_axes` 밖 축 변경 금지
- root-scoped modifier는 참조 root에만 적용
- multi-root scope 불명·static conflict 시 수치 적용 보류
- natal static 반복 비누적 · modifier는 root 수에 기여 안 함

### 의미 분리
```
activation ≠ stability ≠ realization ≠ formalization
stability ≠ separation_pressure
```
- 충·형으로 experience negative 확정 금지
- 합으로 commitment/formalization 확정 금지
- relation activation으로 candidate 자동 생성 금지

### Event independence
- 벡터는 event-independent
- family(new_relationship·relationship_change·marriage_signal)별 legacy 값 역주입 금지
- candidate 존재 여부가 벡터 생성 조건이 아님

### Production 불변 (P2 전체 shadow-only)
```
score/raw/confidence/rank/Top-N/candidate 생성·억제/risk·guard/LLM·report payload delta = 0
```

---

## 5. 의미 단조성 계약 (P2-1 진입 전 고정 — 계수값 무관 유지)

**비감소(non-decreasing)** 계약이다. "반드시 크게 증가"는 고정하지 않는다(secondary_factor=0이면
같은 root 추가 kind가 activation을 안 늘릴 수 있음).

```
negative relation 추가        → stability 더 좋아지지 않음
negative relation 추가        → separation_pressure 낮아지지 않음
동일 root 추가 relation kind   → activation 비감소 & 완전 독립 합산보다 작음
서로 다른 exact root 추가      → activation 비감소
쟁합 추가                     → 합의 stability support 증가하지 않음
duplicate evidence 추가        → 값·band·root 수 불변
입력 순서 변경                → serialized vector 동일
```

---

## 6. 평가 데이터 계층 (역할 분리 — 합산·혼용 금지)

| 계층 | 역할 | 정답 라벨? |
|---|---|---|
| **불변식 fixture** | 기계적 통과 필수(supersession·duplicate·순서·충+형·서로 다른 root·MT2-only·합 단독·blocker-only·modifier-only·net0·static 반복·multi-root 보류) | — |
| **결정적 harness 331** | 계수 전후 분포·root별 값·kind 조합 band·경계 사례·legacy 구조 차이 참고 | **아님** |
| **production coarse** | 실제 root 분포·strong 비율·unresolved·OTHER_BOUNDED·후보 부재 대리 지표 | 아님(현 22기간=배선 검증만, 캘리브레이션 근거 아님) |
| **사람 감수 표본**(P2-3) | 대표·경계·파라미터 민감·ordering 의심 사례 30~50건 | 판단 기준 |

> deterministic·production 분모를 합치지 않는다(HANDOFF §0·§11).

---

## 7. 민감도 분석 계획 (P2-1)

각 파라미터 조합에서 측정할 metric:
```
단일 root vs 복수 root 분리도
relation kind 조합별 ordering
strong 비율
root=1이 과도하게 strong이 되는 비율
root 수 증가에 따른 증가량
stability support/pressure 상쇄 분포
separation pressure 포화 여부
fixture 순위 역전 여부
```
탐색: secondary_factor {0.0/0.15/0.3/0.45/0.6} × activation band {안1~4} × jaenghap_weaken
{0.25/0.5/0.75}. profile 단위 비교(무작위 임계 조합 금지).

---

## 8. 감수 기준 (P2-3)

경계 사례 유형별 대표·경계·반례 30~50건: 단일 root strong / root 2인데 moderate / 합+충 혼합 /
negative stability + high activation / strong vector + 후보 부재 / multi-root + 후보 부재 /
MT2-only / modifier-only. 감수는 "이 상대 강도·band가 관계 구조를 과대·과소 없이 설명하는가"만
판단(길흉·성사·legacy 일치 아님).

---

## 9. Versioning 규칙

```
값·경계 변경 → RELATIONSHIP_CALIBRATION_VERSION bump
구조·의미 변경 → RELATIONSHIP_VECTOR_SCHEMA_VERSION bump
```
**calibration bump 대상**: relation-kind weight·secondary_factor·activation/stability/
separation threshold·modifier coefficient·root 합성 함수·histogram boundary.
**schema bump 대상**: 축 필드 추가·삭제·AxisStatus 의미·RootContribution 구조·telemetry DTO
필드 의미·evidence contract 구조. P2 실험 run은 기존 run과 vector_run_id로 분리(섞지 않음).

---

## 10. P3 연결 금지 조건

P2 종료 전 금지: strong threshold를 후보 생성에 연결 / vector로 candidate 추가·score 가산 /
formalization·separation 후보 승격 / Top-N 반영 / LLM 노출. P3 계약 **문서 초안**은 P2와 병렬
가능하나(taxonomy·positive evidence 종류·blocker/modifier 역할·필요 증거 수·금지 단정 문구),
production/shadow **후보 승격 구현은 P2-4 이후**.

---

## P2-0 완료 게이트

```
[x] P2 범위 = 평가 가능 3축 제한(§2)
[x] 조정 가능 파라미터 ID 단위 열거(§3·레지스트리)
[x] 현재값과 후보 탐색 범위 분리(§3)
[x] 변경 금지 불변식 명문화(§4)
[x] legacy 일치가 목적 함수 아님 명시(§1·§4)
[x] fixture/harness/production/감수 역할 분리(§6)
[x] 단조성 계약 고정(§5)
[x] P3 후보 생성·승격 연결 금지(§10)
[x] spec_only(runtime 미판독) — 레지스트리 status=spec_only
[x] calibration/schema bump 규칙(§9)
[x] P2-1 metric 정의(§7)
[x] 코드·점수·payload delta 0(문서만)
[ ] 문서 lint·기존 suite clean(커밋 게이트)
```

다음: **P2-1 민감도 분석** — 위 파라미터 조합을 결정적 harness·불변식 fixture에 걸어 §7
metric을 측정한다(계수 변경은 실험 run으로만, 운영 반영 아님).
