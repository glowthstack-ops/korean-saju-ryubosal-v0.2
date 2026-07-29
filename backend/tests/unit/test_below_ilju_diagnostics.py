"""`below_iljus_by_anchor` — 지문에 들어가지 않는 호출부 진단값.

`bottom_6_iljus` 는 상위 6개로 잘린 값이라 `repeatedly_below_iljus` 를 만들 수 없다.
그렇다고 `anchors` payload 에 전체 목록을 넣으면 anchor 지문이 이동한다. 그래서
`anchors` **바깥** 형제 키로 낸다.

정확성은 새 지문이 아니라 두 회귀가 담당한다.

    below_iljus_by_anchor → bottom_6_iljus 일치
    below_iljus_by_anchor → repeatedly_below_iljus 일치
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_ROWS = _BACKEND / "compiled" / "oa10b_characterization_rows.jsonl"
_LEGACY_OUTPUT = (
    _BACKEND.parent / "doc" / "v2_2" / "audits" / "oa10b_rolling_window.json"
)


@pytest.fixture(scope="module")
def result() -> dict:
    if not _ROWS.exists():
        pytest.skip("`python3 scripts/legacy_oa10b_runner.py 1000` 으로 생성한다")
    import saju_engines.daily_ilju_fortune as M
    from saju_engines.daily_rolling_audit_aggregate import (
        build_rolling_audit_aggregates,
    )

    with _ROWS.open(encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    events = M.load_daily_dicts().catalog["events"]
    return build_rolling_audit_aggregates(
        rows,
        {k: v["semantic_family"] for k, v in tax.items()},
        {k: e["domain"] for k, e in events.items()},
    )


def test_dates_match_the_anchor_set(result) -> None:
    below = result["below_iljus_by_anchor"]
    anchors = {a["anchor_date"] for a in result["anchors"]}
    assert len(below) == 730
    assert set(below) == anchors


def test_bottom_six_is_derived_from_the_full_list(result) -> None:
    """잘린 값과 전체 목록이 어긋나면 진단값이 무의미하다."""
    below = result["below_iljus_by_anchor"]
    for anchor in result["anchors"]:
        assert anchor["bottom_6_iljus"] == sorted(below[anchor["anchor_date"]])[:6]
        assert anchor["count_below_15"] == len(below[anchor["anchor_date"]])


def test_repeatedly_below_iljus_matches_the_legacy_output(result) -> None:
    """값뿐 아니라 **순서**까지 기존 OA-10b 출력과 같아야 한다."""
    import collections

    counter: collections.Counter = collections.Counter()
    for iljus in result["below_iljus_by_anchor"].values():
        counter.update(iljus)
    rebuilt = dict(counter.most_common(12))

    legacy = json.loads(_LEGACY_OUTPUT.read_text(encoding="utf-8"))["result"]
    assert rebuilt == legacy["repeatedly_below_iljus"]
    assert list(rebuilt) == list(legacy["repeatedly_below_iljus"])


def test_diagnostic_is_outside_the_fingerprinted_payload(result) -> None:
    """anchors·episodes payload 에 새 키가 새어 들어가면 지문이 움직인다."""
    assert "below_iljus" not in result["anchors"][0]
    assert all("below_iljus" not in e for e in result["episodes"])
    assert "below_iljus_by_anchor" in result


# ── family 축 진단 ────────────────────────────────────────────────────────
#
# legacy 의 `count_below_15` · `qualifying_ilju_count` 는 둘 다 **key** 축이다.
# S1 의 성패는 family 축에서 판정하므로 별도 진단이 필요하다.


def test_family_dates_match_the_anchor_set(result) -> None:
    below = result["family_below_iljus_by_anchor"]
    counts = result["family_qualifying_count_by_anchor"]
    anchors = {a["anchor_date"] for a in result["anchors"]}
    assert len(below) == len(counts) == 730
    assert set(below) == set(counts) == anchors


def test_family_counts_sum_to_the_board_size(result) -> None:
    below = result["family_below_iljus_by_anchor"]
    counts = result["family_qualifying_count_by_anchor"]
    for iso, iljus in below.items():
        assert len(iljus) + counts[iso] == 60
        assert len(set(iljus)) == len(iljus)          # 중복 없음


def test_family_p10_and_qualifying_count_are_equivalent(result) -> None:
    """p10 >= 15 ⇔ 미달 <= 5 ⇔ 자격 >= 55. 세 표현이 동시에 성립해야 한다."""
    below = result["family_below_iljus_by_anchor"]
    counts = result["family_qualifying_count_by_anchor"]
    for anchor in result["anchors"]:
        iso = anchor["anchor_date"]
        passes = anchor["family_p10"] >= 15
        assert passes == (len(below[iso]) <= 5), iso
        assert passes == (counts[iso] >= 55), iso
        if not passes:
            assert len(below[iso]) >= 6 and counts[iso] <= 54, iso


def test_family_axis_differs_from_the_key_axis(result) -> None:
    """두 축이 실제로 다르다 — 같다면 진단을 추가할 이유가 없었다."""
    key_below = result["below_iljus_by_anchor"]
    fam_below = result["family_below_iljus_by_anchor"]
    assert any(key_below[iso] != fam_below[iso] for iso in key_below)


def test_family_below_keeps_board_order(result) -> None:
    """새로 정렬하지 않는다 — 공식 60갑자 board 순서를 유지한다."""
    from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

    order = [
        f"{ganzi_from_index(i)[0].value}{ganzi_from_index(i)[1].value}"
        for i in range(60)
    ]
    index = {ilju: n for n, ilju in enumerate(order)}
    for iljus in result["family_below_iljus_by_anchor"].values():
        positions = [index[i] for i in iljus]
        assert positions == sorted(positions)


def test_family_diagnostics_are_outside_the_fingerprinted_payload(result) -> None:
    for hidden in ("family_below_iljus", "family_qualifying_count"):
        assert all(hidden not in row for row in result["anchors"])
    assert "family_below_iljus_by_anchor" in result
    assert "family_qualifying_count_by_anchor" in result
