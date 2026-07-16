> R1-b/c0 표본 감수 고정본(감수 27·28차) — 재생성: `python scripts/risk_scoring_sample.py`
> 출력 결정적 — 본 파일과의 diff = 점수 의미 회귀 신호.

# R1-b/c0 위험 점수 표본 리포트 — risk-score-r1.0.3-shadow
cause semantics: cause-semantics-v2 · scoring_config_hash=ea789b931ee68d29 · cause_semantics_hash=9f2e80bd80731edb
감수 대상 = 절대 점수가 아니라 표본별 예상 불변식(PASS/FAIL).

## 표본 1 — cause identity(관계 원자 + 비관계 전역 namespace)
    SMP_A@2026 elig=eligible exposable=True | occ=0.500 imp=0.00 exp=0.55 per=0.00 cmp=0.25 prot=0.00 | structural=0.000 rankable raw=0.250 capped=0.250 conf=0.40
    SMP_B@2026 elig=eligible exposable=True | occ=0.500 imp=0.00 exp=0.55 per=0.00 cmp=0.00 prot=0.00 | structural=0.000 rankable raw=0.000 capped=0.000 conf=0.40
    SMP_C@2026 elig=eligible exposable=True | occ=0.500 imp=0.00 exp=0.55 per=0.00 cmp=0.00 prot=0.00 | structural=0.000 rankable raw=0.000 capped=0.000 conf=0.40
    SMP_D@2026 elig=eligible exposable=True | occ=0.500 imp=0.00 exp=0.55 per=0.00 cmp=0.25 prot=0.00 | structural=0.000 rankable raw=0.250 capped=0.250 conf=0.60
    SMP_G@2026 elig=eligible exposable=True | occ=0.500 imp=0.00 exp=0.55 per=0.00 cmp=0.00 prot=0.00 | structural=0.000 rankable raw=0.000 capped=0.000 conf=0.40
  [PASS] 같은 충+다른 대상 → cause row 2
  [PASS] 같은 대상+다른 관계(충/형) → cause row 2
  [PASS] 같은 대상·관계 다층 → cause row 1(+supporting layer)
  [PASS] semantic registry: ten_god만 CAUSE row — void/stage/no_void 진입 금지
  [PASS] 상태 원자(void/stage/no_void) 추가 → occurrence 불변
  [PASS] 미상 namespace 거부

## 표본 2 — exposure 정책(rankable 가중)
    SMP_RISK@2026 elig=eligible exposable=True | occ=0.500 imp=0.60 exp=1.00 per=0.00 cmp=0.00 prot=0.00 | structural=0.300 rankable raw=0.300 capped=0.300 conf=0.40
    SMP_RISK@2026 elig=eligible exposable=True | occ=0.500 imp=0.60 exp=0.55 per=0.00 cmp=0.00 prot=0.00 | structural=0.300 rankable raw=0.165 capped=0.165 conf=0.40
    SMP_RISK@2026 elig=eligible exposable=False | occ=0.500 imp=0.60 exp=0.00 per=0.00 cmp=0.00 prot=0.00 | structural=0.300 rankable raw=0.000 capped=0.000 conf=0.40
    SMP_RISK@2026 elig=eligible exposable=True | occ=0.500 imp=0.60 exp=0.00 per=0.00 cmp=0.00 prot=0.00 | structural=0.300 rankable raw=0.000 capped=0.000 conf=0.40
    SMP_RISK@2026 elig=eligible exposable=False | occ=0.500 imp=0.60 exp=0.00 per=0.00 cmp=0.00 prot=0.00 | structural=0.300 rankable raw=0.000 capped=0.000 conf=0.40
    SMP_RISK@2026 elig=eligible exposable=False | occ=0.500 imp=0.60 exp=0.00 per=0.00 cmp=0.00 prot=0.00 | structural=0.300 rankable raw=0.000 capped=0.000 conf=0.40
  [PASS] CONFIRMED(1.0) > 허용 UNKNOWN(0.55) > 나머지 0
  [PASS] DENIED도 구조 진단은 보존(structural > 0)

## 표본 3 — structural exposure 불변
    SMP_A@2026 elig=eligible exposable=True | occ=0.500 imp=0.60 exp=1.00 per=0.00 cmp=0.25 prot=0.00 | structural=0.300 rankable raw=0.550 capped=0.550 conf=0.40
    SMP_B@2026 elig=eligible exposable=True | occ=0.400 imp=0.50 exp=1.00 per=0.00 cmp=0.25 prot=0.00 | structural=0.200 rankable raw=0.450 capped=0.450 conf=0.40
    SMP_A@2026 elig=eligible exposable=True | occ=0.500 imp=0.60 exp=0.00 per=0.00 cmp=0.00 prot=0.00 | structural=0.300 rankable raw=0.000 capped=0.000 conf=0.40
    SMP_B@2026 elig=eligible exposable=True | occ=0.400 imp=0.50 exp=0.00 per=0.00 cmp=0.00 prot=0.00 | structural=0.200 rankable raw=0.000 capped=0.000 conf=0.40
  [PASS] structural priority 동일
  [PASS] 구조 compound 연결(exposure 무관) 동일
  [PASS] rankable compound: CONFIRMED만 양수

## 표본 4 — compound 독립 효과군
    SMP_A@2026 elig=eligible exposable=True | occ=0.500 imp=0.00 exp=0.55 per=0.00 cmp=0.00 prot=0.00 | structural=0.000 rankable raw=0.000 capped=0.000 conf=0.40
  [PASS] compound(같은 family alias) = 0.0
    SMP_A@2026 elig=eligible exposable=True | occ=0.500 imp=0.00 exp=0.55 per=0.00 cmp=0.00 prot=0.00 | structural=0.000 rankable raw=0.000 capped=0.000 conf=0.40
  [PASS] compound(흡수 supporting) = 0.0
    SMP_A@2026 elig=eligible exposable=True | occ=0.500 imp=0.00 exp=0.55 per=0.00 cmp=0.00 prot=0.00 | structural=0.000 rankable raw=0.000 capped=0.000 conf=0.40
  [PASS] compound(비노출 vulnerability) = 0.0
    SMP_A@2026 elig=eligible exposable=True | occ=0.500 imp=0.00 exp=0.55 per=0.00 cmp=0.25 prot=0.00 | structural=0.000 rankable raw=0.250 capped=0.250 conf=0.40
  [PASS] compound(독립 exposable 다른 family) = 0.25

## 표본 5 — persistence(연속성·직렬화 구분)
    SMP_RUN@2026-01 elig=eligible exposable=True | occ=0.500 imp=0.00 exp=0.55 per=0.40 cmp=0.00 prot=0.00 | structural=0.400 rankable raw=0.400 capped=0.400 conf=0.40
    SMP_GAP@2026-01 elig=eligible exposable=True | occ=0.500 imp=0.00 exp=0.55 per=0.00 cmp=0.00 prot=0.00 | structural=0.000 rankable raw=0.000 capped=0.000 conf=0.40
    SMP_BND@2026-12 elig=eligible exposable=True | occ=0.500 imp=0.00 exp=0.55 per=0.40 cmp=0.00 prot=0.00 | structural=0.400 rankable raw=0.400 capped=0.400 conf=0.40
    SMP_SER@2026-01 elig=eligible exposable=True | occ=0.500 imp=0.00 exp=0.55 per=0.00 cmp=0.00 prot=0.00 | structural=0.000 rankable raw=0.000 capped=0.000 conf=0.40
  [PASS] 연속 3개월 = 0.4
  [PASS] 간헐 3회 = 0.0(run 1)
  [PASS] 연도 경계(12→01→02)도 연속 3 = 0.4
  [PASS] 세운 원인 12개월 직렬화 = 0.0(native 발동 아님)
  [PASS] 직렬화가 occurrence를 바꾸지 않음

## 표본 6 — 다중 selection episode 공유 원인(엔진 실후보)
    SEL_RESULT_DELAY_PRESSURE@2026/exam_1 elig=mitigated exposable=True | occ=0.610 imp=0.40 exp=1.00 per=0.00 cmp=0.00 prot=0.30 | structural=-0.056 rankable raw=-0.056 capped=0.000 conf=0.60
    SEL_RESULT_DELAY_PRESSURE@2026/exam_2 elig=mitigated exposable=True | occ=0.610 imp=0.40 exp=1.00 per=0.00 cmp=0.00 prot=0.30 | structural=-0.056 rankable raw=-0.056 capped=0.000 conf=0.60
  [PASS] 후보 = 2(episode별 보존)
  [PASS] 공유 원인의 cause row = 기간당 1
  [PASS] 두 후보 occurrence 동일(1회 계산 참조)
  [PASS] compound가 episode 수로 증가하지 않음(같은 risk_id·family)

## 표본 7 — protection vs recovery
    SMP_RISK@2026 elig=eligible exposable=True | occ=0.500 imp=0.60 exp=0.55 per=0.00 cmp=0.00 prot=0.00 | structural=0.300 rankable raw=0.165 capped=0.165 conf=0.40
    SMP_RISK@2026 elig=eligible exposable=True | occ=0.500 imp=0.60 exp=0.55 per=0.00 cmp=0.00 prot=0.40 | structural=-0.100 rankable raw=-0.235 capped=0.000 conf=0.40
    SMP_RISK@2026 elig=eligible exposable=True | occ=0.500 imp=0.60 exp=0.55 per=0.00 cmp=0.00 prot=0.00 | structural=0.300 rankable raw=0.165 capped=0.165 conf=0.40
  [PASS] 보호 조건이 occurrence를 낮추지 않음
  [PASS] 실질 mitigator → protection > 0 → net priority 완화
  [PASS] 극성 단독 mitigator → protection 0(전역 완화 금지)
    (미래 회복 창은 R0.5 후보에 존재하지 않음 — recovery는 R2 recovery_window 소관, 현재 축 어디에도 반영 경로 없음: 구조적 보장)

## 종합: 27개 불변식 중 FAIL 0건
