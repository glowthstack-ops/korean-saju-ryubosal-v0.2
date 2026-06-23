"""Life Event Inference 개인화 입력 조회 (chat·report 공용).

저장된 subject의 개인 시그니처 + 활성 코호트를 LifeEventStore에서 조회한다. 방어적 —
owner/subject 미확정이거나 DB 미설정·조회 실패면 (None, None)으로 폴백(개인화 실패가 풀이를
막지 않도록 — 규칙11). 활성 코호트는 게이트(§4.4)를 통과한 CohortStats만 반환한다.
"""

from __future__ import annotations

from saju_engines.cohort_calibration import CohortStats, cohort_stats_from_counts
from saju_engines.event_scoring import confirmed_favorability_override, normalize_element
from saju_engines.life_event_store import LifeEventStore
from saju_engines.profile_store import ProfileStore
from saju_engines.reality_calibration import pillars_signature
from saju_shared_types.life_event import LifeEventRow
from saju_shared_types.manse_result import ManseV2Result

_life_event_store: LifeEventStore | None = None
_profile_store: ProfileStore | None = None


def _get_profile_store() -> ProfileStore | None:
    global _profile_store
    if _profile_store is None:
        try:
            _profile_store = ProfileStore()
        except ValueError:
            return None
    return _profile_store


def fetch_confirmed_yongsin_override(
    owner_id: str | None, subject_id: str | None,
) -> tuple[dict[str, str] | None, str | None]:
    """저장된 확정 용신이 있으면 (fav_override{오행:역할}, 정규화 용신) 반환, 없으면 (None, None).

    엔진 최초 도출값(yongsin_analysis.final = 확정 전 후보 상태)은 호출부가 비파괴 보존한다.
    여기서는 확정 용신을 용희기구한 5역할로 재도출한 override만 만든다(미설정·무DB·미상=무override).
    """
    if not subject_id:
        return None, None
    store = _get_profile_store()
    if store is None:
        return None, None
    try:
        element = normalize_element(store.get_yongsin(subject_id))
    except Exception:  # noqa: BLE001 — 확정 조회 실패가 풀이를 막지 않도록(규칙11)
        return None, None
    if element is None:
        return None, None
    try:
        return confirmed_favorability_override(element), element
    except (ValueError, KeyError, StopIteration):
        return None, None


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
