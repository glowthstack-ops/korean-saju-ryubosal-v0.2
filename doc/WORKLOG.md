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
