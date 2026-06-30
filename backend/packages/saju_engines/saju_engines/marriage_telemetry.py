"""Marriage Production Readiness v1 — Step 6: 익명 결혼 신호 텔레메트리.

오픈 이후 실제 사용자 케이스로 calibration하려면 지금부터 로그 구조가 있어야 한다(개인정보 미저장,
익명 집계만). 어떤 stage가 많이 뜨는지·MT4 apply 시 순위가 얼마나 바뀌는지(shadow diff)·가드가
어떻게 걸리는지를 집계한다. **PII(생년월일·이름·owner_id) 미포함** — 도메인/프로파일/단계/코드만.

`build_marriage_telemetry`는 순수 함수(집계 dict 생성), `emit_marriage_telemetry`는 logging으로
debug-only 방출(결과 payload·LLM 입력 미포함 — 별도 채널). 답변 경로가 MT 활성일 때만 호출한다.
"""

from __future__ import annotations

import json
import logging

_LOG = logging.getLogger("saju.marriage_telemetry")
_RELATIONSHIP_EVENTS = frozenset({"new_relationship", "marriage_signal", "relationship_change"})
_TOP_N = 5


def build_marriage_telemetry(
    profile: str,
    enabled_features: list[str],
    candidates: list,
    mt4_shadow: list[dict] | None = None,
    *,
    surface: str = "",
    relationship_context: str = "unknown",
) -> dict:
    """관계 후보·MT4 shadow를 익명 집계 dict로 만든다(PII 없음).

    Args:
        profile: 활성 MT 프로파일명.
        enabled_features: 켜진 MT 기능 목록(['MT1','MT2','MT3','MT4_shadow','MT6'] 등).
        candidates: LlmEventCandidate 류(event_key/marriage_stage/score/marriage_stage_reason 보유).
        mt4_shadow: EventEngineV2.mt4_shadow(없으면 빈 집계).
        surface: 'chat'/'report' 등(선택).
        relationship_context: 'single'/'dating'/'married'/'unknown'.

    Returns:
        익명 집계 dict(생년월일·식별자 미포함).
    """
    rel = [
        c for c in candidates
        if str(getattr(c, "event_key", "")) in _RELATIONSHIP_EVENTS
        and bool(getattr(c, "marriage_stage", None))
    ]
    rel_sorted = sorted(rel, key=lambda c: -int(getattr(c, "score", 0)))
    top_events = [
        {
            "event": str(c.event_key),
            "stage": c.marriage_stage,
            "score": int(getattr(c, "score", 0)),
            "reason_codes": list(getattr(c, "marriage_stage_reason", []))[:6],
        }
        for c in rel_sorted[:_TOP_N]
    ]
    shadow = mt4_shadow or []
    mt4_diff = round(sum(float(d.get("relation_mt4_diff", 0.0)) for d in shadow), 2)
    stages = sorted({c.marriage_stage for c in rel})
    return {
        "query_domain": "marriage_timing",
        "surface": surface,
        "profile": profile,
        "enabled_features": list(enabled_features),
        "relationship_context": relationship_context,
        "relationship_candidate_count": len(rel),
        "stages_present": stages,
        "top_events": top_events,
        "mt4_shadow_diff": mt4_diff,
        "mt4_shadow_entries": len(shadow),
    }


def emit_marriage_telemetry(payload: dict) -> None:
    """익명 집계를 debug 로그로 방출(결과·LLM 입력 미포함, 별도 채널). 실패해도 답변에 영향 없음."""
    try:
        _LOG.info("marriage_telemetry %s", json.dumps(payload, ensure_ascii=False, sort_keys=True))
    except (TypeError, ValueError):  # 직렬화 실패 — 텔레메트리는 답변을 막지 않는다.
        _LOG.debug("marriage_telemetry serialize skipped")
