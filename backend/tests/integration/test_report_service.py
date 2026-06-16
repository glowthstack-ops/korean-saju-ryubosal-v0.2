"""보고서 운영 배선 검증 (v2.2.1 PR-E — Phase 9 실데이터 컨텍스트 빌더, docs/10).

ReportBuilder 골격(테스트 전용이던)에 실데이터 컨텍스트가 주입되어:
1. 섹션 프롬프트에 고정 prefix(명식 구조·해석 자료)와 섹션별 데이터 블록이 실린다.
2. 검사 기준(allowed_ganji/scores/years·evidence_paths)이 실값으로 채워진다.
3. 실컨텍스트 + 모의 LLM으로 RPT_FOCUS 8섹션 전체가 정합성 검사를 통과한다.
4. POST /api/v2/report dry-run이 동작한다.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from saju_api.main import app
from saju_api.services import report_service
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

_TODAY = date(2026, 6, 11)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date="2026-06-11",
)


def _spec(product_code: str = "RPT_FOCUS") -> ReportSpec:
    return ReportSpec(
        product_code=product_code,
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        # health는 테마 전용 목차가 없어 generic FOCUS(C-01~C-08) 경로를 탄다.
        # (career·wealth·relationship 테마 목차는 test_report_topic_scoping에서 검증.)
        topic="health" if product_code == "RPT_FOCUS" else None,
        period=ReportPeriod(start="2026-01-01", end="2026-12-31"),
    )


def test_plan_report_focus_contexts() -> None:
    """RPT_FOCUS 8섹션 — 고정 prefix + 데이터 블록 + 검사 기준 실값."""
    contexts = report_service.plan_report(_BIRTH, _spec(), _TODAY)
    assert [c.section_id for c in contexts] == [f"C-{n:02d}" for n in range(1, 9)]
    for c in contexts:
        assert "[원국·명식 구조" in c.body_prompt  # 대화와 동일한 고정 prefix(캐시 공용)
        assert "[명식 해석 자료" in c.body_prompt
        assert "己亥" in c.allowed_ganji  # 일주 간지 허용
        assert c.allowed_years and c.evidence_paths
    c04 = next(c for c in contexts if c.section_id == "C-04")
    # 리포트 전용 정밀 후보 블록(시점 클러스터 + per-글자 십성/관계).
    assert "[대운표]" in c04.body_prompt and "[이벤트 후보" in c04.body_prompt
    assert "천간" in c04.body_prompt and "지지" in c04.body_prompt  # per-글자 십성 노출


def test_wealth_section_surfaces_wealth_capacity() -> None:
    """재물 테마 — W-05(횡재·상속)에 원국 횡재 그릇 블록 표면화 + 당첨/번호 금지 가드(Phase 1)."""
    spec = ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic="wealth",
        period=ReportPeriod(start="2026-01", end="2031-12"),
    )
    contexts = report_service.plan_report(_BIRTH, spec, _TODAY)
    w05 = next(c for c in contexts if c.section_id == "W-05")
    assert "[원국 횡재 그릇" in w05.body_prompt
    assert "재성 오행:" in w05.body_prompt and "종합 그릇:" in w05.body_prompt
    assert "당첨" in w05.body_prompt and "번호 추천은 절대 금지" in w05.body_prompt
    assert "발동 조건" in w05.body_prompt  # 재성국 완성·충개고·식상생재(운 발동) 안내


def test_plan_report_full_natal_sections() -> None:
    """RPT_FULL — F-02 일주 서사, F-04 용신 확정(이후 섹션 일관 검사 기준)."""
    contexts = report_service.plan_report(_BIRTH, _spec("RPT_FULL"), _TODAY)
    assert len(contexts) == 22
    f02 = next(c for c in contexts if c.section_id == "F-02")
    assert "노란 돼지" in f02.body_prompt  # interpretations/ilju.json 직렬화
    f04 = next(c for c in contexts if c.section_id == "F-04")
    assert f04.yongsin_element == "土"
    f10 = next(c for c in contexts if c.section_id == "F-10")
    assert f10.yongsin_element is None  # 빌더가 F-04 통과 후 전파


def test_focus_report_passes_checks_with_real_contexts() -> None:
    """실컨텍스트 + 모의 LLM — 8섹션 전체 정합성 검사 통과(완성 보고서)."""
    spec = _spec()
    data = report_service._ReportData(_BIRTH, spec, _TODAY)

    def mock_generate(plan, context, attempt):
        # 근거 경로는 내부 근거일 뿐 — 본문엔 분류 용어를 노출하지 않고 일상어로 서술(2026-06-16).
        body = "이 시기에는 변화의 기운이 차분히 흐르고 있어요. "
        filler = "기운을 살펴보면 좋아요. "
        while len(body) < plan.target_chars.min:
            body += filler
        return body[: plan.target_chars.max], 100, 200

    from saju_engines.report_builder import ReportBuilder

    builder = ReportBuilder(
        dictionaries_dir=report_service._DICTS,
        context_builder=lambda plan, s: report_service.build_section_context(plan, s, data),
        generate_fn=mock_generate,
    )
    result = builder.build(spec)
    assert result.status == "completed", result.failed_sections
    assert len(result.sections) == 8 and all(s.passed for s in result.sections)


def test_report_api_dry_run() -> None:
    """POST /api/v2/report dry_run — 섹션 프롬프트 미리보기."""
    client = TestClient(app)
    res = client.post("/api/v2/report", json={
        "birth": {
            "calendar_type": "solar", "birth_date": "1980-11-22",
            "birth_time": "09:08", "birth_place_name": "서울", "gender": "male",
            "reference_date": "2026-06-11",
        },
        "spec": {
            "product_code": "RPT_FOCUS",
            "subjects": [{"kind": "self", "label": "본인"}],
            "topic": "career",
            "period": {"start": "2026-01-01", "end": "2026-12-31"},
        },
        "today": "2026-06-11",
        "dry_run": True,
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "dry_run" and body["section_count"] == 8
    assert "[원국·명식 구조" in body["sections"][0]["body_prompt"]
