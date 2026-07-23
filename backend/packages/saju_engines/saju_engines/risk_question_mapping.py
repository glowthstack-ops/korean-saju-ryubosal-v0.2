"""질문 파서 → 위험 노출 질문 컨텍스트 매핑 R5 (감수 50차 §9-① — SSOT).

새 분류기를 만들지 않는다 — 기존 query_parser의 IntentJson(정본)에서만
매핑한다. **fail-closed**: 미등록 질문 유형·불명확한 시간 범위(TIMELESS·
LIFE_STAGE)·미래 범위 산출 실패(time_range 부재)·과거 회고 전부 None →
게이트 BYPASS(guard조차 없음). episode_followup은 저장된 canonical
episode ID가 있을 때만 허용(문자열 유사도 추정 금지 — canary 2차 확대
전까지 미매핑).
"""

from __future__ import annotations

from saju_shared_types.intent import Domain, IntentJson, QueryType, TimeScope

__all__ = ["map_intent_to_exposure_question"]

# QueryType → 노출 질문 유형(감수 50차 — 보수 매핑: 초기 canary 3유형만.
# COMPARISON→multi_episode_compare는 정의만 두고 canary allowlist가 차단,
# TIMING_SEARCH(좋은 시기 탐색)는 위험 주입 적합성 별도 감수 전 미매핑).
_QUERY_TYPE_MAP: dict[QueryType, str] = {
    QueryType.FORTUNE_OVERVIEW: "period_overview",
    QueryType.DOMAIN_ANALYSIS: "single_domain_period",
    QueryType.EVENT_EXPLANATION: "specific_event",
    QueryType.DECISION_SUPPORT: "specific_event",
    QueryType.COMPARISON: "multi_episode_compare",
}
# TimeScope → temporal scope(불명확=매핑 없음 → fail-closed).
_TIME_SCOPE_MAP: dict[TimeScope, str] = {
    TimeScope.LONG_TERM: "future",
    TimeScope.MID_TERM: "future",
    TimeScope.SHORT_TERM: "future",
    TimeScope.DATE_LEVEL: "future",
    TimeScope.DAEWOON_UNIT: "future",
    TimeScope.PAST: "past_only",
}
# 파서 Domain → 위험 도메인(risk 7도메인 어휘) — general은 무제약.
_DOMAIN_MAP: dict[Domain, str] = {
    Domain.CAREER: "career",
    Domain.RELATIONSHIP: "relationship",
    Domain.RELOCATION: "relocation",
    Domain.WEALTH: "finance",
    Domain.HEALTH: "health_safety",
    Domain.EDUCATION: "selection",
}


def _period_label_ok(label: str) -> bool:
    """미래 범위 라벨 **형식 검증**(YYYY/YYYY-MM만 — 그 외=산출 실패).

    감수 51차 §1-3 불변식: 본 모듈은 시간 라벨을 **재해석하지 않는다**
    ("향후 1년"·"하반기" 류의 regex 파싱 0) — 시간 파서(SSOT)가 정규화한
    절대 날짜만 받아 형식을 확인하고, 정규화 실패는 그대로 BYPASS.
    """
    if len(label) == 4 and label.isdigit():
        return True
    return (len(label) == 7 and label[4] == "-"
            and label[:4].isdigit() and label[5:7].isdigit())


def map_intent_to_exposure_question(
    intent: IntentJson,
    stored_episode_keys: tuple[tuple[str, str, str], ...] = (),
) -> dict | None:
    """IntentJson → 노출 게이트 질문 컨텍스트(감수 50차 — SSOT·fail-closed).

    반환: {"question_type", "temporal_scope", "future_period_range",
    "target_domains"(+"episode_key")} 또는 **None**(매핑 불가 — 게이트
    BYPASS). None 사유: 미등록 query_type·불명확 time_scope(TIMELESS/
    LIFE_STAGE 등)·미래 질문의 time_range 부재/라벨 비정형·subject가
    본인 단독이 아닌 질문(동반자 위험 노출은 별도 감수 전 금지).

    감수 62차 확대:
    - TIMING_SEARCH 분기: 명확한 도메인 1개=single_domain_period, 일반
      총운형=period_overview(전 도메인 위험 3건이 "언제 취업?"류에 실리는
      것 방지). time_range 부재는 기존과 동일하게 BYPASS.
    - episode_followup: stored_episode_keys((key, domain, period) — 직전
      위험 답변 DELIVER 시 저장분)와 도메인·기간이 **정확히 1건으로
      결정적 해소**될 때만. 유사도 추정 금지 — 해소 실패=원 유형 유지.
    """
    question_type = _QUERY_TYPE_MAP.get(intent.query_type)
    if question_type is None and intent.query_type is QueryType.TIMING_SEARCH:
        # TIMING_SEARCH 분기(감수 62차) — 도메인 인식 여부로 예산 유형 결정.
        effective = [d for d in (intent.domains or [intent.domain])
                     if d.value != "general"]
        question_type = ("single_domain_period"
                         if len(set(effective)) == 1 else "period_overview")
    if question_type is None:
        return None
    temporal = _TIME_SCOPE_MAP.get(intent.time_scope)
    if temporal is None:
        return None  # TIMELESS·LIFE_STAGE·HOUR_LEVEL 등 — 불명확=fail-closed
    if intent.subject_mode.value != "single":
        return None  # 동반자·비교 대상 위험 노출은 별도 감수 전 금지
    # 감수 51차 §1-1: DOMAIN_ANALYSIS는 intent 이름이 아니라 **도메인이
    # 정확히 1개**일 때만 single_domain_period — 0개·2개 이상=BYPASS
    # ("직업과 재물운 같이" 류에 단일 도메인 budget 적용 금지).
    if question_type == "single_domain_period":
        effective_domains = [d for d in (intent.domains or [intent.domain])
                             if d.value != "general"]
        if len(set(effective_domains)) != 1:
            return None
    # 감수 51차 §1-2 + 52차 §1: specific_event는 **해소된 target**이 있을
    # 때만. event_key는 자유 문자열이 아니라 EventKey **enum**(사건형 21종
    # — 성향·개념·처방 항목이 없는 폐쇄 어휘)이므로 별도 allowlist 없이
    # enum 존재=eligible로 완료 처리(감수 52차 승인 조건). 파서 enum에
    # 비사건형 키가 추가되면 이 지점에 명시 allowlist를 도입해야 한다.
    if question_type == "specific_event":
        if intent.event_key is None and not intent.event_keys:
            return None
    future_range: tuple[str, str] | None = None
    if temporal == "future":
        tr = intent.time_range
        if tr is None or not tr.start or not tr.end:
            return None  # 미래 범위 산출 실패 — fail-closed
        start, end = str(tr.start)[:7], str(tr.end)[:7]
        if not (_period_label_ok(start[:4]) or _period_label_ok(start)):
            return None
        if not (_period_label_ok(end[:4]) or _period_label_ok(end)):
            return None
        # 라벨 정규화: YYYY-MM-DD → YYYY-MM. boundary 정책(감수 52차 §1):
        # 범위 의미는 시간 파서 SSOT가 확정한 [start, end] 그대로 —
        # 본 모듈은 검사만 하고 날짜를 보정·확장하지 않는다.
        start = start if _period_label_ok(start) else start[:4]
        end = end if _period_label_ok(end) else end[:4]
        future_range = (start, end)
    domains = []
    for d in (intent.domains or [intent.domain]):
        mapped = _DOMAIN_MAP.get(d)
        if mapped:
            domains.append(mapped)
    out: dict = {
        "question_type": question_type,
        "temporal_scope": temporal,
        "future_period_range": future_range,
        "target_domains": tuple(sorted(set(domains))),
    }
    # episode_followup 결정적 해소(감수 62차) — specific_event 계열 질문이
    # 저장된 canonical episode 키와 (도메인 일치 + 기간 겹침) **정확히
    # 1건**으로 해소될 때만 승격. 0건·복수건=원 유형 유지(fail-closed).
    if question_type == "specific_event" and stored_episode_keys \
            and future_range is not None:
        lo, hi = future_range[0][:4], future_range[1][:4]
        matches = [
            key for (key, dom, period) in stored_episode_keys
            if (not out["target_domains"] or dom in out["target_domains"])
            and lo <= str(period)[:4] <= hi]
        if len(set(matches)) == 1:
            out["question_type"] = "episode_followup"
            out["episode_key"] = matches[0]
    return out
