"""운(運) 구조 배경 플래그 — 충근·개두·절각·통관 부재·구응 손상·특수격 역행 (A2, 2026-09-18 승인).

전문가 참고 기준 보완 자료의 '지지 기반과 기운의 흐름이 약해지는 구조'·'제어 장치가 망가지는
경우'를 운 유입 관점으로 판정한다. 판정만 하고 가중치는 소비처(event_engine_v2 favorability,
luck_cycles 월 등급)가 적용한다. 점수·사건 종류·순위는 바꾸지 않는다.

적용 범위(데굴님 결정 2026-09-18): 개두·절각의 원국 기둥 적용은 고전(옥조정진경 사례·역학동 고전
고찰)에 근거가 있으나 '적중률이 더 높다'는 실증 자료는 없었다. 그래서 **판정(감쇠·감점)은 적천수
기준인 운 기둥에만** 걸고, 원국 기둥의 개두·절각은 표지(서술)로만 낸다.

판정 조건:
- 개두(蓋頭): 운 기둥의 천간 오행이 지지 오행을 극 — 지지의 작용이 천간 간섭으로 덜 발휘된다.
- 절각(截脚): 운 기둥의 지지 오행이 천간 오행을 극 — 드러난 역할을 기반이 받쳐 주지 못한다.
  두 경우 모두 '억제되는 쪽'이 용·희신이면 불리, 기·구신이면 오히려 유리(필요 없는 기운의 억제)로
  본다 — 참고 기준 "필요한 기운을 억제하는지, 불필요한 기운을 억제하는지에 따라 평가가 달라진다".
- 충근(沖根): 운 지지가 원국 지지를 충하고, 그 원국 지지의 본기 오행이 원국 천간의 뿌리이면 그
  천간의 기반이 흔들린다. 용·희신 천간이면 '기반 손상', 기·구신 천간이면 '흉 정리'.
  "충이 있다고 뿌리가 무조건 뽑히는 것은 아니다" — 그래서 본기(정기)만 보고, 다른 뿌리가 남아
  있으면(같은 오행의 다른 원국 지지 본기) 손상으로 보지 않는다.
- 통관 부재: 운 천간 오행과 일간 오행이 극 관계인데, 둘을 잇는 통관 오행이 원국 표면(천간·지지
  본기)에 없으면 '대립을 중재할 기운 부재'.
- 구응 손상: 運破格(luck_geok_break)에서 구응이 있다고 본 원국 십성 글자를 운 지지가 충하거나 운
  천간이 합거로 묶으면, 그 구응은 작동하지 않는 것으로 본다(→ 소비처가 '경향'을 '파격'으로 격상).
- 특수격 역행: 원국이 특수격(전왕/종격, override)일 때 그 흐름을 거스르는 오행이 운으로 들어오면
  '성립 조건 파괴 경향'. 전왕격은 전왕 오행을 극하는 운, 종격은 일간을 돕는 운(비겁·인성).
  화기격(化氣格)은 化神 정보가 별도 경로라 이번 범위에서 제외한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from saju_shared_types.constants import (
    BRANCH_CLASHES,
    BRANCH_ELEMENT,
    CONTROLS,
    GENERATES,
    STEM_ELEMENT,
    main_hidden_stem,
    ten_god,
)
from saju_shared_types.enums import Branch, Element, Stem
from saju_shared_types.pillars import FourPillarsResult

from ..relations.hap_modes import resolve_stem_hap
from .luck_geok_break import LuckGeokBreak, geok_break

_USEFUL = {"용신", "희신"}
_UNFAVORABLE = {"기신", "구신"}
_DOMINANT_ELEMENT = {"곡직격": "木", "염상격": "火", "가색격": "土", "종혁격": "金", "윤하격": "水"}
_POS_KO = {"year": "연주", "month": "월주", "day": "일주", "hour": "시주"}


@dataclass(frozen=True)
class LuckStructureFlags:
    """운 간지 1건의 구조 배경 판정."""

    luck_gaedu: bool = False  # 운 기둥 개두(천간이 지지를 극)
    luck_jeolgak: bool = False  # 운 기둥 절각(지지가 천간을 극)
    suppressed_role: str = ""  # 개두·절각으로 억제되는 쪽의 역할('용신'…), 없으면 빈 값
    natal_gaedu_jeolgak: tuple[str, ...] = ()  # 원국 기둥 표지('월주 개두' 등) — 서술 전용
    chunggeun: tuple[str, ...] = ()  # 충근 표지('丁(희신) 뿌리 亥 충' 등)
    chunggeun_useful: bool = False  # 용·희신 천간의 뿌리가 충 → 기반 손상
    chunggeun_unfavorable: bool = False  # 기·구신 천간의 뿌리가 충 → 흉 정리(길)
    tonggwan_absent: str = ""  # '運木↔일간土 통관 火 부재'
    rescue_damaged: tuple[str, ...] = ()  # 구응이 손상된 運破格 구조 이름('비겁쟁재' 등)
    special_breach: str = ""  # '종재격 역행(비겁 土 유입)'
    notes: tuple[str, ...] = ()

    @property
    def any(self) -> bool:
        """판정이 하나라도 있으면 True."""
        return bool(
            self.luck_gaedu or self.luck_jeolgak or self.chunggeun or self.tonggwan_absent
            or self.rescue_damaged or self.special_breach or self.natal_gaedu_jeolgak
        )


def _pillar_gaedu_jeolgak(stem: str, branch: str) -> tuple[bool, bool]:
    """(개두, 절각) — 한 기둥의 천간·지지 오행 극 관계."""
    se = STEM_ELEMENT[Stem(stem)]
    be = BRANCH_ELEMENT[Branch(branch)]
    return CONTROLS[se] == be, CONTROLS[be] == se


def _natal_surface_elements(pillars: FourPillarsResult) -> set[str]:
    out: set[str] = set()
    for pil in (pillars.year, pillars.month, pillars.day, pillars.hour):
        if pil is None:
            continue
        out.add(str(STEM_ELEMENT[Stem(pil.stem)]))
        out.add(str(BRANCH_ELEMENT[Branch(pil.branch)]))
    return out


def _mediator(x: Element, y: Element) -> Element | None:
    """x가 y를 극할 때 x生m生y인 통관 오행 m(없으면 None)."""
    for m in Element:
        if GENERATES[x] == m and GENERATES[m] == y:
            return m
    return None


def resolve_luck_structure_flags(
    pillars: FourPillarsResult,
    favorability: dict[str, str],
    *,
    luck_stem: str,
    luck_branch: str,
    geok_name: str | None = None,
    luck_ten_gods: tuple[str, str] | None = None,
    special_pattern: dict | None = None,
) -> LuckStructureFlags:
    """운 간지 1건의 구조 배경 판정(순수 함수).

    Args:
        pillars: 원국.
        favorability: 오행(한자) → 역할.
        luck_stem / luck_branch: 운 천간·지지(한자).
        geok_name: 원국 주격 이름(구응 손상 판정용, None이면 생략).
        luck_ten_gods: 운 천간·지지(본기) 십성(구응 손상 판정용).
        special_pattern: GeokgukResult.special_pattern(특수격 역행 판정용).
    """
    if pillars.month is None or pillars.day is None:
        return LuckStructureFlags()
    try:
        ls, lb = Stem(luck_stem), Branch(luck_branch)
    except ValueError:
        return LuckStructureFlags()
    dm = Stem(pillars.day_master)
    dm_el = STEM_ELEMENT[dm]
    notes: list[str] = []

    # ── 개두·절각(운 기둥 판정 + 원국 기둥 표지) ──────────────────────────
    gaedu, jeolgak = _pillar_gaedu_jeolgak(luck_stem, luck_branch)
    suppressed = ""
    if gaedu:
        suppressed = favorability.get(str(BRANCH_ELEMENT[lb]), "")
        role_txt = suppressed or "역할 미상"
        notes.append(f"운 기둥 개두({luck_stem}이 {luck_branch}을 극) — 지지 작용 억제({role_txt})")
    elif jeolgak:
        suppressed = favorability.get(str(STEM_ELEMENT[ls]), "")
        role_txt = suppressed or "역할 미상"
        notes.append(f"운 기둥 절각({luck_branch}이 {luck_stem}을 극) — 천간 작용 억제({role_txt})")
    natal_marks: list[str] = []
    pillar_items = (
        ("year", pillars.year), ("month", pillars.month),
        ("day", pillars.day), ("hour", pillars.hour),
    )
    for pos, pil in pillar_items:
        if pil is None:
            continue
        g, j = _pillar_gaedu_jeolgak(pil.stem, pil.branch)
        if g:
            natal_marks.append(f"{_POS_KO[pos]} 개두")
        elif j:
            natal_marks.append(f"{_POS_KO[pos]} 절각")

    # ── 충근 ──────────────────────────────────────────────────────────────
    chung_marks: list[str] = []
    ch_useful = ch_unfav = False
    natal_pillars = [p for _pos, p in pillar_items if p is not None]
    for hit in natal_pillars:
        nb = Branch(hit.branch)
        if frozenset({lb, nb}) not in BRANCH_CLASHES:
            continue
        root_el = STEM_ELEMENT[main_hidden_stem(nb)]
        # 같은 오행의 다른 뿌리(본기)가 남아 있으면 '뿌리가 뽑힌 것'이 아니다.
        other_roots = [
            p for p in natal_pillars
            if p is not hit and STEM_ELEMENT[main_hidden_stem(Branch(p.branch))] == root_el
        ]
        if other_roots:
            continue
        for _pos, pil in (("year", pillars.year), ("month", pillars.month), ("hour", pillars.hour)):
            if pil is None or STEM_ELEMENT[Stem(pil.stem)] != root_el:
                continue
            role = favorability.get(str(root_el), "")
            chung_marks.append(f"{pil.stem}({role or '역할 미상'}) 뿌리 {nb} 충")
            if role in _USEFUL:
                ch_useful = True
            elif role in _UNFAVORABLE:
                ch_unfav = True
    if chung_marks:
        notes.append("충근 — " + " · ".join(chung_marks))

    # ── 통관 부재 ─────────────────────────────────────────────────────────
    tonggwan = ""
    luck_el = STEM_ELEMENT[ls]
    if luck_el != dm_el:
        pair = None
        if CONTROLS[luck_el] == dm_el:
            pair = (luck_el, dm_el)
        elif CONTROLS[dm_el] == luck_el:
            pair = (dm_el, luck_el)
        if pair is not None:
            med = _mediator(*pair)
            if med is not None and str(med) not in _natal_surface_elements(pillars):
                tonggwan = f"運{luck_el}↔일간{dm_el} 통관 {med} 부재"
                notes.append(f"통관 부재 — {tonggwan}(대립을 중재할 기운이 원국 표면에 없음)")

    # ── 구응 손상 ─────────────────────────────────────────────────────────
    damaged: list[str] = []
    if geok_name and luck_ten_gods:
        natal_tg: list[tuple[str, str, str]] = []  # (십성, 글자, 종류 stem|branch)
        for pos, pil in pillar_items:
            if pil is None:
                continue
            if pos != "day":
                natal_tg.append((str(ten_god(dm, Stem(pil.stem))), pil.stem, "stem"))
            hidden = main_hidden_stem(Branch(pil.branch))
            natal_tg.append((str(ten_god(dm, hidden)), pil.branch, "branch"))
        bound_stems: set[str] = set()
        try:
            for r in resolve_stem_hap(pillars, favorability, luck_stems=[luck_stem]):
                if r.luck_origin and r.hap_mode == "bind" and r.direction == "away":
                    bound_stems.update(a.stem for a in r.affected if a.stem != luck_stem)
        except (KeyError, ValueError):
            pass
        clashed = {
            p.branch for p in natal_pillars if frozenset({lb, Branch(p.branch)}) in BRANCH_CLASHES
        }
        b: LuckGeokBreak
        for b in geok_break(geok_name, list(luck_ten_gods), [t for t, _, _ in natal_tg]):
            if not b.rescued:
                continue
            rescuers = set(b.rescue_evidence.split("·"))
            alive = [
                (tg, ch, kind) for tg, ch, kind in natal_tg
                if tg in rescuers and not (
                    (kind == "stem" and ch in bound_stems) or (kind == "branch" and ch in clashed)
                )
            ]
            if not alive:
                damaged.append(b.pattern)
                notes.append(
                    f"구응 손상 — {b.pattern}의 구응({b.rescue_evidence})이 운 충·합거로 작동 불가"
                )

    # ── 특수격 역행 ───────────────────────────────────────────────────────
    breach = ""
    if special_pattern and special_pattern.get("override"):
        name = str(special_pattern.get("name", ""))
        kind = str(special_pattern.get("type", ""))
        if kind == "dominant" and name in _DOMINANT_ELEMENT:
            dom = _DOMINANT_ELEMENT[name]
            if str(CONTROLS[luck_el]) == dom:
                breach = f"{name} 역행(전왕 {dom}을 극하는 {luck_el} 유입)"
        elif kind == "follow":
            if luck_el == dm_el or GENERATES[luck_el] == dm_el:
                breach = f"{name} 역행(일간을 돕는 {luck_el} 유입 — 종(從)의 흐름 이탈)"
        if breach:
            notes.append(f"특수격 성립 조건 파괴 경향 — {breach}")

    return LuckStructureFlags(
        luck_gaedu=gaedu,
        luck_jeolgak=jeolgak,
        suppressed_role=suppressed,
        natal_gaedu_jeolgak=tuple(natal_marks),
        chunggeun=tuple(chung_marks),
        chunggeun_useful=ch_useful,
        chunggeun_unfavorable=ch_unfav,
        tonggwan_absent=tonggwan,
        rescue_damaged=tuple(dict.fromkeys(damaged)),
        special_breach=breach,
        notes=tuple(notes),
    )
