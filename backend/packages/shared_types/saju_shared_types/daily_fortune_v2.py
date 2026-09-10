"""일주별 오늘의 운세 — 3층 판정 모델(v2) 공유 타입 (docs/17 §22).

v2 카탈로그는 **채점 모델 전용**이다: prior / required_signature / evidence.
문구·서사(narrative) 자산은 v1 카탈로그가 SSOT 로 유지된다 — 두 파일에 같은 서사를
복제하면 드리프트가 생기므로, v2 는 사건 정체성(label·domain·valence·slots)과 채점
계약만 담는다. 64종 목록·값의 SSOT 는 docs/17 §22-3·§22-7 표다(변경은 승인 개정으로만).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from saju_shared_types.daily_fortune import (
    CATALOG_EXPANSION_EFFECTIVE_FROM,
    DailyDomain,
    DailySlot,
)

#: v2 채점 모델 버전 — 스냅샷 파일명·플래그 경로 캐시 키의 일부.
#: v2.1(2026-09-10): 카탈로그 48→64종(docs/17 §22-7). 사건 후보가 늘어 선발이 바뀌므로
#: v1 사전과 같은 날짜 경계(CATALOG_EXPANSION_EFFECTIVE_FROM)로 버전을 고른다 — 이미
#: 생성·교정된 9/10·9/11 보드가 재생성(LLM 재교정)되지 않게 하기 위해서다.
MODEL_V2_VERSION = "model.v2.1"
#: 기준일 이전 날짜에 적용되는 v2 모델 버전(48종). 스냅샷
#: `compiled/daily_fortune_v2_model.v2.0.json` 이 함께 커밋돼 있어야 과거 날짜를 재현할 수 있다.
PREVIOUS_MODEL_V2_VERSION = "model.v2.0"


def active_model_v2_version(target_date: date) -> str:
    """그 날짜에 적용할 v2 채점 모델 버전 — v1 `active_dict_version` 과 같은 경계를 쓴다.

    Args:
        target_date: 운세 대상 날짜(KST 기준).

    Returns:
        9/12 이전 `PREVIOUS_MODEL_V2_VERSION`(48종) → 이후 `MODEL_V2_VERSION`(64종).
    """
    if target_date < CATALOG_EXPANSION_EFFECTIVE_FROM:
        return PREVIOUS_MODEL_V2_VERSION
    return MODEL_V2_VERSION

#: prior 3등급 → 사전확률 가산치 (§22-1: signature=출전권, prior=순위만).
PriorTier = Literal["상", "중", "하"]
PRIOR_VALUE: dict[str, float] = {"상": 0.30, "중": 0.18, "하": 0.10}

#: 관계 채널 — 연결/마찰 분리 (§22-2). 존재형 신호라 signature 성립 문턱이 0 초과.
RELATION_CHANNELS: tuple[str, ...] = (
    "yukhap", "samhap", "chung", "hyeong", "pa", "hae", "wonjin", "gongmang",
)
#: 12운성 기능 채널 (§22-2 — 왕/쇠 이분 금지).
STAGE_CHANNELS_V2: tuple[str, ...] = (
    "activity_up", "overdrive", "stamina_down", "pace_down",
    "disengage", "closure", "renewal",
    # §22-8 잔여 채널(2026-09-10 4차) — 목욕=흔들림 / 관대=단장·의욕 / 쇠=노련 / 태·양=구상·양육.
    # 기존 7채널 값은 그대로 두고 덧붙인다(가산) — 사전이 참조하기 전까지 선발에 영향 없음.
    "unsettled", "poised", "seasoned", "incubation",
)
#: 잔여 채널만 따로 — 배선 감사·inert 회귀용.
RESIDUAL_STAGE_CHANNELS: tuple[str, ...] = ("unsettled", "poised", "seasoned", "incubation")
#: 오행 5방향 채널.
ELEMENT_DIRECTION_CHANNELS: tuple[str, ...] = (
    "saeng_a", "a_saeng", "geuk_a", "a_geuk", "bihwa",
)
#: 십성 채널 — 표면성 3등급 값(천간 1.0 / 본기 0.7 / 중기·여기 0.3)으로 계산된다.
SIPSEONG_CHANNELS: tuple[str, ...] = (
    "비견", "겁재", "식신", "상관", "편재", "정재", "편관", "정관", "편인", "정인",
)
#: 십성 그룹 별칭 — signature/evidence 에서 구성원 최댓값으로 해석.
SIPSEONG_GROUPS: dict[str, tuple[str, ...]] = {
    "비겁": ("비견", "겁재"), "식상": ("식신", "상관"), "재성": ("편재", "정재"),
    "관성": ("편관", "정관"), "인성": ("편인", "정인"),
}
#: 오행 활성(간이 object hazard) 채널.
HAZARD_CHANNELS: tuple[str, ...] = ("metal", "fire")

#: signature/evidence 가 참조할 수 있는 이름 전체.
ALLOWED_CHANNEL_NAMES: frozenset[str] = frozenset(
    RELATION_CHANNELS + STAGE_CHANNELS_V2 + ELEMENT_DIRECTION_CHANNELS
    + SIPSEONG_CHANNELS + tuple(SIPSEONG_GROUPS) + HAZARD_CHANNELS
)

#: 게이트식 — 문자열 리프 또는 ["or"|"and", 하위식...]. None = 무게이트(포용 사건).
#: (재귀 구조는 pydantic 스키마 생성이 지원하지 않아 주석은 얕게 두고
#:  `_validate_signature` 가 깊이 검사를 전담한다.)
SignatureExpr = str | list[Any] | None


def _validate_signature(expr: object) -> list[str]:
    """게이트식의 구조·채널 참조를 검사한다. 위반 메시지 목록(비면 통과)."""
    errors: list[str] = []
    if expr is None:
        return errors
    if isinstance(expr, str):
        if expr not in ALLOWED_CHANNEL_NAMES:
            errors.append(f"미정의 채널: {expr}")
        return errors
    if not isinstance(expr, list) or not expr or expr[0] not in ("or", "and"):
        errors.append(f"게이트식 형식 오류: {expr!r}")
        return errors
    if len(expr) < 2:
        errors.append(f"게이트식 피연산자 부족: {expr!r}")
    for sub in expr[1:]:
        errors.extend(_validate_signature(sub))
    return errors


class DailyEventModelV2(BaseModel):
    """사건 1개의 3층 채점 계약 (§22-3 한 행).

    extra 금지 — v2 는 채점 전용 스키마다. expr_confidence 등 v1 필드가 흘러들면
    구조 검증에서 즉시 실패한다(ec 는 prior층·문구 톤 전용, §22-1).
    """

    model_config = ConfigDict(extra="forbid")

    label: str
    domain: DailyDomain
    valence: Literal["good", "caution"]
    slots: list[DailySlot] = Field(min_length=1)
    synonym_group: str | None = None
    headline_slots: list[DailySlot] | None = None
    prior: PriorTier
    required_signature: SignatureExpr = None
    evidence: dict[str, float] = Field(min_length=1)

    @field_validator("evidence")
    @classmethod
    def _evidence_channels(cls, v: dict[str, float]) -> dict[str, float]:
        for name, w in v.items():
            if name not in ALLOWED_CHANNEL_NAMES:
                raise ValueError(f"미정의 evidence 채널: {name}")
            if not (-1.0 <= w <= 1.0) or w == 0.0:
                raise ValueError(f"evidence 가중 범위 위반({name}={w}): [-1,1]·0 금지")
        return v

    @field_validator("required_signature")
    @classmethod
    def _signature_shape(cls, v: SignatureExpr) -> SignatureExpr:
        errors = _validate_signature(v)
        if errors:
            raise ValueError("; ".join(errors))
        return v


class DailyEventCatalogV2(BaseModel):
    """v2 카탈로그 전체 — 64종 (docs/17 §22-3·§22-7, weather_water_safety 제외)."""

    version: str
    #: 사람의 명리 감수 여부 — 구조 검증 통과와 별개(v1 파이프라인과 동일 규약).
    reviewed: bool
    review_note: str | None = None
    events: dict[str, DailyEventModelV2] = Field(min_length=1)
