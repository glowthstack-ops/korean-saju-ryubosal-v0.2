# 조사 계약 — 증거 중첩(subset / partial overlap)

> 상태: **조사 대기** · 기록일 2026-07-27 · 결론 문서 아님
>
> 다음 세션은 **production 점수를 변경하지 않는 조사 세션**이다. 이 문서는 조사 범위와
> 판정 규칙을 미리 고정해, subset과 partial overlap을 혼동하는 실수를 막는다.

## 0. 목표

중첩의 **존재 여부**가 아니라, 동일 효과의 중첩 계상이 **슬롯 상태나 Top-N 노출을
실제로 바꾸는지**를 검증한다.

```
partial overlap이 존재하는가          ← 조사 목표 아님
그 결과 상태·순위가 실제로 뒤집히는가  ← 조사 목표
```

## 1. 이번에 확정된 판정 (재실수 방지)

기준 명식 2026-07-27에서 관측된 火 클러스터:

```
巳午未방합  참여: 원국시지 巳 · 세운 午 · 월운 未
寅午반합    참여: 일진 寅 · 세운 午

교집합 = {午}      포함관계 = 없음      → partial overlap (subset 아님)
```

**이 사례를 `subset_pattern_dominance`의 근거로 쓰면 안 된다.** 반합을 방합의 하위
패턴으로 보고 제거하면 일진 寅이라는 **독립 근거까지 삭제**된다.

## 2. 단계별 상태

| 작업 | 판정 |
|---|---|
| P3-1 `exact_evidence_dedup` | **완료** — 이미 동작(실측 33→26, 7건 제거) |
| P3-2 `subset_pattern_dominance` | 존재 탐색부터. 대표 사례는 근거 아님 |
| P4 `partial_overlap` | 실재하나 '중복 과대계상' 미확정 — shadow 계측 우선 |
| P4-E 표현 압축 | 숫자 불변. role 메타데이터 산출 이후 적용 |

## 2-1. 분석 입력 스냅샷 — 각 신호가 보유해야 할 필드

```
signal_id · relation_id · source_occurrences · source_layers
target · effect_family · runtime_polarity · domain/event
temporal_role · contribution
```

`runtime_polarity`와 `temporal_role`은 조사 시작 전에 산출돼 있어야 한다. 이 둘이
없으면 dominance 판정도 반사실 비교도 성립하지 않는다.

## 3. 불변식 (조사 세션 전체에 적용)

```
P3-1 exact dedup **이후**의 신호만 분석한다
  (제거된 7건을 중첩 통계에 넣으면 부분 중첩률이 부풀려진다)

정적 subset은 후보(STATIC_SUBSET_CANDIDATE)일 뿐 dominance 확정이 아니다

판정은 branch 문자 집합이 아니라 **실제 source occurrence**의 부분집합으로 한다
  {午,未} < {巳,午,未}                              ← 금지
  {year:午, month:未} < {natal_hour:巳, year:午, month:未}  ← 필요

temporal_role이 다르면 숫자 제거를 금지한다
  source layer가 일부 같다는 이유로 role이 같다고 판정하지 않는다

P4 반사실은 최종 점수 차감이 아니라 **신호 집합을 바꾼 전체 재채점**으로 산출한다
  (층위 캡·상태 판정·정렬이 비선형이므로 차감으로 근사할 수 없다)

production 점수·상태·순위 변경 없음. 임의 감쇠계수(0.5배 등) 도입 금지
표현 클러스터링은 숫자 불변
```

## 4. temporal_role 정의 (명시 산출 — 층위 조합으로 추정 금지)

```
STRUCTURAL_CONTEXT   원국 구조·고정 취약성
REGIME               대운의 장기 환경
ANNUAL_AGENDA        세운의 연간 의제
MONTHLY_WINDOW       월운의 활성 구간
DAILY_TRIGGER        일운의 접촉·실행·마찰
COMPOSITE_CONTEXT    여러 층위가 만든 환경 강화
COMPOSITE_TRIGGER    상위 구조를 하위 운이 완성·촉발
```

기준 사례 적용:

```
巳午未방합 → COMPOSITE_CONTEXT / MONTHLY_WINDOW
寅午반합   → DAILY_TRIGGER / COMPOSITE_TRIGGER
same_target=true · same_effect_family=true · same_temporal_role=false
→ 숫자 감쇠 대상에서 제외
```

## 5. P3-2 판정 조건

**정적 후보 생성** (완화 — polarity는 런타임 결정 가능):

```python
child.required_branches < parent.required_branches   # 엄격한 부분집합
and child.target == parent.target
and child.effect_family == parent.effect_family
```

**동적 dominance 확정** (아래 전부 충족해야 함):

```
child 실제 source occurrence ⊂ parent 실제 source occurrence
target / effect_family / polarity 동일
적용 category·event 동일
temporal_role 동일
parent가 완성 패턴
child의 독립 trigger 없음
child의 독립 궁위 의미 없음
child의 독립 formula 기여 없음
```

하나라도 다르면 → 설명 클러스터 포함 가능, **숫자 제거 금지**.

동적 조건 충족 0건이면 P3-2는 `탐색 완료 · dominance 미발생 · 미구현`으로 닫고 탐지
fixture만 보존한다.

## 6. P4 반사실 3종

각각 **신호 집합을 바꿔 전체 파이프라인을 재실행**한다.

```
current            현행 신호 집합
max_only           클러스터별 최대 기여 하나만 유지
primary_only       designated primary만 유지
```

`primary` 선정은 기존 `InteractionCluster`의 규칙을 재사용한다(완성 패턴 > 왕지 반합 >
육합 > 부분). 기여점수 최대를 primary로 삼으면 반사실이 현재 산식에 종속되므로
`designated_primary_only`와 `max_contribution_only`를 분리한다.

각 결과에서 재산출: `raw_status` · `effective_status` · `guard_codes` · `slot rank` ·
`Top-N 포함 여부`.

## 7. 지표 (분모를 나눠 기록)

| 지표 | 분모 |
|---|---|
| partial-overlap 발생률 | 전체 슬롯 |
| same_temporal_role 비율 | overlap 슬롯 |
| 패턴 조합별 발생량 | overlap cluster |
| target·도메인별 분포 | overlap cluster |
| `max_only` 상태 전환률 | **전체 슬롯 + overlap 슬롯 둘 다** |
| `primary_only` 상태 전환률 | 전체 슬롯 + overlap 슬롯 둘 다 |
| `top_n_membership_flip` | overlap이 있는 후보군 |
| 평균·최대 순위 이동 | 순위가 있는 overlap 후보 |

`top_n_membership_flip`이 단순 순위 이동보다 우선한다 — `rank 2→3`은 사용자 영향이
없지만 `rank 5→6`은 Top-5 출력을 바꾼다.

## 8. P4 production 판단

```
A. 대부분 temporal_role이 다름
   → 숫자 감쇠 불필요. P4-E 표현 압축만

B. role은 같지만 상태·Top-N 변화가 거의 없음
   → 과대계상 증거 부족. 숫자 현행 유지, 설명 중복만 축소

C. 같은 role의 중첩이 반복적으로 상태·Top-N을 뒤집음
   → 감수 안건으로 승격. 계수(0.5배)부터 넣지 말고 의미 모델을 먼저 정한다:
     strongest-only / shared source 1회 귀속 / primary + unique-source 기여
```

## 9. P4-E 표현 압축 — 역할 차이 보존

```
권장:
  세운 午를 중심으로 火 기운이 여러 층위에서 활성화됩니다. 巳午未 방합은 이번 달의
  환경을 강화하고, 寅午 반합은 오늘 그 흐름을 촉발하는 쪽에 가깝습니다.

금지:
  방합과 반합이 겹쳐 火가 두 배로 강해집니다.
  (점수 중복 여부가 아직 검증되지 않았다)
```

## 9-1. 조사 코드는 production과 분리한다

```
scripts/audit_evidence_overlap.py    ← 감사 전용. 여기서 먼저 탐색한다
```

실측 결과가 확인되기 전에는 **production scorer(`v2_scoring.py`)에 dominance 분기를
추가하지 않는다.** 조사 스크립트가 production 코드를 import해 읽는 것은 되지만,
그 반대(production이 조사 로직을 참조)는 금지한다.

## 9-2. 종료 판정 4종 — 조사가 끝나면 아래 중 하나로 명확히 닫는다

```
결과 A  실제 subset dominance 없음
        → P3-2 미구현 종료. 정적·동적 탐지 fixture만 보존

결과 B  partial overlap은 많지만 상태·Top-N 영향 없음
        → 숫자 현행 유지. P4-E 표현 압축만 production

결과 C  같은 temporal_role의 중첩이 상태·Top-N을 반복적으로 변경
        → P4 production 모델을 별도 감수 안건으로. 임의 감쇠계수 사용 금지.
          shared-source attribution vs strongest-only 의미 모델 비교부터

결과 D  temporal_role이 대부분 다름
        → 독립 기여로 인정. 감쇠하지 않고 문장에서만 역할을 구분해 압축
```

## 10. 커밋 단위

```
1. test(scoring): discover subset and partial-overlap candidates   ← 점수 불변
2. feat(scoring): add overlap shadow counterfactuals               ← shadow 필드만
3. feat(narrative): compress interaction cluster explanations      ← 숫자 불변 테스트
```

## 11. 관련 코드

- `saju_engines/v2_scoring.py` — `signal_identity` 기반 exact dedup(P3-1, 동작 중)
- `saju_engines/luck_hierarchy.py` — `InteractionCluster` primary 선정 규칙
- `shared_types/luck_hierarchy.py` — `HierarchyInteraction.occurrence_ids`
- `saju_engines/signal_occurrence.py` — occurrence 식별자 형식·범위 계약
