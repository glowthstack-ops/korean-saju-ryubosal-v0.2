"""테마 리포트 기간 섹션의 운 간지별 강의 문구 배선(2026-10-30 데굴님 "그래 제대로 배선해").

2026-10-29 강의 번역층의 운 간지별 문구(직장 운 결·재물 운 결·이별운 운 문구·다름의 인정)는 채팅
말미 블록에만 있었다. 테마 집중 리포트의 기간 섹션과 연도별 상세 페이지에 같은 블록이 붙고, 다른
테마에는 새지 않는지 고정한다. 픽스처는 docs/05 검증 픽스처(2026년 조건 성립 명식).
"""

from __future__ import annotations

from datetime import date

from saju_api.services import report_service
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

_TODAY = date(2026, 10, 30)


def _spec(topic: str) -> ReportSpec:
    return ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic=topic,
        period=ReportPeriod(start="2026-01-01", end="2026-12-31"),
    )


def _birth(d: str, g: str = "male") -> BirthInput:
    return BirthInput(
        calendar_type="solar", birth_date=date.fromisoformat(d), birth_time="10:00",
        birth_place_name="서울", gender=g,
    )


def _bodies(topic: str, d: str, g: str = "male") -> dict[str, str]:
    ctxs = report_service.plan_report(_birth(d, g), _spec(topic), _TODAY)
    return {c.section_id: c.body_prompt for c in ctxs}


def test_career_theme_period_sections_carry_career_exit_lecture() -> None:
    """1978-01-02 남 — 2026-03 辛卯(원국 상관 × 운 정관 자기형)·2026-04 壬辰(편인 휴직)."""
    b = _bodies("career", "1978-01-02")
    j06 = b["J-06"]
    assert "[직장 운 결 — 강의 번역층" in j06
    assert "원국 천간의 상관이 운의 정관과 부딪히는 기간" in j06  # 자기형
    assert "복귀를 전제로" in j06  # 편인 휴직
    assert j06.count("편인 운 공통") <= 1
    assert "[직장 운 결 — 강의 번역층" in b["J-05-Y2026"]  # 연도별 상세 페이지
    assert all("[재물 운 결" not in body for body in b.values())
    assert all("[관계 관점 — 다름의 인정]" not in body for body in b.values())


def test_wealth_theme_period_sections_carry_wealth_period_lecture() -> None:
    """1971-10-12 남 — 戊 편인 운(2026-10 戊戌) 도식 1회 + 재물 운 결 블록."""
    b = _bodies("wealth", "1971-10-12")
    hit = [sid for sid, body in b.items() if "[재물 운 결 — 재물 강의 번역층" in body]
    assert hit and any(sid.startswith("W-0") for sid in hit), hit
    for sid in hit:
        assert b[sid].count("편인 운 공통") <= 1, sid
    assert all("[직장 운 결" not in body for body in b.values())


def test_relationship_theme_period_sections_carry_separation_lecture() -> None:
    """1980-05-24 여 — 관성 3%(매우 약) × 2026-10 戊戌 상관 → 이별운 운 문구 + 다름의 인정."""
    b = _bodies("relationship", "1980-05-24", "female")
    r05 = b["R-05"]
    assert "[연애·관계 운 결 — 이별운 강의 번역층" in r05
    assert "[관계 관점 — 다름의 인정]" in r05
    assert "[관계 관점 — 다름의 인정]" in b["R-05-Y2026"]
    assert all("[직장 운 결" not in body for body in b.values())
    assert all("[재물 운 결" not in body for body in b.values())


def test_natal_sections_do_not_carry_lecture_blocks() -> None:
    b = _bodies("career", "1978-01-02")
    for sid in ("J-01", "J-02"):
        assert "[직장 운 결" not in b[sid], sid
