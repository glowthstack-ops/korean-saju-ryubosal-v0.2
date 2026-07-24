"""관계 위험 dev beta 노출(슬라이스 3) 회귀 — dev 우회 플래그·live 선택·도메인 밴드·가드.

production 위험 노출 파이프라인(RISK_ENGINE_MODE=expose·manifest·HMAC)은 건드리지 않는
별도 dev 경로다. flag off면 무주입(byte-identical), flag on이면 live 관계 유래 위험 후보만
도메인·밴드 수준으로 노출한다. 구체 사건·확률·상대는 노출하지 않고 VULNERABILITY는 제외한다.
"""

from __future__ import annotations

from types import SimpleNamespace

from saju_api.services import chat_service, relationship_shadow, report_service
from saju_shared_types.risk_engine import RiskCandidate, RiskDomain, RiskKind


def _cand(risk_id, domain, kind, *, live=True, tid=None):
    return RiskCandidate(
        risk_id=risk_id, domain=domain, kind=kind, period_key="2027",
        live_relationship_context_derived=live,
        relationship_target_id=tid,
    )


def test_select_live_relationship_risk_candidates_only_live():
    """live-derived(provenance 또는 target 네임스페이스)만 골라낸다."""
    live = _cand("R_A", RiskDomain.RELATIONSHIP, RiskKind.PRESSURE, live=True)
    ns = _cand("R_B", RiskDomain.FINANCE, RiskKind.INCIDENT_RISK,
               live=False, tid="relstate-2")   # namespace fail-safe
    other = _cand("R_C", RiskDomain.HEALTH_SAFETY, RiskKind.PRESSURE,
                  live=False, tid="subject-1")
    got = relationship_shadow.select_live_relationship_risk_candidates(
        [live, ns, other])
    assert {c.risk_id for c in got} == {"R_A", "R_B"}


def test_risk_beta_block_domain_band_only_and_dedup():
    """도메인·밴드만·(도메인,밴드) dedup·VULNERABILITY 제외·cap 4."""
    cands = [
        _cand("R1", RiskDomain.RELATIONSHIP, RiskKind.PRESSURE),
        _cand("R2", RiskDomain.RELATIONSHIP, RiskKind.PRESSURE),   # dedup
        _cand("R3", RiskDomain.FINANCE, RiskKind.INCIDENT_RISK),
        _cand("R4", RiskDomain.HEALTH_SAFETY, RiskKind.VULNERABILITY),  # 제외
    ]
    block = chat_service._relationship_risk_beta_block(cands)
    assert block is not None
    assert "[관계 주의 신호(beta)" in block
    assert "- 관계 영역: 주의 신호" in block
    assert "- 재물 영역: 사건 가능 신호" in block
    assert "건강·안전" not in block          # VULNERABILITY 비노출
    assert block.count("- ") == 2            # dedup 반영
    # 확률·구체 사건·상대 미노출.
    assert "%" not in block


def test_risk_beta_block_empty_returns_none():
    assert chat_service._relationship_risk_beta_block([]) is None
    # 적격 후보가 VULNERABILITY뿐이면 None.
    only_vuln = [_cand("V", RiskDomain.RELATIONSHIP, RiskKind.VULNERABILITY)]
    assert chat_service._relationship_risk_beta_block(only_vuln) is None


def test_risk_beta_directive_guards():
    """가드 지시문 — 미검증·확정 아님·단정 금지·불안 조장 금지·beta 라벨."""
    d = chat_service._RELATIONSHIP_RISK_BETA_DIRECTIVE
    assert "미검증" in d
    assert "확정이 절대 아니다" in d
    assert "단정" in d and "불안 조장" in d
    assert "beta" in d


def test_risk_report_block_direct():
    """리포트용 블록 — risk_shadow에서 live 후보만·도메인 밴드·가드 지시문 포함."""
    data = SimpleNamespace(risk_shadow=(
        _cand("R1", RiskDomain.RELATIONSHIP, RiskKind.INCIDENT_RISK),
        _cand("R2", RiskDomain.CAREER, RiskKind.PRESSURE, live=False, tid="x"),  # 비 live
    ))
    lines = report_service._relationship_risk_beta_report_block(data)
    assert lines
    joined = "\n".join(lines)
    assert "[관계 주의 신호(beta)" in joined
    assert "- 관계 영역: 사건 가능 신호" in joined
    assert "일·직장" not in joined            # 비 live 후보 제외
    assert "미검증" in joined                 # 가드 지시문


def test_risk_report_block_empty_no_live():
    data = SimpleNamespace(risk_shadow=(
        _cand("R", RiskDomain.FINANCE, RiskKind.PRESSURE, live=False, tid="subj-1"),
    ))
    assert report_service._relationship_risk_beta_report_block(data) == []


def test_risk_flag_default_off():
    """기본(env 미설정) off — production 위험 게이트 무변경(REL_LIVE 하드게이트 유지)."""
    import os
    if not os.getenv("SAJU_RELATIONSHIP_RISK_BETA_EXPOSE"):
        assert relationship_shadow.RELATIONSHIP_RISK_BETA_EXPOSE is False
    # dev 우회는 P5 하드 게이트를 건드리지 않는다.
    assert relationship_shadow.REL_LIVE_CONTEXT_EXPOSE_ENABLED is False
