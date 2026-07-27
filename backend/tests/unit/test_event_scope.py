"""EventScope 산출 (P2-1) — 2026-07-27 데굴님 확정.

설계: `doc/v2_2/REVIEW_CONTRIBUTION_PROVENANCE.md` §17~18

이 단계는 **점수·등급·순위·Top-N을 바꾸지 않는다.** "어디까지 말할 수 있는가"만 정한다.
입력은 오직 `candidate_source_layers`(selected base occurrence의 층위)다 —
stack 구성이나 evaluated union을 넣으면 상위 지지 판정이 무너진다(PROV-4 §17-5).
"""

from __future__ import annotations

import pytest

from saju_engines.layer_evidence_scope import derive_event_scope
from saju_shared_types.event_engine import EventScope


@pytest.mark.parametrize(
    ("layers", "expected"),
    [
        (["daewoon"], EventScope.MAJOR_EVENT_ELIGIBLE),
        (["sewoon"], EventScope.MAJOR_EVENT_ELIGIBLE),
        (["sewoon", "ilwoon"], EventScope.MAJOR_EVENT_ELIGIBLE),
        (["wolwoon"], EventScope.LOCAL_TRIGGER_ONLY),
        (["ilwoon"], EventScope.LOCAL_TRIGGER_ONLY),
        (["wolwoon", "ilwoon"], EventScope.LOCAL_TRIGGER_ONLY),
        ([], EventScope.UNKNOWN),
    ],
)
def test_scope_from_selected_base_layers(layers, expected) -> None:
    """상위 층위가 하나라도 승자 근거에 있으면 주요 사건 후보 자격이 있다."""
    assert derive_event_scope(layers) is expected


def test_active_process_opens_minor_only() -> None:
    """월·일운만이어도 진행 중인 현실 과정이 있으면 시점 후보로 허용한다."""
    assert derive_event_scope(["ilwoon"], active_process=True) is (
        EventScope.ACTIVE_PROCESS_TRIGGER
    )


def test_active_process_does_not_upgrade_upper_or_unknown() -> None:
    """진행 사실은 minor-only에만 작용한다 — 상위 근거·판정불가를 덮어쓰지 않는다."""
    assert derive_event_scope(["sewoon"], active_process=True) is (
        EventScope.MAJOR_EVENT_ELIGIBLE
    )
    assert derive_event_scope([], active_process=True) is EventScope.UNKNOWN


def test_support_is_not_favorability() -> None:
    """`support`는 길흉이 아니라 '상위 층위에도 생성 근거가 있는가'다.

    부정 사건이든 긍정 사건이든 층위 구성이 같으면 같은 scope를 받는다 — scope 산출에
    quality·favorability가 들어가지 않음을 시그니처로 고정한다(PROV-4 §17-1).
    """
    assert derive_event_scope(["sewoon"]) is derive_event_scope(["daewoon"])
