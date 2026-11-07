"""리포트 문체·회고 어미·월 단위 감사(2026-11-07 데굴님 "제안대로 진행 + 문체 통일").

실답(구 F-10 '지금의 대운 자세히')에서 ①대운 페이지가 월운 사건을 나열 ②다른 대운 연도 인용
③과거 회고가 사실 단정 어미("있었네요") ④페이지마다 '~다/~요' 혼용이 보였다. 재호출 없는 결정론
교정과 지시문으로 막는다.
"""

from __future__ import annotations

from saju_api.services.report_service import _DECADE_PAGE_GUIDE, apply_report_style_audits
from saju_engines.report_style_audit import (
    hedge_retrospective,
    strip_month_detail,
    unify_haeyo,
)

# ── 해요체 통일 ───────────────────────────────────────────────────────────────


def test_unify_haeyo_converts_plain_and_formal_endings() -> None:
    cases = {
        "이 시기는 전환점이다.": "이 시기는 전환점이에요.",
        "흐름이 좋다.": "흐름이 좋아요.",
        "기회가 많다.": "기회가 많아요.",
        "변화가 온다.": "변화가 와요.",
        "결과를 본다.": "결과를 봐요.",
        "준비를 한다.": "준비를 해요.",
        "문서가 된다.": "문서가 돼요.",
        "여유가 있다.": "여유가 있어요.",
        "부담이 없다.": "부담이 없어요.",
        "쉽지 않다.": "쉽지 않아요.",
        "압박이 컸다.": "압박이 컸어요.",
        "제안이 들어왔다.": "제안이 들어와요.".replace("와요", "왔어요"),
        "기회가 열린다.": "기회가 열려요.",
        "변화의 시기입니다.": "변화의 시기예요.",
        "좋은 흐름입니다.": "좋은 흐름이에요.",
        "준비가 필요합니다.": "준비가 필요해요.",
        "기회가 있습니다.": "기회가 있어요.",
        "부담이 큽니다.": "부담이 커요.",
        "결과가 좋습니다.": "결과가 좋아요.",
        "이직이 거론될 수 있다!": "이직이 거론될 수 있어요!",
        "적극적으로 움직여 보십시오.": "적극적으로 움직여 보세요.",
        "변화가 생긴다.": "변화가 생겨요.",
    }
    for src, want in cases.items():
        got = unify_haeyo(src)
        assert got.text == want, (src, got.text)
        assert got.fixes and not got.unresolved


def test_unify_haeyo_leaves_haeyo_and_non_final_forms_alone() -> None:
    src = "이 흐름은 좋아요. 다만 '정재가 들어온다'는 뜻이다는 식으로 읽히죠? 2027년 丁未 운이에요."
    got = unify_haeyo(src)
    assert "좋아요." in got.text and "읽히죠?" in got.text and "丁未 운이에요." in got.text
    assert "들어온다'는" in got.text  # 비종결('~다'는) 불변
    # 간지·연도 불변.
    assert "2027년 丁未" in got.text


def test_unify_haeyo_logs_irregular_stems_instead_of_guessing() -> None:
    for src in ("길이 가깝다.", "소식을 듣는다.", "그렇습니다.", "그 분야를 모른다.", "집을 산다."):
        got = unify_haeyo(src)
        assert got.text == src and got.unresolved and not got.fixes, src


# ── 과거 대운 회고 어미 ───────────────────────────────────────────────────────


def test_hedge_retrospective_turns_past_assertions_into_confirmation_prompts() -> None:
    src = (
        "상사의 지적이 유난히 거슬리는 기류가 있었네요. 마음이 흔들렸어요. "
        "큰 풍파로 이어지기보다는 내면의 갈등을 다스리며 지나왔을 것으로 보여요. "
        "그때 많이 힘드셨죠? 채용 제안이 들어오는 시기였다."
    )
    out, fixes = hedge_retrospective(src)
    assert "기류가 있었을 수 있어요." in out
    assert "마음이 흔들렸을 수 있어요." in out
    assert "지나왔을 것으로 보여요." in out  # 이미 가능성형
    assert "힘드셨죠?" in out  # 확인 유도형 보존
    assert "시기였을 수 있어요." in out
    assert len(fixes) == 3


def test_hedge_retrospective_keeps_paragraph_breaks_and_future_forms() -> None:
    src = "첫 문단이 있었어요.\n\n둘째 문단은 기회가 올 수 있어요. 준비해 두면 좋아요."
    out, fixes = hedge_retrospective(src)
    assert out == (
        "첫 문단이 있었을 수 있어요.\n\n둘째 문단은 기회가 올 수 있어요. 준비해 두면 좋아요."
    )
    assert len(fixes) == 1
    # 현재(있어요)·추측(겠어요)은 과거가 아니다.
    same = "주목할 필요가 있어요. 준비하겠어요."
    assert hedge_retrospective(same) == (same, [])


# ── 월 단위 제거 ──────────────────────────────────────────────────────────────


def test_strip_month_detail_keeps_year_and_logs_bare_months() -> None:
    src = "2026년 8월 丙申월에 주목하세요. 2027년 1월에는 이동수가 걸려요. 5월에는 압박이 와요."
    out, stripped, bare = strip_month_detail(src)
    assert out.startswith("2026년 丙申월에") and "2027년에는" in out
    assert stripped == ["2026년 8월", "2027년 1월"]
    assert bare == ["5월"]
    assert "2026년" in out and "2027년" in out  # 연도(입력값) 보존


# ── 배선·지시문 ──────────────────────────────────────────────────────────────


def test_apply_report_style_audits_orders_and_scopes() -> None:
    src = "2022년 3월 압박이 컸다. 변화가 올 수 있다."
    # 일반 섹션(해요체) — 문체만.
    assert apply_report_style_audits(
        "F-07", src, style="haeyo", decade_page=False, past_decade_page=False,
    ) == "2022년 3월 압박이 컸어요. 변화가 올 수 있어요."
    # 지난 대운 페이지 — 문체 → 월 제거 → 회고 어미.
    assert apply_report_style_audits(
        "F-14-D1", src, style="haeyo", decade_page=True, past_decade_page=True,
    ) == "2022년 압박이 컸을 수 있어요. 변화가 올 수 있어요."
    # 예정 대운 페이지 — 회고 어미는 건드리지 않는다.
    assert apply_report_style_audits(
        "F-14-D9", "큰 변화가 왔다.", style="haeyo", decade_page=True, past_decade_page=False,
    ) == "큰 변화가 왔어요."
    # 다른 말투 페르소나 — 문체 불변.
    assert apply_report_style_audits(
        "F-07", "흐름이 좋다.", style="hapsyo", decade_page=False, past_decade_page=False,
    ) == "흐름이 좋다."


def test_decade_guide_forbids_month_detail() -> None:
    assert "달(월) 단위로 내려가지 말 것" in _DECADE_PAGE_GUIDE
