"""near-tie 대안 분류의 구조적 퇴화 (CAL-ROLE-MARGIN-CENSUS / MC-B, 2026-08-03).

MC-B 는 near-tie 를 세 갈래로 나눌 계획이었다.

    NEAR_TIE_ROLE_MAP_ALTERNATIVE          역할표가 실제로 다름
    NEAR_TIE_PROVENANCE_ONLY_ALTERNATIVE   역할표는 같고 실현 경로만 다름
    NEAR_TIE_SEMANTICALLY_EQUIVALENT       역할표까지 같음

**뒤의 둘은 도달할 수 없다.** `useful` 후보표가 오행을 키로 하는 dict 라서
(`table[el] = (score, model, role)`) 상위 두 후보는 언제나 서로 다른 오행이고, 역할표의
`yongsin` 필드는 확정된 오행 그 자체다. 오행이 다르면 역할표가 다를 수밖에 없다.

실측도 같다 — 13개 명식 전건이 `ROLE_MAP_ALTERNATIVE` 이며 margin 0.80 짜리도 그렇다.
즉 "역할표가 달라지는가" 는 **near-tie 를 가려내는 성질이 아니다.** 이 판별자로 임계값을
정당화하면 아무것도 걸러내지 못하는 조건을 근거처럼 쓰게 된다.

그래서 이 파일은 분류 결과가 아니라 **분류가 성립하지 않는다는 사실**을 고정한다.
대체 판별자는 설계 결정이 필요하다.
"""

from __future__ import annotations

import inspect
from datetime import date
from typing import Any

import pytest
from saju_manse_analysis.yongsin import candidates as cand_mod
from saju_manse_analysis.yongsin.role_realization import resolve_realized_roles

from saju_api.services import manse_service
from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput

#: MC-A 와 같은 모집단(13 independent charts). 성별은 결과를 바꾸지 않아 하나만 쓴다.
_CHARTS: tuple[tuple[int, int, int, str], ...] = (
    (1980, 11, 22, "09:08"), (1980, 11, 22, "09:40"), (1985, 3, 5, "12:00"),
    (1985, 3, 15, "14:30"), (1985, 4, 18, "16:00"), (1985, 5, 5, "14:00"),
    (1987, 8, 5, "21:00"), (1988, 3, 5, "10:30"), (1990, 3, 3, "10:00"),
    (1990, 3, 15, "10:00"), (1990, 5, 5, "13:30"), (1990, 5, 15, "09:30"),
    (1992, 7, 20, "14:00"),
)


def _fresh_capture(birth: BirthInput, patcher: pytest.MonkeyPatch) -> tuple[Any, dict]:
    captured: dict[str, Any] = {}

    def _spy(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return resolve_realized_roles(**kwargs)

    patcher.setattr(cand_mod, "resolve_realized_roles", _spy)
    manse_service._cache.clear()
    analysis = calculate(birth).yongsin_analysis
    manse_service._cache.clear()
    return analysis, captured


@pytest.fixture(scope="module")
def cohort(request) -> list[dict[str, Any]]:
    """13 명식의 primary·alternate 실현 결과. 각 실행은 fresh capture 에서 시작한다."""
    patcher = pytest.MonkeyPatch()
    request.addfinalizer(patcher.undo)

    rows: list[dict[str, Any]] = []
    for year, month, day, hhmm in _CHARTS:
        birth = BirthInput(
            birth_date=date(year, month, day), birth_time=hhmm,
            birth_place_name="서울", gender="male", reference_date=date(2026, 7, 27),
        )
        analysis, captured = _fresh_capture(birth, patcher)
        candidates = analysis.useful_candidates
        primary = resolve_realized_roles(**captured).result

        _, second = _fresh_capture(birth, patcher)
        alternate = resolve_realized_roles(**{
            **second, "selected_yongsin_element": candidates[1].element,
        }).result
        rows.append({
            "chart": f"{year}-{month:02d}-{day:02d} {hhmm}",
            "top1": candidates[0].element, "top2": candidates[1].element,
            "primary": primary, "alternate": alternate,
        })
    return rows


# ── 후보표가 오행 키라는 구조 ────────────────────────────────────────────


def test_useful_table_is_keyed_by_element() -> None:
    """후보표가 오행 dict 라 같은 오행이 두 번 오를 수 없다."""
    source = inspect.getsource(cand_mod.build_yongsin)
    assert "table[el] = (score, model, role)" in source
    assert "useful: dict[str, tuple[float, str, str]] = {}" in source


def test_top_two_candidates_never_share_an_element(cohort) -> None:
    """상위 두 후보의 오행이 겹치는 경우가 없다 — 구조적으로 불가능하다."""
    assert cohort
    for row in cohort:
        assert row["top1"] != row["top2"], row["chart"]


# ── 그래서 역할표 차이는 판별자가 되지 못한다 ────────────────────────────


def test_role_map_yongsin_field_always_follows_the_forced_element(cohort) -> None:
    """역할표의 용신 칸은 확정된 오행 그 자체다."""
    for row in cohort:
        assert row["primary"].final_role_map.yongsin == row["top1"], row["chart"]
        assert row["alternate"].final_role_map.yongsin == row["top2"], row["chart"]


def test_every_runner_up_differs_regardless_of_margin(cohort) -> None:
    """margin 과 무관하게 전건 역할표가 다르다 — 걸러내는 성질이 아니다.

    이 성질로 near-tie 임계값을 정당화하면, 아무것도 배제하지 못하는 조건을 근거처럼
    쓰게 된다. `0.80` 짜리도 통과한다.
    """
    differing = [
        row for row in cohort
        if row["primary"].final_role_map != row["alternate"].final_role_map
    ]
    assert len(differing) == len(cohort)


def test_semantic_equivalence_classes_are_unreachable(cohort) -> None:
    """`SEMANTICALLY_EQUIVALENT`·`PROVENANCE_ONLY` 로 분류되는 사례가 없다."""
    equivalent = [
        row for row in cohort
        if row["primary"].final_role_map == row["alternate"].final_role_map
    ]
    assert equivalent == []


# ── MC-B 가 실제로 남기는 것 — provenance 조합 ───────────────────────────


def test_realization_paths_vary_independently_of_margin(cohort) -> None:
    """실현 경로 조합은 한 가지가 아니다 — 이쪽이 실제 정보다.

    승격/승격 · 폴백/폴백 · 승격/폴백 · 특수분기/승격 이 모두 관측된다. 즉 primary 가
    항상 완비 모델맵인 것도 아니다.
    """
    pairs = {
        (row["primary"].realization_origin, row["alternate"].realization_origin)
        for row in cohort
    }
    assert len(pairs) >= 3

    primary_origins = {row["primary"].realization_origin for row in cohort}
    assert len(primary_origins) >= 2, "primary 도 완비 모델맵만 나오는 것이 아니다"
