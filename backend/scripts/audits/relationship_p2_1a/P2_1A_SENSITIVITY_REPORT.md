# P2-1A 민감도 harness — secondary_factor × activation band

spec p2.1a.v1 · baseline calibration cal-2026-07-24.1 · lattice 33 case. **감사 전용·읽기 전용·production delta 0.** 두 효과 분리(raw synthesis / band projection). 자동 최적 profile 선정 없음(§12).

## 0. 불변식 게이트

- baseline P2A_SF30_B0 == production BASELINE: OK
- band 보수화 역방향 위반: 0
- 전체 위반: **0** (PASS)

## 1. Raw synthesis 축 (secondary_factor sweep · band 고정 B0)

### 축별 SF 영향(§4 — 구조별 SF00↔SF60 value 변화)

| 구조 | activation | stability_support | stability_net | separation |
|---|---|---|---|---|
| single | 없음 | 없음 | 없음 | 없음 |
| same_root_pair | 있음 | 없음 | 있음 | 있음 |
| cross_root_pair | 없음 | 없음 | 없음 | 없음 |
| root_n | 없음 | 없음 | 없음 | 없음 |

> single-kind는 전 축 SF 불변(복합 없음). same-root는 activation·stability_net·separation 변동(stability_support는 순수 sum이라 불변). cross-root는 서로 다른 root라 SF 미적용.

### same-root / cross-root increment(§4·§2 정규화 병기)

> same_inc = V_same − max(V_a,V_b) · cross_inc = V_cross − max(V_a,V_b) · margin = cross−same · retention = margin/cross_inc · same/cross = same_inc/cross_inc. 기대: same_inc≥0 · cross_inc≥same_inc (SF00에서 same_inc=0). retention↓ = root 구별력 침식.

| pair | SF | same_inc | cross_inc | margin | retention | same/cross |
|---|---|--:|--:|--:|--:|--:|
| CHUNG+HAE | SF00 | 0.0 | 7.774 | 7.774 | 1.0 | 0.0 |
| CHUNG+HAE | SF15 | 1.166 | 7.774 | 6.608 | 0.85 | 0.15 |
| CHUNG+HAE | SF30 | 2.332 | 7.774 | 5.442 | 0.7 | 0.3 |
| CHUNG+HAE | SF45 | 3.498 | 7.774 | 4.276 | 0.55 | 0.45 |
| CHUNG+HAE | SF60 | 4.664 | 7.774 | 3.11 | 0.4 | 0.6 |
| CHUNG+HYEONG | SF00 | 0.0 | 15.548 | 15.548 | 1.0 | 0.0 |
| CHUNG+HYEONG | SF15 | 2.332 | 15.548 | 13.216 | 0.85 | 0.15 |
| CHUNG+HYEONG | SF30 | 4.664 | 15.548 | 10.884 | 0.7 | 0.3 |
| CHUNG+HYEONG | SF45 | 6.997 | 15.548 | 8.551 | 0.55 | 0.45 |
| CHUNG+HYEONG | SF60 | 9.329 | 15.548 | 6.219 | 0.4 | 0.6 |
| CHUNG+PA | SF00 | 0.0 | 11.661 | 11.661 | 1.0 | 0.0 |
| CHUNG+PA | SF15 | 1.749 | 11.661 | 9.912 | 0.85 | 0.15 |
| CHUNG+PA | SF30 | 3.498 | 11.661 | 8.163 | 0.7 | 0.3 |
| CHUNG+PA | SF45 | 5.247 | 11.661 | 6.414 | 0.55 | 0.45 |
| CHUNG+PA | SF60 | 6.997 | 11.661 | 4.664 | 0.4 | 0.6 |
| HAP+CHUNG | SF00 | 0.0 | 13.604 | 13.604 | 1.0 | 0.0 |
| HAP+CHUNG | SF15 | 2.041 | 13.604 | 11.563 | 0.85 | 0.15 |
| HAP+CHUNG | SF30 | 4.081 | 13.604 | 9.523 | 0.7 | 0.3 |
| HAP+CHUNG | SF45 | 6.122 | 13.604 | 7.482 | 0.55 | 0.45 |
| HAP+CHUNG | SF60 | 8.162 | 13.604 | 5.442 | 0.4 | 0.6 |
| HAP+HYEONG | SF00 | 0.0 | 13.604 | 13.604 | 1.0 | 0.0 |
| HAP+HYEONG | SF15 | 2.041 | 13.604 | 11.563 | 0.85 | 0.15 |
| HAP+HYEONG | SF30 | 4.081 | 13.604 | 9.523 | 0.7 | 0.3 |
| HAP+HYEONG | SF45 | 6.122 | 13.604 | 7.482 | 0.55 | 0.45 |
| HAP+HYEONG | SF60 | 8.162 | 13.604 | 5.442 | 0.4 | 0.6 |
| HYEONG+PA | SF00 | 0.0 | 11.661 | 11.661 | 1.0 | 0.0 |
| HYEONG+PA | SF15 | 1.749 | 11.661 | 9.912 | 0.85 | 0.15 |
| HYEONG+PA | SF30 | 3.498 | 11.661 | 8.163 | 0.7 | 0.3 |
| HYEONG+PA | SF45 | 5.247 | 11.661 | 6.414 | 0.55 | 0.45 |
| HYEONG+PA | SF60 | 6.997 | 11.661 | 4.664 | 0.4 | 0.6 |

### raw pairwise ordering inversion vs SF30(§6)

> band threshold는 raw ordering을 바꾸지 못한다 — 이 값은 순수 raw 효과.

| SF | raw_inversion |
|---|--:|
| SF00 | 6 |
| SF15 | 6 |
| SF30 | 0 |
| SF45 | 6 |
| SF60 | 10 |

## 2. Band projection 축 (band sweep · SF 고정 0.30)

### band 분포 + collapse(§3·§4 — collapse = 최대 band 점유율)

| profile | 분포 | collapse |
|---|---|--:|
| B0 | {"moderate": 15, "weak": 5, "strong": 13} | 0.455 |
| B1 | {"weak": 8, "moderate": 15, "strong": 10} | 0.455 |
| B2 | {"weak": 10, "moderate": 12, "low": 2, "strong": 9} | 0.364 |
| B3 | {"weak": 10, "moderate": 14, "low": 2, "strong": 7} | 0.424 |

### B0 대비 band transition(§6 — 보수화 방향만 허용)

| profile | transition | (역방향 위반은 §0 게이트) |
|---|---|---|
| B1 | {"moderate->weak": 3, "strong->moderate": 3} | |
| B2 | {"moderate->weak": 7, "weak->low": 2, "strong->moderate": 4} | |
| B3 | {"moderate->weak": 7, "weak->low": 2, "strong->moderate": 6} | |

### near-threshold(§8 · |v−thr|≤0.5 · SF30/B0)

weak 0 · moderate 3 · strong 1

### root=N strong rate(§5 · 분모=root=N & EVALUATED · SF30 발췌)

| band | root별 rate |
|---|---|
| B0 | {"root_1": {"n": 24, "strong": 4, "rate": 0.167}, "root_2": {"n": 7, "strong": 7, "rate": 1.0}, "root_3": {"n": 1, "strong": 1, "rate": 1.0}, "root_4": {"n": 1, "strong": 1, "rate": 1.0}} |
| B1 | {"root_1": {"n": 24, "strong": 1, "rate": 0.042}, "root_2": {"n": 7, "strong": 7, "rate": 1.0}, "root_3": {"n": 1, "strong": 1, "rate": 1.0}, "root_4": {"n": 1, "strong": 1, "rate": 1.0}} |
| B2 | {"root_1": {"n": 24, "strong": 0, "rate": 0.0}, "root_2": {"n": 7, "strong": 7, "rate": 1.0}, "root_3": {"n": 1, "strong": 1, "rate": 1.0}, "root_4": {"n": 1, "strong": 1, "rate": 1.0}} |
| B3 | {"root_1": {"n": 24, "strong": 0, "rate": 0.0}, "root_2": {"n": 7, "strong": 5, "rate": 0.714}, "root_3": {"n": 1, "strong": 1, "rate": 1.0}, "root_4": {"n": 1, "strong": 1, "rate": 1.0}} |

## 3. 핵심 발견 — secondary_factor는 공유 계수

> **리뷰 §10의 'activation 전용' 가정과 코드가 다르다.** secondary_factor는 `_primary_plus_secondary`로 **activation·stability_pressure·separation 세 축의 same-root 복합에 동일 적용**된다(spec §3 affected_axes에 이미 명시). 따라서 P2-1A raw sweep은 activation뿐 아니라 same-root 사례의 stability(net)·separation value도 함께 움직인다. stability_support(순수 sum)·status·root/evidence count는 SF 불변임을 게이트로 확인했다.

> **함의(P2-1C 전달)**: secondary_factor를 축별로 분리할지(activation vs stability/separation 별도 계수) 여부는 P2 캘리브레이션 결정 사항이다. 현 단계는 공유 계수 사실을 확정·관측만 한다(수정 없음).

## 4. 관찰 분류(§12 — 최적 profile 선정 아님)

- 이 결과는 P2-1B(쟁합)·P2-1C(kind/stability/separation OAT) 실험 범위를 좁히는 자료다. baseline 대비 raw·band 민감도가 큰 SF·profile을 표시하되 운영 채택 후보로 선정하지 않는다.
- 분모 분리(§3): 본 표는 **lattice** 전용. 331 harness·불변식 fixture와 합산 금지.

