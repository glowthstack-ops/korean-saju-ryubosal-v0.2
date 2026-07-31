"""대운 합화 체용 배경 — 현행(랭킹 반영)과 post_selection(서사 전용) 두 모드.

원래 이 파일은 `DAEWOON_HWA_BG_*` 가 candidate 의 `reason_codes` 에 실린다는 것을 고정하고
있었다. DW-HWA 감사에서 그 위치가 **잘못된 의미 계약**임이 드러났다 — 점수 기여가 없더라도
근거 목록을 읽는 guard·리포트·감사가 "이 사건의 발생을 대운이 지지했다" 로 오독한다.
분기는 `event_key` 가 아니라 `quality`(길/흉군)이므로 그런 뜻이 아니다.

그래서 문자열 값 계약은 보존하되 위치를 `DaewoonHwaBackground.evidence_code` 로 옮겼다.

    DAEWOON_HWA_EVIDENCE_CODE_VALUE_PRESERVED
    DAEWOON_HWA_OCCURRENCE_REASON_REMOVED
    DAEWOON_HWA_BACKGROUND_PROVENANCE_PRESERVED

기본 모드는 여전히 `'current'` 라 production 은 불변이다(PRODUCTION_FLAG_UNCHANGED).
"""

from __future__ import annotations

import pytest

from saju_engines.daewoon_background import (
    LEGACY_SCORE_COEFFICIENT,
    DaewoonHwaBackground,
    background_narrative_block,
    background_narrative_frame,
    derive_daewoon_hwa_background,
)
from saju_engines.event_engine_v2 import _apply_daewoon_hwa_background
from saju_shared_types.event_engine import (
    EventCandidateV2,
    EventQuality,
    PolarityRole,
)


def _c(quality: EventQuality) -> EventCandidateV2:
    return EventCandidateV2(event_key="wealth_change", period="2026", score=100, quality=quality)


# ── 현행 모드(기본) — production 불변 ─────────────────────────────────────


def test_pressure_daewoon_biases_bad_up_good_down() -> None:
    """압력 대운(기신 化) — 흉 사건 성패율↓(점수↑), 길 사건 완화(↓)."""
    bad = _apply_daewoon_hwa_background([_c(EventQuality.LOSS)], PolarityRole.GI)[0]
    good = _apply_daewoon_hwa_background([_c(EventQuality.OPPORTUNITY)], PolarityRole.GI)[0]
    assert bad.score == 103 and good.score == 97
    assert any("DAEWOON_HWA_BG_압력" in rc for rc in bad.reason_codes)


def test_boon_daewoon_biases_good_up_bad_down() -> None:
    """보강 대운(용신 化) — 길 사건↑, 흉 사건 완화(↓)."""
    good = _apply_daewoon_hwa_background([_c(EventQuality.ACHIEVEMENT)], PolarityRole.YONG)[0]
    bad = _apply_daewoon_hwa_background([_c(EventQuality.CONFLICT)], PolarityRole.YONG)[0]
    assert good.score == 103 and bad.score == 97
    assert any("DAEWOON_HWA_BG_보강" in rc for rc in good.reason_codes)


def test_none_or_neutral_unchanged() -> None:
    """대운 합화 없음/중립 → 무변경(사건 종류·점수 불변)."""
    c = _apply_daewoon_hwa_background([_c(EventQuality.LOSS)], None)[0]
    assert c.score == 100 and not any("DAEWOON_HWA" in rc for rc in c.reason_codes)


def test_quality_without_direction_unchanged() -> None:
    """방향 없는 품질(mixed 등)은 성패 보정 대상 아님."""
    c = _apply_daewoon_hwa_background([_c(EventQuality.MIXED)], PolarityRole.GI)[0]
    assert c.score == 100


def test_default_mode_is_current() -> None:
    """기본값이 바뀌면 production 이 조용히 달라진다."""
    assert _apply_daewoon_hwa_background(
        [_c(EventQuality.LOSS)], PolarityRole.GI
    )[0].score == 103


# ── post_selection 모드 — 점수·근거 불변 ──────────────────────────────────


@pytest.mark.parametrize("role", [PolarityRole.GI, PolarityRole.YONG, PolarityRole.HEE])
@pytest.mark.parametrize(
    "quality", [EventQuality.LOSS, EventQuality.OPPORTUNITY, EventQuality.MIXED]
)
def test_post_selection_touches_neither_score_nor_reasons(
    role: PolarityRole, quality: EventQuality
) -> None:
    """랭킹 영향 0 — 점수도 근거 코드도 바뀌지 않는다."""
    src = _c(quality)
    out = _apply_daewoon_hwa_background([src], role, mode="post_selection")[0]
    assert out.score == src.score
    assert out.reason_codes == src.reason_codes
    assert not any("DAEWOON_HWA" in rc for rc in out.reason_codes)
    assert "daewoon_hwa" not in out.contributions


def test_post_selection_preserves_canonical_quality() -> None:
    """canonical EventQuality 는 YongiQualityEngine 소관 — 배경이 바꾸지 않는다."""
    src = _c(EventQuality.LOSS)
    out = _apply_daewoon_hwa_background([src], PolarityRole.YONG, mode="post_selection")[0]
    assert out.quality is EventQuality.LOSS


# ── 배경 파생 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("role", "state", "code"),
    [
        (PolarityRole.YONG, "supportive", "DAEWOON_HWA_BG_보강"),
        (PolarityRole.HEE, "supportive", "DAEWOON_HWA_BG_보강"),
        (PolarityRole.GI, "pressuring", "DAEWOON_HWA_BG_압력"),
    ],
)
def test_evidence_code_value_preserved_at_new_location(
    role: PolarityRole, state: str, code: str
) -> None:
    """문자열 값은 그대로, 위치만 배경으로 옮긴다."""
    bg = derive_daewoon_hwa_background(role)
    assert bg.state == state
    assert bg.evidence_code == code
    assert bg.support_eligibility == "REVIEW_REQUIRED"
    assert bg.usage == "narrative_background_only"


def test_no_hwa_is_not_applicable() -> None:
    """합화 불성립 — 음성 대조에서 이 값이어야 한다."""
    bg = derive_daewoon_hwa_background(None)
    assert bg.state == "not_applicable"
    assert not bg.applicable
    assert bg.evidence_code is None


def test_neutral_role_has_no_direction() -> None:
    """중립은 방향이 없어 서사에 붙일 것이 없다."""
    bg = derive_daewoon_hwa_background(PolarityRole.NEUTRAL)
    assert bg.state == "neutral" and not bg.applicable


def test_legacy_coefficient_is_audit_metadata_not_intensity() -> None:
    """0.03 은 랭킹 계수였다 — 서사 강도로 재사용하지 않는다.

    강도·등급 필드를 두지 않는 것이 계약이다. 두면 검증된 적 없는 수치가 서사 강약을
    결정하게 된다.
    """
    bg = derive_daewoon_hwa_background(PolarityRole.GI)
    assert bg.legacy_score_coefficient == LEGACY_SCORE_COEFFICIENT
    assert not hasattr(bg, "strength")
    assert not hasattr(bg, "narrative_intensity")


# ── 서사 결합(렌더링 단계) ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("role", "quality", "fragment"),
    [
        (PolarityRole.YONG, EventQuality.OPPORTUNITY, "받쳐주는"),
        (PolarityRole.YONG, EventQuality.LOSS, "누그러뜨리는"),
        (PolarityRole.GI, EventQuality.ACHIEVEMENT, "제약을 더하는"),
        (PolarityRole.GI, EventQuality.LOSS, "체감 부담을 키우는"),
    ],
)
def test_four_combinations_render_distinct_frames(
    role: PolarityRole, quality: EventQuality, fragment: str
) -> None:
    """배경 × quality 4조합. 전부 '이미 선택된' 사건의 체감 서술이다."""
    frame = background_narrative_frame(derive_daewoon_hwa_background(role), quality)
    assert frame is not None
    assert fragment in frame
    assert "이미 선택된" in frame


def test_frame_absent_when_quality_has_no_direction() -> None:
    """방향 없는 품질에 억지로 프레임을 붙이면 근거 없는 체감 서술이 된다."""
    bg = derive_daewoon_hwa_background(PolarityRole.GI)
    assert background_narrative_frame(bg, EventQuality.MIXED) is None
    assert background_narrative_frame(bg, None) is None


def test_frame_absent_for_not_applicable() -> None:
    """합화가 없으면 붙일 배경도 없다."""
    assert background_narrative_frame(
        derive_daewoon_hwa_background(None), EventQuality.LOSS
    ) is None


# ── 반복 주입 방지 ───────────────────────────────────────────────────────


def _bg_map() -> dict[str, DaewoonHwaBackground]:
    return {
        "2027-03": derive_daewoon_hwa_background(PolarityRole.GI),
        "2028-06": derive_daewoon_hwa_background(PolarityRole.YONG),
        "2029-01": derive_daewoon_hwa_background(None),
    }


def test_same_period_described_once_within_a_call() -> None:
    """한 호출 안에서 같은 시점이 여러 대표로 나와도 한 번만 서술한다."""
    reps = [("2027-03", EventQuality.LOSS), ("2027-03", EventQuality.PRESSURE)]
    assert len(background_narrative_block(reps, _bg_map())) == 1


def test_request_scoped_dedup_suppresses_later_sections() -> None:
    """섹션이 바뀌어도 같은 (시점, 방향)은 요청 안에서 한 번만 상세 서술한다."""
    seen: set[tuple[str, str]] = set()
    reps = [("2027-03", EventQuality.LOSS)]
    first = background_narrative_block(reps, _bg_map(), already_described=seen)
    second = background_narrative_block(reps, _bg_map(), already_described=seen)
    assert len(first) == 1
    assert second == []


def test_not_applicable_period_yields_no_line() -> None:
    """합화 없는 시점에는 배경 문장이 붙지 않는다."""
    assert background_narrative_block([("2029-01", EventQuality.LOSS)], _bg_map()) == []


def test_unknown_period_is_skipped() -> None:
    """맵에 없는 시점은 조용히 건너뛴다 — 없는 배경을 지어내지 않는다."""
    assert background_narrative_block([("2099-12", EventQuality.LOSS)], _bg_map()) == []


# ── 요청 로컬 수집 계약 ──────────────────────────────────────────────────
#
# chat_service 의 scorer 는 모듈 싱글턴이고 워커 스레드는 재사용된다. 배경 맵은 (감사용
# risk_shadow 와 달리) 서사 렌더러가 실제로 읽을 값이라, 요청 경계가 새면 다른 사람의
# 대운 배경이 답변에 섞인다.


def _scorer(mode: str = "post_selection"):
    """사전 로드 없이 수집 계약만 시험할 최소 스코어러."""
    from pathlib import Path

    from saju_engines.event_engine_v2 import EventEngineV2

    dicts = Path(__file__).resolve().parents[2] / "dictionaries"
    return EventEngineV2(dicts, daewoon_hwa_mode=mode)


def _fill(scorer, periods: dict[str, PolarityRole | None]) -> None:
    """score() 가 하는 수집만 흉내낸다(만세 계산 없이 sink 계약만 본다)."""
    sink: dict[str, object] = {}
    scorer._dw_bg_tls.sink = sink
    try:
        for label, role in periods.items():
            sink[label] = derive_daewoon_hwa_background(role)
    finally:
        from types import MappingProxyType

        scorer._dw_bg_tls.sink = None
        scorer._dw_bg_tls.last = MappingProxyType(dict(sink))


def test_take_clears_the_store() -> None:
    """소비하면 비운다 — 남겨두면 조기 반환 요청이 직전 요청 배경을 본다.

    실측으로 재현했던 결함이다: 요청 A 채점 후 123건, score() 를 부르지 않은 다음
    take 에서도 같은 123건이 나왔다.
    """
    s = _scorer()
    _fill(s, {"2027-03": PolarityRole.GI})
    assert len(s.take_daewoon_hwa_backgrounds()) == 1
    assert len(s.take_daewoon_hwa_backgrounds()) == 0


def test_next_request_does_not_see_previous_values() -> None:
    """다음 요청은 이전 요청 값을 보지 않는다."""
    s = _scorer()
    _fill(s, {"2027-03": PolarityRole.GI})
    _fill(s, {"2029-01": None})
    got = s.take_daewoon_hwa_backgrounds()
    assert set(got) == {"2029-01"}
    assert not any(v.applicable for v in got.values())


def test_exception_during_scoring_leaves_no_stale_value() -> None:
    """예외가 나도 직전 요청 값이 잔류하지 않는다."""
    s = _scorer()
    _fill(s, {"2027-03": PolarityRole.GI})

    class _Boom(Exception):
        pass

    sink: dict[str, object] = {}
    s._dw_bg_tls.sink = sink
    try:
        raise _Boom
    except _Boom:
        pass
    finally:
        from types import MappingProxyType

        s._dw_bg_tls.sink = None
        s._dw_bg_tls.last = MappingProxyType(dict(sink))
    assert s.take_daewoon_hwa_backgrounds() == {}


def test_concurrent_requests_do_not_mix() -> None:
    """동시 요청의 배경 맵이 섞이지 않는다 — thread-local 이어야 하는 이유."""
    import threading

    s = _scorer()
    seen: dict[str, set[str]] = {}

    def worker(name: str, periods: dict[str, PolarityRole | None]) -> None:
        _fill(s, periods)
        seen[name] = set(s.take_daewoon_hwa_backgrounds())

    threads = [
        threading.Thread(target=worker, args=("a", {"2027-03": PolarityRole.GI})),
        threading.Thread(target=worker, args=("b", {"2029-01": PolarityRole.YONG})),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert seen["a"] == {"2027-03"}
    assert seen["b"] == {"2029-01"}


def test_take_without_any_scoring_returns_empty() -> None:
    """한 번도 채점하지 않은 스코어러는 빈 맵을 준다."""
    assert _scorer().take_daewoon_hwa_backgrounds() == {}


# ── 전 섹션 claim 감사 · 모드별 enforcement ──────────────────────────────


_BAD_SENTENCE = "대운 배경이 2028년 3월을 대표 시점으로 끌어올렸어요."
_TAIL = " 나머지 서술은 그대로입니다."


def _audit(*, enforce: bool, background_present: bool, text: str = _BAD_SENTENCE + _TAIL):
    from saju_engines.section_claim_audit import audit_daewoon_hwa_claims

    return audit_daewoon_hwa_claims(
        "W-04", text, enforce=enforce, background_present=background_present,
        fallback_text="폴백 문구." if enforce else None,
    )


def test_current_mode_detects_but_leaves_output_identical() -> None:
    """current 모드에서 금지 문장을 탐지해도 출력은 완전히 동일하다.

    fallback 만 모드로 나누고 patch 를 공통 실행하면 current 출력이 조용히 달라진다 —
    분기는 patch 호출 **이전**에 있어야 한다.
    """
    text = _BAD_SENTENCE + _TAIL
    out = _audit(enforce=False, background_present=True, text=text)
    assert out.violations          # 탐지는 된다
    assert out.text == text        # 출력은 그대로
    assert not out.patched and not out.fell_back


def test_section_without_background_does_not_invent_one() -> None:
    """배경이 제공되지 않은 섹션에 배경 문장을 새로 만들지 않는다.

    전 섹션을 감사하므로 배경 블록 없는 섹션에서도 금지 문장이 나올 수 있다. 이때
    '장기 대운 배경은…' 으로 치환하면 주지도 않은 배경을 생성하게 된다.
    """
    out = _audit(enforce=True, background_present=False)
    assert out.patched
    assert "대운 배경" not in out.text
    assert not out.remaining


def test_section_with_background_keeps_background_framing() -> None:
    """배경이 있는 섹션은 배경을 지우지 않고 허용 범위로 되돌린다."""
    out = _audit(enforce=True, background_present=True)
    assert "대운 배경" in out.text
    assert not out.remaining


def test_unpatchable_variant_falls_back_to_section_text() -> None:
    """patch 로 해결되지 않으면 그 섹션만 폴백한다 — 새 LLM 호출은 없다."""
    from saju_engines import section_claim_audit as S

    # 안전 문장 자체가 위반으로 남는 상황을 만들어 재감사 실패를 강제한다.
    original = S._BG_SAFE_WITH_BACKGROUND
    try:
        S._BG_SAFE_WITH_BACKGROUND = _BAD_SENTENCE
        out = _audit(enforce=True, background_present=True)
    finally:
        S._BG_SAFE_WITH_BACKGROUND = original
    assert out.fell_back
    assert out.text == "폴백 문구."
    assert not out.remaining


def test_audit_observations_are_request_scoped() -> None:
    """관측 계수가 요청 간 섞이면 승격 판단이 왜곡된다."""
    from saju_engines.section_claim_audit import (
        start_daewoon_hwa_audit_collection,
        take_daewoon_hwa_audit,
    )

    start_daewoon_hwa_audit_collection()
    _audit(enforce=True, background_present=True)
    assert len(take_daewoon_hwa_audit()) == 1
    assert take_daewoon_hwa_audit() == ()
