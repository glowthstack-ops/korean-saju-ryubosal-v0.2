"""사건 서술(고민 상담)형 질문의 too_broad 바운스 방지 (B3 예외, 2026-08-11).

관측된 미스: **"집안 자랑하다가 그게 발목을 잡아서 연기인생을 망치게 될 것 같아.
앞으로 어떻게 될까?"** 가 세 번 연속 범위 좁히기 메뉴("질문 범위가 넓어요 …")로
빠졌다. 표현을 바꿔도(했었는데/그간) 같은 곳으로 떨어진다 — 시점·분야 어휘가 없는 한
B3 판정표의 '시점✗ 분야✗'에 계속 걸리기 때문이다. 상황을 구체적으로 서술했는데
되물으면 서술이 통째로 무시된다.

수정 축 3개를 각각 검증한다.

    P1a  CAREER 도메인 연예·예술 직군 어휘("연기인생"·"배우로" 등)
    P1b  SOCIAL_CONFLICT 이벤트 구설·평판 어휘("논란"·"스캔들" 등 — 기존 rescue
         경로: 이벤트 감지 → EVENT_DOMAIN 승격 → 분야 기본 기간)
    P2   사건 서술형 가드 — 과거 서술절+우려+막연 미래 3신호면 too_broad 대신 실행

넓히면서 삼키지 말아야 할 것: 무맥락 광질문("앞으로 내 운세 알려줘")은 기존대로
좁히고, 延期('연기됐어')·학습('배우다')·시간어('다가오는') 동형어는 오검출하지 않는다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.query_parser import parse_message
from saju_engines.rewriter import _is_incident_concern, assess
from saju_shared_types.event_taxonomy_v2 import EventKeyV2
from saju_shared_types.intent import Domain

_TODAY = date(2026, 8, 11)


def _intent(question: str):  # noqa: ANN202 - 파서 반환 타입은 내부 모델이다
    return parse_message(question, _TODAY).intents[0]


# ── 관측된 원 사례 — 어떤 표현으로도 바운스되지 않는다 ────────────────────────


@pytest.mark.parametrize("question", [
    "집안 자랑하다가 그게 발목을 잡아서 연기인생을 망치게 될 것 같아. 앞으로 어떻게 될까?",
    "집안 자랑을 했는데 그게 발목을 잡아서 연기인생을 망치게 될 것 같아. 앞으로 어떻게 될까?",
    "그간 집안 자랑을 했었는데 그게 발목을 잡아서 연기인생을 망치게 될 것 같아. "
    "앞으로 어떻게 될까?",
])
def test_observed_phrasings_are_answered(question: str) -> None:
    """실사용 3연속 바운스 사례 — 이제 실행 경로로 통과한다."""
    intent = _intent(question)
    status = assess(intent, question).status
    assert status not in ("too_broad", "need_subject")
    # '연기인생'이 직업 신호로 잡혀 분야 기본 기간까지 붙는다(P1a).
    assert Domain.CAREER in (intent.domain, *intent.domains)


# ── P1a: 연예·예술 직군 어휘 ─────────────────────────────────────────────────


def test_actor_vocabulary_maps_to_career() -> None:
    q = "배우로 활동 중인데 앞으로 어떻게 될까?"
    intent = _intent(q)
    assert Domain.CAREER in (intent.domain, *intent.domains)
    assert assess(intent, q).status != "too_broad"


def test_postponed_yeongi_is_not_career() -> None:
    """延期 동형어 — '연기됐다'는 직업 도메인이 아니다('연기' 단독 미등재 확인)."""
    from saju_engines.query_parser import _detect_domains

    assert Domain.CAREER not in _detect_domains("행사가 연기됐는데 어떻게 하지?")


def test_learning_baeu_is_not_career() -> None:
    """배우다(학습) 동형어 — '요리를 배우려고'는 직업 신호가 아니다."""
    from saju_engines.query_parser import _detect_domains

    assert Domain.CAREER not in _detect_domains("요리를 배우려고 하는데 괜찮을까?")


# ── P1b: 구설·평판 이벤트 어휘 → 기존 rescue 경로 ────────────────────────────


def test_reputation_vocabulary_rescues_via_event() -> None:
    q = "논란이 생겨서 이미지가 나빠졌는데 앞으로 어떻게 될까?"
    intent = _intent(q)
    assert intent.event_key is EventKeyV2.SOCIAL_CONFLICT
    assert Domain.CAREER in (intent.domain, *intent.domains)
    assert assess(intent, q).status != "too_broad"


# ── P2: 사건 서술형 가드 — 어휘 없이도 문형으로 통과 ─────────────────────────


def test_incident_concern_without_vocabulary_passes() -> None:
    """도메인·이벤트 어휘가 전혀 없어도 3신호 문형이면 실행한다."""
    q = "말실수를 했는데 큰일 날 것 같아. 앞으로 어떻게 될까?"
    assert _is_incident_concern(q)
    assert assess(_intent(q), q).status == "ok"


@pytest.mark.parametrize("question", [
    "앞으로 내 운세 알려줘",            # 무맥락 광질문 — 기존 B3 회귀 보존
    "앞으로 어떻게 될까?",              # 서술절 없음
    "다가오는 시기가 걱정되는데 앞으로 어떻게 될까?",  # '다가오는'은 서술절 아님
])
def test_contextless_broad_questions_still_narrow(question: str) -> None:
    """서술 없는 광질문은 기존대로 좁히기 메뉴를 유지한다."""
    assert not _is_incident_concern(question)
    assert assess(_intent(question), question).status == "too_broad"


def test_present_tense_narrative_is_not_past() -> None:
    """'활동 중인데'(현재)는 과거 서술절이 아니다 — ㅆ 받침 일반화의 경계."""
    from saju_engines.rewriter import _has_past_narrative

    assert not _has_past_narrative("배우로 활동 중인데 궁금해")
    assert _has_past_narrative("집안 자랑을 했었는데")
    assert _has_past_narrative("이미지가 나빠졌는데")
    assert _has_past_narrative("자랑하다가 그게")
    assert not _has_past_narrative("다가오는 3년")
