"""MT1 일간 干合 awareness Seed Producer 단위 테스트 (MARRIAGE_TIMING_ENHANCEMENT §6).

핵심 검증: ① 干合+배우자성이면 new_relationship awareness seed 생성 ② 비배우자성·비干合 미발동
③ 합거·기신 = 불안정 분기(risk_flag, 미발동 아님) ④ gender 미상 = 양 기준 + 점수·confidence 하향
⑤ 생성 범위가 new_relationship + awareness로 하드 제한(marriage/commitment 직접 생성 금지).

일간의 干合 대상은 음간이면 官(여=배우자성)·양간이면 財(남=배우자성)이다 — 고정 생일:
丁(음, 06-01)·甲(양, 06-08).
"""

from __future__ import annotations

from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.marriage_awareness_seed import produce_mt1_awareness_seeds
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import ConfidenceLevel, EventKeyV2
from saju_shared_types.luck import LuckPillar

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"

# 干合 짝(천간 5합).
_HAP = {"甲": "己", "己": "甲", "乙": "庚", "庚": "乙", "丙": "辛",
        "辛": "丙", "丁": "壬", "壬": "丁", "戊": "癸", "癸": "戊"}


def _result(date: str, gender: str = "female"):
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date, birth_time="10:00",
        birth_place_name="서울", gender=gender,
    ))


def _luck(stem: str, branch: str = "子", label: str = "2026") -> LuckPillar:
    """테스트용 운 기둥 — 천간만 의미가 있다(干合 판정)."""
    return LuckPillar(
        label=label, period_type="year", ganji=f"{stem}{branch}",
        stem=stem, branch=branch, stem_ten_god="", branch_ten_god="",
    )


def test_fires_for_yin_daymaster_female() -> None:
    """음간 일간(丁) 여명 + 干合 천간(壬=정관) → awareness seed 1건(점수 40)."""
    r = _result("1990-06-01", "female")  # 丁 일간
    assert r.pillars is not None and r.pillars.day.stem == "丁"
    seeds = produce_mt1_awareness_seeds(_luck("壬"), r, {}, "female", "2026")
    assert len(seeds) == 1
    s = seeds[0]
    assert s.event_key is EventKeyV2.NEW_RELATIONSHIP
    assert s.score == 40  # base 30 + partner_star confirmed 10
    assert "MT1_DAY_STEM_HAP_PARTNER" in s.reason_codes
    assert "MT1_STAGE_AWARENESS" in s.reason_codes
    assert "MT1_PARTNER_STAR_CONFIRMED" in s.reason_codes
    assert "MT1_PARTNER_STAR_PROPER" in s.reason_codes  # 정관 = 正
    assert s.confidence_level is ConfidenceLevel.WEAK_EVENT_CANDIDATE
    assert s.period == "2026"


def test_fires_for_yang_daymaster_male() -> None:
    """양간 일간(甲) 남명 + 干合 천간(己=정재) → awareness seed 생성."""
    r = _result("1990-06-08", "male")  # 甲 일간
    assert r.pillars is not None and r.pillars.day.stem == "甲"
    seeds = produce_mt1_awareness_seeds(_luck("己"), r, {}, "male", "2026")
    assert len(seeds) == 1
    assert seeds[0].event_key is EventKeyV2.NEW_RELATIONSHIP
    assert seeds[0].score == 40


def test_no_fire_wrong_gender_partner_star() -> None:
    """양간 일간(甲) + 干合(己=정재)인데 gender=female이면 배우자성 불일치 → 미발동."""
    r = _result("1990-06-08", "female")  # 甲 일간, 干合 짝 己=정재(여명 배우자성 아님)
    seeds = produce_mt1_awareness_seeds(_luck("己"), r, {}, "female", "2026")
    assert seeds == []


def test_no_fire_when_not_combining() -> None:
    """干合하지 않는 운 천간(丁일간에 甲)은 미발동."""
    r = _result("1990-06-01", "female")  # 丁 일간(干合 짝은 壬)
    assert _HAP["丁"] == "壬"
    seeds = produce_mt1_awareness_seeds(_luck("甲"), r, {}, "female", "2026")
    assert seeds == []


def test_unknown_gender_dual_rule_lowered() -> None:
    """gender 미상 — 양 기준 검사로 발동하되 점수(≤35)·confidence 하향."""
    r = _result("1990-06-01", "unknown")  # 丁 일간, 壬=정관(관살)이라 미상에서도 인정
    seeds = produce_mt1_awareness_seeds(_luck("壬"), r, {}, "unknown", "2026")
    assert len(seeds) == 1
    s = seeds[0]
    assert "UNKNOWN_GENDER_DUAL_RULE" in s.reason_codes
    assert "MT1_PARTNER_STAR_CONFIRMED" not in s.reason_codes
    assert s.score <= 35
    assert s.confidence_level is ConfidenceLevel.THEME_ONLY


def test_gisin_branch_is_unstable_not_silent() -> None:
    """기신 동반 — 미발동이 아니라 risk_flag(MT1_GISIN_RISK)를 달고 awareness 생성."""
    r = _result("1990-06-01", "female")  # 丁 일간, 운 천간 壬=水
    seeds = produce_mt1_awareness_seeds(_luck("壬"), r, {"水": "기신"}, "female", "2026")
    assert len(seeds) == 1
    assert "MT1_GISIN_RISK" in seeds[0].reason_codes


def test_only_generates_new_relationship_awareness() -> None:
    """생성 범위 하드 제한 — event는 new_relationship, stage는 awareness만(승급 신호 없음)."""
    r = _result("1990-06-01", "female")
    seeds = produce_mt1_awareness_seeds(_luck("壬"), r, {}, "female", "2026")
    assert len(seeds) == 1
    s = seeds[0]
    assert s.event_key is EventKeyV2.NEW_RELATIONSHIP
    # marriage/commitment/formalization 등 승급 단계 reason_code 부재.
    forbidden = {"commitment", "formalization", "marriage", "family_expansion", "relationship"}
    assert not any(f in rc.lower() for rc in s.reason_codes for f in forbidden)


def test_no_pillars_returns_empty() -> None:
    """pillars 부재(graceful) — 빈 목록. calculate는 LRU 캐시라 복사본을 변형한다."""
    r = _result("1990-06-01", "female").model_copy(update={"pillars": None})
    assert produce_mt1_awareness_seeds(_luck("壬"), r, {}, "female", "2026") == []


# ── 엔진 통합 (feature flag) ─────────────────────────────────────────


def test_engine_flag_off_is_inert() -> None:
    """feature OFF(기본) — MT1 후보가 전혀 생기지 않고 결과 개수가 불변(완전 비활성)."""
    r = _result("1990-06-01", "female")  # 丁 일간
    years = list(range(2020, 2034))
    off = EventEngineV2(_DICTS).score_years(r, years)  # 기본 OFF
    on = EventEngineV2(_DICTS, enable_mt1_awareness=True).score_years(r, years)
    assert not any("MT1_DAY_STEM_HAP_PARTNER" in c.reason_codes for c in off)
    # ON은 정확히 MT1 seed만큼만 증가(나머지 파이프라인 불변).
    mt1 = [c for c in on if "MT1_DAY_STEM_HAP_PARTNER" in c.reason_codes]
    assert mt1 and len(on) == len(off) + len(mt1)


def test_engine_flag_on_fires_on_combine_year() -> None:
    """feature ON — 丁 일간에 壬년(干合·정관)에서 new_relationship awareness 후보가 발동."""
    r = _result("1990-06-01", "female")
    on = EventEngineV2(_DICTS, enable_mt1_awareness=True).score_years(r, [2022, 2032])
    mt1 = [c for c in on if "MT1_DAY_STEM_HAP_PARTNER" in c.reason_codes]
    assert {c.period for c in mt1} == {"2022", "2032"}  # 壬寅·壬子
    for c in mt1:
        assert c.event_key is EventKeyV2.NEW_RELATIONSHIP
        assert "MT1_STAGE_AWARENESS" in c.reason_codes
        assert c.confidence_level is ConfidenceLevel.THEME_ONLY  # awareness = 낮은 확신
