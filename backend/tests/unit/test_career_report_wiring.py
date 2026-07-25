"""커리어 전이 리포트 배선 회귀 — P4-2 (CAREER_TRANSITION_SYSTEM §12).

핵심은 **chat 과 report 가 같은 판단을 내는가**다. report 전용 해석기·점수·병목을
만들면 같은 명식에 대해 두 화면이 다른 말을 한다.
"""

from __future__ import annotations

import pytest

from saju_api.services import report_service
from saju_engines import career_chat_consumer


class _C:
    def __init__(self, key, period="2026", score=0, favorability=0.0):
        self.event_key, self.period = key, period
        self.score, self.favorability = score, favorability


class _Data:
    def __init__(self, candidates):
        self.candidates = candidates


def _signals():
    from saju_shared_types.event_engine import EventKeyV2 as K

    return [
        _C(K.CAREER_CHANGE, score=80), _C(K.JOB_GAIN, score=60),
        _C(K.CONTRACT_DOCUMENT, favorability=0.3), _C(K.PREPARATION_DELAY, score=50),
    ]


@pytest.fixture
def flags_on(monkeypatch):
    monkeypatch.setattr(career_chat_consumer, "CAREER_TRANSITION_CHAT_ENABLED", True)
    monkeypatch.setattr(career_chat_consumer, "CAREER_TRANSITION_CHAT_BETA_EXPOSE", True)


def test_flag_off_produces_no_block(monkeypatch) -> None:
    """flag OFF → 기존 리포트 byte 불변."""
    monkeypatch.setattr(career_chat_consumer, "CAREER_TRANSITION_CHAT_ENABLED", False)
    assert report_service._career_transition_report_block(_Data(_signals())) == []


def test_enabled_without_expose_produces_no_block(monkeypatch) -> None:
    monkeypatch.setattr(career_chat_consumer, "CAREER_TRANSITION_CHAT_ENABLED", True)
    monkeypatch.setattr(career_chat_consumer, "CAREER_TRANSITION_CHAT_BETA_EXPOSE", False)
    assert report_service._career_transition_report_block(_Data(_signals())) == []


def test_block_matches_chat_verdict(flags_on) -> None:
    """같은 신호에서 report 블록이 chat 과 **같은 병목·요인**을 담아야 한다."""
    from saju_api.services.chat_service import _career_effect_vector_for
    from saju_shared_types.career_transition import (
        CareerEpisodeStore,
        CareerQueryResolution,
        CareerTransitionKind,
    )

    cands = _signals()
    chat_prep = career_chat_consumer.prepare_career_chat_block(
        CareerEpisodeStore(),
        query_resolution=CareerQueryResolution.GENERAL_CAREER, subject_count=1,
        kind=CareerTransitionKind.EXTERNAL_MOVE,
        vector=_career_effect_vector_for(cands),
    )
    block = report_service._career_transition_report_block(_Data(cands))
    assert block and chat_prep.directive
    joined = "\n".join(block)
    for line in chat_prep.directive.splitlines():
        assert line in joined, "report 가 chat 과 다른 서술을 만든다"


def test_no_signal_keeps_existing_report(flags_on) -> None:
    """근거가 없으면 아무것도 붙이지 않는다(기존 직업 테마 서술 유지)."""
    assert report_service._career_transition_report_block(_Data([])) == []


def test_block_never_implies_confirmed_progress(flags_on) -> None:
    """리포트는 확인된 지원·면접 사실을 갖지 않는다 — 진행 중처럼 쓰지 않는다.

    가드 지시문은 금지 대상을 이름으로 열거하므로 서술부만 검사한다.
    """
    block = report_service._career_transition_report_block(_Data(_signals()))
    narrative = "\n".join(
        line for line in block
        if line != report_service._CAREER_TRANSITION_REPORT_DIRECTIVE
    )
    assert "확인된 지원·면접 사실이 없" in narrative
    for banned in ("지원한 곳", "진행 중인 전형", "받으신 오퍼"):
        assert banned not in narrative


def test_block_carries_the_same_prohibitions_as_chat(flags_on) -> None:
    """단정·상대 의향 추정 금지가 리포트에도 그대로 실린다."""
    joined = "\n".join(report_service._career_transition_report_block(_Data(_signals())))
    assert "확정 단정" in joined
    assert "의향 추정" in joined


def test_sections_are_transition_only() -> None:
    """구조·태도·점수표 섹션에는 붙이지 않는다(전이 서술 대상이 아니다)."""
    targets = report_service._CAREER_TRANSITION_SECTIONS
    assert {"J-04", "J-05", "J-07"} <= targets
    assert not ({"J-02", "J-03", "J-08"} & targets)
