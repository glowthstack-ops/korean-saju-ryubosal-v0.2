"""대운 합화 장기 배경 — 시점 속성으로 분리된 서사 전용 계층 (2026-07-31).

감사(DW-HWA, `scripts/audit_daewoon_hwa_cross_domain.py`)에서 확인된 것:

    대표 교체 17건 — 시점 이탈 12건(71%) / 시점 내 경쟁 패배 5건(29%)
    후보 동일 + quality 만 변경   0건
    맞대결 5건 근거 비교          B우세 3 / A우세 2 · 근거 수 차이(A−B) 평균 −1.4

    DAEWOON_HWA_RANKING_EFFECT_NOT_JUSTIFIED_ON_AUDITED_FIXTURES

기존 구현은 랭킹 직전에 `score` 를 곱해 **어느 시기가 대표가 되는지**까지 바꿨다.
그런데 분기는 `event_key` 가 아니라 `quality`(길/흉군)다 — 특정 사건의 발생을 지지한다는
뜻이 아닌 값이 occurrence selection 을 간접 지배한 것이다(P2-PROV-2a 가 경고한 지점).

그래서 배경을 **후보가 아니라 시점의 속성**으로 옮긴다. 후보 객체에 필드를 달지 않으므로
`_CANDIDATE_RANK_KEY` 가 구조적으로 접근할 수 없다 — "랭킹에 쓰지 않는다" 를 규율이 아니라
코드 구조로 강제한다.

    occurrence score / rank / 대표 시점   영향 없음
    canonical EventQuality                변경 없음
    대표 선정 이후 서사                    배경 반영

`strength` 를 두지 않는다. 기존 `0.03` 은 검증된 체감 강도가 아니라 랭킹 계수였고, 그대로
서사 강도로 넘기면 점수 계수를 의미 강도로 재사용하게 된다. 방향(supportive/pressuring)만
전달하며 '약함·중간·강함' 같은 등급도 만들지 않는다.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableSet, Sequence
from dataclasses import dataclass
from typing import Literal

from saju_shared_types.event_engine import EventQuality, PolarityRole

#: 시점 키(예: '2027-03', '2027') → 배경. 후보 키가 아니라 **시점** 키다.
BackgroundState = Literal["supportive", "pressuring", "neutral", "not_applicable"]

#: 감사 메타데이터 전용. 서사 강도가 아니며 렌더러가 읽어서는 안 된다.
LEGACY_SCORE_COEFFICIENT = 0.03

#: 기존 `reason_codes` 에 있던 문자열. 값 계약은 보존하되 위치를 배경으로 옮긴다 —
#: candidate 의 근거 목록에 남으면 다른 소비자가 여전히 "발생을 지지한 근거" 로 읽는다.
_EVIDENCE_CODE = {"supportive": "DAEWOON_HWA_BG_보강", "pressuring": "DAEWOON_HWA_BG_압력"}

_GOOD_Q = frozenset({
    EventQuality.OPPORTUNITY, EventQuality.ACHIEVEMENT, EventQuality.RESOLUTION,
})
_BAD_Q = frozenset({EventQuality.LOSS, EventQuality.PRESSURE, EventQuality.CONFLICT})


@dataclass(frozen=True)
class DaewoonHwaBackground:
    """한 시점의 대운 합화 장기 배경. **서사 전용**이다.

    `support_eligibility` 는 `REVIEW_REQUIRED` 로 고정한다 — 감사에서 occurrence 정합이
    입증되지 않았고(맞대결 5건, B우세 3/A우세 2), 이 값을 발생 지지 근거로 승격하려면
    별도 검증이 필요하다.
    """

    state: BackgroundState
    transformed_element: str | None = None
    transformed_role: PolarityRole | None = None
    evidence_code: str | None = None
    support_eligibility: Literal["REVIEW_REQUIRED"] = "REVIEW_REQUIRED"
    usage: Literal["narrative_background_only"] = "narrative_background_only"
    #: 감사 대조 전용 — 서사에 쓰지 않는다.
    legacy_score_coefficient: float = LEGACY_SCORE_COEFFICIENT

    @property
    def applicable(self) -> bool:
        """서사에 붙일 배경이 실제로 있는가."""
        return self.state in ("supportive", "pressuring")


#: 합화가 성립하지 않은 시점. 음성 대조에서 이 값이어야 한다.
NOT_APPLICABLE = DaewoonHwaBackground(state="not_applicable")


def derive_daewoon_hwa_background(
    role: PolarityRole | None, *, transformed_element: str | None = None
) -> DaewoonHwaBackground:
    """대운 化神의 용기신 역할 → 시점 배경. 점수 경로에서 호출하지 않는다.

    Args:
        role: 化神 오행의 용기신 역할. None 이면 합화 미성립(또는 한신 등 미분류).
        transformed_element: 化神 오행(한자). 근거 부록 표기용.

    Returns:
        서사 전용 배경. 어떤 경우에도 점수·순위·대표 시점을 바꾸지 않는다.
    """
    if role is None:
        return NOT_APPLICABLE
    if role is PolarityRole.NEUTRAL:
        return DaewoonHwaBackground(
            state="neutral", transformed_element=transformed_element,
            transformed_role=role,
        )
    state: BackgroundState = (
        "supportive" if role in (PolarityRole.YONG, PolarityRole.HEE) else "pressuring"
    )
    return DaewoonHwaBackground(
        state=state,
        transformed_element=transformed_element,
        transformed_role=role,
        evidence_code=_EVIDENCE_CODE[state],
    )


#: 배경 × 선택된 후보의 quality → 서사 프레임. **결합은 렌더링 단계에서만** 한다.
#: 배경 맵 자체는 후보 quality 를 담지 않는다.
#:
#: 어떤 조합도 canonical quality·polarity·favorability·score·rank·대표 시점·event family
#: 를 바꾸지 않는다. 전부 '이미 선택된' 사건의 체감에 대한 서술이다.
_FRAME: dict[tuple[str, str], str] = {
    ("supportive", "good"):
        "이미 선택된 유리한 흐름을 받쳐주는 장기 배경",
    ("supportive", "bad"):
        "이미 선택된 불리한 흐름의 부담을 일부 누그러뜨리는 장기 배경",
    ("pressuring", "good"):
        "이미 선택된 유리한 흐름에도 부담이나 제약을 더하는 장기 배경",
    ("pressuring", "bad"):
        "이미 선택된 불리한 흐름의 체감 부담을 키우는 장기 배경",
}


def _quality_axis(quality: EventQuality | None) -> str | None:
    if quality in _GOOD_Q:
        return "good"
    if quality in _BAD_Q:
        return "bad"
    return None


def background_narrative_frame(
    bg: DaewoonHwaBackground, quality: EventQuality | None
) -> str | None:
    """선정된 후보에 붙일 배경 서사 프레임. 붙일 것이 없으면 None.

    방향 없는 품질(mixed 등)은 결합 대상이 아니다 — 억지로 프레임을 붙이면 근거 없는
    체감 서술이 된다.
    """
    if not bg.applicable:
        return None
    axis = _quality_axis(quality)
    if axis is None:
        return None
    return _FRAME[(bg.state, axis)]


def background_narrative_block(
    representatives: Sequence[tuple[str, EventQuality | None]],
    backgrounds: Mapping[str, DaewoonHwaBackground],
    *,
    already_described: MutableSet[tuple[str, str]] | None = None,
) -> list[str]:
    """**선정된** 대표들에 붙일 배경 서술 줄. 대표 선정 이후에만 호출한다.

    같은 (시점, 방향)을 한 요청 안에서 여러 섹션이 반복 서술하면 배경이 실제보다 강한
    신호처럼 읽힌다. `already_described` 를 요청 단위로 넘겨 최초 1회만 상세 서술하고
    이후 섹션에서는 생략한다(SUMMARY·REUSE 는 아예 호출하지 않는 것이 낫다).

    Args:
        representatives: (시점 키, 선정된 후보의 canonical quality) 목록.
        backgrounds: 시점 배경 맵.
        already_described: 요청 단위 중복 방지 집합. None이면 이 호출 안에서만 중복 제거.

    Returns:
        서술 줄 목록. 붙일 배경이 없으면 빈 목록.
    """
    seen: MutableSet[tuple[str, str]] = (
        already_described if already_described is not None else set()
    )
    lines: list[str] = []
    for period, quality in representatives:
        bg = backgrounds.get(period)
        if bg is None or not bg.applicable:
            continue
        marker = (period, bg.state)
        if marker in seen:
            continue
        frame = background_narrative_frame(bg, quality)
        if frame is None:
            continue
        seen.add(marker)
        lines.append(f"{period}: {frame}")
    return lines


#: state → 사람이 읽는 방향 표기.
_STATE_KO = {"supportive": "보강(supportive)", "pressuring": "압력(pressuring)"}


def background_evidence_block(
    periods: Sequence[str],
    backgrounds: Mapping[str, DaewoonHwaBackground],
    *,
    already_described: MutableSet[tuple[str, str]] | None = None,
) -> list[str]:
    """LLM 입력용 **사실 블록**. 완성 문장이 아니라 구조화 사실 + 사용 계약을 준다.

    완성 문장을 답변에 덧붙이면 문맥과 겉돈다. 사실만 주고 서술은 LLM 이 문맥에 맞게
    하되, 허용 범위를 블록 안에 명시해 감사가 걷어낼 일을 줄인다.

    `legacy_score_coefficient` 는 넣지 않는다 — 검증된 체감 강도가 아니라 옛 랭킹
    계수이고, 숫자가 보이면 LLM 이 강약 근거로 쓴다.

    Args:
        periods: **이 섹션이 실제로 선택한** 시점만. 전역 목록을 넘기면 섹션이 쓰지도
            않는 시점의 배경이 노출된다.
        backgrounds: 시점 배경 맵.
        already_described: 요청 단위 중복 방지 집합. 같은 (시점, 방향)은 한 테마에서
            한 번만 상세 제공한다.

    Returns:
        블록 줄 목록. 붙일 배경이 없으면 **빈 목록**(머리글도 만들지 않는다).
    """
    seen: MutableSet[tuple[str, str]] = (
        already_described if already_described is not None else set()
    )
    rows: list[str] = []
    for period in periods:
        bg = backgrounds.get(period)
        if bg is None or not bg.applicable:
            continue  # not_applicable·neutral 은 블록을 만들지 않는다
        marker = (period, bg.state)
        if marker in seen:
            continue
        seen.add(marker)
        rows.append(f"- {period}: {_STATE_KO.get(bg.state, bg.state)}")
        if bg.evidence_code:
            rows.append(f"  근거: {bg.evidence_code}")
        rows.append(f"  사용: {bg.usage}")
    if not rows:
        return []
    return [
        "",
        "[장기 대운 배경 — 서사 참고 전용]",
        "(이미 선택된 흐름의 체감을 설명할 때만 쓴다. 사건의 발생·성사·시점 선정·대표 "
        "순위의 근거로 쓰지 말 것 — 이 값은 그런 근거가 아니다.)",
        *rows,
    ]
