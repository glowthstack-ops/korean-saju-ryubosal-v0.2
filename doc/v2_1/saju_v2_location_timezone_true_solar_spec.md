# 사주서비스 v2 — 지역·타임존·서머타임·진태양시 보정 명세서

> 목적: 해외 출생까지 커버 가능한 안정적 만세력 엔진을 만들기 위한 지역/시간 보정 독립 명세서이다.  
> 원칙: LLM에 의존하지 않고, 입력 시각을 계산용 최종 시각으로 변환하는 모든 과정을 추적 가능하게 만든다.  
> 적용 범위: 출생지 좌표, IANA timezone, 역사적 UTC offset, DST, 경도 보정, 균시차, 진태양시, 시주 변경 여부, 야자시/조자시/일자 경계.

---

## 1. 핵심 원칙

```text
사용자 입력 시각은 곧바로 사주 계산 시각이 아니다.

입력 시각
→ 출생지와 날짜 기준 법정시 확인
→ 역사적 UTC offset/DST 확인
→ UTC 변환
→ 출생지 경도 기반 평균태양시 보정
→ 균시차 적용
→ 진태양시 산출
→ 일자 경계/자시 규칙 적용
→ 최종 사주 계산 시각 확정
```

v2 엔진은 모든 단계의 중간값을 반환해야 한다.

---

## 2. 해외 출생 지원 정책

해외 출생을 지원하려면 단순히 국가명만 받으면 안 된다.

필수 입력:

```yaml
birth_place:
  country_code: KR | US | JP | ...
  city_name:
  latitude:
  longitude:
  iana_timezone:
  source:
    type: user_selected | geocoded | manual
    confidence:
```

권장 UX:

```text
1. 사용자가 도시명 입력
2. 후보 도시 목록 표시
3. 도시 선택 시 위도/경도/IANA timezone 자동 설정
4. 사용자가 직접 좌표 수정 가능
5. timezone이 불확실하면 경고 표시
```

---

## 3. IANA timezone 사용

### 3.1 왜 IANA timezone이 필요한가

국가/도시는 시간대 규칙이 역사적으로 바뀐다.

예:

```text
- UTC offset 변경
- 서머타임 도입/폐지
- 전쟁/점령기 임시 시간
- 행정구역 시간대 변경
```

따라서 `Asia/Seoul`, `America/New_York`, `Europe/London` 같은 IANA timezone ID를 기준으로 계산한다.

### 3.2 구현 권장

Python 기준:

```python
from zoneinfo import ZoneInfo

local_dt = datetime(1980, 11, 22, 9, 8, tzinfo=ZoneInfo("Asia/Seoul"))
utc_dt = local_dt.astimezone(timezone.utc)
```

`zoneinfo`는 시스템 tzdata 또는 PyPI `tzdata`를 사용할 수 있다.

### 3.3 데이터 버전 고정

계산 결과 재현성을 위해 tzdata 버전을 기록한다.

```yaml
timezone_resolution:
  iana_timezone: Asia/Seoul
  tzdata_version: "2026b"
  utc_offset_minutes: 540
  dst_applied: false
  abbreviation: KST
```

주의:

```text
같은 생년월일시라도 tzdata 버전 업데이트에 따라 일부 지역의 역사적 offset이 달라질 수 있다.
계산 결과에는 tzdata_version을 저장한다.
```

---

## 4. Local datetime 모호성 처리

DST 전환 시각에는 두 문제가 생긴다.

```text
1. nonexistent local time
   - 서머타임 시작으로 존재하지 않는 시각

2. ambiguous local time
   - 서머타임 종료로 같은 현지시각이 두 번 존재
```

출생시각이 여기에 걸리면 자동 확정하지 말고 사용자 확인 또는 fallback 정책을 사용한다.

```yaml
local_time_validation:
  status: valid | ambiguous | nonexistent
  resolution_policy:
    ambiguous: ask_user | prefer_earlier | prefer_later
    nonexistent: ask_user | shift_forward
```

MVP 권장:

```text
ambiguous/nonexistent면 경고를 표시하고 사용자가 선택하게 한다.
```

---

## 5. 음력/윤달 처리 위치

윤달은 시간 보정이 아니라 날짜 변환 단계다.

```text
음력 날짜 + 윤달 여부
→ 양력 날짜 변환
→ local datetime 생성
→ timezone/DST 처리
→ 진태양시 처리
```

금지:

```text
윤달을 진태양시나 타임존 보정 단계에서 처리하지 말 것.
```

---

## 6. 경도 보정

### 6.1 기본 개념

표준시는 시간대의 기준 경도에 맞춰져 있다.  
출생지 실제 경도와 표준시 기준 경도가 다르면 평균태양시가 달라진다.

```text
1도 = 4분
경도 차이 1도마다 태양시는 약 4분 차이
```

### 6.2 계산식

```python
standard_meridian = timezone_offset_hours * 15
longitude_correction_minutes = 4 * (birth_longitude - standard_meridian)
```

예:

```text
KST = UTC+9 → 기준 경도 135E
서울 경도 약 126.978E
경도 차이 = 126.978 - 135 = -8.022도
경도 보정 = -32.088분
```

주의:

```text
DST가 적용된 시각에서는 timezone_offset_hours에 DST 포함 offset을 그대로 쓰면 안 된다.
법정시에서 표준시로 먼저 되돌린 뒤 평균태양시/진태양시를 계산하는 정책을 명확히 해야 한다.
```

권장 정책:

```text
1. 현지 법정시에서 UTC offset/DST 식별
2. DST 적용 시 법정시에서 DST 1시간 제거하여 local standard time 산출
3. local standard time 기준으로 경도 보정
```

---

## 7. 균시차 Equation of Time

### 7.1 역할

균시차는 평균태양시와 진태양시의 차이를 보정한다.

```text
진태양시 = 평균태양시 + 균시차
```

### 7.2 MVP 근사식

NOAA 계열 근사식을 사용할 수 있다.

```python
gamma = 2 * pi / 365 * (day_of_year - 1 + (hour - 12) / 24)

eqtime = 229.18 * (
    0.000075
    + 0.001868 * cos(gamma)
    - 0.032077 * sin(gamma)
    - 0.014615 * cos(2 * gamma)
    - 0.040849 * sin(2 * gamma)
)
```

단위: minutes

### 7.3 고정밀 옵션

추후 고도화 시 천문 알고리즘 기반 ephemeris를 사용할 수 있다.

```yaml
equation_of_time_method:
  default: noaa_approximation
  alternatives:
    - astronomical_algorithms
    - ephemeris_table
```

---

## 8. 진태양시 산출

### 8.1 계산 흐름

```python
local_standard_time = local_legal_time - dst_offset

mean_solar_time = local_standard_time + longitude_correction_minutes

true_solar_time = mean_solar_time + equation_of_time_minutes
```

또는 NOAA식 offset:

```python
time_offset = equation_of_time + 4 * longitude - 60 * timezone
true_solar_time_minutes = local_clock_minutes + time_offset
```

단, `timezone`은 표준시 offset 기준으로 사용한다.

### 8.2 출력

```yaml
true_solar_time_result:
  input_local_legal_time:
  local_standard_time:
  utc_datetime:
  timezone_offset_minutes:
  dst_offset_minutes:
  standard_meridian:
  longitude:
  longitude_correction_minutes:
  equation_of_time_minutes:
  true_solar_time:
  date_changed_by_true_solar_time:
  hour_branch_before:
  hour_branch_after:
  hour_pillar_changed:
```

---

## 9. 시주 변경 감지

진태양시 적용 전후로 시주가 바뀌는지 반드시 확인한다.

```yaml
hour_pillar_comparison:
  civil_time:
    time:
    hour_branch:
    hour_pillar:
  true_solar_time:
    time:
    hour_branch:
    hour_pillar:
  changed: true | false
```

사용자 표시:

```text
입력 시각: 09:08
진태양시: 08:50
시주 변화: 있음 / 없음
```

시주 변경 시:

```text
주의: 진태양시 적용으로 시주가 변경되었습니다.
일반시 기준: 기사시
진태양시 기준: 무진시
```

---

## 10. 일자 경계 규칙

사주 계산에서 자시를 어떻게 처리할지 옵션화한다.

```yaml
day_boundary_rule:
  midnight_00:
    description: 00:00 기준 날짜 변경

  late_zi_23:
    description: 23:00 기준 날짜 변경

  split_zi:
    description: 야자시/조자시 분리
```

MVP 기본값:

```yaml
default_day_boundary_rule: late_zi_23
```

하지만 사용자 또는 서비스 설정에서 변경 가능해야 한다.

---

## 11. 지역 데이터베이스

### 11.1 location-db 요구사항

```yaml
location:
  id:
  name_ko:
  name_en:
  country_code:
  admin1:
  latitude:
  longitude:
  iana_timezone:
  aliases:
  valid_from:
  valid_to:
  confidence:
```

### 11.2 도시 후보 선택

도시명이 중복될 수 있다.

예:

```text
Springfield
London
Seoul / 서울
Paris
```

검색 결과에는 국가/주/위도경도/timezone을 함께 표시한다.

---

## 12. 사용자 수동 입력

해외 출생지 또는 과거 지명이 DB에 없을 수 있으므로 수동 모드를 제공한다.

```yaml
manual_location_input:
  latitude:
  longitude:
  iana_timezone:
  note:
```

검증:

```text
- 위도 범위: -90~90
- 경도 범위: -180~180
- IANA timezone 유효성
```

---

## 13. 오류/경고 정책

```yaml
warnings:
  timezone_uncertain:
  dst_ambiguous:
  local_time_nonexistent:
  true_solar_time_changes_hour:
  true_solar_time_changes_date:
  location_low_confidence:
  lunar_conversion_uncertain:
```

계산 불가가 아니라 경고 후 후보를 보여줄 수 있는 경우:

```text
- 도시 후보가 여러 개인 경우
- 진태양시 적용 여부에 따라 시주가 바뀌는 경우
- 야자시 기준에 따라 일주가 바뀌는 경우
```

계산 보류해야 하는 경우:

```text
- timezone을 결정할 수 없음
- DST ambiguous time을 사용자가 선택하지 않음
- 음력 윤달 여부가 필요한데 누락됨
```

---

## 14. API 출력 예시

```json
{
  "location_time_correction": {
    "input": {
      "calendar_type": "solar",
      "date": "1980-11-22",
      "time": "09:08",
      "location": {
        "city": "Seoul",
        "country_code": "KR",
        "latitude": 37.5665,
        "longitude": 126.978,
        "iana_timezone": "Asia/Seoul"
      }
    },
    "timezone_resolution": {
      "iana_timezone": "Asia/Seoul",
      "tzdata_version": "2026b",
      "utc_offset_minutes": 540,
      "dst_applied": false,
      "dst_offset_minutes": 0,
      "local_time_status": "valid"
    },
    "solar_time": {
      "standard_meridian": 135.0,
      "longitude_correction_minutes": -32.088,
      "equation_of_time_minutes": 14.2,
      "true_solar_time": "1980-11-22T08:50:00"
    },
    "comparison": {
      "civil_hour_branch": "巳",
      "true_solar_hour_branch": "辰",
      "hour_branch_changed": true
    },
    "warnings": []
  }
}
```

---

## 15. 테스트 케이스

필수 테스트:

```text
1. 한국 서울 KST DST 없음
2. 미국 뉴욕 DST 적용일
3. 미국 뉴욕 DST 종료 ambiguous time
4. 영국 런던 BST/GMT 전환
5. 일본 도쿄 JST
6. 중국 베이징 CST
7. 인도 IST UTC+5:30
8. 호주 시드니 DST
9. 수동 좌표 입력
10. 진태양시 적용으로 시주 변경
11. 진태양시 적용으로 날짜 변경
12. 23시 전후 야자시/조자시
```

---

## 16. 구현 금지 사항

```text
1. 국가명만으로 timezone을 결정하지 말 것.
2. 현재 UTC offset을 과거 출생일에 그대로 적용하지 말 것.
3. DST를 무시하지 말 것.
4. IANA timezone 없이 해외 출생을 계산 완료 처리하지 말 것.
5. 진태양시 계산에서 경도 보정과 균시차를 섞어 숨기지 말 것.
6. 시주 변경 여부를 표시하지 않는 구현을 하지 말 것.
7. 야자시/조자시 기준을 하드코딩하지 말 것.
8. tzdata 버전을 기록하지 않는 구현을 하지 말 것.
```

---

## 17. Codex 작업 단위

```text
1. Location schema 작성
2. IANA timezone validator 구현
3. timezone resolver 구현
4. local time ambiguity detector 구현
5. DST resolver 구현
6. longitude correction 구현
7. equation of time 구현
8. true solar time calculator 구현
9. hour pillar comparison DTO 구현
10. warnings 정책 구현
11. location fixture 작성
12. timezone/DST/true solar time 테스트 작성
```

---

## 18. 완료 기준

```text
1. 해외 도시의 역사적 timezone/DST를 계산할 수 있다.
2. 출생지 좌표와 IANA timezone이 함께 저장된다.
3. UTC offset, DST 여부, tzdata version이 출력된다.
4. 경도 보정과 균시차가 분리되어 출력된다.
5. 진태양시 적용 전후 시주 변경 여부가 출력된다.
6. ambiguous/nonexistent local time을 감지한다.
7. timezone 결정 불가 시 계산을 보류한다.
