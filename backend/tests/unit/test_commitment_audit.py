"""정정·조건 준수 shadow 감사 회귀(2026-10-01) — 실답은 걸리고 모범 정정문은 통과한다."""

from __future__ import annotations

from saju_engines.commitment_audit import audit_answer

_EXCLUDED = ["커텐으로 할건데 붉은색은 좀 그래"]
_MATCHED = ["- (T2 추천·T3에서 반대 발언으로 대체됨) “…연두색이나 초록색 계열을 선택해 보세요.”"]
# 실로그 4턴 실답 — 자기 발언 부인("…드린 말씀이에요") + 배제한 붉은색 재추천.
_REAL_BAD = (
    "아들님, 사주에 나무 기운이 이미 가득한데 커튼까지 초록으로 채우면 생각만 많아지고 몸이 "
    "무거워질 수 "
    "있어서 드린 말씀이에요. 지금은 밖으로 기운을 내뿜어야 하는 시기라 붉은색이나 밝은 조명으로 방 "
    "안의 "
    "온기를 돋우는 편이 학업 능률을 올리는 데 훨씬 이롭네요."
)
_GOOD = (
    "맞아요. 제가 앞서 연두색과 초록색 커튼을 추천했습니다. 그런데 사주 판정상 목은 기신이라 그 "
    "추천을 "
    "철회합니다. 붉은색이 부담스럽다고 하셨으니 희신 금의 흰색·회색 계열이 1차 대안이에요."
)


def test_real_log_answer_is_flagged() -> None:
    res = audit_answer(
        _REAL_BAD, is_challenge=True, matched_quotes=_MATCHED, excluded_quotes=_EXCLUDED,
    )
    assert "no_acknowledgment" in res.violations
    assert "excluded_reoffered" in res.violations


def test_model_correction_passes() -> None:
    res = audit_answer(_GOOD, is_challenge=True, matched_quotes=_MATCHED, excluded_quotes=_EXCLUDED)
    assert res.passed, res.violations


def test_pivot_mention_of_excluded_option_is_not_reoffer() -> None:
    """'붉은색이 부담스럽다면 분홍을 …'은 거른 색을 전제로만 언급 — 재제시 아님(표면형 비교)."""
    ans = "붉은색이 부담스럽다면 같은 화 오행의 분홍색이나 주황 계열을 선택해 보세요."
    res = audit_answer(ans, is_challenge=False, matched_quotes=[], excluded_quotes=_EXCLUDED)
    assert "excluded_reoffered" not in res.violations


def test_no_ack_check_when_not_challenge_or_no_match() -> None:
    res = audit_answer(
        "초록은 기신 색이라 삼가는 편이 좋아요.", is_challenge=False, matched_quotes=_MATCHED,
                       excluded_quotes=[])
    assert "no_acknowledgment" not in res.violations
    res2 = audit_answer(
        "초록은 기신 색이라 삼가는 편이 좋아요.", is_challenge=True, matched_quotes=[],
                        excluded_quotes=[])
    assert res2.passed


def test_effect_assertion_flagged() -> None:
    ans = "초록 커튼 때문에 잡생각이 늘어나고 실행력이 떨어져요."
    res = audit_answer(ans, is_challenge=False, matched_quotes=[], excluded_quotes=[])
    assert "effect_assertion" in res.violations
