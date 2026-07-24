"""Marriage Production Readiness v1 — Step 3: 결혼 답변 출력 가드 (코드 레벨).

LLM 프롬프트에만 맡기지 않고, **코드가 무엇을 말할 수 있는지 결정**해 payload에 주입한다. 핵심은
과판단(결혼 확정·올해 결혼·거의 100%) 차단이다. 단계(marriage_stage)와 marker 유무로 허용 표현
수위를 정하고, commitment/formalization marker가 없으면(미구현) **결혼 확정·논의 표현을 막는다**.

`compute_marriage_output_guard`는 순수 함수(허용/차단 결정), `marriage_guard_directive`는 이를 LLM
지시문으로 렌더, `detect_marriage_overclaim`는 LLM 출력에서 금지 표현을 탐지(테스트·텔레메트리·후속
재생성용). 하드 금지 표현(반드시 결혼·거의 100% 등)은 단계와 무관하게 **항상** 차단한다(절대원칙 3).
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# 단계·marker와 무관하게 항상 금지(절대원칙 3 — 단정·확률 단정).
_HARD_BLOCKED: tuple[str, ...] = (
    "반드시 결혼", "꼭 결혼", "거의 100%", "100% 결혼", "혼인 확정", "결혼 확정",
    "올해 결혼한다", "이 사람과 결혼", "반드시 만난다", "꼭 사귄다",
)
# 출력 과claim 탐지 패턴(확정 단정형). 단계가 허용해도 '확정 어미'는 잡아 후속 점검에 쓴다.
_OVERCLAIM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"반드시\s*결혼"),
    re.compile(r"꼭\s*결혼"),
    re.compile(r"거의\s*100\s*%"),
    re.compile(r"100\s*%\s*(결혼|이혼)"),
    re.compile(r"혼인\s*확정|결혼\s*확정"),
    re.compile(r"올해\s*(반드시\s*)?결혼(합니다|한다|하게\s*됩니다)"),
    re.compile(r"이\s*사람과\s*결혼(합니다|한다|하게\s*됩니다)"),
)


# B2(RELATIONSHIP_EVENT_SYSTEM 부록 B, 2026-07-24) — 배우자궁 충·형·파·해 REL reason의
# 명시적 안정성 위험 분류. P0-A 실측: REL_CHUNG_* 기반 marriage_signal이 리스크 표기 없이
# Top5에 진입하던 방향 누수를 출력 가드에서 차단한다(점수·순위·confidence 불변).
_NEGATIVE_RELATION_REASON_PREFIXES: tuple[str, ...] = (
    "REL_CHUNG_", "REL_HYEONG_", "REL_PA_", "REL_HAE_",
)


def is_relationship_stability_risk(reason_code: str) -> bool:
    """REL_{kind}_{palace} reason이 안정성 위험(충·형·파·해) 계열인지 명시적으로 분류한다.

    문자열 임의 포함 검사가 아니라 접두사 화이트리스트 — 합(REL_HAP_*)·복음(REL_BOKEUM_*)은
    위험으로 분류하지 않는다.

    Args:
        reason_code: 후보 reason 코드 1건(예: 'REL_CHUNG_day_pillar').

    Returns:
        충·형·파·해 계열이면 True.
    """
    return reason_code.startswith(_NEGATIVE_RELATION_REASON_PREFIXES)


def has_stability_risk(reason_codes: list[str]) -> bool:
    """배우자궁 충·형·파·해·쟁합·기신 등 안정성 저해 risk 코드 존재 여부.

    충+기신 배우자궁 발동은 결혼이 아니라 관계 변화·갈등일 수 있으므로(§12 재분기), 답변에서
    'marriage 긍정 단정'이 아니라 'relationship_change 가능성 병기'를 강제하는 트리거다.

    판정 2계층(B2): ①기존 MT 계열("CLASHED"/"RISK" 포함 — MT2_EMERGENCE_CLASHED·
    SPOUSE_PALACE_CLASHED·MT1_GISIN_RISK 등) ②REL 계열 명시 분류(충·형·파·해 접두사).
    REL_COMPOUND 단독(구성 REL 코드 부재 — 이론상 없음)은 합 중심 복합일 수 있어 보수적으로
    미판정하고 감사 로그만 남긴다.
    """
    codes = list(reason_codes)
    if any("CLASHED" in c or "RISK" in c for c in codes):
        return True
    if any(is_relationship_stability_risk(c) for c in codes):
        return True
    if "REL_COMPOUND" in codes and not any(
        c.startswith("REL_") and c != "REL_COMPOUND" for c in codes
    ):
        # relation_palace_engine은 구성 REL 코드를 COMPOUND보다 먼저 넣으므로 도달 시 이상 상황.
        logger.info("REL_COMPOUND 단독 — 구성 코드 부재로 안정성 위험 미판정: %s", codes)
    return False


class MarriageOutputGuard(BaseModel):
    """결혼 답변에서 코드가 결정한 허용/차단(LLM에 주입)."""

    stage: str = ""
    can_say_marriage_confirmed: bool = False      # formalization marker 있을 때만
    can_say_marriage_discussion: bool = False     # commitment marker 있을 때만
    can_say_relationship_progress: bool = False   # relationship 단계 이상
    must_branch_by_relationship_status: bool = True
    stability_risk: bool = False                  # 충·쟁합·기신 → 관계 변화·갈등 가능성 병기
    blocked_expressions: list[str] = Field(default_factory=lambda: list(_HARD_BLOCKED))


def compute_marriage_output_guard(
    stage: str,
    *,
    has_commitment_marker: bool = False,
    has_formalization_marker: bool = False,
    stability_risk: bool = False,
) -> MarriageOutputGuard:
    """단계·marker → 출력 가드(허용 표현 수위 결정).

    marker는 현재 미구현이라 기본 False — 따라서 결혼 확정·논의 표현은 막히고 'relationship 진전
    가능성'까지만 허용된다(과판단 차단). marker 게이트 구현 시 인자만 채우면 자동 해제된다.

    Args:
        stage: marriage_stage(awareness/relationship/commitment/formalization/"").
        has_commitment_marker / has_formalization_marker: marker 게이트(미구현 시 False).

    Returns:
        MarriageOutputGuard. stage=""(비-MT)면 progress=False·확정 차단(보수).
    """
    confirmed = has_formalization_marker and stage == "formalization"
    discussion = has_commitment_marker and stage in ("commitment", "formalization")
    progress = stage == "relationship" or discussion or confirmed
    # 안정성 risk면 결혼 확정·논의를 더 강하게 막는다(관계 변화 가능성 병기).
    if stability_risk:
        confirmed = False
        discussion = False
    return MarriageOutputGuard(
        stage=stage,
        can_say_marriage_confirmed=confirmed,
        can_say_marriage_discussion=discussion,
        can_say_relationship_progress=progress,
        must_branch_by_relationship_status=True,
        stability_risk=stability_risk,
    )


def marriage_guard_directive(guard: MarriageOutputGuard) -> str:
    """가드 → LLM 지시문(코드 결정사항을 프롬프트로 전달)."""
    allow = (
        "관계 진전 가능성" if guard.can_say_relationship_progress
        else "관심·인연 의식(연애 생각)"
    )
    lines = [
        "[결혼 답변 출력 가드 — 코드 결정, 위반 금지]",
        f"- 허용 수위: '{allow}'까지만.",
    ]
    if not guard.can_say_marriage_discussion:
        lines.append("- '결혼 논의·상견례·결혼 결정' 단정 금지(commitment marker 부재).")
    if not guard.can_say_marriage_confirmed:
        lines.append("- '결혼 확정·혼인 성사·올해 결혼' 금지(formalization marker 부재).")
    if guard.must_branch_by_relationship_status:
        lines.append("- 관계 상태 모르면 분기 서술(있으면 결혼 논의 / 없으면 진지한 만남).")
    if guard.stability_risk:
        lines.append(
            "- 배우자궁 충·쟁합·기신 동반 — marriage 긍정 단정 금지, '관계 변화·갈등·"
            "불안정한 끌림' 가능성을 반드시 병기(activation 높아도 stability 낮음)."
        )
    lines.append("- 금지 표현: " + " / ".join(guard.blocked_expressions))
    return "\n".join(lines)


def detect_marriage_overclaim(text: str) -> list[str]:
    """LLM 출력에서 결혼 과claim(확정 단정) 표현을 탐지한다(테스트·텔레메트리·후속 재생성용).

    Args:
        text: LLM 답변 텍스트.

    Returns:
        탐지된 과claim 표현 목록(없으면 빈 목록).
    """
    found: list[str] = []
    for pat in _OVERCLAIM_PATTERNS:
        m = pat.search(text)
        if m and m.group(0) not in found:
            found.append(m.group(0))
    return found
