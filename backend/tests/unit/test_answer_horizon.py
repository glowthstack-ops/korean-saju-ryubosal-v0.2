"""답변 시간 지평(Horizon) 정책 — 질문 유형별 서술 범위 회귀 (2026-07-09 데굴님 지시).

기준 예시 4종: ① 급전(즉시형)=3개월 ② 부업 전망(전망형)=6개월+5년 ③ 사업 시작
④ 퇴사(구조 결정형)=원국+현재 대운+5년+당장 3개월. 명시적 장기 질문만 10년 digest 유지.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

import saju_api.services.chat_service as chat_service
from saju_engines.horizon import month_add, resolve_horizon
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import IntentJson

_TODAY = date(2026, 7, 9)
_BIRTH = BirthInput(
    calendar_type="solar",
    birth_date="1980-11-22",
    birth_time="09:08",
    birth_place_name="서울",
    gender="male",
    reference_date="2026-07-09",
)

Q_IMMEDIATE = "지금 돈이 좀 필요한데 돈이 생길 여지가 있을까?"
Q_VENTURE = "현재 개발중인 사이드프로젝트로 부업을 해볼까 하는데 성공할 수 있을까?"
Q_BUSINESS = "아예 사업을 시작해보는 건 어떨까?"
Q_QUIT = "그럼 지금 회사는 그만두면 안돼?"


def _intent(**over) -> IntentJson:
    return IntentJson.model_validate(
        {"intent_id": "t-horizon", "query_type": "domain_analysis", **over}
    )


# ── 정책 산출 (단위) ─────────────────────────────────────────────────────


def test_resolve_kinds_for_exemplar_questions() -> None:
    """기준 예시 4종의 유형 감지 — 우선순위(구조>즉시>전망)."""
    it = _intent()
    assert resolve_horizon(Q_IMMEDIATE, it).kind == "immediate"
    assert resolve_horizon(Q_VENTURE, it).kind == "venture"
    assert resolve_horizon(Q_BUSINESS, it).kind == "structural"
    assert resolve_horizon(Q_QUIT, it).kind == "structural"


def test_resolve_long_term_returns_none() -> None:
    """명시적 장기 질문(대운·인생 흐름)은 정책 밖 — 기존 10년 digest 유지."""
    assert resolve_horizon("내 대운 흐름이 궁금해", _intent()) is None
    assert resolve_horizon("장기적으로 인생 흐름이 어떻게 될까", _intent()) is None


def test_resolve_domain_default_consumes_rewriter_dict() -> None:
    """무시점 분야 질문 — docs/03 B3의 분야 기본 기간(dead code였던 사전) 소비."""
    p = resolve_horizon("재물운이 궁금해요", _intent(domain="wealth"))
    assert p is not None and p.kind == "domain_default" and p.months_detail == 12
    g = resolve_horizon("운세가 궁금해요", _intent(domain="general"))
    assert g is not None and g.months_detail == 3


def test_month_add() -> None:
    """월 라벨 덧셈 — 연 경계 이월."""
    assert month_add("2026-07", 3) == "2026-10"
    assert month_add("2026-11", 3) == "2027-02"


# ── e2e (dry-run 프롬프트) ───────────────────────────────────────────────


def _prompt(question: str) -> str:
    res = chat_service.chat(_BIRTH, question, _TODAY, dry_run=True)
    assert res.prompt_preview is not None
    return res.prompt_preview


def _overview_labels(text: str) -> list[str]:
    """운 흐름/월별/연도별 표의 행 라벨(YYYY 또는 YYYY-MM)."""
    return re.findall(r"^(20\d\d(?:-\d\d)?) [甲乙丙丁戊己庚辛壬癸]", text, re.M)


def test_immediate_three_months_only() -> None:
    """즉시형 — 3개월 월 단위만, 연 단위·대운 배경·10년 digest 없음."""
    text = _prompt(Q_IMMEDIATE)
    labels = _overview_labels(text)
    assert labels == ["2026-07", "2026-08", "2026-09"]
    assert "[답변 지평]" in text and "향후 3개월" in text
    assert "[대운 배경" not in text
    assert "약 10년의 흐름" not in text  # 10년 digest 지시 미부착


def test_venture_six_months_plus_five_years() -> None:
    """전망형 — 앞 6개월 월 단위 + 5년 연 단위 + 대운 배경(5년)."""
    text = _prompt(Q_VENTURE)
    labels = _overview_labels(text)
    months = [x for x in labels if len(x) == 7]
    years = [x for x in labels if len(x) == 4]
    assert months == [f"2026-{m:02d}" for m in range(7, 13)]
    assert years == [str(y) for y in range(2026, 2031)]
    assert "[대운 배경 — 5년 흐름]" in text
    assert "[답변 지평]" in text and "6개월" in text


@pytest.mark.parametrize("question", [Q_BUSINESS, Q_QUIT])
def test_structural_natal_daewoon_five_years(question: str) -> None:
    """구조 결정형 — 원국 적합성 우선 지시 + 현재 대운 배경 + 5년 연 단위 + 3개월."""
    text = _prompt(question)
    labels = _overview_labels(text)
    months = [x for x in labels if len(x) == 7]
    years = [x for x in labels if len(x) == 4]
    assert months == ["2026-07", "2026-08", "2026-09"]
    assert years == [str(y) for y in range(2026, 2031)]
    assert "원국 기준 적합성" in text  # natal_fit 구성 지시
    assert "[대운 배경 — 5년 흐름]" in text
    # 지평 밖(2031+) 연 단위 행이 표에 없어야 한다.
    assert not any(y in years for y in ("2031", "2033", "2034", "2035"))


def test_horizon_directive_allows_one_line_notice() -> None:
    """지평 밖 서술 금지 + '더 긴 흐름은 이어서 물어보라' 한 줄 안내만 허용."""
    text = _prompt(Q_QUIT)
    assert "이 지평 밖 기간은 본문에서 서술하지 말 것" in text
    assert "한 줄 안내만 허용" in text


def test_long_term_question_keeps_ten_year_digest() -> None:
    """명시적 장기 질문(노후 등)은 기존 10년 연 단위 digest 유지(정책 미적용)."""
    text = _prompt("노후 운세가 궁금해")
    assert "[답변 지평]" not in text
    assert "약 10년의 흐름" in text
