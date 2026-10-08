"""운 기둥 지지 중기·여기 십성 신호 (2026-10-08 데굴님 승인, shadow·기본 OFF).

실험용 채택 규칙: 채점 대상 기둥만, 중기 0.9×0.6=0.54·여기 0.9×0.35=0.315, 천간·본기와 같은
십성군은 제외, 중·여기끼리 같은 군이면 큰 쪽(중기)만. 배경 운층·플래그 OFF·day_master 미전달이면
기존 2신호 그대로.
규격: doc/v2_2/TRANSIT_HIDDEN_STEM_REVIEW.md §3
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import period_v2_config as cfg
from saju_engines.ten_god_brancher import TenGodEventBrancher
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import TEN_GOD_GROUP

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _pillar_with_branch(branch: str):
    """기준 사주 1985-10-29(辛 일간)의 기준 창 세운 중 지지가 branch 인 기둥."""
    r = calculate(BirthInput(calendar_type="solar", birth_date="1985-10-29", birth_time="22:20",
                             birth_place_name="서울", gender="female", reference_date="2026-10-08"))
    for dw in r.luck_cycles.daewoon_table:
        for sp in dw.sewoon:
            if sp.branch == branch:
                return r, sp
    raise AssertionError(branch)


def test_flag_off_or_no_day_master_keeps_two_signals() -> None:
    assert cfg.TRANSIT_HIDDEN_STEM_ENABLED is False
    br = TenGodEventBrancher(_DICTS)
    r, sp = _pillar_with_branch("寅")  # 寅: 甲(본기)·丙(중기)·戊(여기)
    base = br.collect_from_pillar(sp, "sewoon", is_target=True)
    assert [s.source for s in base] == ["stem", "branch_main"]
    with_dm = br.collect_from_pillar(sp, "sewoon", is_target=True, day_master=r.pillars.day_master)
    assert [s.source for s in with_dm] == ["stem", "branch_main"]  # OFF 면 불변


def test_flag_on_adds_hidden_signals_with_dedup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "TRANSIT_HIDDEN_STEM_ENABLED", True)
    br = TenGodEventBrancher(_DICTS)
    r, sp = _pillar_with_branch("寅")
    sig = br.collect_from_pillar(sp, "sewoon", is_target=True, day_master=r.pillars.day_master)
    hidden = [s for s in sig if s.source in ("branch_mid", "branch_initial")]
    assert hidden, "寅 중기 丙·여기 戊 중 천간·본기와 군이 다른 것이 신호로 들어와야 한다"
    base_groups = {TEN_GOD_GROUP[s.ten_god] for s in sig if s.source in ("stem", "branch_main")}
    for h in hidden:
        assert TEN_GOD_GROUP[h.ten_god] not in base_groups  # 천간·본기와 같은 군 제외
        assert h.strength in (0.54, 0.315)
    groups = [TEN_GOD_GROUP[h.ten_god] for h in hidden]
    assert len(groups) == len(set(groups))  # 중·여기 같은 군은 1개만
    # 배경 운층은 본기 유지.
    bg = br.collect_from_pillar(sp, "sewoon", is_target=False, day_master=r.pillars.day_master)
    assert [s.source for s in bg] == ["stem", "branch_main"]


def test_single_hidden_branch_adds_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """子(癸 단독)·卯(乙 단독)·酉(辛 단독)은 중·여기가 없어 신호 추가 없음."""
    monkeypatch.setattr(cfg, "TRANSIT_HIDDEN_STEM_ENABLED", True)
    br = TenGodEventBrancher(_DICTS)
    r, sp = _pillar_with_branch("子")
    sig = br.collect_from_pillar(sp, "sewoon", is_target=True, day_master=r.pillars.day_master)
    assert [s.source for s in sig] == ["stem", "branch_main"]
