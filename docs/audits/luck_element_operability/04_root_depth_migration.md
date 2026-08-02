# 지장간 깊이 이행 (CAL-ROOT-DEPTH-01)

```
verdict   ROOT_DEPTH_MIGRATION_PASS

  P2 status semantics improved
  P3 activation discrimination unchanged
```

두 결론을 **분리해서** 적는다. 뿌리 정책은 최고등급 자격의 의미를 바로잡았지만, `FULLY` 와
`OPERABLE` 이 모두 `HIGH` 로 압축되는 활성도 계약 때문에 P3 입력은 달라지지 않았다.

## 기준 커밋

```
ablation baseline       9e60185   측정만 — 코드 변경 전 영향 범위
profile implementation  af99e9f   RootDepth 프로필 (등급 불변)
policy implementation   ce90c32   FULLY 자격 제한
01d audit               (이 커밋)
```

---

## 1. 문제

첫 shadow 측정에서 `FULLY_OPERABLE` 이 67.0% 였다. 원인은 뿌리 탐색이 모든 자리의 지장간
전부(여기·중기·정기)를 동등하게 보았기 때문이다. 원국 4지 + 운 2지 × 지장간 최대 3개 =
최대 18개 후보가 있어 어지간한 오행이 최고등급 자격을 얻었다.

**뿌리를 없애는 것이 답이 아니다.** 같은 오행의 지장간이 있으면 직접 뿌리가 맞다. 문제는
정기·중기·여기를 같은 품질로 취급해 `FULLY_OPERABLE` 자격까지 동일하게 준 것이다.

---

## 2. 모집단 — 01a와 동일

```
고유 적격 입력   78     (canonical key 중복 0)
평가 target      312    (= 78 × 4)
비적격           0
canonical key    원국 4주 + 대운 간지 + 세운 간지 + 성별 + 역할표 버전
role basis       ENGINE_NATIVE
기준 프레임      terminal final frame
```

01a·01b·01c·01d가 같은 모집단을 쓴다. 하나라도 달라지면 직접 비교하지 않는다.

---

## 3. RootDepth 계약

```
MAIN_QI > MIDDLE_QI > RESIDUAL_QI > NONE        (UNKNOWN 별도)
```

`NONE` 과 `UNKNOWN` 은 다르다.

```
NONE      해당 범위의 지지를 정상적으로 전부 조사했고 같은 오행 뿌리가 없다
UNKNOWN   resolved_element 미확정 등으로 전수 판정 자체가 불가능하다
```

한 범위가 `UNKNOWN` 이면 다른 범위에 정기 뿌리가 있어도 전체를 `UNKNOWN` 으로 둔다 —
"확실히 MAIN_QI" 라고 말할 수 없다(보수적).

간접 생조는 `RootDepth` 에 넣지 않는다. 금생수를 水의 `RESIDUAL_QI` 로 올리면 뿌리와 생조의
구분이 무너진다.

깊이 해석은 `hidden_stems_with_depth` 한 곳에 고정한다. `HiddenStemType` 만 읽으며 **배열
길이나 순서로 역할을 추측하지 않는다** — 지지마다 지장간이 1~3개로 달라 길이 기반은 틀린다.
12지지 전수를 회귀로 고정했다.

---

## 4. 01b — 프로필 확장 (등급 불변)

```
RootInstance.depth                          인스턴스별
natal_root_depth · transit_root_depth       범위별
strongest_root_depth · has_main_qi_root     집계
```

집계만 두면 "어느 자리의 어떤 지장간 때문에 MAIN_QI 인가" 를 설명할 수 없어 인스턴스에도
깊이를 남겼다.

감사 overlay 의 깊이 산출 복사본은 제거하고 production helper 를 import 하도록 바꿨다.
복사본을 남기면 결과가 같아도 "같은 판정을 썼다" 가 아니라 "우연히 일치했다" 가 된다.
의존 방향은 production ← audit 한 방향뿐이다.

검증: 01a 후보 이동 52건 재현, `OperabilityStatus`·`matched_rule_id`·`root_status` 전부 동일.

---

## 5. 01c — 자격 제한

```
FULLY + MAIN_QI      → FULLY 유지
FULLY + MIDDLE_QI    → OPERABLE
FULLY + RESIDUAL_QI  → OPERABLE
그 밖                 → 기존 결과 유지
```

`has_main_qi_root=False` 로 판정하지 않는다. 그 값은 중기·여기뿐 아니라 `NONE`·`UNKNOWN`
에서도 False 라, 직접 뿌리가 있는데 깊이가 `NONE` 인 **모순 조합까지 조용히 하향**시켜
프로필 불변식 위반을 정상 결과로 흡수한다. 하향은 명시적으로 중기·여기일 때만 한다.

기존 규칙 ID 는 개명하지 않았다. 개명하면 52건 외의 행에서도 `matched_rule_id` 가 바뀌어
"01a 에서 검증한 변경만 적용" 이라는 계약이 흐려진다.

```
R10_NATAL_AND_TRANSIT_ROOT_CLEAR         유지
R20_NATAL_ROOT_STABLE_SUPPORT            유지
R10_NATAL_AND_TRANSIT_NON_MAIN_ROOT_CAP  신규 35
R20_NATAL_NON_MAIN_ROOT_CAP              신규 17
```

판정은 사후 덮어쓰기가 아니라 규칙 predicate 안에 넣어 `matched_rule_id` 하나가 최종 결과를
완전히 설명한다. 수치 감점(정기 1.0 / 중기 0.7 / 여기 0.4)은 도입하지 않았다.

---

## 6. 이행 결과

```
                    01a 동결      현재 HEAD(ce90c32)
fully_operable       209 (67.0%)   157 (50.3%)
operable              56 (17.9%)   108 (34.6%)
partially_operable     8             8
weakened              36            36
suppressed             1             1
unknown                2             2
```

```
migration_delta_from_01a_baseline   52건   FULLY → OPERABLE
outstanding_policy_gap_after_01c     0건   현재 production 대비 overlay 잔여
illegal_transitions                  []
invariant_violations                 {}
```

잔여 gap 이 0 이므로 **정책이 이중 적용되지 않았다.** 01c 이후에도 overlay 가 52건을 또
내렸다면 두 번 적용된 것이다.

### 규칙 변화

```
R10_NATAL_AND_TRANSIT_NON_MAIN_ROOT_CAP   35   (01a moved_by_rule R10 35 과 일치)
R20_NATAL_NON_MAIN_ROOT_CAP               17   (01a moved_by_rule R20 17 과 일치)
```

기존 규칙 12종(`R00`·`R11`·`R12`·`R21`·`R22`·`R23`·`R30`·`R31`·`R32`·`R40`·`R42`·`R43`)의
건수는 전부 그대로다. 무근 규칙·절각·12운성 복합규칙·`DIRECT_TRANSIT_ROOT` 는 불변이다.

---

## 7. 활성도 영향 — 0건

```
ActivationLevel        HIGH → HIGH   (52건 전부)
activation anchor      0.75 → 0.75
favorable/adverse/mitigation/neutral/tension   변경 0
canonical role         변경 0
```

P2-3 매핑이 `FULLY_OPERABLE → HIGH` 와 `OPERABLE → HIGH` 로 같기 때문이다.
`structural_tension` 도 유리 역할은 둘 다 `NONE`, 불리 역할은 둘 다 `HIGH` 라 이동이 없다.

> **RootDepth 정책은 작동성 상태의 과도한 최고등급 집중을 완화했지만, 현재 P2-3 활성도
> 해상도에서는 P3 입력의 변별력을 높이지 않는다.**

주의: 활성도 **축** 은 불변이지만 `RoleActivationResult` 는 `operability_status`·
`operability_anchor` 를 보존하므로 52건에서 객체 byte 는 달라진다. 두 주장을 구분한다.

---

## 8. 생산 비회귀 — 현재 HEAD 재검증

`6f730ac` 의 매트릭스는 **당시 HEAD** 를 증명한다. 이후 `af99e9f`·`ce90c32` 에서 shadow
프로필과 평가 규칙이 바뀌었으므로 현재 HEAD 에서 다시 실행했다.

```
실행 대상   ce90c32 (clean tree, 네 실행 종료까지 수정 없음)

R0  graph=F state=F oper=F   exit 0
R1  graph=F state=T oper=F   exit 0
R2  graph=F state=F oper=T   exit 0
R3  graph=T state=T oper=T   exit 0
```

editable 설치가 메인 저장소를 가리키므로 detached worktree 를 쓰지 않았다 — worktree 에서
돌려도 import 되는 코드는 메인 저장소의 것이라 측정 대상이 어긋난다.

### 증명 범위

```
증명한다      네 플래그 조합에서 기존 생산 assertion 전건 통과
              OFF/ON inert 회귀 · production 응답 · LLM 입력 · score/status/rank 회귀
              shadow 예외가 생산 요청으로 전파되지 않음
증명하지 않는다  동일 요청에 대한 R0/R3 런타임 산출물의 외부 fingerprint 직접 교차 비교
```

---

## 9. 남은 한계와 후속

```
해결   ROOT_DEPTH_OVERGENEROUS_FULLY_ELIGIBILITY

미해결 ACTIVATION_LEVEL_COMPRESSION
       FULLY 와 OPERABLE 이 모두 HIGH — RootDepth 개선이 P3 활성도 해상도에 전달되지 않는다
```

`FULLY 50.3%` 는 더 이상 결함 판정으로 쓰지 않는다. 관측값은 높지만 기존 회귀 fixture 의
편향 가능성이 있고, 남은 최고등급 행은 `MAIN_QI` 자격을 충족한다. **추가 하향은 별도 근거
없이 수행하지 않는다.**

다음은 `CAL-ACTIVATION-RESOLUTION-01a` — 후보 A(등급 세분)·B(operability anchor 병행)·
C(자격 태그)의 measurement-only 비교다. 뿌리 정책은 다시 손대지 않는다.
