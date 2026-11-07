"""지지충 완화 글자 서술층 (2026-11-07, 충 강의 대조 — doc/v2_2/EXTERNAL_TEXT_GAP_CLASH_LECTURE.md).

충의 한쪽 글자를 **합으로 묶거나 살려 주는 글자**와, 그 글자가 드는 시기(세운·절기월)를
서술 전용으로 싣는다. 점수·사건 판정에는 관여하지 않는다.

우위 논리(자평진전 「논형충회합해법」 통설): 합은 충을 누그러뜨리되 자동 해소가 아니다 —
①가까이 붙은 합이 우선 ②삼합·방합 완성이 육합보다 세고 ③제3 글자가 그 합 글자를 삼합으로
끌어가면 충이 되살아나며 ④원국 합과 운 충의 선후를 본다. 합이 아니라 상생 논리인 글자
(巳←寅·亥←申)와 방합 짝이면서 해(害)도 되는 글자(卯辰·酉戌)는 형·해가 함께 서므로 완화와
자극을 **병기**한다(2026-11-07 데굴님 결정 — 검색으로 단일 우위 논리를 못 찾는 항목은 병기).

완화 서술은 맞는 글자가 **용·희신**일 때만 낸다 — 기·구신 글자의 충은 충거(정리) 쪽이라
완화 글자를 찾을 이유가 없다(강의: "불이 더 필요하신 분", "물이 공격받지 않아야 되는 사주").
한신은 제외한다. 출생시간 미상으로 용희신이 미확정이면 `favorability_map` 이 비어 전부 생략된다.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from saju_manse_core.calendar.sexagenary_cycle import year_ganzi
from saju_shared_types.constants import BRANCH_CLASHES, BRANCH_ELEMENT
from saju_shared_types.enums import Branch
from saju_shared_types.manse_result import ManseV2Result

_DICT_DIR = Path(__file__).resolve().parents[3] / "dictionaries"

#: 충 쌍 → 사전 관계 이름(원국 관계 발췌 key 와 같다).
PAIR_NAME_KO: dict[frozenset[str], str] = {
    frozenset("子午"): "자오충", frozenset("丑未"): "축미충", frozenset("寅申"): "인신충",
    frozenset("卯酉"): "묘유충", frozenset("辰戌"): "진술충", frozenset("巳亥"): "사해충",
}
#: 삼합 — 제3 글자가 완화 글자를 끌어가는지(충 부활) 판정용.
_TRINES: tuple[frozenset[str], ...] = (
    frozenset("申子辰"), frozenset("亥卯未"), frozenset("寅午戌"), frozenset("巳酉丑"),
)
#: 절기월 지지 → 사용자용 달 라벨(양력 대략 범위).
MONTH_LABEL_KO: dict[str, str] = {
    "寅": "寅월(대략 2월 초~3월 초)", "卯": "卯월(대략 3월 초~4월 초)",
    "辰": "辰월(대략 4월 초~5월 초)", "巳": "巳월(대략 5월 초~6월 초)",
    "午": "午월(대략 6월 초~7월 초)", "未": "未월(대략 7월 초~8월 초)",
    "申": "申월(대략 8월 초~9월 초)", "酉": "酉월(대략 9월 초~10월 초)",
    "戌": "戌월(대략 10월 초~11월 초)", "亥": "亥월(대략 11월 초~12월 초)",
    "子": "子월(대략 12월 초~1월 초)", "丑": "丑월(대략 1월 초~2월 초)",
}
_PALACE_KO = {"year": "연지", "month": "월지", "day": "일지", "hour": "시지"}
_PALACE_INDEX = {"year": 0, "month": 1, "day": 2, "hour": 3}
_RELIEF_ROLES = ("용신", "희신")
#: 한 블록의 줄 상한(토큰 보호) — 후보 기간이 많아도 충 쌍×대상 글자 수는 작다.
_MAX_LINES = 6

RELIEF_BLOCK_HEADER = (
    "[충 완화 글자 — 통설 서술층(점수 미반영)] 아래는 운 지지가 원국의 용·희신 글자를 충할 때 "
    "그 글자를 합으로 묶어 주거나 살려 주는 글자와 시기다. 합이 충을 자동으로 없애지는 않는다"
    "(가까이 붙은 합 우선 · 삼합/방합 완성 > 육합 · 제3 글자가 삼합으로 끌어가면 충 부활). "
    "완화 글자가 형·해도 함께 이루면 완화와 자극을 병기하고, 완화를 '충이 없어진다'로 쓰지 말 것."
)


@lru_cache(maxsize=1)
def load_clash_relief_text(dictionaries_dir: Path | None = None) -> dict:
    """`interpretations/clash_relief_text.json` 원본(캐시)."""
    base = dictionaries_dir or _DICT_DIR
    return json.loads(
        (base / "interpretations" / "clash_relief_text.json").read_text(encoding="utf-8")
    )


def _relief_by_target() -> dict[tuple[frozenset[str], str], dict]:
    """(충 쌍, 맞는 글자) → 완화 항목."""
    return {
        (frozenset(it["pair"]), it["target"]): it
        for it in load_clash_relief_text()["items"]
    }


def _natal_branch_positions(result: ManseV2Result) -> list[tuple[str, str]]:
    """원국 (자리, 지지) 목록 — 시주 미상이면 3자리."""
    pil = result.pillars
    if pil is None:
        return []
    out = [("year", pil.year.branch), ("month", pil.month.branch), ("day", pil.day.branch)]
    if pil.hour is not None:
        out.append(("hour", pil.hour.branch))
    return out


def _role_of_branch(branch: str, fav: dict[str, str]) -> str:
    """지지 오행의 용희기구한 역할(미배정이면 빈 문자열)."""
    try:
        return fav.get(BRANCH_ELEMENT[Branch(branch)].value, "")
    except ValueError:
        return ""


def next_year_with_branch(branch: str, start_year: int, span: int = 12) -> int | None:
    """`start_year` 부터 `span` 년 안에서 세운 지지가 `branch` 인 첫 연도(없으면 None)."""
    for y in range(start_year, start_year + span):
        if year_ganzi(y)[1].value == branch:
            return y
    return None


def _presence_note(
    glyph: str, target_pos: str | None, natal: list[tuple[str, str]],
) -> tuple[bool, str]:
    """완화 글자의 원국 보유 여부와 거리 메모(인접=완화 우세 / 격위=약함)."""
    spots = [pos for pos, b in natal if b == glyph]
    if not spots:
        return False, "원국에 없음"
    notes: list[str] = []
    for pos in spots:
        if target_pos is None:
            notes.append(f"원국 {_PALACE_KO[pos]}에 있음")
            continue
        dist = abs(_PALACE_INDEX[pos] - _PALACE_INDEX[target_pos])
        if dist == 1:
            notes.append(f"원국 {_PALACE_KO[pos]}에 있음(인접 — 묶임이 가까워 완화 우세)")
        else:
            notes.append(f"원국 {_PALACE_KO[pos]}에 있음(격위 — 떨어져 있어 완화 약함)")
    return True, " · ".join(notes)


def _trine_revival_note(glyph: str, pair: frozenset[str], natal: list[tuple[str, str]]) -> str:
    """원국의 제3 글자가 완화 글자를 삼합으로 끌어가면 충이 되살아날 수 있다는 메모."""
    natal_set = {b for _, b in natal}
    for trine in _TRINES:
        if glyph not in trine:
            continue
        others = [g for g in trine if g != glyph and g not in pair and g in natal_set]
        if others:
            return (
                f" ※ 원국 {'·'.join(others)}가 {glyph}를 삼합으로 끌어가면 충이 되살아날 수 있음"
            )
    return ""


def _timing_note(glyph: str, reference_year: int) -> str:
    """완화 글자가 운으로 드는 시기 — 다음 세운 연도와 매년 절기월."""
    y = next_year_with_branch(glyph, reference_year)
    year_part = f"{glyph} 세운 {y}년" if y is not None else f"{glyph} 세운"
    return f"{year_part}·매년 {MONTH_LABEL_KO[glyph]}에 완화 결"


def _relief_phrase(
    item: dict, target: str, role: str, target_pos: str | None,
    natal: list[tuple[str, str]], reference_year: int, *, luck_branch: str | None = None,
) -> str:
    """한 대상 글자의 완화 구절 — 글자·기제·보유/시기·병기 메모."""
    glyph = item["glyph"]
    el = BRANCH_ELEMENT[Branch(target)].value
    head = f"{target}({role} {el})를 {'살리는' if item['mechanism'] == '상생' else '묶는'} {glyph}"
    present, note = _presence_note(glyph, target_pos, natal)
    if present:
        body = note
    elif luck_branch is not None and glyph == luck_branch:
        body = "이번 운 지지가 바로 그 글자"
    else:
        body = f"원국에 없음 — {_timing_note(glyph, reference_year)}"
    tail = _trine_revival_note(glyph, frozenset(item["pair"]), natal) if present else ""
    co = item.get("coRelation", "")
    if co:
        tail += f" ※ {co}도 함께 서므로 완화와 자극을 병기"
    return f"{head}({item['mechanism']}) — {body}{tail}"


def natal_clash_relief_by_name(
    result: ManseV2Result, reference_year: int | None = None,
) -> dict[str, str]:
    """원국 지지충 → {관계 이름: '완화 글자: …'} (대상 글자가 용·희신인 것만).

    원국 관계 발췌(고정 prefix)의 충 항목 끝에 붙인다. 두 글자가 모두 용·희신이면 구절 두 개를
    ' / ' 로 잇는다. 해당 글자가 없으면 그 충은 비워 둔다(사전 없음·용희신 미확정 포함).
    """
    from .event_scoring import favorability_map  # 지역 import — 순환 회피

    sa = result.structure_analysis
    if sa is None or result.pillars is None:
        return {}
    fav = favorability_map(result)
    if not fav:
        return {}
    ref_year = reference_year or date.today().year
    natal = _natal_branch_positions(result)
    by_target = _relief_by_target()
    out: dict[str, str] = {}
    for inter in sa.interactions:
        if inter.relation_type != "clash" or inter.scope != "branch" or len(inter.members) != 2:
            continue
        pair = frozenset(inter.members)
        name = PAIR_NAME_KO.get(pair)
        if name is None or name in out:
            continue
        phrases: list[str] = []
        for target, pos in zip(inter.members, inter.positions, strict=False):
            role = _role_of_branch(target, fav)
            if role not in _RELIEF_ROLES:
                continue
            item = by_target.get((pair, target))
            if item is None:
                continue
            phrases.append(_relief_phrase(
                item, target, role, pos if pos in _PALACE_INDEX else None, natal, ref_year,
            ))
        if phrases:
            out[name] = "완화 글자: " + " / ".join(phrases)
    return out


def _with_year_pillars(periods: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """후보 기간 목록에 그 연도의 세운 간지를 보탠다(연도 라벨이 이미 있으면 그대로).

    연 단위 질문의 후보는 월 단위(월운 간지)라 세운 지지의 충(2031 辛亥 → 巳)이 목록에 없었다
    (2026-11-07 dry-run 실측). 세운 간지는 달력 계산값이라 여기서 더해도 엔진 계산 원칙을
    어기지 않는다. 순서: 원래 후보 순서 유지, 연도 항목은 그 연도의 첫 후보 앞에 둔다.
    """
    labels = {p for p, _ in periods}
    out: list[tuple[str, str]] = []
    added: set[str] = set()
    for period, ganji in periods:
        year = period[:4]
        if year.isdigit() and year not in labels and year not in added:
            stem, branch = year_ganzi(int(year))
            out.append((year, f"{stem.value}{branch.value}"))
            added.add(year)
        out.append((period, ganji))
    return out


def luck_clash_relief_block(
    result: ManseV2Result,
    periods: list[tuple[str, str]],
    reference_year: int | None = None,
) -> list[str]:
    """후보 기간의 운 지지가 원국 용·희신 글자를 충할 때의 완화 글자 블록(채팅 말미·리포트 공용).

    Args:
        result: 본인 명식.
        periods: (기간 라벨, 운 간지) 목록 — 같은 간지는 한 번만, 후보 순서 유지.
        reference_year: 세운 탐색 시작 연도(기본 올해).

    Returns:
        머리말 + 줄 목록. 조건에 맞는 충이 없으면 빈 목록(블록 없음).
    """
    from .event_scoring import favorability_map  # 지역 import — 순환 회피

    if result.pillars is None or not periods:
        return []
    fav = favorability_map(result)
    if not fav:
        return []
    ref_year = reference_year or date.today().year
    natal = _natal_branch_positions(result)
    by_target = _relief_by_target()
    lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    for period, ganji in _with_year_pillars(periods):
        if not ganji or len(ganji) < 2:
            continue
        luck_branch = ganji[1]
        for pos, nb in natal:
            pair = frozenset({luck_branch, nb})
            if pair not in BRANCH_CLASHES or (luck_branch, nb) in seen:
                continue
            role = _role_of_branch(nb, fav)
            if role not in _RELIEF_ROLES:
                continue
            item = by_target.get((pair, nb))
            if item is None:
                continue
            seen.add((luck_branch, nb))
            name = PAIR_NAME_KO.get(pair, "충")
            phrase = _relief_phrase(
                item, nb, role, pos, natal, ref_year, luck_branch=luck_branch,
            )
            lines.append(
                f"- {period} {ganji} {name}(운 {luck_branch} → 원국 {_PALACE_KO[pos]} {nb}): "
                f"{phrase}"
            )
            if len(lines) >= _MAX_LINES:
                break
        if len(lines) >= _MAX_LINES:
            break
    if not lines:
        return []
    return [RELIEF_BLOCK_HEADER, *lines]
