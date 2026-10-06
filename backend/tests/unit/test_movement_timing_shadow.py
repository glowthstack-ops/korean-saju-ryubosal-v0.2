"""이동 시기 shadow — 계절 묶임·왕지 트리거 감지 (2026-10-06, doc/v2_2/MOVEMENT_TIMING_SHADOW.md).

관측 전용 모듈이므로 '무엇을 기록하는가'만 고정한다. 해석·점수 연결은 검증 대상이 아니다
(존재하지 않아야 한다).
"""

from __future__ import annotations

from types import SimpleNamespace

from saju_engines import movement_timing_shadow as mv
from saju_shared_types.enums import Branch as B
from saju_shared_types.enums import Stem as S

_YANG = {B.JA, B.IN, B.JIN, B.O, B.SIN, B.SUL}


def _p(branch: B) -> tuple[S, B]:
    """음양이 맞는 60갑자 쌍 — 양지는 甲, 음지는 乙(지지 배합만 보는 테스트라 천간은 무관)."""
    return (S.GAP if branch in _YANG else S.EUL), branch


def _bound(make_pillars, year, month, day, hour, dm=S.GAP):
    return mv.detect_season_bound(make_pillars(year, month, day, hour, dm))


# ── 계절 묶임 ───────────────────────────────────────────────────────


def test_directional_full_is_strong(make_pillars) -> None:
    """寅卯辰 방합 완성 + 앵커 寅 → strong, 왕지 午·고지 戌."""
    b = _bound(make_pillars, _p(B.IN), _p(B.MYO), _p(B.JIN), _p(B.JA))
    assert b.tier == "strong" and b.season == "봄" and b.anchor == "寅"
    assert "directional_full" in b.evidence
    assert b.royal_branch == "午" and b.storage_branch == "戌"


def test_repeat_birth_branch_is_moderate(make_pillars) -> None:
    """巳巳 반복(월지는 다른 계절) → moderate, 근거 repeat_birth_branch."""
    b = _bound(make_pillars, _p(B.SA), _p(B.JA), _p(B.SA), _p(B.YU))
    assert b.tier == "moderate" and b.season == "여름" and b.anchor == "巳"
    assert b.evidence == ["repeat_birth_branch"]
    assert b.royal_branch == "酉"


def test_season_dominance_is_strong(make_pillars) -> None:
    """申·酉·酉 + 앵커 申(세 글자 중 두 종류) → 편중 3개 → strong."""
    b = _bound(make_pillars, _p(B.SIN), _p(B.YU), _p(B.YU), _p(B.JA))
    assert b.tier == "strong" and b.season == "가을"
    assert "season_dominance" in b.evidence and "directional_full" not in b.evidence
    assert b.royal_branch == "子" and b.storage_branch == "辰"


def test_partial_with_month_is_moderate(make_pillars) -> None:
    """亥 + 월지 子(겨울) 두 글자 → directional_partial_with_month → moderate."""
    b = _bound(make_pillars, _p(B.HAE), _p(B.JA), _p(B.O), _p(B.YU))
    assert b.tier == "moderate" and b.evidence == ["directional_partial_with_month"]
    assert "month_in_season" in b.flags


def test_no_anchor_means_no_binding(make_pillars) -> None:
    """卯辰 두 글자가 있어도 생지 寅이 없으면 묶임 없음(앵커 필수)."""
    b = _bound(make_pillars, _p(B.MYO), _p(B.JIN), _p(B.O), _p(B.YU))
    assert b.tier == "none" and b.season is None and b.royal_branch is None


def test_storage_month_and_anchor_clash_and_royal_flags(make_pillars) -> None:
    """辰월(고지) 보류 플래그, 앵커 寅이 申 충을 받음, 대응 왕지 午 원국 보유 — 모두 관측값.

    寅·辰·寅은 봄 글자 3개라 편중(strong)이며 생지 반복 근거도 함께 기록된다.
    """
    b = _bound(make_pillars, _p(B.IN), _p(B.JIN), _p(B.IN), _p(B.SIN))
    assert b.tier == "strong"
    assert {"repeat_birth_branch", "season_dominance"} <= set(b.evidence)
    assert {"month_is_storage", "month_in_season", "anchor_clashed"} <= set(b.flags)
    assert "natal_royal_present" not in b.flags
    b2 = _bound(make_pillars, _p(B.IN), _p(B.MYO), _p(B.IN), _p(B.O))
    assert "natal_royal_present" in b2.flags


def test_higher_tier_wins_then_month_season(make_pillars) -> None:
    """두 계절이 동시에 걸리면 등급 높은 쪽 — 寅寅(moderate) vs 巳午未(strong) → 여름."""
    b = _bound(make_pillars, _p(B.SA), _p(B.O), _p(B.MI), _p(B.IN))
    assert b.season == "여름" and b.tier == "strong"


# ── 왕지 트리거 ──────────────────────────────────────────────────────


def _cand(key: str, period: str):
    return SimpleNamespace(event_key=key, period=period)


def _periods():
    return [
        mv.PeriodRef(level="daewoon", label="DW:庚午", branch="午", relations=["삼합기여:火"]),
        mv.PeriodRef(level="year", label="2026", branch="午", relations=["반합성립:火"]),
        mv.PeriodRef(level="year", label="2027", branch="未", relations=[]),
        mv.PeriodRef(level="year", label="2030", branch="戌", relations=["충:戌-辰"]),
        mv.PeriodRef(level="month", label="2026-06", branch="午", relations=[]),
        mv.PeriodRef(level="month", label="2026-10", branch="戌", relations=[]),
    ]


def test_royal_arrival_recorded_storage_marked_non_trigger(make_pillars) -> None:
    bound = _bound(make_pillars, _p(B.IN), _p(B.MYO), _p(B.JIN), _p(B.JA))
    out = mv.detect_royal_triggers(bound, _periods(), [])
    kinds = {(t.level, t.period): t.kind for t in out}
    assert kinds == {
        ("daewoon", "DW:庚午"): "royal", ("year", "2026"): "royal", ("month", "2026-06"): "royal",
        ("year", "2030"): "storage", ("month", "2026-10"): "storage",
    }  # 未(2027)는 이 삼합의 고지가 아니라 기록되지 않는다


def test_samhap_overlap_and_candidate_flags(make_pillars) -> None:
    bound = _bound(make_pillars, _p(B.IN), _p(B.MYO), _p(B.JIN), _p(B.JA))
    cands = [_cand("relocation", "2026-06"), _cand("career_change", "2026")]
    out = {(t.level, t.period): t for t in mv.detect_royal_triggers(bound, _periods(), cands)}
    y = out[("year", "2026")]
    assert y.overlaps_samhap is True  # 반합성립 — 중복 가산 차단 근거
    assert y.has_relocation_candidate is True  # 그 해의 월 후보(2026-06)도 인정
    assert y.has_career_candidate is True
    m = out[("month", "2026-06")]
    assert m.overlaps_samhap is False and m.has_relocation_candidate is True
    assert m.has_career_candidate is True  # 연 후보(2026)가 그 해 월을 덮는다
    assert out[("daewoon", "DW:庚午")].has_relocation_candidate is False  # 대운은 미평가
    assert m.compact() == "month:2026-06:午:royal:samhap=0:reloc=1:career=1"


def test_no_binding_yields_no_triggers(make_pillars) -> None:
    bound = _bound(make_pillars, _p(B.MYO), _p(B.JIN), _p(B.O), _p(B.YU))
    assert mv.detect_royal_triggers(bound, _periods(), [_cand("relocation", "2026")]) == []


def test_detect_from_result_uses_luck_cycles(make_pillars) -> None:
    """ManseV2Result 형태(pillars + luck_cycles)에서 기간을 뽑아 end-to-end 로 감지한다."""
    pillars = make_pillars(_p(B.IN), _p(B.MYO), _p(B.JIN), _p(B.JA), S.GAP)
    cycles = SimpleNamespace(
        daewoon_table=[SimpleNamespace(ganji="庚午", branch="午", relations_to_chart=[])],
        yearly_luck=[
            SimpleNamespace(label="2026", branch="午", relations_to_chart=["삼합완성:火"]),
        ],
        monthly_luck=[SimpleNamespace(label="2026-06", branch="午", relations_to_chart=[])],
    )
    result = SimpleNamespace(pillars=pillars, luck_cycles=cycles)
    shadow = mv.detect_movement_timing_shadow(result, [_cand("relocation", "2026")])
    assert shadow.season_bound.tier == "strong"
    assert [t.compact() for t in shadow.royal_triggers] == [
        "daewoon:DW:庚午:午:royal:samhap=0:reloc=0:career=0",
        "year:2026:午:royal:samhap=1:reloc=1:career=0",
        "month:2026-06:午:royal:samhap=0:reloc=1:career=0",
    ]
    assert any("대운" in u for u in shadow.unevaluated)


def test_result_without_pillars_is_unevaluated() -> None:
    shadow = mv.detect_movement_timing_shadow(SimpleNamespace(pillars=None), [])
    assert shadow.season_bound.tier == "none" and shadow.unevaluated == ["pillars 없음"]
