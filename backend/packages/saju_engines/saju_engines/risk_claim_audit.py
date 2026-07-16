"""생성 답변의 위험 claim 사후 감사 R5 — 규칙 기반(감수 45차 §11).

prompt 지시만으로 claim 강제가 완료됐다고 판단하지 않는다 — 모델이 실제로
생성한 최종 문장을 검사하고, 위반이 있으면 사용자 전달 전에 재작성/위험
단락 제거/전체 fail-closed로 처리한다(위반 기록만 남기고 그대로 노출 금지).

검사 축: 확정 발생 표현·사고/질병/법적 결과 단정·금전 손실 확정·partial
episode 동일 현실 건 단정·recovery 보장·항목별 prohibited 원문. 결정적
패턴 매칭(LLM 재판정 아님 — 감사 계층에 LLM 사용 금지).
"""

from __future__ import annotations

import hashlib
import json

# claim audit 정책 버전(감수 46차 §16) — 패턴·qualifier registry·재작성
# 정책 변경 시 올린다(claim_audit_policy_hash 변경 = expose_pipeline 재감수
# 신호 — manifest 병기).
RISK_CLAIM_AUDIT_VERSION = "risk-claim-audit-r5.1.0"
# 재작성 정책(감수 46차 §11): 무제한 재생성 금지.
MAX_RISK_REVISION_ATTEMPTS = 1

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
    # 우회 단정(감수 48차 §11 FN 코퍼스): 금지 키워드 없이 확정을 시사.
    "circumvented_certainty": (
        "피하기 어려운 흐름", "이어지는 수순", "현실화될 가능성이 매우 높",
        "기정사실", "피할 수 없는 수순",
    ),
}
# 안전한 부정문(감수 48차 §11 FP 코퍼스): 매치 직후 부정 표지가 오면 위반
# 아님 — "사고가 난다는 뜻은 아닙니다" 류를 차단하지 않는다.
_NEGATION_MARKERS = ("아닙니다", "아니에요", "않습니다", "아니며", "아니라")
_NEGATION_WINDOW = 25  # 매치 종료 후 부정 표지 탐색 범위(문자)
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
    def _negated(idx: int, pat: str) -> bool:
        tail = answer[idx + len(pat): idx + len(pat) + _NEGATION_WINDOW]
        return any(m in tail for m in _NEGATION_MARKERS)

    violations: list[dict] = []
    for code, patterns in _PROHIBITED_PATTERNS.items():
        for pat in patterns:
            idx = answer.find(pat)
            if idx >= 0 and not _negated(idx, pat):
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


# qualifier 코드 → 답변에서 인정되는 한정어 문구(결정적 — 감수 대상 어휘).
_QUALIFIER_PHRASES: dict[str, tuple[str, ...]] = {
    "possibly_related": ("관련됐을 가능성", "관련이 있을 수", "연결은 확인되지",
                         "함께 나타날 수", "겹칠 수"),
    "conditional_exposure": ("해당된다면", "하고 있다면", "진행 중이라면",
                             "경우에는", "확인되지 않았"),
    "non_assertive_recovery": ("완화될 가능성", "줄어들 수", "안정될 수",
                               "이어질 수"),
}


def audit_risk_sections(sections: list[dict], whole_answer: str) -> dict:
    """구조화 risk section의 episode별 감사(감수 46차 §10·§12).

    전역 문자열 검사의 오판(다른 episode의 qualifier로 충족 오인)을 막기
    위해 **episode 단위**로 검사하고, 모델이 위험 주장을 mainAnswer에 쓸 수
    있으므로 **전체 답변 감사를 병행**한다.

    Args:
        sections: [{"episode_key", "exposed_level", "identity_phrase_mode",
            "required_qualifiers", "prohibited_phrases", "text"}...] —
            구조화 출력 envelope의 risk_guidance 항목들.
        whole_answer: 사용자에게 전달될 전체 답변(main + risk + followup).

    Returns:
        {"violations": [{"episode_key"|None, "code", "matched"}...],
         "action": "ALLOW" | "REVISE_REQUIRED"}
    """
    violations: list[dict] = []
    for sec in sections:
        text = sec.get("text", "")
        key = sec.get("episode_key")
        part = audit_generated_risk_claims(
            text,
            episode_prohibited_phrases=list(
                sec.get("prohibited_phrases", [])),
            required_qualifiers=list(sec.get("required_qualifiers", [])),
            max_exposed_level=str(sec.get("exposed_level", "warning")))
        for v in part["violations"]:
            violations.append({"episode_key": key, **v})
        # episode별 qualifier 존재 검사(전역 출현으로 충족 오인 금지).
        for q in sec.get("required_qualifiers", []):
            phrases = _QUALIFIER_PHRASES.get(q, ())
            if phrases and not any(ph in text for ph in phrases):
                violations.append({"episode_key": key,
                                   "code": "missing_qualifier",
                                   "matched": q})
    whole = audit_generated_risk_claims(whole_answer)
    for v in whole["violations"]:
        violations.append({"episode_key": None, **v})
    return {"violations": violations,
            "action": "ALLOW" if not violations else "REVISE_REQUIRED"}


_LEVEL_RANK = {"advisory": 0, "watch": 1, "warning": 2, "critical": 3}


def validate_risk_guidance_envelope(
    sections: list[dict], llm_episodes: list[dict],
) -> list[str]:
    """구조화 risk_guidance 불변식(감수 48차 §10-⑤) — 위반 코드 목록 반환.

    ①episode_key ⊆ 주입된 llmRiskEpisodes ②같은 key 중복 실패 ③R3
    warning-first 순서 유지 ④exposed level보다 높은 level 출력 실패.
    빈 목록=통과. 위반 시 해당 답변은 REVISE 경로로 보낸다(그대로 전달 금지).
    """
    errors: list[str] = []
    allowed_keys = [str(e.get("episodeKey") or e.get("episode_key") or "")
                    for e in llm_episodes]
    levels = {k: str(e.get("presentationLevel", "warning"))
              for k, e in zip(allowed_keys, llm_episodes, strict=True)}
    seen: set[str] = set()
    last_bucket = -1
    bucket = {"critical": 0, "warning": 0, "watch": 1, "advisory": 2}
    for sec in sections:
        key = str(sec.get("episode_key", ""))
        if key not in levels:
            errors.append(f"UNREGISTERED_EPISODE_KEY:{key}")
            continue
        if key in seen:
            errors.append(f"DUPLICATE_EPISODE_KEY:{key}")
            continue
        seen.add(key)
        out_level = str(sec.get("exposed_level", "warning"))
        max_level = levels[key]
        if _LEVEL_RANK.get(out_level, 9) > _LEVEL_RANK.get(max_level, 0):
            errors.append(f"LEVEL_EXCEEDS_EXPOSED:{key}")
        b = bucket.get(out_level, 3)
        if b < last_bucket:
            errors.append(f"ORDER_NOT_WARNING_FIRST:{key}")
        last_bucket = max(last_bucket, b)
    return errors


def plan_remediation(attempt: int, audit_action: str) -> str:
    """위반 시 결정적 처리 순서(감수 46차 §11 — 무제한 재생성 금지).

    attempt 0 위반 → REVISE(violation code로 1회 재작성) / 재작성도 위반 →
    REGENERATE_WITHOUT_RISK(risk payload 없이 suppressed guard로 전체
    재생성) / 그래도 위반 → BLOCK(안전 fallback·응답 차단). 위반 초안을
    그대로 사용자에게 전달하는 경로는 없다.
    """
    if audit_action == "ALLOW":
        return "DELIVER"
    if attempt <= MAX_RISK_REVISION_ATTEMPTS - 1:
        return "REVISE"
    if attempt == MAX_RISK_REVISION_ATTEMPTS:
        return "REGENERATE_WITHOUT_RISK"
    return "BLOCK"


def claim_audit_policy_hash() -> str:
    """claim audit 정책 해시(감수 46차 §16) — 변경=expose 재감수 신호."""
    policy = {
        "version": RISK_CLAIM_AUDIT_VERSION,
        "prohibited_patterns": {k: list(v) for k, v in
                                sorted(_PROHIBITED_PATTERNS.items())},
        "escalation_patterns": list(_ESCALATION_PATTERNS),
        "qualifier_phrases": {k: list(v) for k, v in
                              sorted(_QUALIFIER_PHRASES.items())},
        "negation_handling": "매치 직후 25자 내 부정 표지(아닙니다 등)="
                             "위반 아님(감수 48차 FP 코퍼스) — 잔여 오탐은"
                             " 재작성 경로로 흡수, LLM 재판정 금지",
        "negation_markers": list(_NEGATION_MARKERS),
        "envelope_invariants": "episode_key ⊆ llm episodes·중복 실패·"
                               "warning-first 순서·exposed level 초과 실패"
                               "(validate_risk_guidance_envelope)",
        "max_revision_attempts": MAX_RISK_REVISION_ATTEMPTS,
        "remediation_order": "REVISE(1회) → REGENERATE_WITHOUT_RISK →"
                             " BLOCK — 위반 초안 직접 전달 경로 없음",
        "audit_scope": "risk section(episode별) + whole answer 병행",
    }
    return hashlib.sha256(json.dumps(
        policy, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


__all__ = [
    "MAX_RISK_REVISION_ATTEMPTS",
    "RISK_CLAIM_AUDIT_VERSION",
    "audit_generated_risk_claims",
    "audit_risk_sections",
    "claim_audit_policy_hash",
    "plan_remediation",
    "validate_risk_guidance_envelope",
]
