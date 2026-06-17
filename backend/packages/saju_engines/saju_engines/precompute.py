"""LuckComposite 계산기 (v2.2 Phase 2.5 T2.5.3, docs/09 1·3장).

만세력 엔진 결과(`ManseV2Result`)에서 레벨별(natal/대운/세운/월운/일운) LuckComposite를
산출한다. 각 레벨 레코드는 그 레벨 소스가 **참여한** 상호작용만 담는다:

  natal  → P01 (원국 내부)                                   [T0]
  daewoon→ P02 (원국×대운)                                    [T1]
  year   → P03·P06 + 다자 혼합(원국·대운·세운)                [T1]
  month  → P04·P07·P09 + 다자 혼합                            [T1]
  day    → P05·P08·P10·P11 + 다자 혼합                        [T2]

해석 결정(검수 대상, docs에 미정의): ① natal 레코드의 대표 ganji=일주 ② favorability
단일 값은 레벨 대표 간지의 **천간 오행** 기준(천간=드러남 통설; 지지 분리 평가는 엔진
LuckPillar에 이미 존재). ③ EventKey→Domain 매핑은 초안 상수(_EVENT_DOMAIN).
"""

from __future__ import annotations

import json
from pathlib import Path

from saju_shared_types.constants import STEM_ELEMENT
from saju_shared_types.enums import Stem
from saju_shared_types.luck import LuckPillar
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.precompute import (
    CompositeGanji,
    CompositeLevel,
    DomainSignal,
    InteractionHit,
    InteractionSource,
    LuckComposite,
    ParentContext,
    TenGodPair,
)

from .dictionaries import FavorabilityRulesFile, RelationsFile
from .event_scoring import favorability_map
from .interactions import (
    InteractionDetector,
    PoolEntry,
    clash_pair_sets,
    natal_structure_flags,
    structure_flags,
)

# EventKey → Domain 초안 매핑 (docs/03 C graphScope 어휘 기준 — 검수 대상).
_EVENT_DOMAIN: dict[str, str] = {
    "career_change": "career", "promotion": "career", "resignation": "career",
    "business_start": "career",
    "relationship_start": "relationship", "relationship_end": "relationship",
    "marriage": "relationship", "childbirth": "relationship",
    "relocation": "relocation", "travel": "relocation",
    "contract": "wealth", "document": "wealth",
    "wealth_change": "wealth", "income_change": "wealth", "expense_risk": "wealth",
    "windfall": "wealth", "speculation_risk": "wealth", "asset_volatility": "wealth",
    "education_start": "education", "education_complete": "education", "exam": "education",
    "health_issue": "health", "surgery": "health",
    "family_change": "relationship", "lawsuit": "general",
}

_NATAL_SOURCES = (
    InteractionSource.NATAL_YEAR, InteractionSource.NATAL_MONTH,
    InteractionSource.NATAL_DAY, InteractionSource.NATAL_HOUR,
)

_LEVEL_SOURCE = {
    CompositeLevel.DAEWOON: InteractionSource.DAEWOON,
    CompositeLevel.YEAR: InteractionSource.YEAR,
    CompositeLevel.MONTH: InteractionSource.MONTH,
    CompositeLevel.DAY: InteractionSource.DAY,
}


class CompositeBuilder:
    """결정론 LuckComposite 계산기 — 동일 (대상, 기간, dictVersion) → 동일 출력."""

    def __init__(self, dictionaries_dir: Path) -> None:
        """사전 로드: 상호작용 탐지기 + favorability 보정 + 충/합 쌍 집합."""
        relations_path = dictionaries_dir / "relations.json"
        self._detector = InteractionDetector(relations_path)
        self._stem_clash, self._branch_clash, self._six = clash_pair_sets(relations_path)
        self._favorability = FavorabilityRulesFile.model_validate(
            json.loads((dictionaries_dir / "favorability_rules.json").read_text("utf-8"))
        )
        relations = RelationsFile.model_validate(
            json.loads(relations_path.read_text("utf-8"))
        )
        self._relation_domains: dict[str, list[str]] = {
            item.id: [str(e) for e in item.event_domains] for item in relations.items
        }
        self._relation_element: dict[str, str | None] = {
            item.id: item.result_element for item in relations.items
        }
        # favorability(용·희·기·구·한) → 일반 보정 규칙 modifier.
        self._fav_modifier: dict[str, float] = {
            r.condition.favorability: r.effect.score_modifier
            for r in self._favorability.items
            if r.condition.ten_god is None
        }

    # ── 공개 API ─────────────────────────────────────────────────

    def build(
        self,
        result: ManseV2Result,
        subject_id: str,
        dict_version: str,
        computed_at: str,
        levels: set[CompositeLevel] | None = None,
    ) -> list[LuckComposite]:
        """만세 결과 전체를 레벨별 LuckComposite 목록으로 변환한다.

        Args:
            result: pillars·luck_cycles가 채워진 만세력 엔진 결과.
            subject_id: 대상 식별자(쌍둥이 변형은 'subjectId#variant' — docs/09 1장).
            dict_version: 컴파일 사전 버전(불일치 데이터 혼용 금지 — docs/07 리스크 13).
            computed_at: 계산 시각 ISO 문자열(호출 측 주입 — 결정성 유지).
            levels: 산출할 레벨(None=전부).

        Returns:
            natal → daewoon → year → month → day 순의 LuckComposite 목록.
        """
        if result.pillars is None:
            return []
        wanted = levels or set(CompositeLevel)
        fav_map = favorability_map(result)
        natal_entries = self._natal_entries(result)
        natal_ganji_pairs = [(e.stem, e.branch) for e in natal_entries if e.stem and e.branch]
        void = list(result.pillars.gongmang_branches)

        out: list[LuckComposite] = []
        common = dict(
            subject_id=subject_id, dict_version=dict_version, computed_at=computed_at,
        )

        if CompositeLevel.NATAL in wanted:
            out.append(self._natal_composite(result, natal_entries, fav_map, **common))

        lc = result.luck_cycles
        if lc is None:
            return out

        daewoon_by_year: dict[int, str] = {}
        for d in lc.daewoon_table:
            for y in range(d.approx_start_date.year, d.approx_end_date.year):
                daewoon_by_year[y] = d.ganji

        if CompositeLevel.DAEWOON in wanted:
            for d in lc.daewoon_table:
                pillar = _daewoon_pillar_view(d)
                out.append(self._luck_composite(
                    CompositeLevel.DAEWOON, f"DW:{d.ganji}", pillar,
                    natal_entries, natal_ganji_pairs, void, fav_map,
                    ParentContext(), upper=[], **common,
                ))

        year_ganji = {p.label: p.ganji for p in lc.yearly_luck}
        month_ganji = {p.label: p.ganji for p in lc.monthly_luck}
        # 일운의 부모 월은 절기 월을 따른다 — 캘린더 월(label[:7])로 잡으면 절입(예: 소서)
        # 이전 초순의 날이 다음 절기월로 오인된다(2026-07-04는 절기상 甲午인데 乙未로 잡힘).
        seolgi_month = self._seolgi_month_labels(result, lc) if CompositeLevel.DAY in wanted else {}

        for level, pillars in (
            (CompositeLevel.YEAR, lc.yearly_luck),
            (CompositeLevel.MONTH, lc.monthly_luck),
            (CompositeLevel.DAY, lc.daily_luck),
        ):
            if level not in wanted:
                continue
            for p in pillars:
                parent, upper = self._parents_for(
                    level, p.label, daewoon_by_year, year_ganji, month_ganji,
                    seolgi_month,
                )
                out.append(self._luck_composite(
                    level, p.label, p, natal_entries, natal_ganji_pairs,
                    void, fav_map, parent, upper, **common,
                ))
        return out

    # ── 내부 ─────────────────────────────────────────────────────

    def _natal_entries(self, result: ManseV2Result) -> list[PoolEntry]:
        """원국 4주 → 풀 엔트리(시주 미상 시 3주)."""
        assert result.pillars is not None
        p = result.pillars
        entries = [
            PoolEntry(InteractionSource.NATAL_YEAR, p.year.stem, p.year.branch),
            PoolEntry(InteractionSource.NATAL_MONTH, p.month.stem, p.month.branch),
            PoolEntry(InteractionSource.NATAL_DAY, p.day.stem, p.day.branch),
        ]
        if p.hour is not None:
            entries.append(PoolEntry(InteractionSource.NATAL_HOUR, p.hour.stem, p.hour.branch))
        return entries

    def _natal_composite(
        self, result: ManseV2Result, natal_entries: list[PoolEntry],
        fav_map: dict[str, str], *, subject_id: str, dict_version: str, computed_at: str,
    ) -> LuckComposite:
        """P01(원국 내부) 레코드 — 대표 간지=일주(해석 결정, 검수 대상)."""
        assert result.pillars is not None
        day = result.pillars.day
        hits = self._detector.detect(natal_entries)
        sinsal = result.traditional_extras.sinsal if result.traditional_extras else None
        return LuckComposite(
            subject_id=subject_id,
            level=CompositeLevel.NATAL,
            period_key="natal",
            ganji=CompositeGanji(stem=day.stem, branch=day.branch),
            ten_god=TenGodPair(stem=day.stem_ten_god, branch_main=day.branch_main_ten_god),
            twelve_stage=day.twelve_unseong,
            favorability=fav_map.get(str(STEM_ELEMENT[Stem(day.stem)]), "한신"),
            interactions=hits,
            structure_flags=natal_structure_flags(
                [(e.stem, e.branch) for e in natal_entries if e.stem and e.branch]
            ),
            shinsal_active=(
                sorted({i.name for i in sinsal.full_list}) if sinsal else []
            ),
            domain_signals=self._domain_signals(hits, fav_map),
            dict_version=dict_version,
            computed_at=computed_at,
        )

    def _luck_composite(
        self, level: CompositeLevel, period_key: str, pillar: LuckPillar,
        natal_entries: list[PoolEntry], natal_ganji_pairs: list[tuple[str, str]],
        void: list[str], fav_map: dict[str, str], parent: ParentContext,
        upper: list[tuple[InteractionSource, str]], *,
        subject_id: str, dict_version: str, computed_at: str,
    ) -> LuckComposite:
        """운 레벨 레코드 — 이 레벨 소스가 참여한 상호작용만 수록(P02~P11)."""
        source = _LEVEL_SOURCE[level]
        pool = [
            *natal_entries,
            *[PoolEntry(src, g[0], g[1]) for src, g in upper],
            PoolEntry(source, pillar.stem, pillar.branch),
        ]
        hits = [
            h for h in self._detector.detect(pool)
            if any(pt.source == source for pt in h.participants)
        ]
        flags = structure_flags(
            pillar.stem, pillar.branch, natal_ganji_pairs, void,
            self._stem_clash, self._branch_clash, self._six,
        )
        return LuckComposite(
            subject_id=subject_id,
            level=level,
            period_key=period_key,
            ganji=CompositeGanji(stem=pillar.stem, branch=pillar.branch),
            parent_context=parent,
            ten_god=TenGodPair(stem=pillar.stem_ten_god, branch_main=pillar.branch_ten_god),
            twelve_stage=pillar.twelve_unseong,
            favorability=fav_map.get(str(STEM_ELEMENT[Stem(pillar.stem)]), "한신"),
            interactions=hits,
            structure_flags=flags,
            shinsal_active=[s.name for s in pillar.luck_sinsal],
            domain_signals=self._domain_signals(hits, fav_map),
            dict_version=dict_version,
            computed_at=computed_at,
        )

    def _parents_for(
        self, level: CompositeLevel, label: str, daewoon_by_year: dict[int, str],
        year_ganji: dict[str, str], month_ganji: dict[str, str],
        seolgi_month: dict[str, str],
    ) -> tuple[ParentContext, list[tuple[InteractionSource, str]]]:
        """상위 레벨 간지(parentContext)와 풀에 넣을 상위 운 글자들."""
        year_label = label[:4]
        dw = daewoon_by_year.get(int(year_label)) if year_label.isdigit() else None
        parent = ParentContext(daewoon=dw)
        upper: list[tuple[InteractionSource, str]] = []
        if dw:
            upper.append((InteractionSource.DAEWOON, dw))
        if level in (CompositeLevel.MONTH, CompositeLevel.DAY):
            yg = year_ganji.get(year_label)
            parent.year = yg
            if yg:
                upper.append((InteractionSource.YEAR, yg))
        if level is CompositeLevel.DAY:
            # 절기 월 키 우선(절입 경계 보정) — 미산출/미등록이면 캘린더 월로 폴백.
            month_key = seolgi_month.get(label, label[:7])
            if month_key not in month_ganji:
                month_key = label[:7]
            mg = month_ganji.get(month_key)
            parent.month = mg
            if mg:
                upper.append((InteractionSource.MONTH, mg))
        return parent, upper

    @staticmethod
    def _seolgi_month_labels(
        result: ManseV2Result, lc: object
    ) -> dict[str, str]:
        """일운 날짜 → 절기 월 라벨('YYYY-MM') 매핑. 절입 이전 초순일의 월주 오인 방지.

        만세 코어의 luck_month_label(절기 경계 기준)을 SSOT로 쓴다. 실패는 빈 맵으로 폴백해
        캘린더 월 동작을 유지한다(데이터 부재가 산출을 막지 않게).
        """
        from datetime import date as _date

        try:
            from saju_manse_analysis.luck.luck_calendar import luck_month_label

            from saju_manse_core.calendar.solar_terms import get_table
        except ImportError:
            return {}
        tz = result.time_correction.timezone if result.time_correction else "Asia/Seoul"
        table = get_table()
        mapping: dict[str, str] = {}
        for p in getattr(lc, "daily_luck", []):
            try:
                mapping[p.label] = luck_month_label(_date.fromisoformat(p.label), table, tz)
            except (ValueError, TypeError):
                continue
        return mapping

    def _domain_signals(
        self, hits: list[InteractionHit], fav_map: dict[str, str]
    ) -> list[DomainSignal]:
        """상호작용 → 사전 eventDomains 기반 도메인 신호(favorability 보정 포함)."""
        out: list[DomainSignal] = []
        for hit in hits:
            # favorability 보정: 합화 결과 오행이 정의된 관계는 그 오행의 역할로 보정.
            element = self._relation_element.get(hit.relation_id)
            fav = fav_map.get(element) if element else None
            modifier = self._fav_modifier.get(fav, 0.0) if fav else 0.0
            for event in self._relation_domains.get(hit.relation_id, []):
                weight = max(hit.base_weight + modifier, 0.0)
                if hit.partial:
                    weight *= 0.6  # 반합/부분형 감쇠 — 초안 계수(검수 대상)
                out.append(DomainSignal(
                    domain=_EVENT_DOMAIN.get(event, "general"),
                    event_key=event,
                    weight=round(weight, 4),
                    source_interaction=hit.relation_id,
                ))
        return out


def _daewoon_pillar_view(d) -> LuckPillar:
    """DaewoonItem을 공용 LuckPillar 형태로 투영(계산기 내부 공용 경로용)."""
    return LuckPillar(
        label=f"DW:{d.ganji}", period_type="daewoon", ganji=d.ganji,
        stem=d.stem, branch=d.branch,
        stem_ten_god=d.stem_ten_god, branch_ten_god=d.branch_ten_god,
        twelve_unseong=d.twelve_unseong,
        relations_to_chart=d.relations_to_chart,
        gongmang_activation=d.gongmang_activation,
        luck_sinsal=d.luck_sinsal,
    )
