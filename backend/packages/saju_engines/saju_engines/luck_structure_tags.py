"""운 구조 태그 — '원국 구조 × 운 글자'를 사람 사이에 비교할 수 있는 태그로 정규화한다.

배경(2026-11-18 데굴님): 같은 십성이라도 원국 구성에 따라 역할이 다르다 — "원국의 구조는 이러한데
운에서 이런 십성이 와서 이런 결과가 났다"로 읽어야 한다. 그래서 운 글자를 십성 이름으로 두지 않고
① 그 명식에서 맡은 역할(용·희·기·구·한) ② 원국 세력 대비 위치(없는 군을 채움 / 과다 군을 더함)
③ 운 스택(대운→세운→월운)에서 서거나 풀리는 구조 계열 ④ 원국 월지와의 합·충으로 옮긴다.

모든 값은 엔진 출력에서 읽는다(손 계산 없음): 역할=`yongsin_analysis.final`, 세력=
`force_analysis.ten_gods`, 구조 상태=`pattern_transit.evaluate_pattern_states`(직전 층 대비),
계열=`structure_patterns.json` family, 합·충=`shared_types.constants` 표.

순수 함수·서술/측정 전용 — 점수·판정을 바꾸지 않는다. 시주 미상이면 구조 상태 태그는 비고
(패턴 운 판정 정책), 역할·세력 태그만 나온다. SSOT: doc/v2_2/EMPLOYMENT_HISTORY_CALIBRATION.md §7.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from saju_shared_types.constants import (
    BRANCH_CLASHES,
    SIX_COMBINATIONS,
    main_hidden_stem,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.structure_patterns import DetectedPattern

from .pattern_conditions import GROUP_OF
from .pattern_transit import LuckGlyph, evaluate_pattern_states, transit_type_of
from .structure_patterns import load_structure_patterns

#: 십성군 키 → 한글(서술·로그용).
GROUP_KO: dict[str, str] = {
    "peer": "비겁", "output": "식상", "wealth": "재성", "officer": "관성", "resource": "인성",
}
#: 원국 세력 '과다' 기준(%) — 구조 사전 과다 계열 근거 문구('과다(30%+)')와 같은 값.
EXCESS_PCT = 30.0
_ROLE_KEYS: tuple[tuple[str, str], ...] = (
    ("yongsin", "용신"), ("heesin", "희신"), ("gisin", "기신"), ("gusin", "구신"),
    ("hansin", "한신"),
)
_FAVORABLE = frozenset({"용신", "희신"})
_UNFAVORABLE = frozenset({"기신", "구신"})
#: 부담 계열(과다·충돌·형·건강 부담) / 받침 계열(상생·통관·제어) — structure_patterns.json family.
BURDEN_FAMILIES = frozenset({"overload", "conflict", "punishment", "health_burden"})
HELP_FAMILIES = frozenset({"generation_flow", "mediation", "control"})

# 태그 어휘(지문·로그·서술 공용 — 문자열 고정).
TAG_YONG_GROUP = "yong_group"          # 용신 군 글자가 옴
TAG_FAV_ANY = "fav_any"                # 용·희신 글자가 하나 이상
TAG_FAV_ALL = "fav_all"                # 천간·지지 모두 용·희신
TAG_UNFAV_ALL = "unfav_all"            # 천간·지지 모두 기·구신
TAG_ABSENT_SUPPLY = "absent_supply"    # 원국에 드러난 글자가 없는 군을 채움
TAG_EXCESS_ADD = "excess_add"          # 원국 과다 군을 더함
TAG_BURDEN_UP = "burden_up"            # 부담 계열 구조가 서거나 강해짐
TAG_BURDEN_DOWN = "burden_down"        # 부담 계열 구조가 풀리거나 약해짐
TAG_HELP_UP = "help_up"                # 받침 계열 구조가 서거나 강해짐
TAG_HELP_DOWN = "help_down"            # 받침 계열 구조가 풀리거나 약해짐
TAG_MB_ECHO = "month_branch_echo"      # 원국 월지와 같은 글자
TAG_MB_CLASH = "month_branch_clash"    # 원국 월지와 충
TAG_MB_HAP = "month_branch_hap"        # 원국 월지와 육합

_UP_STATUS = frozenset({"new", "strengthened"})
_DOWN_STATUS = frozenset({"weakened", "resolved"})


@dataclass(frozen=True)
class NatalStructureProfile:
    """원국 구조 요약 — 십성군 세력·역할·원국 구조 배합."""

    day_master: str
    band: str                                # 신강약 밴드
    group_share: dict[str, float]            # 군 키 → 실세력 %(effective_percent 합)
    absent_groups: frozenset[str]            # 드러난 글자(천간·지지 본기)가 없는 군
    excess_groups: frozenset[str]            # 실세력 EXCESS_PCT 이상
    group_role: dict[str, str]               # 군 키 → 용신/희신/기신/구신/한신('' = 미정)
    month_branch: str
    pattern_names: tuple[str, ...]           # 원국 성립 구조 배합(한글명, 강도순)
    pattern_ids: tuple[str, ...]
    #: 그중 운에 따라 상태가 달라지는 구조(운 판정 유형 T1~T5)이면서 부담·받침 계열인 것.
    core_pattern_names: tuple[str, ...] = ()

    def role_of(self, group: str) -> str:
        """군의 역할 한글명(미정이면 빈 문자열)."""
        return self.group_role.get(group, "")


def natal_structure_profile(
    result: ManseV2Result, natal_patterns: Sequence[DetectedPattern] = (),
) -> NatalStructureProfile | None:
    """만세력 결과에서 원국 구조 요약을 만든다. 원국·세력·용신이 없으면 None."""
    pillars, force, yong = result.pillars, result.force_analysis, result.yongsin_analysis
    if pillars is None or force is None or yong is None:
        return None
    tg = force.ten_gods
    share: dict[str, float] = dict.fromkeys(GROUP_KO, 0.0)
    visible: dict[str, float] = dict.fromkeys(GROUP_KO, 0.0)
    for name, pct in tg.effective_percent.items():
        grp = GROUP_OF.get(name)
        if grp is not None:
            share[grp] += float(pct)
    for name, cnt in tg.raw_visible.items():
        grp = GROUP_OF.get(name)
        if grp is not None:
            visible[grp] += float(cnt)
    dm = Stem(pillars.day.stem)
    final = yong.final or {}
    element_role = {str(final[k]): ko for k, ko in _ROLE_KEYS if final.get(k)}
    group_element = _group_elements(dm)
    return NatalStructureProfile(
        day_master=str(dm),
        band=force.strength.band,
        group_share={g: round(v, 2) for g, v in share.items()},
        absent_groups=frozenset(g for g, v in visible.items() if v == 0),
        excess_groups=frozenset(g for g, v in share.items() if v >= EXCESS_PCT),
        group_role={g: element_role.get(el, "") for g, el in group_element.items()},
        month_branch=str(pillars.month.branch),
        pattern_names=tuple(p.name_ko for p in natal_patterns),
        pattern_ids=tuple(p.pattern_id for p in natal_patterns),
        core_pattern_names=tuple(
            p.name_ko for p in natal_patterns
            if transit_type_of(p.pattern_id) is not None
            and frozenset(p.family) & (BURDEN_FAMILIES | HELP_FAMILIES)
        ),
    )


def _group_elements(dm: Stem) -> dict[str, str]:
    """일간 기준 군 키 → 오행(한자). 열 천간을 십성으로 분류해 얻는다(표 재작성 없음)."""
    from saju_shared_types.constants import STEM_ELEMENT, STEMS

    out: dict[str, str] = {}
    for s in STEMS:
        grp = GROUP_OF.get(str(ten_god(dm, s)))
        if grp is not None:
            out.setdefault(grp, str(STEM_ELEMENT[s].value))
    return out


def glyph_groups(day_master: str, stem: str, branch: str) -> tuple[str, str]:
    """운 글자의 (천간 군, 지지 본기 군) 키."""
    dm = Stem(day_master)
    sg = GROUP_OF[str(ten_god(dm, Stem(stem)))]
    bg = GROUP_OF[str(ten_god(dm, main_hidden_stem(Branch(branch))))]
    return sg, bg


@dataclass(frozen=True)
class LuckLayerReading:
    """운 한 층(스택 마지막 글자)이 원국 구조에 한 일 — 태그와 서술 재료."""

    stem_god: str                      # 천간 십성(한글)
    branch_god: str                    # 지지 본기 십성(한글)
    stem_group: str                    # 군 키
    branch_group: str
    stem_role: str                     # 용신/희신/기신/구신/한신(미정이면 '')
    branch_role: str
    tags: tuple[str, ...]              # 정렬된 고정 어휘(TAG_*)
    #: 이 층에서 달라진 구조 — (구조 한글명, 'burden'|'help', new|strengthened|weakened|resolved).
    changes: tuple[tuple[str, str, str], ...] = ()


def read_luck_layer(
    result: ManseV2Result,
    profile: NatalStructureProfile,
    natal_patterns: Sequence[DetectedPattern],
    stack: Sequence[LuckGlyph],
) -> LuckLayerReading | None:
    """운 스택 **마지막 층**의 읽기(역할·원국 대비 위치·구조 변화·월지 관계). 스택이 비면 None.

    Args:
        result: 만세력 결과.
        profile: `natal_structure_profile` 결과.
        natal_patterns: 원국 감지 패턴 전체(`detect_structure_patterns`).
        stack: 대운→세운→월운 순 누적 운 글자. 구조 상태는 직전 층 대비로 읽는다
            (세운은 대운 위에서, 월운은 대운·세운 위에서).
    """
    if not stack:
        return None
    last = stack[-1]
    dm = Stem(profile.day_master)
    stem_god = str(ten_god(dm, Stem(last.stem)))
    branch_god = str(ten_god(dm, main_hidden_stem(Branch(last.branch))))
    sg, bg = GROUP_OF[stem_god], GROUP_OF[branch_god]
    groups = {sg, bg}
    roles = {profile.role_of(g) for g in groups}
    tags: set[str] = set()
    if "용신" in roles:
        tags.add(TAG_YONG_GROUP)
    if roles & _FAVORABLE:
        tags.add(TAG_FAV_ANY)
    if roles <= _FAVORABLE:
        tags.add(TAG_FAV_ALL)
    if roles <= _UNFAVORABLE:
        tags.add(TAG_UNFAV_ALL)
    if groups & profile.absent_groups:
        tags.add(TAG_ABSENT_SUPPLY)
    if groups & profile.excess_groups:
        tags.add(TAG_EXCESS_ADD)
    families = {e.pattern_id: frozenset(e.family) for e in load_structure_patterns().patterns}
    changes: list[tuple[str, str, str]] = []
    for st in evaluate_pattern_states(result, natal_patterns, stack):
        fam = families.get(st.pattern_id, frozenset())
        up, down = st.status_vs_parent in _UP_STATUS, st.status_vs_parent in _DOWN_STATUS
        if not (up or down):
            continue
        if fam & BURDEN_FAMILIES:
            tags.add(TAG_BURDEN_UP if up else TAG_BURDEN_DOWN)
            changes.append((st.name_ko, "burden", st.status_vs_parent))
        if fam & HELP_FAMILIES:
            tags.add(TAG_HELP_UP if up else TAG_HELP_DOWN)
            changes.append((st.name_ko, "help", st.status_vs_parent))
    pair = frozenset({Branch(last.branch), Branch(profile.month_branch)})
    if last.branch == profile.month_branch:
        tags.add(TAG_MB_ECHO)
    elif pair in BRANCH_CLASHES:
        tags.add(TAG_MB_CLASH)
    elif pair in SIX_COMBINATIONS:
        tags.add(TAG_MB_HAP)
    return LuckLayerReading(
        stem_god=stem_god, branch_god=branch_god, stem_group=sg, branch_group=bg,
        stem_role=profile.role_of(sg), branch_role=profile.role_of(bg),
        tags=tuple(sorted(tags)), changes=tuple(changes),
    )


def luck_structure_tags(
    result: ManseV2Result,
    profile: NatalStructureProfile,
    natal_patterns: Sequence[DetectedPattern],
    stack: Sequence[LuckGlyph],
) -> list[str]:
    """운 스택 **마지막 층**의 구조 태그(정렬된 고정 어휘) — `read_luck_layer` 의 태그만."""
    reading = read_luck_layer(result, profile, natal_patterns, stack)
    return list(reading.tags) if reading is not None else []


# ── 서술 블록(채팅·리포트 공용) ──────────────────────────────────────────────

#: 블록에 싣는 층 수 상한 — 넘으면 그 층은 통째로 싣지 않는다(일부만 실으면 오독한다).
ROLE_BLOCK_MAX_MONTHS = 3
ROLE_BLOCK_MAX_YEARS = 6
#: 대운별 페이지(총운 F-14-D*)용 세운 상한 — 한 대운의 10년을 통째로 싣는다(2026-11-18).
ROLE_BLOCK_DECADE_YEARS = 10
ROLE_BLOCK_MAX_CHANGES = 3
_STATUS_KO = {"new": "새로 섬", "strengthened": "강해짐", "weakened": "약해짐", "resolved": "풀림"}
_KIND_KO = {"burden": "과다·충돌 계열", "help": "상생·제어 계열"}

NATAL_LUCK_ROLE_DIRECTIVE = (
    "같은 십성이라도 명식마다 맡은 역할이 다르다. 운을 풀 때 십성 이름만으로 좋고 나쁨이나 사건을 "
    "말하지 말고, ① 아래 '원국' 줄의 구조를 한 구절로 밝히고 ② 각 운 줄의 글자가 그 구조에 한 일"
    "(없던 것이 들어옴·많은 것이 더해짐·구조가 서거나 풀림)을 말한 뒤 ③ 그래서 이 기간에 나타나는 "
    "모습을 서술할 것. 층의 크기를 지킬 것 — 대운은 10년의 판, 세운은 그 판 위에서 그 해에 "
    "드러나는 일, 월운은 그 해 안의 시점이다. 대운·세운·월운을 따로 떼어 각각 풀지 말고 위 층이 "
    "깔아 둔 것 위에서 아래 층을 말할 것. 아래에 없는 역할·구조를 지어내지 말 것 — 구조 변화는 "
    "작동 방식의 설명이지 길흉 확정이 아니다."
)


def _natal_line(profile: NatalStructureProfile) -> str:
    """'원국' 한 줄 — 신강약·군 세력(과다/드러난 글자 없음 표지)·역할·핵심 구조."""
    shares = "·".join(
        f"{GROUP_KO[g]} {profile.group_share[g]:.0f}%"
        + ("(과다)" if g in profile.excess_groups else "")
        + ("(드러난 글자 없음)" if g in profile.absent_groups else "")
        for g in GROUP_KO
    )
    roles = "·".join(f"{GROUP_KO[g]}={profile.role_of(g)}" for g in GROUP_KO if profile.role_of(g))
    line = f"원국: {profile.band} · 세력 — {shares}"
    if roles:
        line += f" · 역할 — {roles}"
    if profile.core_pattern_names:
        line += " · 구조 — " + "·".join(profile.core_pattern_names[:4])
    return line


def _reading_phrases(profile: NatalStructureProfile, r: LuckLayerReading) -> str:
    """층 읽기 → '원국 구조에 한 일' 구절(없으면 변화 없음)."""
    groups = [r.stem_group] + ([r.branch_group] if r.branch_group != r.stem_group else [])
    out: list[str] = []
    supplied = [GROUP_KO[g] for g in groups if g in profile.absent_groups]
    added = [GROUP_KO[g] for g in groups if g in profile.excess_groups]
    if supplied:
        out.append(f"원국에 드러난 글자가 없는 {'·'.join(supplied)}이 들어옴")
    if added:
        out.append(f"원국에 이미 많은 {'·'.join(added)}이 더해짐")
    # 한 구조가 두 계열에 모두 걸리면(예: 살중제경) 이름을 두 번 쓰지 않고 계열을 한 괄호에 묶는다.
    merged: dict[tuple[str, str], list[str]] = {}
    for name, kind, status in r.changes:
        merged.setdefault((name, status), []).append(_KIND_KO[kind])
    for (name, status), kinds in list(merged.items())[:ROLE_BLOCK_MAX_CHANGES]:
        out.append(f"{name}({' 겸 '.join(kinds)}) {_STATUS_KO[status]}")
    if TAG_MB_ECHO in r.tags:
        out.append("원국 월지와 같은 글자")
    elif TAG_MB_CLASH in r.tags:
        out.append("원국 월지와 충")
    elif TAG_MB_HAP in r.tags:
        out.append("원국 월지와 합")
    return "; ".join(out) if out else "원국 구조에 뚜렷한 변화 없음"


def _layer_line(
    prefix: str, ganji: str, profile: NatalStructureProfile, r: LuckLayerReading,
) -> str:
    """층 한 줄 — '대운 壬辰: 천간 정재(구신)·지지 겁재(용신) — 원국 구조에 한 일'."""
    stem = f"천간 {r.stem_god}" + (f"({r.stem_role})" if r.stem_role else "")
    branch = f"지지 {r.branch_god}" + (f"({r.branch_role})" if r.branch_role else "")
    return f"{prefix} {ganji}: {stem}·{branch} — {_reading_phrases(profile, r)}"


def natal_luck_role_lines(
    result: ManseV2Result,
    natal_patterns: Sequence[DetectedPattern],
    *,
    daewoon_by_year: dict[int, str],
    sewoon_by_year: dict[int, str],
    month_ganji: dict[str, str],
    labels: Sequence[str],
    max_years: int | None = None,
) -> list[str]:
    """'원국 구조 × 운에서 온 글자' 블록 — 원국 한 줄 + 대운·세운·월운 층 줄(헤더·지시문 포함).

    기간 라벨('YYYY'·'YYYY-MM')이 가리키는 층을 위에서 아래로 싣는다: 관할 대운(중복 제거) →
    세운 → 월운. 세운·월운은 상한(`ROLE_BLOCK_MAX_YEARS`·`ROLE_BLOCK_MAX_MONTHS`)을 넘으면 그 층을
    통째로 뺀다 — 여러 해·여러 달 질문은 대운(과 세운) 판만 깔고, 기간별 변화는 기존 '운에서 서는
    구조' 줄이 맡는다. 시주 미상·용신 미정이면 빈 목록(불완전 정보로 역할을 말하지 않는다).

    Args:
        result: 만세력 결과.
        natal_patterns: 원국 감지 패턴 전체.
        daewoon_by_year: 연도 → 관할 대운 간지(`pattern_transit.daewoon_ganji_by_year`).
        sewoon_by_year: 연도 → 세운 간지.
        month_ganji: 절기월 라벨 → 월운 간지(월 줄을 실을 라벨만 있으면 된다).
        labels: 질문 기간 라벨.
        max_years: 세운 줄 상한 덮어쓰기(None=`ROLE_BLOCK_MAX_YEARS`). 대운별 페이지처럼 한 대운의
            10년이 그 페이지의 본문인 자리만 `ROLE_BLOCK_DECADE_YEARS` 를 넘긴다.
    """
    year_cap = ROLE_BLOCK_MAX_YEARS if max_years is None else max_years
    if result.pillars is None or result.pillars.hour is None:
        return []
    profile = natal_structure_profile(result, natal_patterns)
    if profile is None or not any(profile.group_role.values()):
        return []
    asked_months = {lb for lb in labels if len(lb) == 7}
    # 달 줄은 질문한 달 수가 상한 이하일 때만(간지가 일부만 넘어와도 일부만 싣지 않는다).
    month_labels = (
        sorted(lb for lb in asked_months if lb in month_ganji)
        if len(asked_months) <= ROLE_BLOCK_MAX_MONTHS else []
    )
    month_year = {lb: int(lb[:4]) - (1 if lb[5:7] == "01" else 0) for lb in asked_months}
    years = sorted(
        {int(lb) for lb in labels if len(lb) == 4 and lb.isdigit()} | set(month_year.values())
    )
    if not years:
        return []
    lines: list[str] = []
    seen_dw: list[str] = []
    for y in years:
        dw = daewoon_by_year.get(y)
        if not dw or dw in seen_dw:
            continue
        seen_dw.append(dw)
        r = read_luck_layer(result, profile, natal_patterns, [LuckGlyph("daewoon", dw[0], dw[1])])
        if r is not None:
            lines.append(_layer_line("대운", dw, profile, r))

    def _base(y: int) -> list[LuckGlyph]:
        dw = daewoon_by_year.get(y)
        return [LuckGlyph("daewoon", dw[0], dw[1])] if dw else []

    if len(years) <= year_cap:
        for y in years:
            sw = sewoon_by_year.get(y)
            if not sw:
                continue
            r = read_luck_layer(
                result, profile, natal_patterns, [*_base(y), LuckGlyph("year", sw[0], sw[1])],
            )
            if r is not None:
                lines.append(_layer_line("세운", f"{sw} {y}년", profile, r))
    if month_labels:
        for lb in month_labels:
            y, mg = month_year[lb], month_ganji[lb]
            sw = sewoon_by_year.get(y)
            stack = [*_base(y), *([LuckGlyph("year", sw[0], sw[1])] if sw else []),
                     LuckGlyph("month", mg[0], mg[1])]
            r = read_luck_layer(result, profile, natal_patterns, stack)
            if r is not None:
                lines.append(_layer_line("월운", f"{lb} {mg}", profile, r))
    if not lines:
        return []
    span = f"{min(labels)}–{max(labels)}" if len(set(labels)) > 1 else labels[0]
    header = f"[원국 구조 × 운에서 온 글자 — {span}, 엔진 판정] " + NATAL_LUCK_ROLE_DIRECTIVE
    return [header, _natal_line(profile), *lines]


ENTRY_TENURE_HEADER = "[입사 뒤 재직 기간 — 가능성]"
#: 가능성 줄에 싣는 해 상한(넘으면 앞에서부터).
ENTRY_TENURE_MAX_YEARS = 3


def entry_tenure_possibility_line(
    result: ManseV2Result,
    natal_patterns: Sequence[DetectedPattern],
    *,
    daewoon_by_year: dict[int, str],
    sewoon_by_year: dict[int, str],
    periods: Sequence[str],
) -> str | None:
    """입사 후보 기간 가운데 세운에 용신 군 글자가 오는 해 → '오래 재직하게 될 수도 있다' 한 줄.

    2026-11-18 데굴님 결정: '용신 세운 입사 = 장기 재직'은 한 사람의 이력(1년 이상 4곳 전부,
    1년 미만 7곳 중 1곳)에서만 확인됐고 다른 대상에서는 퇴사 기록이 없어 검증되지 않았다.
    그래서 규칙·등급이 아니라 "이 시점 입사의 경우 장기 재직할 수도 있다" 정도의 **가능성 한
    문장**으로만 쓴다(EMPLOYMENT_HISTORY_CALIBRATION.md §9-3). 점수·성사 달 배정·조건 등급은
    건드리지 않는다.

    Args:
        result: 만세력 결과.
        natal_patterns: 원국 감지 패턴 전체.
        daewoon_by_year: 연도 → 관할 대운 간지.
        sewoon_by_year: 연도 → 세운 간지.
        periods: 입사 후보 기간 라벨('YYYY-MM' 절기월 또는 'YYYY'). 1월 라벨은 전년 세운에 속한다.

    Returns:
        지시문 한 줄. 시주 미상·용신 미정·해당 해 없음이면 None(표지 없는 해에 대해서는 아무 말도
        싣지 않는다 — '짧게 끝난다'는 반대 서술의 근거가 아니다).
    """
    if result.pillars is None or result.pillars.hour is None:
        return None
    profile = natal_structure_profile(result, natal_patterns)
    if profile is None:
        return None
    yong = [GROUP_KO[g] for g in GROUP_KO if profile.role_of(g) == "용신"]
    if not yong:
        return None
    years: list[int] = []
    for lb in periods:
        if len(lb) == 7 and lb[:4].isdigit() and lb[5:7].isdigit():
            y = int(lb[:4]) - (1 if lb[5:7] == "01" else 0)
        elif len(lb) == 4 and lb.isdigit():
            y = int(lb)
        else:
            continue
        if y not in years:
            years.append(y)
    hits: list[str] = []
    for y in sorted(years):
        sw = sewoon_by_year.get(y)
        if not sw:
            continue
        dw = daewoon_by_year.get(y)
        stack = [
            *([LuckGlyph("daewoon", dw[0], dw[1])] if dw else []),
            LuckGlyph("year", sw[0], sw[1]),
        ]
        r = read_luck_layer(result, profile, natal_patterns, stack)
        if r is None or TAG_YONG_GROUP not in r.tags:
            continue
        where = "·".join(
            f"{pos} {god}" for pos, god, role in (
                ("천간", r.stem_god, r.stem_role), ("지지", r.branch_god, r.branch_role),
            ) if role == "용신"
        )
        hits.append(f"{y}년({sw} — {where})")
    if not hits:
        return None
    shown = ", ".join(hits[:ENTRY_TENURE_MAX_YEARS])
    return (
        f"{ENTRY_TENURE_HEADER} {shown}은 세운에 이 명식의 용신 군({'·'.join(yong)}) 글자가 오는 "
        "해다. 성사 달·움직이는 달이 이 해에 들면 '이 시점의 입사는 오래 재직하게 될 수도 있다'는 "
        "가능성을 한 문장으로 덧붙일 것. 가능성 서술이다 — 재직 기간을 숫자로 말하거나 확정하지 "
        "말고, 이 표지가 없는 해의 입사를 '짧게 끝난다'로 뒤집어 말하지 말 것."
    )
