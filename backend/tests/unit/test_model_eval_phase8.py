"""Phase 8 T8.4 — 모델 평가 하네스 검증(결정적 지표 3종 + 랭킹)."""

from __future__ import annotations

from saju_engines.model_eval import compare_models, evaluate_response
from saju_shared_types.report import SectionContext

_CTX = SectionContext(
    section_id="EVAL",
    allowed_ganji=["丙午"],
    allowed_scores=[72],
    allowed_years=[2026],
    evidence_paths=["丙午 세운 → 정관 활성 → 직업 변화 72점"],
)

_GOOD = (
    "2026년 丙午 세운에는 정관이 활성화되며 직업 변화 에너지가 72점 수준으로 보여요. "
    "특히 6월~8월 구간과 하반기에 탐색 신호가 강해요. 결정은 4분기가 유리해 보여요."
)
_BAD = (
    "내년에는 반드시 이직한다. 癸亥 운이 들어와 편인이 강해지고 95점의 강한 운세다. "
    "2031년에도 좋다."
)


def test_good_response_scores_high() -> None:
    score = evaluate_response("model-a", _GOOD, _CTX)
    assert score.instruction_compliance == 100
    assert score.date_specificity >= 80  # 연도+월 구간+분기 인용
    assert score.term_accuracy == 100  # 근거 용어(정관) 정확 인용
    assert score.total >= 90 and not score.notes


def test_bad_response_penalized_per_metric() -> None:
    score = evaluate_response("model-b", _BAD, _CTX)
    assert score.instruction_compliance < 70  # 금지 표현 + 미제공 간지·점수
    assert any("금지 표현" in n for n in score.notes)
    assert any("재계산 의심" in n for n in score.notes)
    assert any("입력 밖 연도" in n for n in score.notes)
    assert any("근거 밖 용어" in n for n in score.notes)  # 편인 발명
    assert score.term_accuracy < 100


def test_compare_models_ranks_deterministically() -> None:
    ranked = compare_models({"model-b": _BAD, "model-a": _GOOD}, _CTX)
    assert [s.model for s in ranked] == ["model-a", "model-b"]
    # 결정성 — 동일 입력 동일 점수.
    again = compare_models({"model-b": _BAD, "model-a": _GOOD}, _CTX)
    assert [s.model_dump() for s in ranked] == [s.model_dump() for s in again]
