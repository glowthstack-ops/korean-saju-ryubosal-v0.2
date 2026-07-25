"""기존 이벤트 신호 → 커리어 단계 효과 기여 어댑터 (CAREER_TRANSITION_SYSTEM §4·§9).

P4-1 에서 효과 벡터가 항상 비어 병목이 늘 `NOT_EVALUABLE`("근거가 아직 부족")이었다.
블록은 노출되는데 사용자가 얻는 것이 단계 나열뿐이었다는 뜻이다. 본 모듈이 그 구멍을 메운다.

**새 점수 엔진을 만들지 않는다.** 이미 계산된 `EventCandidate`(event_key·score·
favorability·timing)를 `EffectContribution` 으로 **변환**만 한다. 기존 점수·랭킹·직렬화는
읽기만 하며 바꾸지 않는다.

불변식:
- 기존 점수 변경 0 — 이 모듈은 어떤 후보도 수정하지 않는다.
- `double_contribution` 금지(INV-11) — 한 축에 기여는 **정확히 1건**이며, 기존 점수에
  이미 반영된 신호를 벡터와 원래 점수에 **중복 가산하지 않는다**(별도 축을 만들 뿐
  legacy 점수를 다시 더하지 않는다).
- 한 신호가 여러 축에 들어갈 때는 **축별 evidence_id 와 근거**를 따로 남긴다
  (같은 `signal_ref` 를 공유하되 `evidence_id` 는 축마다 다르다 — 감사 계약 그대로).
- `DERIVED` 를 만들지 않는다(파생 요약값 재합산 금지).
- 필수 관문 축이 하나라도 없으면 병목은 계속 `NOT_EVALUABLE` 로 남는다 — 여기서 0 을
  채워 넣지 않는다.

**축 값은 합이 아니라 최댓값이다.** 축은 "여건 수준"이지 사건 개수가 아니므로, 여러 기간의
후보를 더하면 1.0 을 넘겨 병목 비교(최솟값)가 무의미해진다. 같은 축의 후보 중 가장 강한
신호 하나만 기여로 남기고 나머지는 버린다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from saju_shared_types.career_effect_vector import (
    ContributionRole,
    EffectAxis,
    EffectContribution,
)
from saju_shared_types.event_engine import EventKeyV2

#: 값 산출 방식 — 축이 무엇을 재는가에 따라 읽는 채널이 다르다.
#:  FORMATION : 사건 형성도(일어나는가) → 표시 점수 0~100 을 0~1 로.
#:  QUALITY   : 결과 유불리(유리한가)  → favorability −1~+1 을 0~1 로.
#:  FRICTION  : 마찰·지연(막는가)      → 형성도를 **음수**로(막는 힘이므로 support 아님).
_FORMATION = "formation"
_QUALITY = "quality"
_FRICTION = "friction"

#: (event_key, axis) → (값 산출 방식, 축별 근거). 한 event_key 가 여러 축에 들어갈 때
#: 축마다 다른 근거를 남긴다 — "왜 이 신호가 이 축인가"가 감사·서술 양쪽에 필요하다.
SIGNAL_AXIS_MAP: Mapping[tuple[EventKeyV2, EffectAxis], tuple[str, str]] = MappingProxyType(
    {
        (EventKeyV2.CAREER_CHANGE, EffectAxis.OPPORTUNITY_ACTIVATION): (
            _FORMATION, "이직·전환 기회가 움직이는 정도",
        ),
        (EventKeyV2.CAREER_CHANGE, EffectAxis.EXIT_PRESSURE): (
            _FORMATION, "현재 자리를 떠나려는 압력",
        ),
        (EventKeyV2.JOB_GAIN, EffectAxis.SELECTION_PROGRESS): (
            _FORMATION, "평가·면접·선발 절차가 진행되는 정도",
        ),
        (EventKeyV2.JOB_GAIN, EffectAxis.ENTRY_REALIZATION): (
            _FORMATION, "실제 입사·합류로 이어지는 정도",
        ),
        (EventKeyV2.CONTRACT_DOCUMENT, EffectAxis.AGREEMENT_QUALITY): (
            _QUALITY, "계약·조건·문서 합의의 안정도",
        ),
        (EventKeyV2.PROMOTION, EffectAxis.STABILIZATION): (
            _QUALITY, "역할 정착·수습 통과의 안정도",
        ),
        (EventKeyV2.PROMOTION, EffectAxis.AGREEMENT_QUALITY): (
            _QUALITY, "내부 승진·전보 결정의 안정도",
        ),
        (EventKeyV2.PREPARATION_DELAY, EffectAxis.EXIT_FRICTION): (
            _FRICTION, "인수인계·통보 지연으로 인한 마찰",
        ),
        (EventKeyV2.SOCIAL_CONFLICT, EffectAxis.EXIT_FRICTION): (
            _FRICTION, "퇴사 과정의 관계·계약 장애",
        ),
        (EventKeyV2.BUSINESS_START, EffectAxis.OPPORTUNITY_ACTIVATION): (
            _FORMATION, "창업·독립을 포함한 진로 전환 기회",
        ),
    }
)

#: 어댑터가 신호로 인정하는 event_key — 이 목록 밖 후보는 커리어 축을 만들지 않는다.
CAREER_SIGNAL_KEYS: frozenset[EventKeyV2] = frozenset(k for k, _ in SIGNAL_AXIS_MAP)


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)


def _axis_value(mode: str, score: int, favorability: float) -> float:
    """기존 필드를 축 값으로 변환한다 — 새 가중치를 도입하지 않는다.

    `score` 는 표시용 내부값이라 절대값 신뢰가 금지된 값이다(events.py 주석). 여기서도
    **축 간 비교용 상대 여건**으로만 쓰며, 절대 성사 확률로 읽지 않는다. 캘리브레이션은
    후속 과제다.
    """
    if mode == _QUALITY:
        return _clamp01((favorability + 1.0) / 2.0)
    magnitude = _clamp01(score / 100.0)
    return -magnitude if mode == _FRICTION else magnitude


def build_career_contributions(
    candidates: Iterable[object],
) -> tuple[EffectContribution, ...]:
    """커리어 관련 후보를 축별 기여 1건씩으로 변환한다.

    Args:
        candidates: `event_key`·`period`·`score`·`favorability` 를 갖는 이벤트 후보들
            (`EventCandidate`/`EventCandidateV2` 모두 이 필드를 가진다).

    Returns:
        축별 기여 tuple(축당 최대 1건, 축 이름 순). 관련 신호가 없으면 빈 tuple —
        **없는 근거를 0 으로 채우지 않는다**.
    """
    best: dict[EffectAxis, tuple[float, float, str, str, str]] = {}
    for cand in candidates:
        key = getattr(cand, "event_key", None)
        if key is None:
            continue
        try:
            event_key = EventKeyV2(key)
        except ValueError:
            continue
        if event_key not in CAREER_SIGNAL_KEYS:
            continue
        period = str(getattr(cand, "period", "") or "")
        score = int(getattr(cand, "score", 0) or 0)
        favorability = float(getattr(cand, "favorability", 0.0) or 0.0)
        for axis in EffectAxis:
            spec = SIGNAL_AXIS_MAP.get((event_key, axis))
            if spec is None:
                continue
            mode, rationale = spec
            value = _axis_value(mode, score, favorability)
            signal_ref = f"{event_key.value}:{period}" if period else event_key.value
            # 같은 축에서는 절대값이 가장 큰 신호 하나만 남긴다(합산 금지).
            # 동률은 (signal_ref) 사전순으로 갈라 프로세스 간 결정론을 유지한다.
            rank = (abs(value), signal_ref)
            current = best.get(axis)
            if current is None or rank > (abs(current[0]), current[2]):
                best[axis] = (value, favorability, signal_ref, period, rationale)

    return tuple(
        EffectContribution(
            # 축마다 다른 evidence_id — 같은 신호가 여러 축에 들어가도 중복 가산이
            # 아니라는 것을 감사가 구조적으로 확인할 수 있게 한다.
            evidence_id=f"{signal_ref}#{axis.value}",
            signal_ref=f"{signal_ref} — {rationale}",
            axis=axis,
            role=ContributionRole.PRIMARY,
            value=value,
            period=period or None,
        )
        for axis, (value, _fav, signal_ref, period, rationale) in sorted(
            best.items(), key=lambda kv: kv[0].value
        )
    )


__all__ = [
    "CAREER_SIGNAL_KEYS",
    "SIGNAL_AXIS_MAP",
    "build_career_contributions",
]
