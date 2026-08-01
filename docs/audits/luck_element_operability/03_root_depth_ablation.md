# 지장간 깊이 ablation (CAL-ROOT-01a)

```
verdict   ROOT_DEPTH_ABLATION_STATUS_ONLY
정책      root-depth-main-qi-fully-cap-v1
production 변경  없음 — 감사 overlay 로만 적용
```

**코드를 바꾸기 전에 영향 범위를 잰다.** 후보 정책은 P2-2 평가기를 수정하지 않고 baseline
결과에 상한 하나만 덧씌운 것이다.

```
baseline 이 FULLY_OPERABLE 이고 MAIN_QI 뿌리가 없다  → OPERABLE
그 외                                              → baseline 그대로
```

중기·여기 차등 감점, 뿌리 개수 승격, `OPERABLE` 추가 하향, 절각·생조·12운성 재계산은 하지
않았다. 그렇게 하면 무엇이 이동을 일으켰는지 분리할 수 없다.

---

## 1. 측정 방식

같은 78개 입력·312개 target 에 대해 **한 번의 paired evaluation** 으로 냈다. 현행과 후보를
별도 실행으로 만들면 모집단·정렬 차이가 결과 이동으로 오인된다.

```
--ablation root-depth-main-qi-fully-cap-v1
```

이름 있는 옵션이다. boolean 이면 나중에 다른 ablation 과 결과를 구별할 수 없다. 옵션 없이
실행하면 `fa66cb1` 측정과 동일한 결과·형식이 나온다(회귀로 확인).

```
operability_status · matched_rule_id · root_status · target_count · 고유 입력 수   전부 동일
기본 실행 산출물에 candidate 필드 없음 · ablation 요약 키 없음
```

---

## 2. RootDepth 분포

```
main_qi       198   63.5%
middle_qi      74   23.7%
residual_qi    21    6.7%
none           17    5.4%
unknown         2    0.6%
```

`INDIRECT_GENERATION` 은 포함하지 않는다. 여러 직접 뿌리가 있으면 가장 깊은 자격을 대표로
쓴다(원국·운 깊이는 별도 필드로 보존).

---

## 3. 상태 이동

```
fully_operable → fully_operable   157
fully_operable → operable          52
operable       → operable          56
weakened       → weakened          36
partially      → partially          8
suppressed     → suppressed         1
unknown        → unknown            2

illegal_transitions   []
```

허용 전이 밖의 이동은 0건이다. 후보가 baseline 보다 상향된 경우도 없다.

```
FULLY_OPERABLE   209 (67.0%)  →  157 (50.3%)
OPERABLE          56 (17.9%)  →  108 (34.6%)
```

### 이동 위치

```
layer × component        sewoon.stem 21 · sewoon.branch 13 · daewoon.branch 11 · daewoon.stem 7
canonical_role           희신 22 · 구신 13 · 용신 8 · 기신 7 · 한신 2
baseline matched_rule    R10 35 · R20 17
```

이동은 두 규칙에서만 나왔다. 원국+운 뿌리(R10)와 원국 뿌리+안정 생조(R20) — `FULLY` 자격을
주던 두 경로가 정확히 대상이다.

---

## 4. 핵심 관측 — 활성도는 움직이지 않는다

```
activation_changed   0 / 312
```

P2-3 매핑이 `FULLY_OPERABLE → HIGH` 와 `OPERABLE → HIGH` 로 같기 때문이다.

```
operability   0.90 → 0.75   (52건 이동)
activation    HIGH → HIGH   (0건 이동, anchor 0.75 → 0.75)
```

> **RootDepth 후보 정책은 작동성 상태의 과도한 최고등급 집중을 완화하지만, 현재 P2-3 활성도
> 해상도에서는 P3 입력의 변별력을 높이지 않는다.**

`structural_tension` 도 마찬가지다 — 유리 역할의 `FULLY`·`OPERABLE` 은 둘 다 `NONE`,
불리 역할은 둘 다 `HIGH` 라서 역할별로 대조해도 이동이 없다.

---

## 5. 결론과 분리

이 결과로 RootDepth 정책을 폐기하지 않는다. **두 문제를 분리한다.**

```
CAL-ROOT-DEPTH-01
  P2 상태 의미론 개선. 중기·여기만으로 최고등급을 주지 않는 것은 그 자체로 옳다.
  이동 52건이 허용 전이 안에서만 일어나고 활성도·역할·production 을 건드리지 않으므로
  01b/01c 로 진행 가능하다.

CAL-ACTIVATION-RESOLUTION-01
  FULLY 와 OPERABLE 을 P3 에서 구분할지 별도 검토. 지금 매핑으로는 두 등급이 동일 입력이다.
```

**01a 에서 P2-3 매핑을 함께 바꾸지 않았다.** 함께 바꾸면 상태 이동과 활성도 이동의 원인이
섞여 어느 쪽이 무엇을 만들었는지 분리할 수 없다.

---

## 6. 하드 불변식

```
target 수 변화                        0
canonical key 변화                    0
node_id 누락·중복                     0
baseline 이 기존 보고서와 다름          0
candidate 가 baseline 보다 상향        0
FULLY→OPERABLE 이외 상태 이동          0
ABSENT root 의 상태 변경               0
DIRECT_TRANSIT_ROOT 로 인한 신규 FULLY  0
UNKNOWN 증감                          0
canonical role 변경                   0
production 출력 변경                   0
```

---

## 재현

```bash
cd backend
python scripts/audits/measure_luck_element_operability_shadow.py \
  --out artifacts/audits/luck_element_operability \
  --ablation root-depth-main-qi-fully-cap-v1
```

overlay 구현은 `backend/scripts/audits/_operability_ablations.py` 에 있으며 production
모듈은 이 파일을 import 하지 않는다. 확정되면 P2-1(`RootDepth` 프로필)과
P2-2(`FULLY` 자격 규칙)로 옮긴다.
