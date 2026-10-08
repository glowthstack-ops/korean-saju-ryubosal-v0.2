"""[원국 횡재 그릇] 블록 — 미성립 구조 명시·합성 금지·재성 역할 병기 (2026-10-08 데굴님 지적·승인).

로또 질문 답변이 "지장간에 숨은 식상생재의 통로"를 원국 특징처럼 서술했으나 엔진 판정은
암장 식상 통로 미성립이었다(庚申 丁亥 己亥 戊辰, 己일간). LLM이 일반 '발동 조건' 문장·준비기
'식상 동반'·지장간 잠재 신호 블록을 합성한 결과라, 블록이 구조별 성립/미성립을 모두 적고 합성을
금지하도록 바꿨다.
"""

from __future__ import annotations

from datetime import date

from saju_api.services.manse_service import calculate
from saju_engines.event_scoring import favorability_map
from saju_engines.preparation_context import build_preparation_context
from saju_engines.structural_context import preparation_context_lines, wealth_capacity_lines
from saju_engines.wealth_capacity import analyze_wealth_capacity
from saju_shared_types.birth_input import BirthInput


def _result():
    return calculate(BirthInput(
        birth_date="1980-11-22", birth_time="09:08", birth_place_name="서울",
        gender="male", reference_date=date(2026, 10, 8),
    ))


def test_block_lists_absent_structures_and_forbids_synthesis() -> None:
    """암장 식상 통로 미성립이 '미성립 구조'에 명시되고, 합성·숨은 통로 서술 금지가 들어간다."""
    r = _result()
    wc = analyze_wealth_capacity(r)
    assert wc.hidden_output is False  # 엔진 판정: 식상생재 통로 없음(庚 상관은 연간 투출·申 본기)
    text = "\n".join(wealth_capacity_lines(wc))
    assert "미성립 구조" in text and "암장 식상(식상생재 통로)" in text.split("미성립 구조", 1)[1]
    assert "'숨은·잠재 통로'로 서술 금지" in text
    assert "지장간에 숨은 식상생재" in text  # 금지 예시로 명시
    assert "모두 운의 사건이며 위 원국 구조 목록이 아니다" in text
    # 성립 구조는 엔진 flags 그대로.
    assert "성립 구조: " + ", ".join(wc.flags) in text


def test_block_carries_wealth_role_and_guards_glorification() -> None:
    """재성 오행의 용희기구한을 병기하고, 기·구신이면 미화 금지 문장을 붙인다."""
    r = _result()
    wc = analyze_wealth_capacity(r)
    role = favorability_map(r).get(wc.wealth_element)
    assert role in ("용신", "희신", "기신", "구신", "한신")
    text = "\n".join(wealth_capacity_lines(wc, role))
    assert f"재성 {wc.wealth_element}의 역할: {role}" in text
    if role in ("기신", "구신"):
        assert "미화하지 말고" in text
    else:
        assert "미화하지 말고" not in text
    # 역할 미지정 호출은 병기·가드 모두 없음(하위 호환).
    plain = "\n".join(wealth_capacity_lines(wc))
    assert "의 역할:" not in plain and "미화하지 말고" not in plain


def test_preparation_line_marks_output_as_luck_not_natal() -> None:
    """준비기 발현 후보의 '식상 동반'은 운 유입임을 명시해 원국 구조로 오독되지 않게 한다."""
    r = _result()
    assert r.luck_cycles is not None
    ctx = build_preparation_context(r.luck_cycles.yearly_luck, 2026)
    lines = preparation_context_lines(ctx)
    moderate = [ln for ln in lines if "발현 후보" in ln and "등급 중" in ln]
    for ln in moderate:
        assert "운에서의 식상생재 유입 — 원국 구조 아님" in ln
    assert not any("식상 동반(식상생재 유입)" in ln for ln in lines)
