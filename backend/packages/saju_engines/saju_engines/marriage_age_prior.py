"""MT6 — 배우자성 위치별 혼기(婚期) static prior (v2.2, 2026-06-30).

영상 자료(관 투출 위치 → 혼기 경향): 배우자성(여=관살·남=재성)이 어느 기둥에 드러나는가로 넓은
혼기창 경향을 본다(MARRIAGE_TIMING_ENHANCEMENT §11). **event trigger가 아니라 static prior**다 —
특정 연·월을 발동시키지 않고, "언제 결혼?" 광역 질의의 기본 창·stage threshold 보정에만 쓴다.

**완전 inert 분석기**: event_engine·MarriageResourceProfile을 건드리지 않는다(기존 출력 불변).
호출되기 전까지 아무 영향이 없으며, topic builder 배선은 별도 단계다. 드러난 것(천간 투간+지지
본기)만 세고 지장간 잠복은 제외한다. gender 미상이면 관살·재성 양 기준을 병기하되 confidence를
낮추고 threshold 보정에는 쓰지 않는다(설명 참고만). 단정 금지 — 약한 prior다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from saju_shared_types.manse_result import ManseV2Result

# 성별별 배우자성 십성(드러난 것만). 미상은 양 기준 병기.
_PARTNER_GODS: dict[str, frozenset[str]] = {
    "female": frozenset({"정관", "편관"}),
    "male": frozenset({"정재", "편재"}),
}
# 기둥 우선순위(가장 이른 자리) + 위치별 혼기 band.
_PILLAR_ORDER = ("year", "month", "day", "hour")
_POSITION_BAND: dict[str, str] = {
    "year": "early",                   # 이른 인연
    "month": "normal",                 # 사회 초·중반(적령)
    "day": "spouse_palace_direct",     # 배우자궁 직접(본인 주도)
    "hour": "late",                    # 만혼 경향
}


class MarriageAgePrior(BaseModel):
    """배우자성 위치 기반 혼기 static prior (event 아님)."""

    positions: list[str] = Field(default_factory=list)  # 배우자성 드러난 자리
    band: str = "unknown"  # early|normal|spouse_palace_direct|late|unknown
    structural_flags: list[str] = Field(default_factory=list)  # 예: spouse_palace_direct
    role: str = "static_prior"
    triggers_event: bool = False  # 고정 — 특정 연·월 발동 금지
    confidence: str = "normal"  # normal|low(gender 미상)
    usable_for_threshold: bool = False  # gender 미상·band unknown이면 False(설명 참고만)
    note: str = ""


def _headline_band(positions: list[str]) -> str:
    """드러난 자리들 중 가장 이른 기둥의 band(없으면 unknown)."""
    for pos in _PILLAR_ORDER:
        if pos in positions:
            return _POSITION_BAND[pos]
    return "unknown"


def analyze_marriage_age_prior(result: ManseV2Result) -> MarriageAgePrior:
    """배우자성이 드러난 기둥 → 혼기 static prior를 산출한다(event 아님·비단정).

    Args:
        result: 만세 결과(pillars 필요). input_summary.gender로 배우자성 기준 결정.

    Returns:
        MarriageAgePrior — 드러난 자리·headline band·구조 flag·신뢰도. pillars 부재 시 band=unknown.
    """
    if result.pillars is None:
        return MarriageAgePrior(note="원국 부재 — prior 산출 불가")
    p = result.pillars
    gender = str(result.input_summary.get("gender", "unknown"))
    known = gender in ("female", "male")
    gods = _PARTNER_GODS[gender] if known else (_PARTNER_GODS["female"] | _PARTNER_GODS["male"])

    positions: list[str] = []
    for pos in _PILLAR_ORDER:
        pil = getattr(p, pos, None)
        if pil is None:
            continue
        # 드러난 것만 — 천간 투간 + 지지 본기(지장간 잠복 제외).
        if pil.stem_ten_god in gods or pil.branch_main_ten_god in gods:
            positions.append(pos)

    band = _headline_band(positions)
    structural_flags = ["spouse_palace_direct"] if "day" in positions else []
    confidence = "normal" if known else "low"
    usable = known and band != "unknown"
    if not positions:
        note = "배우자성 미투출 — 혼기 prior 침묵(다른 신호에 위임)"
    elif known:
        note = f"배우자성 드러난 자리 {positions} 기준 약한 혼기 경향(단정 아님)"
    else:
        note = "성별 미상으로 관살/재성 양 기준을 병기한 약한 prior(threshold 보정 미사용)"

    return MarriageAgePrior(
        positions=positions,
        band=band,
        structural_flags=structural_flags,
        confidence=confidence,
        usable_for_threshold=usable,
        note=note,
    )
