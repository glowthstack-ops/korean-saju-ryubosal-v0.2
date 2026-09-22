"""민속 흉방 레이어 엔진 — docs/19 §5 (2026-09-21 데굴님 승인).

연간(삼살방·대장군방·태세방·세파방)은 **그해 지지**(달력연도 라벨 = 만세력 세운과 같은 `year_ganzi`
규칙)로, 손방은 **음력 일**(korean_lunar_calendar)로 계산한다. 개인 사주와 무관한 공통 금기이며
개인 12신살 방향(`sinsal_direction`)과는 별개 줄로 병기한다(덮어쓰기 금지).

- 기원 분리: 삼살방 표는 이 모듈의 사전 표에서만 읽는다. 12신살 겁·재·천 구간과 값이 같아 보여도
  `twelve_sinsal.BASE_MAPS` 를 참조하지 않는다.
- 적용 범위: 이사·개업·증축·터파기 등 큰 공간 변동. 바라보기·머리·위치·출입구 배치에는 판정하지 않고
  고지 한 줄만 둔다(자료: "화장·촬영까지 삼살 때문에 금지하면 과도한 확장").
- 표현: "민속에서는 ○쪽은 ○○한 이유로 피하는 방향으로 본다"(추가 정보). 흉사 확정·공포 조장 금지.
- 서술 전용(inert): 점수·판정·날짜·간지 파이프라인 불변. 택일에는 후보 날짜의 근거 줄로만.
- 계층(2026-09-22 데굴님 승인, 검색 조정 docs/19 §5-4): MOVE(이사·이동 판정)=삼살·대장군·손방,
  GROUND(동토·좌향 참고)=태세·세파. 중첩(STRONG)은 MOVE끼리만, 고지 한 줄·택일 근거·세운 배지는
  MOVE만. 좌향 완화 문구(三煞可向不可坐·太歲可坐不可向)와 120보 원거리 고지를 병기한다 —
  '어느 해든 4방 중 3방이 흉방'으로 읽히던 결함의 수정.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from saju_manse_core.calendar.lunar_solar_converter import solar_to_lunar
from saju_manse_core.calendar.sexagenary_cycle import year_ganzi
from saju_shared_types.constants import BRANCH_CLASHES, DIRECTIONAL_COMBINATIONS, THREE_HARMONY
from saju_shared_types.enums import Branch
from saju_shared_types.folk_direction import (
    FolkDirectionNote,
    FolkTabooDict,
    FolkTabooHit,
    FolkTabooSummary,
)
from saju_shared_types.luck import LuckPillar
from saju_shared_types.manse_result import ManseV2Result

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
_COMPILED_DEFAULT = Path(__file__).resolve().parents[3] / "compiled"
FOLK_TABOO_VERSION = "1.1.0"

#: 12지지 고정 방위(sinsal_direction.BRANCH_CARDINAL 과 같은 표 — 순환 import 회피용 재선언).
_BRANCH_CARDINAL: dict[Branch, str] = {
    Branch.IN: "동", Branch.MYO: "동", Branch.JIN: "동",
    Branch.SA: "남", Branch.O: "남", Branch.MI: "남",
    Branch.SIN: "서", Branch.YU: "서", Branch.SUL: "서",
    Branch.HAE: "북", Branch.JA: "북", Branch.CHUK: "북",
}
_CARDINAL_ORDER = ("북", "동", "남", "서")
_CARDINAL_BRANCHES: dict[str, list[str]] = {
    "동": ["寅", "卯", "辰"], "남": ["巳", "午", "未"],
    "서": ["申", "酉", "戌"], "북": ["亥", "子", "丑"],
}


@lru_cache(maxsize=8)
def load_folk_taboo_dict(
    dictionaries_dir: Path = _DICTS_DEFAULT, compiled_dir: Path = _COMPILED_DEFAULT
) -> FolkTabooDict:
    """민속 흉방 사전 로드 — 컴파일 스냅샷 우선, 원본 폴백(원칙 5)."""
    snapshot = compiled_dir / f"folk_taboo_direction_v{FOLK_TABOO_VERSION}.json"
    if snapshot.exists():
        return FolkTabooDict.model_validate(json.loads(snapshot.read_text("utf-8")))
    raw = json.loads((dictionaries_dir / "folk_taboo_direction.json").read_text("utf-8"))
    return FolkTabooDict.model_validate(raw)


# ── 계산 ──────────────────────────────────────────────────────────────────────


def _trine_label(branch: Branch) -> str:
    """지지 → 삼합국 라벨(생지·왕지·고지 순 — 사전 표 키와 같은 표기)."""
    labels = {
        "寅午戌": {Branch.IN, Branch.O, Branch.SUL},
        "巳酉丑": {Branch.SA, Branch.YU, Branch.CHUK},
        "申子辰": {Branch.SIN, Branch.JA, Branch.JIN},
        "亥卯未": {Branch.HAE, Branch.MYO, Branch.MI},
    }
    for label, members in labels.items():
        if branch in members:
            assert any(members == set(m) for m, _e, _w in THREE_HARMONY)  # 상수와 정합
            return label
    raise ValueError(branch)


def _directional_label(branch: Branch) -> str:
    """지지 → 방합 라벨(사전 표 키)."""
    for members, _elem in DIRECTIONAL_COMBINATIONS:
        if branch in members:
            seq = (
                Branch.HAE, Branch.JA, Branch.CHUK, Branch.IN, Branch.MYO, Branch.JIN,
                Branch.SA, Branch.O, Branch.MI, Branch.SIN, Branch.YU, Branch.SUL,
            )
            order = [b for b in seq if b in members]
            return "".join(str(b) for b in order)
    raise ValueError(branch)


def _clash_of(branch: Branch) -> Branch:
    """지지 충(六沖) 상대."""
    for pair in BRANCH_CLASHES:
        if branch in pair:
            return next(b for b in pair if b is not branch)
    raise ValueError(branch)


def annual_folk_taboos(
    year: int, dictionary: FolkTabooDict | None = None
) -> list[FolkTabooHit]:
    """달력연도의 연간 흉방 4종(삼살·대장군=MOVE, 태세·세파=GROUND). 연지는 `year_ganzi`(입춘 기준).

    대장군방은 방합 3년 고정이라 `span_ko`('2025~2027')를 함께 채운다.
    """
    dic = dictionary or load_folk_taboo_dict()
    stem, branch = year_ganzi(year)
    basis = f"{year} {stem}{branch}년"
    hits: list[FolkTabooHit] = []
    for t in dic.taboos:
        common = {
            "key": t.key, "name_ko": t.name_ko, "reason_ko": t.reason_ko, "period": t.period,
            "basis_ko": basis, "tier": t.tier, "mitigation_ko": t.mitigation_ko,
        }
        if t.basis == "annual_trine":
            d = t.table[_trine_label(branch)]
            hits.append(FolkTabooHit(direction=d, branches=_CARDINAL_BRANCHES[d], **common))
        elif t.basis == "annual_directional":
            label = _directional_label(branch)
            d = t.table[label]
            y0 = year - label.index(str(branch))  # 방합 첫 지지 해 = 3년 구간 시작
            hits.append(FolkTabooHit(
                direction=d, branches=_CARDINAL_BRANCHES[d], span_ko=f"{y0}~{y0 + 2}", **common,
            ))
        elif t.basis == "annual_branch":
            hits.append(FolkTabooHit(
                direction=_BRANCH_CARDINAL[branch], branches=[str(branch)], **common,
            ))
        elif t.basis == "annual_clash":
            c = _clash_of(branch)
            hits.append(FolkTabooHit(direction=_BRANCH_CARDINAL[c], branches=[str(c)], **common))
    return hits


def son_direction(
    day: date, dictionary: FolkTabooDict | None = None
) -> tuple[FolkTabooHit | None, str]:
    """그날의 손방(음력 일 끝자리) — (적중 또는 None=손 없는 날, 음력 라벨)."""
    dic = dictionary or load_folk_taboo_dict()
    lunar_iso, leap = solar_to_lunar(day)
    _y, m, d = (int(x) for x in lunar_iso.split("-"))
    label = f"음력 {'윤' if leap else ''}{m}월 {d}일"
    entry = dic.taboo("son")
    direction = entry.table.get(str(d % 10))
    if direction is None:
        return None, label
    return FolkTabooHit(
        key=entry.key, name_ko=entry.name_ko, direction=direction, branches=[],
        reason_ko=entry.reason_ko, period="day", basis_ko=label, tier=entry.tier,
    ), label


def folk_taboo_summary(
    year: int, day: date | None = None, dictionary: FolkTabooDict | None = None
) -> FolkTabooSummary:
    """기준 연도(·그날)의 방향별 요약 — MOVE 층(삼살·대장군) 2종 중첩이면 STRONG_FOLK_TABOO.

    GROUND 층(태세·세파)은 `ground_hits`로 분리해 등급에 세지 않는다(참고 정보).
    """
    dic = dictionary or load_folk_taboo_dict()
    hits = annual_folk_taboos(year, dic)
    son: FolkTabooHit | None = None
    lunar: str | None = None
    son_free: bool | None = None
    if day is not None:
        son, lunar = son_direction(day, dic)
        son_free = son is None
    notes: list[FolkDirectionNote] = []
    for card in _CARDINAL_ORDER:
        move = [h for h in hits if h.direction == card and h.tier == "MOVE"]
        ground = [h for h in hits if h.direction == card and h.tier == "GROUND"]
        son_here = son is not None and son.direction == card
        if not move and not ground and not son_here:
            continue
        notes.append(FolkDirectionNote(
            direction=card, hits=move, ground_hits=ground, son_today=son_here,
            grade="STRONG_FOLK_TABOO" if len(move) >= 2 else "FOLK_TABOO",
        ))
    stem, branch = year_ganzi(year)
    return FolkTabooSummary(
        year=year, year_ganji=f"{stem}{branch}", notes=notes, son=son, son_free_day=son_free,
        lunar_label=lunar,
    )


# ── 문구 ──────────────────────────────────────────────────────────────────────


def phrase_for_note(
    note: FolkDirectionNote, dictionary: FolkTabooDict | None = None
) -> str:
    """'민속에서는 ○쪽은 ○○한 이유로 피하는 방향으로 봅니다(…)' — 사전 템플릿 치환(즉석 작문 금지).

    연간 흉방만 문구에 넣는다(손방은 그날 줄로 따로). 이유 구는 사전의 '…라' 형태를 살려
    '…자리이고 …자리라는 이유로'가 되게 잇는다.
    """
    dic = dictionary or load_folk_taboo_dict()
    hits = list(note.hits)
    if not hits:
        return ""
    stems = [h.reason_ko[:-1] if h.reason_ko.endswith("라") else h.reason_ko for h in hits]
    reasons = "이고 ".join(stems[:-1]) + ("이고 " if len(stems) > 1 else "") + stems[-1] + "라"
    names = "·".join(
        f"{h.name_ko}({'·'.join(h.branches)})" if h.branches else h.name_ko for h in hits
    )
    text = dic.phrase_template.format(direction=note.direction, reasons=reasons, names=names)
    if note.grade == "STRONG_FOLK_TABOO":
        text += f" {dic.grades['STRONG_FOLK_TABOO']}."
    for h in hits:  # 좌향 완화 문구(삼살: 向 허용·坐만 꺼림) — 강도를 낮추는 근거를 함께 싣는다
        if h.mitigation_ko:
            text += f" 다만 {h.mitigation_ko}"
    return text


def ground_phrase_for_note(
    note: FolkDirectionNote, dictionary: FolkTabooDict | None = None
) -> str:
    """참고층(태세·세파) 한 줄 — 이사 판정이 아니라 건축·터파기·집 좌향에서만 꺼린다고 명시."""
    dic = dictionary or load_folk_taboo_dict()
    if not note.ground_hits:
        return ""
    parts = []
    for h in note.ground_hits:
        entry = dic.taboo(h.key)
        seg = f"{h.name_ko}({'·'.join(h.branches)}) — {'·'.join(entry.avoid_actions)}에서만 꺼림"
        if h.mitigation_ko:
            seg += f"; {h.mitigation_ko}"
        parts.append(seg)
    return f"{note.direction}쪽 {' / '.join(parts)}"


def _actions_ko(note: FolkDirectionNote, dic: FolkTabooDict) -> str:
    """그 방향에 걸린 흉방들이 전통적으로 꺼리는 행위(중복 제거·사전 순서)."""
    seen: list[str] = []
    keys = [h.key for h in note.hits]
    for t in dic.taboos:
        if t.key in keys:
            for a in t.avoid_actions:
                if a not in seen:
                    seen.append(a)
    return "·".join(seen)


def format_folk_taboo_lines(
    summary: FolkTabooSummary,
    *,
    full: bool,
    dictionary: FolkTabooDict | None = None,
) -> list[str]:
    """[민속 흉방] 프롬프트 줄.

    full=True(이사·이동·공사 질문): MOVE 층 방향별 문구(+좌향 완화) + 참고층(태세·세파) 한 줄 +
    손방/손 없는 날 + 원거리 고지 + 범위 고지.
    full=False(그 외 방향 질문): 고지 한 줄(MOVE 층만 — 태세·세파는 싣지 않는다).
    적중이 없으면 빈 목록(무소음).
    """
    dic = dictionary or load_folk_taboo_dict()
    if not summary.notes and summary.son is None:
        return []
    if not full:
        parts = []
        for n in summary.notes:
            if not n.hits:
                continue
            names = "·".join(
                h.name_ko + (f"({h.span_ko} 고정)" if h.span_ko else "") for h in n.hits
            )
            parts.append(
                f"{n.direction}쪽={names}" + ("(중첩)" if n.grade == "STRONG_FOLK_TABOO" else "")
            )
        if not parts:
            return []
        return [
            "",
            f"[민속 흉방 고지 — {summary.year_ganji}년(추가 정보, 개인 12신살과 별개)] "
            + " · ".join(parts)
            + f" — {dic.scope_note} 이 질문의 배치(바라보기·머리·위치·출입구)에는 적용하지 않으며, "
            "답에는 '민속에서는 ○쪽은 …한 이유로 피하는 방향으로 본다'는 추가 정보 한 문장으로만 "
            "둘 것.",
        ]
    lines = [
        "",
        f"[민속 흉방 — {summary.year} {summary.year_ganji}년 연간 + 손방"
        "(추가 정보, 개인 12신살과 별개 층)]",
    ]
    for n in summary.notes:
        if not n.hits:  # 참고층·손방만 걸린 방향은 아래 줄로만
            continue
        span = " · ".join(f"{h.name_ko} {h.span_ko} 3년 고정" for h in n.hits if h.span_ko)
        lines.append(
            f"- {n.direction}쪽[{dic.grades[n.grade]}]: {phrase_for_note(n, dic)} "
            f"전통적으로 {_actions_ko(n, dic)} 등에서 특히 꺼립니다."
            + (f" ({span})" if span else "")
            + (" 오늘 손방도 이 방향입니다." if n.son_today else "")
        )
    ground = [ground_phrase_for_note(n, dic) for n in summary.notes if n.ground_hits]
    if ground:
        lines.append(
            f"- 참고({dic.tiers.get('GROUND', '동토·좌향 참고')}, 이사 판정 아님): "
            + " / ".join(ground)
        )
    if summary.lunar_label is not None:
        if summary.son is not None:
            lines.append(
                f"- 손방(그날): {summary.lunar_label} → {summary.son.direction}쪽 — "
                f"{summary.son.reason_ko} 이사·개업·혼례에서 꺼립니다."
            )
        else:
            lines.append(f"- 손방(그날): {summary.lunar_label} = 손 없는 날(손방 없음).")
    lines.append(f"- 원거리 고지: {dic.distance_note}")
    lines.append(f"범위: {dic.scope_note}")
    return lines


FOLK_TABOO_INSTRUCTION = (
    "[민속 흉방 지침] 위 [민속 흉방] 블록은 개인 사주와 무관한 그해·그날의 전통 방위 금기이며 "
    "개인 12신살 방향과 **별개 층**이다. ①'민속에서는 ○쪽은 ○○한 이유로 피하는 방향으로 본다'는 "
    "추가 정보 형식으로만 쓰고, 개인 방향판의 결론을 지우거나 합산하지 말 것(같은 방향이 "
    "개인적으로 적합해도 두 층을 나란히 적는다). ②적용은 이사·개업·증축·터파기 등 큰 공간 변동에 "
    "한함 — 공부·수면·화장·촬영 배치에 삼살방을 적용하지 말 것. ③'흉방으로 가면 사고가 난다'류 "
    "확정·공포 "
    "표현 금지, '전통적으로 꺼린다' 톤. ④삼재(개인 액년)와 삼살방(연간 공통 흉방)을 섞지 말 것. "
    "⑤중첩(강한 민속 주의)은 근거 흉방 이름을 함께 적을 것. ⑥손방은 그날 기준이며 손 없는 날이면 "
    "손방 없음이라고만. ⑦'참고(동토·좌향 참고)' 줄의 태세방·세파방은 이사·이동 판정에 쓰지 말 것 — "
    "건축·터파기·집 좌향을 묻는 경우에만 한 문장. ⑧'다만 …' 좌향 완화 문구와 원거리 고지(120보)를 "
    "그대로 옮겨 강도를 낮출 것. ⑨피하는 방향은 [민속 주의 방향] 줄의 방향만 — 4방 중 3방 이상을 "
    "'피하라'로 나열하지 말 것."
)


def folk_note_for_day(day: date, dictionary: FolkTabooDict | None = None) -> str:
    """택일 후보 1일의 민속 흉방 근거 줄 — '손방 남쪽 · 올해 삼살방 북·대장군방 동…'(추가 정보)."""
    dic = dictionary or load_folk_taboo_dict()
    summary = folk_taboo_summary(day.year, day, dic)
    annual = " · ".join(  # MOVE 층만(태세·세파는 이사 판정이 아니다)
        f"{h.name_ko} {h.direction}" for n in summary.notes for h in n.hits
    )
    son = f"손방 {summary.son.direction}쪽" if summary.son is not None else "손 없는 날"
    return f"민속 흉방(추가 정보): {son} · 올해 {annual}"


# ── 세운 카드(만세력) 부착 ─────────────────────────────────────────────────────


def enrich_folk_taboos(result: ManseV2Result) -> None:
    """세운(yearly_luck + 대운표 sewoon)에 그해 이사 판정층 흉방(삼살·대장군)을 부착한다(점수 불변).

    태세·세파(참고층)는 배지에 싣지 않는다(2026-09-22 데굴님 결정 b).
    """
    lc = result.luck_cycles
    if lc is None:
        return
    dic = load_folk_taboo_dict()
    cache: dict[int, list[FolkTabooHit]] = {}

    def _fill(p: LuckPillar) -> None:
        if p.period_type != "year" or not p.label[:4].isdigit():
            return
        y = int(p.label[:4])
        if y not in cache:
            cache[y] = [h for h in annual_folk_taboos(y, dic) if h.tier == "MOVE"]
        p.folk_taboos = list(cache[y])

    for p in lc.yearly_luck:
        _fill(p)
    for d in lc.daewoon_table:
        for p in d.sewoon:
            _fill(p)
