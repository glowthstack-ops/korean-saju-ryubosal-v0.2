"""IntentEventFilter (Phase 7c) — 질문 의도·풀이 컨텍스트로 이벤트 후보를 제한한다.

intent_event_filter.json(우리 Domain enum + 일운/세운/리포트 컨텍스트)으로 출력 후보를
도메인에 맞게 추린다. 점수·판정은 바꾸지 않고 '무엇을 노출/억제할지'만 거른다(오케스트레이터
컨텍스트 축소 보조). deprioritize 키는 제거하고, include가 있으면 그 안에서 우선한다.
미입력(general·컨텍스트 없음)이면 전부 통과(차단 금지 — 빈 결과 방지).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class _HasEventKey(Protocol):
    @property
    def event_key(self) -> object: ...


class IntentEventFilter:
    """도메인·컨텍스트 기반 후보 필터."""

    def __init__(self, dictionaries_dir: Path) -> None:
        raw = json.loads(
            (dictionaries_dir / "event_engine" / "intent_event_filter.json").read_text(
                encoding="utf-8"
            )
        )
        self._include: dict[str, set[str]] = {}
        self._deprioritize: dict[str, set[str]] = {}
        for domain, spec in raw["intent_map"].items():
            self._include[domain] = set(spec.get("include", []))
            self._deprioritize[domain] = set(spec.get("exclude_or_deprioritize", []))
        self._overlays: dict[str, set[str] | None] = {}
        for ctx, spec in raw.get("context_overlays", {}).items():
            inc = spec.get("include")
            self._overlays[ctx] = None if inc == "all" else set(inc or [])

    def filter[T: _HasEventKey](
        self, candidates: list[T], domain: str | None, context: str | None = None
    ) -> list[T]:
        """후보를 도메인 deprioritize 제거 + 컨텍스트 오버레이로 거른다(빈 결과면 원본 유지)."""
        out = list(candidates)
        depri = self._deprioritize.get(domain or "", set())
        if depri:
            kept = [c for c in out if str(c.event_key) not in depri]
            out = kept or out  # 전부 걸러지면 원본 유지(차단 금지)
        overlay = self._overlays.get(context or "")
        if overlay is not None:
            kept = [c for c in out if str(c.event_key) in overlay]
            out = kept or out
        return out

    def domain_includes(self, domain: str | None) -> set[str]:
        """도메인 우선 노출 이벤트 키 집합(없으면 빈 집합)."""
        return set(self._include.get(domain or "", set()))
