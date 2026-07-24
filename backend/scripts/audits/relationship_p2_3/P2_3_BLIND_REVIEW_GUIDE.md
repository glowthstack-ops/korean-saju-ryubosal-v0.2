# P2-3 블라인드 감수 가이드 (감수자용)

> 관계 벡터 계수 profile을 **블라인드**로 감수합니다. profile 이름·baseline·legacy는
> 의도적으로 감추어져 있습니다. 감수 프로토콜 전체는
> `doc/v2_2/RELATIONSHIP_P2_3_REVIEW_TEMPLATE.md`를 따릅니다.

## 무엇을 감수하나

각 사례에서 여러 profile(라벨 A~G)이 같은 관계 구조에 대해 만든 **3축 값**을 비교하고,
각 축이 명리 의미상 **적절한지**를 독립적으로 판단합니다.

- **activation** = 관계 영역이 움직이거나 활성화되는 정도 (≠ 길흉·성사·결혼 가능성)
- **stability** = 관계 유지 품질(net = 결속 support − 압력). 음수 = 유지 압력 불리
- **separation** = 종료 압력(충·형·파·해 계열이 있을 때만 평가)

## 감수지(`p2_3_blind_review_sheet.csv`) 열

| 열 | 의미 |
|---|---|
| `review_case_id` | 사례 식별자(실 명식·기간 미노출) |
| `root_count` | 독립 운 신호(root) 수 |
| `kind_combo` | 관계 종류 조합(예: CHUNG+HYEONG = 충+형) |
| `structure` | single / same_root_compound / multi_root |
| `has_modifier` | 구조 modifier(쟁합 등) 적용 여부 |
| `profile_label` | 블라인드 라벨(A~G) — 사례마다 표시 순서 무작위 |
| `display_slot` | 이 사례에서의 표시 순번 |
| `activation_band` / `_raw` | 활성 band(low/weak/moderate/strong/insufficient)·원시값 |
| `stability_net` / `_sign` | 유지 net·부호(pos/neg/zero/insufficient) |
| `separation_band` / `_raw` | 종료 압력 band·원시값 |

> `insufficient` = 근거 부족(미평가). **0과 다릅니다** — 0으로 읽지 마세요.

## 응답 (같은 CSV의 빈 열에 기입)

각 (사례 × profile_label)마다:

```
activation_judgment : too_weak | appropriate | too_strong | insufficient_basis
stability_judgment  : pressure_under | appropriate | pressure_over | insufficient_basis
separation_judgment : under | appropriate | over | insufficient_basis
```

사례 단위(아무 행에나 1회):
```
no_meaningful_difference : yes   (profile 간 의미 있는 차이가 없다고 판단하면)
```

선택적 근거 태그(`basis_tag`) — 자유 서술 대신 고정 태그 병행 가능:
```
single_root_over · same_root_compound_over · cross_root_underseparated ·
hap_support_over · negative_pressure_over · separation_over · negligible · insufficient_basis
```

## 하지 말 것

- 억지로 "우승 profile"을 고르지 마세요 — 차이가 미미하면 `no_meaningful_difference`.
- 특정 profile이 baseline/production이라고 추측해 유리하게 보지 마세요(라벨은 무작위).
- legacy 후보·delta를 정답으로 삼지 마세요(감수지에 없음).

## 제출물

응답을 채운 `p2_3_blind_review_sheet.csv`. 집계·라벨 개봉(answer key)·C0/C1 및 weight
결정은 감수 종료 후 P2-4에서 진행합니다(자동 규칙 아님 — §10).
