"""위험 블록 토큰 실측(감수 62차 — RISK_ENGINE.md §7-1 reserve 산정 근거).

대표 구성(질문 유형 5종 × episode 수 구성 + 재작성/재생성 attempt·긴 한글
근거·리포트 4섹션 동시 활성)에 대해 **위험 부가분**(직렬화 payload +
instruction/notice + wrapper + transport schema) 토큰을 오프라인
(estimate_tokens — 보수적 과대 추정)으로 산출한다. p50/p95/p99 + 합성
결정적 최대를 보고해 RISK_CONTEXT_RESERVE(현행 2,000)의 적정성을 검증한다.

사용: python scripts/risk_block_token_survey.py
"""

from __future__ import annotations

import hashlib
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from saju_engines.risk_claim_audit import build_risk_output_schema  # noqa: E402
from saju_engines.risk_exposure import (  # noqa: E402
    RISK_EXPOSURE_COMPANION_NOTICE_BLOCK,
    RISK_EXPOSURE_INSTRUCTION_BLOCK,
    RiskPromptBlock,
    wrap_risk_block,
)
from saju_engines.risk_presentation import (  # noqa: E402
    build_presentation,
    estimate_tokens,
    serialize_llm_payload,
)
from saju_engines.risk_scoring import score_shadow  # noqa: E402
from saju_engines.risk_selection import build_episodes  # noqa: E402
from saju_shared_types.risk_engine import (  # noqa: E402
    EvidenceRole,
    ExposureStatus,
    RiskCandidate,
    RiskDomain,
    RiskEvidence,
    RiskKind,
)

_REAL_IDS = ["FIN_UNEXPECTED_EXPENSE", "FIN_CASHFLOW_PRESSURE",
             "CAR_ORG_CONFLICT", "LEG_CONTRACT_TERMINATION_RISK",
             "CAR_WORK_OVERLOAD", "LEG_DOCUMENT_ERROR"]
_LONG_KO = ("계약 조건과 보증금 반환 일정, 부서 개편에 따른 업무 이관과 "
            "인수인계 범위를 함께 점검해 두면 좋은 시기입니다. ") * 3


def _candidates(n: int) -> list[RiskCandidate]:
    doms = [RiskDomain.FINANCE, RiskDomain.CAREER,
            RiskDomain.CONTRACT_LEGAL, RiskDomain.RELOCATION]
    out = []
    for i in range(n):
        rid = _REAL_IDS[i % len(_REAL_IDS)]
        src = (f"relation:CHUNG:month_pillar:branch:ZHENGCAI:{i}:"
               + _LONG_KO[:60])
        out.append(RiskCandidate(
            risk_id=rid, domain=doms[i % 4], kind=RiskKind.INCIDENT_RISK,
            risk_family=f"fam{i}", period_key=str(2026 + (i % 2)),
            evidence=[RiskEvidence(
                evidence_id=f"{2026 + (i % 2)}|{src}", code="T",
                period_key=str(2026 + (i % 2)), layer="sewoon",
                source=src, strength=0.6, role=EvidenceRole.TRIGGER,
                source_group="event_shape", target_domain=doms[i % 4])],
            exposure_status=ExposureStatus.CONFIRMED, specificity_rank=2,
            normalized_effect_role="financial_pressure",
            trigger_cause_atoms=[src], legal_episode_id=f"e{i}"))
    return out


def _risk_extra_tokens(n_candidates: int, *, hard_max: int,
                       companion: bool = False) -> int:
    cands = _candidates(n_candidates)
    scored = score_shadow(cands, {c.risk_id: 0.6 for c in cands})
    payload = build_presentation(build_episodes(scored), scored)
    serialized = serialize_llm_payload(payload, 100_000)
    schema = json.dumps(build_risk_output_schema(
        payload["llmRiskEpisodes"], hard_max=hard_max), ensure_ascii=False)
    wrapped = wrap_risk_block(RiskPromptBlock(
        serialized_text=serialized,
        content_hash=hashlib.sha256(serialized.encode()).hexdigest()[:16],
        compression_mode="FULL",
        exact_token_count=max(1, len(serialized) // 4)))
    total = (estimate_tokens(RISK_EXPOSURE_INSTRUCTION_BLOCK)
             + estimate_tokens(wrapped) + estimate_tokens(schema))
    if companion:
        total += estimate_tokens(RISK_EXPOSURE_COMPANION_NOTICE_BLOCK)
    return total


def main() -> int:
    # 표본: self 유형별 episode 구성·pairwise·비교 2기간·hard_max·oversize.
    configs = [
        ("specific_event_1ep", 1, 2, False),
        ("single_domain_2ep", 2, 2, False),
        ("period_overview_3ep", 3, 3, False),
        ("compare_2period_4ep", 4, 4, False),
        ("followup_1ep", 1, 2, False),
        ("pairwise_3ep", 3, 3, True),
        ("report_health_2ep", 2, 2, False),
        ("report_full_3ep", 3, 3, False),
        ("hard_max_4ep", 4, 4, False),
        ("oversized_8ep", 8, 4, False),
        ("oversized_12ep", 12, 4, False),
    ]
    values: list[int] = []
    print("== 위험 블록 부가 토큰(오프라인 보수 추정) ==")
    for name, n, hard, comp in configs:
        tokens = _risk_extra_tokens(n, hard_max=hard, companion=comp)
        values.append(tokens)
        print(f"  {name:22s} {tokens:6d} tok")
    values.sort()

    def pct(q: float) -> float:
        if len(values) == 1:
            return float(values[0])
        return float(statistics.quantiles(
            values, n=100, method="inclusive")[int(q) - 1])

    deterministic_max = max(values)
    report = {
        "p50": pct(50), "p95": pct(95), "p99": pct(99),
        "deterministic_max": deterministic_max,
        "reserve_current": 2_000,
        "reserve_sufficient_p95": pct(95) <= 2_000,
        "note": ("p95가 reserve를 초과하면 해당 call_type만 CALL_LIMITS"
                 " 개별 상향(docs/09 §8 개정+사용자 승인) 후 재실행."
                 " oversized 표본은 R2 hard cap 밖의 스트레스 상한 —"
                 " 운영 형태(≤hard_max)의 p95 기준으로 판단한다."),
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
