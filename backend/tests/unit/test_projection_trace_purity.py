"""projection trace 의 순수성 — 지금 순수한 것과 앞으로도 순수한 것은 다르다.

연속 917일 결과가 강한 증거이긴 하나, 이 회귀는 향후 `_select_slots` 에 전역 RNG·
증분 counter·in-place 정렬이 추가되는 것을 막는 장치다.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
from dataclasses import replace

import pytest

import saju_engines.daily_ilju_fortune as M
from saju_engines.daily_canonical_bootstrap import C10_POLICY
from saju_engines.daily_schedule_runner import (
    DAILY_BOARD_CONTRACT_V1,
    DAILY_HISTORY_CONTRACT_V1,
    CardCandidateBundle,
    ProjectionStatus,
    advance_daily_schedule,
    derive_top1_family_projection,
    empty_state,
)
from saju_engines.daily_selection_policy_shadow import SelectionPolicy
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
_ILJUS = [
    f"{ganzi_from_index(i)[0].value}{ganzi_from_index(i)[1].value}" for i in range(60)
]
_DAY = dt.date(2026, 1, 1)


@pytest.fixture(scope="module")
def family_of() -> dict[str, str]:
    tax = json.loads(
        (
            __import__("pathlib").Path(__file__).resolve().parents[2]
            / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json"
        ).read_text(encoding="utf-8")
    )["events"]
    return {k: t["semantic_family"] for k, t in tax.items()}


def _advance(family_of, *, trace: bool, policy=C10_POLICY, state=None,
             day: dt.date = _DAY):
    return advance_daily_schedule(
        fortune_date=day, state=state or empty_state(), policy=policy,
        board_policy=_BOARD, board_contract=DAILY_BOARD_CONTRACT_V1,
        history_contract=DAILY_HISTORY_CONTRACT_V1, family_of=family_of,
        iljus=_ILJUS, compute_projection_trace=trace,
    )


@pytest.fixture(scope="module")
def warm(family_of):
    """이력이 쌓인 상태 — 빈 상태에서는 모든 원시 1위가 CLEAN 이라 반사실이 없다.

    반사실 경로(rep != raw top)가 나타나야 §3 회귀가 무언가를 검증한다.
    """
    state = empty_state()
    day = _DAY
    for _ in range(95):
        _step, state = advance_daily_schedule(
            fortune_date=day, state=state, policy=C10_POLICY,
            board_policy=_BOARD, board_contract=DAILY_BOARD_CONTRACT_V1,
            history_contract=DAILY_HISTORY_CONTRACT_V1, family_of=family_of,
            iljus=_ILJUS, compute_projection_trace=False,
        )
        day += dt.timedelta(days=1)
    return state, day


def _record_calls(monkeypatch) -> list[dict]:
    """`_select_slots` 호출 인자를 기록한다(거동은 바꾸지 않는다)."""
    calls: list[dict] = []
    original = M._select_slots

    def spy(scored, seed, *, good_override=None, **kw):
        calls.append({
            "scored_keys": tuple(s.event_key for s in scored),
            "scored_probs": tuple(s.probability for s in scored),
            "seed": seed,
            "good_override": good_override,
            "extra": tuple(sorted(kw)),
        })
        return original(scored, seed, good_override=good_override, **kw)

    monkeypatch.setattr(M, "_select_slots", spy)
    return calls


# ── §3 반사실 입력 차이는 good_override 하나뿐 ────────────────────────────


def test_counterfactual_input_differs_only_by_good_override(
    family_of, warm, monkeypatch
) -> None:
    state, day = warm
    calls = _record_calls(monkeypatch)
    step, _next = _advance(family_of, trace=True, state=state, day=day)

    # 반사실이 발생한 일주만 검사한다(호출이 2회인 일주).
    counterfactual_rows = [
        r for r in step.rows
        if r["oa11d_trace"]["projection_source"] == "COUNTERFACTUAL_RAW_TOP_CARD"
    ]
    assert counterfactual_rows, "반사실 경로가 없으면 이 회귀가 아무것도 검증하지 못한다"

    # 호출을 2개씩 짝지어 본다 — 반사실 호출 바로 뒤에 실제 호출이 온다.
    pairs = 0
    for a, b in zip(calls, calls[1:], strict=False):
        if a["good_override"] == b["good_override"]:
            continue
        if a["scored_keys"] != b["scored_keys"] or a["seed"] != b["seed"]:
            continue
        diff = {k for k in a if a[k] != b[k]}
        assert diff == {"good_override"}, diff
        pairs += 1
    assert pairs >= 1


def test_counterfactual_uses_the_raw_top_as_override(family_of, monkeypatch) -> None:
    _calls = _record_calls(monkeypatch)
    step, _next = _advance(family_of, trace=True)
    for row in step.rows:
        trace = row["oa11d_trace"]
        assert trace["projected_top1_event_key"] == trace["raw_top_event_key"]


# ── §4 부작용 0 ───────────────────────────────────────────────────────────


def _catalog_fp() -> str:
    return hashlib.sha256(
        json.dumps(M.load_daily_dicts().catalog, ensure_ascii=False,
                   sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def test_trace_does_not_mutate_the_dictionary_catalog(family_of) -> None:
    before = _catalog_fp()
    _advance(family_of, trace=True)
    assert _catalog_fp() == before


def test_trace_does_not_disturb_the_global_rng(family_of) -> None:
    """명시 seed 를 쓰더라도 내부에서 전역 RNG 를 쓰기 시작하면 잡아야 한다."""
    random.seed(12345)
    before = random.getstate()
    _advance(family_of, trace=True)
    assert random.getstate() == before


def test_numpy_is_not_used_by_the_selection_path(family_of) -> None:
    """NumPy 를 쓰지 않는다는 사실 자체를 고정한다(의존성을 새로 만들지 않는다)."""
    np = pytest.importorskip("numpy")
    before = np.random.get_state()[1].tobytes()
    _advance(family_of, trace=True)
    assert np.random.get_state()[1].tobytes() == before


def test_input_state_is_not_mutated(family_of) -> None:
    state = empty_state()
    before = state.fingerprint()
    _advance(family_of, trace=True, state=state)
    assert state.fingerprint() == before


def test_scored_order_is_not_mutated_by_projection(family_of, monkeypatch) -> None:
    """projection helper 가 원본 list 를 in-place 정렬하면 잡힌다."""
    calls = _record_calls(monkeypatch)
    _advance(family_of, trace=True)
    # 같은 일주의 두 호출은 동일한 scored 순서를 받아야 한다.
    seen: dict[str, tuple] = {}
    for call in calls:
        seen.setdefault(call["seed"], call["scored_keys"])
        assert seen[call["seed"]] == call["scored_keys"]


# ── 호출 수 계약 ──────────────────────────────────────────────────────────


def test_trace_off_makes_no_extra_call(family_of, monkeypatch) -> None:
    calls = _record_calls(monkeypatch)
    step, _next = _advance(family_of, trace=False)
    assert len(calls) == 60                    # 일주당 정확히 1회
    assert all("oa11d_trace" not in r for r in step.rows)


def test_call_count_matches_the_declared_matrix(
    family_of, warm, monkeypatch
) -> None:
    state, day = warm
    calls = _record_calls(monkeypatch)
    step, _next = _advance(family_of, trace=True, state=state, day=day)
    reused = sum(
        1 for r in step.rows
        if r["oa11d_trace"]["projection_source"] == "REUSED_ACTUAL_CARD"
    )
    counterfactual = len(step.rows) - reused
    # 재사용은 1회, 반사실은 2회.
    assert len(calls) == reused + 2 * counterfactual
    for row in step.rows:
        trace = row["oa11d_trace"]
        expected = 0 if trace["projection_source"] == "REUSED_ACTUAL_CARD" else 1
        assert trace["counterfactual_select_slots_calls"] == expected


def test_selection_payload_is_identical_with_and_without_trace(
    family_of, warm
) -> None:
    state, day = warm
    off, off_next = _advance(family_of, trace=False, state=state, day=day)
    on, on_next = _advance(
        family_of, trace=True, state=state, day=day,
        policy=replace(C10_POLICY, family_deficit_clean_bypass=False),
    )
    def strip(rows):
        return [
            {k: v for k, v in r.items() if k != "oa11d_trace"} for r in rows
        ]
    assert strip(off.rows) == strip(on.rows)
    assert off.board_fingerprint == on.board_fingerprint
    assert off_next.fingerprint() == on_next.fingerprint()


# ── AMBIGUOUS 경계 ────────────────────────────────────────────────────────


class _Cand:
    def __init__(self, event_key: str, probability: int) -> None:
        self.event_key = event_key
        self.probability = probability


def _bundle(*cands) -> CardCandidateBundle:
    return CardCandidateBundle(
        good_event_key="raw", slots=(), headline_candidates=tuple(cands)
    )


def test_tied_candidates_with_one_family_are_projected() -> None:
    """문장·사건이 여러 개여도 family 가 하나면 모호하지 않다."""
    projection = derive_top1_family_projection(
        raw_top_event_key="raw",
        card_candidates=_bundle(_Cand("a", 70), _Cand("b", 70)),
        family_of={"a": "work", "b": "work"},
    )
    assert projection.status is ProjectionStatus.PROJECTED
    assert projection.family == "work"


def test_tied_candidates_with_two_families_are_ambiguous() -> None:
    projection = derive_top1_family_projection(
        raw_top_event_key="raw",
        card_candidates=_bundle(_Cand("a", 70), _Cand("b", 70)),
        family_of={"a": "work", "b": "money"},
    )
    assert projection.status is ProjectionStatus.AMBIGUOUS


def test_lower_ranked_family_does_not_cause_ambiguity() -> None:
    """동률이 아닌 하위 후보의 family 는 모호성을 만들지 않는다."""
    projection = derive_top1_family_projection(
        raw_top_event_key="raw",
        card_candidates=_bundle(_Cand("a", 70), _Cand("b", 60)),
        family_of={"a": "work", "b": "money"},
    )
    assert projection.status is ProjectionStatus.PROJECTED
    assert projection.family == "work"
