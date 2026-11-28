"""생활 장면 어휘 층 — 원국 판정에 맞는 장면·대하는 법·놀림 소재를 사전에서 골라 낸다.

SSOT: doc/v2_2/EXTERNAL_TEXT_GAP_CHOI_LIVE.md (§7 장면 칸 규격 · §8 단계).

- 판정은 전부 기존 엔진 값(일간·강약 등급·십성군 가시 글자 수·신살 집계·공망 자리·원국 충)을 읽기만
  한다. 이 모듈은 사전 문장을 **고르기만** 하며 점수·판정·간지·날짜에 관여하지 않는다.
- 시주 미상 가드: 강약 등급이 미확정이면 강약 장면을 내지 않고, 십성군·오행의 '표면에 없음'
  장면은 시주가 있어야만 낸다(미상≠없음 — doc/v2_2/HOUR_UNKNOWN_POLICY.md).
- 출력은 `InterpretationExcerpt(kind="scene")` 목록 — 명식 해석 자료(고정 prefix)의 맨 뒤에 붙어
  토큰 가드가 발췌를 줄일 때 가장 먼저 빠진다. 화면용은 `sinsal_glossary`.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

from saju_shared_types.llm_input import InterpretationExcerpt
from saju_shared_types.manse_result import ManseV2Result

from . import period_v2_config

_INTERP_DIR = Path(__file__).resolve().parents[3] / "dictionaries" / "interpretations"

#: 장면 발췌 kind — 프롬프트 직렬화가 이 값으로 사용 규칙 줄을 붙인다.
SCENE_KIND = "scene"

#: 프롬프트에 싣는 장면 발췌 상한(전체) — 질문과 무관한 성향 재료가 근거 블록을 밀어내지 않게.
MAX_SCENE_EXCERPTS = 11
#: 십성군 '많음'·'표면에 없음' 장면 각각의 상한.
MAX_GROUP_EXCESS = 2
MAX_GROUP_ABSENT = 2
#: 신살 장면 상한과 우선 순서(귀인 → 성향 표지). 판정되고 화면에 보이는 이름만 쓴다.
MAX_SINSAL_SCENES = 3
SINSAL_SCENE_PRIORITY: tuple[str, ...] = (
    "암록", "문창귀인", "월덕귀인", "황은대사", "태극귀인", "현침", "도화", "이동지", "사고지",
)
#: 개별 십성 장면(정관·편관·상관)을 붙이는 조건 — 월지·일지 본기에 있거나 가시 글자 2개 이상.
INDIVIDUAL_TEN_GOD_MIN_COUNT = 2
#: 오행 놀림을 붙이는 '지나치게 많음' 기준(가시 글자 8자 중).
ELEMENT_EXCESS_COUNT = 4

_PALACE_KO = {"year": "연주", "month": "월주", "day": "일주", "hour": "시주"}
_GROUP_ORDER = ("비겁", "식상", "재성", "관성", "인성")
_SIDE_KO = {"weak": "신약 쪽", "balanced": "중화", "strong": "신강 쪽"}
_BRANCH_CHARS = frozenset("子丑寅卯辰巳午未申酉戌亥")

#: 장면 발췌 사용 규칙 — 명식 해석 자료에서 장면 줄 바로 앞에 한 번 싣는다(채팅·리포트 공용).
SCENE_VOCAB_USE_RULE = (
    "[생활 장면 재료 — 쓰는 법] 아래 '장면' 줄은 이 명식의 판정에 맞춰 사전에서 고른 "
    "생활 장면이다. "
    "①성격·성향·관계·적성·배우는 방식·다툼과 이별 방식처럼 사람됨을 묻는 질문에서만 한두 개 골라 "
    "쓰고, 시기·사건·택일 질문에는 쓰지 않는다. ②장면은 '그런 편이다' 수준의 경향이며 길흉·사건 "
    "판정의 근거가 아니다 — 문장을 그대로 옮기지 말고 질문 상황에 맞춰 풀어 쓴다. ③'놀림 소재'는 "
    "가볍게 웃고 넘길 한마디로 답 전체에서 한 번 이하만 쓰고, 건강·사고·상실·이별 통보처럼 무거운 "
    "주제의 답에는 쓰지 않는다. 놀림은 판정도 조언도 아니며 말투는 위 문체 지침을 그대로 따른다. "
    "④'표면에 없음' 장면은 드러난 글자 기준이다 — 그 기운이 아예 없다고 단정하지 않는다. "
    "⑤충·형·공망·합이 함께 있어도 귀인·신살·십성을 '못 쓴다'·'사라진다'로 뒤집지 않는다 — 켜지고 "
    "꺼지는 것이 아니라 세졌다 약해졌다 하는 것이고, 충이 걸린 자리는 두 기질이 번갈아 나오는 "
    "것으로 쓴다. ⑥백호·괴강·양인·현침 같은 흉성은 겁주는 말 대신 '기질이 만만치 않다'는 성향으로 "
    "풀어 쓴다. ⑦치우침·부족을 말할 때는 지금까지 본인이 다뤄 온 방식이 있음을 먼저 인정하고, "
    "탓하는 어조로 쓰지 않는다. ⑧'나란히 보기' 줄은 같은 상황에서의 서로 다른 반응이다 — 다른 쪽 "
    "반응은 주변 사람을 이해하는 재료로만 쓰고, 상대의 명식을 추정하지 않는다."
)

#: 생성 후 감사(로그 전용) — 귀인·신살·십성을 충·형·공망·합 때문에 '못 쓴다'고 뒤집은 문장.
_ON_OFF_SUBJECT_RE = re.compile(r"귀인|신살|도화|역마|문창|암록|태극|월덕|황은|천을|십성|용신")
_ON_OFF_CAUSE_RE = re.compile(r"충|형살|삼형|공망|합거|합이 되")
_ON_OFF_NEGATION_RE = re.compile(
    r"못\s*쓰|쓸\s*수\s*없|쓰지\s*못|무효|소용이?\s*없|사라[지집진]|없어[지집진]|힘을\s*잃"
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。])\s+|\n+")


def find_on_off_claims(answer: str) -> list[str]:
    """답변에서 '충·형·공망·합 때문에 귀인·신살·십성을 못 쓴다'는 식의 문장을 찾는다(로그 전용).

    Args:
        answer: 생성된 답변 본문.

    Returns:
        해당 문장 목록(없으면 빈 목록). 답을 고치지 않는다 — 노출 뒤 실답 감수 재료.
    """
    hits: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(answer or ""):
        if (
            _ON_OFF_SUBJECT_RE.search(sentence)
            and _ON_OFF_CAUSE_RE.search(sentence)
            and _ON_OFF_NEGATION_RE.search(sentence)
        ):
            hits.append(sentence.strip())
    return hits


@cache
def _load(name: str) -> dict:
    """해석 사전 1건(캐시). 스키마·lint 는 dictionaries.py 가 맡는다."""
    return json.loads((_INTERP_DIR / name).read_text("utf-8"))


def _join(parts: list[tuple[str, str | None]]) -> str:
    """(머리말, 문장) 목록을 ' · ' 로 잇는다 — 빈 문장은 건너뛴다."""
    return " · ".join(f"{head}: {text}" for head, text in parts if text)


def _scene_text(item: dict, *, scenes_key: str = "scenes") -> str:
    """장면 칸 공통 직렬화 — 장면 / 원리 / 대하는 법 / 놀림 소재."""
    scenes = item.get(scenes_key) or []
    return _join([
        ("장면", " / ".join(scenes) if scenes else None),
        ("원리", item.get("mechanism")),
        ("대하는 법", item.get("howToTreat")),
        ("놀림 소재", item.get("tease")),
    ])


def _excerpt(key: str, text: str) -> InterpretationExcerpt | None:
    return InterpretationExcerpt(kind=SCENE_KIND, key=key, text=text) if text else None


def _visible_ten_gods(result: ManseV2Result) -> list[tuple[str, str]]:
    """(자리, 십성) 목록 — 천간 + 지지 본기, 일간 제외(십성군 가시 글자 셈과 같은 범위)."""
    out: list[tuple[str, str]] = []
    if result.pillars is None:
        return out
    for palace in ("year", "month", "day", "hour"):
        pil = getattr(result.pillars, palace, None)
        if pil is None:
            continue
        if pil.stem_ten_god and pil.stem_ten_god != "일간":
            out.append((f"{palace}_stem", pil.stem_ten_god))
        if pil.branch_main_ten_god:
            out.append((f"{palace}_branch", pil.branch_main_ten_god))
    return out


def _day_master_excerpt(result: ManseV2Result) -> InterpretationExcerpt | None:
    """일간 장면 — 천간 사전의 행동 장면."""
    stem = result.pillars.day.stem if result.pillars is not None else ""
    item = next((s for s in _load("stems_branches_text.json")["stems"] if s["char"] == stem), None)
    return _excerpt(f"일간 {stem} 장면", _scene_text(item)) if item else None


def _strength_excerpt(result: ManseV2Result) -> InterpretationExcerpt | None:
    """신강·신약 쪽 장면 — 시주 미상으로 등급이 미확정이면 내지 않는다."""
    hu = result.hour_unknown
    if hu is not None and "strength_band" in hu.unconfirmed:
        return None
    force = result.force_analysis
    band = force.strength.band if force is not None else ""
    data = _load("strength_traits.json")
    item = next((it for it in data["items"] if band in it["bands"]), None)
    if item is None:
        return None
    text = " · ".join(t for t in (
        _scene_text(item),
        f"나란히 보기: {item['contrast']}" if item.get("contrast") else "",
        f"기울기: {data['yinYangLean']}" if data.get("yinYangLean") and item["side"] != "balanced"
        else "",
    ) if t)
    return _excerpt(f"{_SIDE_KO[item['side']]}({band}) 장면", text)


def _group_excerpts(result: ManseV2Result) -> list[InterpretationExcerpt]:
    """십성군 '많음'(가시 글자 3개 이상)·'표면에 없음'(0개, 시주가 있을 때만) 장면."""
    from .love_type import LOVE_TYPE_COUNT_THRESHOLD, group_visible_counts  # 지역 import

    counts = group_visible_counts(result)
    traits = {it["group"]: it for it in _load("ten_god_group_traits.json")["items"]}
    out: list[InterpretationExcerpt] = []
    excess = sorted(
        (g for g in _GROUP_ORDER if counts[g] >= LOVE_TYPE_COUNT_THRESHOLD),
        key=lambda g: (-counts[g], _GROUP_ORDER.index(g)),
    )[:MAX_GROUP_EXCESS]
    for g in excess:
        item = traits[g]
        text = _join([
            ("장면", " / ".join(item.get("scenes") or []) or None),
            ("배우는 방식", item.get("study")),
            ("다툼·이별", item.get("parting")),
            ("대하는 법", item.get("howToTreat")),
            ("놀림 소재", item.get("tease")),
        ])
        ex = _excerpt(f"{g} 많음({counts[g]}글자) 장면", text)
        if ex:
            out.append(ex)
    # '표면에 없음'은 시주가 있어야 말할 수 있다(미상≠없음).
    if result.pillars is not None and result.pillars.hour is not None:
        absent = [g for g in _GROUP_ORDER if counts[g] == 0][:MAX_GROUP_ABSENT]
        for g in absent:
            item = traits[g]
            text = _join([
                ("장면", " / ".join(item.get("scenesAbsent") or []) or None),
                ("권하는 행동", item.get("adviceAbsent")),
                ("놀림 소재", item.get("teaseAbsent")),
            ])
            ex = _excerpt(f"{g} 표면에 없음(천간·지지 본기 기준) 장면", text)
            if ex:
                out.append(ex)
    return out


def _individual_ten_god_excerpts(result: ManseV2Result) -> list[InterpretationExcerpt]:
    """정관·편관·상관 장면 — 월지·일지 본기에 있거나 가시 글자 2개 이상일 때만."""
    visible = _visible_ten_gods(result)
    items = {it["tenGod"]: it for it in _load("ten_gods_text.json")["items"] if it.get("scenes")}
    out: list[InterpretationExcerpt] = []
    for name, item in items.items():
        count = sum(1 for _pos, tg in visible if tg == name)
        seated = any(pos in ("month_branch", "day_branch") and tg == name for pos, tg in visible)
        if seated or count >= INDIVIDUAL_TEN_GOD_MIN_COUNT:
            ex = _excerpt(f"{name} 장면", _scene_text(item))
            if ex:
                out.append(ex)
    return out


def _contrast_excerpt(result: ManseV2Result) -> InterpretationExcerpt | None:
    """같은 상황, 다른 반응 — 이 명식이 해당하는 반응이 가장 많은 상황 1건(없으면 None)."""
    from .love_type import LOVE_TYPE_COUNT_THRESHOLD, group_visible_counts  # 지역 import

    counts = group_visible_counts(result)
    visible = _visible_ten_gods(result)
    hour_known = result.pillars is not None and result.pillars.hour is not None

    def holds(when: str) -> bool:
        kind, name, *rest = when.split(":")
        if kind == "group":
            if rest[0] == "excess":
                return counts.get(name, 0) >= LOVE_TYPE_COUNT_THRESHOLD
            return hour_known and counts.get(name, 0) == 0
        count = sum(1 for _pos, tg in visible if tg == name)
        seated = any(pos in ("month_branch", "day_branch") and tg == name for pos, tg in visible)
        return seated or count >= INDIVIDUAL_TEN_GOD_MIN_COUNT

    best: tuple[int, dict, set[str]] | None = None
    for item in _load("contrast_scenes.json")["items"]:
        mine = {r["when"] for r in item["reactions"] if holds(r["when"])}
        if mine and (best is None or len(mine) > best[0]):
            best = (len(mine), item, mine)
    if best is None:
        return None
    _n, item, mine = best
    parts = [
        f"{'이 명식(' + r['label'] + ')' if r['when'] in mine else r['label']} → {r['text']}"
        for r in item["reactions"]
    ]
    return _excerpt(f"나란히 보기 — {item['situation']}", " / ".join(parts))


def _sinsal_names(result: ManseV2Result) -> list[str]:
    """판정되고 화면에 보이는(숨김 아닌) 원국 신살 이름 — 중복 없이."""
    extras = result.traditional_extras
    if extras is None or extras.sinsal is None:
        return []
    names: list[str] = []
    for palace in ("year", "month", "day", "hour"):
        for name in extras.sinsal.by_pillar.get(palace, []):
            if name not in names:
                names.append(name)
    return names


def _sinsal_excerpts(result: ManseV2Result) -> list[InterpretationExcerpt]:
    """신살 장면 — 우선 순서대로 상한까지. 역마가 성립하면 같은 글자의 이동지 표지는 뺀다."""
    judged = _sinsal_names(result)
    texts = {it["name"]: it for it in _load("sinsal_text.json")["items"] if it.get("scenes")}
    out: list[InterpretationExcerpt] = []
    for name in SINSAL_SCENE_PRIORITY:
        if name not in judged or name not in texts:
            continue
        if name == "이동지" and "역마살" in judged:
            continue
        ex = _excerpt(f"{name} 장면(보조)", _scene_text(texts[name]))
        if ex:
            out.append(ex)
        if len(out) >= MAX_SINSAL_SCENES:
            break
    return out


def _void_excerpts(result: ManseV2Result) -> list[InterpretationExcerpt]:
    """공망 자리(연·월·시)의 성향 장면 — 총론은 첫 줄에 한 번만 싣는다."""
    if result.pillars is None:
        return []
    data = _load("void_ten_god_text.json")
    palaces = {p["palace"]: p for p in data.get("palaces") or []}
    general = data.get("general") or {}
    out: list[InterpretationExcerpt] = []
    for palace in ("year", "month", "hour"):
        pil = getattr(result.pillars, palace, None)
        if pil is None or not pil.gongmang_hit or palace not in palaces:
            continue
        head = ""
        if not out and general:
            head = _join([
                ("공망 읽는 법", general.get("text")), ("권하는 행동", general.get("advice")),
            ]) + " · "
        ex = _excerpt(f"공망 {_PALACE_KO[palace]} 장면", head + _scene_text(palaces[palace]))
        if ex:
            out.append(ex)
    return out


def _clash_excerpts(result: ManseV2Result) -> list[InterpretationExcerpt]:
    """원국에 성립한 충 쌍의 장면 — 두 기질이 번갈아 나오는 모습."""
    sa = result.structure_analysis
    if sa is None:
        return []
    by_members = {
        frozenset(ch for ch in it["id"] if ch in _BRANCH_CHARS): it
        for it in _load("relations_text.json")["items"]
        if it.get("scenes") and it.get("type") == "branch_clash"
    }
    out: list[InterpretationExcerpt] = []
    seen: set[str] = set()
    for inter in sa.interactions:
        if inter.relation_type != "clash":
            continue
        item = by_members.get(frozenset(inter.members))
        if item is None or item["name"] in seen:
            continue
        seen.add(item["name"])
        ex = _excerpt(f"{item['name']} 장면", _scene_text(item))
        if ex:
            out.append(ex)
    return out


def _element_tease_excerpts(result: ManseV2Result) -> list[InterpretationExcerpt]:
    """오행 놀림 — 그 오행의 가시 글자가 지나치게 많거나(4개 이상), 시주가 있고 0개일 때."""
    teases = _load("stems_branches_text.json").get("elementTeases") or {}
    if not teases or result.pillars is None:
        return []
    counts: dict[str, int] = {}
    for palace in ("year", "month", "day", "hour"):
        pil = getattr(result.pillars, palace, None)
        if pil is None:
            continue
        for element in (pil.stem_element, pil.branch_element):
            counts[element] = counts.get(element, 0) + 1
    hour_known = result.pillars.hour is not None
    out: list[InterpretationExcerpt] = []
    for element, tease in teases.items():
        n = counts.get(element, 0)
        if n >= ELEMENT_EXCESS_COUNT or (hour_known and n == 0):
            state = f"많음({n}글자)" if n else "표면에 없음"
            ex = _excerpt(f"{element} {state} 놀림 소재", tease)
            if ex:
                out.append(ex)
    return out


def scene_excerpts(result: ManseV2Result) -> list[InterpretationExcerpt]:
    """이 명식에 맞는 생활 장면 발췌 — 일간 → 강약 → 십성군 → 개별 십성 → 신살 → 공망 → 충 → 오행.

    Args:
        result: 만세력 계산 결과(원국·강약·신살·구조 분석 포함).

    Returns:
        `kind="scene"` 발췌 목록(상한 `MAX_SCENE_EXCERPTS`). 플래그가 꺼져 있거나 원국이 없으면
        빈 목록.
    """
    if not period_v2_config.SCENE_VOCAB_ENABLED or result.pillars is None:
        return []
    out: list[InterpretationExcerpt] = []
    for single in (_day_master_excerpt(result), _strength_excerpt(result)):
        if single is not None:
            out.append(single)
    out += _group_excerpts(result)
    out += _individual_ten_god_excerpts(result)
    contrast = _contrast_excerpt(result)
    if contrast is not None:
        out.append(contrast)
    out += _sinsal_excerpts(result)
    out += _void_excerpts(result)
    out += _clash_excerpts(result)
    out += _element_tease_excerpts(result)
    return out[:MAX_SCENE_EXCERPTS]


def sinsal_glossary(names: list[str]) -> dict[str, dict]:
    """화면용 신살 풀이 — 이름 → 뜻·발현·양면·장면·원리·대하는 법·놀림 소재.

    Args:
        names: 화면에 보이는 신살 이름 목록(원국·운 구분 없이).

    Returns:
        사전에 문구가 있는 이름만 담은 사전. 장면 칸은 저작된 항목에만 있다.
    """
    texts = {it["name"]: it for it in _load("sinsal_text.json")["items"]}
    out: dict[str, dict] = {}
    for name in names:
        item = texts.get(name)
        if item is None or name in out:
            continue
        entry = {
            "meaning": item["meaning"],
            "manifestation": item["manifestation"],
            "flip_side": item["flipSide"],
        }
        for src, dst in (
            ("scenes", "scenes"), ("mechanism", "mechanism"),
            ("howToTreat", "how_to_treat"), ("tease", "tease"),
        ):
            if item.get(src):
                entry[dst] = item[src]
        out[name] = entry
    return out


def sinsal_glossary_all(exclude: frozenset[str] = frozenset()) -> dict[str, dict]:
    """사전에 문구가 있는 신살 전부의 화면용 풀이 — `exclude`(숨김 이름)는 뺀다."""
    names = [it["name"] for it in _load("sinsal_text.json")["items"] if it["name"] not in exclude]
    return sinsal_glossary(names)


__all__ = [
    "MAX_SCENE_EXCERPTS",
    "SCENE_KIND",
    "SCENE_VOCAB_USE_RULE",
    "find_on_off_claims",
    "scene_excerpts",
    "sinsal_glossary",
    "sinsal_glossary_all",
]
