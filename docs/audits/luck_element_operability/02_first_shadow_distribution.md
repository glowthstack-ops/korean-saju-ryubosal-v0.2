# 운 오행 실현도 — 첫 shadow 분포 (P2)

```
실행 커밋   9cd3722 (+ 본 사이클의 shadow 배선 결함 수정)
스크립트    backend/scripts/audits/measure_luck_element_operability_shadow.py
production 영향  없음 — 플래그 3종 모두 기본 OFF
```

## 판정

```yaml
production_nonregression_verdict: PASS
semantic_distribution_verdict: PASS_WITH_REVIEW
overall_verdict: PASS_WITH_REVIEW
```

두 축을 분리한다. 생산 비회귀는 R0~R3 매트릭스로 닫혔고, 분포 쪽은 **뿌리 판정이 과도하게
관대**해 검토가 남는다(§9). 전체 verdict 는 `CAL-ROOT-DEPTH-01` 이 닫힌 뒤 올린다.

---

## 1. 모집단

세 코호트를 분리했다. 기존 fixture 는 경계·회귀 사례가 과대표집돼 있어 서비스 사용자
분포가 아니다. 이 문서의 비율은 **existing-fixture shadow distribution** 이다.

```
A 생산 비회귀   기존 회귀 스위트 전체 × R0~R3       ← 전건 통과 (§1-1)
B 분포          고유 적격 입력만                    ← 아래 수치의 모집단
C 의미론 골든   규칙 의도 확인. 비율에 넣지 않음     ← 기존 회귀 스위트가 담당
```

### 1-1. A 코호트 — R0~R3 매트릭스

```
R0  graph=F state=F oper=F   exit 0
R1  graph=F state=T oper=F   exit 0
R2  graph=F state=F oper=T   exit 0
R3  graph=T state=T oper=T   exit 0
```

각 조합은 env 를 명시 주입한 subprocess 로 실행했다 — 현재 셸을 오염시키지 않는다.

**detached worktree 를 쓰지 않았다.** `saju_*` 가 메인 리포 경로로 editable 설치돼 있어,
worktree 에서 pytest 를 돌려도 import 되는 코드는 메인 리포의 것이다. 워크트리를 측정한다고
믿으면서 다른 트리를 재게 된다. 트리가 clean 이고 HEAD 가 정확히 `fa66cb1` 이므로 메인
리포에서 실행해 측정 대상과 import 대상을 일치시켰다.

#### 이 매트릭스가 증명하는 것과 아닌 것

```
증명한다     네 플래그 조합 각각에서 기존 생산 assertion 전건 통과
             (period_fortune 응답 byte 동일 · OFF inert · 점수·status·rank 회귀 포함)
             shadow 예외가 생산 요청으로 전파되지 않음
증명하지 않는다  요청별 생산 산출물을 R0~R3 사이에서 직접 byte 비교한 결과
```

스크립트는 실행별 exit code 를 수집하며 요청 단위 fingerprint 를 교차 비교하지 않는다.
생산 불변의 근거는 **스위트 안의 불변 회귀들이 각 조합에서 통과한다는 사실**이다. 요청 단위
직접 대조가 필요해지면 별도 하네스를 만든다 — 지금 있는 것보다 강한 주장을 하지 않는다.

### B 코호트

기존 회귀 파일에서 수집한 고유 명식 13건 × 성별 2 × 기준일 3.

```
총 입력            78
고유 적격 입력      78     (canonical key 중복 0)
비적격             0
평가 target        312    (= 78 × 4, 대운·세운의 천간·지지)
```

canonical key = 원국 4주 + 대운 간지 + 세운 간지 + 성별 + 역할표 버전.

무작위 생성 명식은 넣지 않았다. 규칙 커버리지는 늘지만 비율의 의미가 사라진다.

---

## 2. 측정 중 발견한 배선 결함

첫 실행에서 `support_status` 가 `stable` 과 `absent` 두 값만 나왔다.

```
1차   indirect_generation_stable 179 · absent 131 · disrupted 0 · mixed 0
```

`build_operability_shadow_bundle` 이 `branch_relations=()` 로 프로필을 뽑고 있었다.
생조원 교란 근거가 아예 전달되지 않아 `DISRUPTED`·`PRESENT_MIXED` 로 갈 수 없는 상태였다.
collector 결과를 넘기도록 고치고 재측정했다.

```
2차   stable 136 · absent 131 · disrupted 25 · mixed 18
```

**분포를 재보지 않았으면 드러나지 않았을 결함이다.** 단위 테스트는 프로필 추출기에 직접
관계를 주입해서 통과했고, 배선이 그걸 빼먹은 것을 잡지 못했다.

---

## 3. OperabilityStatus 분포

```
fully_operable       209   67.0%
operable              56   17.9%
weakened              36   11.5%
partially_operable     8    2.6%
unknown                2    0.6%
suppressed             1    0.3%
```

`UNKNOWN` 0.6% — 경고선(전체 10%)을 크게 밑돈다. 정체성 과잉 전파 수정 전에는 관계에 얽힌
글자가 전부 `UNKNOWN` 이었으므로, 이 수치가 그 수정의 실측 확인이다.

---

## 4. 프로필 축 분포

```
root_status
  direct_natal_and_transit_root  181   58.0%
  direct_natal_root               91   29.2%
  direct_transit_root             21    6.7%
  absent                          17    5.4%
  unknown                          2    0.6%

support_status
  indirect_generation_stable     136   43.6%
  absent                         131   42.0%
  indirect_generation_disrupted   25    8.0%
  indirect_generation_present_mixed 18   5.8%
  unknown                          2    0.6%

cut_off_status
  not_applicable                 154   49.4%   (지지 target — 설계대로)
  cut_off_absent                 127   40.7%
  cut_off_present                 29    9.3%
  unknown                          2    0.6%

stage_applicability
  applicable                     156   50.0%   (천간 target)
  not_applicable                 154   49.4%
  unknown                          2    0.6%
```

`stage`·`cut_off` 의 `not_applicable` 154 는 지지 target 156 에서 `unknown` 2 를 뺀
값으로, 구성요소별 적용 규칙이 의도대로 작동함을 보여준다.

---

## 5. 규칙 분포

```
R10_NATAL_AND_TRANSIT_ROOT_CLEAR            163   52.2%
R20_NATAL_ROOT_STABLE_SUPPORT                46   14.7%
R21_NATAL_ROOT_CLEAR                         37   11.9%
R30_TRANSIT_ROOT_CLEAR                       19    6.1%
R11_NATAL_AND_TRANSIT_ROOT_CUT_OFF_WEAK_STAGE 17   5.4%
R42_ROOTLESS_NO_RELIABLE_SUPPORT             12    3.8%
R22_NATAL_ROOT_CUT_OFF_WEAK_STAGE             6    1.9%
R43_ROOTLESS_WITH_SUPPORT                     4    1.3%
R23_NATAL_ROOT_CUT_OFF                        2    0.6%
R00_UNRESOLVED_ELEMENT                        2    0.6%
R12 · R31 · R32 · R40                     각 1    0.3%
```

각 규칙 ID 는 결과 상태가 하나로 고정돼 있다(감산 누적 부재의 구조적 결과).

### 미도달 규칙

```
R41_ROOTLESS_CUT_OFF_WITH_SUPPORT   0건
```

무근 + 절각 + 안정 생조 조합이 이 모집단에 없었다. **주 분포에 인공 사례를 섞지 않는다** —
후속 coverage-only 보충 코호트에서 결정적 사례로 도달을 확인한다.

---

## 6. UNKNOWN 원인 분해

```
R00_UNRESOLVED_ELEMENT   2   resolved_element 미확정
```

전건 설명 가능하며 다음은 **0건**이다.

```
충 참여만으로 UNKNOWN                0
형·파·해 참여만으로 UNKNOWN           0
tier=None 합 후보만으로 UNKNOWN       0
partial·conditional 만으로 UNKNOWN    0
```

`IDENTITY_LOST_BY_DISRUPTION_ONLY` 카운터로 직접 측정했다.

---

## 7. 변환·환원

```
raw_element != resolved_element   20 / 312   6.4%
```

확정 변환이 실제로 일어나며 후속 계층이 원래 오행이 아닌 값을 소비한다.

---

## 8. 불변식

```
invariant_violations   {}
```

측정한 항목:

```
SUPPRESSED 용신인데 adverse_activation != NONE      0
한신인데 favorable/adverse 활성                      0
UNKNOWN 인데 resolved_element 존재                   0
충 근거만으로 정체성 소실                             0
target 4개 초과                                     0
동일 (layer, component) 중복 결과                    0
```

---

## 9. 검토가 필요한 관측

### 뿌리 판정이 과도하게 관대하다

`direct_natal_and_transit_root` 가 58% 이고 `FULLY_OPERABLE` 이 67% 다.

원인은 뿌리 탐색이 **모든 자리의 지장간 전부(여기·중기·정기)** 에서 같은 오행을 찾기
때문이다. 원국 4지 + 운 2지 × 지장간 최대 3개 = 최대 18개 후보가 있어, 어지간한 오행은
어딘가에 뿌리를 갖는다.

이는 P2-0 에서 확정한 "지장간 정기/중기/여기를 강도 계수로 바꾸지 않는다" 를 따른 결과이고
**규칙 위반이 아니다.** 다만 실현도 등급이 상위에 몰리면 후속 계층에서 변별력이 떨어진다.

### 확정된 방향 — CAL-ROOT-DEPTH-01

뿌리를 없애는 것이 아니라 **존재와 최고 등급 자격을 분리**한다(2026-08-01 확정).

```
같은 오행의 지장간 존재     direct root 유지
정기·중기·여기              RootDepth 로 별도 기록
FULLY_OPERABLE 자격         정기 뿌리가 있을 때만
중기·여기만 있는 경우        유근이되 최대 OPERABLE
DIRECT_TRANSIT_ROOT         깊이와 무관하게 최대 OPERABLE (기존 정책 유지)
```

수치 감점(정기 1.0 / 중기 0.7 / 여기 0.4)은 도입하지 않는다 — `matched_rule_id` 단일 규칙
계약이 깨진다. 중기·여기 뿌리가 여럿이라고 정기와 동등하게 승격시키지도 않는다(개수는
evidence 로만 보존).

깊이 차등은 **출처의 직접 주장이 아니라 우리 엔진의 보수적 해상도 정책**이다. 자료는 같은
오행의 지장간을 직접 뿌리로 보는 것과 금생수가 水의 뿌리가 아닌 것까지만 지지한다.

착수 전에 `CAL-ROOT-01a` ablation 으로 같은 312 target 에 현행·후보 두 정책을 나란히 적용해
전환 규모와 위치를 먼저 본다.

### SUPPRESSED 가 1건뿐이다

첫 측정에서 실패로 보지 않는다(모집단 편향 가능). 다만 뿌리 관대함과 같은 원인일 수 있어
위 검토와 함께 본다.

---

## 10. 하지 않은 것

```
요청 단위 생산 산출물 R0~R3 직접 대조   미수행 (§1-1)
coverage-only 보충 코호트              미작성 — 뿌리 정책 변경 후로 미룬다
첫 shadow 를 켠 운영 측정               없음 — 플래그는 계속 OFF
```

전체 verdict 가 `PASS_WITH_REVIEW` 인 이유는 이제 생산 비회귀가 아니라 **뿌리 해상도**다.
`CAL-ROOT-DEPTH-01` 이 닫히고 재측정이 끝나면 `SHADOW_BASELINE_PASS` 로 올린다.

---

## 재현

```bash
cd backend
python scripts/audits/measure_luck_element_operability_shadow.py \
  --out artifacts/audits/luck_element_operability
python scripts/audits/measure_luck_element_operability_shadow.py \
  --out artifacts/audits/luck_element_operability --with-suite
```

원시 산출물(`targets.jsonl`)은 저장소에 넣지 않는다. 요약(`distribution_summary.json`)과
위 명령으로 재현한다.
