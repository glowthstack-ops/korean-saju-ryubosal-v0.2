"""겉/속 거짓 역접 결정론 재작성 회귀(2026-10-01) — 실답 재발 문장을 그대로 고정한다."""

from __future__ import annotations

import pytest

from saju_api.services.chat_service import finalize_answer_text
from saju_engines.contrast_rewrite import rewrite_false_contrast


@pytest.mark.parametrize(
    "before, after",
    [
        (
            "데굴님의 己亥(기해) 일주는 겉으로는 다정하고 부드럽지만 내면에는 거대한 강물 같은 "
            "지혜와 "
            "실속을 갖춘 구조입니다.",
            "데굴님의 己亥(기해) 일주는 겉으로는 다정하고 부드럽고, 내면에는 거대한 강물 같은 "
            "지혜와 "
            "실속을 갖춘 구조입니다.",
        ),
        (
            "己亥 일주는 겉으로는 부드러워 보이지만 내면에는 실속을 챙기는 영리함을 갖춘 "
            "구조입니다.",
            "己亥 일주는 겉으로는 부드러워 보이고, 내면에는 실속을 챙기는 영리함을 갖춘 "
            "구조입니다.",
        ),
        (
            "겉으로 보기에는 다정한 정원사 같은데, 그 내면에는 냉철한 판단력을 숨기고 있어요.",
            "겉으로 보기에는 다정한 정원사 같고, 그 내면에는 냉철한 판단력을 숨기고 있어요.",
        ),
        (
            "겉은 밝고 사교적인데 속은 원칙적이고 반듯해요.",
            "겉은 밝고 사교적이고, 속은 원칙적이고 반듯해요.",
        ),
        # ㅂ 불규칙 복원
        ("겉으로는 부드러운데 속은 단단한 분이에요.", "겉으로는 부드럽고, 속은 단단한 분이에요."),
    ],
)
def test_rewrites_false_contrast(before: str, after: str) -> None:
    out, changes = rewrite_false_contrast(before)
    assert out == after and len(changes) == 1


@pytest.mark.parametrize(
    "text",
    [
        "고집이 신념이 되면 큰 산이지만, 벽이 되면 외로워질 수 있어요.",  # 겉/속 표지 없음
        "겉으로 보이는 금액뿐만 아니라 그 이면의 배분 조건까지 따져보세요.",  # 연결어 없음
        "겉으로는 조용하지만 속에는 불만이 쌓일 수 있어요.",  # 긍정→부정 진짜 역접(속 절 부정어)
        "겉으로는 괜찮아 보여도 내면에는 부담이 큰 시기예요.",
    ],
)
def test_leaves_real_contrast_and_unrelated_sentences(text: str) -> None:
    out, changes = rewrite_false_contrast(text)
    assert out == text and changes == []


def test_only_target_sentence_changes_in_multi_sentence_answer() -> None:
    text = (
        "데굴님, 10월의 금전운은 유리한 흐름입니다. 데굴님의 己亥(기해) 일주는 겉으로는 다정하고 "
        "부드럽지만 내면에는 실속을 갖춘 구조입니다. 지금은 겉으로 보이는 금액뿐만 아니라 배분 "
        "조건까지 "
        "따져보세요."
    )
    out, changes = rewrite_false_contrast(text)
    assert len(changes) == 1
    assert out.startswith("데굴님, 10월의 금전운은 유리한 흐름입니다. ")
    assert "부드럽고, 내면에는" in out and out.endswith("따져보세요.")


def test_finalize_answer_text_applies_rewrite() -> None:
    out = finalize_answer_text(
        "己亥 일주는 겉으로는 다정하지만 내면에는 영리함을 갖춘 구조입니다.", "t"
    )
    assert "다정하고, 내면에는" in out
