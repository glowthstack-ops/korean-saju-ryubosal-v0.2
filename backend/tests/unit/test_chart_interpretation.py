"""⑤ 명식 구조+해석 자료·2층 프롬프트·동반 신호 매트릭스 검증 (v2.2.1 PR-C).

핵심 회귀:
- 고정 prefix는 같은 명식이면 질문이 달라도 바이트 단위 동일(캐시 적중 조건).
- 운 유입 노트는 천간·지지 십성을 모두 표기(regression_2025_08 — 甲申월의 申 상관 누락 금지).
- branchTenGod 신호 조건이 지지 본기 십성과 매칭된다.
- 회귀 케이스(2025-08 이사≠재취업)가 cases.jsonl에 보존된다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import saju_api.services.chat_service as chat_service
from saju_api.services.manse_service import calculate
from saju_engines.cases_store import CasesStore
from saju_engines.chart_interpretation import (
    build_chart_interpretation,
    incoming_ten_god_note,
)
from saju_shared_types.birth_input import BirthInput

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_TODAY = date(2026, 6, 11)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date="2026-06-11",
)


def _preview(question: str) -> str:
    res = chat_service.chat(_BIRTH, question, _TODAY, dry_run=True)
    assert res.status == "dry_run", res.answer
    assert res.prompt_preview is not None
    return res.prompt_preview


def test_chart_interpretation_built_from_result() -> None:
    """⑤ 빌더 — 주별 구조 + 일주 해석 + 십성·운성 발췌가 채워진다."""
    result = calculate(_BIRTH)
    ci = build_chart_interpretation(result)
    assert ci is not None
    assert [d.palace for d in ci.pillar_details] == ["year", "month", "day", "hour"]
    day = next(d for d in ci.pillar_details if d.palace == "day")
    assert day.ganji == "己亥" and day.branch_ten_god == "정재"
    assert "노란 돼지" in ci.ilju_text and "배우자궁" in ci.ilju_text
    kinds = {e.kind for e in ci.excerpts}
    assert "ten_god" in kinds and "twelve_stage" in kinds


def test_fixed_prefix_identical_across_questions() -> None:
    """2층 구조 — 같은 명식이면 고정 prefix가 질문과 무관하게 동일(캐시 조건)."""
    a = _preview("올해 이직운 어때?")
    b = _preview("내년 연애운은?")
    prefix_a = a.split("[기준 시점]")[0]
    prefix_b = b.split("[기준 시점]")[0]
    assert prefix_a == prefix_b
    assert prefix_a.startswith("[원국·명식 구조")
    assert "[명식 해석 자료" in prefix_a
    assert "신살(보조)" in prefix_a  # 신살은 보조 표기


def test_prompt_has_meaning_layers_and_instructions() -> None:
    """후보별 동반 신호·해석 줄 + 의미 서술/매트릭스/보조 지시가 들어간다."""
    text = _preview("올해 이직운 어때?")
    assert "동반 신호:" in text
    assert "해석:" in text and "유입 = 천간" in text
    assert "이야기로 풍부하게 서술" in text  # _MEANING_INSTRUCTION
    assert "동반 신호 매트릭스" in text  # _MATRIX_INSTRUCTION
    assert "신살·암합은 보조 참고 자료" in text  # _AUXILIARY_INSTRUCTION
    # v2.2.1 신규 지시 — 원국/운 구분, 합 인과 완결, 이벤트 위상, 길이·평문.
    assert "원국(타고난 명식)에 본래 있는 요소" in text  # _ORIGIN_INSTRUCTION
    assert "인과를 완결" in text  # _HARMONY_INSTRUCTION
    assert "기간 전체를 대표하지 않는다" in text  # _SCOPE_INSTRUCTION
    assert "1,500자 이내" in text and "마크다운" in text


def test_incoming_note_includes_branch_ten_god() -> None:
    """regression_2025_08 — 己 일간의 甲申월: 천간 정관과 지지 상관을 함께 표기."""
    note = incoming_ten_god_note("己", "甲申", {})
    assert "천간 甲 정관" in note
    assert "지지 申 상관" in note  # 申(庚) 상관 — 이동성 신호 누락 금지


def test_regression_case_2025_08_is_stored() -> None:
    """기준 회귀 케이스 — 정관합 단독으로 취업 단정 금지(이사 매트릭스 우세)."""
    rows = CasesStore().load()
    case = next(r for r in rows if r.case_id == "regression_2025_08_move_not_job")
    assert case.predicted_event == "relocation" and case.actual_event == "relocation"
    assert case.time == "2025-08" and case.matched is True
    assert "甲己合" in case.signals and any("상관" in s for s in case.signals)
    assert case.notes is not None and "매트릭스" in case.notes


def test_luck_amhap_detection() -> None:
    """운 암합(명암합·지장간암합) — 궁성·십성 매칭(2026-06-12 자료)."""
    from saju_engines.amhap_luck import detect_luck_amhap

    result = calculate(_BIRTH)  # 己亥 일간
    assert result.pillars is not None
    # 운 丁亥: 丁(천간) + 원국 지장간 壬 → 정임 명암합, 일지 비중 큼.
    myeong = detect_luck_amhap("丁", "亥", result.pillars)
    assert myeong, "명암합 탐지 실패"
    top = myeong[0]
    assert top.kind == "myeong" and top.natal_hidden == "壬"
    assert top.ten_god == "정재"  # 己 일간에게 壬은 정재
    assert "일지" in top.stage  # 일지 비중 가장 큼(정렬 1순위)
    # 운 甲午: 午 지지의 지장간이 원국 지장간과 지장간암합.
    jijang = [a for a in detect_luck_amhap("甲", "午", result.pillars) if a.kind == "jijang"]
    assert jijang, "지장간암합 탐지 실패"


def test_luck_amhap_in_prompt_as_auxiliary() -> None:
    """운 암합은 프롬프트에 '보조·물밑'으로만 표기(점수 미반영, 단독 결론 금지)."""
    res = chat_service.chat(_BIRTH, "올해 연애운 어때?", _TODAY, dry_run=True)
    text = res.prompt_preview or ""
    if "운 암합(보조" in text:  # 해당 기간에 운 암합이 있을 때만
        assert "물밑" in text
        assert "암합이 건드린 궁성" in text  # 지시문에 보조·궁성 안내
