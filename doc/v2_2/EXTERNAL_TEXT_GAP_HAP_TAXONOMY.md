# 외부 자료 대조 — 「사주 명리학의 합(合) 종류 총정리」 vs 류보살 v2 합 판정 로직 (2026-10-25)

> 목적: 데굴님이 붙여 넣은 합 분류표(천간오합·육합·삼합·방합·반합·반회·암합·명암합·공합·천합지합 / 합화·합이불화·합반·합거 / 쟁합·투합·합충병견·탐합망충 / 근합·원합, 엔진 권장 5단계)를 현재 판정 로직과 대조하고, **빠진 부분과 판정 오류**를 가려 교정안을 우선순위로 제시한다.
> 원칙: 외부 자료는 참고 문헌이다. 미정의 명리 규칙은 데굴님 결정 전에 구현하지 않는다(원칙 10). 점수 규칙은 85사례·실사례 적중률로 ON/OFF, 문구·기능층은 ON 후 실답 감수(2026-10-15).
> 조사 방법: 코드 전수 탐색(2026-10-25, `hap_modes`·`structure_analysis`·`interactions`·`luck_cycles`·`relation_semantics`·`hap_lines`·`luck_hierarchy`·`amhap_luck`·`structure_patterns`·사전 3종·테스트 20파일) + 쟁점 8건 웹 검색(아래 §4 출처).

## 1. 요약 판정

| 구분 | 건수 | 항목 |
|---|---|---|
| 이미 동등 | 9 | 천간오합 5쌍·化神, 육합 6쌍, 삼합 4국(완성·운 완성), 방합 4(강화=변화 아님·부분), 반합=왕지 포함(다수설), 화(化) 3등급(월령·통근·쟁합·간격극), 합반/합거 상태 모델(Formation/Transformation/Binding), 일간 본신지합·화기격, 공망×합(合則不能空) |
| **판정 오류·결함(교정 대상)** | 6 | ①리포트 운 합 풀링(기간 혼합·운–운 쌍·라벨 오류) ②격위 약화가 化 등급에 미반영 ③쟁합 격위 소멸 예외 미구현 ④탐합망충 사전 항목 소비자 없음(사문) ⑤寅亥·巳申 육합이 자체 파·형 때문에 영구 불확정 ⑥생지+고지 2자(申辰·寅戌·巳丑·亥未) 엔진 불일치 격리 미해결 |
| 빠진 부분(신설 후보) | 6 | 공합(拱合) 분류, 천합지합, 합거 대상 결정(선합·무근), 운이 원국 기존 합에 주는 변화(쟁합 가세·등급 하락) 노출, 암합 '이미 반합으로 묶인 쌍 제외' 가드, 제3 글자 충 간섭의 化 등급 반영(HM) |
| 학파 차이 — 현행 유지 | 3 | 午未合 오행(火 다수설·土 소수설·불변화 극소수), 지지 거리 규칙(미검증), 암합 광의 탐지 |
| 참고만 | 2 | 합거 용어 자체 논쟁(합반 심화=합거 관점), 반합 왕지 없는 쌍도 무조건 약하지 않다는 소수 견해 |

## 2. 항목별 대조

### 2-1. 1단계 — 합 후보 탐지

| 자료 | 우리 시스템 | 판정 |
|---|---|---|
| 천간오합 5쌍·化神 | `STEM_COMBINATIONS`(constants.py:343) 동일, `relations.json` possibleModes 합화·합반·합래·합거 | 동등 |
| 육합 6쌍(午未=土 또는 火) | `SIX_COMBINATIONS`(constants.py:352) 午未→火, SPEC A 표에 다수설·소수설 병기 | 동등 — 웹 확인: 한국 자료 다수 火, 중국 자료 土, 소수 불변화. 현행 유지 |
| 삼합 4국 생·왕·묘 | `THREE_HARMONY` (members, element, 왕지) | 동등 |
| 방합·삼회 | `DIRECTIONAL_COMBINATIONS`, HM: 완성=strengthen(강화), 2자=partial | 동등 |
| 반합 = 왕지 포함 2자 | REL·HM·LC·yearly_environment: 왕지 필수 | 동등(다수설) |
| 반회(방합 2자) | HM partial 0.6, LC `방합기여` — 인접·왕지 조건 없음 | 동등. 웹: 왕지 없는 寅辰은 방합으로 보기 어렵다는 견해 있음 → §3 P2 참고 |
| 공합(拱合: 申辰·寅戌·巳丑·亥未) | **용어·분류 없음.** 탐지기(`interactions.py:151`)는 `partial, royal_included=False`로 잡고 HM은 버려 `ENGINE_CONFLICT` 격리(REVIEW_HALF_HAP_WITHOUT_ROYAL.md 미결). `daily_ilju_fortune.py:205`는 반합으로 **셈** | **결함 ⑥ + 신설 후보** |
| 암합(지장간↔지장간)·명암합(천간↔지장간) | 원국: `relations.py:73-106` 광의(모든 지장간) / 운: `amhap_luck.py` 명암합·지장간 둘 다, 궁위 가중, 서술 전용 / 사전 `rel_암합` enabled:false | 동등(보조) — 자료도 "고정표처럼 취급 어렵다". 웹: 정기 기준 5쌍이 통용, **이미 반합(子辰)인 쌍은 암합 제외** 규칙 → §3 P1-5 |
| 천합지합 | 없음 | 신설 후보 P1-2 |
| 근합·원합(요합) | 천간: 격위(비인접) `weakened`·strength×0.3 / 지지: 거리 규칙 없음(SPEC `[미검증]`) | 부분 — 결함 ② |

### 2-2. 2단계 — 성립 조건 검증

| 자료 | 우리 시스템 | 판정 |
|---|---|---|
| 거리(인접) | HM: 격위 → `weakened`, strength×0.3. **그러나 `disturbed = blocked or contend`라 격위는 化 등급에 들어가지 않아 年干↔時干도 `confirmed` 가능**(hap_modes.py:211-220). strength는 하류 소비자 없음(라벨만) | **결함 ②** — 웹 통설: 천간합은 인접만 성립, 사이 글자 끼면 불성립·약화(時干↔年干 불가). SPEC B 표("불성립 또는 2~3할")와도 불일치 |
| 간격극 | HM `_intervening_control` → blocked·tier none | 동등 |
| 충·형 간섭 | HM: 육합은 **두 글자 자체의** 충·파·해·형만(`_co_relations`), 제3 글자 충은 미반영. SA(보조 판정기)에는 제3 글자 충·형 blocker 있음 | 부분 — 결함 ⑤ + 신설 후보 P1-6 |
| 월령 득기 | HM `season_state` 왕·상 → confirmed 조건 | 동등 |
| 통근·투간 | 통근: 임의 지장간 포함(느슨), 운 지지 미포함 / 化神 투간: 없음 | 부분 — 웹: 투간은 합화 보조 조건(삼합국 "천간에 투출하면 색이 분명"). P2 후보 |
| 쟁합·투합 | HM: 제3 천간이 한쪽과 합하면 contend, strength×0.5, confirmed 불가 → conditional. **제3 천간의 격위·간격극 여부 미검사**(SPEC B "둘 중 하나가 隔位면 쟁투 소멸" 미구현, `test_hap_modes.py:88-97`이 격위 경쟁자도 contend로 고정) | **결함 ③** — 웹: 쟁합=2양:1음, 투합=2음:1양, 쟁합·분합은 합화 어렵다(KCI) — 우리 등급 하락은 통설과 일치 |
| 쟁합 우선순위(년월>월일>일시) | 없음(모든 쌍을 각각 출력) | 참고 — 웹 1건(블로그), 근거 약함. 불채택 |

### 2-3. 3단계 — 작용 상태 판정

| 자료 | 우리 시스템 | 판정 |
|---|---|---|
| 합성·합화·합이불화·합반·합거 | `FormationState`/`TransformationState`/`BindingState`(BOUND=합반, REMOVED=합거). bind+tier≠confirmed=합이불화 | 동등 |
| 합거 대상(어느 글자가 밀리나) | 운 관여 bind만 `direction="away"`(운이 원국 글자를 합거). **원국 내 합은 방향 없음**(선합·인접·뿌리 규칙 부재, SPEC C-3 미구현). `pattern_transit.py:323`은 REMOVED 시 원국 글자 0 | 부분 — 웹: 무근(無根) 천간 쪽이 합거, 뿌리 약한 쪽이 합반. 신설 후보 P1-3(서술 전용) |
| 합래(合來) | `direction="toward"` 미할당 → `HAPRAE` 도달 불가 | 사문 — 정리 대상(P2) |
| 쟁합 상태 | contend → conditional·bind, 라벨(관성/재성/인성 쟁합 — RELATION_TERMS_V2) | 동등 |

### 2-4. 4·5단계 — 명식 영향·운 변화

| 자료 | 우리 시스템 | 판정 |
|---|---|---|
| 합충병견·합중유충 | `structure_patterns.py:476-496` 라벨(원국), `hap_lines.py:174` 합처봉충(운, V2) | 동등(서술) |
| 탐합망충 | **사전 `events/career_change.json:177`·`relocation.json:139`에 `relationAlso: six_combination` 감점(−0.2/−0.25)이 있으나 Python 소비자 없음**(`relation_also`는 검증만) | **결함 ④(사문)** — 웹: 자동 우선 아님, 월령·뿌리·거리·완성도 비교. 점수 반영은 측정 전제 |
| 합해충(합이 충을 해소) | 없음 | 웹: 단일 통설 없음 → 불채택 |
| 합충동시(운) | shadow 환원 체인(RREV R1~R9, 충이 확정 化만 되돌림) — 플래그 OFF | 현상 유지(측정 대기) |
| 운에서 원국 합의 강화·완화·해소·신규 | pattern_transit 신규/강화/완화/해소, `luck_hap_mode_lines`는 **운 관여 쌍만** — 운 글자가 원국 기존 합에 쟁합으로 가세하거나 등급을 떨어뜨리는 변화는 **미노출** | 부분 — 신설 후보 P1-4 |
| 리포트 운 합 블록 | `report_service.luck_hap_lines`(2336-2355): 후보 기간 전체의 세운·월운·대운 글자를 **집합**으로 합쳐 한 번에 resolve → ①서로 다른 기간 운 글자끼리 쌍(운–운 합) ②같은 글자 중복 소실 ③운–운 쌍도 "운 합 — 원국 글자 합거" 라벨 | **결함 ①** |

### 2-5. 두 판정기 공존

- `hap_modes.resolve_*`(정본, LLM 입력·의미·완화·이벤트·패턴 공급)와 `structure_analysis._transformation`(가중 점수, structure_modifier·shadow 공급)이 다른 답을 낼 수 있다. HWAGI_REEVALUATION_REVIEW.md가 HM을 canonical로 선언. 이번 교정은 HM에만 적용하고 SA는 손대지 않는다(제3 글자 충 간섭만 HM으로 이식 — P1-6).

## 2-6. 반영 결과 (2026-10-25 데굴님 "P0 진행하되 사례 비교에 어긋나지 않는지 반드시 확인, P0-4·P1-3 권고대로, 육합 건은 추가 기준 참고")

| # | 상태 | 구현 |
|---|---|---|
| P0-1 리포트 운 합 풀링 | 완료 | `report_service.luck_hap_lines` 후보 기간별(그 기간 운 간지 + 대운) 판정 + `[2027 丁未 · 대운 壬辰]` 라벨. 운–운 집합 쌍 제거 |
| P0-2 격위 → 化 등급 | 완료 | `hap_modes`: `disturbed = blocked or contend or weakened` → 상한 conditional |
| P0-3 쟁합 격위 소멸 | 완료 | `_contend_dissolved` — 제3 천간이 상대와 격위이거나 간격극 차단이면 쟁합 아님. `test_contend_detected` 반전 |
| P0-4 탐합망충 | shadow 구현 | `period_v2_config.TAMHAP_MANGCHUNG_MODE`(off/shadow/apply, 기본 shadow) + `EventEngineV2._apply_tamhap_mangchung`(운 충 구성 지지가 같은 기간 육합(tier≠none)으로 묶이면 사전 `relationAlso` 감점 대상 — shadow=기록, apply=점수×(1+δ)) + `load_tamhap_rules`(사전 소비자 신설) + `casebook_replay --tamhap-mode`. ON 여부는 측정 후 결정 |
| P0-5 寅亥·巳申 | 완료(확장) | `_six_disturbing`: 자체 파·부분형 제외, **제3 글자 충**·완전 삼형만 방해(외부 기준 §5 단계 4·5·6). 寅亥 = 합 중심, 巳申 = 합·형 독립 |
| P0-6 생지+고지 | 완료(일주 운세 제외) | `kind='gonghap'` 신설(HM·ERS 라벨 '공합'·해석 '부분 가세(미약)'·계층 RESOLVED+점수 제외 `WEAK_PARTIAL`·`hap_lines` 표기), HALF 문서 종결. **일주별 오늘의 운세의 반합 카운트는 바꾸지 않음** — 베타 pool `beta-daily-pool.c10.v2` 문장·확률 동결 계약(골든 3일 지문 변경 확인: 巳丑·亥未·申辰 쌍 일주의 확률·top5 이동)이라 다음 pool version 에서 데굴님 결정 |
| P1-3 합거 대상 | 완료(서술) | 원국 bind `notes` "묶이기 쉬운 쪽(통설·참고): X"(뿌리 수 비교, 동률 없음) |

사례 비교(85사례 180명식, 같은 셸): 아래 §2-7.

## 2-7. 사례 비교 측정 (85사례 180명식, 같은 셸, `casebook_replay --out-name` → `casebook_report --tag`)

| 재생 | pair 일치 | 시점 적중(event_hit) | 방향 오탐 | 행 차이 | 비고 |
|---|---:|---:|---:|---|---|
| `hap_base`(변경 전) | 33/68 | 23/44 | 8 | — | 기준선 |
| `hap_after`(P0 1차) | 33/68 | 23/44 | **9** | CASE-028/L event_fav +0.13→−0.12 | 쟁합 격위 소멸이 **일간**(丙, 연간 辛과 격위)까지 소멸로 봐 丙 세운마다 丙辛合 水(구신) 化 확정 → 가족 '+' 사례가 '−'로 |
| `hap_after2`(일간 예외 추가) | 33/68 | 23/44 | 8 | **0건** | 기준선과 완전 동일 — P0-1~6·P1-3 최종 |
| `hap_tamhap2`(탐합망충 apply) | 33/68 | 23/44 | **9** | CASE-072/R fav −0.1(실제 '+'), CASE-042/L −0.04→−0.09, CASE-051/L +0.12→+0.24 | shadow 후보 1,541기간·1,868사건. 적중 이득 없이 오탐 +1 → **apply 미채택, shadow 유지** |

- 결론(데굴님 기준 "점수 규칙은 적중률로 ON/OFF"): 서술·판정 교정(P0-1·2·3·5·6, P1-3)은 사례 지표를 바꾸지 않고 들어갔고, 점수 규칙인 탐합망충은 켜지 않는다. 다음 측정은 실사례 입퇴사 이력(`measure_entry_slot_modes.py` 모집단)에서 재시도.
- 쟁합 소멸 예외의 근거: 일간은 명식의 주체라 자리와 무관하게 자기 합 상대를 두고 다투는 당사자(본신지합) — 외부 규칙 "둘 중 하나가 隔位면 쟁투 소멸"은 비일간 천간 간의 다툼에 적용한다(`hap_modes._contend_dissolved`).

## 2-8. P1·P2·일주 운세 실험 (2026-10-25 데굴님 "실험 우선, 권고대로")

| 항목 | 처리 | 측정·근거 |
|---|---|---|
| P1-2 천합지합 | ON(서술 표지) | `hap_lines.cheonhap_jihap_lines` — 원국 기둥쌍·운 기둥 vs 원국 기둥, 길흉·점수 없음 |
| P1-4 운이 원국 합에 주는 변화 | ON(서술) | `natal_hap_change_lines` — 운 천간 제3자 가세=쟁합(결속 약화) / 운 지지 충으로 化 등급 하락=합·충 경쟁 |
| P1-5 암합 가드 | ON | `amhap_luck._openly_combined` — 육합·왕지 반합 쌍은 지장간암합 제외(공합은 유지) |
| P1-6 제3 충 간섭 → 삼합·반합 | **기본 ON** | `HAP_EXPERIMENTS["trine_third_clash"]` 재생 `hap_exp_trine_third_clash`: pair 33/68·적중 23/44·오탐 8 불변·행 차이 0 → 육합(P0-5)과 일관성 위해 ON |
| P2 化神 투간 조건 | 기본 OFF 유지 | `HAP_EXPERIMENTS["stem_tougan"]` 재생 `hap_exp_stem_tougan`: 지표 불변(행 차이 0). 지표로는 득실이 없고 통설 합의가 약한 추가 조건이라 근거 사례 전까지 OFF |
| P2 합래 사문 | 정리 | `structure_patterns` HAPRAE 방출 제거(도달 불가), 사전 `detector_source: unreachable` |
| 일주 운세 공합 제외 | 플래그 OFF·측정 완료 | `daily_ilju_fortune.HALF_HARMONY_REQUIRES_ROYAL=False`(pool 동결). `scripts/measure_daily_gonghap.py`(c10.v2 공개 창 1,800장): 바뀐 카드 204(11.3%), 확률 변화 425건 평균 \|Δ\| 3.74p·최대 13p, top5 축 이동 38(29/30일) → 다음 pool version 에서 True 통일 여부 데굴님 결정 |

## 3. 교정·신설 제안 (2026-10-25 P0 전체 + P1-3 승인·구현 — §2-6·§2-7; P1·P2 실험 — §2-8)

### P0 — 판정 오류·결함

| # | 항목 | 교정안 | 영향 |
|---|---|---|---|
| P0-1 | 리포트 운 합 풀링 | `luck_hap_lines`를 **후보 기간별**로 호출(그 기간 운 간지 + 그 기간이 속한 대운만), 결과에 기간·층위 라벨(`[2027 丁未 + 대운 壬辰]`) 부착. 운–운 쌍(대운×세운)은 "운 간 합"으로 별도 표기하고 "원국 글자 합거" 라벨 금지 | 서술 입력 정정. 점수 불변 |
| P0-2 | 격위 → 化 등급 | `weakened`면 tier 상한 `conditional`(confirmed 불가) + 노트 "격위 — 합력 약화". 불성립까지 올리지 않음(학파 갈림, SPEC B "불성립 또는 약화") | 원국 年干↔時干 합의 합화 확정이 가화로 내려감 → 85사례 재생 비교 필수(화기격·용신 영향) |
| P0-3 | 쟁합 격위 소멸 | 제3 천간 k가 경쟁 상대와 격위이거나 k 쌍이 간격극 blocked면 contend 제외(SPEC B 명시 규칙). `test_hap_modes.py:88-97` 기대 반전 | 쟁합 과탐지 감소 → 일부 쌍이 confirmed로 승격 → 85사례 재생 비교 |
| P0-4 | 탐합망충 사문 | 두 안 중 택1: (a) `relation_also` 소비자 구현 — 충 신호 감점을 **같은 지지가 육합(운 또는 원국)으로 묶여 있고 그 합이 confirmed/conditional일 때만** 적용 (b) 사전 항목 삭제·문서 정정. 권고 (a)를 **shadow 로그**로 먼저 켜고 85사례 적중률 비교 후 ON | 점수 규칙 → 측정 전제 |
| P0-5 | 寅亥·巳申 자체 파·형 | `_co_relations`에서 **두 글자 자체의** 파·형은 disturbed 제외(가중 노트만), 충은 유지. 寅亥=합 우선(파 미약) 통설, 巳申=형합 논쟁은 노트로 병기 | 寅亥·巳申 합화 confirmed 가능해짐 → 85사례 재생 비교 |
| P0-6 | 생지+고지 2자 | 통일안: 탐지기 kind `half_harmony(royal_included=False)` → 새 kind **`gonghap`(공합·가합)**으로 분리, HM은 `partial` 모드·tier none·strength 0.3·노트 "공합(가합) — 왕지 없음, 합으로 미인정 학파 다수" 로 **의미 판정 부여**(ENGINE_CONFLICT 격리 해제), 서술은 "부분 가세(미약)" 유지, 점수·클러스터 제외, `daily_ilju_fortune` 반합 카운트에서 제외 | HALF 미결 종결. 점수 불변(격리와 같음), 일주 운세 샘플 재생 비교 |

### P1 — 빠진 부분(서술 전용 신설)

| # | 항목 | 제안 |
|---|---|---|
| P1-1 | 공합 용어 | P0-6과 동일 kind. `relations_text.json`에 `rel_공합` 1건(의미·주의: 완전한 삼합처럼 계산 금지) |
| P1-2 | 천합지합 | 두 기둥(원국 기둥쌍 / 운 기둥 vs 원국 기둥)이 천간합+지지합 동시 성립이면 라벨 1줄 "天合地合 — 결속 강함(궁위 의미)". 판정·점수 없음 |
| P1-3 | 합거 대상(원국) | 원국 bind에서 뿌리 비교(`_rooted` 강도·월령)로 "밀리기 쉬운 쪽" 후보를 노트로만 표기("무근 쪽이 묶이기 쉬움 — 통설"). 점수 불변. **명리 규칙 신설이라 데굴님 확정 필요** |
| P1-4 | 운의 원국 합 변화 | 운 천간이 원국 합의 제3자가 되면 "원국 甲己合에 운 己 가세 — 쟁합(결속 약화)" 1줄, 운 충이 원국 합 구성원을 치면 "합처봉충" 확장(현재 운 육합 전용). `luck_hap_mode_lines`에 `natal_change_lines` 추가 |
| P1-5 | 암합 가드 | `amhap_luck`: 두 지지가 이미 삼합·반합·육합으로 묶인 쌍이면 암합 줄 제외(웹 통설 子辰 예외). 보조 자료 노이즈 감소 |
| P1-6 | 제3 글자 충 간섭 | HM 육합·삼합 tier에 "제3 원국 지지가 구성원을 충"을 disturbed에 포함(SA 규칙 이식). 85사례 재생 비교 |

### P2 — 정리·보류

- 합래 `toward` 미할당·`HAPRAE` 도달 불가 → 코드·사전 정리(사문 제거) 또는 운 글자가 원국 희신을 '끌어오는' 정의 확정 후 구현.
- 化神 투간 조건(합화 보조) → 85사례 측정 전제 후보.
- 반회(방합 2자) 왕지 조건 → 소수 견해, 보류.
- 쟁합 우선순위(년월>월일>일시) → 근거 약함, 불채택.
- 지지 거리 규칙 → SPEC `[미검증]` 유지.

## 4. 웹 검색 출처(2026-10-25)

- 午未合: [위키백과 합(사주팔자)](https://ko.wikipedia.org/wiki/%ED%95%A9_(%EC%82%AC%EC%A3%BC%ED%8C%94%EC%9E%90)) 火 / [新浪 地支六合](https://www.sina.cn/news/detail/5325817053446653.html) 土 / [육합(팬덤 위키)](https://auto.fandom.com/ko/wiki/%EC%9C%A1%ED%95%A9) 불변화
- 쟁합·투합: [위키백과](https://ko.wikipedia.org/wiki/%ED%95%A9_(%EC%82%AC%EC%A3%BC%ED%8C%94%EC%9E%90)) / [KCI 천간합충 이론 고찰](https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART002726914)(분합·쟁합은 합화 어려움) / [갑진사주명리 쟁합 요령](https://m.cafe.daum.net/ssmys/X5rp/75?svc=AXZ)
- 합화 조건·인접: [sajustudy 천간합](https://www.sajustudy.com/55) / [이루고 형충회합 정리](https://m.cafe.daum.net/nameoff/8G9l/64) / [합의 조건(스크랩)](https://blog.daum.net/leeks9339/2279) / [KOCW 강의자료](http://contents.kocw.or.kr/contents4/document/lec/2012/Kookjemunhwa/Hongjaekwan/6.pdf)
- 반합·가합·공합: [위키백과 가합](https://ko.wikipedia.org/wiki/%ED%95%A9_(%EC%82%AC%EC%A3%BC%ED%8C%94%EC%9E%90)) / [두루미사주 신자진](https://www.durumisaju.com/dict/relation/sinjajin-samhap) / [dk-saju 삼합](https://www.dk-saju.com/hapchung/%EC%82%BC%ED%95%A9) / [8-codes 13강](https://guide.8-codes.com/lecture/elementary/13.html)
- 탐합망충: [OpenFate 탐합망충](https://wiki.openfate.ai/ko/bazi/stem-branch-relations/combination-neutralizes-clash) / [역학동 충과 합](https://m.cafe.daum.net/2040/MsI/62789?listURI=%2F2040%2FMsI) / KCI 위 논문
- 암합·명암합: [위키백과](https://ko.wikipedia.org/wiki/%ED%95%A9_(%EC%82%AC%EC%A3%BC%ED%8C%94%EC%9E%90)) / [sajuabc 암합](https://sajuabc.com/%EC%95%94%ED%95%A9/) / [김동완 암합](https://m.cafe.daum.net/sajuloves/Bw7y/33?svc=cafeapi)
- 합거·합반: [역학동 합거란 게 있을 수 있는가](https://m.cafe.daum.net/2040/MsI/62815?listURI=/2040/MsI) / [합동·합반·합류](https://blog.daum.net/ghleehan/13369126) / [인터넷역학 합거는 잘못된 이해](http://lifesci.net/pod/bbs/board.php?bo_table=B01&wr_id=907)
