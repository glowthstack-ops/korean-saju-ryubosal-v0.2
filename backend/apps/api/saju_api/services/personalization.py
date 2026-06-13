"""Life Event Inference 개인화 입력 조회 (chat·report 공용).

저장된 subject의 개인 시그니처 + 활성 코호트를 LifeEventStore에서 조회한다. 방어적 —
owner/subject 미확정이거나 DB 미설정·조회 실패면 (None, None)으로 폴백(개인화 실패가 풀이를
막지 않도록 — 규칙11). 활성 코호트는 게이트(§4.4)를 통과한 CohortStats만 반환한다.
"""

from __future__ import annotations

from saju_engines.cohort_calibration import CohortStats, cohort_stats_from_counts
from saju_engines.life_event_store import LifeEventStore
from saju_engines.reality_calibration import pillars_signature
from saju_shared_types.life_event import LifeEventRow
from saju_shared_types.manse_result import ManseV2Result

_life_event_store: LifeEventStore | None = None


def _get_store() -> LifeEventStore | None:
    global _life_event_store
    if _life_event_store is None:
        try:
            _life_event_store = LifeEventStore()
        except ValueError:
            return None
    return _life_event_store


def fetch_personal_inputs(
    owner_id: str | None, subject_id: str | None, result: ManseV2Result,
) -> tuple[list[LifeEventRow] | None, CohortStats | None]:
    """소유자·subject 확정 시 개인 시그니처 + 활성 코호트를 조회한다(실패·미설정=무개인화)."""
    if not (owner_id and subject_id):
        return None, None
    store = _get_store()
    if store is None:
        return None, None
    try:
        sig = store.subject_signature(owner_id, subject_id)
        py, pm, pd, ph, gender = pillars_signature(result)
        coarse = store.cohort_event_counts(pillar_day=pd, gender=gender)
        fine = store.cohort_event_counts(
            pillar_day=pd, gender=gender, fine_pillars=(py, pm, pd, ph),
        )
        return sig, cohort_stats_from_counts(coarse, fine)
    except Exception:  # noqa: BLE001 — 개인화 조회 실패가 풀이를 막지 않도록
        return None, None
