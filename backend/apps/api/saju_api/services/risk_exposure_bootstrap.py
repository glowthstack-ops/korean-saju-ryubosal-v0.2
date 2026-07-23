"""위험 노출 startup 배선(감수 61차 §13 — freeze 후 통합 작업 ①②).

EXPOSE 계열 모드에서만 동작한다 — OFF/SHADOW에서는 모든 함수가 no-op
(기존 경로 byte 불변). 역할:

- **startup stamp**: 실물 Gemini adapter를 reviewed artifact의 corpus
  hash로 명시 등록하고 stamp_runtime_adapter_state로 runtime 상태를
  **검증 결과로 파생**(감수 59차 §3 — VALIDATED는 설정값이 아님).
- **runtime 입력 공급**: chat_service EXPOSE 분기에 counter(감수된
  adapter)·context limit(llm_config — 부재·0=게이트 BYPASS 유지)·
  reviewed request shape digest 집합(감수 60차 §5)을 공급한다.

주의: adapter counter는 provider countTokens **네트워크 호출**이다 —
EXPOSE 계열 요청에서만 사용되며(OFF/SHADOW 미실행), canary에서 지연·
실패율을 관측한다(실패=예외 전파 → 게이트 fail-closed).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from saju_engines import risk_engine_config

_logger = logging.getLogger("saju_api.risk")

_ARTIFACT_DIR = (Path(__file__).resolve().parents[4] / "compiled"
                 / "risk_adapter_validation")

__all__ = ["bootstrap_risk_exposure", "build_risk_payload",
           "exposure_runtime_inputs", "last_bootstrap_reason",
           "load_reviewed_shape_digests", "run_exposed_reading"]

# 마지막 bootstrap 실패 사유(감수 61차 후속 §4 — 조용한 무시 금지,
# 정적 reason 관측): 성공=None.
_LAST_BOOTSTRAP_REASON: str | None = None


def last_bootstrap_reason() -> str | None:
    return _LAST_BOOTSTRAP_REASON


def _exposure_mode_active() -> bool:
    return risk_engine_config.RISK_ENGINE_MODE in ("expose_canary",
                                                   "expose")


def _find_artifact(model_id: str) -> dict | None:
    """모델의 validation artifact 로드(손상=None — fail-closed).

    감수 62차: 동일 모델의 artifact가 2개 이상이면 fail-closed(None) —
    구 identity 파일이 남아 신규 대신 잡히는 사고 방지(운영 정리 강제).
    """
    if not _ARTIFACT_DIR.exists():
        return None
    matches: list[dict] = []
    for path in sorted(_ARTIFACT_DIR.glob("*.json")):
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
            native = artifact["nativeValidationCorpus"]
            if native["identity"].get("resolvedModelId") == model_id:
                matches.append(artifact)
        except (OSError, ValueError, KeyError, TypeError):
            return None
    if len(matches) > 1:
        _logger.error("risk_adapter_bootstrap: 동일 모델 artifact %d개 — "
                      "fail-closed(구 artifact 정리 필요) model=%s",
                      len(matches), model_id)
        return None
    return matches[0] if matches else None


def load_reviewed_shape_digests(model_id: str) -> frozenset[str]:
    """artifact의 reviewed request shape digest 집합(감수 60차 §5).

    부재·손상=빈 집합 — preflight가 모든 attempt를
    REQUEST_SHAPE_NOT_REVIEWED로 차단한다(fail-closed).
    """
    artifact = _find_artifact(model_id)
    if artifact is None:
        return frozenset()
    entries = artifact.get("reviewedRequestShapeDigests") or []
    return frozenset(str(e.get("digest", "")) for e in entries
                     if isinstance(e, dict) and e.get("digest"))


def _actual_worker_count_ok() -> bool:
    """worker=1 실측 검증(감수 61차 §13 — 설정값만으로 불충분).

    topology=single_host_single_process 선언 시 배포 환경 신호
    (WEB_CONCURRENCY·UVICORN_WORKERS·GUNICORN worker 표기)가 1을
    초과하면 부적격 — adapter를 등록하지 않아 전부 BYPASS. 신호 부재=
    uvicorn 기본(단일 프로세스)으로 간주하되, 배포 preflight에서 실제
    프로세스 수 재확인을 통합 감수 자료에 포함한다.
    """
    import os
    if (risk_engine_config.RISK_DEPLOYMENT_TOPOLOGY
            != "single_host_single_process"):
        return True  # 다른 topology의 canary 자격은 게이트가 별도 판정
    for var in ("WEB_CONCURRENCY", "UVICORN_WORKERS"):
        raw = os.environ.get(var)
        if raw:
            try:
                if int(raw) > 1:
                    return False
            except ValueError:
                return False  # 해석 불가=검증 불가(fail-closed)
    return True


def bootstrap_risk_exposure() -> str | None:
    """startup 1회 배선(감수 61차 §13-②) — EXPOSE **계열**(EXPOSE_CANARY
    포함) 모드 전용.

    reviewed artifact의 corpus hash로 실물 adapter를 등록하고 runtime
    상태를 검증 결과로 파생한다. OFF/SHADOW=None(아무것도 하지 않음).
    실패=미등록(전부 BYPASS — baseline 서비스는 정상) + 정적 reason 기록
    (조용한 무시 금지, 감수 61차 후속 §4).
    """
    global _LAST_BOOTSTRAP_REASON
    if not _exposure_mode_active():
        _LAST_BOOTSTRAP_REASON = None
        return None
    try:
        from .gemini_token_adapter import register_gemini_shadow_adapter
        from .llm_client import reading_model
        from .risk_exposure_service import stamp_runtime_adapter_state

        model_id = reading_model()
        if not _actual_worker_count_ok():
            _LAST_BOOTSTRAP_REASON = "RISK_BOOTSTRAP_TOPOLOGY_MISMATCH"
            _logger.error("risk_adapter_bootstrap: worker>1 감지 — "
                          "single_process 선언과 불일치(BYPASS 유지)")
            return None
        artifact = _find_artifact(model_id)
        if artifact is None:
            _LAST_BOOTSTRAP_REASON = "RISK_BOOTSTRAP_ARTIFACT_INVALID"
            _logger.error("risk_adapter_bootstrap: artifact 부재/손상 "
                          "model=%s — BYPASS 유지", model_id)
            return None
        corpus_hash = str(artifact.get("validationCorpusHash", ""))
        report = artifact.get("report") or {}
        cache_ok = bool(report.get("cacheSamplesValidated"))
        overhead = tuple(
            (str(s.get("digest", "")), int(s.get(
                "validated_framing_overhead", 0) or 0))
            for s in (artifact.get("reviewedRequestShapeDigests") or [])
            if isinstance(s, dict) and s.get("digest"))
        adapter = register_gemini_shadow_adapter(
            model_id, corpus_hash, cache_path_validated=cache_ok,
            framing_overhead_by_shape=overhead)
        # 운영 validation lease 검사(감수 62차 P1) — 만료·runway·identity·
        # 서명 불일치 = UNVALIDATED(tombstone 미적용, 재검증으로 복귀).
        from .risk_validation_lease import load_valid_lease
        from .token_counter_registry import (
            adapter_identity_hash,
            set_validation_state,
        )
        lease = load_valid_lease(model_id, adapter_identity_hash(adapter))
        if lease is None:
            set_validation_state(model_id, "UNVALIDATED")
            _LAST_BOOTSTRAP_REASON = "RISK_BOOTSTRAP_LEASE_INVALID"
            _logger.error("risk_adapter_bootstrap: validation lease "
                          "무효/만료 model=%s — UNVALIDATED(BYPASS)",
                          model_id)
            return "UNVALIDATED"
        state = stamp_runtime_adapter_state(model_id)
        if state != "VALIDATED":
            _LAST_BOOTSTRAP_REASON = "RISK_BOOTSTRAP_MANIFEST_MISMATCH"
        else:
            _LAST_BOOTSTRAP_REASON = None
        _logger.info("risk_adapter_bootstrap model=%s state=%s "
                     "lease_id=%s reported_model_version=%s",
                     model_id, state, lease.get("lease_id"),
                     lease.get("reported_model_version"))
        return state
    except Exception:  # noqa: BLE001 — startup 실패=미등록(BYPASS)
        _LAST_BOOTSTRAP_REASON = "RISK_BOOTSTRAP_ADAPTER_UNAVAILABLE"
        _logger.exception("risk_adapter_bootstrap 실패 — BYPASS 유지")
        return None


def exposure_runtime_inputs(call_type: str = "chat_single") -> dict:
    """chat_service EXPOSE 분기용 runtime 입력(감수 61차 §13-①).

    반환: counter(감수 adapter의 단건 계수 — 미해소 시 None: 게이트
    TOKENIZER_UNAVAILABLE), counter_model_id, resolved_model_id,
    context_limit(llm_config primary.context_limit — 부재·0=BYPASS 유지),
    response_reserve(call_type 출력 한도), reviewed_shape_digests.
    """
    from saju_engines.llm_guard import LLMCallGuard

    from .llm_client import load_config, reading_model
    from .risk_exposure_service import _load_manifest_snapshot
    from .token_counter_registry import resolve_expose_counter

    model_id = reading_model()
    try:
        counters = _load_manifest_snapshot()["validated_token_counters"]
    except Exception:  # noqa: BLE001 — manifest 불가=BYPASS(fail-closed)
        counters = []
    adapter = resolve_expose_counter(model_id, counters)
    try:
        context_limit = int(
            load_config()["primary"].get("context_limit") or 0)
    except (ValueError, TypeError, KeyError):
        context_limit = 0  # 미등록·비정상=0 → 게이트 BYPASS(§11)
    try:
        response_reserve = int(
            LLMCallGuard(call_type).request_params()["max_tokens"])
    except Exception:  # noqa: BLE001
        response_reserve = 0
    return {
        "counter": adapter.counter if adapter is not None else None,
        "counter_model_id": (adapter.model_id
                             if adapter is not None else None),
        "resolved_model_id": model_id,
        "context_limit": context_limit,
        "response_reserve": response_reserve,
        "reviewed_shape_digests": load_reviewed_shape_digests(model_id),
    }


def _period_matches(period_key: str, allowed_periods: frozenset[str]) -> bool:
    """기간 교집합 판정(감수 62차 P1) — 후보의 원자 period_key("2026" 또는
    "2026-07")가 허용 연도 집합과 하나 이상 겹치면 적격(연 단위 비교)."""
    year = str(period_key)[:4]
    return year in allowed_periods


def build_risk_payload(
    shadow_candidates: list,
    *,
    question_type: str | None = None,
    target_domains: tuple[str, ...] = (),
    allowed_periods: frozenset[str] | None = None,
    comparison_periods: tuple[str, ...] = (),
) -> dict | None:
    """risk_shadow 원자 후보 → 표현 payload(감수 61차 후속 + 62차 재배선).

    **필터 → 생성 → 선별 순서 불변식(감수 62차 P0②)**: subject 필터는
    호출부(요청 로컬 subject→risk 결과 맵)가 담당하고, 여기서는
    ①기간(정확한 집합 — min/max 범위 아님) ②대상 도메인 필터를 후보
    단계에서 적용한 뒤 episode 생성·R2 예산 선별(budget_for(question_
    type))·표현을 수행한다 — 타 도메인 고득점 후보가 슬롯을 점유한 뒤
    필터로 사라지는 결함 차단. 탈락 후보는 exposureFilterAudit에 사유와
    함께 전량 보존한다(OUTSIDE_TARGET_DOMAIN/OUTSIDE_TIME_SCOPE).

    base_impact는 risks/*.json의 baseImpact(사전 prior)에서 로드한다.
    적격 후보 없음=None(게이트 NO_EXPOSABLE_EPISODE → SUPPRESSED guard —
    약한 후보를 끌어올리지 않는다).
    """
    if not shadow_candidates:
        return None
    import json as _json

    from saju_engines.risk_presentation import build_presentation
    from saju_engines.risk_scoring import score_shadow
    from saju_engines.risk_selection import (
        budget_for,
        build_episodes,
        select_episodes,
    )

    risks_dir = (Path(__file__).resolve().parents[4] / "dictionaries"
                 / "risks")
    base_impact: dict[str, float] = {}
    for path in sorted(risks_dir.glob("*.json")):
        try:
            data = _json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for item in data.get("items", []):
            rid = item.get("riskId")
            if rid is not None:
                base_impact[str(rid)] = float(
                    item.get("baseImpact", 0.0) or 0.0)
    scored = score_shadow(list(shadow_candidates), base_impact)

    # ── 필터(선별보다 먼저) — 탈락 전량 감사 보존 ──────────────────
    filter_audit: list[dict] = []
    eligible = []
    for c in scored:
        reason: str | None = None
        if target_domains and c.domain.value not in target_domains:
            reason = "OUTSIDE_TARGET_DOMAIN"
        elif (allowed_periods is not None
              and not _period_matches(c.period_key, allowed_periods)):
            reason = "OUTSIDE_TIME_SCOPE"
        if reason is not None:
            filter_audit.append({
                "riskId": c.risk_id, "periodKey": c.period_key,
                "domain": c.domain.value, "reason": reason})
        else:
            eligible.append(c)
    if not eligible:
        return None

    selection_omitted: list[tuple[str, str]] = []
    consolidation: list[dict] | None = None
    if (question_type == "multi_episode_compare"
            and len(comparison_periods) >= 2):
        # 비교 계약(감수 62차 P0⑨ — dedup이 아니라 **consolidation**):
        # 기간별 독립 필터·선별(per-period cap) → canonical episodeKey별
        # cross-period 통합 → 전체 cap(통합 item 수·round-robin — 약한
        # 후보 승격·빈 기간 채우기 없음) → 기간별 occurrence 전부 보존.
        from saju_engines.risk_selection import RiskBudgetPolicy
        per_period = RiskBudgetPolicy(soft_target=2, hard_max=2)
        total_cap = budget_for(question_type).hard_max  # 통합 item 기준
        keys_by_period: list[list[str]] = []
        episodes = []
        for period in comparison_periods[:3]:
            in_period = [c for c in eligible
                         if str(c.period_key)[:4] == str(period)[:4]]
            if not in_period:
                keys_by_period.append([])  # 적격 없음=0개(채우지 않음)
                continue
            eps_p, omitted_p = select_episodes(
                build_episodes(in_period), in_period, per_period)
            selection_omitted.extend(omitted_p)
            episodes.extend(eps_p)
            keys_by_period.append([e.episode_key for e in eps_p])
        # round-robin으로 통합 item(고유 key) cap 적용
        kept: list[str] = []
        for round_i in range(max((len(k) for k in keys_by_period),
                                 default=0)):
            for period_keys in keys_by_period:
                if round_i < len(period_keys) and len(kept) < total_cap:
                    key = period_keys[round_i]
                    if key not in kept:
                        kept.append(key)
        dropped = [e for e in episodes if e.episode_key not in kept]
        selection_omitted.extend(
            (e.episode_key, "COMPARISON_TOTAL_CAP") for e in dropped)
        episodes = [e for e in episodes if e.episode_key in kept]
        consolidation = [
            {"canonicalEpisodeKey": key,
             "occurrences": [
                 {"period": str(p)[:4],
                  "present": any(
                      e.episode_key == key
                      and str(e.start_period)[:4] <= str(p)[:4]
                      <= str(e.end_period)[:4]
                      for e in episodes)}
                 for p in comparison_periods[:3]]}
            for key in kept]
    else:
        episodes = build_episodes(eligible)
        if question_type is not None:
            episodes, selection_omitted = select_episodes(
                episodes, eligible, budget_for(question_type))
    payload = build_presentation(episodes, eligible)
    if payload is not None:
        payload["exposureFilterAudit"] = filter_audit
        payload["selectionOmitted"] = [
            {"episodeKey": key, "reason": reason}
            for key, reason in selection_omitted]
        if consolidation is not None:
            payload["comparativeConsolidation"] = consolidation
    return payload


def run_exposed_reading(
    *,
    baseline_prompt: str,
    injected_prompt: str,
    system: str,
    observability: dict,
    payload: dict,
    call_type: str,
    request_context_id: str,
    renderer,
) -> dict:
    """INJECTED 실호출 실행(감수 60·61차 — run_injected_risk_flow 소비).

    chat_service EXPOSE 분기 전용: 실행 context 1회 조립 → 실 Gemini
    구조화 호출(계수와 동일 body) → envelope/claim 감사 → REVISE/
    REGENERATE 상태기 → renderer 후 최종 감사. 종료 후 provider 보고
    token으로 undercount(drift)·cache 관측을 기록한다(감수 60차 §7).
    반환: run_injected_risk_flow 결과(outcome=DELIVER_GENERATED/
    DELIVER_SAFE_FALLBACK/BLOCK).
    """
    import json as _json

    from saju_engines.risk_exposure import (
        build_guidance_reference_context,
    )

    from .gemini_token_adapter import generate_structured
    from .llm_client import reading_model
    from .risk_exposure_service import _load_manifest_snapshot
    from .risk_llm_pipeline import (
        build_risk_execution_context,
        run_injected_risk_flow,
    )
    from .token_counter_registry import (
        ProviderRequest,
        record_cache_observation,
        record_count_observation,
        resolve_expose_counter,
    )

    model_id = reading_model()
    counters = _load_manifest_snapshot()["validated_token_counters"]
    adapter = resolve_expose_counter(model_id, counters)
    inputs = exposure_runtime_inputs(call_type)
    # lease의 기대 모델 버전(감수 62차 P0⑧) — 응답 최상위 modelVersion과
    # 대조해 불일치·누락이면 그 응답을 폐기하고 UNVALIDATED로 전환한다.
    from .risk_validation_lease import invalidate_lease, load_valid_lease
    from .token_counter_registry import (
        adapter_identity_hash,
        set_validation_state,
    )
    expected_model_version = ""
    if adapter is not None:
        lease = load_valid_lease(model_id, adapter_identity_hash(adapter),
                                 require_runway=False)
        expected_model_version = (str(lease.get("reported_model_version"))
                                  if lease else "")
    guidance_context = build_guidance_reference_context(
        request_context_id, payload)
    baseline_request = ProviderRequest(
        system_messages=(system,), user_messages=(baseline_prompt,))
    transport = (observability.get("risk_output_schemas") or {}).get(
        "gemini_transport")
    initial_request = ProviderRequest(
        system_messages=(system,), user_messages=(injected_prompt,),
        output_schema=(_json.dumps(transport, ensure_ascii=False,
                                   sort_keys=True) if transport else None))
    exec_ctx = build_risk_execution_context(
        request_context_id, manifest_counters=list(counters),
        guidance_context=guidance_context,
        baseline_request=baseline_request, resolved_model_id=model_id)
    provider_reports: list[dict] = []

    def _llm_call(request: ProviderRequest) -> dict:
        out = generate_structured(
            request, model_id,
            max_output_tokens=max(256, inputs["response_reserve"]))
        provider_reports.append(out)
        # modelVersion 대조(감수 62차 P0⑧) — 불일치·누락 응답은 감사·
        # 재작성 단계로 넘기지 않고 즉시 폐기(DISCARDED), validation
        # state=UNVALIDATED + lease 무효화 → 이후 요청 BYPASS.
        observed_version = str(out.get("model_version", ""))
        if expected_model_version and (
                not observed_version
                or observed_version != expected_model_version):
            invalidate_lease(
                model_id,
                f"MODEL_VERSION_MISMATCH:{observed_version or '<missing>'}"
                f"!={expected_model_version}")
            set_validation_state(model_id, "UNVALIDATED")
            raise RuntimeError(
                "RISK_MODEL_VERSION_MISMATCH — 응답 폐기(UNVALIDATED)")
        envelope = None
        if request.output_schema:
            try:
                envelope = _json.loads(out["text"])
            except ValueError:
                envelope = {}  # schema 요구에도 비JSON=envelope 실패
        answer = (str(envelope.get("main_answer", ""))
                  if isinstance(envelope, dict) and envelope
                  else out["text"])
        # provider 보고 token을 응답과 함께 반환 — flow가 **전달 판정
        # 전에** drift·cache·출력 잘림(finish_reason)을 검사한다.
        return {"answer": answer, "envelope": envelope,
                "provider_reported_input": out["prompt_tokens"],
                "cached_input": out["cached_tokens"],
                "finish_reason": out.get("finish_reason", "")}

    def _drift_observer(kind: str, counted: int, reported: int,
                        cached: int, request_digest: str) -> None:
        record_count_observation(model_id, counted=counted,
                                 reported=reported,
                                 request_id_hash=request_digest)
        record_cache_observation(model_id, cached)

    result = run_injected_risk_flow(
        initial_request=initial_request,
        baseline_request=baseline_request,
        execution_context=exec_ctx,
        llm_episodes=payload.get("llmRiskEpisodes") or [],
        adapter=adapter,
        final_token_limit=inputs["context_limit"]
        - inputs["response_reserve"],
        llm_call=_llm_call, renderer=renderer,
        resolve_model=reading_model,
        reviewed_shape_digests=inputs["reviewed_shape_digests"],
        drift_observer=_drift_observer)
    result["provider_reports"] = len(provider_reports)  # 관측 보조
    return result
