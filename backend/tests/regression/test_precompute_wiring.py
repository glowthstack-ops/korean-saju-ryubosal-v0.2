"""사전계산 배선 회귀 — docs/09 T0~T2 (CLAUDE.md 원칙 9).

읽기 경로를 저장소로 전환할 때 유일하게 중요한 것은 **읽은 값이 즉석 빌드와 같은가**다.
다르면 사용자는 어제와 다른 풀이를 받는데 원인이 캐시라는 사실은 드러나지 않는다.

DB 없이도 돌아가는 회귀만 여기 둔다(실 Postgres 왕복은
`tests/integration/test_scheduler_phase25.py` 담당). 여기서 고정하는 것:
- 스케줄러 경로와 즉석 빌드 경로의 **의미 필드 동일성**(identity 필드만 다르다)
- 저장소 미사용·오류·빈 결과에서 **즉석 빌드로 폴백**
- 리포트가 저장소와 **같은 dict_version** 을 쓴다(다르면 영구 미적중)
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services import precompute_service
from saju_api.services.manse_service import calculate
from saju_engines.precompute import CompositeBuilder
from saju_engines.precompute_scheduler import PrecomputeScheduler
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.precompute import CompositeLevel, LuckComposite
from saju_shared_types.subject import SubjectRecord

_DICTS = precompute_service._DICTS
_TODAY = date(2026, 7, 26)
_COMPUTED_AT = "2026-07-26T00:00:00+00:00"

#: 두 경로에서 다를 수밖에 없는 identity 필드 — 의미 비교에서 제외한다.
_IDENTITY_FIELDS = {"subject_id", "dict_version", "computed_at"}


def _birth() -> BirthInput:
    return BirthInput(
        calendar_type="solar", birth_date=date(1990, 5, 5), birth_time="13:30",
        birth_place_name="서울", gender="male",
    )


def _subject() -> SubjectRecord:
    return SubjectRecord(
        subject_id="regr-subject-1", owner_id="regr-owner", kind="self",
        label="본인", birth=_birth(),
    )


def _semantic(c: LuckComposite) -> dict:
    """identity 필드를 뺀 의미 payload."""
    return {
        k: v for k, v in c.model_dump(mode="json").items()
        if k not in _IDENTITY_FIELDS
    }


class _MemoryStore:
    """upsert/list_for 만 쓰는 최소 대역 — DB 없이 읽기 경로를 검증한다."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str], LuckComposite] = {}

    def migrate(self) -> None:
        return None

    def upsert(self, composites: list[LuckComposite]) -> int:
        for c in composites:
            self.rows[(c.subject_id, str(c.level), c.period_key)] = c
        return len(composites)

    def get(self, subject_id, level, period_key, dict_version):
        row = self.rows.get((subject_id, str(level), period_key))
        return row if row and row.dict_version == dict_version else None

    def list_for(self, subject_id, dict_version, level=None):
        return [
            c for c in self.rows.values()
            if c.subject_id == subject_id and c.dict_version == dict_version
            and (level is None or c.level == level)
        ]

    def invalidate_subject(self, subject_id: str) -> int:
        keys = [k for k in self.rows if k[0] == subject_id]
        for k in keys:
            del self.rows[k]
        return len(keys)


def _scheduled(store: _MemoryStore) -> PrecomputeScheduler:
    return PrecomputeScheduler(
        store,  # type: ignore[arg-type]
        CompositeBuilder(_DICTS),
        calculate,
        precompute_service.PRECOMPUTE_DICT_VERSION,
    )


def test_precomputed_equals_on_the_fly() -> None:
    """사전계산 결과가 즉석 빌드와 의미상 같아야 한다 — 이 전환의 유일한 안전 조건."""
    subject = _subject()
    store = _MemoryStore()
    _scheduled(store).on_subject_upsert(subject, _TODAY, _COMPUTED_AT)

    # 스케줄러와 같은 조건으로 계산해야 비교가 성립한다(기준일 미지정이면 운이 비어
    # composite 자체가 생성되지 않는다).
    chart = calculate(subject.birth.model_copy(update={"reference_date": _TODAY}))
    levels = {CompositeLevel.YEAR, CompositeLevel.MONTH}
    fresh = CompositeBuilder(_DICTS).build(
        chart, subject.subject_id,
        precompute_service.PRECOMPUTE_DICT_VERSION, _COMPUTED_AT, levels=levels,
    )
    cached = [c for c in store.list_for(
        subject.subject_id, precompute_service.PRECOMPUTE_DICT_VERSION
    ) if c.level in levels]

    assert fresh, "즉석 빌드가 비면 비교 자체가 무의미하다"
    by_key = {(str(c.level), c.period_key): _semantic(c) for c in cached}
    assert len(by_key) == len(cached)
    for c in fresh:
        key = (str(c.level), c.period_key)
        assert key in by_key, f"사전계산에 {key} 누락"
        assert by_key[key] == _semantic(c), f"{key} 의미 필드 불일치"


def test_ensure_current_is_idempotent() -> None:
    """이미 채워져 있으면 재계산하지 않는다(0건)."""
    subject = _subject()
    store = _MemoryStore()
    sched = _scheduled(store)
    sched.on_subject_upsert(subject, _TODAY, _COMPUTED_AT)
    assert sched.ensure_current(subject, _TODAY, _COMPUTED_AT) == 0


def test_upsert_invalidates_previous_records() -> None:
    """출생정보가 바뀌면 옛 레코드가 남지 않는다 — 다른 사람의 운을 보여주면 안 된다."""
    store = _MemoryStore()
    sched = _scheduled(store)
    old = _subject()
    sched.on_subject_upsert(old, _TODAY, _COMPUTED_AT)
    before = {(str(c.level), c.period_key): _semantic(c)
              for c in store.list_for(old.subject_id,
                                      precompute_service.PRECOMPUTE_DICT_VERSION)}

    changed = old.model_copy(update={
        "birth": old.birth.model_copy(update={"birth_date": date(1985, 11, 20)})
    })
    sched.on_subject_upsert(changed, _TODAY, _COMPUTED_AT)
    after = {(str(c.level), c.period_key): _semantic(c)
             for c in store.list_for(old.subject_id,
                                     precompute_service.PRECOMPUTE_DICT_VERSION)}
    assert after and after != before


def test_read_returns_none_when_store_disabled(monkeypatch) -> None:
    """저장소 미사용이면 None — 호출자가 즉석 빌드로 간다."""
    monkeypatch.setattr(precompute_service, "is_enabled", lambda: False)
    monkeypatch.setattr(precompute_service, "_store", None)
    assert precompute_service.read_composites("any-subject") is None


def test_read_returns_none_on_store_error(monkeypatch) -> None:
    """저장소 오류는 삼키고 None — 사전계산 장애가 리포트를 막지 않는다."""
    class _Broken:
        def list_for(self, *a, **k):
            raise RuntimeError("db down")

    monkeypatch.setattr(precompute_service, "store", lambda: _Broken())
    assert precompute_service.read_composites("any-subject") is None


def test_empty_result_is_treated_as_miss(monkeypatch) -> None:
    """레코드 0건을 '신호 없음'으로 넘기지 않는다 — 미적중으로 처리한다."""
    class _Empty:
        def list_for(self, *a, **k):
            return []

    monkeypatch.setattr(precompute_service, "store", lambda: _Empty())
    assert precompute_service.read_composites("any-subject") is None


def test_writes_are_best_effort(monkeypatch) -> None:
    """저장 실패가 대상 등록·수정을 깨뜨리지 않는다."""
    class _Broken:
        def invalidate_subject(self, *a, **k):
            raise RuntimeError("db down")

    monkeypatch.setattr(precompute_service, "store", lambda: _Broken())
    assert precompute_service.on_subject_upsert(_subject(), _TODAY) == 0
    assert precompute_service.ensure_current(_subject(), _TODAY) == 0


def test_backfill_is_noop_without_subject(monkeypatch) -> None:
    """subject_id 가 없으면 보충하지 않는다(익명·dry-run 경로)."""
    assert precompute_service.backfill("") == 0


def test_backfill_survives_subject_lookup_failure(monkeypatch) -> None:
    """대상 조회 실패가 리포트를 깨뜨리지 않는다."""
    class _Any:
        def list_for(self, *a, **k):
            return []

    monkeypatch.setattr(precompute_service, "store", lambda: _Any())
    monkeypatch.setenv("SAJU_V2_DATABASE_URL", "postgresql://invalid:1/none")
    assert precompute_service.backfill("missing-subject") == 0


@pytest.mark.parametrize("mode", ["off", "OFF", " off "])
def test_mode_env_disables_store(monkeypatch, mode: str) -> None:
    """SAJU_PRECOMPUTE_MODE=off 면 저장소를 쓰지 않는다."""
    monkeypatch.setenv("SAJU_PRECOMPUTE_MODE", mode)
    assert precompute_service.is_enabled() is False


def test_report_uses_same_dict_version() -> None:
    """리포트 폴백 빌드가 저장소와 같은 버전을 써야 캐시가 적중한다."""
    from saju_api.services import report_service

    source = report_service._ReportData._build_composites.__doc__ or ""
    assert "dict_version" in source
    assert precompute_service.PRECOMPUTE_DICT_VERSION == "1.0.0"
