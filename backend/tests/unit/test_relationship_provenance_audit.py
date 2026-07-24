"""RiskCandidate live provenance 무결성 회귀 — P1-6 (RELATIONSHIP_EVENT_SYSTEM §5).

1차 방어선(rebuild_risk_candidate — flag 단조 보존) + 2차 fail-safe(namespace
필터)의 독립 검증. 하드 게이트: live 관계 컨텍스트 유래 REL 후보는 P5 전
LLM 노출 0(REL_LIVE_CONTEXT_EXPOSE_ENABLED=False).

- 변환별 단위: rebuild_risk_candidate가 model_copy 변환에서 True→False 강등을
  차단하고 흡수원 provenance를 OR 승계한다.
- 정적 감사: 모든 RiskCandidate 재구성이 helper 경유(감사 스크립트 clean).
- e2e: suppress_by_specificity 흡수에서 대표·흡수 후보 모두 provenance 보존.
- fail-safe 2종 각각 파괴 + 둘 다 파괴: 각 층이 단독으로 차단하며(load-bearing),
  둘 다 유실되면 누출된다(invariant violation — 두 층 모두 필요함을 증명).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from saju_api.services.relationship_shadow import (
    _LIVE_TARGET_PREFIXES,
    strip_live_relationship_candidates,
)
from saju_engines.risk_engine import (
    _apply_specificity_suppression,
    is_exposable,
    merge_live_relationship_provenance,
    rebuild_risk_candidate,
)
from saju_shared_types.risk_engine import (
    EligibilityStatus,
    EvidenceRole,
    RiskCandidate,
    RiskDomain,
    RiskEvidence,
    RiskKind,
)


def _load_audit():
    """감사 스크립트를 파일 경로로 로드(scripts는 설치 패키지가 아님)."""
    path = (Path(__file__).resolve().parents[1].parent / "scripts" / "audits"
            / "relationship_provenance" / "audit_risk_candidate_rebuilds.py")
    spec = importlib.util.spec_from_file_location("_prov_audit", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass 주석 해소를 위해 등록 필요
    spec.loader.exec_module(mod)
    return mod


def _cand(risk_id: str = "REL_TEST", *, live: bool = False,
          target_id: str | None = None) -> RiskCandidate:
    return RiskCandidate(
        risk_id=risk_id, domain=RiskDomain.RELATIONSHIP, kind=RiskKind.PRESSURE,
        period_key="2027", live_relationship_context_derived=live,
        relationship_target_id=target_id)


def _absorbing_cand(risk_id: str, rank: int, *, live: bool) -> RiskCandidate:
    """흡수 성립 조건을 갖춘 관계 후보(같은 상대·같은 trigger 원자·활성)."""
    atom = "relation:CHUNG:day:branch:partner"
    return RiskCandidate(
        risk_id=risk_id, domain=RiskDomain.RELATIONSHIP, kind=RiskKind.PRESSURE,
        period_key="2027", risk_family="rel", relationship_target_id="relstate-1",
        specificity_rank=rank,
        evidence=[RiskEvidence(
            evidence_id=f"2027|{atom}", code="SYN_T1", period_key="2027",
            layer="sewoon", source=atom, strength=0.5, role=EvidenceRole.TRIGGER,
            source_group="event_shape", target_domain=RiskDomain.RELATIONSHIP)],
        eligibility_status=EligibilityStatus.ELIGIBLE,
        relationship_alignment="matched", relationship_role="current_partner",
        live_relationship_context_derived=live)


# ── 변환별 단위: rebuild helper 단조 보존 ────────────────────────────────────
def test_rebuild_preserves_live_flag_through_copy():
    """update가 flag를 언급 안 하면 base의 True를 승계한다."""
    base = _cand(live=True)
    out = rebuild_risk_candidate(base, update={"absorbed_role": "impact_amplifier"})
    assert out.live_relationship_context_derived is True
    assert out.absorbed_role == "impact_amplifier"


def test_rebuild_cannot_downgrade_true_to_false():
    """update가 flag=False를 줘도 base가 True면 True 유지(강등 불가)."""
    base = _cand(live=True)
    out = rebuild_risk_candidate(
        base, update={"live_relationship_context_derived": False})
    assert out.live_relationship_context_derived is True


def test_rebuild_or_from_provenance_sources():
    """흡수원(source)이 live면 base가 False여도 True로 승격(OR)."""
    base = _cand(live=False)
    src = _cand("REL_SRC", live=True)
    out = rebuild_risk_candidate(base, src, update={"absorbed_role": "x"})
    assert out.live_relationship_context_derived is True


def test_rebuild_stays_false_when_no_source_live():
    """base·source 전부 False면 False 유지(허위 양성 없음)."""
    base = _cand(live=False)
    src = _cand("REL_SRC", live=False)
    out = rebuild_risk_candidate(base, src)
    assert out.live_relationship_context_derived is False


def test_merge_provenance_or_semantics():
    assert merge_live_relationship_provenance(False, False) is False
    assert merge_live_relationship_provenance(False, True) is True


# ── 정적 감사: helper 우회 site 0 ────────────────────────────────────────────
def test_provenance_audit_clean():
    """모든 RiskCandidate 재구성이 rebuild helper 경유·승인(신규 우회 유입 차단)."""
    findings = _load_audit().audit_risk_candidate_rebuilds()
    assert findings == [], (
        "미승인 RiskCandidate 재구성: "
        + "; ".join(f"{f.path}:{f.line_no}" for f in findings))


# ── e2e: 흡수 경로 provenance 보존(양방향) ───────────────────────────────────
def test_suppression_preserves_provenance_e2e():
    """실 흡수 경로(_apply_specificity_suppression) 양방향 provenance 보존.

    ①흡수된 live 후보의 flag는 유지(True→False 강등 없음, 359 rebuild)
    ②live 후보를 흡수한 대표는 False→True로 승격(365 rebuild — OR 전파)
    ③strip이 두 후보 모두 차단(하드 게이트).
    """
    primary = _absorbing_cand("REL_CONFLICT", rank=2, live=False)   # 대표(원래 non-live)
    absorbed = _absorbing_cand("REL_DISTANCE", rank=1, live=True)   # 흡수될 live 후보
    assert is_exposable(primary) and is_exposable(absorbed)         # 흡수 전제
    out = _apply_specificity_suppression([primary, absorbed])
    by_id = {c.risk_id: c for c in out}
    # ② 대표가 흡수로 live 승격.
    assert by_id["REL_CONFLICT"].live_relationship_context_derived is True
    # ① 흡수된 후보 flag 유지 + 흡수 표식.
    assert by_id["REL_DISTANCE"].live_relationship_context_derived is True
    assert by_id["REL_DISTANCE"].suppressed_by_specificity == "REL_CONFLICT"
    # ③ strip은 live 유래 후보를 전부 제거.
    kept, removed = strip_live_relationship_candidates(list(out))
    assert removed == 2 and kept == []


# ── fail-safe 2종 각각 파괴 + 둘 다 파괴 ─────────────────────────────────────
def test_layer1_only_flag_blocks():
    """2차(namespace) 유실 — flag만으로 차단(1차 방어선 단독 유효)."""
    c = _cand(live=True, target_id="opaque-not-namespaced")  # namespace 없음
    assert not any(str(c.relationship_target_id).startswith(p)
                   for p in _LIVE_TARGET_PREFIXES)
    kept, removed = strip_live_relationship_candidates([c])
    assert removed == 1 and kept == []


def test_layer2_only_namespace_blocks():
    """1차(flag) 유실 — namespace만으로 차단(2차 fail-safe 단독 유효)."""
    c = _cand(live=False, target_id="relstate-9")  # flag 없음, namespace 있음
    kept, removed = strip_live_relationship_candidates([c])
    assert removed == 1 and kept == []


def test_both_layers_lost_leaks():
    """두 층 모두 유실 = 누출(invariant violation) — 각 층이 load-bearing임을 증명.

    이 테스트가 통과한다는 것은 '어느 한 층이라도 살아 있으면 차단'이 필수임을
    문서화한다(둘 중 하나라도 남기면 위 두 테스트가 지키는 차단이 성립).
    """
    c = _cand(live=False, target_id="opaque-not-namespaced")
    kept, removed = strip_live_relationship_candidates([c])
    assert removed == 0 and kept == [c]   # 두 층 다 없으면 통과(누출) — 방어선 부재
