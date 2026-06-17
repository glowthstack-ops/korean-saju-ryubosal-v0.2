"""Phase R4 — 집 이사(일지 중심) vs 사무실 이전(월주 중심) 분리.

relocation_kind는 선택 입력이며 기본 home으로 기존 동작을 보존한다(원칙 11). 사무실(office)은
월주 중심 officeMove 규격(정재·정관 우대 / 상관·겁재·편관·월지충·월간극 회피)을 일운 적합에
적용한다(사용자 스펙 11·12장). 점수는 코드가 계산한다(절대원칙 1).
"""

from __future__ import annotations

from pathlib import Path

from saju_engines.relocation import (
    RelocationResolver,
    load_date_selection_table,
    office_day_fit,
    stem_relations,
)
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.precompute import (
    CompositeGanji,
    CompositeLevel,
    InteractionHit,
    InteractionKind,
    InteractionParticipant,
    InteractionSource,
    LuckComposite,
    TenGodPair,
)
from saju_shared_types.relocation import RelocationPeriod, RelocationQuery

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_OFFICE = load_date_selection_table(_DICTS)["officeMove"]
_SELF = SubjectRef(kind=SubjectKind.SELF, label="본인")


def _day(stem_tg: str, branch_tg: str, interactions=None) -> LuckComposite:
    return LuckComposite(
        subject_id="본인", level=CompositeLevel.DAY, period_key="2026-06-10",
        ganji=CompositeGanji(stem="甲", branch="寅"),
        ten_god=TenGodPair(stem=stem_tg, branch_main=branch_tg),
        twelve_stage="건록", favorability="한신",
        interactions=interactions or [],
        dict_version="1.0.0", computed_at="2026-06-17T00:00:00+00:00",
    )


def _stem_combine_month() -> InteractionHit:
    return InteractionHit(
        relation_id="rel_test_stem_combine", kind=InteractionKind.STEM_COMBINE,
        participants=[
            InteractionParticipant(source=InteractionSource.DAY, ganji="甲"),
            InteractionParticipant(source=InteractionSource.NATAL_MONTH, ganji="己"),
        ],
    )


def _branch_clash_month() -> InteractionHit:
    return InteractionHit(
        relation_id="rel_test_branch_clash", kind=InteractionKind.BRANCH_CLASH,
        participants=[
            InteractionParticipant(source=InteractionSource.DAY, ganji="寅"),
            InteractionParticipant(source=InteractionSource.NATAL_MONTH, ganji="申"),
        ],
    )


# ── stem_relations / office_day_fit 단위 ─────────────────────────


def test_stem_relations_detects_month_stem_combine() -> None:
    """일운 천간이 월간과 합하면 '월간합'으로 판정."""
    assert "월간합" in stem_relations(_day("정관", "정재", [_stem_combine_month()]))


def test_office_prefers_jeonggwan_over_sanggwan() -> None:
    """사무실: 정관·정재 우대 > 상관·겁재 회피."""
    good = office_day_fit(_day("정관", "정재"), _OFFICE)
    bad = office_day_fit(_day("상관", "겁재"), _OFFICE)
    assert good > bad


def test_office_penalizes_month_branch_clash() -> None:
    """사무실: 월지충이 있으면 같은 십성이라도 점수가 낮아진다(월주 중심 회피)."""
    clean = office_day_fit(_day("정관", "정재"), _OFFICE)
    clashed = office_day_fit(_day("정관", "정재", [_branch_clash_month()]), _OFFICE)
    assert clashed < clean


def test_office_rewards_month_stem_combine() -> None:
    """사무실: 월간합은 가점된다."""
    base = office_day_fit(_day("정관", "정재"), _OFFICE)
    combined = office_day_fit(_day("정관", "정재", [_stem_combine_month()]), _OFFICE)
    assert combined > base


# ── M10 resolver: home vs office 분리 + 기본값 보존 ───────────────


def test_relocation_kind_defaults_to_home() -> None:
    """relocation_kind 미지정 시 기본 home(선택 입력 — 원칙 11)."""
    q = RelocationQuery(
        group_subjects=[_SELF],
        period=RelocationPeriod(start="2026-01", end="2026-12"),
        current_location="서울",
    )
    assert q.relocation_kind == "home"


def test_resolver_day_fit_routes_by_kind() -> None:
    """_day_fit: office는 officeMove, home은 이삿날 점수표를 쓴다(점수 상이)."""
    resolver = RelocationResolver(_DICTS)
    # 정관/상관 — officeMove(상관 회피)와 이삿날(상관 −30) 모두 낮지만 산출 경로가 다르다.
    c = _day("정재", "정관")
    home_fit = resolver._day_fit(c, "home")
    office_fit = resolver._day_fit(c, "office")
    assert isinstance(home_fit, int) and isinstance(office_fit, int)
    assert 0 <= home_fit <= 100 and 0 <= office_fit <= 100
    # 동일 입력이라도 점수표가 달라 일반적으로 값이 갈린다.
    assert home_fit != office_fit
