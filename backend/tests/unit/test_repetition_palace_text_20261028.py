"""반복·자형 활성화 줄의 궁위별 가능성 영역(2026-10-28 데굴님 "진행하자").

월운 己亥 × 원국 亥 강의 대조 — 어느 기둥의 亥와 자형을 이루느냐(연·월·일·시)로 영역이 갈린다.
가능성 서술('~할 수 있다')은 단정이 아니다(데굴님 정정). 점수·사건 후보 불변, 서술 전용.
"""

from __future__ import annotations

import re

from saju_engines.repetition_structure import activation_line, load_repetition_text
from saju_shared_types.repetition_structure import RepetitionActivation

_ASSERTIVE = re.compile(r"반드시|틀림없이|확실히")


def _act(char: str, positions: list[str], kind: str = "period_new") -> RepetitionActivation:
    return RepetitionActivation(
        kind=kind, char=char, luck_char=char, layer="month",
        natal_positions=positions, is_self_punishment=char in "辰午酉亥",
    )


def test_dictionary_has_hae_palace_entries_and_activation() -> None:
    d = load_repetition_text()
    assert d["version"] == "1.1.0" and "palace_possibility" in d["principles"]
    hae = {x["palace"] for x in d["palace"] if x["char"] == "亥"}
    assert hae == {"year", "month", "day", "hour"}
    entry = next(x for x in d["self_punishment"] if x["char"] == "亥")
    assert entry.get("activation")
    for x in d["palace"]:
        assert not _ASSERTIVE.search(x["text"]), x
    assert not _ASSERTIVE.search(entry["activation"])


def test_activation_line_carries_palace_text_by_position() -> None:
    day = activation_line(_act("亥", ["day"]))
    assert "일지(배우자·몸)" in day and "새 친구·새 인연" in day and "활성화 결:" in day
    assert "승진·부서 이동" not in day  # 월지 문구는 일지 활성화에 섞이지 않는다
    month = activation_line(_act("亥", ["month"]))
    assert "월지(사회·직장)" in month and "승진·부서 이동" in month
    hour = activation_line(_act("亥", ["hour"]))
    assert "시지(자녀·지향·투자)" in hour and "자녀의 취업·진로" in hour
    year = activation_line(_act("亥", ["year"]))
    assert "연지(조상·사회 배경)" in year and "해외·먼 곳" in year
    both = activation_line(_act("亥", ["month", "day"], kind="natal_group_active"))
    assert "월지(사회·직장)" in both and "일지(배우자·몸)" in both
    assert "가능성 안내 — 사건 확정 아님" in both


def test_other_self_punishment_chars_fall_back_to_plain_line() -> None:
    line = activation_line(_act("辰", ["day"]))
    assert "자형(辰辰)" in line and "궁위 가능성 영역" not in line and "활성화 결" not in line


def test_non_self_punishment_repetition_has_no_palace_suffix() -> None:
    line = activation_line(_act("子", ["day"]))
    assert "子" in line and "궁위 가능성 영역" not in line
