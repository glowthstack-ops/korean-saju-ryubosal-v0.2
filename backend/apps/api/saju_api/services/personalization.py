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


# ── CAL-P1-c — 저장된 캘리브레이션 blob → LLM 표현 조정 힌트(판정 비개입) ──────
# subject_yongsin.calibration(jsonb, FE가 {answers, result} 저장)에서 trait/pair 힌트만
# 추출해 LLM 입력에 싣는다. 최대 개수 cap으로 토큰을 묶는다(pair 1 + trait 소수).
_CALIB_HINT_CAP = 3


def calibration_hint_lines(blob: dict | None) -> list[str]:
    """캘리브레이션 blob에서 표현 조정 힌트 라인을 추출한다(순수 함수 — DB 무관).

    trait_llm_hints(문자열)와 pair_expression_hints(instruction)를 합쳐 cap까지만.
    어떤 라인도 판정·점수를 바꾸라는 지시가 아니다(scorer가 불변 조항을 내장).
    """
    if not blob:
        return []
    result = blob.get("result") or {}
    if not isinstance(result, dict):
        return []
    lines: list[str] = []
    for hint in result.get("pair_expression_hints") or []:
        if not isinstance(hint, dict):
            continue
        instruction = hint.get("instruction")
        if not instruction:
            continue
        basis = hint.get("basis_label") or hint.get("axis_id") or ""
        year = hint.get("transit_year")
        anchor = f"·확인 해 {year}" if year else ""
        lines.append(f"[캘리브레이션 표현 조정 — {basis}{anchor}] {instruction}")
    for hint in result.get("trait_llm_hints") or []:
        if isinstance(hint, str) and hint:
            lines.append(hint)
    return lines[:_CALIB_HINT_CAP]


def fetch_calibration_expression_hints(subject_id: str | None) -> list[str]:
    """저장된 검증 응답의 표현 조정 힌트를 조회한다(미설정·무DB·실패=빈 목록, 규칙11)."""
    if not subject_id:
        return []
    store = _get_profile_store()
    if store is None:
        return []
    try:
        return calibration_hint_lines(store.get_yongsin_calibration(subject_id))
    except Exception:  # noqa: BLE001 — 조회 실패가 풀이를 막지 않도록
        return []
