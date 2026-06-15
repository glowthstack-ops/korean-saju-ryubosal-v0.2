"""Phase 9 풀이 상품 검증 (docs/10 — 목차 규격·정합성 검사 8종·파이프라인·원가)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from saju_api.main import app
from saju_engines.report_builder import (
    ReportBuilder,
    assemble_markdown,
    estimate_cost_usd,
    load_model_prices,
)
from saju_engines.report_checks import ReportChecker
from saju_engines.report_plan import FULL_TOTAL_TARGET, build_section_plans
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.profile import PersonaConfig
from saju_shared_types.report import (
    ReportPeriod,
    ReportSpec,
    SectionContext,
    SectionPlan,
    TargetChars,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
client = TestClient(app)


def _spec(product: str = "RPT_FULL", topic: str | None = None) -> ReportSpec:
    return ReportSpec(
        product_code=product,
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic=topic,
        period=ReportPeriod(start="2026-01-01", end="2026-12-31"),
    )


# ── 목차 규격(3·4장 — 임의 변경 금지) ────────────────────────────


def test_full_toc_is_22_sections_in_fixed_order() -> None:
    plans = build_section_plans(_spec("RPT_FULL"))
    assert [p.section_id for p in plans] == [f"F-{n:02d}" for n in range(1, 23)]
    # 분량 합계 목표 78,000자 ±10% — min/max 평균 기준.
    mid = sum((p.target_chars.min + p.target_chars.max) / 2 for p in plans)
    assert abs(mid - FULL_TOTAL_TARGET) <= FULL_TOTAL_TARGET * 0.10


def test_full_depends_on_rules() -> None:
    """F-04 → F-10~F-20 선행, F-21 → F-13~F-20 완료 후(3장 규칙)."""
    plans = {p.section_id: p for p in build_section_plans(_spec("RPT_FULL"))}
    for n in range(10, 21):
        assert plans[f"F-{n:02d}"].depends_on == ["F-04"]
    assert plans["F-21"].depends_on == [f"F-{n:02d}" for n in range(13, 21)]
    assert plans["F-01"].depends_on == []


def test_focus_toc_is_8_sections() -> None:
    # health는 테마 전용 목차가 없어 generic FOCUS(C-01~C-08)를 쓴다.
    # (career·wealth·relationship은 테마 전용 목차로 분기 — test_report_topic_scoping에서 검증.)
    plans = build_section_plans(_spec("RPT_FOCUS", topic="health"))
    assert [p.section_id for p in plans] == [f"C-{n:02d}" for n in range(1, 9)]


def test_focus_variant_swaps_title_only() -> None:
    """compatibility/relocation 변형 — 제목·모듈만 교체, 섹션 수·분량 동일(4장)."""
    base = build_section_plans(_spec("RPT_FOCUS", topic="health"))
    compat = build_section_plans(_spec("RPT_FOCUS", topic="compatibility"))
    assert len(compat) == len(base) == 8
    by_id = {p.section_id: p for p in compat}
    assert by_id["C-02"].title == "두 명식의 구조 대조"
    assert by_id["C-04"].title == "관계 이벤트 타임라인"
    assert {m.module_id for m in by_id["C-02"].module_calls} == {"M13"}
    # 분량은 변형 전과 동일.
    base_by_id = {p.section_id: p for p in base}
    assert by_id["C-02"].target_chars == base_by_id["C-02"].target_chars

    reloc = {p.section_id: p for p in build_section_plans(_spec("RPT_FOCUS", topic="relocation"))}
    assert reloc["C-04"].title == "추천 시기·날짜 랭킹"
    assert {m.module_id for m in reloc["C-04"].module_calls} == {"M10"}


# ── 정합성 검사 8종(7장) ─────────────────────────────────────────


@pytest.fixture(scope="module")
def checker() -> ReportChecker:
    return ReportChecker(_DICTS)


def _plan(lo: int = 10, hi: int = 10_000) -> SectionPlan:
    return SectionPlan(
        section_id="F-11", title="올해 세운과 활성 신호",
        target_chars=TargetChars(min=lo, max=hi),
    )


def _ctx(**over) -> SectionContext:
    base = dict(
        section_id="F-11",
        allowed_ganji=["丙午", "甲辰"],
        allowed_scores=[72, 85],
        allowed_years=[2026],
        yongsin_element="土",
        evidence_paths=["丙午 세운 → 정관 활성"],
    )
    base.update(over)
    return SectionContext(**base)


_GOOD_TEXT = (
    "올해 丙午 세운에는 변화 에너지가 활성화돼요. 근거는 丙午 세운 → 정관 활성 경로예요. "
    "이 신호는 72점 수준으로 보여요. 2026년에는 용신인 土 기운이 받쳐줘요."
)


def test_checks_pass_on_good_text(checker) -> None:
    violations = checker.check_section(_plan(), _ctx(), _GOOD_TEXT, PersonaConfig(), "길동")
    assert violations == []


def test_check2_unknown_ganji_fails(checker) -> None:
    text = _GOOD_TEXT + " 그리고 癸亥 운도 함께 봐요."
    violations = checker.check_section(_plan(), _ctx(), text, PersonaConfig(), "길동")
    assert any("미제공 간지" in v and "癸亥" in v for v in violations)


def test_check3_score_year_mismatch(checker) -> None:
    text = _GOOD_TEXT.replace("72점", "91점").replace("2026년", "2031년")
    violations = checker.check_section(_plan(), _ctx(), text, PersonaConfig(), "길동")
    assert any("91점" in v for v in violations)
    assert any("2031년" in v for v in violations)


def test_check4_yongsin_consistency(checker) -> None:
    text = _GOOD_TEXT.replace("용신인 土", "용신은 木")
    violations = checker.check_section(_plan(), _ctx(), text, PersonaConfig(), "길동")
    assert any("용신 불일치" in v for v in violations)


def test_check5_prohibited_styles(checker) -> None:
    text = _GOOD_TEXT + " 내년에는 반드시 이직한다."
    violations = checker.check_section(_plan(), _ctx(), text, PersonaConfig(), "길동")
    assert any("금지 표현" in v for v in violations)


def test_check1_length_and_check8_evidence(checker) -> None:
    short = "짧아요."
    violations = checker.check_section(
        _plan(lo=1_000, hi=2_000), _ctx(), short, PersonaConfig(), "길동",
    )
    assert any("분량 위반" in v for v in violations)
    assert any("근거 경로" in v for v in violations)


def test_check7_subject_label_for_multi(checker) -> None:
    ctx = _ctx(multi_subject=True, subject_label="아드님(1호)")
    violations = checker.check_section(_plan(), ctx, _GOOD_TEXT, PersonaConfig(), "길동")
    assert any("대상 라벨" in v for v in violations)
    labeled = "아드님(1호) 사주 기준으로 보면, " + _GOOD_TEXT
    violations2 = checker.check_section(_plan(), ctx, labeled, PersonaConfig(), "길동")
    assert not any("대상 라벨" in v for v in violations2)


# ── 파이프라인(2장 — 재생성 ≤2회·보류·조립) ──────────────────────


def _focus_builder(generate_fn, progress_fn=None) -> ReportBuilder:
    def ctx_builder(plan: SectionPlan, spec: ReportSpec) -> SectionContext:
        return SectionContext(
            section_id=plan.section_id,
            allowed_ganji=["丙午"], allowed_scores=[72], allowed_years=[2026],
            yongsin_element="土", evidence_paths=["丙午 세운 → 정관 활성"],
        )
    return ReportBuilder(_DICTS, ctx_builder, generate_fn, progress_fn=progress_fn)


def test_progress_fn_called_per_section() -> None:
    """섹션 1개 완료마다 progress_fn(done, total) 호출 — 잡 진행 증분 반영."""
    seen: list[tuple[int, int]] = []

    def gen(plan, context, attempt):
        return _good_section_text(plan), 4_000, 3_000

    _focus_builder(gen, progress_fn=lambda d, t: seen.append((d, t))).build(
        _spec("RPT_FOCUS", topic="health")
    )
    # generic FOCUS 8섹션 → 1..8까지 단조 증가, total 고정.
    assert [d for d, _ in seen] == list(range(1, 9))
    assert all(t == 8 for _, t in seen)


def _good_section_text(plan: SectionPlan) -> str:
    body = (
        "丙午 흐름에서 변화 에너지가 단계적으로 활성화돼요. "
        "근거는 丙午 세운 → 정관 활성 경로이며 신호 강도는 72점이에요. "
        "2026년에는 탐색에서 실행으로 넘어가는 결이 보여요. "
    )
    target = plan.target_chars.min
    return (body * (target // len(body) + 1))[: target + 50]


def test_pipeline_completes_with_mock_llm() -> None:
    calls: list[str] = []

    def gen(plan, context, attempt):
        calls.append(plan.section_id)
        return _good_section_text(plan), 4_000, 3_000

    result = _focus_builder(gen).build(_spec("RPT_FOCUS", topic="health"))
    assert result.status == "completed" and not result.failed_sections
    assert len(result.sections) == 8 and all(s.passed for s in result.sections)
    assert result.cost.calls == 8  # 섹션당 1회(docs/10 9장: FOCUS 8~16 호출)
    assert result.meta["persona_snapshot"]["counselor_age_band"] == "40s"

    md = assemble_markdown(result)
    assert "## 목차" in md and "C-08" in md and "dictVersion" in md


def test_pipeline_regenerates_failed_section_only() -> None:
    """위반 섹션만 재생성(최대 2회) — 1회 실패 후 성공 케이스."""
    attempts_by_section: dict[str, int] = {}

    def gen(plan, context, attempt):
        attempts_by_section[plan.section_id] = attempt + 1
        if plan.section_id == "C-03" and attempt == 0:
            return _good_section_text(plan) + " 반드시 이직한다.", 4_000, 3_000
        return _good_section_text(plan), 4_000, 3_000

    result = _focus_builder(gen).build(_spec("RPT_FOCUS", topic="health"))
    assert result.status == "completed"
    assert attempts_by_section["C-03"] == 2  # 재생성 1회
    assert attempts_by_section["C-01"] == 1  # 다른 섹션은 1회
    assert result.cost.calls == 9


def test_pipeline_on_hold_after_hard_violation() -> None:
    """사실 위반(금지표현) 재생성 실패 → on_hold(관리자 알림) + 부분 산출물 보존."""
    def gen(plan, context, attempt):
        if plan.section_id == "C-05":
            return "반드시 된다.", 1_000, 100  # 항상 금지표현(사실 위반)
        return _good_section_text(plan), 4_000, 3_000

    result = _focus_builder(gen).build(_spec("RPT_FOCUS", topic="health"))
    assert result.status == "on_hold" and result.failed_sections == ["C-05"]
    failed = next(s for s in result.sections if s.section_id == "C-05")
    # MAX_REGENERATIONS=1 → 최초 1 + 재생성 1 = 2회. 사실 위반이라 재생성됨.
    assert failed.attempts == 2 and failed.violations
    assert sum(1 for s in result.sections if s.passed) == 7  # 부분 보존


def test_full_dependency_skips_after_f04_failure() -> None:
    """F-04 실패 시 F-10~F-20은 미생성(용신 일관성 보호)."""
    def gen(plan, context, attempt):
        if plan.section_id == "F-04":
            return "반드시 된다.", 100, 10
        return _good_section_text(plan), 4_000, 3_000

    result = _focus_builder(gen).build(_spec("RPT_FULL"))
    by_id = {s.section_id: s for s in result.sections}
    assert not by_id["F-04"].passed
    assert by_id["F-10"].violations == ["선행 섹션 실패로 미생성"]
    assert by_id["F-01"].passed  # 선행 무관 섹션은 정상


# ── 원가(9장 — 단가 설정 분리) ───────────────────────────────────


def test_model_prices_from_config() -> None:
    prices = load_model_prices()
    assert "claude-opus-4-8" in prices
    cost = estimate_cost_usd("claude-opus-4-8", 5_000, 3_500)
    assert cost == round(5_000 / 1e6 * 5.0 + 3_500 / 1e6 * 25.0, 6)
    assert estimate_cost_usd("unknown-model", 1, 1) == 0.0


# ── CHAT 연계(5장 — too_broad → 상품 제안, 강제 유도 금지) ───────


def test_too_broad_suggests_report_products() -> None:
    res = client.post("/api/v2/chat", json={
        "birth": {
            "calendar_type": "solar", "birth_date": "1980-11-22",
            "birth_time": "09:08", "birth_place_name": "서울", "gender": "male",
        },
        "question": "앞으로 내 운세 전체적으로 다 봐줘", "today": "2026-06-11",
        "dry_run": True,
    })
    body = res.json()
    assert body["status"] == "too_broad"
    suggestion = body["product_suggestion"]
    assert suggestion and set(suggestion["products"]) == {"RPT_FULL", "RPT_FOCUS"}
    assert "대화로도" in suggestion["note"]  # 강제 유도 금지 — 축약 답변 병행
    assert body["answer"]  # 대화 답변(범위 좁히기 제안)도 함께 제공


def test_soft_violation_passes_without_regeneration() -> None:
    """스타일/포맷 위반(분량 미달·종결어미 등)만 있으면 재호출 없이 통과(비용 절감)."""
    calls = {"n": 0}

    def gen(plan, context, attempt):
        calls["n"] += 1
        # 매우 짧은 본문 → 분량 미달(스타일 위반). 사실 위반은 없음.
        return "짧아요.", 100, 10

    result = _focus_builder(gen).build(_spec("RPT_FOCUS", topic="health"))
    assert result.status == "completed"  # 사실 위반 없음 → on_hold 아님
    # 섹션당 1회만 호출(재생성 없음) — 8섹션.
    assert all(s.attempts == 1 for s in result.sections)


def test_repair_appends_evidence_path_without_recall() -> None:
    """근거 경로 미인용 → 경로를 결정적으로 덧붙여 통과(재호출 0)."""
    from saju_engines.report_builder import _repair_section
    from saju_shared_types.report import SectionContext, SectionPlan, TargetChars

    plan = SectionPlan(
        section_id="C-04", title="t",
        target_chars=TargetChars(min=10, max=5_000),
    )
    ctx = SectionContext(section_id="C-04", evidence_paths=["甲申 → 정관 활성"])
    out = _repair_section("운의 흐름이 강해요.", plan, ctx)
    assert "甲申 → 정관 활성" in out  # 경로가 본문에 포함됨(검사 통과)
