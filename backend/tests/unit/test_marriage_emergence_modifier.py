"""MT2 일지 투출 글자 운 회귀 증폭 modifier 단위 테스트 (MARRIAGE_TIMING_ENHANCEMENT §7).

핵심 검증: ① 증폭형 — 후보를 절대 생성하지 않고 기존 관계 후보만 보강 ② same_stem > same_element
2종 차등(천간↔십성 1:1이라 same_ten_god 티어 없음) ③ 배우자성 회귀만 강하게·비배우자성/일간 투출은
약하게 ④ same_element는 stage 승급 없음(증폭만) ⑤ spouse_palace_clashed면 marriage_signal 긍정
증폭 금지.
"""

from __future__ import annotations

from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.marriage_emergence_modifier import (
    EmergedStem,
    MarriageEmergenceModifier,
    MarriageEmergenceNatal,
    analyze_marriage_emergence_natal,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import EventCandidateV2, EventKeyV2

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _es(stem: str, element: str, ten_god: str, *, ps: bool, dm: bool = False) -> EmergedStem:
    return EmergedStem(
        stem=stem, element=element, ten_god=ten_god, source_pillars=("month",),
        is_day_master_exposure=dm, is_partner_star=ps,
    )


def _natal(*emerged: EmergedStem, day_master: str = "癸") -> MarriageEmergenceNatal:
    return MarriageEmergenceNatal(day_master=day_master, emerged=emerged, gender="female")


def _cand(key: EventKeyV2, score: int = 40) -> EventCandidateV2:
    return EventCandidateV2(event_key=key, period="2029", score=score)


def _nr(
    natal: MarriageEmergenceNatal, luck_stem: str, *, clashed: bool = False, score: int = 40
) -> list[EventCandidateV2]:
    """new_relationship 후보 1건에 MT2 modifier를 적용해 반환(줄 길이 헬퍼)."""
    return MarriageEmergenceModifier.apply(
        [_cand(EventKeyV2.NEW_RELATIONSHIP, score)], natal, luck_stem, clashed
    )


def test_same_stem_partner_star_amplifies() -> None:
    """배우자성 투출 글자(己=편관)가 정확 회귀 → new_relationship +10, same_stem 근거."""
    natal = _natal(_es("己", "土", "편관", ps=True))  # 癸 일간, 己=편관(여=관살)
    out = _nr(natal, "己")
    assert len(out) == 1
    assert out[0].score == 50  # 40 + 10
    assert "MT2_EMERGENCE_SAME_STEM" in out[0].reason_codes


def test_same_element_is_weaker_background() -> None:
    """같은 오행 짝(戊=土, 글자 다름) 회귀 → same_element 약한 배경(+4)."""
    natal = _natal(_es("己", "土", "편관", ps=True))
    out = _nr(natal, "戊")
    assert out[0].score == 44  # 40 + 4 (partner same_element)
    assert "MT2_EMERGENCE_SAME_ELEMENT" in out[0].reason_codes


def test_non_partner_return_is_weak() -> None:
    """비배우자성 투출 글자(庚=정재) 정확 회귀 → 약하게(+5)만."""
    natal = _natal(_es("庚", "金", "정재", ps=False))
    out = _nr(natal, "庚")
    assert out[0].score == 45  # non-partner same_stem +5


def test_day_master_exposure_tagged_weak() -> None:
    """일간 자기 투출은 partner_star 아님 + MT2_DAY_MASTER_EXPOSURE 태그(weak)."""
    natal = _natal(_es("癸", "水", "비견", ps=False, dm=True))
    out = _nr(natal, "癸")
    assert "MT2_DAY_MASTER_EXPOSURE" in out[0].reason_codes
    assert out[0].score == 45  # non-partner same_stem


def test_never_creates_candidates() -> None:
    """증폭형 — 회귀가 있어도 후보 개수는 불변(신규 생성 금지)."""
    natal = _natal(_es("己", "土", "편관", ps=True))
    cands = [_cand(EventKeyV2.NEW_RELATIONSHIP), _cand(EventKeyV2.CAREER_CHANGE)]
    out = MarriageEmergenceModifier.apply(cands, natal, "己", False)
    assert len(out) == len(cands)
    # 비관계 후보(career)는 무영향.
    career = next(c for c in out if c.event_key is EventKeyV2.CAREER_CHANGE)
    assert career.score == 40 and not any("MT2" in rc for rc in career.reason_codes)


def test_no_return_leaves_unchanged() -> None:
    """회귀가 없으면(운 천간이 투출 글자/오행과 무관) 후보 불변."""
    natal = _natal(_es("己", "土", "편관", ps=True))
    out = _nr(natal, "甲")
    assert out[0].score == 40 and not any("MT2" in rc for rc in out[0].reason_codes)


def test_same_element_no_stage_promotion() -> None:
    """same_element 회귀는 event_key를 바꾸거나 승급시키지 않는다(증폭만)."""
    natal = _natal(_es("己", "土", "편관", ps=True))
    out = _nr(natal, "戊")
    assert out[0].event_key is EventKeyV2.NEW_RELATIONSHIP  # marriage_signal로 승급 안 됨
    assert len(out) == 1


def test_clashed_does_not_amplify_marriage_signal() -> None:
    """spouse_palace_clashed면 marriage_signal 긍정 증폭 금지 + 충 분기 태그."""
    natal = _natal(_es("己", "土", "편관", ps=True))
    ms = _cand(EventKeyV2.MARRIAGE_SIGNAL, 50)
    out = MarriageEmergenceModifier.apply([ms], natal, "己", True)
    assert out[0].score == 50  # 증폭 없음
    assert "MT2_EMERGENCE_CLASHED" in out[0].reason_codes
    assert "SPOUSE_PALACE_CLASHED" in out[0].reason_codes


def test_clashed_new_relationship_keeps_evidence_no_boost() -> None:
    """충 동반 — new_relationship도 근거(태그)는 남기되 긍정 점수 증폭은 하지 않는다."""
    natal = _natal(_es("己", "土", "편관", ps=True))
    out = _nr(natal, "己", clashed=True)
    assert out[0].score == 40  # delta 0
    assert "MT2_EMERGENCE_CLASHED" in out[0].reason_codes


# ── 원국 분석 + 엔진 통합 ────────────────────────────────────────────


def test_analyze_detects_partner_star_emergence() -> None:
    """1985-03-15(癸 일간 여명)은 己(편관·배우자성) 투출 + 癸(일간 자기 투출)을 검출."""
    r = calculate(BirthInput(
        calendar_type="solar", birth_date="1985-03-15", birth_time="10:00",
        birth_place_name="서울", gender="female",
    ))
    n = analyze_marriage_emergence_natal(r)
    by_stem = {e.stem: e for e in n.emerged}
    assert "己" in by_stem and by_stem["己"].is_partner_star and by_stem["己"].ten_god == "편관"
    assert "癸" in by_stem and by_stem["癸"].is_day_master_exposure


def test_engine_flag_off_is_inert() -> None:
    """feature OFF(기본) — MT2 태그가 전혀 없고 결과가 불변."""
    r = calculate(BirthInput(
        calendar_type="solar", birth_date="1985-03-15", birth_time="10:00",
        birth_place_name="서울", gender="female",
    ))
    years = list(range(2025, 2035))
    off = EventEngineV2(_DICTS).score_years(r, years)
    on = EventEngineV2(_DICTS, enable_mt2_emergence=True).score_years(r, years)
    assert not any(any("MT2_EMERGENCE" in rc for rc in c.reason_codes) for c in off)
    # 증폭형이라 후보 개수는 ON/OFF 동일(생성 없음).
    assert len(on) == len(off)
    assert any(any("MT2_EMERGENCE" in rc for rc in c.reason_codes) for c in on)
