"""연애·결혼 시기 도메인 공유 타입 (MARRIAGE_TIMING_ENHANCEMENT §1·§2, 2026-06-30).

결혼 도메인 stage refinement(`MarriageStage`)와 배우자성/자녀성 추상화(`partner_star`/
`child_star`)를 정의한다. **본 모듈은 타입·매핑·해석 스텁만 제공**하며 점수·판정 로직은 없다
(절대원칙 5 — 검수 전 운영 반영 금지). 내부 계산은 기존 `wealth/officer(officer_killing)`
십성군을 그대로 쓰고, 관계/결혼 도메인의 표기·게이트만 `partner_star`로 추상화한다.

핵심 원칙:
- `MarriageStage`는 base E4 stage(awareness|exploration|action|decision|completion)를 **늘리지
  않고** 그 위에 얹는 6단계 refinement다. `MARRIAGE_TO_BASE_STAGE`로 환원해 `TimelinePhase.stage`
  (자유 str)에 채운다.
- 여 배우자성은 정관만이 아니라 **관살 전체**(officer_killing)다 — 편관 누락 방지. 정관/편관
  분기는 안정성(stability) 평가에서 한다.
- gender 미상은 차단하지 않는다(원칙 11) — `UNKNOWN` 반환 + 호출부에서 양 기준 병기·confidence 하향.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class MarriageStage(StrEnum):
    """관계/결혼 도메인 stage refinement (MARRIAGE_TIMING_ENHANCEMENT §1).

    base E4 stage를 대체하지 않는다. `MARRIAGE_TO_BASE_STAGE`로 base로 환원해 사용한다.
    """

    AWARENESS = "awareness"            # 마음 동함·끌림·관계 생각
    CONTACT = "contact"                # 소개·연락·만남·썸
    RELATIONSHIP = "relationship"      # 교제 시작·관계 진전
    COMMITMENT = "commitment"          # 결혼 논의·상견례·약속·혼인 결정
    FORMALIZATION = "formalization"    # 결혼식·혼인신고·동거·가정 형성
    FAMILY_EXPANSION = "family_expansion"  # 임신·출산·자녀 이슈


# marriage_stage → base E4 stage 문자열(TimelinePhase.stage 호환). base 5단계는 늘리지 않는다 —
# formalization·family_expansion 모두 'completion'에 매핑된다(신규 base stage 없음).
MARRIAGE_TO_BASE_STAGE: dict[MarriageStage, str] = {
    MarriageStage.AWARENESS: "awareness",
    MarriageStage.CONTACT: "exploration",
    MarriageStage.RELATIONSHIP: "action",
    MarriageStage.COMMITMENT: "decision",
    MarriageStage.FORMALIZATION: "completion",
    MarriageStage.FAMILY_EXPANSION: "completion",
}


class TenGodGroup(StrEnum):
    """배우자성/자녀성 추상화에 쓰는 십성 그룹(허용값 고정 — reason_code·gate 안정화).

    내부 계산의 십성군과 동일 표기. `officer_killing`은 정관+편관(관살) 전체를 가리킨다.
    """

    WEALTH = "wealth"                  # 재성(정재·편재)
    OFFICER_KILLING = "officer_killing"  # 관살(정관·편관)
    OUTPUT = "output"                  # 식상(식신·상관)
    UNKNOWN = "unknown"                # gender 미상 — 양 기준 병기·confidence 하향


class PartnerStarRule(BaseModel):
    """배우자성/자녀성 십성 매핑 (설정화 — 향후 관계 모델 확장 대비).

    전통 기준: 여=관살·남=재성이 배우자성, 여=식상·남=관살이 자녀성. 내부 계산은 바꾸지 않고
    도메인 표기·게이트만 추상화하기 위한 설정이다.
    """

    rule: str = "traditional"
    male_partner_star: TenGodGroup = TenGodGroup.WEALTH            # 남=재성(정재·편재)
    female_partner_star: TenGodGroup = TenGodGroup.OFFICER_KILLING  # 여=관살(정관·편관)
    female_child_star: TenGodGroup = TenGodGroup.OUTPUT            # 여=식상
    male_child_star: TenGodGroup = TenGodGroup.OFFICER_KILLING     # 남=관살


def resolve_partner_star(
    gender: str, rule: PartnerStarRule | None = None
) -> TenGodGroup:
    """성별 → 배우자성(partner_star) 십성 그룹.

    Args:
        gender: 'female'/'male'/그 외(미상).
        rule: 매핑 설정(미입력 시 traditional 기본).

    Returns:
        여=관살(OFFICER_KILLING) / 남=재성(WEALTH) / 미상=UNKNOWN.
        UNKNOWN이면 호출부에서 양 기준 병기 + confidence 하향(차단 금지 — 원칙 11).
    """
    r = rule or PartnerStarRule()
    if gender == "female":
        return r.female_partner_star
    if gender == "male":
        return r.male_partner_star
    return TenGodGroup.UNKNOWN


# MT 코드 → marriage_stage 도출(Marriage Production Readiness v1 Step 2). action 단계로 올리는 코드.
_MT_ACTION_CODES = frozenset({"MT3_DIRECTIONAL_DAY_BRANCH", "MT2_EMERGENCE_SAME_STEM"})
_MT_PREFIXES = ("MT1_", "MT2_", "MT3_")


class MarriageStageDerivation(BaseModel):
    """MT reason_codes에서 도출한 관계 단계 payload(LLM 입력용)."""

    stage: str = ""            # awareness | relationship | "" (MT 없음)
    base_stage: str = ""       # base E4 환원
    stage_reason: list[str] = []  # noqa: RUF012 — 단계를 유발한 MT 코드
    stage_limit: str = ""      # 승급 상한 사유(예: commitment_marker_absent)


def derive_marriage_stage(reason_codes: list[str]) -> MarriageStageDerivation:
    """MT reason_codes → 관계 단계(비-MT 후보는 빈 결과).

    awareness/relationship까지만 도출한다 — commitment/formalization은 marker 게이트(Step 3)가
    있어야 가능하며, 현재는 미구현이라 stage_limit='commitment_marker_absent'로 상한을 명시한다
    (MT가 아무리 겹쳐도 결혼 확정 단계로 못 올라감 — 과판단 차단).

    Args:
        reason_codes: 후보의 evidence_path(=EventCandidateV2.reason_codes).

    Returns:
        MarriageStageDerivation. MT 코드가 없으면 stage="" (단계 미부여).
    """
    mt = [c for c in reason_codes if c.startswith(_MT_PREFIXES)]
    if not mt:
        return MarriageStageDerivation()
    stage = (
        MarriageStage.RELATIONSHIP
        if any(c in _MT_ACTION_CODES for c in mt)
        else MarriageStage.AWARENESS
    )
    return MarriageStageDerivation(
        stage=stage.value,
        base_stage=MARRIAGE_TO_BASE_STAGE[stage],
        stage_reason=mt,
        stage_limit="commitment_marker_absent",
    )


def resolve_child_star(
    gender: str, rule: PartnerStarRule | None = None
) -> TenGodGroup:
    """성별 → 자녀성(child_star) 십성 그룹.

    Args:
        gender: 'female'/'male'/그 외(미상).
        rule: 매핑 설정(미입력 시 traditional 기본).

    Returns:
        여=식상(OUTPUT) / 남=관살(OFFICER_KILLING) / 미상=UNKNOWN.
    """
    r = rule or PartnerStarRule()
    if gender == "female":
        return r.female_child_star
    if gender == "male":
        return r.male_child_star
    return TenGodGroup.UNKNOWN
