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
        jiao = [
            date.fromisoformat(d)
            for d in result.luck_cycles.trace.get("exact_jiao_un_dates", [])
        ]

        contributions: list[tuple[str, GanjiLevel, _Contribution]] = []
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
            )
            contributions += [(label, level, c) for c in self._relation_contributions(ctx)]
            contributions += [(label, level, c) for c in self._mapping_contributions(ctx)]

        return self._aggregate(contributions)

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
            for ev in item.event_domains:
                out.append(_Contribution(
                    event=ev,
                    weight=max(item.base_score + modifier, 0.0),
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

    def _mapping_contributions(self, ctx: _PeriodContext) -> list[_Contribution]:
        """events/<domain>.json 신호 매핑 기반 기여(십성·관계·용기신·신살·교운)."""
        out: list[_Contribution] = []
        hit_types = {self._hit_dict_type(h) for h in ctx.hits}
        stem_ten_god = ctx.pillar.stem_ten_god
        stem_el = str(STEM_ELEMENT[Stem(ctx.stem)])
        branch_el = str(BRANCH_ELEMENT[Branch(ctx.branch)])
        sinsal_names = {s.name for s in ctx.pillar.luck_sinsal}

        for mapping in self._mappings:
            for idx, item in enumerate(mapping.items):
                weight_scale = self._match_signal(
                    item, ctx, hit_types, stem_ten_god, stem_el, branch_el, sinsal_names,
                )
                if weight_scale is None:
                    continue
                rule_node = f"rule_{mapping.domain}_{idx:02d}"
                sig = item.signal
                strongest = max(c.score for c in item.event_candidates)
                signal = Signal(
                    type="rule_match",
                    name=rule_node,
                    effect=item.note or rule_node,
                    weight=round(strongest * weight_scale * 100, 1),
                )
                for cand in item.event_candidates:
                    out.append(_Contribution(
                        event=cand.event,
                        weight=cand.score * weight_scale,
                        polarity=cand.polarity,
                        signal=signal,
                        path_nodes=[
                            ctx.period_node,
                            *( [f"tengod_{sig.ten_god}"] if sig.ten_god else [] ),
                            rule_node, f"event_{cand.event}",
                        ],
                        readable=[
                            f"{ctx.stem}{ctx.branch} {_LEVEL_KO[ctx.level]}",
                            *( [f"{ctx.stem}은 일간에게 {sig.ten_god}"] if sig.ten_god else [] ),
                            item.note or rule_node,
                            self._event_ko.get(cand.event, str(cand.event)),
                        ],
                    ))
        return out

    def _match_signal(
        self, item: EventMappingItem, ctx: _PeriodContext, hit_types: set[str],
        stem_ten_god: str, stem_el: str, branch_el: str, sinsal_names: set[str],
    ) -> float | None:
        """신호 조건 전부(AND) 일치 시 가중 배율(보통 1.0, 교운은 분포 가중)을 반환."""
        sig = item.signal
        if sig.ten_god is not None and sig.ten_god != stem_ten_god:
            return None
        if sig.relation is not None and sig.relation not in hit_types:
            return None
        if sig.favorability is not None:
            subject_el = stem_el if sig.ten_god is not None else branch_el
            if ctx.fav_map.get(subject_el) != sig.favorability:
                return None
        if sig.shinsal is not None and sig.shinsal not in sinsal_names:
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
        self, contributions: list[tuple[str, GanjiLevel, _Contribution]]
    ) -> list[EventCandidate]:
        """(period, event)별 weight 합산 → 0~100 클램프 + 대표 polarity/근거."""
        grouped: dict[tuple[str, GanjiLevel, EventKey], list[_Contribution]] = {}
        for label, level, contrib in contributions:
            grouped.setdefault((label, level, contrib.event), []).append(contrib)

        out: list[EventCandidate] = []
        for (label, _level, event), group in grouped.items():
            total = sum(c.weight for c in group)
            score = max(0, min(100, round(total * 100)))
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
                confidence=confidence,
                polarity=top.polarity,
                signals=[c.signal for c in group],
                evidence_path=top.path_nodes,
            ))
        return sorted(out, key=lambda c: (-c.score, c.period, str(c.event_key)))

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
