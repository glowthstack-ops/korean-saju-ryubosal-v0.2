"""반사실 컨텍스트 레이어 회귀 — fail-closed 상태 기계·체리피킹 차단·보호 서사 게이트.

GPT 검토안(2026-07-21 데굴님 승인) §8 사례 고정: 기간·도메인 확정 + 활성화 성립 시만
ELIGIBLE, 현재 미발생/기간 미확정은 INSUFFICIENT(자동 보호 서사 금지), 근거 불일치는
BLOCKED, 회복 증거 없으면 보호 해석 금지. 점수·판정 불변(narrative_only).
"""

from __future__ import annotations

from datetime import date

from saju_api.services.manse_service import calculate
from saju_engines.counterfactual_context import (
    build_counterfactual_context,
    counterfactual_lines,
    detect_counterfactual_mode,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventKey
from saju_shared_types.intent import (
    Domain,
    Granularity,
    IntentJson,
    QueryType,
    TimeRange,
)

_TODAY = date(2026, 7, 21)


def _result():
    return calculate(BirthInput(
        calendar_type="solar", birth_date="1980-11-22", birth_time="09:00",
        birth_place_name="서울", gender="male",
        time_options={"apply_true_solar_time": False},
    ))


def _intent(
    domain: Domain = Domain.RELATIONSHIP,
    event: EventKey | None = EventKey.MARRIAGE_SIGNAL,
    year: str | None = None,
) -> IntentJson:
    tr = (
        TimeRange(type="absolute", granularity=Granularity.YEAR,
                  start=f"{year}-01-01", end=f"{year}-12-31")
        if year else None
    )
    return IntentJson(
        intent_id="t", query_type=QueryType.DOMAIN_ANALYSIS, domain=domain,
        event_key=event, time_range=tr,
    )


# ── 모드 감지 ────────────────────────────────────────────────────────────────


def test_mode_detection_variants() -> None:
    assert detect_counterfactual_mode("2021년에 결혼했으면 어땠을까?") == "counterfactual_explicit"
    assert detect_counterfactual_mode("그때 결혼했으면 이혼했겠지?") == "counterfactual_explicit"
    assert detect_counterfactual_mode("왜 취업이 안 됐지?") == "retrospective_causal"
    assert detect_counterfactual_mode("왜 계약이 늦었지?") == "counterfactual_implicit"
    assert detect_counterfactual_mode("나는 왜 늦게 결혼할 운이야?") == "current_non_occurrence"
    # 미래 가정('한다면')은 반사실 아님 — 기존 conditional 경로 유지.
    assert detect_counterfactual_mode("내년에 이직한다면 어떨까?") == ""
    assert detect_counterfactual_mode("올해 이직운 어때?") == ""


# ── fail-closed 상태 기계 ────────────────────────────────────────────────────


def test_non_saju_question_not_applicable() -> None:
    # '왜 결제가 안 됐지' — 도메인·이벤트 불명 → NOT_APPLICABLE, 무언급.
    ctx = build_counterfactual_context(
        "왜 결제가 안 됐지?", _intent(Domain.GENERAL, None), _result(), _TODAY,
    )
    assert ctx.status == "NOT_APPLICABLE"
    assert counterfactual_lines(ctx) == []


def test_current_non_occurrence_blocks_auto_protection() -> None:
    # '왜 늦게 결혼할 운이야' — 기간 미확정: 정적 구조까지만, 자동 보호 서사 금지.
    ctx = build_counterfactual_context(
        "나는 왜 늦게 결혼할 운이야?", _intent(), _result(), _TODAY,
    )
    assert ctx.status == "INSUFFICIENT"
    assert ctx.allowed_claim_level == "structure_only"
    assert ctx.burden_signals  # 배우자궁 사해충·해해자형 등 정적 구조는 제공
    text = "\n".join(counterfactual_lines(ctx))
    assert "안 하길 잘했다" in text and "만들지 말 것" in text
    assert "단정할 근거는 제공되지 않았다" in text


def test_explicit_with_activated_year_is_burden_only() -> None:
    # 2025 乙巳 — 운 巳가 원국 일지 亥를 충(사해충) → 구조+활성 동시 성립.
    # 이후 창(2026)이 2년 미만이라 회복 비교 불가 → 보호 해석 금지.
    ctx = build_counterfactual_context(
        "2025년에 결혼했으면 어땠을까?", _intent(year="2025"), _result(), _TODAY,
    )
    assert ctx.status == "ELIGIBLE_BURDEN_ONLY"
    assert ctx.period_from == "2025" and ctx.period_source == "user_stated"
    assert any(s.signal_id.startswith("YEAR_충_ACTIVATED") for s in ctx.burden_signals)
    assert all(s.stage in ("initiation", "stabilization", "maintenance", "fruition")
               for s in ctx.burden_signals)
    text = "\n".join(counterfactual_lines(ctx))
    assert "보호 해석 금지" in text
    assert "실패 단정 금지" in text
    assert "이혼·파산" in text  # 파국 생성 금지 가드 동반


def test_explicit_without_activation_is_blocked() -> None:
    # 2021 辛丑 — 이 명식 배우자궁(亥)을 자극하는 충·형 활성 없음 → BLOCKED(단정 금지).
    ctx = build_counterfactual_context(
        "2021년에 결혼했으면 어땠을까?", _intent(year="2021"), _result(), _TODAY,
    )
    assert ctx.status == "BLOCKED"
    text = "\n".join(counterfactual_lines(ctx))
    assert "양쪽 모두 단정하지 말고" in text


def test_catastrophe_leading_question_keeps_burden_level() -> None:
    # '이혼했겠지?' 유도 질문 — 동조 금지: 부담 수준으로만, 파국 생성 금지 가드 포함.
    ctx = build_counterfactual_context(
        "2025년에 결혼했으면 이혼했겠지?", _intent(year="2025"), _result(), _TODAY,
    )
    assert ctx.status in ("ELIGIBLE_BURDEN_ONLY", "ELIGIBLE_PROTECTIVE")
    text = "\n".join(counterfactual_lines(ctx))
    assert "이혼·파산·해고·질병 등 구체 파국 사건 생성" in text


def test_health_domain_excluded() -> None:
    ctx = build_counterfactual_context(
        "2024년에 수술했으면 어땠을까?", _intent(Domain.HEALTH, None, year="2024"),
        _result(), _TODAY,
    )
    assert ctx.status == "NOT_APPLICABLE"


def test_thread_scope_fallback_used_as_period() -> None:
    # 질문에 시점이 없어도 직전 대화 확정 기간(과거)이 있으면 승계.
    ctx = build_counterfactual_context(
        "그때 결혼했으면 어땠을까?", _intent(), _result(), _TODAY,
        prior_time_scope="2025",
    )
    assert ctx.period_from == "2025" and ctx.period_source == "thread_inherited"


def test_resolver_never_mutates_result() -> None:
    r = _result()
    assert r.luck_cycles is not None
    before = r.model_dump()
    build_counterfactual_context("2025년에 결혼했으면 어땠을까?", _intent(year="2025"), r, _TODAY)
    assert r.model_dump() == before


def test_context_is_narrative_only() -> None:
    ctx = build_counterfactual_context(
        "2025년에 결혼했으면 어땠을까?", _intent(year="2025"), _result(), _TODAY,
    )
    assert ctx.usage == "narrative_only"
