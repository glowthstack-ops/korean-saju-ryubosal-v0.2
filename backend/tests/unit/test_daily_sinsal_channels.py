"""docs/17 §22-9 — 신살 채널 8종(2026-09-18 4차, 데굴님 지시 "오늘의 운세에도 반영").

위험 엔진 P2 보조 증폭 층의 오늘의 운세 대응: 신살은 독립 트리거가 아니라 evidence 전용 보조
신호다. ①채널 정의가 만세력 신살 표와 일치 ②게이트 사용은 스키마가 거부 ③배선표 고정(표 밖
사건 참조 금지, 가중 ≤ .3) ④분류(taxonomy)에 '신살' family 가 정확히 배선 사건에만 붙는다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from saju_engines.daily_fortune_v2 import day_channels, load_catalog_v2, sinsal_channels
from saju_shared_types.daily_fortune import DayGanjiContext
from saju_shared_types.daily_fortune_v2 import (
    ALLOWED_CHANNEL_NAMES,
    SINSAL_CHANNELS,
    DailyEventModelV2,
)
from saju_shared_types.enums import Branch as B
from saju_shared_types.enums import Stem as S

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries" / "daily_fortune"

#: §22-9 배선표(evidence 전용) — 표 밖 사건은 신살 채널을 참조하지 않는다.
#: meet_helper·referral_received·praise_recognition·love_spark 는 .3→.2
#: (실험 B — 상위 집중 억제, §22-9 재측정).
WIRING: dict[str, dict[str, float]] = {
    "careless_injury_caution": {"sinsal_hazard": 0.3},
    "cut_burn_tool_caution": {"sinsal_hazard": 0.3},
    "fall_slip_caution": {"sinsal_hazard": 0.3},
    "sports_overuse_caution": {"sinsal_hazard": 0.2},
    "fire_electric_check_caution": {"sinsal_hazard": 0.2},
    "overconfidence_caution": {"sinsal_hazard": 0.2},
    "lost_item_caution": {"sinsal_loss": 0.3},
    "belongings_security_caution": {"sinsal_loss": 0.3},
    "account_phishing_caution": {"sinsal_loss": 0.2},
    "overspend_caution": {"sinsal_loss": 0.2},
    "lend_money_caution": {"sinsal_loss": 0.2},
    "guarantee_stamp_caution": {"sinsal_loss": 0.2},
    "rumor_caution": {"sinsal_loss": 0.2},
    "name_lending_caution": {"sinsal_loss": 0.2},
    "home_vehicle_lock_caution": {"sinsal_loss": 0.2},
    "meet_helper": {"sinsal_noble": 0.2},
    "referral_received": {"sinsal_noble": 0.2},
    "good_news_arrives": {"sinsal_noble": 0.2},
    "relief_news": {"sinsal_noble": 0.2},
    "unexpected_offer": {"sinsal_noble": 0.2},
    "trust_restored": {"sinsal_noble": 0.2},
    "misunderstanding_cleared": {"sinsal_noble": 0.2},
    "praise_recognition": {"sinsal_status": 0.2},
    "opinion_accepted": {"sinsal_status": 0.2},
    "work_smooth": {"sinsal_status": 0.2},
    "approval_resumes": {"sinsal_status": 0.2},
    "smooth_trip": {"sinsal_move": 0.3},
    "walk_refresh": {"sinsal_move": 0.2},
    "traffic_delay_caution": {"sinsal_move": 0.2},
    "travel_schedule_caution": {"sinsal_move": 0.2},
    "love_spark": {"sinsal_charm": 0.2},
    "pleasant_meeting": {"sinsal_charm": 0.2},
    "love_reunion": {"sinsal_charm": 0.2},
    "love_misread": {"sinsal_charm": 0.2},
    "rest_recharge": {"sinsal_retreat": 0.2},
    "tidy_luck": {"sinsal_retreat": 0.2},
    "rumination_caution": {"sinsal_retreat": 0.2, "sinsal_gwimun": 0.3},
    "emotion_rush_caution": {"sinsal_gwimun": 0.2},
    "misunderstanding_caution": {"sinsal_gwimun": 0.2},
    "sleep_recovery_caution": {"sinsal_gwimun": 0.2},
}


def test_channel_values_follow_the_engine_sinsal_tables() -> None:
    """일주 甲子(申子辰 水국) 기준 — 고전 12신살·양인·천을·귀문 표와 일치한다."""
    def ch(ds: S, db: B, mb: B = B.YU) -> dict[str, float]:
        return {k: v for k, v in sinsal_channels(S.GAP, B.JA, ds, db, mb).items() if v}

    assert ch(S.EUL, B.CHUK) == {"sinsal_noble": 1.0, "sinsal_status": 0.8}  # 천을(甲→丑)·반안
    assert ch(S.JEONG, B.MYO)["sinsal_hazard"] == 1.0  # 양인(甲→卯)
    assert ch(S.JEONG, B.MYO)["sinsal_loss"] == 0.6  # 육해(申子辰→卯)
    assert ch(S.GI, B.SA)["sinsal_loss"] == 1.0  # 겁살(申子辰→巳)
    assert ch(S.GAP, B.IN)["sinsal_move"] == 1.0  # 역마(申子辰→寅)
    assert ch(S.GYE, B.YU) == {"sinsal_charm": 1.0, "sinsal_gwimun": 1.0}  # 년살 酉·귀문 子酉
    # 금여(甲→辰)·백호 戊辰·화개 辰
    assert ch(S.MU, B.JIN) == {"sinsal_noble": 0.5, "sinsal_hazard": 0.6, "sinsal_retreat": 1.0}
    assert ch(S.GAP, B.JA) == {"sinsal_hazard": 0.4, "sinsal_status": 1.0}  # 현침 甲·장성 子
    # 천덕·월덕은 오늘의 월지 기준 — 월지 寅이면 丙 천간(월덕)이 .6.
    assert ch(S.BYEONG, B.SUL, B.IN)["sinsal_noble"] == 0.6
    # day_channels 에 전부 실리고 값은 0..1.
    ctx = DayGanjiContext(
        the_date=__import__("datetime").date(2026, 9, 21), day_stem="己", day_branch="巳",
        month_stem="丁", month_branch="酉", year_stem="丙", year_branch="午",
    )
    full = day_channels(S.GAP, B.JA, ctx)
    assert all(name in full and 0.0 <= full[name] <= 1.0 for name in SINSAL_CHANNELS)
    assert set(SINSAL_CHANNELS) <= ALLOWED_CHANNEL_NAMES


def test_sinsal_channels_are_evidence_only() -> None:
    """게이트(required_signature)에 신살 채널을 쓰면 스키마가 거부한다."""
    base = {"label": "x", "domain": "health", "valence": "caution", "slots": ["caution"],
            "prior": "중", "evidence": {"chung": 0.5}}
    with pytest.raises(ValidationError, match="게이트 금지"):
        DailyEventModelV2.model_validate({**base, "required_signature": "sinsal_hazard"})
    with pytest.raises(ValidationError, match="게이트 금지"):
        DailyEventModelV2.model_validate(
            {**base, "required_signature": ["or", "chung", "sinsal_loss"]})
    # evidence 로는 허용.
    DailyEventModelV2.model_validate({**base, "evidence": {"chung": 0.5, "sinsal_hazard": 0.3}})


def test_wiring_table_is_fixed_and_bounded() -> None:
    """배선표 고정 — 표 밖 사건 참조 금지, 가중 0 < w ≤ .3, 어떤 게이트도 신살을 쓰지 않는다."""
    for key, ev in load_catalog_v2().events.items():
        got = {c: w for c, w in ev.evidence.items() if c in SINSAL_CHANNELS}
        assert got == WIRING.get(key, {}), (key, got)
        for w in got.values():
            assert 0.0 < w <= 0.3, (key, w)
        leaves = set(json.dumps(ev.required_signature, ensure_ascii=False).split('"'))
        assert not leaves & set(SINSAL_CHANNELS), key
    assert len(WIRING) == 40


def test_taxonomy_marks_exactly_the_wired_events() -> None:
    tax = json.loads((_DICTS / "daily_event_taxonomy.json").read_text("utf-8"))
    assert "신살" in tax["vocabulary"]["evidence_family"]
    for key, t in tax["events"].items():
        field = "subject_evidence" if t["polarity"] == "good" else "adverse_evidence"
        assert ("신살" in t[field]) == (key in WIRING), key
        other = "adverse_evidence" if field == "subject_evidence" else "subject_evidence"
        assert "신살" not in t[other], key
