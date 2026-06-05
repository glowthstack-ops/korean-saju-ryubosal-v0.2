# 사주서비스 v2 Greenfield 구축 마일스톤 및 초기 시스템 구조 지시서

> 목적: 이 문서는 Codex 또는 개발 에이전트에게 전달하기 위한 **신규 독립 시스템 구축용 구현 지시서**이다.  
> 전제: v2는 v1의 리팩터링이 아니라, **별도 레포/별도 도메인/별도 API/별도 계산 엔진**으로 구축한다.  
> 목표: 먼저 정밀 만세력 엔진을 완성하고, 이후 LLM 기반 사주 서비스와 검증형 용신 캘리브레이션 시스템으로 확장한다.

---

## 0. Greenfield 전제

### 0.1 기본 원칙

v2는 기존 v1 코드를 직접 수정하지 않는다.

```text
v1 = 참고용 산출물 / 검증 비교군
v2 = 신규 설계 / 신규 계산 엔진 / 신규 API / 신규 화면 구조
```

Codex는 아래 원칙을 따른다.

1. 기존 v1 코드를 복사해서 임시 수정하지 않는다.
2. v1의 출력 항목은 참고하되, v2의 데이터 구조는 새로 설계한다.
3. v2는 계산 엔진, 분석 엔진, 검증 엔진, LLM 풀이 엔진을 분리한다.
4. LLM은 사주를 계산하지 않는다. LLM은 계산된 구조화 데이터를 설명만 한다.
5. 모든 핵심 판정에는 `score`, `confidence`, `reason`, `requires_validation`을 포함한다.
6. 용신은 최초부터 확정하지 않는다. 후보 → 검증 → 확정 또는 보류 흐름을 사용한다.
7. 만세력 엔진은 LLM 없이도 독립적으로 동작해야 한다.

---

## 1. 전체 마일스톤

### Milestone 1. 만세력 엔진 제작

목표:

```text
정확한 시간 보정, 절기 기준 사주 산출, 원국/대운/세운/월운 계산이 가능한 독립 엔진 구축
```

포함 범위:

- 양력 입력 처리
- 음력/윤달 입력 처리
- 출생 지역 입력
- 국가/지역/시기별 표준시 처리
- 서머타임 처리
- 경도 보정
- 균시차 보정
- 진태양시 산출
- 절기 기준 월주 산출
- 년주/월주/일주/시주 산출
- 지장간 산출
- 십성 산출
- 12운성 산출
- 공망 산출
- 합충형파해 산출
- 병존/간여지동 산출
- 대운 산출
- 세운/월운 산출
- 구조화 JSON 출력

완료 기준:

```text
동일 입력값에 대해 항상 동일한 JSON 결과를 반환한다.
시간 보정 과정이 추적 가능하다.
진태양시 적용 전후 시주 변화 여부를 확인할 수 있다.
절기 기준 월주 산출 근거를 확인할 수 있다.
```

---

### Milestone 2. 만세력 서비스 우선 론칭

목표:

```text
LLM 풀이 없이도 사용자가 신뢰할 수 있는 정밀 만세력 화면 제공
```

포함 범위:

- 생년월일시 입력 UI
- 양력/음력/윤달 선택
- 출생지 검색 또는 좌표 선택
- 시간 보정 결과 표시
- 사주 팔자 카드 표시
- 오행/십성 분포 표시
- 통근/득령/득지/득세 표시
- 신강/신약 9단계 표시
- 격국 후보 표시
- 합충형파해 구조 표시
- 공망 활성 조건 표시
- 대운표 표시
- 현재 대운 상세 표시

완료 기준:

```text
사용자는 LLM 없이도 자신의 원국, 시간 보정, 대운, 주요 구조 작용을 확인할 수 있다.
v1보다 항목은 많지만 화면은 더 정리되어 있어야 한다.
```

---

### Milestone 3. LLM을 활용한 사주 서비스 제작

목표:

```text
계산 엔진이 만든 구조화 데이터를 기반으로 LLM이 해석 문장을 생성
```

포함 범위:

- LLM 입력용 요약 JSON 생성
- 사용자 질문 분류
- 질문에 필요한 계산 데이터만 추출
- LLM 프롬프트 템플릿
- 명식 계산 금지 가드레일
- 근거 기반 답변
- 불확실성 표현
- 용신 미확정 시 단정 금지
- 검증 필요 시 검증 질문 유도

완료 기준:

```text
LLM은 사주를 새로 계산하지 않는다.
LLM 답변은 engine_result의 필드를 근거로 한다.
용신이 candidate 상태이면 확정 표현을 하지 않는다.
```

---

### Milestone 4. 베타 테스트 및 실전 정보 수집

목표:

```text
사용자의 실제 과거 사건 피드백을 수집하여 용신/기신 후보와 풀이 정확도를 보정
```

포함 범위:

- 용신 후보 2개 생성
- 기신 후보 2개 생성
- 후보별 검증 연도/년월 추출
- 사용자 피드백 질문 5회 생성
- 사건 도메인 선택 UI
- 길/흉 체감 스케일 입력
- 후보 모델별 적합도 계산
- 용신/희신/기신/구신 신뢰도 업데이트
- 베타 피드백 로그 저장
- 오판 케이스 수집

완료 기준:

```text
사용자 피드백을 통해 용신 후보 모델의 score와 confidence가 갱신된다.
검증 실패 시 용신 확정이 보류된다.
베타 로그는 추후 풀이 정교화에 사용할 수 있다.
```

---

### Milestone 5. 서비스 론칭

목표:

```text
검증형 만세력 + LLM 풀이 + 티켓 기반 Q&A 서비스를 안정적으로 제공
```

포함 범위:

- 사용자 세션/임시 ID
- 티켓 차감
- 결제 연동
- 질문 히스토리 정책
- 개인정보 최소 저장 정책
- PDF 또는 로컬 저장 안내
- 장애 로그
- 계산 결과 캐싱
- 베타 피드백 기반 룰 업데이트
- 운영 대시보드

완료 기준:

```text
사용자는 만세력 계산, 용신 검증, LLM 풀이, 유료 Q&A를 하나의 흐름으로 이용할 수 있다.
계산 엔진과 LLM 풀이 엔진은 독립적으로 배포/테스트 가능해야 한다.
```

---

## 2. 신규 시스템 권장 아키텍처

### 2.1 모노레포 권장 구조

초기에는 모노레포로 시작한다. 단, 도메인 경계는 명확히 분리한다.

```text
saju-v2/
  apps/
    web/
      # 사용자 웹 프론트엔드
    admin/
      # 운영자/베타 로그 확인용 어드민
    api/
      # FastAPI 또는 Node API 서버

  packages/
    manse-core/
      # 순수 만세력 계산 엔진
    manse-analysis/
      # 신강약, 격국, 용신 후보, 구조 분석
    manse-calibration/
      # 용신 검증 질문 생성 및 피드백 점수화
    saju-llm/
      # LLM 프롬프트, 답변 생성, 가드레일
    shared-types/
      # 공통 타입, enum, JSON schema
    shared-utils/
      # 날짜, 오행, 간지, 검증 유틸

  data/
    solar-terms/
    timezone-history/
    dst-rules/
    location-db/
    test-fixtures/

  docs/
    product/
    engine/
    api/
    llm/
    calibration/
    qa/

  tests/
    unit/
    integration/
    regression/

  scripts/
    generate_solar_terms.py
    validate_fixtures.py
    compare_with_v1.py
```

---

### 2.2 백엔드 기준 모듈 구조

Python/FastAPI 기준 예시이다.

```text
apps/api/
  app/
    main.py
    routers/
      manse.py
      calibration.py
      llm.py
      health.py
    services/
      manse_service.py
      calibration_service.py
      llm_service.py
    schemas/
      manse_request.py
      manse_response.py
      calibration.py
    settings.py

packages/manse-core/
  manse_core/
    calendar/
      lunar_solar_converter.py
      solar_terms.py
      ganji_calendar.py
    time_correction/
      timezone_resolver.py
      dst_resolver.py
      true_solar_time.py
      equation_of_time.py
      longitude_correction.py
    pillars/
      year_pillar.py
      month_pillar.py
      day_pillar.py
      hour_pillar.py
      hidden_stems.py
      ten_gods.py
      twelve_unseong.py
      gongmang.py
    luck/
      daewoon.py
      yearly_luck.py
      monthly_luck.py
    relations/
      combinations.py
      clashes.py
      punishments.py
      harms.py
      breaks.py
      coexistence.py
      gan_yeo_ji_dong.py

packages/manse-analysis/
  manse_analysis/
    distribution/
      element_distribution.py
      ten_god_distribution.py
      visible_hidden_distribution.py
    strength/
      strength_score.py
      root_score.py
      season_score.py
      side_balance_score.py
      nine_band_classifier.py
    structure/
      geokguk_detector.py
      special_structure_detector.py
      transformation_detector.py
      follow_structure_detector.py
      dominant_structure_detector.py
      tonggwan_detector.py
      isolation_health_detector.py
    yongsin/
      eokbu_model.py
      support_day_master_model.py
      johu_model.py
      tonggwan_model.py
      special_case_model.py
      candidate_aggregator.py
      final_policy.py

packages/manse-calibration/
  manse_calibration/
    period_selector.py
    question_generator.py
    feedback_schema.py
    feedback_scorer.py
    model_updater.py
```

---

## 3. 초기 개발 순서

### Phase 0. 프로젝트 부트스트랩

작업:

```text
1. 신규 레포 생성
2. 패키지 구조 생성
3. 공통 타입 정의
4. 테스트 러너 설정
5. 린트/포맷 설정
6. CI 기본 설정
```

완료 기준:

```text
빈 API 서버가 실행된다.
패키지 단위 테스트가 실행된다.
manse-core, manse-analysis, manse-calibration 패키지가 import 가능하다.
```

---

### Phase 1. 입력 및 시간 보정

작업:

```text
1. BirthInput schema 구현
2. 양력/음력/윤달 입력 정규화
3. 출생지 좌표 처리
4. timezone resolver 구현
5. dst resolver 구현
6. 경도 보정 구현
7. 균시차 구현
8. 진태양시 산출
9. 최종 chart datetime 결정
```

출력 예시:

```json
{
  "time_correction": {
    "input_datetime": "1980-11-22T09:08:00",
    "timezone": "Asia/Seoul",
    "timezone_offset_minutes": 540,
    "dst_applied": false,
    "longitude": 126.978,
    "longitude_correction_minutes": -32.1,
    "equation_of_time_minutes": 14.2,
    "true_solar_time": "1980-11-22T08:50:00",
    "final_chart_time": "1980-11-22T08:50:00",
    "hour_pillar_changed": true,
    "day_boundary_rule": "23:00"
  }
}
```

주의:

```text
윤달은 시간 보정이 아니라 음력→양력 변환 단계에서 처리한다.
진태양시는 법정시/서머타임 처리 이후 적용한다.
```

---

### Phase 2. 원국 계산

작업:

```text
1. 절기 데이터 로딩
2. 절기 기준 월주 산출
3. 년주 산출
4. 일주 산출
5. 시주 산출
6. 지장간 산출
7. 십성 산출
8. 12운성 산출
9. 공망 산출
10. 원국 JSON 출력
```

출력 예시:

```json
{
  "pillars": {
    "year": {
      "stem": "庚",
      "branch": "申",
      "ganji": "庚申",
      "stem_ten_god": "상관",
      "branch_ten_god": "상관"
    },
    "month": {
      "stem": "丁",
      "branch": "亥",
      "ganji": "丁亥",
      "stem_ten_god": "편인",
      "branch_ten_god": "정재"
    },
    "day": {
      "stem": "己",
      "branch": "亥",
      "ganji": "己亥",
      "stem_ten_god": "일간",
      "branch_ten_god": "정재"
    },
    "hour": {
      "stem": "己",
      "branch": "巳",
      "ganji": "己巳",
      "stem_ten_god": "비견",
      "branch_ten_god": "정인"
    }
  }
}
```

---

### Phase 3. 세력 분석

작업:

```text
1. 오행 분포 계산
2. 십성 분포 계산
3. 드러난 기운/암장 기운 분리
4. 통근 계산
5. 득령/득지/득세 계산
6. 신강/신약 9단계 점수 계산
7. confidence 계산
```

9단계 구분:

```text
0~11   극신약
12~22  태신약
23~34  신약
35~44  중화신약
45~55  중화
56~65  중화신강
66~77  신강
78~88  태신강
89~100 극신강
```

신강약 점수 공식:

```python
strength_score = (
    0.35 * season_score
  + 0.35 * root_score
  + 0.30 * side_balance_score
  + structure_modifier
)
```

필수 출력:

```json
{
  "strength": {
    "score": 32.6,
    "band": "신약",
    "confidence": 0.68,
    "borderline": false,
    "components": {
      "season_score": 20,
      "root_score": 42,
      "side_balance_score": 38,
      "structure_modifier": -1.5
    },
    "basis": {
      "deukryeong": false,
      "deukji": false,
      "deukse": false,
      "tonggeun": "partial"
    }
  }
}
```

주의:

```text
통근이 있어도 득지가 없을 수 있다.
득지와 통근을 같은 개념으로 처리하지 않는다.
```

---

### Phase 4. 구조 분석

작업:

```text
1. 천간합
2. 지지육합
3. 삼합/방합/반합
4. 충
5. 형
6. 파
7. 해
8. 병존
9. 간여지동
10. 궁성별 작용
11. 안정도 계산
12. 공망 활성 조건
```

출력 예시:

```json
{
  "structure_analysis": {
    "interactions": [
      {
        "type": "충",
        "pair": "亥-巳",
        "positions": ["day", "hour"],
        "palaces": ["배우자궁", "자녀·결과궁"],
        "affected_elements": ["수", "화"],
        "affected_ten_gods": ["정재", "정인"],
        "severity": "high",
        "effects": {
          "yongsin_stability": "decrease",
          "event_volatility": "increase"
        }
      }
    ],
    "gongmang": {
      "day_basis": ["辰", "巳"],
      "affected_positions": ["hour"],
      "activation_required": true
    }
  }
}
```

---

### Phase 5. 격국 분석

작업:

```text
1. 월지 지장간 분석
2. 월지 정기 기준 주격 후보 산출
3. 투간 여부 확인
4. 성격/패격/중성 판정
5. 보조 구조 산출
6. 격국 안정도 산출
```

주의:

```text
보조격이라는 표현을 남발하지 않는다.
주격과 보조 구조를 분리한다.
```

출력 예시:

```json
{
  "geokguk": {
    "main_structure": "정재격",
    "basis": {
      "month_branch": "亥",
      "main_hidden_stem": "壬",
      "main_ten_god": "정재"
    },
    "formation_level": "중성",
    "stability": "안정",
    "auxiliary_structures": [
      "년주 상관 발현",
      "월간 편인 발현",
      "시주 비견 발현"
    ]
  }
}
```

---

### Phase 6. 특수격 및 용신 후보

작업:

```text
1. 종격 후보 검사
2. 전왕/일행득기 후보 검사
3. 합화/화기격 후보 검사
4. 통관 필요 여부 검사
5. 고립/병약/건강 리스크 검사
6. 조후 후보 산출
7. 부일간/부일주형 후보 산출
8. 일반 억부 후보 산출
9. 후보 통합
10. 용신 후보 2개, 기신 후보 2개 출력
```

특수 케이스 우선순위:

```text
1. 계산 불안정/시간 경계 민감
2. 합화/화기격
3. 전왕/일행득기
4. 종격
5. 통관
6. 고립/병약/건강
7. 조후
8. 부일간/신약 보조
9. 일반 억부
10. 격국 참고
```

출력 예시:

```json
{
  "yongsin_analysis": {
    "status": "candidate",
    "special_case_checks": {
      "transformation_structure": {
        "detected": false,
        "confidence": 0.18
      },
      "dominant_one_element": {
        "detected": false,
        "confidence": 0.22
      },
      "follow_structure": {
        "detected": false,
        "confidence": 0.31
      },
      "bridge_required": {
        "detected": true,
        "bridge_element": "화",
        "confidence": 0.54
      },
      "isolation_health": {
        "detected": true,
        "element": "목",
        "risk_level": "medium"
      }
    },
    "candidate_models": [
      {
        "model": "support_day_master",
        "label": "부일간형",
        "yongsin": "토",
        "heesin": "화",
        "gisin": "목",
        "gusin": "수",
        "hansin": "금",
        "confidence": 0.63,
        "requires_validation": true,
        "reason": [
          "신약 판정",
          "재성 수 세력 우세",
          "비겁 토로 일간 직접 보강 필요"
        ]
      }
    ],
    "useful_candidates": [
      {
        "element": "토",
        "score": 0.63,
        "model": "support_day_master"
      },
      {
        "element": "화",
        "score": 0.48,
        "model": "johu_or_resource_support"
      }
    ],
    "unfavorable_candidates": [
      {
        "element": "수",
        "score": 0.71,
        "reason": "재성 과다"
      },
      {
        "element": "목",
        "score": 0.55,
        "reason": "약한 토를 극하는 관성"
      }
    ]
  }
}
```

---

### Phase 7. 용신 검증 루프

작업:

```text
1. 후보 모델별 테스트 연도 추출
2. 용신 후보가 강해지는 시기 추출
3. 기신 후보가 강해지는 시기 추출
4. 상반된 후보 모델이 갈리는 시기 추출
5. 사용자 질문 5개 생성
6. 사용자 피드백 수집
7. 모델별 적합도 업데이트
8. 최종 용신/희신/기신/구신 확정 또는 보류
```

질문 구성:

```text
1. 용신 후보 긍정 검증
2. 기신 후보 부정 검증
3. 경쟁 모델 비교 검증
4. 특정 사건 도메인 검증
5. 년월 단위 상세 검증
```

피드백 스케일:

```text
매우 좋았다: +2
좋았다: +1
보통: 0
힘들었다: -1
매우 힘들었다: -2
기억나지 않음: null
```

출력 예시:

```json
{
  "calibration": {
    "status": "required",
    "questions": [
      {
        "period": "2015",
        "expected_by_model": {
          "support_day_master": "positive",
          "wealth_excess_model": "mixed"
        },
        "domains": ["career", "study", "relationship"],
        "question": "2015년 전후에는 취업, 자격증, 인연, 진로 면에서 일이 풀리는 느낌이 강했나요?"
      }
    ]
  }
}
```

---

## 4. API 초안

### 4.1 만세력 계산 API

```http
POST /api/v2/manse/calculate
```

Request:

```json
{
  "birth": {
    "calendar_type": "solar",
    "is_leap_month": false,
    "date": "1980-11-22",
    "time": "09:08",
    "time_unknown": false
  },
  "birth_place": {
    "country": "KR",
    "city": "Seoul",
    "latitude": 37.5665,
    "longitude": 126.978
  },
  "options": {
    "use_true_solar_time": true,
    "day_boundary_rule": "23:00",
    "zi_hour_rule": "default",
    "include_traditional_extras": true
  },
  "user_context": {
    "gender_for_daewoon": "male"
  }
}
```

Response:

```json
{
  "chart_id": "uuid",
  "input_summary": {},
  "time_correction": {},
  "solar_term_basis": {},
  "pillars": {},
  "force_analysis": {},
  "structure_analysis": {},
  "geokguk": {},
  "yongsin_analysis": {},
  "luck_cycles": {},
  "calibration": {},
  "traditional_extras": {}
}
```

---

### 4.2 검증 질문 생성 API

```http
POST /api/v2/calibration/questions
```

Request:

```json
{
  "chart_id": "uuid",
  "yongsin_analysis": {},
  "luck_cycles": {},
  "question_count": 5
}
```

Response:

```json
{
  "questions": []
}
```

---

### 4.3 검증 피드백 제출 API

```http
POST /api/v2/calibration/feedback
```

Request:

```json
{
  "chart_id": "uuid",
  "answers": [
    {
      "question_id": "q1",
      "period": "2015",
      "overall_score": 2,
      "selected_events": ["취업", "자격증", "좋은 인연"],
      "memo": "하반기에 원하던 회사에 입사했다."
    }
  ]
}
```

Response:

```json
{
  "calibration_result": {
    "status": "calibrated",
    "final_yongsin": "토",
    "final_heesin": "화",
    "final_gisin": "목",
    "final_gusin": "수",
    "confidence": 0.76,
    "evidence_count": 5
  }
}
```

---

### 4.4 LLM 풀이 API

```http
POST /api/v2/llm/answer
```

Request:

```json
{
  "chart_id": "uuid",
  "question": "올해 이직해도 괜찮을까?",
  "engine_result": {},
  "calibration_result": {},
  "answer_options": {
    "tone": "practical",
    "include_uncertainty": true
  }
}
```

Policy:

```text
LLM은 engine_result에 없는 사주 계산을 새로 하지 않는다.
용신이 candidate 상태이면 확정 용어를 쓰지 않는다.
```

---

## 5. 화면 구조 초안

### 5.1 사용자 입력

```text
1. 생년월일
2. 양력/음력
3. 윤달 여부
4. 태어난 시간
5. 태어난 지역
6. 성별 또는 대운 계산 기준
7. 고급 설정
   - 진태양시 적용
   - 야자시/조자시 기준
   - 일자 변경 기준
```

---

### 5.2 결과 화면

권장 순서:

```text
1. 핵심 요약
2. 입력·시간 보정
3. 사주 원국
4. 세력 분석
5. 신강/신약 9단계
6. 용신 후보
7. 구조 작용
8. 격국
9. 운 흐름
10. 검증 질문
11. 전통 부가 정보
```

---

### 5.3 v1 항목 재배치

| v1 항목 | v2 위치 |
|---|---|
| 양력/음력/경도/KST | 입력·시간 보정 |
| 만 나이/성별/순행대운 | 핵심 요약 |
| 사주 팔자 | 사주 원국 |
| 지장간 | 사주 원국 + 격국 |
| 오행 분포 | 세력 분석 |
| 십성 분포 | 세력 분석 |
| 통근 | 신강/신약 9단계 |
| 암장 십성 | 사주 원국 + 격국 |
| 격국 후보 | 격국 |
| 신강약·용신 | 신강약, 용신 후보로 분리 |
| 납음오행 | 전통 부가 정보 |
| 합충형파해 | 구조 작용 |
| 공망 | 구조 작용 |
| 궁성 | 구조 작용 |
| 자리간 작용 | 구조 작용 |
| 용신 안정도 | 용신 후보 + 구조 작용 |
| 격국 안정도 | 격국 |
| 신살 | 전통 부가 정보 |
| 병존·간여지동 | 구조 작용 |
| 대운 | 운 흐름 |

---

## 6. 테스트 전략

### 6.1 Unit Test

필수 테스트:

```text
1. 양력→간지 변환
2. 음력/윤달→양력 변환
3. 절기 기준 월주
4. 시주 산출
5. 진태양시 보정
6. 공망
7. 십성
8. 지장간
9. 대운 순행/역행
10. 신강약 9단계
11. 용신 후보 생성
12. 검증 피드백 점수화
```

---

### 6.2 Regression Test

v1의 대표 케이스를 fixture로 남긴다.

```text
목적:
v1과 결과를 무조건 같게 만들기 위함이 아니라,
차이가 발생하는 지점을 기록하고 설명하기 위함.
```

필수 fixture 예시:

```json
{
  "name": "1980-11-22 Seoul male",
  "birth": {
    "date": "1980-11-22",
    "time": "09:08",
    "place": "Seoul"
  },
  "expected_core": {
    "day_pillar": "己亥",
    "month_pillar": "丁亥",
    "year_pillar": "庚申"
  }
}
```

---

### 6.3 Validation Test

용신 검증 루프는 아래를 테스트한다.

```text
1. 후보 2개 이상 생성 여부
2. 기신 후보 2개 생성 여부
3. 후보별 검증 연도 추출 여부
4. 같은 연도를 중복 질문하지 않는지
5. 사용자가 기억나지 않음을 선택하면 점수에서 제외하는지
6. 매치율이 낮으면 calibrated가 아니라 uncertain이 되는지
```

---

## 7. 데이터 저장 정책

### 7.1 초기 MVP

초기에는 개인정보 저장을 최소화한다.

```text
저장 가능:
- chart_id
- 익명 세션 ID
- 계산 옵션
- 구조화 계산 결과
- 검증 질문/답변
- 피드백 점수

저장 지양:
- 실명
- 상세 생년월일 원문
- 자유서술 개인정보
- 대화 전문
```

---

### 7.2 추후 론칭

```text
사용자에게 PDF 또는 로컬 저장을 안내한다.
서비스 서버는 최소 데이터만 저장한다.
유료 티켓과 계산 결과는 분리한다.
```

---

## 8. Codex 작업 지시

### 8.1 우선 생성할 파일

Codex는 먼저 아래 파일을 생성한다.

```text
docs/engine/greenfield_milestones.md
docs/engine/manse_v2_result_schema.md
docs/engine/time_correction_spec.md
docs/engine/strength_9_band_algorithm.md
docs/engine/yongsin_candidate_algorithm.md
docs/engine/calibration_loop_spec.md
docs/api/v2_api_spec.md
```

---

### 8.2 우선 구현할 코드

1차 구현 대상:

```text
packages/shared-types
packages/manse-core
packages/manse-analysis
apps/api
```

2차 구현 대상:

```text
packages/manse-calibration
apps/web
```

3차 구현 대상:

```text
packages/saju-llm
apps/admin
```

---

### 8.3 작업 순서

Codex는 아래 순서대로 구현한다.

```text
1. 타입과 JSON schema 작성
2. BirthInput validation 작성
3. TimeCorrectionResult 작성
4. PillarResult 작성
5. ManseV2Result 최상위 schema 작성
6. `/api/v2/manse/calculate` mock response 구현
7. time_correction 모듈 실제 구현
8. pillars 모듈 실제 구현
9. force_analysis 모듈 실제 구현
10. structure_analysis 모듈 실제 구현
11. yongsin_analysis 후보 모듈 구현
12. calibration question mock 구현
13. feedback scorer 구현
```

---

## 9. 완료 기준

v2 초기 구조 완료 기준:

```text
1. v1 코드 없이 신규 레포 또는 신규 패키지 구조가 생성되어 있다.
2. `/api/v2/manse/calculate`가 동작한다.
3. 응답 JSON에 아래 필드가 존재한다.
   - input_summary
   - time_correction
   - solar_term_basis
   - pillars
   - force_analysis
   - structure_analysis
   - geokguk
   - yongsin_analysis
   - luck_cycles
   - calibration
   - traditional_extras
4. 신강/신약 9단계 점수가 반환된다.
5. 용신 후보는 final 확정이 아니라 candidate 상태로 반환된다.
6. 특수격 검사 결과가 포함된다.
7. 검증 질문 생성용 데이터가 포함된다.
8. 모든 주요 판정에는 reason과 confidence가 있다.
```

---

## 10. 구현 시 금지 사항

```text
1. LLM이 사주 팔자를 직접 계산하게 하지 말 것.
2. 용신을 최초 계산에서 확정하지 말 것.
3. 부족한 오행을 무조건 용신으로 처리하지 말 것.
4. 신강/신약을 이분법으로만 처리하지 말 것.
5. 통근과 득지를 같은 개념으로 처리하지 말 것.
6. 신살을 용신 결정의 핵심 근거로 사용하지 말 것.
7. 보조격을 주격처럼 표현하지 말 것.
8. 기존 v1 구조를 그대로 복사하지 말 것.
9. 시간 보정 과정을 숨기지 말 것.
10. 진태양시 적용으로 시주가 바뀌는 경우를 표시하지 않는 구현을 하지 말 것.
```

---

## 11. 첫 PR 목표

첫 PR은 전체 기능을 완성하는 것이 아니라, **신규 시스템의 골격을 확정**하는 것이 목표다.

첫 PR 포함 범위:

```text
- 신규 레포 또는 신규 패키지 구조
- 공통 타입
- API skeleton
- ManseV2Result schema
- mock calculation response
- 테스트 fixture 1개
- README
```

첫 PR 제외 범위:

```text
- 완전한 음력 변환
- 완전한 진태양시 계산
- 완전한 용신 확정
- LLM 풀이
- 결제
- 사용자 계정
```

첫 PR 완료 후 다음 PR에서 계산 모듈을 하나씩 채운다.

---

## 12. 핵심 요약

v2는 다음 구조로 개발한다.

```text
Greenfield 신규 시스템
→ 만세력 코어 엔진
→ 세력/구조 분석 엔진
→ 신강약 9단계
→ 특수격/용신 후보 엔진
→ 사용자 검증 루프
→ LLM 풀이
→ 유료 Q&A 서비스
```

가장 중요한 설계 원칙:

```text
계산은 엔진이 한다.
판정은 score와 confidence로 한다.
용신은 후보로 시작한다.
검증을 거쳐 확정하거나 보류한다.
LLM은 계산하지 않고 설명한다.
```

---

# v2.1 보완 — 전체 신살 표시와 만세력 UI

## 1. 신살 표시 정책 변경

```text
계산 가능한 신살은 모두 계산하고 모두 표시한다.
단, 중요도/반복/궁성/십성/오행 context를 함께 제공한다.
신살은 용신·신강약·격국 판단의 핵심 근거로 직접 사용하지 않는다.
```

## 2. 만세력 UI 방향

```text
사용자가 제공한 전통 만세력 앱 형태를 기본 골격으로 한다.
시주 | 일주 | 월주 | 년주 4주 보드를 중심으로 구성한다.
시간 모름이면 시주 칸은 유지하되 ?로 표시한다.
시간 입력 시 진태양시 적용 전후 시주 변화를 표시한다.
```

신규 문서:

```text
saju_v2_manse_page_ui_spec.md
saju_v2_sinsal_full_display_spec.md
saju_v2_neutral_chart_yongsin_update.md
```
