# 사주서비스 v2 — 안정적 만세력 엔진 검증·회귀 테스트 명세서

> 목적: LLM에 의존하지 않는 만세력 엔진의 정확도와 재현성을 보장하기 위한 테스트/검증 명세서.

---

## 1. 테스트 계층

```text
1. mapping unit test
2. calendar conversion test
3. timezone/DST test
4. true solar time test
5. pillar calculation test
6. hidden stem/ten god test
7. five element distribution test
8. ten god distribution test
9. strength 9 band test
10. relation structure test
11. geokguk test
12. yongsin candidate test
13. luck cycle test
14. calibration loop test
15. full engine snapshot test
```

---

## 2. 재현성 정책

모든 계산 결과에는 데이터 버전을 기록한다.

```yaml
engine_version:
tzdata_version:
solar_terms_version:
lunar_calendar_version:
rule_config_version:
```

---

## 3. Golden Fixture

대표 케이스를 고정한다.

```yaml
fixtures:
  - name: korea_seoul_1980_11_22
  - name: japan_tokyo_standard
  - name: us_newyork_dst
  - name: uk_london_bst
  - name: india_half_offset
  - name: australia_dst
  - name: zi_hour_boundary
  - name: true_solar_hour_change
  - name: lunar_leap_month
```

---

## 4. Snapshot 기준

초기에는 절대 퍼센트를 강하게 lock하지 않는다.

```text
Phase 1:
  핵심 간지, timezone, 시주 변경 여부, strongest/weakest 정도 검증

Phase 2:
  오행/십성 소수점 1자리 snapshot

Phase 3:
  전체 JSON snapshot
```

---

## 5. 실패 테스트

반드시 실패해야 하는 구현:

```text
1. DST 무시
2. timezone 현재 offset만 사용
3. 진태양시 시주 변경 미표시
4. 월주를 음력 월로 계산
5. 일간을 비견 점수에 자동 포함
6. 부족 오행 자동 용신
7. 공망 0 처리
8. 합 자동 합화
9. 대운/세운을 원국분포에 혼합
10. LLM으로 간지 계산
```

---

## 6. CI 기준

```text
- 모든 unit test 통과
- golden fixture 통과
- schema validation 통과
- calculation_trace 필드 존재
- engine_version 필드 존재
```

---

## 7. 완료 기준

```text
1. 동일 입력은 동일 결과를 반환한다.
2. 계산 근거가 trace로 남는다.
3. 버전이 기록된다.
4. timezone/DST/진태양시/절기/간지 계산이 fixture로 검증된다.
5. LLM 없이 전체 만세력 JSON을 생성한다.

---

# v2.1 보완 — UI·신살·중화사주 테스트

## 1. 신살 테스트 추가

```text
- 모든 신살이 full_list에 반환되는지
- 주별/카테고리별 표시가 같은 source를 참조하는지
- 반복 신살 intensity가 증가하는지
- 신살이 strength/yongsin/geokguk 점수에 직접 반영되지 않는지
```

## 2. 중화사주 테스트 추가

```text
- root_score가 높아도 strong_chart_gate 실패 시 신강 확정 금지
- 신왕과 신강 필드가 분리되어 출력되는지
- 중화권에서 competing_models가 반환되는지
```

## 3. UI 테스트 추가

```text
- 시간 모름일 때 시주가 ?로 표시되는지
- 시간 입력 시 시주가 정상 표시되는지
- 진태양시 시주 변경 badge가 표시되는지
- 전체 신살 패널이 누락 없이 렌더링되는지
```
