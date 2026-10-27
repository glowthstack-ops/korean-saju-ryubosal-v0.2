"""외적 인상·매력 신호 판정 (External Impression Engine, v1, 2026-07-01).

SSOT: ``doc/v2_2/EXTERNAL_IMPRESSION_SIGNAL.md``. 원국 구조(운 미반영)에서 외적 인상·분위기·표현
매력·관계적 끌림 신호를 **가중 스코어**로 판정한다. **미인 판정이 아니며**, 이미 계산된 분포·신살·
간지만 조회한다(신규 명리 계산 금지, 절대원칙 1). 노출 게이트(intent allowlist·gender)는 표면화
계층(``structural_context.external_impression_lines``)이 담당하고, 본 엔진은 신호·스코어만 낸다.

핵심 조건(자막 복원 → 현대 재해석):
- 금수상관(일간 金 + 원국 水): 관성 있으면 full(품격·호감), 없으면 약신호(청량·표현).
- 식상 왕성: 표정·리액션·자기표현 매력(남녀 공통, 원문은 여성중심 legacy).
- 도화계(2026-10-13 D안, 데굴님 확정): 일지 진도화(강 1.2) / 일지 외 진도화·홍염(1.0, 같은 진도화
  중복 가산 없음). 子午卯酉 글자 보유(사정지)는 매력 점수에서 제외 — 성향 설명 전용.
- 화기 왕성: 밝음·생기·무대성(남녀 공통, legacy).
- 寅·亥: 생동감/부드러움 — 보조 톤(단독 노출 금지).
"""

from __future__ import annotations

from saju_manse_analysis.sinsal.sinsal_catalog import HONGYEOM

from saju_shared_types.constants import BRANCH_ELEMENT, STEM_ELEMENT
from saju_shared_types.enums import Branch, Element, Stem
from saju_shared_types.external_impression import (
    ExternalImpressionProfile,
    ExternalImpressionSignal,
)
from saju_shared_types.manse_result import ManseV2Result

from .dohwa import analyze_dohwa

_YIN_HAI: frozenset[Branch] = frozenset({Branch.IN, Branch.HAE})  # 寅·亥
_OFFICER_GODS = frozenset({"정관", "편관"})

# 임계(잠정값 — 회귀 픽스처로 튜닝, SSOT §2).
_OUTPUT_MIN = 18.0   # 식상 표현 매력 하한(분포율 %)
_OUTPUT_OVER = 35.0  # 식상 과다(호불호) 경계
_FIRE_MIN = 25.0     # 화기 왕성 하한(분포율 % 또는 계절보정)


def _pillars(result: ManseV2Result) -> list:
    """원국 4주(존재하는 것만) 목록."""
    p = result.pillars
    assert p is not None
    return [pil for pil in (p.year, p.month, p.day, p.hour) if pil is not None]


def _water_present(pillars: list) -> bool:
    """원국에 水가 드러나 있는가(금수상관 성립의 '물을 봤다') — 천간·지지 오행 기준."""
    for pil in pillars:
        if STEM_ELEMENT[Stem(pil.stem)] is Element.WATER:
            return True
        if BRANCH_ELEMENT[Branch(pil.branch)] is Element.WATER:
            return True
    return False


def _officer_visible(pillars: list) -> bool:
    """관성(정관·편관)이 천간·지지 본기에 드러나 있는가('관을 봤다')."""
    return any(
        pil.stem_ten_god in _OFFICER_GODS or pil.branch_main_ten_god in _OFFICER_GODS
        for pil in pillars
    )


def analyze_external_impression(result: ManseV2Result) -> ExternalImpressionProfile:
    """외적 인상·매력 신호를 판정한다(운 미반영, 원국 구조·성별 인지).

    이미 계산된 오행·십성 분포와 지지·신살만 조회한다(신규 계산 금지). 가중 스코어와 band를
    산출하며, 실제 노출 여부·문구는 표면화 계층이 결정한다(미해당 시 완전 무언급 보장).

    Args:
        result: 만세 계산 결과(pillars·force_analysis·input_summary 필수).

    Returns:
        ExternalImpressionProfile — 매칭 신호·스코어·band·is_notable·confidence.
    """
    gender = str(result.input_summary.get("gender", "unknown"))
    if result.pillars is None or result.force_analysis is None:
        return ExternalImpressionProfile(
            gender=gender, confidence="low" if gender not in ("female", "male") else "normal"
        )

    p = result.pillars
    fa = result.force_analysis
    day_pillar = p.day
    assert day_pillar is not None
    pillars = _pillars(result)

    day_stem = Stem(day_pillar.stem)
    day_el = STEM_ELEMENT[day_stem]
    day_branch = Branch(day_pillar.branch)
    all_branches = {Branch(pil.branch) for pil in pillars}

    ten_groups = fa.ten_gods.groups
    elem_env = fa.five_elements.distribution_environment
    elem_sa = fa.five_elements.season_adjusted_element_strength
    strongest_el = fa.five_elements.strongest_element
    deficient = set(fa.five_elements.deficient_elements)

    signals: list[ExternalImpressionSignal] = []
    legacy_used = False

    # C1) 금수상관 — 일간 金 + 원국 水. 관성 있으면 full(primary 1.0), 없으면 약(secondary 0.5).
    if day_el is Element.METAL and _water_present(pillars):
        if _officer_visible(pillars):
            signals.append(ExternalImpressionSignal(
                code="METAL_WATER_OFFICER", category="metal_water",
                legacy_ko="금수상관 + 관성",
                modern_ko="말투·분위기·인상이 맑고 세련되게 보이는 구조. 관성이 받쳐줘 튐보다 "
                          "정돈감·품격이 더해져 사회적 호감으로 이어지기 쉬운 결",
                weight=1.0, tier="primary",
            ))
        else:
            signals.append(ExternalImpressionSignal(
                code="METAL_WATER_EXPRESSION", category="metal_water",
                legacy_ko="금수상관(관성 약)",
                modern_ko="청량감·세련된 말투·맑고 정돈된 분위기 경향(단독 근거로는 약함)",
                weight=0.5, tier="secondary",
            ))

    # C2) 식상 왕성 — 표현 매력(남녀 공통, 원문 여성중심 legacy).
    output_pct = float(ten_groups.get("output", 0.0))
    if output_pct >= _OUTPUT_MIN:
        legacy_used = True
        over = output_pct > _OUTPUT_OVER
        signals.append(ExternalImpressionSignal(
            code="OUTPUT_EXPRESSION", category="output",
            legacy_ko="식상 왕성",
            modern_ko="표정·말·리액션·스타일링처럼 자신을 드러내는 방식이 눈에 띄는 결(외모 "
                      "자체보다 '표현 매력'·콘텐츠성 있는 인상)",
            weight=0.8, tier="primary",
            note="표현이 강해 호불호가 생길 수 있음" if over else "",
        ))

    # 도화계 — 진도화(연지·일지 삼합국 년살 성립)만 매력 점수에 쓴다(2026-10-13 D안). 글자 보유
    # (사정지 子午卯酉)는 성향 설명 전용이라 점수에서 뺐다. 기존 1.2·1.0 수치를 재사용했다는
    # 사실만으로 가중 타당성이 확보되는 것은 아니며, 후보 비교(scripts/compare_dohwa_consumers.py)
    # 에서 글자 신호를 모두 뺀 D안이 채택됐다.
    dohwa = analyze_dohwa(result)
    established = dohwa.established if dohwa is not None else []
    day_jin = any(e.position == "day" for e in established)
    other_jin = any(e.position != "day" for e in established)

    # C3) 일지 진도화 — 관계 장면에서 기억되는 인상(강, primary 1.2).
    if day_jin:
        signals.append(ExternalImpressionSignal(
            code="DAY_BRANCH_PEACH", category="peach",
            legacy_ko="일지 도화(진도화)",
            modern_ko="가까운 관계 안에서 인상이 쉽게 남고 상대가 호기심을 느끼기 쉬운 구조(관계적 "
                      "끌림 신호이며 외모 단정 아님)",
            weight=1.2, tier="primary",
        ))

    # C4a) 일지 외 진도화·홍염 — 시선·호기심을 끄는 분위기(primary 1.0). 일지 진도화는 C3 에서
    # 이미 셌으므로 여기서 다시 세지 않는다(같은 진도화 중복 가산 금지).
    hongyeom = HONGYEOM.get(day_stem)
    if other_jin or (hongyeom is not None and hongyeom in all_branches):
        signals.append(ExternalImpressionSignal(
            code="ACTUAL_DOHWA_OR_HONGYEOM", category="peach",
            legacy_ko="도화·홍염",
            modern_ko="사람들의 시선이나 호기심을 끄는 분위기 경향",
            weight=1.0, tier="primary",
        ))

    # C5) 화기 왕성 — 밝음·생기·무대성(남녀 공통, legacy). 심하게 손상(부족)되지 않은 火.
    fire_str = str(Element.FIRE)
    fire_visible = (
        float(elem_env.get(fire_str, 0.0)) >= _FIRE_MIN
        or float(elem_sa.get(fire_str, 0.0)) >= _FIRE_MIN
        or strongest_el == fire_str
    ) and fire_str not in deficient
    if fire_visible:
        legacy_used = True
        signals.append(ExternalImpressionSignal(
            code="FIRE_VISIBILITY", category="fire",
            legacy_ko="화기 왕성",
            modern_ko="밝음·생기·표정·색감·무대성이 살아나는 결(사진·영상·대면에서 존재감이 "
                      "드러나는 타입)",
            weight=0.8, tier="primary",
        ))

    # C6) 寅·亥 — 생동감/부드러움 보조 톤(단독 노출 금지). 일지(0.5) 우선, 아니면 년·월지(0.2).
    if day_branch in _YIN_HAI:
        # 있는 글자만 적는다 — 종전 "寅은 …, 亥는 …" 병기 문장은 寅이 없는 명식에도 寅을 노출해
        # LLM 이 寅을 명식 사실로 쓸 여지가 있었다(2026-10-26 실답 己亥 일주).
        _glyph, _tone = (
            ("寅", "생동감·신선함") if day_branch is Branch.IN else ("亥", "부드러움·깊이감")
        )
        signals.append(ExternalImpressionSignal(
            code="YIN_HAI_DAY", category="yinhai",
            legacy_ko=f"일지 {_glyph}",
            modern_ko=f"일지 {_glyph} — {_tone}의 인상 톤을 보조",
            weight=0.5, tier="secondary",
        ))
    elif any(
        Branch(pil.branch) in _YIN_HAI for pil in (p.year, p.month) if pil is not None
    ):
        signals.append(ExternalImpressionSignal(
            code="YIN_HAI_OTHER", category="yinhai",
            legacy_ko="년·월지 寅·亥",
            modern_ko="생동감·부드러움의 은근한 인상 톤(보조)",
            weight=0.2, tier="secondary",
        ))

    # 부가(note-only, 스코어·카운트 제외) — 木 왕성: '머리숱' 직접 표현 금지, 완곡 참고만.
    wood_str = str(Element.WOOD)
    if float(elem_env.get(wood_str, 0.0)) >= _FIRE_MIN or strongest_el == wood_str:
        signals.append(ExternalImpressionSignal(
            code="WOOD_TONE", category="note",
            legacy_ko="목기 왕성",
            modern_ko="목기의 생기·성장감·부드러운 선·관리된 인상으로 볼 수 있는 결",
            weight=0.0, tier="note",
        ))

    # 스코어·카운트 — note tier 제외.
    scored = [s for s in signals if s.tier != "note"]
    score = round(sum(s.weight for s in scored), 4)
    primary_count = sum(1 for s in scored if s.tier == "primary")
    category_count = len({s.category for s in scored})

    gated = primary_count >= 1 and category_count >= 2
    if gated and score >= 2.8:
        band = "strong"
    elif gated and score >= 1.8:
        band = "notable"
    elif score >= 1.0:
        band = "weak"
    else:
        band = "none"
    is_notable = band in ("notable", "strong")

    return ExternalImpressionProfile(
        gender=gender,
        signals=signals,
        score=score,
        primary_signal_count=primary_count,
        category_count=category_count,
        band=band,
        is_notable=is_notable,
        legacy_female_centric_used=legacy_used,
        confidence="low" if gender not in ("female", "male") else "normal",
    )
