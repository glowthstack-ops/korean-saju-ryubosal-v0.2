"""위험 노출 계층 R3 — presentation level·claim payload·token guard
(doc/v2_2/RISK_DICTIONARY_REVIEW.md §26 manifest, 감수 41차 착수 — shadow 전용).

핵심 원칙(데굴님): 위험 수준은 점수를 다시 계산하는 계층이 아니라 **이미
감수된 episode를 현실 확인 수준과 근거 독립성에 맞는 문장 강도로 변환하는
계층**이다. 불변식:

- R3는 R1 점수·R2 선택 집합(선택 id·대표·budget 누락 기록)을 절대 변경하지
  않는다 — 입력 불변(순수 함수), episode 추가·삭제·재선택 금지.
- numeric band(대표 raw의 잠정 구간)와 presentation level(정책 게이트 적용
  표현 단계)은 분리 — level이 점수·선별에 역영향 금지.
- critical은 '독립 2계층'이 아니라 **독립 canonical cause ≥ 2**: 같은 cause의
  대운·세운 반복=원인 1개(layer corroboration은 confidence 소관).
- warning-first는 R2 선택 집합 안의 stable sort(bucket 내 R2 순서 유지) —
  경고 0건이어도 억지 경고 금지, '특별한 위험 없음' 단정도 금지(R3 표현 계약).
- SHADOW: payload 계산·검증만 — 기존 LLM prompt 비주입(주입 후 '사용 금지'
  지시 방식 불허). 본 모듈은 어떤 프롬프트 경로에도 배선되지 않는다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from saju_shared_types.risk_engine import (
    ExposureStatus,
    RiskCandidate,
    RiskEpisode,
    RiskKind,
)

from .risk_scoring import _candidate_atoms, risk_priority
from .risk_selection import candidate_uid

# 노출 의미 버전 — 밴드·게이트·claim 정책·압축 순서 변경 시 올린다.
RISK_PRESENTATION_VERSION = "risk-present-r3.0.0-shadow"

# 내부 level 서열(§26-2). 사용자 표시명은 완화형 — 내부 명칭 직접 노출 금지.
_LEVELS = ("none", "advisory", "watch", "warning", "critical")
_LEVEL_RANK = {lv: i for i, lv in enumerate(_LEVELS)}
USER_LEVEL_LABELS = {
    "advisory": "참고",
    "watch": "주의 관찰",
    "warning": "주의 필요",
    "critical": "높은 주의",
}

# numeric band 경계(잠정 — shadow_presentation 감수 대상): 대표 raw 기준.
# C overlay 분포(p50 0.118·p90 0.203·max 0.441)에서 상위 구간을 잠정 구획.
_NUMERIC_BAND_THRESHOLDS = (
    ("critical", 0.40),
    ("warning", 0.25),
    ("watch", 0.12),
    ("advisory", 0.0),  # >0 — 0 이하는 none(대표 자격상 발생하지 않음)
)
# 사용자·LLM 노출용 점수 밴드(§26-7 — raw 소수값 비노출): 같은 경계 공유.
_SCORE_BANDS = (("high", 0.40), ("elevated", 0.25), ("moderate", 0.12),
                ("low", 0.0))
# critical gate의 context confidence 하한(잠정 — 감수 대상).
_CRITICAL_MIN_CONTEXT_CONFIDENCE = 0.5

# 전역 claim 코드(§26-7 — 기계 판정: 항목별 prohibitedClaims 원문과 결합).
GLOBAL_PROHIBITED_CLAIM_CODES = (
    "guaranteed_occurrence",
    "diagnosis",
    "accident_prediction",
    "legal_outcome_certainty",
    "financial_loss_certainty",
    "same_episode_certainty",
    "recovery_guarantee",
)
GLOBAL_ALLOWED_CLAIM_CODES = (
    "pressure_may_increase",
    "review_conditions",
    "watch_timing",
    "partial_relief_possible",
)


def numeric_band(raw_score: float) -> str:
    """대표 raw 점수 → 잠정 numeric band(표현 계층 입력 — 점수 재계산 아님)."""
    if raw_score <= 0.0:
        return "none"
    for band, lo in _NUMERIC_BAND_THRESHOLDS:
        if raw_score >= lo:
            return band
    return "none"


def score_band(raw_score: float) -> str:
    """LLM·사용자 노출용 점수 밴드 — raw 소수값 비노출 계약(§26-7)."""
    if raw_score <= 0.0:
        return "low"
    for band, lo in _SCORE_BANDS:
        if raw_score >= lo:
            return band
    return "low"


def independent_cause_count(rep: RiskCandidate) -> int:
    """독립 canonical cause 수(§26-3) — 같은 cause의 다층 반복은 1개.

    canonical atom(대상 서명 내장)이 유일성 단위: layer corroboration은
    confidence 소관이지 원인 수가 아니다.
    """
    return len(set(_candidate_atoms(rep)))


def identity_phrase_mode(ep: RiskEpisode) -> str:
    """identity 문구 모드 4종(§26-6) — LLM이 병합 확신도를 스스로 판단하지
    않도록 직렬화 단계에서 지정한다."""
    if ep.reality_identity_status == "conflict" or (
            ep.episode_key.startswith("conflict:")):
        return "separate_due_to_conflict"
    if ep.reality_identity_status == "resolved":
        return "confirmed_same_episode"
    if ep.episode_key.startswith("explicit:"):
        return "explicit_local_episode"
    # partial reality alias·fallback 병합 — 확정된 동일 현실 건 단정 금지.
    return "possibly_related"


def _rep_of(ep: RiskEpisode,
            by_uid: Mapping[str, RiskCandidate]) -> RiskCandidate | None:
    return by_uid.get(ep.representative_candidate_id or "")


def _rep_raw(rep: RiskCandidate) -> float:
    if rep.score_components is None:
        return 0.0
    return risk_priority(rep.score_components,
                         transition_bonus=rep.transition_bonus)[0]


def presentation_level(ep: RiskEpisode, rep: RiskCandidate | None) -> str:
    """presentation level(§26-1·2·3) = numeric band + 정책 상한 매트릭스.

    상한: DENIED/NOT_APPLICABLE/CONFLICT=none · confirmed_required+UNKNOWN=
    none · vulnerability=advisory · incident+UNKNOWN=watch · pressure+허용
    UNKNOWN=warning. critical gate: CONFIRMED + 독립 canonical cause ≥2 +
    비취약 + conflict 없음 + context confidence 기준 + identity resolved/
    explicit(partial·fallback의 교차 결합 critical 금지) — 미충족은 warning
    으로 하향(밴드가 critical이어도).
    """
    if rep is None:
        return "none"
    if ep.reality_identity_status == "conflict" or rep.reality_conflict:
        return "none"
    if rep.exposure_status in (ExposureStatus.DENIED,
                               ExposureStatus.NOT_APPLICABLE):
        return "none"
    unknown = rep.exposure_status is ExposureStatus.UNKNOWN
    if unknown and rep.exposure_requirement == "confirmed_required":
        return "none"
    band = numeric_band(_rep_raw(rep))
    cap = "critical"
    if rep.kind is RiskKind.VULNERABILITY:
        cap = "advisory"
    elif unknown:
        cap = ("watch" if rep.kind is RiskKind.INCIDENT_RISK else "warning")
    level = band if _LEVEL_RANK[band] <= _LEVEL_RANK[cap] else cap
    if level == "critical":
        gate = (
            rep.exposure_status is ExposureStatus.CONFIRMED
            and independent_cause_count(rep) >= 2
            and rep.kind is not RiskKind.VULNERABILITY
            and ep.context_confidence >= _CRITICAL_MIN_CONTEXT_CONFIDENCE
            and (ep.reality_identity_status == "resolved"
                 or ep.episode_key.startswith("explicit:"))
        )
        if not gate:
            level = "warning"
    return level


def _required_qualifiers(ep: RiskEpisode, rep: RiskCandidate) -> list[str]:
    """필수 한정어 코드 — token guard에서 절대 제거 금지(P0)."""
    out = []
    if rep.exposure_status is ExposureStatus.UNKNOWN:
        out.append("conditional_exposure")
    if identity_phrase_mode(ep) == "possibly_related":
        out.append("possibly_related")
    if ep.recovery_window is not None:
        out.append("non_assertive_recovery")
    return out


def _confidence_band(value: float) -> str:
    """confidence 숫자 비노출 계약(§26-7) — band만 직렬화."""
    if value >= 0.6:
        return "supported"
    if value >= 0.3:
        return "moderate"
    return "limited"


def build_presentation(
    selected: list[RiskEpisode],
    candidates: list[RiskCandidate],
    claims_by_risk_id: Mapping[str, Mapping[str, object]] | None = None,
) -> list[dict]:
    """R2 선택 집합 → 표현 payload(§26 — 선택 집합 불변·순서만 재배열).

    warning-first(§26-4): bucket(CRITICAL·WARNING → WATCH → ADVISORY → NONE)
    사이만 stable sort — bucket 안에서는 R2 선택 순서 유지. episode 추가·
    삭제 없음(NONE level도 payload에 남긴다 — 비노출 사유 추적, R3 표현
    계층이 조용히 삭제하지 않는다).

    Args:
        selected: select_episodes가 반환한 순서의 episode 목록(불변 소비).
        candidates: 점수 채운 후보(대표 해석용).
        claims_by_risk_id: risk_id → {"manifestations": [ko...],
            "prohibited": [...], "allowed": [...], "claimCeiling": str} —
            사전에서 호출부가 공급(본 모듈은 사전 미접근·순수).
    """
    by_uid = {candidate_uid(c): c for c in candidates}
    claims = claims_by_risk_id or {}

    def _texts(item: Mapping[str, object], key: str) -> list[str]:
        value = item.get(key, [])
        return [str(v) for v in value] if isinstance(value, list) else []

    payloads: list[dict] = []
    for order, ep in enumerate(selected):
        rep = _rep_of(ep, by_uid)
        level = presentation_level(ep, rep)
        item = claims.get(rep.risk_id, {}) if rep is not None else {}
        raw = _rep_raw(rep) if rep is not None else 0.0
        payloads.append({
            # ── P0: 절대 보존(전역 guard·대표 요약·level·qualifier) ──
            "presentationLevel": level,
            "presentationLabel": USER_LEVEL_LABELS.get(level),
            "representativeSummary": _texts(
                item, "manifestations") or None,
            "domains": [d.value for d in ep.domains],
            "exposureStatus": (rep.exposure_status.value if rep else None),
            "identityPhraseMode": identity_phrase_mode(ep),
            "requiredQualifiers": (
                _required_qualifiers(ep, rep) if rep else []),
            "prohibitedClaimCodes": list(GLOBAL_PROHIBITED_CLAIM_CODES),
            "prohibitedClaims": _texts(item, "prohibited"),
            # ── P1: 주요 근거·claim 어휘 ──
            "allowedClaimCodes": list(GLOBAL_ALLOWED_CLAIM_CODES),
            "allowedClaimScope": _texts(item, "allowed"),
            "canonicalCauseCount": (
                independent_cause_count(rep) if rep else 0),
            "scoreBand": score_band(raw),
            "contextConfidenceBand": _confidence_band(ep.context_confidence),
            # ── P2: supporting·recovery ──
            "effectRoles": list(ep.effect_roles),
            "supportingCount": len(ep.supporting_candidate_ids),
            "earliestReliefWindow": (
                ep.recovery_window.earliest_relief_window
                if ep.recovery_window else None),
            "stableRecoveryWindow": (
                ep.recovery_window.stable_recovery_window
                if ep.recovery_window else None),
            "recoveryConfidenceBand": (
                _confidence_band(ep.recovery_window.recovery_confidence)
                if ep.recovery_window else None),
            # ── P3: 진단(LLM 비노출 후보 — 내부 추적) ──
            "diagnostics": {
                "episodeKey": ep.episode_key,
                "selectionOrder": order,
                "startPeriod": ep.start_period,
                "endPeriod": ep.end_period,
            },
        })
    # warning-first stable sort — bucket 순위만 키(§26-4), 동순위=R2 순서.
    bucket = {"critical": 0, "warning": 0, "watch": 1, "advisory": 2,
              "none": 3}
    payloads.sort(key=lambda p: bucket[p["presentationLevel"]])
    return payloads


# token guard 압축 tier(§26-8) — P0 필드는 어떤 예산에서도 제거 금지.
_P0_FIELDS = (
    "presentationLevel", "presentationLabel", "representativeSummary",
    "domains", "exposureStatus", "identityPhraseMode", "requiredQualifiers",
    "prohibitedClaimCodes", "prohibitedClaims",
)
_P1_FIELDS = ("allowedClaimCodes", "allowedClaimScope",
              "canonicalCauseCount", "scoreBand", "contextConfidenceBand")
_P2_FIELDS = ("effectRoles", "supportingCount", "earliestReliefWindow",
              "stableRecoveryWindow", "recoveryConfidenceBand")
_P3_FIELDS = ("diagnostics",)


def serialize_presentation(payloads: list[dict], char_budget: int) -> str:
    """payload 직렬화 + token guard(§26-8 — 문자 예산 기반 결정적 압축).

    P0(전역 claim guard·대표 요약·level·qualifier)는 어떤 예산에서도 보존 —
    prohibited claim·partial/UNKNOWN qualifier·warning 대표 요약을 먼저
    제거하는 압축은 존재하지 않는다. 예산 부족 시 P3→P2→P1 순으로 전
    episode에서 일괄 탈락(선택된 episode의 조용한 삭제 금지 — 최소 compact
    표현(P0)으로 남긴다).
    """
    def _render(tiers: int) -> str:
        fields: tuple[str, ...] = _P0_FIELDS
        if tiers >= 1:
            fields = fields + _P1_FIELDS
        if tiers >= 2:
            fields = fields + _P2_FIELDS
        if tiers >= 3:
            fields = fields + _P3_FIELDS
        slim = [{k: p[k] for k in fields if k in p} for p in payloads]
        return json.dumps({"riskEpisodes": slim}, ensure_ascii=False,
                          sort_keys=True)
    for tiers in (3, 2, 1, 0):
        rendered = _render(tiers)
        if len(rendered) <= char_budget:
            return rendered
    return _render(0)  # P0는 예산 초과여도 보존(절대 제거 금지 계약)


def presentation_policy_hash() -> str:
    """노출 정책 해시(§26-18) — shadow_presentation 감수 무효화 가드 재료."""
    policy = {
        "version": RISK_PRESENTATION_VERSION,
        "numeric_band_thresholds": list(_NUMERIC_BAND_THRESHOLDS),
        "score_bands": list(_SCORE_BANDS),
        "level_cap_matrix": {
            "denied_or_na_or_conflict": "none",
            "confirmed_required_unknown": "none",
            "vulnerability": "advisory",
            "incident_unknown": "watch",
            "pressure_unknown": "warning",
            "confirmed": "numeric band + critical gate",
        },
        "critical_gate": {
            "exposure": "CONFIRMED",
            "independent_canonical_causes": ">=2 — 같은 cause 다층 반복=1"
                                            "(layer corroboration은"
                                            " confidence 소관)",
            "representative": "vulnerability 아님",
            "context_conflict": "없음",
            "min_context_confidence": _CRITICAL_MIN_CONTEXT_CONFIDENCE,
            "identity": "resolved 또는 explicit(partial·fallback 금지)",
            "fail": "warning으로 하향",
        },
        "ordering": "warning-first stable sort — bucket(critical·warning →"
                    " watch → advisory → none) 사이만, bucket 내 R2 순서"
                    " 유지·선택 집합 불변",
        "identity_phrase_modes": ["confirmed_same_episode",
                                  "explicit_local_episode",
                                  "possibly_related",
                                  "separate_due_to_conflict"],
        "claim_codes": {"prohibited": list(GLOBAL_PROHIBITED_CLAIM_CODES),
                        "allowed": list(GLOBAL_ALLOWED_CLAIM_CODES),
                        "merge": "전역 + 항목 prohibitedClaims 결합"},
        "recovery_wording": "단정 금지(해결·완전 회복·위험 소멸)·confidence"
                            " 숫자/퍼센트 비노출(band만)",
        "score_exposure": "raw 소수값·내부 risk_id·cause atom 원문·manifest"
                          " hash 비노출 — scoreBand/confidenceBand만",
        "token_guard": {"tiers": {"P0": list(_P0_FIELDS),
                                  "P1": list(_P1_FIELDS),
                                  "P2": list(_P2_FIELDS),
                                  "P3": list(_P3_FIELDS)},
                        "invariant": "P0 절대 보존·episode 조용한 삭제 금지"
                                     "(compact 표현으로 유지)"},
        "mode": "SHADOW=payload 계산·검증만(prompt 비주입 — '사용 금지' 지시"
                " 방식 불허)·EXPOSE=감수 payload만",
        "user_labels": USER_LEVEL_LABELS,
    }
    return hashlib.sha256(json.dumps(
        policy, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


__all__ = [
    "GLOBAL_ALLOWED_CLAIM_CODES",
    "GLOBAL_PROHIBITED_CLAIM_CODES",
    "RISK_PRESENTATION_VERSION",
    "USER_LEVEL_LABELS",
    "build_presentation",
    "identity_phrase_mode",
    "independent_cause_count",
    "numeric_band",
    "presentation_level",
    "presentation_policy_hash",
    "score_band",
    "serialize_presentation",
]
