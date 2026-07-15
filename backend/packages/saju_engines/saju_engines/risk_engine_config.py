"""위험 엔진 게이트 설정 — 마스터 게이트 상수 (RISK_ENGINE.md §게이트).

sinsal_modifier_config(byte-identical off 게이트)·marriage_timing_profile(1줄 전환) 선례를
따르는 3단계 mode다. 기본 OFF — 위험 계산 자체를 하지 않아 기존 출력이 byte-identical이다.

- "off": 계산하지 않음(수집·매칭 코드 미실행).
- "shadow": 원시 신호 수집 + 원자 후보 생성. 결과는 EventEngineV2.risk_shadow 사이드채널에만
  기록하며 사용자 답변·리포트·LLM 입력·토큰에 일절 주입하지 않는다(구조화 로그/QA 전용).
- "expose": R3(답변 계약·임계값) 배선 전까지는 shadow와 동일하게 동작한다 — 노출 배선은
  별도 세분 게이트와 함께 사용자 승인 후 추가한다.

전환은 이 상수 1줄 수정(또는 테스트 monkeypatch)으로 한다. EventEngineV2가 score() 호출
시점에 읽으므로 재기동 없이 테스트에서 패치 가능하다.
"""

from __future__ import annotations

# 위험 엔진 모드 — RiskEngineMode 값("off" | "shadow" | "expose"). 기본 off(승격은 사용자 승인).
RISK_ENGINE_MODE: str = "off"
