"""OA-11d S1 (shadow) — CLEAN short-circuit 우회는 **한 분기**여야 한다.

S1 은 신규 선택 알고리즘이 아니다. 기존 diversity 경로에 진입할 기회를 여는 것뿐이며,
조건을 못 채우면 C10 과 바이트 단위로 같아야 한다.

진입 조건은 과거 이력과 현재 후보만 본다 — board 이후 실현 여부는 정책 입력이 아니라
사후 평가값이다.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from saju_engines.daily_canonical_bootstrap import C10_POLICY
from saju_engines.daily_selection_policy_shadow import (
    RAW_GOOD_WINNER_SELECTED,
    ProjectionStatus,
    Top1FamilyProjection,
    select_good_representative,
)

_S1_POLICY = replace(C10_POLICY, family_deficit_clean_bypass=True)
#: 원시 1위가 반복이 아니고(CLEAN) 예산 안에 대안이 있는 후보 집합.
_GOODS = [("money_small", 70), ("rest_recharge", 66), ("tidy_luck", 64)]
_FAMILY = {
    "money_small": "small_gain", "rest_recharge": "rest", "tidy_luck": "tidying",
    "walk_refresh": "walk",
}


def _projection(family: str | None, *, event_key: str = "money_small",
                status: ProjectionStatus = ProjectionStatus.PROJECTED):
    """원시 1위(`money_small`)에 결박된 projection."""
    if family is None:
        return None
    return Top1FamilyProjection(
        event_key=event_key, family=family, status=status
    )


def _call(policy, *, headline_history, projected, history=(), **over):
    return select_good_representative(
        _GOODS, list(history), 7, policy=policy, family_of=_FAMILY,
        headline_history=list(headline_history),
        top1_projection=_projection(projected, **over),
    )


def _deficit_history() -> list[str]:
    """family 3종만 반복 — coverage 가 floor(16) 아래다."""
    return ["money_small", "rest_recharge", "tidy_luck"] * 20


def _rich_history() -> list[str]:
    """coverage 를 floor 이상으로 채운다."""
    return [f"e{i}" for i in range(20)] * 3


@pytest.fixture(autouse=True)
def _rich_family_map():
    for i in range(20):
        _FAMILY[f"e{i}"] = f"F{i}"


# ── C10 과 동일해야 하는 경우 ─────────────────────────────────────────────


def test_c10_returns_raw_top_on_clean() -> None:
    rep = _call(C10_POLICY, headline_history=_deficit_history(), projected="walk")
    assert rep.good_selection_reason == RAW_GOOD_WINNER_SELECTED
    assert rep.display_good_representative == "money_small"


def test_s1_matches_c10_when_no_family_deficit() -> None:
    """coverage 충족이면 우회하지 않는다."""
    rich = _rich_history()
    assert _call(_S1_POLICY, headline_history=rich, projected="walk") == (
        _call(C10_POLICY, headline_history=rich, projected="walk")
    )


def test_s1_matches_c10_when_projected_family_is_not_new() -> None:
    """이미 쓰인 family 를 낼 후보면 열지 않는다."""
    deficit = _deficit_history()
    assert _call(_S1_POLICY, headline_history=deficit, projected="rest") == (
        _call(C10_POLICY, headline_history=deficit, projected="rest")
    )


def test_s1_matches_c10_without_projection_information() -> None:
    """정보 없이 열지 않는다."""
    deficit = _deficit_history()
    assert _call(_S1_POLICY, headline_history=deficit, projected=None) == (
        _call(C10_POLICY, headline_history=deficit, projected=None)
    )


def test_s1_matches_c10_when_raw_top_is_not_clean() -> None:
    """원시 1위가 반복이면 기존 C10 경로 그대로다."""
    deficit = _deficit_history()
    repeated = ["money_small"] * 3
    assert _call(_S1_POLICY, headline_history=deficit, projected="walk",
                 history=repeated) == (
        _call(C10_POLICY, headline_history=deficit, projected="walk",
              history=repeated)
    )


def test_flag_off_is_identical_everywhere() -> None:
    """플래그가 꺼져 있으면 어떤 입력에서도 C10 과 같다."""
    deficit = _deficit_history()
    off = replace(C10_POLICY, family_deficit_clean_bypass=False)
    assert _call(off, headline_history=deficit, projected="walk") == (
        _call(C10_POLICY, headline_history=deficit, projected="walk")
    )


# ── 우회가 열리는 유일한 경우 ─────────────────────────────────────────────


def test_s1_enters_diversity_path_on_family_deficit_with_new_family() -> None:
    """세 조건이 모두 맞을 때만 기존 diversity 경로로 들어간다."""
    rep = _call(_S1_POLICY, headline_history=_deficit_history(), projected="walk")
    assert rep.good_selection_reason != RAW_GOOD_WINNER_SELECTED
    assert rep.raw_good_winner == "money_small"          # 원시 1위 기록은 보존
    assert rep.display_displacement_loss <= 7            # 예산 불변


def test_bypass_does_not_relax_the_loss_budget() -> None:
    """진입만 열고 예산·보호는 그대로다."""
    rep = _call(_S1_POLICY, headline_history=_deficit_history(), projected="walk")
    assert 0 <= rep.display_displacement_loss <= 7


def test_projection_is_an_input_not_a_realization() -> None:
    """정책은 board 이후 결과를 보지 않는다 — projection 만 받는다."""
    import inspect

    sig = inspect.signature(select_good_representative)
    assert "top1_projection" in sig.parameters
    for forbidden in ("realized_final_family", "board_result", "realized_family"):
        assert forbidden not in sig.parameters


# ── projection 은 원시 1위에 결박된다 (fail-closed) ───────────────────────


def test_projection_for_another_event_does_not_open_the_bypass() -> None:
    """다른 후보에서 계산된 projection 이 연결되면 열지 않는다."""
    deficit = _deficit_history()
    assert _call(_S1_POLICY, headline_history=deficit, projected="walk",
                 event_key="rest_recharge") == (
        _call(C10_POLICY, headline_history=deficit, projected="walk")
    )


@pytest.mark.parametrize(
    "status", [ProjectionStatus.UNAVAILABLE, ProjectionStatus.AMBIGUOUS]
)
def test_non_projected_status_does_not_open_the_bypass(status) -> None:
    """계산 실패·단일 family 확정 불가면 열지 않는다."""
    deficit = _deficit_history()
    assert _call(_S1_POLICY, headline_history=deficit, projected="walk",
                 status=status) == (
        _call(C10_POLICY, headline_history=deficit, projected="walk")
    )


def test_empty_projected_family_does_not_open_the_bypass() -> None:
    deficit = _deficit_history()
    assert _call(_S1_POLICY, headline_history=deficit, projected="") == (
        _call(C10_POLICY, headline_history=deficit, projected="")
    )


def test_bypass_requires_the_projection_to_name_the_raw_top() -> None:
    """결박이 실제로 검사되는지 — 같은 사건이면 열린다."""
    rep = _call(_S1_POLICY, headline_history=_deficit_history(),
                projected="walk", event_key="money_small")
    assert rep.raw_good_winner == "money_small"
    assert rep.good_selection_reason != RAW_GOOD_WINNER_SELECTED


def test_projection_status_distinguishes_unavailable_from_ambiguous() -> None:
    """정책 판단은 같게 취급하지만 status 자체는 구분돼 보존돼야 한다.

    `oa11d_trace` 에서 "계산 불가" 와 "복수 family 로 단일 투영 불가" 를 분리해야
    5-anchor 결과에서 병목을 가릴 수 있다.
    """
    assert ProjectionStatus.UNAVAILABLE != ProjectionStatus.AMBIGUOUS
    unavailable = Top1FamilyProjection(
        "money_small", "walk", ProjectionStatus.UNAVAILABLE
    )
    ambiguous = Top1FamilyProjection(
        "money_small", "walk", ProjectionStatus.AMBIGUOUS
    )
    assert unavailable.status.value == "UNAVAILABLE"
    assert ambiguous.status.value == "AMBIGUOUS"
    # 둘 다 우회를 열지 않는다.
    deficit = _deficit_history()
    for projection in (unavailable, ambiguous):
        rep = select_good_representative(
            _GOODS, [], 7, policy=_S1_POLICY, family_of=_FAMILY,
            headline_history=deficit, top1_projection=projection,
        )
        assert rep.good_selection_reason == RAW_GOOD_WINNER_SELECTED
