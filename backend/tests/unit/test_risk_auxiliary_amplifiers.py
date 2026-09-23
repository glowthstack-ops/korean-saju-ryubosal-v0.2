"""위험 family 단위 보조 증폭 층(P2, 2026-09-18 데굴님 결정) — 위험 사전 항목 불변.

- 사전 계약: 흉 극성 필수·배경 조건 필수·family/riskId 등록 검증·완곡 라벨.
- 적용은 순수 함수: 후보 신설·삭제 없음, 매칭 없는 후보는 같은 객체, aux_bonus ≤ 상한.
- 점수 불변식: occurrence·원인 표·protection 불변, rankable 우선도만 소폭 상승.
- 플래그 OFF면 엔진 shadow 후보 byte 불변. 표현 계층은 대표 후보의 aux 라벨을 P2 tier로 싣는다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate, luck_months
from saju_api.services.risk_exposure_bootstrap import build_risk_payload
from saju_engines import period_v2_config
from saju_engines.dictionaries import (
    AUX_ADVERSE_POLARITY_ROLES,
    _lint_risk_auxiliary,
    validate_dictionaries,
)
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.risk_auxiliary import (
    AuxiliaryFacts,
    apply_auxiliary_amplifiers,
    auxiliary_labels,
    load_auxiliary_amplifiers,
)
from saju_engines.risk_scoring import (
    _AUX_MAX_BONUS,
    atom_semantics,
    cause_occurrence_table,
    clamp_aux_bonus,
    risk_priority,
    score_shadow,
    structural_priority,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.risk_engine import EvidenceRole

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_FORBIDDEN_LABEL_WORDS = ("반드시", "확실", "사망", "죽", "확정", "틀림없")


def _birth() -> BirthInput:
    return BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
        birth_place_name="서울 구로구", latitude=37.4944, longitude=126.8563,
        timezone="Asia/Seoul", gender="male", reference_date=date(2026, 9, 18),
    )


@pytest.fixture(scope="module")
def chart():
    c = calculate(_birth())
    c.luck_cycles.monthly_luck = luck_months(_birth(), 2026) + luck_months(_birth(), 2027)
    return c


def _shadow(chart, *, aux: bool):
    engine = EventEngineV2(_DICTS, risk_mode="shadow")
    prev = period_v2_config.RISK_AUX_AMPLIFIER_ENABLED
    period_v2_config.RISK_AUX_AMPLIFIER_ENABLED = aux
    try:
        engine.score(chart, levels={GanjiLevel.MONTH})
    finally:
        period_v2_config.RISK_AUX_AMPLIFIER_ENABLED = prev
    return list(engine.risk_shadow)


@pytest.fixture(scope="module")
def shadow_off(chart):
    return _shadow(chart, aux=False)


@pytest.fixture(scope="module")
def shadow_on(chart):
    return _shadow(chart, aux=True)


# ── 1. 사전 계약 ────────────────────────────────────────────────────────────


def test_dictionary_contract_and_lint() -> None:
    items = load_auxiliary_amplifiers(_DICTS)
    assert len(items) == 15
    assert validate_dictionaries(_DICTS) == []
    ids = [it.id for it in items]
    assert len(ids) == len(set(ids))
    for it in items:
        assert it.polarity_role_in and set(it.polarity_role_in) <= AUX_ADVERSE_POLARITY_ROLES, it.id
        assert it.risk_family_in or it.risk_id_in, it.id
        assert any((it.natal_sinsal_in, it.luck_sinsal_in, it.structure_in, it.hap_in)), it.id
        assert 0.0 < it.strength <= 0.35, it.id  # 배경 계수는 낮게(신살 문구 완화 원칙)
        assert not it.reviewed  # 감수 전 상태 위조 금지
        assert not any(w in it.label_ko for w in _FORBIDDEN_LABEL_WORDS), it.id
    # lint: 길 극성·배경 없음·미등록 family·미등록 구조 플래그를 거부한다.
    bad = {"items": [
        {"id": "X1", "riskFamilyIn": ["cashflow"], "polarityRoleIn": ["YONG"],
         "luckSinsalIn": ["겁살"], "strength": 0.2, "labelKo": "a"},
        {"id": "X2", "riskFamilyIn": ["cashflow"], "polarityRoleIn": ["GI"],
         "strength": 0.2, "labelKo": "a"},
        {"id": "X3", "riskFamilyIn": ["no_such_family"], "polarityRoleIn": ["GI"],
         "luckSinsalIn": ["겁살"], "strength": 0.2, "labelKo": "a"},
        {"id": "X3", "riskFamilyIn": ["cashflow"], "polarityRoleIn": ["GI"],
         "structureIn": ["bogus_flag"], "strength": 0.2, "labelKo": "a"},
    ]}
    errors = _lint_risk_auxiliary(_DICTS, bad)
    assert any("X1" in e and "흉 극성" in e for e in errors)
    assert any("X2" in e and "배경 조건" in e for e in errors)
    assert any("X3" in e and "미등록 riskFamily" in e for e in errors)
    assert any("X3" in e and "미등록 structureIn" in e for e in errors)
    assert any("id 중복" in e for e in errors)


# ── 2. 적용 — 순수·유계·후보 불변 ─────────────────────────────────────────────


def _pick(cands, family: str):
    return next(c for c in cands if c.risk_family == family)


def test_apply_adds_amplifier_evidence_only_on_adverse_polarity(shadow_off) -> None:
    acc = _pick(shadow_off, "accident_injury")
    other = _pick(shadow_off, "cashflow")
    facts = AuxiliaryFacts(
        polarity_role="GI", natal_sinsal=frozenset({"백호"}), luck_sinsal=frozenset(),
        structure_flags=frozenset(), hap_flags=frozenset(),
    )
    out = apply_auxiliary_amplifiers([acc, other], facts, dictionaries_dir=_DICTS)
    assert len(out) == 2 and out[1] is other  # 무매칭 후보는 같은 객체(byte 불변)
    amp = out[0]
    added = [e for e in amp.evidence if e.source.startswith("aux:")]
    assert [e.code for e in added] == ["AUX_ACC_NATAL_BLOOD"]
    assert added[0].role is EvidenceRole.AMPLIFIER and added[0].source_group == "auxiliary"
    assert added[0].evidence_id == f"{acc.period_key}|aux:AUX_ACC_NATAL_BLOOD"
    assert amp.aux_bonus == pytest.approx(round(_AUX_MAX_BONUS * 0.3, 6))
    # 근거·aux_bonus 외 전 필드 불변(후보 신설·적격·원인·identity 불개입).
    assert amp.model_dump(exclude={"evidence", "aux_bonus"}) == acc.model_dump(
        exclude={"evidence", "aux_bonus"})
    assert amp.evidence[: len(acc.evidence)] == acc.evidence
    # 길 극성이면 같은 배경이어도 아무것도 붙지 않는다(신살 단독 트리거 금지).
    good = AuxiliaryFacts(
        polarity_role="YONG", natal_sinsal=frozenset({"백호"}), luck_sinsal=frozenset(),
        structure_flags=frozenset(), hap_flags=frozenset(),
    )
    assert apply_auxiliary_amplifiers([acc], good, dictionaries_dir=_DICTS) == [acc]
    # 조건 종류 사이 AND — 원국+운 동반 요구 항목(AUX_LEG_GUGYO)은 한쪽만으로 매칭되지 않는다.
    leg = _pick(shadow_off, "document_liability")
    half = AuxiliaryFacts(
        polarity_role="GI", natal_sinsal=frozenset({"구교살"}), luck_sinsal=frozenset(),
        structure_flags=frozenset(), hap_flags=frozenset(),
    )
    assert apply_auxiliary_amplifiers([leg], half, dictionaries_dir=_DICTS) == [leg]
    both = AuxiliaryFacts(
        polarity_role="GI", natal_sinsal=frozenset({"구교살"}), luck_sinsal=frozenset({"재살"}),
        structure_flags=frozenset(), hap_flags=frozenset(),
    )
    got = apply_auxiliary_amplifiers([leg], both, dictionaries_dir=_DICTS)[0]
    assert "AUX_LEG_GUGYO" in {e.code for e in got.evidence}


def test_bonus_is_saturating_and_capped(shadow_off) -> None:
    acc = _pick(shadow_off, "accident_injury")
    facts = AuxiliaryFacts(
        polarity_role="GI_STRONG", natal_sinsal=frozenset({"백호", "양인"}),
        luck_sinsal=frozenset({"겁살", "탕화살", "낙정관살"}),
        structure_flags=frozenset(), hap_flags=frozenset(),
    )
    amp = apply_auxiliary_amplifiers([acc], facts, dictionaries_dir=_DICTS)[0]
    codes = {e.code for e in amp.evidence if e.source.startswith("aux:")}
    assert codes == {"AUX_ACC_NATAL_BLOOD", "AUX_ACC_LUCK_BLOOD", "AUX_ACC_LUCK_TANGHWA"}
    expected = _AUX_MAX_BONUS * (1 - (1 - 0.3) * (1 - 0.35) * (1 - 0.25))
    assert amp.aux_bonus == pytest.approx(round(expected, 6))
    assert 0 < amp.aux_bonus <= _AUX_MAX_BONUS
    assert clamp_aux_bonus(5.0) == _AUX_MAX_BONUS and clamp_aux_bonus(-1.0) == 0.0
    # 재적용해도 같은 룰은 두 번 붙지 않는다(멱등).
    again = apply_auxiliary_amplifiers([amp], facts, dictionaries_dir=_DICTS)[0]
    assert again.evidence == amp.evidence and again.aux_bonus == amp.aux_bonus


# ── 3. 점수 불변식 ───────────────────────────────────────────────────────────


def test_scoring_axes_unchanged_only_priority_moves(shadow_off) -> None:
    acc = _pick(shadow_off, "accident_injury")
    facts = AuxiliaryFacts(
        polarity_role="GI", natal_sinsal=frozenset({"백호"}), luck_sinsal=frozenset(),
        structure_flags=frozenset(), hap_flags=frozenset(),
    )
    amp = apply_auxiliary_amplifiers([acc], facts, dictionaries_dir=_DICTS)[0]
    assert atom_semantics("aux:AUX_ACC_NATAL_BLOOD") == "amplifier"
    assert cause_occurrence_table([amp]) == cause_occurrence_table([acc])
    base = {acc.risk_id: 0.6}
    before = score_shadow([acc], base)[0]
    after = score_shadow([amp], base)[0]
    assert after.score_components == before.score_components  # 6축 전부 불변
    assert after.confidence == before.confidence
    assert after.aux_bonus == amp.aux_bonus and before.aux_bonus == 0.0
    comp = before.score_components
    assert comp is not None
    raw0 = risk_priority(comp)[0]
    raw1 = risk_priority(comp, aux_bonus=after.aux_bonus)[0]
    if raw0 > 0:
        assert raw1 == pytest.approx(round(raw0 * (1 + after.aux_bonus), 6), abs=2e-6)
    assert structural_priority(comp, aux_bonus=after.aux_bonus) >= structural_priority(comp)


# ── 4. 엔진 플래그 게이트·표현 계층 ───────────────────────────────────────────


def test_engine_flag_gate_and_byte_invariance(shadow_off, shadow_on) -> None:
    assert shadow_off and len(shadow_off) == len(shadow_on)
    assert all(c.aux_bonus == 0.0 for c in shadow_off)
    assert not any(e.source.startswith("aux:") for c in shadow_off for e in c.evidence)
    amplified = [c for c in shadow_on if c.aux_bonus > 0]
    assert amplified, "데굴 차트 2026~2027 월운에서 보조 증폭 후보가 하나도 없다"
    for off, on in zip(shadow_off, shadow_on, strict=True):
        assert off.model_dump(exclude={"evidence", "aux_bonus"}) == on.model_dump(
            exclude={"evidence", "aux_bonus"})
        if on.aux_bonus == 0.0:
            assert on.model_dump() == off.model_dump()
        for e in on.evidence:
            if e.source.startswith("aux:"):
                assert e.role is EvidenceRole.AMPLIFIER
                assert atom_semantics(e.source) == "amplifier"
    assert max(c.aux_bonus for c in amplified) <= _AUX_MAX_BONUS


def test_presentation_carries_aux_labels(shadow_off, shadow_on) -> None:
    labels = auxiliary_labels(_DICTS)
    assert len(labels) == 15
    payload_on = build_risk_payload(shadow_on)
    payload_off = build_risk_payload(shadow_off)
    assert payload_on is not None and payload_off is not None
    for rec in payload_off["presentationRecords"]:
        assert rec["auxiliarySignals"] == []
    seen = [rec["auxiliarySignals"] for rec in payload_on["presentationRecords"]]
    assert all(isinstance(s, list) for s in seen)
    for rec in payload_on["llmRiskEpisodes"]:
        assert "auxiliarySignals" in rec
        for label in rec["auxiliarySignals"]:
            assert label in labels.values()  # 라벨은 사전 문구 그대로(즉석 작문 없음)
