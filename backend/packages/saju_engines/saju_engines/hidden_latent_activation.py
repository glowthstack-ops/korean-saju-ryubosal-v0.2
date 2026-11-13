"""지장간 잠복 십성의 기간별 발현 판정 — 서술 전용 (2026-11-10 데굴님 승인, 권고 A).

배경: 원국 요약의 "[표면 부족 오행의 잠재 신호 — 지장간]" 줄은 "운에서 같은 오행·천간이 오거나 그
지지가 합·충으로 자극될 때 살아난다"는 **일반 조건문**만 주었다. 어느 해·달에 그 조건이 성립하는지는
LLM 이 스스로 간지를 따져야 했고(LLM 계산 금지 원칙 위반), 일반 조건문을 명식 사실로 합성하는
문제(식상생재 과장 사례)와 같은 구조였다. 이 모듈은 그 판정을 엔진이 하고 성립·미성립을 모두 적는다.

정의:
- **잠복 십성군** = 원국 천간(일간 제외)과 지지 본기에 없고, 지장간 중기·여기에만 있는 십성군
  (비겁·식상·재성·관성·인성 다섯 군 모두 — 데굴님 "시작할 때 모두"). 시주 미상이면 판정하지 않는다
  (미상 ≠ 없음 — 출생시간 미상 정책).
- **투출** = 운 천간이 잠복 글자와 같은 글자. 대운·세운·월운 모두 본다.
- **자극** = 운 지지가 그 글자를 품은 지지를 충·육합·삼합으로 건드림. **대운·세운만** 본다 — 월운은
  열두 지지가 해마다 다 지나가 항상 성립한다(데굴님 승인).
- 등급(운 기둥 하나 기준): 투출+자극 = 뚜렷 / 투출만 = 성립 / 자극만 = 약함(참고) / 없음 = 미성립.
  세운 기준 연간 성립률(20만 명식 모의 계산): 투출 12.4% · 자극 43.8% · 둘 다 5.8%.

순수 함수다. 점수·사건 선발·길흉 판정에 관여하지 않는다(길흉은 용신·기신). 문구는 사전
`interpretations/hidden_latent_text.json` 에서 고르기만 한다. 채팅 말미 블록과 테마 리포트 강의
블록이 같은 함수(`hidden_latent_block`)를 쓴다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from saju_manse_analysis.luck.luck_calendar import sewoon_year_of

from saju_manse_core.calendar.sexagenary_cycle import year_ganzi
from saju_shared_types.constants import BRANCH_CLASHES, SIX_COMBINATIONS, THREE_HARMONY
from saju_shared_types.enums import Branch
from saju_shared_types.manse_result import ManseV2Result

from .direction_suggestion import _DOMAIN_PRIORITY_GROUPS
from .marriage_emergence_modifier import _PARTNER_STARS

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"

#: 십성 → 십성군.
_GROUP_OF: dict[str, str] = {
    "비견": "비겁", "겁재": "비겁", "식신": "식상", "상관": "식상",
    "편재": "재성", "정재": "재성", "편관": "관성", "정관": "관성",
    "편인": "인성", "정인": "인성",
}
#: 능동 제안 층의 군 키(`direction_suggestion._GROUPS`) → 십성군 이름.
_GROUP_KEY_KO: dict[str, str] = {
    "peer": "비겁", "output": "식상", "wealth": "재성", "authority": "관성", "resource": "인성",
}
#: 십성군 → 문구 사전 id.
_GROUP_TEXT_ID: dict[str, str] = {
    "재성": "group_wealth", "인성": "group_resource", "관성": "group_officer",
    "식상": "group_output", "비겁": "group_peer",
}
#: 블록을 싣지 않는 도메인(표에 있어도 제외).
_EXCLUDED_DOMAINS: frozenset[str] = frozenset({"health"})
#: 도메인이 없거나 총운형(general)일 때의 군 순서.
_DEFAULT_ORDER: tuple[str, ...] = ("재성", "관성", "인성", "식상", "비겁")
_POS_KO: dict[str, str] = {"year": "연지", "month": "월지", "day": "일지", "hour": "시지"}
_STAGE_KO: dict[str, str] = {"middle": "중기", "residual": "여기"}
_LAYER_KO: dict[str, str] = {"daewoon": "대운", "sewoon": "세운", "wolwoon": "월운"}
_GRADE_KO: dict[str, str] = {"clear": "뚜렷", "emerge": "성립", "stir": "약함(참고)"}
#: 한 블록에 싣는 잠복 글자 상한·글자당 성립 기간 상한(토큰 보호).
MAX_LATENTS = 4
MAX_HITS_PER_LATENT = 6

BLOCK_HEADER = (
    "[지장간 잠복 십성 발현 — 엔진 판정(서술 전용, 점수·길흉 판정 아님)] 원국 천간·지지 본기에는 "
    "없고 지장간 중기·여기에만 있는 십성이 후보 기간의 운에서 드러나는지 엔진이 판정한 결과다. "
    "투출 = 운 천간(대운·세운·월운)이 그 글자와 같은 글자 / 자극 = 운 지지(대운·세운)가 그 글자를 "
    "품은 지지를 충·육합·삼합으로 건드림."
)
USAGE_RULE = (
    "사용 규칙: ①'성립'·'뚜렷'으로 적힌 기간만 '지장간에 숨어 있던 ○○이 드러나 쓸 수 있는 시기'로 "
    "가능성형으로 서술한다. ②'약함(참고)'은 단독 근거로 쓰지 말고 다른 근거가 있을 때 한 구절로만 "
    "덧붙인다. ③'미성립' 기간과 이 블록에 없는 기간을 발현 시기로 지목하지 말 것 — 간지를 직접 "
    "따져 기간을 보태지 않는다. ④질문과 무관한 십성군 줄은 쓰지 않는다."
)
#: 원국 요약의 잠재 신호 줄에 붙는 꼬리 — 일반 조건문을 특정 시기로 합성하지 않게 한다.
NATAL_LATENT_PERIOD_RULE = (
    " 어느 기간에 그 조건이 성립하는지는 [지장간 잠복 십성 발현 — 엔진 판정] 블록에 적힌 기간만 "
    "쓴다 — 블록이 없거나 그 기간이 블록에 없으면 특정 해·달을 발현 시기로 지목하지 말 것."
)


@dataclass(frozen=True)
class HiddenLatent:
    """원국에서 지장간 중기·여기에만 있는 글자 하나(여러 지지에 있으면 hosts 로 묶는다)."""

    group: str  # 십성군
    stem: str  # 잠복 글자(한자)
    ten_god: str
    hosts: tuple[tuple[str, str, str], ...]  # (자리, 지지, 단계 middle|residual)


@dataclass(frozen=True)
class LuckUnit:
    """판정 단위가 되는 운 기둥 하나."""

    layer: str  # daewoon | sewoon | wolwoon
    label: str  # '2021~2030' | '2027' | '2026-11'
    ganji: str


@dataclass(frozen=True)
class LatentHit:
    """잠복 글자 하나 × 운 기둥 하나의 성립 판정."""

    unit: LuckUnit
    emerge: bool
    stir: str | None  # '세운 지지 未–원국 丑 충' 같은 사실 문구(없으면 None)
    grade: str  # clear | emerge | stir


def natal_hidden_latents(result: ManseV2Result) -> list[HiddenLatent]:
    """원국의 잠복 글자 목록 — 십성군이 천간(일간 제외)·지지 본기에 없고 중기·여기에만 있는 것.

    Args:
        result: 만세 결과(pillars 필요).

    Returns:
        (십성군, 글자) 단위 목록(원국 자리 순). 기둥이 없거나 시주 미상이면 빈 목록.
    """
    p = result.pillars
    if p is None or p.hour is None:
        return []
    pillars = (("year", p.year), ("month", p.month), ("day", p.day), ("hour", p.hour))
    visible: set[str] = set()
    for pos, pil in pillars:
        if pos != "day" and pil.stem_ten_god in _GROUP_OF:
            visible.add(_GROUP_OF[pil.stem_ten_god])
        if pil.branch_main_ten_god in _GROUP_OF:
            visible.add(_GROUP_OF[pil.branch_main_ten_god])
    merged: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    gods: dict[tuple[str, str], str] = {}
    for pos, pil in pillars:
        for h in pil.hidden_stems:
            group = _GROUP_OF.get(h.ten_god)
            if h.type == "main" or group is None or group in visible:
                continue
            key = (group, h.stem)
            merged.setdefault(key, []).append((pos, pil.branch, h.type))
            gods[key] = h.ten_god
    return [
        HiddenLatent(group=g, stem=s, ten_god=gods[(g, s)], hosts=tuple(hosts))
        for (g, s), hosts in merged.items()
    ]


def _touch(luck_branch: str, host: str) -> str | None:
    """운 지지가 원국 지지를 건드리는 방식 — '충' | '육합' | '삼합' | None(같은 글자는 제외)."""
    if luck_branch == host:
        return None
    try:
        pair = frozenset({Branch(luck_branch), Branch(host)})
    except ValueError:
        return None
    if pair in BRANCH_CLASHES:
        return "충"
    if pair in SIX_COMBINATIONS:
        return "육합"
    if any(pair <= members for members, _el, _peak in THREE_HARMONY):
        return "삼합"
    return None


def _period_date(label: str) -> date | None:
    """기간 라벨의 대표 날짜(대운 대응용) — 연 = 7/1, 월 = 15일, 일 = 그 날."""
    try:
        if len(label) == 4:
            return date(int(label), 7, 1)
        if len(label) == 7:
            return date(int(label[:4]), int(label[5:7]), 15)
        return date.fromisoformat(label[:10])
    except ValueError:
        return None


def luck_units(result: ManseV2Result, periods: list[tuple[str, str]]) -> list[LuckUnit]:
    """후보 기간 → 판정할 운 기둥 목록(대운 → 세운 → 월운, 각각 등장 순·중복 제거).

    Args:
        result: 본인 명식(대운 표).
        periods: (기간 라벨, 운 간지). 'YYYY-MM' 라벨의 간지는 월운, 'YYYY' 라벨의 간지는 세운이다.
            세운 간지는 라벨에서 달력 계산으로 보탠다(월 후보만 있는 질문에도 그 해 세운을 본다).
    """
    daewoon: dict[str, LuckUnit] = {}
    sewoon: dict[str, LuckUnit] = {}
    wolwoon: dict[str, LuckUnit] = {}
    table = result.luck_cycles.daewoon_table if result.luck_cycles is not None else []
    for label, ganji in periods:
        d = _period_date(label)
        if d is not None:
            for dw in table:
                if dw.approx_start_date <= d <= dw.approx_end_date:
                    span = f"{dw.approx_start_date.year}~{dw.approx_end_date.year}"
                    daewoon.setdefault(span, LuckUnit("daewoon", span, dw.ganji))
                    break
        year = sewoon_year_of(label)
        if year is not None:
            stem, branch = year_ganzi(year)
            ganji_y = f"{stem.value}{branch.value}"
            sewoon.setdefault(str(year), LuckUnit("sewoon", str(year), ganji_y))
        if len(label) == 7 and len(ganji) >= 2:
            wolwoon.setdefault(label, LuckUnit("wolwoon", label, ganji[:2]))
    return [*daewoon.values(), *sewoon.values(), *wolwoon.values()]


def judge(latent: HiddenLatent, unit: LuckUnit) -> LatentHit | None:
    """잠복 글자 × 운 기둥 판정 — 투출·자극 어느 것도 없으면 None(미성립)."""
    if len(unit.ganji) < 2:
        return None
    luck_stem, luck_branch = unit.ganji[0], unit.ganji[1]
    emerge = luck_stem == latent.stem
    stir: str | None = None
    if unit.layer in ("daewoon", "sewoon"):
        for _pos, host, _stage in latent.hosts:
            how = _touch(luck_branch, host)
            if how is not None:
                stir = f"{_LAYER_KO[unit.layer]} 지지 {luck_branch}–원국 {host} {how}"
                break
    if not emerge and stir is None:
        return None
    grade = "clear" if emerge and stir else "emerge" if emerge else "stir"
    return LatentHit(unit=unit, emerge=emerge, stir=stir, grade=grade)


@lru_cache(maxsize=4)
def _texts(dictionaries_dir: Path = _DICTS_DEFAULT) -> dict[str, str]:
    path = dictionaries_dir / "interpretations" / "hidden_latent_text.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {it["id"]: it["text"] for it in data["items"]}


def _partner_group(result: ManseV2Result) -> str | None:
    """배우자성 십성군(남 재성·여 관성) — 성별 미상이면 None."""
    gender = str(result.input_summary.get("gender", "unknown"))
    stars = _PARTNER_STARS.get(gender)
    return _GROUP_OF[next(iter(stars))] if stars else None


def domain_groups(result: ManseV2Result, domain: str | None) -> tuple[str, ...] | None:
    """질문·섹션 도메인에서 싣는 십성군(순서 포함). None 이면 이 도메인에는 블록을 싣지 않는다.

    - 도메인 없음·general(총운형): 다섯 군 전부(`_DEFAULT_ORDER`).
    - career·wealth·education: 능동 제안 층과 같은 도메인→십성군 표
      (`direction_suggestion._DOMAIN_PRIORITY_GROUPS` — 새 대응을 만들지 않는다).
    - relationship: 배우자성(남 재성·여 관성) + 같은 표의 군.
    - 그 밖(relocation·health): 싣지 않는다 — 건강 질문은 십성 발현 문구(문서·직책·재물 …)가
      주제와 맞지 않는다.
    """
    if domain is None or domain == "general":
        return _DEFAULT_ORDER
    keys = _DOMAIN_PRIORITY_GROUPS.get(domain)
    if keys is None or domain in _EXCLUDED_DOMAINS:
        return None
    groups = [_GROUP_KEY_KO[k] for k in keys]
    if domain == "relationship":
        partner = _partner_group(result)
        if partner is not None and partner not in groups:
            groups.insert(0, partner)
    return tuple(groups)


def _host_label(latent: HiddenLatent) -> str:
    return "·".join(
        f"{branch}({_POS_KO[pos]}) {_STAGE_KO.get(stage, stage)}"
        for pos, branch, stage in latent.hosts
    )


def _hit_text(hit: LatentHit) -> str:
    u = hit.unit
    unit_ko = f"{u.label} {u.ganji}{'대운' if u.layer == 'daewoon' else ''}"
    facts: list[str] = []
    if hit.emerge:
        facts.append(f"{_LAYER_KO[u.layer]} 천간 {u.ganji[0]} 투출")
    if hit.stir:
        facts.append(hit.stir)
    tail = "(10년 배경)" if u.layer == "daewoon" else ""
    return f"{unit_ko} = {' + '.join(facts)}{tail} → {_GRADE_KO[hit.grade]}"


def hidden_latent_block(
    result: ManseV2Result, periods: list[tuple[str, str]], domain: str | None = None,
) -> list[str]:
    """잠복 십성 발현 블록(채팅 말미·리포트 강의 블록 공용) — 조건이 없으면 빈 목록.

    Args:
        result: 본인 명식.
        periods: (기간 라벨, 운 간지) 후보 기간 목록.
        domain: 질문·섹션 도메인(`Domain.value`) — 싣는 십성군과 순서를 정한다(`domain_groups`).

    Returns:
        머리말 + 잠복 글자별 한 줄(성립 기간 전부 + '그 밖의 후보 기간 = 미성립') + 읽는 법 +
        사용 규칙. 한 글자라도 걸리면 걸리지 않은 글자도 '후보 기간 전부 미성립'으로 함께 적는다.
        잠복 글자가 없거나, 도메인에 해당하는 군이 없거나, 후보 기간이 없거나, **어느 글자도
        걸리지 않으면** 빈 목록.
    """
    groups = domain_groups(result, domain)
    if groups is None or not periods:
        return []
    latents = [lt for lt in natal_hidden_latents(result) if lt.group in groups]
    if not latents:
        return []
    latents.sort(key=lambda lt: groups.index(lt.group))  # 안정 정렬 — 군 안에서는 원국 자리 순
    units = luck_units(result, periods)
    if not units:
        return []
    t = _texts()
    partner = _partner_group(result) if domain == "relationship" else None
    lines: list[str] = []
    grades: set[str] = set()
    meant: set[str] = set()  # 뜻 문장은 십성군마다 첫 줄에만(같은 군 글자가 둘이면 한 번)
    for lt in latents[:MAX_LATENTS]:
        hits = [h for h in (judge(lt, u) for u in units) if h is not None]
        grades |= {h.grade for h in hits}
        shown = [_hit_text(h) for h in hits[:MAX_HITS_PER_LATENT]]
        verdict = (
            " / ".join([*shown, "그 밖의 후보 기간 = 미성립"]) if shown
            else "후보 기간 전부 미성립"
        )
        meaning = ""
        if lt.group not in meant:
            meant.add(lt.group)
            meaning = " " + (
                t["group_partner"] if lt.group == partner else t[_GROUP_TEXT_ID[lt.group]]
            )
        lines.append(
            f"- {lt.group} — {_host_label(lt)} {lt.stem}({lt.ten_god}): {verdict}.{meaning}"
        )
    if not grades:
        # 어느 잠복 글자도 후보 기간에 걸리지 않으면 블록을 싣지 않는다 — 원국 잠재 신호 줄의 꼬리
        # (`NATAL_LATENT_PERIOD_RULE`: 블록이 없으면 시기를 지목하지 말 것)가 같은 뜻을 이미 싣고,
        # '전부 미성립' 줄만 있는 블록은 이번 달·오늘 총운 답에 군말만 보탠다(2026-11-10 dry-run).
        return []
    legend = [t[f"grade_{g}"] for g in ("clear", "emerge", "stir") if g in grades]
    return [
        BLOCK_HEADER, *lines, "읽는 법: " + " / ".join(legend), f"{USAGE_RULE} {t['caution']}",
    ]
