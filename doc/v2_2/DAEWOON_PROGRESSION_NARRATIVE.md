# 대운 발현 진행(Progression) 서술 레이어 — 스펙 (2026-07-21 데굴님 확정)

> 하드 "전반 0-4년 천간 / 후반 5-9년 지지" 분할 서술을 폐기하고, **기본 그라데이션 prior +
> 즉시 발동 예외 모드**로 대체한 서술 전용(inert) 레이어의 단일 규격 문서(SSOT).

## §1 목적

대운 간지의 역할(천간=계기·드러남 / 지지=현실 기반·정착)과 발현 순서를 LLM이 일관되게
서술하도록 하되, **사건 생성·점수·길흉·confidence를 절대 변경하지 않는다.** "운 후반이
되어야 지지가 작동한다"는 오답과 "상반기 천간 사건/하반기 지지 사건" 단정을 차단한다.

## §2 용어 — 네 개의 독립 축 (혼동 금지)

| 축 | 의미 | 구현 위치 | 성격 |
|---|---|---|---|
| A. 출처 역할(source semantics) | 천간=외부 노출·계기·명분, 지지=환경·관계·현실 조건, 간여지동=동시 활성 | `transit_ten_god_branching_addendum.json` `transit_source_strength`(stem 1.0/branch_main 0.9/…) | 시간 무관 의미론 — **계산 사용, 유지** |
| B. 운 층위 비중(granularity weighting) | 운의 시간 규모별 천간:지지 반영 비율(대운 0.35:0.65 등) | `luck_cycles._PERIOD_WEIGHTS` | 계산 prior — **유지. 대운 1년차/9년차 차이를 뜻하지 않음** |
| C. 운 내부 진행률(progression prior) | 한 대운 안에서 계기 선인식 → 현실화 누적 경향 | 본 레이어(`daewoon_progression`) | **서술 전용 prior — 연차 경계 없음** |
| D. 발동 예외(activation override) | 충·형·합국·공망 발동·천간 작동성이 C의 순서를 뒤집음 | 본 레이어의 모드 판정 | C보다 **우선** |

## §3 불변식 (회귀 테스트로 고정 — `tests/unit/test_daewoon_progression.py`)

1. 진행률·progression 모드는 사건 생성·기본 점수·길흉·confidence·후보 수·시점 후보에
   관여하지 않는다 (`usage="narrative_only"`, resolver는 입력을 변경하지 않음).
2. 발동 예외 모드가 기본 그라데이션 서술보다 우선한다.
3. 세운은 상·하반기로, 월운은 월초·월말로 나누는 서술을 도입하지 않는다.
4. 정확한 발동 시점은 세운·월운 층위 결합(`layer_flow_modifier`)과 Activation Window가
   담당한다 — 본 레이어는 시점을 지정하지 않는다.
5. 하드 연차 분할 문구("전반 0-4년"/"후반 5-9년"/"주도")를 디렉티브·데이터 블록에
   재도입하지 않는다. (구 `DaewoonItem.first_half_focus`/`second_half_focus` 필드 삭제,
   2026-07-21 — 소비처 0건 확인 후.)

## §4 기본 prior (default_gradient)

> 천간이 나타내는 계기·외부 변화가 **상대적으로 먼저 인식**되고, 시간이 지나며 지지가
> 나타내는 생활환경·관계·현실 조건이 **누적·구체화**되기 쉽다.

- "주도"가 아니라 "상대적으로 드러나기 쉬움"으로 표현한다.
- 정확한 연차 경계(0-4/5-9, 60:40 등 수치)를 두지 않는다.

## §5 모드와 판정 우선순위

모드: `default_gradient` / `branch_early_activation` / `stem_persistent` / `coactivated` /
`weak_manifestation` / `indeterminate` (`saju_shared_types.daewoon_progression.ProgressionMode`)

입력 신호(전부 기존 계산값 — `resolve_daewoon_progression()`은 읽기만 한다):

- 지지 조기 발동: `relations_to_chart`의 핵심 궁위(일지·월지) 충·형, `삼합완성`/`방합완성`,
  `삼형`(일지 관여 조건은 luck_cycles가 이미 검사), `gongmang_activation`의 `공망발동(충)`
- 천간 작동성: 운 천간의 **운 지지 자체** 통근(본기·중기, 여기 제외) — 원국 어딘가의 뿌리까지
  인정하면 거의 모든 대운이 지속형이 되므로 지속 판정은 운 지지 통근으로 좁힌다. 원국 통근은
  무근(약발현) 판정에만 사용. `천간합:` 존재 시 무근이면 합거(`STEM_COMBINED_AWAY`),
  통근이면 합반(`STEM_COMBINED_BOUND`, 지속성 배제)
- 간여지동: `stem_ten_god == branch_ten_god`
- 작동 저하: 운 지지 공망 전실(`branch_effect.is_void`이고 충 발동 없음), 천간 무근

우선순위 (위가 먼저):

1. 공망 전실 + 합국 완성 동시(상충) → `indeterminate`
2. 지지 조기 발동 + 천간 작동성 강 → `coactivated`
3. 간여지동(지지 공망 아님) → `coactivated`
4. 지지 조기 발동 → `branch_early_activation`
5. 운 지지 통근 + 미합 → `stem_persistent`
6. 천간 무근/합거 + 지지 공망 → `weak_manifestation`
7. 그 외 → `default_gradient`

## §6 표면화 (LLM 입력)

- 디렉티브: `structural_context.DAEWOON_FRAMING_DIRECTIVE` — 기본 prior + 예외 가능성 문구
  (report F-07/F-10/F-13/Y-03 + chat `_wants_daewoon_frame` 공용).
- 예외 블록: `structural_context.daewoon_progression_lines()` — **예외 모드 대운만** 개별
  표기(전부 default면 무언급), 헤더에 "서술 전용(점수·순위·시기·확신도 변경 금지)" 명시.
- 대운표 행: `report_service.luck_block()` 각 행 접미 `발현 {모드 라벨}`
  (`PROGRESSION_MODE_KO`).
- LLM에는 원시 합충 목록의 재해석을 맡기지 않고 엔진이 확정한 모드 요약만 준다(절대원칙 1).

## §7 도메인별 발현 순서 표현 (참고 — 기존 SSOT 우선)

- 이사: 천간=명분 → 지지=현장 (`RELOCATION_ENHANCEMENT.md`)
- 결혼: 천간 자극=생각·끌림(awareness) → 지지 합=행동(action) (`MARRIAGE_TIMING_ENHANCEMENT.md`)
- 취업/재물/건강 등 확대는 P2 범위 — 별도 승인 후.

## §8 이번 범위 제외 (보류)

- P2: 도메인별 manifestation 표현 확대.
- P3: 진행률의 수치화(점수·confidence 보조값) — 실사용 데이터에서 진행률-사건 시점 상관이
  확인될 때만 재검토. 60:40류 수치를 처음부터 점수에 넣지 않는다(중복 가산·점수 포화 위험).
