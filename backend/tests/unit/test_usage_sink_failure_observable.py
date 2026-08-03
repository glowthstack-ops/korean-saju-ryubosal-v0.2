"""사용량 sink 쓰기 실패의 관측 가능성 (LLM-USAGE-OBSERVABILITY-01 / ③, 2026-08-03).

이전에는 `except Exception: pass` 라서 DB 장애 중 회계 기록이 통째로 유실돼도 아무 신호가
남지 않았다. 나중에 `llm_usage` 침묵을 "호출 없음" 으로 읽을 수 있었고, 일운 사건에서
실제로 그 오독이 가능한 상황이었다.

**전달 정책은 바꾸지 않는다.** 재시도하지 않고 사용자 요청을 실패시키지 않는다. 바뀌는
것은 하나뿐이다 — 실패가 조용히 사라지지 않는다.

통지는 error sink 를 타지 않는다. 드롭을 세는 수단이 함께 드롭되면 계측이 무의미하다.

**검증 대상은 `_emit_usage` 자체다.** 초판은 `generate_reading` 을 통과시켜 확인했는데,
그 진입점은 API 키 존재 여부에 의존해 공급자에 닿기도 전에 끝날 수 있다. 전체 스위트에서
앞선 테스트가 키 env 를 지우면 단독 통과·전체 실패가 된다(실측). 바뀐 단위를 env 의존
경로로 감싸 검증하지 않는다.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from saju_api.services import llm_client


@contextmanager
def _captured_records() -> Iterator[list[logging.LogRecord]]:
    """대상 로거에 **직접** 핸들러를 붙여 기록을 모은다.

    `caplog` 를 쓰지 않는다. caplog 는 root 로 전파된 기록만 보는데, 앞선 테스트가
    이 로거에 자체 핸들러를 붙이고 `propagate` 를 끄면 실제로 로그가 나갔는데도
    `caplog.records` 가 비어 단독 통과·전체 실패가 된다(실측 — stderr 에는 찍혔다).
    """
    records: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = llm_client._logger
    handler = _Collector(level=logging.ERROR)
    previous = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.ERROR)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)

_FIELDS = {
    "surface": "chat", "model": "gemini-3-flash-preview", "provider": "gemini",
    "is_fallback": False, "input_tokens": 10, "output_tokens": 5,
    "cached_tokens": 0, "owner_id": None, "product_code": "CHAT",
    "call_type": "chat_single", "ref_id": "probe-1",
}


def _boom(**_fields: object) -> None:
    raise RuntimeError("usage store 장애(모의)")


def test_sink_failure_is_logged(monkeypatch) -> None:
    """sink 가 던지면 실패 사실이 구조화 로그로 남는다."""
    monkeypatch.setattr(llm_client, "_usage_sink", _boom)
    with _captured_records() as captured:
        llm_client._emit_usage(**_FIELDS)

    records = [
        r for r in captured
        if "usage_accounting_sink_write_failed" in r.getMessage()
    ]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "exception_type=RuntimeError" in message
    assert "call_type=chat_single" in message
    assert "ref_id=probe-1" in message


def test_sink_failure_does_not_propagate(monkeypatch) -> None:
    """회계 실패가 호출부로 전파되지 않는다 — 사용자 요청을 실패시키지 않는다."""
    monkeypatch.setattr(llm_client, "_usage_sink", _boom)
    llm_client._emit_usage(**_FIELDS)  # 예외가 나오면 이 줄에서 실패한다


def test_sink_failure_is_not_retried(monkeypatch) -> None:
    """실패한 sink 를 다시 부르지 않는다 — 호출당 정확히 1회."""
    calls = {"n": 0}

    def _counting(**_fields: object) -> None:
        calls["n"] += 1
        raise RuntimeError("usage store 장애(모의)")

    monkeypatch.setattr(llm_client, "_usage_sink", _counting)
    llm_client._emit_usage(**_FIELDS)
    assert calls["n"] == 1


def test_sink_failure_does_not_use_the_error_sink(monkeypatch) -> None:
    """통지가 error sink 를 타지 않는다.

    error sink 도 앱 배선에 묶여 있어, 같은 장애로 함께 죽으면 드롭이 다시 조용해진다.
    """
    seen: list[object] = []
    monkeypatch.setattr(llm_client, "_error_sink", lambda exc, **kw: seen.append(exc))
    monkeypatch.setattr(llm_client, "_usage_sink", _boom)
    llm_client._emit_usage(**_FIELDS)
    assert seen == []


def test_absent_sink_stays_silent(monkeypatch) -> None:
    """sink 미주입은 실패가 아니다 — 앱 밖 프로세스에서 오류 로그를 쏟지 않는다."""
    monkeypatch.setattr(llm_client, "_usage_sink", None)
    with _captured_records() as captured:
        llm_client._emit_usage(**_FIELDS)
    assert not [
        r for r in captured
        if "usage_accounting_sink_write_failed" in r.getMessage()
    ]


def test_healthy_sink_receives_the_fields_unchanged(monkeypatch) -> None:
    """정상 경로는 그대로다 — 필드를 가공하지 않고 넘긴다."""
    seen: list[dict] = []
    monkeypatch.setattr(llm_client, "_usage_sink", lambda **kw: seen.append(kw))
    with _captured_records() as captured:
        llm_client._emit_usage(**_FIELDS)
    assert seen == [_FIELDS]
    assert not [
        r for r in captured
        if "usage_accounting_sink_write_failed" in r.getMessage()
    ]
