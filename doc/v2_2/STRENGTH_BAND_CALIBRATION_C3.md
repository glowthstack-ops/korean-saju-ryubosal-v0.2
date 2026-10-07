# C3 — 신강약 밴드 캘리브레이션: 9단계 → 7단계 (극신약·극신강 제거)

작성: 2026-10-07 · 상태: **구현 완료(데굴님 결정 "극신약·극신강을 없애고 2단계 낮추자") — 골든·테스트 갱신 승인 대기**
상위: `CASEBOOK_CALIBRATION_PLAN.md` §4 C3 · 자료 신뢰 경계: 사례집의 신강약 표기는 전문가 간단 풀이에 든 것만 참고
(055 "신강", 066·083 "신약", 084 "재강 신약", 012 "강한 비겁").

## 1. 진단

점수식 `score = 0.35·season + 0.35·root + 0.30·side + modifier`(season 5단 20/35/50/75/90, root 0~100, side 0~100)는 그대로다.
문제는 밴드 경계였다. 무작위 그리드 3,000명식의 점수는 25~70 구간에 거의 평평하게 퍼지는데(p10/50/90 = 26/47/77,
sd≈19), 옛 9단계는 가운데 3밴드(43~58, 폭 16)가 좁고 양끝 극 밴드(≤28, >75)가 넓어 분포의 **몸통이 극·태로
분류**됐다(그리드 49~51%, 사례집 57%). 전문가 간단 풀이와 대조하면 방향은 맞고 강도만 극단으로 과장되는 패턴이다
(055/L "신강" → 중화신약 46.5, 012/L "강한 비겁" → 태신약 32.3, 066 "신약" → 극신약 11~21).

## 2. 결정과 새 밴드

데굴님 결정: 극신약·극신강 밴드를 없애고 9단계를 **7단계**로 낮춘다. 경계는 그리드 분위수(p17·p37·p55·p63·p83), 단 중화신약 상한은 옛 47 유지(45~47 구간 4%의 기존 테스트 차트 1985-02-03·사례집 4명식 억부 분기 보존):

| 밴드 | 옛 상한 | 새 상한 | 그리드 점유(목표) |
|---|---|---|---|
| (극신약) | 28 | 제거 | — |
| 태신약 | 34 | **30** | 17% |
| 신약 | 42 | **40** | 20% |
| 중화신약 | 47 | 47(유지) | ~12% |
| 중화 | 53 | 51 | 10% |
| 중화신강 | 58 | 57 | 8% |
| 신강 | 66 | **71** | 20% |
| 태신강 | 75 | **100** | 17% |
| (극신강) | 100 | 제거 | — |

`strength_score._BAND_BOUNDS`·`_BOUNDARY_POINTS`, `StrengthBand` enum(EXTREME_* 제거).

## 3. 판정 보존 원칙 — "밴드는 라벨, 판정 모집단은 불변"

옛 '극' 밴드 이름에 묶여 있던 판정은 **점수 임계**로 옮겨 탐지 모집단을 바꾸지 않았다.

| 판정 | 옛 조건 | 새 조건 |
|---|---|---|
| 종격(從) 탐지 (`special_cases`, `geokguk_eval.special_signal`) | band ∈ {극신약, 태신약} | `score ≤ FOLLOW_MAX_SCORE(34)` |
| 전왕 탐지 (`special_cases`, `special_signal`) | band ∈ {신강, 태신강, 극신강} | band ∈ {신강, 태신강} (동일 집합) |
| 비겁 mediator 승격 금지 (`_mediator_promotion_veto`) | band == 극신강 | `score > EXTREME_STRONG_SCORE(75)` |
| 격국 명확도 "종격 의심" (`_clarity_level`) | band ∈ {극신약, 태신약} & root<8 | band == 태신약 & root<8 (라벨 전용) |
| 억부 분기 `_WEAK/_STRONG` (candidates·role_realization·geokguk_eval·structure_patterns·prediction·shadow specs) | 극 포함 | 극 제거(집합 의미 동일) |
| 일간 감당력 `_DM_CAPABILITY` | 극신약 −70 / 극신강 10 | 항목 제거(태 값 유지) |

검증: 025/L(壬寅×4, 점수 32.0)은 태신약→신약으로 라벨이 바뀌어도 종아격·follow 가 유지된다(점수 임계 덕).

## 4. 결과

| 항목 | 9단계 | 7단계 |
|---|---|---|
| 그리드 태·극 합 / 중화권 | 51% / 25% | **33% / 26%**(시뮬레이션) |
| 사례집 180 태 합 / 중화권 | 극·태 57% / 16% | **38% / 16%** |
| 사례집 최종 용희기구한 변경(C2 대비) | — | 1 (063/L — 밴드 변경으로 억부 분기 변경; 중화신약 상한 47 유지로 4건 보존) |
| 격국 변경 | — | 0 (025/L 종아격 유지) |
| 용신 기준 사주 6건 | — | **불변** |
| 사례집 지표(쌍/세운/대운/이벤트/위험) | 45.6/34.1/59.1/50.0/38.6 | 44.1/34.1/59.1/50.0/38.6 |
| 5역할 분할 불변식 | — | 위반 0 (§5 버그 수정 후) |

예측 지표는 변하지 않는다(쌍 1건 하락, 잡음). C3는 라벨 분포 교정이며 생애 변별은 C4 몫이다.

## 5. 함께 고친 잠재 버그

`_classify_bridge_roles`(통관 역할맵)에서 과다 출발축(병=기신)이 다른 모델의 희신 제안과 같은 오행이면 희신·기신이
같은 오행이 되는 경로가 있었다(080/R 己亥·丙子·辛巳·己丑: 밴드 전환으로 노출, 金/土/**土**/水/木). 병을 우선하고 희신은
폴백으로 다시 뽑도록 고쳤다 — 5역할 분할 불변식.

## 6. 변경 파일과 승인 항목

- 엔진: `strength/strength_score.py`, `shared_types/enums.py`, `yongsin/candidates.py`(_STRONG·veto·bridge 충돌·문구),
  `yongsin/special_cases.py`, `yongsin/role_realization.py`, `structure/geokguk_eval.py`, `saju_engines/prediction.py`,
  `structure_patterns.py`, `shadow_chart_specs.py`, `wealth_capacity.py`(주석).
- 사전·스냅샷(라벨 전용): `direction_suggestions.json`(bands 목록에서 극신약 제거)·`structure_patterns.json`(증거 문구) →
  같은 버전으로 재컴파일(내용 라벨만 변경, 규칙 수 동일 10/154).
- **골든 스냅샷 4건 갱신(승인 항목)**: australia_dst·uk_london_bst·us_newyork_dst 극신강→태신강, japan_tokyo 극신약→태신약.
- **테스트 갱신(승인 항목)**: `test_strength.py`(밴드 표·borderline 경계), `test_yongsin_decision_trace.py`(1965 problem
  "태신강"), `test_structure_patterns_f6_terms.py`(1980-01-20 태신약, 신왕 집합).
- 미갱신: `data/shadow_charts/coverage_report.json`의 predicate 문자열 3곳(생성 산출물, 테스트 미참조) — 다음 shadow
  재스캔 때 자동 갱신.
- 프론트엔드: 밴드 문자열을 그대로 표시하므로 코드 변경 없음(극 라벨이 더 이상 오지 않음).
