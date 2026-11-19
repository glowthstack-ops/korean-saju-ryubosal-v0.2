"""실답 검수(web-mwkfla3y, 2026-11-17 '이번주중 로또사기 좋은 날') 교정 4건.

어제 고친 두 유형(천간 누락·등급 올림)은 재발하지 않았고, 감사가 보지 않던 유형이 나왔다.

  A. 걸리는 관계 2건인 날을 "두 날 모두 … 큰 갈등이 없어"로 묶어 말했다 → 말미 표 인용 규칙.
  B. "금요일 저녁 판매 마감 전까지" — 판매 마감은 토요일 저녁이다 → 기간 기준 줄 + 로그 감사.
  C. 용신 천간·'감당하는 조건' 라벨인 날에 '예상 밖의 지출'을 지어 붙였다 → 말미 표 인용 규칙.
  D. "일주일의 활력소로 삼는 지혜"가 일주 소개 문장 감사에 걸려 지워졌다 → 패턴 교정.
"""

from __future__ import annotations

from datetime import date

from saju_api.services.chat_service import _week_frame_notes
from saju_engines.context_reducer import _DATE_TABLE_GRADE_INSTRUCTION
from saju_engines.date_table_audit import audit_date_table_answer
from saju_engines.ilju_mention_audit import audit_ilju_mention, is_ilju_intro_sentence
from saju_engines.time_parser import WEEK_FRAME_SUN_SAT
from saju_shared_types.events import EventKey
from saju_shared_types.intent import Granularity, QueryType, TimeRange
from saju_shared_types.llm_input import DateChoiceRow, DateSelectionBlock

_REMOVED = (
    "이번 회차는 큰 승부를 보기보다 일주일의 활력소로 삼는 지혜가 필요한 시기이니, "
    "정해진 소액 안에서 즐기며 좋은 꿈 꾸시길 바랍니다."
)


# ── D. 일주 감사 오삭제 ──────────────────────────────────────────


def test_week_word_is_not_a_day_pillar_mention() -> None:
    assert not is_ilju_intro_sentence(_REMOVED)
    assert not is_ilju_intro_sentence("앞으로 일주간은 여유를 갖는 지혜가 필요합니다.")
    assert not is_ilju_intro_sentence("입사 일주년을 맞아 내면을 돌아보는 시기입니다.")
    answer = f"수요일이 무난합니다. {_REMOVED}"
    audit = audit_ilju_mention(answer, QueryType.DATE_RECOMMENDATION)
    assert audit.text == answer and not audit.removed


def test_day_pillar_intro_still_removed() -> None:
    """반례: 진짜 일주 소개 문장은 그대로 걷어낸다('일주 간지' 표기 포함)."""
    intro = "己亥(기해) 일주는 겉으로는 다정하고 여유로워 보이지만 내면에는 치밀함을 품고 있습니다."
    assert is_ilju_intro_sentence(intro)
    assert is_ilju_intro_sentence("일주간지 己亥는 부드러운 성향을 품은 구조입니다.")
    audit = audit_ilju_mention(f"{intro} 수요일이 무난합니다.", QueryType.DATE_RECOMMENDATION)
    assert audit.removed and "일주는" not in audit.text and "수요일이 무난합니다." in audit.text


# ── B. 로또 판매 마감 요일 ───────────────────────────────────────


def _lotto_block(frame_notes: list[str]) -> DateSelectionBlock:
    return DateSelectionBlock(
        purpose_ko="횡재", period="2026-11-17 – 2026-11-21", frame_notes=frame_notes,
        grade_notes=["[추천]은 …"], has_recommended=False,
        rows=[
            DateChoiceRow(
                date="2026-11-20", weekday="금", ganji="戊戌", score=70,
                recommendation="acceptable",
                stem_ten_god="겁재", branch_ten_god="겁재", stem_role="용신"),
        ],
    )


def test_frame_note_pins_deadline_to_saturday() -> None:
    tr = TimeRange(
        type="relative", granularity=Granularity.DAY, start="2026-11-15", end="2026-11-21",
        week_label="이번 주", week_frame=WEEK_FRAME_SUN_SAT,
    )
    joined = " ".join(_week_frame_notes(tr, EventKey.WINDFALL, date(2026, 11, 17)))
    assert "판매 마감은 토요일 저녁 한 번뿐이다" in joined
    assert "다른 요일에 '판매 마감'을 붙이지 않는다" in joined
    assert "표의 등급대로 다른 날을 안내" in joined
    # 횡재가 아닌 목적에는 회차 문장이 없다.
    other = _week_frame_notes(tr, EventKey.RELOCATION, date(2026, 11, 17))
    assert "판매 마감" not in " ".join(other)


def test_audit_flags_deadline_on_wrong_weekday() -> None:
    frame = ["로또는 일요일부터 토요일 저녁 판매 마감 전까지 산 분량을 …"]
    real = (
        "토요일인 11월 21일은 일지와 시지의 글자들이 서로 강하게 충돌하고 얽히는 지점이 많아, "
        "가급적 금요일 저녁 판매 마감 전까지 준비를 마치시는 것이 좋겠습니다."
    )
    audit = audit_date_table_answer(real, _lotto_block(frame))
    assert len(audit.deadline_misplaced) == 1 and not audit.clean
    assert not audit.stem_omitted and not audit.grade_raised


def test_audit_deadline_counter_examples() -> None:
    frame = ["로또는 일요일부터 토요일 저녁 판매 마감 전까지 산 분량을 …"]
    block = _lotto_block(frame)
    ok = "토요일에 사신다면 토요일 저녁 판매 마감 전에 사야 이 회차에 들어갑니다."
    assert audit_date_table_answer(ok, block).clean
    # 요일 뒤에 다른 말이 끼면 그 요일의 마감이 아니다.
    assert audit_date_table_answer("금요일에 사 두시면 마감에 쫓기지 않습니다.", block).clean
    # 회차 기준 줄이 없는 표(다른 목적)는 '금요일 마감'을 문제 삼지 않는다.
    assert audit_date_table_answer("서류는 금요일 마감 전에 내세요.", _lotto_block([])).clean
    # 등급 기준이 없는 표여도 회차 기준 줄이 있으면 마감 요일은 본다.
    bare = _lotto_block(frame).model_copy(update={"grade_notes": []})
    assert audit_date_table_answer("금요일 판매 마감 전에 사세요.", bare).deadline_misplaced


# ── A·C. 말미 표 인용 규칙 ───────────────────────────────────────


def test_grade_instruction_covers_clash_denial_and_invented_reasons() -> None:
    assert "'걸리는 관계 N건'이 적힌 날은 그 관계를 주의 사유로" in _DATE_TABLE_GRADE_INSTRUCTION
    assert "여러 날을 한 문장으로 묶을 때도 같다" in _DATE_TABLE_GRADE_INSTRUCTION
    assert "표 사유에 없는 사유(지출·경쟁·손실 등)" in _DATE_TABLE_GRADE_INSTRUCTION
    # 어제 규칙은 그대로다.
    assert "천간 십성과 지지 십성을 함께" in _DATE_TABLE_GRADE_INSTRUCTION
