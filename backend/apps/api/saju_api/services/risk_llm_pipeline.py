"""INJECTED 위험 생성 실호출 파이프라인(감수 59차 §14 + 60차 §1~§10).

EXPOSE 계열 모드에서 INJECTED 요청의 **생성→감사→재작성→재생성→renderer→
최종 감사** 전 과정을 결정적 상태기로 배선한다. LLM 호출과 renderer는
callable 주입(순수 조립 — 사이드이펙트는 호출부).

핵심 계약:
- **attempt별 독립 ProviderRequest·재계수**(감수 59차 §10 + 60차 §1):
  INITIAL/REVISION_1/REGENERATE_WITHOUT_RISK은 서로 다른 요청이며 각각
  직전에 모델 재해소·adapter 재검증(suspension 최신 상태 포함)·**전체
  token 재계수**·block integrity·shape 대조·context 결속을 다시 통과한다.
  이전 attempt의 count·routing 결과 승계 금지.
- **요청 단위 불변 실행 context**(감수 60차 §2): manifest snapshot·
  guidance context·policy hash·baseline digest는 RiskExecutionContext에
  1회 고정 — attempt 간 manifest 재읽기로 버전이 섞이지 않는다. 단
  **suspension은 안전 차단 상태이므로 attempt마다 최신 공유 상태 재확인**
  (resolve_expose_counter 경유).
- **미감수 fallback에 위험 초안 미전송**(감수 60차 §3): REVISION_1 직전
  라우팅이 바뀌었으면 위험 초안을 포함한 revision을 어떤 모델로도 보내지
  않는다 — 즉시 REGENERATE_WITHOUT_RISK(baseline+guard)로 전환. 감수된
  모델로의 rerouting도 canary 초기에는 게이트 전체 재평가가 필요하므로
  위험 revision을 중단한다(보수 정책 — REROUTE_REQUIRES_GATE_REEVALUATION).
- **request shape 대조**(감수 60차 §5): 각 attempt의 **구조적** shape
  digest(동적 본문 제외 — attempt type·message role 배열·instruction/
  block 존재·schema hash·config shape·schemaVersion)가 reviewed corpus의
  shape digest 집합에 없으면 REQUEST_SHAPE_NOT_REVIEWED(해당 attempt
  실행 금지).
- **REVISE 입력 최소화**(감수 59차 §12): violation codes·누락 required
  refs·qualifier 종류·허용 level·원 초안만 — 내부 canonical episode ID·
  cause atom·manifest hash·감수 상태·clause hash 미포함.
- **terminal 3분리**(감수 60차 §8): DELIVER_GENERATED /
  DELIVER_SAFE_FALLBACK / BLOCK. 결정적 fallback도 renderer 후 최종
  감사를 통과해야 DELIVER_SAFE_FALLBACK — 실패 시에만 BLOCK. 감사 통과
  전 사용자 전달 경로 없음.
- **캐시 경로**(감수 60차 §7): risk-enabled 요청은 explicit caching
  미사용. cached_input>0 관측은 record_cache_observation으로 identity
  전역 차단(CACHE_PATH_UNVALIDATED — 별도 감수 전 재활성화 금지).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field

from saju_engines.risk_claim_audit import (
    audit_rendered_output,
    audit_risk_sections,
    claim_audit_policy_hash,
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
    expose_policy_hash,
    verify_guidance_context,
    verify_risk_block_integrity,
)

from .token_counter_registry import (
    ProviderRequest,
    TokenCounterAdapter,
    adapter_identity_hash,
    resolve_expose_counter,
)

__all__ = ["ATTEMPT_KINDS", "RiskAttemptPlan", "RiskExecutionContext",
           "build_risk_execution_context", "build_revision_request",
           "build_regenerate_request", "canonical_request_bytes",
           "handle_rerouting", "preflight_provider_attempt",
           "request_shape_digest", "run_injected_risk_flow"]

# attempt 종류(감수 59차 §10) — 각각 독립 ProviderRequest·독립 preflight.
ATTEMPT_KINDS = ("INITIAL", "REVISION_1", "REGENERATE_WITHOUT_RISK")
# terminal 결과(감수 60차 §8) — 차단과 전달을 동시에 표현하지 않는다.
TERMINAL_OUTCOMES = ("DELIVER_GENERATED", "DELIVER_SAFE_FALLBACK", "BLOCK")


def canonical_request_bytes(request: ProviderRequest) -> bytes:
    """ProviderRequest canonical 직렬화 — baseline 동일성 대조용."""
    return json.dumps({
        "system": list(request.system_messages),
        "user": list(request.user_messages),
        "output_schema": request.output_schema,
        "tool_schema": request.tool_schema,
        "generation_config": request.generation_config,
    }, ensure_ascii=False, sort_keys=True).encode()


def _schema_structure_hash(schema_text: str) -> str:
    """schema **구조 골격** hash(감수 60차 §5 의도 보존 — P1 교정).

    실서비스 INJECTED의 output schema는 episode 구성에 따라 guidance_ref
    enum·maxItems가 매 요청 달라진다 — 내용 hash를 쓰면 reviewed corpus와
    항상 불일치해 모든 INJECTED가 REQUEST_SHAPE_NOT_REVIEWED로 차단된다
    (fail-open이 아니라 fail-shut 결함). 동적 값(enum 목록·개수 상한)을
    자리표시자로 치환한 구조만 hash — 필드·타입·계약 구조가 바뀌면 여전히
    digest가 달라진다.
    """
    try:
        parsed = json.loads(schema_text)
    except ValueError:
        return hashlib.sha256(schema_text.encode()).hexdigest()

    def _skeleton(obj: object) -> object:
        if isinstance(obj, dict):
            return {k: ("<enum>" if k == "enum"
                        else "<n>" if k in ("minItems", "maxItems",
                                            "minLength", "maxLength")
                        else _skeleton(v))
                    for k, v in obj.items()}
        if isinstance(obj, list):
            return [_skeleton(x) for x in obj]
        return obj

    return hashlib.sha256(json.dumps(
        _skeleton(parsed), ensure_ascii=False,
        sort_keys=True).encode()).hexdigest()


def request_shape_digest(kind: str, request: ProviderRequest,
                         provider_request_schema_version: str = "1") -> str:
    """구조적 request shape digest(감수 60차 §5).

    동적 본문(질문 원문·초안·violation span·token 수·request ID·시각·
    schema의 요청별 enum/상한)은 제외하고 attempt type·message role 배열·
    risk instruction/block 존재·schema **구조 골격** hash·generation
    config shape·schemaVersion만 표현한다 — reviewed corpus의 shape
    digest 집합과 대조 가능해야 한다.
    """
    joined = "\n".join(request.user_messages)
    gen_keys: list[str] = []
    if request.generation_config:
        try:
            gen_keys = sorted(json.loads(request.generation_config))
        except ValueError:
            gen_keys = ["<unparseable>"]
    shape = {
        "attempt_kind": kind,
        "system_message_count": len(request.system_messages),
        "user_message_count": len(request.user_messages),
        "has_risk_instruction": RISK_EXPOSURE_INSTRUCTION_BLOCK in joined,
        "has_risk_block": "BEGIN_RISK_BLOCK:" in joined,
        "risk_block_wrapper": "BEGIN/END_RISK_BLOCK:v1",
        "has_suppressed_guard": RISK_EXPOSURE_SUPPRESSED_GUARD in joined,
        "has_revision_note": "[재작성 요청]" in joined,
        "output_schema_hash": (_schema_structure_hash(
            request.output_schema)
            if request.output_schema else None),
        "tool_schema_hash": (_schema_structure_hash(request.tool_schema)
            if request.tool_schema else None),
        "generation_config_keys": gen_keys,
        "provider_request_schema_version": provider_request_schema_version,
    }
    return hashlib.sha256(json.dumps(
        shape, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class RiskExecutionContext:
    """요청 단위 불변 실행 context(감수 60차 §2).

    하나의 사용자 요청 안에서 INITIAL→REVISION→REGENERATE→renderer→최종
    감사가 **동일한 감수 정본**을 소비한다 — manifest 파일이 중간에
    교체돼도 현재 요청은 최초 snapshot으로 끝까지 처리(다음 요청부터 새
    snapshot). suspension은 여기 고정하지 않는다(attempt마다 최신 확인).
    """

    request_context_id: str
    manifest_counters: tuple[dict, ...]
    guidance_context: GuidanceReferenceContext
    expose_policy_hash: str
    claim_audit_policy_hash: str
    baseline_request_digest: str
    initial_resolved_model_id: str


def build_risk_execution_context(
    request_context_id: str,
    *,
    manifest_counters: list[dict],
    guidance_context: GuidanceReferenceContext,
    baseline_request: ProviderRequest,
    resolved_model_id: str,
) -> RiskExecutionContext:
    """실행 context 1회 조립 — 요청당 한 번, attempt 간 재생성 금지."""
    return RiskExecutionContext(
        request_context_id=request_context_id,
        manifest_counters=tuple(manifest_counters),
        guidance_context=guidance_context,
        expose_policy_hash=expose_policy_hash(),
        claim_audit_policy_hash=claim_audit_policy_hash(),
        baseline_request_digest=hashlib.sha256(
            canonical_request_bytes(baseline_request)).hexdigest(),
        initial_resolved_model_id=resolved_model_id)


@dataclass(frozen=True)
class RiskAttemptPlan:
    """attempt 1건의 실행 계획·관측(감수 60차 §1 필드) — preflight 통과
    후에만 llm_call 허용."""

    kind: str  # ATTEMPT_KINDS
    request: ProviderRequest
    counted_tokens: int
    uses_risk_schema: bool
    resolved_model_id: str = ""
    provider_request_digest: str = ""
    request_shape_digest: str = ""
    counter_validation_identity: str = ""
    available_response_tokens: int = 0
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
    suppressed guard만 부착한다(canonical diff=guard 하나). instruction·
    risk block·risk-enabled schema·guidance context 흔적이 조금이라도
    남으면 계약 위반(fixture 강제).
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
    manifest_counters: list[dict] | tuple[dict, ...],
) -> str:
    """모델 rerouting 처리 판정(감수 59차 §4·§8 + 60차 §3).

    반환: "REEVALUATE_GATE"(감수된 adapter 존재 — 새 모델 기준으로 게이트
    **전체** 재평가 필요) 또는 "REBUILD_BYPASS"(미감수 — risk 요소 일부
    제거가 아니라 baseline BYPASS 요청으로 완전 재조립). **위험 초안이
    이미 존재하는 REVISION 단계에서는 어느 쪽이든 위험 revision을
    중단한다**(초안을 미감수 모델에 보내지 않음·감수 모델도 게이트 재평가
    전 전송 금지) — run_injected_risk_flow가 REGENERATE로 전환.
    """
    adapter = resolve_expose_counter(new_resolved_model_id,
                                     list(manifest_counters))
    return "REEVALUATE_GATE" if adapter is not None else "REBUILD_BYPASS"


def preflight_provider_attempt(
    kind: str,
    request: ProviderRequest,
    *,
    resolved_model_id: str,
    manifest_counters: list[dict] | tuple[dict, ...],
    adapter: TokenCounterAdapter | None,
    guidance_context: GuidanceReferenceContext | None,
    request_context_id: str,
    final_token_limit: int,
    expects_risk_block: bool,
    reviewed_shape_digests: frozenset[str] | None = None,
) -> RiskAttemptPlan:
    """provider 호출 직전 검증(감수 59차 §14-6 + 60차 §1·§5·§6) —
    attempt마다 전부 재실행.

    ①모델-adapter 재해소(manifest 대조+**최신 suspension·marker·topology**
    — resolve_expose_counter 경유) ②**전체 token 재계수**(이전 attempt
    count 재사용 금지)+한도 ③risk block 단일 삽입 integrity(주입 attempt
    만) ④REGENERATE에 risk 요소 잔재 금지 ⑤guidance context 결속(주입
    attempt만) ⑥구조적 shape digest가 reviewed 집합에 존재(집합 지정 시).
    하나라도 실패=해당 attempt 실행 금지(issues에 사유).
    """
    issues: list[str] = []
    if kind not in ATTEMPT_KINDS:
        issues.append("UNKNOWN_ATTEMPT_KIND")
    resolved = resolve_expose_counter(resolved_model_id,
                                      list(manifest_counters))
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
    shape = request_shape_digest(
        kind, request,
        adapter.request_schema_version if adapter is not None else "1")
    if reviewed_shape_digests is not None \
            and shape not in reviewed_shape_digests:
        issues.append("REQUEST_SHAPE_NOT_REVIEWED")
    return RiskAttemptPlan(
        kind=kind, request=request, counted_tokens=counted,
        uses_risk_schema=expects_risk_block,
        resolved_model_id=resolved_model_id,
        provider_request_digest=hashlib.sha256(
            canonical_request_bytes(request)).hexdigest(),
        request_shape_digest=shape,
        counter_validation_identity=(
            adapter_identity_hash(adapter) if adapter is not None else ""),
        available_response_tokens=max(0, final_token_limit - counted),
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
    execution_context: RiskExecutionContext,
    llm_episodes: list[dict],
    adapter: TokenCounterAdapter | None,
    final_token_limit: int,
    llm_call: Callable[[ProviderRequest], dict],
    renderer: Callable[[str], str],
    resolve_model: Callable[[], str] | None = None,
    reviewed_shape_digests: frozenset[str] | None = None,
    allowed_levels: list[str] | None = None,
    drift_observer: Callable[[str, int, int, int, str], None]
    | None = None,
) -> dict:
    """INJECTED 실호출 상태기(감수 59차 §14 + 60차 §3·§8·§9).

    INITIAL→감사→(위반) REVISION_1→감사→(위반) REGENERATE_WITHOUT_RISK→
    renderer→최종 감사→DELIVER_GENERATED. 어느 단계든 실패가 이어지면
    결정적 safe fallback을 생성하되 **fallback도 renderer 후 최종 감사를
    통과해야 DELIVER_SAFE_FALLBACK** — 실패 시에만 BLOCK. REVISION 직전
    라우팅 변경이 감지되면(resolve_model) 위험 초안을 어떤 모델에도 보내지
    않고 REGENERATE로 직행(감수 60차 §3).

    llm_call 반환 계약: {"answer": str, "envelope": dict|None,
    "provider_reported_input": int|None, "cached_input": int}. **drift·
    cache 검사는 응답 수신 직후·전달 판정 전**(통합 감수 §2): counted <
    reported(undercount) 또는 cached_input>0이면 drift_observer로 즉시
    identity 차단을 기록하고 **그 응답 자체를 폐기**(TOKEN_UNDERCOUNT_
    DETECTED/CACHE_PATH_UNVALIDATED) — 이후 위험 attempt·REGENERATE는
    preflight의 최신 suspension 확인이 차단하므로 위험 없는 종결
    (DELIVER_SAFE_FALLBACK/BLOCK)로 수렴한다.
    """
    ctx = execution_context
    guidance_context = ctx.guidance_context
    counters = list(ctx.manifest_counters)
    attempts: list[dict] = []

    def _current_model() -> str:
        return (resolve_model() if resolve_model is not None
                else ctx.initial_resolved_model_id)

    def _record(plan: RiskAttemptPlan) -> dict:
        record = {"kind": plan.kind,
                  "resolved_model_id": plan.resolved_model_id,
                  "provider_request_digest": plan.provider_request_digest,
                  "request_shape_digest": plan.request_shape_digest,
                  "counter_validation_identity":
                      plan.counter_validation_identity,
                  "counted_tokens": plan.counted_tokens,
                  "available_response_tokens":
                      plan.available_response_tokens,
                  "preflight_issues": list(plan.preflight_issues)}
        attempts.append(record)
        return record

    def _run_risk_attempt(kind: str, request: ProviderRequest,
                          model_id: str) -> dict | None:
        plan = preflight_provider_attempt(
            kind, request, resolved_model_id=model_id,
            manifest_counters=counters, adapter=adapter,
            guidance_context=guidance_context,
            request_context_id=ctx.request_context_id,
            final_token_limit=final_token_limit, expects_risk_block=True,
            reviewed_shape_digests=reviewed_shape_digests)
        record = _record(plan)
        if plan.preflight_issues:
            return None
        try:
            result = llm_call(request)
        except Exception:  # noqa: BLE001 — provider 장애=attempt 실패
            # (재시도는 llm_call 내부 소관) → 상태기가 REGENERATE/fallback
            # 으로 수렴. 사용자 500 금지 — DELIVER_*/BLOCK만 종결.
            record["audit_issues"] = ["PROVIDER_CALL_FAILED"]
            record["audit_action"] = "DISCARDED"
            return None
        # drift·cache 검사(통합 감수 §2 — **전달 판정보다 먼저**): 감수된
        # token 조건을 벗어난 응답은 내용이 안전해도 폐기한다.
        # 감수 62차: undercount 판정은 shape별 검증 프레이밍 오버헤드를
        # 가산한 effective counted 기준(범용 tolerance 금지). 캐시 적중은
        # cache 경로가 corpus로 검증된 adapter에서는 관측 필드로만 남긴다
        # — undercount 검사는 캐시와 무관하게 존속.
        reported = result.get("provider_reported_input")
        cached = int(result.get("cached_input") or 0)
        record["provider_reported_input"] = reported
        record["cached_input"] = cached
        framing_overhead = (adapter.framing_overhead_for(
            plan.request_shape_digest)
            if adapter is not None
            and hasattr(adapter, "framing_overhead_for") else 0)
        effective_counted = plan.counted_tokens + framing_overhead
        if drift_observer is not None and reported is not None:
            drift_observer(kind, effective_counted, int(reported),
                           cached, plan.provider_request_digest)
        integrity_issues: list[str] = []
        if reported is not None and effective_counted < int(reported):
            integrity_issues.append("TOKEN_UNDERCOUNT_DETECTED")
        cache_path_ok = bool(adapter is not None and getattr(
            adapter, "cache_path_validated", False))
        if cached > 0 and not cache_path_ok:
            integrity_issues.append("CACHE_PATH_UNVALIDATED")
        if integrity_issues:
            record["audit_issues"] = integrity_issues
            record["audit_action"] = "DISCARDED"
            return {"answer": "", "envelope": {},
                    "issues": integrity_issues}
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

    outcome = _run_risk_attempt(
        "INITIAL", initial_request, _current_model())
    final_answer: str | None = None
    delivery_kind = "DELIVER_GENERATED"
    if outcome is not None and not outcome["issues"]:
        final_answer = outcome["answer"]
    elif outcome is not None \
            and plan_remediation(0, "REVISE_REQUIRED") == "REVISE":
        # REVISION 직전 라우팅 재확인(감수 60차 §3): 모델이 바뀌었으면
        # 위험 초안을 포함한 revision을 어떤 모델에도 보내지 않는다 —
        # REBUILD_BYPASS는 물론, 감수된 모델(REEVALUATE_GATE)도 게이트
        # 전체 재평가 전에는 전송 금지(보수 정책) → REGENERATE 직행.
        revision_model = _current_model()
        if revision_model != ctx.initial_resolved_model_id:
            attempts.append({
                "kind": "REVISION_1", "skipped": True,
                "reason": ("REROUTE_"
                           + handle_rerouting(revision_model, counters)),
            })
        else:
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
            revised = _run_risk_attempt(
                "REVISION_1", revision, revision_model)
            if revised is not None and not revised["issues"]:
                final_answer = revised["answer"]

    if final_answer is None:
        # REGENERATE_WITHOUT_RISK(감수 59차 §10·§11): baseline 완전
        # 재조립 — guidance context는 prompt/schema에 사용 금지.
        regen = build_regenerate_request(baseline_request)
        plan = preflight_provider_attempt(
            "REGENERATE_WITHOUT_RISK", regen,
            resolved_model_id=_current_model(),
            manifest_counters=counters, adapter=adapter,
            guidance_context=None,
            request_context_id=ctx.request_context_id,
            final_token_limit=final_token_limit, expects_risk_block=False,
            reviewed_shape_digests=reviewed_shape_digests)
        _record(plan)
        if not plan.preflight_issues:
            try:
                final_answer = str(llm_call(regen).get("answer", ""))
            except Exception:  # noqa: BLE001 — REGENERATE도 장애=fallback
                attempts[-1]["audit_issues"] = ["PROVIDER_CALL_FAILED"]
                final_answer = None

    if final_answer is None:
        # 결정적 safe fallback(감수 60차 §8·§9) — 이 역시 renderer 후
        # 최종 감사를 통과해야 전달된다.
        final_answer = RISK_SAFE_FALLBACK_TEMPLATE
        delivery_kind = "DELIVER_SAFE_FALLBACK"

    def _final_audit(text: str) -> list[str]:
        return audit_rendered_output(
            text,
            episode_keys=[k for _, k in guidance_context.guidance_ref_map],
            issued_refs=guidance_context.refs())

    rendered = renderer(final_answer)
    final_issues = _final_audit(rendered)
    if not final_issues:
        return {"outcome": delivery_kind, "final_text": rendered,
                "attempts": attempts, "final_audit_issues": []}
    if delivery_kind == "DELIVER_GENERATED":
        # 생성물이 최종 감사 실패 → 결정적 fallback으로 1회 더(§9) —
        # fallback도 같은 renderer·최종 감사를 통과해야 전달.
        fallback_rendered = renderer(RISK_SAFE_FALLBACK_TEMPLATE)
        fallback_issues = _final_audit(fallback_rendered)
        if not fallback_issues:
            return {"outcome": "DELIVER_SAFE_FALLBACK",
                    "final_text": fallback_rendered,
                    "attempts": attempts,
                    "final_audit_issues": final_issues}
        final_issues = final_issues + fallback_issues
    return {"outcome": "BLOCK", "final_text": "",
            "attempts": attempts, "final_audit_issues": final_issues}
