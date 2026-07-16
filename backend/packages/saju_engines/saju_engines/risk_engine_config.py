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

# 위험 엔진 모드 — RiskEngineMode 값("off" | "shadow" | "expose_canary" |
# "expose"). 기본 off(승격은 사용자 승인 — canary는 R5-b 통합·expose_pipeline
# 감수 후에만).
RISK_ENGINE_MODE: str = "off"

# 전역 kill switch(감수 45·46차 — 게이트 최앞): True면 mode 무관 비주입.
# 긴급 중단용 — 계산 자체 차단이 필요하면 RISK_ENGINE_MODE="off"를 함께 쓴다.
RISK_EXPOSURE_KILL_SWITCH: bool = False

# canary allowlist(감수 46차 §14) — **인증된 내부 subject ID만**(클라이언트
# 전달 ID·이메일 원문·쿠키 미검증 값·질문 본문 플래그 금지). 조회 실패·ID
# 부재=비주입. 로그에는 원문 대신 해시/코호트 ID를 남긴다.
RISK_EXPOSE_CANARY_SUBJECT_IDS: frozenset[str] = frozenset()

# expose_pipeline 감수 상태(감수 47차) — R5-b 통합·감수 완료 후에만 True
# (manifest expose_pipeline.reviewed와 함께 전환). False면 게이트가
# BYPASS(프롬프트 완전 불변)로 처리한다.
RISK_EXPOSE_PIPELINE_REVIEWED: bool = False

# canary 초기 허용 질문 유형(감수 46차 §3 — 감수 5유형 중 3유형만 1차 개방,
# compare·followup은 맥락 혼합이 잦아 2차 확대).
RISK_CANARY_QUESTION_TYPES: tuple[str, ...] = (
    "specific_event", "single_domain_period", "period_overview",
)
