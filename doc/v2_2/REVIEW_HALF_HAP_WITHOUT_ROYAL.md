# 감수 안건 — 왕지 미포함 삼합 부분조합의 성립 기준 통일

> 상태: **미결(격리 중)** · 기록일 2026-07-27 · 결론 문서 아님
>
> 이 문서는 결론을 내리는 문서가 아니다. **현재 왜 제외됐고, 결정할 때 어느 범위를
> 함께 검토해야 하는지**를 보존한다.

## 1. 무엇이 문제인가

같은 글자쌍에 대해 두 엔진이 다른 답을 낸다.

| 엔진 | 위치 | 판정 |
|---|---|---|
| `InteractionDetector` | `saju_engines/interactions.py` | `rel_卯未亥三合` **성립**(부분)으로 기록 |
| `resolve_branch_hap` | `manse_analysis/relations/hap_modes.py` | **미성립** — `반합은 왕지 포함만(다수설)` |

`resolve_branch_hap`은 삼합 반합에서 왕지(子午卯酉)가 없으면 건너뛴다.
따라서 `亥未`(생지+고지)는 탐지는 되지만 의미 판정이 없다.

## 2. 대상 조합

왕지를 포함하지 않는 삼합 2자 조합 전체가 같은 문제를 갖는다.

```
亥未 (亥卯未 중 卯 없음)
寅戌 (寅午戌 중 午 없음)
申辰 (申子辰 중 子 없음)
巳丑 (巳酉丑 중 酉 없음)
```

한쪽으로 통일하면 네 조합이 함께 움직인다.

## 3. 현재 운영 처리 (P1 — 2026-07-27)

`SemanticResolutionStatus.ENGINE_CONFLICT`로 격리한다.

```
formation_confirmed  = False   # 성립 자체가 미확정
narrative_eligible   = False   # 본문 서술 제외
cluster_eligible     = False   # 표현 클러스터 제외
score_eligible       = False   # 점수 제외
                               # 변동성도 반영 금지(formation_confirmed=False)
exclusion_reason     = "탐지기는 성립으로 보지만 의미 판정기는 미성립 — 엔진 불일치"
```

사용자 근거 부록에서도 제외하고, 감사 SSOT(`LuckHierarchy.interactions`)와
telemetry에만 남긴다.

**왜 '의미 미상'으로 흘려보내지 않았는가**: LLM이 자체 명리 지식으로 빈칸을 채운다.
`亥未는 木 반합이니 관성을 강화합니다` 같은 서술이 나오면, P0에서 막으려던 자의적
재해석이 그대로 되살아난다.

## 4. 향후 선택지

1. **왕지 포함 조합만 반합 인정** — `InteractionDetector`에서 해당 후보 제거
2. **생지+고지 조합을 약한 부분 활성으로 인정** — `resolve_branch_hap`에 약한 부분
   성립 규칙 추가 + `PARTIALLY_STRENGTHENED` 강도 별도 정의
3. **관계 후보 탐지와 실제 오행 강화 판정을 분리** — 탐지는 유지하되 강화 효과는 없음

## 5. 결정 시 함께 검증해야 할 범위

어느 쪽으로 정하든 아래가 함께 움직인다.

```
composite (luck_composites 저장분)
period fortune (일·월·연 총운)
이벤트 후보 점수·순위
P3 signal polarity
과거 사전계산 스냅샷
회귀 픽스처
```

특히 2번을 택하면 기존 이벤트 점수가 전반적으로 변하므로 shadow diff와 골든 사례
재검토가 선행되어야 한다.

## 6. 관련 회귀

- `tests/unit/test_luck_hierarchy.py::test_engine_conflict_is_preserved_but_excluded`
- `tests/unit/test_luck_hierarchy.py::test_engine_conflict_never_enters_clusters`

두 테스트가 격리 상태를 고정하고 있으므로, 규칙을 통일할 때 함께 갱신해야 한다.
