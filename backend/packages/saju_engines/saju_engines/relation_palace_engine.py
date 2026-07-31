"""RelationPalaceEngine (Phase 6) — 합충형파해·궁성으로 사건화 여부와 생활 영역을 보정한다.

relation_palace_modifier.json: 관계 종류(HAP/CHUNG/HYEONG/PA/HAE) 발동 보너스 × 궁성 활성 가중 ×
운층 가중. 자극된 궁(년/월/일/시)의 event_domains에 맞는 후보를 강화하고 palace를 부여한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from saju_shared_types.event_engine import (
    EventCandidateV2,
    LuckLayer,
    Pillar4,
    RelationKind,
)
from saju_shared_types.ganji_calendar import RELATION_ID_SHAPE, RelationIdShape

from .marriage_hap_subtype import mt4_subtype_multiplier, partner_elements

# MT4 합 종류 재가중 적용 대상 — 관계/결혼 도메인 한정(타 도메인 합은 항상 ×1.0).
_MT4_DOMAIN = frozenset({"new_relationship", "marriage_signal", "relationship_change"})


@dataclass
class RelationActivation:
    """운이 원국 궁을 자극한 관계 1건."""

    kind: RelationKind
    palace: Pillar4
    layer: LuckLayer
    position: str = "branch"  # 'stem' | 'branch'
    # ── 관측 가능성(2026-07-31) ────────────────────────────────────────
    # `REL_{kind}_{palace}` 코드에는 어느 운 층위·어느 글자가 발동시켰는지가 없다.
    # 그래서 서로 다른 발동이 같은 문자열로 기록되고 "같은 근거 중복" 으로 오독된다
    # (WC-SCORE 감사에서 72건 중 18건). 점수·코드는 그대로 두고 식별 정보만 담는다.
    relation_id: str = ""      # 사전 키 형태 안정 식별자(예: rel_branch_clash_午_子)
    luck_stem: str = ""        # 발동시킨 운 천간
    luck_branch: str = ""      # 발동시킨 운 지지
    natal_stem: str = ""       # 관계에 참여한 원국 천간
    natal_branch: str = ""     # 관계에 참여한 원국 지지
    # MT4(MARRIAGE_TIMING_ENHANCEMENT §9): HAP은 RelationKind로 유지하되 원 합 종류를 곁들인다.
    # 'six_harmony'|'three_harmony'|'directional'|'stem'|None. element=삼합/방합 완성 오행(한자).
    hap_subtype: str | None = None
    element: str | None = None


_MAX_RELATION_DELTA = 22.0  # 발동 보너스 총량 상한(포화 보정 — reviewed:false)


def relation_source_identity(act: RelationActivation) -> str:
    """발동 1건의 **안정 식별자**. 배열 순서나 객체 id 를 쓰지 않는다.

    입력 의미에서만 결정된다 — 같은 실행이든 다른 실행이든 같은 발동은 같은 값이다.
    같은 층위·같은 운 글자에서 독립 발동이 여럿일 수 있으므로 원국 글자까지 넣는다.
    """
    return "|".join((
        "REL", act.kind.value, act.palace.value, act.layer.value, act.position,
        act.luck_stem or "-", act.luck_branch or "-",
        act.natal_stem or "-", act.natal_branch or "-",
        act.relation_id or "-",
    ))


def relation_reason_instance(
    act: RelationActivation, contribution: float
) -> dict[str, object]:
    """`reason_codes` 한 항목에 대응하는 구조화 provenance.

    사람이 읽을 수 있는 원필드를 그대로 보존한다 — 해시만 남기면 감사에서 다시
    역추적할 수 없다.
    """
    return {
        "reason_code": f"REL_{act.kind.value}_{act.palace.value}",
        "source_identity": relation_source_identity(act),
        "source_layer": act.layer.value,
        "natal_pillar": act.palace.value,
        "relation_kind": act.kind.value,
        "position": act.position,
        "transit_ganzhi": f"{act.luck_stem}{act.luck_branch}".strip() or None,
        "natal_ganzhi": f"{act.natal_stem}{act.natal_branch}".strip() or None,
        "relation_id": act.relation_id or None,
        "contribution": round(float(contribution), 4),
    }


#: 합충형파해 RelationType 에 없어 엔진이 합성한 발동의 relation_id. 운 지지 == 원국
#: 지지가 성립 조건이므로 피연산자 비교 대신 두 글자의 동일성만 본다.
_SYNTHETIC_RELATION_IDS = frozenset({"bokeum_day_branch"})

#: 형태표 조회용 — relation_id 는 RelationType 의 **값** 을 담는다.
_SHAPE_BY_RTYPE: dict[str, RelationIdShape] = {
    str(rt.value): shape for rt, shape in RELATION_ID_SHAPE.items()
}


@dataclass(frozen=True)
class OperandConsistency:
    """발동 1건의 피연산자 정합 판정. `reason` 은 위반일 때만 채워진다."""

    valid: bool
    relation_shape: str
    reason: str | None = None


def _split_relation_id(relation_id: str) -> tuple[str, tuple[str, ...]] | None:
    """`rel_{종류}_{피연산자...}` → (종류, 피연산자들). 인식 실패는 None.

    RelationType 값 자체가 '_' 를 포함하므로(`three_harmony_contrib` 등) 단순 split 이
    아니라 **최장 접두 일치** 로 종류를 떼어낸다.
    """
    if not relation_id.startswith("rel_"):
        return None
    body = relation_id[4:]
    for rtype in sorted(_SHAPE_BY_RTYPE, key=len, reverse=True):
        if body == rtype:
            return (rtype, ())
        if body.startswith(rtype + "_"):
            return (rtype, tuple(body[len(rtype) + 1:].split("_")))
    return None


def relation_operand_consistency(act: RelationActivation) -> OperandConsistency:
    """`relation_id` 의 피연산자가 발동에 기록된 운·원국 글자와 맞는가.

    source identity 는 **결정론적이어도 의미가 틀릴 수 있다** — luck_ref 를 한 hit 에서,
    relation_id 를 다른 hit 에서 가져오는 배선 오류는 값이 안정적이라 눈에 띄지 않는다.
    실제로 이 검사를 도입한 계기가 그런 조합이 담긴 fixture 였다(2026-07-31).

    감사·회귀 전용이다. 점수 계산 경로에서 호출하지 않으며 예외도 던지지 않는다.
    인식할 수 없는 relation_id 는 통과가 아니라 **위반**이다(fail-closed) — 관계 종류를
    추가하고 `RELATION_ID_SHAPE` 갱신을 빠뜨리면 그 종류만 조용히 무검증이 되기 때문이다.
    """
    rid = act.relation_id
    if not rid:
        return OperandConsistency(False, "MISSING", "relation_id 없음")
    if rid in _SYNTHETIC_RELATION_IDS:
        ok = bool(act.luck_branch) and act.luck_branch == act.natal_branch
        return OperandConsistency(
            ok, "SYNTHETIC",
            None if ok else f"합성 발동은 운·원국 지지가 같아야 한다: "
                            f"{act.luck_branch!r} != {act.natal_branch!r}",
        )
    parsed = _split_relation_id(rid)
    if parsed is None:
        return OperandConsistency(
            False, "UNRECOGNIZED",
            f"RELATION_ID_SHAPE 에 없는 관계 종류이거나 형식 밖: {rid!r}",
        )
    rtype, ops = parsed
    shape = _SHAPE_BY_RTYPE[rtype]

    def bad(msg: str) -> OperandConsistency:
        return OperandConsistency(False, str(shape.value), f"{rid}: {msg}")

    if shape is RelationIdShape.STEM_PAIR:
        if len(ops) != 2:
            return bad(f"천간쌍은 피연산자 2개여야 한다(실제 {len(ops)})")
        if (ops[0], ops[1]) != (act.luck_stem, act.natal_stem):
            return bad(f"운·원국 천간 불일치: {ops} vs "
                       f"({act.luck_stem!r}, {act.natal_stem!r})")
    elif shape is RelationIdShape.BRANCH_PAIR:
        if len(ops) != 2:
            return bad(f"지지쌍은 피연산자 2개여야 한다(실제 {len(ops)})")
        if (ops[0], ops[1]) != (act.luck_branch, act.natal_branch):
            return bad(f"운·원국 지지 불일치: {ops} vs "
                       f"({act.luck_branch!r}, {act.natal_branch!r})")
    elif shape is RelationIdShape.MULTI_NATAL:
        # 삼형 1건은 natal_refs 여러 건으로 분해된다 — 개별 발동의 원국 글자는
        # 피연산자와 '같은' 게 아니라 그 안에 '포함'된다.
        if len(ops) != 2:
            return bad(f"삼형은 피연산자 2개여야 한다(실제 {len(ops)})")
        if ops[0] != act.luck_branch:
            return bad(f"운 지지 불일치: {ops[0]!r} != {act.luck_branch!r}")
        if not act.natal_branch or act.natal_branch not in ops[1]:
            return bad(f"원국 지지 {act.natal_branch!r} 가 피연산자 {ops[1]!r} 에 없다")
    elif shape is RelationIdShape.ELEMENT:
        # 두 번째 피연산자는 글자가 아니라 완성 오행이다.
        if len(ops) != 2:
            return bad(f"기여는 피연산자 2개여야 한다(실제 {len(ops)})")
        if ops[0] != act.luck_branch:
            return bad(f"운 지지 불일치: {ops[0]!r} != {act.luck_branch!r}")
        if act.element is not None and ops[1] != act.element:
            return bad(f"완성 오행 불일치: {ops[1]!r} != {act.element!r}")
    elif shape is RelationIdShape.SINGLE:
        if len(ops) != 1:
            return bad(f"자형은 피연산자 1개여야 한다(실제 {len(ops)})")
        if not (ops[0] == act.luck_branch == act.natal_branch):
            return bad(f"자형은 운·원국이 같은 글자여야 한다: {ops[0]!r} / "
                       f"{act.luck_branch!r} / {act.natal_branch!r}")
    else:  # pragma: no cover - 형태 추가 시 fail-closed
        return bad(f"미처리 형태 {shape!r}")
    return OperandConsistency(True, str(shape.value))


class RelationPalaceEngine:
    """관계·궁성 발동 보정."""

    def __init__(self, dictionaries_dir: Path) -> None:
        raw = json.loads(
            (dictionaries_dir / "event_engine" / "relation_palace_modifier.json").read_text(
                encoding="utf-8"
            )
        )
        self._rel_bonus: dict[str, int] = {
            k: int(v["base_event_score_bonus"]) for k, v in raw["relation_types"].items()
        }
        self._palace: dict[str, dict] = raw["palace_map"]
        self._rel_to_palace: list[dict] = raw["relation_to_palace_event_rules"]
        self._compounds: list[dict] = raw["compound_relation_patterns"]
        self._layer_w: dict[str, float] = {
            k: float(v["score_multiplier"]) for k, v in raw["relation_layer_weights"].items()
        }
        self._palace_mult: dict[str, dict] = raw["palace_relation_score_multipliers"]

    def apply(
        self,
        candidates: list[EventCandidateV2],
        activations: list[RelationActivation],
        *,
        mt4_mode: str = "off",
        gender: str = "unknown",
        day_element: str = "",
        shadow_sink: list[dict] | None = None,
    ) -> list[EventCandidateV2]:
        """후보에 관계·궁성 발동 보너스를 적용한다.

        MT4(§9): mt4_mode='off'면 기존 동작 그대로(byte 불변). 'shadow'면 관계 도메인 HAP 활성의
        합 종류(subtype) multiplier를 **계산만** 해 shadow_sink에 기록하고 점수·reason은 불변.
        'apply'면 합산 전 보너스에 multiplier를 곱하고(상향 없음 ≤1.0) MT4 reason을 단다.
        """
        kinds = {a.kind for a in activations}
        compound_bonus = self._compound_bonus(kinds)
        # (relation, palace) → likely_events 빠른 조회.
        rel_palace_events: dict[tuple[str, str], set[str]] = {}
        for r in self._rel_to_palace:
            key = (r["relation"], r["target_palace"])
            rel_palace_events.setdefault(key, set()).update(r["likely_events"])
        partner_els = partner_elements(day_element, gender) if mt4_mode != "off" else set()

        out: list[EventCandidateV2] = []
        for c in candidates:
            ek = str(c.event_key)
            best_palace: Pillar4 | None = c.palace
            delta = 0.0
            reasons = [*c.reason_codes]
            instances: list[dict[str, object]] = [*c.reason_instances]
            mt4_reasons: list[str] = []
            for act in activations:
                pinfo = self._palace[act.palace.value]
                in_domain = ek in pinfo["event_domains"]
                likely = ek in rel_palace_events.get((act.kind.value, act.palace.value), set())
                if not (in_domain or likely):
                    continue
                layer_mult = self._layer_w.get(f"{act.layer.value}_to_natal", 1.0)
                pmult = self._palace_mult[act.palace.value][act.position]
                bonus = self._rel_bonus[act.kind.value] * float(pinfo["activation_weight"])
                bonus *= layer_mult * pmult
                if likely:
                    bonus *= 1.2
                # MT4 — 관계 도메인 HAP 활성만 합 종류 재가중(상향 없음). off는 건너뜀.
                if mt4_mode != "off" and act.kind is RelationKind.HAP and ek in _MT4_DOMAIN:
                    mult, mt4_reason = mt4_subtype_multiplier(
                        act.hap_subtype,
                        on_spouse_palace=act.palace is Pillar4.DAY,
                        partner_element=bool(act.element) and act.element in partner_els,
                    )
                    if mt4_mode == "apply":
                        if mult != 1.0:
                            mt4_reasons.append(mt4_reason)
                        bonus *= mult
                    elif mt4_mode == "shadow" and shadow_sink is not None:
                        shadow_sink.append({
                            "event": ek, "palace": act.palace.value,
                            "hapSubtype": act.hap_subtype, "multiplier": mult,
                            "relation_original": round(bonus, 3),
                            "relation_mt4": round(bonus * mult, 3),
                            "relation_mt4_diff": round(bonus * mult - bonus, 3),
                            "reason": mt4_reason,
                        })
                delta += bonus
                best_palace = act.palace
                reasons.append(f"REL_{act.kind.value}_{act.palace.value}")
                # 병렬 provenance — 기존 `reason_codes` 는 값·순서·중복 모두 불변.
                instances.append(relation_reason_instance(act, bonus))
            if compound_bonus and best_palace is not None:
                delta += compound_bonus
                reasons.append("REL_COMPOUND")
            if mt4_mode == "apply" and mt4_reasons:
                reasons.extend(dict.fromkeys(mt4_reasons))  # 중복 제거·순서 보존
            if delta == 0 and c.palace is None:
                out.append(c)
                continue
            # 발동 보너스 총량 상한 — 다중 적중·복합이 점수를 100으로 포화시키는 것을 방지
            # (포화 보정, reviewed:false 초안). 발동 '여부'는 palace·confidence가 별도로 표현한다.
            delta = min(delta, _MAX_RELATION_DELTA)
            new_score = max(0, round(c.score + delta))  # 중간 100 클램프 제거 — raw 보존
            out.append(c.model_copy(update={
                "score": new_score,
                "palace": best_palace,
                "reason_codes": reasons,
                "reason_instances": instances,
                "contributions": {**c.contributions, "relation": float(new_score - c.score)},
            }))
        return sorted(out, key=lambda x: -x.score)

    def _compound_bonus(self, kinds: set[RelationKind]) -> int:
        """동시 발생 관계 조합(합+충, 형+충 등) 발동 보너스."""
        kset = {k.value for k in kinds}
        bonus = 0
        for comp in self._compounds:
            pat = comp.get("pattern", [])
            if all(p in kset for p in pat if p in {"HAP", "CHUNG", "HYEONG", "PA", "HAE"}) and any(
                p in {"HAP", "CHUNG", "HYEONG", "PA", "HAE"} for p in pat
            ):
                eff = comp.get("score_effect", {})
                bonus = max(bonus, int(eff.get("event_activation_bonus", 0)))
        return bonus
