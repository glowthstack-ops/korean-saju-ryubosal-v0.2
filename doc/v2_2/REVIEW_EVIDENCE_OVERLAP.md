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

## 1-1. 식별자 규약 — 결산 명칭과 로드맵 번호를 섞지 않는다

이번에 **배포된 수정**은 영역 명칭으로 부르고, `P0.5`·`P2`·`P3`·`P4`·`P5`는
**앞으로의 작업 식별자**로만 쓴다(과거 회고에서 P1~P3를 배포 항목에 붙여 로드맵
번호와 충돌한 적이 있다).

| 배포된 수정(영역 명칭) | 내용 |
|---|---|
| 관계 의미론 | 寅亥合 canonical claim · 결정론적 문장 교체 |
| 계층형 grounding | 상위 운 결합 · 연·월·일 역할 요약 |
| 간지 극성 | 천간·지지 polarity 분리 · MIXED 보존 |
| 기간 위계 | 양방향 local-only 캡 |
| 출력 안전 | 정책 에코 차단 |
| 운영 안정 | 재기동 스크립트 |

## 2. 단계별 상태

| 작업 | 판정 |
|---|---|
| P3-1 `exact_evidence_dedup` | **완료** — 이미 동작(실측 33→26, 7건 제거) |
| P3-2 `subset_pattern_dominance` | **production 보류** — 대표 사례가 적용 대상이 아님만 확정. 실제 occurrence subset 사례의 존재 여부는 미탐색 |
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

audit 스크립트는 production scorer의 신호를 **읽기만** 한다(판정 분기 추가 금지)
audit 결과·shadow 필드는 API·LLM·리포트 입력에 노출하지 않는다
max_only / designated_primary_only 결과는 감사 출력에만 존재한다
```

**`current` 재현 불변식** — 조사 시작 전 가장 먼저 확인한다.

```
current.raw_status        == production.raw_status
current.effective_status  == production.effective_status
current.guard_codes       == production.guard_codes
current.rank              == production.rank
current.top_n_membership  == production.top_n_membership
```

`top_n_membership`은 rank와 별개로 확인한다 — 개별 후보의 순위가 같아도 후보 집합
구성이나 동률 처리 차이로 Top-N 결과가 달라질 수 있다.

**단일 사례가 아니라 감사 대상 전체**에서 확인한다. 불일치는 아래로 분류한다.

```
STATUS_MISMATCH
GUARD_MISMATCH
RANK_MISMATCH
TOP_N_MEMBERSHIP_MISMATCH
SIGNAL_SET_MISMATCH
```

하나라도 발생하면 P3-2·P4 분석으로 진행하지 않고 **재현 경로부터 수정한다.**
재현이 깨진 상태의 반사실 비교는 의미가 없다.

## 3-1. 조사 세션 중 끝까지 불변으로 유지할 것

```
production contribution · status · rank
기존 InteractionCluster의 점수 소비
API · LLM · 리포트 payload
운영 플래그
```

`P4-E`도 조사 결과 전까지는 **메타데이터 준비까지만** 하고, 실제 사용자 문장 변경은
별도 커밋으로 분리한다 — 역할 분류가 틀리면 숫자는 그대로여도 설명이 실제 계산과
어긋난다.

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

집계 우선순위는 `top_n_membership_flip` > `effective_status_flip` >
`raw_status_flip` > 순위 이동 > 점수 차이다. 점수 차이보다 **사용자가 보는 결과가
바뀌는지**를 먼저 본다.

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

B와 D는 동시에 성립할 수 있다. 하나만 고르지 말고 조합해 보고한다.

```
주 판정  D — temporal_role이 대부분 달라 독립 기여
영향 판정 B — 반사실에서도 상태·Top-N 변화가 미미
조치     숫자 유지 + 표현 클러스터링
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

## 12. 선행 배포의 검증 근거 (기간 위계 캡)

`LOCAL_ADVERSE_ONLY` 운영 활성화(2026-07-27)의 근거를 남긴다.

```
엔진 검증  6명식 636 슬롯 스윕 — 오적용 3종 전부 0건
           (upper_support 있는데 캡 / 상위 부정 있는데 shadow / ADVERSE 아닌데 후보)

문장 검증  LLM 7건 — 관계·직업 각각의 일운/월운/월+일 조합 + 통제 사례
           5개 기준 통과: 장기 악화 확대 없음 · 실패 비약 없음 · 주의점 삭제 없음
                          내부 정보 노출 0건 · 도메인별 문구 반영

통제 사례  명식 E 2026-01-12 (세운에 동일 카테고리 부정 기여 존재)
           → ADVERSE_DOMINANT 유지 · guard_codes=[] · 오적용 없음
           → 문장도 상위 근거(사오미 방합)를 인용하며 국소 한정을 넣지 않음
           재기동 후 스모크에서 재확인

7건 사유   계획 8건 중 decision 경계 사례는 6명식 636슬롯 스윕에서 발생하지 않았다
           (decision 부정 shadow 후보율 0%). 조건이 관측되지 않아 생략했으며,
           인위적 사례를 만들지 않았다.
```
