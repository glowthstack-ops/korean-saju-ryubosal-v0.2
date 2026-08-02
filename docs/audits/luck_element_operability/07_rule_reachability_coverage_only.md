# 규칙 도달성 coverage-only

```yaml
observed_distribution_unchanged: PASS
rule_registry_classified: PASS
r41_reachability: PASS
profile_to_ordering_chain: PASS
production_nonregression: PASS

overall: P2_RULE_REACHABILITY_PASS
```

**기존 관측 분포와 섞지 않는다.** 여기 사례는 78입력·312 target 분포의 어떤 비율에도
합산되지 않는다. 목적은 분포 개선이 아니라 현재 규칙표의 도달 가능성과 계층 연결 증명이다.

---

## 1. 규칙 목록을 코드에서 산출

`R41` 만 하드코딩하지 않고 현재 평가기 소스에서 전체 `matched_rule_id` 집합을 뽑았다.
01c 에서 cap 규칙이 추가됐으므로 미도달 집합도 다시 계산해야 한다.

```
규칙 총      18
기존 관측    16
미도달        2
```

**미도달이 R41 하나일 것이라는 예상은 틀렸다.** 스크립트가 `R01_UNKNOWN_ROOT` 를 함께
찾아냈다 — 결론을 손으로 적지 않고 산출하게 한 이유가 이것이다.

---

## 2. 규칙별 판정

| rule_id | observed | supplemental | reachability |
|---|---:|---:|---|
| R00_UNRESOLVED_ELEMENT | 2 | — | OBSERVED |
| R01_UNKNOWN_ROOT | 0 | 1 | **DEFENSIVE_GUARD** |
| R10_NATAL_AND_TRANSIT_ROOT_CLEAR | 128 | — | OBSERVED |
| R10_NATAL_AND_TRANSIT_NON_MAIN_ROOT_CAP | 35 | — | OBSERVED |
| R11_…_CUT_OFF_WEAK_STAGE | 17 | — | OBSERVED |
| R12_…_CUT_OFF | 1 | — | OBSERVED |
| R20_NATAL_ROOT_STABLE_SUPPORT | 29 | — | OBSERVED |
| R20_NATAL_NON_MAIN_ROOT_CAP | 17 | — | OBSERVED |
| R21_NATAL_ROOT_CLEAR | 37 | — | OBSERVED |
| R22_NATAL_ROOT_CUT_OFF_WEAK_STAGE | 6 | — | OBSERVED |
| R23_NATAL_ROOT_CUT_OFF | 2 | — | OBSERVED |
| R30_TRANSIT_ROOT_CLEAR | 19 | — | OBSERVED |
| R31_TRANSIT_ROOT_CUT_OFF_WEAK_STAGE | 1 | — | OBSERVED |
| R32_TRANSIT_ROOT_CUT_OFF | 1 | — | OBSERVED |
| R40_ROOTLESS_CUT_OFF_NO_RELIABLE_SUPPORT | 1 | — | OBSERVED |
| **R41_ROOTLESS_CUT_OFF_WITH_SUPPORT** | **0** | **1** | **SUPPLEMENTAL_REACHABLE** |
| R42_ROOTLESS_NO_RELIABLE_SUPPORT | 12 | — | OBSERVED |
| R43_ROOTLESS_WITH_SUPPORT | 4 | — | OBSERVED |

미분류 규칙 0건. 새 규칙이 생기면 `test_every_registry_rule_is_classified` 가 먼저 깨진다.

---

## 3. R41 보충 fixture

무근 + 절각 + **안정** 생조. 세 조건이 모두 성립해야 한다.

```yaml
profile:
  root_status: ABSENT
  natal_root_depth: NONE
  transit_root_depth: NONE
  strongest_root_depth: NONE       # UNKNOWN 이면 fixture 결함이다
  has_main_qi_root: false
  support_status: INDIRECT_GENERATION_STABLE
  obstruction_status: CUT_OFF_PRESENT
  stage: 관대                       # 약한 단계가 아니다 — 하향 원인을 겹치지 않게 한다

evaluation:
  status: WEAKENED
  anchor: 0.35
  matched_rule_id: R41_ROOTLESS_CUT_OFF_WITH_SUPPORT
```

### 이웃 규칙과 실제로 갈리는지 확인

```
생조를 DISRUPTED 로 바꾸면   → R40 (SUPPRESSED)
직접 뿌리를 주면              → R2x 계열
```

경계가 갈리지 않으면 "R41 에 도달했다" 가 아니라 "다른 규칙이 우연히 같은 답을 냈다" 일 수
있다.

### 실제 추출기로도 재현

손으로 만든 프로필과 같은 형태가 `extract_element_operability_profile` 로도 나오는지
확인했다(원국 酉 + 세운 癸未). 합성 fixture 만으로 도달을 주장하지 않는다.

---

## 4. 여섯 계층 연결

```
profile → RootDepth → status·rule → 역할 투영 → within-level order key
```

`ENGINE_NATIVE` 역할표로 용신·기신·한신 세 경우를 확인했다.

```
용신   favorable LOW
기신   adverse   LOW
한신   neutral   LOW · structural_tension NONE
order key 생성   within_level_anchor 0.35
```

### 등급 내부 순서

```
LOW / WEAKENED   0.35
>
LOW / SUPPRESSED 0.15        같은 축에서 성립
cross-axis 비교              런타임 거부
```

R40 과 R41 이 같은 `LOW` 로 압축되지만 등급 내부 순서로 갈린다 — 해상도 계약이 실제 규칙
경계에서 값을 하는 첫 사례다.

---

## 5. R01 은 방어 가드다

`RootStatus.UNKNOWN` 은 `resolved_element` 가 없을 때만 생기고, 그때는 `R00` 이 먼저 선점한다.
**추출기를 통해서는 R01 에 도달할 수 없다.**

```
평가기에 직접 주입   → R01_UNKNOWN_ROOT 동작 (죽은 코드가 아니다)
추출기 경로          → R00_UNRESOLVED_ELEMENT 가 선점
```

규칙을 억지로 통과시키지 않고 `DEFENSIVE_GUARD` 로 분류했다. 프로필 계약이 바뀌어
`RootStatus.UNKNOWN` 이 다른 경로로 생기면 그때 자연 도달한다.

---

## 6. 기존 분포 불변

```
operability_status · matched_rule_id · root_status · target_count ·
unique_eligible_inputs        전부 동일
```

coverage-only 사례는 분포 비율·FULLY/OPERABLE 비율·UNKNOWN 비율·역할별 활성도 어디에도
합산되지 않는다. 달라졌다면 fixture 격리가 실패한 것이다.

---

## 7. production 불변

```
schema 변경        없음
호출부 추가        없음
production 코드    변경 없음 (테스트만 추가)
```

---

## 8. 다음

```
CAL-ROLE-BORDERLINE-01
P3 이벤트·풀이 연결
```

위험 lease 유료 실행은 이 트랙과 분리해 `READY_FOR_EXPLICIT_APPROVAL` 상태로 둔다.
