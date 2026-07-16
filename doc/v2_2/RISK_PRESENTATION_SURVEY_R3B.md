> R3-b 노출 전수 측정 고정본(감수 43차 확정 반영 — warning 0.25·conf 0.75 확정, watch 0.12·critical 0.40 shadow 확정, budget 1024/512·보수 estimator·fail-closed, shadow_presentation 49/49) — 재생성: `python scripts/risk_presentation_survey.py`
> 출력 결정적 — 본 파일과의 diff = 노출 의미 회귀 신호.

# R3-b 위험 노출 전수 측정 — risk-present-r3.1.0-shadow
presentation_policy fa183fbeea946528 — 밴드(0.40/0.25/0.12)·critical conf 하한 0.5 전부 잠정(본 측정이 감수 재료)

## profile A_all_unknown — presentation 분포(단위: episode 건수 — 10차트 합산)
  전체 episode(선택 전 — 잠재 구조 포함): critical 0 · warning 0 · watch 89 · advisory 126 · none 520
  budget 선택 후(warning_episode_count 등 — hard_max 3 적용): critical 0 · warning 0 · watch 21 · advisory 9 · none 0
  도메인별(선택): career[watch:4 advisory:3] / finance[watch:14] / health_safety[advisory:6] / relationship[watch:3]
  kind별(선택): incident_risk[watch:14] / pressure[watch:7 advisory:9]
  강등: unique episodes 13 · primary EXPOSURE_POLICY_CEILING 10 · INCIDENT_UNKNOWN_CAP 3 · all EXPOSURE_POLICY_CEILING 10 · INCIDENT_UNKNOWN_CAP 4
  omission(none): 없음
  critical 전수: 0건(정상 — 개수를 만들기 위한 경계 하향 금지)
  claim 검증: partial qualifier 누락 0 · 충돌 제거(참고) 0 · 전역 prohibited 7코드 payload 최상단 상존

## profile B_typical_confirmed — presentation 분포(단위: episode 건수 — 10차트 합산)
  전체 episode(선택 전 — 잠재 구조 포함): critical 0 · warning 4 · watch 100 · advisory 123 · none 488
  budget 선택 후(warning_episode_count 등 — hard_max 3 적용): critical 0 · warning 4 · watch 21 · advisory 5 · none 0
  도메인별(선택): career[watch:3 advisory:2] / contract_legal[watch:5] / finance[watch:7] / health_safety[advisory:3] / relationship[warning:4 watch:6]
  kind별(선택): incident_risk[watch:9] / pressure[warning:4 watch:12 advisory:5]
  강등: unique episodes 13 · primary EXPOSURE_POLICY_CEILING 6 · INCIDENT_UNKNOWN_CAP 2 · ITEM_CLAIM_CEILING 5 · all EXPOSURE_POLICY_CEILING 6 · INCIDENT_UNKNOWN_CAP 3 · ITEM_CLAIM_CEILING 5
  omission(none): 없음
  critical 전수: 0건(정상 — 개수를 만들기 위한 경계 하향 금지)
  claim 검증: partial qualifier 누락 0 · 충돌 제거(참고) 0 · 전역 prohibited 7코드 payload 최상단 상존

## profile C_high_exposure — presentation 분포(단위: episode 건수 — 10차트 합산)
  전체 episode(선택 전 — 잠재 구조 포함): critical 0 · warning 14 · watch 103 · advisory 108 · none 428
  budget 선택 후(warning_episode_count 등 — hard_max 3 적용): critical 0 · warning 14 · watch 12 · advisory 4 · none 0
  도메인별(선택): career[watch:2 advisory:2] / contract_legal[watch:4] / finance[watch:4] / health_safety[warning:3 advisory:2] / relationship[warning:5 watch:2] / relocation[warning:6]
  kind별(선택): incident_risk[warning:6 watch:6] / pressure[warning:8 watch:6 advisory:4]
  강등: unique episodes 15 · primary EXPOSURE_POLICY_CEILING 5 · INCIDENT_UNKNOWN_CAP 2 · ITEM_CLAIM_CEILING 8 · all EXPOSURE_POLICY_CEILING 5 · INCIDENT_UNKNOWN_CAP 3 · ITEM_CLAIM_CEILING 8
  omission(none): 없음
  critical 전수: 0건(정상 — 개수를 만들기 위한 경계 하향 금지)
  claim 검증: partial qualifier 누락 0 · 충돌 제거(참고) 0 · 전역 prohibited 7코드 payload 최상단 상존

## profile D_multi_selection — presentation 분포(단위: episode 건수 — 10차트 합산)
  전체 episode(선택 전 — 잠재 구조 포함): critical 0 · warning 15 · watch 104 · advisory 126 · none 473
  budget 선택 후(warning_episode_count 등 — hard_max 3 적용): critical 0 · warning 11 · watch 13 · advisory 6 · none 0
  도메인별(선택): career[watch:1 advisory:3] / finance[watch:4] / health_safety[advisory:3] / selection[warning:11 watch:8]
  kind별(선택): incident_risk[warning:11 watch:11] / pressure[watch:2 advisory:6]
  강등: unique episodes 8 · primary EXPOSURE_POLICY_CEILING 6 · INCIDENT_UNKNOWN_CAP 1 · ITEM_CLAIM_CEILING 1 · all EXPOSURE_POLICY_CEILING 6 · INCIDENT_UNKNOWN_CAP 1 · ITEM_CLAIM_CEILING 1
  omission(none): 없음
  critical 전수: 0건(정상 — 개수를 만들기 위한 경계 하향 금지)
  claim 검증: partial qualifier 누락 0 · 충돌 제거(참고) 0 · 전역 prohibited 7코드 payload 최상단 상존

## profile E_reality_linked — presentation 분포(단위: episode 건수 — 10차트 합산)
  전체 episode(선택 전 — 잠재 구조 포함): critical 0 · warning 7 · watch 95 · advisory 108 · none 491
  budget 선택 후(warning_episode_count 등 — hard_max 3 적용): critical 0 · warning 7 · watch 17 · advisory 6 · none 0
  도메인별(선택): career[watch:4 advisory:2] / contract_legal[warning:1 watch:4] / finance[watch:8] / health_safety[warning:3 advisory:4] / relationship[watch:1] / relocation[warning:4 watch:4]
  kind별(선택): incident_risk[warning:4 watch:10] / pressure[warning:3 watch:7 advisory:6]
  강등: unique episodes 17 · primary EXPOSURE_POLICY_CEILING 7 · INCIDENT_UNKNOWN_CAP 3 · ITEM_CLAIM_CEILING 7 · all EXPOSURE_POLICY_CEILING 7 · INCIDENT_UNKNOWN_CAP 4 · ITEM_CLAIM_CEILING 7
  omission(none): 없음
  critical 전수: 0건(정상 — 개수를 만들기 위한 경계 하향 금지)
  claim 검증: partial qualifier 누락 0 · 충돌 제거(참고) 0 · 전역 prohibited 7코드 payload 최상단 상존

## token guard 실측(선택 집합·프로필 C 기준 — 보수 estimator·512 미만/compact 초과=fail-closed 비주입)
  budget 256: tier SUPPRESSED(fail-closed) 10 · fail-closed 비주입 차트 10 · episode 주입 0/30 · 전역 dedup 절감(반복 대비) ≈0 tokens
  budget 512: tier P0_COMPACT 10 · fail-closed 비주입 차트 0 · episode 주입 30/30 · 전역 dedup 절감(반복 대비) ≈2093 tokens
  budget 1024: tier P1 6 · P2(full) 4 · fail-closed 비주입 차트 0 · episode 주입 30/30 · 전역 dedup 절감(반복 대비) ≈2093 tokens
  budget 2048: tier P2(full) 10 · fail-closed 비주입 차트 0 · episode 주입 30/30 · 전역 dedup 절감(반복 대비) ≈2093 tokens
  최소 주입 표현(P0_COMPACT) 토큰(차트별): p50 272 · max 285

## 경계 국소 민감도(단위: 선택 후 episode 건수 — C 프로필 10차트 합산, 한 축씩)
  watch=0.10: critical:0 warning:14 watch:12 advisory:4 none:0
  watch=0.12: critical:0 warning:14 watch:12 advisory:4 none:0
  watch=0.15: critical:0 warning:14 watch:12 advisory:4 none:0
  warning=0.22: critical:0 warning:16 watch:10 advisory:4 none:0
  warning=0.25: critical:0 warning:14 watch:12 advisory:4 none:0
  warning=0.28: critical:0 warning:12 watch:14 advisory:4 none:0
  critical=0.35: critical:0 warning:14 watch:12 advisory:4 none:0
  critical=0.40: critical:0 warning:14 watch:12 advisory:4 none:0
  critical=0.45: critical:0 warning:14 watch:12 advisory:4 none:0
  critical_min_conf=0.50: critical:0 warning:14 watch:12 advisory:4 none:0
  critical_min_conf=0.65: critical:0 warning:14 watch:12 advisory:4 none:0
  critical_min_conf=0.75: critical:0 warning:14 watch:12 advisory:4 none:0
