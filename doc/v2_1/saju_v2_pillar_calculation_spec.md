# 사주서비스 v2 — 사주 팔자/간지 산출 명세서

> 목적: 시간 보정 후 최종 계산 시각을 기반으로 년주·월주·일주·시주를 안정적으로 산출하기 위한 명세서.  
> 원칙: LLM 사용 금지. 모든 간지 산출은 deterministic function과 fixture test로 검증한다.

---

## 1. 입력

```yaml
pillar_input:
  final_chart_datetime:
    timezone_aware:
    true_solar_time_applied:
  day_boundary_rule:
  zi_hour_rule:
  solar_term_basis:
  calendar_conversion_result:
```

`final_chart_datetime`은 지역·시간 보정 문서에서 산출된 값이다.

---

## 2. 출력

```yaml
pillars:
  year:
    stem:
    branch:
    ganji:
    element:
    polarity:
  month:
  day:
  hour:

pillar_calculation_trace:
  year_basis:
  month_basis:
  day_basis:
  hour_basis:
  day_boundary_applied:
  solar_term_applied:
  warnings:
```

---

## 3. 년주 산출

### 3.1 기준

년주는 절기 기준으로 산출한다.

```text
입춘 이전 출생이면 전년도 년주를 사용한다.
입춘 이후 출생이면 해당 연도 년주를 사용한다.
```

### 3.2 출력 trace

```yaml
year_pillar_basis:
  gregorian_year:
  lichun_datetime:
  birth_after_lichun:
  ganji_year:
```

---

## 4. 월주 산출

### 4.1 기준

월주는 음력 월이 아니라 절기 기준이다.

```text
12절 기준으로 월지를 결정한다.
```

월지 기준:

```text
인월: 입춘~경칩
묘월: 경칩~청명
진월: 청명~입하
사월: 입하~망종
오월: 망종~소서
미월: 소서~입추
신월: 입추~백로
유월: 백로~한로
술월: 한로~입동
해월: 입동~대설
자월: 대설~소한
축월: 소한~입춘
```

### 4.2 월간 산출

년간에 따라 정월 월간이 정해지고 순행한다.

```yaml
month_stem_start_by_year_stem:
  갑기년: 병인월 시작
  을경년: 무인월 시작
  병신년: 경인월 시작
  정임년: 임인월 시작
  무계년: 갑인월 시작
```

---

## 5. 일주 산출

### 5.1 기준

일주는 기준일 offset으로 60갑자를 계산한다.

```python
day_index = (julian_day_number - reference_jdn + reference_ganzi_index) % 60
```

### 5.2 일자 경계

일주 산출에는 day_boundary_rule을 적용한다.

```yaml
day_boundary_rule:
  midnight_00:
  late_zi_23:
  split_zi:
```

23시 기준이면 23:00 이후는 다음 일주로 볼 수 있다.

---

## 6. 시주 산출

### 6.1 시지

```text
자: 23:00~00:59
축: 01:00~02:59
인: 03:00~04:59
묘: 05:00~06:59
진: 07:00~08:59
사: 09:00~10:59
오: 11:00~12:59
미: 13:00~14:59
신: 15:00~16:59
유: 17:00~18:59
술: 19:00~20:59
해: 21:00~22:59
```

자시 분리 옵션이 켜지면 야자시/조자시를 별도 처리한다.

### 6.2 시간 산출

일간에 따라 자시 천간을 결정하고 순행한다.

```yaml
hour_stem_start_by_day_stem:
  갑기일: 갑자시 시작
  을경일: 병자시 시작
  병신일: 무자시 시작
  정임일: 경자시 시작
  무계일: 임자시 시작
```

---

## 7. 지장간/십성/오행 부가 산출

사주 팔자 산출 후 아래 정보를 붙인다.

```text
- 천간 오행
- 지지 표면 오행
- 지장간
- 천간 십성
- 지지 대표 십성
- 지장간 십성
- 12운성
- 공망
```

단, 오행분포/십성분포는 별도 analysis 패키지에서 계산한다.

---

## 8. 검증 fixture

필수 fixture:

```yaml
fixture_1980_11_22_seoul:
  input:
    date: 1980-11-22
    time: 09:08
    place: Seoul
  expected_core:
    year_pillar: 경신
    month_pillar: 정해
    day_pillar: 기해
  hour_pillar:
    civil_time_candidate: 기사
    true_solar_time_candidate: depends_on_true_solar_time
```

주의:

```text
진태양시 적용 여부에 따라 시주가 달라질 수 있으므로 fixture는 civil/true_solar를 분리한다.
```

---

## 9. API 예시

```json
{
  "pillars": {
    "year": {"ganji": "庚申", "stem": "庚", "branch": "申"},
    "month": {"ganji": "丁亥", "stem": "丁", "branch": "亥"},
    "day": {"ganji": "己亥", "stem": "己", "branch": "亥"},
    "hour": {"ganji": "己巳", "stem": "己", "branch": "巳"}
  },
  "trace": {
    "year_basis": "after_lichun",
    "month_basis": "between_lidong_and_daxue",
    "day_boundary_rule": "23:00",
    "true_solar_time_applied": true
  }
}
```

---

## 10. 구현 금지 사항

```text
1. 음력 월로 월주를 산출하지 말 것.
2. 입춘 기준 없이 년주를 단순 양력 연도로 산출하지 말 것.
3. 시주 천간을 하드코딩하지 말 것.
4. 일자 경계 기준을 숨기지 말 것.
5. 진태양시 적용 전후 시주를 비교하지 않는 구현을 하지 말 것.
6. 간지 산출을 LLM에 맡기지 말 것.
```

---

## 11. Codex 작업 단위

```text
1. GanjiCycle 구현
2. SolarTerm loader 구현
3. YearPillarCalculator 구현
4. MonthPillarCalculator 구현
5. DayPillarCalculator 구현
6. HourPillarCalculator 구현
7. HiddenStem resolver 연결
8. TenGod mapper 연결
9. PillarResult schema 작성
10. fixture test 작성
