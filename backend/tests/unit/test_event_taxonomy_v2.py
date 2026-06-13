"""21키 taxonomy 부속 테이블·직렬화 검증 (Phase 7c 타깃 계층).

라벨·카테고리·도메인의 21키 완전성, 구키 매핑 전수, 금기룰(경쟁 보호 포함), 직렬화를 확인한다.
"""

from __future__ import annotations

from saju_engines.llm_event_serializer import (
    prohibitions_for,
    reason_codes_ko,
    serialize_candidate_v2,
)
from saju_shared_types.event_engine import (
    ConfidenceLevel,
    EventCandidateV2,
    EventKeyV2,
    EventQuality,
    Pillar4,
)
from saju_shared_types.event_taxonomy_v2 import (
    EVENT_DOMAIN,
    EVENT_KO,
    EVENT_TYPE,
    EVENT_WORDS,
    LEGACY_EVENT_KEY_MAP,
)


def test_all_21_keys_labelled() -> None:
    for k in EventKeyV2:
        assert k in EVENT_KO and EVENT_KO[k]
        assert k in EVENT_TYPE and EVENT_TYPE[k] in ("progress", "instant", "hybrid")
        assert k in EVENT_DOMAIN
        # preparation_delay는 엔진 도출 전용(질의 키워드 없음).
        if k is not EventKeyV2.PREPARATION_DELAY:
            assert k in EVENT_WORDS


def test_legacy_map_covers_25_keys_and_targets_valid() -> None:
    # 구 EventKey 25종 전부 매핑 + 타깃은 모두 유효한 EventKeyV2.
    assert len(LEGACY_EVENT_KEY_MAP) == 25
    assert all(isinstance(v, EventKeyV2) for v in LEGACY_EVENT_KEY_MAP.values())
    # 손실성 매핑 확정값.
    assert LEGACY_EVENT_KEY_MAP["resignation"] is EventKeyV2.CAREER_CHANGE
    assert LEGACY_EVENT_KEY_MAP["family_change"] is EventKeyV2.RELATIONSHIP_CHANGE
    assert LEGACY_EVENT_KEY_MAP["travel"] is EventKeyV2.RELOCATION
    assert LEGACY_EVENT_KEY_MAP["speculation_risk"] is EventKeyV2.WEALTH_CHANGE


def test_competition_and_exam_keywords() -> None:
    # 실로그 최다 유형: 진급·평가·오디션·대회·고시·자격증.
    assert "진급" in EVENT_WORDS[EventKeyV2.PROMOTION]
    assert "평가" in EVENT_WORDS[EventKeyV2.PROMOTION]
    assert "오디션" in EVENT_WORDS[EventKeyV2.PUBLIC_EXPOSURE]
    assert "대회" in EVENT_WORDS[EventKeyV2.PUBLIC_EXPOSURE]
    assert "국가고시" in EVENT_WORDS[EventKeyV2.EDUCATION_ADMISSION]
    assert "자격증" in EVENT_WORDS[EventKeyV2.EDUCATION_ADMISSION]


def test_prohibitions_cover_competition_and_exam() -> None:
    assert prohibitions_for("public_exposure"), "경쟁(오디션·대회·선거) 승부 단정 금지 필요"
    assert prohibitions_for("education_admission"), "합격·당락 단정 금지 필요"
    assert prohibitions_for("windfall")
    assert prohibitions_for("health_attention")
    assert not prohibitions_for("relocation")  # 금기 없는 키


def test_reason_codes_ko_dedup() -> None:
    out = reason_codes_ko(["REL_HAP_month_pillar", "REL_CHUNG_day_pillar", "FLOW_GEN"])
    assert out == ["관계 발동", "상생 흐름"]


def test_serialize_enriched_fields() -> None:
    c = EventCandidateV2(
        event_key=EventKeyV2.EDUCATION_ADMISSION, period="2026", score=80,
        confidence_level=ConfidenceLevel.STRONG_EVENT_CANDIDATE,
        quality=EventQuality.ACHIEVEMENT, palace=Pillar4.HOUR,
        reason_codes=["REL_HAP_hour_pillar", "YONGGI_YONG"],
    )
    d = serialize_candidate_v2(c)
    assert d["event_ko"] == "합격·진학·자격"
    assert d["confidence_ko"] == "강한 사건 후보"
    assert d["quality_ko"] == "성취·인정"
    assert d["palace_ko"].startswith("시주")
    assert "관계 발동" in d["signals_ko"]
    assert d["prohibitions"]  # 당락 단정 금지 부착
