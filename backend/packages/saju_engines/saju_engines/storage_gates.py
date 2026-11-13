"""창고(入庫·開庫) 판정 — 서술 전용 (2026-11-13 데굴님 승인 "제안대로 진행").

배경: 辰戌丑未(사고·사묘)의 입고·개고는 "무엇이 갇혀 있는가 → 언제 열리는가 → 열렸을 때 득인가
실인가"로 읽는 통설인데, 엔진에는 조각만 있었다 — 원국 표지 3개(입묘·충개·개고), 재물 쪽 '묘고
충개고' 가산, 건강 쪽 세운 입묘. 무엇의 창고인지·운의 어느 층에서 열리고 닫히는지·득실은 판정하지
않았고 풀이 입력에도 실리지 않았다. 이 모듈이 그 판정을 하고 성립한 것만 줄로 낸다.

확정 규칙(SSOT `doc/v2_2/STORAGE_GATES.md`):
- **창고 대응은 오행 기준**: 辰=水, 戌=火·土, 丑=金, 未=木(현대 한국 통설·삼합의 고). 저장 오행을
  일간 기준 십성군으로 옮겨 재고·관고·인고·식상고·비겁고라 부른다.
- **원국 창고 상태**: 충(辰戌·丑未)으로 열림 / 형(丑戌·戌未)으로 열림(약) / 육합(辰酉·卯戌·子丑·
  午未)으로 묶임 / 저장 오행이 천간에 투출(이미 쓰는 중) / 닫힘.
- **개고는 계기**: 운 지지가 원국(또는 상위 운) 창고를 충·형하면 개고. 성사·횡재의 확정이 아니다 —
  《子平真詮》 17장 "四墓不忌刑沖，刑沖未必成格", "干既透，即不沖而亦得". 운 천간이 창고의 저장
  오행이면 투출(충 없이도 쓰임 — 같은 장 "己生辰月，壬透為財").
- **두 갈래를 모두 낸다**: [원국 발동](원국 창고가 운에 열림·묶임·투출) / [운 도래](운 지지가
  창고로 옴 — 원국 글자의 입고·열린 채 옴, 상위 운 창고를 하위 운이 열거나 묶거나 드러냄).
  운 창고로 들어가는 원국 글자에서 그 창고의 왕지는 뺀다(반합 — "論合不論墓").
- **층의 크기**: 대운 = 10년 배경, 세운 = 그 해의 계기, 월운 = 해마다 돌아오는 짧은 자극(단독으로
  큰 사건 금지 — 대운·세운과 겹칠 때 시점을 좁히는 용도). 읽는 법을 블록에 함께 싣고, 월운 줄이
  대운·세운과 같은 창고를 건드리면 줄 끝에 겹침 표지(`MONTH_OVERLAP_MARK`)를 엔진이 붙인다.
- **입고**: 운 지지가 창고이고 열려 있지 않으면, 원국에 드러난 그 오행(천간·지지 본기)이 창고로
  들어간다. 뜻은 세력으로 가른다 — 강하면(과다) 쌓이는 庫, 약하면(결핍) 갇히는 墓(통설 "旺者入庫
  弱者入墓"). 세력은 엔진 값을 읽는다 — 강 = 보정 세력 30%+(억부 '多' 임계) 또는 과다 목록,
  약 = 결핍 목록(9% 미만).
- **육합은 묶임(닫힘)만** 본다. 합으로 열린다는 설은 채택하지 않는다(기준이 자료마다 다르다).
- **득실**은 저장 오행의 용희기구한 역할을 병기할 뿐이다(길흉 판정은 용신·기신 층).

순수 함수다. 점수·사건 선발·길흉 판정에 관여하지 않는다. 시주 미상이면 판정하지 않는다(용희신·
십성 배치가 미확정). 문구는 사전 `interpretations/storage_gate_text.json` 에서 고르기만 한다.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

from saju_shared_types.constants import STEM_ELEMENT, group_elements, hidden_stems_for
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.structure_patterns import PatternTimeline

from .event_scoring import favorability_map

_TEXT_PATH = (
    Path(__file__).resolve().parents[3]
    / "dictionaries"
    / "interpretations"
    / "storage_gate_text.json"
)

#: 창고 지지 → 저장 오행(오행 기준 — 土는 戌).
STORE: dict[str, tuple[str, ...]] = {
    "辰": ("水",), "戌": ("火", "土"), "丑": ("金",), "未": ("木",),
}
#: 창고끼리의 충(문이 열림).
_CLASH: dict[str, str] = {"辰": "戌", "戌": "辰", "丑": "未", "未": "丑"}
#: 창고끼리의 형(충이 아닌 쌍 — 약하게 열림).
_PUNISH: frozenset[frozenset[str]] = frozenset({frozenset({"丑", "戌"}), frozenset({"戌", "未"})})
#: 창고의 육합 짝(묶임).
_HAP6: dict[str, str] = {"辰": "酉", "戌": "卯", "丑": "子", "未": "午"}
#: 창고와 반합을 이루는 왕지 — 지지끼리는 합으로 보고 입고로 보지 않는다("論合不論墓").
_HALF_HAP_PEAK: dict[str, str] = {"辰": "子", "戌": "午", "丑": "酉", "未": "卯"}
#: 월운 줄 끝에 붙는 표지 — 같은 창고가 대운·세운 줄에도 있을 때만(시점을 좁히는 단서).
MONTH_OVERLAP_MARK = " 〔대운·세운과 같은 창고 — 시점 단서〕"
_GROUP_KO: dict[str, str] = {
    "wealth": "재고", "officer": "관고", "resource": "인고", "output": "식상고", "peer": "비겁고",
}
#: 입고의 뜻을 가르는 세력 임계(보정 세력 %). 강 = 억부의 '多' 임계와 같은 30% 이상(또는 과다
#: 목록), 약 = 결핍 목록(9% 미만). 그 사이는 '거두어 보관'으로 중립 서술.
_STRONG_PERCENT = 30.0
_GROUP_SHORT: dict[str, str] = {
    "wealth": "재성", "officer": "관성", "resource": "인성", "output": "식상", "peer": "비겁",
}
_POS_STEM_KO: dict[str, str] = {"year": "연간", "month": "월간", "day": "일간", "hour": "시간"}
_POS_BRANCH_KO: dict[str, str] = {"year": "연지", "month": "월지", "day": "일지", "hour": "시지"}
_GOOD_ROLES: frozenset[str] = frozenset({"용신", "희신"})
_BAD_ROLES: frozenset[str] = frozenset({"기신", "구신"})


@lru_cache(maxsize=2)
def load_storage_gate_text(path: Path = _TEXT_PATH) -> dict[str, str]:
    """`interpretations/storage_gate_text.json` → id → 문구(캐시). 스키마·린트는 dictionaries.py."""
    doc = json.loads(path.read_text("utf-8"))
    return {str(it["id"]): str(it["text"]) for it in doc["items"]}


class _Chart:
    """원국에서 창고 판정에 쓰는 사실만 뽑아 둔 것."""

    def __init__(self, result: ManseV2Result) -> None:
        pillars = result.pillars
        assert pillars is not None and pillars.hour is not None
        self.stems: list[tuple[str, str]] = []  # (자리, 천간) — 일간 포함
        self.branches: list[tuple[str, str]] = []  # (자리, 지지)
        for pos in ("year", "month", "day", "hour"):
            p = getattr(pillars, pos)
            self.stems.append((pos, p.stem))
            self.branches.append((pos, p.branch))
        ge = group_elements(STEM_ELEMENT[Stem(pillars.day.stem)])
        self.group_of_element: dict[str, str] = {str(e): g for g, e in ge.items()}
        self.role_of: dict[str, str] = favorability_map(result)
        fe = result.force_analysis.five_elements if result.force_analysis is not None else None
        self.excessive: set[str] = set(fe.excessive_elements or []) if fe is not None else set()
        self.deficient: set[str] = set(fe.deficient_elements or []) if fe is not None else set()
        self.percent: dict[str, float] = (
            {str(k): float(v) for k, v in (fe.effective_percent or {}).items()}
            if fe is not None else {}
        )

    def branch_set(self) -> set[str]:
        return {b for _pos, b in self.branches}

    def store_name(self, branch: str) -> str:
        """창고 지지 → '水 창고·재고' 식 이름(戌은 '火 창고·인고 / 土 창고·비겁고')."""
        parts = [
            f"{el} 창고·{_GROUP_KO.get(self.group_of_element.get(el, ''), '창고')}"
            for el in STORE[branch]
        ]
        return " / ".join(parts)

    def element_tag(self, el: str) -> str:
        """오행 → '水(재성·구신)' 식 표기(역할 미정이면 십성군만)."""
        grp = _GROUP_SHORT.get(self.group_of_element.get(el, ""), "")
        role = self.role_of.get(el, "")
        inner = "·".join(x for x in (grp, role) if x)
        return f"{el}({inner})" if inner else el

    def role_class(self, el: str) -> str:
        role = self.role_of.get(el, "")
        return "good" if role in _GOOD_ROLES else ("bad" if role in _BAD_ROLES else "neutral")

    def strength_class(self, el: str) -> str:
        if el in self.excessive or self.percent.get(el, 0.0) >= _STRONG_PERCENT:
            return "strong"
        return "weak" if el in self.deficient else "mid"

    def visible(self, el: str) -> list[str]:
        """원국에 드러난 그 오행의 글자(천간 + 지지 본기) — '연간 壬', '월지 亥' 식."""
        out = [
            f"{_POS_STEM_KO[pos]} {st}" for pos, st in self.stems
            if str(STEM_ELEMENT[Stem(st)]) == el
        ]
        for pos, br in self.branches:
            main = next(
                (hs for hs, kind, _w in hidden_stems_for(Branch(br)) if kind.value == "main"), None
            )
            if main is not None and str(STEM_ELEMENT[main]) == el:
                out.append(f"{_POS_BRANCH_KO[pos]} {br}")
        return out

    def revealed_stems(self, el: str) -> list[str]:
        """원국 천간에 투출한 그 오행의 글자."""
        return [
            f"{_POS_STEM_KO[pos]} {st}" for pos, st in self.stems
            if str(STEM_ELEMENT[Stem(st)]) == el
        ]


def natal_storage_lines(result: ManseV2Result) -> list[str]:
    """원국의 창고 지지마다 '무엇의 창고인가·지금 상태' 한 줄.

    Returns:
        창고 지지가 없으면 그 사실 한 줄. 시주 미상이면 빈 목록.
    """
    if result.pillars is None or result.pillars.hour is None:
        return []
    chart = _Chart(result)
    text = load_storage_gate_text()
    by_branch: dict[str, list[str]] = {}
    for pos, br in chart.branches:
        if br in STORE:
            by_branch.setdefault(br, []).append(_POS_BRANCH_KO[pos])
    if not by_branch:
        return ["원국 창고: 辰戌丑未 없음 — 창고 작용은 운에서 창고 지지가 올 때만 생긴다"]
    have = chart.branch_set()
    out: list[str] = []
    for br, spots in by_branch.items():
        states: list[str] = []
        if _CLASH[br] in have:
            states.append(f"원국 {_CLASH[br]}과 충 — 이미 열려 있음")
        states += [
            f"원국 {other}과 형 — 약하게 열려 있음"
            for other in sorted(have) if frozenset({br, other}) in _PUNISH
        ]
        if _HAP6[br] in have:
            states.append(f"원국 {_HAP6[br]}과 {text['bound']}")
        for el in STORE[br]:
            shown = chart.revealed_stems(el)
            if shown:
                states.append(f"{el} 천간 투출({'·'.join(shown)}) — 이미 쓰는 중")
        if not states:
            states.append("닫힘(충·형이 와야 열리고, 같은 오행 천간이 오면 드러난다)")
        tags = "·".join(chart.element_tag(el) for el in STORE[br])
        out.append(
            f"원국 창고 {br}({'·'.join(spots)}) = {chart.store_name(br)} · 저장 {tags}"
            f" · 상태: {' / '.join(states)}"
        )
    return out


def _period_events(
    chart: _Chart, stem: str, branch: str, upper: Sequence[tuple[str, str]]
) -> list[tuple[str, str]]:
    """운 기둥 하나(천간·지지)가 창고에 일으키는 작용 목록.

    두 갈래를 모두 낸다(데굴님 2026-11-13 "운에서 온 것에 대한 액션과 원국 내에 있는 것이 운에
    의해 발생한 액션 모두"):
    - **[원국 발동]** 원국에 본래 가진 창고가 이 운을 만나 움직임 — 충·형으로 개고, 육합으로
      묶임, 창고 안 글자가 운 천간으로 투출.
    - **[운 도래]** 운에서 온 것의 작용 — 운 지지가 창고로 옴(원국의 드러난 글자가 그리로 입고 /
      충 맞아 열린 채 옴), 상위 운의 창고를 하위 운이 열거나 묶거나 드러냄.

    운에서 온 글자가 원국 창고로 '입묘'한다는 판정은 하지 않는다 — 천간은 《子平真詮》이 투출로
    읽고(壬透), 지지끼리는 왕지+창고(子辰·午戌·酉丑·卯未)가 반합이라 "論合不論墓", 생지 입묘
    (亥辰·寅未·申丑·巳戌)는 맹파 단독 근거다(STORAGE_GATES.md §8).

    Args:
        upper: 이 층보다 위의 운 지지 — (층 이름, 지지). 대운은 빈 목록, 세운은 대운, 월운은
            대운·세운.

    Returns:
        (창고 지지, 작용 줄) 목록 — 창고 지지는 층 사이 겹침 판정에 쓴다.
    """
    text = load_storage_gate_text()
    have = chart.branch_set()
    natal: list[tuple[str, str]] = []  # [원국 발동]
    luck: list[tuple[str, str]] = []  # [운 도래]

    def _open_phrase(el: str) -> str:
        return f"{chart.element_tag(el)} {text['open_' + chart.role_class(el)]}"

    def _enter_phrase(el: str) -> str:
        return text[f"enter_{chart.strength_class(el)}_{chart.role_class(el)}"]

    stem_el = str(STEM_ELEMENT[Stem(stem)])
    targets = [("원국", b) for b in sorted(have & set(STORE))]
    targets += [(layer, b) for layer, b in upper if b in STORE]
    for owner, store in targets:
        sink = natal if owner == "원국" else luck
        name = chart.store_name(store)
        # ① 창고를 이 운 지지가 건드림(충·형 → 개고, 육합 → 묶임).
        if _CLASH[store] == branch:
            opened = " · ".join(_open_phrase(el) for el in STORE[store])
            sink.append((store, f"{owner} {store}({name})을 충 → 개고: {opened}"))
        elif frozenset({store, branch}) in _PUNISH:
            opened = " · ".join(_open_phrase(el) for el in STORE[store])
            sink.append((store, f"{owner} {store}({name})을 형 → 개고(약): {opened}"))
        elif _HAP6[store] == branch:
            sink.append((store, f"{owner} {store}({name})이 {text['bound']}"))
        # ② 운 천간의 오행이 창고의 저장 오행 → 투출(《子平真詮》 17장 "己生辰月，壬透為財" —
        #    辰의 水가 壬으로 드러난 것도 투출로 본다. 양간을 '입묘'로 읽는 설은 채택하지 않았다).
        if stem_el in STORE[store]:
            sink.append((
                store,
                f"운 천간 {stem}이 {owner} {store}의 {chart.element_tag(stem_el)}을 드러냄 → "
                f"{text['tougan']}",
            ))
    # ④ 운 지지 자체가 창고 — 열린 채 오면 개고, 아니면 원국의 드러난 글자가 입고.
    if branch in STORE:
        name = chart.store_name(branch)
        openers = [f"원국 {_CLASH[branch]}"] if _CLASH[branch] in have else []
        openers += [f"{layer} {b}" for layer, b in upper if b == _CLASH[branch]]
        if openers:
            opened = " · ".join(_open_phrase(el) for el in STORE[branch])
            luck.append((
                branch,
                f"운 창고 {branch}({name})이 {'·'.join(openers)}과 충 — 열린 채 들어옴(개고): "
                f"{opened}",
            ))
        else:
            # 원국에 드러난 그 오행이 없으면 들어갈 글자가 없다 — 작용이 아니므로 줄을 내지 않는다.
            # 그 창고의 왕지(子辰·午戌·酉丑·卯未)는 반합이라 입고로 세지 않는다(論合不論墓).
            wang = _HALF_HAP_PEAK[branch]
            for el in STORE[branch]:
                shown = [w for w in chart.visible(el) if not w.endswith(f" {wang}")]
                if not shown:
                    continue
                luck.append((
                    branch,
                    f"운 창고 {branch}({name})이 옴 → 원국에 드러난 {chart.element_tag(el)}"
                    f"[{'·'.join(shown)}]이 입고: {_enter_phrase(el)}",
                ))
    return [(st, f"[원국 발동] {ev}") for st, ev in natal] + [
        (st, f"[운 도래] {ev}") for st, ev in luck
    ]


def storage_gate_lines(
    result: ManseV2Result, timelines: Sequence[PatternTimeline], labels: Sequence[str]
) -> list[str]:
    """질문 기간(월·연 라벨)의 창고 작용을 층별 줄로 낸다 — 대운 → 세운 → 월운.

    `pattern_transit.window_structure_lines` 와 같은 타임라인·같은 라벨 규칙을 쓴다(대운 줄은
    간지마다 한 번, 세운 줄은 해마다 한 번). 작용이 없는 층은 줄을 내지 않는다.

    Args:
        result: 만세 결과(시주 있음).
        timelines: 기간이 걸친 절기 연도의 타임라인(대운·세운·월운 간지를 읽는다).
        labels: 기간 라벨 — 월(YYYY-MM)은 월운, 연(YYYY)은 세운.

    Returns:
        층별 작용 줄. 시주 미상이면 빈 목록.
    """
    if result.pillars is None or result.pillars.hour is None:
        return []
    chart = _Chart(result)
    wanted = list(dict.fromkeys(labels))
    year_labels = {lb for lb in wanted if len(lb) == 4}
    out: list[str] = []
    seen_daewoon: set[str] = set()
    seen_year: set[int] = set()
    for tl in timelines:
        # 이 타임라인의 대운·세운이 건드린 창고 — 월운 줄의 겹침 표지 판정에 쓴다.
        upper_stores: set[str] = set()
        if tl.hour_unknown:
            continue
        idx = {label: i for i, label in enumerate(tl.month_labels)}
        hit = [label for label in wanted if label in idx]
        if not hit and str(tl.year) not in year_labels:
            continue
        upper: list[tuple[str, str]] = []
        dw = tl.daewoon_ganji or ""
        if len(dw) == 2:
            dw_events = _period_events(chart, dw[0], dw[1], [])
            upper_stores |= {st for st, _ev in dw_events}
            if dw not in seen_daewoon:
                seen_daewoon.add(dw)
                out += [f"대운 {dw}: {ev}" for _st, ev in dw_events]
            upper.append(("대운", dw[1]))
        yg = tl.year_ganji or ""
        if len(yg) == 2:
            year_events = _period_events(chart, yg[0], yg[1], upper)
            upper_stores |= {st for st, _ev in year_events}
            if tl.year not in seen_year:
                seen_year.add(tl.year)
                out += [f"세운 {yg} {tl.year}년: {ev}" for _st, ev in year_events]
            upper = [*upper, ("세운", yg[1])]
        for label in hit:
            i = idx[label]
            mg = tl.month_ganji[i] if i < len(tl.month_ganji) else ""
            if len(mg) != 2:
                continue
            out += [
                f"월운 {label} {mg}: {ev}{MONTH_OVERLAP_MARK if st in upper_stores else ''}"
                for st, ev in _period_events(chart, mg[0], mg[1], upper)
            ]
    return out


def storage_gate_block(
    result: ManseV2Result, timelines: Sequence[PatternTimeline], labels: Sequence[str]
) -> list[str]:
    """LLM 입력 블록 — 머리말 + 원국 창고 상태 + 기간별 작용 + 서술 규칙.

    채팅 말미 블록과 테마 리포트·총운 대운 페이지가 같은 함수를 쓴다. 원국에 창고가 없고 기간에도
    작용이 없으면 빈 목록(블록을 싣지 않는다).
    """
    if result.pillars is None or result.pillars.hour is None:
        return []
    text = load_storage_gate_text()
    natal = natal_storage_lines(result)
    period = storage_gate_lines(result, timelines, labels)
    has_natal_store = any(b in STORE for b in _Chart(result).branch_set())
    if not has_natal_store and not period:
        return []
    guide: list[str] = []
    if period:
        # 실린 줄의 층·분류에 해당하는 읽는 법만 싣는다(층의 크기·원국 발동과 운 도래의 구분).
        for prefix, key in (
            ("대운 ", "layer_daewoon"), ("세운 ", "layer_year"), ("월운 ", "layer_month"),
        ):
            if any(ln.startswith(prefix) for ln in period):
                guide.append(text[key])
        for tag, key in (("[원국 발동]", "class_natal"), ("[운 도래]", "class_luck")):
            if any(tag in ln for ln in period):
                guide.append(text[key])
    return [text["header"], *natal, *(period or [text["none"]]), *guide, text["rule"]]
