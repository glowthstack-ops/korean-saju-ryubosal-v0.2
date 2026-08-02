# 활성도 해상도 종료 감사 (CAL-ACTIVATION-RESOLUTION-01c)

```yaml
candidate_selected: B
consumption_contract: WITHIN_LEVEL_ORDERING

newly_distinguishable_targets: 52
newly_orderable_pairs: 3107

activation_level_changes: 0
schema_changes: 0
cross_axis_comparisons: 0
double_weighting_paths: 0
production_diffs: 0

activation_resolution_contract: PASS
p2_shadow_readiness: PASS
p3_consumption_validation: NOT_YET_STARTED

overall: PASS
scope: P2_ACTIVATION_RESOLUTION_CONTRACT
```

```
code_under_test   e80d735   (clean tree · 네 실행 종료까지 수정 없음)
```

---

## 1. 감사 overlay 가 아니라 production helper 로 확인했다

후보 투영으로 확인하면 "계약이 실제로 작동하는가" 가 아니라 "감사 코드가 같은 답을 내는가" 를
재게 된다. `e80d735` 의 `build_axis_activation_resolution` ·
`compare_same_axis_resolution` · `activation_resolution_order_key` 를 312 target 에 직접
돌렸다.

```
targets                 312
FULLY vs OPERABLE 쌍   3107   전부 정렬 가능
root-depth migrated      52   전부 order key 생성
UNKNOWN order key 없음    2   정렬 대상 제외(설계대로)
cross-axis 비교          런타임 거부 — CROSS_AXIS_COMPARISON_PROHIBITED
```

---

## 2. R0~R3 재실행

호출부가 없어도 production 패키지에 새 모듈이 늘었으므로 import 부작용·플래그 조합별 로딩
차이까지 포함해 다시 고정했다.

```
R0  graph=F state=F oper=F   exit 0
R1  graph=F state=T oper=F   exit 0
R2  graph=F state=F oper=T   exit 0
R3  graph=T state=T oper=T   exit 0
```

### 증명 범위

```
증명한다      네 플래그 조합에서 기존 생산 회귀 전건 통과
              shadow ON/OFF 에서 production 불변 회귀 통과
              새 모듈 import 부작용 0 · production 호출부 0 · schema 변경 0
증명하지 않는다  각 요청의 R0/R3 런타임 결과를 외부 fingerprint 로 직접 대조
```

editable 설치가 메인 저장소를 가리키므로 detached worktree 를 쓰지 않았다.

---

## 3. 방어 계약

```
cross-axis 비교 성공                0
status-anchor 불일치 수용            0
UNKNOWN order key 생성              0
NONE 의 operability anchor 소비      0
structural_tension 적용             0
산술 합산·곱셈 소비                  0
```

### `double_weighting_paths: 0` 의 의미

**"향후 어떤 코드도 절대 이중 가중하지 못한다" 는 증명이 아니다.** 현재 제공된 공식 소비
인터페이스로는 산술 소비가 불가능하다는 증명이다.

```
정렬 helper 가 스칼라를 반환하지 않음   (level_rank, within_level_anchor) 튜플
숫자 덧셈·곱셈 인터페이스 없음          심볼 검사 회귀
production callsite 없음
```

`activation_anchor` 와 `operability_anchor` 는 같은 P2 상태의 두 해상도이므로 함께 계산하면
같은 것을 두 번 센다. 허용되는 소비는 정렬 키뿐이다.

### 동일 source 의 favorable + mitigation 이중 소비

**이 슬라이스에서 강제하지 않았다.** 한 사건에서 두 축 중 하나만 고르는 규칙은 이벤트 매핑
계약이지 ordering helper 의 책임이 아니며, P3 이벤트 사전이 어느 축을 소비하는지 정해져야
강제할 수 있다. P3 착수 시 게이트로 둔다.

---

## 4. verdict 를 범위별로 분리

```yaml
production_nonregression: PASS
root_depth_semantics: PASS
relation_identity: PASS

activation_resolution_contract: PASS        # B 계약을 타입·정렬 규칙·가드로 고정
activation_resolution_measurement: PASS     # 52건 · 3107쌍 재현
activation_resolution_integration: NOT_YET_EXERCISED   # 소비하는 곳이 없다

semantic_distribution: PASS
p2_shadow_readiness: PASS

p3_consumption_validation: NOT_YET_STARTED
```

하나로 두면 "계약이 닫혔는가" 와 "실제로 소비돼 검증됐는가" 가 섞인다.

### `semantic_distribution: PASS` 의 근거

```
관계 참여만으로 발생한 UNKNOWN 해소          9cd3722
RootDepth 최고등급 과잉 자격 해소            ce90c32
FULLY/OPERABLE 해상도 손실 → 등급 내부 ordering 으로 해결   e80d735
UNKNOWN 원인 전량 설명
production 불변
```

**`FULLY` 비율이 50.3% 라는 사실 자체는 PASS 근거가 아니다.** 이 판정의 의미는 "관측 분포에서
발견된 알려진 의미론 결함과 해상도 손실이 현재 P2 계약 안에서 해소됐다" 이지, 실제 사용자
트래픽 분포가 이상적이라는 뜻이 아니다.

---

## 5. 상위 진행 상태

```
P1                         PASS
P2                         PASS
CAL-ROOT-DEPTH-01          PASS
CAL-ACTIVATION-RESOLUTION  PASS
P3                         NOT_YET_STARTED

program_overall            INTEGRATION_PENDING
```

`PASS_WITH_REVIEW` 가 아니라 `INTEGRATION_PENDING` 이다. 남은 것은 P2 의미론에 대한 검토
결함이 아니라 **아직 시작하지 않은 다음 계층의 통합 검증**이다.

> This verdict does not validate downstream P3 event consumption.

---

## 6. P3 착수 시 필요한 게이트

```
P3 가 ordering helper 만 사용하는가
anchor 를 점수에 더하거나 곱하지 않는가
같은 사건에서 favorable·mitigation 을 중복 소비하지 않는가
서로 다른 축을 하나의 스칼라로 비교하지 않는가
```

---

## 7. 다음 순서

```
coverage-only 코호트로 R41 도달성 확인
CAL-ROLE-BORDERLINE-01
P3 이벤트·풀이 연결
```

`RISK-LEASE-REVALIDATION-01` 은 현재 fail-closed 상태를 유지한 채 별도 운영 트랙으로 남는다
(`PAID_RUN_NOT_APPROVED` · 무과금 identity preflight 선행).

---

## 재현

```bash
cd backend
python scripts/audits/measure_luck_element_operability_shadow.py \
  --out artifacts/audits/luck_element_operability \
  --ablation activation-resolution-candidates-v1 --with-suite
```

계약 검증은 `tests/unit/test_activation_resolution.py` 22건이 회귀로 고정한다.
