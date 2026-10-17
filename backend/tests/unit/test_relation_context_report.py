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

# ── 등록 관계 키 번역 + 비연애 가드(2026-10-15 데굴님 승인) ────────────────────────────
# 테마 상대 선택 화면은 관계를 따로 고르지 않으면 등록 관계 키(mother·husband …)를 그대로 보낸다.
# 종전엔 번역이 없어 11종이 빈 블록(연애 궁합 톤)이었다 — 채팅(_RELATION_TO_USER)과 같은 표.

_STORED_EXPECTED: dict[str, str | None] = {
    "self": None, "spouse": "spouse", "husband": "spouse", "wife": "spouse",
    "father": "parent_child", "mother": "parent_child", "child": "parent_child",
    "son": "parent_child", "daughter": "parent_child",
    "brother": "family", "sister": "family", "lover": "romance",
    "friend": "friend", "coworker": "coworker", "boss": "boss",
    "business_partner": "business_partner", "other": None,
}


def test_normalize_relation_type_translates_all_stored_keys() -> None:
    """등록 관계 키 17종 전수 — 번역표와 일치하고, 번역된 키는 모두 관계 블록이 생긴다."""
    from saju_engines.relationship_hints import normalize_relation_type
    from saju_shared_types.subject import RELATION_TO_USER_KEYS

    assert set(_STORED_EXPECTED) == set(RELATION_TO_USER_KEYS)
    for key, expected in _STORED_EXPECTED.items():
        assert normalize_relation_type(key) == expected, key
        if expected is None:
            assert relation_context_lines(key) == []
        else:
            assert RELATION_KO[expected] in relation_context_lines(key)[0]
    # 테마 어휘는 그대로, 미지·unknown·빈값은 None.
    for rt in RELATION_TYPES:
        assert normalize_relation_type(rt) == (None if rt == "unknown" else rt)
    assert normalize_relation_type(None) is None
    assert normalize_relation_type("") is None
    assert normalize_relation_type("weird_value") is None


def _pair_data(relation: str | None) -> tuple[ReportSpec, _ReportData]:
    spec = _spec(relation)
    data = _ReportData(
        _BIRTH, spec, date(2026, 7, 3), owner_id=None, subject_id=None,
        partner_birth=_PARTNER,
    )
    return spec, data


def _body(spec: ReportSpec, data: _ReportData, sid: str) -> str:
    plan = next(p for p in build_section_plans(spec) if p.section_id == sid)
    return build_section_context(plan, spec, data).body_prompt


def test_stored_mother_key_gets_parent_child_block_and_non_romantic_guard() -> None:
    """등록 '어머니' 키 — 부모·자녀 블록 + 배우자성·결혼 자원 생략 + 결혼 신호 후보 제외."""
    spec, data = _pair_data("mother")
    assert data.partner_relation_type == "parent_child"
    assert data.non_romantic_pair is True
    assert not any(
        str(c.event_key) in {"marriage_signal", "new_relationship", "childbirth"}
        for c in data.scored
    )
    for sid in ("RP-03", "RP-04"):
        body = _body(spec, data, sid)
        assert "[상대와의 관계 — 사용자가 지정: 부모·자녀]" in body
        assert "배우자성" not in body
        assert "결혼·자산 자원" not in body
        assert "자기인식" in body or "이상형" in body  # 자기인식 가드는 유지
    rp02 = _body(spec, data, "RP-02")
    assert "관계를 맺는 성향" in rp02
    assert "재성/관성" not in rp02
    for sid in ("RP-06", "RP-07"):
        assert "결혼 신호" not in _body(spec, data, sid)


def test_romance_pair_keeps_marriage_blocks_counterexample() -> None:
    """반례 — 연인 관계는 종전 그대로(배우자성·결혼 자원 블록·결혼 신호 후보·애정 성향 지시문)."""
    spec, data = _pair_data("romance")
    assert data.non_romantic_pair is False
    assert any(str(c.event_key) == "marriage_signal" for c in data.scored)
    body = _body(spec, data, "RP-04")
    assert "배우자성" in body and "결혼·자산 자원" in body
    assert "재성/관성" in _body(spec, data, "RP-02")


def test_unset_relation_is_not_non_romantic() -> None:
    """미지정 — 비연애 가드가 켜지지 않는다(중립 궁합 톤, 결혼 블록 유지)."""
    spec, data = _pair_data(None)
    assert data.partner_relation_type is None and data.non_romantic_pair is False
    assert "결혼·자산 자원" in _body(spec, data, "RP-03")
