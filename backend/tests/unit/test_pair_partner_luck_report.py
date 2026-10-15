"""테마 애정·관계운 궁합 모드 — 상대 운 점수화·두 사람 표·호출 유형·제목(2026-10-15 승인 ③④).

종전엔 상대는 원국만 계산해 RP-06·RP-07·연도별 상세 페이지가 본인 운만 담았다(데굴님 지적
"연도별 상세는 본인에 대한 서술만 제공"). 상대 명식도 같은 엔진으로 점수화해 본인 표 뒤에 상대 표를
붙이고, 그 섹션만 입력 상한 두 배 유형을 쓴다. 단독 모드·다른 테마는 불변(반례).
"""

from __future__ import annotations

from datetime import date

from saju_api.services.report_service import (
    _expand_report_plans,
    _ReportData,
    _section_call_type,
    build_section_context,
)
from saju_engines.llm_guard import CALL_LIMITS
from saju_engines.report_plan import build_section_plans
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import InlineBirth, SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec, SectionPlan

_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:40",
    birth_place_name="서울", gender="male",
)
_PARTNER = BirthInput(
    calendar_type="solar", birth_date="1955-03-08", birth_time="10:00",
    birth_place_name="서울", gender="female",
)
_TODAY = date(2026, 7, 3)
_SELF_HEAD = "[아래 표는 본인(데굴) 기준]"
_PARTNER_HEAD = "[아래 표는 상대(어머니) 기준]"
_DIRECTIVE = "[두 사람 표 읽기]"


def _pair_spec(relation: str | None, topic: str = "relationship") -> ReportSpec:
    return ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[
            SubjectRef(kind=SubjectKind.SELF, label="데굴"),
            SubjectRef(
                kind=SubjectKind.INLINE_TEMP, label="어머니",
                inline_birth=InlineBirth(date="1955-03-08", time="10:00", gender="F"),
                relation_type=relation,
            ),
        ],
        topic=topic, period=ReportPeriod(start="2026-07", end="2031-12"),
    )


def _solo_spec() -> ReportSpec:
    return ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="데굴")],
        topic="relationship", period=ReportPeriod(start="2026-07", end="2031-12"),
    )


def _data(spec: ReportSpec, *, partner: bool) -> tuple[_ReportData, list[SectionPlan]]:
    data = _ReportData(
        _BIRTH, spec, _TODAY, owner_id=None, subject_id=None,
        partner_birth=_PARTNER if partner else None,
    )
    return data, _expand_report_plans(build_section_plans(spec), data)


def _body(spec: ReportSpec, data: _ReportData, plans: list[SectionPlan], sid: str) -> str:
    plan = next(p for p in plans if p.section_id == sid)
    return build_section_context(plan, spec, data).body_prompt


def test_pair_call_limit_registered_as_double() -> None:
    """한도표 — 궁합 상대 운 표 섹션 유형은 집중 섹션의 두 배 입력, 출력·글자수 동일."""
    base, pair = CALL_LIMITS["report_focus_section"], CALL_LIMITS["report_focus_section_pair"]
    assert pair.max_input_tokens == base.max_input_tokens * 2
    assert pair.max_output_tokens == base.max_output_tokens
    assert pair.max_output_chars == base.max_output_chars
    # 동반자 대화는 제한 없음(공급자 컨텍스트 한도) — 출력 상한은 그대로.
    assert CALL_LIMITS["chat_compare"].max_input_tokens == 1_000_000
    assert CALL_LIMITS["chat_compare"].max_output_tokens == 5_500


def test_partner_luck_is_scored_and_tables_attached() -> None:
    """상대 운이 점수화되고 RP-06·RP-07·연도별 페이지에 본인·상대 표가 머리줄과 함께 붙는다."""
    spec = _pair_spec("romance")
    data, plans = _data(spec, partner=True)
    assert data.partner_scored is not None and len(data.partner_scored) > 0
    assert data.partner_result is not None and data.partner_result.luck_cycles is not None
    # 상대 명식에도 예측 창 월운이 다년으로 주입됐다(종전 12개월만).
    assert len({p.label[:4] for p in data.partner_result.luck_cycles.monthly_luck}) >= 5
    for sid in ("RP-06", "RP-07", "RP-06-Y2027"):
        body = _body(spec, data, plans, sid)
        assert _SELF_HEAD in body and _PARTNER_HEAD in body and _DIRECTIVE in body, sid
        assert body.index(_SELF_HEAD) < body.index(_PARTNER_HEAD), sid
    year_page = _body(spec, data, plans, "RP-06-Y2027")
    assert "[이 해 세운 — 2027년]" in year_page
    assert "[이 해 세운 — 상대(어머니), 2027년]" in year_page
    # 상대 표가 없는 RP 섹션은 머리줄·지시 없음.
    for sid in ("RP-01", "RP-04", "RP-09"):
        body = _body(spec, data, plans, sid)
        assert _PARTNER_HEAD not in body and _DIRECTIVE not in body, sid


def test_section_call_type_only_for_pair_luck_sections() -> None:
    """호출 유형 — 상대 운 표가 붙는 섹션만 pair, 나머지 RP 섹션은 기본 유형."""
    spec = _pair_spec("romance")
    data, _ = _data(spec, partner=True)
    for sid in ("RP-06", "RP-07", "RP-06-Y2027", "RP-06-Y2031"):
        assert _section_call_type("report_focus_section", data, sid) == "report_focus_section_pair"
    for sid in ("RP-01", "RP-03", "RP-04", "RP-05", "RP-08", "RP-09", "RP-10"):
        assert _section_call_type("report_focus_section", data, sid) == "report_focus_section"


def test_non_romantic_partner_scored_is_filtered() -> None:
    """비연애 관계 — 상대 운에서도 결혼·인연·출산 신호가 빠진다(본인과 같은 오버레이)."""
    spec = _pair_spec("mother")
    data, _ = _data(spec, partner=True)
    assert data.partner_scored is not None and data.partner_scored
    assert not any(
        str(c.event_key) in {"marriage_signal", "new_relationship", "childbirth"}
        for c in data.partner_scored
    )
    romance_data, _ = _data(_pair_spec("romance"), partner=True)
    assert romance_data.partner_scored is not None
    assert any(str(c.event_key) == "marriage_signal" for c in romance_data.partner_scored)


def test_pair_titles_non_romantic_rp02_and_year_pages() -> None:
    """제목 — 비연애면 RP-02 '나의 관계 성향', 궁합 연도별 페이지는 두 사람 라벨."""
    spec = _pair_spec("mother")
    _, plans = _data(spec, partner=True)
    by_id = {p.section_id: p for p in plans}
    assert by_id["RP-02"].title == "나의 관계 성향"
    assert by_id["RP-06-Y2027"].title == "연도별 상세 — 2027년 · 데굴·어머니"
    # 연애 관계는 RP-02 제목 불변, 연도별 페이지는 두 사람 라벨.
    _, plans_r = _data(_pair_spec("romance"), partner=True)
    by_id_r = {p.section_id: p for p in plans_r}
    assert by_id_r["RP-02"].title == "나의 애정 성향"
    assert by_id_r["RP-06-Y2027"].title == "연도별 상세 — 2027년 · 데굴·어머니"


def test_solo_relationship_and_other_theme_unchanged_counterexample() -> None:
    """반례 — 단독 애정운(R-*)·다른 테마는 상대 운·머리줄·pair 유형·제목 변형이 없다."""
    solo = _solo_spec()
    data, plans = _data(solo, partner=False)
    assert data.partner_scored is None
    by_id = {p.section_id: p for p in plans}
    assert by_id["R-02"].title == "나의 애정 성향"
    assert by_id["R-05-Y2027"].title == "연도별 상세 — 2027년"
    for sid in ("R-05", "R-06", "R-05-Y2027"):
        body = _body(solo, data, plans, sid)
        assert "[아래 표는" not in body and _DIRECTIVE not in body, sid
        assert _section_call_type("report_focus_section", data, sid) == "report_focus_section"
    # 궁합 모드라도 topic 이 relationship 이 아니면 pair 목차가 아니다(상대 운 표 미부착).
    career = _pair_spec("coworker", topic="career")
    cdata, cplans = _data(career, partner=True)
    assert all(not p.section_id.startswith("RP-") for p in cplans)
    assert _section_call_type("report_focus_section", cdata, "J-05") == "report_focus_section"
