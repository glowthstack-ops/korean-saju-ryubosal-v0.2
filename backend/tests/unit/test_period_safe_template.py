"""안전 템플릿 사용자 노출 보완 — 2026-10-13 실답 회귀.

사고: 관계 감사 오탐으로 안전 템플릿이 발동했을 때 ①LLM 지시문("…혼동하지 말 것")과
②내부 점수 슬롯("의사결정운 50 — 강한 분야 우선 활용")이 사용자에게 그대로 노출됐다.
"""

from __future__ import annotations

from saju_engines.period_safe_template import build_safe_period_answer
from saju_shared_types.llm_input import PeriodFortune, PeriodFortuneSlot


def _pf(**overrides) -> PeriodFortune:
    base = dict(
        fortune_type="daily",
        period_label="2026-10-13 (화)",
        ganji="庚申",
        solar_month_note=(
            "이 기간이 속한 절기월은 戊戌월(양력 2026-10-08~2026-11-06)이다 — 월운은 절기 "
            "경계라 양력 달과 다르니 '○월=○○월운'으로 혼동하지 말 것."
        ),
        solar_month_user_note="이 기간이 속한 절기월은 戊戌월(양력 2026-10-08~2026-11-06)이에요.",
        pillar_line="庚 상관 · 申 상관",
        luck_label="평운",
        luck_summary="용신·기신 작용이 뚜렷하지 않은 운",
        slots=[
            PeriodFortuneSlot(
                name="핵심기운", score=55, summary="활성 간지: 丙午(희신), 庚申(한신)",
            ),
            PeriodFortuneSlot(name="주의행동", score=50, summary="특이 주의 없음"),
            PeriodFortuneSlot(
                name="활용법", score=50, summary="의사결정운 50 — 강한 분야 우선 활용",
            ),
            PeriodFortuneSlot(name="재물", score=62, summary="점수 62"),
        ],
    )
    base.update(overrides)
    return PeriodFortune(**base)


def test_llm_instruction_note_is_not_shown_to_user():
    """절기월 안내는 사용자용 문장만 — 프롬프트 지시문은 노출 금지."""
    out = build_safe_period_answer(_pf())
    assert "혼동하지 말 것" not in out
    assert "이다 —" not in out
    assert "이 기간이 속한 절기월은 戊戌월(양력 2026-10-08~2026-11-06)이에요." in out


def test_internal_score_slots_are_hidden():
    """'의사결정운 50'·'점수 62' 같은 내부 점수 요약은 내보내지 않는다."""
    out = build_safe_period_answer(_pf())
    assert "의사결정운" not in out
    assert "점수 62" not in out
    assert "· 핵심기운 — 활성 간지: 丙午(희신), 庚申(한신)" in out
    assert "· 주의행동 — 특이 주의 없음" in out


def test_luck_line_spacing_and_tone():
    """'운 입니다' 띄어쓰기 결함 없이 해요체로 닫힌다."""
    out = build_safe_period_answer(_pf())
    assert "이 날의 전체 기운은 평운 — 용신·기신 작용이 뚜렷하지 않은 운이에요." in out
    assert "운 입니다" not in out


def test_without_user_note_no_solar_line():
    """사용자용 절기월 문장이 비어 있으면 프롬프트용 note로 대체하지 않는다."""
    out = build_safe_period_answer(_pf(solar_month_user_note=""))
    assert "절기월" not in out
