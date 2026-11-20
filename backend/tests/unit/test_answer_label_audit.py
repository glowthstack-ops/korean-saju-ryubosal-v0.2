"""답변 내부 표기 교정·두 칸 관측·일주 참조 문장 제거.

SSOT: EMPLOYMENT_HISTORY_CALIBRATION.md §4-2 (2026-10-22).

실답(thread web-mvjij2wx) 누수 '1위로 나타나지만'·'2026-12 庚子월'과, 시기 질문에서 참조 예외로
살아남던 일주 소개 두 문장을 반례로 고정한다. 순수 함수.
"""

from __future__ import annotations

from saju_engines.answer_label_audit import (
    entry_window_labels_present,
    rewrite_rank_labels,
    rewrite_raw_period_labels,
)
from saju_engines.ilju_mention_audit import audit_ilju_mention, strips_referent
from saju_shared_types.intent import Domain, QueryType


def test_rank_labels_rewritten_by_particle() -> None:
    text = "최종 합격이나 승인 같은 성취 신호가 1위로 나타나지만, 2위인 달은 12월이다. 3위는 1월."
    out, changes = rewrite_rank_labels(text)
    assert "가장 강하게 나타나지만" in out and "두 번째로 강한 달" in out
    assert "세 번째로 강한 신호는 1월" in out
    assert len(changes) == 3 and "위" not in out.replace("위로", "")[:0]
    # 숫자 맥락·4위 이상은 건드리지 않는다.
    assert rewrite_rank_labels("10위권, 2·3위 다툼, 4위") == ("10위권, 2·3위 다툼, 4위", [])


def test_raw_period_labels_rewritten_but_dates_and_ranges_kept() -> None:
    text = ("2026-12 庚子(경자)월은 변화가 크다. 2026-10-22 기준, 창은 2026-10~2027-09다. "
            "2027-01도 본다.")
    out, changes = rewrite_raw_period_labels(text)
    assert out.startswith("2026년 12월 庚子")
    assert "2026-10-22" in out and "2026-10~2027-09" in out
    assert "2027년 1월도" in out
    assert [c[0] for c in changes] == ["2026-12", "2027-01"]


def test_raw_period_label_with_month_suffix_and_zero_padded_month() -> None:
    """실답(web-mvjm3vcc): '2026-11월' → '2026년 11월월', '05월' 그대로 — 둘 다 교정."""
    text = "2026-11월에는 비견이 들어오고, 2027년 2월월과 05월은 성사 달이다. 2026-10-05에 본다."
    out, changes = rewrite_raw_period_labels(text)
    assert out == ("2026년 11월에는 비견이 들어오고, 2027년 2월과 5월은 성사 달이다. "
                   "2026-10-05에 본다.")
    assert ("2026-11월", "2026년 11월") in changes and ("월월", "월") in changes
    assert "월월" not in out


def test_relative_year_mentions_log_only() -> None:
    from saju_engines.answer_label_audit import relative_year_mentions

    words = relative_year_mentions("내년 하반기부터 준비해 내후년 상반기에 결론")
    assert words == ["내년", "내후년"]
    assert relative_year_mentions("2027년 2월이 성사 달이에요.") == []


def test_entry_window_labels_present_first_paragraph_only() -> None:
    # 2026-11-20: 달 칸 어간 = '유력한 달·가능성 있는 달·흐름이 보이는 달'(엔진 배정 지시문의
    # 새 틀).
    present = entry_window_labels_present
    both = "유력한 달을 찾아보니 2월이에요. 움직이는 달은 1월이에요.\n\n본문"
    assert present(both) == (True, True)
    # 어간 기준 — "가능성 있는 달 … 미리 움직이며"도 의미상 두 칸으로 센다.
    semantic = "가능성 있는 달은 2월이며, 11월부터 미리 움직이며 조건을 확인하세요.\n\n본문"
    assert present(semantic) == (True, True)
    assert present("흐름이 보이는 달은 11월이에요.\n\n본문") == (True, False)
    # 첫 문단만 본다 — 표지가 둘째 문단에 있으면 세지 않는다.
    assert present("2월을 보세요.\n\n유력한 달은 2월, 움직이는 달은 1월.") == (False, False)
    # 반례(실답 web-mwobgi4o): 부재 선언의 '성사'는 달 칸 표지가 아니다 — 종전에는 통과로 셌다.
    absent = "성사가 확정되는 달은 보이지 않지만, 움직이는 달은 분명히 존재합니다.\n\n본문"
    assert present(absent) == (False, True)
    assert entry_window_labels_present("") == (False, False)


def test_absence_declarations_catch_no_month_sentences_only() -> None:
    """부재 선언 감사(2026-11-20) — '달이 없다' 문장만 잡고, 달을 말한 문장은 놓아둔다."""
    from saju_engines.answer_label_audit import absence_declarations

    for bad in (
        "앞으로 12개월 동안 취직과 관련해 성사가 확정되는 달은 보이지 않지만, 움직이는 달은 "
        "있습니다.",
        "다만 질문하신 12개월 안에는 최종 성사 기준을 충족하는 달이 없고, 단계적으로 나아갑니다.",
        "이 창 안에는 성사 가능 달이 없습니다.",
        "유력한 달은 없지만 준비는 가능합니다.",
        "신호가 성사 기준에 못 미칩니다.",
    ):
        assert absence_declarations(bad), bad
    for good in (
        "유력한 달을 찾아보니 2027년 2월이며 큰 부담은 없습니다.",
        "성사를 단정할 수는 없지만 유력한 달은 2월입니다.",
        "이 달은 지출 부담이 없습니다.",
        "2027년 2월이 가장 유력하고 3월은 약하지만 가능성 있는 달입니다.",
        "",
    ):
        assert absence_declarations(good) == [], good
    # 여러 문장 가운데 해당 문장만 돌려준다.
    mixed = "유력한 달은 2월입니다. 그 밖에 성사 달은 없습니다. 준비를 이어가세요."
    assert absence_declarations(mixed) == ["그 밖에 성사 달은 없습니다."]


def test_ilju_intro_and_referent_removed_for_timing_but_kept_for_domain() -> None:
    answer = (
        "2027년 상반기가 유리해요.\n\n"
        "데굴님의 己亥(기해) 일주는 겉으로는 다정하고 내면에는 냉철한 판단력을 품은 구조입니다. "
        "이러한 기질은 조직 내에서 안정감을 줍니다. 현재 대운인 壬辰은 기반을 만들어 줍니다.\n\n"
        "11월은 검토의 달이에요."
    )
    assert strips_referent(QueryType.TIMING_SEARCH)
    assert not strips_referent(QueryType.DOMAIN_ANALYSIS)
    timing = audit_ilju_mention(answer, QueryType.TIMING_SEARCH, Domain.CAREER)
    assert len(timing.removed) == 1 and len(timing.removed_referents) == 1
    assert "일주" not in timing.text and "이러한 기질" not in timing.text
    assert "현재 대운인 壬辰은 기반을 만들어 줍니다." in timing.text
    assert "11월은 검토의 달이에요." in timing.text
    # 분야 개요는 기존 참조 예외 유지(로그만).
    dom = audit_ilju_mention(answer, QueryType.DOMAIN_ANALYSIS, Domain.CAREER)
    assert dom.removed == [] and len(dom.kept_referenced) == 1 and dom.text == answer
