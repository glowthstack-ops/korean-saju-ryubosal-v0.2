"""INJECTED 위험 생성 실호출 파이프라인(감수 59차 §14 순서 1~8).

EXPOSE 계열 모드에서 INJECTED 요청의 **생성→감사→재작성→재생성→renderer→
최종 감사** 전 과정을 결정적 상태기로 배선한다. LLM 호출과 renderer는
callable 주입(순수 조립 — 사이드이펙트는 호출부).

핵심 계약:
- **attempt별 독립 ProviderRequest**(감수 59차 §10): INITIAL/REVISION_1/
  REGENERATE_WITHOUT_RISK은 서로 다른 요청이며 각각 직전에 모델 재해소·
  adapter 재검증·**전체 token 재계수**·block integrity·schema·context
  결속을 다시 통과해야 한다. 최초 count 재사용 금지.
- **GuidanceReferenceContext 동일 객체**(감수 59차 §11): 최초 INJECTED
  요청에서 1회 생성된 context를 schema 생성·초안 검증·REVISE·renderer·
  최종 감사가 전부 소비한다 — revision에서 ref 재발급·재정렬·order hash
  재생성 금지. REGENERATE 요청의 prompt/schema에는 사용 금지(감사 기록
  보존만).
- **REVISE 입력 최소화**(감수 59차 §12): violation codes·누락 required
  refs·필요 qualifier 종류·허용 exposed level·원 초안만 — 내부 canonical
  episode ID·cause atom·manifest hash·감수 상태·clause hash 미포함.
- **rerouting=게이트 전체 재평가**(감수 59차 §4·§8): 미감수 모델로
  라우팅되면 risk 요소 일부 제거가 아니라 **BYPASS baseline으로 완전
  재조립**(canonical bytes가 원 baseline과 동일해야 함).
- **캐시 경로**(감수 59차 §8): risk-enabled 요청은 explicit caching을
  사용하지 않는다(cachedContent 미사용). implicit cache 적중이 관측되면
  cached_input을 별도 기록하되 undercount 비교는 항상 **전체 input**
  (cached+non-cached) 기준 — 할인 후 과금 token 비교 금지.
- 감사 통과 전 사용자 전달 경로 없음: DELIVER/BLOCK만 종결 상태.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field

from saju_engines.risk_claim_audit import (
    audit_rendered_output,
    audit_risk_sections,
    plan_remediation,
    validate_injected_guidance_presence,
    validate_risk_guidance_envelope,
)
from saju_engines.risk_exposure import (
    RISK_EXPOSURE_INSTRUCTION_BLOCK,
    RISK_EXPOSURE_SUPPRESSED_GUARD,
    RISK_SAFE_FALLBACK_TEMPLATE,
    GuidanceReferenceContext,
    RiskPromptBlock,
    verify_guidance_context,
    verify_risk_block_integrity,
)

from .token_counter_registry import (
    ProviderRequest,
    TokenCounterAdapter,
    resolve_expose_counter,
)

__all__ = ["ATTEMPT_KINDS", "RiskAttemptPlan", "build_revision_request",
           "build_regenerate_request", "canonical_request_bytes",
           "handle_rerouting", "preflight_provider_attempt",
           "run_injected_risk_flow"]

# attempt 종류(감수 59차 §10) — 각각 독립 ProviderRequest·독립 preflight.
ATTEMPT_KINDS = ("INITIAL", "REVISION_1", "REGENERATE_WITHOUT_RISK")

# REVISE 요청에 포함 가능한 정보 화이트리스트(감수 59차 §12) — 이 외의
# 내부 정보(canonical episode ID·cause atom·hash·감수 상태)는 주입 금지.
_REVISION_INPUT_FIELDS = ("violation_codes", "missing_required_refs",
                          "required_qualifier_kinds", "allowed_levels",
                          "draft")


def canonical_request_bytes(request: ProviderRequest) -> bytes:
    """ProviderRequest canonical 직렬화 — baseline 동일성 대조용."""
    return json.dumps({
        "system": list(request.system_messages),
        "user": list(request.user_messages),
        "output_schema": request.output_schema,
        "tool_schema": request.tool_schema,
        "generation_config": request.generation_config,
    }, ensure_ascii=False, sort_keys=True).encode()


@dataclass(frozen=True)
class RiskAttemptPlan:
    """attempt 1건의 실행 계획 — preflight 통과 후에만 llm_call 허용."""

    kind: str  # ATTEMPT_KINDS
    request: ProviderRequest
    counted_tokens: int
    uses_risk_schema: bool
    preflight_issues: tuple[str, ...] = field(default_factory=tuple)


def build_revision_request(
    original: ProviderRequest,
    *,
    draft: str,
    violation_codes: list[str],
    missing_required_refs: list[str],
    required_qualifier_kinds: list[str],
    allowed_levels: list[str],
) -> ProviderRequest:
    """REVISION_1 요청 조립(감수 59차 §10·§12 — 입력 최소화).

    원 요청(instruction·risk block·schema 포함)에 위반 요약과 원 초안만
    덧붙인다. 내부 식별자(canonical episodeKey·risk_id·cause atom·hash)는
    어떤 필드로도 넣지 않는다 — guidance 참조는 opaque ref(rg1…)만.
    """
    payload = {
        "violation_codes": sorted(set(violation_codes)),
        "missing_required_refs": sorted(set(missing_required_refs)),
        "required_qualifier_kinds": sorted(set(required_qualifier_kinds)),
        "allowed_levels": sorted(set(allowed_levels)),
    }
    revision_note = (
        "[재작성 요청] 직전 초안이 위험 표현 계약을 위반했다. 아래 위반"
        " 요약을 반영해 같은 내용을 다시 작성하라. 위반 요약: "
        + json.dumps(payload, ensure_ascii=False, sort_keys=True)
        + "\n[직전 초안]\n" + draft)
    return ProviderRequest(
        system_messages=original.system_messages,
        user_messages=(*original.user_messages, revision_note),
        output_schema=original.output_schema,
        tool_schema=original.tool_schema,
        generation_config=original.generation_config)


def build_regenerate_request(
        baseline: ProviderRequest) -> ProviderRequest:
    """REGENERATE_WITHOUT_RISK 요청(감수 59차 §10) — risk 요소 전무.

    baseline은 위험 주입 **전**의 원 요청(BYPASS 형태)이어야 하며, 여기에
    suppressed guard만 부착한다. instruction·risk block·risk-enabled
    schema·guidance context 흔적이 조금이라도 남으면 계약 위반(fixture
    강제) — canonical bytes가 baseline+guard와 정확히 일치해야 한다.
    """
    return ProviderRequest(
        system_messages=baseline.system_messages,
        user_messages=(*baseline.user_messages,
                       RISK_EXPOSURE_SUPPRESSED_GUARD),
        output_schema=baseline.output_schema,
        tool_schema=baseline.tool_schema,
        generation_config=baseline.generation_config)


def handle_rerouting(
    new_resolved_model_id: str,
    manifest_counters: list[dict],
) -> str:
    """모델 rerouting 처리 판정(감수 59차 §4·§8).

    반환: "REEVALUATE_GATE"(감수된 adapter 존재 — 새 모델 기준으로 게이트
    **전체** 재평가: 재해소→suspension 재검사→전체 재계수→transport schema
    재선택) 또는 "REBUILD_BYPASS"(미감수 — 기존 요청의 risk 요소 일부
    제거가 아니라 baseline BYPASS 요청으로 완전 재조립).
    """
    adapter = resolve_expose_counter(new_resolved_model_id,
                                     manifest_counters)
    return "REEVALUATE_GATE" if adapter is not None else "REBUILD_BYPASS"


def preflight_provider_attempt(
    kind: str,
    request: ProviderRequest,
    *,
    resolved_model_id: str,
    manifest_counters: list[dict],
    adapter: TokenCounterAdapter | None,
    guidance_context: GuidanceReferenceContext | None,
    request_context_id: str,
    final_token_limit: int,
    expects_risk_block: bool,
) -> RiskAttemptPlan:
    """provider 호출 직전 검증(감수 59차 §14-6) — attempt마다 전부 재실행.

    ①모델-adapter 재해소(manifest 대조 — VALIDATED 선언만으로 불충분)
    ②**전체 token 재계수**(이전 attempt count 재사용 금지)+한도 ③risk
    block 단일 삽입 integrity(주입 attempt만) ④REGENERATE에 risk 요소
    잔재 금지 ⑤guidance context 결속(주입 attempt만 — 타 요청 재사용
    차단). 하나라도 실패=해당 attempt 실행 금지(issues에 사유).
    """
    issues: list[str] = []
    if kind not in ATTEMPT_KINDS:
        issues.append("UNKNOWN_ATTEMPT_KIND")
    resolved = resolve_expose_counter(resolved_model_id, manifest_counters)
    if resolved is None or adapter is None \
            or resolved.model_id != adapter.model_id:
        issues.append("TOKENIZER_UNAVAILABLE")
    counted = 0
    if adapter is not None:
        counted = adapter.count_request(request)
        if counted > final_token_limit:
            issues.append("FINAL_PROMPT_TOKEN_OVERFLOW")
    joined = "\n".join(request.user_messages)
    if expects_risk_block:
        block = _extract_risk_block(joined)
        if block is None or not verify_risk_block_integrity(joined, block):
            issues.append("RISK_BLOCK_INTEGRITY_ERROR")
        if guidance_context is None:
            issues.append("GUIDANCE_CONTEXT_MISSING")
        else:
            issues.extend(verify_guidance_context(
                guidance_context, request_context_id))
    else:
        # REGENERATE/비주입 attempt: risk 요소 잔재=계약 위반(§10).
        if ("BEGIN_RISK_BLOCK" in joined
                or RISK_EXPOSURE_INSTRUCTION_BLOCK in joined):
            issues.append("RISK_RESIDUE_IN_NON_RISK_ATTEMPT")
    return RiskAttemptPlan(
        kind=kind, request=request, counted_tokens=counted,
        uses_risk_schema=expects_risk_block,
        preflight_issues=tuple(issues))


def _extract_risk_block(prompt: str) -> RiskPromptBlock | None:
    """prompt의 marker 구간에서 RiskPromptBlock 재구성(부재/기형=None).

    checksum은 marker에 기록된 값을 그대로 쓰고, 본문 재해시 일치 여부는
    verify_risk_block_integrity가 판정한다(위조 marker=불일치 실패).
    """
    marker = "BEGIN_RISK_BLOCK:"
    idx = prompt.find(marker)
    if idx < 0:
        return None
    rest = prompt[idx + len(marker):]
    first_line, _, tail = rest.partition("\n")
    body, sep, _ = tail.partition("\nEND_RISK_BLOCK")
    if not sep:
        return None
    return RiskPromptBlock(serialized_text=body,
                           content_hash=first_line.strip(),
                           compression_mode="UNKNOWN",
                           exact_token_count=0)


def _audit_response(
    response_envelope: dict,
    *,
    guidance_context: GuidanceReferenceContext,
    llm_episodes: list[dict],
    whole_answer: str,
) -> tuple[list[str], dict]:
    """초안/재작성 공용 감사 — envelope 불변식 + episode별 claim audit."""
    guidance = response_envelope.get("risk_guidance")
    issues = list(validate_injected_guidance_presence(
        guidance, llm_episodes))
    ref_map = dict(guidance_context.guidance_ref_map)
    issues += validate_risk_guidance_envelope(
        guidance or [], llm_episodes,
        expected_order_hash=guidance_context.llm_episode_order_hash,
        ref_map=ref_map)
    sections = [{
        "episode_key": str(g.get("guidance_ref", "")),
        "exposed_level": str(g.get("exposed_level", "warning")),
        "required_qualifiers": g.get("required_qualifiers") or [],
        "prohibited_phrases": g.get("prohibited_phrases") or [],
        "text": str(g.get("text", "")),
    } for g in (guidance or [])]
    section_audit = audit_risk_sections(sections, whole_answer)
    if section_audit.get("action") != "ALLOW":
        issues += [f"{v.get('code')}:{v.get('episode_key')}"
                   for v in section_audit.get("violations", [])]
    return issues, section_audit


def run_injected_risk_flow(
    *,
    initial_request: ProviderRequest,
    baseline_request: ProviderRequest,
    guidance_context: GuidanceReferenceContext,
    request_context_id: str,
    llm_episodes: list[dict],
    resolved_model_id: str,
    manifest_counters: list[dict],
    adapter: TokenCounterAdapter | None,
    final_token_limit: int,
    llm_call: Callable[[ProviderRequest], dict],
    renderer: Callable[[str], str],
    allowed_levels: list[str] | None = None,
) -> dict:
    """INJECTED 실호출 상태기(감수 59차 §14 — DELIVER/BLOCK만 종결).

    INITIAL → 감사 → (위반) REVISION_1 → 감사 → (위반)
    REGENERATE_WITHOUT_RISK → renderer → **최종 문자열 감사** → DELIVER.
    어느 attempt든 preflight 실패=그 attempt 실행 없이 다음 단계(주입
    attempt 실패는 REGENERATE로, REGENERATE 실패는 BLOCK). llm_call은
    {"answer": str, "envelope": dict|None} 반환 계약.

    반환: {"outcome": DELIVER|BLOCK, "final_text", "attempts": [...],
    "final_audit_issues"}.
    """
    attempts: list[dict] = []

    def _run_risk_attempt(kind: str,
                          request: ProviderRequest) -> dict | None:
        plan = preflight_provider_attempt(
            kind, request, resolved_model_id=resolved_model_id,
            manifest_counters=manifest_counters, adapter=adapter,
            guidance_context=guidance_context,
            request_context_id=request_context_id,
            final_token_limit=final_token_limit, expects_risk_block=True)
        record: dict = {"kind": kind,
                        "counted_tokens": plan.counted_tokens,
                        "preflight_issues": list(plan.preflight_issues)}
        attempts.append(record)
        if plan.preflight_issues:
            return None
        result = llm_call(request)
        issues, section_audit = _audit_response(
            result.get("envelope") or {},
            guidance_context=guidance_context,
            llm_episodes=llm_episodes,
            whole_answer=str(result.get("answer", "")))
        record["audit_issues"] = issues
        record["audit_action"] = ("ALLOW" if not issues
                                  else section_audit.get("action", "BLOCK"))
        return {"answer": str(result.get("answer", "")),
                "envelope": result.get("envelope") or {},
                "issues": issues}

    # INITIAL(attempt 0) → 필요 시 REVISION_1(attempt 1) — plan_remediation
    # 상태기(REVISE 1회 상한) 그대로.
    outcome = _run_risk_attempt("INITIAL", initial_request)
    final_answer: str | None = None
    if outcome is not None and not outcome["issues"]:
        final_answer = outcome["answer"]
    elif outcome is not None:
        step = plan_remediation(0, "REVISE_REQUIRED")
        if step == "REVISE":
            guidance = outcome["envelope"].get("risk_guidance") or []
            revision = build_revision_request(
                initial_request, draft=outcome["answer"],
                violation_codes=outcome["issues"],
                missing_required_refs=[
                    i.split(":", 1)[1] for i in outcome["issues"]
                    if i.startswith("MISSING_REQUIRED_RISK_EPISODE:")],
                required_qualifier_kinds=[
                    str(q) for g in guidance
                    for q in (g.get("required_qualifiers") or [])],
                allowed_levels=allowed_levels or ["warning"])
            revised = _run_risk_attempt("REVISION_1", revision)
            if revised is not None and not revised["issues"]:
                final_answer = revised["answer"]
    if final_answer is None:
        # REGENERATE_WITHOUT_RISK(감수 59차 §10·§11): baseline 완전
        # 재조립 — guidance context는 prompt/schema에 사용 금지.
        regen = build_regenerate_request(baseline_request)
        plan = preflight_provider_attempt(
            "REGENERATE_WITHOUT_RISK", regen,
            resolved_model_id=resolved_model_id,
            manifest_counters=manifest_counters, adapter=adapter,
            guidance_context=None, request_context_id=request_context_id,
            final_token_limit=final_token_limit, expects_risk_block=False)
        attempts.append({"kind": plan.kind,
                         "counted_tokens": plan.counted_tokens,
                         "preflight_issues": list(plan.preflight_issues)})
        if plan.preflight_issues:
            return {"outcome": "BLOCK",
                    "final_text": RISK_SAFE_FALLBACK_TEMPLATE,
                    "attempts": attempts,
                    "final_audit_issues": list(plan.preflight_issues)}
        final_answer = str(llm_call(regen).get("answer", ""))

    rendered = renderer(final_answer)
    # renderer 후 **최종 사용자 문자열** 감사(감수 59차 §14-7) — 통과 전
    # 전달 경로 없음. guidance context는 여기서도 동일 객체(발급 ref 대조).
    final_issues = audit_rendered_output(
        rendered, episode_keys=[k for _, k in
                                guidance_context.guidance_ref_map],
        issued_refs=guidance_context.refs())
    if final_issues:
        return {"outcome": "BLOCK",
                "final_text": RISK_SAFE_FALLBACK_TEMPLATE,
                "attempts": attempts, "final_audit_issues": final_issues}
    return {"outcome": "DELIVER", "final_text": rendered,
            "attempts": attempts, "final_audit_issues": []}


def request_shape_digest(request: ProviderRequest) -> str:
    """최종 provider request shape digest(감수 59차 §14-9) — reviewed
    corpus의 request digest와 동일 규칙(sha256/canonical)로 대조 가능."""
    return hashlib.sha256(canonical_request_bytes(request)).hexdigest()
