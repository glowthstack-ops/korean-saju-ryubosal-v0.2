"""위험 탐지 엔진 R0 — 원시 신호 → 원자 위험 후보 생성 (doc/v2_2/RISK_ENGINE.md).

기회 파이프라인(EventEngineV2 6계층)과 독립이다. 입력은 **reducer·모디파이어 이전의 원시
신호 스냅샷(RawPeriodFacts)** — 감점·quality flip·floor·Top-N을 거친 최종 후보를 소비하면
위험 근거가 이미 손실되므로 금지한다(2026-07-15 데굴님 승인 조건 1).

R0 책임 범위: 사전 룰 매칭 → 근거(provenance) 수집 → minimum_evidence 게이트 → 원자
RiskCandidate 생성까지. 점수(6축)·기간 병합(RiskEpisode)·risk_level·사용자 노출은 하지
않는다(R1/R2/R3). 결과는 shadow 사이드채널 전용 — LLM 입력에 주입하지 않는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from saju_shared_types.event_engine import (
    TEN_GOD_GROUP,
    LuckLayer,
    Pillar4,
    PolarityRole,
    RelationKind,
    TenGod,
    TwelveStage,
)
from saju_shared_types.risk_engine import (
    EligibilityStatus,
    EvidenceRole,
    ExposureStatus,
    RiskCandidate,
    RiskDomain,
    RiskEvidence,
    RiskKind,
    dedupe_evidence,
    independent_source_count,
)

from .dictionaries import RiskItem, RiskMappingFile, RiskRuleSpec

# 극성 사실은 특정 운 층위가 아니라 시점(기간) 전체의 판정이다 — 근거 layer 표기용.
_PERIOD_LAYER = "period"


@dataclass(frozen=True)
class RelationFact:
    """시점의 관계 발동 원시 사실 1건(합충형파해·복음, 자극 궁성·피자극 십성 포함).

    target_ten_god: 원국 피자극 글자의 십성 — 충·형·공망은 존재만으로 위험 도메인을 못
    정하므로(재성 충 ≠ 배우자궁 충 ≠ 사회궁 충) '무엇을 쳤는가'를 근거에 보존한다
    (2026-07-15 감수 — R0 근거 정확도 문제). 일간 등 십성 미정의는 None.
    """

    kind: RelationKind
    palace: Pillar4
    position: str = "branch"  # 'stem' | 'branch'
    target_ten_god: TenGod | None = None  # 피자극 글자(궁성의 천간/지지 본기) 십성


@dataclass(frozen=True)
class RawPeriodFacts:
    """한 시점의 원시 신호 스냅샷 — 위험 엔진 전용 입력 (Raw Signal Ledger 단위).

    EventEngineV2._score_target이 모디파이어 적용 **이전** 재료(신호·관계 적중·시점 극성·
    운성·공망)에서 그대로 구성한다. 긍정 후보가 하나도 없어도 위험 근거는 남는다.
    """

    period_key: str  # '2026' / '2026-09' 등 운 기간 라벨
    layer: LuckLayer  # 채점 대상 층위(세운/월운/일운/대운)
    ten_god_layers: dict[TenGod, frozenset[LuckLayer]]  # 유입 십성 → 관측 층위들
    relations: tuple[RelationFact, ...]  # 관계 발동 사실(공망류 제외)
    void_active: bool  # 공망 활성(충발·해공 포함 상태 아님 — 활성 여부만)
    polarity_role: PolarityRole  # 시점 유입 글자의 용기신 극성(化/制 반영)
    twelve_stage: TwelveStage | None  # 대상 기둥 지지 12운성


_ROLE_SECTIONS: tuple[tuple[EvidenceRole, str], ...] = (
    (EvidenceRole.TRIGGER, "trigger_rules"),
    (EvidenceRole.AMPLIFIER, "amplifier_rules"),
    (EvidenceRole.MITIGATOR, "mitigator_rules"),
    (EvidenceRole.BLOCKER, "blocker_rules"),
)


@dataclass(frozen=True)
class _Match:
    """룰 매칭 결과 — 원인 사실 서명과 부가 정보."""

    source: str  # 원인 사실 서명(독립 출처·중복 방지 키)
    layer: str  # 근거 층위 표기
    palace: str | None  # 자극 궁성(관계 조건일 때)


class RiskEngine:
    """risks/ 사전을 로드해 원시 신호 스냅샷에서 원자 위험 후보를 생성한다."""

    def __init__(self, dictionaries_dir: Path) -> None:
        """risks/<domain>.json 전체를 로드한다.

        Args:
            dictionaries_dir: 사전 원본 루트(backend/dictionaries).

        Raises:
            FileNotFoundError: risks/ 디렉토리가 없을 때(호출부가 graceful 처리).
        """
        risks_dir = dictionaries_dir / "risks"
        if not risks_dir.is_dir():
            raise FileNotFoundError(f"위험 사전 디렉토리 없음: {risks_dir}")
        self._items: list[RiskItem] = []
        for path in sorted(risks_dir.glob("*.json")):
            file = RiskMappingFile.model_validate(
                json.loads(path.read_text(encoding="utf-8"))
            )
            self._items.extend(file.items)

    # ── 공개 API ─────────────────────────────────────────────────

    def generate(
        self,
        facts: RawPeriodFacts,
        exposure_status: ExposureStatus = ExposureStatus.UNKNOWN,
    ) -> list[RiskCandidate]:
        """한 시점의 원시 신호에서 원자 위험 후보를 생성한다.

        생성 조건(minimum_evidence): trigger 근거 수(중복 제거 후) ≥ trigger_count AND
        독립 출처 수 ≥ independent_source_count AND 필수 그룹(required_groups — 사건
        형태/대상 활성 등)별 trigger 근거 ≥ 1. '약한 범용 신호 N개'와 '사건 형태 + 대상
        활성'을 구분해 신호 1개·범용 신호만의 범람을 사전 게이트로 막는다.

        불변식(2026-07-15 감수): blocker 근거는 후보 기록을 삭제하지 않되
        eligibility_status=BLOCKED로 분리한다 — 근거 연구용으로 보존하고, 활성 위험
        집계(R2 슬롯·R4 오경고 분모)에서는 제외 가능해야 한다. mitigator는 후보 유지 +
        MITIGATED 표시(강도 하향은 R1).

        Args:
            facts: 원시 신호 스냅샷.
            exposure_status: 사용자 노출 상태 — R0 기본 UNKNOWN(프로필 배선은 R1/R5).
                미입력을 숫자 중간값으로 대체하지 않는다.

        Returns:
            생성된 원자 RiskCandidate 목록(점수·등급 미산출 상태).
        """
        out: list[RiskCandidate] = []
        for item in self._items:
            evidences: list[RiskEvidence] = []
            for role, section in _ROLE_SECTIONS:
                rules: list[RiskRuleSpec] = getattr(item, section)
                for rule in rules:
                    m = self._match(rule, facts)
                    if m is None:
                        continue
                    evidences.append(RiskEvidence(
                        evidence_id=f"{facts.period_key}|{m.source}",
                        code=rule.id,
                        period_key=facts.period_key,
                        layer=m.layer,
                        source=m.source,
                        strength=rule.strength,
                        role=role,
                        source_group=rule.group,
                        target_domain=RiskDomain(item.domain),
                        target_palace=m.palace,
                    ))
            evidences = dedupe_evidence(evidences)
            triggers = [e for e in evidences if e.role is EvidenceRole.TRIGGER]
            if len(triggers) < item.minimum_evidence.trigger_count:
                continue
            if independent_source_count(evidences) < (
                item.minimum_evidence.independent_source_count
            ):
                continue
            trigger_groups = {e.source_group for e in triggers}
            if any(
                g not in trigger_groups
                for g in item.minimum_evidence.required_groups
            ):
                continue
            blockers = [e for e in evidences if e.role is EvidenceRole.BLOCKER]
            if blockers:
                status = EligibilityStatus.BLOCKED
            elif any(e.role is EvidenceRole.MITIGATOR for e in evidences):
                status = EligibilityStatus.MITIGATED
            else:
                status = EligibilityStatus.MATCHED
            out.append(RiskCandidate(
                risk_id=item.risk_id,
                domain=RiskDomain(item.domain),
                kind=RiskKind(item.kind),
                period_key=facts.period_key,
                manifestation_ids=[m.id for m in item.manifestations],
                evidence=evidences,
                score_components=None,  # R1에서 산출
                exposure_status=exposure_status,
                confidence=0.0,  # R1에서 산출
                eligibility_status=status,
                suppression_reasons=[e.code for e in blockers],
            ))
        return out

    # ── 룰 매칭 ───────────────────────────────────────────────────

    def _match(self, rule: RiskRuleSpec, facts: RawPeriodFacts) -> _Match | None:
        """룰 조건(전부 AND)을 원시 사실과 대조한다. 통과 시 원인 사실 서명을 만든다.

        source(서명)는 매칭 **룰**이 아니라 바탕 **사실**을 표현한다 — 서로 다른 룰이 같은
        사실을 잡으면 서명이 같아 evidence_id 중복 제거·독립 출처 1개 계산이 성립한다.
        """
        parts: list[str] = []
        layers: list[str] = []
        palace: str | None = None

        if rule.ten_god is not None:
            god = TenGod(rule.ten_god)
            god_layers = facts.ten_god_layers.get(god)
            if not god_layers:
                return None
            parts.append(f"ten_god:{god.value}")
            layers.append("+".join(sorted(la.value for la in god_layers)))

        if rule.ten_god_group is not None:
            matched = sorted(
                g.value for g in facts.ten_god_layers
                if TEN_GOD_GROUP[g].value == rule.ten_god_group
            )
            if not matched:
                return None
            parts.append("ten_god:" + "+".join(matched))
            group_layers = {
                la.value
                for g in facts.ten_god_layers
                if TEN_GOD_GROUP[g].value == rule.ten_god_group
                for la in facts.ten_god_layers[g]
            }
            layers.append("+".join(sorted(group_layers)))

        if rule.relation is not None:
            kind = RelationKind(rule.relation)
            hits = [
                r for r in facts.relations
                if r.kind is kind and (
                    rule.relation_palace is None
                    or r.palace.value == rule.relation_palace
                )
            ]
            # 대상 조건 — '무엇을 충·형했는가'(피자극 십성). 충·형은 존재만으로 도메인을
            # 못 정하므로 대상 필터가 있으면 피자극 십성/십성군이 일치하는 발동만 남긴다.
            if rule.relation_target_ten_god is not None:
                want = TenGod(rule.relation_target_ten_god)
                hits = [r for r in hits if r.target_ten_god is want]
            if rule.relation_target_ten_god_group is not None:
                hits = [
                    r for r in hits
                    if r.target_ten_god is not None
                    and TEN_GOD_GROUP[r.target_ten_god].value == (
                        rule.relation_target_ten_god_group
                    )
                ]
            if not hits:
                return None
            palaces = sorted({r.palace.value for r in hits})
            sig = f"relation:{kind.value}:" + "+".join(palaces)
            # 피자극 십성을 서명에 **항상** 포함 — 대상 조건이 있는 룰과 없는 룰이 같은
            # 충을 잡았을 때 서명이 갈라져 독립 출처가 부풀려지는 것을 막는다(같은 원인
            # 사실 = 같은 서명). 대상이 다르면 실제로 다른 글자를 친 다른 사실이다.
            gods = sorted({
                r.target_ten_god.value for r in hits if r.target_ten_god is not None
            })
            if gods:
                sig += ":" + "+".join(gods)
            parts.append(sig)
            layers.append(facts.layer.value)
            palace = palaces[0] if len(palaces) == 1 else None

        if rule.polarity_role_in is not None:
            if facts.polarity_role.value not in rule.polarity_role_in:
                return None
            parts.append(f"polarity:{facts.polarity_role.value}")
            layers.append(_PERIOD_LAYER)

        if rule.void_active is not None:
            if facts.void_active != rule.void_active:
                return None
            parts.append("void" if rule.void_active else "no_void")
            layers.append(_PERIOD_LAYER)

        if rule.twelve_stage_in is not None:
            if facts.twelve_stage is None:
                return None
            if facts.twelve_stage.value not in rule.twelve_stage_in:
                return None
            parts.append(f"stage:{facts.twelve_stage.value}")
            layers.append(facts.layer.value)

        if not parts:  # 무조건 룰은 스키마에서 거부되지만 방어적으로 차단.
            return None
        return _Match(
            source="&".join(parts),
            layer="&".join(dict.fromkeys(layers)),
            palace=palace,
        )


def build_raw_period_facts(
    *,
    period_key: str,
    layer: LuckLayer,
    ten_god_layers: dict[TenGod, set[LuckLayer]],
    relations: list[RelationFact],
    void_active: bool,
    polarity_role: PolarityRole,
    twelve_stage: TwelveStage | None,
) -> RawPeriodFacts:
    """원시 사실 재료 → RawPeriodFacts 스냅샷(불변화)."""
    return RawPeriodFacts(
        period_key=period_key,
        layer=layer,
        ten_god_layers={g: frozenset(ls) for g, ls in ten_god_layers.items()},
        relations=tuple(relations),
        void_active=void_active,
        polarity_role=polarity_role,
        twelve_stage=twelve_stage,
    )


__all__ = [
    "RawPeriodFacts",
    "RelationFact",
    "RiskEngine",
    "build_raw_period_facts",
]
