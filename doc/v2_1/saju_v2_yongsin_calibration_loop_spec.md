# 사주서비스 v2 — 용신 검증 루프 명세서

> 목적: 용신 후보를 사용자의 실제 과거 사건 피드백으로 검증하고, 후보 모델의 적합도를 갱신하기 위한 명세서.  
> 원칙: 용신 확정은 계산만으로 하지 않고, 대운·세운 반응과 사용자 피드백을 통해 calibration한다.

---

## 1. 입력

```yaml
calibration_input:
  chart_id:
  yongsin_analysis:
  luck_cycles:
    daewoon:
    yearly_luck:
    monthly_luck:
  user_age:
  available_year_range:
```

---

## 2. 검증 질문 구성

질문은 기본 5개 생성한다.

```text
1. 용신 후보 긍정 검증
2. 기신 후보 부정 검증
3. 경쟁 모델 비교 검증
4. 특정 사건 도메인 검증
5. 년월 단위 상세 검증
```

---

## 3. 검증 연도 선택

각 연도별로 다음을 계산한다.

```yaml
period_features:
  year:
  ganji:
  daewoon:
  activated_elements:
  activated_ten_gods:
  relation_to_yongsin_candidate:
  relation_to_gisin_candidate:
  structure_activation:
  palace_activation:
  volatility_score:
  expected_by_model:
```

연도 선택 기준:

```text
- 후보 용신이 강하게 들어오는 해
- 후보 기신이 강하게 들어오는 해
- 두 모델의 예측이 갈리는 해
- 대운과 세운이 같은 방향으로 강화되는 해
- 합충형파해로 원국 핵심 구조가 자극되는 해
- 사용자가 기억할 가능성이 높은 연령대
```

---

## 4. 질문 형식

```yaml
question:
  id:
  period:
  period_type: year | year_month | daewoon_period
  target_models:
  expected_effect:
  domains:
  text:
  answer_options:
```

예시:

```text
2015년 전후에는 취업, 자격증, 진로, 인연 면에서 일이 풀리는 느낌이 강했나요?
```

---

## 5. 사건 도메인

```yaml
event_domains:
  career:
    - 취업
    - 이직
    - 퇴사
    - 승진
    - 프로젝트 성과
  study:
    - 입학
    - 졸업
    - 시험
    - 자격증
  money:
    - 큰 수입
    - 큰 지출
    - 투자 손익
  relationship:
    - 연애 시작
    - 연애 종료
    - 결혼
    - 이별
  family_health:
    - 본인 건강
    - 가족 건강
    - 병원
    - 간병
  relocation:
    - 이사
    - 독립
    - 해외 이동
  legal_public:
    - 계약
    - 소송
    - 공공기관
    - 신분 변화
```

---

## 6. 피드백 스케일

```yaml
feedback_scale:
  very_positive: 2
  positive: 1
  neutral: 0
  negative: -1
  very_negative: -2
  unknown: null
```

`unknown`은 점수 계산에서 제외한다.

---

## 7. 점수 계산

```python
if predicted_effect == user_feedback_direction:
    score_delta = abs(user_score)
else:
    score_delta = -abs(user_score)
```

강한 사건일수록 가중한다.

```yaml
event_weight:
  major_life_event: 1.5
  normal_event: 1.0
  minor_event: 0.5
```

예:

```python
model_score += score_delta * event_weight * period_confidence
```

---

## 8. 최종 판정

```yaml
calibration_decision:
  calibrated:
    condition:
      - evidence_count >= 4
      - match_rate >= 0.75
      - top_model_gap >= 0.15

  probable:
    condition:
      - evidence_count >= 3
      - match_rate >= 0.60

  uncertain:
    condition:
      - evidence_count < 3
      - match_rate < 0.60
      - model_scores_too_close
```

---

## 9. 출력

```yaml
calibration_result:
  status: calibrated | probable | uncertain
  final_yongsin:
  final_heesin:
  final_gisin:
  final_gusin:
  confidence:
  evidence_count:
  match_rate:
  model_scores:
  unresolved_questions:
```

---

## 10. 구현 금지 사항

```text
1. 기억나지 않음 답변을 0점으로 계산하지 말 것.
2. 한 질문만으로 용신 확정하지 말 것.
3. 좋은 사건/나쁜 사건을 분야 구분 없이 단순 합산하지 말 것.
4. 대운을 무시하고 세운만으로 검증 연도 선택하지 말 것.
5. 후보 모델 간 예측이 같은 해만 질문하지 말 것.
6. 검증 실패 시 억지로 calibrated 처리하지 말 것.

---

# v2.1 보완 — 중화사주 검증과 사건 결과 평가

## 1. 중화사주 전용 검증

```yaml
neutral_chart_calibration:
  require_competing_models: true
  compare_opposite_flows: true
  include_behavior_change: true
```

## 2. 건강/사고 사건 결과 평가

```yaml
event_outcome_detail:
  event_occurred:
  event_type:
  severity:
  recovery_speed:
  lasting_damage:
  final_outcome:
```

## 3. 추가 이벤트 도메인

```yaml
behavior_change:
  - 대외활동 증가
  - 성격 변화
  - 독립성 증가
  - 사회적 네트워크 확대
self_direction:
  - 진로 재설정
  - 전공 변경
  - 재수/재입학
  - 새로운 목표 설정
```
