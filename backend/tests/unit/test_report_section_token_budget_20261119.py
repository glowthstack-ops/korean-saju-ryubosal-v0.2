"""풀이 섹션 입력 토큰 예산 회귀(2026-11-19 데굴님 "상한을 증가하는 쪽으로 정리해").

한해 리포트 Y-04 가 26,818tok 로 상한(26,000)을 넘어 생성 실패했다(job c5450c8d). 11-18 에 기간
섹션 전부에 붙은 서술 블록의 재현 측정을 **본문만**으로 재어 시스템 프롬프트+페르소나(약 3.3k)를
빠뜨린 것이 원인이다. 가드(`llm_client.generate` → `LLMCallGuard.check_input`)는 본문+시스템을
함께 센다.

- 표본 명식의 전 상품 섹션이 (본문 + 시스템 + 페르소나) 기준으로 호출 유형 상한 안에 든다.
- 반례: 같은 검사에 낮은 상한을 주면 초과 섹션을 보고한다(검사가 실패할 수 있음을 고정).
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services import llm_client
from saju_api.services import report_service as rs
from saju_engines.llm_guard import CALL_LIMITS, estimate_tokens
from saju_engines.persona import PersonaEngine
from saju_engines.prompt_notation import normalize_range_tilde
from saju_engines.report_plan import build_section_plans
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

_TODAY = date(2026, 11, 19)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1992-03-14", birth_time="15:20",
    birth_place_name="서울", gender="female", reference_date=_TODAY.isoformat(),
)

#: (상품, 테마, 기간 시작, 기간 끝) — 2026-11-19 측정에서 구 상한을 넘은 섹션이 든 상품 전부.
_PRODUCTS: list[tuple[str, str | None, str, str]] = [
    ("RPT_YEAR", None, "2027-01", "2027-12"),      # Y-04·Y-08
    ("RPT_FOCUS", "career", "2026-11", "2031-12"),  # J-06
    ("RPT_FOCUS", "wealth", "2026-11", "2031-12"),  # W-07
    ("RPT_FOCUS", "relocation", "2026-11", "2031-12"),  # RL-06
    ("RPT_FULL", None, "1992-01", "2082-12"),      # F-20b
]


def _section_inputs(
    product_code: str, topic: str | None, start: str, end: str,
) -> list[tuple[str, str, int]]:
    """섹션별 (section_id, 호출 유형, 가드가 세는 입력 토큰) — LLM 미호출.

    `generate_report` 의 조립(시스템 = 보고서 시스템 프롬프트 + 페르소나 블록)과
    `llm_client.generate` 의 계수(본문 + 시스템, 범위 물결표 정규화 뒤)를 그대로 따른다.
    """
    spec = ReportSpec(
        product_code=product_code,  # type: ignore[arg-type]
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="회원")],
        topic=topic,
        period=ReportPeriod(start=start, end=end),
    )
    data = rs._ReportData(_BIRTH, spec, _TODAY)
    base = "report_full_section" if product_code == "RPT_FULL" else "report_focus_section"
    system = llm_client._REPORT_SYSTEM_PROMPT + "\n\n" + PersonaEngine(rs._DICTS).build_block(
        spec.persona, "회원")
    sys_text = normalize_range_tilde(system)
    rows: list[tuple[str, str, int]] = []
    for plan in rs._expand_report_plans(build_section_plans(spec), data):
        ctx = rs.build_section_context(plan, spec, data)
        call_type = rs._section_call_type(base, data, plan.section_id)
        tokens = estimate_tokens(normalize_range_tilde(ctx.body_prompt) + sys_text)
        rows.append((plan.section_id, call_type, tokens))
    return rows


def _over_limit(
    rows: list[tuple[str, str, int]], limits: dict[str, int],
) -> list[tuple[str, int, int]]:
    """상한을 넘는 섹션 — (section_id, 입력 토큰, 상한)."""
    return [(sid, tok, limits[ct]) for sid, ct, tok in rows if tok > limits[ct]]


_LIMITS: dict[str, int] = {k: v.max_input_tokens for k, v in CALL_LIMITS.items()}


@pytest.mark.parametrize(("product_code", "topic", "start", "end"), _PRODUCTS)
def test_sections_fit_input_limit(
    product_code: str, topic: str | None, start: str, end: str,
) -> None:
    """전 섹션이 본문+시스템+페르소나 기준으로 호출 유형 상한 안에 든다."""
    rows = _section_inputs(product_code, topic, start, end)
    assert rows, "섹션 계획이 비어 있다"
    assert _over_limit(rows, _LIMITS) == []


def test_over_limit_check_reports_offenders() -> None:
    """반례 — 낮은 상한을 주면 초과 섹션을 보고한다(시스템+페르소나가 계수에 들어간다)."""
    rows = _section_inputs("RPT_YEAR", None, "2027-01", "2027-12")
    system_tokens = estimate_tokens(
        llm_client._REPORT_SYSTEM_PROMPT + "\n\n"
        + PersonaEngine(rs._DICTS).build_block(ReportSpec(
            product_code="RPT_YEAR",
            subjects=[SubjectRef(kind=SubjectKind.SELF, label="회원")],
            period=ReportPeriod(start="2027-01", end="2027-12"),
        ).persona, "회원"))
    # 어떤 섹션도 시스템+페르소나보다 작을 수 없다 — 본문만 재는 측정과 구분되는 지점.
    assert min(tok for _, _, tok in rows) > system_tokens
    low = {k: system_tokens for k in _LIMITS}
    assert len(_over_limit(rows, low)) == len(rows)
