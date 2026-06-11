"""모델 평가 하네스 (v2.2 Phase 8 T8.4 — 기존 Gemini 평가 방법론 재사용).

후보 모델의 통변 응답을 **결정적 지표 3종**으로 채점해 비교한다(LLM 채점 아님):
  1. instruction 준수 — 금지 표현 0건 + 재계산 금지 준수(미제공 간지/수치 미출현)
  2. 날짜 구체성 — 시기 표현(연·월·구간) 인용 밀도
  3. 용어 정확도 — 입력 근거의 용어를 정확히 인용했는가(왜곡·발명 없음)

입력 기준은 SectionContext와 동일(코드가 확정한 사실 데이터) — 보고서 정합성
검사기(report_checks)와 같은 원천을 공유한다.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from saju_shared_types.report import SectionContext

from .report_checks import _GANJI_RE, _PROHIBITED_PATTERNS, _SCORE_RE, _YEAR_RE

# 시기 구체성 — 연/월/구간/분기 표현.
_PERIOD_RE = re.compile(
    r"(?:19|20)\d{2}년|\d{1,2}월|상반기|하반기|[1-4]분기|\d{1,2}월\s*[~-]\s*\d{1,2}월"
)
# 명리 용어(입력 근거 인용 정확도 측정 대상).
_TERMS = [
    "정관", "편관", "정인", "편인", "식신", "상관", "비견", "겁재", "정재", "편재",
    "용신", "기신", "희신", "삼합", "육합", "충", "공망",
]


class ModelScore(BaseModel):
    """모델 1개의 응답 채점 결과(0~100)."""

    model: str
    instruction_compliance: int = Field(ge=0, le=100)
    date_specificity: int = Field(ge=0, le=100)
    term_accuracy: int = Field(ge=0, le=100)
    total: int = Field(ge=0, le=100)
    notes: list[str] = Field(default_factory=list)


def evaluate_response(
    model: str, response: str, context: SectionContext
) -> ModelScore:
    """응답 1건 채점 — 결정적(동일 입력=동일 점수)."""
    notes: list[str] = []

    # 1. instruction 준수 — 금지 표현·미제공 간지·미제공 수치 감점.
    compliance = 100
    for pattern in _PROHIBITED_PATTERNS:
        if re.search(pattern, response):
            compliance -= 30
            notes.append(f"금지 표현 출현: /{pattern}/")
    allowed = set(context.allowed_ganji)
    for ganji in set(_GANJI_RE.findall(response)):
        if ganji not in allowed:
            compliance -= 20
            notes.append(f"미제공 간지(재계산 의심): {ganji}")
    for m in _SCORE_RE.finditer(response):
        if context.allowed_scores and int(m.group(1)) not in context.allowed_scores:
            compliance -= 15
            notes.append(f"미제공 점수: {m.group(1)}점")
    compliance = max(0, compliance)

    # 2. 날짜 구체성 — 시기 표현 수(5개 이상 만점) + 허용 연도 위반 감점.
    periods = _PERIOD_RE.findall(response)
    specificity = min(100, len(periods) * 20)
    for m in _YEAR_RE.finditer(response):
        if context.allowed_years and int(m.group(1)) not in context.allowed_years:
            specificity = max(0, specificity - 30)
            notes.append(f"입력 밖 연도: {m.group(1)}년")

    # 3. 용어 정확도 — 근거 경로에 등장한 용어의 재인용률(발명 용어 감점).
    evidence_text = " ".join(context.evidence_paths)
    expected = [t for t in _TERMS if t in evidence_text]
    if expected:
        cited = sum(1 for t in expected if t in response)
        accuracy = round(100 * cited / len(expected))
    else:
        accuracy = 100  # 근거에 용어가 없으면 중립
    invented = [
        t for t in _TERMS
        if t in response and evidence_text and t not in evidence_text
    ]
    if invented:
        accuracy = max(0, accuracy - 15 * len(invented))
        notes.append(f"근거 밖 용어 사용: {', '.join(invented)}")

    total = round(compliance * 0.5 + specificity * 0.25 + accuracy * 0.25)
    return ModelScore(
        model=model,
        instruction_compliance=compliance,
        date_specificity=specificity,
        term_accuracy=accuracy,
        total=total,
        notes=notes,
    )


def compare_models(
    responses: dict[str, str], context: SectionContext
) -> list[ModelScore]:
    """모델별 응답 비교 — total 내림차순 랭킹."""
    scores = [evaluate_response(m, r, context) for m, r in responses.items()]
    scores.sort(key=lambda s: -s.total)
    return scores
