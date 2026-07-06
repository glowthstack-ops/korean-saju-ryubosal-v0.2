"""리포트·채팅 서두 반복 방지 (2026-07-06 테스터 지적, 데굴님 승인).

증상: 총운 매 페이지(섹션)와 채팅 매 답변이 비슷한 '나' 공통 묘사("○○님은 ~한 사주…")로
시작해 페이지를 안 넘긴 느낌을 준다 — 한 스레드 안 후속 답변도 동일. 수정: ①섹션 과제에
서두 금지 정적 지시 ②직전 생성 섹션들의 실제 첫 문장을 다음 섹션 프롬프트에 '서두 반복
금지' 블록으로 주입(순차 생성 활용 — 총운·한해·집중 전 상품 공통 경로) ③채팅 범위 지시에
첫 문장 규칙 추가 ④스레드 후속 턴에 직전 답변 첫 문장 제시. 모두 서술 전용 — 점수·간지·
판정 불변.
"""

from __future__ import annotations

from datetime import date

from saju_api.services import chat_service
from saju_api.services.chat_service import _CHAT_SCOPE_DIRECTIVE
from saju_api.services.report_service import (
    _MAX_RECENT_OPENINGS,
    _ReportData,
    build_section_context,
)
from saju_engines.context_reducer import first_sentence
from saju_engines.report_plan import build_section_plans
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

_TODAY = date(2026, 7, 6)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:40",
    birth_place_name="서울", gender="male",
)


def _spec(product_code: str, topic: str | None = None) -> ReportSpec:
    return ReportSpec(
        product_code=product_code,
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic=topic,
        period=ReportPeriod(start="2026-01", end="2026-12"),
    )


_BAN_HEADER = "[서두 반복 금지 — 직전 섹션들이 이미 사용한 첫 문장]"
_SAMPLE_OPENING = "경신년 겨울에 태어난 회원님은 금 기운이 강한 사주입니다. 이어지는 본문."


def _second_section_prompt(spec: ReportSpec, data: _ReportData) -> str:
    plan = build_section_plans(spec)[1]
    return build_section_context(plan, spec, data).body_prompt


def test_static_opening_rule_in_every_section() -> None:
    """섹션 과제에 서두 금지 정적 지시가 항상 실린다."""
    spec = _spec("RPT_FULL")
    data = _ReportData(_BIRTH, spec, _TODAY)
    assert "명식 공통 묘사로 시작하지 말 것" in _second_section_prompt(spec, data)


def test_ban_block_absent_without_recorded_openings() -> None:
    """기록이 없으면(dry-run·첫 섹션) 동적 블록 미부착 — 하위호환."""
    spec = _spec("RPT_FULL")
    data = _ReportData(_BIRTH, spec, _TODAY)
    assert _BAN_HEADER not in _second_section_prompt(spec, data)


def test_ban_block_lists_recorded_openings_full() -> None:
    """총운 — 직전 섹션 첫 문장이 기록되면 다음 섹션 프롬프트에 그대로 실린다."""
    spec = _spec("RPT_FULL")
    data = _ReportData(_BIRTH, spec, _TODAY)
    data.record_opening(_SAMPLE_OPENING)
    prompt = _second_section_prompt(spec, data)
    assert _BAN_HEADER in prompt
    assert "- 경신년 겨울에 태어난 회원님은 금 기운이 강한 사주입니다." in prompt
    assert "같은 패턴·유사 표현으로 이 섹션을 시작하지 말 것" in prompt


def test_ban_block_covers_theme_products() -> None:
    """테마사주(집중 RPT_FOCUS·한해 RPT_YEAR)도 같은 경로 — 동적 블록이 동일 부착된다."""
    for code, topic in (("RPT_FOCUS", "career"), ("RPT_YEAR", None)):
        spec = _spec(code, topic)
        data = _ReportData(_BIRTH, spec, _TODAY)
        data.record_opening(_SAMPLE_OPENING)
        prompt = _second_section_prompt(spec, data)
        assert _BAN_HEADER in prompt, f"{code} 동적 블록 누락"
        assert "명식 공통 묘사로 시작하지 말 것" in prompt, f"{code} 정적 지시 누락"


def test_record_opening_keeps_recent_only() -> None:
    """기록은 최근 _MAX_RECENT_OPENINGS개만 유지(프롬프트 비대 방지)."""
    spec = _spec("RPT_FULL")
    data = _ReportData(_BIRTH, spec, _TODAY)
    for i in range(_MAX_RECENT_OPENINGS + 2):
        data.record_opening(f"{i}번째 섹션의 첫 문장이다. 나머지 본문.")
    assert len(data.recent_openings) == _MAX_RECENT_OPENINGS
    assert data.recent_openings[-1].startswith(f"{_MAX_RECENT_OPENINGS + 1}번째")


def test_first_sentence_extraction() -> None:
    """종결어미('다./요./죠.') 기준 첫 문장 추출 — 없으면 첫 줄, 상한 길이 보호."""
    assert first_sentence("첫 문장이다. 둘째 문장이다.") == "첫 문장이다."
    assert first_sentence("차분히 볼 시기예요. 둘째 문장입니다.") == "차분히 볼 시기예요."
    assert first_sentence("종결어미 없는 한 줄\n둘째 줄") == "종결어미 없는 한 줄"
    assert len(first_sentence("가" * 500 + "다.")) <= 120


def test_chat_scope_directive_bans_common_opening() -> None:
    """채팅 범위 지시 — 첫 문장을 명식 공통 묘사로 열지 말라는 규칙 포함."""
    assert "명식 공통 묘사로 답변을 열지 말 것" in _CHAT_SCOPE_DIRECTIVE
    assert "첫 문장은 이번 질문에 대한 답" in _CHAT_SCOPE_DIRECTIVE


_CHAT_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="07:30",
    birth_place_name="서울", gender="male", reference_date="2026-07-06",
)
_PRIOR_ANSWER = (
    "차분히 흐름을 정리해 볼 시기예요. 이번 달은 문서와 약속이 함께 움직이는 달이라, "
    "서두르기보다 확인이 먼저입니다."
)


def _chat_prompt(question: str, prior: str | None) -> str:
    res = chat_service.chat(_CHAT_BIRTH, question, _TODAY, dry_run=True, prior_answer=prior)
    return res.prompt_preview or ""


def test_thread_prior_opening_ban_injected() -> None:
    """스레드 후속 턴 — 직전 답변의 첫 문장이 서두 반복 금지 지시로 실린다."""
    prompt = _chat_prompt("그럼 다음 달은 어때?", _PRIOR_ANSWER)
    assert "[서두 반복 금지 — 직전 답변의 첫 문장]" in prompt
    assert "차분히 흐름을 정리해 볼 시기예요" in prompt


def test_no_prior_answer_no_thread_ban() -> None:
    """직전 답변이 없으면(첫 턴·단발 질문) 스레드 지시 미부착."""
    prompt = _chat_prompt("이번 달 재물운 어때?", None)
    assert "[서두 반복 금지 — 직전 답변의 첫 문장]" not in prompt
