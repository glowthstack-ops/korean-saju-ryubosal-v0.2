# 사주서비스 v2 만세력 엔진 구축 지시서 for Codex

> 목적: v1 서비스 경험을 초기화하고, v2에서는 **정확한 시간 보정 → 결정론적 만세력 계산 → 신강/신약 9단계 판정 → 용신 후보 산출 → 사용자 과거 검증 → 확정 모델 재출력** 흐름을 구현한다.
>
> 이 문서는 Codex가 실제 코드베이스에 기능을 추가/수정할 수 있도록 만든 개발 지시서다. 구현 시 LLM은 만세력 계산을 수행하지 않는다. LLM은 계산된 구조화 JSON을 설명하거나 사용자 질의에 맞게 해석하는 역할만 담당한다.

---

## 0. 핵심 원칙

### 0.1 엔진과 LLM 분리

- 만세력 계산, 시간 보정, 오행/십성/통근/신강약/용신 후보 산출은 모두 **결정론적 엔진**에서 수행한다.
- LLM은 다음만 수행한다.
  - 구조화 결과 설명
  - 사용자 질문 의도에 맞춘 요약
  - 검증 질문의 자연어 표현 생성
  - 이미 계산된 후보와 근거를 기반으로 한 풀이
- LLM이 임의로 사주 팔자, 대운, 용신, 신강약을 다시 계산하거나 덮어쓰면 안 된다.

### 0.2 용신은 단정값이 아니라 검증 가능한 모델

- v2에서 용신은 최초 계산 시 `candidate` 상태로 둔다.
- 사용자 과거 사건 피드백을 통해 후보 모델을 검증한 뒤 `calibrated`, `probable`, `uncertain` 중 하나로 확정한다.
- 용신/희신/기신/구신은 항상 `confidence`, `source_models`, `evidence_count`를 함께 보관한다.

### 0.3 부족한 오행은 곧 용신이 아니다

- 오행 분포에서 부족한 오행과 용신은 분리한다.
- 예: 목이 부족해도, 신약한 토 일간에게 목 관성이 압박으로 작용하면 목은 기신 후보가 될 수 있다.
- UI와 JSON 모두 이 구분을 명확히 한다.

### 0.4 신강/신약은 9단계 점수형으로 판정

- 기존 `신강/신약/중화` 3분류 대신 0~100 점수와 9단계 구간을 사용한다.
- 중화권은 용신 단정 금지 구간으로 취급하고 사용자 검증을 우선한다.

### 0.5 특수격은 일반 억부보다 먼저 검사

- 종격, 전왕/일행득기, 합화/화기격, 통관, 고립/병약 구조는 일반 억부 로직보다 먼저 검사한다.
- 극신약/극신강일수록 특수격 오판 위험이 크므로 반드시 예외 필터를 거친다.

---

## 1. 전체 서비스 흐름

```text
사용자 진입
→ 생년월일시 입력
→ 양력/음력/윤달 여부 입력
→ 출생 지역 입력
→ 성별 또는 대운 순역 계산 기준 입력
→ 지역/시기 기반 시간 보정
   - 표준시
   - 서머타임
   - 경도 보정
   - 균시차
   - 진태양시
→ 절기 기준 사주 팔자 산출
→ 원국/대운/세운/월운 계산
→ 계산 가능한 통변 데이터 산출
→ 신강/신약 9단계 판정
→ 특수격/예외 구조 검사
→ 용신 후보 2개, 기신 후보 2개 산출
→ 후보별 검증 연도 또는 년월 5개 제시
→ 사용자가 길/흉/사건 분야 응답
→ 후보 모델별 적합도 계산
→ 용신·희신·기신·구신 확정 또는 보류
→ 확정 모델 기준으로 재출력
```

---

## 2. 권장 디렉터리 구조

```text
manse/
  __init__.py

  time_correction/
    __init__.py
    input_normalizer.py
    timezone_resolver.py
    dst_resolver.py
    longitude_correction.py
    equation_of_time.py
    true_solar_time.py
    time_boundary.py

  calendar/
    __init__.py
    lunar_solar_converter.py
    solar_terms.py
    sexagenary_cycle.py

  pillars/
    __init__.py
    four_pillars.py
    hidden_stems.py
    ten_gods.py
    twelve_unseong.py
    naeum.py
    gongmang.py

  relations/
    __init__.py
    combinations.py
    clashes.py
    punishments.py
    harms.py
    breaks.py
    relation_normalizer.py

  analysis/
    __init__.py
    element_distribution.py
    ten_god_distribution.py
    roots.py
    strength_score.py
    johu_score.py
    isolation_score.py
    tonggwan_detector.py
    special_structure_detector.py
    geokguk_detector.py
    stability_score.py
    palace_interactions.py
    amplifiers.py

  yongsin/
    __init__.py
    models.py
    eokbu_model.py
    support_day_master_model.py
    johu_model.py
    isolation_health_model.py
    tonggwan_model.py
    follow_structure_model.py
    dominant_structure_model.py
    transformation_model.py
    geokguk_model.py
    candidate_aggregator.py
    validation_period_selector.py
    feedback_scorer.py
    final_decider.py

  luck/
    __init__.py
    daewoon.py
    yearly_luck.py
    monthly_luck.py
    luck_effect.py

  api/
    schemas.py
    routes.py

  tests/
    test_time_correction.py
    test_four_pillars.py
    test_strength_score.py
    test_special_structures.py
    test_yongsin_candidates.py
    test_calibration.py
```

---

## 3. 입력 스키마

### 3.1 BirthInput

```python
class BirthInput(BaseModel):
    calendar_type: Literal["solar", "lunar"]
    is_leap_month: bool | None = None

    birth_date: date
    birth_time: time | None = None
    birth_time_unknown: bool = False

    birth_place_name: str
    country_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None

    gender: Literal["male", "female", "unknown"] | None = None
    daewoon_direction_basis: Literal["gender_yinyang", "manual"] = "gender_yinyang"
    manual_daewoon_direction: Literal["forward", "backward"] | None = None

    time_options: "TimeCalculationOptions" = Field(default_factory=TimeCalculationOptions)
```

### 3.2 TimeCalculationOptions

```python
class TimeCalculationOptions(BaseModel):
    apply_true_solar_time: bool = True
    apply_daylight_saving: bool = True
    apply_longitude_correction: bool = True
    apply_equation_of_time: bool = True

    day_boundary_rule: Literal["23:00", "00:00"] = "23:00"
    ja_hour_rule: Literal["standard_zi", "early_late_zi", "none"] = "standard_zi"

    compare_standard_and_true_solar: bool = True
```

---

## 4. 시간 보정 엔진

### 4.1 처리 순서

```text
입력 시각
→ 양력/음력/윤달 변환
→ 출생지 좌표 확보
→ 당시 지역 표준시 확인
→ 서머타임 적용 여부 확인
→ UTC 기준 시각 변환
→ 경도 보정
→ 균시차 적용
→ 진태양시 산출
→ 날짜 경계/자시 규칙 적용
→ 최종 사주 계산 시각 확정
```

### 4.2 TimeCorrectionResult

```python
class TimeCorrectionResult(BaseModel):
    input_datetime_local: datetime
    calendar_type: Literal["solar", "lunar"]
    lunar_converted_solar_date: date | None = None
    is_leap_month: bool | None = None

    birth_place_name: str
    latitude: float
    longitude: float
    timezone: str
    timezone_offset_minutes: int
    daylight_saving_applied: bool

    longitude_correction_minutes: float
    equation_of_time_minutes: float
    true_solar_datetime: datetime
    final_chart_datetime: datetime

    standard_time_hour_pillar: str | None = None
    true_solar_time_hour_pillar: str | None = None
    hour_pillar_changed_by_true_solar_time: bool

    day_boundary_rule: str
    ja_hour_rule: str
    warnings: list[str]
```

### 4.3 UI 표시

```text
입력 시각: 1980-11-22 09:08
출생지: 서울, 대한민국
표준시: KST UTC+09:00
서머타임: 미적용
경도 보정: -xx분
균시차: +xx분
진태양시: 1980-11-22 08:xx
최종 계산 시각: 1980-11-22 08:xx
시주 변화: 있음/없음
```

시주가 바뀌면 경고를 표시한다.

```text
주의: 진태양시 적용으로 시주가 변경되었습니다.
일반시 기준: 기사시
진태양시 기준: 무진시
```

---

## 5. 절기 및 사주 팔자 계산

### 5.1 절입 기준

월주는 음력 월이 아니라 절기 기준으로 계산한다.

```python
class SolarTermBasis(BaseModel):
    previous_term_name: str
    previous_term_datetime: datetime
    next_term_name: str
    next_term_datetime: datetime
    month_branch: str
    month_pillar_confirmed: str
    birth_after_month_term: bool
```

UI 표시:

```text
월주 기준: 절기 기준
출생일은 입동 이후, 대설 이전 → 해월 적용
월주: 정해
```

### 5.2 PillarResult

```python
class Pillar(BaseModel):
    stem: str
    branch: str
    ganji: str
    stem_element: str
    branch_element: str
    stem_yinyang: str
    branch_yinyang: str
    stem_ten_god: str
    branch_main_ten_god: str
    twelve_unseong: str
    hidden_stems: list["HiddenStem"]
    naeum: str | None = None
    gongmang_hit: bool = False
    palace: str | None = None

class FourPillarsResult(BaseModel):
    year: Pillar
    month: Pillar
    day: Pillar
    hour: Pillar | None
```

---

## 6. v2 출력 화면 구조

v1의 모든 정보를 유지하되 다음 구조로 재배치한다.

### 6.1 1단: 핵심 요약

```text
기토 일간 · 해월 출생 · 신약 32.6점
재성 수 강함 · 목 부족
1차 용신 후보: 토
희신 후보: 화
검증 필요: 높음
```

### 6.2 2단: 입력·시간 보정

포함 항목:

- 양력/음력/윤달
- 출생지
- 위도/경도
- 표준시
- 서머타임
- 경도 보정
- 균시차
- 진태양시
- 시주 변화 여부
- 날짜 경계 기준
- 자시 기준

### 6.3 3단: 사주 원국

각 주 카드에 다음을 표시한다.

- 천간
- 지지
- 오행
- 음양
- 십성
- 12운성
- 지장간
- 궁성
- 공망 여부

### 6.4 4단: 세력 분석

묶어서 표시해야 하는 항목:

- 오행 분포
- 십성 분포
- 강한 기운
- 부족한 기운
- 통근
- 득령/득지/득세
- 신강/신약 9단계 점수

주의 문구:

```text
부족한 오행이 항상 용신은 아닙니다.
용신 판단은 일간 강약, 월령, 통근, 십성 구조, 대세운 검증을 함께 봅니다.
```

### 6.5 5단: 용신 후보

표시 항목:

- 특수격 검사 결과
- 신강/신약 모델
- 부일간/부일주형 모델
- 억부 모델
- 조후 모델
- 통관 모델
- 고립/건강 모델
- 후보 용신 2개
- 후보 기신 2개
- 검증 필요 여부

### 6.6 6단: 구조 작용

묶어서 표시해야 하는 항목:

- 합
- 충
- 형
- 파
- 해
- 공망
- 궁성
- 자리간 작용
- 용신 안정도
- 격국 안정도
- 병존
- 간여지동

### 6.7 7단: 격국

표시 항목:

- 월지 지장간
- 정기/중기/여기
- 투간 여부
- 주격
- 보조 구조
- 성격/패격/중성
- 격국 안정도

표현 주의:

- `보조격`이라는 표현보다 `보조 구조` 사용 권장.
- 예: `상관격`, `편인격`, `건록격`을 병렬 격으로 확정하지 말고 `상관 발현`, `편인 발현`, `비견/건록성 발현`으로 표시.

### 6.8 8단: 운 흐름

표시 항목:

- 대운표
- 현재 대운 상세
- 대운 교체기 여부
- 세운/월운 계산 가능 상태
- 대운과 원국의 합충형파해
- 대운과 용신/기신 후보 관계

### 6.9 9단: 부가 정보

접기 처리 권장:

- 신살 전체 목록
- 납음오행
- 전통 보조 정보

---

## 7. 오행/십성 분포

### 7.1 원칙

- 천간, 지지, 지장간을 모두 반영한다.
- 월지 보정과 위치 가중치를 적용한다.
- 오행 분포와 십성 분포는 `세력 분석 카드`로 묶는다.
- 강한 기운/부족한 기운은 용신/기신과 별도로 표시한다.

### 7.2 DistributionResult

```python
class DistributionResult(BaseModel):
    five_elements: dict[str, float]
    ten_gods: dict[str, float]
    strongest_element: str
    weakest_element: str
    strongest_ten_god: str
    missing_ten_gods: list[str]
    notes: list[str]
```

---

## 8. 통근, 득령, 득지, 득세

### 8.1 개념 분리

- `득령`: 월령이 일간을 지지하는가?
- `득지`: 일지 또는 주요 지지가 일간의 직접 기반인가?
- `득세`: 원국 전체에서 비겁/인성 등 내 편이 충분한가?
- `통근`: 지장간에 일간 또는 인성의 뿌리가 있는가?

v1의 혼동 포인트를 해결해야 한다.

```text
통근은 있으나 득지가 없을 수 있습니다.
통근은 지장간 어딘가의 뿌리이고,
득지는 일지 또는 핵심 지지가 일간을 직접 지지하는지 보는 기준입니다.
```

### 8.2 RootAnalysisResult

```python
class RootItem(BaseModel):
    pillar_position: Literal["year", "month", "day", "hour"]
    branch: str
    hidden_stem: str
    root_type: Literal["peer_root", "resource_root"]
    strength: Literal["weak", "medium", "strong"]
    score: float
    damaged_by_relations: bool = False
    damage_reason: str | None = None

class RootAnalysisResult(BaseModel):
    deukryeong: bool
    deukji: bool
    deukse: bool
    roots: list[RootItem]
    root_score: float
    explanation: list[str]
```

---

## 9. 신강/신약 9단계 알고리즘

### 9.1 9단계 구간

| 점수 | 단계 | 의미 | 용신 처리 |
|---:|---|---|---|
| 0~11 | 극신약 | 일간이 거의 버티지 못함 | 종격 우선 검사 |
| 12~22 | 태신약 | 매우 약함 | 부일간/종격 경계 |
| 23~34 | 신약 | 일간 보조 필요 | 인성·비겁 후보 |
| 35~44 | 중화신약 | 약간 약함 | 조후·통관·검증 중요 |
| 45~55 | 중화 | 강약 판단 보류 | 용신 단정 금지 |
| 56~65 | 중화신강 | 약간 강함 | 설기·조후·검증 중요 |
| 66~77 | 신강 | 일간 세력 강함 | 식상·재성·관성 후보 |
| 78~88 | 태신강 | 매우 강함 | 전왕/종왕 검사 |
| 89~100 | 극신강 | 일간 또는 동류 세력 과도 | 전왕/일행득기 우선 검사 |

### 9.2 계산 공식

```python
strength_score = (
    0.35 * season_score
  + 0.35 * root_score
  + 0.30 * side_balance_score
  + structure_modifier
)

strength_score = clamp(strength_score, 0, 100)
```

### 9.3 season_score

월령 기준 점수.

| 월령 상태 | 의미 | 점수 |
|---|---|---:|
| 왕 | 일간 오행이 계절을 얻음 | 90 |
| 상 | 일간을 생해주는 계절 | 75 |
| 휴 | 보통 또는 약화 시작 | 50 |
| 수 | 일간이 제어당하거나 힘이 약함 | 35 |
| 사 | 일간이 가장 약한 계절 | 20 |

토 일간은 별도 정책을 둔다.

```yaml
earth_month_policy:
  chen_xu_chou_wei: strong
  si_wu_month: supported_by_fire
  yin_mao_month: controlled_by_wood
  hai_zi_month: dampened_by_water
  shen_you_month: drained_to_metal
```

### 9.4 root_score

위치별 가중치:

| 위치 | 가중치 |
|---|---:|
| 월지 | 35 |
| 일지 | 30 |
| 시지 | 18 |
| 년지 | 12 |

지장간 가중치:

| 구분 | 가중치 |
|---|---:|
| 정기 | 1.00 |
| 중기 | 0.60 |
| 여기 | 0.35 |

계산 규칙:

```python
if hidden_stem.element == day_master_element:
    root += branch_position_weight * hidden_stem_weight * 1.00
elif hidden_stem.element_generates(day_master_element):
    root += branch_position_weight * hidden_stem_weight * 0.65
```

### 9.5 side_balance_score

```python
ally_power = peer_power * 1.00 + resource_power * 0.85

pressure_power = (
    output_power * 0.55
  + wealth_power * 0.75
  + officer_power * 1.00
)

side_balance_score = 100 * ally_power / max(ally_power + pressure_power, 1e-6)
```

십성 그룹 가중치:

| 그룹 | 영향 | 가중치 |
|---|---|---:|
| 비겁 | 일간 직접 강화 | 1.00 |
| 인성 | 일간 생조 | 0.85 |
| 식상 | 일간 기운 배출 | 0.55 |
| 재성 | 일간이 감당해야 하는 대상 | 0.75 |
| 관살 | 일간 직접 압박 | 1.00 |

### 9.6 합충형파해 보정

```yaml
relation_modifiers:
  branch_clash:
    weak_root_loss: -0.40
    both_active_loss: -0.20
  six_combination_no_transform:
    actionability_loss: -0.15
  six_combination_transform:
    original_element_loss: -0.50
    transformed_element_gain: +0.35
  three_harmony_complete:
    target_element_gain: +0.35
  three_harmony_half:
    target_element_gain: +0.18
  directional_combo:
    target_element_gain: +0.30
  punishment:
    stability_loss: -0.10
  harm:
    stability_loss: -0.08
  break:
    stability_loss: -0.08
```

### 9.7 분류 함수

```python
def classify_strength(score: float) -> str:
    if score <= 11:
        return "극신약"
    elif score <= 22:
        return "태신약"
    elif score <= 34:
        return "신약"
    elif score <= 44:
        return "중화신약"
    elif score <= 55:
        return "중화"
    elif score <= 65:
        return "중화신강"
    elif score <= 77:
        return "신강"
    elif score <= 88:
        return "태신강"
    else:
        return "극신강"
```

경계값 처리:

```python
def is_borderline(score: float) -> bool:
    boundaries = [11, 22, 34, 44, 55, 65, 77, 88]
    return any(abs(score - b) <= 2 for b in boundaries)
```

### 9.8 StrengthResult

```python
class StrengthResult(BaseModel):
    score: float
    band: Literal[
        "극신약", "태신약", "신약", "중화신약", "중화",
        "중화신강", "신강", "태신강", "극신강"
    ]
    borderline: bool
    confidence: float
    requires_validation: bool
    components: dict
    explanation: list[str]
```

검증 필요 조건:

```python
def should_validate_strength(score: float, confidence: float) -> bool:
    if 35 <= score <= 65:
        return True
    if confidence < 0.70:
        return True
    if is_borderline(score):
        return True
    return False
```

---

## 10. 특수 용신 케이스

### 10.1 예외 판정 순서

```text
1. 계산 불가/시간 경계 민감 케이스
2. 합화/화기격 후보
3. 전왕/일행득기 후보
4. 종격 후보
5. 통관 우선 케이스
6. 고립/병약/건강 우선 케이스
7. 조후 우선 케이스
8. 부일간/부일주형
9. 일반 억부 케이스
10. 격국 참고 케이스
```

### 10.2 부일간/부일주형

정의: 신약한 일간을 인성/비겁으로 보조하는 모델.

```yaml
case_type: support_day_master
trigger:
  - day_master_strength_score <= 40
  - 일간이 월령을 얻지 못함
  - 일지/월지 통근 약함
  - 관살/재성/식상이 일간을 심하게 소모하거나 압박
  - 종격 조건은 충족하지 않음
yongsin_rule:
  yongsin: 인성 또는 비겁
  heesin: 인성/비겁 중 보조 관계
  gisin: 관살, 재성, 식상 중 일간을 가장 크게 압박하는 오행
```

### 10.3 극신약이나 종격이 아닌 케이스

```yaml
case_type: weak_but_not_follow
trigger:
  - day_master_strength_score <= 25
  - 일간 뿌리 또는 생조가 아주 약하게라도 존재
  - 종격을 방해하는 비겁/인성/근이 있음
  - 충·합으로 종격 흐름이 깨짐
yongsin_rule:
  primary: 인성
  secondary: 비겁
```

### 10.4 종격 후보

```yaml
case_type: follow_structure
subtypes:
  - 종재격
  - 종관살격
  - 종아격
  - 종세격
  - 종왕격
trigger:
  - 일간이 극도로 약함
  - 일간을 돕는 인성/비겁이 거의 없음
  - 월령과 지지 흐름이 특정 십성/오행으로 쏠림
  - 천간도 그 흐름을 방해하지 않음
  - 반대 오행이 있어도 뿌리 없거나 합거/충거됨
yongsin_rule:
  yongsin: 따르는 세력
  gisin: 일간을 억지로 살리는 인성/비겁
validation_required: true
```

### 10.5 전왕/일행득기형

```yaml
case_type: dominant_one_element
trigger:
  - 특정 오행이 65~75% 이상 집중
  - 월령이 해당 오행 또는 생조 오행
  - 지지 삼합/방합/반합이 한 오행으로 흐름
  - 반대 오행이 뿌리 없이 약함
  - 명식 전체가 한 방향으로 흐름
yongsin_rule:
  yongsin: 왕한 기운 또는 그 기운을 순행시키는 오행
  gisin: 왕한 흐름을 정면으로 극하는 오행
```

### 10.6 합화/화기격 후보

```yaml
case_type: transformation_structure
trigger:
  - 천간합 존재
  - 월령이 합화 오행을 지지
  - 지지에 합화 오행의 뿌리 존재
  - 합을 방해하는 극/충이 약함
  - 원국 전체 흐름이 합화 오행으로 기울어짐
yongsin_rule:
  yongsin: 합화된 오행 또는 그 오행을 돕는 오행
  gisin: 합화를 깨는 오행
confidence_policy:
  - 합화 조건이 불완전하면 일반 합반/합거로만 처리
```

### 10.7 통관용신

```yaml
case_type: bridge_element_required
trigger:
  - 두 오행이 강하게 충돌
  - 극하는 쪽이 강함
  - 극당하는 쪽이 완전히 사라지지는 않음
  - 중간에서 생을 이어주는 오행이 필요
yongsin_rule:
  wood_vs_earth: fire
  earth_vs_water: metal
  water_vs_fire: wood
  fire_vs_metal: earth
  metal_vs_wood: water
```

### 10.8 고립/병약/건강용신

최종 용신과 분리해서 리스크 레이어로 관리한다.

```yaml
case_type: isolated_or_sick_element
trigger:
  - 특정 오행이 1개 이하
  - 주변에서 극을 심하게 당함
  - 생조가 없음
  - 뿌리 없음
  - 충/형/파/해로 해당 오행이 손상
  - 해당 오행이 십성상 중요한 역할을 담당
yongsin_rule:
  health_support_element: 고립 오행을 살리는 오행
  not_always_final_yongsin: true
```

### 10.9 조후 우선형

```yaml
case_type: climate_balance_required
trigger:
  - 신강/신약 점수가 41~60으로 애매함
  - 특정 계절성이 강함
  - 한난조습 불균형이 심함
  - 억부 후보 간 점수 차이가 작음
policy:
  - 조후 단독 확정 금지
  - 억부 후보와 충돌하면 검증 질문으로 넘김
```

---

## 11. 용신 후보 산출

### 11.1 모델별 병렬 평가

다음 모델을 각각 실행한다.

```text
1. eokbu_model
2. support_day_master_model
3. johu_model
4. isolation_health_model
5. tonggwan_model
6. follow_structure_model
7. dominant_structure_model
8. transformation_model
9. geokguk_model
```

### 11.2 YongsinCandidateModel

```python
class YongsinCandidateModel(BaseModel):
    model_type: str
    label: str
    yongsin: str | None
    heesin: str | None = None
    gisin: str | None = None
    gusin: str | None = None
    hansin: str | None = None
    confidence: float
    reasons: list[str]
    requires_validation: bool = True
```

### 11.3 AggregatedYongsinResult

```python
class AggregatedYongsinResult(BaseModel):
    status: Literal["candidate", "calibrating", "calibrated", "probable", "uncertain"]
    useful_candidates: list[ElementCandidate]
    unfavorable_candidates: list[ElementCandidate]
    candidate_models: list[YongsinCandidateModel]
    selected_model: YongsinCandidateModel | None = None
    validation_required: bool
    warnings: list[str]
```

### 11.4 UI 표현 예시

```text
1차 용신 후보: 토
판정 모델: 부일간형
이유: 신약한 기토가 재성 수에 눌리는 구조라 비겁 토로 일간을 직접 보강하는 모델

희신 후보: 화
이유: 화는 토를 생조하여 용신 토를 돕는 역할

기신 후보: 목
이유: 목 관성은 약한 토 일간을 제어하는 압박으로 작동 가능

구신 후보: 수
이유: 이미 강한 재성 수가 더 강해지면 일간 부담 증가
```

---

## 12. 격국 분석

### 12.1 주의 원칙

- 격국은 참고 레이어로 둔다.
- 용신 확정에서 격국용신은 낮은 가중치로 사용한다.
- `보조격` 표현 대신 `보조 구조`를 사용한다.

### 12.2 GeokgukResult

```python
class GeokgukResult(BaseModel):
    main_structure: str | None
    basis_month_branch: str
    month_hidden_stems: list[HiddenStem]
    main_qi_ten_god: str
    exposed_stem_exists: bool
    formation_level: Literal["성", "중성", "패", "불명확"]
    stability: Literal["안정", "불안정", "보통"]
    auxiliary_structures: list[str]
    explanation: list[str]
```

---

## 13. 구조 작용 분석

### 13.1 묶어야 할 항목

- 합충형파해
- 공망
- 궁성
- 자리간 작용
- 용신 안정도
- 격국 안정도
- 병존
- 간여지동

### 13.2 StructuralInteraction

```python
class StructuralInteraction(BaseModel):
    relation_type: Literal["합", "충", "형", "파", "해", "자형", "방합", "삼합", "반합"]
    pair: tuple[str, str]
    positions: tuple[str, str]
    palaces: tuple[str, str]
    affected_elements: list[str]
    affected_ten_gods: list[str]
    severity: Literal["low", "medium", "high"]
    yongsin_stability_effect: Literal["increase", "decrease", "neutral"]
    geokguk_stability_effect: Literal["increase", "decrease", "neutral"]
    event_domains: list[str]
    explanation: str
```

### 13.3 공망

```python
class GongmangResult(BaseModel):
    year_pillar_basis_empty_branches: list[str]
    day_pillar_basis_empty_branches: list[str]
    affected_positions: list[str]
    affected_palaces: list[str]
    activation_conditions: list[str]
    explanation: str
```

공망 설명 정책:

```text
원국 공망은 배경값입니다.
대운·세운·월운에서 해당 지지가 자극되거나 합충형파해로 활성화될 때 사건화 가능성이 커집니다.
```

### 13.4 병존/간여지동

```python
class AmplifierResult(BaseModel):
    type: Literal["병존", "간여지동"]
    target: str
    positions: list[str]
    element: str
    strength: Literal["weak", "medium", "strong"]
    amplified_domains: list[str]
    effect_on_strength_score: float
    effect_on_yongsin_model: str | None
```

---

## 14. 대운/세운/월운

### 14.1 DaewoonItem

```python
class DaewoonItem(BaseModel):
    age: int
    start_date: date
    end_date: date
    ganji: str
    stem_ten_god: str
    branch_main_ten_god: str
    twelve_unseong: str
    naeum: str | None = None
    relation_to_chart: list[StructuralInteraction]
    relation_to_yongsin_candidates: dict[str, str]
    volatility_score: float
    event_domains: list[str]
```

### 14.2 현재 대운 상세

```python
class CurrentDaewoonDetail(BaseModel):
    ganji: str
    start_date: date
    end_date: date
    age_range: str
    transition_status: Literal["before", "entering", "active", "leaving"]
    transition_window_start: date | None
    transition_window_end: date | None
    core_ten_gods: list[str]
    relation_to_yongsin: list[str]
    relation_to_gisin: list[str]
    palace_activation: list[str]
    gongmang_activation: list[str]
    explanation: list[str]
```

### 14.3 대운표 UI 추가 컬럼

기존:

```text
나이 | 교운 | 간지 | 십성 | 운성 | 납음
```

v2:

```text
나이 | 교운 | 간지 | 십성 | 운성 | 용신관계 | 원국작용 | 변동성
```

---

## 15. 사용자 검증 루프

### 15.1 목적

용신 후보가 실제 삶의 흐름과 맞는지 검증한다.

### 15.2 질문 구성

5개 질문을 다음 유형으로 구성한다.

```yaml
calibration_question_set:
  question_count: 5
  composition:
    - useful_candidate_year_check
    - unfavorable_candidate_year_check
    - contrast_year_check
    - high_event_domain_check
    - month_or_period_detail_check
```

### 15.3 CalibrationQuestion

```python
class CalibrationQuestion(BaseModel):
    question_id: str
    period_type: Literal["year", "month", "range"]
    year: int | None
    month: int | None = None
    period_label: str
    target_models: list[str]
    activated_elements: list[str]
    activated_ten_gods: list[str]
    expected_effect_by_model: dict[str, Literal["positive", "negative", "mixed", "volatile"]]
    ask_domains: list[str]
    question_text: str
    options: list[str]
```

### 15.4 질문 템플릿

```text
{year}년 전후에는 전반적으로 일이 잘 풀리는 느낌이 강했나요,
아니면 막히는 느낌이 강했나요?

해당되는 사건을 골라주세요.
- 취업/이직/승진
- 입학/졸업/자격증
- 연애 시작/종료
- 이사
- 큰 수입/지출
- 가족/건강 문제
- 특별한 일 없음
- 기억나지 않음
```

### 15.5 응답 스케일

```yaml
feedback_scale:
  very_positive: 2
  positive: 1
  neutral: 0
  negative: -1
  very_negative: -2
  unknown: null
```

### 15.6 FeedbackResult

```python
class FeedbackResult(BaseModel):
    question_id: str
    user_overall_rating: Literal[
        "very_positive", "positive", "neutral", "negative", "very_negative", "unknown"
    ]
    selected_events: list[str]
    free_text: str | None = None
    domain_ratings: dict[str, int | None] = {}
```

### 15.7 점수화

```python
class ValidationScore(BaseModel):
    model_type: str
    expected_effect: str
    user_score: int | None
    match_score: float
    reason: str
```

예측과 실제가 맞으면 가산, 반대면 감산.

```python
def score_feedback(expected: str, user_score: int | None) -> float:
    if user_score is None:
        return 0.0
    if expected == "positive":
        return user_score
    if expected == "negative":
        return -user_score
    if expected == "mixed":
        return 0.5 * abs(user_score)
    if expected == "volatile":
        return 0.3 * abs(user_score)
    return 0.0
```

### 15.8 최종 결정 정책

```yaml
decision_policy:
  match_rate_above_0_75: calibrated
  match_rate_0_55_to_0_75: probable
  match_rate_below_0_55: uncertain
```

```python
class FinalYongsinDecision(BaseModel):
    status: Literal["calibrated", "probable", "uncertain"]
    yongsin: str | None
    heesin: str | None
    gisin: str | None
    gusin: str | None
    hansin: str | None
    selected_model_type: str | None
    confidence: float
    evidence_count: int
    match_rate: float
    model_scores: dict[str, float]
    explanation: list[str]
```

---

## 16. API 설계

### 16.1 POST `/api/v2/manse/calculate`

입력:

```json
{
  "calendar_type": "solar",
  "is_leap_month": null,
  "birth_date": "1980-11-22",
  "birth_time": "09:08",
  "birth_place_name": "서울",
  "latitude": 37.5665,
  "longitude": 126.978,
  "gender": "male",
  "time_options": {
    "apply_true_solar_time": true,
    "day_boundary_rule": "23:00",
    "ja_hour_rule": "standard_zi"
  }
}
```

출력:

```json
{
  "chart_id": "...",
  "input_summary": {},
  "time_correction": {},
  "solar_term_basis": {},
  "pillars": {},
  "force_analysis": {},
  "structure_analysis": {},
  "geokguk_analysis": {},
  "yongsin_analysis": {},
  "luck_cycles": {},
  "traditional_extras": {}
}
```

### 16.2 POST `/api/v2/manse/{chart_id}/calibration/questions`

용신 후보를 기반으로 검증 질문 5개를 생성한다.

### 16.3 POST `/api/v2/manse/{chart_id}/calibration/submit`

사용자 응답을 받아 모델 점수를 갱신한다.

### 16.4 GET `/api/v2/manse/{chart_id}/final`

검증 후 최종 용신/희신/기신/구신 포함 결과를 반환한다.

---

## 17. v1 항목 매핑

| v1 항목 | v2 처리 |
|---|---|
| 양력/음력/경도/KST | 시간 보정 카드로 확장 |
| 만 나이/성별/순행대운 | 입력 요약 카드에 유지 |
| 사주 팔자 | 유지, 궁성·공망 여부 추가 |
| 지장간 | 암장 십성·격국 근거와 묶기 |
| 오행 분포 | 십성 분포·세력 분석과 묶기 |
| 강한/부족한 기운 | 유지하되 용신과 별개임을 표시 |
| 십성 분포 | 오행 분포와 묶기 |
| 없는 십성 | 암장 십성과 함께 표시 |
| 통근 | 신강/신약 근거로 이동 |
| 암장 십성 | 지장간 카드로 이동 |
| 월지 격국 근거 | 격국 카드로 이동 |
| 신강약·용신·격국 | 세 개의 독립 카드로 분리 |
| 납음오행 | 부가 정보로 하향 |
| 합충형파해 | 구조 작용 카드로 이동 |
| 공망 | 구조 작용 + 활성 조건과 묶기 |
| 궁성 | 합충형파해와 묶기 |
| 자리간 작용 | 구조 작용 카드의 핵심으로 유지 |
| 용신 안정도 | 용신 후보 카드와 구조 작용 카드에 연결 |
| 격국 안정도 | 격국 카드로 이동 |
| 신살 | 핵심 3개 요약 + 전체 보기 |
| 병존·간여지동 | 구조 증폭 카드로 이동 |
| 대운 | 현재 대운 상세 + 용신 관계 추가 |

---

## 18. 테스트 케이스

### 18.1 v1 기준 샘플

입력:

```yaml
solar_datetime: 1980-11-22 09:08
birth_place: 서울
longitude: 126.978
timezone: KST
gender: male
```

v1 출력 주요값:

```yaml
pillars:
  year: 경신
  month: 정해
  day: 기해
  hour: 기사

day_master: 기토
strength_v1: 신약
yongsin_v1: 토
heesin_v1: 화
gisin_v1: 목
gusin_v1: 수
geokguk_v1: 정재격
current_daewoon_v1: 임진
```

v2에서 반드시 확인할 것:

```yaml
checks:
  - 진태양시 적용 후 시주 변화 여부를 별도 표시한다.
  - 신약을 단순 문자열이 아니라 0~100 점수와 9단계로 표시한다.
  - 통근 있음과 득지 없음의 차이를 설명한다.
  - 목 부족과 목 기신 후보의 차이를 설명한다.
  - 용신 토는 확정값이 아니라 부일간형 후보 모델로 표시한다.
  - 검증 질문 5개를 생성할 수 있어야 한다.
```

### 18.2 신강/신약 경계 테스트

- score 44.5 → 중화 또는 중화신약 경계 처리
- score 55.5 → 중화 또는 중화신강 경계 처리
- confidence < 0.70이면 검증 필요 true

### 18.3 특수격 테스트

- 극신약 점수이지만 종격 조건 만족 → 부일간이 아니라 종격 후보 반환
- 극신강 점수이지만 전왕 조건 만족 → 극제용신이 아니라 순행 후보 반환
- 합화 조건 불완전 → 화기격 확정 금지, 합반/합거로 처리

---

## 19. 개발 우선순위

### Phase 1: 만세력 계산 안정화

- 입력 정규화
- 음력/윤달 변환
- 시간 보정
- 진태양시
- 절기 기준 월주
- 사주 팔자
- 지장간/십성/12운성/공망
- 대운 산출

### Phase 2: 세력 분석

- 오행 분포
- 십성 분포
- 통근
- 득령/득지/득세
- 신강/신약 9단계 점수
- 합충형파해 보정

### Phase 3: 용신 후보 엔진

- 특수격 검사
- 부일간/억부 모델
- 조후 모델
- 통관 모델
- 고립/건강 모델
- 후보 통합

### Phase 4: 검증 루프

- 후보별 검증 연도/년월 추출
- 질문 생성
- 피드백 수집
- 모델별 점수 업데이트
- 최종 용신 결정

### Phase 5: UI 재구성

- v2 화면 구조 적용
- 카드별 접기/펼치기
- 핵심 요약 우선
- 신살/납음 하향 배치

---

## 20. Codex 작업 지시

다음 순서로 작업한다.

1. 현재 코드베이스에서 만세력 계산 관련 모듈을 찾는다.
2. 기존 계산 로직을 직접 수정하기 전에 `manse_v2` 또는 feature flag 기반 v2 경로를 만든다.
3. `BirthInput`, `TimeCorrectionResult`, `FourPillarsResult`, `StrengthResult`, `AggregatedYongsinResult` 스키마를 먼저 구현한다.
4. v1 출력값을 유지하면서 v2 추가 필드를 병렬 반환한다.
5. 신강/신약 9단계 점수 계산을 pure function으로 구현하고 단위 테스트를 작성한다.
6. 특수격 검사기는 확정이 어려우면 반드시 `confidence`와 `requires_validation`을 반환한다.
7. 용신은 최초에는 `candidate` 상태로 반환한다.
8. 검증 질문 API를 구현한다.
9. 피드백 제출 API를 구현한다.
10. 최종 결과 API에서 `calibrated/probable/uncertain` 상태를 반환한다.

---

## 21. 완료 기준

### 21.1 기능 완료 기준

- 같은 입력은 항상 같은 원국/대운 결과를 반환한다.
- 시간 보정 결과가 JSON에 남는다.
- 진태양시 적용 전후 시주 변화 여부를 알 수 있다.
- 절기 기준 월주 근거를 확인할 수 있다.
- 신강/신약이 9단계 점수로 반환된다.
- 용신 후보가 모델별로 반환된다.
- 특수격 후보가 별도 반환된다.
- 검증 질문 5개를 생성할 수 있다.
- 사용자 피드백으로 후보 모델 점수가 업데이트된다.

### 21.2 UX 완료 기준

- 사용자는 부족한 오행과 용신의 차이를 이해할 수 있다.
- 사용자는 통근과 득지의 차이를 이해할 수 있다.
- 사용자는 용신이 왜 후보 상태인지 이해할 수 있다.
- 사용자는 어떤 과거 사건을 답해야 하는지 명확히 알 수 있다.
- 신살과 납음은 핵심 판단을 방해하지 않도록 하위에 표시된다.

---

## 22. 금지 사항

- LLM이 직접 사주 팔자를 재계산하지 않는다.
- LLM이 엔진 결과와 다른 용신을 임의로 확정하지 않는다.
- 부족한 오행을 자동으로 용신 처리하지 않는다.
- 신강/신약을 단순 boolean으로 저장하지 않는다.
- 중화권 명식에서 용신을 확정값으로 표시하지 않는다.
- 종격/전왕 가능성을 검사하지 않고 극신약/극신강을 일반 억부로 처리하지 않는다.
- 신살을 용신 결정의 핵심 근거로 사용하지 않는다.
- 보조 구조를 모두 `격`으로 확정 표현하지 않는다.

---

## 23. 최종 목표

v2 만세력 엔진은 단순 표시용 만세력이 아니라, 다음을 만족해야 한다.

```text
정확한 시간 보정
→ 근거 있는 원국 계산
→ 점수형 신강/신약 판정
→ 특수격 예외 처리
→ 용신 후보 모델 생성
→ 과거 사건 기반 검증
→ 신뢰도 있는 최종 용신 확정
```

이 구조가 완성되면 이후 LLM 사주 서비스는 계산 오류와 용신 단정 오류를 줄이고, 사용자 실제 경험을 반영한 풀이로 확장할 수 있다.

---

# v2.1 보완 — UI·신살·중화사주 추가 지시

## 1. 신규 패키지/모듈 추가

```text
packages/manse-analysis/
  sinsal/
    sinsal_catalog.py
    twelve_sinsal.py
    noble_stars.py
    academic_stars.py
    movement_stars.py
    relationship_stars.py
    health_risk_stars.py
    wealth_status_stars.py
    sinsal_aggregator.py
    sinsal_intensity.py
apps/web/
  components/manse/
    MansePage.tsx
    BirthSummaryBar.tsx
    TrueSolarTimeInfoCard.tsx
    PillarBoard.tsx
    PillarColumn.tsx
    GanjiTile.tsx
    StructureSummaryPanel.tsx
    SinsalPanel.tsx
```

## 2. 구현 정책 추가

```text
- 전체 신살을 계산/반환/표시한다.
- 중화사주에서는 신왕과 신강을 분리한다.
- 시간 모름 UI를 지원한다.
- 진태양시 적용 전후 시주 변경을 UI에 표시한다.
```
