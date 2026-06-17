"""Phase R3 — 계약일/이삿날 분리 택일 정밀화 (date_selection_ten_gods.json 결합).

계약일=정관·정인(서류) / 이삿날=정재·정관(실행)이 일운 실행 점수에 실제 반영되는지,
충이 택일에서 감점되는지, 천간/지지 가중 차이로 같은 날도 목적별 점수가 갈리는지를
합성 LuckComposite로 결정론 검증한다. 점수 계산은 코드가 한다(절대원칙 1).
"""

from __future__ import annotations

from pathlib import Path

from saju_engines.relocation import (
    branch_relations,
    load_date_selection_table,
    ten_god_day_fit,
)
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

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_TABLE = load_date_selection_table(_DICTS)


def _day(
    stem_tg: str,
    branch_tg: str,
    *,
    stem: str = "甲",
    branch: str = "寅",
    interactions: list[InteractionHit] | None = None,
) -> LuckComposite:
    """십성·상호작용을 통제한 합성 일운 LuckComposite."""
    return LuckComposite(
        subject_id="본인",
        level=CompositeLevel.DAY,
        period_key="2026-06-10",
        ganji=CompositeGanji(stem=stem, branch=branch),
        ten_god=TenGodPair(stem=stem_tg, branch_main=branch_tg),
        twelve_stage="건록",
        favorability="한신",
        interactions=interactions or [],
        dict_version="1.0.0",
        computed_at="2026-06-17T00:00:00+00:00",
    )


def _clash(source: InteractionSource) -> InteractionHit:
    """원국 자리(일지/월지)와의 충 1건."""
    return InteractionHit(
        relation_id="rel_test_clash",
        kind=InteractionKind.BRANCH_CLASH,
        participants=[
            InteractionParticipant(source=InteractionSource.DAY, ganji="寅"),
            InteractionParticipant(source=source, ganji="申"),
        ],
    )


def _combine(source: InteractionSource) -> InteractionHit:
    """원국 자리와의 육합 1건."""
    return InteractionHit(
        relation_id="rel_test_combine",
        kind=InteractionKind.BRANCH_SIX_COMBINE,
        participants=[
            InteractionParticipant(source=InteractionSource.DAY, ganji="寅"),
            InteractionParticipant(source=source, ganji="亥"),
        ],
    )


# ── branch_relations 판정 ────────────────────────────────────────


def test_branch_relations_detects_day_and_month() -> None:
    """natal_day 충=일지충, natal_month 충=월지충, 합 계열=일지합/월지합."""
    c = _day("정재", "정관", interactions=[
        _clash(InteractionSource.NATAL_DAY),
        _combine(InteractionSource.NATAL_MONTH),
    ])
    assert branch_relations(c) == {"일지충", "월지합"}


def test_branch_relations_ignores_non_natal() -> None:
    """원국 자리(natal_*)가 아닌 운끼리 상호작용은 택일 관계로 보지 않는다."""
    c = _day("정재", "정관", interactions=[_clash(InteractionSource.YEAR)])
    assert branch_relations(c) == set()


# ── 계약일 점수표 ────────────────────────────────────────────────


def test_contract_prefers_jeonggwan_over_pyeonin() -> None:
    """계약일: 정관(+25) 천간일 > 편인(−25) 천간일."""
    contract = _TABLE["contractDay"]
    good = ten_god_day_fit(_day("정관", "정인"), contract)
    bad = ten_god_day_fit(_day("편인", "겁재"), contract)
    assert good > bad


def test_contract_penalizes_clash() -> None:
    """계약일: 일지충이 있으면 같은 십성이라도 점수가 낮아진다(충 회피)."""
    contract = _TABLE["contractDay"]
    clean = ten_god_day_fit(_day("정관", "정인"), contract)
    clashed = ten_god_day_fit(
        _day("정관", "정인", interactions=[_clash(InteractionSource.NATAL_DAY)]),
        contract,
    )
    assert clashed < clean


# ── 이삿날 점수표 ────────────────────────────────────────────────


def test_move_prefers_jeongjae_over_sanggwan() -> None:
    """이삿날: 정재(+30) > 상관(−30)."""
    move = _TABLE["moveDay"]
    good = ten_god_day_fit(_day("정재", "정관"), move)
    bad = ten_god_day_fit(_day("상관", "겁재"), move)
    assert good > bad


def test_move_day_branch_relation_weight_dominant() -> None:
    """이삿날: 일지합(+20)이 점수를 올리고 일지충(−20)이 내린다(지지 관계 비중 우세)."""
    move = _TABLE["moveDay"]
    base = ten_god_day_fit(_day("정재", "정관"), move)
    with_combine = ten_god_day_fit(
        _day("정재", "정관", interactions=[_combine(InteractionSource.NATAL_DAY)]), move,
    )
    with_clash = ten_god_day_fit(
        _day("정재", "정관", interactions=[_clash(InteractionSource.NATAL_DAY)]), move,
    )
    assert with_combine >= base > with_clash


def test_contract_and_move_differ_for_same_day() -> None:
    """같은 날(정인 천간)도 계약일은 우대(+20), 이삿날은 감점(−5)이라 점수가 갈린다."""
    c = _day("정인", "정인")
    assert ten_god_day_fit(c, _TABLE["contractDay"]) > ten_god_day_fit(c, _TABLE["moveDay"])


def test_move_jaegwan_combination_bonus() -> None:
    """이삿날: 정재(천간)+정관(지지) 재관 조합 보너스가 가산된다."""
    move = _TABLE["moveDay"]
    combo = ten_god_day_fit(_day("정재", "정관"), move)
    single = ten_god_day_fit(_day("정재", "비견"), move)  # 관성 부재 → 조합 미성립
    assert combo > single
