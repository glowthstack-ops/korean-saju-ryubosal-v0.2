"""계획 날짜가 해를 넘기는 이사 질문의 채팅 입력 (2026-11-21 데굴님 실답).

11월 21일의 "오늘 집이 팔렸어. 2월 12일 정도 이사를 해야해. … 좋은 선택일까?"가 오늘 일진 + 2026년
흉방으로 풀리던 결함. 질문 기간은 내년 2월(절기월)이고, 입춘 전후 세운·월운과 양쪽 해의 민속 흉방,
말한 날 무렵의 일운 참고가 엔진 값으로 실려야 한다.
"""

from __future__ import annotations

from datetime import date, time

from saju_api.services import chat_service
from saju_shared_types.birth_input import BirthInput

_BIRTH = BirthInput(
    birth_date=date(1980, 11, 22), birth_time=time(9, 40), birth_place_name="서울 구로구",
    gender="male", latitude=37.4944, longitude=126.8563, timezone="Asia/Seoul",
)
_TODAY = date(2026, 11, 21)
_QUESTION = (
    "우리가 오늘 집이 팔렸어. 2월 12일 정도 이사를 해야해. ㅠㅠ 우리 충청남도 아산으로 이사를 "
    "하려고 하는데 좋은 선택일까?"
)


def _prompt(question: str) -> str:
    res = chat_service.chat(_BIRTH, question, _TODAY, dry_run=True)
    assert res.status == "dry_run", res.answer
    assert res.prompt_preview is not None
    return res.prompt_preview


def test_planned_february_move_is_read_as_next_year_with_both_sides_of_ipchun() -> None:
    p = _prompt(_QUESTION)
    assert "질문 기간: 2027-02" in p
    # 입춘 전후 세운·월운(엔진 값)
    assert "[입춘 경계 — 양력 2027년 2월은 사주의 해가 바뀌는 달]" in p
    assert "세운 丙午" in p and "세운 丁未" in p and "사용자가 말한 2월 12일은 입춘 뒤에 든다" in p
    # 민속 흉방은 두 해 모두
    assert "[민속 흉방 입춘 경계]" in p
    assert "[민속 흉방 — 2026 丙午년" in p and "[민속 흉방 — 2027 丁未년" in p
    # 근사 날짜 — 그 달 중심, 말한 날 무렵 일운은 참고
    assert "[근사 날짜 — 사용자가 '2월 12일 정도'로 말한 무렵" in p
    assert "02-12(말한 날)" in p
    # 그 날 하루의 일진 중심 지시·오늘 일운 블록은 없다
    assert "특정 날짜를 물었으므로" not in p
    assert "[질문한 날짜의 일운 — 엔진 확정 사실] 2026-11-21" not in p


def test_exact_day_question_keeps_day_fortune_note() -> None:
    """반례 — 날짜를 못박아 물으면 종전대로 그 날 일운 중심."""
    p = _prompt("2월 12일에 이사해도 될까?")
    assert "특정 날짜를 물었으므로" in p and "[근사 날짜" not in p
    assert "[입춘 경계 — 질문한 날은 입춘 뒤]" in p
    assert "[민속 흉방 — 2027 丁未년" in p and "[민속 흉방 입춘 경계]" not in p
