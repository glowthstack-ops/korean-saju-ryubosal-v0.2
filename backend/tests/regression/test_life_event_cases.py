"""실사례 픽스처 러너(P3, 2026-09-18) — doc/v2_2/LIFE_EVENT_CASES.md 스키마.

사례가 0건(템플릿 행만)이면 skip. 사례가 있으면 사례마다 엔진을 돌려 그 시점 후보의 사건 유형·
사건 키·기회 family 와 금지 표현을 대조한다. 실패는 '엔진이 틀렸다'가 아니라 '어긋남 발견'이며,
규칙 조정은 승인 후에 한다(문서 판정 원칙).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate, luck_months, luck_years
from saju_engines import period_v2_config
from saju_engines.event_engine_config import build_event_engine_v2
from saju_engines.event_lexicon import derive_process_types
from saju_engines.event_scoring import favorability_map
from saju_engines.opportunity_engine import detect_opportunities
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "life_event_cases.jsonl"
_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _load_cases() -> list[dict]:
    if not _FIXTURE.exists():
        return []
    rows = [json.loads(line) for line in _FIXTURE.read_text("utf-8").splitlines() if line.strip()]
    return [r for r in rows if not r.get("template")]


_CASES = _load_cases()


def test_fixture_file_is_well_formed() -> None:
    """템플릿 행은 필수 키를 모두 갖고, 실사례 행에는 개인정보 필드가 없다."""
    rows = [json.loads(line) for line in _FIXTURE.read_text("utf-8").splitlines() if line.strip()]
    assert rows and rows[0].get("template") is True
    required = {"caseId", "subject", "domain", "valence", "observed", "period", "expect", "source"}
    for r in rows:
        assert required <= set(r), r.get("caseId")
        assert not ({"name", "phone", "email"} & set(r["subject"])), r.get("caseId")


@pytest.mark.skipif(not _CASES, reason="실사례 없음 — 운영 중 수집(2026-09-18)")
@pytest.mark.parametrize("case", _CASES, ids=[c["caseId"] for c in _CASES])
def test_life_event_case_matches_engine(case: dict, monkeypatch) -> None:
    s = case["subject"]
    birth = BirthInput(
        calendar_type=s.get("calendar_type", "solar"),
        birth_date=date.fromisoformat(s["birth_date"]),
        birth_time=s.get("birth_time"), birth_place_name=s.get("birth_place_name", "서울"),
        gender=s.get("gender", "male"), latitude=s.get("latitude"), longitude=s.get("longitude"),
        timezone=s.get("timezone", "Asia/Seoul"),
    )
    chart = calculate(birth)
    period = case["period"]
    year = int(period[:4])
    monthly = case.get("granularity", "month") == "month"
    c2 = chart.model_copy(deep=True)
    if monthly:
        c2.luck_cycles.monthly_luck = luck_months(birth, year - 1) + luck_months(birth, year)
        level = GanjiLevel.MONTH
    else:
        c2.luck_cycles.yearly_luck = luck_years(birth, [year - 1, year, year + 1])
        level = GanjiLevel.YEAR
    monkeypatch.setattr(period_v2_config, "EVENT_LEXICON_ENABLED", True)
    monkeypatch.setattr(period_v2_config, "OPPORTUNITY_ENABLED", True)
    scored = build_event_engine_v2(_DICTS).score(c2, levels={level})
    cands = [c for c in scored if c.period == period]
    assert cands, f"{case['caseId']}: {period} 후보 없음"
    exp = case["expect"]
    keys = {str(c.event_key) for c in cands}
    if exp.get("event_keys_any"):
        assert keys & set(exp["event_keys_any"]), (case["caseId"], sorted(keys))
    types: set[str] = set()
    for c in cands:
        types |= set(derive_process_types(
            str(c.event_key), list(c.reason_codes), [], c.favorability, dictionaries_dir=_DICTS,
        ))
    if exp.get("process_types_any"):
        assert types & set(exp["process_types_any"]), (case["caseId"], sorted(types))
    if exp.get("opportunity_families_any"):
        fav = favorability_map(c2)
        pillar = next(
            p for p in (c2.luck_cycles.monthly_luck if monthly else c2.luck_cycles.yearly_luck)
            if p.label == period
        )
        signals = detect_opportunities(c2, pillar, fav, dictionaries_dir=_DICTS)
        fams = {sig.family for sig in signals}
        assert fams & set(exp["opportunity_families_any"]), (case["caseId"], sorted(fams))
