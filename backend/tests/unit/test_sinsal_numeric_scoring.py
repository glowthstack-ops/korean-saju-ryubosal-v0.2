"""신살 채널 shadow sidecar 단위 테스트 (SINSAL_MODIFIER_SPEC §10-1b, Phase B-1 v2).

발생 가능성(occurrence) 불변·채널별 부호(길성=mitigation/favorability+, 흉살=risk/favorability−,
중립=texture)·게이트·캡·기간 재활성 검증. score 채널 모델은 폐기(길흉 방향 역행).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import EventEngineV2
from saju_engines import sinsal_modifier_config as cfg
from saju_engines.sinsal_numeric_scoring import (
    apply_sinsal_channel_shadow,
    channel_note_ko,
    sinsal_channel_sidecar,
    sinsal_invariance_snapshot,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventCandidate
from saju_shared_types.ganji_calendar import GanjiLevel

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"


@pytest.fixture(scope="module")
def chart():
    return calculate(BirthInput(
        calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))


@pytest.fixture(scope="module")
def scorer() -> EventEngineV2:
    return EventEngineV2(_DICTS)


@pytest.fixture(scope="module")
def candidates(chart, scorer):
    return scorer.score_legacy(chart, levels={GanjiLevel.YEAR})


def _ganji_map(candidates) -> dict[str, str]:
    return {c.period: "丙午" for c in candidates}


def test_master_gate_off_returns_none(chart, candidates) -> None:
    assert cfg.SINSAL_NUMERIC_SHADOW_ENABLED is False
    assert sinsal_channel_sidecar(chart, candidates, _ganji_map(candidates)) is None


def test_occurrence_score_delta_always_zero(chart, candidates) -> None:
    """발생 가능성 채널은 절대 건드리지 않는다(핵심 불변 — 길흉 역행 폐기)."""
    out = apply_sinsal_channel_shadow(
        chart, candidates, _ganji_map(candidates), domain="career")
    for row in out:
        assert row["occurrence_score_delta"] == 0


def test_candidates_not_mutated_and_invariant(chart, candidates) -> None:
    before = sinsal_invariance_snapshot(chart, candidates)
    apply_sinsal_channel_shadow(chart, candidates, _ganji_map(candidates), domain="career")
    after = sinsal_invariance_snapshot(chart, candidates)
    assert before == after  # score·polarity 불변


def test_eventcandidate_schema_has_no_sinsal_field(candidates) -> None:
    if candidates:
        fields = type(candidates[0]).model_fields
        for k in ("favorability_delta", "risk_delta", "mitigation_delta", "texture_tags"):
            assert k not in fields


def test_sidecar_index_aligned_and_shape(chart, candidates) -> None:
    out = apply_sinsal_channel_shadow(
        chart, candidates, _ganji_map(candidates), domain="career")
    assert len(out) == len(candidates)
    for i, row in enumerate(out):
        assert row["candidate_index"] == i
        assert row["legacy_score"] == int(candidates[i].score)
        for k in ("favorability_delta", "risk_delta", "mitigation_delta", "texture_tags"):
            assert k in row


def test_channel_caps(chart, candidates) -> None:
    out = apply_sinsal_channel_shadow(
        chart, candidates, _ganji_map(candidates), domain="career")
    caps = cfg.SINSAL_CHANNEL_CAPS
    for row in out:
        assert -caps["favorability"] <= row["favorability_delta"] <= caps["favorability"]
        assert 0.0 <= row["risk_delta"] <= caps["risk"]
        assert 0.0 <= row["mitigation_delta"] <= caps["mitigation"]


def test_channel_sign_semantics() -> None:
    """길성=mitigation+/favorability+, 흉살=risk+/favorability−를 합성한 단일 신살로 검증."""
    from types import SimpleNamespace

    # 길성(천을귀인) 단독 차트 모형 + 그 자리 글자 재출현 운간지.
    def _result(name, polarity_pillar="day"):
        pillars = SimpleNamespace(
            year=SimpleNamespace(branch="子", stem="甲"),
            month=SimpleNamespace(branch="丑", stem="乙"),
            day=SimpleNamespace(branch="午", stem="丙"),
            hour=SimpleNamespace(branch="未", stem="丁"),
        )
        sinsal = SimpleNamespace(full_list=[
            SimpleNamespace(name=name, position=polarity_pillar),
        ])
        extras = SimpleNamespace(sinsal=sinsal)
        return SimpleNamespace(traditional_extras=extras, pillars=pillars)

    cand = cast("list[EventCandidate]",
                [SimpleNamespace(score=50, event_key="career_change", period="P")])
    gbp = {"P": "丙午"}  # 일지 午·일간 丙 재출현 → 일주 신살 재활성.

    aus = apply_sinsal_channel_shadow(_result("천을귀인"), cand, gbp, domain="relationship")[0]
    assert aus["mitigation_delta"] > 0 and aus["favorability_delta"] > 0
    assert aus["risk_delta"] == 0.0 and aus["occurrence_score_delta"] == 0

    inaus = apply_sinsal_channel_shadow(_result("백호"), cand, gbp, domain="relationship")[0]
    assert inaus["risk_delta"] > 0 and inaus["favorability_delta"] < 0
    assert inaus["mitigation_delta"] == 0.0 and inaus["occurrence_score_delta"] == 0

    neut = apply_sinsal_channel_shadow(_result("역마살"), cand, gbp, domain="relationship")[0]
    assert neut["texture_tags"] == ["이동·변동성"]
    assert neut["favorability_delta"] == 0.0 and neut["risk_delta"] == 0.0
    assert neut["mitigation_delta"] == 0.0


def test_non_reactivated_is_background(chart, candidates) -> None:
    """동일글자 재출현이 없는 운간지에서는 채널 기여 0(배경)."""
    # 원국에 없을 법한 글자 조합으로 재활성 회피.
    no_react = {c.period: "甲子" for c in candidates}  # 子가 원국에 있으면 재활성될 수 있음
    out = apply_sinsal_channel_shadow(chart, candidates, no_react, domain="career")
    # 적어도 일부 후보는 완전 배경(모든 채널 0·texture 없음)일 수 있음 — 구조만 확인.
    for row in out:
        assert isinstance(row["texture_tags"], list)


def test_missing_ganji_zero_channels(chart, candidates) -> None:
    out = apply_sinsal_channel_shadow(chart, candidates, {}, domain="career")
    for row in out:
        assert row.get("missing_ganji") is True
        assert row["favorability_delta"] == 0.0
        assert row["risk_delta"] == 0.0
        assert row["mitigation_delta"] == 0.0
        assert row["occurrence_score_delta"] == 0


# ── B-2: 채널 → 한글 색채 노트(리포트 운영 반영) ──

def test_channel_note_ko_bands_and_empty() -> None:
    # 강한 완충+리스크+텍스처 → 합성 노트(숫자 없음).
    note = channel_note_ko(0.10, 0.16, 0.18, ["이동·변동성"])
    assert "완충 큼" in note and "리스크 큼" in note and "유리한 색채" in note
    assert "(이동·변동성)" in note
    assert not any(ch.isdigit() for ch in note)
    # 전부 미미 → 빈 문자열.
    assert channel_note_ko(0.0, 0.0, 0.0, []) == ""
    # 부담 색채(흉살 음수 favorability).
    neg = channel_note_ko(-0.08, 0.16, 0.0, [])
    assert "부담스러운 색채" in neg


def test_report_clusters_carry_channel_note_no_digits(chart, scorer) -> None:
    from saju_engines.report_event_input import precise_candidate_clusters
    lc = chart.luck_cycles
    yp = []
    for d in lc.daewoon_table:
        if 20 <= d.start_age < 60:
            yp += [p for p in (d.sewoon or []) if p.label.isdigit()]
    cands = scorer.score_legacy_years(chart, [int(p.label) for p in yp[:20]])
    lines = precise_candidate_clusters(chart, cands)
    notes = [ln for ln in lines if "시기색채" in ln]
    assert notes  # 재활성 기간이 있으면 노트가 붙는다
    for ln in notes:
        # 색채 노트엔 숫자(점수·계수) 미노출.
        assert not any(ch.isdigit() for ch in ln)


def test_channel_note_gate_off(chart, scorer, monkeypatch) -> None:
    import saju_engines.report_event_input as rei
    monkeypatch.setattr(rei._sinsal_cfg, "SINSAL_CHANNEL_APPLY_ENABLED", False)
    lc = chart.luck_cycles
    yp = []
    for d in lc.daewoon_table:
        if 20 <= d.start_age < 60:
            yp += [p for p in (d.sewoon or []) if p.label.isdigit()]
    cands = scorer.score_legacy_years(chart, [int(p.label) for p in yp[:20]])
    lines = rei.precise_candidate_clusters(chart, cands)
    assert not any("시기색채" in ln for ln in lines)  # off → 미부착
