"""Event Scoring Engine (v2.2 Phase 2 T2.3·T2.4, docs/02 E2).

특정 시점(대운/세운/월운/일운)에 어떤 이벤트가 발생할 가능성이 있는지 점수화한다.
점수 산출 규칙(docs/02): ① 관계 사전 base_score → ② favorability_rules 보정(용신 +,
기신 → polarity 변경 + 감점/강제성) → ③ 동일 이벤트 복수 신호 weight 합산 후 0~100
클램프 → ④ 계층 필터(세운은 score≥70 또는 Top5만 다음 단계로).

대운 교운기 신호는 **교운일 중심, 첨도를 높인 정규분포형 영향도**로 가중한다
(사용자 실측 피드백 2026-06-11): w = exp(-(|Δ일수|/scale)^beta), beta=1(라플라스형,
표준 정규보다 뾰족)·scale=365일 초안 — 실테스트로 조정.

모든 가중치·매핑은 reviewed:false 사전 초안에 기반하므로 점수 절대값보다 **상대
순위**를 신뢰한다(docs/07 리스크 1). LLM은 이 점수를 계산하지 않는다(절대 원칙 1).
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

from saju_shared_types.constants import BRANCH_ELEMENT, STEM_ELEMENT
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.events import (
    Confidence,
    EventCandidate,
    EventKey,
    EventPolarity,
    EventType,
    Signal,
)
from saju_shared_types.ganji_calendar import GanjiLevel, RelationHit, RelationType
from saju_shared_types.luck import DaewoonItem, LuckPillar
from saju_shared_types.manse_result import ManseV2Result

from .dictionaries import (
    EventMappingFile,
    EventMappingItem,
    FavorabilityRule,
    FavorabilityRulesFile,
    RelationItem,
    RelationsFile,
    TaxonomyFile,
    TenGodEventsFile,
)
from .ganji_calendar import relation_hits

# ── 교운기 영향도 모델 (사용자 실측: 교운일 중심 뾰족한 분포가 유효) ──
DAEWOON_TRANSITION_BETA = 1.0  # 일반화 정규분포 지수 — 1.0=라플라스형(첨도↑)
DAEWOON_TRANSITION_SCALE_DAYS = 365.0  # 영향 반경 스케일(일)
DAEWOON_TRANSITION_MIN_WEIGHT = 0.05  # 이 미만이면 교운 신호 미적용

# 계층 필터(docs/02): 세운은 score>=70 또는 상위 5건만 다음 단계로.
YEAR_SCORE_THRESHOLD = 70
YEAR_TOP_N = 5

# RelationHit 타입 → 사전 relations.json type.
_HIT_TO_DICT_TYPE: dict[RelationType, str] = {
    RelationType.STEM_COMBINATION: "stem_combination",
    RelationType.BRANCH_CLASH: "branch_clash",
    RelationType.SIX_COMBINATION: "six_combination",
    RelationType.THREE_HARMONY_CONTRIB: "three_harmony",
    RelationType.DIRECTIONAL_CONTRIB: "directional",
    RelationType.BRANCH_BREAK: "branch_break",
    RelationType.HARM: "harm",
    RelationType.PUNISHMENT_TRIPLE: "punishment_triple",
    RelationType.PUNISHMENT_MUTUAL: "punishment_mutual",
    RelationType.SELF_PUNISHMENT: "self_punishment",
    RelationType.VOID_FILL: "void",
    RelationType.VOID_TRIGGER_CLASH: "void",
    RelationType.VOID_RELEASE_COMBINE: "void",
}

_LEVEL_KO = {
    GanjiLevel.DAEWOON: "대운", GanjiLevel.YEAR: "세운",
    GanjiLevel.MONTH: "월운", GanjiLevel.DAY: "일운",
}

# 판정(용기신) 한글 → 그래프 노드 ID (한신은 그래프 노드 없음 — docs/04 NodeType).
_FAV_NODE_ID = {"용신": "yongsin", "희신": "huisin", "기신": "gisin", "구신": "gusin"}


# 극성 종합 — 부정 신호가 긍정의 이 비율 이상이면 단정 대신 '조건부 변동'으로 본다.
_MIXED_POLARITY_RATIO = 0.5
# 한 시점에 충·형·파·원진·공망이 이 개수 이상 얽히면 '복잡·불안정'으로 본다(계약 등 불리).
_INSTABILITY_HIT_THRESHOLD = 3
_VOLATILE_KEYWORDS = ("충", "형", "파", "원진", "공망")


# 운 천간/지지 오행이 흉신(구신·기신)일 때 부정 쪽에 더하는 가중(천간이 더 드러남).
_LUCK_STEM_BAD_WEIGHT = 0.4
_LUCK_BRANCH_BAD_WEIGHT = 0.2
_BAD_ROLES = ("구신", "기신")


def _aggregate_polarity(
    group: list[_Contribution],
    top: _Contribution,
    luck_role: tuple[str | None, str | None] = (None, None),
) -> EventPolarity:
    """후보 1건의 극성을 신호 구성 + 운 간지 오행 용기신으로 종합(단일 최강 신호 단정 대신).

    - 부정(강제·비자발) 신호 + 운 천간/지지 오행이 흉신(구신·기신)이면 부정 쪽에 가중.
    - 부정이 긍정의 일정 비율 이상이면 → conditional(혼재·변동).
    - 충·형·공망 등 변동 신호가 여러 개 얽히면 → conditional(불안정, 안정적 결실 불리).
    - 부정이 긍정보다 우세하면 → negative_or_forced.
    """
    pos = sum(c.weight for c in group if c.polarity is EventPolarity.POSITIVE)
    neg = sum(c.weight for c in group if c.polarity is EventPolarity.NEGATIVE_OR_FORCED)
    stem_role, branch_role = luck_role
    if stem_role in _BAD_ROLES:
        neg += _LUCK_STEM_BAD_WEIGHT  # 운 천간 오행이 흉신 — 부담 요소
    if branch_role in _BAD_ROLES:
        neg += _LUCK_BRANCH_BAD_WEIGHT
    volatile = sum(
        1 for c in group
        if any(k in (c.signal.effect or c.signal.name) for k in _VOLATILE_KEYWORDS)
    )
    if neg > pos and neg > 0:
        return EventPolarity.NEGATIVE_OR_FORCED
    if neg > 0 and neg >= pos * _MIXED_POLARITY_RATIO:
        return EventPolarity.CONDITIONAL  # 긍·부정 혼재 — 변동성 동반
    if volatile >= _INSTABILITY_HIT_THRESHOLD:
        return EventPolarity.CONDITIONAL  # 다중 충·형·공망 얽힘 — 불안정
    return top.polarity


# 운 위계 가중(대운>세운>월운>일운) — 같은 신호라도 상위 운이 이벤트 활성에 더 크게
# 기여한다(2026-06-12 사용자 확정). 교운기 신호는 대운 작용이므로 대운 위상으로 본다.
_LEVEL_WEIGHT = {
    GanjiLevel.DAEWOON: 1.0,
    GanjiLevel.YEAR: 0.85,
    GanjiLevel.MONTH: 0.6,
    GanjiLevel.DAY: 0.4,
}
# 위계 점수 상한 — 월운/일운 작용이 세운·대운을 넘지 못하게(대운>세운>월운>일운).
_LEVEL_CAP = {
    GanjiLevel.DAEWOON: 100,
    GanjiLevel.YEAR: 90,
    GanjiLevel.MONTH: 75,
    GanjiLevel.DAY: 55,
}
# 삼합/방합이 한신·중립일 때 사건 기여 감쇄 계수(범용 세력의 방향 결정력 약함).
_GENERIC_NEUTRAL_FACTOR = 0.4


def _level_weight(level: GanjiLevel, is_transition: bool = False) -> float:
    """위계 가중 — 교운기(대운 작용) 신호는 발생 계층과 무관히 대운 위상."""
    if is_transition:
        return _LEVEL_WEIGHT[GanjiLevel.DAEWOON]
    return _LEVEL_WEIGHT.get(level, 0.6)


def daewoon_transition_weight(
    target: date,
    jiao_dates: list[date],
    *,
    beta: float = DAEWOON_TRANSITION_BETA,
    scale_days: float = DAEWOON_TRANSITION_SCALE_DAYS,
) -> float:
    """교운일 중심의 첨도 높은 정규분포형 영향도(0~1).

    가장 가까운 교운일과의 일수 차 d에 대해 ``exp(-(d/scale)^beta)``.
    beta=2면 표준 정규형, beta<2면 더 뾰족(leptokurtic) — 기본 1.0.
    """
    if not jiao_dates:
        return 0.0
    nearest = min(abs((target - jd).days) for jd in jiao_dates)
    return math.exp(-((nearest / scale_days) ** beta))


def _transition_label(w: float) -> str:
    """교운 가중(0~1) → 근접도 라벨 — 교운일 중심 첨도 분포의 표면화(점수 포화 보완)."""
    if w >= 0.8:
        return "정점권(교운일 임박·직후)"
    if w >= 0.5:
        return "근접"
    return "영향권(완만)"


def _period_midpoint(level: GanjiLevel, label: str) -> date | None:
    """운 라벨의 대표 날짜(교운 거리 계산용). 대운 라벨은 대상 아님."""
    try:
        if level is GanjiLevel.YEAR:
            return date(int(label), 7, 1)
        if level is GanjiLevel.MONTH:
            y, m = label.split("-")
            return date(int(y), int(m), 15)
        if level is GanjiLevel.DAY:
            return date.fromisoformat(label)
    except ValueError:
        return None
    return None


class _Contribution:
    """이벤트 한 건에 대한 신호 1개의 기여(내부 집계용)."""

    def __init__(
        self, event: EventKey, weight: float, polarity: EventPolarity, signal: Signal,
        path_nodes: list[str], readable: list[str],
    ) -> None:
        self.event = event
        self.weight = weight
        self.polarity = polarity
        self.signal = signal
        self.path_nodes = path_nodes
        self.readable = readable


class EventScorer:
    """사전 기반 결정론 이벤트 스코어러 — 같은 입력이면 항상 같은 출력."""

    def __init__(self, dictionaries_dir: Path) -> None:
        """사전 원본을 로드해 조회 인덱스를 만든다."""
        self._relations = RelationsFile.model_validate(
            self._read(dictionaries_dir / "relations.json")
        )
        self._favorability = FavorabilityRulesFile.model_validate(
            self._read(dictionaries_dir / "favorability_rules.json")
        )
        taxonomy = TaxonomyFile.model_validate(
            self._read(dictionaries_dir / "events" / "taxonomy.json")
        )
        self._event_types: dict[EventKey, EventType] = {
            t.event_key: t.event_type for t in taxonomy.items
        }
        self._event_ko: dict[EventKey, str] = {t.event_key: t.ko for t in taxonomy.items}
        # 미발동 글자 기본 가감 — 십성별 대표 이벤트(2026-06-12 사용자 원칙).
        tge = TenGodEventsFile.model_validate(
            self._read(dictionaries_dir / "common" / "ten_god_events.json")
        )
        self._ten_god_event: dict[str, EventKey] = {
            i.ten_god: i.event for i in tge.items
        }
        self._mappings: list[EventMappingFile] = []
        for path in sorted((dictionaries_dir / "events").glob("*.json")):
            if path.name != "taxonomy.json":
                self._mappings.append(EventMappingFile.model_validate(self._read(path)))

        # (type, 참여글자 frozenset) → 항목. 패턴형은 type만으로 조회.
        self._pair_index: dict[tuple[str, frozenset[str]], RelationItem] = {}
        self._pattern_index: dict[str, RelationItem] = {}
        for item in self._relations.items:
            if item.participants:
                self._pair_index[(item.type, frozenset(item.participants))] = item
            else:
                self._pattern_index[item.type] = item

    @staticmethod
    def _read(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    # ── 공개 API ─────────────────────────────────────────────────

    def score(
        self, result: ManseV2Result, levels: set[GanjiLevel] | None = None
    ) -> list[EventCandidate]:
        """만세 결과의 운 전체를 스코어링해 이벤트 후보를 산출한다.

        Args:
            result: 만세력 엔진 결과(pillars·luck_cycles·yongsin final 필요).
            levels: 평가할 운 계층(None=전부).

        Returns:
            (period, event)별로 합산·클램프된 EventCandidate 목록(점수 내림차순).
        """
        if result.pillars is None or result.luck_cycles is None:
            return []
        wanted = levels or set(GanjiLevel)
        fav_map = favorability_map(result)
        natal_unseongs = frozenset(
            u for u in (
                result.pillars.month.twelve_unseong, result.pillars.day.twelve_unseong,
            ) if u
        )
        natal_void = frozenset(result.pillars.gongmang_branches or [])
        dw_branch_by_year: dict[int, str] = {}
        for dwi in result.luck_cycles.daewoon_table:
            for y in range(dwi.approx_start_date.year, dwi.approx_end_date.year):
                dw_branch_by_year[y] = dwi.ganji[1] if len(dwi.ganji) == 2 else ""
        strong_groups = _strong_ten_god_groups(result)
        jiao = [
            date.fromisoformat(d)
            for d in result.luck_cycles.trace.get("exact_jiao_un_dates", [])
        ]

        contributions: list[tuple[str, GanjiLevel, _Contribution]] = []
        luck_role_by_label: dict[str, tuple[str | None, str | None]] = {}
        for level, label, stem, branch, pillar in self._iter_luck(result, wanted):
            hits = relation_hits(
                level, stem, branch,
                pillar.relations_to_chart, pillar.gongmang_activation, result.pillars,
            )
            period_node = f"{level}_{label}_{stem}{branch}"
            ctx = _PeriodContext(
                level=level, label=label, stem=stem, branch=branch,
                period_node=period_node, hits=hits, pillar=pillar,
                fav_map=fav_map, jiao_dates=jiao,
                natal_unseongs=natal_unseongs, strong_groups=strong_groups,
            )
            ctx.natal_void = natal_void
            if label[:4].isdigit():
                ctx.daewoon_branch = dw_branch_by_year.get(int(label[:4]), "")
            contributions += [(label, level, c) for c in self._relation_contributions(ctx)]
            contributions += [(label, level, c) for c in self._mapping_contributions(ctx)]
            contributions += [(label, level, c) for c in self._baseline_contributions(ctx)]
            contributions += [(label, level, c) for c in self._instability_contributions(ctx)]
            # 운 천간/지지 오행의 용기신 역할(구신·기신이면 그 시기 부담 요소).
            luck_role_by_label[label] = (
                fav_map.get(str(STEM_ELEMENT[Stem(stem)])),
                fav_map.get(str(BRANCH_ELEMENT[Branch(branch)])),
            )

        return self._aggregate(contributions, luck_role_by_label)

    # ── 운 순회 ──────────────────────────────────────────────────

    def _iter_luck(
        self, result: ManseV2Result, wanted: set[GanjiLevel]
    ):
        """운 계층별 (level, label, stem, branch, LuckPillar류) 순회."""
        lc = result.luck_cycles
        assert lc is not None
        if GanjiLevel.DAEWOON in wanted:
            for d in lc.daewoon_table:
                label = f"{d.approx_start_date.year}~{d.approx_end_date.year}"
                yield GanjiLevel.DAEWOON, label, d.stem, d.branch, _daewoon_as_pillar(d)
        for level, pillars in (
            (GanjiLevel.YEAR, lc.yearly_luck),
            (GanjiLevel.MONTH, lc.monthly_luck),
            (GanjiLevel.DAY, lc.daily_luck),
        ):
            if level in wanted:
                for p in pillars:
                    yield level, p.label, p.stem, p.branch, p

    # ── 신호 기여 산출 ────────────────────────────────────────────

    def _relation_contributions(self, ctx: _PeriodContext) -> list[_Contribution]:
        """합충형파해/공망 적중 → relations.json eventDomains 기반 기여."""
        out: list[_Contribution] = []
        for hit in ctx.hits:
            item = self._match_relation(hit)
            if item is None or not item.event_domains:
                continue
            # 길흉은 유입(운) 글자의 오행으로 판정한다(docs/04 예시: 甲木 기신 → 부담).
            # 합화 결과 오행은 성립 시 전환 가능성 단서로만 부기한다(합화 판정은 Phase 2.5).
            is_stem = hit.type is RelationType.STEM_COMBINATION
            if is_stem:
                ctx.stem_anchored = True
            else:
                ctx.branch_anchored = True
            incoming_el = str(
                STEM_ELEMENT[Stem(ctx.stem)] if is_stem else BRANCH_ELEMENT[Branch(ctx.branch)]
            )
            fav = ctx.fav_map.get(incoming_el)
            rule = self._find_favorability_rule(fav, ten_god=None)
            modifier = rule.effect.score_modifier if rule else 0.0
            polarity = rule.effect.polarity if rule else EventPolarity.NEUTRAL
            signal = Signal(
                type=str(hit.type),
                name=item.id.removeprefix("rel_"),
                effect=f"{item.name}"
                + (f" → {incoming_el} {fav}" if fav else ""),
                weight=round((item.base_score + modifier) * 100, 1),
            )
            fav_part = [f"{incoming_el} {fav}"] if fav else []
            result_fav = (
                ctx.fav_map.get(item.result_element) if item.result_element else None
            )
            if item.result_element and result_fav and result_fav != fav:
                fav_part.append(
                    f"합화 {item.result_element} 성립 시 {result_fav} 전환 가능"
                )
            # 범용 세력 신호(삼합/방합)가 한신·중립이면 방향 결정력이 약하므로 감쇄.
            generic = 1.0
            if hit.type in (
                RelationType.THREE_HARMONY_CONTRIB, RelationType.DIRECTIONAL_CONTRIB,
            ) and fav in (None, "한신"):
                generic = _GENERIC_NEUTRAL_FACTOR
            for ev in item.event_domains:
                out.append(_Contribution(
                    event=ev,
                    weight=max(item.base_score + modifier, 0.0)
                    * _level_weight(ctx.level) * generic,
                    polarity=polarity,
                    signal=signal,
                    path_nodes=[
                        ctx.period_node,
                        f"stem_{ctx.stem}" if is_stem else f"branch_{ctx.branch}",
                        item.id,
                        *([_FAV_NODE_ID[fav]] if fav in _FAV_NODE_ID else []),
                        f"event_{ev}",
                    ],
                    readable=[
                        f"{ctx.stem}{ctx.branch} {_LEVEL_KO[ctx.level]}",
                        f"{ctx.stem if is_stem else ctx.branch} 유입",
                        item.name, *fav_part,
                        self._event_ko.get(ev, str(ev)),
                    ],
                ))
        return out

    def _instability_contributions(self, ctx: _PeriodContext) -> list[_Contribution]:
        """중복 충 불안정 감점(2026-06-12 계사월 케이스 일반화 — G1).

        같은 운 글자가 원국 복수 글자와 동일 충을 만들면(예: 巳亥沖 ×2 — 월지·일지 亥)
        이동·변동 발생 신호는 커지지만 심리·결정이 흔들려 계약 유지력은 떨어진다.
        발생 점수(career/relocation)는 유지하고 결실류(contract/document)만 감점 —
        '실행월이 아니라 검토월' 판단의 엔진 표현.
        """
        clash_count = sum(
            1 for h in ctx.hits if h.type is RelationType.BRANCH_CLASH
        )
        if clash_count < 2:
            return []
        signal = Signal(
            type="repeated_clash",
            name=f"repeated_clash_{ctx.branch}",
            effect=(
                f"중복 충 — {ctx.branch}이(가) 원국 {clash_count}글자와 같은 충: "
                "변동 과다·결정 불안정(이동수는 강하나 계약 유지력 약화)"
            ),
            weight=-15.0,
        )
        out: list[_Contribution] = []
        for ev, w in ((EventKey.CONTRACT, -0.15), (EventKey.DOCUMENT, -0.1)):
            out.append(_Contribution(
                event=ev,
                weight=w * _level_weight(ctx.level),
                polarity=EventPolarity.NEUTRAL,
                signal=signal,
                path_nodes=[ctx.period_node, f"branch_{ctx.branch}", f"event_{ev}"],
                readable=[
                    f"{ctx.stem}{ctx.branch} {_LEVEL_KO[ctx.level]}",
                    f"{ctx.branch} 중복 충(불안정)",
                    self._event_ko.get(ev, str(ev)),
                ],
            ))
        return out

    def _baseline_contributions(self, ctx: _PeriodContext) -> list[_Contribution]:
        """미발동 글자의 용기신 기본 가감(2026-06-12 사용자 원칙).

        천간/지지 글자가 합충형파해 등 어떤 관계·룰에도 기여하지 않았으면, 그 글자의
        용희기구한 역할에 따라 십성 대표 이벤트에 가감한다. 가중은 favorability_rules
        modifier 재사용(±0.1~0.25) — 발동 신호(0.6~0.8)보다 항상 작다. 한신·매핑 없는
        십성은 건너뛴다. 리스크형 이벤트는 사전에서 제외(방향 반대 — 추후 확장).
        """
        out: list[_Contribution] = []
        targets = []
        if not ctx.stem_anchored:
            targets.append((ctx.stem, str(STEM_ELEMENT[Stem(ctx.stem)]),
                            ctx.pillar.stem_ten_god, "천간"))
        if not ctx.branch_anchored:
            targets.append((ctx.branch, str(BRANCH_ELEMENT[Branch(ctx.branch)]),
                            ctx.pillar.branch_ten_god, "지지"))
        for char, el, ten_god, pos_ko in targets:
            fav = ctx.fav_map.get(el)
            event = self._ten_god_event.get(ten_god or "")
            if fav is None or fav == "한신" or event is None:
                continue
            rule = self._find_favorability_rule(fav, ten_god=None)
            modifier = rule.effect.score_modifier if rule else 0.0
            if modifier == 0.0:
                continue
            polarity = (
                EventPolarity.POSITIVE if modifier > 0 else EventPolarity.NEUTRAL
            )
            signal = Signal(
                type="baseline_favorability",
                name=f"baseline_{char}",
                effect=(
                    f"미발동 글자 기본 {'가점' if modifier > 0 else '감점'} — "
                    f"{pos_ko} {char}({el} {fav}) {ten_god}: 관계 미성립이어도 "
                    f"{fav} 기운 자체의 영향"
                ),
                weight=round(modifier * 100, 1),
            )
            out.append(_Contribution(
                event=event,
                weight=modifier * _level_weight(ctx.level),
                polarity=polarity,
                signal=signal,
                path_nodes=[
                    ctx.period_node,
                    f"stem_{char}" if pos_ko == "천간" else f"branch_{char}",
                    *([_FAV_NODE_ID[fav]] if fav in _FAV_NODE_ID else []),
                    f"event_{event}",
                ],
                readable=[
                    f"{ctx.stem}{ctx.branch} {_LEVEL_KO[ctx.level]}",
                    f"{char} 유입(미발동·{el} {fav})",
                    self._event_ko.get(event, str(event)),
                ],
            ))
        return out

    def _mapping_contributions(self, ctx: _PeriodContext) -> list[_Contribution]:
        """events/<domain>.json 신호 매핑 기반 기여(십성·관계·용기신·신살·교운)."""
        out: list[_Contribution] = []
        hit_types = {self._hit_dict_type(h) for h in ctx.hits}
        stem_ten_god = ctx.pillar.stem_ten_god
        branch_ten_god = ctx.pillar.branch_ten_god
        stem_el = str(STEM_ELEMENT[Stem(ctx.stem)])
        branch_el = str(BRANCH_ELEMENT[Branch(ctx.branch)])
        sinsal_names = {s.name for s in ctx.pillar.luck_sinsal}

        for mapping in self._mappings:
            for idx, item in enumerate(mapping.items):
                weight_scale = self._match_signal(
                    item, ctx, hit_types, stem_ten_god, branch_ten_god,
                    stem_el, branch_el, sinsal_names,
                )
                if weight_scale is None:
                    continue
                rule_node = f"rule_{mapping.domain}_{idx:02d}"
                sig = item.signal
                strongest = max(c.score for c in item.event_candidates)
                effect = item.note or rule_node
                # 교운 신호는 근접도 라벨 부기 — 점수가 상한(cap)에 포화돼도 교운일
                # 가중 차이(첨도 분포)가 LLM 입력에서 변별되게(2026-06-12 지적).
                if sig.daewoon_transition:
                    effect += f" (교운 근접도: {_transition_label(weight_scale)})"
                signal = Signal(
                    type="rule_match",
                    name=rule_node,
                    effect=effect,
                    weight=round(strongest * weight_scale * 100, 1),
                )
                # 미발동 판정용 — 이 룰이 천간/지지 글자 조건을 썼는지 기록.
                if sig.ten_god is not None or sig.stem_favorability is not None:
                    ctx.stem_anchored = True
                if (
                    sig.branch_ten_god is not None or sig.shinsal is not None
                    or sig.unseong is not None
                ):
                    ctx.branch_anchored = True
                lw = _level_weight(ctx.level, is_transition=bool(sig.daewoon_transition))
                for cand in item.event_candidates:
                    out.append(_Contribution(
                        event=cand.event,
                        weight=cand.score * weight_scale * lw,
                        polarity=cand.polarity,
                        signal=signal,
                        path_nodes=[
                            ctx.period_node,
                            *( [f"tengod_{sig.ten_god}"] if sig.ten_god else [] ),
                            *( [f"tengod_{sig.branch_ten_god}"]
                               if sig.branch_ten_god else [] ),
                            rule_node, f"event_{cand.event}",
                        ],
                        readable=[
                            f"{ctx.stem}{ctx.branch} {_LEVEL_KO[ctx.level]}",
                            *( [f"{ctx.stem}은 일간에게 {sig.ten_god}"] if sig.ten_god else [] ),
                            *( [f"{ctx.branch}은 일간에게 {sig.branch_ten_god}"]
                               if sig.branch_ten_god else [] ),
                            item.note or rule_node,
                            self._event_ko.get(cand.event, str(cand.event)),
                        ],
                    ))
        return out

    def _match_signal(
        self, item: EventMappingItem, ctx: _PeriodContext, hit_types: set[str],
        stem_ten_god: str, branch_ten_god: str,
        stem_el: str, branch_el: str, sinsal_names: set[str],
    ) -> float | None:
        """신호 조건 전부(AND) 일치 시 가중 배율(보통 1.0, 교운은 분포 가중)을 반환.

        branchTenGod(v2.2.1): 운 지지 본기 십성 조건 — 동반 신호 매트릭스의 지지 신호
        (예: 甲申월 申 상관 이동성, regression_2025_08).
        """
        sig = item.signal
        if sig.ten_god is not None and sig.ten_god != stem_ten_god:
            return None
        if sig.branch_ten_god is not None and sig.branch_ten_god != branch_ten_god:
            return None
        if sig.relation is not None and sig.relation not in hit_types:
            return None
        # relationAlso(감점 룰) — 두 관계가 같은 기간에 동시 성립해야 매칭(탐합망충 등).
        if sig.relation_also is not None and sig.relation_also not in hit_types:
            return None
        if sig.favorability is not None:
            subject_el = stem_el if sig.ten_god is not None else branch_el
            if ctx.fav_map.get(subject_el) != sig.favorability:
                return None
        if sig.shinsal is not None and sig.shinsal not in sinsal_names:
            return None
        # 대운 지지 공망 배경(G2) — 그 대운 하의 모든 기간에 결실 제약.
        if sig.daewoon_branch_void and (
            not ctx.daewoon_branch or ctx.daewoon_branch not in ctx.natal_void
        ):
            return None
        # 운 천간 오행의 용기신 역할 단독 조건 — '천간 구신 달=계약 불리'(사용자 지식).
        if (
            sig.stem_favorability is not None
            and ctx.fav_map.get(stem_el) != sig.stem_favorability
        ):
            return None
        # 십이운성 조건(2026-06-12 스펙) — modifier 전용, 가중은 사전에서 낮게 저작.
        if sig.unseong is not None and ctx.pillar.twelve_unseong != sig.unseong:
            return None
        if sig.natal_unseong is not None and sig.natal_unseong not in ctx.natal_unseongs:
            return None
        if (
            sig.ten_god_group_strong is not None
            and sig.ten_god_group_strong not in ctx.strong_groups
        ):
            return None
        # does_not_apply_when — 외부 강트리거(충·형 등) 동반 시 안정 감점 미적용.
        if sig.absent_relations and any(r in hit_types for r in sig.absent_relations):
            return None
        scale = 1.0
        if sig.daewoon_transition:
            midpoint = _period_midpoint(ctx.level, ctx.label)
            if midpoint is None:
                return None
            w = daewoon_transition_weight(midpoint, ctx.jiao_dates)
            if w < DAEWOON_TRANSITION_MIN_WEIGHT:
                return None
            scale = w
        return scale

    @staticmethod
    def _hit_dict_type(hit: RelationHit) -> str:
        return _HIT_TO_DICT_TYPE.get(hit.type, str(hit.type))

    def _match_relation(self, hit: RelationHit) -> RelationItem | None:
        """RelationHit → relations.json 항목 매칭."""
        dict_type = self._hit_dict_type(hit)
        if dict_type == "void":
            return self._pattern_index.get("void")
        luck_char = (
            hit.luck_ref.stem
            if hit.type is RelationType.STEM_COMBINATION
            else hit.luck_ref.branch
        )
        natal_chars = {
            (r.stem if hit.type is RelationType.STEM_COMBINATION else r.branch)
            for r in hit.natal_refs
        } - {None}
        # 쌍 관계: 운+원국 글자 조합으로 정확 조회.
        for natal in natal_chars or {luck_char}:
            key = (dict_type, frozenset({luck_char, natal}))
            if key in self._pair_index:
                return self._pair_index[key]
        # 3자 관계(삼합/방합/삼형): 운 글자가 participants에 포함된 항목.
        for (typ, members), item in self._pair_index.items():
            if typ == dict_type and luck_char in members:
                if hit.element is None or item.result_element == hit.element:
                    return item
        return None

    def _find_favorability_rule(
        self, favorability: str | None, ten_god: str | None
    ) -> FavorabilityRule | None:
        """조건에 맞는 보정 규칙 — 구체(십성 포함) 규칙 우선, 없으면 일반 규칙."""
        if favorability is None:
            return None
        specific = [
            r for r in self._favorability.items
            if r.condition.favorability == favorability and r.condition.ten_god == ten_god
        ]
        if ten_god is not None and specific:
            return specific[0]
        generic = [
            r for r in self._favorability.items
            if r.condition.favorability == favorability and r.condition.ten_god is None
        ]
        return generic[0] if generic else None

    # ── 집계 ────────────────────────────────────────────────────

    def _aggregate(
        self,
        contributions: list[tuple[str, GanjiLevel, _Contribution]],
        luck_role_by_label: dict[str, tuple[str | None, str | None]] | None = None,
    ) -> list[EventCandidate]:
        """(period, event)별 weight 합산 → 0~100 클램프 + 대표 polarity/근거."""
        grouped: dict[tuple[str, GanjiLevel, EventKey], list[_Contribution]] = {}
        for label, level, contrib in contributions:
            grouped.setdefault((label, level, contrib.event), []).append(contrib)

        out: list[EventCandidate] = []
        for (label, _level, event), group in grouped.items():
            total = sum(c.weight for c in group)
            score = max(0, min(_LEVEL_CAP.get(_level, 90), round(total * 100)))
            top = max(group, key=lambda c: c.weight)
            confidence = (
                Confidence.MEDIUM_HIGH if len(group) >= 3
                else Confidence.MEDIUM if len(group) == 2
                else Confidence.MEDIUM_LOW
            )
            out.append(EventCandidate(
                event_key=event,
                event_type=self._event_types.get(event, EventType.PROGRESS),
                period=label,
                score=score,
                raw_total=round(total, 4),
                confidence=confidence,
                # 단일 최강 신호가 아니라 긍·부정·변동 신호를 종합해 극성을 정한다
                # (희신 충이 강해도 공망·다중 충형이 얽히면 '조건부 변동'으로).
                polarity=_aggregate_polarity(
                    group, top, (luck_role_by_label or {}).get(label, (None, None)),
                ),
                signals=[c.signal for c in group],
                evidence_path=top.path_nodes,
            ))
        # 동점(점수 클램프) 시 raw 가중 합으로 우위를 가린다 — 범용 신호(삼합/방합 한신)
        # 감쇄·이사 특이 신호 강화가 정렬에 반영되게(regression_2025_08).
        return sorted(
            out,
            key=lambda c: (-c.score, -c.raw_total, -len(c.signals), c.period, str(c.event_key)),
        )

    # ── T2.4 readable path ───────────────────────────────────────

    def readable_path(self, candidate: EventCandidate) -> list[str]:
        """후보의 evidence_path 노드 ID를 사람용 한글 경로로 변환한다."""
        readable: list[str] = []
        for node in candidate.evidence_path:
            readable.append(_node_readable(node, self._event_ko))
        return readable


class _PeriodContext:
    """운 한 항목의 스코어링 문맥(내부 전달용)."""

    def __init__(
        self, *, level: GanjiLevel, label: str, stem: str, branch: str,
        period_node: str, hits: list[RelationHit], pillar: LuckPillar,
        fav_map: dict[str, str], jiao_dates: list[date],
        natal_unseongs: frozenset[str] = frozenset(),
        strong_groups: frozenset[str] = frozenset(),
    ) -> None:
        self.level = level
        self.label = label
        self.stem = stem
        self.branch = branch
        self.period_node = period_node
        self.hits = hits
        self.pillar = pillar
        self.fav_map = fav_map
        self.jiao_dates = jiao_dates
        # 십이운성 조건(2026-06-12 스펙) — 원국 월·일주 운성, 강한 십성군(groups>=30%).
        self.natal_unseongs = natal_unseongs
        self.strong_groups = strong_groups
        # 미발동(관계·룰 비기여) 판정 플래그 — 기여 산출 중 기록(2026-06-12 사용자 원칙).
        self.stem_anchored = False
        self.branch_anchored = False
        # 대운 배경·원국 공망(2026-06-12 계사월 케이스 일반화 — G2 대운 지지 공망 제약).
        self.daewoon_branch = ""
        self.natal_void: frozenset[str] = frozenset()


# 십성군(한글) → 엔진 force_analysis.ten_gods.groups 키.
_TEN_GOD_GROUP_KEY = {
    "인성": "resource", "비겁": "peer", "식상": "output",
    "재성": "wealth", "관성": "officer",
}
# 십성군 '강' 판정 임계(groups percent, 5군 균등 20 기준 1.5배).
_STRONG_GROUP_MIN = 30.0


def _strong_ten_god_groups(result: ManseV2Result) -> frozenset[str]:
    """세력이 강한 십성군(한글) 집합 — SignalSpec.tenGodGroupStrong 조건용."""
    fa = result.force_analysis
    if fa is None or fa.ten_gods is None:
        return frozenset()
    groups = fa.ten_gods.groups or {}
    return frozenset(
        ko for ko, key in _TEN_GOD_GROUP_KEY.items()
        if groups.get(key, 0.0) >= _STRONG_GROUP_MIN
    )


def favorability_map(result: ManseV2Result) -> dict[str, str]:
    """용신 분석 final → 오행(한자) → 역할(용신/희신/기신/구신/한신) 매핑."""
    if result.yongsin_analysis is None:
        return {}
    final = result.yongsin_analysis.final
    roles = (
        ("yongsin", "용신"), ("heesin", "희신"), ("gisin", "기신"),
        ("gusin", "구신"), ("hansin", "한신"),
    )
    out: dict[str, str] = {}
    for key, ko in roles:
        element = final.get(key)
        if isinstance(element, str) and element:
            out[element] = ko
    return out


def filter_year_candidates(candidates: list[EventCandidate]) -> list[EventCandidate]:
    """계층 필터(docs/02): 세운 후보는 score≥70 또는 연도 무관 Top5만 통과.

    월운/일운/대운 후보는 그대로 통과한다(월운 노출 제한은 오케스트레이터 담당).
    """
    years = [c for c in candidates if _is_year_period(c.period)]
    kept_ids = {id(c) for c in years if c.score >= YEAR_SCORE_THRESHOLD}
    kept_ids |= {id(c) for c in sorted(years, key=lambda c: -c.score)[:YEAR_TOP_N]}
    return [c for c in candidates if not _is_year_period(c.period) or id(c) in kept_ids]


def _is_year_period(period: str) -> bool:
    """'2026' 형태(세운 라벨)인지 판별."""
    return len(period) == 4 and period.isdigit()


def _daewoon_as_pillar(d: DaewoonItem) -> LuckPillar:
    """대운 항목을 스코어링 공용 형태(LuckPillar)로 투영."""
    return LuckPillar(
        label=d.ganji, period_type="daewoon", ganji=d.ganji,
        stem=d.stem, branch=d.branch,
        stem_ten_god=d.stem_ten_god, branch_ten_god=d.branch_ten_god,
        relations_to_chart=d.relations_to_chart,
        gongmang_activation=d.gongmang_activation,
        luck_sinsal=d.luck_sinsal,
    )


_FAV_NODE_KO = {"yongsin": "용신", "huisin": "희신", "gisin": "기신", "gusin": "구신"}


def _node_readable(node_id: str, event_ko: dict[EventKey, str]) -> str:
    """그래프/경로 노드 ID 한 개의 한글 표현."""
    if node_id.startswith("event_"):
        key = node_id.removeprefix("event_")
        try:
            return event_ko.get(EventKey(key), key)
        except ValueError:
            return key
    if node_id in _FAV_NODE_KO:
        return _FAV_NODE_KO[node_id]
    for level in GanjiLevel:  # 운 노드: '<level>_<label>_<ganji>' → '甲辰 세운(2024)'
        prefix = f"{level}_"
        if node_id.startswith(prefix):
            rest = node_id.removeprefix(prefix)
            label, _, ganji = rest.rpartition("_")
            return f"{ganji} {_LEVEL_KO[level]}({label})"
    for prefix in ("stem_", "branch_", "tengod_"):
        if node_id.startswith(prefix):
            return node_id.removeprefix(prefix)
    if node_id.startswith("rel_"):
        return node_id.removeprefix("rel_")
    return node_id
