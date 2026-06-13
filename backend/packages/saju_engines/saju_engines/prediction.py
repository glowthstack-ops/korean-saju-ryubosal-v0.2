"""예측 엔진군 — E4 Timeline · E3 Event Form · E5 Self Profile · E6 Manifestation ·
E8 Advice (v2.2 Phase 5 T5.1~T5.5, docs/02).

전부 사전(JSON) 기반 룰 + 가중치의 결정론 계산이다. 가중 계수는 초안(reviewed:false
사전·코드 상수) — 실테스트로 조정한다(docs/07 리스크 1: 절대값보다 상대 순위).
"""

from __future__ import annotations

import json
from pathlib import Path

from saju_shared_types.events import EventCandidate, EventKey
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.prediction import (
    ActivationWindow,
    AdviceItem,
    AdviceResult,
    EventForm,
    EventFormResult,
    EventTimeline,
    ManifestationResult,
    SelfProfile,
    TimelinePhase,
    TimelineScores,
)

_STAGE_ORDER = ["awareness", "exploration", "action", "decision", "completion"]
# 단계 → (interest, action, completion) 기여 가중(초안).
_STAGE_SCORE_W = {
    "awareness": (1.0, 0.2, 0.0),
    "exploration": (0.8, 0.5, 0.1),
    "action": (0.4, 1.0, 0.5),
    "decision": (0.2, 0.7, 1.0),
    "completion": (0.1, 0.3, 1.0),
}


class PredictionEngines:
    """사전 로드를 공유하는 예측 엔진 묶음(결정론)."""

    def __init__(self, dictionaries_dir: Path) -> None:
        """stage_mapping/event_forms/remedy 사전 로드."""
        self._stage_by_signal: dict[str, str] = {
            i["signalType"]: i["stage"]
            for i in self._read(dictionaries_dir / "stage_mapping.json")["items"]
        }
        self._forms_by_event: dict[str, list[dict]] = {
            i["eventKey"]: i["forms"]
            for i in self._read(dictionaries_dir / "event_forms.json")["items"]
        }
        remedy = self._read(dictionaries_dir / "remedy.json")
        self._remedy_branches: list[dict] = remedy["branches"]
        self._disclaimers: dict[str, str] = remedy["disclaimers"]

    @staticmethod
    def _read(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    # ── E4 Timeline (T5.1) — progress 이벤트 전용 ─────────────────

    def build_timeline(
        self, event_key: EventKey, candidates: list[EventCandidate]
    ) -> EventTimeline | None:
        """월운 후보들의 신호 유형을 단계로 매핑해 Activation Window를 만든다.

        Trigger Month ≠ Execution Month(절대 원칙 4): 합(인지)→탐색→충(행동)→결정.
        해당 이벤트의 월 단위 후보가 없으면 None.
        """
        monthly = sorted(
            (c for c in candidates if c.event_key is event_key and len(c.period) == 7),
            key=lambda c: c.period,
        )
        if not monthly:
            return None

        phases: list[TimelinePhase] = []
        acc = {"interest": 0.0, "action": 0.0, "completion": 0.0}
        for c in monthly:
            stages = [
                self._stage_by_signal.get(s.type, "awareness") for s in c.signals
            ]
            # 진행 단계가 가장 깊은 신호를 그 달의 대표 단계로(보수적 표현 회피 방지).
            stage = max(stages, key=_STAGE_ORDER.index) if stages else "awareness"
            phases.append(TimelinePhase(period=c.period, stage=stage))
            wi, wa, wc = _STAGE_SCORE_W[stage]
            acc["interest"] += c.score * wi
            acc["action"] += c.score * wa
            acc["completion"] += c.score * wc

        n = len(monthly)
        scores = TimelineScores(
            interest=min(100, round(acc["interest"] / n)),
            action=min(100, round(acc["action"] / n)),
            completion=min(100, round(acc["completion"] / n)),
        )
        return EventTimeline(
            event_key=event_key,
            activation_window=ActivationWindow(
                start=monthly[0].period, end=monthly[-1].period,
            ),
            phases=phases,
            scores=scores,
        )

    # ── E3 Event Form (T5.2) ─────────────────────────────────────

    def event_forms(
        self, event_key: EventKey, profile: SelfProfile | None = None
    ) -> EventFormResult:
        """발현 형태 분포 — form 사전 + Self Profile 보정(prob 합 ≤ 1.0 유지).

        실행력이 높으면 능동형(첫 번째) 형태를, 낮으면 수동형(후순위)을 소폭 가중.
        """
        base = self._forms_by_event.get(str(event_key), [])
        forms = [EventForm(name=f["name"], prob=f["prob"]) for f in base]
        if profile is not None and forms:
            shift = (profile.execution_power - 50) / 1000  # ±0.05 한도(초안)
            forms[0] = forms[0].model_copy(
                update={"prob": min(1.0, max(0.0, forms[0].prob + shift))}
            )
            forms[-1] = forms[-1].model_copy(
                update={"prob": min(1.0, max(0.0, forms[-1].prob - shift))}
            )
        total = sum(f.prob for f in forms)
        if total > 1.0:  # 합 ≤ 1.0 보정
            forms = [f.model_copy(update={"prob": round(f.prob / total, 4)}) for f in forms]
        return EventFormResult(event_key=event_key, forms=forms)

    # ── E5 Self Profile (T5.3) — 성격검사화 금지 ──────────────────

    def self_profile(self, result: ManseV2Result) -> SelfProfile:
        """십성 분포·강약·구조 플래그 → 현실화 방식 프로파일(모든 축 근거 첨부)."""
        assert result.force_analysis is not None
        dist = result.force_analysis.ten_gods.distribution
        groups = result.force_analysis.ten_gods.groups
        band = result.force_analysis.strength.band
        evidence: list[str] = []

        def g(name: str) -> float:
            return groups.get(name, 0.0)

        # 결정 스타일: 우세 그룹 기반(초안 룰).
        dominant = max(groups, key=lambda k: groups[k]) if groups else "peer"
        style_map = {
            "peer": "impulsive", "output": "impulsive",
            "resource": "deliberate", "officer": "consensus", "wealth": "deliberate",
        }
        decision_style = style_map.get(dominant, "deliberate")
        evidence.append(f"우세 그룹 {dominant}({groups.get(dominant, 0):.2f}) → {decision_style}")

        total = sum(groups.values()) or 1.0
        risk = round(100 * (g("output") + g("peer") * 0.5) / total)
        risk += round(dist.get("겁재", 0) * 0.3 + dist.get("상관", 0) * 0.3)
        risk = max(0, min(100, risk))
        evidence.append(f"위험 감수: 식상+비겁 비중 기반 {risk}")

        strong = band in ("신강", "태신강", "극신강", "중화신강")
        execution = round(100 * (g("peer") + g("output")) / total)
        execution += 15 if strong else -10
        execution = max(0, min(100, execution))
        evidence.append(f"실행력: 비겁+식상 비중 + 강약({band}) 보정 {execution}")

        axes = {
            "relationship": "재성·관성 구성 기반"
            + ("(안정 지향)" if g("officer") >= g("wealth") else "(주도 지향)"),
            "money": "고정 수입 선호" if dist.get("정재", 0) >= dist.get("편재", 0)
            else "유동·기회 추구",
            "work": "조직·규범 적합" if g("officer") >= g("output") else "자율·전문 적합",
            "stress": "수용·학습형" if g("resource") > 0 else "발산·행동형",
        }
        tendency = (
            "accumulate_then_move" if decision_style == "deliberate"
            else "act_then_adjust" if decision_style == "impulsive"
            else "align_then_commit"
        )
        return SelfProfile(
            decision_style=decision_style,
            risk_tolerance=risk,
            execution_power=execution,
            axes=axes,
            manifestation_tendency=tendency,
            evidence=evidence,
        )

    # ── E6 Manifestation (T5.4) ──────────────────────────────────

    def manifestation(
        self,
        candidate: EventCandidate,
        profile: SelfProfile,
        reality_context: dict | None = None,
    ) -> ManifestationResult:
        """발생 가능성 + 성향 + 현실 맥락 결합 — 현실화 점수.

        Reality Context 부재 시 modifier 0 + confidence 하향(필드 부재로 오류 금지 —
        절대 원칙 11).
        """
        profile_modifier = round((profile.execution_power - 50) * 0.3)
        context_modifier = 0
        confidence = "medium"
        if reality_context:
            # 1차 소스: 2단계 프로필(직업/거주/결혼) — 관련 필드가 있으면 ±10 한도 보정.
            relevant = reality_context.get(str(candidate.event_key))
            context_modifier = max(-10, min(10, int(relevant or 0)))
            confidence = "medium_high"
        else:
            confidence = "medium_low"

        realization = max(0, min(100, candidate.score + profile_modifier + context_modifier))
        forms = self.event_forms(candidate.event_key, profile)
        return ManifestationResult(
            event_key=candidate.event_key,
            event_score=candidate.score,
            profile_modifier=profile_modifier,
            context_modifier=context_modifier,
            realization_score=realization,
            likely_forms=[f.name for f in forms.forms[:3]],
            confidence=confidence,
        )

    # ── E8 Advice (T5.5 — remedy 6분기) ──────────────────────────

    def advice(
        self,
        event_key: EventKey,
        timeline: EventTimeline | None,
        cautions_from_signals: list[str] | None = None,
    ) -> AdviceResult:
        """단계별 행동 조언 + 주의 + 고지. 문구는 사전에서, 재서술은 LLM이."""
        items: list[AdviceItem] = []
        stage_action = {
            "awareness": ("정보 수집과 방향 점검", "변화 신호가 켜진 시기 — 결정보다 탐색"),
            "exploration": ("선택지 비교·조건 정리", "기회 비교에 유리한 흐름"),
            "action": ("실행·지원·면접 등 구체 행동", "행동 신호(충·이동)가 강한 시기"),
            "decision": ("최종 결정·계약 확정", "결정 신호(문서·합 해소)가 받치는 시기"),
            "completion": ("마무리·정착", "결과를 안정시키는 구간"),
        }
        if timeline is not None:
            for phase in timeline.phases:
                action, rationale = stage_action[phase.stage]
                items.append(AdviceItem(
                    period=phase.period, action=action, rationale=rationale,
                ))

        cautions = list(cautions_from_signals or [])
        for branch in self._remedy_branches:
            if branch["branch"] in ("time_avoidance", "behavior_caution"):
                cautions += branch["guides"][:1]

        disclaimers: list[str] = []
        if event_key is EventKey.HEALTH_ATTENTION:
            disclaimers.append(self._disclaimers["health"])
        if event_key is EventKey.LEGAL_CONFLICT:
            disclaimers.append(self._disclaimers["legal"])
        if event_key in (EventKey.WINDFALL, EventKey.WEALTH_CHANGE):
            disclaimers.append(self._disclaimers["finance"])

        return AdviceResult(
            event_key=event_key, advice=items, cautions=cautions, disclaimers=disclaimers,
        )
