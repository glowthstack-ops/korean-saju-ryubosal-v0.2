"""Health check."""

from __future__ import annotations

import os

from fastapi import APIRouter

from saju_shared_types.constants import ENGINE_VERSION

router = APIRouter(tags=["health"])


def _beta_flag_snapshot() -> dict[str, bool]:
    """테스터 beta flag 실효값 — env가 아니라 **모듈 상수**를 읽는다.

    flag는 import 시점에 상수로 굳으므로 env만 보면 "env에는 켰는데 실제 분기는
    off"인 상태를 구분할 수 없다. 실제 분기에 쓰이는 값을 그대로 노출해, 켜졌는지
    런타임에서 확인할 수단을 준다. 값 자체는 노출 여부일 뿐 비밀이 아니다.
    """
    flags: dict[str, bool] = {}
    try:
        from ..services import relationship_shadow as _rel

        flags["relationship_beta_expose"] = bool(_rel.RELATIONSHIP_BETA_EXPOSE)
        flags["relationship_risk_beta_expose"] = bool(_rel.RELATIONSHIP_RISK_BETA_EXPOSE)
    except Exception:  # noqa: BLE001 — 관측 실패가 health를 막지 않는다
        pass
    try:
        from saju_engines import career_chat_consumer as _career

        flags["career_transition_chat_enabled"] = bool(
            _career.CAREER_TRANSITION_CHAT_ENABLED
        )
        flags["career_transition_chat_beta_expose"] = bool(
            _career.CAREER_TRANSITION_CHAT_BETA_EXPOSE
        )
    except Exception:  # noqa: BLE001
        pass
    flags["daily_fortune_pregen"] = os.getenv("SAJU_DAILY_FORTUNE_PREGEN") == "1"
    try:
        # 오늘의 운세 3층 판정 모델(docs/17 §22) — 어느 채점 경로가 활성인지 노출한다.
        from saju_engines import daily_fortune_v2 as _dfv2

        flags["daily_fortune_model_v2"] = bool(_dfv2.DAILY_FORTUNE_MODEL_V2_ENABLED)
    except Exception:  # noqa: BLE001
        pass
    try:
        # 상담 결론 의미론(P1) — stage 행동 지침 블록. 실제 분기 상수를 노출한다.
        from saju_engines import counseling_arbiter as _counsel

        flags["counseling_semantics_enabled"] = bool(
            _counsel.COUNSELING_SEMANTICS_ENABLED
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        # 총운 V2(P0~P3) — 어느 논리 버전으로 답변이 나가는지 운영에서 확인 가능해야 한다.
        from saju_engines import period_v2_config as _p2

        flags.update({k: v for k, v in _p2.active_versions().items() if isinstance(v, bool)})
    except Exception:  # noqa: BLE001
        pass
    return flags


@router.get("/health")
async def health() -> dict[str, object]:
    # async so FastAPI runs it on the event loop instead of dispatching the sync
    # handler to a threadpool (which can hang under restricted sandboxes).
    # 위험 노출 readiness는 서비스 전체와 분리(감수 62차 P1) — 위험 시스템
    # DEGRADED가 일반 풀이 트래픽을 빼지 않도록 status는 항상 서비스 기준.
    out: dict[str, object] = {"status": "ok", "engine_version": ENGINE_VERSION,
                              "service_readiness": "READY"}
    try:
        from ..services.risk_exposure_monitor import risk_readiness_snapshot

        # JSON 원형을 보존한다(2026-08-04): 이전 구현은 전 값을 str()로
        # 바꾸고 None을 **버렸다**. 그 결과 ①만료 시각을 읽을 수 없을 때
        # 필드가 사라져 "읽지 못함"과 "필드 없음"이 구분되지 않고 ②지표
        # dict가 파이썬 repr 문자열로 나갔다. 기존 필드는 전부 문자열이라
        # 이 변경으로 표현이 달라지지 않는다.
        for key, value in risk_readiness_snapshot().items():
            out[key] = (value
                        if value is None or isinstance(
                            value, str | int | float | bool | dict | list)
                        else str(value))
    except Exception:  # noqa: BLE001 — 관측 실패가 health를 막지 않는다
        pass
    # beta flag는 gitignore된 .env.beta에만 있어 켜졌는지 확인할 수단이 없었다.
    out["beta_flags"] = _beta_flag_snapshot()
    # 이벤트 엔진 실효 모드 — 선정 모드가 채널 간 갈리면 같은 질문에서 대표 시점이
    # 달라진다. env 가 아니라 실제로 쓰이는 값을 보여준다.
    try:
        from saju_engines.event_engine_config import event_engine_flag_snapshot

        out["event_engine_flags"] = event_engine_flag_snapshot()
    except Exception:  # noqa: BLE001 — 관측 실패가 health를 막지 않는다
        pass
    return out
