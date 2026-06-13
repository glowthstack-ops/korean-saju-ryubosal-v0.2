"""Past Validation 엔진 (v2.2 Phase 6 T6.1·T6.3, docs/02 E7).

T6.1: 과거 N년 이벤트 후보 — **Phase 2 스코어링을 역방향 재사용**한다. 스코어러의
세운 창(기준일 −4~+5년)을 10년 단위로 미끄러뜨려 과거 전 구간을 커버하고,
콜드리딩 방지 규칙(연도당 ≤2건, score 임계 엄격, evidence path 필수)을 적용한다.

T6.3: 사용자 확인 결과 → 맞춘 비율 → 신뢰도% → 미래 예측 표현 강도(보수화 단계).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventCandidate
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.past_validation import (
    CalibrationOutcome,
    PastCandidate,
    PastFeedbackItem,
    PastValidationResult,
)

from .event_engine_v2 import EventEngineV2

ComputeFn = Callable[[BirthInput], ManseV2Result]

PER_YEAR_MAX = 2  # 연도당 후보 상한(docs/07 리스크 3)
SCORE_FLOOR = 70  # 엄격 임계 — 세운 계층 필터와 동일 기준
# 표현 강도 경계(T6.3 초안): 맞춘 비율 기준.
_LEVEL_NORMAL = 0.6
_LEVEL_CONSERVATIVE = 0.3


def generate_past_candidates(
    birth: BirthInput,
    scorer: EventEngineV2,
    compute: ComputeFn,
    start_year: int,
    end_year: int,
    per_year_max: int = PER_YEAR_MAX,
    score_floor: int = SCORE_FLOOR,
) -> PastValidationResult:
    """과거 [start_year, end_year] 구간의 이벤트 후보를 생성한다(역방향).

    Args:
        birth: 대상 출생 정보.
        scorer: EventEngineV2(사전 로드 공유) — 레거시 호환 score_legacy 사용.
        compute: 만세 계산 함수(서비스 calculate 주입 — 캐시 활용).
        start_year, end_year: 검증 대상 연도 구간(과거).
        per_year_max: 연도당 후보 상한(콜드리딩 방지).
        score_floor: 점수 임계(엄격 적용).

    Returns:
        후보 목록(연도 오름차순, 연도당 ≤ per_year_max) — 전 후보 evidence path 동반.
    """
    by_year: dict[str, list[EventCandidate]] = {}
    # 스코어러 세운 창(기준일 −4~+5년)을 10년 간격으로 이동시켜 전 구간 커버.
    ref = start_year + 4
    while ref - 4 <= end_year:
        chart_birth = birth.model_copy(update={"reference_date": date(ref, 6, 15)})
        result = compute(chart_birth)
        for c in scorer.score_legacy(result, levels={GanjiLevel.YEAR}):
            year = c.period[:4]
            if year.isdigit() and start_year <= int(year) <= end_year:
                by_year.setdefault(year, []).append(c)
        ref += 10

    candidates: list[PastCandidate] = []
    for year in sorted(by_year):
        picked = sorted(
            (c for c in by_year[year] if c.score >= score_floor),
            key=lambda c: -c.score,
        )[:per_year_max]
        for c in picked:
            if not c.evidence_path:  # 근거 없는 후보 금지(스키마로도 강제)
                continue
            candidates.append(PastCandidate(
                year_range=year,
                event_key=c.event_key,
                score=c.score,
                evidence_path=c.evidence_path,
                readable=scorer.readable_path(c),
            ))
    return PastValidationResult(candidates=candidates)


def calibrate_confidence(feedback: list[PastFeedbackItem]) -> CalibrationOutcome:
    """사용자 확인 결과 → 신뢰도 → 표현 강도(T6.3).

    맞춘 비율이 낮으면 미래 예측 서술을 보수화한다(docs/02 E7: 신뢰도 %가 이후
    표현 강도에 반영). 피드백이 없으면 중립(conservative)로 시작.
    """
    total = len(feedback)
    matched = sum(1 for f in feedback if f.matched)
    ratio = matched / total if total else 0.0
    if total == 0:
        level, note = "conservative", "검증 전 — 보수적 표현으로 시작"
    elif ratio >= _LEVEL_NORMAL:
        level, note = "normal", "과거 검증 적중률 양호 — 표준 표현"
    elif ratio >= _LEVEL_CONSERVATIVE:
        level, note = "conservative", "부분 적중 — 가능성 중심의 보수적 표현"
    else:
        level, note = "very_conservative", "적중률 낮음 — 단정 회피·탐색형 표현"
    return CalibrationOutcome(
        matched=matched,
        total=total,
        calibrated_confidence=round(ratio, 3),
        expression_level=level,
        note=note,
    )
