"""총운(RPT_FULL) 개편 — "나 → 대운 흐름 → 인생 그래프" (2026-11-07 데굴님 결정 1~5).

docs/10 §3. 1부는 원국 전용(세운·대운 언급 금지), 2부는 대운 전체(과거 포함)와 인생 그래프,
세운은 섹션으로 담지 않고 대운 페이지 연도 줄·그래프 마커의 재료로만 쓴다.
"""

from __future__ import annotations

from datetime import date

from saju_api.services import report_service
from saju_api.services.report_service import _ReportData, build_section_context
from saju_engines.life_graph import (
    KIND_AGE_RANGE,
    KIND_KO,
    PER_DAEWOON_CAP,
    PER_KIND_CAP,
    SCORE_GATE,
    build_life_graph,
    daewoon_summary_lines,
    marker_lines,
)
from saju_engines.report_plan import FULL_TOTAL_TARGET, build_section_plans
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.life_graph import MarkerKind
from saju_shared_types.report import ReportPeriod, ReportSpec

_TODAY = date(2026, 6, 11)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date="2026-06-11",
)
_FIXED = [
    "F-01", "F-02", "F-03", "F-04", "F-05", "F-06", "F-06b", "F-06c",
    "F-07", "F-14", "F-14b", "F-19", "F-20", "F-20b", "F-21", "F-22",
]


def _spec() -> ReportSpec:
    return ReportSpec(
        product_code="RPT_FULL",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start="1980-01", end="2070-12"),
    )


# ── 목차·의존성 ───────────────────────────────────────────────────────────────

def test_full_toc_v3_fixed_sections_and_target() -> None:
    plans = build_section_plans(_spec())
    assert [p.section_id for p in plans] == _FIXED
    mid = sum((p.target_chars.min + p.target_chars.max) / 2 for p in plans)
    assert abs(mid - FULL_TOTAL_TARGET) <= FULL_TOTAL_TARGET * 0.10


def test_full_toc_v3_depends_on() -> None:
    plans = {p.section_id: p for p in build_section_plans(_spec())}
    for sid in ("F-06b", "F-06c", "F-07", "F-14", "F-14b", "F-19", "F-20", "F-20b"):
        assert plans[sid].depends_on == ["F-04"], sid
    assert plans["F-21"].depends_on == ["F-14b", "F-19", "F-20", "F-20b"]
    for sid in ("F-01", "F-04", "F-22"):
        assert plans[sid].depends_on == []


# ── 확장·컨텍스트 ─────────────────────────────────────────────────────────────

def test_plan_report_full_v3_pages_and_blocks() -> None:
    contexts = report_service.plan_report(_BIRTH, _spec(), _TODAY)
    ids = [c.section_id for c in contexts]
    fixed = [i for i in ids if not i.startswith("F-14-D")]
    decades = [c for c in contexts if c.section_id.startswith("F-14-D")]
    assert fixed == _FIXED
    # 대운별 페이지 — 첫 대운부터(과거 포함), F-14 바로 뒤에 연속, F-14b 앞.
    f14 = ids.index("F-14")
    assert ids[f14 + 1 : f14 + 1 + len(decades)] == [c.section_id for c in decades]
    assert ids[f14 + 1 + len(decades)] == "F-14b"
    data = _ReportData(_BIRTH, _spec(), _TODAY)
    lc = data.result.luck_cycles
    assert lc is not None and lc.current_daewoon_index is not None
    assert len(decades) >= lc.current_daewoon_index + 2  # 지난 대운 페이지가 들어 있다
    d1 = decades[0]
    assert "[이 페이지의 대운]" in d1.body_prompt and "[지남]" in d1.body_prompt
    assert "[십년 세운 흐름" in d1.body_prompt
    assert "[이 대운의 주요 이벤트 후보 — 그래프 마커" in d1.body_prompt
    assert "회고" in d1.body_prompt  # 과거 대운 페이지 서술 계약
    assert "[연도별 흐름" not in d1.body_prompt
    # 첫 페이지는 출생~유년 포함(대운 시작 전 연도가 세운 흐름 표에 있다).
    assert "1980년" in d1.body_prompt or "1981년" in d1.body_prompt
    # F-14 인생 그래프 — 엔진 데이터 블록 + 해설만 지시.
    f14c = next(c for c in contexts if c.section_id == "F-14")
    assert "[인생 그래프 데이터" in f14c.body_prompt
    assert "[생애 변곡점 연표" not in f14c.body_prompt and "[연도별 흐름" not in f14c.body_prompt
    # F-14b 종합 — 전 마커 목록(대운별) + 단계 경계.
    f14b = next(c for c in contexts if c.section_id == "F-14b")
    assert "[대운별 주요 이벤트 정리" in f14b.body_prompt
    assert "초년(0–25세)" in f14b.body_prompt
    # F-07 — 전 대운 체크리스트(과거 포함) + 현재 마커.
    f07 = next(c for c in contexts if c.section_id == "F-07")
    assert "[대운 전수 체크리스트" in f07.body_prompt
    assert "← 현재 대운(오늘 포함, 엔진 판정)" in f07.body_prompt
    # 1부 신설 — 원국 전용(대운표·이벤트 후보 미부착) + 전용 재료.
    f06b = next(c for c in contexts if c.section_id == "F-06b")
    assert "[미혼 배우자상" in f06b.body_prompt and "[결혼·자산 자원 구조" in f06b.body_prompt
    assert "[대운표]" not in f06b.body_prompt and "[이벤트 후보" not in f06b.body_prompt
    f06c = next(c for c in contexts if c.section_id == "F-06c")
    assert "[직업 분야 근거" in f06c.body_prompt and "[조직 규모 적합" in f06c.body_prompt
    assert "[원국 횡재 그릇" in f06c.body_prompt
    assert "[대운표]" not in f06c.body_prompt
    # 세운 섹션 부재 — 올해 세운 grounding·월별 표가 어느 섹션에도 없다.
    assert not any("[해당 연 세운 grounding" in c.body_prompt for c in contexts)
    assert not any("[월별 흐름" in c.body_prompt for c in contexts)


# ── 인생 그래프 엔진 ──────────────────────────────────────────────────────────

def test_life_graph_markers_follow_caps_and_gate() -> None:
    data = _ReportData(_BIRTH, _spec(), _TODAY)
    g = data.life_graph
    assert g is not None and g.daewoons and g.years
    assert g.birth_year == 1980 and g.end_year == 2070
    assert {d.status for d in g.daewoons} >= {"past", "current", "future"}
    for d in g.daewoons:
        assert len(d.markers) <= PER_DAEWOON_CAP
        kinds = [m.kind for m in d.markers]
        assert all(kinds.count(k) <= PER_KIND_CAP for k in set(kinds))
        for m in d.markers:
            assert m.score + (10 if m.risk_backed else 0) >= SCORE_GATE
            assert d.start_year <= m.year <= d.end_year
            assert m.kind_ko == KIND_KO[m.kind]
    # 위기(건강·금전)는 흉·혼합 방향만, 종류별 나이 타당성(결혼·취업 18+, 이직 20~70, 취업 ≤70).
    assert all(
        m.tone != "길" for m in g.markers
        if m.kind in (MarkerKind.CRISIS_MONEY, MarkerKind.CRISIS_HEALTH)
    )
    for m in g.markers:
        lo, hi = KIND_AGE_RANGE[m.kind]
        assert lo <= m.age <= hi, (m.kind, m.age)
        if m.age < 18 and m.kind in (MarkerKind.RELOCATION, MarkerKind.CRISIS_MONEY):
            assert "가족" in m.note
        else:
            assert m.note == ""
    # 연속 대운이 창을 빠짐없이 덮는다(첫 페이지는 출생년부터).
    assert g.daewoons[0].start_year == 1980
    for a, b in zip(g.daewoons, g.daewoons[1:], strict=False):
        assert b.start_year == a.end_year + 1
    # 프롬프트 줄 — 마커·대운 요약.
    lines = marker_lines(g)
    assert len(lines) == len(g.markers)
    assert all("점" in ln for ln in lines)
    assert len(daewoon_summary_lines(g)) == len(g.daewoons)


def test_life_graph_none_without_daewoon_table() -> None:
    data = _ReportData(_BIRTH, _spec(), _TODAY)
    bare = data.result.model_copy(deep=True)
    assert bare.luck_cycles is not None
    bare.luck_cycles.daewoon_table = []
    assert build_life_graph(bare, data._lifetime_result, data.lifetime_pool, 1980, 2070) is None


# ── 생성 결과에 구조 데이터 부착 ──────────────────────────────────────────────

def test_generate_full_attaches_life_graph_data_to_f14() -> None:
    from saju_engines.report_builder import ReportBuilder

    spec = _spec()
    data = _ReportData(_BIRTH, spec, _TODAY)

    def mock_generate(plan, context, attempt):
        body = "이 시기에는 변화의 기운이 차분히 흐르고 있어요. "
        while len(body) < plan.target_chars.min:
            body += "기운을 살펴보면 좋아요. "
        return body[: plan.target_chars.max], 100, 200

    builder = ReportBuilder(
        dictionaries_dir=report_service._DICTS,
        context_builder=lambda plan, s: build_section_context(plan, s, data),
        generate_fn=mock_generate,
        plan_expander=lambda plans: report_service._expand_report_plans(plans, data),
    )
    result = builder.build(spec)
    report_service.attach_structured_sections(result, data)
    f14 = next(s for s in result.sections if s.section_id == "F-14")
    assert f14.data is not None and f14.data["birth_year"] == 1980
    assert len(f14.data["daewoons"]) == len(data.life_graph.daewoons)
    assert all(s.data is None for s in result.sections if s.section_id != "F-14")
