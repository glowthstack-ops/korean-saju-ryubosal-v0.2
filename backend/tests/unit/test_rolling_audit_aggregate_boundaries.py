"""OA-10b 집계 의미의 경계 계약 — 이번에 복제한 legacy 의미를 봉인한다.

730 anchor 전수 parity 는 실제 데이터에 나타난 경우만 덮는다. 동률·1일 episode·
구간 첫날/마지막날 종료 같은 경계는 데이터에 없을 수 있으므로 따로 고정한다.

기대값은 production helper 로 계산하지 않고 **상수로 직접 적는다** — helper 로
만들면 자기검증이 된다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import replace

import pytest

from saju_engines.daily_rolling_audit_aggregate import (
    P10_INDEX,
    P10_SAMPLE_SIZE,
    ROLLING_AUDIT_AGGREGATE_CONTRACT_V1,
    RollingAuditInputError,
    _p10,
    build_failure_episodes,
    build_rolling_audit_aggregates,
)

_C = ROLLING_AUDIT_AGGREGATE_CONTRACT_V1


# ── p10 ───────────────────────────────────────────────────────────────────


def test_p10_index_is_a_declared_constant() -> None:
    """라이브러리 percentile 로 대체되지 않도록 정의 자체를 고정한다."""
    assert (P10_SAMPLE_SIZE, P10_INDEX) == (60, 5)
    assert _C.board_size == 60
    assert _C.p10_index == 5


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        # index 5 가 14 — 앞 6개가 14 이하다.
        ([13, 14, 14, 14, 14, 14] + [20] * 54, 14),
        # index 5 가 15 — 6번째로 작은 값이 15 다.
        ([13, 14, 14, 14, 15, 15] + [20] * 54, 15),
        # 경계 index 전후가 14/15 로 갈린다.
        ([10, 11, 12, 13, 14, 15, 16] + [20] * 53, 15),
        ([10, 11, 12, 13, 14, 14, 15] + [20] * 53, 14),
        # 경계 주변 동률이 많아도 index 는 그대로다.
        ([14] * 6 + [15] * 54, 14),
        ([14] * 5 + [15] * 55, 15),
    ],
)
def test_p10_literal_cases(values: list[int], expected: int) -> None:
    assert len(values) == 60
    assert _p10(values, _C) == expected


def test_p10_ignores_input_order() -> None:
    values = [14] * 6 + [15] * 54
    assert _p10(list(reversed(values)), _C) == 14
    assert _p10(values[30:] + values[:30], _C) == 14


@pytest.mark.parametrize("size", [0, 59, 61])
def test_p10_rejects_wrong_sample_size(size: int) -> None:
    with pytest.raises(RollingAuditInputError):
        _p10([15] * size, _C)


# ── 작은 계약으로 실제 집계 경로를 돈다 ───────────────────────────────────
#
# board_size 를 줄인 계약을 써서 bottom·pass 의미를 실제 코드 경로로 검사한다.

# 프로덕션 계약은 board 60 · threshold 15 이며 **비율이 아니라 고정 count** 다.
# 축소 fixture 도 임계값을 비율로 환산하지 않고 명시적으로 주입한다 — builder 가
# 15/60 을 암묵 계산하는 것처럼 보이면 안 된다.
_SMALL = replace(
    ROLLING_AUDIT_AGGREGATE_CONTRACT_V1,
    version="test-reduced-board",
    board_size=4,
    p10_index=1,                 # 4개 중 2번째로 작은 값
    pass_threshold=2,            # 명시 주입 — 60→4 비율 환산이 아니다
    bottom_ilju_threshold=2,     # 〃
    bottom_ilju_limit=2,
    window_days=2,
    warmup_days=0,
    anchor_days=1,
    first_anchor=dt.date(2026, 1, 1),
    recovery_target=99,          # 만료 위험 경로를 이 fixture 에서 끈다
)


def test_reduced_fixture_declares_its_own_thresholds() -> None:
    """축소 fixture 가 프로덕션 계약을 상속한 것처럼 읽히면 안 된다."""
    assert (_C.board_size, _C.pass_threshold) == (60, 15)
    assert (_SMALL.board_size, _SMALL.pass_threshold) == (4, 2)
    # 비율 환산이었다면 15/60 * 4 = 1 이 됐을 것이다.
    assert _SMALL.pass_threshold != round(_C.pass_threshold * 4 / _C.board_size)


def _rows(series: dict[str, list[str]]) -> list[dict]:
    import datetime as dt

    out = []
    days = len(next(iter(series.values())))
    for d in range(days):
        day = (_SMALL.first_anchor - dt.timedelta(days=2) + dt.timedelta(days=d))
        for ilju, seq in series.items():
            out.append({
                "fortune_date": day.isoformat(), "ilju": ilju,
                "final_headline": seq[d],
            })
    return out


def _run(series, family_of, domain_of):
    return build_rolling_audit_aggregates(
        _rows(series), family_of, domain_of, _SMALL
    )


def test_bottom_iljus_use_the_key_axis_not_family() -> None:
    """family 만 낮은 일주는 bottom 에 들어가지 않는다."""
    # a: key 1 (반복) → bottom. b: key 2 이지만 두 사건이 같은 family → family 1.
    series = {
        "a": ["e1", "e1", "e1"], "b": ["e1", "e2", "e2"],
        "c": ["e1", "e2", "e3"], "d": ["e2", "e3", "e1"],
    }
    family_of = {"e1": "F", "e2": "F", "e3": "G"}
    domain_of = {"e1": "money", "e2": "work", "e3": "rest"}
    anchor = _run(series, family_of, domain_of)["anchors"][0]
    assert anchor["bottom_6_iljus"] == ["a"]        # b 는 key 2 라 제외
    assert anchor["family_min"] == 1                # b 의 family 는 1


def test_bottom_iljus_are_capped_and_legacy_sorted() -> None:
    """대상이 한도를 넘으면 legacy 정렬 후 앞에서 자른다."""
    series = {k: ["e1", "e1", "e1"] for k in ("d", "b", "a", "c")}
    family_of = {"e1": "F"}
    domain_of = {"e1": "money"}
    anchor = _run(series, family_of, domain_of)["anchors"][0]
    assert anchor["count_below_15"] == 4            # 대상은 4개지만
    assert anchor["bottom_6_iljus"] == ["a", "b"]   # 정렬 후 앞 2개


@pytest.mark.parametrize(
    ("key_cov", "fam_cov", "expected"),
    [(2, 2, True), (1, 2, False), (2, 1, False), (1, 1, False)],
)
def test_combined_gate_with_explicit_reduced_fixture_threshold(
    key_cov, fam_cov, expected
) -> None:
    """domain 은 게이트가 아니다 — 아무리 높아도 판정을 바꾸지 못한다."""
    # p10_index=1 이므로 4개 중 2번째로 작은 값이 p10 이다. 전부 같은 값으로 둔다.
    seq = ["e1", "e2"] if key_cov == 2 else ["e1", "e1"]
    family_of = {"e1": "F", "e2": "F" if fam_cov == 1 else "G"}
    domain_of = {"e1": "money", "e2": "work"}
    series = {k: [*seq, seq[-1]] for k in ("a", "b", "c", "d")}
    anchor = _run(series, family_of, domain_of)["anchors"][0]
    assert anchor["passes"] is expected
    assert _C.domain_gate_applied is False


# ── episode segmentation ─────────────────────────────────────────────────


def _anchors(spec: list[tuple[str, bool, int, list[str]]]) -> list[dict]:
    """(날짜, passes, key_p10, bottom) 만으로 최소 anchor 를 만든다."""
    return [
        {"anchor_date": d, "passes": p, "key_p10": k, "family_p10": k,
         "count_below_15": len(b), "bottom_6_iljus": b}
        for d, p, k, b in spec
    ]


def test_single_failing_day_is_a_one_day_episode() -> None:
    eps = build_failure_episodes(_anchors([
        ("2026-01-01", True, 15, []),
        ("2026-01-02", False, 14, ["a"]),
        ("2026-01-03", True, 15, []),
    ]), _C)
    assert len(eps) == 1
    assert eps[0]["duration_days"] == 1
    assert eps[0]["episode_id"] == "family-coverage:2026-01-02:2026-01-02"


def test_two_consecutive_days_form_one_episode() -> None:
    eps = build_failure_episodes(_anchors([
        ("2026-01-01", False, 14, ["a"]),
        ("2026-01-02", False, 13, ["b"]),
        ("2026-01-03", True, 15, []),
    ]), _C)
    assert len(eps) == 1
    assert eps[0]["duration_days"] == 2
    assert eps[0]["minimum_key_p10"] == 13


def test_fail_pass_fail_makes_two_episodes() -> None:
    eps = build_failure_episodes(_anchors([
        ("2026-01-01", False, 14, ["a"]),
        ("2026-01-02", True, 15, []),
        ("2026-01-03", False, 14, ["b"]),
    ]), _C)
    assert [e["duration_days"] for e in eps] == [1, 1]
    assert [e["episode_start"] for e in eps] == ["2026-01-01", "2026-01-03"]


def test_episode_starting_at_the_first_anchor() -> None:
    eps = build_failure_episodes(_anchors([
        ("2026-01-01", False, 14, ["a"]),
        ("2026-01-02", True, 15, []),
    ]), _C)
    assert eps[0]["episode_start"] == "2026-01-01"


def test_episode_running_to_the_last_anchor_is_flushed() -> None:
    """마지막 anchor 까지 실패하면 그 날짜에서 닫힌다."""
    eps = build_failure_episodes(_anchors([
        ("2026-01-01", True, 15, []),
        ("2026-01-02", False, 14, ["a"]),
        ("2026-01-03", False, 14, ["b"]),
    ]), _C)
    assert len(eps) == 1
    assert eps[0]["episode_end"] == "2026-01-03"
    assert eps[0]["duration_days"] == 2


def test_all_minimum_key_dates_are_kept() -> None:
    """최저값 동률 날짜를 전부 보존한다."""
    eps = build_failure_episodes(_anchors([
        ("2026-01-01", False, 13, ["a"]),
        ("2026-01-02", False, 14, ["b"]),
        ("2026-01-03", False, 13, ["c"]),
    ]), _C)
    assert eps[0]["minimum_key_p10_dates"] == ["2026-01-01", "2026-01-03"]


def test_minimum_axis_is_key_not_family() -> None:
    """family 만 최저인 날짜는 episode minimum 날짜가 되지 않는다."""
    anchors = _anchors([
        ("2026-01-01", False, 14, ["a"]),
        ("2026-01-02", False, 13, ["b"]),
    ])
    anchors[0]["family_p10"] = 11        # family 는 첫날이 더 낮지만
    anchors[1]["family_p10"] = 14
    eps = build_failure_episodes(anchors, _C)
    assert eps[0]["minimum_key_p10"] == 13
    assert eps[0]["minimum_key_p10_dates"] == ["2026-01-02"]   # key 축으로 고른다


def test_key_only_and_family_only_failures_join_the_same_episode() -> None:
    """결합 게이트라 실패 이유가 달라도 연속이면 한 episode 다."""
    eps = build_failure_episodes(_anchors([
        ("2026-01-01", False, 14, ["a"]),   # key 실패
        ("2026-01-02", False, 15, ["b"]),   # family 실패(key 는 15)
        ("2026-01-03", False, 14, ["c"]),   # 둘 다 실패
    ]), _C)
    assert len(eps) == 1
    assert eps[0]["duration_days"] == 3


# ── affected_iljus ────────────────────────────────────────────────────────


def test_affected_iljus_are_unique_and_legacy_sorted() -> None:
    eps = build_failure_episodes(_anchors([
        ("2026-01-01", False, 14, ["c", "a"]),
        ("2026-01-02", False, 14, ["a", "b"]),
    ]), _C)
    assert eps[0]["affected_iljus"] == ["a", "b", "c"]


def test_affected_iljus_exclude_other_episodes() -> None:
    eps = build_failure_episodes(_anchors([
        ("2026-01-01", False, 14, ["a"]),
        ("2026-01-02", True, 15, []),
        ("2026-01-03", False, 14, ["z"]),
    ]), _C)
    assert eps[0]["affected_iljus"] == ["a"]
    assert eps[1]["affected_iljus"] == ["z"]


def test_episode_id_prefix_is_a_format_constant_only() -> None:
    """코드가 이 문자열을 보고 의미를 추론해서는 안 된다."""
    assert _C.episode_id_prefix == "family-coverage"
    assert _C.episode_id_prefix_semantics == "LEGACY_LABEL_NOT_AUTHORITATIVE"
    assert _C.episode_minimum_axis == "KEY"
    assert _C.episode_affected_axis == "KEY"
    assert _C.episode_trigger == "COMBINED_KEY_AND_FAMILY_GATE_FAILURE"


# ── 부분 지문의 독립성 ────────────────────────────────────────────────────
#
# episode 지문이 anchor 를 덮으면 episode 가 불변이어도 무관한 anchor 변화로
# 움직여 진단성이 사라진다. 동결 artifact 를 건드리지 않고 복제 payload 로 본다.


def _anchor_fp(payload: dict) -> str:
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(
            {"schema": "oa10b-anchor-aggregate.v1",
             "range": ["2026-01-01", "2027-12-31"], "count": 730,
             "gates": {"target": 15}, "anchors": payload["anchors"]},
            ensure_ascii=False, sort_keys=False, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _episode_fp(payload: dict) -> str:
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(
            {"schema": "oa10b-failure-episode.v1", "episodes": payload["episodes"]},
            ensure_ascii=False, sort_keys=False, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _payload() -> dict:
    return {
        "anchors": [
            {"anchor_date": "2026-01-01", "key_p10": 15, "family_p10": 15},
            {"anchor_date": "2026-01-02", "key_p10": 14, "family_p10": 15},
        ],
        "episodes": [
            {"episode_id": "family-coverage:2026-01-02:2026-01-02",
             "duration_days": 1, "minimum_key_p10": 14},
        ],
    }


def test_changing_episodes_does_not_move_the_anchor_fingerprint() -> None:
    base = _payload()
    changed = _payload()
    changed["episodes"][0]["minimum_key_p10"] = 13
    assert _episode_fp(base) != _episode_fp(changed)
    assert _anchor_fp(base) == _anchor_fp(changed)


def test_changing_anchors_does_not_move_the_episode_fingerprint() -> None:
    base = _payload()
    changed = _payload()
    changed["anchors"][0]["key_p10"] = 16
    assert _anchor_fp(base) != _anchor_fp(changed)
    assert _episode_fp(base) == _episode_fp(changed)
