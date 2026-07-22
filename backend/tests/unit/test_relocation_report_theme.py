"""이사 테마 리포트 — 십성 이유분류(reason_profiles)가 RL-* 섹션에 surface되는지 검증.

이사 고도화 R2의 분류(천간=명분/지지=현장, 리스크·체크리스트)가 총운류 리포트(RPT_FOCUS
relocation)에 반영됨을 확인한다. 리포트는 EventEngineV2를 쓰지만 LuckComposite 분류기를
재사용해 이유·집성격·리스크를 본문 데이터로 주입한다.
"""

from __future__ import annotations

from datetime import date

from saju_api.services.report_service import plan_report
from saju_engines.report_plan import build_section_plans
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportSpec

_BIRTH = BirthInput(
    calendar_type="solar", birth_date=date(1990, 3, 15), birth_time="10:00",
    birth_place_name="서울", gender="male",
)
_SELF = SubjectRef(kind=SubjectKind.SELF, label="본인")


def _spec() -> ReportSpec:
    return ReportSpec(
        product_code="RPT_FOCUS", topic="relocation", subjects=[_SELF],
        period={"start": "2026", "end": "2031"},
    )


def test_relocation_theme_toc_has_eight_sections() -> None:
    """이사 테마는 generic FOCUS가 아니라 전용 8섹션(RL-01~RL-08)을 쓴다."""
    plans = build_section_plans(_spec())
    assert [p.section_id for p in plans] == [f"RL-0{n}" for n in range(1, 9)]


def test_reason_classification_surfaces_in_reason_section() -> None:
    """RL-03 본문에 십성 이유분류(천간=명분/지지=현장)가 주입된다."""
    secs = {s.section_id: s for s in plan_report(_BIRTH, _spec(), date(2026, 6, 11))}
    body = secs["RL-03"].body_prompt
    assert "이사의 이유·집 성격 — 십성 분류" in body
    # 천간(명분)/지지(현장) 출처 라벨과 type 분류가 함께 실린다.
    assert "천간(명분)" in body and "지지(현장)" in body
    assert "→" in body  # '십성 → type' 라벨


def test_risk_checklist_surfaces_in_risk_section() -> None:
    """RL-05 본문에 십성별 리스크·계약 전 체크리스트가 주입된다."""
    body = {s.section_id: s for s in plan_report(_BIRTH, _spec(), date(2026, 6, 11))}[
        "RL-05"
    ].body_prompt
    assert "리스크·계약 전 체크리스트" in body
    assert "확인" in body and "핵심 질문" in body


def test_non_relocation_theme_unaffected() -> None:
    """재물 테마는 기존 W-* 그대로(이사 블록 미부착) — 회귀 없음."""
    spec = ReportSpec(
        product_code="RPT_FOCUS", topic="wealth", subjects=[_SELF],
        period={"start": "2026", "end": "2031"},
    )
    plans = build_section_plans(spec)
    assert plans[0].section_id == "W-01"
    secs = plan_report(_BIRTH, spec, date(2026, 6, 11))
    assert all("이사의 이유·집 성격" not in s.body_prompt for s in secs)


def test_procedure_pack_and_uncertainty_rule_in_report() -> None:
    """리포트 공유 배선(2026-07-22): RL-05에 [과업 절차 참고](L1/L2) + 전 섹션 불확실성 규칙."""
    secs = {s.section_id: s for s in plan_report(_BIRTH, _spec(), date(2026, 6, 11))}
    body = secs["RL-05"].body_prompt
    assert "[과업 절차 참고 — 주택 계약·대출·이사" in body
    assert "대출 승인이 나야 잔금" in body            # L1 의존관계
    assert "단정 금지" in body                         # L3 경계 고지
    # 불확실성 번역 규칙은 전 섹션 prefix — 절차 팩 없는 섹션(RL-03)에도 실린다.
    assert "[불확실성 표현 규칙" in secs["RL-03"].body_prompt
    assert "[불확실성 표현 규칙" in body
