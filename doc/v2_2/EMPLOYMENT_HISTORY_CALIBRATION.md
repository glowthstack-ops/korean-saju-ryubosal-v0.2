# 직장 이력 캘리브레이션 (SSOT, 2026-10-22 데굴님 승인)

> 배경: 데굴님 본인 입퇴사 이력 분석(`career_timing_20261022.pdf`, 정본)을 풀이·엔진에 연결한다.
> 결정(2026-10-22): ①퇴사 키 `resignation` 추가 ②군복무·인턴은 `nature` 태그 ③미상 일자는 월 정밀도
> ④P1 글자 가중 초기값은 reviewed:false 로 제안 후 측정으로 확정. **P0 구현 완료(아래 §2 상태 참조).**

## 0. 현재 상태에서 확인된 결함

| # | 결함 | 근거 |
|---|---|---|
| F1 | 원장(`subject_life_events`)은 **달력 월**만 저장하고 지문은 그 달 15일 기준으로 만든다. 절기 경계 사례(떠나요 2019.08.08 입추, 집닥 전월 한로)가 잘못된 월운으로 들어간다. | `routers/reality_calibration.py::_month_fingerprints` — `reference_date=date(year, month, 15)` |
| F2 | 퇴사 키가 없다. `EventKeyV2` 21종에 `resignation`이 빠져 있고 퇴사가 `career_change`에 합쳐진다(docs/02 Event Taxonomy에는 `resignation`이 있음). | `shared_types/event_engine.py`, docs/02 §Event Taxonomy |
| F3 | 캘리브레이션 재제출이 `delete_subject_rows`로 **대상의 모든 행**을 지운다. 다른 소스로 적재한 이력도 함께 사라진다. | `routers/reality_calibration.py::submit` |
| F4 | 개인 지문이 십성 그룹 단위라 亥 4건과 子 0건을 구분하지 못한다. 전월(기회 달) 차원도 없다. | `personal_calibration.py::candidate_fingerprint` |
| F5 | 고용 형태·같은 직장 묶기·입사 통로를 담을 자리가 없다. 군복무·인턴·파견→전환이 입사·퇴사 통계에 섞인다. | `LifeEventRow` 필드 |
| F6 | 엔진 monthly_luck 은 기준일의 **달력 연도** 입춘부터 12개월을 나열해, 1월 회상(丑월 라벨 `YYYY-01`)은 전년 목록에만 있다. 캘리브레이션 1월 발생 사건은 월운 지문이 비어 연도 지문으로 폴백되고 있었다. | 2026-10-22 실측(2022-01-05 기준 → 2022-02~2023-01), `_month_fingerprints` |

## 1. 범위와 원칙

- 신규 명리 규칙 없음. 사용자 제공 사실(user_explicit)의 저장·대조·서술만 다룬다.
- 점수 반영은 P1 측정(적중) 뒤에만 ON. 그 전엔 서술·근거 코드 전용(2026-10-15 정정 준수).
- 입력은 전부 선택(규칙 11). 사용자는 입퇴사 월일 수준만 기억한다는 전제. 단계 사실(지원·면접) 요구 금지.
- 모든 간지·절기월은 엔진이 계산한다. 손 계산·LLM 계산 금지.

## 2. P0 — 이력 원장 확장과 적재 (PR 1)

### 2-1. 데이터 계약
`LifeEventRow`에 선택 필드 추가(모두 optional, 기본 None):

| 필드 | 타입 | 뜻 |
|---|---|---|
| `event_date` | date \| None | 정확한 날짜. 있으면 `period`와 지문을 **이 날짜의 절기월**로 계산 |
| `date_precision` | `day` \| `month` \| `year` | 회상 정밀도. month면 기존 15일 규칙 유지 |
| `nature` | `regular` \| `dispatch` \| `intern` \| `military` \| `conversion` | 사건 성격. 취업 통계는 regular·dispatch만 집계 |
| `entry_channel` | `direct` \| `offer` \| `referral` \| `conversion` \| None | 입사 통로(입사 행만) |
| `exit_reason` | `voluntary` \| `involuntary` \| `contract_end` \| None | 퇴사 사유(퇴사 행만, 모르면 None) |
| `employment_group` | str \| None | 같은 직장 묶기 키. 같은 그룹 안의 entry→exit 사이 행(전환)은 이동으로 세지 않음 |
| `label` | str \| None | 사용자가 준 회사명. 연결 사례 서술에만 사용(점수 무관) |

DB: `migrations/020_life_event_attrs.sql` — `attrs JSONB NOT NULL DEFAULT '{}'` 한 컬럼에 위 필드를 담고, `source` CHECK에 `employment_history` 추가. 스키마 컬럼 추가 대신 JSONB를 쓰는 이유는 코호트 인덱스를 건드리지 않기 위해서다.

### 2-2. 사건 키
- 입사 = `job_gain`(기존). 퇴사 = `resignation` **추가** — docs/02 규격명. 단 **원장 전용 키**(`LEDGER_ONLY_EVENT_KEYS`)로 두고 채점 taxonomy `EventKeyV2`(21종)는 늘리지 않는다. 이유: 21키 전수 사전(`event_forms.json`·진행 사실 호환·12운성 채널 근거·관계 어휘 등 8곳)이 키마다 명리 내용을 요구해, 저장 전용 키를 넣으면 감수 없는 명리 항목을 만들게 된다(규칙 10). `personal_calibration.seed_missing_events`는 원장 전용 키를 시드하지 않는다.
- 군복무·인턴은 키를 늘리지 않고 `nature` 태그로 구분한다(규격 밖 키 신설 회피). 기존 2001-08·2003-10 행은 `career_change`+`nature=military`로 태그만 붙인다.
- `career_change`는 그대로 "이동(입사·퇴사 묶음)"의 상위 키로 남긴다. 적재 시 `job_gain`/`resignation` 행과 별도로 `career_change` 행을 만들지 않는다(중복 가산 금지).

### 2-3. 적재 경로 (구현)
- 순수 변환 `saju_engines/employment_history.py`: `parse_history_date`(일/월 정밀도, 월은 15일 대표) · `luck_month_label`(절기표 `bounding_month_terms`, **정오 KST** 판정, 라벨=직전 節의 KST 'YYYY-MM' — 엔진 월운 라벨과 동일) · `reference_date_for_label`(F6 — 라벨 연도의 7/1, 1월 라벨은 전년) · `rows_from_history`(entry→job_gain, exit→resignation, conversion→career_change, 행 id `{subject}:eh:{날짜|YYYY-MM}:{key}`) · `superseded_keys`.
- 스크립트 `backend/scripts/load_employment_history.py --subject <id> --jsonl <경로> [--execute]`: 행마다 라벨 연도 기준 만세력 + `EventEngineV2.score(levels={MONTH})`로 월운 지문을 얻고 `source=employment_history`로 append. 같은 `(event_key, period)`의 다른 소스 행은 `delete_superseded_rows`로 치환(정본 우선). 기본 dry-run. 유지 스크립트 allowlist 등재.
- F3 수정: `LifeEventStore.delete_subject_rows(owner, subject, source=None)` — 캘리브레이션 재제출은 `reality_signal_calibration` 소스만 치환한다.
- F6 수정: `_month_fingerprints`도 `reference_date_for_label`을 쓴다.
- 입력: 스크래치패드 `employment_history_degool.jsonl`(27행: 입사 13·퇴사 13·전환 1, 군복무 2·인턴 2 포함). 미상 일자 5건(군입대·제대·인턴 시작·종료·권고사직일)은 `month` 정밀도.

### 2-4. 검증 (구현)
- 단위 `tests/unit/test_employment_history.py`: 절기 경계 3건(2019.08.08 입추 04:13 → 壬申, 2022.01.05 소한 18:14 → 庚子, 2022.10.08 한로 16:22 → 己酉)과 기존 period 호환 3건(2025.12.01→2025-11 丁亥, 2015.03.01→2015-02 戊寅, 2022.02.07→2022-02 壬寅)이 엔진 monthly_luck 간지와 일치 · 1월 라벨 전년 목록(F6) · 키 매핑·attrs·행 id·빈 지문 · 원장 전용 키 시드 차단 · attrs 왕복.
- 통합 `tests/integration/test_lei_db_golden.py`: attrs 왕복·치환 삭제·소스 범위 삭제(DB 미기동 시 skip).
- 게이트 4종 — 결과는 WORKLOG 에 기록.

## 3. P1 — 지문 확장과 적중 측정 (PR 2, 구현 완료 2026-10-22)

### 3-1. 지문
`SignalFingerprint`에 추가(기본 빈 값 — 저장된 기존 JSONB와 호환):

| 필드 | 값 | 비고 |
|---|---|---|
| `glyphs` | `{sewoon_stem, sewoon_branch, wolwoon_stem, wolwoon_branch}` | 연 지문은 세운 두 칸만. 1월 라벨(丑월)의 관할 세운은 전년 |
| `natal_echo` | `['wolwoon_branch=month_branch', …]` | 운 글자가 겹치는 원국 자리(천간↔천간, 지지↔지지) |

**전월 글자는 넣지 않는다.** 절기월은 순환하므로 직전 달의 간지는 당월 간지로 결정된다(亥월의 전월은 언제나 戌월, 천간도 순차). PDF의 "입사 전월 戌 4건"은 "당월 亥 4건"의 재진술이라 정보가 0이고 중복 가산만 된다. '움직이는 달 = 성사 달 − 1'은 P2 서술 규칙으로만 쓴다.

구현: `saju_engines/glyph_context.py` — `GlyphContext.from_result(ManseV2Result)`(원국·대운표 세운·monthly_luck), `glyphs_for(period)`, `natal_echo`, `with_glyphs(fp, period)`. 후보 쪽은 `candidate_fingerprint(c, ctx)`, 원장 쪽은 적재 스크립트가 같은 컨텍스트로 채운다(27행 재적재 완료).

### 3-2. 유사도와 기저율
- 사전 `dictionaries/event_engine/personal_glyph_weights.json`(`reviewed:false`, 결정 ④): 자리 가중 wolwoon_branch 0.4 · wolwoon_stem 0.2 · sewoon_branch 0.2 · sewoon_stem 0.2, 원국 재현 공통 보너스 0.1(상한 1.0), `glyph_weight` 0.35, lift 기준(min_rows 5 · min_hits 2 · min_lift 2.0 · 기대 비율 지지 1/12·천간 1/10).
- `fingerprint_similarity(a, b, glyph_weight)` = (1−w)·기존 식 + w·글자 유사도(양쪽에 글자가 있을 때만). w=0 이면 기존 식과 동일(점수 불변).
- 플래그 `SAJU_PERSONAL_GLYPH_SCORE_ENABLED`(기본 **OFF**) → `default_glyph_weight()`. OFF 에서도 월지 lift 가 기준을 넘으면 근거 코드 `PERSONAL_GLYPH_REPEAT`만 붙는다(서술 전용, 점수·personal_match 불변 — 테스트로 고정).
- lift 집계 행 = 같은 키·확정·취업 통계 성격(None/regular/dispatch). 군복무·인턴·전환 제외. `resignation`(원장 전용)은 후보 키와 만나지 않아 매칭·시드 모두 무해.
- 배선: `LifeFitRanker.rank(glyph_context=, glyph_weight=)` ← `EventEngineV2.score_legacy_personalized`가 시그니처가 있을 때 `GlyphContext.from_result(result)`를 넘긴다.

### 3-3. 적중 측정 (`scripts/measure_employment_history_loo.py`, 유지 스크립트)
데굴님 명식, 정규·파견 입사 11건 leave-one-out, 그 절기년 12개월 job_gain 후보 Top-3 적중(우연 25%). 2026-10-22 실측(`var/eh_loo_20261022.md`):

| 모드 | Top-3 적중 | 비율 | 평균 순위 |
|---|---|---|---|
| engine(개인화 없음) | 3/11 | 0.273 | 5.45 |
| base(시그니처, 글자 가중 0 = 현재 운영) | 3/11 | 0.273 | 5.73 |
| glyph(가중 0.35 = 플래그 ON) | 5/11 | 0.455 | 4.64 |

- 십성 그룹 지문만으로는(base) 엔진 대비 개선이 없고, 글자 차원이 +2건이다. 다만 표본 11건이라 **ON 판정은 데굴님 결정**이며, 켜더라도 개인 시그니처가 있는 subject 에만 작용한다(85사례 fixture 는 시그니처가 없어 불변).
- 가중을 켜면 나빠지는 사례도 있다(2006-05 키스템프: engine 1위 → glyph 8위, 巳월 표본 1건). 가중·lift 기준 조정은 이 스크립트로 같은 11건을 재측정한 뒤 한다.

## 4. P2 — 노출 (PR 3, 구현 완료 2026-10-22; 회사명 인용은 데굴님 결정으로 배제)

- **진입 시기 두 칸**: `HorizonPolicy.entry_window`(`resolve_horizon` — 사건 키가 job_gain·career_change 이고 지평이 구조 결정형·택일이 아닐 때) → `horizon_directive`가 `ENTRY_WINDOW_DIRECTIVE`를 붙인다: 성사 달(후보 달) + 한두 달 앞 움직이는 달(제안·접수·면접), 사용자가 말한 리드타임 우선, 행동 제안은 움직이는 달에, 성사 달 결과 단정 금지, **과거 사례의 회사명·고용주 언급 금지**.
- **글자 반복 서술(수치만)**: 근거 코드 `PERSONAL_GLYPH_REPEAT:亥:4/11` → `reason_codes_ko` 라벨 "개인 이력 반복(같은 亥월 글자에서 같은 사건 4/11건 — 기대 비율 1/12, 특정 사례·회사 지목 아님)". `PERSONAL_MATCH`·`PERSONAL_SEED` 라벨도 등록. 회사명(`attrs.label`)은 LLM 입력에 직렬화되지 않는다(후보만 직렬화).
- **진입 통로**: `chat_service._entry_channel_context` — 입사·이직 질문(관계 대상 질문이 아닐 때)의 진입 후보 상위 달 2개의 운 십성을 `ten_god_relations` 근거표(가족 칸 없음)로 옮긴 블록 + `_ENTRY_CHANNEL_DIRECTIVE`(근거표 범주 그대로, 통로 단정·특정인·특정 회사 금지, 근거표 밖 범주 추가 금지). 관성=조직/비겁·재성=지인 같은 **개인 이력 규칙은 넣지 않았다**(규격 밖 명리 규칙 — 근거표 범주만).
- **입력 UI·API**: `GET/POST /api/v2/reality-calibration/{subject_id}/employment-history`(`EmploymentHistoryView`/`EmploymentHistorySubmission`→`EmploymentHistorySubmitResult`, 전체 치환, 캘리브레이션 같은 달 회상 행 치환, 요약에 회사명 없음). 적재 스크립트와 API 는 `make_month_fingerprint_resolver`를 공유한다. 프론트 `components/onboarding/EmploymentHistoryForm.tsx`(날짜·종류·성격·통로/사유·묶기·표시용 이름) + `app/reality-calibration` 탭(연도별 사건 | 직장 이력). 프리필은 `entries_from_rows`(행 id stamp 로 일/월 정밀도 복원).
- 리포트(F-15·J 섹션)에는 아직 배선하지 않았다 — 채팅 실답 감수 후.

### 4-1. 실답 감수 교정 (2026-10-22, thread web-mvjgmlnd-63fer6 "언제 취업할 수 있을까" / "이번 11월에 취업될 가능성은")
감수 결과: 진입 통로 블록은 두 턴 모두 노출·반영(비겁→동료·친구·업계 지인, 재성→거래처). 두 칸 지시는 1턴(transactional_when)에만 붙었고 2턴(시점 명시)은 지평 경로를 타지 않아 없었다. `PERSONAL_GLYPH_REPEAT:亥:4/11`은 후보에 붙었으나 **후보별 동반 신호 4개 상한(삽입 순)에 잘려 프롬프트에 닿지 않았다**. 또 입사 11건 적재로 반복 가중 0.2×(기간−1)=2.0 이 모든 달의 job_gain personal_match 를 246~288로 포화시켜 확신도 +1티어가 어느 달에나 붙었다.
- 교정 ①(프롬프트 전용): `context_reducer` 동반 신호 상한에서 `개인 이력 반복(` 라벨 1개 예외 보장 + `_PERSONAL_REPEAT_DIRECTIVE`(라벨이 실린 후보가 있을 때 수치 한 문장, 회사명 없음, 경향≠확정).
- 교정 ②(프롬프트 전용): `ENTRY_WINDOW_DIRECTIVE`를 지평 경로와 분리해 `_entry_window_directive_needed`(진입 사건·미래·비구조·지평 지시 미포함)이면 시점 명시 질문에도 붙이고, 첫 문단에 '성사 달 ○월·움직이는 달 ○월'을 이름 붙여 쓰고 특정 달 질문이면 그 달이 어느 칸인지부터 밝히라는 형식 문장을 추가.
- 교정 ③(점수 규칙, **값 미확정**): 반복 가중 상한 `repeat_cap`(사전 `personal_glyph_weights.json`, 기본 null=무상한) + `apply_personal_match(repeat_cap=)`·`LifeFitRanker.rank(repeat_cap=)`. 측정(`var/eh_loo_20261022b.md`, --repeat-cap 0.6): Top-3 적중 glyph 5/11 = glyph_cap 5/11(평균 순위 4.64→4.73). 반복 항은 같은 키의 모든 달에 같은 값이라 **달 순서(LOO)에는 영향이 없고**, 사건 키 간 순서와 확신도 티어 포화(톤)에만 작용한다. 85사례는 시그니처가 없어 불변. 값 결정은 데굴님.
- **상한 0.6 적용(2026-10-22, 데굴님 기준 "적중률에 긍정적이면 적용")**: 두 측정을 합쳐 판단했다. ①사건 종류 간(확정 월 17건 LOO) Top-1 11/17→6/17, Top-3 14/17 불변 ②**오탐**(캘리브레이션 not_happened job_gain 4년 × 12달 = 48달에서 job_gain 이 월 Top-1 인 달 수, `measure_false_positive`): engine 6 · base/glyph **33(69%)** · cap0.6 **13(27%)**. 무상한은 사건 없는 해의 달 셋 중 둘에 취업을 1위로 올려 ①의 Top-1 11/17 이 "어느 달이나 취업 1위"의 부산물이었다. 정밀도 기준으로 상한이 명백히 낫고 Top-3 회수는 같으므로 `repeat_cap=0.6` 적용(`personal_glyph_weights.json`). 재측정: `measure_employment_history_loo.py --repeat-cap`(`var/eh_loo_20261022c.md`).

### 4-2. 2차 감수 교정 (2026-10-22, thread web-mvjij2wx "언제 취업할 수 있을까" / "돈이 없어서 빨리 취업해야해")
확인: 수치 라벨이 2턴에 "11건 중 4건"으로 닿았고(회사명 없음), 통로 블록 두 턴 반영(관성·인성 / 비겁·식상), 두 칸은 역할 구분만 되고 첫 문단 이름표('성사 달·움직이는 달')는 없음. 1턴은 숫자 없이 "반복되는 경향"으로 뭉뚱그림. 새 누수: "성취 신호가 1위로 나타나지만"(창 내 상대 순위 블록 내부 용어), "2026-12 庚子월"(후보 라벨 원문). 기존 결함: 1턴 일주 소개 두 문장이 참조 예외(`ilju_mention_kept_referenced`)로 통과.
- 교정 ①: `_PERSONAL_REPEAT_DIRECTIVE`를 "숫자(일치/표본)를 그대로 적어라 — 뭉뚱그리지 말 것"으로 강화. 두 칸 이름표 준수는 `ChatPostprocessContext.entry_window` + `answer_label_audit.entry_window_labels_present`로 **로그만**(`entry_window_audit result=pass|miss`).
- 교정 ②: `saju_engines/answer_label_audit.py` — `rewrite_rank_labels`('1~3위'+조사 → 가장 강하게/두 번째로/세 번째로, 10위권·2·3위 제외), `rewrite_raw_period_labels`('YYYY-MM' 단독 → 'YYYY년 M월', 날짜·범위 제외). `finalize_answer_text`에서 거짓 역접 교정 뒤 적용, 로그 `internal_label_rewritten`.
- 교정 ③: `ilju_mention_audit.strips_referent` — 질문 유형으로 걸린 답(총운·시기·택일)은 참조 예외 없이 지시 문장까지 제거(`removed_referents`, 로그 `ilju_mention_referent_stripped`). 분야 개요(domain_analysis)는 기존 예외 유지. 기존 테스트 2건은 새 규칙으로 개정(택일 답의 '이러한 성향은 … 월운을 만나며' 문장도 성향 서술이라 함께 제거).

### 4-3. 3차 감수 (2026-10-22, thread web-mvjjpmvz "언제 취업할 수 있을까")
확인: 숫자 도달("과거 11건 중 4건"), 통로 반영(2027-02 재성·관성, 2027-05 인성), '1위'·라벨 원문·일주 소개 없음(`ilju_mention_stripped`). `entry_window_audit=miss` — 첫 문단이 "성사 기운이 뚜렷한 달 … 미리 움직이며"로 의미는 지켰으나 '성사 달·움직이는 달' 표기는 없음. 또 11월(亥 4/11 입사 이력)을 "검토월"로만 격하.
- 교정: 관측 어간 기준(`성사`·`움직이`)으로 완화(로그 전용), `_PERSONAL_REPEAT_DIRECTIVE`에 "반복 이력 달은 성사 후보로도 적어라(엔진 상위 달은 앞에)" 추가.

### 4-4. 리포트 배선 (2026-10-22)
- 공용 모듈 `saju_engines/entry_channel.py`(`entry_periods`·`entry_channel_lines`·`ENTRY_CHANNEL_DIRECTIVE`) — 채팅 `_entry_channel_context`가 위임, 리포트 `_ReportData.entry_channel_block`(라벨 절기 연도 월운/세운에서 기둥 해석).
- 지시문 공용화: `context_reducer.PERSONAL_REPEAT_DIRECTIVE`·`has_personal_repeat_signal`(레거시 후보 신호 판정), `horizon.ENTRY_WINDOW_DIRECTIVE`.
- 리포트 섹션 **J-06(주목할 달)·J-07(행동 전략)**: 진입 통로 블록 + 두 칸 지시 + (개인 이력 반복 라벨이 실린 직업 후보가 있을 때) 수치 지시. 후보 없으면 블록 없음. 리포트 후처리에 순위·기간 라벨 원문 교정 추가(`internal_label_rewritten surface=report`). F-15 는 적합 분야 섹션이라 배선하지 않았다(시기 서술 아님).
- 회사명은 리포트에도 없다(후보만 직렬화). 리포트 실답 감수는 다음 생성 때.

### 4-5. 4차 감수 (2026-10-22, thread web-mvjm3vcc "언제 취업할 수 있을까", 상한 0.6 적용 후)
확인: 수치("11건 중 4건")·통로·일주 제거 유지. 결함: ①라벨 교정이 '2026-11월'(모델이 라벨 뒤에 月을 붙인 꼴)을 '2026년 11월월'로 만들고 '05월·07월'(앞자리 0)은 그대로 둠 ②"내년 하반기부터 준비해 내후년 상반기에 결론" — 2027년을 내후년으로 한 해 밀린 상대 연도 오류 ③11월을 검토 단계로만 서술(성사 후보 병기 지시 미준수) ④두 칸 관측 miss(성사 ○·움직 ✗).
- 교정 ①: `_RAW_PERIOD_RE`가 뒤의 '월'을 같이 삼키고, 단독 '0M월'→'M월', 방어적 '월월'→'월'.
- 교정 ②: 결정론 치환은 뜻을 못 고치므로(숫자만 바뀜) `relative_year_mentions` 로그 전용 관측 + `ENTRY_WINDOW_DIRECTIVE`에 "연도는 숫자로, 내년·내후년 금지" 추가.
- ③④는 지시 준수 문제 — 다음 감수에서 재확인(로그 `entry_window_audit`, `relative_year_mentions`).

### 4-6. 5차 감수 — 턴 간 성사 달 모순 (2026-10-24, thread web-mvm8zqyr "다른 사주에서는 내년 4월에 취업할 수 있을거래" / "최대한 빠르게 취업하려면 언제 가능할가")
확인(dry-run 재생): 1턴(domain_analysis, 2027-04 한 달 창)은 후보 '취업 성사 가능성 @ 2027-04 — 매우 강·기회·유입' 1건이라 "성사 가능성 매우 높다"가 입력과 일치. 2턴(timing_search, 15개월 창) Top-5 는 전부 job_gain 이며 2027-02·2027-03·2026-12 는 결과 방향 '국면'(pressure, 결과 불리), 2027-04·2027-05 는 '성사 가능성'(opportunity, 결과 유리). 엔진 그림은 두 턴에서 같았다(2~3월 국면 → 4~5월 성사). 결함은 서술 지시 층: ①`ENTRY_WINDOW_DIRECTIVE`가 "사건 후보가 있는 달을 성사 달로"라고만 해 방향을 구분하지 않아 '최대한 빨리'와 결합되자 가장 이른 국면 달 2027-02 가 성사 달로 올라감 ②성사 방향 후보 2027-04 가 2턴 답에서 통째로 빠짐 ③1턴 답에 두 칸 표지가 없어 `entry_slots`가 비고(`entry_window_audit=miss`), 승계 지시가 명시 시점 후속에만 붙어 '언제' 열린 후속엔 원래 비켜 감. 부차: 1턴 입력 안에서 월별 요약(우세 사건 '계약·문서', 취업은 동반 신호로만)과 이벤트 후보 블록(취업 성사 매우 강)이 긴장.
- 교정 ①(엔진 배정, 채팅·리포트 공용 `saju_engines/entry_slots.py`): `assign_entry_slots` — 월 단위 진입 후보를 `result_direction(quality)==positive`·지연 라벨 아님·검토월 아님이면 **성사 달 후보**, 그 밖은 **움직이는(국면) 달 후보**로 결정론 분리(같은 달에 둘 다 있으면 성사). `entry_slot_directive` → `[진입 시기 두 칸 — 엔진 배정] 성사 달 후보(결과 방향 긍정): 2027-04(甲辰)·2027-05(乙巳) / 움직이는 달 후보(…): 2026-12·2027-02·2027-03. 국면 달을 성사 달로 세우지 말 것 … '가장 빠른·최대한 빨리' 질문이므로 성사 달은 그중 가장 이른 2027-04 … 성사 달 후보는 각각 한 번씩 다룰 것`. 성사 후보가 없으면 "성사 달 후보 없음 — 지어내지 말 것". `is_earliest_question`(최대한 빨리·가장 빠른·빨리)이 가장 이른 성사 달을 못박는다. `ENTRY_WINDOW_DIRECTIVE` 문안도 "성사 방향(기회·유입) 후보가 있는 달을 성사 달로, 국면·압박·지연 후보 달은 움직이는 달로(엔진 배정 블록이 있으면 그 배정)"로 개정. 리포트 J-06·J-07 도 `domain_candidates("career")`로 같은 배정 지시를 붙인다. 점수·판정·후보 선별 불변(지시문 전용).
- 교정 ②(승계): `ChatPostprocessContext.entry_slots_engine`(배정의 `{'done','move'}`)을 prep 이 싣고, 동기·비동기(`update_thread_offer(engine_slots=)`)·비로그인 경로가 `_record_entry_slots(engine_slots=)`로 넘긴다. 저장 규칙: `done`은 엔진 배정 우선(답 파싱은 보조, 어긋나면 `entry_slots_mismatch` 로그), `move`는 답 파싱값(사용자 리드타임) 우선·없으면 엔진값, `source`(engine|answer) 기록. `_prior_entry_slots_directive`는 **같은 사건 키면 링크 판정(NEW)과 무관하게** 주입하고, 시점을 열어 둔 '언제' 후속엔 `_PRIOR_ENTRY_SLOTS_OPEN_DIRECTIVE`("직전 성사 달을 뒤집어 다른 달을 새 성사 달로 올리지 말 것, 더 이른 달은 앞 단계")를 쓴다. 연 단위 명시('2027년')는 월 두 칸 승계 대상이 아니다.
- 교정 ③(관측): `answer_label_audit.audit_entry_candidate_coverage` — 엔진 성사 달 후보가 답에 한 번도 없으면 `entry_candidate_coverage result=violation omitted=[…]`(로그 전용, 교정 없음 — 2026-10-14 정책). '12월' 안의 '2월' 오탐 제외.
- 재생(dry-run, 2026-10-24 기준): 1턴 프롬프트에 `성사 달 후보: 2027-04(甲辰) / 움직이는 달 후보 없음`, 엔진 슬롯 `{done: 2027-04}` 저장 → 2턴 프롬프트에 `성사 달 후보 2027-04·2027-05 / 움직이는 달 2026-12·2027-02·2027-03 … 가장 이른 2027-04` + `[진입 시기 — 직전 안내 유지] 성사 달 2027년 4월 … '언제' 질문`. 반례 테스트 `tests/unit/test_entry_slots_assignment.py`(실답 Top-5 구성·지연/검토월/손실 제외·성사 후보 없음·'언제' 승계·커버리지 감사·실답 명식 dry-run 회귀, 픽스처 `tests/unit/fixtures/entry_slots_birth_19801122.json`). 기존 `test_entry_window_consistency.py`의 승계 조건 단언은 새 규칙으로 개정.
- 후속 두 건(2026-10-24 데굴님 "남은 결정 사항도 권유 형태로 처리하자" → 권고안대로 구현):
  - A. 유력 달 종합의 '동반 신호로만' 격하: 질문 사건 자체가 그 달의 선별 후보로 70점(`ASKED_EVENT_STRONG_MIN`, '가능성이 높습니다') 이상이면 격하하지 않고 "이 달의 최상위 신호는 '계약·문서'이고 질문하신 '취업·합격'도 강한 후보(신호가 매우 강합니다)로 함께 있다 — 둘을 함께 서술하고 격하하지 말 것"으로 바꾼다(`context_reducer.asked_event_score_in_period`). 우세 사건 산출 규칙·점수는 불변, regression_2025_08(이사 우세·이직 2순위 약함) 경로는 그대로 '동반 신호로만'.
  - B. 결정 행동 허용 시기: `chat_service._decision_periods` — 진입 사건 질문이면 두 칸 엔진 배정의 국면·압박 달을 허용에서 빼고 `준비·검토 시기(결정 권고 금지): …` 줄로 따로 낸다(`counseling_block_lines(review_periods=)`; 성사 후보가 없으면 '허용 시기: 없음'). 연 단위 후보는 허용 유지. 월 커버리지 감사의 격상 검사도 같은 허용 목록을 쓴다(국면 달 수락 권고 = 위반 로그). 다른 사건 키·인자 없음은 기존 byte 불변.
  - 재생(2턴): `결정 행동 허용 시기: 2027-05, 2027-04` / `준비·검토 시기: 2027-02, 2027-03, 2026-12`. 1턴: 격하 문구 대신 함께 서술 문구.
- 실답 감수는 다음 실사용 턴에서 `entry_candidate_coverage`·`entry_slots_recorded(source=engine)`·`entry_window_audit`·`month_coverage_audit` 로그로 확인.

### 4-7. "확정 성사 달은 어떻게 판단하나" — 두 칸 배정 모드와 정밀도 측정 (2026-10-24, thread web-mvm8zqyr 3턴 "앞으로 6개월간의 내 취업운")
질문(데굴님): 성사 달 판단 근거가 모호하면 검색으로 보강, 현대 명리 비중. 확인한 현재 구조는 3층 — ①사건 발생 가능성(점수): `transit_ten_god_branching` 의 job_gain 게이트(1차 정관·편관·정인, 보조 정재·편재, 강한 조합 관인상생·재생관·살인상생) + 반복·공망·12운성·개인 글자 가중 ②길흉 방향(quality): `_period_role`(운 글자 오행의 용희기구, 천간 우선·지지 보조, 합거 글자 건너뜀) → `YongiQualityEngine` 이 용희신=opportunity('취업 성사 가능성'), 기구신=pressure('구직·채용 국면'), 공망 충발=delay 로 라벨 ③두 칸(§4-6 오전): 방향 긍정·지연 아님·검토월 아님만 성사 달. 즉 성사 여부가 **그 달 글자가 용희신인지**로 정해지고 있었다. 6개월 답("성사 달 후보 없음")은 이 규칙대로다 — 창 안 2026-11~2027-03 이 전부 기구신(水·木)/지연, 성사 후보 2027-04·05 는 창 밖.
- **실이력 대조(데굴님 입사 13건, 같은 연도 149달 기저율)**: 트리거 점수 85 이상 — 기저율 53% vs 입사 달 75%(9/12); 용희신 방향 성사 후보 — 기저율 49% vs 입사 달 25%(3/12, 반대 신호); 지연 표지(亥월 공망 충발) — 기저율 16% vs 입사 달 33%(2004·2021·2022·2025년 11월 전부 실제 입사). 입사 달 십성은 관성 5·재성 8(지지 亥 정재 5)·인성 4·비견 3. 2003-11 은 후보 없음.
- **현대 통설(웹, 블로그·상담 사이트 — 학술 근거 아님)**: 관성운=자리가 생기는 때, 인성운=서류·자격·합격 통보, 식상운=이직 욕구, 재성=조건·실속; 관인상생·재생관·살인상생이 가장 안정적인 성사 조합; 대운(큰 흐름)→세운→월운(실행 시점); 용신이면 효과가 강하고 기신이면 노력 대비 결과가 아쉽다(결과의 질). 기신 관성운이라 자리가 안 생긴다는 자료는 없음. 리포 원칙 "길흉=용신·기신, 사건 종류=십성"과 같은 방향. 참고: hyuninsaju(취업·이직 운 — 관성·식상 흐름), sajulatte(취업운·합격 시기 / 시험운), dohwaroun(십성으로 보는 직업운), sazasaju(이직 시기), jonsewose(정관·편관 위치), KAIS 진로상담 논문.
- **적중률 정의(데굴님)**: "성사 가능하다고 한 달 가운데 실제 성사된 달의 비율"(정밀도). 재현율·기저율 대비 배수는 참고.
- **구현**: `saju_engines/entry_slots.py` 두 모드(`SAJU_ENTRY_SLOT_MODE`) — `trigger`: 성사 가능 달 = 사건 신호 점수 ≥ `ENTRY_DONE_MIN_SCORE`(`SAJU_ENTRY_DONE_MIN_SCORE` 로 재지정), 용기신은 **조건 등급**(순조/완화(흉신 묶임)/조건 불리(처우·강도 주의))으로 병기, 지연은 '시점 이연 가능' 주석, 검토월은 '계약 유지력 낮음' 주석, 움직이는 달 = 55~하한 미만; `direction`: §4-6 규칙 보존(회귀·비교). 지시문은 모드별 문안(trigger 는 '가장 빠른 성사 가능 달'과 '조건까지 순조한 가장 이른 달'을 나눠 말하게 함, 조건 불리 달을 불성사·국면으로 격하 금지). 채팅은 두 모드를 병행 계산해 `entry_slot_modes` 로그로 남기고, direction 전용 약함 예외(`_entry_window_weak_note`)는 direction 모드에서만 붙는다. `_decision_periods` 는 성사 (가능) 달만 허용, 그 밖의 월 후보(55 미만 포함)는 준비·검토 시기. arbiter 문구 모드 중립('성사 기준에 못 미치는 달'). `ENTRY_WINDOW_DIRECTIVE` 는 배정 블록을 따르라는 문안으로 일반화.
- **측정(`scripts/measure_entry_slot_modes.py`, 유지 스크립트 등재)**: 확정 입사 월이 있는 4명, 첫~마지막 입사 절기년 전 달(입사 없는 해 포함) 456달, 입사 17건. `var/entry_slot_modes_20261024.md`:

두 칸 배정 모드 정밀도 — 대상 4명, 모집단 456달, 실제 입사 17건, 기저율 3.7%

| 변형 | 성사 가능 표지 달 | 그중 실제 입사 | 정밀도 | 재현율 | 기저율 대비 |
|---|---|---|---|---|---|
| direction | 222 | 4 | 1.8% | 23.5% | ×0.48 |
| trigger70 | 420 | 15 | 3.6% | 88.2% | ×0.96 |
| trigger85 | 340 | 14 | 4.1% | 82.4% | ×1.10 |
| trigger90 | 273 | 11 | 4.0% | 64.7% | ×1.08 |
| trigger95 | 109 | 7 | 6.4% | 41.2% | ×1.72 |
| trigger70+pos | 229 | 6 | 2.6% | 35.3% | ×0.70 |
| trigger85+pos | 181 | 5 | 2.8% | 29.4% | ×0.74 |
| top1 | 38 | 1 | 2.6% | 5.9% | ×0.71 |
| top2 | 76 | 1 | 1.3% | 5.9% | ×0.35 |
| top3 | 114 | 3 | 2.6% | 17.6% | ×0.71 |
| top3&85 | 103 | 3 | 2.9% | 17.6% | ×0.78 |

  상대 순위(top-k)는 점수 포화(100 다수)로 변별력이 없고, 방향 결합(+pos)은 모든 하한에서 lift 를 낮춘다. **채택: trigger · 95** (정밀도 6.4%, ×1.72, 재현율 41%). 85(×1.10)는 전체 달의 75%에 표지가 붙어 변별이 약하다. 절대 정밀도가 낮은 것은 월 단위 입사가 희귀(기저율 3.7%)해서이며, 표본(4명·17건, 13건이 한 명)이 작으므로 이력이 쌓이면 재측정한다.
- **재생(기본 모드)**: 1턴 '내년 4월 취업?'(2027-04 한 달, 점수 95 미만) → `성사 가능 달 없음 … 움직이는 달 후보: 2027-04`, 슬롯 저장 없음. 2턴 '최대한 빨리 언제' → `성사 가능 달: 2027-02(壬寅 · 조건 불리) / 움직이는 달: 2026-12·2027-03·2027-04·2027-05`, 허용 시기 2027-02, 준비·검토 2027-05·03·04·2026-12, 슬롯 `{done: 2027-02, move: 2026-12}`. 6개월 → 성사 가능 2027-02(조건 불리), 움직이는 2026-12·2027-03. 두 턴이 같은 달(2027-02)을 가리키되 '조건 불리'가 붙고, 2027-04 는 1턴에서도 성사 달이 아니라 두 턴 모순이 사라진다. 대신 1턴 답은 "4월은 성사 달이 아니라 움직이는 달"이 된다 — 다른 사주가 4월이라 한 것과 다른 판정이지만, 정밀도 기준에서는 이것이 데이터가 말하는 바다.
- 테스트 `tests/unit/test_entry_slots_assignment.py` 전면 개정(두 모드·하한·조건 등급·env 재지정·실답 회귀 — 기본 모드 기대값 + direction 모드 분할 병기). 미결: 2027-04 가 1턴에서 '움직이는 달'로 내려간 것이 실답 감수에서 어색하면 하한 90(×1.08)으로 완화 가능 — 그 경우 정밀도는 4.0%.

## 5. 결정 기록

1. 퇴사 키 `resignation` — 승인(원장 전용 키로 구현, §2-2).
2. 군복무·인턴 — `nature` 태그로 승인.
3. 인턴 시작일·권고사직 통보일 미상 — `month` 정밀도로 적재.
4. P1 글자 가중 초기값 `reviewed:false` 제안 후 측정 — 승인. **플래그 ON 여부는 §3-3 실측을 보고 데굴님이 결정(미결).**
