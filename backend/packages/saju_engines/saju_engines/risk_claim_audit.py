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
import hmac
import json

from . import risk_engine_config

# claim audit 정책 버전(감수 46차 §16) — 패턴·qualifier registry·재작성
# 정책 변경 시 올린다(claim_audit_policy_hash 변경 = expose_pipeline 재감수
# 신호 — manifest 병기).
RISK_CLAIM_AUDIT_VERSION = "risk-claim-audit-r5.3.0"
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
        # 이중 부정(감수 49차 §6) — 위험 가능성을 강화하는 표현.
        "않는다고 볼 수는 없", "않는다고 볼 수는 아닙", "아닐 수는 없",
        "배제할 수 없",
        # 확률을 가장한 단정·부정 뒤 재강화(감수 50차 §8).
        "거의 확실하게", "사실상 결과가 정해진", "가능성이 매우 높아 피하기",
        "실질적으로 손해를 피하기", "사실상 종료 수순",
    ),
}
# 절 단위 부정문(감수 49차 §6 — 25자 창 기각·교체): 매치가 속한 **절**
# 안의 부정 표지만 인정한다. 절 경계=문장 부호 + 역접 접속("하지만" 뒤의
# 재단정을 앞 절의 부정이 덮지 못함). 이중 부정("아니라고 볼 수는 없다"
# 류)은 예외에서 제외 — 위험 가능성을 강화하는 표현이다.
_NEGATION_MARKERS = ("아닙니다", "아니에요", "않습니다", "아니며", "아니라")
_CLAUSE_BOUNDARIES = (".", "?", "!", "\n", "하지만", "그러나", "다만",
                      "반면", "오히려")
_DOUBLE_NEGATION = ("볼 수는 없", "볼 수는 아닙", "아닐 수는 없",
                    "배제할 수 없", "않는다고 볼 수")


def _clause_of(text: str, idx: int) -> str:
    """idx가 속한 절 — 절 경계(_CLAUSE_BOUNDARIES) 사이 구간."""
    start, end = 0, len(text)
    for b in _CLAUSE_BOUNDARIES:
        pos = text.rfind(b, 0, idx)
        if pos >= 0:
            start = max(start, pos + len(b))
        pos = text.find(b, idx)
        if pos >= 0:
            end = min(end, pos)
    return text[start:end]
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
        clause = _clause_of(answer, idx)
        if any(d in clause for d in _DOUBLE_NEGATION):
            return False  # 이중 부정=예외 아님(위험 강화 표현)
        return any(m in clause for m in _NEGATION_MARKERS)

    violations: list[dict] = []
    for code, patterns in _PROHIBITED_PATTERNS.items():
        for pat in patterns:
            idx = answer.find(pat)
            if idx < 0:
                continue
            negated = _negated(idx, pat)
            if negated:
                continue  # 같은 절 부정 — 예외(evidence는 위반만 기록)
            # 감사 evidence(감수 50차 §7 — canary 표본 재현용): 원문 장기
            # 저장 없이 span·절 정보만.
            clause = _clause_of(answer, idx)
            violations.append({
                "code": code, "matched": pat,
                "matched_span": [idx, idx + len(pat)],
                # 일반 운영 로그=clause_hash·길이만 사용(감수 51차 §10).
                # keyed HMAC(감수 52차 §6 — 사전 대입 추정 차단): 식별자·
                # 보안 증명이 아니라 표본 상관관계 확인 전용. 원문
                # clause_text는 감수용 제한 표본 전용·80자·단기 보존.
                "clause_hash": hmac.new(
                    risk_engine_config.RISK_AUDIT_HMAC_KEY,
                    clause.encode(), hashlib.sha256).hexdigest()[:16],
                "clause_len": len(clause),
                "clause_text": clause[:80],
                "negation_status": "not_negated",
                "exception_applied": False,
            })
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


# envelope 허용 필드(감수 49차 §5 — 알 수 없는 필드 금지).
_ENVELOPE_ALLOWED_FIELDS = frozenset(
    {"guidance_ref", "episode_key", "exposed_level", "identity_phrase_mode",
     "required_qualifiers", "prohibited_phrases", "text"})


def validate_risk_guidance_envelope(
    sections: list[dict], llm_episodes: list[dict],
    expected_order_hash: str | None = None,
    ref_map: dict[str, str] | None = None,
) -> list[str]:
    """구조화 risk_guidance 불변식(감수 48차 §10-⑤ + 49차 §5).

    **순서 SSOT(감수 51차 §7-C)**: llm_episodes는 미래 범위 필터 +
    critical exposed 하향 + warning-first 정렬이 전부 끝난 **최종
    llmRiskEpisodes**여야 한다 — presentationRecords·필터 전 순서 사용 금지.
    ①episode_key ⊆ 주입된 llmRiskEpisodes ②같은 key 중복 실패 ③R3
    warning-first 순서 유지 ④exposed level보다 높은 level 출력 실패
    ⑤**필수 episode 누락**(초기 정책: exposed WARNING 이상=출력 필수 —
    MISSING_REQUIRED_RISK_EPISODE, WATCH/ADVISORY는 생략 허용)
    ⑥schema: 미지 필드·빈 episode_key·빈 text 금지, level 입력 불일치.
    빈 목록=통과. 위반 시 해당 답변은 REVISE 경로로 보낸다(그대로 전달
    금지). risk_guidance 부재(None)와 빈 배열은 호출부가 구분한다 —
    본 함수는 '주입됐는데 생성이 비었는가'만 판정.
    """
    errors: list[str] = []
    if expected_order_hash is not None:
        from .risk_presentation import llm_episode_order_hash
        if llm_episode_order_hash(llm_episodes,
                                  ref_map) != expected_order_hash:
            # 잘못된 배열(records·필터 전 순서) 전달 탐지(감수 52차 §3).
            return ["EPISODE_ORDER_SOURCE_MISMATCH"]
    # opaque guidanceRef(감수 54차 §5): sections는 guidance_ref로 대응 —
    # 미등록 ref 실패·중복 실패·요청 간 재사용 불가(ref는 요청 단위 생성).
    allowed_keys = [str(e.get("guidanceRef") or e.get("episodeKey")
                        or e.get("episode_key") or "")
                    for e in llm_episodes]
    levels = {k: str(e.get("presentationLevel", "warning"))
              for k, e in zip(allowed_keys, llm_episodes, strict=True)}
    seen: set[str] = set()
    last_bucket = -1
    bucket = {"critical": 0, "warning": 0, "watch": 1, "advisory": 2}
    for sec in sections:
        unknown = set(sec) - _ENVELOPE_ALLOWED_FIELDS
        if unknown:
            errors.append(
                f"UNKNOWN_ENVELOPE_FIELD:{','.join(sorted(unknown))}")
        key = str(sec.get("guidance_ref") or sec.get("episode_key") or "")
        if not key:
            errors.append("EMPTY_EPISODE_KEY")
            continue
        if not str(sec.get("text", "")).strip():
            errors.append(f"EMPTY_SECTION_TEXT:{key}")
        if key not in levels:
            errors.append(f"UNREGISTERED_EPISODE_KEY:{key}")
            continue
        if key in seen:
            errors.append(f"DUPLICATE_EPISODE_KEY:{key}")
            continue
        seen.add(key)
        out_level = str(sec.get("exposed_level", "warning"))
        max_level = levels[key]
        if out_level != max_level:
            # 입력 exposed level과 정확 일치 요구(초과는 별도 코드).
            code = ("LEVEL_EXCEEDS_EXPOSED"
                    if _LEVEL_RANK.get(out_level, 9)
                    > _LEVEL_RANK.get(max_level, 0)
                    else "LEVEL_MISMATCH")
            errors.append(f"{code}:{key}")
        b = bucket.get(out_level, 3)
        if b < last_bucket:
            errors.append(f"ORDER_NOT_WARNING_FIRST:{key}")
        last_bucket = max(last_bucket, b)
    # 필수 episode 누락(감수 49차 §5): WARNING 이상은 출력 필수.
    for k, lv in levels.items():
        if _LEVEL_RANK.get(lv, 0) >= _LEVEL_RANK["warning"] and (
                k not in seen):
            errors.append(f"MISSING_REQUIRED_RISK_EPISODE:{k}")
    # 부분수열 검증(감수 50차 §5): watch/advisory 생략이 허용되므로 완전
    # 동일 비교가 아니라 — 생성 순서가 입력 순서(R3 warning-first)의
    # **부분수열**이어야 한다(B,A 같은 역전 금지).
    gen_keys = [str(s.get("guidance_ref") or s.get("episode_key") or "")
                for s in sections
                if str(s.get("guidance_ref") or s.get("episode_key")
                       or "") in levels]
    pos = {k: i for i, k in enumerate(allowed_keys)}
    indices = [pos[k] for k in gen_keys if k in pos]
    if indices != sorted(indices):
        errors.append("ORDER_NOT_SUBSEQUENCE")
    return errors


def validate_injected_guidance_presence(
    guidance: list[dict] | None, llm_episodes: list[dict],
) -> list[str]:
    """None vs 빈 배열 계약(감수 50차 §5): INJECTED인데 risk_guidance 필드
    자체가 없음(None)=schema 실패, []는 필수 WARNING episode가 없을 때만
    허용."""
    if guidance is None:
        return ["RISK_GUIDANCE_FIELD_MISSING"]
    if guidance == []:
        has_warning = any(
            _LEVEL_RANK.get(str(e.get("presentationLevel", "")), 0)
            >= _LEVEL_RANK["warning"] for e in llm_episodes)
        return (["EMPTY_GUIDANCE_WITH_REQUIRED_WARNING"]
                if has_warning else [])
    return validate_risk_guidance_envelope(guidance, llm_episodes)


# 내부 식별자 leak 검사 대상(감수 51차 §9): key 원문 외 prefix·내부 enum.
_INTERNAL_TOKEN_PATTERNS = ("reality:", "explicit:", "fallback:",
                            "conflict:", "presentationLevel",
                            "exposedPresentationLevel", "riskEpisodes")


def audit_rendered_output(final_text: str, episode_keys: list[str],
                          internal_ids: list[str] | None = None) -> list[str]:
    """renderer 후 최종 사용자 문자열 감사 보조(감수 50차 §6 + 51차 §9).

    검출: ①내부 episode_key 원문 ②key prefix·내부 enum 원문(reality: 등)
    ③내부 risk_id·cause_atom(internal_ids로 공급). 사용자에게는 감수된
    표시명만 나가야 한다. 전체 claim audit과 병행.
    """
    leaks = [f"INTERNAL_KEY_LEAKED:{k}" for k in episode_keys
             if k and k in final_text]
    leaks += [f"INTERNAL_TOKEN_LEAKED:{p}" for p in _INTERNAL_TOKEN_PATTERNS
              if p in final_text]
    for ident in internal_ids or []:
        if ident and ident in final_text:
            leaks.append(f"INTERNAL_ID_LEAKED:{ident}")
    return leaks


def build_risk_output_schema(llm_episodes: list[dict],
                             hard_max: int) -> dict:
    """INJECTED 전용 risk-enabled output schema(감수 52차 §7).

    BYPASS=기존 schema 그대로(request byte-identical), SUPPRESSED=기존
    schema+guard(risk_guidance 요구 금지 — 빈 위험 section 유도 방지),
    INJECTED만 본 schema. JSON Schema가 episode별 key-level 대응을 완전히
    표현하지 못하므로 후처리 validator(validate_risk_guidance_envelope)를
    반드시 병행한다.
    """
    keys = [str(e.get("guidanceRef") or e.get("episodeKey")
                or e.get("episode_key") or "")
            for e in llm_episodes]
    levels = sorted({str(e.get("presentationLevel", "warning"))
                     for e in llm_episodes})
    required_count = sum(
        1 for e in llm_episodes
        if str(e.get("presentationLevel", "")) in ("warning", "critical"))
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["main_answer", "risk_guidance"],
        "properties": {
            "main_answer": {"type": "string", "minLength": 1},
            "risk_guidance": {
                "type": "array",
                # 감수 53차 §9: hard_max는 상한일 뿐 — 실제 최종 episode
                # 수가 정확한 상한. minItems=필수 warning 수(watch/advisory
                # 생략 허용과 무충돌 — 특정 key 포함은 후처리 validator).
                "maxItems": min(hard_max, len(llm_episodes)),
                "minItems": required_count,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["guidance_ref", "exposed_level", "text"],
                    "properties": {
                        "guidance_ref": {"type": "string",
                                         "enum": [k for k in keys if k]},
                        "exposed_level": {"type": "string",
                                          "enum": levels},
                        "text": {"type": "string", "minLength": 1},
                    },
                },
            },
        },
    }


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
        "negation_handling": "절 단위(감수 49차 §6 — 25자 창 기각):"
                             " 매치가 속한 절의 부정 표지만 인정, 절 경계="
                             "문장 부호+역접 접속(하지만/그러나/다만/반면/"
                             "오히려 — 뒤 절 재단정은 별도 판정), 이중"
                             " 부정은 예외 제외. 잔여 오탐은 재작성 경로.",
        "negation_markers": list(_NEGATION_MARKERS),
        "clause_boundaries": list(_CLAUSE_BOUNDARIES),
        "double_negation_exclusions": list(_DOUBLE_NEGATION),
        "envelope_invariants": "episode_key ⊆ llm episodes·중복 실패·"
                               "warning-first 순서·exposed level 정확 일치"
                               "(초과=EXCEEDS·상이=MISMATCH)·WARNING 이상"
                               " 출력 필수(MISSING_REQUIRED — WATCH/"
                               "ADVISORY 생략 허용)·미지 필드/빈 key/빈"
                               " text 금지(감수 49차 §5)",
        "max_revision_attempts": MAX_RISK_REVISION_ATTEMPTS,
        "remediation_order": "REVISE(1회) → REGENERATE_WITHOUT_RISK →"
                             " BLOCK — 위반 초안 직접 전달 경로 없음",
        "audit_scope": "risk section(episode별) + whole answer 병행 +"
                       " renderer 후 최종 문자열(key 비노출 포함)",
        "evidence_log_policy": "일반 운영 로그=code·pattern·clause_hash·"
                               "길이만 / 감수용 제한 표본=clause_text 80자·"
                               "단기 보존·접근 제한(감수 51차 §10)",
        "evidence": "violation에 matched_span·clause_text(80자)·negation"
                    "_status 보존 — 원문 장기 저장 없음(감수 50차 §7)",
        "order_check": "부분수열(watch/advisory 생략 허용·역전 금지)",
        "presence_contract": "INJECTED+guidance None=schema 실패 / []="
                             "필수 warning 없을 때만 허용(감수 50차 §5)",
        "output_schema_by_disposition": "BYPASS=기존 schema(byte 불변) /"
                                        " SUPPRESSED=기존 schema+guard"
                                        "(risk_guidance 미요구) / INJECTED="
                                        "risk-enabled schema(additional"
                                        "Properties=false·maxItems=hard_max"
                                        "·episode_key/level enum)+후처리"
                                        " validator 병행(감수 52차 §7)",
        "clause_hash": "keyed HMAC-SHA256(16자) — 운영 secret 환경별·회전,"
                       " 식별자/보안 증명 사용 금지(감수 52차 §6)",
        "order_fingerprint": "llmEpisodeOrderHash — canonical identity"
                             "(episodeKey+level+required) 기준(감수 54차"
                             " §6), validator가 잘못된 배열 수신 탐지",
        "opaque_reference": "LLM payload=guidanceRef(rg1… — 요청 단위·순서"
                            " 기반·중복 없음·타 요청 재사용 불가·사용자"
                            " 출력 제거), canonical episodeKey는"
                            " guidanceRefMap(감사·후처리 전용 — LLM 직렬화"
                            " 제외)만 보유(감수 54차 §5)",
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
    "audit_rendered_output",
    "build_risk_output_schema",
    "validate_injected_guidance_presence",
    "validate_risk_guidance_envelope",
]
