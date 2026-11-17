"""다인 이사 택일 — 구성원별 풀이(2026-11-17 데굴님 결정).

"다인 이사 택일의 경우에는 모든 구성원을 대상으로 풀이 해주는게 나을 것 같아. 사용자 판단에
맡기는거지." · "동반자 제한은 다자 비교 상한에 맞추는게 맞겠어."

종전 그룹 표는 본인 + 상대 1명만 받았고, 일 단위 점수·회피일을 첫 구성원의 일진만으로 계산해
상대의 기신 천간·충이 반영되지 않았다. 지금은 구성원마다 단일 이사 택일 엔진을 돌려 등급·사유를
나란히 싣는다. 여기서는 그 표의 불변식과 반례를 고정한다(LLM 미호출).
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services import chat_service
from saju_engines.context_reducer import (
    _DATE_TABLE_GROUP_INSTRUCTION,
    _DATE_TABLE_INSTRUCTION,
)
from saju_engines.date_selection import reality_allows_day
from saju_engines.query_parser import parse_message
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.llm_input import DateSelectionBlock

_TODAY = date(2026, 6, 11)
_SELF = BirthInput(
    calendar_type="solar", birth_date=date(1990, 3, 15), birth_time="10:00",
    birth_place_name="서울", gender="male",
)
_PARTNER = BirthInput(
    calendar_type="solar", birth_date=date(1992, 7, 20), birth_time="14:00",
    birth_place_name="서울", gender="female",
)
_CHILD = BirthInput(
    calendar_type="solar", birth_date=date(2015, 3, 9), birth_time="14:00",
    birth_place_name="서울", gender="female",
)
_UNFAVORABLE = ("기신", "구신")


def _intent(question: str = "배우자랑 같이 이사 좋은 날 언제야?"):
    return parse_message(question, _TODAY, birth_year=1990).intents[0]


@pytest.fixture(scope="module")
def block() -> DateSelectionBlock:
    """본인·배우자·아이 3인 이사 택일 블록."""
    out = chat_service._relocation_group_block(
        [("본인", _SELF), ("배우자", _PARTNER), ("아이", _CHILD)], _intent(), _TODAY,
    )
    assert out is not None
    return out


def test_every_row_carries_every_member_in_order(block) -> None:
    assert block.group_members == ["본인", "배우자", "아이"]
    assert 0 < len(block.rows) <= chat_service._GROUP_DATE_ROWS
    for row in block.rows:
        assert [m.label for m in row.members] == block.group_members
        assert all(m.recommendation in ("recommended", "acceptable", "avoid") for m in row.members)
        assert all(m.notes for m in row.members)


def test_member_grade_follows_that_members_own_stem_role(block) -> None:
    """등급은 구성원 각자의 명식 기준 — 기신·구신 천간인 구성원은 그날 [추천]이 아니다."""
    seen_unfavorable = False
    for row in block.rows:
        for m in row.members:
            if m.stem_role in _UNFAVORABLE:
                seen_unfavorable = True
                assert m.recommendation != "recommended"
            if m.stem_ten_god:  # 후보로 계산된 줄은 그 사람 기준 천간 십성으로 시작한다
                assert m.notes[0].startswith(f"천간 {row.ganji[0]} {m.stem_ten_god}({m.stem_role})")
    assert seen_unfavorable  # 이 픽스처에는 누군가에게 기신·구신 천간인 날이 표에 있다


def test_members_can_disagree_on_the_same_day(block) -> None:
    """반례(종전 결함): 첫 구성원에게 [추천]인 날이 다른 구성원에게는 [추천]이 아닐 수 있다."""
    split = [
        r for r in block.rows
        if r.members[0].recommendation == "recommended"
        and any(m.recommendation != "recommended" for m in r.members[1:])
    ]
    assert split
    # 행 등급은 '구성원 모두 추천'일 때만 recommended 다.
    assert all(r.recommendation == "acceptable" for r in split)


def test_rows_sorted_by_recommended_headcount_not_group_score(block) -> None:
    def key(row) -> tuple[int, int, str]:
        rec = sum(1 for m in row.members if m.recommendation == "recommended")
        avoid = sum(1 for m in row.members if m.recommendation == "avoid")
        return (-rec, avoid, row.date)

    assert [key(r) for r in block.rows] == sorted(key(r) for r in block.rows)


def test_summary_notes_state_facts_and_leave_choice_to_user(block) -> None:
    joined = " ".join(block.grade_notes)
    assert "구성원마다 그 사람 명식으로 따로 매겼다" in joined
    assert "어느 구성원을 기준으로 고를지는 사용자가 정한다" in joined
    all_rec = [
        r.date for r in block.rows if all(m.recommendation == "recommended" for m in r.members)
    ]
    if all_rec:
        assert all(d in joined for d in all_rec)
    else:
        assert "구성원 모두 [추천]인 날이 없다" in joined
    assert block.has_recommended is None  # '1–3개 추천' 분기를 타지 않는다


def test_date_level_facts_sit_on_the_date_line_not_member_lines(block) -> None:
    for row in block.rows:
        for m in row.members:
            assert "손없는 날" not in m.notes
            assert not any(n.startswith("공휴일(") for n in m.notes)
    assert any("손없는 날" in r.notes for r in block.rows)


def test_direction_lines_per_member_and_common(block) -> None:
    assert sum(1 for ln in block.group_lines if ln.startswith("방위(구성원 공통)")) == 1
    for label in block.group_members:
        assert any(ln.startswith(f"방위({label}): ") for ln in block.group_lines)
    assert not block.directions  # 평균 방위 표는 쓰지 않는다('남(None)' 누출 경로 제거)


def test_weekend_only_constraint_filters_rule_avoid_days_too() -> None:
    """현실 제약으로 후보가 아닌 날은 금기일로도 되살리지 않는다."""
    intent = _intent("배우자랑 같이 이사 좋은 날 언제야? 주말만 가능해")
    out = chat_service._relocation_group_block(
        [("본인", _SELF), ("배우자", _PARTNER)], intent, _TODAY,
    )
    assert out is not None
    assert all(date.fromisoformat(r.date).weekday() >= 5 for r in out.rows)
    assert reality_allows_day(date(2026, 6, 13), ["주말만 가능"])
    assert not reality_allows_day(date(2026, 6, 15), ["주말만 가능"])
    assert not reality_allows_day(date(2026, 6, 13), ["평일만 가능"])
    assert reality_allows_day(date(2026, 6, 15), ["평일 선호"])  # 선호는 필터가 아니다
    assert reality_allows_day(date(2026, 6, 15), None)


def test_single_member_returns_none() -> None:
    assert chat_service._relocation_group_block([("본인", _SELF)], _intent(), _TODAY) is None
    # 같은 사람을 두 번 넣어도 한 명이다(기준일만 다른 같은 출생 정보).
    twin = _SELF.model_copy(update={"reference_date": _TODAY})
    assert chat_service._relocation_group_block(
        [("본인", _SELF), ("나", twin)], _intent(), _TODAY,
    ) is None


def test_group_members_dedupe_cap_and_missing_birth() -> None:
    others = [
        BirthInput(
            calendar_type="solar", birth_date=date(1960 + i, 5, 1 + i), birth_time="08:00",
            birth_place_name="서울", gender="female",
        )
        for i in range(5)
    ]
    # 칩 상대가 지칭 목록에도 있으면 한 번만, 출생 정보 없는 동반자는 건너뛴다.
    members, truncated = chat_service._relocation_group_members(
        base=("본인", _SELF), partner=("아내", _PARTNER),
        companions=[("아내", _PARTNER), ("미등록", None), ("아이", _CHILD)], cap=4,
    )
    assert [label for label, _ in members] == ["본인", "아내", "아이"] and not truncated
    # 지칭 목록에 없는 칩 상대는 뒤에 붙는다.
    members, _ = chat_service._relocation_group_members(
        base=("본인", _SELF), partner=("아내", _PARTNER), companions=[("아이", _CHILD)], cap=4,
    )
    assert [label for label, _ in members] == ["본인", "아이", "아내"]
    # 상한(다자 비교 상한과 같은 값) 초과분은 빼고 그 사실을 돌려준다.
    members, truncated = chat_service._relocation_group_members(
        base=("본인", _SELF), partner=None,
        companions=[(f"동반자{i}", b) for i, b in enumerate(others)], cap=4,
    )
    assert len(members) == 5 and truncated
    # 기준 대상과 같은 사람은 구성원으로 다시 세지 않는다.
    members, _ = chat_service._relocation_group_members(
        base=("본인", _SELF), partner=("나", _SELF.model_copy(update={"reference_date": _TODAY})),
        companions=[], cap=4,
    )
    assert len(members) == 1


def test_truncation_note_and_duplicate_labels() -> None:
    out = chat_service._relocation_group_block(
        [("본인", _SELF), ("가족", _PARTNER), ("가족", _CHILD)], _intent(), _TODAY,
        members_truncated=True,
    )
    assert out is not None
    assert out.group_members == ["본인", "가족", "가족(2)"]
    assert any("앞 3명까지만 실었다" in c for c in out.cautions)


def test_group_instruction_differs_from_single_pick() -> None:
    assert "1–3개 날짜를 명확히 추천할 것" in _DATE_TABLE_INSTRUCTION
    assert "추천할 것" not in _DATE_TABLE_GROUP_INSTRUCTION
    assert "회피성 답변을 절대 하지 말 것" in _DATE_TABLE_GROUP_INSTRUCTION
    assert "사용자가 정하도록 맡길 것" in _DATE_TABLE_GROUP_INSTRUCTION
