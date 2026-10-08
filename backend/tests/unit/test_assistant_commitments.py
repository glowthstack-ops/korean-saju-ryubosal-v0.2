"""시스템 발언 원장 — 추출·병합(번복 이력)·검색 회귀(2026-10-01).

실로그 web-mup4m82l 답변 문장을 그대로 쓴다: 2턴 "연두색이나 초록색 계열을 선택해 보세요"(추천) →
3턴 "녹색을 더하는 것은 … 무겁게 할 수 있어요"(비권장). 녹색↔초록은 표면형이 달라 색 범주 정규화
('COLOR:木')로 같은 대상임을 알아야 번복(superseded) 이력이 남는다.
"""

from __future__ import annotations

from saju_engines.assistant_commitments import (
    content_tokens,
    extract_commitments,
    match_commitments,
    mentions_commitment,
    merge_commitments,
    prior_statement_lines,
)

_A2 = (
    "아들님, 사주에서 부족한 기운을 채워줄 커튼 색상은 용신인 화 기운을 돕는 따뜻한 계열이 가장 "
    "좋네요. "
    "붉은색이 부담스럽다면 같은 화 오행에 속하면서도 조금 더 부드러운 분홍색이나 보라색, 혹은 화를 "
    "생해주는 목 기운의 연두색이나 초록색 계열을 선택해 보세요. "
    "올해 안에 꼭 마무리하고 싶은 구체적인 공부 목표가 있다면, 그 목표를 위해 12월에 어떤 서류나 "
    "자격을 먼저 준비해두면 좋을까요?"
)
_A3 = (
    "아들님, 사주에 목 기운이 이미 두터운 상태에서 녹색을 더하는 것은 오히려 생각의 짐을 무겁게 할 "
    "수 있어요. "
    "지금은 오히려 붉은색이나 밝은 계열로 화 용신의 기운을 살려 머릿속을 명쾌하게 비워내는 것이 "
    "공부 "
    "효율을 높이는 길이에요."
)


def test_extract_keeps_recommendations_and_drops_questions() -> None:
    c = extract_commitments(_A2, turn=2, topic="education")
    quotes = [x.quote for x in c]
    assert any("연두색이나 초록색 계열을 선택해 보세요" in q for q in quotes)
    assert all(not q.endswith("?") for q in quotes)  # 되물음은 원장에 넣지 않는다
    assert all(x.polarity == "recommend" for x in c)


def test_color_tokens_normalize_to_element_category() -> None:
    assert "COLOR:木" in content_tokens("녹색을 추가해도 돼?")
    assert "COLOR:木" in content_tokens("니가 연두색이나 초록색계열 커튼을 추천해줬잖아")
    # 표면형 모드 — 거른 '특정 선택지' 판정용(분홍 ≠ 붉은색).
    assert "COLOR:火" not in content_tokens("분홍색 커튼", normalize=False)


def test_merge_marks_reversal_as_superseded_not_deleted() -> None:
    led = merge_commitments([], extract_commitments(_A2, 2))
    led = merge_commitments(led, extract_commitments(_A3, 3))
    green = next(x for x in led if "연두색" in x.quote)
    assert green.status == "superseded" and green.superseded_by_turn == 3
    assert any(x.polarity == "avoid" and x.source_turn == 3 for x in led)


def test_single_generic_token_overlap_does_not_supersede() -> None:
    led = merge_commitments([], extract_commitments("아침 산책을 추천해요.", 1))
    led = merge_commitments(led, extract_commitments("밤늦은 운동은 피하는 편이 좋아요.", 2))
    # '운동'↔'산책' 겹침 없음 — 일반어 1개로는 번복 아님
    assert all(x.status == "active" for x in led)


def test_match_returns_both_sides_of_reversal_for_challenge() -> None:
    led = merge_commitments([], extract_commitments(_A2, 2))
    led = merge_commitments(led, extract_commitments(_A3, 3))
    matched = match_commitments(led, "니가 연두색이나 초록색계열 커튼을 추천해줬잖아")
    turns = {m.source_turn for m in matched}
    assert turns == {2, 3}
    lines = prior_statement_lines(matched)
    assert any("T2 추천·T3에서 반대 발언으로 대체됨" in ln for ln in lines)
    assert any("T3 비권장·유효" in ln for ln in lines)


def test_match_empty_when_user_misremembers() -> None:
    led = merge_commitments([], extract_commitments(_A2, 2))
    assert match_commitments(led, "니가 노란색 커튼을 추천했잖아") == []


def test_mentions_commitment_for_option_check() -> None:
    led = merge_commitments([], extract_commitments(_A2, 2))
    assert mentions_commitment(led, "녹색을 추가해도 돼?")
    assert not mentions_commitment(led, "올해 재물운은 어때?")
