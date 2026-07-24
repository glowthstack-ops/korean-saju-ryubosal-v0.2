"""P0-A relation delta legacy 동작 고정 (RELATIONSHIP_EVENT_SYSTEM 부록 A-3·B).

두 층위를 분리해 고정한다:
- **Legacy characterization** — 현재 점수 동작을 의도적으로 보존(수정 아님·관측 기준선).
  P1 벡터화·이후 소유권 전환(§4-1 옵션 1/3) 시 이 기대가 바뀌면 명시적 결정으로만 갱신.
- **Safety expectation** — 결함의 사용자 노출을 허용하지 않는 안전 기대(B2 가드).

측정 하네스 원본: scripts/audits/relationship_p0a/ (읽기 전용 감사, 2026-07-24).
"""

from __future__ import annotations

from pathlib import Path

from saju_engines.marriage_output_guard import has_stability_risk
from saju_engines.relation_palace_engine import RelationActivation, RelationPalaceEngine
from saju_shared_types.event_engine import (
    EventCandidateV2,
    LuckLayer,
    Pillar4,
    RelationKind,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_CAP = 22.0  # relation_palace_engine._MAX_RELATION_DELTA — legacy 상한(P0-A A-3 #3)


def _eng() -> RelationPalaceEngine:
    return RelationPalaceEngine(_DICTS)


def _cands(score: int = 50) -> list[EventCandidateV2]:
    return [
        EventCandidateV2(event_key="relationship_change", period="2026", score=score),
        EventCandidateV2(event_key="marriage_signal", period="2026", score=score),
        EventCandidateV2(event_key="new_relationship", period="2026", score=score),
    ]


def _apply(kinds: list[RelationKind], score: int = 50) -> dict[str, EventCandidateV2]:
    acts = [RelationActivation(k, Pillar4.DAY, LuckLayer.SEWOON) for k in kinds]
    out = _eng().apply(_cands(score), acts)
    return {str(c.event_key): c for c in out}


# ── Legacy characterization — 현재 점수 동작 보존(관측 기준선) ─────────────────────


def test_chung_creates_activation_delta_on_both_labeled_keys() -> None:
    """충은 방향 무관 중립 활성 — relationship_change와 marriage_signal에 동시 가산.

    (방향 누수의 characterization: 점수 계층은 방향을 구분하지 않는다 — 사용자 노출
    차단은 safety 계층(B2)이 담당. 이 동작 변경은 §4-1 소유권 전환 결정으로만.)
    """
    by = _apply([RelationKind.CHUNG])
    assert by["relationship_change"].score > 50
    assert by["marriage_signal"].score > 50


def test_delta_cap_22_saturates_compound_patterns() -> None:
    """상한 22 포화 — 충 단독과 충+형 복합이 같은 delta(해상도 손실 characterization)."""
    single = _apply([RelationKind.CHUNG])["relationship_change"].score
    compound = _apply([RelationKind.CHUNG, RelationKind.HYEONG])["relationship_change"].score
    assert single - 50 <= _CAP and compound - 50 <= _CAP
    assert single == compound  # cap 포화로 변별 소실(P0-A A-3 #3)


def test_chung_delta_exceeds_hap_delta() -> None:
    """kind 서열 — 충 > 육합 (P0-A A-3 #5, relationship_change 기준)."""
    chung = _apply([RelationKind.CHUNG])["relationship_change"].score
    hap = _apply([RelationKind.HAP])["relationship_change"].score
    assert chung > hap > 50


def test_new_relationship_is_delta_blind_spot() -> None:
    """new_relationship은 legacy relation delta 사각지대 — 어떤 발동에도 0 가산.

    (P1 activation 벡터→P3 분기→P5 적용 검증 순으로 해소 예정 — legacy 사전에
    즉시 추가 금지: 부록 A-3 #2.)
    """
    for kinds in ([RelationKind.HAP], [RelationKind.CHUNG],
                  [RelationKind.HAP, RelationKind.CHUNG]):
        assert _apply(kinds)["new_relationship"].score == 50


def test_no_activation_no_change() -> None:
    """무발동 시 후보 무변경(무간섭 — P0-A 대조군 byte 일치의 유닛 등가)."""
    out = _eng().apply(_cands(), [])
    assert all(c.score == 50 and not c.reason_codes for c in out)


# ── Safety expectation — 결함의 사용자 노출 금지(B2) ──────────────────────────────


def test_chung_based_marriage_signal_flags_stability_risk() -> None:
    """충 기반 marriage_signal의 reason은 출력 가드에서 안정성 위험으로 판정돼야 한다."""
    by = _apply([RelationKind.CHUNG])
    assert has_stability_risk(list(by["marriage_signal"].reason_codes))


def test_hyeong_pa_hae_reasons_flag_stability_risk() -> None:
    for kind in (RelationKind.HYEONG, RelationKind.PA, RelationKind.HAE):
        by = _apply([kind])
        codes = list(by["relationship_change"].reason_codes)
        assert codes and has_stability_risk(codes), kind


def test_hap_only_reasons_do_not_flag_risk() -> None:
    """합 단독 발동 reason은 위험 아님(합=결속·재정의 활성)."""
    by = _apply([RelationKind.HAP])
    codes = list(by["marriage_signal"].reason_codes)
    assert codes and not has_stability_risk(codes)


def test_guard_layer_does_not_touch_scores() -> None:
    """B2는 출력 가드 전용 — 판정 실행이 점수·reason을 변경하지 않는다."""
    by = _apply([RelationKind.CHUNG])
    before = {k: (c.score, list(c.reason_codes)) for k, c in by.items()}
    for c in by.values():
        has_stability_risk(list(c.reason_codes))
    after = {k: (c.score, list(c.reason_codes)) for k, c in by.items()}
    assert before == after
