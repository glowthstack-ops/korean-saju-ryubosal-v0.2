"""전 생애/인생 단계 스캔 라우팅 (2026-08-07 데굴님 승인).

발동: C13 단계 어휘(파서 life_stage) 또는 전 생애 키워드(_LIFETIME_RE).
데이터: 대운표 sewoon(전 생애 세운) 재사용 + YEAR 레벨 이벤트 채점 → 선별 연도만
digest 표(상한 12·10년 구간당 3). 디렉티브: 대운 배경 위 후보 서술 + 과거/미래
분리 + 백세 안내. 비대상 질문(막연 미래)은 기존 10년 digest 경로 불변.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from saju_api.services import chat_service
from saju_api.services.chat_service import _select_lifetime_years
from saju_shared_types.birth_input import BirthInput

_TODAY = date(2026, 8, 7)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:40",
    birth_place_name="서울", gender="male", reference_date="2026-08-07",
)

_LIFETIME_MARK = "[응답 형식 — 인생 단계 스캔]"
_YEAR_DIGEST_MARK = "올해부터 약 10년의 흐름을"
_CENTENARY_MARK = "백세까지를 기준으로 본다"
_DAEWOON_SPAN_MARK = "대운 흐름(배경)"


def _prompt(q: str) -> str:
    res = chat_service.chat(_BIRTH, q, _TODAY, dry_run=True)
    return res.prompt_preview or ""


# ── 발동 — C13 단계 어휘 경유 ────────────────────────────────


def test_lifetime_question_routes_to_scan() -> None:
    p = _prompt("평생 재물운의 흐름을 알려줘")
    assert _LIFETIME_MARK in p
    assert _CENTENARY_MARK in p
    assert _DAEWOON_SPAN_MARK in p
    assert _YEAR_DIGEST_MARK not in p  # 10년 digest로 새지 않는다
    assert "평생(출생~약 100세, 1980~2080년)" in p


def test_late_life_stage_scan_window() -> None:
    """'말년' — 단계 창(76~100세=2056~2080)이 디렉티브에 나이 병기로 실린다."""
    p = _prompt("말년에 돈 걱정 없이 살 수 있을까?")
    assert _LIFETIME_MARK in p
    assert "말년(76~100세 무렵, 2056~2080년)" in p
    assert _YEAR_DIGEST_MARK not in p


# ── 발동 — 정규식 보강 경로(파서 단계 어휘 없이) ─────────────


def test_regex_trigger_without_stage_vocab() -> None:
    p = _prompt("살면서 결혼운이 가장 강한 시기는 언제야?")
    assert _LIFETIME_MARK in p
    assert "평생(출생~약 100세" in p


# ── 비발동 — 기존 경로 불변 ──────────────────────────────────


def test_vague_future_keeps_year_digest() -> None:
    """막연한 미래 질문은 기존 10년 digest 유지(2026-06-18 결정 보존)."""
    p = _prompt("언제쯤 결혼할 수 있을까?")
    assert _LIFETIME_MARK not in p
    assert _YEAR_DIGEST_MARK in p


def test_explicit_year_not_lifetime() -> None:
    p = _prompt("2027년 이직운 어때?")
    assert _LIFETIME_MARK not in p


# ── 과거/미래 분리 문구 ──────────────────────────────────────


def test_past_recall_guidance_present_for_lifetime() -> None:
    """평생 창은 과거를 포함한다 — 회고·적중 확인 유도 문구가 실린다(확정안 ①)."""
    p = _prompt("평생 재물운의 흐름을 알려줘")
    assert "이미 지난 시기다" in p
    assert "활성화되는 창" in p


# ── 선별 헬퍼 ────────────────────────────────────────────────


@dataclass
class _C:
    period: str
    score: int


def test_select_lifetime_years_caps_and_diversity() -> None:
    """상한 12·10년 구간당 3 — 한 구간 고점이 표를 독점하지 못한다."""
    cands = [_C(str(2030 + i), 90 - i) for i in range(8)]  # 2030년대 8건(고점)
    cands += [_C(str(2050 + i), 50 - i) for i in range(5)]  # 2050년대 5건(저점)
    picked = _select_lifetime_years(cands, 2030, 2080)  # type: ignore[arg-type]
    assert len([y for y in picked if 2030 <= y < 2040]) == 3
    assert len([y for y in picked if 2050 <= y < 2060]) == 3
    assert picked == sorted(picked)
    assert len(picked) <= 12


def test_select_lifetime_years_quality_gate() -> None:
    """후보가 존재하는 연도만 오른다 — 무신호 연도 강제 충원 금지."""
    assert _select_lifetime_years([], 1980, 2080) == []
    picked = _select_lifetime_years([_C("2040", 70)], 1980, 2080)  # type: ignore[arg-type]
    assert picked == [2040]


def test_select_lifetime_years_window_filter() -> None:
    """창 밖 연도·월 후보는 무시한다."""
    cands = [_C("2020", 99), _C("2040-05", 99), _C("2060", 80)]
    picked = _select_lifetime_years(cands, 2030, 2080)  # type: ignore[arg-type]
    assert picked == [2060]
