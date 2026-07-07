"""관계 엔진 — E13 Compatibility(궁합) · E12 Competition(경쟁/승부) (Phase 5 T5.6·T5.7).

E13: 관계 유형별로 보는 축이 다르다(relation_profiles 사전). 일지 상호작용은
relations.json의 글자쌍을 단일 소스로 조회한다.
E12: 판정일 운세 강도 비교 — **당락·승패 확정 표현 출력 금지**(절대 원칙 8),
실존 공인은 대부분 시각 미상 → no_hour 모드 + 신뢰도 한계 명시.
"""

from __future__ import annotations

import json
from pathlib import Path

from saju_manse_analysis.yongsin.operational_role_config import is_unfavorable_role

from saju_shared_types.constants import GENERATES, STEM_ELEMENT
from saju_shared_types.enums import Element, Stem
from saju_shared_types.events import EventCandidate, EventKey
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.prediction import (
    CompatibilityAxis,
    CompatibilityResult,
    CompetitionCandidate,
    CompetitionResult,
)

from .event_scoring import favorability_map

# E12 당락 단정 금지 — templates 레벨 고정 문구(docs/02 E12 정책).
COMPETITION_PROHIBITIONS = [
    "당락·승패·순위 단정 표현 금지 — '해당일 운이 상대적으로 강하다'까지만",
    "실존 공인 비교는 명예·선거 리스크 고지 + 출생 시각 미상 한계 명시",
    "조건 분기('당선되면 이후 운')는 시나리오임을 명시",
]


class CompatibilityEngine:
    """E13 — 두 차트의 관계 유형별 축 분석(결정론)."""

    def __init__(self, dictionaries_dir: Path) -> None:
        """relation_profiles + relations 글자쌍 로드."""
        profiles = json.loads(
            (dictionaries_dir / "relation_profiles.json").read_text("utf-8")
        )
        self._profiles: dict[str, list[dict]] = {
            i["relationType"]: i["axes"] for i in profiles["items"]
        }
        relations = json.loads(
            (dictionaries_dir / "relations.json").read_text("utf-8")
        )
        self._pair_kind: dict[frozenset[str], str] = {}
        for item in relations["items"]:
            members = item["participants"]
            if len(members) == 2 and members[0] != members[1]:
                self._pair_kind[frozenset(members)] = item["type"]

    def analyze(
        self, a: ManseV2Result, b: ManseV2Result, relation_type: str = "lover"
    ) -> CompatibilityResult:
        """관계 유형 축 가중으로 두 차트의 적합도를 평가한다."""
        assert a.pillars is not None and b.pillars is not None
        axes_spec = self._profiles.get(relation_type, self._profiles["friend"])
        fav_a = favorability_map(a)
        fav_b = favorability_map(b)

        scores: dict[str, tuple[int, list[str]]] = {}
        scores["day_pillar_interaction"] = self._day_pillar_axis(a, b)
        scores["yongsin_complement"] = self._yongsin_axis(a, b, fav_a, fav_b)
        # 그 외 축은 공통 베이스(50) + 일간 십성 관계 보정(초안 — 세분화는 검수 후).
        generic = self._stem_relation_axis(a, b)
        for spec in axes_spec:
            scores.setdefault(spec["axis"], generic)

        axes: list[CompatibilityAxis] = []
        overall = 0.0
        for spec in axes_spec:
            score, notes = scores[spec["axis"]]
            axes.append(CompatibilityAxis(
                axis=spec["axis"], ko=spec["ko"], score=score, notes=notes,
            ))
            overall += score * spec["weight"]

        patterns, frictions = self._patterns(scores)
        return CompatibilityResult(
            relation_type=relation_type,
            overall=max(0, min(100, round(overall))),
            axes=axes,
            patterns=patterns,
            frictions=frictions,
            advice=(
                ["갈등 축은 역할 분담을 명시적으로 정하면 완화됩니다"] if frictions else []
            ),
        )

    # ── 축 계산 ──────────────────────────────────────────────────

    def _day_pillar_axis(
        self, a: ManseV2Result, b: ManseV2Result
    ) -> tuple[int, list[str]]:
        """일지 글자쌍 관계(합 + / 충·형·원진 −) — relations.json 단일 소스."""
        assert a.pillars is not None and b.pillars is not None
        pair = frozenset({a.pillars.day.branch, b.pillars.day.branch})
        kind = self._pair_kind.get(pair)
        if kind in ("six_combination",):
            return 85, [f"일지 육합({a.pillars.day.branch}-{b.pillars.day.branch}) — 결속"]
        if kind in ("branch_clash",):
            return 30, [f"일지 충({a.pillars.day.branch}-{b.pillars.day.branch}) — 부딪힘 주의"]
        if kind in ("punishment_mutual", "harm", "wonjin"):
            return 38, [f"일지 {kind} — 정서적 마찰 가능"]
        if kind in ("branch_break",):
            return 45, ["일지 파 — 약한 흔들림"]
        return 60, ["일지 특이 관계 없음 — 무난"]

    @staticmethod
    def _yongsin_axis(
        a: ManseV2Result, b: ManseV2Result,
        fav_a: dict[str, str], fav_b: dict[str, str],
    ) -> tuple[int, list[str]]:
        """상대 일간 오행이 내 용신/기신인가 — 상호 보완성."""
        assert a.pillars is not None and b.pillars is not None
        el_a = str(STEM_ELEMENT[Stem(a.pillars.day.stem)])
        el_b = str(STEM_ELEMENT[Stem(b.pillars.day.stem)])
        score = 50
        notes: list[str] = []
        for my_fav, other_el, who in ((fav_a, el_b, "상대"), (fav_b, el_a, "나")):
            role = my_fav.get(other_el)
            if role == "용신":
                score += 20
                notes.append(f"{who}의 일간 오행({other_el})이 용신 — 보완")
            elif role == "희신":
                score += 10
                notes.append(f"{who}의 일간 오행({other_el})이 희신")
            elif is_unfavorable_role(role):
                score -= 15
                notes.append(f"{who}의 일간 오행({other_el})이 {role} — 소모 주의")
        return max(0, min(100, score)), notes or ["용신 상호작용 중립"]

    @staticmethod
    def _stem_relation_axis(a: ManseV2Result, b: ManseV2Result) -> tuple[int, list[str]]:
        """일간 오행 생극 — 생(生) 관계 +, 극(剋) 관계 −(초안 공통 축)."""
        assert a.pillars is not None and b.pillars is not None
        el_a = STEM_ELEMENT[Stem(a.pillars.day.stem)]
        el_b = STEM_ELEMENT[Stem(b.pillars.day.stem)]
        if GENERATES[el_a] is el_b or GENERATES[el_b] is el_a:
            return 70, [f"일간 상생({el_a}↔{el_b})"]
        if el_a is el_b:
            return 60, ["일간 동기(같은 오행) — 동질·경쟁 양면"]
        if GENERATES[Element(el_a)] is not el_b:  # 극 관계 여부 간이 판정
            from saju_shared_types.constants import CONTROLS

            if CONTROLS[el_a] is el_b or CONTROLS[el_b] is el_a:
                return 45, [f"일간 상극({el_a}↔{el_b}) — 역할 정리 필요"]
        return 55, ["일간 관계 중립"]

    @staticmethod
    def _patterns(
        scores: dict[str, tuple[int, list[str]]]
    ) -> tuple[list[str], list[str]]:
        patterns = [n for s, notes in scores.values() if s >= 70 for n in notes]
        frictions = [n for s, notes in scores.values() if s <= 40 for n in notes]
        return patterns, frictions


class CompetitionEngine:
    """E12 — 판정일 운세 강도 비교(당락 단정 금지)."""

    GAP_CLEAR = 15  # 점수차 임계(초안) — 이상이면 'clear'
    GAP_NARROW = 5

    def compare(
        self,
        subjects: list[tuple[str, ManseV2Result, list[EventCandidate]]],
        anchor_date: str,
        event_key: EventKey | None = None,
    ) -> CompetitionResult:
        """대상별 판정일 기준 운세 강도(일운+월운+세운 가중)와 상대 우열.

        Args:
            subjects: (라벨, 만세 결과, 그 대상의 이벤트 후보) — 후보는 기준일 차트로 산출.
            anchor_date: 판정 기준일('YYYY-MM-DD') — 사용자 지정 우선(투표일 vs 개표일).
            event_key: 경쟁 이벤트(시험/선거 등) — 해당 신호 가중.
        """
        out: list[CompetitionCandidate] = []
        for label, result, candidates in subjects:
            score, path = self._strength(result, candidates, anchor_date, event_key)
            no_hour = result.pillars is not None and result.pillars.hour is None
            out.append(CompetitionCandidate(
                subject_label=label,
                strength_score=score,
                evidence_path=path,
                data_quality="no_hour" if no_hour else "full",
            ))
        out.sort(key=lambda c: -c.strength_score)
        gap = (
            "inconclusive" if len(out) < 2
            else "clear" if out[0].strength_score - out[1].strength_score >= self.GAP_CLEAR
            else "narrow" if out[0].strength_score - out[1].strength_score >= self.GAP_NARROW
            else "inconclusive"
        )
        return CompetitionResult(
            anchor_date=anchor_date,
            candidates=out,
            relative_gap=gap,
            prohibitions=list(COMPETITION_PROHIBITIONS),
        )

    @staticmethod
    def _strength(
        result: ManseV2Result,
        candidates: list[EventCandidate],
        anchor_date: str,
        event_key: EventKey | None,
    ) -> tuple[int, list[str]]:
        """판정일 강도 = 일운 0.5 + 월운 0.3 + 세운 0.2 (luck_score 기반, 초안 가중)."""
        lc = result.luck_cycles
        score = 50.0
        path: list[str] = []
        if lc is not None:
            year_key, month_key = anchor_date[:4], anchor_date[:7]
            for weight, pillars, key in (
                (0.2, lc.yearly_luck, year_key),
                (0.3, lc.monthly_luck, month_key),
                (0.5, lc.daily_luck, anchor_date),
            ):
                match = next((p for p in pillars if p.label == key), None)
                if match is not None:
                    score += match.luck_score * weight * 50
                    label = match.luck_label or match.yongsin_alignment
                    path.append(f"{key} {match.ganji} {label}")
        # 해당 이벤트 신호 가중(판정일이 속한 기간의 후보).
        if event_key is not None:
            relevant = [
                c for c in candidates
                if c.event_key is event_key and anchor_date.startswith(c.period[:4])
            ]
            if relevant:
                best = max(relevant, key=lambda c: c.score)
                score += best.score * 0.1
                path.append(f"{best.event_key}@{best.period} {best.score}점")
        return max(0, min(100, round(score))), path
