"""성별별 답변 형태(2026-11-07 데굴님 "사주를 보는 사람이 남자인지 여자인지에 따라 답변 형태를
다르게").

실답(총운 F-06b, 남성 명식): 입력에 배우자성 가드가 있어도 산출문이 중성 호칭에 '관성 부재=결혼
책임'
(여성 기준)을 섞었고, 공용 헤더에는 성별이 없어 F-03 등은 육친을 추측했다. ①고정 prefix 2행 육친 줄
②F-06b 성별 서술 형태 디렉티브 ③결혼 자원 나이대 라벨 성별화 ④육친 성별 기준 soft 감사.
"""

from __future__ import annotations

from datetime import date

from saju_api.services import report_service
from saju_api.services.manse_service import calculate
from saju_engines.context_reducer import build_birth_summary, serialize_chart_prefix
from saju_engines.gender_kin_audit import audit_gender_kin_claims
from saju_engines.marriage_resource import analyze_marriage_resource
from saju_engines.structural_context import (
    gender_kin_line,
    marriage_resource_lines,
    spouse_form_directive,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

_TODAY = date(2026, 11, 7)


def _birth(gender: str) -> BirthInput:
    return BirthInput(
        calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울", gender=gender, reference_date="2026-11-07",
    )


# ── ① 고정 prefix 2행 ─────────────────────────────────────────────────────────


def test_gender_kin_line_three_branches() -> None:
    male, female = gender_kin_line("male"), gender_kin_line("female")
    unknown = gender_kin_line(None)
    assert male.startswith("[주인공] 남성") and "재성=아내" in male and "관성=자녀" in male
    assert female.startswith("[주인공] 여성") and "관성=남편" in female and "식상=자녀" in female
    assert unknown.startswith("[주인공] 성별 미상") and "중성 호칭" in unknown
    assert gender_kin_line("weird") == unknown


def test_chart_prefix_second_line_is_gender_kin_line() -> None:
    result = calculate(_birth("male"))
    summary = build_birth_summary(result)
    assert summary.gender == "male"
    lines = serialize_chart_prefix(summary, None)
    assert lines[0].startswith("[원국·명식 구조")
    assert lines[1] == gender_kin_line("male")
    # 같은 명식·다른 성별 — 2행만 달라진다(사용자별 상수 → 캐시 안전).
    female = summary.model_copy(update={"gender": "female"})
    f_lines = serialize_chart_prefix(female, None)
    assert f_lines[1] == gender_kin_line("female")
    assert f_lines[0] == lines[0] and f_lines[2:] == lines[2:]


# ── ② F-06b 서술 형태 디렉티브 ───────────────────────────────────────────────


def test_spouse_form_directive_wording() -> None:
    male = spouse_form_directive("male")
    assert "남성 명식" in male and "'아내(아내가 될 분)'" in male and "여성상 어휘" in male
    assert "결혼 책임·배우자 인연의 근거로 쓰지 말 것" in male
    female = spouse_form_directive("female")
    assert "여성 명식" in female and "'남편(남편이 될 분)'" in female and "남성상 어휘" in female
    assert "시댁" in female
    assert "성별 미상" in spouse_form_directive(None)


def test_full_report_prompts_carry_gender_form() -> None:
    spec = ReportSpec(
        product_code="RPT_FULL",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start="1980-01", end="2070-12"),
    )
    contexts = {c.section_id: c for c in report_service.plan_report(_birth("male"), spec, _TODAY)}
    # 모든 섹션 헤더 2행 — 1부(F-03 십성 구조)도 성별·육친 기준을 받는다.
    for sid in ("F-03", "F-06b", "F-14-D1"):
        assert gender_kin_line("male") in contexts[sid].body_prompt, sid
        assert contexts[sid].gender == "male"
    f06b = contexts["F-06b"].body_prompt
    assert "[배우자 서술 형태 — 남성 명식]" in f06b
    assert "[배우자성 — 성별 기준]" in f06b  # 기존 가드도 유지
    assert "남성 명식에는 참고만" in f06b  # 나이대 라벨 성별화
    assert "여성 명식에 더 유효" not in f06b
    # 형태 디렉티브는 F-06b 전용 — 적성 섹션엔 없다.
    assert "[배우자 서술 형태" not in contexts["F-06c"].body_prompt


# ── ③ 결혼 자원 나이대 라벨 ──────────────────────────────────────────────────


def test_marriage_resource_age_label_follows_gender() -> None:
    result = calculate(_birth("female"))
    mr = analyze_marriage_resource(result, build_birth_summary(result).useful_gods)
    assert mr.gender == "female"
    joined = "\n".join(marriage_resource_lines(mr))
    if mr.partner_age_tendencies:
        assert "여성 명식에 더 유효" in joined


# ── ④ 육친 성별 기준 감사 ────────────────────────────────────────────────────


def test_gender_kin_audit_flags_opposite_axis_claims_only() -> None:
    male_bad = (
        "특히 관성(책임과 의무)의 기운이 겉으로 드러나지 않은 구조라, 연애 때는 즐겁다가도 막상 "
        "결혼이라는 현실적인 책임이 닥치면 이를 무겁게 느낄 수 있어요. 일지 정재는 아내 자리예요."
    )
    hits = audit_gender_kin_claims(male_bad, "male")
    assert len(hits) == 1 and hits[0].startswith("특히 관성")
    # 부정문·올바른 축(자녀·직장) 설명은 통과.
    ok = (
        "관성은 남성에게 배우자가 아니라 자녀와 직장의 자리예요. "
        "정관이 자녀 자리라 결혼 뒤 자녀 복이 커요."
    )
    assert audit_gender_kin_claims(ok, "male") == []
    # 여성 명식 — 재성=배우자 주장만 위반, 시댁 축은 통과.
    female_bad = (
        "재성이 약해 배우자 인연이 늦어질 수 있어요. "
        "재성은 시댁과 물질 환경이라 결혼 뒤 집안 분위기를 봐요."
    )
    hits_f = audit_gender_kin_claims(female_bad, "female")
    assert len(hits_f) == 1 and hits_f[0].startswith("재성이 약해")
    # 미상·None은 감사하지 않는다.
    assert audit_gender_kin_claims(male_bad, None) == []
    assert audit_gender_kin_claims(male_bad, "unknown") == []
