"""ErrorStore 단위 테스트 — fingerprint 정규화 + 적재·묶음·해결(격리 DB)."""

from __future__ import annotations

import os

import pytest

from saju_engines.error_store import ErrorStore, fingerprint


def test_fingerprint_ignores_numbers() -> None:
    """숫자(아이디·시각·토큰 등)가 달라도 같은 원인이면 같은 fingerprint로 묶인다."""
    a = fingerprint("llm", "HTTPError", "타임아웃 12345ms job=abc-001")
    b = fingerprint("llm", "HTTPError", "타임아웃 678ms job=abc-999")
    assert a == b


def test_fingerprint_distinguishes_source_and_kind() -> None:
    """출처·종류가 다르면 다른 묶음."""
    base = fingerprint("llm", "HTTPError", "타임아웃")
    assert fingerprint("http", "HTTPError", "타임아웃") != base
    assert fingerprint("llm", "ValueError", "타임아웃") != base


@pytest.mark.skipif(
    not os.getenv("SAJU_V2_DATABASE_URL"), reason="DB 미설정 — 통합 경로 생략"
)
def test_record_group_resolve_roundtrip() -> None:
    """적재 → 묶음 집계 → fingerprint 해결 처리 왕복(격리 테스트 DB)."""
    store = ErrorStore()
    store.migrate()
    # 같은 원인 2건 적재(끝 수치만 상이) → 정규화로 동일 fingerprint·한 묶음이 되어야 한다.
    store.record(source="llm", kind="HTTPError", message="왕복테스트 메시지 1")
    store.record(source="llm", kind="HTTPError", message="왕복테스트 메시지 2")
    fp = fingerprint("llm", "HTTPError", "왕복테스트 메시지 1")
    assert fp == fingerprint("llm", "HTTPError", "왕복테스트 메시지 2")
    groups = {g["fingerprint"]: g for g in store.group_summary(days=1)}
    assert fp in groups
    assert groups[fp]["count"] >= 2
    assert groups[fp]["unresolved"] >= 2
    # 해결 처리 후 미해결 목록에서 빠진다.
    resolved = store.resolve(fingerprint=fp)
    assert resolved >= 2
    remaining = store.list_recent(fingerprint=fp, unresolved_only=True)
    assert remaining == []
