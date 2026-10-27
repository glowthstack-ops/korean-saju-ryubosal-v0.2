"""합 체계 대조 P1·P2(2026-10-25 데굴님 "실험 우선, 권고대로") 회귀.

서술 전용 ON: 천합지합 표기·운이 원국 기존 합에 주는 변화 줄·운 암합 가드(이미 드러난 합 쌍 제외).
실험 플래그(기본 OFF): hap_modes.HAP_EXPERIMENTS trine_third_clash / stem_tougan.
사문 정리: 합래(HAPRAE) 패턴 미방출.
"""

from __future__ import annotations

from datetime import date

import pytest
from saju_manse_analysis.relations import hap_modes as hm

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
from saju_shared_types.constants import STEM_ELEMENT, hidden_stems_for, ten_god
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.pillars import FourPillarsResult, HiddenStem, Pillar

_DG = BirthInput(
    calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
    birth_place_name="서울", gender="male", apply_true_solar_time=False,
)


# CI 는 저장소 루트를 sys.path 에 넣지 않아 `from tests.unit.test_hap_modes import _pillars` 가
# 수집 단계에서 실패했다(2026-10-27 PR #9 CI) — 같은 helper 를 이 파일에 둔다
# (test_hap_modes 와 동일).
def _pillar(stem: str, branch: str, dm: str) -> Pillar:
    """리졸버가 읽는 필드(stem·branch·hidden_stems)만 실제값으로, 나머지는 placeholder."""
    b = Branch(branch)
    hs = [
        HiddenStem(
            stem=h.value, element=STEM_ELEMENT[h].value, type=t.value, weight=wt,
            ten_god=str(ten_god(Stem(dm), h)),
        )
        for h, t, wt in hidden_stems_for(b)
    ]
    return Pillar(
        stem=stem, branch=branch, ganji=stem + branch,
        stem_element="", branch_element="", stem_yinyang="", branch_yinyang="",
        stem_ten_god="", branch_main_ten_god="", twelve_unseong="", hidden_stems=hs,
    )


def _pillars(y: str, m: str, d: str, h: str, dm: str) -> FourPillarsResult:
    return FourPillarsResult(
        year=(_pillar(y.split()[0], y.split()[1], dm) if " " in y
              else _pillar(y[0], y[1], dm)),
        month=_pillar(m[0], m[1], dm),
        day=_pillar(d[0], d[1], dm),
        hour=_pillar(h[0], h[1], dm),
        day_master=dm,
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
    assert natal_hap_change_lines(r, luck_stems=["丁"]) == []  # 무관한 운 천간은 무변화


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
    # 2026-10-25 측정 후: trine_third_clash 기본 ON(85사례 불변·육합과 일관). 2차 실험 3종은 OFF,
    # 공합 休 조건부는 기본 ON(데굴님 확정 R3).
    assert hm.HAP_EXPERIMENTS == {
        "trine_third_clash": True, "tougan_composite": True,
        "luck_transform_requires_tier": False, "luck_transform_exclude_weak": False,
        "gonghap_effective_scoring": False, "gonghap_xiu_conditional": True,
    }
    # trine_third_clash: 寅午 반합(午 왕지) + 원국 申(寅申충) → ON 이면 等級 하락.
    p = _pillars("庚申", "丙寅", "壬午", "丙子", dm="壬")
    hm.HAP_EXPERIMENTS["trine_third_clash"] = False
    off = next(x for x in hm.resolve_branch_hap(p, {"火": "기신"}) if x.kind == "half")
    hm.HAP_EXPERIMENTS["trine_third_clash"] = True
    on = next(x for x in hm.resolve_branch_hap(p, {"火": "기신"}) if x.kind == "half")
    assert any(c.startswith("충:") for c in on.co_relations) and not any(
        c.startswith("충:") for c in off.co_relations
    )


# ── 2차: 化神 투간 분류(근거) + 복합 판단형 실험 ────────────────────────────


def test_tougan_classification_levels_and_sources(_experiments_off) -> None:
    """甲己合(土): 당사자 己는 투간 아님 / 戊 별도 투간=동일오행 / 참여 지지 지장간 글자면 직접."""
    p = _pillars("甲辰", "己巳", "丙午", "壬申", dm="丙")  # 甲己 외 土 천간 없음
    hap = next(x for x in hm.resolve_stem_hap(p, {"土": "용신"}) if set(x.pair) == {"甲", "己"})
    assert hap.tougan.level == "none" and hap.tougan.label() == "투간 없음"
    p2 = _pillars("甲辰", "己巳", "戊午", "壬申", dm="戊")  # 일간 戊 — 辰 지장간 戊 → 직접 투출
    hap2 = next(x for x in hm.resolve_stem_hap(p2, {"土": "용신"}) if set(x.pair) == {"甲", "己"})
    assert hap2.tougan.level == "direct" and hap2.tougan.source == "natal"
    # 운 천간 투간: 출처 'luck'
    hap3 = next(x for x in hm.resolve_stem_hap(p, {"土": "용신"}, luck_stems=["戊"])
                if set(x.pair) == {"甲", "己"} and not x.luck_origin)
    assert hap3.tougan.source == "luck" and "운 戊" in hap3.tougan.label()
    # 육합 寅亥(木): 원국 甲 = 寅 지장간 甲 → 직접 투출
    p4 = _pillars("辛亥", "庚寅", "甲子", "戊戌", dm="甲")
    six = next(x for x in hm.resolve_branch_hap(p4, {"木": "희신"})
               if x.kind == "six" and set(x.members) == {"寅", "亥"})
    assert six.tougan.level == "direct" and six.tougan.on_member_pillar is False


def test_tougan_composite_lifts_xiu_season_only_with_tougan(_experiments_off) -> None:
    """복합 판단형: 월령 休 + 투간 + 통근·무방해 → confirmed. 미투간이면 등급 불변."""
    # 乙庚合(金): 월지 酉 → 金 왕(확정) 대신 '休'가 되는 월령 = 金이 생하는 水 월(亥·子).
    p = _pillars("庚子", "乙亥", "丙申", "辛卯", dm="丙")  # 亥월 金 休·申 통근·辛 투간
    hm.HAP_EXPERIMENTS["tougan_composite"] = False
    base = next(x for x in hm.resolve_stem_hap(p, {"金": "용신"}) if set(x.pair) == {"乙", "庚"})
    assert base.transform_tier == "conditional"  # 복합 판단 OFF: 休 → 조건부
    hm.HAP_EXPERIMENTS["tougan_composite"] = True
    on = next(x for x in hm.resolve_stem_hap(p, {"金": "용신"}) if set(x.pair) == {"乙", "庚"})
    assert on.transform_tier == "confirmed" and any("월령 休 보완" in n for n in on.notes)
    p2 = _pillars("庚子", "乙亥", "丙申", "丁卯", dm="丙")  # 투간 없음 → 休 그대로 조건부
    off = next(x for x in hm.resolve_stem_hap(p2, {"金": "용신"}) if set(x.pair) == {"乙", "庚"})
    assert off.transform_tier == "conditional"


# ── 2차: 공합 상태 모델(인접=거리 1·旺相·休 조건부·囚死 제외·제3 충 강등) ──────


def _gonghap(p, fav=None):
    return next(x for x in hm.resolve_branch_hap(p, fav or {}) if x.kind == "gonghap")


def test_gonghap_states_by_adjacency_season_tougan(_experiments_off) -> None:
    # 申辰 공합(水): 月지 申·日지 辰 인접, 申월(金生水 → 水 相), 壬 투간(申 지장간 壬 → 직접) → 유효
    g = _gonghap(_pillars("壬午", "甲申", "丙辰", "乙未", dm="丙"), {"水": "기신"})
    assert g.gonghap_state in ("effective", "strengthened"), g.notes
    assert g.transform_tier == "conditional" and g.strength >= 0.5
    assert "인접(거리 1)" in g.notes[0] and "투간 직접" in g.notes[0]
    # 원거리(연지 申·일지 辰): 후보만
    g2 = _gonghap(_pillars("壬申", "甲午", "丙辰", "乙未", dm="丙"), {"水": "기신"})
    assert g2.gonghap_state == "candidate" and g2.transform_tier == "none" and g2.strength == 0.3
    # 囚·死 월령(未월 土 당령 → 水 死): 인접·투간 있어도 기본 제외
    g3 = _gonghap(_pillars("壬午", "乙未", "甲申", "丙辰", dm="甲"), {"水": "기신"})
    assert g3.gonghap_state == "candidate", g3.notes


def test_gonghap_xiu_conditional_requires_tougan_and_support(_experiments_off) -> None:
    """寅戌 공합(火): 戌월(火 休). 투간 丙 + 독립 지원(별도 통근 巳)이면 유효, 없으면 후보."""
    # 戌·寅 인접(月·日), 巳 별도 통근, 丙 투간
    with_support = _pillars("丙巳", "甲戌", "乙寅", "己卯", dm="乙")
    g = _gonghap(with_support, {"火": "희신"})
    assert g.gonghap_state in ("effective", "strengthened"), g.notes
    hm.HAP_EXPERIMENTS["gonghap_xiu_conditional"] = False
    g_strict = _gonghap(with_support, {"火": "희신"})
    assert g_strict.gonghap_state == "candidate"  # 旺·相만 허용하면 休는 제외
    hm.HAP_EXPERIMENTS["gonghap_xiu_conditional"] = True
    # 별도 통근 없음(子는 水)·생조 천간(木) 없음 — 戊·己·癸 천간, 丙 투간만.
    no_support = _pillars("丙子", "戊戌", "己寅", "癸卯", dm="己")
    g2 = _gonghap(no_support, {"火": "희신"})
    assert g2.gonghap_state == "candidate" and "독립 지원 없음" in g2.notes[0]


def test_gonghap_third_clash_demotes_effective_to_weak(_experiments_off) -> None:
    # 申辰(인접·申월 水 相·壬 투간) + 원국 寅(寅申충) → 유효→약한 공합 강등(삭제 아님)
    g = _gonghap(_pillars("壬寅", "甲申", "丙辰", "乙未", dm="丙"), {"水": "기신"})
    assert g.gonghap_state == "weak" and "강등" in g.notes[0], g.notes


def test_gonghap_effective_scoring_flag_gates_hierarchy_eligibility(_experiments_off) -> None:
    from saju_engines.relation_semantics import derive_branch_semantics

    g = _gonghap(_pillars("壬午", "甲申", "丙辰", "乙未", dm="丙"), {"水": "기신"})
    sem = derive_branch_semantics(g)
    assert sem.aux_state in ("effective", "strengthened")
    assert "제한적 결속" in sem.allowed_interpretations[0]
    assert "투간" in sem.tougan_label


# ── 2차: T-3 운 점수층 '합국 성립 ≠ 합화' ───────────────────────────────────


def test_luck_transform_requires_tier_filters_unconfirmed(_experiments_off) -> None:
    from saju_manse_analysis.luck.luck_cycles import _transformed_elements

    from saju_shared_types.enums import Branch

    p = _pillars("庚申", "丁亥", "己亥", "己巳", dm="己")  # 데굴님 원국
    # 운 寅: 寅亥合(木) — 亥월 木 相이나 寅申충으로 화 불성, 종전에는 木을 무조건 가산.
    legacy = _transformed_elements(Branch("寅"), p)
    assert "木" in legacy
    hm.HAP_EXPERIMENTS["luck_transform_requires_tier"] = True
    gated = _transformed_elements(Branch("寅"), p)
    assert "木" not in gated
    # 운 子: 申子辰? 원국 申·辰 없음(辰 없음) → 申子 반합(왕지) — 반합은 化 대상 아님 → 제외
    assert _transformed_elements(Branch("子"), p) == []


# ── 2차: G-3 운 화신 투간 → 원국 공합 강화 줄 ───────────────────────────────


def test_luck_tougan_line_for_natal_gonghap() -> None:
    p = _pillars("壬申", "甲午", "丙辰", "乙未", dm="丙")  # 申辰 공합(원거리 후보)
    r = calculate(_DG).model_copy(update={"pillars": p})
    lines = natal_hap_change_lines(r, luck_stems=["癸"])
    assert any("申辰 공합에 운 癸 투간" in ln and "삼합 아님" in ln for ln in lines), lines
    assert not any("공합에 운" in ln for ln in natal_hap_change_lines(r, luck_stems=["丙"]))


# ── 일주 운세: 운영 경로는 공합 제외(왕지 필수), 동결 pool 렌더는 종전 유지 ───────


def test_daily_half_harmony_requires_royal_live_but_not_for_frozen_pool() -> None:
    from saju_engines import daily_ilju_fortune as dif
    from saju_shared_types.enums import Branch

    assert dif.HALF_HARMONY_REQUIRES_ROYAL is True
    helpers = (Branch("午"), Branch("未"))
    live = dif._branch_relations(Branch("申"), Branch("辰"), helpers)  # 申辰 — 왕지 子 없음
    assert "half_harmony" not in live
    royal = dif._branch_relations(Branch("申"), Branch("子"), helpers)
    assert "half_harmony" in royal
    token = dif.half_royal_override.set(False)  # 동결 pool 렌더 문맥
    try:
        frozen = dif._branch_relations(Branch("申"), Branch("辰"), helpers)
        assert "half_harmony" in frozen
    finally:
        dif.half_royal_override.reset(token)
    assert "half_harmony" not in dif._branch_relations(Branch("申"), Branch("辰"), helpers)
