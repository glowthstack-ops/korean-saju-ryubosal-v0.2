"""원국 지지 자리 십성 표기 감사 — 2026-10-13 실답 회귀(월지 편관 → '정관' 오기).

프롬프트에 '월주 丙子 · 지지 편관'이 정확히 실렸는데 답변이 "월지에 자리한 정관의 기운"으로 썼다.
명확한 불일치만 결정론으로 고치고(재호출 없음), 모호한 문장은 건너뛴다.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any, cast

import pytest

from saju_api.services import chat_service
from saju_api.services.manse_service import calculate
from saju_engines.ten_god_label_audit import (
    audit_ten_god_labels,
    facts_from_pillar_details,
    facts_from_pillars,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.llm_input import PillarDetail

# 1975-01-01 07:30 서울 여 — 甲寅·丙子·丁未·癸卯(丁 일간) 실측 지지 본기 십성.
_FACTS = {"year": ("정인", "寅"), "month": ("편관", "子"), "day": ("식신", "未"),
          "hour": ("편인", "卯")}


def test_incident_sentence_is_corrected():
    text = "월지에 자리한 정관의 기운이 단정한 인상을 만들고, 시지의 인성이 보호 본능을 자극해요."
    fixed, fixes = audit_ten_god_labels(text, _FACTS)
    assert fixed == text.replace("정관", "편관")
    assert [(f.position, f.written, f.corrected) for f in fixes] == [("월지", "정관", "편관")]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("월지 子(자) 정관이 들어와요.", "월지 子(자) 편관이 들어와요."),
        ("일지는 정재라서요.", "일지는 식신이라서요."),  # 조사도 받침에 맞춘다
        ("월지 정관이 강해요", "월지 편관이 강해요"),
        ("일지에 있는 정관을 보면", "일지에 있는 식신을 보면"),
        ("월지 정재가 있어", "월지 편관이 있어"),
        ("시지 재성의 힘", "시지 인성의 힘"),  # 십성군으로 썼으면 십성군으로
    ],
)
def test_clear_mismatches_are_corrected(text, expected):
    fixed, fixes = audit_ten_god_labels(text, _FACTS)
    assert fixed == expected and len(fixes) == 1


@pytest.mark.parametrize(
    "text",
    [
        "월지에 자리한 편관의 기운",          # 일치
        "시지의 인성이 보호 본능을",           # 십성군 일치(편인 ∈ 인성)
        "월지와 시지에 자리한 편관과 편인",     # 자리어 나열 — 모호
        "월지 정관과 편관이 섞여",             # 십성 나열 — 모호
        "세운의 월지 정관",                   # 운 표현 직후 — 운 기둥일 수 있음
        "월지 午 정관",                       # 적힌 글자가 원국 월지(子)와 다름
        "업무 일지를 쓰세요. 연간 정재 수입",   # 일상어·천간 자리어 제외
        "월지 관성도화(본기 편관)",            # 블록 표기 그대로
    ],
)
def test_ambiguous_or_matching_text_is_untouched(text):
    fixed, fixes = audit_ten_god_labels(text, _FACTS)
    assert fixed == text and fixes == []


def test_hour_unknown_skips_only_hour():
    """시주 미상이면 **시지만** 검사하지 않는다 — 연지·월지·일지 교정은 그대로 한다."""
    r = calculate(BirthInput(
        birth_date=date(1975, 1, 1), birth_time=None, birth_time_unknown=True,
        birth_place_name="서울", gender="female",
    ))
    assert r.pillars is not None
    facts = facts_from_pillars(r.pillars)
    assert set(facts) == {"year", "month", "day"}
    assert audit_ten_god_labels("시지 정관", facts) == ("시지 정관", [])
    fixed, fixes = audit_ten_god_labels("월지에 자리한 정관과 다른 이야기", facts)
    assert fixed == "월지에 자리한 편관과 다른 이야기" and len(fixes) == 1
    # 채팅 경로(LLM 입력 기둥 상세)도 시주 미상이면 시지 상세가 없어 시지만 빠진다.
    details = [
        PillarDetail(palace=slot, ganji=getattr(r.pillars, slot).ganji,
                     stem_ten_god=getattr(r.pillars, slot).stem_ten_god,
                     branch_ten_god=getattr(r.pillars, slot).branch_main_ten_god,
                     twelve_stage="")
        for slot in ("year", "month", "day")
    ]
    assert facts_from_pillar_details(details) == facts


def test_facts_from_real_chart_match_prompt_details():
    """실제 명식 — 만세 기둥과 LLM 입력 기둥 상세에서 같은 정답표가 나온다."""
    r = calculate(BirthInput(
        birth_date=date(1975, 1, 1), birth_time="07:30:00", birth_place_name="서울",
        gender="female",
    ))
    assert r.pillars is not None
    from_pillars = facts_from_pillars(r.pillars)
    assert from_pillars["month"] == ("편관", "子") and from_pillars["hour"] == ("편인", "卯")
    details = [
        PillarDetail(palace=slot, ganji=getattr(r.pillars, slot).ganji,
                     stem_ten_god=getattr(r.pillars, slot).stem_ten_god,
                     branch_ten_god=getattr(r.pillars, slot).branch_main_ten_god,
                     twelve_stage="")
        for slot in ("year", "month", "day", "hour")
    ]
    assert facts_from_pillar_details(details) == from_pillars


def _ctx(subject_blocks: int = 0, relationship: bool = False, prompt: str = "") -> Any:
    details = [
        PillarDetail(palace="month", ganji="丙子", stem_ten_god="겁재", branch_ten_god="편관",
                     twelve_stage=""),
    ]
    payload = SimpleNamespace(
        chart_interpretation=SimpleNamespace(pillar_details=details),
        subject_blocks=[object()] * subject_blocks,
        relationship_context=object() if relationship else None,
    )
    return cast(Any, SimpleNamespace(payload=payload, prompt_text=prompt))


def test_chat_audit_corrects_single_subject():
    out = chat_service._audit_ten_god_labels_answer("월지에 자리한 정관", _ctx(), "t")
    assert out == "월지에 자리한 편관"


@pytest.mark.parametrize(
    "ctx_kwargs",
    [{"subject_blocks": 2}, {"relationship": True}, {"prompt": "[궁합 신호 — 엔진 계산값]"}],
)
def test_chat_audit_skips_multi_person_answers(ctx_kwargs):
    """동반자 공동 풀이·궁합 답은 어느 사람의 자리인지 확정할 수 없어 건너뛴다."""
    text = "월지에 자리한 정관"
    assert chat_service._audit_ten_god_labels_answer(text, _ctx(**ctx_kwargs), "t") == text


# ── 2026-10-14 검수 반례 ─────────────────────────────────────────────────────────────────

# 받침 없는 교정어(정재)·받침 있는 교정어(정관)가 섞인 facts — 서술격 '이-' 처리 확인용.
_FACTS_MIXED = {"month": ("정재", "申"), "day": ("정관", "亥")}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("월지에 자리한 식신이죠.", "월지에 자리한 정재죠."),
        ("월지 식신이지만 힘이 약해요.", "월지 정재지만 힘이 약해요."),
        ("월지의 식신이네요.", "월지의 정재네요."),
        ("월지 식신이면", "월지 정재면"),
        ("월지 식신이다.", "월지 정재다."),
        ("일지 정재죠.", "일지 정관이죠."),            # 역방향 — 받침 생기면 '이' 복원
        ("일지 정재지만", "일지 정관이지만"),
        ("월지 식신이 다 모여", "월지 정재가 다 모여"),  # 주격 '이/가'는 그대로 동작
    ],
)
def test_predicative_josa_is_adjusted_not_turned_into_subject_marker(text, expected):
    """서술격 '이죠·이지만·이네요·이면·이다'를 주격 '가'로 바꾸는 비문('정재가죠')을 내지 않는다."""
    fixed, fixes = audit_ten_god_labels(text, _FACTS_MIXED)
    assert fixed == expected and len(fixes) == 1


@pytest.mark.parametrize("text", ["일지 亥에 든 정인(甲)의 기운", "일지에 든 편인"])
def test_hidden_stem_description_is_not_corrected(text):
    """'에 든'은 지장간 서술 — 자리 본기 십성으로 바꾸지 않는다."""
    assert audit_ten_god_labels(text, _FACTS_MIXED) == (text, [])
