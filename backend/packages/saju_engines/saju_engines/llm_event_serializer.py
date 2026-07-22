"""EventCandidateV2 → LLM 입력 직렬화 (Phase 7c — 신 필드 풍부화).

구 계약(polarity·signals·evidence_path) 대신 재설계 출력 차원(quality·confidence_level·
temporal_mode·궁성·12운성 단계)을 한글 톤 힌트로 직렬화한다. LLM은 이 사실을 자연어로 설명만
하고 점수·간지·판정을 계산하지 않는다(절대 원칙 1·2). 단정 표현은 금기룰로 별도 차단한다.
"""

from __future__ import annotations

from saju_shared_types.event_engine import EventCandidateV2
from saju_shared_types.event_taxonomy_v2 import (
    CONFIDENCE_KO,
    PALACE_KO,
    PROHIBITIONS,
    QUALITY_KO,
    TEMPORAL_KO,
    event_display_ko,
)

# 사람에게 의미 있는 근거코드 접두어만 노출(내부 룰 id는 LLM 입력에서 변별만).
# specific-before-general: 더 좁은 접두어를 먼저 둬야 reason_codes_ko가 정확히 매칭한다
# (예: PROFILE_public_official_* 는 일반 PROFILE_ 보다 앞).
_REASON_PREFIX_KO: dict[str, str] = {
    # 직업운 결과 길흉(자료 9-3·9-4·9-6·12·13-1) — LLM이 자연어로 풀어 설명해야 할 '내용' 신호.
    "EXAM_PASS": "합격 기류",
    "EXAM_FAIL": "불합격 위험",
    "CAREER_EXIT": "퇴직·이탈 리스크",
    "CAREER_SPECIAL": "특수직군 길화",
    "JOBCHANGE_PRESSURE": "압박성 이직",
    "JOBCHANGE_OPPORTUNITY": "기회성 이직",
    "PROFILE_public_official": "공직 발령·전보",
    "REL_": "관계 발동",
    "FLOW_GEN": "상생 흐름",
    "FLOW_REVERSE": "역행 흐름",
    "REPEAT_": "반복 강화",
    "MIXED_": "혼합 신호",
    "GATE_": "현실 보정",
    "PROFILE_": "프로필 반영",
    "VOID_": "공망 지연",
    "YONGGI_": "용기신 품질",
    "SUPPRESS_": "신호 약화",
    "DIFFUSE_": "복수 가능성",
}

# 사용자 본문에 그대로 노출되면 안 되는 내부 분류 라벨(순화 대상 — 근거 경로 누출 방지).
# '상생/역행 흐름'과 직업운 결과 길흉 라벨은 LLM이 그대로 풀어 써야 할 '내용'이라 제외한다
# (나머지는 명백한 내부 용어 — 본문 노출 시 순화 대상).
_CONTENT_LABELS = frozenset({
    "상생 흐름", "역행 흐름",
    "합격 기류", "불합격 위험", "퇴직·이탈 리스크", "특수직군 길화",
    "압박성 이직", "기회성 이직", "공직 발령·전보",
})
INTERNAL_JARGON_LABELS: tuple[str, ...] = tuple(
    ko
    for ko in dict.fromkeys(_REASON_PREFIX_KO.values())
    if ko not in _CONTENT_LABELS
)

# event_key → 금기룰 설명(있으면 LLM 입력에 톤 제한으로 부착).
_PROHIBITION_BY_KEY: dict[str, list[str]] = {}
for _rid, _desc, _keys in PROHIBITIONS:
    for _k in _keys:
        _PROHIBITION_BY_KEY.setdefault(_k, []).append(_desc)


def reason_codes_ko(reason_codes: list[str]) -> list[str]:
    """근거코드 목록 → 사람용 한글 분류(중복 제거, 순서 보존)."""
    out: list[str] = []
    for code in reason_codes:
        for prefix, ko in _REASON_PREFIX_KO.items():
            if code.startswith(prefix):
                if ko not in out:
                    out.append(ko)
                break
    return out


def prohibitions_for(event_key: str) -> list[str]:
    """이벤트 키에 부착된 금기 표현 규칙(없으면 빈 목록)."""
    return list(_PROHIBITION_BY_KEY.get(event_key, []))


def score_band(score: int) -> str:
    """display_score → 거친 신호 강도 밴드(절대 점수 노출 대신 — LIFE_EVENT_INFERENCE §6)."""
    if score >= 75:
        return "강"
    if score >= 50:
        return "중"
    return "약"


def serialize_candidate_v2(c: EventCandidateV2) -> dict[str, object]:
    """후보 1건을 LLM 입력용 한글 톤 힌트 dict로 직렬화한다.

    1차 신호는 사건화 강도(confidence)·길흉(quality)·현실 적합(life_fit)이며, score는 절대값 대신
    거친 밴드(강/중/약)로만 노출한다(표시용 격하 — 절대 점수 신뢰 금지).
    """
    return {
        # 방향 인지 라벨(2026-07-22 P2) — '횡재+손실' 류 모순 차단(판정·점수 불변).
        "event_ko": event_display_ko(
            str(c.event_key), c.quality.value if c.quality else None,
        ),
        "period": c.period,
        "confidence_ko": CONFIDENCE_KO.get(c.confidence_level, ""),
        "quality_ko": QUALITY_KO.get(c.quality, "") if c.quality else "",
        "temporal_ko": TEMPORAL_KO.get(c.temporal_mode, "") if c.temporal_mode else "",
        "palace_ko": PALACE_KO.get(c.palace, "") if c.palace else "",
        "phase": c.event_phase or "",
        "score_band": score_band(c.score),  # 표시용 — 절대 점수 대신 강/중/약
        "personal_pattern": c.personal_match > 0,  # 과거 패턴 일치(있으면 우선 서술 근거)
        "signals_ko": reason_codes_ko(c.reason_codes),
        "prohibitions": prohibitions_for(str(c.event_key)),
    }
