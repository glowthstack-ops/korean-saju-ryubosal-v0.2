"""결혼·자산 자원 구조 분석 (v2.2, 2026-06-16).

같은 년월일·다른 시주(2021-09-15 午시 vs 卯시, 둘 다 丙火 여성) 비교 사례를 일반화한다 —
시주가 '결과 자원'을 가른다. 자산 출처 경향(부모 기반/배우자 집안/자수성가)·시주 자원 역할·
배우자 별(성별 인지)을 **중립·비단정 구조**로만 산출한다(신규 이벤트 키 없음).

여성: 관성=배우자 본인, **재성=시댁 재력·물질 환경**. 남성: 재성=배우자(처)·물질 환경. 관성이
없어도 재성 환경이 강하면 결혼·가정의 물질 기반이 두드러질 잠재가 있다(실사례 — 관성 0인데
시댁 자산가). 예측이 아니라 해석 맥락이며, 운 발동(합·충·결혼운)에서 현실화된다.
"""

from __future__ import annotations

from saju_manse_analysis.sinsal.sinsal_catalog import HONGYEOM, SAGO, SAJEONG, SASAENG, WONJIN

from saju_shared_types.constants import (
    BRANCH_BREAKS,
    BRANCH_CLASHES,
    BRANCH_ELEMENT,
    BRANCH_HARMS,
    PUNISHMENT_MUTUAL,
    PUNISHMENT_TRIPLES,
    SELF_PUNISHMENT,
    STEM_ELEMENT,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.llm_input import UsefulGods
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

# 일지 본기 십성 그룹 → 끌리는 이상형 타입(경향·비단정 — 영상 자료 A).
_IDEAL_TYPE: dict[str, tuple[str, str]] = {
    "peer": (
        "peer",
        "비겁(대등·독립형) — 친구·동료처럼 맞먹고 자기 앞가림 하는 상대에 끌리는 결(과한 의존·"
        "애교엔 거리감)",
    ),
    "output": (
        "output",
        "식상(표현·꾸밈형) — 자기 관리하고 애정 표현·이벤트가 있는 상대 선호(과묵·무뚝뚝엔 답답함)",
    ),
    "wealth": (
        "wealth",
        "재성(현실 매력형) — 외모·스타일 등 눈에 보이는 매력을 솔직히 중시하는 결(실용·현실형)",
    ),
    "officer": (
        "officer",
        "관성(조건·태도형) — 집안·직업·매너·반듯함을 보는 눈 높은 편(시작은 신중·검증)",
    ),
    "resource": (
        "resource",
        "인성(보살핌형) — 칭찬하고 받아주고 다정한 상대에게 안정감을 느끼는 결",
    ),
}
_GOD_GROUP: dict[str, str] = {
    **{g: "peer" for g in _PEER_GODS}, **{g: "output" for g in _OUTPUT_GODS},
    **{g: "wealth" for g in _WEALTH_GODS}, **{g: "officer" for g in _OFFICER_GODS},
    **{g: "resource" for g in _RESOURCE_GODS},
}
# 십성 그룹 → 짧은 타입어(생애 단계별 연애 대상 서술용 — 영상 자료 B).
_TYPE_SHORT: dict[str, str] = {
    "peer": "대등·독립형", "output": "표현·꾸밈형", "wealth": "현실 매력형",
    "officer": "조건·태도형", "resource": "보살핌형",
}

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


def _day_branch_temperament(branch: Branch) -> tuple[str, str]:
    """일지(배우자궁) 12지지 → 왕지/생지/고지 3분류 + 관계 기질 경향 라벨(비단정).

    왕지(子午卯酉·도화)·생지(寅申巳亥·역마)·고지(辰戌丑未·화개)로 나눠 연애·배우자 관계의
    기질을 중립 경향으로만 표면화한다. 점수·단정 없이 서술 보조로만 쓰며, 미분류면 빈 값.

    Args:
        branch: 일지 지지.

    Returns:
        (group, tendency) — group은 'wangji'/'saengji'/'goji'/''(미분류), tendency는 한글 라벨.
    """
    if branch in SAJEONG:
        return (
            "wangji",
            "왕지(子午卯酉·도화형) — 이성 인연이 잦고 끌림이 빠르나, 익숙해지면 마음이 먼저 "
            "식기 쉬운 결·'내 페이스' 경향",
        )
    if branch in SASAENG:
        return (
            "saengji",
            "생지(寅申巳亥·역마형) — 먼저 다가가 시작은 화려하나 지속·마무리가 약해질 수 있는 "
            "결·변화·이동 지향",
        )
    if branch in SAGO:
        return (
            "goji",
            "고지(辰戌丑未·화개형) — 신중·수동적이고 익숙한 관계를 선호, 걱정·의심이 앞서 "
            "표현이 늦어질 수 있는 결",
        )
    return ("", "")


def _ideal_type(day_branch_main_ten_god: str | None) -> tuple[str, str]:
    """일지 본기 십성 → 끌리는 이상형 타입 그룹·라벨(경향·비단정 — 영상 자료 A).

    Args:
        day_branch_main_ten_god: 일지 지지 본기의 십성(예: '정재').

    Returns:
        (group, tendency) — group은 peer/output/wealth/officer/resource/''(미상), tendency는 라벨.
    """
    group = _GOD_GROUP.get(day_branch_main_ten_god or "", "")
    if not group:
        return ("", "")
    return _IDEAL_TYPE[group]


def _life_stage_ideals(
    year_god: str | None, month_god: str | None, hour_god: str | None,
) -> list[str]:
    """연지/월지/시지 본기 십성 → 생애 단계별 끌리는 연애 대상(경향·비단정 — 영상 자료 B).

    연지=어릴 때(또래·유행) / 월지=사회·원숙기(결혼 적령) / 시지=말년(약하게). 일지(평소 취향)와
    별개의 보조 축이며 시기를 단정하지 않는다(경향으로만).

    Args:
        year_god / month_god / hour_god: 각 지지 본기 십성(없으면 None).

    Returns:
        단계별 라벨 목록(해당 지지 십성이 분류되는 것만).
    """
    out: list[str] = []
    yg = _GOD_GROUP.get(year_god or "", "")
    mg = _GOD_GROUP.get(month_god or "", "")
    hg = _GOD_GROUP.get(hour_god or "", "")
    if yg:
        out.append(f"어릴 때(또래·유행)엔 {_TYPE_SHORT[yg]}에 끌리는 경향")
    if mg:
        out.append(f"사회·원숙기(결혼 적령)엔 {_TYPE_SHORT[mg]}을 현실 파트너로 찾는 경향")
    if hg:
        out.append(f"말년엔 {_TYPE_SHORT[hg]}이 마음을 움직이는 경향(약하게)")
    return out


def _relationship_affinity(p: object, fa: object) -> list[str]:
    """관계 친화·돌봄 성향 — 십성 구조×신강약으로 '관계에 어떻게 임하는가'(경향·비단정·성별 중립).

    영상 자료(여자에게 잘하는 남자 구조)를 성별 무관 '관계 친화도'로 일반화한다 — 식신(케어·표현),
    식상생재(적극), 인성 적정(정·안정, 과다는 단점), 비겁(당당), 신약+비겁 약(회피 주의), 균형
    (누구에게나 맞춤). 본인 자기인식·상대 평가 양용. 점수·단정 없이 경향으로만.

    Args:
        p: pillars(year/month/day/hour).
        fa: force_analysis(ten_gods.groups·strength).

    Returns:
        관계 친화 성향 경향 라벨 목록(해당 신호만).
    """
    out: list[str] = []
    g = fa.ten_gods.groups  # type: ignore[attr-defined]
    out_pct = float(g.get("output", 0.0))
    wlt = float(g.get("wealth", 0.0))
    res = float(g.get("resource", 0.0))
    peer = float(g.get("peer", 0.0))
    band = str(getattr(fa.strength, "band", "") or "")  # type: ignore[attr-defined]
    pillars = [pil for pil in (p.year, p.month, p.day, p.hour) if pil is not None]  # type: ignore[attr-defined]
    md = [pil for pil in (p.month, p.day) if pil is not None]  # type: ignore[attr-defined]
    res_count = sum(
        1 for pil in pillars
        for tg in (pil.stem_ten_god, pil.branch_main_ten_god) if tg in _RESOURCE_GODS
    )
    # 1) 식신 케어형 / 상관 — 월·일지 본기.
    if any(pil.branch_main_ten_god == "식신" for pil in md):
        out.append(
            "식신(월·일지) — 표현·재미·살뜰한 케어가 자연스러운 결(무심하지 않고 관계에 활기)"
        )
    elif any(pil.branch_main_ten_god == "상관" for pil in md):
        out.append(
            "상관(월·일지) — 표현·끼는 좋으나 직설·돌발이 섞일 수 있는 결(말씨를 다듬으면 보완)"
        )
    # 2) 식상생재 — 적극·집중 케어(단 터프함·장기 안정감은 약할 수 있음).
    if out_pct >= 10.0 and wlt >= 10.0:
        out.append(
            "식상생재 — 관심·시간을 들여 타이밍 맞춰 적극적으로 챙기는 결(단, 터프함·장기 "
            "안정감은 약할 수 있음)"
        )
    # 3) 인성 적정/과다 — 정·안정 vs 답답·의존.
    if res >= 35.0 or res_count >= 3:
        out.append(
            "인성 과다 — 익숙함·인정 욕구가 커 다소 답답·의존으로 비칠 수 있는 결(절제로 보완)"
        )
    elif res_count >= 1:
        out.append("인성 적정 — 정·도덕·정착을 중시해 정서적 안정감을 오래 주는 결")
    # 4) 비겁 당당 — 회피 적고 든든.
    if peer >= 10.0:
        out.append("비겁 — 관계에서 당당하고 회피가 적어 든든한 안정감을 주는 결")
    # 5) 신약+비겁 약 + 식상·재성 중심 — 회피·맞춰짐 주의.
    if "약" in band and peer < 10.0 and (out_pct >= 10.0 or wlt >= 10.0):
        out.append(
            "신약·비겁 약 + 식상·재성 중심 — 힘든 일엔 한 발 물러서거나 상대에 맞춰지기 쉬운 "
            "결(의지처가 되어줄 상대와 보완)"
        )
    # 6) 균형 — 누구에게나 맞춰가는 안정적 배우자감.
    if "중" in band:
        out.append(
            "신강약 균형 — 너무 강하지도 약하지도 않아 누구에게나 맞춰가기 좋은 안정적 배우자감"
        )
    return out


def _is_punishment(a: Branch, b: Branch) -> bool:
    """두 지지가 형(刑) 관계인지 — 삼형 부분쌍 또는 무례지형(子卯)."""
    if frozenset({a, b}) in PUNISHMENT_MUTUAL:
        return True
    return any({a, b} <= triple for triple in PUNISHMENT_TRIPLES if a != b)


def _spouse_palace_afflictions(day_b: Branch, others: list[Branch]) -> list[str]:
    """일지(배우자궁)가 원국 내 충/형/원진/파/해(자형 포함)에 관여하는지(영상 자료 F).

    배우자궁 안정도 판정용 — 일지가 다른 기둥 지지와 충·형·원진·파·해를 이루면 관계 내구성이
    약한 경향(이혼수 단정 아님 — 개운·궁합·노력으로 보완 가능). 발견된 살 이름을 우선순위
    순(충>형>원진>파>해)으로 중복 없이 반환한다.

    Args:
        day_b: 일지 지지.
        others: 년·월·시주 지지 목록.

    Returns:
        일지를 흔드는 살 한글명 목록(없으면 빈 목록 = 안정).
    """
    found: set[str] = set()
    for ob in others:
        pair = frozenset({day_b, ob})
        if pair in BRANCH_CLASHES:
            found.add("충")
        if _is_punishment(day_b, ob) or (ob is day_b and day_b in SELF_PUNISHMENT):
            found.add("형")
        if pair in WONJIN:
            found.add("원진")
        if pair in BRANCH_BREAKS:
            found.add("파")
        if pair in BRANCH_HARMS:
            found.add("해")
    order = ["충", "형", "원진", "파", "해"]
    return [name for name in order if name in found]


def analyze_marriage_resource(
    result: ManseV2Result, useful: UsefulGods | None = None,
) -> MarriageResourceProfile:
    """결혼·자산 자원 구조를 판정한다(운 미반영, 성별 인지).

    Args:
        result: 만세 계산 결과(pillars·force_analysis·input_summary 필수).
        useful: 용희기구한(BirthChartSummary.useful_gods). 배우자성=용신 '배우자 덕' 판정에 쓴다.
            미입력이면 spouse_is_yongsin=False로 둔다(graceful).

    Returns:
        MarriageResourceProfile — 배우자 별·재성 위치·이상형 취향·배우자복 품질(중립).
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

    # ── 배우자 인연 결(중립·비낙인 — 궁합 자료 ⑤⑥) ──
    # 배우자 별 과다: 남성 재성 / 여성 관성의 세력(분포≥30% 또는 본기·투간 3곳↑). '바람둥이/
    # 관살혼잡'을 단정하지 않고 '인연 신호가 많아 끌림이 잦은 경향'으로만 본다.
    spouse_group = "officer" if gender == "female" else "wealth"
    spouse_pct = float(groups.get(spouse_group, 0.0))
    spouse_visible_count = sum(
        1
        for pil in all_pillars
        for tg in (pil.stem_ten_god, pil.branch_main_ten_god)
        if tg in spouse_gods
    )
    spouse_star_excess = spouse_pct >= 30.0 or spouse_visible_count >= 3
    spouse_star_absent = not spouse_star_present
    # 도화(사정지 子午卯酉)·홍염(일간→지지) — 이성에게 매력적으로 비치는 끌림 경향.
    day_master = Stem(day_pillar.stem)
    branch_objs = [Branch(pil.branch) for pil in all_pillars]
    charm_present = (
        any(b in SAJEONG for b in branch_objs)
        or HONGYEOM.get(day_master) in branch_objs
    )

    # 배우자궁(일지) 기질 — 왕지/생지/고지 3분류(경향·비단정).
    day_branch_group, day_branch_tendency = _day_branch_temperament(Branch(day_pillar.branch))
    # A) 일지 십성 이상형 — 일지 본기 십성 → 끌리는 타입(경향).
    day_branch_ten_god_group, ideal_type_tendency = _ideal_type(day_pillar.branch_main_ten_god)
    # B) 생애 단계별 연애 대상 — 연지/월지/시지 본기 십성(경향·시기 단정 아님).
    life_stage_ideals = _life_stage_ideals(
        p.year.branch_main_ten_god if p.year else None,
        p.month.branch_main_ten_god if p.month else None,
        p.hour.branch_main_ten_god if p.hour else None,
    )
    # 관계 친화·돌봄 성향 — 십성 구조×신강약(경향·비단정·성별 중립).
    relationship_affinity = _relationship_affinity(p, fa)

    # E) 배우자별 하나·튼튼 — 정확히 1개 드러남(깔끔) + 지지 본기에 뿌리(튼튼).
    spouse_star_clean = (
        spouse_star_present and spouse_visible_count == 1 and not spouse_star_excess
    )
    spouse_star_rooted = any(
        pil.branch_main_ten_god in spouse_gods for pil in all_pillars
    )

    # F) 배우자궁(일지) 안정도 — 충/형/원진/파/해 관여 여부.
    day_b = Branch(day_pillar.branch)
    other_branches = [
        Branch(pil.branch) for pil in (p.year, p.month, p.hour) if pil is not None
    ]
    spouse_palace_afflictions = _spouse_palace_afflictions(day_b, other_branches)
    spouse_palace_stable = not spouse_palace_afflictions

    # G) 배우자성=용신 → 배우자 덕. 배우자성 오행(남=재성·여=관성)이 용·희신이면 True.
    officer_el = _inverse(_CONTROLS, day_el)  # 일간을 극하는 오행 = 관성
    spouse_star_el = officer_el if gender == "female" else wealth_el
    spouse_is_yongsin = bool(
        useful is not None
        and spouse_star_el in (set(useful.yongsin) | set(useful.heesin))
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

    # 배우자 별 과다 라벨 — 성별 인지·비낙인(경향·가능성으로만, 단정 금지).
    if gender == "male":
        excess_label = "재성(이성·물질) 강 — 새 자극·인연에 끌리는 경향(호기심 큰 결, 단정 아님)"
    elif gender == "female":
        excess_label = "관성(이성·인연) 많음 — 인연 신호가 복잡한 결(관살혼잡 경향·단정 아님)"
    else:
        excess_label = "배우자 별 세력 강 — 이성·인연 신호가 두드러지는 결"
    absent_label = f"{spouse_star} 미투출 — 인연을 스스로 만들어가는 능동형(부재 단정 아님)"
    labels = [
        (spouse_star_present, f"{spouse_star} 존재(배우자 신호)"),
        (spouse_star_absent, absent_label),
        (spouse_star_excess, excess_label),
        (charm_present, "도화·홍염 — 이성에게 매력적으로 비치고 끌림이 잦은 경향"),
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
        spouse_star_excess=spouse_star_excess,
        spouse_star_absent=spouse_star_absent,
        charm_present=charm_present,
        day_branch_group=day_branch_group,
        day_branch_tendency=day_branch_tendency,
        day_branch_ten_god_group=day_branch_ten_god_group,
        ideal_type_tendency=ideal_type_tendency,
        life_stage_ideals=life_stage_ideals,
        relationship_affinity=relationship_affinity,
        spouse_star_clean=spouse_star_clean,
        spouse_star_rooted=spouse_star_rooted,
        spouse_palace_stable=spouse_palace_stable,
        spouse_palace_afflictions=spouse_palace_afflictions,
        spouse_is_yongsin=spouse_is_yongsin,
        hour_resource_role=hour_role,
        wealth_source_leans=leans,
        flags=flags,
    )
