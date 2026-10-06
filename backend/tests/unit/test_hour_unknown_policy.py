"""출생시간 미상 정책 — 미상≠없음·불완전 정보 비확정 (2026-10-06, doc/v2_2/HOUR_UNKNOWN_POLICY.md).

- 계산: 12시진 후보 비교 메타(hour_unknown)가 붙고, 갈리는 항목은 unconfirmed 에 든다.
- LLM 입력: 상이 항목은 '미확정'으로, 용희신 상이면 비워서 길흉·처방에 쓰지 못하게 한다.
- 지시문: 시주 미상 명식에만 해석 제한 규칙이 붙는다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.context_reducer import (
    build_birth_summary,
    polarity_ko,
    serialize_chart_prefix,
)
from saju_engines.structural_context import HOUR_UNKNOWN_DIRECTIVE, hour_unknown_directive
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.hour_unknown import ConsensusItem, HourUnknownAnalysis

_BASE = dict(birth_date="1980-11-22", birth_place_name="서울", gender="male",
             reference_date=date(2026, 10, 6))


@pytest.fixture(scope="module")
def unknown():
    return calculate(BirthInput(**_BASE, birth_time=None, birth_time_unknown=True))


@pytest.fixture(scope="module")
def known():
    return calculate(BirthInput(**_BASE, birth_time="09:40"))


def test_unknown_time_gets_candidate_analysis(unknown) -> None:
    hu = unknown.hour_unknown
    assert hu is not None and unknown.pillars is not None and unknown.pillars.hour is None
    assert [c.hour_branch for c in hu.candidates] == list("子丑寅卯辰巳午未申酉戌亥")
    assert all(c.ganji and c.strength_band for c in hu.candidates)
    # 1980-11-22 서울: 시진에 따라 신강 밴드·격국이 갈리고 용희신은 전부 같다(실측 고정).
    assert hu.strength_band.status == "differ" and "strength_band" in hu.unconfirmed
    assert hu.geokguk.status == "differ" and set(hu.geokguk.values) == {"정재격", "정관격"}
    assert hu.useful_gods.status == "agree" and "useful_gods" not in hu.unconfirmed
    assert hu.daewoon_start_range is not None
    lo, hi = hu.daewoon_start_range
    assert lo < hi and hi - lo < 0.5  # ±12시간 → 약 0.3년 범위
    assert "출생시간 미상" in hu.notice and "상이 신강약·격국" in hu.notice
    assert hu.boundary_warnings == []  # 11-22 는 절입·입춘 경계가 아니다


def test_known_time_has_no_analysis(known) -> None:
    assert known.hour_unknown is None
    summary = build_birth_summary(known)
    assert summary.hour_unknown is False and summary.hour_unknown_items == []
    prefix = "\n".join(serialize_chart_prefix(summary, None))
    assert "시주 미상" not in prefix and "hour:미상" not in prefix


def test_summary_marks_unconfirmed_and_prefix_discloses(unknown) -> None:
    summary = build_birth_summary(unknown)
    assert summary.hour_unknown is True
    assert summary.strength.startswith("미확정(시주 미상")
    assert summary.geokguk.startswith("미확정(시주 미상")
    assert summary.useful_gods.yongsin == ["土"]  # 후보 전부 일치 → 유지
    prefix = "\n".join(serialize_chart_prefix(summary, None))
    assert "hour:미상(산출 불가)" in prefix
    assert "시주 미상: 3기둥 기준" in prefix
    assert "[시주 미상 — 확정 제외·해석 제한]" in prefix
    assert "용신 土" in prefix  # 일치 항목은 그대로 전달


def test_useful_gods_differ_blanks_roles(unknown) -> None:
    """용희신이 후보에 따라 갈리면 LLM 에 넘기지 않는다(길흉·색·방향 처방 차단)."""
    hu = unknown.hour_unknown
    assert hu is not None
    forced = hu.model_copy(update={
        "useful_gods": ConsensusItem(status="differ", base=hu.useful_gods.base,
                                     values=["용土·희火·기木", "용火·희木·기水"]),
        "unconfirmed": [*hu.unconfirmed, "useful_gods"],
    })
    result = unknown.model_copy(update={"hour_unknown": forced})
    summary = build_birth_summary(result)
    assert summary.useful_gods.yongsin == [] and summary.useful_gods.gisin == []
    prefix = "\n".join(serialize_chart_prefix(summary, None))
    assert "용신·희신·기신·구신·한신: 미확정(시주 미상" in prefix
    assert "용신 土" not in prefix
    assert polarity_ko("unconfirmed") == "극성 보류(시주 미상·용희신 미확정)"


def test_directive_only_for_unknown(unknown, known) -> None:
    assert hour_unknown_directive(known) is None
    text = hour_unknown_directive(unknown)
    assert text is not None and text.startswith(HOUR_UNKNOWN_DIRECTIVE)
    assert "[엔진 산출]" in text and "상이 신강약·격국" in text
    # 핵심 금지 규칙이 들어 있다.
    for key in ("시주·시지 궁위", "무재성", "미확정", "대운수"):
        assert key in text


def test_analysis_model_helpers() -> None:
    hu = HourUnknownAnalysis(
        strength_band=ConsensusItem(status="agree", base="신약", values=["신약"]),
        geokguk=ConsensusItem(status="differ", base="정재격", values=["정재격", "정관격"]),
        useful_gods=ConsensusItem(status="agree", base="용土·희火·기木"),
        unconfirmed=["geokguk"],
    )
    assert hu.is_unconfirmed("geokguk") and not hu.is_unconfirmed("useful_gods")
    assert hu.geokguk.agree is False and hu.strength_band.agree is True


# ── 2차(2026-10-06 후속): 엔진 극성 중립화·시간대/추정 후보·경계 당일 명식 분기·성향 좁히기 ──


def test_favorability_map_neutral_when_useful_gods_unconfirmed(unknown) -> None:
    """용희신이 후보 간 갈리면 엔진 전체가 쓰는 favorability_map 이 비어 극성이 중립이 된다."""
    from saju_engines.event_scoring import favorability_map

    assert favorability_map(unknown)  # 이 명식은 일치 → 그대로
    hu = unknown.hour_unknown
    assert hu is not None
    forced = unknown.model_copy(update={"hour_unknown": hu.model_copy(update={
        "unconfirmed": [*hu.unconfirmed, "useful_gods"],
    })})
    assert favorability_map(forced) == {}


def test_band_narrows_candidates_and_basis() -> None:
    r = calculate(BirthInput(**_BASE, birth_time=None, birth_time_unknown=True,
                             birth_time_approx="아침"))
    hu = r.hour_unknown
    assert hu is not None and hu.basis == "band:아침" and hu.approx_band == "아침"
    assert [c.hour_branch for c in hu.candidates] == ["辰", "巳"]
    assert "시간대 '아침' 2후보" in hu.notice
    # 辰·巳 두 후보는 모두 '신약'이라 이 시간대에서는 신강약이 일치한다(실측 고정).
    assert hu.strength_band.status == "agree"


def test_hint_is_marked_as_estimate_not_confirmed() -> None:
    r = calculate(BirthInput(**_BASE, birth_time=None, birth_time_unknown=True,
                             birth_time_approx="밤", hour_branch_hint="子"))
    hu = r.hour_unknown
    assert hu is not None and hu.basis == "hint:子"
    assert [c.hour_branch for c in hu.candidates] == ["子"]
    assert r.pillars is not None and r.pillars.hour is None  # 여전히 시간 미상 모드
    assert "성향 추정 시진 子(확정 아님)" in hu.notice
    summary = build_birth_summary(r)
    assert summary.pillars["hour"].startswith("추정 甲子(성향 기반·확정 아님)")
    prefix = "\n".join(serialize_chart_prefix(summary, None))
    assert "hour:추정 甲子(성향 기반·확정 아님)" in prefix and "hour:미상" not in prefix
    text = hour_unknown_directive(r)
    assert text is not None and "추정 시진 기준" in text


def test_boundary_day_splits_pillar_variants() -> None:
    """2024-02-04(입춘 17:20 KST) 시간 미상 → 시각에 따라 연·월주가 갈린다(명식 변형 2갈래)."""
    r = calculate(BirthInput(
        calendar_type="solar", birth_date="2024-02-04", birth_time=None, birth_time_unknown=True,
        birth_place_name="서울", gender="female", reference_date=date(2026, 10, 6),
    ))
    hu = r.hour_unknown
    assert hu is not None
    assert len(hu.pillar_variants) == 2
    assert {"year_pillar", "month_branch"} <= set(hu.unconfirmed)
    assert "day_master" not in hu.unconfirmed
    assert any(v.is_base for v in hu.pillar_variants)
    assert any("입춘 경계" in w for w in hu.boundary_warnings)
    assert "명식 자체가 2갈래" in hu.notice
    summary = build_birth_summary(r)
    assert "명식 변형:" in summary.hour_unknown_note
    text = hour_unknown_directive(r)
    assert text is not None and "경계 경고" in text


def test_hour_narrowing_statements_and_ranking() -> None:
    from saju_api.services import hour_narrowing as hn

    birth = BirthInput(**_BASE, birth_time=None, birth_time_unknown=True, birth_time_approx="낮")
    traits = hn.trait_candidates(birth)
    assert traits.basis == "band:낮" and [c.hour_branch for c in traits.candidates] == ["午", "未"]
    for c in traits.candidates:
        assert {s.source for s in c.statements} == {"stem", "branch", "stage"}
        assert all(s.text for s in c.statements)  # 사전 문구 그대로(빈 문장 없음)
    # 午 후보 문장 3개를 모두 고르면 午가 단독 1위 → 추천(공유 문장이 있으면 未도 가산되나 3>미만).
    picked = [s.id for s in traits.candidates[0].statements]
    out = hn.narrow(hn.HourNarrowRequest(birth=birth, picked=picked))
    assert out.ranking[0].hour_branch == "午" and out.ranking[0].matched == 3
    assert out.recommended == "午" and out.confidence in ("low", "medium")
    assert "추정이며 확정이 아니다" in out.note
    # 아무것도 고르지 않으면 추천 없음.
    none = hn.narrow(hn.HourNarrowRequest(birth=birth, picked=[]))
    assert none.recommended is None and none.confidence == "none"
    # 시간이 있으면 좁힐 것이 없다.
    known = hn.trait_candidates(BirthInput(**_BASE, birth_time="09:40"))
    assert known.basis == "known" and known.candidates == []
