"""위험 노출 계층 R3 — presentation level·claim payload·token guard
(doc/v2_2/RISK_DICTIONARY_REVIEW.md §26 manifest, 감수 41·42차 — shadow 전용).

핵심 원칙(데굴님): 위험 수준은 점수를 다시 계산하는 계층이 아니라 **이미
감수된 episode를 현실 확인 수준과 근거 독립성에 맞는 문장 강도로 변환하는
계층**이다. 불변식:

- R3는 R1 점수·R2 선택 집합(선택 id·대표·budget 누락 기록)을 절대 변경하지
  않는다 — 입력 불변(순수 함수), episode 추가·삭제·재선택 금지.
- numeric band 입력=대표 **capped**(감수 42차 — R2 정렬은 raw, R3 의미
  밴드는 bounded score)와 presentation level(정책 게이트)은 분리.
- critical의 원인 수는 episode 전체가 아니라 **critical 적격 원인**만 —
  대표를 직접 지지하거나 독립 exposable primary effect를 지지하는 canonical
  CAUSE(supporting·background·vulnerability·비노출·partial 교차 연결 제외).
- **audit payload와 LLM payload 분리**(감수 42차): NONE episode는 감사
  기록(presentation_records)에 omission reason과 함께 보존하되 LLM payload
  (llm_risk_episodes)에서는 제외 — prompt에 넣고 '언급 금지' 지시 방식 불허.
- claim 충돌은 prohibited 우선, 미등록 코드는 fail-closed 오류.
- SHADOW: payload 계산·검증만 — 기존 LLM prompt 비주입. 본 모듈은 어떤
  프롬프트 경로에도 배선되지 않는다(OFF vs SHADOW 최종 입력 byte 불변).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping

from saju_shared_types.risk_engine import (
    ExposureStatus,
    RiskCandidate,
    RiskEpisode,
    RiskKind,
    is_exposable,
)

from .risk_scoring import _candidate_atoms, normalized_effect_role, risk_priority
from .risk_selection import candidate_uid

# 노출 의미 버전 — 밴드·게이트·claim 정책·압축 순서 변경 시 올린다.
RISK_PRESENTATION_VERSION = "risk-present-r3.1.0-shadow"

# 내부 level 서열(§26-2). 사용자 표시명은 완화형 — 내부 명칭 직접 노출 금지.
_LEVELS = ("none", "advisory", "watch", "warning", "critical")
_LEVEL_RANK = {lv: i for i, lv in enumerate(_LEVELS)}
# 표시명(감수 43차 확정): 사건 발생 확정으로 읽히지 않는 대응 우선도 표현.
USER_LEVEL_LABELS = {
    "advisory": "참고 신호",
    "watch": "관찰 필요",
    "warning": "주의 필요",
    "critical": "우선 점검 필요",
}

# numeric band 경계(감수 43차 — warning 0.25 **확정**, watch 0.12·critical
# 0.40 shadow 확정: critical은 코퍼스 양성 0건이라 실분포 검증 pending).
# 대표 **capped** rankable 기준(감수 42차 — cap 초과 정보는 R2 정렬 소관).
_NUMERIC_BAND_THRESHOLDS = (
    ("critical", 0.40),
    ("warning", 0.25),
    ("watch", 0.12),
    ("advisory", 0.0),  # >0 — 0 이하는 none(대표 자격상 발생하지 않음)
)
# 사용자·LLM 노출용 점수 밴드(§26-7 — raw 소수값 비노출): 같은 경계 공유.
_SCORE_BANDS = (("high", 0.40), ("elevated", 0.25), ("moderate", 0.12),
                ("low", 0.0))
# critical gate의 context confidence 하한(감수 43차 **0.75 확정** — 코퍼스
# 양성 0건이라 분포 선택 불가 → 최강 표현에 맞는 보수 정책값. 실분포
# calibration pending: EXPOSE에서 critical 활성화 전 golden corpus 필요).
_CRITICAL_MIN_CONTEXT_CONFIDENCE = 0.75
# critical 실증 검증 상태는 risk_exposure.critical_validation_state로
# 분리(감수 44차 §2) — 실사용 양성 사례 추가가 49항목 shadow_presentation
# 감수를 강등하지 않도록 정책 공식(본 모듈 hash)과 실증 상태를 분리한다.
# token budget(감수 43차 확정): 기본 1024 · 안전 하한 512 — 512 미만이거나
# P0_COMPACT조차 초과하면 위험 payload 전체 비주입(fail-closed).
DEFAULT_RISK_PRESENTATION_BUDGET = 1024
MIN_SAFE_RISK_PRESENTATION_BUDGET = 512

# 전역 claim 코드(§26-7 — 기계 판정). 항목별 prohibitedClaims 원문은 감수된
# 짧은 지침으로 episode payload에 병기하되, 런타임 강제는 코드가 담당한다.
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
_KNOWN_CLAIM_CODES = frozenset(GLOBAL_PROHIBITED_CLAIM_CODES
                               + GLOBAL_ALLOWED_CLAIM_CODES)

# NONE(비노출) 감사 사유(감수 42차 §5) — LLM payload 제외 + 기록 보존.
_OMISSION_REASONS = (
    "NON_EXPOSABLE",
    "CLAIM_CEILING_NONE",
    "CONTEXT_CONFLICT",
    "CONFIRMED_REQUIRED_UNKNOWN",
)
# 사전 claim ceiling 어휘 → 내부 level 정규화(감수 42차 — fail-closed).
_CEILING_ALIASES = {"conditional_warning": "warning"}
# 강등 사유 코드(감수 42차 §12 — primary + all 병기).
_DOWNGRADE_REASON_ORDER = (
    "ITEM_CLAIM_CEILING",
    "EXPOSURE_POLICY_CEILING",
    "VULNERABILITY_CAP",
    "INCIDENT_UNKNOWN_CAP",
    "EXPOSURE_CAP",
    "INDEPENDENT_CAUSE_UNMET",
    "IDENTITY_NOT_STRONG_ENOUGH",
    "CONTEXT_CONFIDENCE_UNMET",
)


def numeric_band(capped_score: float) -> str:
    """대표 capped 점수 → 잠정 numeric band(표현 계층 입력 — 재계산 아님)."""
    if capped_score <= 0.0:
        return "none"
    for band, lo in _NUMERIC_BAND_THRESHOLDS:
        if capped_score >= lo:
            return band
    return "none"


def score_band(capped_score: float) -> str:
    """LLM·사용자 노출용 점수 밴드 — raw 소수값 비노출 계약(§26-7)."""
    if capped_score <= 0.0:
        return "low"
    for band, lo in _SCORE_BANDS:
        if capped_score >= lo:
            return band
    return "low"


def independent_cause_count(rep: RiskCandidate) -> int:
    """대표의 독립 canonical cause 수 — 같은 cause의 다층 반복은 1개."""
    return len(set(_candidate_atoms(rep)))


def critical_eligible_cause_count(
    ep: RiskEpisode,
    rep: RiskCandidate,
    members: list[RiskCandidate],
) -> int:
    """critical 적격 원인 수(감수 42차 §4) — episode 전체 원인이 아니다.

    포함: 대표를 직접 지지하는 canonical CAUSE + **독립 exposable primary
    effect**(대표와 다른 normalized role의 비흡수·비취약·노출 가능 구성원)를
    지지하는 CAUSE. 제외: vulnerability·absorbed supporting·background·
    비노출 member 원인·partial identity의 교차 도메인 연결로만 합쳐진 원인
    (partial episode는 대표 자신의 원인만). canonical atom이 유일성 단위 —
    layer 반복=1(_candidate_atoms는 CAUSE 원자만 — activation/amplifier의
    occurrence 기여 0 원자는 애초에 포함되지 않는다).
    """
    causes = set(_candidate_atoms(rep))
    if ep.reality_identity_status == "partial":
        return len(causes)
    rep_role = normalized_effect_role(rep)
    for m in members:
        if candidate_uid(m) == candidate_uid(rep):
            continue
        if m.suppressed_by_specificity is not None:  # absorbed supporting
            continue
        if m.kind is RiskKind.VULNERABILITY:
            continue
        if not is_exposable(m):
            continue
        if normalized_effect_role(m) == rep_role:  # 독립 effect만
            continue
        causes |= set(_candidate_atoms(m))
    return len(causes)


def identity_phrase_mode(ep: RiskEpisode) -> str:
    """identity 문구 모드 4종(§26-6) — LLM이 병합 확신도를 스스로 판단하지
    않도록 직렬화 단계에서 지정. separate_due_to_conflict는 감사·설명 전용."""
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


def _rep_capped(rep: RiskCandidate) -> float:
    if rep.score_components is None:
        return 0.0
    return risk_priority(rep.score_components,
                         transition_bonus=rep.transition_bonus)[1]


def presentation_decision(
    ep: RiskEpisode,
    rep: RiskCandidate | None,
    members: list[RiskCandidate] | None = None,
    *,
    item_claim_ceiling: str | None = None,
    unknown_claim_ceiling: str | None = None,
) -> dict:
    """presentation 판정(§26-1·2·3 + 감수 42차 §3·4·5).

    반환: {"level", "omission_reason"(none일 때), "downgrade_reasons"(all),
    "primary_downgrade_reason"}. 최종 level = min(numeric band, 전역
    exposure/kind 상한, **item claimCeiling**, **exposurePolicy의 UNKNOWN
    ceiling**) + critical gate. 판정은 R1/R2에 역영향 없음(순수).
    """
    if rep is None:
        return {"level": "none", "omission_reason": "NON_EXPOSABLE",
                "downgrade_reasons": [], "primary_downgrade_reason": None}
    if ep.reality_identity_status == "conflict" or rep.reality_conflict:
        return {"level": "none", "omission_reason": "CONTEXT_CONFLICT",
                "downgrade_reasons": [], "primary_downgrade_reason": None}
    if rep.exposure_status in (ExposureStatus.DENIED,
                               ExposureStatus.NOT_APPLICABLE):
        return {"level": "none", "omission_reason": "NON_EXPOSABLE",
                "downgrade_reasons": [], "primary_downgrade_reason": None}
    unknown = rep.exposure_status is ExposureStatus.UNKNOWN
    if unknown and rep.exposure_requirement == "confirmed_required":
        return {"level": "none",
                "omission_reason": "CONFIRMED_REQUIRED_UNKNOWN",
                "downgrade_reasons": [], "primary_downgrade_reason": None}

    band = numeric_band(_rep_capped(rep))
    caps: list[tuple[str, str]] = []  # (cap level, reason code)
    if rep.kind is RiskKind.VULNERABILITY:
        caps.append(("advisory", "VULNERABILITY_CAP"))
    elif unknown:
        if rep.kind is RiskKind.INCIDENT_RISK:
            caps.append(("watch", "INCIDENT_UNKNOWN_CAP"))
        else:
            caps.append(("warning", "EXPOSURE_CAP"))
    # 항목별 상한(감수 42차 §3): claimCeiling + exposurePolicy의 UNKNOWN 상한.
    if item_claim_ceiling is not None:
        caps.append((item_claim_ceiling, "ITEM_CLAIM_CEILING"))
    if unknown and unknown_claim_ceiling is not None:
        caps.append((unknown_claim_ceiling, "EXPOSURE_POLICY_CEILING"))

    # 사전 ceiling 어휘 정규화(fail-closed — 미등록 값은 오류):
    # conditional_warning=조건부 warning(조건성은 qualifier가 담당 — 상한은
    # warning과 동일). 사전 어휘 추가 시 여기 명시 매핑 필수.
    caps = [(_CEILING_ALIASES.get(cap, cap), reason)
            for cap, reason in caps]
    for cap_level, _reason in caps:
        if cap_level not in _LEVEL_RANK:
            raise ValueError(f"미지원 claim ceiling: {cap_level}")
    level = band
    binding: list[str] = []
    for cap_level, reason in caps:
        if _LEVEL_RANK[cap_level] < _LEVEL_RANK[level]:
            level = cap_level
            binding = [reason]
        elif _LEVEL_RANK[cap_level] == _LEVEL_RANK[level] and (
                _LEVEL_RANK[cap_level] < _LEVEL_RANK[band]):
            binding.append(reason)
    if level == "critical":
        member_list = members if members is not None else [rep]
        gate_fail: list[str] = []
        if rep.exposure_status is not ExposureStatus.CONFIRMED:
            gate_fail.append("EXPOSURE_CAP")
        if critical_eligible_cause_count(ep, rep, member_list) < 2:
            gate_fail.append("INDEPENDENT_CAUSE_UNMET")
        if not (ep.reality_identity_status == "resolved"
                or ep.episode_key.startswith("explicit:")):
            gate_fail.append("IDENTITY_NOT_STRONG_ENOUGH")
        if ep.context_confidence < _CRITICAL_MIN_CONTEXT_CONFIDENCE:
            gate_fail.append("CONTEXT_CONFIDENCE_UNMET")
        if rep.kind is RiskKind.VULNERABILITY:
            gate_fail.append("VULNERABILITY_CAP")
        if gate_fail:
            level = "warning"
            binding = gate_fail
    if level == "none":
        return {"level": "none", "omission_reason": "CLAIM_CEILING_NONE",
                "downgrade_reasons": sorted(set(binding)),
                "primary_downgrade_reason": _primary_reason(binding)}
    return {"level": level, "omission_reason": None,
            "downgrade_reasons": sorted(set(binding)),
            "primary_downgrade_reason": _primary_reason(binding)}


def _primary_reason(reasons: list[str]) -> str | None:
    for code in _DOWNGRADE_REASON_ORDER:
        if code in reasons:
            return code
    return None


def presentation_level(
    ep: RiskEpisode,
    rep: RiskCandidate | None,
    members: list[RiskCandidate] | None = None,
    *,
    item_claim_ceiling: str | None = None,
    unknown_claim_ceiling: str | None = None,
) -> str:
    """presentation_decision의 level만(하위 호환 헬퍼)."""
    return presentation_decision(
        ep, rep, members, item_claim_ceiling=item_claim_ceiling,
        unknown_claim_ceiling=unknown_claim_ceiling)["level"]


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


def _validate_claim_codes(codes: list[str], where: str) -> list[str]:
    """미등록 claim code fail-closed(감수 42차 §6)."""
    unknown = [c for c in codes if c not in _KNOWN_CLAIM_CODES]
    if unknown:
        raise ValueError(f"미등록 claim code({where}): {unknown}")
    return codes


def build_presentation(
    selected: list[RiskEpisode],
    candidates: list[RiskCandidate],
    claims_by_risk_id: Mapping[str, Mapping[str, object]] | None = None,
) -> dict:
    """R2 선택 집합 → 표현 payload(§26 + 감수 42차 audit/LLM 분리).

    반환:
        {"globalProhibitedClaimCodes", "globalAllowedClaimCodes",  # 1회
         "presentationRecords": [전 episode — NONE 포함·omission reason·
                                 진단 필드(감사 전용)],
         "llmRiskEpisodes": [ADVISORY 이상만 — LLM 노출 필드만(진단·전역
                             코드 반복 없음)]}

    warning-first(§26-4): bucket(critical·warning → watch → advisory) 사이만
    stable sort — bucket 안에서는 R2 선택 순서 유지. episode 추가·삭제·
    재선택 없음. claim 충돌은 prohibited 우선(effective allowed에서 제거),
    미등록 코드 fail-closed.

    Args:
        selected: select_episodes가 반환한 순서의 episode 목록(불변 소비).
        candidates: 점수 채운 후보(대표 해석용).
        claims_by_risk_id: risk_id → {"manifestations": [ko...],
            "prohibited": [ko 짧은 지침...], "allowed": [ko...],
            "claimCeiling": str|None, "unknownClaimCeiling": str|None,
            "allowedCodes": [...], "prohibitedCodes": [...]} — 사전에서
            호출부가 공급(본 모듈은 사전 미접근·순수).
    """
    by_uid = {candidate_uid(c): c for c in candidates}
    claims = claims_by_risk_id or {}

    def _texts(item: Mapping[str, object], key: str) -> list[str]:
        value = item.get(key, [])
        return [str(v) for v in value] if isinstance(value, list) else []

    def _ceiling(item: Mapping[str, object], key: str) -> str | None:
        value = item.get(key)
        return str(value) if isinstance(value, str) else None

    records: list[dict] = []
    for order, ep in enumerate(selected):
        rep = _rep_of(ep, by_uid)
        members = [by_uid[m] for m in ep.member_candidate_ids if m in by_uid]
        item = claims.get(rep.risk_id, {}) if rep is not None else {}
        decision = presentation_decision(
            ep, rep, members,
            item_claim_ceiling=_ceiling(item, "claimCeiling"),
            unknown_claim_ceiling=_ceiling(item, "unknownClaimCeiling"))
        level = decision["level"]
        capped = _rep_capped(rep) if rep is not None else 0.0
        item_prohibited_codes = _validate_claim_codes(
            _texts(item, "prohibitedCodes"), "prohibitedCodes")
        item_allowed_codes = _validate_claim_codes(
            _texts(item, "allowedCodes"), "allowedCodes")
        # 충돌 우선순위(감수 42차 §6): prohibited always wins.
        all_prohibited = set(GLOBAL_PROHIBITED_CLAIM_CODES) | set(
            item_prohibited_codes)
        effective_allowed = [c for c in (*GLOBAL_ALLOWED_CLAIM_CODES,
                                         *item_allowed_codes)
                             if c not in all_prohibited]
        records.append({
            # ── P0(LLM에서도 절대 보존) ──
            "presentationLevel": level,
            "presentationLabel": USER_LEVEL_LABELS.get(level),
            "representativeSummary": _texts(item, "manifestations") or None,
            "domains": [d.value for d in ep.domains],
            "exposureStatus": (rep.exposure_status.value if rep else None),
            "identityPhraseMode": identity_phrase_mode(ep),
            "requiredQualifiers": (
                _required_qualifiers(ep, rep) if rep else []),
            # 항목별 추가분만(전역 7코드는 payload 최상단 1회 — 중복 제거).
            "episodeProhibitedClaimCodes": sorted(item_prohibited_codes),
            "episodeProhibitedPhrases": _texts(item, "prohibited"),
            # ── P1 ──
            "effectiveAllowedClaimCodes": effective_allowed,
            "allowedClaimScope": _texts(item, "allowed"),
            "criticalEligibleCauseCount": (
                critical_eligible_cause_count(ep, rep, members)
                if rep is not None else 0),
            "scoreBand": score_band(capped),
            "contextConfidenceBand": _confidence_band(ep.context_confidence),
            # ── P2 ──
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
            # ── 감사 전용(LLM 비노출) ──
            "presentationOmissionReason": decision["omission_reason"],
            "downgradeReasons": decision["downgrade_reasons"],
            "primaryDowngradeReason": decision["primary_downgrade_reason"],
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
    records.sort(key=lambda p: bucket[p["presentationLevel"]])
    llm_episodes = [
        {k: r[k] for k in (*_P0_FIELDS, *_P1_FIELDS, *_P2_FIELDS)}
        for r in records if r["presentationLevel"] != "none"
    ]
    return {
        "globalProhibitedClaimCodes": list(GLOBAL_PROHIBITED_CLAIM_CODES),
        "globalAllowedClaimCodes": list(GLOBAL_ALLOWED_CLAIM_CODES),
        "presentationRecords": records,
        "llmRiskEpisodes": llm_episodes,
    }


# token guard 압축 tier(§26-8 + 감수 42차 §8) — P0는 어떤 예산에서도 유지,
# P0 초과 시 P0_COMPACT 고정 포맷으로 축약(예산 초과 방치 금지).
_P0_FIELDS = (
    "presentationLevel", "presentationLabel", "representativeSummary",
    "domains", "exposureStatus", "identityPhraseMode", "requiredQualifiers",
    "episodeProhibitedClaimCodes", "episodeProhibitedPhrases",
)
_P1_FIELDS = ("effectiveAllowedClaimCodes", "allowedClaimScope",
              "criticalEligibleCauseCount", "scoreBand",
              "contextConfidenceBand")
_P2_FIELDS = ("effectRoles", "supportingCount", "earliestReliefWindow",
              "stableRecoveryWindow", "recoveryConfidenceBand")


def estimate_tokens(text: str, counter=None) -> int:
    """token 추정(감수 43차 — ceil(chars/3) 기각·교체).

    1순위: counter(모델 tokenizer adapter — Callable[[str], int]) 주입 시
    그 결과 사용(EXPOSE 배선 시 provider token-count 연결). fallback(보수적
    다국어): ascii 4자≈1토큰, **비ascii(한국어 등) 1자≈1토큰**(한국어에 /3
    적용 금지 — 과소 추정 불허가 원칙) + 10% 안전 여유 + 고정 wrapper 8토큰.
    과대 계산은 허용, 과소 계산은 불허.
    """
    if counter is not None:
        return int(counter(text))
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    non_ascii = len(text) - ascii_chars
    estimated = math.ceil(ascii_chars / 4) + non_ascii
    return math.ceil(estimated * 1.10) + 8


def _compact_episode(r: dict) -> dict:
    """P0 compact fallback(감수 42차 §8) — 고정 포맷 최소 표현."""
    return {
        "presentationLevel": r["presentationLevel"],
        "domains": r["domains"],
        "effectRoles": r.get("effectRoles", [])[:1],
        "requiredQualifiers": r["requiredQualifiers"],
        "episodeProhibitedClaimCodes": r["episodeProhibitedClaimCodes"],
    }


RENDER_TIERS = ("P2", "P1", "P0", "P0_COMPACT")


def render_llm_payload(payload: dict, tier: str) -> str:
    """명시 tier로 LLM payload 직렬화(감수 45차 — RiskPromptBlock의 2차
    재계수·재압축 루프가 사용). tier: P2(full)/P1/P0/P0_COMPACT."""
    episodes = payload["llmRiskEpisodes"]
    fields_by_tier = {
        "P2": _P0_FIELDS + _P1_FIELDS + _P2_FIELDS,
        "P1": _P0_FIELDS + _P1_FIELDS,
        "P0": _P0_FIELDS,
    }
    if tier == "P0_COMPACT":
        slim = [_compact_episode(r) for r in episodes]
    else:
        fields = fields_by_tier.get(tier)
        if fields is None:
            raise ValueError(f"미지원 render tier: {tier}")
        slim = [{k: r[k] for k in fields if k in r} for r in episodes]
    doc = {
        "globalProhibitedClaimCodes": payload["globalProhibitedClaimCodes"],
        "globalAllowedClaimCodes": payload["globalAllowedClaimCodes"],
        "riskEpisodes": slim,
    }
    if tier == "P0_COMPACT":
        doc["compressionMode"] = "P0_COMPACT"
    return json.dumps(doc, ensure_ascii=False, sort_keys=True)


def serialize_llm_payload(payload: dict, token_budget: int,
                          counter=None) -> str:
    """LLM payload 직렬화 + token guard(감수 42·43차 — fail-closed).

    전역 prohibited/allowed 코드는 최상단 1회(중복 제거). 예산 부족 시
    P2→P1→P0→**P0_COMPACT** 순 전 episode 일괄 축약 — episode의 조용한
    삭제·prohibited/qualifier 제거는 어떤 단계에도 없다.

    **fail-closed(감수 43차)**: budget < MIN_SAFE(512)이거나 P0_COMPACT
    조차 초과하면 riskEpisodes=[] + exposureSuppressedReason=
    TOKEN_BUDGET_INSUFFICIENT — overflow 상태로 prompt에 주입하는 경로는
    존재하지 않는다. counter=모델 tokenizer adapter(미주입 시 보수 추정).
    """
    episodes = payload["llmRiskEpisodes"]

    def _render(fields: tuple[str, ...] | None, compact: bool) -> str:
        if compact:
            slim = [_compact_episode(r) for r in episodes]
        else:
            assert fields is not None
            slim = [{k: r[k] for k in fields if k in r} for r in episodes]
        doc = {
            "globalProhibitedClaimCodes":
                payload["globalProhibitedClaimCodes"],
            "globalAllowedClaimCodes": payload["globalAllowedClaimCodes"],
            "riskEpisodes": slim,
        }
        if compact:
            doc["compressionMode"] = "P0_COMPACT"
        return json.dumps(doc, ensure_ascii=False, sort_keys=True)

    def _suppressed() -> str:
        # fail-closed(감수 43차): 일부 episode·qualifier를 잘라 불완전한
        # 위험 설명을 넣는 것보다 위험 payload 전체 비주입이 안전 —
        # presentationRecords(감사)는 payload dict에 그대로 남는다.
        return json.dumps({
            "globalProhibitedClaimCodes":
                payload["globalProhibitedClaimCodes"],
            "globalAllowedClaimCodes": payload["globalAllowedClaimCodes"],
            "riskEpisodes": [],
            "exposureSuppressedReason": "TOKEN_BUDGET_INSUFFICIENT",
        }, ensure_ascii=False, sort_keys=True)

    if token_budget < MIN_SAFE_RISK_PRESENTATION_BUDGET:
        return _suppressed()
    tiers: list[tuple[str, ...]] = [
        _P0_FIELDS + _P1_FIELDS + _P2_FIELDS,
        _P0_FIELDS + _P1_FIELDS,
        _P0_FIELDS,
    ]
    for fields in tiers:
        rendered = _render(fields, compact=False)
        if estimate_tokens(rendered, counter) <= token_budget:
            return rendered
    rendered = _render(None, compact=True)
    if estimate_tokens(rendered, counter) <= token_budget:
        return rendered
    return _suppressed()  # compact조차 초과 — 전체 비주입(fail-closed)


def presentation_policy_hash() -> str:
    """노출 정책 해시(§26-18 + 감수 42차 §14) — 감수 무효화 가드 재료."""
    policy = {
        "version": RISK_PRESENTATION_VERSION,
        "numeric_band_source": "representative capped_rankable_priority"
                               "(감수 42차 — R2 정렬은 raw·R3 밴드는 capped)",
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
        "item_ceiling": "final = min(전역 상한, item claimCeiling,"
                        " exposurePolicy unknown ceiling) — 미지원 값"
                        " fail-closed(감수 42차 §3)",
        "ceiling_aliases": _CEILING_ALIASES,
        "critical_gate": {
            "exposure": "CONFIRMED",
            "cause_basis": "critical_eligible_cause_ids ≥2 — 대표 직접 지지"
                           " + 독립 exposable primary effect의 CAUSE만"
                           "(supporting·background·vulnerability·비노출·"
                           "partial 교차 연결 제외, 다층 반복=1)",
            "representative": "vulnerability 아님",
            "context_conflict": "없음",
            "min_context_confidence": _CRITICAL_MIN_CONTEXT_CONFIDENCE,
            "identity": "resolved 또는 explicit(partial·fallback 금지)",
            "fail": "warning으로 하향 + 사유 기록(primary/all)",
        },
        "payload_split": "presentation_records(전 episode·NONE 포함·omission"
                         " reason — 감사)와 llm_risk_episodes(ADVISORY 이상만"
                         " — prompt 주입 후보) 분리: NONE은 LLM 비노출"
                         "(감수 42차 §5)",
        "omission_reasons": list(_OMISSION_REASONS),
        "downgrade_reason_order": list(_DOWNGRADE_REASON_ORDER),
        "ordering": "warning-first stable sort — bucket 사이만, bucket 내"
                    " R2 순서 유지·선택 집합 불변",
        "identity_phrase_modes": ["confirmed_same_episode",
                                  "explicit_local_episode",
                                  "possibly_related",
                                  "separate_due_to_conflict"],
        "claim_codes": {
            "prohibited": list(GLOBAL_PROHIBITED_CLAIM_CODES),
            "allowed": list(GLOBAL_ALLOWED_CLAIM_CODES),
            "conflict_precedence": "prohibited always wins(effective"
                                   " allowed에서 제거)",
            "unknown_code": "fail-closed 오류",
            "global_dedup": "전역 코드는 payload 최상단 1회 —"
                            " episode에는 항목 추가분만",
        },
        "recovery_wording": "단정 금지(해결·완전 회복·위험 소멸)·confidence"
                            " 숫자/퍼센트 비노출(band만)",
        "score_exposure": "raw/capped 소수값·내부 risk_id·cause atom 원문·"
                          "manifest hash 비노출 — scoreBand/confidenceBand만",
        "token_guard": {
            "estimator": "1순위=모델 tokenizer adapter 주입 / fallback="
                         "보수적 다국어(ascii/4 + 비ascii 1:1 · ×1.10 · +8"
                         " wrapper) — 한국어 /3 금지·과소 추정 불허"
                         "(감수 43차 확정)",
            "budgets": {"default": DEFAULT_RISK_PRESENTATION_BUDGET,
                        "min_safe": MIN_SAFE_RISK_PRESENTATION_BUDGET},
            "tiers": {"P0": list(_P0_FIELDS), "P1": list(_P1_FIELDS),
                      "P2": list(_P2_FIELDS)},
            "fail_closed": "budget<512 또는 P0_COMPACT 초과 →"
                           " riskEpisodes=[] + exposureSuppressedReason="
                           "TOKEN_BUDGET_INSUFFICIENT(감사 기록 유지) —"
                           " overflow 주입 경로 없음(감수 43차)",
        },
        "critical_validation": "실증 상태는 exposure 계층으로 분리"
                               "(감수 44차 — risk_exposure."
                               "critical_validation_state)",
        "mode": "SHADOW=payload 계산·검증만 — OFF와 최종 LLM 입력"
                " byte-identical(주입 후 '사용 금지' 지시 방식 불허)"
                "·EXPOSE=감수 payload만",
        "user_labels": USER_LEVEL_LABELS,
    }
    return hashlib.sha256(json.dumps(
        policy, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


__all__ = [
    "DEFAULT_RISK_PRESENTATION_BUDGET",
    "GLOBAL_ALLOWED_CLAIM_CODES",
    "MIN_SAFE_RISK_PRESENTATION_BUDGET",
    "GLOBAL_PROHIBITED_CLAIM_CODES",
    "RISK_PRESENTATION_VERSION",
    "USER_LEVEL_LABELS",
    "build_presentation",
    "critical_eligible_cause_count",
    "estimate_tokens",
    "identity_phrase_mode",
    "independent_cause_count",
    "numeric_band",
    "presentation_decision",
    "presentation_level",
    "presentation_policy_hash",
    "RENDER_TIERS",
    "render_llm_payload",
    "score_band",
    "serialize_llm_payload",
]
