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

import os as _os


def _env_mode(default: str) -> str:
    """모드 env override(r4.1.0-canary 운영 활성화 — 통합 감수 §5).

    허용값 밖·미설정=기본값(off) — env 오타·오염으로 켜지는 경로 없음
    (fail-closed). 코드 기본값은 계속 "off"라 env 없인 아무것도 안 켜진다.
    """
    raw = (_os.environ.get("RISK_ENGINE_MODE") or "").strip().lower()
    return raw if raw in ("off", "shadow", "expose_canary",
                          "expose") else default


def _env_flag(name: str, default: bool) -> bool:
    """boolean env override — 정확히 "true"/"1"만 True(그 외=기본값)."""
    raw = (_os.environ.get(name) or "").strip().lower()
    if raw in ("true", "1"):
        return True
    if raw in ("false", "0"):
        return False
    return default


# 위험 엔진 모드 — RiskEngineMode 값("off" | "shadow" | "expose_canary" |
# "expose"). 기본 off — canary 활성화는 운영 preflight(통합 감수 §5:
# HMAC 운영 키→topology·worker=1→allowlist→태그 배포) 후 env로만.
RISK_ENGINE_MODE: str = _env_mode("off")

# 전역 kill switch(감수 45·46차 — 게이트 최앞): True면 mode 무관 비주입.
# 긴급 중단용 — 계산 자체 차단이 필요하면 RISK_ENGINE_MODE="off"를 함께 쓴다.
RISK_EXPOSURE_KILL_SWITCH: bool = False

# canary allowlist(감수 46차 §14) — **인증된 내부 subject ID만**(클라이언트
# 전달 ID·이메일 원문·쿠키 미검증 값·질문 본문 플래그 금지). 조회 실패·ID
# 부재=비주입. 로그에는 원문 대신 해시/코호트 ID를 남긴다.
RISK_EXPOSE_CANARY_SUBJECT_IDS: frozenset[str] = frozenset(
    s.strip() for s in
    (_os.environ.get("RISK_EXPOSE_CANARY_SUBJECT_IDS") or "").split(",")
    if s.strip())

# 런타임 활성화 스위치(감수 48차 §4 — 역할 분리): 감수 사실의 SSOT는
# **manifest**(expose_pipeline.reviewed + expose_policy_hash 일치)이고,
# 이 값은 "감수된 기능을 현 환경에서 켤지"만 결정한다. 환경변수가 스스로
# reviewed=true를 선언할 수 없다 — 둘 중 하나만 true면 절대 주입되지 않음
# (fixture 강제). 기본 False.
RISK_EXPOSURE_RUNTIME_ENABLED: bool = _env_flag(
    "RISK_EXPOSURE_RUNTIME_ENABLED", False)

# suspension backend·배포 topology(감수 55차 §6): 파일 backend는
# single_host_shared_state에서만 전역 suspension이다 — 미지원 조합이면
# EXPOSE 해소가 BYPASS된다(다중 호스트=공유 저장소 backend 필요).
RISK_SUSPENSION_BACKEND: str = "file"
RISK_DEPLOYMENT_TOPOLOGY: str = (
    _os.environ.get("RISK_DEPLOYMENT_TOPOLOGY")
    or "single_host_shared_state").strip()
_SUPPORTED_SUSPENSION_COMBOS: frozenset[tuple[str, str]] = frozenset({
    ("file", "single_host_shared_state"),
    ("file", "single_host_single_process"),
})
# canary 자격 조합(감수 56차 §4): suspension 기록과 전역 marker 기록이
# **둘 다** 실패해도 다른 worker의 위험 주입이 남지 않는 조합만 — 파일
# backend는 로컬 flag가 곧 전역이 되는 단일 프로세스 topology뿐이다.
# multi-worker 유지 시에는 공유 저장소 backend(Redis·DB)·supervisor 전역
# kill switch 등으로 교체·보강 후 이 집합에 조합을 추가한다(재감수 필요).
_CANARY_ELIGIBLE_SUSPENSION_COMBOS: frozenset[tuple[str, str]] = frozenset({
    ("file", "single_host_single_process"),
})

# claim audit evidence용 HMAC 키(감수 52차 §6): 짧은 한국어 절의 사전
# 대입 추정을 막기 위해 clause hash는 단순 SHA가 아니라 keyed HMAC.
# **운영 배포 전 환경별 secret으로 교체·주기 회전 필수**(원문과 secret
# 동시 보관 금지) — 기본값은 개발·테스트 전용.
# 운영 키는 RISK_AUDIT_HMAC_KEY_B64 환경변수(base64, decode 후 32바이트
# 이상 — 통합 감수 §6)로 주입: 소스·manifest·로그에 값 저장 금지(로그엔
# 유효성 결과만). 미설정·비정상=dev 기본키 → AUDIT_HMAC_KEY_INVALID로
# EXPOSE 전부 BYPASS(fail-closed).
def _env_hmac_key(default: bytes) -> bytes:
    raw = (_os.environ.get("RISK_AUDIT_HMAC_KEY_B64") or "").strip()
    if not raw:
        return default
    import base64
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception:  # noqa: BLE001 — 비정상 인코딩=기본키(차단 유지)
        return default
    return key if len(key) >= 32 else default


RISK_AUDIT_HMAC_KEY: bytes = _env_hmac_key(
    b"dev-only-rotate-before-canary")

# canary 초기 허용 질문 유형(감수 46차 §3 — 감수 5유형 중 3유형만 1차 개방,
# compare·followup은 맥락 혼합이 잦아 2차 확대).
RISK_CANARY_QUESTION_TYPES: tuple[str, ...] = (
    "specific_event", "single_domain_period", "period_overview",
)
