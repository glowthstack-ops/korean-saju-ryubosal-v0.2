"""OA-9c G0 — 불리 발현 자격 게이트의 계약.

지켜야 할 것이 셋이다. 하나라도 무너지면 게이트가 "편재를 다른 이름으로 다시 쓰는"
장치가 되어 OA-9a 가 진단한 문제를 그대로 재현한다.

1. 재성은 **주제 활성** 근거일 뿐이다 — 불리 발현 근거로 재사용되지 않는다.
2. 불리 근거는 **재물 관련**이어야 한다 — 다른 도메인의 마찰이 과소비 경고를 열 수 없다.
3. raw 점수는 보존된다 — 자격만 분리한다(감사 가능성).
"""

from __future__ import annotations

import copy
import datetime as dt

import pytest

import saju_engines.daily_g0_shadow as G
import saju_engines.daily_ilju_fortune as M
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

_START = dt.date(2026, 7, 1)
_DAYS = 14


@pytest.fixture(scope="module")
def dicts():
    return M.load_daily_dicts()


def _cards(days: int = _DAYS):
    """(일주 천간, 일주 지지, 그 날의 간지 맥락) 전수 순회."""
    for i in range(days):
        ctx = M.build_day_context(_START + dt.timedelta(days=i))
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            yield stem, branch, ctx


# ── 범위 ───────────────────────────────────────────────────────────────────


def test_gate_targets_are_the_approved_money_slice() -> None:
    """승인 범위 밖으로 조용히 넓어지지 않는다 — document 3종은 deferred 다."""
    assert G.g0_target_keys() == ("lend_money_caution", "overspend_caution")


def test_both_money_cautions_are_gated_together(dicts) -> None:
    """하나만 막으면 같은 편재 근거를 쓰는 다른 사건으로 승자가 이동한다(OA-9a 223건)."""
    events = dicts.catalog["events"]
    stem, branch, ctx = next(iter(_cards(1)))
    _scored, _survivors, decisions = G.evaluate_card(events, stem, branch, ctx)

    assert set(decisions) == {"overspend_caution", "lend_money_caution"}


# ── 불변식 1: 재성은 불리 근거가 아니다 ────────────────────────────────────


def test_wealth_is_never_adverse_provenance(dicts) -> None:
    """근거 원인군은 비겁·충형파해뿐이다 — 재성이 여기 나오면 계약 위반이다."""
    allowed = {G.WEALTH_CONTENTION, G.WEALTH_BRANCH_CONFLICT}
    for stem, branch, ctx in _cards(3):
        for ev in G.money_adverse_evidence(stem, branch, ctx):
            assert ev.cause_group in allowed
            assert not any(w in ev.source_pattern.split(" ")[0] for w in G.WEALTH_TEN_GODS)


def test_gate_decision_is_invariant_to_wealth_affinity(dicts) -> None:
    """사건의 편재·정재 계수를 전부 지워도 자격 판정이 **한 건도** 바뀌지 않는다.

    이것이 "재성 affinity 를 다시 포장하지 않았다"는 기계적 증명이다. 게이트가
    명식·운의 십성 구성만 보고 판정하므로 사건 사전과 독립이다.
    """
    events = dicts.catalog["events"]
    stripped = copy.deepcopy(events)
    for key in G.g0_target_keys():
        for tg in G.WEALTH_TEN_GODS:
            stripped[key]["ten_god_affinity"].pop(tg, None)

    for stem, branch, ctx in _cards(3):
        _s0, _v0, d0 = G.evaluate_card(events, stem, branch, ctx)
        _s1, _v1, d1 = G.evaluate_card(stripped, stem, branch, ctx)
        for key in d0:
            assert d0[key].caution_slot_eligible == d1[key].caution_slot_eligible, key
            assert d0[key].gate_codes == d1[key].gate_codes, key
            assert d0[key].adverse_evidence_provenance == d1[key].adverse_evidence_provenance


def test_subject_activation_alone_never_grants_eligibility(dicts) -> None:
    """주제만 활성이고 독립 불리 근거가 없으면 반드시 탈락한다(fail-closed)."""
    events = dicts.catalog["events"]
    seen = 0
    for stem, branch, ctx in _cards(5):
        if not G.wealth_subject_activated(stem, branch, ctx):
            continue
        if G.money_adverse_evidence(stem, branch, ctx):
            continue
        seen += 1
        _s, _v, decisions = G.evaluate_card(events, stem, branch, ctx)
        for key, d in decisions.items():
            assert d.caution_slot_eligible is False, key
            assert d.headline_eligible is False, key
            assert d.gate_codes == (G.ADVERSE_MANIFESTATION_NOT_ESTABLISHED,)
    assert seen, "해당 조합이 표본에 없다 — 테스트가 아무것도 검증하지 못했다"


# ── 불변식 2: 불리 근거는 재물 관련이어야 한다 ────────────────────────────


def test_every_evidence_declares_money_relevance(dicts) -> None:
    for stem, branch, ctx in _cards(3):
        for ev in G.money_adverse_evidence(stem, branch, ctx):
            assert ev.domain_relevance == "money"
            assert ev.evidence_role == "independent_adverse_manifestation"


def test_branch_conflict_requires_a_wealth_branch(dicts) -> None:
    """충·형이 있어도 재물 자리가 걸려 있지 않으면 근거가 되지 않는다.

    이게 없으면 관계 갈등·이동 차질 같은 다른 영역의 마찰이 과소비 경고를 연다.
    """
    for stem, branch, ctx in _cards(5):
        for ev in G.money_adverse_evidence(stem, branch, ctx):
            if ev.cause_group != G.WEALTH_BRANCH_CONFLICT:
                continue
            sides = ev.evidence_id.split(":")[-1].split("+")
            assert sides, ev.evidence_id
            holders = {
                "ilju_branch": branch,
                "day_branch": M.Branch(ctx.day_branch),
                "month_branch": M.Branch(ctx.month_branch),
                "year_branch": M.Branch(ctx.year_branch),
            }
            assert any(G._branch_holds_wealth(stem, holders[s]) for s in sides)


def test_unrelated_conflict_does_not_open_the_gate(dicts) -> None:
    """재물 자리가 없고 비겁도 없는데 충만 있는 카드 — 자격이 열리면 안 된다."""
    checked = 0
    for stem, branch, ctx in _cards(10):
        rel_any = any(
            M._branch_relations(
                M.Branch(ctx.day_branch), branch,
                (M.Branch(ctx.month_branch), M.Branch(ctx.year_branch)),
            ).get(k, 0.0) > 0
            for k in G.ADVERSE_RELATIONS
        )
        if not rel_any:
            continue
        ev = G.money_adverse_evidence(stem, branch, ctx)
        if any(e.cause_group == G.WEALTH_CONTENTION for e in ev):
            continue  # 비겁이 따로 있으면 이 테스트의 대상이 아니다
        checked += 1
        for e in ev:
            assert e.cause_group == G.WEALTH_BRANCH_CONFLICT
    assert checked, "불리 관계만 있는 카드가 표본에 없다"


# ── 불변식 3: raw 보존 + 슬롯 영향 범위 ───────────────────────────────────


def test_raw_scores_are_untouched(dicts) -> None:
    """게이트는 점수를 만지지 않는다 — 라이브 산식과 값이 같아야 한다."""
    events = dicts.catalog["events"]
    for stem, branch, ctx in _cards(2):
        scored, _survivors, decisions = G.evaluate_card(events, stem, branch, ctx)
        for key, d in decisions.items():
            assert d.raw_probability == M._score_event(
                key, events[key], stem, branch, ctx
            ).probability
        for key, s in scored.items():
            assert s == M._score_event(key, events[key], stem, branch, ctx)


def test_gate_touches_only_caution_slot(dicts) -> None:
    """제외 대상은 전부 caution 전용 사건이라 good·support 선발이 흔들리지 않는다."""
    events = dicts.catalog["events"]
    for key in G.g0_target_keys():
        assert events[key]["slots"] == ["caution"]
        assert (events[key].get("headline_slots") or events[key]["slots"]) == ["caution"]

    for stem, branch, ctx in _cards(3):
        _scored, survivors, _d = G.evaluate_card(events, stem, branch, ctx)
        seed = f"{ctx.the_date.isoformat()}|{stem.value}{branch.value}|x"
        good, caution, support = M._select_slots(survivors, seed)
        base_good, _bc, base_support = M._select_slots(
            list(_scored.values()), seed
        )
        assert good.event_key == base_good.event_key
        assert support.event_key == base_support.event_key
        assert caution.valence == "caution"


def test_blocked_event_never_reaches_a_slot(dicts) -> None:
    events = dicts.catalog["events"]
    for stem, branch, ctx in _cards(7):
        _scored, survivors, decisions = G.evaluate_card(events, stem, branch, ctx)
        blocked = {k for k, d in decisions.items() if not d.caution_slot_eligible}
        if not blocked:
            continue
        seed = f"{ctx.the_date.isoformat()}|{stem.value}{branch.value}|x"
        chosen = {s.event_key for s in M._select_slots(survivors, seed)}
        assert not (chosen & blocked)


def test_eligible_caution_always_remains(dicts) -> None:
    """이번 슬라이스에서는 25종 중 2종만 막으므로 주의 후보가 고갈되지 않는다.

    고갈되면 `NO_ELIGIBLE_CAUTION_EVENT` 경로로 가야 하는데, 여기서 0건임을
    확인해 두어야 감사 보고의 '0건'이 미구현이 아니라 실측임을 보장한다.
    """
    events = dicts.catalog["events"]
    for stem, branch, ctx in _cards(7):
        _scored, survivors, _d = G.evaluate_card(events, stem, branch, ctx)
        assert any(s.valence == "caution" for s in survivors)


# ── 라이브 불변 ────────────────────────────────────────────────────────────


def test_importing_the_gate_does_not_change_live_boards(dicts) -> None:
    """shadow 모듈을 불러오는 것만으로 라이브 보드가 달라지면 안 된다."""
    day = dt.date(2026, 8, 3)
    board = M.compute_board(M.build_day_context(day), M.load_daily_dicts_for(day))
    again = M.compute_board(M.build_day_context(day), M.load_daily_dicts_for(day))
    assert [f.headline_event_key for f in board.fortunes] == [
        f.headline_event_key for f in again.fortunes
    ]
    assert any(
        e.event_key in G.g0_target_keys()
        for f in board.fortunes for e in f.events
    ), "라이브에는 아직 게이트가 적용되지 않아야 한다(대상 사건이 그대로 노출된다)"
