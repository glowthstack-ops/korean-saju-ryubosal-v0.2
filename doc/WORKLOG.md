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

### 만세력 서비스 캐시·chart_id 안정화 + 시간옵션 전 API 일관 적용 ✅
- **chart_id 연 단위 안정화**(`manse_service.py` `_chart_id`): 프론트가 매 방문
  `reference_date=오늘`을 보내는데 기존엔 전체 날짜를 해시 → 다음날 chart_id가 바뀌어
  저장된 검증(캘리브레이션) 답변이 무효화되던 문제. 질문셋은 기준 **연도**에만 의존하므로
  연 단위로만 해시. 대운방향 옵션(`daewoon_direction_basis`/`manual_daewoon_direction`)도
  식별자에 포함(차트 정체성 누락 보완).
- **calculate() 인프로세스 LRU 캐시**: 검증 피드백·월운·일운 요청이 매번 전체 파이프라인
  (분석+질문 생성+운 기둥 100여 개)을 재계산하던 비용 제거. 키는 BirthInput 전체 canonical
  JSON(연 단위 chart_id가 아님 — 세운/월운 anchoring은 전체 날짜 의존), OrderedDict LRU
  64건 + `threading.Lock`(FastAPI 스레드풀 안전). 신규 테스트 6건
  (`tests/integration/test_manse_service_cache.py`): 연내 동일 chart_id/연 경계 상이·
  파이프라인 1회 실행·전체 날짜 키·LRU 상한.
- **시간옵션(균시차 토글) 전 API 일관 적용**: 기존엔 `calculate`만 `time_options`를 받아
  월운/일운/검증 채점이 화면 차트와 다른 기준으로 계산될 수 있었음.
  `api.ts` `profileToBirthInput`에 timeOptions 통합 후 `submitCalibration`/`fetchLuckMonths`/
  `fetchLuckDays` 전부 전달. 토글 상태는 `storage.ts` localStorage(`ryubosal:applyEquationOfTime`,
  비민감 boolean이라 비암호화)에 저장 — 결과 페이지 마운트 시 복원, 간지달력(일운, 별도
  라우트)도 같은 기준으로 조회. LuckPanel은 결과 재계산 시 이전 옵션 기준 월운 캐시 재시드.
- **API 에러 메시지 개선**(`api.ts` `postJSON`): FastAPI 에러 본문 `detail` 문자열을
  사용자 메시지로 노출(없으면 기존 기본 메시지, 상태코드 유지).
- **천을귀인 대상 지지 응답 포함**: `SinsalAnalysis.cheoneul_targets`(일간 기준, 원국 성립
  무관 항상 제공) 신설 — 프론트 `Panels.tsx`에 하드코딩 중복돼 있던 CHEONEUL 표를 응답값
  우선 사용으로 전환(구버전 응답 대비 fallback 표 유지).
검증: backend pytest 177 pass(캐시 6·천을 타깃 1 신규) · ruff clean · mypy(변경 파일 0건;
  기존 7건은 미수정 테스트/structure_analysis 잔존 건) · frontend tsc OK · 프로덕션 build 성공.

### mypy 잔존 7건 정리 — None-guard 보강 ✅
- `structure_analysis.py:_transformation`: "caller ensures non-None" 주석을 실제
  `assert rel.transform_element is not None`로 형식화(런타임 검증 + mypy 내로잉).
- 테스트 None-guard: `test_yongsin.py`(special_case `detail` 2곳),
  `test_luck.py`(甲午 stem/branch_effect, `base_score`), `test_calibration.py`
  (`yongsin_analysis` 2곳) — Optional 필드 접근 전 `assert ... is not None` 추가.
검증: mypy clean(95파일 0건) · ruff clean · pytest 177 pass.

### v2.2 착수 — 루트 CLAUDE.md를 v2_2 가이드와 병합 ✅
- `doc/v2_2/`(통변 서비스 v2.2 설계 문서 11종 + CLAUDE.md) 검토 완료.
- 스택 불일치 확인: 문서는 TS/Node/zod/src 기준(v1 코드베이스 가정), 본 리포는
  Python FastAPI+pydantic. **사용자 확정: Python 백엔드 통합 구현**(zod→pydantic,
  src/types→backend/packages/shared_types 번역, 문서의 스키마·규격 내용은 그대로 준수).
- 루트 `/CLAUDE.md` 업데이트: 기존 운영 규칙(체크리스트·금지사항) 전부 유지 +
  프로젝트 요약/절대 원칙 12개/설계 문서 인덱스(doc/v2_2/docs 경로)/Python 번역
  코드 컨벤션·목표 디렉토리 구조 추가. "현재 상태" 절은 실제 리포 기준으로 교정
  (Python 만세력 엔진·FastAPI·Next.js UI 완성, DB 미도입). 원본은 doc/v2_2/CLAUDE.md 유지.
검증: 문서 변경(코드 무변경) — 게이트 해당 없음.

### v2.2 Phase 0 — 공유 타입 + saju_engines 어댑터/간지달력 생성기 ✅
- **신규 패키지 `backend/packages/saju_engines/`**(pyproject packages.find·ruff src 등록).
  만세력 엔진은 일절 수정하지 않고 어댑터·생성기만 추가(기존 엔진 수정 금지 원칙).
- **T0.1 공유 타입**(`shared_types`, 문서 camelCase→snake_case 번역, 스키마 내용 유지):
  - `events.py`: EventKey(taxonomy 전체 26종, wealth 하위 5종 포함)·EventType·
    EventPolarity·Confidence·Signal·EventCandidate(score 0~100 클램프).
  - `intent.py`: QueryType(Q1~Q14)·Domain·SubjectKind/Mode·CompanionRelationType·
    TimeScope·Granularity·OutputFormat·SubjectRef·TimeRange·Constraints·OutputStyle·
    IntentJson·ParsedMessage. (간지 RelationType과 충돌 회피 위해 인간관계용은 'Companion' 접두.)
  - `ganji_calendar.py`: GanjiLevel·RelationType(13종, 엔진 한글 접두사와 1:1)·GanjiRef·
    RelationHit·GanjiCalendarEntry.
  - `engine_io.py`: ManseChart(신규 엔진 입력 계약, docs/02 E0) + ChartPillar·
    FourPillarsChart·DaewoonPeriod·BirthMeta.
- **T0.3 어댑터**(`adapter.py`): `ManseV2Result`→`ManseChart` 1:1 투영. 원국 간지/일간/
  공망/대운표/신살(자리별)/성별(male·female·unknown→M·F·U) 매핑. 쌍둥이 미구현이라
  chart_variant='original'/twin_shift=0 고정(미구현으로 차단·오류 금지 원칙).
- **T0.4 간지달력 생성기**(`ganji_calendar.py`): 엔진의 표시용 관계 문자열
  (`relations_to_chart`/`gongmang_activation`)을 구조화 `RelationHit`로 변환. 성립 판정은
  엔진이 이미 했으므로 재계산하지 않고 파싱·보강만(엔진=SSOT). 충/육합/파/해/무례지형/
  공망3종은 원국 자리 해소, 천간합은 원국 천간 자리, 삼합·방합 기여는 완성 오행 + 국 구성
  원국 지지를 공유 상수 테이블에서 보강, 삼형/자형 처리. `calendar_entries_from_result`로
  대운/세운/월운/일운 일괄 변환(levels 필터 지원). 미인식 접두사는 조용히 스킵.
- **T0.2 사전 파이프라인 골격**: `backend/dictionaries/`(README, 규칙·목표 구조) +
  `backend/scripts/validate_dictionaries.py`(UTF-8/BOM·JSON 파싱·reviewed:bool 플래그 검사,
  재귀 탐색, 종료코드).
- **루트 CLAUDE.md**: 디렉토리 구조 절에 이미 saju_engines 반영됨.
검증: pytest 194 pass(어댑터 4·간지달력 8·validate 6 신규) · ruff clean · **mypy clean(105파일)**.

### v2.2 Phase 1 — 사전 데이터 MVP (T1.1~T1.6) ✅
- **생성 원칙**: 기계적 사실(십성표·지장간·오행 생극·관계 참여 글자·결과 오행)은 엔진
  상수에서 프로그램 생성해 수기 오류 차단(엔진=SSOT, 테스트로 일치 고정). 명리 매핑·
  가중치(eventDomains·baseScore·score·domains 키워드)는 **전 항목 reviewed:false 초안**
  — 사용자 검수 후 true 전환(docs/07 Phase 1 워크플로).
- **T1.1 common/ 4종**: stems(10, 일간별 십성표 10×10) · branches(12, 지장간 본중여+가중치) ·
  ten_gods(10, 그룹·도메인 초안) · elements(5, 생극).
- **T1.2 relations.json 48항목**: 천간합5(합화 오행 포함)·육합6·삼합4·방합4·충6·삼형2
  (인사신/축술미)·무례지형1·자형4·파6·해6 + 패턴형 4(공망활성·복음·병존·간여지동 —
  participants=[] + pattern 설명). id는 docs/05 형식(rel_甲己合 등).
- **T1.3 taxonomy.json**: EventKey **25종** 전체 1:1 커버(중복 없음, 테스트 고정) +
  progress/instant/hybrid 분류 초안. (이전 기록의 "26종"은 오기 — 실제 25종.)
- **T1.4 events/**: career_change.json 7신호(정관합+기신 → 강제 이동 docs/05 회귀 기준
  케이스 포함) · relocation.json 6신호(역마+충, 공망활성, 대운교체 — docs/03 graphScope).
  signal 스키마는 docs/05의 tenGod/relation/favorability에 shinsal·daewoonTransition
  키 확장(docs/02 Signal.type 어휘와 정합).
- **T1.5 favorability_rules.json**: 용(+0.2)/희(+0.1)/기(−0.2)/구(−0.15)/한(0.0 조건부)
  5규칙 + docs/05 예시(기신×정관 −0.25) 1규칙.
- **T1.6 `saju_engines/dictionaries.py`**: 파일별 pydantic 스키마(camelCase alias,
  extra=forbid) — EventKey/EventPolarity/EventType enum 검증, score 0~1 범위,
  signal 최소 1조건, 패턴형 participants/pattern 상호 보완. **dict:lint**: relation id
  중복 / 기신·구신인데 positive(용·희인데 negative) / 같은 신호 상반 이벤트 동시
  강유발(≥0.7) / 동일 신호 중복 정의. `scripts/validate_dictionaries.py`가
  generic → validate → lint 3단계 실행.
- 주의(검수 필요 표시): polarity 어휘는 docs/05 예시("forced_or_burdensome")가 아닌
  docs/02 EventCandidate 표준("negative_or_forced")으로 통일 — 문서 간 불일치 발견분.
검증: pytest 207 pass(Phase1 13 신규) · ruff clean · mypy clean(107파일) ·
  validate 스크립트 실데이터 9파일 통과.

### v2.2 Phase 2 — Event Graph + Scoring (T2.1~T2.5) ✅
- **shared_types/graph.py**: GraphNode/GraphEdge(docs/04 Node·EdgeType)·EventGraph(semver)·
  EvidencePath·EvidenceBundle.
- **T2.1 graph_builder.py**: 사전 → 이벤트 후보 그래프 컴파일. 오행(생극)·천간·지지·십성
  노드 + 관계(rel_*, 참여글자 combines_with/conflicts_with/punishes 엣지 + eventDomains
  triggers 엣지 weight=baseScore) + 판정 노드 4종(용·희·기·구신) + 해석 규칙 노드
  (events/<domain>.json 매핑 → supports/triggers) + 금기 규칙 4종(windfall 당첨 단정 금지
  등 — 절대 원칙 3·8). `scripts/build_event_graph.py`: validate+lint 통과 후에만 빌드.
  스냅샷 `compiled/event_graph_v1.0.0.json`(131노드/272엣지) git 체크인.
- **T2.2 graph_retrieval.py**: 인메모리 인접 리스트 GraphIndex. graphScope(EventKey 목록)
  역방향 triggers 탐색(기본 5-hop), 신호→이벤트 정규화 경로 + supports/contradicts +
  prohibitions(금기 항상 첨부) + interpretation_hints 출력. 전체 검색 금지 준수.
- **T2.3 event_scoring.py**: 결정론 EventScorer — ① RelationHit→relations.json 매칭
  (쌍/3자/패턴 인덱스) base_score ② favorability_rules 보정(**유입 글자 오행 기준** 판정,
  docs/04 예시 정합 — 합화 결과 오행은 "성립 시 전환 가능" 단서로 부기, 합화 판정은
  Phase 2.5) ③ events/* 신호 매핑(십성·관계·용기신·신살·교운 AND 조건) ④ (period,event)
  합산 → 0~100 클램프 ⑤ 계층 필터(세운 score≥70 또는 Top5).
- **대운 교운기 가중(사용자 실측 피드백)**: 교운일 중심 **첨도 높은 정규분포형** 영향도
  `exp(-(|Δ일|/365)^1.0)`(라플라스형, beta<2=첨도↑) — `daewoon_transition_weight()`.
  교운일은 luck_cycles.trace.exact_jiao_un_dates 사용. 상수는 초안, 실테스트 조정 예정.
- **T2.4**: `EventScorer.readable_path()` — evidence path 노드 ID → 한글 경로
  (예: 甲辰 세운(2024) → 甲 → 甲己合 → 기신 → 이직·직업 변화).
- **T2.5 회귀 픽스처 11케이스**(tests/regression/test_event_scoring_cases.py):
  갑기합+정관+기신 → career_change 상위(docs/05 기준)·강제성 신호 존재·contract 동반·
  역마충 relocation·evidence path 구조·클램프·계층 필터·windfall 금기 첨부·
  retrieval 경로·교운 분포 형태(중심 1.0/단조감소/뾰족)·교운 신호 실반영.
  절대 점수가 아닌 **상대 순위·신호 존재·극성** 고정(가중치 조정에 견디는 계약).
검증: pytest 218 pass(Phase2 11 신규) · ruff clean · mypy clean(113파일) ·
  그래프 빌드 스크립트 실행 성공.

### v2.2 Phase 2.5(1차) — 상호작용 탐지기 전수 + LuckComposite + 전용 DB 분리 ✅
- **DB 분리(사용자 요구: v1과 비충돌)**: v1은 saju-db-1(5432)·saju-redis-1(6379) 사용 중 —
  v2는 루트 `docker-compose.yml`로 **별도 컨테이너(saju-v2-db)·별도 호스트 포트(5433)·
  별도 볼륨(saju-v2-pgdata)**, 이미지 pgvector/pgvector:pg16. 접속은
  `SAJU_V2_DATABASE_URL`(backend/.env.example, .env는 gitignore). psycopg 의존성 추가.
- **relations.json 보강(docs/09 2장 필수 범위)**: 천간충 4(甲庚·乙辛·丙壬·丁癸) ·
  원진 6(子未·丑午·寅酉·卯申·辰亥·巳戌, 기본 활성) · 암합(패턴형, **enabled:false** —
  유파 차이로 기본 비활성, 사전 플래그로만 활성화). RelationItem에 enabled 필드(기본 true).
  총 59항목. 그래프 빌더도 신규 타입 반영(천간충 참여자=천간 노드, 비활성 관계 미수록)
  → 스냅샷 재빌드(141노드/312엣지).
- **T2.5.1·T2.5.2 `interactions.py`**: 풀(pool) 기반 전수 탐지기 — 천간합/충, 육합,
  삼합(3자+**반합, 왕지 포함 플래그**), 방합(+반합), 충, 형(삼형+**부분형**·상형·자형),
  파, 해, 원진, 암합(비활성 스킵). **다자 소스 혼합 성립**(예: 원국 申+세운 子+일운 辰 =
  申子辰 삼합) + 참여 소스 기록. 구조 플래그: 공망활성(전실/충발/합해소)·복음·
  **반음(천극지충)**·병존(원국 인접). 관계 글자쌍은 relations.json 단일 소스
  (Phase 1 테스트가 엔진 상수와 일치 고정).
- **T2.5.3 `precompute.py`+`precompute_store.py`**: 레벨별(natal/대운/세운/월운/일운)
  LuckComposite 산출 — 레벨 레코드는 그 레벨 소스가 참여한 상호작용만(P01~P11 분할),
  parentContext(상위 운 간지) 동반, 도메인 신호(favorability 보정+반합 0.6 감쇠 초안).
  PG 저장소: upsert/get/list(dict_version 필터 필수)/구버전 무효화/대상 무효화/
  day 보존 정리(과거 90·미래 400일). `migrations/001_luck_composites.sql`(docs/09 DDL).
- **해석 결정(검수 대상, 문서 미정의)**: ① natal 레코드 대표 간지=일주 ② favorability
  단일값은 레벨 간지의 천간 오행 기준 ③ EventKey→Domain 초안 매핑 ④ 원진의 그래프
  노드 분류=해 계열(docs/04 NodeType에 원진 없음).
- **보류(다음 단계)**: T2.5.4 갱신 스케줄러·T2.5.6~7 Topic Builder·T2.5.8 LLM 래퍼 —
  대상(subject) 저장 인프라 선행 필요.
검증: pytest 237 pass(탐지기 13·precompute 6·저장소 라이브 1 신규 — **전용 DB 기동 후
  실제 왕복/무효화/정리 검증**) · ruff clean · mypy clean(119파일) · v1 컨테이너 무변경.

### v2.2 Phase 2.5(2차) — 대상 영속화 + 갱신 스케줄러 + LLM 토큰 가드 + Topic Builder 골격 ✅
- **subjects 인프라**(`migrations/002_subjects.sql`, `shared_types/subject.py`,
  `saju_engines/subject_store.py`): self/동반자 최소 영속화(별칭·관계·출생정보 JSONB·
  is_minor·구독). 활성 대상(docs/09 1장) = 구독 중 OR 최근 30일 대화(last_interaction_at).
  E14 전체(별칭 학습·인라인 인물·쌍둥이 변형)는 Phase 4 확장.
- **T2.5.4·T2.5.5 `precompute_scheduler.py`**: 경계 갱신을 **ensure-current 방식**으로
  구현 — 운 period_key가 경계(자정/입춘/절입/교운)를 지나면 자연히 새 키가 되므로
  "현재 기준일 레코드 누락 보충"이 곧 T1/T2 갱신. T0=on_subject_upsert(전체 무효화+
  재계산), T2=daily_batch(활성 대상 보충+day 보존 정리), 비활성=lazy_get,
  사전 버전 변경=on_dict_version_change(구버전 전체 무효화). 만세 계산 함수는
  주입(compute: BirthInput→ManseV2Result) — 엔진→서비스 역의존 차단.
- **T2.5.8 `llm_guard.py`**: docs/09 8장 한도표 6행 그대로(chat 6k/1.2k ·
  compare 8k/1.6k · parser 2k/300 · 섹션 5k/3.5k+4,500자 · 정합성 8k/500).
  입력 토큰 호출 전 측정→초과 시 TokenBudgetExceeded(Context Reduction 재실행 유도),
  **thinking 비활성 강제**, 보수적(과대) 토큰 추정(ASCII 4자/tok·비ASCII 1자/tok,
  카운터 주입 가능), LLMCostLedger 원가 집계.
- **T2.5.6 Topic Builder 골격**(`shared_types/topic_context.py`,
  `saju_engines/topic_builder.py`): TopicContext 표준(docs/09 5장 — findings/
  timeSeries/rankedResults/traitShifts/groupAggregation/evidence/styleRules/budget,
  Finding 등 세부 필드는 문서 미정의라 최소형) + **M01~M15 레지스트리 전수 등록**
  (15종 외 추가 금지, 미구현 모듈은 NotImplementedError) + **M07 career 구현**
  (composite career 신호 시계열 합산 → Top5 findings 확정, 압축 간지 동반,
  단정 금지 스타일 + chat_single 예산).
- 보류: M03(trait_mapping.json 필요)·M10 이사 S1~S10(region_elements/housing_rules) ·
  M15(format_slots.json) — 전용 사전 신설 필요, 후속 단위.
검증: pytest 255 pass(가드 6·M07 6·스케줄러 라이브 6 신규 — daily_batch 멱등/월 경계
  보충/lazy/버전 무효화 실 DB 검증) · ruff clean · mypy clean(128파일).

### v2.2 Phase 2.5(완결) — M03·M10·M15 + 전용 사전 6종 ✅
- **사전 6종 신설**(전 항목 reviewed:false — 도메인 검수 대상):
  `templates/format_slots.json`(일일7/주간5/연간8 고정 슬롯 — docs/02 E9 전체 규격),
  `trait_mapping.json`(W_natal 1.0·W_daewoon 0.45·W_year 0.25, 천간 1.0·본기 0.7,
  십성→성향 어휘 10종), `calendar/direction_rules.json`(용신 오행→길방, 통설 기반),
  `calendar/son_eomneun_nal.json`(음력 끝자리 9·0 규칙), `region_elements.json`
  (지역오행 — **명리 표준 없음, 자체 기준 초안 10개 지역, 검수 전 출시 금지**),
  `housing_rules.json`(buy 문서+재물 / jeonse·monthly 문서 / 신축·구축 0 보정 고정).
- **M03 personality_traits**(docs/09 6장 계산식 전체): effectiveDist = natal×1.0 +
  대운기여×0.45 + 세운기여×0.25. favorability는 분포 미조정, quality_flag(발현 질)로만.
  대운(DW:)·세운 단위 TraitShift(dominant/rising/fading) + MBTI 고정 유형화 금지 스타일.
  natal 십성 분포는 T0(force_analysis.ten_gods.distribution)에서 extras로 공급.
- **M15 lifestyle**: format_slots 슬롯 **전부** findings로 채움(축약 금지). 카테고리
  5점수(work/money/relationship/health/decision) = 50 중립 ± 부호화 신호 합. 연간
  상·하반기 집계, 좋은날/주의할날 상·하위 추출.
- **M10 relocation_composite(T2.5.7, S1~S10 전체)**: `relocation.py` RelocationResolver —
  S1 구성원 월 시계열 → S2 그룹 집계(householder_primary 0.5/0.3/잔여균등 ·
  balanced · protect_weakest + 구성원 충돌 경고) → S3 월 후보(상위+macro 게이트) →
  S4 일 후보 → S5 방위 적합(미지정 시 8방위 분리 산출·단일 답 강제 금지) +
  region_fit(동일 1.0/생 0.8/미등재 0.5 중립) → S6 주거 보정 → S7 손없는날(음력 9·0,
  korean-lunar-calendar 재사용)·기신+충 회피일 → S8 주말 제약 → S9 체인 기본형
  (이사일 역산 30~90일 전 계약 창) → S10 부분점수 5종 합성 랭킹.
  shared_types/relocation.py(RelocationQuery/Result — docs/09 7장).
- 디스패치: build_topic_context(..., **extras) — T0 데이터 필요 모듈은 extras로 주입.
- 부수: 사용자 커밋분 잔여 게이트 정리(candidates.py 줄길이 2, test_calibration
  import 정렬+None-guard — 로직 무변경).
검증: pytest 270 pass(M03 3·M15 2·M10 5 신규) · ruff clean · mypy clean(131파일) ·
  사전 validate 15파일 통과. **Phase 2.5 전체 태스크 완료.**

### v2.2 Phase 3 착수 — T3.3 Execution Planner + T3.8 비분석 라우트 ✅
- **shared_types/execution_plan.py**: ExecutionPlan(docs/03 B4 — intent·eventType·
  engineCalls 순서 보장·dictionaryScope 분할 로드·graphScope·perSubject·policy_route).
- **T3.3 `planner.py`**: queryType별 **고정 템플릿**(LLM 무관여, 동일 intent → 동일 plan
  결정성 테스트 고정). Q1 대운스캔→세운필터→과거검증 요약 / Q2 도메인→Topic 모듈
  (M07/M09/M10/M11/M12/M01/M15) / Q3 Scoring→Timeline→Manifestation→Advice /
  Q4 macro→월적합→일후보→리스크→캘린더→현실제약→랭킹(+방위/시진/체인 분기) /
  Q5 역방향+evidence / Q6 M13(다중 대상 per_subject + chat_compare 예산) /
  Q7 선택지별+excludeOptions / Q8 T0 / Q9 M13 pairwise / Q10 remedy 체인.
  공통 마무리: graph_retrieval→context_reduction→llm. graphScope=docs/03 C 표 +
  명시 eventKey 합집합. dictionaryScope=docs/05 분할 로드.
- **T3.8 비분석 라우트**: Q11 terminology(사전+예시) / Q12 claim_recheck(재검산+
  cases.jsonl 적재) / Q13 empathy_first(엔진 미호출) / Q14 fixed_policy(엔진·LLM 모두
  미호출 — 고정 템플릿 응답). 분석 파이프라인 미진입 테스트 고정.
- **Phase 3 잔여(다음 단위)**: T3.1 Query Parser(경량 LLM+룰 폴백) · T3.2 Broad Query
  Rewriter · T3.4 Context Reduction · T3.5 LLM 입력 계약 직렬화기(docs/06) ·
  T3.6 다중 intent 파싱 · T3.7 시점 파서 18패턴 — **docs/08(실로그 2,255건 카탈로그)
  정독 후 진행**(파서 작업 전 필독 + 골든 테스트 30케이스 원천).
검증: pytest 282 pass(planner 12 신규) · ruff clean · mypy clean(134파일).

### v2.2 Phase 3(2차) — 룰 기반 파서·시점 18패턴·리라이터 + 골든 테스트 ✅
- **docs/08 정독 완료**(실로그 2,255건/353명 카탈로그): 시점 누락률 79%(텍스트 직접
  파싱 필수) · 단답 후속 11% · 다중 질문 7.5% · 대상 혼동이 최다 치명 오류.
- **T3.7 `time_parser.py`** — C1~C18 전수: 일 상대어(글피 +3 등재)·주·월(당해 연도
  기준, "내년" 명시 시만 +1)·연·반기·상대기간(N개월 안에)·데드라인(C9)·사용자 구간
  (C10 "26-27/28-30")·외부 앵커(C11 투표일)·나이 변환(C12, 만나이 기준 출생연도+나이)·
  인생 단계(C13)·대운 단위(C14)·역검증(C15 "맞춰봐")·즉시성(C16)·시진(C17)·
  단위 지정(C18 granularity_override). 결정론(같은 텍스트+기준일 → 같은 TimeRange).
- **T3.1·T3.6 `query_parser.py`** — 룰 기반 폴백(운영 1차는 경량 LLM, 본 모듈이 검증
  기준): Q1~Q14 분류(우선순위 고정: 메타/로또번호 Q14 → 정정 Q12 → 용어 Q11 → 감정
  Q13 → 비교 Q6 → 선택지 Q7 → 택일 Q4 → 개운 Q10 → 역검증 Q5 → 시기 Q3 → 명식 Q8 →
  관계 Q9 → 분야 Q2 → 종합 Q1) · 다중 질문 분리(B4, 물음표 단위+조각 병합) ·
  다중 도메인 결합(B5) · 인라인 생년월일(A6/A7: '91년 10월 31일 오후 3시'+'1998.07.23
  여자', 양/음력·성별) · 관계어/별칭 대상(A2/A9: 엄마·남편·1호) · 대상 모드(본인제외/
  랭킹/궁합/합산) · 출력 형식(B14: 100점/순위/동화체) · 조건(B7 가정형·B8 분기
  시나리오·방위·주말 제약·C9 계약→이사 체인) · **단답 후속 슬롯 상속(B2/B3:
  prev_intent 주입 시 10자 이하+시점만 → 도메인·대상 상속)**.
- **T3.2 `rewriter.py`** — B3 판정표 전체: 대상 모호 → 확인 질문(추측 실행 금지) /
  시점·분야 모두 없음 → too_broad+실행 가능 제안 3종 / 분야만 → 기본 기간
  (연애 6·직업 12개월 등 defaults 초안) / 둘 다 → ok.
- **골든 테스트**(`tests/regression/test_golden_questions.py`) — docs/08 H장 체크리스트
  31케이스 통과(A2×C1, A3×A6, A5×E×C11, A7, A9×B5, A10, A11×C9, B2×F2, B3, B4, B5,
  B6, B7×D2-1, B8~B14, C9, C10×A2, C12, C13, C15, C17×D2-5, C18, D2-12, G6 + 리라이터
  2종). 대화 이력 필요 3건(F4 누적참조·F7 반복감지·A13 프로필)은 **xfail로 명시 보류**
  (Phase 4 Conversation Layer).
- 발견(검수 필요): D-1의 employment(취업 308건)는 EventKey taxonomy에 없음 —
  잠정 career_change 매핑, taxonomy 추가 여부 사용자 결정 필요.
- **Phase 3 잔여**: T3.4 Context Reduction + T3.5 LLM 입력 계약 직렬화기(docs/06 정독
  필요) + LLM 파서 어댑터(가드 경유).
검증: pytest 313 pass + 3 xfail(골든 31 신규) · ruff clean · mypy clean(138파일).

### v2.2 Phase 3(완결) — T3.4 Context Reduction + T3.5 LLM 입력 계약 ✅
- **docs/06 정독 완료**: LLM 입력 4요소 필수(압축 간지달력·이벤트 후보+점수·근거 경로·
  해석 제한 규칙), 전체 간지달력/사전/원시 그래프 투입 금지.
- **`shared_types/llm_input.py`(T3.5)**: LlmInput 표준 스키마 전체 — birthChartSummary·
  calendarContext(대운/선택 세운/선택 월운/택일 일운)·eventCandidates(간지+대운 맥락
  필수)·evidence(반대 근거 동반)·styleRules·persona(Phase 8.5 전 빈 블록)·sectionMode·
  budget. 점수→표현 강도 매핑표(85+/70/55/40 구간) 수록.
- **`context_reducer.py`(T3.4)**: docs/03 B5 규칙 전체 — ① 간지 계층 압축(대운은 장기
  질문이면 전체·아니면 선택 후보의 대운만, 세운은 선택분만+선별 사유, 월운은 선택 세운
  내, 일운은 택일에서만) ② graphScope evidence만 ③ 사전 미적재(Planner 소관)
  ④ Top5+score≥40 임계(40 미만=언급 생략 구간) ⑤ 후보마다 간지·대운 맥락 강제.
- **직렬화기**: docs/06 '좋은 입력 예' 형태의 한국어 사실 서술([원국]/[간지달력(압축)]/
  [이벤트 후보 — 재계산 금지]/[근거 경로]/[지시] 섹션, 지시는 데이터와 분리).
  `serialize_with_guard`: llm_guard로 호출 전 토큰 검증, 초과 시 후보 3개·경로 1개로
  1회 재축소 후 재검증(그래도 초과면 예외 전파).
검증: pytest 320 pass + 3 xfail(reducer 7 신규) · ruff clean · mypy clean(141파일).
**Phase 3 코드 태스크 완료** — 잔여: LLM 파서/통변 실호출 어댑터(운영 연동 시),
Phase 4 Conversation Layer(xfail 3건 해소).

### v2.2 MVP 파이프라인 통합 — /api/v2/chat + Claude API 어댑터 ✅
- **llm_guard 수정**: thinking 비활성을 명시적 {"type":"disabled"}가 아닌 **파라미터
  생략**으로 강제(최신 모델은 미지정=비활성, 일부 모델은 명시적 disabled가 400 —
  claude-api 스킬 레퍼런스 확인). request_params에 thinking 추가 금지 명문화.
- **`llm_client.py`**: Claude API 어댑터 — 모든 호출이 가드 경유(호출 전 토큰 차단,
  max_tokens 상한), usage(input/output_tokens)를 원가 장부에 적재. 모델 env 설정:
  SAJU_V2_LLM_MODEL(통변 기본 claude-opus-4-8) / SAJU_V2_PARSER_MODEL(경량 파서
  기본 claude-haiku-4-5). 표현 원칙 시스템 프롬프트 고정([필수 준수] 블록 —
  수치 재계산 금지·변화 에너지 표현·미제공 정보 처리). anthropic>=0.40 의존성 추가.
- **`chat_service.py`**: MVP 오케스트레이션 — 파서(룰) → 정책 라우트(Q11~Q14 고정
  응답, 엔진·LLM 미호출) → too_broad/대상 판정(추측 실행 금지) → 만세 계산(캐시) →
  스코어링+계층 필터 → Graph Retrieval(plan graphScope만) → Context Reduction+직렬화
  +가드(초과 시 too_broad 안내) → LLM 서술. **API 키 미설정 시 dry-run 폴백**
  (직렬화 본문 반환 — 개발/검증 경로).
- **`routers/chat.py`**: POST /api/v2/chat {birth, question, today?, dry_run?} →
  ChatResponse(status/answer/intents/assessment/prompt_preview/input_tokens).
- E2E 7건: 이직 질문 dry-run(4요소 섹션+한도 내 토큰), intent 메타 왕복, 로또 번호
  거부+대안, 감정 공감 우선, too_broad 제안 3종, 모의 LLM answered, 키 미설정 폴백.
검증: pytest 327 pass + 3 xfail · ruff clean · mypy clean(145파일).
**"단일 질문 → 정확한 풀이" MVP가 API로 동작**(실 LLM 호출은 ANTHROPIC_API_KEY
설정 시 자동 활성).

### v2.2 Phase 4 — Conversation Layer (T4.1~T4.6) ✅
- **`shared_types/conversation.py`**: ConversationState(A1 — 활성 대상/토픽/시점/이벤트/
  누적 조건/앵커/직전 intent·결과/반복 카운트/엔티티), TrackedEntity(A2 — 7종,
  **claim 포함**), LinkResult(A3 — 7종 linkKind), SubjectResolution(A0 — unresolved·
  correction·time_unknown), ResultSummaryRef.
- **`conversation.py`(T4.2~T4.4)**: 턴 처리 순서 = ①Subject Resolution(대상 우선,
  절대 원칙 7) ②Question Linking(룰 1~4순위 — 참조어 확정/단답 슬롯상속/조건누적·
  세분화/challenge; 5순위 LLM 분류기는 운영 연동 시) ③파서 호출+슬롯 병합 ④상태·
  엔티티 갱신. 대상 해소: A8 본인 복귀 · A9 별칭→companion_id(미등록은 unresolved —
  추측 금지) · A6/A7 인라인 임시 인물(Entity Tracking 필수 등록) · **F4 누적 참조**
  ("앞서 물어본 2명" → 과거 턴 임시 인물 재호출) · A10 정정(re실행 신호 + Q12 강제) ·
  A13 생시 미상(3주 모드 신호). **F7 반복 감지**(정규화 동일 질문 → repeat_count).
- **T4.5 claim 엔티티**: `register_system_results()` — 시스템 답변의 명리 판정/이벤트를
  assistant 발 엔티티로 등록(수 턴 뒤 "라고 했잖아?" 이의 → challenge 라우팅 검증).
- **T4.1 영속화**: `migrations/003_conversation.sql`(threads, state JSONB) +
  `conversation_store.py`(save/load/delete — 라이브 왕복 검증).
- **T4.6 통합 시나리오**(docs/07 명시 3종 전부): ①연애운→그 사람은?→결혼 가능성
  (도메인 상속+assistant 엔티티) ②내일운세→모레→글피(시점 체인) ③1호 2호 둘 다
  (별칭 매핑+합산 모드) + F4/F7/A10/A13/claim/영속화 10케이스.
- **골든 테스트 xfail 3건 전부 해소**(F4·F7·A13) — Conversation Layer 실통과로 교체.
  골든 34케이스 전수 통과(xfail 0).
검증: pytest 340 pass(Phase4 10+골든 갱신 3) · ruff clean · mypy clean(149파일).

### v2.2 — /api/v2/chat 멀티턴 연결(Conversation Layer 통합) ✅
- chat_service: `thread_id` 지정 시 ConversationStore에서 상태 복원 →
  ConversationEngine.process_turn(대상 해소·슬롯 상속·반복 감지) → 모든 응답 경로에서
  상태 저장. 미등록 별칭 → need_subject 확인 질문. 응답 상위 이벤트를 claim/event
  엔티티로 등록(T4.5 — 이의 재검산 대비). ChatResponse에 thread_id/turn_no/repeated 추가.
- 라우터: ChatRequest.thread_id(선택) — 미지정 시 기존 단발 경로 그대로.
- E2E: "올해 연애운"→"5월은 어때?" 도메인 상속 + 동일 질문 3연속 repeated=True
  (라이브 DB 검증).
검증: pytest 342 pass · ruff clean · mypy clean(149파일).

### v2.2 Phase 5 — 예측 엔진 확장 (T5.1~T5.7) ✅
- **사전 4종 신설**(전 항목 reviewed:false): `stage_mapping.json`(신호 유형 16종 →
  awareness/exploration/action/decision 단계 — 합=인지, 충=행동, 문서/결정 룰=결정),
  `event_forms.json`(이벤트별 발현 형태+확률, prob 합 ≤1), `remedy.json`(D-3 6분기:
  시기회피/주의행동/기질보완/구조보완/오행생활화/민속비방 + 의료·법률·투자 고지 고정),
  `relation_profiles.json`(관계 7유형별 분석 축·가중 — 부부/연인/부모자식/동업/동료/
  상사/친구).
- **`prediction.py`**: E4 Timeline(월운 신호→단계 매핑, **Activation Window**,
  interest/action/completion 분리 점수 — 월 후보 없으면 None) · E3 Event Form
  (form 사전 + Self Profile 실행력 보정 ±0.05, 합 ≤1 정규화) · E5 Self Profile
  (십성 그룹·강약 기반 결정 스타일/위험 감수/실행력/4축 — **모든 축 근거 첨부**,
  성격검사화 금지) · E6 Manifestation(event+profile+context 결합, **context 부재 시
  modifier 0+confidence 하향** — 차단 금지) · E8 Advice(단계별 행동 조언 + remedy
  주의 + 이벤트별 고지 자동 첨부).
- **`relations_engines.py`**: E13 Compatibility — 관계 유형별 축 가중(relation_profiles),
  일지 글자쌍 관계(relations.json 단일 소스: 육합 85/충 30/형·해·원진 38/파 45),
  용신 상호 보완(상대 일간 오행이 내 용신 +20/기신 −15), 일간 생극 공통 축, 패턴/갈등
  추출. E12 Competition — 판정일 강도(일운 0.5+월운 0.3+세운 0.2 가중 + 이벤트 신호),
  relative_gap(clear≥15/narrow≥5), **당락 단정 금지 고정 문구** + no_hour 모드
  (시각 미상 공인 — 비교는 지원하되 품질 표시).
- shared_types/prediction.py: docs/02 출력 스키마 7종 전체.
검증: pytest 354 pass(Phase5 12 신규) · ruff clean · mypy clean(153파일) ·
  사전 validate 19파일 통과.

### v2.2 Phase 6 — Past Validation 신뢰 엔진 (T6.1~T6.4) ✅
- **T6.1 `past_validation.py`**: 과거 N년 이벤트 후보 — **Phase 2 스코어링 역방향
  재사용**(세운 창 −4~+5년을 10년 간격으로 이동시켜 전 구간 커버, calculate 캐시 활용).
  콜드리딩 방지 규칙(docs/07 리스크 3): 연도당 후보 ≤2건 · score≥70 엄격 임계 ·
  **evidence path 필수**(스키마 min_length=1로도 강제) + 사람용 근거 경로 동반
  ("2009 입학 ← 정관 활성" 형태의 원천).
- **T6.3 Confidence Calibration**: 맞춘 비율 → 신뢰도(0~1) → 표현 강도 3단계
  (normal ≥0.6 / conservative ≥0.3 / very_conservative) — 미래 예측 서술 보수화에
  반영(docs/02 E7). 피드백 0건이면 conservative 시작.
- **T6.2 `cases_store.py`**: cases.jsonl 적재/조회 — docs/05 행 스키마(camelCase:
  caseId/signals/predictedEvent/actualEvent/time/matched/notes) 그대로. 회귀 테스트·
  가중치 보정 자료의 누적 원천(절대값 신뢰는 사례 축적 후).
- **T6.4 API**: POST /api/v2/past-validation(후보 — 기간 미지정 시 성년~작년) +
  /feedback(확인 적재 + CalibrationOutcome 반환) — 온보딩 "미래 예측 전 과거 검증
  먼저" 플로우의 서버 측 연동(docs/01).
검증: pytest 361 pass(Phase6 7 신규) · ruff clean · mypy clean(158파일).

### v2.2 Phase 7 — 생활 운세 & 택일 (T7.1~T7.7) ✅
- (M10 이사 S1~S10·M15 lifestyle은 Phase 2.5에서 선구현 — 본 단계는 일반화·보강.)
- **사전 3종 신설**(reviewed:false): `purpose_profiles.json`(목적 7종별 5단계 가중 +
  옵션 — 이사: 월운+일운+손없는날 / 계약: 일운 0.5+충돌 회피 / 결혼: 세운·월운 안정 /
  수술: 일운 회피 엄격 / 개업: 대운·세운 0.35 / 복권·투자: **일운 비중 축소+변동성
  경고**), `calendar/holidays.json`(고정 양력 8종 + 음력 명절 정의), `calendar/
  avoid_days.json`(금기일 룰 3종 — 기신+충 / 형 활성=수술·계약 / 원진=혼사).
- **T7.3 `date_selection.py`**: 계산 순서 고정(docs/02 E10) — macro(세운)→월운 적합→
  일운 실행→**금기일 필터(E10-b, 룰 사전+사유)**→손없는날·공휴일·요일(E10-a)→
  현실 제약(T7.4 "가능한 날 중 가장 좋은 날")→목적별 가중 합산 랭킹. 부분점수 5종 +
  risk_score(충·형 수 기반) + recommendation 3단계.
- **T7.7 시진(時辰)**: 12시진 적합도 — 시지 오행 × 용신(동일 1.0/생용신 0.8/기본 0.5),
  "로또 사러 가기 좋은 시간대"(C17) 대응.
- **T7.6 표현 제한 검증**: windfall/speculation 목적 → 변동성·과몰입 경고 +
  "당첨·수익 단정 불가/투자 조언 아님" 고정 첨부(전 후보), 로또 번호 직접 요청은
  여전히 정책 거부(G6 — /api/v2/chat 정책 라우트), advice 고지 고정 — 전부 테스트 고정.
검증: pytest 371 pass(Phase7 10 신규) · ruff clean · mypy clean(161파일) ·
  사전 validate 22파일 통과.

### v2.2 Phase 8.5 — 사용자 프로필 & 페르소나 (T8.5.1~T8.5.11) ✅
- **docs/11 전체 규격 그대로 구현**(필드·enum·분류 임의 변경 없음).
- **사전 3종 신설**: `occupation_taxonomy.json`(O01~O18 닫힌 분류 + 물상 매핑 +
  formBias(E3)/contextModifiers(E6, ±10 한도) — 전 항목 reviewed:false),
  `persona_lexicon.json`(endings 4종·difficulty_rules 3종은 규격 그대로, 성별3×연령5
  =15조합 어휘 초안 reviewed:false), `honorific_presets.json`(7종 + 금칙어 필터).
- **`shared_types/profile.py`**: BasicProfile(윤달·시간모름·대략시간대·해외출생·
  multipleBirth·displayName), ExtendedProfile(occupation O-ID 패턴 강제·residence·
  maritalStatus 7종('별거' 포함)·children), PersonaConfig 5축(speech 유효 조합
  jondae→haeyo|hapsyo / banmal→banmal_chae|hagae를 pydantic으로 강제), ChartVariantState.
- **`profile_engine.py`**: T8.5.1 BasicProfile→BirthInput(보정은 기존 엔진 재사용,
  3주 모드·대략 시간대 후보 2~3개 병기) · **T8.5.10 쌍둥이 시주 조정**(시지 n-1칸
  전진+시두법 재계산, **wrap 시 일·월·년주 불변 + 원 일간 기준 시두법**,
  TWIN_WRAP_CONVENTION 플래그, 변형 상태 original/twin_adjusted, 안내 문구 고정
  템플릿 양방향) · T8.5.3 occupation→E3 formBias(O14+relocation→'출장·파견')/E6
  reality_context · T8.5.4 marital 분기(기혼 연애운→배우자 우선+확인, 이혼·사별→재혼,
  미입력 '미혼' 가정 금지) + 자녀 동반자 등록 제안(강제 아님) · T8.5.2 JIT 트래커
  (1회 요청·거절 시 재요청 금지·한계 고지) + 개별 삭제→캐시 무효화 ·
  T8.5.8 대화 추출 갱신(확인 전 저장 금지 — F9).
- **`persona.py`**: T8.5.5 조합 제약(politeness↔호칭, jane→hagae 전용, custom 금칙어·
  10자 제한) · T8.5.6 프롬프트 블록 — **5-3 고정 템플릿 슬롯 치환만**(즉석 작문 금지,
  문체 전용 고지 포함) · T8.5.7 준수 검사 4종(종결어미 ≥95% — 스타일 접미 클래스 판정,
  허용 외 호칭, 존대 혼용, easy 미해설 용어).
- migrations/004_user_profiles.sql + profile_store.py(JSONB 필드 개별 삭제 지원).
- 테스트 32건: 문서 예시 검증(乙丑 둘째→丙寅·셋째→丁卯, 亥→子 wrap 甲子),
  T8.5.9 미입력 영향표(전 필드 부재에도 차단 없음), E6 실연동(O14→relocation +8).
검증: pytest 403 pass(Phase8.5 32 신규) · ruff clean · mypy clean(166파일) ·
  사전 validate 25파일 통과.

### v2.2 Phase 9 — 풀이 상품 3종 (docs/10 전체 규격) ✅
- **`report_plan.py`**: 고정 목차 — RPT_FULL 22섹션(F-01~F-22, 분량 합계 78,000자
  ±10% 검증) / RPT_FOCUS 8섹션(C-01~C-08). dependsOn 규칙(F-04 용신 확정 →
  F-10~F-20 선행, F-21 → F-13~F-20 완료 후), 과거 검증(F-08/09)을 미래보다 앞에
  두는 고정 순서(신뢰 형성 원칙). 주제 변형(compatibility/relocation)은 **제목·모듈만
  교체, 섹션 추가/삭제 금지** — 테스트로 고정.
- **`report_checks.py`**: 정합성 검사 8종(7장 전체) — ①분량 ②간지(미제공 간지 등장
  = 즉시 실패) ③수치(점수·연도 정규식 대조) ④용신 일관(F-04 확정 기준) ⑤금지 표현
  (반드시~/당첨/당선/합격 단정 등 prohibited 패턴) ⑥페르소나(docs/11 5-4 4종 재사용)
  ⑦다중 대상 라벨 ⑧근거 경로 ≥1. **전부 코드 검증**(LLM 자기 검증 금지).
- **`report_builder.py`**: ReportSpec→SectionPlan→컨텍스트(주입)→LLM 생성(주입)→
  검사→**실패 섹션만 재생성(≤2회)**→2회 실패 시 on_hold(부분 산출물 보존+관리자
  알림 대상)→조립(표지/자동 목차/부록 재현성 파라미터: dictVersion·chartVariant·
  페르소나 스냅샷). F-04 실패 시 의존 섹션 미생성(용신 일관성 보호). F-04 확정
  용신을 후속 섹션 검사 기준으로 전파. 원가 집계(호출 수·입출력 토큰) +
  **단가 설정 분리**(config/model_prices.json — 하드코딩 금지).
- **CHAT 연계(5장)**: too_broad → RPT_FULL/RPT_FOCUS 제안 카드 동반(강제 유도 금지
  — "대화로도" 축약 답변 병행 명시).
- docx/pdf 변환(8장)은 운영 출시 단계 항목으로 보류 — 조립은 마크다운+메타 구조까지
  (표지·목차·부록 규격 충족). 후속: python-docx 파이프라인.
검증: pytest 420 pass(Phase9 17 신규) · ruff clean · mypy clean(171파일).

### v2.2 Phase 8 — 통합 & 품질 (T8.1~T8.4) ✅ — 전 페이즈 완료
- **T8.1 E2E**: 질문→답변 전체 파이프라인 통합 테스트 — Q1~Q9 각 5개(총 45문,
  docs/08 실측 어구 변형). 분류 정확 + 분석 라우트는 4요소 입력·토큰 한도 검증 +
  어떤 질문도 예외 없이 정의된 status로 응답. **E2E가 드러낸 파서 분류 사각 보강**
  (골든 34케이스 비파괴 확인): 소유격 용어("내 용신"→Q8, 용어교육 아님), 양자택일
  ("~할까 말까"→Q7), 궁합/우열 어휘("궁합/중에 누가/합이 좋은"→Q6), 과거 설명
  ("무슨 일이 있었/운 때문/이유가 사주"→Q5), 관계어+인물 질문("남편은 어떤 사람"
  →Q9, Q8보다 우선), 손없는 날→Q4 직행.
- **T8.2 토큰 측정**: `scripts/measure_tokens.py` — Context Reduction 전/후 입력
  토큰 비교 리포트. 표본 5문 기준 **절감 88.9%**(축소 전 ≈5.8k → 후 ≈0.6k/질문).
- **T8.3 CI**: `.github/workflows/backend-ci.yml` — push/PR 시 사전 validate →
  ruff → mypy → pytest(회귀 포함). DB 라이브 테스트는 러너에서 자동 skip.
- **T8.4 모델 평가 하네스**: `model_eval.py` — 후보 모델 응답을 **결정적 지표 3종**
  으로 채점(LLM 채점 아님): instruction 준수(금지 표현·미제공 간지/수치 = 재계산
  의심 감점) 0.5 + 날짜 구체성(연·월·구간·분기 인용 밀도) 0.25 + 용어 정확도(근거
  경로 용어 재인용률·근거 밖 용어 발명 감점) 0.25 → compare_models 랭킹.
  report_checks와 동일 원천(SectionContext) 공유.
검증: pytest 469 pass(E2E 46+평가 3 신규) · ruff clean · mypy clean(176파일).

**🎉 v2.2 로드맵 전 페이즈(0~9 + 8.5 + 8) 완료.** 남은 운영 전 작업: ① 실 API 키
라이브 테스트(사용자) ② 사전 reviewed:false 전 항목 도메인 검수(region_elements·
occupation 물상·persona_lexicon 등 — 검수 전 해당 기능 출시 금지) ③ employment
EventKey 추가 여부 결정 ④ docx/pdf 변환 파이프라인(보고서 출시 시).

### v2.2 — LLM 공급자 전환: Gemini 메인 + GPT-5 mini 비상 폴백 ✅ (라이브 검증 완료)
- **배경**: Anthropic API 결제 오류로 사용 불가(사용자 결정) → 메인 gemini-3-flash-
  preview, 비상 gpt-5-mini로 전환. 운영 편의를 위해 **단일 설정 파일** 요구.
- **`config/llm_config.json`(단일 관리 파일)**: 메인/폴백/파서 프로파일(공급자·모델·
  키 env 이름·generation_extras) + 옵션(타임아웃·재시도·백오프). 모델 교체·폴백
  순서 변경은 이 파일 수정만으로 가능(코드 불변). thinking/추론 비활성도 여기서
  강제(Gemini thinkingLevel MINIMAL / OpenAI reasoning_effort minimal — 절대 원칙 9).
- **`llm_client.py` 재작성**: httpx REST(공급자 SDK 의존 없음 — anthropic 의존성
  제거). 루트 `.env` 자동 로드(무의존 간이 파서, 기존 환경변수 우선). 폴백 정책:
  메인 N회 재시도(5xx/429/타임아웃) → 비상 모델 전환, 사용 공급자를 장부
  product_code 접미(:gemini/:openai)로 기록. **빈 응답 가드**: 추론 모델이 출력
  한도를 추론 토큰으로 소진하면(실측: gpt-5-mini가 통변 프롬프트에서 reasoning
  1200/1200 소모) 빈 응답 → 오류 처리 + 프로파일별 `output_token_buffer`(폴백
  2500)로 보전. 가드 한도는 가시 출력 기준 유지.
- **라이브 검증(실키)**: ① Gemini 모델 목록 조회로 gemini-3-flash-preview 확인
  ② Gemini 실호출 통변 성공(점수·간지 재계산 없이 인용, Trigger→진행 구조)
  ③ 검증 중 실제 Gemini 503(과부하) 발생 → **폴백이 자동으로 받아 정상 통변 완성**
  (비상 체계 실전 검증) ④ gpt-5-mini 버퍼 적용 후 정상 본문 확인.
- model_prices.json에 gemini/gpt-5-mini 단가 추가. .env.example에 키 안내.
- 폴백 단위 테스트 5건: 단일 파일 설정 반영·메인 성공·연속 실패→폴백·모두
  실패 오류·한도 초과 시 호출 전 차단.
검증: pytest 474 pass · ruff clean · mypy clean(177파일) + 라이브 E2E(answered).

### v2.2 — 프론트 대화형 통변 페이지(/chat) + 라이브 서비스 기동 ✅
- **`app/chat/page.tsx`**: 저장된 프로필(만세력 입력 재사용)로 /api/v2/chat 호출.
  thread_id 자동 생성으로 같은 창에서 멀티턴 유지, 추천 질문 칩, status 안내
  (too_broad/need_subject/policy), 반복 감지·상품 제안 카드 표시. 프로필 없으면
  만세력 입력으로 유도.
- lib/types.ts(ChatApiResponse)·lib/api.ts(postChat) 추가, 홈에 '대화형 통변' 카드.
- **next.config.mjs: experimental.proxyTimeout 120s** — LLM 호출(수십 초)이 Next
  프록시 기본 30초 타임아웃에 끊기는 문제 예방(첫 스모크에서 36.6초 응답 실측).
- 라이브 확인: 백엔드(uvicorn :8000, DB env+.env 키 자동 로드)·프론트(:3000 prod)
  재기동 → 프록시 경유 실통변 11~15초 응답, **멀티턴 상속 동작**("재물운 봐줘" →
  "그럼 내년은 어때?" turn 2 문맥 유지).
검증: tsc clean · next build 통과(/chat 4.36kB) · 라이브 E2E(answered) 3회.

### fix(frontend): 만세력 관계 표시 — 내부 변수 노출 수정(암합·지장간합) ✅
- **배경**: 엔진 커밋 a5ea1fe(에지 케이스 검출 개선)가 추가한 신규 관계 타입
  `hidden_stem_combination`(천간×지장간 암합)·`hidden_hidden_combination`(지장간끼리
  합)이 프론트 라벨 맵에 없어 내부 키가 그대로 노출 + 관계도에서 영문 잘림 +
  자합(동일 기둥)은 화살표 없는 외톨이 박스로 표시됨.
- **계산 검증(정확함 확인)**: 1980-11-22 09:08 차트(庚申/丁亥/己亥/己巳) 기준
  암합 7건 전수 일치 — 丁壬암합 3건(丁×申중壬·丁×亥중壬 월지/일지) +
  甲己암합 4건(己 일간·시간 × 亥중甲 월지/일지). 巳·庚 조합은 합 대상 지장간
  부재로 미검출(정상).
- **수정(표시만, 계산 불변)**: ① 관계도 다이어그램에서 암합·지장간합 제외
  (low-severity 보조 신호 — 도식 과밀 + 자합 도식 불가) ② '원국 구조 상세' 목록은
  한글 라벨("암합"/"지장간합") + 가독 표기("암합: 丁 × 亥중壬 (월·월)" — 내부 표기
  "亥:壬" 노출 제거) ③ 목록 정렬에서 보조 신호는 끝으로.
검증: tsc clean · next build 통과 · 프론트 재기동.

### fix: 분석 경고 문자열 내부 키 한글화(사용자 노출 문자열 한글 원칙) ✅
- 신강/신약·용신 패널 경고가 `yongsin_competing_candidates:` 등 내부 키 접두로
  노출되던 문제 — **백엔드 원천에서 한글 제목으로 교체**(표시 로직 아님, 문자열만):
  신강약 경계 / 용신 후보 경합 / 조후 경계 / 중화 구간(×3) / 통근 신왕 /
  신약 상한 적용 / 가종(假從) / 시간 미상. 프론트의 pseudo_follow 치환 코드 제거.
- 라이브 확인: /manse/calculate 응답 경고 3건 전부 한글 제목.
검증: pytest 474 pass · ruff·mypy clean · tsc·build 통과 · 서버 재기동.

### fix(llm-input): 실사용 결함 수정 — 기준 시점·기간 필터·택일 표·월별 요약 (P1~P7) ✅
- **배경(실측)**: LLM이 '올해'를 2024로 오인(입력에 오늘 날짜 부재), '올해' 질문에
  2022/2024 과거 100점 후보가 메인 서술 점유(기간 필터 부재), 택일 질문에 일운
  미제공("날짜 정보 없음" 회피 답변), 영문 키·내부 노트 노출. 구버전 모델은 아무
  계산도 못 하므로 **모든 필요 정보를 입력에 담아야 한다**(v1 prompt.ts 원칙 계승).
- **P1 [기준 시점]**: 직렬화 최상단에 오늘(요일)·올해(간지)·질문 기간 해석 결과
  명시 + "임의 날짜 기준 금지" 지시(v1 [오늘 날짜] 계승).
- **P2 기간 필터**: reduce_with_context — 질문 기간 내 후보가 메인, 기간 외 상위
  2건은 [참고 — 질문 기간 외 흐름(메인 서술 금지)]로 분리. 기간 내 0건이면
  "'뚜렷한 신호 없음'으로 정직 안내" 지시 명시. 계층 필터(Top5)가 과거 고점에
  점유돼도 기간 내 후보를 보존하는 보강을 chat 흐름에 추가.
- **P3 택일 라우팅**: Q4(date_recommendation) → CompositeBuilder(대상 월 기준)
  → DateSelectionEngine → [택일 결과] 표(날짜·요일·간지·점수·손없는날·사유 +
  회피일 목록, avoid 등급은 표에서 제외) + "표가 있으면 회피성 답변 절대 금지,
  표 날짜 그대로 사용" 지시(v1 이사일 원칙 계승). 실패 시 일반 풀이 폴백.
- **P4 월별 요약**: "월별" 요청/월 단위 granularity → 질문 연도 12개월 표(간지·
  최고 신호·점수·극성). 입춘 전 1월은 "전년 세운 구간" 정직 표기. 연 단위 질문의
  대운 과밀 수정(전체 10줄 → 관련 대운만).
- **P5 표기 정제**: 이벤트 한글 라벨(taxonomy ko) + "영문 키 노출 금지" 지시,
  근거 경로 내부 노트("(docs/05 …)") 제거, polarity 한글(우호적/부담·비자발 계열/
  조건부/중립), 월운 중복 제거, 대운 기간 ASCII 표기(2015-2025).
- **P6**: 점수에 신호 건수 병기("100점(신호 3건)") — 동점 변별.
- **P7**: 자가 검증 지시(v1 체크리스트 계승 — "답변의 모든 연도·간지·점수가 입력에
  존재하는지 확인") + 페르소나 연결(ChatRequest.persona → 5-3 블록을 시스템
  프롬프트에 결합, 문체 전용).
- **라이브 재검증**: "올해 연애운" → 2026 丙午 기준 메인 서술 + 과거는 배경 맥락 /
  "다음 달 이사 날짜" → 2026-07 인지 + 택일 표 기반 날짜 추천(회피성 답변 소멸).
검증: pytest 483 pass(품질 회귀 9 신규) · ruff clean · mypy clean(178파일) ·
  라이브 2문 확인.

## v2.2.1 — 해석 사전 계층 신설 (PR-A 문서 개정 + PR-B 1순위 사전) ✅

- **배경**: 풀이가 글자 의미·관계 해석 없이 계산 결과(점수·간지)만 낭독하는 결함
  확인(2026-06-12 점검). 원인 = ①의미 사전 미직렬화 ②시스템 프롬프트의 LLM 자체
  지식 차단 이중 봉쇄. 보완 방향 사용자 승인: "계산은 엔진, 의미는 사전, 서술은 LLM".
- **PR-A 문서 개정**: docs/05에 `interpretations/` 계층(6종)·공통 규칙 6항(basis
  의무·엔진 교차검증·일간 중심·신살/암합 보조자료) 신설, docs/06에 ⑤
  chart_interpretation 요소 + 프롬프트 2층 구조(캐시 prefix/동적 suffix) 신설,
  docs/09 8장 한도표 상향(대화형 12k/2.4k 등 + thinking low 이하, 캐시 적중 별도
  집계), CLAUDE.md 원칙 9 문구 개정(양쪽). **품질>토큰 정책**(사용자 확정).
- **PR-B 사전 집필(전량)**: `interpretations/ilju.json` 60갑자(물상·일주 동물·
  캐릭터 서사·빛/그림자·배우자궁·computed·basis — 예시 풀이(己亥) 스타일 기준),
  `ten_gods_text.json` 10종(natal/excess/absence/incoming/asYongsin/asGisin —
  일간 중심·상황 의존), `twelve_stages_text.json` 12종, `relations_text.json`
  59종(relations.json 1:1, 원국 내 vs 운 유입 구분, 암합 role=auxiliary).
- **검증기**: dictionaries.py에 스키마 4종 + lint 확장 — ilju computed ↔ 만세력
  엔진 전수 교차검증(십성·십이운성·지장간·오행색·띠), 십성/운성 커버리지,
  relations_text 1:1 정합, 암합 auxiliary 강제. `scripts/export_review_sheet.py`
  — 전문가 감수용 Markdown 시트(basis 열 기준, 검수 현황 집계).
- **콘텐츠 규율**: 단정 표현 금지를 사전 콘텐츠에도 적용(테스트로 강제,
  "반드시" 2건 적발·수정). 전 항목 `reviewed:false` 시작 — 전문가 감수 전 출시 금지.
- 검증: pytest 490 pass(해석 사전 회귀 7 신규) · ruff clean · mypy clean(180파일) ·
  validate_dictionaries 29파일 통과.
- **남은 단계**: PR-C(context_reducer 2층 직렬화 + [명식 구조]/[해석 자료] 섹션 +
  근거 경로 의미 결합 + 시스템 프롬프트 분리 + llm_config thinking LOW + 캐시 로깅),
  PR-D(신살·물상·terminology·templates·events 4종 + 골든 스타일 회귀),
  PR-E(풀이 상품 F-01~F-06 컨텍스트 빌더 운영 배선).

## v2.2.1 PR-C — 프롬프트 직렬화 개편 + Graph RAG 정밀화 (해석 레이어 실가동) ✅

- **Graph RAG 사용 실태 점검**(사용자 요청 — 2025-08 케이스 기준): ①후보 생성
  (relations eventDomains 복수 전파)과 AND-조건 동반 신호 합산은 구현돼 있었으나
  ②신호 매칭이 천간 십성만 지원(甲申월 申 상관 이동성 표현 불가) ③프롬프트
  [근거 경로]가 정적 사전 경로(graph retrieve)뿐 — 스코어러의 사용자별 인스턴스
  경로(readable_path)는 미사용(scorer 파라미터 수령 후 무시) ④해당 회귀 케이스
  미저장. 4건 모두 본 PR에서 해소.
- **동반 신호 매트릭스 보강**: SignalSpec에 `branchTenGod`(운 지지 본기 십성) 추가
  + _match_signal 확장, relocation.json에 상관/식신+역마 룰 2건(reviewed:false),
  docs/05 events 스키마·매트릭스 원칙 명문화, compiled 그래프 재빌드(143노드).
  **cases.jsonl에 regression_2025_08_move_not_job 적재**(2025-08 이사 / 2025-11말
  합격 / 2025-12 출근 — "정관합=직장" 단정 금지의 기준 사례).
- **⑤ chart_interpretation**: chart_interpretation.py 신규 — 주별 십성·운성·신살
  (보조 표기)·원국 관계(암합류 제외)+병존·간여지동, 일주 사전 엔트리 직렬화,
  원국 활성 십성·일지 운성·관계 해석 발췌(전체 사전 투입 금지·상한 가드).
- **2층 직렬화**: [원국·명식 구조]+[명식 해석 자료] = 고정 prefix(사용자별 바이트
  동일 — 캐시 조건, 테스트로 고정) → [기준 시점] 이하 동적 suffix. 후보별
  "동반 신호:"(매트릭스 구성 명시) + "해석:"(운 유입 천간·지지 십성 + 발췌 —
  甲申=정관+상관 양표기). 근거 경로는 인스턴스 경로 우선·정적 경로 폴백.
- **지시·프롬프트 개정**: 시스템 프롬프트 6항(계산 금지/의미 서술 의무 분리 +
  매트릭스 재해석 금지 + 신살·암합 보조) + [지시]에 _MEANING/_MATRIX/_AUXILIARY
  3종 추가.
- **한도·설정**: llm_guard CALL_LIMITS v2.2.1(채팅 12k/2.4k, 비교 14k/2.8k,
  섹션 입력 10k — 사용자 승인), LLMCallLog.cached_input_tokens 신설,
  llm_client 공급자 응답에서 캐시 적중 토큰 수집(Gemini cachedContentTokenCount /
  OpenAI cached_tokens), llm_config thinking LOW(파서 MINIMAL 유지).
- 실측: "올해 이직운" 프롬프트 3,256tok(한도 12k 내) — 일주 서사·십성/관계 해석·
  동반 신호·운 유입 해석 포함 확인.
- 검증: pytest 496 pass(신규 6 — 고정 prefix 동일성·해석 노트·branchTenGod 매칭·
  회귀 케이스 보존) · ruff clean · mypy clean(182파일).
- **남은 단계**: PR-D(신살·물상·terminology·templates·prohibited_styles·events 4종
  + 골든 스타일 회귀), PR-E(보고서 F-01~F-06 컨텍스트 빌더 운영 배선), 라이브
  키로 실응답 품질 확인.

## v2.2.1 PR-D + PR-E — 잔여 사전 완비 + 골든 스타일 회귀 + 보고서 운영 배선 ✅

- **PR-D 사전(docs/05 잔여 전량)**: events 4종 신설(relationship 6룰·wealth 6·
  education 5·health 5 — 전부 동반 신호 2조건 이상, 신살 단독 룰 금지) +
  career_change에 취업 매트릭스 룰(정관+인성/문서 — regression_2025_08 일반화).
  `interpretations/sinsal_text.json` 44종 — **전 항목 flipSide(양면 해석) 의무**
  (사용자 확정: 천을귀인 과다=나태, 고신살=일 몰두형 성공·자발적 만혼, 양인=
  외과의사·군인 적성 등 길신의 그림자·흉성의 빛 병기, 스키마로 강제).
  `stems_branches_text.json`(천간10·지지12 물상), `terminology.json` 53용어,
  `templates/interpretation.json`(이벤트×극성 29 + generic 폴백),
  `templates/prohibited_styles.json` 20패턴. 스키마 5종 등록 + lint(물상
  오행·띠 엔진 교차검증, 템플릿 EventKey 유효성·중복).
- **신살 발췌 프롬프트 연결**: chart_interpretation에 주요 신살(길신/주의 우선
  +일주) 발췌 — "(보조 — 단독 판정 금지) 의미+발현+양면" 형식으로 고정 prefix 탑재.
- **실결함 수정**: "나의 일주캐릭터는?"이 fortune_overview→too_broad로 차단되던
  문제 — 파서 Q8 패턴(일주/캐릭터/기질/타고난/어떤 사람) 추가 + CHART_ANALYSIS는
  B3 판정 면제(원국 T0 질문 — 시점·분야 불요). 골든 스타일 픽스처
  (tests/fixtures/golden_style_ilju_example.md — 사용자 제공 己亥 예시) + 회귀 4건
  (Q8 흐름·스타일 재료·신살 양면·페르소나 쉬움/존대 준수).
- **PR-E 보고서 운영 배선**: `report_service.py` — _ReportData(만세+스코어링
  1회 공유), build_section_context(고정 prefix 재사용 — serialize_chart_prefix
  공용화 + 섹션 과제/가이드 + 운 섹션 데이터 블록(대운표·후보 Top·근거 경로) +
  검사 기준 실값(allowed_ganji/scores/years·F-04 용신 확정)), generate_report
  (llm_client 주입·페르소나 블록·재생성 힌트), plan_report(dry-run).
  **POST /api/v2/report** 라우터(dry_run 미리보기 포함). 실컨텍스트+모의 LLM으로
  RPT_FOCUS 8섹션 정합성 검사 전체 통과 확인.
- 검증: pytest 504 pass(골든 스타일 4 + 보고서 4 신규) · ruff clean ·
  mypy clean(186파일) · validate 38파일 통과 · 그래프 재빌드(166노드).
- **남은 운영 전 작업**: ①라이브 키 실응답 품질 확인(/chat·/report) ②사전
  reviewed:false 전 항목 전문가 감수(export_review_sheet.py 시트) ③F-08/F-09
  (과거 복원 M14)·C-03~C-07 모듈 데이터 정밀화(현재 공용 데이터 블록) ④docx/pdf.

## v2.2.1 풀이 교정 1차 — 출력·관점 (사용자 18항목 중 5·13·4·2·18·10·6·16) ✅

- 점수·신호건수 미노출(항목 5): candidate_line·월별·택일에서 숫자 제거, 강도는 tone_for_score 치환 문장만. 이벤트 헤더 '추측 신호'로 변경.
- 출력 1,500자(항목 13): _LENGTH_INSTRUCTION + 시스템 프롬프트 + llm_guard chat_single 출력 1,800tok/1,500자 안전망.
- 마크다운 금지(항목 4, 백엔드측): _FORMAT_INSTRUCTION + 시스템 프롬프트(평문).
- 신살 보조 강화(항목 2): _AUXILIARY_INSTRUCTION '이런 신살의 영향일 수도' 톤, 성향 부각 금지.
- 합 인과 완결(항목 18): _HARMONY_INSTRUCTION '무엇과 합하여 무엇으로 작용해 어떤 결과'까지.
- 이벤트=추측값(항목 10): _SCOPE_INSTRUCTION '기간 전체 대표 아님, 원국+대운 흐름 먼저'.
- 대운>세운>월운>일운 위계(항목 6): _HIERARCHY_INSTRUCTION.
- 원국 vs 운 구분(항목 16): _ORIGIN_INSTRUCTION.
- 검증: pytest 504 pass(영향 테스트 6건 갱신) · ruff·mypy clean. 라이브: "올해 이직운" 1,232자·마크다운/점수 없음·대운 배경·합 인과 완결·원국/운 구분 확인.
- 남은 배치: 2차 입력확충(희신/구신/한신·격국·공망활성·합화방식·궁성·원국암합), 3차 엔진(방합 준방합 규칙·운 암합 이벤트·graph rag 심화), 4차 설계(용신 확정 질문·균시차 검증보고).

## v2.2.1 풀이 교정 2·3차 — 입력 확충 + 방합 규칙 (항목 8·9·14·1·17·3) ✅

- 용희기구한 5역할(항목 8): UsefulGods에 heesin/gusin/hansin 추가, favorability_map에서 전 역할 추출, 고정 prefix에 '용신·희신·기신·구신·한신' 전부 직렬화. 라이브: "격국·희신·구신?" 질문에 정재격 + 5역할 전부 정확 답변(환각·모름 없음).
- 격국(항목 9): BirthChartSummary.geokguk = '정재격 · 중성 · 반성반패', prefix에 '격국:' 표기.
- 궁성 자리역할(항목 14): PillarDetail.palace_role(연-조상/월-부모/일-나·배우자/시-자녀, 천간·지지 구분), prefix에 '궁성:' 표기.
- 원국 암합(항목 9): chart_interpretation에서 hidden_ 관계를 제외→'암합(보조·단독 판정 금지)' 라벨로 상한 3개 표기.
- 교운일(항목 1): DaewoonEntry.jiao_date, 대운 줄에 '교운일 YYYY-MM-DD'.
- _STRUCTURE_INSTRUCTION(격국·용희기구한·궁성 활용 지시).
- 방합 준방합(항목 3, 사용자 정통 기준): relations_text directional 4종에 '세 글자 모두 모여야 진방합, 두 글자는 준방합(화기 강화·미완성), 운에서 마지막 글자 채워질 때 촉발' 규칙 추가 + _BANGHAP_INSTRUCTION. (엔진 점수 로직은 회귀 위험으로 보존 — 설명 왜곡만 교정)
- 균시차(항목 12): 검증 완료 — manse_service.calculate가 진태양시·균시차 보정된 final_chart_datetime으로 원국을 세움. 추가 작업 불요.
- 검증: pytest 504 pass · ruff·mypy clean. 라이브 2건 확인.
- 남은 항목(다음 배치): 갑기합 이사우위 점수 보강·운 암합 이벤트(7)·공망활성 신호 노출(1)·graph rag 심화(15)·용신 확정 질문 재설계(11)·프론트 react-markdown(4 근본).

## v2.2.1 풀이 교정 3차-b + 멀티턴 절제 (항목 15·19, 7 부분) ✅

- graph rag 실효화(항목 15): LlmEvidence에 supports·interpretation_hints 추가, 근거 경로 블록에 '보조 근거'·'해석 힌트' 직렬화. 컴파일 그래프에 interpretation_rule 38노드·supports 36엣지 실재 → "정관합+기신/정관합+용신/정관+인성→취업" 등 동반 신호 매트릭스 규칙이 해석 힌트로 LLM에 전달됨(갑기합 이사우위 판단 간접 보강).
- 후속 턴 절제(항목 19, 사용자 추가 요청): LlmInput.is_followup_turn(state.turn_no≥2), _FOLLOWUP_INSTRUCTION '인사·자기소개 반복 금지, 앞 배경 재인용 금지'. 라이브 2턴 검증: 1턴 "회원님 반갑습니다" → 2턴 인사 없이 본론 직행.
- 운 암합(항목 7): 원국 암합(2차) + graph 해석힌트로 부분 충족. 운 암합 단독 이벤트 점수화는 보조 자료 원칙(단독 결론 금지) + 회귀 영향이 커 별도 검토로 보류.
- 검증: pytest 504 pass · ruff·mypy clean. 라이브 멀티턴·graph 힌트 확인.
- 남은 항목: 용신 확정 질문 재설계(11, calibration 패키지), 프론트 react-markdown(4 근본 — 현재 백엔드 평문 지시로 증상 차단됨).

## v2.2.1 풀이 교정 4차-a — 용신 확정 질문 재설계 (항목 11) ✅

- 질문을 '막연한 흐름' → '대표 영역(intent) 제시 + 긍정/부정 흐름 택일'로 개선(2026-06-12 사용자 확정). q1=용신 긍정후보(직업·학업·연애 중 중요 영역), q2=기신 부정후보(금전·건강·계약), q3=모델 비교. 흐름은 기존 overall_rating(very_positive~very_negative)으로 받아 score_feedback이 모델 예측과 대조 — 스키마·채점 로직 불변(안전).
- 라이브: "2017년(丁酉세운·만37세)는 좋은 기운이 들어올 것으로 본 해예요. 그 무렵 직업·학업·연애/부부 중 본인이 가장 중요하게 여긴 영역의 흐름은 순조로웠나요, 힘들었나요?" 생성 확인.
- 항목 4(마크다운): 백엔드 평문 지시(1차)로 실질 해결 — 프론트 react-markdown 도입은 npm 의존성 추가라 별도 확인 후 진행(보고서 등 대비 보강).
- 검증: pytest 504 pass · ruff·mypy clean.

## v2.2.1 풀이 교정 5차 — 구신 반전 + 프론트 마크다운 + 보류 3건 정리 ✅

- 구신 반전(사용자 추가 요청 2026-06-12): interpretations/favorability_text.json 신설(용희기구한 5역할 + reversal 의무). 구신 4반전(①희신 태과 제어 ②탐합망극으로 기신 합거 ③운 통관 징검다리 ④제화로 권력·기술 치환) + 기신 반전(합거·제화). chart_interpretation이 사용자 명식의 구신·기신 reversal 발췌, _REVERSAL_INSTRUCTION 지시. 파서 Q8에 용신/희신/기신/구신/한신·십성·신살·궁성 키워드 추가(too_broad 방지). 라이브: "구신 나쁘기만 한거야?" → "무조건 나쁜 게 아니라 균형의 핵심 성분" + 정임합 묶음 설명(1,395자).
- 프론트 react-markdown(항목 4 근본): react-markdown@9 + @tailwindcss/typography 설치, chat/page.tsx 어시스턴트 메시지를 ReactMarkdown+prose 렌더로 교체(마크다운이 와도 깨지지 않음). tsc·prod build 통과.
- 보류 3건 처리 결과:
  · 공망활성(보류-3): 이미 신호로 노출 확인("공망 활성 → 金 용신" 등) — 추가 작업 불요.
  · 갑기합 이사우위(보류-1): graph 해석 힌트(매트릭스 규칙 전체)+_MATRIX_INSTRUCTION으로 LLM이 동반 신호로 판단. 점수 클램프(100) 동점은 구조적 한계 — 절대 점수 보강은 명리 검수 후 별도(상대 순위 신뢰 원칙).
  · 운 암합(보류-2): 원국 암합 보조 표기 + graph 힌트 + 암합 지시로 부분 충족. 완전한 운 암합 이벤트화는 만세력 엔진(luck relations_to_chart)에 암합 산출 추가가 필요 — 만세력 수정 금지 원칙 + 회귀 영향으로 별도 검토.
- 검증: pytest 505 pass(favorability 회귀 1 신규) · ruff·mypy clean · 프론트 build 통과.

## v2.2.1 풀이 교정 6차 — 운 암합 구현 + 갑기합 정렬 + 교운 가중 확인 ✅

- 교운일 변동성 가중(사용자 확인 요청): 검증 완료 — event_scoring.daewoon_transition_weight = exp(-(d/365)^1.0), 첨도 큰 라플라스형. jiao_dates(trace.exact_jiao_un_dates) 정상 채움, 세운/월운 신호에 분포 가중 적용. 교운일 1.0 / ±1년 0.368 / ±2년 0.135 / ±3년 floor(0.05) — 전후 2년이 핵심 작용 구간(메모리 [[daewoon-transition-influence-model]] 실측 모델 그대로).
- 운 암합 구현(보류-2 해소, 2026-06-12 사용자 자료): amhap_luck.py 신설 — ①명암합(운 천간+원국 지장간) ②지장간암합(운 지지 지장간+원국 지장간), 천간오합(STEM_COMBINATIONS) 기준. 궁성 매칭(연-대외/월-직장·사회/일-사생활·배우자 비중 최대/시-취미·투자) + 십성(지장간↔일간). LlmEventCandidate.amhap_notes로 프롬프트에 '운 암합(보조·물밑)' 표기 — 점수 미반영(보조 원칙·회귀 0), _AUXILIARY_INSTRUCTION에 궁성·십성 참고 안내. 라이브 탐지 확인(丁↔壬 정재 일지 명암합 등).
- 갑기합 이사우위(보류-1 해소): 점수 클램프(100) 동점 시 동반 신호 수로 정렬(-score,-len(signals),period,key) — 사건명은 매트릭스 일치 수가 결정(2025-08: 이사 2신호 > 직장 1신호). 회귀 케이스(2024 동반 없음 → career 상위권) 영향 없음.
- 검증: pytest 507 pass(운 암합 회귀 2 신규) · ruff·mypy clean(187파일).

## v2.2.1 풀이 교정 7차 — 엔진 polarity 종합화 (지시문→엔진 전환, 사용자 피드백) ✅

- **방향 전환(사용자 피드백)**: "프롬프트 지시로 모든 걸 커버 = v1 실패(프롬프트 180k)". 교운기·공망 지시문(_TRANSITION/_VOID)을 제거하고 엔진/데이터로 이전.
- polarity 종합화(근본): 기존 polarity=top.polarity(단일 최강 신호) → `_aggregate_polarity` — 긍/부정 신호 weight 비교 + 충·형·공망 얽힘 복잡도 + 운 천간/지지 오행 용기신을 종합. 희신 충이 강해도 공망·다중 충형·운 천간 흉신이 얽히면 conditional(변동)로.
- 운 천간/지지 오행 용기신 반영(사용자 지적 "5월 계수=구신"): score()에서 운 간지 오행 role 맵 구축 → _aggregate_polarity에 전달, 구신·기신이면 부정 가중(천간 0.4/지지 0.2). incoming_note에 "癸 편재(水 구신)" 형태로 오행 용기신 명시.
- 교운기 비자발성(데이터): events career_change/relocation의 daewoonTransition note를 "환경이 떠미는 비자발적 전환"으로 강화(지시문 대신 데이터 — graph 자동 반영).
- 공망 발동 불리(데이터): career_change.json에 void→career/document conditional 룰 추가(공망 충발 시 결과 지연·무산).
- 출력 토큰 상한(Gemini thinking+가시 합산): chat 1,800→5,000(thinking 잠식으로 답변 잘림 해소). docs/09 8장 갱신.
- 검증: 사용자 차트(1980-11-22 0940 진태양시 미적용) 라이브 — 2025 conditional / 4월 positive(용신) / 5월 conditional(구신+공망+충) / 6월 negative. 교운기 비자발·5월 구신/변동 답변 반영 확인. pytest 507 pass · ruff·mypy clean.

## v2.2.1 풀이 교정 8차 — 운 위계(대운>세운>월운>일운) 점수 차등 (사용자 지적) ✅

- **진단**: level은 후보 분류(라벨)에만 쓰이고 신호 weight에 level 차등이 전혀 없었음 — 같은 신호가 월운에서 와도 세운·대운과 동일 점수(위계 미반영).
- 위계 가중(event_scoring): `_LEVEL_WEIGHT`(대운1.0/세운0.85/월운0.6/일운0.4)를 _relation_contributions·_mapping_contributions의 weight에 곱. 교운기(daewoonTransition) 신호는 대운 작용이므로 발생 계층과 무관히 대운 위상(1.0)으로 처리.
- 위계 점수 상한(클램프): `_LEVEL_CAP`(대운100/세운90/월운75/일운55) — 월운/일운에 충·합이 몰려도 세운·대운을 넘지 못하게(점수 클램프 100에 묻히던 역전 해소).
- 결과(사용자 차트): 대운 2025~2035=100 > 세운 2025=90/2026=85 > 월운 2026-05=75. 강도 표현(tone_for_score)도 차등되어 LLM에 전달.
- 라이브: "올해 직업운" → 임진 대운(교운기·환경 강제)을 큰 배경으로 먼저, 세운 병오년 희신, 4·5·6월 월운을 디테일로 배치 — 대운>세운>월운 위계 구조 반영 확인.
- 검증: pytest 507 pass · ruff·mypy clean.

## v2.2.1 풀이 교정 9차 — 대운 교운일 정확값 제공 (사용자 지적) ✅

- 지적: 질문 연관 대운의 교운일이 프롬프트에 제대로 제공되지 않음 — 만세력 엔진에 정확 교운일이 있는데 대략값(approx_start_date)을 쓰고 있었음.
- 수정: context_reducer build_calendar_context가 만세력 엔진 trace.exact_jiao_un_dates에서 각 대운 approx_start_date에 가장 가까운 정확 교운일을 매칭해 DaewoonEntry.jiao_date로 제공(_exact_jiao_dates·_nearest_jiao 헬퍼, 차이 400일 초과 시 approx 폴백).
- 결과: "올해 직업운" → 대운 壬辰(2025-2035), 교운일 2025-11-22(대략) → 2025-11-14(엔진 정확값). 질문 연관 대운(현재 대운)이 교운일과 함께 프롬프트 [간지달력]에 노출.
- 검증: pytest exit 0(통과) · ruff·mypy clean(편집 파일).

## v2.2.1 풀이 교정 10차 — '몇 월' 시기 질문에 월운 보장 (사용자 지적) ✅

- 지적: "재취업한 달은 언제" 질문(몇 월 명시 요구)에 "달을 특정할 수 없다"고 회피.
- 진단: query_type=timing_search·granularity=month인데 이벤트 후보에 월운 0개(세운만) + 월별 요약 미동반. 위계 cap(월운 75<세운 90)으로 월운이 Top N에서 밀리고, "최근 1년"이 time_range로 파싱 안 돼(open_when) 월별 트리거(start 4자리 조건)에 안 걸림.
- 수정(chat_service): wants_monthly 트리거 확장 — "월별" 키워드 OR query_type=timing_search OR granularity=month OR "몇 월/언제/어느 달" 키워드. 시점 미지정 시 '최근/지난/작년'이면 직전 해(today-1), 아니면 올해를 target_year로 월별 요약 생성. (_SCORE_LEVELS에 MONTH 포함돼 월운 데이터 존재.)
- 결과: 같은 질문 라이브 — 회피 사라지고 "작년 하반기~올해 초" 시기 제시 + 교운일(11/14) 짚음.
- 유사 케이스 처리: 시기 특정형 질문(timing_search/월 granularity/몇월·언제·어느달) 전반에 월별 표 보장.
- 검증: ruff·mypy clean(편집 파일), 라이브 확인. pytest 백그라운드 실행 중.

## v2.2.1 풀이 교정 11차 — 과거 월운 on-demand 계산 (회피 답변 근절) ✅

- 지적: "2025년 월별 정보 미제공 → 특정 달 확언 어렵다" 회피 — 신뢰 훼손("다 확인 안 하고 아무말").
- 진단: monthly_luck은 미래 12개월(2026-02~2027-01)만 계산, 과거(2025) 빈 표. 10차에서 "최근→직전해(2025)"로 잡았더니 빈 표가 들어가 회피 유발.
- 수정(chat_service): target_year가 result.monthly_luck 범위 밖이면 luck_months(birth, year) 어댑터로 그 해 월운 on-demand 계산 → result 사본 monthly_luck 교체 → MONTH 레벨 재스코어 → build_monthly_overview. 신호 0인 빈 표는 overview=None으로 차단(빈 표가 회피 유발).
- 결과: "최근 1년 재취업한 달" 라이브 — 회피 사라지고 2025년 12개월 표(간지·이벤트·극성·강도) 제공, 2025-07 계미월(우호적)·2025-10 병술월 등 구체 월 특정. 11월 교운기·비자발·사해충 근거 제시.
- 검증: pytest exit 0 · ruff·mypy clean(편집 파일) · 라이브 확인.

## v2.2.1 풀이 교정 12차 — 월별 표 누락 신호 보완 (2025-08 이사 누락) ✅

- 지적: 2025-08(甲申)은 이사 신호가 더 큰데 답변이 재취업만 단정(regression_2025_08 재발).
- 진단: graph rag·매트릭스·정렬은 이벤트 후보 경로엔 적용됐으나, 월별 표(build_monthly_overview)는 별도 경로로 월당 최상위 1개만 표기. 2025-08 career(신호7) > relocation(신호5)이라 이사 통째 누락.
- 수정: build_monthly_overview를 월당 상위 2개 이벤트로(점수→신호수 정렬, 이벤트 후보와 일관). 2025-08 → "이직·직업 변화 / 이사" 병기.
- 결과: 라이브 "2025년 8월 변화" → 이사 신호 우세(상관+역마, 거처 강제 전환) 먼저 서술 + 직업 변화 병기. 공망 지연도 언급.
- 남은 한계: 갑기합·삼합·방합이 career_change로 매핑돼 career 신호 수 부풀림(점수는 동점) — '이사 점수 우위'까지 하려면 범용 관계 신호 방향 가중 약화 또는 정관합+역마/식상 동반 시 relocation 재배분 필요(명리 검수 동반, 별도).
- 검증: pytest exit 0 · 라이브 확인.

## v2.2.1 풀이 교정 13차 — 2025-08 이사 점수 우위 (범용 신호 감쇄 + raw 정렬) ✅

- 목표: 2025-08(甲申)을 점수상으로도 이사 우위로(이전엔 career 신호수 우위로 이사 누락/2순위).
- 근본 원인: 갑기합·삼합·방합이 career_change로 매핑돼 career 신호 부풀림 + 정렬이 신호 수 기준.
- 수정: ①삼합/방합이 한신·중립일 때 사건 기여 ×0.4 감쇄(_GENERIC_NEUTRAL_FACTOR — 방향 결정력 약한 범용 세력) ②relocation '상관+역마' 0.7→0.85(이동성 특이 신호 강화) ③relocation에 '정관합+기신→원치 않는 이동·배치' 0.55 추가(이사 의미) ④EventCandidate.raw_total 추가, 정렬 (-score, -raw_total, -신호수)로 변경(클램프 동점을 raw로 변별) ⑤월별 표 정렬도 raw_total 통일.
- 결과: 2025-08 relocation raw 2.019 > career 1.857(1위), 월별 표 "이사 / 이직·직업 변화" 순. 직업 핵심 달(4·6·7월)은 이직 먼저 유지.
- 검증: pytest exit 0 · ruff·mypy clean · validate 통과 · 월별 표 확인.
- 별도 미해결: '2025년 8월' 단발 과거 월 질문에서 target_year(월별표 기준 연도)가 2025로 일관 파싱 안 됨 → LLM이 2026-08로 대체하는 경우. 파서 보강 필요(이사 우위와 별개).

## v2.2.1 풀이 교정 14차 — 절대 연·월 파싱 버그 (2025년 8월 → 2026 오인) ✅

- 지적: "2025년 8월" 단발 질문에서 LLM이 2026-08로 대체.
- 진단: time_parser C5(월 단위)가 "8월"을 잡으며 연도를 today.year(2026)로만 채우고 명시 연도(2025)를 무시(C6 연도 처리가 뒤에 있어 도달 못 함). C7(반기)도 동일.
- 수정: C5·C7에서 "(20\d{2})년" 절대 연도가 있으면 우선 사용(없으면 당해/내년). "2025년 8월"→2025-08, "2025년 하반기"→2025-07~12.
- 효과: 과거 월운 on-demand 계산(11차)·월별 표(12차)·이사 우위(13차)가 올바른 연도로 연결.
- 검증: pytest exit 0 · 파서 진단 정확 · 라이브("2025년 8월" → 2025년 답변, 이사 신호 강조) 확인.

## v2.2.1 풀이 교정 15차 — '1년 내/앞으로 1년' 월별 요약 롤링 창 (오늘 기준) ✅

- 지적: "1년 내라고 하면 오늘(2026-06-12) 기준이어야 하는데 왜 2025만 봤나."
- 진단: build_monthly_overview가 '달력상 한 해(1~12월)'만 그리도록 설계됨. 상대-미래 질문에서도 연도만 뽑아(2026) 1~12월을 그려 ① 이미 지난 2026-01~05 포함 ② 2027-01~05 누락 → 오늘 기준 롤링 창이 아님. "1년 내"는 time_range가 없어 월별 표 자체가 안 나옴.
- 수정:
  - context_reducer.build_monthly_overview: months(명시적 'YYYY-MM' 목록) 파라미터 추가 — 달력 연도와 무관한 롤링 창 지원. 헤더도 "질문 연도" → 실제 구간 "{첫달}~{끝달}"로 정확화.
  - chat_service: start가 'YYYY-MM-DD' 앵커이거나 '앞으로/향후/다가오는/1년 내' 키워드면 _rolling_months(today.year, today.month)로 오늘 달부터 12개월 롤링 창 생성. 연도 경계를 넘으므로 닿는 연도별 luck_months를 합쳐 on-demand 스코어. 명시 연도('2025년 8월')·과거('작년')는 기존 달력-연도 로직 유지.
  - _rolling_months 헬퍼 추가. wants_monthly에 상대-미래 키워드 추가.
- 효과: '앞으로 1년' → 2026-06~2027-05 롤링 창. '2025년 8월'은 그대로 2025년(14차).
- 검증: pytest exit 0 · ruff/mypy clean · 롤링 빌드(2026-06~2027-05 확인) · 라이브("앞으로 1년" → 2026 병오년부터, 2025-11은 대운 교체 배경으로만).

## v2.2.1 풀이 교정 16차 — '오늘의 운세'(일 단위) E9 Lifestyle 라우팅 + 위계 가중 ✅

- 치명 오류: "오늘의 운세"(gran=day)인데 chat_service에 일 분기가 없어 세운/월운 거시 이벤트(이직·이사)만 후보로 넘겨, 하루 질문에 인생 사건을 단정. 정작 그날 일진(丁巳 등)은 LLM에 전달 안 됨.
- 진단: 파서는 정상(gran=day). E9 Lifestyle(daily) 엔진(build_lifestyle_context, M15)은 이미 구현돼 있었으나 chat이 라우팅하지 않음. 데이터(일운 LuckPillar: 간지·십성·운성·형충회합·공망·신살·luck_summary)는 완비.
- 구현:
  - shared_types/llm_input.py: DailyFortune/DailyFortuneSlot 모델 + LlmInput.daily_fortune.
  - chart_interpretation.py: build_daily_grounding(일진 십성·운성·형충회합 fromLuck·신살 양면·공망). 관계 fromLuck 매칭 위해 relations_text 역색인(_luck_rel_text_index, 관계명 한자 제외).
  - chat_service.py: _build_daily_fortune — gran=day면 luck_days로 해당일 일운 확보, CompositeBuilder로 컴포지트 생성, build_lifestyle_context로 7슬롯(핵심기운/일·공부/돈·소비/관계·연애/건강/주의행동/활용법)+점수 산출, grounding 결합. 일일 경로는 거시 이벤트 후보·그래프·월별표 배제(이직·이사 단정 차단).
  - context_reducer.py: build_llm_input daily_fortune 처리 + [오늘의 운세] 직렬화 + _DAILY_INSTRUCTION(하루 범위 한정: 조짐·횡재·가벼운 변화·만남·다툼·컨디션, 인생사건 실행 단정 금지).
- 점수 모델(사용자 2회 정정 후 확정): 일일 슬롯 점수는 운 위계 가중 합산(대운1.0>세운0.85>월0.6>일0.4, event_scoring._LEVEL_WEIGHT 동일 철학). 대운·세운이 형성한 기운을 월이 더하고 일에서 사건화. topic_builder._lifestyle_scores에 _LIFESTYLE_LEVEL_WEIGHT 적용. (초안 일>월>세는 사용자 반박으로 폐기 — 거시 형성 에너지를 빼면 안 됨; 출력 framing만 하루 단위로 한정.)
- 효과: "오늘의 운세" → 丁巳 일진 중심, 사해충/사신합을 하루 단위 트리거·조짐으로 서술, 이직·이사 단정 0. 슬롯 점수 극단(0/100)→9~79로 안정.
- 검증: pytest exit 0 · ruff/mypy clean · 라이브(1100자, 이직/이사 단정 없음) 확인.

## v2.2.1 풀이 교정 17차 — 월간·연간 총운 E9 라우팅(일 총운과 동일 철학) ✅

- 요청: 특정 월간·연간 운세도 일 총운과 같은 철학으로 정리(주간은 '날들의 종합'이라 성격 달라 제외).
- 규격 보완: format_slots.json·docs/02 E9에 **monthly 슬롯 신설**(연간 도메인형 월 스케일: 핵심흐름/일·직업/재물/관계·연애/건강/주의시기/기회시기, reviewed:false, 사용자 확정). docs E9에 위계·사건화 철학 주석 추가.
- 일반화:
  - llm_input: DailyFortune→**PeriodFortune**(fortune_type·period_label 추가), DailyFortuneSlot→PeriodFortuneSlot, LlmInput.period_fortune.
  - chart_interpretation: build_daily_grounding→**build_luck_grounding**(일/월/세운 LuckPillar 공용).
  - topic_builder: _fortune_type에 monthly 분기, _SLOT_DOMAIN에 '일·직업'→work.
  - context_reducer: period_fortune 직렬화(헤더·라벨 fortune_type별), _MONTHLY_/_YEARLY_INSTRUCTION + _PERIOD_FORTUNE_INSTRUCTION/_HEADER 맵.
  - chat_service: _build_daily_fortune→**_build_period_fortune**(일/월/연), _period_fortune_type 게이트(FORTUNE_OVERVIEW·단일 기간만; 주간·도메인·'월별/달별' 분해는 제외해 월별 표 경로 양보). 일=단일일(start==end)로 제한해 주간 분리.
- 점수 정규화(극단 0/100 해소): _lifestyle_scores를 **레벨 내 평균 후 위계 가중 결합**으로 변경 — 월간(~30일)·연간(12개월) 하위 레벨 개수 폭주 방지. 일간은 레벨당 1개라 불변. 위계 가중(대운1.0>세운0.85>월0.6>일0.4)은 유지(사건화 철학).
- 효과: 이번 달/특정 월/올해/특정 연 총운이 해당 기간 간지(월운/세운)·분야 슬롯·주의·기회 시기 중심으로 정리. '올해운을 월별로'는 월별 표 경로 유지. 라이브 월간(갑오월 갑기합 활성화)·연간(병오년 화 희신·직업·상하반기·도화) 확인.
- 검증: pytest 507 passed · ruff clean · mypy 내 코드 clean(기존 manse_core stub 2건은 baseline·수정 금지 영역, 회귀 아님).

## v2.2.1 풀이 교정 18차 — 신살 궁성론(위치별 해석) 반영 ✅

- 요청: 신살은 원국 위치(궁성)·운 유입 레벨에 따라 의미가 다르다 — 검색 확인 후 시스템 반영.
- 검증: 웹 검색으로 궁성론 통설 확인(년=초년·조상/고향, 월=청년·직장/부모·작용력 최대, 일=장년·본인/배우자, 시=말년·자녀/내면; 역마·도화·화개는 年月=사회 vs 日時=개인/가정으로 발현 분기). 제미나이 내용과 일치.
- 현황: 엔진은 신살 위치(by_pillar) 이미 추적·_PALACE_ROLE 존재했으나, 해석부(_sinsal_excerpts)·사전(sinsal_text.json)에 위치별 발현 차이 없었음.
- 반영(사용자 확정 범위 = 주요 신살 byPosition + 공통 L1·L3·L4):
  - L2 데이터: sinsal_text.json 15종(역마·도화·화개·천을/천덕/월덕귀인·문창/문곡귀인·고신·과숙·양인·백호·괴강·홍염·현침)에 **byPosition{social(年月)/personal(日時)}** 저작. dictionaries.py에 SinsalByPosition 모델 + SinsalTextItem.by_position(선택). reviewed:false(감수 대상).
  - L1 프레임워크: chart_interpretation._sinsal_excerpts가 신살 위치(_SINSAL_PALACE_LABEL)를 표기하고, 자리에 사회궁(年月)/개인궁(日時)이 걸린 쪽 byPosition만 부착. _sinsal_positions(by_pillar 역색인).
  - L3 보정 지시: context_reducer._SINSAL_POSITION_INSTRUCTION — 위치 축 + 신살 자리의 충·형·공망(작용 정지/배가/무력화)·일간 용기신(반감/승화) 보정을 원국 관계·공망·용희기구한과 연결. chart_interpretation 동반 시 출력.
  - L4 운 신살 레벨: build_luck_grounding이 운 신살에 유입 레벨(대운=장기/세운=올해/월/일) 표기(_LUCK_LEVEL_KO).
- 효과: 같은 역마살이 연주(초년 사회이동)↔시주(말년 활동)로 갈리고, 천을귀인 사회조력·고신살 일몰두 등 byPosition 변주가 풀이에 반영. 라이브("신살 위치별") 확인.
- 검증: pytest 507 passed · ruff clean · mypy 내 코드 clean(기존 manse_core stub 2건 무관) · 사전 스키마 검증 45/45(byPosition 15).

## v2.2.1 풀이 교정 19차 — 운(運)에서 오는 신살 해석 ✅

- 요청: 운(대운·세운)에서 오는 신살은 원국 보유와 작용 방식이 다름(체질 vs 사건/자극) — 해석 추가.
- 원리(통설 확인): 운 신살은 원국 글자를 합·충·형으로 건드려 발동(작동 스위치), 대운=10년 무대·환경, 세운=그해 실제 사건. 길흉 3기준: ①희기 결합(희신+흉살=통제된 권력, 기신+길신=실속 약) ②원국 궁성(월지=직업/일지=배우자) 충돌 ③공망이 충으로 풀려 해방.
- 반영(18차 byPosition과 동일 15종 + 공통 지시):
  - 데이터: sinsal_text.json 15종에 **fromLuck**(운 도래 시 현실 징후) 저작. dictionaries.py SinsalTextItem.from_luck(선택). reviewed:false.
  - build_luck_grounding: 운 신살 서술을 manifestation 대신 **fromLuck 우선**(없으면 폴백) — 운 신살=사건 프레이밍.
  - 지시(L5): context_reducer._LUCK_SINSAL_INSTRUCTION — 운 신살=사건 타이머(체질 아님)·대운(환경)/세운(사건) 역할·합충형 발동(형충회합/궁성 연결)·길흉 3기준. period_fortune에 운 신살 있을 때 출력.
- 효과: '올해 운세'에서 천록귀인=수입 기반·도화=사회 주목·현침=신경 날카로움 등 운 신살이 '들어오는 사건'으로 서술. 라이브 확인.
- 검증: pytest 507 passed · ruff clean · mypy 내 코드 clean · 사전 검증 45/45(byPosition 15·fromLuck 15).

## v2.2.1 풀이 교정 20차 — 시점 미지정 미래지향 질문의 현재(올해) 앵커링 ✅

- 지적: '이직 제안 들어올까?'(시점 미지정) 답변이 과거 2025년을 '현재'로 서술하고 올해 2026을 건너뛰어 2025→2027로 점프.
- 진단: query_type=domain_analysis·time_range=None → filter_year_candidates가 시점 무관 고점 반환. 상위가 2025·2024(과거 90)·2031(먼 미래)이고 2026(career 85 positive)은 Top5에서 탈락. in_question_range가 time_range None일 때 전부 통과시켜 과거 고점이 메인 점유.
- 수정:
  - chat_service: 미래지향 질문(time_range None·query≠event_explanation·과거 키워드 없음) 감지 → default_period=(today.year, +2). 근미래 창 후보를 all_scored에서 보존(기존 P2 메커니즘 확장)해 2026/2027 누락 방지.
  - context_reducer.build_llm_input: default_period 파라미터 — time_range 없을 때 후보 reduce 창으로 사용(과거는 out_of_range 배경으로 분리).
  - _REFERENCE_INSTRUCTION 강화: 오늘보다 과거 기간은 '이미 지난 일'로 과거형 서술·예측 금지, 시점 미지정 질문은 올해+근미래 중심·올해 건너뛰기 금지.
- 효과: 메인 후보 2026·2027, 참고(배경) 2024·2025로 분리. 라이브('이직 제안')에서 올해 2026 병오년 중심→2027 전망, 2025는 진행 중 대운 교체 배경으로만.
- 검증: pytest 507 passed · ruff clean · mypy 내 코드 clean.

## v2.2.1 풀이 교정 21차 — 이벤트 감점(억제) 룰 도입 ✅

- 지적: 이벤트 신호가 가점뿐, 감점 요소 점검 없음 — 전 이벤트 점검 요청.
- 점검 결과: 전 사전 59룰 전부 가점·감점 0. 스키마 score ge=0.0이 음수 금지(docs/02는 'weight 양/음수 가능(공망 활성 -8)' 명시 — 구현이 설계보다 좁음). 기신 modifier는 max(…,0) 클램프로 감쇄만 가능, 공망도 가점(document 등)만.
- 반영(사용자 확정 = 핵심 감점 룰 일괄):
  - 스키마: EventCandidateSpec.score ge=-1.0(감점 허용), SignalSpec.relationAlso(복합 관계 조건 — relation과 동시 성립). 감점 룰 polarity=neutral 컨벤션(극성 집계 왜곡 방지).
  - 스코어러: _match_signal에 relationAlso 조건. 합산(total)에서 음수 기여가 자연 차감, 0 클램프·raw_total 정렬 기존 유지.
  - 감점 룰 11항목(16후보, 전부 reviewed:false): ①공망→결실·확정 감점(promotion/contract/marriage/windfall/income_change/exam/education_complete) — career_change.json은 기존 void 가점 항목에 병합(한 신호가 불안정 가점+결실 감점 양방향) ②탐합망충(branch_clash+six_combination)→career_change/relocation/travel 감점 ③천덕·월덕귀인→health_issue/surgery/lawsuit/expense_risk/speculation_risk 완화 감점 ④고신·과숙→relationship_start 감점.
- 한계(보고): ⑤'강한 인성+건록(안정)→이직 감점'은 십이운성 조건이 SignalSpec에 없어 보류. 탐합망충 매칭은 '같은 기간 동시 존재' 기준이라 같은 글자 경합보다 넓음(보수적 가중 -0.15~-0.25, 감수 대상).
- 효과: 샘플 차트 230후보 중 88개에 감점 신호 실림(raw_total 차감·약한 후보 점수 하락), LLM 입력 동반 신호에 '감점 — …' 표기.
- 검증: dict validate 0·lint 0 · pytest 507 passed(회귀 픽스처 상대순위 유지) · ruff/mypy clean.

## v2.2.1 풀이 교정 22차 — 십이운성 SignalSpec 조건 + 안정/리셋 modifier 룰 ✅

- 요청: 십이운성 조건 확장 스펙(JSON) 반영 — 21차 보류분('인성 강+건록 → 이직 감점') 해소. 재미 위주 그룹명은 서빙 적합어로 대치(응애존→성장기, 청년기→왕성기, 노년존→쇠퇴기, 세포존→재생기).
- 스키마(dictionaries.py):
  - SignalSpec 4조건 추가: unseong(운 유입 글자 운성)/natalUnseong(원국 월·일주 운성)/tenGodGroupStrong(십성군 강 — 인성·비겁·식상·재성·관성)/absentRelations(does_not_apply_when — 충·형 등 외부 강트리거 동반 시 룰 미적용).
  - common/twelve_unseong_groups.json 신설(12운성 stability·changeDrive·도메인 bias + 4그룹, 그룹명 정제, reviewed:false) + TwelveUnseongGroupsFile 스키마 등록.
- 스코어러(event_scoring.py): _strong_ten_god_groups(force_analysis.ten_gods.groups percent>=30 → 강), _PeriodContext에 natal_unseongs(월·일주)/strong_groups 주입, _match_signal에 4조건.
- 룰 6건(reviewed:false, modifier 전용 — 가중을 낮게 저작해 합충형파해·공망·용기신보다 자연 하위):
  - career: 인성강+운건록 -0.12 / 인성강+원국건록 -0.12 (둘 다 absentRelations로 충·형 시 미적용) / 운절 +0.10 / 운사 +0.06 (가점은 conditional — 리셋성 전환).
  - relocation: 운건록 -0.07(정착) / 운절 +0.08(리셋).
- 실측: 인성 19% 차트 → 감점 미발동(정확). 午=기토 건록 → 2026 병오·6월 갑오 relocation 정착 감점. 인성강+월주건록 차트(1975-06-20) → career 감점 발동(2027 점수 0). scoring_policy(우선순위 하위·modifier 전용) 준수.
- 검증: dict validate 0·lint 0 · pytest 507 passed · ruff/mypy clean.

## v2.2.1 풀이 교정 23차 — 유효 창 현재 달 클램프(지속 시점 오류 근본 수정) ✅

- 지적: '이직 제안(무시점)'·'올해 연애' 답변이 이미 지난 2026년 4·5월을 다가올 트리거처럼 서술 — 한 해 전체를 미래로 잡는 지속적 시점 오류.
- 진단: ①'올해'(2026) 창=1~12월이라 지난 4월 후보(임진월 정임합 등)가 '기간 내' 메인으로 서빙 ②무시점 default_period도 연 단위(2026~2028)라 1~5월 포함. 20차 수정(과거 연도 분리)은 연 단위만 다뤄 '올해 안의 지난 달'을 놓침.
- 수정(엔진/데이터 차원 — 프롬프트 지시 의존 금지 원칙):
  - chat_service P6: 유효 창 시작을 '오늘이 속한 달'로 클램프. 무시점 → (현재 달, +2년). 질문 창이 '과거 시작+미래 포함'(올해 등)이면 (현재 달, 원래 끝). 과거 회고(event_explanation·_PAST_KEYWORDS)·전체 과거 창은 클램프 제외. P2 보존 블록도 유효 창 기준.
  - build_llm_input: default_period(유효 창)가 후보 축소에서 질문 창보다 우선(기준 시점 표시는 원래 창 유지).
  - build_reference_frame: 창이 과거~미래에 걸치면 '이 중 X~Y는 이미 지남(과거형으로만·앞으로의 권고 금지) — 남은 구간 Z~W' 데이터 노트(_prev_month 헬퍼).
  - 직렬화 '지남' 마커: 기간 외 후보 블록에 '※ 위 기간은 이미 지났다', 월별 요약 행에 '· 지남(과거형으로만)' — 현재 달은 reference.today에서 산출.
- 효과: '올해 연애' → 메인 후보 없음(남은 6~12월 기준) 정직 안내 + 2022/2025 과거형 배경, 4월 미래 둔갑 소멸. '이직 제안' → 메인 2026·2026-06~08·2027. '2025년 8월' 과거 회고는 비클램프 유지.
- 검증: pytest 507 passed · ruff/mypy clean · dry-run 3종 창 확인 · 라이브('올해 연애') 확인.

## v2.2.1 풀이 교정 24차 — '지난 N년/개월' 과거 롤링 창(시점 처리 5단계) ✅

- 지적: '지난 1년내 재취업한 달은?'에 2026년 1·4·5월을 꼽고 '2025-06~12 데이터 미제공' 회피 — 과거 방향 롤링 창 누락(15차는 미래 방향만).
- 진단: time_parser에 '지난/최근 N년·N개월·반년' 규칙이 없어 time_range=None → 후보가 시점 무관 고점(기본 월운 창 2026 월들)으로 흘러감. 월별 표도 질문 창과 불일치.
- 수정:
  - time_parser C8b: '지난/최근 N년·N개월·반년' → 현재 달 포함 직전 N개월 절대 창(예: 지난 1년=2025-07~2026-06), scope=PAST. 숫자 없는 '지난달/지난해' 단수는 비처리(오인 방지).
  - chat_service: wants_monthly에 다중 월 창 분기(start·end 모두 YYYY-MM이고 다르면 _months_between으로 질문 창 그대로 표, 상한 13). 창 스코어 후보(scored_win)를 메인 후보에도 보존 — 표와 근거 경로가 같은 달을 가리키게.
  - 직렬화: 월별 요약 헤더 '12개월' 하드코딩 → 실제 행 수.
- 효과: 표 2025-07~2026-06 12행, 메인 후보 2025·2025-07~09·2026(미래월 오염 0). 라이브: 2025년 7월 최유력 + 8·9월 비자발 비교 + 2026년 1월 보조 — 전부 과거형, '미제공' 회피 소멸. 8월 甲申 비자발 구분은 13차 회귀와 일관.
- 기존 보존: '지난달'(단수) 비처리, '앞으로 1년' 미래 롤링, '2025년 8월' 절대 월, 23차 클램프(과거 키워드 제외) 모두 유지.
- 검증: pytest 507 passed · ruff clean · mypy clean(기존 manse_core stub 2건 외 0) · 라이브 확인.

## v2.2.1 풀이 교정 25차 — 교운기 가중의 표면화(점수 cap 포화 보완) ✅

- 지적: '지난 1년 재취업' 답변에서 대운 교운기 가점이 모두 무시된 듯 — 교운 근접 달(2025-10~12)이 부각되지 않음.
- 진단: 교운 가중은 내부적으로 정확(교운일 2025-11-14 중심 첨도 분포, w 39~55). 그러나 월운 점수가 _LEVEL_CAP(75)에 전월 포화 → 표·톤이 전부 '가능성이 높습니다'로 동일해져 교운 근접 차이가 LLM 입력에서 소실. cap(위계 모델, 사용자 확정)은 유지하고 교운 근접도를 데이터로 표면화.
- 수정:
  - event_scoring: 교운 신호 effect에 근접도 라벨 부기 — _transition_label(w): ≥0.8 '정점권(교운일 임박·직후)' / ≥0.5 '근접' / 그 외 '영향권(완만)'. 후보 동반 신호(signals_ko)에서 차등 변별.
  - MonthOverviewRow.transition 필드 + build_monthly_overview에서 교운일 거리 기반 라벨(≤45일 '대운 교체 정점' / ≤180 '대운 교체기' / ≤365 '영향권') — 엔진 가중 모델과 동일 거리 기준.
  - 직렬화: 표 행에 '· 대운 교체 정점' 등 표기 + 사용 노트('같은 강도의 달이 여럿이면 교운 근접 달을 우선 지목').
- 효과: 표에서 2025-10~12 '정점' 차등 노출. 라이브: '갑작스러운 변화라는 측면에서 가장 뚜렷한 구간은 대운 교체일 2025-11-14 전후' — 7월(우호 시작)→8·9월(정체)→11월(교운 폭발=재취업) 서사로 질문 의도('갑작스럽게')와 정합.
- 검증: pytest 507 passed · ruff/mypy clean · dry-run 표 라벨·라이브 확인.

## v2.2.1 풀이 교정 26차 — 월별 표 상대 강도 순위·사건 우열 표기 ✅

- 지적: LLM 입력 프롬프트만 봐서는 '진짜 중요한 달'을 알 수 없음(전월 '가능성이 높습니다' 포화). 달 내 사건 나열('이사 / 이직')이 발생 가능성 순이라는 의미도 무시됨.
- 수정(절대값보다 상대 순위 신뢰 — docs/07 원칙의 표면화):
  - MonthOverviewRow.strength_rank — 창 내 달별 최강 후보의 raw(클램프 전) 기준 상위 3위 산출(build_monthly_overview).
  - 직렬화: '★기간 내 강도 1위'/'2위'/'3위' 마커, 사건 나열 구분자 ' / '→' > '(앞이 우세).
  - 표 읽는 법 노트 통합: '>' 의미 + 'N위가 실제 상대 순위 — 가장 유력한 달은 1위부터' + 교운 표기 의미(25차 노트 흡수).
- 효과: 표에서 1위 2026-05·2위 2025-08·3위 2025-11 즉시 변별. 라이브: '가장 강렬하게 분출된 시점은 2026년 5월(강도 최고)' → 2025-11 교운 정점 보조 → 2025-08 비자발 비교 — 데이터 순위가 답변 구조로 직결.
- 참고: 순위는 reviewed:false 가중 초안 기반 결정론 산출 — 도메인 직관과 다르면 가중 튜닝 대상(cases.jsonl 축적 후).
- 검증: pytest 507 passed · ruff/mypy clean · dry-run 표·라이브 확인.

## v2.2.1 풀이 교정 27차 — 운 천간 구신의 유불리 반영(발생 강도와 분리) ✅

- 지적: 2026-05(癸巳)는 계수=구신이라 계약 등에 불리해 이동하면 안 되는 달인데, 이벤트 스코어에 반영됐는지?
- 진단(부분 반영 + 누락 2건):
  - 반영돼 있던 것: polarity 조건부(극성 종합 모델), 결실류 저점(contract 24·document 54, 공망 감점).
  - 누락 ①: 천간 癸(구신) 자체가 career 점수 기여에 전무 — 기여 전부가 지지 巳(희신) 관계·교운·공망. ②버그: 과거 창 월 후보의 간지가 빈 값('@ 2025-07(,') → incoming_note('癸 편재(水 구신)') 월 후보에 누락 — ganji lookup이 원본 result(기본 월운 창)만 봄. ③표가 발생 강도 순위만 노출해 '유리한 달'로 오독.
- 수정:
  - (버그) chat_service result_for_llm — on-demand 월운 주입본(result_win/result_year)을 build_llm_input에 전달 → 창 월 간지·해석 줄 복원(2025-07 癸未 등 5건).
  - 표 행에 간지 용기신 역할 표기: MonthOverviewRow.luck_roles('癸水 구신·巳火 희신') + 표 읽는 법에 '천간 구신·기신 달은 발생해도 계약·결실·실속에 불리 — 좋은 달로 단정 금지(발생 강도와 유불리 구분)'.
  - SignalSpec.stemFavorability(운 천간 오행 용기신 단독 조건) + 감점 룰: 천간 구신 → contract -0.2·document -0.15(reviewed:false, 사용자 도메인 지식). 효과: 2026-05 contract 24→12·document 54→45.
- 검증: dict validate/lint 0 · pytest 507 passed · ruff/mypy clean · 라이브 미래 권고형('이직 좋은 달·피할 달')에서 강도 1위 달(2027-05)을 추천이 아닌 '조건 까다로움' 경고로 구분 — 발생 강도/유불리 분리가 답변 구조에 구현됨.
- 메모: 발생 회고형('성공한 달은?') 답변에서는 구신 코멘트가 생략될 수 있음(질문 성격상) — 권고형에서 분리가 작동하는 것이 핵심.

## v2.2.1 풀이 교정 27차 보완 — 천간 기신 감점 룰(기신·구신 대칭) ✅

- 정정: 27차는 구신만 저작 — 의도는 천간이 '기신 또는 구신'일 때의 감점 요인 점검.
- 점검: 기신 천간 기존 반영 = 관계 기여 modifier(-0.2, 0 클램프 감쇄)·polarity 종합(neg+0.4)뿐 — 결실류 감점 룰 부재. 실측: 2026-06(甲午, 甲=木 기신) contract 75점 방치(구신 달 2026-04 contract 0과 비대칭).
- 수정: {stemFavorability:"기신"} → contract -0.25·document -0.2 (기신은 용신을 직접 극 — 구신(-0.2/-0.15)보다 강하게, reviewed:false). 효과: 2026-06 contract 75→70·document→0. 잔여 점수는 정관합 등 발생 신호 — '불리한 계약 사건 발생 가능성'로 polarity(negative_or_forced)가 유불리 담당(score=발생/polarity=유불리 원칙 일관).
- 검증: dict validate/lint 0 · pytest 507 passed · ruff clean.

## v2.2.1 풀이 교정 28차 — 미발동 글자의 용기신 기본 가감(일반 원칙) ✅

- 사용자 원칙: "천간·지지에 들어온 글자가 합충형파해 등 어떤 형태로도 가점·감점에 기여하지 않은 경우, 용신·희신·기신·구신 여부에 따라 가감될 수 있다."
- 기존: 미발동 글자의 용기신 역할은 극성 종합·표시(incoming_note)에만 반영 — 점수 기여 0.
- 구현:
  - 사전: common/ten_god_events.json 신설 — 십성→대표 이벤트 매핑 9종(비견·식신→business_start, 상관·편관·정관→career_change, 편재·정재→income_change, 편인→education_start, 정인→document). 리스크형 이벤트(손재·송사)는 가감 방향이 반대라 1차 제외(겁재 미등재, note 명시). TenGodEventsFile 스키마 등록.
  - 스코어러: _PeriodContext.stem_anchored/branch_anchored 플래그 — 관계 기여(천간합=stem/그 외=branch)·매핑 룰 매칭(tenGod·stemFavorability=stem / branchTenGod·shinsal·unseong=branch) 시 기록. _baseline_contributions: 미발동 글자만 — favorability_rules modifier 재사용(용신+0.2/희신+0.1/기신-0.2/구신-0.15, 한신·무매핑 십성 제외) × 레벨 가중. polarity: 가점=positive/감점=neutral. 신호 type='baseline_favorability', effect '미발동 글자 기본 가점/감점 — 천간 己(土 용신) 비견: …'.
- 효과: 미발동 용신 己→business_start +20, 희신 丙·丁→document/education +10, 기신 卯(편관)→career_change -20. 발동 글자는 제외(8/238 후보만) — 베이스라인 < 트리거 위계 유지(±10~25 raw vs 발동 60~80).
- 검증: dict validate/lint 0 · pytest 507 passed(회귀 상대순위 유지) · ruff/mypy clean. 매핑·계수 reviewed:false(감수 대상).

## v2.2.1 풀이 교정 29차 — 유불리가 풀이에 미반영되던 잔여 결함 2건 ✅

- 지적: 프롬프트(표 역할·각주)는 수정됐으나 풀이가 여전히 1위 달(癸巳)을 '계약·문서 기회'로 우호 서술.
- 진단(근본 원인): ①**후보 선별(reduce_candidates)이 raw_total 무시** — (-score, 기간 오름차순) 정렬이라 동점(75) 중 이른 달(2025-07~09)만 Top5에 들고, 강도 1위 2026-05는 후보 블록에 아예 없음 → '癸(水 구신)' 해석 줄이 LLM에 미전달. ②표 각주는 지지 희신 서사에 묻혀 무시됨.
- 수정:
  - reduce_candidates 정렬에 -raw_total 추가 — 후보 선별이 표의 '기간 내 강도 N위'와 같은 달을 가리킴(후보: 2026-05·2025-08·2025-11 = 표 1·2·3위 일치).
  - 표 행 역할에 천간 흉신 경고 직접 부착: '[癸水 구신·巳火 희신 ⚠계약·결실 불리]'.
  - LlmEventCandidate.caution_note(후보별 사실 데이터) + 직렬화 '⚠유불리:' 줄 — 천간 기·구신 후보에 '사건이 일어나도 계약·결실·실속에 불리(조건 악화·소모 주의), 우호적으로만 서술 금지'.
- 효과(라이브): "가장 눈에 띄는 변화는 2026년 5월 … 다만 천간의 계수가 구신으로 작용해 계약 조건이 까다로웠거나 실속 면에서 고민이 따랐을 수 있지만…" — 1위 지목+유불리 단서가 한 문단에 완결. 11월(교운 정점·비자발)·8월(기신 정관합 배치변경) 차등 서술 유지.
- 검증: pytest 507 passed · ruff/mypy clean · 라이브 확인.

## v2.2.1 풀이 교정 30차 — 계사월 케이스 일반화: 중복 충·대운 공망·검토월 ✅

- 사용자 도메인 풀이(2026-05 계사월에 이동하면 안 되는 이유)를 일반 룰로 정리·반영:
  - G1 **중복 충 불안정**(스코어러 _instability_contributions): 같은 운 글자가 원국 2글자 이상과 동일 충(巳亥沖×2 등)이면 변동 과다·결정 불안정 — 발생 점수(career/relocation)는 유지, 결실류 감점(contract -0.15·document -0.1, 레벨 가중). '이동수는 켜져도 계약 유지력 약화'.
  - G2 **대운 지지 공망 배경 제약**: SignalSpec.daewoonBranchVoid 조건 신설(_PeriodContext에 daewoon_branch·natal_void 주입) + 룰: contract -0.15/document -0.1/relocation -0.1 — 대운 전 기간 새 계약·환경 진입 실속 부족·지연(임진 대운 辰=공망 케이스).
  - G3 **검토월 표면화**: 후보에 불안정 신호(중복 충·공망 계열) 동반 시 ⚠유불리에 "'실행월'이 아니라 '검토월'(조사·조건 확인까지)" 부기 — judgement {movement high, contract_stability low}의 데이터 표현.
  - (공망 글자 재등장 감점은 기존 21차 반영 확인 — 중복 저작 안 함.)
- 효과: 2026-05 contract 12→0·document 45→33, career 75 유지(발생/유불리 분리 원칙 일관). 후보 블록에 구신+검토월 명시.
- 검증: dict validate/lint 0 · pytest 507 passed · ruff/mypy clean. 룰 reviewed:false.

## v2.2.1 풀이 교정 31차 — 유력 달 종합 블록 + Gemini 프리뷰 장애 발견·전환 ✅

- 지적: 표·후보 데이터는 완비됐는데 풀이에 '8월=이사 우세'·'2026-05 검토월'이 계속 미반영.
- 원인 2중:
  ① 정보가 표·후보·각주에 분산돼 LLM이 서사에서 일부 누락(비결정).
  ② **gemini-3-flash-preview 서비스 장애(503/응답 행 — 11.9k 프롬프트에서 180s+ 타임아웃)** → 모든 라이브 응답이 GPT-5 mini 폴백으로 처리되고 있었음(Trigger/진행/결과 문체·내부 표기 노출이 단서). 단순 프롬프트는 정상이라 장애가 가려짐.
- 수정:
  - **[유력 달 종합] 블록**(직렬화, 엔진 사전 종합): 순위·우세 사건(2순위 포함)·성격·간지 역할·교운을 달별 한 줄로 — '답의 골자, 누락 금지'. ⚠ 보유 달엔 '검토월 성격(우호 서술 금지)', 질문 사건≠우세 사건이면 '※ 이 달의 주된 신호는 X — 질문 사건은 동반 신호로만'(regression_2025_08 데이터화).
  - **모델 전환**: config/llm_config.json primary gemini-3-flash-preview → **gemini-2.5-flash**(thinkingBudget 512 = LOW 상당, 절대 원칙 9). 실측: 동일 프롬프트 7.6s OK vs 프리뷰 503. note에 원복 검토 명시.
- 효과(라이브): "2026-05 … 癸水 구신 때문에 계약·결실·실속 불리 — 실행월이 아니라 검토월" + "2025-08 … 월별 요약에서는 이사 신호가 더 우세, 이직은 동반 신호" + 2025-11 교운 정점·계약 유지력 낮음 — 지적 2건 완전 반영.
- 검증: pytest 507 passed · ruff clean · 라이브 확인.
- 운영 메모: 프리뷰 모델 장애 시 폴백이 무음으로 대체하므로, 응답 문체 급변(구조체 영어 헤더 등)은 폴백 신호로 볼 것. 모델 헬스 체크/폴백 알림은 추후 운영 과제.

## v2.2.1 풀이 교정 32차 — 과거 개방형 회고(공백기 탐색) 경로 ✅

- 지적(대화 3턴 다발 결함): ①'오래 쉬었던 기간 언제였을까'가 올해(2026) 데이터로만 답하고 '2026 이전 데이터 미제공' 자백 ②후속 단답 '년단위였어'가 too_broad 거절(엉뚱한 연애운 제안) ③턴 간 모순(1턴 2026-05 재취업 성공 ↔ 2턴 같은 기간 공백기).
- 이번 수정(①):
  - _PAST_KEYWORDS에 과거형 어미 추가('였을까/었을까/았을까/였던/었던/았던/였지/었지') — 미감지 시 과거 질문이 미래 창(+2년)으로 클램프되던 근본 원인.
  - 과거 회고 + 시점 미정(open_when 포함) → default_period=(today-10년, 현재 달) 과거 창 앵커링.
  - **연도별 흐름 표**: 과거 회고 timing_search에 과거 10년(세운 데이터 있는 연도로 클립) 연도별 표 — build_monthly_overview를 연 라벨('YYYY')도 받게 일반화(매칭·교운 중점·헤더 분기), '점수 낮은 해=신호 없던 해' 노트로 공백 연도(2023 '뚜렷한 신호 없음')가 데이터로 드러남.
  - 연 라벨 '지남' 마커 비교 보정(현재 연도 오표기 제거).
  - 모델 전환(31차) 추종: test_llm_client_failover의 하드코딩 모델명 → '단일 파일 계약'만 고정하도록 완화.
- 효과(라이브): '미제공' 회피 소멸 — 2022·2024·2025 비자발 변화 흐름 + 연도별 표 기반 서술.
- 검증: pytest 507 passed · ruff/mypy clean · dry-run 표·라이브 확인.
- 남은 과제(보고): ②후속 단답('년단위였어') 질문 링킹 미발동 — ConversationEngine 단답 상속 점검 필요. ③턴 간 모순 — state에 등록된 이전 시스템 claim을 후속 턴 프롬프트에 '[이전 답변 결과 — 모순 금지]'로 주입하는 작업 필요.

## v2.2.1 풀이 교정 33차 — 멀티턴 모순 방지 + 후속 단답('년단위였어') 링킹 ✅

- (④ 턴 간 모순) LlmInput.prior_claims + 직렬화 '[이전 답변에서 이미 제시한 엔진 결과 — 모순 금지(같은 기간을 다른 사건·성격으로 뒤집지 말 것, 어긋나면 차이를 명시)]' 블록. chat_service가 후속 턴에서 state.last_results(T4.5 claim 등록분)를 한글화(event_ko)해 주입.
- (③ 단답 링킹) '년단위였어' too_broad 원인 3중 수정:
  - conversation.link_question 2순위 시간 단서에 '[년연월주일]\s*단위' 추가(TIME_SHIFT).
  - query_parser B2b: 단위 정정 단답은 time_range 미파싱이어도 직전 intent 상속 + granularity만 갱신(년→YEAR 등, open_when 보존).
  - chat_service is_retro에 open_when 포함 — 후속 단답엔 과거 어미가 없어도 상속 intent로 과거 회고 식별.
- 라이브 3턴 검증(thread_id): 1턴 재취업 성공 달 → 2턴 공백기 질문이 '2026 공백' 모순 없이 2024 甲辰(기신 정관·비자발·계약 불리→재취업 곤란)·2025 압박 이탈로 일관 서술 → 3턴 '년단위였어' answered("지난 답변에 이어 년 단위 흐름…", 2023 무신호 연도 언급).
- mypy 변수 충돌(r 재사용) 정리(mr), 게이트: pytest 507 passed · ruff clean · mypy 0(기존 stub 2건 외).

## v2.2 프론트 확장 Phase 1 — 계정(ID+PIN)·사주·프로필·페르소나 API 노출 ✅

- 배경: 프론트가 단일 프로필(IndexedDB)뿐이라 다중 사주목록·테마사주·AI상담 흐름이 불가.
  백엔드 stores(SubjectStore/ProfileStore/ConversationStore)·shared_types는 갖춰졌으나 API
  미노출. 사용자 승인 계획(`.claude/plans/iridescent-munching-pie.md`) 기준 단계별 PR 진행.
- 결정(사용자 승인): ①인증=ID+PIN 경량(OAuth 추후 대치, 같은 ID+PIN→같은 owner_id로 사주
  연속성), PIN은 pbkdf2-sha256 해시. ②저장=로그인 사용자 PostgreSQL n사주 / 비로그인 무료
  IndexedDB 1사주. ③페르소나=계정 전역 1개(궁합 충돌 방지), 물상·용신=사주별(user_profiles를
  subject_id로 키잉). ④리포트 PDF=클라이언트 인쇄(MVP). ⑤리포트 생성=비동기 잡(후속 Phase).
- 신규:
  - `migrations/005_accounts_and_settings.sql`: accounts(owner_id PK, login_id UNIQUE, pin_hash),
    account_settings(owner_id PK, persona), user_profiles.confirmed_yongsin 컬럼 가산(멱등).
  - shared_types `account.py`: AccountRecord/Credentials(login_id·PIN 패턴)/AuthToken.
  - saju_engines `auth_store.py`(AccountAuthStore: register/verify/get, pbkdf2 해시),
    `account_store.py`(AccountSettingsStore: get/save_persona), `profile_store.py`에
    set/get_yongsin 가산.
  - apps/api `deps.py`: HMAC 서명 세션 토큰(make/parse_token)·owner_id 해석(require/optional_owner)·
    저장소 프로바이더(DSN 미설정→503). 인증 교체가 본 모듈 한 곳에 격리.
  - 라우터: `auth.py`(/register·/login·/me), `subjects.py`(CRUD+목록 등록여부 인디케이터,
    owner 격리), `profile.py`(subject_id 키 GET/PUT/필드삭제, persona 스냅샷), `account.py`
    (/persona GET·PUT). main.py 배선 + CORS에 PUT/DELETE 추가.
- 검증: ruff clean · mypy clean(91 files) · 신규 `test_accounts_subjects_api.py` 6 pass(토큰
  라운드트립·변조 거부·PIN 해시·401 게이트·Credentials 검증) + 1 skip(전용 DB 미기동 시 CRUD
  전체흐름). 기존 test_api/report/profile 회귀 없음. 라우트 등록 확인(8개 신규 엔드포인트).
- 환경 메모: 본 WSL에서 Docker 통합 미활성 → 전용 DB(5433) 기동 불가로 CRUD 통합테스트는
  skip 처리(스토어 테스트 관행과 동일). DB 기동 환경에서 전체흐름 검증 필요.

## v2.2 프론트 확장 Phase 2 — 프론트 데이터 계층 ✅

- 신규: `lib/auth.ts`(토큰 localStorage 보관·login/register/fetchMe·authHeaders), `lib/types.ts`
  확장(BirthInputDTO·AuthToken·AccountRecord·PersonaConfig+DEFAULT_PERSONA·ExtendedProfile·
  BasicProfile·SubjectSummary/Upsert·ProfileResponse/Upsert·SubjectRef·ReportSpec·
  ReportJobStatus — 모두 백엔드 snake_case와 1:1), `lib/subject-mapping.ts`(profileToBirthDTO/
  summaryToProfile/profileToBasic — Profile↔BirthInput, male/female↔M/F, HH:MM:SS→HH:MM,
  저장용은 reference_date 제외), `lib/subjects.ts`(사주 CRUD·프로필·페르소나·리포트잡 래퍼).
- 변경: `lib/api.ts` — request() 공통화로 모든 호출에 인증 헤더 자동 첨부(토큰 없으면 비로그인),
  getJSON/putJSON/deleteJSON 추가, 204 처리, postChat에 persona 인자.
- 검증: tsc 0 · vitest 13 pass(신규 subject-mapping 5: 라운드트립·양음력·시각 트림·M/F 매핑) ·
  프로덕션 빌드 성공.

## v2.2 프론트 확장 Phase 3 — 앱 셸(GNB·프로바이더·ID/PIN 로그인) ✅

- 신규: `components/providers/AuthProvider.tsx`(ID+PIN 인증 컨텍스트, lib/auth 위임),
  `SelectedSubjectProvider.tsx`(선택 사주·동반자 sessionStorage 캐시), `Providers.tsx`(묶음),
  `components/layout/Gnb.tsx`(햄버거→좌측 드로어: 선택 사주 칩·무료/유료 메뉴·사주목록·설정·계정),
  `AuthPanel.tsx`(로그인/등록 폼, 비로그인 유료항목 '로그인 필요' 뱃지).
- 변경: `app/layout.tsx` — Nav 제거, Providers로 감싸고 Gnb 마운트(레이아웃은 서버 컴포넌트 유지).
- 검증: tsc 0 · vitest 17 pass(신규 auth 4: 토큰 보관·헤더 주입·에러 detail·로그아웃) · 빌드 성공.
- 참고: /themes·/sajus·/settings 라우트는 후속 Phase에서 생성(드로어 링크 선반영). Nav.tsx는 미사용.

- (DB 검증 추가) Docker 기동 후 마이그레이션 001~005 적용(컨텍스트 매니저 커밋 보장),
  test_accounts_subjects_api 7 pass(스킵 해제 — 등록→사주생성→프로필→페르소나→owner 격리→삭제
  전체 흐름) + 전체 백엔드 스위트 회귀 없음.

## v2.2 프론트 확장 Phase 4 — 게이트웨이·사주목록·랜딩 ✅

- 신규: `components/subject/SubjectCard.tsx`(별명+생년월일시+용신/물상 인디케이터+액션),
  `SubjectGateway.tsx`(선택/추가/동반자 단계, 비로그인 안내), `app/sajus/page.tsx`(목록 관리:
  추가→온보딩, 수정→온보딩, 삭제→스낵바 되돌리기(5s 후 확정)).
- 변경: `app/page.tsx` 랜딩 개편 — 사주목록 진입 + 무료(만세력·간지달력)/로그인전용(테마사주·
  AI상담) 구분, 비로그인 '로그인 필요' 뱃지.
- 검증: tsc 0 · 빌드 성공(/sajus 추가). 게이트웨이는 만세력(P5)·테마(P7)·채팅(P8)에서 배선 예정.

## v2.2 프론트 확장 Phase 5 — 온보딩 위저드 + 만세력 subject 소비 ✅

- 신규: `components/onboarding/`(StepShell 진행바, StepBirth=BirthForm+별명, StepYongsin=
  calculateManse+YongsinPanel+CalibrationPanel, StepMulsang=O01~O18·거주·혼인, StepPersona=5축
  유효조합/호칭 제약 게이팅, Wizard 오케스트레이터), `app/onboarding/page.tsx`(?mode=add|edit|
  oneoff&subject=&next=, Suspense), `lib/onboarding-constants.ts`(직업/고용/혼인 목록).
- 변경: `components/manse/BirthForm.tsx`에 initial(프리필)·heading·submitLabel·children 슬롯 가산
  (기존 호출 호환). `app/manse/page.tsx` — 로그인:게이트웨이→결과(?subject=) / 비로그인:IndexedDB
  1회성. `app/manse/result/page.tsx` — resolveProfile()로 ?subject 우선, 없으면 IndexedDB.
- 동작: add=createSubject+saveProfile(subject_id)+savePersona(계정), edit=프리필→update, oneoff=
  IndexedDB 저장→결과. 용신/물상/페르소나 스킵 가능(스킵 시 유력 후보/기본값).
- 검증: tsc 0 · vitest 17 pass · 빌드 성공(/onboarding 추가).

## v2.2 프론트 확장 Phase 6 — 리포트 비동기 잡 + FOCUS topic 스코핑(백엔드) ✅

- 비동기 잡: `migrations/006_report_jobs.sql`(report_jobs: status queued/running/completed/on_hold/
  failed·진행·결과·사유), `report_job_store.py`(create/mark_running/update_progress/complete/fail/get),
  `routers/report.py` POST /jobs(subject_id로 대상 출생·소유 검증→BackgroundTasks 생성→202)·
  GET /jobs/{id}(소유자 한정 폴링). dry-run 동기 POST는 유지. LLM 키 미설정 시 잡 failed(사유 보존).
- topic 스코핑: `report_plan.py` _FOCUS_TOC의 'MODULE' 플레이스홀더를 주제 모듈로 해석
  (_TOPIC_MODULE: career→M07·wealth→M09·compatibility→M13 등). `report_service.py` _ReportData가
  EventKey→도메인(_EVENT_DOMAIN) 매핑으로 FOCUS 후보를 주제별 필터(직장운≠금전운 본문, 도메인
  후보 없으면 전체 폴백). 섹션 구성(22/8)은 불변.
- 검증: ruff clean · mypy 92 clean · 신규 test_report_topic_scoping 3 pass(M07/M09/M13 해석·8섹션
  불변·dry-run) + test_report_jobs_api 2 pass(401 게이트 / DB: 생성→폴링→failed(LLM 미설정)·owner
  격리; LLM은 is_available 패치로 미호출). 전체 백엔드 스위트 회귀 없음.
- 한계(보고): 궁합(compatibility)은 generate_report가 단일 차트 기반이라 두 명식 쌍방(M13) 본문은
  후속 과제. 현재는 본인 차트 기준 리포트가 생성된다.

## v2.2 프론트 확장 Phase 7 — 테마사주 UI(4종) + 리포트 뷰어/PDF ✅

- 신규: `lib/themes.ts`(THEMES 4종: 총운/궁합/직장운/금전·횡재운, buildReportSpec=인생전반 기간
  출생년~+90·동반자 ref), `app/themes/page.tsx`(서브메인), `app/themes/[topic]/page.tsx`(게이트웨이
  +궁합 동반자→createReportJob→/reports/jobId), `app/reports/[jobId]/page.tsx`(3s 폴링·진행바·실패
  안내·완료 시 뷰어), `components/reports/ReportPager.tsx`(섹션 페이저, @media print 전체 출력),
  `PdfExportButton.tsx`(window.print). 변경: `lib/subjects.createReportJob(subjectId,spec)`.
- 검증: tsc 0 · vitest 22 pass(신규 themes 5: 4종·기간 유도·동반자 ref) · 빌드 성공
  (/themes·/themes/[topic]·/reports/[jobId]).

## v2.2 프론트 확장 Phase 8 — AI채팅 재배선 + 설정 ✅

- 변경: `app/chat/page.tsx` — 로그인 게이트 + SubjectGateway로 선택 사주 사용(summaryToProfile),
  계정 페르소나(getPersona) 전달, 선택 변경 시 대화 초기화. need_subject 안내 보강.
- 신규: `app/settings/page.tsx` — 페르소나(계정 전역) 편집·저장, 물상해석(사주별) 선택·편집·필드별
  삭제(deleteExtendedField). 물상 저장 시 basic은 subject에서 유도(display_name=label 10자 클립),
  confirmed_yongsin 보존. 정리: 미사용 Nav.tsx 삭제.
- 검증: tsc 0 · vitest 22 pass · 빌드 성공(/settings 추가, 전 라우트 정상).

### 전체 요약 (Phase 1~8 완료)
- 백엔드: 계정(ID+PIN)·사주·프로필·페르소나·리포트잡 API + topic 스코핑. 마이그레이션 005·006.
  게이트: ruff/mypy clean, 전체 pytest 통과(신규 12 — 토큰/PIN/CRUD/잡/스코핑, DB 연동 검증).
- 프론트: GNB 드로어·ID/PIN 로그인·다중 사주목록·온보딩 4모듈 위저드·만세력 subject 소비·
  테마사주 4종(폴링·페이저·PDF 인쇄)·AI채팅 재배선·설정. 게이트: tsc 0, vitest 22 pass, 빌드 성공.
- 미해결(보고): 궁합 쌍방(M13) 본문은 단일 차트 기반(후속). 리포트 PDF는 클라이언트 인쇄(MVP),
  서버 docx→pdf는 후속(docs/10 8장). 실 LLM 키 환경에서 리포트 완료 경로 라이브 검증 권장.

## v2.2 프론트 확장 — 내 풀이 내역(구매·결과 재확인 + PDF) ✅

- 배경: 로그인 사용자가 생성한 풀이(구매내역·결과)를 다시 보고 PDF로 출력할 진입점 필요.
- 백엔드: `report_job_store.list_by_owner`(owner별 최신순 메타 — result 제외), `routers/report.py`
  GET /api/v2/report/jobs(ReportJobSummary: product_code·topic·subject_labels·status·created_at,
  spec에서 추출). 소유자 한정.
- 프론트: `lib/subjects.listReportJobs`, `lib/themes.themeLabel`(product/topic→테마명),
  `app/reports/page.tsx`(내역 목록·상태칩·상세 링크), 상세 뷰어 헤더에 테마·대상 표기(재확인),
  GNB 드로어에 '내 풀이 내역' 링크(로그인 시). 열람·PDF는 기존 /reports/[jobId] 재사용.
- 검증: ruff/mypy clean · test_report_jobs_api 목록 단언 추가(생성 잡이 내역에 노출·메타 일치)
  9 pass · tsc 0 · 빌드 성공 · 터널 라이브(빈 목록 200·미인증 401) 확인.

## v2.2 용신 검증 질문 개선 — 연도별 이벤트 나열 + 이벤트별 긍/부정 ✅

- 배경: 한 해를 한 문장(overall_rating)으로 묻던 검증을, 그 해 검출 이벤트를 나열해 이벤트별
  긍/부정을 받아 모델별 기대 극성과 대조하는 방식으로 개선(응답 신뢰도·변별력↑).
- Step1 event_scoring: `score(fav_override=)`·`favorability_map_from_model(model)` 추가, 본문을
  `_score_periods`로 추출하고 `score_years(result, years, fav_override=)` 신설 — yearly_luck
  윈도 밖 과거 세운은 `daewoon_table[*].sewoon`에서 가져와 동일 파이프라인으로 스코어링.
- Step2 스키마: `CalibrationEventItem`(event_key·category·label·expected_by_model), Question.events,
  FeedbackAnswer.event_ratings, EVENT_CATEGORY(직업·이동·애정·금전·건강·학업)·MAJOR_CATEGORIES·
  EVENT_RATING_SCORE 상수.
- Step3 질문 생성: manse_service가 result 구성 후 EventScorer로 연도별 이벤트 검출(차트 용신=표시
  이벤트 상위4, 모델별 fav_override 재계산=이벤트별 기대 극성) provider를 generate_calibration에
  주입. q1~q3는 event_list, 이벤트 0건이면 텍스트형 폴백. saju_engines 의존은 manse_service에 격리.
- Step4 채점: event_ratings(긍+1/부-1/na제외)를 이벤트 expected_by_model과 대조, 카테고리 MAJOR
  가중 1.5. 레거시 overall_rating 경로 유지(하위호환).
- Step5 프론트: CalibrationPanel이 events 있으면 이벤트 행별 [긍정][부정][해당없음] 토글 렌더,
  event_ratings 제출. 타입(CalibrationEventItem·events·event_ratings)·AnswerMap·api 확장.
- 검증: backend 524 pass·ruff/mypy clean(신규 favorability override 3 + event 채점 2 + calibration
  갱신) / frontend tsc 0·vitest 22·빌드. 라이브(터널): 1980 픽스처 → q1~q3 event_list(연애 시작/
  사업 개업/이사 등, 모델별 기대 극성 상이), 이벤트 긍/부정 13건 제출 → calibrated(용신 土, 일치율 0.92).

## v2.2 AI채팅상담 대화 영속화 — 스레드별 저장·열람·이어가기·삭제 ✅

- 배경: ConversationState(003)는 오케스트레이터 상태만 저장 → 사용자 열람용 대화 전문 부재.
- 백엔드: `migrations/007_chat_history.sql`(chat_threads + chat_messages, ON DELETE CASCADE),
  `chat_history_store.py`(record_turn 자동저장·list_threads·get_messages·owner_of·delete_thread),
  `routers/chat.py` 확장 — POST에서 로그인+실답변 시 턴 자동저장(subject_label·title=첫 질문),
  GET /threads·GET /threads/{id}·DELETE /threads/{id}(소유자 한정, 삭제 시 ConversationState도 정리).
  비로그인 호출은 저장 안 함(optional_owner). deps에 get_chat_history_store.
- 프론트: `app/chat/page.tsx` — threadId 가변화, '대화 목록'(열람·이어가기·삭제)·'새 대화' 버튼,
  resumeThread(메시지 복원)·removeThread·newConversation. postChat에 subject_label 전달.
  `lib/api.ts`(listChatThreads/getChatThread/deleteChatThread + postChat subject_label),
  `lib/types.ts`(ChatThreadSummary·ChatMessageDTO).
- 검증: backend 526 pass·ruff/mypy clean(신규 test_chat_history_api 2: 401 게이트 / 기록→목록→열람
  →owner 격리→삭제) / frontend tsc 0·vitest 22·빌드. 라이브(터널): /threads 인증 200([])·미인증 401.

## v2.2 이벤트 엔진 재설계 Phase 1 — 새 사전 4종 + v2 타입 시스템 ✅

- 배경: 십성=종류 / 12운성=상태 / 합충형파해=발동 / 궁성=생활영역 / 용신=품질로 책임 분리하는
  엔진 재설계(사용자 제공 사양 4종). taxonomy 전면 교체(21키) + 엔진 전면 교체. Phase 1~6 신규
  병행(기존 엔진 무변경), Phase 7 스위치.
- 신규 사전(`dictionaries/event_engine/`, reviewed:false, generic 검증만 — events/ 자동 스키마 비충돌):
  `transit_ten_god_branching.json`(단일/그룹/특정/층위/반복/게이트), `_addendum.json`(지장간 강도·
  디스앰비규·안전 게이트·의지·시차·실패모드·프로필 게이트), `twelve_stage_modifier.json`(12운성 상태
  보정), `relation_palace_modifier.json`(합충형파해 type·9서브타입 + 궁성 map + 발동·materialization).
  정규화: ZHISHEN→SHISHEN, 21키 외 downgrade 대상은 기존 키로 매핑.
- 신규 타입 `shared_types/event_engine.py`: EventKeyV2(21) + TenGod/TenGodGroup/LuckLayer/TemporalMode/
  EventQuality/ConfidenceLevel/PolarityRole/TwelveStage/RelationKind/Pillar4 enum + 한글 십성·운성→enum
  매핑 + EventCandidateV2. 기존 EventKey/EventCandidate는 병행 유지.
- 검증: JSON 유효 · validate_dictionaries clean(45파일) · build_event_graph 컴파일 정상(event_engine/
  비간섭) · ruff/mypy clean · 전체 pytest 526 pass(기존 엔진 무변경 → 회귀 0).
- 다음: Phase 2 TenGodBrancher(십성 조합→타입 후보) — 사전 로더 pydantic + 단일/그룹/특정/3중 조합.

## v2.2 이벤트 엔진 재설계 Phase 1+ — 보완 모듈 6종 사전 추가 ✅

- 사용자 추가 사양(후보 축소·우선순위·사건화 판정 10모듈)을 우리 서비스에 맞춰 적응·추가:
  `void_repetition_modifier`(공망 해공·지연 + 복음/반음/병존/간여지동), `evidence_grading`(증거 7종
  ×5등급 + no_event_suppression), `conflict_resolver_duration`(충돌 우선순위 + 즉효/진행/구조/결과/
  반복 분류), `yonggi_quality_matrix`(이벤트별 용신/기신 품질), `user_profile_event_gate`(ExtendedProfile
  직업·고용형태·혼인 파생 매핑, 미입력=게이트 미적용), `intent_event_filter`(Domain enum + 일운/세운/
  리포트 컨텍스트). 10번 골든셋은 Phase 8 테스트 구조(regression_case_2025_08 연계)로 보류.
- 서비스 적응: 직업 O01~O18+employment_form→occupation_status, marital_status→relationship_status,
  intent_map→Domain(career/wealth/relationship/relocation/education/health/general)+컨텍스트.
- 검증: JSON 유효 · validate_dictionaries clean(51파일). 로드맵에 우선순위·11단계 흐름 통합.

## v2.2 이벤트 엔진 재설계 Phase 2 — TenGodEventBrancher(십성 조합→사건 타입) ✅

- 신규 `saju_engines/ten_god_brancher.py`: event_engine/ 사전 로더(pydantic, extra=ignore) +
  `TenGodEventBrancher`. 운 십성 신호(TransitSignal: ten_god·layer·source) → 단일(single_transit)·
  그룹2조합(group_combination)·특정2조합(specific_combination)·3중그룹(three_god) 룰 적용 →
  EventCandidateV2(event_key·score·source_layers·source_ten_gods·reason_codes). 룰별 점수 최댓값 채택,
  조건부(condition) branch는 Phase 2 미방출(Phase 6 평가). collect_from_pillar로 LuckPillar 천간·지지
  본기 십성 수집(지장간 중기·여기는 후속 강도 보정).
- 검증: 신규 test_ten_god_brancher 6 pass(단일·관인상생 특정조합 85·식상재성 그룹·3중조합·조건부
  미방출·차트 통합) · ruff/mypy clean · 전체 pytest 532 pass(기존 엔진 무변경 → 회귀 0).
- 다음: Phase 3 — 12운성 상태 보정(brancher 후보의 event_phase·강도·시차 보정).

## v2.2 이벤트 엔진 재설계 Phase 3 — TwelveStageModifier(12운성 상태 보정) ✅

- 신규 `saju_engines/twelve_stage_modifier.py`: twelve_stage_modifier.json 로드 →
  brancher 후보에 운 지지 12운성 적용. stage_modifier_rules(단계별 score_modifier·good_for·
  caution_for·event_phase) + event_specific_modifiers(boost/reduce stages) + layer_stage_combination
  (대운·세운 단계그룹 조합 보너스). 사건 성숙도 우선순위(세운>월운>대운>일운)로 대표 단계 채택,
  총 보정 ±18 한도(과보정 방지). **타입 생성 없음**(보정 전용). EventCandidateV2에 twelve_stage·
  event_phase 필드 가산.
- 동작: 건록→job_gain 가점·career_change 감점("인성+건록→이직 감점" 취지), 절→job_gain 감점,
  대운 양+세운 장생→business_start 보너스(DAEWOON_SEED_SEWOON_START).
- 검증: 신규 6 pass(타입 불변·건록 boost+phase·절 감점·건록 career 감점·층위조합 보너스·보정 한도)
  · ruff/mypy clean · 전체 pytest 538 pass(회귀 0).
- 다음: Phase 4 — 층위 결합 배율·반복(repetition)·십성 흐름(생성/극).

## v2.2 이벤트 엔진 재설계 Phase 4 — LayerFlowModifier(층위·반복·흐름) ✅

- 신규 `saju_engines/layer_flow_modifier.py`: layer_combination_rules(대운+세운 결합 ×배율 등)·
  repetition_rules(동일 십성 ≥2층 반복 +8, 동일 그룹 +6, MIXED 정관+편관/정재+편재/식신+상관/정인+편인
  쌍 가점)·ten_god_flow_rules(대운→세운→월운 상생 흐름 +12, 역흐름 -10) 적용. 타입 불변(점수만).
  MIXED 텍스트 조건은 룰 id→십성 쌍으로 기계화.
- 검증: 신규 5 pass(층위배율+반복, MIXED 가점, 생성흐름 +, 역흐름 -, 타입 불변) · ruff/mypy clean ·
  전체 pytest 543 pass(회귀 0).
- 다음: Phase 5 — Addendum 게이트(지장간 강도·디스앰비규·안전 downgrade·의지·시차·실패모드·프로필) +
  공망/반복성(void_repetition).

## v2.2 이벤트 엔진 재설계 Phase 5 — AddendumGateModifier(과잉 억제 게이트) ✅

- 신규 `saju_engines/addendum_gate_modifier.py`: GateContext(present 십성·층위·공망·직업/혼인상태)
  기반으로 event_gate_safety_rules(business_start 재성 없으면 약화, windfall 월/일 트리거 없으면
  wealth_change 강등, childbirth 관계상태 없으면 creative_output, marriage_signal single 약화, job_gain
  보조 없으면 약화) + user_profile_event_gate(employee→job_gain→promotion, married→new_relationship→
  relationship_change, business_owner+식상→wealth_change→business_expansion) + void(미해공 -10·delay).
  라벨 강등 시 동일 키 최댓값 병합. 미입력 컨텍스트는 게이트 미적용(규칙11).
- 검증: 신규 7 pass · ruff/mypy clean · 전체 pytest 550 pass(회귀 0).
- 다음: Phase 6 — 발동(관계·궁성) + 용신 품질 + 랭커(증거 등급·충돌 해결·confidence_level).

## v2.2 이벤트 엔진 재설계 Phase 6 — 발동(관계·궁성) + 용신 품질 + 랭커 ✅

- 신규 `saju_engines/relation_palace_engine.py`: RelationActivation(관계종류·자극궁·층위·천간/지지)로
  합충형파해 발동 보너스 × 궁성 활성가중(월/일주↑) × 층위가중 × 천간/지지 배율을 적용하고, 자극된 궁의
  event_domains·relation_to_palace 규칙에 맞는 후보에 palace(생활영역)를 부여한다. 동시발생 조합
  (합+충·형+충 등) 발동 보너스. 타입 불변(점수·궁성만).
- 신규 `saju_engines/yongi_quality_engine.py`: polarity_rules 배율(용신 ×1.15·희신 ×1.08·기신 ×1.15
  +quality_flip)과 yonggi_quality_matrix를 결합해 길흉 quality 확정(기신→재물형 loss·갈등형 conflict·
  그 외 pressure / 용신→성취형 achievement·그 외 opportunity). DELAY 등 시차 신호는 보존. NEUTRAL 무보정.
- 신규 `saju_engines/event_ranker.py`: evidence_grading 5등급으로 confidence_level 산출(십성만=theme_only
  → 십성+12운성+관계+궁성+층위+용기신+프로필=high_probability). no_event_suppression(월/일운 단독 신호
  강등) + conflict_resolver priority_rules(RankContext 플래그로 prefer↑/over↓) + 근접 3+ 묶음(DIFFUSE).
- 검증: 신규 17 pass(관계·궁성 5 / 용신 품질 6 / 랭커 6) · ruff/mypy clean · 엔진 단위 전체 회귀 0.
  (DB 미기동 세션이라 chat/report HTTP 통합 9건은 503 "저장소 미설정"으로 실패 — 환경 의존, 코드 무관.)
- 다음: Phase 7 — EventScorer를 새 파이프라인으로 교체 + 다운스트림 21키 마이그레이션 + intent_event_filter 배선.

## v2.2 이벤트 엔진 재설계 Phase 7a — EventEngineV2 통합 코어(거버닝 스택) ✅

- 신규 `saju_engines/event_engine_v2.py`: 재설계 6계층(brancher→12운성→층위·흐름→게이트→관계·궁성→
  용신→랭커)을 **거버닝 스택**으로 묶음. 세운=관할 대운+세운, 월운=+월운, 일운=+일운을 한 신호셋으로
  결합해 십성 조합 후보 생성 후 보정. 만세 신호 추출: relation_hits→RelationActivation(타입→RelationKind·
  natal position→Pillar4), twelve_unseong→TwelveStage, favorability_map→PolarityRole, 십성군→RankContext
  플래그. score/score_years 시그니처 유지(+선택 occupation/relationship). 호출부 미변경(추가 전용).
- 발견: 거버닝 스택은 다층 십성 결합으로 점수가 100에 포화→raw score 변별 소실. 사건화 강도
  (confidence_level)를 1차 정렬축으로 채택(_rank_key), 점수는 2차. 골든차트 2025 세운에서 직업
  (career_change·job_gain·promotion, 월주 발동)이 strong, theme/weak가 하위 — 회귀 기대(직업 변화 상위권)와
  방향 일치. 점수 포화 절대값 보정은 가중 튜닝(전문가 감수) 과제로 분리.
- 검증: 신규 6 pass(후보생성·confidence 1차정렬·결정론·강후보 궁성동반·score_years 과거연도·프로필 옵션)
  · ruff/mypy clean. 추가 전용이라 기존 회귀 무영향.
- 다음: 7c 다운스트림 하드 스위치(사용자 확정) — 호출부·다운스트림 21키 전환은 파일별 제시 후 적용.

## v2.2 이벤트 엔진 재설계 Phase 7c-1 — 21키 타깃 계층(추가 전용) ✅

- 신규 `shared_types/event_taxonomy_v2.py`: EventKeyV2(21) 한글라벨·시간성격(progress/instant/hybrid)·
  검증카테고리(career/move/affection/money/health/study)·리포트도메인·구키 25→21 매핑(LEGACY_EVENT_KEY_MAP,
  사용자 확정)·금기룰(PROHIBITIONS)·질의키워드(EVENT_WORDS)·택일대상(DATE_PURPOSES)·신 차원 한글라벨
  (quality/confidence/temporal/궁성). 실로그 최다 유형 반영: 진급·평가→promotion, 오디션·대회·선거→
  public_exposure, 국가고시·자격증·시험→education_admission. 금기룰 신규: prohibit_competition
  (경쟁 승부 단정 금지)·prohibit_exam(합격·당락 단정 금지).
- 신규 `saju_engines/llm_event_serializer.py`: EventCandidateV2 → LLM 입력 신 필드 풍부화
  (event_ko·confidence_ko·quality_ko·temporal_ko·palace_ko·근거코드 한글분류·금기룰 부착). 구 계약
  (polarity·signals·evidence_path) 대체.
- 검증: 신규 12 pass(엔진 6 + taxonomy/직렬화 6) · ruff/mypy clean · 전체 570 pass(회귀 0,
  실패 9는 DB 미기동 503 환경 의존). 추가 전용 — 호출부 미변경.
- 다음: 7c-2 플립 — 서비스(report/chat/manse/past_validation)를 EventEngineV2로, planner·calibration·
  query_parser·prediction·graph·context_reducer·llm_input·intent를 21키로 전환 + intent_event_filter
  배선 + 구 EventScorer/EventKey 제거. (타입 리플 큼 — mypy 안전망으로 일괄 전환 후 회귀.)

## v2.2 이벤트 엔진 재설계 Phase 7c-2 — 전면 하드 스위치(구 엔진 제거) ✅

- **EventKey 일원화**: `events.EventKey`를 21키 `EventKeyV2` 별칭으로 교체. 구 25키 폐기, 타입 주석
  15+개 파일 무변경. 구→신 매핑·한글·카테고리·금기룰은 `event_taxonomy_v2`.
- **구 엔진 제거**: `EventScorer`(사전 기반 스코어러) 삭제. `event_scoring.py`는 헬퍼만 유지
  (favorability_map/_from_model·filter_year_candidates·daewoon_transition_weight). `EventEngineV2`가
  유일 스코어러. `__init__` exports 교체.
- **레거시 어댑터**: `EventEngineV2.score_legacy/score_legacy_years`(→ `to_legacy_candidate`)로 신
  후보를 다운스트림 DTO(EventCandidate)로 변환. quality→polarity, confidence_level→confidence,
  reason_codes→signals. 신 차원(품질·확신도·궁성·단계)은 첫 동반 신호로 표면화(LLM 입력 풍부화).
- **서비스 switch**: report/chat/manse/past_validation/past_validation router → EventEngineV2.
  manse 검증 약-proxy 제외는 confidence==LOW(theme_only) 기준으로 일반화. report `_EVENT_DOMAIN`·
  chat `_DATE_PURPOSES`·context_reducer event_ko·calibration EVENT_CATEGORY·planner graphScope·
  query_parser 키워드·prediction 디스클레이머 전부 21키.
- **그래프 21키**: dictionaries 레거시 event 필드 str 완화 + graph_builder가 21키 event 노드
  (taxonomy_v2)·금기룰(PROHIBITIONS, prohibit_competition·prohibit_exam 신규)·구키 엣지 LEGACY 리맵.
  compiled 스냅샷 재생성(21 event 노드, 6 prohibition 노드). 택일 purpose_profiles·avoid_days 21키.
- **intent_event_filter 배선**: 신규 `intent_event_filter.py`(도메인 deprioritize + 컨텍스트 오버레이,
  빈 결과 방지) chat 후보 선별에 연결.
- 검증: ruff clean · mypy 0(사전 존재 manse_core 2건 제외) · pytest **573 pass** / 9 fail(전부 DB
  미기동 503 환경 의존 — 회귀 0). 라이브 스모크: report 경로가 신 엔진 레거시 후보(polarity·confidence·
  풍부화 신호) 정상 산출. 실로그 최다 유형(진급·평가→promotion / 오디션·대회→public_exposure /
  국가고시·자격증→education_admission) + 경쟁·합격 단정 금지 반영.
- 남은 과제(별도): reviewed:false 가중 전문가 감수·튜닝(점수 100 포화 보정), 레거시 events/*.json 신호
  매핑의 21키 정식 이관(현재 graph만 리맵 사용), DB 기동 환경에서 chat/report 통합 회귀 재확인.

## v2.2 Life Event Inference 2단계 — 저장소 골격 + 현실 신호 캘리브레이션(수집만) ✅

- 설계: `doc/v2_2/LIFE_EVENT_INFERENCE.md` 확정(설계 원칙 최상단 — 점수 아닌 현실 사건 근사 /
  life_fit 정렬축 / reality_gate / 3소스·3계층 personal_calibration / 코호트 활성 게이트 / 미래 outcome 루프).
- **migrations/008_life_events.sql**: `subject_life_events` 원자행 테이블 — 코호트 지문(보정 후 4기둥
  간지+성별), 일주+성별=coarse 인덱스 / 전체=fine 인덱스, outcome·source·weight. 수집만(랭킹 미반영).
- **shared_types/life_event.py**: LifeEventOutcome(confirmed/not_happened/planned/pending/reality_fit_only)·
  LifeEventSource·SignalFingerprint·LifeEventRow + 현실 신호 캘리브레이션 질문/제출 타입.
- **saju_engines/reality_calibration.py**: `build_reality_calibration`(성년~현재에서 사건화 강도+대운
  교운 인접+분산으로 주요 ~10개 연도 선정, 연도별 후보 이벤트+한글 라벨+신호 지문) · `fingerprint_of`
  (십성그룹·궁성·관계·12운성) · `rows_from_submission`(선택=confirmed/미선택=not_happened, 미응답 연도 무적재).
- **saju_engines/life_event_store.py**: LifeEventStore(append_rows 멱등 upsert, cohort_count coarse/fine —
  활성 게이트 판정용, subject_signature) — SubjectStore와 동일 DSN·단기 커넥션.
- **API**: `GET/POST /api/v2/reality-calibration/{subject_id}/questions|submit` (owner 검증, deps에
  get_life_event_store 추가, main 등록). 질문은 결정론적 재생성으로 제출 시 지문 확보.
- 검증: 신규 6 pass(질문 생성·라벨·지문·salience·제출→행·해당없음) · ruff/mypy clean · 전체 579 pass
  (9 fail=DB 미기동 503 환경, 신규 회귀 0). 랭킹/스코어링 경로 미변경(수집 전용).
- 다음(LEI 3~5): reality_gate 맥락 확장 + life_fit/personal_match 필드·배선(개인 시그니처 우선) →
  score→display_score 격하 → 코호트 활성 게이트. 그 뒤 가중 튜닝 → 21키 이관 → DB 통합회귀.

## v2.2 Life Event Inference 3단계 — life_fit/personal_match + 개인 시그니처 배선 ✅

- EventCandidateV2에 내부 정렬 필드 추가: `life_fit`(현실 적합도)·`personal_match`(과거 유사도). 기본 0 →
  미사용 시 기존 정렬과 동치(회귀 무영향).
- **personal_calibration.py**: candidate_fingerprint(십성그룹·궁성·관계·12운성)·fingerprint_similarity
  (Jaccard+궁성·관계·12운성 일치)·apply_personal_match(past_event_match + 반복테마 가중 −
  failed_prediction 페널티)·seed_missing_events(반복 확정/예정인데 후보에 없는 사건 시드).
- **reality_context.py**: RealityContext(직업·혼인·이사계획·계약·이직의향·시험 — 전부 optional) +
  apply_life_fit("있으면 강하게, 없으면 0" — 규칙11). 맥락 맞는 후보 life_fit↑.
- **life_fit_ranker.py**: LifeFitRanker.rank — 시드 → personal_match → life_fit 적용 후 LEI 정렬축
  (life_fit > confidence > personal_match > score > 시점·키)으로 재정렬. EventEngineV2는 불변(별도 후처리).
- **검증(핵심 페이오프)**: 골든차트 2026 세운에서 relocation은 엔진만으론 **미검출**이나, 사용자 실제
  이사 이력(2024·2025 확정) + 이사 예정 맥락을 주면 **relocation #1**(SEED, life_fit=40·personal_match=50).
  점수 튜닝이 아니라 개인 현실/과거로 누락 사건을 복원 — LEI 재정의의 실증.
- 검증: 신규 6 pass(빈입력 동치·매칭 가점·실패 감점·누락 시드·life_fit 최상위축·빈맥락 무보정) ·
  ruff/mypy clean · 전체 585 pass(9 fail=DB 503 환경, 신규 회귀 0). 코호트는 미배선(활성 게이트 5단계).
- 다음(LEI 4): score→display_score 격하·정렬축 공식 재정의 → (5) 코호트 활성 게이트.

## v2.2 Life Event Inference 4단계 — 정렬축 일원화 + score 표시용 격하 ✅

- 공식 정렬축 `lei_rank_key`를 shared_types/event_engine.py에 단일 정의(현실적합 life_fit >
  사건화증거 confidence > 과거유사 personal_match > 잠재 score > 시점·키). EventEngineV2·LifeFitRanker가
  공용 — 엔진 단독에선 life_fit·personal_match=0이라 (confidence, score) 순서로 자연 환원(회귀 무영향).
- score는 '표시용 내부값(display_score)'으로 격하: EventCandidateV2 필드 주석 명시 + llm_event_serializer가
  절대 점수 대신 강/중/약 밴드(score_band) 노출, 1차 신호는 confidence·quality·personal_pattern.
- 검증: ruff/mypy clean · 전체 585 pass(9 fail=DB 503 환경, 신규 회귀 0).

## v2.2 Life Event Inference — 현실 신호 캘리브레이션 월단위 정밀화(발생 건 한정) ✅

- 발생 사건에만 월을 받는 하이브리드: 연도 선택(넓게·저부담) → 선택한 사건만 선택적 월. 시기가 사건
  발현의 핵심이라(이사 시점 등), 월 지정 시 그 달 월운을 스코어링해 **월운 지문**(월지 십성·관계 = 실제
  trigger)으로 period='YYYY-MM' 정밀 적재. 월 미입력은 연도 지문 폴백(규칙11).
- 타입: OccurredEvent(event_key, month?) + RealityCalibrationYearAnswer.occurred. reality_calibration에
  month_event_fingerprints + rows_from_submission(month_fp) 확장. 라우터 submit이 발생 월 건만 월운
  차트를 계산해 지문 생성(발생 건 한정 — 부담 최소). 저장소 period TEXT가 월 지원(스키마 무변경).
- 검증: 신규 2 pass(월 period·월운 지문 사용 / 지문 없으면 연도 폴백) · ruff/mypy clean · 전체 587 pass
  (9 fail=DB 503 환경, 신규 회귀 0). LIFE_EVENT_INFERENCE.md §5 갱신.

## v2.2 Life Event Inference 5단계 — 코호트 활성 게이트 ✅

- **cohort_calibration.py**: 동일사주 코호트(일주+성별=coarse / 전체 4기둥+성별=fine) 확인 사건 빈도를
  personal_match에 합산. **활성 게이트**: 표본(확정 사건 보유 distinct subject 수)이 임계 미만이면
  미반영(저장만) — 소표본 왜곡 차단. 백오프 select_tier(fine 충분→fine / coarse 충분→coarse / 둘 다
  미달→none). 임계 COARSE=20·FINE=8(reviewed:false 초안). 익명 집계만(개인 비노출), 확률적 경향(단정 금지).
- **life_event_store.cohort_event_counts**: (총 distinct subject, 이벤트별 distinct subject) — coarse/fine
  GROUP BY. **life_fit_ranker.rank(cohort=...)**: 개인 personal_match → 코호트 합산(활성 시) → life_fit 순.
- 검증: 신규 5 pass(백오프·임계미만 미반영·fine 비율 합산·coarse 폴백·랭커 활성시만 반영) · ruff/mypy
  clean · 전체 592 pass(9 fail=DB 503 환경, 신규 회귀 0).
- LEI 엔진 계층(설계·수집·개인·정렬축·월정밀·코호트) 완료. 다음: 서비스 배선(chat/report에 LifeFitRanker +
  개인 시그니처·코호트 조회 — DB 게이트), 이후 가중 튜닝 → 21키 이관 → DB 통합회귀+골드셋.

## v2.2 Life Event Inference — 서비스 seam(엔진→레거시→다운스트림 LEI 정렬) ✅(부분)

- 레거시 EventCandidate에 life_fit·personal_match 전달 필드 추가 + to_legacy_candidate가 복사.
  EventEngineV2.score_legacy_personalized(signature·reality_context·cohort) = score → LifeFitRanker → 레거시.
- 다운스트림 LEI-aware 정렬(backward-compatible): report_service pool·context_reducer.reduce_candidates·
  out_top을 (-life_fit, -personal_match, -score, …)로. 개인 시그니처 미배선 시 0이라 기존 -score와 동치.
- 검증: 신규 4 pass(레거시 전달·LEI 순서·역호환·개인화 relocation 시드가 레거시까지) · ruff/mypy clean ·
  전체 596 pass(9 fail=DB 503 환경, 신규 회귀 0).
- **남은 경계(결정 필요)**: chat/report 요청이 subject_id를 안 들고 다님(chat=birth+subject_label, report=
  SubjectRef). 라이브 개인화는 subject_id로 시그니처·코호트를 DB 조회해 score_legacy_personalized에 주입해야
  하므로, 요청 경로에 subject_id를 넣는 API/프론트 계약 결정이 선행돼야 한다. 엔진 seam·필드·정렬·조회
  메서드(subject_signature·cohort_event_counts·cohort_stats_from_counts·pillars_signature)는 모두 준비됨.

## v2.2 Life Event Inference — chat 라이브 개인화 배선(subject_id) ✅(backend)

- 사용자 확정(2026-06-13): 요청에 subject_id 추가. ChatRequest.subject_id(선택) + chat 라우터가
  owner_id·subject_id를 chat_service.chat에 전달.
- chat_service: _personal_inputs(owner_id, subject_id, result) — LifeEventStore에서 개인 시그니처
  (subject_signature) + 활성 코호트(cohort_event_counts→cohort_stats_from_counts) 조회. **방어적**:
  owner/subject 없거나 DB 미설정·조회 실패면 (None, None) 폴백(개인화 실패가 풀이를 막지 않음 — 규칙11).
  메인 스코어링을 score_legacy_personalized(signature, cohort)로 교체 → LEI 정렬축이 출력에 반영.
- 검증: 신규 1 pass(무DB 방어 폴백) — 총 seam 5 pass · ruff/mypy clean · app import OK · 전체 596 pass
  (9 fail=DB 503 환경, 신규 회귀 0).
- 남은 활성화 조건: ① 프론트가 저장된 사주 질문 시 subject_id 전송 ② DB 기동 + 현실 신호 캘리브레이션
  수집 데이터 ③ (선택) report_service도 동일 패턴 배선. 엔진/저장/조회/정렬은 전부 준비됨.

## v2.2 Life Event Inference — report 개인화 배선 + 공용화(A) ✅
- 공용 services/personalization.py(fetch_personal_inputs) 신설 — chat·report 공유(방어적 폴백).
- report_service._ReportData·generate_report에 owner_id·subject_id → score_legacy_personalized.
  report 잡 흐름(ReportJobRequest.subject_id+owner 검증)이 이미 식별자 보유 → _run_report_job이 전달.
  chat_service는 공용 helper로 리팩터. 검증: ruff/mypy clean·전체 597 pass(9 DB환경, 회귀 0).

## v2.2 Life Event Inference — 프론트(subject_id 전송 + 현실 신호 캘리브레이션 UI)(B) ✅
- B1 chat 개인화 활성: lib/api.postChat에 subjectId 인자+subject_id 페이로드, app/chat이 selected.subjectId 전송.
- B2 수집 UI: lib/types 캘리브레이션 타입 + lib/subjects(getRealityCalibration·submitRealityCalibration) +
  components/onboarding/StepRealityCalibration.tsx(연도별 사건 선택 + 발생 사건만 선택적 월 — '월 모름' 허용) +
  app/reality-calibration/page.tsx(사주 선택·재진입) + settings 링크.
- 프론트 게이트: tsc clean · vitest 22 pass · next build 성공(/reality-calibration 3.94kB).

## v2.2 LEI — 가중 튜닝(포화 보정, reviewed:false 초안)(C1) ✅
- 층위 결합 배율↓(대운+세운 1.25→1.05 등)·base_events ×0.75·흐름 +8/-8·용신 1.075·관계 보너스 ×0.55·
  관계 delta 상한 22(_MAX_RELATION_DELTA). 골든차트 포화: 2024 6→0·2025 9→2·2026 6→0, raw 최대
  109~127→74~87. score 변별 복원·디커플링 정상. compiled 스냅샷 재생성.
- 회귀: 절대 점수 비고정(상대/구조)이라 무영향. 튜닝으로 깨진 단위 2건(절대 임계)을 상대 우위로 수정.
  검증: ruff/mypy clean·전체 597 pass(9 DB환경, 신규 회귀 0). SCORE_SATURATION_REVIEW.md §7 기록.

## v2.2 LEI — 레거시 사전 21키 정식 이관(C2) ✅
- events/*.json·taxonomy.json·relations.json·common/ten_god_events.json·templates/interpretation.json·
  event_forms.json·occupation_taxonomy.json·event_engine/relation_palace_modifier.json의 이벤트 키를
  LEGACY_EVENT_KEY_MAP으로 21키 변환(병합·dedup·contextModifiers 합산). housing_rules "document"는
  도메인 가중치(이벤트 키 아님)라 유지. graph_builder _norm_event 리맵은 이제 identity(데이터 네이티브 21키).
- validate_dictionaries 0 violations · compiled 스냅샷 재생성 · ruff/mypy clean · 전체 597 pass
  (9 DB환경, 신규 회귀 0). 이관으로 변한 단위 2건(occupation O14 travel→relocation 병합 등)을 상대 불변으로 수정.

## v2.2 LEI — DB 통합회귀 + 골든셋 재현(C3) ✅
- saju-v2-db(5433) 기동 확인. 마이그레이션 001~008 멱등 적용(subject_life_events 생성).
- **DB 연결 전체 스위트: 608 passed, 0 failed** — 그간 "환경 실패"였던 9건(chat/report/accounts/
  chat_history/lotto)이 DB 연결로 전부 통과 = 하드 스위치+LEI+개인화 end-to-end 검증.
- 골든 통합 tests/integration/test_lei_db_golden.py: 2025-08 이사 확정 + 2026-08 예정(planned) 적재 →
  subject_signature 라운드트립 → 2026 relocation 개인화 부상(personal_match>0) / 동일사주 8명 코호트 →
  fine 활성 게이트 + relocation 비율>0. DB 미기동 시 skip 가드(테스트 owner 격리·종료 정리).
- 게이트: ruff/mypy clean · WITH DB 608 pass / WITHOUT DB 597 pass+9 DB게이트 실패+2 skip(골든).

## v2.2 리포트 품질 — 리포트 전용 정밀 LLM 입력(채팅과 분리) + 내부 문구 제거 ✅(1차)
- 진단: 재물운 테스트 리포트의 "辛亥=정재", "재성 지지 충", "삼합 세력"은 사전·엔진 값이 아니라
  LLM 환각(엔진은 辛=식신·亥본기 壬=정재로 정확). 리포트가 채팅과 같은 압축 입력을 써서 정밀도 부족이 원인.
- 신규 saju_engines/report_event_input.py: 후보를 시점 클러스터로 묶고 per-글자 십성(천간 辛=식신/
  지지 亥=정재)·관계 분해(運亥↔원국巳 충 / 亥亥 자형·복음)를 명시. report_service.luck_block 교체 +
  프롬프트 "제공 라벨만 사용, '재성 지지 충' 류 임의 표현 금지". 사용자 확정: 명리는 LLM 입력 명시만(계산 불변).
- 내부 문구 제거: Gnb copyright placeholder, reports on_hold 라벨·메시지를 사용자향으로 정리.
- 검증: 신규 3 pass(per-글자 십성·관계 분해·클러스터 병합) · ruff/mypy clean · 611 pass(DB) · 프론트 tsc clean.
- 남은(리포트): ① 테마별 구조 재편(재물운 7부 스토리: 성향→재물구조→축재형태→횡재→5년종합→주목달)
  ② 실제 점수표(부록) ③ 인사·원국 반복 제거 프롬프트 ④ 행동전략 구체화. (과잉탐지 게이트는 다음 단계 보류.)

## v2.2 리포트 품질 — 재물운 테마 전용 목차(W-01~W-09) + 점수표 + 반복 억제 ✅(2차)
- 사용자 확정(2026-06-14): 주제마다 다른 스토리 구조. 재물운은 generic FOCUS(C-01~C-08) 대신
  테마 전용 9섹션: W-01 핵심요약 / W-02 재물성향 / W-03 재물구조 / W-04 축재형태 / W-05 횡재·상속 /
  W-06 향후5년 종합 / W-07 주목할 달 / W-08 행동전략 / W-09 부록 점수표.
- report_plan: _WEALTH_TOC + _THEME_TOCS(주제→목차 매핑). build_section_plans가 topic으로 분기
  (테마 있으면 전용 목차, 없으면 generic). RPT_FULL·generic FOCUS는 불변.
- report_service: _SECTION_GUIDES에 W-01~W-09 지침 추가. 데이터 배선 — _NATAL_SECTIONS(W-02·W-03=
  명식 구조, 운 블록 미부착) / _SCORE_TABLE_SECTIONS(W-09=실제 마크다운 점수표) / 그 외 운 섹션은
  precise_candidate_clusters 정밀 후보 블록. 모든 섹션 프롬프트에 "인사·원국 재설명 생략(앞 섹션 1회면
  충분)" 지침 추가(반복 제거). W-08 행동전략은 확장/소액검증/계약보류/현금확보/레버리지금지 단위로 구체화.
- report_event_input.score_table_lines: 시점·운간지·이벤트·점수·신뢰도·방향·십성/관계근거 마크다운 표
  (표 밖 새 수치 생성 금지 프롬프트와 함께). 부록 W-09에 그대로 인용.
- 검증: dry-run에서 wealth=W-01~W-09 생성·W-09 점수표 박힘·W-07 정밀 클러스터 확인. ruff/mypy clean ·
  611 pass(DB). test_report_topic_scoping을 테마 9섹션 기준으로 갱신.
- 남은: 과잉탐지 게이트(엔진), 다른 테마(직업·관계 등) 전용 목차는 추후 동일 패턴으로 확장.

## v2.2 리포트 품질 — 직업운(J)·관계운(R, 단독 모드) 테마 목차 ✅(3차)
- 사용자 지시(2026-06-14): 직업운·관계운도 테마 전용 목차. 재물운과 동일 8섹션 패턴.
  - 직업운 J-01~J-08: 핵심요약/직업성향/직업구조(격국·관성·재성·식상)/직업변동(이직·승진·창업)/
    향후5년 종합/주목할 달/행동전략/점수표. MODULE→M07.
  - 관계운 R-01~R-08(단독 모드): 핵심요약/애정성향/배우자·인연구조(일지 배우자궁·재성/관성·도화/홍염)/
    인연변화(만남·결혼신호·갈등)/향후5년 종합/주목할 달/행동전략/점수표. MODULE→M01.
- report_plan: _CAREER_TOC·_RELATIONSHIP_TOC를 _THEME_TOCS에 등록. report_service:
  _SECTION_GUIDES J/R 지침, _NATAL_SECTIONS(J-02·J-03·R-02·R-03), _SCORE_TABLE_SECTIONS(J-08·R-08).
  J-07/R-07 행동전략은 단정·낙인·운명론 금지(승진/합격/상대 강요 표현 차단).
- 테스트: test_report_topic_scoping 3테마(W/J/R) 검증. 파이프라인 기계 테스트(phase9)·통합 dry-run은
  generic 경로 검증이 목적이라 topic을 health(테마 목차 없음=generic FOCUS)로 전환.
- 검증: dry-run에서 J/R 8섹션·점수표·정밀 클러스터·natal 운블록 미부착 확인. ruff clean · 611 pass(DB).
- **관계운 상대(궁합) 모드는 미구현(설계 확인 대기)**: 상대 명식 계산 배선 + 원국A↔원국B 궁합 신호
  엔진 + "어떤 상대인가 솔직 해석"·"안 좋을 때 극복 마음가짐/행동" 섹션은 새 명리 규칙·새 아키텍처라
  사용자 확인 후 별도 구현(CLAUDE.md 6·10). 조사: M13(bond_compare) 빌더 미구현, 두번째 BirthInput
  계산·궁합 비교 부재 확인.

## v2.2 리포트 품질 — 관계운 궁합(상대 선택) 모드 + 두 명식 궁합 엔진 ✅(4차)
- 사용자 확정(2026-06-14): 궁합 전용 10섹션(RP-01~RP-10) + 신호 세트 = 일주 상호작용·십성 관계·
  용신 상호보완(관계 신살 제외). 상대 해석은 솔직하게, 마찰 시 극복 마음가짐·행동까지.
- 신규 궁합 엔진(reviewed:false 방향/톤): compatibility.py(타입 — CompatSignal/CompatibilityReport),
  compatibility_engine.analyze_compatibility(원국A↔원국B). 기존 명리 프리미티브 재사용
  (STEM_COMBINATIONS 천간합, SIX_COMBINATIONS/BRANCH_CLASHES/HARMS/BREAKS/PUNISHMENT 일지관계,
  ten_god 십성, STEM_ELEMENT·useful_gods 용신 보완). 방향=보완/마찰/중립, 전반 톤=보완·마찰 카운트.
- report_plan: _RELATIONSHIP_PAIR_TOC + is_pair_relationship(관계운 + SELF 아닌 subject→궁합 모드).
  build_section_plans가 상대 등록 시 단독 R-* 대신 궁합 RP-* 분기.
- report_service: _ReportData가 partner_birth로 상대 명식·궁합 계산. RP 지침 + 배선 —
  _PARTNER_NATAL_SECTIONS(RP-03 상대 명식), _COMPAT_SECTIONS(RP-04·RP-05·RP-08 궁합 신호 블록),
  RP-10 점수표. RP-08은 마찰 신호 기반 극복(상대 탓·운명론·강요 금지). plan_report/generate_report에
  partner_birth 인자 추가. 상대 미해석 시 빈 블록 안내로 단독 강등(오류 없음 — 규칙11 정신).
- report 라우터: _resolve_partner_birth — INLINE_TEMP(inline_birth) 즉시 / COMPANION(companion_id)
  SubjectStore 조회. dry-run·동기 생성은 inline, 비동기 잡은 companion까지 해석.
- 테스트: test_compatibility_engine(일지 합/충/형/복음·십성 양방향·용신 보완·카운트 일관),
  test_report_topic_scoping(단독8 vs 궁합10 분기·궁합 블록·partner 미전달 우아한 강등). 619 pass(DB) ·
  ruff/mypy clean(manse_service 기존 2건 제외).
- 남은: 궁합 방향/톤 reviewed:false 전문가 감수, 프론트 상대 선택 UI(상대 추가/선택 토글), 관계 신살
  교차는 사용자 확정대로 제외 유지.

## v2.2 프론트 — 관계운 상대 선택 UI + AI채팅 동반자 선택 ✅(5차)
- 리포트(테마): "궁합(compatibility, 미구현 M13 변형)"을 "애정·관계운(relationship, optional 동반자)"로
  교체. 상대 없이 진행 → 단독 R-*, 상대 선택 → 궁합 RP-*(백엔드 분기). themes.ts: requireCompanion
  boolean → companionMode("none"/"optional"/"required"). buildReportSpec은 companionMode!=none + 상대
  선택 시에만 companion ref 포함. themeLabel은 레거시 topic "compatibility"→"궁합" 매핑 유지.
- SubjectGateway: companionMode 도입(requireCompanion 호환 유지). optional 모드는 "상대 없이 내
  명식만으로 보기" 스킵 버튼 + 상대 카드 동시 노출. themes/[topic] 페이지·themes 목록 라벨 반영.
- AI채팅상담(/chat): 헤더에 "사주 변경" 버튼 + 인라인 사주 전환 패널(본인·동반자 listSubjects).
  선택 시 setSelected → effect가 해당 사주 프로필 재로드·새 스레드. 백엔드 무변경(채팅이 이미
  birth+subject_id 수신 — 동반자의 birth/subject_id를 그대로 전송, 개인화도 그 대상 기준).
- 검증: tsc clean · vitest 22 pass(themes 테스트 relationship 기준 갱신) · next build pass.
- 남은(후속): 채팅 내 두 명식 동시 궁합(pairwise)은 chat_service에 궁합 계산이 없어 별도 백엔드
  작업 필요 — 현재는 대상 전환(동반자 단독 상담)까지. 상대 선택 UI는 inline_temp(즉석 입력)는
  미노출(등록 동반자만) — 필요 시 추가.

## v2.2 관계운 — 즉석 상대 입력(inline_temp) + 채팅 pairwise 궁합 ✅(6차)
- 즉석 상대 입력(리포트): 등록 없이 상대 출생정보를 입력해 1회 궁합. 백엔드는
  _resolve_partner_birth가 inline_birth를 이미 해석(무변경). 프론트 — SubjectRef.inline_birth +
  InlineBirthDTO 타입, CompanionChoice 유니온(registered|inline), InlinePartnerForm(생년월일·시간모름·
  양음력·성별·출생지), SubjectGateway 상대 선택 단계에 '즉석 입력' details.
- 채팅 pairwise 궁합: 상대를 첨부하면 두 명식 궁합 신호를 LLM 입력에 더해 답한다.
  - 백엔드: services/partner_resolve.inline_to_birth 공용화(report 라우터도 사용). chat_service.chat에
    partner_birth/partner_label 인자 + _compat_prompt_block(analyze_compatibility 재사용, 직렬화된
    prompt_text에 궁합 블록 append, 단정·상대탓·운명론 금지 가드). chat 라우터 ChatRequest에
    partner_subject_id/partner_inline/partner_label + _resolve_chat_partner(즉석/등록 동반자 소유검증)
    + SubjectStore 의존성.
  - 프론트: postChat에 partner 인자(partner_subject_id/partner_inline/partner_label 페이로드).
    /chat 헤더 '궁합 상대' 버튼 + 첨부 칩(해제) + 상대 선택 패널(등록 동반자 + 즉석 입력). 첨부 시
    이후 질문에 함께 적용.
- 검증: 백엔드 ruff/mypy clean · 621 pass(+2: inline 첨부 궁합 블록 주입 / 미첨부 시 블록 없음).
  프론트 tsc clean · vitest 23 pass(+1 inline_temp ref) · next build pass.
- 남은: 궁합 방향/톤 reviewed:false 전문가 감수, 채팅 멀티턴에서 상대 첨부 상태 영속화(현재는 세션
  로컬 상태 — 새로고침 시 해제), 관계 신살 교차 제외 유지.

## v2.2 궁합 — 채팅 첨부 영속화 + 관계 신살 교차(보조) ✅(7차)
- 채팅 첨부 영속화(프론트): 궁합 상대 첨부를 스레드별 localStorage(ryubosal:chatPartner:<threadId>)에
  저장 → 새로고침·대화 이어가기에도 유지. threadId 변경 시 복원, 새 대화는 미첨부로 시작.
  백엔드 무변경(요청별 partner 처리는 이미 정확 — 갭은 프론트 상태 소실뿐). attachPartner로 통일.
- 관계 신살 교차(보조 신호): 사용자 확정(2026-06-14) — 도화·홍염(끌림)·원진·귀문(미묘한 거슬림)을
  보조로 가볍게만. compatibility_engine._sinsal_cross_signals — saju_manse_analysis.sinsal_catalog의
  권위 테이블(SAJEONG·HONGYEOM·WONJIN·GWIMUN) 재사용. CompatSignal.auxiliary=True·direction=NEUTRAL
  → 보완/마찰 카운트·전반 톤에 미반영. compatibility_lines가 '[참고 — 보조 신살(가볍게만)]' 섹션으로
  분리 출력. CompatSignalKind에 SINSAL_CHARM/SINSAL_FRICTION 추가.
- 검증: 백엔드 ruff/mypy clean · 623 pass(+2: 신살 보조 NEUTRAL·카운트 제외). 프론트 tsc·vitest 23·
  build pass.
- 남은: 궁합 방향/톤 reviewed:false 전문가 감수(신살 포함), 채팅 첨부의 서버측(크로스 디바이스) 영속화는
  미적용(현재 브라우저 localStorage — 기기 간 이어보기 시 칩 미복원).

## v2.2 궁합 — 채팅 첨부 서버측(크로스 디바이스) 영속화 ✅(8차)
- 첨부를 ConversationState(JSONB, 이미 영속)에 미러링 → 다른 기기에서 스레드 이어볼 때 복원.
  궁합 계산은 기존대로 요청의 partner로 수행하고, 서버 상태는 재개 복원용(읽기).
- 백엔드: ConversationState.partner(dict, 프론트 ChatPartner 형태). chat_service.chat에 partner_ref
  인자 — process_turn 직후 state.partner=partner_ref로 매 턴 미러링(첨부/해제가 곧 서버 상태). chat
  라우터 _partner_ref(req→ChatPartner dict) + GET /threads/{id}/partner(소유자 한정, 상태에서 복원).
- 프론트: getChatPartner(threadId). /chat 복원 effect — 로컬(localStorage) 우선, 없으면 저장된
  스레드에 한해 서버에서 복원(신규 대화는 스킵해 404 잡음 방지). 복원 시 localStorage 동기화.
- 검증: 백엔드 624 pass(+1: 미러링·GET 복원·타계정 404·해제 시 None). ruff/mypy clean. 프론트 tsc·
  vitest 23·build pass.
- 남은: 궁합 방향/톤 reviewed:false 전문가 감수(신살 포함).

## v2.2 채팅 품질 — 3 flash 원복 + thinking LOW + 요일 파싱 + 범위 프롬프트 ✅(9차)
- 실사용 결함 보고(2026-06-14): ① 2.5-flash가 쓰임 ② thinking ③ 정황설명 과다 ④ '다음주 월요일'
  시점 오류. 사용자 지시: 3 flash 고정, thinking LOW, 후속 3종.
- A 모델/thinking(llm_config.json): primary를 gemini-3-flash-preview로 원복(6/12 장애로 내려둔
  2.5-flash 임시 폴백 해제). thinkingConfig를 thinkingLevel:LOW로(2.5식 thinkingBudget 512 대체).
  폴백은 OpenAI gpt-5-mini 유지(사용자 선택). note 갱신.
- B 요일 파싱(time_parser.py C3.5): '다음주 월요일'·'이번주 금요일'·'월요일'을 주 전체가 아니라
  단일 일운(DAY)으로 해석. _WEEKDAYS(월0~일6), 주 단위 규칙 앞에 배치. '다음주'(요일 없음)는 기존
  주 전체 유지. test_time_parser_weekday 5케이스.
- D 범위 프롬프트(chat_service): 대화형 전용 _CHAT_SCOPE_DIRECTIVE를 prompt_text에 append —
  질문 범위에 집중, 원국 통독·정황 재설명·인사말 차단(리포트의 전체 서술은 불변). 직렬화 후 주입.
- 검증: 629 pass(+5 요일) · ruff/mypy clean. '다음주 월요일' → 2026-06-15 단일 일운 확인.
- C 명시적 캐시 — 실측 후 **implicit 캐시 의존으로 결정**(2026-06-14 사용자 승인, 추가 코드 없음).
  근거: 지시(시스템 프롬프트) ≈516토큰으로 Gemini 명시적 캐시 최소치(~1,024) 미만 → 단독 캐시 불가.
  차트 고정 prefix ≈2,592토큰은 사용자별이라 글로벌 캐시 불가지만 멀티턴·리포트 섹션 반복에서 implicit
  캐시로 이미 자동 할인(코드가 cachedContentTokenCount 집계). 구조도 캐시 친화적(시스템 분리 + prefix
  본문 맨 앞 + 동적 지시 끝 append). 명시적 캐시는 실익 적거나 불가 → 미구현.

## v2.2 리포트 UX — 실시간 진행 + 완료 알림(토스트·뱃지) ✅(10차)
- 결함(2026-06-14): 진행 카운트가 0/8에서 멈춤(완료 시 일괄 반영). 이탈 후 완료 확인·알림 부재.
- 진행 실시간화: ReportBuilder에 progress_fn 추가 — 섹션 1개 완료마다 호출. report_service.generate_report
  ·_run_report_job에 배선해 store.update_progress(이미 정의돼 있었으나 미호출)를 연결 → sections_done이
  실제로 증가(폴링 3s에 반영). (안내문 대체 대신 '진짜 동작'으로 해결.)
- 완료 알림: ReportNotificationsProvider(신규) — 로그인 시 잡 목록 20s 백그라운드 폴링, 새로 완료/보완/
  실패된 풀이를 토스트(우하단)로 알림 + GNB 뱃지(햄버거 점·'내 풀이 내역' 카운트). 본 상태는
  localStorage(notified/seen) 추적, 최초 실행분은 retro 알림 제외. 내역 진입 시 markReportsSeen로 해제.
- 재진입 확인: 기존 잡 영속(report_job_store) + 목록(/reports)→열람(/reports/[id])으로 이미 동작 —
  진행 페이지 문구만 '닫아도 계속·알림·내역에서 다시' 안내로 보강.
- 검증: 630 pass(+1 progress_fn 섹션별 호출) · ruff/mypy clean · 프론트 tsc·vitest 23·build pass.
  프로덕션(.next-prod) 재빌드·재기동 반영.

## 한해풀이(RPT_YEAR) 상품 추가 + 리포트 공백 정규화 (2026-06-14) ✅

- **신규 풀이 상품 `RPT_YEAR` 한해풀이**(사용자 확정). 총운(RPT_FULL 22섹션)에서 단일 년도에
  의미 있는 항목만 발췌·중복 제거한 **12섹션(Y-01~Y-12)**. 장기 항목(생애 대운 로드맵·과거
  복원·고점 연도 Top·성격 종합) 제외, 원국+용신은 Y-02 1섹션으로 압축. 세운 기준=달력연도
  1~12월(`spec.period`가 그 해로 스코프). dependsOn: Y-02(용신)→Y-03~Y-11.
  - 분량 합계 21,600~28,400자 → **A4 약 14~18장**(1p≈1,600자). 집중(15장)<한해<총운(50장).
  - docs/10 1장 상품표 + 4-2장 목차 규격 신설.
- **백엔드**: `report.py` product_code Literal에 RPT_YEAR. `report_plan.py` `_YEAR_TOC`·
  `_Y02_DEPENDENTS`·`YEAR_TOTAL_TARGET`·`YONGSIN_SECTIONS`(F-04/Y-02) + build_section_plans
  분기. 하드코딩 `"F-04"` 용신 전파를 `YONGSIN_SECTIONS` 멤버십으로 일반화
  (report_builder.py·report_service.py). report_service에 Y-01~Y-12 작성 가이드,
  `_NATAL_SECTIONS`에 Y-02 등록.
- **공백 낭비 수정(전 상품 공통)**: 섹션 프롬프트에 '지면 절약'(연속 빈 줄·잔 소제목·한 문장
  단락 금지, 조밀한 산문) 지시 추가. 생성 후 `_tighten()`으로 연속 빈 줄(3줄+)→1개 정규화.
  렌더(ReportPager) 타이틀 간격 `prose-headings:mt-3`→`mt-4`(문단 간격의 2배).
- **프런트**: `lib/themes.ts` THEMES index 1(총운 오른쪽)에 `year`(한해풀이) + `needsYear`.
  `buildReportSpec(…, year)`→period=그 해 1~12월. 테마 시작 페이지에 년도 셀렉터
  (기본 올해, 범위 올해~+5년). lib/types.ts product_code 유니온 확장.
- **검증**: 백엔드 631 pass · ruff/mypy clean · 프론트 tsc clean · production build pass.
  dry-run: 12섹션·deps·용신 전파(水) 정상, 분량 합계 A4 13.5~17.8장. `_tighten` 실측 잔존
  연속 빈 줄 0.
- **관찰(기존 파이프라인 공통, 본 작업 범위 외)**: 라이브 생성 시 Gemini가 목표보다 짧게
  생성(예: 목표 2,500~3,500자에 ~1,900자)하고 evidence path를 그대로 인용하지 않아 분량·근거
  정합성 검사(무허용오차)에 실패→on_hold. **총운 F-01/F-04도 동일하게 실패** 확인 — RPT_YEAR
  고유 결함 아님. 길이 하한 완화/허용오차·근거 인용 강제는 전 상품에 걸친 별도 튜닝 결정으로
  사용자 승인 후 진행 대상.

### 분량 캘리브레이션 'B' 적용 (2026-06-14, 같은 작업 후속)

- 위 '관찰'의 분량 미달 on_hold를 사용자 확정 'B'(실측 기반 하향)로 처리. 실측(gemini-3-flash):
  섹션 출력은 목표 크기와 무관하게 ~1,400~1,950자에 수렴(목표 4,500~5,500자 F-08·F-14 →
  1,953·1,718자). 길게 잡은 목표를 일괄 유지하는 것이 분량 검사(무허용오차) 실패의 직접 원인.
- `report_plan.calibrate_chars(lo,hi)` 신설 — 목차표의 편집 의도 분량을 실측 밴드로 압축(전 상품
  공통). 짧은 섹션(의도 mid<2,200)→700~2,200자, 표준·긴 섹션→900~2,900자. build_section_plans
  세 분기(FULL/YEAR/FOCUS) 모두 `_tc()` 경유 적용. `FULL_TOTAL_TARGET` 78,000→41,000,
  `YEAR_TOTAL_TARGET` 25,000→18,000(캘리브레이션 mid합 FULL 40,900·YEAR 18,300, 테스트 ±10% 통과).
- 상품 분량(실측 기준) 갱신: 총운 A4 ~20~25장, 한해풀이 ~11~14장, 집중 ~8~9장. docs/10 1장 표 +
  캘리브레이션 주석 + 4-2장 갱신.
- 검증: 631 pass · ruff/mypy clean. 한해풀이 실생성 재측정 — **12섹션 중 10개 통과**(이전 캐스케이드
  해소), 총 17,428자/A4 약 11장. 남은 실패 2건은 길이와 무관: Y-05·Y-12 근거 경로(evidence path)
  미인용(간헐), Y-12 종결어미 93%(경계). 동일 검사는 총운/집중에도 간헐 적용되는 전 상품 공통 사안
  으로, evidence 인용 강제/완화(옵션 C)·페르소나 임계는 별도 결정 대기.

### 리포트 인스트럭션 분리 + 근거 인용 강화(C-2) + 종결어미 임계(C-3) (2026-06-14)

- **확인**: 테마사주(리포트)와 AI채팅이 `llm_client._SYSTEM_PROMPT`를 공유 — 별도 관리 아니었음
  (chat_service.py:756 / report_service generate_fn). 공유 프롬프트의 '입력에 없는 간지·수치·날짜가
  필요하면 해당 정보는 제공되지 않았다로 처리한다'는 채팅 강제답변용 회피 문구로, 신뢰도상 리포트엔
  필요해서도 본문에 나와서도 안 됨(사용자 지적).
- **분리**: `_REPORT_SYSTEM_PROMPT` 신설(리포트 전용). `_SYSTEM_PROMPT` 최소 변경 — ① 규칙1의
  '해당 정보는 제공되지 않았다' 절 제거, ② 규칙7의 대화용 1,500자 상한 해제(분량은 섹션 과제 목표).
  나머지(오프닝 '서술가', 평문 기본, 점수 비노출)는 원본 유지. 주의: 오프닝을 '보고서 서술가'/
  '보고서'로 칭하니 모델이 문어체로 흘러 페르소나 해요체가 59~68%로 붕괴 → '서술가' 유지로 복구.
  report_service.generate_fn이 `_REPORT_SYSTEM_PROMPT` 사용. 채팅은 `_SYSTEM_PROMPT` 그대로.
- **C-2(근거 인용 강화)**: 재생성(attempt>0) 시 context.evidence_paths가 있으면 '경로 중 하나를
  화살표 포함 글자 그대로 1회 인용' 강제 문구를 프롬프트에 덧붙임(report_service.generate_fn).
- **C-3(종결어미 임계)**: persona.check_compliance 종결어미 비율 임계 0.95→0.93(표·짧은 섹션의
  비서술 문장 변동 흡수). check_compliance는 리포트 전용 게이트(채팅은 페르소나 블록만 주입).
- **검증**: 631 pass · ruff/mypy clean. 한해풀이 실생성 = **status completed(12/12 통과)**,
  18,897자/A4 약 11.8장, '정보 없음/제공되지 않았다' 류 문구 0건.

### thinking LOW 적용 확인 + 시제 앵커 주입(시제 혼동 해소) (2026-06-14)

- **thinking 조사**: '씽킹 low 미적용' 의심 확인. Gemini 호출 경로는 llm_client._call_gemini 단일,
  운영 요청에 generationConfig.thinkingConfig.thinkingLevel="LOW"가 실제 전송됨(요청 본문 캡처로
  확정). 무거운 리포트 프롬프트(4,704자)에서 thoughts 2,794→0으로 작동, 짧은 채팅은 LOW여도
  ~400 thoughts(gemini-3 LOW 바닥값). 설정 우회 경로 없음. → LOW는 정상 적용.
- **실제 문제는 시제**: 사용자 지적('생각 안 하고 답변, 특히 테마사주가 오늘 기준 시제를 못 잡음').
  원인 — `today`가 차트 계산·후보 필터엔 쓰이나 LLM 프롬프트엔 미주입. thinking이 low라 모델이
  오늘 날짜·시제를 스스로 추론 못 해 과거/미래를 혼동. 규칙 9상 thinking을 올릴 수 없으므로
  '오늘'과 시제를 사실로 주입(엔진이 사실 제공 → LLM 서술).
- **구현**: `_ReportData.today` 보관 + `tense_anchor_lines(spec)` 신설 — 모든 섹션 프롬프트 상단에
  '[기준 시점]: 오늘은 YYYY년 M월 D일, 이전=과거/이번 달=현재/이후=미래' 주입. RPT_YEAR는 대상
  연도의 월별 과거·현재·미래까지 명시(예: 2026 풀이를 6월에 보면 1~5월=과거, 6월=현재,
  7~12월=미래). build_section_context가 prefix 직후 주입.
- **검증**: 631 pass · ruff/mypy clean. 실생성 — Y-05 월별이 '1~5월 …했고(과거)', '현재인 6월
  갑오월은 …네요(현재)', '7~12월 …예상되네요(미래)'로 시제 정확 교정. status completed(12/12).

### 페르소나 말버릇 교체 (2026-06-14)

- 기본 페르소나(female_40s)의 거슬리는 말버릇 "다만 한 가지는요"를 "한 가지 짚어드릴 점이 있어요"로
  대체(dictionaries/persona_lexicon.json). 다른 연령대 톤과 중복 없는 40대 여성 해요체.
  validate_dictionaries 통과 · 631 pass. persona_lexicon은 PersonaEngine이 요청마다 직접 로드 →
  재시작 없이 반영.

### 발현 분기(Manifestation Branch) 프로세스 신설 — 챗·리포트 공통 (2026-06-14)

- **문제**: 한 사건의 에너지가 같은 계열(EVENT_CATEGORY)의 형제 사건으로도 발현될 수 있음에도
  (예: '이직·직업 변화'↔'이사·이동' = move 계열), 그 분기 가능성을 도출·주입하는 프로세스가 부재.
  build_monthly_overview의 `[:2]` 절단으로 형제 후보가 버려지고, 풀이는 한 사건으로 단정.
- **신설**: `saju_engines/manifestation_branch.py` — `branch_events(focal, period_candidates)`(같은
  EVENT_CATEGORY·같은 시점에 **실제 점수화된** 형제만 강도순, distinct·최댓값, <2면 빈값 — 추측 배제),
  `branch_line(...)`(발현 분기 1줄, 계열 라벨+형제 강도순). 사용자 확정: EVENT_CATEGORY 그대로 /
  같은 시점 점수화 형제만 / 챗·리포트 동시.
- **챗**: MonthOverviewRow에 `branch_ko` 추가. build_monthly_overview가 절단 전 그 달 후보 전체로
  분기 산출 → 유력 달 종합에 분기 줄 주입.
- **리포트**: `_ReportData.scored`(전체 점수화) 보관 + `_branch_lines()`가 후보 기간별 형제 분기 도출
  → luck_block에 '[발현 분기]' 블록 주입(운 데이터 부착 섹션 전체).
- **일반화 확인(실측)**: move(이직·이사)뿐 아니라 money(재물·횡재)·career(취업·승진·사업)·
  affection(관계·결혼)까지 같은 시점 동시 점수화된 달에서만 분기 노출(노이즈 0). 점수·판정 불변.
- **검증**: 636 pass(+5 단위 test_manifestation_branch) · ruff/mypy clean.

### 발현 분기 누락 수정 + 호칭 과다 반복 억제 (2026-06-14)

- **발현 분기 누락(2025-08 이직↔이사)**: 분기 초점을 그 달 1위(cs[0]) 단일 계열로만 잡아, 100점
  동점이 흔들리면(취업↔이직) move 계열 분기가 통째 누락. `branch_summary(focal_keys, …)` 신설 —
  표시되는 상위 사건(cs/후보) **전부의 계열**을 훑어 형제를 계열당 cap개(기본 3)로 제시. 챗
  build_monthly_overview·리포트 _branch_lines 모두 전환. 실측: 2025-08이 1위가 취업이어도
  '이동·변동(이직·직업 변화/이사·이동)' 분기를 안정적으로 포함.
- **호칭 과다 반복('회원님'/'OO님')**: 페르소나 템플릿이 '반드시 호칭 사용'을 강제 → 매 문장 호명.
  ① 템플릿을 '최대 2회·문장 첫머리 반복 금지'로 강화. ② `persona.cap_honorific(text, honorific,
  keep=2)` 후처리 신설 — 생략해도 자연스러운 형태(호격 쉼표/주어 은·는·이·가·께서/여격 에게·께/
  소유격 의)만 keep 초과분에서 제거, 목적격(을·를)은 보존(문법 안전). chat_service 답변·
  report_service 섹션 출력에 적용. 실측: 섹션당 8→2, 6→4회로 감소(가독성 유지).
- **검증**: 642 pass(+cap_honorific·branch_summary 단위테스트) · ruff/mypy clean. 터널 재기동 반영.

### 형제 분기 노출 위치 수정 + 호칭 후처리 제거 (2026-06-14)

- **형제 분기 누락 근본원인**: branch_ko는 전 월 계산되나 [유력 달 종합](top-3)에만 렌더링 →
  2025-08이 top-3 밖이면 이사 형제가 어디에도 안 보임(랭킹 run마다 변동). [월별 요약] 표는
  top-2(`[:2]`)만 보여 이사(3위) 잘림. dry_run 전체 프롬프트로 확인.
- **수정**: `branch_summary`를 압축형(계열·형제 목록만, 지시문 제거)으로 바꾸고 [월별 요약] 표
  모든 달 행에 ` · 분기 …` 렌더링(top-3 의존 제거). 안내문은 표 하단 1회. [유력 달 종합]은 압축
  분기에 지시를 wrap. 실측: 2025-08 행에 '이동·변동'(이직·직업 변화/이사·이동) 노출 확인.
- **호칭 후처리 제거(사용자 방침)**: cap_honorific 및 _HONORIFIC_* 전부 삭제(persona/chat/report).
  호칭은 페르소나 인트로 지시(단일 LLM 호출)로만 처리 — 후처리·재호출 0. 비용 원칙: 답변 1건당
  LLM 호출 최소화가 우선(채팅=1회, 후처리는 추가 호출 0이지만 방침상 제거).
- 검증: 638 pass · ruff/mypy clean. 터널 재기동 반영.

### 재생성(LLM 재호출) 최소화 — 비용 절감 (2026-06-14)

- **원칙**: 답변 1건당 LLM 호출 최소화. 리포트 섹션이 검사 실패 시 최대 2회 재호출하던 것을 대폭 축소.
- **결정적 보정(재호출 0)** `report_builder._repair_section`: ① 분량 초과 → 문장 경계로 잘라 상한 내,
  ② 근거 경로 미인용 → 경로 1줄을 본문 끝에 결정적으로 덧붙여 검사 통과.
- **재생성은 '사실 위반'에만**: `_hard_violations`(미제공 간지/입력에 없는 점수·연도/용신 불일치/
  금지 표현)만 재생성 유발. 분량·종결어미·근거·대상라벨 등 스타일·포맷 잔여 위반은 재호출 없이
  통과(passed=True, 위반은 기록). on_hold도 사실 위반에만.
- **MAX_REGENERATIONS 2→1**: 최악 재호출 절반(섹션당 3→2회 상한).
- **실측**: 한해풀이 12섹션 = LLM **12회 호출(재생성 0)**, status completed. (이전 최악 36회·잦은 on_hold)
- 검증: 640 pass(+regen-min 단위테스트 2) · ruff/mypy clean. 터널 재기동 반영.

### 호칭 별명 주입 + 이사 형제 surfacing (실제 사주 검증) (2026-06-14)

- **검증 방법론 오류 정정**: 앞선 분기 검증을 잘못된 성별(여성, 대운 壬午)로 해 무효였음. 실제
  사주는 남성(대운 壬辰). 남성 사주로 재검증.
- **호칭 별명 미연결 버그**: ChatRequest.subject_label(사주 별명)이 chat()에 전달조차 안 되고
  build_block(persona,"회원") 하드코딩 → 늘 '회원님'. 수정: chat()에 subject_label 인자 추가,
  라우터가 req.subject_label 전달, build_block(persona, subject_label). → '데글님' 등 별명 호칭.
- **이사 형제 미노출**: 실제 남성 사주 2025-08은 relocation(이사)이 후보로 점수화되지 않아
  'co-scored only' 규칙으론 이사 분기가 원천 불가. 이사는 이직(career_change)과 동일한 역마·이동
  에너지이므로, 상호교환 계열(_INTERCHANGEABLE_FAMILIES={'move'})은 한 멤버만 점수화돼도 형제를
  잠재 발현으로 포함하도록 branch_events 보강. 실측: 2025-08 월별요약에 '이동·변동'(이직·직업
  변화/이사·이동) 노출 확인.
- 검증: 641 pass(+이사 surfacing 단위테스트) · ruff/mypy clean. 터널 재기동 반영.

### 발현 분기 상호교환 계열 일반화 (이사만 특수처리 → 동형 전반) (2026-06-14)

- `_INTERCHANGEABLE_FAMILIES`를 {'move'} 하드코딩에서 **EVENT_CATEGORY 멤버가 정확히 2종인 계열
  자동 도출**로 일반화: move(이직↔이사)·money(재물 변화↔횡재)·study(진학·자격↔수료·졸업). 한 멤버만
  점수화돼도 나머지를 잠재 형제로 노출. career(6종)·affection(4종)은 구별 사건이라 co-scored 유지.
- 실측(남성 사주 월별표): 2025-08~12 이직/이사, 2026-01·04·05 재물/횡재, 2026-02 진학/수료 노출.
  career는 co-scored된 형제만(전체 나열 안 함).
- 검증: 642 pass(+일반화 단위테스트) · ruff/mypy clean. 터널 재기동.

### 맥락 기반 형제 사건 disambiguation — 무직→이직 불가→이사 (2026-06-14)

- **굉장한 오류**: '백수→재취업' 질문에서 2025-08은 이동(이직/이사) 신호가 취업보다 강한데,
  무직 상태라 '이직'은 성립 불가 → 이사가 답인데도 풀이가 2025-08을 '재취업 달'로 단정.
- **일반 안내(분기 노트)로는 실패**: thinking LOW LLM이 다단계 추론(무직→이직불가→이사)을 못 함.
  실측에서 LLM이 여전히 2025-08=재취업으로 답하고 이사 언급조차 안 함.
- **수정**: 질문에서 무직 맥락(_UNEMPLOYED_KEYS) 감지 시, 우선순위 높은 명시 제약
  (_UNEMPLOYED_DIRECTIVE)을 프롬프트 말미 주입 — "이직 성립 불가, 이직 우세 달의 이동 에너지는
  이사로 해석, 재취업은 취업·합격 우세 달에서만 지목". 분기 안내문도 '맥락으로 갈래를 좁혀라'로 강화
  (context_reducer 월별요약 노트 / report [발현 분기] 헤더).
- **실측(재검증)**: LLM이 재취업을 2025-11(취업·합격 우세)로 지목, 2025-08은 '이직/이사 같은 이동
  ·검토 과정'으로 풀이 — 핵심 오류 해소.
- 검증: 642 pass · ruff/mypy clean. 터널 재기동.

### 운영 관리자 콘솔 Phase A–E (2026-06-14)

- **Phase A 사용량·비용 영속 로깅(토대)**: migration 009 — llm_usage(호출별 토큰·cost_usd 스냅샷)·
  model_pricing(관리자 등록 단가)·admin_settings(환율)·accounts.is_admin. usage_store.py
  (UsageStore·PricingStore·compute_cost_usd). llm_client에 usage sink 주입(set_usage_sink) —
  호출마다 단가로 비용 계산 후 DB 적재(best-effort). chat/report가 owner·surface·ref 전달.
  in-memory COST_LEDGER(가드용) 유지. 단가 seed=model_prices.json, 환율 기본 1350.
- **Phase B 인증**: accounts.is_admin + AccountAuthStore.is_admin/set_admin + deps.require_admin
  (401/403) + env SAJU_ADMIN_LOGIN_IDS 시드(startup lifespan).
- **Phase C API** /api/v2/admin/*(require_admin): overview(오늘/7d/30d 토큰·비용 USD·KRW·월예상·
  단위비용·잡상태) / usage/summary(group_by day·surface·product·model·owner) / usage/timeseries /
  events(리포트 잡 목록·상태필터) / pricing GET·PUT / settings/usd_krw PUT. ReportJobStore에
  list_recent·status_counts 추가.
- **Phase D 프런트** app/admin/*(가드 레이아웃 + 개요·사용량·이벤트·단가/환율 탭). lib/admin.ts.
  단가·환율은 관리자가 페이지에서 직접 등록(현재 모델 제시 + 단가·환율 입력), 비용 USD·KRW 병기.
- **Phase E 비용 예측**: overview에 월 예상(30일 평균×30)·단위 비용(채팅 1질의/리포트 1섹션) 포함.
- **검증**: 645 pass(+compute_cost_usd 단위) · ruff/mypy clean · tsc·build pass. 라이브 HTTP:
  비관리자 403 / 관리자 overview·pricing 200 / 실제 채팅→사용량 적재($0.003918=5원) / 단가·환율
  편집 반영 확인. 관리자 부여는 SAJU_ADMIN_LOGIN_IDS(env) 또는 AccountAuthStore.set_admin.

### AI채팅 시점/기간 산출 개선 P0–P3 — '이사 시기 질문이 2026만 답' 수정 (2026-06-14)

- **진단(실측)**: intent(relocation)·domain은 정상인데 time_range가 깨져 전부 2026 중심창으로 떨어짐
  — ①축약연도 '27/28년'→None(4자리만 인식), ②'내후년' 미지원, ③'앞으로 N년'이 _rolling_months
  12개월 고정으로 N 무시.
- **P0 parse_time**: 축약연도 'NN년'→20NN(00~69→2000s, 70~99→1900s; 기간어미 후/뒤/간/안에 제외),
  '내후년'→+2년, '향후/앞으로 N년(간)'→현재월부터 N×12개월 롤링창(C8a 신설). 실측: 27년→2027 월별표
  2027-01~12, 앞으로5년→2026-06~2031-05.
- **P1 chat_service**: `_EVENT_MONTHLY`(EVENT_TYPE progress+hybrid) — 사건형(이사·이직 등)은 '월별'
  미명시 연 질문도 12개월 overview 계산. 응답형식: '월별' 명시→전체표 / 미명시→연간 요약+핵심 달
  (`_KEY_MONTHS_DIRECTIVE`). 실측: '28년 이사운'→2028 12개월+핵심달 지시, '28년 이사운 월별로'→전체표.
- **P2 query_parser**: 시점-only 후속('그럼 28년은?')은 기존 B2 상속이 P0 파싱으로 동작 + 단위 미명시
  후속은 직전 granularity 상속(월별 맥락 보존). 실측: relocation·2028·month 상속.
- **P3 context_reducer**: build_reference_frame note에 의도 사건·기간 유형(달력연도/미래 롤링)·재해석
  금지 명시.
- 검증: 651 pass(+test_time_parser_year 5케이스) · ruff/mypy clean. 터널 재기동.

### 관리자 사용량 '상품' 묶음 표시 + 선택 사주 정체성 정리 (2026-06-14)

- **관리자 사용량·비용**: '상품' 집계에서 섹션 코드(RPT_FOCUS:W-01 등)를 `:` 앞 상품 단위로
  묶어 합산 상위 행으로 표시, 행 클릭 시 섹션 상세를 펼침(▶/▼, (N섹션) 뱃지). 데이터는 이미
  섹션 단위로 내려오므로 프런트 그룹핑만으로 처리(백엔드·추가호출 0). app/admin/usage/page.tsx.
- **선택 사주 stale 버그**: 이전 로그인의 선택('데굴')이 빈 사주목록 위에 남던 문제. 원인=선택을
  로그인 정체성·실제 목록과 대조하지 않고 sessionStorage에 보존. 수정 ①선택 캐시에 owner(로그인 ID)
  스탬프 → authReady/loginId 변동 시 owner 불일치(타 사용자·로그아웃·구버전)면 폐기, ②reconcile(validIds)
  추가 → 사주목록 조회 직후 서버 진실과 대조해 없는 선택/동반자 정리. SelectedSubjectProvider.tsx,
  app/sajus/page.tsx.
- 검증: tsc clean · production build 성공(/admin/usage, /sajs).

### 관리자 시스템 에러 모니터링 — 중앙 적재 + 빈도 묶음 페이지 (2026-06-14)

- **목적**: 그동안 채팅 LLM 실패(삼켜짐)·미처리 5xx가 어디에도 안 남던 문제. 리포트 실패만
  report_jobs.error에 부분 기록. → 중앙 에러 로그 신설.
- **DB**: 마이그레이션 010 `system_errors`(source/severity/kind/message/detail/path/owner_id/ref_id/
  fingerprint/resolved_at). fingerprint=출처+종류+정규화(숫자 '#' 치환)메시지 해시로 유사 에러 묶음.
- **백엔드**: `error_store.ErrorStore`(record/list_recent/group_summary/resolve/counts/unresolved_total,
  usage_store 패턴 미러), `services/error_logging`(싱글톤 sink + best-effort record + _logged WeakSet로
  중복 적재 방지). 캡처 3지점: ①main.py 전역 `@app.exception_handler(Exception)` → 미처리 5xx를
  source=http로 적재 후 일반화 500(HTTPException·검증오류 제외) ②llm_client 에러 sink → 메인·폴백 모두
  실패 시 source=llm(provider/model/ref_id) ③report.py 잡 catch → source=report_job(이미 기록된 예외는
  is_logged로 제외). admin API: `GET /errors`, `GET /errors/groups`, `POST /errors/resolve` +
  overview에 unresolved_errors KPI.
- **프런트**: `/admin/errors` 페이지(묶음/전체 토글, 출처·심각도·미해결·기간 필터, 묶음 행 N회 발생·
  최종발생(KST)·펼치면 개별 발생+스택, 해결 버튼 행/묶음 단위), layout 탭 '에러 로그', 개요에 미해결
  에러 뱃지(클릭→에러 로그).
- 기록은 전부 best-effort(DB 미설정 시 setup no-op으로 비활성). 검증: 654 pass(+ErrorStore 3) ·
  ruff/mypy clean · tsc/build OK · 010 적용·엔드포인트 401 가드 확인. 백엔드 재기동.

### AI채팅 맥락파악 실패 2건 수정 (2026-06-14)

- **① '아가' 오추출(맥락 갇힘)**: "…다시 회사로 돌아가게 될까?"의 '돌아가게'에서 부분문자열 '아가'를
  동반자 별칭으로 오인 → 대상 확인에 갇힘. conversation.py:106 별칭 정규식에 단어 경계 가드
  `(?<![가-힣])(\d+\s*호|신랑|아가)(?!씨)` — 앞에 한글(동사 어간)이 붙으면 제외, '아가씨'도 제외,
  조사(아가는/아가가)는 정상. 실측: '돌아가게'·'나아가야' 오추출 0, '아가는'(직접 입력)은 그대로 확인 대상.
- **② 취업운→재물운 오답**: '취직/복직/구직'이 도메인 단어에도 이벤트 단어에도 없어 general로 떨어지고,
  특정 사건 앵커가 없어 일반 월별 흐름(재물 등)으로 샘. (a) EVENT_WORDS[JOB_GAIN]에 취직·구직·복직·일자리
  추가, (b) query_parser: 도메인어 미검출이어도 event_key가 잡히면 EVENT_DOMAIN으로 도메인 유도(향후
  갭도 방지). 실측: 취직·복직·구직·재취업 → career/job_gain.
- 검증: 657 pass(+3 회귀) · ruff/mypy clean. 백엔드 재기동.

### '직장운' 의미 매핑 — 재직 전제(이직+승진) + 비정직원 시 취업 포함 (2026-06-14)

- **사용자 기준**: 직장운 문의는 통상 재직 상태의 이직·입지·승진 / 단, 정직원이 아니면 취업도 대상.
- **파서**(query_parser): '직장운/직장 운' → event_key=이직(career_change) + event_keys=[승진(promotion)],
  domain=career. event_keys는 graph_scope(context_reducer:760, planner:93)에 합산돼 이직·승진 후보가
  함께 산출.
- **상태 판정 배선**: chat 라우터가 대상 사주의 2단계 프로필 employment_form을 best-effort 조회해
  chat_service로 전달(부재·무DB면 None — 규칙11 선택 입력). nonregular = 고용형태{계약직·프리랜서·
  무급가족종사} ∪ 질문 키워드(_UNEMPLOYED_KEYS). 재직 전제 사건(이직·승진)+nonregular면 intent.event_keys
  에 취업(job_gain) 추가(plan 이전 보강 → scope 반영) + _CAREER_NONREGULAR_DIRECTIVE(취업 포함, '무직'
  단정 회피, 당락 단정 금지). 기존 무직→이사 분기는 비career 맥락에만 적용(도메인 인지).
- 실측(dry_run): 직장운+정규직/미상→이직·승진만 / +계약직·백수→취업 디렉티브 ON / 이사+백수→기존 이사
  분기 유지. 검증: 658 pass(+취업 동의어·직장운 회귀) · ruff/mypy clean. 백엔드 재기동.

### 이벤트 엔진 월 기간 절기 경계 어긋남 수정 — 절기 기준 당월 라벨 (2026-06-15)

- **증상**: 양력 달의 節 이전(보통 1~7일경) 구간에서 '당월 운세'가 한 칸 어긋난 월운으로
  풀림. 월운 LuckPillar 라벨은 절기 시작 시각의 로컬 월(未월=2026-07 등)인데, 코드 곳곳이
  `f"{today.year}-{today.month:02d}"`(양력)로 만든 라벨을 절기 월 라벨과 동일시했다. 예: 양력
  7/3은 절기상 午월(2026-06)이나 양력 라벨은 2026-07.
- **헬퍼 신설**: `manse_analysis/luck/luck_calendar.py` — `luck_month_label(day, table, tz)`
  (절기 기준 당월 YYYY-MM; `month_branch`의 지배 節 시각 로컬 월) + `shift_month_label(label,
  delta)`(라벨 산술). 런타임 manse_core 의존 없음(SolarTermTable은 TYPE_CHECKING, table 주입).
- **수정 지점(5)**: ① time_parser `parse_time(current_month_label)` — '이번 달/다음 달'·미래
  (C8a)·과거(C8b) 롤링 창 기준 달을 절기로(query_parser·conversation 통해 전달). ② context_reducer
  `build_reference_frame`/`build_llm_input`(current_month_label) — P6 지남/남은 구간 판정 +
  serialize cur_month을 ReferenceFrame.this_luck_month(신규 필드)로. ③ chat_service —
  차트 타임존으로 당월 라벨 재확정 후 current_month·_rolling_months·parse_message·build_llm_input
  에 주입(파싱 시점은 차트 전이라 KST). ④ report_service RPT_FOCUS '향후 N년' cur 필터. ⑤
  precompute_scheduler `_missing_levels` 당월 키(table 주입 시 절기, 미주입 시 양력 폴백).
- **타임존**: 월운 라벨이 생성된 차트 `time_correction.timezone` 우선, 미상/파싱 선행 시 KST 폴백
  (사용자 승인 2026-06-15).
- 검증: 신규 test_luck_calendar.py 10건(경계 7/1·7/6·7/7·8/1·8/8 + shift + parse 주입/폴백) 포함
  전체 598 pass · ruff/mypy clean. 백엔드 재기동.

### 월 총운(이번 달) 일 단위 산정 절기 월 보정 — 누수 후속 (2026-06-15)

- **점검 발견**: 앞선 절기 월 보정 후에도 `_build_period_fortune` 월간 분기가 일운을
  `luck_days(birth, year, mon)`(양력 월)으로 뽑아, '이번 달 총운'의 주의/기회 날짜가
  절기 경계에서 새어나감. 예 today=2026-08-01(절기 未월): 주의시기에 2026-07-01(절기상
  午월)이 끼고, 당월 절기 구간(8/1~6)은 누락 → 전부 과거 날짜만 제시.
- **수정**: `_solar_month_range(label, tz)` 신설(`bounding_month_terms`로 절입~다음 절입 전일
  산출). 월간 분기에서 걸치는 양력 두 달 일운을 합치고 PeriodSpec를 절기 범위로 지정 →
  `build_lifestyle_context._in_period`가 절기 경계 일운만 남김. 인접 절기월 월운 composite가
  월 비교에 섞이지 않게 MONTH 레벨은 당월(start) 라벨만 유지.
- **검증**: 未월(8/1)→주의/기회 모두 7/7~8/6 범위·午월 7/1~6 배제 / 午월(7/3)→7/1 포함·6/6~7/6
  범위 / 申월(다음 달)→8/8~ 8/7 이후만. 신규 test_period_fortune_solar_month 2건 포함 전체
  600 pass · ruff/mypy clean. 백엔드 재기동.

### 합(合) 작용 모드 — Phase 1 천간합 판정 모듈 (2026-06-15)

- **배경**: Graph RAG가 합의 종류(합화/합거/합반/합래/쟁투)를 반영 못함 → 2회 딥리서치로
  HAP_INTERACTION_SPEC 규격 작성 후 엔진 판정 모듈 1차 구현. 정책: 化 3단계 확률화·일간
  합거×기반×·다수설 우선(2026-06-15 사용자 확정).
- **신규(어댑터, manse_core 무수정)**: `manse_analysis/relations/hap_modes.py` —
  `resolve_stem_hap(pillars, favorability, luck_stems=…)` 순수 함수.
  - B 게이트: 간격극(사이 극천간)=차단 / 隔位(비인접)=약화 / 쟁합·투합(제3 천간 경합, 위치 기준).
  - C-1 化 3단계: 化神 season_state(월령)+통근+방해 → confirmed/conditional/none.
  - 모드: 합화(transform)/합반·합거(bind+affected 길흉)/일간 본신지합(combine_self)/blocked.
  - 용기신 길흉: 기·구신 묶임=boon, 용·희신 묶임=harm. 보수 가중치 `HAP_WEIGHTS`(# CALIBRATE).
- **범위 밖(Phase 2)**: context_reducer/LLM 계약·그래프 retrieve·점수 엔진 배선.
- 검증: test_hap_modes 6건(합화 confirmed·합반/합거·본신지합·쟁투·간격극·실제 예제) +
  전체 606 pass · ruff/mypy clean.

### 합 작용 모드 — Phase 2a LLM 입력 배선 (2026-06-15)

- **목표**: Phase 1 판정(resolve_stem_hap)을 LLM 입력에 연결 — 대화·총운·**테마사주** 전부.
- **신규** `saju_engines/hap_lines.py`: `natal_hap_mode_lines`(원국)·`luck_hap_mode_lines`(운) —
  합화/합반/합거/본신지합/쟁투를 모드+영향+신뢰도(확정/조건부/불성) 한 줄로 직렬화. 단정 금지.
- **배선**: ① `ChartInterpretation.hap_modes` 필드 신설, `build_chart_interpretation`이 원국 합 채움 →
  `serialize_chart_prefix`(대화·리포트·테마 **공용** 고정 prefix)가 "합 작용(원국)" 렌더 →
  3경로 동시 커버. ② `build_luck_grounding`(총운)에 운 천간합 모드 줄 추가.
- **버그 수정(hap_modes)**: 본신지합 판정을 **일주(日) 자리** 기준으로(StrEnum 싱글톤이라 같은
  글자 비견을 일간으로 오판하던 것 수정). 己亥+시간 비견 己+운 甲 → 일간 본신지합 + 시간 비견
  합거(쟁합)로 정밀 분류. 표기 순서 천간 표준순 정규화 + dedup.
- **범위 밖(Phase 2b)**: 점수 엔진 반영(합거 기신=+/희신=−·합반 감산), 그래프 retrieve, 리포트
  per-기간 운 합.
- 검증: test_hap_lines 6건 + test_hap_modes 6건 + 전체 618 pass · ruff/mypy clean. dry-run 확인(원국
  prefix·총운 운 합 등장).

### 합 작용 모드 — Phase 2b 리포트/테마 운 합 (2026-06-15)

- **목표**: '테마운세에도 적용' 완성 — 리포트(테마사주)의 운 섹션에 per-기간 운 천간합 모드 주입.
  (원국 합은 Phase 2a serialize_chart_prefix 공용으로 이미 커버.)
- **구현**: report_service `_ReportData.luck_hap_lines()` — 후보 기간 세운·월운·대운 천간 수집 →
  `luck_hap_mode_lines`로 모드(합화/합반/합거/본신지합/쟁투)+신뢰도 줄 산출 → `luck_block()`(운
  섹션 데이터 블록)에 "[합 작용(운)]" 블록 추가. 명식 섹션엔 미부착(원국 합은 prefix).
- **점수 반영은 보류**(사용자 결정) — 정량 가중치 [미검증]·캘리브레이션 데이터 필요. 그래프
  retrieve 모드 연결도 보류(hap_lines가 이미 엔진 판정 모드를 LLM에 전달 → 사실상 해소).
- 검증: test_report_hap_lines 3건 + 전체 685 pass · ruff/mypy clean. dry-run으로 career 섹션에
  운 합 블록(합화 확정·합반·합거·본신지합·쟁합) 등장 확인.

### 합 작용 모드 — Phase 3 지지합(육합·삼합·방합) (2026-06-15)

- **신규**: `hap_modes.resolve_branch_hap` — 육합(化神 월령으로 합화/합반, 지지는 보수적 묶임
  경향)·삼합(완전국/반합 왕지 포함만)·방합(완전 강화/부분) 판정 + 결합 지지 사이 동시 충/형/파/해
  (`co_relations`, §D-2). `hap_lines._format_branch`로 직렬화해 원국·운 모드 줄에 합류.
- **배선**: natal/luck 모드 줄에 지지합 추가 — build_luck_grounding(운 지지)·report luck_hap_lines(운
  세운·월운·대운 지지)까지 천간+지지 동시 주입.
- 검증: 申巳合 → 합반 + 동시 파·형(§D-2 케이스), 申子辰 삼합 水국, 방합 부분 등 dry-run 확인.
  test_hap_modes/test_hap_lines 지지합 5건 추가 + 전체 690 pass · ruff/mypy clean.

### 합 작용 모드 — Phase 3 정련: 지지 합거 정기 십성 + 화기격 (2026-06-15)

- **지지 합거 정기 십성**: 육합 합반/합거 시 묶인 지지의 정기(正氣, main_hidden_stem) 십성을
  일간 기준으로 산출해 길흉 부여(기·구신 묶임=길, 용·희신 묶임=흉). 운 지지 육합은 direction=away.
  예: 申巳合 합반 → 庚 상관=한신 · 丙 정인=희신 불리(길 상실).
- **화기격(化氣格) 후보**: 일간 본신지합 + 化神 통근 + 化 확정 시 chart_transform=True. 일간 무근=진화,
  유근=가화 구분(note). hap_lines가 '본신지합 → 化氣格 후보(일간이 化神 X로 化)'로 표기.
  (성립 후 격국·용신 재평가는 geokguk 연계 — 후속.)
- 검증: test 2건 추가(화기격·지지 합거 정기) + 전체 692 pass · ruff/mypy clean.

### 결실 유불리 마커 — 천간 단순 단정의 비대칭 보정(통관/누설) (2026-06-15)

- **문제**(사용자 지적): 월별/후보 '⚠계약·결실 불리'가 **천간 기신/구신만 보고** 무조건 부착 →
  지지 용·희신·관인상생(통관)을 무시. 예: 己 일간 신약, 2026-06 甲午 = 甲(관·기신)生午(인·희신)生
  일간 = 관인상생인데 '결실 불리'로 단정. 역으로 천간 길신 달엔 경고가 전혀 없어 과낙관 여지.
- **수정**: `_ganji_result_nuance(천간역할 × 지지 생극)` 신설 — ①흉천간이 지지 용·희신 생 → ↗통관
  순화(검토월 아님, 과낙관만 경계) ②흉천간 비통관 → ⚠계약·결실 불리(현행) ③길천간이 지지 흉신
  생 or 지지 흉신에 피극 → ⚠천간 길신 누설(좋은 달 단정 금지) ④길천간 무해 → 무마커. 후보
  caution_note·월별 _roles_for·월별표 부가설명·범례에 일관 적용.
- **버그 수정**: caution 블록에서 `note` 변수가 incoming_ten_god_note('유입 = 천간')를 덮어쓰던 것
  → `nuance_note`로 분리.
- 검증: 사용자 사주 2026-06이 '↗통관 순화 — 관인상생으로 순화, 과낙관 금물'로 정정. 전체 692
  pass · ruff/mypy clean.

### LLM 프롬프트: Trigger 한글화 + 채팅 답변 마무리(정리·질문) (2026-06-15)

- **Trigger 순화**: LLM 지시문 '5. …Trigger→진행→결과'의 영문 Trigger를 '촉발'로 한글화 —
  채팅(_SYSTEM_PROMPT)·리포트(_REPORT_SYSTEM_PROMPT)·_BASE_INSTRUCTION 3곳. (내부 개념
  'Trigger Month ≠ Execution Month'(CLAUDE.md §4·prediction)는 표시용이 아니라 유지.)
- **채팅 전용 마무리 지시**: _SYSTEM_PROMPT에 '8. 답변 끝에 핵심을 한두 문장으로 정리하고
  사용자가 이어서 생각해볼 만한 질문 1개를 덧붙인다' 추가. **테마사주(리포트)에는 미추가**
  (사용자 확정 — AI채팅상담에서만 적용). 앞서 오해로 CLAUDE.md §8에 넣었던 항목은 환원.
- 검증: 채팅/리포트 프롬프트 분리 확인 + 전체 692 pass · ruff clean.

### 발현 분기(형제 사건) 표면화 — 이직↔이사 무시 결함 보정 (2026-06-15)

- **결함**(사용자 실로그): 2025-08 甲申에서 이직(career_change)=100점이 우세로 잡히고 이사
  (relocation)는 같은 '이동·변동' 계열 형제로만 분기에 들어가는데, ① 월별 요약 행의 '분기'가
  줄 끝에 묻히고 ② 골자([유력 달 종합])엔 계열만 적혀(판별 지시는 표 하단 범례에만) → LLM이
  우세 사건명(이직)에 고정, 실제 발현(이사)을 무시.
- **수정(텍스트 전용·점수 불변)**: ① 월별 요약 행의 분기를 **사건명 바로 뒤**로 이동(줄 끝→
  2번째). ② 골자의 '발현 분기: {계열}'에 **판별 지시 직접 부착** — "우세 사건명에 고정 말 것,
  같은 계열 형제(이직↔이사)가 실제 발현일 수 있으니 맥락(직업·거주 변화)으로 판별·단정 금지"
  (골자는 '누락 금지'라 LLM이 따름).
- 검증: 2025-08 행/골자에 이사가 표면화됨 확인. 전체 692 pass · ruff/mypy clean.

### 테마사주 풀이 품질 — 근거 경로 내부화 + 한해풀이 반복 해소 + 케이스별 프롬프트 (2026-06-16)

사용자 실사용 피드백(지정년 총운 출력) 기반 3개 개선(사용자 승인 후 구현):

- **이슈1 — 근거 경로 내부용어 누출**: "근거 경로: 관계 발동 → 용기신 품질 → 복수 가능성"이
  본문에 그대로 노출됐다. 누출 4겹을 모두 '내부 근거(전문용어 노출 금지, 일상어로 풀어 녹임)'로
  전환: ① 프롬프트 지시(그대로 인용→내부 근거) ② 검사8(미인용 강제→내부용어 노출 soft 위반,
  `INTERNAL_JARGON_LABELS`) ③ `_repair_section`의 '근거 경로:' 자동 덧붙임 제거 ④ 재생성 시
  인용 강제 제거. `_tighten`이 '근거 경로:' 잔여 줄 결정적 제거. (절대원칙2 — 경로는 LLM
  **입력**엔 유지, **출력** 인용만 폐지.)
- **이슈2 — 한해풀이 강신호 반복·intent 편향**: 전 섹션이 전역 top-8을 공유해 한두 강신호가
  12페이지 반복 + 지정 intent 없는 총운인데 한두 도메인만 사용. ① 섹션별 도메인 후보
  (`domain_candidates` — 길·흉 포함, 주의운 ≤2 보장) Y-06~Y-09 + F-15~F-18 적용(RPT_YEAR·
  RPT_FULL 공통, 사용자 확정). ② Y-05에 12개월 전체 표(`month_overview_lines` — 간지·도메인·
  강도밴드·길흉·★Top3). ③ 프레이밍에서 길·흉 함께·활용법 지시. `allowed_scores`를 전 scored로
  확장(도메인 후보 점수 검사 통과).
- **이슈3 — 케이스별 전문 프롬프트 + intent 기간**: `_product_framing(spec)`으로 인생총운/
  지정년총운/지정기간 intent운 케이스별 프레이밍을 섹션 프롬프트 선두 주입. intent 풀이 기간을
  '인생 전반'→**현재월~+5년**(`currentForwardPeriod`)으로 변경, 테마 scope·desc에 '향후 5년'
  반영. (지정월총운은 docs/10 미정의 — 이번 범위 제외, 사용자 확정.)
- 검증: 백엔드 전체 pass(ruff/mypy clean), 프론트 tsc·vitest·production build pass. docs/10
  §7 검사8·4·4-2 규격 동기화. 변경 파일: report_service.py, report_event_input.py,
  report_checks.py, report_builder.py, llm_event_serializer.py, frontend/lib/themes.ts.

### 재물·횡재(windfall) 모델링 강화 Phase 1 — 원국 횡재 그릇 + 그래프 RAG (2026-06-16)

로또 1등 당첨 사주(1984-10-31 戌시, 戊戌 일간) 분석을 시스템 인사이트로 반영. 사용자 확정 범위:
신규 이벤트 키 없이 기존 WINDFALL/WEALTH_CHANGE 유지 · 엔진/스키마 신설 · 로또 택일 포함(Phase 3) ·
단일 사례 과적합 방지(reviewed:false + 회귀 코퍼스 검증 후 가중치 확정).

- **신규 분석** `wealth_capacity.analyze_wealth_capacity` — 원국 횡재 '그릇' 6요소(身強임재·재성 투간·
  재성 뿌리·암장 식상[식상생재 통로]·재성국 삼합 씨앗·묘고 반복) 판정. 운 미반영. `WealthCapacity`
  pydantic 모델(shared_types). force_analysis(신강약·십성·뿌리)+지장간 재사용.
- **스키마** `SignalSpec.natalWealthCapacity`(strong/moderate) 신설 — windfall 해석 규칙을 원국 그릇에
  게이트. **events/wealth.json**에 그릇 게이트 windfall 후보 3건 추가(reviewed:false, 보수적 0.3~0.45,
  표현 제한 note).
- **그래프 RAG** `graph_builder`: `wealth_capacity_strong/moderate` 노드 + 규칙 supports 엣지 추가.
  재컴파일 → **event_graph v1.1.0**(노드 186→191·엣지 384→394). chat_service·테스트 로더 v1.1.0 갱신.
- **리포트 노출** report_service: 재물 섹션(W-04·W-05·Y-07·F-16)에 [원국 횡재 그릇] 블록 표면화 —
  '그릇≠당첨, 운 발동 필요' 전제 + 당첨 단정·번호 추천 금지 가드 문구.
- **과적합 차단**: 당첨 사주는 6/6 strong이나 대조군도 1~5요소로 갈림(그릇은 흔함 → 예측 아님). 회귀
  테스트는 '구조 플래그 검출'만 검증(당첨 예측 금지).
- **미반영(후속)**: 실제 per-period 점수 가산은 transit 발동(申子辰 누적완성·辰戌충 개고)과 함께 Phase 2,
  로또 택일(날짜/방향/시간)은 Phase 3, 가중치 확정은 Phase 4(캘리브레이션).
- 검증: 전체 백엔드 pass(신규 test_wealth_capacity 5건 포함)·ruff·mypy clean, 사전 validate→compile 통과.
  docs/05 signal 키·v1.1.0 동기화. 변경: wealth_capacity.py(신규)×2, dictionaries.py, graph_builder.py,
  events/wealth.json, report_service.py, chat_service.py, report_event_input.py(mypy 수정).

### 재물·횡재 Phase 2 — 운 발동(transit) 정밀화 + 보수적 점수 가산 (2026-06-16)

Phase 1(원국 그릇)에 이어 '운에서의 발동'을 결합. 사용자 보완: **원국에 그릇/씨앗이 없어도 운에서
완성되는 경로**도 인정(그릇을 하드 게이트가 아니라 배율로). 사용자 확정: 보수적 게이트 가산 + 표면화.

- **발동 감지** `detect_wealth_activations` — 거버닝 스택(원국+대운+세운+월)에서 ① 재성국 완성(삼합,
  운 단독/원국+운) ② 묘고 충개고(辰戌·丑未충, 운 개입) ③ 식상생재(운 천간 식상+재성 동시 투간)를
  판정. 모두 **운 참여 필수**(정적 원국만으론 미발동). 단순 '재성 투간(운)'은 평범한 재물 운이라
  횡재 발동에서 제외(과발동·base 중복).
- **점수 가산** `WealthActivationModifier` — windfall/wealth_change에만 그릇 배율(strong 1.0/
  moderate 0.7/weak 0.5)×발동 가중(재성국 0.18·충개고 0.12·식상생재 0.10)으로 (1+boost)배. 잠정값
  (Phase 4 캘리브레이션 전). EventEngineV2._score_target 체인에 배선(원국 그릇 1회 계산→스레딩).
- **사전/그래프** events/wealth.json에 그릇 게이트 없는 운-완성 windfall 후보(편재+삼합, 재성 지지 충)
  추가 → event_graph v1.1.0 재컴파일(192노드·396엣지).
- **리포트** 재물 섹션 그릇 블록에 '발동 조건(재성국 완성·충개고·식상생재)' 안내 추가 — '그릇 없어도
  운 완성 시 일부 발동, 그릇이 받칠수록 크게' 명시.
- **검증/안전**: 전체 백엔드 pass(핫패스 회귀 0)·ruff·mypy clean. 발동 빈도 점검 — 당첨자 충개고 3건
  등 선택적. 보수 가산이라 base 포화(100) 시 클램프로 무영향, 미발동·타도메인 무변(테스트 보장).
  당첨 단정·번호 생성 금지 가드 유지(prohibit_windfall). docs/05 동기화.
- **남은 단계**: Phase 3 로또 택일(일운 길일·방위·시진), Phase 4 캘리브레이션(당첨 코퍼스+대조군)으로
  가중치 확정 → reviewed:true 승격.

### 재물·횡재 Phase 3 — 로또 택일 방위(方位) 추가 (2026-06-16)

기존 택일(Phase 7: 날짜 랭킹·시진 12칸·windfall 변동성 경고·로또 번호 거부·투자 고지)에 **방위**를
추가(docs/08 D2-5 '어느 방향으로 가서 사야'). 번호 생성은 변함없이 거부.

- **방위 엔진** `direction_fits(wealth_element, yongsin_element)` — 정오행 방위(木동·火남·土중앙·金서·
  水북) 기준 재성 방위 1.0 / 식상(생재) 방위 0.8 / 용신 방위 0.7 / 그 외 0.5. `DirectionFit` 타입 +
  `DateSelectionResult.directions`. `select(wealth_element=...)` 시 부착.
- **chat 배선** `_date_selection_block`: 횡재/재물 목적이면 `analyze_wealth_capacity(chart).wealth_element`로
  재성 방위 + 시진(include_hour_fit)을 함께 제공. DateSelectionBlock에 directions·hour_fits 필드 추가,
  context_reducer가 '방위: …' '시간대: …'로 렌더.
- **표현 정리(사용자 지적)**: 방위/시간대 줄의 '(참고 — 당첨 보장 아님)' 중복 강조 제거 — 바로 아래
  '주의: 당첨·수익 단정 불가…' 경고가 한 번만 전달하면 충분.
- **E2E 확인**: "로또 사러 가기 좋은 날·방향·시간대" → 날짜표 + 방위(북=재성 水·서=식상 金) + 시간대
  (子·申·酉·亥시) + 변동성 경고 + 근거 경로(Phase1 그릇→Phase2 재성국 완성). 로또 번호 요청은 정책 거부 유지.
- 검증: 전체 백엔드 pass(신규 방위 테스트 2건)·ruff·mypy clean.
- **남은 단계**: Phase 4 캘리브레이션(당첨 코퍼스+대조군)으로 Phase 2 발동 가중치·Phase 1 그릇 신호를
  검증 후 reviewed:true 승격.

### 재물·횡재 Phase 3+ — 방위에 용희기구한 반영(기신·구신·생구신 감점) (2026-06-16)

사용자 지적: 재성 방위라도 그 오행이 기신·구신이거나 구신을 생하는 방향이면 추천하기 어렵다.

- `direction_fits(wealth_element, favorability_by_element)` 재설계 — **역할 기반**(용신 1.0/희신 0.85/
  한신 0.55/기신 0.3/구신 0.15)을 기본으로, 재성(+0.1)·식상생재(+0.05) 가점은 **역할이 용신/희신/한신
  일 때만** 적용(기신·구신 재성 방위는 가점 없이 낮음 = 추천 어려움). **구신을 생하는 방위는 0.6배 감점**.
  note에 역할·'구신 생(주의)' 표기.
- `DateSelectionEngine.select(favorability=...)` 파라미터 추가, chat `_date_selection_block`이
  `favorability_map(chart)`를 주입.
- E2E(당첨 사주): 水=용신→북 1.0(재성·용신), 金=희신→서 0.9(식상생재), 木=한신이나 火(구신) 생→동 0.33,
  土=기신→중앙 0.3, 火=구신→남 0.15. 흉신·생구신 방위가 정확히 하위로.
- 검증: 전체 백엔드 pass(방위 테스트 3건)·ruff·mypy clean.

### 챗 근거 경로/note 누출 정리 (2026-06-16)

이슈1(리포트 근거 순화)을 챗 경로에도 적용. 로또 택일 E2E에서 챗 [근거 경로]·해석 힌트에 wealth.json
저작 note의 메타("(windfall은 표현 제한 — 당첨 단정 금지, 변동성·과몰입 경고)" 등)와 "(표현 제한)"
이벤트 라벨이 그대로 노출되던 결함 정리.

- **택소노미 라벨 근본 수정**: `EventKeyV2.WINDFALL` "횡재(표현 제한)" → "횡재"(표현 제한은
  prohibit_windfall 금기룰이 강제 — 라벨 비주입). 그래프 재컴파일(event_windfall 라벨='횡재').
- **저작 메타 괄호 제거**: context_reducer `_AUTHORING_PAREN_RE` + `_clean_evidence_text` 추가 —
  근거 경로/보조·반대 근거/해석 힌트에서 표현 제한·당첨·단정·번호 거부·로또·과몰입·투자 조언·고지·
  경계 동반 류 괄호를 제거. '(재성국 완성)'처럼 의미 있는 괄호는 보존. 경로 끝 단계가 이벤트
  라벨과 같으면 'label:' 중복이라 제거.
- 의도된 표기는 유지: '주의:' 변동성 경고, '금기 표현:'(prohibit_windfall 강제 노출), 표 읽는 법·
  신살 등 시스템 지시.
- 검증: E2E에서 [근거 경로]='횡재: 편재 → 편재+삼합(재성국 완성)+원국 그릇 강 — 큰 재물이...'로
  메타 제거·끝단계 중복 제거 확인. 전체 백엔드 pass(신규 정리 테스트 1건)·ruff·mypy clean.

### 결혼·자산 자원 구조 분석 — 시주 민감도·자산 출처·시댁 재력(성별 인지) (2026-06-16)

실사례(둘 다 丙火 여성, 60대=1961-09-30, 같은 년월일·다른 시주): 午시(甲午)=부모 혜택·보호,
卯시(辛卯)=시댁 재력·결혼 후 자산. 사용자 확정: **신규 이벤트 키 없이 구조 프로필**, **중립·비단정**.

- **신규 분석** `marriage_resource.analyze_marriage_resource` — 성별 인지(여성 관성=배우자, 재성=
  시댁·물질 환경). 6요소: 배우자 별 존재(투간·본기만), 재성 년월(집안)/시주(결혼후·결과), 재성 세력,
  인성·뿌리 보호, 재성궁 충(발동 잠재), 시주 자원 역할. 자산 출처 경향(parental/spouse_family/self,
  중립·가능성). `MarriageResourceProfile` 타입(shared_types).
- **핵심 차별화 검증**: 같은 년월일·시주만 다른 두 사주에서 spouse_family가 卯시(재성 시주)만 성립,
  午시는 parental만. 여성 관성 투간·본기 부재(水 0)여도 재성 환경으로 spouse_family 잠재 포착.
- **리포트 표면화**: 관계·재물구조 섹션(R-03·R-05·RP-03·RP-04·F-17·Y-08·W-03·J-03)에 [결혼·자산
  자원 구조] 블록 — '신분 상승·신데렐라·반드시' 단정 금지 + 성별 인지 + 돈의 출처(부모/배우자 집안/
  자수성가) 구분 지시. 신규 이벤트 키·그래프 신호 없음(해석 맥락만).
- **민감 프레이밍**: '신데렐라/신분 상승' 라벨 미생성, 재성 환경은 '물질 기반 두드러질 잠재'(가능성)
  로만. 같은 구조 흔함 → 예측 아님(확증편향 차단).
- **충 발동**: 卯酉충처럼 재성궁을 건드리는 충을 '발동·변화 잠재'로 표면화(엔진 relation_palace가
  이미 충을 감점 아닌 발동으로 처리하는 것과 정합).
- 검증: 전체 백엔드 pass(신규 marriage_resource 테스트 2건)·ruff·mypy clean.

### 건강 리스크 Phase 1 — 원국 건강 취약 구조 분석 (2026-06-16)

전문가 강의 기반 고전 명리 건강 룰을 원국 구조로 흡수. 사용자 확정: **신규 키 없이 취약 구조 프로필**,
**수명·사망 예측 없음 + 의료 면책 필수**, '적당한 경고성(검진 유도)' 허용.

- **신규 분석** `health_vulnerability.analyze_health_vulnerability` — 손상 장기 오행(약+극+통관약),
  관다신약, 식신 약·편인 도식, 과다 기신 오행, 일간/식신 입묘 글자(천간별 묘지 표준표), 일간 물상
  예외(辛 토다매금 등). `HealthVulnerabilityProfile`·`OrganVulnerability` 타입.
- **오행-장기 매핑** `dictionaries/health_element_organs.json`(하드코딩 금지, reviewed:false) — 木 간·담
  계열 등 '계열'로만(질병명 단정 금지).
- **리포트 표면화** 건강 섹션(Y-09·F-18, health 주제 C-02·C-06)에 [원국 건강 취약 구조] 블록 —
  **'의료 진단 아님·질병명·수명·사망 절대 단정 금지' + 예방·검진·전문의 상담 톤** 명시. 경고성 점수
  미노출(Phase 2).
- 검증: 전체 백엔드 pass(신규 건강 테스트 3건)·ruff·mypy clean, 사전 validate(52파일) 통과.
- **다음(Phase 2)**: 운(대운 배경·세운 사건화·월 발현) 재자극 감지 → 위험 등급/점수(검진 유도 톤,
  사망·질병 단정 없음).

### 건강 리스크 Phase 2 — 운 재자극 위험 시기·등급 (2026-06-16)

Phase 1(원국 취약 구조)에 운(대운 배경·세운 사건화·중첩)을 결합해 '관리 권장 시기'를 등급화.
사용자 확정: 위험 등급/점수 필요 + 적당한 경고성(검진 유도), 단 수명·사망·질병 단정 없음.

- **분석** `health_risk_windows(result, profile, today_year)` — 세운(향후 N년) 각 해에 7룰(천극지충·
  손상 오행 재공격·일간/식신 입묘·관살 재유입·과다 기신 반복·편인 도식) 적중 점수 + 관할 대운 배경
  0.4 가산 + 대운·세운 중첩 가산. `HealthRiskWindow` 타입(period·daewoon·score·level·reasons).
- **등급(행동 권고)**: 생활 관리(30~49) < 정기 검진 권장(50~69) < 적극 관리·검진 권장(70+).
  '사망·중병' 류 라벨 없음. **임계(>=30) 이상 상위 6개만** 노출(과도한 경고 차단).
- **리포트**: 건강 블록에 '관리 권장 시기(질병·사망 예측 아님 — 그 무렵 컨디션·검진 신호)'로 표면화.
  스코어링 핫패스 미변경(리포트 분석으로만 — 안전).
- **보수성 확인**: 실차트 1~2개 시기·모두 '생활 관리' 수준으로 산출(알람성 아님). 가중치 잠정(Phase 4
  캘리브레이션 전).
- 검증: 전체 백엔드 pass(신규 위험시기 테스트 2건 포함)·ruff·mypy clean.

### 사주 기본 개념 보완 — 연운 시대 기운 + 부/귀 지향 (2026-06-16)

전문가 강의('사회운 먼저, 개인은 그 안에서' + '부로 가나 귀로 가나')를 우리 서비스 기준으로 감사 →
두 갭 보완. 사용자 확정: A·B 둘 다, 경제·시장 예측은 별도 논의(미도입).

- **감사 결과**: ① 사회운/시대운 우선 — 없음(개인 중심) ② 세운 자체 성격 framing — 없음 ③ 부/귀 분류
  — 격국 격신 그룹은 있으나 '부/귀 축'으로 미표면화 ④ 천간별 시기 유불리 — 개인 스코어링으로 커버.
- **A. 연운 시대 기운** `era_energy.era_energy_profile(stem, branch)` — 그 해 간지의 오행·음양·계절·
  통설 키워드를 명리로만 캐릭터화(경제·시장 예측 제외). 리포트 Y-01(한해)·F-11(총운 올해)에 '개인
  풀이 앞 사회 맥락'으로. 예: 2026 丙午 = 여름 火왕·양→음 교차(하지)·드러남·개인화.
- **B. 부/귀 지향** `wealth_status_lean.analyze_wealth_status_lean` — 격국 격신 그룹(재격·식상→부 /
  관격·인성→귀) + 재성/관성 분포로 부/귀/부귀겸전/뚜렷하지 않음. 우열 아님·방향. 리포트 F-04·J-02·
  J-03·W-02에 표면화.
- **경계 유지**: 시대 기운은 '경제·시장·채용 단정 절대 금지' 프롬프트, 명리 기운 톤만.
- 검증: 전체 백엔드 pass(신규 테스트 2건)·ruff·mypy clean.
- **미결**: 강의의 '사회운'에 든 경제·시사 연결을 어떤 형태로 다룰지 사용자와 추가 논의 필요.

### 구조 분석 블록 — 누출 차단 + 총운/intent/챗 활용 + 운영자 시대 노트 (2026-06-16)

지금까지 추가한 구조 분석(횡재 그릇·결혼/자산·건강·부귀·시대 기운)을 누출 안전하게 정리하고
리포트·AI채팅 전반에 배선. 사용자 확정: intent 미확정이면 **총운으로 간주(모든 블록)**, 확정 도메인은
선택적. 그리고 경제 연결은 **운영자 큐레이션(옵션1)**.

- **누출 차단**: `wealth_status_block`이 영문 격신 그룹('wealth')·원시 퍼센트('재성 30%')를 노출하던
  결함 → 한글 그룹('격신은 재성')·정성 표현('재성이 관성보다 우세')으로 수정. 단일 소스
  `structural_context.py` 포맷터(영문 변수·점수·band 코드·퍼센트 비노출) 신설.
- **챗 배선**: `chat_service._structural_context(result, intent, today)` — intent.domain==GENERAL(미확정)
  → 총운으로 간주해 전 블록(시대 기운·횡재 그릇·부귀·결혼/자산·건강), 확정 도메인은 해당 블록만.
  `LlmInput.structural_context` 필드 + build_llm_input·serialize 배선. 궁합(다대상)은 생략.
- **테마 적합화**: 결혼/자산 블록을 직업 테마(J-03)에서 제거(주제 부적합 — 개별 intent 선택적 원칙).
  총운(F-04·F-11·F-16·F-17·F-18)은 5종 모두 부착.
- **운영자 시대 노트(옵션1)**: `dictionaries/era_notes.json`(연도/간지 키, 운영자 수기·검수, 참고용·
  단정 아님) + `era_curated_note()`. 시대 기운 블록에 '운영자 시대 노트(참고): …'로 동반(리포트·챗
  공통). 자동 경제 예측 아님(통제된 큐레이션).
- 검증: 전체 백엔드 pass·ruff·mypy clean, 사전 validate(53파일). E2E: 미확정 질문→5블록 전부,
  건강 질문→건강만, 부귀줄 영문·퍼센트 누출 0, 운영자 노트 표시 확인.

### 구조 블록 단일 소스화 — 리포트 블록을 structural_context로 위임 (2026-06-16)

리포트 `_ReportData` 블록 메서드와 `structural_context` 포맷터의 중복 제거(둘 다 누출 안전했으나
이원화). structural_context를 단일 소스로 확정하고 리포트는 위임.

- `structural_context` 포맷터를 풍부한 버전으로 통일(횡재 그릇 '발동 조건' 풀이, 결혼/자산 '출처'
  괄호, 건강 '입묘 주의 지지' 줄 포함).
- 리포트 `wealth_capacity_block`·`marriage_resource_block`·`health_vulnerability_block`·
  `wealth_status_block`·`era_energy_block`을 structural_context 위임 1줄로 축소(era만 리포트 전용
  연결 지시 1줄 추가). 누출 한글화 매핑(_CAPACITY_BAND_KO·_GENDER_KO·_LEAN_KO·_GEOKSIN_GROUP_KO)·
  미사용 import(era_energy_profile·era_curated_note·health_risk_windows) 제거 — structural_context로 이관.
- 검증: 전체 백엔드 pass·ruff·mypy clean. 리포트 F-04·F-11(+운영자 노트)·F-16·F-17·F-18 블록 동일
  렌더 확인, 챗도 동일 포맷터 사용으로 표면화 일관.

### 구조 질문에서 불필요한 시점/이벤트 데이터 제거 (2026-06-16)

사용자 지적: '내 사주는 귀한 사주일까?'(원국 구조 질문)인데 프롬프트에 월별 이벤트 후보·근거 경로·
과거 흐름이 잔뜩 들어가 답변이 엉뚱한 월별 사건(6월 계약·문서)으로 샘.

- **원인**: CHART_ANALYSIS(구조·성격·부귀·격국 질문)도 항상 이벤트 후보를 산출·포함. default_period가
  시점 창을 설정해 '질문 기간 내 후보 없음' 빈 안내까지 노출. 빈 이벤트 후보/근거 경로 섹션 헤더도 출력.
- **수정**: chat_service에서 `is_structural = query_type==CHART_ANALYSIS`이면 candidates·bundles 비우고
  default_period=None(시점 창 제거). context_reducer 직렬화는 이벤트 후보·근거 경로 섹션을 **내용 있을
  때만** 출력(빈 헤더 차단).
- **결과**: 구조 질문 = 원국·명식 해석·구조 블록(부귀·그릇 등)만, 시점/이벤트 데이터 0. 시점 질문
  (이직운 등)은 이벤트 후보·근거 경로·월별 요약 그대로 유지.
- 검증: 전체 백엔드 pass(신규 구조질문 게이팅 테스트 포함)·ruff·mypy clean.

### 다중 월 비교 질문 파싱 — '8월과 10월 중' 양쪽 다 잡기 (2026-06-16)

사용자 케이스: '이직, 이사와 관련해서 8월과 10월 중 언제가 나아?' — 구조-질문 게이팅과 별개 버그.

- **진단**: time_parser C5가 첫 월(8월)만 잡아 time_range=2026-08만 설정 → 10월이 '질문 기간 외'로
  밀려 비대칭 비교(8월만 이벤트 후보·근거, 10월은 월별 표 한 줄). query_type=timing_search라 구조
  게이팅 대상 아님(시점 데이터는 필요 — 적용 안 되는 게 맞음).
- **수정**: time_parser C5가 다중 월("8월과 10월")을 모두 추출해 **min~max 구간으로 스팬**
  (2026-08~2026-10). 단일 월은 그대로. → 질문 기간이 양 끝 달을 포함, 10월이 '질문 기간 외'가
  아니라 기간 내 비교 대상(월별 표 강도 순위 부여)으로.
- **확인**: 10월은 이 차트상 이직(career_change)·이사(relocation) 후보가 애초에 없음(재물·계약·사회
  갈등 우세) → 이벤트 후보에 10월 미표시는 정상. 단 '이사'(relocation)는 intent.domains엔 잡히나
  단일 domain 후보 필터엔 미반영(이 차트는 10월 relocation 신호 부재로 영향 없음 — 다중 도메인
  후보 반영은 후속 과제).
- 검증: 전체 백엔드 pass(신규 다중월 파싱 테스트 포함)·ruff·mypy clean.

### 다중 도메인 질문 후보 반영 — '이직, 이사' 양쪽 다 (2026-06-16)

'이직, 이사와 관련해서…'에서 '이직'은 event_key(career_change), '이사'는 secondary domain(relocation)
으로만 잡혀, build_llm_input의 후보 graph_scope(event_key/event_keys만)에서 relocation이 빠져
이벤트 후보에 이사가 안 나오던 비대칭 수정.

- context_reducer build_llm_input: graph_scope에 intent.domains의 secondary 도메인 대표 이벤트
  (_DOMAIN_PRIMARY_EVENT: relocation→RELOCATION 등)를 추가. 전체 도메인 이벤트로 범람하지 않게
  대표 1개만.
- 확인: '이직, 이사…' 질문 이벤트 후보에 '이직·직업 변화'+'이사(relocation)' 둘 다 표시.
- 검증: 전체 백엔드 pass·ruff·mypy clean.

### AI채팅 백그라운드 생성 + 폴링 복구 + 뱃지 (Bug B) / 폴백 즉시화 (Bug C) — 2026-06-16

모바일웹 실사용 결함 2건. (B) 질문 직후 사용자가 페이지를 닫거나 새로고침해 상태를 이탈하면
시스템이 답변을 끝까지 받아 전달하지 않고 폐기 → 생성된 Gemini 결과가 버려짐. (C) 메인(Gemini)에
요청해두고 기다리지 않고 곧장 폴백(ChatGPT)을 호출 → Gemini 결과가 생성 후 버려지는 비용 낭비.

- **Bug C (즉시화)**: `config/llm_config.json` `options.primary_attempts` 2→1. 불안정 프리뷰
  모델에 2회 재시도 후 폴백하던 것을 1회 시도 후 폴백으로 축소(메인 실패 시 폴백은 그대로 동작).
  `test_llm_client_failover`를 설정값 구동(`["gemini"]*attempts+["openai"]`)으로 변경 — 향후 튜닝에
  깨지지 않음.
- **Bug B (백그라운드 + 폴링 + 뱃지)**: 리포트 잡(BackgroundTasks) 패턴을 채팅에 적용. 답변을
  요청 커넥션과 분리해 서버에서 끝까지 생성·영속.
  - 마이그레이션 `011_chat_message_status.sql`: `chat_messages`에 `status('done'|'pending'|'error')`,
    `seen` 컬럼 + pending 부분 인덱스. `ChatHistoryStore.migrate()`가 007+011 적용.
  - `ChatHistoryStore`: `start_turn`(질문 저장 + 어시스턴트 pending 예약 → message_id),
    `complete_turn`(본문·상태 채움), `mark_seen`, `unseen_count`. `get_messages`에 status·seen,
    `list_threads`에 has_unseen·pending 노출.
  - `chat_service`: `system`/`call_type`를 dry_run 분기 앞에서 구성해 dry_run 응답이 LLM 호출에
    필요한 모든 것(prompt_preview·system_prompt·call_type)을 운반 → 백그라운드가 파이프라인
    중복 실행 없이 generate_reading만 수행. `ChatResponse`에 message_id 추가.
  - 라우터 `chat.py`: 빠른 분류(dry_run, LLM 미호출) → 로그인+스레드+LLM 경로면 `start_turn`(pending)
    + `BackgroundTasks(_run_chat_answer)` 후 `status='pending'` 즉시 반환. 비로그인은 prep 재사용
    동기 생성. 정책/범위 응답은 동기 영속화. GET `/threads/{id}`가 조회 시 `mark_seen`(뱃지 해제),
    신규 GET `/unseen`(전역 뱃지 카운트).
  - 프론트 `chat/page.tsx`: `status='pending'`이면 플레이스홀더 + 2초 간격 폴링(최대 ~4분, 토큰으로
    스레드 전환 시 무효화), 완료 시 서버 메시지 전체로 교체. 이어보기 스레드가 pending이면 폴링 재개.
    대화 목록에 미열람(인디고 점)·생성중(앰버 점) 표시 + '대화 목록' 버튼에 미열람 카운트 뱃지.
    `error` 상태는 빨간 말풍선.
- **검증**: 백엔드 전체 pytest pass(신규 `test_background_turn_pending_complete_seen` 포함)·ruff·
  mypy clean(touched). 프론트 tsc·vitest(23)·production build pass. 라이브 스모크: POST→
  `pending`(message_id) → 백그라운드 생성 → 폴링 3틱 후 `done`(1004자), 커넥션 독립 확인.

### 읽기 글자 크기 3단계 + 테마 뷰어 공통 적용 — 2026-06-16

설정의 'AI 채팅 글자 크기'(기본/크게 2단계)를 **읽기 글자 크기 3단계(기본/크게/더크게)**로 확장하고,
AI 채팅 상담뿐 아니라 **테마 사주 뷰어(ReportPager)에도 공통 적용**.

- `lib/storage.ts`: 채팅 전용 명칭을 읽기 공통으로 일반화 — `ReadingFontSize`(base/large/xlarge),
  `load/saveReadingFontSize`, `READING_FONT_CHANGE_EVENT`, 단계→클래스 매핑 `readingFontClasses()`
  (base=text-sm/prose-sm, large=text-base/prose-base, xlarge=text-lg/prose-lg). localStorage 키 값은
  유지(`ryubosal:chatFontSize`)해 기존 설정 보존.
- `lib/useReadingFontSize.ts`(신규): 설정 변경 구독 공용 훅(같은 탭 이벤트 + 다른 탭 storage). 채팅·뷰어 공유.
- `settings/page.tsx`: 3단계 버튼 + 안내문("채팅·테마 뷰어 공통").
- `chat/page.tsx`: 로컬 effect/state 제거 → 공용 훅. `ReportPager.tsx`: 본문 prose 크기 동적 적용.
- 검증: tsc·vitest(23)·production build pass. Tailwind content에 lib/** 포함 → 신규 클래스 생성 확인.

### 답변 취소선(자기수정 자취) 제거 — 정확한 내용만 전달 (2026-06-16)

모델이 간혹 취소선(GFM ~~…~~)으로 '틀린 표현을 그어 지운 자취'를 남겨 사용자에게 의문만 주는 문제.
마커만 떼면 틀린 내용이 평문으로 남으므로 구간을 통째로 제거 + 프롬프트로 자기수정 금지.

- `llm_client._sanitize_output`: generate_reading 반환 텍스트(메인·폴백 공통)에서 `~~…~~` 구간을
  통째 제거하고 제거 자리의 이중 공백·구두점 앞 공백·줄 끝 공백을 정돈. 단일 물결표(범위 '1~2개월')는
  보존(이중 물결표만 대상). 채팅·리포트 모든 표면이 거치는 단일 지점이라 일괄 적용.
- 시스템 프롬프트(_SYSTEM_PROMPT·_REPORT_SYSTEM_PROMPT) 규칙7에 "취소선·자기수정 표기 금지,
  고친 흔적 없이 최종 확정 내용만" 추가.
- `ReportPager`(테마 뷰어, 유일하게 GFM 렌더): remarkGfm `singleTilde:false`(범위 오인 방지) +
  `del`(취소선) 렌더를 null 처리(기존 저장 리포트 대비 belt-and-suspenders).
- 검증: 신규 `test_sanitize_*`·`test_primary_output_is_sanitized` 포함 백엔드 pytest pass·ruff·mypy
  clean, 프론트 tsc·build pass.

### 길흉=용신/기신 우선 + 한신 생(生) 간접 길흉 + LLM 해석 우선순위 (2026-06-16)

사용자 지적: "길흉 판단은 용신/기신 오행 우선, 사건 종류는 십성 우선"인데 실제 풀이가 그렇지 않음.
조사 결과 사건종류=십성(TenGodEventBrancher)은 적용돼 있으나, 길흉은 용신/기신이 후행 보정에 그치고
한신은 NEUTRAL로 무보정(생 관계 미반영)이었음. 세 가지를 사용자 확정 후 반영.

- **Part 1 — 한신 생(生) 간접 길흉**: PolarityRole에 HAN_GOOD/HAN_BAD 추가. event_engine_v2._period_role
  재구성 — 직접 역할(용·희·기·구, 천간>지지) 우선, 천간·지지 모두 직접 역할이 없을 때만 한신이
  생(_GENERATES)하는 대상의 역할로 약한 길/흉 판정(용신·희신→HAN_GOOD, 기신·구신→HAN_BAD).
  강도는 희신(1.04)보다 약한 1.015(약 1/2.6) — polarity_rules JSON. yongi_quality_engine은 한신 생일 때
  quality가 None일 때만 OPPORTUNITY/PRESSURE(약한 방향)만 부여하고 정해진 품질은 보존(간접·약신호).
- **Part 2 — LLM 해석 우선순위 지시**: 대화·리포트 시스템 프롬프트 규칙2에 "사건 도메인=십성,
  길흉=용신·기신(한신은 생 대상), 영역=궁위; 좋은 십성도 기신이면 부담, 불편한 십성도 용신이면
  성장 기회" 명시. 점수·판정 불변(서술 일관성만).
- **Part 3 — 길흉 우선순위 구조 강화**: 직접 용신·희신이 들어오면 기존 흉 품질(LOSS/CONFLICT/PRESSURE)을
  MIXED로 누그러뜨림(YONGGI_SOFTEN). DELAY(발현 타이밍)는 길흉이 아니므로 용신·기신 모두 불변.
- **검증**: 신규 test_period_role_hansin(11)·test_yongi_quality_engine 추가분 포함 전체 백엔드 pytest pass
  (회귀 픽스처 무파손), ruff·mypy clean, validate_dictionaries 53/53. event_graph 재빌드 불요(스코어링만).

### 월별 길흉을 운 품질(용신운 강도) 1차 기준으로 + 천간·지지 더블 용신 강화 (2026-06-16)

사용자 지적(실차트 1980-11-22 己土 신약, 용신 土): 천간·지지 모두 용신인 2026-10 戊戌이 가장 좋아야
하는데 답변이 그렇지 않음. 원인 — 운 품질 엔진(luck_cycles)은 이미 10월을 "강한 용신운" 0.9(연중
최고)로 판정하나, 월별 답변 표(build_monthly_overview)가 사건 점수로만 줄세우고(모든 달 100 포화)
운 품질 라벨을 LLM에 전달하지 않아, 비겁운(사건 적음)인 10월이 "특이 신호 없음"으로 묻힘.

- **Part 1-2 — 월별 운 품질 노출**: MonthOverviewRow.luck_grade 추가. build_monthly_overview가
  result.luck_cycles.monthly_luck/yearly_luck의 권위 라벨(luck_label: "강한 용신운" 등)을 달별로 매핑
  (추가 계산 없음). serialize_llm_input가 각 달 사건명 앞에 〈운 품질 등급〉으로 노출 +
  유력 달 종합 bits에도 "운 품질 …" 추가.
- **Part 3 — 디렉티브**: 월별 표 범례에 "좋은 달은 사건 밀도가 아니라 운 품질 등급(강한 용신운>
  용신운(부분)>혼합>기신운)으로 판단, 사건은 그 위에 십성. '강한 용신운' 달은 사건이 적어도 기반이
  가장 좋은 달로 짚을 것" 추가(has_grade일 때만).
- **Part 4 — 천간·지지 더블 신호**: PolarityRole YONG_STRONG/GI_STRONG 추가. _period_role이 천간·지지
  모두 용신이면 YONG_STRONG, 모두 기신·구신이면 GI_STRONG(단일/혼합은 기존 천간 우선). 배율 1.12
  (용신 1.075보다 강), yongi_quality_engine은 YONG_STRONG=길(흉 완화 포함)·GI_STRONG=흉 flip 처리.
- **검증**: 실차트 재실행 — 2026-10만 〈강한 용신운〉(유일), 전 달 사건점수 100 포화에도 운 품질로 변별.
  신규 테스트(period_role 더블 4 + yongi STRONG 3 + serialize 1) 포함 전체 pytest 743 pass, ruff·mypy
  clean(touched), validate_dictionaries 53/53. event_graph 재빌드 불요.

### 테마(리포트) 경로에도 월별 운 품질 등급 적용 (2026-06-16)

사용자 확인 질문: 앞선 변경이 테마 사주(리포트)에도 모두 적용되는가. 점검 결과:
- 스코어링(길흉=용신/기신·한신 생·더블 용신 YONG_STRONG/GI_STRONG): 리포트도 동일 EventEngineV2
  (report_service.scorer)를 써서 **이미 적용**.
- LLM 해석 우선순위·취소선 제거: _REPORT_SYSTEM_PROMPT·llm_client 공유라 **이미 적용**.
- **월별 운 품질 등급: 미적용이었음** — 리포트는 build_monthly_overview가 아니라
  report_event_input.month_overview_lines를 쓰기 때문. 이번에 동일하게 보강:
  - 각 달 라인에 〈운 품질 등급〉(p.luck_label) 노출(LuckPillar 직접 보유).
  - ★주목 선정에 '강한 용신운'/'강한 기신운' 달 포함(사건 점수 Top3 ∪ 강품질) — 사건 적은
    강한 용신운 달이 누락되지 않게.
  - report_service.month_overview_block 지시문을 "좋은 달/주의할 달의 1차 기준은 사건 밀도가
    아니라 운 품질 등급, 강한 용신운 달은 사건 적어도 기반이 가장 좋은 달"로 보강.
- **검증**: 실차트(己土 신약) 2026 리포트 월별 — 2026-10 戊戌이 〈강한 용신운〉 ★주목으로 노출,
  전 달 운 품질 등급 부착 확인. 신규 test_month_overview_surfaces_luck_grade 포함 전체 pytest 744
  pass, ruff·mypy clean(touched).

### 사건 방향성 표시 1차 — quality(길흉) 보존 + timing(지연) 분리 + 사용자 방향 라벨 (2026-06-16)

사용자 지적: "재물 변화 100점 · 조건부"만 보여선 좋아지는지 나빠지는지 알 수 없어 혼란(다른 사건도 동일).
근원: 엔진은 풍부한 quality로 길흉을 판정하나, 출력 직전 polarity 4값(긍정/부정/조건부/중립)으로
뭉개지며 특히 'delay(공망 지연)'와 'mixed'가 모두 "조건부"로 합쳐져 방향이 사라짐. 사용자 리뷰 반영
(작업명: EventCandidate quality 보존 및 방향 라벨 개선 — 점수 산식·사건명 불변).

- **타이밍을 방향과 분리(리뷰 핵심)**: EventTiming(active/delay) 신설, EventCandidateV2.timing 추가.
  addendum_gate_modifier의 공망·게이트 보류를 `quality=DELAY` → `timing=DELAY`로 변경 → 공망이어도
  yongi가 방향(용신/기신)을 quality에 남긴다. EventQuality.DELAY는 미생산(deprecated).
  · 효과: 2026-10 wealth_change = quality=opportunity + timing=delay → "기회·유입 · 지연·보류"
    (이전엔 quality=delay로 방향 소실 → "조건부"). 12월 = quality=loss → "손실·지출".
- **방향 라벨 노출**: QUALITY_KO 문구 정비(기회·유입/성취·결실/손실·지출/압박·부담/갈등·마찰/해소·정리/
  혼합), TIMING_KO 신설, `direction_label(quality, timing)` 헬퍼. legacy EventCandidate에 quality·timing
  실어 전달. 채팅(context_reducer: LlmEventCandidate.direction·월별 row.direction·유력달 bits)과
  리포트(report_event_input: 월별·정밀클러스터·점수표) 모두 모호한 polarity 대신 방향 라벨 표시.
- **범위 밖(2차 별도)**: reason_code 계열화·점수 포화(매달 100점) 제어 — 미착수.
- **검증**: 신규 test_direction_label + 게이트 timing 테스트 갱신 포함 전체 pytest 745 pass, ruff·mypy
  clean(touched). 실차트 채팅·리포트 양쪽에서 10월 "기회·유입 · 지연·보류"·12월 "손실·지출" 확인.

### 점수 포화 제어 2차-1단계 — soft_cap + 단계 클램프 제거 + 기여 계측 (2026-06-16)

사용자 리뷰(C안): B(소프트캡)를 먼저 하되 A(계열 인지 감쇠) 전환용 계측을 1차에 포함.
원인: base(MAX≈64)에 12운성(±18)+관계(+22) 등 모디파이어가 누적되며 단계마다 100 하드 클램프 →
서로 다른 달·사건이 모두 100에 붙어 변별 소실. (식상생재가 base+wealth_act, 재성국이 relation+
wealth_act 양쪽에 잡히는 계열 중복도 확인.)

- **단계별 하드 클램프(min(100)) 제거**: ten_god_brancher·twelve_stage·layer_flow·addendum_gate·
  relation_palace·yongi_quality·wealth_activation·event_ranker — 누적 raw를 끝까지 보존(max(0)만 유지).
  EventCandidateV2.score 필드의 le=100 제약 해제(내부 표시값).
- **최종 soft_cap만 적용**: event_engine_v2._score_target가 랭커 뒤에서 `soft_cap(raw, knee=85, tau=25)`
  = 100 - 15·exp(-(raw-85)/25). raw 85→85·100→91.8·120→96.3·150→98.9. 단조 증가라 순위 보존.
  raw_score에 cap 전 누적 보존.
- **단계별 기여 로그(계측)**: EventCandidateV2.contributions{base/stage/flow/gate/relation/yongi/
  wealth_act/rank} — 각 모디파이어가 적용한 delta. 2차 계열 인지 감쇠·fingerprint 중복 제거의 근거.
- **효과(실차트)**: 2026 월별 재물/계약 후보가 전부 100 → 94~98로 분산(raw 106~141 보존). 12월
  contributions가 relation +12 + wealth_act +21(재성 계열 중복)을 그대로 노출 → 2차 타깃 확인.
- **검증**: 신규 test_score_saturation(soft_cap 곡선·포화 분산·기여 합≈raw) 포함 전체 pytest 747 pass,
  ruff·mypy clean(touched). 기존 픽스처 무파손.
- **2차-2단계(후속 PR)**: family/fingerprint 정규화 → 같은 현상(식상생재=COMBO+WEALTHACT, 재성국=
  REL+WEALTHACT) 중복 가산 1회화, 같은 계열 추가 감쇠·다른 계열 강화. 미착수.

### 점수 포화 제어 2차-2단계 — 계열 인지 감쇠(중복 가산 제거) (2026-06-16)

1차(soft_cap+계측)로 드러난 같은-계열 중복 가산 2곳을 제거. 사용자 설계(대표 강·추가 감쇠·교차
중복 1회화)를 검증된 지점에 적용. 채팅·테마 공통(동일 EventEngineV2).

- **wealth_activation 계열 감쇠**: 재성국·충개고·식상생재는 한 '재성 작동' 계열인데 boost가 단순
  sum이라 중복 누적 → `_family_boost`로 가중 큰 순 대표(1.0)·2번째(0.45)·3번째(0.25)… 감쇠 합.
  교차 중복(식상생재가 base COMBO_OUTPUT_WEALTH/SPEC_*에 이미 잡힘)은 ×0.35로 추가 최소화.
  후보별 reason_codes 기준이라 base 유무에 따라 달라짐. WEALTHACT_FAMILY_DIMINISH 표식.
- **layer_flow 반복 계열 감쇠**: REPEAT_SAME_TEN_GOD(+8) + REPEAT_SAME_GROUP(+6)이 같은 '반복'
  계열인데(같은 십성이면 같은 그룹이라 항상 중복) 둘 다 가산 → 십성 반복이 잡히면 그룹 반복은
  +2로 감쇠(REPEAT_SAME_GROUP_DIMINISH). 그룹만 반복이면 온전히 +6.
- **효과(실차트)**: 2026-12 재물 wealth_act +21→+15(식상생재 교차중복 감쇠), raw 135→129. 8월은
  과대평가됐던 wealth_change가 줄며 실제 더 타당한 creative_output(상관) 표면화(디바이어싱).
- **검증**: 신규 test_family_diminishing(대표·추가감쇠·교차중복·순서무관·그릇배율) 포함 전체 pytest
  752 pass, ruff·mypy clean(touched), 기존 픽스처 무파손. 채팅·리포트 라이브 반영 확인.
- **남은 확장(선택)**: 다른 도메인은 현재 단계별 단일 신호(다른 계열)라 가산이 타당해 추가 감쇠
  불요. 새 계열 중복이 발견되면 같은 패턴(fingerprint 맵 + 감쇠)으로 확장.

### 기반 최고 달(강한 용신운) 누락 수정 — 이름 박은 고-가시성 지목 (2026-06-16)

사용자 지적: 엔진이 10월을 연중 최고 운(강한 용신운)으로 판정해 놓고도, 이직/이사 등 intent
질문 답변에 10월이 전혀 언급 안 됨. 진단(dry-run): 10월 〈강한 용신운〉과 "강한 용신운 달 짚을 것"
지시가 입력에 모두 있으나, 10월의 그 달 top 사건이 '재물 변화'(career 아님)라 LLM이 career 사건
있는 달(6·7·8·12)에 집중하고 10월을 건너뜀(지시가 월별 표 범례에 묻힘 + Gemini flash thinking LOW).

- **수정**: 월별 블록 헤더 직후에 운 품질 최고 달을 **이름 박아** 별도 지목 —
  "※ [기반 최고 달] 2026-10(강한 용신운) — 질문 사건이 약하거나 없더라도 '기반이 가장 좋은
  시기'로 반드시 한 번 짚을 것." context_reducer._best_quality_months(강한 용신운 우선, 없으면
  용신운(부분); 흉·혼합 제외, 최대 3개). 채팅(serialize_llm_input)·리포트(report_service.
  month_overview_block, LuckPillar.luck_label 기준) 양쪽.
- **검증**: 신규 test_best_quality_months·콜아웃 직렬화 테스트 포함 전체 pytest 754 pass, ruff·mypy
  clean(touched). **라이브 Gemini**: 이직 질문 답변에 "2026년 10월(戊戌)은 가장 유리한 강한 용신운의
  달" 명시 확인(이전엔 누락).

### 生剋제화 化(합화) 우선 — 길흉 계층 반영(사건 라벨 불간섭) (2026-06-16)

사용자 지적(체용+생극제화): 사건 추론이 십성-first라 化(합화)가 십성 분기 이전에 반영 안 됨.
1차 시도(化神 십성을 brancher=사건 라벨 생성기에 주입)는 대운 천간 합화로 전 기간 사건이 통째
재분류돼 데모 차트 146건 과발동 → 사용자 진단대로 "대운 합화를 사건 라벨 생성기에 넣은" 오류.

- **수정(Option D)**: 化神 십성의 brancher 주입을 철회(HWA_TRANSFORM 0). 대신 합화를 **길흉(용기신)
  계층에만** 반영 — `_target_hwa_element`가 그 시점 '본 천간'(세운·월운 target)이 confirmed 합화면
  化神 오행 반환, `_period_role(stem_element=…)`이 그 오행으로 용기신 역할(길흉)을 본다. 사건 종류·
  개수는 불변(세운·월운 십성이 결정). 化神 음양은 합 상대(운 천간) 승계, 일간 자합(본신지합)은 제외.
- **범위**: 본 천간(국소)만. 대운 배경 천간의 합화는 per-월 길흉 블랭킷을 피해 제외 — 대운 합화의
  체용/용신 반영은 별도 후속(체용 계층).
- **효과(실차트)**: 데모 2026-04(壬辰, 壬丁합화木)만 HWA_길흉 10건, 사건 타입 불변. 사건 폭증 없음.
- **검증**: 신규 test_hwa_element_override 포함 전체 pytest 755 pass, ruff·mypy clean(touched).
- **남은 후속**: (a) 대운 합화의 체용/용신 반영, (b) 制/합거(탐합망극) 흉 무력화, (c) 체용 적합도
  점수 초반 가중 — 슬라이스 2·3.

### 化 우선 문구 보정 + 슬라이스 2(대운 합화 체용 배경 보정) (2026-06-16)

사용자 보정 2건 반영:
1. **문구**: "사건 종류=세운·월운 십성"은 단정적 → **"사건 라벨은 본 운의 원래 십성·궁위·관계작용
   (합충형파해)이 결정하고, 합화는 그 사건의 길흉·강약·성패에만 반영"**으로 정정(메모리·코드 주석).
2. **대운 합화 배경**: per-월 직접 치환은 안 하되, 대운 기간 전체의 체용·용신 적합도·성패율에
   배경값으로 반영(10년 배경 체질 변화) — 완전 제외는 과함.

- **슬라이스 2 구현**: `_daewoon_hwa_role`(현재 대운 천간 confirmed 합화 시 化神 용기신 역할) +
  `_apply_daewoon_hwa_background`(보강 대운: 길 사건↑·흉 완화 / 압력 대운: 흉↑·길↓, 폭 ±0.03 잠정).
  사건 종류·개수 불변 — 같은 대운 내 길/흉 상대 성패만 미세 조정. wealth_act 뒤·랭커 앞 적용.
- **효과(실차트)**: 데모 대운 化木(기신=압력) → 흉 사건(loss/pressure) 성패율 약하게 강화 171건.
- **검증**: 신규 test_daewoon_hwa_background(보강/압력/중립/무방향) 포함 전체 pytest 759 pass,
  ruff·mypy clean(touched). 보정폭 0.03은 잠정(Phase 4 캘리브레이션).
- **남은 슬라이스 3**: 制/합거(탐합망극) 흉 무력화, 체용 적합도 점수 초반 가중.

### 슬라이스 3a — 制/합거(탐합망극) 흉 무력화 (2026-06-16)

生剋制化의 制: 기신이 합으로 묶이면 극(흉) 작용을 못 한다(탐합망극). 본 천간이 기·구신인데
합거(direction 'away', affected effect 'boon')되면 그 천간의 흉 역할을 길흉 판정에서 건너뛴다.

- `_target_stem_bound`(본 천간 기·구신 + 합거 'away' + boon) + `_period_role(stem_bound=…)`이 묶인
  천간을 빈 라벨로 처리 → 지지·한신생으로 길흉 판단. 사건 종류·개수 불변. 化 > 制 우선(합화면 制
  미적용). 합반(부분)은 제외(보수적, 합거 'away'만).
- **효과(실차트)**: 데모 2026-07(乙未) 기신 천간 乙이 원국 庚과 합거 → 흉 무력화, 지지 未(용신)이
  살아 opportunity로(25건). 여러 차트에서 23~71건 발동.
- **검증**: 신규 test_stem_bound_neutralizes_gisin 포함 전체 pytest 760 pass, ruff·mypy clean(touched).

### 슬라이스 3b(체용 적합도 점수 가중) — 의도적 스킵 (2026-06-16)

사용자 판단(동의): 체용 적합도는 이미 5계층에 반영됨 — ①원국 체용→용신 확정, ②_period_role
길흉 판정, ③YongiQualityEngine 배율(1.04~1.12), ④대운 합화 배경(±0.03), ⑤life_fit 정렬축.
여기에 새 점수 가중을 더하면 "하나의 현상을 4~5번 재채점"(식상생재 중복·재성국 중복·12운성+관계
중복과 동일 패턴) → 포화·100점 남발 재발. 체용→용신→체용 순환 참조이기도 함.

- **결정**: 3b(신규 점수 가중) 추가 안 함. 슬라이스 3은 3a(制/합거 무력화)로 마무리.
- **후속(캘리브레이션 대기)**: YongiQualityEngine 배율 구간(현 1.04~1.12)을 실제 검증 데이터 확보 후
  소폭 조정(예: 1.03~1.15). 지금은 데이터 없이 손대지 않는다(잠정값 변경 금지).
- 원칙: **체용 반영 부족이 아니라 중복 반영이 위험** — 새 항목 추가보다 중복 제거가 우선.

생극제화/체용 반영 작업(化 길흉 / 대운 배경 / 制 무력화) 완료. 체용은 더 넣지 않는다.

### 확정 용신 동기화 버그 수정 — 검증 확정이 DB·사주목록에 반영 (2026-06-16)

증상: 만세력 페이지에서 용신을 등록(검증 확정)해도 ①만세력 페이지에서 미입력으로 노출(교차기기),
②사주목록 수정·카드에서 미등록으로 노출. 근본 원인: 확정 용신이 두 저장소로 갈라져 desync —
만세력 검증 확정은 localStorage(calibration)만 저장하고 DB(confirmed_yongsin, 사주목록·수정 폼·
백엔드가 읽는 값)엔 절대 쓰지 않았다. 게다가 user_profiles.confirmed_yongsin은 basic/persona
NOT NULL이라 프로필 행 없이는 저장 불가.

- **DB 분리**: migration 012 `subject_yongsin`(subject_id PK) 전용 테이블 + 기존 user_profiles.
  confirmed_yongsin 이관(컬럼 있을 때만). ProfileStore.get/set_yongsin을 이 테이블 UPSERT로 변경 —
  프로필 행 유무와 무관하게 동작(호출부는 메서드만 쓰므로 불변). migrate에 012 추가.
- **신규 엔드포인트** `PUT /api/v2/profile/{id}/yongsin` — 확정 용신만 저장(소유 검증). basic 불요.
- **프론트**: lib.setSubjectYongsin. 만세력 페이지 onCalibrationResult가 검증 확정 용신을 DB에 영속
  + 로드 시 getProfile로 DB 확정값을 불러와 YongsinPanel에 반영(교차기기·Wizard 등록 복원,
  '등록된 용신 반영됨' 배지). 표시 우선순위: 이 기기 검증 > DB 등록 > 계산 후보.
- **검증**: 신규 통합 테스트(프로필 행 없이 등록·해제·타계정 404) 포함 전체 pytest 760 pass,
  ruff·mypy clean. 프론트 tsc·vitest(23)·build pass. 실DB 스모크(행 없이 set/get) 확인.

### 수정 화면 용신 등록 상태 미표시 + 편집 시 등록 소실 버그 (2026-06-16)

사주 수정(Wizard edit)의 용신 단계가 이미 등록된 용신을 "후보(검증 필요)"로 표시하는 문제 +
잠복 데이터 손실: StepYongsin 마운트가 항상 onYongsin(lead, false)로 yongsinConfirmed를 false로
리셋 → 편집 후 저장 시 confirmed_yongsin이 null로 지워짐.

- Wizard가 StepYongsin에 draft.yongsin/yongsinConfirmed(initialYongsin/initialConfirmed) 전달.
- StepYongsin: initialConfirmed면 마운트에서 onYongsin(false) 호출 안 함(등록 상태 보존) +
  YongsinPanel에 confirmedYongsin 전달.
- YongsinPanel: 등록된 경우 상태를 '확정(등록됨)'으로 + '등록된 용신 반영됨' 배지.
- 검증: 프론트 tsc·vitest(23)·build pass. (확정 용신 동기화 후속 — 21ef333과 연결.)

### 등록 후 검증 질문 노출 → '등록 완료' 표시 (2026-06-16)

등록(DB 확정)했는데도 용신 검증 질문이 계속 노출되는 문제. CalibrationPanel은 submitted(이 기기
검증 기록)일 때만 질문을 접었는데, DB로 등록한 경우 calibration=null이라 질문이 그대로 보였다.

- CalibrationPanel에 registered prop + 내부 reverify 상태 추가 — registered && !reverify면 질문 대신
  '용신 등록 완료'(+ '다시 검증' 버튼). 만세력 페이지(confirmedYongsin)·StepYongsin(initialConfirmed)
  양쪽에서 전달.
- 검증: 프론트 tsc·vitest(23)·build pass.

### AI채팅상담 페이지 리디자인 (2026-06-16)

목업 반영(프론트 전용):
- 상단 정보줄(생년월일시 기준·자동저장 안내) 제거 + 툴바 4버튼 제거 → 헤더 슬림화(제목만).
- 하단 입력바 재설계: 좌측 '+' → 레이어 팝업[새 대화·사주 변경·동반자 추가·대화 목록(미열람 뱃지/99+)],
  입력창 글자수 카운터(N/120, 사용자 확정), 보내기 ↑ 아이콘. '+'에도 미열람 점.
- '+' 팝업 항목은 기존 패널(showSwitch/showPartner/showHistory) 재사용 — closeMenuAndOpen이 대상만
  열고 상단으로 스크롤(패널이 헤더에 위치).
- '궁합 상대' → '동반자 추가'로 명칭·문구 변경(궁합 확정 아님, 질문에 따라 관계·궁합 등 유연).
- 전역 GNB '○○ 기준' 칩 클릭 → 툴팁으로 선택 사주 생년월일·출생시각·출생지 표시(getSubject 조회).
- 검증: tsc·vitest(23)·build pass.

### AI채팅상담 리디자인 v2 — 헤더 카드 제거·레이어 모달·메신저 입력 (2026-06-16)

1차 리디자인 피드백 반영:
- 상단 헤더 카드(제목·인라인 패널·제안 칩) **전부 제거**. 페이지 타이틀은 GNB의 '류보살 v2' 자리에
  표시(pathname→nav 라벨 매핑).
- '+' 서브메뉴(사주 변경·동반자 추가·대화 목록)를 인라인 패널이 아니라 **레이어 팝업 모달**(Modal,
  모바일 바텀시트)로. 새 대화는 즉시 실행.
- 입력바를 **메신저 스타일 박스**로: 테두리 둥근 박스 + 'M메시지…' textarea(Enter 전송/Shift+Enter
  줄바꿈, 자동 줄) + 하단 액션행('+'·글자수 N/120·원형 보내기 ↑). 동반자 첨부 칩은 입력 위로.
- 동반자 선택 표시 항목을 **관계(relation_to_user) 기반**으로(기능설명 '이미 등록된 사람'에 맞춤).
- 검증: tsc·vitest(23)·build pass.

### AI채팅상담 리디자인 후속 — 동반자 문구·등록 안내·전역 페이지 타이틀 (2026-06-16)

- 동반자 모달 문구: "함께 볼 동반자(해제 전까지)를 고르거나 즉석 입력(1회용)하세요. 질문에 따라
  관계·궁합 등으로 함께 풀이됩니다."로 변경.
- 등록된 동반자(현재 대상 제외)가 없으면 '동반자 등록하러 가기' 버튼 → /sajus 이동(즉석입력은 유지).
- GNB 페이지 타이틀: 메인('/') 외 모든 페이지에서 '류보살 v2'를 페이지 타이틀로 대체(PAGE_TITLES
  전역 맵 — 만세력·간지달력·테마사주·AI채팅상담·사주목록·사주 등록·설정·내 풀이·용신 검증·관리자).
- 검증: tsc·vitest(23)·build pass.

### AI채팅상담 — 막연한 시점은 10년 연(세운) digest + 대운 교운기 + 연도 지정 유도 (2026-06-18)

데굴님 지적: 특정 연·월 미지정 질문('결혼…때를 알고 싶어')에서 현재 연도 12개월로 좁혀 특정 달을
단정하던 결함. "막연한 기간은 년운 중심으로 보고, 이후 사용자가 특정 연도를 지정해 상세를 보도록
유도"가 원칙.

- 판별 `vague_future` = period_fortune 없음 + 구조질문 아님 + 과거회고 아님 +
  `intent.time_range` 없음(또는 start 없음). 올해/내년/특정연·월/향후 N년(start 있음)은 제외.
- 동작: 올해부터 10년(올해…+9) 연(세운) digest를 제공. 기본 yearly_luck 창(올해±5) 밖 연도
  (올해+6~+9)는 `luck_years`(신규 `yearly_luck_for_range`)로 온디맨드 보강 후 YEAR 재스코어.
  월별 12개월 표·핵심달 지시 비활성, 후보는 세운(연) 중심으로 10년 범위.
- 대운 교운기: 10년 안에 대운이 바뀌면(`_daewoon_span_context`) 현재+다음 대운 구간과 교운 연도를
  배경으로 실어 전환 에너지를 반영(교운 가중은 이미 event_scoring에 반영 — 텍스트는 배경용).
- 응답 지시문 `_YEAR_DIGEST_DIRECTIVE`: 연 단위 큰 줄기·교운기 반영·특정 달 단정 금지·답변 끝에
  '어느 해를 자세히 볼지' 유도.
- 검증: 실 사주(1980-11-22) 라이브 — 2027/2033~2034 핵심·2035 교운기 반영·"어느 해를 더 자세히
  보고 싶으신가요?"로 마감. ruff·mypy clean, 회귀 테스트 추가(test_conversation_date_fixes.py),
  전체 스위트 통과(DB 미설정 통합 3건 제외).

### 결혼·궁합 보강 — 일지 3분류 배우자궁 기질·십성 보완 끌림·복음 결혼 트리거 (2026-06-22)

데굴님 요청: 결혼·연애·궁합 영상 스크립트의 명리 요소가 미반영됐는지 점검·반영. 조사 결과
끌림/안정 이중채널·용신 보완·12운성 관대건록·재성(남)/관성(여) 십성·일지 육합(RELATION_HAP_DAY)은
이미 반영, 아래 3가지가 미반영이라 사용자 승인 후 정석 구현(규칙 5·6·10 준수). 전부 비단정·경향
서술(규칙 3·8). chat(AI채팅상담)·report(테마사주) **공용 직렬화/엔진**을 거치므로 양쪽 자동 반영.

- **Task 1 — 일지 3분류 배우자궁 기질**(원국, 순수 엔진): 일지를 왕지(子午卯酉·도화)/생지
  (寅申巳亥·역마)/고지(辰戌丑未·화개)로 분류해 관계 기질 경향을 중립 라벨로 표면화.
  `MarriageResourceProfile`에 `day_branch_group`·`day_branch_tendency` 추가, `marriage_resource.py`
  `_day_branch_temperament()`, `structural_context.marriage_resource_lines`에 "배우자궁(일지) 기질"
  줄 추가. chat `_structural_context`(RELATIONSHIP/총운)·report `marriage_resource_block` 노출 검증.
- **Task 2 — 복음(伏吟) 결혼 보조 트리거**(이벤트 엔진+사전, 정석): 운 지지=원국 일지(배우자궁)
  복음을 결혼 트리거로 추가. `RelationKind.BOKEUM` enum, `relation_palace_modifier.json`에
  `BOKEUM` relation_type(bonus 5, 보조)·`RELATION_BOKEUM_DAY`(→marriage_signal·relationship_change)
  규칙, `event_engine_v2._bokeum_activations()`로 일지 복음 발동 합성(단독 생성 아님·기존 후보만
  강화). 라이브 검증: 1985-03-15(일지 丑) → 2021·2009(丑년) marriage_signal에 `REL_BOKEUM_day_pillar`
  가점(91/93), 비복음년 미발동. 골든/회귀 스냅샷 영향 없음.
- **Task 3 — 십성 보완 끌림**(궁합, 순수 엔진): force_analysis 십성군 분포에서 한쪽이 약/부재(<10%)인
  군을 상대가 뚜렷이 보유(>=20%)하면 보완 끌림 신호(격차 최대 1건/방향). 식재(식상·재성) 부재
  보완은 여성 taker=결혼·생활 기반 보탬 뉘앙스. `CompatSignalKind.TEN_GOD_COMPLEMENT` enum,
  `compatibility_engine._ten_god_complement_signals()`, 끌림 가중 1(잔잔한 보완형). chat
  `_compat_prompt_block`·report `compatibility_block` 노출 검증.
- 검증: ruff·mypy clean, 단위 테스트 추가(test_marriage_resource·test_compatibility_engine·
  test_relation_palace_engine), 전체 스위트 통과(기존 DB/환경 의존 통합 2건 제외 — stash 확인상
  본 변경과 무관). 사전 검증 `validate_dictionaries.py` 통과.

### 결혼 보강 후속 — 비식재(比食財) 흐름 결혼 타겟팅 (2026-06-22)

위 Task 2의 확장. 정통 배우자성 경로(여=관성합·남=재성합)가 약/부재인 사주가 **비겁→식상→재성**
생성 흐름으로 결혼하는 메커니즘(영상 자료) 반영. 원국 비식재 구조 × 운의 식재/재생관 보강을 결합한
**원국×운 모델**로, 횡재 발동(WealthActivationModifier)과 동일한 순수 엔진·잠정 가중·reviewed:false
패턴. **증폭만**(기존 marriage_signal·relationship_change 후보 가산, 후보 신규 생성 안 함 — 2026-06-22
사용자 확정). EventEngineV2 공용이라 chat(AI채팅상담)·report(테마사주) 자동 반영.

- 신규 `marriage_flow_modifier.py`: `analyze_marriage_flow_natal()`(원국 그릇 band — strong=비식재
  라인+배우자성 약 / moderate=라인만 / none), `detect_marriage_flow_activations()`(시점 십성군→발동:
  식상 보강 0.08·재성 보강 0.12·완성 0.16, 성별 인지 — 여=재생관 완성 / 남=식상생재 완성),
  `MarriageFlowModifier.apply()`(band 배율 1.0/0.5/0 × 계열 감쇠 1.0/0.45/0.25 → (1+boost)배).
- `event_engine_v2`: `marriage_flow`를 capacity처럼 1회 계산해 `_score_target`에 스레딩, `_wealth_act`
  다음에 `present_gods`→그룹 환원 후 `_marriage_flow.apply` 적용.
- 라이브 검증: 1990-05-05 남(band strong) → 2027 marriage_signal·relationship_change에
  `MARRIAGEFLOW_재성 보강`, 2032 `식상생재 완성`; 1988-09-09 여(strong) → `재생관 완성` 가점.
  band=none 명식은 무가산.
- 검증: ruff·mypy clean, 단위 테스트 `test_marriage_flow_modifier.py`(7건), 전체 스위트 통과
  (기존 환경 의존 통합 2건 제외 — 본 변경과 무관). 골든/회귀 스냅샷 영향 없음.

### 배우자성 성별 오역 교정 — 남=재성·여=관성 (2026-06-22)

데굴님 지적: 남성 사주인데 "정관=여성에게는 배우자" 식 **여성 기준 풀이**가 나옴. 원인 =
`marriage_resource_lines` 헤더가 성별 무관하게 `관성=배우자, 재성=시댁`(여성 고정)으로 하드코딩돼
남성 명식에 자기모순 입력이 들어가 LLM이 여성 프레이밍을 따름. + 프롬프트에 배우자성 가드 부재.
+ 엔진이 정관→marriage_signal을 성별 무관하게 생성(남성도 정관 해에 결혼신호 정점).

- **① 헤더 성별 인지**(`structural_context._SPOUSE_FRAME_KO`): 여=관성=배우자(남편)·재성=시댁 /
  남=재성=배우자(처)·관성=직위·자식(배우자 아님) / 미상=성별 기준 안내.
- **② 배우자성 가드 디렉티브**(`structural_context.spouse_star_directive`, chat·report 공용):
  결혼·관계 질문(Domain.RELATIONSHIP 또는 결혼 키워드)·테마사주 결혼 섹션에 성별 명시 + 반대 성별
  기준 해석 금지. chat_service trailing·report_service _MARRIAGE_RESOURCE_SECTIONS에 주입.
- **③ 엔진 배우자성 성별 가중**(`marriage_flow_modifier.apply_marriage_gender_weight`, 브랜칭 직후):
  구동 십성(reason_code SINGLE_/SPEC_/TRI_)으로 남성 정관 단독=×0.6·여성 재성 단독=×0.7 약화,
  재관 동반(재생관 등)은 불변. 잠정·reviewed:false. 결과 — 남성은 정재(재성=처) 연도가 상위로,
  여성은 정관·재관인이 상위로 정렬(라이브 1980-11-22 확인). 골든/회귀 영향 없음.
- 검증: ruff·mypy clean, 단위 테스트 추가(gender weight 4건·헤더/가드 2건), 전체 스위트 통과
  (기존 환경 의존 통합 2건 제외). EventEngineV2·공용 직렬화라 chat·report 양쪽 자동 반영.

### 결혼 후속 — GENERAL 관계질문 가드 누락·만남시기 택일오해 교정 (2026-06-22)

데굴님 지적(연속): 남성에게 ①6월 정관을 '결혼 만남'으로 풀고 ②막연한 '언제 만나' 질문에 2월을
선택지처럼 콕 집어 잘못 안내. 원인 = '그럼 그 연인은 언제쯤 만나?'가 `domain=GENERAL`로 파싱돼
(ⓐ)배우자성 가드 트리거(RELATIONSHIP/결혼키워드)를 빗나가 누락, (ⓑ)직전 '2년 안에 결혼?'
(relationship·2026-06~2028-05·월)의 시점 범위를 상속해 월 후보가 유입→LLM이 기신 달(2월)을
선택지로 나열.

- **Fix A**: 배우자성 가드를 `_structural_context`의 결혼 블록 바로 뒤로 이동 — 트리거를
  도메인/키워드가 아니라 '결혼 블록 표면화 시(general 포함)'로 바꿔 GENERAL 관계질문에도 항상 동반.
  chat trailing 중복 제거(report는 기존대로 결혼 섹션에 동반).
- **Fix B**: `_MEETING_TIMING_DIRECTIVE`(+`_is_relationship_context`/`_RELATIONSHIP_KEYS`) 신설 —
  관계 맥락(도메인 또는 연애·연인·인연·배우자·결혼·솔로 등 키워드)에서 "만남은 택일이 아니다:
  약한/기신 달을 선택지로 끌어와 무르지 말고 가장 유리한 시기 하나(연·반기·계절)로, 만날 장소·경로는
  사주로 단정 불가(출장지·교육현장 창작 금지)"를 주입.
- 검증: ruff·mypy clean, 단위 테스트 6건(test_relationship_decision_directives.py 보강), 전체
  스위트 통과(기존 환경 의존 통합 2건 제외). 런타임 — GENERAL 관계질문에 가드 포함·만남 디렉티브 동반 확인.

### 결혼·연애 보강 2차 — 일지 십성 이상형·배우자복 3조건·자기인식 (2026-06-22)

데굴님 제공 영상 2건(① 십성별 운명의 짝 ② 배우자복 결정 3요소) 기반 추가 보완. 전부 원국·결정론·
비단정, `marriage_resource` + 공용 직렬화라 chat·report 자동 반영. (B 생애단계·D 운 일시취향은 후순위.)

- **A 일지 십성 이상형**: 일지 본기 십성 → 끌리는 타입(비겁=대등/식상=표현·꾸밈/재성=현실 매력·외모/
  관성=조건·태도/인성=보살핌). `_ideal_type`·`day_branch_ten_god_group`·`ideal_type_tendency`.
  기존 일지 글자그룹(도화/역마/화개 기질)과 상호보완(HOW vs WHAT). 검증: 己亥(일지 정재)→'외모 중시'.
- **C 자기인식 어드바이스**: `RELATIONSHIP_SELF_AWARENESS_DIRECTIVE`(공용) — '사주에 드러난 취향을
  본인이 인정 않으면 연애가 어긋난다, 실제 끌리는 타입 받아들이도록' 안내. 관계 맥락 chat·report 주입.
- **E 배우자별 하나·튼튼**(`spouse_star_clean`·`spouse_star_rooted`): 정확히 1개 드러남(깔끔) + 지지
  본기 뿌리(튼튼=현실적 도움 경향).
- **F 배우자궁(일지) 안정도**(`spouse_palace_stable`·`spouse_palace_afflictions`): 일지 충/형/원진/파/해
  관여 여부 → 관계 내구성. 손상 시 '개운·궁합·노력으로 보완 가능(이혼 단정 아님, 남 탓보다 본인 대응)'
  가드 동반.
- **G 배우자성=용신 덕**(`spouse_is_yongsin`): 배우자성 오행(남=재성·여=관성)이 용·희신이면 '배우자가
  부족한 기운 채워주는 에어컨/보일러 — 결혼하며 더 풀리는 배우자 덕'. `analyze_marriage_resource(result,
  useful)` 인자 추가(chat=build_birth_summary·report=summary.useful_gods 전달, 미입력 graceful).
- 검증: ruff·mypy clean, 단위 테스트 보강(test_marriage_resource.py — A/E/F/G 8건), 전체 스위트 통과
  (기존 환경 의존 통합 2건 제외). 런타임 — GENERAL 관계질문에 이상형·배우자복 품질·자기인식·성별 가드 4축 동반 확인.

### 결혼·연애 보강 3차 — 생애단계 연애대상(B)·운 일시 취향변동(D) (2026-06-22)

영상1 후순위 2종 마저 반영. 원국·결정론(B)·디렉티브(D), chat·report 공용 자동 반영.

- **B 생애 단계별 연애 대상**(`life_stage_ideals`, `_life_stage_ideals`/`_TYPE_SHORT`): 연지=어릴 때
  또래·유행 / 월지=사회·원숙기 결혼상대 / 시지=말년(약) — 각 지지 본기 십성 → 짧은 타입어. 직렬화에
  "생애 단계 연애 대상(…경향·시기 단정 아님)" 줄 추가. 검증 1980-11-22 男: 어릴때 표현·꾸밈형/원숙기
  현실 매력형/말년 대등·독립형.
- **D 운 일시 취향 변동**(`TENDENCY_SHIFT_DIRECTIVE`, 공용): 운에서 평소 일지 취향과 다른 십성(특히
  인성·식상)이 강하면 일시적으로 다른 타입에 끌리고 운 빠지면 흔들림 — '운에 취해' 급히 정하지 말라는
  주의(불안 조장·단정 금지). chat `_structural_context`·report 결혼 섹션 주입.
- 검증: ruff·mypy clean, 단위 테스트 보강(B 2건), 전체 스위트 통과(기존 환경 의존 통합 2건 제외).
  런타임 — chat·report 양쪽에 B 직렬화·D 디렉티브 동반 확인(데굴님 요구 — 양쪽 반영 검증 완료).

### 관계 후속 토픽 연속 — '주변 vs 새 인연' too_broad 바운스 차단 (2026-06-22)

데굴님 지적: 관계 풀이 직후 '주변에 있는 사람이야 아니면 완전히 새로운 사람이야?'가 시점(6개월/올해)
좁히기로 바운스됨. 원인 = 지시어·도메인 키워드가 없어 `link_question`이 NEW로 떨어짐 → 관계 도메인
상속 실패 → GENERAL+무시점 → `assess` too_broad. 데굴님 방향대로 **기존 intent 분류 재사용**으로 해결.

- **Fix 1 토픽 연속 팔로업**(`conversation.link_question`): 활성 스레드(직전 분야 확정)에서 새 도메인을
  안 들고 온(`_detect_domains==[]`) 충분히 구체적인(compact≥12) 후속은 직전 분야를 잇는 DRILL_DOWN
  으로 본다. 가드 — 짧은 반응어('그래?')·새 풀이/리셋 요청(`_READING_REQUEST_RE`·`_FRESH_OVERVIEW_RE`:
  '네 사주 봐줘'/'총운 처음부터')은 제외. 결과 — 도메인 상속(relationship)으로 has_domain=True +
  is_followup_turn=True 이중으로 too_broad 차단 → 관계 맥락 답변.
- **Fix 2 인연 출처 디렉티브**(`PARTNER_SOURCE_DIRECTIVE`, 공용): '기존 지인 vs 새 인연' 질문에 합·도화
  =가깝고 익숙한 인연 / 충·역마=외부·새 인연 근거로 설명하되 사주로 확정 불가(경향·비단정). 출처 키워드
  (`_is_partner_source_question`)일 때 chat trailing 주입.
- 검증: ruff·mypy clean, 단위 테스트 추가(토픽 연속·출처 디렉티브 2건) + 회귀(affirmation 오인 1건 좁힌
  가드로 해결), 전체 스위트 통과(기존 환경 의존 통합 2건 제외 — 본 변경과 무관). Fix는 chat 라우팅 특성상
  채팅 경로 적용(구조 컨텍스트 자체는 기존대로 chat·report 공용).

### 통변 충실성 — 사용자 전제 존중·명식 간지 환각 차단 (2026-06-22)

데굴님 지적: ① '6월은 신호 없으니 그 다음부터 봐'라 했는데 LLM이 '사실은 6월에 강한 신호가 있다'며
전제를 반박, ② 己亥 일주를 己未로 환각 서술. 진단 — 6월(甲午)은 정관 단독이 아니라 재성(남 배우자성)
동반 재생관이라 엔진상 정당한 상위 신호(버그 아님)이나, 시스템 프롬프트에 사용자 전제 존중 규칙 부재 +
간지 변경 금지가 약했음. 시스템 프롬프트(llm_client) 보강.

- **Fix B 사용자 전제·시기 존중**(_SYSTEM_PROMPT 규칙 9 신설, 대화 전용): 사용자가 특정 시기를 빼달라거나
  본인 판단을 제시하면 부정·반박('아무 신호 없다고 생각하셨겠지만 사실은…' 류 금지) 말고 사용자가 원하는
  범위 중심으로 답하고, 그 시기에 신호가 있어도 사용자 의사를 우선.
- **Fix C 명식 간지 충실성**(_SYSTEM_PROMPT·_REPORT_SYSTEM_PROMPT 규칙 1 보강): [원국·명식 구조] 제공
  일주 등 간지를 그대로 인용, 다른 글자로 바꾸거나(己亥→己未) 물상·비유를 간지와 다르게 창작 금지.
- 검증: ruff·mypy clean, 프롬프트 반영 확인(양쪽 간지 가드 + 대화 규칙9), 전체 스위트 통과(기존 환경
  의존 통합 2건 제외). B는 대화 전용, C는 chat·report 양쪽.

### 절기월 경계 — 날짜 질문 월운 오매핑·절기월 날짜범위 주입 (2026-06-22)

데굴님 지적: '7월 4일 이사' 질문에 절기상 甲午월(소서 7/7 전)인데 乙未월(양력 7월)로 답함. 진단 —
날짜(daily) 질문이 MONTH composite를 절기월로 한정하지 않아(월 경로엔 필터 있음) 모든 월이 노출,
LLM이 양력 7월=乙未로 오인. + 데굴님 제안: 절기월을 '을미월' 대신 '7월 n일~8월 n일' 날짜범위로 주입.

- **Fix 1 절기월 필터**(`_build_period_fortune` daily): `_current_luck_month(target)`로 그 날의 절기월
  라벨을 구해 MONTH composite를 그 하나로 한정. 검증 — 7/4 컨텍스트에서 乙未 제거, 甲午만 노출.
- **Fix 2 절기월 날짜범위 주입**(데굴님 제안, `PeriodFortune.solar_month_note`): daily·monthly에 해당
  절기월 간지 + 양력 절입~다음절입 범위를 함께 준다(예: '甲午월(양력 2026-06-06~2026-07-06)').
  context_reducer가 '절기월 안내:' 줄로 렌더. '○월=○○월운' 혼동 금지 문구 동반.
- 검증: ruff·mypy clean, 단위 테스트 추가(절기월 경계 1건), 전체 스위트 통과(기존 환경 의존 통합 2건
  제외). 날짜·기간 질문은 대화(chat) 기능이라 채팅 경로 적용.

### 절기월 경계 후속 — 이사 날짜 질문 월 후보·이유블록 절기월 보정 (2026-06-22)

데굴님 재지적('안 바뀐 것 같은데'): 7/4 이사 질문이 여전히 乙未월(양력 7월)로 풀림. 진단 — 이 질문은
relocation 도메인이라 _build_period_fortune(daily, 앞서 수정)을 **타지 않고**(period_fortune_type=None)
일반 후보 경로를 탐. 두 곳이 양력 달로 乙未를 끌어옴: ① 후보 선택(win=2026-07-04 → in_question_range가
월 후보 '2026-07'=乙未 매칭), ② 이사 이유 블록(month_key=start[:7]='2026-07'). build_luck_grounding이
선택된 乙未 후보를 '乙未 유입=천간 乙…' grounding으로 노출 → LLM이 乙木 기신/未土 용신 서술.

- **Fix 1 후보 선택 절기월화**(chat_service 후보 윈도우): 날짜(YYYY-MM-DD) 단일일 질문이면 월 후보를
  `_current_luck_month(target)` 절기월 라벨로만 매칭(`_in_win`) — 7/4 → 2026-06(甲午)만, 2026-07(乙未)
  제외. 검증: 선택 월 후보 {2026-06}(기존 {2026-07}).
- **Fix 2 이사 이유 블록 절기월화**(`_relocation_reason_context`): YYYY-MM-DD면 month_key를 양력 달이
  아니라 절기월(`_current_luck_month`)로. 검증: 월운 천간 甲(정관)으로 교정(기존 乙 편관).
- 검증: ruff·mypy clean, 단위 테스트 추가(후보 절기월 선택 1건), 전체 스위트 통과(기존 환경 의존 통합
  2건 제외). 7/4 질문 grounding에서 乙未 제거·甲午로 일원화.

### 절기월 경계 3차 — 날짜 월간지 사실 명시 주입(LLM 양력 달 오답 차단) (2026-06-22)

데굴님 재지적('안 고쳐졌어, gpt쪽도 봐야지') + 직접 질문 '7월 4일의 월 간지는?'에 LLM이 '乙未(2026년
7월)'로 오답. 근본 원인 — 후보·블록을 절기월로 고쳐도 LLM이 monthly_luck 라벨('2026-07=乙未')을 보고
'7/4→7월→乙未'로 양력 달에 끌려 매핑. 후보 필터로는 LLM의 자체 매핑을 못 막음.

- **Fix(공통·provider 무관)**: `_date_solar_month_note` — 날짜(YYYY-MM-DD) 질문이면 그 날의 절기 월간지
  + 양력 절입 범위를 '[날짜 절기월 — 엔진 확정 사실]'로 trailing에 주입. '양력 N월 다음 절기월로 답하지
  말고 반드시 {간지}로 본다' 못박음. 검증: 7/4→甲午(2026-06-06~07-06)·7/10→乙未. Gemini·GPT 폴백 공통
  컨텍스트라 양쪽 적용.
- 검증: ruff·mypy clean, 단위 테스트 추가(날짜 월간지 사실 1건), 전체 스위트 통과(기존 환경 의존 통합
  2건 제외).

### 관계 친화·돌봄 성향 — '여자에게 잘하는 남자 사주' 일반화 (2026-06-22)

데굴님 제공 영상(여자에게 잘하는 남자 3유형) 기반. 성별 한정을 **성별 중립 '관계 친화도'**로 일반화 —
한 명식이 관계에 어떻게 임하는가(본인 자기인식·상대 평가 양용)를 십성 구조×신강약으로 산출(positive·
경향·비단정). marriage_resource + 공용 직렬화라 chat·report 자동 반영.

- `_relationship_affinity`(`marriage_resource`)·`relationship_affinity` 필드: 식신(월·일지)=케어·표현·
  재미 / 상관=표현 좋으나 돌발 / 식상생재=적극·타이밍 케어(단 장기 안정감 약) / 인성 적정=정·안정,
  과다=답답·의존 / 비겁=당당·회피 적음 / 신약+비겁 약+식상·재성 중심=회피·맞춰짐 주의 / 신강약 균형=
  누구에게나 맞춤 안정적 배우자감. 직렬화에 "관계 친화·돌봄 성향(경향·단정 아님)" 줄.
- 검증: ruff·mypy clean, 단위 테스트 2건(신호 분기·중립 렌더), 전체 스위트 통과(기존 환경 의존 2건
  제외). chat(RELATIONSHIP/총운)·report 결혼 섹션 양쪽 노출 확인.

### 교운(대운 교체) 가중 복원 — 전환성 이벤트 raw_score 곱셈 배율 (2026-06-23)

데굴님 지적('재취업 달이 11/12월이었는데 6월로 어긋남, 교운일 영향력이 낮게 평가된 듯'). 진단 결과
**낮아진 게 아니라 통째로 누락(0)**. 구 EventScorer는 `daewoonTransition` 신호를 `daewoon_transition_weight`
로 점수에 배율 적용했으나, 21키 재설계 하드스위치(645659b)에서 `EventEngineV2`+십성 brancher로 교체되며
교운 항이 전부 빠짐. `daewoon_transition_weight()`는 실사용 0건(테스트만 참조), `daewoonTransition` 신호는
career_change/relocation.json에 남았으나 새 엔진이 안 읽는 죽은 신호. 결과: 6월 강한 정관(甲午)이 교운일
(데굴 차트 2025-11-15) 근접한 11/12월을 누름.

- **복원(2026-06-23 사용자 승인 — 곱셈 배율×전환성 전반)**:
  - `event_scoring.py`: `DAEWOON_TRANSITION_BOOST_ALPHA=1.0` + `TRANSITIONAL_EVENT_KEYS`(career_change·
    job_gain·business_start·relocation·new_relationship·marriage_signal·relationship_change·childbirth·
    education_admission) + 순수함수 `daewoon_transition_boost(raw, target, jiao_dates, event_key)` →
    전환성 이벤트이고 weight≥MIN_WEIGHT면 `raw×(1+α·weight)`.
  - `event_engine_v2.py`: `_StackIndex.jiao_dates`(trace.exact_jiao_un_dates) + `_period_midpoint` +
    `_score_target` soft_cap **이후** raw_score에만 배율 적용(가산 기여 `daewoon_transition` + reason_code).
    display score·activation(포화 채널)은 base raw 기준 불변 — 유력 달은 strength_rank(raw_total)로 가므로
    랭킹만 정확히 뒤집히고 display 포화/변별·desaturation 불변(test_score_saturation 정당 통과).
- 검증: 데굴 실차트(교운일 2025-11-15) job_gain raw_score 11월=240 1위(기존 7월125·2월122에 밀려 3위였음),
  strength_rank rank1=11월「취업·합격」·rank3=12월(둘 다 '대운 교체 정점'). ruff·mypy clean, 회귀 2건 추가
  (부스트 게이팅 + 사용자 보고 케이스 재현, 죽은 신호 재발 방지), 전체 스위트 통과(기존 환경 의존 통합 2건 제외).

### 테마운세(테마 FOCUS)·총운 전 구간 스펙트럼 보강 — 다년 월운 + 연도/월 전수 표 (2026-06-23)

데굴님 지적('테마운세가 3년+특정 달만 반복, 좋은/나쁜/평범 달 전체를 세부적으로 못 풀어줌'). 진단(실측):
① `calculate(reference_date)`가 **월운을 1년(12개월)만** 생성 → 5년 예측인데 월 디테일 1년뿐.
② 거의 모든 섹션이 쓰는 `self.candidates`(top-8)가 **전부 2026년 달**로 채워져 동일 강신호 반복.
③ 전체 12개월 표(`month_overview`)·도메인 후보 분리(`domain_candidates`)가 **RPT_YEAR·RPT_FULL에만**
적용, 테마 FOCUS(W/J/R/RL) 목차엔 미연결. ④ 2027~2031 세운은 계산돼 있으나 top-8에 밀려 미노출.

- **보강(2026-06-23 사용자 승인 — 전체 1~5, 테마+총운 / 목차 섹션 가감 없이 데이터·풀이 프로세스만)**:
  1. **월운 다년 생성**: `_ReportData.__init__`이 예측 창(오늘~+5년) 각 해 `luck_months`를 주입 →
     월 후보·12개월 표가 다년에 걸침(데굴 케이스 12→72개월). `_forecast_years` 헬퍼.
  2. **월 표 다년 그룹화**: `month_overview_lines`를 연도별(〈YYYY년〉) 그룹 출력으로 확장, ★주목은 연도
     내 상대. 테마 '주목할 달' 섹션(W-07/J-06/R-06/RP-07/RL-06/C-04)에 `_MONTH_OVERVIEW_SECTIONS`로 연결.
  3. **연도 스펙트럼 표 신설**: `year_spectrum_lines` — 예측 창 세운 전 연도를 운품질 등급·우세도메인·
     길흉·★주목으로 빠짐없이. '향후 N년 종합' 섹션(W-06/J-05/R-05/RP-06/RL-06/C-03) + 총운 F-14에 연결.
  4. **도메인 후보 분리 확대**: 테마 FOCUS 종합·주목달 섹션을 `_SECTION_DOMAIN`에 추가(길·흉 포함 후보).
     스펙트럼 표·후보 모두 **도메인 인지**(테마 섹션은 대표 사건을 주제로 한정, 운 품질 등급은 도메인 무관 표기).
  5. **분량 상한 확대**: 스펙트럼 섹션(`_WIDE_SECTIONS`)은 검사 상한을 4,200자로(하한은 캘리브레이션값 유지 —
     미달 오탐 방지). `report_plan._tc_for`.
- 검증: 데굴 직업운 FOCUS — 월운 72개월(2026~2032), 연도 스펙트럼 6년 전수(강한 용신운/기신운 등급·★),
  월 표 연도별 그룹 80줄, 도메인 후보 2026~2031 분포(종전 전부 2026). ruff·mypy clean, 전체 스위트 통과
  (기존 환경 의존 통합 2건 제외). Y-05(한해풀이)는 도메인 None으로 교차도메인 기존 동작 보존.

### 대운 풀이 보강 — 전문가 강의(대운=환경/공간감) 참고 반영 (2026-06-23)

데굴님 제공 대운 강의 스크립트 검토. 강의 핵심 중 조후(겨울생→여름대운=조후용신 火→火대운 용신운)·
대운 천간-일간 오행관계·대운 품질 등급(luck_label/stem_effect)·천간/지지 시기분할(first/second_half_focus)·
구간(activation window)은 **이미 정식 구현**돼 있어 참고 불필요(강의의 '일간별 유리 오행' 휴리스틱은
우리 용신의 단순화 — 정확도상 미채택). 풀이(서술) 품질만 4건 보강(계산 불변, 사용자 승인):

- **A. 대운 framing**: 대운을 '환경·공간감(플랫폼)이 닥쳐오는 흐름', 핵심은 '이 대운이 나에게(용신·조후)
  맞느냐'로 서술하는 `_DAEWOON_FRAMING_DIRECTIVE` → F-07/F-10/F-13/Y-03(`_DAEWOON_FRAMING_SECTIONS`).
- **B. 천간/지지 시기 분할 노출**: 계산만 되고 미노출이던 first/second_half_focus를 `luck_block`[대운표]에
  '전반 0-4년 천간 주도 · 후반 5-9년 지지 주도'로 surface(+ 대운별 천간/지지 십성).
- **C. 교체기 체감 신호(비단정)**: 주변 사람 교체·새 일 도모·막연한 기대·지인 반대·거주/물건 정리·외모
  변화를 '겪을 수 있다' 가능 형태로만(`_DAEWOON_TRANSITION_SIGNALS_DIRECTIVE`) → F-07·F-09(과거 검증
  체크리스트). 단정·예언 금지 가드 포함(원칙8).
- **D. 안 맞는 대운 조언**: 평운·기신 구간은 '포기 아니라 유지·내실·다음 대운 준비'(`_OFF_PEAK_DAEWOON_
  ADVICE_DIRECTIVE`) → 행동전략 섹션(F-19/Y-10/W-08/J-07/R-07/RP-09/RL-07/C-07).
- 미채택: 일간별 유리 오행 휴리스틱(우리 용신이 더 정확·원칙1), '목 대운 보편 성장' 단정(용신-relative
  충돌·단정 위험). 검증: ruff·mypy clean, 디렉티브 부착 시뮬 확인, 전체 스위트 통과(기존 환경 2건 제외).

### 대운 framing — AI 채팅 확장 적용 (2026-06-23)

리포트 대운 섹션에만 있던 대운 풀이 관점을 채팅 응답에도 확장(사용자 승인). 공용화:
- 디렉티브를 `structural_context`로 이관(`DAEWOON_FRAMING_DIRECTIVE`·`DAEWOON_TRANSITION_SIGNALS_
  DIRECTIVE`) → 채팅·리포트 공용. report_service는 import로 전환(off-peak 조언은 리포트 전용 유지).
- framing을 product-agnostic으로 정리: A(환경/공간감·'나에게 맞느냐')+B(전반 천간/후반 지지 시기차)+
  D(안 맞는 구간=유지·내실) 한 디렉티브에 통합('위 대운표' 참조 제거).
- 채팅: `_is_daewoon_question`(키워드 대운/교운/평생/10년 등) 추가 → trailing에 framing+교체기 신호 append.
  막연한 장기 질문(vague_future, 이미 10년 digest)도 OR로 묶어 함께 적용.
- 검증: ruff·mypy clean, 술어 키워드 판정 확인(대운/교운/10년→적용, '올해 재물운'→미적용), 전체 스위트
  통과(기존 환경 2건 제외). 계산 불변(점수·날짜·간지·판정 무관 — 서술 관점만, 원칙1·8).

### 사용자 확정 용신 → 용희기구한 5역할 일관 재도출 + 스코어링 반영 (2026-06-23)

데굴님 지적: 용신 확정질문으로 용신이 바뀌면 희/기/구/한도 그 용신 기준으로 함께 바뀌어야 오행
중복이 안 생긴다. 기존엔 `subject_yongsin.confirmed_yongsin`(단일 오행)이 **저장·표시만** 되고 스코어링
파이프라인이 전혀 소비하지 않아, 확정해도 풀이가 안 바뀜(역할 재도출도 미발생). 연결 추가:

- **event_scoring.py**: `classify_yongsin_roles(용신)` — 생극 순환으로 기신=극용신·희신=생용신·구신=
  생기신·한신=용신생을 1:1 배정(candidates._classify_roles와 동일 규칙, 5오행 중복 0). `confirmed_
  favorability_override`(→{오행:역할} fav_override), `normalize_element`(한자/한글/영문), `confirmed_
  yongsin_note`(확정 적용 + 엔진 최초 도출 병기 — 같으면 빈 문자열).
- **personalization.py**: `fetch_confirmed_yongsin_override(owner,subject)` — ProfileStore.get_yongsin →
  정규화 → override. 미설정·무DB·미상=무override(규칙11).
- **chat_service.py**: 스코어링 4곳(all_scored·year_scored·window·target_year)에 `fav_override` 주입 +
  trailing에 확정 안내 주석.
- **report_service.py**: `score_legacy_personalized(fav_override=…)` + prefix에 확정 안내 주석 부착.
- **핵심 — 비파괴 보존(사용자 추가 요건)**: 엔진 최초 도출값(yongsin_analysis.final = 확정 전 후보
  상태)은 **절대 덮어쓰지 않음**. 확정은 fav_override로만 적용하고, 최초 도출은 기본값·되돌림 기준으로
  주석에 병기. calculate()가 결정론적이라 기본값은 항상 재현 가능.
- 검증: 5오행 전수 — 각 용신마다 용희기구한 5역할이 서로 다른 오행(중복 0). 데굴 차트 木 확정 →
  용木·희水·기金·구土·한火, final(土) 비파괴 보존(==before). ruff·mypy clean, 전체 스위트 통과(기존 2건 제외).

### 후속 턴 일주 오답 수정 — 멀티턴 원국 사실 일관성 가드 (2026-06-23)

데굴님 지적: 첫 질문은 일주(己亥)를 맞게 답하는데 이어진 후속 질문에서 일주를 틀리게 답함(예:
'기미'). 진단 — 데이터는 정상(후속 턴 prefix에도 일주 己亥가 명식줄·궁성줄·일주사전 3중으로 존재).
원인은 `_FOLLOWUP_INSTRUCTION`이 후속 턴마다 "앞서 설명한 **일주**·격국·용신 등 배경을 길게
재인용하지 말 것"이라 지시 → LLM이 일주를 '재인용 말아야 할 배경'으로 취급, 그래도 습관적으로 일주
물상 문장을 열며 사실 블록을 안 읽고 기억으로 생성→환각. (첫 턴엔 이 지시 없어 정확)

- **수정(지시문 2곳, 계산·점수 불변)**: ① `_FOLLOWUP_INSTRUCTION` — '일주 재인용 금지' 문구 제거,
  대신 "일주·일간·용신·격국 등 원국 사실 언급 시 [원국·명식 구조] 값을 글자 그대로, 기억으로 지어내거나
  다른 간지로 바꾸지 말 것" 일관성 가드로 교체. ② `_SELF_CHECK_INSTRUCTION` — "일주(日柱)·일간·용신
  표기가 [원국·명식 구조]와 글자까지 일치하는지 대조, 틀리면 정정" 1줄 추가.
- 채팅·리포트 공용 직렬화(serialize_llm_input) 경로라 후속 턴 전반 적용. 검증: ruff·mypy clean, 지시문
  반영 확인, 전체 스위트 통과(기존 환경 2건 제외).

### 멀티턴 시점 승계 — 후속 턴이 직전 시점 창을 잇도록 (2026-06-23)

데굴님 지적: 8/31·9/30(=2026 매매·이사) 질문 뒤 후속 '대출 안 나오나?'에 2027~2035 연 흐름으로
오답(사용자 '2026인데 왜 그 이후?'). 진단 — 후속 턴 '대출/비용/계약'이 새 도메인을 들고 와 link이
**NEW로 분류**(follow-up 아님)→`prev=None`→시점 미상속→intent.time_range None→`vague_future`(올해부터
10년 digest) 발동. 파서(B2/B2d)·대화엔진 슬롯상속 모두 **긴 후속의 time_range를 승계하지 않았음**.

- **수정(conversation.py)**: 시점을 **스레드 레벨 슬롯**으로 격상 — link 종류(NEW·도메인전환 포함) 무관,
  이번 턴이 자체 시점을 안 들고 오고(`time_range` None/무 start) '새 풀이·리셋' 신호(`_FRESH_OVERVIEW_RE`
  총운/평생/처음부터 · `_READING_REQUEST_RE` 사주 봐줘)도 아니면 `state.last_intent.time_range`를 승계.
  명시 시점을 새로 주면 자체 시점 우선(미승계).
- 검증: 시뮬 — 턴1 2026-08-31 → 턴2(link=NEW) 2026-08-31 승계(10년 digest 차단), 턴3 '2026' 명시 우선,
  턴4 '총운 처음부터' 미승계. 회귀 2건 추가(도메인전환 승계 / 새풀이·명시 미승계). ruff·mypy clean,
  전체 스위트 통과(기존 환경 2건 제외).

### 특정 날짜 질문 — 일운(日運) 중심 서술 보강 (2026-06-23)

데굴님 지적(같은 로그): '중도금 8/31·이사 9/30 운' 질문에 월운(丙申월·丁酉월)만 답하고 그 날의
일운(日運)이 빠짐. 원인 — 두 날짜(다중)라 단일 daily 총운·택일 경로에서 빠지고, 트레일링의
`_date_solar_month_note`는 **절기월 간지만** 주입해 LLM이 월 단위로만 답함.

- **수정(chat_service.py)**: `_explicit_dates`(질문서 'N월 N일' 다중 추출, 연도 생략 시 기준연도) +
  `_date_day_fortune_note`(각 날의 일운 간지·천간/지지 십성·길흉 + 절기월 + '그 날의 일운을 중심으로,
  월운·세운은 배경' 디렉티브, 최대 4일). 트레일링에서 단일 월간지 노트 대신 이 일운 노트를 주입
  (명시 날짜 우선, 없으면 단일 날짜 시점 폴백). `_date_solar_month_note`는 기존 테스트용 보존.
- 검증: '8/31·9/30' → 일운 두 개 모두 사실 주입(8/31 丁丑·9/30 丁未 등)·일운 중심 지시 확인, 연도 생략
  보정. 회귀 1건 추가. ruff·mypy clean, 전체 스위트 통과(기존 환경 2건 제외).

### 멀티턴 시점 승계 과잉 적용 수정 — 시점-탐색·새 시점 구분 (2026-06-23)

데굴님 지적: 직전 시점 승계(스레드 레벨) 도입 후, 날짜를 한 번 지정하면(예: 7/4 이사) 이후 그와
무관한 '연애는 언제 시작?'·'결혼할까?' 같은 시점-탐색 질문까지 7/4에 고정돼 풀이됨(과잉 승계).

- **원인**: 파서가 '언제'를 `open_when`(start 없음)으로 잡는데, 승계 코드가 `not start`만 보고 그 위에
  직전 날짜를 덮어써 시점-탐색 질문을 고정.
- **수정(conversation.py)**: ① `_TIME_SEEKING_RE`(언제/할 수 있을까/가능할까/몇 년 후/언제부터) 매칭
  턴은 승계 제외. ② 승계 대상 intent가 자체 시점이 있거나 `time_range.type=='open_when'`이면 건너뜀.
- **'다른 시점 지정 시 승계 기준 초기화'(추가 요건)**: `last_intent`가 매 턴 갱신되므로 새 시점을 주면
  그게 다음 승계 기준이 되어 자동 초기화 — 시뮬로 확인(8/31 승계 → '2028년' 지정 → 이후 '돈은?'이
  2028 승계, 옛 8/31 아님).
- 검증: 시뮬 — 7/4 뒤 '연애 언제?'=open_when 미승계, '결혼할까?' 미승계 / 8/31→대출(승계 유지)→
  2028(초기화)→돈(2028 승계). 회귀 2건 추가. ruff·mypy clean, 전체 스위트 통과(기존 환경 2건 제외).

### 페르소나 말버릇이 말투를 안 따르는 결함 수정 (2026-06-23)

데굴님 지적: 반말 페르소나 답변에 '이 흐름 좋네요'(해요체)가 끼어듦. 원인 — `persona_lexicon.json`의
말버릇은 gender_ageband로만 뽑히고 전부 해요체인데(neutral_20s='이 흐름 좋네요'), 말투(반말 등)는
별도 축이라 프롬프트에 해요체 말버릇이 그대로 주입됨. 채팅은 페르소나 준수 검사(보고서 전용 게이트)도
안 걸려 그대로 노출.

- **수정(persona.py 템플릿)**: 말버릇 주입 지시를 '말버릇의 결만 참고하되 반드시 현재 말투·종결어미로
  변환'으로 변경(예시가 해요체여도 그대로 박지 말 것 — 예: 반말체면 '이 흐름 좋네요'→'이 흐름 좋네').
  채팅·리포트 공용 템플릿이라 양쪽 적용. 페르소나=문체 전용·점수/판정 불변 유지(docs/11 5-3).
- 검증: 반말+neutral_20s 블록에 '현재 말투로 변환'·변환 예시 노출 확인, 해요체 혼입은 준수검사 ③에서
  혼용 위반으로 검출. 회귀 1건 추가. ruff·mypy clean, 전체 스위트 통과(기존 환경 2건 제외).
- (참고) 채팅은 페르소나 준수 검사·재생성이 없어 LLM이 지시를 어기면 폴백 없음 — 필요 시 채팅측
  경량 검사 추가는 별도 작업.

### 신뢰도 한글 순화 + 페르소나 변경 시 호칭 유지 (2026-06-23)

데굴님 지적 2건:
1) 신뢰도가 'medium_high'/'high' 내부 키 그대로 노출(리포트 후보 블록·점수표). →
   `events.py`에 `CONFIDENCE_KO`/`confidence_ko()`(낮음/다소 낮음/보통/다소 높음/높음) 추가,
   `report_event_input`의 후보 블록·점수표 렌더를 한글 라벨로 교체. (채팅 후보는 tone으로 대체돼
   confidence 미노출 — 영향 없음.) 회귀 1건.
2) 페르소나(말투) 변경 시 사용자 지정 호칭이 기본값으로 리셋됨. → 프론트 `StepPersona.setPoliteness`가
   politeness 변경 때 호칭을 무조건 preset 기본값으로 덮어쓰던 것을 수정 — custom 호칭은 그대로 유지,
   preset 호칭은 새 politeness와 정말 충돌할 때만 보정(호환 프리셋은 유지). 백엔드 resolve_honorific은
   원래 config 값을 그대로 사용(정상). 성별·나이·난이도 변경은 호칭 미변경(기존 정상).
- 검증: confidence_ko 매핑·리포트 렌더에 내부 키 0건 확인. backend ruff·mypy·pytest 통과(기존 환경 2건
  제외), frontend tsc·production build 통과.

### 용신 작동역할 2계층 모델 설계 스펙 작성 (2026-06-24)

데굴님 지적(丁巳/壬子/丁未/癸卯, 일간 丁火 신약·水 60.3% 사례): 살인상생형인데 水가 희신으로
고정되는 게 위험. 검증 결과 — 진짜 결함은 "엔진이 조후·합·관살혼잡을 안 봐서"가 아니라,
후보 모델(`resource_as_yongsin`)이 火=희신·水=한신을 **이미 계산**했는데 최종
`candidates.py::_classify_roles`가 용신 오행 하나만으로 정적 생극 순환(희신=生용신)을 다시 돌려
水=희신으로 **평탄화·덮어쓰기** 하는 점. `_climate_harmful`이 水를 한습역행으로 잡고도 최종 희신
슬롯을 우회하는 모순도 확인.

- **조사(코드 수정 없음)**: 후보 모델 역할맵 vs final 불일치 지점([candidates.py:777]) 확정. 7개
  명리 요소 코드 커버리지 — 官 합반 세력차감(미구현·분포단계 relation deferred), 子卯刑(격각 비인접
  의도적 제외), 형/해 통관 미반영(건강레이어 전용), 용신 원소별 투간/통근(일간만), 정/편인(분류만,
  용신단계 오행 합산으로 소실), 조후 축(신약 eokbu0.45>johu0.25), 조건부역할 스키마(없음). 테스트
  정합성 — 회귀 골든은 용신 역할 미고정, resource_as_yongsin selected 단언 0건 → 모델맵 존중 전환
  시 직접 파손 0건(부분맵 폴백 보존 조건).
- **산출물**: `doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md` 신규. canonical(정적)/operational(작동)
  2계층 역할 모델, ElementRole 스키마, Phase 0~4 계획+회귀 게이트, 결정사항 D1~D4(子卯刑 격각=
  operability penalty 0.3·이벤트 비신호 / 합반=HAP_SPEC 위임 / 조후 火=조후보조신 격상 / 정·편인=
  confidence modifier·용신 불변), 수치 계수는 config/experimental 분리(§6).
- 정책(데굴님 확정): 전체 갭을 정식 범위로 인정하되 단계별 승인 — docs/spec→테스트→Phase0부터 순차.
- (다음) 데굴님 스펙 승인 후 Phase 0 착수(계층 분리 + 5역할완비 모델 역할맵 존중, 표준사례 픽스처).

### 용신 2계층 역할 Phase 0 — canonical/operational 분리 (2026-06-24)

YONGSIN_OPERATIONAL_ROLE_SPEC Phase 0 구현(데굴님 3개 보완조건 반영). 정적 역할(final/canonical)
불변·additive only·scoring 미연결 원칙 준수.

- **수정(yongsin.py)**: `ElementRole`(element/canonical_role/operational_role + Phase1용 positive_when/
  negative_when/note) 신규. `AggregatedYongsinResult`에 `canonical_roles: dict[str,str|None]`(=final
  5역할 미러) + `operational_roles: list[ElementRole]` additive 추가. `final` 불변.
- **수정(candidates.py::build_yongsin)**: 헬퍼 3종(`_role_by_element`/`_operational_role_map`/
  `_build_operational_roles`) + final 조립 직후 operational 산출. **selected_model 객체 직접 탐색**
  (동일 model_type·yongsin 중 최고 confidence — 보완①). **게이트**: final 이 정적 `_classify_roles`를
  그대로 쓴 경우에만 5역할완비 모델의 자체맵 채택, bridge_tonggwan·부일간(무비겁) 특수분기는 canonical
  폴백(특수분기 교정을 되돌리지 않음). canonical_roles 타입 `str|None` 방어(보완②), 생성은 중첩 컴프
  대신 `_role_by_element` 명시 helper(보완③).
- **효과**: 표준사례 丁巳/壬子/丁未/癸卯 — final/canonical 은 정적대로 희신=水·한신=火 유지, operational
  만 火=희신·水=한신 정상화. event_scoring `favorability_map`은 final 만 소비 → 다운스트림 점수 불변.
- **신규 테스트**(test_yongsin_operational.py 6종): 표준사례 정상화·5오행 무None·bridge/disease/
  support특수분기 canonical 폴백·final&favorability 불변.
- 검증: unit 699 pass·1 skip, ruff·mypy clean(65). 잔여 2건(chat_pipeline too_broad·report_jobs)은
  clean HEAD에서도 동일 실패하는 기존 DB 통합 환경 실패 — 본 변경과 무관(스태시 대조 확인).
- (다음) Phase 1(ElementRole 조건부 필드 positive_when/negative_when 채움) — 데굴님 승인 후 착수.

### 용신 2계층 역할 Phase 1 — 과다·병 기반 조건부 라벨 (2026-06-24)

YONGSIN_OPERATIONAL_ROLE_SPEC Phase 1(데굴님 조건부 승인 — G1~G4 + 추가조건 반영). 조후는 Phase 2로
유지, operational 미소비(생성·노출만, scoring 영향 0).

- **신규(operational_role_config.py, experimental)**: `OPERATIONAL_ROLE_CLASS`(라벨→길흉클래스 mapper —
  "조건부 희신/병"=conditional 로 고정, 향후 scoring 은 문자열 부분파싱 금지·이 mapper만 경유) +
  `CONDITION_TEMPLATES`(ConditionTemplate TypedDict, 조건부 희신/병·조건부 제살보조 2종 positive/
  negative_when·note). 문구는 candidates.py 에 직접 박지 않고 이 모듈에서만 관리.
- **수정(yongsin.py)**: `operational_role: str` → `OperationalRole` Literal enum(정적 5 + 조건부 희신/병·
  조후보조신·조건부 제살보조). 잘못된 라벨 ValidationError.
- **수정(candidates.py)**: `_overloaded_element`(기존 과다 판정 _officer_heavy/_output_heavy/
  _resource_overload/_bigyeob_overload 만 사용)·`_with_condition`·`_annotate_overload_conditions`.
  과다 십성이며 canonical 희신(生용신)→"조건부 희신/병", 과다 오행을 극하는 canonical 구신/기신→
  "조건부 제살보조". note 에 합성출처(base_model_role=한신·canonical_role=희신·synthesized_by=
  overload_condition) 기록. **model_map 채택 케이스(model_map_adopted)에만 적용** → fallback/부분맵·
  특수분기(bridge·disease·support)에 조건부 라벨 미누출.
- **효과**: 표준사례 — 水=조건부 희신/병(과다·병), 土=조건부 제살보조, 火=희신(조후보조신 격상은 Phase 2),
  木=용신·金=기신. final/canonical/favorability 불변.
- **테스트**: test_yongsin_operational_conditions.py 신규(과다 조건부 라벨·비과다 plain 유지·fallback
  미누출·enum reject·roundtrip·final/canonical 불변). Phase 0 표준사례 단언은 누적 진화 반영해 phase-안정
  단언으로 갱신(水·土 조건부 검증은 Phase 1 파일이 소유).
- 검증: unit 710 pass·1 skip, ruff·mypy clean(168). 잔여 2건은 기존 DB 통합 환경 실패(무관).
- (다음) Phase 2(조후 가드 _climate_harmful 연결 → 火=조후보조신, 한습 水 강등) — 승인 후 착수.

### 용신 2계층 역할 Phase 2 — 조후 가드 operational 연결 (2026-06-24)

YONGSIN_OPERATIONAL_ROLE_SPEC Phase 2(데굴님 조건부 승인 F1~F4 + 추가조건 3). 기존 _climate_harmful
(子월 한습 火<22%→水 역행 등)을 operational 역할에 연결 — 계산만 하고 최종역할 미반영이던 모순 해소.

- **수정(operational_role_config.py)**: CONDITION_TEMPLATES["조후보조신"] + CLIMATE_HARMFUL_REASON
  (cold/hot). OPERATIONAL_ROLE_CLASS 주석에 "조후보조신=favorable 보조약, primary yongsin 동일가중 금지".
- **수정(candidates.py)**: _with_condition 시그니처 확장(synthesized_by: list[str] 고정순서·extra_negative,
  _dedupe 순서보존 중복제거) → Phase 1 호출 synthesized_by=["overload_condition"]. 신규
  _annotate_climate_conditions: harmful is None(중립월/조후정상)이면 no-op; climate_need(한습→火/조열→水)이
  operational 희신/한신→"조후보조신"(synthesized_by=climate_need); climate_harmful이 희신→"조건부 희신/병",
  이미 조건부면 한습 negative 추가+출처 병합(overload_condition+climate_harmful, 순서 고정).
  build_yongsin Phase 1 직후 동일 model_map_adopted 게이트로 호출.
- **효과**: 표준사례 §4-2 목표 완성 — 火=조후보조신, 水=조건부 희신/병(과다+한습 병합), 土=조건부 제살보조,
  木=용신, 金=기신. 중립월(辰戌) 차트는 조후 no-op(과다 라벨만). final/canonical/favorability 불변·미소비.
- **테스트**: test_yongsin_operational_climate.py 신규(火 조후격상·水 병합 출처·중립월 no-op·final 불변).
  Phase 1 obsolete(火 not_yet_johu) 제거, no_overload 테스트는 "과다 합성 출처 없음"으로 정정(亥월 조후보조신은
  정상 허용). Phase 0 표준 단언도 누적반영 갱신.
- 검증: unit 713 pass·1 skip, ruff·mypy clean(168). 잔여 2건은 기존 DB 통합 환경 실패(무관).
- **요약: 최초 문제(水 희신 고정·火 한신 밀림)는 operational 레이어에서 정상화 완료.** (다음) Phase 3
  (합반/합화/관살혼잡 → 官殺 세력 재산정, HAP_INTERACTION_SPEC 위임) 승인 후 착수.

### 용신 2계층 역할 Phase 3 — 官殺 합 맥락 주석 (Option B) (2026-06-24)

YONGSIN_OPERATIONAL_ROLE_SPEC Phase 3(데굴님 Option B 승인 DP1~4 + 추가조건 6). **범위 결정**: Option A
(distribution 차감→groups→신강약→모델선택→final 연쇄 변경, scoring SSOT 변경, HAP_SPEC §H '보류' 영역)는
별도 이니셔티브로 분리. Phase 3는 operational 주석/조건 enrichment로 한정(라벨·세력·final 불변, scoring-0).

- **재사용**: resolve_stem_hap(pillars, fav)[완성 — transform_tier·hap_mode(bind/transform)·direction(away)·
  contend(쟁합)] + geokguk.evaluation.damage_types(mixed_officer_killing 관살혼잡). 둘 다 build_yongsin에서
  접근 가능(분포 미변경).
- **수정(operational_role_config.py)**: OFFICER_HAP_REASON(bind/contend/away/transform_confirmed/
  mixed_officer_killing 텍스트만; 배치는 함수 규칙).
- **수정(candidates.py)**: note 합성 단일화 _compose_note/_parse_note, _enrich_element(라벨 불변·기존
  positive/negative/note 누적·synthesized_by 끝에 출처 추가). 신규 _annotate_officer_hap_context:
  resolve_stem_hap에 canonical 기준 fav 전달(DP3), 官殺 원소(g["officer"])를 묶은 resolution 추출 →
  배치 규칙(추가조건 1~3): bind/합반→positive, transform confirmed→positive, contend/쟁합→negative,
  관살혼잡→negative, away/합거→note(官이 병이면 positive). build_yongsin Phase 2 직후 model_map_adopted
  게이트로 호출.
- **효과**: 표준사례 水(官殺) — operational_role=조건부 희신/병 **불변**, positive_when에 "합반 官 압박 완화",
  negative_when에 "쟁합 불안정"·"관살혼잡 탁", note synthesized_by=overload_condition+climate_harmful+
  officer_hap(고정순서). final/groups(officer 45 불변)/strength/canonical/favorability **불변**·미소비.
- **테스트**: test_yongsin_operational_officer_hap.py 6종(라벨불변 enrich·중복없음·합없으면 미부착·fallback
  미누출·final/groups/strength/favorability 불변·roundtrip).
- 검증: unit 719 pass·1 skip, ruff·mypy clean(168). 잔여 2건 기존 DB 통합 환경 실패(무관).
- (다음) Phase 4(용신 작동성 — 투간/통근·정/편인·子卯刑 격각 통관손상 operability) 승인 후 착수. Option A
  (관계 보정 기반 분포 재산정)는 별도 이니셔티브로 보류.

### 용신 2계층 역할 Phase 4a — 용신 작동성(operability) 투간/통근·정편인 (2026-06-24)

YONGSIN_OPERATIONAL_ROLE_SPEC Phase 4 분할(데굴님 4a/4b 분할 승인). 4a=투간/통근+정편인, 4b=子卯刑 격각
(별도). DP1~5 + 추가조건 8 반영. final.confidence 불변(=모델 선택 신뢰도) / operability=실제 작동성 분리.

- **수정(yongsin.py)**: ElementRole에 `operability: float|None = Field(default=None, ge=0, le=1)` +
  `operability_factors: list[str]`(stable key) 추가. 용신만 채움·나머지 None.
- **수정(operational_role_config.py)**: OPERABILITY_PENALTY(no_transmit 0.15·no_root 0.20·
  pyeonin_only 0.10, experimental) + OPERABILITY_REASON(표시 문구 — factors는 key, 문구는 분리).
- **수정(candidates.py)**: _compute_yongsin_operability(투간=Pillar.stem_element, 통근=hidden_stems
  element, 정/편인=Pillar.stem_ten_god 기준; 印 용신 투출+정인無+편인만→pyeonin_only, 印 투간無면
  no_transmit만 중복없음; 순서 no_transmit→no_root→pyeonin_only; round 1회). _with_operability(용신
  ElementRole에 수치·factor key·표시 사유 negative_when 부착). build_yongsin Phase 3 직후 model_map_
  adopted 게이트로 용신만 set. **격각 로직 없음**(4b).
- **효과**: 표준사례 용신 木 — 투간無(통근 卯·未 O) → operability 0.85, factors=["no_transmit"],
  negative_when에 표시 사유. 정인(甲) 투출 차트=1.0, 편인(乙)만=0.9(차등). 비용신·fallback=None.
  데굴님 최초 지적("木 투간 안 됨 → confidence 0.88 과하다")이 operability 0.85로 표면화(final.confidence
  는 불변 — 별도 지표). final/groups/strength/favorability **불변**·미소비.
- **테스트**: test_yongsin_operability.py 7종(no_transmit·정상 1.0·편인<정인·비용신 None·fallback None·
  final 등 불변·roundtrip). 계수는 config에서 읽어 단언(하드코딩 없음).
- 검증: unit 726 pass·1 skip, ruff·mypy clean(168). 잔여 2건 기존 DB 통합 환경 실패(무관).
- (다음) Phase 4b(子卯刑 격각 통관손상 allowlist, operability penalty 전용·이벤트/관계 판정 불변) 승인 후.

### 용신 2계층 역할 Phase 4b — 子卯刑 격각 통관손상 operability (2026-06-24)

YONGSIN_OPERATIONAL_ROLE_SPEC Phase 4b(데굴님 승인 DP-b1~3 + 추가조건 8). 비인접 子卯 격각만 operability
penalty(allowlist 1건, 용신 木만). **이벤트/관계 판정 불변** — relations.py·이벤트 산출 미수정.

- **수정(operational_role_config.py)**: GYEOKGAK_ALLOWLIST(experimental — 子卯刑 1건: branches(子卯)·
  yongsin_elements(木)·weight 0.30·reason). 확장은 후속 승인.
- **수정(candidates.py)**: _ADJ_POSITION_PAIRS(年月·月日·日時=인접) + _gyeokgak_operability_factors
  (allowlist 순회, 두 지지가 비인접 위치에 모두 존재 AND 용신∈yongsin_elements → factor·weight·reason;
  인접쌍 제외·동일 factor 1회). _compute_yongsin_operability에 4a 뒤 격각 penalty 추가(순서 no_transmit
  →no_root→pyeonin_only→gyeokgak_zimao, round 최종 1회), reasons 스레딩(allowlist reason→negative_when).
- **효과**: 표준사례 용신 木 — 4a no_transmit(×0.85) + 4b 子卯 격각(子 월지·卯 시지 비인접, ×0.70) →
  **operability 0.595**, factors=["no_transmit","gyeokgak_zimao"], negative_when에 격각 사유. 인접 子卯
  (이벤트 형으로 검출되는 차트)는 operability 미반영(op 1.0). final.confidence 0.8822·groups·strength·
  favorability **불변**, relations에 子卯 격각 비검출(이벤트 불변).
- **테스트**: test_yongsin_operability_gyeokgak.py 7종(표준 0.595·이벤트 비격각화·인접은 이벤트 operability
  미반영·용신 오행 게이팅·子卯 없으면 미적용·중복1회·final 등 불변). 4a 테스트는 누적 진화로 격각 무관
  차트(no_transmit 단독 壬子/丙子/丁丑/癸未, 편인 단독 癸亥/乙亥/丁丑/乙未)로 교체.
- 검증: unit 733 pass·1 skip, ruff·mypy clean(168). 잔여 2건 기존 DB 통합 환경 실패(무관).

**🎉 용신 작동역할 2계층 워크스트림(Phase 0~4b) 완료.** 최초 지적(丁巳/壬子/丁未/癸卯 사례 "木 용신은
맞으나 水가 과다해 희신 고정은 위험·火는 조후약·투간無·子卯 격각 통관손상·confidence 과대")이 operational
레이어로 전부 표면화: operational 火=조후보조신·水=조건부 희신/병(과다+한습+관살혼잡 합반/쟁합)·土=조건부
제살보조, 용신 木 operability 0.595. final/canonical/scoring은 전 구간 불변(operational 미소비 — 향후
scoring 연결은 별도, OPERATIONAL_ROLE_CLASS mapper 경유). **보류: Option A(관계 보정 기반 분포 재산정 —
distribution 차감→신강약/모델선택/final 변경)는 별도 이니셔티브(자체 스펙·전면 리베이스라인·승인) 대기.**

### 용신 작동역할 Phase 5a — operational → LLM 안전 노출 (2026-06-24)

YONGSIN_OPERATIONAL_ROLE_SPEC §10 Phase 5a(데굴님 승인 DP-5a1~3 + 추가조건 8). operational 레이어를
실서비스 응답에 처음 연결 — compact summary adapter + chart_interpretation surface + mapper 강제 + LLM 지침.
**점수·이벤트·final 불변(scoring-0)**.

- **수정(llm_input.py)**: YongsinOperationalSummary(원국 기준, primary_yongsin·operability·operability_level·
  factors·main_support·conditional·warnings) + ChartInterpretation.yongsin_operational_summary(None=fallback).
- **수정(operational_role_config.py)**: OPERABILITY_LEVEL_BANDS(low0.7/mid0.9, 표시용 밴드 — 확정등급 아님).
- **수정(chart_interpretation.py)**: build_yongsin_operational_summary(operational_roles→compact 요약,
  **OPERATIONAL_ROLE_CLASS mapper로 conditional 선별**·문자열 substring 파싱 금지; warnings deterministic
  우선순위 ①조건부 희신/병 ②용신 operability ③구조, _MAX_WARNINGS=3·_WARNINGS_CHAR_BUDGET=120 트림;
  구형/부분 결과 None fallback). manse_analysis config 직접 import(TODO: shared 이전 — 순환참조 없음).
- **수정(context_reducer.py)**: serialize_chart_prefix에 [작동 역할 — 원국 기준] compact 블록 추가(None 안전),
  _OPERATIONAL_INSTRUCTION 지침(canonical=정적 설명·실제 작동성은 작동역할 우선 참고·점수/이벤트는 엔진값
  그대로·조건부 희신/병≠단순 희신·조후보조신=보조약·operability 낮으면 작동성 약함) — summary 있을 때만.
- **효과**: 표준사례(1977-12-16 05:30 서울 = 丁巳/壬子/丁未/癸卯) chat dry-run 프리뷰에 작동역할 블록(용신 木
  작동성 낮음 0.595·火 조후보조신·水 조건부 희신/병·土 조건부 제살보조) + 지침 노출. canonical(水=희신·火=한신)도
  병기 — LLM이 정적/작동 둘 다 보고 정적만 낭독하지 않게. favorability_map/final/event score 불변 확인.
- **테스트**: test_yongsin_operational_summary.py 6종(요약 필드·mapper guard·fallback None·warnings 우선순위/
  예산·직렬화 블록+토큰 proxy·e2e 프롬프트+불변). 추가 char 217(≈130tok).
- 검증: unit 739 pass(+6)·1 skip, ruff·mypy clean(168). 잔여 2건 기존 DB 통합 환경 실패(무관).
- (다음) Phase 5b(운세 해석 operational 우선 규칙) 또는 #6 operability 확장(공망·충·합반·고립) — 승인 후.
  Option A는 spec §10-4 진입조건 충족 + 별도 승인까지 보류.

### 용신 작동역할 Phase 5b-1 — 운세 해석 operational guard + 5a token 압축 (2026-06-24)

YONGSIN_OPERATIONAL_ROLE_SPEC §10 Phase 5b-1(데굴님 승인 DP-5b1~4 + 추가조건 7). 운 입자 오행이 원국
operational role(조건부 희신/병·조후보조신·조건부 제살보조)이면 "단순 희신/기신운" 단정 방지. **explanation
only** — favorability/event score/랭킹/final 불변.

- **선행(5a token 압축)**: config OPERABILITY_FACTOR_SHORT(no_transmit→투간無·gyeokgak_zimao→子卯 격각),
  YongsinOperationalSummary.operability_factors_ko(프리픽스용 한국어), serialize_chart_prefix가 키 대신
  한국어 노출 → 추가 200자(≈115tok, 목표 ≤120 내). 키는 내부 summary에만.
- **수정(operational_role_config.py)**: LUCK_OPERATIONAL_GUARD(라벨별 guard 문구 — 조건부 희신/병=단순
  길운 금지·조후보조신=보조 긍정·조건부 제살보조=조건부 제어, experimental).
- **수정(chart_interpretation.py)**: natal_operational_role_map(원국 기준 {오행:operational_role}, 구형
  fallback {}). incoming_ten_god_note에 operational_map 인자(None=기존 canonical 동작 동일) — 인라인 태그
  "(水 희신 → 원국 작동: 조건부 희신/병)" + guard suffix "※ 운 水: …"(오행별 1회 dedupe). build_luck_grounding
  이 map 전달(단일 기간 운세 해석 블록).
- **수정(context_reducer.py)**: _OPERATIONAL_INSTRUCTION에 운 입자 1문장 추가(점수·판정 엔진값 유지).
  **후보별 note(_to_llm_candidate)는 operational guard 미적용** — 월별 overview 다수 후보 토큰 과증(12092>
  12000) 방지(조건 5/7), guard는 단일 기간 build_luck_grounding에만.
- **효과**: 표준 원국에서 水운(壬子) 유입 → 인라인 "원국 작동: 조건부 희신/병" + suffix "단순 길운 단정 금지";
  火운(丙午)→"조후보조신 … 기후·균형 보조"(긍정, 라벨별 문구 구분). favorability_map 불변, 월별 overview
  토큰 한도 내 통과.
- **테스트**: test_yongsin_luck_operational_guard.py 7종(map·水 조건부·None 동등·火 보조 긍정·build_luck_
  grounding·favorability 불변·운세 지침) + 5a 압축 단언 보강.
- 검증: unit 746 pass(+7)·1 skip, ruff·mypy clean(168). 잔여 2건 기존 DB 통합 환경 실패(무관).
- (다음) #6a operability 공망·충 확장 / #6b 합반·고립 / #7 官 외 합 → Phase 5b-2(운세 길흉 우선)·#9 shadow는
  후속. Option A는 spec §10-4 진입조건 + 별도 승인.

### 용신 작동성 #6a — 공망·충 operability (2026-06-24)

YONGSIN_OPERATIONAL_ROLE_SPEC §10 #6a(데굴님 승인 DP-6a1~4 + 추가조건 7). 용신 통근 지지의 공망·충만
**보수적**으로 operability penalty. operability 전용 — final/groups/strength/distribution/favorability/
event score/랭킹/relations 전부 불변.

- **수정(operational_role_config.py)**: OPERABILITY_PENALTY에 yongsin_void 0.20·yongsin_clash 0.15
  (experimental) + OPERABILITY_REASON·OPERABILITY_FACTOR_SHORT(공망/충) 추가.
- **수정(candidates.py)**: BRANCH_CLASHES 상수 재사용(relations 미수정). _yongsin_void_clash_factors —
  용신 통근 지지 수집 → **전부 공망일 때만** yongsin_void(solid root 1개라도 있으면 미적용·과발동 방지) /
  **용신 통근 지지가 六沖**일 때 yongsin_clash(원국 아무 곳 충 아님). 통근 없으면 둘 다 미적용(no_root만).
  _compute_yongsin_operability 4b(gyeokgak) 뒤 추가 — 순서 …→yongsin_void→yongsin_clash, round 1회.
- **효과**: 표준사례(卯 공망+未 solid) → solid 있어 void 미적용, 충無 → **operability 0.595 유지**(과발동
  방지·테스트 안정). void fixture(통근 전부 공망)→0.8, clash fixture(통근 충)→0.85.
- **테스트**: test_yongsin_operability_void_clash.py 7종(표준 미적용·void·clash·no_root 배타·helper 표적·
  순서·불변). 4a isolated fixture는 #6a 충에 걸려 충/공망 없는 차트로 교체(no_transmit·pyeonin 단독).
- 검증: unit 753 pass(+7)·1 skip, ruff·mypy clean(168). 잔여 2건 기존 DB 통합 환경 실패(무관).
- **교훈**: operability factor 추가 시 기존 'isolated' fixture가 신규 factor에 걸릴 수 있음 → 단독 factor
  fixture는 전 factor clean 조건으로 재탐색.
- (다음) #6b(합반·고립) → #7(官 외 합) → Phase 5b-2(운세 길흉 우선)·#9 shadow. Option A는 §10-4 진입조건.

### 용신 작동성 #6b-1 — 고립 operability (2026-06-24)

YONGSIN_OPERATIONAL_ROLE_SPEC §10 #6b-1(데굴님 승인 — 고립 정의 4조건 AND로 강화). 보수적 복합 고립만
operability penalty. operability 전용 — final/groups/strength/distribution/favorability/event score/랭킹/
relations 불변. (#6b-2 합반은 별도 단계.)

- **수정(operational_role_config.py)**: yongsin_isolation 0.15(experimental) + REASON·FACTOR_SHORT(고립).
- **수정(candidates.py)**: _yongsin_isolation_applies — **4조건 AND**(과발동 방지): ①present(투간 or 통근)
  ②생조부재(生용신 오행이 천간·지장간 어디에도 없음) ③단일출처(용신 출처 정확히 1 — 투간+통근 동시/통근
  2개+면 미적용) ④손상동반(yongsin_clash/yongsin_void/gyeokgak_zimao 중 ≥1). _compute_yongsin_operability
  6a 뒤 적용 — 순서 …→void→clash→isolation, round 1회. (factors 누적값으로 ④ 손상 판정.)
- **효과**: 표준사례(木 통근 2개·생조 水 충분) → ②③ 불충족 → 고립 미적용·**0.595 유지**. isolation fixture
  (金 용신·통근1·생조無·卯酉충) → no_transmit·clash·isolation 0.6141.
- **테스트**: test_yongsin_operability_isolation.py 5종(표준 미적용·복합적용·손상필수·다중출처/생조 시
  미적용·불변). helper 직접 단언으로 4조건 검증.
- 검증: unit 758 pass(+5)·1 skip, ruff·mypy clean(168). 잔여 2건 기존 DB 통합 환경 실패(무관).
- (다음) #6b-2(용신 합반 — resolve_stem_hap bind/contend, operability-only) → #7(官 외 합) → Phase 5b-2·
  #9 shadow. Option A는 §10-4 진입조건.

### 용신 작동성 #6b-2 — 합반 operability + operability 1차 체계 완성 (2026-06-24)

YONGSIN_OPERATIONAL_ROLE_SPEC §10 #6b-2(데굴님 승인 DP-6b2a~c + 추가조건 7). 용신 투출 천간이 bind/
contend로 묶일 때만 operability penalty. operability 전용 — final/groups/strength/distribution/
favorability/event score/랭킹/relations 불변.

- **수정(operational_role_config.py)**: yongsin_bound 0.15(experimental) + REASON·FACTOR_SHORT(합반).
- **수정(candidates.py)**: _yongsin_bound_factor(yongsin_el, pillars, canonical_roles) — ①용신 투출일 때만
  ②resolve_stem_hap(fav=canonical) 에서 bind 또는 contend AND affected element==용신 → True. **transform
  (合化 confirmed)·direction==away(합거) 제외**. _compute_yongsin_operability에 **canonical_roles 인자
  추가**(build_yongsin 호출부 전달) — isolation 뒤 적용. relations.py 미수정.
- **효과**: 표준사례 木 미투출 → bound 미적용·**0.595 유지**. bound fixture(金 투출·乙庚合 bind)→0.85.
- **테스트**: test_yongsin_operability_bound.py 5종(표준 미적용·bind 적용·**monkeypatch로 transform/away
  제외·bind/contend 적용 검증**·미투출 제외·불변). transform/away 실차트는 희귀→monkeypatch로 exclusion
  로직 직접 검증. #6a clash fixture가 #6b-2 bound와 겹쳐 clash-단독(합반無) 차트로 교체.
- 검증: unit 763 pass(+5)·1 skip, ruff·mypy clean(168). 잔여 2건 기존 DB 통합 환경 실패(무관).

**🎉 용신 operability 1차 체계 완성.** 작동성 손상 factor 8종: no_transmit·no_root·pyeonin_only(4a)·
gyeokgak_zimao(4b)·yongsin_void·yongsin_clash(6a)·yongsin_isolation(6b-1)·yongsin_bound(6b-2). 전부
operability 전용(감점형·≤1.0·순서 고정)·config experimental·LLM 압축 라벨(투간無/통근無/편인만/子卯 격각/
공망/충/고립/합반). 표준사례 0.595 일관 유지. **다음**: #7(官 외 합 맥락 확장 — 財/印/食傷/比劫)·Phase 5b-2
(운세 길흉 우선)·#9 shadow. Option A는 §10-4 진입조건+별도 승인.

### #7 官 외 합 맥락 확장 — 財/印/食傷/比劫 operational 주석 (2026-06-24)

YONGSIN_OPERATIONAL_ROLE_SPEC §10 #7(데굴님 승인 DP-7a~d, DP-7b 수정 — conditional은 unfavorable과
분리·note 중심). Phase 3 官殺 합 맥락을 나머지 십성으로 일반화. operational 주석 only — 라벨·세력·final
·scoring·랭킹·relations 불변.

- **수정(operational_role_config.py)**: TEN_GOD_HAP_REASON(財/印/食傷/比劫 도메인 라벨) + TEN_GOD_HAP_
  MODE_PHRASE(bind/contend/away/transform 공통 문구). OFFICER_HAP_REASON(官殺·Phase 3) 유지.
- **수정(candidates.py)**: _ten_god_hap_placement(role class별 배치 — **favorable=negative·unfavorable=
  positive(bind/away)·contend negative·conditional=note 중심(쟁합만 negative 병기)·neutral=note·transform
  =note only**) + _annotate_ten_god_hap_context(el2role 역인덱스로 affected element→십성, **官殺 제외**,
  _enrich_element 재사용 synthesized_by="ten_god_hap", dedupe). build_yongsin Phase 3 officer_hap 직후
  호출(model_map_adopted 게이트).
- **효과**: 표준사례 火(比劫·조후보조신=favorable) — 丁壬合 bind+contend → negative_when에 比劫 합반/쟁합,
  note synthesized_by += ten_god_hap. **水(官殺)는 officer_hap만**(ten_god_hap 미적용·중복 방지). 라벨
  (조후보조신·조건부 희신/병)·operability(木 0.595)·final **전부 불변**.
- **핵심 안전장치**: conditional role(조건부 희신/병·조건부 제살보조)은 unfavorable로 단정하지 않고 note
  중심(완화·지연 양면). DP-7b 수정 반영.
- **테스트**: test_yongsin_ten_god_hap.py 7종(배치 favorable/unfavorable/**conditional note중심**/neutral
  직접 단언·표준 比劫 enrich+官殺 미중복·불변·fallback 미누출). 배치는 helper 직접 단언으로 fixture 헌팅 회피.
- 검증: unit 770 pass(+7)·1 skip, ruff·mypy clean(168). 잔여 2건 기존 DB 통합 환경 실패(무관).
- **합 맥락이 전 십성(官殺 Phase3 + 財印食傷比劫 #7)으로 확장 완료.** 다음: Phase 5b-2(운세 길흉 판단
  operational 우선)·#9 shadow scoring. Option A는 §10-4 진입조건+별도 승인.

### #9a operational shadow scoring — 계산·검증 전용 (2026-06-24)

YONGSIN_OPERATIONAL_ROLE_SPEC §10 #9a(데굴님 승인 DP-9a1~5 + 추가조건 7). operational 기반 shadow 가중을
legacy와 병행 산출·diff 기록. **실제 scoring 미소비** — favorability_map/event score/운세 랭킹/final/
canonical 전부 불변. Phase 5b-2 전 완충 검증 단계(9b 후보 rank 관찰은 9a 검증 후).

- **수정(operational_role_config.py)**: SHADOW_ROLE_WEIGHT(experimental, legacy/shadow 공용 스케일) —
  용신 1.0 > 희신 0.6 > 조후보조신 0.35 > 조건부 제살보조 0.1 > **조건부 희신/병 0.0(★mixed·positive 금지)**
  ·한신 0.0 > 구신 -0.6 > 기신 -1.0. 모든 OperationalRole enum 매핑.
- **신규(saju_engines/shadow_scoring.py)**: operational_shadow_weights(operational_role→SHADOW_ROLE_WEIGHT
  exact lookup·fail-fast; **용신 element만 × operability**) + shadow_vs_legacy_diff(오행별 legacy_role/
  legacy_weight/operational_role/shadow_weight/delta). on-demand 함수만 — AggregatedYongsinResult 미저장·
  파이프라인 미연결.
- **효과**: 표준사례 diff — 木(용신 1.0 → ×0.595 작동성 → 0.595), **水(희신 0.6 → 조건부 희신/병 0.0,
  delta -0.6 — 단순 길신 처리 교정)**, 火(한신 0.0 → 조후보조신 0.35), 土(구신 -0.6 → 조건부 제살보조 0.1),
  金(기신 -1.0 유지). legacy favorability_map·event score 불변.
- **테스트**: test_shadow_scoring.py 7종(enum 전체 매핑·표준 golden 고정·조건부 희신/병=0 mixed·operability
  용신만·diff 전 필드+delta·**fail-fast KeyError**·legacy 불변).
- 검증: unit 777 pass(+7)·1 skip, ruff·mypy clean(169). 잔여 2건 기존 DB 통합 환경 실패(무관).
- (다음) **#9b**(이벤트/운세 후보에 shadow 적용→순위 변화 관찰, legacy 랭킹 불변) — 9a 검증 후. 그 뒤
  Phase 5b-2(운세 길흉 제한 적용, §9a 골든 검증 만족 시). Option A는 §10-4 진입조건+별도 승인.

### #9b 후보 단위 shadow 관찰 — 순위 변화 (2026-06-24)

YONGSIN_OPERATIONAL_ROLE_SPEC §10 #9b(데굴님 승인 DP-9b1~5 + 추가조건 7, 명칭 수정). 이벤트/운세 후보에
operational shadow 유불리를 적용해 legacy와의 차이·가상 순위 변화를 **관찰만**. 실제 score/event score/
운세 랭킹/favorability_map/final/polarity 전부 불변(미소비).

- **수정(operational_role_config.py)**: SHADOW_PERIOD_ELEMENT_WEIGHT(stem 0.5/branch 0.5, 지장간 미포함) +
  SHADOW_SCORE_SPAN 30.0(experimental). **둘 다 config·하드코딩 금지.**
- **수정(shadow_scoring.py)**: candidate_shadow_diff(result, candidates, ganji_by_period) — 후보 period→
  간지(caller 제공)의 천간·지지 표면 오행 평균으로 legacy_fav vs shadow_fav, fav_delta, **shadow_observation
  _score**(=clamp(score+fav_delta×SPAN) — **실제 score 아님·관찰 명칭**), reason(라벨 변경 또는 용신
  operability, ≤3). shadow_rank_diff(legacy_rank/shadow_rank/rank_delta/rank_changed — 가상 관찰만).
  #9a operational_shadow_weights 재사용. 파이프라인 미연결·미저장.
- **효과**(표준사례 운별 golden): 水運 fav_delta −0.6(조건부 희신/병 하향), 火運 +0.35(조후보조신 상향),
  木運 −0.405(용신 operability 0.595 하향·reason "木: 용신이나 작동성 0.595"), 土運 +0.7(조건부 제살보조
  완화), 金運 0.0(유지). 동일 legacy score에서 shadow 순위 재배열 관찰. legacy_score·favorability_map 불변.
- **핵심 명칭**: shadow_observation_score(≠score) — 발생 가능성/유불리 분리 보존(데굴님 수정).
- **테스트**: test_shadow_scoring_candidate.py 7종(운별 fav_delta golden·결합값·reason 라벨/operability·
  조건부 희신/병 하향·rank 관찰·간지없음 skip·legacy 불변).
- 검증: unit 784 pass(+7)·1 skip, ruff·mypy clean(169). 잔여 2건 기존 DB 통합 환경 실패(무관).
- **#9(a+b) 완료 — operational shadow scoring 체계.** 다음: Phase 5b-2(운세 길흉 operational 제한 적용 —
  §9 골든 검증 만족 시: 조건부 희신/병 단순 길신화 안 됨·조후보조신 과대 안 됨·낮은 operability 용신운 과대
  안 됨·랭킹 변화 과도하지 않음). Option A는 §10-4 진입조건+별도 승인.

### Phase 5b-2a 운세 길흉 표현 제한 (clamp, 점수 불변) (2026-06-24)

YONGSIN_OPERATIONAL_ROLE_SPEC §10 Phase 5b-2a(데굴님 승인 DP-5b2a1~5 + 보완조건 3). operational
워크스트림 중 **처음으로 실제 답변 출력에 영향** — 단 점수 교체가 아니라 **길흉 표현 강도만 clamp**.
score/rank/favorability_map/final/canonical/polarity 전부 불변.

- **수정(operational_role_config.py)**: EXPRESSION_BAND 0.3·EXPRESSION_OPERABILITY_THRESHOLD 0.9·
  EXPRESSION_GUIDANCE(등급별 1줄, experimental).
- **수정(shadow_scoring.py)**: _element_expression_class(legacy 밴드×shadow 가중 — **조건부 희신/병 등은
  '길' 승격 금지**)·_merge_expression(천간·지지 다르면 보수 병합)·luck_expression_clamp(운 간지 표현 등급 +
  용신 operability<0.9 부기). 등급: 길/조건부·유보/조건부·유보+주의/보조 긍정/주의 속 일부 완화/주의/주의·흉/
  중립. #9 weights 재사용.
- **수정(chart_interpretation.py build_luck_grounding)**: pillar_line에 [표현 제한] 1줄 append(단일 기간
  블록만 — 후보 다수 경로 미영향). "(점수·순위 불변)" 자체 표기.
- **효과**(표준 운별): 水運 조건부·유보(단순 길운 금지), 火運 보조 긍정(주용신급 아님), 木運 길+작동성 낮음
  부기(0.595), 土運 주의 속 일부 완화, 金運 주의/흉. 혼합 간지(壬午)는 보수 병합→조건부·유보.
- **토큰**: _OPERATIONAL_INSTRUCTION에 directive 추가는 월별 overview(12000 한도 임박)를 초과시켜 제거 —
  [표현 제한] 라인 자체가 자기설명적이라 directive 불요(period fortune에만 노출).
- **테스트**: test_luck_expression_clamp.py 7종(운별 등급·**조건부 희신/병 길 승격 금지**·보수 병합·operability
  부기·build_luck_grounding 노출·favorability 불변·프롬프트 [표현 제한]).
- 검증: unit 791 pass(+7)·1 skip, ruff·mypy clean(169). 잔여 2건 기존 DB 통합 환경 실패(무관). 월별 overview
  토큰 통과 재확인.
- **원칙**: operational shadow는 점수를 바꾸지 않고 과한 길흉 단정을 막는 문장 안전장치로만(데굴님). 다음:
  Phase 5b-2b(일부 도메인 제한 반영)·shadow 누적 후 scoring 반영 판단. Option A는 §10-4 진입조건.

### operational 워크스트림 안정화·정리 (Phase 0~5b-2a) (2026-06-24)

데굴님 지시 — 5b-2b 확장 전, 첫 출력 영향 단계(5b-2a)의 회귀 기준 고정. **새 기능 구현 없음·문서 갱신만.**

- **산출물**: YONGSIN_OPERATIONAL_ROLE_SPEC.md §11 "통합 정리" 신규 — ①Phase별 변경 요약(출력 영향
  표기) ②전 구간 불변 원칙(final·canonical_roles·favorability_map·score·rank·polarity·groups·신강약·
  모델선택) ③레이어 역할 구분(canonical/operational/operability/hap context/shadow/expression clamp)
  ④표준사례 golden 표(canonical·operational·shadow weight·운별 expression) ⑤token budget 회귀 기준
  (월별 overview 12000 임박·_OPERATIONAL_INSTRUCTION 추가 금지·단일 기간 블록만·데이터 라인 자기설명)
  ⑥Phase 5b-2b 진입 조건(golden 안정+도메인 문구 매핑 선설계+토큰 검증) ⑦rollback/disable 검토.
- **rollback 검토 결과(미구현)**: 첫 출력 영향(5b-2a)은 config 플래그 EXPRESSION_CLAMP_ENABLED(default
  True)를 build_luck_grounding [표현 제한] append 게이트로 두면 즉시 off 가능(코드 1곳·테스트 1건 저비용).
  shadow/operational 산출은 미소비라 별도 토글 불요. 필요 시 다음 작업으로 추가 가능.
- **operational 레이어 1차 MVP 완료**(Phase 0~5b-2a). 회귀 픽스처: test_yongsin_operational*·operability*·
  ten_god_hap·shadow_scoring*·luck_expression_clamp(현행 unit 791 pass 기준). 코드 무변경.
- (다음 후보) Phase 5b-2b(도메인별 표현 제한 — §11-6 조건 충족 후)·shadow 누적 기반 scoring 반영 판단·
  EXPRESSION_CLAMP_ENABLED rollback 플래그. Option A는 §10-4 진입조건+별도 승인.

### EXPRESSION_CLAMP_ENABLED rollback 플래그 (Phase 5b-2a 안전장치) (2026-06-24)

데굴님 지시 — 5b-2b 도메인 확장 전, 첫 출력 영향 기능(5b-2a 표현 제한)을 즉시 off 할 안전장치. 새 해석
기능 없음.

- **수정(operational_role_config.py)**: EXPRESSION_CLAMP_ENABLED = True(experimental). False면 [표현 제한]
  라인 미노출(즉시 off).
- **수정(chart_interpretation.py build_luck_grounding)**: [표현 제한] 라인 생성을 _op_config.EXPRESSION_
  CLAMP_ENABLED로 게이트(config 모듈 참조 — 런타임 토글 가능). False면 luck_expression_clamp 미호출.
- **불변**: shadow_scoring(luck_expression_clamp 등) 계산 자체는 플래그 무관 유지. score/rank/
  favorability/final/polarity/event score 전부 불변(소비처 1곳만 게이트).
- **테스트**: test_expression_clamp_rollback.py 4종(default True·on 노출·off 미노출·플래그 무관 shadow
  계산 동일). monkeypatch ci._op_config로 토글.
- 검증: unit 795 pass(+4)·1 skip, ruff·mypy clean(169). 잔여 2건 기존 DB 통합 환경 실패(무관). spec §11-7
  rollback 검토를 구현으로 전환(미구현→구현).
- (다음) Phase 5b-2b(도메인별 표현 제한 — §11-6 진입 조건: 직업/재물/연애/이동/학업 문구 매핑 선설계 후)·
  shadow 누적 후 scoring 반영 판단. Option A는 §10-4 진입조건+별도 승인.

### Phase 5b-2b 도메인별 표현 제한 (번역 레이어, 점수 불변) (2026-06-24)

YONGSIN_OPERATIONAL_ROLE_SPEC §12(데굴님 승인 DP-5b2b1~5 + impl1~3 + 보완 7조건). 5b-2a
expression_class를 **도메인 언어로 번역만** — 해석·점수 변경 아님.

- **수정(operational_role_config.py)**: EXPRESSION_CLASSES(6 정규 등급)·DOMAIN_EXPRESSION_PHRASE
  (career/wealth/relationship/relocation/study_document × 6, §12-2 순화 확정 — "관재"·"이별"·"투자 유리"
  강한 표현 배제). 도메인×등급만(십성 하드코딩 금지 — 십성은 5b-1 운 line 담당).
- **수정(shadow_scoring.py)**: domain_to_expression_key(Domain.value str→key, lowercase normalize,
  education→study_document, GENERAL/미상/health→None)·domain_expression_phrase(미상/미매핑→base
  fallback, 등록 domain+등급 누락→KeyError fail-fast, 변형 등급 +주의/주의→정규 재사용). 파서 enum 비종속.
- **수정(chart_interpretation.py build_luck_grounding)**: domain_key: str|None=None 인자 추가(기존 호출부
  무영향). [표현 제한] guidance를 domain_expression_phrase로 치환(1줄·base→domain, 길이 유사·토큰 중립).
- **수정(chat_service.py)**: period fortune에서 domain_to_expression_key(intent.domain.value) 전달.
  후보 다수 경로(_to_llm_candidate) 미전달 — 미노출 유지.
- **효과**(표준 水運 조건부·유보): career=책임·압박·조직 이슈 동반 / wealth=계약·현실 부담 동반 /
  relationship=감정 과다·관계 압박 가능 / GENERAL·미상=base guidance. 운 입자 십성(水=官殺 등)은 5b-1
  line이 그대로 노출 — domain phrase 십성 무관.
- **안전장치**: EXPRESSION_CLAMP_ENABLED=False면 도메인 문구 포함 [표현 제한] 라인 전체 미노출(5b-2a
  게이트 그대로). domain 미상→graceful fallback.
- **불변**: score/rank/event score/favorability_map/final/canonical_roles/polarity 전부 불변(테스트 강제).
- **테스트**: test_domain_expression_phrase.py 8종(완전성·키 매핑·fallback·번역·fail-fast·도메인별 노출·
  rollback off·favorability 불변). build_luck_grounding 인자 확장.
- 검증: unit 1017 pass(+8)·18 skip, ruff·mypy clean(packages 169·chat_service). manse_service.py mypy 2건은
  HEAD 동일 기존 이슈(무관). 토큰 ≤12000(context_reducer) 유지. 잔여 2건 기존 DB 통합 환경 실패(무관).
- (다음) shadow 누적 후 scoring 반영 판단. Option A는 §10-4 진입조건+별도 승인.

### Shadow Validation Harness — scoring 반영 전 검증 도구 (2026-06-24)

데굴님 지시 — operational을 실제 점수에 반영할지 **감이 아니라 데이터로** 판단하기 위한 일괄 리포트
도구. spec §13. 새 해석 기능 없음·운영 미연결.

- **신규(data/shadow_charts/charts.jsonl)**: 골든 차트 9개(operational_std 익명 + golden manse 8). 20~30
  누적은 행 추가. **chart_id 익명·BirthInput 원본 리포트 미노출.**
- **신규(saju_engines/shadow_report.py, 순수)**: build_shadow_report(result, candidates, ganji_by_period,
  chart_id, period_level)→(rows 19컬럼, summary) + invariance_snapshot(Guard #6). candidate_shadow_diff
  /shadow_rank_diff/luck_expression_clamp 조합. **rank는 diffs 순서로 index 정렬(period 키 충돌 버그 수정 —
  동일 기간 복수 후보 rank 보존).**
- **신규(scripts/shadow_validation_harness.py, CLI)**: charts→calculate→score_legacy(YEAR+DAEWOON)→리포트
  →CSV/JSON + top-N. 옵션 --charts/--out-dir/--top-n/--dry-run. 월운 1차 제외(후속 optional).
- **수정(operational_role_config.py)**: SHADOW_WARN_SCORE_DELTA=18·SHADOW_WARN_RANK_DELTA=3(WARN 임계).
- **gitignore**: data/shadow_reports/*.csv|json(재생성). charts.jsonl은 추적.
- **Guard**: #1~5 PASS/WARN(리포트·top-N 리뷰용), #5=abs(score/rank_delta) 임계 WARN. #6 불변(favorability
  ·final·후보 score/polarity)·schema/config = hard fail. missing ganji(exact match 실패)=skip+집계, 전부
  skip=errors.
- **실행 결과**(9차트 633행): 불변 매 차트 통과(위반 0). WARN 분포 — india/japan/us 0건(shadow≈legacy),
  uk_london score 57·rank 58(대운 큰 shift), operational_std rank 60. score_delta는 운 간지 단위(동일 기간
  복수 event 동일). **주의: rank는 YEAR+DAEWOON 혼합 전역 풀 — 대운 shift가 전역 순위 크게 흔듦. 레벨별
  랭킹은 후속 옵션.**
- **테스트**: test_shadow_report.py 8종(행 스키마·level·operational 요약·guard #1/#3/#5·불변 #6·missing
  skip·전부 skip errors). CLI는 --dry-run smoke.
- 검증: unit pass(+8·총 1033), ruff·mypy clean(packages+harness 171). 잔여 2건 기존 DB 통합 환경 실패(무관).
- **결론 도구**: 누적 리포트(20~30 차트)로 scoring 반영 여부 판단. 본 harness는 검증 전용·운영 미연결.

### Shadow Harness 레벨별 랭킹 보정 + YEAR 후보 materialize (2026-06-24)

데굴님 지시 — YEAR+DAEWOON 혼합 전역 랭킹 착시 제거. spec §13-2b.

- **수정(shadow_scoring.shadow_rank_diff)**: level_by_period 옵션 추가 → 전역(_global)+레벨별(_level)
  순위 동시. _rank_maps 헬퍼로 풀별 순위. **하위호환**: level 미지정 시 기존 키만 반환(기존 테스트 불변).
- **수정(shadow_report.py)**: REPORT_COLUMNS 에 legacy/shadow/rank_delta _global·_level 6필드(기존 단일
  rank 3필드 대체). **rank WARN 은 rank_delta_level 기준**(착시 제거). score_delta WARN 유지.
- **수정(scripts/harness)**: 버그 발견 — 기본 calculate 는 yearly_luck=0(대운만). YEAR 후보가 0이라
  레벨 비교 불능이었음. **score_legacy_years + daewoon_table[].sewoon(장년기 20~60세, --year-window
  기본 20)로 YEAR materialize.** dw_cands(score_legacy DAEWOON) + yr_cands 결합. top-N/표시 _level 기준.
- **실측(9차트 2778행)**: level year 2145·daewoon 633. **level≠global delta 1439행, 전역 WARN→레벨
  非WARN 180행(착시 제거 입증).** 불변 매 차트 통과. 신호 편차 큼 — india/japan/us 무변 vs uk_london
  score106·rank287.
- **관찰(후속)**: YEAR 풀이 커(≈240/차트) abs rank_delta≥3 임계 과민·WARN 범람(290/319). **rank WARN
  임계 상대화(비율·percentile) 필요 — 후속 튜닝.** score_delta WARN 이 더 안정.
- **테스트**: test_shadow_report.py +1(test_level_aware_ranking — 합성 YEAR5+DAEWOON5, 레벨 내 1~5·전역
  1~10·대운 level<global 착시 보정). 기존 test_shadow_scoring_candidate(no-level 경로) 불변.
- 검증: unit pass, ruff·mypy clean(171). 잔여 2건 기존 DB 환경 실패(무관).
- (다음) rank WARN 임계 상대화(후속 튜닝 옵션) → 차트 20~30 누적 → scoring 반영 판단.

### Shadow Harness rank WARN 임계 상대화 (2026-06-24)

데굴님 지시 — 큰 YEAR 풀(≈240) 과민 WARN 제거. spec §13-3b.

- **수정(operational_role_config.py)**: SHADOW_WARN_RANK_DELTA → SHADOW_WARN_RANK_DELTA_ABS(3)·
  SHADOW_WARN_RANK_DELTA_RATIO(0.05).
- **수정(shadow_report.py)**: level_pool(레벨별 후보 수) 산출 → threshold = max(ABS, ceil(pool×RATIO)),
  abs(rank_delta_level) ≥ threshold 면 WARN. REPORT_COLUMNS +3(level_pool_size·rank_delta_pct·
  rank_warn_threshold). score_delta WARN·global rank 참고용·불변 전부 유지.
- **효과(9차트 2778행)**: 대운 풀(≈70)→임계 4, 세운 풀(≈240)→12~13. **rank WARN 91%→33%(929행)** —
  korea 229→26·lunar 237→51(잔흔 제거)·zi_hour 260→182, uk_london 268·operational_std 190 유지(실 영향).
- **테스트**: test_shadow_report.py +1(test_rank_warn_threshold_scales_with_pool — 작은 풀 5→임계 3·큰 풀
  100→임계 5·잔흔 비-WARN·rank_delta_pct 존재). 총 10종.
- 검증: unit pass, ruff·mypy clean(171). 잔여 2건 기존 DB 환경 실패(무관).
- **Shadow Validation Harness 최종 안정화 완료.** (다음) 차트 20~30 누적 → scoring 반영 판단.

### Shadow 차트 구조 coverage — 합성 명식 탐색 24 구조 (2026-06-24)

데굴님 지시 — scoring 반영 전, operational shadow 가 다양한 구조에서 과발동/미발동 안 하는지 coverage
확보. 1차=합성/검증 명식(실데이터는 2단계 golden_events 분리). spec §13-5.

- **신규(saju_engines/shadow_chart_predicates.py)**: 엔진 산출 바인딩 predicate primitive(strength band·
  five_elements%·ten_gods groups·operational_roles 라벨·operability_factors·transform·geokguk +
  expected_shadow·invariant_additive). Pred(name,fn) — coverage_report satisfied/missing 표기.
- **신규(saju_engines/shadow_chart_specs.py)**: 24 ChartSpec(그룹 1~7). required/critical/preferred/
  expected_shadow/invariants/best_match_allowed. hap_confirmed_01=transform note only·final/groups/분포/
  scoring 불변(invariant). yongsin_bound_01(operability factor)·hap_bind_01(일반 합 맥락) 분리. 특수격은
  best_match_allowed.
- **신규(scripts/find_shadow_charts.py)**: deterministic stratified sweep(1950–2009×월×일{3,13,23}×12시지×
  성별, 연도 innermost). **distinct-birth 우선**(폴백으로 커버리지 보장). FOUND(required 전부)/BEST_MATCH
  (critical+2/3)/NOT_FOUND. charts.jsonl 추가 + coverage_report.json manifest(timestamp·경로·로그 제외).
- **수정(operational_role_config.py)**: SHADOW_WARN 주석.
- **결과**: FOUND 22(distinct birth 22)·NOT_FOUND 2(종격/전왕 — 그리드 미확보, 2차 확장 후속). charts.jsonl
  9→31. harness 31차트 9475행 **불변 매 차트 통과**. **coverage 가드 G1/G3/G4 위반 0**(조건부 희신/병 미승격·
  저operability 용신 미과대·제살보조 미과승격) — score 편차는 구신/기신 de-penalize·조건부 희신/병 downgrade
  의 의도된 보정.
- **산출물**: charts.jsonl·coverage_report.json 커밋(manifest). shadow_reports/·search_logs/ gitignore.
- **테스트**: test_shadow_chart_specs.py 5종(spec 수·critical⊆required·hap_confirmed note-only·bound/bind
  분리·predicate 표준차트 평가). unit 818 pass.
- 검증: ruff·mypy clean(174). 잔여 2건 기존 DB 환경 실패(무관).
- (다음) 2차 확장(종격/전왕 그리드 확대)·도메인 snapshot 분리·shadow 누적 후 scoring 반영 판단.

### Phase 5b-2b 도메인 출력 snapshot 분리 (2026-06-24)

데굴님 지시 — scoring 반영 전, 5b-2b domain_key×expression_class 번역이 chat/period fortune 경로에서
안정 노출되는지 고정. 명식 구조 coverage(shadow_charts)와 분리. scoring 무관·불변.

- **신규(tests/unit/test_domain_snapshot.py)** 9종: ①adapter wiring(Domain.value→key, GENERAL→None)
  ②도메인×水運 정확 문구 5종(chat_service:466-467 동일 체인 — career=책임·압박·조직 이슈 동반 등)
  ③5 운별 base 등급(水 조건부·유보·火 보조 긍정·木 길+작동성·土 주의 속 일부 완화·金 주의/흉)
  ④GENERAL/None→base fallback ⑤flag off 라인 미노출 ⑥chat 경로 [표현 제한] 노출 ⑦chat flag off
  ⑧후보 다수 경로 미노출(라인 ≤1회) ⑨domain 무관 favorability/final 불변.
- **구조 근거**: build_luck_grounding(domain_key=) 호출처는 chat_service:467 **단일**(period fortune)
  — 후보 다수 경로 구조적 미노출 확인.
- 검증: unit 827 pass(+9), ruff·mypy clean(172). 잔여 2건 기존 DB 환경 실패(무관).
- **operational 출력 레이어 고정 완료**(설명→작동성→합→shadow→표현제한→rollback→도메인번역→snapshot).
- (다음) 종격/전왕 2차 확장 best-effort → scoring 반영 설계안(SCORING_OPERATIONAL_SHADOW_ENABLED=False
  기본·제한 도메인부터).

### 종격/전왕 2차 확장 — coverage 24/24 완료 (2026-06-24)

데굴님 지시 — 1차 NOT_FOUND 2건(jonggyeok/jeonwang) best-effort 확보. 억지 주입 금지. spec §13-5-4.

- **원인 규명**: 종격/전왕은 엔진이 산출함(geokguk.special_pattern). 1차가 못 찾은 건 days {3,13,23}
  한정 탓 — 확장 days {1,6,11,16,21,26} 2160샘플에 전왕 75·종격 52 다수.
- **수정(shadow_chart_predicates.py)**: special_pattern_type(t) 신규 — special_pattern.type 'follow'(종격)/
  'dominant'(전왕·일행득기)로 판정(종혁격을 '종'으로 오분류하던 키워드 매칭 폐기). geokguk_special 은 dict
  name 안전 접근.
- **수정(shadow_chart_specs.py)**: jonggyeok_01=special_pattern_type('follow'), jeonwang_01=('dominant').
- **수정(find_shadow_charts.py)**: 2차 확장 CLI(--days/--year-start/--year-end/--only). --only 시 비대상
  spec 은 기존 coverage_report 병합 보존. prior 레코드 birth 없음 → 표시·write .get 가드.
- **결과**: jonggyeok_01(1950-01-01 follow)·jeonwang_01(1953-01-01 dominant) **FOUND**. coverage **24/24
  FOUND·NOT_FOUND 0**. charts.jsonl 31→33(distinct 24 구조 + 기존 9).
- **harness 33차트 10066행**: 불변 매 차트 통과. 종격/전왕 WARN(0,0)(극단 단일오행 shadow≈legacy·과발동
  없음). **coverage 가드 G1/G3/G4 위반 0**(33차트).
- **테스트**: test_shadow_chart_specs.py +1(special_pattern_type — charts.jsonl jonggyeok/jeonwang birth
  regression + 표준차트 정격). 총 6종.
- 검증: unit pass, ruff·mypy clean(174). 잔여 2건 기존 DB 환경 실패(무관).
- (다음) **scoring 반영 설계안** — SCORING_OPERATIONAL_SHADOW_ENABLED=False 기본·제한 component(조건부
  희신/병 downgrade·저operability 용신 보정)부터.

### Scoring Phase 1a — operational adjusted score (감점·산출만) (2026-06-24)

데굴님 지시 — operational shadow 를 scoring 에 최소 위험 반영(감점 2 component). spec §14. **flag off
byte-identical·랭킹/LLM 미반영·1a 산출만.**

- **수정(operational_role_config.py)**: SCORING_OPERATIONAL_SHADOW_ENABLED=False(마스터)·
  SCORING_OPERATIONAL_COMPONENTS{conditional_byeong_downgrade·low_operability_yongsin}=False·
  SCORING_OPERATIONAL_COEF(byeong12·low_op10·op_threshold0.9·floor0.5, experimental).
- **신규(saju_engines/scoring_operational.py)**: apply_operational_scoring(순수 — component flag·계수만,
  마스터 미참조) + operational_scoring_sidecar(마스터 게이트 wrapper, off→None). **sidecar=candidate
  index 기반 list**(데굴님 지시 — (period,event_key) 키 폐기·충돌 방지). A=조건부 희신/병 downgrade
  (legacy_fav>0만), B=낮은 operability 용신(용신 오행만). #9b 표면 오행(stem0.5/branch0.5). adjusted=
  clamp(legacy−A−B, ceil(legacy×0.5), legacy)·delta≤0·penalties 양수. missing ganji→skip 명시(임의 계산
  금지).
- **chat_service·EventCandidate 미변경**(byte-identical 구조 보장) — 라이브 service 삽입·랭킹 교체는 1b.
- **검증**: test_scoring_operational.py 11종(flag off None·index 정렬·단조성·바닥·A/B 게이트·둘 off 0·
  missing·불변·**EventCandidate 스키마 미변경**·후보 비변형). 33차트 flag-on 2271 rows 단조성·바닥 위반 0·
  coverage 가드 G1/G3/G4 위반 0. unit 839 pass, ruff·mypy clean(173). 잔여 2건 기존 DB 환경 실패(무관).
- (다음·후속 분리) 1b: 제한 조건 adjusted_score 랭킹 실험(별도 sub-flag)·service 삽입. 1c: 도메인/intent
  실제 적용. 계수 33차트 튜닝. Option A 보류(§10-4).

### Scoring 1a 계수 튜닝 리포트 (2026-06-24)

데굴님 지시 — Phase 1b 전, 계수(byeong12·low_op10·floor0.5) 체감 강도 33차트 분포 확인. **실제 .score·
랭킹 불변·리포트용.**

- **신규(scripts/scoring_tuning_report.py)**: 33차트 flag-on sidecar(YEAR+DAEWOON) 집계 — component별
  감점 분포·total delta·floor hit·차트별·level별·가상 rank shift·top-N·A+B 중복. 재실행 가능.
- **결과(채점 10066)**: A 감점 n=783 mean6.2 p50/p90=6 max12(단일 0.5→6, 양면→12). B 감점 n=1850 mean1.3
  p90=2 max4(매우 완만). total |delta| mean3.0 p90=6 max12. **floor hit 13/10066=0.1%(무난<3%)** — 계수
  과하지 않음(소멸 없음). 가상 rank(level) year p90=10 max50·daewoon p90=3 max16, rank WARN 760. A+B
  중복 158(6%). top 감점은 yongsin_gyeokgak_zimao_01 2032(양면 조건부 희신/병 −12).
- **계수 제안(1a 유지 권장)**: floor hit 0.1%·delta 완만 → **byeong12·low_op10·floor0.5 유지**. 단 B(low_op)
  매우 완만(mean1.3) — 1b 랭킹 실험에서 B가 거의 안 물리면 low_op_max_penalty 14~15 상향 검토. A는 적정
  (90% ≤6, 양면 신호만 12). floor 0.5 backstop 미발동(0.1%)이라 distortion 없음.
- 검증: ruff clean. 산출 console only(파일 미저장).
- (다음) 계수 확정(유지) → Phase 1b adjusted rank 실험 설계(별도 sub-flag).

### Scoring Phase 1b — adjusted rank 실험 (랭킹 미교체·관찰) (2026-06-24)

데굴님 지시 — 1a sidecar(adjusted_score)로 가상 랭킹 흔들림 관찰·low_op 10 약함 판단. spec §14-8.
**실제 .score·rank·reduce_candidates·LLM 불변.**

- **수정(config)**: SCORING_OPERATIONAL_RANK_EXPERIMENT_ENABLED=False(독립 sub-flag)·RANK_TOPN=10.
- **수정(scoring_operational.py)**: apply_operational_scoring(*, components, coef_override) 키워드 추가
  (config 불변·주입만). adjusted_rank_experiment(legacy=입력순서·재계산 금지, adjusted=adjusted_score
  stable 재정렬·tie=legacy order, level 분리·global 참고) + rank_experiment_sidecar(sub-flag 게이트).
  missing ganji 후보 유지(adjusted=legacy·풀 보존).
- **confound 발견·해결**: legacy_rank(=score_legacy 입력순서=lei_rank_key) ≠ score순서 → penalty 0에서도
  rank 50/72 이동(검증). rank_delta_level(vs 엔진순서)는 confound 포함 → **op_rank_delta_level(score
  베이스라인 대비) + op_left_topn 신설**로 순수 operational penalty 효과 격리.
- **신규(scripts/scoring_rank_experiment.py)**: 33차트 A-only/B-only/A+B + low_op 10/14/15(B-only·A+B)
  op_rank_delta 분포·top-N 이탈·차트별 max. console.
- **결론(op_rank_delta)**: A-only year mean2.38 p90=11·B-only 0.99 p90=3·A+B 2.70(**A 지배·B 약함**, p50=0
  =대부분 무영향). low_op 10→14→15 B-only mean 0.82→1.03→1.06(미미·topN 이탈 10→12). **B는 14 상향해도
  랭킹 영향 경미 → low_op=10 유지 타당**(B 의도적 보조 효과). 차트별 max: jesal 50·gyeokgak 45(양면 조건부
  희신/병 집중).
- **검증**: test_scoring_rank_experiment.py 10종(sub-flag off None·legacy=입력순서·tie-break·level 분리·
  component 분기·coef_override+config 불변·top-N 이탈·missing 유지·불변). unit 849 pass, ruff·mypy clean.
  잔여 2건 기존 DB 환경 실패(무관).
- (다음) low_op 계수 결정(10 유지 권장) → Phase 1c(제한 도메인/intent 실제 적용) 설계. Option A 보류.

### Scoring Phase 1c-α — rank guard 태그 (순위·score 불변·career 한정) (2026-06-24)

데굴님 지시 — operational scoring 첫 실제 적용. lei_rank_key 보존·후보 단위 과대해석 방지 태그만(순위
변경 금지). spec §14-9. **첫 LLM 출력 영향 scoring 적용.**

- **수정(config)**: SCORING_OPERATIONAL_APPLY_ENABLED=False(마스터)·APPLY_MODE{rank_guard,near_tie_
  demotion}·APPLY_INTENTS=["career"]·APPLY_COEF(penalty_threshold6·max_guards3·near_tie 1c-β용 미사용)·
  GUARD_PHRASE(penalty 유래 2종·짧게).
- **신규(scoring_operational.py)**: operational_rank_guards — 게이트 조합 전부(APPLY_ENABLED ∧ rank_guard
  ∧ domain∈career(normalize) ∧ component≥1) 만족 시만. reduce 후 selected 에 apply_operational_scoring
  재산출(index 1:1) → delta≤−6 후보, 감점 큰 순 max3, 우세 penalty 1줄. missing ganji 미부착(임의 계산 X).
- **수정(context_reducer.py)**: build_llm_input llm_candidates 매핑 직후 caution_note append(기존 필드·
  스키마 불변). flag off→루프 0회→byte-identical.
- **검증**: byte-identical — master off·非career(general) 출력 동일 확인. career+on → [해석 주의] 태그 2개
  (≤3)·+56자. token: 올해 직업운 8412·이번달 직업운 10385 ≤12000. 33차트 가드 G1/G3/G4 위반 0(산출 flag
  무관). test_scoring_apply.py 9종(master/mode/domain/component 게이트·max3·reason 출처·조후보조신/제살보조
  무태그·missing 미부착). unit 858 pass, ruff·mypy clean. 잔여 2건 기존 DB 환경 실패(무관).
- **불변**: .score·실제 rank·reduce 순서·final·favorability_map·canonical_roles·polarity 전부 불변.
- (다음·후속) career 운영 관찰 → wealth 등 intent 확대 / Phase 1c-β near-tie demotion(별도 승인). 계수
  유지(1b 결론). Option A 보류(§10-4).

### Scoring 1c-α career 운영 관찰 리포트 (2026-06-24)

데굴님 지시 — wealth 확대·near-tie 전, career rank guard 작동 양상 관찰. **기능 변경 없음·관찰 전용.**

- **신규(scripts/scoring_guard_observe.py)**: 33차트 career guard 부착 샘플·reason 분포·caution_note
  append 자연성·과발동/미발동·과장단어 점검. console only.
- **관찰 결과(총 guard 21, 7/33 차트)**:
  ① **reason 분포 = conditional_byeong_downgrade 21 / low_operability_yongsin 0** — **B는 1c-α에서 한 번도
     발동 안 함**(B max penalty ≈4 < threshold 6). 즉 현 임계에서 1c-α는 사실상 "조건부 희신/병 과대평가
     방지 태그"(A 전용). 1b 결론(B 약함)과 일치.
  ② **과발동 0**(차트당 ≤3·max_guards 준수)·**미발동 26/33 차트**(조건부 희신/병 운 없는 차트는 무태그) —
     적절히 선택적.
  ③ **과장 단어(흉/나쁨/위험) 0** — "과한 긍정 금지"로만 작동(흉 단정 아님).
  ④ **기존 caution_note 존재 17/21** — 대부분 기존 주의문("좋은 달로 과하게 단정 말 것" 등) 뒤에 append.
     메시지 방향 일치(둘 다 과대긍정 차단)이나 **경미한 의미 중복** 존재(관찰 메모 — 차단 아님).
  ⑤ token: 직업운 off 8372 → on 8412(+40·2태그)·≤12000. non-career(general) on==off(미적용)·APPLY off
     byte-identical 재확인.
- **판단**: 1c-α career 작동 안정. **임계 −6에서 B 미발동은 의도된 보수성**(B는 표현 레이어로 충분). 경미한
  중복은 운영 리뷰 후 필요 시 조정. 검증: ruff·mypy clean, unit 858(기능 무변). 잔여 2건 기존 DB(무관).
- (다음·후속·별도 승인) career 실사용 관찰 누적 → wealth/relationship 확대 설계 / 1c-β near-tie demotion.

### Scoring 1c-α caution 중복 정리 + intent 확대 검증 (2026-06-24)

데굴님 지시(정확도 마무리) — ① guard 문구 중복 정리 ② intent 확대 검증 리포트. **score/rank/reduce 불변.**

**① caution 중복 정리(구현)**
- 수정(config): SCORING_OPERATIONAL_GUARD_PHRASE_COMPACT(reason만)·SCORING_OPERATIONAL_REDUNDANCY_
  MARKERS(과하게 단정·과한 긍정·단정하지 말·단정 말·좋은 달로·좋은 흐름으로 단정 — "좋은" 단독 금지).
- 수정(scoring_operational.py): operational_rank_guards 반환 (idx, reason_key)로 변경 +
  guard_caution_phrase(기존 caution 마커 有→compact·지시문 중복 제거, 無→full). **engine 텍스트 재작성
  안 함.**
- 수정(context_reducer.py): caution_note append 시 guard_caution_phrase 경유.
- 효과: "…좋은 달로 과하게 단정 말 것" + "[해석 주의] 조건부 희신/병"(compact·지시문 1회). "검토월"류
  (마커 無)는 full 유지(방향 다름).
- 테스트: test_scoring_apply.py +1(compact/full)·기존 reason_key 전환. unit 859.

**② intent 확대 검증 리포트(scripts/scoring_guard_intent_report.py)**
- 대표 3차트 × 5 intent in-process 일시 적용(config default 불변)·실 chat 경로. **guard 문구 자체 과장단어
  0(config 보장).**
- 결과: **career tags6 max2 +40 절단0(안전)** · **wealth tags3 max1 +19~20 절단0(안전)** ·
  **relationship tags1 tokΔ−1384 절단1(★토큰예산 초과→본문 1384토큰 절단 위험)** · relocation/study tags0
  (질문이 후보 경로/도메인 라우팅 안 됨). reason 전 intent conditional_byeong_downgrade(B 미발동).
- **★핵심 발견**: career(배포 파일럿)는 33차트 전부 +태그만(절단 0·안전). 그러나 **relationship 등 근접-
  ceiling 프롬프트에서 +태그가 토큰예산을 넘겨 본문이 절단됨**. → **intent 확대 전 토큰 헤드룸 처리 필요**
  (태그용 예산 예약 또는 ceiling 근접 시 미부착). career/wealth는 헤드룸 충분으로 안전.
- 검증: ruff·mypy clean(173)·unit 859. chat 결정적(off 2회 동일) 확인. 잔여 2건 기존 DB(무관).
- (다음) **토큰 헤드룸 가드 설계**(절단 방지) → wealth 운영 적용 검토(절단0) → relationship 은 헤드룸 가드
  후. near-tie demotion·Option A 보류.

### Scoring 토큰 헤드룸 가드 — guard 태그 본문 절단 방지 (2026-06-24)

데굴님 지시(정확도 마무리) — rank guard 태그가 토큰예산을 넘겨 본문 재축소(절단)를 유발하던 문제 해결.
**본문 우선·태그 후순위.** spec §14-9. score/rank/reduce/final/favorability 불변.

- **원인**: serialize_with_guard 가 over-budget 시 event_candidates[:3]·evidence[:3]·excerpts[:4]로
  재축소 → relationship+kansal 에서 +태그 1개가 본문 −1384토큰 절단.
- **수정(config)**: SCORING_OPERATIONAL_GUARD_TOKEN_EST=25(폴백)·HEADROOM_RESERVE=1500(reserved_tokens
  미전달 시 system+trailing 보수 예약).
- **수정(context_reducer.build_llm_input)**: rank guard 적용을 llm_candidates 매핑 직후 →
  **payload 조립 후 _apply_rank_guards** 로 이동(전체 본문 토큰 측정 가능). reserved_tokens 인자 추가
  (chat_service 의 reserve 는 trailing 이 build_llm_input 뒤에 만들어져 전달 불가 → HEADROOM_RESERVE
  폴백). headroom = max_input_tokens − base(태그없는 본문) − reserve. **phrase 실토큰 순차 차감**(full/
  compact 반영)·헤드룸 부족 시 미부착·max_guards 동적 3→1→0. APPLY off → 무동작(byte-identical).
- **효과(33차트)**: **career 절단0·태그 6차트 13개(정상)** · wealth 절단0 2개 · **relationship 절단0**
  (kansal 태그 억제·본문 보존 — 이전 −1384 → tokΔ 0). 전 intent 절단 0.
- **테스트**: test_scoring_headroom.py 4종(relationship+kansal 절단 재발 금지·career 부착·헤드룸 부족 억제·
  APPLY off byte-identical). unit 863 pass, ruff·mypy clean(173). 잔여 2건 기존 DB(무관).
- (다음·건별) wealth 운영 적용 검토(절단0) → relationship 은 헤드룸 통과 케이스만. near-tie·Option A 보류.

### Scoring 1c-final — 핵심 intent 전체 rank guard 안전 적용 (2026-06-24)

데굴님 지시(정확도 마무리) — operational rank guard 를 핵심 intent 5종에 안전 적용 가능 상태로 닫음.
**score/rank/reduce 불변·near-tie/Option A 제외.** spec §14-9.

- **★버그 수정(domain normalize)**: APPLY_INTENTS 가 "study_document" key 인데 intent.domain.value 는
  "education" 이라 미매칭(study 0 tags 원인). operational_rank_guards 가 domain_to_expression_key 로
  정규화(education→study_document·5b-2b 동일) 후 매칭. enum value/string 일관.
- **수정(config)**: SCORING_OPERATIONAL_APPLY_INTENTS 기본을 5종 확장 — career/wealth/relationship/
  relocation/study_document(표현 key 기준). **master off 라 inert(byte-identical 유지).**
- **라우팅 진단**: parse_message 로 5 질문 모두 정확 라우팅 확인(직업운→career·재물운→wealth·연애운→
  relationship·이사운→relocation·시험운/학업운/자격증→education). 즉 study/relocation 0 tags 는 신호
  부재가 아니라 **naming 버그**였음(수정됨).
- **최종 회귀(scripts/scoring_guard_final_report.py, 33차트×5 intent)**: **전 intent 절단 0·max/resp≤3·
  과장단어(흉/위험/손실/투자주의/이별/파탄) 0.** career 13태그(6차트)·wealth 2·relationship 1·relocation
  1·study_document 2. tokΔ 0~60. 헤드룸 가드로 relationship 근접-ceiling 절단 방지 유지.
- **유지**: caution 중복 정리(compact)·토큰 헤드룸 가드(본문 우선). 강한 금전/관계 문구 미추가(문구는
  penalty 유래 2종 고정).
- **테스트**: test_scoring_apply +1(education→study_document 정규화). unit 864 pass, ruff·mypy clean(173).
  default(APPLY off·INTENTS5) byte-identical 확인. 잔여 2건 기존 DB(무관).
- **오픈 기본값 권장(검증 통과)**: SHADOW_ENABLED=False·RANK_EXPERIMENT=False·**APPLY_ENABLED=True**·
  rank_guard=True·near_tie_demotion=False·APPLY_INTENTS=5종. (master True 전환은 데굴님 최종 확정 후.)
- (보류) near-tie demotion(1c-β)·Option A.

### Scoring 1c 오픈 활성화 (APPLY_ENABLED=True) (2026-06-24)

데굴님 최종 확정 — operational rank guard 운영 활성화.

- **수정(config 운영 기본값)**: SCORING_OPERATIONAL_APPLY_ENABLED=True·APPLY_MODE.rank_guard=True·
  **SCORING_OPERATIONAL_COMPONENTS 둘 다 True**(1c guard penalty 산정에 필요 — 누락 시 가드 게이트
  `if not any(components)` 에 막혀 태그 0). APPLY_INTENTS 5종. SHADOW_ENABLED·RANK_EXPERIMENT 는 False.
- **불변 확인**: component on 은 **score/rank 미변경** — penalty 는 1c 태그 결정에만 소비, 1a sidecar 는
  SHADOW_ENABLED off 라 미실행. SHADOW/RANK_EXPERIMENT off 유지.
- **활성 동작**: 운영 default 로 career '올해 직업운' → [해석 주의] 2태그 노출 확인. off-switch(False 한 줄)
  즉시 복귀 확인.
- **테스트**: default 변경에 맞춰 test_master_off_empty·test_apply_off_byte_identical 을 monkeypatch off
  로 전환. full suite 1078 pass(잔여 2건 기존 DB 무관)·unit 864·ruff·mypy clean(173).
- **최종 상태**: operational scoring = rank guard 태그(5 intent·순위/score/reduce 불변·본문 우선 헤드룸
  가드·과한 긍정만 차단). 되돌리려면 APPLY_ENABLED=False 한 줄.

### 절기 경계 직전 날짜 일운 프롬프트 보정 (2026-06-24)

데굴님 지적 — 절기 직전 날짜(양력 달 ≠ 절입 달)에 월을 정확히 주입해도 LLM 이 양력 달로 월운을 오인
(7/4 질문에 "7월 전반…" 식으로 절기월 甲午 대신 양력 7월 기준 서술·천간/지지 역할 혼동).

- **수정(chat_service._date_day_fortune_note)**: 일운 사실 주입 시, `tgt.month != 절기월 절입 양력 월
  (mp.label[5:7])` 이면(=절기 경계 직전) 문장을 **"절기월 {간지}({N}월 절입)의 기운이 아직 이어지는 날,
  일운(日運) …"** 로 재구성해 절기월 기운 연속을 명시. 같은 달이면 기존 "일운 … / 그 날의 절기월 …" 유지
  (절기월 막 시작한 날에 '아직 이어지는' 오문구 방지). 후행 지시문("월간지로 그 날의 운 대신 금지…") 유지.
- **효과**: 2026-07-04 → "절기월 甲午(6월 절입)의 기운이 아직 이어지는 날, 일운(日運) 己卯(…)". 2026-06-20
  (같은 달) → 기존 형식.
- **검증**: test_conversation_date_fixes +1(경계 직전 강조·같은 달 기존형식). full suite 1078 pass, ruff·mypy
  clean. 잔여 2건 기존 DB(무관).

### 신살 보정 레이어 — 스펙 확정 + Phase A-1 LLM payload 배선 (2026-06-25)
- **배경**: 신살/길성을 사건 라벨 단독 생성기가 아니라 **위치(궁성)·운층·길흉·intent·생애단계에
  따라 기존 후보 해석을 조정하는 보조 레이어**로 구조화(사용자 제안 3건). 철학·분류·위치·운층은
  이미 존재 → 신규는 수치 구조화 + intent 정렬 + 생애단계/재활성화 + LLM 구조화 태그.
- **스펙**: `doc/v2_2/SINSAL_MODIFIER_SPEC.md` 확정. 4결정 — ①Domain enum 불변(GENERAL+palace_tags)
  ②`SinsalItem` 불변·별도 `SinsalModifier` derive ③LLM엔 숫자 미노출(한글 강도어) ④생애단계=대운 경계
  우선→나이 fallback. 생애단계 곡선·재활성화는 **4주 × 길성·흉살 전체**(근묘화실).
- **핵심 엔진(순수 추가)**: `sinsal_modifier_config.py`(전 수치 initial_default 상수)·`SinsalModifier`/
  `LlmSinsalModifier`(shared_types)·`sinsal_modifier.py`(`derive_natal_sinsal_modifiers`,
  `select_llm_sinsal_modifiers` pruning). 위치 scope/가중·domain_override 임계(0.85)·생애단계 곡선·
  운 재활성화(relations_to_chart/복음/동일신살)·강도밴드.
- **A-1 배선**: `LlmEventCandidate.sinsal_modifiers` 추가 → `build_llm_input`에서 도메인 기준 1회
  derive·prune → 상위 N(기본 2) 후보에만 부착(토큰 중복 차단) → `candidate_block` 직렬화 + 지시문 1줄.
  **광역 총운(FORTUNE_OVERVIEW) 제외**(토큰 가드 — 도메인/이벤트/타이밍/결정 질문만).
- **불변 보장**: event_score·favorability·ranking·용신 final·operational guard **무변경**(순수
  enrichment, monkeypatch 회귀 테스트로 검증). 숫자 weight LLM 미노출 테스트.
- **검증**: 신규 단위 15 + payload 통합 4 + 회귀. full suite **1098 pass**(실패 2 = 사전 존재 환경
  이슈: dry_run·auth 토큰 시드, stash로 베이스라인 동일 실패 확인). ruff·mypy clean.
- **후속**: A-2 = `chart_interpretation._sinsal_excerpts` 생애단계/재활성화 문장 enrich(분리). Phase B =
  신살 numeric 스코어링 편입(shadow sidecar 먼저, 별도 승인).

### 신살 보정 — Phase A-2 생애단계/재활성화 안내 (리포트 경로, 2026-06-25)
- **A-2 목표**: 근묘화실(년=초년/월=청년·사회/일=중년/시=말년) 정점 시기 + 평생 작동(정점 전 잠재·
  정점 후 배경·누적) + 운 자극 시 재활성화 원리를 LLM에 안내.
- **챗 경로 불가(측정 근거)**: career '올해 이직운'은 ≈10,856 tok로 trim 임계 아래 여유 ~140 tok뿐.
  안내 텍스트 추가 시 `serialize_with_guard` excerpt 트리머(`excerpts[:4]`)가 그 질문에서만 발동 →
  캐시 고정 prefix의 신살 excerpt 차등 삭제 → `test_fixed_prefix_identical_across_questions` 위반.
  → 챗은 A-1만 유지(고정 prefix·토큰 불변).
- **리포트 경로 채택(사용자 확정)**: `report_service._SECTION_GUIDES["F-05"]`(신살 섹션 지침)에
  근묘화실 정점·평생 작동·재활성 원리를 추가(보조 전제·단정 금지 유지). 리포트는 토큰 예산이 커
  안전, 챗 무영향.
- **검증**: full suite **1098 pass**(실패 2 = 사전 존재: dry_run·auth 토큰 시드). ruff·mypy clean.
  F-05 가이드에 '정점 시기'·'재활성' 반영 + '보조 자료임을 전제' 유지 확인.
- **보류**: 챗에도 넣으려면 trim 우선순위 리팩터(신살 텍스트를 캐시 excerpt보다 먼저 트림) 필요 — 별도.

### 신살 보정 — Phase B-1 numeric 스코어링 shadow sidecar (관측, 2026-06-25)
- **목표**: 신살 numeric 보정을 용신 operational sidecar와 **동일 패턴**으로 — shadow 관측 먼저,
  운영 score/rank/favorability/polarity **불변**.
- **구현**:
  - `sinsal_modifier_config.py`: 게이트 `SINSAL_NUMERIC_SHADOW_ENABLED=False` + 계수(극성/명명 점수·
    재활성 boost·클램프 caps·WARN 임계).
  - `sinsal_numeric_scoring.py`: `apply_sinsal_numeric_adjustment`(순수, index 기반 dict list,
    EventCandidate 미변경) + `sinsal_numeric_sidecar`(게이트 wrapper→off면 None) +
    `sinsal_invariance_snapshot`. 기간 numeric은 **그 기간 재활성(복음 동일글자 재출현)된 신살만**
    반영(전체 합산 시 길성·흉살이 캡에서 상쇄돼 변별력 소실 → 재활성만 셈). 길성+/흉살−/중립0, 클램프 ±10.
  - `sinsal_shadow_report.py` + `scripts/sinsal_shadow_harness.py`: 골든 차트 일괄 관측 → CSV/JSON.
    용신 operational shadow와 **분리**(독립 모듈·산출 파일).
- **관측(33차트·domain=career)**: 10,066행, **불변 위반 0**, 비0 delta 34%, 범위 −8~+8, WARN(|Δ|≥6)
  859행. 예: 년지 巳 재출현 기간(乙巳 대운·辛巳 세운)에 천덕귀인+협록@year 재활성 → Δ+7.
- **불변 보장**: 게이트 off 기본(라이브 무영향)·EventCandidate 스키마 무변경·invariance 스냅샷
  before==after(하네스 hard-fail 가드). 신규 단위 9건.
- **검증**: full suite **1107 pass**(실패 2 = 사전 존재: dry_run·auth 토큰 시드). ruff·mypy clean.
  shadow 산출물은 gitignore(미커밋).
- **후속**: B-2(운영 반영) = 분포 검증(과반영·WARN 비율) 후 `_score_target` 편입, 별도 승인.

### 신살 보정 — Phase B-1 v2 채널 shadow (방향 역행 수정, 2026-06-25)
- **검토 결과(B-1 score 모델 폐기)**: 33차트 관측에서 ①같은 기간 내 모든 사건 동일 delta(96%) ②길흉
  방향 역행 ≈981행(길성이 흉사건 발생가능성↑·흉살이 길사건↓) 확인. 신살은 발생 가능성 장치가
  아니므로(스펙 §2-1·§6) score 채널이 잘못 — 폐기(사용자 확정).
- **재설계(채널 모델)**: 신살을 **발생 가능성에 미반영(occurrence_score_delta=0 고정)**, 사건의
  favorability/risk/mitigation/texture **채널만** 관측. 길성=mitigation·favorability(+), 흉살=risk·
  favorability(−), 중립(역마·도화·화개·문창)=texture 태그(숫자 0). 채널 계수는 0~1 분수(§6),
  위치/intent·재활성 boost 곱, 캡(fav ±0.12·risk/mit ≤0.20).
- **구현**: `sinsal_modifier_config.py`(채널 계수 dict), `sinsal_numeric_scoring.py`
  (`apply_sinsal_channel_shadow`/`sinsal_channel_sidecar`), `sinsal_shadow_report.py`(채널 컬럼),
  `scripts/sinsal_shadow_harness.py`(채널 출력).
- **관측(33차트·career)**: 10,066행, **occurrence_score_delta!=0 행 0**(발생 가능성 불변), 채널 활성
  49%, fav −0.12~0.12·risk 0~0.20·mit 0~0.20(캡 정상), 불변 위반 0. 길성·흉살이 별도 채널이라
  같은 기간 동시 재활성해도 상쇄 없음. 방향 역행 소멸.
- **검증**: full suite **1107 pass**(실패 2 = 사전 존재). ruff·mypy clean. 게이트 OFF 기본·산출물 gitignore.
- **후속**: B-2 = favorability/risk/mitigation 채널에만 반영(occurrence·ranking 불변), LLM엔 한글 태그만.
  별도 승인.

### 신살 보정 — Phase B-2 채널 운영 반영 (리포트 경로, 2026-06-25)
- **목표**: B-1 v2 채널(완충/리스크/색채/질감)을 운영 출력에 반영 — occurrence_score·ranking 불변,
  LLM엔 숫자 없는 한글 태그만(사용자 재진입 조건).
- **챗 경로 불가(측정)**: career≈10,856tok·wealth≈10,796tok 등 무거운 질문이 trim 임계 여유 ~140tok뿐
  (A-2와 동일 벽). per-후보 채널 노트 추가 시 excerpt 트리머가 캐시 prefix를 깨므로 챗 제외.
- **리포트 경로 채택**: `report_event_input.precise_candidate_clusters` 기간 클러스터 head 뒤에 채널
  색채 노트 1줄 부착. `sinsal_numeric_scoring.channel_note_ko()` 로 채널값→한글 밴드 변환
  (예: '신살 시기색채: 완충 큼·리스크 주의·유리한 색채 (이동·변동성)'). 게이트
  `SINSAL_CHANNEL_APPLY_ENABLED`(config·롤백 1줄).
- **불변**: occurrence_score·ranking·favorability_ko 수치 무변경(텍스트 노트만 추가). 채널은 기간
  단위(재활성)라 클러스터당 1줄. **챗 토큰 무영향**(context_reducer 미접촉 — career 10,856 동일 확인).
- **검증**: full suite **1107 pass**(실패 2 = 사전 존재). ruff·mypy clean. 신규 테스트 3건(밴드 변환·
  리포트 노트 숫자 미노출·게이트 off).

### 신살 보정 — 챗 트림 우선순위 리팩터 + 챗 채널 노트 (2026-06-25)
- **목표**: 챗에도 B-2 채널 색채를 넣되, A-1/A-2에서 막혔던 토큰 천장 문제(무거운 질문이 신살 추가
  시 excerpt 트리머를 건드려 캐시 prefix 붕괴)를 트림 우선순위로 해소.
- **트림 우선순위(serialize_with_guard 다단계화)**:
  - Tier0(신규): 토큰 초과 시 신살 보조(sinsal_modifiers·sinsal_channel_note)를 **캐시 prefix
    (excerpt)보다 먼저** 제거(`_drop_sinsal_aux`). 신살 의존 지시문도 조건부 emit이라 자동 제거.
  - Tier1(기존): 그래도 초과면 excerpts[:4]·event_candidates[:3]·evidence trim(신살 이미 제거).
  - 효과: 무거운 질문(career)도 신살부터 빠져 고정 prefix·후보 본문 보존 → 캐시 불변 유지.
- **챗 채널 노트**: `LlmEventCandidate.sinsal_channel_note` 추가, `build_llm_input`이 상위 N후보에
  period 채널 노트(`channel_note_ko`) 부착. 신살 총비용 ≈169tok(career full 7,882→no_sinsal 7,713).
- **검증**: career·연애운 둘 다 채널 노트 부착 + 고정 prefix 동일(캐시 불변). Tier0 강제 초과 테스트
  (신살 먼저 제거·excerpt 보존)·_drop_sinsal_aux noop·숫자 미노출. full suite **1113 pass**
  (실패 2 = 사전 존재). ruff·mypy clean.
- **결과**: 신살 채널 색채가 챗·리포트 양쪽에 반영되며, 토큰 압박 시 신살이 보조 레이어로서 가장
  먼저 양보해 핵심(명식·후보) 품질과 캐시 안정성을 지킨다.

### 시점 파싱 — 슬래시/대시 날짜 + 과거시제 (멀티턴 승계 오류 수정, 2026-06-25)
- **버그(실로그)**: "집 계약은 6/17에 했는데…" 질문이 6월 17일을 인지하지 못하고 이전 턴 시점
  (2026-07-05)을 그대로 승계. 원인 ①`time_parser` C5b가 "N월 N일"만 인식하고 "6/17"·"6-17"
  슬래시/대시 M/D 형식 미파싱 → time_range=None → `conversation` 멀티턴 승계가 이전 턴 시점으로
  덮어씀. ②과거시제인데 연도 미지정 과거 날짜를 '내년 택일'로 밀어버림.
- **수정(time_parser.py)**:
  - `_SLASH_DATE_RE`: "6/17"·"6-17"·"2026-06-17"(선택 연도) 인식. 뒤에 숫자·구분자/기간단위
    (월/년/주/개월/시간/살/분/초/%)가 붙으면 제외 → "8-10월"(월 범위)·"3-4년" 오인 차단.
  - C5b를 "N월 N일" 우선·없으면 슬래시/대시로 통합 처리(동일 앵커·이후/부터 로직).
  - `_PAST_TENSE_RE`(했/찍었/샀/봤/였/었…): 과거시제면 연도 미지정 과거 날짜를 그 해(과거) 유지
    ('6/17 계약했는데'→2026-06-17). 미래 택일('7월 4일 이사하려고')은 표지 없어 영향 없음.
  - 파싱되면 intent.time_range.start가 채워져 conversation 멀티턴 승계가 자동 skip(추가 변경 불필요).
- **검증**: 6/17·6-17·ISO·과거→올해, 미래→내년, 기존 'N월 N일' 불변, 범위('8-10월'/'3-4년') 오인
  없음. end-to-end: 이전 턴 7/5 있어도 현재 '6/17' → 2026-06-17(승계 아님). 신규 테스트 11건.
  full suite **1124 pass**(실패 2 = 사전 존재). ruff·mypy clean.

### 이사 지역오행(터전) 적합 누락 수정 — 지명 추출 어순 보강 (2026-06-25)
- **버그(실로그)**: "현재는 고양시 일산동구에 있는데 이사할집은 서울 중구야" 질문이 목적지 지역
  오행 적합(터전)이 아니라 연도별 이사 타이밍으로 응답. 사용자는 "서울 중구가 내 용신과 맞는
  터전인지"를 물었음.
- **원인**: relocation intent·structural 블록·region_fit 엔진은 모두 정상인데, `query_parser`의
  지명 추출 정규식이 이 어순을 못 잡음 → target_region=None → `_relocation_region_context`가
  `if not phrase: return []`로 조용히 빠짐:
  - 목적지: "[지명](으로|로|에) 이사"만 인식 → "이사할집은 [지명]야"(지명이 '이사' 뒤) 미매치.
  - 현재지: "지금 사는 곳은/현재 거주지는"만 인식 → "현재는 [지명]에 있는데" 미매치.
- **수정(query_parser._detect_constraints)**: 재사용 `_REGION_PHRASE` 추가 +
  - target_region: "이사할/이사갈 (집|곳)은 [지명]", "새 집은 [지명]", "이사는 [지명]" 진술형 추가.
  - location_base: "현재는 [지명]에 있는데/사는데", "[지명]에 살고/거주" 어순 추가.
- **검증**: 추출 — "이사할집은 서울 중구야"→target 서울 중구·base 고양시 일산동구; 기존 "서울 중구로
  이사" 어순 불변. end-to-end: 프롬프트에 "서울 중구(오행 土) × 용신(土) → 적합도 1.0 (매우 유리)"
  지역 오행 적합 블록 주입 확인. 신규 테스트 8건. full suite **1132 pass**(실패 2 = 사전 존재).
  ruff·mypy clean.
- **남은 한계(방향)**: region_elements.json은 region/element만 보유(좌표·방위 없음) → 두 지역 간
  실제 지리 방향 계산은 불가. 8방위 용신 적합은 택일(date_recommendation) 경로에만 존재. 방위까지
  비-택일 이사 질문에 넣으려면 별도 데이터·작업 필요.

### 이사 이동 '방위' 분석 추가 — 지역 좌표 + 후천팔괘 방위 길흉 (2026-06-25)
- **목적**: 비-택일 이사 질문에서 '터전(지역오행)'에 더해 '방향(이동 방위)'까지 답. 사용자가 함께
  물었으나 좌표 데이터 부재로 미지원이던 부분.
- **데이터**: `dictionaries/region_coords.json` 신규 — 수도권(서울 25구·경기 주요시·인천 구)+
  6광역시+시도 폴백 65개 근사 중심좌표(8방위 분류용 ±0.05°, reviewed:false·검수 전 초안,
  절대원칙 5). 키=region_elements 형식('{시도} {시군구}').
- **엔진**: `region_direction.py` — 좌표 해석(완전→접미→토큰; '고양시 일산동구'→'경기도 고양시'
  흡수), `_bearing_to_compass`(경도 cos 보정 8방위), 후천팔괘 방위-오행(북水·동木·남火·서金·
  간방 土/木/金), `direction_fit`(이동 방위 오행 × 용희기구한 → 매우유리/유리/주의/중립, 生용신 포함).
- **연결**: `chat_service._relocation_region_context`에 location_base 있을 때 '이동 방위 적합' 줄 추가.
  지역오행 적합과 **별개 축**(목적지가 용신이어도 가는 방향은 기신일 수 있음).
- **검증**: 고양 일산동구→서울 중구=남동(木=기신)→주의; 강남→고양=북서; 서울→부산=남동. end-to-end
  프롬프트에 '지역 오행 적합(서울중구 土=용신 매우유리)' + '이동 방위 적합(남동 木 기신 주의)' 둘 다
  주입 확인. 신규 테스트 6건. full suite **1138 pass**(실패 2 = 사전 존재). ruff·mypy clean.
- **한계**: 좌표 65개 커버(미등재 지역은 방위 산출 graceful 생략). 정밀 검수·확장은 후속.

### 연/월 흐름 블록 기간 단위어 정합 — '해' vs '달' (2026-06-25)
- **버그(실로그)**: 연 단위 블록('[연도별 흐름 — 2026~2035 10년]')의 하위 줄·표 범례가 '달'(월)을
  써서 년/월 혼동. 예: '[기반 최고 달]', '이 달에 약하거나', '그 달 발생 가능성', '구신·기신인 달은'.
- **원인**: context_reducer monthly_overview 블록은 헤더만 _is_yearly로 분기('연도별 흐름/월별 요약')
  하고, 기반-최고 지목·표 범례의 '달'은 하드코딩. 연 단위에서도 '달'로 출력.
- **수정(context_reducer)**: 단위어 `_unit`('해'/'달')+조사 `_n`('는'/'은')·`_l`('를'/'을') 도입
  ('달'은 ㄹ받침이라 은/을, '해'는 모음이라 는/를). 기반-최고 줄·표 범례의 기간-단위 '달'을
  전부 `{_unit}`+조사로 치환. 마커 용어 '검토월'은 '검토 시기'로 중립화.
- **검증**: 연 블록 → '[기반 최고 해]·이 해에·그 해·해는·좋은 해'(달 미노출); 월 블록 → '[기반 최고
  달]·달은'(조사 정상, '달는/달를' 없음). 신규 테스트 2건(연/월 단위·조사). full suite **1140 pass**
  (실패 2 = 사전 존재). ruff·mypy clean.

### 이사 목적지 질문 — 지역오행·방위 중심 라우팅 (10년 타임라인 묻힘 수정, 2026-06-25)
- **버그(실로그 후속)**: 지역오행·방위 적합 블록은 프롬프트에 들어가는데, '시점 막연' 판정으로
  `_YEAR_DIGEST_DIRECTIVE`(올해부터 10년 연 단위 흐름으로 답하라)·대운 framing이 붙어 답이 10년
  타임라인으로 채워지고 지역/방위 의도가 묻힘.
- **원인**: 목적지(target_region)를 명시한 적합성 질문도 '시점 막연 미래'로 분류돼 타임라인 강제
  지시가 적용됨.
- **수정(chat_service)**: `_relo_dest = relocation ∧ target_region` 감지. 참이면
  ①`_YEAR_DIGEST_DIRECTIVE`·대운 framing(vague) **억제** ②신규 `_RELOCATION_DESTINATION_DIRECTIVE`
  (답 중심을 [지역 오행 적합]·[이동 방위 적합]에 두고, 목적지 오행이 용신이어도 방위는 기신일 수
  있으니 구분; 연도별 흐름은 보조 한두 줄) 추가.
- **검증**: 목적지 질문 → 목적지 지시 ON·year digest/대운 framing OFF·지역/방위 블록 유지; 목적지
  없는 막연 이사질문 → 기존 10년 digest 유지(회귀 안전); 비이사 질문 무영향. 신규 테스트 3건.
  full suite **1143 pass**(실패 2 = 사전 존재). ruff·mypy clean.

### 이동 방위 오행 — 명리형 간방 혼합 모델로 전환 (2026-06-25)
- **지적(데굴님)**: '남동은 화랑 목이 함께 있는 방위 아니야?' — 기존 region_direction은 후천팔괘
  단일 배정(남동=巽=木)이라 간방을 한 오행으로만 봄.
- **확정**: 풍수 팔괘(좌향·공간 배치)는 단일 배정이 맞지만, 개인 사주 방향 적합엔 **간방 혼합
  모델**이 기본값. 사정(동木·남火·서金·북水)=단일, 간방=인접 두 사정 혼합 45:45 + 土 전환 10
  (남동=木0.45·火0.45·土0.10, 남서=火金土, 북서=金水土, 북동=水木土).
- **수정(region_direction.py)**: `_DIRECTION_ELEMENT`(단일)→`_DIRECTION_ELEMENTS`(가중 dict).
  `direction_fit`을 역할 가중합(용신+2.0/희신+1.2/한신0/기신−2.0/구신−1.2)×방위 비중 합 →
  밴드(≥1.2 매우유리/0.4 유리/−0.4 중립/−1.2 다소주의/그 이하 주의)로 판정. 간방은 한쪽이 기신
  이어도 다른쪽 길신이면 '혼합' 완화. 라벨은 사정/간방 공통 중립표기, '혼합·전환' 뉘앙스는 근거
  문구가 담당. chat_service 헤더도 '(후천팔괘)'→'명리 방향 적합(간방 혼합)'으로 갱신.
- **검증**: 용신 土·희신 火·기신 木 → 남동=木(기신)·火(희신)·土(용신) score −0.16 '중립(도움·부담
  공존)'(기존 '주의' 대비 정교화); 남=매우유리·동=주의·북=다소주의(사정 단일 정상). 고양 일산→
  서울 중구 남동='중립'. 신규/갱신 테스트 7건. full suite **1144 pass**(실패 2=사전 존재). ruff·mypy clean.
- **메모(후속)**: 풍수 팔괘 단일 배정 모드(fengshui_bagua)는 좌향·공간 배치 기능 도입 시 분리 추가.

### 결정형 이사 질문 — 타임라인 데이터 차단 (이미 정해진 이사에 '가능시기' 나열 제거, 2026-06-25)
- **지적(데굴님)**: '이사할집은 서울 중구야'(이미 집이 정해진/계약한 상태)인데 시스템이 여전히
  2026~2035 '언제 이사하면 좋은지' 타임라인을 그려 비논리적. 앞서 추가한 목적지 중심 지시는 들어갔으나
  [연도별 흐름] 데이터 블록 자체가 남아 LLM이 그것을 풀이함.
- **수정(chat_service)**: `relo_decided = (relocation ∧ target_region) ∧ 시점 미질문(언제/몇 월/시기
  등 없음)` 산출. 참이면 `vague_future`·`wants_monthly`를 모두 False로 막아 **연/월 흐름 overview
  데이터 자체를 생성하지 않음**. 평가형 질문이므로 지역오행·이동방위·이사이유(십성) 블록과 목적지 중심
  지시만 남긴다. 타이밍 질문('언제 이사')·목적지 없는 막연 질문은 기존 타임라인 유지.
- **검증**: 결정형 → [연도별 흐름]·[월별 요약]·연도 나열 제거, 지역/방위/이사이유 유지; 타이밍 이사·
  목적지 없는 막연 이사·비이사 질문 → 타임라인 유지(회귀 안전). 신규 테스트 3건. full suite **1147
  pass**(실패 2 = 사전 존재). ruff·mypy clean.

### 멀티턴 — '그래 봐줘' 동의+이어보기 후속 의도 승계 (대화 단절 수정, 2026-06-25)
- **버그(실로그)**: 턴1 '이직 언제 할 수 있을까'(career/timing_search) 뒤 턴2 '그래 봐줘'가
  새 풀이 요청으로 끊겨 일반 10년 인생 흐름(general/fortune_overview)으로 빠짐 — 직전 이직 맥락 단절.
- **원인(conversation.link_question)**: `AFFIRMATION_RE`에 '봐줘'가 없어 '그래 봐줘'가 fullmatch
  실패, '봐줘'가 `_READING_REQUEST_RE`(새 풀이)에 걸려 토픽연속 경로에서도 제외 → NEW로 떨어짐.
- **수정**: `_AFFIRM_CONTINUE_RE`(동의어 시작 + 선택 이어보기/풀이 동사: 봐줘·보여줘·계속·이어·더)
  추가. 새 도메인이 없으면 follow-up(DRILL_DOWN)으로 직전 의도 승계(기존 승계 로직이 domain·
  query_type·event_key를 직전에서 잇는다). 새 도메인 후속('연애운 봐줘')은 도메인 전환, 새 풀이
  요청('총운 봐줘')은 NEW 유지.
- **검증**: '그래 봐줘'·'응 보여줘'·'좋아 계속'·'그래' → follow_up·career·timing_search·career_change
  승계; '연애운 봐줘' → relationship 전환; '총운 봐줘' → NEW. end-to-end 턴2 프롬프트가 이직·직업
  후보 중심. 신규 테스트 8건. full suite **1155 pass**(실패 2=사전 존재). ruff·mypy clean.
- **운영**: 백엔드 --reload로 재기동돼 자동 반영(이전 stale 프로세스 이슈 해소).

### 멀티턴 — LLM 즉석 제안 이어보기('그래 봐줘'로 그 제안 계속, 2026-06-25)
- **지적(데굴님)**: '그래 봐줘'가 직전 이직 맥락은 잇게 됐으나, LLM이 답변 끝에 제시한 구체 제안
  ('제안받는 쪽 vs 내가 움직이는 쪽')은 상태에 없어 그대로 이어가지 못함 → 사용자는 여전히 단절로
  오인. 개선 필요.
- **구현(상태 스키마 변경 없이 history 재사용)**:
  - 라우터(chat.py): `_last_assistant_answer`로 스레드의 가장 최근 완료 assistant 답변을 읽어
    `chat_service.chat(prior_answer=...)`로 전달.
  - chat_service: `_extract_offer`(답변 끝 1~2문장에서 제안 표지 '봐드릴게요/이어서/어느 쪽/원하시면'
    등이 있는 부분 추출, 300자 가드) + `_OFFER_CONTINUE_DIRECTIVE`. `is_affirm_continue(question)`
    (conversation 공개 판정)이고 제안이 추출되면, '직전에 네가 제안한 「offer」를 이번 답 중심으로
    이어 풀라'는 우선 지시문을 주입.
- **검증**: '그래 봐줘'+직전 제안 → 제안 텍스트('제안이 들어오는 쪽')가 프롬프트에 실리고 이어보기
  지시 주입; 새 질문('재물운')·제안 없는 답변·prior 없음 → 미주입. 신규 테스트 5건. full suite
  **1160 pass**(실패 2=사전 존재). ruff·mypy clean. 백엔드 --reload로 자동 반영.

---

## 지역 오행 엔진 P1 — 한자+음운+방위+상속 → 읍면동 프로필·매칭 ✅ (2026-06-26)

docs/12 §10 P1. 시군구 230 퇴행을 막고 **읍면동 5,065**까지 고유 오행 프로필을 사전계산.

- **스키마**(`region_element.py`): `DominanceType` 신뢰도 밴드형 재정의(unknown<0.35≤weak<0.55,
  그 이상 single/composite/contested), `RegionLevel`(ctprvn/sig/emd), `RegionElementProfile`에
  region_level·parent_code·anchor 좌표·source_layers 추가, `RegionUnitInput`/`RegionProfilesMeta`/
  `RegionProfilesSnapshot` 신설. shared_types `__init__` export.
- **사전**(`region/region_dominance_rules.json` v0.2.0): confidence 밴드 + match_score 산식
  파라미터(role_scores·penalty·confidence_adjust·score_caps). `dictionaries.py`에 region/ 4종
  pydantic 스키마+lint 등록(가중합≈1·오행 유효성·음운 cap·밴드 단조성).
- **엔진**(`region_element_engine.py`): ①한자 토큰화(region_hanja_tokens) → 미매칭 시
  region_elements 큐레이션 폴백(D2) ②한글 초성 음운(유효가중 cap 0.03 **절대 상한**, 신뢰도
  비-기여 — D1) ③한자 없는 단위는 부모 프로필 상속(신뢰도 감쇠) ④미공급 GIS 레이어 제외 후
  재정규화(절대원칙 11). 추천: 용/희/기/구신×벡터 match/avoid(0~100, 저신뢰 cap 78/65),
  방위는 프로필 미저장·추천 시점 anchor bearing으로 region_direction 혼합모델 재사용(§4-4·§12).
  `region_fit_scores` 모듈 함수로 승격(D3).
- **빌드**(`build_region_profiles.py`): doc/gis `region_units_compact`(5,332) + region_elements
  한자 조인(248/250, 도시명 접두 폴백) → `compiled/region_element_profiles_v1.json`(+meta).
  스냅샷 2.4M(컴팩트·centroid 생략·라운딩). dominance 분포: unknown 1780/weak 3397/
  single 138/composite 17(P1은 우세 단정 보수적).
- **호환**: `relocation.region_fit()`은 엔진 승격본 위임 래퍼로 출력 동일.
- **데이터 처리**: doc/gis 대용량 원천(sqlite/jsonl/csv/csv.gz) gitignore + graceful 재빌드,
  소형 메타·검증·스키마는 추적, 운영 스냅샷은 커밋(절대원칙 9).
- **검증**: 신규 테스트 11(cap·과확정 금지·emd≥5000·부모상속·방위 분리·기신 감점·승격 호환).
  unit 전체 pass, dict validate 65 pass, ruff·mypy clean(127 files). 기존 relocation/region
  회귀 불변. (사전 검수 전이므로 reviewed:false — 절대원칙 5.)
- **P1 미수행(설계상)**: GIS 지형 오행 확정, `alt.when` 지형조건 발동(P3), 방위 프로필 저장,
  음운 단정 추천. 다음(P2)=ingest_legal_dong/admin_unit, (P3)=GIS feature 어댑터.

---

## 지역 오행 엔진 P2 — 행정 registry + 지명 해소기 + scope ✅ (2026-06-26)

docs/12 §10 P2. 원래 정의(별도 admin_unit 적재)는 P1에서 읍면동 프로필을 이미 적재해 대부분
중복 → **이름 해소 계층 + 경량 admin registry**로 재정의(사용자 승인 옵션 A).

- **경량 registry**(`build_region_admin.py` → `compiled/region_admin_units_v1.json`, 1.4M):
  doc/gis 5,332단위를 구조화 이름(시도/시군구/읍면동)·area_m2·parent 트리만으로 적재. 좌표는
  프로필이 보유하므로 생략(중복·용량 방지). `RegionAdminUnit`에 region_level 추가 +
  `RegionAdminSnapshot` 신설(shared_types export).
- **해소기**(`RegionNameResolver` in region_element_engine.py): 읍면동명 전국 590종 중복
  (효자동×4·사직동×5)이라 단순명 해소 불가 → full_name 완전일치(유일) → 시도 별칭 확장 토큰
  포함 → leaf 명 동률 시 leaf 정확일치로 좁힘. **끝까지 모호하면 추측 않고 후보 목록 반환**
  (절대원칙 7 — 지역 혼동 방지). scope: 수도권(서울·경기·인천)·시도(약식 포함)·상위지역 하위
  트리(BFS) → region_code 열거.
- **recommend() 배선**: candidate_regions·base_location은 해소기로 코드 확정(모호 시 노트로
  surface), candidate_scope는 resolve_scope로 후보군 확정. admin_path 미로딩 시 legacy full_name
  매칭으로 graceful 폴백(기존 P1 테스트 불변).
- **검증**: 신규 테스트 6(완전/약식/유일 해소·동명 모호 후보 반환·미등재·scope 시도/수도권/하위·
  recommend 배선·registry 카운트). unit 963 pass·1 skip, admin 빌드 결정론, dict validate 65,
  ruff·mypy clean(146 files). 수도권 시군구 77=서울25+경기42+인천10 검증. 전 항목 reviewed:false.
- **다음**: P3 = GIS feature 어댑터(doc/gis sqlite의 external_feature·region_feature_direction·
  emd_direction_probe 16만 행 활용, 외부 지형 데이터 공급 시 physical_geography 레이어 활성).

---

## 지역 오행 엔진 P3 — GIS 지형 feature 어댑터(스키마+어댑터+스텁) ✅ (2026-06-26)

docs/12 §10 P3. doc/gis sqlite의 external_feature·region_feature_direction가 0행(외부 지형
데이터 미공급, README 한계) → §10 정의대로 "스키마+어댑터+스텁, 공급 시 활성화". 외부 데이터
부재 시 빌드 산출은 P1/P2와 **완전 동일**(재빌드 검증 — items identical).

- **스키마**: `RegionGeoFeature`(§3-C 집계 필드) + `RegionGeoFeatureFile` export.
  `region/region_geo_signal_rules.json`(§4-1 매핑 데이터화): forest→木, water/river/wetland/
  coast→水, mountain_score→土(+木 alt), plain/basin→土, south_facing/elevation→火,
  industrial/road/rail→金. dictionaries 등록+lint(layer/오행/필드 유효성), geo 샘플도 스키마 검증.
- **어댑터**(region_element_engine.py): `_geo_layers`가 feature→physical_geography(0.45)·
  landcover_hydro_forest(0.20) 레이어 벡터로 변환(정규화: ratio 0~1·density/고도 norm·bool).
  build_profile이 §5 결합에 지형 레이어 추가→재정규화로 지형 우세(절대원칙 11), **자체 지형
  신호 있으면 부모 상속 차단**(own_signal 게이트). 한자 문맥규칙 alt.when(D2 보류분)도 지형
  신호 충족 시 활성(山+산림→土+木). 산 지형성=土, 산림 피복=木 분리(§4-1 핵심).
- **빌더**: `build_region_profiles.py [units] [compiled] [geo]` — 지형 파일(기본
  doc/gis/region_geo_features.jsonl) 공급 시 활성, 부재 시 graceful.
- **검증**: 신규 테스트 8(활성·벡터이동·신뢰도상승·상속차단·mountain_score=土·정규화·
  alt.when·build_profiles geo). unit 971 pass·1 skip, 무지형 재빌드 산출 동일, dict validate 66,
  ruff·mypy clean. 전 항목 reviewed:false.
- **다음 P4**: 풍수 형국(DEM)+의도별 가중+evidence Graph RAG 경로+택일 결합+chat 연동.
  sqlite의 external_feature 포인트 모델·region_feature_direction·emd_direction_probe(16만)는
  방향성 풍수(§4-5)용으로 P4에서 활용(외부 지형 데이터 공급 전제).

---

## 지역 오행 엔진 P4-A — 의도가중·evidence·chat 오케스트레이션·택일 bridge + P4-B 스텁 ✅ (2026-06-26)

docs/12 §10 P4. 외부 데이터 의존 여부로 분리(사용자 확정): **P4-A 구현 + P4-B 스텁+계약**.
지역 엔진을 실사용 오케스트레이션에 연결.

- **P4-1 의도별 가중 치환**: region/region_intent_weights.json(IntentMode별 preset) +
  `resolve_intent_weights(intent, available)` — 미공급 레이어 제외 후 재정규화(절대원칙 11),
  phonetic 0.03 cap 유지, 미공급은 missing_layers 보고(0점 감점 금지). dict 등록+lint(합 1·키 유효).
  아키텍처: 고정 프로필 단일 벡터라 intent 전면 재가중은 지형데이터+per-layer 저장 필요 → P4-A는
  가중 해소 메커니즘 + explanation 노출, match_score(고정 벡터)는 불변(criteria 1 보존).
- **P4-2 evidence 구조화**: RegionFitSummary(positive/negative/neutral)·RegionRecommendationEvidence·
  RegionMissingLayer·RegionRecommendationExplanation + `explain_fit()`(역할별 적합 근거+레이어 근거+
  미공급). recommend가 top_n에 explanations 부착(RegionRecommendationResult.explanations).
- **P4-3 chat 오케스트레이션**: region_recommendation_orchestrator.py — 의도 라벨→IntentMode,
  용희기구신→Query, recommend→LLM payload(계산 금지 지침 포함). LLM은 fit_summary·evidence로 설명만.
- **P4-4 택일 bridge**: RelocationRegionCandidate·RegionTaekilContext + to_taekil_context() —
  '어디(지역)'를 '언제(택일)' 엔진으로 넘기는 페이로드. 택일 점수는 date_selection 책임(역할 분리).
- **P4-5 풍수/방향성 스텁**: region_geo_stubs.py — FengshuiFormAdapter(DEM 미공급→available=False),
  DirectionalFeatureAdapter(sqlite region_feature_direction 0행→available=False). 감점 금지·missing 표시.
- **검증**: 신규 테스트 9, unit 980 pass·1 skip, P1/P2/P3 프로필 재빌드 items 불변, recommend
  match_score 불변(마포구 92·중구 0), dict validate 67, ruff·mypy clean. 전 항목 reviewed:false.
- **남은 외부 데이터 의존(P4-Data/P5)**: 산/하천/DEM/토지피복 공급 시 ①physical/landcover 레이어
  실활성(P3 어댑터) ②풍수·방향성(P4-B) 실판정 ③intent 전면 per-layer 재가중. 그 전까지 지역 추천은
  한자·음운·기존자산 기반 1차 추정(확정도 낮음 명시).

---

## 지역 오행 엔진 P4-Data — 외부 지형 feature index → 읍면동×방위 요약 파이프라인 ✅ (2026-06-26)

docs/12 §4-1·§4-4·§6, 사용자 확정("원본 SHP 아닌 feature coordinate index"). 외부 지형을 대표
좌표로 압축해 읍면동×8방위 주변 지형 오행을 사전계산. 데이터 수급/변환(SHP→좌표)은 상류 툴킷
doc/gis_region(geopandas/pyproj) 담당, 백엔드는 핸드오프 CSV 소비. 외부 데이터 부재 → 산출 0(스텁).

- **계약 정렬**(doc/gis_region SQL과 1:1): ExternalGeoFeature(대표좌표+오행벡터)·
  RegionDirectionalElementSummary(읍면동×8방위 오행+nearest_*+top_features)·Snapshot. shared_types export.
- **오행 사전 미러**: region/region_geo_feature_elements.json(툴킷 feature_element_rules + reviewed:false,
  13 feature_type, 거리버킷 1/3/5/10km) + dictionaries 등록·lint(feature_type/오행/버킷 단조성).
- **빌더**: build_region_directional_summary.py — external_geo_feature.csv + 읍면동 anchor →
  거리/bearing(atan2(dx,dy) N=0/E=90)/8방위/버킷 influence/signal=오행×influence×importance/방위 합산
  → compiled 요약. 순수 파이썬(EPSG:5179 평면, pyproj 불필요), 그리드 prefilter(5,065×N). graceful 부재.
- **소비**: DirectionalFeatureAdapter가 요약 조회(없으면 available=False·감점 금지), orchestrator
  payload에 주변 지형 하이라이트("북 1.8km 산") 덧붙임. FengshuiFormAdapter는 DEM 필요라 스텁 유지.
- **정정**: doc/gis_region/samples 의 손제작 sample은 x_5179/y_5179가 lon/lat과 불일치(북악산 방위
  오류) — 코드 정상, 실툴킷(pyproj) 출력은 정합. 테스트는 실 읍면동 anchor 기준 합성 feature 사용.
- **검증**: 신규 테스트 14(방위·산=土≠木·하천 다중 anchor·adapter 소비·부재 graceful 등), unit 985 pass,
  P1~P4-A 재빌드 불변, dict validate 68, ruff·mypy clean. 전 항목 reviewed:false.
- **활성 경로**: doc/gis_region 툴킷으로 POI+하천+해안 → external_geo_feature.csv 드롭 →
  build_region_directional_summary.py 실행 → 방향성 풍수 자동 활성. 외부 데이터는 gitignore.

---

## 지역 오행 엔진 — chat 라우터 실배선(#2) ✅ (2026-06-26)

P4-A 오케스트레이터를 실제 chat 파이프라인에 연결. 이제 사용자가 "나에게 맞는 이사 지역 추천"·
"제주 쪽 어때?"류를 물으면 시군구 후보가 surface된다.

- chat_service `_region_recommendation_context`: 이사 의도 + 목적지 미지정/시도·수도권 범위일 때
  favorability_map→용희기구신으로 RegionRecommendationOrchestrator 호출 → 시군구 top5(적합·유리/
  주의 오행·방위) 구조 블록 surface. 특정 시군구 목적지는 기존 `_relocation_region_context` 단건
  궁합이 담당(중복 방지 게이트 — resolve_region SIG 일치 시 빈 줄).
- lazy 싱글턴 `_get_region_orchestrator`(compiled 프로필+행정 registry+방향성 요약). 미빌드 시
  graceful None(일반 풀이 무영향). 엔진에 공개 `resolve_region` 추가.
- LLM은 계산 없이 fit_summary·evidence로 '유리/보완성/기류' 설명(payload directive). 지형 GIS
  미반영 1차 추정·단정 금지 라벨 동반.
- 검증: 신규 테스트 1(개방형 전국 추천·시도 scope·특정 시군구 제외), unit 986 pass·1 skip,
  ruff·mypy clean, 기존 chat/relocation 회귀 불변.

---

## 지역 오행 엔진 #3 소비 경로 검증 + 활성화 runbook ✅ / #1 수급은 데이터 블로커 (2026-06-26)

- **#3 코드 완성·검증**: 토지피복/임상도 집계(region_geo_features.jsonl) 드롭 시 build_region_profiles가
  physical_geography·landcover_hydro_forest 레이어를 활성화함을 스크립트 레벨 회귀로 고정
  (test_build_profiles_script_consumes_geo_handoff — 산림→木·수계→水 검증). 방향성(external_geo_features.csv)
  소비도 P4-Data에서 검증됨. 즉 #3의 엔진 소비 코드는 전부 완성.
- **활성화 runbook**(docs/12): 두 핸드오프(집계 jsonl·점좌표 csv)→빌드 명령→활성 레이어 매핑 정리.
- **#1 데이터 수급은 블로커**: 정부 GIS(NGII POI·VWorld 하천·해양조사원 해안·산림청 임상도·환경
  토지피복·국토정보플랫폼 DEM)는 로그인/신청 수동 다운로드 + geopandas/pyproj 미설치 → 본 환경에서
  원본 SHP 취득·변환 불가. 변환 툴킷(doc/gis_region)은 사용자 제작 완비. 데이터 드롭 시 빌드만 실행.
- **DEM/풍수(FengshuiForm)**: 별도 알고리즘 + DEM 필요 → 미구현(3차 고도화).
- 검증: 신규 테스트 1, unit 987 pass·1 skip, ruff·mypy clean.

---

## 지역 오행 엔진 — P4-Data Acceptance Layer + emd 계산/sig surface + 무데이터 문구 가드 ✅ (2026-06-26)

데이터 수급 전 마무리(사용자 확정): 입구 검증·동읍 계산 유지·LLM 과장 차단.

- **Acceptance Layer**(입구 검증): geo_acceptance.py(inspect/validate 13항목 — 좌표/CRS/인코딩/
  feature_type/한반도 범위/geometry/row count 등) + CLI 3종(inspect_geo_source·
  validate_external_geo_sources(게이트)·build_external_geo_acceptance_report(리포트 json/md)) +
  doc/gis_external_data_acceptance.md. csv/jsonl/geojson 순수 파이썬 전수, shp/gpkg는 geopandas
  있으면 전수·없으면 .prj 메타+안내(graceful). fail이면 변환 금지, warning은 보정 후 진행.
- **emd 계산/sig surface**(요구사항1): recommend_payload에 computed_level=eup_myeon_dong/
  surface_level=sig/surface[].top_emd_candidates. _select_candidates 전국 폴백을 요청 해상도 기준으로
  수정(emd 요청 시 읍면동 후보 유지 — 시군구 추천기 퇴행 방지). chat은 emd 계산→시군구 묶음+세부 동.
- **무데이터 문구 가드**(요구사항2): payload.terrain_data_available + directive가 외부 지형 미연결 시
  '북쪽에 산·배산임수·풍수 완성' 류 실제 지형 주장 금지, '1차 추정' 문구 권장.
- 검증: 신규 테스트 11(acceptance 9 + emd/sig payload 1 + 기존 chat 회귀 보강), unit 997 pass·1 skip,
  ruff·mypy clean. 엔진 결과 불변(입구 검증은 변환·점수 미개입).
- 남은 순서(데이터 전): 지역 추천 golden case 20개·가중치 튜닝 준비. 데이터 후: POI→하천→해안→
  임상도/토지피복→DEM 순 활성. DEM 풍수(FengshuiForm)는 별도 알고리즘 필요로 미구현.

---

## 지역 오행 엔진 — 추천 golden 20케이스(#4) + 가중치 튜닝 준비(#5) ✅ (2026-06-26)

데이터 수급 전 마지막 마무리. reviewed:false 가중이라 절대값이 아닌 **상대 순위·역할·구조 불변식**을
고정해 향후 튜닝 시 의미 퇴행을 회귀로 잡는다.

- **#4 golden 20케이스**: tests/fixtures/region_recommendation_cases.jsonl + test_region_golden.py.
  결정론 candidate_regions 기반(검증된 시군구 우세오행: 중구土·마포구水·동대문구木·부산남구火·
  서대문구金·종로구金weak·제주시水weak). 불변식: 5오행 용신 최상위·용>희>한 순위·기신 risk_flag·
  구신 avoid·약신뢰(conf<0.40) score_cap 65·강신뢰>약신뢰·거주지 방위 산출/미산출·동명(중구) 모호
  노트·미등재 노트·scope(제주/수도권) 한정·읍면동 계산+시군구 surface·전 케이스 terrain_data 미연결.
- **#5 가중치 튜닝 준비**: scripts/region_weights_report.py — 튜닝 knob(사전 5종 + 엔진 상수 7개)을
  한곳에 모으고 현재 스냅샷 행동 베이스라인(dominance·우세오행·레이어·신뢰도 분포) 출력 →
  region_weights_review.{json,md}(감사 산출물, gitignore). 실제 값 변경은 전문가/코호트 데이터 필요라
  surface만. 베이스라인: dominance unknown1780/weak3397/single138/composite17, 우세 土1477·水1079.
- 검증: 신규 테스트 23(golden 21 + report 2), unit 1020 pass·1 skip, ruff·mypy clean. 엔진 결과 불변.
- **지역 오행 엔진 데이터-전 작업 전부 완료.** 남은 것은 외부 지형 데이터 수급(수동·로그인) → 빌드
  실행으로 방향성/physical/landcover 활성, DEM 풍수(별도 알고리즘), 전문가 가중 감수.

---

## 지역 오행 엔진 — P4-SearchSeed(검색 기반 부트스트랩) ✅ (2026-06-26)

공식 GIS 원천 수급(수동·로그인) 전, 시군구명 + 지형 키워드 검색 → 좌표 API로 external_geo_feature를
빠르게 생성하는 부트스트랩(사용자 확정). 읍면동 전수 검색 금지(시군구 250×키워드 9=2,250건만,
읍면동은 on-demand). 검색 데이터 오탐 대비: 카테고리 거름 + 낮은 confidence + review_status.

- 공유 코어 추출: region_directional.py(build_directional_summaries — GIS·검색 공용 방위 집계).
  build_region_directional_summary.py를 이 함수로 리팩터(출력·테스트 불변 확인).
- search_seed.py 코어: QUERY_KEYWORDS(9), classify_feature_type(카테고리>이름>검색어, 비지형 reject),
  element_vector_for, base_confidence, project_equirect(pyproj 불필요), dedupe(300m·같은 이름·같은 type
  병합, source_count·지역·confidence 보정), SearchSeedFeature 모델.
- 스크립트 5종: build_search_seed_queries → fetch_search_seed_features(Kakao Local provider, 키
  KAKAO_REST_API_KEY 환경변수·없으면 graceful·provider 주입 테스트·재시도·rate limit) → classify →
  dedupe → build_search_seed_direction_summary(lon/lat 등거리 투영→방위 요약 json/csv).
- 산출 doc/gis/search_seed/(gitignore). provisional이라 compiled 운영본 자동 덮어쓰기 금지 —
  검수 후 수동 승격(공식 GIS 확보 시 교체). 하천/해안은 대표 feature로만.
- 검증: 신규 테스트 10(분류·오탐 거름·중복 병합·쿼리 생성·fake provider fetch·키 없음 graceful·
  방위 요약 e2e·투영 정합), unit 1030 pass·1 skip, ruff·mypy clean. 쿼리 생성 실측 2,250건.
- **활성**: KAKAO 키 설정 → 5스크립트 순차 → region_directional_summary_search_seed.json →
  (검수 후) compiled 승격 → DirectionalFeatureAdapter 활성. 실제 API 호출은 키/네트워크 필요(환경 블로커).

---

## Topic Builder 모듈 확장 — 도메인 신호형 5종(M01·M02·M09·M11·M12) ✅ (2026-06-26)

docs/09 4·5장. 미구현 11개 중 도메인 신호 매핑형 5개를 M07 패턴으로 구현(기존 엔진 조립 어댑터,
외부 데이터 불필요). 50장 총운 리포트 섹션(F-14→M09 등) 품질 직결.

- 공용 헬퍼 `_domain_series_findings`/`_domain_topic`: 기간 내 composite의 domain(+event_key)
  신호를 시계열·findings로 확정(점수 최종, LLM은 서술만). 모듈은 domain/event_keys/label/style만 지정.
- M01 love_timing(relationship: relationship_start/end) · M02 marriage(relationship: marriage/
  childbirth/family_change) · M09 wealth(wealth 전체) · M11 health(health) · M12 education_exam(education).
- 정책 톤(절대원칙 3·8): M09=생활형 횡재 가드(번호·종목 픽 금지·당첨 단정 금지·과몰입 금지),
  M12=당락 확정 금지, M11=의료 단정 금지·전문의 상담, M02=운 저점 큰 결정 보류, M01=만남 단정 금지.
- 검증: 신규 테스트 12(도메인 격리·이벤트 필터·정책 톤·결정성·간지 동반·미구현 모듈 raise), 기존
  test_planned_module을 M04로 갱신(M01 구현됨). unit 1042 pass·1 skip, ruff·mypy clean.
- 남은 미구현 6개(M04 부모·M05 자녀·M06 직장관계·M08 사업·M13 비교·M14 과거검증)는 subject/관계
  엔진·past_validation 역방향 등 추가 배선 필요 — 후속 배치.

---

## Topic Builder — M14 past_validation 모듈(역방향 엔진 어댑터) ✅ (2026-06-26)

docs/09 4장, E7. M14는 composites가 아니라 past_validation.py 엔진을 역방향으로 재사용 —
birth/scorer/compute를 extras로 받아(M03/M10처럼) 과거창 후보를 findings로 확정. 점수·근거는
엔진이 확정(콜드리딩 가드: 연 ≤2·근거 필수), LLM은 사실 확인형으로만. 리포트 F-08/F-09 의존 해소.
정책 톤: 콜드리딩 금지·이미 일어난 일은 사실 확인형. **Topic Builder 11/15 완료**(미구현 M04/M05/
M06/M13 — natal 십성 구조·subject·compatibility extras 필요). 신규 테스트 1, unit 1042 pass·ruff·mypy clean.

---

## Topic Builder 완성 — M04·M05·M06·M13 (육친 구조형 + 궁합) 🎉 (2026-06-26)

docs/09 4장. 남은 4종 구현으로 **M01~M15 전 15종 완성**.

- 육친 구조형(공용 _relation_axis_context, extras=natal_ten_god_dist): M04 parents(인성 편인·정인)·
  M05 children(식상 식신·상관)·M06 workplace_relations(관성·비겁). natal 십성 축 세력(상대 비율) +
  relation_profiles 구조축(parent_child/colleague) + 기간 도메인 신호를 findings로 확정.
- M13 bond_compare(엔진 위임): compatibility_engine(E13) 재사용 — self/partner result·useful_gods를
  extras로 받아 안정(보완/마찰)·끌림(자극) 2축 findings. 끌림≠좋은 궁합·당락 단정 금지(절대원칙 8).
- 정책 톤: M04 수명·질병 단정 금지, M05 출산 여부 단정 금지, M06 인사 결과 단정 금지, M13 천생연분/
  최악 단정 금지.
- 테스트 갱신: planned-module raise 테스트를 '전 15종 빌더 연결' 검증으로 교체, M04/M05/M06/M13 신규.
  unit 1042 pass·1 skip, ruff·mypy clean. **Topic Builder M01~M15 전 15종 구현 완료.**

---

## 출시 점검 — Topic Builder 제품 배선(옵션1) + 거주지 지역 평가·추천 ✅ (2026-06-26)

점검 결과 Topic Builder M01~M15는 정의·테스트만 됐고 build_topic_context가 프로덕션 미호출이었음
(리포트/채팅은 자체 조립). 옵션1로 실제 배선 + 거주지 기반 지역 블록 추가(사용자 확정).

- **리포트 배선**(commit 3fbba96): _ReportData에 topic extras(지연 composites·natal 분포·birth·
  partner) 추가, build_section_context가 섹션 module_calls를 build_topic_context로 실행해 확정
  findings + 모듈 특화 정책 톤(절대원칙 8) 주입. 재물(F-16/W-*)→M09 횡재 가드 등 검증.
- **채팅 배선**: _topic_module_context — 질문 도메인(직업/재물/건강/시험/연애)→모듈 실행→구조 블록에
  확정 신호+정책 톤. relocation은 기존 지역/이사 경로 담당, general 등 비토픽은 빈 줄.
- **리포트 거주지 지역 블록**: 거주 정보(ExtendedProfile.residence.region)가 있으면 현 지역 평가
  (용희기구신×지역오행) + 살면 좋은 지역 추천(읍면동 계산→시군구 surface)을 F-20(개운·보완)·
  RL-04(이사 방위)에 주입. compiled 미빌드·무거주지·무DB graceful. 채팅 지역은 권장(P4-A) 유지.
- **프론트**(commit 07345e8): 테마사주 화면 페이지 분량 callout 전부 삭제(themes.ts pages 필드·
  "22개 장"·{t.pages}). tsc·테스트·build 통과.
- 검증: 신규 테스트 4(리포트 토픽·채팅 토픽·거주지 블록 + 페이지분량 회귀), unit 1045 pass·1 skip,
  ruff·mypy clean. 기존 리포트/채팅 회귀 불변.

---

## 멀티턴 지역추천 질문 결함 4종 수정 ✅ (2026-06-26)

데굴님 실로그 지적: '7월 4일에 서울 중구로 이사' 직후 '서울 내에 살면 좋은 지역 추천' 질문에서
(1)7/4 시점 과잉 승계 (2)서울 스코프 무시→광주 추천 (3)간지 이중병기 (4)7/4를 乙未월로 오배정.

근본원인 — 추천형 공간 질문이 query_parser에서 domain=general·target_region=None으로 떨어져,
conversation.py가 직전 턴(7/4 이사)의 날짜·이사의도를 통째로 승계 → 일운/질문기간/월별 타이밍
장치가 전부 주입되고, 지역 블록은 스코프 없이 전국 폴백(광주)으로 빠짐.

- R1-a query_parser `_DOMAIN_WORDS[relocation]`: '살면 좋은/살 곳/거주지/어디 살/지역 추천' 등
  추천형 구를 relocation으로 감지 → 직전 dated-eval query_type 미승계.
- B query_parser: `_SIDO` + 거주·추천 맥락에서 시도 스코프('서울')를 target_region에 채움
  (시군구 목적지·타도메인 '서울에 재물운'은 미오염). → 지역블록이 서울 시군구로 한정.
- R1-b conversation.py `_PLACE_SEEKING_RE`: 공간('어디') 질문을 시점 미승계 가드에 추가
  (_TIME_SEEKING_RE와 동일 취지) → 7/4 일운/질문기간/응답형식/유력달 장치 전부 미주입.
- R1-c: 위 승계 차단의 cascade로 타이밍 장치가 제거돼 별도 코드 불요(재현 확인).
- C chat_service `_normalize_ganji_gloss`: '갑오(甲午(갑오))'·'己卯(기묘)(기묘)' 중첩·중복 병기를
  '갑오(甲午)'로 collapse(LLM 과글로싱 보정, 엔진 입력은 순수 한자). 응답 후처리에 적용.

재현 검증(2턴 dry_run): 질문기간/일운/2026-07-04/광주 0건, '서울특별시 중구 적합 78' surface,
이중병기 정규화 단위테스트 통과. 신규 테스트 3, unit 1048 pass·1 skip, ruff·mypy clean.

---

## 지역 오행 사실 질문 직접응답 라우트 ✅ (2026-06-26)

데굴님 지적: '창원 성산구의 오행은 뭐야?'가 too_broad('범위가 넓어요')로 빠짐. 지역 오행은 사주·시점
무관 고정 사전계산값이라 단순 조회인데 분석 질문으로 오인됨.

- chat_service `_region_element_fact`: 시군구/지명+'오행' 패턴이면 지역 엔진 resolve_region→get_profile로
  우세 오행을 직접 답한다(LLM 미호출). assess(too_broad) 게이트 앞 사실 라우트로 early-return.
- 모호 지명은 확인 질문, 미등재·compiled 미빌드면 일반 흐름 폴백. '내 사주 오행 분포'는 시군구
  접미가 없어 미매칭 → 개인 분석 경로 유지(오염 방지). 지형 GIS 미연결 1차 추정 고지 포함.

검증: '창원 성산구'→'경상남도 창원시 성산구 … 토(土) … 1차 추정' answered. 신규 테스트 1,
unit 1049 pass·1 skip, ruff·mypy clean.

---

## 통합시 자치구 지역오행 폴백 결함 수정(전수) ✅ (2026-06-26)

데굴님 지적: '마산합포구 오행'이 창원 성산구와 똑같이 土로 나옴. 원인 — region_elements.json에
통합시 자치구(창원·수원·성남·고양·용인·청주·천안·전주·포항) 32구의 자체 항목이 없어 상위 도시
한자로 폴백, 昌原의 原(土)이 지배 → 자치구 고유 한자(마산합포 浦=水 등) 미반영, 자치구끼리 동일값.

- region_elements.json에 통합시 자치구 32개 전수 등재(자체 구 한자 + 오행). 토큰화되는 18구는 구
  한자 산출(마산합포 馬山合浦→水, 수지 水枝→水, 진해 鎭海→水, 덕양 德陽→火, 성산 城山→土 등),
  추상 지명 14구(長安·盆唐·萬安 등)는 부모 도시 큐레이션 오행 상속(명리 임의판단 회피). reviewed:false.
- 재빌드: region_element_profiles_v1.json(한자조인 248/250). 마산합포구 土0.978→水0.53(土0.46),
  창원 4구가 더는 동일 土 아님.
- 회귀 가드: test_region_golden 통합시 자치구 테스트(마산합포≠성산·水/土/火 검증). 사전검증 68파일
  통과, unit 1050 pass, ruff clean. compiled 스냅샷 git 추적분 갱신.

---

## 지역 지형(GIS) 데이터 무로그인 연결 — Tier B 파이프라인 구축 ✅ / geo 가중 보정은 감수 대기 (2026-06-26)

데굴님 요청: 지형 데이터를 로그인·API 없이 연결. 무로그인 루트 확인·구축 완료, 단 활성화는 보류.

- **무로그인 소스(이 환경 접근 확인)**: OSM south-korea(Geofabrik shp, 544MB) — 행정경계·토지피복·
  수계 / Natural Earth 10m land(GitHub raw) — 해/육 / Copernicus DEM GLO-90(익명 AWS S3, 44타일
  114MB) — 고도·경사. 전부 무로그인/무API.
- **GIS 스택**: geopandas·shapely·rasterio·pyproj·fiona pip 설치(GDAL 번들 휠, apt 불요).
  pyproject [geo-build] extra로 기록(빌드타임 전용 — 런타임 엔진은 compiled만 사용).
- **빌드 파이프라인**: scripts/build_geo_features.py — 지역 경계는 bbox가 아니라 **OSM 행정경계
  실폴리곤(centroid-containment 매칭, 마산합포구 338km²·강릉 1968km² 정확)**. 실폴리곤×지형 레이어
  면적 비율(water=바다+내륙, forest/agri/urban/industrial) + DEM(mean_elevation·slope·
  mountain_score) 산출. 5236/5332 지역 신호. region_geo_features.jsonl(gitignore — 재생성 가능).
- **핵심 발견(활성화 보류 사유)**: 데이터는 정확히 연결되나, geo 신호 가중(region_layer_weights·
  region_geo_signal_rules, **reviewed:false 초안**)이 산악국가 특성상 ubiquitous 지형을 과대반영 →
  physical_geography 0.45(mountain_score)로 전 지역 土 지배, 또는 forest 木 지배. 한자 명칭(0.15)이
  묻힘. 이름-주도 보정(한자 0.40)을 시험해도 마산합포(浦 水 vs 무학산 木/土)처럼 항·만+산악 혼재
  지역은 단일 오행이 안 정해짐 — **명리 가중 보정/per-region 큐레이션은 전문가 감수 영역(절대원칙 5)**.
- 따라서 커밋 상태(한자 기반: 마산합포 水, 성산 土)를 유지하고, Tier B는 **연결 완료·활성 대기**로
  둔다. 감수 후 build_geo_features→build_region_profiles 재실행으로 활성화. golden 픽스처 7개는
  활성화 시 함께 재생성 필요(geo가 추천 랭킹·신뢰도 변경 — 회귀 게이트 정상 작동 확인).

---

## 풍수 형국·방위 역할 레이어 — 설계검토 + P5-1 스캐폴딩 ✅ (2026-06-26)

데굴님 외부 자료(산·물·도로·좌향·양택 길흉 결합) 검토 → docs/12 §14 스펙 + 무보정 스캐폴딩.

- **검토 결론**: 방향성 정합. 제안의 절반 이상이 이미 설계됨(region_feature_direction 스키마·
  region_directional·region_direction의 팔괘 분리·山=土 context_rule). 핵심 신규는 사신사 좌향·
  형국 채점·팔택·비보. 직전 'Tier B 가중 보정 벽'이 형국에서 더 커지므로 분리 계약 + 감수 우선.
- **§14 스펙(코드 0)**: 분리 계약(A 오행/B 형국/C 방위/D 추천·비보, 점수 미혼합), TerrainRole/
  FormEffect enum, 좌향 모드 A(8방위)/B(facing→전후좌우), 사신사, FengshuiFormProfile 채점+페널티,
  물길·도로/철도 특수처리, 팔택 optional 가드, 비보, SearchSeed 컬럼, 결과 분리 블록, P5-1~3 순서.
- **P5-1 스캐폴딩(무보정·회귀 무영향)**: shared_types에 TerrainRole·FormEffect·
  DirectionalSectorProfile·FengshuiFormProfile·RemedySuggestion 추가(점수 0 기본·available=False).
  fengshui_form.py sasinsa_sectors(좌향→전후좌우 sector, region_direction 8방위 컨벤션 동일) —
  남향=현무 북·동향=현무 서로 '북산 고정' 오류 방지. 채점·도로/팔택 가중은 감수 후 P5-3.
- 검증: 신규 테스트 8, unit 1059 pass, ruff·mypy clean(133 files). 추천 경로 미개입(스캐폴딩만).

---

## P5-2 이산 지형 feature 추출 ✅ (2026-06-26)

docs/12 §14-10 P5-2 — 방향성 지형(점·선 feature)을 OSM/NE에서 추출해 ExternalGeoFeature 계약으로
직렬화(면적 비율 Tier B와 별개 경로).

- scripts/extract_osm_geo_features.py: OSM natural=peak(16,553)·waterway river/canal anchor(11,180)·
  water_a 호수 centroid(2,141)·landuse forest 대형 patch(4,561) + NE 해안선 anchor(14,410) =
  **48,845 feature** → doc/gis/external_geo_features.csv(gitignore). element_*는
  region_geo_feature_elements.json 규칙(산봉우리 土0.75/木0.25 등).
- 도로·철도는 기본 제외(--with-transport opt-in): 오행 매핑 감수 대기 + 실제 쓰임은 8방위 element가
  아니라 road_rush 直충 penalty(P5-3 형국 — 최근접 도로 bearing)라 다른 소비자. inert 점 수십만개
  미포함(48,845 vs 248,145).
- 검증: ExternalGeoFeature 계약 파싱 OK, 남산·관악산·무학산·북악산 봉우리 土0.75/木0.25. 기존
  build_region_directional_summary.py로 end-to-end 증명(40,369행/5,065 읍면동, TEMP 출력) —
  청운효자동 N방위 top=홍제천(하천)·형제봉(봉우리). **directional 스냅샷은 미커밋(활성=P5-3 감수)**.
- unit 1059 pass(런타임 미개입), 추출 스크립트만 추가. CSV·원천 gitignore.

---

## P5-3 슬라이스 1 — form_quality 채점 코어(좌향 유무 2모드) ✅ (2026-06-26)

데굴님 §14-12 감수 기준으로 P5-3 착수. 핵심 분리 원칙(형국 점수 ≠ 지역 오행 벡터)을 순수 함수로
먼저 구현 — 추천 경로 미개입(무회귀), 가중 cap은 감수값 그대로.

- docs/12 §14-12: P5-3 활성화 보정 기준 권위 기록(명칭 분리 directional_terrain≠relative_direction,
  활성화 순서, 점수 cap 첫릴리즈/확장, form_quality 산식 2모드, 도로/철도 form penalty 전용,
  거리버킷·반경, OSM<공식GIS confidence, golden 20+ 카테고리, 금지 8).
- fengshui_form.py: compute_form_quality_open(좌향 없음 — 산수분포/수계접근/지형균형, 사신사
  강판정 금지)·compute_form_quality_facing(좌향 있음 — 현무/주작/청룡/백호 §14-3)·form_quality_bonus
  (±cap, base_match_score 미반전). 신호는 directional_terrain(RegionDirectionalElementSummary 8방위)
  에서 도출. road_rush=0(transport OFF). 확정 가중은 §14-12 산식 그대로.
- 검증: 신규 테스트 3(산수혼합 가산·수변과다 감점·남향 현무=북·cap 불반전), unit 1062 pass,
  ruff·mypy clean. 추천 경로·기존 golden 불변(미배선).

남은 슬라이스: P5-3A 배선(directional 스냅샷 build·shadow evidence)·P5-3 통합(form_quality_bonus를
recommend에 cap 결합)·road/rail form penalty(transport)·팔택 stub OFF·golden 20+.

---

## P5-3A — directional_terrain·form_quality shadow 배선(점수 미반영) ✅ (2026-06-26)

데굴님 지시: 점수 결합 전, 관측 가능성부터. directional_terrain/form_quality를 추천 payload에 노출하되
match_score·랭킹·element_vector 불변.

- 방향성 스냅샷 build(extract_osm_geo_features→build_region_directional_summary, 40,369행/5,065 emd,
  31MB → gitignore·재생성, 런타임 graceful). 소형 compiled(profiles/admin)만 추적.
- region_recommendation_orchestrator: _directional_payload를 방위별(N/E/S/W/간방) earth/wood/water +
  top_features(≤5) + confidence로 enrich. _form_quality_payload 추가(score_raw·bonus_preview·
  **applied_to_score=false**·evidence). 둘 다 directional adapter 있을 때만(opt-in shadow).
- REGION_REASONING_DIRECTIVE: 좌향 없으면 사신사·배산임수 확정 금지('북쪽 산지 신호' 식만) +
  directional_terrain≠relative_direction 분리 명시 + form_quality 점수 미반영 인용 금지.
- 검증: directional 유무로 match_score·랭킹 **불변**(shadow), form_quality.applied_to_score=false,
  relative_direction(direction)·directional_terrain 별도 필드, 사신사 라벨 미생성, top_features ≤5.
- 신규 테스트 6(합성 adapter 결정론 + 실스냅샷 skipif), unit 1068 pass, ruff·mypy·dict validate clean.
  기존 golden 불변(orchestrator가 directional 미주입 → terrain_data_available=false 유지).

다음(각각 별도 게이트): P5-3B nearby_discrete_geo_layer(cap 0.18) / P5-3C form_quality_bonus(±5) /
P5-3D road_rush(좌향) / P5-3E 팔택 stub. ※ B와 C는 동시 적용 금지(신호 추적성).

---

## P5-3B — nearby_discrete_geo 0.18 블렌드(지역 오행 보강) ✅ (2026-06-26)

데굴님 §14-12: P5-2 이산 방향성 지형을 지역 오행 벡터에 cap 0.18로 일부 반영. directional_terrain
(shadow)·form_quality와 별도 신호로, 단독 적용(추적성 — B/C 동시 금지).

- 핵심: 레이어 재정규화(절대원칙 11) 때문에 면적비 GIS 부재 시 raw 0.18이 ~0.5로 과대 → **유효
  블렌드 비율**로 캡(normalize(0.82·base + 0.18·discrete)). 0 dominant flip(마산합포 水·성산 土·
  종로 金 불변), EMD 단위 미세 보강(부모 상속 EMD에도 적용 — 그 지역 주변 지형 자체 신호).
- 재현용 소형 산출물 compiled/region_nearby_discrete_v1.json(315KB, region→5벡터, 추적). 31MB
  directional 요약(gitignore)에서 추출. build_region_profiles가 로드해 블렌드.
- **footgun 수정**: 면적비 geo(Tier B, 감수 전)를 기본 로드하던 _DEFAULT_GEO 제거 → argv[3] 명시
  시만 활성(미적용 시 재빌드가 Tier B 土/木 과잉으로 오염되던 문제 차단). 재현성 확보(fresh clone =
  hanja+discrete 동일).
- 검증: golden/p4/engine 49 + 전체 unit 1068 pass, ruff·mypy·dict validate clean. 추천 랭킹 불변
  (discrete가 EMD 미세 보강이라 golden SIG 케이스 무영향).

---

## P5-3C — form_quality_bonus 추천 점수 반영(cap ±5, 재랭킹) ✅ (2026-06-26)

데굴님 §14-12: form_quality(좌향 없음 산수분포/수계접근/균형)를 추천 점수에 cap ±5로 가산. B와
별도 슬라이스(추적성). directional adapter 있을 때만 적용(graceful).

- recommend_payload: base_match_score 보존 + form_quality_bonus(±5 cap, _applied_form_bonus)
  가산 → 보정 점수로 재랭킹. surface grouping도 보정 점수 사용. applied_to_score=true·bonus_applied
  노출. cap이 명확한 우위를 못 뒤집음(§14-12 금지 7).
- 검증: 월계동 78→82(+4) 등 ±5 내 보정, base 보존, 내림차순 유지. golden 불변(directional 미주입
  orchestrator라 base 그대로). unit 1068 pass, ruff·mypy clean.

---

## P5-3D/E — road_rush penalty + 팔택 stub(OFF) ✅ (2026-06-26)

§14-12 마지막 슬라이스. 둘 다 현 추천 흐름(좌향 입력 없음·transport OFF·팔택 OFF)에서 비활성 —
역량 스캐폴딩(점수 무영향).

- D road_rush(§14-5·§14-12): road_rush_signal(front_road_m/front_rail_m 근접 티어 — 도로 100m 0.7/
  300m 0.4, 철도 100m 1.0/300m 0.6, 미공급 0)을 compute_form_quality_facing에 결합(좌향 있을 때만
  直충 penalty). 좌향 없는 지역 추천에선 항상 0(직충 강판정 금지). transport feature는 extract의
  --with-transport opt-in.
- E 팔택(§14-6): PaltaekDirection·PaltaekResult 타입 + compute_paltaek stub(기본 OFF→빈 결과,
  enabled여도 본명궁 산식 감수 대기로 confidence 0). 용희신과 별개 체계 — 추천 점수 자동 결합 금지.
- 검증: 신규 테스트 2(근접 티어·직충 점수 하락 / 팔택 OFF), unit 1070 pass, ruff·mypy clean.

→ P5-3 전 슬라이스(A shadow·B 0.18블렌드·C form bonus±5·D road_rush·E 팔택OFF) 완료. 추가 활성
(directional_terrain_bonus ±3, form ±8/road −6 확장, 팔택 본명궁 산식)은 감수 후 §14-12 확장표 적용.

---

## 전문가 감수 시군구 오행 통합 — reviewed:true 권위 레이어 ✅ (2026-06-26)

데굴님 제공 CSV(전문가 감수 230 시군구 오행, CP949). 세션 내내 막혔던 'reviewed:false 가중 보정'의
ground truth — 한자 토큰화로 틀렸던 28%(61/219)를 전문가값으로 바로잡는다.

- dictionaries/_src/sigungu_ohaeng_expert.csv(UTF-8 디코딩 소스) + scripts/build_sigungu_expert_dict.py
  → dictionaries/region/region_sigungu_expert_ohaeng.json(217 entry, region_code 매핑).
- 엔진 _expert_layer: 시군구에 전문가 entry 있으면 한자 토큰화를 덮는 권위 레이어(_combine 단독
  non-phonetic이라 ~0.97 지배). 복합오행은 primary 우세 벡터(2원소 0.55/0.45), reviewed 신뢰도
  0.85(검수필요 0.60). EMD는 전문가 SIG 상속 + P5-3B discrete 블렌드.
- 경계: 통합시(수원·창원 등 시 단위)는 자치구 코드 미해소라 제외 → 자치구 자체 한자 유지(마산합포
  浦=水·성산 城山=土 그대로, 창원 火에 안 묻힘). 지명(여의도·묵호) 제외. 검수필요(무주·세종) reviewed:false.
- 검증: 강남 火(江南→水 아님)·노원 木·강서 金·종로 金 전문가 적용, 마산합포 水 유지. golden 6건
  재생성(전문가로 高신뢰화된 종로·제주·마포가 cap-weak 예시 부적격 → 수원장안·세종 약신뢰로 repoint,
  마포 水木 92→76). 신규 테스트 1, unit 1071 pass, ruff·mypy·dict validate(69파일) clean.

---

## Report Context Reduction — 다년 테마풀이 섹션 토큰 상한 초과 수정 ✅ (2026-06-27)

라이브 테스트 중 RPT_FOCUS(직업운, 2026-06~2031-12, 5.5년) 생성이 `report_focus_section:
입력 10212tok > 상한 10000tok`로 6/8 섹션(J-06)에서 실패. DB의 실패 job(spec·subject)을
그대로 재현해 원인 규명.

- 근본 원인: `month_overview_lines`가 예측 창의 **모든 달을 빠짐없이** 출력(2026-06-16 단년
  반복방지 의도). 다년 창에선 ~84줄(3,651tok)로 폭증해 J-06만 상한 초과(다른 7섹션은 5~7k 여유).
- 구조적 결함: docs/09 L333이 규정한 "상한 초과 → Context Reduction 재실행"이 **chat 경로엔
  있으나(serialize_with_guard→too_broad) report 경로엔 부재** → 가드 예외가 job 전체를 실패시킴.
- 수정(사용자 승인 Option 1 — 초과 시에만 축소): report 경로에 Context Reduction 추가.
  `generate_fn`이 `TokenBudgetExceeded`를 잡아 `reduction_level`을 올려 컨텍스트 재구성·재호출
  (`_MAX_REPORT_REDUCTION=2`). level1=다년 월별 흐름 ★주목 달만(연도별 top3+강한 용/기신운),
  level2=연도별 흐름도 ★주목 해만. `month_overview_lines`/`year_spectrum_lines`에 `notable_only`
  파라미터(기본 False=전체 유지) 추가 — **상한 내 섹션·단년 풀이는 0단계로 12개월 그대로**.
- 검증: 실패 job 재현 측정 J-06 10,123→8,343tok(level1 자동 선택), 나머지 7섹션 level0 유지.
  report 테스트 82 pass, ruff·mypy clean, 전체 스위트 실패셋 클린트리와 동일(회귀 0 — 유일 실패
  test_too_broad_returns_suggestions는 사전 존재·LLM 가용성 env 의존, 본 변경 무관).
- 후속(2026-06-27 사용자 승인): `report_focus_section`·`report_full_section` 입력 상한 10,000→15,000
  (llm_guard CALL_LIMITS + docs/09 8장 표 동기화). 다년 풀이도 월별 흐름을 **축소 없이** 보존 —
  재현상 8섹션 전부 level0 통과(J-06 10,123<15,000). Context Reduction은 15,000 초과 극단 안전망으로
  잔존. guard 테스트 7 pass, ruff·mypy clean.

---

## 병기 중복 정리 — '정해(丁亥(정해))'·'정재(정재)' 제거 ✅ (2026-06-27)

데굴님 지적: 총운(RPT_FULL) 본문에 `정해(丁亥(정해))`·`기해(己亥(기해))`·`정재(정재)`처럼
한글 병기가 이중 중첩. 저장된 완료 job(22섹션) 스캔 결과 27건(F-02·04·06·07·10…).

- 원인: ① **중첩** — LLM이 '기해(己亥)'(역순 병기)로 쓰면 `_sanitize_output`의 `_normalize_ganji`가
  괄호 안 한자 '己亥'만 다시 병기(`(?!\()`가 바깥 한글만 건너뜀) → '기해(己亥(기해))'. ② **자기중복**
  — LLM이 ganji '한자(한글)' 병기를 십성·신살(정재·상관·천문성 등)에까지 과잉 일반화해 '정재(정재)'.
  입력 프롬프트는 순수 한글로만 제공(유도 아님) — ②는 LLM 출력 습성.
- 수정: `_sanitize_output`(채팅·리포트 공통 단일 지점)에 `_normalize_ganji` 뒤로 결정적 2패스 추가.
  `_NESTED_GLOSS_RE` 한글(한자(한글))→한자(한글)(바깥 한글 버리고 한자 신뢰 — '임인(壬辰(임진))'
  불일치도 '壬辰(임진)'으로 일관), `_SELF_GLOSS_RE` X(X)→X. 정상 '己亥(기해)'·'해수(亥水)'는 불변.
- 검증: 저장 22섹션 재적용 중복 27→0, 정상 병기 보존. 신규 단위 테스트 1(중첩·불일치·자기중복·보존),
  llm_client 9 pass, 전체 스위트 회귀 0(클린트리 동일 — 유일 실패 too_broad는 무관). ruff·mypy clean.
  ※ 기 저장 보고서는 미소급(재생성 시 정리). 필요 시 report_jobs.result 일괄 재정리 가능.

---

## 총운 데이터-목적 시간범위 불일치 교정 — 과거 섹션에 미래 후보 혼입 제거 ✅ (2026-06-27)

데굴님 지적: 총운 'F-07 대운 흐름 개관'이 이후 5년만 자세히 풀림 → 전수 감사. 원인은
`build_section_context`의 `elif not is_natal_section:`이 비-원국·비-도메인 섹션 **전부**에
`luck_block()`(=[대운표]+미래 +5년 이벤트 후보 4블록[이벤트후보·합작용·발현분기·내부근거])을
무조건 주입한 것. docs/10 시간범위와 대조 시 **2부 과거 섹션이 미래 후보를 받는** 명백한 불일치.

- 감사 결과(22섹션): F-07(출생~현재 대운개관)·F-08(과거 이벤트 복원)·F-09(과거 검증)이 미래
  2026~2031 월별 후보 7건 수신(F-08/09는 올바른 M14 과거 데이터와 **공존**). 메타 F-21(요약카드)·
  F-22(부록=달력·용어)도 원시 미래 클러스터 부적절. F-10~F-18(현재·미래·도메인 전망)은 정합.
- 수정(2026-06-27 사용자 승인 Option2): `luck_block(daewoon_only=True)` 추가 — [대운표](생애
  backbone, 과거 포함)만 남기고 미래 후보 4블록 생략. `_DAEWOON_ONLY_SECTIONS={F-07,F-08,F-09,
  F-21,F-22}` 적용. F-07·08·09 전용 가이드 추가(시간범위 '출생~현재' 한정, 미래 연·월 디테일은
  3·4부 몫임을 명시). 현재·미래·도메인 섹션은 불변.
- 검증: 재감사 — F-07/08/09/21/22 미래월 7→0(대운표·M14 보존), F-10/13 미래 후보 유지. body
  3.8~5.6k tok(starved 아님). report 테스트 140 pass, 전체 1304 pass(회귀 0), ruff·mypy clean.
  ※ 기 저장 보고서 미소급 — 재생성 시 정합.

---

## F-22 부록 간지 달력표 — 결정론적 표 자동 첨부 + 분량 캡 면제 ✅ (2026-06-27)

데굴님 지적: 총운 F-22 '간지 달력표 + 용어 해설'에 **실제 표가 안 나오고 산문 요약만** 나옴.
원인 — ① F-22에 간지 달력표 데이터 자체가 없고(대운표만), ② LLM은 간지를 못 지어내(절대원칙 1)
재료 없이 "요약"만, ③ `_repair_section`이 `target_chars.max`로 절단(데굴님 '정형적 분량 제한').

- 해법(2026-06-27 사용자 승인 — 범위: 대운 생애·세운 10년·월운 10년, "제일 비싼 상품"):
  간지 달력표를 **엔진이 결정론적으로 렌더링**(LLM 미생성)해 섹션 끝에 첨부, **분량 캡 면제**.
  - `_ReportData.ganji_calendar_md()` — 대운(생애 `daewoon_table`)·세운(`daewoon.sewoon` 향후
    10년)·월운(`luck_months` 연도별 10년=120개월). 간지 한자(한글)+천간/지지 십성. RPT_FULL=10년,
    그 외=1년 스코프. `_ganji_ko`로 병기(표는 `_sanitize_output` 미경유라 직접 병기).
  - `generate_report`: `builder.build()` 후(=_repair_section 절단·정합성 검사 뒤) F-22(_GANJI_
    CALENDAR_SECTIONS={F-22,Y-12})에 표를 append → 절단·검사·간지변형 대상 제외. total_chars 재계산.
  - F-22/Y-12 가이드 변경(표 직접 생성 금지·읽는 법+용어 집중) + terminology.json(53항목) [용어 사전]
    주입(용어 해설을 검수 사전 기준으로).
- 검증: 표 생성 — 대운 10행·세운 10행(2026~2035)·월운 120행(10연도그룹), 2026=丙午(병오) 정확.
  F-22 본문 [용어 사전] 주입·미래 후보 무·총 7.7k tok(<15000). 신규 테스트 1, report 6 pass,
  전체 1304 pass(회귀 0), ruff·mypy clean. ※ 기 저장본 미소급 — 재생성 시 표 첨부.

---

## 연애·결혼 시기 고도화 (Marriage Timing Enhancement) — 설계 + Phase 1·2 적용 🚧 (2026-06-30)

전문가 영상(연애·결혼 시기 판정법) 대조 분석. 기존 로직(배우자성 투출·무관/다관·배우자궁
형충·생애단계·일지복음·비식재흐름결혼·성별가중)은 영상보다 정교하나, **영상의 두 기둥**(일간
干合 awareness 신호 / 일지 투출 글자 운 회귀 트리거)과 방합·관식동반이 갭으로 확인됨.

- **SSOT 설계 문서 신설**: `doc/v2_2/MARRIAGE_TIMING_ENHANCEMENT.md`(v2, 사용자 2차 리뷰 반영).
  핵심 재설계 = 결혼 시기를 단일 activation이 아니라 **`발동도 × 단계 × 안정성 × 현재 관계상태`**
  + **2축 산출**(activation_score × stability_score)로 본다. "마음 동함 ≠ 결혼" 과판단 차단이 1순위.
  - MT1 일간 干合 배우자성(awareness, 단독 action 금지) / MT2 일지 투출 글자 회귀(글자/십성/오행
    3종 차등, 배우자성만 action) / MT3 방합 action(spousePalace 게이트) / MT4 육합>삼합>방합 subtype
    차등(HAP 붕괴 금지) / MT5 partner+child 동반(family_formation_awareness, 출산 직승 금지) /
    MT6 배우자성 위치별 혼기 = static prior(event 아님).
  - marriage_stage 6단계(awareness/contact/relationship/commitment/formalization/family_expansion),
    commitment/formalization_marker 게이트, relationship_context_gate(점수 무개입·라벨/문구/confidence만),
    layer confluence, 단계별 cap, risk_flags 재분기(충+기신 배우자궁=marriage 아닌 relationship_change).
  - "거의 100%" 표현 제거 → strong_confluence(marker 대체 불가, 단계 승급만).
- **§14 1·2단계 적용(비파괴)**:
  - docs/02 E4 — marriage_stage refinement 표(base 5단계 미확장, completion 매핑).
  - docs/05 — partner_star 추상화 규칙(여=관살 officer_killing, 남=재성 wealth, gender 미상 양 기준 병기).
  - `shared_types/marriage_timing.py` 신설 — `MarriageStage`/`MARRIAGE_TO_BASE_STAGE`/`TenGodGroup`
    enum + `PartnerStarRule`·`resolve_partner_star/child_star`(스텁, 로직·점수 무변경).
  - `prediction.py` TimelinePhase docstring 주석(필드 무변경).
- 검증: ruff·mypy clean, TimelinePhase 직렬화 불변, resolver/매핑 스모크 OK, 기존 결혼·관계 테스트
  40건 불변. 전부 `reviewed:false` — 가중치는 전문가 감수 전 미보장(원칙 5).
- **다음**: §14 3단계(MT1~5 signal 정의) → 4 subtype 보존 → 5 negative matrix → 6 static prior → 회귀.

### §14 3단계 — A(스키마) 적용 + 구조 발견 (2026-06-30)

연애·결혼 signal 정의(MT1~5) 변경안에 사용자 2차 리뷰(7개 수정) 반영 후 **A 스키마만 적용**:
- `dictionaries.py` SignalSpec 신규 게이트: `tenGodGroup`(MT1 partner_star 추상화)·`spousePalace`(MT3)·
  `branchHiddenTenGods`(MT5) + 검증(값 화이트리스트 `_PARTNER_STAR_GROUPS`). EventCandidateSpec 신규:
  `stageHint`(MarriageStage enum 검증 — 임의 stage 거부)·`partnerStarBonus`·`topicHint`.
- 전부 default None·비파괴. validate 69사전 불변, 스키마 스모크(검증/거부/직렬화) OK, 결혼·관계 +
  사전/이벤트 테스트 136건 불변. ruff·mypy clean.
- **구조 발견 2건(SSOT 반영)**: ① 방합 relation 값은 기존 `directional`(InteractionKind.BRANCH_
  DIRECTIONAL)이지 `branch_directional` 아님. ② `directional`은 이미 탐지·매칭되는 어휘라, MT3
  엔트리를 `spousePalace` 게이트 엔진 구현 전에 넣으면 **모든 방합 오발동** → MT3은 엔진과 한 단위로.
  MT1(day_master_stem_combine)·MT5(branchHiddenTenGods)는 신규 어휘라 inert(단독 안전).
- **미결**: `family_formation_signal`(MT5)은 21키 하드셋 확장(다운스트림 8곳) — 적용 범위 사용자 확정 필요.
- 전체 회귀: 2건 실패(test_chat_pipeline::too_broad, test_report_jobs_api::job_lifecycle)는 **pristine
  HEAD에서도 실패**하는 기존 결함 — 본 작업과 무관(stash 격리로 확정).

### §14 3단계 — MT1 단위 구현 완료 (생성형 Seed Producer, 2026-06-30)

MT1(일간 干合 배우자성 awareness)을 **MT별 단위(엔트리+탐지 함께)**로 구현. 사용자 확정 = 생성형이되
modifier가 아닌 **Seed Producer**로 분리(marriage_flow의 '증폭만' 원칙 유지), 생성 범위는
new_relationship + awareness로 하드 제한.

- **명리 근거**: 일간의 干合 대상은 음간이면 官(여=배우자성)·양간이면 財(남=배우자성) — MT1은
  음일간 여명·양일간 남명에서 자연 발동(영상 丁일간=음간 예시와 일치). hap_mode='combine_self'(본신지합).
- **1) relationship.json**: MT1 엔트리(relation=day_master_stem_combine, tenGodGroup=partner_star,
  stageHint=awareness, partnerStarBonus, score 0.3, reviewed:false).
- **2) graph_builder**: signal.relation==day_master_stem_combine / ten_god_group → supports 엣지
  + aux 노드(relation_day_master_stem_combine·ten_god_group_partner_star) 즉석 생성·dedup(dangling 방지).
- **3) marriage_awareness_seed.py(신설)**: `produce_mt1_awareness_seeds` 순수 함수. 조건=운천간이
  일간과 干合(combine_self·luck_origin) + 그 십성군=partner_star(성별 인지). 점수=base30 +성별확정10
  +합화용희신5, awareness cap60 / unknown cap35. 합거·쟁합·기신=불안정 분기(MT1_GISIN_RISK·
  MT1_COMPETITION_RISK, 미발동 아님). gender 미상=양 기준 검사+THEME_ONLY 하향(차단 안 함).
- **4) event_engine_v2**: `enable_mt1_awareness` 생성자 flag(기본 OFF). branch 직후 seed 합류 →
  6계층 보정·랭킹·soft_cap 동일 통과. OFF=기존 결과 byte 불변.
- **5) 테스트(test_marriage_awareness_seed.py 10건)**: 음일간여명/양일간남명 발동, 비배우자성·비干合
  미발동, gender unknown 하향, 기신 risk_flag, new_relationship+awareness 한정, pillars graceful,
  flag OFF inert(개수 불변)/ON 발동(壬년 2022·2032 confidence theme_only). LRU 캐시 오염 회피(model_copy).
- 검증: validate 69사전 OK, graph build(MT1 aux 2노드·supports 2엣지), ruff·mypy clean, 전체 1296 pass
  (2 fail=pristine HEAD 기존 결함 무관, 18 skip). 전부 reviewed:false·feature OFF — 운영 영향 0.
- **다음 단위**: MT2(일지 투출 글자 회귀, EMERGENCE_RETURN) 또는 MT3(방합 spousePalace 게이트, 엔진과 한 단위).

### §14 3단계 — MT2 단위 구현 완료 (전용 증폭 modifier, 2026-06-30)

MT2(일지 투출 글자 운 회귀)를 사용자 확정 = **A 전용 `MarriageEmergenceModifier`(증폭형)**로 구현
(RelationKind.EMERGENCE_RETURN/relation_palace 경로 미사용 — 3종 강도·게이트·충 분기가 flat bonus와
안 맞음). 5개 보정 + 3 테스트 반영.

- **명리 발견(SSOT 정정)**: 일간 기준 천간↔십성은 **1:1 전단사**라 'same_ten_god'(글자 다름+십성 동일)
  티어는 실현 불가(같은 십성 ⟺ 같은 글자) → **2티어로 축소**(same_stem / same_element=음양 짝).
- **marriage_emergence_modifier.py(신설)**: `analyze_marriage_emergence_natal`(일지 지장간 ∩ 원국
  천간4, 각 stem/element/ten_god/source_pillars/is_day_master_exposure/is_partner_star) + `MarriageEmergenceModifier`.
  증폭만(생성 금지) — new_relationship/marriage_signal/relationship_change에만. **절대 delta 상한**
  (partner same_stem+10/same_element+4, 비partner +5/+1 — 과증폭 방지, 점수 곱 안 함). 일간 투출=weak
  flag(action 금지). **spouse_palace_clashed**면 긍정 증폭 0 + MT2_EMERGENCE_CLASHED·SPOUSE_PALACE_CLASHED
  태그(marriage_signal 증폭 금지).
- **event_engine_v2**: `enable_mt2_emergence` flag(기본 OFF). marriage_flow 직후 적용, hits에서 일지 충
  판정. OFF=결과 불변(개수도 동일 — 증폭형).
- **테스트(test_marriage_emergence_modifier.py 11건)**: same_stem/same_element 차등, 비partner·일간투출
  weak, 회귀 없음 불변, 신규 생성 금지(개수 불변), same_element 승급 없음, 충 분기(marriage_signal 증폭
  금지·new_relationship 근거만), 원국 분석(己 편관 투출·癸 일간투출 검출), flag OFF inert/ON 증폭.
- 검증: validate 69 OK, ruff·mypy clean, 전체 1307 pass(+11 MT2, 2 fail=pristine HEAD 기존 결함 무관, 18 skip).
  전부 reviewed:false·feature OFF — 운영 영향 0.
- **다음 단위**: MT3(방합 spousePalace 게이트 — directional이 이미 매칭되므로 엔진 게이트와 한 단위).

### §14 3단계 — MT3 단위 구현 완료 (방합 배우자궁 게이트, 얇은 태깅, 2026-06-30)

MT3(방합 spousePalace 게이트)를 사용자 확정 = **A안 얇은 태깅 레이어**(점수 무가산)로 구현.

- **핵심 근거**: 방합(DIRECTIONAL_CONTRIB)은 이미 `_REL_KIND`에서 HAP→일지(DAY)궁 활성으로 관계
  후보를 보강 중(activation_weight 1.3). MT3가 점수를 또 더하면 중복 점수화(포화) → **점수 0,
  의미만 태깅**. spousePalace 게이트 = DAY궁 활성과 동치(방합 hit natal_refs에 day 포함).
- **marriage_directional_tag.py(신설)**: `apply_mt3_directional_tags` — 방합이 일지 포함 시 관계 후보
  (new_relationship/marriage_signal/relationship_change)에 태그. `MT3_DIRECTIONAL_DAY_BRANCH` +
  `MT3_DIRECTIONAL_PARTNER_ELEMENT`(방합 완성 오행=배우자성 오행, 여=관살·남=재성) + 일지 관여
  충형파해 분기 태그(`MT3_DIRECTIONAL_CLASHED/PUNISHMENT/HARM/BREAK`). **점수·event_key 무변경**.
  full/partial(반합)은 hit 미노출 → 2차 보류(사용자 허용).
- **relationship.json**: MT3 graph evidence 엔트리(relation=directional, spousePalace, note에
  "graph evidence only·라이브는 relation_palace 재사용·MT3 무가산" 명시). graph_builder에
  relation_directional·spouse_palace supports 엣지 + 노드.
- **event_engine_v2**: `enable_mt3_directional` flag(기본 OFF). MT2 직후 태깅. OFF=점수·개수 byte 불변.
- **테스트(test_marriage_directional_tag.py 9건)**: 일지 포함 태그·점수 불변, 일지 미포함 미발동,
  partnerElement 유/무, 충 분기, 비관계 후보 무영향, 방합 없음 불변, flag OFF inert(점수 리스트 동일)/
  ON 태그(2019 己亥→亥子丑·일지 丑).
- 검증: validate 69 OK, graph(MT3 aux 2노드), ruff·mypy clean, 전체 1316 pass(+9, 2 fail=기존 결함, 18 skip).
  전부 reviewed:false·feature OFF — 운영 영향 0.
- **다음 단위**: MT4(육합>삼합>방합 subtype 차등 — relation_palace HAP 붕괴 해소, hap_subtype 보존).

### §14 3단계 — MT4 단위(shadow까지) 구현 완료 (HAP subtype 재가중, 2026-06-30)

MT4(육합>삼합>방합 차등)를 사용자 확정 = **shadow-first 3-state + 관계 도메인 한정 재분배(상향 없음)**로 구현.
shadow까지 승인, apply 운영 반영은 비교 후 별도 승인 보류.

- **marriage_hap_subtype.py(신설)**: 순수 함수 `mt4_subtype_multiplier`(육합1.0/삼합0.85/방합0.70·
  일지0.75·partnerElement0.80, unknown·stem=1.0) + `partner_elements`(여=관살·남=재성, **미상=빈 집합**
  → partnerElement 완화 0.80 미적용). 모든 multiplier ≤1.0(포화 방지).
- **RelationActivation**: hap_subtype·element 필드 추가(HAP 붕괴 유지하되 원 종류 곁들임). `_activations`가
  hit.type→subtype·hit.element 보존.
- **relation_palace.apply**: `mt4_mode`(off/shadow/apply)·gender·day_element·shadow_sink 인자.
  관계 도메인(new_relationship/marriage_signal/relationship_change) HAP 활성에만 적용. off=불변,
  shadow=점수·reason·contributions 불변 + **diagnostics 사이드채널(mt4_shadow)에만** 기록(LLM 입력 무영향),
  apply=합산 전 보너스에 곱 + MT4 reason.
- **event_engine_v2**: `enable_mt4_subtype` 3-state(기본 off), `self.mt4_shadow` debug 채널(score()마다 초기화).
- **테스트(test_marriage_hap_subtype.py 9건)**: multiplier 테이블·상향없음·unknown 1.0·partner_elements
  성별(미상 빈집합)·off==shadow byte 동일(점수·reason·contributions)·shadow 진단 diff≤0·apply 상향 위반0·
  관계 외 도메인 불변.
- **shadow 영향(4차트×25년 42건)**: six_harmony 0(불변)·stem 0(불변)·three_harmony −12.2·directional −65.3
  누적 감쇠. 방합 중복 점수화가 가장 크게 완화됨.
- 검증: validate 69 OK, ruff·mypy clean, 전체 1325 pass(+9, 2 fail=기존 결함, 18 skip). off/shadow 운영 영향 0.
- **다음**: MT4 apply 승인(shadow 비교 후) → MT5(family_formation 21키 보류) → MT6.

### MT4 상태 종결 — shadow 검증 완료·apply 운영 보류 (2026-06-30 사용자 결정)

MT4 subtype reweighting은 **shadow 검증까지 완료**(모든 multiplier ≤1.0, 관계 도메인 한정, unknown/
stem fallback 1.0, 관계 외 도메인 불변, off==shadow byte 동일 확인). 다만 apply는 기존 HAP 점수
**재분배로 순위 변화**가 생기고 방합 누적 감쇠(−65.3, 4차트×25년)가 커서, **golden marriage/relationship
사례 비교 전까지 운영 기본값 적용 보류**(사용자 결정). flag 상태 유지: off=운영 기본 / shadow=검증용 /
apply=개발·실험 전용. **apply 켜기 전 통과 기준**: ①golden 결혼·연애 20건+ 비교 ②top3 라벨 과변동 없음
③실제 결혼 후보가 relationship_change로 과분기 안 됨 ④방합 감쇠 후에도 spousePalace+partnerElement는
근거 유지 ⑤평균 점수↓이되 적중 recall 유지(방합 성혼 케이스 + 방합 갈등종결 케이스 동시 포함).

### §14 6단계 — MT6 구현 완료 (배우자성 위치별 혼기 static prior, 2026-06-30)

MT6(배우자성 위치별 혼기)를 **event 아닌 static prior · 완전 inert 독립 분석기**로 구현(사용자 확정).

- **marriage_age_prior.py(신설)**: `analyze_marriage_age_prior(result) → MarriageAgePrior`. 배우자성
  (여=관살·남=재성)이 드러난 자리(천간 투간+지지 본기, 지장간 제외) → band(년 early/월 normal/일
  spouse_palace_direct/시 late/없음 unknown). **headline=가장 이른 자리**, 일지 배우자궁 직접성은
  `structural_flags=["spouse_palace_direct"]`로 **별도 보존**(보강①). `triggers_event=False`·
  `role="static_prior"` 고정 — 특정 연·월 발동 금지.
- **gender 미상**(보강②): 관살·재성 양 기준 병기 + `confidence="low"` + `usable_for_threshold=False`
  (threshold 보정 미사용·설명 참고만). gender 확정+배우자성 드러남이면 normal·usable.
- **완전 inert**: event_engine·MarriageResourceProfile **미수정** → 기존 출력 byte 불변. topic builder
  (M01/M02 광역 혼기) 배선은 별도 단계.
- **테스트(test_marriage_age_prior.py 8건)**: band 매핑·가장 이른 자리 headline·일지 structural flag·
  static_prior(event 아님)·gender 미상 low/미사용·확정 usable·pillars graceful·드러난 것만(positions⊆4기둥).
- 검증: validate 69 OK, ruff·mypy clean, 전체 1333 pass(+8, 2 fail=기존 결함, 18 skip). 운영 영향 0(inert).
- **MT 시리즈 현황**: MT1(awareness seed)·MT2(emergence 증폭)·MT3(방합 태깅)·MT6(혼기 prior) 구현·검증 완료
  (전부 reviewed:false·feature OFF/inert). MT4(subtype) shadow까지·apply 보류. MT5(family_formation)
  21키 보류. **다음**: MT5 21키 결정 또는 golden 사례 확보 후 MT4 apply.

### Marriage Production Readiness v1 — Step 1: MT feature 프로파일 + 비파괴 플러밍 (2026-06-30)

연애·결혼 답변 파이프라인 전수 조사 결과 **아키텍처 정정**: 주 답변 후보는 EventEngineV2의
`score_legacy_personalized`/`score_legacy`(report·chat)에서 나오고(MT가 사는 곳), topic_builder
(CompositeBuilder)는 보조 "참고 신호"(MT 없음). MT reason_codes는 to_legacy_candidate→evidence_path로
보존됨. → **플래그만 켜면 MT가 주 후보에 흐름**(precompute 경유 아님 — 조사 에이전트 전제 정정).

- **marriage_timing_profile.py(신설)**: `MARRIAGE_TIMING_PROFILES`(default=전부 OFF / production_candidate=
  MT1·2·3 ON·MT4 shadow) + `marriage_engine_flags(profile)` + `ACTIVE_MARRIAGE_PROFILE="default"`
  (가드·단계 payload 완비 전까지 default → 출력 byte 불변). MT5/MT6은 엔진 플래그 아님(별도 배선).
- **배선**: report_service.py:428·chat_service.py:280의 `EventEngineV2(_DICTS)` → `EventEngineV2(_DICTS,
  **marriage_engine_flags())`. ACTIVE=default라 무인자와 동일(비파괴). past_validation은 미배선(default 유지).
- **테스트(test_marriage_timing_profile.py 6건)**: default OFF·production_candidate 값·활성=default·미지
  fallback·반환 사본·**default 프로파일 엔진==무인자 엔진(점수·reason 동일)**.
- 검증: 신규 파일 ruff·mypy clean(서비스 **kwargs 언팩 타입 OK), 전체 1339 pass(+6, 2 fail=기존 결함, 18 skip).
  ※ report_service:218/220 E501은 세션 선행 작업의 기존 긴 문자열(내 변경 아님).
- **다음(Step2~7, 각 출력변화 → 단계별 검토)**: marriage_stage payload → output guard → context/risk 분기
  → MT6 광역혼기 연결 → MT4 shadow telemetry → 결혼확정 금지 directive + 활성 프로파일 전환.

### Marriage Production Readiness v1 — Step 2: marriage_stage LLM payload 연결 (2026-06-30)

MT 신호(evidence_path=reason_codes)에서 관계 단계를 도출해 **chat·report 양쪽 LLM 직렬화**에 연결.
- **derive_marriage_stage(reason_codes)** (marriage_timing.py 신설): MT3_DIRECTIONAL_DAY_BRANCH·
  MT2_EMERGENCE_SAME_STEM→relationship / 그 외 MT→awareness / 비-MT→"". **stage_limit=
  commitment_marker_absent**로 상한 명시(marker 미구현 → relationship 초과 불가 = 결혼 확정 단계 차단).
- **LlmEventCandidate +4 필드**(llm_input.py): marriage_stage·marriage_base_stage·marriage_stage_reason·
  marriage_stage_limit(기본 빈값).
- **chat 경로**: context_reducer._to_llm_candidate가 c.evidence_path로 도출·주입 + candidate_block
  렌더러가 stage 있을 때만 "관계 단계: …(근거…; 상한…)" 라인 추가.
- **report 경로**(총운·년운·애정운): report_event_input `_marriage_stage_note(c)` 헬퍼 + precise_candidate_
  clusters 후보 라인에 접미사(MT 있을 때만).
- **적용 범위 확인**(사용자 질문): report 테마사주(총운/년운/애정운)·AI 채팅상담 **둘 다** — Step1
  프로파일이 양쪽 엔진에 걸려 MT 생성, Step2가 양쪽 직렬화에 연결. (chat topic_builder 참고 신호는
  CompositeBuilder라 MT 없음 — 주 후보엔 있음.) 실제 노출은 Step7 프로파일 전환 후.
- **byte 불변**: default 프로파일(MT OFF)→MT 코드 없음→stage 빈값→렌더 미추가. 전체 1347 pass(+8,
  report·chat 스냅샷 포함 불변, 2 fail=기존 결함). ruff·mypy clean.
- **다음 Step3**: marriage_output_guard — commitment/formalization marker 게이트 + 결혼 확정 표현
  코드 레벨 차단.

### Marriage Production Readiness v1 — Step 3: 결혼 출력 가드(코드 레벨) (2026-06-30)

LLM 프롬프트에만 맡기지 않고 **코드가 허용 수위를 결정**해 payload에 주입. 과판단(결혼 확정·올해
결혼·거의 100%) 차단이 핵심.
- **marriage_output_guard.py(신설)**: `compute_marriage_output_guard(stage, has_commitment_marker,
  has_formalization_marker)` 순수 함수 — marker 미구현(기본 False)이라 **결혼 확정·논의 차단·
  relationship 진전까지만 허용**(commitment/formalization은 marker 채우면 자동 해제). `marriage_guard_
  directive()` LLM 지시문 렌더. `detect_marriage_overclaim(text)` 출력 과claim 탐지(테스트·텔레메트리·
  후속 재생성용). 하드 금지(반드시 결혼·거의 100%·혼인 확정 등)는 단계 무관 **항상** 차단.
- **연결**: context_reducer serialize_llm_input — 이벤트 후보 중 marriage_stage가 있을 때만 강한 단계
  (relationship>awareness)로 guard directive 1회 주입. MT 없으면 미주입(default 불변).
- **테스트(test_marriage_output_guard.py 9건)**: relationship→진전만·확정 차단 / awareness→진전X /
  비-MT 보수 / commitment·formalization marker 해제 / 하드 금지 상존 / directive 반영 / overclaim 탐지.
- 검증: ruff·mypy clean, 전체 1356 pass(+9, 2 fail=기존 결함). default 프로파일 출력 byte 불변.
- **다음 Step4**: relationship_context(미혼/기혼 등)·risk_flags(충·쟁합·기신) 답변 분기 directive.

### Marriage Production Readiness v1 — Step 4: risk_flags 분기 directive (2026-06-30)

- marriage_output_guard에 `has_stability_risk(reason_codes)`(CLASHED/RISK 코드 탐지) + 가드 필드
  `stability_risk` 추가. risk면 `can_say_marriage_confirmed/discussion`을 강제 False로 덮고, directive에
  "marriage 긍정 단정 금지·관계 변화·갈등 가능성 병기"(§12 재분기) 추가.
- context_reducer 가드 주입부가 관계 MT 후보의 marriage_stage_reason에서 risk를 집계해 전달.
- relationship_context: unknown→분기 서술은 Step3 가드 directive가 이미 강제. known-status 맞춤 서술은
  LlmInput 필드 필요해 소규모 후속으로 분리(보수 기본 = unknown 분기로 안전).
- 테스트 +2(risk 탐지·risk가 marker 허용 덮음·관계변화 병기). 전체 1358 pass(+2), default 불변.

### Marriage Production Readiness v1 — Step 5: MT6 혼기 prior 답변 연결 (2026-06-30)

- structural_context.`marriage_age_prior_lines(result)` 신설 — MT6 analyze_marriage_age_prior 호출,
  band 한글(early=이른/normal=적령/spouse_palace_direct=배우자궁 직접/late=만혼) + "특정 시기 아님·
  운이 결정" 명시. spouse_palace_direct는 별도 줄, gender 미상은 약한 참고 표기.
- 프로파일 aux로 self-gate: marriage_timing_profile.`active_marriage_aux()`(호출 시점 ACTIVE 반영 —
  런타임 전환 전파). default(mt6_age_prior=False)→빈 목록(출력 불변), production_candidate→prior 노출.
- 연결: report_service.marriage_resource_block + chat_service 결혼 컨텍스트에 append.
- 테스트 +3(default 빈/production prior·특정연월 미언급/graceful). 전체 1361 pass(+3), default 불변.

### Marriage Production Readiness v1 — Step 6: 익명 결혼 텔레메트리 (2026-06-30)

- marriage_telemetry.py(신설): `build_marriage_telemetry`(관계 MT 후보·stage·점수·reason·mt4_shadow_diff
  익명 집계 — **PII 없음**: 생년월일·식별자·gender 미포함) + `emit_marriage_telemetry`(logging
  "saju.marriage_telemetry" debug 채널, 직렬화 실패해도 답변 무영향). marriage_timing_profile.
  `active_mt_features()`(프로파일별 켜진 MT 라벨).
- 연결: context_reducer serialize_llm_input 가드 블록에서 MT 후보 있을 때만 emit(_mtp.ACTIVE_*·
  active_mt_features 동적 읽기 → Step7 전환 전파). default(MT off)→MT 후보 없음→무방출.
- 테스트 +5(관계 MT만 집계·PII 키 부재·mt4 diff 합·프로파일별 features·emit 예외 무해). 전체 1366 pass.

### Marriage Production Readiness v1 — Step 7: directive + 전환 대기 + 종합 검증 (2026-06-30)

- **answer directive**: 사용자 요구 금지(반드시 결혼·거의 100%·혼인 확정·올해 결혼한다)·허용(관계
  공식화 가능성·만나는 사람 있으면 결혼 논의·싱글이면 진지한 만남·충/쟁합이면 관계 변화 병기)은
  Step3·4 marriage_guard_directive가 **MT 활성 시** 전부 방출(코드 결정). 별도 style 추가 불요.
- **타입 정정**: marriage_engine_flags 반환 dict[str,object]→dict[str,Any](**unpack mypy 해소).
- **엔드투엔드 검증**: production_candidate 엔진→MT 태그 4건→marriage_stage='relationship'(상한
  commitment_marker_absent)→LlmEventCandidate→stage 라인+guard directive+telemetry. shadow 2건.
- 종합: 신규 MT/상용 모듈 ruff·mypy clean, validate 69 OK, 전체 1366 pass(2 fail=기존 결함). **default
  프로파일에서 report·chat 출력 byte 불변**(전 스냅샷 통과).
- **남은 단일 액션 = 활성 프로파일 전환**(ACTIVE_MARRIAGE_PROFILE 'default'→'production_candidate', 1줄):
  사용자 노출 출력 변경이라 임의 전환하지 않고 사용자 승인 대기. 전환 시 report(총운·년운·애정운)·
  chat에 MT1~3 awareness/relationship 단계·MT6 혼기 prior·결혼확정 차단 가드·MT4 shadow 텔레메트리가
  일괄 활성. rollback=1줄 복귀. MT5(family_formation 21키)·MT4 apply는 계속 보류.

## Marriage Production Readiness v1 — 완료 요약
Step1 프로파일·Step2 stage payload·Step3 출력가드·Step4 risk분기·Step5 MT6 prior·Step6 텔레메트리 전부
구현·검증(전부 default에서 byte 불변, feature OFF/inert). 상용 활성은 ACTIVE_MARRIAGE_PROFILE 전환 1줄로
on, 즉시 rollback 가능. 검증은 오픈 후 텔레메트리·사용자 피드백으로(golden 사례 축적).

### Marriage Production Readiness v1 — 상용 활성 전환 완료 (2026-06-30 사용자 승인)

`ACTIVE_MARRIAGE_PROFILE` 'default'→'production_candidate' 전환(1줄). MT1·2·3·6 + 출력 가드 + 텔레메트리
상용 활성. MT4 apply·MT5는 계속 보류.
- **토큰 영향 해소**: 전환으로 MT 단계 라인·가드 directive가 입력에 더해져 chat 단건이 12,000 초과
  (12,096). ① MT 답변 콘텐츠(단계 라인·가드 directive)를 **관계 도메인 질문에만** 렌더하도록 게이트
  (`_rel_focus` — 일반 월간운엔 결혼 가드 불필요·의미 정합·토큰 절약), 가드 directive·단계 라인 간결화.
  ② **대화형 입력 상한 12,000/14,000→20,000 상향**(2026-06-30 사용자 승인, llm_guard.CALL_LIMITS +
  docs/09 8장 표). 텔레메트리는 토큰 무관(logging)이라 도메인 무관 유지.
- 전환·상한 변경으로 한도 단언 테스트 6건 갱신(test_llm_guard·context_reducer·topic_builder·
  topic_modules·sinsal_payload — 12,000/14,000→20,000), 프로파일/혼기 테스트 2건 갱신(active=production·
  monkeypatch off).
- 엔드투엔드: 관계 질문 → MT 태그→marriage_stage='relationship'(상한 commitment_marker_absent)→
  단계 라인+가드 directive 노출, 일반 질문은 미노출. 전체 1366 pass(2 fail=pristine HEAD 기존 결함 무관).
- **rollback**: ACTIVE_MARRIAGE_PROFILE='default' 1줄. **검증**: 오픈 후 marriage_telemetry 집계로.

### claim recheck(B) — 멀티턴 직전 풀이 재검토 (2026-06-30)

라이브 채팅에서 "...아니야?" 류 후속 반문이 FEEDBACK_CORRECTION으로 분류돼 canned 폴백("재검산하려면
대화 이력 연동 필요·준비 중·출생정보 다시")으로 빠지던 문제(query_parser.py:214 `아니야\s*\?` 규칙 →
planner claim_recheck policy_route → chat_service.py:1680 단락).
- **B(제대로 처리)**: chat_service `_recheck_continuation(intent, prior_intent)` — FEEDBACK_CORRECTION +
  subject 확정 + 직전이 분석 질문(_RECHECK_ANALYSIS_QTYPES)이면 직전 도메인·이벤트·시점을 상속해 분석
  query_type으로 전환 → policy 단락 회피, 정상 분석 경로. `_RECHECK_DIRECTIVE`를 trailing에 주입해
  "출생정보 재요청 금지·prior_claims와 엔진 근거로 재검토·트리거≠실행·단계(awareness→진전) 구분" 지시.
- 맥락 없음(새 스레드)·직전 비분석이면 전환 안 함(진짜 정정·새 질문 보호). prior_claims 인프라 재사용.
- 검증: 단위 5건(상속·미전환 조건) + 엔드투엔드(1턴 연애시기 dry_run → 2턴 "...아니야?"가 policy 아닌
  **dry_run**으로 전환). 전체 1371 pass(+5, 2 fail=기존 결함). ruff·mypy clean.

### claim recheck 연쇄 결함 수정 — '그래' 수락이 canned로 빠지던 문제 (2026-06-30)

라이브 검증 중 발견: '...아니야?'(B 재검토) 다음 '그래'(수락)가 다시 canned claim_recheck로 빠짐.
원인 연쇄 — ① B는 답변을 분석으로 처리하나 스레드 저장 last_intent는 FEEDBACK_CORRECTION ②
다음 약한 발화('그래')가 conversation.py에서 직전 query_type(FEEDBACK_CORRECTION)을 상속 → 다시
FEEDBACK_CORRECTION → B는 prior가 분석 아님으로 보고 전환 안 함 → canned.
- **Fix 1(conversation.py)**: 약한 후속의 query_type 상속에서 **정책류(_POLICY_QTYPES: FEEDBACK_
  CORRECTION·TERMINOLOGY·EMOTIONAL·OUT_OF_SCOPE) 제외**(주제가 아니라 정책이므로 상속 부적합).
- **Fix 2(chat_service)**: B 재검토 전환 시 `state.last_intent`도 전환된 분석 intent로 갱신 →
  다음 턴이 분석 주제를 상속(연쇄 차단).
- 검증: 엔드투엔드 연쇄(연애시기→아니야?→이직 아니야?→그래) 4턴 모두 분석(dry_run, canned 탈출).
  회귀 테스트 추가(test_recheck_followup_and_affirm_escape_canned). 전체 1391 pass(DB 로드 시,
  1 fail=기존 too_broad 결함), ruff·mypy clean.

### 시점 오류 수정 — 미래 '언제 들어올까'가 과거 달을 답하던 문제 (2026-06-30)

라이브 검증: "이직 제안은 언제쯤 들어올까?"(미래·오늘 2026-06-30)에 2026-02·04(이미 지난 달)를 메인으로
답하던 시점 오류. 원인 — chat_service의 미래 클램프 로직이 **모든 open_when을 과거 회고로 간주**
(주석 "open_when='언제였는지' 과거 개방 탐색"). '언제 들어올까?'도 open_when으로 파싱돼 과거 10년
창으로 앵커링 → 지난 달이 메인에 오름.
- **수정**: `_FUTURE_WHEN_RE`(언제쯤·들어올까·올까·될까·만날까·풀릴까 등) 추가 → open_when이어도
  미래지향이면 is_retro에서 제외. 미래 클램프(current_month ~ +2년)가 적용돼 지난 달이 배경으로 분리.
- 검증: "이직 제안 언제 들어올까?" 후보가 2026-02/03/04 → **전부 사라지고** 2026-06~ 미래로 이동
  (2026-05 한 달 경계 잔존은 절기/overview 엣지·경미). 과거 회고("작년 무슨 일"·"언제였을까"·단답
  "년단위였어")는 retro 유지(보존). 단위 테스트 test_future_when_clamp(미래 매치/과거 비매치).
- 전체 1393 pass(+2, 1 fail=기존 too_broad), ruff·mypy clean. 백엔드 재기동(21:28).

### 시점 오류 추가 조임 — 토픽 참고 신호 현재 달 floor (2026-06-30)

미래 클램프 후에도 [M07 토픽 신호(참고)] 블록이 올해 전체 월(2026-05 등 지난 달)을 노출하던 잔존
(CompositeBuilder가 연 단위 period로 올해 findings 생성). `_topic_module_context`에 future_floor
('YYYY-MM') 추가 — 미래지향(비회고) 질문이면 현재 달 이전 월 findings 제외. 검증: '이직 제안 언제
들어올까?' 토픽 신호가 2026-05 제거→2026-06부터, 과거회고('작년 무슨 일?')는 2025 보존(floor 미적용).
전체 1393 pass.

### 시점 오류 근본 수정 — open_when 후속 방향 상속 (2026-06-30)

'이직 제안 언제?'(미래) 다음 '월단위로 알려줘'가 다시 2~4월(과거)을 답하던 문제. 원인: '월단위로'는
미래 동사가 없어 _FUTURE_WHEN_RE 미스 → 상속된 open_when이 일괄 과거 분류 → 과거 창. 근본 수정:
ConversationState.last_retro(직전 턴 시간 방향) 추가, is_retro 판정을 과거신호>미래신호>open_when은
직전 방향 상속(기본 미래) 순으로 재구성. '월단위로'가 미래질문 뒤면 미래·과거질문 뒤면 과거 승계.
검증: 미래→월단위 후보 2026-06~(과거 제거), 과거→월단위 과거 유지. test_open_when_followup_inherits_
direction(last_retro 미래False/과거True). 전체 1393 pass.

### 실상담 사례 역공학 — 명식 정합성 fixture + 답변 방식(P0~P2) 보강 (2026-07-03)

데굴님 제공 실상담 케이스(1980-11-22 09:40 서울 남, 메타인지보고서 PDF+전화 요약)를 3가치
(엔진 정합성 검증·상담 UX 역공학·테마운세 답변 방식 보강)로 반영(사용자 승인 플랜 1~8).
사례 분석: `doc/v2_2/cases/1980_1122_job_report_case.md`. 명식(庚申 丁亥 己亥 己巳)·신약·
정재격(반성반패)·용신土/희신火/구신水가 상담사 판정과 일치, 金(한신vs BAD)·木(기신vs혼재)은
expert_review_required로 fixture `review_flags`에만 등록(단일 사례로 role 변경 금지 — 木은
정적 결핍 vs 운 작동 분리 원리의 감수 사례). **목차 개편 없음** — 기존 J 목차가 커버, 부족한
건 생활 언어 번역층으로 확정.

- **fixture 회귀**: `tests/fixtures/cases/1980_1122_job_report_case.json` +
  `test_case_1980_1122_job_report.py`(6건 — 사주·진태양시 시주 유지·신강약·격국·용신 부분단언·
  현침·감수 플래그). 金/木은 테스트 실패 기준으로 단언하지 않음(데굴님 확정).
- **P0 서술 디렉티브 7종**(`structural_context.py`, 채팅·리포트 공용, 계산 불변 원칙 1·12):
  결론 선제시 / 활동 키워드 번역 / 탈규범 안심 / 극복 아니라 관리 / 운 품질→의사결정 태도 /
  시기 단정 금지 / 성향 반박 수용(풀이 인용+부정 감지 — 상담사가 회피하던 지점의 명시 규칙화).
- **P1 활동 키워드 사전**: `dictionaries/interpretations/activity_keyword_map.json`(오행 5종+
  현침살, reviewed:false). 직업 추천이 아니라 활동축·환경·방식 번역 전용. **P2 개운 행동 사전**:
  `remedy_action_map.json`(not_magic/behavior_first/avoid_certainty 원칙+5오행 행동,
  reviewed:false — 기존 remedy.json D-3 상황 6분기와 별개 축). 둘 다 SCHEMA_BY_PATH 등록
  (pydantic 검증, remedy는 5오행·3원칙 고정 validator).
- **배선**: 리포트 — J-07에 활동 키워드+개운 행동 블록(용신·희신=살릴 기운/기신·구신=기준,
  원국 신살 매칭, 결정론 선별)+번역 지시, 행동 전략 섹션군(F-19/Y-10/W-08/J-07/R-07/RP-09/
  RL-07/C-07)에 관리·태도 디렉티브, R-07·RP-09에 탈규범, J-06에 시기 단정 금지(가이드 문구+
  디렉티브 — 우선 J-06만, 감수 후 타 테마 주목달 확장 검토). 채팅 — 비교/의사결정→결론 선제시,
  REMEDY→관리 프레임, 대운·장기→태도 번역, 성향 반박(인용+부정)→수용·재해석, 강한 당위
  ('꼭 해야')→탈규범(일반 의사결정 질문 오탐 방지 키워드 게이트).
- 검증: 신규 테스트 19건(fixture 6+사전/배선 8+트리거 5... 실측 6+6+2 파일) 포함 전체
  1439 passed·1 skipped, ruff·mypy clean, validate_dictionaries 74개 통과.
- 남은 감수 대기: 金/木 role, 두 사전 전 항목 reviewed:false(감수 통과 후 W-08 등 확장),
  산업 조합(실버×온라인) 세분화는 occupation_taxonomy 연계 여부 별도 논의.

### CAL-P0 — 캘리브레이션 질문 품질 개선: 교운기 우선 배치 + trait_probe 수집 (2026-07-03)

실상담 사례 분석(doc/v2_2/cases/1980_1122_job_report_case.md)에서 도출한 캘리브레이션 개선
6안 중 데굴님이 P0로 확정한 2건 구현. **불변식: 점수·용신 role·favorability·세운/월운 산출
불변** — probe는 질문 후보 순서·질문 문구·축적 레코드에만 관여(원칙 준수 테스트로 고정).

- **P0-a transition_probe(교운기 우선 배치)**: `period_selector`에 교체 연도 거리 가중
  {0:1.0, ±1:0.368, ±2:0.135, ±3:0.05}을 후보 ranking에만 boost 가산(`transition_weight`
  필드). `question_generator`가 교운 근접 최상위 해로 회상형 질문(q_transition) 생성 —
  교체기 체감 신호(주변 사람 교체·정리·거주/리듬 변화·싱숭생숭)를 회상 단서로, 사건 단정
  금지 문구 고정. cap 기본 1(쏠림 방지, `max_transition_probes`). manse_service가
  `luck_cycles.daewoon_table`의 approx_start_date.year를 주입.
- **P0-b trait_probe(성향 동의/반박 수집)**: 새 질문 유형 — 채점 절대 비반영(scorer가
  `_PROBE_TYPES` 명시 제외 + expected/target 공란 이중 차단). 후보는 manse_service의
  결정론 predicate(`_trait_probe_candidates`): 현침→communication_style, 관성 표면
  부재(visible_absent ⊇ {정관,편관})→decision_style. cap 1. 응답(agreed/mixed/denied/
  unclear, 자유 진술)은 `CalibrationResult.trait_probe_feedback`(scoring_effect=none,
  review_status=accumulate_only)로 축적, denied/mixed면 `trait_llm_hints`에 '단정 회피·
  발현 조건 재해석' 표현 조정 힌트만 생성(役 confidence 조정·override는 이번 스코프에서
  의도적으로 제외 — 데굴님 확정).
- 스키마: CalibrationQuestion(trait_target·engine_basis, 유형 주석), FeedbackAnswer
  (trait_response·trait_statement), TraitProbeCandidate/TraitProbeFeedback,
  TRAIT_PROBE_TARGETS 6축·옵션 4지 상수.
- 검증: 신규 test_calibration_probes.py 9건(교운기 4 — 창 앵커·±3년 밖 boost 0·cap 1·
  q1~q5 유지+expected_by_model 불변 / trait 5 — 생성·agreed/denied 축적·unclear 처리·
  용신 결정 불변·힌트 전용). 기존 test_calibration 질문 수 단언을 새 규격(기본 5+probe)
  으로 갱신. 전체 1448 passed·1 skipped, ruff·mypy clean.
- 보류(데굴님 확정): 갈리는 오행 조준 샘플링(②)·정적 결핍 vs 작동 이원 질문(③)·대화 중
  실측 승격(⑤)·role confidence 미세 조정(⑥). FE는 신규 question_type 2종 렌더링 미배선.

### FE-P0 — 캘리브레이션 probe 2종 프론트 렌더링 배선 (2026-07-03)

CAL-P0 신규 question_type(transition_probe/trait_probe)의 FE 대응(데굴님 확정 지시).
CalibrationPanel(만세력 결과·온보딩 StepYongsin 공용)에 명시 분기 추가 — 기존 q1~q5
렌더링 불변, 기존 응답 구조 불변.

- **trait_probe**: 선택형 고정(대체로 그렇다/상황에 따라 다르다/그렇지 않다/잘 모르겠다,
  `TRAIT_OPTIONS` — 백엔드 TRAIT_RESPONSES 미러) + 보조문 "답변 스타일을 더 잘 맞추기 위한
  확인 질문이에요. 용신이나 운세 점수는 바뀌지 않아요."(용신 수정 UI로 오인 차단) + 자유
  한 줄 입력(선택, 80자). 응답은 payload `trait_response`/`trait_statement`로 전달.
- **transition_probe**: 회상형 — 질문 본문 + 보조문 "이 시기는 대운(10년 흐름)이 바뀌는
  전환 전후예요. 실제 사건이 아니더라도 생활 리듬이나 주변 환경 변화가 체감됐는지
  확인해요."(사건 단정 문구 금지) + 변화 영역 칩(복수, 기존 selected_events 재사용).
  전체 체감·영역별 체감 그리드는 미노출(채점 비반영 문항에 과입력 방지).
- 타입: lib/types CalibrationQuestion(trait_target·engine_basis), lib/api FeedbackAnswer
  (trait_response·trait_statement), lib/calibration AnswerMap 확장. isAnswered가 probe
  유형별 응답 판정(trait=선택지, transition=칩).
- QA 7항 실측(FE payload 형태 그대로 백엔드 E2E 시뮬): q1~q5 유지 / probe 각 ≤1 /
  payload 역직렬화 OK / trait denied·agreed 간 용신·희신·기신·selected_model 동일 /
  denied만 표현 힌트 1건·agreed 힌트 0건 / transition 문구 단정어(반드시·무조건 등) 없음.
- 검증: tsc clean, next production build 통과, vitest 23 passed.

### QA-P0 — probe pre-live 수동 QA(synthetic 20건) + 기본 질문 굶김 결함 수정 (2026-07-03)

CAL-P0/FE-P0 probe의 오픈 전 검수(데굴님 지시). 재실행 가능한 QA 하네스
`scripts/qa_calibration_probes.py` — 명식 풀(~160개 조합)을 스캔해 버킷별 20건 선별:
A 교운기 명확(±1년) 5 / B 교운기 원거리(≥4년) 3 / C 현침→communication_style 4 /
D 관성 표면 부재→decision_style 4 / E probe 미노출(성별 미상=대운 없음+trait 없음) 2 /
F trait 반박 시나리오 2. 각 건에서 노출 조건·cap·기본 질문 불변·FE 동형 payload→백엔드→
LLM 힌트·판정 불변식(trait denied/mixed/agreed/미응답 4종 대조)·80자 진술 경계·단정어를 검사.

- **QA 중 실결함 1건 발견·수정(F2)**: q_transition이 연도를 **먼저** 선점해, 교운 해가
  기본 질문의 유일 후보인 차트에서 q1~q5를 굶길 수 있는 구조. 수정 — 기본 q1~q5 생성
  **후** 남은 연도에서 probe 선택(표시 순서는 insert로 맨 앞 유지). 회귀:
  test_transition_probe_does_not_starve_base_questions(1975-03-08 04:30 男 — 갈림 해
  2020 하나뿐인 실측 케이스).
- **QA 판정 기준 교정**: 'q1~q5 5개 존재'가 아니라 'probe 미주입(cap 0) 기준선과 (id,
  year) 동일'이 정확한 불변식 — q3(갈림 해)은 갈림 해가 없으면 CAL-P0 이전부터 원래
  미생성(F2 최초 실패는 probe 원인이 아니라 기준 과엄격이었음을 기준선 대조로 확인).
- **결과: 20/20 통과** — payload 정상 20/20, cap 위반 0, 기본 질문 구성 변형 0,
  trait 반박으로 인한 role·model_scores 변경 0, denied/mixed만 힌트 생성(agreed·미응답
  0건), transition 문구 단정어(반드시/무조건/됩니다 등) 0, 80자 진술 저장 일치.
- FE 계약 고정: tests/luck-calibration.test.ts에 TRAIT_OPTIONS↔백엔드 TRAIT_RESPONSES/
  TRAIT_PROBE_OPTIONS 값·라벨·순서 미러 테스트 추가(어긋나면 unclear 강등되는 계약).
- 검증: 전체 1449 passed·1 skipped, ruff·mypy clean / FE vitest 25 passed·tsc clean.
- UI 시각 확인(모바일 과밀)은 컴포넌트 구조 검토(기존 칩/버튼 flex-wrap 패턴 재사용,
  probe 카드가 기본 문항보다 가벼움)까지 — 실기기 확인은 데굴님 오픈 전 체크 항목으로 남김.
- **CAL-P1 입력용 관찰**: trait 반박의 3결(성향 자체 부정 / 특정 상황 한정 / 시기 변화)
  구분은 synthetic으로 만들 수 없는 실사용 데이터 — trait_statement 자유 진술이 그 원천.
  CAL-P1(정적 결핍 vs 운 작동 이원 질문) 설계 시 trait_probe_feedback에 반박 결 태깅
  스킴(trait_denial_kind: absolute/situational/temporal)을 함께 정의할 것.

### CAL-P1 설계안 — 정적 결핍 vs 운 작동 이원 질문 + 반박 결 태깅 (2026-07-03, 문서만)

데굴님 착수 지시(구현 금지 — 문서 설계부터). 신규 SSOT:
`doc/v2_2/CALIBRATION_STATIC_TRANSIT_PROBES.md`. 핵심: 같은 오행/십성이라도 "원국에
없어서 부족한 것"(정적 결핍)과 "운에서 들어와 압박·사건으로 작동하는 것"(운 작동)을
분리해 묻는다 — 木 사례처럼 '없어서 허전 + 들어오면 부담'이 동시 성립 가능(모순 아님).

- **질문 축 2종**: `static_deficiency_probe`(비시간형, 결핍 체감 — agreed/mixed/denied/
  unclear) + `transit_activation_probe`(해당 오행 강세 해 앵커 — strong/partial/none/
  unknown). 트리거는 결정론 predicate(부재 오행·십성 그룹 표면 부재), 길흉 어휘 배제.
- **쌍 생성 원칙**: 반드시 pair(단독 금지 — B 앵커 해 없으면 쌍 전체 미생성), 단일
  좋다/나쁘다 질문으로 합치기 금지, 쌍 cap 1(CAL-P0 포함 추가 문항 ≤3), 축 선정은
  용신 논쟁 축(감수 플래그 축) 최우선, 표시는 A→B(응답 오염 방지), 기본 q1~q5 연도
  보호(QA-P0 불변식 승계). CAL-P0의 관성부재 decision_style trait_probe는 A축으로
  승격·대체 예정(중복 방지).
- **질문 쌍 예시 규격 초안**: 오행 5축 + 십성 그룹 5축 표(전 항목 감수 대상,
  reviewed:false — 구현 시 JSON 사전으로, 원칙 5·12).
- **trait_denial_kind 태깅**: absolute/situational/temporal/mixed/unclear 5종, 룰
  기반만(키워드 표지 + situational·temporal 동시=mixed, 빈 진술=null≠unclear).
  situational/temporal은 오류가 아니라 '발현 조건 정보'로 LLM 힌트에 승계, absolute
  반복 축적은 expert_review 우선순위 상향(자동 조정은 CAL-P2 전 금지).
- **해석 매트릭스(2×2)**: A×B 응답 조합 → LLM 표현 힌트 방향(agreed+strong='양면 서사,
  모순으로 쓰지 말 것' 등) — 판정 비개입, 감수 자료 겸용.
- 불변식(§5): role/confidence/event score/favorability 불변, 응답으로 용신·기신 확정
  금지. 테스트 기준 9항 초안(§7), 구현 단계 P1-a(스키마·태깅 함수)/P1-b(사전+생성기+
  scorer 축적)/P1-c(FE+QA-P1) 제안. 미결 3건(§8 — B 연도의 대운 중첩 우선 여부, 노출
  위치, decision_style 승격 시점)은 구현 승인 시 확정 요청.
- 교차 참조: docs/14 §7 후속 포인터 신설, 사례 문서 §7 갱신. 코드 변경 없음.

### CAL-P1 확정 + P1-a 구현 — 이원 probe 스키마·반박 결 태깅 (2026-07-03)

설계안 승인 + 미결 3건 확정(데굴님) → 설계 문서(`CALIBRATION_STATIC_TRANSIT_PROBES.md`)
확정 상태로 갱신: ① B 앵커 = 세운 활성 해 기본 + 대운 중첩 boost + q_transition
동일/±1년 penalty(유일 후보면 교운 중첩 회피 힌트 문구), ② 노출 = 현행 CalibrationPanel
합류(추가 문항 cap ≤3, 표시 transition→A→B→q1~q5→trait fallback, 생성은 기본 질문
먼저), ③ P1 pair 생성 axis의 CAL-P0 trait_probe suppress(fallback 유지, 현침 축은
다르면 유지, cap 초과 시 pair 우선). 테스트 기준 10~13 추가(suppress·앵커 회피·중첩
예외 문구·총량 cap).

**P1-a 구현(승인 스코프 — 스키마+태깅만, 질문 생성은 P1-b)**:
- 스키마: question_type 2종 주석 등록(static_deficiency_probe/transit_activation_probe),
  응답 enum(STATIC_DEFICIENCY_RESPONSES=trait 4지 재사용 / TRANSIT_ACTIVATION_RESPONSES
  strong·partial·none·unknown + 옵션 라벨), TRAIT_DENIAL_KINDS 5종,
  CalibrationQuestion pair 필드(pair_id·axis_type·axis_id), FeedbackAnswer
  transit_response/statement, DeficiencyPairFeedback(§6-1, scoring_effect=none·
  accumulate_only 기본), CalibrationResult.deficiency_pair_feedback. 전부 기본값
  None/[] — 하위호환.
- 태깅 순수 함수: `manse_calibration/trait_tagging.classify_trait_denial_kind` —
  룰 기반만(situational·temporal 동시=mixed 우선, 강부정=absolute, 빈 진술=None≠unclear).
  feedback_scorer가 trait 축적 레코드에 denial_kind 부착(채점 비반영 — 진술 유무와
  무관하게 용신 확정·model_scores 동일함을 테스트로 고정).
- 검증: 신규 test_trait_denial_tagging.py 9건(결별 룰·mixed 우선·빈 진술 None·E2E
  denial_kind 흐름·판정 불변·pair 스키마 기본값·transit 필드 하위호환). 전체
  1458 passed·1 skipped, ruff·mypy clean.
- 다음: P1-b(axis predicate·pair 생성·B 앵커 랭킹·suppress·cap 통합) — 착수 지시 대기.

### CAL-P1-b — 이원 질문 쌍 생성·B 앵커 랭킹·suppress·cap 통합 (2026-07-03)

데굴님 착수 지시대로 질문 생성·응답 왕복·축적까지(LLM 힌트는 P1-c 보류). 전체
1467 passed·1 skipped, ruff·mypy clean, QA 하네스 20/20 유지.

- **질문 쌍 사전**: `dictionaries/interpretations/deficiency_pair_questions.json`
  (오행 5축 + 십성그룹 5축, reviewed:false — 축 전수 validator 포함 SCHEMA_BY_PATH 등록).
- **axis predicate**(manse_service, 기존 엔진 값 재사용·새 임계값 없음): element 축 =
  raw_visible==0(표면 부재 — '木 지장간 有·표면 無'를 잡는 사례 핵심), ten_god_group 축 =
  그룹 십성 모두 visible_absent. 그룹 축 오행이 동시 표면 부재면 병합(그룹 문구 채택,
  engine_basis 양쪽 기재). 우선순위: 논쟁 축(모델 간 용희↔기구 갈림 — 감수 플래그 축의
  런타임 proxy) > 병합 축 > 결핍 강도. intent 축은 온보딩에 intent 없어 미적용.
- **B 앵커 랭킹**(question_generator): 세운 축 활성(천간/지지 각 +1) + 대운 중첩 boost(+1,
  manse_service가 오행별 대운 활성 연도 주입) + 깨끗한 해 보너스(+0.5) − 교운 동일 해(−3)/
  ±1년(−1) − 기본 질문 중복(−1.5). 후보 0이면 쌍 전체 미생성(A 단독 금지). 유일 후보가
  교운과 겹치면 생성하되 '대운 전환감 중첩' 안내 문구 부착(단정 금지).
- **생성/표시 분리**: 생성 q1~q5 → transition → pair → trait fallback → cap, 표시
  transition → A → B → q1~q5 → trait. cap: 추가 probe 총합 ≤3(우선순위 transition >
  pair(2문항 통째) > trait). pair 생성 axis의 trait_probe suppress(axis_key 매칭 —
  관성 decision_style은 officer pair 시 미노출, 현침은 axis 무관 유지).
- **응답 축적**(scorer): `_PROBE_TYPES`에 P1 2유형 추가(채점 명시 제외).
  `deficiency_pair_feedback`(pair_id·axis·static/transit 응답·denial_kind 태깅·
  transit_year, scoring_effect=none·accumulate_only) — 미응답 쌍은 기록 안 함.
- **사례 실측**: 1980-11-22 명식에서 officer 축(木·관성 병합) pair 생성, **B 앵커
  2023년(癸卯)** — 실제 사용자의 2023-10 퇴사 해와 일치. transition 2025 + pair 2 =
  cap 3 도달 → trait drop(의도된 우선순위).
- 테스트: 신규 test_deficiency_pair_probes.py 8건(무앵커 미생성·A단독 0·쌍 cap 1·총량
  cap 3·suppress·현침 유지·교운 회피/유일 후보 예외 문구·기준선 동일·응답 4조합 판정
  불변+축적). 기존 trait E2E는 cap 우선순위 변화(의도)에 맞춰 generator+score_calibration
  직접 경로로 재작성, 기본 질문 필터에 q_pair 반영. QA 하네스에 pair(0 또는 2)·총량 cap
  검사 추가.
- FE: P1 pair 렌더링은 P1-c(현재 FE는 default 폼으로 표시 — 응답 필드 미전송 시 축적
  레코드 미생성이라 무해).

### CAL-P1-c — A×B 매트릭스 LLM 표현 힌트 + 주입 + FE pair 렌더링 (2026-07-03, CAL-P1 core 완료)

데굴님 지시대로 표현 힌트·주입·FE만(엔진 판정·점수·role·confidence 불변 — 회귀로 고정).
BE 전체 1475 passed·1 skipped, ruff·mypy clean, QA 하네스 20/20 / FE vitest 27 passed·
tsc clean·production build 통과.

- **A×B 매트릭스**(feedback_scorer): agreed+strong=dual(양면 서사, 모순 금지) /
  agreed+partial·mixed/partial 계열=conditional(조건부 발현) / agreed+none=felt_lack
  (사건 예측 근거 금지, 생활감 중심) / denied+strong=external_period_pressure(성향 축소,
  시기·환경 중심) / denied+none=deemphasize(비중 축소·단정 회피, '원국상 부족=반드시 문제'
  금지) / 유보(unclear·unknown·미응답)=hedge. 전 instruction에 불변 조항('판정 변경 금지·
  처방 금지') 내장. `CalibrationResult.pair_expression_hints`(PairExpressionHint —
  axis·element·응답·transit_year·narrative_mode·instruction).
- **payload 확정**: FeedbackAnswer.static_response 전용 필드 신설(P1-b의 trait_response
  재사용은 폴백으로 하위호환). question에 axis_element 추가(힌트 직렬화용).
- **LLM 주입**: personalization.calibration_hint_lines(순수 함수 — subject_yongsin.
  calibration blob의 pair instruction+trait 힌트를 '[캘리브레이션 표현 조정 — 근거·확인 해]'
  라인으로, cap 3) + fetch_calibration_expression_hints(무DB·실패=빈 목록, 규칙11).
  chat trailing(확정 용신 안내 옆) + report prefix(전 섹션 공통, 확정 용신 note 옆) 주입.
- **FE**: static_deficiency_probe='평소 체감' 칩+4지(trait 4지 재사용)+참고용 보조문,
  transit_activation_probe='해당 시기 체감' 칩+4지(강하게/일부/거의 없음/모름)+'점수를
  바꾸지 않아요' 보조문 — default fallback 제거. payload에 static/transit_response(null
  기본). enum 계약 vitest 미러 테스트 추가.
- 테스트: 신규 test_pair_expression_hints.py 8건(전용 필드 왕복·pair_id 묶임·dual/
  deemphasize/conditional/hedge 매트릭스·전 조합 판정 불변·blob 직렬화(cap·방어)·미응답
  무힌트). 설계 문서 상태 'CAL-P1 core 완료'로 갱신.
- 남은 감수 대기: deficiency_pair_questions.json 전 항목 reviewed:false(전문가 감수),
  denial_kind 키워드 룰은 실사용 진술 축적 후 보정. FE 모바일 실기기 확인은 release
  checklist 유지.

### CAL-P1 core close + release checklist 정리 (2026-07-03, 데굴님 최종 판정)

**CAL-P1 Static Deficiency vs Transit Activation Probes: core 완료.**

완료 범위:
- 정적 결핍 vs 운 작동 pair 질문 설계·생성 / B 앵커 랭킹 / trait_probe suppress·cap 통합
- 응답 축적(deficiency_pair_feedback) / trait_denial_kind 태깅
- A×B 응답 매트릭스 기반 LLM 표현 힌트(chat trailing·report prefix 주입)
- FE 전용 렌더링('평소 체감/해당 시기 체감') 및 payload 연결
- scoring/role/favorability/event 산출 불변 회귀 고정

남은 항목(release/review 트랙 — `doc/v2_2/RELEASE_CHECKLIST_CALIBRATION.md` 신설):
- R-1 deficiency_pair_questions(+activity/remedy map) 문구 전문가 감수 — 감수 시트
  export_review_sheet.py §5~7 확장(신규 3사전 포함, 기준 5항 시트에 명시. 현황 0/162).
- R-2 denial_kind 룰 실사용 로그 기반 보정(지금 정교화 금지 — 과적합 위험. 관찰 지표
  6종 명시).
- R-3 모바일 실기기 화면 확인 5항.

다음 순서 고정: release checklist 3건 → 오픈/베타 → 실사용 로그 2차 검수 → CAL-P2 범위
결정(②갈리는 오행 조준 / ⑤대화 실측 승격 / ⑥role confidence — 판단 데이터 5종 checklist에
기재). 기능 확장 착수 금지 — probe 체계의 실사용 작동 관찰이 먼저.

### CAL-QA — 무신호 응답 상태 추가(pre-release data hygiene) (2026-07-03)

데굴님 지적('직장인에게 학업 질문 — 시도 자체가 없었음을 표현 불가 / 취업은 발생+경험
2단인데 결과만 받음') → 진행 A+B·보류 C·비권장 D 확정. 기능 확장이 아니라 **데이터 계약
수정** — 오픈 후 쌓일 응답에서 무응답·기억 안 남·실제 없음을 분리하기 위한 오픈 전 패치.
docs/14 §8 신설.

- **A. 영역별 체감 +`no_domain_activity`**("특별한 일 없었음") — unknown(기억 안 남)과
  구분되는 비활성 신호. 채점 제외+분모 제외, raw 응답 blob에 값 그대로 축적.
- **B. 용신 검증 이벤트 결과 +`not_occurred`**("그런 일 없었다") — 발생 반증 신호.
  용신 채점 미사용(결정②), accumulate_only, personal_match 승격은 CAL-P2 판단.
  '기신 아님'으로 즉시 해석 금지(용신 검증≠이벤트 개인 적합도 검증 — 계층 분리 명문화).
- **구현 중 잡은 간접 개입 2건**: ①`_score_domains` 변동성 보너스가 극성 제외와 무관하게
  실행 — 무신호 가드 추가(unknown의 기존 동작은 스코프 밖 유지). ②이벤트 브랜치 선택 —
  무신호만 고른 응답이 이벤트 브랜치를 열어 연도 전체 평점 폴백을 건너뛰며 점수가 달라지던
  문제 → 무신호(+레거시 na, 의미 동일 '해당없음'이라 무신호로 매핑 — 데굴님 허용 옵션)를
  브랜치 판정 전에 필터. **브랜치 불변식**(무신호만 응답=무응답과 채점 동일)을 docs/14
  §8에 명문화.
- FE: DOMAIN_OPTIONS +1(특별한 일 없었음). 이벤트는 `YONGSIN_EVENT_OPTIONS` 분리 신설
  (+그런 일 없었다) — 현실 캘리브레이션(발생 체크 후 결과)은 기존 EVENT_OPTIONS 유지
  (모순 옵션 방지). normalizeEventRating이 무신호 값 보존(na→unknown 표시 정규화 유지).
- 검증: 신규 test_no_signal_ratings.py 6건(delta 0·분모 제외·unknown과 구분 저장·용신
  비반영·raw 보존·legacy na 하위호환). 전체 1481 passed·1 skipped, ruff·mypy clean,
  QA 하네스 20/20, FE vitest 30·tsc·build 통과. 실서버(:4000 프록시) 무신호 payload
  왕복 200 확인, 백엔드 재기동 완료(터널 체인 정상).

### 기간 없는 '달/날짜' 입도 질문 라우팅 교정 (2026-07-03)

실사례(데굴님 제보): '연애를 시작하는 달은 언제야?' → 10년 연 단위 나열로 오답. 원인 3축:
① 기간 미지정이면 vague_future(10년 연 digest)가 무조건 선점 — 월 경로(wants_monthly)는
`not vague_future` 게이트에 막힘. ② 연애 문맥 _MEETING_TIMING_DIRECTIVE의 '연·반기·계절
단위 제시' 지시가 명시적 달 요청과 정면 충돌. ③ _augment_time_by_similarity(시점 유사도
보강)가 '좋은 달 추천해줘'를 '이번 달'(relative 당월) 시점으로 오주입 — 12개월 창이 한
달로 좁혀지고 입도 라우팅이 막힘(디버깅 중 실측).

수정(chat_service):
- **입도 감지** `_timing_granularity(question)` → month/day/None. 표지: 몇 월/어느·무슨·
  좋은 달/'~하는(할·될) 달'/'달은 언제' 등 + 날짜 계열(며칠·길일·날짜·좋은 날(?!씨) 등).
  '한 달(기간)'·'다음 달(시점)'·'날씨'·'달라지다' 오탐 방지 테스트 고정.
- **gran_no_period**(입도 명시 + 기간 없음 + 비회고·비구조·비택일) → vague_future 제외,
  wants_monthly 편입, **오늘 절기 당월부터 12개월 롤링 창**(2026-06-18 '올해 달력 연도로
  좁힘' 결함 회귀 방지 — 기존 '앞으로/향후' 분기와 동일 창).
- **응답 형식 디렉티브 2종**: _MONTH_PICK(유리한 달 1~3개, 활성화 창 표현, 12개월 밖 강한
  해는 참고로만, 연 나열 금지) / _DAY_PICK(날짜 즉석 단정 불가 → 달로 좁혀 답하고 '달을
  정하면 날짜 단위로 좁혀 볼 수 있다' 안내). 택일 분류(DATE_RECOMMENDATION)는 기존 라우트
  불변.
- **만남 디렉티브 달 변형** _MEETING_TIMING_MONTH_DIRECTIVE: 달 명시 시 '연·계절로 뭉개기'
  대신 유리한 달 1~2개로 — 비택일·장소 단정 금지 원칙은 유지.
- **시점 유사도 보강 가드**: 입도 명시 질문은 augment 스킵(멀티턴 '언제·추천형 시점 미승계'
  가드와 동일 원리).
- 보존: 입도 미지정 '언제쯤~' 질문은 기존 10년 digest 유지(2026-06-18 결정), 연도 명시
  '2027년 몇 월' 질문은 기존 창 로직.
- 검증: 신규 test_timing_granularity_routing.py 10건(감지 4·오탐 방지 6문형·dry_run E2E —
  실사례 질문 월별 창 2026-06~2027-05 확인·digest 부재·만남 달 변형·택일 불변·digest 보존).
  전체 1491 passed·1 skipped, ruff·mypy clean. 백엔드 재기동, 터널 체인 정상.

### 메인·테마사주 노출 문구 — 사용자 베네핏 중심 재작성 (2026-07-03)

데굴님 지적: 서비스 카드·페이지 설명이 개발자 구분용('결정론적 엔진이 계산', '페이지 단위
풀이 제공' 등)으로 쓰여 있음. '우리가 어떻게 하는지'가 아니라 '사용자가 무엇을 얻는지'로 전면
교체(문구만 — 기능·라우팅 불변).

- 랜딩 히어로: 'LLM이 계산하지 않습니다…' → '생년월일시만 입력하면 명식부터 지금 흐르는 운,
  주제별 깊은 풀이까지 한곳에서' + 정확성 신뢰 한 줄(명리 규칙대로 계산, AI는 풀이만)을
  사용자 언어로 유지.
- 서비스 카드 4종(만세력/간지달력/테마사주/AI채팅상담): 입력→얻는 것 구조로. 예) 만세력
  '생년월일시·출생지로 원국과 대운/세운/월운을 확인하고 용신을 검증합니다' → '생년월일시만
  입력하면 … 한눈에 볼 수 있어요. 간단한 과거 확인으로 나에게 필요한 기운(용신)까지'.
- 테마사주 서브메인 인트로 + THEMES desc 5종(총운/한해풀이/애정·관계운/직장운/금전·횡재운)
  전부 베네핏 서술로(질문형 훅 포함, 단정 표현 없음 — 원칙 3 톤 준수). 테마 진입([topic])
  페이지는 theme.desc 재사용이라 자동 반영.
- 기타 페이지(만세력/달력/채팅/사주목록/풀이내역) 노출 문구는 이미 사용자향 — 변경 없음
  (엔진 언급은 코드 주석뿐).
- 검증: tsc clean·vitest 30 passed·production build 통과, 라이브(:4000) 반영 확인.

### 입력 폼 버그 2종 + 용신 재검증 이중 단계 제거 (2026-07-03, 데굴님 제보)

**① 즉석입력(상대정보) 출생지 미동작** — 원인: InlinePartnerForm이 출생지를 자유 텍스트로만
전송하는데 백엔드 지명 시드는 4개(서울/부산/도쿄/뉴욕)뿐이라 그 외 지명은 location.resolve
ValueError로 풀이 실패. 정상 경로(BirthForm — 만세력·신규 등록·동반자 추가)는 FE 큐레이션
목록(전국 시군구)에서 선택해 좌표·tz를 함께 보내므로 무사(신규 등록도 좌표 저장 확인 — 이상
없음). 수정: InlineBirth 스키마에 latitude/longitude/timezone 옵션 추가 + inline_to_birth가
좌표 전달(request-source resolve, 시드 무관) + 좌표 없는 시드 미등록 지명은 서울 폴백(풀이
중단 방지 — 미입력 폴백과 동일 정책). FE는 즉석입력 출생지를 BirthForm과 동일한 지역 검색
피커로 교체(선택 시 좌표 동반, 미선택 시 '서울 기준 계산' 안내). 변환 지점이 단일
(partner_resolve.inline_to_birth)이라 테마사주·채팅 즉석 상대 모두 수정 적용.
테스트 6건(test_inline_birth_location — 좌표 통과·미등록 폴백·시드 지명 유지·미입력 폴백·
부분 좌표 방어·버그 재현 전제).

**② 생년월일 연도 6자리** — InlinePartnerForm의 type=date에 min/max가 없어 브라우저가
6자리 연도를 허용 → 4자 입력 후 월 칸 자동 이동 안 됨. min=1900-01-01/max=오늘 추가
(BirthForm은 기존에 동일 처리 완료 — type=date 전수 2곳 확인, 그 외 날짜 입력 없음).

**③ 용신 재검증 이중 단계** — '답변 반영 완료→[검증 다시 진행]' 클릭 시 질문 폼이 아니라
'용신 등록 완료→[다시 검증]' 게이트가 한 번 더 나오던 문제. registered 게이트는 교차 기기
확정 사용자의 초기 진입 전용인데 redo 경로가 같은 게이트를 탐. 수정: 결과 페이지에
redoRequested 상태 추가 — '검증 다시 진행' 한 번으로 곧장 질문 폼, 제출 완료 시 리셋.
게이트 본연의 용도(초기 진입 시 질문 강요 방지)는 유지. 온보딩(StepYongsin)은 redo 경로
자체가 없어 무관.

검증: BE 1497 passed·1 skipped, ruff·mypy clean / FE tsc·vitest 30·production build 통과.
백엔드 재기동, 터널 체인 정상.

### 테마 애정·관계운 — 상대와의 관계 명시 수집·풀이 반영 (2026-07-03, 데굴님 지시)

문제: 궁합(RP) 풀이가 상대와의 관계(상사/부하/친구/연인/결혼예정/기혼/이혼예정/외도 등)를
모른 채 중립 연애 톤으로 생성됨 — 수집 입구도, 리포트 전달 경로도 없음(채팅만 관계 추론 소비).

- **관계 체계 확장**(relationship_hints — 채팅·리포트 공용): RELATION_TYPES에 crush(썸)/
  fiance(결혼예정)/divorcing(이혼예정)/affair(외도)/boss/subordinate 6종 추가(14종).
  RELATION_KO 라벨 + RELATION_FRAMING(관계별 풀이 방향 — 애정 단계별 톤 분리, 사회 관계는
  연애 프레임 금지, divorcing=정리/회복 결 분리, affair=훈계·미화 금지+현실 리스크 병기)
  + PERSPECTIVE_HINTS 신규 6종 + relation_context_lines([상대와의 관계] 블록 — 단정 금지
  꼬리 고정). **키워드 추론 규칙은 불변**(신규 값은 명시 선택으로만 유입 — 추론 확장은
  실사용 후, 회귀 리스크 차단). _RELATION_TO_USER에 identity 매핑 추가(채팅 폴백 호환).
- **스키마**: SubjectRef.relation_type(str|None — docs/03 B2 확장, 데굴님 지시로 확정).
- **리포트**: _ReportData.partner_relation_type(비SELF subject에서 추출) → RP-* 전 섹션에
  관계 블록 부착. 미지정=미부착(기존 중립 톤 하위호환, 판정·점수 불변).
- **FE**: 테마 상대 선택 단계(SubjectGateway)에 '나와의 관계' 셀렉트(13종+선택 안 함) —
  등록 카드·즉석 입력 모두 적용. 우선순위: 명시 선택 > 등록 동반자 저장값(relation_to_user)
  > null. RELATION_OPTIONS(BE 미러) 신설, buildReportSpec이 subjects[1].relation_type 전달.
- 검증: BE 신규 6건(라벨·프레이밍 전수/미지정 빈 목록/boss 위계·affair 균형 문구/RP-01·
  08·09 공통 부착/미지정 미부착) 포함 1503 passed·1 skipped, ruff·mypy clean. FE 신규 4건
  (명시>저장값>null 전달·옵션 미러) 포함 vitest 34·tsc·build 통과. 백엔드 재기동.
- 후속(미구현 명시): 등록 폼(온보딩)에서 relation_to_user 영구 저장 입력, 테마에서 선택한
  관계의 프로필 저장(현재 1회성), 채팅 즉석 상대 관계 선택, 신규 관계값 키워드 추론 확장.

### 사용자 노출 문구에서 '통변' 제거 (2026-07-03, 데굴님 지시)

'통변'은 일반 사용자가 모르는 명리 전문 용어 — 노출 텍스트에서 교체(전수 스캔 후 분류).
- FE: 채팅 로딩 '통변 작성 중…'→'풀이 작성 중…', GNB 메뉴 desc '대화형 통변'→'대화형
  사주 풀이'.
- LLM 누출 차단: 시스템 프롬프트 2곳 '사주 통변 서술가'→'사주 풀이 서술가'(LLM이 답변에
  용어를 따라 쓰는 경로 차단 — 고정 프롬프트 캐시 1회 무효화 수용). 신살 사전
  flipSide(백호) '현대 통변에서는'→'현대 해석에서는'(LLM 재료로 사용자 노출).
- 유지(내부 전용): 코드 주석·docstring·테스트 모의 문자열, 사전 basis 필드(전문가 감수용
  근거 — 감수자 대상 전문 용어 적합).
- 검증: 사전 validate 통과, llm failover 테스트·ruff clean, FE tsc·vitest 34·build 통과.
  백엔드 재기동.

### 지장간 잠재·유통 완화 — LLM 명식 prefix 배선 (2026-07-03, 데굴님 원리 확정)

감사 결과: 엔진 계산 계층은 데굴님 정리 원리와 일치(표면 부재≠완전 부재 분리 — raw_visible
기준 신약·오행결핍 유지 + hidden_support 별도 / 유통 _circulation이 지장간 포함 분포로
상생 고리 판정·'신약 완화 해석' 정보성 메모 / 강도 계층 정기0.6·중기0.2·여기0.2 + 통근
본기1.0·동기0.85·인성0.65 + 공망0.60·충0.75 감쇠 / 운 활성: 투출·MT2 회귀·충개고·암합·
공망 발동·SEASON_FACTOR·삼합국). **갭 = LLM 전달 누락** — 계산은 있는데 prefix에 지장간
잠복·유통 정보가 없어 풀이 문구 재료 부재.

수정(채팅·리포트 공용 serialize_chart_prefix — 명식별 고정값이라 프롬프트 캐시 안전):
- BirthChartSummary에 hidden_latents·flow_note 추가. build_birth_summary가 계산:
  표면 부재(raw_visible=0) 오행의 지장간 출처('亥중甲' 파싱 → '亥 중기 甲(정관)' — 단계·
  일간 기준 십성 병기) / 신약+유통 smooth일 때만 flow_note.
- prefix 라인 2종: ①[표면 부족 오행의 잠재 신호 — 지장간] 잠복 표기 + 과대평가 가드
  ('존재≠작동', 투출과 동급 서술 금지, 잠재·조건부, 운 유입·지지 합충 자극 시 활성,
  충 자극=사건화·변동 동반) ②[오행 유통] 완화 프레임(신강 뒤집기 금지, 운·환경 자극 시
  적응력·회복력 구조 — 데굴님 제안 문구 채택).
- 검증: 신규 test_hidden_latent_prefix.py 4건(사례 명식 잠복 라인·십성/유통 완화+신약
  유지/오행 구족 명식 미부착/prefix 결정성=캐시 조건). 전체 1507 passed·1 skipped,
  ruff·mypy clean. 백엔드 재기동.
- 후속 후보(감수 대상): 지장간 작동 강도 단일 스칼라화(현재 분포·통근·modifier 분산),
  범용 이벤트 스코어링에 '지장간+같은 오행 운 활성' 일반화(현재 결혼 MT2·묘고·암합·공망
  도메인별로만).

### 테마사주 목차 친화 표시 + 뷰어 목차 점프 (2026-07-03, 데굴님 지적)

문제: 목차 제목이 개발자 규격 용어('명식 속 주제 구조', '운에서 드러난 축재 형태' 등)라
사용자가 '이게 왜?'로 느낌 + 뷰어에 목차 단위 이동 수단 없음(이전/다음만).

- **친화 표시(규격 불변)**: 백엔드 report_plan.py 규격 제목(docs/10 — 원칙 10, 임의 변형
  금지)은 그대로 두고, FE `lib/section-display.ts`에 표시용 별칭(label)+한 줄 설명(blurb)
  매핑. 전 85섹션(F/C/W/J/R/RP/RL/Y) 전수 매핑(폴백 불필요 — 자동 검증). 예: '명식 속
  주제 구조'→'내 사주 속 이 주제'('사주에서 이 주제가 어떻게 드러나는지 봐요'), '운에서
  드러난 축재 형태'→'돈이 모이는 방식'. 매핑 없는 id는 원본 title 폴백(안전).
- **뷰어(ReportPager)**: 섹션 제목을 친화 라벨로 렌더 + 제목 아래 한 줄 설명(화면 전용,
  인쇄 시 숨김). 하단 페이저 가운데 'N/M · 제목' 표시를 **목차 열기 버튼**으로 전환 →
  목차 드로어(모바일 하단시트/데스크톱 우측 패널) — 장별 라벨·설명·현재 위치 하이라이트,
  클릭 시 해당 장 이동+상단 스크롤. 인쇄(PDF)는 전체 섹션 출력 유지(기능 불변).
- 검증: 섹션 ID 커버리지 85/85, FE tsc·vitest 34·build 통과. 백엔드 변경 없음(FE 전용).

### 통합 테스트 2건 교정 — probe 규격 반영 + too_broad 시점 합성 가드 (2026-07-06, 데굴님 승인)

2026-07-03 배치 커밋 시 발견된 통합 테스트 실패 2건 수정(데굴님 "1, 2 모두 수정" 승인).

- **test_calibration_feedback_endpoint**: 질문 수 `== 5` 고정 단언이 CAL-P0/P1 probe 추가
  규격과 불일치(실제 8 = 기본 5 + transition 1 + pair 2). 단언을 규격대로 갱신 — 채점 반영
  기본 5문항(event_list) + probe 추가 문항 총합 ≤ 3, feedback 응답은 기본 문항에만 제출.
- **too_broad 우회 회귀**: `_augment_time_by_similarity`가 '앞으로 내 운세 알려줘'의
  '앞으로'를 2027 연도로 합성해 B3 판정표의 too_broad('좁혀볼까요' 재작성 제안) 관문을
  우회, 종합운으로 흘러가던 결함(원인은 기커밋된 시점 유사도 보강). 가드 추가 —
  `assess(intent).status == "too_broad"`(무시점·무분야)면 시점 합성 스킵. 도메인 유사도
  보강 이후 호출이므로 유사도로도 분야를 못 잡은 질문만 해당. 분야 있는 완곡 시점 질문의
  보강 경로는 불변(멀티턴 '언제' 시점 미승계 가드와 동일 원리).
- 검증: 신규 test_time_augment_too_broad_guard.py 2건(too_broad 질문 time_range None 유지 /
  분야 질문 가드 비대상). 전체 1642 passed(.env 로드 — DB 의존 포함), ruff clean, 변경
  3개 파일 mypy clean.
- 참고(별도 사안): 리포 전체 `mypy .`는 변경과 무관한 기존 파일 38곳에서 110건 보고 —
  venv mypy 2.1.0 버전 드리프트 추정, 후속 정리 필요.

### 총운·채팅 서두 반복 방지 — '나' 공통 묘사 반복 제거 (2026-07-06, 테스터 피드백)

테스터 지적: 총운 매 페이지 첫 문장이 비슷한 '나' 공통 묘사("○○님은 ~한 사주…")로 시작해
"페이지를 안 넘겼나?" 느낌 + AI채팅 상담도 매 답변 동일 반복. 원인 = 두 표면 모두 매 LLM
호출에 명식 사실 블록이 필수 포함(계산 금지 원칙)인데, 기존 금지 지시가 '원국 전체 재설명'
수준이라 1~2문장 요약 캡슐 서두는 안 걸림. 수정 3건(데굴님 승인) — 모두 서술 프롬프트 전용,
점수·간지·판정 불변:

- **리포트 정적 지시**: 섹션 과제에 "첫 문장을 명식 공통 묘사로 시작하지 말 것 — 섹션 주제
  구체 내용으로 바로 시작, 명식 근거는 본문 중간에" 추가.
- **리포트 동적 서두 중복 차단(핵심)**: 섹션 순차 생성을 활용 — generate_fn이 각 섹션 첫
  문장을 `_ReportData.record_opening`으로 기록(최근 3개), build_section_context가 다음 섹션
  프롬프트에 "[서두 반복 금지 — 직전 섹션들이 이미 사용한 첫 문장]" 블록으로 실제 문장을
  주입. 추상 금지가 아니라 피할 문장을 구체 제시. dry-run(plan_report)·첫 섹션은 기록 없어
  미부착(하위호환). LLM 추가 호출 0, 섹션 프롬프트는 원래 가변이라 캐시 영향 없음.
- **채팅**: `_CHAT_SCOPE_DIRECTIVE`(전 턴 부착)에 "첫 문장은 이번 질문에 대한 답으로 바로
  시작 — 명식 공통 묘사로 답변을 열지 말 것" 추가(후속 턴 지시와 별개로 첫 턴부터 적용).
- 검증: 신규 test_opening_repetition_guard.py 6건(정적 지시/동적 블록 부착·미부착/기록
  cap/첫 문장 추출/채팅 문구). 전체 1648 passed, ruff clean, 변경 파일 mypy clean. 라이브
  채팅 확인 — 답변이 "이번 달 재물운은…"으로 본론 직행(명식 캡슐 서두 소멸).

### 서두 반복 방지 확장 — 테마사주 커버 확인 + 채팅 스레드 내 반복 차단 (2026-07-06, 데굴님 후속)

데굴님 확인 질문 2건에 대한 답 + 보강.

- **테마사주(집중/한해) 커버**: 직전 수정이 이미 전 상품 공통 경로(build_section_context·
  generate_report의 generate_fn)에 있어 RPT_FULL/RPT_YEAR/RPT_FOCUS 모두 적용됨 — 회귀
  테스트로 명시 고정(test_ban_block_covers_theme_products: FOCUS·YEAR 동적 블록+정적 지시
  부착 검증).
- **채팅 스레드 내 반복(신규 갭)**: 스레드 후속 턴에 직전 답변(prior_answer — 라우터가
  history에서 전달)의 실제 첫 문장을 "[서두 반복 금지 — 직전 답변의 첫 문장]" 지시로 주입
  (_THREAD_OPENING_BAN). 리포트 섹션 동적 차단과 동일 원리. 전개 구성 판박이 금지 문구 포함.
- **first_sentence 헬퍼 단일화**: report_service 로컬 → saju_engines.context_reducer 공개
  함수로 이동(채팅·리포트 공용). 채팅 답변이 해요체인 점 반영 — 종결어미를 '다.'→
  '다./요./죠.'로 확장(해요체 첫 문장이 안 끊기던 결함 예방).
- 검증: test_opening_repetition_guard.py 10건으로 확장(테마 상품 커버/스레드 주입/첫 턴
  미부착/해요체 추출). 전체 1651 passed, ruff clean, 변경 4개 파일 mypy clean.

### 전체 검증 게이트 점검 + 잡 통합 테스트 skip 가드 누락 수정 (2026-07-07, 데굴님 요청)

전 게이트 일제 점검(pytest·ruff·mypy / tsc·build·vitest) 결과 pytest 1건 실패 발견·수정.

- **원인**: `test_report_jobs_api.py::test_job_lifecycle_and_owner_isolation`에만
  `@pytestmark_db`(전용 DB 5433 미기동 시 skip) 데코레이터가 누락 — DB 꺼진 환경에서
  skip되지 않고 실행되다 register 503(`저장소(DB) 미설정`)→`KeyError: 'token'`으로 실패.
  형제 테스트와 동일하게 데코레이터 부착(한 줄).
- **mypy 잔여 백로그**: 리포 전체 13건/7파일(기존 110건에서 감소, mypy 2.1.0 드리프트
  건 — scripts/ 11건 + manse_service.py 서브모듈 import attr-defined 오탐 2건). 신규
  회귀 아님, 후속 정리 대상 유지.
- 검증: 해당 파일 1 passed·2 skipped(DB 미기동), ruff·mypy clean. FE tsc·production
  build·vitest 34 passed 모두 통과.

### 독립 개발 가능 항목 일괄 — mypy 백로그 해소·mapper 강제(#4)·1c-β 구현·문서 싱크 (2026-07-07, 데굴님 승인)

정확도 점검에서 나온 항목 중 외부 감수·사용자 참여 불필요한 4건 진행. 화기격 재평가·용신
투출 천간 손상·합거/합반 점수는 스펙 미정의(#규칙10)·캘리브레이션 필요로 제외.

- **mypy 백로그 13건 전량 해소**: 서브모듈 from-import → `import ... as ...` 전환
  (manse_service·measure_tokens·scoring_guard 2종), dict 값 타입 주석(extract_osm·
  build_geo·qa_calibration_probes). measure_tokens 는 `scorer.score()`(V2 반환)→
  `score_legacy()`로 교정 — build_llm_input 계약(EventCandidate)과 일치·실서비스 경로와
  동일 측정. 전체 `mypy packages apps scripts` 273파일 clean.
- **역할 문자열 파싱 금지 — mapper 강제(용신 spec §10-2 #4)**: operational_role_config 에
  `role_class`/`is_favorable_role`/`is_unfavorable_role` 헬퍼 신설, 클래스 판정(용·희/기·구
  묶음) 전 사이트를 mapper 경유로 이관 — event_engine_v2(2)·relations_engines(1)·
  topic_builder(3)·relocation(3)·chart_interpretation(1)·region_direction(2)·
  region_element_engine(2)·date_selection(1)·context_reducer(4). 세분 exact enum 비교
  (용신 단독·한신·PolarityRole 매핑·희신+한신 도메인 집합)는 정책 허용대로 유지.
  출력 불변 — 전체 회귀 통과로 확인.
- **1c-β near-tie demotion 구현(스펙 §14 규격·계수 그대로)**:
  `scoring_operational.near_tie_demotion_order` — 동일 level·event group·legacy 순위차
  ≤3·score 차 ≤5 인접 쌍만, 감점(delta≤−6)·adjusted 역전 시 후보당 max 2칸 후순위화,
  top-N(10) 변화 >1 이면 legacy fallback. context_reducer 배선(LLM 노출 순서만·엔진
  .score/rank/reduce 불변). **sub-flag 기본 off → byte-identical, 활성화는 누적 관찰 후
  별도 승인(기존 결정 유지).** 신규 test_scoring_near_tie.py 15건(게이트 5·조건 미충족
  5·cap/top-N 3·배선 2).
- **문서 싱크**: LIFE_EVENT_INFERENCE.md 모듈 표(personal_calibration·life_fit_ranker
  ❌→✅ 실코드 매핑)+§7 구현 현황(1~5 완료·6~8 남음). 용신 spec §10-2 #4 완료 표기·
  §14 1c-β 구현 완료 표기.
- 검증: BE 1628 passed(신규 15 포함)·38 skipped(DB 미기동), ruff clean, mypy 273파일
  clean. FE 변경 없음(금일 tsc·build·vitest 34 통과 유지).

### 배우자궁(일지) 성향 보조 사전 — 상담가 강의 경험칙 반영 (2026-07-07, 데굴님 승인)

영상 강의(배우자궁 4인자·일지 계절론) 정리에서 데굴님이 1·2번 항목만 "성향 묘사 보조
자료 수준" 반영을 승인. 명의(부동산)·외도 상대 규칙은 근거 취약·민감성으로 제외(사전
note 에 제외 사유 기록).

- **사전**: `dictionaries/interpretations/spouse_palace_tendency.json`(reviewed:false) —
  ①4인자(子亥巳午): 희생 대가 부재·모질지 못함·소속 유리·순발력 강점 ②계절(寅卯辰巳午未=
  봄여름/申酉戌亥子丑=가을겨울): 배우자 유형·사랑 스타일 경향. 원 강의의 단정 톤
  ("정확도 높다"·연상/연하 예측)은 경향·끌림 묘사로 변환, "경험칙" 명시(절대 원칙 3).
- **배선**: `chart_interpretation._spouse_palace_excerpts` — kind=`spouse_palace_tendency`
  발췌(최대 2건, 상보 레이어)를 excerpts 말미 부착 → [명식 해석 자료 — 점수·판정 변경
  금지] 블록으로 대화·리포트 공용 유입. 말미 부착이라 토큰 압박 시 우선 절삭(보조 자료
  우선순위). 전 발췌에 "(경험칙·감수 전 — 성향 묘사에만 보조 인용, 판정·시기 인용 금지)"
  마킹 강제. 점수·판정·시기 산출 미개입(순수 텍스트).
- 강의 중 "배우자궁 합충 = 이성 사건 트리거"는 기존 MT2/관계궁 발동 설계와 일치 —
  신규 반영 없음(교차 검증 사례).
- 검증: 신규 test_spouse_palace_tendency.py 7건(사전 규격·단정 금지·4인자/계절 분기·
  마킹·통합·chat 노출). 전체 1635 passed·38 skipped, ruff·mypy clean,
  validate_dictionaries 76파일 통과.

### 운 십성 출처 강도 배선 + 비견·편재 규칙 — 재물운 영상 대조 P1·P2 (2026-07-12, 데굴님 승인)

유튜브 재물운 강의(운 간지 상하 슬롯 십성 조합 7종) 전수 대조 결과, 사전에 스펙만 있던
`transit_source_strength` 배율이 미배선임을 확인 → 배선 + 커버리지 보강. 결정 4건
(데굴님): ①조합 배율=기여 십성 강도 산술평균(개수 보너스 금지) ②동일계열 1.25 판정=
십성군 기준·지지 본기만(丙午 정인+편인 성립 — 운 간여지동) ③SPEC_BIJIAN_PIANCAI 신규
④식신+편인은 이벤트 불변, 문구만 도식 단정→조건부 양면 구조로 수정(긍정 경로는 추후
Phase D 서술 시드).

- **엔진**: `ten_god_brancher.py` — TransitSignal에 strength/same_group/same_god,
  collect_from_pillar가 천간 1.0·지지 본기 0.9·동일 십성군 기둥 1.25(사전 로드,
  하드코딩 없음) 부여. branch()는 규칙 점수 × 기여 십성 강도 평균(round). 설명 태그
  SRC_SAME_GOD(甲寅류)/SRC_SAME_GROUP(丙午류) reason_codes 부착, contributions에
  src_strength 기록. 지장간 중기·여기(0.55/0.35)는 신호 미수집이라 범위 밖.
- **배경층 제외 설계**: 동일계열 1.25는 채점 대상 층(is_target)에만 — 세운 간여지동이
  그 해 전체 월운을 일괄 증폭해 교운 가중 실측 랭킹(case12, 2025-11 재취업 1위)을
  깨는 것을 확인하고 차단(`event_engine_v2._score_target` 배선, addendum notes 명문화).
- **사전**: SPEC_BIJIAN_PIANCAI(비견+편재 — business_start/expansion 52·wealth_change
  52·windfall 41, 확장·개업 국면, 감수 대상) 추가. SPEC_PIANYIN_SHISHEN quality 양면
  구조 문구 수정(동작 무영향 — 규칙 레벨 quality는 문서용). stem_branch_same_god
  notes에 십성군·본기·배경층 제외 기준 명문화.
- **부수 효과(의도된 변별)**: 지지 본기 단독 유래 약신호가 0.9 감쇠로 SCORE_FLOOR(40)
  아래로 이동 가능 — test_in_period_candidates_are_main 을 경계선 후보(연애 40점)에
  의존하지 않는 직업 도메인 질문으로 교체(기간 필터 검증 의도 보존).
- 검증: 신규 브랜처 테스트 7건(출처 배율·간여지동 증폭/태그·배경층 제외·평균 배율·신규
  규칙). 전체 1689 passed·38 skipped, ruff·mypy(111파일) clean, validate_dictionaries
  77파일 통과, case12 실측 랭킹 복원 확인(2025-11 raw 230 > 2026-02 209.7).
- **후속(P2 잔여)**: 정인+재성 세분 SPEC은 그룹 규칙(COMBO_WEALTH_RESOURCE)이 커버해
  보류. "운 도래 전 준비기(lead-up)" 모델(P3)·오행-산업 매핑(P4)은 미착수 — 착수 전
  데굴님 규칙 확정 필요.

### 재물 준비기(lead-up) 서술 레이어 — 재물운 영상 대조 P3 (2026-07-12, 데굴님 승인)

"재성 운 도래 전 준비해야 발현" 프레임을 서술 전용 inert 레이어로 신설. 규칙 4건
데굴님 확정: ①준비 창=발현 후보년 직전 2년(Y-1 가중 1.0·Y-2 0.55, Y-3·대운 확장 금지)
②준비 십성=식상 1차·비겁 2차 조건부(식상+비겁 또는 두 자리 모두=강/식상=중/비겁 단독=약),
인성은 준비년 단독 생성 금지(식상 동반 시 resource_support 보조 태그만) ③발현년=확정이
아닌 '후보 등급제'(천간·지지 모두 재성=strong/한쪽+식상 동반=moderate/한쪽 단독=weak,
지장간 전용 배제) — 이벤트 엔진은 발현년 결정 불관여(순환 참조 방지) ④서술 전용 inert:
점수·후보 순위·발현 시점·confidence·favorability 불변, 사건 생성 금지.

- **타입**: `shared_types/preparation_context.py` — ManifestationCandidate/
  PreparationYear/PreparationContext(usage=narrative_only 고정).
- **엔진**: `saju_engines/preparation_context.py` — 세운 십성 라벨만 조회하는 순수 함수
  `build_preparation_context(yearly_luck, 기준년, horizon=5)`. 후보 상위 3(등급·근접 우선),
  현재년 역할(preparation/manifestation/none) 판정. 과거 준비년은 세운 창(올해±5) 내에서만.
- **직렬화**: `structural_context.preparation_context_lines` — [재물 준비기 신호] 한글
  블록 + 서술 규칙 4항(과거 준비년 회상·확인형 한정, 인과 확정 금지, 질문 시간 지평 초과
  후보 서술 금지(docs/16), 비겁 단독 조건부). 미검출=빈 목록(무언급).
- **배선**: chat `_structural_blocks`(general 또는 WEALTH 도메인, 기존 wealth_capacity
  블록과 동일 조건) / report W-06(5년 종합)·W-08(재물 행동 전략) 섹션 주입.
- 검증: 신규 test_preparation_context.py 6건(등급·창·강도·인성 단독 금지·무언급·지평 경계·
  디렉티브). 전체 1695 passed·38 skipped, ruff·mypy(164파일) clean. 실배선 확인 —
  1980-11-22 명식에서 2031 辛亥(식상생재 moderate)·준비년 2030/2029 판정, 점수 불변
  (회귀 전체 통과).
- **후속**: P4(오행-산업 매핑) 보류 유지. 준비기 신호의 리포트 목차 확장·개인 캘리브레이션
  연동은 골든 사례 축적 후 재논의.

### 동반자 첨부 대상 해소 결함 수정 — need_subject 무한 반복 (2026-07-12, 실사용 리포트)

라이브 테스트(스크린샷): FE 칩으로 '남편' 첨부 후 "남편 사주로 대출 시 어떤 흐름일지
봐달라고" 질문 → "'남편'가 어느 분인지 확인이 필요해요" need_subject 무한 반복.

원인 2건: ①대상 해소(A9)가 서버 등록 별칭 인덱스만 조회 — 게스트·인라인 첨부는 서버
레지스트리에 없어 '남편' 지칭이 unresolved로 빠짐(첨부 폴백 `inline:partner`→partner_birth
는 다운스트림에 이미 있었으나 그 앞 조기 반환에 막힘). ②'대출'이 재물 도메인 키워드에
없어 해소를 통과해도 general→too_broad로 이탈.

- **수정 1**: `companion_alias.merge_attached_partner` 신설 — 첨부 라벨(정규화)을 첨부
  대상 단일 항목으로 인덱스에 덮어씀(명시 선택 > 텍스트 해소, 원칙 7. 동일 라벨 등록
  대상과 ambiguous 처리하지 않음). chat_service의 ConversationEngine 생성 시 병합.
  등록 첨부=그 subject_id, 인라인 첨부=`inline:partner`(기존 birth 폴백 키와 정합).
- **수정 2**: `query_parser` WEALTH 키워드에 대출·융자·빚·부채 추가.
- **부수**: need_subject 안내문 조사 교정("'남편'가"→"'남편'이(가)").
- 검증: 신규 테스트 4건(미등록 첨부 해소·동일 라벨 우선·registered id·noop). 실서버
  재현 — 첨부 시 chat_single·domain wealth·base=남편 명식·재물/준비기 블록 주입 확인,
  미첨부 시 need_subject 확인 질문 유지(회귀 없음). 전체 1699 passed·38 skipped,
  ruff·mypy clean.

### 용신 역할 배정 — 희신=과다(병) 교정 (2026-07-12, 데굴님 확정)

실사용 리포트: 丁巳/壬子/丁未/癸卯(丁火 신약·子월 관살 태왕)에서 희신 水·한신 火로 표기 —
"水生木이므로 水=희신"의 기계적 생극 순환이 원국 과다(관살 병)를 무시. 올바른 역할맵
(살인상생형: 희=비겁 火·한=관살 水)은 operational 계층에만 있고 final(사용자 노출+점수화
SSOT)에 미반영이던 구 설계(Phase 0 'final 불변')를 폐기하고 교정 승격.

**보편 조건**: 정적 생극 순환이 배정한 희신 오행이 원국 과다 병(_overloaded_element —
관살/식상/인성/비겁 기존 임계 재사용)과 일치하면 희신 부적격 → 선택 모델이 5역할 완비
자체맵으로 교정 중이면(모델 희신≠병) final 도 모델맵 채택. bridge/무비겁 특수분기 제외.
새 명리 상수 없음(기존 과다 판정·기존 모델맵만 재사용).

- **candidates.py**: overload_heesin_fixed 분기 + model_map_adopted 확장(교정 케이스 포함
  — Phase 1~4 주석·조건부 라벨 계속 작동). 신규 operational 라벨 **'조건부 한신/병'**
  (병 오행이 한신 강등된 케이스 — 중첩 유입 시 기신성, 중립 한신 처리 금지):
  OperationalRole enum·ROLE_CLASS(conditional)·SHADOW_ROLE_WEIGHT(0.0, 점수 계열 불변)·
  CONDITION_TEMPLATES·LUCK_OPERATIONAL_GUARD 추가. climate_harmful 병합·warnings ①을
  희신/한신 강등형 공통으로 확장. shadow_chart_specs 관살태왕 스펙 라벨 갱신.
- **결과(신고 차트)**: 용 木·희 火·기 金·구 土·한 水 + operational 火=조후보조신·
  土=조건부 제살보조·水=조건부 한신/병 — ChatGPT 감수 제안과 완전 일치(조건부 뉘앙스 포함).
- **파급**: 동일 살중용인 구조(예: 丑월 壬/癸 관살 토왕)도 동일 교정 — 의도된 일반화.
  구 '정적 순환 불변'을 고정하던 operational/shadow/scoring 계열 테스트 49건을 새 정답으로
  갱신. 가드·shadow '기계' 검증(조건부 희신/병 감점 −12·조건부·유보 클램프)은 교정 후에도
  해당 라벨이 남는 차트(1970-01-13 癸巳 — 비겁 희신이 한습 조후 역행으로 강등)로 차량 교체
  (의미 보존). **회귀·통합·캘리브레이션 스위트는 무수정 통과 — 그 외 명식 부수 피해 없음.**
- 검증: 전체 1699 passed·38 skipped, ruff clean, mypy 243파일 clean.
- **주의**: data/shadow_charts/charts.jsonl 의 kansal_taewang/sarin_sangsaeng/
  conditional_byeong 계열은 교정으로 라벨이 바뀌어 spec 재탐색(find_shadow_charts) 대상 —
  하네스 재실행 시 재생성 권장(운영 미연결이라 서비스 영향 없음).

### 유사 오류 전수 점검 + 모델맵 final 채택 전면화 (2026-07-12, 데굴님 확정)

희신=과다(병) 교정 직후 "유사 오류" 전수 점검(672명식 그리드, 1950~2005): final(정적
생극 순환) ≠ 선택 모델 자체맵이 **204건(30%)** — 6개 모델 유형.

- **A군(명백 동일 계열 오류, 154건)**: ①억부형 신강 78/80 — 희신=비겁(신강 강화 방향)
  ②군겁쟁재형 37/37 — 희신=재성(쟁재 대상)·기신=식상(통관 오행) ③인성제식상형 39/43 —
  희신=관성(신약 극신). 모델 자체맵(희=재성/식상/비겁)이 명리 통설과 일치.
- **B군(감수 검토 후 채택, 38건)**: ④인수격 관성용신형 27 — 기신: 정적=식상 vs 모델=
  인성(40~50% 과다 병) ⑤財損印 재성용신형 11 — 정적이 병(인성)을 구신으로 방치,
  모델은 기=인성·희=관성(도식으로 식상 무력 → 재생관 유통). 실측 예시 3건씩 비교 검토
  결과 두 유형 모두 '과다 병 우선' 원칙에 모델맵이 정합 — 데굴님 채택 확정.
- **정상(by design)**: 부일간 무비겁 특수분기 12건 — final 이 이미 맥락 교정값(보존).
- **조후 축(참고)**: 과다 임계 미달 조후 역행 희신(한습월 水 등) 소수 잔존 — operational
  '조건부 희신/병'+운 가드가 커버, final 개입은 조후 우선순위 재설계 필요로 보류.

**구현(단순화)**: 단계적 허용목록 대신 **"5역할 완비 선택 모델은 final 도 자체맵 채택"**
으로 전면화(candidates.py model_map_promoted). 직전 커밋의 overload_heesin_fixed 조건은
전면 채택에 흡수·제거. 정적 생극 순환은 부분맵 모델(johu/pattern/disease/bridge/follow)·
특수분기 폴백 전용으로 강등. 재스캔: 잔여 불일치 = 특수분기 12건뿐(설계 보존).

- 검증: 전체 1699 passed·38 skipped(무수정 — A·B군 구 final 을 고정한 테스트 없음),
  ruff·mypy clean. 회귀·통합·캘리브레이션 통과(전면화 파급은 A+B군 192/672≈29% 명식의
  희·기·구·한 교체 — 용신 불변·모델 선택 불변).
- **후속**: 골든 사례 축적 시 A·B군 교체 명식들의 운 판정 정확도 재검(캘리브레이션),
  재성용신형 희=관성의 관생인 부작용은 operational 조건부 주석 후보.

### 대상 지칭 오탐 2종 수정 — 문맥 소유격·명시적 제외 (2026-07-12, 실사용 리포트)

라이브 스크린샷: "이사는 아들의 교육을 위해 가는거야"(문맥 언급)가 '아들' 확인 질문을
유발하고, "아들사주는 빼고 봐줘"·"아들사주는 안봐도 된다니까"(명시 제외)에도 같은
need_subject 가 무한 반복.

- **수정 1(소유격 조건 강화)**: _REL_REF_RE 의 소유격('~의') 분기를 "뒤에 풀이성 명사
  (사주/팔자/궁합/운세/신수/운)가 8자 이내에 이어질 때만"으로 한정 — "아들의 교육을
  위해"는 미트리거, "아들의 취업운/사주"는 유지.
- **수정 2(제외 표현 처리)**: _EXCLUDE_TAIL_RE + _mention_excluded 신설 — 지칭 토큰
  직후 정규화 창(12자)에서 빼/제외/안봐/안보/보지마·않/필요없/말고/없이 확인 시 그
  토큰은 ①등록 동반자여도 해소 제외 ②미등록이어도 확인 질문 제외(토큰 단위 —
  "아들 빼고 남편이랑"은 남편만 해소).
- 검증: 신규 테스트 5건(문맥 소유격 미트리거·풀이명사 소유격 유지·제외 3표현·등록
  동반자 제외·토큰 단위 제외). 실서버 재현 — 스크린샷 3개 발화 모두 need_subject 없이
  진행. 전체 1704 passed·38 skipped, ruff·mypy clean.

### 균시차 설정 미영속 — 만세력 화면과 풀이(챗/리포트)가 다른 시주를 쓰던 문제 (2026-07-13)

라이브 테스트(2015-03-01 03:34 남·서울 "아들"): 만세력 화면(균시차 토글 OFF)은
庚寅시·용신 金/희신 水, 챗·리포트 풀이는 己丑시·火/金 — 같은 사주가 경로마다 다른
명식으로 계산. "화/금이어야 하는데 금/수 회귀" 리포트의 실체는 회귀가 아니라 변형
혼동: 庚寅판은 최소 6/11 이래 항상 용신 金(財損印)이었고, 희신 水만 7/12 모델맵
전면화(36e0666)로 土→水.

- **원인**: 균시차 토글은 만세력 페이지 localStorage 전용. 대상 등록의
  profileToBirthDTO(frontend/lib/subject-mapping.ts)가 time_options를 싣지 않아
  서버는 항상 pydantic 기본값(모든 보정 적용=균시차 ON)으로 저장 → 챗·리포트는
  저장된 birth를 그대로 사용(routers/chat.py·report.py).
- **수정(FE)**: profileToBirthDTO에 timeOptions 선택 인자 추가, 온보딩 Wizard가
  저장 시 loadEotPreference()를 apply_equation_of_time으로 영속화. BirthInputDTO에
  time_options 필드 추가. 등록·수정 모두 커버(등록 경로는 Wizard 단일).
- **데이터 교정**: "아들" subject의 birth.time_options.apply_equation_of_time을
  false로 UPDATE(1건) — 저장본 재계산으로 庚寅시 확인.
- **회귀 테스트**: test_yongsin.py에 균시차 미적용판(乙未 戊寅 丙子 庚寅) 특성화
  테스트 추가 — 財損印 선택·金/水/木/火/土 고정. ※ 庚寅판에서 통관(bridge) 후보가
  아예 생성되지 않는 것이 명리적으로 타당한지는 감수 쟁점으로 보류(적용판 己丑은
  기존 test_2015_excess_resource_is_gisin이 火/金 유지).
- 검증: backend pytest 전체 통과(실패 0)·ruff clean·mypy 243파일 clean, FE vitest
  35 passed(신규 time_options 케이스 포함)·tsc·production build 통과. 저장본 E2E:
  DB birth → calculate = 庚寅·金/水로 만세력 화면과 일치.
- **후속(미해결)**: 균시차 설정이 사주별 속성이 아니라 기기 로컬 토글이라 두 진실
  소스가 여전히 공존 — 만세력 화면이 저장 subject의 time_options를 초기값으로 쓰는
  동기화, 등록 화면 내 명시 옵션 노출은 별도 결정 필요.

### 偏印奪食 감지 + 화인통관 치료 중재 — 용신 P0~P2.5 (2026-07-13, 데굴님 감수 확정)

2015-03-01 03:34 균시차 미적용판(乙未 戊寅 丙子 庚寅) 감수: 병=월주 偏印奪食(월간
戊식신 vs 월지 본기 甲편인), 치료=火통관(化印·扶身·通關·生食)으로 木→火→土→金 식신생재
복원 → **기대 판정 火/金**. 기존 엔진은 庚 투간만 보고 게이트 없이 財損印(金/水)을
고신뢰(0.89) 선택 — 재성 무근·실령·피극, 통관 후보 미생성(양강 25% 게이트), 조후 축
부재(寅월)가 원인.

- **P0(테스트)**: 특성화 金/水 삭제 → 영구 원시 신호(월간 식신·월지 본기 편인·시간
  편재·庚 무근·잠재 火(본기 火 지지 없음)·子中癸 관인상생 경로·乙庚 원거리 합 감지·
  己丑판 대비 인성/신강 증가) + strict xfail 火/金(구현 후 정상 승격).
- **P1(candidates.py)**: `_wealth_standalone_operability` — 재성 무근(지지 지장간 金
  전무)이면 財損印 confidence ×0.55(실령·피극 시 ×0.9 추가), **필요성은 유지**(후보
  존속·희신 경로 보존, 데굴님 #2). 통근 재성은 무감점(진짜 財損印 보존).
- **P2**: `_output_disease` 2계층 — 특수형 偏印奪食(식신 투간 + 같은 주 본기 편인
  대립/인접 천간 편인 접촉) ⊃ 일반형 印旺克食(접촉 없음·낮은 강도), 중복 가산 금지.
  상관 투간은 미발동(별도 규칙 확정 전). `_additional_mediator_operability` — **일간
  자신 제외**(데굴님 #4) 추가 통관 가용량: 천간 비겁 0.4/왕지 본기 0.35/지장간 중·여기
  (잠재, 데굴님 #2) 0.1/득령 0.2, 임계 0.45 미만일 때만 `food_rescue:pyeonin_talsik|
  inwang_geuksik` 모델 승격(용=비겁 희=재성 기=인성 구=관성 한=식상, eokbu 축 경쟁).
  채택 시 operational 주석: 土=protected_output(보호 대상 식신), 金=필요성/작동성 분리,
  水=官印相生 병 재생, 火=과다 시 무근 재성 극 상한.
- **P2.5(재스캔)**: 672명식(1950~2005) diff — **교체 1건**(1965-05-15 乙巳 辛巳 己巳
  庚午, 극신강 己·火인성 45%·재성 水 전무 → 財損印(水)→food_rescue 일반형(용=土 희=水)).
  財損印 감점-유지 0건(그리드 내 무근 재성 財損印이 이 1건뿐). 골든 가드: 庚寅판 火/金
  도달·己丑판 불변·노출 화력 충분(시간 丙) 억제·식신 미투간 미발동·상관 미발동·신약
  미발동(분기 밖) — 가드 3종 영구 테스트 고정.
- 검증: 전체 pytest 통과(실패 0)·ruff clean·mypy 243파일 clean.
- **감수 대기**: 1965-05-15 판정(극조열 巳월·재성 水 전무 명식에서 용=土 비겁 통관 vs
  조후 水 우선 — 희신으로 水 보존됨). **후속**: P3 乙庚합 이원화(설명 중심·점수 상한·
  동일 신호 소비 가드), P5 시두 경계 민감도 플래그, P4 궁통보감 조후 사전(壬癸 구분).

### 1965-05-15 감수 반영 — mediator veto + 조후 필요도 보존 (2026-07-13 데굴님 확정)

감수 결론: 1965-05-15(乙巳 辛巳 己巳 庚午, 극신강 己·조열 巳월·水 전무)는 **용신 水
복귀**. 화인통관 土 승격은 오판(일간 오행 보강=신강 악화·건토 심화·金 매몰). 복귀
방식은 "조후 필요신 무근 감점 완전 면제"가 아니라 **필요도 계층 보존 + 감점은 작동성
계층 유지**(climate_need_preservation).

- **mediator veto**(`_mediator_promotion_veto`): 비겁 mediator 주용신 승격 금지 3사유 —
  ①극신강(strength_aggravation, 태신강은 허용 → 庚寅판 보존) ②mediator 오행 자체
  포화(계절보정 ≥25%) ③조후 악화(조열월 土 / 한습월 水 mediator). 차단 시 경고 명시,
  병 감지는 유효(財損印 등이 경쟁 승계).
- **climate_need_preservation**(`_wealth_standalone_operability`): 극단 한열월의 조후
  필요신(조열 水/한습 火)이 무근·부재(<22%)면 결핍의 증거 — canonical 감점 미적용,
  무근 감점은 기존 Phase 4a operability(no_root)에만 남음(1965 실측: 水 operability
  0.68·no_root — canonical 용신 순위는 불변).
- **부수 발견·수정(비결정성)**: `_classify_bridge_roles` 폴백 3곳이 set 순회+max 동점으로
  **프로세스 해시 시드에 따라 희신이 플립**(실측 1953-01-15 壬辰 癸丑 丙寅 甲午 —
  PYTHONHASHSEED 0/1=火, 2/3=木). sorted 순회로 결정화 — 오늘 변경과 무관한 선재 버그.
- 재스캔: 672 그리드 diff = **1건**(1953-01-15 희/한 스왑 — 비결정성 동점이 canonical
  순서로 고정된 것, 판정 로직 변경 아님). 1965 복귀·庚寅판(火/金) 보존 확인.
  1965 회귀 테스트 추가(모델·용신·차단 경고·operability 감점 잔존).
- 검증: 전체 pytest 통과(실패 0)·ruff clean·mypy 243파일 clean.
- **참고(P4 연계)**: 감수 이상형은 조후 모델(climate_dryness_correction)이 1965의
  주모델이 되고 희신=金(설기·생수) 지정 — 현재는 財損印 복귀(희=木 모델맵)로 잠정,
  조후 사전(P4) 설계 시 재방문. 1953 동점 희신의 의미론적 타이브레이크(생용신 우선 등)도
  후보 과제.

### 균시차 = 사주별 속성 승격 (로그인 한정, 2026-07-13 데굴님 확정)

직전 "두 진실 소스 공존" 후속 해소. 로그인 사주는 균시차가 **사주별 속성**
(birth.time_options, DB 영속)이고, 비로그인은 종전대로 기기 로컬(localStorage) 속성.

- **subject-mapping.ts**: `subjectEotPreference(summary)` — 저장값 false만 false,
  미저장(구 레코드)·부분 옵션은 백엔드 기본값 true.
- **만세력 결과 페이지**: `resolveProfile`이 SubjectSummary 동반 반환 → 초기 토글 =
  로그인 사주는 저장값·비로그인은 기기 토글. 토글 변경 시 로그인 사주는
  `updateSubject`로 birth.time_options 영속(챗·리포트 동일 기준), 비로그인만
  `saveEotPreference`. 영속 실패해도 화면 재계산은 유지.
- **간지달력 CalendarGrid**: 오버레이 일운 계산이 선택 사주의 저장값 사용(게스트는
  기기 토글) — 만세력 화면 토글과의 간접 공유 제거.
- **온보딩 Wizard**: edit 는 저장된 사주별 값 보존(기기 토글로 덮지 않음), add 는
  기기 토글 시드. `storedEot` 상태로 관리.
- 검증: vitest 36 passed(사주별 균시차 판정 4케이스 신규)·tsc·production build 통과.
  백엔드 무변경(BirthInput 왕복 저장은 기존 구조 그대로).

### 잔여 안건 P3·P5·P4 일괄 구현 (2026-07-13, 데굴님 착수 지시)

**P3 — 乙庚합 이원 평가(설명 전용)**: `_disease_remedy_binding` — 희신(치료) 천간과
기신(병) 천간의 천간합을 감지해 화인통관 채택 시 희신 ElementRole 에
①beneficial_binding(과다 병 천간 구속 이득) ②remedy_operability(자기 묶임 감소)를
병기. **점수·역할·confidence 불변**(score_delta 0). 간격극 차단·격위 약화도 강도
한정어와 함께 방향성 참고로 기록(庚寅판: "간격극 차단 — 실질 작용 제한"). 동일 신호
소비 가드 = 합은 이 주석에서만 소비, 모델 점수화 없음.

**P5 — 시두 경계 민감도**: TimeCorrectionResult 에 `hour_boundary_distance_seconds`/
`boundary_sensitive`(±180초)/`alternative_hour_pillar` 신설 — 경계 반대편 시각으로
시주 재산출(자시·일경계 규칙 동일 적용). 기준 사례 실측: 庚寅판 +114초·대체 己丑.
FE TrueSolarTimeCard 에 경고 표시. 테스트 3종(민감/비민감/시간미상).

**P4 — 궁통보감 조후 사전(천간 단위·壬癸 구분)**:
- `dictionaries/johu_yongsin.json` — 조후용신표 10일간×12월지(120셀), 서락오 정리본
  기준 **초안(reviewed:false, 전 항목 도메인 감수 필요)**. `scripts/build_johu_snapshot.py`
  validate(120셀 완전성·천간 유효성)→`compiled/johu_yongsin_v0.1.0.json` 스냅샷.
- `yongsin/johu_dict.py` 로더(스냅샷 우선→원본 폴백→부재 시 None·graceful) +
  `_johu_model` v2: 일간×월지 조후 천간 조회, 투간/지장간 존재 검사, 동일 오행 대체는
  "완전한 대체 아님(壬≠癸)" 주석. 극단 한열월(亥子丑·巳午未) 한정 결핍 가산
  (+0.15 최우선 천간 부재, +0.10 필요 오행 <5%). 비극단월도 후보 제공(conf 0.35).
  사전 부재 시 레거시(한습→火/조열→水) 폴백. 용신 operability 산정을 johu 선택
  케이스로 확장(조후 필요신 무근 감점의 작동성 계층 보존).
- **1965-05-15 이상형 도달**: selected=johu(궁통보감), 용=水·희=金(생용신 순환) —
  감수 yaml(climate_dryness_correction·水/金)과 일치. 회귀 테스트 갱신.
- **재스캔 파급: 24/672(3.6%)** — 대부분 극단월(5·6·7·11·12월) 조후 결핍 명식의 johu
  전환(水/金 방향). 주의 케이스: 사전 1순위가 한난 오행이 아닌 셀(亥월 辛→壬, 亥월
  戊→甲 등)은 레거시 조후(火)와 다른 용신 산출 — **사전 감수 시 함께 검토 필요**.
  픽스처 1건 교정(test_yongsin_operability no_transmit 격리 — 子월 甲 명식에 丁 투간
  추가로 조후 가산 개입 제거, 목적 보존).
- 검증: 전체 pytest 통과(실패 0)·ruff clean·mypy 244파일 clean·validate_dictionaries
  78파일 통과·FE vitest 36+tsc+build 통과.
- **후속(감수 대기)**: ①조후 사전 120셀 도메인 감수(reviewed:false→true) ②재스캔 24건
  중 비한난 1순위 셀 유형 확인 ③동점 희신 의미론적 타이브레이크.

### 조후 감수 확정 반영 — 사전 v0.2.0 + 기후 축 + 의미론 타이브레이크 (2026-07-13, 데굴님 최종 승인안)

감수 순서 ①사전 확정 → ②재스캔 예외 검증 → ③동점 타이브레이크 적용.

- **① 사전 v0.2.0 (reviewed:true, canonical need 한정)**: 셀 구조를
  `primary/secondary/avoid/climate_axis`로 분리(120셀). reviewed:true 의미는
  "canonical climate need 검토 완료"로 top-level note 에 명문화 — 최종 용신 확정·
  작동성·타 축 우선·시지 반영을 뜻하지 않음. avoid 는 고전 명시분만(삼춘 丙火 癸,
  3셀) — 증분 감수. climate_axis enum = cold/heat/dry/damp/mixed/neutral.
  build_johu_snapshot v2 검증(필드·enum·120셀) → compiled v0.2.0(v0.1.0 초안 삭제).
- **② 기후 축 판정 + 가산 정밀화**: `_climate_axes` — temperature/moisture 2축
  severity(±40=severe, ±20=축 성립, 분포+열한지지·조습토 가중). emergency 가산은
  **severe 축을 직접 교정하는 천간(cold→火·heat→水·dry→水·damp→火, 셀 내 탐색)이
  부재할 때만**(+0.15/+0.10) — 억부·매개·구조 목적 천간(亥월 辛→壬 등)은 가산 금지,
  base conf 의 climate_helper 로만 제시. 교정 오행이 반대 severe 축을 악화하면 승격
  억제(5단계). avoid 천간 투간 시 주석. 불변식 유지: 무근·전무 → operability 하락
  ≠ canonical_need 삭제(1965 회귀 고정).
- **③ 동점 희신 의미론 타이브레이크**: `_semantic_tiebreak_key` — dominant_need(기후
  축 직접 교정) > 주 병 직접 극 > 生용신 > 조후 악화 없음 > 용신 설기 흐름 > 통근 >
  결정적 오행 순서. **동점 후보만** 정렬(비동점 byte 불변), 점수·confidence·역할
  불변, `tiebreak_reason` warning 기록. 전역 고정 역할 순위 없음(극조열=climate_helper
  우선, 통관=mediator 우선은 ①번 키가 자연 결정). 1953-01-15 실측: 火/木 동점 →
  火 선택("dominant_need 일치 — 丑월 한축 교정") 기록.
- **골든 회귀 3종 고정**: 1965 johu 주모델 水/金 유지(emergency), 1959-11 비조후
  1순위(亥월 辛→壬) 무가산 + 억부 최종, 1953 타이브레이크 火 + 사유 기록.
- **재스캔(672)**: P4 초안 대비 9건 정밀화(억부성 승격 4건 취소 — 1961-12·1969-07·
  1972-07·2003-05 억부/관성 복귀 ✓). 원 베이스 대비 최종 잔여 **25건** — trace 전수
  생성(scratchpad p4_trace_report.json): climate_emergency_promoted 16(전원 severe:
  heat 15·dry 1 — dry_first 유형 실존), canonical_helper_won 5(비 severe johu-선택
  명식의 원소가 궁통보감 정론으로 교체: 亥월 戊→甲, 亥월 壬→戊, 未월 庚→丁),
  dictionary_reinforced 4(사전이 타 축 후보를 보강 — 1994-07 未월 壬→辛이 동률
  disease 승자 교체 포함). 극신약 4건은 역할 동일(水/金)·모델 라벨만 교체.
- 검증: 전체 pytest 통과(실패 0)·ruff clean·mypy 244파일 clean·validate_dictionaries
  통과. FE 무변경.
- **후속**: canonical_helper_won 5건의 원소 교체(궁통보감 정론이나 레거시 조후 火와
  상이)는 실사용 리포트에서 재확인 권장. avoid 천간 증분 감수. 조습 우선형
  (dry_first/damp_first) 라벨의 LLM 입력 노출은 별도 결정.

### 시점 정합 P0~P5 — 다중 연도·부정 파싱 + 배제 스코프 + 2단계 커밋 (2026-07-14, 데굴님 설계 확정)

실측 결함(아들 학업 스레드 3턴): "2026년 27년은 초딩때라 의미없고 2033년 시험운
합격운이 중요해"에서 time_parser C6이 **문장 첫 4자리 연도(2026)만** 선택
(time_parser.py:367 `re.search`) → 배제 대상이 스레드 시점으로 저장 → 후속 "그래서
원하는 대학에 붙는다는거야?"가 오염된 2026을 정상 승계해 丙午년 월운을 통째 재서술.
2차 결함 = 파서 상태(2026)와 LLM 답변 중심(2033)의 불일치를 감지 없이 커밋.

- **P0(추적)**: ParsedMessage.trace — extracted_times/resolved_target/own_time/
  inherited_time/active_exclusions/dialogue_act. chat 멀티턴 경로에서 turn_trace
  debug 로그. 실패 전사 3턴 E2E 픽스처 고정.
- **P1(typed time constraints)**: `extract_time_constraints` — 연도 언급 전수 추출
  (4자리+체인 축약 '27년'+올해/내년, '년생' 제외) → 인접 그룹핑 → 술어 창 분석 →
  역할 분류(target/excluded/comparison/correction/hypothetical/mention). 우선순위
  = 정정 > 요청 대상 > 비교 스팬 > 단일 언급, **배제는 절대 승격 금지**. 같은 연도
  배제+긍정 공존 시 긍정 승리(재요청). `parse_time_with_constraints`가 연/월 단위
  결과만 재조준(나이·구간묶음·데드라인·앵커 불변 — 회귀 0). 골든: A 말고 B/A가
  아니라 B/A는 됐고 B/A까지는 아니고 B쯤/비교 스팬/전부 배제→None.
- **P2(스코프 배제 상태)**: ConversationState.time_exclusions(start/end/scope/
  source_turn/reason) — current_turn|current_topic|thread 스코프. 병합 규칙:
  주제 전환(NEW) 시 topic 만료·명시적 재요청 시 해제·배제는 target 승격 금지.
  시점 승계 가드: 직전 시점이 배제 창과 겹치면 승계 차단. chat 불변식: 배제 창이
  엔진 창에 진입하면(임베딩 보강 합성 등) 시점 미확정으로 리셋 + [시점 제약]
  구조화 지시문(확정 시점+배제 기간+서술 금지). active_time_meta(P7 lite) =
  value/source_turn/resolution_type(explicit>inherited)/confidence.
- **P3(2단계 커밋)**: `_time_commit_guard` — 답변 중심 연도(최빈 20NN, ≥2회)가
  엔진 창 밖이거나 배제 연도면 시점 슬롯 커밋을 직전 정상 상태로 되돌림(warning
  로그). 파서 오독이 다음 턴으로 전파되지 않는 구조적 차단.
- **P4(결론 요구형)**: `_CONCLUSION_SEEK_RE` — "그래서 ~라는거야/결론이 뭐야"류를
  dialogue_act=conclusion_summary로(같은 도메인 후속 한정). 지시문 계약: 새 월별
  분석 금지, 직전 창 기준 ①1문장 결론 ②확실성(단정 불가) ③근거 2~3 ④조건.
  당락 확정 금지(원칙 8) 유지.
- **P5(연령 정합)**: `_minor_lifestage_directive_text` — **분석 대상 연도의 만 나이
  근사**(목표연도-출생연도, 컷오프 >19 — 19는 수능 해 고3 가능)로 미성년이면 성인
  사건 표현 변환(계약·채용→선발·등록·과정 진입) + 명백 불가 사건 서술 금지.
  점수·판정 불변(서술 계층 전용). 억제가 아닌 적합도 조정(청소년 자격시험 유효).
- 테스트 3계층(tests/unit/test_time_constraints.py, 17종): ①파서 골든 ②상태 병합
  (누적/승계 가드/재요청 해제/주제 전환 만료) ③E2E 실패 전사 재현 + 커밋 가드 +
  연령 지시문. 스키마 신설: TimeConstraintRole/TimeConstraintItem(intent),
  TimeExclusion(conversation), IntentJson.time_exclusions·dialogue_act.
- 검증: 전체 pytest 통과(실패 0·기존 스킵만)·ruff clean·mypy 244파일 clean.
  FE 무변경(구 스레드 상태는 pydantic 기본값으로 하위호환).
- **후속(선택)**: ①배제 창의 엔진 후보 산출 자체 제외(현재는 창 재설정+서술
  차단까지) ②conclusion_summary의 LLM 경량 폴백(룰 미스 변형 표현) ③trace의
  운영 대시보드 노출. → ①②는 아래에서 즉시 구현(데굴님 지시), ③만 잔여.

### 시점 정합 후속①② — 배제 후보 제거 + 결론 요구형 폴백 (2026-07-14, 데굴님 착수 지시)

- **①(배제 창 후보 제거)**: `_drop_excluded_candidates` — 배제 기간(연 접두 판정,
  'YYYY'/'YYYY-MM')에 속한 이벤트 후보를 산출 단계에서 제거해 LLM 입력에서 근거
  자체를 소거. 의도 필터의 fallback-원본-유지와 달리 **빈 결과 허용**(배제는 사용자
  지시이지 보정이 아님). horizon/vague_future/기본 경로 공통 적용.
- **②(결론 요구형 폴백, 2계층)**: ⑴룰 확장 — `_CONCLUSION_SEEK_RE`에 '~다는
  소리야/뜻이야/말이야' 변형 추가('무슨 뜻이야' 용어 질문은 (다는|라는) 선행 조건으로
  배제). ⑵임베딩 폴백 — `dialogue_act_similarity.py`(intent_onnx 재사용, 자립 복제
  관례) + `dialogue_act_seed_corpus.json`(conclusion_summary + distractor 3라벨).
  게이트 score≥0.60·margin≥0.05, 1차 안전은 '후속 턴+같은 도메인+룰 미확정' 구성
  게이트. 실측: 양성 5/6 통과·distractor 오탐 0.
- **부수 수정 2건(실측 발견)**: ⑴결론 요구형이 같은 도메인 단어('합격')를 포함하면
  link=NEW로 끊기던 결함 — link_question에 결론 요구형 후속 규칙 추가(도메인 동일·
  미검출 한정). ⑵'~라는 소리야 뭐야'의 '뭐야'가 TERMINOLOGY_EDUCATION(policy)으로
  오분류돼 canned 응답으로 빠지던 결함 — dialogue_act 지정 시 policy query_type을
  직전 분석 주제로 복원.
- 테스트 3종 추가(총 20): 배제 후보 제거(빈 결과 포함)·소리/뜻 변형 룰·임베딩
  게이트(distractor 무오탐, ONNX 부재 시 skip).
- 검증: 전체 pytest 통과(실패 0)·ruff clean·mypy 245파일 clean·validate_dictionaries
  79파일 통과.

### 추첨·선발·배치(selection_allocation) 범용 코어 + 군입대 어댑터 (2026-07-14, 데굴님 설계 확정)

"군입대 추첨 당첨"을 사주가 직접 맞히는 단일 사건으로 두지 않는다 — **당첨되는
운과 원하는 조건에 배치되는 운은 다른 사건**이며, 외부 무작위성이 큰 추첨은 표현을
제한해야 한다. 군입대 전용이 아니라 범용 코어 + 도메인 어댑터로 구현(shadow-first,
검증 전 설명 보조 전용 — 기존 사건 점수·판정·실행 경로 불변).

- **스키마(shared_types/selection_allocation.py)**: 9단계(SelectionStage: 기회→지원→
  자격→선발→배정→희망일치→수락→실행→적응), 선발 방식 7종·배치 방식 8종, 결과
  **상태 머신 18상태**(SELECTION_STATE_TRANSITIONS — 대기→추가선발, 선발→자격재검토
  취소, 차선 배정 수락 등 현실 서사 지원, 이진 당첨값 금지), StageScores(단계별
  0~100 분리), ExternalUncertainty·ResponsePolicy(단정 금지·confidence cap·대기
  시나리오), 도메인 어댑터 레지스트리 8종(military_service·housing_subscription·
  school_assignment·dormitory·public_program·workplace·event_ticketing·generic —
  ticketing은 multi_stage=False로 selection 종료형).
- **엔진(saju_engines/selection_allocation.py)**: DirectionFacts(능동 제안 레이어와
  공유) → **기능 신호 8종 추상화**(institution←관성/qualification←인성/application←
  식상/competition←비겁/benefit·matching←재성/transition←충+운유입/stability←마찰
  역수+인성). 강도 = 작동0.65/존재0.4/부재0.2 + 용기신 보정 + 운유입/과다/부족 보정.
  단계 점수 = 단계별 가중 결합 — **경쟁 신호는 반전 결합**(비겁≠탈락, 용·희신이면
  감점 완화), merit형(score_ranked/hybrid)은 selection 가중을 제출·자격 중심으로
  교체. **무작위성 캡**: lottery=confidence low·선발≤70·일치≤65, weighted_lottery
  ≤72/68, hybrid=medium≤80, score_ranked=≤88. 충·이동 신호는 당첨이 아니라
  execution 단계에만 연결(설계 §2).
- **파싱(selection_intent.py)**: 도메인 7종+generic 감지, 단계 분리 매핑("지원해도
  될까"→application, "붙을까"→selection, "원하는 날짜"→preference_match, "대기번호"
  →waitlist, "적응"→adaptation). 가드: 로또·복권은 횡재 정책(원칙 8) 관할로 비개입,
  '합격' 단독(시험)은 기존 분류 관할. **멀티턴 승계**: 도메인 단어 없는 후속("그래서
  원하는 날짜로 갈 수 있다는 거야?")은 강한 단계 신호 + 직전 답변의 선발 맥락일
  때만 도메인 승계 — 결론 요약 모드와 결합해 preference_match만 잇는다(설계 §9).
- **chat 배선**: 감지 시 `[선발·배치 풀이]` 후행 지시문 — 단계 점수 8종 + 신호
  근거(도메인 언어 번역) + 표현 규칙(당첨 단정·확률% 금지, 이동 신호=실행 전용,
  경쟁=환경 강도, 추첨성 명시, 대기 시나리오) + 답변 형식(결론→유리→변수→전개).
  dry_run 실측: 군입대 질문에 weighted_lottery·초점 '희망 조건 일치' 블록 정상 주입.
- 테스트 11종(test_selection_allocation.py): 상태 머신 흐름/차단, 신호-사실 반영,
  충→execution 연결, 경쟁 반전·완화, merit 가중, lottery 캡, 파싱 매핑/가드/승계,
  실차트 통합, LLM 블록 정책 문구, 청약 어댑터 범용성.
- 검증: 전체 pytest 통과(실패 0)·ruff clean·mypy 248파일 clean.
- **후속**: ①실사례 골든(지원/선발/희망일치/실입영 각각) 축적 후 가중 캘리브레이션
  ②가중 상수의 사전(JSON) 외부화 ③EventKey 정식 편입 + 사전계산(T0~T2) 통합
  ④객관 경쟁률(objective_odds) 입력 채널(사주 해석과 분리 표기) ⑤리포트 상품 연동.
  → ②③(시기 축)④는 아래에서 즉시 구현(데굴님 지시), ①은 데이터 축적 대기.

### 선발·배치 잔여 ②③④ 일괄 구현 (2026-07-14, 데굴님 착수 지시 — ① 제외)

- **②(가중 사전 외부화)**: `dictionaries/selection_allocation_weights.json`(v0.1.0,
  reviewed:false — 코드 기본값과 동일한 캘리브레이션 기준선) +
  `scripts/build_selection_allocation_snapshot.py`(단계 가중 8종 완전성·합 1.0·신호
  키·모드 가드 7종·캡 범위·pydantic 스키마 검증) → `compiled/…_v0.1.0.json`.
  엔진 로더 = 스냅샷 우선→원본 폴백→코드 기본값 graceful(원칙 5). 캘리브레이션(①)의
  조정 지점이 이 사전으로 일원화됨. `SelectionWeightsConfig`/`ModeGuard` 스키마 신설.
- **③(시기 축 — 사전계산 통합의 경량 선행)**: `rank_timing_windows` — 향후 12개월
  월운(LuckPillar 십성)의 초점 단계 신호 군 유입 스윕. 관성·인성 유입 달 가산,
  비겁 유입 감산, boost>0만 상위 3창. 지시문에 "상대적으로 유리한 창(결과 보장
  아님)"으로 주입 — response_policy.relative_timing_comparison 허용 범위 내.
  **EventKey 정식 편입은 보류**: EventKeyV2는 2026-06-13 확정 21키 하드 스위치
  (canonical)라 스코어링 모델·금기룰·그래프 동반 설계 없이 키만 추가하면 반쪽
  통합(후보 없는 event_key)이 됨 — 골든 검증(①)과 함께 21키 개편안으로 재상정.
- **④(객관 경쟁률 채널)**: `ObjectiveOdds` 스키마 + `parse_objective_odds` —
  'N대 1'/'A명 중 B명'/'확률 N%' 3형 파싱, 수치 없으면 미생성(임의 확률 생성 금지).
  reading에 실려 지시문이 분리 표기 강제("객관 확률은 이 정도, 사주상 흐름은 이렇다"
  — 혼합 보정 확률 금지). E2E 실측: "경쟁률 3대 1 … 붙을까?" → 약 33% 분리 라인 +
  유리 창 3개 정상 주입.
- **⑤(리포트 연동)**: 방안 ⑵(기존 topic 섹션 조건부 보조 블록 — 목차 불변) 데굴님
  확정 → 즉시 구현. `selection_report_lines`(엔진) — 기관(관성)·자격(인성) 신호
  **notable(≥0.65) 게이트**: 미달이면 빈 목록=본문 무언급(외적 인상 신호 관행),
  노출돼도 "본문 맥락과 무관하면 통째 생략" 지침 동봉(추첨류 강제 삽입 방지).
  부착 지점: RL-04(이사→청약·공공주택)·J-04(직업→근무지·부서 배치)·C-04+education
  topic(학교·기숙사 배정). `_ReportData.selection_block` + `_SELECTION_AUX_SECTIONS`.
  **EventKey 편입은 ①(골든 캘리브레이션)과 함께 21키 개편안으로 재상정** — 데굴님
  확정(2026-07-14).
- 테스트 3종 추가(총 14): 사전-스냅샷-기본값 동등성+빌드 검증, 시기 스윕 순위
  (관성월>비겁월·초점별 창 교체), 확률 파싱 3형+분리 표기 강제.
- 검증: 전체 pytest 통과(실패 0)·ruff clean·mypy 248파일 clean·validate_dictionaries
  80파일 통과.

### 총운형 다변화 선별 — 의미 클러스터링 + 품질 게이트 (2026-07-14, 데굴님 감수 확정)

실측 결함(데굴님 본인 사주): "앞으로 1년 주요 이벤트"(FORTUNE_OVERVIEW·general·12개월)
답변이 직업 도메인으로만 쏠림. 원인 = 총운 질문에도 단일 도메인 질문과 동일한 순수
점수순 Top-5(reduce_candidates) 적용 — 강한 십성 유입 해에 한 사건이 기간만 바꿔
5슬롯 독점(재현: 타 명식에서 재물 변화 ×5). 감수 확정 설계: **균등 배분(라운드로빈)이
아니라 중복 압축 후 유효 신호 범위 안에서 조망성 확보**.

- **P1-a(의미 클러스터링)**: `reduce_overview_candidates` — 클러스터 키 =
  event_key + 길흉 방향(quality 길·흉군, 폴백 favorability 부호) + 지배 신호 계열
  (|weight| 최대 signal.type). 반대 방향(재물 기회 vs 손실)·원인 다른 독립 피크는
  분리, 기간 반복은 대표(정렬 최상위)+supporting_periods 집계 —
  `LlmEventCandidate.recurrence_note`("같은 계열 신호가 …에도 나타남, 총 N회")로
  직렬화해 '반복적으로 강한 신호' 정보 보존.
- **P1-b(품질 게이트 다양화)**: ①life_fit 계층 불변(reduce_candidates와 동일 정렬키)
  ②전체 최고 1개 ③미포함 도메인 후보는 게이트 통과 시에만(절대 최소 55 + 최고점−30
  이내 + life_fit 격차 ≤0.15) ④충원도 게이트 통과 클러스터만(약한 후보 강제 충원
  금지 — Top 3~5는 목표 범위) ⑤동일 도메인 최대 2개는 미포함 유효 도메인이 남아
  있을 때만(조건부 — 압도 도메인 집중 보존). 도메인 판정은 EVENT_DOMAIN(primary).
- **활성 게이트**: general 전체가 아니라 명시 조건 — FORTUNE_OVERVIEW + 주도메인
  general + 부도메인·이벤트 없음 + **단일 최대 사건 요구 제외**("가장 중요한 일
  하나"류 — 다양화 대신 최고점 중심). 특정 도메인 질문은 기존 로직 그대로(회귀 0).
- **P2(조망 서술 계약)**: 후보가 존재하는 영역만 조망(5영역 강제 채움 환각 방지),
  같은 영역 집중은 반복 나열 대신 통합+집중 명시, 반복 신호는 대표·재등장 시기를
  한 흐름으로, **미선정 영역은 '신호 없음' 단정 금지·언급 생략**(Top-N만으로는
  후보군 부재/임계 미달/병합을 구분 불가 — overview_domain_status 메타는 후속).
- 실측 재확인: 동일 명식 동일 질문 — 재물×5 → 재물(반복 노트)+창작+결혼+이사+건강
  5영역 조망 + 조망 지시문 주입.
- 회귀 테스트 8종(test_overview_diversity.py, 감수 케이스 전수): 월별 반복 집계 /
  다도메인 커버리지 / 단일 도메인 압도 보존(약한 후보 미포함) / 반대 방향 분리 /
  독립 원인 분리 / life_fit 계층 불변 / 활성 게이트(도메인·분석형·단일최대 제외) /
  강제 충원 금지.
- 검증: 전체 pytest 통과(실패 0)·ruff clean·mypy 248파일 clean.
- **후속(선택)**: ①overview_domain_status 메타(no_candidate/below_threshold 구분
  언급) ②event_family 계층 도입(유사 사건군 통합 — 현재는 event_key+방향+원인 근사)
  ③단일최대(single_major_event) 응답 계약 별도 정의.

### 총운 다변화 2차 결함 — co-top 우선 패스 (2026-07-14, 데굴님 실사용 재지적)

1차 배포 후에도 총운이 직업 위주 + **결혼 신호 98점 누락**(후속 "애정운은 없어?"
에서야 노출). 합성 재현으로 메커니즘 확정: 커버리지 패스가 top_n까지 슬롯을 무제한
소모 → 이동 82·건강 75점(게이트 통과)이 결혼 98·이직 99점을 밀어냄 — '유효 도메인
1개씩'이 '주요 이벤트'보다 우선돼 버린 설계 결함.

- **co-top 패스 신설**: 최고점 −10(OVERVIEW_CO_TOP_WINDOW) 이내 클러스터는 도메인
  커버리지보다 먼저 선정(그 자체가 주요 이벤트). 게이트·조건부 도메인 캡(2)은 동일
  적용 — 단일 도메인 90점대 나열로의 회귀 방지. 정렬이 life_fit 우선(점수 비단조)
  이므로 창 밖은 break가 아니라 continue. 수정 후 동일 시나리오:
  [job 100, career_change 99, 관계 변화 98, **결혼 신호 98**, 재물 96] — 82·75 탈락.
- **서술 계약 강화**: 선정 후보는 각각 최소 1회 직접 서술 + 최고 강도 후보는 영역
  무관 서두 비중 + 월별 용신·기신 흐름 서술이 후보 조망을 대체(직업 쏠림)하지 못하게
  명시(1차에서 후보가 5영역이어도 직업 서사가 지배하던 잔여 결함).
- 회귀 테스트 case9(co-top 밀림 방지 — 98 포함·75 배제·career 캡 2) 추가, 기존
  8케이스 전부 유지 통과.
- 검증: 전체 pytest 통과(실패 0)·ruff clean·mypy 248파일 clean.

### 총운 다변화 3차 — 선정 제외 강신호 메타 + 선별 trace (2026-07-14, 데굴님 재검 결과)

co-top 수정 후에도 데굴님 실계정 총운에서 결혼 신호 98 여전히 부재(반복 노트
"8회 이상"은 서술됨 = 새 코드 반영 확인). 무개인화 합성 명식으로는 결혼 후보가
정상 선정됨을 확인 → 소거법상 잔여 원인 = **개인화 life_fit 계층**(재직 IT 프로필로
직업 후보 fit 상승 → `top_fit−0.15` 게이트가 결혼(낮은 fit)을 전 패스에서 제외).
이는 감수 규칙 ④(life_fit 계층 불변)의 의도된 강등이나, 98점 강신호가 총운에서
**완전 침묵**하는 것은 별개 결함 — 감수 회신의 not_selected_due_to_limit 방식 구현.

- **선정 제외 강신호 메타**: reduce_overview_candidates가 (선정, 반복노트,
  **제외 메타**) 3-튜플 반환 — 근-최고점(co-top 창)인데 미선정된 클러스터를 사유
  (개인화 적합도 후순위 / 조망 슬롯 제한)와 함께 한 줄로.
  `LlmInput.overview_dropped_notables` 신설, 직렬화 시 [선정 제외 강신호] 블록 —
  "한 문장으로 존재만 언급(승격 금지), '신호 없음' 단정 금지" 계약. 낮은 점수
  탈락은 메타 미포함(노이즈 방지).
- **선별 trace**: overview_selection INFO 로그(선정 키·기간·점수·life_fit + 제외
  사유) — 라이브 재질문 시 dev 서버 로그로 원인 즉시 관측 가능.
- 회귀 case10(life_fit 강등 메타·슬롯 제한 메타·저점수 비포함) 추가 — 총 10케이스.
- 검증: 전체 pytest 통과(실패 0)·ruff clean·mypy 248파일 clean.
- **미결(데굴님 확인 대기)**: 개인화 fit 게이트가 원인인지 라이브 재질문 1회로 trace
  확정 필요. 만약 fit 강등이 맞다면 — co-top 한정 fit 게이트 면제(강신호는 fit
  무관 정식 선정) vs 현행(메타 한 줄 언급) 중 정책 결정 여지.

### 총운 다변화 4차 — 공동 평가·메타 창 확대·수치 환각 가드·관측성 (2026-07-14, 데굴님 확정)

3차 반영 후 재질문 공동 평가: ✅다도메인 조망(직업+관계 문단+말미 메타)·반복 통합·
집중 명시·제외 강신호 한 문장 언급 전부 계약대로 작동. ⚠️결혼 신호는 선정·제외 메타
어디에도 없음 → **이전 "98점"은 LLM이 지어낸 수치일 개연성**(엔진은 점수 숫자를 LLM에
비노출 — "매우 강합니다" 표현만 전달). 실점수가 85 안팎이면 관계 질문에선 최상위로
노출되고 총운에선 co-top 창(−10) 밖 — 모든 관찰 정합.

- **① 제외 메타 창 확대**: co-top(−10) → 상대 −30(커버리지 게이트와 동일) + 절대
  하한 70('가능성이 높습니다' 등급) + 캡 3건(정렬순) — 85점급 강신호도 총운 말미
  한 문장 보장, 노이즈·나열 폭주 방지.
- **② 수치 환각 가드**: 이벤트 후보 헤더에 "점수·백분율 수치 미제공 — '98점'류
  지어내기 금지" 명시 + _CHAT_SCOPE_DIRECTIVE에 일반 조항(입력에 없는 점수·확률·
  백분율 발화 금지, 사용자가 점수 환산을 명시 요청한 경우만 '감각적 어림 환산' 단서
  달고 허용 — 100점 환산 요청 UX 보존).
- **③ 관측성**: uvicorn 기본 로깅이 앱 로거 INFO를 침묵시키던 문제 — main.py에서
  saju_api·saju_engines 네임스페이스에만 StreamHandler 부착(서드파티 소음 없음,
  중복 부착 가드). overview_selection trace가 dev 콘솔에 노출됨(실측 확인).
- 테스트: case10 확장(85점급 메타 포함·캡 3건·70 미만 생략) — 총 10케이스 유지.
- 검증: 전체 pytest 통과(실패 0)·ruff clean·mypy 248파일 clean.

### 총운 다변화 5차 — 점수 누출 차단·표시 순서·지시문 충돌 해소 (2026-07-14, LLM 입력 전문 공동 검토)

데굴님이 LLM 입력 전문을 공유 — 4차 진단("98점=환각")이 **오진**으로 판명:
`_selection_reason`(context_reducer.py:944)이 `f"{event_key} {score}점"`으로 **영문
내부 키+원점수를 간지달력 세운 선별 사유에 노출**("선별: wealth_change 98점") —
관계운 답변의 '98점'은 여기서 인용된 것(점수 비노출·내부 키 비노출 원칙 위반 소스).
추가 발견 2건: ①후보 표시 순서가 life_fit순이라 fit 부스트 받은 최약 직업 후보
("흐름" 등급)가 목록 리드 — life_fit이 데굴님 계정에서 실제 작동 중임을 확인
②[유력 달 종합]의 "누락 금지" 강제가 총운 조망 지침과 충돌 — LLM이 달 순위(직업
쏠림)를 따라가 관계 변화(매우 강·반복 11회)를 직접 서술하지 않음.

- **①선별 사유 정화**: 한글 라벨 + tone 표현("재물 변화 — 신호가 매우 강합니다"),
  점수·영문 키 제거. E2E 검증: 프롬프트 내 `\d+점`·`선별: [a-z_]+` 잔존 0
  (가드 지시문의 자기 인용 제외).
- **②총운 표시 순서 = 강도(점수) 내림차순**: 선정·life_fit 계층 불변, 직렬화
  순서만 — 최강 신호가 후보 목록 리드를 잡도록 구조로 보장.
- **③지시문 우선순위**: overview_mode 플래그(LlmInput 신설)로 [유력 달 종합]
  헤더 분기 — 총운에선 "이 순위는 시기 짚기 참고, 서술 골격은 [이벤트 후보]".
  비총운 질문은 기존 헤더 그대로.
- 회귀 case11(선별 사유 무누출)·case12(표시 순서) 추가 — 총 12케이스.
- 검증: 전체 pytest 통과(실패 0)·ruff clean·mypy 248파일 clean.

### 총운 다변화 6차 — 무비용 서술 유도(재생성 금지 확정) (2026-07-14, 데굴님 피드백)

5차 반영 후에도 서술 위반 잔존: 표시 1위(관계 변화 @2026-12·갈등·불리)가 한 구절로
뭉개지고, 관계 기회(@2026-07·반복 11회)는 문장 단위 미서술, ⚠우호 단정 금지가 붙은
7월을 "다소 긍정적"으로 반전. 사후 검증+재생성안은 **데굴님 반대(비용 증가)로 폐기**
— 추가 LLM 호출 0의 입력 구조 수단으로 전환.

- **①후보 블록 후치(총운 한정)**: [이벤트 후보]·[선정 제외 강신호]를 [월별 요약]·
  [유력 달 종합] 뒤(최종 지시문 인접)로 이동 — 마지막 데이터 블록이 서술을 지배하는
  경향을 역이용(월별 표의 직업 신호 밀집이 후보 조망을 덮던 쏠림 완화). 비총운
  질문은 기존 순서 그대로(E2E 검증: 총운=월별<유력달<후보, 도메인 질문=후보<월별).
- **②순번 체크리스트**: 총운 후보에 "후보 N/5 ·" 순번 + 목록 끝 서술 체크리스트
  (각 후보 시기와 함께 최소 한 문장, 갈등·손실·압박·'불리' 반전/생략 금지, ⚠ 시기
  '긍정적' 요약 금지).
- **③커버리지 계측(관측 전용)**: `_overview_missed_candidates` — 문장 단위로
  '라벨 토큰+기간 마커' 동시 출현 판정(전역 검사는 '관계'·'7월'이 딴 문장에 있어도
  통과하는 오탐). 누락을 INFO 로그로만 계측 — **재생성·재호출 없음**. ①②의 효과를
  라이브에서 실측하는 용도.
- 회귀 case13(문장 단위 커버리지 판정) 추가 — 총 13케이스.
- 검증: 전체 pytest 통과(실패 0)·ruff clean·mypy 248파일 clean.
- **남은 관찰**: ①②로도 위반이 지속되면(coverage_miss 로그로 확인) 남는 옵션은
  모델 교체 실험 또는 총운 전용 시스템 프롬프트 — 데굴님 결정 사항.

## 위험 탐지 엔진 R0 — 원자 위험 후보 생성 기반 (2026-07-15, 데굴님 조건부 승인 반영)

**배경**: 기존 서비스가 좋은 시기만 찾고 어려운 시기·위험 이벤트를 경고하지 못함
(불리 신호가 감점·quality flip·favorability 조정으로만 소비 — 별도 위험 후보 없음,
Top-N에서 긍정 후보에 밀림). 데굴님이 기회/위험/회복 독립 산출 스펙 제공 → 조건부
승인 4조건(①reducer 이전 raw signal 입력 ②RiskCandidate/RiskEpisode 분리 ③구조화
근거 provenance ④protection/recovery 분리)을 R0에 전부 반영. 규격은
`doc/v2_2/RISK_ENGINE.md`로 고정.

- **R0-A 규격**: `doc/v2_2/RISK_ENGINE.md` — kind 3분류(pressure/vulnerability/
  incident_risk), risk_level≠confidence, protection≠recovery, critical 필수 조건
  (exposure CONFIRMED + 독립 계층 2개 등), exposure 미입력 숫자 대체 금지(UNKNOWN=
  warning 상한), R2 병합 키(risk_id+cause_signature+domain+exposure_target), 질문
  유형별 위험 노출 min/max 정책, R3 우선 서술 계약. **토큰 일괄 30k 상향 보류** —
  R3에서 위험 블록 p50/p95 실측 후 risk_context_reserve + 호출별 개별 상향.
- **R0-B 타입**: `shared_types/risk_engine.py` — RiskEngineMode(off/shadow/expose)/
  RiskDomain(7종)/RiskKind/EvidenceRole(trigger·amplifier·mitigator·blocker)/
  ExposureStatus/RiskLevel/RiskEvidence(evidence_id=원인 사실 서명 기반 중복 방지)/
  RiskScoreComponents(6축 0~1, R1)/RiskCandidate(원자·단일 period_key)/RiskEpisode
  (R2 병합, 타입만)/ProtectiveFactor/RecoveryWindow + independent_source_count·
  dedupe_evidence 헬퍼.
- **R0-C 사전**: `dictionaries/risks/{finance,career,contract_legal,health_safety,
  relationship,relocation,selection}.json` 7종 44항목 전부 reviewed:false 초안(감수
  대기). 기존 SignalSpec 재사용 안 함 — RiskRuleSpec(AND 조건: tenGod/tenGodGroup/
  relation+palace/polarityRoleIn/voidActive/twelveStageIn) + trigger/amplifier/
  mitigator/blocker 분리 + minimumEvidence(incident_risk는 독립 출처 ≥2 lint 강제 —
  신호 1개 범람 방지). risk_id는 EventKeyV2와 별도 네임스페이스(FIN_/CAR_/LEG_/HLT_/
  REL_/MOV_/SEL_ 접두 lint). `dictionaries.py`에 RiskMappingFile 스키마·schema_for
  등록·`_lint_risk_mapping` 추가(검사 사전 87개 통과).
- **R0-D 엔진**: `saju_engines/risk_engine.py` — RawPeriodFacts(원시 신호 스냅샷:
  층위별 십성·관계 발동·공망·시점 극성(化/制 반영)·12운성) → 룰 매칭 → provenance
  수집(dedupe) → minimum_evidence 게이트 → 원자 RiskCandidate. 점수·병합·노출 없음.
  blocker 근거는 후보 삭제 없이 보존(발현 제한 판정은 R1). `event_engine_v2.py`
  `_collect_risk_shadow`: 모디파이어 적용 전 재료로 스냅샷 구성, **긍정 후보 0건
  조기 반환보다 앞에서 수집**(위험 근거 소실 방지), 읽기 전용 — risk_shadow
  사이드채널(LLM 입력·리포트 미주입). 게이트 `risk_engine_config.RISK_ENGINE_MODE`
  기본 "off"(byte-identical, 호출 시점 로드 — 1줄 전환), risks/ 부재 시 graceful.
- **R0-E 검증**: unit 20건(무불리신호→0건, 압박만→pressure만, 단일 trigger 차단,
  독립 2출처 생성, mitigator 보존, 동일 원인 2룰=출처 1개, blocker 보존, exposure
  전달, 7도메인 대표 사건 parametrize, lint/스키마 거부) + regression 5건(OFF 기본
  무수집, SHADOW=OFF 긍정 출력 동일 직렬화, 원자 후보 R0 계약, config 1줄 전환,
  score_years 초기화). 검증: 전체 pytest 1788 passed·ruff clean·mypy packages 224
  파일 clean(전체 리포 잔존 오류는 tests/ 기존분, 신규 파일 0건).
- **다음**: 위험 사전 7종 감수(reviewed:false → 확정) → R1 점수 6축 → R2 병합·분리
  선별 → R3 답변 계약+토큰 실측 → R4 골든 세트 → R5 개인화.

### 위험 엔진 R0.5 — 사전 감수 인프라 + 밀도 기준선 (2026-07-15, 데굴님 감수 지시)

R0 커밋(fe939f8) 후 감수 지시 반영: 기신·공망·12운성은 원칙적으로 독립 사건 트리거가
아니라 증폭·취약 신호, incident_risk는 사건 형태(event_shape)+대상 활성(target_activation)
필수 그룹. R1은 계속 보류.

- **스키마**: RiskRuleSpec에 `group`(신호 역할 — 극성·공망·운성 단독 룰은 event_shape/
  target_activation 금지 스키마 강제) + `relationTargetTenGod(Group)`(무엇을 충·형했는가).
  RiskMinimumEvidence에 `requiredGroups`(약한 범용 신호 2개 ≠ 사건형태+대상활성 구분).
  RiskItem에 `riskFamily`/`relatedDomains`(도메인 교차 중복 통합), `allowedClaimScope`/
  `claimCeiling`(건강·법률 화이트리스트+표현 상한). lint: requiredGroups 충족 불가능
  항목 검출 + 감수 승격(reviewed:true) incident 게이트(필수 그룹·generic trigger 금지).
- **provenance**: RelationFact에 피자극 십성(target_ten_god) — event_engine_v2가 자극
  궁성의 천간/지지 본기 십성을 주입. 관계 서명에 피자극 십성 항상 포함(대상 조건
  유무로 서명이 갈라져 독립 출처가 부풀려지는 것 차단). 잔여 갭(R1): 원국 취약 구조·
  투간통근 작동성·구조 패턴.
- **적격 상태**: EligibilityStatus(matched/mitigated/blocked) + suppression_reasons —
  blocker는 기록 보존하되 활성 집계 제외 가능(불변식: recovery는 적격성·점수 불변).
- **밀도 리포트**: scripts/risk_shadow_density.py — 기준선 실측(1980 차트, 세운+월운
  22기간): 기간당 6.82후보, 활성 기간 81.8%, 충 1건→11개 risk_id 확산, vulnerability
  발동률 54.5% — 감수 필요성 실증(진단: 대상 무관 관계 trigger + 기신 독립 trigger).
- **감수 문서**: RISK_ENGINE.md §3-1 신호 역할 매트릭스(표 A)·§4-0 적격 불변식·§10-1
  R0.5 절차. doc/v2_2/RISK_DICTIONARY_REVIEW.md — 대표 7항목(도메인별 1건) 개정안 +
  잔여 37항목 일괄 규칙 + 밀도 목표(기간당 ≤3, 단일 원인 확산 ≤3) — **데굴님 확정 대기**.
- 테스트 +5(requiredGroups 게이트·대상 매칭·동일 충 서명 공유·극성 단독 event_shape
  거부·감수 승격 lint). 검증: pytest 1793 passed·ruff clean·mypy packages clean.
- **다음**: 표 A + 대표 7항목 확정(데굴님) → 44항목 전체 적용 → 밀도 재실측 → reviewed
  전환 → R1.

### 위험 엔진 R0.5 2차 — 감수 보완 6종 + 대표 7항목 실룰 + 코퍼스 밀도 (2026-07-15, 데굴님 감수 2차)

커밋 A(c4628e1, R0.5 인프라) 후 조건부 승인 보완 반영. 원칙: blocker≠반대 극성,
후보 생성 조건≠높은 경고 등급 조건, cap이 아니라 대표 후보 결정.

- **상태 4종**: EligibilityStatus = insufficient_evidence(룰 일부 매칭·계약 미충족 —
  observed와 활성 분리)/eligible/mitigated/blocked. 활성 판정 is_active() 단일 함수.
  matched는 룰 평가 결과로만.
- **증거 계약**: evidenceContract(anyOf allOfGroups + minIndependentCauses) — 신그룹
  targeted_event_shape(형태+대상이 한 사실, 관계+대상 스키마 강제, 형식적 중복 룰
  제거). 한 사실이 두 의미 충족해도 독립 원인 1개(등급은 R1에서 watch 상한).
- **kind별 승격 lint**: incident=(shape+activation)|targeted+generic 금지 /
  pressure=비generic 1+ / vulnerability=대상 활성·구조 약화 / 건강·법률 incident=
  claimCeiling+allowedClaimScope 필수(건강 conditional_warning 이하) / manifestation↔
  prohibitedClaims substring 충돌 검사.
- **blocker 3분리**: hard blocker(BLOCKED — 노출 DENIED/NOT_APPLICABLE 엔진 자동 처리,
  대상 부재)/mitigator(YONG_STRONG 강등)/claim ceiling(표현 제한, R3 강제).
- **특이도 억제**: specificityRank(구체3>일반2>취약1>압박0) + 동일 기간·family·원인
  원자(cause_atoms — 서명 & 분해) 공유 시 하위 후보를 suppressed_by_specificity로
  대표에 흡수(활성 제외·기록 보존). relatedDomains는 복제가 아니라 부착.
- **provenance**: RelationFact에 피자극 글자(target_letter) 추가 + relationTargetLetter
  룰 축. 매칭 우선순위(궁위·자리>글자>십성>십성군>일반) 규격화(RISK_ENGINE.md §3-2).
- **대표 7항목 실룰 반영**(reviewed:false 유지): FIN_UNEXPECTED_EXPENSE·CAR_ORG_CONFLICT·
  LEG_PENALTY_LIABILITY·HLT_CHRONIC_FLAREUP(가장 엄격: shape+activation AND 독립 2)·
  REL_PARTNER_READJUST(배우자궁만 — 배우자성은 R1 성별 축까지 미저작)·MOV_CONTRACT_FAIL
  (family housing_contract, related FIN/LEG)·SEL_UNWANTED_PLACEMENT. 기신·공망 trigger
  전량 amplifier 강등. riskFamily 저작(cashflow·health_condition·partner_relation 등).
- **밀도 리포트 2차**: 단계 분리(observed→eligible→active) + 10차트 코퍼스(시드 지역
  제약으로 서울/부산) + p50/p90·kind별·원인 확산. 실측: 활성 6.63/기간·incident
  3.12/기간·확산 max 12 — **경고 전부 미개정 37항목 기인**(개정 7항목은 FIN_UEX 27.3%
  등 목표 근접, 특이도 흡수·INSUFFICIENT 분리 작동 확인). 목표는 raw가 아니라
  active·family 기준으로 규격화(incident/기간 ≤1.5, family/기간 ≤3, 확산 ≤2).
- 테스트 44건(적대적 fixture 7종 추가: generic 기신만→incident 0, 동일 원인 중복
  INSUFFICIENT, blocker 동시 성립, 구체가 일반 흡수(FIN·REL), 노출 DENIED 차단,
  targeted 단독 계약, claim 정책 lint). 검증: pytest 1800 passed·ruff·mypy clean.
- **대기**: 표 A(+targeted_event_shape)·대표 7항목 실룰 데굴님 확정 → 커밋 B → 잔여
  37항목 일괄 적용(§2 규칙) → 재실측 → reviewed:true → R1.

### 위험 엔진 R0.5 3차 — 불변식 4종 고정 + 표 A·대표 7항목 확정 (2026-07-15, 데굴님 커밋 B 승인)

- **is_active = 구조적 활성 한정**: 사용자 노출 가능 의미 아님(문서·docstring 고정).
  R1 is_score_qualified / R3 is_exposable 별도 판정 예정. RISK_ENGINE_MODE는 유지(off).
- **targeted_event_shape 성립 조건 강화**(스키마 강제): 관계+십성(군) 대상만으로는
  불가 — ①궁위가 사건 형태 정의(배우자궁 충) 또는 ②사건 구조 십성 동반(겁재-재성
  경쟁이 재성을 직접 대상 등). '대상 특정 일반 관계'는 target_activation으로 저작.
  7항목 재구조화: FIN(targeted=+JIECAI 동반, 순수 재성 피격은 target_activation로
  강등 — 단독 생성 불가)·CAR(+SHANGGUAN)·LEG(+QISHA)·MOV/SEL(targeted 단독 경로
  제거, shape+activation AND 독립 2)·REL(궁위 정의 유지)·HLT(불변).
- **fallback 금지**: 구체 provenance(궁위) 불일치 시 하위 일반화 축(십성군)이 룰을
  구제하지 못함(AND 결합) — 테스트 고정. 궁위 무관 매칭은 일반 룰로만.
- **원인별 완화(전역 완화 금지)**: 극성 단독(YONG_STRONG 등) mitigator는 근거만
  보존·상태 전환 없음. 실질 조건(합·통관 십성) 동반 mitigator만 MITIGATED.
  operability·mitigation_target 연동은 R1.
- **흡수 역할 보존**: absorbed_role(supporting_manifestation/impact_amplifier/
  background_vulnerability/secondary_domain_effect) — 흡수는 삭제가 아니라 역할 전환,
  R1 impact/exposure 계산에 사용. family 다르면 같은 충이라도 병존.
- **cause_atom 정규화 테스트**: 관계·대상·기간별 분리, 반복 호출 결정성, 다중 십성
  정렬(순서 무관), & 원자 분해.
- **대표 7항목 reviewed:true 전환**(shadow 구조 감수 완료 의미 — 노출 승인 아님).
  kind별 승격 lint 통과 확인.
- **밀도 리포트 3차**: 발동률 분모 명시(적용 차트/전체 병기) + 최장 연속 발동(월)
  지표(>50% 범용 룰 의심 경고). 재실측: FIN_UNEXPECTED_EXPENSE top10 이탈(3차
  강화 효과), incident 687→632. 잔여 경고 전부 미개정 37항목. 목표 확정치
  (RISK_ENGINE.md §10-2): 코퍼스 기준 >40% = 0, p90 active incident ≤3, 확산 3은
  교차 도메인 연쇄만.
- 테스트 47건(+5: fallback 금지·극성 mitigator 무전환·흡수 역할·cause_atom 정규화·
  target-only targeted 거부). 검증: pytest 1805 passed·ruff·mypy clean.
- **다음(승인됨)**: 잔여 37항목 §2 일괄 규칙 적용(변환 직후 reviewed:false, 엔진 변경
  필요 시 커밋 분리) → 재실측(§10-2 기준) → 도메인별 표본 감수 → reviewed:true.

### 위험 엔진 R0.5 4차 — 생성/등급 재분리·reviewScope·관계 allowlist·과소탐지 가드 (2026-07-15, 데굴님 커밋 B 승인 조건)

37항목 도메인별 적용 착수 전 선행 조건 반영:
- **생성 조건 ≠ 등급 조건 재분리**: MOV/SEL evidenceContract minIndependentCauses
  2→1 완화(구조 충족 + 독립 1원인도 후보 생성, 등급 watch 상한은 R1). 다원인 강제는
  예외적 위험별 정책으로 격하 — candidatePolicy="multi_cause_only"+rationale 명시를
  스키마로 강제(현재 유일: HLT_CHRONIC_FLAREUP 건강 오경고 통제).
- **reviewScope/reviewVersion**: reviewed:true는 reviewScope 필수(lint) —
  shadow_structure(노출 승인 아님)/scoring/selection/exposure. 대표 7항목에
  shadow_structure·R0.5 부여.
- **targeted_event_shape 관계 allowlist**: 충·형·파·해만(HAP·BOKEUM 스키마 거부) —
  '궁위가 있으니 targeted' 기계 변환 차단.
- **다층 중첩 cause 테스트**: 같은 관계·같은 대상 반복=원인 1(중첩은 R1
  layer_convergence 소관), 충+형이 같은 대상=독립 2. 파생 태그≠새 원인(원시 사실만
  수집으로 원천 차단) 문서화.
- **과소탐지 가드**: 단일 원인 targeted 후보 생존 테스트(FIN 겁재 동반 재성 피격
  단독→활성), 유사 음성(대상 미상 관계) 테스트, 지표 규격화(양성 fixture recall
  100%=pytest CI·골든 recall·watch 생존율·mitigated 보존율 — 밀도만 최적화 금지).
- 테스트 53건. 검증: pytest 1811 passed·ruff·mypy clean.
- **다음**: 37항목 도메인별 적용(①재물·계약 ②직업·시험·선발 ③이동·주거 ④관계
  ⑤건강·안전 ⑥일반 pressure/vulnerability — 차수당 5~10항목, 각 차수 저작→lint→
  fixture→중간 밀도→표본 감수. 자동 변환 금지 대상: 무대상 사건·건강/법률 결과
  암시·프로필 축 필요·relatedDomains 복제·3도메인 확산 → pressure/vulnerability
  강등 또는 비활성).

### 위험 엔진 R0.5 5차 — 착수 전 필수 보완 6종 (2026-07-15, 데굴님 재물·계약 차수 승인 조건)

- **manifest 정정**: 미개정 = FIN 6 + LEG 5 = **11항목**(이전 "10항목" 보고 오류 —
  코드 기준 재집계). REVIEW.md §6에 항목별 표(kind 변경·exposure 필요·claim 방향)
  고정. 커밋 분리: C1=FIN 6(전용 밀도·감수) / C2=LEG 5(교차 중복 검사).
- **reviewScopes 누적 구조**: 단일 reviewScope → reviewScopes 배열 +
  reviewVersions(scope→차수 map). 단계별 감수(structure/scoring/selection/exposure)
  기록이 덮어써지지 않음.
- **감수 무효화 가드**: reviewedRuleHash(룰 본문 sha256[:16] — 트리거·증폭·완화·차단·
  증거계약·kind, 표현 정책 제외) — reviewed:true인데 해시 불일치면 lint 실패(룰 수정
  = 자동 재감수 요구). risk_rule_hash() 헬퍼로 스탬프. 7항목 스탬프 완료.
- **관계 의미 계층**: targeted_event_shape는 충·형만(disruptive_strong). 파·해
  (disruptive_weak)는 target_activation만 — 단독 발화 불가·기계 동일 적용 금지.
  특수 합(합거·묶임)·복음(반복성)은 relationEffect 축 R1 백로그.
- **HLT_CHRONIC_FLAREUP 현실 노출 조건**: multi_cause는 필요조건일 뿐 — R1 필수
  조건(독립 2 + 관리 상태/노출 CONFIRMED, UNKNOWN이면 '기존 약점 관리' 수준 제한 +
  is_exposable=false, 미충족 시 HLT_GENERAL_VULNERABILITY 강등 검토) 명시,
  "만성질환 재발 단정" prohibited 추가.
- **항목별 recall 게이트**: reviewed:true risk_id마다 양성 fixture 존재를 테스트로
  강제(_DOMAIN_CASES 커버리지 검사 — 전체 평균이 아니라 항목 단위 100%).
- 테스트 56건(해시 불일치·PA targeted 거부·reviewed fixture 커버리지 등 +3).
  검증: pytest 1814 passed·ruff·mypy clean.

### 위험 엔진 C1 — 재물 6항목 저작 + 공통 정책 (2026-07-15, 데굴님 C1 승인 조건 6종 반영)

- **C1-a(ed27514) 공통 정책**: 범위별 reviewHashes(hashSchemaVersion=2, structure/
  scoring/selection/exposure 해시 대상 분리+lint), RiskExposurePolicy(요구 4단계
  not_required/required_for_warning/required_for_exposure/confirmed_required + UNKNOWN/
  DENIED 액션 + claimCeilingWhenUnknown — note가 아닌 기계 판독), crossDomainEffects,
  dedupe 키에 source_group(같은 사실의 shape/targeted 병행 매칭 시 그룹 보존),
  밀도 structural vs exposure-qualified 병기.
- **C1-b FIN 6항목 저작**(전부 reviewed:false): CASHFLOW_PRESSURE=재정 유입·유출
  activation 필수(범용 기신+겁재 단독 미생성 — 회귀 갱신)/INVESTMENT_LOSS=편재-비겁
  동반 shape·required_for_exposure(UNKNOWN watch 상한)/DEBT_GUARANTEE_BURDEN(canonical
  ID)=confirmed_required(UNKNOWN은 advisory 체크포인트만·운 구조로 보증 추론 금지·
  family=liability)/INCOME_DELAY=지급 지연 전용(수입 감소=CFP·금액 이견=SET 분리,
  재성 공망 shape 필수)/SETTLEMENT_DISPUTE=FIN 소유(돈의 지급·회수·정산 — 권리·의무·
  절차는 LEG, crossDomainEffects=contract_review_needed, 형+재성 이견 구조 필수 —
  단순 재성 충으로 승격 금지)/BUFFER_WEAK=GI_STRONG 단독 제거(재물 활성 동반),
  구체 사건 시 background_vulnerability 흡수.
- **의미론적 recall fixture**(test_risk_fin_c1.py 7건): 생성 여부가 아니라 상태·흡수
  역할·근거 원자·exposure_requirement까지 검증. 유사 음성(편재 없는 피격, 공망 없는
  피격, 충만으로 분쟁 승격) 고정.
- **밀도(C1 후, 10차트)**: 활성 6.38→5.81/기간, structural incident 2.87→2.41,
  exposure-qualified 2.25. **FIN 전 항목 경고·top10 발동률 이탈**(BUFFER_WEAK 28.2%
  · >40% 차트 0). 잔여 경고 = LEG_REVIEW_CAPACITY_WEAK 45.5%(C2 대상)·
  CAR_WORK_OVERLOAD 41.8%(직업 차수 대상). 검증: pytest 1821 passed·ruff·mypy clean.
- **다음**: C2 = LEG 5항목(+교차 도메인 중복 검사) → 표본 감수.

### 위험 엔진 C1 마감 — FIN 6항목 shadow_structure 승격 (2026-07-15, 데굴님 조건 3종 충족)

- 조건① specificityRank를 scoring 해시에서 제거(selection 전용) — hashSchemaVersion 3.
  매처 의미론 변경 감지(reviewEnvironmentVersion)는 R1 전 도입 예정으로 규격 기록.
- 조건② 노출 음성 fixture 확장: INV UNKNOWN(구조 유지)≠DENIED(BLOCKED), DEBT
  DENIED→BLOCKED(근거 보존), SET 대상 무관 형 음성 + 동일 사실 shape/targeted 병행
  매칭 시 독립 원인 1 assertion(R1 occurrence 1회 가산 규격).
- 조건③ SET는 형 자체가 아니라 정산 대상(재성) 활성 필수 — 음성 fixture로 고정.
- FIN 6항목 reviewed:true·reviewScopes [shadow_structure]·reviewVersions {C1} 승격 +
  전 reviewed 13항목 v3 해시 재스탬프. BUF trigger는 구조적 약화=event_shape 재분류
  (vulnerability 승격 계약 충족). RISK_ENGINE_MODE는 계속 off.
- 밀도 리포트에 exposure_assumption 명시(전 후보 UNKNOWN 가정·qualified 정의).
- 테스트 59건(FIN 10건). 검증: pytest 1824 passed·ruff·mypy clean.
- **다음: C2 = LEG 5항목**(REVIEW_CAPACITY_WEAK 45.5% 원인 제거, DISPUTE_LITIGATION
  노출 필수, FIN-LEG primary 구분: 돈=FIN/권리·의무·절차=LEG/독립 원인 양쪽=병존/
  파급만=primary+crossDomainEffects).

### 위험 엔진 C2 — 계약·법률 6항목 저작 + 착수 조건 5종 (2026-07-15, 데굴님 C2 승인)

- C2-a(60c6850): 상태 변경 exposurePolicy 필드 구조 해시 편입(hashSchemaVersion 4),
  structural_weakness 그룹(vulnerability 전용 — occurrence/impact 역할 분리),
  BUF 재분류·13항목 v4 재스탬프. 매처 의미론 불변 → reviewEnvironmentVersion 연기.
- C2-b(62222ac): LEG_DISPUTE_LITIGATION을 DISPUTE_RISK(required_for_exposure)/
  LITIGATION_ESCALATION(confirmed_required, 같은 family 흡수)으로 분리. ADMIN_DELAY
  pressure 강등. REVIEW_CAPACITY_WEAK GI_STRONG 단독 제거(structural_weakness+문서
  동반). CONTRACT_CANCEL·DOCUMENT_ERROR 대상·노출 계약. FIN-LEG primary fixture
  (재성 형=FIN/관성 형=LEG/독립 대상=병존/흡수). 전부 reviewed:false — 감수 대기.
- 밀도(10차트): structural incident 2.41→2.20, exposure-qualified 1.88(목표 1.5 근접),
  LEG 전 항목 경고·top10 이탈. 잔여 경고 = CAR_WORK_OVERLOAD 41.8%(직업 차수).
  pytest 1829 passed·ruff·mypy clean.
- 다음: LEG 6항목 표본 감수 → 직업·시험·선발 차수(C3).

### 위험 엔진 C2 마감 — LEG 승격 조건 6종 + shadow_structure 전환 (2026-07-15)

- **흡수 역전 방지(조건1)**: 대표 우선순위 = 구조 적격성 → 노출 적격성 → 특이도.
  confirmed_required인데 CONFIRMED가 아닌 후보는 노출 가능 후보를 흡수 불가 —
  UNKNOWN이면 대표=DISPUTE_RISK(escalation은 구조 보존), CONFIRMED이면 escalation이
  흡수, DENIED면 BLOCKED(fixture 3상태 고정).
- **reviewEnvironmentVersion 도입(조건6)**: 억제 의미 변경과 동시 도입 —
  RISK_REVIEW_ENVIRONMENT_VERSION="risk-engine-r0.5.4", reviewed 항목은 감수 당시
  버전 스탬프·불일치 시 lint 실패(사전 불변이어도 엔진 의미 변경=재감수).
- **대상 서명 정규화(조건2)**: 관계 서명에 궁위+자리+글자+십성(target_object_signature)
  — '다른 글자'만으로 병존 판정하지 않음.
- **fixture(조건3~5)**: LEG 6항목 양성 전수 + DOC 문서 대상 없는 유사 음성(RCW 소관
  분리) + RCW 단독 양성·흡수 역할 recall. 커버리지 게이트에 LEG_POSITIVE_IDS 편입.
- **LEG 6항목 shadow_structure 승격**(reviewVersions C2) — reviewed 총 19항목(대표7+
  FIN6+LEG6), 전체 env 버전+v4 해시 스탬프. RISK_ENGINE_MODE는 계속 off.
- **87 카운트 설명(조건 — 숫자 불일치 해소)**: validate_dictionaries의 87은 위험
  엔트리 수가 아니라 **사전 JSON 파일 수**다. risks/는 도메인 7파일 고정이라 분리로
  항목이 45개(44+분리1)가 돼도 파일 수는 불변.
- 테스트 60건. 검증: pytest 1830 passed·ruff·mypy clean.
- **다음(C3 착수 전 확정 필요)**: CAR_WORK_OVERLOAD·SEL_COMPETITION_INTENSIFY의
  kind 재분류(pressure 유지 vs 구체 incident 분리) — 범용 관성·경쟁 신호 단독 발동
  제거가 선행 과제.

### 위험 엔진 C3 선행 — CAR_WORK_OVERLOAD·SEL_COMPETITION 재저작 (2026-07-15, 데굴님 수정 조건 5종)

- **manifest 확정(조건4)**: 미개정 = CAR 5 + SEL 5 = 10항목(이전 "CAR 6"은 reviewed
  ORG_CONFLICT 포함 오집계 — 코드 기준 고정).
- **CAR_WORK_OVERLOAD(조건1)**: 관성+월주 고정 AND 폐기 → work_role_activation(월주
  궁위 충·형 또는 관성·식상 피격 — 사업자·프리랜서·학생 경로 포함) + workload_shape
  (편관+식상/정관+재성/겁재+관성 등 요구·산출·역할 중첩 조합) 계약. 기신·운성·공망
  amplifier. required_for_exposure(UNKNOWN='맡은 일이 있다면' advisory). 과부하·번아웃·
  건강 악화 표현 금지.
- **SEL_COMPETITION_INTENSIFY(조건2·3)**: selection_target_activation(심사 관문 피격)
  + competition_shape(비겁+관성 결합) 필수. applicableSelectionModes 필드 신설 —
  competitive_assessment 전용(추첨·자격 심사·배치 별도 구조, '실력 열세 단정(추첨형)'
  prohibited). 경쟁 심화는 탈락 후보의 trigger가 아니라 배경 압박(fixture 고정).
- **조건5**: 기존 그룹·매칭 축만 사용(신규 매처 의미 없음) — reviewEnvironmentVersion
  r0.5.4 유지.
- fixture: 양성/관성 기신만 음성/월주만 음성/선발 대상 없음 음성/DENIED 차단/결과
  미생성. **밀도: 발동률 >40% 항목 0건 달성**(CAR 41.8%·SEL 39.1% top10 소멸), 활성
  5.20/기간. 검증: pytest 1834 passed·ruff·mypy clean. 두 항목 reviewed:false — 감수 대기.
- 다음: C3 본 차수(CAR 4 incident + SEL 4 incident 재저작 — EXIT_PRESSURE·HIRING·
  LOTTERY_MISS(SEL_ODDS_PRESSURE 전환 검토)·PLACEMENT 등).

### 위험 엔진 C3-a 마감 — 대상 연결·mode UNKNOWN 정책 + 두 pressure 승격 (2026-07-15)

- **requiresLinkedTargets(env r0.5.5)**: shape 계열과 활성 계열 trigger가 원인 원자
  공유 또는 십성군 대상 겹침이어야 적격 — 편관=사회궁·식상=가족궁 같은 무관 조합은
  targets_unlinked로 INSUFFICIENT(fixture 고정: 재성 피격+관성·식상 shape=미연결,
  관성 피격+편관 shape=연결 양성). 적격성 의미 변경이라 env 버전 갱신+21항목 재스탬프.
- **SEL 표현 제한**: 경쟁률 상승·지원자 증가·당첨 확률 저하 단정 prohibited(사주
  신호로 외부 사실 주장 금지), 사용자 라벨='선발 경쟁 부담'. 선발 방식 UNKNOWN이면
  경쟁 평가 가정 금지(fallback 미저작 — is_exposable=false, R3).
- CAR_WORK_OVERLOAD·SEL_COMPETITION_INTENSIFY shadow_structure 승격(C3) —
  reviewed 21항목. C3 본 차수 재분류 manifest 확정(REVIEW.md §7): incident 8개 전제
  폐기 — EXIT_PRESSURE·ELIGIBILITY·LOTTERY(폐기→DRAW_OUTCOME_UNCERTAINTY)·WAITLIST
  pressure 계열, HIRING 분리(지연 pressure+결과 incident), 선발 mode+stage 2축.
- 검증: pytest 1836 passed·ruff·mypy clean.

### 위험 엔진 C3-b — CAR canonical 5항목 저작 (2026-07-15, 데굴님 조건 4종 반영)

- **십성군 fallback 강화(감수 12차)**: 양쪽이 구체 대상 객체(관계 원자)를 갖는데 서로
  다르면 십성군 일치가 구제 불가 — fixture 고정(일지 형 vs 월주 충, 같은 관성군 →
  targets_unlinked). link_type 기록은 R1 백로그.
- **CAR legacy 4항목 → canonical 5항목**(전부 reviewed:false — 감수 대기):
  EVALUATION_SETBACK_RISK(DISADVANTAGE 대체 — 결과 불이익 아닌 기대 미달 위험, 평가
  노출 필요)/REASSIGNMENT_RISK(UNWANTED_TRANSFER 대체 — assignment_authority 노출
  기준, 직업 범주 아님·프리랜서 포함, '원치 않는'은 preference CONFIRMED)/
  EXIT_PRESSURE(pressure 재분류 — 해고·퇴사·실직·계약 종료 단정 금지)/
  HIRING_PROCESS_DELAY(pressure)/HIRING_OUTCOME_SETBACK(incident — 분리, 채용 결과
  CAR primary·일반 시험/공모/추첨 SEL primary). legacy 3 ID 제거(신·구 동시 생성
  불가 fixture). 전 항목 requiresLinkedTargets.
- 밀도: 활성 5.18/기간(structural incident 2.15·exposure-qualified 1.82). 검증:
  pytest 1839 passed·ruff·mypy clean.
- 다음: C3-c = SEL 4항목 canonical(DOCUMENT_DEFECT·ELIGIBILITY_REVIEW·
  DRAW_OUTCOME_UNCERTAINTY·WAITLIST_PROLONGATION/RESULT_DELAY 분기) + mode/stage
  2축(적격성 사용 시 env r0.5.6 필수) → CAR 5항목 표본 감수.

### 위험 엔진 C3-c — SEL canonical 5항목 + stage 축 + CAR fixture 확충 (2026-07-15)

- **manifest 정정**: SEL legacy 4 → canonical **5**(RESULT_DELAY와 WAITLIST 분리 —
  exposure·stage 상이). SEL_DOCUMENT_DEFECT_RISK(stage=application_document)/
  ELIGIBILITY_REVIEW_RISK(pressure — 자격 미달 단정 금지)/DRAW_OUTCOME_UNCERTAINTY
  (mode=lottery_draw+stage=draw 전용, 상시 발동 방지: 관문 활성+기간 특이 shape,
  확률·방향 단정 금지)/RESULT_DELAY_PRESSURE(stage=result_wait, 인성 통지 정체 —
  대기명단 추론 금지, 채용 대기는 CAR primary)/WAITLIST_PROLONGATION(stage=waitlist,
  confirmed_required — UNKNOWN이면 표현 절대 불가). legacy 4 ID 제거.
- **applicableSelectionStages 축**(7단계) + mixed mode: mode·stage 상호 자동 추론
  금지, MATCHED/UNKNOWN/MISMATCHED 3상태는 R3 노출 판정 소비(UNKNOWN=구조 보존·특정
  표현 금지 / MISMATCHED=NOT_APPLICABLE·임의 fallback 금지). **현 엔진 적격성에는
  미사용(사전 메타데이터)이라 env r0.5.5 유지** — 적격성 사용 시 r0.5.6 필수 규격 명시.
  context_target_signature(현실 맥락 activation 연결)는 R1 백로그.
- CAR 승격 커버리지 확충: EVALUATION 관성 피격 단독 음성, EXIT 종료 사건 미생성,
  HIRING_OUTCOME 절차 정체 단독 음성. CAR·SEL canonical 전부 reviewed:false — 감수
  대기(승격은 표본 감수 후).
- 검증: pytest 1844 passed·ruff·mypy clean.

### 위험 엔진 C3-d — 선발 적격성 마감 (2026-07-15, 데굴님 필수 수정 9종)

- **결함 테스트 수정(①)**: exit/hiring OR assertion 교정 → 실제 과발동 노출 →
  HIRING_OUTCOME 계약 조정(targeted 단독 제거 — 결과 정체(공망+관성) AND 관성 피격
  필수: 관성 피격만으로는 EXIT 압박과 미구분).
- **SelectionContext 3상태 실구현(②③, env r0.5.6)**: mode/stage/target_type 엔진
  입력 — MATCHED=활성 / UNKNOWN=구조 보존+is_exposable=false / MISMATCHED=BLOCKED
  (selection_*_mismatch, 임의 fallback 금지). 상호 자동 추론 금지 fixture(stage=draw
  여도 mode=unknown). stage-aware suppression(교집합 없는 stage 메타끼리 흡수 금지).
  적격성 의미 변경 — env r0.5.6 + 21항목 재스탬프.
- **소유권 실구현(④)**: applicableTargetTypes — 채용(employment_hiring)=CAR primary
  (SEL 결과 지연 차단), 일반 선발=SEL(CAR 채용 차단) fixture. context_target_signature
  의 선발·직업 구현체(확장은 후속).
- **waitlist 기계 차단(⑤)**: exposurePolicy.unknownExposable=false + is_exposable()
  헬퍼(R3 상위 게이트 — '~일 수 있다면' 우회 금지) fixture.
- **SEL 전수 fixture(⑥)**: 5항목 각각 양성(INSUFFICIENT 아님)·3상태·상호배제·비노출.
- **공망 shape 강등(⑦)**: SEL 4건 공망 event_shape → amplifier(대체 shape: 편인 왜곡/
  관문 흔들림(충+관성)/통지 어긋남(해+인성)/계류(형+관성)). 대상 연결 판정을
  target_object_signature(관계 종류 제외 — 궁위:자리:글자:십성) 비교로 교정(형·해가
  같은 대상을 치면 연결).
- **밀도 표현·기여도(⑧⑨)**: 목표 분리(구조=structural 추적/노출=exposure-qualified
  ≤1.5 — "달성"은 프로필 미입력 UNKNOWN 가정의 projected 값임을 명시), family 밀도
  도메인 기여도 추가 — **relationship 32%가 최대**(다음 차수 근거), contract 19%,
  finance 15%. kind 비율은 완료 기준에서 제거.
- CAR 5·SEL 5 여전히 reviewed:false — C3-d 재실측 후 표본 감수 대기. 검증: pytest
  1850 passed·ruff·mypy clean.

### 위험 엔진 C4 — CAR·SEL 승격 조건 4종 + shadow_structure 전환 (2026-07-15)

- ①HOS 공망 강등: event_shape→amplifier — shape=결정·통지 어긋남(해+관성 동반),
  공망+관성 피격만으로 미활성 fixture.
- ②같은 대상·다른 관계(형+해) = linked ✓ AND 독립 원인 2(collapse 금지) fixture —
  target_object_signature(무엇을)와 cause_atom(어떤 방식) 분리, layer_convergence·
  compound 전제.
- ③소유권 항목별 매트릭스: 공통 절차 위험(문서·자격·대기명단)은 채용에도 적용
  (employment_hiring 추가) — CAR primary는 채용 과정·결과 소유권이지 절차 위험
  차단 아님. fixture(채용+서류 단계 → SEL_DOCUMENT 활성).
- ④부분 UNKNOWN: 항목이 요구하는 축만 평가(문서=stage만→matched, 추첨=mode 미확인
  →unknown 비노출, 자격=mixed matched) fixture.
- is_exposable=context-level exposure eligibility로 의미 제한(판정 계층:
  is_active→is_exposable→is_score_qualified(R1)→is_selection_qualified(R2)→
  is_finally_exposable(R3)). 기여도 계산 기준 명시(suppression 후 활성 unique
  (기간,도메인,family) 합).
- **CAR 5·SEL 5 shadow_structure 승격(C3-d)** — reviewed **31항목**, r0.5.6 재스탬프.
  검증: pytest 1854 passed·ruff·mypy clean.
- **다음: REL 6항목 차수**(family 기여 32% 최대) — 목표: 같은 관계 작용 하나가
  배우자·감정·가족·동업·사회관계 위험으로 복제되지 않도록 관계 대상·관계 exposure·
  역할별 대표 위험 분리.

## 위험 엔진 REL 차수(C5 — 감수 16차) — RelationshipContext + 관계 7항목 재저작 + C4-f (2026-07-15)

배경: C4 승인 시 데굴님 조건 — ①HOS 결과 단계 게이트 확인(부재 시 후속 패치)
②reviewed 자동 manifest ③REL 착수 조건 7건(재분류·역할별 exposure·같은 상대 흡수·
배우자궁≠현실 관계·FIN 소유권·env r0.5.7·수량 자동화). 추가 지시: 테마사주·AI채팅
궁합/함께보기 풀이 고려.

- **C4-f(HOS 후속)**: 결과 단계 게이트 부재 확인 → `applicableSelectionStages:
  [result_wait, final_decision]`(어휘 신설) — 지원·면접 단계 통지 어긋남 미적용,
  fixture 3종(matched/assessment 차단/단계 미확인 비노출).
- **자동 manifest**: `scripts/risk_review_manifest.py` →
  `doc/v2_2/RISK_REVIEW_MANIFEST.json`(reviewed_total/by_scope/by_domain/ids/env/해시
  버전) + 회귀 `test_risk_review_manifest.py`(파일=재생성 일치 + 수량 정합 강제).
- **RelationshipContext(env r0.5.7·해시 v5)**: 역할 8종 어휘·익명 target_id·관계별
  exposure·financial_tie/shared_responsibility·is_question_target(궁합/함께보기 질문
  대상). 3상태 matched/unknown/mismatched — mismatched=BLOCKED(fallback 금지),
  unknown=유효 노출 UNKNOWN(조건부 표현은 exposurePolicy 소관 — selection 축과 다름).
  requires* 유도: False→DENIED, None→CONFIRMED여도 UNKNOWN 강등(존재 추론 금지).
  해시 v5: 적용 가능성 축(mode/stage/targetType/relationshipRole)+관계 실질 조건을
  structure 해시에, absorbedRoleHint를 selection 해시에 편입(축 변경=재감수 구멍 차단).
  reviewed 30항목 재스탬프(31-PARTNER_READJUST 재저작 반납).
- **같은 상대 흡수**: relationship 도메인 억제 범위=family→같은 상대(target_id·역할
  호환), cross-family 수렴. 대표 탐색 일반화(그룹 최상위 1건→선호 순서대로 원인 공유
  첫 적격 대표, 흡수된 후보는 대표 불가). absorbed_role에 possible_trajectory 신설
  (사전 absorbedRoleHint 데이터 주도).
- **REL 7항목 재저작**: PARTNER_READJUST(incident→pressure, 역할 한정, 겁재·상관
  amplifier 강등) · EMOTIONAL_CLASH(→pressure, 겁재/칠살 shape+비겁군 피격 linked) ·
  COMMUNICATION_MISALIGNMENT(개명, 상관 shape+식상군 해·파) · TRUST_STABILITY_WEAK
  (개명, vulnerability — structural_weakness+파 계약) · DISTANCE_PRESSURE(개명,
  공망·묘절·편인 amplifier 강등, 흡수 시 possible_trajectory) · FAMILY_BURDEN
  (년·월주 targeted, requiresSharedResponsibility) · PEER_FINANCIAL_ENTANGLEMENT_RISK
  (개명, confirmed_required+requiresFinancialTie+2독립 원인, unknownExposable=false,
  FIN 소유권: 같은 원인 동시 활성 대표 선정은 R2 병합 소관 — R0.5 양쪽 구조 보존).
- **fixture(test_risk_rel_c5.py, 23종)**: 항목별 양성 recall 7 + 역할 분리(배우자궁/
  가족궁/친구 금전) + partner 4상태(CONFIRMED 노출·UNKNOWN 조건부·DENIED 차단
  +fallback 금지·N.A. 차단) + 같은 상대 확산 수렴(대표 1 family) + 다른 상대 병존 +
  궁합 질문 대상 역할 불일치 차단 + requires* 축별 유도 + FIN-REL 소유권/병존 +
  HOS 단계 게이트.
- **밀도 실측**: relationship 기여 32%→19%, REL family/기간 p90 2, REL 단일 원인 확산
  max 2(예외 한도 내), 흡수 역할 수렴 실측(trajectory 13·supporting 6·background 4),
  structural incident/기간 1.75→1.22. 잔여: 전역 확산 max 9 — 미개정 MOV·HLT 원천.
- 상태: REL 7항목 reviewed:false(표본 감수 대기 — 승격 시 30→37, manifest 확인).
  RISK_ENGINE_MODE=off 유지. 검증: pytest passed·ruff·mypy clean(아래 게이트 실행).

### C5 감수 17차 후속 — 커밋 전 필수 조건 7건 (2026-07-15)

①대표 선택 결정적 비교자(노출 적격→구체 상대→역할 특정→rank→risk_id, 사전 역순
fixture) ②target_id 미확인 수렴 제한(같은 상대 아니면 relation 원자 공유 필수 —
십성 유입 단독 수렴 금지) ③is_question_target 자동 확인 금지 fixture ④FAMILY_BURDEN
월주 경로=가족 육친 대상(인성·비겁군) 피격 명시 발동만(27.7%→20.0%) ⑤possible_
trajectory R1 불변식 기록(occurrence·원인 수·등급 기여 금지) ⑥trigger_cause_atoms
연결 키(FIN·REL 1회 계산·R2 대표 1개 재료) ⑦r0.5.6→r0.5.7 비REL diff: 2,759건 비교
— 대표 변경 0·신규 흡수 0·해제 0(무영향 확정). UNKNOWN 차등: 역할 특정 항목 조건부
노출은 matched(관계 질문·확인)에서만. cross-family 흡수=absorbedRoleHint 명시 항목만.
재실측: REL 기여 17%, REL 확산 max 2, 전체 family p50 4·p90 8·max 13.

## 위험 엔진 MOV 차수(C6 — 감수 18차) — MobilityContext + 이동·주거 6항목 (2026-07-15, 감수 대기)

manifest 선행 고정(REVIEW.md §9 — 데굴님 조건 6건) 후 구현: ①MobilityContext(target
8종·stage 8종·preference=R3 표현 전용·tenure·실질 조건 3종) — 축 UNKNOWN=selection과
동일 하드 비노출, env r0.5.8·해시 v6, reviewed 37 재스탬프 ②소유권: 발령=CAR(workplace
제외 MISMATCHED)·계약 문서=LEG·수리비 금전=FIN 파생·거주 이동=MOV·안전=권고 톤
③재저작: SCHEDULE_DISRUPTION(→pressure·공망 강등), DEFECT_REPAIR(겁재-인성 동반+
requiresRepairResponsibility), COMMUTE_BURDEN(운성 강등+requiresCommuteDependency·해
트리거 밀도 교정), UNWANTED_MOVE→RELOCATION_PRESSURE(비자발 명칭 제거·→pressure),
VEHICLE(requiresVehicleExposure+unknownExposable=false), CONTRACT_FAIL 축·정책 추가
(C6 재스탬프 — 재감수 대상) ④수렴 도메인 {relationship, relocation} 확장 — 같은 이동
episode 대표+supporting/impact_amplifier ⑤억제 baseline 게이트 신설(3,330건 — diff는
relocation만, 타 도메인 0) ⑥밀도 계층화(구조 진단/context-exposable ≤4~5/R2 ≤3)+max
기간 구성 보고. 밀도: relocation 12%, MOV fanout 2, structural incident 1.09. fixture
13종, pytest·ruff·mypy clean(아래 게이트). MOV 5항목 reviewed:false 감수 대기.

### C6 감수 19차 후속 — 커밋·승격 전 필수 조건 8건 (2026-07-15, 감수 대기)

①CONTRACT_FAIL 승인 전 강등(reviewPending=C6, manifest 36)+재스탬프 절차 가드
(scripts/risk_restamp.py — HEAD 비교로 내용 변경=자동 강등, env-only만 재스탬프)
②개명 MOV_CONTRACT_SETBACK_RISK(결과형 명칭 완화) ③stage 호환 억제(계약 전 vs 정착
후 상호 배타 수렴 금지) ④mobility episode_id(익명 계획 키 — 다른 계획 병존)
⑤UNKNOWN 차등(RELOCATION=required_for_warning 조건부 유지, 구체 항목 하드 비노출)
⑥workplace 병존(컨텍스트 목록+is_question_target — 발령+주거 이동 확인 시 CAR·MOV)
⑦confirmed 시나리오 4종 실측(--mov-scenarios: 노출 25/38/52/56, family/기간 p90 1)
⑧DEFECT→MOV_HOUSING_DEFECT_RISK(하자 전용·비용 FIN·책임 LEG 파생)+COMMUTE 적응 분리.
baseline --rename 분류: relocation만(rename 130·수렴 20·소실 200·신규 141), 타 도메인 0.

### C6 감수 20차 — 마감 조건 4건·승격 42 (2026-07-15)

①restamp 1차 기준=저장 reviewHashes(커밋 순서 비의존, HEAD는 --schema-migration 보조)
+회귀 3종 ②DEFECT 본체에서 repair_responsibility 제거(FIN 파생 게이트 전용 — 임차인
과소탐지 방지) ③RELOCATION DENIED=BLOCKED 확정(UNKNOWN advisory와 구분, 이사 표현
차단, fallback 미저작) ④episode별 후보 분리 생성(동일 항목 2 episode=후보 2·결정적
병합·episode 경계 흡수) + 시나리오 비율 지표(exposable/active 25→57%). baseline 소실
200건 성격 명시: exposure 게이트는 후보를 제거하지 않으므로(구조 보존) 소실은 전량
구조 단계 변화(트리거 강화·계약·개명 — UNWANTED 68=개명 14+트리거 재저작 54 등).
**MOV 6항목 shadow_structure 승격(C6) — reviewed 42**, baseline 재기록. pytest 1911.

## 위험 엔진 HLT 차수(C7 — 감수 21차) — HealthContext + 건강 8항목 (2026-07-15, 감수 대기)

manifest 선행 고정(REVIEW.md §10 — 조건 8건) 후 구현: ①HealthContext(context_type
7종·상태값 4축·health_episode_id·is_question_target — 질병명·부위 저장 금지), 실질
조건 4종(none=DENIED·미확인=UNKNOWN 강등·physical none/low=DENIED), env r0.5.9·해시
v7 ②CHRONIC_FLAREUP 착수 강등(42→41)+개명 EXISTING_CONDITION_STRAIN(→pressure)
③전 항목 pressure/vulnerability(질병 incident 금지 — 사전+런타임 fixture) ④신설 2
(치료·회복 부담/신체 업무 부담 — §11·§15 근거, 감수 질문) ⑤수렴 도메인 health_safety
추가+episode 분리 ⑥소유권(CAR·FIN·LEG·MOV — 진단은 예측 대상 아님) ⑦restamp
--schema-migration 절차 첫 적용(41건 불변) ⑧baseline 메타데이터 신설+비HLT 변화 0
확인 ⑨밀도 교정(FATIGUE 42.7%→18.2%) ⑩시나리오 5종(오노출 0, 질문=미확인 동일성
검증). structural incident 1.00. pytest 전체(아래)·ruff·mypy clean. 감수 대기.

## 위험 엔진 HLT 차수(C7 — 감수 21·22차) — HealthContext + 건강 8항목 승격 49 (2026-07-15)

감수 22차 조건 4건: ①FATIGUE에서 GI_STRONG shape 제거(소모 shape+체력 피격 계약,
GI_STRONG=amplifier — 단독 미활성/증폭 테스트) ②ECS 1원인 watch 복원(2원인 필수 폐지)
③shift_or_irregular·monitoring 비확인 처리+TRL 표현 단계 분기 ④차량 episode 교차
도메인 수렴(MOV primary·HLT impact_amplifier). 파생: 노출 역전 방지 일반화(_exposure_
ok=is_exposable, confirmed_required 미충족=비노출) — 비HLT 30건 의도 변경 허용 목록
기록(REL FAMILY_BURDEN·MOV CONTRACT_SETBACK 비노출 대표의 advisory 흡수 해제).
vulnerability 추적 지표 신설(활성/기간 1.20·흡수 23·승격 기여 0). **HLT 8항목
shadow_structure 승격 — reviewed 49(전 도메인 unreviewed 0)**. incident 감소분
1.09→1.00은 CHRONIC kind 재분류 주요인. pytest 1936·ruff·mypy clean.

## 위험 엔진 LEG 재검토 차수(C8 — 감수 23차) — LegalProcessContext (2026-07-15, 감수 대기)

manifest 선행(REVIEW.md §11 — 기준 9건): ①LEG 6항목 착수 강등(49→43, PENALTY 유지=
감수 질문)+재스탬프 43 ②LegalProcessContext(target 8·stage 11·process_episode_id·
existing_dispute/litigation — Selection 어휘 비재사용) ③개명 CONTRACT_TERMINATION_
RISK·문서=법적 효력 한정·ADMIN=공식 행정 한정·LITIGATION=requiresExistingLitigation·
RCW=process 연결+background 수렴 ④수렴 도메인 LEG 추가+같은 현실 대상 판정 일반화
(episode 동일성) ⑤vulnerability 단독 노출 없음 명문화 — BUF→CFP 역전 42건 해소(의도
변경 목록) ⑥env r0.5.10·해시 v8 ⑦baseline: 비LEG 파생=위 42건뿐. 밀도: structural
incident 0.95, LEG p90 2, 잔여=RCW 구조 40.9%(노출 0)·확산 3(PENALTY 미개정 포함).
fixture 8종+c2 개정. pytest 전체 clean. 감수 대기.

## 위험 엔진 C8 마감 — 감수 23차 커밋 조건 4건+권장 2건 일괄·LEG 7항목 승격 49 (2026-07-16)

데굴님 감수 23차 결론(6항목 단독 재승격 보류) 반영: ①PENALTY 감수 반납+C8 편입
(process 대상 5종·성립 전/종결 stage 제외·unknownExposable=false — 벌금·과태료·처벌·
유죄·행정처분 단정 금지) ②LITIGATION_ESCALATION→**LEG_LITIGATION_PROCESS_BURDEN**
(incident→pressure — 이미 소송 중=절차 부담, structural incident 0.95→0.92는 재분류
효과) ③stage **active_contract** 신설 — TERMINATION은 negotiating으로 대체 불가
④closed stage 명시 opt-in(종결 절차의 신규 후보 생성·흡수 차단) ⑤vulnerability
대표 금지 일반화(단독 노출 없음+흡수 대표 불가 — 전 도메인 synthetic fixture)
⑥`--leg-scenarios` 4종 실측: RCW observed 90 전부 잠재 구조 — 독립 노출 0·독립
family 기여 0·대표 흡수 0(전 시나리오 목표 충족, 표기=observed latent 40.9%).
fixture 8→19종(PENALTY 3·RCW 역할·결정적 병합·stage 배타·closed·MOV/SEL/REL
소유권·7도메인 역전 방지). env r0.5.11(42건 env-only 재스탬프)+**LEG 7항목 승격 —
reviewed 49(전 도메인 unreviewed 0)**, manifest·baseline 재기록(diff 전수 분류:
비LEG=승인된 FIN 42건뿐). pytest 1960·ruff clean·mypy C8 파일 clean(기존 테스트
타입 부채 142건 발견 — 중복 모듈 오류가 가리던 것, 별도 차수 필요). 다음: 3프로필
시나리오 재실측→R1.

## C8 승인 확정(감수 24차) — RCW 지표 분리·3프로필 baseline·R1 진입 게이트 (2026-07-16)

데굴님 최종 결정: **커밋 03eeac5·LEG 7항목 재승격·reviewed 49·env r0.5.11·해시 v8
전부 승인, C8 마감 완료(재오픈 없음)**.

**검증 표기 정정(데굴님 지적 — 이후 차수 공통 규칙)**: 기존 `mypy .` 검사가
tests.unit 접두 import의 중복 모듈 오류 1건에서 조기 종료되어 **전체 테스트 타입
검증을 수행하지 못하고 있었음**(기존 게이트의 사각지대 — C8의 실패 아님). import
정합화 후 기존 부채 142건 확인. 현재 정확한 상태 표기:
`mypy production/C8 scope: clean · project-wide mypy: existing test typing debt 142`.
저장소 전체를 "mypy clean"으로 표기 금지. env r0.5.11 재스탬프 42건의 정확한 성격:
사전 본문은 불변이나 엔진 대표 선정 의미가 변경됐고, 관측된 비LEG 동작 변화
42건(FIN 역전 해소)을 전수 감수한 **환경 재승격**.

후속 반영: ①RCW 지표 명칭 분리 — rcw_became_representative(반드시 0) vs
rcw_absorbed_as_background(같은 episode 구체 대표 아래 흡수 — 정상 발생 가능) vs
rcw_standalone_exposable(반드시 0) ②**3프로필 노출 단계 baseline 고정**
(--profile-scenarios → doc/v2_2/RISK_PROFILE_BASELINE.md): all_unknown 하한
exposable 1.28/기간 → typical_confirmed 1.56 → high_exposure 상한 1.64, C의
BLOCKED 468 전량 소유권 MISMATCHED(SEL 45→0, CAR primary — 라우팅 검증).

**R1 진입 게이트(데굴님 §10 — R1 착수 전 필수)**: ①PENALTY risk_id/kind/claim
scope 최종 정합화(현 허용 표현이 전부 점검 수준이면 pressure 재분류 —
LEG_COMPLIANCE_OBLIGATION_PRESSURE 류 — 또는 위반·제재 CONFIRMED 조건의 conditional
incident 유지, **감수 질문**) ②RCW 지표 분리(완료) ③3프로필 결과 고정(완료)
④**TYP-0 차수: 프로젝트 전체 mypy 부채 0**(mypy production=0 즉시·tests=142
baseline 신규 증가 금지 CI 분리 → 별도 차수에서 0. union-attr=assert/type guard,
arg-type=fixture 반환 타입, 광범위 Any·ignore 금지, 테스트 의미·입력 불변, 완료
조건=mypy 0+pytest 불변+risk baseline diff 0+3프로필 지표 불변) ⑤프로필별 양성
fixture recall 유지 ⑥교차 도메인 동일 cause occurrence 1회 계산 규격 확인(표본
372~399건) ⑦possible_trajectory·vulnerability occurrence 기여 0 ⑧R1 전 baseline
commit·env·사전 해시 고정. 순서: C8 baseline → 3프로필(완료) → **TYP-0** → 동일
프로필 재확인 → R1.

## C8-f — 구 PENALTY kind 정합화·baseline 최종 고정(감수 24차 후속) (2026-07-16)

데굴님 확정 반영: **LEG_PENALTY_LIABILITY → LEG_COMPLIANCE_OBLIGATION_PRESSURE**
(incident_risk→pressure·claimCeiling watch·manifestations=기한 재확인/의무 점검/
대응 자료 부담 — 허용 표현·노출 조건이 전부 준법 점검 수준이라 incident 아님, R1
impact prior·budget 왜곡 방지). 금지 표현 유지. 별도 제재 incident(LEG_SANCTION_
RISK 류)는 실제 위반·제재 절차 CONFIRMED 데이터 확보 전 저작 금지. 감수 반납
(49→48)→재승격(49), env r0.5.11·해시 v8 유지(사전 변경 — 엔진 의미 불변).
suppression baseline diff=순수 개명 이동(29+대표 표기 5)·비LEG 0, 재기록.

재측정: structural incident/기간 0.92→**0.87**(재분류 효과), LEG 기여 193(23%)·
family p50/p90/max·exposable 밀도 전부 불변. **기계 판독 profile baseline 신설**
(scripts/risk_profile_baseline.py --write/--check — 완전 일치 원칙, env·사전 해시·
프로필 컨텍스트 해시 불일치도 실패): doc/v2_2/RISK_PROFILE_BASELINE.json + MD 최종
고정(exposable/기간 1.28/1.56/1.64). **blocked 분해 지표 추가 + SEL 45→0 범위
확정**: C의 BLOCKED 468 전량 selection 도메인·selection 축 사유(타 도메인 오차단
0 — 채용 episode 국한 정상). 단 SelectionContext는 단수·episode 없음이라 "채용+
일반 선발 동시 episode" 병존은 표현 불가 — selection 축 episode 확장(SEL-e 차수,
엔진 의미 변경) 필요 여부를 감수 질문으로 기록(확장 전 R3/R5 배선은 질문 대상
선발 1건만 주입). pytest 1960·ruff clean·mypy 신규/변경 스크립트 clean.
다음: **TYP-0** → profile·suppression baseline exact match → R1.

## TYP-0 — 테스트 타입 부채 142건 → 0·mypy 게이트 복구 (감수 25차 승인 착수, 2026-07-16)

blocked 지표 표기 보완 선행(데굴님 §3): blocked_unique_candidates(468) vs
blocked_reason_occurrences(927) 분리 + selection 축 조합 분해(target_type_only 214·
stage_only 202·동시 52 = 468 합 검증), profile baseline JSON/MD 재기록.

TYP-0 본문 — 런타임 동작 불변 원칙(허용 diff 0): tests/ 39개 파일 142건 전수 수정.
①union-attr(51)=assert/type guard 축소(luck_cycles·yongsin_analysis·time_range·
pillars 등 Optional 접근) ②arg-type(57)=helper 반환 타입 정확화(SimpleNamespace
테스트 더블은 cast("ManseV2Result" 등) — 개별·명시적, 광범위 Any 금지 준수.
importlib spec None 가드, dict 값 타입 주석, **kwargs 번들만 dict[str, Any])
③attr-defined(23)=helper 반환 object→실제 타입(DirectionSuggestion·
RegionElementProfile 등) ④전체 실행에서 unused 확인된 type: ignore 4건 제거(스코프
실행의 unused 오탐 2건은 유지) ⑤hap_modes _pillar 가변 인자 정리·lei_db fixture
Iterator 반환 명시. 수정 중 회귀 1건 자가 검출·정정(test_event_taxonomy_v2 —
signals_ko는 list[str]인데 str 가정으로 의미 변경했던 것을 원 의미로 복원).

CI 게이트 분리(ci.yml): Mypy (production)=packages/apps/scripts + Mypy
(project-wide)=`mypy .` 2단계 — 테스트 부채가 production 회귀를 가리는 사각지대
재발 방지.

완료 게이트 전부 통과: **mypy . = 0(516파일) · mypy production = 0(294파일)** ·
pytest 1960 passed·38 skipped(기존 결과 불변) · ruff clean · **profile baseline
완전 일치(exact match)** · suppression baseline diff 0(3,412건) · manifest 일치.
다음: SEL-e(다중 선발 episode 확장 — R1 전 필수) → A/B/C+D(multi_selection)
프로필 재실측 → R1.

## SEL-e — SelectionContext 다중 선발 episode 확장(감수 25차 승인 착수, 2026-07-16)

blocked 3층 집계 확정 선행(unique 468/candidate×reason pairs 927 — target·stage 축
520=불변식 assert 내장/raw hits 927 — '927'은 축 외 사유 포함 pair였음, 명칭 정정).

본문: ①SelectionContext 확장 — episode_id(유형과 별개 명시 키)·exposure·
is_question_target(기본 True=단수 의미 보존) ②episode별 해석·후보 identity(risk_id+
period+episode)·소유권(mismatch 전파 금지 — 호환 episode 우선) ③결정적 병합·보완
vs CONTEXT_CONFLICT(임의 우선순위 금지 — 구조 보존·비노출·위생 로그) ④서로 다른
episode 자동 흡수 금지(shared cause는 R1 1회 계산 연결 유지) ⑤단수 하위 호환
(selection_context=ctx ≡ selection_contexts=[ctx], byte-identical). env r0.5.12·
해시 v8 유지, 9항목(SEL 7+CAR_HIRING 2) 반납 49→40→재승격 **49**, 타 40건 env-only
재스탬프. fixture 8종 + 기존 위험 테스트 198건 불변 + A/B/C profile 완전 동일 +
**D_multi_selection 신설**(hiring 4·exam_1 25·exam_2 32·lottery 23 병존, BLOCKED
468→202 전량 stage 사유, SEL 기여 0→33, exposable 1.58·p90 4). suppression
baseline diff 0 재기록(메타 r0.5.12). pytest 1968·ruff·mypy 0(전체) clean.
다음: **R1 착수**(진입 게이트 §10 전부 충족 — occurrence 1회 계산 표본 372~399,
possible_trajectory·vulnerability 기여 0 원칙, baseline commit·env·해시 고정).

## R1-a — 위험 점수 인프라(shadow 전용·감수 26차 착수, 2026-07-16)

blocked 지표 명칭 분리 선행(데굴님 §2 — 927은 차단 사유가 아니라 BLOCKED 후보의
전체 eligibility 사유 pair): blocking_axis(C 520/D 251)·evidence_deficiency(407/
180)·all_reason_pairs(927/431)·raw_hits 4층 + 불변식 assert.

risk_scoring.py 신설(순수 함수·랭킹/노출/등급 없음): 6축 score_shadow(그 외 필드
byte 불변)·cause_occurrence_table((기간,원인)당 1회 — 포트폴리오 합산 원천)·
risk_priority(raw/capped — total은 마지막 한 번·후보 미저장). 불변식 fixture 9종:
적격성/대표/노출 불변·evidence 1회·충+형=2원인 vs 다층=1원인+convergence 진단·
컨텍스트 occurrence 비기여·polarity amplifier/극성 mitigator 기여 0·compound=
다른 risk_id 연결만·persistence=반복 횟수만·D-golden(시험 2 episode 같은 원인
1회 평가)·raw>1 보존+capped clamp. env r0.5.12 유지(suppression baseline diff 0·
전 프로필 지표 불변), RISK_SCORING_VERSION=risk-score-r1.0.0-shadow 분리, 가중치
전부 잠정(감수 질문 — exposure UNKNOWN 0.55는 랭킹 정책 가중·§5-1 상한 별도).
pytest 1977·ruff·mypy 0·전 baseline exact match. 다음: R1-b 표본 → R1-c 49항목
shadow scoring(+shadow_scoring scope 감수).

## R1-a 후속 보완 — 감수 26차 확정 5건(R1-b 착수 전) (2026-07-16)

①cause identity 계약 명시(관계 원자=target_object_signature 내장 canonical —
로직 불변, docstring+fixture 3종: 다른 대상=원인 2·다른 관계=원인 2·다층=원인 1)
②DENIED ranking 가중 0.15 제거 — exposure 축=rankable 가중(is_exposable 미통과
전부 0: DENIED·confirmed_required+UNKNOWN·conflict·vulnerability), 통과 후보만
1.0/0.55 ③structural_priority 신설(exposure 제외 구조 진단 — counterfactual 전용)
④compound=독립 exposable 효과군(다른 family+노출 가능+미흡수 — alias·supporting·
vuln 연결 제외, fixture 4상황) ⑤persistence=longest contiguous run(간헐 3회 0.0 ≠
연속 3개월 0.4, 연운이 같은 달 지지=기간 1+convergence). RISK_SCORING_VERSION
r1.0.1-shadow(env r0.5.12 불변). fixture 14종·pytest 1982·mypy 0·전 baseline
exact match. 다음: R1-b 표본 측정(경계 사례 목록은 REVIEW.md §13-1·데굴님 지정).

## R1-b — 표본 검증 차수(감수 27차 착수 슬라이스 1 + 표본 리포트, 2026-07-16)

착수 조건 2건: ①cause namespace 계약 검증기(target 내장 canonical/명시적 전역
사실만 — 미상 namespace는 cause_occurrence_table이 거부, polarity 진입 필터, 엔진
실후보 전수 통과) ②structural/rankable 완전 분리 — compound_family_links(
exposable_only False/True), structural_priority는 compound 축 제외, CONFIRMED↔
DENIED 전환 시 structural 완전 동일 fixture, 점수층 DENIED/NA 자체 방어.

persistence 경계: 연도 경계 연속(canonical month index)·상위 layer 직렬화 구분
(period-native trigger 게이트 — 세운 원인 12개월 복제=지속 0·occurrence 불변)·
lineage(계열 키) vs cause instance(기간 내) 구분 문서화.

표본 리포트 신설(scripts/risk_scoring_sample.py → doc/v2_2/RISK_SCORING_SAMPLE_
R1B.md 고정): 표본 7종·§9 필드 전체 출력·**예상 불변식 26개 전부 PASS**(감수
대상=절대 점수가 아니라 관계). RISK_SCORING_VERSION r1.0.2-shadow(env r0.5.12
불변). fixture 19종·pytest 1987·mypy 0·전 baseline exact match.
다음: R1-c 49항목 shadow scoring 전수(+포화 지표·프로필 비교·shadow_scoring
scope 감수 — 기존 scope 해제 금지).

## R1-c0 — 점수 의미론 고정 슬라이스(감수 28차, 2026-07-16)

canonical 식별≠occurrence 적격(데굴님 필수 7건): ①의미 registry — relation/
ten_god=CAUSE·void=조건부(단독 원인 금지)·no_void=게이트(기여 0)·stage=작동/확신
보조(row 금지)·polarity=증폭·미상 fail-closed. CAUSE 동반 source만 occurrence
재료 ②persistence=cause lineage(연결 episode 서명+CAUSE 원자 집합 — 원인 교체형
연속=run 1, 효과 연속은 effect_contiguous_runs 진단 분리, 무관 episode 추가=전
점수 byte 불변) ③compound effect identity — 같은 episode·같은 kind의 교차 family
복제=0(MOV·LEG·FIN 병렬 표현), episode-free 쌍은 riskFamily 저작 소관(감수 질문)
④confidence 분리 — structural(후보 저장)/context_confidence(진단 함수), 상호
불간섭 fixture ⑤scoring_config_hash+cause_semantics_hash(잠정 가중 변경=감수
자동 강등 재료). RISK_SCORING_VERSION r1.0.3-shadow(env r0.5.12 불변). fixture
26종·표본 불변식 27 PASS·pytest 1994·mypy 0·전 baseline exact match.
다음: R1-c1(49항목 전수 — cohort 6군 분리·structural/rankable 분포·포화·단조성)
→ R1-c2(가중 확정·shadow_scoring scope 승격).

## R1-c0 후속 — 감수 29차 확정 6건(R1-c1 착수 전) (2026-07-16)

①persistence=**개별 cause lineage**(보조 원인 증감 무영향 — {A}→{A,B}→{A}=A run
3, 묶음 연속은 trigger_bundle_contiguous_runs 진단 분리) ②normalized effect role
registry(49항목 전수 매핑 — riskFamily는 교차 통합 1건뿐이라 부족, scoring 계층
잠정+cause_semantics_hash 포함, 사전 필드 편입=감수 질문) ③compound=서로 다른
role 개수(같은 role=복제/폭 — R2 breadth 소관, episode 수 비증가, episode-free
미해결=fail-closed 0+unresolved 진단) ④targeted void fail-closed fixture(전역
상태 계약 명문화) ⑤context_axes 축별 confidence(요구 축만 평가) ⑥r1.0.4-shadow·
semantics v3(env r0.5.12 불변). fixture 28종·표본 불변식 31 PASS·pytest 1996·
mypy 0·전 baseline exact match. 다음: R1-c1(49항목 전수 — cohort 6군·structural/
rankable 분포 분리·포화·단조성 6종·추가 진단 4종) → R1-c2(가중 확정·shadow_
scoring scope 승격).

## R1-c1 — 49항목 전수 shadow scoring 측정(감수 30차, 2026-07-16)

착수 조건: compound=연결 effect graph만(무연결 co-period 0 fixture)·is_question_
target 제외 fixture·이중 모집단(전체 구조 코퍼스+A/B/C/D overlay)·단조성 8종.
결과(고정본 RISK_SCORING_SURVEY_R1C1.md): **포화 없음**(raw>1 1~4%·축 cap 미미),
상위 10% 축 구성 건강(구조=occurrence·persistence 주도 → C=exposure·compound
상승 — 컨텍스트가 상위 결정), cohort 분리 유효(비rankable 739 제외). **감수 판단
지점**: 코퍼스 98% episode-free → unresolved effect 연결이 상위 10% 전원 —
compound 가중 확정은 R1-c2(사전 role 편입+episode 시나리오 재측정) 후로 보류.
persistence lineage 1,061·다기간 793. 모집단 1≡overlay A 상호 검증. fixture
30종·pytest 1998·mypy 0(521파일)·전 baseline exact match.
다음: R1-c2 — normalizedEffectRole 사전 SSOT 편입(+lint·해시)·episode 시나리오
compound 재측정·가중 확정·shadow_scoring scope 감수.

## R1-c2 — 보고 정정·normalizedEffectRole 사전 SSOT(해시 v9)·민감도/ablation
(감수 31차, 가중 확정 대기, 2026-07-16)

①R1-c1 보고 정정 5건: count/rate 분리·exposure 범주값 vs clamp 분리·'병적 상한
집중 없음' 표현+동점/다양성/p95/p99·가중 기여도(발견: 구조 상위=persistence
+0.541이 곱항 +0.169의 3배)·net_priority_raw(C군 raw<0 64.8%=protection 감점).
②role SSOT: 사전 필드 신설+49항목 저작+lint(enum 43종·kind 혼동 금지)+**해시
v9**(shadow_scoring scope 신설 — role 변경=해당 scope만 강등)+reviewPendingScopes
(shadow_structure 49/49 유지·shadow_scoring 0/49 대기)+v9 재스탬프 49(본문 불변)
+코드 registry 삭제. ③측정: compound 민감도(0→overlap 4/10·0.15→9/10 — 0.25는
작지 않음, 0.10~0.15 완만)·exposure ablation(전 구간 10/10 — 상위 과대 지배
없음)·pairwise golden 3종 PASS(구조 우위·근접 구조선 현실 우선). E1~E6=fixture
고정. 게이트: pytest 1998·mypy 0(521)·ruff clean·baseline 지표 diff 0(메타 v9
재기록)·manifest 일치. **감수 대기**: compound 증분(0.15 권고)·UNKNOWN 0.55·
persistence 주도 허용·capped=1 단일 항목·ByContext·shadow_scoring 49 스탬프.

## R1-c2b — 점수 공식 modifier 전환·taxonomy 정리·ByContext(감수 32차, 2026-07-16)

공식 개정(r1.1.0-shadow): raw = exposure × (occ×impact) × (1+per+cmp) × (1−prot)
— 지속·복합·보호를 기본 위험의 modifier로(독립 가산 폐지). 3대 문제 전면 해소:
persistence 주도(기여 base의 1/4로)·protection 음수 64.8%→0·CAR capped 3건→0
(자연 해소 — persistence additive가 원인). compound 증분 0.25 기각→0.10 잠정
(민감도: 0.10~0.15 안정). role taxonomy 43→40종(병합 3건: result_wait_delay·
liability_obligation — 감수 질문)+audit(singleton 32·공유 8·교차 3종·shared-cause
same-role 0/diff 68). ByContext 저작(TRL 치료≠회복)+엔진 branch 해소+lint.
pairwise·span 비교·protection pairwise 전부 PASS·고정본 갱신. fixture 32종·
pytest 2000·mypy 0·baseline 지표 diff 0·manifest 일치(scoring scope 0/49 유지).
다음: R1-c3 — singleton 32 심사·compound/span/UNKNOWN 확정·shadow_scoring 49
스탬프(감수) → R2.

## R1-c3 — 최종 확정·shadow_scoring 49/49 스탬프(감수 33차, 2026-07-16)

확정: modifier 공식·span 5·compound 0.10(cap 0.30)·result_wait_delay·TRL
ByContext·protection 공식 승인 / liability 병합 기각→**분리**(compliance_
obligation·guarantee_or_contractual_liability — 병존 compound 정당). protection
**cap 0.70** 하드 가드(+존재 삭제 금지 fixture)·additive 상한 회귀 golden.
**UNKNOWN 0.55 확정**(국소 민감도 기준 전부 충족: 0.50↔0.60 top25 100%/92%·
crossing 0·추월 0). shared-cause 16조합 표(최다 compliance↔dispute 13× — 분리
정당성 실증)·ByContext 자동 탐색(추가 저작 불요). **shadow_scoring 49/49 스탬프**
+ manifest에 scoring version·config/semantics hash 병기(변경=자동 재감수 신호).
r1.1.1-shadow. fixture 34종·pytest 2002·mypy 0·전 baseline 지표 diff 0·restamp
불변 49. **R1 완료 — 다음: R2(episode 병합·risk budget·대표 선택).**

## R2-a — 선별 계층 인프라(episode 병합·대표·budget·portfolio·recovery)
(감수 34차 착수, 2026-07-16)

manifest 선행 고정(REVIEW.md §20 — 데굴님 episode key 수정 반영: **risk_id·domain
제외**, 3-identity 분리). ①RiskEpisode 개편(§8 구조 — R0 자리표시 키 폐기,
member/representative/supporting/background·cause·role·domains 속성) + Recovery
Window 확장(earliest/stable/confidence/reasons) ②risk_selection.py 신설(shadow
전용): build_episodes(explicit id 우선·fallback=대상+원인+family+기간 연속
fail-closed), 대표 선택(exposable+rankable>0+비취약+비흡수, specificity→score→
confidence→id — 점수가 primary를 못 밀어냄), RiskBudgetPolicy(hard_min 0·
soft_target·hard_max, dedup: role→shared cause→budget→도메인 soft tie-break·누락
기록), portfolio_diagnostics(unique cause·role·episode — 후보 합산 금지),
attach_recovery_windows(lineage 지평 내 종료 시만·점수/순위 byte 불변)
③RISK_SELECTION_VERSION=risk-select-r2.0.0-shadow + selection_policy_hash
manifest 병기(scope shadow_selection 0/49 — 스탬프는 측정·감수 후). §13 필수
fixture 10종 전부 통과(병합 4·대표 2·budget 3·recovery 1). pytest 2012·mypy
0(523)·전 baseline 불변. 다음: R2-b — 전수 episode 측정(코퍼스·프로필 overlay
선별 밀도·대표 분포·budget 시뮬레이션) → R2-c 감수·스탬프.

## R2-a 후속 — 감수 35차 확정 6건(R2-b 착수 전) (2026-07-16)

①축 namespace+reality_episode_id alias(컨텍스트 5종·엔진 전파·상충 fail-closed·
병합 우선순위 reality→explicit→fallback) ②대표 정렬 ownership 선두(잠정 도메인
소유 축 매핑 — 감수 질문·policy hash) ③budget soft tie-break(같은 role·cause의
다른 현실 episode 제거 금지·적격≤max 전부 선택·누락 taxonomy 3종) ④fallback
transitive bridge 차단(완전 일치 그룹) ⑤recovery right-censoring(quiet 2기간·
다중 cause 지속=earliest만·censored 기록) ⑥episode confidence 팽창 방지 fixture.
r2.0.1-shadow. fixture 19종·pytest 2021·mypy 0·baseline 불변.
다음: R2-b 전수 episode 측정(§12 지표 — 형성·병합 품질·대표·budget 시뮬레이션·
recovery·portfolio) → R2-c 감수·shadow_selection 스탬프.

## R1-T/R2-a2 — 교운기 temporal modifier·R2-a 잔여 보완(감수 36차, 2026-07-16)

교운기: 이벤트 엔진 kernel SSOT 공유(복제 0·MIN 0.05 동일)·transitionSensitivity
사전 필드(v10·vulnerability=none lint·49항목 잠정 저작)·timed_base 곱형 공식
(r1.2.0-shadow — None 입력=기존 byte 불변)·불변식 fixture 7종(부활 차단·persistence
비개입·ownership 유지·recovery 비생성)·overlay 실측(교운일 +27.0%/±1년 +9.9%/
±2년 +3.6% — 감쇠 정상, 교운일 포화 4건 감수 확인 대상)·shadow_scoring 49/49
R1-T 재스탬프. R2-a 잔여: alias CONFLICT 상태 보존(fallback 재진입 금지)·novelty
near-tie(ε=0.02) 전용·earliest relief=최고 기여 cause 기준·context confidence=
대표 충족도×identity 품질·ownership 사전 계약은 R2-c 전(adapter 유지). r2.0.2-
shadow. pytest 2031·mypy 0·baseline diff 0. 다음: R2-b 전수(교운 overlay 포함).

## 감수 37차 조건 차수 — scope 절차 교정·reality type·anchor-bucket (2026-07-16)

절차 교정: 잠정 temporal 계수의 shadow_scoring 재스탬프를 **shadow_temporal
scope 신설**로 교정(shadow_scoring="R1" 복원·temporal 0/49 pending·
transition_policy_hash 분리·manifest 병기). reality_episode_type 7종 enum —
같은 alias라도 type 비호환·enum 밖 값이면 CONFLICT(엔진+병합 이중 감지, 오부여
alias 오병합 차단). near-tie를 **anchor-bucket**으로 재구현(anchor 고정 bucket
≤ε=0.02 내부만 novelty 순서 — 비추이적 연쇄 확장 금지, 입력 permutation 전수
byte-identical fixture). earliest relief는 dominant 동률(strength≥max−ε) 집합
**전체** 완화 필요(r2.0.3-shadow). temporal 감수 재료: 교운일 capped 4건 개별
(LEG_COMPLIANCE 3 — bonus 기여 미미 / MOV_CONTRACT_SETBACK 1 — +0.500)·top10
신규 4건 전부 MOV_CONTRACT_SETBACK(high)·MAX_BONUS 0.30/0.40/0.50 민감도
(16.2/21.6/27.0% — 포화 3/3/4)·sensitivity 저작 audit(high 8·medium 10 표).
fixture +7(selection 36종). pytest 2037·ruff·mypy 0(523)·suppression diff 0·
profile baseline 값 byte 동일(meta만)·manifest 일치·survey 재생성 byte 동일.
REVIEW.md §22. 다음: R2-b 전수 측정(교운 overlay·ownership proxy audit 포함).

## 감수 38차 preflight + R2-b 전수 선별 측정 (2026-07-16)

preflight 4건: MOV_CONTRACT_SETBACK high→medium(과정 차질 — 무산 단정
prohibited, 근거 note 사전 명문화)·reality identity 3상태(resolved 1.0/partial
0.85 잠정/conflict 0 — partial=병합 유지·완전 identity 금지, episode 필드
신설)·선별 정렬 raw 전환(capped=표시 전용 — cap 동점 뭉침 금지)·ε 경계
round(9) 정규화(0.020 경계 float-safe fixture). r2.0.4-shadow, fixture +3.
R2-b 전수 측정(risk_selection_survey.py — RISK_SELECTION_SURVEY_R2B.md 고정,
byte-identical): 프로필 A~D+E_reality_linked(reality 13·resolved 10·partial
3·다도메인 6 — 교차 병합 실측 최초)·episode 형성/대표/budget/recovery/
portfolio/under-merge 진단·교운 overlay matrix(medium 적용안 vs MOV high
비교안 × MB 0.20/0.30). 판정 5기준 전 변형·전 프로필 PASS: episode top10
overlap 9~10/10(비교안 high는 C-T 9/10 — MOV 독점 진입, medium이 제거)·
ownership override 0·low 신규 진입 0·cap 유발 동점 0. MB 0.20/0.30 확정·
sensitivity 저작·shadow_temporal 스탬프는 데굴님 감수 대기. pytest 2040·
ruff·mypy 0(524)·baseline 값 불변·manifest 일치. REVIEW.md §23.
다음: R2-c(primaryOwnership 사전 편입 + shadow_selection·temporal 감수).

## 감수 39차 — temporal 확정·49/49 스탬프·R2-c ownership SSOT (2026-07-16)

MAX_BONUS **0.20 확정**(r1.2.1-shadow)·high 재판정: REL_PARTNER_READJUST
high→medium(재조정 과정 부담 — 감수 medium 기준 해당), 6종 high 확정(근거
note 저작 + manifest 근거표 병기, 최종 high 6·medium 12·low 26·none 5).
**shadow_temporal 49/49 스탬프**(R1-T — structure·scoring·temporal 49/
selection 0). R2-c: RiskPrimaryOwnership 사전 계약 49항목 저작(axis 6종·
none 명시 14종·도메인≠축)+lint 4종+selection scope 해시 편입(변경=selection만
pending), _ownership_rank를 사전 계약 소비로 교체(명시 local episode 직접
매칭만 — **partial alias≠ownership 가드**+fixture), ε 해시 구조화(digits 9·
near_tie/dominant 0.02·"<="), r2.1.0-shadow. proxy audit: match 34·mismatch
1(HLT 차량=mobility 교차 소유 의도)·n/a 14, behavioral 불일치 0·대표 변화 0
(안전 교체 실증). 재측정 판정 전 PASS 유지·고정본 2종 갱신(byte-identical).
pytest 2041·ruff·mypy 0(524)·baseline 값 불변·manifest 일치. REVIEW.md §24.
다음: shadow_selection 스탬프 감수(ε·identity quality·quiet span·relief
confidence·budget 정책·ownership 계약 49건 확정).

## 감수 40차 — temporal high 4 최종·recovery 교정·shadow_selection 49/49 (2026-07-16)

CAR_EXIT_PRESSURE·MOV_RELOCATION_PRESSURE high→medium(압박·검토≠실제 상태
전환 — REL 동일 기준, note 저작·R1-T2 재스탬프·r1.2.2-shadow). 최종 high 4·
medium 14·low 26·none 5. delta: candidate 상승 9.4→8.3%·강등 2종 top10 신규
소멸·판정 전 PASS. recovery confidence를 고정값에서 **cap×episode.context_
confidence**로(earliest 0.20·stable 0.40 — identity 약한 episode 과대 확신
제거), quiet span **월 단위 계약**(month-native만 stable — 재측정에서 stable
95~115→6~7건: 연 단위 '2기간=2년' 오해석 전량 차단). 질문 유형별 budget 표
고정(5유형·hard_min 0·미상 fail-closed)+axis none 대표 자격 불변식. fixture
+4(selection 38종). **shadow_selection 49/49 스탬프(R2-c)** — 4 scope 전부
49/49(모드 off 유지). r2.2.0-shadow. pytest 2045·ruff·mypy 0(524)·baseline
값 불변·manifest 일치·고정본 2종 갱신. REVIEW.md §25. 다음: R3 노출 계층.

## R3-a — 노출 계층 구현(감수 41차 착수 승인, 2026-07-16)

manifest 선행 고정(REVIEW.md §26 — 8건: 밴드/level 분리·상한 매트릭스·
critical=독립 canonical cause≥2(층 반복≠2)·R2 불변식·phrase mode 4종·claim
코드·SHADOW 비주입·token guard P0 보존) 후 risk_presentation.py 구현: 밴드
잠정(0.40/0.25/0.12)·cap 매트릭스(confirmed_required+UNKNOWN=none·incident+
UNKNOWN≤watch·pressure≤warning·vuln≤advisory)·critical gate(CONFIRMED+독립
cause 2+identity resolved/explicit+conf≥0.5)·warning-first stable sort(R2
순서 보존·NONE도 payload 유지)·claim payload(전역 7+4 코드·항목 결합·raw/
risk_id/atom 비노출·scoreBand·confidenceBand)·token guard(P0~P3 — P0 절대
보존·episode 삭제 금지)·presentation_policy_hash·shadow_presentation 0/49·
r3.0.0-shadow. fixture 11종(§19 전 항목 — SHADOW 미배선 grep 강제 포함).
§25 stable 건수 표기 프로필별 정정(A 95→6·B 100→6·C 92→7·D 115→6·E 87→6).
pytest 2056·ruff·mypy 0(526)·baseline 불변·manifest 일치. 다음: R3-b 전수
측정(level 분포·cap 강등 사유·critical 발생률·token 압축) → 밴드·경계 감수
→ shadow_presentation 스탬프.

## R3-a preflight + R3-b 전수 측정(감수 42차, 2026-07-16)

preflight 6건: ①item claimCeiling·exposurePolicy UNKNOWN ceiling 실적용
(min 결합·conditional_warning 정규화·fail-closed) ②critical_eligible_cause
분리(대표+독립 exposable primary effect만 — supporting·partial 교차 제외)
③audit/LLM payload 분리 — **NONE은 LLM 비노출**(omission reason 4종 기록)
④claim 충돌 prohibited 우선·미등록 fail-closed ⑤token guard: 전역 코드
최상단 1회·token 추정·P0_COMPACT fallback(overflow 표시·episode 삭제 없음)
⑥OFF vs SHADOW 최종 직렬화 byte-identical 통합 fixture + numeric band=
capped 계약. r3.0.1-shadow, fixture 16+1종. R3-b 전수(risk_presentation_
survey.py·고정본): critical 전 프로필 0(정상), 선택 후 warning 4~14·watch
12~21·advisory 4~9, 강등 primary=EXPOSURE_POLICY_CEILING·ITEM_CLAIM_CEILING
(항목 ceiling 실작동), token 512=compact 경계·1024=full·보존 30/30, 경계
민감도 warning 축만 실질 변별(critical·conf 축은 후보 부재로 변별 불가 —
확정은 critical 발생 코퍼스 후). pytest 2062·ruff·mypy 0(527)·baseline
불변·manifest 일치. REVIEW.md §26-2. 다음: 밴드·하한·token 기본값 감수 →
shadow_presentation 스탬프 → EXPOSE 게이트 설계.

## 감수 43차 — 확정값 반영·estimator 교체·shadow_presentation 49/49 (2026-07-16)

확정: warning 0.25·conf 0.75(보수 정책값 — validation pending 기록)·budget
1024/512(256=EXPOSE 미지원)·표시명(참고 신호/관찰 필요/주의 필요/우선 점검
필요). 수정 2건: ①estimator — ceil(chars/3) 기각 → tokenizer adapter 주입
1순위 + 보수 다국어 fallback(ascii/4+비ascii 1:1×1.10+8, 한국어 과소 추정
불허) ②token fail-closed — 512 미만/compact 초과=riskEpisodes 비주입+
exposureSuppressedReason(overflow 주입 경로 제거). 재측정: 256=비주입·512=
compact 30/30(p50 272 tokens)·1024=P1~P2·2048=full. **shadow_presentation
49/49 스탬프 — 5 scope 전부 49/49**(모드 off 유지). r3.1.0-shadow. fixture
18종. pytest 2064·ruff·mypy 0(527)·baseline 값 불변·manifest 일치. REVIEW.md
§26-3. 다음: EXPOSE 게이트 설계(critical 하향 게이트·tokenizer adapter·R5
연동 — manifest 선행).

## R4-a — EXPOSE 게이트(감수 44차 착수 승인, 2026-07-16)

manifest 선행(REVIEW.md §27 — 8건: tokenizer 필수·전체 prompt headroom·
episode/token budget 분리·computed/exposed 분리·critical 하향·단일
fail-closed 게이트·전역 pipeline scope·canary). risk_exposure.py:
tokenCountMode 3분류(heuristic=EXPOSE 금지), available/effective budget
공식(<512 비주입), exposure_token_budget_for(768/1024 — R2 개수 예산과
분리), apply_exposure_levels(critical→warning 하향·감사 computed 보존·LLM
직렬화에서 사유 필드 제거), evaluate_risk_exposure_gate(reason codes 10종·
관측값), RiskEngineMode.EXPOSE_CANARY 추가, critical_validation_state 분리
(presentation policy hash에서 이동 — 상태 변화≠49항목 강등),
expose_policy_hash·manifest expose_pipeline{reviewed:false} 병기.
r4.0.0-gated. fixture 10종(§13). 주입 배선 없음(게이트 함수만 — off 기본
불변). pytest 2074·ruff·mypy 0(529)·baseline 불변·manifest 일치.
다음: R5 파이프라인 배선(주입 지점·tokenizer adapter 실물·canary allowlist)
감수 후 EXPOSE_CANARY.

## R5-a — EXPOSE 배선 전 계층(감수 45차 착수 승인, 2026-07-16)

§28 manifest 선행(EXPOSE_CANARY 개시 전 필수 4건 — 2차 계수·모델 일치·
suppressed guard·출력 claim audit). 게이트 확장(r4.0.1-gated): kill switch
최앞·EXPOSE_PIPELINE_NOT_REVIEWED·TOKENIZER_MODEL_MISMATCH·primary/all
reasons(정적 일괄 수집·순서 policy hash)·riskExposurePolicy enum(전 유형
ALLOW_IMPLICIT·미등록 DENY)·혼합 기간 필터(episode ∩ 미래 범위)·critical
state fail-closed(validated 명시 전 하향). RiskPromptBlock(frozen)+
finalize_risk_prompt_block(최종 prompt 재계수→재압축→FINAL_PROMPT_TOKEN_
OVERFLOW)·RISK_EXPOSURE_GUARD_BLOCK(EXPOSE 전용 — apps 미참조 grep 강제)·
risk_claim_audit(결정적 사후 검사 — ALLOW/REVISE_REQUIRED). fixture 16종.
pytest 2080·ruff·mypy 0(530)·baseline 불변·manifest 일치. REVIEW.md §28-1.
다음: R5-b 배선(chat 주입 지점·tokenizer adapter 실물·canary allowlist·
audit 재생성 흐름·통합 fixture) → expose_pipeline reviewed 감수 →
r4.1.0-canary.

## R5-b — EXPOSE 실배선(감수 46차 착수 승인, 2026-07-16)

완료 조건 반영: FULL(=P2) 우선 압축 순서·미래 필터의 감사 records 전량
보존(OUTSIDE_FUTURE_SCOPE 표시·LLM만 필터·recovery 미래≠재노출)·
RiskPromptBlock content_hash+verify_risk_block_integrity·instruction/
suppressed guard 분리(둘 다 EXPOSE 전용·token 계수 대상)·episode별
claim audit(audit_risk_sections — 전역 출현 오인 차단+전체 답변 병행)·
재작성 상태기(REVISE 1회→REGENERATE_WITHOUT_RISK→BLOCK)·claim audit
버전/해시(expose_policy_hash 포함)·canary 정책(초기 3유형·내부 subject
ID allowlist 기본 거부·kill switch env). chat_service 배선: EXPOSE 계열
전용 분기+risk_exposure_service(현 단계=reviewed:false·adapter 부재 →
전부 비주입·suppressed guard만). 통합 fixture 8종: **OFF/SHADOW 실제
chat 최종 prompt byte-identical**·canary 차등·kill switch·재작성·checksum.
pytest 2088·ruff·mypy 0(532)·baseline 불변·manifest 일치. REVIEW.md §28-2.
canary 개시 잔여: tokenizer adapter 실물·질문 매핑 감수·출력 envelope·
재호출 배선·reviewed=true 전환(r4.1.0-canary).

## 감수 47차 — BYPASS/SUPPRESSED/INJECTED 분리 (2026-07-16)

핵심 교정: 비대상 요청(정적 사유 — canary 비허용·pipeline 미감수·tokenizer
부재 등)은 guard조차 없이 **prompt 한 바이트도 불변**(BYPASS — 진단 로그만),
자격 있는 요청의 런타임 실패만 suppressed guard(SUPPRESSED), 실주입은
INJECTED 단일 경로. reason→disposition 매핑 policy hash 편입. §2 회귀
fixture 4종(비허용 canary=chat 실측 byte-identical 포함). FULL 단일
명칭(P2 별칭 제거)·wrap_risk_block(BEGIN/END marker)+단일 삽입 검증(중복
=실패)·RISK_EXPOSE_PIPELINE_REVIEWED config(기본 False). pytest 2090·
ruff·mypy 0(532)·baseline 불변·manifest 일치. REVIEW.md §28-3.

## 감수 48차 — SSOT 분리·integrity 재조립·registry·envelope·FP/FN (2026-07-16)

decision reason 스키마 정본화(BYPASS≠suppression·하위 호환 별칭)·감수 SSOT
분리(RISK_EXPOSURE_RUNTIME_ENABLED=활성화만, manifest reviewed+expose_
policy_hash **런타임 실비교** — 한쪽만 true=BYPASS fixture 2종)·integrity
실패=SUPPRESSED 강등 계약(RISK_BLOCK_INTEGRITY_ERROR — instruction 잔존
금지·전체 재조립)·tokenizer adapter registry 골격(미등록=BYPASS·heuristic
등록 금지·fallback 재해소 계약)·risk_guidance envelope 불변식 검증기·claim
audit r5.1.0(부정문 예외 5표지+우회 단정 패턴 — FP/FN 코퍼스 fixture).
pytest 2096·ruff·mypy 0(533)·baseline 불변·manifest 일치. REVIEW.md §28-4.
잔여: 질문 파서 매핑·재작성 실배선·provider 직전 검증·renderer 재감사·
expose_pipeline 감수 → r4.1.0-canary.

## 감수 49차 — snapshot·재조립 상한·인터페이스·누락 정책·절 부정문 (2026-07-16)

별칭=정본 복사만(불일치 0 fixture)·ManifestSnapshot(단일 read·schema 검증·
snapshot_hash 관측 — 혼합 상태 차단)·재조립 1회 상한+SUPPRESSED_GUARD_
TOKEN_OVERFLOW→RISK_SAFE_RESPONSE_REQUIRED(조용한 원 prompt 호출 경로
없음)·TokenCounter 인터페이스(ProviderRequest 전체 계수·count_request
정본)·warning 이상 출력 필수(MISSING_REQUIRED→REVISE·watch/advisory 생략
허용)+envelope schema(미지 필드·빈 key/text·level 정확 일치)·절 단위
부정문(r5.2.0 — 25자 창 기각·역접 경계·이중 부정 위반 편입·필수 코퍼스
4종). fixture +6(통합 28종). pytest 2102·ruff·mypy 0(533)·baseline 불변·
manifest 일치. REVIEW.md §28-5. 잔여: 질문 파서 매핑→adapter shadow 등록→
envelope 배선→재작성 실배선→provider 검증→renderer 감사→감수→canary.

## 감수 50차 — 파서 SSOT 매핑·safe response 순서·validation 상태기 (2026-07-16)

risk_question_mapping 신설(IntentJson 정본만 — 미등록 유형·TIMELESS·
time_range 부재·비단독 subject=fail-closed None→BYPASS, chat이 intent
전달)·plan_safe_response(재생성 1회→감사→전달/fallback→BLOCK 고정)·strict
manifest schema+canonical snapshot hash·adapter 검증 상태기(VALIDATED만
EXPOSE 해소·등록≠검증)·envelope 부분수열 검증+presence 계약(None/빈 배열)
+episode_key 비노출 감사·audit evidence(span·절·negation)+확률 가장 단정
패턴(r5.3.0). fixture +5(통합 33종). pytest 2107·ruff·mypy 0(534)·baseline
불변·manifest 일치. REVIEW.md §28-6. 잔여: adapter 실물 shadow 등록·output
envelope provider 강제·재작성 실배선·provider 직전 검증·renderer 감사 배선
→ expose_pipeline 감수 → canary 전환(별도 커밋).

## 감수 51차 — 매핑 정밀화·validation policy 선행 고정·fallback hash (2026-07-16)

착수 전 계약 4건: A.매핑 정밀화(DOMAIN_ANALYSIS=실질 도메인 정확 1개·
specific_event=event_key 해소 필수·시간 regex 재해석 0 불변식) B.adapter
승격 기준 선행 고정(validation key·표본 10형·과소 계산 불허·reported 기준
— adapter_validation_policy_hash manifest 병기) C.envelope 순서 SSOT=최종
llmRiskEpisodes(필터·하향·정렬 후) D.safe fallback template 정책화(자체
audit ALLOW·expose hash 편입 — 문구 변경=pending). 보완: key 누출 확장
(prefix·내부 enum·internal_ids)·evidence 로그 정책(일반=clause_hash/길이·
원문=감수 표본 전용). fixture +6(통합 39종). pytest 2113·ruff·mypy 0(534)·
baseline 불변·manifest 일치. REVIEW.md §28-7. 잔여: adapter 실물 shadow
등록→envelope provider 강제→재작성 실배선→provider 검증→renderer 감사→
감수→canary(별도 커밋).

## 감수 52차 — adapter manifest SSOT·order fingerprint·output schema·HMAC (2026-07-16)

매핑 보완(도메인 dedup fixture·EventKey enum 근거 완료·boundary 보정 금지)·
adapter manifest SSOT(resolve_expose_counter — registry 자체 선언 불가·
manifest 항목 대조, drift 1건=SUSPENDED, 표본 30·overcount 관측)·order
fingerprint(llmEpisodeOrderHash — 잘못된 배열=EPISODE_ORDER_SOURCE_
MISMATCH)·fallback 문구 교정(r1.1.0 — 시스템 실패 노출 제거)·strict 정책
구간(expose_pipeline 미지 필드=실패)·HMAC clause hash(keyed 16자·운영
secret 교체 계약)·output schema 3상태(INJECTED 전용 build_risk_output_
schema — SUPPRESSED에 risk_guidance 미요구). fixture +7(통합 46종).
pytest 2120·ruff·mypy 0(534)·baseline 불변·manifest 일치. REVIEW.md §28-8.
잔여: adapter 실물 shadow 등록·계수 대조→schema 실배선→재작성 배선→
provider 검증→renderer 감사→감수→canary(별도 커밋).

## 감수 53차 — adapter 대조 확장·전역 suspension·HMAC 차단·EventKey hash (2026-07-16)

preflight 5건: ①resolve_expose_counter 대조 키 4종+validationPolicyHash
(현행 일치)+validationCorpusHash(존재) — 불일치=BYPASS ②전역 suspension
공유 파일(atomic·단방향·자동 복구 금지·관측 3필드 — 다중 worker 즉시
적용) ③운영 개발 HMAC 키 구조적 차단(AUDIT_HMAC_KEY_INVALID BYPASS)
④event_key_enum_hash expose hash 편입(enum 추가=자동 pending)
⑤episodeKey P0 노출(envelope 대응·renderer 제거)+order hash 보강(key+
level+required)+output schema maxItems=min(hard_max, len)·minItems=warning
수+strict 확장(critical_validation_state·validatedTokenCounters 미지 필드
실패). pytest 2120·ruff·mypy 0(534)·baseline 불변·manifest 일치.
REVIEW.md §28-9. 다음: adapter 실물 shadow 등록(30표본)→schema 실배선→
재작성 배선→provider 검증→renderer 감사→감수→canary(별도 커밋).

## 감수 54차 — suspension 동시성·오류 BYPASS·opaque guidanceRef (2026-07-16)

flock read-modify-write(+fsync·dir fsync — 동시 writer 유실 차단 fixture)·
suspension을 validation identity hash 기준 기록(옛 identity 영구 거부·
복구=새 identity 감수)·경로 var/risk_state(gitignore)·request id HMAC·
배포 불변식(single host 전제·다중 호스트=공유 저장소) 명시. 저장소 손상=
불가용→전부 BYPASS(fixture). **opaque guidanceRef**: LLM payload=rg1…만
(canonical episodeKey 제거 — guidanceRefMap은 감사 전용·직렬화 제외),
validator/schema guidance_ref 전환, order fingerprint는 canonical
identity 유지(같은 ref 배열·다른 구성=상이 hash). fixture +4(통합 50종).
pytest 2124·ruff·mypy 0(534)·baseline 불변·manifest 일치. REVIEW.md
§28-10. 다음: adapter 실물 shadow 등록(30표본·artifact hash) 착수 조건
충족.

## 감수 55차 — identity corpus 포함·전용 lock·rg 누출·요청 결속 (2026-07-16)

suspension identity를 감수 identity와 동일 구성으로(+countMode·corpusHash
— corpus 재감수=새 identity 복구 계약 정합, manifest 대조도 corpus 일치·
countMode 일치 강화)·전용 lock 파일 계약 fixture(+in-process mutex)·
INTERNAL_GUIDANCE_REF_LEAKED(한글 인접 rg 검출+발급 ref 대조). 병행:
persistence 쓰기 실패=전역 marker→전부 BYPASS(+로컬 flag fallback)·
GuidanceReferenceContext(요청 단위 불변 snapshot — 전 과정 동일 객체)·
topology 검증(미지원 조합=BYPASS). fixture +6(통합 56종). pytest 2130·
ruff·mypy 0(534)·baseline 불변·manifest 일치. REVIEW.md §28-11.
다음: adapter 실물 shadow 등록(30표본·§11 보고) 착수 조건 충족.

## 감수 56차 — tombstone·Unicode 누출·topology 자격 + 실물 adapter 30표본 합격 (2026-07-16)

suspension tombstone(append-only ledger — state 삭제로 부활 불가·손상=
BYPASS)·Unicode 변형 rg 누출 감사(NFKC+zero-width+casefold: RG2·ｒｇ２·
r​g2 검출)·canary topology 자격(DEPLOYMENT_TOPOLOGY_UNSUPPORTED —
파일 backend는 single_host_single_process만)·실제 subprocess crash·lock
회수 fixture·verify_guidance_context(GUIDANCE_CONTEXT_MISMATCH). 실물
Gemini adapter(PROVIDER_EXACT·countTokens) 30표본 실측: **30/30 delta 0·
undercount 0·rerouting recount 3/3·4 tier 대표 — 합격**, corpus hash
90e88fa2cafb3d24, artifact→manifest validatedTokenCounters(reviewed=
false 감수 후보) 결정적 생성. SHADOW_VALIDATING 유지(자동 승격 없음).
pytest 2136·ruff·mypy 0(536)·manifest 일치. REVIEW.md §28-12.

## 감수 57차 — rerouting 집계 분리·full digest·schema 분리·3상태 배선 (2026-07-17)

rerouting 3건이 30표본에 포함돼 있었음(native 27)을 확인·교정 — native
30(전부 최종 resolved=primary)+rerouting 별도 부록(최종 모델 기준 집계·
fallback은 감수 전 BYPASS). S09_runtime_hard_max(2/3/4)+
S10_oversized_stress(8/12/16) 명칭 정정. corpus hash 정본=full SHA-256
(short는 표시용). ledger·state 동일 lock(LOCK_SH) 스냅샷.
build_gemini_transport_schema 정본화(canonical 불약화·후처리 validator가
canonical 재검사·S05 출력 동일=schemaVersion 1 유지)+3상태 output
schema 배선(INJECTED만 RISK_ENABLED). 재실측: native 30/30 delta 0·
undercount 0·rerouting 3/3 delta 0 — 합격, corpus full hash
fc54e4bc…ebb3f9c. manifest 후보(reviewed=false) 갱신. pytest 2138·
ruff·mypy 0·manifest 일치. REVIEW.md §28-13. 잔여: context 전 경로 소비·
REVISE 실배선·renderer 후 최종 감사.

## 감수 58차 — corpus 3층 분리·full policy hash + adapter reviewed 승격 (2026-07-17)

fc54e4bc…는 supplementary 포함 hash였음을 확인 — nativeValidationCorpus
(30표본만)/supplementaryReroutingEvidence/validationArtifactHash 3층
분리, native hash 65db8eb9…7ee59b 재산출(재실측 합격: delta 전부 0).
policy hash full digest 전환, schema digest 2종 병기+변환 규칙 스냅샷
fixture, maxItems=min(hard_max,최종 episode 수) fixture. 감수 58차 §11
사전 승인 조건 충족 확인 후 _REVIEWED_COUNTER_CORPUS_HASHES 승격
(reviewed=true) — expose_pipeline.reviewed=false 등 3중 잠금 유지,
gemini-2.5-flash 미감수 BYPASS. pytest 2140·ruff·mypy 0·manifest 일치.
REVIEW.md §28-14. 다음: §12 실배선(context 전 경로·schema 강제·envelope
audit·REVISE/REGENERATE·provider 직전 검증·최종 감사·corpus 대조).

## 감수 59차 — INJECTED 실호출 파이프라인·runtime 상태 파생 (2026-07-17)

adapter reviewed 승격 승인 후속: derive_runtime_adapter_state(VALIDATED=
검증 결과 — artifact 재해시+manifest 7요소+suspension 전부 충족 시만,
stamp 함수 전용)·validationArtifactHash manifest 병기(생성기 재해시
검증). risk_llm_pipeline 신설: attempt별 독립 ProviderRequest·전체
재계수·preflight(모델 재해소·block integrity·context 결속)·REVISE 입력
최소화(내부 ID 금지)·REGENERATE=baseline+guard 완전 재조립(bytes 일치
fixture)·rerouting 판정(미감수=REBUILD_BYPASS)·renderer 후 최종 감사→
DELIVER/BLOCK만. 캐시 정책 명문화(explicit 미사용·비교는 전체 input).
fixture +6(71종). pytest 2146·ruff·mypy 0(537)·manifest 일치.
REVIEW.md §28-15. 잔여: chat_service 실연결·shape corpus 대조 배선·
expose_pipeline 감수 자료.

## 감수 60차 — 실행 context 결속·revision fallback 차단·shape 대조·36표본 (2026-07-17)

RiskExecutionContext(요청 단위 불변 — manifest snapshot 승계·suspension
만 attempt마다 최신), REVISION 직전 reroute 감지 시 위험 초안 미전송
(REGENERATE 직행 — 감수 모델도 게이트 재평가 전 금지), 구조적
request_shape_digest+REQUEST_SHAPE_NOT_REVIEWED(동적 본문 제외), terminal
3분리(DELIVER_GENERATED/DELIVER_SAFE_FALLBACK/BLOCK — fallback도 최종
감사 경유), attempt 관측 7필드, record_cache_observation(cached>0=
identity 차단). policy에 attempt shape 2형 추가(12형×3=36) → 직전 승격
무효(allowlist 비움) → 재실측 합격(36/36 delta 0·shape digest 7종) →
corpus b00716ee…902ce1 reviewed=false 후보 재제출. fixture +5(76종).
pytest 2151·ruff·mypy 0(537)·manifest 일치. REVIEW.md §28-16.

## 감수 61차 — corpus 승격·shape 이름·architecture freeze (2026-07-17)

corpus b00716ee…902ce1 승격(reviewed=true — adapter 감수 한정, 3중 잠금
유지), shape digest 7종에 안정 이름 결속(BYPASS_PLAIN~REVISION_1_
INJECTED — artifact 후처리, corpus hash 불변 검증). **1b52cc2 기준
pre-canary architecture freeze**: 동결 목록·P0/P1 변경 사유 고정, 차수별
미세 감수 중단 → 구현 커밋은 게이트 통과 시 진행, 10항 완료 후 통합
pre-canary 감수 1회 → 제한 canary → 관측 기반 수정. REVIEW.md §28-17.

## freeze 후 구현 1 — startup 배선·runtime 실값 공급 (2026-07-17)

(감수 61차 §10 방식 — 게이트 통과 구현 커밋, 개별 감수 없음)
risk_exposure_bootstrap 신설: bootstrap_risk_exposure(EXPOSE 전용 —
artifact corpus hash로 adapter 등록+stamp_runtime_adapter_state 파생,
OFF/SHADOW=no-op)·exposure_runtime_inputs(감수 adapter counter·
llm_config primary.context_limit(부재·0=BYPASS)·call_type 출력 예산·
reviewed shape digest 7종). main.py lifespan 연결(suppress).
chat_service EXPOSE 분기 model_context_limit=0 해제 — 실값 공급(기존
직렬화 추정치·시스템 예약 재사용). llm_config에 context_limit=1000000.
fixture +3(79종). pytest 2154·ruff·mypy 0(538)·manifest 일치·회귀 통과.
잔여(통합 감수 전): INJECTED 시 run_injected_risk_flow 소비(response
schema 실호출·renderer 연결)·rerouting 실배선·worker=1 실측 검증·kill
switch e2e·expose_pipeline 감수 자료.

## freeze 후 구현 2 — INJECTED 실호출 배선 (2026-07-17)

(감수 61차 §10 방식 — 게이트 통과 구현 커밋)
generate_structured(계수와 동일 build_gemini_request_body 본문으로
generateContent — 폴백 없음·실패=예외→flow 처리), bootstrap 확장:
build_risk_payload(risk_shadow→score(사전 baseImpact prior)→episodes→
presentation), run_exposed_reading(실행 context 1회 조립→실 구조화 호출→
envelope/claim 감사→REVISE/REGENERATE→renderer(_normalize_ganji_gloss)
후 최종 감사→종료 후 attempt별 counted vs provider 보고 대조
record_count_observation+record_cache_observation), 정적 bootstrap
reason 4종(TOPOLOGY_MISMATCH/ARTIFACT_INVALID/MANIFEST_MISMATCH/
ADAPTER_UNAVAILABLE)+worker>1 환경 신호 검증. chat_service: EXPOSE
분기에 payload 공급+INJECTED 시 flow 소비(DELIVER_*만 전달, BLOCK=위험
무관 일반 실패 문구), BYPASS/SUPPRESSED는 기존 generate_reading 경로
그대로. shadow 비주입 가드 allowed에 bootstrap 등재(EXPOSE 전용 근거
주석). pytest 2154·ruff·mypy 0(538)·manifest 일치.
잔여: rerouting 시 모델별 context limit 재해소·kill switch/rollback
e2e·worker=1 배포 preflight 문서·expose_pipeline 통합 감수 자료.

## freeze 후 구현 3 — kill switch/rollback e2e·worker 검증·통합 감수 자료 (2026-07-17)

kill switch e2e(전 조건 충족+switch=BYPASS)·rollback(off 전환=분기
미실행 byte 복귀)·worker>1 신호=TOPOLOGY_MISMATCH fixture 3종(통합
87종). 통합 pre-canary 감수 자료 doc/v2_2/RISK_EXPOSE_PRECANARY.md
작성(잠금 상태·경로 계약·canary 전 사람 확인 5항·관측 계획·알려진
한계). pytest 2157·ruff·mypy clean·manifest 일치.

## 통합 pre-canary 감수 반영 — 두 불변식 + reviewed=true (2026-07-17)

drift·cache 검사를 attempt 응답 직후·전달 판정 전으로 이동(위반=응답
폐기 DISCARDED→identity 차단→위험 없는 종결, fixture 2종 통과),
SUPPRESSED bytes-diff e2e fixture(=guard 한 블록·schema 불변), BLOCK
문구 중립화. **expose_pipeline.reviewed=true 전환**(§8 즉시 승인 조건
충족) — 실주입은 RUNTIME_ENABLED=False·MODE=off·dev HMAC 키가 계속
차단(fixture ①-b). canary 개시=사람 확인 5항 후 r4.1.0-canary 별도
커밋. pytest 2160·ruff·mypy 0(538)·manifest 일치. REVIEW.md §28-18.

## r4.1.0-canary 전환 준비 커밋 (2026-07-17 — 통합 감수 최종 승인)

RISK_EXPOSURE_VERSION=r4.1.0-canary(policy hash 재스탬프), 활성화 env
배선(모드·runtime·topology·HMAC_B64(32B+ 검증)·allowlist — 미설정·오타·
비정상=전부 잠금 유지 fixture), scripts/risk_canary_smoke.py(§9 점검),
.env.example 안내. pytest 2161·ruff·mypy 0(539)·manifest 일치.
활성화 자체=데굴님 운영 preflight(HMAC secret·worker=1 실측·allowlist)
후 환경변수 설정 — 코드 커밋으로는 아무것도 켜지지 않음.

## 베타 적용 — 위험 노출 expose 활성화 (2026-07-17 데굴님 결정)

운영 preflight 절차 생략(현 환경=테스트 상태) — 베타 테스터 전면 적용.
.env.risk(gitignore·dev.sh source·pytest 미접촉): mode=expose·runtime
=true·topology=single_host_single_process·테스트 HMAC 키(48B). 감수
게이트 완화 없음(요구값 충족 방식). smoke 7/7: bootstrap VALIDATED
(실 artifact·manifest 파생)·비대상 BYPASS byte 불변·대상 질문 감수 경로.
smoke 스크립트 expose 모드 지원 갱신. 문서에서 preflight 요구 절차
제거(PRECANARY §4=적용 상태 기록). 중단=.env.risk 삭제/mode=off.
pytest 전체 통과(격리 확인)·ruff·mypy clean.

## 테마사주(리포트) 배선 + P1 교정 2건 (2026-07-17 데굴님 지시)

**P1 교정(실서비스 INJECTED 차단 결함 — 배선 중 발견)**: ①shape digest의
output/tool schema hash를 내용→**구조 골격**(동적 enum·개수 상한 자리
표시자 치환)으로 — 요청별 episode 구성 차이로 corpus와 항상 불일치하던
문제 해소(구조 변화에는 여전히 반응, fixture) ②INJECTED prompt에
wrap_risk_block(BEGIN/END marker+checksum) 실적용 — flow preflight
integrity 검사와 정합(기존 주석 "canary 차수에서 교체" 잔여분).
harness S07/S09/S10/S11을 실요청과 동일 구조(wrapped block+transport
schema)로 갱신 → 재실측 39표본 delta 전부 0·합격, 새 corpus
f7f33358…f38914 승격(b00716ee… 대체 — 구 표본은 실요청과 shape 불일치).

**테마사주 배선**: 기존 목차 C-06 "주의 시기·리스크" 슬롯 재사용(목차
변경 없음 — 데굴님 변경 허용받았으나 불필요). _try_risk_exposed_section:
리포트는 기간이 상품 파라미터(allowed_years)로 명시적이라 파서 없이
period_overview/future/연도범위 직접 전달, data.scorer.risk_shadow→
payload, 채팅과 동일한 run_exposed_reading(게이트·상태기·감사·최종 감사)
소비. INJECTED 성공=그 본문, SUPPRESSED=guard 부착 prompt로 기존 생성,
BYPASS/BLOCK/실패=기존 경로 폴백(위반 초안 미전달). renderer=_tighten.
OFF no-op fixture(+shadow 가드 allowed 등재). 실서비스 INITIAL shape이
reviewed corpus에 존재함을 fixture로 고정. smoke 7/7 재통과(bootstrap
VALIDATED — 새 corpus 기준). pytest 전체 통과·ruff·mypy 0(539)·manifest
일치.

## 대화 시점 scope 동반 승계 (2026-07-17 데굴님 베타 실로그 지적)

실로그: '오늘 운세'→'이후 3개월 주의점'→'건강은 어때?'에서 마지막 턴이
시점 창(90일 offset)은 승계했지만 time_scope가 timeless로 남아 응답이
'오늘' 중심으로 좁혀짐. conversation 승계 블록에서 time_range 승계 시
scope도 동반 승계(이번 턴 scope가 미확정 기본값 timeless일 때만 — 자체
신호 보존). 회귀 fixture: 3턴 시나리오(scope=short_term·offset=90 승계)
+명시 연도 후속은 미승계. 부수 확인: '작년에 건강이 왜 나빴지?'류 과거
회고 시점 미파싱은 별도 기존 이슈로 관찰. pytest 전체·ruff·mypy clean.
위험 게이트 부수 효과: scope 승계로 후속 질문도 미래 창이 살아 위험
노출 대상이 정상 판정됨(timeless=BYPASS였던 것이 창 기준으로).

## 'N개월 안에' 상대 창 소비 결함 2건 (2026-07-17 데굴님 베타 실로그)

'12개월안에' 질문이 [질문 기간: 오늘 하루]로 축소+'질문한 날짜의 일운'
블록 오주입 → 일운 중심 답변. 파서는 정상(offset 360일 창) — 소비 측
결함: ①context_reducer.build_reference_frame이 end_offset_days 창의
end를 환산 표기(2026-07-17 ~ 2027-07-12) ②chat 일운 블록 fallback을
진짜 '그 날 하루' 창(granularity=DAY·offset 없음·end==start)으로 한정.
회귀 fixture 3종(신규 test_offset_window_period_label.py). pytest
전체·ruff·mypy clean — 실서버 자동 반영.

## 대운 발현 진행 모드 — 하드 전/후반 분할 폐기 (2026-07-21 데굴님 확정)

"전반 0-4년 천간 주도 / 후반 5-9년 지지 주도" 하드 이분 서술(디렉티브·
대운표 입력 블록·죽은 스키마 필드)이 "운 후반이 되어야 지지가 작동"류
오답을 유도하던 문제. GPT 제안 검토 후 '새 점수 모델이 아니라 잘못된
하드 이분 서술 제거 + 기존 동태 신호를 발현 서사에 연결'로 정의(P0+P1,
P2 도메인 확대·P3 수치화는 보류). 스펙 SSOT:
doc/v2_2/DAEWOON_PROGRESSION_NARRATIVE.md (4축 분리 — 출처 역할/층위
비중/내부 진행률/발동 예외. luck_cycles._PERIOD_WEIGHTS·transit_source_
strength는 별개 축으로 유지).

구현: ①shared_types/daewoon_progression.py — ProgressionMode 6종
(default_gradient/branch_early_activation/stem_persistent/coactivated/
weak_manifestation/indeterminate)+reason_codes, usage=narrative_only
②saju_engines/daewoon_progression.py — resolve_daewoon_progression:
기존 신호만 읽는 순수 판정(relations_to_chart 충·형·합국완성/
gongmang_activation 공망발동/branch_effect.is_void/간여지동=십성 동일).
신규 소계산은 운 천간의 통근뿐 — 지속(persistent) 판정은 '운 지지 자체'
통근으로 한정(원국 뿌리까지 인정하면 전 대운이 지속형화), 원국 통근은
무근(약발현) 판정에만. 우선순위: 전실+합국 상충→indeterminate > 조기
발동+천간작동/간여지동→coactivated > 조기발동 > 지속 > 약발현 > 기본
③structural_context — DAEWOON_FRAMING_DIRECTIVE 그라데이션 개정('주도'
금지·'상대적으로 드러나기 쉽다'), daewoon_progression_lines(예외 대운만
표기·전부 기본이면 무언급·서술 전용 헤더) ④report_service — luck_block
헤더·행 접미를 '발현 {모드}'로 교체, F-07/F-22 가이드 개정,
_DAEWOON_FRAMING_SECTIONS에 예외 블록 동반 주입 ⑤chat_service —
_wants_daewoon_frame 시 동일 렌더 재사용 ⑥DaewoonItem.first_half_focus/
second_half_focus 삭제(소비처 0건 — FE TS 인터페이스 미정의·backend
로직 참조 없음 전수 확인).

회귀(test_daewoon_progression.py 14케이스): 판정표 모드별 fixture(일지
충→조기발동, 삼합완성+통근→동시발현, 간여지동→동시발현, 무근+합거+공망
→약발현, 운지지 통근→지속, 전실+방합완성→단정불가, 공망충발→조기발동)+
입력 불변(model_dump 동일·실명식 e2e)+문구 회귀(디렉티브·렌더에 0-4/5-9
재유입 금지, 전부 기본이면 침묵, 라벨맵=모드 전수). pytest 전체·ruff·
mypy clean.

## 과거 창 질문의 미래 시제 서술 결함 (2026-07-21 데굴님 베타 실로그)

'2025년 중 몇월에 취직에 성공했을까?'(오늘=2026-07-21)가 전면 미래
시제("열릴 것으로 보여요")로 답변되던 3중 결함: ①'했을까'(하+였 축약)가
_PAST_KEYWORDS '았을까' 부분 문자열에 안 걸림 ②창 전체가 과거(end<오늘)
라는 구조 신호를 방향 판정이 안 봄(문구 키워드 의존) ③회고 판정돼도
시제 디렉티브가 없어 이벤트 후보·트리거류 미래 지향 디렉티브에 묻힘.

교정: ①_question_time_direction 헬퍼 추출 — 절대창 end월<현재월이면
문구 무관 회고(상대 offset 창 제외), 우선순위 구조>과거 문구>미래 문구>
open_when 승계 ②_has_contracted_past — 종성 ㅆ(했/됐/갔…) 유니코드
분해+회고 표지(을까/을지/을 때/던) 결합 판정, '있'(가능 의문)·'겠'(추측)
제외(초판이 '성공할 수 있을까'를 과거로 오탐해 전망형 2케이스 회귀 →
어간 예외로 교정) ③_RETRO_TENSE_DIRECTIVE 신설 — is_retro 시 trailing
주입(과거 추정형 강제·미래 예측/권고 금지·확인 질문도 회고형)
④context_reducer P6 확장 — 걸침 창만 표시하던 사각지대에 elif end<현재:
"이 기간은 전부 이미 지났다(회고 질문)" 노트.

회귀 test_retro_tense.py 16케이스(실로그 시나리오·구조 신호 단독·offset
창 제외·open_when 승계 보존·오탐 가드·frame 노트 신구 분리). 실서버
dry-run 스모크: 실로그 질문=회고 디렉티브+전부지남 노트 주입 확인,
'올해 이직' 대조군=미주입. pytest 2194 passed·ruff·mypy clean —
uvicorn --reload로 실서버 자동 반영.

## '12개월 내에는 없어?' 후속 단절 결함 3중 교정 (2026-07-21 데굴님 베타 실로그)

이직 타이밍 답변(끝문장 "…월별 흐름을 짚어드릴까요?") 뒤 "12개월
내에는 없어?"가 too_broad 안내("질문 범위가 넓어요")로 끊기던 결함.
①time_parser C8이 'N개월 내(에)'를 미커버 — 안에/이내만 인정, '내에는'
창 미파싱 → 내에/내로/내 추가('내(?!내)' lookahead로 '3년 내내' 오탐
차단) ②링커에 상대 창 단답·부정 존재형 규칙 부재 — 2순위 단답
TIME_SHIFT에 '\d+(개월|년|주|일)+(안|이내|내)' 토큰 추가, _REFINE_RE에
없(어/나/나요/을까/는지) 추가(직전 의도 승계 → broad 가드
is_followup_turn 발동) ③비동기(로그인+스레드) 경로 last_offer 사장 —
prep(dry-run)이 조기 return이라 동기 경로 전용 갱신(3849행)이 한 번도
실행 안 됨, offer-slot 링킹이 죽은 규칙이었음 → chat_service.
update_thread_offer 신설(성공=answer에서 추출, 실패=''로 만료),
_run_chat_answer 완료 시 호출. 경합(생성 중 새 턴)은 폴링 UI 특성상
무시 가능 수준으로 주석 명시.

회귀 test_relative_window_followup.py 9케이스(창 파싱·내내 가드·링커
2종·실로그 2턴 재현 career+360일 승계·새 도메인 과승계 가드·offer 갱신
3종). 실서버 2턴 dry-run 스모크: turn2=career/offset360/too_broad
False. pytest 2203 passed·ruff·mypy clean. 부수 발견(별도 이슈):
비동기 경로는 P3 시점 커밋 가드(_time_commit_guard)도 건너뜀 — 이번
범위 제외.

## 배우자 질문 '연주 재성' 원국 오독 교정 (2026-07-21 데굴님 실로그)

실로그(1980-11-22 09:00 서울 男·진태양시 미적용, 庚申 丁亥 己亥 己巳):
"재성이 연주와 월주에 뚜렷하게 드러나 있어" — 연주 庚申은 상관·상관,
재성(水)은 월지·일지 亥 정재뿐. 원인=결혼·자산 블록의 뭉뚱그림 라벨
"재성 환경: 년월(집안 기반)"(wealth_in_family_palace boolean이 년·월을
한 덩어리로 표기)을 LLM이 '연주+월주에 재성'으로 오독.

교정: ①MarriageResourceProfile.wealth_positions 신설 — 드러난(천간·
지지 본기) 재성의 정확한 자리 목록(예: ["월지 정재","일지 정재"],
지장간 잠복 제외) ②marriage_resource_lines — "재성 위치(명식 그대로 —
이 자리 표기만 인용하고 재성이 없는 주(柱)로 옮겨 말하지 말 것): 월지
정재·일지 정재 · 환경 결: 집안·초년 기반권"으로 정밀 표기+가드, 구
'년월(집안 기반)' 라벨 제거(위치 데이터 없을 때만 구 형식 폴백).
판정 boolean·leans 로직 불변.

회귀 test_marriage_resource.py 2케이스(실로그 명식 positions 정확 일치·
년주 미포함, 렌더 가드·구 라벨 부재). 실서버 dry-run에서 신규 라인 주입
확인. 부수 확인: BirthInput 최상위에 apply_true_solar_time을 넘기면
extra로 조용히 무시됨(올바른 경로는 time_options) — 스모크 중 발견,
별도 이슈로 기록. pytest 2205 passed·ruff·mypy clean.

## 년주 천을귀인 '월주' 오독 교정 (2026-07-21 데굴님 실로그)

동일 명식(庚申 丁亥 己亥 己巳) 답변에서 "월주에 있는 천을귀인" — 실제
위치는 년주뿐. 원인=신살 발췌의 위치별 일반론("위치별: 년·월에 있으면
조상의 덕·사회적 조력…")이 재성 '년월' 건과 동일한 뭉뚱그림 패턴으로
실위치([위치: 년주])를 덮음. 교정: ①chart_interpretation._sinsal_
excerpts — 위치별 일반론이 붙는 발췌에 실위치 앵커 "※ 실제 위치 년주
한정(다른 주로 옮겨 말하지 말 것)" 동반 ②_SELF_CHECK_INSTRUCTION에
신살·십성 주(柱) 위치 대조 항목 추가. 초판 문구가 chat_single 12k 토큰
한도를 58tok 초과(integration 가드 적중) → 압축 재작성으로 한도 내 복귀.
회귀 2케이스(test_chart_interpretation.py — 앵커 문구·자체검증 문구),
실서버 dry-run에서 발췌 라인 앵커 확인. pytest 2207 passed·ruff·mypy
clean.

## '생성됐는데 전달 안 된 답변' 원인 규명 + 폴백 관측·타임아웃 교정 (2026-07-21)

실로그('그럼 퇴직 신호는 없어?' 턴): Gemini 콘솔엔 완성 답변이 있는데
사용자에겐 다른 답변이 전달됨. 규명(DB 증거): 01:39:10 질문 → Gemini
호출이 60초 타임아웃(01:40:11경) → gpt-5.4-mini 폴백이 새로 생성해
01:40:15 전달(llm_usage #1148 is_fallback=t, 답변 본문도 폴백산 확인).
Gemini는 서버측 생성을 완료해 콘솔에 남았지만 클라이언트 미수신 —
'재작성'이 아니라 타임아웃→폴백 재생성. 같은 아침 폴백 3건(Gemini 지연).

문제 2건 교정(데굴님 승인): ①관측 공백 — 전환이 무기록(system_errors
0건)이라 추적 불가 → llm_client에 메인 시도 실패 warning(원인·차수·
call_type·ref)+폴백 전환 warning+error sink 통지(kind=
llm_primary_failover, 비치명) 추가 ②timeout_seconds 60→90
(llm_config.json — 60초 초과 생성이 폐기·과금 낭비되던 구간 축소,
pending 폴링 UI라 대기 UX 영향 적음).

회귀 test_llm_client_failover.py 2케이스(전환 시 warning 2종+sink
kind/ref 통지 — caplog는 스위트 간섭으로 _logger 직접 기록, timeout>=90
가드). pytest 2209 passed·ruff·mypy clean.

## 일지 십성 배우자상 세분화 P0~P2 (2026-07-21 데굴님 승인 — 전문가 영상 자료)

'일지=배우자상' 전문가 영상 스크립트 반영. 기존 5군 이상형 레이어
(_IDEAL_TYPE, 영상 자료 A)의 확장 — 전부 서술 전용·판정 불변.

P0 음양 세분: _IDEAL_TYPE_BY_GOD 신설 — 정재(단정·태도까지)/편재(뚜렷
외모)/정관(조건 균형·시간 지나며 현실화)/편관(엣지 선호·한 조건 포기
가능)/정인(인정·칭찬)/편인(+기술·전문성 부양) 6종. 비겁·식상은 군 라벨
유지(자료도 군 단위) + 식상 라벨에 유머·챙김 결 보강. 군 라벨 폴백.
P1 마찰 결: ideal_type_friction 필드 — 군별 '잘 안 맞기 쉬운 결'(비겁→
휘어잡는 상대, 식상→노잼 성실형, 재성→끌림 없는 조건 선택, 관성→기준
대폭 하향, 인성→팩폭·인색한 인정) + 렌더에 '결심 선택은 수년에 걸쳐
마찰' 가드(낙인·이별 단정 금지 명시).
P2 속설 교정: LOVE_MARRIAGE_UNIFIED_DIRECTIVE — '연애운 없으면 결혼운
좋다' 이원 구도 채택 금지·일지 중심 통합 관점, 질문에 '연애운'+'결혼운'
동시 언급 시에만 주입(반박·훈계 없이 정리).
미반영(정책 충돌): 구체 수치(연봉·키)·결혼정보회사 낙인·'얼굴 안 보면
유지 안 된다' 단정·월주 결혼관 폄하 — 경향 표현으로 순화.

회귀 test_marriage_resource.py +5(세분 라벨 정/편 상이·군 폴백·3튜플·
마찰 렌더+비낙인 가드·실로그 명식 정재 세분·P2 디렉티브), 실서버
dry-run에서 3종 주입 확인. pytest 2213 passed·ruff·mypy clean.

## 반사실(counterfactual) 부담 분석 레이어 — 도메인 범용 (2026-07-21 데굴님 승인)

'왜 늦게 결혼할 운이야/왜 안 됐지/그때 했으면 어땠을까' 류 질문에 "그때
실행됐다면 함께 활성화됐을 부담"을 도메인 범용(관계·직업·계약·재물·이사·
학업, health 제외)으로 서술하는 inert 레이어. GPT 검토안(사용자 승인)
4대 수정 선반영: ①부담 분석과 보호 서사 분리 ②fail-closed 상태 기계
③기간 미확정 시 체리피킹 금지 ④사건 단계(시작/조율/유지/결실/회복) 구분.

구현: shared_types/counterfactual.py(상태 5종·모드 4종·신호·claim level,
narrative_only) + saju_engines/counterfactual_context.py:
- 모드 감지 rules-first — 과거 가정형(종성 ㅆ+다면/으면, 있·겠 제외)+
  결과 질의, 과거 원인 회고, 현재 미발생 구분('한다면' 미래 가정 자동 배제)
- 기간 우선순위: 질문 명시(전체 과거 절대창) > 직전 대화 active_time_
  scope > 실제 시도 기록(LifeEventRow confirmed/planned) > 없으면
  INSUFFICIENT(과거 전체 뒤져 '안 하길 잘했다' 서사 생성 금지 지시만)
- 증거: 원국 StructuralInteraction(궁위 라벨 내장, 파싱 불필요) 도메인
  매칭 + 기간 세운(대운 sewoon 생애 커버)의 궁위 직접 자극(충·형·자형
  partner 대조)·공망 발동·운 품질. '구조 AND 활성화' 동시 성립해야
  ELIGIBLE — 기신운 단독은 저신뢰 배경(단독 근거 금지 명시). 불성립=
  BLOCKED(양쪽 모두 단정 금지)
- 보호 해석: 기간 이후 창(≥2년)에서 자극 빈도 감소 AND 지원 비율 증가가
  확인될 때만 ELIGIBLE_PROTECTIVE('시간을 둔 것이 부담을 줄이는 방향과
  겹쳤다' 수준까지) — 아니면 '보호 해석 금지' 명시 주입
- 금지 가드 6종(파국 생성·확정 실패·미발생 과거형·자동 보호 결론·행동
  추정·과거 선택 평가) 블록 고정. chat trailing 배선(도메인 무관).

회귀 test_counterfactual_context.py 10케이스(GPT §8: 모드 7변형·비대상
NA·현재미발생 INSUFFICIENT+자동보호금지·2025충활성 ELIGIBLE_BURDEN_ONLY·
2021무활성 BLOCKED·이혼 유도 비동조·health 제외·스레드 기간 승계·입력
불변·narrative_only). 실서버 dry-run 3케이스(한계/맥락/무언급) 확인,
중복 충 라인 dedupe. pytest 2223 passed·ruff·mypy clean.

## 되물음 답변·서비스 설명 발화 스레드 단절 교정 (2026-07-22 데굴님 실로그)

증상: 사업/부업 질문 뒤 되물음('제품형인지 서비스형인지 궁금해요')에 대한
답변 "사주 풀이를 해주는 웹 서비스인데, 이미 개발은 끝났어"가 NEW로 끊겨
too_broad로 빠지고, 좁히기 제안마저 '연애운'으로 나감. 재현으로 원인 3중 확정:

1. **'사이' 오검출**: `_DOMAIN_WORDS`의 관계어 "사이"(2026-07-01 추가)가
   '**사이**드프로젝트'에 부분문자열 매칭 → 1턴 도메인 [RELATIONSHIP, CAREER],
   RELATIONSHIP이 primary로 스레드 오염 → `_context_suggestions`가 연애운 제안.
   → `_SAI_BOUNDARY_RE` 경계 가드: '사이' 뒤가 문말·비한글·조사류·'좋'일 때만
   관계어 인정(사이드/사이트/사이즈/사이클/사이버 차단, '우리 사이·사이가
   좋아질까·사이좋게'는 유지 — 2026-07-01 계기 케이스 보존).
2. **서술문의 풀이 요청 오인**: `_READING_REQUEST_RE`의 `사주\s*(봐|풀)`이
   '사주 풀이를 해주는 (서비스)'에 매칭 → 토픽 연속(640행) 차단 → NEW.
   → 요청형만 매칭하도록 개정: 관형형 '해주는' 부정 lookahead, '해줘/부탁/줘'
   청유 신호 필수. 트레이드오프: '사주 풀이 가능해?' 같은 변형 요청은 미매칭
   → 후속 승계로 흡수(스레드 단절보다 저위험).
3. **offer-answer 링킹 공백**: 기존 offer-slot은 12자 이하 단답만 수용 —
   되물음에 문장으로 답하면 어떤 규칙에도 안 걸림. → `last_offer` 존재 +
   새 도메인·총운·새풀이 신호 없으면 길이 무관 DRILL_DOWN 승계 규칙 추가.
   `_OFFER_MARKERS`에 되물음 표지('궁금해요/궁금합니다/알려주시면') 보강.

변경: saju_engines/conversation.py(_READING_REQUEST_RE·offer-answer 규칙),
saju_engines/query_parser.py(_SAI_BOUNDARY_RE·_domain_word_position),
chat_service.py(_OFFER_MARKERS). 전부 링킹/서술 계층 — 점수·간지 미개입.
회귀 test_conversation_offer_answer_link.py 20케이스(외래어 4종 차단·관계어
5종 보존·요청형 5종 매칭·서술 2종 미매칭·실로그 2턴 연결·offer 무길이제한·
새 도메인 우선). pytest unit 1918 passed·chat_pipeline 10 passed·ruff·mypy clean.

## 부부 공동 질문 본인 배제 교정 + 이사 세대주(호주) 분리 풀이 (2026-07-22 데굴님 지시)

증상(실로그): '9/30 이사 … 우리가 주의할 점은? 은행 대출(남편)…'+남편 첨부(나×남편)가
"비교할 대상의 출생 정보를 확인할 수 없어요"(need_subject)로 거부. 재현으로 확정한 체인:
'우리가'가 본인(SELF) 신호로 인식되지 않아 subjects=[남편] 단독 → 본인 미포함+동반자 1명
= companion_only(남편 사주만) 오판 → 그 모드 전용 birth 게이트에서 차단. birth가 있었어도
본인 배제된 남편 단독 풀이가 나갈 상황이었음.

수정:
1. **INCLUSIVE_WE_RE**(query_parser, 단일 출처): '우리가(?!게)/우리는/우리 둘/우리 부부/
   저희가' 등 조사 필수 매칭 — '우리 남편/우리 집' 소유격·'우리가게'는 제외. 파서
   _detect_subjects(group 분기 합류→GROUP_AGGREGATE)와 대화 계층 resolve_subjects(별칭
   해소 뒤 SELF 삽입)·_subject_mode(group 판정) 3곳 배선. 결과: 실로그 케이스가
   본인+남편 pairwise로 정상 라우팅(기존 궁합 경로 — birth 없으면 블록 생략 graceful).
2. **관계어 경계 보정**(파서): '{word}(?:의|이랑|…|\s)' → 문말·비한글 lookahead — '은행
   대출(남편)'의 닫는 괄호도 경계 인정('남편감' 합성어는 계속 제외).
3. **이사 세대주(호주) 분리 디렉티브**(_RELOCATION_HOJU_SPLIT_DIRECTIVE): 이사 intent +
   pairwise + relation_type=spouse + 명식 블록 확보 시 '①본인 세대주 ②배우자 세대주' 두
   갈래 분리 풀이 강제. ②는 [대상별 명식] 블록(명식+현재 대운·세운)만 근거, 블록 밖 간지
   관계 계산·월별 신호 날조 금지(fail-closed — 상세 월 신호는 별도 풀이 안내). 블록 미확보
   시 미주입. 서술 전용 — 점수·판정·엔진 경로 불변.

회귀: test_couple_subject_inclusion.py 14케이스(실로그 pairwise·소유격 companion_only
보존·긍/부정 어형·괄호 경계·남편감 제외) + test_chat_pipeline 2케이스(세대주 디렉티브
주입/단독 이사 미주입). pytest 전체 2259 passed·ruff·mypy clean.

## 부부 공동 질문 재발 교정 — 괄호 주석 강등 + kind='self' 동반자 인정 (2026-07-22 후속)

재발(실로그 2): '9/30 이사 예정 … 은행 대출(남편) - 인테리어 등이 남아있는데 주의사항이
뭐가 있을까'(+남편 칩) — 이번 문구엔 '우리가'가 없어 직전 수정(INCLUSIVE_WE_RE) 미적용,
동일 need_subject 거부. 서버 로그·DB 추적으로 2중 원인 확정:

1. **괄호 주석 오채택**: '(남편)'은 대출 담당 표기인데 별칭 해소가 대상 지정으로 채택 →
   본인 배제 companion_only. → strip_parenthetical(query_parser, 단일 출처): 대상 스캔
   (파서 관계어·N호 / 대화 계층 별칭·미등록 지칭)에서 괄호 구간 제외. 인라인 생년월일
   ('동생(1998.07.23)')은 원문 파싱 유지. 결과: 괄호 언급은 서술로만 남고, 동반자는 칩
   첨부(나×남편)로 합류해 pairwise 정상 라우팅. '남편, 사업 어때'(괄호 밖)는 계속 검출.
2. **kind='self' 동반자 사장(치명)**: 실DB 확인 — 사주목록(나님·남편·아들)이 전부
   kind='self'(등록 API 기본값, FE는 companion 플로 미사용). 그런데 별칭 인덱스
   (build_companion_alias_index)·birth 맵(routers/chat.py companion_births)이 kind!='self'
   만 동반자로 인정 → 등록 기반 동반자 해소·birth 조회가 실계정에서 전부 죽어 있었다
   (칩을 붙여도 birth 미발견 → need_subject). → 두 필터 모두 '기준 사주(base) 제외 전부'
   기준으로 변경. 파생 효과: '남편 사주 봐줘'·'아들 시험운' 등 등록 지칭 풀이가 실계정에서
   처음으로 정상 동작.

검증: 실운영 동일 조건(registered 칩+괄호 주석+'우리가' 없음) 종단 dry_run — 분석 경로
진행 + 세대주(호주) 분리 디렉티브 + 남편 명식·궁합 블록 주입 확인. 회귀
test_couple_subject_inclusion.py 18케이스로 확장(재발 문구 pairwise·괄호 주석 비대상·쉼표
경계 유지·kind='self' 인덱스 포함·'남편 사주 봐줘' 해소). pytest 전체 2263 passed·
ruff·mypy clean.

## 특정일 질문 상세화 — '9/30 이사 주의점' 두루뭉술 답변 교정 (2026-07-22 테스터 신고)

신고: 이삿날(9/30) 주의점 상세 요청에 두루뭉술·이상한 흐름 답변. DB 스레드
(web-mrvd0sfa-a3lbei) 전수 추적으로 결함 4중 확정:

1. **단일 날짜 일운 근거 부재(핵심)**: _is_day_range가 end!=start를 요구해 주간 범위만
   일별 일운을 주입 — '9월 30일' 단일 날짜는 당일 간지·길흉·십성이 입력에 없었고, 엔진
   후보도 연·월 창(wealth_change@2026/@2026-09)뿐이라 LLM이 기간 기운 서술로 답을 채우고
   (신고 ②'불필요한 기간 언급') 당일 상호작용(해묘미 목국·유금 충)을 임의 서술(원칙 1
   위반 결). → 단일일도 surface(start<=end, '해당 일' 헤더) + _SINGLE_DAY_FOCUS_DIRECTIVE
   (당일 중심·행동 단위 주의점·기간 서술 한두 줄 제한·데이터 밖 합충 계산 금지).
2. **시제 정정 발화의 시점 오채택**: '오늘은 7월 22일이고 이사는 미래의 일이야'의
   '7월 22일'이 explicit 시점으로 채택돼 active_time_scope가 9/30→7/22로 교체, 답이
   오늘 일운(丁酉) 기준으로 이탈. → time_parser에 _TODAY_DATE_STATEMENT_RE: '오늘은/
   지금은 + 날짜 + 연결어미(이고/인데/이야…)' 진술 절을 시점 추출 전에 제거(순수 '오늘
   운세'는 불변, 진술+명시 목표 혼합문은 목표만 채택).
3. **명시 미래 창의 회고 반전**: '이미 계약도 끝냈고 잔금만 남았는데'의 축약 과거형이
   _question_time_direction ②(문구)에 걸려 9/30 미래 창 후속이 retro 모드→과거형 서술
   ('풀리는 날이었어요'). → ①b 구조 가드: 창 시작이 오늘 이후면 문구와 무관하게 미래
   (기존 ①과거창 가드와 대칭, 과거 창 회고는 불변).
4. **스레드 대상 오염(데이터)**: 이 스레드는 kind-필터 수정 이전에 companion_only(남편
   base)로 굳어 이후 전 턴이 남편님 호칭·남편 명식 기준. 코드로는 기수정(괄호 강등·kind
   인정)이라 신규 스레드 재발 없음 — 해당 스레드는 DB jsonb_set으로 상태 복구
   (active_subjects→본인, 시점 앵커→2026-09-30, ConversationStore 로드 검증).

검증: 실로그 문구 dry_run — [해당 일(2026-09-30) 일운 丁未·한신·식신/편재](엔진 계산)
+ 특정일 디렉티브 + 세대주 분리 디렉티브 동시 주입, 정정 발화 time_range=None(승계),
'이미 계약 끝냈고' retro=False. 회귀 test_single_day_focus.py 8케이스 + 통합 1케이스,
기존 주간 테스트는 단일일 포함 의미론으로 갱신. pytest 2272 passed·ruff·mypy clean.

## 사용자 제공 사실 원장 P0 + chat 입력 상한 22k (2026-07-22 데굴님 승인 — GPT 검토안)

배경: 이전 질문 원문을 상속하지 않는 구조에서 사용자 명시 사실("이미 계약 끝냈고"·
"잔금만 남음"·"손없는 날")이 매 턴 증발 → 모순 서술·되묻기(테스터 스레드). GPT 검토안
(intent-scoped conversational state) 대조 결과 제안의 ~70%는 기구현(링킹·시점 승계·
배제 1급·우선순위·trace) — 실제 공백인 '사실 원장'만 도입, continuation 점수화·
intent_family 개편·자유문장 요약은 기존 체계와 중복이라 미도입.

구현(P0):
- shared_types.UserFact — key/quote(원문 인용)/scope(topic|global)/status/supersedes.
  쓰기 정책 불변식: user_explicit만 저장(엔진 결과·LLM 해석 기록 금지).
- saju_engines/user_facts.py — rules-first 추출 5슬롯(완료·잔여 절차·확정 일정·변경
  불가·손없는날 속설), 문장 절 인용 보존, 단수 키 supersede(이전 인용 이력), 주제
  전환(NEW+도메인 변경) 시 topic 스코프 만료, 저장 캡 12건.
- conversation._advance_state 병합 배선(topic_reset 파라미터), chat_service가
  [사용자 제공 정보] 블록(캡 10건)으로 주입 — "모순 서술·되묻기 금지" 지시 포함,
  주입 슬롯 수 debug 로그.
- 한도표: chat_single/chat_compare 20,000→22,000 (2026-07-22 데굴님 승인 — 사실 원장
  블록+특정일·세대주 디렉티브 흡수). llm_guard 주석·고정 테스트 5파일 동기 갱신.

검증: test_user_facts.py 9케이스(실로그 문장 추출·정정 이력·만료·캡·렌더·턴 축적) +
E2E(t-facts: 1턴 사실이 2턴 프롬프트에 인용) 통과. pytest 2280 passed·ruff·mypy clean.
후속(P1 보류): stage 슬롯 범용화, topic_id 세분화(Domain보다 좁은 상담 단위).

## 절기 경계 특정일 — 타 절기월 후보 오염 제거 + 절기월 앵커 (2026-07-22 데굴님 재발 신고)

신고: '7월 4일에 이사했어, 잘한걸까?'가 또 '7월 운'으로 서술됨 — 7/4는 소서(7/7) 전이라
甲午월(라벨 2026-06) 소속. 프롬프트 재현으로 원인 확정: 기존 절기월 게이트(2026-06-22,
solar_m)는 '창 안 후보 추가'만 걸렀고, **계층 필터 Top-N이 미리 뽑은 다른 절기월 후보**
('이사·이동 @ 2026-07(乙未) — 현재 진행 중·신호 매우 강함')는 입력에 그대로 남아 LLM
서술을 지배했다. [질문한 날짜의 일운] 블록에 '절기월 甲午' 사실이 있었지만 강신호 후보에
묻힘.

수정: ①단일일 질문(solar_m 확정)이면 월 후보 전체에서 다른 절기월(len==7 &&
period!=solar_m) 제거 — 연 후보 유지. ②_SINGLE_DAY_FOCUS_DIRECTIVE에 절기월 앵커 조건부
주입(_SINGLE_DAY_SOLAR_MONTH_NOTE): 절기월 라벨이 양력 달과 어긋나는 날만 '그 날은
{간지}월(라벨) 소속 — 다른 절기월 기운 적용·양력 달 이름 운세 금지' 명시(luck_months로
월 간지 조회, 실패 시 앵커 생략 fail-open).

검증: 7/4 재현 — 乙未 월 후보 제거·甲午 앵커 주입 확인, 7/15(절기월=양력 일치)는 앵커
미주입. 회귀 test_single_day_focus.py 10케이스로 확장. pytest 2282 passed·ruff·mypy clean.

## 사실 원장 커버리지 확대 + 과업 점검 응답형 + 불확실성 번역 P0 (2026-07-22 데굴님 승인)

테스터(김혜선) 신고 4건 + GPT 검토안('가능성은 열리지만 조건 확인이 필요한 달' 폐기):

1. **사실 원장 커버리지(실측 0% → 4/4)**: 실문장 4종("이사가 결정되었어"·"계약서는 이미
   다 썼고"·"8월 신청·9월 공사"·"주택을 사기 위한 대출")이 전부 미추출 — 원장 빈 채
   유지돼 '다시 백지에서 시작' 재현. completed 동사 확장(썼/냈/됐/받았/맺었 + '다 ~')·
   fixed_schedule에 '결정' 추가·신규 슬롯 3종(planned_task 월+과업, day_plan '짐만
   옮기는 날', stated_purpose '~위한 대출'). 같은 절의 fixed/planned 중복은 fixed 우선.
2. **사실 점괘화 금지**: 사용자가 알려준 사실("주택 사려는 대출")을 "~로 읽혀요"로 점친
   듯 반환하던 문제 — [사용자 제공 정보] 블록 지시에 금지 문구 추가.
3. **기간×과업 점검 응답형**(_TASK_RISK_CHECK_DIRECTIVE): 과업 명사+점검 질문+창이면
   과업별 소제목 구조(①절기월 신호 ②구체 문제 ③실무 체크포인트) 강제, 창 밖 서술 금지.
   질문에 월 구간('8~9월'·'8월과 9월')이 있으면 확정일(9/30)이 단일일로 파싱돼도 과업
   점검이 우선(특정일 디렉티브 생략 — 실창=과업 기간). 과업은 질문+원장(planned_task/
   remaining) 양쪽에서 수집.
4. **창 밖 위로성 서술 금지**: 특정일 디렉티브에 '질문 창 밖 다른 해 흐름(내년 용신운
   등) 위로·전망용 언급 금지' 명문화(9/30 질문에 2027 상반기 용신운 서술되던 건).
5. **불확실성 번역 P0**(_UNCERTAINTY_TRANSLATION_DIRECTIVE, 상시): '가능성 열림·조건
   확인 필요·변수 있음' 추상 문구 단독 금지 — ①구체 사건 ②가능/미확정 구분 ③변수 실명
   (심사·상대·자금·서류·일정) ④행동 1개 구조 강제, 변수 미상이면 '준비·탐색 신호 중심'
   으로. GPT안 P1(uncertainty_type 코드)·P2(조건명 산출)·P3(이해도 회귀)는 후속 보류.

검증: 실문장 4/4 추출, 과업 점검·불확실성 디렉티브 주입 통합 테스트, 전체 pytest 2286
passed·ruff·mypy clean. 능력 탐문 질문('너 ~ 알고 있어?') 라우팅은 별도 건으로 보류.

## 현실 과업 절차 레이어 — 능력 탐문 라우트 + 절차 지식팩 (2026-07-22 데굴님 승인)

보류 항목 진행(GPT 검토안 '사주 신호→현실 과업 번역' — 승인 문서 기준 P1~P3 축소 구현):

1. **CAPABILITY_PROBE/PROCEDURE_QUERY 선행 라우트**: '너 집 계약 절차 알아?'·'계약
   순서가 어떻게 돼?'가 일진 풀이로 응답되던 과잉 라우팅 차단. QueryType enum은 확장하지
   않고(docs/03 taxonomy 불변 — 절대원칙 10) 서비스 계층 선행 라우트(지역오행 사실 질문
   패턴)로 처리: 명식·이벤트·LLM 미호출, status=policy(질문권 미차감), 절차 단계+한계
   고지+'어떤 과업의 시기·주의점부터 볼까요?' 상담 전환 유도. 시기·길흉 신호(운세/언제/
   괜찮/해도 될)가 있으면 미발동 — 분석 경로 보존.
2. **task_procedures.py 지식팩(L1/L2, 코드 상수)**: housing(자금계획→…→입주·하자, 승인
   ≠실행·잔금 의존 등)/employment/selection/marriage 4종 + 범용 온톨로지 폴백. 팩마다
   단계·의존관계·흔한 실패·되돌리기 어려운 시점·확인 행동 + **expert_note(L3 경계 —
   최신 규제·법률·승인 가능성 자체 단정 금지, 확인 안내로 분리)**.
3. **MIXED_TASK 배선**: 기간 과업 점검 발동 시 [과업 절차 참고] 블록 가산(운 신호 아님
   명시·점괘화 금지) + 디렉티브에 4층위 구분(사용자 사실/운 신호/절차 점검/미확인)과
   단계 미확인 시 '신청 전이라면/진행 중이라면' 분기 안내 강제.
4. **추상 경고 린트 확장**: 금지 어휘 4종 추가(신중한 접근·흐름 살피기·무리하지 않기·
   꼼꼼히 준비) + 경고 문장은 '과업+실패 형태+확인 행동+시점' 중 3요소 이상 규칙.

검증: 라우팅 판정 8케이스(탐문 4 통과/운세 4 미발동)·팩 감지·L1/L2/L3 경계·policy 즉답·
과업 점검 절차 블록 주입. pytest 2299 passed·ruff·mypy clean. 잔여: 재생성 린트(출력
후 검사), 지식팩 확장(사업·여행·치료), uncertainty_type 엔진 코드(P1)·조건명 산출(P2).

## 대화 개선분의 테마 리포트 공유 배선 (2026-07-22 데굴님 승인)

점검 결과 당일 개선분은 전부 chat 경로 전용이었고, 리포트 파이프라인(report_service)은
별도 경로라 미적용 — 이식 가치 있는 2건을 공유 배선:

1. **불확실성 번역 규칙 공용 승격**: chat_service 내부 상수 → structural_context.
   UNCERTAINTY_TRANSLATION_DIRECTIVE(양 파이프라인 공유 디렉티브 관례 위치). chat은
   상시 trailing, 리포트는 전 섹션 prefix(GONGMANG 옆 — 캐시 대상 고정 prefix)에 부착.
2. **절차 지식팩 리포트 부착**(_PROCEDURE_PACK_SECTIONS): RL-05(리스크·계약 전
   체크리스트)/RL-07(이사 행동 전략)→housing, J-07(직업 행동 전략)→employment.
   목차 불변(절대원칙 10 — 컨텍스트 재료만). 선발·배치는 기존 전용 보조 유지.
   결혼 팩의 관계 테마(R-07/RP-09) 부착은 연애 상담에 결혼 절차가 새는 위험이 있어
   보류(필요 시 별도 검토).

나머지 당일 개선분(링킹·사실 원장·시점 승계·세대주 분리·능력 탐문·kind 필터)은 대화
전용 개념이거나 리포트가 원래 정합(절기월=composites 원천, partner=직조회)이라 비대상.
검증: RL-05 절차 블록+L1/L3 경계·RL-03 불확실성 규칙 prefix 확인, pytest 2300 passed·
ruff·mypy clean.
