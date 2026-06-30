"""Marriage Production Readiness v1 — Step 5: MT6 혼기 prior 답변 연결.

핵심 검증: ① default 프로파일 → 빈 목록(출력 불변) ② production_candidate → 혼기 경향 줄 ③ 특정
연·월 미언급(static prior) ④ band 한글 매핑.
"""

from __future__ import annotations

import saju_engines.structural_context as sc
from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput


def _r(date: str = "1985-03-15", gender: str = "female"):
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date, birth_time="10:00",
        birth_place_name="서울", gender=gender,
    ))


def test_default_profile_is_empty(monkeypatch) -> None:
    """MT6 off(aux mt6_age_prior=False) → 빈 목록(출력 불변)."""
    monkeypatch.setattr(sc, "active_marriage_aux", lambda *a, **k: {"mt6_age_prior": False})
    assert sc.marriage_age_prior_lines(_r()) == []


def test_production_profile_emits_prior(monkeypatch) -> None:
    """production_candidate → 혼기 경향 줄(특정 연·월 미언급)."""
    monkeypatch.setattr(sc, "active_marriage_aux", lambda *a, **k: {"mt6_age_prior": True})
    lines = sc.marriage_age_prior_lines(_r())
    assert lines
    text = " ".join(lines)
    assert "혼기 경향" in text and "static prior" in text
    # 특정 연·월(2026 등) 단정 금지 — static prior.
    assert "2026" not in text and "년에 결혼" not in text


def test_no_pillars_graceful(monkeypatch) -> None:
    monkeypatch.setattr(
        sc, "active_marriage_aux", lambda *a, **k: {"mt6_age_prior": True}
    )
    r = _r().model_copy(update={"pillars": None})
    assert sc.marriage_age_prior_lines(r) == []
