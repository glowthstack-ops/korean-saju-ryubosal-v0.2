"""공망 2축 상태·강도(자왕)·자극 확장 — 순수 함수(서술 전용, 2026-10-23).

SSOT: doc/v2_2/GONGMANG_HAP_SEMANTICS.md §2(2축)·§3(해공 강도 계층)·§7(고전 근거·현대 통설).
- VOID_STATE: FULL_VOID → PARTIAL_VOID → RELEASED (해공 강도 최대값으로 등급화)
- ACTIVATION: DORMANT → CONTACTED → ACTIVATED (자극 유무·강도)
- 강도(자왕): 공망 글자의 세력 — 월령 왕상휴수사 + 일간 기준 12운성(통설 "旺不爲空, 休囚落空 難解")
- 자극 종류: 전실(같은 글자)·충·형·육합·삼합국·반합·방합·암합 — 《삼명통회》
  "若無沖無合無刑 謂眞空亡"(충·합·형이 있으면 진공망이 아니다)을 따라 형을 포함한다.
점수·게이트·선별에 개입하지 않는다. 등급 수치는 SSOT §3 계층의 서술 등급이다.
"""

from __future__ import annotations

from saju_manse_core.pillars.twelve_unseong import twelve_unseong
from saju_shared_types.constants import (
    BRANCH_CLASHES,
    BRANCH_ELEMENT,
    BRANCH_INDEX,
    BRANCHES,
    DIRECTIONAL_COMBINATIONS,
    PUNISHMENT_MUTUAL,
    PUNISHMENT_TRIPLES,
    SIX_COMBINATIONS,
    STEM_COMBINATIONS,
    STEM_INDEX,
    THREE_HARMONY,
    main_hidden_stem,
    season_state,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.gongmang import (
    ACTIVATION_KO,
    STIMULUS_KO,
    VOID_STATE_KO,
    GongmangSlotState,
    GongmangStimulus,
    GongmangTransitState,
)

#: 해공 강도 등급(SSOT §3) — 전실 > 충 > 삼합국 > 형 > 육합 > 반합 > 암합 > 방합.
STIMULUS_STRENGTH: dict[str, float] = {
    "fill": 1.0, "clash": 0.8, "trine": 0.6, "punishment": 0.5, "six_combine": 0.4,
    "half_trine": 0.3, "hidden_combine": 0.2, "directional": 0.1,
}
#: 합 상대(운 글자)까지 공망 글자면 해공력 감산(SSOT §3 '합 상대까지 공망').
PARTNER_VOID_FACTOR = 0.5
_RELEASED_MIN = 0.7
_PARTIAL_MIN = 0.3
_POS_KO = {"year": "연지", "month": "월지", "hour": "시지", "day": "일지"}
_SEASON_KO = {"wang": "왕", "xiang": "상", "xiu": "휴", "qiu": "수", "si": "사"}
_STAGE_UP = {"장생", "관대", "건록", "제왕"}
_STAGE_DOWN = {"병", "사", "묘", "절"}


def intensity_of(day_master: Stem, branch: Branch, month_branch: Branch) -> tuple[str, str]:
    """공망 글자의 세력(자왕) 등급 — (등급, 근거). 월령 왕상=2·휴=1·수사=0, 12운성 ±1."""
    season = season_state(BRANCH_ELEMENT[branch], month_branch)
    score = {"wang": 2, "xiang": 2, "xiu": 1}.get(season, 0)
    stage = twelve_unseong(day_master, branch)
    if stage in _STAGE_UP:
        score += 1
    elif stage in _STAGE_DOWN:
        score -= 1
    grade = "강" if score >= 2 else ("중" if score == 1 else "약")
    return grade, f"월령 {_SEASON_KO[season]} · 12운성 {stage}"


def _trine_kind(luck: Branch, natal: Branch, natal_all: set[Branch]) -> str | None:
    for members, _el, royal in THREE_HARMONY:
        if luck in members and natal in members and luck != natal:
            third = next(iter(members - {luck, natal}))
            if third in natal_all:
                return "trine"
            if royal in (luck, natal):
                return "half_trine"
            return None
    return None


def stimuli_for(
    luck_branch: Branch, slot_branch: Branch, position: str,
    natal_branches: set[Branch], void_set: set[Branch],
) -> list[GongmangStimulus]:
    """운 지지가 원국 공망 자리 글자에 가하는 자극 목록(종류별 최대 1건)."""
    out: list[GongmangStimulus] = []
    pair = frozenset({luck_branch, slot_branch})
    partner_void = luck_branch in void_set and luck_branch != slot_branch

    def add(kind: str, note: str = "") -> None:
        strength = STIMULUS_STRENGTH[kind]
        if partner_void and kind in ("six_combine", "trine", "half_trine", "directional",
                                     "hidden_combine"):
            strength = round(strength * PARTNER_VOID_FACTOR, 2)
            note = (note + " · " if note else "") + "합 상대도 공망 글자(해공력 감산)"
        out.append(GongmangStimulus(
            kind=kind, luck_branch=str(luck_branch), natal_branch=str(slot_branch),
            natal_position=position, strength=strength, partner_void=partner_void, note=note,
        ))

    if luck_branch == slot_branch:
        add("fill", "같은 글자 유입")
        return out
    if pair in BRANCH_CLASHES:
        add("clash")
    if pair in PUNISHMENT_MUTUAL or any(pair <= t for t in PUNISHMENT_TRIPLES):
        add("punishment")
    if pair in SIX_COMBINATIONS:
        add("six_combine")
    tk = _trine_kind(luck_branch, slot_branch, natal_branches)
    if tk is not None:
        add(tk)
    if any(pair <= members for members, _el in DIRECTIONAL_COMBINATIONS):
        add("directional")
    hidden_pair = frozenset({main_hidden_stem(luck_branch), main_hidden_stem(slot_branch)})
    if hidden_pair in STEM_COMBINATIONS:
        add("hidden_combine")
    return out


def _state_from(stimuli: list[GongmangStimulus]) -> tuple[str, str]:
    top = max((s.strength for s in stimuli), default=0.0)
    if top >= _RELEASED_MIN:
        return "RELEASED", "ACTIVATED"
    if top >= _PARTIAL_MIN:
        return "PARTIAL_VOID", "ACTIVATED"
    if top > 0:
        return "FULL_VOID", "CONTACTED"
    return "FULL_VOID", "DORMANT"


def natal_void_slots(
    pillars: dict[str, str], day_master: str, void_branches: list[str],
) -> list[tuple[str, Branch]]:
    """원국 공망 자리 (position, branch) — 연·월·시만(일지는 일주 기준 공망이 될 수 없다)."""
    void = {Branch(v) for v in void_branches}
    out: list[tuple[str, Branch]] = []
    for pos in ("year", "month", "hour"):
        g = pillars.get(pos)
        if g and len(g) == 2 and Branch(g[1]) in void:
            out.append((pos, Branch(g[1])))
    return out


def transit_state(
    pillars: dict[str, str], day_master: str, void_branches: list[str],
    luck_label: str, luck_ganji: str, *, is_daewoon: bool = False,
) -> GongmangTransitState | None:
    """운 기둥 1개의 공망 상태 — 원국 공망 자리가 없고 빈 자리 전실도 없으면 None.

    Args:
        pillars: {'year': '庚申', ...}(시주 미상이면 hour 없음).
        is_daewoon: 대운이면 '빈 자리 전실'(운 글자 자체 공망)은 기록하지 않는다(대운 공망 무시).
    """
    if not void_branches or len(luck_ganji) != 2 or "month" not in pillars:
        return None
    dm = Stem(day_master)
    luck_b = Branch(luck_ganji[1])
    month_b = Branch(pillars["month"][1])
    void_set = {Branch(v) for v in void_branches}
    natal_all = {Branch(g[1]) for g in pillars.values() if len(g) == 2}
    slots: list[GongmangSlotState] = []
    for pos, b in natal_void_slots(pillars, day_master, void_branches):
        sts = stimuli_for(luck_b, b, pos, natal_all, void_set)
        vs, act = _state_from(sts)
        grade, basis = intensity_of(dm, b, month_b)
        slots.append(GongmangSlotState(
            natal_branch=str(b), position=pos, position_ko=_POS_KO[pos],
            ten_god=str(ten_god(dm, main_hidden_stem(b))), intensity=grade,
            intensity_basis=basis, void_state=vs, activation=act, stimuli=sts,
        ))
    fill_absent: list[str] = []
    if not is_daewoon and luck_b in void_set and luck_b not in natal_all:
        fill_absent.append(str(luck_b))
    if not slots and not fill_absent:
        return None
    return GongmangTransitState(
        luck_label=luck_label, luck_ganji=luck_ganji, slots=slots, fill_absent=fill_absent,
    )


def natal_slot_lines(
    pillars: dict[str, str], day_master: str, void_branches: list[str],
) -> list[str]:
    """고정 prefix 용 — 원국 공망 자리의 글자·궁위·십성·강도(자왕) 한 줄씩(운 자극 전 기본 상태)."""
    if not void_branches or "month" not in pillars:
        return []
    slots = natal_void_slots(pillars, day_master, void_branches)
    if not slots:
        return []
    dm = Stem(day_master)
    month_b = Branch(pillars["month"][1])
    lines = [
        "[공망 상태(사실·점수 아님)] 기본 완전공망·잠복. 운 자극(전실·충·형·합) 시 간지달력 행에 "
        "'공망 자극' 표기. 상태≠길흉 — 살아난 글자의 십성·용희기구한으로 판정. "
        "강도=세력 통설(단정 금지)."
    ]
    for pos, b in slots:
        grade, basis = intensity_of(dm, b, month_b)
        lines.append(
            f"공망 자리 {b}({_POS_KO[pos]} · {ten_god(dm, main_hidden_stem(b))}) — "
            f"강도 {grade}({basis})"
        )
    return lines


def xun_head_of(day_ganji: str) -> str | None:
    """일주 간지 → 旬 머리('甲午旬'). 형식이 어긋나면 None."""
    if len(day_ganji) != 2:
        return None
    try:
        s, b = Stem(day_ganji[0]), Branch(day_ganji[1])
    except ValueError:
        return None
    return f"甲{BRANCHES[(BRANCH_INDEX[b] - STEM_INDEX[s]) % 12]}旬"


def same_xun_line(
    self_pillars: dict[str, str], partner_pillars: dict[str, str],
    self_label: str = "본인", partner_label: str = "상대",
) -> str | None:
    """동반자 동순(同旬) 사실 줄(2026-10-23 데굴님 승인 — 사실만, 인연 성패 단정 금지).

    두 일주가 같은 旬(공망 글자가 같음)이면 '동순'. 통설(인연법)은 동순이면 뜻·기운이 잘 맞는다고
    보나
    결혼 지속·동업 성공의 근거는 아니다 — 지시문에 그 한계를 함께 싣는다.
    """
    a, b = xun_head_of(self_pillars.get("day", "")), xun_head_of(partner_pillars.get("day", ""))
    if a is None or b is None:
        return None
    verdict = "동순(同旬) — 공망 글자가 같음" if a == b else "동순 아님"
    return (
        f"[동순 사실] {self_label} 일주 {a} · {partner_label} 일주 {b} → {verdict}. "
        "통설 인연법은 동순이면 뜻이 잘 맞는다고 보나 사실 한 줄로만 언급하고, 결혼 지속·동업 "
        "성공의 "
        "근거로 단정하지 말 것."
    )


def transit_suffix(state: GongmangTransitState | None) -> str:
    """간지달력 행 접미 — **활성(ACTIVATED)** 슬롯과 빈 자리 전실만 압축 표기(없으면 빈 문자열).

    접촉(CONTACTED — 방합·암합·합 상대 공망 등 0.3 미만)은 토큰 예산(단건 20k) 안에서 10년 창 질문이
    넘치지 않도록 행에 싣지 않는다(상태 모델에는 남는다).
    """
    if state is None:
        return ""
    parts: list[str] = []
    for s in state.slots:
        if not s.stimuli or s.activation != "ACTIVATED":
            continue
        kinds = "·".join(
            STIMULUS_KO[x.kind] + ("(합 상대도 공망)" if x.partner_void else "") for x in s.stimuli
        )
        parts.append(
            f"{s.natal_branch}({s.position_ko}) {kinds}←{state.luck_ganji[1]} → "
            f"{VOID_STATE_KO[s.void_state]}·{ACTIVATION_KO[s.activation]}"
        )
    for b in state.fill_absent:
        parts.append(f"공망 글자 {b} 유입(원국에 없는 자리 — 전실, 실체화 신호)")
    return (" · 공망 자극: " + " / ".join(parts)) if parts else ""
