# 외부 강의 대조 — 「지지충 6종: 종류·작용·개운법」 vs 류보살 v2 엔진 (2026-11-07)

> 목적: 데굴님이 붙여 넣은 외부 영상 스크립트(子午·丑未·寅申·卯酉·辰戌·巳亥 충의 결, 운에서의 작용, 완화 글자)를 우리 엔진과 대조하고, 풀이 품질에 쓸 항목을 구현·측정한다.
> 원칙: 강의는 **참고 문헌**이지 지침이 아니다(붙여 넣은 외부 의견과 같은 지위 — 데굴님 발언과 충돌하면 절충하지 않고 묻는다). 노출·측정 원칙(2026-10-15): 문구·기능층은 적용(ON) 후 실답 감수, 점수 규칙은 85사례·실사례 적중률로 ON/OFF. 단정 금지 정의(`structural_context.ASSERTION_POLICY`)는 그대로.
> 조사 방법: 탐지·점수(`relations.py`·`luck_cycles._branch_dynamics`·`relation_palace_engine`·`event_engine_v2` 이중충/탐합망충/충근·`risk_engine`·`wealth_capacity`)와 서술층(`relations_text`·`relation_palace_pairs_text`·`health_element_organs`·`structure_patterns`·`luck_hierarchy_render`·`remedy`)을 두 축으로 전수 탐색(2026-11-07).

## 1. 요약 판정

| 구분 | 건수 | 비고 |
|---|---:|---|
| 이미 동등 (불채택) | 3 | 일지 충 가중(1.3) · 충=양면·길흉은 용기신 · 원국(성향)/운(사건) 분리 |
| 채택 — 서술층(바로 ON) | 4 | ① 계층 블록 구조적 긴장 줄에 쌍별 `fromLuck` 결 + 극 방향 라벨 ② 6쌍 `natalTrait`(丑未·辰戌 신설)·`fromLuck` 첫 문장 水火/木金/土 결 ③ 충 완화 글자 서술 블록(원국 발췌 + 채팅 말미 + 리포트 4도메인) ④ 사문 `branch_relation_pairs` 삭제 |
| 채택 — 점수 규칙(측정 후 ON) | 1 | 강충 방향(운 글자가 원국 글자를 극 + 피격 글자 고립 → 수술·이별·퇴직 계열 ×1.15) — `SAJU_CLASH_DIRECTION_MODE` 기본 shadow |
| 불채택 | 3 | 토 다자 "무조건 부동산"(단정·문서 외 규칙), 子午충=천재·유명인 열거(출처 표기 금지), 寅申巳亥=역마·子午卯酉=도화 재정의(엔진 정의 유지) |
| 결정(2026-11-07 데굴님) | 3 | ① 도화는 **진도화 기준**으로만 서술(왕지충에 '도화성' 추가 안 함) ② 합해충은 명리 우위 논리를 찾아 쓰고, 못 찾는 항목은 **병기** ③ 점수 규칙은 측정 후 |

## 2. 영역별 대조표

| # | 강의 주장 | 현재 엔진(2026-11-07 작업 전) | 판정·반영 |
|---|---|---|---|
| ① | 子午·巳亥=水火충: 보이지 않는 영역 — 생각 변화·멘탈 분리·공황·우울. 子午는 지장간이 깔끔해 빨리 결판, 巳亥는 庚·壬이 얽혀 질질 끌리고 머리 복잡·불안정 | 子午 "감정·심리 동요", 巳亥 "계획 변경"만 | 채택(서술) — `fromLuck` 첫 문장에 水火충·결판 속도 결, `natalTrait` 보강(질환어는 기존 린트 표기) |
| ② | 子午=애정 갈등·인기·질투, 해외 인연 | 없음 | 부분 채택 — 애정 갈등(子午 natalTrait)·물 건너 먼 곳(巳亥 natalTrait). 인기·질투는 도화 전용이라 제외(결정 ①) |
| ③ | 寅申·卯酉=木金충: 현실 사건(이직·승진·이사·이혼·소송·사업). 寅申 원국=순함·고생·시작은 잘하나 마무리 약함. 卯酉=극단적 성공/실패·예민·까다로움·예술성·사람 살리는 일 | 寅申 "이동", 卯酉 "관계·문서"; natalTrait 분노/강박 | 채택(서술) — `fromLuck` 첫 문장 木金충·현실 사건·극단 결과, natalTrait 보강 |
| ④ | 辰戌·丑未=土충: 겉은 조용·속 시끄러움. 丑未=독립심·자신감·성실·융통성 부족. 辰戌=카리스마·예술성·세밀·반복 작업 | **natalTrait 없음**(2쌍) | 채택(서술) — natalTrait 신설, `fromLuck` 첫 문장 土충 결 |
| ⑤ | 운 글자가 원국 글자를 극할 때(金→木·水→火) 가장 강하고, 약한 글자가 맞으면 수술·사고·이별·갑자기 그만둠 | 상극 승자·피격 글자 세력 미판정. 피격 원국 글자만 ×0.7 | 채택(점수, 측정) — `EventEngineV2._apply_clash_direction` shadow 기본. 서술은 계층 줄 방향 라벨로 바로 ON |
| ⑥ | 일지 충이 특히 체감 큼 | 궁위 가중 일지 1.3 | 동등 |
| ⑦ | 충=성장·승진·합격 vs 실패 양면, 길흉 별도 | `fromLuck` 양면 + 용기신 판정 | 동등 |
| ⑧ | 완화 글자: 子←丑·午←未·丑←子·未←午(육합), 寅卯←辰·申酉←戌·辰←卯·戌←酉(방합), 巳←寅·亥←申(상생). 그 글자 세운·월운에 완화. 충 받는 글자가 "내게 필요한 글자"일 때 | 없음(합해충 2026-10-25 불채택 "단일 통설 없음") | 채택(서술) — 결정 ②. 자평진전 「논형충회합해법」 우위 논리(근접 우선·삼합/방합 완성>육합·제3 글자 삼합 시 충 부활·선후)를 조건 문구로, 巳←寅(寅巳 형·해)·亥←申(申亥 해)·辰←卯(卯辰 해)·戌←酉(酉戌 해)는 **병기**. 용·희신 글자만 |
| ⑨ | 토 다자+토충=고생, 재테크는 "무조건 부동산" | 없음 | 불채택 — 단정(원칙 3)·문서 외 규칙(원칙 10) |
| ⑩ | 子午충=천재(윤동주·헤세·하루키), 해외 운 강함 | 없음 | 불채택 — 이름 열거는 출처 표기 금지와 충돌. 해외는 ②의 '물 건너' 결로만 |
| ⑪ | 寅申巳亥=역마, 子午卯酉=도화(인기살) | 역마=상대 12신살(2026-10-29 유지), 도화=진도화만(2026-10-13) | 불채택(정의 유지) — 쌍 성격은 '역마성 충' 표현처럼 서술로만, 도화는 결정 ① |

### 2-1. 작업 전 공백(실측)

- 운영 설정(`SAJU_PERIOD_HIERARCHY_ENABLED=true`)에서는 기존 형충회합 줄(쌍별 `fromLuck`)이 계층 블록으로 **통째로 대체**돼 "구조적 긴장: 자오충 [子·午] — 성립 확정…" 한 문장만 LLM에 갔다(`context_reducer.py:3813-3819`, `luck_hierarchy_render.py:140-144`). 강의 이전부터 있던 사전 문구도 운영에서 안 나가던 상태.
- 사문 2곳: `relation_palace_modifier.json` `branch_relation_pairs.CHUNG`(쌍별 테마, Python 소비자 없음 → 삭제), `relations.json` 쌍별 `eventDomains`(precompute/graph 전용, v2 후보 점수 미반영 → 현행 유지).

## 3. 합해충 우위 논리 조사(결정 ②)

- 자평진전 「論刑沖會合解法」: 삼합·육합이 형충을 풀 수 있고(會合可以解刑沖) 형충도 회합을 풀 수 있다(刑沖可以解會合). **가까이 붙은 글자가 먼저 작용**하고 떨어진 글자는 힘이 약하다. 子년 午월에 일지 丑이 子를 합해도 시지 巳·酉가 丑을 삼합으로 끌어가면 子는 여전히 午를 충한다(會合而不能解刑沖).
- 삼명통회: 합이 충의 통로를 견제·변경할 수 있으나 실제 효력은 위치·旺衰·선후에 따른다.
- 현대 정리(openfate 위키·명리 카페): 탐합망충은 자동 취소가 아니라 월령·뿌리·근접·완성도 비교. 삼합·방합(완성) > 육합. 학파별로 방합>삼합도 있음.
- 강의의 巳←寅·亥←申은 합이 아니라 상생 논리이며 寅巳 형·해, 申亥 해가 동시에 선다. 辰←卯·戌←酉도 방합 짝이면서 해(害)다 → **병기**.
- 반영: `clash_relief_text.json` `principles`(adjacent_first·remote_weak·trine_revives·co_relation·no_score) + 블록 머리말. 점수 규칙(탐합망충 apply)은 10-25 측정대로 shadow 유지.

## 4. 구현

| 항목 | 위치 | 비고 |
|---|---|---|
| 계층 줄 쌍별 결 + 방향 라벨 | `luck_hierarchy_render._pair_texture`·`_clash_direction_note` | 구조적 긴장 줄 끝 ` · 결: {fromLuck 첫 문장}` + `(방향: 운 X(金)이 원국 Y(木)을 극하는 쪽 — 체감이 큰 방향)` / 원국이 운을 극하면 "덜한 방향". 土끼리·운끼리·천간충은 라벨 없음 |
| 사전 보강 | `interpretations/relations_text.json` 6쌍 | `natalTrait` 6쌍 전부, `fromLuck` 첫 문장(≤200자 렌더)에 水火충/木金충/土충 결 |
| 완화 글자 사전 | `interpretations/clash_relief_text.json`(신규, `ClashReliefTextFile`, 린트 `_lint_clash_relief_text`) | 12지지 각 1회, 기제(육합/방합/상생) 정합 검사, 상생은 coRelation 필수, 단정 어휘 금지 |
| 완화 글자 엔진 | `saju_engines/clash_relief.py` | `natal_clash_relief_by_name`(원국 충 → 관계 발췌 끝 "완화 글자: …", 용·희신 글자만, 보유/인접·격위/세운 연도·절기월/삼합 부활/병기) · `luck_clash_relief_block`(후보 기간 운 지지 → 원국 용·희신 글자 충, 운 지지당 1줄, 상한 6) |
| 배선 | `chart_interpretation.build_chart_interpretation`(고정 prefix 관계 발췌) · `chat_service` trailing(도메인 무관, 조건 없으면 블록 없음) · `report_service.ReportData.lecture_block`(career/wealth/relationship/relocation 끝) | |
| 강충 방향(측정) | `period_v2_config.CLASH_DIRECTION_MODE`(off/shadow/apply, 기본 shadow)·`CLASH_DIRECTION_BONUS=0.15` · `EventEngineV2._apply_clash_direction`·`take_clash_direction_shadow` · `casebook_replay --clash-direction-mode` | 조건: 운 지지 오행이 피격 지지 오행을 극(金→木·水→火) + 피격 글자 고립(그 자리를 뺀 천간·지지 본기에 같은 오행 없음). 대상 health_attention·relationship_change·career_change |
| 사문 삭제 | `event_engine/relation_palace_modifier.json` `branch_relation_pairs` | 소비자 없음(grep 전수) |

## 5. 측정(강충 방향 apply vs shadow, 85사례 180명식)

측정 절차: `casebook_replay.py --clash-direction-mode shadow --out-name subjects_cd_shadow.jsonl` / `--clash-direction-mode apply --out-name subjects_cd_apply.jsonl` → `casebook_report.py --subjects … --tag cd_shadow|cd_apply` → 지표 비교(2026-11-07 실행).

| 지표 | shadow(현행) | apply | 비고 |
|---|---:|---:|---|
| 조건 성립 기간 / 가산 대상 사건 | 314 / 647 | 314 / 647 | 판정 공유(두 모드 동일) |
| A. 쌍 비교 순위 일치 | 33/68 | 33/68 | 불변 |
| 시기 — 세운 일치 | 14/44 | 14/44 | 불변 |
| 시기 — 대운 일치 | 25/44 | 25/44 | 불변 |
| 시기 — 사건 적중 | 23/44 | 23/44 | 불변 |
| 명식 행 변경(점수·순위) | — | 52/180 (lifetime 47 · daewoon 19) | 예: relationship_change 67→77 로 2위 상승 |

판정: **측정 지표 중립**(적중 상승도 하락도 없음, 방향 오탐 지표는 사례집 보고서에 없어 미측정). 2026-10-15 원칙(중립이면 감수를 위해 ON 가능, 하락이면 OFF)에 따라 `apply` 전환은 데굴님 결정 — 기본값은 `shadow` 유지. 재측정은 `scripts/casebook_replay.py --clash-direction-mode apply --out-name X` → `casebook_report.py --subjects var/casebook_replay/X --tag X`.

## 6. 테스트

- `tests/unit/test_clash_lecture_20261107.py` — 6쌍 natalTrait·첫 문장 결, 완화 사전 린트(기제·단정), 12지지 커버리지·병기, 원국 완화(용·희신만·구신 제외·세운 연도·형해 병기), 기신 쌍 무출력, 관계 발췌 병기, 운 블록(운 지지당 1줄·기신 제외·빈 목록), 강충 방향 shadow 기록/apply 가산/고립 아님/off/미지원 모드.
- `tests/unit/test_luck_hierarchy.py::test_structural_tension_line_carries_pair_texture` — 계층 줄 결·방향 라벨.
