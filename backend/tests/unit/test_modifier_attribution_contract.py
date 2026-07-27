"""modifier occurrence 귀속 계약 (P2-PROV-2b) — 2026-07-27 데굴님 확정.

설계: `doc/v2_2/REVIEW_CONTRIBUTION_PROVENANCE.md` §14

5종 modifier는 후보별 상위 사건 지지를 공급할 수 없다고 실사로 판정했다. 이 테스트는
그 판정을 하드코딩하지 않는다 — **판정의 근거가 된 입력 구조**를 고정한다. 입력이
바뀌면(예: relation이 target 외 층위를 읽기 시작) 실패해서 PROV-2 재감수를 강제한다.

    relation       TARGET_LAYER_ONLY   target 기둥 × 원국만 본다
    twelve_stage   STACK_LEVEL         층위 판정을 stack 기반 필드로 한다
    layer_flow     STACK_LEVEL         스택 조합 배율 + evaluated union 십성
    wealth         NOT_RECOVERABLE     층위를 버리고 지지 집합만 만든다
    ranker         후처리              후보 생성 이후 순위·등급만 바꾼다

여기서 고정하는 것은 "현재 자격 없음"이 아니라 "왜 자격이 없는지"다.
"""

from __future__ import annotations

import inspect

from saju_engines import event_engine_v2, event_ranker, layer_flow_modifier, twelve_stage_modifier


def _src(mod) -> str:
    return inspect.getsource(mod)


# ── relation — target 층위 하나만 본다 ────────────────────────────


def test_relation_activations_use_target_layer_only() -> None:
    """관계 발동은 채점 대상 층위로만 만들어진다 — 상위 층위를 공급할 수 없다.

    이 구조가 바뀌면(상위 층위 hit을 함께 넘기면) 일운 후보도 대운·세운 관계 근거를
    가질 수 있게 되므로 PROV-2 감수를 다시 해야 한다.
    """
    src = _src(event_engine_v2)
    assert "layer = target_layer" in src
    assert "_activations(hits, layer)" in src
    # hits 자체가 target 기둥 기준이다.
    assert "self._relation_hits(result, level, target)" in src


# ── twelve_stage — 층위 판정이 stack 기반이다 ─────────────────────


def test_twelve_stage_layer_gate_reads_stack_not_candidate_provenance() -> None:
    """12운성은 후보의 stack 필드로 층위를 거른다 — 후보별 귀속이 아니다."""
    src = _src(twelve_stage_modifier)
    assert "if layer not in c.source_layers" in src
    # 후보별 기여 필드를 읽기 시작하면 귀속 판정이 달라진다.
    assert "candidate_source_layers" not in src


# ── layer_flow — 스택 조합 배율 + evaluated union ─────────────────


def test_layer_flow_multiplier_is_keyed_by_whole_stack() -> None:
    """배율 키가 후보 기여가 아니라 스택 조합 전체다."""
    src = _src(layer_flow_modifier)
    assert "frozenset(c.source_layers)" in src
    assert "candidate_source_layers" not in src


def test_layer_flow_repeat_uses_evaluated_union_ten_gods() -> None:
    """반복 판정 입력이 evaluated union(source_ten_gods)이다 — provenance가 아니다."""
    assert "set(c.source_ten_gods) & repeated_gods" in _src(layer_flow_modifier)


# ── wealth — 층위를 버린다 ───────────────────────────────────────


def test_wealth_activation_discards_layer(  ) -> None:
    """재물 발동은 스택 지지를 집합으로 뭉개 층위를 남기지 않는다 — 복원 불가."""
    src = _src(event_engine_v2)
    assert "luck_branches = {pillar.branch for _layer, pillar in stack}" in src
    # `_layer` 언더스코어 폐기가 곧 '층위를 쓰지 않는다'는 계약이다.
    # 이 줄이 바뀌어 층위를 보존하기 시작하면 wealth를 가설에 넣을 수 있는지 재감수한다.


# ── ranker — 후보 생성 이후 후처리 ───────────────────────────────


def test_ranker_does_not_touch_candidate_provenance() -> None:
    """랭커는 순위·등급만 바꾸고 후보 기여 층위를 읽거나 쓰지 않는다."""
    src = _src(event_ranker)
    assert "candidate_source_layers" not in src
    assert "stack_layers" not in src
    # 억제 판정도 여전히 stack 기반 source_layers를 본다(귀속 아님).
    assert "lset = set(c.source_layers)" in src


# ── daewoon_hwa — 유일하게 대운을 특정한다 ───────────────────────


def test_daewoon_hwa_identifies_a_specific_daewoon_occurrence() -> None:
    """대운 합화만 특정 대운 천간을 집어낸다 — PROV-2a 관측 대상인 이유."""
    src = _src(event_engine_v2)
    assert (
        "dw_stem = next((p.stem for layer, p in stack if layer is LuckLayer.DAEWOON), None)"
        in src
    )


def test_daewoon_hwa_branches_on_quality_not_event_key() -> None:
    """대운 합화는 후보별이 아니라 quality(길/흉)군 단위로 같은 배율을 쓴다.

    그래서 occurrence를 특정할 수 있어도 '사건 발생의 상위 근거'로 바로 승격하지
    않는다(설계 §14-3 — support_eligibility=REVIEW_REQUIRED).
    """
    src = inspect.getsource(event_engine_v2._apply_daewoon_hwa_background)
    assert "c.quality in _GOOD_Q" in src
    assert "c.quality in _BAD_Q" in src
    assert "c.event_key" not in src
