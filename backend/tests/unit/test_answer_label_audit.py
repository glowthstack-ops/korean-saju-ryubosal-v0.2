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


def test_entry_window_labels_present_first_paragraph_only() -> None:
    present = entry_window_labels_present
    assert present("성사 달은 2월, 움직이는 달은 1월이에요.\n\n본문") == (True, True)
    assert present("2월이 유력해요.\n\n움직이는 달은 1월, 성사 달은 2월.") == (False, False)
    assert entry_window_labels_present("") == (False, False)


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
