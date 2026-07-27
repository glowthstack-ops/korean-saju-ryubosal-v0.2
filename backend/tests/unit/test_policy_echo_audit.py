"""P0.5 내부 지시문 에코 차단 (2026-07-27 데굴님 지적)."""

from __future__ import annotations

from saju_engines.policy_echo_audit import detect_policy_echo, strip_policy_echo


def test_detects_policy_sentences():
    """'~ 서술 금지' 같은 내부 지침이 답변에 나오면 잡는다."""
    answer = (
        "오늘은 정리와 보완에 유리한 편이에요. "
        "장기·지배적 호전으로 확대 금지(상위 운의 지지가 없음). "
        "무리한 결정은 미루는 편이 좋겠어요."
    )
    echoes = detect_policy_echo(answer)
    assert len(echoes) == 1
    assert "금지" in echoes[0].matched


def test_detects_internal_enum_leak():
    """내부 enum 이름이 노출되면 잡는다."""
    assert detect_policy_echo("현재 상태는 LOCAL_FAVORABLE_ONLY 입니다.")


def test_normal_answer_is_untouched():
    """평범한 풀이 문장은 걸리지 않는다."""
    answer = (
        "오늘은 큰 흐름을 바꿀 정도는 아니지만, 밀린 일을 정리하거나 부담을 "
        "줄이기에는 상대적으로 나은 날이에요. 중요한 결정은 조건을 한 번 더 "
        "확인한 뒤에 하시는 편이 좋겠습니다."
    )
    assert detect_policy_echo(answer) == []


def test_strip_removes_only_the_echo_sentence():
    """노출 문장만 제거하고 나머지 문맥은 유지한다."""
    answer = (
        "오늘은 정리에 유리해요. 장기·지배적 호전으로 확대 금지. "
        "일정은 여유 있게 잡으세요."
    )
    cleaned, removed = strip_policy_echo(answer, detect_policy_echo(answer))
    assert removed == 1
    assert "확대 금지" not in cleaned
    assert "오늘은 정리에 유리해요" in cleaned
    assert "일정은 여유 있게 잡으세요" in cleaned
    assert detect_policy_echo(cleaned) == []
