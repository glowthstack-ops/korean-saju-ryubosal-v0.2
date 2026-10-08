# C1-c — 종격(從格) 검출기 통일 변경안 (2026-10-08, 검토 단계·기존 결과만 사용)

> 배경: C1 기록(CASEBOOK_CALIBRATION_PLAN §6 2026-10-07) "종격을 격국 게이트에 맞추면 기준 차트 3종이 깨진다. 격국 종격 신호가 root_score<8 기준이라
> 교과서 종살격조차 신호 없음. 통일은 골든 8건에 닿는다" → 보류. 본 문서는 데굴님 지시(2026-10-08)대로 **새 실행 없이** 코드·테스트 기대값·기존 재생
> 산출물(`subjects_base_20261008.jsonl`, `JOHU_AB_2026-10-07.md`, `REPLAY_REPORT_2026-10-08.md`)만으로 차이와 예상 영향을 정리한다. 구현은 결정 후.

## 0. 요약

- 종격 판정 경로는 **세 개**다: ① 용신 `special_cases.py:79-86`(점수≤34 이고 root<8 **또는** 비겁·인성 세력비) ② 격국 `geokguk_eval.py:475`(점수≤34 **이고** root<8, override 는 conf≥0.70 즉 root≤3) ③ 격국 명확도 `geokguk_eval.py:383-385`(밴드 태신약 이고 root<8).
- 갈리는 원인은 `root_score`가 **인성 통근(0.65)과 중·여기**를 포함(`strength/rooting.py:25`)하는 데 있다. 교과서 종살 庚申庚申甲申庚午는 申중 壬(인성) 때문에 root≈30, 종재≈9.3, 종아≈20(수계산)이라 격국 쪽은 신호가 없고, 용신 쪽은 세력비 분기로 잡는다. 용신 쪽 주석(`special_cases.py:72-75`)이 이 결함을 이미 명시한다.
- 기준 3종 테스트는 **용신만** 검사한다. 따라서 "격국을 용신에 종속"(A)은 통과, "용신을 격국에 종속"은 실패.
- 골든 8건은 전부 정격이나 **japan_tokyo_standard(乙丑己卯癸丑己未)** 는 용신이 이미 `follow_structure`를 고르는데 격국은 식신격 — 통일 시 직접 영향 1건.
- 063/L은 root 7.0으로 용신 쪽 real 종격이지만 격국 conf 0.298<0.70이라 override=False → C1-a 조후 면제가 막혀 午월 조후 강등으로 火가 빠지고 土 병약이 남는다(현행 = C1 전과 동일). 통일(A) 시 R 과 같은 火 종격 역할표가 되어 壬戌 대운(+, 발재 사건 일치)이 R 처럼 −로 뒤집힐 가능성이 크다.
- **결정(2026-10-08 데굴님): C안 = 판정 통일이 아니라 불일치 관리 조치**(정합 경고·공통 상수 중복 제거·실제 불일치 사례에만 프론트 안내, 서로 다른 판정 임계값은 유지·기존 점수·역할·격국 불변). A안 보류·B안 미채택, 063/L·066은 상충 사례로 보존해 독립 사례 확보 후 재검토. 아래 원 권고 문장은 검토 기록으로 남긴다.
- (원 권고) C안 즉시, A안 보류 — 063/L(통일 시 악화 우려)과 066(전문가 "인비 필요" vs 용신 종재)이 서로 반대 방향이라 사례 근거가 상쇄된다. 추가 사례(Vol.3) 전까지 SSOT 전환 금지.

## 1. 현황 — 종격 판정 경로 3종

| 경로 | 위치 | 조건 | 출력 | 소비자 |
|---|---|---|---|---|
| ① 용신 특수격 | `yongsin/special_cases.py:79-86` | score≤FOLLOW_MAX_SCORE(34, strength_score.py) 이고 [root<8 → real] 또는 [peer<0.07·dom≥0.33 → res<0.12·dom≥0.40 real / res<0.28 pseudo] | `follow_structure.detail="real:officer:…"`, conf 0.85/0.5 | `candidates.py:2025-2055` 종격 모델(real=단독, pseudo=억부 병기), special 축 1.0(`:2187`) |
| ② 격국 특수 신호 | `structure/geokguk_eval.py:475-485` | score≤_FOLLOW_MAX_SCORE(34, **사본 상수** :51) 이고 root<8. 명칭은 십성 **개수**(천간3+지지본기4) 최대 그룹 | `special_pattern{type=follow, conf=min((10−root)/10, .9)}` | `geokguk.py:133-141` override = conf≥0.70(root≤3) → main_structure 치환 |
| ③ 격국 명확도 | `geokguk_eval.py:383-385` | band==태신약(≤30) 이고 root<8 | `clarity_level=special_pattern_uncertain`(×1.30) | 성패 가중 |
| 연결 | `candidates.py:2261` special_confirmed = override / `:2291-2299` 미확정 종격의 조후 역행은 강등(C1-c 안전장치) | — | — |
| 하류 | `luck_structure_flags.py:242-252`(override 시만) → 이벤트·위험 / **구조 패턴 JONG\*(`saju_engines/saju_engines/structure_patterns.py:261`, override 미확인)** / shadow predicate / 프론트 Panels(override 여부로 "특수격:"·"특수격 가능성:") | | |

## 2. 두 경로가 갈리는 조건

| 조건 | ① 용신 | ② 격국 | 사례 |
|---|---|---|---|
| score≤34, root<8 | real(special 1.0) | 신호 有, override는 root≤3 | 063/R(root 0, 둘 다 확정) |
| score≤34, **root≥8**, 세력비 충족(인성 뿌리가 지장간에만) | real/pseudo | **무신호** | 교과서 종살(root 30)·종재(≈9.3)·종아(≈20), 043/3, 066/L, japan_tokyo(≈14) |
| score≤34, 3<root<8 | real | 신호만(override F) → C1-a 면제 불가 → 조후 역행 시 강등 | **063/L(7.0)**, 082/3(7.0); 025/R(4.2)·046/L(4.7)은 조후 역행 없어 follow 유지 |
| 명칭 | 세력 가중 groups 최대 | 십성 개수 최대 | 다르게 나올 수 있음 |
| 임계 기준 | 점수(≤34) | 점수(≤34) + 밴드(태신약≤30, 명확도) | 30<score≤34 구간은 신호 有·명확도 無(025/L 31.99, 025/R 30.88) |

## 3. 기준 차트·골든·사례집 영향 자료

- 기준 테스트: `tests/unit/test_yongsin.py:315-345`(종살 庚申庚申甲申庚午 real:officer 金 / 종재 戊戌戊戌甲戌戊辰 土 / 종아 戊辰戊辰丙辰戊戌 土), `:348-363` 가종아(乙丑庚辰丁亥戊申 = 기준 사주 1985-04-18 사천, pseudo:output·support_day_master), `test_yongsin_decision_trace.py:166-187` 가전왕(1951-03-15). **전부 용신 결과만 고정**.
- 골든 `data/test_fixtures/manse/golden/*.json`(`test_golden_snapshots.py:54`) 8건 main_structure: 정인·정관·**식신(japan_tokyo, 태신약·용신 follow_structure 土)**·정재·정관·건록·건록·식신 — 태신강 3건은 dominant 경로(범위 밖).
- 사례집(`subjects_base_20261008.jsonl`) ①②불일치: 격국 무신호·용신 follow = 043/3·066/L(·japan) / 신호만·용신 follow = 025/R·046/L / 신호만·용신 real인데 조후 강등 = **063/L·082/3** / 둘 다 확정 = 025/L·031/R·063/R·066/M·R·082/1·2·4.
- 전문가 해설 대조: 066 "신약 甲, 재성 강, **인비 필요**" ↔ 용신 종재(土) **충돌**. 082 "상관·편관" 종격 전제 없음. 063 해설 없음(claims []).
- 063/L 데이터: score 28.0 태신약, 격국 상관격·패, special 종아격 conf 0.298 override F, final 土/火/木/水/金(disease_remedy:pyeonin_dosik), 壬戌 대운 **+**(발재 일치). 063/R: 종아격 특수격, final 火/木/水/金/土(follow_structure), 壬戌 대운 **−**.

## 4. 통일 후보와 예상 영향(기존 결과로만 추정, 새 실행 없음)

| 안 | 내용 | 기준 3종 | 골든 8건 | 사례집·기타 |
|---|---|---|---|---|
| **A. 격국 신호를 용신 검출기에 종속** | ② follow 분기를 ①(`detect_special_cases`) 결과로 대체: real→override, pseudo→신호만. 명칭 groups 기준 통일 | 통과(용신 불변) | **japan_tokyo 식신격→종격 1건 갱신** | 063/L·082/3 종격 용신(火·水)으로 전환 → 063/L 壬戌 대운 + → − 가능성 큼(악화). 043/3·066/L·025/R·046/L 격국만 특수격. 가종아 기준 사주에 JONG 패턴 emit 발생(패턴이 override 미확인). 066은 전문가 해설과 더 멀어짐 |
| **B. 격국 root 임계 상향** | ②의 8.0·게이트 0.70 상향 | 통과 | 종살(30)까지 잡으려면 임계>30 → 인성 뿌리 있는 태신약 전반이 신호를 받음, japan(≈14)·신약 3건까지 번질 위험 | root가 인성을 포함하는 구조 결함은 그대로. **권장 안 함** |
| **C. 두 경로 유지 + 정합 규칙** | (c1) ②에 `yongsin_follow_kind`·불일치 경고 필드 추가(표기 전용) (c2) `_FOLLOW_MAX_SCORE` 사본 → strength_score import (c3) JONG 패턴 emit 에 override 게이트 (c4) 프론트 "특수격 가능성:" 문구에 용신 판정 병기. **C1-a 면제 조건(`special_confirmed`)은 변경하지 않음** | 통과 | **0건 변경** | 점수·역할·지표 불변. 063/L·082/3 현행 유지. 가종아 패턴 emit 은 c3 로 오히려 차단(검토 필요: 현재 emit 되는지 확인 후) |

## 5. 권고와 결정 요청

| # | 결정 | 권고 | 근거 |
|---|---|---|---|
| E1 | C안 c1·c2·c4 적용(표기·상수 정리, 점수 불변) | 승인 검토 | 골든 0건, 프론트 정격/종격 표기 불일치 해소 |
| E2 | C안 c3(JONG 패턴 override 게이트) | 영향 확인 후 결정 | 구조 패턴 사전 출력이 바뀌는 명식 수를 기존 산출물로 세어 보고 |
| E3 | A안(SSOT = 용신 검출기) | **보류** | 063/L(통일 시 악화 우려) vs 066(용신 종재가 전문가와 충돌) — 사례 근거 상쇄, Vol.3 후 재검토. C1-a 면제 조건 완화도 같은 이유로 보류 |
| E4 | B안 | 기각 | 구조 결함 미해소·확산 위험 |
| E5 | 확인 사항: C3 기록 "C2 대비 063/L 역할 변경 1건"이 `subjects_c2.jsonl`(土/火/木/水/金 동일)과 맞지 않음 | 기록 정정 또는 산출물 재확인 | 기존 산출물 대조 |
| E6 | root_score 의 인성 포함을 종격 판정용 "비겁 뿌리 점수"와 분리하는 설계(장기) | 별도 과제 | `special_cases.py:72-75` 주석이 지적한 결함의 근본 해소, 명리 규칙 변경이라 승인 사항 |

## 6. C안 구현 기록 (2026-10-08 — **불일치 관리 완료**, 판정 통일 아님; c3 override 게이트는 보류 유지)

| 조치 | 변경 | 검증 |
|---|---|---|
| c2 공통 상수 | `geokguk_eval._FOLLOW_MAX_SCORE` 사본 제거 → `strength_score.FOLLOW_MAX_SCORE` import(값 34 동일, 판정 임계 불변) | `test_follow_max_score_single_source` |
| c1 정합 표기 | `GeokgukResult.follow_consistency: dict|None` 신설(`geokguk._follow_consistency`): 어느 한쪽이라도 종격을 보면 `{status: consistent|mismatch, geokguk_signal, geokguk_override, geokguk_label, yongsin_follow_kind, yongsin_label, note}` 기록. consistent = 격국 override 종격 ∧ 용신 진종. `main_structure`·`special_pattern`·점수·역할 불변(special_pattern 을 새로 만들지 않아 JONG 패턴 emit·운 특수격 플래그 등 하류 불변) | `test_mismatch_when_only_yongsin_detects_follow`(japan_tokyo: 식신격 유지·mismatch), `test_consistent_when_both_confirm`(jonggyeok_01), `test_none_when_neither_detects`(1980-11-22) |
| c4 프론트 | `Panels.tsx` 격국 패널: `follow_consistency.status === "mismatch"` 인 명식에만 "종격 판단이 기준에 따라 다릅니다" + 격국/용신 기준 라벨 + 설명. 일치·해당 없음은 표시 없음 | `tsc --noEmit` exit 0, production build 성공 |
| c3 JONG 패턴 override 게이트 | **미적용**(E2 — 영향 확인 후 별도 결정) | — |
| 미변경 | 서로 다른 판정 임계값(격국 root<8·override root≤3 / 용신 세력비) 유지, C1-a 면제 조건(`special_confirmed`) 유지 | 회귀 골든 8건·용신·격국·shadow spec 테스트 통과 |

E5 정정: C3 기록의 "C2 대비 063/L 역할 변경 1건"은 `subjects_c2.jsonl`과 현재 산출물의 063/L final 이 동일하고 C3 시점 산출물이 없어 **변경 확인 불가**로 계획서·C3 문서에 명시했다.
