# 외부 강의 대조 — 「직장을 그만두거나 이직해야 할 때」(상관견관·편인 도식·겁재) vs 류보살 v2 엔진 (2026-10-29)

> 목적: 데굴님이 붙여 넣은 외부 영상 스크립트(이직·퇴사·직장 생활의 어려움이 오는 사주 성분과 운)를 우리 엔진과 대조하고, 풀이 품질에 쓸 항목을 우선순위로 기획·구현한다.
> 원칙: 강의는 **참고 문헌**이지 지침이 아니다(붙여 넣은 외부 의견과 같은 지위 — 데굴님 발언과 충돌하면 절충하지 않고 묻는다). 강사 스스로 "개인 견해·참고만"이라 전제했고, 우리도 단정 금지 정의(`structural_context.ASSERTION_POLICY`)와 이동 주체 미상 지시를 그대로 둔다. 노출·측정 원칙(2026-10-15): 문구·기능층은 적용(ON) 후 실답 감수, 점수 규칙은 85사례·실사례 적중률로 ON/OFF.
> 조사 방법: 브랜처(`ten_god_brancher`)·시드 3종(`peer_mobility_seed`·`role_event_seed`·MT1)·運破格(`luck_geok_break`)·구조 패턴·서술 사전(`ten_gods_text`·`transit_peer_mobility_text`·`career_fields`)·사건 키 레지스트리 전수 탐색(2026-10-29).

## 1. 요약 판정

| 구분 | 건수 | 비고 |
|---|---:|---|
| 이미 동등 (불채택) | 2 | 천간 중심 유입 강도(천간 1.0·지지 본기 0.9, 시드 stem_only/branch_only), 참고 지나갈 수 있음=단정 금지·이동 주체 미상 |
| 채택 — 점수 규칙(측정 후 ON) | 3 | ① 원국 천간 정관 × 운 상관(환경형) ② 원국 천간 상관 × 운 정관(자기형) — 정인 구응 감쇠 포함, ⑤ 겁재 운 한신·희신·구신 이동 시드, ④ 편인 운 → 휴직 시드(신규 사건 키 `career_leave`) |
| 채택 — 서술층(바로 ON) | 3 | ①②③ 원인 축·정인 완화 문구, ④ 편인 '쉬어가는 운' 문구, ⑥ 원국 연·월 천간 겁재 이동·부업 성향 문구(정관 유무 분기) |
| 결정(2026-10-29 데굴님) | 3 | 원국 쪽은 **천간만**(지지 본기는 측정에서 비교), 휴직 사건 키 **신설**(복귀 전제의 긴 휴가 — 완전 이탈 아님), 겁재 한신 시드는 **겁재 천간만**(비견 제외) |

## 2. 영역별 대조표

| # | 강의 주장 | 현재 엔진(2026-10-29) | 판정 |
|---|---|---|---|
| ① | 원국 천간 정관 + 운(대운·세운) 천간 상관 → 멀쩡히 다니던 직장이 불편해짐: 시스템 변화·상사 교체·부서 발령 — **원인은 환경**(운이 환경을 조성) | `SPEC_SHANGGUAN_ZHENGGUAN`(64)은 **운 스택 안에서** 상관·정관이 함께 들어올 때만 성립 — 브랜처(`ten_god_brancher.branch`)는 운 신호만 조합하고 원국 글자는 참여하지 않는다. 원국 정관×운 상관은 **정관격일 때만** 運破格(`luck_geok_break` → favorability 감점·사건 시드 없음·프롬프트 서술 없음). | 빈 곳(점수+서술) |
| ② | 원국 천간 상관 + 운 천간 정관 → **원인은 나**: 평소 안 하던 실수, 괜한 불만, 충고가 거슬림 | 상관격 運破格 감점만. ①과 ②의 방향(환경/자기)을 구분하는 코드·문구가 없다. | 빈 곳(점수+서술) |
| ③ | ①②에 원국 정인이 있으면 상관 작용을 달래 참고 지나갈 수 있음 | 運破格 구응(정인·편인·재성 → '경향' 강등)에만 있고 격국이 아닌 명식엔 적용 안 됨. 서술 없음. | 부분 → 시드 감쇠(×0.8)+문구 |
| ④ | 운 편인 → 도식(편인이 식신을 극): 식신 유무와 무관하게 직장 생활이 피곤·불안해지고 **일시 휴직**(번아웃·출산휴가)으로 나타나기도. 상관·겁재처럼 '불만'이 아니라 '피곤함' | `SINGLE_PIANYIN`: preparation_delay 41·health_attention 26·education_admission 30. `SPEC_PIANYIN_SHISHEN`(운 스택 도식) preparation_delay 60. 건강 층 "편인 도식 재자극". **휴직 사건 키 없음**(event_keys 21종). | 빈 곳 → 사건 키 `career_leave` 신설 + 시드 + 문구 |
| ⑤ | 운 **천간 겁재** → 이직·퇴사가 가장 많이 발생: 재성(내 지위·공간·무대·종업원·소유)을 흔들고 경쟁자(승진 경쟁·같은 업종 출현)를 만든다 | `SINGLE_JIECAI`: wealth_change 38·social_conflict 41·business_start 26 — career_change 없음. 비겁 이동 시드는 **용신·기신일 때만**(`peer_yongsin/gisin_mobility_rules`); 희신·한신·구신은 비어 있음. | 빈 곳(점수) → 역할 무관 겁재 시드(기준점 낮게) |
| ⑥ | 원국 **연·월 천간 겁재** → 삶의 환경이 불안정하기 쉬워 직장을 자주 옮기고, 한 직업에 충실하기 어렵고, 부업·아르바이트를 두기도. 정관 유무로 달라짐 | `ten_gods_text` 겁재 natal = 승부 근성·배짱(이동 성향 없음). `career_fields` 겁재 = 경쟁 영업·창업·공동사업 직군. 궁위(연·월 천간) 조건 문구 없음. | 빈 곳(서술) → career_field 간지론 블록 |
| ⑦ | 대운·세운 **천간**으로 오는 글자를 본다 | 브랜처 천간 1.0·지지 본기 0.9, 시드 유입 4단계(same_god > same_group > stem_only > branch_only). | 동등 — 같은 표 재사용 |
| ⑧ | 이직·퇴사하지 않고 참고 넘어갈 수도 있으니 참고만 | 단정 금지 정의·이동 주체 미상(`mobility_agency`)·'이동이 걸릴 수 있는 기간' 어휘. | 동등 |
| ⑨ | 여성에게 정관=남편·남자, 오늘은 직장으로 국한 | 질문 도메인별 십성 해석 분리(관성=직업 축 vs 배우자 축)가 이미 있다. | 동등(참고) |

## 3. 개선 기획 — 우선순위·구현 위치·검증

| 순위 | 항목 | 구현 위치 | 데이터 | 검증 |
|---|---|---|---|---|
| P0-1 | **원국×운 상관견관 시드**(점수) — 원국 천간(연·월·시; 일간 제외) 정관 × 채점 대상 운 상관 → career_change(환경형), 대칭 원국 상관 × 운 정관 → career_change(자기형). 유입 4단계 기준점은 비겁 시드와 같은 값(68/58/50/44). 원국(천간·지지 본기)에 정인이 있으면 ×0.8 + `CXL_RESCUE_ZHENGYIN`. 원인 축은 reason_code(`CXL_CAUSE_ENVIRONMENT`/`CXL_CAUSE_SELF`)로만 싣는다. 브랜처 직후 합류 → 6계층 보정 공통 | `saju_engines/career_exit_seed.py` 신규, `event_engine_v2` 합류 지점(역할 시드 뒤), 플래그 `SAJU_CAREER_EXIT_SEED_ENABLED`(기본 OFF) + 규칙별 `enabled`·`rule_ids` | `transit_ten_god_branching.json` → `career_exit_lecture_rules` | 단위 테스트(합성 명식·OFF 불변) + 85사례 off/on 재생 + 생애 사건 원장 측정(`scripts/measure_career_exit_seed.py`) |
| P0-2 | **원인 축·완화 서술층** — 환경형/자기형/정인 완화 문구 3종. 운 유입 십성 1줄(`incoming_ten_god_note`)에 원국 천간 십성을 넘겨 조건에 맞는 문구를 고른다(작문 금지). 시드 플래그와 무관하게 항상 노출 | `chart_interpretation.incoming_ten_god_note(natal_stem_ten_gods=…)`, 호출처 `build_luck_grounding`·`report_event_input._tone_line`·`context_reducer` 후보 note | `interpretations/career_exit_lecture_text.json` + `dictionaries.py` 모델·lint | 사전 lint(id 정확 커버리지·단정 어휘 금지), 단위 테스트, 실답 감수 |
| P1-1 | **겁재 천간 운 역할 무관 이동 시드**(점수) — 비겁 역할이 희신·한신·구신인 명식에 겁재가 운 천간으로 들어오면 career_change(기준점 58/50/44/38 — 용신·기신 시드보다 한 단계 낮게). 비견 제외(데굴님 결정) | 같은 모듈·같은 절 규칙 `CXL_PEER_NEUTRAL_MOBILITY` | 같은 절 | 같은 측정 |
| P1-2 | **편인 운 → 휴직 시드 + 문구** — 신규 사건 키 `career_leave`(휴직·휴가·일시 중단, 복귀 전제 — 완전 이탈 아님). 편인 유입 → career_leave(기준점 58/50/44/38). 문구 "쉬어가라는 운 — 피곤·불안, 휴직이 거론될 수 있음(번아웃·건강·재충전; 여성 명식이면 출산·육아 휴직 형태도)" | 사건 키 레지스트리 전수(`EventKeyV2`·taxonomy_v2 라벨/성격/카테고리·event_forms·taxonomy·intent_event_filter·yonggi_quality_matrix·twelve_stage event_channel_evidence·relationship_event_vocab·process_event_compatibility·opportunity_engine·report_service view) + 시드 규칙 `CXL_PIANYIN_LEAVE` + 문구 | 위 레지스트리 + 텍스트 사전 | 21종→22종 전수 테스트 갱신, 단위 테스트, 실답 감수(원장에 휴직 행이 없어 적중률 측정은 보류 — shadow 관측) |
| P1-3 | **원국 연·월 천간 겁재 성향 문구** — "한 직장에 오래 머물기보다 옮기거나 부업·겸업을 두는 결 / 정관이 있으면 완화" (성향으로만, 단정 금지) | `career_field.py` `_peer_stem_lines` + `CareerFieldFacts.peer_lines`, 간지론 블록 렌더 | `career_fields.json` → `peer_stem` 절 | 단위 테스트 + 실답 감수 |

## 4. 불채택·참고 사유

- "모든 명리가가 동의하지 않음·참고만" — 우리 단정 금지 정의와 같은 지위. 문구에 "참고"를 반복하지 않는다(과도한 면책 금지).
- 겁재의 재성 탈취(돈·여자)는 이미 `SINGLE_JIECAI`·쟁재 규칙에 있다 — 이번 범위는 직장 축만.
- 비견은 강의가 언급하지 않아 제외(데굴님 결정). 비견 천간 운의 이동 시드는 측정 결과를 본 뒤 별도 결정.

## 5. 확인 항목(코드 사실, 2026-10-29)

- 브랜처는 거버닝 스택(대운·세운·월운)의 운 신호만 조합한다 — 원국 십성은 `_natal_ten_gods`(運破格 판정)에만 쓰인다. 따라서 '원국 글자 × 운 글자' 사건 시드는 새 모듈이 필요하다.
- 비겁 이동 시드는 `fav_map[비겁 오행] ∈ {용신}` / `{기신}` 만 — 희신·한신·구신 명식은 후보 0건.
- 사건 키 21종은 `EventKeyV2` + 10개 레지스트리에 전수 테스트가 걸려 있다(`test_event_taxonomy_v2`·`test_event_lexicon`·`test_twelve_stage_modifier`·`test_event_semantic_facets`·`process_event_compatibility`).
- 생애 사건 원장: career_change confirmed 19(월 정밀 16)·not_happened 47(연), resignation(원장 전용) 13(월 정밀 13) — 이직·퇴사 시드 측정 모집단.

## 6. 데굴님 결정 (2026-10-29)

1. P0-1 원국 쪽 글자는 **천간만** — "제안대로 진행".
2. 휴직 사건 키 **신설** — "휴직은 다시 그 회사로 돌아가 일하는 것이라 긴 휴가와 같다. 완전 이탈이 아니다."
3. P1-1 범위는 **겁재 천간만** — "제안대로 진행".

## 7. 구현 결과 (2026-10-29)

- 구현: 사건 키 `career_leave`(EventKeyV2 22종, 레지스트리 10곳) · 점수층 `saju_engines/career_exit_seed.py` + 사전 절 `career_exit_lecture_rules` 4규칙(플래그 `SAJU_CAREER_EXIT_SEED_ENABLED` 기본 OFF, `casebook_replay --career-exit-seed`) · 문구층 `career_exit_lecture_text.json` 6항목(항상 노출, `incoming_ten_god_note(natal=…)` 단일 기간 근거 전용) · career_fields.json `peer_stem` 3칸 · 테스트 `test_career_exit_seed.py` 15건 · 측정 `scripts/measure_career_exit_seed.py`. 상세는 docs/05 절.
- **생애 사건 원장 측정(11명, career_change·resignation 연 72건/양성 26·월 라벨 27건)**: off와 on(절 전체·규칙별 4종)이 **모든 변형(t55·t70·t85·t95·top1·top3)에서 동일** — 연 정밀도 t95 0.413(lift 1.14), 월 top3 정밀도 0.145(lift 1.48). 원인: 규칙이 발동한 달(환경형 42·자기형 104·겁재 역할 무관 62건)에는 브랜처가 이미 career_change 기본점 59~61(상관·정관·겁재 조합 규칙)을 세워 두어, 시드 기준점(천간만 50·간여지동 68)이 최댓값 병합에서 기존 점수를 넘지 못했다(`role_event_seed` 기여 0.0). 즉 이 모집단에서 세 career_change 시드는 **점수에 비활성(inert)** 이며 적중률 변화가 없다. 시드가 실제로 순위를 바꾸는 경우는 브랜처 기본 가지가 낮거나 없는 달(예: 2026-10 겁재 간여지동 실사례 같은 비겁 시드 구조)에 한정된다.
- `career_leave`(편인 휴직) 후보: 11명·72연도에서 160건 생성(shadow). 원장에 휴직 행이 없어 적중률은 측정 불가 — 실답 노출 로그로 감수한다.
- **85사례 180명식 재생(off/on, 같은 셸)**: `casebook_report` metrics.json 전 항목 **변화 0건**(쌍 비교 순위·시점 극성·도메인 히트 모두 동일) — 원장 측정과 같은 이유(시드가 기존 기본점을 넘지 못함).
- 권고: 점수층은 **OFF 유지**(변화 없음 — 켜도 해가 없지만 근거도 없다). 문구층(원인 축·정인 완화·겁재 지위 위협·편인 쉬어가는 운)과 career_field 성향 문구는 ON 으로 실답 감수.
- 채팅 노출 경로: 직업 도메인 질문은 후보별 note(`_to_llm_candidate`)가 원국을 받지 않아 문구가 실리지 않았다(실측 dry-run 0건) → `career_exit_lecture_block`(간지당 1회, `[직장 운 결 — 강의 번역층]`)을 프롬프트 말미에 추가(2026-10-29). 총운(일·월·연)은 `build_luck_grounding` 경로로 운 결 1줄에 붙는다. 리포트는 `report_event_input._tone_line` 운 결 줄.
- 후속: 시드가 순위를 바꾸려면 기준점을 조합 규칙(59~61) 위로 올리거나(측정 근거 없음 — 보류) 브랜처 기본 가지가 없는 달에서만 의미가 있다. 실답 노출 로그로 문구 감수 후 재검토.
