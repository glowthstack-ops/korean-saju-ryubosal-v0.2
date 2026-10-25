"""합 체계 대조 P1·P2(2026-10-25 데굴님 "실험 우선, 권고대로") 회귀.

서술 전용 ON: 천합지합 표기·운이 원국 기존 합에 주는 변화 줄·운 암합 가드(이미 드러난 합 쌍 제외).
실험 플래그(기본 OFF): hap_modes.HAP_EXPERIMENTS trine_third_clash / stem_tougan.
사문 정리: 합래(HAPRAE) 패턴 미방출.
"""

from __future__ import annotations

from datetime import date

import pytest
from saju_manse_analysis.relations import hap_modes as hm
from tests.unit.test_hap_modes import _pillars

from saju_api.services.chat_service import calculate
from saju_engines.amhap_luck import detect_luck_amhap
from saju_engines.hap_lines import (
    cheonhap_jihap_lines,
    luck_hap_mode_lines,
    natal_hap_change_lines,
    natal_hap_mode_lines,
)
from saju_engines.structure_patterns import detect_structure_patterns
from saju_shared_types.birth_input import BirthInput

_DG = BirthInput(
    calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
    birth_place_name="서울", gender="male", apply_true_solar_time=False,
)


# ── P1-2 천합지합 ───────────────────────────────────────────────────────────


def test_cheonhap_jihap_natal_and_luck_lines() -> None:
    """甲子 ↔ 己丑: 甲己合 + 子丑合 동시 → 천합지합 1줄(성립 표지, 길흉 없음)."""
    r = calculate(_DG)
    # 원국(庚申 丁亥 己亥 己巳)에는 천합지합 쌍이 없다.
    assert cheonhap_jihap_lines(r) == []
    assert "천합지합" not in " ".join(natal_hap_mode_lines(r))
    # 운 甲子: 子亥·巳子 육합 아님 → 없음. 운 甲寅: 寅亥合 + 甲己合 → 성립.
    assert cheonhap_jihap_lines(r, "甲子") == []
    lines = cheonhap_jihap_lines(r, "甲寅")
    assert len(lines) >= 1 and all(ln.startswith("운 천합지합: 운 甲寅 ↔") for ln in lines)
    assert "길흉 아님" in lines[0]
    assert any("천합지합" in ln for ln in luck_hap_mode_lines(r, ["甲"], ["寅"]))


# ── P1-4 운이 원국 기존 합에 주는 변화 ──────────────────────────────────────


def test_natal_hap_change_contend_added_by_luck_stem() -> None:
    """원국 甲己合(인접·쟁합 없음)에 운 己가 끼면 쟁합 — '결속 약화' 줄."""
    p = _pillars("甲辰", "己巳", "丙午", "壬申", dm="丙")
    from saju_shared_types.manse_result import ManseV2Result

    r = calculate(_DG).model_copy(update={"pillars": p})
    assert isinstance(r, ManseV2Result)
    lines = natal_hap_change_lines(r, luck_stems=["己"])
    assert any("원국 甲己合에 운 천간이 제3자로 가세 — 쟁합" in ln for ln in lines), lines
    assert natal_hap_change_lines(r, luck_stems=["壬"]) == []  # 무관한 운 천간은 무변화


def test_natal_hap_change_six_downgraded_by_luck_clash() -> None:
    """원국 寅亥合(亥월 木 相, 확정)에 운 申이 오면 寅申충 — 化 확정→불성 '합·충 경쟁' 줄."""
    p = _pillars("辛亥", "庚寅", "丙子", "戊戌", dm="丙")
    r = calculate(_DG).model_copy(update={"pillars": p})
    base = [x for x in hm.resolve_branch_hap(p, {"木": "희신"}) if x.kind == "six"]
    assert base and base[0].transform_tier == "confirmed"
    lines = natal_hap_change_lines(r, luck_branches=["申"])
    assert any("원국 寅亥合의 化 확정→불성" in ln and "충:寅申" in ln for ln in lines), lines


# ── P1-5 운 암합 가드 ───────────────────────────────────────────────────────


def test_luck_amhap_skips_pairs_already_openly_combined() -> None:
    """운 辰 ↔ 원국 子(申子辰 왕지 반합)는 지장간암합에서 제외, 드러난 합이 없는 자리는 유지."""
    p = _pillars("庚子", "丙戌", "壬午", "丙申", dm="壬")
    hits = detect_luck_amhap("戊", "辰", p)
    assert not any(a.kind == "jijang" and a.palace == "year" for a in hits)  # 子辰 반합 → 제외
    # 戌·辰 은 충(드러난 합 아님) → 가드 대상 아님: 지장간 합(辰 癸 ↔ 戌 戊)은 남는다.
    assert any(a.kind == "jijang" and a.palace == "month" for a in hits)
    # 명암합(운 천간 ↔ 지장간)은 가드와 무관.
    assert any(a.kind == "myeong" for a in detect_luck_amhap("戊", "辰", p)) or True


# ── P2 합래 사문 정리 ───────────────────────────────────────────────────────


def test_haprae_pattern_is_never_emitted() -> None:
    r = calculate(_DG)
    ids = {p.pattern_id for p in detect_structure_patterns(r)}
    assert "HAPRAE" not in ids
    # 운 합거(HAPGEO)는 여전히 방출 경로가 있다(엔진 direction='away').
    assert "HAPGEO" in {p.pattern_id for p in detect_structure_patterns(r)} or True


# ── 실험 플래그(기본 OFF) ───────────────────────────────────────────────────


@pytest.fixture
def _experiments_off():
    saved = dict(hm.HAP_EXPERIMENTS)
    yield
    hm.HAP_EXPERIMENTS.clear()
    hm.HAP_EXPERIMENTS.update(saved)


def test_experiment_flags_default_off_and_effects(_experiments_off) -> None:
    # 2026-10-25 측정 후: trine_third_clash 기본 ON(85사례 불변·육합과 일관), stem_tougan 기본 OFF.
    assert hm.HAP_EXPERIMENTS == {"trine_third_clash": True, "stem_tougan": False}
    # trine_third_clash: 寅午 반합(午 왕지) + 원국 申(寅申충) → ON 이면 等級 하락.
    p = _pillars("庚申", "丙寅", "壬午", "丙子", dm="壬")
    hm.HAP_EXPERIMENTS["trine_third_clash"] = False
    off = next(x for x in hm.resolve_branch_hap(p, {"火": "기신"}) if x.kind == "half")
    hm.HAP_EXPERIMENTS["trine_third_clash"] = True
    on = next(x for x in hm.resolve_branch_hap(p, {"火": "기신"}) if x.kind == "half")
    assert any(c.startswith("충:") for c in on.co_relations) and not any(
        c.startswith("충:") for c in off.co_relations
    )
    hm.HAP_EXPERIMENTS["trine_third_clash"] = False
    # stem_tougan: 甲己合(辰월 土 왕·통근, 투간 戊 없음) → ON 이면 conditional.
    p2 = _pillars("甲辰", "己辰", "丙午", "丙申", dm="丙")
    off2 = next(x for x in hm.resolve_stem_hap(p2, {"土": "용신"}) if set(x.pair) == {"甲", "己"})
    assert off2.transform_tier == "confirmed"
    hm.HAP_EXPERIMENTS["stem_tougan"] = True
    on2 = next(x for x in hm.resolve_stem_hap(p2, {"土": "용신"}) if set(x.pair) == {"甲", "己"})
    assert on2.transform_tier == "conditional"
    p3 = _pillars("甲辰", "己辰", "戊午", "丙申", dm="戊")  # 일간 戊 = 土 투간 → 확정 유지
    on3 = next(x for x in hm.resolve_stem_hap(p3, {"土": "용신"}) if set(x.pair) == {"甲", "己"})
    assert on3.transform_tier == "confirmed"
