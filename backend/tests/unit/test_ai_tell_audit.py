"""한글 AI 티 문체 층(2026-10-19 데굴님 승인) — 사전·지시문·탐지·자동 교정 3종·보호 불변식."""

from __future__ import annotations

import pytest

from saju_engines.ai_tell_audit import (
    apply_safe_fixes,
    audit_ai_tells,
    build_style_directive,
    detect_ai_tells,
    load_ai_tell_patterns,
    s1_ids,
)


def _ids(findings) -> set[str]:
    return {f.id for f in findings}


# ── 사전·지시문 ──────────────────────────────────────────────────────────


def test_dictionary_loads_with_source_and_fix_scope():
    """사전은 MIT 출처를 적고, 자동 교정(fix)은 승인된 3종(A-3·A-8·D-1a)에만 있다."""
    f = load_ai_tell_patterns()
    assert f.source.license == "MIT" and "im-not-ai" in f.source.url
    assert {it.id for it in f.items if it.fix} == {"A-3", "A-8", "D-1a"}
    # S1 9종 — 2026-10-29 D-15(판정 라벨 직역 '조건부 유리함') 추가, 자동 교정 없음.
    assert sum(1 for it in f.items if it.severity == "S1") == 9
    assert all(it.reviewed is False for it in f.items)


def test_directive_is_dictionary_substitution_only():
    """지시문은 사전 directive 문구 치환으로만 만들어지고 슬롯·내부 enum 이 없다."""
    f = load_ai_tell_patterns()
    chat = build_style_directive("chat")
    assert chat.startswith(f.directive.header)
    for it in f.items:
        if "chat" in it.scopes:
            assert it.directive in chat
    assert "{" not in chat and "}" not in chat
    # 충돌 조정 — 단정 전환 금지·마무리 규칙 8 공존.
    assert "단정으로 바꾸지 않는다" in chat
    assert "결론적으로·정리하자면' 없이" in chat


def test_directive_daily_is_one_line_and_short():
    """오늘의 운세용은 카드 길이에 맞춘 한 줄(개행 없음)이며 daily 범위 항목만 담는다."""
    f = load_ai_tell_patterns()
    daily = build_style_directive("daily")
    assert "\n" not in daily
    for it in f.items:
        if "daily" not in it.scopes:
            assert it.directive not in daily
    assert len(daily) < len(build_style_directive("chat")) / 2


def test_report_directive_mentions_section_title_exclusion():
    """리포트 머리말은 섹션 제목(docs/10 규격)을 대상에서 뺀다고 적는다."""
    assert "섹션 제목은 그대로" in build_style_directive("report")


# ── 자동 교정 3종(양성 + 반례) ───────────────────────────────────────────


def test_fix_a3_abstract_noun_only():
    """A-3: 추상명사 뒤 '에 있어서'만 '에서'로 — 실제 머무름 동사('집에 있어서')는 손대지 않는다."""
    fixed, fixes, discarded = apply_safe_fixes("재물에 있어서 올해는 좋아요. 집에 있어서 편해요.")
    assert fixed == "재물에서 올해는 좋아요. 집에 있어서 편해요."
    assert [x.id for x in fixes] == ["A-3"] and not discarded


def test_fix_a8_double_passive_family():
    """A-8: '되어져요·되어집니다·되어진·되어지는'을 단일 피동으로.

    '돼지(동물)'·'지게 되다'는 불변이다.
    """
    text = (
        "정리되어져요. 관계가 형성되어집니다. 만들어지게 돼요. 돼지고기는 피하세요. "
        "결정되어지는 일."
    )
    fixed, fixes, _ = apply_safe_fixes(text)
    assert fixed == (
        "정리돼요. 관계가 형성됩니다. 만들어지게 돼요. 돼지고기는 피하세요. 결정되는 일."
    )
    assert [x.id for x in fixes] == ["A-8"]


def test_fix_d1a_only_sentence_initial():
    """D-1a: 문두 '결론적으로,·정리하자면'만 삭제.

    문장 중간('그래서 결론적으로')은 남기고 로그만 남긴다.
    """
    text = (
        "결론적으로, 이직은 하반기가 나아요. 그래서 결론적으로 보면 기다리세요.\n"
        "정리하자면 서두르지 마세요."
    )
    fixed, fixes, _ = apply_safe_fixes(text)
    assert fixed == (
        "이직은 하반기가 나아요. 그래서 결론적으로 보면 기다리세요.\n서두르지 마세요."
    )
    assert [x.id for x in fixes] == ["D-1a"]
    assert "D-1a" in _ids(detect_ai_tells(fixed))  # 잔존 1건은 탐지에 남는다


def test_fix_skips_direct_quotes():
    """큰따옴표 안(직접 인용)은 교정하지 않는다."""
    text = '사용자가 "결론적으로 어떻게 하죠?"라고 물었어요. 결론적으로, 지금은 아니에요.'
    fixed, _, _ = apply_safe_fixes(text)
    assert fixed == '사용자가 "결론적으로 어떻게 하죠?"라고 물었어요. 지금은 아니에요.'


def test_fix_preserves_ganji_and_digits():
    """교정 전후 간지·숫자 다중집합이 같아야 한다 — 2026년 甲午 가 그대로다."""
    text = "결론적으로, 2026년 甲午 세운은 재물에 있어서 강해요."
    audit = audit_ai_tells(text, "chat")
    assert audit.text == "2026년 甲午 세운은 재물에서 강해요."
    assert not audit.fixes_discarded


def test_fix_discarded_when_protected_chars_change(monkeypatch):
    """보호 글자가 변하는 교정이 섞이면 교정 전체를 버리고 원문을 돌려준다(방어 경로)."""
    from saju_engines import ai_tell_audit as m
    from saju_engines.dictionaries import AiTellFix

    f = m.load_ai_tell_patterns()
    bad = f.model_copy(deep=True)
    bad.items[0].fix = [AiTellFix(pattern="甲", repl="乙")]
    bad.items[0].scopes = ["chat"]
    monkeypatch.setattr(m, "load_ai_tell_patterns", lambda path=None: bad)
    fixed, fixes, discarded = m.apply_safe_fixes("甲午년 좋아요.", "chat")
    assert fixed == "甲午년 좋아요." and fixes == [] and discarded is True


def test_empty_and_plain_text_untouched():
    """빈 문자열·평범한 풀이 문장은 교정·탐지 모두 없다."""
    assert audit_ai_tells("", "chat").text == ""
    plain = "올해는 밀린 일을 정리하기에 나은 해예요. 큰 결정은 가을까지 미루는 편이 좋겠어요."
    a = audit_ai_tells(plain, "chat")
    assert a.text == plain and a.fixes == [] and a.findings == []


# ── 탐지(임계·반례) ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "pid, text",
    [
        ("A-7", "강한 경쟁력을 가지고 있어요."),
        ("D-2", "이 흐름은 시사하는 바가 커요."),
        ("D-3", "크게 세 가지로 나눌 수 있어요."),
        ("D-8", "중요한 것은 타이밍이에요."),
        ("D-12", "다만 과제도 남아 있어요."),
        ("D-14", "건강에 적신호가 켜져요."),
        ("G-2", "좋아질 가능성이 있을 수 있어요."),
        ("I-2", "주목할 점은 관성의 위치예요."),
        ("A-21", "단순한 이직을 넘어 전환이에요."),
    ],
)
def test_single_hit_patterns(pid, text):
    """임계 1인 항목은 한 번만 나와도 잡는다."""
    assert pid in _ids(detect_ai_tells(text, "chat"))


def test_threshold_patterns_need_density():
    """임계가 있는 항목(C-8·A-1·C-11)은 밀집해야 잡히고, 한두 번은 사람 글로 보존한다."""
    one = "돈이 아니라 사람이에요. 관계에 대해 생각해 보세요. 쉬면서, 정리하세요."
    assert _ids(detect_ai_tells(one, "chat")).isdisjoint({"C-8", "A-1", "C-11"})
    dense = (
        "돈이 아니라 사람이에요. 속도가 아니라 방향이에요. "
        "일에 대해, 돈에 대해, 사람에 대해 고민해요. "
        "쉬면서, 정리하고, 다시 보지만, 서두르지 마세요."
    )
    assert {"C-8", "A-1", "C-11"} <= _ids(detect_ai_tells(dense, "chat"))


def test_e2_same_ending_run():
    """E-2: 같은 종결 토큰이 4문장 이상 이어지면 잡고, 변주되면 잡지 않는다."""
    same = "흐름이 좋아요. 기회가 많아요. 연락이 잦아요. 부담이 작아요."
    assert "E-2" in _ids(detect_ai_tells(same, "chat"))
    varied = "흐름이 좋아요. 기회가 많습니다. 연락이 잦죠. 결정이 빨라요."
    assert "E-2" not in _ids(detect_ai_tells(varied, "chat"))


def test_d11_tail_region_only():
    """D-11: '앞으로·향후'는 결말부(뒤 30%)에서만 본다."""
    head = (
        "앞으로 흐름을 볼게요. 봄은 준비예요. 여름은 실행이에요. 가을은 정리예요. "
        "겨울은 쉼이에요."
    )
    assert "D-11" not in _ids(detect_ai_tells(head, "chat"))
    tail = "봄은 준비예요. 여름은 실행이에요. 가을은 정리예요. 겨울은 쉼이에요. 앞으로 좋아져요."
    assert "D-11" in _ids(detect_ai_tells(tail, "chat"))


def test_daily_scope_excludes_report_only_items():
    """daily 범위에는 C-11·A-1 같은 긴 글 전용 항목이 없다."""
    text = "쉬면서, 정리하고, 다시 보지만, 서두르지 마세요. 일에 대해, 돈에 대해, 사람에 대해."
    assert _ids(detect_ai_tells(text, "daily")).isdisjoint({"C-11", "A-1"})


def test_s1_ids_for_daily_line_guard():
    """오늘의 운세 줄 검증용 — 원문에 없던 S1 이 새로 생기면 id 로 드러난다."""
    raw = "연락이 하나 와요. 미뤘던 답을 주세요."
    polished = "결론적으로 연락이 와요. 답을 가지고 있어요."
    assert s1_ids(polished, "daily") - s1_ids(raw, "daily") == {"A-7", "D-1a"}
    assert s1_ids(raw, "daily") == set()


# ── 배선 ────────────────────────────────────────────────────────────────


def test_system_prompts_carry_style_block_after_rules():
    """채팅·리포트 시스템 프롬프트는 규칙 리터럴 뒤에 문체 블록을 싣는다(규칙 8 앵커 불변)."""
    from saju_api.services import llm_client

    for sp in (llm_client._SYSTEM_PROMPT, llm_client._REPORT_SYSTEM_PROMPT):
        assert "[문체 — 한글 AI 티 제거]" in sp
        assert sp.index("응답은 한국어로") < sp.index("[문체 — 한글 AI 티 제거]")
    assert "답변 끝에 핵심을 한두 문장으로 정리" in llm_client._SYSTEM_PROMPT


def test_chat_finalize_applies_fix():
    """채팅 후처리 공용 경로가 자동 교정을 반영한다."""
    from saju_api.services.chat_service import finalize_answer_text

    out = finalize_answer_text("결론적으로, 재물에 있어서 甲午년이 좋아요.")
    assert out == "재물에서 甲午(갑오)년이 좋아요." or out == "재물에서 甲午년이 좋아요."


def test_report_section_audit_applies_fix():
    """리포트 섹션 감사 끝에서 자동 교정이 반영된다(정책 없는 섹션도)."""
    from saju_api.services.report_service import _audit_section_text

    out = _audit_section_text("F-99", "정리하자면 관계가 형성되어집니다.")
    assert out == "관계가 형성됩니다."


def test_daily_reject_on_new_s1_tell():
    """오늘의 운세 교정 줄에 원문에 없던 S1 상투구가 생기면 그 줄을 폐기한다."""
    from saju_api.services.daily_fortune_polish import _reject_reason

    assert _reject_reason("결론적으로 연락이 와요.", "연락이 와요.", 200) == "ai_tell:D-1a"
    assert _reject_reason("연락이 하나 와요.", "연락이 와요.", 200) is None
    # 원문에 이미 있던 표현은 폐기 사유가 아니다(원문 유지 정책과 동일).
    assert _reject_reason("재물에 있어 좋아요.", "재물에 있어 좋아요.", 200) is None
