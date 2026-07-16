"""생성 답변의 위험 claim 사후 감사 R5 — 규칙 기반(감수 45차 §11).

prompt 지시만으로 claim 강제가 완료됐다고 판단하지 않는다 — 모델이 실제로
생성한 최종 문장을 검사하고, 위반이 있으면 사용자 전달 전에 재작성/위험
단락 제거/전체 fail-closed로 처리한다(위반 기록만 남기고 그대로 노출 금지).

검사 축: 확정 발생 표현·사고/질병/법적 결과 단정·금전 손실 확정·partial
episode 동일 현실 건 단정·recovery 보장·항목별 prohibited 원문. 결정적
패턴 매칭(LLM 재판정 아님 — 감사 계층에 LLM 사용 금지).
"""

from __future__ import annotations

# 전역 금지 코드 → 결정적 한국어 위반 패턴(부분 문자열 — 감수 대상 어휘).
# 과잉 차단 금지: '계약 검토가 필요한 시기' 수준의 권고는 잡지 않는다.
_PROHIBITED_PATTERNS: dict[str, tuple[str, ...]] = {
    "guaranteed_occurrence": (
        "반드시 발생", "반드시 일어", "무조건 발생", "확실히 발생",
        "반드시 생깁", "피할 수 없",
    ),
    "accident_prediction": (
        "사고가 납니다", "사고를 당합니다", "사고가 발생합니다",
        "다치게 됩니다",
    ),
    "diagnosis": (
        "병에 걸립니다", "질병이 발생합니다", "발병합니다", "진단됩니다",
    ),
    "legal_outcome_certainty": (
        "패소합니다", "승소합니다", "유죄", "처벌받습니다", "구속됩니다",
    ),
    "financial_loss_certainty": (
        "파산합니다", "전액 손실", "재산을 잃습니다", "손해를 봅니다",
        "돈을 잃게 됩니다",
    ),
    "same_episode_certainty": (
        "동일한 사건입니다", "같은 사건입니다", "하나의 사건에서",
        "같은 계약 때문에",
    ),
    "recovery_guarantee": (
        "완전히 해결됩니다", "완전히 회복됩니다", "위험이 사라집니다",
        "문제가 해결됩니다", "완벽하게 회복",
    ),
}
# exposed level 초과 표현(감수 45차): 최대 노출 수준이 warning 이하일 때
# 금지되는 격상 표현(치명·중대 단정 계열).
_ESCALATION_PATTERNS = ("치명적", "심각한 위험이 확실", "매우 위험합니다",
                        "큰 문제가 생깁니다")


def audit_generated_risk_claims(
    answer: str,
    *,
    episode_prohibited_phrases: list[str] | None = None,
    required_qualifiers: list[str] | None = None,
    max_exposed_level: str = "warning",
) -> dict:
    """생성 답변의 위험 claim 위반 검사(결정적 — 감수 45차 §11).

    Args:
        answer: 모델이 생성한 최종 답변.
        episode_prohibited_phrases: 주입된 episode들의 항목별 금지 원문
            (사전 prohibitedClaims — 부분 문자열 검사).
        required_qualifiers: 주입된 episode들의 필수 한정어 코드 —
            possibly_related가 있으면 동일 사건 단정 검사 강화.
        max_exposed_level: 주입된 episode 중 최고 exposed level —
            warning 이하면 격상 표현 검사.

    Returns:
        {"violations": [{"code", "matched"}...], "action": "ALLOW" |
        "REVISE_REQUIRED"} — REVISE_REQUIRED면 재작성/위험 단락 제거/전체
        fail-closed 중 하나를 호출부가 수행(그대로 노출 금지).
    """
    violations: list[dict] = []
    for code, patterns in _PROHIBITED_PATTERNS.items():
        for pat in patterns:
            if pat in answer:
                violations.append({"code": code, "matched": pat})
    for phrase in episode_prohibited_phrases or []:
        # 사전 원문은 '~단정' 형태의 지침이라 어간만 대조(예: "계약 무산
        # 단정" → "계약 무산"이 단정형으로 등장하는지).
        stem = phrase.replace(" 단정", "").strip()
        if stem and f"{stem}됩니다" in answer or f"{stem}입니다" in answer:
            violations.append({"code": "item_prohibited", "matched": phrase})
    if "possibly_related" in (required_qualifiers or []):
        for pat in _PROHIBITED_PATTERNS["same_episode_certainty"]:
            if pat in answer and not any(
                    v["matched"] == pat for v in violations):
                violations.append(
                    {"code": "same_episode_certainty", "matched": pat})
    if max_exposed_level in ("advisory", "watch", "warning"):
        for pat in _ESCALATION_PATTERNS:
            if pat in answer:
                violations.append(
                    {"code": "level_escalation", "matched": pat})
    return {
        "violations": violations,
        "action": "ALLOW" if not violations else "REVISE_REQUIRED",
    }


__all__ = ["audit_generated_risk_claims"]
