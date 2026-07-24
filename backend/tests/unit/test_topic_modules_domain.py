"""도메인 신호형 Topic Builder 모듈 검증 — M01·M02·M09·M11·M12 (docs/09 4·5장).

합성 LuckComposite(도메인 신호 주입)로 모듈이 올바른 도메인/이벤트만 집계하고 정책 톤(절대원칙
3·8)을 싣는지 결정론적으로 검증한다. 실차트 의존을 피해 신호 매핑 자체를 고정한다.
"""

from __future__ import annotations

import pytest

from saju_engines.topic_builder import build_topic_context
from saju_shared_types.precompute import (
    CompositeGanji,
    CompositeLevel,
    DomainSignal,
    LuckComposite,
    TenGodPair,
)
from saju_shared_types.topic_context import PeriodSpec

_PERIOD = PeriodSpec(start="2024", end="2027", granularity="year")


def _comp(
    period_key: str, domain: str, event_key: str, *, weight: float = 0.6, fav: str = "용신",
    stem: str = "甲", branch: str = "辰",
) -> LuckComposite:
    return LuckComposite(
        subject_id="s", level=CompositeLevel.YEAR, period_key=period_key,
        ganji=CompositeGanji(stem=stem, branch=branch),
        ten_god=TenGodPair(stem="편재", branch_main="정관"), twelve_stage="건록",
        favorability=fav,
        domain_signals=[DomainSignal(
            domain=domain, event_key=event_key, weight=weight, source_interaction="rel_x",
        )],
        dict_version="1.0.0", computed_at="2026-01-01T00:00:00+00:00",
    )


def test_m01_love_picks_relationship_events_only() -> None:
    """M01은 연애 이벤트(canonical new_relationship/relationship_change)만, 결혼 이벤트 제외.

    B1-a: 구키(relationship_start)는 read-adapter가 canonical로 해소한 뒤 매칭된다.
    """
    comps = [
        _comp("2025", "relationship", "relationship_start"),  # legacy → new_relationship
        _comp("2026", "relationship", "marriage"),  # legacy → marriage_signal, M01 제외
        _comp("2025", "wealth", "wealth_change"),  # 타도메인 제외
    ]
    ctx = build_topic_context("M01", [], _PERIOD, comps)
    assert ctx.module_id == "M01" and ctx.findings
    assert all(f.event_key == "new_relationship" for f in ctx.findings)


def test_m02_marriage_picks_marriage_events_only() -> None:
    """M02는 canonical {marriage_signal, childbirth}만, 연애 시작은 제외(B1-a 결정문)."""
    comps = [
        _comp("2026", "relationship", "marriage"),  # legacy → marriage_signal
        _comp("2025", "relationship", "relationship_start"),  # M02 제외
    ]
    ctx = build_topic_context("M02", [], _PERIOD, comps)
    assert ctx.findings and all(
        f.event_key in ("marriage_signal", "childbirth") for f in ctx.findings
    )


def test_m09_wealth_aggregates_wealth_domain() -> None:
    """M09는 wealth 도메인 신호를 점수로 확정(시계열·findings)."""
    comps = [
        _comp("2025", "wealth", "wealth_change", weight=0.8),
        _comp("2026", "wealth", "windfall", weight=0.5),
        _comp("2025", "health", "health_issue"),  # 제외
    ]
    ctx = build_topic_context("M09", [], _PERIOD, comps)
    assert {f.period_key for f in ctx.findings} == {"2025", "2026"}
    assert ctx.findings[0].period_key == "2025"  # 가중 큰 쪽이 상위
    assert all(0 <= p.score <= 100 for p in ctx.time_series)


def test_m11_health_and_m12_education_domains() -> None:
    """M11=health, M12=education 도메인만 각각 집계."""
    comps = [
        _comp("2025", "health", "health_issue"),
        _comp("2026", "education", "exam"),
    ]
    h = build_topic_context("M11", [], _PERIOD, comps)
    e = build_topic_context("M12", [], _PERIOD, comps)
    # B1-a: 구키는 canonical(health_attention/education_admission)로 해소돼 집계된다.
    assert [f.event_key for f in h.findings] == ["health_attention"]
    assert [f.event_key for f in e.findings] == ["education_admission"]


def test_policy_tone_notes_present() -> None:
    """정책 톤(절대원칙 8·3): 재물=횡재 가드, 시험=당락 금지, 건강=의료 단정 금지, 결혼=보류."""
    comps_w = [_comp("2025", "wealth", "windfall")]
    comps_e = [_comp("2025", "education", "exam")]
    comps_h = [_comp("2025", "health", "surgery")]
    comps_m = [_comp("2026", "relationship", "marriage")]
    def _tones(mid: str, comps: list) -> list[str]:
        return build_topic_context(mid, [], _PERIOD, comps).style_rules.tone_notes

    assert any("횡재" in t for t in _tones("M09", comps_w))
    assert any("당락" in t for t in _tones("M12", comps_e))
    assert any("전문의" in t for t in _tones("M11", comps_h))
    assert any("보류" in t for t in _tones("M02", comps_m))


def test_findings_deterministic_and_calendar_attached() -> None:
    """동일 입력 → 동일 출력 + 시계열 간지가 압축 간지달력에 동반(절대원칙 2)."""
    comps = [_comp("2025", "wealth", "wealth_change"), _comp("2026", "wealth", "windfall")]
    a = build_topic_context("M09", [], _PERIOD, comps)
    b = build_topic_context("M09", [], _PERIOD, comps)
    assert a.model_dump() == b.model_dump()
    cal_keys = {e.period_key for e in a.calendar_context}
    assert {p.period_key for p in a.time_series} <= cal_keys
    assert all(p.ganji for p in a.time_series)


def test_m08_business_combines_business_and_contract() -> None:
    """M08은 창업(business_start)+사업 계약(contract/document)만, 일반 재물흐름은 제외."""
    comps = [
        _comp("2025", "career", "business_start", weight=0.7),
        _comp("2026", "wealth", "contract"),
        _comp("2025", "wealth", "windfall"),  # 사업 아님 → 제외
        _comp("2025", "career", "promotion"),  # 사업 아님 → 제외
    ]
    ctx = build_topic_context("M08", [], _PERIOD, comps)
    assert ctx.findings and all(
        f.event_key in ("business_start", "contract_document") for f in ctx.findings
    )
    assert any("동업" in t for t in ctx.style_rules.tone_notes)


def test_m14_past_validation_reverse_engine() -> None:
    """M14: past_validation 역방향 — 과거 후보 findings 확정(extras=birth/scorer/compute)."""
    from datetime import date

    from saju_api.services.manse_service import calculate
    from saju_engines.event_engine_v2 import EventEngineV2
    from saju_shared_types.birth_input import BirthInput

    dicts = __import__("pathlib").Path(__file__).resolve().parents[2] / "dictionaries"
    birth = BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    )
    ctx = build_topic_context(
        "M14", [], PeriodSpec(start="2019", end="2021", granularity="year"), [],
        birth=birth, scorer=EventEngineV2(dicts), compute=calculate,
    )
    assert ctx.module_id == "M14" and ctx.findings
    assert all(f.period_key is not None and 2019 <= int(f.period_key[:4]) <= 2021
               for f in ctx.findings)
    assert any("콜드리딩" in t for t in ctx.style_rules.tone_notes)


@pytest.mark.parametrize(
    ("mid", "axis_tgs", "label"),
    [("M04", ("편인", "정인"), "부모"), ("M05", ("식신", "상관"), "자녀"),
     ("M06", ("편관", "정관", "비견", "겁재"), "직장")],
)
def test_relation_axis_modules(mid: str, axis_tgs: tuple, label: str) -> None:
    """M04/M05/M06: natal 십성 축 세력 + relation_profiles 구조축 finding(육친 구조형)."""
    dist = {tg: 0.2 for tg in axis_tgs}
    dist.update({"편재": 0.1, "정재": 0.1})  # 축 외 십성(상대 세력 분모)
    ctx = build_topic_context(mid, [], _PERIOD, [], natal_ten_god_dist=dist)
    assert ctx.module_id == mid and ctx.findings
    natal = next(f for f in ctx.findings if f.period_key == "natal")
    assert set(axis_tgs) == set(natal.signals)  # 축 십성이 신호로
    assert natal.score > 0  # 세력 비율 산출


def test_m13_bond_compare_two_subjects() -> None:
    """M13: compatibility_engine 재사용 — 안정(보완/마찰)·끌림 두 축 findings + 정책 톤."""
    from datetime import date

    from saju_api.services.manse_service import calculate
    from saju_engines.context_reducer import build_birth_summary
    from saju_shared_types.birth_input import BirthInput

    a = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11)))
    b = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1985, 5, 5), birth_time="14:00",
        birth_place_name="서울", gender="female", reference_date=date(2026, 6, 11)))
    ctx = build_topic_context(
        "M13", [], PeriodSpec(start="2026", end="2026", granularity="year"), [],
        self_result=a, partner_result=b,
        self_useful=build_birth_summary(a).useful_gods,
        partner_useful=build_birth_summary(b).useful_gods,
    )
    assert ctx.module_id == "M13" and ctx.findings
    assert any(f.key == "bond_stability" for f in ctx.findings)
    assert any("끌림" in t for t in ctx.style_rules.tone_notes)


# ── B1-a: 어휘 정규화·M01/M02 소유권 매트릭스 (RELATIONSHIP_EVENT_SYSTEM 부록 B §9) ──


def _m01_keys(comps: list[LuckComposite]) -> set[str]:
    return {f.event_key for f in build_topic_context("M01", [], _PERIOD, comps).findings}


def _m02_keys(comps: list[LuckComposite]) -> set[str]:
    return {f.event_key for f in build_topic_context("M02", [], _PERIOD, comps).findings}


def test_b1a_canonical_relationship_change_owned_by_m01_only() -> None:
    """canonical relationship_change → M01 포함·M02 제외(중복 소비 금지 — 결정문)."""
    comps = [_comp("2025", "relationship", "relationship_change")]
    assert _m01_keys(comps) == {"relationship_change"}
    assert _m02_keys(comps) == set()


def test_b1a_canonical_new_relationship_m01_only() -> None:
    comps = [_comp("2025", "relationship", "new_relationship")]
    assert _m01_keys(comps) == {"new_relationship"}
    assert _m02_keys(comps) == set()


def test_b1a_canonical_marriage_signal_childbirth_m02_only() -> None:
    comps = [
        _comp("2025", "relationship", "marriage_signal"),
        _comp("2026", "relationship", "childbirth"),
    ]
    assert _m01_keys(comps) == set()
    assert _m02_keys(comps) == {"marriage_signal", "childbirth"}


def test_b1a_legacy_relationship_end_to_m01() -> None:
    """legacy relationship_end → canonical relationship_change로 M01 포함·M02 제외."""
    comps = [_comp("2025", "relationship", "relationship_end")]
    assert _m01_keys(comps) == {"relationship_change"}
    assert _m02_keys(comps) == set()


def test_b1a_legacy_family_change_m02_compat_only() -> None:
    """legacy family_change → canonical relationship_change로 정규화되지만
    provenance 기반으로 M02 호환 포함·M01 배제(결정문 — 가족·가정 변화는 M02 소유)."""
    comps = [_comp("2025", "relationship", "family_change")]
    assert _m01_keys(comps) == set()
    assert _m02_keys(comps) == {"relationship_change"}


def test_b1a_unknown_legacy_key_excluded_everywhere() -> None:
    """미지 legacy 키 — 도메인 임의 배정·소비 금지(원본 유지+계측만)."""
    comps = [_comp("2025", "relationship", "mystery_event_key")]
    assert _m01_keys(comps) == set()
    assert _m02_keys(comps) == set()


def test_b1a_general_domain_repaired_for_canonical_keys() -> None:
    """기존 DB 오분류(domain=general·canonical 키) — read-adapter가 도메인을 수리해
    M01이 소비한다(P0-A 실측 결함 부활 경로)."""
    comps = [_comp("2025", "general", "new_relationship")]
    assert _m01_keys(comps) == {"new_relationship"}


def test_b1a_no_duplicate_signal_across_m01_m02() -> None:
    """F-17/Y-08(M01+M02 동시 조립) 중복 방지 — 동일 신호가 양쪽 findings에 못 들어간다."""
    comps = [
        _comp("2025", "relationship", "relationship_change"),  # M01 소유
        _comp("2026", "relationship", "family_change"),        # M02 호환 소유(legacy)
        _comp("2027", "relationship", "marriage_signal"),      # M02 소유
    ]
    m01_ctx = build_topic_context("M01", [], _PERIOD, comps)
    m02_ctx = build_topic_context("M02", [], _PERIOD, comps)
    m01 = {(f.event_key, f.period_key) for f in m01_ctx.findings}
    m02 = {(f.event_key, f.period_key) for f in m02_ctx.findings}
    assert m01 == {("relationship_change", "2025")}
    assert m02 == {("relationship_change", "2026"), ("marriage_signal", "2027")}
    assert m01.isdisjoint(m02)
