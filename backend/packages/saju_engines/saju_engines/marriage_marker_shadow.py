"""결혼 marker shadow 감지 — Detection ≠ Interpretation ≠ Exposure permission (CDS-P1d).

MARRIAGE_TIMING_ENHANCEMENT.md §1의 commitment/formalization marker 후보를 **감지만**
한다. 3층 분리(2026-08-21 데굴님 확정):
  - Detection(이 모듈): marker 성립 여부·근거를 shadow 데이터로 계산한다.
  - Interpretation: derive_marriage_stage/MarriageOutputGuard — **변경 없음**.
  - Exposure permission: commitment/formalization claim은 MT 전환 승인까지 계속 False.

즉 이 모듈의 결과는 사용자 출력·LLM 입력에 절대 연결하지 않는다 — 로그로만 적재해
MT 전환 승인 판단의 실측 데이터를 모은다. 문서에 정의된 marker 후보만 구현하며,
현 데이터로 판정 불가한 후보는 unevaluated에 명시한다(빈칸을 추론으로 메우지 않는다).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from saju_shared_types.llm_input import LlmEventCandidate

# 문서 §1 marker 후보 중 이번 구현 범위 밖(입력 데이터 부재) — coverage 명시.
_UNEVALUATED = (
    "commitment:관계창(대운·세운)+월운 트리거 confluence — 후보별 층위 provenance 미수집",
    "formalization:택일·일운 안정 보강 — 택일 경로 미배선",
)

# 12운성 관대·건록 reason code(twelve_stage_modifier가 부여) — 제도·사회 승인 신호.
_FORMAL_STAGE_CODES = ("stage:GWANDAE", "stage:GEONROK")
# 문서성 사건 키(관성/인성/문서 결합 판정용).
_DOCUMENT_KEYS = ("contract_document",)
_MARRIAGE_KEYS = ("marriage_signal", "new_relationship", "relationship_change")
# 장기 관계 상태(문서 §1 c4 — context=dating/engaged 상당).
_COMMITTED_STATUSES = ("dating", "engaged", "연애", "약혼")


class MarriageMarkerShadow(BaseModel):
    """marker shadow 결과 — 로그 전용(사용자 출력·LLM 입력 연결 금지)."""

    commitment_marker: bool = False
    formalization_marker: bool = False
    reasons: list[str] = Field(default_factory=list)
    unevaluated: list[str] = Field(default_factory=list)


def detect_marriage_marker_shadow(
    cands: list[LlmEventCandidate], relationship_status: str = ""
) -> MarriageMarkerShadow:
    """후보 목록에서 marker 후보 성립을 감지한다(문서 §1 정의 한정, 판정·점수 불변).

    Args:
        cands: 이번 턴 LLM 입력 후보(evidence_path 포함).
        relationship_status: 프로필 관계 상태(user_explicit — 없으면 빈 문자열).

    Returns:
        MarriageMarkerShadow — 성립 근거와 미평가 목록을 함께 담는다.
    """
    result = MarriageMarkerShadow(unevaluated=list(_UNEVALUATED))
    mt_cands = [
        c for c in cands
        if str(c.event_key) in _MARRIAGE_KEYS
        and any(code.startswith(("MT1", "MT2", "MT3")) for code in c.evidence_path)
    ]
    if not mt_cands:
        return result
    mt_periods = {c.period for c in mt_cands}
    doc_periods = {c.period for c in cands if str(c.event_key) in _DOCUMENT_KEYS}
    relocation_periods = {c.period for c in cands if str(c.event_key) == "relocation"}

    # ── commitment marker 후보 ──────────────────────────────────────────────
    # c1: 배우자성 직접 투출+배우자궁 합/회귀 = MT2 배우자성 회귀 코드.
    if any(
        code.startswith("MT2") for c in mt_cands for code in c.evidence_path
    ):
        result.commitment_marker = True
        result.reasons.append("commitment:MT2 배우자성 회귀")
    # c3: 관성/인성/문서성 신호가 관계 도메인과 결합(같은 기간 문서 사건 동시 발동).
    if mt_periods & doc_periods:
        result.commitment_marker = True
        result.reasons.append("commitment:문서성 사건 동기간 결합")
    # c4: 장기 관계 상태 + MT1·MT2·MT3 동시(strong confluence).
    prefixes = {
        code[:3] for c in mt_cands for code in c.evidence_path
        if code.startswith(("MT1", "MT2", "MT3"))
    }
    if (
        any(s in (relationship_status or "") for s in _COMMITTED_STATUSES)
        and prefixes >= {"MT1", "MT2", "MT3"}
    ):
        result.commitment_marker = True
        result.reasons.append("commitment:장기 관계+MT1·2·3 confluence")

    # ── formalization marker 후보 ───────────────────────────────────────────
    # f1: 인성/문서/계약 신호 결합 — commitment c3와 같은 관측(문서 §1이 양쪽에 둠).
    if mt_periods & doc_periods:
        result.formalization_marker = True
        result.reasons.append("formalization:문서·계약 신호 결합")
    # f2: 관성/제도 승인 신호 — 12운성 관대·건록이 관계 후보에 붙음.
    if any(
        code in _FORMAL_STAGE_CODES for c in mt_cands for code in c.evidence_path
    ):
        result.formalization_marker = True
        result.reasons.append("formalization:12운성 관대·건록")
    # f3: 주거·이사 신호와 결혼 도메인 동시 발동.
    if mt_periods & relocation_periods:
        result.formalization_marker = True
        result.reasons.append("formalization:이사·주거 동시 발동")
    return result
