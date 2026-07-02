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
