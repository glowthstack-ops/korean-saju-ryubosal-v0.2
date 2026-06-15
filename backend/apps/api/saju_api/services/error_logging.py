"""시스템 에러 중앙 로깅 배선 (운영 콘솔 — 에러 모니터링).

미처리 예외(http 5xx)·LLM 호출 실패(llm)·리포트 잡 실패(report_job)를 ErrorStore에 적재한다.
모든 기록은 best-effort — 모니터링이 본 기능을 깨지 않도록 예외를 삼킨다. DSN 미설정 시 setup이
no-op이라 DB 없이도(테스트 등) 안전하다.

이미 기록한 예외(_logged)는 상위(전역 핸들러·잡 catch)에서 중복 적재하지 않도록 표시한다.
예: LLM 호출 실패가 llm sink에서 기록되면, 같은 예외가 HTTP 500으로 전파돼도 다시 쌓지 않는다.
"""

from __future__ import annotations

import logging
from weakref import WeakSet

from saju_engines.error_store import ErrorStore

from . import llm_client

_logger = logging.getLogger(__name__)
_store: ErrorStore | None = None
_logged: WeakSet[BaseException] = WeakSet()


def setup() -> bool:
    """010 마이그레이션 적용 후 llm_client 에러 sink를 주입한다. DSN 없으면 no-op(False)."""
    global _store
    try:
        store = ErrorStore()
    except ValueError:
        return False  # DSN 미설정 — 에러 로깅 비활성(앱은 정상 기동)
    store.migrate()
    _store = store
    llm_client.set_error_sink(_llm_sink)
    return True


def record_error(
    *, source: str, kind: str, message: str, severity: str = "error",
    detail: str | None = None, path: str | None = None,
    owner_id: str | None = None, ref_id: str | None = None,
    exc: BaseException | None = None,
) -> None:
    """에러 1건 적재(best-effort). exc를 주면 중복 적재 방지용으로 기록 표시한다."""
    if exc is not None:
        _logged.add(exc)
    if _store is None:
        return
    try:
        _store.record(
            source=source, kind=kind, message=message, severity=severity,
            detail=detail, path=path, owner_id=owner_id, ref_id=ref_id,
        )
    except Exception:  # noqa: BLE001 — 에러 로깅 실패가 응답/흐름을 막지 않도록
        _logger.warning("system_errors 적재 실패", exc_info=True)


def is_logged(exc: BaseException) -> bool:
    """해당 예외가 이미(하위 계층에서) 기록됐는지 여부 — 상위 중복 적재 방지."""
    return exc in _logged


def _llm_sink(
    exc: BaseException, *, kind: str, message: str, surface: str | None = None,
    provider: str | None = None, model: str | None = None,
    owner_id: str | None = None, ref_id: str | None = None,
) -> None:
    """llm_client가 메인·폴백 모두 실패했을 때 호출 — source='llm'로 적재."""
    where = f"{surface or 'llm'}:{provider or '?'}/{model or '?'}"
    record_error(
        source="llm", kind=kind, message=message, path=where,
        owner_id=owner_id, ref_id=ref_id, exc=exc,
    )
