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

## 3. P1 — 지문 확장과 적중 측정 (PR 2)

### 3-1. 지문
`SignalFingerprint`에 선택 필드 추가:

| 필드 | 값 | 비고 |
|---|---|---|
| `glyphs` | `{sewoon_stem, sewoon_branch, wolwoon_stem, wolwoon_branch}` | 해당 달의 네 글자 |
| `natal_echo` | 운 글자가 겹치는 원국 자리 목록 (`month_branch`, `day_branch` …) | 亥=월지·일지 같은 재현 |
| `prev_month` | 전월(달력 한 달 전 날짜의 절기월) 네 글자 | 기회 달. 당월과 독립 가산 금지 — 유사도 항 하나로만 |

### 3-2. 유사도와 기저율
- `fingerprint_similarity`에 글자 항 추가. 초기 가중은 `reviewed:false`로 사전에 두고 기존 상한(±8점·±1티어)은 유지.
- 개인 기저율 lift = (해당 글자에서 사건 비율) / (전체 기간 중 그 글자 달의 비율). 사건 표본 5건 미만이면 lift 산출 금지. lift는 **근거 코드 `PERSONAL_GLYPH_REPEAT`와 서술에만** 쓰고 점수엔 넣지 않는다(측정 전).
- `resignation` 시그니처는 입사 후보 매칭에서 제외(Exit/Entry 분리의 실효).

### 3-3. 적중 측정(ON 판정 기준)
- 데굴님 명식 leave-one-out: 정규·파견 입사 11건 중 1건을 빼고 나머지 10건으로 지문을 만든 뒤, 그 해 12개 절기월 중 Top-3에 실제 입사월이 드는 비율. 기준선 = 지문 확장 전 같은 절차.
- 85사례 replay 적중 불변 + 연도 top-1 변동 보고.
- 두 지표가 모두 하락하지 않을 때만 점수 반영 플래그(`SAJU_PERSONAL_GLYPH_SCORE_ENABLED`, 기본 OFF) ON 제안.

## 4. P2 — 노출 (PR 3)

- 취업 시기 답(채팅·리포트 커리어 섹션): "움직이는 달(접수·제안) + 성사 달(입사)" 두 칸. 창 기본 1~2개월, 사용자가 리드타임을 말했을 때만 좁힌다. 행동 제안은 접수 달에 붙인다.
- 연결 사례: 후보 달마다 같은 월운의 과거 입사 `label`을 한 줄 인용("2021년 11월 입사 때와 같은 월운"). 사용자 제공 사실이라 점괘화 금지와 충돌 없음. 단정 금지 어휘는 기존 감사 그대로.
- 통로 제안: 운 십성→관계 유형 매핑(`ten_god_relations.json`)으로 "사람 통로 우선 / 공고 통로 우선" 한 줄.
- 입력 UI: `StepRealityCalibration` 옆에 선택 탭 "직장 이력" — 행 단위(회사명·입사월일·퇴사월일·성격·통로·같은 직장 묶기). 날짜는 일 단위 선택, 모르면 월만.

## 5. 결정 필요 항목

1. 퇴사 키 `resignation` 추가(규격 내) 승인 여부.
2. 군복무·인턴을 키가 아닌 `nature` 태그로 두는 방식 승인 여부.
3. 인턴 시작일(2003.11 초순 여부)·권고사직 통보일. 모르면 `month` 정밀도로 적재.
4. P1 글자 가중 초기값은 제가 `reviewed:false`로 제안하고 측정으로 결정 — 동의 여부.
