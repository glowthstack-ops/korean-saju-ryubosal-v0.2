"""공망×합 확정 의미론(2026-08-21, 三命通會 '合則不能空') — 방향 오역 회귀 방지.

발단 사례: 공망 辰巳 명식의 丙申월 — 申은 공망지 巳의 육합 파트너인데 엔진이
'해소(합)'를 지연 게이트로 뒤집어 "공망과 겹쳐 공허·지연"으로 서술됐다.
확정 규칙: 지연·감점은 충발에만 / 전실=실체화·합=억제 완화(신호만) /
살아난 대상의 길흉은 별도 판정 / 검토월 근거는 충발뿐.
"""

from __future__ import annotations

from saju_engines.addendum_gate_modifier import AddendumGateModifier, GateContext
from saju_engines.context_reducer import _to_llm_candidate
from saju_engines.event_engine_v2 import to_legacy_candidate
from saju_engines.llm_event_serializer import reason_codes_ko
from saju_engines.structural_context import GONGMANG_ACTIVATION_DIRECTIVE
from saju_shared_types.event_engine import EventCandidateV2, EventKeyV2, EventTiming
from saju_shared_types.events import Confidence, EventCandidate, EventPolarity, EventType, Signal


def _cand(score: int = 60) -> EventCandidateV2:
    return EventCandidateV2(
        event_key=EventKeyV2.CONTRACT_DOCUMENT, period="2026-08", score=score,
    )


# ── 게이트 — 지연은 충발에만 ────────────────────────────────────────────────


def test_combine_release_no_delay_no_penalty() -> None:
    out = AddendumGateModifier().apply(
        [_cand(60)], GateContext(void_active=True, void_kinds={"combine"})
    )
    c = out[0]
    assert c.score == 60  # 감점 없음 — '해소'는 억제가 풀리는 방향
    assert c.timing is EventTiming.ACTIVE
    assert "VOID_COMBINE_RELEASE" in c.reason_codes
    assert "VOID_delay" not in c.reason_codes


def test_fill_no_delay() -> None:
    out = AddendumGateModifier().apply(
        [_cand(60)], GateContext(void_active=True, void_kinds={"fill"})
    )
    c = out[0]
    assert c.score == 60
    assert c.timing is EventTiming.ACTIVE
    assert "VOID_FILL" in c.reason_codes


def test_clash_keeps_delay_invariant() -> None:
    # 충발 = 발현 지연 + 변동성 보조(2026-07-22 확정 불변식) — 그대로 유지.
    out = AddendumGateModifier().apply(
        [_cand(60)], GateContext(void_active=True, void_kinds={"clash", "combine"})
    )
    c = out[0]
    assert c.score < 60
    assert c.timing is EventTiming.DELAY
    assert "VOID_delay" in c.reason_codes
    assert "VOID_COMBINE_RELEASE" in c.reason_codes  # 서브타입 공존 보존


def test_legacy_bool_only_keeps_old_behavior() -> None:
    # 구 호출자(void_kinds 미지정) — 기존 동작(충발 취급) 유지(하위 호환).
    out = AddendumGateModifier().apply([_cand(60)], GateContext(void_active=True))
    assert out[0].timing is EventTiming.DELAY


# ── 신호 라벨 — 서브타입 분리 ───────────────────────────────────────────────


def test_legacy_signals_subtype_labels() -> None:
    combine = to_legacy_candidate(
        _cand().model_copy(update={"reason_codes": ["VOID_COMBINE_RELEASE"]})
    )
    effects = [s.effect for s in combine.signals]
    assert any("공망 해소·접촉" in e for e in effects)
    assert not any("공망 지연" in e for e in effects)
    clash = to_legacy_candidate(
        _cand().model_copy(update={"reason_codes": ["VOID_delay"]})
    )
    assert any("공망 지연" in s.effect for s in clash.signals)


def test_pair_suffix_carried_to_signal_label() -> None:
    # 글자 쌍·궁위 보존 — 없으면 LLM이 공망지를 다른 지지로 오지목한다(亥 오지목 실측).
    out = AddendumGateModifier().apply(
        [_cand(60)],
        GateContext(
            void_active=True, void_kinds={"combine"},
            void_pairs={"combine": "申-巳(시지)"},
        ),
    )
    legacy = to_legacy_candidate(out[0])
    effects = [s.effect for s in legacy.signals]
    assert any("운 申이 공망지 巳(시지)와 합" in e for e in effects)


def test_reason_codes_ko_subtypes() -> None:
    assert reason_codes_ko(["VOID_COMBINE_RELEASE"]) == ["공망 해소·접촉(합 — 억제 완화)"]
    assert reason_codes_ko(["VOID_FILL"]) == ["공망 전실(실체화)"]
    assert reason_codes_ko(["VOID_delay"]) == ["공망 지연"]


# ── 검토월 — 충발만 근거 ────────────────────────────────────────────────────


def _legacy(effect: str) -> EventCandidate:
    return EventCandidate(
        event_key="contract_document", event_type=EventType.INSTANT, period="2026-08",
        score=60, confidence=Confidence.MEDIUM, polarity=EventPolarity.NEUTRAL,
        signals=[Signal(type="void", name="void", effect=effect, weight=0.0)],
    )


def test_review_month_only_from_clash() -> None:
    release = _to_llm_candidate(
        _legacy("공망 해소·접촉(합 — 억제 완화)"), ganji={}, dw_by_year={}
    )
    assert release.review_month is False  # '공망' 문자열 포함이어도 해소는 근거 아님
    clash = _to_llm_candidate(_legacy("공망 지연"), ganji={}, dw_by_year={})
    assert clash.review_month is True


# ── 프롬프트 계약 — 방향 오역 금지 ──────────────────────────────────────────


def test_directive_carries_canonical_semantics() -> None:
    t = GONGMANG_ACTIVATION_DIRECTIVE
    assert "合則不能空" in t
    assert "본래 작용이 현실화" in t
    assert "방향 오역" in t
    assert "공망'이라 부르지 말 것" in t
