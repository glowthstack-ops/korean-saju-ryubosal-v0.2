"""테마 애정·관계운 — 상대와의 관계 명시 선택 → 궁합(RP) 풀이 방향 반영 (2026-07-03).

데굴님 지시: 상사/부하/친구/연인/결혼예정/기혼/이혼예정/외도 등 관계에 따라 풀이가
달라져야 한다. 관계는 서술 방향 전용 — 점수·간지·판정 불변, 미지정이면 기존 중립 궁합 톤.
"""

from __future__ import annotations

from datetime import date

from saju_api.services.report_service import _ReportData, build_section_context
from saju_engines.relationship_hints import (
    RELATION_FRAMING,
    RELATION_KO,
    RELATION_TYPES,
    relation_context_lines,
)
from saju_engines.report_plan import build_section_plans
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import InlineBirth, SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:40",
    birth_place_name="서울", gender="male",
)
_PARTNER = BirthInput(
    calendar_type="solar", birth_date="1985-03-08", birth_time="10:00",
    birth_place_name="서울", gender="female",
)


def _spec(relation: str | None) -> ReportSpec:
    return ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[
            SubjectRef(kind=SubjectKind.SELF, label="본인"),
            SubjectRef(
                kind=SubjectKind.INLINE_TEMP, label="상대",
                inline_birth=InlineBirth(date="1985-03-08", time="10:00", gender="F"),
                relation_type=relation,
            ),
        ],
        topic="relationship", period=ReportPeriod(start="2026-07", end="2031-12"),
    )


def _rp_prompt(relation: str | None, sid: str = "RP-04") -> str:
    spec = _spec(relation)
    data = _ReportData(
        _BIRTH, spec, date(2026, 7, 3), owner_id=None, subject_id=None,
        partner_birth=_PARTNER,
    )
    plan = next(p for p in build_section_plans(spec) if p.section_id == sid)
    return build_section_context(plan, spec, data).body_prompt


def test_all_relation_types_have_label_and_framing() -> None:
    """전 관계 유형에 라벨·프레이밍·힌트가 정의돼 있다(unknown 제외 framing)."""
    for rt in RELATION_TYPES:
        assert rt in RELATION_KO
        if rt != "unknown":
            assert rt in RELATION_FRAMING, f"{rt} 프레이밍 누락"
            lines = relation_context_lines(rt)
            assert lines and RELATION_KO[rt] in lines[0]
            assert "단정하지 말 것" in lines[-1]


def test_unset_relation_returns_empty() -> None:
    """미지정·unknown은 빈 목록 — 기존 중립 궁합 톤 유지(하위호환)."""
    assert relation_context_lines(None) == []
    assert relation_context_lines("unknown") == []
    assert relation_context_lines("weird_value") == []


def test_rp_section_includes_relation_block_for_boss() -> None:
    """사회 관계(상사) 지정 — RP 섹션에 관계 블록 + 연애 프레임 금지 방향이 실린다."""
    prompt = _rp_prompt("boss")
    assert "[상대와의 관계 — 사용자가 지정: 상사]" in prompt
    assert "위계를 전제로" in prompt


def test_rp_section_relation_block_for_affair_is_balanced() -> None:
    """외도 관계 — 훈계·미화 금지 + 현실 리스크 병기 방향."""
    prompt = _rp_prompt("affair")
    assert "외도 관계" in prompt
    assert "도덕적 훈계도 관계 미화도 하지 말 것" in prompt


def test_rp_section_without_relation_keeps_neutral_tone() -> None:
    """관계 미지정 — 관계 블록 미부착(기존 RP 프롬프트 그대로)."""
    prompt = _rp_prompt(None)
    assert "[상대와의 관계" not in prompt


def test_relation_block_attached_across_rp_sections() -> None:
    """관계 블록이 RP 전 섹션에 공통 부착된다(요약·전략 섹션 포함)."""
    for sid in ("RP-01", "RP-08", "RP-09"):
        assert "[상대와의 관계" in _rp_prompt("fiance", sid)