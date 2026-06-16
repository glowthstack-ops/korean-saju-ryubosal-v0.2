"""부(富)/귀(貴) 지향 분석 (v2.2, 2026-06-16).

격국 격신 그룹과 재성/관성 분포로 '사주가 부로 가느냐 귀로 가느냐'를 도출한다. 격신이 재성·식상
(재물 생산)이면 부 지향, 관성·인성(관인상생, 조직·명예)이면 귀 지향. 재성>관성이면 부, 관성>재성
이면 귀로 분포가 보강한다. **우열·단정이 아니라 결의 방향**이며 운·선택으로 달라질 수 있다.
"""

from __future__ import annotations

from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.wealth_status_lean import WealthStatusLean

# 십성 → 격신 그룹.
_TEN_GOD_GROUP = {
    "정재": "wealth", "편재": "wealth", "식신": "output", "상관": "output",
    "정관": "officer", "편관": "officer", "정인": "resource", "편인": "resource",
    "비견": "peer", "겁재": "peer",
}
_WEALTH_LEAN_GROUPS = {"wealth", "output"}  # 재격·식상생재 → 부
_STATUS_LEAN_GROUPS = {"officer", "resource"}  # 관격·관인상생 → 귀

_NOTE = {
    "부": "실리·재물·전문성 중심으로 풀리기 쉬운 결 — 조직 명예보다 결과·자산·기술로 평가받는 길"
          "(사업·전문·성과형). 우열이 아니라 방향.",
    "귀": "명예·조직·지위 중심으로 풀리기 쉬운 결 — 관직·제도권·일반 경쟁에서 두각"
          "(조직·공직·관리형). 우열이 아니라 방향.",
    "부귀겸전": "재물과 명예를 겸할 잠재 — 재성·관성이 함께 받쳐주는 결.",
    "뚜렷하지 않음": "부·귀 어느 쪽으로도 뚜렷하지 않음 — 운·선택에 따라 결이 정해지는 구조.",
}


def analyze_wealth_status_lean(result: ManseV2Result) -> WealthStatusLean:
    """원국의 부/귀 지향을 판정한다(격국 격신 + 재/관 분포).

    Args:
        result: 만세 계산 결과(geokguk·force_analysis 필수).

    Returns:
        WealthStatusLean — 부/귀/부귀겸전/뚜렷하지 않음 + 격국·분포 근거.
    """
    assert result.force_analysis is not None
    fa = result.force_analysis
    geokguk = result.geokguk

    geokguk_name = ""
    group = ""
    if geokguk is not None:
        geokguk_name = geokguk.main_structure or ""
        main_god = (geokguk.basis or {}).get("main_ten_god", "")
        group = _TEN_GOD_GROUP.get(main_god, "")

    groups = fa.ten_gods.groups
    wealth_pct = float(groups.get("wealth", 0.0))
    officer_pct = float(groups.get("officer", 0.0))

    score_wealth = (1 if group in _WEALTH_LEAN_GROUPS else 0) + (
        1 if wealth_pct >= officer_pct + 5.0 else 0
    )
    score_status = (1 if group in _STATUS_LEAN_GROUPS else 0) + (
        1 if officer_pct >= wealth_pct + 5.0 else 0
    )

    if score_wealth >= 1 and score_status >= 1 and wealth_pct >= 15 and officer_pct >= 15:
        lean = "부귀겸전"
    elif score_wealth > score_status:
        lean = "부"
    elif score_status > score_wealth:
        lean = "귀"
    else:
        lean = "뚜렷하지 않음"

    flags = []
    if group:
        flags.append(f"격신 {group}")
    flags.append(f"재성 {wealth_pct:.0f}% · 관성 {officer_pct:.0f}%")

    return WealthStatusLean(
        lean=lean,
        geokguk_name=geokguk_name,
        geokguk_group=group,
        wealth_pct=wealth_pct,
        officer_pct=officer_pct,
        note=_NOTE.get(lean, ""),
        flags=flags,
    )
