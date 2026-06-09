# 류보살 v2 작업 이력 (Work Log)

> 구현 기준: `doc/v2_1/` v2.1 명세. 권장 순서는 `saju_v2_engine_document_index.md`.
> 각 단계 완료 시 이 문서에 결과·검증·결정 사항을 append 한다.

---

## Phase 0 — 부트스트랩 (골격) ✅

- 모노레포 워크스페이스(`pyproject.toml`, setuptools editable): `packages/shared_types`,
  `packages/manse_core`, `apps/api`.
- `shared_types`: enums + 단일 출처 상수표 + 전체 `ManseV2Result` 스키마.
  후속 레이어(force/structure/geokguk/yongsin/luck/calibration/traditional_extras)는
  스키마 자리만 확정하고 placeholder(None)로 둠.
- `apps/api`: FastAPI `/health`, `POST /api/v2/manse/calculate`.
- CI(`.github/workflows/ci.yml`): ruff + mypy + pytest.

## Phase 1 — 시간보정 + 절기 + 원국 ✅

- **시간보정**: IANA tz·역사적 DST(`zoneinfo`+`tzdata`, 버전 기록), 경도보정
  `4*(lon-기준자오선)`, 균시차(NOAA 근사), 진태양시, 자시/일자경계(23:00 기본).
  진태양시 적용 전후 시주 변화 표시(`standard_time_hour_pillar` vs
  `true_solar_time_hour_pillar` + 경고).
- **달력/절기**: 음력·윤달→양력(`korean_lunar_calendar`, KASI). 절기는
  `scripts/generate_solar_terms.py`(Meeus 태양황경, 외부 의존성 0)로 1900–2100
  4824개 사전계산 → `data/solar_terms/…json` 고정(재현성).
- **원국**: 입춘 기준 년주, 절기+둔월법 월주, JDN 60갑자 일주(offset=49, 2000-01-01=戊午로
  교차검증), 둔시법 시주, 지장간(가중치합=1.0)·십성·12운성·공망(旬 기반)·납음·궁성.
- **오케스트레이션**: `apps/api/.../manse_service.py` → `ManseV2Result` 조립,
  `metadata`(engine/ruleset/tzdata/solar_terms 버전) + `trace` 기록, chart_id는 입력 해시(결정론).

### 검증 (Golden Fixture: 1980-11-22 09:08 서울 남성)
- 년/월/일 = 庚申·丁亥·己亥, 시(일반시)=己巳 → 진태양시 戊辰(변경 표시), 공망 辰巳, 순행대운.
- 십성: 년干 상관·월干 편인·월支 정재·시干 겁재. 경도보정 -32.088분, 절기 입동→해월.
- pytest 37 pass · ruff clean · mypy clean · 라이브 API 확인 · 동일입력 동일 JSON.

### 결정 사항
- 1차 범위 = 골격 + 시간보정/원국 (사용자 승인).
- 천문/달력 = 검증 라이브러리 + 절기 사전계산 테이블(네트워크 불필요·결정론).
- 프론트엔드 제외(백엔드 엔진 우선).

---

## Phase 2 — 세력분석 (오행/십성 분포 · 통근 · 신강약 9단계) ✅

신규 패키지 `packages/manse_analysis`.

- **오행분포**(`distribution/element_distribution.py`): raw_visible / hidden_base /
  effective_force 3레이어. effective = 위치가중치(천간 8/12/0/10, 지지 12/28/24/16)
  × 지장간 실세력(1.0/0.6/0.35) × 월령계수(왕1.30…사0.65) × 월지본기 1.12 × 투간 × 통근.
  진단: strongest/weakest, excessive(>35%)/deficient(<8%).
- **십성분포**(`distribution/ten_god_distribution.py`): raw/effective + 그룹
  (peer/resource/output/wealth/officer) + missing/hidden_only 분류(천간 부재 vs 지장간 잠재).
- **통근**(`strength/rooting.py`): root_score(월35/일30/시18/년12 × 비겁1.0/인성0.65),
  득령(왕·상)·득지(일지 본기 비겁/인성)·득세(side≥50)·통근 분리, 신왕(무근/약근/보통/신왕).
- **신강약 9단계**(`strength/strength_score.py`): `0.35*season+0.35*root+0.30*side+structure_mod`,
  9구간 분류·±2 borderline·confidence(요소 clarity)·requires_validation, **신왕≠신강 게이트**
  (월/일지 비겁·인성 + 타 자리 1+), 중화권 경고.
- **왕상휴수사**는 `season_state()`로 통합(토월=토 → codex 토일간 정책 자동 재현).
- `force_analysis.py` 집계 → `ManseV2Result.force_analysis`(타입 확정), service 연결.

### 검증 (Golden Fixture)
- 신강약 = **신약** 26.5점(v1 신약 일치), rootedness 약근, 게이트 미통과, conf 0.56→검증필요.
- 오행 effective: 水 최강·excessive(재성 수 강함), raw_visible 木=0(표면 부족)·hidden 木>0.
- 득령/득지/득세=False, 통근=True (신약 정합).
- pytest 60 pass · ruff clean · mypy clean · 라이브 API force_analysis 직렬화 확인.

### 알려진 차이 / 후속 결정 필요
- `five_element_distribution_tests`의 **잠정** 기대값 "effective weakest=wood/deficient=wood"는
  본 엔진의 명세 수식 결과(亥 수월이 水生木으로 지장간 목을 상(1.15)로 보정)와 충돌.
  엔진은 **raw 레이어에서 목 표면부족**을 표시하고 effective에서는 목을 중간값으로 둔다
  (명세의 raw↔effective 분리 원칙에 부합). 테스트 doc은 "퍼센트는 알고리즘 확정 후 lock"이라
  명시 → 현 구현을 기준 스냅샷으로 채택. 스펙 오너 확인 시 조정 가능.
- **구조작용 보정 미반영**(합충형파해/병존/합화/공망 외): structure_modifier는 현재 공망(일/월지)만
  반영. 나머지는 Phase 3(구조작용)에서 추가 예정.

### 결정 사항
- 세력분석은 용신 확정이 아니라 후보 산출 입력값으로만 사용(명세 원칙 유지).

---

## Phase 2.1 — 감사(codex) 지적 반영 ✅

Phase 3 진입 전 재현성 문제 정리.

1. **통합테스트 재현성**: `tests/integration/test_api.py`를 Starlette `TestClient`
   (anyio portal/스레드 기동 → 일부 샌드박스에서 hang)에서 **httpx `ASGITransport` +
   `anyio.run`** 인프로세스 호출로 교체. deprecation 경고도 제거.
2. **mypy 범위 정정 및 강화**: 테스트의 Optional 접근에 assert 추가 →
   이제 `mypy .`(테스트 포함 61파일) clean. CI도 `mypy .`로 상향.
3. **manse_calibration 골격 추가**: `packages/manse_calibration`(period_selector·
   question_generator·feedback_scorer) skeleton — import 가능, 본 구현은 Phase 4
   (`NotImplementedError`). 인덱스/greenfield의 Phase 0 패키지 4종 구성 충족.
4. **오행분포 trace 추가**: `five_elements.calculation_trace`에 위치가중치·월령계수·
   월지본기 보너스·투간/통근 multiplier·연기된 보정(relation/void/coexistence) 기록.
5. **신왕 게이트 정정**: "월/일지 외 다른 자리" 의미로 `evaluate_strong_gate()` 분리
   (월·일지 동시 동류는 한쪽이 ②역할). 순수함수로 단위테스트 추가.

검증: **pytest 64 pass(unit 52 / regression 9 / integration 3)** ·
`mypy .` clean · ruff clean.

**통합테스트 hang 후속 정정(2차)**: ASGITransport 전환만으로는 부족했음 — 라우터가
동기 `def`라 FastAPI가 threadpool(`anyio.to_thread`)로 디스패치하는 지점이 일부
샌드박스에서 hang. `health`/`calculate` 핸들러를 **`async def`**로 전환해 threadpool
디스패치 자체를 제거(엔진은 빠른 결정론적 CPU 작업이라 인라인 호출). 통합 3개 정상 종료.

---

## Phase 3 — 구조작용 + structure_modifier 완성 + 격국 ✅

권장 순서대로 구조작용 → structure_modifier 완성 → 격국.

- **관계 테이블**(`shared_types/constants.py`): 천간합·지지육합·삼합·방합·충·형(삼형/상형/자형)·
  파·해 정규 테이블(육합 辰酉金·巳申水 등 정설 채택, 午未는 火 보수표기).
- **관계 감지**(`manse_core/relations/relations.py`): 천간합, 삼합/반합(왕지 포함)/방합, 육합/충/
  파/해/상형, 삼형(셋 중 2+), 자형, 병존(인접 동일 간/지), 간여지동(주 내 간지 동일 오행).
- **구조작용 집계**(`manse_analysis/structure/structure_analysis.py`): 합화 판정(월령·뿌리·방해
  요소 → exists/possible/confirmed/confidence, 보수적), 궁성 연결, 안정도(용신/격국/뿌리,
  명세 §7 stability_modifier), volatility, calculation_trace.
- **structure_modifier 완성**(strength_9_band §6): day_master_root_clashed(-4)/only_root_damaged
  (-6)/strong_peer_duplication(+3)/strong_resource_support(+2)/day·month_branch_void(-2)/
  transformation_supports·against(±3, 확정 합화만)/self_punishment_on_support_root(-2),
  clamp[-10,10] + breakdown. confidence의 relation_stability도 구조작용 기반으로 산출.
  Phase 2의 공망-only 잠정 structure_modifier를 대체(strength에 주입).
- **격국**(`manse_analysis/structure/geokguk.py`): 월지 정기 주격(비견/겁재→건록/양인격),
  투간(정기/동일십성), 성격/패격/중성(월지 충·형·공망→패), 안정도, 보조 구조("발현" 표기).
- 오케스트레이터 `analyze_chart()` 신설: 분포→통근→구조작용→신강약(구조보정 주입)→격국.
  service가 `force_analysis`/`structure_analysis`/`geokguk` 동시 채움.

### 검증 (Golden Fixture)
- 구조작용: 申亥 해×2, 亥亥 자형, 庚申·戊辰 간여지동, 亥亥 병존 정확 감지.
  structure_modifier=0(뿌리 申/辰 미충·일월지 공망 없음), 안정도 용신0.72/격국0.80/뿌리0.84.
- 격국: **정재격**(월지 亥 정기 壬, v1 일치), 성격=패(亥亥 자형), 보조 "년주 상관/월간 편인/시주 겁재 발현".
- 신강약: structure_modifier 주입 후에도 신약 26.51(이 케이스는 보정 0이라 동일).
- pytest **73 pass** · `mypy .` clean(70파일) · ruff clean · 라이브 API 직렬화 확인.

### 결정/연기
- 합화 확정은 보수적(월령+뿌리+무방해) — 불완전 시 합반/합거로만 처리(명세 원칙).
- 오행/십성 effective 분포의 관계 보정(합충형파해 multiplier)은 여전히 별도 후속 항목으로 연기
  (분포 trace의 deferred_modifiers에 명시). structure_modifier(신강약)는 본 단계에서 완성됨.

---

## Phase 3.1 — 감사(codex) 지적 반영 ✅

1. **합화 blockers 실제 구현**: 기존 `blockers=[]` 고정 → 합 참여 글자가 충/형/자형으로
   흔들리거나(관계 교차), 천간합 글자가 타 천간에 극당하면 blocker로 기록. `confirmed`는
   이제 월령+뿌리+**무방해**를 실제로 만족해야 True, blocker당 confidence -0.15.
   (structure_modifier의 합화 ±3에 직접 영향.)
2. **격국 손상 사유 라벨 정정**: 항상 `month_branch_clashed` → 실제 관계 유형으로
   `month_branch_clashed/punished/self_punished` 구분. 1980 fixture는 亥亥 →
   `month_branch_self_punished`로 정확 표기.
3. **WORKLOG 순서 정정**: 통합테스트 hang 2차 정정 블록을 Phase 2.1 아래로 이동.

검증: **pytest 75 pass** · `mypy .` clean(70파일) · ruff clean ·
blocker 단위테스트(寅亥 육합 + 寅申 충) 및 격국 self_punished reason 테스트 추가.

---

## Phase 4a — 용신 후보 산출 ✅

신규 패키지 `manse_analysis/yongsin` (특수격 검사 → 모델별 후보 → 통합).

- **group↔element 매핑**(`shared_types/constants.group_elements`): 일간 오행 기준
  peer/resource/output/wealth/officer → 오행.
- **특수격 검사**(`special_cases.py`, 보수적): 합화(구조작용 confirmed), 전왕(한 오행 ≥60% +
  신강계열), 종격(극신약/태신약 + 무근), 통관(상극 두 오행 모두 ≥25%), 고립/병약(부족 오행이
  손상 관계 노출). 억부보다 먼저 검사.
- **후보 모델**(`candidates.py`): 부일간형(용=비겁·희=인성·기=관살·구=재성·한=식상),
  인성용신형(관인상생), 식상용신형(제살), 억부형(신강 설기·재관), 조후 보조형(한/난 월령),
  종격/전왕. v2.1 신약 3분기(신왕+관강→식상 / 유근+재·식강→인성 / else 비겁).
- **통합/확정**: 용신·희신 → useful(상위2), 기신·구신 → unfavorable(상위2). 검증 전 status는
  candidate(단일·고신뢰·특수격無·경쟁無이면 probable), `requires_validation=True` 유지.
  `analyze_chart()`/service가 `yongsin_analysis` 채움.

### 검증 (Golden Fixture)
- **용신 土 · 희신 火 · 기신 木 · 구신 水** — v1과 정확히 일치.
  selected_model=부일간형, 경쟁 모델(인성용신·조후) 동시 제시, status=candidate.
- 목은 raw 표면 부족이나 자동 용신이 아니라 **기신(관살)**으로 분류(부족≠용신 원칙 입증).
- 특수격 5종 모두 미검출(중화권 아닌 신약 → 부일간 경로). pytest **80 pass** ·
  `mypy .` clean(75파일) · ruff clean · 라이브 API 직렬화 확인.

### 결정/연기
- 용신 status는 검증 전 candidate/probable까지만(calibrated는 4c 검증 후).
- climate_context 미구현 → 조후는 월령 한난(亥子丑/巳午未) 기반 경량 판정(단독 확정 금지).
- **후보 통합 점수는 경량(모델 confidence max 기반)**. 명세의 full candidate_score
  (model_confidence·strength/structure/climate/geokguk_alignment·stability 가중합)은 후속 보정.

### Phase 4a.1 — 감사(codex) 보완 ✅
- `ElementCandidate.model`/`reason`을 채움(최고 점수를 낸 모델 출처 + 역할 yongsin/heesin/
  gisin/gusin) — 검증 루프(4c) 질문 생성에서 후보 provenance 사용 예정.
- candidate_score full scoring 연기 사항을 위 결정/연기에 명시.

---

## Phase 4b — 대운/세운/월운/일운 ✅

감사 반영해 범위를 **대운/세운/월운/일운**으로 확장. 운은 원국 분포를 바꾸지 않는
별도 레이어. `manse_analysis/luck/luck_cycles.py` + `shared_types/luck.py`.

- **대운**: 순역(양남음녀 순행/음남양녀 역행), 시작나이=절기(월령 節) 거리/3
  (中氣 아닌 節 경계 사용; `SolarTermTable.bounding_month_terms`), 9구간 표,
  간지(월주에서 순/역 진행)·십성·12운성·상반기(천간)/하반기(지지)·원국과의 관계
  (충/육합/천간합/삼합기여)·raw/transformed 오행·용신관계·volatility.
- **세운/월운/일운**: 날짜 함수라 결정론적. 세운=연 간지(입춘 기준), 월운=절기 12개월
  + 둔월법, 일운=해당 월 일주(JDN). 각 항목에 용신정렬(용신운/기신운/혼합/평운).
- **reference_date**(신규 입력, optional): 없으면 대운표만(완전 결정론). 있으면 current_age·
  current_daewoon_index + 세운(±2년)·월운(해당년 12)·일운(해당월) 채움. chart_id에도 포함.

### 검증 (Golden Fixture, ref=2015-06-15)
- 순행, 시작나이 **5**(exact 4.985 = 약 15일/3), 대운 戊子→己丑→庚寅→辛卯…(월주 丁亥 순행).
- current_age 34 → 대운 index 2(庚寅, age25-35). 세운 2015=乙未, 월운 12개, 일운 30개.
- 여성(양녀)→역행 첫 대운 丙戌. 용신운/기신운 라벨링 동작(己丑 土=용신운).
- ref 없으면 세/월/일운 빈 리스트(결정론). pytest **87 pass** · `mypy .` clean(79파일) · ruff clean.

### 결정/연기
- 운의 transformed 오행은 육합/삼합기여 기반 경량 산출(합화 confidence 정밀화는 후속).
- luck_effect의 정밀 정렬 점수(yongsin_alignment_score 수치)는 4c 검증 루프에서 활용 시 보강.

### Phase 4b.1 — 감사(codex) 보완 ✅
1. **대운 transformed_elements 버그 수정**: `육합:子-丑` 문자열을 `split(":")[1]`로 넣어
   오행 아닌 쌍(子-丑)이 들어가던 문제 → `_transformed_elements()` 신설, SIX_COMBINATIONS의
   target 오행 + 삼합 target만 넣도록 수정(戊子→水, 庚寅→木 등 검증).
2. **대운 start_date 표현 정정**: `start_date/end_date` → **`approx_start_date/approx_end_date`**
   (정수 나이 기반 근사임을 명시). 정밀 교운일시는 `LuckCycles.trace.exact_jiao_un_dates`에
   별도 보관(출생 절대시각 + 정확 시작나이년). 1985-11-17 등.

검증: **pytest 88 pass** · `mypy .` clean(79파일) · ruff clean.

---

## Phase 4c — 용신 검증 루프 ✅ (Phase 4 완료)

`manse_calibration` 골격을 실구현(NotImplementedError 제거).

- **검증 기간 선택**(`period_selector.py`): 기억 가능 연령대(만 12세~기준연도) 각 해의
  연간지 오행이 후보 모델별로 positive/negative/mixed/neutral 중 무엇인지 산출 →
  비중립·모델 불일치(경쟁) 가중으로 정보량 점수화·정렬.
- **질문 5종**(`question_generator.py`): ① 용신 긍정 ② 기신 부정 ③ 경쟁 모델 비교
  ④ 사건 도메인 ⑤ 년월 상세. **같은 연도 중복 금지**(used_years), 사건 도메인 옵션 +
  "기억나지 않음" 포함, target_models·expected_effect_by_model 부착.
- **피드백 점수화**(`feedback_scorer.py`): score_feedback(positive→점수/negative→-점수/
  mixed→0.5|x|/volatile→0.3|x|), **unknown 제외**, 중대 사건 1.5 가중. 모델별 누적 →
  best 모델 match_rate·evidence·gap → **calibrated(≥4·≥0.75·gap≥0.15)/probable(≥3·≥0.60)/
  uncertain**.
- **연결**: `ManseV2Result.calibration`(reference_date 있을 때 질문 생성, 없으면 None) +
  **`POST /api/v2/manse/calibration/feedback`**(무상태: birth 재계산 → 동일 질문 채점 →
  CalibrationResult). `ManseV2Result.calibration` 타입 확정, 골격 패키지 → 실구현으로 교체.

### 검증 (Golden Fixture, ref=2015-06-15)
- 질문 5종(2014/2012/2013/2007/2002 — **중복 연도 없음**), 유형 5종 모두 생성.
- 전부 unknown → uncertain·evidence 0. 전부 positive → 모델 점수화 후 판정(calibrated 등).
- reference_date 없으면 calibration None. pytest **92 pass** · `mypy .` clean(80파일) ·
  ruff clean · 피드백 API 직렬화 확인.

### 결정/연기
- calibration은 무상태(persistence 없음): 제출 시 birth로 동일 질문을 결정론 재생성해 채점.
  영속 저장/티켓/세션은 Milestone 5 범위.
- period_confidence·event_weight 정밀화, 월 단위 expected(현재 연 단위)는 후속 보정.

---

## Phase 4 완료 요약

용신 후보(4a) → 대운/세운/월운/일운(4b) → 검증 루프(4c)로 명세 인덱스 Phase 4 완료.
`ManseV2Result`의 force/structure/geokguk/yongsin/luck/calibration 전 레이어가 채워짐
(traditional_extras·신살 전체·UI는 Phase 5 범위).

### Phase 4c.1 — 감사(codex) 보완 ✅ (조후 단독 확정 금지)
- **Blocker 수정**: 조후 보조형(johu)이 raw 점수만으로 단독 calibrated 되던 문제.
  - `YongsinCandidateModel.is_auxiliary` 추가, johu에 True.
  - 피드백 점수에 **모델 confidence prior 가중**(weighted = score × confidence) 적용.
  - **최종 용신 확정은 primary 모델만으로** 수행(보조 모델 단독 확정 금지). 보조가 동일
    용신을 지지하면 보조 근거로만 반영(+0.05), 다른 용신을 지지하며 우세하면 "단독 확정
    불가, primary 기준 채택"을 explanation에 기록. primary 점수 비양수면 uncertain.
- 결과: 1980 fixture 전부 positive → johu(raw 6.0)가 아니라 **support_day_master(土)** 선택.
- 테스트 추가: `test_auxiliary_johu_cannot_be_solely_calibrated`. pytest **93 pass** ·
  `mypy .` clean · ruff clean.

---

## Phase 4 후속 — weighted_model_scores 노출 ✅
- 감사 권고 반영: `CalibrationResult.weighted_model_scores`(confidence 가중=실제 선택 기준)
  를 raw `model_scores`와 함께 노출(UI/로그 혼동 방지).

---

## Phase 5 — 전체 신살 엔진 (traditional_extras) ✅

신규 패키지 `manse_analysis/sinsal` + `shared_types/sinsal.py`.
프론트 UI는 초기 결정상 보류, 백엔드 신살 엔진 우선.

- **catalog**(`sinsal_catalog.py`, default·config 교체 가능): 12신살(삼합 생지 기준),
  천을/천덕/월덕/태극/문창/학당 귀인, 금여·암록, 도화·홍염, 양인·괴강·백호·현침,
  귀문관살·원진 — 표준 공식 테이블. 카테고리/길흉/해석태그 메타 포함.
- **detector + aggregator**(`sinsal_aggregator.py`): 일간·년지·월지·주간지·지지쌍 기준
  감지 → 주별/카테고리별/full_list. **강도**(반복+0.20·월일+0.15·일지+0.12·충형겹침+0.12·
  공망-0.05 → low/medium/high/very_high), 반복 플래그, 구조작용 겹침(activated_by_relations),
  궁성·십성·오행 context. 시간모름 시 시주 신살 미생성 + warning.
- **정책**: 전체 표시하되 `use_for_yongsin_decision=False` — 신강약/용신/격국 점수 불변.
- `ManseV2Result.traditional_extras`(TraditionalExtras: sinsal + 납음) 타입 확정·연결.

### 검증 (Golden Fixture)
- 18개 신살. 천을귀인@년(己→申), 12신살 申=지살·亥=망신살(월·일 반복→very_high)·辰=화개살,
  귀문관살/원진(辰亥), 백호(시주 戊辰 인정 — 백호대살 7종에 戊辰 포함), 납음(庚申=석류목) 등.
- 신살이 신강약(신약 26.51)·용신(土)·격국(정재격)을 바꾸지 않음을 테스트로 고정.
- 시간모름 → 시주 신살 미생성. pytest **98 pass** · `mypy .` clean(85파일) · ruff clean.

### Phase 5 완료 — ManseV2Result 전 레이어 채워짐
time_correction/solar_term_basis/pillars/force/structure/geokguk/yongsin/luck/
calibration/traditional_extras 모두 산출. (만세력 UI = apps/web는 백엔드 우선 결정으로 보류.)

### 결정/연기
- 신살 catalog은 default 표(유파 차이는 config 교체 전제). 추가 신살(공망살 등 별도 표기)은
  필요 시 확장. 신살의 대운/세운 활성화(운에서의 신살)는 후속.

---

## Phase 6 — 회귀 고정 + 공망 보강 ✅

검증 명세(`saju_v2_stable_engine_validation_spec`)의 골든 픽스처/스냅샷/실패테스트 반영.

- **골든 회귀 하니스**(`tests/regression/test_golden_snapshots.py` + `data/.../golden/*.json`):
  korea_seoul_1980 / japan_tokyo / us_newyork_dst / uk_london_bst / india_half_offset /
  australia_dst / zi_hour_boundary / lunar_leap_month — 핵심 간지·일간·tz offset·DST·
  진태양시 시주변화·윤달변환·신강약 band·격국을 lock. 각 케이스 **결정론(동일 JSON)** +
  버전(engine/solar_terms/tzdata)·trace 필드 존재 검증.
  - 행동 가드: DST 케이스 실제 DST 적용(무시 시 실패), 자시경계 23:30 → 일주 己亥→庚子.
- **공망 first-class 보강**(감사 후속): `StructureAnalysis.gongmang`(empty_branches·
  affected_positions·affected_palaces·activation_note) + **공망살**을 신살 full_list에 표시
  (miscellaneous, use_for_yongsin_decision=False).
- **공망 정책 회귀**(`tests/unit/test_gongmang_policy.py`): 공망 글자 분포 유지(제거 금지)·
  월지 공망→격국 패+month_branch_void 사유·신강약 -2 보정·공망살 표시. 기존 분포/신살/
  신강약/confidence의 공망 반영은 이전 단계에서 이미 구현됨을 회귀로 고정.
- 백호 문구 정정: 시주 戊辰은 백호대살 7종에 포함 → 인정이 의도(WORKLOG 정정).

### 검증
- pytest **120 pass**(unit/regression/integration) · `mypy .` clean(87파일) · ruff clean.
- 골든 8케이스 결정론·버전·trace·tz/DST 동작 고정.

### 연기(후속, 명세 §운/공망)
- 오행/십성 effective 분포의 void_modifier(분포 trace deferred) 정밀 반영.
- 대운·세운·운에서의 공망 발동/해소(gongmang_activation) 분석.
- 만세력 UI(apps/web)는 백엔드 우선 결정으로 보류.

### Phase 6 = 백엔드 엔진 마일스톤 완료
명세 인덱스 Phase 0–6의 백엔드 범위 완료(UI 제외). ManseV2Result 10개 레이어 전부 산출 +
지역/DST/윤달/자시/공망 회귀 고정.

### Phase 6.1 — 감사(codex) 보완 + 공망 정책 변경 ✅
- **Blocker(hash-seed 비결정성) 수정**: `four_pillars`/`conftest`에서 `gongmang_branches()`의
  순서 있는 결과를 set→list로 되돌려 순서가 PYTHONHASHSEED에 따라 흔들리던 문제 →
  **canonical list 유지**(set은 membership 전용). pytest seed 0/1/2 모두 121 pass.
  **cross-process 결정성 테스트**(PYTHONHASHSEED 1 vs 2 subprocess JSON 동일) 추가.
- **공망을 신살과 분리**(사용자 지시): 신살 catalog/full_list에서 공망 제거 →
  `StructureAnalysis.gongmang`를 **타입 모델 `GongmangAnalysis`로 승격**(dict→model).
- **일공망 중심·년공망 참조**(사용자 지시): `day_basis_empty_branches`(중심, 신강약/격국
  보정에 사용) + `year_basis_empty_branches`(참조정보, 점수 미사용) 분리. primary_basis="day".
  1980: 일공망 辰巳 / 년공망 子丑(참조).

검증: pytest **121 pass**(seed 0/1/2 동일) · `mypy .` clean(87파일) · ruff clean ·
cross-process 결정성 가드 추가.

---

## 구조 정리 — 백엔드 경계 분리 ✅

전체 서비스 관점에서 현 구현물은 **백엔드**(만세력 엔진 + API)임을 반영해 폴더 재배치.

- `apps/`·`packages/`·`data/`·`scripts/`·`tests/`·`pyproject.toml` → **`backend/`** 하위로 이동
  (git mv로 이력 보존). `__file__` 상대경로 깊이가 보존되어 코드 변경 없음.
- 루트는 전체 서비스 기준: `backend/`(구현됨) · `frontend/`(예정) · `doc/`(공통 명세·이력).
- 루트 `README.md`=전체 서비스 개요, `backend/README.md`=엔진 상세.
- CI: `working-directory: backend`로 조정(job명 backend). `.venv`는 루트 유지, 설치는
  `pip install -e ./backend`.

검증: backend/에서 pytest **121 pass(seed 0/1/2)** · `mypy .` clean(87파일) · ruff clean.

---

## 서비스 #1 — 프론트엔드 (페이지뷰형 만세력 + 간지달력) ✅

전체 서비스의 첫 사용자 서비스(광고/페이지뷰). `frontend/`(Next.js App Router + TS + Tailwind).
계산은 전부 백엔드 API(프론트는 표시 전담).

- **백엔드 추가**: `GET /api/v2/calendar/{year}/{month}`(+/today) — 월 그리드 간지(년/월/일주,
  한자+한글 병기, 절기 마커, KST 만세력 기준). CORS 미들웨어. (커밋 a6c4d64)
- **lib**: `storage.ts`(IndexedDB + Web Crypto **non-extractable AES-GCM** 키로 프로필 암호화,
  서버 미저장), `api.ts`(calculate/calibration/calendar), `locations.ts`(국내·해외 큐레이션 좌표·tz),
  `elements.ts`(오행 색/한자·한글, 간지 한글변환).
- **메뉴/페이지**: 홈 / 만세력(A-1 등록폼 → A-2 결과) / 간지달력.
  - A-1: 성별·양음력(윤달)·생년월일·시간(+**시간모름**)·지역검색. 제출 시 암호화 저장.
  - A-2: 출생요약·진태양시(시주변화 경고)·**4주 보드**(시\|일\|월\|년, 오행색·십성·12운성·지장간·
    공망·궁성, 시간모름 시 ?)·구조작용·요약·신강약·분포·격국·**용신 후보(검증 필요)**·대운표+세운·
    전체 신살. 각 항목 InfoTooltip 설명. **등록정보 초기화** 버튼(IndexedDB 삭제 후 A-1 이동).
  - **용신 검증(흐름)**: A-2 원국/후보 렌더 후 calibration 질문 5종 제시 → 제출 →
    `/calibration/feedback` → 확정/유력/불확실 + 확정 용신 반영(YongsinPanel 상태 갱신).
  - 간지달력: 오늘 기준 이동, 월 그리드(간지 한글+한자, 절기·오늘 강조), 이전/다음 달, 날짜 점프. SSR.
- **광고**: AdSlot placeholder(상/하단), 추후 네트워크 연동 지점.

### 검증
- 프론트 `npm test`(vitest) **7 pass**: 프로필 암복호화 라운드트립 + **평문 미노출**(ciphertext에
  "서울"/"1980" 없음) + 초기화, elements/locations 유틸. `npm run build` 성공(타입체크 통과,
  7 라우트, 달력은 SSR-dynamic).
- E2E(백엔드+`next start`): CORS 200, SSR 달력 페이지에 간지(경신)·절기(입춘) 렌더, 홈 정상.
- 백엔드 pytest **125 pass** · ruff/mypy clean 유지.
- CI에 frontend 잡(npm ci/test/build) 추가.

### 결정/연기
- 실제 광고 네트워크 연동·배포·i18n, 서비스 #2(LLM)는 후속.
- 개인정보는 로컬 암호화 캐시만(서버 저장 없음) — 명세 개인정보 최소화 정책 준수.

### 서비스 #1.1 — 감사(codex) 보완 ✅
1. **/calendar/today KST 고정**: `date.today()`(서버 로컬) → `datetime.now(ZoneInfo("Asia/Seoul")).date()`.
2. **용신 검증 기준일 고정**: 결과 페이지가 마운트 시 `referenceDate=todayISO()`를 state로 1회 고정,
   `calculateManse`와 `submitCalibration`에 동일 값 전달(자정/연 경계에서 질문 재생성 불일치 방지).
3. **월운/일운 렌더 추가**: LuckPanel에 monthly_luck(월운) 전체·daily_luck(일운) 요약(앞 5일+총개수) 노출.
4. **개인정보 문구 정정**: "서버로 전송·저장되지 않고" → "서버에 저장하지 않으며, 계산 요청 시에만
   전송하고 브라우저에 암호화 저장".
- 재진입 UX 확인: `/manse`는 IndexedDB 저장 프로필 감지 시 자동으로 `/manse/result`로 이동(재입력 불필요).
  정보 변경은 결과 페이지의 "등록 정보 초기화" 버튼으로.

검증: backend 125 pass·ruff·mypy clean / frontend vitest 7 pass·next build 성공.

---

## 후속 3 — 엔진 정밀화 (공망 연기분 완성) ✅

- **오행/십성 effective 분포 void_modifier**: 공망 지지의 지장간 기여에 **×0.85**(제거하지 않음)
  적용, trace `void_modifier{factor,applied_to}` 기록, `deferred_modifiers`에서 void 제거
  (이제 relation/coexistence만 연기). 1980 케이스 신강약 26.51→26.28(밴드 신약·용신 土 불변).
- **운 공망 발동/해소(gongmang_activation)**: 대운/세운/월운/일운 지지가 원국 공망 지지를
  전실(채움)/충(발동)/육합(해소)로 자극하면 표기. `DaewoonItem`/`LuckPillar.gongmang_activation`.
  1980: 壬辰·癸巳 대운 공망전실, 丙申 대운 공망해소(申-巳) 등.

## 후속 4 — 간지달력 고도화 ✅

- 백엔드 `CalendarDay`에 **음력(lunar_date·윤달)**, **납음(일주)**, **띠(년지 zodiac)** 추가
  (solar→lunar는 korean_lunar_calendar, 띠는 BRANCH_ZODIAC). 월건(month_ganji)은 기존 제공.
- 프론트 달력: 셀에 음력(음 M.D/윤) 표기, **일 클릭 시 상세 패널**(양력·요일·음력·년/월/일주 한자+한글·
  납음·절기·띠), 월 헤더에 년 간지·띠·월건 요약.

## 개발 서버 편의 ✅
- `scripts/dev.sh`(백엔드:8000 + 프론트:3000 동시 기동), `frontend/.env.example`,
  README "개발 서버" 섹션.

검증: backend **128 pass** · ruff/mypy clean / frontend **7 pass** · next build 성공 ·
라이브 캘린더 음력/납음/띠 필드 확인.

---

## 버그픽스 — 오행 effective 분포 지장간 과대 (five_element_weight_bugfix_spec) ✅

증상: 표면(천간·지지)에 木이 0인데도 effective 木이 19.48%로 "강함"처럼 표시(亥중甲 과대) +
土가 8.72%로 과소. 원인: effective 지장간 가중치(1.0/0.6/0.35)가 지지별 합 1.0을 안 지켜
중기 甲이 과대 + 글로벌 계절보정이 중기 甲까지 부스트 + 표시용/판정용 분포 혼동.

수정(`element_distribution.py`/`ten_god_distribution.py`):
- **지장간 budget 통일**: effective도 지지별 합=1.0 가중치(단1.0/2→0.75·0.25/3→0.70·0.20·0.10).
  亥중甲 0.6→0.25.
- **월령 보정은 본기에만**(×1.30), 중기/여기는 cap(≤1.03). 글로벌 계절보정 제거.
- **암장(hidden-only)**: 표면 없음+지장간만 있는 오행을 `hidden_only_elements`(sources·label 암장·
  operability low) + `display_summary`(visible 우선, 경고)로 분리. (schema 확장)
- 공망 0.85·visible floor 가드 유지.
- **UI**: QuickSummary/DistributionPanel을 **표면 우선** + 암장 별도 + 실세력(고급) 라벨로 변경.

결과(버그 케이스 庚申丁亥己亥己巳): 木 19.48→**10.89%**, 土 8.72→**10.92%**, 火 9.93→**19.87%**,
水 최강 유지. 木 = 암장(亥중甲×2, 작동성 낮음)로 표기. 신강약 신약 유지(점수 스냅샷 갱신).

검증: backend **129 pass**·ruff·mypy clean / frontend **7 pass**·build OK. fixture/실패케이스 테스트 추가.

### 버그픽스 후속 — 표시용/판정용 분포 분리 + 회귀 고정(감사 반영) ✅
감사 권고 반영:
1. **effective 정확 lock**: 버그케이스 effective_percent를 pytest.approx로 고정
   (木 10.89·火 19.87·土 10.92·金 18.35·水 39.96) — 예전 과대 산식 재발 방지.
2. **죽은 상수 제거**: `_chart.HIDDEN_EFF_WEIGHT(1.0/0.6/0.35)` 삭제(분포는 budget 사용).
   `ROOT_HIDDEN_WEIGHT`는 통근 전용·분포 budget과 의도적 차이임을 주석 명시.
3. **표면 최강/최약 tie 배열화**: `strongest_visible_elements`/`weakest_visible_elements`.
4. **표시용(visible) 분포 신설**: 천간(일간 제외)+지지 본기, **암장 제외**, 정규화 →
   `five_elements.visible_percent`/`ten_gods.visible_percent`(+`visible_absent`).
   버그케이스: 오행 木 0%·水 47.3% 과다·火 25.5·金 18.2·土 9.1, 십성 정재 47.3 최강·
   정관/편관 0(표면 부재). effective는 "내부/고급 판정용"으로 격하.
5. **UI**: 요약/분포 패널 기본값을 표시용(암장 제외)로, 암장 별도, 실세력은 접이식 "고급".

본기/중기 비중: 분포 budget(본기 0.70/0.75 > 중기 0.20/0.25), 표시용(본기만), 통근(본기 1.0 >
중기 0.6) — 각 레이어가 본기>중기로 차등. 검증: backend **132 pass**·clean / frontend 7 pass·build OK.

### 후속 — 표면(visible)을 단순 글자수로 재정의(감사 지시) ✅
표면이 판정용 위치가중치를 쓰던 문제 → **표시용은 단순 표면 글자 수**로 분리.
- `five_elements.visible_percent`: 천간(일간 포함) + 지지 표면, **위치가중치 미사용**, 정규화.
  庚申丁亥己亥己巳 → 木 0·火 25·土 25·金 25·水 25(%). 시간 모름이면 존재 6글자 기준 정규화.
- `visible_percent_without_day_master` 별도 필드(일간 1글자만 제외).
- `ten_gods.visible_percent`: 단순 표면(천간 일간 제외 + 지지 본기), `visible_absent`로 표면 부재(-).
- `hidden_support`: 오행별 지장간 출처(표면 유무 무관, 예: 土←申여戊·巳여戊) — 표면 %엔 섞지 않음.
- effective_percent(위치가중·월령·통근·공망·budget)는 **판정용(고급/내부)** 그대로 유지·분리.
- UI: 요약/분포 기본을 표면(단순)으로, 십성은 '일간 제외' 명시, 지장간 보조 라인 추가,
  툴팁에 표면/실세력 정의 구분.
- 테스트: 표면 25/25/25/25/0 고정 + 위치가중 비영향 회귀 + 시간모름 정규화 + hidden_support +
  without_day_master. backend **135 pass**·clean / frontend 7 pass·build OK.

### 버그픽스 — 지장간 표 오류(여기 누락) 교정 ✅
사용자 제보: 亥 지장간이 화면에 甲壬만 표시(표준은 戊甲壬). 표준 지장간표 대조 결과 **왕지·해의
여기(餘氣) 5개 누락** 확인:
- 子 癸 → **壬·癸**, 卯 乙 → **甲·乙**, 酉 辛 → **庚·辛** (왕지: 여기+정기 2개)
- 午 己·丁 → **丙·己·丁**, 亥 甲·壬 → **戊·甲·壬** (3개)
- 나머지 丑寅辰巳未申戌은 정확.
수정: `_HIDDEN_RAW` 교정 + 2지장간 budget이 여기(RESIDUAL)도 처리(MAIN 0.75/보조 0.25, 합 1.0).
회귀 락 테스트 `test_hidden_stem_table_matches_standard`(12지지 전체 + budget 합=1.0) 추가.

영향(정당한 스냅샷 변동, 용신·격국 불변):
- 己 일간이 亥戊·巳戊 등으로 뿌리 강화 → 1980 케이스 신강약 **신약→중화신약**(38.17),
  effective 土 10.92→15.44·木 10.89→8.73 등. 용신 土·정재격 유지.
- 골든: korea 신약→중화신약, uk/us 태신강→극신강(geokguk 불변). effective lock·sinsal·api·
  fixture·golden 스냅샷 갱신.
검증: backend **136 pass**·ruff·mypy clean / frontend 7 pass·build OK.

### 지장간 비중 — 월률분야 일수(月律分野) budget 적용 ✅
사용자 결정(doc/jijanggan_weolryulbunya_ratio.md): 지지 내 본/중/여 비율을 카운트 기반
(0.70/0.20/0.10·0.75/0.25)에서 **월률분야 일수(30일 기준)**로 교체.
- 생지 寅申巳亥=7:7:16 / 고지 辰戌丑未=9:3:18 / 왕지 子卯酉=10:20 / 午(예외)=10:10:10. 亥 戊 인정.
- `_HIDDEN_DAYS`(일수 테이블)로 통합, `hidden_stems_for`=일수/30, `hidden_stem_days` 추가.
  회귀 락 테스트를 글자+일수+합30+budget합1.0까지 고정.
- **자리별(위치) 가중치는 분포 계층의 BRANCH_POS_WEIGHT로 별도 적용**(이번 변경과 독립).
- 분포 표시: 표면(단순)과 실세력(자리별 가중) **둘 다 동등 병표**(접기 제거).

영향(정당, 용신 土 유지): 정기 비중↓·여기 비중↑로 재이동.
- 진태양시(戊辰) 1980: 최강 오행 水→**土**(31%, 戊 시간·辰·亥亥申 여기 戊), 신강약 40.08(중화신약),
  土↔水 근접으로 bridge_required(통관) 감지. 일반시(己巳): effective 木10.32·火18.1·土24.72·
  金17.07·水29.79(水 최강 유지).
- 골든: uk 극신강→태신강, zi_hour 신약→중화신약. effective lock·sinsal·fixture·yongsin 스냅샷 갱신.
검증: backend **136 pass**·ruff·mypy clean / frontend 7 pass·build OK.

### 정정 — 비중 계산에서 일수 budget 제거(자리별 가중치만 유지) ✅
직전 '월률분야 일수 budget' 적용이 사용자 의도와 달랐음. 오행/십성 **비중 계산은 지장간에
자리별(위치) 가중치(BRANCH_POS_WEIGHT)만** 적용하고, 지지 내 본/중/여는 구조적 budget으로 나눈다.
일수(7:7:16 등)는 비중 산식에 곱하지 않는다(표시·사령 참고 표준으로만 보관).
- constants/테스트/골든을 일수 이전(d6c032c, count-budget) 계산 상태로 복구.
- 프론트 '표면+실세력 병표'는 유지. 검증: backend 136 pass·clean / frontend build OK.

### 지장간 본/중/여 분배 비율 — 사용자 지정표 적용 ✅
오행/십성 비중 = **자리별 가중치(BRANCH_POS_WEIGHT) × 본/중/여 비율(사용자 지정)**. 일수 미사용.
- 비율: 3지장간 0.20·0.20·0.60 / 왕지(子卯酉) 0.30·0.70 / 午(예외) 0.30·0.20·0.50. 亥 戊 인정.
- constants `_HIDDEN`(stem,type,ratio)로 통합, 회귀 락 테스트에 비율까지 고정.
- 1980: bug effective 木8.8·火18.83·土22.32·金17.36·水32.69(水 최강), 진태양시 중화신약 39.56·
  용신 土. 골든 전부 동일(밴드 변동 없음). effective lock·sinsal·yongsin(bridge 허용) 스냅샷 갱신.
검증: backend 136 pass·clean / frontend 7 pass·build OK.

### 오행/십성 분포율 — 자리별 가중치 × 지장간 비율 + 일간 포함/제외 3분할 ✅
사용자 가이드 반영. 표시용 분포율 = 자리별 가중치(천간 각10, 지지 年15·月25·日15·時15) × 지장간
비율(0.2/0.2/0.6 등). 월령/투간/공망 보정은 미적용(별도 실세력 레이어).
- `five_elements.distribution_total`(오행, 일간 포함, raw110→100) — 화면 기본
- `five_elements.distribution_environment`(오행, 일간 제외, 100) — 고급
- `ten_gods.distribution`(십성, 일간 제외, 100) — 화면 기본
- 기존 effective_percent(월령·통근·공망)는 신강약/용신 내부용·고급 표기로 유지(미변경).
- UI: 오행=일간 포함, 십성=일간 제외 기본 / 환경 오행·실세력은 '고급' 접기.
1980(일반시): 오행 원국 木7.3·火17.3·土30.9·金20·水24.6, 십성 정재27·상관22·겁재14 …(합100).
검증: backend 137 pass·clean / frontend 7 pass·build OK. (신강약/용신 스냅샷 불변)

### 세력 판단 레이어 분리 — 월령·통근·공망을 분포에서 분리(가이드 반영) ✅
'월령/통근/공망을 분포 그래프에 섞지 말고 세력 판단용으로 분리'하는 4단계 구조 반영.
- **월령**: `five_elements.season_adjusted_element_strength` 신설 = 환경 오행 분포 × SEASON_FACTOR[월지].
  (constants.SEASON_FACTOR 12지지 계수 추가) 용신 전왕/오행 과다·부족 판단도 이 값 사용.
- **신강약 side_balance**: 십성 effective(혼합) → **clean distribution(ten_gods.distribution)** groups로 전환.
  일간 월령이 season과 이중 반영되던 문제 해소.
- **통근**(root_score)·**공망**(structure_modifier)은 기존대로 별도 컴포넌트 유지.
- effective_percent는 주 경로에서 제외(참고 trace). UI 고급은 '월령 보정 세력'으로 표기.
영향: 1980 중화신약 39.99·용신 土·희신 火 유지. 골든 uk 극신강→태신강, zi_hour 신약→중화신약.
검증: backend 139 pass·clean / frontend 7 pass·build OK.

### 격국 평가 + 용신 다축 랭킹 (Phase A/B) ✅
v1 geokguk_master_v2를 v2 네이티브 이식 + 용신을 다축 보정 랭킹으로 개선(사용자 가이드 반영).

**Phase A — 격국 평가**(`structure/geokguk_eval.py`): pattern_confidence(0~1, §7 공식), 성패(-100~100)+
damage_types, 파격/구제, clarity(6 levels), final_weight(0.10~0.60). GeokgukResult.evaluation 추가.
신뢰도는 '성공 크기' 아닌 '무대 선명도(social_expression)'. 1980 정재격·신뢰도 0.35(D)·월지 자형·
final_weight 0.15.

**Phase B — 용신 다축 랭킹**(`yongsin/candidates.py`): 억부/조후/격국(상신)/병약(약신)/특수격 5축 +
동적 가중치(band/조후/파격/격국선명별 §10 세트). 신약→억부0.45 우선으로 용신 안정. 격국·조후·병약은
'보정 레이어'(단독 확정 금지). YongsinAnalysis에 axis_weights/axes 추가. 1980 용신 土·희신 火 유지.
극신약→종격 우선 체크는 special_cases가 억부 전에 처리(유지).

검증: backend **147 pass**·ruff·mypy clean / frontend 7 pass·build OK. 기존 강약/골든/effective 스냅샷 불변.

### 신강·신약 v1.3 8성분 전면 재산정 (day_strength_v1.json 이식) ✅
사용자 제공 v1 마스터를 v2에 네이티브 이식. 강약 점수식을 v1 8성분 합산으로 전면 교체.
- `strength/strength_v1.py` 신설: 월령(관계×월지강도)·통근(정/중/여기)·투간(부호별)·천간십성·
  지장간십성(위치×단계)·합국(삼합/방합/육합 max k)·충(통근지지/월지/관성)·조후 8성분 → score(-100~+100대).
  구조(합/충) 탐지는 v2 constants 재사용, 계수만 v1 마스터에서 이식.
- 7밴드(극신강/신강/중화신강/중화/중화신약/신약/극신약) + **가종격(假從)** 분기
  (일간그룹≤40%·외부≥60%·통근≤15 → band 중화 재라벨, 억부 우선 warning).
- `strength_score.compute_strength`가 compute_v1에 위임(게이트/rootedness/confidence/components 계약 유지).
  components는 8성분(root_score 키 포함) → 격국/용신 다운스트림 호환.
- 용신 신뢰도 공식을 0-100→v1 스케일(중심 0)로 보정.
- **v1 재현 확인**: 1980.11.22 일반시(己巳) = **-53.8 신약**(레퍼런스 일치). 진태양시(戊辰) = -22.7 중화신약, 용신 土 유지.
- 골든 재고정: australia 신강·india 중화신약·japan 중화(가종)·lunar 극신약·uk/us 극신강·zi 중화(가종).
  test_strength 밴드/경계·test_structure·fixture·sinsal 스냅샷 갱신. v1 parity/불변식 테스트 추가.
검증: backend **147 pass**·ruff·mypy clean / frontend 7 pass·build OK.

### 격국 평가 — geokguk_master_v2.json 권위표로 정렬 ✅
Phase A 격국 평가를 사용자 제공 마스터로 재정렬(신뢰도 공식은 마스터 7요소 채택).
- 신뢰도: §7(0~1) → **마스터 7요소(0~100)** 20·20·15·15·15·10·5 + A~E 등급. pattern_confidence는
  =score/100로 보존(용신 가중 호환). 충/합거/공망은 성패로 이동.
- 성패: 6요소 가중치를 마스터(격신성형·일간감당·상신·파격없음 각 0.20 + 구제 0.15 + 청탁 0.05)로 교체,
  6등급(complete_success…severe_muddiness).
- clarity·final_weight(0.25×clarity_mult, cap 0.10~0.60)는 마스터와 동일 확인.
- 1980: 정재격 신뢰도 90(A)·성패 7.0(반성반패)·clarity clear_but_mixed·final_weight 0.30. 용신 土 유지.
검증: backend 147 pass·ruff·mypy clean / frontend 7 pass·build OK.

### 격국 표시 일관성 — 성격(formation)을 성패와 일치 ✅
화면에 '성격 패' ↔ '성패 반성반패/격국 중심'이 모순돼 보이던 문제 수정.
- `formation_level`을 success_failure 등급에서 도출(성격/중성/패) — 월지 손상 하나로 '패' 단정하지 않음.
  월지 공망/충은 damage_type(void_month_branch/chung_month_branch)로 성패에 반영.
- final_weight 해석 구간을 마스터(0.46↑ 핵심 / 0.36↑ 격국중심 / 0.21↑ 주요참고 / 보조)로 정정 →
  0.30은 '주요 참고 축'.
- 용신 axes를 기여 점수 내림차순 정렬.
- 1980: 정재격 성격 중성 · 성패 반성반패 · 가중치 0.30(주요 참고). 용신 土 유지.
검증: backend 147 pass·clean / frontend build OK.

### 격국 다후보 엔진화 + 정밀화 (정기단일 → 후보 랭킹·특수격·격별 위험규칙) ✅
- **배경/문제**: 격이 '월지 정기 1글자'로만 단일 확정 → 중기/여기 투간으로 생기는 격 후보 누락,
  극신약/극신강을 일반 내격으로 고정, 음간 겁재를 일괄 '양인격'으로 오판, 디버그(후보·근거) 부재.
- **해결**:
  - `geokguk_eval`: `GeokCandidate`/`build_candidates`(지장간 전체+투간위치), `score_candidate`
    (위계30·격신투간25[월간]/15[년시]·통근15·상신15·무파격10·청정5=100), `score_all_candidates`(랭킹),
    `special_signal`(전왕/종격), `evaluate_geokguk`를 선택 후보 기준으로 파라미터화.
  - `geokguk.detect_geokguk`: 다후보 산출→랭킹→주격 선택, `candidates[]`·`special_pattern` 출력.
  - **양인 지지조건**: 양인은 양간+양인지지(`_YANGIN`)만, 그 외 겁재월은 `월겁격`(음간 양인 제거).
    yongsin `_GEOK_SANGSIN_GROUPS`에 `월겁격` 매핑 추가(격국용신 누락 회귀 수정).
  - **특수격 치환**: 강신호(타입별 `dominant 0.60`/`follow 0.70`)면 `main_structure`를 특수격으로 치환,
    정격은 `candidates`·`special.jeonggyeok`로 병기. 경계(가전왕/가종)는 '병행 검토'만.
  - **격별 위험규칙(5종)**: 칠살격 무제·인성과다·상관 무로·정관 합거(쟁합 구제)·식신 도식 가중(f1 −25).
  - **격신 투간 정밀화**: '아무 지장간 투간'이 아니라 '주격 격신 본인의 투간'만 가산
    (무관한 여기 투간 과대평가 제거). 1980 정재격 신뢰도 90→**65(B)**로 정정.
  - **모델**: `GeokgukResult`에 `candidates`·`special_pattern` 필드 추가.
  - **프론트**: `GeokgukPanel`에 후보 랭킹 리스트(이름·출처·신뢰도·투간·주격/보조) + 특수격 박스
    (override 시 '특수격(주격)' / 정격 병기).
- **CLAUDE.md 준수 정리**: 신규/재작성 함수 docstring 추가(`detect_geokguk`/`evaluate_geokguk`/
  `candidate_dict`), `special_signal` 타입 안전화(`top` 기본 `""`)로 geokguk 파일 mypy clean.
- **검증**: 골든/회귀/yongsin/api 불변(선택 격 동일, 신뢰도만 정밀화). 동작 확인 — 1986 극신약→종재격
  치환(정격 정재격 병기), 1983 dominant 0.42→병행, 1970 정관격 합거 감지, 식신격+도식→반성반패.
검증: backend 147 pass·ruff clean·mypy(geokguk.py/geokguk_eval.py) clean / frontend tsc OK.
(잔여: `structure/structure_analysis.py:86` unused type-ignore — 본 변경 범위 밖 기존 항목)

### 격국 박스 정리 — 내부 배점/변수 숨김(사용자 친화) ✅
- **문제**: `GeokgukPanel`이 내부 수치·변수를 노출(신뢰도 65점(B)·성패 -5·명확도 `clear_but_mixed`
  enum·격국 가중치 0.3·파격 코드 `chung_month_branch`·후보 신뢰도 숫자).
- **해결**(frontend `GeokgukPanel`만): 정성적 한글로 치환 — 성패는 색 배지(한글 라벨), 선명도/방침은
  `social_expression`+`clarity_policy` 문장, 파격은 `failures[].evidence`(한글)+구제 여부, 특수격은
  `신뢰도 %` 제거·`dominant/follow`→`전왕·일행득기/종격`. 격 후보는 숫자 빼고 접기(▸)로 이동.
  백엔드/데이터 변경 없음.
검증: frontend tsc OK.

### 격국 명확도 정책 문구 정정 — 억부는 용신법(목적 아님) ✅
- **문제**: `_CLARITY_POLICY`가 `억부·용신`/`억부·조후·용신`처럼 나열 → 방법(억부)과 목적(용신)을
  병렬로 둬 개념 혼동(억부 ⊂ 용신법).
- **해결**: `clear_but_mixed` "…억부용신으로 보완한다", `unclear` "…억부·조후 용신 중심으로 해석한다"로 정정.
검증: backend 147 pass·ruff clean.

### ? 툴팁 사용자 친화 정리 + 화면 이탈 방지 ✅
- **문제**: `?` 툴팁이 내부 용어·로직(8성분 점수범위, 레이어, 원점수/보정 등)을 노출. 일부는 화면
  우측을 벗어남. 제목 `신강/신약 (v1.3 8성분)`에 버전·로직 노출.
- **해결**(frontend): 툴팁 7종을 '항목 설명(용도·풀이)'로 교체(시간보정·신강약·오행십성분포·격국·
  신살·대운세운월운·용신). 제목 `(v1.3 8성분)` 제거. `InfoTooltip`을 client 컴포넌트로 바꿔
  열릴 때 위치 측정→뷰포트 밖이면 자동으로 안쪽 이동(좌/우 8px 여백), max-w 90vw로 확대.
검증: frontend tsc OK.
  (후속: 경계 변경 핫리로드 한계로 position:fixed+뷰포트 클램프 방식으로 재작성, dev 서버 1회 재시작 필요)

### 암장(지장간만) 표기 개선 — 위치 포함·중복 제거·한글 통일 ✅
- **문제**: `암장: 木(목)(亥중甲,亥중甲)`처럼 위치 없음·중복·혼합표기(한자+한글 한 토큰)로 읽기 어려움.
- **해결**: backend `_hidden_only_elements` 출처를 `위치(년/월/일/시지) 지지 단계(정/중/여기) 지장간`
  한글 통일 문자열로 생성(`STEM_KO`/`BRANCH_KO` 사용) → 위치로 자연 중복 제거.
  frontend 표기를 `목 — 월지 해 중기 갑 · 일지 해 중기 갑 · 시지 진 여기 을 · 표면에 안 드러나
  작동력 낮음`으로 정리. (`hidden_support`의 "申여戊" 포맷은 테스트 고정이라 유지)
검증: backend 147 pass·ruff·mypy(element_distribution.py) clean / frontend tsc OK.
  (후속: 암장은 오행 내용이므로 **오행 차트 하단**으로 이동, 오행은 사주 원국 **범례 색 배지
  `木(목)`** 방식으로 표기. 지장간 출처는 한글 유지.)

### 암장 — 오행이자 십성으로 재구성(위치별 오행+십성) ✅
- **인식**: 암장 지장간(갑)은 오행(木)이자 십성(정관)이라, 한쪽에만 두면 안 됨.
- **해결**: backend `_hidden_only_elements` 출처를 구조화 — `{position, branch, stage, stem, element,
  ten_god}`(위치별 오행·십성 포함, `ten_god(day_master, stem)`). frontend는 패널 **하단에 합쳐**
  위치(월지/일지/시지)별로 `{위치} {지장간} [오행 색배지 木(목)] {십성}` 한 줄씩(인라인) 표기.
  예: `월지 중기 갑 [木(목)] [정관]`. 표기 세분 — 텍스트 `{위치} {단계} {지장간}`,
  오행은 범례 색 배지(elementStyle+elementLabel), 십성은 십성 그래프 과다/부족과 동일한
  단일 컬러 인디고 칩(tgBadge).
- types.ts `hidden_only_elements.sources` 타입 string[]→구조체 배열로 갱신.
검증: backend 147 pass·ruff·mypy(element_distribution.py) clean / frontend tsc OK / 라이브 API dict 확인.

### 신강·신약 — 별개 v1 엔진을 '우리 값' 통합형으로 복원 + 보수화(merge-A + C) ✅
- **문제**: v1.3 8성분 엔진(`strength_v1.py`)이 분포/통근/구조 값을 인자로 받고도 **무시하고
  자체 테이블로 재계산**(별개 로직). `side_balance_score`는 죽은 코드(0.0)였음.
- **A. 통합 공식 복원**: `score = clamp(0.35·season + 0.35·root + 0.30·side + structure_mod, 0,100)`.
  season=SEASON_SCORE[season_state], root=rooting.root_score, side=side_balance_score(십성그룹,
  일간 기준 생조/극설 비율), structure_mod=합충형파해/공망. `strength_v1.py` 삭제. 9밴드 복원
  (태신약/태신강 부활 — geokguk `_WEAK/_STRONG`와 정합). side 가중치 사용자값(식상0.60·관성0.90).
- **밴드 임계(사용자 지정)**: 28/34/42/47/53/58/66/75 (상한 inclusive).
- **보완 3종**: 오행구족(표면 5오행 존재, 신강약과 분리) · 오행 편중도(max/min) · '중화이나 편중'
  · 판정 사유(reason). 모델/타입에 신규 필드 추가, 프론트 StrengthPanel에 표시(내부 '구성:' 키 제거).
- **C. 통근 보수화**(rooting.py): 본기(같은 천간)1.0 / **동기(같은 오행 다른 천간)0.85** / 인성0.65.
  뿌리 지지의 **공망·충 reliability**(공망0.60·충0.75·둘다0.45) 추가. → 신약화의 핵심 동력은
  동기 감산이 아니라 reliability(목표 분석과 일치).
- **캡 룰**: `season≤38 and root≤45 and side≤48 → 신약 이상 금지`(오행구족·일부 통근이 점수를
  우연히 끌어올려도 신약 캡). 구조보정(#4)은 root reliability와 **중복 감산 방지로 현행 유지**.
- **결과**: 1980(진태양시 戊辰, 己 일간) **신약**(score 40→**35.5**, root 44.95→32.1로 borderline 탈출).
  골든 8개 밴드는 임계 변경 시 재고정값과 **동일**(통근 보수화가 밴드 불변). 240표본 분포 균형적
  (약39/중26/강35%), 토일간 과편향 없음.
- **cascade**: 1980 밴드 중화신약→신약으로 **용신 土→火**(亥월 한습 → 조후축 우세). yongsin/sinsal/
  fixture/api 테스트를 새 출력으로 재고정. (※ 신약인데 희신 金(설기)이 나오는 등 yongsin 축 가중은
  별도 검토 여지 — strength 범위 밖.)
- 진태양시 정책(09:08→08:49→辰시→戊辰)은 Phase 1부터 의도·골든 락 확인(회귀 아님).
- `structure_analysis.py` Element() type-ignore에 사유 주석(전체 mypy clean).
검증: **backend 146 pass · ruff · mypy 전체 clean(63파일) / frontend tsc OK**.

### 신강약 — 충/공망 이중 감산 제거(역할 분리 '나'') ✅
- **문제**: 같은 巳亥충이 **두 번 감산**됨 — rooting.reliability(巳 ×0.45) + structure_modifier
  `day_master_root_clashed:-4`. 09:40 명식(己巳, 巳 공망+巳亥충)이 score 33.2로 **태신약**(실제 신약).
- **해결(역할 분리)**: 뿌리 지지의 충/공망은 **rooting.reliability가 전담**, structure_modifier에서
  중복 항목 제거 — `only_root_damaged`/`day_master_root_clashed`(root 충) 삭제, 궁성 공망(day/month
  branch void)은 **그 지지가 뿌리면 비적용**(rooting이 처리). structure_modifier는 병존·자형·합화·
  비root 궁성 공망 등 전체 구조만 담당. relation_stability(안정도, 점수 아님)는 충/공망 그대로 집계.
- `RootItem`에 `root_kind`·`reliability` 노출(디버그/검증).
- **결과**: 09:40(己巳) score 33.2→**37.2 신약**(목표 달성), 09:08(戊辰) 신약 유지. 골든 **1건만 변동**
  (india 중화신약→중화, void 게이팅 +4). 나머지 7개 불변. test_structure를 역할 분리로 갱신.
검증: backend 146 pass · ruff · mypy 전체 clean(63파일) / frontend tsc OK.

### 용신 — 억부 신뢰도 공식의 강약 스케일 회귀 수정 ✅
- **문제(회귀)**: 용신 모델 신뢰도가 옛 강약 스케일(-100~+100, 신약=음수)을 전제했는데, 강약 통합이
  0~100(신약=양수)으로 바뀌며 `_support_model`/`_resource_model`의 `0.5+(-score)/120`이 **역전**.
  신약 09:40에서 부일간 conf가 0.19로 붕괴 → "단독 확정 금지"인 조후·격국이 실질 용신을 확정하고
  **신약인데 희신이 金(식상=설기)** 모순. 같은 신약을 옛 -53→conf 0.85, 신 +37→0.19로 검증.
- **(A) 신뢰도 공식 재정의**: 중화(50) 기준 거리로 — 신약 `0.5+max(50-score,0)/60`(cap .85),
  인성 `0.45+…/75`(cap .78), 신강 `0.5+max(score-50,0)/60`. 약할수록/강할수록 conf↑(정상화).
- **(B) 자동 교정**: 억부 정상화로 신약에서 억부축(0.45) 주도 → 09:40·09:08 모두
  **용 土(비겁)·희 火(인성)·기 木·구 水** 부일간형. 식상 희신 모순 제거. (강약 통합 때 발생했던
  "용신 土→火 cascade"가 이 버그의 산물이었음 → 도메인 정답 土로 복귀.)
- **(C) selected_model 일치**: `final.selected_model`/`confidence`를 첫 생성 모델이 아니라 **실제
  top 용신을 만든 모델**로 보고(`useful_candidates[0].model`). india(중화) johu/johu 일치 확인.
- 골든 밴드 불변, 용신만 정합화(신약군 일관 부일간형). 1980 용신 테스트 6건을 土 기반으로 재고정.
검증: backend 146 pass · ruff · mypy 전체 clean(63파일) / frontend tsc OK.

### 용신 검증 질문 — 연도 명시 + 답변 축 정합화 ✅
- **문제①(모호)**: "{연도}년 전후" — 16~18 흐름인지 16→17 변화인지 불명확. 실제 검증 대상은 그 해
  세운 1년임. → `_anchor`로 **{연도}년({간지}·만N세)** 명시, "전후" 제거.
- **문제②(불일치)**: 질문은 "…강했나요?"인데 답은 좋음/힘듦(방향). 채점은 방향(좋/나)으로 용신을
  검증하므로 방향은 유지 필요. → 질문을 **방향 단정 없는 중립 문구**("삶의 흐름은 어땠나요?")로,
  답변은 **방향·강도 1축**(크게 좋아짐~크게 힘들어짐·기억없음) + **영향 영역 멀티(범주)**로 분리.
- 영역을 개별 사건→**범주**(직업·금전·연애/부부·건강·이동·학업·계약/공공)로. `DOMAIN_LABELS` 신설,
  가중치를 `MAJOR_EVENTS`→`MAJOR_DOMAINS`(직업·금전·연애/부부·건강·이동 1.5×)로 교체.
- 프론트 행 라벨 "그 해 흐름"/"영향 영역(복수)", 등급 라벨 방향·강도 표현으로. 채점 로직(방향) 불변.
- 테스트 `selected_events ["취업"]→["직업"]`(범주) 갱신.
검증: backend 146 pass · ruff · mypy 전체 clean(63파일) / frontend tsc OK.

### 용신 검증 질문 — 세운(입춘) 범위 명시 + 군 입대 영역(남성) ✅
- **입춘 경계**: 세운은 양력 1/1이 아니라 입춘(~2/4)에 바뀜 → "2001년"과 세운(辛巳) 불일치. period에
  `range_label` 추가(`get_table().lichun_for_year(Y/Y+1)` KST 변환 → "입춘 기준 2001-02-04 ~
  2002-02-03"). 앵커를 `{year}년({간지}세운·만N세)`로(세운 명시), `CalibrationQuestion.period_range`
  필드 신설, 프론트 질문 아래 회색 서브타이틀로 노출.
- **군 입대/제대 영역(남성 한정)**: 나이 고정(~20)·고회상·관성/신분변화 신호 → 검증 정확도↑. `gender`를
  generate_calibration→generate_questions에 전달, 남성 명식에만 영역 칩 추가. `MILITARY_DOMAIN` 상수,
  MAJOR_DOMAINS(1.5×)에 포함. 여성은 미노출 확인.
- 프론트 영역 칩 `slice(0,9)` 제거(범주 ≤10개 전부 표시).
검증: backend 146 pass · ruff · mypy 전체 clean(73파일) / frontend tsc OK.

### 운(대운·세운·월운·일운) — 천간/지지 분리 + 강약·세분 라벨 ✅
- **문제**: 용신운/기신운을 {천간오행,지지오행} 한 집합으로 묶어 단일 라벨만 냄. 천간(드러남)과
  지지(기반·사건화)의 작동 방식 차이, 지장간 강약이 반영 안 됨.
- **분리 평가**(luck_cycles.py): `_stem_effect`(천간 1오행) + `_branch_effect`(지장간 정·중·여 **가중
  합**으로 강약, 예 巳=戊庚丙→火 +0.8) + `_relation_modifier`(충 −0.15·합변환 ±0.1·공망, ±0.3 제한).
- **가중 점수**: 대운 0.35·천간+0.65·지지, 세운 0.45/0.55, 월·일 0.40/0.60 + 관계.
- **세분 라벨**: pure_yongsin/pure_gisin/**mixed_yongsin_surface**(천용·지기=겉기회·현실부담)/
  **mixed_gisin_surface**(천기·지용=초반압박·기반회복)/partial_*/trigger/neutral + 한글 요약.
- 스키마 `LuckPolarity`(element·type·score·detail) 신설, `LuckPillar`/`DaewoonItem`에
  stem_effect·branch_effect·luck_score·luck_label(_code)·luck_summary 추가. 기존 yongsin_relation/
  alignment은 coarse 도출로 **호환 유지**(기존 테스트 불변).
- 프론트 LuckPanel: 대운표에 세분 라벨 칩 + 천간/지지(↑용신↓기신) + 범례, 세운에 세분 라벨.
- 검증 예(1980 남): 戊子=천용·지기, 己丑=강한 용신운, 甲午=천기·지용. 지장간 가중 테스트 추가.
검증: backend 148 pass · ruff · mypy 전체 clean(73파일) / frontend tsc OK.

### 운 지지 — 공망·충 동태(실속·사건성) 분리 ✅
- **원칙**: 방향(용신/기신)은 유지, **공망=실속·작동력**, **충=사건화·변동성**으로 분리. 운 평가 내에서
  같은 충/공망을 두 번 깎지 않도록 `_relation_modifier`의 충·공망 항을 제거하고 지지 동태로 이관.
- `_branch_dynamics`(luck_cycles.py): 공망 ×0.60(신뢰0.6)·충 ×0.80(트리거+1)·**공망+충 ×0.65**(트리거1.5·
  변동1.5·신뢰0.5). 경우 A/B: 용신지지가 원국 기신을 충거(정리)=트리거↑, 기신지지가 원국 용신 충=변동↑.
  라벨 공망/충발/공망충발 용신운·기신운. `LuckPolarity`에 base_score·is_void·has_clash·branch_label·
  event_trigger·volatility·reliability 추가.
- 검증 예(1980 남, 공망 辰巳): 壬辰=공망 용신운(0.2→0.12·신뢰0.6), 癸巳=공망충발 용신운·원국 기신(水)
  충거(트리거2.5·변동1.5·신뢰0.5), 庚寅=충동 기신운. 프론트 대운표에 동태 라벨(보라) + 범례.
검증: backend 149 pass · ruff · mypy 전체 clean(73파일) / frontend tsc OK.

### 용신 검증 — 운 동태(공망·충)를 검증 기간·채점·문구에 연동 ✅
- **문제**: 검증 기간 선택이 세운을 {천간,지지오행}만으로 거칠게 판정 — 공망/충을 무시해, 공망으로
  muted된 해를 깨끗한 용신해처럼 묻고 사용자가 "별로"라 답하면 모델을 오답 처리할 위험.
- **연동**(period_selector): 원국 pillars를 받아 세운 지지의 **공망(원국 공망지지)·충(원국 충)** 판정.
  `_apply_dynamics`로 expected 보정 — **공망=mixed(절반 반영), 충=volatile(약한 반영)**. **깨끗한
  해(공망·충 없음)에 score +2** → 방향 신호가 또렷한 해를 검증 우선순위로.
- **문구 힌트**(question_generator): 부득이 공망/충 해가 뽑히면 "결과가 지연·무산"(공망)/"이동·변화·
  사건"(충) 회상 단서를 질문에 덧붙임. generate_calibration→select에 pillars 전달.
- 채점(feedback_scorer)은 mixed(0.5·|x|)·volatile(0.3·|x|)을 이미 처리 → 연결만으로 동작.
- 결과(1980 남): 5문항 모두 깨끗한 해(乙未·辛卯·甲午·戊子·丁亥)로 선택됨. 공망 辰/巳 세운은 is_void
  표시·mixed 보정. test_auxiliary_johu는 핵심 불변(보조 단독 확정 금지→primary)으로 갱신.
검증: backend 150 pass · ruff · mypy 전체 clean(73파일) / frontend tsc OK.

### 용신 검증 제출 — 결과 피드백 가시성 수정 ✅
- **증상**: "검증 질문 제출했는데 변화가 없어." 백엔드/엔드포인트/와이어링은 정상(확정·match 등 정상 반환).
- **원인**: 제출 결과가 위쪽 `용신 후보`(YongsinPanel)에만 반영되고, 제출 버튼이 있는 `검증 질문`
  패널엔 로컬 피드백이 없었음. 답변이 부일간형(土)을 지지하면 용신 글자도 그대로라 더더욱 무변화로 보임.
- **수정**(CalibrationPanel, 프론트 전용): 제출 후 **결과 배너**(상태·용신/희신/기신/구신·일치도·근거·
  채택 모델 + "위 패널 반영" 안내), `N/5개 응답` 카운터 + 0개 응답 경고, 버튼 "다시 검증 제출". 상태
  라벨 STATUS_KO 모듈 상수화. uncertain(final None)이면 '근거 부족' 안내.
검증: frontend tsc OK (CalibrationPanel은 기존 client 컴포넌트라 재시작 불요).

### 용신 검증 제출 후 UX — 문항 접고 완료/재시도 ✅
- 제출 후 노출되던 기술 수치(일치도·근거·채택 모델)는 일반 사용자에 불필요 → 제거.
- 제출되면 **문항 영역 전체를 접고**, "답변 반영 완료(결과는 위 용신 후보에 반영)" + **검증 다시 진행**
  버튼만 표시. '다시 진행'은 done 해제로 문항 재노출(이전 답변 유지) → 반복 검증 가능.
검증: frontend tsc OK.

### 용신 후보 박스 — 완료/재시도 내장 + 한신 + 오행 색상 ✅
- 별도 완료 박스가 영역을 크게 차지 → 제거. **제출되면 CalibrationPanel은 숨기고**(submitted prop),
  "답변 반영 완료 + 검증 다시 진행"을 **용신 후보 박스 안**의 컴팩트 바로 이동(onRedo=calibration 해제).
- **한신 추가**: 용/희/기/구에 안 들어간 나머지 한 오행을 계산해 5칸으로 표시.
- **오행 색상**: 5칸에 `elementStyle`(파스텔 오방색) + `elementLabel`(한자+한글) 적용.
- 기술 수치(검증결과 match/근거/모델) 라인 제거.
검증: frontend tsc OK.

### 대운·세운·월운 — 만세력 카드형 + 대운 상세표(교운일) ✅
- **카드형 스트립**(LuckCol/LuckStrip): 칸별 상단(나이/년/월 + 천간 십성) → **천간 박스**(오행색·한자+
  한글) → **지지 박스**(오행색) → 하단(지지 십성·운성). 색은 stem_effect/branch_effect.element.
  대운·세운·월운 각각 가로 스크롤, 현재 구간 강조(대운 index·세운 current_year·월운 current_month).
- **대운 상세 정리** 표(접이): 기존 표를 details로, **용신관계 우측에 교운일 컬럼**(trace.exact_jiao_un_dates).
- **백엔드 보강**: 대운 9→**10**, 세운 5→**10**(기준연−4~+5), `LuckPillar.twelve_unseong` 추가(세운·
  월운 운성), `LuckCycles.current_year/current_month` 추가(카드 강조). 영향 테스트 갱신(대운 10·교운일
  10·세운 10창/乙未 index4·운성).
검증: backend 150 pass · ruff · mypy 전체 clean(73파일) / frontend tsc OK.

### 운 카드 연동 — 대운→세운→월운 선택 + 마진·역순·달력링크 ✅
- **연동 선택**: 대운 칸 클릭 → 그 대운 **세운 10년** 노출, 세운 칸 클릭 → 그 해 **월운 12개** 노출,
  월운 칸 클릭 → **`/calendar/{년}/{월}`** 이동. 기본 선택=현재 대운·현재 연도(강조).
- **데이터**: `DaewoonItem.sewoon`(대운별 10세운) 메인 응답에 선계산. 월운은 양이 커 **온디맨드
  엔드포인트** `POST /api/v2/manse/luck/months {birth, year}` 신설(`manse_service.luck_months` +
  `monthly_luck_for_year`). 프론트 `fetchLuckMonths`로 세운 선택 시 조회·캐시.
- **표시 정리**: 카드 **마진 확대**(strip mt-4·gap-2·여백), **우→좌 오름차순**(배열 역순 렌더),
  **일운 제거**, 선택 칸 인디고 링·현재 칸 노랑 링.
- 테스트: test_daewoon_carries_sewoon(대운별 10세운·운성), test_luck_months_endpoint(12개).
검증: backend 152 pass · ruff · mypy 전체 clean(73파일) / frontend tsc OK.
- **후속 보완**(프론트): 선택 링이 가로 스크롤 컨테이너에 잘리던 문제 → 스트립에 pt/pb 여백.
  최초 진입 시 선택(현재) 칸을 **가운데 정렬**(centerInScroll: 선택 요소를 스크롤 부모 중앙으로,
  페이지 세로 스크롤 불변). 월운 라벨 "월운 (2026)" → **"월운 - 2026년"**.
  검증: frontend tsc OK.

### 교운일 산식 검토 — 현행(생일+절기거리) 방식 확정 ✅ (코드 변경 없음)
- 사용자 제보: 교운일이 "12월 11일경"이어야 하는데 엔진은 11월로 나온다.
- 사용자 제공 참고 구현(`myeongli.py` calc_daewun) 산식을 우리 절기표로 재현 비교:
  | 방식 | 대운수 | 첫 교운일(1980-11-22 09:08) |
  |---|---|---|
  | 참고 파일(생일+절기거리, 달력 사다리, 버림 //3) | 4 | 1985-11-15 |
  | 우리 엔진(생일+절기거리, 선형 ×365.2425, 반올림) | 5 | 1985-11-17 |
  | 절기(절입일=대설) 기준 | (5) | 1985-12-07 |
- **결론**: 참고 파일도 11/15(우리와 같은 「생일+절기거리」 계열, 2일차)로, 12월을 만들지 않음 → 엔진이
  사실상 정합. "12월"은 절기(절입일) 기준 표기의 다른 계열일 뿐. **현행 방식을 정설로 확정**(변경 없음).
- (메모) 참고 파일과의 미세 차이: 대운수 반올림 vs 버림(//3), 교운 선형 vs 달력 시/분 사다리(±2일). 추후
  절기 기준 표기를 원하면 별도 옵션으로 검토.

### 신살 — 표준 명리표 14종 추가 + 패널 정리 ✅
- 패널 제목 "전체 신살"→**"신살/길성, 납음오행"**, 시/일/월/년→**시주/일주/월주/년주**, 영문 intensity 제거,
  각 주 하단에 **납음오행 색배지** 추가(끝 글자 오행으로 색 판별).
- 참고 `myeongli.py`/`constants.py`로 누락 신살 점검(파일은 인코딩 손상 → 역마살 대조로 표준표임 확인 후
  **표준 명리표로 재작성, 각 표 주석 명시**). 추가 14종:
  - 길성(8): 천록귀인(건록)·천주귀인(식신건록)·관귀학관(관 장생)·문곡귀인(문창 충)·일덕·일귀·천의성
    (월지 직전)·천문성(일지 戌亥).
  - 흉살(6): 낙정관살·비인살(양인 충)·격각살(일지+2)·천라지망살(戌亥/辰巳)·고신살·과숙살(년지 삼방)·
    단교관살(월별). (※ 유파 편차 큰 천복귀인·복성귀인·부벽살·혈인살은 깨끗한 표 확보 시 별도.)
- `sinsal_catalog.py`에 표·META, `sinsal_aggregator.py`에 감지 로직 추가. 검증 예(1980 진태양시): 관귀학관·
  고신살·천문성 신규 감지. test_sinsal 2건 추가(감지+표 lookup).
검증: backend 154 pass · ruff · mypy 전체 clean(73파일) / frontend tsc OK.

### 신살 — 12신살 일지 기준 추가(역마 누락 수정) + 협록(夾祿) ✅
- **버그**: 12신살을 년지 기준으로만 산출 → 09:40(己亥일) 시주 巳가 년지 申 기준 겁살로만 잡히고 **일지 亥
  기준 역마살 누락**. 참고 파일은 년지+일지 모두 본다 → 일지 기준 12신살 추가(같은 자리 같은 이름은 1회).
- **협록(夾祿)** 추가: 일간 정록(L)을 두 지지가 L−1·L+1로 끼면 성립(CHEONROK=정록표 재사용). ※ 09:40
  명식(申亥亥巳, 己 정록 午)은 午을 끼려면 巳+未 필요한데 未가 없어 미성립(정상).
- 검증: 09:40 시주 역마살 감지. test_sinsal 1건 추가.
검증: backend 155 pass · ruff · mypy 전체 clean(73파일) / frontend tsc OK.

### 신살 — 위치별 12신살 폐지 + 역마/도화/화개 글자살로 전환 ✅
- 사용자 정책: "일간·연지 중심 항목 + 지지글자(도화류)만 노출". 참고 앱은 위치별 12신살을 펼치지 않고
  역마=寅申巳亥 글자로 본다(申亥亥巳가 전부 역마).
- **변경**: 삼합기준 위치별 12신살(겁살·재살·천살·지살·년살·월살·망신·장성·반안·육해 등) **폐지**. 대신
  **역마살(寅申巳亥)·도화살(子午卯酉)·화개살(辰戌丑未)을 지지 글자살**로 표시(`SASAENG/SAJEONG/SAGO`).
  천문성도 일지→**戌亥 글자(위치 무관)**로. `_twelve_sinsal`/YEOKMA·DOHWA·HWAGAE 제거.
- 결과(09:40 申亥亥巳): 년 금여·역마·천을·현침 / 월·일 고신·관귀학관·역마·천문성 / 시 낙정관살·역마 →
  참고 앱과 일치(낙정관살만 추가, 일간 기준이라 정책상 유지). test_sinsal 갱신.
검증: backend 155 pass · ruff · mypy 전체 clean(73파일) / frontend tsc OK.

### 용신 검증 상태 — localStorage(IndexedDB) 영구 저장 ✅
- 증상: 검증 결과/답변이 React state로만 있어 reload 시 사라짐.
- storage.ts: `saveCalibration/loadCalibration/clearCalibration` + `profileSig`(기준일 제외 안정 키) 추가.
  프로필과 동일 AES-GCM 암호화로 IndexedDB 저장. `clearProfile`에 검증 삭제 포함.
- 복원 정책: **sig(출생) 동일** → 확정 결과(용신 후보) 유지 / **chartId(기준일 포함) 동일** → 답변까지 복원
  (다른 날엔 질문셋이 달라지므로 답변은 미복원·결과만 유지). 제출 시 자동 저장, '등록 정보 초기화' 시 삭제.
- CalibrationPanel: `initialAnswers` 복원(useEffect), `onResult(res, answers)`로 답변 전달.
검증: frontend tsc OK.

### 용신 — 인성과다(印重) 처리 추가(財損印) ✅
- 버그: 인성과다 신강(예 1985-10-29 22:00 辛金, 土 인성 46/55%)을 일반 신강 억부(식상 설기)로 처리 →
  용 水·희 木·火 한신. 인성과다는 식상(土극水로 무력)이 아니라 **재성으로 인성 제어(財損印)**가 정석.
- `_resource_overload`(인성 비중 ≥35% 且 인성 > 비겁×1.5) 감지 → **재성용신형(財損印)** 모델
  (용 재성·희 관성·기 인성·구 비겁·한 식상). 인성과다면 '인성 약신' 병약 모델은 역효과라 제외.
- 밴드 처리 확인: 78.56=극신강(신강 계열) 정상 → 신강 분기 → 인성과다 감지 라우팅.
- 결과: 1985-10-29 → 용 木·희 火·기 土·구 金(한신 水, 사용자 기대 木火 일치). australia(인성40·극신강)도
  재성용신형 전환. 골든은 밴드/격국만 락이라 불변, 테스트 통과.
검증: backend 155 pass · ruff · mypy 전체 clean(73파일).

### 용신 — 인성과다(財損印) 중화신강 조건부 확장 ✅
- 신강 계열(신강/태신강/극신강): `_resource_overload`(인성≥35% 且 >비겁×1.5) → 곧바로 재성형(財損印).
- **중화신강은 곧바로 보내지 않음**: 엄격 조건 `_resource_overload_strict`(인성≥40% 且 >비겁×2.0) +
  `_johu_or_disease_active`(한습·조열 월령 또는 파격 2건+) **비우선**일 때만, 재성형을 '경쟁 후보'로
  조건부 추가(확정 아님 — 축가중·신뢰도 경쟁에 맡김).
- 검증 스캔(1970~2000): 중화신강·strict 인성과다 24건 중 재성형 발동 2건 / 조후·병증·격국 디퍼 22건.
  극신강 1985-10-29(용木 희火) 회귀 유지.
검증: backend 155 pass · ruff · mypy clean(73파일).

### 용신 — 조후 게이트 버그 + 재다신약 인성 배제(水 오용 2건 수정) ✅
- 증상: ① 2018-01-09 12:50 창원(辛金 丑월 극신강) 희水, ② 1955-09-05 음력(甲木 戌월 재다신약) 희水.
- ① 조후 게이트 버그: `월령오행 ≠ 土` 조건이 丑(한겨울)·未(한여름)까지 조후에서 제외(辰·戌만 빼면 됨).
  → 게이트 제거(_johu_model이 亥子丑/巳午未만 모델 생성). 추가로 **기후역행 배제**(`_climate_harmful`):
  한습(亥子丑)+火<22% → 水, 조열(巳午未)+水<22% → 火를 용·희에서 강등.
- ② 재다신약(`_jaeda_sinyak`: 재성>인성×3 且 재성>비겁): 인성용신형(_resource_model) 제외 + 인성 원소를
  용·희에서 강등(재극인·무근).
- 결과: ① 용木 희火, ② 용木 희火 — 둘 다 水 완전 배제. 회귀 스캔(1960~2005): 조열월 水 용/희 보존 90건,
  한습월 水 배제 101건(비대칭 정상). 골든 japan(극신약·조열) 용水 보존.
검증: backend 155 pass · ruff · mypy clean(73파일).

### 용신 — 과다그룹 극파 케이스 일괄 보강(군겁쟁재·살중) ✅
- 재다신약과 대칭인 "과다 그룹이 극하는 원소를 용·희로 미는" 패턴을 756명식 감사로 발굴.
- **A. 비겁과다 신강(군겁쟁재)**: `_bigyeob_overload`(비겁≥35% 且 >재성×1.5) → 군겁쟁재형
  (용 관성·희 식상·기 비겁·구 인성·한 재성) + 재성 강등. 비겁과다→재성 46→11건.
- **B. 관살과다 신약(살중)**: `_officer_heavy`(관성≥30% 且 >비겁×1.5) → 살인상생형
  (용 인성·희 비겁 방조·기 재성), 뿌리 강하면 식신제살 경쟁. 관살과다→비겁용신 60→11건
  (비겁은 방조 희신으로 전환=의도).
- 회귀: 재다신약·인성과다·한습 모두 유지. 잔여(인성과다 임계 경계 29·중화신강 경계·상관견관)는 후순위(C·D).
검증: backend 155 pass · ruff · mypy clean(73파일).

### 용신 — 식상과다 신약(印制食) 처리: 관성 기신 오분류 수정 ✅
- 증상: 1985-04-18 16:00 사천(丁火 신약, 식상 土 40 태과, 비겁 火 0 무근) → 水(관성)가 기신.
- 원인: 부일간형(용 火=비겁)을 1순위로 잡는데 비겁이 무근(火=0)이라 부적절. 그 모델이 관성(水)을
  기신(일간 압박)으로 분류. 식상과다 신약은 인성으로 제식상(木극土)+생일간(印制食)이 정석.
- `_output_heavy`(식상≥35% 且 >비겁×1.5) → 인성제식상형(`_output_overload_model`:
  용 인성·희 비겁(방조)·기 식상(병)·구 재성·**한 관성=관인상생**). 비겁은 식상을 생해 악화하므로
  부일간형 자체 제외.
- 결과: 사천 → 용 木·희 火·기 土·구 金, **水=한신(길신)**. 기존 6개 명식(재다신약·인성과다·한습·살중·군겁) 유지.
검증: backend 155 pass · ruff · mypy clean(73파일).

### 용신 — 극파 무력 배제 일반화(후순위 C·D 마무리) ✅
- 개별 demote(재다신약·군겁쟁재)를 일반 규칙으로 통합: 용/희 원소가 그것을 극하는 그룹에게
  압도(>3배·최강군)당하면 강등. 단 **비겁(일간 동기·방조)·조후 필요 원소(한습 火/조열 水)는 보존**.
- 효과(1950~2010 감사): 인성과다→식상 29→6, 비겁과다→재성 11→0, 식상과다→관성 11→6.
  잔여 대부분은 의도(비겁 방조=살인상생, 인성=조후 보호).
- 명식 7건(식상과다·재다신약·인성과다·한습·살중·군겁) 회귀 유지. 골든 밴드/격국 불변.
검증: backend 155 pass · ruff · mypy clean(73파일).

### 용신 — 극신약 중화·길 처리 4종(종격 세분·가종·통관·유통) ✅
- 배경: 극신약/태신약에서 중화·길로 보는 특수구조(종격·살인상생·통관·유통) 반영 점검 →
  종격은 일반 플래그뿐(세분 X), 통관은 경고만, 가종/유통 미반영으로 확인 → 4종 보강.
- **① 종격 세분 명칭**: 진종 성립 시 압도 세력으로 종재격(財)·종살격(殺)·종아격(兒) 라벨
  (`_FOLLOW_SUBTYPE`). 검증: 庚申庚申甲申庚午→종살격 金 / 戊戌戊戌甲戌戊辰→종재격 土 /
  戊辰戊辰丙辰戊戌→종아격 土.
- **② 가종격(假從)**: `root_score`가 비겁통근+인성생조 합산이라 종격 진위를 세력비로 재판별.
  진종=무근+무인 / **가종=무근+약인(인성 12~28%)**. 가종은 억부(印·比) 1차 유지 + 종격 병기 +
  검증 경고(집계 제외). 검증: 사천 1985-04-18(乙丑庚辰丁亥戊申, 丁)→1차 印制食 木 유지·가종아 土 병기.
- **③ 통관용신형**: 상극 두 세력(각 25%+)에서 통관 오행(a生M·M生b)이 약하면(<15%) 약신 후보로
  승격(병약 축, is_auxiliary). 검증: 甲寅戊辰甲寅戊戌→木→火→土, 통관 火 모델 생성.
- **④ 유통(流通) 점수**: 상생 5고리 충족률(`flow_circulation` 필드). 신약+원활(≥4고리·4종+)이면
  "유연·적응형·신약 완화" 정보성 메모(용신 선택 불변). 검증: 1980→5/5 smooth.
- 정답지 문서 신규: `doc/yongsin_special_cases_test_cases.md`. 회귀 가드: 1980 부일간형(용 土) 불변.
검증: backend 160 pass(+신규 6) · ruff · mypy clean(73파일) · frontend tsc OK.

### 프론트 — 태블릿·PC 폰트 전반 확대(≥641px) ✅
- 목적: 밀집 패널(사주판·운·달력)의 작은 글씨 가독성 확보. 폰트 크기만 키우고
  여백/레이아웃 spacing(rem)은 불변. **모바일(≤640px)은 기본값 유지.**
- `frontend/app/globals.css`에 `@media (min-width:641px)` 한 블록 추가. 명명 유틸
  `text-xs`(12→13)·`text-sm`(14→15)과 임의 px값 `text-[9px]/[10px]`(→12)·
  `text-[11px]/[12px]`(→13) 오버라이드. 60여 호출처 무수정.
- (이력) 최초 모바일(≤640px) 확대로 적용했다가, 검토 후 태블릿·PC(≥641px) 적용으로
  분기 반전. 모바일은 기존 크기로 환원.
- 우선순위: Tailwind 유틸은 비(非)`@layer` 출력이라 globals.css 말미의 규칙이 출처 순서로
  승리(서빙 CSS 바이트 위치로 확인). 헤드리스 브라우저 부재로 레이아웃 육안 검증은
  실기기(터널 URL)로 위임.
검증: dev 서버 CSS 컴파일·서빙 OK · 미디어쿼리/오버라이드 적용 확인.

### 운(대운·세운·월운·일운) 카드에 신살/길신/흉성 표시 ✅
- 목적: 대운·세운·월운 각 카드의 십이운성 아래에 구분선을 긋고, 그 운의 간지가 불러오는
  신살/길신/흉성을 간단히(단색 회색) 표시.
- **운의 신살 산출**: 기존 신살 로직은 원국 4기둥 전용 → 운의 간지를 새로운 자리(位)로 보고
  원국 기준점(일간·월지·년지·일지)+운 간지 자체에 대조하는 `sinsal_for_luck()` 신설
  (`sinsal/sinsal_aggregator.py`). 단일 간지에 적용 가능한 신살만 포함: 역마·도화·화개·현침·
  천문성(글자), 천을·태극·문창·학당·홍염·금여·암록·양인·천록·천주·관귀학관·문곡·낙정관·비인
  (일간 기준), 월덕·천덕·천의성·단교관살(월지), 고신·과숙(년지), 격각살(일지),
  귀문관살·원진(운지↔원국지 쌍). 제외: 일덕·일귀(일주 고정)·천라지망·협록(원국 구조 별).
- **분류·정렬**: 카탈로그 polarity로 길신(positive)·흉성(caution)·신살(neutral) 분류,
  표시는 길신→신살→흉성 순. polarity는 툴팁(`길신·OO`)으로 노출.
- **스키마**: `LuckSinsal(name, polarity)` 모델 신설(`shared_types/sinsal.py`),
  `LuckPillar`·`DaewoonItem`에 `luck_sinsal: list[LuckSinsal]` 추가. `_luck_pillar()`와
  대운 생성부에서 부착 → 대운·세운·월운·일운 전부 자동 적용.
- **프론트**: `LuckCol`에 `sinsal` prop 추가, 십이운성 아래 `border-t` 구분선 + 신살명을
  text-[9px] 회색으로 줄바꿈 표시(없으면 미표시). 대운·세운·월운 3개 호출부에 전달.
  (text-[9px]는 ≥641px에서 12px로 확대되어 태블릿·PC 가독성 확보.)
검증: backend 160 pass · ruff clean · mypy clean(변경 4파일) · frontend tsc OK · build OK ·
  end-to-end(1990-05-15 샘플) 대운/세운/월운/일운 신살 산출 확인.

#### 후속: 운+원국 짝-완성 신살 추가(협록·천라지망) ✅
- 배경: 협록(夾祿)·천라지망(天羅地網)은 "짝을 이뤄야 성립"하는 신살이라 최초엔 운에서 제외했으나,
  원국이 한쪽을 보유하고 운이 나머지를 가져오면 완성되는 대표 케이스 → 귀문관살·원진의 쌍 완성과
  동일 논리로 `sinsal_for_luck()`에 보강.
- 협록: 일간 정록(L)의 양 협지(L-1·L+1) 중 운이 한쪽·원국이 다른 한쪽이면 성립(길신).
- 천라지망: 천라(戌亥)·지망(辰巳) 짝 중 운이 한쪽·원국이 나머지면 성립(흉성).
- (일덕·일귀는 일주 간지 자체 지칭이라 운엔 계속 미적용.)
검증: 협록(운 乙丑+원국 卯)·천라지망(운 乙亥+원국 戌) 발동 + 짝 없을 때 미발동 확인 ·
  backend 160 pass · ruff/mypy clean · 백엔드 --reload 자동 반영.

### 간지달력 — 일운(십성·십이운성·신살/길신/흉성) 오버레이 ✅
- 목적: 간지달력 각 날짜 셀에 그날 일운의 십성·십이운성·신살(길신/흉성 포함)을 사용자 원국 기준으로 표시.
- 아키텍처: 달력은 stateless(원국 모름)·캐시(revalidate 3600) → 캐시 모델 유지 위해 일운을
  클라이언트에서 온디맨드 오버레이. 기존 `luck/months` 패턴 그대로 일운 경로 신설.
- 백엔드: `daily_luck_for_month()`(luck_cycles, `_daily` 공개 래퍼) + `manse_service.luck_days()` +
  `POST /api/v2/manse/luck/days`(LuckDaysRequest: birth/year/month) → `list[LuckPillar]`.
  LuckPillar에 stem/branch_ten_god·twelve_unseong·luck_sinsal이 이미 있어 그대로 활용.
  label='YYYY-MM-DD'라 달력 셀과 날짜로 매칭(달력 day_ganji와 일운 간지 일치 확인: 丙午/丁未/戊申).
- 프론트: `fetchLuckDays(profile, year, month)`(api.ts). `CalendarGrid`가 IndexedDB 프로필 로드 후
  일운 조회→날짜맵 오버레이. 프로필 없거나 실패 시 기본 달력만(graceful).
  - 셀: 절기 슬롯을 고정 높이(h-[15px])로 둬 그 아래 `border-t` 구분선이 셀마다 같은 줄에 정렬.
    구분선 아래 천간·지지 십성(편관·정관) → 십이운성 → 신살(단색 회색, polarity는 툴팁).
  - 요일 헤더 `sticky top-0`(여백 pt-2) + bg-white로 상단 고정 → 스크롤 시 요일 가시성 확보.
  - 상세 패널(DayDetail)에도 십성/십이운성/신살 행 추가.
검증: backend 160 pass · ruff/mypy clean(변경 파일) · frontend tsc OK · build OK ·
  luck/days 엔드포인트(:8000 직접·:3000 리라이트) 200 · 30일 일운 산출 확인 · 백엔드 --reload 반영.

### 일주복음(伏吟) — 운 간지가 일주와 동일할 때만 표시 ✅
- 정책: 현대 실무상 복음은 대운·세운·월운·일운에서 일반 표시하지 않으나, 일주복음만은 활용.
  운(대운/세운/월운/일운)의 간지가 일주 간지와 완전히 동일할 때만 "복음"을 표시한다
  (년·월·시주 대조 복음은 제외).
- 백엔드: `sinsal_for_luck()`에서 정렬 후 `stem==일간 and branch==일지`이면
  `LuckSinsal(name="복음", polarity="caution")`를 목록 맨 앞(index 0)에 삽입 → 신살 영역 최상단 고정.
- 프론트: 만세력 카드(Panels.tsx `LuckCol`)·간지달력 셀/상세(CalendarGrid.tsx `SinsalChips`·`DayDetail`)에
  `sinsalTitle()` 헬퍼 도입 — 복음 칩은 전용 툴팁(`복음(伏吟) · 운의 간지가 일주와 동일 — 엎드려
  신음하는 형국으로 정체·반복·내적 침체를 의미`)과 강조색(amber-600)을 적용, 그 외 신살은 기존
  `분류 · 이름` 유지. 백엔드가 0번 인덱스로 고정하므로 두 화면 모두 자동으로 최상단 표시.
검증: 갑자 운(==일주 甲子) → 복음 최상단 / 을축 운(!=일주) → 복음 미발동 확인 ·
  ruff clean · frontend tsc OK. (mypy의 structure_analysis.py:86 unused-ignore는 본 변경과 무관한 기존 건.)

### 만세력 — 우측 중앙 플로팅 목차(ToC) 버튼 ✅
- 목적: 만세력 결과 페이지 우측 중앙(상하 기준)에 노션 스타일 반투명 목차 이동 버튼 배치.
- 컴포넌트: `components/manse/FloatingToc.tsx`(신설) — `fixed right-0 top-1/2 -translate-y-1/2`.
  평소엔 섹션마다 얇은 가로 막대(dash)만 반투명 노출, hover 시 `bg-white/70 backdrop-blur` 패널로
  펼쳐져 섹션 라벨 목록 표시. `IntersectionObserver`(rootMargin -45%/-50%)로 현재 섹션 강조(scroll spy).
  hover 상태는 onMouseEnter/Leave + 좌측 `pl-10` 투명 영역으로 안정화(absolute hover-loss 회피).
- 노출 기준: `lg:block`(≥1024px) — 본문 `max-w-3xl`(768px)과 겹치지 않는 폭에서만 표시, 그 이하 숨김.
- 페이지: `app/manse/result/page.tsx` — 각 섹션을 `<div id="sec-*" class="scroll-mt-4">`로 감싸 앵커 부여,
  `TOC_ITEMS`(10개: 진태양시·사주원국·형충회합·신살길성·오행십성분포·격국·신강신약·용신·용신검증·대운세운월운)
  렌더 순서와 일치. 클릭 시 `scrollIntoView({behavior:'smooth'})`.
검증: frontend tsc OK · 프로덕션 build 성공(lint/type 통과).

### 신살 표기·운 서브타이틀·ToC 모바일 노출 정리 ✅
- **신살 표기**: `도화살` → `도화`로 단축(이웃한 `홍염`과 일관). 카탈로그 키
  `sinsal_catalog.py:36` + 글자살 탐지 2곳(`sinsal_aggregator.py` 40·240, `cat.CATALOG_META[name]`
  조회·설명문 `f"{branch} {name}(글자살)"`에 함께 반영). 검증: 잔여 참조 0 · ruff clean ·
  sinsal pytest 9 pass.
- **운 서브타이틀 문구**(`Panels.tsx` LuckStrip hint): 대운 "대운 선택시 해당 세운이 표시됩니다" /
  세운 "세운 선택시 해당 월운이 표시됩니다" / 월운 "월운 선택시 간지달력으로 이동합니다".
- **ToC 모바일 노출**: `FloatingToc.tsx` — 기존 `hidden lg:block`(≥1024px 전용)이 모바일에서
  ToC를 숨기던 문제 해결 → `block`(전 화면 노출). 모바일은 호버 불가라 접힌 막대를 `<button>`으로
  바꿔 탭→펼침, 항목 선택·바깥 `pointerdown` 시 닫힘 추가. 위치는 화면(뷰포트) 끝 `right-0` 유지.
검증: frontend tsc OK.

### 삼형(三刑) 성립 정책 — 인사신 일지 조건 + 운(運) 형충회합 검출 ✅
- 정책(웹 조사 반영): 인사신(寅巳申·무은지형)은 **원국 일지(日支)가 寅·巳·申 중 하나일 때만** 삼형
  성립(일지 관여설). 축술미(丑戌未·지세지형)·자형·무례지형은 **위치 무관**(2글자 이상 모이면 성립).
  형은 합·충과 달리 위치 제약이 약하고, 운에서 글자가 들어와 완성될 때도 성립한다는 통설을 채택.
- 원국: `relations.py` 삼형 루프에 인사신 한정 `day_branch ∈ {寅,巳,申}` 게이트 추가(축술미 영향 없음).
  → 기존 형충회합 섹션(Panels.tsx)에 즉시 반영.
- 운(運): `luck_cycles.py:_relations_to_chart`에 형(刑) 계열 신규 검출 추가 — 삼형(인사신 일지 조건
  동일)·자형·무례지형, 그리고 파·해도 함께(기존엔 충·육합·천간합·삼합기여만). `relations_to_chart`는
  현재 프론트 미렌더 상태라 **데이터만 확정, 운 칸 표시는 후속 작업**으로 보류(사용자 결정).
- 조사 메모: "일지 글자 포함을 성립요건으로 못박는" 합충은 인사신 외 표준에 없음. 가장 유사한
  위치 게이팅은 자형·자묘형의 인접 필수, 삼합의 왕지(월지) 조건 — 단 본 엔진은 전부 존재기반 검출.
검증: pytest 164 pass(원국 2·운 2 신규) · ruff clean · mypy(변경 파일 0건;
  structure_analysis.py:86 unused-ignore는 기존 무관 건).

### 형충 커버리지 보강 — 운 방합 + 무례지형 인접 게이트 ✅
- 운(運) 합충형파해 완전화: `_relations_to_chart`에 **방합기여** 추가(기존 충·육합·천간합·
  삼합기여·형·파·해에 더해). 이제 운에서 합충형파해 전 분류 검출.
- 무례지형(子卯·자묘형): **원국은 인접(연-월·월-일·일-시)할 때만 성립**으로 게이트
  (`relations.py` `_ADJ_PAIRS`). 격각(연-일·월-시·연-시)은 가운데 글자에 막혀 흉살로
  잡지 않음. 자형(self_punishment)은 **위치 무관 유지**(정책 확인). 운 무례지형은 외부
  자리이므로 존재기반 유지(운이 나머지 글자를 데려와 발동).
- 보류: 삼합/방합/육합 **합화(化) 위치 가중**은 별도 — 현 엔진은 binary month_supports+
  root_exists 모델. 왕지/월지 가중 임계값 모델로의 튜닝은 후속 협의(용신·강약 영향).
검증: pytest 166 pass(무례지형 인접 2·자형 1·방합 1 신규) · ruff clean · mypy 동일.

### 합화(化) 판정 — 왕지/월지 가중 임계값 모델 ✅
- 동기: 기존 `_transformation`은 `month_supports`·`root_exists`가 **이진값**이라 "월지가 왕지냐",
  "통근이 얼마나 두텁냐"가 합화에 반영 안 됨. 사용자 제안(가중 점수제)으로 교체.
- 모델(`structure_analysis.py`):
  `score = (0.30 + 0.35·월령등급 + 0.25·통근비율 + 왕지가산)·합종류계수 − 0.15·blocker`
  - 월령등급 wol: 월지 오행 일치 1.0 > 계절 일치 0.7 > 없음 0.0.
  - 통근비율: `_target_root_ratio` — rooting 배점(자리 월35·일30·시18·년12 × 위계 정1.0·중0.6·여0.35)
    재사용, 월지 정기(35)=1.0 정규화.
  - 왕지가산 +0.15: 월지가 왕지(子午卯酉)이고 합화 오행과 일치.
  - 합종류계수: 방합 1.12(계절세력)·삼합/반합/천간합 1.0·육합 0.80(월령 없으면 化 어려움).
  - confirmed = score≥0.58 **and 월령지원 and blocker 없음**(완전 합화는 월령 전제). possible(가합)=
    score≥0.40 and blocker 없음(통근만으로도 기운 인정). confidence=score.
- 호환성: 기존 confirmed 전제(월령 지원·blocker 없음)를 유지해 회귀 최소화. 부수로
  structure_analysis의 장기 미사용 `type: ignore`(WORKLOG 반복 언급분) 정리.
검증: pytest 167 pass(회귀 0) · ruff clean · **mypy clean**(3개 핵심 파일 무이슈).

### 용신 역할 배정(용·희·기·구·한) 기신축 생극 분할 재설계 ✅
- 문제: 기존 `final`은 후보 모델들의 역할 투표를 useful/unfavorable 두 테이블로 **교차 집계**해
  산출 → 모델들이 같은 오행을 정반대로 투표하면(병약형 용신 木 vs 억부형 기신 木) 한 오행이
  희신·기신에 동시 등장하고 다른 오행이 누락됨(예: 희木·기木·水 누락). 또 오행 **과다/부족**이
  길흉에 미반영(2015 인성 木 과다인데 한신으로 잘못 분류).
- 도메인 정리(웹 조사 + 사용자 스펙): 표준 용희기구한은 용신 기준 생극 1:1이나, **희신은
  "용신을 생하는 오행"만이 아니라 "과다 기신을 설기하는 오행"도 포함**. 억부에서 용신과 기신은
  항상 극 관계이므로 기신 후보는 {극용신, 용신극} 둘뿐.
- 알고리즘(`candidates.py` `_classify_roles`): 용신=모델 파이프라인 1등(유지). 기신=
  {극용신·용신극} 중 '병'이 큰 쪽(분포 과다 비율 + 일간을 극하는 관성 + 흉 투표). 그러면
  나머지는 생극으로 결정 — **구신=생기신, 희신=기신설기(기신이 생하는 오행), 한신=잔여**.
  단 설기 희신이 스스로 과다(비율≥0.33)면 생용신으로 강등. → 항상 5오행 1:1 분할(중복·누락 불가).
- 단일 출력(str) 유지 → 스키마·프론트·캘리브레이션 무변경(다중 오행안은 변수 과다로 폐기).
- 부수: 캘리브레이션 문항 0개(저연령 등) 시 빈 화면 대신 사유 1문장 안내(`CalibrationPanel.tsx`).
검증: 2015(丙·신강)=용金 희火 기木 구水 한土(인성 木 과다=기신, 火 설기 희신) ·
  1980 골든(己·신약)=용土 희火 기木 구水 한金 보존 · 2015 잠금·분할 불변 테스트 추가 ·
  pytest 전체 통과 · ruff clean · mypy clean.
- 강약별 보강: **극일간(관성) 가중은 신약군에만** 적용(신강에선 관성=제어=길이라 제외) → 강군
  기신은 과다 인성/비겁이 됨. 또 **태신강·극신강에서 설기 희신이 일간(비겁)이면 한신과 교체**
  (일간 추가강화 회피; plain 신강은 비겁이 과다할 때만). 대표 8차트 명리 정합 확인
  (2010 극신강 희金식상 · 1975 태신강 희土재성 · 신약군 용·희=비겁·인성/기=관성).

### 시간 보정 UI — 균시차 토글·부호 표시 ✅
- 균시차는 출생시각의 고정 천문값이라 **항상 원값 보고**(`true_solar_time.py`); 진태양시에만
  옵션(`apply_equation_of_time`) 반영(미사용 시 0으로 더함). 11월 +13·3월 −13 등 부호는 천문적
  정상(KASI 관례: 시태양시−평균시).
- 프론트(`Panels.tsx`/`result/page.tsx`/`lib/api.ts`): '균시차 사용' 체크박스를 시간보정 카드
  **타이틀 우측**에 배치(기본 사용), 토글 시 `time_options`로 재계산. 경도보정·균시차 **부호
  명시(+/−)**, 미사용 시 밝은 회색(비활성) 노출.
검증: frontend tsc OK · 라이브 토글(균시차 ON 진태양시 02:38 / OFF 02:51) 확인.
