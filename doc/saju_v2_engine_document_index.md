# 사주서비스 v2 — 안정적 만세력 엔진 문서 인덱스

> 목적: LLM에 의존하지 않는 안정적 만세력 엔진을 구축하기 위한 전체 설계 문서 목록과 권장 읽기 순서.

## 1. 권장 읽기 순서

01. `saju_v2_greenfield_milestone_structure.md` — Greenfield 신규 시스템 마일스톤 및 초기 구조
02. `saju_v2_manse_engine_codex_spec.md` — v2 만세력 엔진 전체 Codex 구현 지시서
03. `saju_v2_location_timezone_true_solar_spec.md` — 해외 출생 지원용 지역·타임존·DST·진태양시 보정
04. `saju_v2_pillar_calculation_spec.md` — 년주·월주·일주·시주 간지 산출
05. `saju_v2_five_element_distribution_algorithm.md` — 오행분포 계산 알고리즘
06. `saju_v2_ten_god_distribution_algorithm.md` — 십성분포 계산 알고리즘
07. `saju_v2_force_analysis_integration_spec.md` — 오행/십성/통근/신강약 연동 세력분석
08. `saju_v2_strength_9_band_algorithm.md` — 신강·신약 9단계 점수 알고리즘
09. `saju_v2_structure_relation_spec.md` — 합충형파해·합화·궁성 구조 작용
10. `saju_v2_geokguk_analysis_spec.md` — 격국 분석
11. `saju_v2_yongsin_candidate_algorithm.md` — 용신 후보 산출
12. `saju_v2_luck_cycle_calculation_spec.md` — 대운·세운·월운 계산
13. `saju_v2_yongsin_calibration_loop_spec.md` — 용신 검증 루프
14. `saju_v2_five_element_distribution_tests.md` — 오행분포 테스트/엣지케이스
15. `saju_v2_stable_engine_validation_spec.md` — 전체 엔진 검증·회귀 테스트

## 2. 구현 우선순위

```text
Phase 0: Greenfield 구조 + schema + API skeleton
Phase 1: 지역/시간 보정 + 절기 + 간지 산출
Phase 2: 오행분포 + 십성분포 + 세력분석
Phase 3: 신강약 9단계 + 구조 작용 + 격국
Phase 4: 용신 후보 + 대운/세운/월운 + 검증 루프
Phase 5: 회귀 테스트 고정 + UI/서비스 연결
```

## 3. 엔진 절대 원칙

```text
1. LLM은 사주를 계산하지 않는다.
2. 모든 계산은 deterministic engine에서 수행한다.
3. 해외 출생은 IANA timezone + 역사적 DST + 좌표 기반으로 처리한다.
4. 진태양시 적용 전후 시주 변화 여부를 반드시 표시한다.
5. 월주는 음력 월이 아니라 절기 기준이다.
6. 오행분포/십성분포/신강약/용신은 모두 분리된 레이어다.
7. 용신은 최초에는 candidate이며, 사용자 검증 후 calibrated가 된다.
8. 계산 결과에는 data version과 trace가 남아야 한다.
```

## 4. Codex 첫 작업 지시

```text
이 문서 묶음을 기준으로 v1 리팩터링이 아니라 신규 Greenfield 시스템을 생성한다.
먼저 shared-types, manse-core, manse-analysis, manse-calibration 패키지를 만들고,
Mock API가 전체 ManseV2Result schema를 반환하도록 구현한다.
그 다음 지역/시간 보정 → 간지 산출 → 오행/십성분포 → 신강약 순으로 실제 계산을 채운다.
```
