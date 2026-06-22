"""비식재(比食財) 흐름 결혼 발동 모디파이어 검증 (Task 2 확장, 2026-06-22).

원국 비식재 그릇(식상생재 라인 × 배우자성 약) × 운의 식재/재생관 보강 → marriage_signal·
relationship_change 보수 가산(증폭만). 성별 인지 완성 조건·band 배율·계열 감쇠를 확인한다.
가중은 reviewed:false 잠정값이라 절대값이 아니라 '발동 여부·방향'을 검증한다.
"""

from __future__ import annotations

from datetime import date

from saju_api.services.manse_service import calculate
from saju_engines.marriage_flow_modifier import (
    MarriageFlowModifier,
    MarriageFlowNatal,
    analyze_marriage_flow_natal,
    apply_marriage_gender_weight,
    detect_marriage_flow_activations,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import EventCandidateV2


def _chart(y: int, m: int, d: int, hm: str, gender: str):
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(y, m, d), birth_time=hm,
        birth_place_name="서울", gender=gender,
    ))


def _cand(event: str, score: int = 60, reason_codes: list[str] | None = None) -> EventCandidateV2:
    return EventCandidateV2(
        event_key=event, period="2026", score=score, reason_codes=reason_codes or [],
    )


# ── 배우자성 성별 가중(③) — 남=재성·여=관성 ──
def test_gender_weight_male_officer_only_downweighted() -> None:
    # 남성 정관 단독(배우자성 아님) → 약화. 정재 단독(재성=처) → 불변.
    cands = [
        _cand("marriage_signal", 50, ["SINGLE_ZHENGGUAN"]),
        _cand("marriage_signal", 50, ["SINGLE_ZHENGCAI"]),
    ]
    out = apply_marriage_gender_weight(cands, "male")
    officer, wealth = out[0], out[1]
    assert officer.score < 50  # 정관 단독 약화
    assert any("MARRIAGE_GENDER_MALE" in rc for rc in officer.reason_codes)
    assert wealth.score == 50  # 재성 구동 불변


def test_gender_weight_female_wealth_only_downweighted() -> None:
    # 여성 재성 단독(시댁·간접) → 약화. 정관 단독(관성=남편) → 불변.
    cands = [
        _cand("marriage_signal", 50, ["SINGLE_ZHENGCAI"]),
        _cand("marriage_signal", 50, ["SINGLE_ZHENGGUAN"]),
    ]
    out = apply_marriage_gender_weight(cands, "female")
    assert out[0].score < 50 and any("MARRIAGE_GENDER_FEMALE" in rc for rc in out[0].reason_codes)
    assert out[1].score == 50


def test_gender_weight_both_stars_unchanged() -> None:
    # 재성+관성 동반(재생관) → 어느 성별이든 약화 안 함.
    for g in ("male", "female"):
        out = apply_marriage_gender_weight(
            [_cand("marriage_signal", 50, ["SPEC_ZHENGCAI_ZHENGGUAN"])], g,
        )
        assert out[0].score == 50


def test_gender_weight_unknown_and_nontarget_unchanged() -> None:
    # 미상 성별 → 무변경.
    assert apply_marriage_gender_weight(
        [_cand("marriage_signal", 50, ["SINGLE_ZHENGGUAN"])], "unknown",
    )[0].score == 50
    # 비대상 이벤트(career_change) → 무변경.
    assert apply_marriage_gender_weight(
        [_cand("career_change", 50, ["SINGLE_ZHENGGUAN"])], "male",
    )[0].score == 50


# ── 운 발동 판정(성별 인지) ──
def test_activations_gender_aware_completion() -> None:
    # 여성: 재성+관성(authority) → 재생관 완성. 남성: 식상+재성 → 식상생재 완성.
    fem = detect_marriage_flow_activations({"wealth", "authority"}, "female")
    assert "재성 보강" in fem and "재생관 완성" in fem
    assert "식상생재 완성" not in fem
    male = detect_marriage_flow_activations({"output", "wealth"}, "male")
    assert "식상 보강" in male and "재성 보강" in male and "식상생재 완성" in male
    assert "재생관 완성" not in male
    # 식상만 — 보강만 있고 완성 없음.
    assert detect_marriage_flow_activations({"output"}, "female") == ["식상 보강"]
    # 무관 십성군 — 발동 없음.
    assert detect_marriage_flow_activations({"resource", "peer"}, "male") == []


# ── 모디파이어 가산(증폭만) ──
def test_apply_boosts_only_target_keys() -> None:
    natal = MarriageFlowNatal(band="strong", gender="female")
    acts = ["재성 보강", "재생관 완성"]
    out = MarriageFlowModifier.apply(
        [_cand("marriage_signal", 60), _cand("career_change", 60)], natal, acts,
    )
    ms = next(c for c in out if str(c.event_key) == "marriage_signal")
    cc = next(c for c in out if str(c.event_key) == "career_change")
    assert ms.score > 60  # 결혼 신호 증폭
    assert any("MARRIAGEFLOW" in rc for rc in ms.reason_codes)
    assert "marriage_flow" in ms.contributions
    assert cc.score == 60  # 비대상 도메인 불변


def test_apply_band_none_or_no_activation_unchanged() -> None:
    cands = [_cand("marriage_signal", 60)]
    # band=none → 무가산.
    assert MarriageFlowModifier.apply(
        cands, MarriageFlowNatal(band="none", gender="female"), ["재성 보강"],
    )[0].score == 60
    # 발동 없음 → 무가산.
    assert MarriageFlowModifier.apply(
        cands, MarriageFlowNatal(band="moderate", gender="female"), [],
    )[0].score == 60


def test_apply_strong_band_beats_moderate() -> None:
    acts = ["재성 보강", "재생관 완성"]
    base = 60
    strong = MarriageFlowModifier.apply(
        [_cand("marriage_signal", base)], MarriageFlowNatal("strong", "female"), acts,
    )[0].score
    moderate = MarriageFlowModifier.apply(
        [_cand("marriage_signal", base)], MarriageFlowNatal("moderate", "female"), acts,
    )[0].score
    assert base < moderate < strong  # 배율 1.0 > 0.5 > 0


def test_apply_family_diminish_flag() -> None:
    # 복수 발동(같은 계열) → 감쇠 표식이 붙는다.
    out = MarriageFlowModifier.apply(
        [_cand("marriage_signal", 60)], MarriageFlowNatal("strong", "female"),
        ["재성 보강", "재생관 완성"],
    )[0]
    assert "MARRIAGEFLOW_FAMILY_DIMINISH" in out.reason_codes


# ── 원국 그릇 판정 ──
def test_natal_band_classification() -> None:
    # 실제 명식들의 band가 strong/moderate/none 중 하나로 결정되고, 일관적이다.
    for (y, m, d, hm, g) in (
        (1990, 5, 5, "10:00", "male"),
        (1992, 7, 7, "20:00", "female"),
        (1988, 9, 9, "12:00", "female"),
    ):
        nat = analyze_marriage_flow_natal(_chart(y, m, d, hm, g))
        assert nat.band in ("strong", "moderate", "none")
        assert nat.gender == g


def test_end_to_end_marriage_flow_reason_code() -> None:
    """엔진 스코어링에서 비식재 그릇 명식의 결혼 후보에 MARRIAGEFLOW 가점이 박힌다."""
    from saju_api.services.manse_service import _DICTS
    from saju_engines.event_engine_v2 import EventEngineV2
    from saju_engines.event_scoring import favorability_map

    r = _chart(1990, 5, 5, "10:00", "male")
    nat = analyze_marriage_flow_natal(r)
    assert nat.band in ("strong", "moderate")  # 이 명식은 비식재 그릇 보유
    eng = EventEngineV2(_DICTS)
    cands = eng.score_years(r, list(range(2020, 2034)), favorability_map(r))
    boosted = [
        c for c in cands
        if str(c.event_key) in ("marriage_signal", "relationship_change")
        and any("MARRIAGEFLOW" in rc for rc in c.reason_codes)
    ]
    assert boosted, "비식재 그릇 명식의 식재/완성 연도에 결혼 후보 가점이 있어야 한다"
