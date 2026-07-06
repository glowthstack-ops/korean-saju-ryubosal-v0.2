# 14. 캘리브레이션 해상도 개선 — 발생/경험 분리 + 영역·변동성 (확정안)

> 상태: **확정(2026-07-02 사용자 승인)**. 1차 = A+B+C, D는 스키마만(비활성). 코드 변경은 단계별 커밋.
> 배경: 기존 문항·채점이 혼재된 현실("취업은 됐지만 힘들었다")을 이진·연 단위로 뭉개 용신 후보 판별력을 잃었다. 본 문서는 그 해상도를 올리는 확정 설계다.

## 0. 대원칙 — 두 캘리브레이션의 목표 분리 (가장 중요)

| 수집 축 | 보정 대상 | 반영 경로 |
|---|---|---|
| **발생(occurrence)** | 이벤트 감지 엔진(그 신호에 사건이 실제 나는가) | 현실 캘리브레이션 → `personal_calibration.apply_personal_match`(subject_life_events) |
| **경험(experience) 극성** | 용신/희신/기신 후보 검증 | 용신 검증 → `feedback_scorer` |
| **영역별 체감** | 용신 후보 **모델 간 판별** | 용신 검증 → `feedback_scorer` |
| **mixed/변동성** | 충·형·합·교운·대운전환 검증 | `feedback_scorer`(변동성 축) |

**결정②**: 용신 모델 판별 점수에서 **발생 일치(occurrence match)는 제외**한다. 발생은 어느 용신 모델이 맞는지 못 가리는 모델-무관 감지값이므로 이벤트 엔진/personal_match로 보낸다. → "취업은 됐지만 힘들었다"를 모순이 아니라 `발생=confirmed · 경험=negative`(부담·기신성 직업 변화)로 올바르게 해석.

## 1. 공통 값 모델 (A — 정도 + 반반, 2축 분해)

`ExperienceRating`(내부 7상태): `very_positive | positive | neutral | mixed | negative | very_negative | unknown`

2축 분해(핵심 — `neutral`≠`mixed`):
- `polarity`: vp:+2, p:+1, neutral:0, **mixed:0**, n:−1, vn:−2, unknown:None
- `volatility`: **mixed:1**, 그 외:0 (좋고 나쁨이 같이 셌던 = 충·형·합·교운 신호)

FE 노출 해상도:
- **영역별 선택은 5상태**: 좋음/보통/반반/힘듦/모름 → `positive/neutral/mixed/negative/unknown`
- `very_positive`·`very_negative`는 **연도 전체 평가·사건 강도**에서만.

## 2. 스키마 (P0)

- **용신 `FeedbackAnswer`**: `event_ratings` 값 → `ExperienceRating`(승격). **`domain_ratings: dict[domain, ExperienceRating]` 활성**(4도메인: career/money/relationship/health). `overall_rating`(약보조) 유지. `intensity`·`confidence` 선택.
- **용신 `CalibrationQuestion`**: 모델별 **도메인 기대**를 부착 — `domain_expectations: dict[model_type, dict[domain, DomainExpectation]]`(질문 생성 시 계산).
- **`DomainExpectation`**: `{expected_polarity: float|None, expected_volatility: float|None, signal_strength: float, status: "scored"|"no_signal"}`. **결정③ — `no_signal`≠`neutral`**(모델이 그 영역 판단 근거 없음 vs 평온 예상).
- **현실 `RealityCalibrationYearAnswer`/`OccurredEvent`**: `OccurredEvent`에 `experience: ExperienceRating|None`·`intensity: int|None`; 연 단위 `overall_rating`·`domain_ratings`; `period_nuance`(비활성).

### 결정① — 현실 캘리브레이션 저장 분리
- `subject_life_events`(테이블): **발생/미발생 기반 personal_match 전용 유지**(구조 불변).
- **연 단위 체감·영역·사건별 경험은 별도 jsonb blob**에 저장(용신 `subject_yongsin.calibration`과 동형). per-year `domain_ratings`가 per-event-row에 안 맞으므로 컬럼 억지 부착 금지. `experience`의 row 컬럼화는 검색·집계 필요 시 후속.

## 3. 채점 (P1) — 용신 모델 판별

**결정③ 도메인 기대극성 산출**: 새 도메인→십성 매핑 금지. 기존 이벤트 후보의 `expected_by_model`/`favorability_map_from_model`을 `shadow_scoring._DOMAIN_KEY` 기준으로 집계:
1. `_DOMAIN_KEY`로 이벤트를 도메인 귀속.
2. 이벤트별 모델 기대극성 읽기.
3. confidence/signal_strength 가중.
4. 동일 계열 중복은 **family cap**.
5. 후보 부족 도메인은 `neutral` 아님 → **`no_signal`**(채점 제외).

**가중치(용신 판별 전용)** — 기존 `발생30/영역45/변동15/강도10` → 변경:

| 항목 | 가중 |
|---|---|
| 영역 극성 일치(domain polarity) | **60** |
| 변동성 일치(volatility) | **20** |
| 사건별 경험 극성(event experience) | **10** |
| 강도·확신도(intensity·confidence) | **10** |
| ~~발생 일치~~ | **제외**(→ personal_match) |

`no_signal` 도메인은 분모에서 제외. 모델 prior(confidence)로 가중 후 primary 기준 확정(기존 유지). 이벤트 엔진 캘리브레이션은 별도 점수 체계.

## 4. 문항 UX (P2) — 3단계

① 연도 전체 체감(7상태) → ② 영역별(5상태: 좋음/보통/반반/힘듦/모름) → ③ 실제 사건 발생 + 사건별 "결과 어땠나(좋음/힘듦/반반/판단어려움)". 화면당 부담 분산.

## 5. D 보류 — `period_nuance` 스키마만(비활성)

`{has_peak_period, peak_granularity(season|month|half), peak_value, peak_experience}` 스키마만 남기고 미노출. **후속 발동 조건**(고해상도 선택 입력):
1. 모델 간 점수 차가 작아 용신 후보가 갈릴 때.
2. 고확신 응답인데 모델 기대와 강하게 불일치할 때.
3. `volatility_score` 높은 해(교운·충형 중첩·대운 전환기).
4. 사용자가 "그해 특정 시기가 유독 달랐다"고 응답할 때.

## 6. 구현 순서 (단계별 독립 커밋)

- **P0**: 스키마(ExperienceRating·2축맵·FeedbackAnswer·DomainExpectation·현실 answer·period_nuance) — 기존 필드 유지(하위호환).
- **P1**: 도메인 기대극성 집계기 + `feedback_scorer` 재구성(발생 제외, 영역/변동성/경험/강도).
- **P2**: `question_generator` 도메인 기대 부착 + 프런트(CalibrationPanel 3단계·5상태, StepRealityCalibration 경험/영역).
- **현실 blob 저장소**: 연 단위 체감/영역/경험 jsonb(용신과 동형). subject_life_events는 occurrence 유지.

불변 가드: 기존 `outcome`·`overall_rating`·`event_ratings`·`personal_match` 하위호환. 명리 규칙 신규 추가 없음(기존 기대극성·용신 모델 재사용).

## 7. 후속 설계 포인터 (본 문서 범위 밖)

- **CAL-P0(2026-07-03 구현 완료)**: 교운기 우선 질문 배치(`transition_probe` — ranking
  boost 전용) + 성향 동의/반박 수집(`trait_probe` — 채점 절대 비반영, accumulate_only).
  출처: `../cases/1980_1122_job_report_case.md` §7.
- **CAL-P1(설계안)**: 정적 결핍 vs 운 작동 이원 질문 쌍(`static_deficiency_probe` +
  `transit_activation_probe`) + `trait_denial_kind` 태깅 —
  `../CALIBRATION_STATIC_TRANSIT_PROBES.md`. 두 probe 계열 모두 본 문서의 용신 판별
  채점(§3)에 개입하지 않는다(불변식은 해당 문서 §5).

## 8. CAL-QA — 무신호 응답 상태 추가 (2026-07-03 확정, pre-release data hygiene)

배경: 기존 응답 체계는 경험 극성(좋음~힘듦)은 받지만 **가장 중요한 반증값인 "그 일이
없었다 / 그 영역이 비활성이다"를 받지 못한다**(직장인이 학업 질문을 받으면 고를 답이
없음). 오픈 후 이 상태로 쌓이면 무응답·기억 안 남·실제 없음을 분리할 수 없어 R-2·CAL-P2
개인화 보정 데이터가 오염된다 — 기능 확장이 아니라 **데이터 계약 수정**.

1. **영역별 체감에 `no_domain_activity` 추가** ("특별한 일 없었음")
   - 의미: 해당 기간 해당 영역에서 특별히 평가할 활동·사건이 없었음.
   - `unknown`(기억 안 남)과 **구분**한다(혼합 금지). 채점 제외 + 분모 제외.
   - raw calibration record(answers blob)에는 값 그대로 저장한다.
   - 명명: `not_applicable`은 '영역 자체가 무관'으로 읽힐 수 있어 배제.
2. **이벤트별 결과에 `not_occurred` 추가** ("그런 일 없었다")
   - 의미: 엔진이 제시한 이벤트 후보가 실제로 발생하지 않았음.
   - **용신/기신 검증 채점에는 사용하지 않는다**(결정② — 발생은 용신 판별 축이 아님).
     `not_occurred`를 '기신 아님·신호 약함'으로 즉시 해석하는 구현 금지 — 그건 용신
     검증이 아니라 이벤트 엔진 개인 적합도 검증이다.
   - subject_life_events/personal_match 승격은 **CAL-P2에서 판단**. 현재는
     accumulate_only(응답 blob 저장)만.
   - 레거시 `na`("해당없음")는 의미가 같으므로 **무신호로 매핑**해 동일 처리(채점 제외 +
     브랜치 판정 제외). 저장 값은 변형하지 않는다(FE 표시 정규화만 unknown).
   - **브랜치 불변식**: 무신호만 고른 이벤트 응답은 '아무것도 고르지 않은' 응답과 채점
     결과가 완전히 동일해야 한다 — 무신호가 이벤트 브랜치를 열어 연도 전체 평점 폴백을
     건너뛰게 만들면 간접 개입(위반)이다.
3. **불변식**: final role 불변 / score·confidence·favorability 불변 / 용신 채점 분모
   오염 금지 / unknown과 무신호(no-signal) 상태 혼합 금지.

계층 분리(원칙):
```text
용신 캘리브레이션: 경험 극성만 사용 — not_occurred/no_domain_activity/unknown 채점 제외
이벤트 개인화: not_occurred 누적 → 반복 패턴 충분 시 personal_match 보정 후보(CAL-P2)
```
