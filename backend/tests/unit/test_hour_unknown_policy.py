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
