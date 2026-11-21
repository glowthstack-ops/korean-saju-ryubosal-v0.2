"""세운 12신살 결 층 — 띠(연지)·일지 삼합국 기준 그 해의 결(2026-11-21 데굴님 승인, docs/18 §9).

삼재(연지 기준 역마·육해·화개 3종)의 일반화다. 그 해 세운 지지가 띠(연지) 삼합국과 일지 삼합국에서
각각 어느 12신살 자리에 놓이는지를 공용 표(`twelve_sinsal.BASE_MAPS`)로 읽고, 사전
(`interpretations/year_sinsal_text.json`)의 장면·태도 문구를 붙여 렌더한다.

- 판정은 표 조회뿐이다(신규 명리 규칙 없음). 엔진이 덧붙이는 사실은 넷이다.
  ① 두 기준의 12신살명과 일치 여부(띠와 일지가 같은 삼합국이면 같다)
  ② 띠 기준 3년 흐름(앞 해 → 이 해 → 다음 해)과 삼재 단계 병기
  ③ 화개 해의 삼합 주기 — 같은 삼합국 시작 해(지살, 8년 전)·한창 해(장성, 4년 전)
  ④ 천살 해의 '바깥 주체' 단서 — 일간 기준 세운 천간·지지 십성, 천을귀인 동반 여부
- 기준 자리 읽는 법: 띠(연지) 기준 = 바깥·사회 쪽, 일지 기준 = 가까운 관계·생활 쪽(궁위 통설).
- **서술 전용(inert)** — 점수·후보·역할 판정에 관여하지 않는다. 신살은 보조 자료이며 길흉·사건 종류·
  시기는 용희기신·십성·사건 후보가 정한다. 삼재 해의 성격(복/평/악)은 삼재 블록이 정본이다.
- 사전 문구가 있는 것은 辰戌丑未 해의 4종(화개살·월살·천살·반안살)이고, 나머지 8종은
  `sinsal_text.json` 의 뜻 한 문장으로 폴백한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from saju_manse_analysis.sinsal import sinsal_catalog as _cat

from saju_manse_core.calendar.sexagenary_cycle import year_ganzi
from saju_shared_types.constants import main_hidden_stem, ten_god
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.twelve_sinsal import (
    SAMJAE_BY_SINSAL,
    SAMJAE_LABEL_KO,
    relative_twelve_sinsal,
    trine_group_label,
)

_DICT_DIR = Path(__file__).resolve().parents[3] / "dictionaries" / "interpretations"
_TEXT_FILE = "year_sinsal_text.json"
_SINSAL_TEXT_FILE = "sinsal_text.json"

#: 한 블록에 싣는 최대 연도 수(토큰 예산 — 해마다 2종까지 문구가 붙는다).
MAX_YEARS = 3
#: 화개 해 기준 같은 삼합국 시작 해(지살)·한창 해(장성)까지의 햇수 — 생지→왕지→고지는 4년 간격.
_CYCLE_START_OFFSET = 8
_CYCLE_PEAK_OFFSET = 4
#: sinsal_text.json 이 다른 표시명을 쓰는 12신살(년살 = 도화).
_SINSAL_TEXT_ALIAS: dict[str, str] = {"년살": "도화"}

YEAR_SINSAL_HEADER = (
    "[세운 12신살 결 — 띠(연지)·일지 삼합국 기준 · 보조 서술(점수·판정 아님) · 입춘 기준 세운]"
)
YEAR_SINSAL_INSTRUCTION = (
    "[세운 12신살 지침] 12신살은 그 해 흐름의 결을 더하는 보조 자료다 — 길흉·사건 종류·시기는 "
    "용희기신·십성·사건 후보가 정하며, 이 블록만으로 사건을 단정하지 말 것. "
    "①띠 기준은 바깥·사회 쪽, 일지 기준은 가까운 관계·생활 쪽 체감이다. 두 기준이 다르면 "
    "'밖에서는 ~, 가까운 관계와 생활에서는 ~'처럼 나눠 말하고 한쪽을 전체로 일반화하지 말 것. "
    "②장면은 질문 주제와 닿는 것 1~2개만 골라 '~할 수 있다' 가능성으로 쓰고 전부 나열하지 말 것. "
    "③'태도' 문장은 조언으로 한 번만. ④삼재 해의 성격(복/평/악)은 삼재 블록이 정본이다. "
    "⑤살 이름으로 겁주지 말 것('천살이라 큰일' 류 금지), 이 블록에 없는 해의 12신살을 새로 "
    "계산하지 말 것. ⑥'주기'의 연도는 그 해에 실제로 무슨 일이 있었는지 모르므로 '그 무렵 시작한 "
    "일이 있다면'처럼 조건으로만 쓸 것. ⑦출처·강의 언급 금지."
)


@lru_cache(maxsize=2)
def load_year_sinsal_text(path: str = "") -> dict:
    """`interpretations/year_sinsal_text.json` 원본(캐시). 스키마·린트는 dictionaries.py."""
    p = Path(path) if path else _DICT_DIR / _TEXT_FILE
    return json.loads(p.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _sinsal_meanings() -> dict[str, str]:
    """`sinsal_text.json` 이름 → 뜻 한 문장(문구 없는 12신살의 폴백)."""
    raw = json.loads((_DICT_DIR / _SINSAL_TEXT_FILE).read_text(encoding="utf-8"))
    return {item["name"]: item["meaning"] for item in raw["items"]}


@dataclass(frozen=True)
class YearSinsalRow:
    """세운 1건의 12신살 사실 — 표 조회 결과(판정·점수 아님).

    Attributes:
        year: 달력연도(입춘 기준 세운).
        stem: 세운 천간.
        branch: 세운 지지.
        year_base: 원국 연지(띠).
        day_base: 원국 일지.
        by_year: 띠(연지) 삼합국 기준 12신살명.
        by_day: 일지 삼합국 기준 12신살명.
        flow: 띠 기준 3년 흐름 — (연도, 세운 지지, 12신살명) 앞 해·이 해·다음 해.
        samjae_label: 띠 기준 이름이 삼재 3종이면 들삼재/눌삼재/날삼재, 아니면 None.
        stem_god: 일간 기준 세운 천간 십성(한글).
        branch_god: 일간 기준 세운 지지 본기 십성(한글).
        cheoneul: 세운 지지가 일간의 천을귀인 글자인가.
    """

    year: int
    stem: Stem
    branch: Branch
    year_base: Branch
    day_base: Branch
    by_year: str
    by_day: str
    flow: tuple[tuple[int, Branch, str], ...]
    samjae_label: str | None
    stem_god: str
    branch_god: str
    cheoneul: bool

    @property
    def same(self) -> bool:
        """두 기준의 12신살이 같은가(띠와 일지가 같은 삼합국)."""
        return self.by_year == self.by_day


def build_year_sinsal(result: ManseV2Result, year: int) -> YearSinsalRow | None:
    """그 해 세운 지지의 띠·일지 기준 12신살 사실을 만든다. 원국이 없으면 None.

    Args:
        result: 만세력 결과(원국 연지·일지·일간 필요).
        year: 달력연도(입춘 기준 세운 간지로 판정 — 삼재와 같은 경계).
    """
    pillars = result.pillars
    if pillars is None:
        return None
    year_base = Branch(pillars.year.branch)
    day_base = Branch(pillars.day.branch)
    day_stem = Stem(pillars.day.stem)
    stem, branch = year_ganzi(year)
    by_year = relative_twelve_sinsal(year_base, branch)
    flow = tuple(
        (y, year_ganzi(y)[1], relative_twelve_sinsal(year_base, year_ganzi(y)[1]))
        for y in (year - 1, year, year + 1)
    )
    stage = SAMJAE_BY_SINSAL.get(by_year)
    return YearSinsalRow(
        year=year, stem=stem, branch=branch, year_base=year_base, day_base=day_base,
        by_year=by_year, by_day=relative_twelve_sinsal(day_base, branch), flow=flow,
        samjae_label=SAMJAE_LABEL_KO[stage] if stage is not None else None,
        stem_god=str(ten_god(day_stem, stem).value),
        branch_god=str(ten_god(day_stem, main_hidden_stem(branch)).value),
        cheoneul=branch in _cat.CHEONEUL.get(day_stem, []),
    )


def _item_lines(
    row: YearSinsalRow, name: str, scope_label: str, items: dict[str, dict], *, compact: bool,
) -> list[str]:
    """12신살 1종의 문구 줄 — 사전 문구가 없으면 뜻 한 문장 폴백."""
    item = items.get(name)
    if item is None:
        meaning = _sinsal_meanings().get(_SINSAL_TEXT_ALIAS.get(name, name), "")
        return [f"  ▸ {name} [{scope_label}]: (뜻) {meaning}" if meaning
                else f"  ▸ {name} [{scope_label}]"]
    lines = [f"  ▸ {name} [{scope_label}]: {item['core']}"]
    if not compact:
        lines.append("    장면: " + " / ".join(item["scenes"]))
    lines.append(f"    태도: {item['stance']}")
    if item.get("cycle"):
        start, peak = row.year - _CYCLE_START_OFFSET, row.year - _CYCLE_PEAK_OFFSET
        lines.append(
            f"    주기: 같은 삼합국 시작 해 {start}년(지살) · 한창 해 {peak}년(장성살) → 이 해. "
            f"{item['cycle']}"
        )
    if item.get("who"):
        noble = " · 천을귀인 동반" if row.cheoneul else ""
        lines.append(
            f"    바깥의 주체: 이 해 운의 십성 — 천간 {row.stem} {row.stem_god} · "
            f"지지 {row.branch} {row.branch_god}{noble}. {item['who']}"
        )
    if item.get("contrast") and not compact:
        lines.append(f"    대비: {item['contrast']}")
    return lines


def format_year_sinsal_lines(
    result: ManseV2Result,
    years: list[int],
    *,
    current_year: int | None = None,
    compact: bool = False,
    dict_path: str = "",
) -> list[str]:
    """[세운 12신살 결] 블록 — 원국이 없거나 연도가 없으면 빈 목록.

    Args:
        result: 만세력 결과.
        years: 대상 연도(오름차순 권장). `MAX_YEARS` 까지만 싣는다.
        current_year: 올해 표식(◀ 올해)용. None 이면 표식 없음.
        compact: True 면 장면·대비 줄을 빼고 결·태도만 싣는다(사건 질문 맥락용).
        dict_path: 사전 경로(테스트용). 빈 문자열이면 리포 기본 사전.

    Returns:
        머리말(빈 줄 포함) + 읽는 법 + 연도별 줄. 지침(`YEAR_SINSAL_INSTRUCTION`)은 호출자가 붙인다.
    """
    rows = [
        row for y in list(dict.fromkeys(years))[:MAX_YEARS]
        if (row := build_year_sinsal(result, y)) is not None
    ]
    if not rows:
        return []
    text = load_year_sinsal_text(dict_path)
    scopes = {sc["id"]: sc for sc in text["scopes"]}
    items = {it["name"]: it for it in text["items"]}
    first = rows[0]
    lines = [
        "",
        YEAR_SINSAL_HEADER,
        f"읽는 법: {scopes['year']['label']}: {scopes['year']['text']} / "
        f"{scopes['day']['label']}: {scopes['day']['text']}",
        f"기준: 띠(연지) {first.year_base}({trine_group_label(first.year_base)}국) · "
        f"일지 {first.day_base}({trine_group_label(first.day_base)}국)",
    ]
    for row in rows:
        mark = " ◀ 올해" if current_year is not None and row.year == current_year else ""
        samjae = f"(= {row.samjae_label})" if row.samjae_label else ""
        if row.same:
            head = f"띠·일지 두 기준 모두 {row.by_year}{samjae} — {scopes['both']['text']}"
        else:
            head = f"띠 기준 {row.by_year}{samjae} · 일지 기준 {row.by_day}"
        lines.append(f"- {row.year}년 {row.stem}{row.branch}{mark}: {head}")
        lines.append(
            "  띠 기준 3년 흐름: "
            + " → ".join(f"{y} {b} {name}" for y, b, name in row.flow)
        )
        if row.same:
            lines += _item_lines(row, row.by_year, scopes["both"]["label"], items, compact=compact)
        else:
            lines += _item_lines(row, row.by_year, scopes["year"]["label"], items, compact=compact)
            lines += _item_lines(row, row.by_day, scopes["day"]["label"], items, compact=compact)
    return lines


__all__ = [
    "MAX_YEARS",
    "YEAR_SINSAL_HEADER",
    "YEAR_SINSAL_INSTRUCTION",
    "YearSinsalRow",
    "build_year_sinsal",
    "format_year_sinsal_lines",
    "load_year_sinsal_text",
]
