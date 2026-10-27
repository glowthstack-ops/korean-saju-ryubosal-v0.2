"""합 체계 대조 P0 회귀(2026-10-25 데굴님 승인).

리포트 기간별 운 합 라벨·탐합망충 규칙 로더·모드 검증.

hap_modes 자체 규칙(격위 상한·쟁합 소멸·육합 방해·공합·합거 노트)은 test_hap_modes.py 에 있다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.report_service import _ReportData
from saju_engines.event_engine_v2 import EventEngineV2, load_tamhap_rules
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_BIRTH = BirthInput(
    calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
    birth_place_name="서울", gender="male", apply_true_solar_time=False,
)


def test_report_luck_hap_lines_are_per_period_with_layer_label() -> None:
    """P0-1 — 후보 기간별로 판정하고 `[기간 간지 · 대운 간지]` 라벨을 붙인다.

    기간 혼합·운–운 쌍 금지.
    """
    spec = ReportSpec(
        product_code="RPT_FOCUS", subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic="career", period=ReportPeriod(start="2024-01", end="2030-12"),
    )
    data = _ReportData(_BIRTH, spec, date(2026, 6, 15), owner_id=None, subject_id=None)
    lines = data.luck_hap_lines(data.candidates)
    assert lines
    for ln in lines:
        assert ln.startswith("["), ln
        head = ln[1:ln.index("]")]
        period, _, rest = head.partition(" ")
        assert period[:4].isdigit() and len(rest.split()[0]) == 2  # 'YYYY[-MM] 干支'
    # 같은 기간 라벨 안의 줄만 그 기간 간지·대운으로 판정됐다 — 다른 기간 글자끼리의 쌍이 없다.
    periods = {ln[1:ln.index("]")] for ln in lines}
    assert all(("대운 " in p) or (" " in p) for p in periods)


def test_tamhap_rules_loaded_from_event_dictionaries() -> None:
    """P0-4 — events/*.json 의 relationAlso(six_combination) 감점이 소비자(로더)로 읽힌다."""
    rules = load_tamhap_rules(_DICTS)
    assert rules == {"career_change": -0.2, "relocation": -0.25}


def test_tamhap_mode_off_loads_no_rules_and_shadow_default_records_only() -> None:
    off = EventEngineV2(_DICTS, risk_mode="shadow", tamhap_mangchung_mode="off")
    assert off._tamhap_rules == {}
    shadow = EventEngineV2(_DICTS, risk_mode="shadow")
    assert shadow._tamhap_mode == "shadow" and shadow._tamhap_rules
    assert shadow.take_tamhap_shadow() == []


def test_tamhap_mode_flag_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    from saju_engines import period_v2_config as c

    monkeypatch.setattr(c, "TAMHAP_MANGCHUNG_MODE", "sometimes")
    with pytest.raises(c.ConfigurationError):
        c.validate_flags()
    monkeypatch.setattr(c, "TAMHAP_MANGCHUNG_MODE", "shadow")
    c.validate_flags()


def test_tamhap_shadow_detects_clash_member_in_six_and_apply_discounts() -> None:
    """P0-4 — 2022 壬寅: 寅申충의 寅이 원국 亥와 寅亥合(木 相) → 탐합망충 후보.

    shadow=기록만, apply=감산.
    """
    from saju_api.services.chat_service import calculate
    from saju_shared_types.ganji_calendar import GanjiLevel

    birth = _BIRTH.model_copy(update={"reference_date": date(2022, 7, 1)})
    result = calculate(birth)
    shadow_eng = EventEngineV2(_DICTS, risk_mode="shadow", tamhap_mangchung_mode="shadow")
    cands = shadow_eng.score(result, levels={GanjiLevel.YEAR})
    recs = shadow_eng.take_tamhap_shadow()
    rec = next(r for r in recs if r["period"] == "2022")
    assert rec["luck_branch"] == "寅" and any(b.startswith("寅亥合") for b in rec["bound_by"])
    assert "career_change" in rec["events"]
    base = next(c for c in cands if c.period == "2022" and str(c.event_key) == "career_change")
    assert "tamhap_mangchung" not in base.contributions  # shadow 는 점수 불변
    apply_eng = EventEngineV2(_DICTS, risk_mode="shadow", tamhap_mangchung_mode="apply")
    cands2 = apply_eng.score(result, levels={GanjiLevel.YEAR})
    applied = next(c for c in cands2 if c.period == "2022" and str(c.event_key) == "career_change")
    assert applied.contributions.get("tamhap_mangchung") == -0.2
    assert applied.score < base.score
    assert any(code.startswith("合_탐합망충_寅") for code in applied.reason_codes)
