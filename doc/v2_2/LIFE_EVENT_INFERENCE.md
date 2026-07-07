# Life Event Inference — 설계 (v2.2 Phase 8+)

> ## 설계 원칙 (DESIGN PRINCIPLE — 최상단 고정)
>
> **사주 신호를 많이 맞히는 것이 목적이 아니라, 사용자의 실제 삶에 가장 가까운 사건 서사를 선택한다.**
>
> - 점수(score)는 풀이의 목적이 아니라 **후보 압축용 내부 정렬값**이다.
> - 높은 점수라도 현실 맥락과 맞지 않으면 낮춘다.
> - 낮은 점수라도 궁성·관계·과거 패턴·사용자 맥락이 맞으면 우선할 수 있다.
> - 확실하지 않은 사건은 확정형으로 말하지 않는다(절대 원칙 3·8).
> - 이벤트는 개별 라벨이 아니라 **삶의 서사 단위**로 묶어 풀이한다.

배경: 현재 EventScoring은 `score=100` 포화로 후보의 45~70%가 천장에 붙고, raw 1위가 confidence
weak인 사례가 생긴다(`doc/v2_2/SCORE_SATURATION_REVIEW.md`). 더 근본적으로, 사용자의 실제 사건
(예: 2025·2026 이사)이 후보에 **생성조차 안 되는** 누락이 있다. 이는 점수 버그가 아니라 **목적과
점수 체계의 어긋남**이다. 그래서 엔진을 "Event Scoring"이 아니라 **"Life Event Inference"**로
재정의한다.

---

## 1. 최종 정렬축 (점수는 최하위)

```
1. life_fit                 현실 적합도 (reality_gate + 맥락)
2. confidence               사건화 증거 (궁성·관계·층위 = 기존 confidence_level)
3. personal_match           과거 검증 유사도 (개인 + 코호트)
4. intent_match             질문 의도 적합 (intent_event_filter)
5. potential                사주 잠재 (기존 score의 역할)
6. display_score            표시용 — 거의 마지막
```

`EventCandidateV2`에 내부 필드 추가: `life_fit`, `personal_match`, `narrative_group`.
기존 `score`는 제거하지 않고 **`display_score`(최하위 정렬축)로 격하** — 절대값 신뢰를 포기하고
상대 압축·표시 용도로만 쓴다.

## 2. 모듈 구조 + 기존 코드 매핑

| 모듈 | 역할 | 현재 코드 | 상태 |
|---|---|---|---|
| candidate_generator | 운 십성·12운성으로 사건 후보 넓게 생성 | `ten_god_brancher` | ✅ (누락 보강 필요 — §3) |
| reality_gate | 현실 상태와 안 맞는 후보 억제·맥락 후보 시드 | `addendum_gate_modifier`+`GateContext` | ⚠️ 부분 (맥락 필드 확장) |
| event_materialization_checker | 궁성·관계·층위로 사건화 여부 판단 | `relation_palace_engine`+`event_ranker(confidence_level)` | ✅ |
| **personal_calibration** | 과거 실제 사건과 유사 패턴 우선 | `personal_calibration`(apply_personal_match·seed_missing_events)+`life_event_store`(migrations/008) | ✅ (가중 reviewed:false — §7-6 감수 대기) |
| **life_fit_ranker** | 삶의 맥락에 가장 맞는 후보 우선 정렬 | `life_fit_ranker`(LifeFitRanker.rank — event_engine_v2 배선)+`cohort_calibration`(§4.4 활성 게이트) | ✅ (코호트는 임계 미충전 — 수집만, 설계대로) |
| llm_narrative_controller | 확실/가능성 구분, 서사 단위 1~3개 풀이 | `context_reducer`+프롬프트 | ⚠️ 서사 그룹핑 추가 |

## 3. reality_gate — "있으면 강하게, 없으면 폴백" (규칙11 준수)

현실 맥락 입력이 있으면 life_fit으로 강하게 우선·억제하고, **없으면 confidence+personal_match로
폴백**(차단·오류 금지 — 절대 원칙 11). 미입력 시에는 "가능성" 톤으로만 서술.

```
정관+정인 → 학생=입학·합격·자격 / 직장인=직책·승진 / 무직=취업 / 사업자=허가·공문서
일지 충+재성+정인 → 이사계획 있음=이사·계약 / 연애 중=관계 변화 / 맥락 없음=생활 기반 흔들림
```

맥락 필드(전부 optional): career(직업상태·이직의향·소속), relocation(이사계획·계약·거주불안정),
relationship(관계상태·연애의향·배우자), education(재학·시험계획), business(준비·운영·투자).
**누락 사건 시드**(§4와 결합): 이사계획 있음 + 과거 이사 반복 → relocation을 사주 신호가 약해도
후보로 강제 시드(2025·2026 이사 누락 보완).

## 4. personal_calibration

### 4.1 데이터 소스 3종 (새 질문/데이터셋 없음 — 받는 답을 안 버릴 뿐)

| 소스 | 빈도 | 신뢰 | 비고 |
|---|---|---|---|
| ① 현실 신호 캘리브레이션 (§5) | 1회(온보딩) | 높음 | 과거 명시 — 가장 깨끗 |
| ② 채팅 답변 피드백 | 고빈도 | 중 | 평가(👍/👎)+맞은/틀린 직접 입력 |
| ③ 지연 outcome 회수 | 시점 경과 | **최상** | "전에 물어본 X 실제로 됐나요?" |

②③은 기존 chat의 claim 등록/정정 경로(`ConversationEngine.register_system_results`,
FEEDBACK_CORRECTION)를 확장한다. 후보 신호 지문은 엔진이 그 후보를 만들 때 이미 계산한다.

### 4.2 미래 사건 루프 (채팅의 핵심 단서)

채팅은 미래 질문이 많아 즉시 outcome을 못 받는다. 그래서 상태를 분리:

```
reality_fit (즉시: 방향이 맞나)  →  pending (사건 미발생, 결과 대기)  →  outcome (시점 경과 후 확정)
```

`outcome` enum: `confirmed | not_happened | planned | pending | reality_fit_only`.

### 4.3 3계층 보정 + 계층적 백오프 (콜드스타트 해법)

| 계층 | 키 | 가용성 | 가중 |
|---|---|---|---|
| 개인 | subject 본인 | 즉시 | 최상 |
| 코호트(coarse) | **일주 + 성별** (60갑자×2=120버킷) | 초기부터 충전 빠름 | 중 |
| 코호트(fine) | **전체 4기둥 + 성별** | 데이터 쌓인 뒤 | 상 |
| 모집단 | 전체 차트 익명(cases.jsonl) | 항상 | 하(전역 튜닝) |

백오프: `n(fine) ≥ 임계 → fine 사용, 미만 → coarse(일주+성별)로 폴백, 표본수·최근성으로 가중`.
(옵션 중간 계층: 일주+월지+성별 — 격국·조후. 2계층으로 시작.)
키는 `chart_id`가 아니라 **보정 후 산출된 年月日時 간지 + 성별**(진태양시로 장소별 사주가 갈리므로).

### 4.4 코호트 활성 게이트 ★ (사용자 확정)

**모집단(코호트 표본)이 임계 크기에 도달하기 전까지는 "정리(저장)만" 하고 랭킹에 반영하지 않는다.**

```
cohort_sample_n < ACTIVATION_THRESHOLD  →  수집·저장만, life_fit/personal_match에 미반영
cohort_sample_n ≥ ACTIVATION_THRESHOLD  →  해당 계층 코호트 신호 활성
```

- 소표본 코호트가 풀이를 왜곡하는 것을 차단(통계적 안정성). 임계값은 계층별로 둔다(coarse < fine).
- 활성 전에도 **개인 시그니처(①소스)는 사용** — 개인은 표본 1로도 본인에게 유효.
- 임계 미달 동안 데이터는 §4.5 저장소에 계속 누적되어, 도달 즉시 자동 활성된다.

### 4.5 저장 설계 (migrations/008)

확정 사건을 **원자 행**으로 저장(미리 버킷팅 금지 — 읽을 때 granularity별 집계):

```json
{
  "subject_id": "...", "owner_id": "...",
  "pillars": {"year":"庚申","month":"丁亥","day":"己亥","hour":"戊辰"}, "gender": "male",
  "event_key": "relocation", "period": "2025",
  "signal_fingerprint": {"ten_god_groups":["wealth","resource"],"palace":"day_pillar","relation":"CHUNG","twelve_stage":"JEOL"},
  "outcome": "confirmed",
  "source": "reality_signal_calibration | chat_correction | chat_rating | delayed_outcome",
  "weight": 1.0
}
```

인덱스: `(day_pillar, gender)` · `(year,month,day,hour pillars, gender)` · `(owner_id, subject_id)`.
**익명 집계만** — 코호트 쿼리는 빈도·비율만 반환, 개인 식별 데이터 비노출.

## 5. 현실 신호 캘리브레이션 — 질문 규격 ★ (사용자 확정)

개인 시그니처의 깨끗한 1차 소스. **주요 ~10개 연도**에 대해 **그 해 실제 발생한 이벤트를 선택**한다.

- **연도 선정(~10)**: 성년(만19) 이후 현재까지에서 ① 엔진 사건화 강도(confidence) 상위 세운 +
  ② 대운 교운 인접 연도 + ③ 생애 구간 분산(사회초년·30대 등)을 우선해 약 10개.
- **연도별 선택지**: 그 해 엔진이 생성한 후보 이벤트(한글 라벨) + "해당 없음".
  사용자는 실제 일어난 사건을 **다중 선택**.
- **발생 월(선택적·발생 건 한정) ★**: 시기가 사건 발현의 핵심이므로, **선택한(발생한) 사건에만**
  "기억나면 몇 월쯤?"을 추가로 받는다. 월을 주면 그 달 월운을 스코어링해 **월운 지문**(월지 십성·관계 —
  실제 trigger 신호)으로 `period='YYYY-MM'` 정밀 적재한다. 월 미입력은 연도 지문 폴백(규칙11).
  부담은 연도 수준으로 유지하되, 예정·최근 사건(이사 2025-08, 2026-08 예정)은 월 정밀도를 얻는다.
- **이중 목적**: 용신 검증(모델 선택, 기존)과 개인 시그니처(신규)를 **한 질문으로 동시 충족**.
  '해당 없음'/미선택 후보는 not_happened(failed_prediction 페널티 소스)가 된다.
- 저장: §4.5 store에 `source="reality_signal_calibration"`로 적재(신호 지문 동봉).
- 미입력 허용(규칙11) — 안 하면 개인 시그니처 없이 confidence+코호트로 폴백.

## 6. 절대 원칙 준수

- **단정 금지**(규칙3·8): 코호트·개인 신호는 confidence/quality(가능성·톤)에만 반영. "이 사주는
  반드시 이사한다" 류 출력 금지. 명리 자체가 "같은 사주 다른 삶"을 인정 — 확률적 경향이다.
- **미입력 무해**(규칙11): 맥락·이력 없으면 폴백, 차단·오류 없음.
- **익명 집계**: 코호트는 개인 노출 없이 빈도·비율만.
- **reviewed:false 가중**: life_fit·personal_match·코호트 임계·소스 weight는 초안 — 전문가 감수 대상.
- **회귀 보호**: 상대 순위·신호·confidence·금기룰만 고정(절대 점수 비고정) — 튜닝이 회귀를 안 깬다.

## 7. 구현 순서 (수정본 — score 튜닝 이전에 목표 재정의)

```
1. (본 문서) 설계 원칙 + life_fit/personal_calibration 확정
2. 저장소 골격: migrations/008 + 현실 신호 캘리브레이션 질문(수집만, 랭킹 미반영)
3. reality_gate 맥락 필드 확장 + life_fit/personal_match 필드 추가(개인 시그니처만 우선 배선)
4. score → display_score 격하, 정렬축 재정의
5. 코호트 활성 게이트(임계 도달 시 활성) — 그전까지 정리만
6. (그 다음) 가중 튜닝(전문가 감수) — 포화 보정은 이 단계
7. 레거시 events/*.json 21키 정식 이관
8. DB 기동 통합회귀 재확인 + 골드셋(2025-08 재현)
```

기존 순서(score 튜닝 → 이관 → 회귀)를 **목표 재정의 → 저장소·수집 → life_fit 배선 → score 격하
→ (그 다음) 튜닝 → 이관 → 회귀**로 교체한다.

**구현 현황(2026-07-07 문서 싱크)**: 1~5 완료 — ①본 문서 ②`migrations/008_life_events.sql`+
`life_event_store.py` ③`life_fit_ranker.py`(개인 시그니처·코호트 배선, `event_engine_v2.rank`)
④`EventCandidateV2.life_fit/personal_match` + score의 display 격하(`event_engine.py` 정렬축)
⑤코호트 활성 게이트(`cohort_calibration.py` — 임계 미충전으로 수집만, §4.4 설계대로).
남은 단계 = 6(가중 튜닝 — 전문가 감수+실데이터 필요) · 7(레거시 21키 이관) · 8(DB 통합회귀+골드셋).
