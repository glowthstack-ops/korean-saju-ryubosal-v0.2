"""대운 강의 대조 반영 고정 (2026-10-29 데굴님 결정 — "모두 제안대로").

P0 결함 교정: '지금 대운'(too_broad 반려)·'언제 대운이 들어오나요'·'제 인생에 좋은 대운'(월 단위
시기 탐색으로 빠짐) 라우팅, 리포트 십년 풀이 페이지 대운 역할 라벨. P1 서술: '대운=좋은 운' 오해
교정(대운 시기 질문에만)·대운 받을 준비(재성 대운 × 원국 식상만)·맞는 대운도 노력·
맞지 않는 대운 대비.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services import chat_service
from saju_api.services.manse_service import calculate
from saju_engines.structural_context import DAEWOON_FRAMING_DIRECTIVE, DAEWOON_WHEN_DIRECTIVE
from saju_engines.time_parser import is_daewoon_when_question, parse_time
from saju_engines.wealth_lecture import daewoon_readiness_lines
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import TimeScope

_T = date(2026, 10, 29)


@pytest.mark.parametrize(("q", "scope", "life", "when"), [
    ("지금 대운은 어때요?", TimeScope.DAEWOON_UNIT, None, False),
    ("요즘 대운 어때", TimeScope.DAEWOON_UNIT, None, False),
    ("이번 대운은 어때요?", TimeScope.DAEWOON_UNIT, None, False),
    ("다음 대운은 언제 들어와요?", TimeScope.DAEWOON_UNIT, None, False),
    ("대운이 언제 바뀌어요?", TimeScope.DAEWOON_UNIT, None, False),
    ("선생님 저는 언제쯤 대운이 들어오나요?", TimeScope.LIFE_STAGE, "평생", True),
    ("제 인생에 좋은 대운은 언제 와요?", TimeScope.LIFE_STAGE, "평생", True),
    ("좋은 대운 언제 와?", TimeScope.LIFE_STAGE, "평생", True),
])
def test_daewoon_question_routing(q: str, scope: TimeScope, life: str | None, when: bool) -> None:
    tr, sc = parse_time(q, _T, birth_year=1973)
    assert sc is scope and tr is not None and tr.life_stage == life
    assert is_daewoon_when_question(q) is when


def test_non_daewoon_questions_unchanged() -> None:
    assert parse_time("대운이 뭐예요?", _T)[1] is TimeScope.TIMELESS
    assert parse_time("올해 운세 어때?", _T)[1] is TimeScope.MID_TERM


@pytest.mark.parametrize(("q", "scope", "start", "end"), [
    # 2026-10-30 점검: 대운 낱말이 섞여도 명시 시점이 창이다(C14/C14b 가 C5·C6·C12 보다 뒤).
    ("지금 대운이 안 좋은 거 같은데 내년엔 괜찮아질까요?", TimeScope.MID_TERM, "2027", "2027"),
    ("요즘 대운이 바뀐 것 같은데 올해 이직 될까요?", TimeScope.MID_TERM, "2026", "2026"),
    ("2028년에 좋은 대운이 오나요?", TimeScope.MID_TERM, "2028", "2028"),
    ("내년에 대운 들어오나요?", TimeScope.MID_TERM, "2027", "2027"),
    ("좋은 대운은 지나갔고 올해는 어때요?", TimeScope.MID_TERM, "2026", "2026"),
    ("2030년 3월에 대운이 바뀌나요?", TimeScope.SHORT_TERM, "2030-03", "2030-03"),
    ("40대에 대운이 바뀌나요?", TimeScope.LIFE_STAGE, "2013", "2022"),
])
def test_explicit_time_beats_daewoon_regexes(
    q: str, scope: TimeScope, start: str, end: str,
) -> None:
    tr, sc = parse_time(q, _T, birth_year=1973)
    assert sc is scope and tr is not None and (tr.start, tr.end) == (start, end), (q, sc, tr)


def test_prefixed_daewoon_word_is_not_when_question() -> None:
    """'역마대운이 들어오는 시기'의 '대운'은 낱말 '대운'이 아니다 — 오해 교정 지시 금지."""
    q = "역마대운이 들어오는 시기에 해외 갈까요?"
    assert is_daewoon_when_question(q) is False
    assert parse_time(q, _T, birth_year=1973)[1] is TimeScope.TIMELESS


def test_lifetime_regex_covers_my_life_phrases() -> None:
    for q in ("제 인생에 좋은 대운은 언제 와요?", "저의 인생에서 큰 변화", "내 인생 전체"):
        assert chat_service._LIFETIME_RE.search(q), q


def test_when_directive_and_framing_sentences() -> None:
    d = DAEWOON_WHEN_DIRECTIVE
    assert "좋은 운이라는 뜻이 아니라 10년마다" in d and "대운수" in d
    assert "가르치듯 쓰지 말고" in d and "대운 역할 라벨" in d
    f = DAEWOON_FRAMING_DIRECTIVE
    assert "내 것으로 만들려는 노력" in f and "미리 대비하면" in f
    assert "상대적으로 드러나기 쉽다" in f  # 기존 고정 문구 보존


def _chart(d: str):
    return calculate(BirthInput(
        birth_date=date.fromisoformat(d), birth_time="10:00:00", birth_place_name="서울",
        gender="male",
    ))


def test_readiness_lines_follow_natal_output() -> None:
    ready = daewoon_readiness_lines(_chart("1970-01-12"), 2032, 2041)
    assert ready and "받을 준비가 된 대운" in ready[1] and "庚午" in ready[1]
    no_spoon = daewoon_readiness_lines(_chart("1975-01-12"), 2024, 2032)
    assert no_spoon and "숟가락(식상)이 약해" in no_spoon[1]
    # 창에 걸리는 대운이 없으면 블록 없음(대운표 밖 연도).
    assert daewoon_readiness_lines(_chart("1970-01-12"), 2300, 2301) == []


def test_chat_when_question_carries_directive_and_lifetime_scan() -> None:
    b = BirthInput(
        calendar_type="solar", birth_date="1973-01-12", birth_time="10:00",
        birth_place_name="서울", gender="male", reference_date="2026-10-29",
    )
    q = "선생님 저는 언제쯤 대운이 들어오나요?"
    p = chat_service.chat(b, q, _T, dry_run=True).prompt_preview
    assert p and "[대운 시기 질문 — '대운=좋은 운' 오해 교정]" in p
    assert "대운 흐름(배경)" in p
    unit = chat_service.chat(b, "지금 대운은 어때요?", _T, dry_run=True)
    assert unit.status != "too_broad"
    assert "[대운 시기 질문" not in (unit.prompt_preview or "")
