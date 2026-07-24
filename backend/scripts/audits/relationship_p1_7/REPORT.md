# P1-7b 결정적 비교 harness — 관찰 지도 (2026-07-24)

fixture 6종(성별·일간 음양 stratified) · 비교 record 331건. **감사 전용 — 수정 없음.** legacy relation delta와 P1 activation은 동일 척도가 아니다(유무·방향·cap·root·kind 우선, delta는 bucket 보조).

## 비교 class 분포

| class | count |
|---|--:|
| legacy_candidate_absent | 107 |
| vector_insufficient | 50 |
| aligned | 47 |
| legacy_event_key_blind_spot | 41 |
| legacy_cap_saturated | 28 |
| review_required_direction_mismatch | 18 |
| mixed | 17 |
| vector_only_structure | 13 |
| legacy_only_signal | 10 |

### 후보 부재 세분(§7 — 오류 아님, P3 검토 신호)

| subclass(대표값) | count |
|---|--:|
| vector_present | 85 |
| multi_root | 22 |

### 중첩 독립 finding(§2·§3 — 합계≠record 수, 복합 현상 보존)

> primary_class 하나가 가리는 현상을 독립 카운터로 집계한다. strong+multi-root 부재처럼 한 record가 복수 finding을 동시에 갖는다.

| finding | count |
|---|--:|
| legacy_event_key_coverage_gap | 135 |
| negative_stability_with_positive_delta | 88 |
| all_candidates_absent | 57 |
| multi_root | 57 |
| cap_saturated | 53 |
| vector_insufficient | 50 |
| strong_activation | 36 |
| multi_root_candidate_absent | 22 |
| strong_activation_candidate_absent | 15 |

## §4 필수 매트릭스

### A. Root 수 × legacy cap

| row | cap | no_cap | cap_unknown |
|---|---|---|---|
| 0 | 0 | 60 | 13 |
| 1 | 34 | 167 | 0 |
| 2 | 19 | 38 | 0 |

### B. KindCombo × 후보 family(후보 존재 수)

| row | marriage_signal | new_relationship | relationship_change |
|---|---|---|---|
| emergence_only | 7 | 6 | 4 |
| hap_only | 16 | 11 | 12 |
| hap_with_negative | 7 | 4 | 6 |
| multi_negative | 2 | 2 | 2 |
| negative_single | 15 | 11 | 11 |
| none | 21 | 22 | 17 |
| other_bounded | 5 | 5 | 2 |
| palace_plus_emergence | 9 | 8 | 6 |

### C. 벡터 stability/separation × legacy delta 방향

| 벡터 축 | legacy delta 분포 |
|---|---|
| stab=mixed_or_neutral/sep=evaluated | {"capped_22": 4, "zero": 2} |
| stab=na/sep=insufficient_evidence | {"zero": 95, "mid": 4, "delta_na": 13} |
| stab=negative/sep=evaluated | {"capped_22": 41, "zero": 42, "mid": 11, "high": 28, "low": 4} |
| stab=positive/sep=insufficient_evidence | {"high": 18, "zero": 29, "mid": 32, "capped_22": 8} |

## stratification(§8)

### 성별 × class

| gender | class 분포 |
|---|---|
| female | {"legacy_candidate_absent": 53, "mixed": 6, "legacy_cap_saturated": 15, "aligned": 27, "review_required_direction_mismatch": 9, "legacy_event_key_blind_spot": 25, "vector_insufficient": 21, "legacy_only_signal": 8, "vector_only_structure": 6} |
| male | {"vector_insufficient": 29, "legacy_cap_saturated": 13, "legacy_candidate_absent": 54, "aligned": 20, "legacy_event_key_blind_spot": 16, "vector_only_structure": 7, "mixed": 11, "review_required_direction_mismatch": 9, "legacy_only_signal": 2} |

### 일간 음양 × class

| 음양 | class 분포 |
|---|---|
| yang | {"vector_insufficient": 26, "legacy_cap_saturated": 14, "legacy_candidate_absent": 60, "aligned": 19, "legacy_event_key_blind_spot": 16, "vector_only_structure": 11, "mixed": 12, "review_required_direction_mismatch": 8} |
| yin | {"legacy_candidate_absent": 47, "mixed": 5, "legacy_cap_saturated": 14, "aligned": 28, "review_required_direction_mismatch": 10, "legacy_event_key_blind_spot": 25, "vector_insufficient": 24, "legacy_only_signal": 10, "vector_only_structure": 2} |

## findings(관찰만 — 수정은 P2/P3 별도 승인)

명칭은 결론을 선점하지 않게 중립 서술한다(§5). 아래는 결정적 재현 관찰이며 production 빈도는 P1-7d coarse aggregate가 별도 분모로 확인한다(fixture는 확률 표본 아님 — §11).

- **event family 신호 소비 비대칭**(coverage gap) 41건 — 동일 기간·구조에서 일부 family만 relation 신호를 소비. 의도된 사건별 계약인지 구현 사각지대인지는 P3 판단.
- **legacy cap 포화** 28건 — cap 22는 복수 root의 복합성뿐 아니라 단일 root 안의 강한 relation kind·원시 강도도 동일 +22로 압축한다(root=1 cap 포화가 이를 입증 — 매트릭스 A).
- **벡터 존재·후보 미생성** 107건 — legacy ten-god branching gate/신호 소비 공백/P1 activation 범위가 사건 후보보다 넓음 중 하나일 수 있음. P3 증거 계약·후보 승격 검토(원인은 미확정).
- **방향 의미 혼합**(review-required) 18건 — legacy 단일 스칼라에 관계 활성과 유지 품질이 함께 압축된 현상. 오류 확정 아님 — P1 formalization 미평가라 leakage 판단은 P3 이후.
- **P1 축 근거 부족** 50건 — legacy 후보 있으나 P1 해당 축 미평가(정상 보류 — 0으로 비교하지 않음).

