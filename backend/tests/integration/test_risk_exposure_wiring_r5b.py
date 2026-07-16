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


def test_expose_canary_appends_suppressed_guard_only(monkeypatch) -> None:
    """EXPOSE_CANARY(현 단계 — reviewed:false·adapter 부재): suppressed
    guard만 부착되고 위험 episode 정보는 어떤 형태로도 주입되지 않는다."""
    off_p, _ = _prompt("off", monkeypatch)
    can_p, _ = _prompt("expose_canary", monkeypatch)
    assert can_p.endswith("\n" + RISK_EXPOSURE_SUPPRESSED_GUARD)
    assert can_p[: -len("\n" + RISK_EXPOSURE_SUPPRESSED_GUARD)] == off_p
    assert RISK_EXPOSURE_INSTRUCTION_BLOCK not in can_p
    # 위험 payload 미주입(guard 문구의 'riskEpisodes' 언급과 구분 —
    # JSON 직렬화 키·필드가 존재하지 않음을 검사).
    assert '"riskEpisodes"' not in can_p
    assert "presentationLevel" not in can_p


def test_gate_observability_reports_fail_closed(monkeypatch) -> None:
    """현 단계 게이트 사유: 질문 매핑 미확정(DENY)·pipeline 미감수·adapter
    부재가 all reasons에 잡히고 primary는 고정 순서를 따른다."""
    from saju_api.services.risk_exposure_service import apply_risk_exposure

    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE",
                        "expose_canary")
    _p, _s, obs = apply_risk_exposure("본문", None, subject_id=None)
    assert obs["injected"] is False
    reasons = set(obs["all_reasons"])
    assert {"CANARY_NOT_ALLOWLISTED", "QUESTION_TYPE_NOT_ALLOWED",
            "EXPOSE_PIPELINE_NOT_REVIEWED",
            "TOKENIZER_UNAVAILABLE"} <= reasons
    assert obs["reason"] == "CANARY_NOT_ALLOWLISTED"  # 순서 최앞


def test_kill_switch_blocks_regardless_of_mode(monkeypatch) -> None:
    """kill switch=게이트 최앞 — EXPOSE 모드여도 비주입 primary."""
    from saju_api.services.risk_exposure_service import apply_risk_exposure

    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE", "expose")
    monkeypatch.setattr(risk_engine_config, "RISK_EXPOSURE_KILL_SWITCH",
                        True)
    _p, _s, obs = apply_risk_exposure("본문", None)
    assert obs["reason"] == "KILL_SWITCH"


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
    )

    text = '{"riskEpisodes": []}'
    block = RiskPromptBlock(
        serialized_text=text, compression_mode="P0_COMPACT",
        exact_token_count=10,
        content_hash=hashlib.sha256(text.encode()).hexdigest()[:16])
    assert verify_risk_block_integrity(f"머리\n{text}\n꼬리", block)
    assert not verify_risk_block_integrity("머리\n변형된 블록\n꼬리", block)
    tampered = RiskPromptBlock(
        serialized_text=text, compression_mode="P0_COMPACT",
        exact_token_count=10, content_hash="0" * 16)
    assert not verify_risk_block_integrity(f"머리\n{text}\n꼬리", tampered)


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
