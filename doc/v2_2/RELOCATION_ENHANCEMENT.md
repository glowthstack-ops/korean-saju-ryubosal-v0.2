# 이사운 고도화 (Relocation Enhancement) — R1~R4

> 사용자 스펙(2026-06-17) 기반. 본 문서가 이사운 4단계 시스템의 단일 진실 공급원(SSOT)이며,
> `docs/02`(E10)·`docs/09`(7장 M10)·`docs/05`(사전)의 이사 관련 항목을 보강한다.

## 0. 핵심 원칙

> **이사 '발생'은 합·충·역마·재관 자극이 보고, 십성은 '왜 이사하고 어떤 집으로 가는가'를
> 분류한다. 계약일은 정관·정인(서류), 이삿날은 정재·정관(실행)을 우선하며, 충은 이벤트
> 탐지에는 긍정 신호지만 택일에서는 돌발 리스크로 감점한다.**

- 탐지·분류·점수·날짜는 전부 코드가 계산한다(절대원칙 1). 십성 분류는 **해석 라벨 전용**으로
  점수·날짜·랭킹에 개입하지 않는다(절대원칙 1·12).
- 천간 = 겉으로 드러나는 명분(이유), 지지 본기 = 실제 사건 현장(집 성격)(사용자 스펙 5장).
- 대운=배경 / 세운=그 해 주제 / 월운=실제 발동 / 일운=계약일·이삿날 택일.

4단계 파이프라인:

| 단계 | 내용 | 주 신호 | 구현 |
|---|---|---|---|
| 1 탐지 | 이사 발생 가능성 | 일지/월지 충·합, 역마, 재관 활성, 공망 해소, 교운기 | `events/relocation.json`(13규칙) — 기존 |
| 2 이유분류 | 동기·집 성격·리스크 | 운의 십성(천간/지지) | R2 (M10 reasonProfiles) |
| 3 택일 | 계약일/이삿날 분리 | 일진 십성·관계 | R3 (E10 + M10 S9) |
| 4 리스크/대상 | 체크리스트·집/사무실 | 십성 리스크, 궁 분기 | R1 사전 + R4 |

## 1. 사전 (R1)

신설 사전 2종(전 항목 `reviewed:false` 초안 — 검수 게이트 전 운영 반영 금지, 절대원칙 5).

### `dictionaries/interpretations/relocation_ten_gods.json`
십성 10종 × `{type, moveReason, propertyTendency, risk, requiredChecks, riskLevel, mainQuestion, basis}`.
이사의 이유·집 성격·리스크·계약 전 체크리스트를 분류한다(사용자 스펙 3~8·15장).

| 십성 | type | 핵심 리스크 |
|---|---|---|
| 식신 | 생활편의형 | 생활 동선 미확인 |
| 상관 | 비표준주거형 | 위반건축물·불법확장·용도변경 |
| 정인 | 권리안정형_임시거처 | 계약 조건·권리관계 |
| 편인 | 저비용_노후주택형 | 누수·곰팡이·노후·겉만 수리 |
| 비견 | 지인연결형 | 지인 의존·현지 조사 부족 |
| 겁재 | 탈피형 | 충동 결정·고립·재이사 |
| 정재 | 장기정착형 | 과한 인테리어·동네 조건 간과 |
| 편재 | 생활권중심형 | 집 내부 상태 간과 |
| 정관 | 직장기반형_검증주거 | 직장 치우침·가족 편의 간과 |
| 편관 | 긴축형_임시거처 | 하향 이동·장기 거주 부적합 |

### `dictionaries/calendar/date_selection_ten_gods.json`
계약일/이삿날 점수표 + 작업별 천간/지지 가중 + 충 이중성 + 사무실 이전 궁(사용자 스펙 9~12장).

- **계약일**: 우대 정관(+25)·정인(+20), 오행 水(+15)·金(+8); 회피 편인·겁재·상관·편관(−); 가중 `천간십성 0.45 / 지지관계 0.35 / 천간오행 0.20`.
- **이삿날**: 우대 정재(+30)·정관(+25), 조합 정재+정관(+20)·재관(+18); 회피 상관·겁재·편관·식신·비견·편재·편인·정인(−); 일지합(+20)·일지충(−20)·월지충(−15); 가중 `지지관계 0.45 / 천간십성 0.30 / 지지십성 0.25`.
- **충 이중성**: `chungPolicy.eventDetection = positive_for_relocation_trigger`, `dateSelection = negative_for_move_day`.
- **officeMove**: 월간·월지·월주 중심, 월간합/월지합/월주생 우대, 월간극/월지충/월주극 회피(R4 배선).

## 2. 이유분류 (R2) — M10 reasonProfiles

`RelocationResolver._reason_profiles`: 의사결정 주체(첫 대상 — 대상 우선 원칙 7)의 최상위 후보월
세운·월운 십성(천간=명분 → 지지=현장 순, 십성 dedup, 최대 4건)을 `relocation_ten_gods.json`로 변환.

- `RelocationResult.reason_profiles: list[RelocationReasonProfile]` 추가(`ten_god, source, type, move_reason, property_tendency, risk, required_checks, risk_level, main_question`).
- M10 `TopicContext.findings`: `reason@{십성}`(score=0, signals=requiredChecks)을 `move@{date}` **앞에** 배치
  (출력 순서: 요약→이유→집성격→리스크→체크리스트→택일, 사용자 14장).
- `style_rules`: "이사 발생 단정 금지 — 가능성·단계 표현, 십성 리스크 체크리스트 동반".
- **점수 미개입 불변식**: 분류 산출 여부와 무관하게 `move_dates` 점수는 동일(테스트로 강제).
- 출력 문장은 하드코딩하지 않는다 — 구조화된 reason_profiles + style_rules가 LLM의 서술 재료이며
  LLM은 제공된 사실을 자연어로 풀어낸다.

## 3. 택일 분리 (R3)

공유 헬퍼(`relocation.py` — `date_selection.py`가 import, 순환 방지):
- `branch_relations(c)` — 일운 지지와 원국 일지/월지의 합·충(`interactions`의 `natal_day`/`natal_month` 참여자 + kind)을 일지합/일지충/월지합/월지충 라벨로 판정.
- `ten_god_day_fit(c, table)` — 작업별 가중으로 0~100 적합도 산출. 점수→0~100: `clamp(50 + 점수·(50/30))`(스케일 30 초안).

연결:
- `DateSelectionEngine.select()`: 목적이 `relocation`(→이삿날)·`contract_document`(→계약일)이면
  `day_execution = round(0.5·도메인신호 + 0.5·ten_god_day_fit)`(블렌드 0.5 초안). 나머지 4부분점수·랭킹·금기일 불변.
- `RelocationResolver._contract_window`(S9): 휴리스틱 `wealth` 도메인 → **계약일 점수표**로 교체
  (정관·정인 우대, 편인·겁재·상관·편관·충 회피).

부수 — chat DB 의존 결함 수정(로또 안전정책 G6 복구):
- `/api/v2/chat` POST가 DB 스토어(history/subject)를 무조건 의존해 DSN 없으면 익명·dry-run·정책 요청도 503이던 결함.
- `deps.py`에 `get_*_store_optional`(DSN 없으면 None) 추가, POST 핸들러만 optional 의존 + None 가드.
  로그인 데이터 경로(`/threads` 등)는 엄격 버전 유지(DB 없으면 503). DB 없는 배포에서도 정책 거부·dry-run 동작.

## 4. 집/사무실 분리 (R4)

- 집 이사: 일지·일주·생활궁 중심(기존 M10 일지 기반).
- 사무실 이전: 월간·월지·월주 중심(`date_selection_ten_gods.json.officeMove`).
- `RelocationQuery.relocation_kind: 'home' | 'office'`(기본 home) 추가 — 미입력 시 기존 동작(원칙 11 optional).
- 궁 분기로 충·합 판정과 점수표 적용 자리를 전환.

## 5. 리포트/테마 반영 (총운류 — RPT_FOCUS relocation)

이사 고도화의 십성 이유분류를 리포트에도 활용한다. 단, 리포트는 EventEngineV2/EventCandidate
시스템을 쓰고 M10은 LuckComposite 기반이라, 리포트에서 대상의 YEAR/MONTH 컴포짓을 별도
산출해 R2 분류기(`RelocationResolver.classify_reasons`)를 **재사용**한다(로직 중복 없음).

- 이사 전용 테마 목차 `_RELOCATION_TOC`(RL-01~RL-08, 재물 W-* 패턴) — generic FOCUS 변형 승격.
- `_ReportData.relocation_reason_block`(RL-03 이유·집성격)·`relocation_risk_block`(RL-05 리스크·
  체크리스트)이 세운 천간(명분)/지지(현장)·월운 십성 분류를 본문 데이터로 주입.
- RL-04/RL-06은 relocation 도메인으로 스코프된 기존 운 흐름 블록을 사용. 일자 택일(DAY)은
  리포트 미포함 — 택일은 채팅 라우트 담당. 신호 약함·실패 시 빈 폴백(규칙 11).

## 6. M10 그룹 리졸버 오케스트레이션 (채팅 + 리포트)

M10 RelocationResolver(다인 집계·방위·택일 랭킹)를 production에 연결한다. 범위: 본인+첨부
상대 2인(기존 partner 메커니즘 재사용 — 요청 스키마 변경 없음). n인은 후속.

- **채팅 (`chat_service._relocation_group_block`)**: 이사 택일 질문 + 동반자 첨부 시 단일
  `DateSelectionEngine` 대신 M10 그룹 집계로 분기. [self, partner] 각각 윈도우 LuckComposite·
  용신 산출 → `RelocationQuery`(group_subjects·period·current_location·relocation_kind) →
  `resolve()`. 결과를 `DateSelectionBlock`으로 렌더(함께 무난한 이사일 랭킹 + 구성원 충돌
  경고 `group_warnings` + 방위 적합). 게이트: `_is_relocation_intent`(domain/event=relocation).
  current_location은 `constraints.location_base`(이미 파싱) 또는 "미지정"(resolver 미사용 메타).
- **리포트 (`_ReportData._relocation_ctx`)**: 이사 테마에서 YEAR/MONTH 컴포짓으로 `resolve()`
  1회(캐시) → RL-03/RL-05(이유·리스크) + **RL-04 방위 적합**(`resolver.direction_fit`) +
  **RL-06 월별 이동운 흐름·충돌**(`group_summary`). 일자 택일(DAY)은 리포트 미포함(채팅 담당).
- `DateSelectionBlock.group_warnings` 신설 + context_reducer 렌더("구성원 주의: …").
- `RelocationResolver.direction_fit`·`classify_reasons` 공개 API(day 후보 없이 방위·이유 산출).

## 구현 파일 맵

| 파일 | 변경 |
|---|---|
| `dictionaries/interpretations/relocation_ten_gods.json` | R1 신설 |
| `dictionaries/calendar/date_selection_ten_gods.json` | R1 신설 |
| `packages/saju_engines/.../dictionaries.py` | R1 스키마·lint(커버리지·가중합·충 이중성) |
| `packages/shared_types/.../relocation.py` | R2 `RelocationReasonProfile`·`reason_profiles` / R4 `relocation_kind` |
| `packages/saju_engines/.../relocation.py` | R2 `_reason_profiles` / R3 헬퍼·S9 / R4 궁 분기 |
| `packages/saju_engines/.../date_selection.py` | R3 십성 블렌드 |
| `packages/saju_engines/.../topic_builder.py` | R2 reason findings·style |
| `apps/api/.../deps.py`·`routers/chat.py` | R3 chat DB-optional |
| `apps/api/.../services/chat_service.py`·`query_parser.py`·`intent.py` | R4 사무실 이전 택일 라우트 배선 |
| `packages/saju_engines/.../report_plan.py`·`apps/.../report_service.py` | 리포트 이사 테마(RL-*) + reason 분류 surface |
| `apps/.../chat_service.py`·`relocation.py`·`context_reducer.py`·`llm_input.py` | M10 그룹 택일 채팅 연결(2인) + 방위/월흐름 리포트 surface |

## 검수 대상 (reviewed:false 초안 — 실측 튜닝 전 운영 반영 금지)

- 두 사전의 십성 매핑·점수값 전체.
- 점수→0~100 스케일 30, 택일 블렌드 0.5.
- officeMove 궁 가중 세부값.
