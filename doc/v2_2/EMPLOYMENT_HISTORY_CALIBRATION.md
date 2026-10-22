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

### 4-2. 2차 감수 교정 (2026-10-22, thread web-mvjij2wx "언제 취업할 수 있을까" / "돈이 없어서 빨리 취업해야해")
확인: 수치 라벨이 2턴에 "11건 중 4건"으로 닿았고(회사명 없음), 통로 블록 두 턴 반영(관성·인성 / 비겁·식상), 두 칸은 역할 구분만 되고 첫 문단 이름표('성사 달·움직이는 달')는 없음. 1턴은 숫자 없이 "반복되는 경향"으로 뭉뚱그림. 새 누수: "성취 신호가 1위로 나타나지만"(창 내 상대 순위 블록 내부 용어), "2026-12 庚子월"(후보 라벨 원문). 기존 결함: 1턴 일주 소개 두 문장이 참조 예외(`ilju_mention_kept_referenced`)로 통과.
- 교정 ①: `_PERSONAL_REPEAT_DIRECTIVE`를 "숫자(일치/표본)를 그대로 적어라 — 뭉뚱그리지 말 것"으로 강화. 두 칸 이름표 준수는 `ChatPostprocessContext.entry_window` + `answer_label_audit.entry_window_labels_present`로 **로그만**(`entry_window_audit result=pass|miss`).
- 교정 ②: `saju_engines/answer_label_audit.py` — `rewrite_rank_labels`('1~3위'+조사 → 가장 강하게/두 번째로/세 번째로, 10위권·2·3위 제외), `rewrite_raw_period_labels`('YYYY-MM' 단독 → 'YYYY년 M월', 날짜·범위 제외). `finalize_answer_text`에서 거짓 역접 교정 뒤 적용, 로그 `internal_label_rewritten`.
- 교정 ③: `ilju_mention_audit.strips_referent` — 질문 유형으로 걸린 답(총운·시기·택일)은 참조 예외 없이 지시 문장까지 제거(`removed_referents`, 로그 `ilju_mention_referent_stripped`). 분야 개요(domain_analysis)는 기존 예외 유지. 기존 테스트 2건은 새 규칙으로 개정(택일 답의 '이러한 성향은 … 월운을 만나며' 문장도 성향 서술이라 함께 제거).

## 5. 결정 기록

1. 퇴사 키 `resignation` — 승인(원장 전용 키로 구현, §2-2).
2. 군복무·인턴 — `nature` 태그로 승인.
3. 인턴 시작일·권고사직 통보일 미상 — `month` 정밀도로 적재.
4. P1 글자 가중 초기값 `reviewed:false` 제안 후 측정 — 승인. **플래그 ON 여부는 §3-3 실측을 보고 데굴님이 결정(미결).**
