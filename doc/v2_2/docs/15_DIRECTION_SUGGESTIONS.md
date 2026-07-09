# 15. 능동 제안 계층 (Direction Suggestions)

> E8 Advice Engine(docs/02 §E8, 로드맵 T5.5)의 실구현. 수동 답변을 넘어 "이런 식으로
> 진행해보는 것도 고려해볼 만하다" 수준의 방향 제안을 **엔진이 판정**하고 LLM은 재서술만 한다.
> 원형 사례(정재 과다 + 상관 작동 → 본업 유지 + 부업형 수익화 소규모 검증)는 2026-07-09
> 데굴님 정리·승인.

## 1. 원칙

1. **LLM 판정 금지(절대원칙 1)**: trigger/channel/guard 매칭은 전부 엔진 계산. LLM은
   direction/caution 재료를 "고려" 톤으로 재서술만 한다.
2. **십성 단독 판정 금지(다요소 원칙)**: 룰의 trigger+channel 조건 축(kind)이 2종
   이상이어야 하며 lint가 강제한다. 신강약·용신/기신·작동성·구조패턴·충파를 함께 본다.
3. **guard = 차단이 아니라 서술 반전**: 위험 조건 매칭 시 제안을 삭제하지 않고
   `mode=caution`으로 전환 — caution_headline + 매칭 guard note가 권장 서술보다 앞선다.
   (예: "부업 확장 권장" → "지출·부채·계약 부담 주의")
4. **단정 금지(절대원칙 3)**: direction 문구는 "~해보는 것도 고려해볼 만하다" 수준.
   확장보다 검증 우선. `forbidden_framings`(퇴사 권유·수익 확정·픽 제공 등)로 차단.
5. **사전 파이프라인(절대원칙 5)**: validate → compile(snapshot) → regression 후 배포.

## 2. 십성군 상태 판정 (원국+운 합산 — 2026-07-09 사용자 확정)

원국 십성군(비겁/식상/재성/관성/인성) 분포에 **대운·세운 간지를 추가 글자로 합산해
재계산**한다(지지=본기 십성, 지장간 가중은 원국 방식 재사용). 임계는 기존 오행 과다
기준 재사용: **과다 ≥35%, 부족 <9% 또는 본기 무존재**.

| 상태 (`GroupStateValue`) | 의미 |
|---|---|
| `natal_excess` | 원국 과다 |
| `luck_excess_onset` | 원국 정상 → 운 유입으로 임계 돌파 |
| `excess_intensified` | 원국 과다 + 운 동일군 유입 (심화) |
| `natal_deficient` | 원국 부족 |
| `deficient_persistent` | 원국 부족 + 운 보충 없음 |
| `luck_replenished` | 원국 부족 + 운 유입 — **경고가 아니라 기회 창** |
| `luck_inflow` | 임계 무관 운 유입 (보조 조건 전용) |

`luck_replenished` 채널에는 `yongsin_role ∈ {용신, 희신, 한신}` 게이트가 붙는다 —
보충되는 군이 기신·구신이면 "기회 창" 서술을 하지 않는다(길흉=용신/기신 우선).

## 3. 구성 요소

| 구성 | 위치 |
|---|---|
| 타입 | `backend/packages/shared_types/saju_shared_types/direction_suggestions.py` |
| 사전 원본 | `backend/dictionaries/direction_suggestions.json` (schema `direction_suggestions.v1`) |
| 스키마 등록·lint | `saju_engines/dictionaries.py` — `_lint_direction_suggestions` |
| 스냅샷 빌드 | `backend/scripts/build_direction_suggestions_snapshot.py` → `compiled/direction_suggestions_v1.0.0.json` |
| 테스트 | `backend/tests/unit/test_direction_suggestions_dict.py` (사전), `test_direction_suggestion_engine.py` (엔진) |
| 판정 엔진 | `saju_engines/direction_suggestion.py` — 로더·`build_direction_facts`·`evaluate_direction_suggestions` |

### 조건 프리미티브 (`SuggestionCondition.kind`)

| kind | 엔진 매핑 (Phase B) | 필수 필드 |
|---|---|---|
| `group_state` | §2 합산 과다/부족 계산 | group, states |
| `ten_god_status` | 존재(present/absent) + 작동 계층(active/inactive/not_active) | ten_gods, status (+match any/all) |
| `yongsin_role` | 용희기구한 정적 배정 | target(십성 로마자 또는 군), roles |
| `strength_band` | 신강약 9단계 | bands |
| `pattern` | 구조패턴 68종 감지(`detect_structure_patterns`) | pattern_ids |
| `conflict` | 해당 군 지지의 충·형·파·해 | group, conflict_kinds |

### 룰 발화 의미

`trigger`(AND) 성립 + `channels` 중 1개 이상 성립 → 제안 후보 생성.
성립 채널이 없으면 제안 없음. `supports` 매칭은 strength만 상향, `guards` 매칭은
`mode=caution` 반전. guards가 있으면 `caution_headline` 필수(lint).

## 4. 시드 10종 (5개 십성군 × 과다/부족 — 2026-07-09 승인 매트릭스)

| suggestion_id | 통로(채널) | guard 반전 |
|---|---|---|
| WEALTH_EXCESS | 상관 작동→부업형 수익화 검증(원형) / 식신 작동→점진 확장 / 신약+비겁운→득비이재 조력 | 신약·상관기신·상관견관·쟁재/탈재·편재동반·재성충파·관살압박·재생살 |
| WEALTH_DEFICIT | 운보충→수익화 시도 창 / 식상생재→역량 상품화 | 비겁과다(군겁쟁재)·탐재괴인 |
| AUTHORITY_EXCESS | 인성 작동→살인상생 전환 / 식상 작동→제살 협상 | 신약·재생살·인성부재 |
| AUTHORITY_DEFICIT | 운보충→취업·계약·직책 창 / 재성 작동+재생관→성과의 지위 연결 | 상관견관·상관작동 |
| RESOURCE_EXCESS | 식상 작동→축적의 출력 / 재성 작동→실리 기준 도입 | 식상부재·편인도식 |
| RESOURCE_DEFICIT | 운보충→기반(자격·문서·조력) 정비 창 | 관살압박(완충 부재) |
| PEER_EXCESS | 식상 작동→설기 / 관성 작동→규칙 제어 | 재성약(군겁쟁재)·쟁재패턴·관성부재 |
| PEER_DEFICIT | 운보충→주도·협력 확보 창 (재다신약이면 득비이재 호기=support) | (없음 — 강도 조절만) |
| OUTPUT_EXCESS | 재성 작동→식상생재 수렴 / 인성 작동→마무리 제어 | 재성부재·상관견관·관약+상관작동 |
| OUTPUT_DEFICIT | 운보충→발신 시도 창 | 인성과다(도식 위험) |

십성 세분(정재/편재, 정관/편관 등) 분기 콘텐츠는 Phase D에서 modifier로 확장한다.

## 5. Phase B 판정 엔진 확정 규칙 (`saju_engines/direction_suggestion.py`)

목적 재확인: 이 계층은 특정 도메인(부업 등) 추천기가 아니라, **원국과 운에서 읽히는
가능성을 능동적으로 짚어주는 범용 레이어**다(2026-07-09 데굴님 확인). 시드 10종은
5개 십성군 전반(재물·조직·표현·관계·기반)을 커버하며 도메인 확장은 룰 추가로 한다.

### 5-1. 합산 분포 (`_group_percents`)
- 원국: 표시 분포 가중 재사용 — 천간 각 10(일간 제외), 지지 年15·月25·日15·時15
  × 지장간 비율(`hidden_stems_for`). 시주 미상이면 3주.
- 운 글자: 현재 대운·세운 간지를 **원국 연주급**으로 합산 — 천간 10, 지지 15×지장간
  비율. 합산 후 재정규화(100%).
- 현재 운은 `luck_cycles.current_daewoon_index`/`yearly_luck[current_year]`
  (sinsal_modifier `_current_luck` 관행). **`reference_date`가 있어야 채워진다** —
  chat/report 경로는 항상 reference 앵커로 calculate()하므로 충족.

### 5-2. 상태·작동·역할·충파 산출 (`build_direction_facts`)
- 군 상태: natal ≥35 → `natal_excess`(+운 유입 시 `excess_intensified`),
  natal 정상 & 합산 ≥35 → `luck_excess_onset`, natal <9 → `natal_deficient`
  (+운 유입 시 `luck_replenished`, 아니면 `deficient_persistent`), 운 유입 시
  `luck_inflow` 병기. 상태는 집합(복수 성립 허용).
- 운 유입 판정: 대운·세운의 천간 + 지지 본기 십성군.
- **작동(active)**: 원국 천간 투출 또는 지지 본기 노출, 또는 현재 운 간지(천간·지지
  본기) 유입. 지장간 중기·여기에만 있으면 존재(present)하되 비작동(inactive).
- 용신 역할: `yongsin_analysis.canonical_roles`는 **역할 슬러그→오행** 방향이므로
  역전개해 오행→역할로 만들고, `group_elements(일간 오행)`로 군·소속 십성 키에 전개.
- 충파: 원국 `structure_analysis.interactions`(영문 enum: clash/break/harm/
  punishment/self_punishment → 충/파/해/형)와 현재 운 `relations_to_chart`
  ("충:巳-亥" 형식 한글)를 지지 본기 십성군으로 귀속.
- 누락 계층(None)은 빈 값 → 조건 불일치 → 제안 없음(안전 방향).

### 5-3. 평가 (`evaluate_direction_suggestions`, 순수 함수)
- trigger(AND) 성립 + 채널 1개 이상 성립 → 제안. 복수 채널 성립 시 **사전 순서가
  우선순위**(첫 채널 채택, 나머지는 evidence에 `대안채널:`로 기록).
- guard 매칭(조건 AND, 1개 이상) → `mode=caution` 반전: headline은
  `caution_headline`으로 교체, guard note 전부 `cautions`로 누적. actions/avoid
  재료는 유지(LLM이 "방향은 이렇지만 지금은 이 관리가 먼저" 서술 가능).
- strength = 0.5 + 0.15 × support 매칭 수 (상한 1.0). 길흉·사건 점수와 무관한
  제안 강도이며 기존 수치 파이프라인에 영향 없음(inert).
- 출력은 strength 내림차순(동률 시 suggestion_id 순) — 결정적.
- 근거 경로(evidence): 트리거·채널 조건 라벨(`군상태:`, `십성:`, `채널:` 등).

## 6. Phase C LLM 배선 확정 규칙

- **선별**: `select_direction_suggestions` — 질문/섹션 도메인 일치 십성군 우선
  **소프트 필터**(career→관성·식상, wealth→재성·비겁, education→인성·식상,
  relationship→비겁, health→인성 — 타 군 배제 없음), 이후 strength·id 순, **top-2**
  (토큰 가드 하 소수 정예). chat은 intent의 domains(복수)+domain(단수) 합집합 사용
  (복수형이 비는 파서 경로 존재).
- **직렬화**: `format_direction_suggestion_lines` — `[제안 방향 — 엔진 판정 참고
  재료('고려' 수준 서술 전용, 단정 금지)]` 블록. 항목당: (권장|주의) 헤드라인 →
  전제(reality_note) → (주의 모드면 guard note 최대 2) → 해볼 만한 것(≤3) →
  피하는 게 좋은 것(≤3) → 표현 금지. 빈 목록이면 무헤더(토큰 0).
- **chat**: `build_llm_input`에서 판정·선별 후 `LlmInput.direction_suggestions`에 적재,
  `serialize_llm_input` **동적 suffix**에 블록 + `DIRECTION_SUGGESTION_INSTRUCTION`
  ("질문과 관련될 때 답 말미 1~2문장, 무관하면 생략") 부착. **캐시 프리픽스 금지**
  (세운 의존). 미노출 유형: 용어교육·피드백교정·감정지원·범위외
  (`_NO_SUGGESTION_QUERY_TYPES`).
- **report**: `_ReportData.direction_suggestions` 1회 판정 → `build_section_context`에서
  `_SECTION_DOMAIN`이 wealth/career인 섹션(W-06·W-07·J-05·J-06·F-15·F-16·Y-06·Y-07)에만
  블록+지시문 주입. **목차·판정·점수 불변**(절대원칙 10 — 섹션 컨텍스트 재료만 추가).
- 페르소나·점수 파이프라인 영향 없음(inert). 발화 없으면 어디에도 흔적 없음.

## 7. 로드맵 및 상태

- **Phase A (완료, 2026-07-09)**: 타입 + 사전 스키마 + 시드 10종 + validate/lint/snapshot
  파이프라인 + 단위 테스트. **시드 명리 콘텐츠는 데굴님 감수 전(`reviewed: false`)**.
- **Phase B (완료, 2026-07-09)**: 판정 엔진(§5) + 합성 facts·실차트 통합 테스트 16종.
  실차트 8건 스캔에서 7건 발화, 균형 명식은 0건(억지 제안 없음) 확인.
- **Phase C (완료, 2026-07-09)**: 대화+리포트 동시 배선(§6) + 배선 테스트 10종
  (선별·직렬화·프리픽스 순수성·chat 주입/도메인 정렬/미발화·report 주입/비주입).
- **Phase D (예정)**: 십성 세분 modifier·룰 확장, remedy 6분기(docs/08 D-3)와의 연결 정리.
- **운영 전 필수**: 시드 사전 감수(reviewed→true, 스냅샷 재빌드) + 라이브 응답 품질 확인.
