"""사전계산(Precompute) 배선 — docs/09 T0~T2 (CLAUDE.md 원칙 9).

`PrecomputeStore`·`PrecomputeScheduler` 는 구현·테스트가 끝나 있었으나 apps 어디서도
쓰이지 않아, report/chat 이 요청마다 `CompositeBuilder` 로 즉석 빌드하고 있었다. 본
모듈이 그 사이를 잇는다.

**cache-aside**: 저장소에 있으면 읽고, 없거나 오류면 **즉석 빌드로 폴백**한다. 사전계산은
응답 지연·비용 최적화이지 기능 요건이 아니므로, DB 가 없거나 죽어도 서비스는 그대로
동작해야 한다(커리어 shadow 원장과 정반대의 판단 — 그쪽은 상태 유실이 대화 모순을
만들지만, 여기서는 같은 값을 다시 계산할 뿐이다).

**동일성 보장**: 저장된 composite 는 즉석 빌드와 의미 필드가 같아야 한다. 다른 것은
identity 필드(`subject_id`·`dict_version`·`computed_at`)뿐이며, 이는 회귀
(`test_precompute_wiring`)가 강제한다.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, date, datetime
from pathlib import Path

from saju_engines.precompute import CompositeBuilder
from saju_engines.precompute_scheduler import PrecomputeScheduler
from saju_engines.precompute_store import PrecomputeStore, default_dsn
from saju_shared_types.precompute import CompositeLevel, LuckComposite
from saju_shared_types.subject import SubjectRecord

_logger = logging.getLogger(__name__)

_DICTS = Path(__file__).resolve().parents[4] / "dictionaries"

#: 사전계산 사전 버전 — 사전·계산 규칙이 바뀌면 올린다(구버전 레코드는 무효화 대상).
PRECOMPUTE_DICT_VERSION = "1.0.0"

#: `off` 로 두면 저장소를 쓰지 않고 항상 즉석 빌드한다(로컬·CI 기본 동작 보존).
_MODE_ENV = "SAJU_PRECOMPUTE_MODE"

_store: PrecomputeStore | None = None
_store_failed = False


def is_enabled() -> bool:
    """사전계산 저장소 사용 여부 — DSN 이 있고 모드가 off 가 아닐 때만."""
    if os.getenv(_MODE_ENV, "on").strip().lower() == "off":
        return False
    return bool(default_dsn())


def store() -> PrecomputeStore | None:
    """저장소 단일 인스턴스 — 초기화 실패는 1회만 로깅하고 None 으로 고정한다."""
    global _store, _store_failed
    if _store is not None or _store_failed or not is_enabled():
        return _store
    try:
        instance = PrecomputeStore()
        instance.migrate()
    except Exception:  # noqa: BLE001 — 사전계산 부재가 서비스를 막지 않는다
        _logger.warning("precompute_store_unavailable — 즉석 빌드로 동작", exc_info=True)
        _store_failed = True
        return None
    _store = instance
    return _store


def _scheduler(target: PrecomputeStore) -> PrecomputeScheduler:
    """스케줄러 조립 — 만세 계산은 API 의 캐시된 calculate 를 주입한다."""
    from .manse_service import calculate

    return PrecomputeScheduler(
        target, CompositeBuilder(_DICTS), calculate, PRECOMPUTE_DICT_VERSION
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def on_subject_upsert(subject: SubjectRecord, today: date | None = None) -> int:
    """T0 — 대상 등록/출생정보 수정 시 기존 레코드 무효화 후 재계산.

    출생정보가 바뀌었는데 옛 사전계산이 남으면 **다른 사람의 운을 보여주는** 것과 같으므로,
    무효화만은 실패를 삼키지 않고 로깅한다(다음 읽기는 어차피 폴백으로 정확한 값을 낸다).

    Args:
        subject: 갱신된 대상.
        today: 기준일(미지정 시 오늘).

    Returns:
        저장된 레코드 수(저장소 미사용·실패면 0).
    """
    target = store()
    if target is None:
        return 0
    try:
        return _scheduler(target).on_subject_upsert(
            subject, today or date.today(), _now_iso()
        )
    except Exception:  # noqa: BLE001
        _logger.warning("precompute_upsert_failed subject=%s", subject.subject_id,
                        exc_info=True)
        return 0


def ensure_current(subject: SubjectRecord, today: date | None = None) -> int:
    """T1/T2 — 기준일의 현재 period_key 레코드가 비었으면 보충한다(멱등)."""
    target = store()
    if target is None:
        return 0
    try:
        return _scheduler(target).ensure_current(
            subject, today or date.today(), _now_iso()
        )
    except Exception:  # noqa: BLE001
        _logger.warning("precompute_ensure_failed subject=%s", subject.subject_id,
                        exc_info=True)
        return 0


def read_composites(
    subject_id: str | None, levels: set[CompositeLevel] | None = None
) -> list[LuckComposite] | None:
    """저장된 composite 를 읽는다 — 미사용·미적중·오류면 None(호출자가 즉석 빌드).

    빈 목록도 None 으로 돌려준다. "레코드 0건"과 "캐시 미적중"을 구분하지 않으면
    사전계산이 비어 있는 대상에게 **신호 없음**을 사실처럼 보여주게 된다.
    """
    target = store()
    if target is None or not subject_id:
        return None
    try:
        rows = target.list_for(subject_id, PRECOMPUTE_DICT_VERSION)
    except Exception:  # noqa: BLE001
        _logger.warning("precompute_read_failed subject=%s", subject_id, exc_info=True)
        return None
    if levels is not None:
        rows = [c for c in rows if c.level in levels]
    return rows or None


def backfill(subject_id: str | None, today: date | None = None) -> int:
    """T1/T2 — 미적중 대상의 경계 레코드를 보충한다(다음 요청부터 적중).

    입춘·절입·교운·자정을 지나면 현재 period_key 가 바뀌므로, 누락 보충이 곧 경계
    갱신이다(`ensure_current` 는 멱등이라 이미 차 있으면 재계산하지 않는다). 이번
    요청의 응답은 호출자가 이미 즉석 빌드로 만들었으므로, 여기서 실패해도 사용자에게
    보이는 것은 없다.

    Args:
        subject_id: 대상 식별자(익명 경로에서는 None 일 수 있다).
        today: 기준일(미지정 시 오늘).

    Returns:
        보충된 레코드 수(불가·실패면 0).
    """
    if not subject_id or store() is None:
        return 0
    try:
        from saju_engines.subject_store import SubjectStore

        record = SubjectStore().get(subject_id)
    except Exception:  # noqa: BLE001 — 대상 조회 실패는 보충 생략일 뿐이다
        _logger.warning("precompute_backfill_subject_lookup_failed subject=%s",
                        subject_id, exc_info=True)
        return 0
    if record is None:
        return 0
    return ensure_current(record, today)


__all__ = [
    "PRECOMPUTE_DICT_VERSION",
    "backfill",
    "ensure_current",
    "is_enabled",
    "on_subject_upsert",
    "read_composites",
    "store",
]
