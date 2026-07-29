"""OA-10a — 일별 선택 원장의 계약 상수·호환성·지문.

원장 3계층(generation / selection ledger / active pointer)이 무엇을 "같은 것"으로
볼지 정하는 모듈이다. DB 는 행의 유효성을 막고, 여기서는 **어떤 이력을 읽어도 되는가**
와 **무엇이 바뀌면 다른 결과인가**를 정한다.

호환성은 **코드 상수**로만 바꾼다. DB 테이블로 두면 운영 중 데이터만 고쳐 과거 이력의
해석 계약을 바꿀 수 있게 되고, 그 순간 재현성이 깨진다. 호환 범위 확대는 코드 리뷰·
fixture 추가·과거 원장 replay 테스트·배포를 반드시 거친다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

# ── 정책 버전 ──────────────────────────────────────────────────────────────

#: 현행 라이브 동작에 붙인 이름. "현재 코드에서 C10 플래그만 끈 상태"로 정의하지
#: 않는다 — 이후 코드가 변하면 legacy 도 함께 변해 과거 재현이 무너진다.
#: 실제 거동은 `daily_legacy_display.py` 의 고정 adapter 가 소유한다.
DISPLAY_SELECTION_POLICY_LEGACY_V0 = "display-selection.legacy-v0"
#: C10 — coverage floor + 계층형 밴드 보호.
DISPLAY_SELECTION_POLICY_C10_V1 = "display-selection.p4-lc.c10.v1"

#: 이 결과를 장기 이력으로 해석할 수 있는 계약. 정책 버전과 **다른 축**이다 —
#: 정책이 바뀌어도 사용자가 이전 정책에서 본 이력은 계속 읽어야 한다.
HISTORY_CONTRACT_VERSION = "daily-selection-history.v1"

#: 호환 registry. 키는 target(현재), 값은 읽어도 되는 source 집합.
HISTORY_CONTRACT_COMPATIBILITY: dict[str, frozenset[str]] = {
    "daily-selection-history.v1": frozenset({"daily-selection-history.v1"}),
}

#: taxonomy 호환 registry. `semantic_family` 가 정책 입력이 된 이상 SSOT 다.
TAXONOMY_COMPATIBILITY: dict[str, frozenset[str]] = {
    "taxonomy.v1": frozenset({"taxonomy.v1"}),
}


class HistoryCompatibility(StrEnum):
    """과거 이력을 현재 정책 입력으로 쓸 수 있는가."""

    EXACT = "EXACT"
    EXPLICIT_COMPAT_MAPPING = "EXPLICIT_COMPAT_MAPPING"
    INCOMPATIBLE = "INCOMPATIBLE"
    #: registry 에 없는 값 — **호환으로 간주하지 않는다**(fail-closed).
    UNKNOWN = "UNKNOWN"


#: 이력으로 사용할 수 있는 판정.
USABLE_COMPATIBILITY = frozenset({
    HistoryCompatibility.EXACT, HistoryCompatibility.EXPLICIT_COMPAT_MAPPING,
})


def classify_history_compatibility(
    *,
    source_history_contract: str,
    source_taxonomy_version: str,
    target_history_contract: str,
    target_taxonomy_version: str,
) -> HistoryCompatibility:
    """과거 generation 의 이력을 현재 정책 입력으로 쓸 수 있는지 판정한다.

    두 축을 함께 본다 — 이력 해석 계약과 taxonomy. `semantic_family` 매핑이
    달라지면 같은 event_key 도 다른 의미 장면이 되므로 이력 계약만으로는 부족하다.

    Args:
        source_history_contract: 과거 generation 의 이력 계약.
        source_taxonomy_version: 과거 generation 의 taxonomy 버전.
        target_history_contract: 현재 정책의 이력 계약.
        target_taxonomy_version: 현재 taxonomy 버전.

    Returns:
        판정. registry 에 없으면 `UNKNOWN`(호환 아님).
    """
    allowed = HISTORY_CONTRACT_COMPATIBILITY.get(target_history_contract)
    tax_allowed = TAXONOMY_COMPATIBILITY.get(target_taxonomy_version)
    if allowed is None or tax_allowed is None:
        return HistoryCompatibility.UNKNOWN
    if source_history_contract not in allowed or source_taxonomy_version not in tax_allowed:
        return HistoryCompatibility.INCOMPATIBLE
    if (
        source_history_contract == target_history_contract
        and source_taxonomy_version == target_taxonomy_version
    ):
        return HistoryCompatibility.EXACT
    return HistoryCompatibility.EXPLICIT_COMPAT_MAPPING


# ── 결손·재현 상태 코드 ────────────────────────────────────────────────────

HISTORY_INCOMPLETE_REPLAY_REQUIRED = "HISTORY_INCOMPLETE_REPLAY_REQUIRED"
HISTORY_REPLAY_FAILED = "HISTORY_REPLAY_FAILED"
HISTORY_INCOMPLETE_FAIL_CLOSED_TO_LEGACY = "HISTORY_INCOMPLETE_FAIL_CLOSED_TO_LEGACY"
HISTORY_VERSION_MISMATCH = "HISTORY_VERSION_MISMATCH"
CONTRACT_REPLAY_INCOMPLETE = "CONTRACT_REPLAY_INCOMPLETE"
NONDETERMINISTIC_REPLAY_DETECTED = "NONDETERMINISTIC_REPLAY_DETECTED"
ACTIVATION_CONFLICT = "ACTIVATION_CONFLICT"

REPLAY_PLANNED = "REPLAY_PLANNED"
REPLAY_RUNNING = "REPLAY_RUNNING"
REPLAY_VALIDATED = "REPLAY_VALIDATED"
REPLAY_ACTIVATED = "REPLAY_ACTIVATED"
REPLAY_ABORTED = "REPLAY_ABORTED"


# ── 지문 ──────────────────────────────────────────────────────────────────


def _sha(parts: Sequence[str]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


@dataclass(frozen=True)
class HistoryDay:
    """이력 한 날의 정체성 — active pointer 가 바뀌면 이 값이 바뀐다."""

    fortune_date: date
    active_generation_id: str
    board_result_fingerprint: str
    history_contract_version: str
    taxonomy_version: str


def history_set_fingerprint(days: Sequence[HistoryDay]) -> str:
    """읽은 이력 집합의 지문.

    단순 날짜 범위 해시가 아니다 — **날짜순 활성 결과의 정체성**을 포함한다.
    어느 하루의 active pointer 가 바뀌면 이 값도 반드시 달라져야 백필이 새 결과를
    만들었다는 사실이 드러난다.

    Args:
        days: 이력 날짜들(정렬 여부 무관 — 내부에서 날짜순 정렬한다).

    Returns:
        sha256 hex.
    """
    parts: list[str] = []
    for d in sorted(days, key=lambda x: x.fortune_date):
        parts += [
            d.fortune_date.isoformat(), d.active_generation_id,
            d.board_result_fingerprint, d.history_contract_version, d.taxonomy_version,
        ]
    return _sha(parts)


def engine_input_fingerprint(
    *,
    fortune_date: date,
    active_dict_version: str,
    content_version: str,
    event_selection_contract: str,
    display_selection_policy_version: str,
    taxonomy_version: str,
    board_rebalance_version: str,
    feature_flags: dict[str, str] | None = None,
) -> str:
    """엔진 입력의 지문 — 이 값이 같으면 같은 결과가 나와야 한다.

    `content_version` 과 사전 버전이 **반드시** 포함된다(회귀로 고정).

    Args:
        fortune_date: 대상 날짜.
        active_dict_version: 그 날짜에 적용되는 사전 버전.
        content_version: 그 날짜의 콘텐츠 버전.
        event_selection_contract: 동결된 원시 사건 선택 계약.
        display_selection_policy_version: 표시 정책 버전.
        taxonomy_version: taxonomy 버전.
        board_rebalance_version: 보드 재배정 계약.
        feature_flags: 결과에 영향을 주는 플래그(키 정렬해 포함).

    Returns:
        sha256 hex.
    """
    parts = [
        fortune_date.isoformat(), active_dict_version, content_version,
        event_selection_contract, display_selection_policy_version,
        taxonomy_version, board_rebalance_version,
    ]
    for key in sorted(feature_flags or {}):
        parts += [key, (feature_flags or {})[key]]
    return _sha(parts)


def row_result_fingerprint(
    *, ilju: str, display_good_representative: str, support_event: str,
    caution_event: str, final_headline: str, good_selection_reason: str,
    display_displacement_loss: int,
) -> str:
    """원장 1행의 결과 지문 — 재생 결정론 비교의 최소 단위."""
    return _sha([
        ilju, display_good_representative, support_event, caution_event,
        final_headline, good_selection_reason, str(display_displacement_loss),
    ])


def board_result_fingerprint(row_fingerprints: Sequence[str]) -> str:
    """보드 60행의 결과 지문. 행 순서에 흔들리지 않도록 정렬해 해싱한다."""
    return _sha(sorted(row_fingerprints))


def board_cache_key(
    *, fortune_date: date, content_version: str,
    display_selection_policy_version: str, board_result_fingerprint_: str,
) -> str:
    """캐시 키 — 어느 원장 결과인지 지문으로 확정한다.

    증가 번호(`history_snapshot_version`)는 쓰지 않는다. 원장 내용과의 실제 연결을
    증명하지 못하기 때문이다.
    """
    return (
        f"daily:board:{fortune_date.isoformat()}:{content_version}"
        f":{display_selection_policy_version}:{board_result_fingerprint_}"
    )


def board_lock_key(*, fortune_date: date, display_selection_policy_version: str) -> str:
    """Redis 락 키 — 중복 계산 방지용(정합성은 DB advisory lock + CAS 가 맡는다)."""
    return f"daily:lock:{fortune_date.isoformat()}:{display_selection_policy_version}"


def advisory_lock_key(
    *, fortune_date: date, display_selection_policy_version: str
) -> int:
    """PG advisory lock 키(bigint). `pg_advisory_xact_lock` 은 tx 종료 시 자동 해제."""
    digest = hashlib.sha256(
        f"{fortune_date.isoformat()}|{display_selection_policy_version}".encode()
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=True)
