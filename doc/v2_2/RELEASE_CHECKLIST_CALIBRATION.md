# Release Checklist — 캘리브레이션 probe 트랙 (CAL-P0/P1)

> 상태: **대기(2026-07-03 작성 — CAL-P1 core close 시점)**. 아래 3건은 core가 아니라
> release/review 트랙이다. 전부 처리 후 오픈/베타 → 실사용 로그 2차 검수 → CAL-P2 범위
> 결정 순서로 진행한다(데굴님 확정).
>
> 관련: `CALIBRATION_STATIC_TRANSIT_PROBES.md`(설계 SSOT),
> `cases/1980_1122_job_report_case.md`(출발 사례).

## R-1. 문구 전문가 감수 — deficiency_pair_questions.json 외

- [ ] `backend/dictionaries/interpretations/deficiency_pair_questions.json` (10축, A/B 쌍)
- [ ] `backend/dictionaries/interpretations/activity_keyword_map.json` (오행 5 + 현침살)
- [ ] `backend/dictionaries/interpretations/remedy_action_map.json` (오행 5 행동)

감수 시트 생성(§5~7에 포함됨):

```bash
python backend/scripts/export_review_sheet.py backend/dictionaries review_sheet.md
```

**감수 기준(질문 문구 — 엔진 로직 아님)**:
1. 결핍을 결함처럼 표현하지 않는가
2. 특정 오행/십성을 좋다/나쁘다로 단정하지 않는가
3. 사용자가 자기비난으로 받아들이지 않는가
4. 질문이 너무 전문용어화되어 있지 않은가
5. A/B 쌍이 실제로 정적 체감과 운 작동을 분리해서 묻는가

통과 항목은 `reviewed: true` 반영(원칙 5 — validate → 회귀 → 반영).

## R-0. ✅ CAL-QA 무신호 응답 패치 (2026-07-03 완료)

오픈 전 데이터 위생: 영역별 체감 `no_domain_activity`("특별한 일 없었음") + 용신 검증
이벤트 `not_occurred`("그런 일 없었다") 추가 — 채점·분모 제외, accumulate_only(docs/14 §8).
이로써 R-2·CAL-P2가 쓸 응답 데이터에서 무응답/기억 안 남/실제 없음이 분리 수집된다.

## R-2. denial_kind 룰 실사용 보정 — 지금 정교화 금지(과적합 위험)

현행 룰 기반 5분류(absolute/situational/temporal/mixed/unclear + 빈 진술 null)는 1차로
충분. **실사용 `trait_statement`가 쌓인 뒤** 문장 분포를 보고 보정한다.

출시 후 관찰 지표(원천: `CalibrationResult.trait_probe_feedback`·`deficiency_pair_feedback`
— subject_yongsin.calibration blob에 저장됨):
1. 빈 진술 비율
2. situational 비율
3. temporal 비율
4. mixed 비율
5. absolute 반복 축(같은 axis에서 반복되면 expert_review 우선순위 상향)
6. 특정 trait_target에서 denied가 과도하게 나오는지

## R-3. 모바일 실기기 화면 확인

- [ ] transition_probe 카드가 길게 밀리지 않는가
- [ ] static/transit pair가 같은 맥락으로 보이는가('평소 체감/해당 시기 체감' 칩)
- [ ] 선택지 버튼이 두 줄 이상일 때 깨지지 않는가
- [ ] trait_statement 입력창이 과도하게 눈에 띄지 않는가
- [ ] q1~q5보다 probe가 부담스럽게 보이지 않는가

## 이후 — CAL-P2 범위 결정에 필요한 실사용 데이터

CAL-P2 후보(② 갈리는 오행 조준 / ⑤ 대화 실측 승격 / ⑥ role confidence 미세 조정)는
아래 데이터를 본 뒤 결정한다:
1. 사용자가 trait_statement를 실제로 얼마나 쓰는가
2. 반박이 absolute인지 situational인지 temporal인지
3. static_deficiency × transit_activation 응답 조합 분포
4. denied+none 축이 자주 나오는가
5. agreed+strong 양면 서사가 실제 답변 만족도를 높이는가
