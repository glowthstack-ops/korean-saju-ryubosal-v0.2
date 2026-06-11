"""간지달력 엔트리·관계 적중 schemas (v2.2 Phase 0, docs/02 E0).

설계 문서의 `GanjiCalendarEntry` / `RelationHit` / `RelationType`를 Python으로 옮긴 것.
운(대운/세운/월운/일운) 간지가 원국과 만드는 합충형파해·공망 활성을 **구조화된** 형태로
표현한다. 만세력 엔진은 이를 표시용 문자열(`relations_to_chart`)로 내보내므로, 본 타입은
`saju_engines`의 변환기가 그 문자열을 파싱·보강해 채운다(엔진 = 유일 진실 공급원, 절대 원칙 1).

문서의 `RelationHit.participants = {from, to}`는 운 1글자가 원국 복수 자리와 동시에 관계를
맺을 수 있어, 본 구현은 `to`를 단수가 아닌 `natal_refs`(list)로 일반화한다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class GanjiLevel(StrEnum):
    """간지달력 계층 (docs/01 핵심 시간 모델)."""

    DAEWOON = "daewoon"
    YEAR = "year"
    MONTH = "month"
    DAY = "day"


class RelationType(StrEnum):
    """원국과의 관계 종류. 만세력 엔진의 한글 접두사와 1:1 대응한다.

    삼합/방합 기여는 운 글자가 원국 글자들과 국(局)을 완성하는 경우이며, 元 문자열은
    완성 오행만 담으므로 변환기가 해당 오행의 국 구성 지지를 원국에서 찾아 보강한다.
    공망 3종은 운이 원국 공망 지지를 자극(전실/충발동/합해소)하는 경우다.
    """

    STEM_COMBINATION = "stem_combination"  # 천간합
    BRANCH_CLASH = "branch_clash"  # 충
    SIX_COMBINATION = "six_combination"  # 육합
    THREE_HARMONY_CONTRIB = "three_harmony_contrib"  # 삼합기여
    DIRECTIONAL_CONTRIB = "directional_contrib"  # 방합기여
    BRANCH_BREAK = "branch_break"  # 파
    HARM = "harm"  # 해
    PUNISHMENT_TRIPLE = "punishment_triple"  # 삼형(인사신/축술미)
    PUNISHMENT_MUTUAL = "punishment_mutual"  # 무례지형(자묘)
    SELF_PUNISHMENT = "self_punishment"  # 자형
    VOID_FILL = "void_fill"  # 공망전실
    VOID_TRIGGER_CLASH = "void_trigger_clash"  # 공망발동(충)
    VOID_RELEASE_COMBINE = "void_release_combine"  # 공망해소(합)


class GanjiRef(BaseModel):
    """관계에 참여하는 간지 한 자리(운 측 또는 원국 측).

    position은 운 측이면 GanjiLevel, 원국 측이면 'year'/'month'/'day'/'hour'.
    stem/branch는 해당 자리에서 관계에 실제로 관여한 글자(한자)다.
    """

    side: str  # 'luck' (운) / 'natal' (원국)
    position: str  # 'daewoon'|'year'|'month'|'day'(운) · 'year'|'month'|'day'|'hour'(원국)
    stem: str | None = None
    branch: str | None = None


class RelationHit(BaseModel):
    """운 간지 ↔ 원국 사이의 단일 관계 적중 (docs/02 E0 RelationHit).

    relation_id는 사전 키 형태의 안정 식별자(예: 'rel_branch_clash_午_子'). element는
    삼합/방합 기여의 완성 오행처럼 관계가 산출하는 오행이 있을 때만 채운다.
    """

    relation_id: str
    type: RelationType
    luck_ref: GanjiRef
    natal_refs: list[GanjiRef] = Field(default_factory=list)
    element: str | None = None  # 삼합/방합 기여 완성 오행 등


class GanjiCalendarEntry(BaseModel):
    """기간 단위 간지 + 원국과의 관계 적중 묶음 (docs/02 E0 GanjiCalendarEntry).

    period는 계층별 라벨('2026' / '2026-06' / '2026-06-10' / '2026~2035').
    """

    level: GanjiLevel
    period: str
    stem: str
    branch: str
    ganji: str
    relations_with_chart: list[RelationHit] = Field(default_factory=list)
