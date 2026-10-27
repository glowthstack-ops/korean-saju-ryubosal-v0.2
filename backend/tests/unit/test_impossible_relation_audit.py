"""성립 불가 간지 관계 주장 감사(2026-10-27) — 위반 적발·반례·문장 제거·후처리 연결.

발단 실답: "일간인 戊(무)토와 운의 壬(임)수가 합을 이루어"(戊의 합은 癸). 과거 저장 답변 910건
전수 스캔에서 오탐 0건이 되도록 맞춘 규칙을 고정한다.
"""

from __future__ import annotations

import pytest

from saju_engines.impossible_relation_audit import (
    find_impossible_relation_claims,
    strip_impossible_relation_claims,
)


@pytest.mark.parametrize(
    ("text", "pair", "relation"),
    [
        ("일간인 戊(무)토와 운의 壬(임)수가 합을 이루어 인연이 자리 잡게 됩니다.", "戊壬", "합"),
        ("巳와 亥가 합을 이루니 좋은 흐름이에요.", "巳亥", "합"),
        ("자수와 축토가 충돌하는 달이에요.", "子丑", "충돌"),
        ("甲목과 乙목이 합해 힘이 커져요.", "甲乙", "합"),
        ("午와 卯가 서로 충하는 시기예요.", "午卯", "충"),
        ("辰과 酉가 만나 충을 이뤄요.", "辰酉", "충"),
        ("子와 午가 육합을 이뤄요.", "子午", "육합"),
        ("申과 酉가 원진으로 얽혀요.", "申酉", "원진"),
    ],
)
def test_detects_impossible_pairs(text: str, pair: str, relation: str) -> None:
    claims = find_impossible_relation_claims(text)
    assert [(c.pair, c.relation) for c in claims] == [(pair, relation)]


@pytest.mark.parametrize(
    "text",
    [
        "운에서 들어온 壬水 편재가 정인 丁火와 합을 이루어 불안을 걷어내요.",  # 연결어 없음
        "丁(정)화와 壬(임)수가 합을 이뤄요.",  # 정당한 천간합
        "巳와 亥가 충하고, 申과 巳가 합을 이루는 구조예요.",  # 주체 교체(巳申 육합)
        "丁(정)화와 壬(임)수 기운을 잘 써야 합니다.",  # '합니다'
        "戊토와 壬수는 합이 아니라 극의 관계예요.",  # 부정 문맥
        "子와 午의 기운이 충분히 강해요.",  # '충분'
        "寅과 午, 戌이 삼합을 이뤄요. 午·戌 반합도 있어요.",  # 삼합 부분
        "亥와 亥가 자형을 이루는 구조예요.",  # 자형
        "壬과 丁이 암합해요.",  # 암합은 판정 밖
        "寅과 巳가 형성하는 흐름이에요.",  # '형성'
        "卯와 酉가 충하는 달이에요.",  # 정당한 충
        "원국의 巳(사화)와 연지의 申(신금), 그리고 월운의 申(신금)이 만나 삼형의 긴장을 만들어요.",
        "사해충(亥·巳)이나 해해자형(亥·亥)의 기운이 있어요.",  # 괄호 속 관계어
        "丁과 亥가 합을 이뤄요.",  # 천간·지지 혼합은 판정 밖
    ],
)
def test_counter_examples_pass(text: str) -> None:
    assert find_impossible_relation_claims(text) == []


def test_strip_removes_only_violating_sentence() -> None:
    text = (
        "첫 문장이에요. 일간인 戊(무)토와 운의 壬(임)수가 합을 이루어 인연이 자리 잡아요. "
        "마지막 문장이에요.\n\n둘째 문단도 그대로예요."
    )
    out, claims = strip_impossible_relation_claims(text)
    assert [c.pair for c in claims] == ["戊壬"]
    assert out == "첫 문장이에요. 마지막 문장이에요.\n\n둘째 문단도 그대로예요."


def test_strip_is_noop_without_violation() -> None:
    text = "丁(정)화와 壬(임)수가 합을 이뤄요. 다음 문장이에요."
    assert strip_impossible_relation_claims(text) == (text, [])


def test_chat_finalize_strips_impossible_relation() -> None:
    from saju_api.services.chat_service import finalize_answer_text

    answer = (
        "좋은 흐름이에요. 일간인 戊(무)토와 운의 壬(임)수가 합을 이루어 인연이 생겨요. "
        "준비해 보세요."
    )
    out = finalize_answer_text(answer)
    assert "戊(무)토와 운의 壬(임)수가 합" not in out
    assert "좋은 흐름이에요." in out and "준비해 보세요." in out
