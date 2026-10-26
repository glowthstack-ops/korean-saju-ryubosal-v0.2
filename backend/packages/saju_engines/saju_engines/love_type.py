"""연애 유형 5종(십성군) 분류 — 외부 강의 「연애운 셀프 리딩 2탄」 번역층(2026-10-25 데굴님 승인).

SSOT: doc/v2_2/EXTERNAL_TEXT_GAP_LOVE_TIMING.md P2-6. 판정 순서(강의 1~3단계)
  1) 같은 십성군의 가시 글자(천간 + 지지 본기) ≥3 → 그 군(둘 이상이면 많은 쪽이 주, 다음이 부)
  2) 없으면 간여지동 기둥(천간·지지 본기 같은 군) → 그 군. 1)이 있고 2)가 다른 군이면 부 유형
  3) 둘 다 없으면 월지(≤50세) / 일지(51세+) 본기 군 — 나이 분기는 강의의 20~37/38+ 대신 **100세
     밴드**(`time_parser.LIFE_STAGE_AGE_RANGES`, 2026-08-07 데굴님 확정)로 번역. 나이 미상이면 월지.
서술 재료는 `dictionaries/interpretations/love_types.json`. 점수·판정 비개입(서술 전용).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from saju_shared_types.manse_result import ManseV2Result

from .time_parser import LIFE_STAGE_AGE_RANGES

_LOVE_TYPES_PATH = (
    Path(__file__).resolve().parents[3] / "dictionaries" / "interpretations" / "love_types.json"
)
#: 십성 → 군(한글) — 사전 group 키와 동일.
TEN_GOD_GROUP_KO: dict[str, str] = {
    "비견": "비겁", "겁재": "비겁", "식신": "식상", "상관": "식상", "편재": "재성", "정재": "재성",
    "편관": "관성", "정관": "관성", "편인": "인성", "정인": "인성",
}
#: 동률 시 우선 순서(강의 설명 순서).
_GROUP_ORDER = ("관성", "재성", "비겁", "식상", "인성")
#: 1단계 임계 — 같은 군 가시 글자 수.
LOVE_TYPE_COUNT_THRESHOLD = 3
#: 3단계 나이 분기 — 청년(≤50) 월지 / 중년 이상(51+) 일지(100세 밴드).
_MONTH_BRANCH_MAX_AGE = LIFE_STAGE_AGE_RANGES["청년"][1]


@dataclass(frozen=True)
class LoveTypeResult:
    """연애 유형 분류 결과(서술 전용)."""

    primary: str  # 군(한글) — 빈 문자열이면 미분류(명식 없음)
    secondary: str = ""  # 부 유형(강의: 두 유형까지 해당 가능)
    basis: str = ""  # 판정 근거 한 줄(단계·글자 수·기둥)
    stage: int = 0  # 적용 단계 1~3
    later_shift: str = ""  # 3단계에서 월지≠일지일 때 51세 이후 전환 안내


def load_love_types() -> dict[str, dict]:
    """연애 유형 사전 → {군: 항목}. reviewed 와 무관하게 전부 돌려준다(검수는 실답으로)."""
    return dict(_load_love_types_cached())


@lru_cache(maxsize=1)
def _load_love_types_cached() -> dict[str, dict]:
    data = json.loads(_LOVE_TYPES_PATH.read_text(encoding="utf-8"))
    return {item["group"]: item for item in data["items"]}


def age_from_result(result: ManseV2Result, today: date) -> int | None:
    """입력 요약의 생년월일(ISO)로 만 나이를 구한다(없거나 파싱 불가면 None)."""
    raw = result.input_summary.get("birth_date") if result.input_summary else None
    if not isinstance(raw, str):
        return None
    try:
        birth = date.fromisoformat(raw[:10])
    except ValueError:
        return None
    age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    return age if age >= 0 else None


def classify_love_type(result: ManseV2Result, age: int | None = None) -> LoveTypeResult:
    """강의 1~3단계로 연애 유형(십성군)을 정한다 — 서술 전용, 점수·판정 비개입.

    Args:
        result: 만세 결과(pillars 필수 — 없으면 미분류).
        age: 만 나이(3단계 월지/일지 분기용). None 이면 월지 기준으로 두고 일지 전환을 안내한다.

    Returns:
        LoveTypeResult(primary·secondary·basis·stage).
    """
    p = result.pillars
    if p is None or p.month is None or p.day is None:
        return LoveTypeResult(primary="")
    pillars = [("연", p.year), ("월", p.month), ("일", p.day), ("시", p.hour)]
    counts: dict[str, int] = dict.fromkeys(_GROUP_ORDER, 0)
    ganyeo: list[tuple[str, str]] = []  # (기둥, 군)
    for name, pil in pillars:
        if pil is None:
            continue
        sg = TEN_GOD_GROUP_KO.get(pil.stem_ten_god or "", "")
        bg = TEN_GOD_GROUP_KO.get(pil.branch_main_ten_god or "", "")
        if sg:
            counts[sg] += 1
        if bg:
            counts[bg] += 1
        if sg and sg == bg:
            ganyeo.append((name, sg))
    # 1단계 — 같은 군 ≥3(많은 순, 동률은 강의 순서).
    ranked = sorted(
        (g for g in _GROUP_ORDER if counts[g] >= LOVE_TYPE_COUNT_THRESHOLD),
        key=lambda g: (-counts[g], _GROUP_ORDER.index(g)),
    )
    if ranked:
        primary = ranked[0]
        secondary = ranked[1] if len(ranked) > 1 else ""
        basis = f"1단계 — {primary} 가시 글자 {counts[primary]}개(천간·지지 본기)"
        if not secondary:
            # 2단계 간여지동이 다른 군이면 부 유형(강의 예시 3: 재성 3 + 비겁 간여지동).
            other = next((g for _n, g in ganyeo if g != primary), "")
            if other:
                secondary = other
                basis += f" · 부 유형 {other}(간여지동 기둥)"
        else:
            basis += f" · 부 유형 {secondary}({counts[secondary]}개)"
        return LoveTypeResult(primary=primary, secondary=secondary, basis=basis, stage=1)
    # 2단계 — 간여지동 기둥(월·일·시·연 순).
    order = {"월": 0, "일": 1, "시": 2, "연": 3}
    if ganyeo:
        name, g = sorted(ganyeo, key=lambda x: order[x[0]])[0]
        others = [og for _n, og in ganyeo if og != g]
        secondary = others[0] if others else ""
        basis = f"2단계 — {name}주 간여지동({g})"
        if secondary:
            basis += f" · 부 유형 {secondary}(간여지동 기둥)"
        return LoveTypeResult(primary=g, secondary=secondary, basis=basis, stage=2)
    # 3단계 — 월지(≤50세) / 일지(51세+) 본기 군(100세 밴드).
    mg = TEN_GOD_GROUP_KO.get(p.month.branch_main_ten_god or "", "")
    dg = TEN_GOD_GROUP_KO.get(p.day.branch_main_ten_god or "", "")
    use_day = age is not None and age > _MONTH_BRANCH_MAX_AGE
    primary = (dg if use_day else mg) or mg or dg
    if not primary:
        return LoveTypeResult(primary="")
    if use_day:
        basis = f"3단계 — 일지 본기({dg}), 만 {age}세(51세 이상·100세 밴드 중년) 기준"
    else:
        who = f"만 {age}세" if age is not None else "나이 미상"
        basis = f"3단계 — 월지 본기({mg}), {who}(50세 이하 기준)"
    later = ""
    if mg and dg and mg != dg and not use_day:
        later = f"51세 이후(100세 밴드 중년)는 일지 본기 {dg} 유형 쪽으로 옮겨 읽을 수 있음"
    elif mg and dg and mg == dg:
        later = "월지·일지가 같은 군 — 나이와 무관하게 같은 유형"
    return LoveTypeResult(primary=primary, basis=basis, stage=3, later_shift=later)


def love_type_lines(lt: LoveTypeResult) -> list[str]:
    """[연애 유형] 블록 — 사전 문구(심리·바라는 것·공략·주의)와 판정 근거(경향·단정 아님)."""
    if not lt.primary:
        return []
    items = load_love_types()
    item = items.get(lt.primary)
    if item is None:
        return []
    lines = [
        "[연애 유형 — 십성군 분류(강의 번역층, 경향·단정 아님). 한 사람에 둘까지 해당할 수 있고 "
        "운에 따라 달라질 수 있는 결. 유형명은 '○○형'으로 쓰고 상대 평가·낙인에 쓰지 말 것]",
        f"유형: {lt.primary}형 — 근거: {lt.basis}",
        f"  · 십성 의미: {item['meaning']}",
        f"  · 연애 심리: {item['psychology']}",
        f"  · 중시하는 것: {item['wants']}",
        f"  · 상대가 이 유형일 때 다가가는 법: {item['approach']}",
        f"  · 주의: {item['caution']}",
    ]
    if lt.later_shift:
        lines.append(f"  · {lt.later_shift}")
    if lt.secondary and (sec := items.get(lt.secondary)) is not None:
        lines.append(
            f"부 유형: {lt.secondary}형 — {sec['meaning']} · 심리 요지: "
            + sec["psychology"].split(".")[0]
        )
    return lines


def absent_group_note(group_ko: str) -> str:
    """해당 십성군 미투출 시 결(사전 absent) — 없으면 빈 문자열."""
    item = load_love_types().get(group_ko)
    return str(item.get("absent", "")) if item else ""


__all__ = [
    "LOVE_TYPE_COUNT_THRESHOLD",
    "TEN_GOD_GROUP_KO",
    "LoveTypeResult",
    "absent_group_note",
    "age_from_result",
    "classify_love_type",
    "load_love_types",
    "love_type_lines",
]
