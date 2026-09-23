"""능동 제안(Direction Suggestion) 판정 엔진 (Phase B, docs/15).

십성군 과다·부족 상태(원국+운 합산)에 작동성·용신 역할·구조패턴·충파·신강약을
조합해 "이런 방향도 고려해볼 만하다" 수준의 방향 제안을 판정한다. LLM은 판정하지
않는다(절대원칙 1) — 여기서 매칭된 direction/caution 재료를 '고려' 톤으로 재서술만 한다.

구성:
- ``load_direction_suggestions``: 컴파일 스냅샷 우선 로더(structure_patterns 관행).
- ``build_direction_facts``: ManseV2Result → DirectionFacts 어댑터. 누락 계층은
  빈 값으로 두며, 빈 값은 조건 불일치로 처리된다(제안을 안 하는 쪽이 안전).
- ``evaluate_direction_suggestions``: (facts, dict) → 제안 목록 순수 함수.
- ``detect_direction_suggestions``: 편의 래퍼(facts 조립 + 평가).

판정 규칙(설계 docs/15 §6):
- 작동(active) = 원국 천간 투출 또는 지지 본기 노출, 또는 현재 운(대운·세운)
  간지(천간·지지 본기) 유입. 지장간 중기·여기에만 있으면 존재(present)하되 비작동.
- 군 상태 = 원국 표시 분포율(DIST 가중)과 운 글자를 합산 재계산. 운 글자 가중은
  원국 연주급(천간 10·지지 15×지장간 비율). 과다 >=35%, 부족 <9%
  (오행 임계 재사용 — 2026-07-09 사용자 확정).
- guard 매칭은 차단이 아니라 caution 모드 반전. 성립 채널이 없으면 제안 없음.
  복수 채널 성립 시 사전 순서가 우선순위(첫 채널 채택, 나머지는 evidence에 기록).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from saju_manse_analysis._chart import DIST_BRANCH_WEIGHT, DIST_STEM_WEIGHT

from saju_shared_types.constants import (
    STEM_ELEMENT,
    group_elements,
    hidden_stems_for,
    main_hidden_stem,
    ten_god,
)
from saju_shared_types.direction_suggestions import (
    DirectionFacts,
    DirectionRule,
    DirectionSuggestion,
    DirectionSuggestionDict,
    GroupStateValue,
    SuggestionCondition,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.event_engine import TEN_GOD_GROUP, TEN_GOD_KO_TO_KEY
from saju_shared_types.luck import DaewoonItem, LuckCycles, LuckPillar
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.pillars import FourPillarsResult, Pillar

from .structure_patterns import detect_structure_patterns

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
_COMPILED_DEFAULT = Path(__file__).resolve().parents[3] / "compiled"
DIRECTION_SUGGESTIONS_VERSION = "1.0.0"

# 합산 임계(오행 과다/부족 기준 재사용 — element_distribution과 동일 수치).
EXCESS_PCT = 35.0
DEFICIENT_PCT = 9.0
# 운 글자 합산 가중 — 원국 연주급 취급(DIST_STEM_WEIGHT/DIST_BRANCH_WEIGHT year 값).
_LUCK_STEM_WEIGHT = 10.0
_LUCK_BRANCH_WEIGHT = 15.0
# 제안 강도: 기본 0.5 + support 매칭당 0.15 (상한 1.0).
_STRENGTH_BASE = 0.5
_STRENGTH_PER_SUPPORT = 0.15

_GROUPS = ("peer", "output", "wealth", "authority", "resource")
# 출력 group_state 선택 우선순위(구체적 상태 우선).
_STATE_PRIORITY: tuple[GroupStateValue, ...] = (
    "excess_intensified",
    "luck_excess_onset",
    "natal_excess",
    "luck_replenished",
    "deficient_persistent",
    "natal_deficient",
    "luck_inflow",
)
# 원국 interactions relation_type(영문 enum) → 사전 conflict_kinds(한글).
_RELATION_KIND_KO = {
    "clash": "충",
    "break": "파",
    "harm": "해",
    "punishment": "형",
    "self_punishment": "형",
}
# canonical_roles 키(역할 슬러그 → 오행) → 사전 역할 한글명.
_ROLE_SLUG_KO = {
    "yongsin": "용신",
    "heesin": "희신",
    "gisin": "기신",
    "gusin": "구신",
    "hansin": "한신",
}
# 군 → 소속 로마자 십성 (TEN_GOD_GROUP 역인덱스).
_GROUP_TEN_GODS: dict[str, list[str]] = {}
for _tg, _grp in TEN_GOD_GROUP.items():
    _GROUP_TEN_GODS.setdefault(_grp.value, []).append(_tg.value)


@lru_cache(maxsize=8)
def load_direction_suggestions(
    dictionaries_dir: Path = _DICTS_DEFAULT, compiled_dir: Path = _COMPILED_DEFAULT
) -> DirectionSuggestionDict:
    """능동 제안 사전을 로드한다 — 컴파일 스냅샷 우선, 원본 사전 폴백(원칙 5)."""
    snapshot = compiled_dir / f"direction_suggestions_v{DIRECTION_SUGGESTIONS_VERSION}.json"
    if snapshot.exists():
        return DirectionSuggestionDict.model_validate(json.loads(snapshot.read_text("utf-8")))
    raw = json.loads((dictionaries_dir / "direction_suggestions.json").read_text("utf-8"))
    return DirectionSuggestionDict.model_validate(raw)


# ── facts 조립 (ManseV2Result 어댑터) ─────────────────────────────────


def _iter_pillars(pillars: FourPillarsResult) -> list[tuple[str, Pillar]]:
    """(position, pillar) 목록 — 시주 미상이면 3주."""
    items = [("year", pillars.year), ("month", pillars.month), ("day", pillars.day)]
    if pillars.hour is not None:
        items.append(("hour", pillars.hour))
    return items


def _roman(tg_ko: str) -> str | None:
    """한글 십성 → 로마자 enum 값. 일간 등 매핑 밖 값은 None."""
    tg = TEN_GOD_KO_TO_KEY.get(tg_ko)
    return tg.value if tg else None


def _group_key(dm: Stem, stem: Stem) -> str | None:
    """일간 기준 글자의 십성군 값(peer/output/wealth/authority/resource)."""
    tg = TEN_GOD_KO_TO_KEY.get(str(ten_god(dm, stem)))
    return TEN_GOD_GROUP[tg].value if tg else None


def _group_percents(
    pillars: FourPillarsResult, luck_pairs: list[tuple[Stem, Branch]]
) -> dict[str, float]:
    """십성군 분포율(%) — 표시 분포 가중(ten_god_distribution의 dist 레이어)과 동일
    방식에 운 글자(천간 10·지지 15×지장간 비율)를 합산해 재정규화한다."""
    dm = Stem(pillars.day.stem)
    acc = {g: 0.0 for g in _GROUPS}

    def _add(stem: Stem, weight: float) -> None:
        g = _group_key(dm, stem)
        if g is not None:
            acc[g] += weight

    for pos, p in _iter_pillars(pillars):
        if pos != "day":  # 십성 분포는 일간(기준점) 제외
            _add(Stem(p.stem), float(DIST_STEM_WEIGHT[pos]))
    for pos, p in _iter_pillars(pillars):
        for hstem, _kind, ratio in hidden_stems_for(Branch(p.branch)):
            _add(hstem, DIST_BRANCH_WEIGHT[pos] * ratio)
    for stem, branch in luck_pairs:
        _add(stem, _LUCK_STEM_WEIGHT)
        for hstem, _kind, ratio in hidden_stems_for(branch):
            _add(hstem, _LUCK_BRANCH_WEIGHT * ratio)

    total = sum(acc.values())
    if total <= 0:
        return {g: 0.0 for g in _GROUPS}
    return {g: round(v / total * 100, 2) for g, v in acc.items()}


def _current_luck(lc: LuckCycles | None) -> tuple[DaewoonItem | None, LuckPillar | None]:
    """현재 대운·세운 기둥(sinsal_modifier._current_luck 관행)."""
    if lc is None:
        return None, None
    daewoon = None
    idx = lc.current_daewoon_index
    if idx is not None and 0 <= idx < len(lc.daewoon_table):
        daewoon = lc.daewoon_table[idx]
    sewoon = next((p for p in lc.yearly_luck if p.label == str(lc.current_year)), None)
    return daewoon, sewoon


def _luck_relation_kind(head: str) -> str | None:
    """운 relations_to_chart 유형('충'/'무례지형' 등) → 충/형/파/해 정규화."""
    for kind in ("충", "파", "해", "형"):
        if kind in head:
            return kind
    return None


def build_direction_facts(result: ManseV2Result) -> DirectionFacts:
    """ManseV2Result → DirectionFacts. 누락 계층은 빈 값(조건 불일치)으로 둔다."""
    pillars = result.pillars
    if pillars is None:  # 원국 없이는 판정 불가 — 빈 facts(제안 없음)
        return DirectionFacts()
    dm = Stem(pillars.day.stem)
    daewoon, sewoon = _current_luck(result.luck_cycles)
    luck_pairs = [
        (Stem(item.stem), Branch(item.branch)) for item in (daewoon, sewoon) if item is not None
    ]

    # ── 존재/작동: 원국(천간 투출·지지 본기=작동, 중기·여기=존재) + 운 유입=작동 ──
    present: set[str] = set()
    active: set[str] = set()

    def _mark(stem: Stem, is_active: bool) -> None:
        roman = _roman(str(ten_god(dm, stem)))
        if roman is None:
            return
        present.add(roman)
        if is_active:
            active.add(roman)

    for pos, p in _iter_pillars(pillars):
        if pos != "day":
            _mark(Stem(p.stem), is_active=True)
    for _pos, p in _iter_pillars(pillars):
        for hstem, hkind, _ratio in hidden_stems_for(Branch(p.branch)):
            _mark(hstem, is_active=hkind.value == "main")
    for stem, branch in luck_pairs:
        _mark(stem, is_active=True)
        for hstem, hkind, _ratio in hidden_stems_for(branch):
            _mark(hstem, is_active=hkind.value == "main")

    # ── 군 상태: 원국/합산 분포율 + 운 유입(천간·지지 본기 기준) ──
    natal_pct = _group_percents(pillars, [])
    combined_pct = _group_percents(pillars, luck_pairs)
    inflow: set[str] = set()
    for stem, branch in luck_pairs:
        for g in (_group_key(dm, stem), _group_key(dm, main_hidden_stem(branch))):
            if g is not None:
                inflow.add(g)

    group_states: dict[str, list[GroupStateValue]] = {}
    for g in _GROUPS:
        states: list[GroupStateValue] = []
        if natal_pct[g] >= EXCESS_PCT:
            states.append("natal_excess")
            if g in inflow:
                states.append("excess_intensified")
        elif combined_pct[g] >= EXCESS_PCT:
            states.append("luck_excess_onset")
        if natal_pct[g] < DEFICIENT_PCT:
            states.append("natal_deficient")
            states.append("luck_replenished" if g in inflow else "deficient_persistent")
        if g in inflow:
            states.append("luck_inflow")
        group_states[g] = states

    # ── 용신 역할: 정적 역할(역할 슬러그→오행)을 오행→역할로 뒤집어 군·십성 키로 전개 ──
    yongsin_roles: dict[str, str] = {}
    canonical = result.yongsin_analysis.canonical_roles if result.yongsin_analysis else {}
    element_role = {
        element: _ROLE_SLUG_KO[slug]
        for slug, element in canonical.items()
        if slug in _ROLE_SLUG_KO and element
    }
    if element_role:
        for gkey, element in group_elements(STEM_ELEMENT[dm]).items():
            group = "authority" if gkey == "officer" else gkey
            role = element_role.get(str(element))
            if role:
                yongsin_roles[group] = role
                for roman in _GROUP_TEN_GODS[group]:
                    yongsin_roles[roman] = role

    # ── 충파: 원국 interactions(영문 enum) + 현재 운 relations_to_chart(한글) ──
    conflicts: dict[str, set[str]] = {g: set() for g in _GROUPS}

    def _hit(char: str, kind: str) -> None:
        try:
            branch = Branch(char)
        except ValueError:
            return  # 천간 관여 관계(천간합 등)는 대상 아님
        g = _group_key(dm, main_hidden_stem(branch))
        if g is not None:
            conflicts[g].add(kind)

    if result.structure_analysis:
        for it in result.structure_analysis.interactions:
            kind = _RELATION_KIND_KO.get(it.relation_type)
            if kind is None:
                continue
            for member in it.members:
                _hit(member, kind)
    for item in (daewoon, sewoon):
        if item is None:
            continue
        for rel in item.relations_to_chart:
            head, _, tail = rel.partition(":")
            kind = _luck_relation_kind(head)
            if kind is None or not tail:
                continue
            for char in tail.split("-"):
                _hit(char, kind)

    strength_band = ""
    if result.force_analysis and result.force_analysis.strength:
        strength_band = result.force_analysis.strength.band

    return DirectionFacts(
        group_states=group_states,
        ten_god_present=sorted(present),
        ten_god_active=sorted(active),
        yongsin_roles=yongsin_roles,
        strength_band=strength_band,
        pattern_ids=[p.pattern_id for p in detect_structure_patterns(result)],
        group_conflicts={g: sorted(v) for g, v in conflicts.items() if v},
    )


# ── 평가 (순수 함수) ─────────────────────────────────────────────────


def _tg_status_match(tg: str, status: str, facts: DirectionFacts) -> bool:
    """십성 1개의 상태 판정."""
    present = tg in facts.ten_god_present
    active = tg in facts.ten_god_active
    if status == "present":
        return present
    if status == "absent":
        return not present
    if status == "active":
        return active
    if status == "inactive":
        return present and not active
    return not active  # not_active


def _match_condition(cond: SuggestionCondition, facts: DirectionFacts) -> bool:
    """조건 1건 매칭 — kind별 사실 대조. 미산정 사실은 불일치 처리."""
    if cond.kind == "group_state":
        states = facts.group_states.get(cond.group or "", [])
        return any(s in states for s in cond.states)
    if cond.kind == "ten_god_status":
        if cond.status is None:  # 스키마 검증상 도달 불가 — 방어
            return False
        results = (_tg_status_match(t, cond.status, facts) for t in cond.ten_gods)
        return all(results) if cond.match == "all" else any(results)
    if cond.kind == "yongsin_role":
        role = facts.yongsin_roles.get(cond.target or "")
        return role is not None and role in cond.roles
    if cond.kind == "strength_band":
        return facts.strength_band in cond.bands
    if cond.kind == "pattern":
        return any(pid in facts.pattern_ids for pid in cond.pattern_ids)
    # conflict
    kinds = facts.group_conflicts.get(cond.group or "", [])
    return any(k in kinds for k in cond.conflict_kinds)


def _condition_evidence(cond: SuggestionCondition) -> str:
    """조건의 근거 경로 라벨(LLM 근거·디버깅용, 판정에는 미사용)."""
    if cond.kind == "group_state":
        return f"군상태:{cond.group}∈{'/'.join(cond.states)}"
    if cond.kind == "ten_god_status":
        return f"십성:{'/'.join(cond.ten_gods)}={cond.status}"
    if cond.kind == "yongsin_role":
        return f"용신역할:{cond.target}∈{'/'.join(cond.roles)}"
    if cond.kind == "strength_band":
        return f"신강약:{'/'.join(cond.bands)}"
    if cond.kind == "pattern":
        return f"패턴:{'/'.join(cond.pattern_ids)}"
    return f"충파:{cond.group}∈{'/'.join(cond.conflict_kinds)}"


def _output_group_state(rule: DirectionRule, facts: DirectionFacts) -> GroupStateValue:
    """출력용 대표 상태 — 성립 상태 중 가장 구체적인 것."""
    states = facts.group_states.get(rule.group, [])
    for state in _STATE_PRIORITY:
        if state in states:
            return state
    return "luck_inflow"  # 방어적 기본값(트리거 성립 시 도달하지 않음)


def evaluate_direction_suggestions(
    facts: DirectionFacts, dictionary: DirectionSuggestionDict | None = None
) -> list[DirectionSuggestion]:
    """사실 집합을 사전 룰에 대조해 제안 목록을 판정한다(순수 함수).

    trigger(AND) 성립 + 채널 1개 이상 성립 → 제안. guard 매칭 시 caution 반전,
    support 매칭 수로 strength 가산. 결과는 strength 내림차순(동률 시 id 순).
    """
    d = dictionary or load_direction_suggestions()
    out: list[DirectionSuggestion] = []
    for rule in d.rules:
        if not all(_match_condition(c, facts) for c in rule.trigger):
            continue
        matched = [
            ch for ch in rule.channels if all(_match_condition(c, facts) for c in ch.conditions)
        ]
        if not matched:
            continue
        primary = matched[0]  # 사전 순서 = 우선순위
        guards_hit = [
            g for g in rule.guards if all(_match_condition(c, facts) for c in g.conditions)
        ]
        supports_hit = [s for s in rule.supports if _match_condition(s.condition, facts)]
        mode = "caution" if guards_hit else "recommend"
        headline = (
            rule.caution_headline
            if guards_hit and rule.caution_headline
            else primary.direction.headline
        )
        evidence = [_condition_evidence(c) for c in rule.trigger]
        evidence.append(f"채널:{primary.channel_id}")
        evidence.extend(_condition_evidence(c) for c in primary.conditions)
        evidence.extend(f"대안채널:{ch.channel_id}" for ch in matched[1:])
        out.append(
            DirectionSuggestion(
                suggestion_id=rule.suggestion_id,
                name_ko=rule.name_ko,
                group=rule.group,
                group_state=_output_group_state(rule, facts),
                mode=mode,
                strength=min(
                    1.0, round(_STRENGTH_BASE + _STRENGTH_PER_SUPPORT * len(supports_hit), 2)
                ),
                channel_id=primary.channel_id,
                headline=headline,
                actions=list(primary.direction.actions),
                avoid=list(primary.direction.avoid),
                reality_note=rule.reality_note,
                cautions=[g.note for g in guards_hit],
                matched_guards=[g.guard_id for g in guards_hit],
                matched_supports=[s.note for s in supports_hit if s.note],
                evidence=evidence,
                forbidden_framings=list(rule.forbidden_framings),
                llm_tag=rule.llm_tag,
            )
        )
    out.sort(key=lambda s: (-s.strength, s.suggestion_id))
    return out


def detect_direction_suggestions(result: ManseV2Result) -> list[DirectionSuggestion]:
    """편의 래퍼 — 결과 객체에서 facts를 조립해 제안을 판정한다."""
    return evaluate_direction_suggestions(build_direction_facts(result))


# ── LLM 노출 선별·직렬화 (Phase C, docs/15 §6) ───────────────────────────

# LLM 노출 상한 — 토큰 가드(docs/09 8장) 하에서 블록이 잘리지 않도록 소수 정예.
MAX_LLM_SUGGESTIONS = 2
# 질문/섹션 도메인 → 우선 십성군. 도메인 일치 제안을 앞세우는 소프트 필터일 뿐
# 다른 군 제안을 배제하지 않는다(능동 제안은 범용 레이어 — 2026-07-09 사용자 확인).
_DOMAIN_PRIORITY_GROUPS: dict[str, tuple[str, ...]] = {
    "career": ("authority", "output"),
    "wealth": ("wealth", "peer"),
    "education": ("resource", "output"),
    "relationship": ("peer",),
    "health": ("resource",),
}

DIRECTION_SUGGESTION_INSTRUCTION = (
    "[제안 방향] 블록은 엔진이 원국·운 조합에서 판정한 참고 재료다. 질문·주제와 관련될 때 "
    "본문 흐름 안에 '~해보는 것도 고려해볼 만하다' 수준의 방향 제안 1~2문장으로 자연스럽게 "
    "녹여라. 답을 맺는 별도 문단이나 되묻는 질문으로 만들지 마라 — 마무리는 시스템 지시의 "
    "마지막 항목 한 곳에서만 한다. "
    "단정·강요·확정 표현 금지, '주의' 모드는 권장보다 주의를 먼저 말하고, 각 항목의 표현 금지 "
    "목록은 절대 쓰지 말 것. 질문과 무관하면 블록 전체를 생략하라."
)


def select_direction_suggestions(
    suggestions: list[DirectionSuggestion],
    domains: list[str] | None = None,
    max_count: int = MAX_LLM_SUGGESTIONS,
) -> list[DirectionSuggestion]:
    """LLM 노출용 상위 N 선별 — 도메인 일치 군 우선, 이후 strength·id 순(결정적)."""
    priority: set[str] = set()
    for d in domains or []:
        priority.update(_DOMAIN_PRIORITY_GROUPS.get(d, ()))
    ranked = sorted(
        suggestions,
        key=lambda s: (0 if s.group in priority else 1, -s.strength, s.suggestion_id),
    )
    return ranked[:max_count]


def format_direction_suggestion_lines(suggestions: list[DirectionSuggestion]) -> list[str]:
    """`[제안 방향]` 블록 직렬화 — 빈 목록이면 빈 리스트(헤더·토큰 낭비 없음).

    chat(serialize_llm_input 동적 suffix)과 report(build_section_context)가 공용한다.
    """
    if not suggestions:
        return []
    lines = ["", "[제안 방향 — 엔진 판정 참고 재료('고려' 수준 서술 전용, 단정 금지)]"]
    for s in suggestions:
        mode_ko = "권장" if s.mode == "recommend" else "주의"
        lines.append(f"- ({mode_ko}) {s.name_ko}: {s.headline}")
        if s.reality_note:
            lines.append(f"  전제: {s.reality_note}")
        if s.mode == "caution":
            lines.extend(f"  주의: {c}" for c in s.cautions[:2])
        lines.append("  해볼 만한 것: " + " · ".join(s.actions[:3]))
        if s.avoid:
            lines.append("  피하는 게 좋은 것: " + " · ".join(s.avoid[:3]))
        if s.forbidden_framings:
            lines.append("  표현 금지: " + " / ".join(s.forbidden_framings))
    return lines
