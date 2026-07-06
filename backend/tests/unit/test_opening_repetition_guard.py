"""리포트·채팅 서두 반복 방지 (2026-07-06 테스터 지적, 데굴님 승인).

증상: 총운 매 페이지(섹션)와 채팅 매 답변이 비슷한 '나' 공통 묘사("○○님은 ~한 사주…")로
시작해 페이지를 안 넘긴 느낌을 준다. 수정: ①섹션 과제에 서두 금지 정적 지시 ②직전 생성
섹션들의 실제 첫 문장을 다음 섹션 프롬프트에 '서두 반복 금지' 블록으로 주입(순차 생성 활용)
③채팅 범위 지시에 첫 문장 규칙 추가. 모두 서술 전용 — 점수·간지·판정 불변.
"""

from __future__ import annotations

from datetime import date

from saju_api.services.chat_service import _CHAT_SCOPE_DIRECTIVE
from saju_api.services.report_service import (
    _MAX_RECENT_OPENINGS,
    _first_sentence,
    _ReportData,
    build_section_context,
)
from saju_engines.report_plan import build_section_plans
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:40",
    birth_place_name="서울", gender="male",
)

_SPEC = ReportSpec(
    product_code="RPT_FULL",
    subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
    period=ReportPeriod(start="2026-01", end="2026-12"),
)

_BAN_HEADER = "[서두 반복 금지 — 직전 섹션들이 이미 사용한 첫 문장]"


def _data() -> _ReportData:
    return _ReportData(_BIRTH, _SPEC, date(2026, 7, 6))


def _second_plan():
    plans = build_section_plans(_SPEC)
    return plans[1]


def test_static_opening_rule_in_every_section() -> None:
    """섹션 과제에 서두 금지 정적 지시가 항상 실린다."""
    data = _data()
    prompt = build_section_context(_second_plan(), _SPEC, data).body_prompt
    assert "명식 공통 묘사로 시작하지 말 것" in prompt


def test_ban_block_absent_without_recorded_openings() -> None:
    """기록이 없으면(dry-run·첫 섹션) 동적 블록 미부착 — 하위호환."""
    data = _data()
    prompt = build_section_context(_second_plan(), _SPEC, data).body_prompt
    assert _BAN_HEADER not in prompt


def test_ban_block_lists_recorded_openings() -> None:
    """직전 섹션 첫 문장이 기록되면 다음 섹션 프롬프트에 그대로 실린다."""
    data = _data()
    data.record_opening(
        "경신년 겨울에 태어난 회원님은 금 기운이 강한 사주입니다. 이어지는 본문은 무관하다."
    )
    prompt = build_section_context(_second_plan(), _SPEC, data).body_prompt
    assert _BAN_HEADER in prompt
    assert "- 경신년 겨울에 태어난 회원님은 금 기운이 강한 사주입니다." in prompt
    assert "같은 패턴·유사 표현으로 이 섹션을 시작하지 말 것" in prompt


def test_record_opening_keeps_recent_only() -> None:
    """기록은 최근 _MAX_RECENT_OPENINGS개만 유지(프롬프트 비대 방지)."""
    data = _data()
    for i in range(_MAX_RECENT_OPENINGS + 2):
        data.record_opening(f"{i}번째 섹션의 첫 문장이다. 나머지 본문.")
    assert len(data.recent_openings) == _MAX_RECENT_OPENINGS
    assert data.recent_openings[-1].startswith(f"{_MAX_RECENT_OPENINGS + 1}번째")


def test_first_sentence_extraction() -> None:
    """'다.' 기준 첫 문장 추출 — 종결어미 없으면 첫 줄, 상한 길이 보호."""
    assert _first_sentence("첫 문장이다. 둘째 문장이다.") == "첫 문장이다."
    assert _first_sentence("종결어미 없는 한 줄\n둘째 줄") == "종결어미 없는 한 줄"
    assert len(_first_sentence("가" * 500 + "다.")) <= 120


def test_chat_scope_directive_bans_common_opening() -> None:
    """채팅 범위 지시 — 첫 문장을 명식 공통 묘사로 열지 말라는 규칙 포함."""
    assert "명식 공통 묘사로 답변을 열지 말 것" in _CHAT_SCOPE_DIRECTIVE
    assert "첫 문장은 이번 질문에 대한 답" in _CHAT_SCOPE_DIRECTIVE
