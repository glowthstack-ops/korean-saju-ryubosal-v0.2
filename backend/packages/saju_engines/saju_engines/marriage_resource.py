"""결혼·자산 자원 구조 분석 (v2.2, 2026-06-16).

같은 년월일·다른 시주(2021-09-15 午시 vs 卯시, 둘 다 丙火 여성) 비교 사례를 일반화한다 —
시주가 '결과 자원'을 가른다. 자산 출처 경향(부모 기반/배우자 집안/자수성가)·시주 자원 역할·
배우자 별(성별 인지)을 **중립·비단정 구조**로만 산출한다(신규 이벤트 키 없음).

여성: 관성=배우자 본인, **재성=시댁 재력·물질 환경**. 남성: 재성=배우자(처)·물질 환경. 관성이
없어도 재성 환경이 강하면 결혼·가정의 물질 기반이 두드러질 잠재가 있다(실사례 — 관성 0인데
시댁 자산가). 예측이 아니라 해석 맥락이며, 운 발동(합·충·결혼운)에서 현실화된다.
"""

from __future__ import annotations

from saju_shared_types.constants import BRANCH_ELEMENT, STEM_ELEMENT
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.marriage_resource import MarriageResourceProfile

# 오행 상생/상극.
_GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
_CONTROLS = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
# 지지 6충 쌍.
_CLASH_PAIRS = (
    {"子", "午"}, {"丑", "未"}, {"寅", "申"}, {"卯", "酉"}, {"辰", "戌"}, {"巳", "亥"},
)
_WEALTH_GODS = {"편재", "정재"}
_OFFICER_GODS = {"편관", "정관"}
_RESOURCE_GODS = {"편인", "정인"}
_OUTPUT_GODS = {"식신", "상관"}
_PEER_GODS = {"비견", "겁재"}

# 시주 천간 십성 → 자원 역할(중립 라벨).
_HOUR_ROLE = {
    "정재": "결혼 후·결과 자리의 재물 자원", "편재": "결혼 후·결과 자리의 유동 재물 자원",
    "정인": "보호·지원(인성) 자원", "편인": "보호·지원(인성) 자원",
    "비견": "자립·생활력 자원", "겁재": "자립·생활력 자원",
    "정관": "사회·배우자 연결 자원", "편관": "사회·배우자 연결 자원",
    "식신": "표현·산출 자원", "상관": "표현·산출 자원",
}


def _inverse(table: dict[str, str], target: str) -> str:
    """상생/상극 역방향 — table[e] == target 인 e(없으면 빈 문자열)."""
    return next((e for e, v in table.items() if v == target), "")


def analyze_marriage_resource(result: ManseV2Result) -> MarriageResourceProfile:
    """결혼·자산 자원 구조 6요소를 판정한다(운 미반영, 성별 인지).

    Args:
        result: 만세 계산 결과(pillars·force_analysis·input_summary 필수).

    Returns:
        MarriageResourceProfile — 배우자 별·재성 위치·자원 역할·자산 출처 경향(중립).
    """
    assert result.pillars is not None
    assert result.force_analysis is not None
    p = result.pillars
    fa = result.force_analysis
    day_pillar = p.day
    assert day_pillar is not None

    gender = str(result.input_summary.get("gender", "unknown"))
    day_el = str(STEM_ELEMENT[Stem(day_pillar.stem)])
    wealth_el = _CONTROLS[day_el]  # 일간이 극하는 오행 = 재성

    family = [pil for pil in (p.year, p.month) if pil is not None]  # 부모·집안 자리
    hour = p.hour
    all_pillars = [pil for pil in (p.year, p.month, p.day, p.hour) if pil is not None]

    def _has_god(pillars: list, gods: set[str]) -> bool:
        """천간·지지 본기·지장간 중 어디든 해당 십성이 있으면 True(재성 뿌리·환경용)."""
        return any(
            pil.stem_ten_god in gods
            or pil.branch_main_ten_god in gods
            or any(h.ten_god in gods for h in pil.hidden_stems)
            for pil in pillars
        )

    def _has_visible(pillars: list, gods: set[str]) -> bool:
        """천간·지지 본기에만 있으면 True(지장간 제외 — '드러난' 신호 판정용)."""
        return any(
            pil.stem_ten_god in gods or pil.branch_main_ten_god in gods
            for pil in pillars
        )

    # 여성=관성(배우자 본인) / 남성=재성(배우자·물질). 배우자 별은 '드러난(투간·본기)' 것만
    # 센다 — 지장간에만 있으면 약/잠복으로 보아 부재 처리(관성 약해도 재성 환경은 별도로 본다).
    spouse_star = "관성" if gender == "female" else "재성"
    spouse_gods = _OFFICER_GODS if gender == "female" else _WEALTH_GODS
    spouse_star_present = _has_visible(all_pillars, spouse_gods)

    wealth_in_family_palace = _has_god(family, _WEALTH_GODS)
    wealth_in_result_palace = bool(hour is not None and _has_god([hour], _WEALTH_GODS))

    # 재성 세력 강 — 분포 비중(>=22%) 또는 자리 반복(>=3곳).
    groups = fa.ten_gods.groups
    wealth_pct = float(groups.get("wealth", 0.0))
    wealth_count = sum(
        1
        for pil in all_pillars
        for tg in (pil.stem_ten_god, pil.branch_main_ten_god)
        if tg in _WEALTH_GODS
    )
    wealth_strong = wealth_pct >= 22.0 or wealth_count >= 3

    # 보호받는 구조 — 인성 존재 + 일간 뿌리(비겁/인성 root).
    has_resource = _has_god(all_pillars, _RESOURCE_GODS)
    rooted = any(
        r.root_kind in ("primary_root", "resource_root") for r in fa.rooting.roots
    )
    resource_support = has_resource and rooted

    # 재성 지지가 원국 충에 관여 — 발동·변화 잠재(卯酉충이 재성 酉를 건드리는 류).
    branches = [pil.branch for pil in all_pillars]
    wealth_palace_clash = any(
        pair <= set(branches)
        and any(str(BRANCH_ELEMENT[Branch(b)]) == wealth_el for b in pair)
        for pair in _CLASH_PAIRS
    )

    hour_role = ""
    if hour is not None and hour.stem_ten_god:
        hour_role = _HOUR_ROLE.get(hour.stem_ten_god, "")

    # 자산 출처 경향(중립·가능성, 중복 가능).
    leans: list[str] = []
    if wealth_in_family_palace and resource_support:
        leans.append("parental")  # 부모·집안 기반(년월 재성 + 보호 구조)
    if wealth_strong and wealth_in_result_palace:
        leans.append("spouse_family")  # 결혼 후·결과 자리 재성 환경(여성: 시댁 재력 잠재)
    if _has_god(all_pillars, _OUTPUT_GODS) and (
        wealth_in_family_palace or wealth_in_result_palace
    ):
        leans.append("self")  # 식상생재 — 자수성가 경향

    labels = [
        (spouse_star_present, f"{spouse_star} 존재(배우자 신호)"),
        (wealth_in_family_palace, "재성 년월(집안·초년 기반)"),
        (wealth_in_result_palace, "재성 시주(결혼 후·결과 자원)"),
        (wealth_strong, "재성 세력 강"),
        (resource_support, "인성·뿌리 보호 구조"),
        (wealth_palace_clash, "재성궁 충(발동·변화 잠재)"),
    ]
    flags = [label for ok, label in labels if ok]

    return MarriageResourceProfile(
        gender=gender,
        wealth_element=wealth_el,
        spouse_star=spouse_star,
        spouse_star_present=spouse_star_present,
        wealth_in_family_palace=wealth_in_family_palace,
        wealth_in_result_palace=wealth_in_result_palace,
        wealth_strong=wealth_strong,
        resource_support=resource_support,
        wealth_palace_clash=wealth_palace_clash,
        hour_resource_role=hour_role,
        wealth_source_leans=leans,
        flags=flags,
    )
