# 사전 감수 대기 목록 (별도 릴리즈)

> 기능 개발 완료 조건과 **분리된** 목록이다. 사전 감수를 기능 출시 게이트로 묶으면
> 감수 표본이 쌓이기 전에 전체 일정이 멈춘다(D22 — "내부 검수 후 오픈" 모델 폐기).

## 원칙

- 구조 검증과 명리 감수는 다르다. 전자는 컴파일 파이프라인이 보장하고, 후자는 사람의
  판단이다. **파이프라인 통과가 `reviewed` 를 참으로 만들지 않는다.**
- `reviewed:false` 인 채로 서비스하는 것 자체는 금지가 아니다. 금지는 **감수하지 않은
  것을 감수했다고 기록**하는 것이다.
- 빠르게 끝낸다는 이유로 `reviewed:true` 로 바꾸지 않는다 — 어떤 규칙을 승인했는지
  추적할 수 없게 된다.

## 상태 어휘 (오해 방지)

```
runtime_status = ACTIVE   → 점수·등급 산출에 실제로 쓰인다
review_status  = PENDING  → 명리 감수 미완료
```

**`review_status=PENDING` 은 "계산 미사용"이 아니다.** 두 축을 분리해 선언하지 않으면
나중에 `reviewed:false` 를 비활성 규칙으로 오해해 영향 범위를 잘못 판단하게 된다.
컴파일 검증이 두 필드의 선언을 강제한다(`validate_sources`).

## 오늘의 운세 사전 3종 (2026-07-26 등록, dict.v1.8)

### `daily_fortune/daily_event_catalog.json`

| 항목 | 내용 |
|---|---|
| runtime 사용 | **ACTIVE** — 사건 후보·도메인·확률의 원천 |
| 점수 영향 범위 | 전면. 60일주 × 3슬롯(good/caution/support) 전부가 이 카탈로그에서 나온다 |
| 대표 출력 사례 | "오늘 뜻밖의 수입이 생길 확률 62%", 연애 신호(`love_line`) 선정 |
| 논쟁점 | 일진-사건 매핑의 명리 타당성, 도메인 분류 경계(work↔social), 확률 밴드 폭 |
| 감수 후 가능한 변경 | 사건 추가·삭제, 도메인 재배정, 슬롯(good/caution) 재분류, 확률 범위 조정 |
| 관련 fixture | `tests/unit/test_daily_fortune_dicts.py`(카탈로그 수·스키마·caution 전용 슬롯·동의어 그룹) |

### `daily_fortune/daily_phrase_templates.json`

| 항목 | 내용 |
|---|---|
| runtime 사용 | **ACTIVE** — 사용자 노출 문장 전부 |
| 점수 영향 범위 | 없음(문구 전용). 점수는 카탈로그가 정한다 |
| 대표 출력 사례 | `love_reunion` 여운·정리 문구, 행운의 장소 문장, 로또 문구 |
| 논쟁점 | 밝은 단정 톤과 절대원칙 3(단정 금지)의 경계, 재회 서술의 기대 조성 수위 |
| 감수 후 가능한 변경 | 문구 교체·변형 추가, 톤 조정. **사건·확률은 바뀌지 않는다** |
| 관련 fixture | 같은 파일(커버리지 최소 변형 수·금지 명리 용어·한자 미노출·로또 정책·placeholder) |

### `daily_fortune/daily_lucky_places.json`

| 항목 | 내용 |
|---|---|
| runtime 사용 | **ACTIVE** — 행운의 장소 선정 |
| 점수 영향 범위 | 없음(장소 선정 전용) |
| 대표 출력 사례 | "동네 서점", "물 가까운 곳" |
| 논쟁점 | 오행-장소 대응의 자의성. 규격상 "정확성보다 기억성·재미 우선"으로 설계됨 |
| 감수 후 가능한 변경 | 장소 추가·삭제, 오행 재배정 |
| 관련 fixture | 같은 파일(`test_places_schema`) |

**2026-09-10 추가분(dict.v1.13, 외부 감수 전)**: ①사건 16종(§22-7 — good 11·caution 5, v1/v2 카탈로그·taxonomy.v2·문구 템플릿) ②표현 결 풀(§23 — 사건×십성 행동 1,280 + 5군 폴백 640, 12운성 채널 결과 42, 사건별 채널 제외 18슬롯). **내부 전수 감수 완료(2026-09-10 2차, docs/17 §23-5)**: 행동 42건·결과 16건 교체, 모순 조합 84건 해소. 결 풀은 점수에 영향 없음(문체 전용). 채점 규칙 지적 5건(body_light·procrastination 사문 감점, answer_arrives 삼합·learning_click 육합 가중 누락, opinion_accepted 상관+정관 동시 가점)은 사용자 승인으로 §22-7 2차 개정에 반영(model.v2.1 in-place). love_spark 삼합 .3 도 3차에서 반영. 3차 추가분: 12스테이지 결과 풀 72문장(§23-6, 내부 감수 교체 23건) — 외부 감수 대상. 4차(§22-8): 잔여 12운성 채널 4종(흔들림·단장·노련·구상) B안 배선 14사건 — 채점 규칙이라 외부 감수 우선순위 높음.

**우선순위 근거**: 60일주 전체 사용자에게 매일 반복 노출되므로, 잘못된 규칙 하나의
노출 범위가 커리어 beta 보다 넓다. 다만 커리어 완료 조건은 아니다.

**현재 보호 장치**(감수 전에도 유지되는 것):
- `validate → compile(snapshot) → regression` 파이프라인 통과분만 서비스
  (`compiled/daily_fortune_{DICT_VERSION}.json`, `structural_validation: passed`)
- 사전 수정 후 `DICT_VERSION` 미갱신·재컴파일 누락은 회귀가 차단
  (`tests/regression/test_daily_fortune_snapshot.py`)
- 금지어·한자 노출·로또 정책·커버리지는 `tests/unit/test_daily_fortune_dicts.py`

**감수 후 절차**: 해당 파일의 `reviewed` 를 `true`, `review_status` 를 `APPROVED` 로,
`review_note` 를 감수자·일자로 바꾸고 `DICT_VERSION` 을 올린 뒤
`python scripts/build_daily_fortune_snapshot.py` 재실행.

## 그 외 대기분

- 위험 사전 REL 7 · MOV 6 · HLT 8 · LEG 6 — `doc/v2_2/RISK_DICTIONARY_REVIEW.md`
- 지역 오행 Tier B — `doc/v2_2/docs/12_REGION_ELEMENT_ENGINE.md`

**2026-09-10 사문 감사 후속**: `event_engine/void_repetition_modifier.json` 은 `runtime_status=PARAMETER_SOURCE`(void_unresolved 만 코드가 읽음), `user_profile_event_gate.json` 은 `SPEC_ONLY`(implemented_by 로 구현 여부 선언 — 미구현 6건). 감수 시 "코드가 읽는 필드" 만 점수에 영향이 있음을 전제로 볼 것.

**2026-09-10 신설 `career_fields.json`(reviewed=false)**: 데굴님 제공 십성×직업 기능 참고표를 그대로 옮김. 감수 관점: 학파별 배속 차이, `thresholds`(강함 25%·과다 30%·두드러짐 10% — 자료에 없는 기계 기본값), 배합 파생 규칙 2건(비겁→식상·인성→일간→식상은 구조 패턴 id 없이 군 활성으로 판정).
