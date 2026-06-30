"""MT4 관계 도메인 HAP 합 종류(subtype) 재가중 테스트 (MARRIAGE_TIMING_ENHANCEMENT §9).

핵심 검증: ① multiplier 테이블(육합1.0>삼합0.85>방합0.70/0.75/0.80, unknown 1.0) ② gender 미상은
partnerElement 완화(0.80) 미적용 ③ off==shadow 결과 byte 불변(점수·reason) + shadow 진단만 기록
④ apply는 상향 없음(≤기존)·관계 도메인 한정.
"""

from __future__ import annotations

from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.marriage_hap_subtype import mt4_subtype_multiplier, partner_elements
from saju_shared_types.birth_input import BirthInput

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _r(date: str = "1985-03-15", gender: str = "female"):
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date, birth_time="10:00",
        birth_place_name="서울", gender=gender,
    ))


# ── 순수 함수: multiplier 테이블 ─────────────────────────────────────


def _mult(sub: str | None, *, sp: bool = False, pe: bool = False) -> float:
    return mt4_subtype_multiplier(sub, on_spouse_palace=sp, partner_element=pe)[0]


def test_multiplier_table() -> None:
    assert _mult("six_harmony") == 1.00
    assert _mult("three_harmony", sp=True, pe=True) == 0.85
    assert _mult("directional") == 0.70
    assert _mult("directional", sp=True) == 0.75
    assert _mult("directional", sp=True, pe=True) == 0.80


def test_multiplier_never_above_one() -> None:
    """상향 보정 없음 — 모든 multiplier ≤ 1.0(포화 방지)."""
    for sub in ("six_harmony", "three_harmony", "directional", "stem", None, "bogus"):
        for sp in (True, False):
            for pe in (True, False):
                assert _mult(sub, sp=sp, pe=pe) <= 1.0


def test_unknown_and_stem_fallback_to_one() -> None:
    """unknown/천간합/누락은 ×1.0(기존값 보존)."""
    for sub in (None, "stem", "weird"):
        mult, reason = mt4_subtype_multiplier(sub, on_spouse_palace=True, partner_element=True)
        assert mult == 1.00 and reason == "MT4_HAP_UNKNOWN_FALLBACK_1_00"


def test_partner_elements_gender() -> None:
    """여=관살(甲木→金) / 남=재성(甲木→土) / 미상=빈 집합(보수적)."""
    assert partner_elements("木", "female") == {"金"}
    assert partner_elements("木", "male") == {"土"}
    assert partner_elements("木", "unknown") == set()


def test_gender_unknown_no_partner_element_relief() -> None:
    """gender 미상 → partner_elements 빈 집합이라 호출부가 partner_element=False → 0.80 미적용."""
    # 미상에서는 partnerElement가 성립할 수 없으므로 directional은 최대 0.75(일지)까지만.
    assert not partner_elements("金", "unknown")


# ── 엔진 통합: off / shadow / apply ──────────────────────────────────


def test_off_equals_shadow_byte_identical() -> None:
    """off와 shadow는 점수·reason_codes가 완전히 동일(shadow는 출력 미변경)."""
    r = _r()
    years = list(range(2018, 2035))
    off = EventEngineV2(_DICTS).score_years(r, years)
    sh_eng = EventEngineV2(_DICTS, enable_mt4_subtype="shadow")
    sh = sh_eng.score_years(r, years)
    assert [c.score for c in off] == [c.score for c in sh]
    assert [c.reason_codes for c in off] == [c.reason_codes for c in sh]
    assert [c.contributions for c in off] == [c.contributions for c in sh]


def test_shadow_records_diagnostics() -> None:
    """shadow 모드는 진단 사이드채널에만 기록하고, 감쇠 diff는 ≤ 0(상향 없음)."""
    r = _r()
    eng = EventEngineV2(_DICTS, enable_mt4_subtype="shadow")
    eng.score_years(r, list(range(2018, 2035)))
    assert eng.mt4_shadow  # 진단 기록 존재
    assert all(d["relation_mt4_diff"] <= 0 for d in eng.mt4_shadow)
    assert all(d["multiplier"] <= 1.0 for d in eng.mt4_shadow)


def test_apply_changes_scores_without_raising() -> None:
    """apply는 삼합/방합 후보 점수를 낮추되, 어떤 후보도 off보다 커지지 않는다(상향 없음)."""
    r = _r()
    years = list(range(2018, 2035))
    off = EventEngineV2(_DICTS).score_years(r, years)
    ap = EventEngineV2(_DICTS, enable_mt4_subtype="apply").score_years(r, years)
    off_map = {(c.period, c.event_key.value): c.score for c in off}
    raised = [
        c for c in ap
        if (c.period, c.event_key.value) in off_map
        and c.score > off_map[(c.period, c.event_key.value)]
    ]
    assert not raised  # 상향 위반 없음
    assert [c.score for c in off] != [c.score for c in ap]  # 실제 변화는 있음


def test_apply_non_relationship_domain_unchanged() -> None:
    """관계 외 도메인(career 등) 후보는 apply에서도 off와 동일(관계 도메인 한정)."""
    r = _r()
    years = list(range(2018, 2035))
    off = EventEngineV2(_DICTS).score_years(r, years)
    ap = EventEngineV2(_DICTS, enable_mt4_subtype="apply").score_years(r, years)
    rel = {"new_relationship", "marriage_signal", "relationship_change"}
    off_non = {
        (c.period, c.event_key.value): c.score
        for c in off if c.event_key.value not in rel
    }
    ap_non = {
        (c.period, c.event_key.value): c.score
        for c in ap if c.event_key.value not in rel
    }
    assert off_non == ap_non
