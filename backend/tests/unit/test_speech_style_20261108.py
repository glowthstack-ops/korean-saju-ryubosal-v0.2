"""해요체 → 페르소나 말투 결정론 변환(docs/17 §26-3, 2026-11-08) — 사전 전 문장 커버리지·대표."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from saju_engines.speech_style import has_haeyo_ending, restyle, restyle_sentence

_DICT = Path(__file__).resolve().parents[2] / "dictionaries" / "daily_fortune"
_SKIP_META = {"since", "decision_ref", "note", "group_axes"}
_NO_ENDING_OK = ("늦게", "짧게", "꼼꼼히", "—")


def _sentences() -> list[str]:
    d = json.loads((_DICT / "daily_phrase_templates.json").read_text(encoding="utf-8"))
    out: list[str] = []

    def walk(o: object) -> None:
        if isinstance(o, str):
            out.extend(s for s in re.split(r"(?<=[.!?])\s+", o.strip()) if s)
        elif isinstance(o, dict):
            for k, v in o.items():
                if k not in _SKIP_META:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(d["simple_layer"])
    walk(d["month_layer"]["month_tone"])
    walk(d["month_layer"]["day_scene"])
    out.append("(일간과 운의 십성만 본 단식 풀이라 참고용이에요.)")
    return out


@pytest.mark.parametrize("style", ["hapsyo", "banmal_chae", "hagae"])
def test_every_dictionary_sentence_converts_without_haeyo_residue(style: str) -> None:
    sents = _sentences()
    assert len(sents) > 200
    for s in sents:
        out = restyle_sentence(s, style)
        if s.rstrip(".").endswith(_NO_ENDING_OK):
            assert out == s
            continue
        assert not has_haeyo_ending(out), (style, s, out)
        assert out != s, (style, s)


def test_representative_conversions() -> None:
    cases = {
        "받아들이고 쉬는 해예요.": (
            "받아들이고 쉬는 해입니다.", "받아들이고 쉬는 해야.", "받아들이고 쉬는 해일세.",
        ),
        "하던 일이 멈추거나 느려지기 쉬워요.": (
            "하던 일이 멈추거나 느려지기 쉽습니다.", "하던 일이 멈추거나 느려지기 쉬워.",
            "하던 일이 멈추거나 느려지기 쉽네.",
        ),
        "결이에요.": ("결입니다.", "결이야.", "결일세."),
        "기회가 늘어요.": ("기회가 늡니다.", "기회가 늘어.", "기회가 느네."),
        "도움이 와요.": ("도움이 옵니다.", "도움이 와.", "도움이 오네."),
        "손에 남는 걸 보세요.": (
            "손에 남는 걸 보는 것이 좋습니다.",
            "손에 남는 걸 보는 게 좋아.",
            "손에 남는 걸 보는 게 좋겠네.",
        ),
        "하지 마세요.": ("하지 않는 것이 좋습니다.", "하지 않는 게 좋아.", "하지 않는 게 좋겠네."),
        "(참고용이에요.)": ("(참고용입니다.)", "(참고용이야.)", "(참고용일세.)"),
        "맞는 말도 한 박자 늦게.": ("맞는 말도 한 박자 늦게.",) * 3,
    }
    for src, (hap, ban, hag) in cases.items():
        assert restyle_sentence(src, "hapsyo") == hap
        assert restyle_sentence(src, "banmal_chae") == ban
        assert restyle_sentence(src, "hagae") == hag
    assert restyle_sentence("그대로예요.", "haeyo") == "그대로예요."
    assert restyle("결이에요. 도움이 와요.", "hapsyo") == "결입니다. 도움이 옵니다."
