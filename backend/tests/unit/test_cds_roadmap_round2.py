"""CDS 로드맵 2라운드 — P1a(rank 분리)·P1d(marker shadow)·P1-b(hedge 계측) 단위 검증."""

from __future__ import annotations

from datetime import date

from saju_api.services.chat_service import _hedge_density
from saju_engines.marriage_marker_shadow import detect_marriage_marker_shadow
from saju_shared_types.llm_input import LlmEventCandidate


def _cand(**kw) -> LlmEventCandidate:
    base = dict(
        event_key="marriage_signal", event_ko="결혼 신호", period="2026-12", ganji="庚子",
        daewoon_context="", score=80, confidence="medium", polarity="neutral",
    )
    base.update(kw)
    return LlmEventCandidate(**base)


# ── P1d — marker shadow (Detection 전용, exposure 불변) ─────────────────────


def test_no_mt_candidates_no_markers() -> None:
    out = detect_marriage_marker_shadow([_cand()])  # MT 코드 없음
    assert not out.commitment_marker and not out.formalization_marker
    assert len(out.unevaluated) == 2  # 미평가 후보 coverage 명시


def test_mt2_emergence_triggers_commitment_only() -> None:
    out = detect_marriage_marker_shadow(
        [_cand(evidence_path=["MT2_EMERGENCE_SAME_STEM"])]
    )
    assert out.commitment_marker is True
    assert out.formalization_marker is False
    assert any("MT2" in r for r in out.reasons)


def test_document_coupling_triggers_both() -> None:
    out = detect_marriage_marker_shadow([
        _cand(evidence_path=["MT1_DAY_STEM_HAP"]),
        _cand(event_key="contract_document", event_ko="계약·문서"),
    ])
    assert out.commitment_marker is True
    assert out.formalization_marker is True


def test_gwandae_stage_triggers_formalization() -> None:
    out = detect_marriage_marker_shadow(
        [_cand(evidence_path=["MT1_DAY_STEM_HAP", "stage:GWANDAE"])]
    )
    assert out.formalization_marker is True
    assert out.commitment_marker is False


def test_committed_status_confluence() -> None:
    out = detect_marriage_marker_shadow(
        [_cand(evidence_path=["MT1_A", "MT2_B", "MT3_C"])],
        relationship_status="dating",
    )
    assert out.commitment_marker is True
    # 상태 없으면 confluence 만으로는 c4 미성립(MT2 단독 사유는 별개로 성립).
    base = detect_marriage_marker_shadow([_cand(evidence_path=["MT1_A", "MT3_C"])])
    assert base.commitment_marker is False


# ── P1-b — hedge density 계측 ───────────────────────────────────────────────


def test_hedge_density_counts_sentences() -> None:
    text = "결과는 유리합니다. 다만 늦어질 수 있어요. 진행하세요. 조건이 붙을 수 있습니다."
    hits, total = _hedge_density(text)
    assert (hits, total) == (2, 4)


# ── P1a — rank 필드가 프롬프트에 분리 표기 ──────────────────────────────────


def test_period_rank_line_in_prompt() -> None:
    from saju_api.services import chat_service
    from saju_shared_types.birth_input import BirthInput

    birth = BirthInput(
        calendar_type="solar", birth_date="1984-08-19", birth_time="10:15",
        birth_place_name="서울", gender="male",
    )
    p = chat_service.chat(
        birth, "2026년 12월 이직 운 어때?", date(2026, 8, 21), True
    ).prompt_preview or ""
    assert "강도 맥락: 기간 내 상대 " in p
    assert "절대 강도 표현과 별개" in p
