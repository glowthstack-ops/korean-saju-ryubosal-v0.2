"""총운(RPT_FULL) 개편 — "나 → 대운 흐름 → 인생 그래프" (2026-11-07 데굴님 결정 1~5).

docs/10 §3. 1부는 원국 전용(세운·대운 언급 금지), 2부는 대운 전체(과거 포함)와 인생 그래프,
세운은 섹션으로 담지 않고 대운 페이지 연도 줄·그래프 마커의 재료로만 쓴다.
"""

from __future__ import annotations

from datetime import date

from saju_api.services import report_service
from saju_api.services.report_service import _ReportData, build_section_context
from saju_engines.context_reducer import overview_cluster_key
from saju_engines.life_graph import (
    CRISIS_PER_DAEWOON_CAP,
    KIND_AGE_RANGE,
    KIND_KO,
    MINOR_NOTE,
    PER_DAEWOON_CAP,
    PER_KIND_CAP,
    SCORE_GATE,
    _select_markers,
    build_life_graph,
    build_positive_windows,
    daewoon_summary_lines,
    marker_lines,
    positive_window_lines,
    when_tag,
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
    # 세운 행 시제 표식.
    assert "1981년 [지남]" in d1.body_prompt or "1980년 [지남]" in d1.body_prompt
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
        # 위기(건강+금전) 합산 상한 — 한 대운이 위기로만 채워지지 않는다(2026-11-07 "너무 극단적").
        crisis_n = sum(
            1 for k in kinds if k in (MarkerKind.CRISIS_HEALTH, MarkerKind.CRISIS_MONEY)
        )
        assert crisis_n <= CRISIS_PER_DAEWOON_CAP
        for m in d.markers:
            assert m.score + (10 if m.risk_backed else 0) >= SCORE_GATE
            assert d.start_year <= m.year <= d.end_year
            assert m.kind_ko == KIND_KO[m.kind]
    # 위기(건강·금전)는 흉·혼합 방향만, 재물 유입은 길 방향만.
    assert all(
        m.tone != "길" for m in g.markers
        if m.kind in (MarkerKind.CRISIS_MONEY, MarkerKind.CRISIS_HEALTH)
    )
    assert all(m.tone == "길" for m in g.markers if m.kind is MarkerKind.WEALTH_GAIN)
    # 결혼 마커는 방향 무관(2026-11-07 결혼운 강의 정정) — 2축 메모는 test_marriage_lectures 가
    # 검사.
    for m in g.markers:
        lo, hi = KIND_AGE_RANGE[m.kind]
        assert lo <= m.age <= hi, (m.kind, m.age)
        if m.age < 18 and m.kind in (
            MarkerKind.RELOCATION, MarkerKind.CRISIS_MONEY, MarkerKind.WEALTH_GAIN,
        ):
            assert m.note == MINOR_NOTE
    assert all(m.age <= 70 for m in g.markers if m.kind is MarkerKind.MARRIAGE)
    # 이 명식은 2026~2030 재물 변화 길 방향 후보가 79~92점 — 재물 유입 마커가 현재 대운에 있다.
    cur = next(d for d in g.daewoons if d.status == "current")
    assert any(m.kind is MarkerKind.WEALTH_GAIN for m in cur.markers)
    # 좌석 보장 — 현재 대운이 위기 종류로만 채워지지 않고 4종 이상이 섞인다(점수순만이면
    # 금전 위기·이직·취업 90점대가 자리를 독점했다).
    assert len({m.kind for m in cur.markers}) >= 4
    # 연속 대운이 창을 빠짐없이 덮는다(첫 페이지는 출생년부터).
    assert g.daewoons[0].start_year == 1980
    for a, b in zip(g.daewoons, g.daewoons[1:], strict=False):
        assert b.start_year == a.end_year + 1
    # 프롬프트 줄 — 마커·대운 요약.
    lines = marker_lines(g)
    assert len(lines) == len(g.markers)
    assert all("점" in ln for ln in lines)
    assert len(daewoon_summary_lines(g)) == len(g.daewoons)


def test_life_graph_positive_windows_nearest_first() -> None:
    data = _ReportData(_BIRTH, _spec(), _TODAY)
    g = data.life_graph
    assert g is not None and g.positive_windows
    for w in g.positive_windows:
        assert w.start_year >= _TODAY.year and w.end_year <= g.end_year
        assert w.start_year <= w.peak_year <= w.end_year and w.peak_score >= SCORE_GATE
        assert w.kind in (
            MarkerKind.ROMANCE, MarkerKind.MARRIAGE, MarkerKind.JOB, MarkerKind.CAREER_CHANGE,
            MarkerKind.WEALTH_GAIN, MarkerKind.RELOCATION,
        )
    years = [w.start_year for w in g.positive_windows]
    assert years == sorted(years)
    # 결혼 창은 마커보다 이른 해(2032~2035)를 먼저 보여 준다 — "76세에나 결혼" 보완.
    marriage = [w for w in g.positive_windows if w.kind is MarkerKind.MARRIAGE]
    assert marriage and marriage[0].start_year <= 2035
    # 시제 표식 — 오늘(2026) 기준 지남/올해/예정이 마커 줄에 붙는다.
    assert g.today_year == _TODAY.year
    tagged = marker_lines(g)
    assert all(("[지남]" in ln) == (int(ln[2:6]) < _TODAY.year) for ln in tagged)
    assert all(("[예정]" in ln) == (int(ln[2:6]) > _TODAY.year) for ln in tagged)
    assert when_tag(2025, 2026) == " [지남]" and when_tag(2026, 2026) == " [올해]"
    assert when_tag(2027, 2026) == " [예정]" and when_tag(2027, None) == ""
    lines = positive_window_lines(g)
    assert lines and lines[0].startswith("[앞으로의 긍정 창")
    assert any(ln.startswith("- 결혼:") for ln in lines)
    assert any(ln.startswith("- 재물 유입:") for ln in lines)


def _clone(c, *, year: int, score: int):
    return c.model_copy(update={"period": str(year), "score": score})


def test_select_markers_seat_guarantee_and_crisis_cap() -> None:
    """합성 풀: 금전 위기 3해(99·98·97) + 결혼 60 + 취업 58 → 위기 2·결혼·취업이 모두 앉는다."""
    data = _ReportData(_BIRTH, _spec(), _TODAY)
    pool = data.lifetime_pool

    def pick(key: str, direction: str):
        return next(
            c for c in pool
            if str(c.event_key) == key and overview_cluster_key(c)[1] == direction
        )

    crisis, marriage, job = pick("wealth_change", "neg"), pick("marriage_signal", "pos"), pick(
        "job_gain", "pos",
    )
    cands = {
        2030: [_clone(crisis, year=2030, score=99)],
        2031: [_clone(crisis, year=2031, score=98)],
        2032: [_clone(crisis, year=2032, score=97), _clone(marriage, year=2032, score=60)],
        2033: [_clone(job, year=2033, score=58)],
    }
    picked = _select_markers(4, range(2030, 2035), cands, {}, {}, 1980)
    kinds = [m.kind for m in picked]
    assert kinds.count(MarkerKind.CRISIS_MONEY) == CRISIS_PER_DAEWOON_CAP
    assert MarkerKind.MARRIAGE in kinds and MarkerKind.JOB in kinds
    assert len(picked) <= PER_DAEWOON_CAP
    # 긍정 창 — 공백 2년까지 한 창, 3년 이상 떨어지면 분리. 과거(2020)는 제외. 가까운 창부터.
    wealth_pos = pick("wealth_change", "pos")
    wins = build_positive_windows(
        [
            _clone(wealth_pos, year=2030, score=80), _clone(wealth_pos, year=2031, score=70),
            _clone(wealth_pos, year=2035, score=60), _clone(wealth_pos, year=2020, score=90),
        ],
        1980, 2026, 2070,
    )
    assert [
        (w.start_year, w.end_year, w.peak_year, w.peak_score, w.years_count) for w in wins
    ] == [(2030, 2031, 2030, 80, 2), (2035, 2035, 2035, 60, 1)]
    assert all(w.kind is MarkerKind.WEALTH_GAIN for w in wins)


def test_allowed_years_cover_first_decade_page_rows() -> None:
    """실답 회귀(2026-11-07): 첫 대운 페이지 세운 표(출생~유년 포함)의 모든 해가 허용 연도에
    있어야 한다 — 빠지면 정합성 검사가 '입력에 없는 연도'로 2회 실패해 on_hold가 된다."""
    data = _ReportData(_BIRTH, _spec(), _TODAY)
    g = data.life_graph
    assert g is not None
    d1 = g.daewoons[0]
    first_daewoon_start = data.result.luck_cycles.daewoon_table[0].approx_start_date.year
    assert d1.start_year == 1980 < first_daewoon_start  # 유년 구간이 실제로 존재하는 명식
    missing = [y for y in range(d1.start_year, d1.end_year + 1) if y not in data.allowed_years]
    assert missing == []
    # 생애 창(출생~90세) 전체가 허용 연도에 들어 있다.
    assert set(range(g.birth_year, g.end_year + 1)) <= set(data.allowed_years)


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
