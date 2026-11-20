"""축 글자 도래 층 — 질문 주제의 중심 십성군이 원국에 어떻게 놓였고 운의 어디로 오는지(2026-11-20).

배경(데굴님 제공 영상 스크립트 대조, doc/v2_2/EXTERNAL_TEXT_GAP_POSITION_SEAL_VIDEO.md):
'원국 구조 × 운에서 온 글자' 블록(`luck_structure_tags`)은 "드러난 글자가 없는 관성이 들어옴"까지는
말하지만, 그 일이 시험·취업·승진·공모 질문에서 무슨 뜻인지는 말하지 않았다. 이 층은 주제마다 중심이
되는 십성군(축)을 정해 두고(렌즈), 같은 엔진 값을 주제의 말로 옮긴다.

- 렌즈 5종: `position_seal`(시험·자격·취업·승진·공모 — 관성·인성), `business`(창업·사업 —
  재성·식상), `wealth`(재물 — 재성의 천간/지지 양상만. 원국×운 보완은 재물 강의층이 이미 맡는다),
  `children_female`·`children_male`(출산·자녀 — 여성 식상 / 남성 관성, 2026-11-20 데굴님 "출산은
  가능성 여부를 궁금해하는 부분이라 민감영역은 아니야").
- 판정은 전부 기존 엔진 값이다 — 새 임계·새 규칙을 만들지 않는다.
  · 드러난 글자 없음·과다: `luck_structure_tags.natal_structure_profile`(가시 글자 0 / 실세력 30%+)
  · 이어지는 구조: `structure_patterns` 원국 성립 패턴 id
  · 운 층·글자: `hidden_latent_activation.luck_units`(대운 → 세운 → 월운), 지지는 본기 십성
  · 대운 교체 전후: `daewoon_turn` 과 같은 교운일·교운 가중(앞뒤 1년 = `CORE_WEIGHT`)
- 문구는 `interpretations/axis_arrival_lens.json` 에서 고르기만 한다.
- 서술 전용이다 — 점수·순위·시기·길흉·당락 판정에 개입하지 않는다. 글자가 드는 것은 사건의
  종류·형태이고 유불리는 역할(용·희·기·구신)과 후보 줄이 정한다(판정 우선순위 원칙).
- 시주 미상이면 블록을 내지 않는다(미상≠없음 — '드러난 글자 없음'을 말할 수 없다).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from saju_manse_core.calendar.sexagenary_cycle import year_ganzi
from saju_shared_types.constants import main_hidden_stem, ten_god
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.structure_patterns import DetectedPattern

from .daewoon_turn import CORE_WEIGHT, jiao_date_of
from .event_scoring import daewoon_transition_weight
from .hidden_latent_activation import LuckUnit, luck_units
from .luck_structure_tags import NatalStructureProfile, natal_structure_profile
from .pattern_conditions import GROUP_OF
from .structure_patterns import detect_structure_patterns

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"

LENS_POSITION = "position_seal"
LENS_BUSINESS = "business"
LENS_WEALTH = "wealth"
LENS_CHILDREN_FEMALE = "children_female"
LENS_CHILDREN_MALE = "children_male"
#: 사업 사건 키 — 리포트 직업 섹션이 이 사건의 후보 기간에만 사업 렌즈를 싣는다.
BUSINESS_EVENT_KEYS: frozenset[str] = frozenset({"business_start", "business_expansion"})
#: 출산·자녀 사건 키 — 자녀성은 성별로 갈린다(`children_lens`).
CHILDBIRTH_EVENT_KEY = "childbirth"

#: 사건 키 → 렌즈. 사건이 정해진 질문은 이 표만 본다(이직·횡재처럼 표에 없는 사건은 렌즈 없음 —
#: 이직은 직장 운 결 층, 횡재는 횡재 신호 층이 맡는다).
_EVENT_LENS: dict[str, str] = {
    "education_admission": LENS_POSITION,
    "job_gain": LENS_POSITION,
    "promotion": LENS_POSITION,
    "business_start": LENS_BUSINESS,
    "business_expansion": LENS_BUSINESS,
    "wealth_change": LENS_WEALTH,
}
#: 사건 키가 없는 질문의 도메인 → 렌즈.
_DOMAIN_LENS: dict[str, str] = {"education": LENS_POSITION, "wealth": LENS_WEALTH}

#: 층 줄 상한 — 넘으면 그 층은 통째로 싣지 않는다(일부만 실으면 실리지 않은 기간을 오독한다).
MAX_DAEWOON = 2
MAX_YEARS = 6
MAX_MONTHS = 6
#: '다음에 드는 해' 탐색 범위(질문 기간 뒤 몇 해)와 군마다 싣는 해 수.
NEXT_ARRIVAL_SPAN = 12
NEXT_ARRIVAL_COUNT = 2

_LAYER_KO: dict[str, str] = {"daewoon": "대운", "sewoon": "세운", "wolwoon": "월운"}
_POS_KO: dict[str, str] = {"stem": "천간", "branch": "지지"}

AXIS_LENS_RULE = (
    "(위 줄은 이 주제의 일이 어떤 모양으로 올 수 있는지 보는 참고다. 표기된 층·글자만 쓰고 "
    "새 글자나 새 달을 지어내지 말 것. 달 줄은 후보로 실린 달만 본 것이니 실리지 않은 달을 두고 "
    "'글자가 없다'고 말하지 말 것. 유불리는 괄호의 역할(용신·희신·기신·구신)과 [이벤트 후보]를 "
    "따르고, 이 줄만으로 합격·성사·당락·임신·출산이나 그 시기를 확정하지 말 것. "
    "'이 기간에는 ○○ 글자가 없다'는 "
    "선언은 쓰지 말고 있는 글자를 말할 것. 답에는 1~3문장으로 녹이되 '~하기 쉽다'·'~할 수 있다' "
    "처럼 가능성으로 말할 것.)"
)


@dataclass(frozen=True)
class LensAxis:
    """렌즈의 축 십성군 하나."""

    group: str  # peer | output | wealth | officer | resource
    label: str  # '관성(자리·직책·평가)'


@dataclass(frozen=True)
class AxisLens:
    """주제 렌즈 — 축 십성군과 문구(사전 원본)."""

    key: str
    title: str
    intro: str
    axes: tuple[LensAxis, ...]
    chain_patterns: frozenset[str]
    bridge_excess: str | None
    bridge_group: str | None
    next_arrival: bool
    texts: dict[str, str]

    def label_of(self, group: str) -> str:
        """축 군의 표기(축이 아니면 군 키 그대로)."""
        return next((a.label for a in self.axes if a.group == group), group)

    def short_of(self, group: str) -> str:
        """축 군의 짧은 이름 — 표기에서 괄호 앞('관성')."""
        return self.label_of(group).split("(")[0]


@dataclass(frozen=True)
class AxisArrival:
    """운 기둥 하나에 축 십성군이 든 자리 하나."""

    unit: LuckUnit
    group: str
    position: str  # stem | branch
    glyph: str
    ten_god: str


@lru_cache(maxsize=4)
def load_axis_lenses(dictionaries_dir: Path = _DICTS_DEFAULT) -> dict[str, AxisLens]:
    """렌즈 사전(캐시) — 렌즈 키 → `AxisLens`."""
    path = dictionaries_dir / "interpretations" / "axis_arrival_lens.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, AxisLens] = {}
    for raw in data["lenses"]:
        out[raw["key"]] = AxisLens(
            key=raw["key"],
            title=raw["title"],
            intro=raw["intro"],
            axes=tuple(LensAxis(a["group"], a["label"]) for a in raw["axes"]),
            chain_patterns=frozenset(raw.get("chainPatterns") or ()),
            bridge_excess=raw.get("bridgeExcess"),
            bridge_group=raw.get("bridgeGroup"),
            next_arrival=bool(raw.get("nextArrival")),
            texts={it["id"]: it["text"] for it in raw["items"]},
        )
    return out


def is_judged_selection(selection_domain: str | None, question: str) -> bool:
    """선발 질문 가운데 심사로 뽑히는 것(공모·지원사업·선정)인가 — 자리·자격 렌즈 대상.

    추첨·배정형(군 입대·청약·기숙사·티켓팅)은 관성·인성으로 풀 일이 아니므로 제외한다.

    Args:
        selection_domain: `selection_intent.detect_selection_query` 의 도메인(미감지면 None).
        question: 질문 원문.
    """
    if selection_domain is None:
        return False
    if selection_domain == "public_program":
        return True
    return selection_domain == "generic" and any(w in question for w in ("공모", "선정", "선발"))


def children_lens(gender: str | None) -> str | None:
    """출산·자녀 렌즈 키 — 여성 식상 / 남성 관성(자녀성 성별 분기, M05 와 같은 대응).

    성별 미상이면 None(자녀성을 정할 수 없으면 말하지 않는다).
    """
    if gender == "female":
        return LENS_CHILDREN_FEMALE
    if gender == "male":
        return LENS_CHILDREN_MALE
    return None


def lens_for(
    event_key: str | None,
    domain: str | None,
    *,
    selection: bool = False,
    gender: str | None = None,
) -> str | None:
    """질문의 사건 키·도메인에 맞는 렌즈 키(없으면 None).

    Args:
        event_key: 의도 사건 키(없으면 None). 있으면 사건 표만 본다.
        domain: 질문 도메인 값(`Domain.value`). 사건 키가 없을 때만 쓴다.
        selection: 공모·지원사업처럼 심사로 뽑히는 선발 질문이면 True — 자리·자격 렌즈.
        gender: 명식 성별('male'·'female'·그 밖) — 출산·자녀 질문의 자녀성 분기에만 쓴다.
    """
    if selection:
        return LENS_POSITION
    if event_key == CHILDBIRTH_EVENT_KEY:
        return children_lens(gender)
    if event_key:
        return _EVENT_LENS.get(event_key)
    return _DOMAIN_LENS.get(domain or "")


def axis_arrivals(
    profile: NatalStructureProfile, lens: AxisLens, units: Sequence[LuckUnit],
) -> list[AxisArrival]:
    """운 기둥들에서 축 십성군이 든 자리(천간 → 지지 본기 순). 간지가 온전하지 않으면 건너뛴다."""
    dm = Stem(profile.day_master)
    groups = {a.group for a in lens.axes}
    out: list[AxisArrival] = []
    for u in units:
        if len(u.ganji) < 2:
            continue
        try:
            stem_god = str(ten_god(dm, Stem(u.ganji[0])))
            branch_god = str(ten_god(dm, main_hidden_stem(Branch(u.ganji[1]))))
        except ValueError:
            continue
        for pos, glyph, god in (("stem", u.ganji[0], stem_god), ("branch", u.ganji[1], branch_god)):
            grp = GROUP_OF.get(god)
            if grp in groups:
                out.append(AxisArrival(u, grp, pos, glyph, god))
    return out


def _period_bounds(labels: Sequence[str]) -> tuple[date, date] | None:
    """기간 라벨들의 (가장 이른 날, 가장 늦은 날) — 'YYYY' 는 그 해 전체, 'YYYY-MM' 은 그 달."""
    lows: list[date] = []
    highs: list[date] = []
    for lb in labels:
        try:
            if len(lb) == 4:
                lows.append(date(int(lb), 1, 1))
                highs.append(date(int(lb), 12, 31))
            elif len(lb) >= 7:
                y, m = int(lb[:4]), int(lb[5:7])
                lows.append(date(y, m, 1))
                highs.append(date(y, m, 28))
        except ValueError:
            continue
    if not lows:
        return None
    return min(lows), max(highs)


def daewoon_turn_near(result: ManseV2Result, labels: Sequence[str]) -> list[str]:
    """질문 기간이 대운 교체의 앞뒤 1년(교운 가중 ≥ `CORE_WEIGHT`)에 걸리면 그 교체 표기 목록.

    교운일·가중은 교운 방향 층(`daewoon_turn`)과 같은 엔진 값을 쓴다.

    Returns:
        '2030년 무렵 대운 교체(壬辰 → 癸巳)' 형태. 걸리는 교체가 없으면 빈 목록.
    """
    lc = result.luck_cycles
    bounds = _period_bounds(labels)
    if lc is None or bounds is None or len(lc.daewoon_table) < 2:
        return []
    lo, hi = bounds
    out: list[str] = []
    table = lc.daewoon_table
    for prev, nxt in zip(table, table[1:], strict=False):
        jiao = jiao_date_of(result, nxt.approx_start_date)
        nearest = min(max(jiao, lo), hi)
        if daewoon_transition_weight(nearest, [jiao]) >= CORE_WEIGHT:
            out.append(f"{jiao.year}년 무렵 대운 교체({prev.ganji} → {nxt.ganji})")
    return out


def next_arrival_years(
    profile: NatalStructureProfile, group: str, after_year: int,
) -> list[str]:
    """`after_year` 뒤로 그 십성군이 세운(천간 또는 지지 본기)에 드는 해 — 앞에서부터 상한까지.

    Returns:
        '2028 戊申(지지)' 형태. 간지는 달력 계산(`year_ganzi`)이다.
    """
    dm = Stem(profile.day_master)
    out: list[str] = []
    for y in range(after_year + 1, after_year + 1 + NEXT_ARRIVAL_SPAN):
        stem, branch = year_ganzi(y)
        pos = [
            _POS_KO[p] for p, g in (
                ("stem", GROUP_OF.get(str(ten_god(dm, stem)))),
                ("branch", GROUP_OF.get(str(ten_god(dm, main_hidden_stem(branch))))),
            ) if g == group
        ]
        if pos:
            out.append(f"{y} {stem.value}{branch.value}({'·'.join(pos)})")
        if len(out) >= NEXT_ARRIVAL_COUNT:
            break
    return out


def _state(profile: NatalStructureProfile, group: str) -> str:
    """축 군의 원국 상태 표기 — 드러난 글자 없음 / 많음 / 있음(+세력·역할)."""
    share = f"세력 {profile.group_share.get(group, 0.0):.0f}%"
    if group in profile.absent_groups:
        state = f"드러난 글자 없음({share})"
    elif group in profile.excess_groups:
        state = f"많음({share})"
    else:
        state = f"있음({share})"
    role = profile.role_of(group)
    return f"{state} · {role}" if role else state


def _where(arrivals: Sequence[AxisArrival]) -> str:
    """도래 자리 묶음 표기 — '세운 2027 천간·월운 2027-05 지지'."""
    seen: list[str] = []
    for a in arrivals:
        tag = f"{_LAYER_KO[a.unit.layer]} {a.unit.label} {_POS_KO[a.position]}"
        if tag not in seen:
            seen.append(tag)
    return "·".join(seen)


def axis_arrival_block(
    result: ManseV2Result,
    periods: Sequence[tuple[str, str]],
    lens_key: str | None,
    *,
    natal_patterns: Sequence[DetectedPattern] | None = None,
) -> list[str]:
    """축 글자 도래 블록(채팅 말미·리포트 기간 섹션 공용) — 실을 내용이 없으면 빈 목록.

    Args:
        result: 본인 명식.
        periods: (기간 라벨, 운 간지). 'YYYY-MM' 라벨의 간지는 월운, 'YYYY' 라벨은 세운(간지 없어도
            달력 계산으로 채운다) — `hidden_latent_activation.luck_units` 와 같은 약속.
        lens_key: 렌즈 키(`lens_for` 결과). None·미정의 키면 빈 목록.
        natal_patterns: 원국 감지 패턴(이미 구해 둔 값이 있으면 넘긴다. None 이면 여기서 감지).

    Returns:
        머리말 + (원국 줄) + 운 층 줄 + 뜻 줄 + 사용 규칙. 뜻 줄도 덧붙일 줄(다음에 드는 해·대운
        교체)도 없으면 빈 목록.
    """
    if lens_key is None or not periods:
        return []
    lens = load_axis_lenses().get(lens_key)
    if lens is None or result.pillars is None or result.pillars.hour is None:
        return []
    patterns = list(natal_patterns) if natal_patterns is not None else list(
        detect_structure_patterns(result)
    )
    profile = natal_structure_profile(result, patterns)
    if profile is None:
        return []
    units = luck_units(result, list(periods))
    if not units:
        return []
    by_layer: dict[str, list[LuckUnit]] = {"daewoon": [], "sewoon": [], "wolwoon": []}
    for u in units:
        by_layer[u.layer].append(u)
    for us in by_layer.values():
        us.sort(key=lambda u: u.label)  # 후보 등장 순이 아니라 시점 순으로 싣는다
    caps = {"daewoon": MAX_DAEWOON, "sewoon": MAX_YEARS, "wolwoon": MAX_MONTHS}
    shown = [u for layer, us in by_layer.items() if len(us) <= caps[layer] for u in us]
    t = lens.texts
    # 대운에 든 축 글자는 그 군의 '대운에 놓인 10년' 문구가 있는 렌즈에서만 본다 — 뜻을 말해 줄
    # 문구가 없는 글자를 줄로만 실으면 읽는 쪽이 뜻을 지어낸다.
    arrivals = [
        a for a in axis_arrivals(profile, lens, shown)
        if a.unit.layer != "daewoon" or f"decade.{a.group}" in t
    ]
    has_natal_forms = any(
        k.startswith(("absent_arrive.", "chain_")) or k == "bridge" for k in t
    )

    unit_lines: list[str] = []
    for u in shown:
        here = [a for a in arrivals if a.unit is u]
        if not here:
            continue
        parts = []
        for a in here:
            role = profile.role_of(a.group)
            tail = f"{lens.short_of(a.group)}" + (f" · {role}" if role else "")
            parts.append(f"{_POS_KO[a.position]} {a.glyph} = {a.ten_god}({tail})")
        unit_lines.append(f"{_LAYER_KO[u.layer]} {u.label} {u.ganji}: " + " / ".join(parts))

    meaning: list[str] = []
    # 천간·지지 양상 — 세운·월운에 실제로 나온 (군, 자리) 조합마다 한 번(대운은 10년 배경이라
    # 사건의 모양을 말하지 않는다 — 대운 줄은 아래 '대운에 놓인 축 군'이 맡는다).
    timed = [a for a in arrivals if a.unit.layer != "daewoon"]
    for axis in lens.axes:
        for pos in ("stem", "branch"):
            key = f"aspect.{axis.group}.{pos}"
            if key in t and any(a.group == axis.group and a.position == pos for a in timed):
                meaning.append(f"- {t[key]}")
    # 원국에 드러난 글자가 없던 군이 들어옴(과다 군을 건너는 다리이면 그 문구로 대신한다).
    for axis in lens.axes:
        came = [a for a in arrivals if a.group == axis.group]
        if not came or axis.group not in profile.absent_groups:
            continue
        is_bridge = (
            "bridge" in t and axis.group == lens.bridge_group
            and lens.bridge_excess in profile.excess_groups
        )
        key = "bridge" if is_bridge else f"absent_arrive.{axis.group}"
        if key in t:
            meaning.append(f"- [{_where(came)}] {t[key]}")
    # 대운에 놓인 축 군(10년 배경).
    for axis in lens.axes:
        came = [a for a in arrivals if a.group == axis.group and a.unit.layer == "daewoon"]
        key = f"decade.{axis.group}"
        if came and key in t:
            meaning.append(f"- [{_where(came)}] {t[key]}")
    # 원국에 이어지는 구조가 서 있고 운(세운·월운)에서 첫 축 군이 한 번 더 들어옴.
    chain_names = [
        name for pid, name in zip(profile.pattern_ids, profile.pattern_names, strict=False)
        if pid in lens.chain_patterns
    ]
    lead = lens.axes[0].group
    lead_came = [a for a in arrivals if a.group == lead and a.unit.layer != "daewoon"]
    if chain_names and lead_came and "chain_move" in t:
        line = f"- [{_where(lead_came)}] {t['chain_move']}"
        if "chain_long" in t and any(a.group in profile.excess_groups for a in lens.axes):
            line += " " + t["chain_long"]
        meaning.append(line)
    # 조언 — 세운·월운에 든 축 군마다 한 문장.
    for axis in lens.axes:
        key = f"care.{axis.group}"
        if key in t and any(
            a.group == axis.group and a.unit.layer != "daewoon" for a in arrivals
        ):
            meaning.append(f"- {t[key]}")

    extra: list[str] = []
    labels = [lb for lb, _g in periods]
    if "turn_care" in t:
        turns = daewoon_turn_near(result, labels)
        if turns:
            extra.append(f"- [{'·'.join(turns)}] {t['turn_care']}")
    # 다음에 드는 해 — 질문 기간의 세운에 들지 않은 축 군만(부재를 말하지 않고 드는 해를 말한다).
    sewoon_all = by_layer["sewoon"]
    if lens.next_arrival and sewoon_all:
        in_window = {a.group for a in axis_arrivals(profile, lens, sewoon_all)}
        last_year = max(int(u.label) for u in sewoon_all if u.label.isdigit())
        upcoming = [
            f"{lens.short_of(axis.group)} {'·'.join(years)}"
            for axis in lens.axes if axis.group not in in_window
            if (years := next_arrival_years(profile, axis.group, last_year))
        ]
        if upcoming:
            extra.append(
                "- 세운으로 드는 다음 해 — " + " / ".join(upcoming)
                + " (글자가 드는 해라는 사실일 뿐, 그 일이 이루어지는 시기의 근거로 쓰지 말 것)"
            )
    if not meaning and not extra:
        return []

    lines = [
        f"[{lens.title} — 원국 × 운에서 온 글자(엔진 판정 · 서술 전용 · 점수·당락 판정 아님)] "
        f"{lens.intro}"
    ]
    if has_natal_forms:
        natal = " · ".join(f"{a.label} — {_state(profile, a.group)}" for a in lens.axes)
        if chain_names:
            natal += " · 이어지는 구조 — " + "·".join(chain_names) + " 성립"
        lines.append(f"원국: {natal}")
    lines += [*unit_lines, *meaning, *extra, AXIS_LENS_RULE]
    return lines
