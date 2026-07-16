"""R5-b 배선 통합 fixture (감수 46차 — RISK_DICTIONARY_REVIEW.md §28).

성공 조건: OFF/SHADOW의 실제 최종 prompt byte 불변, EXPOSE 계열에서만
suppressed guard/instruction 차등 부착, 게이트 fail-closed(현 단계=
reviewed:false·adapter 부재 → 위험 정보 미주입), 재작성 흐름 결정적.
"""

from __future__ import annotations

from datetime import date

from saju_api.services import chat_service
from saju_engines import risk_engine_config
from saju_engines.risk_exposure import (
    RISK_EXPOSURE_INSTRUCTION_BLOCK,
    RISK_EXPOSURE_SUPPRESSED_GUARD,
)
from saju_shared_types.birth_input import BirthInput

_TODAY = date(2026, 6, 11)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date="2026-06-11",
)
_QUESTION = "올해 하반기 전체 운세 알려줘"


def _prompt(mode: str, monkeypatch) -> tuple[str, str | None]:
    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE", mode)
    res = chat_service.chat(_BIRTH, _QUESTION, _TODAY, dry_run=True)
    assert res.status == "dry_run", res.answer
    return res.prompt_preview or "", res.system_prompt


def test_off_and_shadow_final_prompt_byte_identical(monkeypatch) -> None:
    """OFF vs SHADOW: 실제 chat 최종 prompt·system byte-identical(감수 46차
    §15 Mode) — 위험 배선 분기가 EXPOSE 계열에서만 실행됨의 실증."""
    off_p, off_s = _prompt("off", monkeypatch)
    sh_p, sh_s = _prompt("shadow", monkeypatch)
    assert off_p == sh_p
    assert off_s == sh_s
    assert RISK_EXPOSURE_SUPPRESSED_GUARD not in off_p
    assert RISK_EXPOSURE_INSTRUCTION_BLOCK not in off_p


def test_expose_canary_unauthorized_is_bypass_byte_identical(
        monkeypatch) -> None:
    """감수 47차 §2-①: EXPOSE_CANARY + canary 비허용 → disposition=BYPASS —
    guard조차 없이 **최종 prompt baseline과 byte-identical**(위험 파이프라인
    적용 대상이 아닌 요청은 기존 요청 그대로)."""
    off_p, off_s = _prompt("off", monkeypatch)
    can_p, can_s = _prompt("expose_canary", monkeypatch)
    assert can_p == off_p
    assert can_s == off_s
    assert RISK_EXPOSURE_SUPPRESSED_GUARD not in can_p
    assert RISK_EXPOSURE_INSTRUCTION_BLOCK not in can_p


def test_canary_allowed_but_pipeline_unreviewed_is_bypass(
        monkeypatch) -> None:
    """감수 47차 §2-②: canary 허용 + expose_pipeline reviewed=false →
    BYPASS(guard 없음·prompt 불변)."""
    from saju_api.services.risk_exposure_service import apply_risk_exposure

    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE",
                        "expose_canary")
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSE_CANARY_SUBJECT_IDS",
                        frozenset({"internal-tester-1"}))
    p, s, obs = apply_risk_exposure(
        "본문", None, subject_id="internal-tester-1",
        question_type="period_overview", temporal_scope="future")
    assert p == "본문" and s is None
    assert obs["disposition"] == "BYPASS"
    assert obs["reason"] == "EXPOSE_PIPELINE_NOT_REVIEWED"


def test_qualified_but_runtime_short_is_suppressed_guard(
        monkeypatch) -> None:
    """감수 47차 §2-③: 감수·허용·tokenizer 정상 + 노출 episode 없음/예산
    부족 → SUPPRESSED — suppressed guard만 추가."""
    from saju_api.services.risk_exposure_service import apply_risk_exposure

    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE",
                        "expose_canary")
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSE_CANARY_SUBJECT_IDS",
                        frozenset({"internal-tester-1"}))
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSURE_RUNTIME_ENABLED", True)
    from saju_api.services import risk_exposure_service as _svc
    monkeypatch.setattr(_svc, "_manifest_expose_state",
                        lambda: (True, True))  # 감수 완료 상태 모의
    p, _s, obs = apply_risk_exposure(
        "본문", None, subject_id="internal-tester-1",
        question_type="period_overview", temporal_scope="future",
        counter=lambda t: max(1, len(t) // 4),
        counter_model_id="m1", resolved_model_id="m1",
        model_context_limit=16_000, base_prompt_tokens=1_000,
        user_input_tokens=100, existing_context_tokens=1_000,
        response_reserve=2_000)
    assert obs["disposition"] == "SUPPRESSED"
    assert obs["reason"] == "NO_EXPOSABLE_EPISODE"
    assert p == "본문\n" + RISK_EXPOSURE_SUPPRESSED_GUARD


def test_all_conditions_met_is_injected(monkeypatch) -> None:
    """감수 47차 §2-④: 모든 조건 충족 → INJECTED — instruction + risk
    block 추가(위험 payload 실주입 경로의 유일한 형태)."""
    from saju_api.services.risk_exposure_service import apply_risk_exposure
    from saju_engines.risk_presentation import build_presentation
    from saju_engines.risk_scoring import score_shadow
    from saju_engines.risk_selection import build_episodes
    from saju_shared_types.risk_engine import (
        EvidenceRole,
        ExposureStatus,
        RiskCandidate,
        RiskDomain,
        RiskEvidence,
        RiskKind,
    )

    src = "relation:CHUNG:month_pillar:branch:ZHENGCAI"
    cand = RiskCandidate(
        risk_id="LEG_A", domain=RiskDomain.CONTRACT_LEGAL,
        kind=RiskKind.INCIDENT_RISK, risk_family="fam", period_key="2026",
        evidence=[RiskEvidence(
            evidence_id=f"2026|{src}", code="T", period_key="2026",
            layer="sewoon", source=src, strength=0.5,
            role=EvidenceRole.TRIGGER, source_group="event_shape",
            target_domain=RiskDomain.CONTRACT_LEGAL)],
        exposure_status=ExposureStatus.CONFIRMED, specificity_rank=2,
        normalized_effect_role="legal_dispute", trigger_cause_atoms=[src],
        legal_episode_id="e1")
    scored = score_shadow([cand], {"LEG_A": 0.6})
    payload = build_presentation(build_episodes(scored), scored)
    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE",
                        "expose_canary")
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSE_CANARY_SUBJECT_IDS",
                        frozenset({"internal-tester-1"}))
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSURE_RUNTIME_ENABLED", True)
    from saju_api.services import risk_exposure_service as _svc
    monkeypatch.setattr(_svc, "_manifest_expose_state",
                        lambda: (True, True))  # 감수 완료 상태 모의
    p, _s, obs = apply_risk_exposure(
        "본문", None, payload=payload, subject_id="internal-tester-1",
        question_type="period_overview", temporal_scope="future",
        counter=lambda t: max(1, len(t) // 4),
        counter_model_id="m1", resolved_model_id="m1",
        model_context_limit=16_000, base_prompt_tokens=1_000,
        user_input_tokens=100, existing_context_tokens=1_000,
        response_reserve=2_000)
    assert obs["disposition"] == "INJECTED"
    assert RISK_EXPOSURE_INSTRUCTION_BLOCK in p
    assert '"riskEpisodes"' in p
    assert RISK_EXPOSURE_SUPPRESSED_GUARD not in p


def test_kill_switch_blocks_regardless_of_mode(monkeypatch) -> None:
    """kill switch=게이트 최앞 — EXPOSE 모드여도 BYPASS primary."""
    from saju_api.services.risk_exposure_service import apply_risk_exposure

    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE", "expose")
    monkeypatch.setattr(risk_engine_config, "RISK_EXPOSURE_KILL_SWITCH",
                        True)
    p, _s, obs = apply_risk_exposure("본문", None)
    assert obs["reason"] == "KILL_SWITCH"
    assert obs["disposition"] == "BYPASS"
    assert p == "본문"  # 한 바이트도 불변


def test_remediation_flow_is_deterministic() -> None:
    """재작성 상태기(감수 46차 §11): 위반→REVISE(1회)→재실패→risk 없는 전체
    재생성→그래도 위반→BLOCK. 위반 초안 직접 전달 경로 없음."""
    from saju_engines.risk_claim_audit import (
        MAX_RISK_REVISION_ATTEMPTS,
        plan_remediation,
    )

    assert MAX_RISK_REVISION_ATTEMPTS == 1
    assert plan_remediation(0, "ALLOW") == "DELIVER"
    assert plan_remediation(0, "REVISE_REQUIRED") == "REVISE"
    assert plan_remediation(1, "REVISE_REQUIRED") == (
        "REGENERATE_WITHOUT_RISK")
    assert plan_remediation(2, "REVISE_REQUIRED") == "BLOCK"


def test_episode_level_qualifier_audit() -> None:
    """episode별 qualifier 검사(감수 46차 §12): 두 partial episode 중 한
    건에만 한정어가 있으면 다른 건이 missing_qualifier로 잡힌다 + 전체 답변
    감사 병행(mainAnswer의 위반도 검출)."""
    from saju_engines.risk_claim_audit import audit_risk_sections

    sections = [
        {"episode_key": "reality:a", "exposed_level": "warning",
         "identity_phrase_mode": "possibly_related",
         "required_qualifiers": ["possibly_related"],
         "prohibited_phrases": [],
         "text": "두 흐름은 서로 관련됐을 가능성이 있어 함께 살펴보면"
                 " 좋습니다."},
        {"episode_key": "reality:b", "exposed_level": "warning",
         "identity_phrase_mode": "possibly_related",
         "required_qualifiers": ["possibly_related"],
         "prohibited_phrases": [],
         "text": "계약 조건 변화 흐름에 유의하세요."},  # 한정어 없음
    ]
    whole = ("전반적으로 안정적인 해입니다. "
             f"{sections[0]['text']} {sections[1]['text']}"
             " 다만 하반기에는 문제가 해결됩니다.")
    out = audit_risk_sections(sections, whole)
    assert out["action"] == "REVISE_REQUIRED"
    keys = {(v["episode_key"], v["code"]) for v in out["violations"]}
    assert ("reality:b", "missing_qualifier") in keys
    assert ("reality:a", "missing_qualifier") not in keys
    assert (None, "recovery_guarantee") in keys  # 전체 답변 감사 병행


def test_block_integrity_checksum() -> None:
    """RiskPromptBlock checksum(감수 46차 §7): 원문 포함+해시 일치=통과,
    복사 후 변형·누락=실패(비주입)."""
    import hashlib

    from saju_engines.risk_exposure import (
        RiskPromptBlock,
        verify_risk_block_integrity,
        wrap_risk_block,
    )

    text = '{"riskEpisodes": []}'
    block = RiskPromptBlock(
        serialized_text=text, compression_mode="P0_COMPACT",
        exact_token_count=10,
        content_hash=hashlib.sha256(text.encode()).hexdigest()[:16])
    wrapped = wrap_risk_block(block)
    assert verify_risk_block_integrity(f"머리\n{wrapped}\n꼬리", block)
    # 본문 변형·marker 부재 → 실패.
    assert not verify_risk_block_integrity("머리\n변형된 블록\n꼬리", block)
    assert not verify_risk_block_integrity(f"머리\n{text}\n꼬리", block)
    # 중복 삽입(감수 47차 §3) — hash가 맞아도 실패.
    assert not verify_risk_block_integrity(
        f"{wrapped}\n중간\n{wrapped}", block)
    tampered = RiskPromptBlock(
        serialized_text=text, compression_mode="P0_COMPACT",
        exact_token_count=10, content_hash="0" * 16)
    assert not verify_risk_block_integrity(
        f"머리\n{wrap_risk_block(tampered)}\n꼬리", tampered)


def test_future_scope_preserves_audit_records() -> None:
    """미래 필터(감수 46차 §4): 감사 records 전량 보존 +
    OUTSIDE_FUTURE_SCOPE 표시, LLM episodes만 제외."""
    from saju_engines.risk_exposure import filter_payload_to_future_scope

    payload = {
        "globalProhibitedClaimCodes": [], "globalAllowedClaimCodes": [],
        "presentationRecords": [
            {"presentationLevel": "warning", "diagnostics":
             {"startPeriod": "2024", "endPeriod": "2024"}},
            {"presentationLevel": "watch", "diagnostics":
             {"startPeriod": "2026-03", "endPeriod": "2026-05"}},
        ],
        "llmRiskEpisodes": [{"presentationLevel": "warning"},
                            {"presentationLevel": "watch"}],
    }
    out = filter_payload_to_future_scope(payload, ("2026-01", "2027-12"))
    assert len(out["presentationRecords"]) == 2  # 감사 흔적 보존
    statuses = [r["exposureScopeStatus"] for r in out["presentationRecords"]]
    assert statuses == ["OUTSIDE_FUTURE_SCOPE", "IN_SCOPE"]
    assert len(out["llmRiskEpisodes"]) == 1


# ── 감수 48차 fixture ─────────────────────────────────────────────


def test_runtime_and_manifest_must_both_be_true(monkeypatch) -> None:
    """감수 48차 §4: manifest(감수 SSOT)와 runtime enabled 중 하나만
    true여서는 절대 주입되지 않는다 — 환경변수가 reviewed를 대체 불가."""
    from saju_api.services import risk_exposure_service as svc

    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE",
                        "expose_canary")
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSE_CANARY_SUBJECT_IDS",
                        frozenset({"internal-tester-1"}))
    common: dict = dict(
        subject_id="internal-tester-1",
        question_type="period_overview", temporal_scope="future",
        counter=lambda t: max(1, len(t) // 4),
        counter_model_id="m1", resolved_model_id="m1",
        model_context_limit=16_000, base_prompt_tokens=1_000,
        user_input_tokens=100, existing_context_tokens=1_000,
        response_reserve=2_000)
    # ① runtime=true + manifest reviewed=false(현 실제 상태) → BYPASS.
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSURE_RUNTIME_ENABLED", True)
    p, _s, obs = svc.apply_risk_exposure("본문", None, **common)
    assert obs["disposition"] == "BYPASS" and p == "본문"
    assert obs["reason"] == "EXPOSE_PIPELINE_NOT_REVIEWED"
    # ② manifest reviewed=true(모의) + runtime=false → BYPASS.
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSURE_RUNTIME_ENABLED", False)
    monkeypatch.setattr(svc, "_manifest_expose_state",
                        lambda: (True, True))
    p2, _s2, obs2 = svc.apply_risk_exposure("본문", None, **common)
    assert obs2["disposition"] == "BYPASS" and p2 == "본문"
    assert obs2["reason"] == "EXPOSE_PIPELINE_NOT_REVIEWED"


def test_manifest_hash_mismatch_is_bypass(monkeypatch) -> None:
    """expose 정책 코드가 manifest와 어긋나면(hash 불일치) BYPASS —
    감수 시점과 다른 정책으로 주입 불가."""
    from saju_api.services import risk_exposure_service as svc

    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE",
                        "expose_canary")
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSE_CANARY_SUBJECT_IDS",
                        frozenset({"internal-tester-1"}))
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSURE_RUNTIME_ENABLED", True)
    monkeypatch.setattr(svc, "_manifest_expose_state",
                        lambda: (True, False))  # reviewed=true·hash 불일치
    p, _s, obs = svc.apply_risk_exposure(
        "본문", None, subject_id="internal-tester-1",
        question_type="period_overview", temporal_scope="future",
        counter=lambda t: 1, counter_model_id="m1", resolved_model_id="m1")
    assert obs["disposition"] == "BYPASS" and p == "본문"
    assert obs["reason"] == "POLICY_HASH_MISMATCH"


def test_integrity_failure_demotes_to_suppressed() -> None:
    """감수 48차 §7: integrity 실패=instruction만 남는 상태 금지 —
    SUPPRESSED 강등(RISK_BLOCK_INTEGRITY_ERROR)·전체 재조립 계약."""
    from saju_engines.risk_exposure import resolve_block_integrity_failure

    injected = {"inject": True, "disposition": "INJECTED",
                "serialized": "{}",
                "observability": {"attempted": True, "injected": True,
                                  "disposition": "INJECTED",
                                  "effective_budget": 1024}}
    out = resolve_block_integrity_failure(injected)
    assert out["disposition"] == "SUPPRESSED"
    assert out["primary_decision_reason"] == "RISK_BLOCK_INTEGRITY_ERROR"
    assert out["serialized"] is None
    assert out["observability"]["reason"] == "RISK_BLOCK_INTEGRITY_ERROR"


def test_token_counter_registry_contract() -> None:
    """adapter registry(감수 48차 §10-③): 기본 비어 있음(미등록=None →
    BYPASS), heuristic mode 등록 금지, resolved ID 기반 해소."""
    import pytest as _pytest

    from saju_api.services.token_counter_registry import (
        TokenCounterAdapter,
        register_adapter,
        resolve_counter,
    )

    assert resolve_counter("gemini-2.5-flash") is None  # 기본 미등록
    with _pytest.raises(ValueError):
        register_adapter(TokenCounterAdapter(
            model_id="x", mode="HEURISTIC_FALLBACK", counter=len))
    register_adapter(TokenCounterAdapter(
        model_id="test-model-x", mode="MODEL_TOKENIZER", counter=len))
    adapter = resolve_counter("test-model-x")
    assert adapter is not None and adapter.counter("abc") == 3


def test_risk_guidance_envelope_invariants() -> None:
    """envelope 불변식(감수 48차 §10-⑤): 미등록 key·중복·level 초과·
    warning-first 위반 검출."""
    from saju_engines.risk_claim_audit import (
        validate_risk_guidance_envelope,
    )

    llm = [{"episodeKey": "e1", "presentationLevel": "warning"},
           {"episodeKey": "e2", "presentationLevel": "watch"}]
    ok = validate_risk_guidance_envelope(
        [{"episode_key": "e1", "exposed_level": "warning"},
         {"episode_key": "e2", "exposed_level": "watch"}], llm)
    assert ok == []
    errors = validate_risk_guidance_envelope(
        [{"episode_key": "e2", "exposed_level": "watch"},
         {"episode_key": "e1", "exposed_level": "critical"},  # 초과+순서
         {"episode_key": "e1", "exposed_level": "warning"},   # 중복
         {"episode_key": "ghost", "exposed_level": "watch"}], llm)
    codes = {e.split(":")[0] for e in errors}
    assert {"LEVEL_EXCEEDS_EXPOSED", "ORDER_NOT_WARNING_FIRST",
            "DUPLICATE_EPISODE_KEY", "UNREGISTERED_EPISODE_KEY"} <= codes


def test_claim_audit_negation_and_circumvention() -> None:
    """FP/FN 코퍼스(감수 48차 §11): 안전한 부정문은 통과, 우회 단정은 검출."""
    from saju_engines.risk_claim_audit import audit_generated_risk_claims

    safe = ("이 신호가 사고가 납니다라는 뜻은 아닙니다. 계약이 반드시"
            " 종료된다는 의미는 아니며, 손실이 확정된 것은 아닙니다.")
    # 부정문 — 위반 아님(FP 차단).
    out = audit_generated_risk_claims(safe)
    assert out["action"] == "ALLOW", out["violations"]
    evasive = ("법적 결과를 피하기 어려운 흐름입니다. 금전 손실로"
               " 이어지는 수순입니다.")
    out2 = audit_generated_risk_claims(evasive)
    assert out2["action"] == "REVISE_REQUIRED"
    assert any(v["code"] == "circumvented_certainty"
               for v in out2["violations"])
