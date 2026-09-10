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
        """후보별로 12운성을 적용해 점수·event_phase를 보정한다.

        **층 누적 제거(P1-a, 2026-09-10 사용자 승인)**: 이전에는 source_layer 마다 단계 보정을
        더해(세운 +12 + 월운 +15 + 대운 …) 후보 46% 가 상한 +18 에 붙었고 사(死)·병(病)·절(絶)
        조차 과반이 양수였다(40명식 ablation — EVENT_SCORING_3LAYER_PROPOSAL §3). 이제
        **사건 성숙도 우선 층 하나**(세운 > 월운 > 대운 > 일운 — phase 를 정하던 층과 동일)의
        단계 보정만 `stage` 로 싣고, 대운×세운 조합 보너스는 별도 기여 `stage_combo` 로
        분리한다(각각 ±cap). 실측: 포화 45.5%→0%, 스테이지 평균 제왕 +11.1 … 절 −5.3(사전
        `score_modifier` 의도대로), 기간별 top 변경 23.9%.
        """
        out: list[EventCandidateV2] = []
        for c in candidates:
            ek = str(c.event_key)
            spec = self._event_specific.get(ek)
            delta = 0
            phase: str | None = None
            chosen_stage: TwelveStage | None = None
            # 우선순위(사건 성숙도): 세운 > 월운 > 대운 > 일운 — 첫 성립 층만 적용.
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
                    delta = mag
                elif (spec and stage in spec.reduce_stages) or ek in rule.caution_for:
                    delta = -mag
                else:
                    delta = rule.score_modifier  # 중립 — 단계 기본 부호
                chosen_stage, phase = stage, rule.event_phase
                break

            # 상한은 문서 불변식대로 **합계** ±cap(단계 + 조합). 기여는 stage/stage_combo 로 분리.
            stage_part = max(-_STAGE_DELTA_CAP, min(_STAGE_DELTA_CAP, delta))
            combo_raw = self._combo_bonus(ek, stage_by_layer, c.source_layers)
            total = max(-_STAGE_DELTA_CAP, min(_STAGE_DELTA_CAP, stage_part + combo_raw))
            combo = total - stage_part

            reasons = [*c.reason_codes]
            if chosen_stage is not None:
                reasons.append(f"stage:{chosen_stage.value}")
            if combo:
                reasons.append("stage_combo")
            new_score = max(0, c.score + total)  # 중간 100 클램프 제거 — raw 누적 보존
            contributions = {**c.contributions, "stage": float(stage_part)}
            if combo:
                contributions["stage_combo"] = float(combo)
            new = c.model_copy(update={
                "score": new_score,
                "twelve_stage": chosen_stage,
                "event_phase": phase,
                "reason_codes": reasons,
                "contributions": contributions,
            })
            out.append(new)
        return sorted(out, key=lambda x: -x.score)

    #: 조합 규칙 condition 키 → (층, 비교 종류). 사전에 있는 키를 **전부** 평가한다.
    _COND_KEYS: dict[str, tuple[LuckLayer, str]] = {
        "daewoon_stage_group": (LuckLayer.DAEWOON, "group"),
        "sewoon_stage_group": (LuckLayer.SEWOON, "group"),
        "wolwoon_stage_group": (LuckLayer.WOLWOON, "group"),
        "ilwoon_stage_group": (LuckLayer.ILWOON, "group"),
        "daewoon_stage": (LuckLayer.DAEWOON, "stage"),
        "sewoon_stage": (LuckLayer.SEWOON, "stage"),
        "wolwoon_stage": (LuckLayer.WOLWOON, "stage"),
        "ilwoon_stage": (LuckLayer.ILWOON, "stage"),
    }

    def _combo_bonus(
        self,
        event_key: str,
        stage_by_layer: dict[LuckLayer, TwelveStage],
        source_layers: list[LuckLayer] | None = None,
    ) -> int:
        """운 층 단계 조합(layer_stage_combination_rules) 보너스.

        2026-09-10 P1-a 결함 수정: 이전에는 대운·세운 조건만 평가하고 월운·일운·
        `sewoon_has_event_candidate` 조건은 **무시**해, 그 조건만 가진
        `SEWOON_EVENT_WOLWOON_ILWOON_TRIGGER`(+8, 전 사건)가 모든 후보에 무조건 붙었다
        (12운성 보정이 항상 양수·상한 포화가 된 두 번째 원인). 이제 condition 의 모든 키를
        평가하고, 알 수 없는 키는 성립하지 않는 것으로 본다(fail-closed).
        """
        bonus = 0
        for combo in self._combos:
            cond = combo.condition
            ok = True
            for key, want in cond.items():
                if key == "sewoon_has_event_candidate":
                    has = LuckLayer.SEWOON in (source_layers or [])
                    ok = ok and (has == bool(want))
                    continue
                spec = self._COND_KEYS.get(key)
                if spec is None:
                    ok = False  # 사전이 낸 조건을 코드가 모르면 보너스를 주지 않는다
                    break
                layer, kind = spec
                st = stage_by_layer.get(layer)
                if st is None:
                    ok = False
                    break
                if kind == "group":
                    ok = ok and self._stage_group.get(st) == want
                else:
                    ok = ok and st.value == want
                if not ok:
                    break
            if ok and (not combo.good_for or event_key in combo.good_for):
                bonus += combo.score_bonus
        return bonus
