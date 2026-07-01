"""외적 인상·매력 신호 프로파일 (External Impression / Charm Signal, v1, 2026-07-01).

SSOT: ``doc/v2_2/EXTERNAL_IMPRESSION_SIGNAL.md``. **"미인 판정"이 아니라** 원국에서 드러나는
외적 인상·분위기·표현 매력·관계적 끌림을 보조적으로 해석하는 구조 신호다. 도화·식상·화기·
금수상관 등을 **엔진이 코드로 판정**하고(절대원칙 1), 가중 스코어로 노출 여부를 게이트한다.
'예쁘다/못생겼다' 단정·부정 평가는 어떤 형태로도 담지 않는다(미해당 시 완전 무언급).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExternalImpressionSignal(BaseModel):
    """외적 인상 신호 1건 — 엔진이 원국에서 판정한 정제 태그(원시 점수·퍼센트는 노출 금지).

    Attributes:
        code: 신호 코드(예: ``DAY_BRANCH_PEACH``). 내부 식별·테스트용.
        category: 카테고리 그룹(``metal_water``/``output``/``peach``/``fire``/``yinhai``).
            category_count(서로 다른 카테고리 수) 산정에 쓰여 동일 계열 중복 과발동을 막는다.
        legacy_ko: 전통 명리 근거(예: '일지 도화성').
        modern_ko: 현대적 해석 문구(외모 단정이 아닌 인상·끌림 서술).
        weight: 가중치(primary/secondary 배점).
        tier: ``primary`` | ``secondary`` | ``note``. note는 스코어·카운트 제외(모발 등 완곡 참고).
        note: 부가 주의(예: 표현 과다 시 호불호 가능). 없으면 빈 문자열.
    """

    code: str
    category: str
    legacy_ko: str
    modern_ko: str
    weight: float
    tier: str
    note: str = ""


class ExternalImpressionProfile(BaseModel):
    """외적 인상·매력 신호 종합 — 가중 스코어 + 노출 게이트 판정 결과(운 미반영, 원국 구조).

    Attributes:
        gender: 'female'/'male'/'unknown'.
        signals: 매칭된 신호 목록(note-only 포함).
        score: primary/secondary 가중 합(note 제외).
        primary_signal_count: tier=='primary' 신호 개수.
        category_count: 매칭된 서로 다른 카테고리 수(note 제외).
        band: ``none`` | ``weak`` | ``notable`` | ``strong``.
        is_notable: 노출 후보 여부(score>=1.8 AND primary>=1 AND category>=2).
        legacy_female_centric_used: 원문 여성중심 신호(식상·화기)를 남녀 공통 적용 시 True(진단용).
        confidence: 'normal' | 'low'(성별 미상). low면 직접 질문·strong일 때만 노출.
    """

    gender: str
    signals: list[ExternalImpressionSignal] = Field(default_factory=list)
    score: float = 0.0
    primary_signal_count: int = 0
    category_count: int = 0
    band: str = "none"
    is_notable: bool = False
    legacy_female_centric_used: bool = False
    confidence: str = "normal"
