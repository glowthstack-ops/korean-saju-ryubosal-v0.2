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
                        "RISK_DEPLOYMENT_TOPOLOGY",
                        "single_host_single_process")
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
                        "RISK_DEPLOYMENT_TOPOLOGY",
                        "single_host_single_process")
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSE_CANARY_SUBJECT_IDS",
                        frozenset({"internal-tester-1"}))
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSURE_RUNTIME_ENABLED", True)
    monkeypatch.setattr(risk_engine_config, "RISK_AUDIT_HMAC_KEY",
                        b"a" * 32)  # 운영 유효 키 모의(감수 53차 §8)
    from saju_api.services import risk_exposure_service as _svc
    monkeypatch.setattr(_svc, "_load_manifest_snapshot",
                        lambda: {"reviewed": True, "hash_ok": True,
                                 "schema_version": 10,
                                 "snapshot_hash": "mock"})
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
                        "RISK_DEPLOYMENT_TOPOLOGY",
                        "single_host_single_process")
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSE_CANARY_SUBJECT_IDS",
                        frozenset({"internal-tester-1"}))
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSURE_RUNTIME_ENABLED", True)
    monkeypatch.setattr(risk_engine_config, "RISK_AUDIT_HMAC_KEY",
                        b"a" * 32)  # 운영 유효 키 모의(감수 53차 §8)
    from saju_api.services import risk_exposure_service as _svc
    monkeypatch.setattr(_svc, "_load_manifest_snapshot",
                        lambda: {"reviewed": True, "hash_ok": True,
                                 "schema_version": 10,
                                 "snapshot_hash": "mock"})
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
                        "RISK_DEPLOYMENT_TOPOLOGY",
                        "single_host_single_process")
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
    # ① runtime=true + manifest reviewed=false(모의 — 통합 감수 §8로
    # 실물은 true 전환: 역방향 차단이 유지됨을 검증) → BYPASS.
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSURE_RUNTIME_ENABLED", True)
    monkeypatch.setattr(svc, "_load_manifest_snapshot",
                        lambda: {"reviewed": False, "hash_ok": True,
                                 "validated_token_counters": [],
                                 "schema_version": 10,
                                 "snapshot_hash": "mock"})
    p, _s, obs = svc.apply_risk_exposure("본문", None, **common)
    assert obs["disposition"] == "BYPASS" and p == "본문"
    assert obs["reason"] == "EXPOSE_PIPELINE_NOT_REVIEWED"
    # ①-b manifest reviewed=true + runtime=true여도 dev 기본 HMAC 키가
    # 다음 차단기 — 운영 키 교체(사람 확인 4항) 전 주입 불가.
    monkeypatch.setattr(svc, "_load_manifest_snapshot",
                        lambda: {"reviewed": True, "hash_ok": True,
                                 "validated_token_counters": [],
                                 "schema_version": 10,
                                 "snapshot_hash": "mock"})
    p1b, _s1b, obs1b = svc.apply_risk_exposure("본문", None, **common)
    assert obs1b["disposition"] == "BYPASS" and p1b == "본문"
    assert obs1b["reason"] == "AUDIT_HMAC_KEY_INVALID"
    # ② manifest reviewed=true(모의) + runtime=false → BYPASS.
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSURE_RUNTIME_ENABLED", False)
    monkeypatch.setattr(svc, "_load_manifest_snapshot",
                        lambda: {"reviewed": True, "hash_ok": True,
                                 "validated_token_counters": [],
                                 "schema_version": 10,
                                 "snapshot_hash": "mock"})
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
                        "RISK_DEPLOYMENT_TOPOLOGY",
                        "single_host_single_process")
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSE_CANARY_SUBJECT_IDS",
                        frozenset({"internal-tester-1"}))
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSURE_RUNTIME_ENABLED", True)
    monkeypatch.setattr(svc, "_load_manifest_snapshot",
                        lambda: {"reviewed": True, "hash_ok": False,
                                 "schema_version": 10,
                                 "snapshot_hash": "mock"})
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
        [{"episode_key": "e1", "exposed_level": "warning", "text": "점검"},
         {"episode_key": "e2", "exposed_level": "watch", "text": "관찰"}],
        llm)
    assert ok == []
    errors = validate_risk_guidance_envelope(
        [{"episode_key": "e2", "exposed_level": "watch", "text": "a"},
         {"episode_key": "e1", "exposed_level": "critical",
          "text": "b"},  # 초과+순서
         {"episode_key": "e1", "exposed_level": "warning",
          "text": "c"},   # 중복
         {"episode_key": "ghost", "exposed_level": "watch", "text": "d"}],
        llm)
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


# ── 감수 49차 fixture ─────────────────────────────────────────────


def test_clause_aware_negation_corpus() -> None:
    """절 단위 부정문(감수 49차 §6 필수 코퍼스 4종): 안전 부정문 허용,
    역접 뒤 재단정·이중 부정·부정 후 우회 단정은 위반."""
    from saju_engines.risk_claim_audit import audit_generated_risk_claims

    # ① 안전 부정문 → 허용.
    ok = audit_generated_risk_claims("사고가 난다는 뜻은 아닙니다.")
    assert ok["action"] == "ALLOW", ok["violations"]
    # ② 부정 후 역접 재단정 → 위반(앞 절 부정이 뒤 절을 덮지 못함).
    v2 = audit_generated_risk_claims(
        "사고가 난다는 뜻은 아닙니다. 하지만 발생을 피하기 어려운 흐름입니다.")
    assert v2["action"] == "REVISE_REQUIRED"
    # ③ 이중 부정 → 위반(예외 제외).
    v3 = audit_generated_risk_claims("사고가 나지 않는다고 볼 수는 없습니다.")
    assert v3["action"] == "REVISE_REQUIRED", v3["violations"]
    # ④ 같은 문장 부정 + 역접 후 우회 단정 → 위반.
    v4 = audit_generated_risk_claims(
        "계약이 반드시 깨진다는 뜻은 아닙니다만 사실상 이어지는 수순입니다.")
    assert v4["action"] == "REVISE_REQUIRED"


def test_envelope_missing_required_warning_episode() -> None:
    """warning 이상 episode 출력 필수(감수 49차 §5) — 누락=MISSING_REQUIRED,
    watch/advisory는 생략 허용. schema 위반(미지 필드·빈 text)도 검출."""
    from saju_engines.risk_claim_audit import (
        validate_risk_guidance_envelope,
    )

    llm = [{"episodeKey": "w1", "presentationLevel": "warning"},
           {"episodeKey": "w2", "presentationLevel": "warning"},
           {"episodeKey": "c1", "presentationLevel": "watch"}]
    # warning 1건 누락 + watch 생략 → MISSING은 w2만.
    errors = validate_risk_guidance_envelope(
        [{"episode_key": "w1", "exposed_level": "warning",
          "text": "일정·문서를 점검해 두면 좋습니다."}], llm)
    assert errors == ["MISSING_REQUIRED_RISK_EPISODE:w2"]
    # 미지 필드·빈 text·level 불일치.
    errors2 = validate_risk_guidance_envelope(
        [{"episode_key": "w1", "exposed_level": "watch", "text": "x",
          "surprise_field": 1},
         {"episode_key": "w2", "exposed_level": "warning", "text": " "}],
        llm)
    codes = {e.split(":")[0] for e in errors2}
    assert {"UNKNOWN_ENVELOPE_FIELD", "LEVEL_MISMATCH",
            "EMPTY_SECTION_TEXT"} <= codes


def test_rebuild_once_then_terminal_safe_response() -> None:
    """재조립 1회 제한(감수 49차 §3): 2회째 integrity 실패·guard 예산
    초과=RISK_SAFE_RESPONSE_REQUIRED — guard 없는 조용한 원 prompt 호출
    경로 없음."""
    from saju_engines.risk_exposure import (
        MAX_SUPPRESSED_REBUILD_ATTEMPTS,
        RISK_SAFE_RESPONSE_REQUIRED,
        resolve_block_integrity_failure,
        resolve_guard_overflow,
    )

    injected = {"inject": True, "disposition": "INJECTED",
                "serialized": "{}", "observability": {}}
    first = resolve_block_integrity_failure(injected, rebuild_attempt=0)
    assert first["disposition"] == "SUPPRESSED"
    assert "terminal_action" not in first
    second = resolve_block_integrity_failure(
        injected, rebuild_attempt=MAX_SUPPRESSED_REBUILD_ATTEMPTS)
    assert second["terminal_action"] == RISK_SAFE_RESPONSE_REQUIRED
    overflow = resolve_guard_overflow(injected)
    assert overflow["primary_decision_reason"] == (
        "SUPPRESSED_GUARD_TOKEN_OVERFLOW")
    assert overflow["terminal_action"] == RISK_SAFE_RESPONSE_REQUIRED


def test_legacy_reason_fields_are_copies() -> None:
    """하위 호환 별칭(감수 49차 §1): 구 필드=정본 복사만 — 불일치 0."""
    from saju_engines.risk_exposure import (
        ExposureGateContext,
        evaluate_risk_exposure_gate,
    )
    from saju_shared_types.risk_engine import RiskEngineMode

    empty: dict = {"globalProhibitedClaimCodes": [],
                   "globalAllowedClaimCodes": [],
                   "presentationRecords": [], "llmRiskEpisodes": []}
    for mode in (RiskEngineMode.OFF, RiskEngineMode.EXPOSE):
        ctx = ExposureGateContext(
            mode=mode, question_type="period_overview",
            temporal_scope="future", risk_intent_allowed=True,
            token_count_mode="MODEL_TOKENIZER", model_context_limit=16_000,
            base_prompt_tokens=1_000, user_input_tokens=100,
            existing_context_tokens=1_000, response_reserve=2_000,
            scopes_all_reviewed=True, policy_hashes_match=True,
            expose_pipeline_reviewed=True, counter_model_id="m",
            resolved_model_id="m")
        out = evaluate_risk_exposure_gate(ctx, empty, counter=len)
        assert out["suppression_reason"] == out["primary_decision_reason"]
        assert out["all_suppression_reasons"] == out["all_decision_reasons"]


def test_manifest_snapshot_consistency_and_observability(
        monkeypatch) -> None:
    """manifest snapshot(감수 49차 §2): 단일 로드·schema 검증·snapshot
    hash 관측 — 미지원 schema=fail-closed."""
    from saju_api.services import risk_exposure_service as svc

    snap = svc._load_manifest_snapshot()
    assert snap["schema_version"] == 10
    # 통합 pre-canary 감수 §8(2026-07-17): reviewed=true 전환 — 실주입은
    # RUNTIME_ENABLED(False)·MODE(off)·운영 HMAC 키가 계속 막는다.
    assert snap["hash_ok"] is True and snap["reviewed"] is True
    assert len(snap["snapshot_hash"]) == 16
    # 관측에 snapshot hash 병기.
    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE",
                        "expose_canary")
    _p, _s, obs = svc.apply_risk_exposure("본문", None)
    assert obs["manifest_snapshot_hash"] == snap["snapshot_hash"]
    # 미지원 schema → fail-closed.
    monkeypatch.setattr(svc, "_SUPPORTED_MANIFEST_SCHEMA_VERSIONS", (99,))
    bad = svc._load_manifest_snapshot()
    assert bad["reviewed"] is False and bad["hash_ok"] is False


def test_count_request_covers_whole_provider_request() -> None:
    """TokenCounter 인터페이스(감수 49차 §4): count_request가 request
    전체(system·user·schema·config)를 계수."""
    from saju_api.services.token_counter_registry import (
        ProviderRequest,
        TokenCounterAdapter,
    )

    adapter = TokenCounterAdapter(
        model_id="m", mode="MODEL_TOKENIZER", counter=len,
        provider_id="test", counter_version="v1")
    req = ProviderRequest(
        system_messages=("sys",), user_messages=("user",),
        output_schema="schema", tool_schema=None,
        generation_config="cfg")
    # 구성요소 전부 합산(3+4+6+3) + wrapper 여유(4×4).
    assert adapter.count_request(req) == 3 + 4 + 6 + 3 + 16


# ── 감수 50차 fixture ─────────────────────────────────────────────


def test_intent_mapping_ssot_and_fail_closed() -> None:
    """질문 파서 SSOT 매핑(감수 50차 §9-①): 정본 IntentJson에서만 매핑,
    미등록 유형·불명확 시간·미래 범위 산출 실패·비단독 대상=fail-closed."""
    from saju_engines.risk_question_mapping import (
        map_intent_to_exposure_question,
    )
    from saju_shared_types.intent import (
        Domain,
        IntentJson,
        QueryType,
        SubjectMode,
        TimeRange,
        TimeScope,
    )

    def _intent(**kw):
        base = dict(intent_id="i1", query_type=QueryType.FORTUNE_OVERVIEW,
                    time_scope=TimeScope.MID_TERM,
                    time_range=TimeRange(type="relative",
                                         granularity="month",
                                         start="2026-07", end="2027-06"),
                    domains=[Domain.WEALTH])
        base.update(kw)
        return IntentJson(**base)

    ok = map_intent_to_exposure_question(_intent())
    assert ok == {"question_type": "period_overview",
                  "temporal_scope": "future",
                  "future_period_range": ("2026-07", "2027-06"),
                  "target_domains": ("finance",)}
    # fail-closed 4종.
    assert map_intent_to_exposure_question(
        _intent(query_type=QueryType.CHART_ANALYSIS)) is None
    assert map_intent_to_exposure_question(
        _intent(time_scope=TimeScope.TIMELESS)) is None
    assert map_intent_to_exposure_question(
        _intent(time_range=None)) is None
    assert map_intent_to_exposure_question(
        _intent(subject_mode=SubjectMode.PAIRWISE)) is None
    # 과거 회고 → past_only(게이트가 비주입 판단).
    past = map_intent_to_exposure_question(
        _intent(time_scope=TimeScope.PAST, time_range=None))
    assert past is not None and past["temporal_scope"] == "past_only"


def test_safe_response_sequence_is_fixed() -> None:
    """safe response 우선순위 고정(감수 50차 §3): 재생성 1회→감사→전달/
    fallback→BLOCK — 호출부 임의 선택 금지, 최종 감사 생략 경로 없음."""
    from saju_engines.risk_exposure import plan_safe_response

    assert plan_safe_response(0, False) == "SAFE_REGENERATE_ONCE"
    assert plan_safe_response(1, True) == "DELIVER"
    assert plan_safe_response(1, False) == "DETERMINISTIC_FALLBACK"
    assert plan_safe_response(2, True) == "DELIVER"
    assert plan_safe_response(2, False) == "BLOCK"
    assert plan_safe_response(3, True) == "BLOCK"


def test_adapter_validation_states_gate_expose() -> None:
    """adapter 검증 상태기(감수 50차 §4): 등록≠검증 — EXPOSE 해소는
    VALIDATED만, SHADOW_VALIDATING/SUSPENDED=None(BYPASS)."""
    import pytest as _pytest

    from saju_api.services.token_counter_registry import (
        TokenCounterAdapter,
        register_adapter,
        resolve_counter,
        resolve_validated_counter,
        set_validation_state,
    )

    register_adapter(TokenCounterAdapter(
        model_id="val-model", mode="MODEL_TOKENIZER", counter=len))
    assert resolve_counter("val-model") is not None  # shadow 측정용
    assert resolve_validated_counter("val-model") is None  # 검증 전
    set_validation_state("val-model", "VALIDATED")
    assert resolve_validated_counter("val-model") is not None
    set_validation_state("val-model", "SUSPENDED")
    assert resolve_validated_counter("val-model") is None
    with _pytest.raises(ValueError):
        set_validation_state("val-model", "WHATEVER")


def test_envelope_subsequence_and_presence_contract() -> None:
    """부분수열 검증(감수 50차 §5): A,B,C 입력에서 A,C 허용·B,A 역전 실패.
    None=schema 실패, []=필수 warning 있으면 실패."""
    from saju_engines.risk_claim_audit import (
        validate_injected_guidance_presence,
        validate_risk_guidance_envelope,
    )

    llm = [{"episodeKey": "A", "presentationLevel": "warning"},
           {"episodeKey": "B", "presentationLevel": "watch"},
           {"episodeKey": "C", "presentationLevel": "advisory"}]
    ok = validate_risk_guidance_envelope(
        [{"episode_key": "A", "exposed_level": "warning", "text": "x"},
         {"episode_key": "C", "exposed_level": "advisory", "text": "y"}],
        llm)
    assert ok == []  # watch 생략 + 부분수열 유지
    bad = validate_risk_guidance_envelope(
        [{"episode_key": "B", "exposed_level": "watch", "text": "x"},
         {"episode_key": "A", "exposed_level": "warning", "text": "y"}],
        llm)
    assert any(e.startswith("ORDER_NOT_") for e in bad)
    assert validate_injected_guidance_presence(None, llm) == [
        "RISK_GUIDANCE_FIELD_MISSING"]
    assert validate_injected_guidance_presence([], llm) == [
        "EMPTY_GUIDANCE_WITH_REQUIRED_WARNING"]
    only_watch = [{"episodeKey": "B", "presentationLevel": "watch"}]
    assert validate_injected_guidance_presence([], only_watch) == []


def test_rendered_output_key_leak_and_evidence() -> None:
    """episode_key 비노출(감수 50차 §6) + 감사 evidence(§7 — span·절)."""
    from saju_engines.risk_claim_audit import (
        audit_generated_risk_claims,
        audit_rendered_output,
    )

    leaked = audit_rendered_output(
        "하반기에는 reality:deal_1 관련 점검이 필요합니다.",
        ["reality:deal_1", "explicit:legal:e2"])
    # key 원문 + prefix(감수 51차 확장) 둘 다 검출.
    assert "INTERNAL_KEY_LEAKED:reality:deal_1" in leaked
    assert "INTERNAL_TOKEN_LEAKED:reality:" in leaked
    assert audit_rendered_output("점검이 필요합니다.", ["reality:d"]) == []
    out = audit_generated_risk_claims("이 문제는 거의 확실하게 현실화됩니다.")
    v = out["violations"][0]
    assert v["code"] == "circumvented_certainty"
    assert v["matched_span"][0] >= 0 and "clause_text" in v
    assert v["negation_status"] == "not_negated"


# ── 감수 51차 fixture ─────────────────────────────────────────────


def test_domain_analysis_requires_exactly_one_domain() -> None:
    """§1-1: DOMAIN_ANALYSIS는 도메인 정확히 1개일 때만 매핑 — 0·2개=BYPASS."""
    from saju_engines.risk_question_mapping import (
        map_intent_to_exposure_question,
    )
    from saju_shared_types.intent import (
        Domain,
        IntentJson,
        QueryType,
        TimeRange,
        TimeScope,
    )

    def _intent(domains):
        return IntentJson(
            intent_id="i", query_type=QueryType.DOMAIN_ANALYSIS,
            time_scope=TimeScope.MID_TERM,
            time_range=TimeRange(type="relative", granularity="month",
                                 start="2026-07", end="2026-12"),
            domains=domains)

    ok = map_intent_to_exposure_question(_intent([Domain.CAREER]))
    assert ok is not None and ok["question_type"] == "single_domain_period"
    assert map_intent_to_exposure_question(
        _intent([Domain.CAREER, Domain.WEALTH])) is None
    assert map_intent_to_exposure_question(
        _intent([Domain.GENERAL])) is None  # 실질 도메인 0개


def test_specific_event_requires_resolved_target() -> None:
    """§1-2: EVENT_EXPLANATION/DECISION_SUPPORT는 파서가 해소한 event
    target(event_key)이 있을 때만 — 광역 질문=BYPASS."""
    from saju_engines.risk_question_mapping import (
        map_intent_to_exposure_question,
    )
    from saju_shared_types.intent import (
        IntentJson,
        QueryType,
        TimeRange,
        TimeScope,
    )

    def _intent(**kw):
        base = dict(intent_id="i", query_type=QueryType.DECISION_SUPPORT,
                    time_scope=TimeScope.SHORT_TERM,
                    time_range=TimeRange(type="relative",
                                         granularity="month",
                                         start="2026-08", end="2026-10"))
        base.update(kw)
        return IntentJson(**base)

    assert map_intent_to_exposure_question(_intent()) is None  # target 없음
    ok = map_intent_to_exposure_question(
        _intent(event_key="career_change"))
    assert ok is not None and ok["question_type"] == "specific_event"


def test_safe_fallback_template_is_policy() -> None:
    """§4-D: fallback 문구=정책(hash 포함) — 단정·보장·시스템 설명·추측
    표현 부재, 자체 claim audit 통과."""
    from saju_engines.risk_claim_audit import audit_generated_risk_claims
    from saju_engines.risk_exposure import (
        RISK_SAFE_FALLBACK_TEMPLATE,
        RISK_SAFE_FALLBACK_VERSION,
        expose_policy_hash,
    )

    assert RISK_SAFE_FALLBACK_VERSION.startswith("risk-safe-fallback-")
    out = audit_generated_risk_claims(RISK_SAFE_FALLBACK_TEMPLATE)
    assert out["action"] == "ALLOW"
    for banned in ("위험이 없", "발생하지 않", "게이트", "감수", "검증 실패"):
        assert banned not in RISK_SAFE_FALLBACK_TEMPLATE
    assert len(expose_policy_hash()) == 16  # template이 hash에 편입됨


def test_adapter_validation_policy_fixed_before_measurement() -> None:
    """§6-B: 승격 기준이 실측 전 고정(hash·manifest 병기) — 과소 계산
    불허·validation key·표본 목록 포함."""
    import json
    from pathlib import Path

    from saju_api.services.token_counter_registry import (
        ADAPTER_VALIDATION_POLICY,
        adapter_validation_policy_hash,
    )

    assert "과소 계산 불허" in ADAPTER_VALIDATION_POLICY[
        "model_tokenizer_pass"]
    assert "provider_request_schema_version" in ADAPTER_VALIDATION_POLICY[
        "validation_key"]
    manifest = json.loads(
        (Path(__file__).resolve().parents[2].parent / "doc" / "v2_2"
         / "RISK_REVIEW_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["adapter_validation_policy_hash"] == (
        adapter_validation_policy_hash())


def test_rendered_leak_covers_prefixes_and_internal_ids() -> None:
    """§9: key 원문 외 prefix·내부 enum·risk_id/cause_atom 노출도 검출."""
    from saju_engines.risk_claim_audit import audit_rendered_output

    leaks = audit_rendered_output(
        "이 시기의 reality: 연결 신호와 LEG_CONTRACT_TERMINATION_RISK를"
        " 주의하세요.",
        episode_keys=[], internal_ids=["LEG_CONTRACT_TERMINATION_RISK"])
    codes = {leak.split(":")[0] for leak in leaks}
    assert "INTERNAL_TOKEN_LEAKED" in codes
    assert "INTERNAL_ID_LEAKED" in codes
    assert audit_rendered_output("일정과 문서를 점검해 두세요.", []) == []


def test_violation_evidence_has_hash_for_general_logs() -> None:
    """§10: 일반 로그용 clause_hash·길이 병기(원문은 80자 제한 표본 전용)."""
    from saju_engines.risk_claim_audit import audit_generated_risk_claims

    out = audit_generated_risk_claims("계약 파기가 거의 확실하게 진행됩니다.")
    v = out["violations"][0]
    assert len(v["clause_hash"]) == 16 and v["clause_len"] > 0  # HMAC 16자
    assert len(v["clause_text"]) <= 80


# ── 감수 52차 fixture ─────────────────────────────────────────────


def test_domain_dedup_before_count() -> None:
    """§1: 도메인 중복 제거 후 개수 판정 — [career, career]=1개 허용."""
    from saju_engines.risk_question_mapping import (
        map_intent_to_exposure_question,
    )
    from saju_shared_types.intent import (
        Domain,
        IntentJson,
        QueryType,
        TimeRange,
        TimeScope,
    )

    intent = IntentJson(
        intent_id="i", query_type=QueryType.DOMAIN_ANALYSIS,
        time_scope=TimeScope.MID_TERM,
        time_range=TimeRange(type="relative", granularity="month",
                             start="2026-07", end="2026-12"),
        domains=[Domain.CAREER, Domain.CAREER, Domain.GENERAL])
    ok = map_intent_to_exposure_question(intent)
    assert ok is not None and ok["question_type"] == "single_domain_period"


def test_order_fingerprint_detects_wrong_array() -> None:
    """§3: llmEpisodeOrderHash — validator가 records(잘못된 배열)를 받으면
    EPISODE_ORDER_SOURCE_MISMATCH, 최종 llmRiskEpisodes면 통과."""
    from saju_engines.risk_claim_audit import (
        validate_risk_guidance_envelope,
    )
    from saju_engines.risk_presentation import llm_episode_order_hash

    llm = [{"episodeKey": "A", "presentationLevel": "warning",
            "domains": ["contract_legal"], "effectRoles": ["x"]},
           {"episodeKey": "B", "presentationLevel": "watch",
            "domains": ["finance"], "effectRoles": ["y"]}]
    wrong = list(reversed(llm))  # records/필터 전 순서를 흉내
    expected = llm_episode_order_hash(llm)
    sections = [{"episode_key": "A", "exposed_level": "warning",
                 "text": "점검"}]
    assert validate_risk_guidance_envelope(
        sections, llm, expected_order_hash=expected) == []
    out = validate_risk_guidance_envelope(
        sections, wrong, expected_order_hash=expected)
    assert out == ["EPISODE_ORDER_SOURCE_MISMATCH"]


def test_new_fallback_wording_and_hash_updated() -> None:
    """§4: 교정된 fallback 문구 — 시스템 실패 직접 노출 없음·audit ALLOW·
    버전 r1.1.0."""
    from saju_engines.risk_claim_audit import audit_generated_risk_claims
    from saju_engines.risk_exposure import (
        RISK_SAFE_FALLBACK_TEMPLATE,
        RISK_SAFE_FALLBACK_VERSION,
    )

    assert RISK_SAFE_FALLBACK_VERSION == "risk-safe-fallback-r1.1.0"
    assert "안전하게 구성하지 못했" not in RISK_SAFE_FALLBACK_TEMPLATE
    assert "실제 일정과 조건" in RISK_SAFE_FALLBACK_TEMPLATE
    assert audit_generated_risk_claims(
        RISK_SAFE_FALLBACK_TEMPLATE)["action"] == "ALLOW"


def test_strict_policy_section_rejects_unknown_fields(tmp_path,
                                                      monkeypatch) -> None:
    """§5: expose_pipeline 구간 미등록 필드=fail-closed."""
    import json

    from saju_api.services import risk_exposure_service as svc

    manifest = json.loads(svc._MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["expose_pipeline"]["surprise_policy"] = True
    bad = tmp_path / "manifest.json"
    bad.write_text(json.dumps(manifest, ensure_ascii=False),
                   encoding="utf-8")
    monkeypatch.setattr(svc, "_MANIFEST_PATH", bad)
    snap = svc._load_manifest_snapshot()
    assert snap["reviewed"] is False and snap["hash_ok"] is False


def test_adapter_manifest_ssot_and_drift_suspend() -> None:
    """§2: registry 자체 VALIDATED 선언만으로 EXPOSE 자격 불가 — manifest
    항목 일치 필요. drift(counted<reported) 1건=즉시 SUSPENDED."""
    from saju_api.services.token_counter_registry import (
        TokenCounterAdapter,
        adapter_validation_policy_hash,
        record_count_observation,
        register_adapter,
        resolve_expose_counter,
        set_validation_state,
    )

    register_adapter(TokenCounterAdapter(
        model_id="ssot-model", mode="MODEL_TOKENIZER", counter=len,
        provider_id="prov", counter_version="v1",
        request_schema_version="1", validation_corpus_hash="corpus-abc"))
    set_validation_state("ssot-model", "VALIDATED")
    # manifest 항목 없음 → None(BYPASS).
    assert resolve_expose_counter("ssot-model", []) is None
    # 확장 대조 키(감수 53차 §2 + 55차 §1): schemaVersion·countMode·
    # policy/corpus hash 포함(corpus는 adapter 값과 일치).
    entry = {"reviewed": True, "resolvedModelId": "ssot-model",
             "providerId": "prov", "counterVersion": "v1",
             "providerRequestSchemaVersion": "1",
             "countMode": "MODEL_TOKENIZER",
             "validationPolicyHash": adapter_validation_policy_hash(),
             "validationCorpusHash": "corpus-abc"}
    assert resolve_expose_counter("ssot-model", [entry]) is not None
    # reviewed=false·key 불일치·artifact 부재 → None.
    assert resolve_expose_counter(
        "ssot-model", [{**entry, "reviewed": False}]) is None
    assert resolve_expose_counter(
        "ssot-model", [{**entry, "counterVersion": "v2"}]) is None
    assert resolve_expose_counter(
        "ssot-model",
        [{**entry, "providerRequestSchemaVersion": "2"}]) is None
    assert resolve_expose_counter(
        "ssot-model", [{**entry, "validationPolicyHash": "stale"}]) is None
    assert resolve_expose_counter(
        "ssot-model", [{**entry, "validationCorpusHash": ""}]) is None
    assert resolve_expose_counter(
        "ssot-model", [{**entry, "countMode": "PROVIDER_EXACT"}]) is None
    # drift: 과소 계산 1건 → 전역 SUSPENDED(공유 파일·identity 기준·
    # 잠금 하 기록) → 이후 해소 불가.
    from saju_api.services.token_counter_registry import (
        _SUSPENSION_FILE,
        _shared_suspensions,
        adapter_identity_hash,
        resolve_counter,
    )

    adapter = resolve_counter("ssot-model")
    assert adapter is not None
    identity = adapter_identity_hash(adapter)
    record_count_observation("ssot-model", counted=100, reported=120,
                             request_id_hash="req-1")
    assert resolve_expose_counter("ssot-model", [entry]) is None
    records, ok = _shared_suspensions()
    assert ok is True
    rec = records[identity]
    assert rec["undercount_detected_count"] >= 1
    assert len(rec["first_undercount_request_id_hash"]) == 16  # HMAC
    # 정리(테스트 격리 — 항목 제거는 재감수 절차의 모의: 실제 운영에선
    # 새 identity 감수로만 복구하며 tombstone ledger는 삭제 금지).
    import json as _json

    from saju_api.services.token_counter_registry import _SUSPENSION_LEDGER
    remaining = {k: v for k, v in records.items() if k != identity}
    _SUSPENSION_FILE.write_text(_json.dumps(remaining), encoding="utf-8")
    if _SUSPENSION_LEDGER.exists():
        kept = [line for line in _SUSPENSION_LEDGER.read_text(
            encoding="utf-8").splitlines()
            if line.strip() and identity not in line]
        _SUSPENSION_LEDGER.write_text(
            "\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


def test_injected_output_schema_contract() -> None:
    """§7: INJECTED 전용 schema — additionalProperties=false·maxItems=
    hard_max·episode_key/level enum(후처리 validator 병행 전제)."""
    from saju_engines.risk_claim_audit import build_risk_output_schema

    llm = [{"guidanceRef": "rg1", "presentationLevel": "warning"},
           {"guidanceRef": "rg2", "presentationLevel": "watch"}]
    schema = build_risk_output_schema(llm, hard_max=3)
    assert schema["additionalProperties"] is False
    guidance = schema["properties"]["risk_guidance"]
    # 감수 53차 §9: 실제 최종 episode 수(2)가 정확한 상한 — hard_max는 상한.
    assert guidance["maxItems"] == 2
    assert guidance["minItems"] == 1  # warning 1건=필수 최소
    item = guidance["items"]
    assert item["additionalProperties"] is False
    # opaque guidanceRef(감수 54차 §5) — canonical key 대신 요청 단위 참조.
    assert set(item["properties"]["guidance_ref"]["enum"]) == {"rg1", "rg2"}
    assert set(item["properties"]["exposed_level"]["enum"]) == {
        "warning", "watch"}


def test_clause_hash_is_keyed_hmac() -> None:
    """§6: clause_hash=keyed HMAC(16자) — key가 다르면 hash가 다르다."""
    from saju_engines import risk_engine_config
    from saju_engines.risk_claim_audit import audit_generated_risk_claims

    text = "계약 파기가 거의 확실하게 진행됩니다."
    h1 = audit_generated_risk_claims(text)["violations"][0]["clause_hash"]
    assert len(h1) == 16
    original = risk_engine_config.RISK_AUDIT_HMAC_KEY
    try:
        risk_engine_config.RISK_AUDIT_HMAC_KEY = b"other-key"
        h2 = audit_generated_risk_claims(
            text)["violations"][0]["clause_hash"]
    finally:
        risk_engine_config.RISK_AUDIT_HMAC_KEY = original
    assert h1 != h2


# ── 감수 54차 fixture ─────────────────────────────────────────────


def test_concurrent_suspension_writes_are_not_lost() -> None:
    """§2: 동시 writer 갱신 유실 차단(flock read-modify-write) — adapter
    A·B를 병렬 기록해도 최종 파일에 둘 다 존재."""
    import json as _json
    import threading

    from saju_api.services.token_counter_registry import (
        _SUSPENSION_FILE,
        TokenCounterAdapter,
        adapter_identity_hash,
        record_count_observation,
        register_adapter,
    )

    ids = []
    for name in ("conc-a", "conc-b"):
        adapter = TokenCounterAdapter(
            model_id=name, mode="MODEL_TOKENIZER", counter=len,
            provider_id="prov", counter_version="v1")
        register_adapter(adapter)
        ids.append(adapter_identity_hash(adapter))
    threads = [threading.Thread(
        target=record_count_observation,
        args=(name, 10, 20), kwargs={"request_id_hash": name})
        for name in ("conc-a", "conc-b")]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    records = _json.loads(_SUSPENSION_FILE.read_text(encoding="utf-8"))
    assert all(identity in records for identity in ids)
    # 정리(테스트 격리).
    remaining = {k: v for k, v in records.items() if k not in ids}
    _SUSPENSION_FILE.write_text(_json.dumps(remaining), encoding="utf-8")


def test_suspension_store_corruption_is_bypass(monkeypatch) -> None:
    """§2: 저장소 손상='suspension 없음'이 아니라 불가용 → 해소 전부
    None(BYPASS)."""
    from saju_api.services import token_counter_registry as reg
    from saju_api.services.token_counter_registry import (
        TokenCounterAdapter,
        adapter_validation_policy_hash,
        register_adapter,
        resolve_expose_counter,
        set_validation_state,
        suspension_state_ok,
    )

    register_adapter(TokenCounterAdapter(
        model_id="corrupt-model", mode="MODEL_TOKENIZER", counter=len,
        provider_id="prov", counter_version="v1",
        validation_corpus_hash="corpus"))
    set_validation_state("corrupt-model", "VALIDATED")
    entry = {"reviewed": True, "resolvedModelId": "corrupt-model",
             "providerId": "prov", "counterVersion": "v1",
             "providerRequestSchemaVersion": "1",
             "countMode": "MODEL_TOKENIZER",
             "validationPolicyHash": adapter_validation_policy_hash(),
             "validationCorpusHash": "corpus"}
    assert resolve_expose_counter("corrupt-model", [entry]) is not None
    # 손상 파일 주입 → 불가용 → BYPASS.
    bad = reg._SUSPENSION_FILE
    bad.parent.mkdir(parents=True, exist_ok=True)
    original = bad.read_text(encoding="utf-8") if bad.exists() else None
    try:
        bad.write_text("{corrupted json", encoding="utf-8")
        assert suspension_state_ok() is False
        assert resolve_expose_counter("corrupt-model", [entry]) is None
    finally:
        if original is None:
            bad.unlink(missing_ok=True)
        else:
            bad.write_text(original, encoding="utf-8")


def test_llm_payload_uses_opaque_guidance_ref() -> None:
    """§5: LLM payload에 canonical episodeKey 부재 — guidanceRef(rg1…)만,
    canonical 연결은 guidanceRefMap(감사 전용)·직렬화 제외."""
    import json as _json

    from saju_engines.risk_presentation import (
        build_presentation,
        serialize_llm_payload,
    )
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
    cands = score_shadow([RiskCandidate(
        risk_id="LEG_A", domain=RiskDomain.CONTRACT_LEGAL,
        kind=RiskKind.INCIDENT_RISK, risk_family="fam", period_key="2026",
        evidence=[RiskEvidence(
            evidence_id=f"2026|{src}", code="T", period_key="2026",
            layer="sewoon", source=src, strength=0.5,
            role=EvidenceRole.TRIGGER, source_group="event_shape",
            target_domain=RiskDomain.CONTRACT_LEGAL)],
        exposure_status=ExposureStatus.CONFIRMED, specificity_rank=2,
        normalized_effect_role="legal_dispute", trigger_cause_atoms=[src],
        legal_episode_id="e1")], {"LEG_A": 0.6})
    payload = build_presentation(build_episodes(cands), cands)
    llm = payload["llmRiskEpisodes"]
    assert [e["guidanceRef"] for e in llm] == [
        f"rg{i + 1}" for i in range(len(llm))]
    assert all("episodeKey" not in e for e in llm)
    ref_map = payload["guidanceRefMap"]
    assert set(ref_map) == {e["guidanceRef"] for e in llm}
    assert all(v.startswith(("explicit:", "reality:", "fallback:",
                             "conflict:")) for v in ref_map.values())
    rendered = serialize_llm_payload(payload, token_budget=100_000)
    doc = _json.loads(rendered)
    assert "guidanceRefMap" not in doc  # 감사 전용 — LLM 비노출
    assert all("episodeKey" not in e for e in doc["riskEpisodes"])
    assert all(e.get("guidanceRef") for e in doc["riskEpisodes"])


def test_order_fingerprint_uses_canonical_identity() -> None:
    """§6: fingerprint는 ref가 아니라 canonical identity 기준 — 같은 ref
    배열이라도 canonical 구성이 다르면 hash가 다르다."""
    from saju_engines.risk_presentation import llm_episode_order_hash

    llm = [{"guidanceRef": "rg1", "presentationLevel": "warning"}]
    h1 = llm_episode_order_hash(llm, {"rg1": "reality:deal_1"})
    h2 = llm_episode_order_hash(llm, {"rg1": "explicit:legal:e9"})
    assert h1 != h2  # 같은 rg1이어도 canonical이 다르면 상이


# ── 감수 55차 fixture ─────────────────────────────────────────────


def test_new_corpus_hash_creates_new_identity() -> None:
    """§1: 같은 adapter + 새 validationCorpusHash → 새 validation identity
    — 기존 suspension 미적용·새 manifest 감수 전에는 여전히 BYPASS."""
    from saju_api.services.token_counter_registry import (
        TokenCounterAdapter,
        adapter_identity_hash,
        adapter_validation_policy_hash,
        register_adapter,
        resolve_expose_counter,
        set_validation_state,
    )

    def _make(corpus: str) -> TokenCounterAdapter:
        return TokenCounterAdapter(
            model_id="corpus-model", mode="MODEL_TOKENIZER", counter=len,
            provider_id="prov", counter_version="v1",
            request_schema_version="1", validation_corpus_hash=corpus)

    old_adapter = _make("corpus-old")
    new_adapter = _make("corpus-new")
    assert adapter_identity_hash(old_adapter) != adapter_identity_hash(
        new_adapter)  # corpus 변경=새 identity
    # 새 identity 등록·VALIDATED여도 manifest entry의 corpus hash가
    # 어긋나면 BYPASS.
    register_adapter(new_adapter)
    set_validation_state("corpus-model", "VALIDATED")
    entry = {"reviewed": True, "resolvedModelId": "corpus-model",
             "providerId": "prov", "counterVersion": "v1",
             "providerRequestSchemaVersion": "1",
             "countMode": "MODEL_TOKENIZER",
             "validationPolicyHash": adapter_validation_policy_hash(),
             "validationCorpusHash": "corpus-old"}  # 옛 corpus로 감수됨
    assert resolve_expose_counter("corpus-model", [entry]) is None
    assert resolve_expose_counter(
        "corpus-model",
        [{**entry, "validationCorpusHash": "corpus-new"}]) is not None


def test_lock_file_is_dedicated_and_stable() -> None:
    """§2: flock 대상=교체되지 않는 전용 lock 파일(데이터 파일과 분리) —
    atomic replace 후에도 lock inode 불변."""
    from saju_api.services.token_counter_registry import (
        _SUSPENSION_FILE,
        _SUSPENSION_LOCK_FILE,
    )

    assert _SUSPENSION_LOCK_FILE != _SUSPENSION_FILE
    assert _SUSPENSION_LOCK_FILE.parent == _SUSPENSION_FILE.parent
    assert _SUSPENSION_LOCK_FILE.suffix == ".lock"


def test_guidance_ref_leak_in_final_text_detected() -> None:
    """§8: opaque ref가 최종 사용자 문장에 남으면
    INTERNAL_GUIDANCE_REF_LEAKED — guidance_ref 필드 제거만으로는 text 안
    'rg1'이 사라지지 않는다."""
    from saju_engines.risk_claim_audit import audit_rendered_output

    leaks = audit_rendered_output(
        "rg1 항목은 주의가 필요합니다. rg2도 함께 보세요.",
        episode_keys=[], issued_refs=["rg1", "rg2"])
    assert "INTERNAL_GUIDANCE_REF_LEAKED:rg1" in leaks
    assert "INTERNAL_GUIDANCE_REF_LEAKED:rg2" in leaks
    assert audit_rendered_output(
        "계약 조건을 점검해 두면 좋은 시기입니다.", [],
        issued_refs=["rg1"]) == []


def test_guidance_reference_context_is_immutable_snapshot() -> None:
    """§7·9: 최종 payload에서 요청 단위 불변 snapshot(refMap·orderHash·
    policy hash) 생성 — 전 과정이 동일 객체를 소비(재계산 금지)."""
    import dataclasses

    import pytest as _pytest

    from saju_engines.risk_exposure import (
        build_guidance_reference_context,
        expose_policy_hash,
    )

    payload = {"guidanceRefMap": {"rg1": "explicit:legal:e1"},
               "llmEpisodeOrderHash": "abc123"}
    ctx = build_guidance_reference_context("req-1", payload)
    assert ctx.refs() == ["rg1"]
    assert ctx.llm_episode_order_hash == "abc123"
    assert ctx.expose_policy_hash == expose_policy_hash()
    with _pytest.raises(dataclasses.FrozenInstanceError):
        ctx.request_context_id = "req-2"  # type: ignore[misc]


def test_unsupported_topology_disables_suspension_state(monkeypatch) -> None:
    """§6: 미지원 backend·topology 조합=전역 suspension 미보장 →
    suspension_state_ok=False(전부 BYPASS)."""
    from saju_api.services.token_counter_registry import (
        suspension_state_ok,
    )
    from saju_engines import risk_engine_config

    assert suspension_state_ok() is True
    monkeypatch.setattr(risk_engine_config, "RISK_DEPLOYMENT_TOPOLOGY",
                        "kubernetes_multi_pod")
    assert suspension_state_ok() is False


def test_persistence_failure_marker_disables_exposure(monkeypatch,
                                                      tmp_path) -> None:
    """§4: suspension 기록 실패 → 전역 marker → 모든 해소 BYPASS."""
    from saju_api.services import token_counter_registry as reg

    marker = tmp_path / "exposure_disabled.marker"
    monkeypatch.setattr(reg, "_EXPOSURE_DISABLED_MARKER", marker)
    assert reg.suspension_state_ok() is True
    marker.write_text("suspension_persistence_failed", encoding="utf-8")
    assert reg.suspension_state_ok() is False


def test_suspension_tombstone_survives_state_file_deletion(
        monkeypatch, tmp_path) -> None:
    """감수 56차 §5: state 파일 삭제·항목 제거만으로 옛 identity가
    부활하지 않는다 — append-only ledger(tombstone)가 계속 차단."""
    from saju_api.services import token_counter_registry as reg
    from saju_api.services.token_counter_registry import (
        TokenCounterAdapter,
        adapter_identity_hash,
        adapter_validation_policy_hash,
        record_count_observation,
        register_adapter,
        resolve_expose_counter,
        set_validation_state,
    )

    monkeypatch.setattr(reg, "_SUSPENSION_FILE",
                        tmp_path / "adapter_suspensions.json")
    monkeypatch.setattr(reg, "_SUSPENSION_LOCK_FILE",
                        tmp_path / "adapter_suspensions.lock")
    monkeypatch.setattr(reg, "_SUSPENSION_LEDGER",
                        tmp_path / "adapter_suspensions_ledger.jsonl")
    monkeypatch.setattr(reg, "_EXPOSURE_DISABLED_MARKER",
                        tmp_path / "exposure_disabled.marker")
    register_adapter(TokenCounterAdapter(
        model_id="tomb-model", mode="MODEL_TOKENIZER", counter=len,
        provider_id="prov", counter_version="v1",
        validation_corpus_hash="corpus"))
    set_validation_state("tomb-model", "VALIDATED")
    entry = {"reviewed": True, "resolvedModelId": "tomb-model",
             "providerId": "prov", "counterVersion": "v1",
             "providerRequestSchemaVersion": "1",
             "countMode": "MODEL_TOKENIZER",
             "validationPolicyHash": adapter_validation_policy_hash(),
             "validationCorpusHash": "corpus"}
    assert resolve_expose_counter("tomb-model", [entry]) is not None
    record_count_observation("tomb-model", counted=10, reported=20)
    assert resolve_expose_counter("tomb-model", [entry]) is None
    # state 파일 전체 삭제 — ledger tombstone이 남아 있어 계속 차단.
    reg._SUSPENSION_FILE.unlink()
    set_validation_state("tomb-model", "VALIDATED")  # 로컬 상태 복구 모의
    assert reg._SUSPENSION_LEDGER.exists()
    assert resolve_expose_counter("tomb-model", [entry]) is None
    identity = adapter_identity_hash(reg._REGISTRY["tomb-model"])
    assert identity in reg._SUSPENSION_LEDGER.read_text(encoding="utf-8")
    set_validation_state("tomb-model", "SUSPENDED")


def test_suspension_ledger_corruption_is_bypass(
        monkeypatch, tmp_path) -> None:
    """감수 56차 §5: ledger 손상=저장소 불가용(suspension 없음 아님) →
    suspension_state_ok=False(전부 BYPASS)."""
    from saju_api.services import token_counter_registry as reg

    monkeypatch.setattr(reg, "_SUSPENSION_FILE",
                        tmp_path / "adapter_suspensions.json")
    monkeypatch.setattr(reg, "_SUSPENSION_LEDGER",
                        tmp_path / "adapter_suspensions_ledger.jsonl")
    monkeypatch.setattr(reg, "_EXPOSURE_DISABLED_MARKER",
                        tmp_path / "exposure_disabled.marker")
    assert reg.suspension_state_ok() is True
    reg._SUSPENSION_LEDGER.write_text('{"부분 json', encoding="utf-8")
    assert reg.suspension_state_ok() is False


def test_guidance_ref_leak_unicode_variants_detected() -> None:
    """감수 56차 §6: NFKC(전각)·casefold(대문자)·zero-width 삽입 변형도
    INTERNAL_GUIDANCE_REF_LEAKED — zero-width 존재 자체도 검출."""
    from saju_engines.risk_claim_audit import audit_rendered_output

    assert "INTERNAL_GUIDANCE_REF_LEAKED:rg2" in audit_rendered_output(
        "RG2 항목을 확인하세요.", [], issued_refs=["rg2"])
    assert "INTERNAL_GUIDANCE_REF_LEAKED:rg2" in audit_rendered_output(
        "Rg2 항목을 확인하세요.", [], issued_refs=["rg2"])
    assert "INTERNAL_GUIDANCE_REF_LEAKED:rg2" in audit_rendered_output(
        "ｒｇ２ 항목을 확인하세요.", [], issued_refs=["rg2"])
    zw = audit_rendered_output(
        "r\u200bg2 항목을 확인하세요.", [], issued_refs=["rg2"])
    assert "INTERNAL_GUIDANCE_REF_LEAKED:rg2" in zw
    assert "OBFUSCATION_ZERO_WIDTH_DETECTED" in zw
    # 정상 문장(변형 없음)은 통과.
    assert audit_rendered_output(
        "규모 2의 문제가 아니라 일정 관리의 문제입니다.", [],
        issued_refs=["rg1"]) == []


def test_guidance_context_binding_mismatch() -> None:
    """감수 56차 §7: 다른 요청의 context 재사용·snapshot과 다른 payload
    소비 → GUIDANCE_CONTEXT_MISMATCH(REVISE/BLOCK — 전달 금지)."""
    from saju_engines.risk_exposure import (
        GUIDANCE_CONTEXT_MISMATCH,
        build_guidance_reference_context,
        verify_guidance_context,
    )

    payload = {"guidanceRefMap": {"rg1": "explicit:legal:e1"},
               "llmEpisodeOrderHash": "abc123"}
    ctx = build_guidance_reference_context("req-1", payload)
    assert verify_guidance_context(ctx, "req-1", payload) == []
    assert verify_guidance_context(ctx, "req-2") == [
        GUIDANCE_CONTEXT_MISMATCH]
    mutated = {"guidanceRefMap": {"rg1": "explicit:legal:e9"},
               "llmEpisodeOrderHash": "abc123"}
    assert verify_guidance_context(ctx, "req-1", mutated) == [
        GUIDANCE_CONTEXT_MISMATCH]


def test_canary_topology_eligibility_gate(monkeypatch) -> None:
    """감수 56차 §4: marker 기록까지 실패해도 전 worker 차단이 보장되지
    않는 조합(file+multi-worker)은 EXPOSE 진입 자체가 BYPASS — 파일
    backend의 canary 자격은 single_host_single_process뿐."""
    from saju_engines import risk_engine_config as cfg
    from saju_engines.risk_exposure import (
        ExposureGateContext,
        evaluate_risk_exposure_gate,
    )
    from saju_shared_types.risk_engine import RiskEngineMode

    assert (("file", "single_host_shared_state")
            not in cfg._CANARY_ELIGIBLE_SUSPENSION_COMBOS)
    assert (("file", "single_host_single_process")
            in cfg._CANARY_ELIGIBLE_SUSPENSION_COMBOS)
    ctx = ExposureGateContext(
        mode=RiskEngineMode.EXPOSE_CANARY, question_type="specific_event",
        temporal_scope="future", risk_intent_allowed=True,
        token_count_mode="MODEL_TOKENIZER", model_context_limit=100000,
        base_prompt_tokens=100, user_input_tokens=10,
        existing_context_tokens=0, response_reserve=100,
        scopes_all_reviewed=True, policy_hashes_match=True,
        canary_allowlisted=True, expose_pipeline_reviewed=True,
        counter_model_id="m", resolved_model_id="m",
        topology_canary_eligible=False)
    result = evaluate_risk_exposure_gate(
        ctx, {"globalProhibitedClaimCodes": [],
              "globalAllowedClaimCodes": [], "presentationRecords": [],
              "llmRiskEpisodes": []}, counter=len)
    assert result["disposition"] == "BYPASS"
    assert ("DEPLOYMENT_TOPOLOGY_UNSUPPORTED"
            in result["observability"]["all_reasons"])


def test_crash_during_lock_hold_recovers(monkeypatch, tmp_path) -> None:
    """감수 56차 §2: process A가 lock 보유 중 SIGKILL → OS가 flock 회수 →
    process B(현 프로세스) 정상 진입·기록, suspension JSON은 완성본만
    존재(부분 JSON 없음). 실제 별도 process 기반."""
    import json as _json
    import signal
    import subprocess
    import sys
    import time

    from saju_api.services import token_counter_registry as reg
    from saju_api.services.token_counter_registry import (
        TokenCounterAdapter,
        record_count_observation,
        register_adapter,
    )

    state = tmp_path / "adapter_suspensions.json"
    lock = tmp_path / "adapter_suspensions.lock"
    monkeypatch.setattr(reg, "_SUSPENSION_FILE", state)
    monkeypatch.setattr(reg, "_SUSPENSION_LOCK_FILE", lock)
    monkeypatch.setattr(reg, "_SUSPENSION_LEDGER",
                        tmp_path / "ledger.jsonl")
    monkeypatch.setattr(reg, "_EXPOSURE_DISABLED_MARKER",
                        tmp_path / "exposure_disabled.marker")
    # process A: 전용 lock 파일 flock 획득 + 데이터 파일에 '부분 쓰기'
    # (crash 직전 상태 모의) 후 신호를 보내고 대기 — SIGKILL로 종료.
    child_src = (
        "import fcntl, sys, time\n"
        "f = open(sys.argv[1], 'w')\n"
        "fcntl.flock(f, fcntl.LOCK_EX)\n"
        "open(sys.argv[2] + '.tmp-crash', 'w').write('{\"부분')\n"
        "print('LOCKED', flush=True)\n"
        "time.sleep(30)\n")
    proc = subprocess.Popen(
        [sys.executable, "-c", child_src, str(lock), str(state)],
        stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "LOCKED"
        proc.send_signal(signal.SIGKILL)
        deadline = time.time() + 10
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.05)
        assert proc.poll() is not None
        # process B: OS가 flock을 회수했으므로 정상 진입·기록된다.
        register_adapter(TokenCounterAdapter(
            model_id="crash-model", mode="MODEL_TOKENIZER", counter=len,
            provider_id="prov", counter_version="v1",
            validation_corpus_hash="corpus"))
        record_count_observation("crash-model", counted=1, reported=2)
        # 데이터 파일은 완성된 JSON — 부분 쓰기 잔재는 데이터 파일이 아님.
        records = _json.loads(state.read_text(encoding="utf-8"))
        assert any(v.get("model_id") == "crash-model"
                   for v in records.values())
        assert not reg._EXPOSURE_DISABLED_MARKER.exists()
    finally:
        if proc.poll() is None:
            proc.kill()


def test_transport_schema_separated_from_canonical() -> None:
    """감수 57차 §4: canonical 정본은 약화되지 않는다 — transport는
    provider 수용용 축소 표현일 뿐(additionalProperties 제거·type 대문자),
    canonical 계약(additionalProperties=false·enum·minItems)은 유지."""
    from saju_api.services.gemini_token_adapter import (
        build_gemini_transport_schema,
    )
    from saju_engines.risk_claim_audit import build_risk_output_schema

    llm = [{"guidanceRef": "rg1", "presentationLevel": "warning"},
           {"guidanceRef": "rg2", "presentationLevel": "watch"}]
    canonical = build_risk_output_schema(llm, hard_max=3)
    transport = build_gemini_transport_schema(canonical)
    # canonical 정본 유지(입력 불변·계약 보존).
    assert canonical["additionalProperties"] is False
    guidance = canonical["properties"]["risk_guidance"]
    assert guidance["minItems"] == 1
    # transport: 미지원 키 제거·type 대문자·enum/required 보존.
    assert "additionalProperties" not in transport
    assert transport["type"] == "OBJECT"
    t_item = transport["properties"]["risk_guidance"]["items"]
    assert "additionalProperties" not in t_item
    assert set(t_item["properties"]["guidance_ref"]["enum"]) == {
        "rg1", "rg2"}


def test_output_schema_three_state_wiring(monkeypatch) -> None:
    """감수 57차 §10-3: BYPASS/SUPPRESSED=기존 schema 그대로(schema 키
    부재·output_schema_state=BASE_UNCHANGED), INJECTED만 RISK_ENABLED +
    canonical/transport 병행 산출."""
    from saju_api.services.risk_exposure_service import apply_risk_exposure

    # BYPASS(비허용 canary): schema 키 자체가 없음.
    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE",
                        "expose_canary")
    _p, _s, obs = apply_risk_exposure(
        "본문", None, subject_id=None,
        question_type="period_overview", temporal_scope="future")
    assert obs["disposition"] == "BYPASS"
    assert obs["output_schema_state"] == "BASE_UNCHANGED"
    assert "risk_output_schemas" not in obs
    # SUPPRESSED(자격 충족·episode 없음): guard만 — schema 불변.
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSE_CANARY_SUBJECT_IDS",
                        frozenset({"internal-tester-1"}))
    monkeypatch.setattr(risk_engine_config,
                        "RISK_DEPLOYMENT_TOPOLOGY",
                        "single_host_single_process")
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSURE_RUNTIME_ENABLED", True)
    monkeypatch.setattr(risk_engine_config, "RISK_AUDIT_HMAC_KEY",
                        b"a" * 32)
    from saju_api.services import risk_exposure_service as _svc
    monkeypatch.setattr(_svc, "_load_manifest_snapshot",
                        lambda: {"reviewed": True, "hash_ok": True,
                                 "schema_version": 10,
                                 "snapshot_hash": "mock"})
    _p, _s, obs = apply_risk_exposure(
        "본문", None, subject_id="internal-tester-1",
        question_type="period_overview", temporal_scope="future",
        counter=lambda t: max(1, len(t) // 4),
        counter_model_id="m1", resolved_model_id="m1",
        model_context_limit=16_000, base_prompt_tokens=1_000,
        user_input_tokens=100, existing_context_tokens=1_000,
        response_reserve=2_000)
    assert obs["disposition"] == "SUPPRESSED"
    assert obs["output_schema_state"] == "BASE_UNCHANGED"
    assert "risk_output_schemas" not in obs
    # INJECTED: canonical+transport 병행 산출, hard_max=질문 유형 정책.
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
    _p, _s, obs = apply_risk_exposure(
        "본문", None, subject_id="internal-tester-1", payload=payload,
        question_type="period_overview", temporal_scope="future",
        counter=lambda t: max(1, len(t) // 4),
        counter_model_id="m1", resolved_model_id="m1",
        model_context_limit=100_000, base_prompt_tokens=1_000,
        user_input_tokens=100, existing_context_tokens=1_000,
        response_reserve=2_000)
    assert obs["disposition"] == "INJECTED"
    assert obs["output_schema_state"] == "RISK_ENABLED"
    schemas = obs["risk_output_schemas"]
    assert schemas["canonical"]["additionalProperties"] is False
    assert "additionalProperties" not in schemas["gemini_transport"]
    guidance = schemas["canonical"]["properties"]["risk_guidance"]
    assert guidance["maxItems"] <= 3  # period_overview hard_max=3


def test_transport_conversion_rule_digest_frozen() -> None:
    """감수 58차 §5: transport 변환 규칙 스냅샷 고정 — 이 digest가 바뀌면
    provider 전송 shape 변경 가능성이므로 providerRequestSchemaVersion
    상향+SHADOW_VALIDATING 강등+새 corpus 재검증 없이는 배포 금지."""
    import hashlib
    import json as _json

    from saju_api.services.gemini_token_adapter import (
        build_gemini_transport_schema,
    )

    reference = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "risk_guidance": {
                "type": "array", "minItems": 1, "maxItems": 2,
                "items": {"type": "object", "additionalProperties": False,
                          "properties": {
                              "guidance_ref": {"type": "string",
                                               "enum": ["rg1", "rg2"]},
                              "exposed_level": {"type": "string",
                                                "enum": ["warning"]}},
                          "required": ["guidance_ref", "exposed_level"]}},
        }, "required": ["risk_guidance"], "x_internal": "drop-me"}
    digest = hashlib.sha256(_json.dumps(
        build_gemini_transport_schema(reference), ensure_ascii=False,
        sort_keys=True).encode()).hexdigest()
    # 규칙 스냅샷(결정적 참조 입력에 대한 출력 digest) — 변환 규칙이
    # 하나라도 바뀌면 아래 값이 달라진다.
    expected = hashlib.sha256(_json.dumps({
        "type": "OBJECT",
        "properties": {
            "risk_guidance": {
                "type": "ARRAY", "minItems": 1, "maxItems": 2,
                "items": {"type": "OBJECT",
                          "properties": {
                              "guidance_ref": {"type": "STRING",
                                               "enum": ["rg1", "rg2"]},
                              "exposed_level": {"type": "STRING",
                                                "enum": ["warning"]}},
                          "required": ["guidance_ref", "exposed_level"]}},
        }, "required": ["risk_guidance"]}, ensure_ascii=False,
        sort_keys=True).encode()).hexdigest()
    assert digest == expected


def test_output_schema_max_items_is_final_episode_count() -> None:
    """감수 58차 §9: maxItems=min(질문 hard_max, **미래 필터 후 최종
    episode 수**) — hard_max=4여도 최종 2건이면 maxItems=2."""
    from saju_engines.risk_claim_audit import build_risk_output_schema

    llm = [{"guidanceRef": "rg1", "presentationLevel": "warning"},
           {"guidanceRef": "rg2", "presentationLevel": "watch"}]
    schema = build_risk_output_schema(llm, hard_max=4)
    assert schema["properties"]["risk_guidance"]["maxItems"] == 2


def _pipeline_env(monkeypatch, tmp_path):
    """감수 59차 pipeline fixture 공통 조립 — VALIDATED adapter + 최종
    payload/guidance context + wrapped block prompt."""
    import hashlib as _hashlib

    from saju_api.services import token_counter_registry as reg
    from saju_api.services.token_counter_registry import (
        ProviderRequest,
        TokenCounterAdapter,
        adapter_validation_policy_hash,
        register_adapter,
        set_validation_state,
    )
    from saju_engines.risk_exposure import (
        RiskPromptBlock,
        build_guidance_reference_context,
        wrap_risk_block,
    )
    from saju_engines.risk_presentation import (
        build_presentation,
        serialize_llm_payload,
    )
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

    monkeypatch.setattr(reg, "_SUSPENSION_FILE",
                        tmp_path / "suspensions.json")
    monkeypatch.setattr(reg, "_SUSPENSION_LOCK_FILE", tmp_path / "l.lock")
    monkeypatch.setattr(reg, "_SUSPENSION_LEDGER", tmp_path / "l.jsonl")
    monkeypatch.setattr(reg, "_EXPOSURE_DISABLED_MARKER",
                        tmp_path / "marker")
    adapter = TokenCounterAdapter(
        model_id="flow-model", mode="MODEL_TOKENIZER",
        counter=lambda s: max(1, len(s) // 4), provider_id="prov",
        counter_version="v1", validation_corpus_hash="corpus")
    register_adapter(adapter)
    set_validation_state("flow-model", "VALIDATED")
    entry = {"reviewed": True, "resolvedModelId": "flow-model",
             "providerId": "prov", "counterVersion": "v1",
             "providerRequestSchemaVersion": "1",
             "countMode": "MODEL_TOKENIZER",
             "validationPolicyHash": adapter_validation_policy_hash(),
             "validationCorpusHash": "corpus"}
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
    serialized = serialize_llm_payload(payload, 100_000)
    block = RiskPromptBlock(
        serialized_text=serialized,
        content_hash=_hashlib.sha256(
            serialized.encode()).hexdigest()[:16],
        compression_mode="FULL",
        exact_token_count=max(1, len(serialized) // 4))
    ctx = build_guidance_reference_context("req-flow-1", payload)
    baseline = ProviderRequest(system_messages=("sys",),
                               user_messages=("질문 본문",))
    from saju_engines.risk_exposure import (
        RISK_EXPOSURE_INSTRUCTION_BLOCK,
    )
    initial = ProviderRequest(
        system_messages=("sys",),
        user_messages=("질문 본문",
                       RISK_EXPOSURE_INSTRUCTION_BLOCK,
                       wrap_risk_block(block)))
    from saju_api.services.risk_llm_pipeline import (
        build_risk_execution_context,
    )
    exec_ctx = build_risk_execution_context(
        "req-flow-1", manifest_counters=[entry], guidance_context=ctx,
        baseline_request=baseline, resolved_model_id="flow-model")
    return {"adapter": adapter, "entry": entry, "payload": payload,
            "ctx": ctx, "baseline": baseline, "initial": initial,
            "exec": exec_ctx}


def _good_envelope(payload: dict) -> dict:
    eps = payload["llmRiskEpisodes"]
    return {"risk_guidance": [{
        "guidance_ref": e["guidanceRef"],
        "exposed_level": e.get("presentationLevel", "warning"),
        "text": "관련 조건을 미리 점검해 두면 좋은 시기입니다.",
    } for e in eps]}


def test_injected_flow_clean_draft_delivers(monkeypatch,
                                            tmp_path) -> None:
    """감수 59차 §14: 정상 초안 → INITIAL 1회·감사 통과 → renderer →
    최종 감사 통과 → DELIVER."""
    from saju_api.services.risk_llm_pipeline import run_injected_risk_flow

    env = _pipeline_env(monkeypatch, tmp_path)
    calls: list[str] = []

    def llm_call(request):
        calls.append("call")
        return {"answer": "조건을 점검해 두면 좋은 시기입니다.",
                "envelope": _good_envelope(env["payload"])}

    result = run_injected_risk_flow(
        initial_request=env["initial"], baseline_request=env["baseline"],
        execution_context=env["exec"],
        llm_episodes=env["payload"]["llmRiskEpisodes"],
        adapter=env["adapter"],
        final_token_limit=100_000, llm_call=llm_call,
        renderer=lambda s: s + "\n(정리된 답변)")
    assert result["outcome"] == "DELIVER_GENERATED"
    assert len(calls) == 1
    assert [a["kind"] for a in result["attempts"]] == ["INITIAL"]
    assert result["attempts"][0]["counted_tokens"] > 0


def test_injected_flow_revise_then_deliver(monkeypatch, tmp_path) -> None:
    """감수 59차 §10·§12: 초안 위반 → REVISION_1(별도 요청·재계수·최소
    입력 — 내부 episodeKey 미포함) → 통과 → DELIVER."""
    from saju_api.services.risk_llm_pipeline import run_injected_risk_flow

    env = _pipeline_env(monkeypatch, tmp_path)
    seen_requests = []

    def llm_call(request):
        seen_requests.append(request)
        if len(seen_requests) == 1:
            return {"answer": "반드시 소송이 발생한다.",
                    "envelope": {"risk_guidance": []}}  # 필수 warning 누락
        return {"answer": "조건을 점검해 두면 좋은 시기입니다.",
                "envelope": _good_envelope(env["payload"])}

    result = run_injected_risk_flow(
        initial_request=env["initial"], baseline_request=env["baseline"],
        execution_context=env["exec"],
        llm_episodes=env["payload"]["llmRiskEpisodes"],
        adapter=env["adapter"],
        final_token_limit=100_000, llm_call=llm_call,
        renderer=lambda s: s)
    assert result["outcome"] == "DELIVER_GENERATED"
    kinds = [a["kind"] for a in result["attempts"]]
    assert kinds == ["INITIAL", "REVISION_1"]
    # attempt별 독립 재계수(§10) — revision이 더 긴 요청이므로 count 증가.
    assert (result["attempts"][1]["counted_tokens"]
            > result["attempts"][0]["counted_tokens"])
    # REVISE 입력 최소화(§12): 내부 canonical episode key 미포함.
    revision_text = "\n".join(seen_requests[1].user_messages)
    for _, canonical_key in env["ctx"].guidance_ref_map:
        assert canonical_key not in revision_text
    assert "[재작성 요청]" in revision_text


def test_injected_flow_regenerate_without_risk(monkeypatch,
                                               tmp_path) -> None:
    """감수 59차 §10: REVISE도 위반 → REGENERATE_WITHOUT_RISK — baseline
    +suppressed guard만(canonical bytes 일치·risk 요소 잔재 0)."""
    from saju_api.services.risk_llm_pipeline import (
        build_regenerate_request,
        canonical_request_bytes,
        run_injected_risk_flow,
    )
    from saju_api.services.token_counter_registry import ProviderRequest
    from saju_engines.risk_exposure import (
        RISK_EXPOSURE_SUPPRESSED_GUARD,
    )

    env = _pipeline_env(monkeypatch, tmp_path)
    regen_requests = []

    def llm_call(request):
        joined = "\n".join(request.user_messages)
        if RISK_EXPOSURE_SUPPRESSED_GUARD in joined \
                and "BEGIN_RISK_BLOCK" not in joined:
            regen_requests.append(request)
            return {"answer": "일정을 점검해 두면 좋은 시기입니다.",
                    "envelope": None}
        return {"answer": "반드시 소송이 발생한다.",
                "envelope": {"risk_guidance": []}}

    result = run_injected_risk_flow(
        initial_request=env["initial"], baseline_request=env["baseline"],
        execution_context=env["exec"],
        llm_episodes=env["payload"]["llmRiskEpisodes"],
        adapter=env["adapter"],
        final_token_limit=100_000, llm_call=llm_call,
        renderer=lambda s: s)
    assert result["outcome"] == "DELIVER_GENERATED"
    kinds = [a["kind"] for a in result["attempts"]]
    assert kinds == ["INITIAL", "REVISION_1", "REGENERATE_WITHOUT_RISK"]
    # 완전 재조립 계약: baseline+guard와 canonical bytes 정확 일치.
    assert len(regen_requests) == 1
    expected = ProviderRequest(
        system_messages=env["baseline"].system_messages,
        user_messages=(*env["baseline"].user_messages,
                       RISK_EXPOSURE_SUPPRESSED_GUARD))
    assert (canonical_request_bytes(regen_requests[0])
            == canonical_request_bytes(expected)
            == canonical_request_bytes(
                build_regenerate_request(env["baseline"])))


def test_injected_flow_final_render_audit_blocks(monkeypatch,
                                                 tmp_path) -> None:
    """감수 59차 §14-7: 감사 통과 초안이라도 renderer 후 최종 문자열에
    내부 ref가 남으면 BLOCK+결정적 fallback(전달 경로 없음)."""
    from saju_api.services.risk_llm_pipeline import run_injected_risk_flow
    from saju_engines.risk_exposure import RISK_SAFE_FALLBACK_TEMPLATE

    env = _pipeline_env(monkeypatch, tmp_path)

    result = run_injected_risk_flow(
        initial_request=env["initial"], baseline_request=env["baseline"],
        execution_context=env["exec"],
        llm_episodes=env["payload"]["llmRiskEpisodes"],
        adapter=env["adapter"],
        final_token_limit=100_000,
        llm_call=lambda r: {"answer": "조건을 점검해 두면 좋습니다.",
                            "envelope": _good_envelope(env["payload"])},
        renderer=lambda s: s + "\n(내부 참조: rg1)")  # renderer가 누출
    # 생성물·결정적 fallback 모두 같은 renderer로 오염 → 전달 없음(BLOCK,
    # 감수 60차 §8 — 차단과 전달을 동시에 표현하지 않는다).
    assert result["outcome"] == "BLOCK"
    assert result["final_text"] == ""
    assert any("INTERNAL_GUIDANCE_REF_LEAKED" in i
               for i in result["final_audit_issues"])
    _ = RISK_SAFE_FALLBACK_TEMPLATE  # fallback 문구는 정책 상수 유지


def test_rerouting_decision_and_context_mismatch(monkeypatch,
                                                 tmp_path) -> None:
    """감수 59차 §4·§8·§11: 미감수 모델 rerouting=REBUILD_BYPASS, 감수
    모델=REEVALUATE_GATE. 다른 요청의 guidance context는 preflight에서
    GUIDANCE_CONTEXT_MISMATCH."""
    from saju_api.services.risk_llm_pipeline import (
        handle_rerouting,
        preflight_provider_attempt,
    )

    env = _pipeline_env(monkeypatch, tmp_path)
    assert handle_rerouting("flow-model", [env["entry"]]) == (
        "REEVALUATE_GATE")
    assert handle_rerouting("unreviewed-2.5", [env["entry"]]) == (
        "REBUILD_BYPASS")
    plan = preflight_provider_attempt(
        "INITIAL", env["initial"], resolved_model_id="flow-model",
        manifest_counters=[env["entry"]], adapter=env["adapter"],
        guidance_context=env["ctx"],
        request_context_id="req-OTHER",  # 타 요청 재사용 시도
        final_token_limit=100_000, expects_risk_block=True)
    assert "GUIDANCE_CONTEXT_MISMATCH" in plan.preflight_issues


def test_runtime_validated_is_derived_not_configured(monkeypatch,
                                                     tmp_path) -> None:
    """감수 59차 §3: VALIDATED=검증 결과 — artifact 불일치·manifest 불일치·
    suspension이면 절대 VALIDATED가 되지 않는다."""
    from saju_api.services import token_counter_registry as reg
    from saju_api.services.token_counter_registry import (
        TokenCounterAdapter,
        adapter_validation_policy_hash,
        derive_runtime_adapter_state,
        record_count_observation,
        register_adapter,
    )

    monkeypatch.setattr(reg, "_SUSPENSION_FILE", tmp_path / "s.json")
    monkeypatch.setattr(reg, "_SUSPENSION_LOCK_FILE", tmp_path / "s.lock")
    monkeypatch.setattr(reg, "_SUSPENSION_LEDGER", tmp_path / "s.jsonl")
    monkeypatch.setattr(reg, "_EXPOSURE_DISABLED_MARKER",
                        tmp_path / "m")
    adapter = TokenCounterAdapter(
        model_id="derive-model", mode="MODEL_TOKENIZER", counter=len,
        provider_id="prov", counter_version="v1",
        validation_corpus_hash="corpus")
    entry = {"reviewed": True, "resolvedModelId": "derive-model",
             "providerId": "prov", "counterVersion": "v1",
             "providerRequestSchemaVersion": "1",
             "countMode": "MODEL_TOKENIZER",
             "validationPolicyHash": adapter_validation_policy_hash(),
             "validationCorpusHash": "corpus"}
    assert derive_runtime_adapter_state(None, [entry], True) == (
        "UNREGISTERED")
    assert derive_runtime_adapter_state(adapter, [entry], True) == (
        "VALIDATED")
    assert derive_runtime_adapter_state(adapter, [entry], False) == (
        "SHADOW_VALIDATING")  # artifact 재해시 불일치=승격 불가
    assert derive_runtime_adapter_state(
        adapter, [{**entry, "reviewed": False}], True) == (
        "SHADOW_VALIDATING")
    register_adapter(adapter)
    record_count_observation("derive-model", counted=1, reported=2)
    assert derive_runtime_adapter_state(adapter, [entry], True) == (
        "SUSPENDED")


def test_revision_reroute_never_sends_risky_draft(monkeypatch,
                                                  tmp_path) -> None:
    """감수 60차 §3: INITIAL 후 라우팅이 미감수 모델로 바뀌면 위험 초안을
    포함한 revision을 어떤 모델에도 보내지 않고 REGENERATE로 직행."""
    from saju_api.services.risk_llm_pipeline import run_injected_risk_flow

    env = _pipeline_env(monkeypatch, tmp_path)
    models = iter(["flow-model", "unreviewed-2.5", "flow-model"])
    sent_requests = []

    def llm_call(request):
        sent_requests.append("\n".join(request.user_messages))
        if len(sent_requests) == 1:
            return {"answer": "반드시 소송이 발생한다.",
                    "envelope": {"risk_guidance": []}}
        return {"answer": "일정을 점검해 두면 좋은 시기입니다.",
                "envelope": None}

    result = run_injected_risk_flow(
        initial_request=env["initial"], baseline_request=env["baseline"],
        execution_context=env["exec"],
        llm_episodes=env["payload"]["llmRiskEpisodes"],
        adapter=env["adapter"], final_token_limit=100_000,
        llm_call=llm_call, renderer=lambda s: s,
        resolve_model=lambda: next(models))
    assert result["outcome"] == "DELIVER_GENERATED"
    skipped = [a for a in result["attempts"] if a.get("skipped")]
    assert skipped and skipped[0]["kind"] == "REVISION_1"
    assert skipped[0]["reason"] == "REROUTE_REBUILD_BYPASS"
    # 위험 초안이 포함된 두 번째 provider 전송이 없어야 한다 — 두 번째
    # 전송은 REGENERATE(baseline+guard, 초안·block 없음)뿐.
    assert len(sent_requests) == 2
    assert "반드시 소송이 발생한다" not in sent_requests[1]
    assert "BEGIN_RISK_BLOCK" not in sent_requests[1]


def test_request_shape_not_reviewed_blocks_attempt(monkeypatch,
                                                   tmp_path) -> None:
    """감수 60차 §5: attempt의 구조적 shape digest가 reviewed 집합에
    없으면 REQUEST_SHAPE_NOT_REVIEWED — 해당 attempt 실행 금지."""
    from saju_api.services.risk_llm_pipeline import (
        build_regenerate_request,
        request_shape_digest,
        run_injected_risk_flow,
    )

    env = _pipeline_env(monkeypatch, tmp_path)
    reviewed = frozenset({
        request_shape_digest("INITIAL", env["initial"]),
        request_shape_digest(
            "REGENERATE_WITHOUT_RISK",
            build_regenerate_request(env["baseline"])),
    })  # REVISION_1 shape은 의도적으로 미포함

    calls = []

    def llm_call(request):
        calls.append(request)
        if len(calls) == 1:
            return {"answer": "반드시 소송이 발생한다.",
                    "envelope": {"risk_guidance": []}}
        return {"answer": "일정을 점검해 두면 좋습니다.", "envelope": None}

    result = run_injected_risk_flow(
        initial_request=env["initial"], baseline_request=env["baseline"],
        execution_context=env["exec"],
        llm_episodes=env["payload"]["llmRiskEpisodes"],
        adapter=env["adapter"], final_token_limit=100_000,
        llm_call=llm_call, renderer=lambda s: s,
        reviewed_shape_digests=reviewed)
    assert result["outcome"] == "DELIVER_GENERATED"
    revision = [a for a in result["attempts"]
                if a["kind"] == "REVISION_1"][0]
    assert "REQUEST_SHAPE_NOT_REVIEWED" in revision["preflight_issues"]
    assert len(calls) == 2  # revision은 provider로 전송되지 않음


def test_execution_context_snapshot_isolated(monkeypatch,
                                             tmp_path) -> None:
    """감수 60차 §2: 실행 context는 요청 단위 불변 — 전달한 counters
    리스트를 이후에 바꿔도 snapshot이 유지되고, guidance context는 전
    과정 동일 객체(object identity)다."""
    from saju_api.services.risk_llm_pipeline import (
        build_risk_execution_context,
    )

    env = _pipeline_env(monkeypatch, tmp_path)
    counters = [env["entry"]]
    ctx = build_risk_execution_context(
        "req-x", manifest_counters=counters,
        guidance_context=env["ctx"], baseline_request=env["baseline"],
        resolved_model_id="flow-model")
    counters.clear()  # 외부 변이 — snapshot에 영향 없어야 함
    assert len(ctx.manifest_counters) == 1
    assert ctx.guidance_context is env["ctx"]  # 동일 객체 소비(§10)
    assert ctx.expose_policy_hash and ctx.claim_audit_policy_hash
    assert len(ctx.baseline_request_digest) == 64


def test_suspension_between_attempts_stops_risky_calls(monkeypatch,
                                                       tmp_path) -> None:
    """감수 60차 §6·§12: INITIAL 후 adapter가 SUSPENDED되면 REVISION·
    REGENERATE preflight가 최신 suspension을 감지 — 이후 위험 호출 없이
    safe fallback으로 종결(fallback도 최종 감사 통과 시 전달)."""
    from saju_api.services.risk_llm_pipeline import run_injected_risk_flow
    from saju_api.services.token_counter_registry import (
        record_count_observation,
    )

    env = _pipeline_env(monkeypatch, tmp_path)
    calls = []

    def llm_call(request):
        calls.append(request)
        # INITIAL 처리 중 undercount 관측 → 전역 SUSPENDED.
        record_count_observation("flow-model", counted=1, reported=2)
        return {"answer": "반드시 소송이 발생한다.",
                "envelope": {"risk_guidance": []}}

    result = run_injected_risk_flow(
        initial_request=env["initial"], baseline_request=env["baseline"],
        execution_context=env["exec"],
        llm_episodes=env["payload"]["llmRiskEpisodes"],
        adapter=env["adapter"], final_token_limit=100_000,
        llm_call=llm_call, renderer=lambda s: s)
    assert result["outcome"] == "DELIVER_SAFE_FALLBACK"
    assert len(calls) == 1  # suspension 후 어떤 provider 호출도 없음
    revision = [a for a in result["attempts"]
                if a["kind"] == "REVISION_1"][0]
    assert "TOKENIZER_UNAVAILABLE" in revision["preflight_issues"]
    from saju_api.services.token_counter_registry import (
        set_validation_state,
    )
    set_validation_state("flow-model", "SUSPENDED")


def test_cache_observation_blocks_identity(monkeypatch,
                                           tmp_path) -> None:
    """감수 60차 §7: cached_input>0 최초 관측 → CACHE_PATH_UNVALIDATED
    ledger 기록 + identity 전역 차단(별도 감수 전 재활성화 금지)."""
    from saju_api.services import token_counter_registry as reg
    from saju_api.services.token_counter_registry import (
        TokenCounterAdapter,
        adapter_validation_policy_hash,
        record_cache_observation,
        register_adapter,
        resolve_expose_counter,
        set_validation_state,
    )

    monkeypatch.setattr(reg, "_SUSPENSION_FILE", tmp_path / "s.json")
    monkeypatch.setattr(reg, "_SUSPENSION_LOCK_FILE", tmp_path / "s.lock")
    monkeypatch.setattr(reg, "_SUSPENSION_LEDGER", tmp_path / "s.jsonl")
    monkeypatch.setattr(reg, "_EXPOSURE_DISABLED_MARKER", tmp_path / "m")
    register_adapter(TokenCounterAdapter(
        model_id="cache-model", mode="MODEL_TOKENIZER", counter=len,
        provider_id="prov", counter_version="v1",
        validation_corpus_hash="corpus"))
    set_validation_state("cache-model", "VALIDATED")
    entry = {"reviewed": True, "resolvedModelId": "cache-model",
             "providerId": "prov", "counterVersion": "v1",
             "providerRequestSchemaVersion": "1",
             "countMode": "MODEL_TOKENIZER",
             "validationPolicyHash": adapter_validation_policy_hash(),
             "validationCorpusHash": "corpus"}
    assert resolve_expose_counter("cache-model", [entry]) is not None
    record_cache_observation("cache-model", cached_input=0)  # 무변화
    assert resolve_expose_counter("cache-model", [entry]) is not None
    record_cache_observation("cache-model", cached_input=17)
    assert resolve_expose_counter("cache-model", [entry]) is None
    ledger = (tmp_path / "s.jsonl").read_text(encoding="utf-8")
    assert "CACHE_PATH_UNVALIDATED" in ledger


def test_bootstrap_noop_outside_expose_modes() -> None:
    """감수 61차 §13: OFF/SHADOW에서 bootstrap=no-op(None) — 기존 경로
    byte 불변 계약 유지(등록·stamp 부작용 없음)."""
    from saju_api.services.risk_exposure_bootstrap import (
        bootstrap_risk_exposure,
    )

    assert risk_engine_config.RISK_ENGINE_MODE == "off"
    assert bootstrap_risk_exposure() is None


def test_bootstrap_stamps_derived_state_in_expose(monkeypatch) -> None:
    """감수 61차 §13-②: EXPOSE 모드 startup — adapter 등록 후 상태를
    검증 결과로 파생(artifact·manifest 일치 실환경 기준). 실물 corpus가
    reviewed=true이므로 suspension 없으면 VALIDATED, 저장소 상태에 따라
    SHADOW_VALIDATING/SUSPENDED — 어느 쪽이든 임의 대입이 아니다."""
    from saju_api.services.risk_exposure_bootstrap import (
        bootstrap_risk_exposure,
    )
    from saju_api.services.token_counter_registry import (
        ADAPTER_VALIDATION_STATES,
    )

    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE",
                        "expose_canary")
    state = bootstrap_risk_exposure()
    assert state in ADAPTER_VALIDATION_STATES
    from saju_api.services.token_counter_registry import (
        set_validation_state,
    )
    set_validation_state("gemini-3-flash-preview", "SHADOW_VALIDATING")


def test_runtime_inputs_fail_closed_defaults(monkeypatch) -> None:
    """감수 61차 §11: limit 미등록·adapter 미해소=게이트 BYPASS 입력 —
    reviewed shape 집합은 실물 artifact에서 7종 로드."""
    from saju_api.services.risk_exposure_bootstrap import (
        exposure_runtime_inputs,
        load_reviewed_shape_digests,
    )

    inputs = exposure_runtime_inputs("chat_single")
    # 실물 corpus 승격 후에도 runtime 상태는 startup stamp 전
    # SHADOW_VALIDATING이므로 counter는 해소되지 않는다(VALIDATED만).
    assert inputs["resolved_model_id"] == "gemini-3-flash-preview"
    assert inputs["context_limit"] >= 0
    assert inputs["response_reserve"] > 0
    shapes = load_reviewed_shape_digests("gemini-3-flash-preview")
    assert len(shapes) == 7  # 감수 61차 §5 — 이름 결속 7종
    assert load_reviewed_shape_digests("unknown-model") == frozenset()


def test_kill_switch_blocks_expose_end_to_end(monkeypatch) -> None:
    """통합 §13-⑩ kill switch: EXPOSE 전 조건 충족 상태에서도 kill
    switch=True면 즉시 BYPASS(prompt 불변·flow 미실행)."""
    from saju_api.services.risk_exposure_service import apply_risk_exposure

    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE",
                        "expose_canary")
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSE_CANARY_SUBJECT_IDS",
                        frozenset({"internal-tester-1"}))
    monkeypatch.setattr(risk_engine_config,
                        "RISK_DEPLOYMENT_TOPOLOGY",
                        "single_host_single_process")
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSURE_RUNTIME_ENABLED", True)
    monkeypatch.setattr(risk_engine_config, "RISK_EXPOSURE_KILL_SWITCH",
                        True)
    p, s, obs = apply_risk_exposure(
        "본문", None, subject_id="internal-tester-1",
        question_type="period_overview", temporal_scope="future")
    assert p == "본문" and s is None
    assert obs["disposition"] == "BYPASS"
    assert obs["reason"] == "KILL_SWITCH"


def test_rollback_to_off_restores_byte_identical(monkeypatch) -> None:
    """통합 §13-⑩ rollback: EXPOSE→off 전환만으로 chat 분기 자체가
    실행되지 않아 prompt·system이 byte-identical로 복귀."""
    from saju_api.services.risk_exposure_service import (
        exposure_mode_active,
    )

    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE",
                        "expose_canary")
    assert exposure_mode_active() is True
    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE", "off")
    assert exposure_mode_active() is False  # 분기 미실행=불변 복귀


def test_bootstrap_worker_mismatch_disables(monkeypatch) -> None:
    """감수 61차 §13 worker=1 실측: single_process 선언+worker>1 환경
    신호 → adapter 미등록(RISK_BOOTSTRAP_TOPOLOGY_MISMATCH — 전부
    BYPASS). baseline 서비스는 영향 없음."""
    from saju_api.services import risk_exposure_bootstrap as reb

    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE",
                        "expose_canary")
    monkeypatch.setattr(risk_engine_config, "RISK_DEPLOYMENT_TOPOLOGY",
                        "single_host_single_process")
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    assert reb.bootstrap_risk_exposure() is None
    assert reb.last_bootstrap_reason() == (
        "RISK_BOOTSTRAP_TOPOLOGY_MISMATCH")
    monkeypatch.setenv("WEB_CONCURRENCY", "abc")  # 해석 불가=검증 불가
    assert reb.bootstrap_risk_exposure() is None
    assert reb.last_bootstrap_reason() == (
        "RISK_BOOTSTRAP_TOPOLOGY_MISMATCH")


def test_undercount_discards_safe_response_before_delivery(
        monkeypatch, tmp_path) -> None:
    """통합 감수 §2 fixture-①: 내용이 안전한 INITIAL 응답이라도 provider
    보고 input이 counted를 초과(undercount)하면 **전달 전에 폐기** —
    identity 전역 SUSPENDED, 이후 위험 attempt 전부 차단 → 위험 없는
    종결(DELIVER_SAFE_FALLBACK)."""
    from saju_api.services.risk_llm_pipeline import run_injected_risk_flow
    from saju_api.services.token_counter_registry import (
        record_cache_observation,
        record_count_observation,
    )

    env = _pipeline_env(monkeypatch, tmp_path)
    calls = []

    def llm_call(request):
        calls.append(request)
        return {"answer": "조건을 점검해 두면 좋은 시기입니다.",
                "envelope": _good_envelope(env["payload"]),
                # 안전한 내용 + undercount(reported > counted) 보고.
                "provider_reported_input": 10_000_000,
                "cached_input": 0}

    def observer(kind, counted, reported, cached, digest):
        record_count_observation("flow-model", counted=counted,
                                 reported=reported, request_id_hash=digest)
        record_cache_observation("flow-model", cached)

    result = run_injected_risk_flow(
        initial_request=env["initial"], baseline_request=env["baseline"],
        execution_context=env["exec"],
        llm_episodes=env["payload"]["llmRiskEpisodes"],
        adapter=env["adapter"], final_token_limit=100_000_000,
        llm_call=llm_call, renderer=lambda s: s,
        drift_observer=observer)
    assert result["outcome"] == "DELIVER_SAFE_FALLBACK"
    assert len(calls) == 1  # suspension 후 어떤 위험 호출도 없음
    initial = result["attempts"][0]
    assert "TOKEN_UNDERCOUNT_DETECTED" in initial["audit_issues"]
    assert initial["audit_action"] == "DISCARDED"
    # 안전 문구는 위험 초안이 아님 — 초안 내용이 전달되지 않았다.
    assert "조건을 점검" not in result["final_text"]
    from saju_api.services.token_counter_registry import (
        set_validation_state,
    )
    set_validation_state("flow-model", "SUSPENDED")


def test_cache_hit_discards_response_before_delivery(
        monkeypatch, tmp_path) -> None:
    """통합 감수 §2 fixture-②: cached_input>0 관측 시 안전한 응답도
    전달 전 폐기 — CACHE_PATH_UNVALIDATED로 identity 차단 후 위험 없는
    종결."""
    from saju_api.services.risk_llm_pipeline import run_injected_risk_flow
    from saju_api.services.token_counter_registry import (
        record_cache_observation,
        record_count_observation,
    )

    env = _pipeline_env(monkeypatch, tmp_path)
    calls = []

    def llm_call(request):
        calls.append(request)
        return {"answer": "조건을 점검해 두면 좋은 시기입니다.",
                "envelope": _good_envelope(env["payload"]),
                "provider_reported_input": 1,  # undercount 아님
                "cached_input": 42}

    def observer(kind, counted, reported, cached, digest):
        record_count_observation("flow-model", counted=counted,
                                 reported=reported, request_id_hash=digest)
        record_cache_observation("flow-model", cached)

    result = run_injected_risk_flow(
        initial_request=env["initial"], baseline_request=env["baseline"],
        execution_context=env["exec"],
        llm_episodes=env["payload"]["llmRiskEpisodes"],
        adapter=env["adapter"], final_token_limit=100_000,
        llm_call=llm_call, renderer=lambda s: s,
        drift_observer=observer)
    assert result["outcome"] == "DELIVER_SAFE_FALLBACK"
    assert len(calls) == 1
    initial = result["attempts"][0]
    assert "CACHE_PATH_UNVALIDATED" in initial["audit_issues"]
    ledger = (tmp_path / "l.jsonl").read_text(encoding="utf-8")
    assert "CACHE_PATH_UNVALIDATED" in ledger
    from saju_api.services.token_counter_registry import (
        set_validation_state,
    )
    set_validation_state("flow-model", "SUSPENDED")


def test_suppressed_request_is_baseline_plus_guard_only(
        monkeypatch) -> None:
    """통합 감수 §3 fixture: 3상태 실제 요청 경계 — BYPASS=baseline
    bytes 동일, SUPPRESSED=canonical diff가 guard 하나뿐(risk schema·
    BEGIN_RISK_BLOCK 없음)."""
    from saju_api.services.risk_exposure_service import apply_risk_exposure
    from saju_engines.risk_exposure import (
        RISK_EXPOSURE_SUPPRESSED_GUARD,
    )

    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE",
                        "expose_canary")
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSE_CANARY_SUBJECT_IDS",
                        frozenset({"internal-tester-1"}))
    monkeypatch.setattr(risk_engine_config,
                        "RISK_DEPLOYMENT_TOPOLOGY",
                        "single_host_single_process")
    monkeypatch.setattr(risk_engine_config,
                        "RISK_EXPOSURE_RUNTIME_ENABLED", True)
    monkeypatch.setattr(risk_engine_config, "RISK_AUDIT_HMAC_KEY",
                        b"a" * 32)
    from saju_api.services import risk_exposure_service as _svc
    monkeypatch.setattr(_svc, "_load_manifest_snapshot",
                        lambda: {"reviewed": True, "hash_ok": True,
                                 "validated_token_counters": [],
                                 "schema_version": 10,
                                 "snapshot_hash": "mock"})
    # BYPASS(비허용 subject): prompt·system 완전 동일 + schema 키 없음.
    p, s, obs = apply_risk_exposure(
        "본문", "시스템", subject_id=None,
        question_type="period_overview", temporal_scope="future")
    assert (p, s) == ("본문", "시스템")
    assert obs["disposition"] == "BYPASS"
    assert "risk_output_schemas" not in obs
    # SUPPRESSED(자격 충족·episode 없음): diff=guard 한 블록뿐.
    p, s, obs = apply_risk_exposure(
        "본문", "시스템", subject_id="internal-tester-1",
        question_type="period_overview", temporal_scope="future",
        counter=lambda t: max(1, len(t) // 4),
        counter_model_id="m1", resolved_model_id="m1",
        model_context_limit=100_000, base_prompt_tokens=100,
        user_input_tokens=0, existing_context_tokens=0,
        response_reserve=1_000)
    assert obs["disposition"] == "SUPPRESSED"
    assert p == "본문\n" + RISK_EXPOSURE_SUPPRESSED_GUARD
    assert s == "시스템"  # system 불변
    assert "BEGIN_RISK_BLOCK" not in p
    assert "risk_output_schemas" not in obs  # 기존 output schema 유지


def test_env_activation_is_fail_closed(monkeypatch) -> None:
    """r4.1.0-canary 활성화 배선: env 미설정·오타·비정상 값=전부 잠금
    유지(off·False·dev키 → AUDIT_HMAC_KEY_INVALID) — env 오염으로 켜지는
    경로 없음."""
    import importlib

    from saju_engines import risk_engine_config as cfg

    monkeypatch.delenv("RISK_ENGINE_MODE", raising=False)
    monkeypatch.delenv("RISK_EXPOSURE_RUNTIME_ENABLED", raising=False)
    monkeypatch.delenv("RISK_AUDIT_HMAC_KEY_B64", raising=False)
    monkeypatch.delenv("RISK_EXPOSE_CANARY_SUBJECT_IDS", raising=False)
    mod = importlib.reload(cfg)
    assert mod.RISK_ENGINE_MODE == "off"
    assert mod.RISK_EXPOSURE_RUNTIME_ENABLED is False
    assert mod.RISK_AUDIT_HMAC_KEY == b"dev-only-rotate-before-canary"
    assert mod.RISK_EXPOSE_CANARY_SUBJECT_IDS == frozenset()
    # 오타·비정상 값=기본값(fail-closed).
    monkeypatch.setenv("RISK_ENGINE_MODE", "expose!!")
    monkeypatch.setenv("RISK_EXPOSURE_RUNTIME_ENABLED", "yes")
    monkeypatch.setenv("RISK_AUDIT_HMAC_KEY_B64", "not-base64!!")
    mod = importlib.reload(cfg)
    assert mod.RISK_ENGINE_MODE == "off"
    assert mod.RISK_EXPOSURE_RUNTIME_ENABLED is False
    assert mod.RISK_AUDIT_HMAC_KEY == b"dev-only-rotate-before-canary"
    # 짧은 키(<32B)=기본키 유지(운영 키 자격 없음).
    import base64
    monkeypatch.setenv("RISK_AUDIT_HMAC_KEY_B64",
                       base64.b64encode(b"short").decode())
    mod = importlib.reload(cfg)
    assert mod.RISK_AUDIT_HMAC_KEY == b"dev-only-rotate-before-canary"
    # 정상 활성화 값은 반영된다(운영 preflight 후에만 설정).
    monkeypatch.setenv("RISK_ENGINE_MODE", "expose_canary")
    monkeypatch.setenv("RISK_EXPOSURE_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("RISK_AUDIT_HMAC_KEY_B64",
                       base64.b64encode(b"k" * 32).decode())
    monkeypatch.setenv("RISK_EXPOSE_CANARY_SUBJECT_IDS", "tester-1, t2")
    mod = importlib.reload(cfg)
    assert mod.RISK_ENGINE_MODE == "expose_canary"
    assert mod.RISK_EXPOSURE_RUNTIME_ENABLED is True
    assert mod.RISK_AUDIT_HMAC_KEY == b"k" * 32
    assert mod.RISK_EXPOSE_CANARY_SUBJECT_IDS == {"tester-1", "t2"}
    # 정리: env 제거 후 원상 복구(다른 테스트 오염 방지).
    monkeypatch.delenv("RISK_ENGINE_MODE")
    monkeypatch.delenv("RISK_EXPOSURE_RUNTIME_ENABLED")
    monkeypatch.delenv("RISK_AUDIT_HMAC_KEY_B64")
    monkeypatch.delenv("RISK_EXPOSE_CANARY_SUBJECT_IDS")
    importlib.reload(cfg)


def test_shape_digest_invariant_to_dynamic_schema_values() -> None:
    """P1 교정(테마사주 배선 차): shape digest는 schema의 요청별 동적
    값(guidance_ref enum·maxItems)에 불변 — 구조(필드·타입) 변화에만
    반응한다. 실서비스 INJECTED가 corpus와 대조 가능해지는 근거."""
    import json as _json

    from saju_api.services.risk_llm_pipeline import request_shape_digest
    from saju_api.services.token_counter_registry import ProviderRequest

    def schema(refs, max_items):
        return _json.dumps({
            "type": "OBJECT", "required": ["main_answer", "risk_guidance"],
            "properties": {
                "main_answer": {"type": "STRING"},
                "risk_guidance": {
                    "type": "ARRAY", "maxItems": max_items,
                    "items": {"type": "OBJECT", "properties": {
                        "guidance_ref": {"type": "STRING", "enum": refs},
                    }}}}}, ensure_ascii=False)

    req_a = ProviderRequest(system_messages=("s",), user_messages=("u",),
                            output_schema=schema(["rg1"], 1))
    req_b = ProviderRequest(system_messages=("s",), user_messages=("u",),
                            output_schema=schema(["rg1", "rg2", "rg3"], 3))
    assert (request_shape_digest("INITIAL", req_a)
            == request_shape_digest("INITIAL", req_b))
    # 구조 자체가 바뀌면(필드 추가) digest 상이 — 감수 의도 보존.
    extra = _json.loads(schema(["rg1"], 1))
    extra["properties"]["unreviewed_field"] = {"type": "STRING"}
    req_c = ProviderRequest(
        system_messages=("s",), user_messages=("u",),
        output_schema=_json.dumps(extra, ensure_ascii=False))
    assert (request_shape_digest("INITIAL", req_a)
            != request_shape_digest("INITIAL", req_c))


def test_report_risk_section_off_mode_is_noop() -> None:
    """테마사주 배선: OFF 모드에서 C-06 헬퍼는 (None, 원본 그대로) —
    기존 리포트 경로 byte 불변."""
    from saju_api.services.report_service import (
        _RISK_EXPOSED_SECTION_ID,
        _try_risk_exposed_section,
    )

    assert _RISK_EXPOSED_SECTION_ID == "C-06"
    assert risk_engine_config.RISK_ENGINE_MODE == "off"
    # OFF면 data/spec 접근 전에 즉시 반환하므로 None 전달이 안전.
    text, prompt = _try_risk_exposed_section(
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        "원본 프롬프트", "시스템", "report_full_section",
        subject_id="s1")
    assert text is None
    assert prompt == "원본 프롬프트"


def test_service_initial_request_shape_in_reviewed_corpus() -> None:
    """실서비스 정합(P1 교정 검증): 채팅/리포트가 실제로 조립하는 INITIAL
    INJECTED 요청(instruction+wrapped block+transport schema)의 구조적
    digest가 reviewed corpus shape 집합에 존재해야 한다."""
    import hashlib as _hashlib
    import json as _json

    from saju_api.services.gemini_token_adapter import (
        build_gemini_transport_schema,
    )
    from saju_api.services.risk_exposure_bootstrap import (
        load_reviewed_shape_digests,
    )
    from saju_api.services.risk_llm_pipeline import request_shape_digest
    from saju_api.services.token_counter_registry import ProviderRequest
    from saju_engines.risk_claim_audit import build_risk_output_schema
    from saju_engines.risk_exposure import (
        RISK_EXPOSURE_INSTRUCTION_BLOCK,
        RiskPromptBlock,
        wrap_risk_block,
    )

    llm = [{"guidanceRef": "rg1", "presentationLevel": "warning"}]
    transport = build_gemini_transport_schema(
        build_risk_output_schema(llm, hard_max=3))
    serialized = '{"riskEpisodes": []}'
    block = RiskPromptBlock(
        serialized_text=serialized,
        content_hash=_hashlib.sha256(
            serialized.encode()).hexdigest()[:16],
        compression_mode="FULL", exact_token_count=5)
    initial = ProviderRequest(
        system_messages=("sys",),
        user_messages=("질문 본문\n" + RISK_EXPOSURE_INSTRUCTION_BLOCK
                       + "\n" + wrap_risk_block(block),),
        output_schema=_json.dumps(transport, ensure_ascii=False,
                                  sort_keys=True))
    digest = request_shape_digest("INITIAL", initial)
    reviewed = load_reviewed_shape_digests("gemini-3-flash-preview")
    assert digest in reviewed, "실서비스 INITIAL shape이 corpus에 없음"
