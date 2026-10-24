"""실답 web-mvf73q3h(2026-10-19) 교정 회귀 — '이력서 넣기 좋은 날' 2턴.

①택일 지평=탐색 창(기반 최고 달·유력 달 종합 의무 없음) ②택일 표 라벨=취업 서류 제출 ③회피 구간에
추천일이 끼면 회피일 목록으로 ④공망 지목 감사 ⑤현재 대운 지지 공망 사실 명시 ⑥일주 문장 제거 시
지시어
보존 ⑦사실 반박형 이의 ⑧커리어 폴백 전제 금지 가드 ⑨마무리 질문 뒤 꼬리 제거.
"""

from __future__ import annotations

from datetime import date, time

import pytest

from saju_api.services import chat_service
from saju_engines.challenge_detect import is_challenge
from saju_engines.date_answer_audit import rewrite_avoid_ranges, strip_after_closing_question
from saju_engines.gongmang_claim_audit import audit_gongmang_claims
from saju_engines.horizon import horizon_directive, resolve_horizon
from saju_engines.ilju_mention_audit import audit_ilju_mention
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import Domain, IntentJson, QueryType

# 실답 명식(庚申 丁亥 己亥 己巳, 일공망 辰巳, 현재 대운 壬辰) — 진태양시 보정 전 입력.
_BIRTH = BirthInput(
    birth_date=date(1980, 11, 22), birth_time=time(9, 40), birth_place_name="서울 구로구",
    latitude=37.4944, longitude=126.8563, timezone="Asia/Seoul", gender="male",
)
_TODAY = date(2026, 10, 19)
_VOID = ["辰", "巳"]


@pytest.fixture(scope="module")
def resume_prep() -> chat_service.ChatResponse:
    res = chat_service.chat(_BIRTH, "이력서 넣기 좋은 날을 알려줘", _TODAY, dry_run=True)
    assert res.status == "dry_run"
    return res


# ── ① ② ⑤ 택일 프롬프트 ─────────────────────────────────────────────────


def test_date_pick_horizon_is_search_window() -> None:
    it = IntentJson(intent_id="i", query_type=QueryType.DATE_RECOMMENDATION, domain=Domain.CAREER)
    pol = resolve_horizon("이력서 넣기 좋은 날을 알려줘", it)
    assert pol is not None and pol.kind == "date_window" and pol.months_detail == 2
    assert pol.years_span == 0
    assert "추천일을 먼저" in horizon_directive(pol)


def test_non_date_question_horizon_unchanged() -> None:
    """반례 — 분야 개요는 기존 분야 기본 지평."""
    it = IntentJson(intent_id="i", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.CAREER)
    pol = resolve_horizon("취업운 어때?", it)
    assert pol is not None and pol.kind == "domain_default"


def test_resume_prompt_has_no_month_obligations_and_job_label(resume_prep) -> None:
    p = resume_prep.prompt_preview or ""
    assert "기반 최고" not in p and "유력 달 종합" not in p
    assert "[택일 결과 — 취업 서류 제출" in p
    assert "택일 탐색 창" in p
    assert "2027-02 壬寅" not in p  # 창 밖 달 표 행 없음


def test_resume_prompt_states_daewoon_void_fact(resume_prep) -> None:
    p = resume_prep.prompt_preview or ""
    assert "대운 지지 공망(엔진 사실): 현재 대운 壬辰의 지지 辰" in p
    assert "월운·세운 글자를 공망이라 부르지 말 것" in p


# ── ③ 회피 구간 ──────────────────────────────────────────────────────────


_REC = ["2026-10-29", "2026-11-01", "2026-11-11", "2026-10-20", "2026-11-13"]
_AVOID = ["2026-10-19", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24"]


def test_avoid_range_with_recommended_day_rewritten() -> None:
    text = (
        "반면 10월 19일부터 24일까지는 관계가 엉키는 기운이 강해 서류 제출은 피하는 것이 "
        "좋습니다."
    )
    out = rewrite_avoid_ranges(text, _REC, _AVOID, 2026)
    assert out.text == (
        "반면 10월 19일, 21일, 22일, 23일, 24일은 관계가 엉키는 기운이 강해 서류 제출은 "
        "피하는 것이 좋습니다."
    )


def test_avoid_range_without_recommended_day_kept() -> None:
    """반례 — 구간 안에 추천일이 없으면(21~24일) 그대로 둔다."""
    text = "10월 21일부터 24일까지는 서류 제출을 피하세요."
    assert rewrite_avoid_ranges(text, _REC, _AVOID, 2026).text == text


def test_non_avoid_range_sentence_kept() -> None:
    """반례 — 피하라는 문장이 아니면(추천 구간 안내) 손대지 않는다."""
    text = "10월 19일부터 24일까지 준비 서류를 정리해 두세요."
    assert rewrite_avoid_ranges(text, _REC, _AVOID, 2026).text == text


# ── ④ 공망 지목 ──────────────────────────────────────────────────────────


def test_month_branch_called_gongmang_removed() -> None:
    answer = (
        "이러한 흐름은 2026년 11월 己亥(기해) 월운에서 "
        "뚜렷해집니다. 비견의 기운이 들어와 제안의 기회는 "
        "열리지만 지지의 정재가 공망의 영향으로 지연을 일으켜 승인이 더딜 수 있습니다. "
        "태의 에너지가 흐르는 시기입니다."
    )
    out = audit_gongmang_claims(answer, _VOID, set())
    assert len(out.removed) == 1 and "공망" not in out.text
    assert out.text.endswith("태의 에너지가 흐르는 시기입니다.")


def test_gongmang_fact_sentences_kept() -> None:
    """반례 — 원국 시지 巳·현재 대운 辰을 공망으로 말한 문장, 부정문, 신호 있는 달은 둔다."""
    keep = [
        "원국에서 비어 있는 기운은 시주의 巳(사) 정인 자리뿐입니다.",
        "현재 대운 壬辰의 지지 辰은 공망 글자입니다.",
        "일지 亥(해) 정재는 공망에 해당하지 않는 것이 맞습니다.",
        "2027년 5월 乙巳월은 공망지 巳가 채워지는 공망 전실의 달입니다.",
    ]
    for s in keep:
        out = audit_gongmang_claims(s, _VOID, {"2027-05"})
        assert out.text == s, s


def test_signal_month_gongmang_kept() -> None:
    """반례 — 엔진이 공망 신호를 표기한 달이면 글자 지목 없이 말해도 둔다."""
    s = "2027년 5월에는 공망이 채워지며 문서가 움직입니다."
    assert audit_gongmang_claims(s, _VOID, {"2027-05"}).text == s


# ── ⑥ 일주 지시어 보존 ───────────────────────────────────────────────────


def test_ilju_intro_and_referent_both_removed_for_timing_types() -> None:
    """2026-10-22 개정: 총운·시기·택일(질문 유형으로 걸린 답)은 참조 예외 없이 지시 문장까지 제거.
    실답 '언제 취업할 수 있을까'에서 '己亥 일주는 … 이러한 기질은 …' 두 문장이 통째로 남던 결함."""
    answer = (
        "데굴님의 己亥(기해) 일주는 다정하고 실리를 추구하는 구조입니다. "
        "이러한 성향은 2026년 11월 己亥 월운을 만나며 더욱 뚜렷해집니다."
    )
    out = audit_ilju_mention(answer, QueryType.DATE_RECOMMENDATION, Domain.CAREER)
    assert out.text == "" and len(out.removed) == 1 and len(out.removed_referents) == 1
    assert not out.kept_referenced


def test_ilju_intro_across_paragraph_referent_removed_too() -> None:
    answer = (
        "추천일은 11월 1일이에요.\n\n데굴님의 己亥(기해) 일주는 다정한 구조입니다.\n\n"
        "이런 기질은 서류 준비에서 드러나요."
    )
    out = audit_ilju_mention(answer, QueryType.DATE_RECOMMENDATION, Domain.CAREER)
    assert out.text == "추천일은 11월 1일이에요."
    assert out.removed_referents == ["이런 기질은 서류 준비에서 드러나요."]


def test_ilju_intro_referent_kept_for_domain_analysis() -> None:
    """분야 개요(domain_analysis)는 기존 참조 예외 유지 — 로그만 남긴다."""
    answer = (
        "데굴님의 己亥(기해) 일주는 다정하고 실리를 추구하는 구조입니다. "
        "이러한 성향은 2026년 11월 己亥 월운을 만나며 더욱 뚜렷해집니다."
    )
    out = audit_ilju_mention(answer, QueryType.DOMAIN_ANALYSIS, Domain.CAREER)
    assert out.text == answer and not out.removed and out.kept_referenced


# ── ⑦ 사실 반박형 이의 ───────────────────────────────────────────────────


@pytest.mark.parametrize("q", [
    "지지의 정재는 공망이랑 상관없는 글자인데 대운의 공망을 이야기 하는거야?",
    "亥는 공망이 아닌데 왜 공망이라고 해?",
    "11월은 용신운이랑 관계없는 달인데 그게 맞아?",
])
def test_fact_rebuttal_is_challenge(q: str) -> None:
    assert is_challenge(q)


@pytest.mark.parametrize("q", [
    "공망이 뭐야?",
    "이력서 넣기 좋은 날을 알려줘",
    "나랑 상관없는 일인데 신경 쓰여",  # 확인형 반문 없음
])
def test_non_rebuttal_not_challenge(q: str) -> None:
    assert not is_challenge(q)


# ── ⑧ 커리어 폴백 가드 ───────────────────────────────────────────────────


def test_career_fallback_keeps_presupposition_guard(monkeypatch) -> None:
    from types import SimpleNamespace

    from saju_engines import career_chat_consumer

    sent: dict[str, str] = {}
    monkeypatch.setattr(
        career_chat_consumer, "audit_career_chat_response",
        lambda answer, prep: SimpleNamespace(delivered=False, violations=[]),
    )
    monkeypatch.setattr(
        chat_service.llm_client, "generate_reading",
        lambda prompt, **kw: sent.setdefault("p", prompt) or "재생성",
    )
    prep = SimpleNamespace(
        eligible=True,
        directive=(
            "[커리어] 확인된 지원·면접 사실이 없으므로, 지금 진행 중인 절차가 있다고 "
            "전제하지 말 것."
        ),
    )
    chat_service._audit_career_transition_answer(
        "답", prep, "본문\n\n" + prep.directive, "chat_single", None, None, "t",
    )
    assert "확인된 지원·면접 사실이 없" not in sent["p"].split("[전제 금지]")[0]
    assert "[전제 금지]" in sent["p"] and "이미 들어온 제안" in sent["p"]


# ── ⑨ 마무리 질문 뒤 꼬리 ────────────────────────────────────────────────


def test_tail_after_closing_question_removed() -> None:
    text = (
        "본문입니다.\n\n준비 중인 자격이 있습니까? "
        "여기서부터 다음 운이 본격적으로 풀릴 것으로 보입니다."
    )
    out = strip_after_closing_question(text)
    assert out.text == "본문입니다.\n\n준비 중인 자격이 있습니까?"


def test_mid_answer_question_not_treated_as_closing() -> None:
    """반례 — 본문 중간 질문 뒤에 긴 본문이 이어지면 손대지 않는다."""
    text = "왜 늦어질까요? " + "이유는 지연 신호 때문이에요. " * 20
    assert strip_after_closing_question(text).text == text


def test_notice_line_after_question_kept() -> None:
    """반례 — 질문 뒤 줄을 바꾼 고지 줄(beta 안내 등)은 지우지 않는다."""
    text = "본문입니다.\n무엇이 가장 중요한가요?\n\n※ 관계 신호는 시험(beta) 관측치예요."
    assert strip_after_closing_question(text).text == text


def test_answer_ending_with_question_untouched() -> None:
    text = "본문입니다. 어떤 달을 먼저 볼까요?"
    assert strip_after_closing_question(text).text == text
