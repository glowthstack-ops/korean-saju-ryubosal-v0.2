"""LLM 입력 품질 수정 검증 (P1~P7 — 실사용 결함 회귀 방지).

배경: 실서비스 검증에서 LLM이 '올해'를 2024로 오인(기준 시점 부재), 과거 후보가
메인 서술 점유(기간 필터 부재), 택일 질문에 일운 미제공, 영문 키 노출이 확인됨.
"""

from __future__ import annotations

from datetime import date

from saju_api.services import chat_service
from saju_shared_types.birth_input import BirthInput

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


# ── P1 — 기준 시점(LLM은 오늘을 모른다) ──────────────────────────


def test_reference_frame_always_present() -> None:
    text = _preview("올해 연애운은 어때?")
    # v2.2.1 2층 구조: 고정 prefix(명식 구조·해석 자료)가 먼저, [기준 시점]은
    # 동적 suffix의 최상단(캐시 무효화 방지 — docs/06).
    assert text.startswith("[원국·명식 구조")
    assert text.index("[기준 시점]") < text.index("[간지달력")
    assert "오늘: 2026-06-11 (목)" in text
    assert "올해: 2026년" in text
    assert "질문 기간: 2026" in text  # '올해' 해석 결과 명시
    assert "임의로 다른 날짜를 기준으로 삼지 말 것" in text


# ── P2 — 질문 기간 필터 + 기간 외 참고 분리 ──────────────────────


def test_in_period_candidates_are_main() -> None:
    """'올해' 질문: 메인 후보는 전부 2026, 과거(2022 등)는 참고 블록으로."""
    text = _preview("올해 연애운은 어때?")
    main = text.split("[이벤트 후보")[1].split("[참고")[0]
    assert "@ 2026" in main
    assert "@ 2022" not in main and "@ 2024" not in main  # 과거가 메인 점유 금지
    assert "[참고 — 질문 기간 외 흐름" in text
    assert "메인 서술 금지" in text


def test_no_candidates_in_period_is_honest() -> None:
    """기간 내 후보가 없으면 '신호 없음' 정직 안내 지시가 입력에 박힌다."""
    res = chat_service.chat(_BIRTH, "내일 운세는?", _TODAY, dry_run=True)
    if res.status == "dry_run" and res.prompt_preview and \
            "질문 기간 내 해당 도메인 후보 없음" in res.prompt_preview:
        assert "정직하게 안내" in res.prompt_preview


# ── P3 — 택일 라우팅(표 제공 + 회피성 답변 금지) ─────────────────


def test_date_recommendation_includes_engine_table() -> None:
    text = _preview("다음 달 이사하기 좋은 날짜 알려줘")
    assert "[택일 결과 — 이사" in text
    assert "2026-07-" in text  # '다음 달'=2026-07 날짜 행
    assert "회피일" in text
    assert "회피성 답변을 절대 하지 말 것" in text
    table = text.split("[택일 결과")[1].split("회피일")[0]
    assert "[avoid]" not in table  # 추천 표에 회피 등급 없음


# ── P4 — 월별 요약(12개월) ───────────────────────────────────────


def test_monthly_overview_for_monthly_question() -> None:
    text = _preview("올해운을 월별로 이야기 해줘")
    assert "[월별 요약" in text
    for m in range(2, 13):  # 2~12월(1월은 입춘 전 — 전년 구간 표기)
        assert f"2026-{m:02d}" in text
    assert "입춘 전" in text  # 2026-01 정직 표기
    # 연 단위 질문에 대운 전체(10줄) 과밀 금지 — 달력 섹션에는 관련 대운만.
    calendar = text.split("[간지달력(압축)]")[1].split("[이벤트 후보")[0]
    daewoon_lines = [ln for ln in calendar.splitlines() if ln.startswith("대운 ")]
    assert len(daewoon_lines) <= 3


# ── P5 — 표기 정제(한글 라벨·내부 노트 제거) ─────────────────────


def test_korean_labels_and_no_internal_notes() -> None:
    text = _preview("올해 이직운 어때?")
    assert "이직·직업 변화 @" in text  # 한글 라벨
    assert "career_change @" not in text  # 영문 키 라인 금지
    assert "(docs/" not in text  # 내부 회귀 노트 제거
    assert "영문 내부 키를 답변에 노출하지 말 것" in text
    assert "부담·비자발 계열" in text or "우호적" in text  # polarity 한글


# ── P6 — 점수·신호 건수 미노출, 강도는 치환 문장만(v2.2.1 항목 5) ──────


def test_scores_not_exposed_only_phrases() -> None:
    """점수 숫자·신호 건수는 내부 변수라 노출 금지 — 강도는 표현 문장으로만."""
    text = _preview("올해 이직운 어때?")
    assert "점(신호 " not in text  # 'NN점(신호 N건)' 형태 제거
    # 강도 치환 문장(tone_for_score)이 후보 줄에 들어간다.
    assert any(
        phrase in text
        for phrase in ("신호가 매우 강합니다", "가능성이 높습니다", "흐름이 나타날 수 있습니다")
    )


# ── P7 — 자가 검증 지시 + 페르소나 결합 ──────────────────────────


def test_self_check_instruction_present() -> None:
    text = _preview("올해 이직운 어때?")
    assert "자체 검증" in text and "입력에 실제로 존재하는지" in text


def test_persona_block_composes_system(monkeypatch) -> None:
    """persona 지정 시 시스템 프롬프트에 5-3 템플릿 블록 결합(문체 전용)."""
    from saju_api.services import llm_client
    from saju_shared_types.profile import PersonaConfig

    captured: dict = {}

    def fake_reading(prompt_text, call_type="chat_single", system=None, **kw):
        captured["system"] = system
        return "모의 응답입니다."

    monkeypatch.setattr(llm_client, "is_available", lambda: True)
    monkeypatch.setattr(llm_client, "generate_reading", fake_reading)
    res = chat_service.chat(
        _BIRTH, "올해 이직운 어때?", _TODAY,
        persona=PersonaConfig(),
    )
    assert res.status == "answered"
    assert captured["system"] is not None
    assert "[페르소나 — 필수 준수]" in captured["system"]
    assert "점수·날짜·간지·판정을 바꾸는 것" in captured["system"]  # 문체 전용 고지
