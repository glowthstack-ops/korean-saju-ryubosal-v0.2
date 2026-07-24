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

| subclass | count |
|---|--:|
| vector_present | 85 |
| multi_root | 22 |

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

- LEGACY_EVENT_KEY_BLIND_SPOT 41건 — family별 사각지대(합산 금지 대상).
- LEGACY_CAP_SATURATED 28건 — cap 22로 구조 정보 소실.
- LEGACY_CANDIDATE_ABSENT 107건 — 벡터 있으나 후보 미생성(P3 증거 계약 검토).
- REVIEW_REQUIRED_DIRECTION_MISMATCH 18건 — 보수 분류(P1 formalization 미평가 — leakage 확정은 P3 이후).
- VECTOR_INSUFFICIENT 50건 — legacy 후보 있으나 P1 축 근거 부족(정상 보류).

