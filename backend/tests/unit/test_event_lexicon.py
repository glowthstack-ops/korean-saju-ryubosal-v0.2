"""사건 어휘 층(B1·B2·B6, 2026-09-18 데굴님 승인, 전문가 참고 기준) — 사전·분류·지시문·감사 회귀.

플래그 SAJU_EVENT_LEXICON_ENABLED(기본 OFF). 점수·판정은 어느 쪽도 바뀌지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

from saju_engines import period_v2_config
from saju_engines.event_lexicon import (
    derive_process_types,
    event_narration_directive,
    load_life_event_lexicon,
    load_process_types,
    process_type_legend,
)
from saju_engines.month_coverage_audit import audit_month_coverage, build_coverage_notes
from saju_shared_types.events import EventKey
from saju_shared_types.llm_input import MonthOverviewRow

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def test_event_forms_cover_all_21_keys_with_prob_sum_le_1() -> None:
    """event_forms.json — 21종 전량, prob 합 ≤ 1, 반대 발현 포함(손실 자동 결론 방지)."""
    d = json.loads((_DICTS / "event_forms.json").read_text("utf-8"))
    keys = {i["eventKey"] for i in d["items"]}
    assert keys == {str(k) for k in EventKey}
    for i in d["items"]:
        assert sum(f["prob"] for f in i["forms"]) <= 1.0 + 1e-9, i["eventKey"]
    windfall = next(i for i in d["items"] if i["eventKey"] == "windfall")
    assert any("반대 발현" in f["name"] for f in windfall["forms"])


def test_process_types_dictionary_has_both_valences() -> None:
    """공통 사건 유형 — 부정 15(회복 포함)·긍정 14, id 유일, '손실·손상'은 자동 결론 아님."""
    d = load_process_types(_DICTS)
    ids = [i.id for i in d.items]
    assert len(ids) == len(set(ids)) == 29
    positive = sum(1 for i in d.items if i.valence == "positive")
    assert positive == 15  # 회복·해소·재개(부정 목록의 마지막 항목) + 긍정 14
    loss = next(i for i in d.items if i.id == "loss")
    assert not loss.loss_is_conclusion and loss.match.favorability == "adverse"
    lex = load_life_event_lexicon(_DICTS)
    assert len(lex.areas) == 16 and all(a.negative_events and a.positive_events for a in lex.areas)
    assert any("빼앗긴다" in r.perceived for r in lex.perceived_to_observable)


def test_derive_process_types_is_deterministic_and_separates_loss() -> None:
    """경쟁 근거만 있으면 '경쟁·경합'이지 '손실·손상'이 아니다. 유리 밴드면 긍정 유형이 붙는다."""
    comp = derive_process_types(
        "wealth_change", ["格_운파격_비겁쟁재"], ["쟁합·투합 — 정이 전일하지 못함"], -0.3,
        dictionaries_dir=_DICTS,
    )
    assert "경쟁·경합" in comp and "손실·손상" not in comp
    loss = derive_process_types(
        "wealth_change", ["制_합거_길신손상"], [], -0.6, dictionaries_dir=_DICTS,
    )
    assert "손실·손상" in loss
    # 같은 손상 코드라도 유불리가 중립이면 손실 유형은 붙지 않는다.
    assert "손실·손상" not in derive_process_types(
        "wealth_change", ["制_합거_길신손상"], [], 0.0, dictionaries_dir=_DICTS,
    )
    good = derive_process_types(
        "job_gain", ["EXAM_PASS_관인상생"], ["관인상생"], 0.4, dictionaries_dir=_DICTS,
    )
    assert "선발·통과·승인" in good and len(good) <= 3
    # 사건 키 제한이 있는 유형은 근거(코드·신호)가 함께 있어야 붙는다 — 키만으로 붙이지 않는다.
    assert derive_process_types("relocation", [], [], 0.0, dictionaries_dir=_DICTS) == []
    moved = derive_process_types(
        "relocation", [], ["지지 충 — 이동 발동"], 0.0, dictionaries_dir=_DICTS,
    )
    assert "이동·교체·재편" in moved


def test_directive_and_legend_come_from_dictionary() -> None:
    """지시문은 사전의 분리 원칙·번역 표를 그대로 싣는다(즉석 작문 없음)."""
    text = event_narration_directive(_DICTS)
    assert "[사건 서술 계약" in text
    assert "경쟁이 생기는 것, 경쟁에서 탈락하는 것" in text
    assert "'내 몫을 빼앗긴다' → 배분 비율 변경" in text
    assert "12운성 병=질병" in text
    assert "경쟁이 생기는 것≠탈락≠손실" in process_type_legend(_DICTS)
    assert isinstance(period_v2_config.EVENT_LEXICON_ENABLED, bool)


def test_loss_overclaim_audit_flags_only_typed_months_without_loss_type() -> None:
    """B6 — 손실 확정어가 경쟁·배분 유형뿐인 달이면 위반, 손실 유형·미분류 달은 통과."""
    rows = [
        MonthOverviewRow(period="2026-11", ganji="己亥", luck_grade="혼합"),
        MonthOverviewRow(period="2026-12", ganji="庚子", luck_grade="기신운(부분)"),
        MonthOverviewRow(period="2027-01", ganji="辛丑", luck_grade="용신운(부분)"),
    ]
    types = {"2026-11": {"경쟁·경합", "배분·귀속 다툼"}, "2026-12": {"손실·손상"}}
    bad = (
        "11월에는 동업자에게 몫을 빼앗길 수 있습니다. 12월에는 손해를 볼 수 있습니다. "
        "1월은 잃는 달입니다."
    )
    audit = audit_month_coverage(bad, rows, ("2026-12",), process_types_by_period=types)
    assert "loss_overclaim" in audit.violations
    # 12월(손실 유형 있음)·1월(미분류)은 제외된다.
    assert [x.periods for x in audit.loss_overclaims] == [("2026-11",)]
    notes = build_coverage_notes(audit, rows)
    assert any("2026년 11월(己亥월)" in n and "자동 결론이 아닙니다" in n for n in notes)
    # 부정 문맥("빼앗기지 않")은 제외.
    ok = "11월에는 몫을 빼앗기지 않도록 정산 기준을 미리 정해 두세요."
    calm = audit_month_coverage(ok, rows, ("2026-12",), process_types_by_period=types)
    assert calm.loss_overclaims == [] and "loss_overclaim" not in calm.violations
