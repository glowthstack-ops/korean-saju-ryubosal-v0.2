"""Scoring Phase 1c-β — near-tie demotion(LLM 노출 순서 제한 재배열) 검증.

게이트(APPLY_ENABLED ∧ near_tie_demotion ∧ domain∈APPLY_INTENTS ∧ component≥1)·동일
level/event group·score 창·인접 쌍만·후보당 max 2칸·top-N 변화 ≤1(초과 시 legacy fallback)·
sub-flag off → None(byte-identical). 규격: YONGSIN_OPERATIONAL_ROLE_SPEC §14 1c-β.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import cast

import saju_manse_analysis.yongsin.operational_role_config as cfg

from saju_api.services import chat_service
from saju_api.services.manse_service import calculate
from saju_engines.scoring_operational import near_tie_demotion_order
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventCandidate

# 희신 과다 교정(2026-07-12) 후 구 표준차트는 A 감점 대상이 아님(水=조건부 한신/병·legacy
# 한신 0) — 교정 후에도 조건부 희신/병이 남는 차트(비겁 희신의 한습 강등, 癸巳 일주)를 쓴다.
_STD = BirthInput(calendar_type="solar", birth_date="1970-01-13", birth_time="04:30",
                  birth_place_name="Seoul", gender="male")
# 壬子=水 조건부 희신/병(A 감점 −12) / 甲寅=木 구신(감점 0) — test_scoring_apply 와 동일 차트.
_PEN, _CLEAN = "壬子", "甲寅"


def _cands(specs: list[tuple[str, int, str]]) -> tuple[list, dict[str, str]]:
    """(간지, score, event_key) 목록 → (후보 리스트, period→간지 맵).

    period 는 'p{i}'(하이픈 없음 → 동일 year level)로 부여해 level 조건을 통일한다.
    """
    sel = [SimpleNamespace(period=f"p{i}", score=s, event_key=k)
           for i, (_g, s, k) in enumerate(specs)]
    gbp = {f"p{i}": g for i, (g, _s, _k) in enumerate(specs)}
    return sel, gbp


def _on(monkeypatch, *, master=True, mode=True, intents=("career",),
        components=True) -> None:
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_APPLY_ENABLED", master)
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_APPLY_MODE",
                        {"rank_guard": False, "near_tie_demotion": mode})
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_APPLY_INTENTS", list(intents))
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_COMPONENTS",
                        {"conditional_byeong_downgrade": components,
                         "low_operability_yongsin": components})


def _order(monkeypatch, specs, *, domain="career", **kw):
    _on(monkeypatch, **kw)
    sel, gbp = _cands(specs)
    return near_tie_demotion_order(calculate(_STD), sel, gbp, domain=domain)


_PAIR = [(_PEN, 80, "e"), (_CLEAN, 80, "e")]  # 감점 후보가 위 — swap 기대


# ── 게이트: 기본 config(sub-flag off) → None(byte-identical) ──
def test_default_config_none() -> None:
    sel, gbp = _cands(_PAIR)
    assert near_tie_demotion_order(
        calculate(_STD), cast("list[EventCandidate]", sel), gbp,
        domain="career") is None


def test_master_off_none(monkeypatch) -> None:
    assert _order(monkeypatch, _PAIR, master=False) is None


def test_mode_off_none(monkeypatch) -> None:
    assert _order(monkeypatch, _PAIR, mode=False) is None


def test_domain_not_allowed_none(monkeypatch) -> None:
    assert _order(monkeypatch, _PAIR, domain="general") is None
    assert _order(monkeypatch, _PAIR, intents=("wealth",)) is None


def test_components_off_none(monkeypatch) -> None:
    assert _order(monkeypatch, _PAIR, components=False) is None


# ── 기본 swap: 감점 후보(adjusted 역전)가 near-tie 인접 아래로 ──
def test_basic_demotion(monkeypatch) -> None:
    assert _order(monkeypatch, _PAIR) == [1, 0]


# ── 조건 미충족이면 미재배열(None) ──
def test_different_group_none(monkeypatch) -> None:
    assert _order(monkeypatch, [(_PEN, 80, "e1"), (_CLEAN, 80, "e2")]) is None


def test_score_gap_over_window_none(monkeypatch) -> None:
    assert _order(monkeypatch, [(_PEN, 80, "e"), (_CLEAN, 70, "e")]) is None


def test_no_penalty_none(monkeypatch) -> None:
    assert _order(monkeypatch, [(_CLEAN, 80, "e"), (_CLEAN, 80, "e")]) is None


def test_penalized_below_stays(monkeypatch) -> None:
    # 감점 후보가 이미 아래면 재배열 없음(위 후보 adjusted 가 더 높음).
    assert _order(monkeypatch, [(_CLEAN, 80, "e"), (_PEN, 80, "e")]) is None


def test_different_level_none(monkeypatch) -> None:
    _on(monkeypatch)
    sel = cast("list[EventCandidate]",
               [SimpleNamespace(period="2026", score=80, event_key="e"),
                SimpleNamespace(period="2026-07", score=80, event_key="e")])
    gbp = {"2026": _PEN, "2026-07": _CLEAN}
    assert near_tie_demotion_order(calculate(_STD), sel, gbp, domain="career") is None


# ── 후보당 최대 max_demotion_cap(2) 칸만 하강 ──
def test_demotion_cap_two_positions(monkeypatch) -> None:
    specs = [(_PEN, 80, "e")] + [(_CLEAN, 80, "e")] * 5
    assert _order(monkeypatch, specs) == [1, 2, 0, 3, 4, 5]


# ── top-N 구성 변화 1 이내 → 재배열 유지 ──
def test_topn_change_within_limit(monkeypatch) -> None:
    specs = [(_CLEAN, 80, "e")] * 9 + [(_PEN, 80, "e")] + [(_CLEAN, 80, "e")] * 2
    # index 9(감점)가 2칸 하강 → top-10 에서 9 이탈·10 진입(변화 1) — 허용.
    order = _order(monkeypatch, specs)
    assert order is not None
    assert order.index(9) == 11 and order[:9] == list(range(9))


# ── top-N 구성 변화 초과 → legacy fallback(None) ──
def test_topn_change_over_limit_fallback(monkeypatch) -> None:
    specs = ([(_CLEAN, 80, "e")] * 8 + [(_PEN, 80, "e")] * 2
             + [(_CLEAN, 80, "e")] * 2)
    # index 8·9 둘 다 하강 시 top-10 변화 2 — topn_change_limit(1) 초과 → None.
    assert _order(monkeypatch, specs) is None


# ── 배선: flag on 채팅 경로 무예외 + 기본 config 미적용 ──
def test_wiring_chat_path(monkeypatch) -> None:
    birth = _STD.model_copy(update={"reference_date": "2026-06-11"})
    off = chat_service.chat(birth, "올해 직업운 어때?", date(2026, 6, 11),
                            dry_run=True).prompt_preview or ""
    assert off  # 기본 config(sub-flag off) — 기존 경로 정상
    _on(monkeypatch)
    on = chat_service.chat(birth, "올해 직업운 어때?", date(2026, 6, 11),
                           dry_run=True).prompt_preview or ""
    assert on  # flag on 에서도 조립·직렬화 무예외(재배열은 후보 구성에 따라 0회 가능)
