"""오행 보완 음식 층 — 채팅 배선 회귀(dry_run, 2026-10-28).

실로그 "오늘 점심은 뭘 먹는게 좋을까"가 일운 5영역 총운으로 답하던 결함. 승격 턴의 프롬프트에는
음식 표·말미 지시·그날 일운 사실이 있어야 하고, 총운용 구조 블록(횡재 그릇·배우자성·연애 유형·
인상)·건강 취약·이벤트 후보는 없어야 한다. 색 질문·총운 질문은 기존 그대로.
"""

from __future__ import annotations

from datetime import date

from saju_api.services import chat_service
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import QueryType

_TODAY = date(2026, 10, 28)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date=_TODAY.isoformat(),
)


def _prompt(question: str) -> tuple[str, object]:
    res = chat_service.chat(_BIRTH, question, _TODAY, dry_run=True)
    assert res.status == "dry_run", res.answer
    assert res.prompt_preview is not None
    return res.prompt_preview, res.intents[0]


def test_lunch_question_gets_food_table_and_lean_prompt() -> None:
    p, intent = _prompt("오늘 점심은 뭘 먹는게 좋을까")
    assert intent.query_type is QueryType.REMEDY and intent.food_question is True
    # 있어야 하는 것
    assert "[오행 보완 음식 — 용희기구한 기준" in p
    assert "[오행 보완 음식 지침]" in p
    assert "[끼니 질문 — 말미 고정]" in p
    assert "[질문한 날짜의 일운 — 엔진 확정 사실] 2026-10-28" in p
    # 없어야 하는 것 — 총운용 구조 블록·건강 취약·이벤트 후보
    for banned in (
        "[원국 횡재 그릇", "[배우자성 — 성별 기준]", "[연애 유형 — ", "[궁위 관계망",
        "[외적 인상·분위기 구조", "[건강 취약", "[이벤트 후보 — ", "[이동 주체 미상]",
        "[참고 — 질문 기간 외 흐름",
    ):
        assert banned not in p, banned
    # 말미 지시가 음식 표보다 뒤에 있다(말미 고정)
    assert p.rfind("[끼니 질문 — 말미 고정]") > p.find("[오행 보완 음식 — 용희기구한 기준")


def test_plain_today_overview_unchanged() -> None:
    p, intent = _prompt("오늘 운세 봐줘")
    assert intent.query_type is QueryType.FORTUNE_OVERVIEW and intent.food_question is False
    assert "[오행 보완 음식" not in p and "[끼니 질문 — 말미 고정]" not in p
    assert "[원국 횡재 그릇" in p  # 총운 구조 블록은 그대로


def test_color_question_layer_not_affected() -> None:
    # 시점·도메인 없는 색 질문('커튼 색 추천해줘')은 기존대로 too_broad 로 바운스된다(색 층은
    # 라우팅 불변 — 승격 여부는 별도 결정). 분석 흐름을 타는 색 질문으로 비회귀만 확인한다.
    p, intent = _prompt("올해 학업운에 좋은 커튼 색 추천해줘")
    assert intent.color_question is True and intent.food_question is False
    assert "[오행 보완 색 — 용희기구한 기준" in p
    assert "[오행 보완 음식" not in p
