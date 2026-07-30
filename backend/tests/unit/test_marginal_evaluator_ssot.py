"""OA-11f-S 보조 — marginal 평가자 SSOT 의 단계 라벨 계약.

`audit_oa11f_ssot_parity` 는 origin~2026-04-02 전 행에서 동작 보존을 증명했지만,
`KEY_MARGINAL` 분기는 그 구간에서 한 번도 관측되지 않았다(0건). 실측으로 닫히지
않은 분기는 fixture 로 닫는다 — 관측되지 않은 분기를 "검증됨"으로 계상하지 않기
위한 회귀다.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
for _p in (_BACKEND / "scripts",):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import audit_oa11f_b_online_replay as B  # noqa: E402


def _baseline(**kw):
    base = dict(
        available=True, base_key_coverage=20, base_family_coverage=14,
        raw_top_band=3, raw_probability=70, loss_limit=6, window=(),
    )
    return B.MarginalBaseline(**(base | kw))


def test_stage_labels_and_mediation_map_are_aligned() -> None:
    """단계 목록과 mediation 매핑이 어긋나면 진단 라벨이 조용히 비어버린다."""
    assert set(B.MARGINAL_STAGES) == set(B.STAGE_TO_MEDIATION)
    assert all(v.endswith("_MEDIATION") for v in B.STAGE_TO_MEDIATION.values())


def _stub_pipeline(monkeypatch, preboard_key: str, family: str) -> None:
    """slot·후보·projection 단계를 통제해 한계효과 분기만 시험한다."""
    node = SimpleNamespace(event_key=preboard_key, domain="d", probability=64)
    monkeypatch.setattr(
        B.M, "_select_slots", lambda *a, **k: (node, node, node)
    )
    monkeypatch.setattr(B.M, "_band", lambda *a, **k: 3)
    monkeypatch.setattr(B.M, "_headline_candidates", lambda *a, **k: [node])
    monkeypatch.setattr(
        B, "derive_top1_family_projection",
        lambda **k: SimpleNamespace(
            status=B.ProjectionStatus.PROJECTED, family=family
        ),
    )


@pytest.mark.parametrize(
    ("prob", "expected"),
    [(64, "PASS"), (63, "LOSS_OVER_LIMIT")],   # raw 70 → 손실 6 통과 / 7 차단
)
def test_loss_limit_is_the_diversity_limit_not_the_global_budget(
    prob: int, expected: str, monkeypatch
) -> None:
    """손실 상한은 보조 정책의 실효 상한(6p)이다 — 전역 예산 7p 가 아니다."""
    _stub_pipeline(monkeypatch, "x", "F1")
    ev = B.evaluate_marginal_candidate(
        scored=[], seed="", family_of={}, baseline=_baseline(),
        event_key="x", rank=2, probability=prob,
    )
    assert ev.safety_result == expected
    if expected != "PASS":
        assert ev.rejected_at_stage == "SAFETY"
        assert ev.mediation == "SAFETY_MEDIATION"
        assert ev.slot_feasible is None      # 안전 차단 후보는 slot 을 구성하지 않는다


def test_s5_protection_blocks_before_slot_construction() -> None:
    """s5(band 4) 원시 1위는 하위 band 후보로 교체하지 않는다."""
    ev = B.evaluate_marginal_candidate(
        scored=[], seed="", family_of={}, baseline=_baseline(raw_top_band=4),
        event_key="x", rank=2, probability=68,
    )
    assert (ev.safety_result, ev.rejected_at_stage) == (
        "S5_PROTECTION", "SAFETY"
    )


def test_key_marginal_stage_is_reachable_and_labelled(monkeypatch) -> None:
    """KEY_MARGINAL — family 는 늘지만 key 축이 손해인 후보는 탈락한다.

    실측 구간(origin~2026-04-02, 후보 평가 91,134건)에서 0건이었던 분기다. 실측으로
    닫히지 않았으므로 여기서 실제 평가자를 통과시켜 라벨까지 고정한다.
    """
    _stub_pipeline(monkeypatch, "b", "F2")
    fam = {"a": "F1", "b": "F2"}
    # base_key_coverage 를 크게 두어 key 축이 반드시 손해가 되게 만든다.
    base = _baseline(window=("a",), base_family_coverage=0, base_key_coverage=99)
    ev = B.evaluate_marginal_candidate(
        scored=[], seed="", family_of=fam, baseline=base,
        event_key="b", rank=2, probability=64,
    )
    assert ev.safety_result == "PASS"
    assert ev.slot_feasible is True
    assert ev.projection_status == B.ProjectionStatus.PROJECTED.value
    d_fam = ev.family_coverage_delta_vs_raw
    d_key = ev.key_coverage_delta_vs_raw
    assert d_fam is not None and d_key is not None
    assert d_fam > 0 and d_key < 0                # family 이득 · key 손해
    assert ev.rejected_at_stage == "KEY_MARGINAL"
    assert ev.mediation == "KEY_MARGINAL_MEDIATION"
    assert ev.selector_eligible is False


def test_family_marginal_stage_precedes_key_stage(monkeypatch) -> None:
    """family 이득이 없으면 key 축을 보기 전에 FAMILY_MARGINAL 로 탈락한다."""
    _stub_pipeline(monkeypatch, "b", "F2")
    fam = {"a": "F1", "b": "F2"}
    base = _baseline(window=("a",), base_family_coverage=99, base_key_coverage=0)
    ev = B.evaluate_marginal_candidate(
        scored=[], seed="", family_of=fam, baseline=base,
        event_key="b", rank=2, probability=64,
    )
    assert ev.rejected_at_stage == "FAMILY_MARGINAL"


def test_eligible_candidate_reports_positive_family_and_safe_key(monkeypatch) -> None:
    """자격 획득 후보는 family 순증가 + key 비손해를 동시에 만족한다."""
    _stub_pipeline(monkeypatch, "b", "F2")
    fam = {"a": "F1", "b": "F2"}
    base = _baseline(window=("a",), base_family_coverage=1, base_key_coverage=1)
    ev = B.evaluate_marginal_candidate(
        scored=[], seed="", family_of=fam, baseline=base,
        event_key="b", rank=2, probability=64,
    )
    assert ev.rejected_at_stage is None
    assert ev.selector_eligible is True
    assert ev.mediation is None
    d_fam = ev.family_coverage_delta_vs_raw
    d_key = ev.key_coverage_delta_vs_raw
    assert d_fam is not None and d_key is not None
    assert d_fam > 0 and d_key >= 0


def test_as_record_drops_unserialisable_objects() -> None:
    """artifact 직렬화 시 slot/candidate 객체가 새어 나가면 안 된다."""
    ev = B.evaluate_marginal_candidate(
        scored=[], seed="", family_of={}, baseline=_baseline(),
        event_key="x", rank=2, probability=50,
    )
    rec = ev.as_record()
    assert "slots" not in rec and "cands" not in rec
    assert rec["mediation"] == "SAFETY_MEDIATION"
