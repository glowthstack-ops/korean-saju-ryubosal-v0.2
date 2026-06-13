"""TwelveLifeStageModifier (Phase 3) — 12운성으로 사건 후보의 상태·강도·시차를 보정한다.

십성이 만든 사건 '타입' 후보(EventCandidateV2)에 운 지지 12운성을 적용해 event_phase(시작·공식화·
정점·종료 등)와 점수를 조정한다. **사건 타입을 새로 만들지 않는다**(보정 전용).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from saju_shared_types.event_engine import (
    TWELVE_STAGE_KO_TO_KEY,
    EventCandidateV2,
    LuckLayer,
    TwelveStage,
)
from saju_shared_types.luck import LuckPillar

# 12운성 단독 적용 시 사건 점수 총 보정 한도(과보정 방지).
_STAGE_DELTA_CAP = 18


class _StageRule(BaseModel):
    model_config = ConfigDict(extra="ignore")
    stage: TwelveStage
    event_phase: str
    score_modifier: int
    good_for: list[str] = []
    caution_for: list[str] = []


class _EventSpecific(BaseModel):
    model_config = ConfigDict(extra="ignore")
    boost_stages: list[TwelveStage] = []
    reduce_stages: list[TwelveStage] = []


class _LayerStageCombo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    condition: dict
    score_bonus: int = 0
    good_for: list[str] = []


class TwelveStageModifier:
    """brancher 후보에 12운성 보정을 적용한다."""

    def __init__(self, dictionaries_dir: Path) -> None:
        raw = json.loads(
            (dictionaries_dir / "event_engine" / "twelve_stage_modifier.json").read_text(
                encoding="utf-8"
            )
        )
        self._stage: dict[TwelveStage, _StageRule] = {
            (r := _StageRule.model_validate(item)).stage: r
            for item in raw["stage_modifier_rules"]
        }
        self._event_specific: dict[str, _EventSpecific] = {
            k: _EventSpecific.model_validate(v)
            for k, v in raw["event_specific_modifiers"].items()
        }
        self._combos: list[_LayerStageCombo] = [
            _LayerStageCombo.model_validate(c) for c in raw["layer_stage_combination_rules"]
        ]
        # stage → group
        self._stage_group: dict[TwelveStage, str] = {}
        for gkey, g in raw["stage_groups"].items():
            for s in g["stages"]:
                self._stage_group[TwelveStage(s)] = gkey

    @staticmethod
    def stage_of(pillar: LuckPillar) -> TwelveStage | None:
        """운 기둥의 12운성(한글)을 enum으로."""
        return TWELVE_STAGE_KO_TO_KEY.get(pillar.twelve_unseong or "")

    def apply(
        self,
        candidates: list[EventCandidateV2],
        stage_by_layer: dict[LuckLayer, TwelveStage],
    ) -> list[EventCandidateV2]:
        """후보별로 source_layer들의 12운성을 적용해 점수·event_phase를 보정한다."""
        out: list[EventCandidateV2] = []
        for c in candidates:
            ek = str(c.event_key)
            spec = self._event_specific.get(ek)
            delta = 0
            phase: str | None = None
            chosen_stage: TwelveStage | None = None
            # 우선순위(사건 성숙도): 세운 > 월운 > 대운 > 일운.
            for layer in (LuckLayer.SEWOON, LuckLayer.WOLWOON, LuckLayer.DAEWOON, LuckLayer.ILWOON):
                if layer not in c.source_layers or layer not in stage_by_layer:
                    continue
                stage = stage_by_layer[layer]
                rule = self._stage.get(stage)
                if rule is None:
                    continue
                mag = abs(rule.score_modifier)
                # 이벤트별 boost/reduce 우선, 없으면 stage의 good_for/caution_for.
                if (spec and stage in spec.boost_stages) or ek in rule.good_for:
                    delta += mag
                elif (spec and stage in spec.reduce_stages) or ek in rule.caution_for:
                    delta -= mag
                else:
                    delta += rule.score_modifier  # 중립 — 단계 기본 부호
                if chosen_stage is None:  # 가장 우선되는 층의 단계를 대표로.
                    chosen_stage, phase = stage, rule.event_phase

            delta += self._combo_bonus(ek, stage_by_layer)
            delta = max(-_STAGE_DELTA_CAP, min(_STAGE_DELTA_CAP, delta))

            reasons = [*c.reason_codes]
            if chosen_stage is not None:
                reasons.append(f"stage:{chosen_stage.value}")
            new = c.model_copy(update={
                "score": max(0, min(100, c.score + delta)),
                "twelve_stage": chosen_stage,
                "event_phase": phase,
                "reason_codes": reasons,
            })
            out.append(new)
        return sorted(out, key=lambda x: -x.score)

    def _combo_bonus(self, event_key: str, stage_by_layer: dict[LuckLayer, TwelveStage]) -> int:
        """대운·세운 단계 그룹 조합(layer_stage_combination_rules) 보너스."""
        bonus = 0
        dw = stage_by_layer.get(LuckLayer.DAEWOON)
        sw = stage_by_layer.get(LuckLayer.SEWOON)
        dw_group = self._stage_group.get(dw) if dw else None
        sw_group = self._stage_group.get(sw) if sw else None
        for combo in self._combos:
            cond = combo.condition
            ok = True
            if "daewoon_stage_group" in cond:
                ok = ok and dw_group == cond["daewoon_stage_group"]
            if "sewoon_stage_group" in cond:
                ok = ok and sw_group == cond["sewoon_stage_group"]
            if "sewoon_stage" in cond:
                ok = ok and sw is not None and sw.value == cond["sewoon_stage"]
            if ok and (not combo.good_for or event_key in combo.good_for):
                bonus += combo.score_bonus
        return bonus
