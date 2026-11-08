"""실답 교정 3건(2026-11-08) — ① '저번달/지난달' 파싱·회고 판정 ② 단식 참고 줄 결정론 삽입
③ 후속 확인 중복 제거·'다음에' 보류 키.
"""

from __future__ import annotations

import datetime as dt

from saju_api.services import chat_service
from saju_engines.life_event_followup import (
    FollowupCandidate,
    asked_keys_from_meta,
    exclude_asked,
)
from saju_engines.time_parser import parse_time
from saju_shared_types.intent import Granularity, IntentJson, QueryType, TimeRange
from saju_shared_types.llm_input import LlmInput, PeriodFortune

_TODAY = dt.date(2026, 11, 8)  # 己亥월(11/8 입동 후) — 지난 달 = 2026-10 戊戌월


def _tr(text: str) -> TimeRange | None:
    tr, _scope = parse_time(text, _TODAY, current_month_label="2026-11")
    return tr


# ── ① 지난 달 파싱 ──────────────────────────────────────────────────────────


def test_last_month_expressions_resolve_to_previous_luck_month() -> None:
    for q in ("저번달 운세는 어때?", "지난달 운세는 어땠어?", "지난 달 어땠어", "저번 달은?"):
        tr = _tr(q)
        assert tr is not None, q
        assert (tr.granularity, tr.start, tr.end) == (Granularity.MONTH, "2026-10", "2026-10"), q
    tr = _tr("지지난달은 어땠어?")
    assert tr is not None and (tr.start, tr.end) == ("2026-09", "2026-09")
    # '이번 달'·'다음 달'은 종전 그대로.
    assert _tr("이번 달 운세는 어때?").start == "2026-11"
    assert _tr("다음 달 운세는 어때?").start == "2026-12"


def test_last_month_question_is_retro_even_with_present_tense_verb() -> None:
    """'저번달 운세는 어때?' — 동사는 현재형이지만 창이 과거라 회고 모드(window_past)."""
    intent = IntentJson(
        intent_id="t", query_type=QueryType.FORTUNE_OVERVIEW,
        time_range=TimeRange(
            type="relative", granularity=Granularity.MONTH, start="2026-10", end="2026-10",
        ),
    )
    retro, reason = chat_service._question_time_direction_reason(
        "저번달 운세는 어때?", intent, None, _TODAY, "2026-11",
    )
    assert retro and reason == "window_past"
    # 시점 창이 없어도 '저번' 문구만으로 회고.
    assert "저번" in chat_service._PAST_KEYWORDS


# ── ② 단식 참고 줄 결정론 삽입 ──────────────────────────────────────────────


def _payload(line: str) -> LlmInput:
    pf = PeriodFortune(
        fortune_type="monthly", period_label="2026-10", ganji="戊戌", pillar_line="-",
        simple_reading_line=line,
    )
    return LlmInput.model_construct(period_fortune=pf)


def test_simple_reading_line_inserted_after_first_paragraph_when_missing() -> None:
    line = (
        "간단히 봤을 때, 戊戌월은 경(庚) 일간에게 인성(편인·편인) 결이에요. "
        "생각이 깊어지는 달이에요."
    )
    answer = "첫 판정 문단이에요.\n\n둘째 문단이에요."
    fixed = chat_service._ensure_simple_reading_line(answer, _payload(line), "t")
    assert fixed == f"첫 판정 문단이에요.\n\n{line}\n\n둘째 문단이에요."
    # LLM 이 바꿔 쓴 단식 문단은 엔진 문단으로 교체(2026-11-08 실답: '겁재 — 경쟁심·지출'로 변형).
    # 그 다음 문단(개인 판정 '다만 이 명식에서는')은 그대로 남는다.
    present = (
        "첫 문단.\n\n간단히 봤을 때, 다른 표현으로 쓴 문장.\n\n다만 이 명식에서는 다르다.\n\n둘째."
    )
    fixed2 = chat_service._ensure_simple_reading_line(present, _payload(line), "t")
    assert fixed2 == f"첫 문단.\n\n{line}\n\n다만 이 명식에서는 다르다.\n\n둘째."
    # 엔진 문단 그대로면 바이트 불변.
    exact = f"첫 문단.\n\n{line}\n\n둘째."
    assert chat_service._ensure_simple_reading_line(exact, _payload(line), "t") == exact


def test_simple_reading_paragraph_keeps_persona_style_when_content_faithful() -> None:
    """페르소나 말투(합쇼체·반말체)로 종결어미만 바뀐 단식 문단은 그대로 둔다(2026-11-08 데굴님)."""
    line = (
        "간단히 봤을 때, 戊戌월은 기(己) 일간에게 비겁(겁재·겁재) 결이에요. 내 몫을 챙기는 일이 "
        "중요해지는 달이에요. 올해 丙午년은 인성(정인·편인) 결이에요. 받아들이고 쉬는 해예요. "
        "하던 일이 갑자기 멈추거나 게으름이 길어지기 쉽고, 몸이 쉬라고 신호를 보내기도 해요. "
        "(일간과 운의 십성만 본 단식 풀이라 참고용이에요. 길흉과 개인 판정은 명식 전체 기준이 "
        "우선이에요.)"
    )
    hapsyo = (
        "간단히 봤을 때, 戊戌월은 기(己) 일간에게 비겁(겁재·겁재) 결입니다. 내 몫을 챙기는 일이 "
        "중요해지는 달입니다. 올해 丙午년은 인성(정인·편인) 결입니다. 받아들이고 쉬는 해입니다. "
        "하던 일이 갑자기 멈추거나 게으름이 길어지기 쉽고, 몸이 쉬라고 신호를 보내기도 합니다. "
        "(일간과 운의 십성만 본 단식 풀이라 참고용입니다.)"
    )
    banmal = (
        "간단히 봤을 때, 戊戌월은 기(己) 일간에게 비겁(겁재·겁재) 결이야. 내 몫을 챙기는 일이 "
        "중요해지는 달이야. 올해 丙午년은 인성(정인·편인) 결이야. 받아들이고 쉬는 해야. "
        "하던 일이 갑자기 멈추거나 게으름이 길어지기 쉽고, 몸이 쉬라고 신호를 보내기도 해."
    )
    for styled in (hapsyo, banmal):
        answer = f"첫 판정.\n\n{styled}\n\n다만 이 명식에서는 충전 쪽이에요."
        assert chat_service._ensure_simple_reading_line(answer, _payload(line), "t") == answer
    # 내용이 바뀐 문단(실답: 겁재 — 경쟁심·지출, 올해 결·절정 문장 누락)은 교체된다.
    distorted = (
        "간단히 봤을 때, 2026년 10월은 기 일간에게 겁재의 기운이 강하게 작용했던 달이었습니다. "
        "일반적으로는 경쟁심이 강해지고 지출이 늘어나는 시기로 봅니다."
    )
    answer = f"첫 판정.\n\n{distorted}\n\n둘째."
    fixed = chat_service._ensure_simple_reading_line(answer, _payload(line), "t")
    assert fixed == f"첫 판정.\n\n{line}\n\n둘째."


def test_simple_reading_audit_respects_persona_style() -> None:
    """실답(2026-11-08): 합쇼체 답에서 표지 없는 LLM 문단을 못 찾아 해요체 원문이 추가 삽입됨."""
    from saju_engines.speech_style import restyle

    line = (
        "간단히 봤을 때, 戊戌월은 기(己) 일간에게 비겁(겁재·겁재)의 달이고, 올해 丙午년은 "
        "인성(정인·편인)의 해예요. 받아들이고 쉬는 해예요. 발판이 되는 쪽이면 배움이 들어와요. "
        "소모가 되는 쪽이면 하던 일이 멈춰요. (일간과 운의 십성만 본 단식 풀이라 참고용이에요.)"
    )
    styled = restyle(line, "hapsyo")
    assert styled.endswith("참고용입니다.)") and "해입니다" in styled
    # ① 표지 없이 요약·병합한 문단(실답) — 핵심어로 찾아 교체하고, 그 안의 개인 판정
    #    문장('이 명식에서는 … 발판')은 뒤에 살린다. 중복 삽입은 없다.
    merged = (
        "지난 10월 戊戌월은 기(己) 일간에게 비겁(겁재)의 결이었습니다. 내 몫을 챙기는 일이 "
        "중요해지는 시기로, 올해 丙午년의 인성 흐름과 겹쳐 재정비가 이루어졌을 것입니다. "
        "이 명식에서는 토(土)가 "
        "용신으로 작용하므로 이러한 비겁의 유입은 더 좋은 방향으로 나아가기 위해 등을 떠미는 "
        "발판이 "
        "되었습니다."
    )
    answer = f"첫 판정입니다.\n\n{merged}\n\n일과 직업 면에서는 유리했습니다."
    fixed = chat_service._ensure_simple_reading_line(answer, _payload(line), "t", "hapsyo")
    assert fixed.count("간단히 봤을 때") == 1
    assert fixed.startswith(f"첫 판정입니다.\n\n{styled}\n\n이 명식에서는 토(土)가 용신으로")
    assert fixed.endswith("일과 직업 면에서는 유리했습니다.")
    assert "결이에요" not in fixed  # 해요체 잔여 없음
    # ② 표지 없이도 내용이 충실한 합쇼체 문단은 그대로 둔다.
    faithful = styled.replace("간단히 봤을 때, ", "")
    answer2 = f"첫 판정입니다.\n\n{faithful}\n\n둘째입니다."
    kept2 = chat_service._ensure_simple_reading_line(answer2, _payload(line), "t", "hapsyo")
    assert kept2 == answer2
    # ③ 문단이 아예 없으면 설정 말투로 변환해 삽입한다.
    answer3 = "첫 판정입니다.\n\n둘째입니다."
    fixed3 = chat_service._ensure_simple_reading_line(answer3, _payload(line), "t", "banmal_chae")
    assert fixed3 == f"첫 판정입니다.\n\n{restyle(line, 'banmal_chae')}\n\n둘째입니다."
    # 줄이 없으면(총운 아님) 불변.
    assert chat_service._ensure_simple_reading_line(answer, _payload(""), "t") == answer
    # 한 문단뿐이면 끝에 붙인다.
    one = chat_service._ensure_simple_reading_line("한 문단.", _payload(line), "t")
    assert one == f"한 문단.\n\n{line}"


# ── ③ 후속 확인 중복 제거·보류 키 ──────────────────────────────────────────


def test_exclude_asked_drops_candidates_answered_elsewhere() -> None:
    cands = [
        FollowupCandidate(event_key="wealth_change", event_ko="재물 변화", period="2026-10"),
        FollowupCandidate(event_key="career_change", event_ko="이직", period="2026-10"),
    ]
    asked = {("wealth_change", "2026-10")}
    left = exclude_asked(cands, asked)
    assert [c.event_key for c in left] == ["career_change"]
    assert exclude_asked(cands, set()) == cands


def test_asked_keys_from_meta_reads_answers_and_dismissed_candidates() -> None:
    meta = {
        "followup_answered": {"answers": [
            {"event_key": "wealth_change", "period": "2026-10", "outcome": "confirmed"},
            {"event_key": "contract_document", "period": "2026-10", "outcome": "unknown"},
        ]},
        "followup_dismissed": {"candidates": [{"event_key": "career_change", "period": "2026-10"}]},
    }
    assert asked_keys_from_meta(meta) == {
        ("wealth_change", "2026-10"),
        ("contract_document", "2026-10"),
        ("career_change", "2026-10"),
    }
    assert asked_keys_from_meta({}) == set()
