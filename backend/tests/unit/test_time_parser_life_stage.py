"""C13 인생 단계의 연도 환산 (2026-08-07 데굴님 확정).

근묘화실 4분법의 100세 시대 재조정 경계(초년 0~25 / 청년 26~50 / 중년 51~75 /
말년 76~100, 평생=출생~100세)를 birth_year로 연도 환산해 start/end를 채운다.
기존 결함: '말년에'가 start=None이라 vague_future(올해~+9 창)로 빠져 오답
— C12 나이 표현('88세쯤')과의 비대칭 보완.
"""

from __future__ import annotations

from datetime import date

from saju_engines.time_parser import LIFE_STAGE_AGE_RANGES, parse_time
from saju_shared_types.intent import TimeScope

_TODAY = date(2026, 8, 7)
_BIRTH_YEAR = 1980


def _parse(text: str, birth_year: int | None = _BIRTH_YEAR):
    return parse_time(text, _TODAY, birth_year)


# ── 경계표 자체 ──────────────────────────────────────────────


def test_stage_age_ranges_cover_life() -> None:
    """단계 경계가 0~100세를 빈틈없이 덮고 '평생'은 전체 창이다."""
    assert LIFE_STAGE_AGE_RANGES["초년"] == (0, 25)
    assert LIFE_STAGE_AGE_RANGES["청년"] == (26, 50)
    assert LIFE_STAGE_AGE_RANGES["중년"] == (51, 75)
    assert LIFE_STAGE_AGE_RANGES["말년"] == (76, 100)
    assert LIFE_STAGE_AGE_RANGES["평생"] == (0, 100)


# ── 연도 환산 ────────────────────────────────────────────────


def test_late_life_converted_to_years() -> None:
    tr, scope = _parse("말년에 돈 걱정 없이 살 수 있을까?")
    assert scope is TimeScope.LIFE_STAGE
    assert tr is not None and tr.life_stage == "말년"
    assert (tr.start, tr.end) == ("2056", "2080")


def test_lifetime_converted_to_years() -> None:
    tr, scope = _parse("평생 재물운의 흐름을 알려줘")
    assert scope is TimeScope.LIFE_STAGE
    assert tr is not None and tr.life_stage == "평생"
    assert (tr.start, tr.end) == ("1980", "2080")


def test_nohu_alias_maps_to_late_life() -> None:
    tr, _ = _parse("노후 준비는 어떻게 해야 할까?")
    assert tr is not None and tr.life_stage == "말년"
    assert (tr.start, tr.end) == ("2056", "2080")


def test_early_life_past_window() -> None:
    tr, _ = _parse("초년에 왜 힘들었을까?")
    assert tr is not None and tr.life_stage == "초년"
    assert (tr.start, tr.end) == ("1980", "2005")


# ── 청년 — 단계 문맥 접미가 있을 때만 ─────────────────────────


def test_youth_stage_with_suffix() -> None:
    tr, scope = _parse("청년기에 크게 성공할 수 있을까?")
    assert scope is TimeScope.LIFE_STAGE
    assert tr is not None and tr.life_stage == "청년"
    assert (tr.start, tr.end) == ("2006", "2030")


def test_bare_youth_not_stage() -> None:
    """인구통계 용법('청년 대출')은 단계로 잡지 않는다 — 오탐 차단."""
    tr, scope = _parse("청년 전세대출 받으면 좋을까?")
    assert scope is not TimeScope.LIFE_STAGE or (tr is not None and tr.life_stage is None)


# ── birth_year 미제공 폴백 ───────────────────────────────────


def test_no_birth_year_keeps_stage_without_years() -> None:
    tr, scope = _parse("말년 운세 어때?", birth_year=None)
    assert scope is TimeScope.LIFE_STAGE
    assert tr is not None and tr.life_stage == "말년"
    assert tr.start is None and tr.end is None


# ── 기존 C12 우선순위 보존 ───────────────────────────────────


def test_age_expression_still_wins_over_stage() -> None:
    """'88세쯤'은 C12 나이 창(±1년) — C13 확장이 우선순위를 바꾸지 않는다."""
    tr, scope = _parse("88세쯤 건강 어떨까?")
    assert scope is TimeScope.LIFE_STAGE
    assert tr is not None and tr.life_stage is None
    assert (tr.start, tr.end) == ("2067", "2069")
