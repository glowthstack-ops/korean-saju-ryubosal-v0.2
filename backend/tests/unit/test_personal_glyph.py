"""개인 글자 지문 P1 검증 — EMPLOYMENT_HISTORY_CALIBRATION.md §3.

글자 컨텍스트(세운·월운·원국 재현, 1월 라벨 전년 세운), 글자 유사도, 플래그 OFF 점수 불변,
가중 ON 시 글자 일치 우대, 월지 lift 근거 코드(표본·성격 필터), 원장 전용 키 무해를 확인한다.
골든 차트 1980-11-22 09:40 서울(庚申·丁亥·己亥·己巳).
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.glyph_context import GlyphContext
from saju_engines.life_fit_ranker import LifeFitRanker
from saju_engines.personal_calibration import (
    PERSONAL_GLYPH_REPEAT,
    apply_personal_match,
    candidate_fingerprint,
    default_glyph_weight,
    fingerprint_similarity,
    glyph_lift,
    glyph_similarity,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import ConfidenceLevel, EventCandidateV2, Pillar4, TenGod
from saju_shared_types.life_event import (
    LifeEventAttrs,
    LifeEventOutcome,
    LifeEventRow,
    LifeEventSource,
    SignalFingerprint,
)

_BIRTH = BirthInput(
    calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
    birth_place_name="서울", gender="male", reference_date=date(2026, 10, 22),
)


@pytest.fixture(scope="module")
def ctx() -> GlyphContext:
    return GlyphContext.from_result(calculate(_BIRTH))


# ── 글자 컨텍스트 ─────────────────────────────────────────────────────────────
def test_glyph_context_month_year_and_natal_echo(ctx: GlyphContext) -> None:
    g = ctx.glyphs_for("2026-11")
    assert g == {"wolwoon_stem": "己", "wolwoon_branch": "亥",
                 "sewoon_stem": "丙", "sewoon_branch": "午"}
    echo = ctx.natal_echo(g)
    # 亥 = 원국 월지·일지, 己 = 일간·시간 — 복음 재현 자리가 모두 표기된다.
    assert {"wolwoon_branch=month_branch", "wolwoon_branch=day_branch",
            "wolwoon_stem=day_stem", "wolwoon_stem=hour_stem"} <= set(echo)
    assert ctx.glyphs_for("2026") == {"sewoon_stem": "丙", "sewoon_branch": "午"}


def test_glyph_context_january_label_uses_previous_sewoon(ctx: GlyphContext) -> None:
    g = ctx.glyphs_for("2027-01")  # 辛丑월 — 절기년은 2026(丙午)
    assert g["wolwoon_branch"] == "丑" and g["sewoon_stem"] == "丙"
    assert ctx.glyphs_for("1800-05") == {}  # 모르는 연도는 빈 dict(규칙 11)


def test_candidate_fingerprint_with_and_without_context(ctx: GlyphContext) -> None:
    c = EventCandidateV2(event_key="job_gain", period="2026-11", score=40,
                         confidence_level=ConfidenceLevel.EVENT_CANDIDATE,
                         source_ten_gods=[TenGod.ZHENGCAI], palace=Pillar4.DAY)
    plain = candidate_fingerprint(c)
    assert plain.glyphs == {} and plain.natal_echo == []
    rich = candidate_fingerprint(c, ctx)
    assert rich.glyphs["wolwoon_branch"] == "亥" and rich.ten_god_groups == plain.ten_god_groups


# ── 유사도 ───────────────────────────────────────────────────────────────────
def _fp(branch: str, stem: str = "己", echo: list[str] | None = None) -> SignalFingerprint:
    return SignalFingerprint(
        ten_god_groups=["wealth"], glyphs={
            "wolwoon_stem": stem, "wolwoon_branch": branch,
            "sewoon_stem": "丙", "sewoon_branch": "午",
        }, natal_echo=echo or [],
    )


def test_glyph_similarity_positions_and_echo_bonus() -> None:
    assert glyph_similarity(_fp("亥"), _fp("亥")) == 1.0
    assert glyph_similarity(_fp("亥"), _fp("子")) == pytest.approx(0.6)   # 월지만 다름(0.4 빠짐)
    assert glyph_similarity(_fp("亥"), SignalFingerprint()) == 0.0
    both = _fp("亥", echo=["wolwoon_branch=month_branch"])
    assert glyph_similarity(both, both) == 1.0  # 보너스는 상한 1.0 클램프


def test_fingerprint_similarity_unchanged_at_zero_weight_and_prefers_glyph_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from saju_engines import period_v2_config as cfg

    a, same, other = _fp("亥"), _fp("亥"), _fp("子")
    base = fingerprint_similarity(a, other)
    assert fingerprint_similarity(a, other, 0.0) == base == 0.4  # 기존 식(Jaccard 1.0×0.4)
    assert fingerprint_similarity(a, same, 0.35) > fingerprint_similarity(a, other, 0.35)
    # 플래그 OFF 면 0, ON 이면 사전값(.env.beta 와 무관하게 코드 기준으로 검증).
    monkeypatch.setattr(cfg, "PERSONAL_GLYPH_SCORE_ENABLED", False)
    assert default_glyph_weight() == 0.0
    monkeypatch.setattr(cfg, "PERSONAL_GLYPH_SCORE_ENABLED", True)
    assert default_glyph_weight() == 0.35


# ── lift·근거 코드·플래그 OFF 점수 불변 ──────────────────────────────────────
def _row(period: str, branch: str, nature: str | None = "regular",
         key: str = "job_gain") -> LifeEventRow:
    return LifeEventRow(
        event_row_id=f"s:eh:{period}:{key}", subject_id="s", pillar_year="庚申",
        pillar_month="丁亥", pillar_day="己亥", event_key=key, period=period,
        signal_fingerprint=_fp(branch), outcome=LifeEventOutcome.CONFIRMED,
        source=LifeEventSource.EMPLOYMENT_HISTORY, attrs=LifeEventAttrs(nature=nature),
    )


def _cand(period: str) -> EventCandidateV2:
    return EventCandidateV2(event_key="job_gain", period=period, score=40,
                            confidence_level=ConfidenceLevel.EVENT_CANDIDATE,
                            source_ten_gods=[TenGod.ZHENGCAI])


def test_glyph_lift_requires_min_rows_and_filters_nature(ctx: GlyphContext) -> None:
    rows = [_row("2004-11", "亥"), _row("2021-11", "亥"), _row("2022-11", "亥"),
            _row("2025-11", "亥"), _row("2018-03", "卯"), _row("2020-01", "丑")]
    cfp = ctx.with_glyphs(SignalFingerprint(), "2026-11")  # 亥월 후보
    lift, hits, n = glyph_lift(cfp, rows)
    assert (hits, n) == (4, 6) and lift == pytest.approx((4 / 6) / (1 / 12), rel=1e-3)
    assert glyph_lift(cfp, rows[:4]) is None  # 표본 5건 미만
    assert glyph_lift(SignalFingerprint(), rows) is None  # 후보에 글자 없음

    sig = [*rows, _row("2001-08", "亥", nature="military"),
           _row("2015-02", "亥", key="resignation")]
    ranked = apply_personal_match([_cand("2026-11"), _cand("2026-12")], sig, ctx, 0.0)
    nov = next(c for c in ranked if c.period == "2026-11")
    dec = next(c for c in ranked if c.period == "2026-12")
    assert any(c.startswith(PERSONAL_GLYPH_REPEAT + ":亥:4/6") for c in nov.reason_codes)
    assert not any(c.startswith(PERSONAL_GLYPH_REPEAT) for c in dec.reason_codes)  # 子월 0건
    # 글자 가중 0 → 점수·personal_match 는 글자 없이 계산한 값과 같다(플래그 OFF 불변).
    plain = apply_personal_match([_cand("2026-11"), _cand("2026-12")], sig)
    assert [(c.score, c.personal_match) for c in ranked] == [
        (c.score, c.personal_match) for c in plain
    ]


def test_glyph_weight_on_prefers_repeated_branch(ctx: GlyphContext) -> None:
    sig = [_row("2004-11", "亥"), _row("2021-11", "亥"), _row("2022-11", "亥"),
           _row("2025-11", "亥"), _row("2018-03", "卯")]
    ranked = LifeFitRanker().rank(
        [_cand("2026-11"), _cand("2026-12")], signature=sig, glyph_context=ctx, glyph_weight=0.35,
    )
    nov = next(c for c in ranked if c.period == "2026-11")
    dec = next(c for c in ranked if c.period == "2026-12")
    assert nov.personal_match > dec.personal_match
    assert ranked[0].period == "2026-11"


def test_ledger_only_key_rows_are_harmless_in_ranker(ctx: GlyphContext) -> None:
    sig = [_row("2015-02", "寅", key="resignation"), _row("2022-11", "亥", key="resignation")]
    ranked = LifeFitRanker().rank([_cand("2026-11")], signature=sig, glyph_context=ctx)
    assert [str(c.event_key) for c in ranked] == ["job_gain"]  # resignation 시드 없음
