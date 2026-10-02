"""위험 family 단위 보조 증폭 층(P2, 2026-09-18 데굴님 결정).

위험 사전 항목(risks/*.json)은 scope별 감수 해시로 잠겨 있어 룰을 고치면 감수가 강등된다.
이 층은 항목을 건드리지 않고, **이미 생성된 후보**에 배경 신호를 AMPLIFIER 근거(source
``aux:<id>``)와 ``aux_bonus``(상한 ``risk_scoring._AUX_MAX_BONUS``)로 덧붙인다.

원칙:
- 신살·구조·합 배경은 독립 트리거가 아니다(RISK_ENGINE.md §3-1). 항목마다 흉 극성
  (GI/GI_STRONG/HAN_BAD) 조건이 필수이며 극성 단독·배경 단독 증폭은 사전 lint가 막는다.
- 후보 신설·삭제 없음. 적격 상태·원인 수·persistence·episode identity·protection 불변.
  rankable/structural 우선도만 ``timed_base × (1 + aux_bonus)``로 소폭 보정된다.
- 사실은 만세력 산출(원국 신살 full_list·운 신살 luck_sinsal)과 기존 판정 함수(구조 배경
  플래그·합 완화)를 그대로 읽는다 — 여기서 명리를 재계산하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from saju_manse_analysis.relations.hap_mitigation import resolve_hap_mitigation
from saju_manse_analysis.structure.luck_structure_flags import resolve_luck_structure_flags

from saju_shared_types.luck import LuckPillar
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.risk_engine import EvidenceRole, RiskCandidate, RiskEvidence

from .dictionaries import (
    AUX_ADVERSE_POLARITY_ROLES,
    RiskAuxiliaryAmplifierFile,
    RiskAuxiliaryAmplifierItem,
)
from .risk_engine import rebuild_risk_candidate
from .risk_scoring import _AUX_MAX_BONUS

AUX_DICTIONARY_NAME = "risk_auxiliary_amplifiers.json"
AUX_SOURCE_GROUP = "auxiliary"


@dataclass(frozen=True)
class AuxiliaryFacts:
    """한 시점의 보조 배경 사실 — 극성·원국 신살·운 신살·구조 플래그·합 플래그."""

    polarity_role: str
    natal_sinsal: frozenset[str]
    luck_sinsal: frozenset[str]
    structure_flags: frozenset[str]
    hap_flags: frozenset[str]


@lru_cache(maxsize=8)
def load_auxiliary_amplifiers(dictionaries_dir: Path) -> tuple[RiskAuxiliaryAmplifierItem, ...]:
    """보조 증폭 사전 로드(경로 캐시). 파일이 없으면 빈 튜플(fresh-clone graceful)."""
    path = Path(dictionaries_dir) / AUX_DICTIONARY_NAME
    if not path.exists():
        return ()
    import json

    file = RiskAuxiliaryAmplifierFile.model_validate(json.loads(path.read_text("utf-8")))
    return tuple(file.items)


def auxiliary_labels(dictionaries_dir: Path) -> dict[str, str]:
    """룰 id → 한글 라벨(표현 계층 공급용)."""
    return {it.id: it.label_ko for it in load_auxiliary_amplifiers(Path(dictionaries_dir))}


def build_auxiliary_facts(
    result: ManseV2Result,
    target: LuckPillar,
    fav_map: dict[str, str],
    *,
    polarity_role: str,
) -> AuxiliaryFacts:
    """만세력 산출·기존 판정 함수에서 보조 사실을 읽는다(재계산 금지)."""
    natal: set[str] = set()
    extras = result.traditional_extras
    if extras is not None and extras.sinsal is not None:
        natal = {s.name for s in extras.sinsal.full_list}
    luck = {s.name for s in (target.luck_sinsal or [])}
    structure: set[str] = set()
    hap: set[str] = set()
    if result.pillars is not None:
        geok = result.geokguk.main_structure if result.geokguk is not None else None
        special = result.geokguk.special_pattern if result.geokguk is not None else None
        try:
            fl = resolve_luck_structure_flags(
                result.pillars, fav_map, luck_stem=target.stem, luck_branch=target.branch,
                geok_name=geok, luck_ten_gods=(target.stem_ten_god, target.branch_ten_god),
                special_pattern=special,
            )
        except (KeyError, ValueError):
            fl = None
        if fl is not None:
            if fl.luck_gaedu:
                structure.add("luck_gaedu")
            if fl.luck_jeolgak:
                structure.add("luck_jeolgak")
            if fl.chunggeun_useful:
                structure.add("chunggeun_useful")
            if fl.tonggwan_absent:
                structure.add("tonggwan_absent")
            if fl.rescue_damaged:
                structure.add("rescue_damaged")
            if fl.special_breach:
                structure.add("special_breach")
        try:
            mit = resolve_hap_mitigation(
                result.pillars, fav_map, luck_stem=target.stem, luck_branch=target.branch,
            )
        except (KeyError, ValueError):
            mit = None
        if mit is not None:
            for name in ("stem_harmed", "branch_harmed", "stem_mitigated", "branch_mitigated"):
                if getattr(mit, name):
                    hap.add(name)
    return AuxiliaryFacts(
        polarity_role=polarity_role,
        natal_sinsal=frozenset(natal),
        luck_sinsal=frozenset(luck),
        structure_flags=frozenset(structure),
        hap_flags=frozenset(hap),
    )


def _item_matches(
    item: RiskAuxiliaryAmplifierItem, c: RiskCandidate, facts: AuxiliaryFacts,
) -> bool:
    """대상(family/risk_id) AND 흉 극성 AND 명시된 배경 조건 전부(목록 안은 OR)."""
    if item.risk_family_in and c.risk_family not in item.risk_family_in:
        if c.risk_id not in item.risk_id_in:
            return False
    elif item.risk_id_in and c.risk_id not in item.risk_id_in:
        return False
    if facts.polarity_role not in item.polarity_role_in:
        return False
    if facts.polarity_role not in AUX_ADVERSE_POLARITY_ROLES:  # 사전 lint와 이중 방어
        return False
    checks = (
        (item.natal_sinsal_in, facts.natal_sinsal),
        (item.luck_sinsal_in, facts.luck_sinsal),
        (item.structure_in, facts.structure_flags),
        (item.hap_in, facts.hap_flags),
    )
    specified = [(want, have) for want, have in checks if want]
    if not specified:
        return False
    return all(set(want) & have for want, have in specified)


def apply_auxiliary_amplifiers(
    candidates: list[RiskCandidate],
    facts: AuxiliaryFacts,
    *,
    dictionaries_dir: Path,
    items: tuple[RiskAuxiliaryAmplifierItem, ...] | None = None,
) -> list[RiskCandidate]:
    """후보 목록에 보조 증폭 근거·aux_bonus를 덧붙인 사본을 돌려준다(순수 함수, 순서 보존).

    매칭 없는 후보는 같은 객체 그대로(byte 불변). 매칭 후보는 rebuild_risk_candidate로
    evidence 뒤에 aux:* AMPLIFIER 근거를 추가하고 aux_bonus = MAX × (1 − Π(1 − s))로 채운다.
    """
    rules = items if items is not None else load_auxiliary_amplifiers(Path(dictionaries_dir))
    if not rules or facts.polarity_role not in AUX_ADVERSE_POLARITY_ROLES:
        return list(candidates)
    out: list[RiskCandidate] = []
    for c in candidates:
        matched = [it for it in rules if _item_matches(it, c, facts)]
        if not matched:
            out.append(c)
            continue
        existing = {e.code for e in c.evidence if e.source.startswith("aux:")}
        added: list[RiskEvidence] = []
        acc = 1.0
        for it in matched:
            acc *= 1.0 - it.strength
            if it.id in existing:
                continue
            added.append(RiskEvidence(
                evidence_id=f"{c.period_key}|aux:{it.id}",
                code=it.id,
                period_key=c.period_key,
                layer="period",
                source=f"aux:{it.id}",
                strength=it.strength,
                role=EvidenceRole.AMPLIFIER,
                source_group=AUX_SOURCE_GROUP,
                target_domain=c.domain,
            ))
        bonus = round(min(_AUX_MAX_BONUS, _AUX_MAX_BONUS * (1.0 - acc)), 6)
        out.append(rebuild_risk_candidate(c, update={
            "evidence": [*c.evidence, *added],
            "aux_bonus": max(c.aux_bonus, bonus),
        }))
    return out
