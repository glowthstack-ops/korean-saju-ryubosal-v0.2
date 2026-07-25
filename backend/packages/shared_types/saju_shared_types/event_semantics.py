"""이벤트 의미 3분리 계약 — category 공존·전환 (CAREER_TRANSITION_SYSTEM §11).

하나의 legacy `category`가 세 역할(라우팅·형제 발현·캘리브레이션)을 겸하던 것을
`event_domain` / `transition_family` / `calibration_domain`으로 분리한다.

**P0-B 범위**: 타입과 canonical 매핑만 정의한다. 기존 `EVENT_CATEGORY`(taxonomy_v2·
calibration 두 곳)·`CATEGORY_TO_CALIB_DOMAIN`·기존 직렬화는 **손대지 않는다**
(D12·INV-20 — 전환 기간에는 legacy가 **직렬화 호환성**을, 신규 필드가 **의미 소유권**을
갖는다. 동일 소비자가 둘을 동시에 집계·가점하지 않는다).

권위 규칙(§11-4):
- canonical `EventKeyV2` 매핑이 **의미 SSOT**다. 신규 필드는 그 직렬화·전달본이다.
- **legacy category는 신규 의미의 권위 소스가 아니다.**
- `transition_family`는 legacy category에서 **단독 유도하지 않는다**(§11-5 — canonical
  `move`는 정확히 2멤버(career_change·relocation)로 `manifestation_branch`의 "정확히
  2멤버 계열" 규칙 근거이나, legacy `move`는 4멤버(+resignation·travel)라 legacy에서
  유도하면 여행·퇴사가 형제 가족에 유입된다).
- 모호하면 `LEGACY_AMBIGUOUS`로 **fail-closed** — 의미 필드를 부분적으로 남기지 않는다.

`event_domain`·`calibration_domain`을 신규 enum으로 만들지 않는 이유: 기존
`EVENT_DOMAIN` 어휘(career/relocation/wealth/education/relationship/health)를 그대로
쓰며, 여기서 enum을 새로 선언하면 **두 번째 canonical SSOT**가 되기 때문이다.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict

from .event_engine import EventKeyV2

#: 의미 계약 버전 — 매핑·해소 규칙이 바뀌면 올린다. 캐시·저장 레코드는 이 값이 다르면
#: 이전 해소 결과를 재사용하지 않고 재해소한다(§13-1 마지막 fixture).
SEMANTICS_CONTRACT_VERSION = "career-semantics.v1"


class TransitionFamily(StrEnum):
    """형제 발현 가족 — `manifestation_branch` 전용 축(라우팅·캘리브레이션에 쓰지 않음).

    형제 발현 대상만 값을 가지며 기본은 None이다. 현재 canonical 가족은 `move`
    (career_change ↔ relocation) 하나뿐이다.
    """

    MOVE = "move"


class CalibrationCapKey(StrEnum):
    """검증 질문 중복 제한용 파생 키 (D21 — 설계 B).

    `calibration_domain`을 그대로 cap 키로 쓰면 이직·취업·승진이 서로를 밀어내므로
    사건별 검증을 보존하는 파생 키를 둔다. **호출자가 입력하는 권위 필드가 아니라
    resolver가 canonical event_key에서 파생한다.**
    """

    CAREER_TRANSITION = "career_transition"
    EMPLOYMENT_ENTRY = "employment_entry"
    PROMOTION = "promotion"
    RELOCATION = "relocation"


class ResolutionSource(StrEnum):
    """의미 해소 출처 — 결과의 신뢰 근거이자 텔레메트리 라벨(§11-9)."""

    CANONICAL = "canonical"                    # canonical event_key 매핑으로 해소
    EXPLICIT_VALIDATED = "explicit_validated"  # 신규 필드가 canonical과 일치 검증됨
    LEGACY_FALLBACK = "legacy_fallback"        # event_key 부재로 legacy 보조 사용
    LEGACY_AMBIGUOUS = "legacy_ambiguous"      # 모호 — fail-closed
    INVALID_MISMATCH = "invalid_mismatch"      # 신규 필드가 canonical과 충돌 — fail-closed


#: fail-closed 출처 — 의미 필드를 전부 None으로 두고 소비를 막는다.
_FAIL_CLOSED_SOURCES: frozenset[ResolutionSource] = frozenset(
    {ResolutionSource.LEGACY_AMBIGUOUS, ResolutionSource.INVALID_MISMATCH}
)


class CanonicalEventSemantics(BaseModel):
    """canonical event_key 1건의 의미 — `CANONICAL_EVENT_SEMANTICS`의 값 타입."""

    model_config = ConfigDict(frozen=True)

    event_domain: str
    transition_family: TransitionFamily | None = None
    calibration_domain: str | None = None
    calibration_cap_key: CalibrationCapKey | None = None


#: canonical event_key → 의미 (§11-5 명시 매핑). **이 매핑이 유일한 SSOT**이며 테스트·
#: adapter에서 동일 매핑을 다시 선언하지 않는다.
#:
#: 범위: §11-5가 규정한 커리어·이동 4키만 캘리브레이션 의미를 갖는다. 나머지 canonical
#: 키는 `event_domain`(기존 EVENT_DOMAIN)만 해소되고 `transition_family`·
#: `calibration_domain`·`calibration_cap_key`는 **본 Phase 범위 밖(None)** 이다 —
#: 억지로 career 의미를 채우지 않는다.
CANONICAL_EVENT_SEMANTICS: Mapping[EventKeyV2, CanonicalEventSemantics] = MappingProxyType(
    {
        EventKeyV2.CAREER_CHANGE: CanonicalEventSemantics(
            event_domain="career",
            transition_family=TransitionFamily.MOVE,
            calibration_domain="career",
            calibration_cap_key=CalibrationCapKey.CAREER_TRANSITION,
        ),
        EventKeyV2.RELOCATION: CanonicalEventSemantics(
            event_domain="relocation",
            transition_family=TransitionFamily.MOVE,
            # 신규 의미에서는 이사를 career로 접지 않는다(legacy move→career fold는 불변).
            calibration_domain="relocation",
            calibration_cap_key=CalibrationCapKey.RELOCATION,
        ),
        EventKeyV2.JOB_GAIN: CanonicalEventSemantics(
            event_domain="career",
            transition_family=None,  # 형제 발현 대상 아님
            calibration_domain="career",
            calibration_cap_key=CalibrationCapKey.EMPLOYMENT_ENTRY,
        ),
        EventKeyV2.PROMOTION: CanonicalEventSemantics(
            event_domain="career",
            transition_family=None,
            calibration_domain="career",
            calibration_cap_key=CalibrationCapKey.PROMOTION,
        ),
    }
)

#: legacy 문자열 키 → canonical event_key 정규화. legacy `resignation`은 canonical
#: `career_change`로 정규화한 뒤 의미를 해소한다(별도 family 멤버로 추가하지 않는다).
#: canonical `EventKeyV2`에 `travel`은 존재하지 않으므로 여기에도 없다 — legacy `move`
#: 라는 이유로 형제 가족에 넣지 않기 위함(§11-5).
LEGACY_KEY_NORMALIZATION: Mapping[str, EventKeyV2] = MappingProxyType(
    {
        "career_change": EventKeyV2.CAREER_CHANGE,
        "resignation": EventKeyV2.CAREER_CHANGE,
        "relocation": EventKeyV2.RELOCATION,
        "job_gain": EventKeyV2.JOB_GAIN,
        "promotion": EventKeyV2.PROMOTION,
    }
)


class ResolvedEventSemantics(BaseModel):
    """해소 결과 — reader는 자체 매핑표를 만들지 않고 이 결과만 소비한다(§11-4).

    fail-closed 불변식: `resolution_source`가 `LEGACY_AMBIGUOUS`/`INVALID_MISMATCH`면
    **의미 필드가 전부 None**이고 `is_consumable`이 False다. 부분 fallback을 허용하면
    후속 reader가 반쪽 값을 잘못 쓴다.
    """

    model_config = ConfigDict(frozen=True)

    event_domain: str | None = None
    transition_family: TransitionFamily | None = None
    calibration_domain: str | None = None
    calibration_cap_key: CalibrationCapKey | None = None
    resolution_source: ResolutionSource
    contract_version: str = SEMANTICS_CONTRACT_VERSION

    @property
    def is_consumable(self) -> bool:
        """소비 가능 여부 — fail-closed 출처면 False."""
        return self.resolution_source not in _FAIL_CLOSED_SOURCES
