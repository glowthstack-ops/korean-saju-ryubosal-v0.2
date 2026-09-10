# 이벤트 채점 3층 판정 모델 도입 제안 (권장 순서 5 — shadow 진단, 2026-09-10)

> 상태: **제안(승인 대기)**. 라이브 코드 무변경. 근거 수치는 40명식 × 2026년(연운+월운) shadow
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
