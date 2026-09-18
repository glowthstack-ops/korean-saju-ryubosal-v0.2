"""운(運) 합에 의한 흉신 완화·관운 강화 판정 — 월 등급·이벤트 유불리·프롬프트가 공유하는 SSOT.

배경(2026-09-18 데굴님 지시, 전문가 반박 사례 — 데굴 차트 2027-02 壬寅월):
- 엔진 관계 층은 이미 丁壬合을 '합화 확정·化木', 寅亥合을 '합반·합거(away) · 壬 구신 boon ·
  甲 기신 boon'으로 판정하고 있었다. 그러나 월 품질 등급(luck_cycles._luck_label)과 이벤트
  결과 유불리(event_engine_v2._period_role)는 운 글자의 원값 역할만 읽어 '강한 기신운·불리'로
  냈고, 프롬프트에는 합 판정이 실리지 않아 LLM이 알 수 없었다.
- 전문가 요약: **"기신의 작용을 누르고 관운의 강화"**, 단 "제거보다는 원래 가지고 있던 지병의
  완화 느낌". → 묶인 흉 글자의 흉을 없애지 않고 **한 단계 낮춘다**(잔존 약흉). 합/합화의 결과
  오행이 관(官, 일간을 극하는 오행)이면 관 계열 사건(이직·취업·승진)의 결과 유불리를 보강한다.
- 기존 천간 합거(event_engine_v2._target_stem_bound)는 흉을 통째로 건너뛰었다. 전문가 취지대로
  천간도 '완화'로 통일한다(데굴님 확정 2026-09-18) — 플래그 ON일 때 길흉 채널에서만,
  OFF는 기존 byte 유지.

이 모듈은 판정만 한다(가중치 적용은 소비처 각자). 판정 조건:
- 천간 완화: 운 천간이 기·구신이고, 원국 천간과의 천간합이 합반(bind)·합거(direction 'away')
  이며 그 운 천간 자신이 boon(흉 제거) 대상으로 잡힐 때.
- 지지 완화: 운 지지가 기·구신이고, 원국 지지와의 **육합**이 합반(bind)·합거(away)이며
  affected 중 boon이 있을 때(운 지지가 원국 흉신 지지를 묶는 경우 — 寅亥合의 亥 정재·구신).
  삼합·방합은 '묶임'이 아니라 국(局) 강화라 대상이 아니다(보수적).
- 관운 강화 재료: 위 합(천간 합화 확정 포함)의 결과 오행이 관이면 그 오행을 officer_elements에
  담는다. 엔진이 化 불성(bind)으로 본 합도 포함한다 — 전문가는 寅亥合木의 '木 작용'을 관운으로
  읽었고, 그 취지가 승인됐다.
"""

from __future__ import annotations

from dataclasses import dataclass

from saju_shared_types.constants import BRANCH_ELEMENT, CONTROLS, STEM_ELEMENT
from saju_shared_types.enums import Branch, Element, Stem
from saju_shared_types.pillars import FourPillarsResult

from .hap_modes import (
    _BOON_WHEN_BOUND,
    BranchHapResolution,
    StemHapResolution,
    resolve_branch_hap,
    resolve_stem_hap,
)


@dataclass(frozen=True)
class HapMitigation:
    """운 간지 1건의 합 완화 판정 — 판정만 담고 가중치는 담지 않는다."""

    stem_mitigated: bool = False  # 운 천간(흉신)이 천간합 합거로 묶임 → 흉 한 단계 완화
    branch_mitigated: bool = False  # 운 지지(흉신)가 육합 합거로 묶임 → 흉 한 단계 완화
    officer_elements: tuple[str, ...] = ()  # 합/합화 결과 오행 중 관(官)인 것(관운 강화 재료)
    notes: tuple[str, ...] = ()  # 서술용 짧은 표지('지지 寅亥合 합거 — 亥 정재·구신 완화' 등)

    @property
    def any(self) -> bool:
        """완화 또는 관운 강화 재료가 하나라도 있으면 True."""
        return self.stem_mitigated or self.branch_mitigated or bool(self.officer_elements)


def officer_element(day_master: str) -> str:
    """일간을 극하는 오행(관성 오행)의 한자 — 己 → 木."""
    dm_el = STEM_ELEMENT[Stem(day_master)]
    return next(str(x) for x in Element if CONTROLS[x] == dm_el)


def _stem_part(
    pillars: FourPillarsResult, favorability: dict[str, str], luck_stem: str, officer: str,
) -> tuple[bool, list[str], list[str]]:
    """운 천간 판정 → (완화 여부, 관운 강화 오행 목록, 표지)."""
    try:
        stem_el = str(STEM_ELEMENT[Stem(luck_stem)])
        stem_res: list[StemHapResolution] = resolve_stem_hap(
            pillars, favorability, luck_stems=[luck_stem],
        )
    except (KeyError, ValueError):
        return False, [], []
    mitigated = False
    officers: list[str] = []
    notes: list[str] = []
    for sr in stem_res:
        if not sr.luck_origin:
            continue
        pair = "".join(sr.pair)
        if sr.transform_element and str(sr.transform_element) == officer and (
            (sr.hap_mode == "transform" and sr.transform_tier == "confirmed")
            or (sr.hap_mode == "bind" and sr.direction == "away")
        ):
            officers.append(officer)
            notes.append(f"천간 {pair}合 → 결과 오행 {officer}(관) — 관운 강화 재료")
        if (
            favorability.get(stem_el) in _BOON_WHEN_BOUND
            and sr.hap_mode == "bind" and sr.direction == "away"
            and any(a.stem == luck_stem and a.effect == "boon" for a in sr.affected)
        ):
            mitigated = True
            notes.append(f"천간 {pair}合 합거 — 운 천간 {luck_stem} 흉 완화(지병 완화)")
    return mitigated, officers, notes


def _branch_part(
    pillars: FourPillarsResult, favorability: dict[str, str], luck_branch: str, officer: str,
) -> tuple[bool, list[str], list[str]]:
    """운 지지 판정(육합만) → (완화 여부, 관운 강화 오행 목록, 표지)."""
    try:
        branch_el = str(BRANCH_ELEMENT[Branch(luck_branch)])
        branch_res: list[BranchHapResolution] = resolve_branch_hap(
            pillars, favorability, luck_branches=[luck_branch],
        )
    except (KeyError, ValueError):
        return False, [], []
    mitigated = False
    officers: list[str] = []
    notes: list[str] = []
    for br in branch_res:
        if not br.luck_origin or br.kind != "six":
            continue
        members = "".join(br.members)
        bound_away = br.hap_mode == "bind" and br.direction == "away"
        boon = [a for a in br.affected if a.effect == "boon"]
        if br.transform_element and str(br.transform_element) == officer and (
            bound_away or (br.hap_mode == "transform" and br.transform_tier == "confirmed")
        ):
            officers.append(officer)
            notes.append(f"지지 {members}合 → 결과 오행 {officer}(관) — 관운 강화 재료")
        if favorability.get(branch_el) in _BOON_WHEN_BOUND and bound_away and boon:
            mitigated = True
            bound = "·".join(f"{a.stem} {a.ten_god}" for a in boon)
            notes.append(f"지지 {members}合 합거 — {bound} 흉 완화(지병 완화, 제거 아님)")
    return mitigated, officers, notes


def resolve_hap_mitigation(
    pillars: FourPillarsResult,
    favorability: dict[str, str],
    *,
    luck_stem: str,
    luck_branch: str,
) -> HapMitigation:
    """운 간지가 원국과 맺는 합에서 흉신 완화·관운 강화 재료를 판정한다.

    Args:
        pillars: 원국 사주.
        favorability: 오행(한자) → 역할('용신'/'희신'/'기신'/'구신'/'한신'). luck_cycles처럼
            역할명이 용신/기신 두 가지뿐이어도 동작한다(boon 판정은 기·구신만 본다).
        luck_stem: 운 천간(한자). 빈 문자열이면 천간 판정 생략.
        luck_branch: 운 지지(한자). 빈 문자열이면 지지 판정 생략.

    Returns:
        HapMitigation — 조건에 맞는 것이 없으면 모든 필드가 기본값.
    """
    if pillars.month is None or pillars.day is None:
        return HapMitigation()
    officer = officer_element(pillars.day_master)
    stem_m = False
    officers: list[str] = []
    notes: list[str] = []
    if luck_stem:
        stem_m, officers, notes = _stem_part(pillars, favorability, luck_stem, officer)
    branch_m = False
    if luck_branch:
        branch_m, b_officers, b_notes = _branch_part(pillars, favorability, luck_branch, officer)
        officers += b_officers
        notes += b_notes
    return HapMitigation(
        stem_mitigated=stem_m,
        branch_mitigated=branch_m,
        officer_elements=tuple(dict.fromkeys(officers)),
        notes=tuple(dict.fromkeys(notes)),
    )
