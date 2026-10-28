"""반복 구조 판정 어댑터 — 천간 반복·지지 반복·자형·같은 간지 기둥 (2026-10-27 데굴님 승인).

만세력 핵심(`saju_manse_core.relations`)은 인접 쌍만 병존으로 기록하고 수정 금지라, 원국 기둥에서
같은 글자 반복을 직접 모아 **그룹 단위**로 판정하는 어댑터를 둔다.

단계 분리(설계 원칙):
  1. 존재 — 같은 글자 여부만(지장간은 보지 않는다).
  2. 설명용 구조 강도 — 위치 가중(인접 1.00·한 칸 건너 0.70·두 칸 건너 0.50) 최댓값 +
     min(0.25, 0.10·(n−2)). **검증 전 가설값**이라 점수·사건 판정에 쓰지 않는다.
  3. 유불리 재료 — 반복 글자의 십성·오행 역할(용희기구한)을 붙이기만 한다(판정은 기존 엔진).
  4. 운 활성화 — 같은 글자 운 유입은 새 사건이 아니라 기존 그룹의 기간 활성화, 원국에 한 개뿐이면
     기간 한정 반복(자형 글자만 기록), 원국에 없고 상위 운과 겹치면 운끼리 반복, 반복 그룹을 충하면
     충 활성화 그룹 1건.
점수·사건 후보·오행 세력은 바꾸지 않는다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from itertools import combinations
from pathlib import Path

from saju_shared_types.constants import (
    BRANCH_CLASHES,
    BRANCH_ELEMENT,
    SELF_PUNISHMENT,
    STEM_ELEMENT,
    main_hidden_stem,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.repetition_structure import (
    RepetitionActivation,
    RepetitionGroup,
    RepetitionPair,
)

_POSITIONS = ("year", "month", "day", "hour")
_POS_KO = {"year": "연", "month": "월", "day": "일", "hour": "시"}
#: 위치 가중(기둥 간격 → 가중) — 가설값, 설명 전용.
DISTANCE_WEIGHT: dict[int, float] = {1: 1.0, 2: 0.7, 3: 0.5}
_SELF_PUNISH_CHARS = frozenset(str(b) for b in SELF_PUNISHMENT)
_BRANCHES = frozenset("子丑寅卯辰巳午未申酉戌亥")
_LAYER_KO = {"daewoon": "대운", "year": "세운", "month": "월운", "day": "일운"}
#: 궁위 라벨(활성화 줄의 궁위별 가능성 영역 안내용, 2026-10-28). 사전 `palace` 항목의
#: palace_ko 가 있으면 그쪽이 우선.
_PALACE_KO = {
    "year": "연지(조상·사회 배경)", "month": "월지(사회·직장)",
    "day": "일지(배우자·몸)", "hour": "시지(자녀·지향·투자)",
}
_DICT_PATH = (
    Path(__file__).resolve().parents[3]
    / "dictionaries" / "interpretations" / "repetition_text.json"
)


@lru_cache(maxsize=1)
def load_repetition_text() -> dict:
    """repetition_text.json(서술 재료) 로드 — 프로세스 캐시."""
    return json.loads(_DICT_PATH.read_text(encoding="utf-8"))


def structural_strength(pairs: list[RepetitionPair], count: int) -> float:
    """설명용 구조 강도 — max(w) + min(0.25, 0.10·(n−2)). 사건 확률이 아니다."""
    if not pairs:
        return 0.0
    return round(max(p.weight for p in pairs) + min(0.25, 0.10 * max(count - 2, 0)), 2)


def _pairs(positions: list[str]) -> list[RepetitionPair]:
    out: list[RepetitionPair] = []
    for a, b in combinations(positions, 2):
        d = abs(_POSITIONS.index(b) - _POSITIONS.index(a))
        out.append(RepetitionPair(a=a, b=b, distance=d, weight=DISTANCE_WEIGHT.get(d, 0.5)))
    return out


def _ten_god_of(day_master: str, kind: str, char: str) -> str:
    try:
        dm = Stem(day_master)
        if kind == "stem":
            return str(ten_god(dm, Stem(char)))
        return str(ten_god(dm, Stem(main_hidden_stem(Branch(char)).value)))
    except ValueError:
        return ""


def _element_of(kind: str, char: str) -> str:
    try:
        if kind == "stem":
            return str(STEM_ELEMENT[Stem(char)])
        return str(BRANCH_ELEMENT[Branch(char)])
    except ValueError:
        return ""


def detect_repetition_groups(
    result: ManseV2Result, fav_map: dict[str, str] | None = None,
) -> list[RepetitionGroup]:
    """원국 반복 그룹 — 천간·지지·같은 간지 기둥(시주 미상이면 3기둥만).

    Args:
        result: 만세 결과(pillars 필수 — 없으면 빈 목록).
        fav_map: {오행 한자: 역할}(없으면 역할 빈 값).

    Returns:
        그룹 목록(천간 → 지지 → 간지 기둥, 기둥 순 첫 자리 기준 정렬).
    """
    p = result.pillars
    if p is None:
        return []
    stems: dict[str, list[str]] = {}
    branches: dict[str, list[str]] = {}
    ganjis: dict[str, list[str]] = {}
    for pos in _POSITIONS:
        pil = getattr(p, pos, None)
        if pil is None:
            continue
        stems.setdefault(pil.stem, []).append(pos)
        branches.setdefault(pil.branch, []).append(pos)
        ganjis.setdefault(f"{pil.stem}{pil.branch}", []).append(pos)
    fav = fav_map or {}
    out: list[RepetitionGroup] = []
    for kind, table in (("stem", stems), ("branch", branches), ("pillar", ganjis)):
        for char, positions in table.items():
            if len(positions) < 2:
                continue
            pairs = _pairs(positions)
            base = char[0] if kind == "pillar" else char
            base_kind = "stem" if kind in ("stem", "pillar") else "branch"
            element = _element_of(base_kind, base)
            out.append(RepetitionGroup(
                kind=kind,
                char=char,
                positions=positions,
                count=len(positions),
                pairs=pairs,
                adjacent=any(pr.distance == 1 for pr in pairs),
                is_self_punishment=kind == "branch" and char in _SELF_PUNISH_CHARS,
                structural_strength=structural_strength(pairs, len(positions)),
                ten_god=_ten_god_of(p.day_master, base_kind, base),
                element=element,
                role=fav.get(element, ""),
            ))
    order = {"stem": 0, "branch": 1, "pillar": 2}
    out.sort(key=lambda g: (order[g.kind], _POSITIONS.index(g.positions[0])))
    return out


def _upper_layers(result: ManseV2Result, layer: str, period: str) -> list[tuple[str, str, str]]:
    """대상 운 기둥 위층의 (층위, 천간, 지지) — 세운이면 대운, 월운이면 대운·세운."""
    lc = result.luck_cycles
    if lc is None or not period[:4].isdigit():
        return []
    year = int(period[:4])
    out: list[tuple[str, str, str]] = []
    if layer in ("year", "month"):
        for d in lc.daewoon_table:
            if d.approx_start_date.year <= year <= d.approx_end_date.year:
                out.append(("daewoon", d.stem, d.branch))
                break
    if layer == "month":
        for y in lc.yearly_luck:
            if y.label == period[:4]:
                out.append(("year", y.stem, y.branch))
                break
    return out


def repetition_activations(
    result: ManseV2Result, layer: str, period: str, ganji: str,
) -> list[RepetitionActivation]:
    """운 기둥 하나가 반복 구조를 건드린 기록 — 서술 전용(점수·사건 비개입).

    Args:
        result: 원국 결과.
        layer: daewoon/year/month(일운·기타는 빈 목록 — 짧은 단위는 다루지 않는다).
        period: 운 라벨('2027' · '2027-02' · 대운은 시작연도 문자열).
        ganji: 운 간지 2글자.
    """
    p = result.pillars
    if p is None or layer not in ("daewoon", "year", "month") or len(ganji) < 2:
        return []
    natal = {
        "stem": [(pos, getattr(p, pos).stem) for pos in _POSITIONS if getattr(p, pos, None)],
        "branch": [(pos, getattr(p, pos).branch) for pos in _POSITIONS if getattr(p, pos, None)],
    }
    upper = _upper_layers(result, layer, period)
    out: list[RepetitionActivation] = []
    for kind, luck_char in (("stem", ganji[0]), ("branch", ganji[1])):
        same = [pos for pos, ch in natal[kind] if ch == luck_char]
        self_p = kind == "branch" and luck_char in _SELF_PUNISH_CHARS
        if len(same) >= 2:
            out.append(RepetitionActivation(
                kind="natal_group_active", char=luck_char, luck_char=luck_char, layer=layer,
                natal_positions=same, is_self_punishment=self_p,
            ))
        elif len(same) == 1 and self_p:
            out.append(RepetitionActivation(
                kind="period_new", char=luck_char, luck_char=luck_char, layer=layer,
                natal_positions=same, is_self_punishment=True,
            ))
        elif not same and self_p:
            # 운끼리 반복은 자형 글자만 기록한다(천간·일반 지지의 층간 반복은 노이즈 — 실답 검토).
            idx = 0 if kind == "stem" else 1
            layers = [lv for lv, st, br in upper if (st, br)[idx] == luck_char]
            if layers:
                out.append(RepetitionActivation(
                    kind="luck_luck", char=luck_char, luck_char=luck_char, layer=layer,
                    luck_layers=layers, is_self_punishment=self_p,
                ))
    # 반복 그룹(같은 지지 2개 이상)을 운 지지가 충하면 활성화 그룹 1건(쌍마다 사건을 세지 않는다).
    by_branch: dict[str, list[str]] = {}
    for pos, ch in natal["branch"]:
        by_branch.setdefault(ch, []).append(pos)
    try:
        lb = Branch(ganji[1])
    except ValueError:
        return out
    for ch, positions in by_branch.items():
        if len(positions) >= 2 and frozenset({lb, Branch(ch)}) in BRANCH_CLASHES:
            out.append(RepetitionActivation(
                kind="clash_group", char=ch, luck_char=ganji[1], layer=layer,
                natal_positions=positions, is_self_punishment=ch in _SELF_PUNISH_CHARS,
                relation="clash",
            ))
    return out


def _kind_label(group: RepetitionGroup) -> str:
    if group.kind == "stem":
        return f"천간 {group.char} 반복"
    if group.kind == "pillar":
        return f"같은 간지 기둥 {group.char} 반복"
    sp = f" · 자형({group.char}{group.char})" if group.is_self_punishment else ""
    return f"지지 {group.char} 반복{sp}"


def group_line(group: RepetitionGroup) -> str:
    """원국 반복 그룹 한 줄(설명용) — 자리·인접·그룹·십성·역할·해석 후보."""
    text = load_repetition_text()
    seat = "주" if group.kind == "pillar" else ("간" if group.kind == "stem" else "지")
    where = "·".join(f"{_POS_KO[p]}{seat}" for p in group.positions)
    adj = "인접" if group.adjacent else "떨어져 있음"
    tg = f" · {group.ten_god} 반복" if group.ten_god else ""
    role = f" · {group.element} {group.role}" if group.role else ""
    head = (
        f"{_kind_label(group)}({where}, {adj}, {group.count}글자 1그룹"
        + (f"·관계 쌍 {len(group.pairs)}" if len(group.pairs) > 1 else "")
        + f", 설명용 구조 강도 {group.structural_strength:.2f}){tg}{role}"
    )
    if group.is_self_punishment:
        sp = next((x for x in text["self_punishment"] if x["char"] == group.char), None)
        if sp:
            head += (
                f" — 중심: {sp['center']} / 살아나면 {sp['positive']} / "
                f"지나치면 {sp['negative']}"
            )
    elif group.kind in ("stem", "pillar"):
        st = next((x for x in text["stems"] if x["char"] == group.char[0]), None)
        if st:
            head += f" — 기본 방향: {st['base']} / 과할 때: {st['excess']}"
    else:
        br = next((x for x in text["branches"] if x["char"] == group.char), None)
        if br:
            head += f" — 해석 후보: {br['base']}"
    return head


def _palace_suffix(act: RepetitionActivation, text: dict | None = None) -> str:
    """활성화 줄 뒤의 가능성 영역 안내(2026-10-28, 서술 전용) — 자형 글자의 공통 활성화 문구 +
    원국 기둥별 궁위 문구. 사전에 해당 글자·궁위 항목이 없으면 빈 문자열(공통 문구 폴백).

    단정이 아니라 '거론될 수 있는 영역'이다 — 같은 영역의 독립 사건 후보가 있으면 그 판정이 우선.
    """
    if act.relation != "same" or act.char not in _BRANCHES:
        return ""
    text = text or load_repetition_text()
    parts: list[str] = []
    if act.is_self_punishment:
        entry = next((x for x in text.get("self_punishment", []) if x["char"] == act.char), None)
        if entry and entry.get("activation"):
            parts.append(f"활성화 결: {entry['activation']}")
    by_palace = {
        (x["char"], x["palace"]): x for x in text.get("palace", []) if x.get("text")
    }
    for pos in act.natal_positions:
        item = by_palace.get((act.char, pos))
        if item is None:
            continue
        label = item.get("palace_ko") or _PALACE_KO.get(pos, pos)
        parts.append(f"궁위 가능성 영역 — {label}: {item['text']}")
    if not parts:
        return ""
    return (
        " · " + " / ".join(parts)
        + " (가능성 안내 — 사건 확정 아님, 같은 영역 사건 후보가 있으면 그 판정 우선)"
    )


def activation_line(act: RepetitionActivation) -> str:
    """운 활성화 한 줄 — 구조의 기간 활성화(+ 사전에 있으면 궁위별 가능성 영역)."""
    lv = _LAYER_KO.get(act.layer, act.layer)
    seat = "지" if act.char in _BRANCHES else "간"
    where = "·".join(f"{_POS_KO[p]}{seat}" for p in act.natal_positions)
    sp = f" 자형({act.char}{act.char})" if act.is_self_punishment else ""
    if act.kind == "natal_group_active":
        return (
            f"{lv} {act.luck_char} 유입 — 원국 {act.char} 반복 그룹({where}){sp}의 기간 활성화"
            "(새 사건이 아니라 기존 구조가 이 기간 두드러짐)" + _palace_suffix(act)
        )
    if act.kind == "period_new":
        return (
            f"{lv} {act.luck_char} 유입 — 원국 {act.char}({where})와 기간 한정{sp} 성립"
            "(이 기간에만)" + _palace_suffix(act)
        )
    if act.kind == "luck_luck":
        ups = "·".join(_LAYER_KO.get(x, x) for x in act.luck_layers)
        return f"{lv}·{ups} 모두 {act.char} — 운끼리 기간 한정 반복{sp}(원국에는 없음)"
    return (
        f"{lv} {act.luck_char} 유입 — 원국 {act.char} 반복 그룹({where})을 함께 충하는 충 활성화 "
        f"그룹 1건(관계 쌍 {len(act.natal_positions)}개 — 두 영역을 함께 검토하되 사건을 쌍마다 "
        "따로 세지 말 것)"
    )


__all__ = [
    "DISTANCE_WEIGHT",
    "activation_line",
    "detect_repetition_groups",
    "group_line",
    "load_repetition_text",
    "repetition_activations",
    "structural_strength",
]
