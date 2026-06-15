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
