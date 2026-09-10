# 이벤트 채점 3층 판정 모델 도입 제안 (권장 순서 5 — shadow 진단, 2026-09-10)

> 상태: 2026-09-10 사용자 승인 → **P0 완료·P1-a 적용 완료**(§7). P1-b(채널화)·P2 는 §4 대로 후속. 근거 수치는 40명식 × 2026년(연운+월운) shadow
> (`EventEngineV2.score`, contributions 재구성 ablation). 스크립트는 세션 스크래치패드
> (`shadow_layer_ablation.py`, `shadow_stage_saturation.py`) — 채택 시 `backend/scripts/` 로 이관.

## 1. 배경

오늘의 운세(docs/17 §22)는 2026-08-24 전문 리뷰를 받아 채점을 **required_signature(출전권) /
prior(순위) / evidence(가산)** 3층으로 분리하고, 12운성을 ±점수가 아니라 **기능 채널**(활동↑·과속·
체력↓·둔화·이탈·수렴·재생 + 흔들림·단장·노련·구상)로 바꿨다. 그 뒤 사문 감점·게이트-evidence 불일치를
기계적으로 잡는 회귀가 가능해졌다. 리포트·채팅의 메인 채점(`event_engine_v2._score_target`)은 아직
6계층 **정수 델타 가산**이다: brancher base → 12운성(±18 cap) → layer_flow → addendum gate →
relation/palace → yongi quality → ranker.

## 2. 현행 파이프라인의 3층 대응 (매핑)

| 3층 | 현행 계층 | 비고 |
|---|---|---|
| required(출전권) | `ten_god_brancher`(운 십성 단일·군·특정 조합 규칙이 사건 후보를 **생성**) | 후보가 존재한다 = 십성 게이트 통과. 관계·12운성·궁성은 출전권이 아니라 전부 가산 |
| prior(순위) | 규칙 base score(예: SINGLE_BIJIAN→social_conflict 34) × transit_source_strength | 사건별 prior 와 신호 강도가 한 값에 섞여 있음 |
| evidence(가산) | stage ±18 / flow / gate / relation / yongi / daewoon_transition / rank | 전부 정수 델타, cap 은 stage 만 |

## 3. shadow 진단 (40명식 × 2026, 후보 6,272건 · 기간 440)

**층별 기여 비중(|contribution| 평균 비율)**: base 50% · flow 14% · stage 14% · relation 7% ·
daewoon_transition 5% · yongi 5% · gate 2% · rank 1%.

**ablation — 한 층을 0으로 두면 선별이 얼마나 바뀌나**

| 제거 층 | 기간별 top 사건 변경 | 연간 raw Top-5 집합 변경(명식 비율) |
|---|---|---|
| base | 30.7% | 92.5% |
| daewoon_transition | 31.4% | 57.5% |
| flow | 21.6% | 72.5% |
| relation | 20.7% | 92.5% |
| stage(12운성) | 16.1% | 57.5% |
| rank | 8.9% | 30.0% |
| gate | 2.5% | 35.0% |
| yongi | 1.4% | 42.5% |
| daewoon_hwa | 0.0% | 2.5% |

**12운성 보정 포화(핵심 발견)**: stage 기여값이 상한 +18 에 붙은 후보가 **46%**(−18 은 1%).
스테이지별 평균·상한 비율: 장생 13.9(69%) · 제왕 13.0(62%) · 건록 11.7(54%) · 목욕 11.4(49%) ·
태 10.3(43%) · 사 7.1(24%) · 절 6.1(30%) · 병 3.9(21%). 즉 12운성은 "사건 상태를 정한다"는 사전
원칙(`twelve_stage_modifier.core_principle`)과 달리 **대부분 +18 상수**로 작동하고, 사(死)·절(絶)·
병(病)조차 절반 이상이 양수다. daily 진단(십성·12운성이 채점 입력일 뿐 결과에 닿지 않음)과 같은 구조.
원인은 `stage_modifier_rules`의 good_for/caution_for 가 사건별로 넓게 열려 있고 `_combo_bonus` 가
가산돼 cap 에 닿기 때문(코드: `twelve_stage_modifier.apply` 104~113행).

**yongi(용신 품질) 층의 순위 영향은 1.4%** — 길흉(quality)은 바꾸지만 순위에는 거의 관여하지 않는다.
이것은 설계 의도(길흉=용신, 사건 종류=십성, 판정 우선순위 메모리)와 부합하므로 결함이 아니다.

## 4. 제안 — 단계별(전부 shadow-first, 라이브는 승인 후)

**P0 (점수 불변, 즉시 가능)** — 진단 상설화
- `scripts/audit_event_layer_ablation.py`(maintained allowlist) + 회귀: "12운성 기여값 상한 포화율 ≤ X%"
  같은 상한은 명리 판단이라 **측정만** 고정(수치 상한 강제는 승인 후).
- contributions 에 층별 기여가 이미 있으므로 추가 계측 비용 없음.

**P1 (12운성 기능 채널화, 채점 변경 → 승인 필요)**
- `twelve_stage_modifier` 를 "스테이지 → 사건별 ±mag" 에서 "스테이지 → 기능 채널 값(§22-2 표 + §22-8
  잔여 4채널)" 로 바꾸고, 사건별 evidence 가중을 사전(`twelve_stage_modifier.json` 신규 섹션)에 둔다.
  cap 은 채널 합에 1회만. 제안 가중은 daily 카탈로그(v2)의 12운성 evidence 를 **참고 초안**으로
  삼되(사건 키가 다르므로 1:1 아님), 표는 사용자 승인 대상.
- 검증: 현행 대비 기간별 top 변경률·Top-5 집합 변경률·스테이지별 평균 델타 분포(포화 해소 여부).

**P2 (required/prior/evidence 분리)**
- brancher base 를 prior(사건별 3등급) 와 신호 강도(evidence) 로 분리, 관계·궁성·게이트를 사건별
  required_signature 로 선언(daily §22-1 방식). 회귀: 게이트 리프 evidence 필수·감점 채널 도달
  가능·signature 성립 가능성 연 전수(daily 에서 이식).
- 선례: `career_effect_vector.REQUIRED_GATES/GATE_AXIS/ContributionRole`(shadow 검증 완료),
  `risk_scoring.atom_semantics`(CAUSE/GATE/ACTIVATION 분리).

## 5. 승인이 필요한 결정

1. P0 진단 상설화 착수 여부(점수 불변).
2. P1 12운성 채널화의 사건별 가중 표 — 초안은 착수 승인 후 작성해 별도 제시.
3. P2 착수 시점(P1 결과를 본 뒤 권장).

## 6. 관련

- 권장 순서 1~4 결과: WORKLOG 2026-09-10 항목들, `test_dead_path_regressions.py`, `test_compiled_snapshot_drift.py`,
  `test_tone_layer_transfer.py`, `test_selection_contradiction_guard.py`.
- 클론 캡(순서 4 — 2단계) 승인 대기: period×지배 신호 ≤2 + 재충원(채팅 13/40·리포트 40/40 명식 변화).

## 7. 적용 이력 (2026-09-10 승인 후)

**P0 — 진단 상설화(점수 불변).** `scripts/audit_event_layer_ablation.py`(maintained allowlist) +
`tests/unit/test_event_layer_ablation_audit.py`(형태·범위·결정론만 고정, 상한 강제 없음).

**P1-a — 12운성 보정 층 누적 제거 + 조합 보너스 조건 전수 평가 + 기여 분리.** 포화의 원인은 둘이었다.
1. `TwelveStageModifier.apply` 가 source_layer 마다 단계 보정을 **누적**(세운 +12, 월운 +15, 대운 +10 …).
   → 사건 성숙도 우선 층 하나(세운>월운>대운>일운 — phase 를 정하던 층)만 적용.
2. `_combo_bonus` 가 `wolwoon_*`·`ilwoon_*`·`sewoon_has_event_candidate` 조건을 **평가하지 않아**,
   그 조건만 가진 `SEWOON_EVENT_WOLWOON_ILWOON_TRIGGER`(+8, 전 사건)가 모든 후보에 무조건 붙었다.
   → condition 의 모든 키 평가, 미지 키는 fail-closed. 조합 보너스는 `stage_combo` 기여로 분리,
   상한은 문서 불변식대로 합계 ±18 유지.

재측정(40명식 × 2026, 같은 스크립트):

| 지표 | 수정 전 | 수정 후 |
|---|---|---|
| stage 기여 +18 포화율 | 45.5% | **0.0%** |
| 스테이지 평균(제왕/건록/장생/목욕/태/사/병/절) | 13.0/11.7/13.9/11.4/10.3/7.1/3.9/6.1 | **11.1/6.8/5.1/3.0/2.2/−2.0/−4.9/−5.3** |
| stage 제거 시 기간 top 변경 | 16.1% | 10.7% (부풀려진 상수분 제거) |
| stage_combo |기여| 비중 | (stage 에 섞임) | 0.2% (조건 성립 시에만) |
| 수정 전후 기간 top 변경 / 연간 Top-5 집합 변경 | – | 23.9% / 80.0% |

읽기: 사(死)·병·절이 음수, 제왕·건록·장생이 양수 — 사전 `score_modifier` 의 의도가 처음으로 순위에
반영된다. 변경 폭(기간 top 24%)은 크지만 "12운성이 사건 상태를 정한다"는 사전 원칙의 복원이다.
회귀: 기존 `test_twelve_stage_modifier.py`(단일 층·감점·조합·상한) 전부 통과.

## 8. P1-b 초안 — 12운성 기능 채널 evidence 표 (승인 대기, 라이브 미적용)

유도 규칙(기계적·새 명리 판단 없음): 스테이지→채널 대응은 daily §22-2 + §22-8(장생→재생 / 목욕→재생·흔들림 /
태·양→재생·구상 / 관대→활동↑·단장 / 건록→활동↑ / 제왕→활동↑·과속 / 쇠→체력↓·노련 / 병→체력↓·둔화 / 사→둔화·이탈 /
절→이탈 / 묘→수렴). 사건별 `event_specific_modifiers.boost/reduce_stages`(없으면 `stage_modifier_rules.good_for/caution_for`)의
스테이지를 채널로 펼쳐 ±1 씩 세고, 최대 |값| 을 .4 로 정규화(.1 단위). 즉 **현행 사전이 이미 말하는 것을 채널 언어로
옮긴 것**이며, 가중의 절대 크기·부호 재검토가 승인 대상이다.

| 사건 | 채널 evidence 초안 |
|---|---|
| career_change | disengage +0.4, renewal +0.2, unsettled +0.2, stamina_down +0.2, seasoned +0.2, pace_down +0.2, activity_up -0.2 |
| job_gain | activity_up +0.4, pace_down -0.3, disengage -0.3, renewal +0.1, poised +0.1, overdrive +0.1, stamina_down -0.1 |
| promotion | activity_up +0.4, stamina_down -0.3, poised +0.1, overdrive +0.1, seasoned -0.1, pace_down -0.1, disengage -0.1 |
| business_start | renewal +0.4, activity_up +0.3, incubation +0.3, pace_down -0.3, poised +0.1, stamina_down -0.1, disengage -0.1, closure -0.1 |
| business_expansion | activity_up +0.4, stamina_down -0.4, pace_down -0.4, renewal +0.2, unsettled +0.2, overdrive +0.2, seasoned -0.2, disengage -0.2, closure -0.2 |
| wealth_change | activity_up +0.4, overdrive +0.2, closure +0.2, stamina_down -0.2, pace_down -0.2 |
| windfall | unsettled +0.4, overdrive +0.4, pace_down -0.4, disengage -0.4, closure -0.4, incubation -0.4 |
| contract_document | activity_up +0.4, poised +0.2, closure +0.2, renewal -0.2, unsettled -0.2, stamina_down -0.2, pace_down -0.2, disengage -0.2 |
| education_admission | renewal +0.4, activity_up +0.2, poised +0.2, incubation +0.2, stamina_down -0.2, pace_down -0.2, disengage -0.2 |
| education_completion | renewal -0.4, activity_up +0.3, incubation -0.3, poised +0.1, pace_down +0.1, disengage +0.1, closure +0.1 |
| relationship_change | renewal +0.4, unsettled +0.1, incubation +0.1 |
| new_relationship | renewal +0.4, unsettled +0.1, pace_down -0.1, disengage -0.1, closure -0.1, incubation +0.1 |
| marriage_signal | activity_up +0.4, poised +0.2, renewal -0.2, unsettled -0.2, disengage -0.2, stamina_down -0.2, pace_down -0.2 |
| childbirth | renewal +0.4, incubation +0.3, stamina_down -0.1, pace_down -0.1, disengage -0.1 |
| relocation | renewal +0.4, unsettled +0.2, disengage +0.2, activity_up -0.2 |
| legal_conflict | activity_up -0.4, overdrive +0.4, renewal +0.4, unsettled +0.4, disengage +0.4, stamina_down +0.4, pace_down +0.4, poised -0.4 |
| health_attention | stamina_down +0.4, pace_down +0.4, disengage +0.4, seasoned +0.2, renewal -0.2, activity_up -0.2 |
| social_conflict | activity_up -0.4, overdrive -0.4 |
| preparation_delay | stamina_down +0.4, pace_down +0.4, disengage +0.4, seasoned +0.2, closure +0.2, renewal +0.2, incubation +0.2 |
| creative_output | renewal +0.4, incubation +0.2, unsettled +0.1 |
| public_exposure | renewal +0.4, unsettled +0.4, activity_up +0.4, overdrive +0.4, pace_down -0.4, disengage -0.4, closure -0.4 |

적용 방식(승인 시): `TwelveStageModifier` 가 성숙도 우선 층의 스테이지 → 채널 값(§22-2 가중)을 만들고
`Σ evidence×채널값 × 스케일(현행 |score_modifier| 평균 ≈ 8)` 을 `stage` 기여로 싣는다(상한 ±18 유지). 검증은 P1-a 와
같은 ablation(포화율·스테이지 평균 분포·기간 top 변경률) + 회귀(daily 이식: 감점 채널 도달 가능·gate-evidence 정합).
