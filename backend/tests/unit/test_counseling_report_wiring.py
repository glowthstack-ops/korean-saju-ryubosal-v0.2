"""상담 결론 의미론 — 테마사주(리포트) 배선 검증 (2026-08-21).

채팅 패리티 3종: ①[상담 결론] 블록(플래그 게이트, 도메인 섹션만) ②후보 클러스터의
결실 뉘앙스(⚠유불리)·검토월 표기 ③기간 내 상대 순위(절대 강도와 분리).
목차·판정·점수 불변 — 섹션 컨텍스트 재료만 추가(절대원칙 10).
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services import report_service
from saju_engines import counseling_arbiter as ca
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.report import ReportPeriod, ReportSpec

_TODAY = date(2026, 8, 21)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1984-08-19", birth_time="10:15",
    birth_place_name="서울", gender="male",
)


def _spec(topic: str = "career") -> ReportSpec:
    return ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[{"kind": "self", "label": "본인"}],
        topic=topic,
        period=ReportPeriod(start="2026-01", end="2026-12"),
    )


@pytest.fixture(scope="module")
def career_contexts_flag_on():
    orig = ca.COUNSELING_SEMANTICS_ENABLED
    ca.COUNSELING_SEMANTICS_ENABLED = True
    try:
        return report_service.plan_report(_BIRTH, _spec("career"), _TODAY)
    finally:
        ca.COUNSELING_SEMANTICS_ENABLED = orig


def _domain_sections(contexts, domain: str):
    return [
        c for c in contexts
        if report_service._SECTION_DOMAIN.get(c.section_id) == domain
    ]


def test_counseling_block_in_domain_sections(career_contexts_flag_on) -> None:
    secs = _domain_sections(career_contexts_flag_on, "career")
    assert secs, "커리어 테마에 career 도메인 섹션이 있어야 한다"
    hits = [s for s in secs if "[상담 결론" in s.body_prompt]
    assert hits, "도메인 섹션에 상담 결론 블록이 주입돼야 한다"
    body = hits[0].body_prompt
    assert "요약 태세" in body
    assert "두 축은 별개" in body  # INV-C 계약 문구 동반


def test_cluster_lines_carry_semantics(career_contexts_flag_on) -> None:
    # 후보 클러스터에 상대 순위 병기(⚠유불리·검토월은 해당 시점 성립 시에만).
    secs = _domain_sections(career_contexts_flag_on, "career")
    joined = "\n".join(s.body_prompt for s in secs)
    assert "기간 내 상대 " in joined


def test_flag_off_no_counseling_block(monkeypatch) -> None:
    monkeypatch.setattr(ca, "COUNSELING_SEMANTICS_ENABLED", False)
    contexts = report_service.plan_report(_BIRTH, _spec("career"), _TODAY)
    for sec in contexts:
        assert "[상담 결론" not in sec.body_prompt


def test_relationship_topic_capped_summary(monkeypatch) -> None:
    # 관계 도메인 — big_decision 캡: 요약이 '진행에 무게'(PUSH형)로 나가지 않는다.
    monkeypatch.setattr(ca, "COUNSELING_SEMANTICS_ENABLED", True)
    contexts = report_service.plan_report(_BIRTH, _spec("relationship"), _TODAY)
    rel = [
        s for s in _domain_sections(contexts, "relationship")
        if "[상담 결론" in s.body_prompt
    ]
    for sec in rel:
        assert "요약 태세: 진행에 무게" not in sec.body_prompt
