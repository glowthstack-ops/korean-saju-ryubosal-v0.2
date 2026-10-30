"""직장 강의 문구(휴직·겁재 천간·도식)의 도메인 게이트(2026-10-30 데굴님 "수정하는게 좋겠어").

리포트 후보 클러스터의 '운 결' 줄과 채팅 후보 note·단일 기간 근거가 섹션·질문 도메인과 무관하게
직장 전용 문구를 붙여 관계·건강·방위 섹션과 관계 질문에 '휴직·이직' 서사가 새던 결함. 일반(총운)·
직업에만 붙고, 도식 문구는 한 섹션의 클러스터 목록 안에서 1회만.
"""

from __future__ import annotations

from datetime import date

from saju_api.services import chat_service, report_service
from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import dosik_texts, incoming_ten_god_note
from saju_engines.event_scoring import favorability_map
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

_TODAY = date(2026, 10, 30)
_LEAVE = "복귀를 전제로"


def _birth(d: str, t: str = "10:00", g: str = "male") -> BirthInput:
    return BirthInput(
        calendar_type="solar", birth_date=date.fromisoformat(d), birth_time=t,
        birth_place_name="서울", gender=g,
    )


def _spec(pc: str, topic: str | None) -> ReportSpec:
    return ReportSpec(
        product_code=pc, subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic=topic, period=ReportPeriod(start="2026-01-01", end="2026-12-31"),
    )


def _bodies(pc: str, topic: str | None, d: str) -> dict[str, str]:
    ctxs = report_service.plan_report(_birth(d), _spec(pc, topic), _TODAY)
    return {c.section_id: c.body_prompt for c in ctxs}


def test_note_gate_switches_career_texts() -> None:
    chart = calculate(_birth("1978-01-02"))
    dm, fav = chart.pillars.day_master, favorability_map(chart)
    on = incoming_ten_god_note(dm, "壬辰", fav, natal=chart)  # 편인 운
    off = incoming_ten_god_note(dm, "壬辰", fav, natal=chart, career_lecture=False)
    assert _LEAVE in on and _LEAVE not in off
    assert off and off == on.split(" · 편인이 들어오는 기간")[0]  # 앞부분(십성 해석)은 동일


def test_career_theme_carries_leave_text_once_per_ganji() -> None:
    """직업 섹션은 클러스터 줄이 아니라 말미 [직장 운 결] 블록이 간지당 1회 담당한다."""
    b = _bodies("RPT_FOCUS", "career", "1978-01-02")
    assert b["J-06"].count(_LEAVE) == 1 and "[직장 운 결" in b["J-06"]


def test_relationship_theme_has_no_career_lecture_texts() -> None:
    b = _bodies("RPT_FOCUS", "relationship", "1978-01-02")
    assert all(_LEAVE not in body for body in b.values())
    assert all("겁재가 천간으로 들어오는 기간" not in body for body in b.values())


def test_full_report_gates_by_section_domain() -> None:
    """1974-01-12 — 일반(총운) 세운 줄은 유지, 관계·건강 도메인 섹션은 제외, 도식은 섹션당 1회."""
    b = _bodies("RPT_FULL", None, "1974-01-12")
    dom = report_service._SECTION_DOMAIN
    assert _LEAVE in b["F-11"]  # 연 총운(일반)
    for sid, body in b.items():
        if dom.get(sid) in ("relationship", "health", "relocation", "education"):
            assert _LEAVE not in body, sid
    # 도메인 미매핑이지만 총운이 아닌 섹션(부모·가족/행동 전략/개운/방위)도 제외.
    for sid in ("F-17b", "F-19", "F-20", "F-20b"):
        assert _LEAVE not in b[sid], sid
    dosik = dosik_texts(calculate(_birth("1974-01-12")))
    if dosik:
        for sid, body in b.items():
            assert body.count(dosik[0]) <= 1, sid


def test_chat_relationship_question_has_no_career_note() -> None:
    b = BirthInput(
        calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date="2026-10-30",
    )
    love = chat_service.chat(b, "2027년 연애운은 어때?", _TODAY, dry_run=True).prompt_preview or ""
    work = chat_service.chat(b, "2027년 직장운은 어때?", _TODAY, dry_run=True).prompt_preview or ""
    assert "丁未" in love and _LEAVE not in love  # 2027 丁未 = 편인 운
    assert work.count(_LEAVE) == 1  # 같은 간지(丁未) 후보가 여럿이어도 첫 후보에만
