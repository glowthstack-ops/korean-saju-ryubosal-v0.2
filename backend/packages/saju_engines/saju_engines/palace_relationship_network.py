"""궁위 관계망 분석 (Palace Relationship Network, P3, 2026-07-01).

SSOT: doc/v2_2/RELATIONSHIP_READING.md §3. 연(조상·사회 배경)·월(부모·성장환경)·일(배우자·친밀)·
시(자식·결과) 궁위 간 합충형파해원진과 궁위 공망을 감지해 **중립 설명 context**로 제공한다.
P4 관계질 라벨 사전을 재사용하며, **점수·confidence·후보 생성을 변경하지 않는다(inert)**. 조부모
육아·공공사업 같은 구체 발현은 질문 intent가 맞을 때만 조건부로 노출한다(단정 금지).
"""

from __future__ import annotations

from saju_manse_analysis.sinsal.sinsal_catalog import WONJIN

from saju_shared_types.constants import (
    BRANCH_BREAKS,
    BRANCH_CLASHES,
    BRANCH_HARMS,
    PUNISHMENT_MUTUAL,
    PUNISHMENT_TRIPLES,
    SELF_PUNISHMENT,
    SIX_COMBINATIONS,
    THREE_HARMONY,
)
from saju_shared_types.enums import Branch
from saju_shared_types.intent import Domain
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.palace_network import PalaceNetwork, PalacePairRelation

from .relationship_relation_labels import relation_summary_ko

# 궁위 역할(한글) — 연·월·일·시.
_PALACE_ROLES: dict[str, str] = {
    "year": "연주(조상·가문·사회 배경)",
    "month": "월주(부모·형제·성장환경)",
    "day": "일지(배우자·친밀관계)",
    "hour": "시주(자식·후대·결과)",
}
_PALACE_ORDER = ("year", "month", "day", "hour")


def _is_punishment(a: Branch, b: Branch) -> bool:
    """두 지지가 형(刑) 관계인지 — 삼형 부분쌍·무례지형·자형(같은 글자)."""
    if a is b:
        return a in SELF_PUNISHMENT
    if frozenset({a, b}) in PUNISHMENT_MUTUAL:
        return True
    return any({a, b} <= triple for triple in PUNISHMENT_TRIPLES)


def _is_banhap(a: Branch, b: Branch) -> bool:
    """반합(半合) — 삼합 3지지 중 왕지를 포함한 2지지."""
    for members, _elem, wangji in THREE_HARMONY:
        if a in members and b in members and (a is wangji or b is wangji):
            return True
    return False


def _branch_relation(a: Branch, b: Branch) -> tuple[str, str] | None:
    """두 궁위 지지의 최우선 관계 → (라벨키, 한글명). 없으면 None.

    우선순위: 육합·반합(합) > 충 > 형 > 원진 > 파 > 해. 같은 글자(복음)는 관계로 보지 않는다.
    """
    if a is b:
        return None
    pair = frozenset({a, b})
    if pair in SIX_COMBINATIONS:
        return ("hap", "육합")
    if _is_banhap(a, b):
        return ("hap", "반합")
    if pair in BRANCH_CLASHES:
        return ("chung", "충")
    if _is_punishment(a, b):
        return ("hyeong", "형")
    if pair in WONJIN:
        return ("wonjin", "원진")
    if pair in BRANCH_BREAKS:
        return ("pa", "파")
    if pair in BRANCH_HARMS:
        return ("hae", "해")
    return None


def analyze_palace_network(result: ManseV2Result) -> PalaceNetwork:
    """연·월·일·시 궁위 간 합충형파해원진 + 궁위 공망을 판정한다(운 미반영, 원국 구조).

    이미 계산된 원국 지지·공망만 조회한다(신규 계산 금지). 점수·판정에 개입하지 않는 순수 서술용.

    Args:
        result: 만세 계산 결과(pillars 필수).

    Returns:
        PalaceNetwork — 궁위 쌍 관계 목록 + 공망 궁위 코드.
    """
    if result.pillars is None:
        return PalaceNetwork()
    p = result.pillars
    pillars = {"year": p.year, "month": p.month, "day": p.day, "hour": p.hour}

    pairs: list[PalacePairRelation] = []
    for i, code_a in enumerate(_PALACE_ORDER):
        for code_b in _PALACE_ORDER[i + 1:]:
            pil_a, pil_b = pillars[code_a], pillars[code_b]
            if pil_a is None or pil_b is None:
                continue
            a, b = Branch(pil_a.branch), Branch(pil_b.branch)
            rel = _branch_relation(a, b)
            if rel is None:
                continue
            key, ko = rel
            pairs.append(PalacePairRelation(
                palace_a=code_a, palace_b=code_b,
                role_a=_PALACE_ROLES[code_a], role_b=_PALACE_ROLES[code_b],
                relation=key, relation_ko=ko, branches=f"{a.value}↔{b.value}",
            ))

    gongmang = [
        code for code, pil in pillars.items()
        if pil is not None and getattr(pil, "gongmang_hit", False)
    ]
    return PalaceNetwork(pairs=pairs, gongmang_palaces=gongmang)


def palace_network_lines(network: PalaceNetwork, domain: Domain) -> list[str]:
    """[궁위 관계망] — 궁위 간 관계질을 중립 설명으로. cross-palace 발현은 intent 조건부.

    기본 관계망(궁위 쌍·공망)은 관계·총운 맥락에서 서술하고, 조부모 육아·가족 기반 도움 같은
    구체 발현은 질문 도메인이 맞을 때만 '가능성'으로 조건부 노출한다(단정·일반화 금지).

    Args:
        network: analyze_palace_network 결과.
        domain: 현재 질문 도메인(cross-palace 조건부 노출 게이트).

    Returns:
        LLM 입력 지시문 목록(관계 없음·비대상 도메인이면 빈 목록).
    """
    if not network.pairs and not network.gongmang_palaces:
        return []
    lines = [
        "[궁위 관계망 — 원국 구조(운 미반영). 연=조상·사회 배경, 월=부모·성장환경, 일=배우자·친밀, "
        "시=자식·결과. 궁위 간 관계질은 좋다/나쁘다 단정 없이 경향으로만, 구체 발현은 질문 맥락에 "
        "맞을 때만 가능성으로 서술]",
    ]
    for pr in network.pairs:
        summ = relation_summary_ko(pr.relation)
        lines.append(f"- {pr.role_a} ↔ {pr.role_b} {pr.relation_ko}({pr.branches}): {summ}")
    for code in network.gongmang_palaces:
        lines.append(f"- {_PALACE_ROLES[code]} 공망: {relation_summary_ko('gongmang')}")

    # cross-palace 구체 발현(조건부) — 월·시(가족↔자식/결과) 합이 있고 관계·총운 맥락일 때만.
    family_link = any(
        pr.relation == "hap" and {pr.palace_a, pr.palace_b} in ({"month", "hour"}, {"year", "hour"})
        for pr in network.pairs
    )
    if family_link and domain in (Domain.RELATIONSHIP, Domain.GENERAL):
        lines.append(
            "  · (조건부) 가족·성장 기반과 자식·결과 영역이 연결되는 결 — 육아·돌봄 맥락이면 "
            "조부모·가족의 도움으로, 성과 맥락이면 가족 기반의 도움으로 발현할 가능성(단정 아님)."
        )
    return lines
