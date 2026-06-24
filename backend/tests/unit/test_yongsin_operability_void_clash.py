"""용신 작동성 — 공망·충 (#6a). 용신 통근 지지의 공망·충만 보수적으로 penalty.

void = 통근 지지 전부 공망(solid root 1개라도 있으면 미적용). clash = 용신 통근 지지가 六沖.
통근 없으면 no_root 만(void/clash 아님). relations·이벤트·랭킹·final 불변. 계수는 config.
규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §5-4
"""

from __future__ import annotations

from saju_manse_analysis import analyze_chart
from saju_manse_analysis.yongsin.candidates import _yongsin_void_clash_factors
from saju_manse_analysis.yongsin.operational_role_config import (
    OPERABILITY_FACTOR_SHORT,
    OPERABILITY_PENALTY,
)

from saju_shared_types.enums import Branch, Stem


def _yongsin(make_pillars, *args):
    y = analyze_chart(make_pillars(*args)).yongsin
    return y, next(r for r in y.operational_roles if r.element == y.final["yongsin"])

# 차트 인자 묶음
_STD = ((Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG)
# 용신 木, 통근(亥) 전부 공망 → void (0.8)
_VOID = ((Stem.SIN, Branch.YU), (Stem.JEONG, Branch.HAE),
         (Stem.EUL, Branch.CHUK), (Stem.GI, Branch.CHUK), Stem.EUL)
# 용신 金 투출(辛)·통근(丑)이 丑未 충 → clash 단독(합반 무관, 0.85)
_CLASH = ((Stem.EUL, Branch.CHUK), (Stem.GAP, Branch.JA),
          (Stem.GAP, Branch.JA), (Stem.SIN, Branch.MI), Stem.GAP)
# 용신 木, 통근 전무 → no_root (void/clash 아님)
_NOROOT = ((Stem.GYEONG, Branch.SIN), (Stem.EUL, Branch.CHUK),
           (Stem.GAP, Branch.JA), (Stem.GYEONG, Branch.SIN), Stem.GAP)


def test_standard_no_void_clash_solid_root(make_pillars) -> None:
    # 표준: 木 통근 卯(공망)+未(solid) → solid 있어 void 미적용, 충도 없음 → 0.595 유지.
    _, er = _yongsin(make_pillars, *_STD)
    assert er.operability == 0.595
    assert "yongsin_void" not in er.operability_factors
    assert "yongsin_clash" not in er.operability_factors


def test_void_penalty_all_roots_gongmang(make_pillars) -> None:
    _, er = _yongsin(make_pillars, *_VOID)
    assert "yongsin_void" in er.operability_factors
    assert er.operability == round(1.0 * (1 - OPERABILITY_PENALTY["yongsin_void"]), 4)
    assert OPERABILITY_FACTOR_SHORT["yongsin_void"] == "공망"  # 프리픽스 압축 라벨
    assert any("공망" in s for s in er.negative_when)


def test_clash_penalty_yongsin_root_clashed(make_pillars) -> None:
    _, er = _yongsin(make_pillars, *_CLASH)
    assert "yongsin_clash" in er.operability_factors
    assert er.operability == round(1.0 * (1 - OPERABILITY_PENALTY["yongsin_clash"]), 4)
    assert OPERABILITY_FACTOR_SHORT["yongsin_clash"] == "충"
    assert any("충" in s for s in er.negative_when)


def test_no_root_excludes_void_clash(make_pillars) -> None:
    # 통근 없으면 no_root 만 — void/clash 아님(상호배타).
    _, er = _yongsin(make_pillars, *_NOROOT)
    assert "no_root" in er.operability_factors
    assert "yongsin_void" not in er.operability_factors
    assert "yongsin_clash" not in er.operability_factors


def test_helper_targets_only_yongsin_roots(make_pillars) -> None:
    # _yongsin_void_clash_factors 는 용신 통근 지지만 본다(원국 아무 곳 아님).
    std_pillars = make_pillars(*_STD)
    assert _yongsin_void_clash_factors("木", std_pillars) == []   # 未 solid·충無
    void_pillars = make_pillars(*_VOID)
    keys = [k for k, _w in _yongsin_void_clash_factors("木", void_pillars)]
    assert keys == ["yongsin_void"]


def test_factor_order_appended_after_gyeokgak(make_pillars) -> None:
    # 순서 고정: …gyeokgak_zimao→yongsin_void/clash (기존 뒤).
    _, er = _yongsin(make_pillars, *_VOID)
    if "yongsin_void" in er.operability_factors:
        assert er.operability_factors[-1] in ("yongsin_void", "yongsin_clash")


def test_invariance_final_groups_strength(make_pillars) -> None:
    chart = analyze_chart(make_pillars(*_VOID))
    y, force = chart.yongsin, chart.force
    # operability 만 변경 — 모델 선택/역할/세력 불변.
    assert y.final["selected_model"]  # 산출 정상
    assert y.canonical_roles == {
        k: y.final[k] for k in ("yongsin", "heesin", "gisin", "gusin", "hansin")
    }
    assert sum(force.ten_gods.groups.values()) > 0  # groups 산출 정상(차감 없음)
